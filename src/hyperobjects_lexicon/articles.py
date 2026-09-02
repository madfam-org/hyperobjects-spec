"""Article frontmatter: the encyclopaedia layer's checkable half (RFC 0039 G2).

G2 in the RFC's road is "article elevation: frontmatter + article view in each catalog
surface; heritage entries as the exemplar set", and it is estimated at one session per
commons. The half that belongs HERE is the frontmatter contract and its lane — the same
move this package was made by: the bar lived inside the repos, and the shared part got
extracted. The article VIEW is each platform's own build, and the articles themselves are
each commons' editorial property (§2, §4). What this module gives both of them is one
definition of what an elevated article must carry, so a term popover, an A-Z page and a
catalog card mean the same thing on either side.

The rules, and the reason each one is a rule
--------------------------------------------
1. **Schema-valid** against ``article-frontmatter.schema.json``.
2. **The object resolves** — only when a catalog is supplied, exactly as ``embodied_by``
   does. Absent one, the count of unresolved references prints rather than passing
   silently.
3. **Citations where §7 demands them** — ``heritage: true`` with no ``sources`` fails.
4. **A heritage article says what it does NOT draw.** The heritage cartridges already
   write this in prose ("No botonadura de plata. No escudo… The competition dress codes
   belong to the Federación Mexicana de Charrería"), and a boundary a platform cannot
   read is a boundary a platform will cross — so ``excludes`` is required alongside the
   citation, and the pair is what "heritage" costs.
5. **``related.terms`` resolve** against the lexicon, when one is supplied. A term
   popover pointing at a term that does not exist is a broken article.
6. **The article path stays inside the repo** — relative, no ``..``, and Markdown. The
   frontmatter is a pointer to the single source, and a pointer that can leave the repo
   is a pointer at something the commons does not publish.

Language coverage is REPORTED, never failed. The lexicon is born quadrilingual because
that is free at authoring time; the catalogs are not, phase G-L is the backfill, and a
lane that failed en/es articles today would simply stop G2 until G-L finished.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from hyperobjects_schemas import load as load_schema

from .lexicon import LANGUAGES, load_lexicon

__all__ = [
    "ArticleResult",
    "article_status",
    "check_article",
    "check_articles",
    "language_coverage",
    "load_article",
]

SCHEMA_NAME = "article-frontmatter"


@dataclass
class ArticleResult:
    """The verdict on a set of articles. Falsey when there are problems."""

    articles: int
    ok: bool
    problems: list[str] = field(default_factory=list)
    unresolved_objects: int = 0
    catalog_checked: bool = False
    heritage: int = 0

    def __bool__(self) -> bool:
        return self.ok


def load_article(path: str | Path) -> dict:
    """Read one frontmatter record. Raises on unreadable JSON."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _schema_errors(doc: object) -> list[str]:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(load_schema(SCHEMA_NAME))
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"{where}: {err.message}")
    return out


def check_article(
    doc: object,
    *,
    known_terms: set[str] | None = None,
    catalog: set[str] | None = None,
) -> list[str]:
    """Check one article's frontmatter. Returns its problems (empty means it conforms)."""
    problems = _schema_errors(doc)
    if not isinstance(doc, dict):
        return problems or ["not an object"]

    path = (doc.get("article") or {}).get("path", "")
    if isinstance(path, str) and path:
        parts = Path(path).parts
        if ".." in parts or path.startswith("/"):
            problems.append(
                f"article.path {path!r} escapes the repository — the frontmatter points "
                f"at the single source, and a path that can leave the repo points at "
                f"something the commons does not publish"
            )

    if doc.get("heritage"):
        if not doc.get("sources"):
            problems.append(
                "heritage is true but sources is empty — a cultural or historical claim "
                "ships with a citation or not at all (RFC 0039 §7)"
            )
        if not doc.get("excludes"):
            problems.append(
                "heritage is true but excludes is empty — a heritage article states what "
                "the cartridge deliberately does NOT draw, because a boundary a platform "
                "cannot read is a boundary a platform will cross"
            )

    if known_terms is not None:
        for term in (doc.get("related") or {}).get("terms") or []:
            if term not in known_terms:
                problems.append(
                    f"related.terms: {term!r} is not a term in the lexicon — an article "
                    f"whose popover resolves to nothing is a broken article"
                )

    if catalog is not None:
        for slug in [doc.get("object")] + list(
            (doc.get("related") or {}).get("objects") or []
        ):
            if isinstance(slug, str) and slug not in catalog:
                problems.append(
                    f"{slug!r} does not resolve against the supplied catalog"
                )

    return problems


def check_articles(
    articles: dict[str, dict],
    *,
    lexicon: dict[str, dict] | None = None,
    catalog: set[str] | None = None,
) -> ArticleResult:
    """Check a set of articles, keyed by whatever names them (a path, usually)."""
    if lexicon is None:
        lexicon = load_lexicon()
    known_terms = set(lexicon)

    problems: list[str] = []
    unresolved = 0
    heritage = 0
    seen_objects: dict[str, str] = {}

    for name in sorted(articles):
        doc = articles[name]
        if isinstance(doc, dict):
            if doc.get("heritage"):
                heritage += 1
            obj = doc.get("object")
            if isinstance(obj, str):
                if obj in seen_objects:
                    problems.append(
                        f"{name}: {obj} already has an article ({seen_objects[obj]}) — "
                        f"one object, one article, or the two will drift"
                    )
                seen_objects[obj] = name
            if catalog is None:
                unresolved += 1 + len((doc.get("related") or {}).get("objects") or [])
        for prob in check_article(doc, known_terms=known_terms, catalog=catalog):
            problems.append(f"{name}: {prob}")

    return ArticleResult(
        articles=len(articles),
        ok=not problems,
        problems=problems,
        unresolved_objects=unresolved,
        catalog_checked=catalog is not None,
        heritage=heritage,
    )


def language_coverage(articles: dict[str, dict]) -> dict[str, int]:
    """How many articles carry a title in each language.

    This is the G-L debt, counted. The lexicon's N/M line counts entries that are
    complete in four languages; an article corpus cannot be measured that way yet, so
    what gets reported is the per-language count, which goes up as the backfill lands.
    """
    counts = dict.fromkeys(LANGUAGES, 0)
    for doc in articles.values():
        title = doc.get("title") if isinstance(doc, dict) else None
        if not isinstance(title, dict):
            continue
        for lang in LANGUAGES:
            value = title.get(lang)
            if isinstance(value, str) and value.strip():
                counts[lang] += 1
    return counts


def article_status(articles: dict[str, dict]) -> str:
    """The house N/M line for the encyclopaedia layer."""
    total = len(articles)
    heritage = sum(1 for d in articles.values() if isinstance(d, dict) and d.get("heritage"))
    cited = sum(
        1
        for d in articles.values()
        if isinstance(d, dict) and d.get("heritage") and d.get("sources") and d.get("excludes")
    )
    coverage = language_coverage(articles)
    langs = " ".join(f"{lang}={coverage[lang]}" for lang in LANGUAGES)
    return (
        f"article_status: {total} article(s) heritage={heritage} "
        f"cited+bounded={cited}/{heritage} titles: {langs}"
    )
