"""Support pieces of the standard-parts catalog: the frame-expression walker, the
interface-sizes supplement merge, the field-concept lexicon terms and the `vocab` hook."""

from __future__ import annotations

import json

import pytest

from hyperobjects_lexicon.fabrication import (
    load_fabrication_vocabularies,
    load_fabrication_vocabulary,
    vocabulary_keys,
)
from hyperobjects_lexicon.lexicon import LANGUAGES, load_lexicon
from hyperobjects_standard_parts.expressions import (
    ExpressionError,
    evaluate_component,
    expression_names,
)
from y4d_spec.cli import main as y4d_main

# --- the expression walker ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        (5, 5.0),
        (-2.5, -2.5),
        ("length_mm / 2 + offset", 175.0),
        ("-half", -79.5),
        ("(length_mm - 10) * 2", 680.0),
        ("min(length_mm, 100)", 100.0),
        ("max(1, 2, 3)", 3.0),
        ("abs(offset - 10)", 10.0),
    ],
)
def test_the_grammar_evaluates(expr, expected):
    values = {"length_mm": 350.0, "offset": 0.0, "half": 79.5}
    assert evaluate_component(expr, values) == expected


@pytest.mark.parametrize(
    ("expr", "message"),
    [
        ("__import__('os')", "outside the frame grammar"),
        ("length_mm.real", "outside the frame grammar"),
        ("length_mm ** 2", "outside the frame grammar"),
        ("[1][0]", "outside the frame grammar"),
        ("'abc'", "not a numeric literal"),
        ("True", "not a numeric literal"),
        ("abs(1, 2)", "exactly one argument"),
        ("width", "unknown identifier 'width'"),
        ("1 / (length_mm - 350)", "division by zero"),
        ("1 +", "does not parse"),
        ("1" * 300, "longer than 256"),
    ],
)
def test_the_walker_refuses(expr, message):
    with pytest.raises(ExpressionError, match=message):
        evaluate_component(expr, {"length_mm": 350.0})


def test_non_components_are_refused():
    for bad in (True, None, [1]):
        with pytest.raises(ExpressionError):
            evaluate_component(bad, {})


def test_non_finite_is_refused():
    with pytest.raises(ExpressionError, match="non-finite"):
        evaluate_component("1e308 * 10", {})


def test_expression_names():
    assert expression_names("min(a, b) + c / 2") == {"a", "b", "c"}
    assert expression_names(3) == set()
    assert expression_names("1 +") == set()


# --- the interface-sizes supplement -------------------------------------------------------

NEW_SIZE_KEYS = {
    "tslot-2020-end-tap-m5",
    "mgn12-rail",
    "bearing-608-bore",
    "prop-shaft-m5",
    "battery-strap-20mm",
    "meanwell-lrs-200-base-m4",
    "meanwell-lrs-200-side-m4",
    "omron-d2f-mount-m2",
}


def test_bundled_interface_sizes_merge_the_supplement():
    keys = vocabulary_keys("interface-sizes", load_fabrication_vocabularies())
    assert NEW_SIZE_KEYS <= keys
    assert {"nema-17-face", "stack-30.5x30.5-m3"} <= keys  # the base file is still there
    doc = load_fabrication_vocabulary("interface-sizes")
    assert doc["vocabulary"] == "interface-sizes"
    assert "P3-LEX" in doc["review"]["note"]  # the base document's head is kept


def test_new_size_keys_are_drafts_with_cited_facts():
    doc = load_fabrication_vocabulary("interface-sizes")
    entries = {e["key"]: e for e in doc["entries"] if e["key"] in NEW_SIZE_KEYS}
    assert set(entries) == NEW_SIZE_KEYS
    for key, entry in entries.items():
        assert entry["review_status"]["state"] == "generated", key
        assert all(entry["label"][lang].strip() for lang in LANGUAGES), key
        assert all(0 <= d["source"] < len(entry["sources"]) for d in entry["dimensions"].values())


def test_directory_supplements_merge(tmp_path):
    base = load_fabrication_vocabulary("processes")
    first, rest = base["entries"][:3], base["entries"][3:]
    (tmp_path / "processes.json").write_text(json.dumps({**base, "entries": first}))
    (tmp_path / "processes.extra.json").write_text(json.dumps({**base, "entries": rest}))
    docs = load_fabrication_vocabularies(tmp_path)
    assert list(docs) == ["processes"]
    assert [e["key"] for e in docs["processes"]["entries"]] == [e["key"] for e in base["entries"]]


def test_a_supplement_of_another_vocabulary_is_an_error(tmp_path):
    base = load_fabrication_vocabulary("processes")
    (tmp_path / "processes.json").write_text(json.dumps(base))
    (tmp_path / "processes.extra.json").write_text(
        json.dumps({**base, "vocabulary": "material-classes"})
    )
    with pytest.raises(ValueError, match="declares vocabulary 'material-classes'"):
        load_fabrication_vocabularies(tmp_path)


# --- the field-concept terms --------------------------------------------------------------

NEW_TERMS = {
    "interface-polarity": "cdg-interface",
    "interface-size-key": "cdg-interface",
    "interface-frame": "cdg-interface",
    "interface-symmetry": "cdg-interface",
    "parameter-unit": "manifest",
    "assembly": "manifest",
    "mate": "cdg-interface",
    "assembly-placement": "geometry",
    "standard-part": "cdg-interface",
    "external-design-reference": "licensing",
}


def test_field_concept_terms_exist_as_quadrilingual_drafts():
    lexicon = load_lexicon()
    for tid, domain in NEW_TERMS.items():
        term = lexicon[tid]
        assert term["domain"] == domain, tid
        assert term["review_status"]["state"] == "generated", tid
        assert all(term["term"][lang].strip() for lang in LANGUAGES), tid
        assert all(term["definition"][lang].strip() for lang in LANGUAGES), tid


# --- the `vocab` hook ---------------------------------------------------------------------


def test_vocab_reports_the_catalog(capsys):
    assert y4d_main(["vocab"]) == 0
    out = capsys.readouterr().out
    assert "y4d-spec vocab standard-parts: parts=14 interfaces=37 failures=0" in out
    assert "standard_parts_status: parts=14" in out


def test_vocab_fails_on_a_broken_catalog(tmp_path, capsys):
    from hyperobjects_standard_parts import load_part

    part = load_part("prop-5in")
    part["interfaces"][0]["size_key"] = "prop-shaft-m6"
    (tmp_path / "prop-5in.json").write_text(json.dumps(part))
    assert y4d_main(["vocab", "--standard-parts", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "FAIL standard-parts: prop-5in:" in out
    assert "vocab standard-parts: parts=1 interfaces=1 failures=1" in out
