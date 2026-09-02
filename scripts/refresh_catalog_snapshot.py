#!/usr/bin/env python3
"""Refresh the vendored commons slug snapshot from a commit of each platform repo.

The lexicon lane resolves every ``embodied_by`` slug against a snapshot of both
commons' slug sets, so CI can run the strict check with no platform checkout and no
network. A snapshot goes stale in exactly one direction: a term naming a cartridge
added after the capture fails the lane while being correct in the commons. That is the
safe direction — it asks for this script rather than silently passing.

    python3 scripts/refresh_catalog_snapshot.py \\
        --yantra4d ../yantra4d --fashion-cabinet ../fashion-cabinet

**Why it reads through ``git show`` rather than the working tree**, and why the recorded
rev is the FULL sha. Both are the posture its two siblings already take —
``refresh_reader_snapshots.py`` for the G4 catalogs and ``refresh_vocabulary_counts.py``
for the G3 vocabularies — adopted here so every capture block in this repo means the same
thing. Naming the ref (``--yantra4d-ref`` / ``--fashion-cabinet-ref``, both defaulting to
``origin/main``) and reading every file out of that commit means the capture records the
commit it was actually built from: a refresh never needs a shared platform clone to be
moved off its branch, cannot silently capture uncommitted work, and never has to
materialise a private submodule the superproject merely points at. The sha is written in
full because an abbreviation is a guess a later reader has to resolve — and because this
file carrying a 7-character rev while the documents one directory over carried the full
one made the same fact about the same repo look like two different kinds of fact.

Reads yantra4d's published ``docs/commons-catalog.json`` and enumerates fashion-cabinet's
``projects/*/project.json``, adds each repo's ``materials/*/material.json`` cards, records
the commit each was read at so a reader can tell exactly what was captured, and rewrites
the bundled snapshot in place.

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


def _run(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True)


def _commit(repo: Path, ref: str) -> str:
    """The full sha ``ref`` resolves to in ``repo``."""
    return _run(repo, "rev-parse", ref).strip()


def _show_json(repo: Path, ref: str, path: str) -> object:
    return json.loads(_run(repo, "show", f"{ref}:{path}"))


def _slugs_at(repo: Path, ref: str, directory: str, filename: str) -> list[str]:
    """``<directory>/<slug>/<filename>`` in that commit, as sorted slugs.

    ``git ls-tree`` rather than a directory walk: the whole point of reading through the
    commit is that a slug nobody committed is not a slug the commons has. A missing
    directory is not an error — ls-tree simply lists nothing, and both commons are
    entitled to arrive without material cards.
    """
    try:
        listing = _run(repo, "ls-tree", "-r", "--name-only", ref, f"{directory}/")
    except subprocess.CalledProcessError:
        return []
    out = []
    for line in listing.splitlines():
        parts = line.split("/")
        if len(parts) == 3 and parts[0] == directory and parts[2] == filename:
            out.append(parts[1])
    return sorted(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yantra4d", required=True, type=Path, help="path to a yantra4d clone")
    ap.add_argument(
        "--fashion-cabinet", required=True, type=Path, help="path to a fashion-cabinet clone"
    )
    ap.add_argument(
        "--yantra4d-ref",
        default="origin/main",
        help="the commit-ish to read yantra4d at (default: origin/main)",
    )
    ap.add_argument(
        "--fashion-cabinet-ref",
        default="origin/main",
        help="the commit-ish to read fashion-cabinet at (default: origin/main)",
    )
    args = ap.parse_args(argv)

    try:
        y4d_sha = _commit(args.yantra4d, args.yantra4d_ref)
        fc_sha = _commit(args.fashion_cabinet, args.fashion_cabinet_ref)
        y4d_catalog = _show_json(args.yantra4d, y4d_sha, "docs/commons-catalog.json")
        y4d_cartridges = sorted(c["slug"] for c in y4d_catalog["cartridges"])
        y4d_materials = _slugs_at(args.yantra4d, y4d_sha, "materials", "material.json")
        fc_cartridges = _slugs_at(args.fashion_cabinet, fc_sha, "projects", "project.json")
        fc_materials = _slugs_at(args.fashion_cabinet, fc_sha, "materials", "material.json")
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError) as exc:
        print(
            f"ERROR: cannot read the commons (yantra4d@{args.yantra4d_ref}, "
            f"fashion-cabinet@{args.fashion_cabinet_ref}) — {exc}",
            file=sys.stderr,
        )
        return 2

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
                "rev": y4d_sha,
                "count": len(y4d),
                "cartridges": len(y4d_cartridges),
                "materials": len(y4d_materials),
            },
            "fashion-cabinet": {
                "path": "projects/*/project.json + materials/*/material.json",
                "rev": fc_sha,
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
        f"yantra4d {y4d_sha[:9]} {len(y4d)} "
        f"({len(y4d_cartridges)} cartridges + {len(y4d_materials)} cards) "
        f"fashion-cabinet {fc_sha[:9]} {len(fc)} "
        f"({len(fc_cartridges)} cartridges + {len(fc_materials)} cards)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
