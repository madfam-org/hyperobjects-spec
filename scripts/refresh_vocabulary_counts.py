#!/usr/bin/env python3
"""Re-count the controlled vocabularies against local platform checkouts.

A vocabulary is a reading of a corpus at a moment. The COUNTS in it go stale the day a
wave lands, and — more importantly — a new key can appear that the vocabulary has never
heard of, which is exactly the drift the vocabulary exists to stop.

    python3 scripts/refresh_vocabulary_counts.py \\
        --yantra4d ../yantra4d --fashion-cabinet ../fashion-cabinet

What it does:

* rewrites every entry's ``observed`` block and the document's ``captured`` block from
  what the two checkouts actually contain, leaving every curated field alone — glosses,
  terms, aliases, equivalences, rulings;
* prints, and **fails on**, any key in either commons that no entry and no alias covers.
  That failure is the point: a new capability key is a decision to record, and a silent
  absence would let the vocabulary drift back into a list of what somebody once saw.

It does not invent entries. Adding one is an editorial act — a gloss, and often a term —
and this script is deliberately unable to perform it.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import subprocess
import sys
from pathlib import Path

VOCAB_DIR = (
    Path(__file__).resolve().parent.parent / "src/hyperobjects_lexicon/vocabularies"
)


def _rev(repo: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


class _Tally:
    """Interfaces and distinct cartridges per key, kept per ROLE.

    Types and ids are counted separately and never merged, because the same word is
    often both: Fashion Cabinet's `hem` is an interface type on 160 cartridges AND an
    interface id on many of those same ones, and adding the two would report a number
    that is true of nothing.
    """

    def __init__(self) -> None:
        self.ifaces = collections.Counter()
        self.carts = collections.defaultdict(set)

    def add(self, key: str | None, slug: str) -> None:
        if key:
            self.ifaces[key] += 1
            self.carts[key].add(slug)

    def observed(self, key: str) -> dict:
        return {"cartridges": len(self.carts.get(key, ())), "interfaces": self.ifaces.get(key, 0)}


def _y4d_counts(repo: Path):
    """Interface counts from the published commons catalog: types, and ids."""
    catalog = json.loads(
        (repo / "docs/commons-catalog.json").read_text(encoding="utf-8")
    )["cartridges"]
    types, ids = _Tally(), _Tally()
    for cart in catalog:
        for iface in cart.get("cdg_interfaces") or []:
            types.add(iface.get("geometry_type"), cart["slug"])
            ids.add(iface.get("id"), cart["slug"])
    return len(catalog), types, ids


def _fc_counts(repo: Path):
    """Interface and capability counts from the garment manifests."""
    types, ids = _Tally(), _Tally()
    cap_carts = collections.Counter()
    cap_true = collections.Counter()
    projects = sorted((repo / "projects").glob("*/project.json"))
    for path in projects:
        slug = path.parent.name
        block = json.loads(path.read_text(encoding="utf-8")).get("hyperobject") or {}
        for iface in block.get("interfaces") or []:
            types.add(iface.get("type"), slug)
            ids.add(iface.get("id"), slug)
        for key, value in (block.get("capabilities") or {}).items():
            cap_carts[key] += 1
            if value:
                cap_true[key] += 1
    return len(projects), types, ids, cap_carts, cap_true


def _observed_for(entry: dict, key: str, repo: str, tallies: dict) -> dict:
    """The counts that belong to this entry, chosen by its role."""
    if entry["role"] == "capability_flag":
        cap_carts, cap_true = tallies["capabilities"]
        return {"cartridges": cap_carts.get(key, 0), "true": cap_true.get(key, 0)}
    which = "ids" if entry["role"] == "interface_id" else "types"
    return tallies[repo][which].observed(key)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yantra4d", required=True, type=Path)
    ap.add_argument("--fashion-cabinet", required=True, type=Path)
    ap.add_argument(
        "--check",
        action="store_true",
        help="report drift and change nothing (what a CI lane would run)",
    )
    args = ap.parse_args(argv)

    y4d_total, y4d_types, y4d_ids = _y4d_counts(args.yantra4d)
    fc_total, fc_types, fc_ids, cap_carts, cap_true = _fc_counts(args.fashion_cabinet)
    tallies = {
        "yantra4d": {"types": y4d_types, "ids": y4d_ids},
        "fashion-cabinet": {"types": fc_types, "ids": fc_ids},
        "capabilities": (cap_carts, cap_true),
    }

    captured = {
        "date": datetime.date.today().isoformat(),
        "sources": {
            "yantra4d": {
                "path": "docs/commons-catalog.json",
                "rev": _rev(args.yantra4d),
                "cartridges": y4d_total,
            },
            "fashion-cabinet": {
                "path": "projects/*/project.json",
                "rev": _rev(args.fashion_cabinet),
                "cartridges": fc_total,
            },
        },
    }

    covered: dict[str, set[str]] = {"yantra4d": set(), "fashion-cabinet": set()}
    changed = []

    for name in ("interfaces", "capabilities"):
        path = VOCAB_DIR / f"{name}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        for entry in doc["entries"]:
            repo, key = entry["repo"], entry["key"]
            covered[repo].add(key)
            for alias in entry.get("aliases") or []:
                covered[alias["repo"]].add(alias["name"])

            observed = _observed_for(entry, key, repo, tallies)
            if entry.get("observed") != observed:
                changed.append(f"{name}: {repo}/{key} {entry.get('observed')} -> {observed}")
            entry["observed"] = observed

            for alias in entry.get("aliases") or []:
                if "observed" in alias:
                    alias["observed"] = _observed_for(
                        entry, alias["name"], alias["repo"], tallies
                    )

        doc["captured"] = captured
        if not args.check:
            path.write_text(
                json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    # The drift that matters: a key nobody has placed. Interface IDS are deliberately not
    # exhaustive (an id is a cartridge's own name for its own feature), so only the
    # enumerable spaces are checked — the two type enums and the capability keys.
    unknown = sorted(k for k in cap_carts if k not in covered["fashion-cabinet"])
    y4d_types = {
        i.get("geometry_type")
        for cart in json.loads(
            (args.yantra4d / "docs/commons-catalog.json").read_text(encoding="utf-8")
        )["cartridges"]
        for i in cart.get("cdg_interfaces") or []
    }
    unknown_types = sorted(t for t in y4d_types if t and t not in covered["yantra4d"])

    for line in changed:
        print(f"  count {line}")
    print(
        f"vocabulary counts: yantra4d={y4d_total} cartridges fashion-cabinet={fc_total} "
        f"cartridges changed={len(changed)} "
        f"{'(checked, not written)' if args.check else '(written)'}"
    )

    if unknown or unknown_types:
        for key in unknown:
            print(
                f"  UNPLACED fashion-cabinet capability key {key!r} "
                f"({cap_carts[key]} cartridges)"
            )
        for key in unknown_types:
            print(f"  UNPLACED yantra4d geometry_type {key!r}")
        print(
            "A key nobody has placed is the drift this vocabulary exists to stop. Add an "
            "entry — with a gloss, and with a term if two or more cartridges write it."
        )
        return 1
    print("no unplaced keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
