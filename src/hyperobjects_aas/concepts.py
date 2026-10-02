"""ConceptDescriptions for every MADFAM semanticId a projection uses.

Two kinds of MADFAM semanticId exist (SEM-1 §1):

* ``https://id.madfam.io/concept/{term-id}`` — a Commons Lexicon term. The projection
  asks :meth:`Concepts.term` for one and gets an IRI back **only if the term exists in
  the bundled lexicon**, so no element ever points at a concept nobody defined. The
  ConceptDescription is built from the term itself: the four preferred names, the four
  definitions, ``exact_match`` identifiers (when the term carries them) as ``isCaseOf``,
  and a ``unit`` when the term states one.
* ``https://id.madfam.io/smt/{template}/{major}/{minor}`` — a MADFAM submodel template.
  Its ConceptDescription comes from :data:`hyperobjects_aas.templates.MADFAM`.

Both use DataSpecificationIEC61360. The lexicon lane (P3-LEX) owns the terms; this
module only reads them.
"""

from __future__ import annotations

from functools import cache

from hyperobjects_lexicon import load_lexicon

from .elements import PREFERRED_NAME_LIMIT, TEXT_LIMIT, external_ref, lang_strings
from .ids import concept_id, id_short
from .templates import DATA_SPECIFICATION_IEC61360, MADFAM

__all__ = ["Concepts", "bundled_lexicon", "concept_description"]


@cache
def bundled_lexicon() -> dict[str, dict]:
    """The bundled Commons Lexicon, ``{term id: term}`` (cached, read-only)."""
    return load_lexicon()


def _iec61360(preferred: object, definition: object, unit: object = None) -> dict:
    content: dict = {
        "modelType": "DataSpecificationIec61360",
        "preferredName": lang_strings(preferred, PREFERRED_NAME_LIMIT),
    }
    definitions = lang_strings(definition, TEXT_LIMIT)
    if definitions:
        content["definition"] = definitions
    if isinstance(unit, str) and unit.strip():
        content["unit"] = unit
    return {
        "dataSpecification": external_ref(DATA_SPECIFICATION_IEC61360),
        "dataSpecificationContent": content,
    }


def concept_description(iri: str, short: str, preferred: object, definition: object,
                        unit: object = None, is_case_of: tuple[str, ...] = ()) -> dict:
    cd: dict = {
        "modelType": "ConceptDescription",
        "id": iri,
        "idShort": id_short(short, "Concept"),
        "embeddedDataSpecifications": [_iec61360(preferred, definition, unit)],
    }
    if is_case_of:
        cd["isCaseOf"] = [external_ref(i) for i in is_case_of]
    return cd


class Concepts:
    """Collects the MADFAM semanticIds one projection uses, then describes them."""

    def __init__(self, lexicon: dict[str, dict] | None = None) -> None:
        self._lexicon = bundled_lexicon() if lexicon is None else lexicon
        self._terms: set[str] = set()
        self._templates: set[str] = set()

    def term(self, term_id: object) -> str | None:
        """The concept IRI of a lexicon term, recorded as used — or None if the bundled
        lexicon has no such term (the element then carries no semanticId)."""
        if not isinstance(term_id, str) or term_id not in self._lexicon:
            return None
        self._terms.add(term_id)
        return concept_id(term_id)

    def template(self, name: str) -> None:
        self._templates.add(name)

    def descriptions(self) -> list[dict]:
        """One ConceptDescription per used id, sorted by id (deterministic)."""
        out = []
        for term_id in self._terms:
            term = self._lexicon[term_id]
            exact = tuple(
                i for i in term.get("exact_match", []) or [] if isinstance(i, str) and i
            )
            out.append(
                concept_description(
                    concept_id(term_id), term_id, term.get("term"), term.get("definition"),
                    term.get("unit"), exact,
                )
            )
        for name in self._templates:
            t = MADFAM[name]
            out.append(concept_description(t.id, name, t.preferred_name, t.definition))
        return sorted(out, key=lambda cd: cd["id"])
