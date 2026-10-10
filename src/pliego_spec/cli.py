"""pliego-spec command-line interface — the sheet commons' conformance runner.

    pliego-spec list
    pliego-spec check sheet-manifest <project.json> [...]
    pliego-spec check sheet-document <document.fold|.json> [...]
    pliego-spec check cartridge <cartridge-dir> [...]
    pliego-spec rules
    pliego-spec lexicon [--catalog CATALOG] [--status] [-v] · vocab · article <path>
    pliego-spec define <word> [--lang es|en|fr|pt] · lookup <repo/slug> · related <term-id>

Exit code 0 iff everything checked conforms; 1 on any FAIL; 2 on usage or read
errors. A `note` never fails. Output is read-proof: every run prints how much it
checked and what it did NOT verify — `geometry=NOT verified` means no sheet geometry
(face simplicity and tiling, sheet overlap, developability) was judged, and
`documents=NOT built` means a cartridge's scripts were not run.

The shared lexicon, vocabulary, article and dictionary subcommands are the same ones
`fc-spec` and `y4d-spec` mount: the vocabulary belongs to no single commons.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hyperobjects_lexicon.cli import (
    add_article_parser,
    add_dictionary_parsers,
    add_lexicon_parser,
    add_vocabulary_parser,
    run_lexicon,
)

from . import __version__
from .conformance import (
    CONTRACTS,
    UNVERIFIED_DOCUMENT_RULES,
    check,
    check_cartridge,
    list_contracts,
)
from .rules import LANGUAGES, SHEET_COMMONS_LICENSE

PROG = "pliego-spec"
TARGETS = (*CONTRACTS, "cartridge")

RULES_TEXT = f"""\
pliego-spec {__version__} — what `check` verifies, in order

sheet-manifest (schema: hyperobjects_schemas sheet-manifest)
  1. schema — JSON Schema 2020-12; closed objects; every text object born quadrilingual
  2. slugs — project.slug, sheet ids and stock slugs are strict kebab case
  3. licence — project.attribution.license and hyperobject.commons_license both equal
     {SHEET_COMMONS_LICENSE} (owner ruling 2026-10-10) and agree
  4. i18n — {', '.join(LANGUAGES)} present and non-blank on every user-visible text
  5. references — modes→sheets, parameters→modes/groups, presets→mode/parameters,
     interfaces→parameters/sheet edges/frame sheet; no duplicate ids; slider and select
     defaults inside their range/options
  6. heritage — a heritage claim cites at least one source (RFC 0039 §7)
  7. hardware_ref — the local half: params_map expressions parse and read only declared
     parameters (the yantra4d side is not resolved)
  8. constraints — the safeFormula dialect: no function calls, no strings, numeric
     parameters only, <=256 characters / 128 tokens
  9. controls — min <= default <= max; a toggle's default is a boolean
 10. fabrication vocabulary — an interface size_key is an interface-sizes key (SEM-1 §4)

cartridge <dir> (all of sheet-manifest, plus)
 11. a directory without project.json is a FAIL, never a skip
 12. the triple project.json / main.py / docs/README.md, each non-empty
 13. the directory name equals project.slug
 14. every mode's script_file exists and stays inside the cartridge
 15. no LICENSE/COPYING file at any depth; no vendor/ tree
 16. scripts import only pliego and math (the runner's two modules)
 17. G-DEADPARAM — every parameter is read by a script of a mode that lists it
     (y4d_spec's rule, unchanged), or carries intentionally_unused with a reason
  note: documents=NOT built — scripts are not run (no published Pliego kernel)

sheet-document (schema: Pliego's, vendored and sha-256-locked)
 18. schema — FOLD 1.2 + pliego: extensions
 19. spec §8.1 lengths and index ranges; §8.2 sheet membership; §8.4 treatment and
     fold-angle pairs; §8.6 stock keys; §8.7 references and unique ids; §8.8 sequence
     targets; §8.9 one 3-D coordinate per vertex; §8.10 the GOC-1 canonical digest
  NOT verified (geometry=NOT verified): §{', §'.join(UNVERIFIED_DOCUMENT_RULES)}
"""


def _load_json(path: str) -> object:
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def _run_contract(contract: str, files: list[str]) -> int:
    failures = 0
    totals = {"sheets": 0, "vertices": 0, "edges": 0, "faces": 0, "joins": 0}
    for f in files:
        try:
            doc = _load_json(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"  ERROR {f}: cannot read — {exc}")
            failures += 1
            continue
        result = check(contract, doc)
        for key in totals:
            totals[key] += result.counts.get(key, 0)
        if result.ok:
            print(f"  ok {f} ({contract})")
        else:
            failures += 1
            for prob in result.problems:
                print(f"  FAIL {f}: {prob}")
    line = f"{PROG} check: contract={contract} files={len(files)} failures={failures}"
    if contract == "sheet-document":
        line += " " + " ".join(f"{k}={v}" for k, v in totals.items())
        line += " geometry=NOT verified"
    print(line)
    return 1 if failures else 0


def _run_cartridges(dirs: list[str], verbose: bool) -> int:
    failures = notes = 0
    for d in dirs:
        result = check_cartridge(d)
        notes += len(result.notes)
        if result.ok:
            print(f"  ok {d} ({result.slug})")
        else:
            failures += 1
            for prob in result.problems:
                print(f"  FAIL {d}: {prob}")
        if verbose or not result.ok:
            for note in result.notes:
                print(f"  note {d}: {note}")
    print(
        f"{PROG} check: cartridges={len(dirs)} failures={failures} notes={notes} "
        f"documents=NOT built geometry=NOT verified"
    )
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=PROG, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list the checkable contracts")
    p_check = sub.add_parser("check", help="check files against a contract, or cartridges")
    p_check.add_argument("target", choices=TARGETS)
    p_check.add_argument("paths", nargs="+", help="JSON file(s), or cartridge director(ies)")
    p_check.add_argument("-v", "--verbose", action="store_true",
                         help="cartridge: print notes for passing cartridges too")
    sub.add_parser("rules", help="print every check, in order, and what is NOT verified")

    add_lexicon_parser(sub, PROG)
    add_vocabulary_parser(sub, PROG)
    add_article_parser(sub, PROG)
    add_dictionary_parsers(sub, PROG)

    args = parser.parse_args(argv)

    if args.cmd == "lexicon":
        return run_lexicon(args, PROG)
    if args.cmd in ("vocab", "article", "define", "lookup", "related"):
        return args.func(args)
    if args.cmd == "list":
        for name in list_contracts():
            print(f"{name}\t{CONTRACTS[name]['home']}")
        return 0
    if args.cmd == "rules":
        print(RULES_TEXT, end="")
        return 0
    if args.target == "cartridge":
        return _run_cartridges(args.paths, args.verbose)
    return _run_contract(args.target, args.paths)


if __name__ == "__main__":
    sys.exit(main())
