"""Two ASM-1 fixes from the P4-ASM2 findings.

* 3b — on a continuous-symmetry (0) mate the stated ``angle_deg`` is compared with the
  angle the geometry realises whenever both frames declare an ``x_axis``; a cycle-closing
  mate that contradicts it is an error. Without an ``x_axis`` the angle is a convention,
  and a closing mate says so (``angle-unchecked`` warning) rather than passing silently.
* 5 — ``capability_profile.process`` is a LIST of ``processes`` keys (like
  ``requirements.process``), in the schema, the vocabulary and the validator.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assembly_helpers import assembly, codes, mate
from hyperobjects_lexicon import capability_profile_problems
from hyperobjects_lexicon.fabrication import load_fabrication_vocabulary
from y4d_spec.assembly import CompositeResolver, ExternalResolver, validate_assembly

GOLDEN = Path(__file__).parent / "fixtures" / "assembly-golden" / "commons"


def _external(cid, interfaces):
    return {"id": cid, "source": {"type": "external", "name": cid.upper(), "license": "MIT",
                                  "url": f"https://example.org/{cid}", "interfaces": interfaces}}


def _iface(iid, origin, normal, polarity, x_axis=True):
    frame = {"origin": origin, "normal": normal}
    if x_axis:
        frame["x_axis"] = [1, 0, 0]
    return {"id": iid, "frame": frame, "polarity": polarity, "size_key": "test-pin",
            "symmetry": 0}


def _loop(angle_closing, x_axis_on_q2=True):
    """Two parts joined twice: m1 places b (θ = 0), m2 closes the cycle at
    `angle_closing`. The geometry realises 0° on m2."""
    a = _external("plate", [_iface("p1", [0, 0, 0], [0, 0, 1], "male"),
                            _iface("p2", [10, 0, 0], [0, 0, 1], "male")])
    b = _external("block", [_iface("q1", [0, 0, 0], [0, 0, -1], "female"),
                            _iface("q2", [10, 0, 0], [0, 0, -1], "female", x_axis_on_q2)])
    return assembly([a, b], [mate("m1", "plate.p1", "block.q1", angle_deg=0),
                             mate("m2", "plate.p2", "block.q2", angle_deg=angle_closing)])


RESOLVER = CompositeResolver(external=ExternalResolver())


def test_a_continuous_closing_mate_at_the_realised_angle_holds():
    report = validate_assembly(_loop(0), RESOLVER)
    assert report.ok, report.findings
    m2 = report.mates[1]
    assert not m2.in_tree and m2.x_axis_deg == pytest.approx(0, abs=1e-9)
    assert report.mates[0].x_axis_deg == pytest.approx(0, abs=1e-9)  # tree: by construction


def test_a_continuous_closing_mate_that_contradicts_the_geometry_fails():
    report = validate_assembly(_loop(40), RESOLVER)
    assert codes(report) == [("closure", "m2")]
    (finding,) = report.errors
    assert "stated angle_deg 40° but the geometry realises 0°" in finding.message
    assert "40.0000° apart" in finding.message
    assert report.mates[1].x_axis_deg == pytest.approx(40)


def test_the_angle_residual_is_measured_on_the_full_circle():
    assert validate_assembly(_loop(360), RESOLVER).ok
    report = validate_assembly(_loop(-0.4), RESOLVER)
    assert report.ok and report.mates[1].x_axis_deg == pytest.approx(0.4)
    assert not validate_assembly(_loop(-0.6), RESOLVER).ok


def test_without_an_x_axis_the_closing_angle_is_reported_unchecked():
    report = validate_assembly(_loop(40, x_axis_on_q2=False), RESOLVER)
    assert report.ok
    assert codes(report, "warning") == [("angle-unchecked", "m2")]
    assert report.mates[1].x_axis_deg is None


def test_assembly_b_states_the_angle_its_geometry_realises():
    """B closes the camera cage on the side plates' outer faces at 0° (solid #136): with 3b
    in force the stated angle of that continuous closing mate is checked, and holds."""
    from hyperobjects_aas.resolver import bundled_standard_parts_dir

    doc = json.loads((GOLDEN / "assemblies" / "fpv-5in-freestyle" / "assembly.json")
                     .read_text("utf-8"))
    resolver = CompositeResolver.for_directories(GOLDEN, bundled_standard_parts_dir())
    report = validate_assembly(doc, resolver)
    closing = next(m for m in report.mates if m.mate_id == "cage_ear_right_on_plate")
    assert report.ok and not closing.in_tree
    assert closing.x_axis_deg == pytest.approx(0, abs=1e-9)
    doc["mates"][11]["angle_deg"] = 1
    assert codes(validate_assembly(doc, resolver)) == [("closure", "cage_ear_right_on_plate")]


# ── finding 5: capability_profile.process is a list ──────────────────────────
def _producer(profile):
    a = _external("plate", [_iface("p1", [0, 0, 0], [0, 0, 1], "male")])
    return assembly([a], [], kind="producer", capability_profile=profile)


def test_the_vocabulary_types_process_as_a_list_of_processes_keys():
    entry = next(e for e in load_fabrication_vocabulary("fabrication-capabilities")["entries"]
                 if e["key"] == "process")
    assert entry["value_type"] == "array"
    assert entry["value_vocabulary"] == "processes"


def test_a_list_of_processes_is_accepted():
    report = validate_assembly(_producer({"process": ["fff", "laser_2d"],
                                          "toolhead_count": 1,
                                          "connectivity": ["moonraker"]}), RESOLVER)
    assert report.ok, report.findings


def test_a_bare_process_string_is_refused_by_the_schema():
    report = validate_assembly(_producer({"process": "fff"}), RESOLVER)
    assert [f.code for f in report.errors] == ["schema"]
    assert "capability_profile/process" in report.errors[0].message


@pytest.mark.parametrize("profile,needle", [
    ({"process": ["fdm"]}, "'fdm' is not a key of the processes vocabulary"),
    ({"build_volume": 350}, "'build_volume' is not a key of the fabrication-capabilities"),
    ({"toolhead_count": 1.5}, "1.5 is not a integer"),
    ({"enclosure": "yes"}, "'yes' is not a boolean"),
    ({"firmware": "grbl"}, "'grbl' is not one of klipper"),
    ({"connectivity": ["moonraker", "usb"]}, "connectivity[1]: 'usb' is not one of"),
])
def test_capability_profile_membership(profile, needle):
    problems = capability_profile_problems(profile)
    assert any(needle in p for p in problems), problems
    report = validate_assembly(_producer(profile), RESOLVER)
    assert "capability" in [f.code for f in report.errors]


def test_no_profile_has_no_problems():
    assert capability_profile_problems(None) == []
