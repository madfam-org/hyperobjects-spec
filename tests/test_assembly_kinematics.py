"""ASM-1 §9 (contract v1.3): joints, machine-axis bindings, the pose sweep, the reference
forward kinematics and the golden pose files.

The fixture `tests/fixtures/kinematics/kinematic-gantry.assembly.json` is a Y gantry on two
MGN12 rails: the left carriage is driven (`gantry_y`), the right one is PASSIVE and closes
the cycle frame → rails → carriages → beam; an X carriage (`x_carriage`) carries a
toolhead; a motor pulley follows 9·x + 9·y (degrees); a closed GT2 loop wraps the pulley
and three idlers. Belt paths have their own module (`test_assembly_paths.py`).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path

import pytest

from assembly_helpers import assert_matrix, codes
from hyperobjects_aas.resolver import bundled_standard_parts_dir
from y4d_spec.assembly import (
    POSE_SAMPLES,
    CompositeResolver,
    PoseError,
    format_number,
    golden_poses,
    joints_of,
    pose,
    pose_from_axes,
    pose_sweep,
    validate_assembly,
)
from y4d_spec.assembly.kinematics import joint_matrix, measured_joint_value, radical_inverse
from y4d_spec.assembly.transforms import matmul

REPO = Path(__file__).resolve().parent.parent
KIN = REPO / "tests" / "fixtures" / "kinematics"
GOLDEN = REPO / "tests" / "fixtures" / "assembly-golden"
A = "voron-2-4-class-350-motion-frame"
B = "fpv-5in-freestyle"


def gantry() -> dict:
    return json.loads((KIN / "kinematic-gantry.assembly.json").read_text("utf-8"))


def resolver():
    return CompositeResolver.for_directories(
        standard_parts=[bundled_standard_parts_dir(), KIN / "standard-parts"])


def mate(doc, mate_id):
    return next(m for m in doc["mates"] if m["id"] == mate_id)


def iface(doc, component, interface):
    source = next(c for c in doc["components"] if c["id"] == component)["source"]
    return next(i for i in source["interfaces"] if i["id"] == interface)


def translation(m):
    return (m[0][3], m[1][3], m[2][3])


# ── the fixture validates at every pose ──────────────────────────────────────
def test_the_gantry_validates_at_home_every_limit_and_the_sweep():
    report = validate_assembly(gantry(), resolver())
    assert report.ok, [str(f) for f in report.findings]
    assert not report.warnings
    # home + 2 limits for each of the two driven joints + the Halton samples
    assert len(report.poses) == 1 + 2 * 2 + POSE_SAMPLES
    assert [p.name for p in report.poses[:5]] == [
        "home", "gantry_y@lower", "gantry_y@upper", "x_carriage@lower", "x_carriage@upper"]
    assert all(p.ok for p in report.poses)
    roles = {j.id: j.role for j in report.joints}
    assert roles == {"gantry_y": "driven", "gantry_y_right": "passive",
                     "x_carriage": "driven", "motor_rotation": "follower"}
    for p in report.poses:
        # the passive right carriage is measured where the beam puts it: with the left one
        assert p.joints["gantry_y_right"] == pytest.approx(p.joints["gantry_y"], abs=1e-9)
        assert p.joints["motor_rotation"] == pytest.approx(
            9 * p.joints["x_carriage"] + 9 * p.joints["gantry_y"])
        assert p.worst_origin_mm < 1e-9


def test_the_passive_mate_never_places_and_the_tree_is_reported():
    report = validate_assembly(gantry(), resolver())
    checks = {m.mate_id: m for m in report.mates}
    assert not checks["y_block_right_on_rail"].in_tree
    assert checks["y_block_right_on_rail"].joint == "gantry_y_right"
    assert checks["beam_on_right_block"].in_tree
    assert checks["y_block_left_on_rail"].in_tree


def _golden(slug):
    resolver_ab = CompositeResolver.for_directories(GOLDEN / "commons",
                                                    bundled_standard_parts_dir())
    doc = json.loads((GOLDEN / "commons" / "assemblies" / slug / "assembly.json")
                     .read_text("utf-8"))
    return doc, validate_assembly(doc, resolver_ab)


def test_the_rigid_golden_is_unchanged_one_pose_no_joints():
    _doc, report = _golden(B)
    assert report.ok and not report.warnings
    assert report.joints == [] and report.paths == []
    assert [p.name for p in report.poses] == ["home"]


def test_golden_a_poses_over_the_whole_sweep_with_constant_belts():
    """A is the full 2.4-class motion system (lane P6-ASM): three driven joints bound to
    Klipper's corexy axes, followers for the CoreXY motors, the Z blocks and the Z drives,
    and ten belt paths whose length never moves over the sweep."""
    doc, report = _golden(A)
    assert report.ok and not report.warnings, [str(f) for f in report.findings]
    driven = [j for j in report.joints if j.role == "driven"]
    assert {j.id for j in driven} == {"x_carriage", "gantry_y", "gantry_z"}
    assert len(report.joints) == 25
    assert len(report.poses) == 1 + 2 * 3 + 16 and all(p.ok for p in report.poses)
    assert len(report.paths) == 10
    for path in report.paths:
        assert path.ok and path.length_spread_mm < 1e-6, path.path_id
    axes = {b["axis"]: b for b in doc["machine"]["axes"]}
    assert doc["machine"]["kinematics"] == "corexy"
    assert {a: axes[a]["joint"] for a in axes} == {
        "x": "x_carriage", "y": "gantry_y", "z": "gantry_z"}


def test_home_is_the_placement_table_and_the_joints_move_the_children():
    doc = gantry()
    report = validate_assembly(doc, resolver())
    home = report.placements
    moved = pose(doc, resolver(), {"x_carriage": 25.0, "gantry_y": -40.0})
    # gantry_y runs along the left rail's track x, which the frame turns to world +y
    tx, ty, tz = translation(home["toolhead"])
    assert translation(moved["toolhead"]) == pytest.approx((tx + 25.0, ty - 40.0, tz))
    assert translation(moved["y_block_right"]) == pytest.approx(
        (translation(home["y_block_right"])[0], ty - 40.0, translation(home["y_block_right"])[2]))
    # the frame-fixed parts do not move
    assert_matrix(moved["idler_2"], home["idler_2"])
    # the follower pulley turns 9·(25 − 40) = −135° about its bore axis (+z in the world)
    rot = moved["motor_pulley"]
    assert math.degrees(math.atan2(rot[1][0], rot[0][0])) == pytest.approx(-135.0)


# ── negative controls ────────────────────────────────────────────────────────
def test_a_misplaced_passive_rail_fails_closure_at_home():
    doc = gantry()
    iface(doc, "frame", "y_seat_right")["frame"]["origin"] = [301, 0, 0]
    report = validate_assembly(doc, resolver())
    assert ("closure", "y_block_right_on_rail") in codes(report)
    assert "1.0000 mm apart" in str(next(f for f in report.errors if f.code == "closure"))


def test_a_rail_out_of_parallel_closes_at_home_and_fails_in_the_sweep():
    """The right rail turned 0.5° about the point its carriage sits on at home: the cycle
    closes at home, and the sweep finds it 150 · sin 0.5° = 1.31 mm off at the limits."""
    doc = gantry()
    a = math.radians(0.5)
    seat = iface(doc, "frame", "y_seat_right")["frame"]
    seat["origin"] = [300 + 165 * math.sin(a), 165 - 165 * math.cos(a), 0]
    seat["x_axis"] = [-math.sin(a), math.cos(a), 0]
    report = validate_assembly(doc, resolver())
    assert report.poses[0].ok
    errors = [f for f in report.errors if f.code == "pose-closure"]
    assert [f.subject for f in errors] == ["y_block_right_on_rail"]
    assert "first at gantry_y@lower (gantry_y=-150 mm" in errors[0].message
    assert "origins 1.3090 mm apart" in errors[0].message


def test_a_driven_joint_where_a_passive_one_belongs_fails_the_sweep_not_home():
    doc = gantry()
    joint = mate(doc, "y_block_right_on_rail")["joint"]
    del joint["passive"]
    joint["home"] = 0
    report = validate_assembly(doc, resolver())
    assert report.poses[0].ok
    assert ("pose-closure", "beam_on_right_block") in codes(report)


def test_a_passive_joint_beyond_its_limits_is_an_error():
    doc = gantry()
    mate(doc, "y_block_right_on_rail")["joint"]["limits"] = [-100, 100]
    report = validate_assembly(doc, resolver())
    errors = [f for f in report.errors if f.code == "joint-limit"]
    assert [f.subject for f in errors] == ["gantry_y_right"]
    assert "first at gantry_y@lower: gantry_y_right = -150 mm" in errors[0].message


def test_a_follower_beyond_its_limits_is_an_error():
    doc = gantry()
    mate(doc, "pulley_on_shaft")["joint"]["limits"] = [-360, 360]
    report = validate_assembly(doc, resolver())
    assert ("joint-limit", "motor_rotation") in codes(report)


@pytest.mark.parametrize("edit,code,subject,fragment", [
    (lambda d: mate(d, "x_block_on_rail")["joint"].update(id="gantry_y"), "joint", "gantry_y",
     "used by mates"),
    (lambda d: mate(d, "x_block_on_rail")["joint"].update(home=120), "joint", "x_carriage",
     "outside its limits"),
    (lambda d: mate(d, "x_block_on_rail")["joint"].update(limits=[10, -10], home=0), "joint",
     "x_carriage", "lower < upper"),
    (lambda d: mate(d, "pulley_on_shaft")["joint"]["follows"]["terms"].append(
        {"joint": "nope", "scale": 1}), "joint", "motor_rotation", "not a joint"),
    (lambda d: mate(d, "pulley_on_shaft")["joint"]["follows"]["terms"].append(
        {"joint": "gantry_y_right", "scale": 1}), "joint", "motor_rotation", "passive joint"),
    (lambda d: mate(d, "pulley_on_shaft")["joint"]["follows"]["terms"].append(
        {"joint": "motor_rotation", "scale": 1}), "joint", "motor_rotation", "itself"),
    (lambda d: mate(d, "pulley_on_shaft")["joint"]["follows"]["terms"][0].update(scale=0),
     "joint", "motor_rotation", "non-zero"),
    (lambda d: d["machine"]["axes"].append({"axis": "x", "joint": "x_carriage"}), "machine",
     "x", "bound twice"),
    (lambda d: d["machine"]["axes"].append({"axis": "z", "joint": "gantry_y_right"}),
     "machine", "z", "passive joint"),
    (lambda d: d["machine"]["axes"].append({"axis": "e", "joint": "motor_rotation"}),
     "machine", "e", "follower joint"),
    (lambda d: d["machine"]["axes"].append({"axis": "z", "joint": "lift"}), "machine", "z",
     "not a joint"),
    (lambda d: d["machine"]["axes"].append({"axis": "z", "joint": "x_carriage"}), "machine",
     "z", "already bound"),
])
def test_static_joint_and_machine_problems(edit, code, subject, fragment):
    doc = gantry()
    edit(doc)
    report = validate_assembly(doc, resolver())
    found = [f for f in report.errors if f.code == code and f.subject == subject]
    assert found and fragment in found[0].message, [str(f) for f in report.errors]
    assert len(report.poses) <= 1  # no sweep runs on a broken contract


def test_a_follower_cycle_is_named():
    doc = gantry()
    joint = mate(doc, "x_block_on_rail")["joint"]
    del joint["home"]
    joint["follows"] = {"terms": [{"joint": "motor_rotation", "scale": 1}]}
    report = validate_assembly(doc, resolver())
    cycle = [f for f in report.errors if "cycle" in f.message]
    assert cycle and "motor_rotation" in cycle[0].message and "x_carriage" in cycle[0].message


@pytest.mark.parametrize("joint", [
    {"id": "j", "type": "prismatic", "axis": "x", "home": 0},                      # no limits
    {"id": "j", "type": "prismatic", "axis": "x", "limits": [0, 1]},                # no home
    {"id": "j", "type": "revolute", "axis": "z", "passive": True, "home": 0},      # passive + home
    {"id": "j", "type": "revolute", "axis": "z", "home": 0,
     "follows": {"terms": [{"joint": "k", "scale": 1}]}},                    # follower + home
    {"id": "j", "type": "screw", "axis": "z", "home": 0},
    {"id": "j", "type": "revolute", "axis": "w", "home": 0},
])
def test_the_schema_refuses_an_incomplete_or_contradictory_joint(joint):
    doc = gantry()
    mate(doc, "x_block_on_rail")["joint"] = joint
    report = validate_assembly(doc, resolver())
    assert any(f.code == "schema" for f in report.errors)


# ── the reference forward kinematics ─────────────────────────────────────────
def test_pose_refuses_what_it_cannot_honestly_compute():
    doc = gantry()
    with pytest.raises(PoseError, match="not a joint"):
        pose(doc, resolver(), {"z_lift": 1})
    with pytest.raises(PoseError, match="follower joint"):
        pose(doc, resolver(), {"motor_rotation": 1})
    with pytest.raises(PoseError, match="passive joint"):
        pose(doc, resolver(), {"gantry_y_right": 1})
    with pytest.raises(PoseError, match="outside its limits"):
        pose(doc, resolver(), {"x_carriage": 100.5})
    with pytest.raises(PoseError, match="not a finite number"):
        pose(doc, resolver(), {"x_carriage": float("nan")})
    broken = copy.deepcopy(doc)
    iface(broken, "frame", "y_seat_right")["frame"]["origin"] = [301, 0, 0]
    with pytest.raises(PoseError, match="does not pass"):
        pose(broken, resolver(), {})


def test_pose_from_axes_applies_scale_and_offset():
    doc = gantry()
    doc["machine"]["axes"][0].update(scale=-1, offset=10)  # x_carriage = −x + 10
    a = pose_from_axes(doc, resolver(), {"x": 30.0, "y": 5.0})
    b = pose(doc, resolver(), {"x_carriage": -20.0, "gantry_y": 5.0})
    for cid in a:
        assert_matrix(a[cid], b[cid])
    with pytest.raises(PoseError, match="not bound"):
        pose_from_axes(doc, resolver(), {"z": 1.0})


@pytest.mark.parametrize("axis", ["x", "y", "z"])
@pytest.mark.parametrize("kind,value", [("prismatic", 12.5), ("revolute", -37.25),
                                         ("revolute", 179.0)])
def test_a_joint_value_is_measured_back_from_its_matrix(axis, kind, value):
    m = joint_matrix(kind, axis, value)
    assert measured_joint_value(kind, axis, m) == pytest.approx(value)


def test_revolute_joints_turn_right_handed_about_their_axis():
    # +90° about z takes x to y; about x takes y to z; about y takes z to x
    assert_matrix(matmul(joint_matrix("revolute", "z", 90), ((1, 0, 0, 0), (0, 1, 0, 0),
                                                              (0, 0, 1, 0), (0, 0, 0, 1))),
                  ((0, -1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
    assert joint_matrix("revolute", "x", 90)[2][1] == 1.0
    assert joint_matrix("revolute", "y", 90)[0][2] == 1.0


# ── the sweep ────────────────────────────────────────────────────────────────
def test_the_halton_sequence_is_the_documented_one():
    assert [radical_inverse(k, 2) for k in (1, 2, 3, 4)] == [0.5, 0.25, 0.75, 0.125]
    assert radical_inverse(1, 3) == pytest.approx(1 / 3)
    assert radical_inverse(5, 3) == pytest.approx(7 / 9)
    joints = joints_of(gantry())
    poses = pose_sweep(joints, samples=3)
    assert [p.name for p in poses] == [
        "home", "gantry_y@lower", "gantry_y@upper", "x_carriage@lower", "x_carriage@upper",
        "sample-1", "sample-2", "sample-3"]
    # gantry_y (base 2) over [−150, 150], x_carriage (base 3) over [−100, 100]
    assert poses[5].driven == {"gantry_y": 0.0, "x_carriage": -33.3333}
    assert poses[6].driven == {"gantry_y": -75.0, "x_carriage": 33.3333}
    assert pose_sweep(joints, samples=3, seed=2)[5].driven == poses[6].driven


def test_a_continuous_revolute_joint_is_sampled_over_a_turn_and_has_no_limit_poses():
    doc = gantry()
    joint = mate(doc, "pulley_on_shaft")["joint"]
    del joint["follows"]
    joint["home"] = 0
    poses = pose_sweep(joints_of(doc), samples=4)
    assert not any(p.name.startswith("motor_rotation@") for p in poses)
    samples = [p.driven["motor_rotation"] for p in poses if p.kind == "sample"]
    assert all(-180 <= v < 180 for v in samples) and len(set(samples)) == 4
    report = validate_assembly(doc, resolver(), pose_samples=4)
    assert report.ok and all(p.ok for p in report.poses)


def test_the_sweep_is_fast_enough_for_every_pr():
    """The budget the docs state: the fixture's 21 poses well under a second."""
    import time

    start = time.perf_counter()
    validate_assembly(gantry(), resolver())
    assert time.perf_counter() - start < 2.0


# ── the golden pose files ────────────────────────────────────────────────────
def _refresh_script():
    spec = importlib.util.spec_from_file_location(
        "refresh_pose_golden", REPO / "scripts" / "refresh_pose_golden.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_golden_pose_files_are_current():
    script = _refresh_script()
    for document, golden, res in script.targets():
        assert golden.is_file(), f"{golden} is missing: run scripts/refresh_pose_golden.py"
        assert script.build(document, res) == golden.read_text("utf-8"), (
            f"{golden.name} moved: run scripts/refresh_pose_golden.py and review the diff")


def test_the_golden_pose_file_format():
    doc = gantry()
    report = validate_assembly(doc, resolver())
    golden = golden_poses(doc, report)
    assert golden["format"] == "hyperobjects.assembly-poses"
    assert golden["assembly_digest"] == report.digest
    assert [j["id"] for j in golden["joints"]] == ["gantry_y", "x_carriage", "motor_rotation"]
    sample = golden["poses"][5]
    assert sample["inputs"] == {"gantry_y": 0.0, "x_carriage": -33.3333}
    assert sample["joints"]["motor_rotation"] == "-299.999700"
    assert len(sample["transforms"]) == len(doc["components"])
    assert all(len(v) == 16 and all(isinstance(x, str) for x in v)
               for v in sample["transforms"].values())
    # the fixed format round-trips to the placement within half a unit of the sixth decimal
    placed = pose(doc, resolver(), sample["inputs"])
    flat = [v for row in placed["toolhead"] for v in row]
    assert all(abs(float(s) - v) <= 5e-7 for s, v in zip(sample["transforms"]["toolhead"],
                                                          flat, strict=True))


@pytest.mark.parametrize("value,text", [
    (1.0, "1.000000"),
    (0.0078125, "0.007813"),       # an exact binary tie: away from zero, like toFixed(6)
    (-0.0078125, "-0.007813"),
    (-1e-9, "0.000000"),           # −0 is written 0
    (-0.0, "0.000000"),
    (165.0000004, "165.000000"),
    (2.675, "2.675000"),
    (1e-7, "0.000000"),
    (5e-7, "0.000000"),            # the double lies just below 0.0000005: no tie, down
])
def test_format_number_is_the_documented_fixed_format(value, text):
    assert format_number(value) == text
