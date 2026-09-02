"""Loading and checking the Commons Lexicon corpus.

Storage: one JSON file per term, ``terms/<id>.json``
---------------------------------------------------
RFC 0039 §3 sketches the schema in YAML, and one-file-per-term is the right grain: a
term is the unit of review, and a single-file corpus makes every PR a conflict against
every other. The *format* is JSON rather than YAML on purpose, and the reason is a
promise this package already made:

    "Manifest conformance only — pure python, runs in under a second."

The base install declares exactly one dependency (``jsonschema``). PyYAML is not in it,
and adding a parser to the base install so a data file can have nicer quotes would tax
every third party who installs this package to check a cartridge — for a corpus this
package itself is the only reader of. Every other data file here is JSON (the schemas,
the fixtures, the identity example), the schema formalizing §3 is a JSON Schema like its
five siblings, and ``json`` is in the standard library. So: JSON files, YAML-shaped
content, no new dependency. The filename IS the id, and the lane enforces that — the
corpus is browsable as a directory listing.

What the lane checks (each failure class has a test)
----------------------------------------------------
1. **Schema-valid** against ``lexicon-term.schema.json``.
2. **Quadrilingual completeness** — en/es/fr/pt present and non-empty in both ``term``
   and ``definition``. The schema requires the keys; this also refuses whitespace, which
   is how a "placeholder for now" entry sneaks past a required-key check.
3. **No dangling ``see_also``** — every cross-reference resolves to a term in the corpus.
4. **Citations where §7 demands them** — a ``heritage: true`` entry with no ``sources``
   fails. Uncited cultural claims are the one thing the commons' doctrine will not ship.
5. **Review claims are honest** — an entry whose ``review_status`` says ``reviewed``
   names at least one reviewer, and never claims review while one of its four language
   facets is still ``generated``. A generated entry ships (quadrilingual completeness is
   the gate, not review) but is counted separately, so a corpus drafted in one pass can
   never read as a corpus that a native speaker has been over.
6. **``embodied_by`` slugs resolve** — but only when a catalog is supplied. Absent one,
   the lane reports the count as unresolved and stays green: this package has no repo to
   look in, exactly as the identity key's existence check does not. CI passes
   ``--catalog`` and gets the strict version; a third party without a catalog checkout
   still gets everything else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from hyperobjects_schemas import load as load_schema

__all__ = [
    "LANGUAGES",
    "REVIEW_STATES",
    "LEXICON_DIR",
    "LexiconResult",
    "check_lexicon",
    "check_term",
    "lexicon_status",
    "review_counts",
    "load_lexicon",
    "load_term_file",
    "load_catalog_slugs",
    "bundled_catalog_slugs",
    "SNAPSHOT_NAME",
]

# The four languages of the commons, ruled 2026-08-25 (RFC 0039 §5). Order is not
# alphabetical: `es` leads because it is the house register and the quality bar.
LANGUAGES: tuple[str, ...] = ("es", "en", "fr", "pt")

#: The review states an entry may declare, worst first. ``unmarked`` is not a declarable
#: value — it is what an entry with no ``review_status`` counts as, and it is deliberately
#: distinct from ``generated``: the G1 corpus predates the block and claims neither.
REVIEW_STATES: tuple[str, ...] = ("generated", "reviewed")

SCHEMA_NAME = "lexicon-term"

#: Where the bundled corpus lives inside the installed package.
LEXICON_DIR = "hyperobjects_lexicon.terms"

#: Where the vendored catalog snapshot lives, and its filename.
CATALOG_DIR = "hyperobjects_lexicon.catalogs"
SNAPSHOT_NAME = "commons-slugs.snapshot.json"


@dataclass
class LexiconResult:
    """The verdict on a corpus (or on one term). Falsey when there are problems.

    ``unresolved_slugs`` is not a problem count — it is how many ``embodied_by``
    references could not be checked because no catalog was supplied. It prints so a
    reader can never mistake an unchecked run for a checked one.
    """

    terms: int
    ok: bool
    problems: list[str] = field(default_factory=list)
    unresolved_slugs: int = 0
    catalog_checked: bool = False

    def __bool__(self) -> bool:
        return self.ok


def _schema_errors(doc: object) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise RuntimeError("jsonschema is required (pip install hyperobjects-spec)") from exc
    validator = Draft202012Validator(load_schema(SCHEMA_NAME))
    problems = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        problems.append(f"{where}: {err.message}")
    return problems


def load_term_file(path: str | Path) -> dict:
    """Read one term file. Raises on unreadable JSON — a corpus with a broken file is
    not a corpus with a missing term."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_lexicon(directory: str | Path | None = None) -> dict[str, dict]:
    """Load a corpus as ``{id: term}``.

    With no argument, loads the corpus bundled with this package. The key is the term's
    declared ``id``; ``check_lexicon`` is what asserts the id matches the filename, so a
    corpus that disagrees with itself still loads (and then fails the lane loudly)
    rather than silently dropping a term.
    """
    if directory is None:
        files = sorted(
            p
            for p in resources.files(LEXICON_DIR).iterdir()
            if p.name.endswith(".json")
        )
        docs = [(p.name, json.loads(p.read_text(encoding="utf-8"))) for p in files]
    else:
        paths = sorted(Path(directory).glob("*.json"))
        docs = [(p.name, load_term_file(p)) for p in paths]

    out: dict[str, dict] = {}
    for name, doc in docs:
        key = doc.get("id") if isinstance(doc, dict) and doc.get("id") else name[: -len(".json")]
        out[key] = doc
    return out


def load_catalog_slugs(path: str | Path) -> set[str]:
    """Read a commons catalog into a set of ``'<repo>/<slug>'`` strings.

    Accepts the shapes a contributor actually has on disk, so nobody has to reshape a
    file to run the lane:

      * Yantra4D's ``docs/commons-catalog.json`` — ``{"cartridges": [{"slug": ...}]}``
      * Fashion Cabinet's vendored snapshot — ``{"cartridges": {slug: {...}}}``
      * an already-qualified list — ``["yantra4d/zipper", "fashion-cabinet/blouse"]``
      * a ``{repo: [slug, ...]}`` map, for a hermetic CI snapshot of both sides at once

    Bare slugs (the first two shapes) are qualified by the catalog's declared ``repo``
    when it has one, and otherwise recorded under BOTH repos. That last fallback is
    deliberately permissive: guessing the repo wrong would fail a valid term, and the
    strict version of this check is available to anyone who passes a qualified catalog.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: set[str] = set()

    def _add(repo: str | None, slug: str) -> None:
        if "/" in slug:
            out.add(slug)
        elif repo:
            out.add(f"{repo}/{slug}")
        else:
            out.add(f"yantra4d/{slug}")
            out.add(f"fashion-cabinet/{slug}")

    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                _add(None, item)
            elif isinstance(item, dict) and item.get("slug"):
                _add(item.get("repo"), item["slug"])
        return out

    if not isinstance(data, dict):
        return out

    # A {repo: [slugs]} map — the hermetic two-sided snapshot shape. The vendored
    # snapshot also carries metadata keys (provenance, capture date); a repo key
    # holding a list is the signal, and everything else at the top level is ignored.
    repo_lists = {
        k: v
        for k, v in data.items()
        if k in {"yantra4d", "fashion-cabinet"} and isinstance(v, list)
    }
    if repo_lists:
        for repo, slugs in repo_lists.items():
            for s in slugs:
                _add(repo, s if isinstance(s, str) else str(s.get("slug", "")))
        return out

    repo = data.get("repo") or (data.get("upstream") or {}).get("repo")
    if isinstance(repo, str) and "/" in repo:
        repo = repo.rsplit("/", 1)[-1]  # 'madfam-org/yantra4d' -> 'yantra4d'

    carts = data.get("cartridges", data)
    if isinstance(carts, list):
        for c in carts:
            if isinstance(c, dict) and c.get("slug"):
                _add(c.get("repo") or repo, c["slug"])
    elif isinstance(carts, dict):
        for slug, entry in carts.items():
            entry_repo = entry.get("repo") if isinstance(entry, dict) else None
            _add(entry_repo or repo, slug)
    return out


def bundled_catalog_slugs() -> set[str]:
    """The vendored snapshot of both commons' slug sets, as ``'<repo>/<slug>'``.

    This is what makes the strict ``embodied_by`` check runnable **hermetically** — CI
    resolves every slug with no platform checkout and no network. It is a snapshot and
    therefore goes stale in one direction only: a term naming a cartridge added after
    the capture date fails here while being correct in the commons. That is the safe
    direction (it asks for a refresh rather than silently passing), and
    ``scripts/refresh_catalog_snapshot.py`` is the refresh. Anyone with a live checkout
    can bypass the snapshot entirely with ``--catalog``.
    """
    with resources.files(CATALOG_DIR).joinpath(SNAPSHOT_NAME).open(encoding="utf-8") as f:
        data = json.load(f)
    out: set[str] = set()
    for repo in ("yantra4d", "fashion-cabinet"):
        for slug in data.get(repo, []):
            out.add(f"{repo}/{slug}")
    return out


def _text_missing(block: object, field_name: str) -> list[str]:
    """Which languages are absent or blank in one quadrilingual block.

    The schema already requires the four keys. This exists for the failure the schema
    cannot see: a key present with an empty or whitespace-only value, which is what a
    half-finished entry looks like.
    """
    problems = []
    if not isinstance(block, dict):
        return [f"{field_name}: not a four-language object"]
    for lang in LANGUAGES:
        value = block.get(lang)
        if not isinstance(value, str) or not value.strip():
            problems.append(
                f"{field_name}.{lang}: missing or empty — all four languages "
                f"({', '.join(LANGUAGES)}) are required to ship (RFC 0039 §7)"
            )
    return problems


def _review_problems(doc: dict) -> list[str]:
    """The review claim's own integrity, which the schema cannot express.

    Two failures, and both are the same failure wearing different clothes: an entry
    reading as reviewed when nobody reviewed it. A `reviewed` state with no named
    reviewer is a review nobody signed, and a `reviewed` state over a language facet
    still marked `generated` is a review that skipped a language.
    """
    block = doc.get("review_status")
    if not isinstance(block, dict):
        return []
    problems = []
    state = block.get("state")
    langs = block.get("languages") or {}
    if state == "reviewed":
        if not block.get("reviewers"):
            problems.append(
                "review_status: state is 'reviewed' with no reviewers — a review "
                "nobody signed is not a review (RFC 0039 §5)"
            )
        still_generated = sorted(
            lang for lang, value in langs.items() if value == "generated"
        )
        if still_generated:
            problems.append(
                f"review_status: state is 'reviewed' while {', '.join(still_generated)} "
                f"{'is' if len(still_generated) == 1 else 'are'} still 'generated' — "
                f"the state is the WORST facet, never the best"
            )
    return problems


def check_term(
    doc: object,
    *,
    known_ids: set[str] | None = None,
    catalog: set[str] | None = None,
    filename: str | None = None,
) -> list[str]:
    """Check one term. Returns its problems (empty means it conforms).

    ``known_ids`` is the corpus's id set, for ``see_also`` resolution; omit it and
    cross-references are not checked (a single term validated in isolation cannot know
    what else exists). ``catalog`` is the ``'<repo>/<slug>'`` set from
    ``load_catalog_slugs``; omit it and ``embodied_by`` is not resolved.
    """
    problems = _schema_errors(doc)
    if not isinstance(doc, dict):
        return problems or ["not an object"]

    term_id = doc.get("id")

    # The filename IS the id. A corpus you cannot navigate by `ls` is a corpus where a
    # duplicate hides, because two files can carry the same id and the second wins.
    if filename is not None and isinstance(term_id, str):
        stem = filename[: -len(".json")] if filename.endswith(".json") else filename
        if stem != term_id:
            problems.append(
                f"id {term_id!r} does not match filename {filename!r} — the corpus is "
                f"addressed by filename, so the two must agree"
            )

    problems.extend(_text_missing(doc.get("term"), "term"))
    problems.extend(_text_missing(doc.get("definition"), "definition"))

    # RFC 0039 §7: no uncited cultural or historical claim.
    if doc.get("heritage") and not doc.get("sources"):
        problems.append(
            "heritage is true but sources is empty — a cultural or historical claim "
            "ships with a citation or not at all (RFC 0039 §7)"
        )

    problems.extend(_review_problems(doc))

    if known_ids is not None:
        for ref in doc.get("see_also") or []:
            if ref == term_id:
                problems.append(f"see_also: {ref!r} points at itself")
            elif ref not in known_ids:
                problems.append(
                    f"see_also: {ref!r} is not a term in this lexicon — a dangling "
                    f"cross-reference is a broken dictionary"
                )

    if catalog is not None:
        for slug in doc.get("embodied_by") or []:
            if slug not in catalog:
                problems.append(
                    f"embodied_by: {slug!r} does not resolve against the supplied catalog"
                )

    return problems


def check_lexicon(
    lexicon: dict[str, dict] | None = None,
    *,
    catalog: set[str] | None = None,
) -> LexiconResult:
    """Check a whole corpus: every term, plus the corpus-level properties.

    Corpus-level means the things no single term can see — duplicate ids, and whether a
    ``see_also`` resolves. Problems are prefixed with the term id so a failing run names
    the file to open.
    """
    if lexicon is None:
        lexicon = load_lexicon()

    known_ids = set(lexicon)
    problems: list[str] = []
    unresolved = 0

    for key in sorted(lexicon):
        doc = lexicon[key]
        declared = doc.get("id") if isinstance(doc, dict) else None
        if declared and declared != key:
            problems.append(
                f"{key}: declares id {declared!r} — two terms cannot share a key"
            )
        for prob in check_term(
            doc, known_ids=known_ids, catalog=catalog, filename=f"{key}.json"
        ):
            problems.append(f"{key}: {prob}")
        if catalog is None and isinstance(doc, dict):
            unresolved += len(doc.get("embodied_by") or [])

    return LexiconResult(
        terms=len(lexicon),
        ok=not problems,
        problems=problems,
        unresolved_slugs=unresolved,
        catalog_checked=catalog is not None,
    )


def review_counts(lexicon: dict[str, dict] | None = None) -> dict[str, int]:
    """How many entries are reviewed, how many are a drafting pass, how many say neither.

    ``unmarked`` is its own bucket rather than being folded into ``generated``: the G1
    corpus was written before the block existed and makes no claim, and quietly counting
    it as either would put words in its author's mouth.
    """
    if lexicon is None:
        lexicon = load_lexicon()
    counts = {"reviewed": 0, "generated": 0, "unmarked": 0}
    for doc in lexicon.values():
        block = doc.get("review_status") if isinstance(doc, dict) else None
        if not isinstance(block, dict):
            counts["unmarked"] += 1
        else:
            counts[block.get("state", "generated")] = (
                counts.get(block.get("state", "generated"), 0) + 1
            )
    return counts


def lexicon_status(lexicon: dict[str, dict] | None = None) -> str:
    """The house N/M line: how many terms are shippable out of how many exist.

    Shippable means quadrilingually complete — the count RFC 0039 §7 asks for, which
    counts entries and never fragments. A corpus where the two numbers differ has a
    translation debt, and the point of the line is that the debt is impossible to
    not see.

    The review clause carries the second debt, which N/M cannot show: four complete
    languages that nobody has read are still four complete languages. A corpus that is
    130/130 and ``generated=100`` is quadrilingual and has a hundred entries waiting on
    a native pass, and both facts belong on the same line.
    """
    if lexicon is None:
        lexicon = load_lexicon()
    total = len(lexicon)
    complete = sum(
        1
        for doc in lexicon.values()
        if isinstance(doc, dict)
        and not _text_missing(doc.get("term"), "term")
        and not _text_missing(doc.get("definition"), "definition")
    )
    domains = len({doc.get("domain") for doc in lexicon.values() if isinstance(doc, dict)})
    review = review_counts(lexicon)
    return (
        f"lexicon_status: {complete}/{total} terms quadrilingual "
        f"({'/'.join(LANGUAGES)}) domains={domains} "
        f"review: reviewed={review['reviewed']} generated={review['generated']} "
        f"unmarked={review['unmarked']}"
    )
