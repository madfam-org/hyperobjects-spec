"""The Z drive, the Z belt and the bed mount's hardware (lane P6-ZBED), proven by placement.

Voron 2.4r2 build guide (cited by page only) facts the catalog entries carry:

* belt drive assembly (pp. 32–34): a 5x60 D-cut shaft, three 625 bearings, a GT2 80-tooth
  pulley and a GT2 20-tooth 9 mm pulley on it, a GT2 188 mm loop to the motor;
* the motor (p. 38): a GT2 16-tooth pulley on each Z NEMA 17 (5:1 with the 80-tooth);
* the frame (pp. 19, 41–43): M5x10 BHCS into M5 T-nuts; the Z belt (p. 111): GT2, 9 mm.

Three chains close here, each against an ORIGINAL commons cartridge framed exactly as its
manifest frames it at its defaults (solid PRs of this lane):

(i)   the bottom corner: upright → two horizontals by blind joints → ``z-drive-housing``
      keyed into both bottom slots → T-nuts, M5x10 screws → three 625s → the shaft through
      all three (two cycles) → the 20-tooth Z pulley and the 80-tooth pulley → the NEMA 17
      on wall C → the 16-tooth pulley, coplanar with the 80-tooth;
(ii)  the same upright's top corner with ``corner-idler-bracket``: the Z idler and the Z
      pulley share one belt plane and one vertical, so the Z belt runs straight;
(iii) the gantry clamp ``z-belt-clamp`` on a 2020 face, and a 9 mm belt end in its jaw;
(iv)  the bed mount ``bed-extrusion-mount`` joining a bed extrusion's end to a frame
      horizontal;
(v)   the whole 350 frame cube at its cited cut lengths (530 uprights, 470 horizontals, by
      blind joints), with a Z drive at each bottom corner (diagonal corners one hand, the
      other two mirrored) and both bed rails held by four bed mounts.
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
NEW_KEYS = ("bearing-625-bore", "z-drive-pulley-hub-5mm", "z-belt-gt2-9mm-clamp")
NEW_PARTS = ("gt2-pulley-16t-5mm", "gt2-pulley-20t-9mm", "gt2-pulley-80t-5mm", "bearing-625",
             "shaft-5mm", "gt2-belt-9mm", "gt2-belt-loop-188mm", "bhcs-m5x10", "bhcs-m5x16")


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
        "format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "z-drive",
        "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
        "root": components[0]["id"], "components": components, "mates": mates,
    }


def _mate(mid, a, b, **kw):
    (ca, ia), (cb, ib) = a.split("."), b.split(".")
    return {"id": mid, "a": {"component": ca, "interface": ia},
            "b": {"component": cb, "interface": ib}, **kw}


def _apply(matrix, point):
    return tuple(sum(matrix[r][c] * (list(point) + [1.0])[c] for c in range(4)) for r in range(3))


def _axis(matrix):
    """A part's +z in the assembly frame."""
    return tuple(matrix[r][2] for r in range(3))


def _axis_x(matrix):
    """A part's +x in the assembly frame."""
    return tuple(matrix[r][0] for r in range(3))


# z-drive-housing (z_drive) at its defaults: belt_offset 13, belt_plane 17.5,
# center_distance 40.8, big_pulley_od 55 (shaft axis z = −(19 + 27.5) = −46.5),
# mount_pitch 20. Model frame: origin on the inside corner line at the bottom horizontals'
# slot height; +x along the horizontal it hangs under, +y into the frame, +z up (frame
# bottom at z = −10). Walls (README "Layout"): bearing openings at y = 17.5 + 13.65,
# 17.5 − 14.85 and 17.5 − 40.35, all facing +y; the motor face at y = 17.5 − 46.85.
ZA = -46.5
HOUSING_FRAMES = (
    _iface("z_drive_mount_a", "male", "m5-screw-joint", 0, [20, -10, -10], [0, 0, 1], [1, 0, 0]),
    _iface("z_drive_mount_b", "male", "m5-screw-joint", 0, [40, -10, -10], [0, 0, 1], [1, 0, 0]),
    _iface("z_drive_mount_a_head", "female", "m5-clearance-hole", 0, [20, -10, -14.5],
           [0, 0, -1], [1, 0, 0]),
    _iface("z_drive_mount_b_head", "female", "m5-clearance-hole", 0, [40, -10, -14.5],
           [0, 0, -1], [1, 0, 0]),
    _iface("z_drive_slot_key", "male", "tslot-2020-6mm", 2, [10, -10, -10], [0, 0, 1], [1, 0, 0]),
    _iface("z_drive_corner_key", "male", "tslot-2020-6mm", 2, [-10, 10, -10], [0, 0, 1],
           [0, 1, 0]),
    _iface("z_drive_bearing_a", "female", "bearing-625", 0, [13, 31.15, ZA], [0, 1, 0], [1, 0, 0]),
    _iface("z_drive_bearing_b", "female", "bearing-625", 0, [13, 2.65, ZA], [0, 1, 0], [1, 0, 0]),
    _iface("z_drive_bearing_c", "female", "bearing-625", 0, [13, -22.85, ZA], [0, 1, 0],
           [1, 0, 0]),
    _iface("z_drive_motor_face", "male", "nema-17-face", 4, [53.8, -29.35, ZA], [0, -1, 0],
           [1, 0, 0]),
)
#: The 16-tooth pulley goes on flange end first; its face B lands 6.85 off the motor face
#: so its belt mid-plane (12.85 from face A, 18 − 12.85 = 5.15 from face B) meets the
#: 80-tooth's at y = 17.5 − 34.85.
MOTOR_SEAT = 6.85


def _drive(housing_frames=HOUSING_FRAMES, motor_pulley_bore="bore_b", big_pulley_seat="hub_b"):
    housing = _external("housing", *housing_frames)
    mates = [
        _mate("h1_blind", "upright.blind_xp_a", "h1.end_a_blind", rotation_index=0),
        _mate("h2_blind", "upright.blind_yp_a", "h2.end_a_blind", rotation_index=3),
        _mate("housing_key_in_h1", "h1.slot_xn_a", "housing.z_drive_slot_key", rotation_index=0),
        _mate("housing_key_in_h2", "h2.slot_yp_a", "housing.z_drive_corner_key", rotation_index=0),
        _mate("tnut_a_on_housing", "housing.z_drive_mount_a", "tnut_a.thread", angle_deg=0),
        _mate("tnut_b_on_housing", "housing.z_drive_mount_b", "tnut_b.thread", angle_deg=0),
        _mate("screw_a_seat", "housing.z_drive_mount_a_head", "screw_a.head_seat", angle_deg=0),
        _mate("screw_b_seat", "housing.z_drive_mount_b_head", "screw_b.head_seat", angle_deg=0),
        _mate("bearing_a_seat", "housing.z_drive_bearing_a", "bearing_a.outer_race", angle_deg=0),
        _mate("bearing_b_seat", "housing.z_drive_bearing_b", "bearing_b.outer_race", angle_deg=0),
        _mate("bearing_c_seat", "housing.z_drive_bearing_c", "bearing_c.outer_race", angle_deg=0),
        _mate("shaft_in_a", "bearing_a.bore", "shaft.journal_a", angle_deg=0),
        _mate("shaft_in_b", "bearing_b.bore", "shaft.journal_b", angle_deg=0),
        _mate("shaft_in_c", "bearing_c.bore", "shaft.journal_c", angle_deg=0),
        _mate("z_pulley_on_shaft", "shaft.hub_a", "z_pulley.bore", angle_deg=0),
        _mate("big_pulley_on_shaft", f"shaft.{big_pulley_seat}", "big_pulley.bore", angle_deg=0),
        _mate("motor_on_housing", "housing.z_drive_motor_face", "motor.face", rotation_index=0),
        _mate("motor_pulley_on_motor", "motor.shaft", f"motor_pulley.{motor_pulley_bore}",
              angle_deg=0),
    ]
    return _assembly(
        [_std("upright", "extrusion-2020"), _std("h1", "extrusion-2020"),
         _std("h2", "extrusion-2020"), housing, _std("tnut_a", "tnut-2020-m5"),
         _std("tnut_b", "tnut-2020-m5"), _std("screw_a", "bhcs-m5x10"),
         _std("screw_b", "bhcs-m5x10"), _std("bearing_a", "bearing-625"),
         _std("bearing_b", "bearing-625"), _std("bearing_c", "bearing-625"),
         _std("shaft", "shaft-5mm"), _std("z_pulley", "gt2-pulley-20t-9mm"),
         _std("big_pulley", "gt2-pulley-80t-5mm"),
         _std("motor", "nema-17-48mm", shaft_seat_mm=MOTOR_SEAT),
         _std("motor_pulley", "gt2-pulley-16t-5mm")],
        mates,
    )


# ── vocabulary and catalog facts ──────────────────────────────────────────────
def test_the_new_size_keys_are_cited_and_typed():
    entries = {e["key"]: e for e in load_fabrication_vocabulary("interface-sizes")["entries"]}
    expected = {"bearing-625-bore": "socket", "z-drive-pulley-hub-5mm": "socket",
                "z-belt-gt2-9mm-clamp": "profile"}
    for key, gtype in expected.items():
        entry = entries[key]
        assert entry["geometry_type"] == gtype, key
        assert entry["sources"] and all(s["url"].startswith("https://") for s in entry["sources"])
        for dim in entry["dimensions"].values():
            assert 0 <= dim["source"] < len(entry["sources"]), key
        assert set(entry["label"]) == set(entry["definition"]) == {"en", "es", "fr", "pt"}


def test_the_new_parts_are_in_the_catalog():
    keys = set(hyperobjects_standard_parts.list_part_keys())
    assert set(NEW_PARTS) <= keys
    entries = {e["key"] for e in load_fabrication_vocabulary("interface-sizes")["entries"]}
    assert set(NEW_KEYS) <= entries


@pytest.mark.parametrize(("key", "teeth", "pd"), [
    ("gt2-pulley-16t-5mm", 16, 10.19), ("gt2-pulley-20t-9mm", 20, 12.73),
    ("gt2-pulley-80t-5mm", 80, 50.93)])
def test_every_pulley_states_a_cited_pitch_diameter_on_the_gt2_circle(key, teeth, pd):
    part = load_part(key)
    dims, engagement = part["dimensions"], part["belt_engagement"]
    assert dims["tooth_count"]["value"] == teeth
    assert dims["pitch"]["value"] == 2
    assert engagement["pitch_diameter"]["value"] == pd
    assert 0 <= engagement["pitch_diameter"]["source"] < len(part["sources"])
    # The cited pitch diameter is the 2 mm GT2 pitch circle of that many teeth.
    assert pd == pytest.approx(teeth * 2 / math.pi, abs=0.005)
    # The belt mid-plane lies on the bore axis, inside the pulley, between its end faces.
    assert engagement["axis"] == [0, 0, 1]
    assert engagement["center"][:2] == [0, 0]
    assert 0 < engagement["center"][2] < dims["overall_length"]["value"]


def test_the_reduction_is_five_to_one():
    """Guide pp. 33 and 38: an 80-tooth pulley driven by a 16-tooth one."""
    big = load_part("gt2-pulley-80t-5mm")["dimensions"]["tooth_count"]["value"]
    small = load_part("gt2-pulley-16t-5mm")["dimensions"]["tooth_count"]["value"]
    assert big / small == 5


def test_the_z_belt_states_the_belt_facts_a_path_reads():
    part = load_part("gt2-belt-9mm")
    assert part["category"] == "belt"
    dims = part["belt"]
    assert (dims["pitch"]["value"], dims["width"]["value"], dims["height"]["value"],
            dims["tooth_depth"]["value"]) == (2, 9, 1.52, 0.76)
    # The 9 mm belt is the width the Z idler and the Z pulley carry.
    for wheel in ("gt2-idler-20t-9mm", "gt2-pulley-20t-9mm"):
        assert dims["width"]["value"] == load_part(wheel)["dimensions"]["belt_width"]["value"]
    length = part["parameters"][0]
    assert (length["id"], length["default"]) == ("length_mm", 1200)   # guide p. 111, 350 spec


def test_the_bearing_and_the_shaft_match_their_datasheets():
    bearing = load_part("bearing-625")["dimensions"]
    assert [bearing[k]["value"] for k in ("bore", "outside_diameter", "width")] == [5, 16, 5]
    shaft = load_part("shaft-5mm")
    assert shaft["dimensions"]["diameter"]["value"] == 5
    length = shaft["parameters"][0]
    assert (length["default"], length["min"], length["max"]) == (60, 10, 400)


@pytest.mark.parametrize("length", [10, 16])
def test_the_short_button_heads_match_their_datasheets(length):
    dims = load_part(f"bhcs-m5x{length}")["dimensions"]
    assert (dims["head_diameter"]["value"], dims["head_height"]["value"],
            dims["length"]["value"]) == (9.5, 2.75, length)


def test_shaft_stations_follow_their_parameters():
    part = load_part("shaft-5mm")
    values = resolve_parameters(part, {"journal_b_mm": 30, "hub_b_mm": 40})
    frames = interface_frames(part, values)
    assert frames["journal_a"].origin == pytest.approx((0, 0, 5))
    assert frames["journal_b"].origin == pytest.approx((0, 0, 30))
    assert frames["hub_b"].origin == pytest.approx((0, 0, 40))
    assert frames["hub_a"].normal == pytest.approx((0, 0, -1))
    assert frames["hub_b"].normal == pytest.approx((0, 0, 1))


# ── (i) the bottom corner and the Z drive ─────────────────────────────────────
def test_the_z_drive_closes_and_places_every_part():
    report = validate_assembly(_drive(), _resolver())
    assert report.ok, report.findings
    assert len(report.mates) == 18 and all(m.ok for m in report.mates)
    p = report.placements
    # The horizontals butt the upright's faces with their bottoms flush with its end.
    assert _apply(p["h1"], (0, 0, 0)) == pytest.approx((10, 0, 10))
    assert _apply(p["h2"], (0, 0, 0)) == pytest.approx((0, 10, 10))
    # The housing's frame is the inside corner of the two bottom horizontals.
    assert _apply(p["housing"], (0, 0, 0)) == pytest.approx((10, 10, 10))
    assert _apply(p["housing"], (1, 2, 3)) == pytest.approx((11, 12, 13))
    # Both T-nuts in h1's bottom face (z = 0), 20 apart; the M5x10s pass 5.5 into them.
    assert _apply(p["tnut_a"], (0, 0, 0)) == pytest.approx((30, 0, 0))
    assert _apply(p["tnut_b"], (0, 0, 0)) == pytest.approx((50, 0, 0))
    assert _apply(p["screw_a"], (0, 0, 10)) == pytest.approx((30, 0, 5.5))
    # The shaft: end A flush with wall A's outer face, through all three bearings.
    assert _apply(p["shaft"], (0, 0, 0)) == pytest.approx((23, 41.15, -36.5))
    assert _apply(p["shaft"], (0, 0, 60)) == pytest.approx((23, -18.85, -36.5))
    for bearing, face_a_y in (("bearing_a", 41.15), ("bearing_b", 12.65), ("bearing_c", -12.85)):
        assert _apply(p[bearing], (0, 0, 0)) == pytest.approx((23, face_a_y, -36.5))
        assert _apply(p[bearing], (0, 0, 5)) == pytest.approx((23, face_a_y - 5, -36.5))


def test_the_z_pulley_runs_in_the_belt_plane():
    p = validate_assembly(_drive(), _resolver()).placements
    # Belt mid-plane 14.35 from the hub end: y = 10 + 17.5, on the shaft axis (x 23).
    assert _apply(p["z_pulley"], (0, 0, 14.35)) == pytest.approx((23, 27.5, -36.5))
    assert _axis(p["z_pulley"]) == pytest.approx((0, 1, 0))
    # The flanged end clears wall A by 0.5 (wall A inner face at 10 + 17.5 + 7.15).
    assert _apply(p["z_pulley"], (0, 0, 21))[1] == pytest.approx(10 + 17.5 + 6.65)


def test_the_reduction_pulleys_share_a_plane_at_the_centre_distance():
    p = validate_assembly(_drive(), _resolver()).placements
    big = _apply(p["big_pulley"], (0, 0, 13))
    small = _apply(p["motor_pulley"], (0, 0, 12.85))
    assert big[1] == pytest.approx(small[1], abs=1e-6) == pytest.approx(10 + 17.5 - 34.85)
    assert big[2] == pytest.approx(small[2])
    assert small[0] - big[0] == pytest.approx(40.8)
    # Axes parallel; the motor body hangs outside the frame (h1's outer face is y = −10).
    assert _axis(p["motor"]) == pytest.approx((0, 1, 0))
    assert _apply(p["motor"], (0, 0, -48))[1] < -10


def test_the_centre_distance_closes_a_188_mm_loop():
    """The housing's default 40.8 puts the 16/80-tooth loop within 0.05 mm of 188 (guide p. 34)."""
    big = load_part("gt2-pulley-80t-5mm")["belt_engagement"]["pitch_diameter"]["value"]
    small = load_part("gt2-pulley-16t-5mm")["belt_engagement"]["pitch_diameter"]["value"]
    centre = 40.8
    phi = math.asin((big - small) / (2 * centre))
    length = 2 * centre * math.cos(phi) + math.pi * (big + small) / 2 + phi * (big - small)
    assert length == pytest.approx(188, abs=0.05)


def test_the_reduction_loop_is_a_closed_188_mm_belt_with_no_interfaces():
    part = load_part("gt2-belt-loop-188mm")
    assert part["category"] == "belt" and part["interfaces"] == []
    belt = part["belt"]
    assert (belt["pitch"]["value"], belt["width"]["value"], belt["loop_length"]["value"]) == (
        2, 6, 188)
    # 94 teeth: the loop length over the pitch.
    assert part["dimensions"]["tooth_count"]["value"] == 188 / 2


def test_the_reduction_loop_path_closes_at_188_mm_with_no_warning():
    """ASM-1 §9: the 16 → 80-tooth loop declared as a closed path in the Z drive."""
    doc = _drive()
    doc["paths"] = [{"id": "z_reduction", "kind": "belt", "part": "gt2-belt-loop-188mm",
                     "closed": True, "via": ["motor_pulley", "big_pulley"]}]
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    (path,) = report.paths
    assert path.ok and path.closed
    assert path.loop_length_mm == 188
    assert path.length_mm == pytest.approx(188.006, abs=0.005)
    assert not [f for f in report.findings if f.code == "path-length"]


def test_a_reduction_loop_two_mm_off_its_centre_distance_warns():
    frames = [dict(f, frame=dict(f["frame"])) for f in HOUSING_FRAMES]
    for f in frames:
        if f["id"] == "z_drive_motor_face":
            f["frame"]["origin"] = [55.8, -29.35, ZA]
    doc = _drive(tuple(frames))
    doc["paths"] = [{"id": "z_reduction", "kind": "belt", "part": "gt2-belt-loop-188mm",
                     "closed": True, "via": ["motor_pulley", "big_pulley"]}]
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings      # a warning, not an error (a tensioner's choice)
    assert any(f.code == "path-length" for f in report.findings)
    # The open-belt formula at 42.8: L = 2C·cos φ + π(D + d)/2 + φ(D − d).
    big, small, centre = 50.93, 10.19, 42.8
    phi = math.asin((big - small) / (2 * centre))
    expected = 2 * centre * math.cos(phi) + math.pi * (big + small) / 2 + phi * (big - small)
    assert report.paths[0].length_mm == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize("angle", [0, 72, 301])
def test_the_shaft_turns_in_its_bearings(angle):
    doc = _drive()
    for mate in doc["mates"]:
        if mate["id"] in ("shaft_in_a", "shaft_in_b", "shaft_in_c"):
            mate["angle_deg"] = angle
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings


def test_a_bearing_seat_one_mm_off_breaks_the_shaft():
    frames = [dict(f, frame=dict(f["frame"])) for f in HOUSING_FRAMES]
    for f in frames:
        if f["id"] == "z_drive_bearing_b":
            f["frame"]["origin"] = [13, 3.65, ZA]
    report = validate_assembly(_drive(tuple(frames)), _resolver())
    assert not report.ok
    assert any(f.code == "closure" for f in report.errors), report.findings


def test_a_wrong_corner_station_breaks_the_housing():
    frames = [dict(f, frame=dict(f["frame"])) for f in HOUSING_FRAMES]
    for f in frames:
        if f["id"] == "z_drive_corner_key":
            f["frame"]["origin"] = [-11, 10, -10]
    report = validate_assembly(_drive(tuple(frames)), _resolver())
    assert not report.ok
    assert any(f.code == "closure" for f in report.errors), report.findings


def test_the_motor_pulley_does_not_mate_the_output_shaft():
    """A NEMA-bore pulley and a Z-shaft hub are two keys: no accidental swap."""
    doc = _assembly(
        [_std("shaft", "shaft-5mm"), _std("pulley", "gt2-pulley-16t-5mm")],
        [_mate("m1", "shaft.hub_a", "pulley.bore", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}


def test_the_80_tooth_pulley_does_not_mate_a_motor_shaft():
    doc = _assembly(
        [_std("motor", "nema-17-48mm"), _std("pulley", "gt2-pulley-80t-5mm")],
        [_mate("m1", "motor.shaft", "pulley.bore", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}


# ── (ii) one upright, both corners: the Z belt runs straight ──────────────────
# corner-idler-bracket (corner_idler) at its defaults, as test_catalog_m5_idlers frames it.
BRACKET_FRAMES = (
    _iface("corner_idler_mount_a", "male", "m5-screw-joint", 0, [10, 0, 0], [0, -1, 0], [1, 0, 0]),
    _iface("corner_idler_corner_key", "male", "tslot-2020-6mm", 2, [0, 10, 0], [-1, 0, 0],
           [0, 1, 0]),
    _iface("corner_idler_upright_key", "male", "tslot-2020-6mm", 2, [-10, 0, -20], [0, -1, 0],
           [0, 0, 1]),
    _iface("corner_idler_idler_bolt", "female", "m5-clearance-hole", 0, [13, 30, -24],
           [0, 1, 0], [1, 0, 0]),
)


def test_the_top_idler_and_the_z_pulley_share_the_belt_plane_and_vertical():
    doc = _drive()
    doc["components"][0]["source"]["parameters"] = {"length_mm": 530, "slot_station_mm": 30}
    doc["components"] += [
        _std("h1_top", "extrusion-2020"), _std("h2_top", "extrusion-2020"),
        _std("idler_tnut", "tnut-2020-m5"), _external("bracket", *BRACKET_FRAMES),
        _std("idler_axle", "bhcs-m5x30"), _std("idler", "gt2-idler-20t-9mm"),
    ]
    doc["mates"] += [
        _mate("h1_top_blind", "upright.blind_xp_b", "h1_top.end_a_blind", rotation_index=0),
        _mate("h2_top_blind", "upright.blind_yp_b", "h2_top.end_a_blind", rotation_index=3),
        _mate("idler_tnut_in_slot", "h1_top.slot_yn_a", "idler_tnut.slot", rotation_index=0),
        _mate("bracket_on_tnut", "idler_tnut.thread", "bracket.corner_idler_mount_a", angle_deg=0),
        _mate("bracket_key", "h2_top.slot_xp_a", "bracket.corner_idler_corner_key",
              rotation_index=0),
        _mate("bracket_heel", "upright.slot_yp_b", "bracket.corner_idler_upright_key",
              rotation_index=0),
        _mate("idler_axle_seat", "bracket.corner_idler_idler_bolt", "idler_axle.head_seat",
              angle_deg=0),
        _mate("idler_on_axle", "idler_axle.journal", "idler.bore", angle_deg=0),
    ]
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    p = report.placements
    idler_mid = _apply(p["idler"], (0, 0, 7))          # mid-width of the 14 mm idler
    pulley_mid = _apply(p["z_pulley"], (0, 0, 14.35))
    # One plane, one vertical: the axes coincide in x and y, so each strand is vertical.
    assert idler_mid[0] == pytest.approx(pulley_mid[0])
    assert idler_mid[1] == pytest.approx(pulley_mid[1])
    assert idler_mid[2] - pulley_mid[2] == pytest.approx((530 - 10 - 24) - (10 - 46.5))


# ── (iii) the gantry clamp and a Z belt end ──────────────────────────────────
# z-belt-clamp (z_belt_clamp) at its defaults: jaw_length 14, post_d 6, slot_w 2.4,
# base_t 3.5. Model frame: origin on the mount face on the screw axis, +x along the slot
# line, +z out of the extrusion face. End faces at x = ±(9.25 + (6 + 3.64)/2 + 14) =
# ±28.07; the belt's back bears on the wall y = −1.2; its mid-plane is 3.5 + 4.8 = 8.3 out.
CLAMP_X = 9.25 + (6 + 3.64) / 2 + 14
CLAMP_FRAMES = (
    _iface("z_belt_clamp_mount", "male", "m5-screw-joint", 0, [0, 0, 0], [0, 0, -1], [1, 0, 0]),
    _iface("z_belt_clamp_mount_head", "female", "m5-clearance-hole", 0, [0, 0, 4.5], [0, 0, 1],
           [1, 0, 0]),
    _iface("z_belt_clamp_key", "male", "tslot-2020-6mm", 2, [0, 0, 0], [0, 0, -1], [1, 0, 0]),
    _iface("z_belt_clamp_upper", "female", "z-belt-gt2-9mm-clamp", 2, [CLAMP_X, -1.2, 8.3],
           [1, 0, 0], [0, 0, 1]),
    _iface("z_belt_clamp_lower", "female", "z-belt-gt2-9mm-clamp", 2, [-CLAMP_X, -1.2, 8.3],
           [-1, 0, 0], [0, 0, 1]),
)


def _clamp(belt_jaw="z_belt_clamp_upper"):
    return _assembly(
        [_std("beam", "extrusion-2020", length_mm=300, slot_station_mm=150),
         _external("clamp", *CLAMP_FRAMES), _std("tnut", "tnut-2020-m5"),
         _std("screw", "bhcs-m5x10"), _std("belt", "gt2-belt-9mm")],
        [_mate("clamp_key", "beam.slot_xp_a", "clamp.z_belt_clamp_key", rotation_index=0),
         _mate("clamp_on_tnut", "clamp.z_belt_clamp_mount", "tnut.thread", angle_deg=0),
         _mate("clamp_screw", "clamp.z_belt_clamp_mount_head", "screw.head_seat", angle_deg=0),
         _mate("belt_in_jaw", f"clamp.{belt_jaw}", "belt.end_a", rotation_index=0)],
    )


def test_a_z_belt_end_closes_in_the_clamp_on_a_beam():
    report = validate_assembly(_clamp(), _resolver())
    assert report.ok, report.findings
    p = report.placements
    beam_face = _apply(p["beam"], (10, 0, 150))          # slot_xp_a at the 150 station
    clamp = _apply(p["clamp"], (0, 0, 0))
    assert clamp == pytest.approx(beam_face)
    # The belt leaves the upper jaw along the slot line, its back on the jaw's wall, its
    # mid-width 8.3 off the beam face: end A at the jaw entrance, end B 1200 mm on.
    entry = _apply(p["clamp"], (CLAMP_X, -1.2, 8.3))
    assert _apply(p["belt"], (0, 0, 0)) == pytest.approx(entry)
    far = _apply(p["clamp"], (CLAMP_X + 1200, -1.2, 8.3))
    assert _apply(p["belt"], (1200, 0, 0)) == pytest.approx(far)
    # Its width runs out of the beam face (clamp +z).
    edge = _apply(p["clamp"], (CLAMP_X, -1.2, 12.8))
    assert _apply(p["belt"], (0, 4.5, 0)) == pytest.approx(edge)


def test_both_jaws_hold_the_belt_on_one_line():
    upper = validate_assembly(_clamp("z_belt_clamp_upper"), _resolver()).placements
    lower = validate_assembly(_clamp("z_belt_clamp_lower"), _resolver()).placements
    a, b = _apply(upper["belt"], (0, 0, 0)), _apply(lower["belt"], (0, 0, 0))
    # The two entrances differ only along the slot line (the clamp's +x), by 2 × CLAMP_X.
    slot_line = tuple(upper["clamp"][r][0] for r in range(3))
    assert tuple(a[i] - b[i] for i in range(3)) == pytest.approx(
        tuple(2 * CLAMP_X * v for v in slot_line))
    # …and the belt leaves each jaw outward, away from the other.
    assert _axis_x(upper["belt"]) == pytest.approx(slot_line)
    assert _axis_x(lower["belt"]) == pytest.approx(tuple(-v for v in slot_line))


def test_a_belt_end_does_not_mate_a_slot():
    doc = _assembly(
        [_std("beam", "extrusion-2020"), _std("belt", "gt2-belt-9mm")],
        [_mate("m1", "beam.slot_xp_a", "belt.end_a", rotation_index=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}


# ── (iv) the bed extrusion mount ─────────────────────────────────────────────
# bed-extrusion-mount (bed_mount) at its defaults: screw_offset 14, stem_length 17.5,
# plate_t 4.5. Model frame: origin where the bed extrusion's centreline meets the
# horizontal's inner face, in the top faces' plane; +x along the horizontal, +y along the
# bed extrusion, +z up.
BED_MOUNT_FRAMES = (
    _iface("bed_mount_frame_a", "male", "m5-screw-joint", 0, [-14, -10, 0], [0, 0, -1], [1, 0, 0]),
    _iface("bed_mount_frame_b", "male", "m5-screw-joint", 0, [14, -10, 0], [0, 0, -1], [1, 0, 0]),
    _iface("bed_mount_bed", "male", "m5-screw-joint", 0, [0, 10, 0], [0, 0, -1], [1, 0, 0]),
    _iface("bed_mount_bed_head", "female", "m5-clearance-hole", 0, [0, 10, 4.5], [0, 0, 1],
           [1, 0, 0]),
    _iface("bed_mount_frame_key", "male", "tslot-2020-6mm", 2, [0, -10, 0], [0, 0, -1], [1, 0, 0]),
    _iface("bed_mount_bed_key", "male", "tslot-2020-6mm", 2, [0, 10, 0], [0, 0, -1], [0, 1, 0]),
)


def _bed(bed_station=10):
    return _assembly(
        [_std("upright", "extrusion-2020"), _std("h1", "extrusion-2020", length_mm=470),
         _external("mount", *BED_MOUNT_FRAMES),
         _std("bed_rail", "extrusion-2020", length_mm=470, slot_station_mm=bed_station),
         _std("tnut_a", "tnut-2020-m5"), _std("tnut_b", "tnut-2020-m5"),
         _std("tnut_bed", "tnut-2020-m5"), _std("screw_bed", "bhcs-m5x10")],
        [_mate("h1_blind", "upright.blind_xp_a", "h1.end_a_blind", rotation_index=0),
         _mate("mount_key_on_h1", "h1.slot_xp_a", "mount.bed_mount_frame_key", rotation_index=0),
         _mate("mount_key_on_bed", "bed_rail.slot_xp_a", "mount.bed_mount_bed_key",
               rotation_index=0),
         _mate("tnut_a_on_mount", "mount.bed_mount_frame_a", "tnut_a.thread", angle_deg=0),
         _mate("tnut_b_on_mount", "mount.bed_mount_frame_b", "tnut_b.thread", angle_deg=0),
         _mate("tnut_bed_on_mount", "mount.bed_mount_bed", "tnut_bed.thread", angle_deg=0),
         _mate("screw_bed_seat", "mount.bed_mount_bed_head", "screw_bed.head_seat", angle_deg=0)],
    )


def test_the_bed_mount_holds_a_bed_extrusion_square_flush_and_butted():
    report = validate_assembly(_bed(), _resolver())
    assert report.ok, report.findings
    p = report.placements
    # h1 runs along +x at z = 10 (top face z = 20, inner face y = 10); the mount sits on
    # its top slot at the 10 station.
    assert _apply(p["mount"], (0, 0, 0)) == pytest.approx((20, 10, 20))
    # The bed extrusion: end A butts h1's inner face, axis along +y, top flush (z 20).
    assert _apply(p["bed_rail"], (0, 0, 0)) == pytest.approx((20, 10, 10))
    assert _apply(p["bed_rail"], (0, 0, 470)) == pytest.approx((20, 480, 10))
    assert _apply(p["bed_rail"], (10, 0, 0))[2] == pytest.approx(20)
    # The bed screw passes 5.5 below the plate into the bed extrusion's T-nut.
    assert _apply(p["screw_bed"], (0, 0, 10)) == pytest.approx((20, 20, 14.5))


def test_a_bed_extrusion_off_its_station_moves_with_it():
    """The bed key fixes the butt: a slot station of 12 pulls end A 2 mm into h1."""
    p = validate_assembly(_bed(bed_station=12), _resolver()).placements
    assert _apply(p["bed_rail"], (0, 0, 0)) == pytest.approx((20, 8, 10))


# ── (v) the 350 frame cube, its four Z drives and the bed rails ──────────────
# Frame-cube lengths for the 350 build (no catalog entry: extrusion-2020.length_mm). The
# guide counts the extrusions without lengths (p. 13: A × 10, B × 4) and gives half the
# printer width (p. 20: 255 for the 350, so 510 = 470 + 2 × 20); two kit listings (Spool3D's
# Voron 2.4r2 extrusion kit; the LDO V2.4 frame kit) give B = 530 (×4) and A = 470 (×10: the
# eight frame horizontals and the two bed extrusions).
UPRIGHT, HORIZONTAL = 530, 470
#: The bed extrusions are 130 apart on the centreline (p. 20): 255 − 65 − 20 = 170 from
#: either end of a front or back horizontal.
BED_STATION = 255 - 65 - 20

_CUBE = (  # (component, length, mates: (a, b) with rotation_index 0)
    ("bx_front", HORIZONTAL, [("u0.blind_xp_a", "bx_front.end_a_blind")]),
    ("by_left", HORIZONTAL, [("u0.blind_yp_a", "by_left.end_a_blind")]),
    ("u1", UPRIGHT, [("bx_front.end_b_blind", "u1.blind_xn_a")]),
    ("u2", UPRIGHT, [("by_left.end_b_blind", "u2.blind_yn_a")]),
    ("by_right", HORIZONTAL, [("u1.blind_yp_a", "by_right.end_a_blind")]),
    ("bx_back", HORIZONTAL, [("u2.blind_xp_a", "bx_back.end_a_blind")]),
    ("u3", UPRIGHT, [("by_right.end_b_blind", "u3.blind_yn_a"),
                     ("bx_back.end_b_blind", "u3.blind_xn_a")]),
    ("tx_front", HORIZONTAL, [("u0.blind_xp_b", "tx_front.end_a_blind"),
                              ("tx_front.end_b_blind", "u1.blind_xn_b")]),
    ("ty_left", HORIZONTAL, [("u0.blind_yp_b", "ty_left.end_a_blind"),
                             ("ty_left.end_b_blind", "u2.blind_yn_b")]),
    ("ty_right", HORIZONTAL, [("u1.blind_yp_b", "ty_right.end_a_blind"),
                              ("ty_right.end_b_blind", "u3.blind_yn_b")]),
    ("tx_back", HORIZONTAL, [("u2.blind_xp_b", "tx_back.end_a_blind"),
                             ("tx_back.end_b_blind", "u3.blind_xn_b")]),
)
#: corner: (y-running bottom horizontal, its bottom slot at this corner, mirrored, key
#: rotation). The drive keys only into the y-running horizontal: the x-running ones carry
#: the bed rails' station (one slot_station_mm per extrusion).
_DRIVES = {
    "z0": ("by_left", "slot_xn_a", False, 0),
    "z1": ("by_right", "slot_xn_a", True, 0),
    "z2": ("by_left", "slot_xn_b", True, 1),
    "z3": ("by_right", "slot_xn_b", False, 1),
}
_DRIVE_PARTS = (
    ("tnut_a", "tnut-2020-m5", {}), ("tnut_b", "tnut-2020-m5", {}),
    ("screw_a", "bhcs-m5x10", {}), ("screw_b", "bhcs-m5x10", {}),
    ("bearing_a", "bearing-625", {}), ("bearing_b", "bearing-625", {}),
    ("bearing_c", "bearing-625", {}), ("shaft", "shaft-5mm", {}),
    ("z_pulley", "gt2-pulley-20t-9mm", {}), ("big_pulley", "gt2-pulley-80t-5mm", {}),
    ("motor", "nema-17-48mm", {"shaft_seat_mm": MOTOR_SEAT}),
    ("motor_pulley", "gt2-pulley-16t-5mm", {}),
)


def _housing_frames(mirrored):
    """z-drive-housing's frames at its defaults; `mirrored` negates every origin's x."""
    out = []
    for f in HOUSING_FRAMES:
        origin = list(f["frame"]["origin"])
        if mirrored:
            origin[0] = -origin[0]
        out.append(dict(f, frame=dict(f["frame"], origin=origin)))
    return out


def _cube(horizontal=HORIZONTAL, bed_rail=HORIZONTAL):
    comps = [_std("u0", "extrusion-2020", length_mm=UPRIGHT)]
    mates = []
    for cid, length, pairs in _CUBE:
        length = horizontal if length == HORIZONTAL else length
        params = {"length_mm": length}
        if cid in ("bx_front", "bx_back"):
            params["slot_station_mm"] = BED_STATION
        comps.append(_std(cid, "extrusion-2020", **params))
        mates += [_mate(f"{a.split('.')[0]}__{b.split('.')[0]}", a, b, rotation_index=0)
                  for a, b in pairs]
    # Four Z drives: the bottom-corner chain of _drive(), keyed into the y horizontal.
    corner_only = ("h1_blind", "h2_blind", "housing_key_in_h1", "housing_key_in_h2")
    template = [m for m in _drive()["mates"] if m["id"] not in corner_only]
    for z, (h2, slot, mirrored, rotation) in _DRIVES.items():
        comps.append(_external(f"{z}_housing", *_housing_frames(mirrored)))
        comps += [_std(f"{z}_{n}", key, **kw) for n, key, kw in _DRIVE_PARTS]
        mates.append(_mate(f"{z}_key", f"{h2}.{slot}", f"{z}_housing.z_drive_corner_key",
                           rotation_index=rotation))
        for m in template:
            a = f"{z}_{m['a']['component']}.{m['a']['interface']}"
            b = f"{z}_{m['b']['component']}.{m['b']['interface']}"
            extra = {k: v for k, v in m.items() if k not in ("id", "a", "b")}
            mates.append(_mate(f"{z}_{m['id']}", a, b, **extra))
    # Two bed rails, each held at both ends by a bed mount on the front and back
    # horizontals' top slots (the back mounts turned 180°, stem toward the front): a
    # closed cycle through the whole bottom frame.
    for rail, end in (("rail_l", "a"), ("rail_r", "b")):
        comps.append(_std(rail, "extrusion-2020", length_mm=bed_rail))
        for side, horiz, rail_slot in (("front", "bx_front", "slot_xp_a"),
                                       ("back", "bx_back", "slot_xp_b")):
            mount = f"{rail}_{side}_mount"
            comps.append(_external(mount, *BED_MOUNT_FRAMES))
            mates += [
                _mate(f"{mount}_on_frame", f"{horiz}.slot_xp_{end}",
                      f"{mount}.bed_mount_frame_key", rotation_index=0),
                _mate(f"{mount}_on_rail", f"{rail}.{rail_slot}", f"{mount}.bed_mount_bed_key",
                      rotation_index=0 if side == "front" else 1),
            ]
    return _assembly(comps, mates)


def test_the_350_cube_with_four_z_drives_and_the_bed_rails_closes():
    report = validate_assembly(_cube(), _resolver())
    assert report.ok, report.findings
    p = report.placements
    # Uprights at the four corners of a 510 × 510 outer frame (axes 490 apart), 530 tall.
    for u, (x, y) in {"u1": (490, 0), "u2": (0, 490), "u3": (490, 490)}.items():
        assert _apply(p[u], (0, 0, 0)) == pytest.approx((x, y, 0))
        assert _apply(p[u], (0, 0, UPRIGHT)) == pytest.approx((x, y, UPRIGHT))
    assert _apply(p["tx_back"], (0, 0, 0)) == pytest.approx((10, 490, UPRIGHT - 10))
    # Each Z pulley's belt mid-plane sits 13 in from its corner and 17.5 into the frame;
    # diagonal corners share a hand, adjacent ones are mirrored (guide p. 47).
    for z, (x, y) in {"z0": (23, 27.5), "z1": (467, 27.5), "z2": (23, 462.5),
                      "z3": (467, 462.5)}.items():
        assert _apply(p[f"{z}_z_pulley"], (0, 0, 14.35)) == pytest.approx((x, y, -36.5))
    # Every motor hangs outside the frame, front or back.
    for z in ("z0", "z1"):
        assert _apply(p[f"{z}_motor"], (0, 0, -48))[1] < -10
    for z in ("z2", "z3"):
        assert _apply(p[f"{z}_motor"], (0, 0, -48))[1] > 500
    # The bed rails run front to back, 130 apart on the centreline (x 245 ± 65), tops flush.
    assert _apply(p["rail_l"], (0, 0, 0)) == pytest.approx((180, 10, 10))
    assert _apply(p["rail_l"], (0, 0, HORIZONTAL)) == pytest.approx((180, 480, 10))
    assert _apply(p["rail_r"], (0, 0, 0))[0] == pytest.approx(310)


@pytest.mark.parametrize("given", [{"horizontal": 471}, {"bed_rail": 469}])
def test_a_wrong_cut_length_does_not_close_the_cube(given):
    report = validate_assembly(_cube(**given), _resolver())
    assert not report.ok
    assert any(f.code == "closure" for f in report.errors), report.findings
