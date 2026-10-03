#!/usr/bin/env python3
"""SEM-1 §5 fleet gate: project EVERY cartridge and material card, check every result.

    python scripts/qa/aas_fleet_gate.py --solid <solid-commons> --soft <soft-commons> \
        [--material <material.json> ...] [--basyx auto|require|off] [--json OUT]

A commons argument is a directory whose immediate subdirectories hold a ``project.json``
(the layout of solid-hyperobjects and soft-hyperobjects). Each cartridge is built TWICE
and the two canonical byte strings compared, so determinism is measured across the
fleet rather than asserted on a fixture. Exit 0 iff every input built, checked with zero
errors and reproduced byte-identically. Progress prints every 50 inputs.

Not run in CI: CI has no commons checkout. The PR body and the lane report carry the
totals of a run against the pinned commons.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

from hyperobjects_aas.check import check_environment
from hyperobjects_aas.common import build_environment
from hyperobjects_aas.material import project_material
from hyperobjects_aas.soft import project_soft
from hyperobjects_aas.solid import project_solid
from hyperobjects_schemas.generator_output import canonical_json


def _cartridges(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.glob("*/project.json"))


def _run(label: str, items: list, build, basyx: str, totals: dict) -> None:
    stats = totals.setdefault(label, collections.Counter())
    claims = totals.setdefault(f"{label}_conformance", collections.Counter())
    failures = totals.setdefault("failures", [])
    started = time.monotonic()
    for n, item in enumerate(items, 1):
        stats["inputs"] += 1
        try:
            env_a, conformance = build(item)
            env_b, _ = build(item)
        except Exception as exc:  # a fleet gate reports every failure, whatever its type
            stats["build_errors"] += 1
            failures.append({"input": str(item), "stage": "build", "error": repr(exc)[:400]})
            continue
        a, b = canonical_json(env_a), canonical_json(env_b)
        if a != b:
            stats["nondeterministic"] += 1
            failures.append({"input": str(item), "stage": "determinism"})
        result = check_environment(env_a, basyx=basyx)
        schema_errors = sum(f.code == "schema" for f in result.errors)
        stats["schema_errors"] += schema_errors
        stats["madfam_errors"] += sum(f.code not in ("schema", "basyx") for f in result.errors)
        stats["basyx_errors"] += sum(f.code == "basyx" for f in result.errors)
        stats["warnings"] += len(result.warnings)
        stats[f"basyx_{result.basyx.replace(' ', '_')}"] += 1
        stats["submodels"] += len(env_a.get("submodels") or [])
        stats["concept_descriptions"] += len(env_a.get("conceptDescriptions") or [])
        stats["bytes"] += len(a)
        for c in conformance:
            claims[f"{c.submodel}:{c.claimed}"] += 1
        if not result.ok:
            failures.append({"input": str(item), "stage": "check",
                             "findings": [str(f) for f in result.errors[:5]]})
        else:
            stats["ok"] += 1
        if n % 50 == 0 or n == len(items):
            print(f"  {label}: {n}/{len(items)} ({time.monotonic() - started:.0f}s)", flush=True)


def _solid(path: Path):
    proj = project_solid(path)
    return build_environment(proj), proj.conformance


def _soft(path: Path):
    proj = project_soft(path)
    return build_environment(proj), proj.conformance


def _material(path: Path):
    proj = project_material(path)
    return proj.environment(), proj.conformance


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--solid", type=Path)
    ap.add_argument("--soft", type=Path)
    ap.add_argument("--material", type=Path, nargs="*", default=[])
    ap.add_argument("--basyx", choices=("auto", "require", "off"), default="auto")
    ap.add_argument("--json", type=Path, help="write the totals and failures here")
    args = ap.parse_args(argv)
    totals: dict = {}
    if args.solid:
        _run("solid", _cartridges(args.solid), _solid, args.basyx, totals)
    if args.soft:
        _run("soft", _cartridges(args.soft), _soft, args.basyx, totals)
    if args.material:
        _run("material", sorted(args.material), _material, args.basyx, totals)
    inputs = sum(v["inputs"] for k, v in totals.items() if k in ("solid", "soft", "material"))
    if not inputs:
        print("aas fleet gate: ERROR checked=0 inputs")
        return 2
    for label in ("solid", "soft", "material"):
        if label in totals:
            print(f"{label}: " + " ".join(f"{k}={v}" for k, v in sorted(totals[label].items())))
            print(f"{label} conformance: " + " ".join(
                f"{k}={v}" for k, v in sorted(totals[f"{label}_conformance"].items())))
    failures = totals.get("failures", [])
    for f in failures[:20]:
        print(f"  FAIL {json.dumps(f, ensure_ascii=False)}")
    print(f"aas fleet gate: inputs={inputs} failures={len(failures)}")
    if args.json:
        args.json.write_text(json.dumps(totals, indent=2, sort_keys=True, default=dict) + "\n",
                             encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
