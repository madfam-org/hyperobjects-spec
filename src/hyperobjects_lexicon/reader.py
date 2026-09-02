"""The cross-commons reader: one lexicon, both encyclopaedias, the bridge as navigation.

RFC 0039 G4. The three layers the RFC keeps distinct (§2) each already exist in this
package or in the two commons; what did not exist is a surface where a visitor can hold
all three at once — look a word up, follow it to the objects that embody it, and walk
from a garment to the solid it resolves and back again.

What this module is
-------------------
A pure function from vendored data to a directory of files. ``render()`` returns
``{relative path: text}`` and touches no disk; ``build()`` writes that mapping out and
``check()`` compares it against what is committed. Everything it reads is bundled with
the package — the term corpus, the two pinned catalog snapshots, the pinned bridge
graph — so a build needs no network, no platform checkout, and no clock.

Five properties, each of which a test holds
-------------------------------------------
1. **Deterministic.** Same inputs, byte-identical output. Every iteration is over a
   sorted sequence, every count comes from the data, and nothing carries a build
   timestamp — the only dates in the output are the ``captured_at`` of the snapshots,
   which is data about the commons and not about the build.
2. **Honest about language.** A page offers a language if and only if it HAS that
   language. The lexicon is quadrilingual by its ship gate, the catalogs are not (RFC
   0039 §5's debt: yantra4d names are English with en/es blurbs, Fashion Cabinet names
   run en/es/fr/pt at four different depths), and a switcher that offered a language the
   entry lacks would be a promise the corpus cannot keep. Where a language facet is
   missing, the page says so in that language rather than hiding the gap.
3. **Honest about review.** Every language section of a term carries its own review
   state — ``generated`` where a drafting pass wrote it, per COMMONS_VOCABULARY.md. Four
   complete languages nobody has read are still four complete languages, and the reader
   must never let a generated definition read as a reviewed one.
4. **Honest about the bridge.** Every edge either resolves to a page on both ends or is
   reported as unresolved, with the reason its author wrote where fashion-cabinet
   published one. Unresolved is REPORTED, never fatal — the same convention the
   back-edge itself keeps, and the reason `painters-pant → hammer-loop` is allowed to
   exist as an honest placeholder for a solid nobody has built yet.
5. **Works with nothing.** Semantic HTML and one stylesheet. No JavaScript, no
   framework, no CDN, no build toolchain. The language switcher is anchors plus one CSS
   rule; where ``:has()`` is unsupported the page shows every language at once, which is
   a degradation and not a break.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .lexicon import CATALOG_DIR, LANGUAGES, load_lexicon
from .vocabulary import load_vocabularies

__all__ = [
    "READER_DIR",
    "REPOS",
    "ReaderModel",
    "BridgeEdge",
    "build",
    "check",
    "load_reader_catalog",
    "load_bridge_graph",
    "load_model",
    "reader_counts",
    "reader_status",
    "render",
]

#: Where the built reader lives in this repo, relative to its root. `docs/` is where
#: this repo already publishes prose a human is meant to read (BRIDGE_HANDSHAKE,
#: COMMONS_VOCABULARY, P1B_ADOPTION), and the reader is that and not source: it is not
#: importable, not package data, and not installed. Committing it is what lets `--check`
#: fail closed and what lets a clone read the commons with no build step at all.
READER_DIR = "docs/reader"

#: The two commons, in the order the reader lists them: the solid side first, because
#: the bridge's forward direction (garment resolves hardware) reads better arriving.
REPOS: tuple[str, ...] = ("yantra4d", "fashion-cabinet")

SNAPSHOT_NAMES = {repo: f"{repo}-catalog.snapshot.json" for repo in REPOS}
BRIDGE_SNAPSHOT = "commons-bridges.snapshot.json"

#: A slug or term id safe to use as a path segment. The corpus and both catalogs are
#: kebab-case by their own schemas; this is the guard that keeps a future one from
#: writing a page outside the output directory.
SAFE_NAME = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*$")

#: Language names, in the language itself. A switcher that labelled French "French"
#: would be a switcher written for people who already read English.
LANGUAGE_NAMES = {
    "es": "Español",
    "en": "English",
    "fr": "Français",
    "pt": "Português",
}

#: Every chrome string in all four languages. Global chrome renders in `es` — the house
#: register, RFC 0039 §5 — while each language section renders its own labels in its own
#: language. Holding all four here is what makes per-language page variants a later
#: rendering choice rather than a rewrite.
CHROME: dict[str, dict[str, str]] = {
    "reader": {
        "es": "Lector del procomún",
        "en": "Commons reader",
        "fr": "Lecteur des communs",
        "pt": "Leitor do comum",
    },
    "terms": {"es": "Términos", "en": "Terms", "fr": "Termes", "pt": "Termos"},
    "term": {"es": "Término", "en": "Term", "fr": "Terme", "pt": "Termo"},
    "definition": {
        "es": "Definición",
        "en": "Definition",
        "fr": "Définition",
        "pt": "Definição",
    },
    "name": {"es": "Nombre", "en": "Name", "fr": "Nom", "pt": "Nome"},
    "languages": {"es": "Idiomas", "en": "Languages", "fr": "Langues", "pt": "Idiomas"},
    "all": {"es": "Todos", "en": "All", "fr": "Toutes", "pt": "Todos"},
    "societal_benefit": {
        "es": "Beneficio social",
        "en": "Societal benefit",
        "fr": "Bénéfice sociétal",
        "pt": "Benefício social",
    },
    "compensation_notes": {
        "es": "Notas de compensación",
        "en": "Compensation notes",
        "fr": "Notes de compensation",
        "pt": "Notas de compensação",
    },
    "no_name": {
        "es": "Sin nombre en este idioma.",
        "en": "No name in this language.",
        "fr": "Pas de nom dans cette langue.",
        "pt": "Sem nome nesta língua.",
    },
    "generated": {
        "es": "redactado por una pasada de borrador, sin revisión nativa",
        "en": "written by a drafting pass, not natively reviewed",
        "fr": "rédigé par une passe de brouillon, sans relecture native",
        "pt": "redigido por uma passagem de rascunho, sem revisão nativa",
    },
    "reviewed": {
        "es": "revisado",
        "en": "reviewed",
        "fr": "relu",
        "pt": "revisto",
    },
    "unmarked": {
        "es": "sin marcar: la entrada no declara revisión",
        "en": "unmarked: the entry claims no review",
        "fr": "non marqué : l'entrée ne déclare aucune relecture",
        "pt": "sem marca: a entrada não declara revisão",
    },
}

#: Section headings that are not per-language (they label structured data, not prose).
LABELS = {
    "domain": "Dominio",
    "aliases": "Cómo se escribe en cada repositorio",
    "standards": "Normas citadas",
    "constraints": "Restricción",
    "sources": "Fuentes",
    "notes": "Notas",
    "see_also": "Véase también",
    "embodied_by": "Encarnado por",
    "vocabulary_keys": "Claves de manifiesto",
    "review": "Revisión",
    "facts": "Ficha",
    "interfaces": "Interfaces declaradas",
    "terms_here": "Términos que encarna",
    "bridge_out": "Puente al hardware",
    "bridge_in": "Prendas que lo consumen",
    "manifest": "Manifiesto",
    "unresolved": "Sin resolver",
    "provenance": "Procedencia",
}


# ── loading ──────────────────────────────────────────────────────────────────


def _bundled(name: str) -> dict:
    with resources.files(CATALOG_DIR).joinpath(name).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_reader_catalog(repo: str) -> dict:
    """One commons' pinned catalog snapshot, as vendored."""
    if repo not in SNAPSHOT_NAMES:
        raise ValueError(f"unknown commons {repo!r} — expected one of {', '.join(REPOS)}")
    return _bundled(SNAPSHOT_NAMES[repo])


def load_bridge_graph() -> dict:
    """The pinned bridge graph: forward claims, published back edge, unlinked claims."""
    return _bundled(BRIDGE_SNAPSHOT)


@dataclass(frozen=True)
class BridgeEdge:
    """One cross-commons edge, with everything the reader needs to be honest about it.

    ``resolved`` is strictly about PAGES: both ends exist in the vendored catalogs, so
    the reader can link them. ``linked`` is the commons' own claim about the geometry,
    and the two are deliberately separate axes — `hi-vis-vest → hook-loop-tape` has two
    pages and an honest `linked: false`, because the solid exists and the placket maths
    was written against parameters it does not have.
    """

    source: str
    target: str
    linked: bool
    direction: str
    drives: tuple[str, ...] = ()
    resolved: bool = True
    reason: str | None = None

    @property
    def problems(self) -> tuple[str, ...]:
        return () if self.resolved else (f"no page for one end of {self.source} → {self.target}",)


@dataclass
class ReaderModel:
    """Everything the reader renders, assembled once and read many times."""

    terms: dict[str, dict]
    catalogs: dict[str, dict]
    bridges: dict
    entries: dict[str, dict] = field(default_factory=dict)
    terms_by_object: dict[str, list[str]] = field(default_factory=dict)
    edges: list[BridgeEdge] = field(default_factory=list)
    back_edges: list[BridgeEdge] = field(default_factory=list)
    vocabulary_keys: dict[str, list[dict]] = field(default_factory=dict)
    dangling_embodied_by: list[str] = field(default_factory=list)

    def entry(self, key: str) -> dict | None:
        return self.entries.get(key)


def _object_key(repo: str, slug: str) -> str:
    return f"{repo}/{slug}"


def load_model(
    lexicon: dict[str, dict] | None = None,
    catalogs: dict[str, dict] | None = None,
    bridges: dict | None = None,
) -> ReaderModel:
    """Assemble the reader's model from the bundled data (or from data handed in)."""
    lexicon = load_lexicon() if lexicon is None else lexicon
    catalogs = (
        {repo: load_reader_catalog(repo) for repo in REPOS} if catalogs is None else catalogs
    )
    bridges = load_bridge_graph() if bridges is None else bridges

    entries: dict[str, dict] = {}
    for repo in REPOS:
        for entry in catalogs[repo]["entries"]:
            slug = entry["slug"]
            if not SAFE_NAME.match(slug):
                raise ValueError(
                    f"{repo}: slug {slug!r} is not a safe path segment — the reader "
                    f"writes one file per entry and will not write outside its output"
                )
            entries[_object_key(repo, slug)] = {**entry, "repo": repo}

    terms_by_object: dict[str, list[str]] = {}
    dangling: list[str] = []
    for term_id in sorted(lexicon):
        if not SAFE_NAME.match(term_id):
            raise ValueError(f"term id {term_id!r} is not a safe path segment")
        for ref in lexicon[term_id].get("embodied_by") or []:
            if ref in entries:
                terms_by_object.setdefault(ref, []).append(term_id)
            else:
                dangling.append(f"{term_id}: embodied_by {ref} has no page in this snapshot")

    keys: dict[str, list[dict]] = {}
    for name, doc in sorted(load_vocabularies().items()):
        for vocab_entry in doc.get("entries") or []:
            term_id = vocab_entry.get("term")
            if not term_id:
                continue
            keys.setdefault(term_id, []).append(
                {
                    "vocabulary": name,
                    "repo": vocab_entry.get("repo"),
                    "key": vocab_entry.get("key"),
                    "role": vocab_entry.get("role"),
                    "aliases": sorted(
                        alias.get("name", "") for alias in vocab_entry.get("aliases") or []
                    ),
                }
            )
    for term_id in keys:
        keys[term_id].sort(key=lambda k: (k["repo"] or "", k["key"] or ""))

    reasons = {
        claim["hardware"]: claim.get("reason")
        for claim in bridges.get("unlinked_claims") or []
        if claim.get("hardware")
    }

    edges: list[BridgeEdge] = []
    for raw in bridges.get("edges") or []:
        source = _object_key("fashion-cabinet", raw["garment"])
        target = _object_key(raw.get("platform") or "yantra4d", raw.get("hardware") or "")
        resolved = source in entries and target in entries
        edges.append(
            BridgeEdge(
                source=source,
                target=target,
                linked=bool(raw.get("linked")),
                direction="forward",
                drives=tuple(raw.get("params_map_keys") or ()),
                resolved=resolved,
                reason=None if raw.get("linked") else reasons.get(raw.get("hardware")),
            )
        )

    back: list[BridgeEdge] = []
    for raw in bridges.get("back_edges") or []:
        source = _object_key("yantra4d", raw["hardware"])
        target = _object_key("fashion-cabinet", raw["garment"])
        back.append(
            BridgeEdge(
                source=source,
                target=target,
                linked=True,
                direction="back",
                drives=tuple(raw.get("drives") or ()),
                resolved=source in entries and target in entries,
            )
        )

    return ReaderModel(
        terms=lexicon,
        catalogs=catalogs,
        bridges=bridges,
        entries=entries,
        terms_by_object=terms_by_object,
        edges=edges,
        back_edges=back,
        vocabulary_keys=keys,
        dangling_embodied_by=sorted(dangling),
    )


# ── counting ─────────────────────────────────────────────────────────────────


def _language_tally(blocks) -> dict[str, int]:
    """How many of a set of records carry each language. The reader's honesty budget."""
    tally = {lang: 0 for lang in LANGUAGES}
    for langs in blocks:
        for lang in langs:
            if lang in tally:
                tally[lang] += 1
    return tally


def reader_counts(model: ReaderModel | None = None) -> dict:
    """Every number the reader publishes about itself, computed from the data.

    This is the one place counts are produced. The README and COMMONS_VOCABULARY tables
    are written from it by ``scripts/refresh_reader_counts.py``, and the built reader
    ships it as ``summary.json``, so a number in the docs and a number on the page
    cannot disagree — the failure mode `refresh_vocabulary_counts.py` already exists to
    prevent, one layer up.
    """
    model = load_model() if model is None else model

    review = {"reviewed": 0, "generated": 0, "unmarked": 0}
    for doc in model.terms.values():
        block = doc.get("review_status")
        state = block.get("state", "generated") if isinstance(block, dict) else "unmarked"
        review[state] = review.get(state, 0) + 1

    forward_linked = {(e.target, e.source) for e in model.edges if e.linked}
    back_pairs = {(e.source, e.target) for e in model.back_edges}

    catalogs = {}
    for repo in REPOS:
        source = model.catalogs[repo]["source"]
        entries = model.catalogs[repo]["entries"]
        catalogs[repo] = {
            "entries": len(entries),
            "cartridges": source.get("cartridges"),
            "materials": source.get("materials"),
            "commit": source.get("commit"),
            "captured_at": model.catalogs[repo].get("captured_at"),
            "languages": _language_tally(
                set(e.get("names") or {}) | set(e.get("summary") or {}) for e in entries
            ),
        }

    pages = (
        3  # index, bridges, terms index
        + len(REPOS)  # one index per commons
        + len(model.terms)
        + len(model.entries)
    )

    return {
        "schema_version": 1,
        "terms": {
            "total": len(model.terms),
            "domains": len(
                {doc.get("domain") for doc in model.terms.values() if isinstance(doc, dict)}
            ),
            "review": review,
            "languages": _language_tally(
                set(doc.get("term") or {}) & set(doc.get("definition") or {})
                for doc in model.terms.values()
            ),
        },
        "catalog": catalogs,
        "bridges": {
            "edges": len(model.edges),
            "resolved": sum(1 for e in model.edges if e.resolved),
            "unresolved": sum(1 for e in model.edges if not e.resolved),
            "linked": sum(1 for e in model.edges if e.linked),
            "unlinked": sum(1 for e in model.edges if not e.linked),
            "unlinked_claims": len(model.bridges.get("unlinked_claims") or []),
            "back_edges": len(model.back_edges),
            "back_resolved": sum(1 for e in model.back_edges if e.resolved),
            "back_unresolved": sum(1 for e in model.back_edges if not e.resolved),
            "mirrored": len(forward_linked & back_pairs),
            "resolved_against": (model.bridges.get("resolved_against") or {}).get(
                "yantra4d_commit"
            ),
        },
        "embodied_by_without_page": len(model.dangling_embodied_by),
        "pages": pages,
    }


def reader_status(model: ReaderModel | None = None) -> str:
    """The house one-line status, in the shape ``lexicon_status`` established."""
    counts = reader_counts(model)
    bridges = counts["bridges"]
    return (
        f"reader_status: pages={counts['pages']} terms={counts['terms']['total']} "
        f"yantra4d={counts['catalog']['yantra4d']['entries']} "
        f"fashion-cabinet={counts['catalog']['fashion-cabinet']['entries']} "
        f"bridges: edges={bridges['edges']} resolved={bridges['resolved']} "
        f"unresolved={bridges['unresolved']} unlinked={bridges['unlinked']} "
        f"back={bridges['back_edges']} mirrored={bridges['mirrored']}"
    )


# ── rendering ────────────────────────────────────────────────────────────────


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _chrome(key: str, lang: str = "es") -> str:
    return CHROME[key][lang]


STYLESHEET = """\
/* The whole reader's stylesheet. No framework, no CDN, no JavaScript anywhere in this
   build: the language switcher below is anchors and one rule.

   How the switcher works, and how it fails safely. Each page carries every language it
   HAS as a <section class="lang" id="es|en|fr|pt">. With no fragment in the URL, all of
   them show. Selecting one from the nav targets it, and the rule hides its siblings. A
   browser without :has() support simply never matches the rule and shows every language
   at once — a degradation, not a break, and the reason this is CSS rather than script. */
:root {
  --ink: #17181c;
  --muted: #5c6068;
  --rule: #d8d5cd;
  --paper: #fbfaf7;
  --accent: #7a4a1f;
  --warn: #8a4b16;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font: 16px/1.55 Georgia, "Iowan Old Style", "Times New Roman", serif;
}
header.site, footer.site {
  border-bottom: 1px solid var(--rule);
  padding: 0.8rem 1.2rem;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 0.85rem;
}
footer.site { border-bottom: 0; border-top: 1px solid var(--rule); color: var(--muted); }
header.site a.brand { font-weight: 700; margin-right: 1.2rem; }
header.site nav { display: inline; }
header.site nav a { margin-right: 0.9rem; }
a { color: var(--accent); }
main { max-width: 46rem; margin: 0 auto; padding: 1.4rem 1.2rem 3rem; }
h1 { font-size: 1.7rem; line-height: 1.2; margin: 0 0 0.2rem; }
h2 { font-size: 1.15rem; margin: 1.8rem 0 0.4rem; }
h3 { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.07em;
     color: var(--muted); margin: 1rem 0 0.2rem;
     font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
p.lede { color: var(--muted); margin-top: 0; }
p.headword { font-size: 1.2rem; font-weight: 700; margin: 0.1rem 0; }
p.absent { color: var(--muted); font-style: italic; }
nav.langs {
  border: 1px solid var(--rule); border-radius: 3px; padding: 0.4rem 0.7rem;
  margin: 1.2rem 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 0.85rem;
}
nav.langs .langs-label { color: var(--muted); margin-right: 0.6rem; }
nav.langs a { margin-right: 0.8rem; }
section.lang { border-left: 3px solid var(--rule); padding-left: 0.9rem; margin: 1.2rem 0; }
section.lang:target { border-left-color: var(--accent); }
body:has(section.lang:target) section.lang:not(:target) { display: none; }
span.badge {
  display: inline-block; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
  border: 1px solid var(--rule); border-radius: 2px; padding: 0.05rem 0.35rem;
  color: var(--muted);
}
span.badge-generated { color: var(--warn); border-color: var(--warn); }
p.review { color: var(--muted); font-size: 0.85rem; margin: 0.3rem 0 0; }
blockquote.constraint {
  border-left: 3px solid var(--warn); margin: 0.4rem 0; padding: 0.2rem 0 0.2rem 0.9rem;
}
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { border-bottom: 1px solid var(--rule); padding: 0.3rem 0.5rem 0.3rem 0;
         text-align: left; vertical-align: top; }
th { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size: 0.75rem;
     text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
code, .mono { font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
              font-size: 0.85em; }
ul.cols { columns: 2; list-style: none; padding: 0; }
ul.cols li { break-inside: avoid; margin-bottom: 0.15rem; }
ul.plain { list-style: none; padding: 0; }
.unresolved { color: var(--warn); }
@media (max-width: 34rem) { ul.cols { columns: 1; } }
"""


def _document(*, title: str, root: str, main: str, provenance: str) -> str:
    """One page. Global chrome is `es` — the house register — while each language
    section below renders its own labels in its own language."""
    nav = "".join(
        f'<a href="{root}{href}">{_esc(label)}</a>\n      '
        for href, label in (
            ("terms/index.html", _chrome("terms")),
            ("yantra4d/index.html", "Yantra4D"),
            ("fashion-cabinet/index.html", "Fashion Cabinet"),
            ("bridges.html", "Puentes"),
        )
    )
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<link rel="stylesheet" href="{root}style.css">
</head>
<body>
<header class="site">
  <a class="brand" href="{root}index.html">{_esc(_chrome("reader"))}</a>
  <nav aria-label="Secciones">
      {nav.strip()}
  </nav>
</header>
<main>
{main.rstrip()}
</main>
<footer class="site">
  <p>{provenance}</p>
</footer>
</body>
</html>
"""


def _language_sections(
    facets: dict[str, list[tuple[str, str | None]]],
    *,
    self_href: str,
    review: dict | None = None,
) -> str:
    """The switcher and the per-language sections, for exactly the languages present.

    ``facets`` maps a language to the labelled blocks written in it. A language absent
    from that mapping gets no anchor and no section: the reader never offers a language
    the entry does not have, which is the whole point of building this from the data
    rather than from the four-language ideal.
    """
    present = [lang for lang in LANGUAGES if lang in facets]
    if not present:
        return '<p class="absent">Esta entrada no trae texto en ningún idioma.</p>'

    links = "".join(
        f'<a href="#{lang}" hreflang="{lang}" lang="{lang}">{_esc(LANGUAGE_NAMES[lang])}</a>\n  '
        for lang in present
    )
    out = [
        f'<nav class="langs" aria-label="{_esc(_chrome("languages"))}" '
        f'data-langs="{" ".join(present)}">',
        f'  <span class="langs-label">{_esc(_chrome("languages"))}</span>',
        f"  {links.strip()}",
        f'  <a class="all" href="{_esc(self_href)}">{_esc(_chrome("all"))}</a>',
        "</nav>",
    ]

    for lang in present:
        out.append(f'<section class="lang" id="{lang}" lang="{lang}">')
        out.append(f"<h2>{_esc(LANGUAGE_NAMES[lang])}</h2>")
        if review is not None:
            state = (review.get("languages") or {}).get(lang) or review.get(
                "state", "unmarked"
            )
            css = "badge-generated" if state == "generated" else ""
            out.append(
                f'<p class="review"><span class="badge {css}">{_esc(state)}</span> '
                f'{_esc(_chrome(state, lang))}</p>'
            )
        for label, text in facets[lang]:
            if label == "no_name":
                out.append(f'<p class="absent">{_esc(_chrome("no_name", lang))}</p>')
                continue
            heading = _esc(_chrome(label, lang))
            body = _esc(text)
            if label in ("term", "name"):
                out.append(f"<h3>{heading}</h3>")
                out.append(f'<p class="headword">{body}</p>')
            else:
                out.append(f"<h3>{heading}</h3>")
                out.append(f"<p>{body}</p>")
        out.append("</section>")
    return "\n".join(out)


def _term_facets(doc: dict) -> dict[str, list[tuple[str, str | None]]]:
    facets: dict[str, list[tuple[str, str | None]]] = {}
    term = doc.get("term") or {}
    definition = doc.get("definition") or {}
    for lang in LANGUAGES:
        rows: list[tuple[str, str | None]] = []
        if isinstance(term.get(lang), str) and term[lang].strip():
            rows.append(("term", term[lang].strip()))
        if isinstance(definition.get(lang), str) and definition[lang].strip():
            rows.append(("definition", definition[lang].strip()))
        if rows:
            facets[lang] = rows
    return facets


def _entry_facets(entry: dict) -> dict[str, list[tuple[str, str | None]]]:
    names = entry.get("names") or {}
    summary = entry.get("summary") or {}
    label = entry.get("summary_label") or "societal_benefit"
    facets: dict[str, list[tuple[str, str | None]]] = {}
    for lang in LANGUAGES:
        rows: list[tuple[str, str | None]] = []
        if names.get(lang):
            rows.append(("name", names[lang]))
        elif summary.get(lang):
            rows.append(("no_name", None))
        if summary.get(lang):
            rows.append((label, summary[lang]))
        if rows:
            facets[lang] = rows
    return facets


def _entry_label(entry: dict) -> str:
    for lang in LANGUAGES:
        value = (entry.get("names") or {}).get(lang)
        if value:
            return value
    return entry.get("slug", "")


def _object_href(key: str, root: str) -> str:
    repo, slug = key.split("/", 1)
    return f"{root}{repo}/{slug}.html"


def _object_link(model: ReaderModel, key: str, root: str) -> str:
    """A link to an object's page — or a visible statement that it has none.

    An `embodied_by` or a bridge target that this snapshot cannot show is written out
    as unresolved rather than dropped. A reader that silently omits what it cannot
    resolve is a reader you cannot trust about what it does show.
    """
    entry = model.entry(key)
    if entry is None:
        return (
            f'<span class="unresolved"><span class="mono">{_esc(key)}</span> — '
            f"sin página en esta instantánea</span>"
        )
    return (
        f'<a href="{_esc(_object_href(key, root))}">'
        f'<span class="mono">{_esc(key)}</span></a> — {_esc(_entry_label(entry))}'
    )


def _provenance(model: ReaderModel, root: str) -> str:
    parts = []
    for repo in REPOS:
        source = model.catalogs[repo]["source"]
        parts.append(
            f'{_esc(repo)} <span class="mono">{_esc((source.get("commit") or "")[:9])}</span>'
        )
    return (
        f'Construido de instantáneas fijadas (RFC 0039 G4): {" · ".join(parts)}. '
        f'Sin JavaScript. <a href="{root}bridges.html">Procedencia completa</a>.'
    )


def _dl(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    items = "".join(
        f"  <dt>{_esc(key)}</dt><dd>{value}</dd>\n" for key, value in rows
    )
    return f"<dl>\n{items}</dl>"


def _term_page(model: ReaderModel, term_id: str) -> str:
    doc = model.terms[term_id]
    root = "../"
    review = doc.get("review_status") if isinstance(doc.get("review_status"), dict) else None
    body = [
        f"<h1>{_esc(term_id)}</h1>",
        f'<p class="lede">{_esc(LABELS["domain"])}: <span class="mono">'
        f'{_esc(doc.get("domain", "?"))}</span></p>',
        _language_sections(
            _term_facets(doc),
            self_href=f"{_esc(term_id)}.html",
            review=review or {"state": "unmarked"},
        ),
    ]

    if doc.get("constraints"):
        body.append(f'<h2>{_esc(LABELS["constraints"])}</h2>')
        body.append(
            f'<blockquote class="constraint" lang="en"><p>{_esc(doc["constraints"])}</p>'
            f"</blockquote>"
        )

    aliases = doc.get("aliases") or []
    if aliases:
        rows = "".join(
            f"<tr><td><span class=\"mono\">{_esc(a.get('name'))}</span></td>"
            f"<td><span class=\"mono\">{_esc(a.get('repo'))}</span></td>"
            f"<td>{_esc(a.get('note', ''))}</td></tr>\n"
            for a in aliases
        )
        body.append(f'<h2>{_esc(LABELS["aliases"])}</h2>')
        body.append(
            "<table>\n<thead><tr><th>clave</th><th>repositorio</th><th>nota</th></tr>"
            f"</thead>\n<tbody>\n{rows}</tbody>\n</table>"
        )

    keys = model.vocabulary_keys.get(term_id) or []
    if keys:
        rows = "".join(
            f"<tr><td><span class=\"mono\">{_esc(k['repo'])}/{_esc(k['key'])}</span></td>"
            f"<td>{_esc(k['role'])}</td>"
            f"<td><span class=\"mono\">{_esc(', '.join(k['aliases']))}</span></td></tr>\n"
            for k in keys
        )
        body.append(f'<h2>{_esc(LABELS["vocabulary_keys"])}</h2>')
        body.append(
            "<table>\n<thead><tr><th>clave</th><th>papel</th><th>alias</th></tr></thead>\n"
            f"<tbody>\n{rows}</tbody>\n</table>"
        )

    if doc.get("standards"):
        items = "".join(f"<li>{_esc(s)}</li>" for s in doc["standards"])
        body.append(f'<h2>{_esc(LABELS["standards"])}</h2><ul>{items}</ul>')

    see_also = doc.get("see_also") or []
    if see_also:
        items = "".join(
            f'<li><a href="{_esc(ref)}.html">{_esc(ref)}</a></li>'
            if ref in model.terms
            else f'<li class="unresolved">{_esc(ref)}</li>'
            for ref in see_also
        )
        body.append(f'<h2>{_esc(LABELS["see_also"])}</h2><ul class="cols">{items}</ul>')

    embodied = doc.get("embodied_by") or []
    if embodied:
        items = "".join(
            f"<li>{_object_link(model, ref, root)}</li>\n" for ref in embodied
        )
        body.append(f'<h2>{_esc(LABELS["embodied_by"])}</h2><ul class="plain">\n{items}</ul>')

    if doc.get("sources"):
        items = "".join(f"<li>{_esc(s)}</li>" for s in doc["sources"])
        body.append(f'<h2>{_esc(LABELS["sources"])}</h2><ul>{items}</ul>')

    if doc.get("notes"):
        body.append(f'<h2>{_esc(LABELS["notes"])}</h2><p lang="en">{_esc(doc["notes"])}</p>')

    state = (review or {}).get("state", "unmarked")
    facets = (review or {}).get("languages") or {}
    detail = ", ".join(f"{lang}={facets[lang]}" for lang in LANGUAGES if lang in facets)
    body.append(f'<h2>{_esc(LABELS["review"])}</h2>')
    body.append(
        f'<p class="review"><span class="badge '
        f'{"badge-generated" if state == "generated" else ""}">{_esc(state)}</span> '
        f'{_esc(_chrome(state))}'
        + (f" — {_esc(detail)}" if detail else "")
        + "</p>"
    )

    return _document(
        title=f"{term_id} — {_chrome('reader')}",
        root=root,
        main="\n".join(body),
        provenance=_provenance(model, root),
    )


def _entry_page(model: ReaderModel, key: str) -> str:
    entry = model.entries[key]
    repo, slug = key.split("/", 1)
    root = "../"
    source = model.catalogs[repo]["source"]
    blob = f"{source['url']}/blob/{source['commit']}/{entry.get('manifest', '')}"

    body = [
        f"<h1>{_esc(_entry_label(entry))}</h1>",
        f'<p class="lede"><span class="mono">{_esc(key)}</span> · {_esc(entry["kind"])}'
        + (f' · {_esc(entry["license"])}' if entry.get("license") else "")
        + "</p>",
        _language_sections(_entry_facets(entry), self_href=f"{_esc(slug)}.html"),
    ]

    if entry.get("facts"):
        body.append(f'<h2>{_esc(LABELS["facts"])}</h2>')
        body.append(_dl([(k, _esc(v)) for k, v in entry["facts"]]))

    if entry.get("interfaces"):
        rows = "".join(
            f"<tr><td><span class=\"mono\">{_esc(i.get('id'))}</span></td>"
            f"<td><span class=\"mono\">{_esc(i.get('type'))}</span></td>"
            f"<td>{_esc(i.get('label') or '')}</td>"
            f"<td>{_esc(i.get('standard') or '')}</td></tr>\n"
            for i in entry["interfaces"]
        )
        body.append(f'<h2>{_esc(LABELS["interfaces"])}</h2>')
        body.append(
            "<table>\n<thead><tr><th>id</th><th>tipo</th><th>etiqueta</th>"
            f"<th>norma</th></tr></thead>\n<tbody>\n{rows}</tbody>\n</table>"
        )

    if entry.get("standards"):
        items = "".join(f"<li>{_esc(s)}</li>" for s in entry["standards"])
        body.append(f'<h2>{_esc(LABELS["standards"])}</h2><ul>{items}</ul>')

    terms_here = model.terms_by_object.get(key) or []
    if terms_here:
        items = "".join(
            f'<li><a href="{root}terms/{_esc(t)}.html">{_esc(t)}</a> — '
            f'{_esc((model.terms[t].get("term") or {}).get("es", t))}</li>\n'
            for t in terms_here
        )
        body.append(f'<h2>{_esc(LABELS["terms_here"])}</h2><ul class="plain">\n{items}</ul>')

    out_edges = [e for e in model.edges if e.source == key]
    if out_edges:
        body.append(f'<h2>{_esc(LABELS["bridge_out"])}</h2>')
        for edge in out_edges:
            drives = ", ".join(edge.drives)
            state = (
                '<span class="badge">linked</span>'
                if edge.linked
                else '<span class="badge badge-generated">no enlazado</span>'
            )
            body.append(
                f'<p>{state} {_object_link(model, edge.target, root)}</p>'
            )
            if drives:
                body.append(
                    f'<p class="review">Parámetros: '
                    f'<span class="mono">{_esc(drives)}</span></p>'
                )
            if edge.reason:
                body.append(f'<p class="review" lang="en">{_esc(edge.reason)}</p>')

    in_edges = [e for e in model.back_edges if e.source == key]
    if in_edges:
        items = "".join(
            f"<li>{_object_link(model, e.target, root)}"
            + (
                f' — <span class="mono">{_esc(", ".join(e.drives))}</span>'
                if e.drives
                else ""
            )
            + "</li>\n"
            for e in in_edges
        )
        body.append(
            f'<h2>{_esc(LABELS["bridge_in"])} ({len(in_edges)})</h2>'
            f'<ul class="plain">\n{items}</ul>'
        )

    if entry.get("manifest"):
        body.append(f'<h2>{_esc(LABELS["manifest"])}</h2>')
        body.append(
            f'<p><a href="{_esc(blob)}"><span class="mono">'
            f'{_esc(entry["manifest"])}</span></a> — la fuente única vive en su procomún; '
            f"este lector enlaza el artículo, nunca lo copia (RFC 0039 §2).</p>"
        )

    return _document(
        title=f"{_entry_label(entry)} — {repo}",
        root=root,
        main="\n".join(body),
        provenance=_provenance(model, root),
    )


def _chips(langs) -> str:
    """The languages a row actually has, as chips. Absent languages are absent — the
    index never shows a language a reader could click into and find nothing."""
    return "".join(
        f'<span class="badge" lang="{lang}">{lang}</span> '
        for lang in LANGUAGES
        if lang in langs
    )


def _terms_index(model: ReaderModel) -> str:
    root = "../"
    by_domain: dict[str, list[str]] = {}
    for term_id in sorted(model.terms):
        by_domain.setdefault(model.terms[term_id].get("domain", "?"), []).append(term_id)

    counts = reader_counts(model)
    body = [
        f"<h1>{_esc(_chrome('terms'))}</h1>",
        f'<p class="lede">{counts["terms"]["total"]} términos en '
        f'{counts["terms"]["domains"]} dominios, cada uno cuadrilingüe (es/en/fr/pt). '
        f'Revisión: reviewed={counts["terms"]["review"]["reviewed"]} '
        f'generated={counts["terms"]["review"]["generated"]} '
        f'unmarked={counts["terms"]["review"]["unmarked"]}.</p>',
    ]
    for domain in sorted(by_domain):
        body.append(f"<h2>{_esc(domain)} ({len(by_domain[domain])})</h2>")
        rows = []
        for term_id in by_domain[domain]:
            doc = model.terms[term_id]
            review = doc.get("review_status")
            state = review.get("state", "generated") if isinstance(review, dict) else "unmarked"
            langs = set(doc.get("term") or {}) & set(doc.get("definition") or {})
            rows.append(
                f'<tr><td><a href="{_esc(term_id)}.html">{_esc(term_id)}</a></td>'
                f'<td>{_esc((doc.get("term") or {}).get("es", ""))}</td>'
                f"<td>{_chips(langs)}</td>"
                f'<td><span class="badge '
                f'{"badge-generated" if state == "generated" else ""}">{_esc(state)}'
                f"</span></td></tr>"
            )
        body.append(
            "<table>\n<thead><tr><th>id</th><th>es</th><th>idiomas</th>"
            f"<th>revisión</th></tr></thead>\n<tbody>\n{chr(10).join(rows)}\n"
            "</tbody>\n</table>"
        )
    return _document(
        title=f"{_chrome('terms')} — {_chrome('reader')}",
        root=root,
        main="\n".join(body),
        provenance=_provenance(model, root),
    )


def _catalog_index(model: ReaderModel, repo: str) -> str:
    root = "../"
    snapshot = model.catalogs[repo]
    source = snapshot["source"]
    counts = reader_counts(model)["catalog"][repo]

    cartridges: dict[str, list[dict]] = {}
    materials: list[dict] = []
    for entry in snapshot["entries"]:
        if entry["kind"] == "material":
            materials.append(entry)
        else:
            cartridges.setdefault(entry.get("group") or "?", []).append(entry)

    langs = ", ".join(f"{lang}={counts['languages'][lang]}" for lang in LANGUAGES)
    body = [
        f"<h1>{_esc(repo)}</h1>",
        f'<p class="lede">{counts["entries"]} entradas '
        f'({counts["cartridges"]} cartuchos + {counts["materials"]} fichas de material) '
        f'fijadas en <span class="mono">{_esc((source.get("commit") or "")[:9])}</span>, '
        f'capturadas {_esc(snapshot.get("captured_at"))}. '
        f"Cobertura de idiomas: {_esc(langs)}.</p>",
    ]

    def _rows(entries: list[dict]) -> str:
        out = []
        for entry in entries:
            key = _object_key(repo, entry["slug"])
            bridged = sum(
                1
                for e in model.edges + model.back_edges
                if e.source == key or e.target == key
            )
            langs_here = set(entry.get("names") or {}) | set(entry.get("summary") or {})
            out.append(
                f'<tr><td><a href="{_esc(entry["slug"])}.html">'
                f'<span class="mono">{_esc(entry["slug"])}</span></a></td>'
                f"<td>{_esc(_entry_label(entry))}</td>"
                f"<td>{_chips(langs_here)}</td>"
                f'<td>{bridged or ""}</td></tr>'
            )
        return "\n".join(out)

    header = (
        "<thead><tr><th>slug</th><th>nombre</th><th>idiomas</th>"
        "<th>puentes</th></tr></thead>"
    )
    for group in sorted(cartridges):
        body.append(f"<h2>{_esc(group)} ({len(cartridges[group])})</h2>")
        body.append(f"<table>\n{header}\n<tbody>\n{_rows(cartridges[group])}\n</tbody>\n</table>")
    if materials:
        body.append(f"<h2>fichas de material ({len(materials)})</h2>")
        body.append(f"<table>\n{header}\n<tbody>\n{_rows(materials)}\n</tbody>\n</table>")

    return _document(
        title=f"{repo} — {_chrome('reader')}",
        root=root,
        main="\n".join(body),
        provenance=_provenance(model, root),
    )


def _bridges_page(model: ReaderModel) -> str:
    root = ""
    counts = reader_counts(model)
    bridges = counts["bridges"]
    y4d_commit = model.catalogs["yantra4d"]["source"]["commit"]
    fc_commit = model.catalogs["fashion-cabinet"]["source"]["commit"]
    against = bridges["resolved_against"] or ""

    body = [
        "<h1>Puentes entre los dos procomunes</h1>",
        '<p class="lede">Cada prenda que declara <span class="mono">hardware_ref</span> '
        "resuelve un sólido de Yantra4D; cada sólido publica de vuelta las prendas que lo "
        "consumen. Esas dos aristas vienen de dos archivos publicados distintos, y aquí se "
        "guardan las dos: que coincidan es un hecho comprobado, no supuesto.</p>",
        f'<h2>{_esc(LABELS["provenance"])}</h2>',
        _dl(
            [
                ("yantra4d", f'<span class="mono">{_esc(y4d_commit)}</span>'),
                ("fashion-cabinet", f'<span class="mono">{_esc(fc_commit)}</span>'),
                (
                    "back edge resuelta contra",
                    f'<span class="mono">{_esc(against)}</span>'
                    + (
                        ""
                        if against == y4d_commit
                        else ' <span class="unresolved">— un commit de yantra4d distinto '
                        "del catálogo fijado aquí; la arista de vuelta se calculó antes</span>"
                    ),
                ),
            ]
        ),
        "<h2>Cuentas</h2>",
        _dl(
            [
                ("aristas declaradas (prenda → hardware)", str(bridges["edges"])),
                ("con página en ambos extremos", str(bridges["resolved"])),
                ("sin resolver", str(bridges["unresolved"])),
                ("enlazadas", str(bridges["linked"])),
                ("reclamadas pero no enlazadas", str(bridges["unlinked"])),
                ("aristas de vuelta (hardware → prendas)", str(bridges["back_edges"])),
                ("de vuelta con página en ambos extremos", str(bridges["back_resolved"])),
                ("coincidentes en las dos direcciones", str(bridges["mirrored"])),
            ]
        ),
    ]

    unresolved = [e for e in model.edges + model.back_edges if not e.resolved]
    body.append(f'<h2>{_esc(LABELS["unresolved"])} ({len(unresolved)})</h2>')
    if not unresolved:
        body.append("<p>Ninguna: cada arista llega a una página en los dos extremos.</p>")
    else:
        items = "".join(
            f"<li>{_object_link(model, e.source, root)} → {_object_link(model, e.target, root)}"
            + (f'<br><span class="review" lang="en">{_esc(e.reason)}</span>' if e.reason else "")
            + "</li>\n"
            for e in unresolved
        )
        body.append(
            "<p>Se informan, nunca hacen fallar la construcción — la misma convención que "
            "la arista de vuelta: una reclamación honesta sobre un sólido que nadie ha "
            "construido todavía vale más que un enlace que resuelve por nombre y miente "
            f'sobre la geometría.</p><ul class="plain">\n{items}</ul>'
        )

    claims = model.bridges.get("unlinked_claims") or []
    body.append(f"<h2>Reclamaciones no enlazadas ({len(claims)})</h2>")
    for claim in claims:
        garments = ", ".join(
            _object_link(model, _object_key("fashion-cabinet", g), root)
            for g in claim.get("garments") or []
        )
        body.append(
            f'<h3>{_object_link(model, _object_key("yantra4d", claim["hardware"]), root)}</h3>'
            f'<p>{garments}</p>'
            f'<p class="review" lang="en">{_esc(claim.get("reason", ""))}</p>'
        )

    by_target: dict[str, list[BridgeEdge]] = {}
    for edge in model.back_edges:
        by_target.setdefault(edge.source, []).append(edge)
    body.append(f"<h2>Arista de vuelta ({len(by_target)} sólidos)</h2>")
    rows = []
    for target in sorted(by_target):
        consumers = "".join(
            f'<a href="{_esc(_object_href(e.target, root))}">'
            f'{_esc(e.target.split("/", 1)[1])}</a> '
            for e in by_target[target]
        )
        rows.append(
            f"<tr><td>{_object_link(model, target, root)}</td>"
            f"<td>{len(by_target[target])}</td><td>{consumers}</td></tr>"
        )
    body.append(
        "<table>\n<thead><tr><th>sólido</th><th>n</th><th>prendas</th></tr></thead>\n"
        f"<tbody>\n{chr(10).join(rows)}\n</tbody>\n</table>"
    )

    return _document(
        title=f"Puentes — {_chrome('reader')}",
        root=root,
        main="\n".join(body),
        provenance=_provenance(model, root),
    )


def _home(model: ReaderModel) -> str:
    root = ""
    counts = reader_counts(model)
    body = [
        f"<h1>{_esc(_chrome('reader'))}</h1>",
        '<p class="lede">Un léxico, dos enciclopedias, y el grafo de puentes como '
        "navegación entre ellas (RFC 0039 G4). Todo se construye de instantáneas fijadas "
        "en este repositorio: sin red, sin checkout de plataforma, sin JavaScript.</p>",
        "<h2>Capas</h2>",
        f'<ul class="plain">'
        f'<li><a href="terms/index.html">{_esc(_chrome("terms"))}</a> — '
        f'{counts["terms"]["total"]} términos cuadrilingües, el diccionario compartido.</li>'
        f'<li><a href="yantra4d/index.html">Yantra4D</a> — '
        f'{counts["catalog"]["yantra4d"]["entries"]} entradas del procomún sólido.</li>'
        f'<li><a href="fashion-cabinet/index.html">Fashion Cabinet</a> — '
        f'{counts["catalog"]["fashion-cabinet"]["entries"]} entradas del procomún textil.</li>'
        f'<li><a href="bridges.html">Puentes</a> — {counts["bridges"]["edges"]} aristas '
        f'declaradas, {counts["bridges"]["resolved"]} con página en ambos extremos, '
        f'{counts["bridges"]["unresolved"]} sin resolver.</li></ul>',
        "<h2>Lo que este lector no hace</h2>",
        "<p>No copia ningún artículo. El cuerpo de cada objeto vive en el "
        '<span class="mono">docs/README.md</span> de su propio procomún y es fuente única '
        "(RFC 0039 §2); aquí sólo se enlaza, fijado al commit capturado. Tampoco ofrece un "
        "idioma que la entrada no tenga: el léxico es cuadrilingüe por su puerta de "
        "publicación, los catálogos todavía no, y la deuda se ve en lugar de taparse.</p>",
        "<h2>Cobertura de idiomas</h2>",
    ]
    rows = []
    for label, tally in (
        ("términos", counts["terms"]["languages"]),
        ("yantra4d", counts["catalog"]["yantra4d"]["languages"]),
        ("fashion-cabinet", counts["catalog"]["fashion-cabinet"]["languages"]),
    ):
        cells = "".join(f"<td>{tally[lang]}</td>" for lang in LANGUAGES)
        rows.append(f"<tr><td>{_esc(label)}</td>{cells}</tr>")
    heads = "".join(f"<th>{lang}</th>" for lang in LANGUAGES)
    body.append(
        f"<table>\n<thead><tr><th>capa</th>{heads}</tr></thead>\n<tbody>\n"
        f"{chr(10).join(rows)}\n</tbody>\n</table>"
    )
    if model.dangling_embodied_by:
        items = "".join(f"<li>{_esc(p)}</li>" for p in model.dangling_embodied_by)
        body.append(
            f'<h2>{_esc(LABELS["unresolved"])}</h2>'
            f"<p>Referencias del léxico sin página en estas instantáneas. Se informan, "
            f'nunca hacen fallar la construcción.</p><ul>{items}</ul>'
        )
    return _document(
        title=_chrome("reader"),
        root=root,
        main="\n".join(body),
        provenance=_provenance(model, root),
    )


# ── build and check ──────────────────────────────────────────────────────────


def render(model: ReaderModel | None = None) -> dict[str, str]:
    """The whole reader as ``{relative path: text}``. Pure: no disk, no clock.

    Being a mapping rather than a directory is what makes ``--check`` cheap and exact —
    the check renders the same thing and compares, so there is no second code path that
    could drift from the build.
    """
    model = load_model() if model is None else model

    files: dict[str, str] = {
        "style.css": STYLESHEET,
        "index.html": _home(model),
        "bridges.html": _bridges_page(model),
        "terms/index.html": _terms_index(model),
        "summary.json": json.dumps(reader_counts(model), indent=2, ensure_ascii=False)
        + "\n",
    }
    for term_id in sorted(model.terms):
        files[f"terms/{term_id}.html"] = _term_page(model, term_id)
    for repo in REPOS:
        files[f"{repo}/index.html"] = _catalog_index(model, repo)
    for key in sorted(model.entries):
        repo, slug = key.split("/", 1)
        files[f"{repo}/{slug}.html"] = _entry_page(model, key)
    return files


def _existing(dest: Path) -> set[str]:
    return {
        p.relative_to(dest).as_posix() for p in sorted(dest.rglob("*")) if p.is_file()
    }


def build(dest: str | Path, model: ReaderModel | None = None) -> dict[str, str]:
    """Write the reader to ``dest``, removing anything there that the build did not
    produce. An output directory that keeps a stale page is an output directory whose
    ``--check`` would pass on a lie."""
    dest = Path(dest)
    files = render(model)
    dest.mkdir(parents=True, exist_ok=True)
    for rel in sorted(_existing(dest) - set(files)):
        (dest / rel).unlink()
    for rel, text in sorted(files.items()):
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for directory in sorted(
        (p for p in dest.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)
    ):
        if not any(directory.iterdir()):
            directory.rmdir()
    return files


def check(dest: str | Path, model: ReaderModel | None = None) -> list[str]:
    """What differs between the committed reader and a rebuild. Empty means identical.

    Fails closed by construction: a missing directory, an absent page, a page nobody
    generates and a page whose bytes moved are all problems. The alternative — checking
    only the files that happen to exist — would pass an output directory that had been
    emptied.
    """
    dest = Path(dest)
    if not dest.is_dir():
        return [f"{dest}: no built reader here — run the build with --out {dest}"]
    files = render(model)
    found = _existing(dest)
    problems = [f"missing: {rel}" for rel in sorted(set(files) - found)]
    problems += [f"unexpected: {rel}" for rel in sorted(found - set(files))]
    for rel in sorted(set(files) & found):
        try:
            current = (dest / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"unreadable: {rel} — {exc}")
            continue
        if current != files[rel]:
            problems.append(f"stale: {rel}")
    return problems
