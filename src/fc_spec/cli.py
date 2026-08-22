"""fc-spec command-line interface.

    fc-spec list
    fc-spec check <contract> <file> [<file> ...] [--resolve catalog.json]
    fc-spec identity <pair.json> [<pair.json> ...]

Exit code 0 iff every file conforms; 1 on any conformance problem; 2 on usage /
read errors. Output is read-proof: it prints how many files it checked, and
checking zero files is a usage error.

`identity` checks a cross-commons identity pair record (RFC 0038 §9) — the same
check `y4d-spec identity` runs, exposed on both tools so a contributor on either
side of the commons can validate a pair with what they already have installed.
`list` and `check` are unchanged: they are a published contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .conformance import CONTRACTS, check, list_contracts


def _load_json(path: str) -> dict:
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def _resolve_map(path: str | None) -> dict[str, list[str]]:
    """Load a hardware-ref resolution surface: slug -> parameter ids. Accepts

      * yantra4d's commons-catalog.json — {"cartridges": [{slug, parameter_ids}, ...]}
      * the FC vendored snapshot — {"cartridges": {slug: {parameter_ids}, ...}}
      * a plain {slug: {"parameter_ids": [...]}} or {slug: [param, ...]} map
    """
    if not path:
        return {}
    data = _load_json(path)
    carts = data.get("cartridges", data) if isinstance(data, dict) else data

    if isinstance(carts, list):
        return {c["slug"]: c.get("parameter_ids", [])
                for c in carts if isinstance(c, dict) and c.get("slug")}
    if isinstance(carts, dict):
        out: dict[str, list[str]] = {}
        for slug, entry in carts.items():
            if isinstance(entry, dict):
                out[slug] = entry.get("parameter_ids", [])
            elif isinstance(entry, list):
                out[slug] = entry
        return out
    return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fc-spec", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list the checkable contracts")

    p_check = sub.add_parser("check", help="check file(s) against a contract")
    p_check.add_argument("contract", choices=list(CONTRACTS))
    p_check.add_argument("files", nargs="+", help="JSON file(s) to check")
    p_check.add_argument(
        "--resolve", metavar="CATALOG",
        help="hardware-ref: a yantra4d commons-catalog.json (or {slug:[params]} map) "
             "to resolve linked slugs against",
    )

    p_id = sub.add_parser("identity", help="check a cross-commons identity pair file")
    p_id.add_argument("files", nargs="+", help="pair record JSON file(s)")

    args = parser.parse_args(argv)

    if args.cmd == "list":
        for name in list_contracts():
            print(name)
        return 0

    if args.cmd == "identity":
        from hyperobjects_schemas.identity import check_identity_file

        failures = 0
        for f in args.files:
            try:
                result = check_identity_file(f)
            except (OSError, ValueError) as exc:
                print(f"  ERROR {f}: cannot read — {exc}")
                failures += 1
                continue
            if result.ok:
                print(f"  ok {f} (identity '{result.identity_id or 'multiple'}')")
            else:
                failures += 1
                for prob in result.problems:
                    print(f"  FAIL {f}: {prob}")
        print(f"fc-spec identity: files={len(args.files)} failures={failures}")
        return 1 if failures else 0

    resolve = _resolve_map(args.resolve)
    failures = 0
    for f in args.files:
        try:
            doc = _load_json(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ERROR {f}: cannot read — {exc}")
            failures += 1
            continue
        result = check(args.contract, doc, resolve=resolve)
        if result.ok:
            print(f"  ok {f} ({args.contract})")
        else:
            failures += 1
            for prob in result.problems:
                print(f"  FAIL {f}: {prob}")

    print(f"fc-spec check: contract={args.contract} files={len(args.files)} failures={failures}")
    if not args.files:  # argparse nargs='+' prevents this, but stay read-proof
        print("  ERROR checked=0 files")
        return 2
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
