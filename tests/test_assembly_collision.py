"""ASM-1 §3.7: `--collision`, rigid-body interference at every pose of the sweep.

A slider runs on a base (a prismatic joint, ±150 mm). A stop block sits near the base's
+x end. At home and at the lower limit nothing touches; at the upper limit the slider's
box runs 10 mm into the stop's. The overlap is a 10 × 20 × 10 mm block, so 2000 mm³. All
three bodies are external envelopes (numbers only), so every volume here is exact. A
second case renders a real cartridge (the test `nema-bracket`) against a catalog
envelope (`nema-17-48mm`).
"""

from __future__ import annotations

import pytest

from assembly_helpers import assembly, codes, resolver, standard

pytestmark = pytest.mark.geometry

URL = "https://github.com/madfam-org/hyperobjects-spec"


def _external(name, interfaces, solids):
    return {"type": "external", "name": name, "license": "CERN-OHL-W-2.0", "url": URL,
            "interfaces": interfaces,
            "envelope": {"solids": solids, "note": "Test proxy body, numbers only."}}


def _iface(iid, origin, normal, polarity, size="slide-test"):
    return {"id": iid, "frame": {"origin": origin, "normal": normal, "x_axis": [1, 0, 0]},
            "polarity": polarity, "size_key": size, "symmetry": 1}


def _box(lo, hi):
    return {"shape": "box", "min": lo, "max": hi}


def slider_on_base(**extra):
    base = _external("Test base", [
        _iface("way", [0, 0, 0], [0, 0, 1], "female"),
        _iface("stop_seat", [145, 0, 0], [0, 0, 1], "female", "stop-test"),
    ], [_box([-200, -20, -10], [200, 20, 0])])
    slider = _external("Test slider", [_iface("shoe", [0, 0, 0], [0, 0, -1], "male")],
                       [_box([-10, -10, 0], [10, 10, 10])])
    stop = _external("Test stop", [_iface("foot", [0, 0, 0], [0, 0, -1], "male", "stop-test")],
                     [_box([-5, -10, 0], [5, 10, 10])])
    return assembly(
        [{"id": "base", "source": base}, {"id": "slider", "source": slider},
         {"id": "stop", "source": stop}],
        [{"id": "slide", "a": {"component": "base", "interface": "way"},
          "b": {"component": "slider", "interface": "shoe"}, "rotation_index": 0,
          "joint": {"id": "slide", "type": "prismatic", "axis": "x", "limits": [-150, 150],
                    "home": 0}},
         {"id": "stop_on_base", "a": {"component": "base", "interface": "stop_seat"},
          "b": {"component": "stop", "interface": "foot"}, "rotation_index": 0}],
        **extra,
    )


def _check(doc, **kw):
    from y4d_spec.assembly import validate_assembly

    return validate_assembly(doc, resolver(), collision=True, **kw)


def test_a_part_moved_into_another_fails_at_the_pose_where_it_does():
    report = _check(slider_on_base(), pose_samples=4)
    assert report.collision == "checked"
    (finding,) = [f for f in report.errors if f.code == "collision"]
    assert finding.subject == "slider|stop"
    assert "2000.00 mm³ (at slide@upper" in finding.message
    assert report.collision_result.pairs["slider|stop"]["max_mm3"] == pytest.approx(2000.0)
    # flush faces (the slider on the base, the stop on the base) are contact, not interference
    assert "base|slider" not in report.collision_result.pairs
    assert "base|stop" not in report.collision_result.pairs


def test_a_declared_overlap_passes_within_its_allowance_and_fails_above_it():
    allowed = [{"a": "stop", "b": "slider", "max_mm3": 2500, "reason": "a test end stop"}]
    assert _check(slider_on_base(allowed_overlaps=allowed), pose_samples=4).ok
    allowed[0]["max_mm3"] = 1000
    report = _check(slider_on_base(allowed_overlaps=allowed), pose_samples=4)
    (finding,) = [f for f in report.errors if f.code == "collision"]
    assert "more than the 1000 mm³ the document allows (a test end stop)" in finding.message


def test_an_allowance_that_never_overlaps_warns():
    doc = slider_on_base(allowed_overlaps=[
        {"a": "base", "b": "stop", "max_mm3": 5, "reason": "stale"}])
    doc["mates"][0]["joint"]["limits"] = [-150, 130]  # the slider never reaches the stop
    report = _check(doc, pose_samples=4)
    assert report.ok
    assert ("allowed-overlap-unused", "base|stop") in codes(report, "warning")


def test_a_component_without_a_solid_is_named_never_passed():
    doc = slider_on_base()
    del doc["components"][2]["source"]["envelope"]
    report = _check(doc, pose_samples=4)
    assert report.collision == "partial"
    (warning,) = [f for f in report.warnings if f.code == "collision-unchecked"]
    assert "stop: external/Test stop (CERN-OHL-W-2.0) declares no envelope" in warning.message


@pytest.mark.parametrize("entry,fragment", [
    ({"a": "base", "b": "ghost", "max_mm3": 1, "reason": "test"}, "not a component"),
    ({"a": "base", "b": "base", "max_mm3": 1, "reason": "test"}, "overlap itself"),
])
def test_allowed_overlaps_name_two_real_components(entry, fragment):
    report = _check(slider_on_base(allowed_overlaps=[entry]), pose_samples=0)
    assert any(f.code == "allowed-overlap" and fragment in f.message for f in report.errors)


def test_a_rendered_cartridge_against_a_catalog_envelope():
    """The test nema-bracket's flat plate (rendered, 5 mm thick, no shaft hole in this
    TEST cartridge) and a NEMA 17 (its envelope) bolted to its motor face: the motor body
    hangs below the plate and its Ø5 shaft runs through the plate's 5 mm, which the render
    finds as π · 2.5² · 5 = 98.17 mm³. Declared, the assembly passes."""
    from assembly_helpers import COMMONS
    from hyperobjects_aas.resolver import bundled_standard_parts_dir
    from y4d_spec.assembly import CompositeResolver, validate_assembly

    def doc(**extra):
        return assembly(
            [{"id": "bracket", "source": {"type": "cartridge", "commons": "solid",
                                          "slug": "nema-bracket", "mode": "flat", "part": None}},
             standard("motor", "nema-17-48mm")],
            [{"id": "m", "a": {"component": "bracket", "interface": "motor_face"},
              "b": {"component": "motor", "interface": "face"}, "rotation_index": 0}],
            **extra)

    both = CompositeResolver.for_directories(COMMONS, bundled_standard_parts_dir())
    report = validate_assembly(doc(), both, collision=True)
    assert report.collision == "checked" and report.collision_result.unchecked == {}
    (finding,) = [f for f in report.errors if f.code == "collision"]
    assert "overlap by up to 98.17 mm³" in finding.message
    allowed = [{"a": "bracket", "b": "motor", "max_mm3": 100,
                "reason": "the test plate has no shaft hole"}]
    assert validate_assembly(doc(allowed_overlaps=allowed), both, collision=True).ok
