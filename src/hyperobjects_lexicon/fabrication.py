"""The fabrication vocabularies (SEM-1 §4): the KEYS a manifest's fabrication fields write.

Five documents ship under ``vocabularies/fabrication/``, one per vocabulary:

* ``processes`` — how a part is made (``fff``, ``sla``, ``sls``, ``mjf``, ``cnc_3axis``,
  ``cnc_router``, ``laser_2d``), each mapped to Cotiza's process code where Cotiza has one.
* ``material-classes`` — what it is made of (``pla``, ``tpu-95a``, ``pa12`` … and the six
  Fashion Cabinet fabric classes), each listing the commons' material cards that belong to it
  and the EMMO class those cards record.
* ``process-parameters`` — the slicer settings a requirement profile bounds, every one an
  OrcaSlicer key pinned to the line of ``PrintConfig.cpp`` that defines it.
* ``fabrication-capabilities`` — what a producer MACHINE declares (build volume, nozzle
  range, enclosure, firmware, connectivity). Not the garment ``capabilities`` vocabulary.
* ``interface-sizes`` — the size keys two mating interfaces must share, every dimension
  citing a public standard or manufacturer source.

Why a sibling of ``vocabulary.py`` and not more of it
----------------------------------------------------
The commons vocabularies are READINGS of a corpus: keys the two commons already write, with
how many cartridges write them, an English gloss, and a pointer at a lexicon term for the
four languages. These are REFERENCE lists: no manifest writes them yet, each entry carries
its own quadrilingual label and definition, and the facts in it are cited rather than
counted. Forcing them into ``commons-vocabulary.schema.json`` would have meant a ``repo``
they do not have, snake_case keys their outside world does not use (``tpu-95a``,
``stack-30.5x30.5-m3``), and an English-only gloss where RFC 0039 asks for four languages —
so they get ``fabrication-vocabulary.schema.json`` and this lane.

What the lane checks
--------------------
1. Schema-valid against ``fabrication-vocabulary.schema.json``; the file name is the
   vocabulary it declares.
2. Keys are unique; labels and definitions are present and non-blank in es/en/fr/pt.
3. Review claims are honest — ``reviewed`` needs a named reviewer and no ``generated``
   language facet (the same rule as a lexicon term).
4. Cross-references resolve: ``term`` in the lexicon, ``processes`` in ``processes``,
   ``cards`` in the bundled catalog snapshot, ``geometry_type`` in the ``interfaces``
   vocabulary, ``value_vocabulary`` in this family.
5. Facts are cited: every dimension names a source index that exists, a material class
   other than a fabric names the processes it is made by, an enumerated capability cites
   its values, and an OrcaSlicer binding is the entry's own key at a revision a source URL
   carries.
6. Nothing is claimed twice: a card belongs to one class, a Cotiza code to one process, an
   identifier is not both an exact and a close match, and no machine-capability key is
   also a garment capability key.

A key's concept IRI is derived, never stored: ``entry_concept_iri(vocabulary, key)`` →
``https://id.madfam.io/concept/{vocabulary}/{key}``. Term ids are kebab-case and contain no
``/``, so these can never collide with a term's ``https://id.madfam.io/concept/{id}``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from hyperobjects_schemas import load as load_schema

from .lexicon import CONCEPT_NAMESPACE, LANGUAGES, load_lexicon

__all__ = [
    "FABRICATION_VOCABULARIES",
    "FabricationResult",
    "check_fabrication_vocabularies",
    "check_fabrication_vocabulary",
    "entry_concept_iri",
    "fabrication_status",
    "load_fabrication_vocabularies",
    "load_fabrication_vocabulary",
    "vocabulary_keys",
]

SCHEMA_NAME = "fabrication-vocabulary"

#: The bundled documents, in dependency order (processes first: the others point at it).
FABRICATION_VOCABULARIES: tuple[str, ...] = (
    "processes",
    "material-classes",
    "process-parameters",
    "fabrication-capabilities",
    "interface-sizes",
)

_DIR = "vocabularies/fabrication"


@dataclass
class FabricationResult:
    """The verdict on the fabrication vocabularies. Falsey when there are problems."""

    entries: int
    ok: bool
    problems: list[str] = field(default_factory=list)
    vocabularies: int = 0

    def __bool__(self) -> bool:
        return self.ok


def _merge_supplements(name: str, base: dict | None, supplements: list[dict]) -> dict:
    """A vocabulary's base document with its supplements' entries appended, in file order.

    A supplement is a whole document of the SAME vocabulary in ``{name}.{label}.json`` —
    how one vocabulary grows past a file size a reviewer can read without splitting the
    vocabulary itself (the standard-parts catalog's interface sizes live in
    ``interface-sizes.standard-parts.json``). Only its ``entries`` are used; a supplement
    that declares another vocabulary is an error here rather than a silent merge.
    """
    for sup in supplements:
        if not isinstance(sup, dict) or sup.get("vocabulary") != name:
            declared = sup.get("vocabulary") if isinstance(sup, dict) else None
            raise ValueError(f"a supplement of {name!r} declares vocabulary {declared!r}")
    if base is None:
        if not supplements:
            raise ValueError(f"no document for vocabulary {name!r}")
        base, supplements = supplements[0], supplements[1:]
    if not supplements:
        return base
    merged = dict(base)
    merged["entries"] = list(base.get("entries") or [])
    for sup in supplements:
        merged["entries"].extend(sup.get("entries") or [])
    return merged


def load_fabrication_vocabulary(name_or_path: str | Path) -> dict:
    """Load one document — a bundled vocabulary name (with its supplements merged in), or a
    path to a file (read as is)."""
    if isinstance(name_or_path, str) and name_or_path in FABRICATION_VOCABULARIES:
        folder = resources.files("hyperobjects_lexicon").joinpath(_DIR)
        base = json.loads(folder.joinpath(f"{name_or_path}.json").read_text(encoding="utf-8"))
        supplements = [
            json.loads(ref.read_text(encoding="utf-8"))
            for ref in sorted(folder.iterdir(), key=lambda r: r.name)
            if ref.name.startswith(f"{name_or_path}.") and ref.name != f"{name_or_path}.json"
            and ref.name.endswith(".json")
        ]
        return _merge_supplements(name_or_path, base, supplements)
    return json.loads(Path(name_or_path).read_text(encoding="utf-8"))


def load_fabrication_vocabularies(directory: str | Path | None = None) -> dict[str, dict]:
    """Load every document as ``{name: document}`` — bundled, or every ``*.json`` in a dir.

    In a directory, ``{name}.{label}.json`` is a supplement of ``{name}`` and is merged into
    it, exactly as the bundled set is read.
    """
    if directory is None:
        return {name: load_fabrication_vocabulary(name) for name in FABRICATION_VOCABULARIES}
    groups: dict[str, dict] = {}
    for path in sorted(Path(directory).glob("*.json")):
        name = path.stem.split(".", 1)[0]
        group = groups.setdefault(name, {"base": None, "supplements": []})
        doc = json.loads(path.read_text(encoding="utf-8"))
        if path.stem == name:
            group["base"] = doc
        else:
            group["supplements"].append(doc)
    return {
        name: _merge_supplements(name, group["base"], group["supplements"])
        for name, group in groups.items()
    }


def vocabulary_keys(name: str, docs: dict[str, dict] | None = None) -> set[str]:
    """The key set of one fabrication vocabulary (bundled unless ``docs`` is given)."""
    doc = (docs or {}).get(name) if docs is not None else load_fabrication_vocabulary(name)
    return {
        e["key"]
        for e in (doc or {}).get("entries") or []
        if isinstance(e, dict) and isinstance(e.get("key"), str)
    }


def entry_concept_iri(vocabulary: str, key: str) -> str:
    """The permanent concept IRI of a fabrication-vocabulary key.

    ``https://id.madfam.io/concept/{vocabulary}/{key}``. Raises ``ValueError`` for a
    vocabulary this package does not define, rather than minting an identifier under a
    name nobody owns.
    """
    if vocabulary not in FABRICATION_VOCABULARIES:
        raise ValueError(f"{vocabulary!r} is not a fabrication vocabulary")
    if not isinstance(key, str) or not key or "/" in key or key != key.strip():
        raise ValueError(f"{key!r} is not a vocabulary key")
    return f"{CONCEPT_NAMESPACE}{vocabulary}/{key}"


def _schema_errors(doc: object) -> list[str]:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(load_schema(SCHEMA_NAME))
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"{where}: {err.message}")
    return out


def _blank_languages(block: object, what: str) -> list[str]:
    if not isinstance(block, dict):
        return [f"{what}: not a four-language object"]
    return [
        f"{what}.{lang}: missing or empty — all four languages are required (RFC 0039 §7)"
        for lang in LANGUAGES
        if not isinstance(block.get(lang), str) or not block[lang].strip()
    ]


def _review_problems(block: object, where: str) -> list[str]:
    if not isinstance(block, dict) or block.get("state") != "reviewed":
        return []
    problems = []
    if not block.get("reviewers"):
        problems.append(f"{where}: 'reviewed' with no reviewers — a review nobody signed")
    still = sorted(k for k, v in (block.get("languages") or {}).items() if v == "generated")
    if still:
        problems.append(
            f"{where}: 'reviewed' while {', '.join(still)} still 'generated' — the state is "
            f"the WORST facet"
        )
    return problems


def _entry_problems(entry: dict, name: str, ctx: dict) -> list[str]:
    key = entry.get("key")
    out = _blank_languages(entry.get("label"), "label")
    out += _blank_languages(entry.get("definition"), "definition")
    out += _review_problems(entry.get("review_status"), "review_status")

    term = entry.get("term")
    if term and ctx["terms"] is not None and term not in ctx["terms"]:
        out.append(f"term {term!r} is not in the lexicon")

    exact = {i for i in entry.get("exact_match") or [] if isinstance(i, str)}
    for ident in sorted(exact & set(entry.get("close_match") or [])):
        out.append(f"{ident!r} is in both exact_match and close_match")

    sources = entry.get("sources") or []
    for dim_name, dim in (entry.get("dimensions") or {}).items():
        idx = dim.get("source") if isinstance(dim, dict) else None
        if not isinstance(idx, int) or not 0 <= idx < len(sources):
            out.append(
                f"dimensions.{dim_name}: cites source {idx!r}, but the entry has "
                f"{len(sources)} — an uncited dimension is a guess"
            )

    for proc in entry.get("processes") or []:
        if ctx["processes"] is not None and proc not in ctx["processes"]:
            out.append(f"processes: {proc!r} is not a key of the processes vocabulary")

    if name == "material-classes":
        if entry.get("kind") != "fabric" and not entry.get("processes"):
            out.append("names no processes — a solid material class says how it is made")
        for card in entry.get("cards") or []:
            owner = ctx["card_owner"].setdefault(card, key)
            if owner != key:
                out.append(f"card {card!r} is already in class {owner!r} — one card, one class")
            if ctx["catalog"] is not None and card not in ctx["catalog"]:
                out.append(f"card {card!r} does not resolve against the catalog snapshot")

    if name == "processes" and entry.get("cotiza_code"):
        code = entry["cotiza_code"]
        owner = ctx["cotiza_owner"].setdefault(code, key)
        if owner != key:
            out.append(f"cotiza_code {code!r} is already mapped by {owner!r}")

    binding = entry.get("orcaslicer")
    if isinstance(binding, dict):
        if binding.get("key") != key:
            out.append(
                f"orcaslicer.key {binding.get('key')!r} differs from the entry key — these keys "
                f"ARE OrcaSlicer's, so the two must be the same string"
            )
        rev = binding.get("rev")
        if rev and not any(rev in (s.get("url") or "") for s in sources):
            out.append(f"no source URL is pinned to OrcaSlicer revision {rev}")

    if name == "fabrication-capabilities":
        if key in ctx["garment_capabilities"]:
            out.append(
                "is also a garment capability key (capabilities vocabulary) — a machine "
                "capability and a garment feature must not share a spelling"
            )
        if entry.get("allowed_values") and not sources:
            out.append("enumerates allowed_values with no source for them")

    if name == "interface-sizes":
        gtype = entry.get("geometry_type")
        if ctx["geometry_types"] is not None and gtype not in ctx["geometry_types"]:
            out.append(f"geometry_type {gtype!r} is not a yantra4d geometry_type key")

    return out


def check_fabrication_vocabulary(doc: object, *, name: str | None = None, **ctx) -> list[str]:
    """Check one document. ``ctx`` carries the cross-reference sets (see the module doc);
    a missing set skips that resolution rather than failing it."""
    problems = _schema_errors(doc)
    if not isinstance(doc, dict):
        return problems or ["not an object"]
    declared = doc.get("vocabulary")
    if name is not None and declared != name:
        problems.append(f"declares vocabulary {declared!r} in a file named {name!r}")
    if (doc.get("review") or {}).get("state") == "reviewed" and not doc["review"].get("reviewers"):
        problems.append("review: 'reviewed' with no reviewers")

    ctx = {
        "terms": ctx.get("terms"),
        "processes": ctx.get("processes"),
        "catalog": ctx.get("catalog"),
        "geometry_types": ctx.get("geometry_types"),
        "garment_capabilities": ctx.get("garment_capabilities") or set(),
        "card_owner": {},
        "cotiza_owner": {},
    }
    seen: set[str] = set()
    for entry in doc.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if key in seen:
            problems.append(f"{key}: declared twice — one key means one thing")
        seen.add(key)
        problems.extend(f"{key}: {p}" for p in _entry_problems(entry, declared, ctx))
    return problems


def check_fabrication_vocabularies(
    docs: dict[str, dict] | None = None,
    *,
    lexicon: dict[str, dict] | None = None,
    catalog: set[str] | None = None,
) -> FabricationResult:
    """Check every fabrication vocabulary with its cross-references resolved.

    ``catalog`` defaults to the bundled slug snapshot (so card references are resolved
    hermetically), the lexicon to the bundled corpus, and the interface / capability sets
    to the bundled commons vocabularies.
    """
    from .lexicon import bundled_catalog_slugs
    from .vocabulary import load_vocabularies

    if docs is None:
        docs = load_fabrication_vocabularies()
    if lexicon is None:
        lexicon = load_lexicon()
    if catalog is None:
        catalog = bundled_catalog_slugs()
    commons = load_vocabularies()
    ctx = {
        "terms": set(lexicon),
        "processes": vocabulary_keys("processes", docs) if "processes" in docs else None,
        "catalog": catalog,
        "geometry_types": {
            e.get("key")
            for e in commons.get("interfaces", {}).get("entries") or []
            if e.get("repo") == "yantra4d" and e.get("role") == "geometry_type"
        },
        "garment_capabilities": {
            e.get("key") for e in commons.get("capabilities", {}).get("entries") or []
        },
    }
    problems: list[str] = []
    entries = 0
    for name in sorted(docs):
        doc = docs[name]
        entries += len(doc.get("entries") or []) if isinstance(doc, dict) else 0
        problems.extend(
            f"{name}: {p}" for p in check_fabrication_vocabulary(doc, name=name, **ctx)
        )
    return FabricationResult(
        entries=entries, ok=not problems, problems=problems, vocabularies=len(docs)
    )


def fabrication_status(docs: dict[str, dict] | None = None) -> list[str]:
    """One line per fabrication vocabulary: entries, how many are cited, review state.

    The review clause says ``signed`` / ``draft`` rather than the lexicon's
    ``reviewed=`` / ``generated=`` on purpose: README count checks read those two tokens
    as corpus-wide TERM counts, and a vocabulary's numbers must not be mistaken for them.
    """
    if docs is None:
        docs = load_fabrication_vocabularies()
    lines = []
    for name in FABRICATION_VOCABULARIES:
        if name not in docs:
            continue
        entries = docs[name].get("entries") or []
        cited = sum(1 for e in entries if e.get("sources"))
        facts = sum(len(e.get("dimensions") or {}) for e in entries)
        provisional = sum(1 for e in entries if e.get("status") == "provisional")
        reviewed = sum(
            1 for e in entries if (e.get("review_status") or {}).get("state") == "reviewed"
        )
        lines.append(
            f"fabrication_status[{name}]: entries={len(entries)} cited={cited} "
            f"dimensions={facts} provisional={provisional} "
            f"review: signed={reviewed} draft={len(entries) - reviewed}"
        )
    return lines
