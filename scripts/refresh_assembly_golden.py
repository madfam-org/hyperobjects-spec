#!/usr/bin/env python3
"""Rebuild the golden AAS environments, and guard the projection version (SEM-1 §1).

    python3 scripts/refresh_assembly_golden.py           # rewrite the golden files
    python3 scripts/refresh_assembly_golden.py --check    # report drift, change nothing

The goldens are one of every kind of shell the projection mints:

* assemblies A and B (ASM-1 §5) and the nine solid cartridges they use, from the
  byte-identical copies of the solid commons in ``tests/fixtures/assembly-golden/commons``
  (see its NOTICE.md), written to ``tests/fixtures/assembly-golden/golden/`` and
  ``…/golden/cartridges/``;
* one soft garment (``tests/fixtures/aas/sem1-garment``) and one material card
  (``tests/fixtures/aas/bambu-tpu-95a.material.json``), written to
  ``tests/fixtures/aas/golden/``.

Each file is exactly what ``y4d-spec aas build`` / ``build-material`` writes (canonical
JSON, GOC-1 §3.1), and records the projection version it was made with: in every id
(``…/p{N}``) and in the shell's ``ProjectionVersion`` extension.

**The drift guard.** Shells and submodels are immutable per id (asset-shells answers a
409 to different bytes under a stored id), so a rebuild that changes the bytes under an
id the golden already carries means the projection moved for the same inputs. That is
refused, in both modes, until ``hyperobjects_aas.ids.PROJECTION_VERSION`` is bumped; the
bumped projection then mints new ids and the refresh goes through. Moved ids (an input
changed) and ConceptDescription-only changes (a lexicon or template text edit; the store
updates those in place) are ordinary drift: rerun this script and review the diff.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from hyperobjects_aas import (
    build_material_environment,
    build_soft_environment,
    build_solid_environment,
    ids,
)
from hyperobjects_aas.assembly import build_assembly_environment
from hyperobjects_aas.drift import immutable_drift
from hyperobjects_aas.resolver import bundled_standard_parts_dir
from hyperobjects_schemas.generator_output import canonical_json
from y4d_spec.assembly import CompositeResolver, validate_assembly

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "tests" / "fixtures" / "assembly-golden"
COMMONS = ROOT / "commons"
GOLDEN = ROOT / "golden"
AAS_FIXTURES = REPO / "tests" / "fixtures" / "aas"
AAS_GOLDEN = AAS_FIXTURES / "golden"
SLUGS = ("voron-2-4-class-350-motion-frame", "fpv-5in-freestyle")
SOFT = "sem1-garment"
MATERIAL = "bambu-tpu-95a"

#: (golden path, builder) pairs; the builder returns the environment.
Target = tuple[Path, Callable[[], dict]]


def build(slug: str) -> bytes:
    """The canonical JSON of assembly ``slug``'s environment."""
    return canonical_json(_assembly(slug))


def _assembly(slug: str) -> dict:
    doc = json.loads((COMMONS / "assemblies" / slug / "assembly.json").read_text("utf-8"))
    resolver = CompositeResolver.for_directories(COMMONS, bundled_standard_parts_dir())
    report = validate_assembly(doc, resolver)
    if not report.ok:
        raise SystemExit(f"{slug}: the golden assembly no longer passes: "
                         + "; ".join(map(str, report.errors)))
    return build_assembly_environment(doc, report)


def cartridges() -> list[Path]:
    """The solid cartridges assemblies A and B use (every cartridge directory copied)."""
    return sorted(p for p in COMMONS.iterdir() if (p / "project.json").is_file())


def targets() -> list[Target]:
    out: list[Target] = [(GOLDEN / f"{slug}.aas.json", lambda s=slug: _assembly(s))
                         for slug in SLUGS]
    out += [(GOLDEN / "cartridges" / f"{d.name}.aas.json", lambda d=d: build_solid_environment(d))
            for d in cartridges()]
    out.append((AAS_GOLDEN / f"{SOFT}.aas.json",
                lambda: build_soft_environment(AAS_FIXTURES / SOFT)))
    out.append((AAS_GOLDEN / f"{MATERIAL}.aas.json",
                lambda: build_material_environment(AAS_FIXTURES / f"{MATERIAL}.material.json")))
    return out


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def main(argv: list[str], goldens: list[Target] | None = None) -> int:
    check = "--check" in argv
    goldens = targets() if goldens is None else goldens
    drifted = blocked = 0
    for path, builder in goldens:
        data = canonical_json(builder())
        if path.is_file() and path.read_bytes() == data:
            continue
        frozen = immutable_drift(json.loads(path.read_bytes()), json.loads(data)) \
            if path.is_file() else []
        if frozen:
            blocked += 1
            print(f"immutable drift: {_rel(path)}: the projection changed the bytes under "
                  f"{len(frozen)} id(s) it already minted, e.g. {frozen[0]}. Bump "
                  f"hyperobjects_aas.ids.PROJECTION_VERSION (now {ids.PROJECTION_VERSION}) and "
                  "rerun; a store refuses different bytes under a stored id (409).")
            continue
        drifted += 1
        if check:
            print(f"drift: {_rel(path)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print(f"wrote {_rel(path)}")
    print(f"projection golden: files={len(goldens)} projection_version={ids.PROJECTION_VERSION} "
          f"drifted={drifted} immutable_drift={blocked}")
    return 1 if blocked or (check and drifted) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
