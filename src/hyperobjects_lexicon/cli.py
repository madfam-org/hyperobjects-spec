"""The `lexicon` subcommand, shared by both CLIs.

Exposed on ``fc-spec`` and ``y4d-spec`` alike, the same way ``identity`` is: a
contributor on either side of the commons checks the shared vocabulary with the tool
they already have installed. The command body lives here so the two cannot drift.
"""

from __future__ import annotations

from .lexicon import (
    bundled_catalog_slugs,
    check_lexicon,
    lexicon_status,
    load_catalog_slugs,
    load_lexicon,
)

#: `--catalog bundled` resolves against the vendored snapshot instead of a path.
BUNDLED = "bundled"

__all__ = ["add_lexicon_parser", "run_lexicon"]


def add_lexicon_parser(sub, prog: str) -> None:
    """Register the `lexicon` subcommand on an argparse subparsers object."""
    p = sub.add_parser(
        "lexicon",
        help="check the Commons Lexicon (RFC 0039) — schema, four languages, cross-refs",
    )
    p.add_argument(
        "--terms",
        metavar="DIR",
        help="a directory of term JSON files to check instead of the bundled corpus",
    )
    p.add_argument(
        "--catalog",
        metavar="CATALOG",
        action="append",
        help="a commons catalog to resolve embodied_by slugs against (repeatable, so "
        "both commons can be supplied). Pass the literal 'bundled' to use the vendored "
        "snapshot of both commons, which needs no checkout and no network — that is "
        "what CI runs. Without any --catalog, slugs are NOT resolved and the summary "
        "says so.",
    )
    p.add_argument(
        "--status",
        action="store_true",
        help="print only the lexicon_status N/M line",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="list every term")
    p.set_defaults(func=lambda args: run_lexicon(args, prog))


def run_lexicon(args, prog: str) -> int:
    """Run the lexicon lane. 0 conformant · 1 a problem · 2 usage/read error."""
    try:
        lexicon = load_lexicon(args.terms)
    except (OSError, ValueError) as exc:
        print(f"  ERROR cannot read the lexicon — {exc}")
        return 2

    if not lexicon:
        # Read-proof: an empty corpus passes every check vacuously, so it is an error
        # rather than a green run with nothing in it.
        print("  ERROR terms=0 — an empty lexicon is not a passing lexicon")
        return 2

    if args.status:
        print(lexicon_status(lexicon))
        return 0

    catalog: set[str] | None = None
    if args.catalog:
        catalog = set()
        for path in args.catalog:
            try:
                catalog |= (
                    bundled_catalog_slugs() if path == BUNDLED else load_catalog_slugs(path)
                )
            except (OSError, ValueError) as exc:
                print(f"  ERROR {path}: cannot read catalog — {exc}")
                return 2

    result = check_lexicon(lexicon, catalog=catalog)

    if args.verbose:
        for term_id in sorted(lexicon):
            doc = lexicon[term_id]
            domain = doc.get("domain", "?") if isinstance(doc, dict) else "?"
            print(f"  ok {term_id} ({domain})")

    for prob in result.problems:
        print(f"  FAIL {prob}")

    slugs = (
        "resolved"
        if result.catalog_checked
        else f"NOT resolved ({result.unresolved_slugs} refs; pass --catalog)"
    )
    print(
        f"{prog} lexicon: terms={result.terms} failures={len(result.problems)} "
        f"embodied_by={slugs}"
    )
    print(lexicon_status(lexicon))
    return 1 if result.problems else 0
