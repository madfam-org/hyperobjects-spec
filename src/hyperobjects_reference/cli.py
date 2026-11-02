"""``ho-reference`` — check the reference-objects catalog, print its status, a digest, or a fit.

    ho-reference check  [--objects DIR] [-v] [--json]
    ho-reference status [--objects DIR]
    ho-reference digest --family SLUG [--objects DIR]
    ho-reference fit    --container KEY --content KEY [--clearance-mm X] [--objects DIR] [--json]

``check`` exits 1 when any object has a problem; a ``note`` (an edition key the catalog does
not hold yet) never fails it. ``digest`` prints the sha256 a commons preset generator records
in a manifest's ``_generated_from`` for one family. ``fit`` (gate G-X2) exits 0 when the
container's inside holds the content's envelope plus the clearance per side, 1 when it does
not, 3 when a null input leaves it unknown (never a pass), and 2 for a key the catalog does
not hold or a negative clearance.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import family_digest, load_catalog, load_family
from .check import catalog_status, check_catalog
from .fit import DOES_NOT_FIT, FITS, fit

#: ``fit`` exit codes by verdict; 2 is a usage error (argparse's own, and a missing key).
FIT_EXIT = {FITS: 0, DOES_NOT_FIT: 1}
FIT_EXIT_UNKNOWN = 3


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ho-reference", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("check", "status", "digest", "fit"):
        s = sub.add_parser(name)
        s.add_argument("--objects", metavar="DIR",
                       help="a directory of objects (default: the bundled catalog)")
        if name == "check":
            s.add_argument("-v", "--verbose", action="store_true")
            s.add_argument("--json", action="store_true")
        if name == "digest":
            s.add_argument("--family", required=True)
        if name == "fit":
            s.add_argument("--container", required=True, metavar="KEY")
            s.add_argument("--content", required=True, metavar="KEY")
            s.add_argument("--clearance-mm", type=float, default=0.0, metavar="X",
                           help="clearance per side, on every axis (default 0)")
            s.add_argument("--json", action="store_true")
    return p


def _mm(value: float | None) -> str:
    return "null" if value is None else f"{value:g}"


def _fit(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.objects)
    for role, key in (("container", args.container), ("content", args.content)):
        if key not in catalog:
            print(f"ho-reference fit: {role} {key!r} is not in the catalog", file=sys.stderr)
            return 2
    try:
        result = fit(catalog[args.container], catalog[args.content], args.clearance_mm)
    except ValueError as exc:
        print(f"ho-reference fit: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        print(f"ho-reference fit: container={result.container} content={result.content} "
              f"envelope={result.content_state or '-'} clearance={result.clearance_mm:g}mm/side")
        for a in result.axes:
            state = {True: "ok", False: "SHORT", None: "unknown"}[a.fits]
            print(f"  {a.axis:<6} inside={_mm(a.inside_mm)} ({a.inside_from or 'no input'}) "
                  f"required={_mm(a.required_mm)} margin={_mm(a.margin_mm)} {state}")
        for path in result.unknown:
            print(f"  null {path}")
        print(f"ho-reference fit: {result.verdict}")
    return FIT_EXIT.get(result.verdict, FIT_EXIT_UNKNOWN)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "fit":
        return _fit(args)
    if args.command == "digest":
        objects = load_family(args.family, args.objects)
        if not objects:
            print(f"ho-reference digest: no object has family {args.family!r}", file=sys.stderr)
            return 1
        print(f"{family_digest(args.family, args.objects)}  family={args.family} "
              f"objects={len(objects)}")
        return 0
    catalog = load_catalog(args.objects)
    if args.command == "status":
        print("\n".join(catalog_status(catalog)))
        return 0
    result = check_catalog(catalog)
    if args.json:
        print(json.dumps({"objects": result.objects, "values": result.values,
                          "failures": len(result.problems), "notes": len(result.notes),
                          "problems": result.problems, "note_lines": result.notes},
                         indent=2))
    else:
        for problem in result.problems:
            print(f"FAIL {problem}")
        for note in result.notes:
            print(f"note {note}")
        if args.verbose:
            print("\n".join(catalog_status(catalog)))
        print(f"ho-reference check: objects={result.objects} values={result.values} "
              f"failures={len(result.problems)} notes={len(result.notes)}")
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
