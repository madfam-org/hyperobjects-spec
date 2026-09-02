"""The controlled vocabularies: the KEYS both commons write, as checkable data.

Where the lexicon defines words, a vocabulary defines identifiers — the literal strings
a manifest carries. Two documents ship, one per vocabulary:

* ``vocabularies/interfaces.json`` — both commons' interface names. Each repo's type set
  is already a closed enum in its own schema, so the drift is not inside a repo but
  ACROSS the two: RFC 0038 §5 B2's ``zipper_tape`` against ``tape_edge``. Those pairs are
  recorded as explicit ``equivalent_to`` edges, and the pair that merely LOOKS like one
  (``pocket`` on both sides, meaning opposite things) as ``distinct_from``.
* ``vocabularies/capabilities.json`` — Fashion Cabinet's ``hyperobject.capabilities``
  keys. The garment manifest types that block as ``additionalProperties: boolean``, so
  every key is legal and none is defined; 516 cartridges wrote 134 distinct ones. This
  is the missing enum, assembled additively: every observed key is present, near
  duplicates canonicalise through ``aliases``, narrower claims hang off their broader key
  through ``narrower_than``, and nothing existing is invalidated.

What the lane checks, and why each rule is here
-----------------------------------------------
1. **Schema-valid** against ``commons-vocabulary.schema.json``.
2. **(repo, key) is unique** — the same key can be real in both repos, and inside one repo
   it can only mean one thing.
3. **``term`` resolves** in the lexicon, and **a key two or more cartridges use HAS one**.
   That is the rule that keeps the vocabulary quadrilingual where it is actually used: a
   key with a term inherits four languages, and a key without one is a single English
   gloss at best.
4. **Nothing is undefined by accident** — every entry carries a term, a gloss, or an
   explicit ``needs_definition``. The flag exists so the honest state is countable.
5. **An alias is not canonical** — an alias name may not also be an entry key in the same
   repo, or the rewrite it asks for would be circular.
6. **Equivalences are cross-repo and symmetric.** Two spellings of one thing inside a
   single repo are an alias; across repos they are an equivalence, and an edge one side
   declares and the other does not is a half-recorded dialect split.
7. **``distinct_from`` is symmetric too, and carries its reason.** A false-friend pair is
   only protected if BOTH entries say so — a de-duplication pass reading one entry must
   find the warning.
8. **``narrower_than`` resolves and does not cycle.**
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from hyperobjects_schemas import load as load_schema

from .lexicon import load_lexicon

__all__ = [
    "VOCABULARY_DIR",
    "VOCABULARIES",
    "VocabularyResult",
    "check_vocabularies",
    "check_vocabulary",
    "canonical_key",
    "equivalences",
    "load_vocabularies",
    "load_vocabulary",
    "vocabulary_status",
]

SCHEMA_NAME = "commons-vocabulary"

#: Where the bundled vocabularies live inside the installed package.
VOCABULARY_DIR = "hyperobjects_lexicon.vocabularies"

#: The vocabularies this package ships. The filename IS the vocabulary name.
VOCABULARIES: tuple[str, ...] = ("interfaces", "capabilities")

#: A key used by at least this many cartridges must carry a lexicon term.
TERM_REQUIRED_AT = 2


@dataclass
class VocabularyResult:
    """The verdict on the vocabularies. Falsey when there are problems."""

    entries: int
    ok: bool
    problems: list[str] = field(default_factory=list)
    vocabularies: int = 0

    def __bool__(self) -> bool:
        return self.ok


def load_vocabulary(name_or_path: str | Path) -> dict:
    """Load one vocabulary document — a bundled name, or a path to a file."""
    if isinstance(name_or_path, str) and name_or_path in VOCABULARIES:
        with resources.files(VOCABULARY_DIR).joinpath(
            f"{name_or_path}.json"
        ).open(encoding="utf-8") as f:
            return json.load(f)
    return json.loads(Path(name_or_path).read_text(encoding="utf-8"))


def load_vocabularies(directory: str | Path | None = None) -> dict[str, dict]:
    """Load every vocabulary as ``{name: document}``.

    With no argument, loads the ones bundled with this package. The key is the filename
    stem; ``check_vocabularies`` is what asserts the document's declared ``vocabulary``
    agrees with it.
    """
    if directory is None:
        return {name: load_vocabulary(name) for name in VOCABULARIES}
    paths = sorted(Path(directory).glob("*.json"))
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in paths}


def _schema_errors(doc: object) -> list[str]:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(load_schema(SCHEMA_NAME))
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"{where}: {err.message}")
    return out


def _ref(entry: dict) -> tuple[str, str]:
    return (entry.get("repo"), entry.get("key"))


def _index(docs: dict[str, dict]) -> dict[tuple[str, str], dict]:
    """Every entry of every vocabulary, addressed by (repo, key).

    The index spans documents on purpose: an equivalence between an interface type and an
    interface id lives in one file today, but nothing in the model requires that, and a
    cross-file edge should resolve rather than silently dangle.
    """
    out: dict[tuple[str, str], dict] = {}
    for doc in docs.values():
        for entry in doc.get("entries") or []:
            if isinstance(entry, dict):
                out.setdefault(_ref(entry), entry)
    return out


def check_vocabulary(
    doc: dict,
    *,
    name: str | None = None,
    known_terms: set[str] | None = None,
    index: dict[tuple[str, str], dict] | None = None,
) -> list[str]:
    """Check one vocabulary document. Returns its problems (empty means it conforms)."""
    problems = _schema_errors(doc)
    if not isinstance(doc, dict):
        return problems or ["not an object"]

    declared = doc.get("vocabulary")
    if name is not None and declared != name:
        problems.append(
            f"declares vocabulary {declared!r} in a file named {name!r} — the filename is "
            f"how the document is addressed, so the two must agree"
        )

    review = doc.get("review") or {}
    if review.get("state") == "reviewed" and not review.get("reviewers"):
        problems.append(
            "review: state is 'reviewed' with no reviewers — a canonicalisation nobody "
            "signed is a proposal, not a ruling (RFC 0039 §5)"
        )

    entries = doc.get("entries") or []
    seen: dict[tuple[str, str], int] = {}
    alias_names: dict[tuple[str, str], str] = {}

    for pos, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        ref = _ref(entry)
        key = f"{ref[0]}/{ref[1]}"
        if ref in seen:
            problems.append(
                f"{key}: declared twice (entries {seen[ref]} and {pos}) — one key means "
                f"one thing in one repo"
            )
        seen[ref] = pos

        has_meaning = entry.get("term") or entry.get("gloss") or entry.get("needs_definition")
        if not has_meaning:
            problems.append(
                f"{key}: no term, no gloss and no needs_definition — an entry that says "
                f"nothing about what the key means is a key nobody can adopt"
            )

        uses = (entry.get("observed") or {}).get("cartridges", 0)
        if uses >= TERM_REQUIRED_AT and not entry.get("term"):
            problems.append(
                f"{key}: used by {uses} cartridges with no lexicon term — a key this "
                f"widely written is vocabulary the commons reads, and it ships "
                f"quadrilingual or not at all (RFC 0039 §7)"
            )

        if known_terms is not None and entry.get("term") and entry["term"] not in known_terms:
            problems.append(
                f"{key}: term {entry['term']!r} is not in the lexicon — a vocabulary "
                f"pointing at a definition that does not exist is worse than one pointing "
                f"at nothing"
            )

        for alias in entry.get("aliases") or []:
            aref = (alias.get("repo"), alias.get("name"))
            if aref in alias_names:
                problems.append(
                    f"{alias.get('repo')}/{alias.get('name')}: aliased by both "
                    f"{alias_names[aref]} and {key} — a spelling canonicalises onto one key"
                )
            alias_names[aref] = key
            if aref == ref:
                problems.append(f"{key}: aliases itself")

    for ref, owner in alias_names.items():
        if ref in seen:
            problems.append(
                f"{ref[0]}/{ref[1]}: is an alias of {owner} AND an entry of its own — an "
                f"alias asks a consumer to rewrite the spelling, and rewriting it onto a "
                f"key that also stands alone is circular"
            )

    if index is None:
        return problems

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ref = _ref(entry)
        key = f"{ref[0]}/{ref[1]}"

        for edge in entry.get("equivalent_to") or []:
            target = (edge.get("repo"), edge.get("key"))
            other = index.get(target)
            if other is None:
                problems.append(
                    f"{key}: equivalent_to {target[0]}/{target[1]} does not resolve"
                )
                continue
            if target[0] == ref[0]:
                problems.append(
                    f"{key}: equivalent_to {target[0]}/{target[1]} is in the SAME repo — "
                    f"two spellings of one thing inside one repo are an alias, not an "
                    f"equivalence"
                )
            back = {(e.get("repo"), e.get("key")) for e in other.get("equivalent_to") or []}
            if ref not in back:
                problems.append(
                    f"{key}: equivalent_to {target[0]}/{target[1]}, which does not point "
                    f"back — a dialect split recorded on one side only is half a record"
                )

        for edge in entry.get("distinct_from") or []:
            target = (edge.get("repo"), edge.get("key"))
            other = index.get(target)
            if other is None:
                problems.append(
                    f"{key}: distinct_from {target[0]}/{target[1]} does not resolve"
                )
                continue
            back = {(e.get("repo"), e.get("key")) for e in other.get("distinct_from") or []}
            if ref not in back:
                problems.append(
                    f"{key}: distinct_from {target[0]}/{target[1]}, which does not say so "
                    f"in return — a false-friend pair only protects the reader who arrives "
                    f"at either half"
                )

        narrower = entry.get("narrower_than")
        if narrower:
            target = (narrower.get("repo"), narrower.get("key"))
            if target == ref:
                problems.append(f"{key}: narrower_than itself")
            elif target not in index:
                problems.append(
                    f"{key}: narrower_than {target[0]}/{target[1]} does not resolve"
                )
            else:
                # Walk up; a cycle here would make a consumer's generalisation loop.
                seen_chain = {ref}
                cur = target
                while cur is not None and cur in index:
                    if cur in seen_chain:
                        problems.append(
                            f"{key}: narrower_than forms a cycle through "
                            f"{cur[0]}/{cur[1]}"
                        )
                        break
                    seen_chain.add(cur)
                    nxt = index[cur].get("narrower_than")
                    cur = (nxt.get("repo"), nxt.get("key")) if nxt else None

    return problems


def check_vocabularies(
    docs: dict[str, dict] | None = None,
    *,
    lexicon: dict[str, dict] | None = None,
) -> VocabularyResult:
    """Check every vocabulary, plus the cross-document edges between them."""
    if docs is None:
        docs = load_vocabularies()
    if lexicon is None:
        lexicon = load_lexicon()

    known_terms = set(lexicon)
    index = _index(docs)
    problems: list[str] = []
    entries = 0

    for name in sorted(docs):
        doc = docs[name]
        entries += len(doc.get("entries") or []) if isinstance(doc, dict) else 0
        for prob in check_vocabulary(
            doc, name=name, known_terms=known_terms, index=index
        ):
            problems.append(f"{name}: {prob}")

    return VocabularyResult(
        entries=entries,
        ok=not problems,
        problems=problems,
        vocabularies=len(docs),
    )


def canonical_key(
    name: str,
    *,
    vocabulary: str = "capabilities",
    repo: str = "fashion-cabinet",
) -> str:
    """The spelling to write, for a key a manifest already carries.

    Returns ``name`` unchanged when it is already canonical or unknown — a vocabulary
    that renamed keys it has never seen would be a worse problem than the drift it is
    fixing. This is the call a platform's compliance lane makes.
    """
    doc = load_vocabulary(vocabulary)
    for entry in doc.get("entries") or []:
        if entry.get("repo") != repo:
            continue
        if entry.get("key") == name:
            return name
        for alias in entry.get("aliases") or []:
            if alias.get("name") == name and alias.get("repo") == repo:
                return entry["key"]
    return name


def equivalences(docs: dict[str, dict] | None = None) -> list[tuple[str, str]]:
    """Every cross-commons equivalence, as sorted ``('repo/key', 'repo/key')`` pairs.

    One tuple per pair rather than one per direction — the lane already proved the edges
    are symmetric, so a reader wants the pair.
    """
    if docs is None:
        docs = load_vocabularies()
    pairs = set()
    for doc in docs.values():
        for entry in doc.get("entries") or []:
            a = f"{entry.get('repo')}/{entry.get('key')}"
            for edge in entry.get("equivalent_to") or []:
                b = f"{edge.get('repo')}/{edge.get('key')}"
                pairs.add(tuple(sorted((a, b))))
    return sorted(pairs)


def vocabulary_status(docs: dict[str, dict] | None = None) -> list[str]:
    """One N/M line per vocabulary, in the house style.

    Every number on the line is a fact about the same corpus, and the ones that look bad
    are the point: `needs_definition` counts the keys nobody has defined yet, and it is
    on the line precisely so it cannot be mistaken for zero.
    """
    if docs is None:
        docs = load_vocabularies()
    lines = []
    for name in sorted(docs):
        entries = docs[name].get("entries") or []
        termed = sum(1 for e in entries if e.get("term"))
        glossed = sum(1 for e in entries if not e.get("term") and e.get("gloss"))
        undefined = sum(1 for e in entries if e.get("needs_definition"))
        aliases = sum(len(e.get("aliases") or []) for e in entries)
        equiv = sum(len(e.get("equivalent_to") or []) for e in entries) // 2
        distinct = sum(len(e.get("distinct_from") or []) for e in entries) // 2
        provisional = sum(1 for e in entries if e.get("status") == "provisional")
        review = (docs[name].get("review") or {}).get("state", "unmarked")
        lines.append(
            f"vocabulary_status[{name}]: entries={len(entries)} "
            f"term={termed} gloss={glossed} undefined={undefined} "
            f"aliases={aliases} equivalences={equiv} distinct_pairs={distinct} "
            f"provisional={provisional} review={review}"
        )
    return lines
