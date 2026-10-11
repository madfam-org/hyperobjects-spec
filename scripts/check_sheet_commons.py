#!/usr/bin/env python3
"""Build every sheet document of the sheet commons with a Pliego kernel, then check them.

The keystone does not run the Pliego kernel (``pliego-spec check cartridge`` says
``documents=NOT built``). This script is the whole-commons half of that bargain, run by
hand against two checkouts: it asks the Pliego kernel to render every mode and every
preset of every cartridge (``python -m pliego.cartridge <dir> --out <tmp>``), then runs
``pliego_spec.document.check_document`` (schema + the structural §8 subset) on each
document the kernel wrote. It is the false-positive analysis a sheet rule needs before a
re-pin: a document the kernel accepts and the keystone refuses is either a keystone bug
(fix the keystone) or a real document problem (report it to the commons).

    python3 scripts/check_sheet_commons.py --pliego ../pliego --commons ../sheet-hyperobjects

The kernel is stdlib-only and runs from the checkout: ``PYTHONPATH=<pliego>/packages/
kernel/src`` and ``PLIEGO_MATERIALS=<pliego>/materials`` are set for each child. Output
goes to a temporary directory that is removed afterwards (``--keep DIR`` keeps it). The
summary line is read-proof:

    check_sheet_commons: cartridges=C modes=M documents=D failures=F kernel_errors=K

A mode with no default document, a non-zero kernel exit, a timeout and a kernel verify
line with ``errors`` > 0 all count as ``kernel_errors``. Exit 1 when F or K is not 0.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pliego_spec.document import check_document


def _render(python: str, pliego: Path, commons: Path, slug: str, out: Path,
            timeout: float) -> tuple[object, list[str]]:
    env = dict(os.environ, PYTHONPATH=str(pliego / "packages/kernel/src"),
               PLIEGO_MATERIALS=str(pliego / "materials"))
    try:
        run = subprocess.run(
            [python, "-m", "pliego.cartridge", slug, "--out", str(out)], cwd=commons, env=env,
            capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return "timeout", []
    lines = (run.stdout + run.stderr).splitlines()
    return run.returncode, [ln for ln in lines if ln.startswith("verify:")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pliego", required=True, type=Path, help="a Pliego checkout")
    ap.add_argument("--commons", required=True, type=Path, help="a sheet-hyperobjects checkout")
    ap.add_argument("--python", default=sys.executable,
                    help="the interpreter that runs the kernel (default: this one)")
    ap.add_argument("--only", nargs="*", help="check only these cartridge slugs")
    ap.add_argument("--timeout", type=float, default=900, help="seconds per cartridge")
    ap.add_argument("--keep", type=Path, help="write the documents here and keep them")
    args = ap.parse_args(argv)

    slugs = sorted(p.parent.name for p in args.commons.glob("*/project.json"))
    if args.only:
        slugs = [s for s in slugs if s in set(args.only)]
    if not slugs:
        print("check_sheet_commons: no cartridge found", file=sys.stderr)
        return 2

    tmp = None
    if args.keep is None:
        tmp = tempfile.TemporaryDirectory(prefix="sheet-commons-")
        root = Path(tmp.name)
    else:
        root = args.keep
        root.mkdir(parents=True, exist_ok=True)

    modes = documents = failures = 0
    kernel_errors: list[str] = []
    problems = collections.Counter()
    failed: dict[str, list[str]] = {}
    try:
        for slug in slugs:
            out = root / slug
            out.mkdir(parents=True, exist_ok=True)
            code, verify = _render(args.python, args.pliego.resolve(),
                                   args.commons.resolve(), slug, out, args.timeout)
            if code != 0:
                kernel_errors.append(f"{slug}: kernel exit {code}")
            kernel_errors += [f"{slug}: {v}" for v in verify if " errors=0 " not in f"{v} "]
            manifest = json.loads((args.commons / slug / "project.json").read_text("utf-8"))
            for mode in manifest.get("modes") or []:
                modes += 1
                if not (out / f"{slug}.{mode['id']}.fold").exists():
                    kernel_errors.append(f"{slug}: mode {mode['id']} wrote no document")
            for path in sorted(out.glob("*.fold")):
                documents += 1
                result = check_document(json.loads(path.read_text("utf-8")))
                if not result.ok:
                    failures += 1
                    failed[path.name] = result.problems
                    for problem in result.problems:
                        problems[problem.split(":")[0]] += 1
    finally:
        if tmp is not None:
            tmp.cleanup()

    for name, found in sorted(failed.items()):
        for problem in found:
            print(f"  FAIL {name}: {problem}")
    for line in kernel_errors:
        print(f"  KERNEL {line}")
    for label, count in problems.most_common():
        print(f"  {count:5d} {label}")
    print(f"check_sheet_commons: cartridges={len(slugs)} modes={modes} documents={documents} "
          f"failures={failures} kernel_errors={len(kernel_errors)}")
    return 1 if failures or kernel_errors else 0


if __name__ == "__main__":
    sys.exit(main())
