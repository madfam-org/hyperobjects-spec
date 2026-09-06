#!/usr/bin/env python3
"""Graph-engine drift guard — the vendored transpiler must match its lock.

The keystone renders `.graph.json` cartridges by transpiling them with the SAME code
the platform runs, so that a verdict here is a verdict about the script users get. The
canonical source is Yantra4D (`apps/api/services/engine/graph_engine.py` plus
`packages/schemas/graph{.schema,-node-catalog}.json`); this repo vendors a copy under
`src/y4d_spec/graph/`. This lane asserts the vendored copy matches the sha256 hashes
pinned in `graph.lock.json`, so an edit here — or a stale copy after the platform moves
— cannot pass unnoticed.

    python scripts/qa/check_graph_sync.py            # verify (CI)
    python scripts/qa/check_graph_sync.py --update   # re-pin after re-vendoring

Modelled on yantra4d's `scripts/qa/check_sandbox_sync.py`, deliberately: the two guards
protect the same kind of thing (one authored source, two copies that must not diverge)
and reading one should teach you the other.

The loop closes on the platform side: yantra4d's `spec-conformance` job installs the
keystone at `SPEC_PIN` and asserts the INSTALLED keystone's hashes equal the platform's
live files, so a platform engine change goes red there until the copy here is refreshed
and re-pinned.

Read-proof and fail-closed: a missing file or lock, or any hash mismatch, fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "src" / "y4d_spec" / "graph"
LOCK = PKG / "graph.lock.json"

# The vendored files whose bytes must not drift from the canonical source. The engine
# is the transpiler itself; the schema and the catalog are the document contract it
# enforces, and a copy of the engine paired with someone else's schema is exactly the
# silent disagreement this guard exists to prevent. `__init__.py` is NOT guarded: it is
# keystone-authored glue (the re-export surface), not vendored platform code.
GUARDED = ["graph_engine.py", "graph.schema.json", "graph-node-catalog.json"]

# Where each guarded file comes from in a yantra4d checkout, printed on a mismatch so
# the repair is the message rather than something to look up.
CANONICAL = {
    "graph_engine.py": "apps/api/services/engine/graph_engine.py",
    "graph.schema.json": "packages/schemas/graph.schema.json",
    "graph-node-catalog.json": "packages/schemas/graph-node-catalog.json",
}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _current() -> dict[str, str]:
    return {name: _hash(PKG / name) for name in GUARDED}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update", action="store_true",
                    help="re-pin graph.lock.json to the vendored files' current hashes")
    args = ap.parse_args()

    missing = [n for n in GUARDED if not (PKG / n).is_file()]
    if missing:
        print(f"check_graph_sync: FAIL — vendored engine missing: {', '.join(missing)}")
        return 1

    current = _current()

    if args.update:
        LOCK.write_text(json.dumps({
            "_comment": "sha256 of the vendored Yantra4D graph engine and its document "
                        "contract. Canonical source: madfam-org/yantra4d "
                        "(apps/api/services/engine/graph_engine.py, "
                        "packages/schemas/graph.schema.json, "
                        "packages/schemas/graph-node-catalog.json). "
                        "Re-pin only after re-vendoring; see VENDORED.md.",
            "canonical_repo": "madfam-org/yantra4d",
            "canonical_paths": CANONICAL,
            "hashes": current,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"check_graph_sync: re-pinned {len(current)} files in {LOCK.name}")
        return 0

    if not LOCK.exists():
        print(f"check_graph_sync: FAIL — {LOCK.name} missing (run with --update to create)")
        return 1

    locked = json.loads(LOCK.read_text(encoding="utf-8")).get("hashes", {})
    problems = []
    for name in GUARDED:
        if locked.get(name) != current[name]:
            problems.append(
                f"{name}: vendored copy does not match the lock — re-vendor from "
                f"madfam-org/yantra4d:{CANONICAL[name]} and re-pin (see VENDORED.md)"
            )

    print(f"check_graph_sync: guarded={len(GUARDED)} mismatches={len(problems)}")
    for p in problems:
        print(f"  FAIL {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
