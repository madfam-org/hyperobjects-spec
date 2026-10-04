"""The FPV antenna chain on the frame (owner decision O3(a), lane P4-AUTH-C), by placement.

* fpv-frame-5in-x-225 gains `rear_vtx_mount`: the 20 × 20 mm VTX pattern (GEPRC MK5) on
  the top plate's UPPER face at `rear_mount_x_mm` — a convention, like `camera_axis_x_mm`.
* fpv-antenna-mount's `sma_bracket` foot bolts through ONE 20 mm row of it (bolt_span 20
  across the foot's x); its frame sits at the pattern centre, 10 mm off the foot's bolt
  line on the side away from the lean. The fixture below mirrors the cartridge's frames.
* Chain: frame rear seat ↔ mount foot → mount jack seat ↔ sma-bulkhead-jack.panel →
  jack.coupling ↔ vtx-antenna-sma.connector.
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
FRAME = {"id": "frame", "source": {"type": "standard", "key": "fpv-frame-5in-x-225"}}
JACK = {"id": "jack", "source": {"type": "standard", "key": "sma-bulkhead-jack"}}
ANTENNA = {"id": "antenna", "source": {"type": "standard", "key": "vtx-antenna-sma"}}
STALK_H, BASE_H = 35.0, 3.0  # fpv-antenna-mount defaults (base_h is a script constant)
# The row the foot uses: rotation_index 3 turns the foot so its lean (its +y) points to
# the frame's rear (−x), with the foot on the pattern's rear row.
REAR_ROW = 3


def _resolver():
    return CompositeResolver(standard=StandardPartsResolver(CATALOG), external=ExternalResolver())


def _mate(mid, a, b, **kw):
    (ca, ia), (cb, ib) = a.split("."), b.split(".")
    return {"id": mid, "a": {"component": ca, "interface": ia},
            "b": {"component": cb, "interface": ib}, **kw}


def _apply(matrix, point):
    return tuple(sum(matrix[r][c] * (list(point) + [1.0])[c] for c in range(4)) for r in range(3))


def _mount(back_angle, bolt_span=20.0, foot_key="vtx-mount-20x20"):
    """fpv-antenna-mount (sma_bracket) as its manifest frames it."""
    a = math.radians(max(0.0, min(back_angle, 45.0)) if back_angle > 0.1 else 0.0)
    foot = {"id": "foot", "polarity": "male", "size_key": foot_key, "symmetry": 4,
            "geometry_type": "bolt_pattern",
            "frame": {"origin": [0, -bolt_span / 2, -BASE_H], "normal": [0, 0, -1],
                      "x_axis": [1, 0, 0]}}
    seat = {"id": "jack_seat", "polarity": "female", "size_key": "sma-bulkhead", "symmetry": 0,
            "geometry_type": "thread",
            "frame": {"origin": [0, STALK_H * math.sin(a), STALK_H * math.cos(a)],
                      "normal": [0, -math.sin(a), -math.cos(a)], "x_axis": [1, 0, 0]}}
    return {"id": "mount", "source": {"type": "external", "name": "fpv-antenna-mount fixture",
                                      "license": "CERN-OHL-W-2.0",
                                      "url": "https://example.org/x",
                                      "interfaces": [foot, seat]}}


def _doc(components, mates):
    return {"format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "antenna-chain",
            "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
            "root": "frame", "components": components, "mates": mates}


def _chain(back_angle, **mount_kw):
    return _doc([FRAME, _mount(back_angle, **mount_kw), JACK, ANTENNA],
                [_mate("m1", "frame.rear_vtx_mount", "mount.foot", rotation_index=REAR_ROW),
                 _mate("m2", "mount.jack_seat", "jack.panel", angle_deg=0),
                 _mate("m3", "jack.coupling", "antenna.connector", angle_deg=0)])


def test_the_key_and_the_seat_are_cited_and_the_position_is_a_convention():
    entries = {e["key"]: e for e in load_fabrication_vocabulary("interface-sizes")["entries"]}
    key = entries["vtx-mount-20x20"]
    assert key["dimensions"]["hole_spacing"]["value"] == 20
    assert "20mm x 20mm" in key["sources"][0]["supports"]
    part = load_part("fpv-frame-5in-x-225")
    params = {p["id"]: p for p in part["parameters"]}
    assert params["rear_mount_x_mm"]["note"] == params["camera_axis_x_mm"]["note"]
    assert "source" not in params["rear_mount_x_mm"]
    frames = interface_frames(part, resolve_parameters(part, {}))
    seat = frames["rear_vtx_mount"]
    assert seat.origin == pytest.approx((-45.0, 0.0, 27.5))  # top plate's UPPER face
    assert seat.normal == pytest.approx((0.0, 0.0, 1.0))


@pytest.mark.parametrize("back_angle", [0, 20, 25, 45])
def test_frame_rear_seat_to_mount_to_jack_to_antenna_closes(back_angle):
    report = validate_assembly(_chain(back_angle), _resolver())
    assert report.ok, report.findings
    assert all(m.ok for m in report.mates) and len(report.mates) == 3
    mount, jack, antenna = (report.placements[k] for k in ("mount", "jack", "antenna"))
    # The foot's bolt line is the pattern's REAR row: 10 mm behind the pattern centre.
    assert _apply(mount, (0, 0, -BASE_H)) == pytest.approx((-55.0, 0.0, 27.5))
    for x in (-10.0, 10.0):  # its two bolts land on two of the four 20 × 20 holes
        hole = _apply(mount, (x, 0, -BASE_H))
        assert (round(hole[0] + 45.0, 9), round(abs(hole[1]), 9)) == (-10.0, 10.0)
    # The stalk leans BACK (world −x) by back_angle; the jack's shoulder is on the cap
    # underside and the antenna continues up the leaned axis.
    a = math.radians(back_angle)
    axis = (-math.sin(a), 0.0, math.cos(a))
    base = (-55.0, 0.0, 27.5 + BASE_H)
    expect = lambda t: tuple(base[i] + t * axis[i] for i in range(3))  # noqa: E731
    assert _apply(jack, (0, 0, 0)) == pytest.approx(expect(STALK_H), abs=1e-9)
    assert _apply(jack, (0, 0, 10)) == pytest.approx(expect(STALK_H + 10), abs=1e-9)
    assert _apply(antenna, (0, 0, 60)) == pytest.approx(expect(STALK_H + 70), abs=1e-9)


def test_a_foot_on_another_pattern_is_refused():
    """A pattern mismatch: a foot keyed for a 20 × 20 FC stack (same holes, other seat)."""
    doc = _chain(25, foot_key="stack-20x20-m2")
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert any(f.code == "size_key" for f in report.errors)


def test_the_rear_seat_does_not_take_the_stack_pattern():
    doc = _doc([FRAME, _mount(25)],
               [_mate("m1", "frame.stack_mount", "mount.foot", rotation_index=REAR_ROW)])
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert any(f.code == "size_key" for f in report.errors)


def test_a_foot_whose_span_is_not_20_misses_the_row():
    """Even with the key forced, a 25 mm foot's frame is off the pattern: the seat holds,
    but its second bolt would miss — the cartridge's slider key resolves only at 20."""
    report = validate_assembly(_chain(25, bolt_span=25.0), _resolver())
    assert report.ok  # closure alone cannot see a bolt that misses: the key must
    mount = report.placements["mount"]
    hole = _apply(mount, (12.5, 0, -BASE_H))
    assert abs(hole[1]) != pytest.approx(10.0)
