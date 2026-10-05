"""The 350 build plate on its bed rails (lane P6-ZBED), proven by placement.

The plate (`bed-plate-350`, a class: 355 × 355 cast aluminium, 8–10 mm by maker) stands on
M4 thumb-nut spacers over the two bed extrusions, screwed into M3 T-nuts in their top slots
(Voron 2.4r2 build guide pp. 58–59). The bottom of the 350 frame cube (530 uprights, 470
horizontals by blind joints), the two 470 bed rails held by four `bed-extrusion-mount`
plates (framed as that commons cartridge frames itself at its defaults), four
`tnut-2020-m3` and the plate close with no warning. The hole positions along the rails are
not cited, so the plate's mount interfaces travel along their rail and the mates' offsets
set them (ASM-1 §9 v1.4).
"""

from __future__ import annotations

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
UPRIGHT, HORIZONTAL = 530, 470
#: The bed rails' station on the front and back horizontals: 255 − 65 − 20 (guide p. 20).
BED_STATION = 255 - 65 - 20
#: CONVENTION for these tests: the plate's holes 150 mm either side of its centre along a
#: rail (no listing publishes the hole pattern).
HOLE_Y = 150
#: The plate's centre along the rails: its front edge 38 behind the frame's front edge
#: (guide p. 60; the frame's front face is at y = −10), plus half the plate.
PLATE_CENTRE_Y = -10 + 38 + 355 / 2


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


def _mate(mid, a, b, **kw):
    (ca, ia), (cb, ib) = a.split("."), b.split(".")
    return {"id": mid, "a": {"component": ca, "interface": ia},
            "b": {"component": cb, "interface": ib}, **kw}


def _apply(matrix, point):
    return tuple(sum(matrix[r][c] * (list(point) + [1.0])[c] for c in range(4)) for r in range(3))


# bed-extrusion-mount (bed_mount) at its defaults; see that cartridge's README.
BED_MOUNT_FRAMES = (
    _iface("bed_mount_frame_key", "male", "tslot-2020-6mm", 2, [0, -10, 0], [0, 0, -1], [1, 0, 0]),
    _iface("bed_mount_bed_key", "male", "tslot-2020-6mm", 2, [0, 10, 0], [0, 0, -1], [0, 1, 0]),
)

_BOTTOM = (  # the bottom ring of the 350 cube, every mate rotation_index 0
    ("bx_front", HORIZONTAL, [("u0.blind_xp_a", "bx_front.end_a_blind")]),
    ("by_left", HORIZONTAL, [("u0.blind_yp_a", "by_left.end_a_blind")]),
    ("u1", UPRIGHT, [("bx_front.end_b_blind", "u1.blind_xn_a")]),
    ("u2", UPRIGHT, [("by_left.end_b_blind", "u2.blind_yn_a")]),
    ("by_right", HORIZONTAL, [("u1.blind_yp_a", "by_right.end_a_blind")]),
    ("bx_back", HORIZONTAL, [("u2.blind_xp_a", "bx_back.end_a_blind")]),
    ("u3", UPRIGHT, [("by_right.end_b_blind", "u3.blind_yn_a"),
                     ("bx_back.end_b_blind", "u3.blind_xn_a")]),
)


def _bed(plate_params=None, hole_y=HOLE_Y, plate_y=PLATE_CENTRE_Y):
    comps = [_std("u0", "extrusion-2020", length_mm=UPRIGHT)]
    mates = []
    for cid, length, pairs in _BOTTOM:
        params = {"length_mm": length}
        if cid in ("bx_front", "bx_back"):
            params["slot_station_mm"] = BED_STATION
        comps.append(_std(cid, "extrusion-2020", **params))
        mates += [_mate(f"{a.split('.')[0]}__{b.split('.')[0]}", a, b, rotation_index=0)
                  for a, b in pairs]
    for rail, end in (("rail_l", "a"), ("rail_r", "b")):
        comps.append(_std(rail, "extrusion-2020", length_mm=HORIZONTAL))
        for side, horiz, rail_slot in (("front", "bx_front", "slot_xp_a"),
                                       ("back", "bx_back", "slot_xp_b")):
            mount = f"{rail}_{side}_mount"
            rot = 0 if side == "front" else 1
            comps.append(_external(mount, *BED_MOUNT_FRAMES))
            mates += [
                _mate(f"{mount}_on_frame", f"{horiz}.slot_xp_{end}",
                      f"{mount}.bed_mount_frame_key", rotation_index=rot),
                _mate(f"{mount}_on_rail", f"{rail}.{rail_slot}", f"{mount}.bed_mount_bed_key",
                      rotation_index=rot),
            ]
    # Four M3 T-nuts in the rails' top slots, at the plate's holes: a rail's end A is at
    # y = 10 and its slot_xp_a station is 10, so a hole at world y sits at offset y − 20.
    comps.append(_std("plate", "bed-plate-350", **(plate_params or {})))
    for rail, side_x in (("rail_l", "left"), ("rail_r", "right")):
        for end, dy in (("front", -hole_y), ("back", hole_y)):
            nut = f"nut_{side_x}_{end}"
            comps.append(_std(nut, "tnut-2020-m3"))
            mates += [
                _mate(f"{nut}_in_slot", f"{rail}.slot_xp_a", f"{nut}.slot", rotation_index=0,
                      offset={"axis": "x", "value": plate_y + dy - 20}),
                _mate(f"plate_on_{nut}", f"{nut}.thread", f"plate.mount_{side_x}_{end}",
                      angle_deg=0, offset={"side": "b", "axis": "x", "value": dy}),
            ]
    return {"format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "bed-plate",
            "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
            "root": "u0", "components": comps, "mates": mates}


def test_the_plate_closes_on_four_t_nuts_in_the_bed_rails_with_no_warning():
    report = validate_assembly(_bed(), _resolver())
    assert report.ok, report.findings
    assert not [f for f in report.findings if f.severity == "warning"], report.findings
    p = report.placements
    # The rails run front to back at x 180 and 310, tops at z 20.
    assert _apply(p["rail_l"], (0, 0, 0)) == pytest.approx((180, 10, 10))
    # The plate is centred between them, its underside on the 9.5 mm spacers (z 29.5), its
    # front edge 38 behind the frame's front face (y −10 → 28), square to the frame.
    assert _apply(p["plate"], (0, 0, 0)) == pytest.approx((245, PLATE_CENTRE_Y, 29.5))
    assert _apply(p["plate"], (-177.5, -177.5, 0)) == pytest.approx((67.5, 28, 29.5))
    assert _apply(p["plate"], (177.5, 177.5, 9.525)) == pytest.approx((422.5, 383, 39.025))


def test_the_plate_is_inside_the_frame_and_clear_of_the_uprights():
    p = validate_assembly(_bed(), _resolver()).placements
    lo = _apply(p["plate"], (-177.5, -177.5, 0))
    hi = _apply(p["plate"], (177.5, 177.5, 0))
    # The uprights' inner faces are at 10 and 480 in x and y.
    assert 10 < lo[0] and hi[0] < 480 and 10 < lo[1] and hi[1] < 480


@pytest.mark.parametrize("thickness", [8, 10])
def test_a_thinner_or_thicker_plate_keeps_its_underside(thickness):
    p = validate_assembly(_bed({"thickness_mm": thickness}), _resolver()).placements
    assert _apply(p["plate"], (0, 0, 0))[2] == pytest.approx(29.5)
    assert _apply(p["plate"], (0, 0, thickness))[2] == pytest.approx(29.5 + thickness)


def test_a_taller_spacer_lifts_the_plate():
    p = validate_assembly(_bed({"standoff_mm": 12}), _resolver()).placements
    assert _apply(p["plate"], (0, 0, 0))[2] == pytest.approx(32)


def test_a_hole_station_that_disagrees_with_its_nut_breaks_closure():
    doc = _bed()
    for mate in doc["mates"]:
        if mate["id"] == "plate_on_nut_right_back":
            mate["offset"]["value"] = HOLE_Y + 1
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert any(f.code == "closure" for f in report.errors), report.findings


def test_a_hole_outside_the_plate_is_an_offset_error():
    report = validate_assembly(_bed(hole_y=180), _resolver())
    assert not report.ok
    assert any(f.code == "offset" for f in report.errors), report.findings


def test_the_plate_and_nut_facts_match_their_sources():
    plate = load_part("bed-plate-350")
    dims = plate["dimensions"]
    assert (dims["length"]["value"], dims["width"]["value"]) == (355, 355)
    assert sorted(d["value"] for k, d in dims.items() if k.startswith("thickness_")) == [
        8, 9.525, 10]
    thickness, standoff = plate["parameters"]
    assert (thickness["min"], thickness["default"], thickness["max"]) == (8, 9.525, 10)
    assert standoff["default"] == dims["spacer_height"]["value"] == 9.5
    assert dims["rail_spacing"]["value"] == 130
    nut = load_part("tnut-2020-m3")["dimensions"]
    assert (nut["thread"]["value"], nut["length"]["value"], nut["width"]["value"]) == (
        "M3", 15, 8)


def test_the_mounts_sit_on_the_rail_lines_under_the_spacers():
    plate = load_part("bed-plate-350")
    frames = interface_frames(plate, resolve_parameters(plate, {}))
    for iface, x in (("mount_left_front", -65), ("mount_right_back", 65)):
        assert frames[iface].origin == pytest.approx((x, 0, -9.5))
        assert frames[iface].normal == pytest.approx((0, 0, -1))
        assert frames[iface].x_axis == pytest.approx((0, 1, 0))


def test_an_m3_joint_does_not_mate_an_m5_nut():
    doc = {"format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "x",
           "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
           "root": "nut", "components": [_std("nut", "tnut-2020-m5"),
                                         _std("plate", "bed-plate-350")],
           "mates": [_mate("m1", "nut.thread", "plate.mount_left_front", angle_deg=0)]}
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}


def test_the_new_key_is_cited():
    entries = {e["key"]: e for e in load_fabrication_vocabulary("interface-sizes")["entries"]}
    entry = entries["m3-screw-joint"]
    assert entry["geometry_type"] == "bolt_pattern"
    assert set(entry["label"]) == set(entry["definition"]) == {"en", "es", "fr", "pt"}
