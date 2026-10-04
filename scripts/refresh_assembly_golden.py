#!/usr/bin/env python3
"""Rebuild the golden AAS environments of assemblies A and B (ASM-1 §5).

    python3 scripts/refresh_assembly_golden.py           # rewrite the golden files
    python3 scripts/refresh_assembly_golden.py --check    # report drift, change nothing

Inputs are the byte-identical copies of the solid commons in
``tests/fixtures/assembly-golden/commons`` (see its NOTICE.md); outputs are
``tests/fixtures/assembly-golden/golden/<slug>.aas.json``, exactly what
``y4d-spec aas build <assembly-dir>`` writes (canonical JSON, GOC-1 §3.1). The projection
attaches lexicon terms and copies template descriptions, so a lexicon or template edit
moves these files on purpose: rerun this script and review the diff.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hyperobjects_aas.assembly import build_assembly_environment
from hyperobjects_aas.resolver import bundled_standard_parts_dir
from hyperobjects_schemas.generator_output import canonical_json
from y4d_spec.assembly import CompositeResolver, validate_assembly

ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "assembly-golden"
COMMONS = ROOT / "commons"
GOLDEN = ROOT / "golden"
SLUGS = ("voron-2-4-class-350-motion-frame", "fpv-5in-freestyle")


def build(slug: str) -> bytes:
    doc = json.loads((COMMONS / "assemblies" / slug / "assembly.json").read_text("utf-8"))
    resolver = CompositeResolver.for_directories(COMMONS, bundled_standard_parts_dir())
    report = validate_assembly(doc, resolver)
    if not report.ok:
        raise SystemExit(f"{slug}: the golden assembly no longer passes: "
                         + "; ".join(map(str, report.errors)))
    return canonical_json(build_assembly_environment(doc, report))


def main(argv: list[str]) -> int:
    check = "--check" in argv
    drifted = 0
    for slug in SLUGS:
        path = GOLDEN / f"{slug}.aas.json"
        data = build(slug)
        if path.is_file() and path.read_bytes() == data:
            continue
        drifted += 1
        if check:
            print(f"drift: {path.relative_to(ROOT.parent.parent.parent)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print(f"wrote {path.relative_to(ROOT.parent.parent.parent)}")
    print(f"assembly golden: files={len(SLUGS)} drifted={drifted}")
    return 1 if check and drifted else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
