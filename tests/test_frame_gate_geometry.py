"""The render-time frame gate against real renders (ASM-1 §8). Needs the [geometry] extra.

Fixtures: `frame-plate` (every frame right) and `frame-plate-wrong` (an origin 1 mm off
its face, a bore normal flipped). The plate is 30 × 30 mm on z = 0..plate_thick with a
16 × 16 M3 pattern and a centre bore; the pin is a Ø20 × 3 flange with a shaft on it.
"""

import copy
import json
import math
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.geometry

FIXTURES = Path(__file__).parent / "fixtures" / "y4d"
FRAME_PLATE = FIXTURES / "frame-plate"
FRAME_PLATE_WRONG = FIXTURES / "frame-plate-wrong"
T = 4.0  # plate_thick default
BORE_R = 4.0  # bore_d default / 2


def _frame(origin, normal, x_axis=None, part="plate"):
    from y4d_spec.frame_eval import Frame

    length = math.sqrt(sum(c * c for c in normal))
    return Frame(part=part, origin=tuple(float(c) for c in origin),
                 normal=tuple(c / length for c in normal), x_axis=x_axis)


def _tilted(deg):
    return (math.sin(math.radians(deg)), 0.0, math.cos(math.radians(deg)))


@pytest.fixture(scope="module")
def meshes(tmp_path_factory):
    """The plate and the pin at their defaults, rendered once through render_part."""
    import trimesh

    from y4d_spec.geometry import render_part

    out = {}
    for part in ("plate", "pin"):
        stl_dir = tmp_path_factory.mktemp(part)
        check = render_part(FRAME_PLATE, "main.py", part, part, stl_dir=stl_dir)
        assert check.ok, check.problems
        out[part] = trimesh.load(check.stl_path, force="mesh")
    return out


# ── planar ────────────────────────────────────────────────────────────────────
def test_planar_top_face_passes(meshes):
    from y4d_spec.frame_geometry import planar_check

    v = planar_check(meshes["plate"], _frame((0, 0, T), (0, 0, 1)))
    assert v.status == "pass", v.message
    assert v.residuals["area_mm2"] > 500
    assert v.residuals["plane_offset_mm"] <= 1e-6
    assert v.residuals["normal_deg"] <= 1e-6


@pytest.mark.parametrize("dz, status", [(0.05, "pass"), (-0.09, "pass"), (0.2, "fail"),
                                        (1.0, "fail"), (-1.0, "fail")])
def test_planar_offset_along_normal(meshes, dz, status):
    from y4d_spec.frame_geometry import planar_check

    v = planar_check(meshes["plate"], _frame((0, 0, T + dz), (0, 0, 1)))
    assert v.status == status, v.message
    if status == "fail":
        assert v.residuals["plane_offset_mm"] == pytest.approx(-dz, abs=1e-6)
        assert "from the origin along its normal" in v.message


def test_planar_flipped_normal_fails(meshes):
    from y4d_spec.frame_geometry import planar_check

    v = planar_check(meshes["plate"], _frame((0, 0, T), (0, 0, -1)))
    assert v.status == "fail"
    assert v.residuals["normal_deg"] == pytest.approx(180.0)
    assert "off the normal" in v.message


@pytest.mark.parametrize("deg, status", [(1.0, "pass"), (1.9, "pass"), (3.0, "fail")])
def test_planar_normal_tolerance(meshes, deg, status):
    from y4d_spec.frame_geometry import planar_check

    v = planar_check(meshes["plate"], _frame((0, 0, T), _tilted(deg)))
    assert v.status == status, v.message


def test_planar_origin_off_the_part_fails(meshes):
    from y4d_spec.frame_geometry import planar_check

    v = planar_check(meshes["plate"], _frame((100, 0, T), (0, 0, 1)))
    assert v.status == "fail"
    assert v.residuals["area_mm2"] == 0.0


def test_planar_cannot_see_a_slide_along_its_own_face(meshes):
    """The documented limit: an origin moved WITHIN its face plane by less than the
    search radius still finds the face. Axis checks and assembly closure constrain
    in-plane position; a plane cannot."""
    from y4d_spec.frame_geometry import planar_check

    assert planar_check(meshes["plate"], _frame((5, 3, T), (0, 0, 1))).status == "pass"


def test_planar_underside(meshes):
    from y4d_spec.frame_geometry import planar_check

    assert planar_check(meshes["plate"], _frame((0, 0, 0), (0, 0, -1))).status == "pass"
    assert planar_check(meshes["plate"], _frame((0, 0, 0), (0, 0, 1))).status == "fail"


# ── axis ──────────────────────────────────────────────────────────────────────
def test_axis_bore_passes(meshes):
    from y4d_spec.frame_geometry import axis_check

    v = axis_check(meshes["plate"], _frame((0, 0, T), (0, 0, 1)), "female")
    assert v.status == "pass", v.message
    assert v.residuals["kind"] == "bore"
    assert v.residuals["radius_mm"] == pytest.approx(BORE_R, abs=1e-3)
    assert v.residuals["axis_offset_mm"] <= 1e-3
    assert v.residuals["coverage_deg"] == 360.0


def test_axis_bore_entered_from_the_other_side_passes(meshes):
    from y4d_spec.frame_geometry import axis_check

    v = axis_check(meshes["plate"], _frame((0, 0, 0), (0, 0, -1)), "female")
    assert v.status == "pass", v.message


@pytest.mark.parametrize("dx, status", [(0.05, "pass"), (0.5, "fail"), (2.0, "fail")])
def test_axis_lateral_offset(meshes, dx, status):
    from y4d_spec.frame_geometry import axis_check

    v = axis_check(meshes["plate"], _frame((dx, 0, T), (0, 0, 1)), "female")
    assert v.status == status, v.message
    assert v.residuals["axis_offset_mm"] == pytest.approx(dx, abs=1e-3)


def test_axis_flipped_bore_fails(meshes):
    from y4d_spec.frame_geometry import axis_check

    v = axis_check(meshes["plate"], _frame((0, 0, T), (0, 0, -1)), "female")
    assert v.status == "fail"
    assert "normal points the wrong way" in v.message


def test_axis_origin_off_the_bore_end_fails(meshes):
    from y4d_spec.frame_geometry import axis_check

    v = axis_check(meshes["plate"], _frame((0, 0, T + 1), (0, 0, 1)), "female")
    assert v.status == "fail"
    assert v.residuals["axial_gap_mm"] == pytest.approx(1.0, abs=1e-6)


def test_axis_polarity_must_match(meshes):
    from y4d_spec.frame_geometry import axis_check

    v = axis_check(meshes["plate"], _frame((0, 0, T), (0, 0, 1)), "male")
    assert v.status == "fail"
    assert "polarity is male but the cylinder at the origin is a bore" in v.message


def test_axis_shaft_passes_and_innermost_cylinder_is_judged(meshes):
    from y4d_spec.frame_geometry import axis_check

    v = axis_check(meshes["pin"], _frame((0, 0, 3), (0, 0, 1), part="pin"), "male")
    assert v.status == "pass", v.message
    assert v.residuals["kind"] == "shaft"
    assert v.residuals["radius_mm"] == pytest.approx(2.5, abs=1e-3)
    # Flipped: the flange's rim (r 10) WOULD read as a shaft pointing down from z = 3;
    # the innermost cylinder at the origin plane is the pin, and it points up.
    flipped = axis_check(meshes["pin"], _frame((0, 0, 3), (0, 0, -1), part="pin"), "male")
    assert flipped.status == "fail"
    assert flipped.residuals["radius_mm"] == pytest.approx(2.5, abs=1e-3)
    wrong = axis_check(meshes["pin"], _frame((0, 0, 3), (0, 0, 1), part="pin"), "female")
    assert wrong.status == "fail"


def test_axis_tilted_normal_falls_back_to_the_face_and_fails(meshes):
    from y4d_spec.frame_geometry import axis_check, verify_frame_on_mesh

    frame = _frame((0, 0, T), _tilted(3.0))
    assert axis_check(meshes["plate"], frame, "female") is None
    v = verify_frame_on_mesh(meshes["plate"], frame,
                             {"geometry_type": "socket", "polarity": "female"})
    assert v.status == "fail"
    assert v.rule == "planar (no cylinder at the origin)"


def test_axis_type_without_a_cylinder_uses_the_face(meshes):
    """A hex or square socket is still a socket: with no cylinder around the origin
    the entrance face is what is checked, and the verdict names that rule."""
    from y4d_spec.frame_geometry import verify_frame_on_mesh

    v = verify_frame_on_mesh(meshes["plate"], _frame((0, 12, T), (0, 0, 1)),
                             {"geometry_type": "socket", "polarity": "female"})
    assert v.status == "pass", v.message
    assert v.rule == "planar (no cylinder at the origin)"


def test_unsupported_type_is_unverified(meshes):
    from y4d_spec.frame_geometry import verify_frame_on_mesh

    for gtype in ("snap", "custom", None):
        v = verify_frame_on_mesh(meshes["plate"], _frame((0, 0, T), (0, 0, 1)),
                                 {"geometry_type": gtype})
        assert v.status == "unverified"
        assert "NOT verified" in v.message


# ── the gate end to end ───────────────────────────────────────────────────────
def test_correct_fixture_passes_the_render_check():
    from y4d_spec import check_cartridge

    result = check_cartridge(FRAME_PLATE, render=True, printability=False)
    assert result.ok, result.problems
    by_status = {}
    for fc in result.frames:
        by_status.setdefault(fc.status, []).append((fc.interface, fc.point))
    # 5 framed interfaces × 3 points (defaults + 2 presets).
    assert len(result.frames) == 15
    assert len(by_status["pass"]) == 12
    assert sorted({i for i, _ in by_status["unverified"]}) == ["edge_clip"]
    assert "fail" not in by_status
    # Unverified is a NOTE, never silent and never a pass.
    assert sum("UNVERIFIED" in n for n in result.notes) == 3
    # The frame follows the preset: the 'thick' preset moves the face to z = 6.
    thick = next(f for f in result.frames
                 if f.interface == "motor_face" and f.point == "thick")
    assert thick.residuals["origin"] == [0.0, 0.0, 6.0]


def test_wrong_fixture_fails_naming_interface_point_and_residuals():
    from y4d_spec import check_cartridge

    result = check_cartridge(FRAME_PLATE_WRONG, render=True, printability=False)
    assert not result.ok
    failed = {(f.interface, f.point) for f in result.frames if f.status == "fail"}
    assert failed == {(i, p) for i in ("motor_face", "centre_bore")
                      for p in ("defaults", "thick", "long_pin")}
    assert all(f.status == "pass" for f in result.frames if f.interface == "underside")
    problems = "\n".join(result.problems)
    assert "frame 'motor_face' (plate, defaults, planar): FAIL" in problems
    assert "frame 'centre_bore' (plate, preset 'thick', axis): FAIL" in problems
    assert '"plane_offset_mm": -1.0' in problems
    assert "normal points the wrong way" in problems


def test_cli_summary_counts_frames(capsys):
    from y4d_spec.cli import main

    code = main(["check", str(FRAME_PLATE_WRONG), "--render", "--no-presets",
                 "--no-printability"])
    assert code == 1
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.endswith("frames=1/3 ok, unverified=0, failures=2")


def _mutated(tmp_path, mutate) -> tuple[Path, dict]:
    target = tmp_path / "frame-plate"
    shutil.copytree(FRAME_PLATE, target)
    doc = json.loads((target / "project.json").read_text(encoding="utf-8"))
    doc = copy.deepcopy(doc)
    mutate(doc)
    (target / "project.json").write_text(json.dumps(doc), encoding="utf-8")
    return target, doc


def test_evaluation_error_at_a_preset_is_a_failure(tmp_path):
    from y4d_spec.frame_gate import check_frames

    def mutate(doc):
        ifs = doc["hyperobject"]["cdg_interfaces"]
        doc["hyperobject"]["cdg_interfaces"] = [i for i in ifs if i["id"] == "underside"]
        doc["hyperobject"]["cdg_interfaces"][0]["frame"]["origin"] = [
            0, 0, "0 / (plate_thick - 6)"]

    target, doc = _mutated(tmp_path, mutate)
    checks = check_frames(target, doc, presets=True)
    by_point = {c.point: c for c in checks}
    assert by_point["defaults"].status == "pass"  # 0 / -2 = 0: the underside
    assert by_point["thick"].status == "fail"  # plate_thick 6: division by zero
    assert "division by zero" in by_point["thick"].message


def test_part_in_no_mode_is_unverified(tmp_path):
    from y4d_spec.frame_gate import check_frames

    def mutate(doc):
        doc["parts"].append({"id": "spare", "label": {"en": "Spare", "es": "Repuesto"}})
        doc["hyperobject"]["cdg_interfaces"] = [doc["hyperobject"]["cdg_interfaces"][2]]
        doc["hyperobject"]["cdg_interfaces"][0]["frame"]["part"] = "spare"

    target, doc = _mutated(tmp_path, mutate)
    checks = check_frames(target, doc, presets=False)
    assert [c.status for c in checks] == ["unverified"]
    assert "listed in no mode" in checks[0].message
