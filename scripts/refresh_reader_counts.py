#!/usr/bin/env python3
"""Rewrite every count this repo's docs state, from the data they claim to describe.

`refresh_vocabulary_counts.py` exists because a vocabulary's counts go stale the day a
wave lands. The same is true one layer up: the README quotes lane transcripts, the
adoption checklist quotes corpus totals, and the cross-commons reader publishes a
summary — and all three are counts a human typed once. This script is where they come
from instead.

    python3 scripts/refresh_reader_counts.py           # rewrite
    python3 scripts/refresh_reader_counts.py --check    # report drift, change nothing

It needs no platform checkout and no network: every number comes from what is bundled
with the package — the term corpus, the two controlled vocabularies, and the pinned
catalog and bridge snapshots the reader is built from.

Each block it owns is delimited in the Markdown:

    <!-- counts:<name>:start -->
    …generated…
    <!-- counts:<name>:end -->

Everything outside the markers is editorial and is never touched. A block that drifts
is not a formatting nit: it is a document making a claim about the corpus that the
corpus no longer supports, which is exactly the failure the vocabularies' `observed`
blocks are refreshed to prevent.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hyperobjects_lexicon import (  # noqa: E402
    bundled_catalog_slugs,
    check_lexicon,
    check_vocabularies,
    lexicon_status,
    load_lexicon,
    load_vocabularies,
    vocabulary_status,
)
from hyperobjects_lexicon.lexicon import LANGUAGES  # noqa: E402
from hyperobjects_lexicon.reader import (  # noqa: E402
    REPOS,
    load_model,
    reader_counts,
    reader_status,
)

ROOT = Path(__file__).resolve().parent.parent

#: Which files carry which blocks. A file may carry several; a block may appear in
#: several files and is emitted identically in each.
DOCUMENTS = {
    "README.md": ("lexicon-status", "vocabulary-status", "reader"),
    "docs/COMMONS_VOCABULARY.md": ("reader",),
}

MARKER = "<!-- counts:{name}:{edge} -->"


def _lexicon_block() -> str:
    lexicon = load_lexicon()
    result = check_lexicon(lexicon, catalog=bundled_catalog_slugs())
    return (
        "```\n"
        "$ y4d-spec lexicon --catalog bundled\n"
        f"y4d-spec lexicon: terms={result.terms} failures={len(result.problems)} "
        "embodied_by=resolved\n"
        f"{lexicon_status(lexicon)}\n"
        "```"
    )


def _vocabulary_block() -> str:
    docs = load_vocabularies()
    result = check_vocabularies(docs)
    lines = "\n".join(vocabulary_status(docs))
    return (
        "```\n"
        "$ fc-spec vocab\n"
        f"fc-spec vocab: vocabularies={result.vocabularies} entries={result.entries} "
        f"failures={len(result.problems)}\n"
        f"{lines}\n"
        "```"
    )


def _reader_block() -> str:
    model = load_model()
    counts = reader_counts(model)
    bridges = counts["bridges"]

    rows = [
        "| Layer | Pages | Languages present (es/en/fr/pt) |",
        "|---|--:|---|",
        "| terms | {n} | {langs} |".format(
            n=counts["terms"]["total"],
            langs=" / ".join(str(counts["terms"]["languages"][lang]) for lang in LANGUAGES),
        ),
    ]
    for repo in REPOS:
        entry = counts["catalog"][repo]
        rows.append(
            "| {repo} | {n} | {langs} |".format(
                repo=repo,
                n=entry["entries"],
                langs=" / ".join(str(entry["languages"][lang]) for lang in LANGUAGES),
            )
        )
    entry_pages = sum(counts["catalog"][repo]["entries"] for repo in REPOS)
    chrome_pages = counts["pages"] - counts["terms"]["total"] - entry_pages
    rows.append(f"| index, bridge and catalog index pages | {chrome_pages} | — |")

    bridge_rows = [
        "",
        "| Bridge | Count |",
        "|---|--:|",
        f"| declared edges (garment → hardware) | {bridges['edges']} |",
        f"| resolving to a page on both ends | {bridges['resolved']} |",
        f"| unresolved (reported, never fatal) | {bridges['unresolved']} |",
        f"| linked | {bridges['linked']} |",
        f"| claimed but not linked | {bridges['unlinked']} |",
        f"| published back edges (hardware → garments) | {bridges['back_edges']} |",
        f"| agreeing in both directions | {bridges['mirrored']} |",
        "",
        "```",
        "$ fc-spec reader --check",
        f"fc-spec reader --check: out=docs/reader pages={counts['pages']} differences=0",
        reader_status(model),
        "```",
    ]
    return "\n".join(rows + bridge_rows)


BLOCKS = {
    "lexicon-status": _lexicon_block,
    "vocabulary-status": _vocabulary_block,
    "reader": _reader_block,
}


def _replace(text: str, name: str, body: str) -> tuple[str, bool]:
    """Swap one delimited block's body. Raises when the markers are missing, because a
    doc that lost its markers would otherwise refresh to a silent no-op."""
    start = MARKER.format(name=name, edge="start")
    end = MARKER.format(name=name, edge="end")
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        raise ValueError(f"no {name!r} block — expected {start} … {end}")
    replacement = f"{start}\n{body}\n{end}"
    new = pattern.sub(lambda _: replacement, text, count=1)
    return new, new != text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="report drift and change nothing (what CI runs)",
    )
    args = ap.parse_args(argv)

    bodies = {name: emit() for name, emit in BLOCKS.items()}
    drifted: list[str] = []

    for relative, names in sorted(DOCUMENTS.items()):
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot read {relative} — {exc}", file=sys.stderr)
            return 2
        updated = text
        for name in names:
            try:
                updated, changed = _replace(updated, name, bodies[name])
            except ValueError as exc:
                print(f"ERROR: {relative}: {exc}", file=sys.stderr)
                return 2
            if changed:
                drifted.append(f"{relative}: {name}")
        if updated != text and not args.check:
            path.write_text(updated, encoding="utf-8")

    for line in drifted:
        print(f"  drift {line}")
    print(
        f"reader counts: blocks={sum(len(v) for v in DOCUMENTS.values())} "
        f"drifted={len(drifted)} "
        f"{'(checked, not written)' if args.check else '(written)'}"
    )
    if drifted and args.check:
        print(
            "A count in the docs no longer matches the corpus it describes. Run "
            "`python3 scripts/refresh_reader_counts.py` and commit the result."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
