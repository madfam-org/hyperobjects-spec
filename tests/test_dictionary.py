"""Tests for the dictionary tools (RFC 0039 §6.2): define, lookup, related.

These are the functions both platforms' MCP servers wrap, so what is asserted here is
what an agent or an LLM will actually get back — including the parts that are easy to
get wrong quietly: which route resolved a word, whether an accent was required, and
whether an empty answer is distinguishable from an unasked question.
"""

import pytest

from hyperobjects_lexicon import LANGUAGES
from hyperobjects_lexicon.dictionary import define, lookup, related

# ------------------------------------------------------------------------- define


def test_define_resolves_a_term_id():
    record = define("tape-edge")
    assert record["id"] == "tape-edge"
    assert record["matched"]["route"] == "id"
    assert set(record["term"]) == set(LANGUAGES)


def test_define_resolves_a_headword_in_any_language():
    for word in ("sewn tape edge", "canto de cinta cosido", "bord de ruban cousu"):
        assert define(word)["id"] == "tape-edge"


def test_define_does_not_require_the_accent():
    """A dictionary that only answers when the accent is typed is a dictionary for
    people who already know the word."""
    assert define("elevacion del escote trasero")["id"] == "back-neck-rise"
    assert define("elevación del escote trasero")["id"] == "back-neck-rise"


def test_define_resolves_a_repo_spelling_through_an_alias():
    """The B2 case, as a user experiences it: arrive with either dialect, land on one
    entry."""
    assert define("zipper_tape")["id"] == "tape-edge"
    assert define("tape_edge")["id"] == "tape-edge"


def test_define_resolves_a_vocabulary_key_and_its_near_duplicate():
    assert define("knit_negative_ease")["id"] == "knit-negative-ease"
    assert define("negative_ease_knit")["id"] == "knit-negative-ease"


def test_define_prefers_a_term_id_over_another_terms_alias():
    """A real collision, not a hypothetical: `ease` recorded `knit_negative_ease` as an
    alias before that flag had an entry of its own. A manifest key that IS a term id
    under another separator resolves to that term."""
    record = define("knit_negative_ease")
    assert record["id"] == "knit-negative-ease"
    assert record["matched"]["route"] == "id"


def test_define_prefers_an_exact_id_over_anyone_elses_alias():
    """Resolution order is not cosmetic: an id a caller named must never be shadowed."""
    record = define("snap")
    assert record["id"] == "snap"
    assert record["matched"]["route"] == "id"


def test_define_narrows_to_one_language():
    record = define("tape-edge", "pt")
    assert record["lang"] == "pt"
    assert record["term"] == "debrum de fita costurado"
    assert isinstance(record["definition"], str)


def test_define_refuses_a_language_the_commons_does_not_speak():
    """Silently returning all four to a caller who asked for one would render the wrong
    one."""
    with pytest.raises(ValueError):
        define("tape-edge", "de")


def test_define_reports_whether_a_human_has_read_the_entry():
    """RFC 0039 §5: a drafted entry must never read as a reviewed one, including through
    the MCP surface."""
    assert define("knit-negative-ease")["review"] == "generated"
    assert define("tape-edge")["review"] == "unmarked"


def test_define_carries_the_constraint():
    """The field that pays for the lexicon travels with the definition, or an agent
    quoting the definition drops the rule."""
    assert "clamp" in define("back-neck-rise")["constraints"].lower()


def test_define_returns_none_for_an_unknown_word():
    assert define("no-such-word-anywhere") is None
    assert define("   ") is None


# ------------------------------------------------------------------------- lookup


def test_lookup_finds_every_term_a_cartridge_embodies():
    record = lookup("fashion-cabinet/garter-belt")
    ids = {t["id"] for t in record["terms"]}
    assert {"strap-slot", "shaped-ring", "hook-closure"} <= ids
    assert record["repos"] == ["fashion-cabinet"]
    assert record["count"] == len(record["terms"])


def test_lookup_accepts_a_bare_slug_and_says_which_commons_answered():
    """A bare slug may be real on either side; the answer names the side rather than
    picking one."""
    record = lookup("chainmail-panel")
    assert record["repos"] == ["fashion-cabinet"]
    assert record["count"] >= 1


def test_lookup_of_an_unknown_object_is_an_empty_answer_not_an_error():
    record = lookup("yantra4d/not-a-cartridge")
    assert record["count"] == 0
    assert record["terms"] == []


def test_lookup_carries_the_constraints():
    """The question behind `lookup(object)` is "what rules apply to this thing", so the
    rules travel with the terms."""
    record = lookup("fashion-cabinet/changpao")
    assert any(t["constraints"] for t in record["terms"])


# ------------------------------------------------------------------------ related


def test_related_gives_both_directions_of_the_graph():
    """A term can be central and look isolated from its own file — cross references are
    authored one way."""
    record = related("tape-edge")
    assert "flange" in record["see_also"]
    assert "panel-edge" in record["referenced_by"]


def test_related_reports_the_manifest_keys_that_write_the_term():
    record = related("tape-edge")
    keys = {(k["repo"], k["key"]) for k in record["vocabulary_keys"]}
    assert ("yantra4d", "tape_edge") in keys
    assert ("fashion-cabinet", "zipper_tape") in keys


def test_related_reports_the_aliases_a_key_absorbs():
    record = related("knit-negative-ease")
    aliases = {a for k in record["vocabulary_keys"] for a in k["aliases"]}
    assert "negative_ease_knit" in aliases


def test_related_returns_none_for_an_unknown_term():
    assert related("no-such-term") is None


# ---------------------------------------------------------------------------- CLI


@pytest.mark.parametrize("prog", ["fc-spec", "y4d-spec"])
def test_the_dictionary_commands_are_on_both_clis(prog, capsys):
    main = (
        __import__("fc_spec.cli", fromlist=["main"]).main
        if prog == "fc-spec"
        else __import__("y4d_spec.cli", fromlist=["main"]).main
    )
    assert main(["define", "zipper_tape", "--lang", "es"]) == 0
    assert "canto de cinta cosido" in capsys.readouterr().out

    assert main(["lookup", "fashion-cabinet/garter-belt"]) == 0
    assert f"{prog} lookup:" in capsys.readouterr().out

    assert main(["related", "tape-edge"]) == 0
    assert "referenced_by" in capsys.readouterr().out


def test_cli_define_exits_nonzero_on_an_unknown_word(capsys):
    from fc_spec.cli import main

    assert main(["define", "no-such-word"]) == 1
    assert "no entry" in capsys.readouterr().out


def test_cli_json_output_is_the_record_itself(capsys):
    import json

    from y4d_spec.cli import main

    assert main(["define", "tape-edge", "--json"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["id"] == "tape-edge"
    assert record["matched"]["route"] == "id"
