"""Verify the installed graph drift contract survives wheel packaging.

Also verifies that every schema `hyperobjects_schemas.SCHEMAS` declares is in the
wheel and byte-identical to the source tree: consumers pin this package by SHA and
`load()` reads the installed copy, so a schema missing from the wheel (a package-data
glob that stopped matching) would only surface downstream.

And the device-control vocabulary's input-code table: it must be in the wheel, byte for
byte, and `y4d_spec.device.input_codes()` must load it from the wheel's own files. The
second is run in a fresh interpreter (`-I`) whose only copy of the package is the
unpacked wheel, so it cannot pass by reading the source tree.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

REPO = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO / "src" / "hyperobjects_schemas" / "schemas"
INPUT_CODES = "y4d_spec/device/input-codes.json"
LOAD_INPUT_CODES = """
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
import y4d_spec.device as device
where = Path(device.__file__).resolve()
assert root in where.parents, f"imported {where}, not the unpacked wheel"
table = device.input_codes()
print(json.dumps({"tag": table["source"]["tag"], "names": sum(map(len, table["codes"].values()))}))
"""


def _check_input_codes(wheel: ZipFile) -> None:
    if wheel.read(INPUT_CODES) != (REPO / "src" / INPUT_CODES).read_bytes():
        raise SystemExit(f"device table in wheel differs from source: {INPUT_CODES}")
    expected = json.loads((REPO / "src" / INPUT_CODES).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="wheel-") as root:
        wheel.extractall(root)
        run = subprocess.run(
            [sys.executable, "-I", "-c", LOAD_INPUT_CODES, root],
            capture_output=True, text=True, check=False,
        )
    if run.returncode != 0:
        raise SystemExit(f"input_codes() did not load from the wheel:\n{run.stderr}")
    loaded = json.loads(run.stdout.strip().splitlines()[-1])
    names = sum(map(len, expected["codes"].values()))
    if loaded != {"tag": expected["source"]["tag"], "names": names}:
        raise SystemExit(f"input_codes() from the wheel read {loaded}, expected {names} names")
    print(f"device wheel: input_codes() loaded {names} names from the unpacked wheel")


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

        # The graph core (RFC 0067) is what kernels vendor by hash, from the INSTALLED
        # package at their SPEC_PIN: every locked file must be in the wheel, unchanged.
        core = "hyperobject_graph/"
        core_lock = json.loads(wheel.read(core + "core.lock.json"))
        for name, expected in core_lock["hashes"].items():
            if hashlib.sha256(wheel.read(core + name)).hexdigest() != expected:
                raise SystemExit(f"graph-core wheel hash mismatch: {name}")
        print(f"graph-core wheel: verified {len(core_lock['hashes'])} locked files")

        names = set(wheel.namelist())
        schemas = _declared_schemas()
        for name in schemas:
            member = f"hyperobjects_schemas/schemas/{name}.schema.json"
            if member not in names:
                raise SystemExit(f"schema missing from wheel: {member}")
            if wheel.read(member) != (SCHEMA_DIR / f"{name}.schema.json").read_bytes():
                raise SystemExit(f"schema in wheel differs from source: {member}")
        print(f"schema wheel: verified {len(schemas)} bundled schemas")

        _check_input_codes(wheel)


if __name__ == "__main__":
    main()
