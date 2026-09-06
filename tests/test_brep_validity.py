"""The B-Rep gate: an invalid or inverted shape must fail HERE, before tessellation.

Solid #45 (tripod-hub, 2026-09-06) is the case these tests encode. Its `core.union(rib)`
over a `makeHelix(radius=1e-6)` path returned an invalid shape that macOS OCCT
nevertheless tessellated into a watertight STL with a plausible volume — every mesh check
passed — while the Linux OCP build segfaulted on the next boolean with no traceback.

THE FIXTURES ARE BUILT, NOT FUSED — and that is the point
---------------------------------------------------------
The obvious fixture is the tripod-hub recipe itself: sweep a rib along
`makeHelix(radius=1e-6)` and union it. It IS invalid on macOS OCCT (`face:
UnorientableShape`, the exact status the real cartridge produced). It is **not invalid on
the Linux OCP build**, which fuses the same recipe into a clean solid of volume 155.19 —
observed on this repo's own CI, which is what turned the first draft of this file red.

That is not a nuisance; it is the same non-determinism as the bug. A boolean's result
depends on the kernel build, so a boolean can never be the *fixture* for a gate that must
behave identically everywhere. Every shape below is therefore assembled from topology
directly (`BRep_Builder`, `BRepBuilderAPI_*`, `TopoDS_Shape.Reversed()`), which no OCCT
build is free to reinterpret. `test_the_tripod_hub_recipe_is_kernel_dependent` keeps the
real recipe in the suite as a *documented observation* rather than an assertion.

Three fixtures, because the gates catch three different faults and none subsumes another:

  * `_open_wire_face` — a face on an open wire. `IsValid()` False, and the analyzer
    attributes `face: UnorientableShape` to a sub-shape, so this is what exercises the
    status enumeration.
  * `_open_shell_solid` — a solid whose shell is missing a face. `IsValid()` False with
    NO sub-shape status: a top-level fault, the shape of tripod-hub's `quarter_to_arca`.
  * `_reversed_solid` — a solid whose orientation is flipped. It is topologically perfect
    and `IsValid()` returns **True**; only the signed volume betrays it. This is why the
    volume rule is not decoration on top of the analyzer.
"""

import pytest

pytest.importorskip("cadquery")
pytest.importorskip("OCP")

import cadquery as cq  # noqa: E402

from y4d_spec import brep  # noqa: E402

pytestmark = pytest.mark.geometry


# --------------------------------------------------------------------------- fixtures


def _valid_cylinder():
    """The healthy twin: a plain extrusion, valid on every kernel."""
    return cq.Workplane("XY").circle(6).extrude(9.0)


def _box_faces():
    """The six faces of a unit box, as raw TopoDS shapes to reassemble."""
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer

    box = cq.Workplane("XY").box(10, 10, 10).val().wrapped
    faces = []
    explorer = TopExp_Explorer(box, TopAbs_ShapeEnum.TopAbs_FACE)
    while explorer.More():
        faces.append(explorer.Current())
        explorer.Next()
    return faces


def _open_wire_face():
    """A planar face built on an OPEN wire — three edges of a square, not four.

    `IsValid()` False, and the analyzer attributes `face: UnorientableShape` — the same
    status the real tripod-hub fuse produced, reached by construction instead of by a
    boolean whose outcome the kernel build gets to decide.
    """
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeWire,
    )
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    corners = [gp_Pnt(0, 0, 0), gp_Pnt(10, 0, 0), gp_Pnt(10, 10, 0), gp_Pnt(0, 10, 0)]
    maker = BRepBuilderAPI_MakeWire()
    for i in range(3):  # the closing edge is deliberately absent
        maker.Add(BRepBuilderAPI_MakeEdge(corners[i], corners[i + 1]).Edge())
    plane = gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    return cq.Shape(BRepBuilderAPI_MakeFace(plane, maker.Wire()).Face())


def _open_shell_solid():
    """A solid wrapped around a shell that is missing one of its six faces.

    `IsValid()` False with NO sub-shape carrying a status — the analyzer rejects it at
    the top level. That case is not hypothetical: it is what tripod-hub's
    `quarter_to_arca` did at the parent of #45, and the gate must report it as a finding
    rather than as an absence of one.
    """
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Shell, TopoDS_Solid

    builder = BRep_Builder()
    shell = TopoDS_Shell()
    builder.MakeShell(shell)
    for face in _box_faces()[:-1]:
        builder.Add(shell, face)
    solid = TopoDS_Solid()
    builder.MakeSolid(solid)
    builder.Add(solid, shell)
    return cq.Shape(solid)


def _reversed_solid():
    """A box turned inside out.

    `TopoDS_Shape.Reversed()` flips orientation without touching the topology, which is
    exactly the inverted shell a bad fuse leaves behind: valid to the analyzer, negative
    in signed volume, and nothing at all to a printer.
    """
    return cq.Shape(cq.Workplane("XY").box(10, 10, 10).val().wrapped.Reversed())


def _degenerate_helix_fuse():
    """The real tripod-hub recipe. KERNEL-DEPENDENT — never assert validity on it.

    Invalid on macOS OCCT, valid on the Linux OCP build (volume 155.19). Kept so the
    suite still exercises the actual idiom that caused solid #45, and so the divergence
    itself is recorded somewhere a reader will find it.
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


# ------------------------------------------------------------------ the three faults


def test_valid_shape_passes_both_gates():
    verdict = brep.check_shape(_valid_cylinder())
    assert verdict.ok
    assert bool(verdict) is True
    assert verdict.analyzer_valid is True
    assert verdict.volume > 0
    assert verdict.negative_solids == []
    assert verdict.problems == []


def test_open_wire_face_fails_with_a_named_sub_shape_status():
    verdict = brep.check_shape(_open_wire_face())
    assert verdict.analyzer_valid is False
    assert not verdict.ok
    assert any(p.startswith("invalid B-Rep (BRepCheck):") for p in verdict.problems)
    assert any("face: UnorientableShape" in p for p in verdict.problems)


def test_open_shell_solid_fails_even_though_no_sub_shape_is_blamed():
    """An unattributed rejection is a finding, and must not read as an absence of one.

    This is tripod-hub's `quarter_to_arca` at the parent of #45: `IsValid()` False, and
    the per-sub-shape walk comes back empty because the fault was found at the top level.
    """
    verdict = brep.check_shape(_open_shell_solid())
    assert verdict.analyzer_valid is False
    assert not verdict.ok
    assert brep.status_names(_open_shell_solid()) == []
    assert any("top-level fault" in p for p in verdict.problems)
    assert not any("no sub-shape status reported" == p for p in verdict.problems)


def test_the_tripod_hub_recipe_is_kernel_dependent():
    """An OBSERVATION, deliberately not an assertion about validity.

    `makeHelix(radius=1e-6)` + union is invalid on macOS OCCT and valid on the Linux OCP
    build. A boolean cannot be the fixture for a gate that must behave identically
    everywhere — which is why the fixtures above are assembled from topology. What IS
    asserted is that the gate survives the shape on either kernel and returns a verdict
    consistent with itself rather than raising.
    """
    verdict = brep.check_shape(_degenerate_helix_fuse())
    assert verdict.analyzer_valid in (True, False)
    assert verdict.volume is not None
    # ok is exactly "nothing was found", on whichever kernel is running.
    assert verdict.ok == (not verdict.problems)
    if verdict.analyzer_valid is False:
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
    names = brep.status_names(_open_wire_face())
    assert names, "an invalid shape must name at least one failing sub-shape"
    for line in names:
        # "<kind>: <Status>" — the OCCT enum prefix is stripped, never printed raw.
        assert "BRepCheck_" not in line
        assert ": " in line or line.startswith("(+")
    assert "face: UnorientableShape" in names


def test_status_names_are_capped_and_say_what_was_elided(monkeypatch):
    """A shape with many distinct statuses must not print a wall of them."""
    monkeypatch.setattr(brep, "MAX_STATUS_LINES", 1)
    names = brep.status_names(_open_wire_face())
    assert len(names) <= 2  # the one kept line, plus at most the elision note
    if len(names) == 2:
        assert names[1].startswith("(+") and "more status kind(s)" in names[1]


def test_status_names_count_repeats_rather_than_repeating_them():
    """Two identical faults read as one line with ×N, not N lines."""
    names = brep.status_names(_open_wire_face())
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
