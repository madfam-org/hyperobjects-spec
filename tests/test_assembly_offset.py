"""ASM-1 §9 (v1.4): a station on the mate (`offset`), checked against the interface's
`travel`.

`extrusion-2020` shares ONE `slot_station_mm` between its eight slots, so two parts on the
same extrusion at different stations could not both mate (P6-ZBED's finding). A mate
`offset` slides one side's interface frame along its own axis before the mate is formed;
each slot declares its travel — the slot's run from end A to end B, measured from the
station — and an offset outside it is an error.
"""

from __future__ import annotations

import pytest

from assembly_helpers import assembly, assert_matrix, codes, standard
from hyperobjects_aas.resolver import bundled_standard_parts_dir
from y4d_spec.assembly import CompositeResolver, validate_assembly


def resolver():
    return CompositeResolver.for_directories(standard_parts=bundled_standard_parts_dir())


def _mate(mid, a, b, offset=None, **extra):
    ca, ia = a.split(".")
    cb, ib = b.split(".")
    out = {"id": mid, "a": {"component": ca, "interface": ia},
           "b": {"component": cb, "interface": ib}, "rotation_index": 0, **extra}
    if offset is not None:
        out["offset"] = offset
    return out


def rail_with_two_nuts(offset, *, swap=False):
    """One 350 mm extrusion (stations at 10 mm) and two T-nuts in slot +x near end A: the
    first at the station, the second at the station plus `offset`."""
    second = (_mate("nut_2_in_slot", "nut_2.slot", "rail.slot_xp_a",
                    offset=None if offset is None else {**offset, "side": "b"})
              if swap else _mate("nut_2_in_slot", "rail.slot_xp_a", "nut_2.slot", offset=offset))
    return assembly(
        [standard("rail", "extrusion-2020", length_mm=350, slot_station_mm=10),
         standard("nut_1", "tnut-2020-m5"), standard("nut_2", "tnut-2020-m5")],
        [_mate("nut_1_in_slot", "rail.slot_xp_a", "nut_1.slot"), second],
    )


def _z(report, cid):
    return report.placements[cid][2][3]


def test_two_parts_on_one_slot_at_different_stations():
    report = validate_assembly(rail_with_two_nuts({"axis": "x", "value": 160}), resolver())
    assert report.ok and not report.warnings, [str(f) for f in report.findings]
    assert _z(report, "nut_1") == pytest.approx(10.0)
    assert _z(report, "nut_2") == pytest.approx(170.0)  # 10 + 160 along the extrusion


def test_the_offset_may_sit_on_side_b():
    a = validate_assembly(rail_with_two_nuts({"axis": "x", "value": 160}), resolver())
    b = validate_assembly(rail_with_two_nuts({"axis": "x", "value": 160}, swap=True),
                          resolver())
    assert b.ok, [str(f) for f in b.findings]
    assert _z(b, "nut_2") == pytest.approx(_z(a, "nut_2"))


@pytest.mark.parametrize("value,ok", [(-10, True), (340, True), (-10.5, False), (340.5, False)])
def test_the_offset_stays_inside_the_slots_run(value, ok):
    report = validate_assembly(rail_with_two_nuts({"axis": "x", "value": value}), resolver())
    assert report.ok is ok
    if not ok:
        (finding,) = [f for f in report.errors if f.code == "offset"]
        assert "leaves rail.slot_xp_a's travel [-10, 340] mm" in finding.message


def test_the_offset_runs_along_the_travel_axis_only():
    report = validate_assembly(rail_with_two_nuts({"axis": "y", "value": 5}), resolver())
    assert ("offset", "nut_2_in_slot") in codes(report)


def test_an_interface_without_travel_warns_that_the_offset_is_unchecked():
    doc = rail_with_two_nuts(None)
    doc["components"].append({"id": "stud", "source": {
        "type": "external", "name": "Test stud", "license": "CERN-OHL-W-2.0",
        "url": "https://github.com/madfam-org/hyperobjects-spec", "interfaces": [
            {"id": "thread", "frame": {"origin": [0, 0, 0], "normal": [0, 0, -1],
                                       "x_axis": [1, 0, 0]},
             "polarity": "male", "size_key": "m5-screw-joint", "symmetry": 0}]}})
    doc["mates"].append(_mate("stud_in_nut", "nut_1.thread", "stud.thread", angle_deg=0,
                              offset={"axis": "z", "value": 1}))
    del doc["mates"][-1]["rotation_index"]
    report = validate_assembly(doc, resolver())
    assert ("offset-unchecked", "stud_in_nut") in codes(report, "warning")


def test_a_mate_carries_an_offset_or_a_joint_never_both():
    doc = rail_with_two_nuts({"axis": "x", "value": 20})
    doc["mates"][1]["joint"] = {"id": "j", "type": "prismatic", "axis": "x",
                                "limits": [0, 1], "home": 0}
    report = validate_assembly(doc, resolver())
    assert any(f.code == "schema" for f in report.errors)


def test_the_same_station_through_the_parameter_or_the_offset_agrees():
    """slot_station_mm = 170 on a second extrusion places a nut exactly where offset 160
    from station 10 does."""
    by_parameter = validate_assembly(assembly(
        [standard("rail", "extrusion-2020", length_mm=350, slot_station_mm=170),
         standard("nut_2", "tnut-2020-m5")],
        [_mate("nut_2_in_slot", "rail.slot_xp_a", "nut_2.slot")]), resolver())
    by_offset = validate_assembly(rail_with_two_nuts({"axis": "x", "value": 160}), resolver())
    assert_matrix(by_parameter.placements["nut_2"], by_offset.placements["nut_2"])
