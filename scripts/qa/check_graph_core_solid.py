#!/usr/bin/env python3
"""The solid pack moved behind the core without changing its output — proved per graph.

RFC 0067 put the kernel-neutral half of the graph in `hyperobject_graph` and the solid
vocabulary behind its node-pack interface (`y4d_spec.solid_pack`). The promise of that move
is that no existing graph renders differently. This checks it, for every graph given:

  1. the core accepts the document with ZERO problems under the solid pack;
  2. the program the core produces (`hyperobject_graph.transpile`) is byte-identical to
     the program the vendored engine produces when called directly, with the same
     manifest bindings;
  3. (fixtures only) that program's sha256 equals the one pinned in
     `tests/fixtures/graph-core/solid-transpile.sha256.json`, so a re-vendored engine
     that changes any graph's emission says which.

    python scripts/qa/check_graph_core_solid.py                     # the 15 fixtures (CI)
    python scripts/qa/check_graph_core_solid.py --commons ../solid-hyperobjects
    python scripts/qa/check_graph_core_solid.py --update-golden     # after a re-vendor

Fail-closed: an unreadable graph, a problem, a byte difference or a missing golden fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import hyperobject_graph as core  # noqa: E402
from y4d_spec.graph import graph_engine  # noqa: E402
from y4d_spec.solid_pack import SOLID_PACK  # noqa: E402

FIXTURE_ROOTS = (
    ROOT / "tests" / "fixtures" / "graph-core" / "solid-commons",
    ROOT / "tests" / "fixtures" / "assembly-golden" / "commons",
)
GOLDEN = ROOT / "tests" / "fixtures" / "graph-core" / "solid-transpile.sha256.json"


def graphs_under(roots) -> list[Path]:
    return sorted(g for root in roots for g in Path(root).glob("*/*.graph.json"))


def judge(graph: Path) -> tuple[str, str | None, list[str]]:
    """(key, sha256 of the program or None, problems) for one graph file."""
    key = f"{graph.parent.name}/{graph.name}"
    doc = json.loads(graph.read_text(encoding="utf-8"))
    manifest = json.loads((graph.parent / "project.json").read_text(encoding="utf-8"))
    params = manifest.get("parameters") or []
    problems = [str(p) for p in core.validate(doc, SOLID_PACK, parameters=params)]
    try:
        through_core = core.transpile(doc, SOLID_PACK, parameters=params, source_name=graph.name)
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return key, None, problems + [f"core transpile failed: {exc}"]
    direct = graph_engine.transpile(
        doc, graph_engine.extract_bindings(params), source_name=graph.name
    )
    if through_core != direct:
        problems.append("the core's program differs from the engine's (not byte-identical)")
    if core.pack_document(doc) != doc:
        problems.append("the core changed the document it handed the engine")
    return key, hashlib.sha256(through_core.encode()).hexdigest(), problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--commons", type=Path,
                    help="a solid-hyperobjects checkout: check every graph in it")
    ap.add_argument("--update-golden", action="store_true",
                    help="re-pin the fixtures' program digests (after re-vendoring)")
    args = ap.parse_args()

    graphs = graphs_under([args.commons] if args.commons else FIXTURE_ROOTS)
    if not graphs:
        print("check_graph_core_solid: FAIL — no graphs found")
        return 1
    golden = {}
    if not args.update_golden and GOLDEN.exists():
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["programs"]
    digests: dict[str, str] = {}
    failures = 0
    for graph in graphs:
        key, digest, problems = judge(graph)
        if digest is not None:
            digests[key] = digest
        if not args.commons and not args.update_golden:
            if key not in golden:
                problems.append("no pinned digest (run --update-golden after review)")
            elif digest is not None and golden[key] != digest:
                problems.append(f"program digest {digest[:12]}… ≠ pinned {golden[key][:12]}…")
        if problems:
            failures += 1
            print(f"  FAIL {key}")
            for p in problems:
                print(f"       {p}")
        else:
            print(f"  ok   {key}  {digest[:16]}…")

    if args.update_golden and not args.commons:
        GOLDEN.write_text(json.dumps({
            "_comment": "sha256 of the CadQuery script the vendored solid engine emits for "
                        "each solid-commons graph with its manifest's bindings. Moves only "
                        "on a re-vendor; see tests/fixtures/graph-core/NOTICE.md.",
            "engine_sha256": json.loads(
                (ROOT / "src/y4d_spec/graph/graph.lock.json").read_text()
            )["hashes"]["graph_engine.py"],
            "programs": dict(sorted(digests.items())),
        }, indent=2) + "\n", encoding="utf-8")
        print(f"check_graph_core_solid: pinned {len(digests)} program digests")
    print(f"check_graph_core_solid: graphs={len(graphs)} identical="
          f"{len(graphs) - failures} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
