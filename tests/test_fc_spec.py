"""Tests for the fc-spec conformance runner.

Ported from fashion-cabinet/packages/spec/tests/test_conformance.py. The rule and
contract assertions are unchanged; what changed is where the documents come from.

In the FC repo those tests read the live repo (REPO/projects/bodice-block/project.json
and friends) and asserted the bundled schemas matched packages/schemas/ byte-for-byte.
Neither travels: this package has no FC repo to read. So the real documents are copied
into tests/fixtures/fc/ and the drift guard is re-pointed at the copy this package
itself bundles twice (fc_spec/schemas vs hyperobjects_schemas/schemas) — which is the
drift that can actually happen HERE.

The FC-side drift guard (bundled vs packages/schemas) and the lane-sharing guard
(verify_hardware_links.py imports fc_spec.rules) stay in the FC repo, where the files
they guard live. See docs/P1B_ADOPTION.md.
"""

import json
from pathlib import Path

import pytest

import fc_spec
import hyperobjects_schemas
from fc_spec import conformance, rules

FIXTURES = Path(__file__).parent / "fixtures" / "fc"
BUNDLED_SCHEMAS = Path(fc_spec.__file__).parent / "schemas"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ── contract surface ─────────────────────────────────────────────────────────
def test_lists_the_five_contracts():
    assert set(fc_spec.list_contracts()) == {
        "garment-manifest",
        "fabric-card",
        "body-measurements",
        "hardware-ref",
        "explode-json",
    }


def test_unknown_contract_raises():
    with pytest.raises(ValueError):
        conformance.check("no-such-contract", {})


# ── drift guard (the one that is real inside THIS package) ────────────────────
@pytest.mark.parametrize(
    "name",
    [
        "garment-manifest.schema.json",
        "fabric-manifest.schema.json",
        "body-measurements.schema.json",
    ],
)
def test_fc_bundled_schema_matches_the_consolidated_copy(name):
    """fc_spec keeps its own bundled schemas for compat; hyperobjects_schemas holds
    the consolidated copy. If those two drift, a caller gets a different answer
    depending on which one they loaded."""
    bundled = json.loads((BUNDLED_SCHEMAS / name).read_text(encoding="utf-8"))
    consolidated = hyperobjects_schemas.load(name)
    assert bundled == consolidated, (
        f"{name}: fc_spec's bundled copy has drifted from hyperobjects_schemas — "
        f"re-sync them, they are meant to be the same contract"
    )


# ── garment manifest ─────────────────────────────────────────────────────────
def test_real_garment_manifest_passes():
    assert conformance.check("garment-manifest", _fixture("bodice-block.project.json")).ok


def test_garment_manifest_bad_piece_ref_fails():
    doc = {
        "project": {
            "name": "X",
            "slug": "x",
            "version": "0.1.0",
            "attribution": {"license": "LicenseRef-FC1-pending", "lineage": []},
        },
        "modes": [
            {"id": "m", "label": {"en": "M"}, "script_file": "main.py", "pieces": ["ghost"]}
        ],
        "pieces": [{"id": "real", "label": {"en": "Real"}}],
        "parameters": [{"id": "p", "type": "slider", "label": {"en": "P"}}],
        "hyperobject": {"is_hyperobject": True, "domain": "garment"},
    }
    result = conformance.check("garment-manifest", doc)
    assert not result.ok
    assert any("unknown piece 'ghost'" in p for p in result.problems)


# ── body measurements ────────────────────────────────────────────────────────
def test_real_body_passes():
    assert conformance.check("body-measurements", _fixture("straight-w-m.body.json")).ok


def test_body_bogus_landmark_fails():
    doc = {
        "body": {"slug": "x", "name": {"en": "X"}, "kind": "person"},
        "landmarks": {"bogus_girth": 900},
    }
    result = conformance.check("body-measurements", doc)
    assert not result.ok
    assert any("bogus_girth" in p for p in result.problems)


# ── hardware ref ─────────────────────────────────────────────────────────────
def _snapshot() -> dict:
    return _fixture("yantra4d-hardware.snapshot.json")["cartridges"]


def test_hardware_ref_resolves_against_snapshot_dict():
    doc = _fixture("shank-button.project.json")
    resolve = {k: v["parameter_ids"] for k, v in _snapshot().items()}
    assert conformance.check("hardware-ref", doc, resolve=resolve).ok


def test_hardware_ref_unresolvable_without_catalog():
    doc = _fixture("shank-button.project.json")
    result = conformance.check("hardware-ref", doc, resolve={})
    assert not result.ok
    assert any("does not resolve" in p for p in result.problems)


def test_hardware_ref_allows_safe_numeric_builtins_in_value():
    # A dimension→count mapping legitimately rounds (e.g. ring columns from panel
    # width). `round` is a call target from the safe whitelist, not a parameter.
    doc = {
        "parameters": [{"id": "panel_width_mm"}, {"id": "ring_id"}, {"id": "wire_d"}],
        "notion": {
            "kind": "custom",
            "hardware_ref": {
                "platform": "yantra4d",
                "project_slug": "panel",
                "linked": True,
                "params_map": {"cols": "round(panel_width_mm / (ring_id + wire_d))"},
            },
        },
    }
    assert rules.hardware_ref_rules(doc, {"panel": ["cols"]}) == []


def test_hardware_ref_safe_builtin_does_not_mask_bad_operand():
    doc = {
        "parameters": [{"id": "panel_width_mm"}],
        "notion": {
            "kind": "custom",
            "hardware_ref": {
                "platform": "yantra4d",
                "project_slug": "panel",
                "linked": True,
                "params_map": {"cols": "round(panel_width_mm / not_a_param)"},
            },
        },
    }
    problems = rules.hardware_ref_rules(doc, {"panel": ["cols"]})
    assert any("not_a_param" in p for p in problems)


def test_hardware_ref_bad_params_map_key():
    doc = {
        "parameters": [{"id": "opening_len", "type": "slider", "label": {"en": "L"}}],
        "notion": {
            "kind": "zipper",
            "hardware_ref": {
                "platform": "yantra4d",
                "project_slug": "zipper",
                "linked": True,
                "params_map": {"not_a_param": "opening_len"},
            },
        },
    }
    result = conformance.check("hardware-ref", doc, resolve={"zipper": ["zip_length"]})
    assert any("params_map key 'not_a_param'" in p for p in result.problems)


# ── the dimensional handshake ────────────────────────────────────────────────
_ZIPPER_FULL = {
    "zipper": {
        "parameter_ids": ["zip_length", "tape_width"],
        "cdg_interfaces": [
            {"id": "tape_edge", "geometry_type": "flange", "parameters": ["zip_length"]},
            {"id": "slider_channel", "geometry_type": "socket", "parameters": ["gap"]},
        ],
    }
}


def _zipper_garment(zip_value_param, garment_iface_params):
    return {
        "parameters": [{"id": zip_value_param}],
        "hyperobject": {
            "interfaces": [
                {"id": "cf_zipper", "type": "zipper_tape", "parameters": garment_iface_params}
            ]
        },
        "notion": {
            "kind": "zipper",
            "hardware_ref": {
                "platform": "yantra4d",
                "project_slug": "zipper",
                "linked": True,
                "params_map": {"zip_length": zip_value_param},
            },
        },
    }


def test_dimensional_handshake_passes_when_coupled():
    doc = _zipper_garment("front_len", ["front_len"])
    assert rules.hardware_dimensional_rules(doc, _ZIPPER_FULL) == []


def test_dimensional_handshake_flags_decoupled():
    doc = _zipper_garment("random_param", ["chest_girth"])
    problems = rules.hardware_dimensional_rules(doc, _ZIPPER_FULL)
    assert problems and "dimensional handshake" in problems[0]


def test_dimensional_handshake_ignores_garment_without_interfaces():
    doc = _zipper_garment("random_param", [])
    doc["hyperobject"]["interfaces"] = []
    assert rules.hardware_dimensional_rules(doc, _ZIPPER_FULL) == []


def test_dimensional_handshake_ignores_numeric_literal_mapping():
    doc = {
        "parameters": [{"id": "x"}],
        "hyperobject": {"interfaces": [{"id": "i", "parameters": ["x"]}]},
        "notion": {
            "kind": "hook",
            "hardware_ref": {
                "platform": "yantra4d",
                "project_slug": "hook-and-eye",
                "linked": True,
                "params_map": {"size_mm": "7"},
            },
        },
    }
    full = {
        "hook-and-eye": {
            "parameter_ids": ["size_mm"],
            "cdg_interfaces": [
                {"id": "sew_plate", "geometry_type": "flange", "parameters": ["size_mm"]}
            ],
        }
    }
    assert rules.hardware_dimensional_rules(doc, full) == []


def test_dimensional_handshake_on_the_real_linked_fixtures():
    """Every real linked notion in the fixtures must be dimensionally coupled — the
    0-false-positive guard the FC lane runs, on the cartridges we carry."""
    resolve_full = _snapshot()
    checked = 0
    for path in sorted(FIXTURES.glob("*.project.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        hw = (doc.get("notion") or {}).get("hardware_ref") or {}
        if isinstance(hw, dict) and hw.get("linked"):
            assert rules.hardware_dimensional_rules(doc, resolve_full) == [], path.name
            checked += 1
    assert checked >= 2, "fixtures should carry at least two real linked notions"


# ── explode json ─────────────────────────────────────────────────────────────
def test_explode_json_ok_payload():
    doc = {
        "name": "x",
        "units": "mm",
        "pieces": [{"name": "a", "edges": {"e": 10.0}}],
        "seams": [{"a": "a.e", "b": "a.e", "ok": True}],
        "issues": [],
    }
    assert conformance.check("explode-json", doc).ok


def test_explode_json_failed_seam():
    doc = {
        "name": "x",
        "units": "mm",
        "pieces": [{"name": "a"}],
        "seams": [
            {
                "a": "a.l",
                "b": "a.r",
                "ok": False,
                "length_a_mm": 100,
                "length_b_mm": 120,
                "tol_mm": 2,
            }
        ],
    }
    result = conformance.check("explode-json", doc)
    assert not result.ok
    assert any("is not ok" in p for p in result.problems)


def test_explode_json_wrong_units():
    result = conformance.check("explode-json", {"name": "x", "units": "in", "pieces": [{}]})
    assert any("units must be 'mm'" in p for p in result.problems)


# ── fabric card ──────────────────────────────────────────────────────────────
def test_real_fabric_card_passes():
    assert conformance.check("fabric-card", _fixture("manta-cruda.material.json")).ok


def test_fabric_card_non_boolean_etextile_flag():
    doc = _fixture("manta-cruda.material.json")
    doc.setdefault("e_textile", {})["conductive_thread_compatible"] = "yes"
    result = conformance.check("fabric-card", doc)
    assert any("must be a boolean" in p for p in result.problems)


# ── result object ────────────────────────────────────────────────────────────
def test_result_is_falsey_on_problems():
    r = conformance.ConformanceResult(contract="x", ok=False, problems=["p"])
    assert not r
    assert bool(conformance.ConformanceResult(contract="x", ok=True)) is True


def test_rules_canonical_codes_reads_schema():
    codes = rules.canonical_landmark_codes(hyperobjects_schemas.load("body-measurements"))
    assert "waist_girth" in codes and "chest_bust_girth" in codes


# ── the CLI contract (must keep working verbatim for downstream) ──────────────
def test_cli_check_contract_is_unchanged(capsys):
    """`fc-spec check <contract> <file>` is a published contract — downstream CI
    invokes it by that exact shape. Exit 0 on a conformant file."""
    from fc_spec.cli import main

    rc = main(["check", "garment-manifest", str(FIXTURES / "bodice-block.project.json")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ok" in out
    assert "files=1 failures=0" in out


def test_cli_check_reports_failures_with_exit_1(capsys, tmp_path):
    from fc_spec.cli import main

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"name": "x", "units": "in", "pieces": []}))
    rc = main(["check", "explode-json", str(bad)])
    assert rc == 1
    assert "FAIL" in capsys.readouterr().out


def test_cli_list_prints_every_contract(capsys):
    from fc_spec.cli import main

    assert main(["list"]) == 0
    printed = capsys.readouterr().out.split()
    assert set(printed) == set(fc_spec.list_contracts())
