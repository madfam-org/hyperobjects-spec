"""Plain-dict builders for the AAS v3.1 JSON serialization.

No SDK at runtime: every builder returns the JSON object the metamodel's ``aas.json``
describes, and drops absent optional fields instead of writing ``null`` or an empty
array (the schema forbids both — every optional array has ``minItems: 1``). Values are
always strings in the JSON serialization; :func:`xsd` picks the value type and the
lexical form together so the two can never disagree.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping

__all__ = [
    "NAME_LIMIT",
    "annotated_relationship",
    "blob",
    "capability",
    "PREFERRED_NAME_LIMIT",
    "TEXT_LIMIT",
    "entity",
    "external_ref",
    "lang_strings",
    "mlp",
    "model_ref",
    "prop",
    "qualifier",
    "range_element",
    "reference_element",
    "relationship",
    "smc",
    "sml",
    "xsd",
]

#: LangStringTextType (descriptions, MultiLanguageProperty values, IEC 61360 definitions).
TEXT_LIMIT = 1023
#: LangStringNameType (displayName).
NAME_LIMIT = 128
#: LangStringPreferredNameTypeIec61360.
PREFERRED_NAME_LIMIT = 255

_LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{1,8})*$")
_ELLIPSIS = "…"


def _truncate(text: str, limit: int) -> str:
    """Cut ``text`` to ``limit`` characters at a word boundary, marked with an ellipsis.

    Truncation is visible by construction: a cut string always ends in ``…``.
    """
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    space = head.rfind(" ")
    if space > limit // 2:
        head = head[:space]
    return head.rstrip() + _ELLIPSIS


def lang_strings(value: object, limit: int = TEXT_LIMIT, default_lang: str = "en") -> list[dict]:
    """``[{"language", "text"}]`` from an i18n dict (or a bare string, tagged
    ``default_lang``). Languages are emitted in sorted order; empty texts and
    non-BCP-47-shaped keys are skipped. Over-long texts are truncated (see
    :func:`_truncate`)."""
    if isinstance(value, str):
        value = {default_lang: value}
    if not isinstance(value, Mapping):
        return []
    out = []
    for lang in sorted(value):
        text = value[lang]
        if not isinstance(lang, str) or not _LANG.match(lang):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        out.append({"language": lang, "text": _truncate(text, limit)})
    return out


def _number_lexical(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    if value.is_integer() and abs(value) < 2**53:
        return str(int(value))
    return repr(value)


def xsd(value: object, prefer: str | None = None) -> tuple[str, str] | None:
    """``(valueType, lexical)`` for a JSON scalar, or None when it has no value.

    ``prefer`` is honoured only when the value fits it (an integer for ``xs:double``, an
    integral number for ``xs:integer``, a string for ``xs:anyURI``); otherwise the type
    follows the value. Non-finite numbers return None — the lexical spaces the projection
    uses never need them, and GOC-1 canonical JSON forbids them. Lists and objects are
    carried as their canonical JSON text in ``xs:string``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "xs:boolean", "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        is_integral = isinstance(value, int) or value.is_integer()
        if prefer == "xs:integer" and is_integral:
            return "xs:integer", str(int(value))
        if prefer == "xs:integer" or prefer == "xs:double" or not isinstance(value, int):
            return "xs:double", _number_lexical(value)
        return "xs:integer", str(value)
    if isinstance(value, str):
        if prefer == "xs:anyURI":
            return "xs:anyURI", value
        return "xs:string", value
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "xs:string", text


def external_ref(iri: str) -> dict:
    """An ExternalReference with one GlobalReference key (a semanticId or asset id)."""
    return {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": iri}]}


def model_ref(keys: Iterable[tuple[str, str]]) -> dict:
    """A ModelReference: ``[(KeyType, value), ...]`` from the Identifiable down."""
    return {"type": "ModelReference", "keys": [{"type": t, "value": v} for t, v in keys]}


def _base(
    model_type: str,
    id_short: str | None,
    semantic_id: str | None = None,
    description: object = None,
    supplemental: Iterable[str] = (),
    qualifiers: Iterable[dict] = (),
) -> dict:
    el: dict = {"modelType": model_type}
    if id_short is not None:
        el["idShort"] = id_short
    if semantic_id:
        el["semanticId"] = external_ref(semantic_id)
    supp = [external_ref(s) for s in supplemental]
    if supp:
        el["supplementalSemanticIds"] = supp
    desc = lang_strings(description) if description is not None else []
    if desc:
        el["description"] = desc
    quals = list(qualifiers)
    if quals:
        el["qualifiers"] = quals
    return el


def prop(
    id_short: str | None,
    value: object,
    *,
    prefer: str | None = None,
    semantic_id: str | None = None,
    description: object = None,
    qualifiers: Iterable[dict] = (),
) -> dict | None:
    """A Property, or None when ``value`` has no representable value."""
    typed = xsd(value, prefer)
    if typed is None:
        return None
    el = _base("Property", id_short, semantic_id, description, qualifiers=qualifiers)
    el["valueType"], el["value"] = typed
    return el


def mlp(
    id_short: str | None,
    value: object,
    *,
    semantic_id: str | None = None,
    default_lang: str = "en",
) -> dict | None:
    """A MultiLanguageProperty, or None when there is no text in any language."""
    texts = lang_strings(value, TEXT_LIMIT, default_lang)
    if not texts:
        return None
    el = _base("MultiLanguageProperty", id_short, semantic_id)
    el["value"] = texts
    return el


def range_element(
    id_short: str, low: object, high: object, *, prefer: str = "xs:double"
) -> dict | None:
    """A Range over two numbers, or None unless both bounds are finite numbers."""
    lo, hi = xsd(low, prefer), xsd(high, prefer)
    if lo is None or hi is None or lo[0] != hi[0] or lo[0] not in ("xs:double", "xs:integer"):
        return None
    el = _base("Range", id_short)
    el["valueType"], el["min"], el["max"] = lo[0], lo[1], hi[1]
    return el


def _children(elements: Iterable[dict | None]) -> list[dict]:
    return [e for e in elements if e is not None]


def smc(
    id_short: str | None,
    elements: Iterable[dict | None],
    *,
    semantic_id: str | None = None,
    description: object = None,
    supplemental: Iterable[str] = (),
) -> dict | None:
    """A SubmodelElementCollection, or None when it would be empty."""
    value = _children(elements)
    if not value:
        return None
    el = _base("SubmodelElementCollection", id_short, semantic_id, description, supplemental)
    el["value"] = value
    return el


def sml(
    id_short: str,
    elements: Iterable[dict | None],
    *,
    type_value: str,
    value_type: str | None = None,
    semantic_id: str | None = None,
    semantic_id_list_element: str | None = None,
) -> dict | None:
    """A SubmodelElementList, or None when it would be empty.

    Children must not carry an idShort (AASd-120); a child built with one has it
    removed here. A list of Properties must declare one ``valueTypeListElement`` that
    every child shares (AASd-109): ``value_type`` when given and every child has it,
    else the children's common type, else every child is carried as ``xs:string`` (its
    lexical form is unchanged, and every lexical form is a valid string).
    """
    value = []
    for child in _children(elements):
        child = dict(child)
        child.pop("idShort", None)
        value.append(child)
    if not value:
        return None
    el = _base("SubmodelElementList", id_short, semantic_id)
    el["orderRelevant"] = True
    if semantic_id_list_element:
        el["semanticIdListElement"] = external_ref(semantic_id_list_element)
    el["typeValueListElement"] = type_value
    if type_value == "Property":
        types = {c.get("valueType") for c in value}
        common = value_type if types == {value_type} else (types.pop() if len(types) == 1 else None)
        if common is None:
            common = "xs:string"
            for c in value:
                c["valueType"] = common
        el["valueTypeListElement"] = common
    el["value"] = value
    return el


def reference_element(
    id_short: str | None, reference: dict, *, semantic_id: str | None = None
) -> dict:
    el = _base("ReferenceElement", id_short, semantic_id)
    el["value"] = reference
    return el


def relationship(
    id_short: str | None, first: dict, second: dict, *, semantic_id: str | None = None
) -> dict:
    el = _base("RelationshipElement", id_short, semantic_id)
    el["first"], el["second"] = first, second
    return el


def entity(
    id_short: str,
    statements: Iterable[dict | None],
    *,
    global_asset_id: str | None = None,
    semantic_id: str | None = None,
    description: object = None,
    specific_asset_ids: Iterable[tuple[str, str]] = (),
) -> dict:
    """An Entity: SelfManaged iff it names an asset (AASd-014), else CoManaged.
    ``specific_asset_ids`` (``(name, value)`` pairs) are kept only on a SelfManaged one."""
    el = _base("Entity", id_short, semantic_id, description)
    stmts = _children(statements)
    if stmts:
        el["statements"] = stmts
    if global_asset_id:
        el["entityType"] = "SelfManagedEntity"
        el["globalAssetId"] = global_asset_id
        specific = [{"name": n, "value": v} for n, v in specific_asset_ids if n and v]
        if specific:
            el["specificAssetIds"] = specific
    else:
        el["entityType"] = "CoManagedEntity"
    return el


def annotated_relationship(
    id_short: str | None,
    first: dict,
    second: dict,
    annotations: Iterable[dict | None],
    *,
    semantic_id: str | None = None,
) -> dict:
    """An AnnotatedRelationshipElement; ``annotations`` are DataElements (None dropped)."""
    el = _base("AnnotatedRelationshipElement", id_short, semantic_id)
    el["first"], el["second"] = first, second
    notes = _children(annotations)
    if notes:
        el["annotations"] = notes
    return el


def blob(id_short: str, data: bytes, content_type: str, *, semantic_id: str | None = None) -> dict:
    """A Blob: ``data`` base64-encoded (xs:base64Binary), with its MIME content type."""
    import base64

    el = _base("Blob", id_short, semantic_id)
    el["contentType"] = content_type
    el["value"] = base64.b64encode(data).decode("ascii")
    return el


def capability(id_short: str, *, semantic_id: str | None = None,
               supplemental: Iterable[str] = ()) -> dict:
    """A Capability element (it has no value; its semantic ids say what it is)."""
    return _base("Capability", id_short, semantic_id, supplemental=supplemental)


def qualifier(qtype: str, value: object) -> dict | None:
    typed = xsd(value)
    if typed is None:
        return None
    return {"type": qtype, "valueType": typed[0], "value": typed[1]}
