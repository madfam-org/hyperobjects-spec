"""The dictionary tools both commons' MCP servers expose (RFC 0039 §6.2).

The RFC's ask is literal: "both commons already ship MCP servers — add ``define(term,
lang)``, ``lookup(object)``, ``related(id)`` tools. LLMs and agent users get the
dictionary natively." The servers live in the platform repos; what belongs HERE is the
one implementation both of them call, so a definition cannot differ depending on which
half of the commons you asked.

Three functions, each returning plain JSON-able data and doing no I/O of its own:

    define("zipper_tape", "pt")   -> the tape-edge entry, in Portuguese
    lookup("fashion-cabinet/garter-belt")
                                  -> every term that cartridge embodies
    related("tape-edge")          -> what it points at, and what points back

Resolution is the part worth stating. ``define`` accepts what a user actually has in
hand, in this order: a term id (``tape-edge``, and a manifest key that is one under
another separator — ``knit_negative_ease``), a headword in any of the four languages
(``debrum de fita costurado``), a repo spelling recorded as an alias (``zipper_tape``),
or a controlled-vocabulary key and its near-duplicates (``negative_ease_knit``). That
order is deliberate — an exact id must never be shadowed by someone else's alias, which
is a real collision and not a hypothetical one: `ease` recorded `knit_negative_ease` as
an alias before that flag had an entry of its own. Every result says which route it took,
because "I found this by a fuzzy alias" and "you named it" are different claims.
"""

from __future__ import annotations

import unicodedata

from .lexicon import LANGUAGES, load_lexicon
from .vocabulary import load_vocabularies

__all__ = ["define", "lookup", "related", "MATCH_ROUTES"]

#: How a lookup found what it found, strongest first. It travels in every result.
MATCH_ROUTES: tuple[str, ...] = ("id", "headword", "alias", "vocabulary_key", "vocabulary_alias")


def _as_id(text: str) -> str:
    """Fold a manifest key onto the shape a term id has: `knit_negative_ease` is one."""
    return _fold(text).replace("_", "-").replace(".", "-").replace(" ", "-")


def _fold(text: str) -> str:
    """Casefold and strip accents, so `elevacion` finds `elevación`.

    A dictionary that only answers when the accent is typed correctly is a dictionary
    for people who already know the word.
    """
    if not isinstance(text, str):
        return ""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").strip()


def _entry_view(doc: dict, lang: str | None) -> dict:
    """One term as a caller wants it: everything, or one language of it."""
    view = {
        "id": doc.get("id"),
        "domain": doc.get("domain"),
        "term": doc.get("term"),
        "definition": doc.get("definition"),
    }
    if lang:
        view["lang"] = lang
        view["term"] = (doc.get("term") or {}).get(lang)
        view["definition"] = (doc.get("definition") or {}).get(lang)
    for optional in ("constraints", "standards", "see_also", "embodied_by", "aliases",
                     "sources", "notes", "heritage"):
        if doc.get(optional):
            view[optional] = doc[optional]
    review = doc.get("review_status")
    # Always present, and never silently absent: a caller rendering a definition to a
    # reader should be able to say whether a human has read it.
    view["review"] = review.get("state") if isinstance(review, dict) else "unmarked"
    return view


def _index(lexicon: dict[str, dict], vocabularies: dict[str, dict]):
    """Build the four resolution maps once, in priority order."""
    by_headword: dict[str, str] = {}
    by_alias: dict[str, str] = {}
    for term_id, doc in lexicon.items():
        for lang in LANGUAGES:
            word = _fold((doc.get("term") or {}).get(lang, ""))
            if word:
                by_headword.setdefault(word, term_id)
        for alias in doc.get("aliases") or []:
            name = _fold(alias.get("name", ""))
            if name:
                by_alias.setdefault(name, term_id)

    by_key: dict[str, str] = {}
    by_vocab_alias: dict[str, str] = {}
    for doc in vocabularies.values():
        for entry in doc.get("entries") or []:
            term_id = entry.get("term")
            if not term_id:
                continue
            key = _fold(entry.get("key", ""))
            if key:
                by_key.setdefault(key, term_id)
            for alias in entry.get("aliases") or []:
                name = _fold(alias.get("name", ""))
                if name:
                    by_vocab_alias.setdefault(name, term_id)
    return by_headword, by_alias, by_key, by_vocab_alias


def define(
    word: str,
    lang: str | None = None,
    *,
    lexicon: dict[str, dict] | None = None,
    vocabularies: dict[str, dict] | None = None,
) -> dict | None:
    """Resolve a word to its lexicon entry. ``None`` when nothing matches.

    ``lang`` narrows the entry to one of ``es/en/fr/pt``; omit it for all four. An
    unknown language is an error rather than a silent full entry — a caller asking for
    Portuguese and getting four languages back would render the wrong one.
    """
    if lang is not None and lang not in LANGUAGES:
        raise ValueError(f"unknown language {lang!r}; the commons speaks {', '.join(LANGUAGES)}")
    if lexicon is None:
        lexicon = load_lexicon()
    if vocabularies is None:
        vocabularies = load_vocabularies()

    query = _fold(word)
    if not query:
        return None

    by_headword, by_alias, by_key, by_vocab_alias = _index(lexicon, vocabularies)

    for route, table in (
        ("id", {_as_id(k): k for k in lexicon}),
        ("headword", by_headword),
        ("alias", by_alias),
        ("vocabulary_key", by_key),
        ("vocabulary_alias", by_vocab_alias),
    ):
        term_id = table.get(_as_id(word) if route == "id" else query)
        if term_id and term_id in lexicon:
            view = _entry_view(lexicon[term_id], lang)
            view["matched"] = {"query": word, "route": route}
            return view
    return None


def lookup(
    obj: str,
    *,
    lexicon: dict[str, dict] | None = None,
) -> dict:
    """Every term a cartridge or material card embodies.

    ``obj`` may be qualified (``fashion-cabinet/garter-belt``) or bare (``garter-belt``);
    a bare slug matches in either commons and the result says which repos answered, so an
    ambiguous name never resolves silently to one side.
    """
    if lexicon is None:
        lexicon = load_lexicon()

    wanted = obj.strip()
    qualified = "/" in wanted
    terms = []
    repos = set()
    for term_id in sorted(lexicon):
        for slug in lexicon[term_id].get("embodied_by") or []:
            hit = slug == wanted if qualified else slug.split("/", 1)[-1] == wanted
            if hit:
                doc = lexicon[term_id]
                terms.append(
                    {
                        "id": term_id,
                        "domain": doc.get("domain"),
                        "term": doc.get("term"),
                        "constraints": doc.get("constraints"),
                    }
                )
                repos.add(slug.split("/", 1)[0])
                break
    return {"object": wanted, "repos": sorted(repos), "terms": terms, "count": len(terms)}


def related(
    term_id: str,
    *,
    lexicon: dict[str, dict] | None = None,
    vocabularies: dict[str, dict] | None = None,
) -> dict | None:
    """The neighbourhood of a term: what it points at, what points back, what writes it.

    ``referenced_by`` is the half a stored `see_also` list cannot give you. Cross
    references are authored in one direction, so a term can be central to the corpus and
    look isolated from its own file — this is what makes the graph navigable in both.
    """
    if lexicon is None:
        lexicon = load_lexicon()
    if vocabularies is None:
        vocabularies = load_vocabularies()
    if term_id not in lexicon:
        return None

    doc = lexicon[term_id]
    referenced_by = sorted(
        other for other, d in lexicon.items() if term_id in (d.get("see_also") or [])
    )

    keys = []
    for name, vocab in vocabularies.items():
        for entry in vocab.get("entries") or []:
            if entry.get("term") != term_id:
                continue
            keys.append(
                {
                    "vocabulary": name,
                    "key": entry.get("key"),
                    "repo": entry.get("repo"),
                    "role": entry.get("role"),
                    "aliases": [a.get("name") for a in entry.get("aliases") or []],
                }
            )

    return {
        "id": term_id,
        "domain": doc.get("domain"),
        "see_also": list(doc.get("see_also") or []),
        "referenced_by": referenced_by,
        "embodied_by": list(doc.get("embodied_by") or []),
        "vocabulary_keys": keys,
    }
