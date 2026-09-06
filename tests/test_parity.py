"""Cross-kernel parity: the gate logic, and one real dual-engine cartridge.

The gate tests build synthetic meshes rather than rendering, so the three thresholds
and the conjunctive warn tier are exercised without a CAD kernel deciding what the
numbers are. They still need trimesh (the gates take meshes), so they carry the
`geometry` marker like the rest of the render lane.

The integration test renders the bundled `dual-block` fixture on BOTH kernels and
compares them for real, plus its divergent twin, which must FAIL. A gate never
exercised in the failing direction is a gate nobody can trust.

The G38 block at the end tests the per-part exemption policy on that same divergent
geometry: an exemption over a pair that would have passed anyway proves nothing, so the
exempt and widened-tolerance fixtures are the divergent one with a manifest bolted on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from y4d_spec.cli import main
from y4d_spec.conformance import check_cartridge, check_manifest
from y4d_spec.geometry import openscad_binary, reset_openscad_probe
from y4d_spec.parity import (
    AABB_WARN_BAND,
    PARITY_TOLERANCE,
    ParityCheck,
    compare_meshes,
    pair_renders,
    parity_checks,
    resolve_parity_policy,
)
from y4d_spec.rules import verification_rules

FIXTURES = Path(__file__).parent / "fixtures" / "y4d"
DUAL_BLOCK = FIXTURES / "dual-block"
DUAL_DIVERGENT = FIXTURES / "dual-block-divergent"
#: The divergent fixture's geometry with the part declared exempt (G38).
DUAL_EXEMPT = FIXTURES / "dual-block-exempt"
#: A 0.1mm divergence with a manifest tolerance of 0.2mm (G38).
DUAL_WIDENED = FIXTURES / "dual-block-widened"

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
    assert "parity=3/3 ok, warn=0, exempt=0, failures=0" in out
    assert "3 parity pair(s) agree" in out
    assert "parity (block, block): ok" in out


@pytest.mark.geometry
@needs_openscad
def test_a_parity_failure_is_counted_and_exits_nonzero(capsys):
    assert main(["check", "--render", "--parity", str(DUAL_DIVERGENT)]) == 1
    out = capsys.readouterr().out
    assert "parity=0/1 ok, warn=0, exempt=0, failures=1" in out


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


# --- the per-part exemption policy (G38) ---------------------------------------
#
# Three layers, tested separately because they fail separately: the SCHEMA accepts or
# rejects the declaration, `resolve_parity_policy` decides which declaration is in
# force, and the render lane turns that into a line and a count. A policy that
# resolves correctly but never reaches the output is a policy nobody can see, which is
# the exact failure mode the whole ruling exists to prevent.


def _manifest_with(verification: dict) -> dict:
    """The divergent fixture's manifest with a `verification` block spliced in."""
    import json

    doc = json.loads((DUAL_DIVERGENT / "project.json").read_text(encoding="utf-8"))
    doc["verification"] = verification
    return doc


def _base(policy: dict) -> dict:
    return {"stages": {"geometry": {"checks": {"parity": policy}}}}


def _per_part(mode: str, part: str, policy: dict) -> dict:
    return {
        "stages": {"geometry": {"checks": {}}},
        "mode_overrides": {mode: {"part_overrides": {part: {"geometry.parity": policy}}}},
    }


# --- schema ---------------------------------------------------------------------


def _schema_errors(doc: dict) -> list[str]:
    from jsonschema import Draft202012Validator

    import hyperobjects_schemas as hs

    return [e.message for e in Draft202012Validator(hs.load("project-manifest")).iter_errors(doc)]


def test_the_schema_accepts_a_reasoned_exemption():
    doc = _manifest_with(_per_part("block", "block", {"enabled": False, "reason": "BOSL2 helix"}))
    assert _schema_errors(doc) == []


def test_the_schema_rejects_an_exemption_with_no_reason():
    doc = _manifest_with(_per_part("block", "block", {"enabled": False}))
    assert any("reason" in m for m in _schema_errors(doc))


def test_the_schema_rejects_an_empty_reason():
    """An empty string is not an explanation, and the schema says so before the rule
    does — a `reason` field satisfied by `""` would make the whole mechanism optional."""
    doc = _manifest_with(_per_part("block", "block", {"enabled": False, "reason": ""}))
    assert _schema_errors(doc)


def test_the_schema_rejects_an_unknown_key_in_the_policy():
    """`additionalProperties: false` so a typo'd `reasons`/`enable` is caught here and
    not read as an unreasoned exemption at resolution time."""
    doc = _manifest_with(_per_part("block", "block", {"enable": False, "reason": "typo"}))
    assert _schema_errors(doc)


def test_the_schema_rejects_a_nonpositive_tolerance():
    doc = _manifest_with(_base({"tolerance": 0, "reason": "x"}))
    assert _schema_errors(doc)


def test_the_schema_accepts_the_base_declaration():
    assert _schema_errors(_manifest_with(_base({"enabled": True}))) == []


# --- the conformance rule -------------------------------------------------------


def test_an_unreasoned_exemption_is_a_conformance_failure_without_render():
    """The whole point: caught by a manifest-only check, in seconds, with no kernel.

    If the reason were only checked where the comparison runs, a cartridge could switch
    the comparison off and thereby switch off the check on switching it off.
    """
    result = check_manifest(_manifest_with(_per_part("block", "block", {"enabled": False})))
    assert not result.ok
    assert any("visible debt" in p and "G38" in p for p in result.problems)


def test_a_reasoned_exemption_is_conformant():
    doc = _manifest_with(
        _per_part("block", "block", {"enabled": False, "reason": "BOSL2 helical thread"})
    )
    assert check_manifest(doc).ok, check_manifest(doc).problems


def test_a_whitespace_reason_does_not_count():
    problems = verification_rules(
        _manifest_with(_per_part("block", "block", {"enabled": False, "reason": "   "}))
    )
    assert any("without a `reason`" in p for p in problems)


def test_a_widened_tolerance_needs_a_reason():
    problems = verification_rules(_manifest_with(_base({"tolerance": 0.06})))
    assert len(problems) == 1
    assert "widened to 0.06mm" in problems[0]
    assert "G38" in problems[0]


def test_a_tightened_tolerance_needs_no_reason():
    """Tightening makes the bar stricter and owes nobody an explanation."""
    assert verification_rules(_manifest_with(_base({"tolerance": 0.0005}))) == []


def test_the_default_written_longhand_is_not_a_departure():
    assert verification_rules(_manifest_with(_base({"enabled": True}))) == []


def test_a_manifest_with_no_verification_block_says_nothing():
    import json

    assert verification_rules(json.loads((DUAL_BLOCK / "project.json").read_text())) == []


def test_a_malformed_policy_is_reported_not_obeyed():
    """A typo'd `enabled` must never read as permission."""
    problems = verification_rules(_manifest_with(_base({"enabled": "false"})))
    assert any("must be a boolean" in p for p in problems)
    # ...and resolution keeps the gate ON.
    doc = _manifest_with(_base({"enabled": "false"}))
    assert resolve_parity_policy(doc, "block", "block").enabled


# --- resolution precedence ------------------------------------------------------


def test_a_silent_manifest_resolves_to_the_default():
    policy = resolve_parity_policy({}, "block", "block")
    assert policy.enabled and policy.tolerance is None and policy.source == "default"


def test_the_base_declaration_applies_to_every_part():
    doc = _manifest_with(_base({"enabled": False, "reason": "both parts, one idiom"}))
    for part in ("block", "plate", "anything"):
        policy = resolve_parity_policy(doc, "block", part)
        assert not policy.enabled
        assert policy.source == "base"


def test_a_part_override_beats_the_base():
    doc = _manifest_with(_base({"enabled": True}))
    off = {"enabled": False, "reason": "r"}
    doc["verification"]["mode_overrides"] = {
        "block": {"part_overrides": {"block": {"geometry.parity": off}}}
    }
    assert not resolve_parity_policy(doc, "block", "block").enabled
    # ...and only for that (mode, part).
    assert resolve_parity_policy(doc, "block", "plate").enabled
    assert resolve_parity_policy(doc, "other", "block").enabled


def test_the_part_override_replaces_the_base_object_whole():
    """It does not merge: a base `reason` must not justify an override that says nothing.

    One block carries the whole policy for a part, so a reader who finds it need not go
    hunting for a second one that silently supplies half the answer.
    """
    doc = _manifest_with(_base({"enabled": True, "tolerance": 0.06, "reason": "base reason"}))
    doc["verification"]["mode_overrides"] = {
        "block": {"part_overrides": {"block": {"geometry.parity": {"enabled": True}}}}
    }
    policy = resolve_parity_policy(doc, "block", "block")
    assert policy.tolerance is None
    assert policy.reason == ""
    assert policy.source == "mode_overrides.block"


def test_a_mode_override_with_no_part_overrides_falls_through_to_the_base():
    doc = _manifest_with(_base({"enabled": False, "reason": "r"}))
    doc["verification"]["mode_overrides"] = {"block": {"stages": ["geometry"]}}
    assert resolve_parity_policy(doc, "block", "block").source == "base"


# --- the reported line ----------------------------------------------------------


def test_an_exempt_check_prints_its_reason_and_is_ok():
    check = ParityCheck(mode="m", part="p", ok=True, exempt=True, reason="BOSL2 helix")
    assert check.summary == "parity (m, p): exempt — BOSL2 helix"
    assert check.ok


def test_a_widened_tolerance_is_printed_in_the_line():
    """A pair judged at a wider bar did not clear the bar the others did, and a line
    that does not say so overstates what was proven."""
    ok = ParityCheck(mode="m", part="p", ok=True, effective_tolerance=0.2, reason="fine")
    assert ok.summary == "parity (m, p): ok (tolerance 0.2mm) — fine"
    bad = ParityCheck(mode="m", part="p", ok=False, effective_tolerance=0.2, reason="nope")
    assert bad.summary == "parity (m, p): FAIL (tolerance 0.2mm) — nope"


def test_the_run_wide_tolerance_is_not_repeated_in_every_line():
    assert ParityCheck(mode="m", part="p", reason="x").summary == "parity (m, p): ok — x"


@pytest.mark.geometry
def test_an_exempt_pair_is_never_compared():
    """No mesh is loaded for an exempt pair — the STL paths are nonsense on purpose."""
    renders = [
        _FakeCheck("block", "block", "openscad", stl_path="/nonexistent/a.stl"),
        _FakeCheck("block", "block", "cadquery", stl_path="/nonexistent/b.stl"),
    ]
    doc = _manifest_with(_per_part("block", "block", {"enabled": False, "reason": "declared"}))
    checks = parity_checks(renders, PARITY_TOLERANCE, doc)
    assert len(checks) == 1
    assert checks[0].exempt and checks[0].ok
    assert checks[0].reason == "declared"
    # Nothing was measured, and the report says so rather than reporting a zero delta.
    assert checks[0].report == {}


@pytest.mark.geometry
def test_without_a_doc_every_pair_is_still_compared():
    """The pre-G38 behaviour is exactly what a caller who passes no manifest gets."""
    renders = [
        _FakeCheck("block", "block", "openscad", stl_path="/nonexistent/a.stl"),
        _FakeCheck("block", "block", "cadquery", stl_path="/nonexistent/b.stl"),
    ]
    checks = parity_checks(renders, PARITY_TOLERANCE)
    assert not checks[0].exempt
    assert not checks[0].ok  # the meshes do not exist, so it fails to load — a failure


# --- the render lane, end to end ------------------------------------------------


@pytest.mark.geometry
@needs_openscad
def test_a_declared_exemption_turns_a_real_failure_into_a_note():
    """Same two meshes as the divergent twin; only the manifest differs."""
    result = check_cartridge(DUAL_EXEMPT, render=True, printability=False, parity=True)
    assert result.ok, result.problems
    assert len(result.parity) == 1
    assert result.parity_failures == []
    assert result.parity_warnings == []
    assert len(result.parity_exemptions) == 1
    note = result.parity_exemptions[0].summary
    assert note.startswith("parity (block, block): exempt — ")
    assert "BOSL2" in note
    # An exemption is never silent: it lands in the notes, on every run.
    assert note in result.notes


@pytest.mark.geometry
@needs_openscad
def test_the_summary_counts_exemptions_separately_from_agreement(capsys):
    """N+K+E+J = M — an exemption must not shrink the denominator."""
    assert main(["check", "--render", "--parity", "-v", str(DUAL_EXEMPT)]) == 0
    out = capsys.readouterr().out
    assert "parity=0/1 ok, warn=0, exempt=1, failures=0" in out
    assert "1 parity pair(s) agree (1 exempt)" in out
    assert "parity (block, block): exempt — " in out


@pytest.mark.geometry
@needs_openscad
def test_a_widened_tolerance_turns_a_real_failure_into_an_ok(capsys):
    """0.1mm is over the faceting band, so the default run fails; 0.2mm clears it.

    The FAILING half is shown on the same two meshes with the manifest's own tolerance
    removed — the check_cartridge STLs die with the call, so the comparison is re-run
    against a policy-free manifest rather than against retained paths.
    """
    import json

    # The 0.2mm the manifest declares is what makes this pass, and nothing else.
    doc = json.loads((DUAL_WIDENED / "project.json").read_text(encoding="utf-8"))
    declared = doc["verification"]["mode_overrides"]["block"]["part_overrides"]["block"][
        "geometry.parity"
    ]
    assert declared["tolerance"] == 0.2
    assert declared["reason"].strip()

    assert main(["check", "--render", "--parity", "-v", str(DUAL_WIDENED)]) == 0
    out = capsys.readouterr().out
    assert "parity=1/1 ok, warn=0, exempt=0, failures=0" in out
    assert "parity (block, block): ok (tolerance 0.2mm) — " in out


@pytest.mark.geometry
@needs_openscad
def test_the_widened_fixture_fails_at_the_default_tolerance(capsys):
    """The other half of the claim: without the manifest's tolerance it is red.

    A tolerance that widens nothing would let the previous test pass on a cartridge
    that was fine all along, so the same geometry is run with `--parity-tolerance` back
    at the package default, which overrides the manifest for every pair.
    """
    assert (
        main(
            [
                "check",
                "--render",
                "--parity",
                "--parity-tolerance",
                str(PARITY_TOLERANCE),
                "-v",
                str(DUAL_WIDENED),
            ]
        )
        == 1
    )
    out = capsys.readouterr().out
    assert "parity=0/1 ok, warn=0, exempt=0, failures=1" in out
    assert "Bounding boxes differ by 0.100000mm" in out


@pytest.mark.geometry
@needs_openscad
def test_the_divergent_twin_still_fails_with_the_new_summary(capsys):
    """The default path is unchanged: no verification block, no exemption, still red."""
    assert main(["check", "--render", "--parity", str(DUAL_DIVERGENT)]) == 1
    assert "parity=0/1 ok, warn=0, exempt=0, failures=1" in capsys.readouterr().out


@pytest.mark.geometry
def test_an_explicit_cli_tolerance_beats_a_manifest_one():
    """`--parity-tolerance 0.001` must actually show the cartridge at 0.001mm."""
    renders = [
        _FakeCheck("block", "block", "openscad", stl_path="/nonexistent/a.stl"),
        _FakeCheck("block", "block", "cadquery", stl_path="/nonexistent/b.stl"),
    ]
    doc = _manifest_with(_base({"tolerance": 0.2, "reason": "declared"}))
    # Inherited default: the manifest's 0.2mm is in force and is printed.
    assert parity_checks(renders, PARITY_TOLERANCE, doc)[0].effective_tolerance == 0.2
    # Named on the command line: the flag wins and nothing claims a wider bar.
    named = parity_checks(renders, PARITY_TOLERANCE, doc, tolerance_is_explicit=True)
    assert named[0].effective_tolerance is None


@pytest.mark.geometry
def test_a_cli_tolerance_does_not_override_an_exemption():
    """An exemption says the comparison is meaningless, which no number answers."""
    renders = [
        _FakeCheck("block", "block", "openscad", stl_path="/nonexistent/a.stl"),
        _FakeCheck("block", "block", "cadquery", stl_path="/nonexistent/b.stl"),
    ]
    doc = _manifest_with(_per_part("block", "block", {"enabled": False, "reason": "idiom"}))
    checks = parity_checks(renders, 10.0, doc, tolerance_is_explicit=True)
    assert checks[0].exempt
