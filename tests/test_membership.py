"""Tests for vocabulary membership on manifests (SEM-1 §4 rule).

The fixtures in tests/fixtures/sem1/ carry the SEM-1 §2.3/§2.4/§3 shapes. The rule must be
silent on every manifest that predates them — the real fixtures below are that case — and
must name each unknown key in each place it reads.
"""

import json
from pathlib import Path

import pytest

from fc_spec import check as fc_check
from hyperobjects_lexicon import manifest_vocabulary_problems
from hyperobjects_lexicon.membership import RULE_PREFIX
from y4d_spec import rules

FIXTURES = Path(__file__).parent / "fixtures"
SEM1 = FIXTURES / "sem1"


def _load(name: str) -> dict:
    return json.loads((SEM1 / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "path",
    [
        FIXTURES / "y4d" / "thimble" / "project.json",
        FIXTURES / "y4d" / "sew-on-snap" / "project.json",
        FIXTURES / "fc" / "bodice-block.project.json",
        FIXTURES / "fc" / "chainmail-panel.project.json",
    ],
)
def test_a_manifest_without_the_new_fields_passes_silently(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert manifest_vocabulary_problems(doc) == []


@pytest.mark.parametrize(
    "name", ["solid-requirements.project.json", "soft-requirements.project.json"]
)
def test_the_sem1_shapes_resolve(name):
    assert manifest_vocabulary_problems(_load(name)) == []


def test_every_place_the_rule_reads_reports_its_unknown_key():
    probs = manifest_vocabulary_problems(_load("solid-unknown-keys.project.json"))
    assert len(probs) == 6, probs
    assert all(p.startswith(RULE_PREFIX) for p in probs)
    expected = [
        "cdg_interfaces['literal'].size_key: 'nema17-face'",
        "cdg_interfaces['mapped'].size_key.map['2207']: 'motor-mount-16x16'",
        "requirements.process[0]: 'fdm'",
        "requirements.materials.any_of[0]: 'tpu-95'",
        "requirements.process_parameters.wall_count",
        "requirements.parts.damper.materials.none_of[0]: 'nylon'",
    ]
    for needle in expected:
        assert any(needle in p for p in probs), needle


def test_a_near_miss_gets_a_suggestion():
    probs = manifest_vocabulary_problems(_load("solid-unknown-keys.project.json"))
    assert any("did you mean 'nema-17-face'" in p for p in probs)
    assert any("did you mean 'tpu-95a'" in p for p in probs)


def test_an_unreadable_shape_is_reported_never_skipped():
    probs = manifest_vocabulary_problems(_load("malformed-shapes.project.json"))
    assert len(probs) == 6, probs
    for needle in ("size_key: is neither", "empty map", "process: is neither",
                   "materials: is not an object", "process_parameters: is not an object",
                   "parts: is not an object"):
        assert any(needle in p for p in probs), needle


def test_a_bare_string_process_is_accepted():
    assert manifest_vocabulary_problems({"requirements": {"process": "sla"}}) == []
    assert manifest_vocabulary_problems({"requirements": {"process": "resin"}})


def test_custom_vocabularies_can_be_supplied():
    vocab = {"processes": {"entries": [{"key": "weaving"}]}}
    assert manifest_vocabulary_problems(
        {"requirements": {"process": ["weaving"]}}, vocabularies=vocab
    ) == []


def test_non_object_manifest_is_not_this_rules_business():
    assert manifest_vocabulary_problems(["not", "a", "manifest"]) == []


def test_y4d_spec_runs_the_rule_with_its_manifest_rules():
    probs = rules.all_manifest_rules(_load("solid-unknown-keys.project.json"))
    assert sum(1 for p in probs if p.startswith(RULE_PREFIX)) == 6


def test_fc_spec_runs_the_rule_on_a_garment_manifest():
    doc = json.loads((FIXTURES / "fc" / "bodice-block.project.json").read_text(encoding="utf-8"))
    assert fc_check("garment-manifest", doc).ok
    doc["requirements"] = {"materials": {"any_of": ["denim"]}}
    result = fc_check("garment-manifest", doc)
    assert any(p.startswith(RULE_PREFIX) and "'denim'" in p for p in result.problems)
