"""The catalog lane: what keeps a reference object honest.

What the lane checks (each failure class has a test)
----------------------------------------------------
1. **Schema-valid** against ``reference-object.schema.json``; the file is named for its
   ``key``.
2. **Every value is sourced** — each non-null scalar under the fact roots
   (:data:`hyperobjects_reference.FACT_ROOTS`) is covered by a source of a value tier
   (primary, museum, regulatory, derived, measured) whose ``field`` is the value's path
   or an ancestor of it. A ``secondary`` source covers nothing: it only locates a primary.
3. **Sources name real paths** — a source's ``field`` resolves in the object (it may name
   a null: a source can confirm that a list is empty or a value is absent).
4. **Each tier carries what makes it checkable** — primary, museum and regulatory: a URL
   and the quoted line; secondary: a URL; derived: the ``method``; measured: the
   ``instrument``, ``resolution_mm``, ``specimen`` and ``measurer_role``, and no URL.
5. **Derived display areas match their formula** — an ``active_area_mm`` covered by a
   ``derived`` source is marked ``derived: true`` and equals
   ``25.4·D·a/√(a²+b²)`` × ``25.4·D·b/√(a²+b²)`` (``a:b`` from ``resolution_px``, else
   from ``aspect``), rounded half-up to 0.1 mm — the same law the device registry was
   built with, so a corrected input is a recomputation, never a hand edit.
6. **Conflicts are decided** — every candidate cites a source that covers the field, the
   candidates differ, and the object's value equals the chosen one.
7. **Status is honest** — ``unverified`` exactly when no value-tier source exists.
8. **A booklet's page count is printable** — positive, and a multiple of 4 when its
   ``binding`` is ``saddle_stitch`` (folded sheets of four pages each).
9. **A container holds other objects, once each** — no ``contents[]`` key is the object's
   own, and no key appears twice (one item carries the count).

One rule reads the whole catalog, so :func:`check_catalog` runs it and :func:`check_object`
does not:

10. **An edition's keys resolve to the right kind** — ``edition.platform`` to a ``device``,
    ``edition.media.key`` to a ``media`` object, ``edition.package`` to a ``case`` or a
    ``carton``, and each ``edition.bundled[]`` key to anything but an edition. A key the
    catalog does not hold is a **note**, never a failure, so an edition can land before its
    formats do; ``contents[]`` keys are resolved the same way, note-only.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from hyperobjects_schemas import load as load_schema

from . import (
    SCHEMA_NAME,
    VALUE_TIERS,
    PathError,
    covers,
    field_exists,
    item_path,
    leaves,
    load_catalog,
    value_at,
)

__all__ = [
    "EDITION_REFERENCE_KINDS",
    "CatalogResult",
    "active_area",
    "catalog_status",
    "check_catalog",
    "check_object",
    "check_references",
]

_MM_PER_INCH = Decimal("25.4")

#: The kinds an edition's keys must resolve to. ``bundled`` takes any kind but ``edition``.
EDITION_REFERENCE_KINDS = {
    "edition.platform": frozenset({"device"}),
    "edition.media.key": frozenset({"media"}),
    "edition.package": frozenset({"case", "carton"}),
}
_QUANTUM = Decimal("0.1")

#: What each tier must carry, beyond ``field``, ``tier`` and ``retrieved``.
_TIER_REQUIRES = {
    "primary": ("url", "quote"),
    "museum": ("url", "quote"),
    "regulatory": ("url", "quote"),
    "secondary": ("url",),
    "derived": ("method",),
    "measured": ("instrument", "resolution_mm", "specimen", "measurer_role"),
}


@dataclass
class CatalogResult:
    """The verdict on a catalog. Falsey when there are problems."""

    objects: int
    values: int
    ok: bool
    problems: list[str] = field(default_factory=list)
    #: True and worth saying, never a failure: an edition key the catalog does not hold yet.
    notes: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def _schema_errors(doc: object) -> list[str]:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(load_schema(SCHEMA_NAME))
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"{where}: {err.message}")
    return out


def _value_sources(obj: Mapping) -> list[tuple[int, Mapping]]:
    return [
        (i, s) for i, s in enumerate(obj.get("sources") or []) if s.get("tier") in VALUE_TIERS
    ]


def _covered(fields: list[str], path: str) -> bool:
    item = item_path(path)
    if item is not None:
        # A label is sourced when anything about its item is (see ``item_path``).
        return any(covers(f, item) or covers(item, f) or _within(f, item) for f in fields)
    return any(covers(f, path) for f in fields)


def _within(source_field: str, item: str) -> bool:
    # ``displays[].panel`` speaks about ``displays[0]`` too.
    if "[]" not in source_field:
        return False
    head, _, _ = source_field.partition("[]")
    return item.startswith(head + "[")


def _coverage_problems(obj: Mapping) -> list[str]:
    fields = [s.get("field") or "" for _, s in _value_sources(obj)]
    return [
        f"{path}: {value!r} is not covered by any primary, museum, regulatory, derived or "
        f"measured source — null = unresolved, never guessed"
        for path, value in leaves(obj)
        if not _covered(fields, path)
    ]


def _source_problems(obj: Mapping) -> list[str]:
    out = []
    for i, src in enumerate(obj.get("sources") or []):
        where = f"sources[{i}] ({src.get('field')})"
        if not field_exists(obj, src.get("field") or ""):
            out.append(f"{where}: names a field that does not exist in the object")
        tier = src.get("tier")
        missing = [k for k in _TIER_REQUIRES.get(tier, ()) if src.get(k) in (None, "")]
        if missing:
            out.append(f"{where}: tier {tier!r} needs {', '.join(missing)}")
        if tier == "measured" and src.get("url"):
            out.append(f"{where}: a measured value is ours — it cites an instrument, not a URL")
        if tier == "measured" and src.get("quote"):
            out.append(f"{where}: a measured value has no quote to carry")
    return out


def _ratio(display: Mapping) -> tuple[Decimal, Decimal] | None:
    res = display.get("resolution_px")
    if isinstance(res, list) and len(res) == 2:
        return Decimal(str(res[0])), Decimal(str(res[1]))
    aspect = display.get("aspect")
    if isinstance(aspect, str) and ":" in aspect:
        left, right = aspect.split(":", 1)
        try:
            return Decimal(left.strip()), Decimal(right.strip())
        except InvalidOperation:
            return None
    return None


def active_area(diagonal_in: float, a: Decimal, b: Decimal) -> tuple[float, float]:
    """The derivation law: Decimal throughout, half-up to 0.1 mm."""
    diagonal_mm = Decimal(str(diagonal_in)) * _MM_PER_INCH
    hypotenuse = (a * a + b * b).sqrt()
    width = (diagonal_mm * a / hypotenuse).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    height = (diagonal_mm * b / hypotenuse).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    return float(width), float(height)


def _derived_area_problems(obj: Mapping) -> list[str]:
    derived_fields = [
        s.get("field") or "" for s in obj.get("sources") or [] if s.get("tier") == "derived"
    ]
    out = []
    for i, display in enumerate(obj.get("displays") or []):
        path = f"displays[{i}].active_area_mm"
        if not any(covers(f, path) or covers(path, f) for f in derived_fields):
            continue
        area = display.get("active_area_mm") or {}
        if area.get("derived") is not True:
            out.append(f"{path}: covered by a derived source but not marked derived: true")
        ratio = _ratio(display)
        diagonal = display.get("diagonal_in")
        if ratio is None or diagonal is None:
            out.append(f"{path}: derived without a diagonal and a pixel ratio to derive from")
            continue
        want = active_area(diagonal, *ratio)
        have = (area.get("width"), area.get("height"))
        if have != want:
            out.append(f"{path}: {have} does not match the derivation law, which gives {want}")
    return out


def _conflict_problems(obj: Mapping) -> list[str]:
    sources = obj.get("sources") or []
    out = []
    for n, conflict in enumerate(obj.get("conflicts") or []):
        where = f"conflicts[{n}] ({conflict.get('field')})"
        try:
            actual = value_at(obj, conflict.get("field") or "")
        except PathError:
            out.append(f"{where}: names a field that does not exist in the object")
            continue
        candidates = conflict.get("candidates") or []
        values = [c.get("value") for c in candidates]
        if len({repr(v) for v in values}) != len(values):
            out.append(f"{where}: two candidates carry the same value — no conflict to decide")
        for c in candidates:
            idx = c.get("source")
            if not isinstance(idx, int) or not 0 <= idx < len(sources):
                out.append(f"{where}: cites source {idx!r}, but the object has {len(sources)}")
            elif not covers(sources[idx].get("field") or "", conflict.get("field") or ""):
                out.append(f"{where}: source {idx} does not cover the field")
            elif sources[idx].get("tier") not in VALUE_TIERS:
                out.append(f"{where}: source {idx} is secondary and supports no value")
        chosen = conflict.get("chosen")
        if not isinstance(chosen, int) or not 0 <= chosen < len(candidates):
            out.append(f"{where}: chosen {chosen!r} is not a candidate")
        elif actual != candidates[chosen].get("value"):
            out.append(
                f"{where}: the object says {actual!r}, the chosen candidate "
                f"{candidates[chosen].get('value')!r}"
            )
    return out


def _status_problems(obj: Mapping) -> list[str]:
    sourced = bool(_value_sources(obj))
    status = obj.get("status")
    if status == "unverified" and sourced:
        return ["status: 'unverified' while value-tier sources exist — say partial or verified"]
    if status != "unverified" and not sourced:
        return [f"status: {status!r} with no value-tier source — that is 'unverified'"]
    return []


def _booklet_problems(obj: Mapping) -> list[str]:
    booklet = (obj.get("edition") or {}).get("booklet")
    if not isinstance(booklet, Mapping) or booklet.get("pages") is None:
        return []
    pages = booklet["pages"]
    if pages <= 0:
        return [f"edition.booklet.pages: {pages} — a booklet has at least one page"]
    if booklet.get("binding") == "saddle_stitch" and pages % 4:
        return [
            f"edition.booklet.pages: {pages} saddle-stitched — a saddle-stitched booklet is "
            f"nested sheets of four pages each, so its count is a multiple of 4"
        ]
    return []


def _contents_problems(obj: Mapping) -> list[str]:
    out = []
    seen: set[str] = set()
    for i, item in enumerate(obj.get("contents") or []):
        key = item.get("key")
        if key == obj.get("key"):
            out.append(f"contents[{i}].key: {key!r} is the object itself — a container cannot "
                       f"hold itself")
        if key in seen:
            out.append(f"contents[{i}].key: {key!r} is listed twice — one item carries the count")
        seen.add(key)
    return out


def _references(obj: Mapping) -> list[tuple[str, str, frozenset[str] | None]]:
    """``(path, key, allowed kinds)`` for every key an object names; ``None`` = any but edition,
    and an empty set = any kind at all (``contents[]``)."""
    refs: list[tuple[str, str, frozenset[str] | None]] = []
    edition = obj.get("edition")
    if isinstance(edition, Mapping):
        media = edition.get("media")
        named = {
            "edition.platform": edition.get("platform"),
            "edition.media.key": media.get("key") if isinstance(media, Mapping) else None,
            "edition.package": edition.get("package"),
        }
        refs += [(path, key, EDITION_REFERENCE_KINDS[path])
                 for path, key in named.items() if isinstance(key, str)]
        refs += [(f"edition.bundled[{i}]", key, None)
                 for i, key in enumerate(edition.get("bundled") or []) if isinstance(key, str)]
    refs += [(f"contents[{i}].key", item.get("key"), frozenset())
             for i, item in enumerate(obj.get("contents") or [])
             if isinstance(item, Mapping) and isinstance(item.get("key"), str)]
    return refs


def check_references(catalog: Mapping[str, object]) -> tuple[list[str], list[str]]:
    """Rule 10, over a whole catalog: ``(problems, notes)``, each line prefixed by its stem.

    A key the catalog does not hold is a note ("not checked"), never a failure. A key it does
    hold must name an object of the kind the path requires.
    """
    problems: list[str] = []
    notes: list[str] = []
    for stem in sorted(catalog):
        obj = catalog[stem]
        if not isinstance(obj, Mapping):
            continue
        for path, key, allowed in _references(obj):
            target = catalog.get(key)
            if not isinstance(target, Mapping):
                notes.append(f"{stem}: {path} names {key!r}, which this catalog does not hold "
                             f"yet — its kind is not checked")
                continue
            kind = target.get("kind")
            if allowed is None and kind == "edition":
                problems.append(f"{stem}: {path} names {key!r}, an edition — what an edition "
                                f"bundles is a physical object, not another edition")
            elif allowed and kind not in allowed:
                problems.append(f"{stem}: {path} names {key!r}, a {kind!r} — it must be "
                                f"{' or '.join(repr(k) for k in sorted(allowed))}")
    return problems, notes


def check_object(obj: object, *, name: str | None = None) -> list[str]:
    """Every problem with one object. ``name`` is the file stem it was read from."""
    problems = _schema_errors(obj)
    if not isinstance(obj, Mapping):
        return problems or ["not an object"]
    if name is not None and obj.get("key") != name:
        problems.append(f"key {obj.get('key')!r} is in a file named {name!r}.json")
    if problems:
        # The remaining rules read the shape the schema guarantees.
        return problems
    problems += _coverage_problems(obj)
    problems += _source_problems(obj)
    problems += _derived_area_problems(obj)
    problems += _conflict_problems(obj)
    problems += _status_problems(obj)
    problems += _booklet_problems(obj)
    problems += _contents_problems(obj)
    return problems


def check_catalog(catalog: dict[str, dict] | None = None) -> CatalogResult:
    """Check every object (bundled unless ``catalog`` is given, keyed by file stem).

    Rules 1–9 run per object; rule 10 (:func:`check_references`) over the catalog, and its
    notes ride in :attr:`CatalogResult.notes` without failing the result.
    """
    if catalog is None:
        catalog = load_catalog()
    problems: list[str] = []
    values = 0
    for stem in sorted(catalog):
        obj = catalog[stem]
        if isinstance(obj, Mapping):
            values += sum(1 for _ in leaves(obj))
        problems.extend(f"{stem}: {p}" for p in check_object(obj, name=stem))
    ref_problems, notes = check_references(catalog)
    problems += ref_problems
    return CatalogResult(objects=len(catalog), values=values, ok=not problems,
                         problems=problems, notes=notes)


def catalog_status(catalog: dict[str, dict] | None = None) -> list[str]:
    """Summary lines: objects per family and status, values, and sources per tier."""
    if catalog is None:
        catalog = load_catalog()
    objs = list(catalog.values())
    tiers = Counter(s.get("tier") for o in objs for s in o.get("sources") or [])
    status = Counter(o.get("status") for o in objs)
    families = Counter(o.get("family") or "-" for o in objs)
    tier_text = " ".join(f"{t}={tiers[t]}" for t in sorted(tiers))
    status_text = " ".join(f"{s}={status[s]}" for s in sorted(status))
    lines = [
        f"reference_status: objects={len(objs)} families={len(families)} "
        f"values={sum(sum(1 for _ in leaves(o)) for o in objs)} "
        f"conflicts={sum(len(o.get('conflicts') or []) for o in objs)} "
        f"status: {status_text or '-'} tiers: {tier_text or '-'}"
    ]
    lines += [f"  family {f}: objects={families[f]}" for f in sorted(families)]
    return lines
