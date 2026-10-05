"""The 2.4-class gantry's standard parts (lane P6-GANTRY), proven by placement.

The Voron 2.4r2 build guide (GPL-3.0; cited by page only) and the VORON 2.4 sourcing sheet
name the parts; the facts come from datasheets:

* the gantry's Y sides (guide p. 88): an MGN9 rail centred on each C extrusion, its end 25 mm
  from the extrusion's end, a 400 mm rail for the 350 build size (sourcing sheet), carrying an
  MGN9H block (HIWIN MG series);
* the XY joints (pp. 97–100): an F695 stack (shim, F695, F695, shim) and a GT2 20-tooth idler
  for the 6 mm A/B belt (p. 131; sourcing sheet), each on an M5x40 SHCS;
* the A/B belts: GT2, 2 mm pitch, 6 mm wide (2MR/PGGT2 section from Pfeifer; the pitch line
  0.254 mm above the tooth bottom, SDP/SI Table 4).

Two chains close here:

(i)  C extrusion → MGN9 rail (at its 25 mm setback) → MGN9H block → XY joint → M5x40 →
     shim → F695 → F695 → shim, between the joint's floor and roof faces;
(ii) the same joint → M5x40 → GT2 20T 6 mm idler.

The joint is framed exactly as the commons cartridge ``xy-joint`` frames it at its defaults
(the left hand; solid PR of this lane): origin at the block's top face centre, +x to the
gantry's right (inboard for the left hand), +y to the back, +z up. Its stack sits on the
belt line's front side (centre y −7.006: the back of the belt runs on it, 13 / 2 + 0.506) at
the low level, its idler on the back side (y +6.366: the GT2 20T pitch radius) at the high
level. The block top is 10 above the C extrusion's top face (MGN9 H 10), so the low and high
belt mid-planes are 22 and 31 above it.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

import hyperobjects_standard_parts
from hyperobjects_lexicon.fabrication import load_fabrication_vocabulary
from hyperobjects_standard_parts import interface_frames, load_part, resolve_parameters
from y4d_spec.assembly import (
    CompositeResolver,
    ExternalResolver,
    StandardPartsResolver,
    validate_assembly,
)

CATALOG = Path(hyperobjects_standard_parts.__file__).parent / "parts"
NEW_KEYS = ("mgn9-rail", "mgn9-carriage")
NEW_PARTS = ("mgn9-rail", "mgn9h-carriage", "gt2-belt-6mm", "gt2-idler-20t-6mm")

STACK_Y = -(13 / 2 + 0.506)        # F695 running diameter / 2 + the belt's back-side offset
IDLER_Y = 20 * 2 / math.pi / 2     # GT2 20T pitch radius
LOW, HIGH = 12.0, 21.0             # belt mid-planes above the joint's block top


def _resolver():
    return CompositeResolver(standard=StandardPartsResolver(CATALOG), external=ExternalResolver())


def _iface(iid, polarity, size_key, symmetry, origin, normal, x_axis):
    return {"id": iid, "polarity": polarity, "size_key": size_key, "symmetry": symmetry,
            "frame": {"origin": origin, "normal": normal, "x_axis": x_axis}}


def _external(cid, *ifaces):
    return {"id": cid, "source": {"type": "external", "name": f"Test {cid}",
                                  "license": "CERN-OHL-W-2.0", "url": "https://example.org/x",
                                  "interfaces": list(ifaces)}}


def _std(cid, key, **parameters):
    source = {"type": "standard", "key": key}
    if parameters:
        source["parameters"] = parameters
    return {"id": cid, "source": source}


def _assembly(components, mates):
    return {
        "format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "gantry-parts",
        "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
        "root": components[0]["id"], "components": components, "mates": mates,
    }


def _mate(mid, a, b, **kw):
    (ca, ia), (cb, ib) = a.split("."), b.split(".")
    return {"id": mid, "a": {"component": ca, "interface": ia},
            "b": {"component": cb, "interface": ib}, **kw}


def _apply(matrix, point):
    return tuple(sum(matrix[r][c] * (list(point) + [1.0])[c] for c in range(4)) for r in range(3))


def _joint(stack_z=LOW, idler_z=HIGH, idler_width=9.0, carriage_size="mgn9-carriage"):
    """xy-joint (left hand, defaults): the frames the cartridge declares."""
    return _external(
        "joint",
        _iface("xy_joint_carriage", "male", carriage_size, 2, [0, 0, 0], [0, 0, -1], [0, 1, 0]),
        _iface("xy_joint_stack_bolt", "female", "m5-clearance-hole", 0, [32, STACK_Y, 31],
               [0, 0, 1], [1, 0, 0]),
        _iface("xy_joint_stack_roof", "neutral", "m5-axle-stack-face", 0,
               [32, STACK_Y, stack_z + 5], [0, 0, -1], [1, 0, 0]),
        _iface("xy_joint_stack_floor", "neutral", "m5-axle-stack-face", 0,
               [32, STACK_Y, stack_z - 5], [0, 0, 1], [1, 0, 0]),
        _iface("xy_joint_idler_bolt", "female", "m5-clearance-hole", 0, [37, IDLER_Y, 31],
               [0, 0, 1], [1, 0, 0]),
        _iface("xy_joint_idler_roof", "neutral", "m5-axle-stack-face", 0,
               [37, IDLER_Y, idler_z + idler_width / 2], [0, 0, -1], [1, 0, 0]),
        _iface("xy_joint_idler_floor", "neutral", "m5-axle-stack-face", 0,
               [37, IDLER_Y, idler_z - idler_width / 2], [0, 0, 1], [1, 0, 0]),
    )


def _gantry_side(joint=None, block="mgn9h-carriage", carriage_offset=0.0, stack_journal=14.0,
                 idler_journal=5.5):
    """C extrusion (top face = its +y face) → MGN9 rail → block → joint → stack and idler."""
    components = [
        _std("c_left", "extrusion-2020", length_mm=450),
        _std("y_rail", "mgn9-rail", length_mm=400, base_station_mm=-15,
             carriage_offset_mm=carriage_offset),
        _std("y_block", block),
        joint or _joint(),
        _std("stack_screw", "shcs-m5x40", journal_offset_mm=stack_journal),
        _std("shim_1", "shim-5x10"), _std("f695_1", "bearing-f695"),
        _std("f695_2", "bearing-f695"), _std("shim_2", "shim-5x10"),
        _std("idler_screw", "shcs-m5x40", journal_offset_mm=idler_journal),
        _std("idler", "gt2-idler-20t-6mm"),
    ]
    mates = [
        _mate("rail_on_c", "c_left.slot_yp_a", "y_rail.base_at_station", rotation_index=0),
        _mate("block_on_rail", "y_rail.track", "y_block.rail_way", rotation_index=0),
        _mate("joint_on_block", "y_block.top", "joint.xy_joint_carriage", rotation_index=0),
        _mate("stack_screw_in_joint", "joint.xy_joint_stack_bolt", "stack_screw.head_seat",
              angle_deg=0),
        _mate("shim_1_on_screw", "stack_screw.journal", "shim_1.bore", angle_deg=0),
        _mate("shim_1_on_roof", "joint.xy_joint_stack_roof", "shim_1.face_a", angle_deg=0),
        _mate("f695_1_on_shim", "shim_1.face_b", "f695_1.flange_face", angle_deg=0),
        _mate("back_to_back", "f695_1.plain_face", "f695_2.plain_face", angle_deg=0),
        _mate("shim_2_on_f695", "f695_2.flange_face", "shim_2.face_a", angle_deg=0),
        _mate("stack_on_floor", "shim_2.face_b", "joint.xy_joint_stack_floor", angle_deg=0),
        _mate("idler_screw_in_joint", "joint.xy_joint_idler_bolt", "idler_screw.head_seat",
              angle_deg=0),
        _mate("idler_on_screw", "idler_screw.journal", "idler.bore", angle_deg=0),
        _mate("idler_on_roof", "joint.xy_joint_idler_roof", "idler.face_a", angle_deg=0),
        _mate("idler_on_floor", "idler.face_b", "joint.xy_joint_idler_floor", angle_deg=0),
    ]
    return _assembly(components, mates)


def _height_above_c_top(placements, component, point):
    """World point's height above the C extrusion's top (+y) face, along that face's normal."""
    c = placements["c_left"]
    p = _apply(placements[component], point)
    top = _apply(c, (0, 10, 0))
    normal = tuple(c[r][1] for r in range(3))
    return sum((p[i] - top[i]) * normal[i] for i in range(3))


# ── vocabulary and catalog facts ──────────────────────────────────────────────
def test_the_new_size_keys_are_cited_and_typed():
    entries = {e["key"]: e for e in load_fabrication_vocabulary("interface-sizes")["entries"]}
    for key, gtype in {"mgn9-rail": "rail", "mgn9-carriage": "bolt_pattern"}.items():
        entry = entries[key]
        assert entry["geometry_type"] == gtype, key
        assert entry["sources"] and all(s["url"].startswith("https://") for s in entry["sources"])
        for dim in entry["dimensions"].values():
            assert 0 <= dim["source"] < len(entry["sources"]), key
        assert set(entry["label"]) == set(entry["definition"]) == {"en", "es", "fr", "pt"}


def test_the_part_facts_match_their_datasheets():
    rail = load_part("mgn9-rail")["dimensions"]
    assert [rail[k]["value"] for k in ("rail_width", "rail_height", "hole_pitch",
                                       "end_hole_distance")] == [9, 6.5, 20, 7.5]
    assert rail["length_350_build"]["value"] == 400
    assert rail["setback_from_extrusion_end"]["value"] == 25
    block = load_part("mgn9h-carriage")["dimensions"]
    assert [block[k]["value"] for k in ("assembly_height", "block_width", "hole_spacing_b",
                                        "hole_spacing_c", "block_length")] == [10, 20, 15, 16, 39.9]
    assert block["rail_top_depth"]["value"] == pytest.approx(10 - 6.5)
    belt = load_part("gt2-belt-6mm")
    assert belt["category"] == "belt"
    d = {k: v["value"] for k, v in belt["belt"].items()}  # the ASM-1 §9 belt block
    assert (d["pitch"], d["width"], d["height"], d["tooth_depth"]) == (2, 6, 1.52, 0.76)
    assert d["pitch_line_differential"] == 0.254
    assert d["teeth_side_offset"] == pytest.approx(d["tooth_depth"] + d["pitch_line_differential"])
    assert d["back_side_offset"] == pytest.approx(
        d["height"] - d["tooth_depth"] - d["pitch_line_differential"])
    idler = load_part("gt2-idler-20t-6mm")
    di = {k: v["value"] for k, v in idler["dimensions"].items()}
    assert (di["tooth_count"], di["bore"], di["belt_width"],
            di["outside_diameter"]) == (20, 5, 6, 18)
    # The cited pitch diameter is the GT2 identity pd = N·p/π, to the table's two decimals.
    engagement = idler["belt_engagement"]
    assert engagement["pitch_diameter"]["value"] == pytest.approx(20 * d["pitch"] / math.pi,
                                                                  abs=0.005)
    assert engagement["center"] == [0, 0, "width_mm / 2"] and engagement["axis"] == [0, 0, 1]
    assert idler["parameters"][0]["default"] == di["overall_width"]


def test_the_belt_ends_are_framed_on_the_pitch_line():
    part = load_part("gt2-belt-6mm")
    frames = interface_frames(part, resolve_parameters(part, {"length_mm": 1500}))
    assert frames["end_a"].origin == pytest.approx((0, 0, 0))
    assert frames["end_b"].origin == pytest.approx((1500, 0, 0))
    assert frames["end_a"].normal == pytest.approx((-1, 0, 0))
    assert frames["end_b"].normal == pytest.approx((1, 0, 0))


@pytest.mark.parametrize("given", [{}, {"length_mm": 250, "carriage_offset_mm": 40,
                                        "base_station_mm": -15}])
def test_the_rail_frames_follow_their_parameters(given):
    part = load_part("mgn9-rail")
    values = resolve_parameters(part, given)
    frames = interface_frames(part, values)
    assert frames["track"].origin == pytest.approx(
        (values["length_mm"] / 2 + values["carriage_offset_mm"], 0, 6.5))
    assert frames["base_first_hole"].origin == pytest.approx((7.5, 0, 0))
    assert frames["base_at_station"].origin == pytest.approx((values["base_station_mm"], 0, 0))


# ── (i) a Y carriage on an MGN9 rail, and the F695 stack in the XY joint ─────
def test_the_gantry_side_closes_and_places_every_part():
    report = validate_assembly(_gantry_side(), _resolver())
    assert report.ok, report.findings
    assert len(report.mates) == 14 and all(m.ok for m in report.mates)
    p = report.placements
    # The rail stands on the C's top face, its end A 25 from the C's end A (guide p. 88).
    assert _height_above_c_top(p, "y_rail", (0, 0, 0)) == pytest.approx(0)
    assert _apply(p["y_rail"], (0, 0, 0))[2] == pytest.approx(25)
    assert _apply(p["y_rail"], (400, 0, 0))[2] == pytest.approx(425)
    # The block's top face is H = 10 above the C, at the rail's mid-length.
    assert _height_above_c_top(p, "y_block", (0, 0, 0)) == pytest.approx(10)
    assert _apply(p["y_block"], (0, 0, 0))[2] == pytest.approx(225)
    # The stack: shim, F695 (flange up), F695 (flange down), shim, from the roof down; the
    # plain faces meet on the low belt mid-plane, 22 above the C.
    assert _height_above_c_top(p, "f695_1", (0, 0, 4)) == pytest.approx(10 + LOW)
    assert _height_above_c_top(p, "f695_2", (0, 0, 4)) == pytest.approx(10 + LOW)
    assert _height_above_c_top(p, "shim_1", (0, 0, 0)) == pytest.approx(10 + LOW + 5)
    assert _height_above_c_top(p, "shim_2", (0, 0, 1)) == pytest.approx(10 + LOW - 5)
    # The idler's mid-plane (width_mm / 2, a convention) is the high belt level, 31.
    assert _height_above_c_top(p, "idler", (0, 0, 4.5)) == pytest.approx(10 + HIGH)
    # The screws: heads on the joint's bridge top, 31 above the block top.
    assert _height_above_c_top(p, "stack_screw", (0, 0, 0)) == pytest.approx(10 + 31)
    assert _height_above_c_top(p, "idler_screw", (0, 0, 0)) == pytest.approx(10 + 31)


@pytest.mark.parametrize("offset", [-150, 0, 120])
def test_the_block_runs_along_the_rail(offset):
    """The Y carriage's travel: the rail's carriage_offset_mm moves the whole joint chain."""
    report = validate_assembly(_gantry_side(carriage_offset=offset), _resolver())
    assert report.ok, report.findings
    assert _apply(report.placements["y_block"], (0, 0, 0))[2] == pytest.approx(225 + offset)


def test_the_stack_and_the_idler_tangent_the_same_belt_line():
    """Both elements touch the belt line through the joint's centre (y = 0), on opposite sides:
    the stack by its running diameter plus the belt's back-side offset, the idler by its pitch
    radius (ASM-1 §9 effective diameters)."""
    belt = {k: v["value"] for k, v in load_part("gt2-belt-6mm")["belt"].items()}
    f695 = load_part("bearing-f695")["dimensions"]["outside_diameter"]["value"]
    idler = load_part("gt2-idler-20t-6mm")["belt_engagement"]["pitch_diameter"]["value"]
    assert STACK_Y == pytest.approx(-(f695 / 2 + belt["back_side_offset"]))
    assert IDLER_Y == pytest.approx(idler / 2, abs=0.003)


def test_a_wrong_stack_height_breaks_the_joint():
    """A roof 1 mm low (a stack that does not fit its seat) fails closure."""
    joint = _joint()
    roof = joint["source"]["interfaces"][2]
    roof["frame"]["origin"][2] -= 1
    report = validate_assembly(_gantry_side(joint=joint), _resolver())
    assert not report.ok
    assert any(f.code == "closure" for f in report.errors), report.findings


def test_an_mgn12_block_does_not_run_on_an_mgn9_rail():
    report = validate_assembly(_gantry_side(block="mgn12h-carriage"), _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}


def test_a_part_for_the_mgn12_pattern_does_not_mount_on_an_mgn9_block():
    report = validate_assembly(_gantry_side(joint=_joint(carriage_size="mgn12-carriage")),
                               _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}


# ── (ii) the 6 mm toothed idler on its screw ──────────────────────────────────
@pytest.mark.parametrize("angle", [0, 90, 211])
def test_the_idler_spins_freely_on_its_screw(angle):
    doc = _gantry_side()
    for mate in doc["mates"]:
        if mate["id"] in ("idler_screw_in_joint", "idler_on_screw"):
            mate["angle_deg"] = angle
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    assert _height_above_c_top(report.placements, "idler", (0, 0, 4.5)) == pytest.approx(10 + HIGH)


def test_the_mirrored_joint_swaps_the_belt_levels():
    """The right hand: the stack carries the other belt, on the high level, the idler the low."""
    doc = _gantry_side(joint=_joint(stack_z=HIGH, idler_z=LOW), stack_journal=5.0,
                       idler_journal=14.5)
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    p = report.placements
    assert _height_above_c_top(p, "f695_1", (0, 0, 4)) == pytest.approx(10 + HIGH)
    assert _height_above_c_top(p, "idler", (0, 0, 4.5)) == pytest.approx(10 + LOW)


def test_a_belt_end_does_not_mate_a_pulley_bore():
    doc = _assembly(
        [_std("belt", "gt2-belt-6mm"), _std("idler", "gt2-idler-20t-6mm")],
        [_mate("m1", "belt.end_a", "idler.bore", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}


def test_the_new_parts_are_in_the_catalog():
    keys = set(hyperobjects_standard_parts.list_part_keys())
    assert set(NEW_PARTS) <= keys
    entries = {e["key"] for e in load_fabrication_vocabulary("interface-sizes")["entries"]}
    assert set(NEW_KEYS) <= entries
