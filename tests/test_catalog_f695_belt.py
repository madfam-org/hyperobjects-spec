"""`bearing-f695` as a smooth belt via (ASM-1 §9, lane P6-GANTRY).

A 2.4-class gantry runs its A/B belts round stacks of two F695 flanged bearings, plain face to
plain face with the flanges outward (Voron 2.4r2 build guide, cited by page only: pp. 65, 69,
97, 99). The belt runs on the outer rings (NSK F695ZZ D 13) between the flanges, so the
catalog's `belt_engagement` is a `running_diameter` of 13 centred on the plain-face junction
(z = 4 of either bearing: a labelled convention). A path adds the belt's pitch-line offset for
the side on the stack: its teeth (T + U) at the front idlers and the drives' pass-through
stacks, its back (B − T − U) at the XY joints.

The belt here is a test fixture carrying the 2 mm GT2 section's offsets as the catalog belt
`gt2-belt-6mm` states them (B 1.52, T 0.76 from Pfeifer's 2MR/PGGT2 row; U 0.254 from SDP/SI
Table 4): teeth 1.014, back 0.506.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from hyperobjects_aas.resolver import bundled_standard_parts_dir
from hyperobjects_standard_parts import load_part
from y4d_spec.assembly import CompositeResolver, validate_assembly
from y4d_spec.assembly.paths import Via, effective_diameter

REPO = Path(__file__).resolve().parent.parent
KIN = REPO / "tests" / "fixtures" / "kinematics"
TEETH, BACK = 0.76 + 0.254, 1.52 - 0.76 - 0.254
A = 40.0  # anchors 40 mm out along the two spans


def _belt_dir(tmp_path):
    """The JOINT fixture belt with the 2 mm GT2 section's pitch-line offsets added."""
    belt = json.loads((KIN / "standard-parts" / "gt2-belt-6mm-test.json").read_text("utf-8"))
    belt["key"] = "gt2-belt-6mm-offsets-test"
    belt["sources"].append({
        "title": "SDP/SI Technical Section, Timing Belts, Pulleys, Chains and Sprockets (D820)",
        "url": "https://sdp-si.com/D820/PDFS/Technical-Section.pdf",
        "publisher": "Stock Drive Products / Sterling Instrument", "accessed": "2026-10-04",
        "supports": "2 mm GT: tooth height 0.76, belt height 1.52 (Fig. 19g); "
                    "U 0.010 in (Table 4)"})
    s = len(belt["sources"]) - 1
    belt["belt"]["teeth_side_offset"] = {"value": round(TEETH, 3), "unit": "mm", "source": s}
    belt["belt"]["back_side_offset"] = {"value": round(BACK, 3), "unit": "mm", "source": s}
    out = tmp_path / "parts"
    out.mkdir()
    (out / f"{belt['key']}.json").write_text(json.dumps(belt), "utf-8")
    return out


def _resolver(*extra):
    return CompositeResolver.for_directories(
        standard_parts=[bundled_standard_parts_dir(), KIN / "standard-parts", *extra])


def _iface(iid, polarity, size_key, symmetry, origin, normal=(0, 0, 1), x_axis=(1, 0, 0)):
    return {"id": iid, "polarity": polarity, "size_key": size_key, "symmetry": symmetry,
            "frame": {"origin": list(origin), "normal": list(normal), "x_axis": list(x_axis)}}


def _corner(side, wrap, via_bearing="f695_1", belt="gt2-belt-6mm-offsets-test"):
    """An XY-joint-like corner: a host clamps M5x40 → shim → F695 → F695 → shim (the guide's
    stack, flanges outward) between walls at z 5 and 15, and the belt turns 90° round it
    between two anchors on the stack's mid-plane (z 10)."""
    r = (13 + 2 * (TEETH if side == "teeth" else BACK)) / 2
    host = {"id": "host", "source": {
        "type": "external", "name": "Test host", "license": "CERN-OHL-W-2.0",
        "url": "https://example.org/x", "interfaces": [
            _iface("bolt_hole", "female", "m5-clearance-hole", 0, (0, 0, 0), (0, 0, -1)),
            _iface("lower_face", "neutral", "m5-axle-stack-face", 0, (0, 0, 5)),
            _iface("upper_face", "neutral", "m5-axle-stack-face", 0, (0, 0, 15), (0, 0, -1)),
            # the belt enters along +x tangent to the circle's top, leaves along −y off its right
            _iface("clamp_in", "male", "gt2-belt-6mm", 1, (-A, r, 10)),
            _iface("clamp_out", "male", "gt2-belt-6mm", 1, (r, -A, 10)),
        ]}}

    def std(cid, key):
        return {"id": cid, "source": {"type": "standard", "key": key}}

    def mate(mid, a, b):
        (ca, ia), (cb, ib) = a.split("."), b.split(".")
        return {"id": mid, "a": {"component": ca, "interface": ia},
                "b": {"component": cb, "interface": ib}, "angle_deg": 0}

    return {
        "format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "f695-corner",
        "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
        "root": "host",
        "components": [host, std("screw", "shcs-m5x40"), std("shim_1", "shim-5x10"),
                       std("f695_1", "bearing-f695"), std("f695_2", "bearing-f695"),
                       std("shim_2", "shim-5x10")],
        "mates": [mate("screw_in_host", "host.bolt_hole", "screw.head_seat"),
                  mate("shim_1_on_screw", "screw.journal", "shim_1.bore"),
                  mate("shim_1_on_host", "host.lower_face", "shim_1.face_a"),
                  mate("f695_1_on_shim", "shim_1.face_b", "f695_1.flange_face"),
                  mate("back_to_back", "f695_1.plain_face", "f695_2.plain_face"),
                  mate("shim_2_on_f695", "f695_2.flange_face", "shim_2.face_a"),
                  mate("stack_to_upper_wall", "shim_2.face_b", "host.upper_face")],
        "paths": [{"id": "belt_corner", "kind": "belt", "part": belt, "closed": False,
                   "via": [{"component": "host", "interface": "clamp_in"},
                           {"component": via_bearing, "wrap": wrap, "side": side},
                           {"component": "host", "interface": "clamp_out"}]}],
    }


def test_the_f695_entry_states_a_cited_running_diameter_on_the_pair_junction():
    part = load_part("bearing-f695")
    engagement = part["belt_engagement"]
    assert "pitch_diameter" not in engagement
    d = engagement["running_diameter"]
    assert d["value"] == part["dimensions"]["outside_diameter"]["value"] == 13
    assert part["sources"][d["source"]]["publisher"] == "NSK"
    # the mid-plane is the plain face (face B, z = 4): where two F695 meet flanges outward
    assert engagement["center"] == [0, 0, 4]
    assert engagement["center"][2] == part["dimensions"]["width"]["value"]
    assert engagement["axis"] == [0, 0, 1]
    assert "Convention" in engagement["plane_note"]


@pytest.mark.parametrize("side,expected", [("teeth", 15.028), ("back", 14.012)])
def test_the_effective_diameter_is_the_ring_plus_twice_the_side_offset(side, expected):
    from hyperobjects_standard_parts import BeltEngagement

    e = load_part("bearing-f695")["belt_engagement"]
    engagement = BeltEngagement(False, e["running_diameter"]["value"], (0, 0, 4), (0, 0, 1))
    belt = {"teeth_side_offset_mm": TEETH, "back_side_offset_mm": BACK}
    got = effective_diameter(Via("f695_1", wrap="ccw", side=side), engagement, belt)
    assert got == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("side", ["teeth", "back"])
@pytest.mark.parametrize("bearing", ["f695_1", "f695_2"])
def test_a_quarter_turn_round_a_stack_is_two_spans_and_a_quarter_circle(tmp_path, side,
                                                                        bearing):
    """Either bearing of the pair names the same circle: their plain faces meet at z 10."""
    report = validate_assembly(_corner(side, "cw", via_bearing=bearing),
                               _resolver(_belt_dir(tmp_path)))
    assert report.ok, report.findings
    (path,) = report.paths
    r = (13 + 2 * (TEETH if side == "teeth" else BACK)) / 2
    assert path.length_mm == pytest.approx(2 * A + math.pi / 2 * r, abs=1e-9)
    assert path.planarity_mm == pytest.approx(0.0, abs=1e-9)


def test_a_stack_via_needs_the_belts_offset_for_its_side():
    """JOINT's fixture belt states pitch and width only: a smooth via cannot be measured."""
    report = validate_assembly(_corner("back", "cw", belt="gt2-belt-6mm-test"), _resolver())
    assert not report.ok
    assert any("back_side_offset" in f.message for f in report.errors if f.code == "path")


def test_the_pair_is_planar_only_on_its_junction(tmp_path):
    """Move the anchors 1 mm off the junction: the path is no longer planar."""
    doc = _corner("back", "cw")
    doc = copy.deepcopy(doc)
    for iface in doc["components"][0]["source"]["interfaces"]:
        if iface["id"].startswith("clamp_"):
            iface["frame"]["origin"][2] = 11
    report = validate_assembly(doc, _resolver(_belt_dir(tmp_path)))
    assert not report.ok
    assert any("planar" in f.message for f in report.errors if f.code == "path")
