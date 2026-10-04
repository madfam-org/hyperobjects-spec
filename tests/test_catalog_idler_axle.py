"""The 608 idler axle (lane P4-AUTH-D), proven by placement.

Nothing in the catalog carried a MALE ``bearing-608-bore``, so a 608 and the pulley on
its outer ring could not reach a frame. ``shaft-8mm`` is that axle: a plain Ø8 g6 ground
shaft (MISUMI SFJ / PSFJ) with two male interfaces:

* ``host_end`` (``shaft-8mm``): end A in a host's 8 mm bore, framed at the host face;
* ``bearing_journal`` (``bearing-608-bore``): where the 608's face B lands, one ISO 7089
  washer (1.6 mm) plus the bearing's 7 mm past the host face at the defaults.

The chain host bore → axle → 608 bore, then 608 outer ring → pulley seat, places every
part where the stack says, with each partner on the side its polarity claims. The host
and the pulley are framed exactly as the commons frames them (roller-bracket's
``extrusion_bracket_shaft_bore`` at its defaults; idler-608's
``flat_idler_bearing_seat``), so the same mates hold in an assembly document.
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
AXLE = {"id": "axle", "source": {"type": "standard", "key": "shaft-8mm"}}
BEARING = {"id": "bearing", "source": {"type": "standard", "key": "bearing-608"}}

# roller-bracket extrusion_bracket at its defaults: web_thick 8, mount_height 40. The
# bore's +X face is at x = web_thick / 2, the axis at z = mount_height, normal +x
# (out of the cavity: the bore runs into the web on the −x side).
HOST_BORE = {"id": "bore", "polarity": "female", "size_key": "shaft-8mm", "symmetry": 0,
             "frame": {"origin": [4, 0, 40], "normal": [1, 0, 0], "x_axis": [0, 1, 0]}}
# idler-608 flat_idler at its defaults: width 10; the seat is framed at its entrance,
# the top face, normal +z, with the bearing pocket below it (floor at z = 3).
PULLEY_SEAT = {"id": "seat", "polarity": "female", "size_key": "bearing-608", "symmetry": 0,
               "frame": {"origin": [0, 0, 10], "normal": [0, 0, 1], "x_axis": [1, 0, 0]}}


def _resolver():
    return CompositeResolver(standard=StandardPartsResolver(CATALOG), external=ExternalResolver())


def _external(cid, *ifaces):
    return {"id": cid, "source": {"type": "external", "name": f"Test {cid}",
                                  "license": "CERN-OHL-W-2.0", "url": "https://example.org/x",
                                  "interfaces": list(ifaces)}}


def _assembly(components, mates):
    return {
        "format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "idler-axle",
        "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
        "root": components[0]["id"], "components": components, "mates": mates,
    }


def _mate(mid, a, b, **kw):
    (ca, ia), (cb, ib) = a.split("."), b.split(".")
    return {"id": mid, "a": {"component": ca, "interface": ia},
            "b": {"component": cb, "interface": ib}, **kw}


def _apply(matrix, point):
    return tuple(sum(matrix[r][c] * (list(point) + [1.0])[c] for c in range(4)) for r in range(3))


def _stack(axle=AXLE, host_bore=HOST_BORE):
    return _assembly(
        [_external("host", host_bore), axle, BEARING, _external("pulley", PULLEY_SEAT)],
        [_mate("axle_in_host", "host.bore", "axle.host_end", angle_deg=0),
         _mate("bearing_on_axle", "axle.bearing_journal", "bearing.bore", angle_deg=0),
         _mate("pulley_on_bearing", "bearing.outer_race", "pulley.seat", angle_deg=0)],
    )


# ── vocabulary and catalog facts ──────────────────────────────────────────────
def test_shaft_8mm_is_a_cited_socket_key_distinct_from_the_608_bore():
    entries = {e["key"]: e for e in load_fabrication_vocabulary("interface-sizes")["entries"]}
    shaft = entries["shaft-8mm"]
    assert shaft["geometry_type"] == "socket"
    assert shaft["dimensions"]["shaft_diameter"]["value"] == 8
    assert shaft["dimensions"]["shaft_diameter"]["tolerance"] == "g6 (−0.005/−0.014)"
    assert shaft["sources"] and all(s["url"].startswith("https://") for s in shaft["sources"])
    # The host fit and the bearing fit are two keys: a bore in a bracket is not a 608.
    assert "bearing-608-bore" in entries and shaft["key"] != "bearing-608-bore"


def test_the_shaft_cites_its_length_range_and_the_washer_gap():
    part = load_part("shaft-8mm")
    dims, params = part["dimensions"], {p["id"]: p for p in part["parameters"]}
    assert (params["length_mm"]["min"], params["length_mm"]["max"]) == (
        dims["length_min"]["value"], dims["length_max"]["value"]) == (20, 800)
    assert params["length_mm"]["step"] == dims["length_increment"]["value"] == 1
    assert params["bearing_gap_mm"]["default"] == dims["washer_m8_thickness"]["value"] == 1.6
    assert dims["bearing_608_width"]["value"] == load_part("bearing-608")["dimensions"][
        "width"]["value"] == 7


@pytest.mark.parametrize("given", [{}, {"host_depth_mm": 10, "bearing_gap_mm": 0.5,
                                        "length_mm": 30}])
def test_frames_follow_the_stack(given):
    part = load_part("shaft-8mm")
    values = resolve_parameters(part, given)
    frames = interface_frames(part, values)
    host, journal = frames["host_end"], frames["bearing_journal"]
    depth, gap = values["host_depth_mm"], values["bearing_gap_mm"]
    assert host.origin == pytest.approx((0, 0, depth))
    assert journal.origin == pytest.approx((0, 0, depth + gap + 7))
    # Both partners lie toward end A: the host around it, the bearing between the
    # journal origin and the host.
    assert host.normal == journal.normal == pytest.approx((0, 0, -1))
    # The stack fits on the shaft at these points.
    assert depth + gap + 7 <= values["length_mm"]


# ── host → axle → 608 → pulley ────────────────────────────────────────────────
def test_the_idler_stack_closes_and_places_every_part():
    report = validate_assembly(_stack(), _resolver())
    assert report.ok, report.findings
    assert [m.ok for m in report.mates] == [True, True, True]
    axle, bearing, pulley = (report.placements[k] for k in ("axle", "bearing", "pulley"))
    # The axle runs +x out of the host face (x = 4): end A flush with the web's far face
    # (x = −4, host_depth 8 = web_thick 8), end B at 4 − 8 + 20 = 16, on the axis z = 40.
    assert _apply(axle, (0, 0, 0)) == pytest.approx((-4.0, 0.0, 40.0))
    assert _apply(axle, (0, 0, 20)) == pytest.approx((16.0, 0.0, 40.0))
    # The 608's face A sits one washer (1.6) off the host face; face B 7 mm further.
    assert _apply(bearing, (0, 0, 0)) == pytest.approx((5.6, 0.0, 40.0))
    assert _apply(bearing, (0, 0, 7)) == pytest.approx((12.6, 0.0, 40.0))
    # The pulley's top face is flush with the bearing's face A (it faces the host
    # across the washer gap); its 3 mm floor lies beyond face B, away from the host.
    assert _apply(pulley, (0, 0, 10)) == pytest.approx((5.6, 0.0, 40.0))
    assert _apply(pulley, (0, 0, 3)) == pytest.approx((12.6, 0.0, 40.0))
    assert _apply(pulley, (0, 0, 0)) == pytest.approx((15.6, 0.0, 40.0))


@pytest.mark.parametrize("angle", [0, 37, 180])
def test_the_stack_spins_freely_about_the_axle(angle):
    """Symmetry 0 on every mate: any stated angle closes and leaves the axis in place."""
    doc = _stack()
    for mate in doc["mates"]:
        mate["angle_deg"] = angle
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    assert _apply(report.placements["bearing"], (0, 0, 7)) == pytest.approx((12.6, 0.0, 40.0))


def test_a_thicker_host_and_a_wider_gap_move_the_bearing_with_them():
    axle = {**AXLE, "source": {**AXLE["source"],
                               "parameters": {"host_depth_mm": 10, "bearing_gap_mm": 3,
                                              "length_mm": 25}}}
    report = validate_assembly(_stack(axle=axle), _resolver())
    assert report.ok, report.findings
    assert _apply(report.placements["axle"], (0, 0, 0)) == pytest.approx((-6.0, 0.0, 40.0))
    assert _apply(report.placements["bearing"], (0, 0, 0)) == pytest.approx((7.0, 0.0, 40.0))


# ── negative controls ─────────────────────────────────────────────────────────
def test_the_host_end_does_not_go_into_a_608():
    """The two male interfaces carry different keys: swap them and nothing mates."""
    doc = _assembly(
        [_external("host", HOST_BORE), AXLE, BEARING],
        [_mate("m1", "host.bore", "axle.bearing_journal", angle_deg=0),
         _mate("m2", "axle.host_end", "bearing.bore", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}


def test_a_608_bore_does_not_seat_in_the_host_directly():
    """Without the axle, the bearing's female bore meets the host's female bore."""
    doc = _assembly(
        [_external("host", HOST_BORE), BEARING],
        [_mate("m1", "host.bore", "bearing.bore", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key", "polarity"}


def test_a_host_bore_of_another_size_refuses_the_axle():
    other = {**HOST_BORE, "size_key": "nema-17-shaft-5mm"}
    report = validate_assembly(_stack(host_bore=other), _resolver())
    assert not report.ok
    assert any(f.code == "size_key" and "axle_in_host" in str(f) for f in report.errors)
