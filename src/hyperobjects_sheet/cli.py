"""``fc-spec sheet …`` / ``y4d-spec sheet …``: the sheet-behaviour contract on the CLI.

    sheet check <file>...                         validate sheet_behaviour documents
    sheet map <platform> <card|descriptor> [...]  a card → sheet_behaviour (JSON)
    sheet resolve <ref|file>... --materials P=DIR material_ref, name-level
    sheet laminate <file> [--materials P=DIR]     A, B, D and the stack's sheet_behaviour

The contract belongs to no single commons, so both tools expose it (as they do the
lexicon). ``check`` and ``resolve`` print one line per item and a summary line; ``map``
and ``laminate`` print the document as JSON on stdout (or write it with ``-o``) and the
summary on stderr. No commons runs any of this as a gate yet.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["add_sheet_parser", "run"]


def add_sheet_parser(sub, prog: str) -> None:
    p = sub.add_parser("sheet", help="the sheet-behaviour contract (cross-commons): check, "
                                     "map, resolve, laminate")
    ssub = p.add_subparsers(dest="sheet_cmd", required=True)

    c = ssub.add_parser("check", help="validate sheet_behaviour documents (or cards that "
                                      "carry one)")
    c.add_argument("files", nargs="+")

    m = ssub.add_parser("map", help="map a platform card to sheet_behaviour")
    m.add_argument("platform", choices=["pliego", "fashion-cabinet", "yantra4d"])
    m.add_argument("card", help="the card (pliego, fashion-cabinet) or a thin-print "
                                "descriptor (yantra4d)")
    m.add_argument("--materials", action="append", metavar="PLATFORM=DIR",
                   help="materials directory to resolve a descriptor's card against")
    m.add_argument("-o", "--out", help="write the document here instead of stdout")

    r = ssub.add_parser("resolve", help="resolve material_ref(s), name-level")
    r.add_argument("refs", nargs="+", help="a JSON ref, or a file with a ref or a list")
    r.add_argument("--materials", action="append", metavar="PLATFORM=DIR", required=True)

    lam = ssub.add_parser("laminate", help="classical laminate of a layer stack")
    lam.add_argument("file")
    lam.add_argument("--materials", action="append", metavar="PLATFORM=DIR")
    lam.add_argument("-o", "--out", help="write the document here instead of stdout")

    p.set_defaults(func=lambda args: run(args, prog))


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(doc: dict, out: str | None) -> None:
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def run(args, prog: str) -> int:
    try:
        return {"check": _check, "map": _map, "resolve": _resolve,
                "laminate": _laminate}[args.sheet_cmd](args, prog)
    except (OSError, ValueError) as exc:
        print(f"  ERROR {exc}", file=sys.stderr)
        return 2


def _check(args, prog: str) -> int:
    from .behaviour import validate

    failures = notes = 0
    for f in args.files:
        doc = _read_json(f)
        if isinstance(doc, dict) and isinstance(doc.get("sheet_behaviour"), dict):
            doc = doc["sheet_behaviour"]   # a card that carries the block
        check = validate(doc)
        for e in check.errors:
            print(f"  FAIL {f}: {e}")
        for n in check.notes:
            print(f"  note {f}: {n}")
        if check.ok:
            print(f"  ok {f}")
        failures += not check.ok
        notes += len(check.notes)
    print(f"{prog} sheet check: files={len(args.files)} failures={failures} notes={notes}")
    return 1 if failures else 0


def _map(args, prog: str) -> int:
    from .behaviour import validate
    from .mapping import map_fc_fabric, map_pliego_stock
    from .resolve import CARD_FILES, parse_materials_args
    from .stack import thin_print

    data = _read_json(args.card)
    if args.platform == "pliego":
        doc = map_pliego_stock(data)
    elif args.platform == "fashion-cabinet":
        doc = map_fc_fabric(data)
    else:
        materials = parse_materials_args(args.materials)
        ref = data.get("material_ref") or {}
        root = materials.get("yantra4d")
        if root is None:
            raise ValueError("a thin-print descriptor needs --materials yantra4d=DIR")
        card_path = root / str(ref.get("material_slug")) / CARD_FILES["yantra4d"][0]
        doc = thin_print(data, _read_json(str(card_path)))
    check = validate(doc)
    _emit(doc, args.out)
    print(f"{prog} sheet map: platform={args.platform} rule={doc['source']['rule']} "
          f"valid={'yes' if check.ok else 'NO'} notes={len(check.notes)}", file=sys.stderr)
    return 0 if check.ok else 1


def _refs(items: list[str]) -> list[Any]:
    out: list[Any] = []
    for item in items:
        text = item.strip()
        data = json.loads(text) if text.startswith(("{", "[")) else _read_json(item)
        out.extend(data if isinstance(data, list) else [data])
    return out


def _resolve(args, prog: str) -> int:
    from .resolve import parse_materials_args, resolve_material_ref

    materials = parse_materials_args(args.materials)
    counts: dict[str, int] = {"carries": 0, "maps": 0, "needs-descriptor": 0,
                              "unresolved": 0}
    refs = _refs(args.refs)
    for ref in refs:
        res = resolve_material_ref(ref, materials)
        name = (f"{ref.get('platform')}/{ref.get('material_slug')}"
                if isinstance(ref, dict) else repr(ref))
        counts[res.status] += 1
        for p in res.problems:
            print(f"  FAIL {name}: {p}")
        for n in res.notes:
            print(f"  note {name}: {n}")
        if res.ok:
            print(f"  ok {name} ({res.status})")
    summary = " ".join(f"{k}={v}" for k, v in counts.items())
    print(f"{prog} sheet resolve: refs={len(refs)} {summary}")
    return 1 if counts["unresolved"] else 0


def _laminate(args, prog: str) -> int:
    from .behaviour import validate
    from .resolve import parse_materials_args, resolver_for
    from .stack import laminate_behaviour

    doc_in = _read_json(args.file)
    materials = parse_materials_args(args.materials)
    doc = laminate_behaviour(doc_in, resolver_for(materials) if materials else None)
    check = validate(doc)
    _emit(doc, args.out)
    block = doc["laminate"]
    curl = ""
    if "prestrain_response" in block:
        k = block["prestrain_response"]["curvature_1_m"]
        curl = f" curvature_1_m=[{k[0]:.4g}, {k[1]:.4g}, {k[2]:.4g}]"
    print(f"{prog} sheet laminate: layers={len(block['layers'])} thickness_mm="
          f"{doc['caliper_mm']:.6g} coupled={'yes' if block['coupled'] else 'no'} "
          f"coupling_ratio={block['coupling_ratio']:.3g}{curl} "
          f"valid={'yes' if check.ok else 'NO'}", file=sys.stderr)
    return 0 if check.ok else 1
