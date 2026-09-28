"""Verify the installed graph drift contract survives wheel packaging."""

from __future__ import annotations

import hashlib
import json
import sys
from zipfile import ZipFile


def main() -> None:
    with ZipFile(sys.argv[1]) as wheel:
        root = "y4d_spec/graph/"
        lock = json.loads(wheel.read(root + "graph.lock.json"))
        for name, expected in lock["hashes"].items():
            actual = hashlib.sha256(wheel.read(root + name)).hexdigest()
            if actual != expected:
                raise SystemExit(f"graph wheel hash mismatch: {name}")
        print(f"graph wheel: verified {len(lock['hashes'])} locked files")


if __name__ == "__main__":
    main()
