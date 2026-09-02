"""Tests for the controlled vocabularies (RFC 0039 G3, absorbing RFC 0038 §5 B2).

Same split as the lexicon tests: assertions about the shipped documents, then one test
per failure class the lane claims to catch. The second half matters more here than
usual — a vocabulary's rules are about relationships between entries, and a rule that
has never been seen to fire is indistinguishable from one that does nothing.
"""

import copy
import json

import pytest

from hyperobjects_lexicon import (
    VOCABULARIES,
    canonical_key,
    check_vocabularies,
    check_vocabulary,
    equivalences,
    load_lexicon,
    load_vocabularies,
    vocabulary_status,
)
from hyperobjects_lexicon.vocabulary import TERM_REQUIRED_AT, _index


@pytest.fixture(scope="module")
def vocabularies():
    return load_vocabularies()


@pytest.fixture(scope="module")
def lexicon():
    return load_lexicon()


@pytest.fixture
def pair():
    """A minimal two-entry vocabulary, for the relationship rules."""
    return {
        "capabilities": {
            "spec_version": 1,
            "vocabulary": "capabilities",
            "entries": [
                {
                    "key": "one_thing",
                    "repo": "fashion-cabinet",
                    "role": "capability_flag",
                    "status": "canonical",
                    "gloss": "The first thing, for testing.",
                },
                {
                    "key": "other_thing",
                    "repo": "yantra4d",
                    "role": "capability_flag",
                    "status": "canonical",
                    "gloss": "The second thing, for testing.",
                },
            ],
        }
    }


# --------------------------------------------------------------------- documents


def test_both_vocabularies_ship_and_conform(vocabularies):
    assert set(vocabularies) == set(VOCABULARIES)
    result = check_vocabularies(vocabularies)
    assert result.ok, "\n".join(result.problems)


def test_every_entry_says_what_its_key_means(vocabularies):
    """A registry of keys with no meanings attached is a list, not a vocabulary."""
    for name, doc in vocabularies.items():
        for entry in doc["entries"]:
            assert (
                entry.get("term") or entry.get("gloss") or entry.get("needs_definition")
            ), f"{name}: {entry['repo']}/{entry['key']}"


def test_widely_used_keys_carry_a_quadrilingual_term(vocabularies, lexicon):
    """The rule that keeps the vocabulary and the lexicon in step: a key two or more
    cartridges write is vocabulary the commons reads, and it ships in four languages."""
    for name, doc in vocabularies.items():
        for entry in doc["entries"]:
            uses = (entry.get("observed") or {}).get("cartridges", 0)
            if uses >= TERM_REQUIRED_AT:
                assert entry.get("term"), f"{name}: {entry['repo']}/{entry['key']} ({uses})"
                assert entry["term"] in lexicon


def test_the_b2_equivalence_is_recorded_in_both_directions(vocabularies):
    """RFC 0038 §5 B2, the pair that named the problem. A reader arriving with either
    spelling has to find the other, so the edge is on both entries."""
    assert ("fashion-cabinet/zipper_tape", "yantra4d/tape_edge") in equivalences(vocabularies)


def test_every_equivalence_is_cross_repo_and_symmetric(vocabularies):
    """An equivalence inside one repo would be an alias; an edge only one side declares
    is half a record."""
    index = _index(vocabularies)
    for doc in vocabularies.values():
        for entry in doc["entries"]:
            for edge in entry.get("equivalent_to") or []:
                assert edge["repo"] != entry["repo"], f"{entry['key']}"
                other = index[(edge["repo"], edge["key"])]
                back = {(e["repo"], e["key"]) for e in other.get("equivalent_to") or []}
                assert (entry["repo"], entry["key"]) in back


def test_the_false_friend_pair_is_recorded_on_both_halves(vocabularies):
    """`pocket` is a garment pocket on one side and a recess in a solid on the other.
    Recorded as distinct on both entries, so no de-duplication pass can merge them from
    either direction."""
    index = _index(vocabularies)
    for repo, other in (
        ("fashion-cabinet", "yantra4d"),
        ("yantra4d", "fashion-cabinet"),
    ):
        entry = index[(repo, "pocket")]
        targets = {(d["repo"], d["key"]) for d in entry["distinct_from"]}
        assert (other, "pocket") in targets
        assert all(d["reason"] for d in entry["distinct_from"])


def test_the_capability_near_duplicates_canonicalise(vocabularies):
    """The audit's headline pair, and the two the capture added to it."""
    assert canonical_key("negative_ease_knit") == "knit_negative_ease"
    assert canonical_key("hardware_reference") == "hardware_bridge"
    assert canonical_key("one_handed_dressing") == "one_handed_operation"
    assert canonical_key("one_handed_clip") == "one_handed_operation"


def test_canonical_key_leaves_canonical_and_unknown_keys_alone(vocabularies):
    """A vocabulary that renamed keys it has never seen would be worse than the drift it
    is fixing, so an unknown key comes back unchanged."""
    assert canonical_key("knit_negative_ease") == "knit_negative_ease"
    assert canonical_key("some_key_nobody_has_written") == "some_key_nobody_has_written"


def test_hook_closure_is_not_canonicalised_onto_hook_loop_closure(vocabularies):
    """The false friend in the capability space: they look like a near-duplicate pair and
    bridge to different solid cartridges. Neither rewrites onto the other."""
    assert canonical_key("hook_loop_closure") == "hook_loop_closure"
    assert canonical_key("hook_closure") == "hook_closure"


def test_the_capability_vocabulary_invalidates_no_existing_cartridge(vocabularies):
    """Additive by construction: every key the capture saw is either an entry or an
    alias of one, so a compliance lane can adopt this today without failing a cartridge
    that is correct."""
    doc = vocabularies["capabilities"]
    known = {e["key"] for e in doc["entries"]}
    known |= {a["name"] for e in doc["entries"] for a in e.get("aliases") or []}
    assert len(known) == 134, sorted(known)


def test_the_capture_is_dated_and_attributed(vocabularies):
    """A vocabulary is a reading of a corpus at a moment. A reading with no date is a
    claim nobody can check or refresh."""
    for doc in vocabularies.values():
        captured = doc["captured"]
        assert captured["date"]
        assert captured["sources"]["fashion-cabinet"]["cartridges"] >= 1


def test_the_canonicalisations_do_not_claim_a_review_nobody_did(vocabularies):
    """Counts are measurements; canonicalisations are proposals about meaning. The
    document says which it has had."""
    for doc in vocabularies.values():
        review = doc["review"]
        assert review["state"] in {"generated", "reviewed"}
        if review["state"] == "reviewed":
            assert review.get("reviewers")


def test_status_lines_carry_the_undefined_count(vocabularies):
    """`needs_definition` is on the status line precisely so it cannot be mistaken for
    zero."""
    lines = vocabulary_status(vocabularies)
    assert len(lines) == len(vocabularies)
    for name, line in zip(sorted(vocabularies), lines, strict=True):
        assert line.startswith(f"vocabulary_status[{name}]:")
        assert "undefined=" in line


# ------------------------------------------------------------------- failure classes


def test_validator_catches_an_entry_that_defines_nothing(pair):
    del pair["capabilities"]["entries"][0]["gloss"]
    result = check_vocabularies(pair, lexicon={})
    assert not result.ok
    assert any("needs_definition" in p for p in result.problems)


def test_validator_catches_a_widely_used_key_with_no_term(pair):
    pair["capabilities"]["entries"][0]["observed"] = {"cartridges": 9}
    result = check_vocabularies(pair, lexicon={})
    assert any("quadrilingual" in p for p in result.problems)


def test_validator_catches_a_dangling_term(pair):
    pair["capabilities"]["entries"][0]["term"] = "no-such-term"
    result = check_vocabularies(pair, lexicon={"something-else": {}})
    assert any("not in the lexicon" in p for p in result.problems)


def test_validator_catches_a_duplicate_key_in_one_repo(pair):
    pair["capabilities"]["entries"].append(copy.deepcopy(pair["capabilities"]["entries"][0]))
    result = check_vocabularies(pair, lexicon={})
    assert any("declared twice" in p for p in result.problems)


def test_the_same_key_in_both_repos_is_legal(pair):
    """It is exactly the `pocket` case: one spelling, two repos, two meanings."""
    twin = copy.deepcopy(pair["capabilities"]["entries"][0])
    twin["repo"] = "yantra4d"
    twin["key"] = "one_thing"
    twin["distinct_from"] = [
        {"key": "one_thing", "repo": "fashion-cabinet", "reason": "Different things entirely."}
    ]
    pair["capabilities"]["entries"][0]["distinct_from"] = [
        {"key": "one_thing", "repo": "yantra4d", "reason": "Different things entirely."}
    ]
    pair["capabilities"]["entries"].append(twin)
    assert check_vocabularies(pair, lexicon={}).ok


def test_validator_catches_an_alias_that_is_also_an_entry(pair):
    pair["capabilities"]["entries"][0]["aliases"] = [
        {"name": "other_thing", "repo": "yantra4d"}
    ]
    result = check_vocabularies(pair, lexicon={})
    assert any("circular" in p for p in result.problems)


def test_validator_catches_two_entries_claiming_one_alias(pair):
    for entry in pair["capabilities"]["entries"]:
        entry["aliases"] = [{"name": "a_third_spelling", "repo": "fashion-cabinet"}]
    result = check_vocabularies(pair, lexicon={})
    assert any("canonicalises onto one key" in p for p in result.problems)


def test_validator_catches_a_same_repo_equivalence(pair):
    pair["capabilities"]["entries"][1]["repo"] = "fashion-cabinet"
    pair["capabilities"]["entries"][0]["equivalent_to"] = [
        {"key": "other_thing", "repo": "fashion-cabinet"}
    ]
    pair["capabilities"]["entries"][1]["equivalent_to"] = [
        {"key": "one_thing", "repo": "fashion-cabinet"}
    ]
    result = check_vocabularies(pair, lexicon={})
    assert any("SAME repo" in p for p in result.problems)


def test_validator_catches_a_one_sided_equivalence(pair):
    pair["capabilities"]["entries"][0]["equivalent_to"] = [
        {"key": "other_thing", "repo": "yantra4d"}
    ]
    result = check_vocabularies(pair, lexicon={})
    assert any("does not point back" in p for p in result.problems)


def test_validator_catches_a_one_sided_false_friend(pair):
    pair["capabilities"]["entries"][0]["distinct_from"] = [
        {"key": "other_thing", "repo": "yantra4d", "reason": "They are not the same thing."}
    ]
    result = check_vocabularies(pair, lexicon={})
    assert any("does not say so in return" in p for p in result.problems)


def test_validator_catches_a_dangling_equivalence(pair):
    pair["capabilities"]["entries"][0]["equivalent_to"] = [
        {"key": "nothing_here", "repo": "yantra4d"}
    ]
    result = check_vocabularies(pair, lexicon={})
    assert any("does not resolve" in p for p in result.problems)


def test_validator_catches_a_narrower_than_cycle(pair):
    pair["capabilities"]["entries"][0]["narrower_than"] = {
        "key": "other_thing",
        "repo": "yantra4d",
    }
    pair["capabilities"]["entries"][1]["narrower_than"] = {
        "key": "one_thing",
        "repo": "fashion-cabinet",
    }
    result = check_vocabularies(pair, lexicon={})
    assert any("cycle" in p for p in result.problems)


def test_validator_catches_a_filename_disagreement(pair):
    problems = check_vocabulary(pair["capabilities"], name="interfaces")
    assert any("declares vocabulary" in p for p in problems)


def test_validator_catches_an_unsigned_review_claim(pair):
    pair["capabilities"]["review"] = {"state": "reviewed"}
    result = check_vocabularies(pair, lexicon={})
    assert any("nobody signed" in p for p in result.problems)


def test_validator_catches_an_unknown_field(pair):
    pair["capabilities"]["entries"][0]["capabilty"] = "typo"
    assert not check_vocabularies(pair, lexicon={}).ok


# ------------------------------------------------------------------------------ CLI


@pytest.mark.parametrize("prog", ["fc-spec", "y4d-spec"])
def test_vocab_is_exposed_on_both_clis(prog, capsys):
    main = (
        __import__("fc_spec.cli", fromlist=["main"]).main
        if prog == "fc-spec"
        else __import__("y4d_spec.cli", fromlist=["main"]).main
    )
    assert main(["vocab"]) == 0
    out = capsys.readouterr().out
    assert f"{prog} vocab:" in out
    assert "vocabulary_status[interfaces]" in out


def test_cli_lists_the_equivalences_and_aliases_when_asked(capsys):
    from fc_spec.cli import main

    assert main(["vocab", "-v"]) == 0
    out = capsys.readouterr().out
    assert "equivalent fashion-cabinet/zipper_tape == yantra4d/tape_edge" in out
    assert "alias fashion-cabinet/negative_ease_knit -> fashion-cabinet/knit_negative_ease" in out


def test_cli_fails_on_a_broken_vocabulary(tmp_path, capsys):
    (tmp_path / "capabilities.json").write_text(
        json.dumps(
            {
                "spec_version": 1,
                "vocabulary": "capabilities",
                "entries": [
                    {
                        "key": "undefined_key",
                        "repo": "fashion-cabinet",
                        "role": "capability_flag",
                        "status": "canonical",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    from y4d_spec.cli import main

    assert main(["vocab", "--vocabularies", str(tmp_path)]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_cli_refuses_an_empty_vocabulary_set(tmp_path, capsys):
    from fc_spec.cli import main

    assert main(["vocab", "--vocabularies", str(tmp_path)]) == 2
    assert "vocabularies=0" in capsys.readouterr().out


def test_cli_status_flag_prints_only_the_status_lines(capsys):
    from fc_spec.cli import main

    assert main(["vocab", "--status"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert all(line.startswith("vocabulary_status[") for line in lines)
