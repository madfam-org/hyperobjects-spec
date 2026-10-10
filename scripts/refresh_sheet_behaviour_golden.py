#!/usr/bin/env python3
"""Rebuild the sheet-behaviour goldens, or check that they are current.

    python3 scripts/refresh_sheet_behaviour_golden.py           # rewrite them
    python3 scripts/refresh_sheet_behaviour_golden.py --check    # report drift, change nothing

Inputs live in ``tests/fixtures/sheet-behaviour/`` (provenance in its ``NOTICE.md``):

* ``cards/pliego/<slug>/stock.json`` — Pliego stock cards, mapped by ``pliego-stock/1``;
* ``cards/fashion-cabinet/<slug>/material.json`` — fabric cards, ``fc-fabric/1``;
* ``thin-prints/*.json`` — thin-print descriptors over ``cards/yantra4d``,
  ``y4d-thin-print/1``;
* ``laminates/*.json`` — laminate documents whose ``material_ref`` layers resolve against
  ``cards/`` (``laminate/1``).

Each golden is the canonical document the rule writes today (2-space JSON, UTF-8,
trailing newline). A moved golden is never "fixed" by refreshing alone: review the diff,
because every number in it is one some engine will read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hyperobjects_sheet import (
    laminate_behaviour,
    map_fc_fabric,
    map_pliego_stock,
    resolver_for,
    thin_print,
    validate,
)

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "sheet-behaviour"
CARDS = FIXTURES / "cards"
GOLDEN = FIXTURES / "golden"
MATERIALS = {p: CARDS / p for p in ("pliego", "fashion-cabinet", "yantra4d")}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(doc: dict) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def laminate_document(path: Path) -> dict:
    return laminate_behaviour(_read(path), resolver_for(MATERIALS))


def targets() -> list[tuple[Path, dict]]:
    """(golden path, freshly computed document) for every golden."""
    out: list[tuple[Path, dict]] = []
    for card in sorted((CARDS / "pliego").glob("*/stock.json")):
        out.append((GOLDEN / "pliego" / f"{card.parent.name}.json", map_pliego_stock(_read(card))))
    for card in sorted((CARDS / "fashion-cabinet").glob("*/material.json")):
        out.append((GOLDEN / "fashion-cabinet" / f"{card.parent.name}.json",
                    map_fc_fabric(_read(card))))
    for desc in sorted((FIXTURES / "thin-prints").glob("*.json")):
        spec = _read(desc)
        slug = spec["material_ref"]["material_slug"]
        card = _read(CARDS / "yantra4d" / slug / "material.json")
        out.append((GOLDEN / "thin-prints" / desc.name, thin_print(spec, card)))
    for lam in sorted((FIXTURES / "laminates").glob("*.json")):
        out.append((GOLDEN / "laminates" / lam.name, laminate_document(lam)))
    return out


def main(argv: list[str]) -> int:
    check = "--check" in argv
    drifted = invalid = 0
    pairs = targets()
    expected = {path for path, _ in pairs}
    for path, doc in pairs:
        verdict = validate(doc)
        if not verdict.ok:
            invalid += 1
            for err in verdict.errors:
                print(f"  INVALID {path.relative_to(REPO)}: {err}")
        text = dump(doc)
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current != text:
            drifted += 1
            print(f"  {'drift' if check else 'write'} {path.relative_to(REPO)}")
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
    stray = sorted(p for p in GOLDEN.rglob("*.json") if p not in expected)
    for p in stray:
        print(f"  stray {p.relative_to(REPO)} (no input produces it)")
    print(f"sheet golden: documents={len(pairs)} drifted={drifted} invalid={invalid} "
          f"stray={len(stray)}")
    if check:
        return 1 if (drifted or invalid or stray) else 0
    return 1 if invalid else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
