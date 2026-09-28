"""The vendored Yantra4D graph engine — a `.graph.json` node document → CadQuery.

`graph_engine.py` in this package is a BYTE-IDENTICAL copy of the platform's
`apps/api/services/engine/graph_engine.py`. It is not authored here; see VENDORED.md
for the canonical source and the re-vendoring steps, and `scripts/qa/check_graph_sync.py`
for the blocking guard that keeps the copy honest.

Why a copy and not an import: the keystone installs with `pip install hyperobjects-spec`
on a machine that has no platform checkout, and the whole point of a keystone is that a
third party can verify a cartridge with zero platform code. The engine is stdlib-only
(hashlib, json, keyword, logging, math, os, re, tempfile, pathlib) and its package
`__init__.py` on the platform is empty, so the module is importable standalone — which
is what makes vendoring possible at all. The precedent is
`packages/commons-sandbox` in yantra4d, which vendors Fashion Cabinet's sandbox core the
same way, with the same lock + drift-guard + VENDORED.md shape.

Nothing in this package may be hand-edited. A graph rendered here and a graph rendered
on the platform must be the SAME transpilation, or the keystone's verdict is about a
different script than the one users get — so the emission is imported, never re-implemented.
Everything the keystone needs on top of the emission (finding the manifest's bindings,
handing the transpiled script to the same `.py` render path) lives in
`y4d_spec.graph_render`, outside this directory.
"""

from .graph_engine import (
    GRAPH_FILE_SUFFIX,
    NODE_TYPES,
    GraphError,
    extract_bindings,
    load_graph_document,
    transpile,
)

__all__ = [
    "GRAPH_FILE_SUFFIX",
    "NODE_TYPES",
    "GraphError",
    "extract_bindings",
    "load_graph_document",
    "transpile",
]
