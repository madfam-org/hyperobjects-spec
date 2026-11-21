# Graph-core fixtures — provenance and licence

`solid-commons/` holds byte-identical copies of five cartridges' `project.json` and
`*.graph.json` from [madfam-org/solid-hyperobjects](https://github.com/madfam-org/solid-hyperobjects)
at main `8317c177` (2026-11-20): `book-fold-phone`, `clamshell-dual-screen-handheld`,
`flange-plate`, `idler-608` and `spacer-block`. The other ten graph cartridges of the solid
commons are already here, byte-identical to the same commit, under
`../assembly-golden/commons/` (verified file by file on 2026-11-20), and the tests read them
there rather than keep a second copy.

They are licensed **CERN-OHL-W-2.0** by their authors (see each `project.json`;
<https://spdx.org/licenses/CERN-OHL-W-2.0.html>), not under this repository's Apache-2.0,
and are copied unmodified as test inputs only: together they are every `.graph.json` in the
solid commons, which is what lets `tests/test_graph_core_solid.py` prove that the graph core
hands every existing graph to the solid engine unchanged. Do not edit them; refresh them from
the commons.

`solid-transpile.sha256.json` pins the sha256 of the script the vendored engine emits for
each of the fifteen graphs, with its manifest's bindings. It moves only when the engine is
re-vendored: run `python scripts/qa/check_graph_core_solid.py --update-golden` then, and
review which graphs' emission changed.
