"""Verify the installed graph drift contract survives wheel packaging.

Also verifies that every schema `hyperobjects_schemas.SCHEMAS` declares is in the
wheel and byte-identical to the source tree: consumers pin this package by SHA and
`load()` reads the installed copy, so a schema missing from the wheel (a package-data
glob that stopped matching) would only surface downstream.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile

REPO = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO / "src" / "hyperobjects_schemas" / "schemas"


def _declared_schemas() -> list[str]:
    sys.path.insert(0, str(REPO / "src"))
    from hyperobjects_schemas import SCHEMAS

    return sorted(SCHEMAS)


def main() -> None:
    with ZipFile(sys.argv[1]) as wheel:
        root = "y4d_spec/graph/"
        lock = json.loads(wheel.read(root + "graph.lock.json"))
        for name, expected in lock["hashes"].items():
            actual = hashlib.sha256(wheel.read(root + name)).hexdigest()
            if actual != expected:
                raise SystemExit(f"graph wheel hash mismatch: {name}")
        print(f"graph wheel: verified {len(lock['hashes'])} locked files")

        names = set(wheel.namelist())
        schemas = _declared_schemas()
        for name in schemas:
            member = f"hyperobjects_schemas/schemas/{name}.schema.json"
            if member not in names:
                raise SystemExit(f"schema missing from wheel: {member}")
            if wheel.read(member) != (SCHEMA_DIR / f"{name}.schema.json").read_bytes():
                raise SystemExit(f"schema in wheel differs from source: {member}")
        print(f"schema wheel: verified {len(schemas)} bundled schemas")


if __name__ == "__main__":
    main()
