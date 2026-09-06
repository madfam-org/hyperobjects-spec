"""Rendering a `.graph.json` cartridge — the graph engine's half of the render lane.

A graph cartridge has no geometry of its own. `flange-plate/flange.graph.json` is a node
document: 10 typed nodes, two outputs, and a manifest whose 8 sliders `binding` into
node params. The geometry appears only when the document is **transpiled** into a
CadQuery script, and it is that script — not the JSON — that this package must judge.

So the graph path is not a third renderer. It is one step in front of the existing
CadQuery renderer:

    .graph.json ──transpile (vendored platform engine)──▶ .py ──▶ render_part() ──▶ the house bar

and everything downstream is untouched: the shared sandbox, bare-global parameter
injection, `target_part` dispatch, the B-Rep gate, `toCompound()` assembly export, the
watertight/volume/body-count mesh bar, presets, and `--parity`. A graph cartridge is
held to exactly the bar a `.py` cartridge is held to, because after the transpile it IS
a `.py` cartridge.

THE PARAMETER-INJECTION CONTRACT (why no adapter was needed)
------------------------------------------------------------
`geometry._exec_cartridge` replicates `cq_runner.run_cadquery_script`: parameters are
injected as BARE GLOBALS (`exec_globals.update(params)`), which is why hand-written
cartridges use the `PARAM(lambda: name, default)` idiom, and `target_part` is one of
those params. The transpiler emits against the identical contract — it defines its own
`_param(getter, default)` probe and reads every bound value as a bare name:

    _n_outline = cq.Workplane("XY").center(0.0, 0.0).circle(
        float(_param(lambda: plate_radius, 45.0)))
    ...
    _target = str(_param(lambda: target_part, "flange"))
    result = _outputs.get(_target)

`plate_radius` is the manifest parameter id, reached through the binding
`"binding": "outline.r"`; the literal is the graph node's own value, used when nothing
is injected. `result` is the first of `geometry.RESULT_NAMES`. So the emitted script
satisfies the keystone's execution contract with **no adapter and no shim in the
emission** — which is what makes a byte-identical vendored engine possible at all. The
only keystone-side work is the two things the platform does around the engine and the
keystone must do too, and both are done by calling the platform's own code:

  * finding the bindings — `extract_bindings(manifest["parameters"])`, and
  * materialising the transpiled script as a real `.py` on disk, because
    `commons_sandbox.validate_script_path` gates on the suffix and a `.graph.json` is
    not an allowed one. `prepare_graph_script()` in the vendored engine already does
    this (content-addressed filename, atomic replace); it reads its manifest through
    `getattr(manifest, "parameters", ...)`, so the ONE genuinely keystone-side line in
    this module is a `SimpleNamespace` around the manifest dict the keystone carries.

That is the whole adapter. It is here, in the keystone, and not in the engine — forking
the emission would defeat the point of vendoring.

WHAT A GRAPH CARTRIDGE CANNOT HIDE
----------------------------------
An invalid graph is a RENDER FAILURE, not a crash and not a skip. `transpile()` is the
enforcing validator (cycles, unknown node types, socket-type mismatches, dangling refs,
duplicate ids, bindings onto params a node does not have), and every one of those raises
`GraphError` before a kernel is touched. A cartridge whose graph does not compile fails
here with the engine's own message, which is the same message the platform's editor
refuses the save with.

THE GOLDEN-TWIN RULE (write-up §3.7)
------------------------------------
The write-up's ruling is that a graph is an *authoring format verified through its
transpiled output* — not a peer engine — **with a golden-twin rule**: where a graph is
authored for a cartridge that already has a script, the graph's output must agree with
the script's, at the parity bar, for every preset, before the script is retired. That
turns the 494 verified scripts into the oracle for the graphs.

Mechanically that is the parity pass, run on a pair it did not previously have. The
existing pass compares (openscad, cadquery); this adds (cadquery, graph) for a mode that
declares BOTH a graph source and a script source. `parity.pair_renders` grew a
`graph` arm rather than a second comparator, because the comparison itself — AABB,
volume, placement, shape-after-alignment, the warn tier, the per-part exemptions — must
be the same comparison or "agrees with its script" means something different from
"agrees with the other kernel".

Today NEITHER graph cartridge has a script twin (both `flange-plate` and `spacer-block`
were authored graph-first as reference cartridges), so the rule fires on nothing in the
commons yet. It is landed now because Wave E's `G-TWIN-A` authors 134 twins against it,
and a rule written after the twins exist is a rule the twins were not checked by.
"""

from __future__ import annotations

import types
from pathlib import Path

from .graph.graph_engine import (
    GRAPH_FILE_SUFFIX,
    GraphError,
    load_graph_document,
    prepare_graph_script,
)

__all__ = [
    "GRAPH_FILE_SUFFIX",
    "GraphError",
    "graph_script_path",
    "is_graph_source",
    "transpile_graph",
]


def is_graph_source(candidate: object) -> bool:
    """Is this mode source a node-graph document?

    The suffix is compound (`.graph.json`), so `Path.suffix` — which returns `.json` —
    is the wrong test and would also match every other JSON a cartridge ships. The
    engine's own constant is the authority.
    """
    return isinstance(candidate, str) and candidate.endswith(GRAPH_FILE_SUFFIX)


def transpile_graph(graph_path: Path | str, manifest: dict | None = None) -> str:
    """The CadQuery script text a graph document compiles to.

    Exposed for tests and for anyone who wants to read what a graph actually renders;
    the render path uses `graph_script_path` instead, because the sandbox needs a file.
    Raises `GraphError` on any invalid document — that is a cartridge failure, and the
    caller reports it as one.
    """
    from .graph.graph_engine import extract_bindings, transpile

    doc, _raw = load_graph_document(str(graph_path))
    bindings = extract_bindings((manifest or {}).get("parameters") or [])
    return transpile(doc, bindings, source_name=Path(graph_path).name)


def graph_script_path(graph_path: Path | str, manifest: dict | None = None) -> str:
    """Transpile a graph to a real `.py` on disk and return its path.

    Delegates to the vendored engine's `prepare_graph_script`, which is what the
    platform's render orchestrator calls — same content-addressed filename (graph bytes
    + binding map), same atomic replace, so the keystone and the platform materialise
    byte-identical scripts at identical paths and neither can be verifying something the
    other does not run.

    The one keystone-side line: `prepare_graph_script` reads `manifest.parameters` off
    an OBJECT (the platform's parsed manifest model), and the keystone carries manifests
    as plain dicts. A `SimpleNamespace` bridges the two without touching the engine.
    """
    shim = types.SimpleNamespace(parameters=(manifest or {}).get("parameters") or [])
    return prepare_graph_script(str(graph_path), shim)
