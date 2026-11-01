"""``ho-reference`` — check the reference-objects catalog, print its status, or a digest.

    ho-reference check  [--objects DIR] [-v] [--json]
    ho-reference status [--objects DIR]
    ho-reference digest --family SLUG [--objects DIR]

``check`` exits 1 when any object has a problem. ``digest`` prints the sha256 a commons
preset generator records in a manifest's ``_generated_from`` for one family.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import family_digest, load_catalog, load_family
from .check import catalog_status, check_catalog


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ho-reference", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("check", "status", "digest"):
        s = sub.add_parser(name)
        s.add_argument("--objects", metavar="DIR",
                       help="a directory of objects (default: the bundled catalog)")
        if name == "check":
            s.add_argument("-v", "--verbose", action="store_true")
            s.add_argument("--json", action="store_true")
        if name == "digest":
            s.add_argument("--family", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
                          "failures": len(result.problems), "problems": result.problems},
                         indent=2))
    else:
        for problem in result.problems:
            print(f"FAIL {problem}")
        if args.verbose:
            print("\n".join(catalog_status(catalog)))
        print(f"ho-reference check: objects={result.objects} values={result.values} "
              f"failures={len(result.problems)}")
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
