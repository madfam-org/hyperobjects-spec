"""Tests for hyperobjects_lexicon — the Commons Lexicon corpus and its lane (RFC 0039).

Two halves, and the split is deliberate:

* **The corpus** — assertions about the ~30 shipped terms. These are the lane, run
  against the real data, so a term that breaks a bar fails here and not in a platform.
* **The validator** — one test per failure class the lane claims to catch. A validator
  is only worth its output if each rule is shown to actually fire; a rule nobody ever
  saw fail is indistinguishable from a rule that does nothing.
"""

import copy
import json

import pytest

from hyperobjects_lexicon import (
    LANGUAGES,
    bundled_catalog_slugs,
    check_lexicon,
    check_term,
    lexicon_status,
    load_catalog_slugs,
    load_lexicon,
    review_counts,
)
from hyperobjects_lexicon.cli import BUNDLED


@pytest.fixture(scope="module")
def lexicon():
    return load_lexicon()


@pytest.fixture
def a_term(lexicon):
    """A deep copy of a real, conformant term — the base every mutation starts from.

    Mutating a real entry rather than hand-rolling a minimal fixture means these tests
    fail if the schema tightens under them, which is the point.
    """
    return copy.deepcopy(lexicon["tape-edge"])


# --------------------------------------------------------------------------- corpus


def test_the_bundled_corpus_is_not_empty(lexicon):
    """An empty corpus passes every check vacuously. Seed size per RFC 0039 §8 (G1)
    is ~20 terms; this asserts the floor, not the exact count, so adding terms is not
    a test change."""
    assert len(lexicon) >= 20


def test_the_bundled_corpus_conforms(lexicon):
    result = check_lexicon(lexicon)
    assert result.ok, "\n".join(result.problems)


def test_every_shipped_term_is_quadrilingual(lexicon):
    """RFC 0039 §7: all four languages are a ship gate, and the schema's required-keys
    check cannot see a key present but blank."""
    for term_id, doc in lexicon.items():
        for field in ("term", "definition"):
            for lang in LANGUAGES:
                value = doc[field].get(lang)
                assert isinstance(value, str) and value.strip(), f"{term_id}.{field}.{lang}"


def test_no_dangling_cross_references(lexicon):
    known = set(lexicon)
    for term_id, doc in lexicon.items():
        for ref in doc.get("see_also", []):
            assert ref in known, f"{term_id} -> {ref}"


def test_every_embodied_by_slug_resolves_against_the_bundled_snapshot(lexicon):
    """The strict check, run hermetically. This is what makes the corpus a claim about
    real objects rather than about words."""
    result = check_lexicon(lexicon, catalog=bundled_catalog_slugs())
    assert result.ok, "\n".join(result.problems)
    assert result.catalog_checked


def test_the_corpus_covers_the_b2_seam_vocabulary(lexicon):
    """RFC 0039 §8 G1 absorbs RFC 0038's B2 workstream: the shared wearable interface
    vocabulary, the CDG interface types, and the drafting terms from #113's archaeology.
    Naming them here is what stops the seed corpus from quietly losing its charter."""
    required = {
        # the dialect unification that named the problem
        "tape-edge",
        # CDG interface types, from the manifest schema's geometry_type enum
        "grid", "rail", "thread", "socket", "snap", "bolt-pattern",
        # pattern drafting — the #113 archaeology
        "back-neck-rise", "shoulder-slope", "neck-drop", "ease", "seam-allowance",
        "dart", "raglan", "gusset",
        # the FC<->y4d handshake concepts
        "sew-field", "flange",
        # the geometry bar
        "body-count", "watertight",
    }
    assert required <= set(lexicon), sorted(required - set(lexicon))


def test_the_corpus_covers_the_interface_vocabulary(lexicon):
    """RFC 0039 §8 G3, wave 1: every name in either commons' interface vocabulary has a
    term. The vocabulary is a closed set on both sides — Fashion Cabinet's twelve
    manifest interface types and Yantra4D's fourteen catalog geometry types — so
    coverage of it is checkable rather than aspirational, and `commons-vocabulary`
    entries point at these ids."""
    required = {
        # fashion-cabinet interface types (garment-manifest enum, 12 values)
        "neckline", "armscye", "shoulder-seam", "side-seam", "waistband", "cuff",
        "placket", "hem", "tape-edge", "button-stand", "garment-pocket",
        "custom-interface",
        # yantra4d geometry types (catalog, 14 values)
        "grid", "rail", "thread", "socket", "pocket-recess", "snap", "bolt-pattern",
        "profile", "spline", "surface", "boss", "fem-mesh", "flange",
    }
    assert required <= set(lexicon), sorted(required - set(lexicon))


def test_the_capability_flags_of_the_soft_commons_are_defined(lexicon):
    """Every capability key declared by two or more cartridges has a term, which is what
    makes the capability vocabulary quadrilingual where it is actually used. The
    vocabulary lane asserts the same rule against the live evidence; this asserts the
    terms exist."""
    required = {
        "made-to-measure", "fold-cutting", "fabric-compensation", "hardware-bridge",
        "knit-negative-ease", "printed-textile", "heritage", "elastic-finish",
        "tailoring", "am-fashion", "hook-closure", "e-textile", "closure-free",
        "wire-channel", "pull-on", "compression-support", "stretch-draft",
        "zipper-bridge", "boned", "button-closure", "side-slits", "bound-neckline",
        "adaptive", "panel-width-native", "seam-stabilization", "reversible",
        "double-breasted", "dead-length-solve", "bias-cutting", "shaped-ring",
        "channel-routing", "graduated-compression", "set-in-sleeve", "quick-change",
        "built-in-liner", "separating-zipper",
    }
    assert required <= set(lexicon), sorted(required - set(lexicon))


def test_the_false_friend_pair_is_kept_apart(lexicon):
    """`hook_closure` and `hook_loop_closure` LOOK like a near-duplicate and are not:
    one is hook-and-eye, the other hook-and-loop, and they bridge to different solid
    cartridges. Two entries, each naming the other, is the shape that stops a
    de-duplication pass from merging them."""
    assert "hook-loop-closure" in lexicon["hook-closure"]["see_also"]
    assert "hook-closure" in lexicon["hook-loop-closure"]["see_also"]
    assert lexicon["hook-closure"]["term"]["en"] != lexicon["hook-loop-closure"]["term"]["en"]


def test_the_wave_declares_the_contract_it_was_written_against(lexicon):
    """Contract 2 is additive over 1, so the G1 entries stay at 1. What must hold is the
    other direction: an entry using a contract-2 field declares 2."""
    for term_id, doc in lexicon.items():
        if "review_status" in doc:
            assert doc.get("spec_version") == 2, term_id
        if doc.get("domain") == "capability":
            assert doc.get("spec_version") == 2, term_id


def test_no_entry_claims_a_review_that_did_not_happen(lexicon):
    """RFC 0039 §5: machine or agent drafting is a DRAFT. Every entry that carries the
    block and says `reviewed` names who reviewed it — and a corpus where that is
    vacuously true (nothing reviewed yet) still has to pass, which is why this asserts
    the implication and not a count."""
    for term_id, doc in lexicon.items():
        block = doc.get("review_status")
        if block and block.get("state") == "reviewed":
            assert block.get("reviewers"), f"{term_id} claims review with no reviewer"


def test_the_dialect_split_is_recorded_with_both_repos(lexicon):
    """FC `zipper_tape` and y4d `tape_edge` are ONE term with two recorded dialects.
    A reader arriving with either spelling must land on the same entry, so both are
    recorded with the repo where that spelling is real."""
    aliases = lexicon["tape-edge"]["aliases"]
    by_repo = {a["repo"]: a["name"] for a in aliases}
    assert by_repo["yantra4d"] == "tape_edge"
    assert by_repo["fashion-cabinet"] == "zipper_tape"


def test_heritage_terms_carry_sources(lexicon):
    """RFC 0039 §7: no uncited cultural or historical claim."""
    for term_id, doc in lexicon.items():
        if doc.get("heritage"):
            assert doc.get("sources"), f"{term_id} is heritage-flagged with no sources"


def test_the_motivating_term_carries_its_constraint(lexicon):
    """A term is where a geometry lesson becomes durable instead of living in five
    copied code comments (fashion-cabinet #113). If back-neck-rise ever loses its
    constraint, the lexicon has stopped paying for itself."""
    doc = lexicon["back-neck-rise"]
    assert doc["constraints"]
    assert doc["sources"]


def test_terms_are_addressed_by_filename(lexicon):
    """The corpus is browsable with `ls`, so the filename IS the id."""
    from importlib import resources

    from hyperobjects_lexicon.lexicon import LEXICON_DIR

    names = {
        p.name[: -len(".json")]
        for p in resources.files(LEXICON_DIR).iterdir()
        if p.name.endswith(".json")
    }
    assert names == set(lexicon)


# ------------------------------------------------------------------- failure classes


def test_validator_catches_a_missing_language(a_term):
    del a_term["definition"]["pt"]
    problems = check_term(a_term)
    assert any("definition" in p and "pt" in p for p in problems)


def test_validator_catches_a_blank_language(a_term):
    """The failure the schema cannot see: a key present, holding whitespace. This is
    what a 'placeholder for now' entry actually looks like."""
    a_term["term"]["fr"] = "   "
    problems = check_term(a_term)
    assert any("term.fr" in p for p in problems)


def test_validator_catches_a_dangling_see_also(a_term):
    a_term["see_also"] = ["no-such-term"]
    problems = check_term(a_term, known_ids={"tape-edge"})
    assert any("no-such-term" in p for p in problems)


def test_validator_catches_a_self_reference(a_term):
    a_term["see_also"] = ["tape-edge"]
    problems = check_term(a_term, known_ids={"tape-edge"})
    assert any("itself" in p for p in problems)


def test_validator_catches_an_uncited_heritage_claim(a_term):
    """RFC 0039 §7's citation bar, as a lane rule."""
    a_term["heritage"] = True
    a_term.pop("sources", None)
    problems = check_term(a_term)
    assert any("sources" in p for p in problems)


def test_a_cited_heritage_claim_passes(a_term):
    a_term["heritage"] = True
    a_term["sources"] = ["Some citation a reader can follow, 2026"]
    assert not check_term(a_term)


def test_validator_catches_an_unresolvable_embodied_by(a_term):
    problems = check_term(a_term, catalog={"yantra4d/something-else"})
    assert any("embodied_by" in p for p in problems)


def test_validator_catches_an_id_filename_mismatch(a_term):
    problems = check_term(a_term, filename="not-the-id.json")
    assert any("filename" in p for p in problems)


def test_validator_catches_an_unknown_field(a_term):
    """`additionalProperties: false` — a typo'd field is silently ignored data, which
    is worse than a rejected entry."""
    a_term["definitoin"] = "typo"
    assert check_term(a_term)


def test_validator_catches_a_bad_id_shape(a_term):
    a_term["id"] = "Not Kebab Case"
    assert check_term(a_term)


def test_validator_catches_a_bad_domain(a_term):
    a_term["domain"] = "not-a-real-domain"
    assert check_term(a_term)


def test_validator_catches_a_malformed_slug(a_term):
    """`embodied_by` is '<repo>/<slug>' — a bare slug cannot say which commons."""
    a_term["embodied_by"] = ["zipper"]
    assert check_term(a_term)


def test_duplicate_ids_are_a_corpus_level_failure(a_term):
    """No single term can see this one — two files carrying the same id means the
    second silently wins."""
    other = copy.deepcopy(a_term)
    other["id"] = "tape-edge"
    result = check_lexicon({"tape-edge": a_term, "flange": other})
    assert not result.ok
    assert any("flange" in p for p in result.problems)


def test_validator_catches_a_review_claim_with_no_reviewer(a_term):
    """A review nobody signed is the failure this field exists to prevent."""
    a_term["review_status"] = {"state": "reviewed"}
    problems = check_term(a_term)
    assert any("reviewers" in p for p in problems)


def test_validator_catches_a_reviewed_state_over_a_generated_language(a_term):
    """The state is the WORST facet: an entry cannot read as reviewed while its French
    is still the drafting pass."""
    a_term["review_status"] = {
        "state": "reviewed",
        "reviewers": ["a-native-reader"],
        "languages": {"es": "reviewed", "en": "reviewed", "fr": "generated", "pt": "reviewed"},
    }
    problems = check_term(a_term)
    assert any("fr" in p and "generated" in p for p in problems)


def test_a_signed_full_review_passes(a_term):
    a_term["spec_version"] = 2
    a_term["review_status"] = {
        "state": "reviewed",
        "reviewers": ["a-native-reader"],
        "languages": {"es": "reviewed", "en": "reviewed", "fr": "reviewed", "pt": "reviewed"},
    }
    assert not check_term(a_term)


def test_a_generated_entry_is_shippable(a_term):
    """Quadrilingual completeness is the ship gate; review is tracked, not gated. A
    drafted entry that is complete in four languages passes the lane and says so."""
    a_term["spec_version"] = 2
    a_term["review_status"] = {"state": "generated"}
    assert not check_term(a_term)


def test_validator_catches_an_unknown_review_state(a_term):
    a_term["review_status"] = {"state": "probably-fine"}
    assert check_term(a_term)


# --------------------------------------------------------------- round-trip & status


def test_schema_round_trip(lexicon, tmp_path):
    """Write the corpus out, read it back, and it still conforms — the storage format
    is lossless and the loader agrees with the writer."""
    for term_id, doc in lexicon.items():
        (tmp_path / f"{term_id}.json").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    reloaded = load_lexicon(tmp_path)
    assert reloaded == lexicon
    assert check_lexicon(reloaded, catalog=bundled_catalog_slugs()).ok


def test_term_files_are_utf8_and_ascii_is_not_forced(lexicon):
    """Accented characters ship as characters, not as \\u escapes — the es register is
    the house quality bar and mangling it in storage is not acceptable."""
    assert "ó" in lexicon["back-neck-rise"]["term"]["es"]


def test_status_line_is_the_house_n_over_m_convention(lexicon):
    line = lexicon_status(lexicon)
    assert line.startswith("lexicon_status: ")
    assert f"{len(lexicon)}/{len(lexicon)}" in line


def test_status_line_carries_the_review_debt(lexicon):
    """Four complete languages nobody has read are still four complete languages, so
    N/M cannot show the second debt. The line carries both."""
    line = lexicon_status(lexicon)
    counts = review_counts(lexicon)
    assert f"generated={counts['generated']}" in line
    assert f"reviewed={counts['reviewed']}" in line
    assert f"unmarked={counts['unmarked']}" in line


def test_review_counts_keep_unmarked_apart_from_generated(a_term):
    """The G1 corpus predates the block and claims neither, so counting it as generated
    would put words in its author's mouth."""
    drafted = copy.deepcopy(a_term)
    drafted["id"] = "drafted"
    drafted["review_status"] = {"state": "generated"}
    counts = review_counts({"tape-edge": a_term, "drafted": drafted})
    assert counts == {"reviewed": 0, "generated": 1, "unmarked": 1}


def test_status_counts_entries_not_fragments(a_term):
    """RFC 0039 §7: the N/M tracker counts entries, not fragments. An entry missing one
    language counts as zero, not as three-quarters."""
    incomplete = copy.deepcopy(a_term)
    incomplete["id"] = "half-done"
    incomplete["definition"]["fr"] = ""
    line = lexicon_status({"tape-edge": a_term, "half-done": incomplete})
    assert "1/2" in line


# ------------------------------------------------------------------------- catalogs


def test_bundled_snapshot_covers_both_commons():
    slugs = bundled_catalog_slugs()
    assert any(s.startswith("yantra4d/") for s in slugs)
    assert any(s.startswith("fashion-cabinet/") for s in slugs)


def test_catalog_loader_accepts_the_y4d_catalog_shape(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps(
            {"upstream": {"repo": "madfam-org/yantra4d"}, "cartridges": [{"slug": "zipper"}]}
        ),
        encoding="utf-8",
    )
    assert "yantra4d/zipper" in load_catalog_slugs(p)


def test_catalog_loader_accepts_the_two_sided_snapshot_shape(tmp_path):
    """The vendored snapshot carries provenance metadata alongside the two slug lists;
    the loader must not be confused by the extra keys."""
    p = tmp_path / "s.json"
    p.write_text(
        json.dumps(
            {
                "captured_at": "2026-08-25",
                "sources": {"yantra4d": {"rev": "abc"}},
                "yantra4d": ["zipper"],
                "fashion-cabinet": ["mini-skirt"],
            }
        ),
        encoding="utf-8",
    )
    slugs = load_catalog_slugs(p)
    assert {"yantra4d/zipper", "fashion-cabinet/mini-skirt"} <= slugs


def test_catalog_loader_accepts_an_already_qualified_list(tmp_path):
    p = tmp_path / "q.json"
    p.write_text(json.dumps(["yantra4d/zipper"]), encoding="utf-8")
    assert load_catalog_slugs(p) == {"yantra4d/zipper"}


# ------------------------------------------------------------------------------ CLI


@pytest.mark.parametrize("prog", ["fc-spec", "y4d-spec"])
def test_lexicon_is_exposed_on_both_clis(prog, capsys):
    """The shared vocabulary belongs to neither half of the commons alone, so a
    contributor checks it with whichever tool they already have."""
    main = (
        __import__("fc_spec.cli", fromlist=["main"]).main
        if prog == "fc-spec"
        else __import__("y4d_spec.cli", fromlist=["main"]).main
    )
    assert main(["lexicon", "--catalog", BUNDLED]) == 0
    out = capsys.readouterr().out
    assert f"{prog} lexicon:" in out
    assert "embodied_by=resolved" in out
    assert "lexicon_status:" in out


def test_cli_says_so_when_slugs_were_not_resolved(capsys):
    """Read-proof, the same bar `--render` holds: a run that skipped the catalog check
    must never read like one that passed it."""
    from fc_spec.cli import main

    assert main(["lexicon"]) == 0
    assert "NOT resolved" in capsys.readouterr().out


def test_cli_fails_on_a_broken_corpus(tmp_path, capsys):
    (tmp_path / "broken.json").write_text(
        json.dumps({"id": "broken", "domain": "geometry"}), encoding="utf-8"
    )
    from fc_spec.cli import main

    assert main(["lexicon", "--terms", str(tmp_path)]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_cli_refuses_an_empty_corpus(tmp_path, capsys):
    """An empty corpus passes every check vacuously — a usage error, not a green run."""
    from fc_spec.cli import main

    assert main(["lexicon", "--terms", str(tmp_path)]) == 2
    assert "terms=0" in capsys.readouterr().out


def test_cli_status_flag_prints_only_the_status_line(capsys):
    from y4d_spec.cli import main

    assert main(["lexicon", "--status"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and out[0].startswith("lexicon_status:")
