"""ASM-1 §9 (v1.3): declared belt paths, the catalog's belt facts, the Kinematics
submodel and the CLI. The fixture is `tests/fixtures/kinematics/kinematic-gantry` (see
test_assembly_kinematics.py): its closed loop wraps the motor pulley and three idlers on
an 80 × 200 mm rectangle of pitch-circle centres."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from aas_support import child, submodel
from hyperobjects_aas import check_environment
from hyperobjects_aas.assembly import build_assembly_environment
from hyperobjects_aas.ids import PROJECTION_VERSION
from hyperobjects_aas.resolver import bundled_standard_parts_dir
from hyperobjects_standard_parts import load_part
from hyperobjects_standard_parts.check import check_part
from y4d_spec.assembly import CompositeResolver, assembly_digest, validate_assembly
from y4d_spec.cli import main as y4d_main

REPO = Path(__file__).resolve().parent.parent
KIN = REPO / "tests" / "fixtures" / "kinematics"
GT2_20T_PD = 12.73  # Gates 20-2MR-PS-4 (the catalog entries' cited pitch diameter)
LOOP = 2 * (80 + 200) + math.pi * GT2_20T_PD


def gantry() -> dict:
    return json.loads((KIN / "kinematic-gantry.assembly.json").read_text("utf-8"))


def resolver(*extra):
    return CompositeResolver.for_directories(
        standard_parts=[bundled_standard_parts_dir(), KIN / "standard-parts", *extra])


def iface(doc, component, interface):
    source = next(c for c in doc["components"] if c["id"] == component)["source"]
    return next(i for i in source["interfaces"] if i["id"] == interface)


def path_errors(report):
    return [f.message for f in report.errors if f.code == "path"]


# ── the closed loop ──────────────────────────────────────────────────────────
def test_the_closed_loop_length_is_the_rectangle_plus_one_pitch_circle():
    report = validate_assembly(gantry(), resolver())
    (path,) = report.paths
    assert path.ok and path.closed
    assert path.length_mm == pytest.approx(LOOP, abs=1e-9)
    assert path.planarity_mm == pytest.approx(0.0, abs=1e-12)
    assert path.as_dict()["teeth"] == pytest.approx(LOOP / 2, abs=1e-6)
    # the idlers are frame-fixed: the length cannot move across the sweep
    assert len(path.lengths) == len(report.poses)
    assert path.length_spread_mm == pytest.approx(0.0, abs=1e-9)


def test_wrapping_one_idler_the_other_way_wraps_it_three_quarters_round():
    """idler_2 wrapped clockwise: the belt crosses to its outer side and wraps 270° of it,
    so the loop is longer than the convex one; the length stays finite and valid."""
    doc = gantry()
    doc["paths"][0]["via"][2] = {"component": "idler_2", "wrap": "cw"}
    report = validate_assembly(doc, resolver())
    assert report.ok
    assert report.paths[0].length_mm > LOOP + math.pi * GT2_20T_PD / 2


def _two_pulleys(r1, r2, distance, wraps, closed=True):
    """Two pitch circles on the x axis, seen from +z, through `path_length` directly."""
    from hyperobjects_standard_parts import BeltEngagement
    from y4d_spec.assembly.paths import Via, path_length
    from y4d_spec.assembly.transforms import IDENTITY

    placements = {"p1": IDENTITY,
                  "p2": tuple(tuple(v + (distance if (i, j) == (0, 3) else 0) for j, v in
                                    enumerate(row)) for i, row in enumerate(IDENTITY))}
    engagements = {"p1": BeltEngagement(True, 2 * r1, (0, 0, 0), (0, 0, 1)),
                   "p2": BeltEngagement(True, 2 * r2, (0, 0, 0), (0, 0, 1))}
    vias = [Via("p1", wrap=wraps[0], side="teeth"), Via("p2", wrap=wraps[1], side="teeth")]
    return path_length(vias, closed, placements, engagements, {}, [2 * r1, 2 * r2])[0]


@pytest.mark.parametrize("r1,r2,d", [(10, 10, 100), (20, 6.365, 150), (6.365, 30, 80)])
def test_the_length_matches_the_textbook_open_and_crossed_belt_formulas(r1, r2, d):
    """Open belt: 2√(d² − (r1 − r2)²) + π(r1 + r2) + 2(r1 − r2)·asin((r1 − r2)/d).
    Crossed belt: 2√(d² − (r1 + r2)²) + (r1 + r2)(π + 2·asin((r1 + r2)/d))."""
    open_belt = (2 * math.sqrt(d * d - (r1 - r2) ** 2) + math.pi * (r1 + r2)
                 + 2 * (r1 - r2) * math.asin((r1 - r2) / d))
    crossed = 2 * math.sqrt(d * d - (r1 + r2) ** 2) + (r1 + r2) * (
        math.pi + 2 * math.asin((r1 + r2) / d))
    assert _two_pulleys(r1, r2, d, ("ccw", "ccw")) == pytest.approx(open_belt, abs=1e-9)
    assert _two_pulleys(r1, r2, d, ("cw", "cw")) == pytest.approx(open_belt, abs=1e-9)
    assert _two_pulleys(r1, r2, d, ("ccw", "cw")) == pytest.approx(crossed, abs=1e-9)


def test_the_belt_digest_enters_only_documents_with_paths():
    doc, ids = {"a": 1}, {"c": {"type": "external"}}
    assert assembly_digest(doc, ids) == assembly_digest(doc, ids, path_parts=None)
    assert assembly_digest(doc, ids) != assembly_digest(doc, ids, path_parts={"p": {"k": 1}})
    report = validate_assembly(gantry(), resolver())
    no_paths = gantry()
    del no_paths["paths"]
    assert validate_assembly(no_paths, resolver()).digest != report.digest


# ── path errors ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("edit,fragment", [
    (lambda p: p.update(part="mgn12-rail"), "is not a belt"),
    (lambda p: p.update(part="no-such-belt"), "not in"),
    (lambda p: p["via"].__setitem__(1, "y_block_left"), "declares no belt_engagement"),
    (lambda p: p["via"].__setitem__(1, {"component": "motor_pulley", "side": "back"}),
     "toothed part"),
    (lambda p: p["via"].__setitem__(1, "ghost"), "not a component"),
    (lambda p: p["via"].__setitem__(1, {"component": "frame", "interface": "motor_seat"}),
     "closed path has no anchors"),
    (lambda p: p.update(closed=False), "starts and ends at an anchor"),
])
def test_path_problems_are_errors(edit, fragment):
    doc = gantry()
    edit(doc["paths"][0])
    report = validate_assembly(doc, resolver())
    assert any(fragment in m for m in path_errors(report)), [str(f) for f in report.errors]


def test_a_non_planar_path_fails_at_home():
    doc = gantry()
    iface(doc, "frame", "idler_seat_3")["frame"]["origin"] = [-160, 200, -1]
    report = validate_assembly(doc, resolver())
    assert any("spread 1.0000 mm along the path normal" in m for m in path_errors(report))


def test_tilted_pulley_axes_are_not_one_plane():
    doc = gantry()
    iface(doc, "frame", "idler_seat_3")["frame"]["normal"] = [0, math.sin(math.radians(2)),
                                                                math.cos(math.radians(2))]
    report = validate_assembly(doc, resolver())
    assert any("from parallel" in m for m in path_errors(report))


def test_overlapping_circles_have_no_span():
    doc = gantry()
    iface(doc, "frame", "idler_seat_1")["frame"]["origin"] = [-85, 0, -2]
    doc["paths"][0]["via"][0] = {"component": "idler_1", "wrap": "cw"}
    report = validate_assembly(doc, resolver())
    assert any("overlap" in m for m in path_errors(report))


def _open_path(doc, part="gt2-belt-6mm-test"):
    """A clamp on the toolhead (moves with x and y) → idler_3 → a clamp on the frame, all
    in the belt plane z = 5 (the idlers' mid-plane: seat −2 + width 14 / 2)."""
    toolhead = next(c for c in doc["components"] if c["id"] == "toolhead")["source"]
    toolhead["interfaces"].append({
        "id": "belt_clamp", "frame": {"origin": [0, 0, -41], "normal": [0, 0, 1],
                                      "x_axis": [1, 0, 0]},
        "polarity": "neutral", "size_key": "belt-clamp-test", "symmetry": 1})
    frame = next(c for c in doc["components"] if c["id"] == "frame")["source"]
    frame["interfaces"].append({
        "id": "belt_end", "frame": {"origin": [-160, 300, 5], "normal": [0, 0, 1],
                                    "x_axis": [1, 0, 0]},
        "polarity": "neutral", "size_key": "belt-clamp-test", "symmetry": 1})
    doc["paths"].append({"id": "open", "kind": "belt", "part": part,
                         "closed": False, "via": [
                             {"component": "toolhead", "interface": "belt_clamp"},
                             {"component": "idler_3", "wrap": "cw"},
                             {"component": "frame", "interface": "belt_end"}]})
    return doc


def test_an_open_path_to_a_moving_clamp_warns_when_its_length_varies():
    doc = _open_path(gantry())
    report = validate_assembly(doc, resolver())
    assert report.ok, [str(f) for f in report.errors]
    warnings = [f for f in report.warnings if f.code == "path-length"]
    assert [f.subject for f in warnings] == ["open"]
    assert report.paths[1].length_spread_mm > 1.0


# ── smooth parts, belt sides, closed-loop belts (a temporary catalog) ────────
@pytest.fixture
def smooth_catalog(tmp_path):
    belt = json.loads((KIN / "standard-parts" / "gt2-belt-6mm-test.json").read_text("utf-8"))
    with_offsets = copy.deepcopy(belt)
    with_offsets["key"] = "gt2-belt-offsets-test"
    with_offsets["belt"]["teeth_side_offset"] = {"value": 1.014, "unit": "mm", "source": 0}
    with_offsets["belt"]["back_side_offset"] = {"value": 0.506, "unit": "mm", "source": 0}
    loop = copy.deepcopy(with_offsets)
    loop["key"] = "gt2-loop-test"
    loop["belt"]["loop_length"] = {"value": 600, "unit": "mm", "source": 0}
    idler = load_part("gt2-idler-20t-9mm")
    idler["key"] = "smooth-idler-test"
    idler["belt_engagement"]["running_diameter"] = {"value": 13, "unit": "mm", "source": 0}
    del idler["belt_engagement"]["pitch_diameter"]
    for entry in (with_offsets, loop, idler):
        (tmp_path / f"{entry['key']}.json").write_text(json.dumps(entry), "utf-8")
    return tmp_path


def _smooth(doc):
    next(c for c in doc["components"] if c["id"] == "idler_2")["source"]["key"] = (
        "smooth-idler-test")


def test_a_smooth_via_needs_the_belt_offset_for_its_side(smooth_catalog):
    doc = gantry()
    _smooth(doc)
    report = validate_assembly(doc, resolver(smooth_catalog))
    assert any("teeth_side_offset" in m for m in path_errors(report))


@pytest.mark.parametrize("side,offset", [("teeth", 1.014), ("back", 0.506)])
def test_a_smooth_via_runs_on_its_diameter_plus_the_sides_offset(smooth_catalog, side, offset):
    doc = gantry()
    _smooth(doc)
    doc["paths"][0]["part"] = "gt2-belt-offsets-test"
    doc["paths"][0]["via"][2] = {"component": "idler_2", "side": side}
    report = validate_assembly(doc, resolver(smooth_catalog))
    assert report.ok, [str(f) for f in report.errors]
    # three toothed wheels and one smooth one: the arcs add up to one full turn, so the
    # loop is the rectangle plus a quarter turn on each diameter
    # About a quarter turn on each wheel: the larger smooth wheel tilts its two spans by
    # under 0.01 rad, which the 0.05 mm bound covers (the exact geometry is proven by the
    # two-pulley formulas above)
    smooth = 13 + 2 * offset
    expected = 2 * (80 + 200) + math.pi * (3 * GT2_20T_PD + smooth) / 4
    assert report.paths[0].length_mm == pytest.approx(expected, abs=0.05)
    assert report.paths[0].length_mm > LOOP


def test_a_closed_loop_belt_must_close_and_is_compared_with_its_catalog_length(
        smooth_catalog):
    doc = gantry()
    doc["paths"][0]["part"] = "gt2-loop-test"
    report = validate_assembly(doc, resolver(smooth_catalog))
    assert report.ok
    assert report.paths[0].loop_length_mm == 600
    assert not [f for f in report.warnings if f.code == "path-length"]  # 599.99 vs 600
    report = validate_assembly(_open_path(gantry(), "gt2-loop-test"), resolver(smooth_catalog))
    assert any("must be closed" in m for m in path_errors(report))
    far = gantry()
    far["paths"][0]["part"] = "gt2-loop-test"
    iface(far, "frame", "idler_seat_2")["frame"]["origin"] = [-80, 202, -2]
    iface(far, "frame", "idler_seat_3")["frame"]["origin"] = [-160, 202, -2]
    report = validate_assembly(far, resolver(smooth_catalog))
    assert [f.subject for f in report.warnings if f.code == "path-length"] == ["loop"]


# ── the catalog's belt facts ─────────────────────────────────────────────────
def test_the_two_gt2_entries_cite_their_pitch_diameter():
    for key in ("gt2-pulley-20t-5mm", "gt2-idler-20t-9mm"):
        part = load_part(key)
        pd = part["belt_engagement"]["pitch_diameter"]
        assert pd["value"] == GT2_20T_PD and pd["unit"] == "mm"
        assert "cmtco.com" in part["sources"][pd["source"]]["url"]
        assert "onvention" in part["belt_engagement"]["plane_note"]
        assert check_part(part, name=key) == []
    # 20 teeth × 2 mm / π, to the table's two decimals
    assert round(20 * 2 / math.pi, 2) == GT2_20T_PD


@pytest.mark.parametrize("edit,fragment", [
    (lambda p: p["belt_engagement"].update(center=[0, 0, "nope"]), "not a parameter"),
    (lambda p: p["belt_engagement"].update(axis=[0, 0, 2]), "|axis|"),
    (lambda p: p["belt_engagement"].update(running_diameter={"value": 13, "unit": "mm",
                                                              "source": 0}), "schema"),
    (lambda p: p["belt_engagement"]["pitch_diameter"].update(source=9), "cites source 9"),
    (lambda p: p.update(belt={"pitch": {"value": 2, "unit": "mm", "source": 0},
                              "width": {"value": 6, "unit": "mm", "source": 0}}), "schema"),
    (lambda p: p.update(interfaces=[]), "schema"),
])
def test_catalog_belt_rules(edit, fragment):
    part = load_part("gt2-idler-20t-9mm")
    edit(part)
    problems = check_part(part, name="gt2-idler-20t-9mm")
    if fragment == "schema":
        assert problems and all(":" in p for p in problems)
    else:
        assert any(fragment in p for p in problems), problems


def test_a_belt_needs_its_block_and_may_have_no_interfaces():
    belt = json.loads((KIN / "standard-parts" / "gt2-belt-6mm-test.json").read_text("utf-8"))
    assert check_part(belt, name="gt2-belt-6mm-test") == []
    del belt["belt"]
    assert check_part(belt, name="gt2-belt-6mm-test")


# ── the Kinematics submodel (projection version 2) ───────────────────────────
def test_the_kinematics_submodel_carries_joints_bindings_paths_and_the_sweep():
    doc = gantry()
    report = validate_assembly(doc, resolver())
    env = build_assembly_environment(doc, report)
    result = check_environment(env, basyx="off")
    assert result.ok, [str(f) for f in result.errors]
    sm = submodel(env, "Kinematics")
    assert sm["id"].endswith(f"/p{PROJECTION_VERSION}/Kinematics")
    assert child(sm, "KinematicsClass")["value"] == "cartesian"
    joints = child(sm, "Joints")["value"]
    roles = {child(j, "JointId")["value"]: child(j, "Role")["value"] for j in joints}
    assert roles == {"gantry_y": "driven", "gantry_y_right": "passive",
                     "x_carriage": "driven", "motor_rotation": "follower"}
    assert len(child(sm, "AxisBindings")["value"]) == 2
    (path,) = child(sm, "Paths")["value"]
    assert float(child(path, "PitchLengthMm")["value"]) == pytest.approx(LOOP, abs=1e-6)
    sweep = child(sm, "PoseSweep")
    assert child(sweep, "PoseCount")["value"] == "21"
    assert child(sweep, "Validated")["value"] == "true"


# ── the CLI ──────────────────────────────────────────────────────────────────
def _parts_args():
    return ["--standard-parts", str(bundled_standard_parts_dir()),
            "--standard-parts", str(KIN / "standard-parts")]


def test_cli_check_prints_joints_poses_and_paths(capsys):
    code = y4d_main(["assembly", "check", str(KIN / "kinematic-gantry.assembly.json"),
                     *_parts_args()])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "gantry_y_right: prismatic along/about x of y_rail_right → y_block_right" in out
    assert "x_carriage@upper: origin=0.0000" in out
    assert "path loop: gt2-belt-6mm-test closed length=599.9925 mm" in out
    assert "joints=4 poses=21/21 paths=1" in out


def test_cli_pose_samples_and_the_poses_command(capsys, tmp_path):
    y4d_main(["assembly", "check", str(KIN / "kinematic-gantry.assembly.json"),
              *_parts_args(), "--pose-samples", "0"])
    assert "poses=5/5" in capsys.readouterr().out
    out = tmp_path / "poses.json"
    code = y4d_main(["assembly", "poses", str(KIN / "kinematic-gantry.assembly.json"),
                     *_parts_args(), "--out", str(out)])
    assert code == 0
    assert out.read_text("utf-8") == (KIN / "kinematic-gantry.poses.json").read_text("utf-8")
