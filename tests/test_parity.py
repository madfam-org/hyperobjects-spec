"""Cross-kernel parity: the gate logic, and one real dual-engine cartridge.

The gate tests build synthetic meshes rather than rendering, so the three thresholds
and the conjunctive warn tier are exercised without a CAD kernel deciding what the
numbers are. They still need trimesh (the gates take meshes), so they carry the
`geometry` marker like the rest of the render lane.

The integration test renders the bundled `dual-block` fixture on BOTH kernels and
compares them for real, plus its divergent twin, which must FAIL. A gate never
exercised in the failing direction is a gate nobody can trust.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from y4d_spec.cli import main
from y4d_spec.conformance import check_cartridge
from y4d_spec.geometry import openscad_binary, reset_openscad_probe
from y4d_spec.parity import (
    AABB_WARN_BAND,
    PARITY_TOLERANCE,
    ParityCheck,
    compare_meshes,
    pair_renders,
)

FIXTURES = Path(__file__).parent / "fixtures" / "y4d"
DUAL_BLOCK = FIXTURES / "dual-block"
DUAL_DIVERGENT = FIXTURES / "dual-block-divergent"

HAVE_OPENSCAD = openscad_binary() is not None
needs_openscad = pytest.mark.skipif(
    not HAVE_OPENSCAD, reason="no OpenSCAD binary on this machine"
)


def _box(x: float, y: float, z: float):
    """A watertight axis-aligned box, centred at the origin."""
    import trimesh

    return trimesh.creation.box(extents=(x, y, z))


def _shifted_wall(x: float, y: float, z: float, dx: float):
    """A box whose +X wall alone is moved out by `dx`.

    This is a DIMENSIONAL error, not a tessellation one: the AABB grows by `dx` and a
    surface moves by `dx`. It is the shape the warn tier must refuse to rescue when
    `dx` lands inside the faceting band, and the reason the tier is conjunctive rather
    than a bare band.
    """
    import numpy as np

    mesh = _box(x, y, z)
    verts = np.array(mesh.vertices, dtype=float)
    verts[verts[:, 0] > 0, 0] += dx
    mesh.vertices = verts
    return mesh


def _faceted_pair(delta: float):
    """Two meshes whose AABBs differ by `delta` but whose SURFACES coincide.

    This is what OpenSCAD `$fn` chord error looks like to the gates: a circle
    approximated by a polygon has a slightly smaller bounding box than the analytic
    circle, while every point of either surface is a hair from the other. Built here
    as a cylinder at two facet counts, which is literally that.
    """
    import trimesh

    a = trimesh.creation.cylinder(radius=10.0, height=10.0, sections=256)
    b = trimesh.creation.cylinder(radius=10.0, height=10.0, sections=256)
    # Scale B's X/Y so its AABB is exactly `delta` larger — a chord-error-shaped
    # difference of a known size, rather than one that depends on trimesh's
    # tessellation happening to land where the test wants it.
    scale = (20.0 + delta) / 20.0
    b.apply_scale((scale, scale, 1.0))
    return a, b


# --- gate 1: AABB extents -----------------------------------------------------


@pytest.mark.geometry
def test_identical_meshes_agree():
    agree, warn, reason, report = compare_meshes(_box(10, 10, 10), _box(10, 10, 10))
    assert agree
    assert not warn
    assert report["aabb_delta_mm"] == pytest.approx(0.0)
    assert "identical" in reason


@pytest.mark.geometry
def test_small_delta_with_surfaces_agreeing_is_a_warn():
    """0.03mm — inside the 0.05mm band — and the surfaces coincide: chord error."""
    a, b = _faceted_pair(0.03)
    agree, warn, reason, report = compare_meshes(a, b)
    assert agree, reason
    assert warn
    assert report["aabb_warn"]
    assert report["aabb_delta_mm"] == pytest.approx(0.03, abs=1e-6)
    assert report["hausdorff_proxy_mm"] is not None
    assert report["hausdorff_proxy_mm"] <= 0.5
    # The parsed prefix survives onto a PASSING pair — the sweep reports read it.
    assert reason.startswith("Bounding boxes differ by 0.030000mm")
    assert "faceting warn" in reason


@pytest.mark.geometry
def test_small_delta_with_surfaces_diverging_is_a_failure():
    """The conjunctive half of G27: 0.03mm is inside the band, but a wall MOVED.

    A bare band would pass this. A real dimensional error of this size is exactly what
    the band would hide, which is why the tier requires the surfaces to agree as well.
    """
    a = _box(10, 10, 10)
    # 0.03mm of AABB from moving one wall 0.03mm, plus a wall pushed far enough out
    # elsewhere that the Hausdorff proxy exceeds 0.5mm while the AABB does not grow.
    b = _shifted_wall(10, 10, 10, 0.03)
    import numpy as np

    verts = np.array(b.vertices, dtype=float)
    # Pull the -X wall's vertices 0.9mm inward in Y: a surface that moves without
    # changing the bounding box, so gate 1 stays inside the band and gate 3 refuses.
    inner = verts[:, 0] < 0
    verts[inner, 1] *= 0.82
    b.vertices = verts

    agree, warn, reason, report = compare_meshes(a, b)
    assert not agree, reason
    assert not warn
    assert report["aabb_delta_mm"] == pytest.approx(0.03, abs=1e-6)
    assert "surfaces diverge too" in reason


@pytest.mark.geometry
def test_delta_above_the_band_fails():
    """0.6mm — an order of magnitude past the band. Nothing rescues it."""
    agree, warn, reason, report = compare_meshes(_box(10, 10, 10), _box(10.6, 10, 10))
    assert not agree
    assert not warn
    assert report["aabb_delta_mm"] == pytest.approx(0.6)
    assert reason.startswith("Bounding boxes differ by 0.600000mm")
    assert "A: [10.0, 10.0, 10.0]" in reason
    assert "B: [10.6, 10.0, 10.0]" in reason
    # Above the band the surfaces are never consulted — the platform short-circuits
    # there and so does this, so the proxy stays unmeasured.
    assert report["hausdorff_proxy_mm"] is None


@pytest.mark.geometry
def test_an_unmeasurable_surface_is_not_a_pass(monkeypatch):
    """None is the absence of evidence, and the warn tier needs positive evidence."""
    monkeypatch.setattr("y4d_spec.parity._hausdorff_proxy", lambda _a, _b: None)
    a, b = _faceted_pair(0.03)
    agree, warn, reason, _report = compare_meshes(a, b)
    assert not agree
    assert not warn
    assert "could not be measured" in reason


# --- gate 2: volume -----------------------------------------------------------


def _stepped(fraction: float):
    """An L-prism whose AABB is exactly 10 x 10 x 10 but which encloses less of it.

    Gate 2 has to be reachable with the AABB gate silent, which means a volume
    difference that does NOT move the bounding box — and gate 2 only runs when both
    sides are watertight, so the solid has to be a real closed one. A boolean
    subtraction would be the obvious way and is not available: trimesh's boolean
    engines (manifold3d, blender) and shapely's extruder are all outside the
    `[geometry]` extra, and adding a dependency so a test can build a fixture is the
    wrong trade. So the L is built by hand — a six-point XZ polygon swept along Y —
    which is a handful of lines and depends on nothing.
    """
    import numpy as np
    import trimesh

    h = 5.0  # height at which the step happens
    inset = 1000.0 * fraction / (10.0 * (10.0 - h))  # X given up above the step
    # XZ cross-section, counter-clockwise. Corner-to-corner it still spans 10 x 10.
    xz = [(-5, -5), (5, -5), (5, -5 + h), (5 - inset, -5 + h), (5 - inset, 5), (-5, 5)]
    n = len(xz)

    verts = np.array(
        [(x, y, z) for y in (-5.0, 5.0) for (x, z) in xz], dtype=float
    )
    faces = []
    for i in range(n):  # the swept side walls
        j = (i + 1) % n
        faces += [[i, n + j, j], [i, n + i, n + j]]
    for i in range(1, n - 1):  # the two end caps, fan-triangulated
        faces += [[0, i, i + 1], [n, n + i + 1, n + i]]

    mesh = trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=False)
    mesh.merge_vertices()
    assert mesh.is_watertight and mesh.volume > 0, "fixture is not a closed solid"
    assert np.allclose(mesh.extents, (10.0, 10.0, 10.0), atol=1e-9), mesh.extents
    return mesh


@pytest.mark.geometry
def test_volume_delta_over_two_percent_fails():
    """4% of volume, with the AABB left alone: gate 2 on its own."""
    outer = _box(10, 10, 10)
    stepped = _stepped(0.04)
    rel = abs(outer.volume - stepped.volume) / outer.volume
    assert rel == pytest.approx(0.04, abs=0.002), f"fixture drifted: {rel * 100:.2f}%"

    agree, warn, reason, report = compare_meshes(outer, stepped)
    assert not agree
    assert not warn
    assert report["aabb_delta_mm"] == pytest.approx(0.0, abs=1e-9)
    assert reason.startswith("Volumes differ by ")
    assert "mm^3 (" in reason


@pytest.mark.geometry
def test_volume_delta_under_two_percent_passes():
    """The 2% allowance is real: a 1% pinch is agreement, not divergence.

    Note the surfaces here diverge by more than 0.5mm, so gate 3 records a warn — and
    the pair still PASSES, which is exactly the platform's posture: gate 3 on its own
    never fails anything.
    """
    outer = _box(10, 10, 10)
    stepped = _stepped(0.01)
    rel = abs(outer.volume - stepped.volume) / outer.volume
    assert rel < 0.02, f"fixture drifted: {rel * 100:.2f}%"

    agree, warn, reason, report = compare_meshes(outer, stepped)
    assert agree, reason
    assert not warn  # a gate-3 note is not the gate-1 faceting warn
    assert report["volume_delta_mm3"] is not None


# --- tolerance ----------------------------------------------------------------


@pytest.mark.geometry
def test_parity_tolerance_widens_gate_one_only():
    """--parity-tolerance moves the AABB gate and leaves the band and volume alone."""
    a, b = _box(10, 10, 10), _box(10.02, 10, 10)
    # At the default this is inside the band and the surfaces agree, so it WARNS.
    agree, warn, _reason, report = compare_meshes(a, b, PARITY_TOLERANCE)
    assert agree
    assert warn
    assert report["aabb_warn"]
    # Raised above the delta, gate 1 does not fire at all — not even a warn.
    agree, warn, _reason, report = compare_meshes(a, b, 0.05)
    assert agree
    assert not warn
    assert not report["aabb_warn"]
    # And the proxy was never needed, so it was never measured.
    assert report["hausdorff_proxy_mm"] is not None  # gate 3 still runs on a pass


@pytest.mark.geometry
def test_the_band_is_not_scaled_by_the_tolerance():
    """A widened tolerance must not silently widen the faceting band with it."""
    a, b = _box(10, 10, 10), _box(10 + AABB_WARN_BAND * 2, 10, 10)
    agree, _warn, reason, _report = compare_meshes(a, b, 0.01)
    assert not agree
    assert "Bounding boxes differ by" in reason


# --- pairing ------------------------------------------------------------------


class _FakeCheck:
    def __init__(self, mode, part, engine, *, preset=None, ok=True, stl_path="x.stl"):
        self.mode, self.part, self.engine = mode, part, engine
        self.preset, self.ok, self.stl_path = preset, ok, stl_path


def test_pairs_need_both_engines():
    renders = [
        _FakeCheck("m", "p", "cadquery"),
        _FakeCheck("m", "p", "openscad"),
        _FakeCheck("solo", "p", "cadquery"),
    ]
    pairs = pair_renders(renders)
    assert len(pairs) == 1
    assert pairs[0][0].engine == "openscad"  # A side first, as the platform prints it
    assert pairs[0][1].engine == "cadquery"


def test_a_preset_pairs_with_its_own_preset_only():
    renders = [
        _FakeCheck("m", "p", "cadquery"),
        _FakeCheck("m", "p", "openscad"),
        _FakeCheck("m", "p", "cadquery", preset="big"),
        _FakeCheck("m", "p", "openscad", preset="big"),
    ]
    pairs = pair_renders(renders)
    assert len(pairs) == 2
    assert {p[0].preset for p in pairs} == {None, "big"}


def test_a_skipped_or_failed_side_yields_no_pair():
    """Comparing against a mesh that was never produced is not evidence of agreement."""
    renders = [
        _FakeCheck("m", "p", "cadquery"),
        _FakeCheck("m", "p", "openscad", stl_path=None),  # skipped: no binary
        _FakeCheck("n", "p", "cadquery"),
        _FakeCheck("n", "p", "openscad", ok=False),  # rendered, but broken
    ]
    assert pair_renders(renders) == []


def test_parity_check_summary_shapes():
    assert ParityCheck("m", "p", reason="r").summary == "parity (m, p): ok — r"
    assert ParityCheck("m", "p", warn=True, reason="r").summary == (
        "parity (m, p): warn (faceting) — r"
    )
    assert ParityCheck("m", "p", preset="big", ok=False, reason="r").summary == (
        "parity (m, p, preset 'big'): FAIL — r"
    )


# --- CLI wiring ---------------------------------------------------------------


def test_parity_without_render_is_refused(capsys):
    assert main(["check", "--parity", str(DUAL_BLOCK)]) == 2
    assert "only apply with --render" in capsys.readouterr().out


def test_parity_tolerance_without_parity_is_refused(capsys):
    assert main(["check", "--render", "--parity-tolerance", "0.01", str(DUAL_BLOCK)]) == 2
    assert "--parity-tolerance only applies with --parity" in capsys.readouterr().out


def test_a_nonpositive_tolerance_is_refused(capsys):
    argv = ["check", "--render", "--parity", "--parity-tolerance", "0", str(DUAL_BLOCK)]
    assert main(argv) == 2
    assert "must be > 0" in capsys.readouterr().out


# --- integration: a real dual-engine cartridge --------------------------------


@pytest.fixture(autouse=True)
def _clean_probe():
    reset_openscad_probe()
    yield
    reset_openscad_probe()


@pytest.mark.geometry
@needs_openscad
def test_dual_engine_fixture_agrees_on_both_kernels():
    result = check_cartridge(DUAL_BLOCK, render=True, printability=False, parity=True)
    assert result.ok, result.problems
    assert result.parity_ran
    # block + plate defaults, plus the big_block preset.
    assert len(result.parity) == 3, [c.summary for c in result.parity]
    assert result.parity_failures == []
    assert result.parity_warnings == []
    for check in result.parity:
        assert check.report["aabb_delta_mm"] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.geometry
@needs_openscad
def test_the_divergent_twin_fails_parity_while_both_sides_render():
    """Both kernels produce a valid solid; they are not the same solid.

    This is the whole case for the flag: `--render` alone is green here.
    """
    without = check_cartridge(DUAL_DIVERGENT, render=True, printability=False)
    assert without.ok, without.problems
    assert not without.parity_ran

    withp = check_cartridge(DUAL_DIVERGENT, render=True, printability=False, parity=True)
    assert not withp.ok
    assert len(withp.parity_failures) == 1
    reason = withp.parity_failures[0].reason
    assert reason.startswith("Bounding boxes differ by 0.600000mm")
    assert any(p.startswith("parity (block, block): FAIL") for p in withp.problems)


@pytest.mark.geometry
@needs_openscad
def test_parity_summary_line_counts_the_pairs(capsys):
    assert main(["check", "--render", "--parity", "-v", str(DUAL_BLOCK)]) == 0
    out = capsys.readouterr().out
    assert "parity=3/3 ok, warn=0, failures=0" in out
    assert "3 parity pair(s) agree" in out
    assert "parity (block, block): ok" in out


@pytest.mark.geometry
@needs_openscad
def test_a_parity_failure_is_counted_and_exits_nonzero(capsys):
    assert main(["check", "--render", "--parity", str(DUAL_DIVERGENT)]) == 1
    out = capsys.readouterr().out
    assert "parity=0/1 ok, warn=0, failures=1" in out


@pytest.mark.geometry
@needs_openscad
def test_a_single_engine_cartridge_says_it_had_nothing_to_compare(capsys):
    """Silence would read exactly like a cartridge whose kernels were compared."""
    assert main(["check", "--render", "--parity", str(FIXTURES / "scad-block")]) == 0
    assert "no dual-engine pair to compare" in capsys.readouterr().out


@pytest.mark.geometry
@needs_openscad
def test_without_parity_nothing_is_compared_and_no_stl_is_retained():
    """The default path is byte-for-byte what it was: no comparison, no retention."""
    result = check_cartridge(DUAL_DIVERGENT, render=True, printability=False)
    assert result.ok
    assert result.parity == []
    assert not result.parity_ran
    assert all(getattr(c, "stl_path", None) is None for c in result.renders)


@pytest.mark.geometry
@needs_openscad
def test_retained_stls_do_not_outlive_the_check():
    """The meshes are evidence for one comparison, not an artifact left on disk."""
    result = check_cartridge(DUAL_BLOCK, render=True, printability=False, parity=True)
    paths = [c.stl_path for c in result.renders if c.stl_path]
    assert paths, "parity needs retained STLs"
    assert not any(Path(p).exists() for p in paths)
