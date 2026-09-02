#!/usr/bin/env python3
"""Refresh the vendored commons slug snapshot from local platform checkouts.

The lexicon lane resolves every ``embodied_by`` slug against a snapshot of both
commons' slug sets, so CI can run the strict check with no platform checkout and no
network. A snapshot goes stale in exactly one direction: a term naming a cartridge
added after the capture fails the lane while being correct in the commons. That is the
safe direction — it asks for this script rather than silently passing.

    python3 scripts/refresh_catalog_snapshot.py \
        --yantra4d ../yantra4d --fashion-cabinet ../fashion-cabinet

Reads yantra4d's published ``docs/commons-catalog.json`` and enumerates fashion-cabinet's
``projects/*/project.json``, adds each repo's ``materials/*/material.json`` cards, records
the git revision of each so a reader can tell exactly what was captured, and rewrites the
bundled snapshot in place.

Material cards are in the snapshot because they are commons objects with slugs like any
other: an identity record already pairs two of them by name (``bambu-tpu-95a`` and
``tpu-panel-impreso``), and a lexicon term about cloth or filament has to be able to name
the card it is true of. Their slug spaces do not collide with the cartridges' in either
repo (checked at capture: 0 collisions on both sides).
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

SNAPSHOT = (
    Path(__file__).resolve().parent.parent
    / "src/hyperobjects_lexicon/catalogs/commons-slugs.snapshot.json"
)

COMMENT = (
    "A vendored snapshot of the two commons catalogs, reduced to the slug sets the "
    "lexicon lane needs to resolve embodied_by. It exists so CI can run the STRICT slug "
    "check hermetically, with no platform checkout. It is a snapshot, so it goes stale: "
    "a term naming a cartridge or material card added after captured_at fails here and is "
    "right in the commons. Refresh with scripts/refresh_catalog_snapshot.py, or pass "
    "--catalog with a live catalog to bypass it."
)


def _rev(repo: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _materials(repo: Path) -> list[str]:
    """The repo's material-card slugs — ``materials/<slug>/material.json``.

    Both commons carry cards; a missing directory is not an error here because the
    empty-capture guard below only refuses an empty CARTRIDGE side, and a repo may
    legitimately arrive without cards.
    """
    directory = repo / "materials"
    if not directory.is_dir():
        return []
    return sorted(
        p.name for p in directory.iterdir() if p.is_dir() and (p / "material.json").is_file()
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yantra4d", required=True, type=Path, help="path to a yantra4d checkout")
    ap.add_argument(
        "--fashion-cabinet", required=True, type=Path, help="path to a fashion-cabinet checkout"
    )
    args = ap.parse_args(argv)

    catalog = args.yantra4d / "docs/commons-catalog.json"
    if not catalog.is_file():
        print(f"ERROR: no commons catalog at {catalog}", file=sys.stderr)
        return 2
    y4d_cartridges = sorted(
        c["slug"] for c in json.loads(catalog.read_text(encoding="utf-8"))["cartridges"]
    )

    projects = args.fashion_cabinet / "projects"
    if not projects.is_dir():
        print(f"ERROR: no projects directory at {projects}", file=sys.stderr)
        return 2
    fc_cartridges = sorted(
        p.name for p in projects.iterdir() if p.is_dir() and (p / "project.json").is_file()
    )

    y4d_materials = _materials(args.yantra4d)
    fc_materials = _materials(args.fashion_cabinet)

    # Read-proof: a slug that means two things would make an embodied_by reference
    # ambiguous, and the check is one line, so do it rather than assume it.
    for repo, carts, mats in (
        ("yantra4d", y4d_cartridges, y4d_materials),
        ("fashion-cabinet", fc_cartridges, fc_materials),
    ):
        clash = sorted(set(carts) & set(mats))
        if clash:
            print(
                f"ERROR: {repo}: {len(clash)} slug(s) are both a cartridge and a material "
                f"card ({', '.join(clash[:5])}) — embodied_by could not say which",
                file=sys.stderr,
            )
            return 2

    y4d = sorted(set(y4d_cartridges) | set(y4d_materials))
    fc = sorted(set(fc_cartridges) | set(fc_materials))

    if not y4d or not fc:
        # Read-proof: an empty side would make every slug on that side "resolve" as
        # unresolvable — or worse, silently shrink the bar. Refuse instead.
        print(
            f"ERROR: empty capture (yantra4d={len(y4d)} fashion-cabinet={len(fc)})",
            file=sys.stderr,
        )
        return 2

    snapshot = {
        "schema_version": 1,
        "_comment": COMMENT,
        "captured_at": datetime.date.today().isoformat(),
        "sources": {
            "yantra4d": {
                "path": "docs/commons-catalog.json + materials/*/material.json",
                "rev": _rev(args.yantra4d),
                "count": len(y4d),
                "cartridges": len(y4d_cartridges),
                "materials": len(y4d_materials),
            },
            "fashion-cabinet": {
                "path": "projects/*/project.json + materials/*/material.json",
                "rev": _rev(args.fashion_cabinet),
                "count": len(fc),
                "cartridges": len(fc_cartridges),
                "materials": len(fc_materials),
            },
        },
        "yantra4d": y4d,
        "fashion-cabinet": fc,
    }
    SNAPSHOT.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"refreshed {SNAPSHOT}: "
        f"yantra4d={len(y4d)} ({len(y4d_cartridges)} cartridges + {len(y4d_materials)} cards) "
        f"fashion-cabinet={len(fc)} ({len(fc_cartridges)} cartridges + {len(fc_materials)} cards)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
