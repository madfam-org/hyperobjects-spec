"""The mesh gate, report-only (owner rulings M4–M7, 2026-11-22; y4d_spec.mesh_gate).

Pinned here:

  - the strict switch: empty by default (step 1 is report-only), `all`, a list, and a
    refusal of unknown names from the environment and the command line;
  - the structure counts (non-manifold edges, zero-area triangles, duplicate faces) on
    synthetic meshes, under EVERY mesh oracle (`trimesh`, `geomcore`, `both`), with the
    duplicate count read from trimesh under all three;
  - the resolution checks: the OpenSCAD circle fit at the proposal's numbers (48 flats on
    r=59mm fails chord error, 24 on r=2.5mm fails segments, r<1mm is not judged), the
    CadQuery measurement against the solid (126 segments everywhere; a 200mm radius over
    0.05mm), and a polygon prism passing it (that is what the lint is for);
  - the opt-out: precedence (part > mode > cartridge, replaced whole), the required
    reason as a manifest rule, and that it exempts only chord-error and segments;
  - the lint: what it flags and what it leaves alone;
  - through the CLI: notes by default, a failure under `--mesh-strict`, and the summary
    clause that counts cartridges per check.
"""

import json
import shutil
from pathlib import Path

import pytest

from y4d_spec.mesh_gate import (
    CHECKS,
    STRICT_ENV,
    Circle,
    GateFinding,
    MeshGateError,
    Resolution,
    _lint_source,
    apply_policy,
    cartridge_gate,
    mesh_resolution_policy_rules,
    resolution_findings,
    resolve_policy,
    strict_checks,
    summary_clause,
)

FIXTURES = Path(__file__).parent / "fixtures" / "y4d"


# ── the strict switch ─────────────────────────────────────────────────────────────────


def test_report_only_by_default():
    assert strict_checks(environ={}) == frozenset()


def test_strict_from_environment_and_cli_add_up():
    env = {STRICT_ENV: "chord-error, segments"}
    assert strict_checks(["manifold"], environ=env) == {"manifold", "chord-error", "segments"}
    assert strict_checks(environ={STRICT_ENV: "all"}) == frozenset(CHECKS)


@pytest.mark.parametrize("bad", ["size", "facet-lint", "chord", "sliver"])
def test_unknown_or_warning_only_names_are_refused(bad):
    """`size` and the lint are never strict; sliver share is never judged (M4)."""
    with pytest.raises(MeshGateError):
        strict_checks(environ={STRICT_ENV: bad})
    with pytest.raises(MeshGateError):
        strict_checks([bad], environ={})


# ── resolution findings from measurements ─────────────────────────────────────────────


def test_thresholds_are_the_ruled_ones():
    """M4: chord error at most 0.05mm; 32 segments on full circles of radius >= 1mm."""
    ok = Resolution("m", chord_mm=0.05, circles=[Circle(1.0, 32, 0.0048)])
    assert resolution_findings(ok) == []
    over = Resolution("m", chord_mm=0.0501, circles=[Circle(1.0, 31, 0.005)])
    assert {f.check for f in resolution_findings(over)} == {"chord-error", "segments"}
    tiny = Resolution("m", chord_mm=0.0, circles=[Circle(0.99, 8, 0.07)])
    # under 1mm the segment floor does not apply, but a chord over the limit still counts
    assert [f.check for f in resolution_findings(tiny)] == ["chord-error"]


def test_a_circle_chord_counts_when_no_surface_was_measured():
    res = Resolution("mesh circle fit", circles=[Circle(59.0, 48, 0.126)])
    (finding,) = resolution_findings(res)
    assert finding.check == "chord-error" and "radius 59.000 mm at 48 segments" in finding.detail


# ── the opt-out (M6) ──────────────────────────────────────────────────────────────────


def _doc(base=None, mode=None, part=None):
    verification = {"stages": {"geometry": {"checks": {}}}, "mode_overrides": {}}
    if base is not None:
        verification["stages"]["geometry"]["checks"]["mesh_resolution"] = base
    entry = {}
    if mode is not None:
        entry["overrides"] = {"geometry.mesh_resolution": mode}
    if part is not None:
        entry["part_overrides"] = {"lid": {"geometry.mesh_resolution": part}}
    if entry:
        verification["mode_overrides"]["box"] = entry
    return {"verification": verification}


OFF = {"enabled": False, "reason": "the 16-sided knuckles are the low-poly style"}


def test_policy_precedence_part_over_mode_over_cartridge():
    on = {"enabled": True}
    assert resolve_policy(_doc(base=OFF), "box", "lid").enabled is False
    assert resolve_policy(_doc(base=OFF, mode=on), "box", "lid").enabled is True
    assert resolve_policy(_doc(base=on, mode=on, part=OFF), "box", "lid").enabled is False
    assert resolve_policy(_doc(base=on, mode=on, part=OFF), "box", "base").enabled is True
    assert resolve_policy({}, "box", "lid").enabled is True


def test_an_opt_out_without_a_reason_is_a_failure_and_exempts_nothing():
    bare = {"enabled": False}
    for doc in (_doc(base=bare), _doc(mode=bare), _doc(part=bare)):
        problems = mesh_resolution_policy_rules(doc)
        assert len(problems) == 1 and "without a `reason`" in problems[0]
        assert resolve_policy(doc, "box", "lid").enabled is True
    assert mesh_resolution_policy_rules(_doc(base=OFF, mode=OFF, part=OFF)) == []
    assert mesh_resolution_policy_rules(_doc(base={"enabled": "no"})) == [
        "verification.stages.geometry.checks.mesh_resolution.enabled: must be a boolean"
    ]


def test_the_manifest_rules_carry_the_reason_rule():
    from y4d_spec.rules import all_manifest_rules

    assert any("mesh-resolution" in p for p in all_manifest_rules(_doc(part={"enabled": False})))


class _Render:
    def __init__(self, gate, mode="box", part="lid"):
        self.gate, self.mode, self.part = gate, mode, part
        self.target = f"({mode}, {part}, cadquery)"


def test_opt_out_exempts_only_the_resolution_checks():
    render = _Render([GateFinding("chord-error", "x"), GateFinding("segments", "y"),
                      GateFinding("manifold", "z"), GateFinding("duplicate-faces", "w")])
    apply_policy(render, _doc(part=OFF))
    assert {f.check: f.exempt for f in render.gate} == {
        "chord-error": True, "segments": True, "manifold": False, "duplicate-faces": False,
    }
    gate = cartridge_gate([render], frozenset(), [])
    assert gate.exempt == 2
    assert gate.would_fail["manifold"] and not gate.would_fail["chord-error"]
    assert any("exempt — the 16-sided knuckles" in n for n in gate.notes)


def test_report_only_is_notes_and_strict_is_problems():
    def renders():
        return [_Render([GateFinding("segments", "24 segments"), GateFinding("size", "big")])]

    report = cartridge_gate(renders(), frozenset(), ["mesh-gate facet-lint: x [warning]"])
    assert report.problems == [] and len(report.notes) == 3
    assert report.size_warned and report.linted
    strict = cartridge_gate(renders(), frozenset({"segments"}), [])
    assert len(strict.problems) == 1 and "[FAIL]" in strict.problems[0]
    # size never fails, whatever is strict
    assert not any("size" in p for p in strict.problems)


def test_summary_clause_counts_cartridges_per_check():
    a = cartridge_gate([_Render([GateFinding("segments", "s"), GateFinding("segments", "t")])],
                       frozenset(), [])
    b = cartridge_gate([_Render([GateFinding("chord-error", "c")])], frozenset(), ["lint"])
    clause = summary_clause([a, b], frozenset())
    assert clause == (
        " mesh-gate[report-only]: manifold=0 zero-area=0 duplicate-faces=0 chord-error=1 "
        "segments=1 exempt=0 size=0 facet-lint=1"
    )
    assert "mesh-gate[strict=chord-error,segments]" in summary_clause(
        [a, b], frozenset({"segments", "chord-error"})
    )


# ── the source lint (M5) ──────────────────────────────────────────────────────────────

LINTED = """
import math
def arc_segments():
    if style <= 1:
        return 8
    if style == 2:
        return 16
    return 0
def round_profile(wp, r):
    n = arc_segments()
    return wp.polygon(n, 2 * r)
hexagon = cq.Workplane().polygon(6, 10)
dodecagon = cq.Workplane().polygon(12, 10)
smooth = cq.Workplane().polygon(64, 10)
pts = [(math.cos(t), math.sin(t)) for t in range(16)]
curve = cq.Workplane().polyline(pts).close()
ring = []
for i in range(5):
    ring.append((r * math.cos(i), r * math.sin(i)))
looped = cq.Workplane().polyline(ring).close()
profile = cq.Workplane().polyline([(0, 0), (4, 0), (4, 2)]).close()
centres = []
for i in range(6):
    centres.append((math.cos(i), math.sin(i)))
"""


def test_lint_flags_what_it_is_written_for_and_nothing_else():
    found = _lint_source(LINTED, "main.py")
    lines = [int(f.split(":")[1]) for f in found]
    assert lines == [11, 13, 16, 20]  # polygon(arc_segments()), 12-gon, two trig polylines
    assert "n in {8, 16}" in found[0]
    # a hexagon, a 64-gon, a literal profile and trig used for anything but a polyline
    # are left alone
    assert not any(":12:" in f or ":14:" in f or ":21:" in f for f in found)


def test_lint_is_silent_on_unparseable_source():
    assert _lint_source("def (:", "broken.py") == []


# ── the geom-core side of the oracle seam, without geom-core ──────────────────────────


def test_geom_core_structure_counts_are_read_from_its_integrity_report(monkeypatch):
    """`nonmanifold_edges` and `degenerate_faces` from `assess_integrity()`, the triangle
    count from `get_triangle_count()`; a disagreement with trimesh joins oracle-parity."""
    import sys
    import types

    from y4d_spec import mesh_oracle

    module = types.ModuleType(mesh_oracle.GEOM_CORE_MODULE)

    class Analyzer:
        def load_stl(self, path):
            return True

        def get_triangle_count(self):
            return 14

        def assess_integrity(self, scale_hint=None):
            return types.SimpleNamespace(
                watertight=False, volume=1000.0, body_count=1, boundary_edges=0,
                nonmanifold_edges=3, degenerate_faces=1,
            )

    module.Analyzer = Analyzer
    monkeypatch.setitem(sys.modules, mesh_oracle.GEOM_CORE_MODULE, module)
    measured = mesh_oracle.GeomCoreOracle().measure("part.stl")
    assert (measured.nonmanifold_edges, measured.degenerate_faces, measured.triangles) == (
        3, 1, 14,
    )
    by_trimesh = mesh_oracle.MeshMeasure(
        oracle="trimesh", watertight=False, volume=1000.0, bodies=1,
        nonmanifold_edges=3, degenerate_faces=0, triangles=14,
    )
    note = mesh_oracle.oracle_parity_note("(m, p)", by_trimesh, measured)
    assert note and "degenerate faces trimesh=0 geom-core=1" in note
    assert "nonmanifold" not in note and "triangles" not in note


# ── measured meshes: structure under every oracle, circle fit ─────────────────────────


def _trimesh():
    # Per test, not at module level: the pure tests above must run on a base install.
    return pytest.importorskip("trimesh")


def _write(mesh, tmp_path, name="m.stl"):
    path = tmp_path / name
    mesh.export(path)
    return str(path)


def _box():
    return _trimesh().creation.box((10, 10, 10))


ORACLES = ["trimesh", "geomcore", "both"]


def _select(monkeypatch, oracle):
    from y4d_spec.mesh_oracle import ENV_VAR, geom_core_available

    if oracle != "trimesh" and not geom_core_available():
        pytest.skip("requires geom-core (scripts/qa/install_geom_core.sh)")
    monkeypatch.setenv(ENV_VAR, oracle)


@pytest.mark.geometry
@pytest.mark.parametrize("oracle", ORACLES)
def test_a_closed_box_has_no_structure_findings(tmp_path, monkeypatch, oracle):
    from y4d_spec.geometry import _judge_stl

    _select(monkeypatch, oracle)
    check = _judge_stl(_write(_box(), tmp_path), mode="m", part="p", preset=None,
                       printability=False, engine="cadquery")
    assert check.ok and check.gate == []


@pytest.mark.geometry
@pytest.mark.parametrize("oracle", ORACLES)
def test_a_duplicated_face_is_counted_and_named(tmp_path, monkeypatch, oracle):
    """One triangle listed twice: a duplicate (trimesh, every oracle) and three edges
    now shared by three triangles (the verdict oracle). The watertight failure names
    the non-manifold edges instead of reading "0 boundary edge(s)"."""
    import numpy as np

    from y4d_spec.geometry import _judge_stl

    _select(monkeypatch, oracle)
    trimesh = _trimesh()
    box = _box()
    doubled = trimesh.Trimesh(box.vertices, np.vstack([box.faces, box.faces[:1]]), process=False)
    check = _judge_stl(_write(doubled, tmp_path), mode="m", part="p", preset=None,
                       printability=False, engine="cadquery")
    found = {f.check: f.detail for f in check.gate}
    assert "1 duplicate triangle(s)" in found["duplicate-faces"]
    assert "3 non-manifold edge(s)" in found["manifold"]
    assert not check.ok
    assert any("non-manifold edge(s)" in p for p in check.problems)


@pytest.mark.geometry
@pytest.mark.parametrize("oracle", ORACLES)
def test_a_zero_area_triangle_is_counted(tmp_path, monkeypatch, oracle):
    import numpy as np

    from y4d_spec.geometry import _judge_stl

    _select(monkeypatch, oracle)
    trimesh = _trimesh()
    box = _box()
    # a sliver of three collinear points on one edge of the box, appended to it
    v = np.vstack([box.vertices, [[-5, -5, -5], [0, -5, -5], [5, -5, -5]]])
    n = len(box.vertices)
    faces = np.vstack([box.faces, [[n, n + 1, n + 2]]])
    mesh = trimesh.Trimesh(v, faces, process=False)
    check = _judge_stl(_write(mesh, tmp_path), mode="m", part="p", preset=None,
                       printability=False, engine="cadquery")
    assert "zero-area" in {f.check for f in check.gate}


@pytest.mark.geometry
@pytest.mark.parametrize(
    ("radius", "sections", "expected"),
    [
        (59.0, 48, {"chord-error"}),  # the spiral planter's wall: 0.126mm
        (50.0, 32, {"chord-error"}),  # the Voronoi coaster: 0.241mm
        (2.5, 24, {"segments"}),  # the motor mount's holes
        (0.8, 12, set()),  # under 1mm: not judged on segments, chord tiny
        (10.0, 64, set()),
    ],
)
def test_openscad_circle_fit_at_the_proposals_numbers(tmp_path, radius, sections, expected):
    from y4d_spec.geometry import _judge_stl

    cyl = _trimesh().creation.cylinder(radius=radius, height=10, sections=sections)
    check = _judge_stl(_write(cyl, tmp_path), mode="m", part="p", preset=None,
                       printability=False, engine="openscad")
    assert check.ok
    assert {f.check for f in check.gate} == expected
    for finding in check.gate:
        assert "axis-aligned full circles only" in finding.detail


@pytest.mark.geometry
def test_the_circle_fit_reports_segments_by_the_widest_gap():
    from y4d_spec.mesh_gate import mesh_resolution

    res = mesh_resolution(_trimesh().creation.cylinder(radius=59.0, height=10, sections=48))
    assert {c.segments for c in res.circles} == {48}
    assert all(abs(c.chord_mm - 0.1263) < 1e-3 for c in res.circles)


# ── against the solid (CadQuery) ──────────────────────────────────────────────────────


def _cadquery():
    return pytest.importorskip("cadquery", reason="CadQuery kernel not installed")


def _measure(result, tmp_path):
    from y4d_spec.geometry import _export_stl
    from y4d_spec.mesh_gate import solid_resolution

    _export_stl(result, str(tmp_path / "out.stl"))
    return solid_resolution(result)


@pytest.mark.geometry
def test_cadquery_holes_come_out_at_126_segments_well_inside_the_limit(tmp_path):
    cq = _cadquery()
    plate = cq.Workplane("XY").box(40, 30, 6).faces(">Z").workplane().hole(10)
    res = _measure(plate, tmp_path)
    assert res.circles and {c.segments for c in res.circles} == {126}
    assert res.chord_mm < 0.01
    assert resolution_findings(res) == []


@pytest.mark.geometry
def test_a_200mm_cadquery_circle_is_over_the_chord_limit_at_todays_tolerance(tmp_path):
    """The proposal's warning: 126 segments exceed 0.05mm above r = 161mm."""
    cq = _cadquery()
    res = _measure(cq.Workplane("XY").circle(200).extrude(5), tmp_path)
    found = {f.check for f in resolution_findings(res)}
    assert found == {"chord-error"}
    assert 0.05 < res.chord_mm < 0.07  # 200 * (1 - cos(pi / 126)) = 0.0622


@pytest.mark.geometry
def test_an_assembly_is_measured_in_place(tmp_path):
    cq = _cadquery()
    assy = cq.Assembly().add(cq.Workplane("XY").circle(200).extrude(3), name="disc")
    assy.add(cq.Workplane("XY").box(5, 5, 5), name="block", loc=cq.Location((500, 0, 0)))
    res = _measure(assy, tmp_path)
    assert "chord-error" in {f.check for f in resolution_findings(res)}


@pytest.mark.geometry
def test_closed_forms_agree_with_projection_on_tori_and_cones(tmp_path, monkeypatch):
    """Cylinders, cones, spheres and tori are measured in closed form; every other surface
    by projection. The two must agree where both apply."""
    cq = _cadquery()
    from y4d_spec import mesh_gate

    filleted = cq.Workplane("XY").cylinder(10, 20).edges().fillet(2)  # two tori
    cone = cq.Workplane("XY").add(cq.Solid.makeCone(20, 5, 15))
    monkeypatch.setattr(mesh_gate, "MAX_PROJECTED_SAMPLES", 10**7)  # no striding here
    for shape in (filleted, cone):
        closed = _measure(shape, tmp_path).chord_mm
        with monkeypatch.context() as m:
            m.setattr(mesh_gate, "_analytic_kinds", lambda: frozenset())
            projected = mesh_gate.solid_resolution(shape).chord_mm
        assert closed > 0
        assert closed == pytest.approx(projected, abs=1e-5)


@pytest.mark.geometry
def test_a_polygon_prism_passes_the_solid_measurement(tmp_path):
    """Faceting drawn into the solid matches its own mesh: no finding here, which is why
    the source lint exists (M5) and why no circle fit runs on CadQuery output."""
    cq = _cadquery()
    prism = cq.Workplane("XY").polygon(16, 60).extrude(10)
    res = _measure(prism, tmp_path)
    assert res.circles == [] and res.chord_mm == 0.0
    assert resolution_findings(res) == []


@pytest.mark.geometry
def test_render_part_reports_without_failing(tmp_path):
    _cadquery()
    from y4d_spec.geometry import render_part

    (tmp_path / "disc.py").write_text(
        "import cadquery as cq\nresult = cq.Workplane('XY').circle(200).extrude(5)\n"
    )
    check = render_part(tmp_path, "disc.py", "m", "p")
    assert check.ok  # report-only: the gate never touches the verdict here
    assert [f.check for f in check.gate] == ["chord-error"]


# ── end to end through the CLI ────────────────────────────────────────────────────────


@pytest.fixture
def gate_fixture(tmp_path):
    root = tmp_path / "mesh-gate-disc"
    shutil.copytree(FIXTURES / "mesh-gate-disc", root)
    return root


@pytest.mark.geometry
def test_cli_reports_by_default_and_fails_under_strict(gate_fixture, capsys, monkeypatch):
    _cadquery()
    from y4d_spec.cli import main

    monkeypatch.delenv(STRICT_ENV, raising=False)
    # --no-printability: the 400 mm disc and 360 mm ring would add two build-volume notes.
    args = ["check", "--render", "--no-presets", "--no-printability"]
    assert main([*args, str(gate_fixture)]) == 0
    out = capsys.readouterr().out
    assert "mesh-gate chord-error: (disc, disc, cadquery):" in out
    assert "[report-only]" in out
    assert "mesh-gate chord-error: (disc, ring, cadquery): exempt — TEST FIXTURE" in out
    assert "mesh-gate facet-lint: disc.py:" in out
    summary = out.strip().splitlines()[-1]
    assert (
        " mesh-gate[report-only]: manifold=0 zero-area=0 duplicate-faces=0 chord-error=1 "
        "segments=0 exempt=1 size=0 facet-lint=1"
    ) in summary
    assert " notes=3 " in summary  # the finding, the exemption, the lint

    assert main([*args, "--mesh-strict", "chord-error", str(gate_fixture)]) == 1
    out = capsys.readouterr().out
    assert "FAIL mesh-gate-disc: mesh-gate chord-error:" in out
    assert "mesh-gate[strict=chord-error]" in out.strip().splitlines()[-1]

    monkeypatch.setenv(STRICT_ENV, "segments")
    assert main([*args, str(gate_fixture)]) == 0  # ring exempt; disc and knob have 126 or none


def test_cli_refuses_a_strict_switch_without_render_or_with_a_typo(capsys, monkeypatch):
    from y4d_spec.cli import main

    fixture = str(FIXTURES / "thimble")
    assert main(["check", "--mesh-strict", "segments", fixture]) == 2
    monkeypatch.setenv(STRICT_ENV, "chords")
    if not _geometry():
        pytest.skip("the typo is only read under --render, which needs the geometry extra")
    assert main(["check", "--render", fixture]) == 2
    assert "not one of" in capsys.readouterr().out


def _geometry() -> bool:
    from y4d_spec.geometry import geometry_available

    return geometry_available()


def test_fixture_manifest_declares_a_reasoned_opt_out():
    doc = json.loads((FIXTURES / "mesh-gate-disc" / "project.json").read_text())
    assert mesh_resolution_policy_rules(doc) == []
    assert resolve_policy(doc, "disc", "ring").enabled is False
    assert resolve_policy(doc, "disc", "disc").enabled is True
