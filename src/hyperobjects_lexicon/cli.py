"""The lexicon subcommands, shared by both CLIs.

Exposed on ``fc-spec`` and ``y4d-spec`` alike, the same way ``identity`` is: a
contributor on either side of the commons checks the shared vocabulary with the tool
they already have installed. The command bodies live here so the two cannot drift.

    <tool> lexicon [--catalog bundled] [--terms DIR] [--status] [-v]
    <tool> vocab [--vocabularies DIR] [--status] [-v]
    <tool> define <word> [--lang es|en|fr|pt]
    <tool> lookup <repo/slug>
    <tool> related <term-id>

The last three are the RFC 0039 §6.2 dictionary tools on a command line. They are the
same functions both platforms' MCP servers call, which is the point: a definition must
not depend on which half of the commons you asked, or on whether you asked a server or a
shell.
"""

from __future__ import annotations

import json

from .dictionary import define, lookup, related
from .lexicon import (
    LANGUAGES,
    bundled_catalog_slugs,
    check_lexicon,
    lexicon_status,
    load_catalog_slugs,
    load_lexicon,
)
from .vocabulary import (
    check_vocabularies,
    equivalences,
    load_vocabularies,
    vocabulary_status,
)

#: `--catalog bundled` resolves against the vendored snapshot instead of a path.
BUNDLED = "bundled"

__all__ = [
    "add_lexicon_parser",
    "add_vocabulary_parser",
    "add_dictionary_parsers",
    "LEXICON_COMMANDS",
    "run_lexicon",
    "run_vocabulary",
]

#: Every subcommand this module registers, so a host CLI can dispatch them as a group.
LEXICON_COMMANDS: tuple[str, ...] = ("lexicon", "vocab", "define", "lookup", "related")


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


def add_vocabulary_parser(sub, prog: str) -> None:
    """Register the `vocab` subcommand — the controlled vocabularies (RFC 0039 G3)."""
    p = sub.add_parser(
        "vocab",
        help="check the controlled vocabularies — interface names and capability keys",
    )
    p.add_argument(
        "--vocabularies",
        metavar="DIR",
        help="a directory of vocabulary JSON files to check instead of the bundled ones",
    )
    p.add_argument(
        "--status", action="store_true", help="print only the vocabulary_status lines"
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="also list every cross-commons equivalence and every canonicalised alias",
    )
    p.set_defaults(func=lambda args: run_vocabulary(args, prog))


def run_vocabulary(args, prog: str) -> int:
    """Run the vocabulary lane. 0 conformant · 1 a problem · 2 usage/read error."""
    try:
        docs = load_vocabularies(args.vocabularies)
    except (OSError, ValueError) as exc:
        print(f"  ERROR cannot read the vocabularies — {exc}")
        return 2

    if not docs:
        print("  ERROR vocabularies=0 — an empty vocabulary set is not a passing one")
        return 2

    if args.status:
        for line in vocabulary_status(docs):
            print(line)
        return 0

    result = check_vocabularies(docs)

    if args.verbose:
        for a, b in equivalences(docs):
            print(f"  equivalent {a} == {b}")
        for name in sorted(docs):
            for entry in docs[name].get("entries") or []:
                for alias in entry.get("aliases") or []:
                    print(
                        f"  alias {alias.get('repo')}/{alias.get('name')} -> "
                        f"{entry.get('repo')}/{entry.get('key')}"
                    )

    for prob in result.problems:
        print(f"  FAIL {prob}")

    print(
        f"{prog} vocab: vocabularies={result.vocabularies} entries={result.entries} "
        f"failures={len(result.problems)}"
    )
    for line in vocabulary_status(docs):
        print(line)
    return 1 if result.problems else 0


def add_dictionary_parsers(sub, prog: str) -> None:
    """Register `define`, `lookup` and `related` — RFC 0039 §6.2 on a command line."""
    p_def = sub.add_parser(
        "define", help="define a term, an alias, or a manifest key, in any of the four languages"
    )
    p_def.add_argument("word", help="a term id, a headword, a repo spelling, or a vocabulary key")
    p_def.add_argument(
        "--lang", choices=list(LANGUAGES), help="answer in one language instead of all four"
    )
    p_def.add_argument("--json", action="store_true", help="print the raw record")
    p_def.set_defaults(func=lambda args: _run_define(args, prog))

    p_look = sub.add_parser("lookup", help="every term a cartridge or material card embodies")
    p_look.add_argument("object", help="'<repo>/<slug>', or a bare slug to search both commons")
    p_look.add_argument("--json", action="store_true", help="print the raw record")
    p_look.set_defaults(func=lambda args: _run_lookup(args, prog))

    p_rel = sub.add_parser("related", help="what a term points at, and what points back at it")
    p_rel.add_argument("term", help="a term id")
    p_rel.add_argument("--json", action="store_true", help="print the raw record")
    p_rel.set_defaults(func=lambda args: _run_related(args, prog))


def _dump(record) -> int:
    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0


def _run_define(args, prog: str) -> int:
    record = define(args.word, args.lang)
    if record is None:
        print(f"  no entry for {args.word!r} — try `{prog} lexicon -v` for the corpus")
        return 1
    if args.json:
        return _dump(record)

    langs = [args.lang] if args.lang else list(LANGUAGES)
    print(f"{record['id']} ({record['domain']}) — review: {record['review']}")
    print(f"  matched by {record['matched']['route']}")
    for lang in langs:
        term = record["term"] if args.lang else record["term"][lang]
        definition = record["definition"] if args.lang else record["definition"][lang]
        print(f"  [{lang}] {term}")
        print(f"        {definition}")
    if record.get("constraints"):
        print(f"  constraint: {record['constraints']}")
    return 0


def _run_lookup(args, prog: str) -> int:
    record = lookup(args.object)
    if args.json:
        return _dump(record)
    for term in record["terms"]:
        print(f"  {term['id']} ({term['domain']}) — {term['term']['en']}")
    # Read-proof: zero terms for an object is a real answer and must not look like an
    # error, but it must also not look like a checked object with nothing to say.
    print(
        f"{prog} lookup: object={record['object']} "
        f"repos={','.join(record['repos']) or 'none'} terms={record['count']}"
    )
    return 0


def _run_related(args, prog: str) -> int:
    record = related(args.term)
    if record is None:
        print(f"  no term {args.term!r} in the lexicon")
        return 1
    if args.json:
        return _dump(record)
    print(f"{record['id']} ({record['domain']})")
    print(f"  see_also: {', '.join(record['see_also']) or 'none'}")
    print(f"  referenced_by: {', '.join(record['referenced_by']) or 'none'}")
    for key in record["vocabulary_keys"]:
        aliases = f" (aliases: {', '.join(key['aliases'])})" if key["aliases"] else ""
        print(f"  key: {key['repo']}/{key['key']} [{key['role']}]{aliases}")
    print(f"  embodied_by: {len(record['embodied_by'])} object(s)")
    return 0
