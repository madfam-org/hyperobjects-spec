#!/usr/bin/env python3
"""Rebuild the golden pose files (ASM-1 §9), or check that they are current.

    python3 scripts/refresh_pose_golden.py           # rewrite them
    python3 scripts/refresh_pose_golden.py --check    # report drift, change nothing (CI)

A golden pose file (`hyperobjects.assembly-poses`, `y4d_spec.assembly.posing`) holds the
keystone's reference forward kinematics at every pose of an assembly's sweep — home, each
driven joint's limits, and the Halton samples — as canonical fixed-format strings. A viewer
(yantra4d, Phase 7) proves parity by reproducing them. The files:

* assemblies A and B, from the byte-identical commons copies in
  ``tests/fixtures/assembly-golden/commons`` (rigid today: one pose each), written to
  ``tests/fixtures/assembly-golden/poses/``;
* the kinematic gantry fixture (``tests/fixtures/kinematics/``: a passive carriage closing
  a cycle, an X carriage, a follower pulley and a closed belt loop), resolved against the
  bundled catalog plus the fixture's own test belt.

A moved pose is never "fixed" by refreshing alone: review the diff — every number in it is
a placement some viewer reproduces.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hyperobjects_aas.resolver import bundled_standard_parts_dir
from y4d_spec.assembly import CompositeResolver, golden_poses_json, validate_assembly

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "fixtures" / "assembly-golden"
KINEMATICS = REPO / "tests" / "fixtures" / "kinematics"
SLUGS = ("voron-2-4-class-350-motion-frame", "fpv-5in-freestyle")
FIXTURES = ("kinematic-gantry",)


def kinematic_fixture_resolver() -> CompositeResolver:
    """The bundled catalog, then the fixture's own test parts (the test belt)."""
    return CompositeResolver.for_directories(
        standard_parts=[bundled_standard_parts_dir(), KINEMATICS / "standard-parts"])


def targets() -> list[tuple[Path, Path, CompositeResolver]]:
    """(assembly.json, golden pose file, resolver) for every golden."""
    out = [(GOLDEN / "commons" / "assemblies" / slug / "assembly.json",
            GOLDEN / "poses" / f"{slug}.poses.json",
            CompositeResolver.for_directories(GOLDEN / "commons", bundled_standard_parts_dir()))
           for slug in SLUGS]
    out += [(KINEMATICS / f"{name}.assembly.json", KINEMATICS / f"{name}.poses.json",
             kinematic_fixture_resolver()) for name in FIXTURES]
    return out


def build(document: Path, resolver: CompositeResolver) -> str:
    doc = json.loads(document.read_text("utf-8"))
    report = validate_assembly(doc, resolver)
    if not report.ok:
        raise SystemExit(f"{document}: the assembly no longer passes: "
                         + "; ".join(map(str, report.errors)))
    return golden_poses_json(doc, report)


def main(argv: list[str]) -> int:
    check = "--check" in argv
    drifted = 0
    for document, golden, resolver in targets():
        text = build(document, resolver)
        if golden.is_file() and golden.read_text("utf-8") == text:
            continue
        drifted += 1
        rel = golden.relative_to(REPO)
        if check:
            print(f"drift: {rel} differs from the reference forward kinematics; run "
                  "scripts/refresh_pose_golden.py and review the diff")
        else:
            golden.parent.mkdir(parents=True, exist_ok=True)
            golden.write_text(text, "utf-8")
            print(f"wrote {rel}")
    print(f"pose golden: files={len(targets())} drifted={drifted}")
    return 1 if check and drifted else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
