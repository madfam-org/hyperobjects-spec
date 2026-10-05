"""M5 idler hardware and the 2020 blind joint (lane P4-AUTH-E), proven by placement.

Owner instruction 2026-10-04: catalog a GT2 20-tooth idler and the M5 screws a Voron
2.4-class printer turns its idlers on, a Z-idler corner bracket's hardware, and the F695 +
shim stack on an M5 screw. The Voron 2.4r2 build guide (cited by page only) names the parts:

* Z idler (pp. 48–49): a GT2 20-tooth 9 mm idler on an M5x30 BHCS, the bracket fixed by two
  M5 T-nuts to a top extrusion and pressed into the top corner;
* A/B and XY idlers (pp. 65, 69, 97, 99): shim, F695, F695, shim on an M5x40 SHCS, flanges
  outward;
* the frame (pp. 10, 14, 15): blind joints, an M5x16 BHCS in each tapped end of the
  horizontal extrusions, its head in the upright's slot.

Two chains close here:

(i) the top corner: upright → two horizontals by blind joints → T-nut in the horizontal's
    slot → bracket (also keyed into the other horizontal's slot and the upright's slot) →
    M5x30 → idler. The bracket is framed exactly as the commons cartridge
    ``corner-idler-bracket`` frames it at its defaults (solid PR of this lane).
(ii) M5x40 → shim → F695 → F695 → shim, between two walls of a printed host.
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
NEW_KEYS = ("m5-bolt-axle", "m5-clearance-hole", "m5-screw-joint", "m5-axle-stack-face",
            "bearing-f695", "tslot-2020-blind-joint-m5")
NEW_PARTS = ("bhcs-m5x30", "shcs-m5x40", "gt2-idler-20t-9mm", "bearing-f695", "shim-5x10",
             "tnut-2020-m5")


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
        "format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "m5-idlers",
        "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
        "root": components[0]["id"], "components": components, "mates": mates,
    }


def _mate(mid, a, b, **kw):
    (ca, ia), (cb, ib) = a.split("."), b.split(".")
    return {"id": mid, "a": {"component": ca, "interface": ia},
            "b": {"component": cb, "interface": ib}, **kw}


def _apply(matrix, point):
    return tuple(sum(matrix[r][c] * (list(point) + [1.0])[c] for c in range(4)) for r in range(3))


# corner-idler-bracket (corner_idler) at its defaults. Model frame: origin on the inside
# corner line at the top horizontals' slot height; +x along the horizontal it mounts on,
# +y out of that horizontal's inner face, +z up (the frame top at z = 10). Mount holes at
# x = 10 and 30; the M5x30 heads seat 24.5 from the mount face; the bracket is 30 deep
# (the M5x30's length); the idler axis at x 13, z −24; the heel key at x −10, z −20.
BRACKET = _external(
    "bracket",
    _iface("corner_idler_mount_a", "male", "m5-screw-joint", 0, [10, 0, 0], [0, -1, 0], [1, 0, 0]),
    _iface("corner_idler_mount_b", "male", "m5-screw-joint", 0, [30, 0, 0], [0, -1, 0], [1, 0, 0]),
    _iface("corner_idler_mount_a_head", "female", "m5-clearance-hole", 0, [10, 24.5, 0],
           [0, 1, 0], [1, 0, 0]),
    _iface("corner_idler_corner_key", "male", "tslot-2020-6mm", 2, [0, 10, 0], [-1, 0, 0],
           [0, 1, 0]),
    _iface("corner_idler_upright_key", "male", "tslot-2020-6mm", 2, [-10, 0, -20], [0, -1, 0],
           [0, 0, 1]),
    _iface("corner_idler_idler_bolt", "female", "m5-clearance-hole", 0, [13, 30, -24],
           [0, 1, 0], [1, 0, 0]),
)


def _corner(upright_params=None, bracket=BRACKET, with_upright_key=True):
    upright = {"slot_station_mm": 30, **(upright_params or {})}
    mates = [
        _mate("h1_blind", "upright.blind_xp_b", "h1.end_a_blind", rotation_index=0),
        _mate("h2_blind", "upright.blind_yp_b", "h2.end_a_blind", rotation_index=3),
        _mate("tnut_a_in_slot", "h1.slot_yn_a", "tnut_a.slot", rotation_index=0),
        _mate("bracket_on_tnut_a", "tnut_a.thread", "bracket.corner_idler_mount_a", angle_deg=0),
        _mate("bracket_key_in_h2", "h2.slot_xp_a", "bracket.corner_idler_corner_key",
              rotation_index=0),
        _mate("tnut_b_on_bracket", "bracket.corner_idler_mount_b", "tnut_b.thread", angle_deg=0),
        _mate("mount_screw_a", "bracket.corner_idler_mount_a_head", "mount_screw_a.head_seat",
              angle_deg=0),
        _mate("axle_screw", "bracket.corner_idler_idler_bolt", "axle.head_seat", angle_deg=0),
        _mate("idler_on_axle", "axle.journal", "idler.bore", angle_deg=0),
    ]
    if with_upright_key:
        mates.insert(5, _mate("bracket_heel_in_upright", "upright.slot_yp_b",
                              "bracket.corner_idler_upright_key", rotation_index=0))
    return _assembly(
        [_std("upright", "extrusion-2020", **upright), _std("h1", "extrusion-2020"),
         _std("h2", "extrusion-2020"), _std("tnut_a", "tnut-2020-m5"), bracket,
         _std("tnut_b", "tnut-2020-m5"), _std("mount_screw_a", "bhcs-m5x30"),
         _std("axle", "bhcs-m5x30"), _std("idler", "gt2-idler-20t-9mm")],
        mates,
    )


# ── vocabulary and catalog facts ──────────────────────────────────────────────
def test_the_new_size_keys_are_cited_and_typed():
    entries = {e["key"]: e for e in load_fabrication_vocabulary("interface-sizes")["entries"]}
    expected = {"m5-bolt-axle": "socket", "m5-clearance-hole": "socket",
                "m5-screw-joint": "bolt_pattern", "m5-axle-stack-face": "surface",
                "bearing-f695": "socket", "tslot-2020-blind-joint-m5": "profile"}
    for key, gtype in expected.items():
        entry = entries[key]
        assert entry["geometry_type"] == gtype, key
        assert entry["sources"] and all(s["url"].startswith("https://") for s in entry["sources"])
        for dim in entry["dimensions"].values():
            assert 0 <= dim["source"] < len(entry["sources"]), key
        assert set(entry["label"]) == set(entry["definition"]) == {"en", "es", "fr", "pt"}


def test_the_part_facts_match_their_datasheets():
    bhcs, shcs = load_part("bhcs-m5x30")["dimensions"], load_part("shcs-m5x40")["dimensions"]
    assert (bhcs["head_diameter"]["value"], bhcs["head_height"]["value"],
            bhcs["length"]["value"]) == (9.5, 2.75, 30)        # ISO 7380-1 M5x30
    assert (shcs["head_diameter"]["value"], shcs["head_height"]["value"],
            shcs["length"]["value"], shcs["thread_length"]["value"]) == (8.5, 5, 40, 22)
    f695 = load_part("bearing-f695")["dimensions"]
    assert [f695[k]["value"] for k in ("bore", "outside_diameter", "width", "flange_diameter",
                                       "flange_width")] == [5, 13, 4, 15, 1]
    shim = load_part("shim-5x10")
    assert (shim["dimensions"]["inner_diameter"]["value"],
            shim["dimensions"]["outer_diameter"]["value"]) == (5, 10)
    thickness = shim["parameters"][0]
    assert (thickness["min"], thickness["max"]) == (
        shim["dimensions"]["thickness_min"]["value"], shim["dimensions"]["thickness_max"]["value"])
    idler = load_part("gt2-idler-20t-9mm")
    assert [idler["dimensions"][k]["value"] for k in ("tooth_count", "bore", "belt_width",
                                                      "outside_diameter")] == [20, 5, 9, 18]
    assert idler["parameters"][0]["default"] == idler["dimensions"]["overall_width_gates"]["value"]
    tnut = load_part("tnut-2020-m5")["dimensions"]
    assert (tnut["thread"]["value"], tnut["length"]["value"], tnut["width"]["value"]) == (
        "M5", 15, 8)


def test_the_extrusion_keeps_its_ten_interfaces_and_gains_ten_blind_ones():
    part = load_part("extrusion-2020")
    ids = [i["id"] for i in part["interfaces"]]
    assert ids[:10] == ["end_a", "end_b", "slot_xp_a", "slot_xp_b", "slot_xn_a", "slot_xn_b",
                        "slot_yp_a", "slot_yp_b", "slot_yn_a", "slot_yn_b"]
    assert ids[10:] == ["end_a_blind", "end_b_blind"] + [
        f"blind_{f}_{e}" for f in ("xp", "xn", "yp", "yn") for e in ("a", "b")]
    for iface in part["interfaces"][10:]:
        assert iface["size_key"] == "tslot-2020-blind-joint-m5"
        assert iface["symmetry"] == 4
        assert iface["polarity"] == ("male" if iface["id"].startswith("end_") else "female")


@pytest.mark.parametrize("given", [{}, {"length_mm": 200, "blind_station_mm": 40}])
def test_blind_stations_sit_on_the_face_centrelines(given):
    part = load_part("extrusion-2020")
    values = resolve_parameters(part, given)
    frames = interface_frames(part, values)
    s, length = values["blind_station_mm"], values["length_mm"]
    assert frames["blind_xp_a"].origin == pytest.approx((10, 0, s))
    assert frames["blind_yn_b"].origin == pytest.approx((0, -10, length - s))
    assert frames["blind_yn_b"].normal == pytest.approx((0, -1, 0))
    assert frames["end_b_blind"].origin == pytest.approx((0, 0, length))
    # The blind end shares its frame with the tapped end: the same face, another joint.
    assert frames["end_a_blind"].origin == frames["end_a"].origin
    assert frames["end_a_blind"].normal == frames["end_a"].normal


# ── (i) the top corner, the Z-idler bracket and its idler ─────────────────────
def test_the_top_corner_closes_and_places_every_part():
    report = validate_assembly(_corner(), _resolver())
    assert report.ok, report.findings
    assert all(m.ok for m in report.mates) and len(report.mates) == 10
    p = report.placements
    # The horizontals butt the upright's faces with their tops flush with its top (z 350).
    assert _apply(p["h1"], (0, 0, 0)) == pytest.approx((10, 0, 340))
    assert _apply(p["h1"], (0, 0, 350)) == pytest.approx((360, 0, 340))
    assert _apply(p["h2"], (0, 0, 0)) == pytest.approx((0, 10, 340))
    assert _apply(p["h2"], (0, 0, 350)) == pytest.approx((0, 360, 340))
    # The bracket's corner is the inside corner of the two horizontals; its body runs
    # along h1 and into the frame, top flush with the frame top.
    assert _apply(p["bracket"], (0, 0, 0)) == pytest.approx((10, 10, 340))
    assert _apply(p["bracket"], (40, 30, 10)) == pytest.approx((50, 40, 350))
    # The heel reaches past the corner over the upright's inner face, below h2.
    assert _apply(p["bracket"], (-18, 0, -31)) == pytest.approx((-8, 10, 309))
    # Both T-nuts sit on h1's inner face (y = 10), 20 apart along it.
    assert _apply(p["tnut_a"], (0, 0, 0)) == pytest.approx((20, 10, 340))
    assert _apply(p["tnut_b"], (0, 0, 0)) == pytest.approx((40, 10, 340))
    # The mount screw's head seats 24.5 off the face, so 5.5 of its 30 mm passes the face.
    assert _apply(p["mount_screw_a"], (0, 0, 30)) == pytest.approx((20, 4.5, 340))
    # The axle screw enters from the inside face; its tip ends on the mount plane.
    assert _apply(p["axle"], (0, 0, 0)) == pytest.approx((23, 40, 316))
    assert _apply(p["axle"], (0, 0, 30)) == pytest.approx((23, 10, 316))
    # The idler sits between the arms with 0.5 mm each side (pocket y 20 … 35).
    assert _apply(p["idler"], (0, 0, 0)) == pytest.approx((23, 34.5, 316))
    assert _apply(p["idler"], (0, 0, 14)) == pytest.approx((23, 20.5, 316))


@pytest.mark.parametrize("angle", [0, 90, 211])
def test_the_idler_spins_freely_on_its_screw(angle):
    doc = _corner()
    for mate in doc["mates"]:
        if mate["id"] in ("axle_screw", "idler_on_axle"):
            mate["angle_deg"] = angle
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    assert _apply(report.placements["idler"], (0, 0, 0)) == pytest.approx((23, 34.5, 316))


def test_a_butt_joint_off_its_station_no_longer_validates():
    """P4-ASM2 finding 2: a butt joint driven into the upright validated with exit 0.
    With blind-joint mates, moving the joint by 1 mm breaks the corner's closure."""
    report = validate_assembly(_corner({"blind_station_mm": 11}), _resolver())
    assert not report.ok
    assert any(f.code == "closure" for f in report.errors), report.findings


def test_the_heel_is_what_checks_the_upright():
    """Without the heel mate the same 1 mm error closes: the bracket rides with h1."""
    report = validate_assembly(_corner({"blind_station_mm": 11}, with_upright_key=False),
                               _resolver())
    assert report.ok, report.findings


def test_a_blind_end_does_not_mate_a_slot():
    doc = _assembly(
        [_std("upright", "extrusion-2020"), _std("h1", "extrusion-2020")],
        [_mate("m1", "upright.slot_xp_b", "h1.end_a_blind", rotation_index=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}


def test_a_tnut_does_not_take_the_idler_screw_head():
    """The clearance hole and the screw joint are two keys: a screw's head never seats in a nut."""
    doc = _assembly(
        [_std("tnut", "tnut-2020-m5"), _std("screw", "bhcs-m5x30")],
        [_mate("m1", "tnut.thread", "screw.head_seat", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}


# ── (ii) the F695 stack on an M5x40 ───────────────────────────────────────────
# A printed idler body: a lower wall 5 thick with a clearance hole (the head on its
# outside face, z = 0) and an upper wall whose inside face is `gap` above the lower's.
def _host(gap):
    return _external(
        "host",
        _iface("bolt_hole", "female", "m5-clearance-hole", 0, [0, 0, 0], [0, 0, -1], [1, 0, 0]),
        _iface("lower_face", "neutral", "m5-axle-stack-face", 0, [0, 0, 5], [0, 0, 1], [1, 0, 0]),
        _iface("upper_face", "neutral", "m5-axle-stack-face", 0, [0, 0, 5 + gap], [0, 0, -1],
               [1, 0, 0]),
    )


def _stack(gap=10, shim_mm=1):
    return _assembly(
        [_host(gap), _std("screw", "shcs-m5x40"),
         _std("shim_1", "shim-5x10", thickness_mm=shim_mm), _std("f695_1", "bearing-f695"),
         _std("f695_2", "bearing-f695"), _std("shim_2", "shim-5x10", thickness_mm=shim_mm)],
        [_mate("screw_in_host", "host.bolt_hole", "screw.head_seat", angle_deg=0),
         _mate("shim_1_on_screw", "screw.journal", "shim_1.bore", angle_deg=0),
         _mate("shim_1_on_host", "host.lower_face", "shim_1.face_a", angle_deg=0),
         _mate("f695_1_on_shim", "shim_1.face_b", "f695_1.flange_face", angle_deg=0),
         _mate("back_to_back", "f695_1.plain_face", "f695_2.plain_face", angle_deg=0),
         _mate("shim_2_on_f695", "f695_2.flange_face", "shim_2.face_a", angle_deg=0),
         _mate("stack_to_upper_wall", "shim_2.face_b", "host.upper_face", angle_deg=0)],
    )


def test_the_f695_stack_closes_flanges_outward():
    report = validate_assembly(_stack(), _resolver())
    assert report.ok, report.findings
    assert len(report.mates) == 7 and all(m.ok for m in report.mates)
    p = report.placements
    # Head under the lower wall; the shank runs up through the stack.
    assert _apply(p["screw"], (0, 0, 40)) == pytest.approx((0, 0, 40))
    # shim 5..6, F695 6..10 with its flange (0..1 in its frame) at the bottom,
    # F695 10..14 with its flange at the top, shim 14..15, the upper wall at 15.
    assert _apply(p["shim_1"], (0, 0, 0))[2] == pytest.approx(5)
    assert _apply(p["f695_1"], (0, 0, 0))[2] == pytest.approx(6)
    assert _apply(p["f695_1"], (0, 0, 1))[2] == pytest.approx(7)       # flange underside
    assert _apply(p["f695_2"], (0, 0, 0))[2] == pytest.approx(14)      # flange face, top
    assert _apply(p["f695_2"], (0, 0, 1))[2] == pytest.approx(13)
    assert _apply(p["shim_2"], (0, 0, 1))[2] == pytest.approx(15)


def test_a_thicker_shim_does_not_fit_the_same_host():
    report = validate_assembly(_stack(shim_mm=1.5), _resolver())
    assert not report.ok
    assert any(f.code == "closure" for f in report.errors), report.findings
    # …and does once the walls move with it.
    assert validate_assembly(_stack(gap=11, shim_mm=1.5), _resolver()).ok


def test_an_f695_bore_does_not_seat_in_the_host_hole():
    doc = _assembly(
        [_host(10), _std("f695", "bearing-f695")],
        [_mate("m1", "host.bolt_hole", "f695.bore", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}


def test_the_new_parts_are_in_the_catalog():
    keys = set(hyperobjects_standard_parts.list_part_keys())
    assert set(NEW_PARTS) <= keys
    entries = {e["key"] for e in load_fabrication_vocabulary("interface-sizes")["entries"]}
    assert set(NEW_KEYS) <= entries
