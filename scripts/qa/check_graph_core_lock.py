#!/usr/bin/env python3
"""Graph-core lock guard — `core.lock.json` must describe the core exactly.

`src/hyperobject_graph/` is the shared graph core of RFC 0067, and it is CANONICAL here:
each kernel (Yantra4D for solid, Fashion Cabinet for soft, Pliego for sheet) vendors a
copy of the directory and pins it by the hashes in `core.lock.json` (docs/GRAPH_CORE.md,
"Vendoring the core"). That only works if the lock published here is the truth about the
files published next to it, so this lane asserts:

  * every file of the package (the `.py` modules and the schema) is in the lock, and the
    lock names no file that is not there;
  * every hash matches;
  * the lock's `core_version` and `format_version` equal the package's constants.

    python scripts/qa/check_graph_core_lock.py            # verify (CI)
    python scripts/qa/check_graph_core_lock.py --update   # re-pin after changing the core

A change to the core is a change to every kernel that vendors it: re-pin in the same
commit, bump `CORE_VERSION` when what a valid document is moves, and say in the PR that
the kernels must re-vendor. It is the mirror of `check_graph_sync.py`, which guards the
opposite direction (the solid engine, canonical in Yantra4D, vendored here).

Read-proof and fail-closed: a missing lock, a missing or extra file, or a mismatch fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "src" / "hyperobject_graph"
LOCK = PKG / "core.lock.json"


def core_files() -> list[str]:
    """The files a kernel vendors: every module and the schema, never caches or the lock."""
    return sorted(
        p.name for p in PKG.iterdir()
        if p.is_file() and p.suffix in (".py", ".json") and p.name != LOCK.name
    )


def _hash(name: str) -> str:
    return hashlib.sha256((PKG / name).read_bytes()).hexdigest()


def _versions() -> tuple[str, str]:
    sys.path.insert(0, str(ROOT / "src"))
    import hyperobject_graph as core

    return core.CORE_VERSION, core.FORMAT_VERSION


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--update", action="store_true", help="re-pin core.lock.json")
    args = ap.parse_args()

    files = core_files()
    core_version, format_version = _versions()
    current = {name: _hash(name) for name in files}

    if args.update:
        LOCK.write_text(json.dumps({
            "_comment": "sha256 of every file of the hyperobject graph core (RFC 0067). "
                        "Canonical in madfam-org/hyperobjects-spec; kernels vendor the "
                        "directory and pin these hashes. See docs/GRAPH_CORE.md.",
            "canonical_repo": "madfam-org/hyperobjects-spec",
            "canonical_path": "src/hyperobject_graph",
            "core_version": core_version,
            "format_version": format_version,
            "hashes": current,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"check_graph_core_lock: re-pinned {len(current)} files")
        return 0

    if not LOCK.is_file():
        print("check_graph_core_lock: FAIL — core.lock.json missing (run --update)")
        return 1
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    locked = lock.get("hashes", {})
    problems = []
    for name in sorted(set(locked) | set(current)):
        if name not in current:
            problems.append(f"{name}: locked but not in the package")
        elif name not in locked:
            problems.append(f"{name}: in the package but not locked")
        elif locked[name] != current[name]:
            problems.append(f"{name}: changed since the lock was written")
    if lock.get("core_version") != core_version:
        problems.append(f"core_version {lock.get('core_version')!r} ≠ package {core_version!r}")
    if lock.get("format_version") != format_version:
        problems.append(
            f"format_version {lock.get('format_version')!r} ≠ package {format_version!r}"
        )
    print(f"check_graph_core_lock: files={len(current)} problems={len(problems)}")
    for p in problems:
        print(f"  FAIL {p} — re-pin with --update in the same commit (docs/GRAPH_CORE.md)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
