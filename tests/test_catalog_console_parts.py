"""Console, handheld and game-media standard parts (lane console-parts), by placement.

* USB Type-C mates either way up (symmetry 2): the two rotations mirror the plug across the
  receptacle's width, and the shell's tip lands 6.65 mm inside either way.
* The keyed plugs (Standard-A, Micro-B, HDMI Type A) carry x_axis −x, so the mate's half-turn
  about x puts the plug's +y side on the receptacle's +y side.
* DE-9: the socket connector is framed .265 in ahead of its flange, so a mate puts the two
  flanges the MIL-DTL-24308 mated spacing apart, wide side to wide side.
* A reversed AA cell, a UMD in a 120 mm disc tray and an SD card in a microSD slot are refused
  by their size keys; a CD and a DVD share the tray's pocket and hub.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import hyperobjects_standard_parts
from hyperobjects_standard_parts import load_part
from y4d_spec.assembly import (
    CompositeResolver,
    ExternalResolver,
    StandardPartsResolver,
    validate_assembly,
)

CATALOG = Path(hyperobjects_standard_parts.__file__).parent / "parts"


def _resolver():
    return CompositeResolver(standard=StandardPartsResolver(CATALOG), external=ExternalResolver())


def _std(cid, key):
    return {"id": cid, "source": {"type": "standard", "key": key}}


def _ext(cid, *interfaces):
    return {"id": cid, "source": {"type": "external", "name": f"{cid} fixture",
                                  "license": "CERN-OHL-W-2.0", "url": "https://example.org/x",
                                  "interfaces": list(interfaces)}}


def _seat(iid, gtype, size_key, polarity, symmetry, origin=(0, 0, 0), normal=(0, 0, 1)):
    return {"id": iid, "geometry_type": gtype, "size_key": size_key, "polarity": polarity,
            "symmetry": symmetry,
            "frame": {"origin": list(origin), "normal": list(normal), "x_axis": [1, 0, 0]}}


def _mate(mid, a, b, **kw):
    (ca, ia), (cb, ib) = a.split("."), b.split(".")
    return {"id": mid, "a": {"component": ca, "interface": ia},
            "b": {"component": cb, "interface": ib}, **kw}


def _doc(components, mates):
    return {"format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "console-parts",
            "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
            "root": components[0]["id"], "components": components, "mates": mates}


def _apply(matrix, point):
    return tuple(sum(matrix[r][c] * (list(point) + [1.0])[c] for c in range(4)) for r in range(3))


def _pair(receptacle, plug, **kw):
    doc = _doc([_std("r", receptacle), _std("p", plug)], [_mate("m", "r.mating", "p.mating", **kw)])
    return validate_assembly(doc, _resolver())


@pytest.mark.parametrize("index, x_lands", [(0, (-1.0, 0.0, 0.0)), (1, (1.0, 0.0, 0.0))])
def test_type_c_mates_either_way_up(index, x_lands):
    report = _pair("usb-c-receptacle", "usb-c-plug", rotation_index=index)
    assert report.ok, report.findings
    plug = report.placements["p"]
    assert _apply(plug, (0, 0, 6.65)) == pytest.approx((0.0, 0.0, -6.65))  # the tip, inside
    assert _apply(plug, (1, 0, 0)) == pytest.approx(x_lands)


@pytest.mark.parametrize("receptacle, plug", [
    ("usb-a-receptacle", "usb-a-plug"),
    ("usb-micro-b-receptacle", "usb-micro-b-plug"),
    ("hdmi-type-a-receptacle", "hdmi-type-a-plug"),
])
def test_keyed_plugs_land_the_right_way_up(receptacle, plug):
    report = _pair(receptacle, plug, rotation_index=0)
    assert report.ok, report.findings
    placed = report.placements["p"]
    assert _apply(placed, (0, 1, 0)) == pytest.approx((0.0, 1.0, 0.0))  # +y on +y
    assert _apply(placed, (0, 0, 1)) == pytest.approx((0.0, 0.0, -1.0))  # into the receptacle


def test_de9_flanges_sit_at_the_mated_spacing_wide_side_to_wide_side():
    doc = _doc([_std("pins", "dsub-de9-male"), _std("sockets", "dsub-de9-female")],
               [_mate("m", "pins.mating", "sockets.mating", rotation_index=0)])
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    sockets = report.placements["sockets"]
    assert _apply(sockets, (0, 0, 0)) == pytest.approx((0.0, 0.0, 6.731))  # .265 in
    assert _apply(sockets, (0, 1, 0)) == pytest.approx((0.0, 1.0, 6.731))
    assert load_part("dsub-de9-male")["dimensions"]["mated_flange_spacing"]["value"] == 0.265


@pytest.mark.parametrize("receptacle, plug", [
    ("usb-c-receptacle", "usb-a-plug"),
    ("usb-c-receptacle", "usb-micro-b-plug"),
    ("hdmi-type-a-receptacle", "usb-a-plug"),
    ("iec-60320-c14", "rca-plug"),
])
def test_a_plug_of_another_kind_is_refused(receptacle, plug):
    keyed = load_part(plug)["interfaces"][0]["symmetry"]
    report = _pair(receptacle, plug, **({"rotation_index": 0} if keyed else {"angle_deg": 0}))
    assert not report.ok
    assert any(f.code in {"size_key", "symmetry"} for f in report.errors)


def _bay():
    return _ext("bay",
                _seat("trough", "pocket", "cell-aa", "female", 0),
                _seat("minus_contact", "surface", "cell-aa-minus-contact", "neutral", 0),
                _seat("plus_contact", "surface", "cell-aa-plus-contact", "neutral", 0,
                      origin=(0, 0, 50.5), normal=(0, 0, -1)))


def test_an_aa_cell_closes_between_its_two_contacts():
    doc = _doc([_bay(), _std("cell", "cell-aa")],
               [_mate("m1", "bay.trough", "cell.body", angle_deg=0),
                _mate("m2", "bay.minus_contact", "cell.minus_end", angle_deg=0),
                _mate("m3", "bay.plus_contact", "cell.plus_end", angle_deg=0)])
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    assert _apply(report.placements["cell"], (0, 0, 50.5)) == pytest.approx((0.0, 0.0, 50.5))


def test_a_reversed_cell_does_not_mate_the_bay():
    doc = _doc([_bay(), _std("cell", "cell-aa")],
               [_mate("m1", "bay.minus_contact", "cell.plus_end", angle_deg=0)])
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert any(f.code == "size_key" for f in report.errors)


def _tray():
    return _ext("tray",
                _seat("pocket", "pocket", "optical-disc-120mm", "female", 0),
                _seat("hub", "socket", "optical-disc-centre-hole-15mm", "male", 0))


@pytest.mark.parametrize("disc", ["optical-disc-cd-120mm", "optical-disc-dvd-120mm"])
def test_a_cd_and_a_dvd_share_the_tray_pocket_and_hub(disc):
    doc = _doc([_tray(), _std("disc", disc)],
               [_mate("m1", "tray.pocket", "disc.outline", angle_deg=0),
                _mate("m2", "tray.hub", "disc.centre_hole", angle_deg=0)])
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    # read-out side down on the tray, label side up
    assert _apply(report.placements["disc"], (0, 0, 1.2)) == pytest.approx((0.0, 0.0, 1.2))


def test_a_umd_does_not_fit_a_120mm_tray():
    doc = _doc([_tray(), _std("umd", "umd-cartridge")],
               [_mate("m1", "tray.pocket", "umd.case", rotation_index=0)])
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert any(f.code in {"size_key", "symmetry"} for f in report.errors)


def test_an_sd_card_does_not_fit_a_microsd_slot():
    slot = _ext("slot", _seat("slot", "pocket", "microsd-card", "female", 1, normal=(0, -1, 0)))
    doc = _doc([slot, _std("card", "sd-card")],
               [_mate("m1", "slot.slot", "card.body", rotation_index=0)])
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert any(f.code == "size_key" for f in report.errors)


def test_single_source_entries_are_provisional_and_say_so():
    for key in ("hdmi-type-a-plug", "arcade-button-24mm", "arcade-button-30mm"):
        part = load_part(key)
        assert part["status"] == "provisional", key
        assert "one maker" in part["notes"].lower(), key
