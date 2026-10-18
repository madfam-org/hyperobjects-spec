"""body-count (NOTE ONLY): rendered connected bodies against the declared count.

The keystone counted bodies on every render and never compared the count with
`verification.stages.geometry.checks.body_count` or its mode/part overrides, so a
cartridge declaring one body could render two (solid-hyperobjects voronoi's vase, 2 at
defaults and 26/46 at presets) and stay `ok` with nothing said.
"""

import json
import shutil
from pathlib import Path

import pytest

from y4d_spec import conformance
from y4d_spec.body_count import (
    RULE_ID,
    BodyCountError,
    body_count_notes,
    declared_body_count,
    evaluate_count,
)
from y4d_spec.geometry import RenderCheck

FIXTURES = Path(__file__).parent / "fixtures" / "y4d"


def _manifest(**verification):
    return {
        "parameters": [
            {"id": "n", "type": "slider", "default": 2},
            {"id": "joint_type", "type": "select", "default": "plain"},
        ],
        "modes": [
            {"id": "single", "parts": ["body"]},
            {"id": "set", "parts": ["body", "pin"], "part_quantities": {"pin": 4}},
        ],
        "presets": [{"id": "three", "mode": "single", "values": {"n": 3}}],
        "verification": verification
        or {"stages": {"geometry": {"checks": {"body_count": {"enabled": True, "expected": 1}}}}},
    }


BASE_1 = {"stages": {"geometry": {"checks": {"body_count": {"enabled": True, "expected": 1}}}}}


# --- resolving the declaration (no CAD kernel) -------------------------------------------


def test_base_declaration_applies_to_every_target():
    doc = _manifest()
    decl = declared_body_count(doc, "single", "body")
    assert decl.expected == 1
    assert decl.source == "verification.stages.geometry.checks.body_count"
    assert decl.quantity is None
    assert declared_body_count(doc, "set", "pin").quantity == 4


def test_part_override_beats_mode_override_beats_base():
    doc = _manifest(
        **BASE_1,
        mode_overrides={
            "set": {
                "overrides": {"geometry.body_count": {"expected": 2}},
                "part_overrides": {"pin": {"geometry.body_count": {"expected": 3}}},
            }
        },
    )
    assert declared_body_count(doc, "single", "body").expected == 1
    body = declared_body_count(doc, "set", "body")
    assert body.expected == 2 and body.source.endswith(".set.overrides['geometry.body_count']")
    pin = declared_body_count(doc, "set", "pin")
    assert pin.expected == 3 and ".part_overrides.pin[" in pin.source


def test_override_replaces_the_base_whole():
    # An override without `expected` does not inherit the base's: it is the default, 1.
    doc = _manifest(
        stages={"geometry": {"checks": {"body_count": {"expected": 5}}}},
        mode_overrides={"set": {"part_overrides": {"pin": {"geometry.body_count": {}}}}},
    )
    assert declared_body_count(doc, "set", "pin").expected == 1
    assert declared_body_count(doc, "set", "body").expected == 5


def test_bare_count_shorthand_is_the_expected_count():
    doc = _manifest(
        **BASE_1, mode_overrides={"set": {"part_overrides": {"pin": {"geometry.body_count": 2}}}}
    )
    assert declared_body_count(doc, "set", "pin").expected == 2


def test_disabled_undeclared_and_geometry_free_modes_are_not_judged():
    assert declared_body_count({"modes": []}, "single", "body") is None
    disabled = _manifest(stages={"geometry": {"checks": {"body_count": {"enabled": False}}}})
    assert declared_body_count(disabled, "single", "body") is None
    no_geometry = _manifest(**BASE_1, mode_overrides={"single": {"stages": ["printability"]}})
    assert declared_body_count(no_geometry, "single", "body") is None
    assert declared_body_count(no_geometry, "set", "body") is not None


def test_count_expressions_from_the_commons_evaluate():
    params = {"N": 3, "joint_type": "locking", "hinge_knuckle_count": 5}
    assert evaluate_count(2, params) == 2
    assert evaluate_count(2.0, params) == 2
    assert evaluate_count("12", params) == 12
    assert evaluate_count("hinge_knuckle_count", params) == 5
    assert evaluate_count('3 if joint_type == "locking" else 2', params) == 3
    assert evaluate_count("N * N * N - (N - 2) * (N - 2) * (N - 2)", params) == 26
    assert evaluate_count("6 * N * N", params) == 54
    # sentinel-gripper: `finger_count` is a select valued "3", so this is 6, not "33".
    assert evaluate_count("finger_count * 2", {"finger_count": "3"}) == 6


@pytest.mark.parametrize(
    "value",
    ["missing_param", "N / 2", "N - 9", "__import__('os')", "len(N)", "N +", True, None, "x.y"],
)
def test_unevaluable_counts_raise(value):
    with pytest.raises(BodyCountError):
        evaluate_count(value, {"N": 3})


# --- the note, on RenderChecks (no CAD kernel) --------------------------------------------


def _render(mode, part, bodies, *, preset=None, ok=True, skipped=None, engine="cadquery"):
    return RenderCheck(
        mode=mode, part=part, ok=ok, bodies=bodies, volume=1.0, watertight=True,
        preset=preset, engine=engine, skipped=skipped,
    )


def test_note_names_rule_target_declared_observed_and_source():
    notes = body_count_notes(_manifest(), [_render("single", "body", 2)])
    assert len(notes) == 1
    note = notes[0]
    assert note.startswith(
        f"{RULE_ID}: (single, body, cadquery): renders 2 body/bodies, declares 1"
    )
    assert "verification.stages.geometry.checks.body_count" in note


def test_preset_point_is_used_for_an_expression_and_named_in_the_note():
    doc = _manifest(stages={"geometry": {"checks": {"body_count": {"expected": "n"}}}})
    assert body_count_notes(doc, [_render("single", "body", 2)]) == []  # default n=2
    assert body_count_notes(doc, [_render("single", "body", 3, preset="three")]) == []
    notes = body_count_notes(doc, [_render("single", "body", 2, preset="three")])
    assert len(notes) == 1 and "preset 'three'" in notes[0] and "declares 3" in notes[0]


def test_failed_skipped_and_unmeasured_renders_are_not_judged():
    renders = [
        _render("single", "body", 2, ok=False),
        _render("single", "body", None, skipped="no OpenSCAD binary", engine="openscad"),
        _render("single", "body", None),
    ]
    assert body_count_notes(_manifest(), renders) == []


def test_unevaluable_declaration_is_its_own_note_and_not_compared():
    doc = _manifest(stages={"geometry": {"checks": {"body_count": {"expected": "nope + 1"}}}})
    notes = body_count_notes(doc, [_render("single", "body", 1)])
    assert len(notes) == 1
    assert "cannot be evaluated" in notes[0] and "not compared" in notes[0]


# --- synthetic meshes through THE mesh bar -----------------------------------------------


def _judged(tmp_path, n_bodies, mode="single", part="body"):
    """A real STL of `n_bodies` disjoint boxes, judged by geometry._judge_stl."""
    trimesh = pytest.importorskip("trimesh")
    from y4d_spec.geometry import _judge_stl

    boxes = []
    for i in range(n_bodies):
        box = trimesh.creation.box((10, 10, 10))
        box.apply_translation((30 * i, 0, 0))
        boxes.append(box)
    path = tmp_path / f"{mode}-{part}-{n_bodies}.stl"
    trimesh.util.concatenate(boxes).export(path)
    check = _judge_stl(str(path), mode=mode, part=part, preset=None, printability=False,
                       engine="cadquery")
    assert check.ok and check.bodies == n_bodies
    return check


@pytest.mark.geometry
def test_mesh_one_body_declared_one_is_silent(tmp_path):
    assert body_count_notes(_manifest(), [_judged(tmp_path, 1)]) == []


@pytest.mark.geometry
def test_mesh_two_bodies_declared_one_is_noted(tmp_path):
    notes = body_count_notes(_manifest(), [_judged(tmp_path, 2)])
    assert len(notes) == 1 and "renders 2 body/bodies, declares 1" in notes[0]


@pytest.mark.geometry
def test_mesh_declared_two_with_quantities_is_silent(tmp_path):
    doc = _manifest(
        **BASE_1,
        mode_overrides={
            "set": {"part_overrides": {"pin": {"geometry.body_count": {"expected": 2}}}}
        },
    )
    # pin: declared 2, part_quantities 4 — two bodies per copy, one copy rendered.
    assert body_count_notes(doc, [_judged(tmp_path, 2, "set", "pin")]) == []


@pytest.mark.geometry
def test_mesh_quantity_accepts_one_copy_or_all_copies(tmp_path):
    doc = _manifest()  # pin: declared 1 (base), part_quantities 4
    assert body_count_notes(doc, [_judged(tmp_path, 1, "set", "pin")]) == []
    assert body_count_notes(doc, [_judged(tmp_path, 4, "set", "pin")]) == []
    notes = body_count_notes(doc, [_judged(tmp_path, 3, "set", "pin")])
    assert len(notes) == 1
    assert "renders 3 body/bodies, declares 1 or 4 (× part_quantities 4" in notes[0]


# --- wiring: a note in check_cartridge, never a failure ----------------------------------


def test_check_cartridge_reports_the_note_and_stays_ok(tmp_path, monkeypatch):
    cartridge = tmp_path / "thimble"
    shutil.copytree(FIXTURES / "thimble", cartridge)
    doc = json.loads((cartridge / "project.json").read_text())
    doc["verification"] = BASE_1
    (cartridge / "project.json").write_text(json.dumps(doc))

    import y4d_spec.frame_gate as frame_gate
    import y4d_spec.geometry as geometry

    monkeypatch.setattr(
        geometry, "check_geometry",
        lambda *a, **k: [_render("thimble", "thimble", 2), _render("set", "set", 1)],
    )
    monkeypatch.setattr(frame_gate, "check_frames", lambda *a, **k: [])

    result = conformance.check_cartridge(cartridge, render=True, printability=False)
    body_notes = [n for n in result.notes if n.startswith(f"{RULE_ID}:")]
    assert body_notes == [
        f"{RULE_ID}: (thimble, thimble, cadquery): renders 2 body/bodies, declares 1 "
        "(verification.stages.geometry.checks.body_count) — either the declaration or the "
        "geometry is wrong; a note until the whole-commons pass, then a failure"
    ]
    assert result.ok and result.problems == []
