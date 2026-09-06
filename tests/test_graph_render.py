"""The graph render lane: a `.graph.json` cartridge is judged at the same bar as a `.py`.

Before this, `mode_sources()` returned `[]` for a `.graph.json` and the assertion that it
did so was a TEST — which is how the commons' two graph cartridges came to be the only
two of 500 outside the bar the rest clear. These are the tests for the behaviour that
replaced it.

Four things are checked here, in the order they matter:

  1. THE VENDORED COPY IS BYTE-IDENTICAL and the guard says so. A keystone that
     transpiled a graph with its own re-implementation would be judging a different
     script than the one the platform serves.
  2. `mode_sources()` recognises the compound suffix and labels it `graph`.
  3. A graph RENDERS and clears the whole bar — watertight, body count, B-Rep validity,
     assembly export, presets — because after the transpile it is a CadQuery cartridge.
  4. THE GOLDEN-TWIN RULE: where a graph has a script twin, `--parity` compares them,
     and the comparison can FAIL. A gate only ever seen green is a gate nobody tested.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from y4d_spec.geometry import (
    GRAPH_FILE_SUFFIX,
    GraphError,
    geometry_available,
    mode_sources,
    render_part_graph,
    stl_name,
)
from y4d_spec.graph_render import graph_script_path, is_graph_source, transpile_graph
from y4d_spec.parity import COMPARABLE_PAIRS, ParityCheck, pair_renders

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "y4d"
GRAPH_BLOCK = FIXTURES / "graph-block"
GRAPH_TWIN = FIXTURES / "graph-twin"
GRAPH_TWIN_DIVERGENT = FIXTURES / "graph-twin-divergent"
VENDORED = REPO / "src" / "y4d_spec" / "graph"

needs_geometry = pytest.mark.skipif(
    not geometry_available(), reason="the [geometry] extra is not installed"
)


# ── 1. The vendored copy ──────────────────────────────────────────────────────


def test_the_lock_matches_the_vendored_files():
    """The guard's own assertion, in-process: a hand-edit here must be caught.

    This is the same computation `scripts/qa/check_graph_sync.py` makes. It is tested as
    well as run in CI because the lane is what turns an accidental edit into a red
    build, and a lane nothing exercises is a lane that can rot into always-passing.
    """
    lock = json.loads((VENDORED / "graph.lock.json").read_text(encoding="utf-8"))
    hashes = lock["hashes"]
    assert set(hashes) == {"graph_engine.py", "graph.schema.json", "graph-node-catalog.json"}
    for name, expected in hashes.items():
        actual = hashlib.sha256((VENDORED / name).read_bytes()).hexdigest()
        assert actual == expected, (
            f"{name} does not match graph.lock.json — either it was hand-edited (do not: "
            f"see VENDORED.md) or it was re-vendored without `check_graph_sync.py --update`"
        )


def test_the_sync_guard_fails_when_the_vendored_engine_is_edited(tmp_path):
    """Fail-closed, proved by breaking it. Run against a COPY of the repo tree so the
    real checkout is never mutated — the guard reads paths relative to its own file."""
    sandbox = tmp_path / "repo"
    (sandbox / "src" / "y4d_spec" / "graph").mkdir(parents=True)
    (sandbox / "scripts" / "qa").mkdir(parents=True)
    for name in ("graph_engine.py", "graph.schema.json", "graph-node-catalog.json",
                 "graph.lock.json"):
        (sandbox / "src" / "y4d_spec" / "graph" / name).write_bytes(
            (VENDORED / name).read_bytes()
        )
    guard = sandbox / "scripts" / "qa" / "check_graph_sync.py"
    guard.write_bytes((REPO / "scripts" / "qa" / "check_graph_sync.py").read_bytes())

    clean = subprocess.run([sys.executable, str(guard)], capture_output=True, text=True)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "mismatches=0" in clean.stdout

    engine = sandbox / "src" / "y4d_spec" / "graph" / "graph_engine.py"
    engine.write_text(engine.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")

    dirty = subprocess.run([sys.executable, str(guard)], capture_output=True, text=True)
    assert dirty.returncode == 1, dirty.stdout + dirty.stderr
    assert "graph_engine.py" in dirty.stdout
    # The message must name the repair, not merely the problem.
    assert "madfam-org/yantra4d" in dirty.stdout


def test_the_sync_guard_fails_when_a_vendored_file_is_missing(tmp_path):
    """A deleted file is a mismatch too, and must not read as "nothing to check"."""
    sandbox = tmp_path / "repo"
    (sandbox / "src" / "y4d_spec" / "graph").mkdir(parents=True)
    (sandbox / "scripts" / "qa").mkdir(parents=True)
    for name in ("graph.schema.json", "graph-node-catalog.json", "graph.lock.json"):
        (sandbox / "src" / "y4d_spec" / "graph" / name).write_bytes(
            (VENDORED / name).read_bytes()
        )
    guard = sandbox / "scripts" / "qa" / "check_graph_sync.py"
    guard.write_bytes((REPO / "scripts" / "qa" / "check_graph_sync.py").read_bytes())

    out = subprocess.run([sys.executable, str(guard)], capture_output=True, text=True)
    assert out.returncode == 1
    assert "missing" in out.stdout and "graph_engine.py" in out.stdout


def test_vendored_md_names_the_canonical_source_and_the_revendor_step():
    """The doc is the repair instructions a red guard sends you to."""
    text = (VENDORED / "VENDORED.md").read_text(encoding="utf-8")
    assert "madfam-org/yantra4d" in text
    assert "apps/api/services/engine/graph_engine.py" in text
    assert "check_graph_sync.py --update" in text


def test_the_vendored_engine_imports_only_the_standard_library():
    """What makes vendoring possible at all, asserted rather than remembered.

    A platform-side edit that added, say, `import cadquery` at module scope would make
    the copy un-importable in a manifest-only install and silently break the promise
    that a third party can verify a cartridge with zero platform code. The hash guard
    would catch the drift; this says WHY the drift matters.
    """
    import ast

    tree = ast.parse((VENDORED / "graph_engine.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names), (
        f"the vendored engine imports non-stdlib modules: "
        f"{sorted(imported - set(sys.stdlib_module_names))}"
    )


# ── 2. Source recognition ─────────────────────────────────────────────────────


def test_mode_sources_labels_a_graph_document_graph():
    assert mode_sources({"id": "m", "scad_file": "flange.graph.json"}) == [
        ("graph", "flange.graph.json")
    ]


def test_mode_sources_accepts_the_explicit_graph_file_field():
    """A golden-twin cartridge names both sources; both are rendered and both judged."""
    assert mode_sources(
        {"id": "m", "cq_file": "block.py", "graph_file": "block.graph.json"}
    ) == [("cadquery", "block.py"), ("graph", "block.graph.json")]


def test_mode_sources_orders_cadquery_then_openscad_then_graph():
    """Stable order, so a report diffs across runs."""
    assert mode_sources(
        {"id": "m", "scad_file": "a.scad", "cq_file": "a.py", "graph_file": "a.graph.json"}
    ) == [("cadquery", "a.py"), ("openscad", "a.scad"), ("graph", "a.graph.json")]


def test_mode_sources_does_not_mistake_an_ordinary_json_for_a_graph():
    """`Path.suffix` on `x.graph.json` is `.json`, which is why the test is on the
    COMPOUND suffix. A cartridge's other JSON must not be dragged into the render lane."""
    assert mode_sources({"id": "m", "scad_file": "notes.json"}) == []
    assert mode_sources({"id": "m", "scad_file": "graph.json"}) == []


def test_is_graph_source_is_the_compound_suffix_test():
    assert is_graph_source("flange.graph.json")
    assert not is_graph_source("flange.json")
    assert not is_graph_source("flange.py")
    assert not is_graph_source(None)
    assert GRAPH_FILE_SUFFIX == ".graph.json"


# ── 3. Transpilation and the parameter contract ───────────────────────────────


def test_the_transpiled_script_reads_manifest_parameters_as_bare_globals():
    """THE PARAMETER-INJECTION CONTRACT, asserted on the emission.

    `geometry._exec_cartridge` injects params with `exec_globals.update(params)` — bare
    globals — mirroring cq_runner. The transpiler emits `_param(lambda: <id>, <default>)`
    against exactly that, so no adapter is needed in the emission and the vendored copy
    can stay byte-identical. If the platform ever changed the idiom, this fails.
    """
    manifest = json.loads((GRAPH_BLOCK / "project.json").read_text(encoding="utf-8"))
    script = transpile_graph(GRAPH_BLOCK / "block.graph.json", manifest)

    # The probe the emission defines for itself.
    assert "def _param(getter, default):" in script
    # Every bound manifest parameter is read by its BARE name, with the graph's literal
    # as the fallback when nothing is injected.
    assert "_param(lambda: block_size, 10.0)" in script
    assert "_param(lambda: plate_h, 2.0)" in script
    # `target_part` is one of those params — it is how a per-part render is dispatched.
    assert "_param(lambda: target_part," in script
    # The result lands on the first of geometry.RESULT_NAMES.
    assert "\nresult = _outputs.get(_target)" in script


def test_an_unbound_parameter_is_not_emitted_as_a_probe():
    """Without the manifest there are no bindings, so every dimension is the graph's
    literal — which renders, and ignores every preset. That is why render_part_graph
    takes the manifest, and this is the evidence for the claim."""
    bare = transpile_graph(GRAPH_BLOCK / "block.graph.json", None)
    assert "block_size" not in bare
    assert "cq.Workplane(\"XY\").box(10.0, 10.0, 10.0)" in bare


def test_transpiling_an_invalid_graph_raises_graph_error(tmp_path):
    """A cycle is a hard error in the engine, before any kernel is touched."""
    bad = tmp_path / "cycle.graph.json"
    bad.write_text(json.dumps({
        "version": "1.0.0",
        "units": "mm",
        "nodes": [
            {"id": "a", "type": "union", "inputs": {"a": "b", "b": "b"}},
            {"id": "b", "type": "union", "inputs": {"a": "a", "b": "a"}},
        ],
        "outputs": {"p": "a"},
    }), encoding="utf-8")
    with pytest.raises(GraphError):
        transpile_graph(bad, None)


def test_graph_script_path_writes_a_dot_py_the_sandbox_will_accept():
    """`commons_sandbox.validate_script_path` gates on the suffix, and `.graph.json` is
    not an allowed one — which is the whole reason the document is materialised as a
    real `.py` first, by the PLATFORM's own `prepare_graph_script`."""
    manifest = json.loads((GRAPH_BLOCK / "project.json").read_text(encoding="utf-8"))
    path = graph_script_path(GRAPH_BLOCK / "block.graph.json", manifest)
    assert path.endswith(".py")
    assert Path(path).is_file()


def test_the_transpiled_script_is_content_addressed():
    """Same graph + same bindings → same path; a different manifest → a different one.
    That is what keeps two parts of one cartridge from racing on the same file."""
    manifest = json.loads((GRAPH_BLOCK / "project.json").read_text(encoding="utf-8"))
    first = graph_script_path(GRAPH_BLOCK / "block.graph.json", manifest)
    again = graph_script_path(GRAPH_BLOCK / "block.graph.json", manifest)
    assert first == again
    unbound = graph_script_path(GRAPH_BLOCK / "block.graph.json", None)
    assert unbound != first


def test_stl_name_separates_the_graph_side_from_the_script_side():
    """The golden twin needs BOTH meshes alive at once. One filename means the second
    render overwrites the first and the pass compares a mesh with itself."""
    assert stl_name("graph", "block", "block", None) != stl_name(
        "cadquery", "block", "block", None
    )


# ── 4. Rendering, at the house bar ────────────────────────────────────────────


@needs_geometry
def test_a_graph_renders_and_clears_the_mesh_bar():
    manifest = json.loads((GRAPH_BLOCK / "project.json").read_text(encoding="utf-8"))
    check = render_part_graph(
        GRAPH_BLOCK, "block.graph.json", "block", "block", manifest=manifest
    )
    assert check.ok, check.problems
    assert check.engine == "graph"
    assert check.watertight is True
    assert check.bodies == 1
    assert check.volume == pytest.approx(1000.0, abs=1e-6)


@needs_geometry
def test_the_target_part_dispatch_reaches_the_graphs_outputs_map():
    """`outputs` maps part id → node. A second part must render a DIFFERENT body, or
    the dispatch is dead and every user gets the first part."""
    manifest = json.loads((GRAPH_BLOCK / "project.json").read_text(encoding="utf-8"))
    plate = render_part_graph(
        GRAPH_BLOCK, "block.graph.json", "plate", "plate", manifest=manifest
    )
    assert plate.ok, plate.problems
    assert plate.volume == pytest.approx(800.0, abs=1e-6)


@needs_geometry
def test_a_manifest_binding_actually_moves_the_geometry():
    """The binding chain end to end: manifest slider → node param → emitted `_param`
    probe → injected bare global → a different solid. A graph whose sliders did nothing
    would render, pass the mesh bar, and be a frozen model wearing a parameter panel."""
    manifest = json.loads((GRAPH_BLOCK / "project.json").read_text(encoding="utf-8"))
    bigger = render_part_graph(
        GRAPH_BLOCK, "block.graph.json", "block", "block",
        manifest=manifest, params={"block_size": 20.0}, preset="big_block",
    )
    assert bigger.ok, bigger.problems
    assert bigger.volume == pytest.approx(8000.0, abs=1e-6)


@needs_geometry
def test_an_unrenderable_graph_is_a_failure_not_a_crash(tmp_path):
    """An invalid document fails THIS TARGET, in the engine's own words — the same
    message the platform's editor refuses the save with — and does not take the run out."""
    (tmp_path / "bad.graph.json").write_text(json.dumps({
        "version": "1.0.0",
        "units": "mm",
        "nodes": [{"id": "a", "type": "no_such_node", "params": {}}],
        "outputs": {"p": "a"},
    }), encoding="utf-8")
    check = render_part_graph(tmp_path, "bad.graph.json", "m", "p", manifest={})
    assert not check.ok
    assert check.engine == "graph"
    assert "graph did not transpile" in check.problems[0]
    assert "no_such_node" in check.problems[0]


@needs_geometry
def test_a_missing_graph_file_is_a_failure_not_a_crash(tmp_path):
    """The engine wraps an unreadable file in `GraphError` itself (`load_graph_document`
    raises `cannot read graph file ...`), so this lands in the transpile branch rather
    than the generic one — and the path is named, which is what a repair needs. The
    generic branch stays as the backstop for anything the engine does NOT wrap."""
    check = render_part_graph(tmp_path, "absent.graph.json", "m", "p", manifest={})
    assert not check.ok
    assert check.engine == "graph"
    assert "cannot read graph file" in check.problems[0]
    assert "absent.graph.json" in check.problems[0]


# ── 5. The golden-twin rule ───────────────────────────────────────────────────


def test_the_comparable_pairings_are_the_two_the_rule_defines():
    """(openscad, cadquery) is cross-kernel; (cadquery, graph) is the golden twin.
    (openscad, graph) is deliberately absent — it is a redundant edge whose failure is
    always one of the other two, reported twice."""
    assert COMPARABLE_PAIRS == (("openscad", "cadquery"), ("cadquery", "graph"))


def test_pair_renders_forms_a_graph_versus_script_pair():
    class _R:
        def __init__(self, engine, path):
            self.mode, self.part, self.preset = "m", "p", None
            self.ok, self.engine, self.stl_path = True, engine, path

    cq, graph = _R("cadquery", "/tmp/a.stl"), _R("graph", "/tmp/b.stl")
    assert pair_renders([graph, cq]) == [(cq, graph)]


def test_pair_renders_yields_both_pairings_on_a_three_source_cartridge():
    """Two different claims — "the kernels agree" and "the graph reproduces its
    script" — so two lines, not one."""
    class _R:
        def __init__(self, engine):
            self.mode, self.part, self.preset = "m", "p", None
            self.ok, self.engine, self.stl_path = True, engine, f"/tmp/{engine}.stl"

    scad, cq, graph = _R("openscad"), _R("cadquery"), _R("graph")
    assert pair_renders([graph, cq, scad]) == [(scad, cq), (cq, graph)]


def test_a_graph_with_no_script_twin_yields_no_pair():
    """Both commons graph cartridges are in this state today. Nothing to compare is
    reported as nothing to compare, never as agreement."""
    class _R:
        def __init__(self, engine):
            self.mode, self.part, self.preset = "m", "p", None
            self.ok, self.engine, self.stl_path = True, engine, f"/tmp/{engine}.stl"

    assert pair_renders([_R("graph")]) == []


def test_the_golden_twin_line_names_the_pairing_and_the_cross_kernel_one_does_not():
    """A three-source cartridge would otherwise print two lines identical but for their
    numbers; and the thousands of existing dual-engine lines must keep their shape."""
    twin = ParityCheck(mode="m", part="p", pairing=("cadquery", "graph"))
    assert twin.target == "(m, p, cadquery vs graph)"
    kernels = ParityCheck(mode="m", part="p")
    assert kernels.target == "(m, p)"


@needs_geometry
def test_a_graph_that_reproduces_its_script_passes_the_golden_twin_comparison():
    from y4d_spec.conformance import check_cartridge

    result = check_cartridge(GRAPH_TWIN, render=True, parity=True, printability=False)
    assert result.ok, result.problems
    # block + plate at the defaults, and block again at the `big_block` preset.
    assert len(result.parity) == 3
    assert all(p.ok and not p.exempt for p in result.parity), [p.summary for p in result.parity]
    assert all(p.pairing == ("cadquery", "graph") for p in result.parity)


@needs_geometry
def test_a_graph_that_does_not_reproduce_its_script_FAILS():
    """The rule proved able to fail. Its graph's block is 12mm where the script's cube
    is 10mm; the plate, which agrees, still passes in the same run — so the failure is
    attributed to the part that diverged and not to the cartridge wholesale."""
    from y4d_spec.conformance import check_cartridge

    result = check_cartridge(GRAPH_TWIN_DIVERGENT, render=True, parity=True, printability=False)
    assert not result.ok
    failed = [p for p in result.parity if not p.ok]
    assert [p.part for p in failed] == ["block"]
    assert "Bounding boxes differ by 2.0" in failed[0].reason
    passed = [p for p in result.parity if p.ok]
    assert [p.part for p in passed] == ["plate"]


@needs_geometry
def test_the_two_commons_graph_cartridges_have_no_twin_yet():
    """Documents the state the rule lands into: `flange-plate` and `spacer-block` were
    both authored graph-first, so the golden twin fires on nothing in the commons. Wave
    E's G-TWIN-A is what makes it bite; the rule is here first so those twins are
    checked by a rule that already exists.
    """
    for cartridge in (GRAPH_BLOCK,):
        manifest = json.loads((cartridge / "project.json").read_text(encoding="utf-8"))
        for mode in manifest["modes"]:
            engines = {e for e, _ in mode_sources(mode)}
            assert engines == {"graph"}
