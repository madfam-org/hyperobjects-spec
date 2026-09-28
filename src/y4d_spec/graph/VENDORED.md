# Vendored: the Yantra4D graph engine

This directory is a **vendored copy** of Yantra4D's node-graph transpiler. The
**canonical source** is the platform, `madfam-org/yantra4d`:

<!-- markdownlint-disable MD013 -->

| Vendored here | Canonical source |
|:--|:--|
| `graph_engine.py` | `apps/api/services/engine/graph_engine.py` |
| `graph.schema.json` | `packages/schemas/graph.schema.json` |
| `graph-node-catalog.json` | `packages/schemas/graph-node-catalog.json` |

<!-- markdownlint-enable MD013 -->

Do **not** hand-edit any of those three files here — change the canonical
source on the platform and re-vendor. `__init__.py` and `VENDORED.md` are
keystone-authored and are not vendored.

## Why a copy

A `.graph.json` cartridge has no geometry of its own: it is a document that the
transpiler compiles into a CadQuery script, and that script is what renders. If
the keystone transpiled a graph with its own re-implementation, its verdict
would be about a different script than the one the platform serves — the exact
class of silent disagreement the keystone exists to prevent. So the emission is
imported, byte for byte, never re-written.

An import across repos was not available: the keystone installs with
`pip install hyperobjects-spec` onto a machine that has no platform checkout,
and "validate a cartridge with zero platform code" is the package's whole
promise. What makes vendoring possible is that the engine is **stdlib-only**
(`hashlib`, `json`, `keyword`, `logging`, `math`, `os`, `re`, `tempfile`,
`pathlib`) and the platform's engine package `__init__.py` is empty, so the
module imports standalone.

The precedent is `packages/commons-sandbox/VENDORED.md` in yantra4d, which
vendors Fashion Cabinet's sandbox security core with the same lock +
drift-guard + doc shape.

## Drift guard (both directions)

- **Here:** `scripts/qa/check_graph_sync.py` (a blocking CI lane) asserts these
  three files match the sha256 hashes in `graph.lock.json`. An edit here, or a
  stale copy, turns this repo red.
- **On the platform:** yantra4d's `spec-conformance` (and `spec-nightly`) job
  installs the keystone at `SPEC_PIN` and asserts the **installed** keystone's
  hashes equal the platform's live files. So a change to the engine on the
  platform turns *that* repo red until the copy here is refreshed, re-pinned,
  released, and the pin moved.

The two halves are what make the loop closed rather than a copy someone
remembers to update. Neither repo can drift alone.

## Lint

`graph_engine.py` is excluded from ruff (`pyproject.toml`, `extend-exclude`).
Two of its lines are 102 characters, which is yantra4d's limit and not this
repo's, and reformatting them would break the hash. The byte-identity is the
mechanism — do not "fix" the lint by editing the copy.

## Re-vendoring

```sh
# from a checkout with both repos side by side:
cp ../yantra4d/apps/api/services/engine/graph_engine.py   src/y4d_spec/graph/
cp ../yantra4d/packages/schemas/graph.schema.json         src/y4d_spec/graph/
cp ../yantra4d/packages/schemas/graph-node-catalog.json   src/y4d_spec/graph/
python scripts/qa/check_graph_sync.py --update  # re-pin graph.lock.json
python -m pytest tests/test_graph_render.py     # the emission still transpiles
```

Then the coordinator moves `SPEC_PIN` on the platform and on the commons.
Bumping the pin is **not** part of a re-vendoring PR.

Once a shared MADFAM Python registry exists, replace this vendored copy with a
plain `pip` dependency on the engine package and delete the guard — exactly as
`packages/commons-sandbox/VENDORED.md` already says for the sandbox core.
