"""The B-Rep gate: an invalid or inverted shape must fail HERE, before tessellation.

Solid #45 (tripod-hub, 2026-09-06) is the case these tests encode. Its `core.union(rib)`
over a `makeHelix(radius=1e-6)` path returned an invalid shape that macOS OCCT
nevertheless tessellated into a watertight STL with a plausible volume — every mesh check
passed — while the Linux OCP build segfaulted on the next boolean with no traceback.

Two fixtures, because the two gates catch two DIFFERENT faults and neither subsumes the
other:

  * `_degenerate_helix_fuse` — the tripod-hub idiom. `BRepCheck_Analyzer.IsValid()` is
    False on it.
  * `_reversed_solid` — a solid whose orientation is flipped. It is topologically
    perfect and `IsValid()` returns **True**; only the signed volume betrays it. This is
    why the volume rule is not decoration on top of the analyzer.

The helix fixture is `lru_cache`d: building it costs ~10 s (a degenerate helical sweep is
slow for the same numerical reason it is wrong) and five tests want the same shape, which
is only ever read.
"""

import functools

import pytest

pytest.importorskip("cadquery")
pytest.importorskip("OCP")

import cadquery as cq  # noqa: E402

from y4d_spec import brep  # noqa: E402

pytestmark = pytest.mark.geometry


# --------------------------------------------------------------------------- fixtures


def _valid_cylinder():
    """The healthy twin: the same core, never fused with a degenerate sweep."""
    return cq.Workplane("XY").circle(6).extrude(9.0)


@functools.lru_cache(maxsize=1)
def _degenerate_helix_fuse():
    """The tripod-hub recipe: ribs swept along a helix of radius 1e-6, 4.5 turns.

    Confirmed invalid on this OCCT build (`face: UnorientableShape`). If a future kernel
    ever fuses this cleanly the assertion below will say so out loud rather than the test
    quietly passing on a shape it no longer exercises — and `_reversed_solid` keeps the
    negative-volume rule covered by construction either way.
    """
    pitch, turns = 2.0, 4.5
    height = pitch * turns
    core = cq.Workplane("XY").circle(6).extrude(height)
    helix = cq.Wire.makeHelix(pitch=pitch, height=height, radius=1e-6)
    rib = (
        cq.Workplane("XZ")
        .center(6, 0)
        .circle(0.6)
        .sweep(cq.Workplane(helix), isFrenet=True)
    )
    return core.union(rib)


def _reversed_solid():
    """A box turned inside out — built with OCP directly, so it is deterministic.

    `TopoDS_Shape.Reversed()` flips orientation without touching the topology, which is
    exactly the inverted shell a bad fuse leaves behind: valid to the analyzer, negative
    in signed volume, and nothing at all to a printer.
    """
    return cq.Shape(cq.Workplane("XY").box(10, 10, 10).val().wrapped.Reversed())


# ------------------------------------------------------------------- the two fixtures


def test_valid_shape_passes_both_gates():
    verdict = brep.check_shape(_valid_cylinder())
    assert verdict.ok
    assert bool(verdict) is True
    assert verdict.analyzer_valid is True
    assert verdict.volume > 0
    assert verdict.negative_solids == []
    assert verdict.problems == []


def test_degenerate_helix_fuse_is_invalid_brep():
    verdict = brep.check_shape(_degenerate_helix_fuse())
    assert verdict.analyzer_valid is False, (
        "the tripod-hub recipe no longer produces an invalid B-Rep on this OCCT build — "
        "the fixture must be re-derived, not deleted"
    )
    assert not verdict.ok
    assert any(p.startswith("invalid B-Rep (BRepCheck):") for p in verdict.problems)


def test_reversed_solid_is_valid_to_the_analyzer_but_fails_on_volume():
    """The reason two gates exist. Drop either and this shape ships."""
    verdict = brep.check_shape(_reversed_solid())
    assert verdict.analyzer_valid is True  # the analyzer alone would wave it through
    assert not verdict.ok
    assert verdict.volume < 0
    assert len(verdict.negative_solids) == 1
    assert any("negative volume" in p for p in verdict.problems)


# ------------------------------------------------------------- status enumeration


def test_status_names_empty_on_a_valid_shape():
    assert brep.status_names(_valid_cylinder()) == []


def test_status_names_are_readable_kind_and_status():
    names = brep.status_names(_degenerate_helix_fuse())
    assert names, "an invalid shape must name at least one failing sub-shape"
    for line in names:
        # "<kind>: <Status>" — the OCCT enum prefix is stripped, never printed raw.
        assert "BRepCheck_" not in line
        assert ": " in line or line.startswith("(+")


def test_status_names_are_capped_and_say_what_was_elided(monkeypatch):
    """A shape with many distinct statuses must not print a wall of them."""
    monkeypatch.setattr(brep, "MAX_STATUS_LINES", 1)
    names = brep.status_names(_degenerate_helix_fuse())
    assert len(names) <= 2  # the one kept line, plus at most the elision note
    if len(names) == 2:
        assert names[1].startswith("(+") and "more status kind(s)" in names[1]


def test_status_names_count_repeats_rather_than_repeating_them():
    """Two identical faults on two faces read as one line with ×2, not two lines."""
    names = brep.status_names(_degenerate_helix_fuse())
    assert len(names) == len(set(names))


# ------------------------------------------------------------- the volume rule


def test_signed_volumes_positive_on_a_solid():
    total, negative = brep.signed_volumes(_valid_cylinder())
    assert total > 0
    assert negative == []


def test_signed_volumes_negative_on_a_reversed_solid():
    total, negative = brep.signed_volumes(_reversed_solid())
    assert total < 0
    assert negative == [pytest.approx(-1000.0, abs=1e-6)]


def test_one_inverted_solid_inside_a_positive_compound_still_fails():
    """The reason the walk is per-solid and not a check on the total.

    A big correct solid plus a small inverted one sums to a comfortable positive number.
    Trusting the total would call that healthy and hand Linux the segfault anyway.
    """
    big = cq.Workplane("XY").box(50, 50, 50).val().wrapped
    small = cq.Workplane("XY").box(5, 5, 5).translate((100, 0, 0)).val().wrapped
    compound = cq.Compound.makeCompound(
        [cq.Shape(big), cq.Shape(small.Reversed())]
    )

    total, negative = brep.signed_volumes(compound)
    assert total > 0, "the total is positive — which is exactly the trap"
    assert len(negative) == 1
    assert negative[0] == pytest.approx(-125.0, abs=1e-6)

    verdict = brep.check_shape(compound)
    assert not verdict.ok
    assert any("inverted shell inside the compound" in p for p in verdict.problems)


def test_near_zero_volume_is_not_called_inverted():
    """Floating-point noise around zero is not an inversion claim."""
    assert brep.NEGATIVE_VOLUME_EPS > 0


# ------------------------------------------------------------------- result plumbing


def test_check_result_on_a_plain_workplane_is_one_unnamed_target():
    verdicts = brep.check_result(_valid_cylinder())
    assert len(verdicts) == 1
    label, verdict = verdicts[0]
    assert label == ""
    assert verdict.ok


def test_check_result_names_each_assembly_member():
    assembly = (
        cq.Assembly()
        .add(_valid_cylinder(), name="good")
        .add(_reversed_solid(), name="bad")
    )
    by_name = dict(brep.check_result(assembly))
    assert by_name["good"].ok
    assert not by_name["bad"].ok


def test_brep_available_is_true_where_the_geometry_extra_is():
    assert brep.brep_available() is True
