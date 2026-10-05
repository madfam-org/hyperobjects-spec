"""The catalog lane: what keeps a standard-parts entry honest.

What the lane checks (each failure class has a test)
----------------------------------------------------
1. **Schema-valid** against ``standard-part.schema.json``; the file is named for its ``key``.
2. **Quadrilingual** — ``name``, ``description`` and every parameter and interface label are
   non-blank in es/en/fr/pt (the schema requires the keys; this refuses whitespace).
3. **Review claims are honest** — ``reviewed`` names a reviewer and has no ``generated``
   language facet (the lexicon's rule).
4. **Facts are cited** — the governing citation, every dimension and every parameter that
   cites a source points at an index that exists.
5. **Parameters are coherent** — ids unique, ``min <= default <= max``.
6. **Interfaces resolve** — ids unique; every ``size_key`` resolves through the fabrication
   vocabulary-membership rule (:func:`hyperobjects_lexicon.membership.manifest_vocabulary_problems`,
   the same machinery a manifest goes through); ``geometry_type`` equals that size key's
   ``geometry_type``; ``frame.part``, when written, is the entry key.
7. **Frames evaluate** — every component evaluates, with ``y4d_spec.frame_eval`` (ASM-1
   §1), at the parameter defaults and at every parameter's ``min`` and ``max``; every
   identifier an expression reads (in the frame or in the interface's ``let``) is a
   declared parameter or a ``let`` name, and every parameter read is listed in the
   interface's ``parameters``; a ``let`` shadows no parameter and has no cycle.
8. **Axes are exact** — at every one of those points ``normal`` and ``x_axis`` are unit
   vectors and orthogonal, to ``AXIS_TOLERANCE``. A catalog entry carries no normalisation
   slack: the assembly placement (ASM-1 §3.4) builds its matrix from these vectors.
9. **Belt facts are usable** (ASM-1 §9, v1.3) — a ``belt`` block (category ``belt``) and a
   ``belt_engagement`` cite sources that exist, state positive numbers in mm, and the
   engagement's ``center`` and ``axis`` read only the parameters it lists, evaluate at the
   same parameter points, and give a unit ``axis``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from hyperobjects_schemas import load as load_schema
from y4d_spec.semantic_rules import LetCycleError, expression_names, let_evaluation_order

from . import (
    BELT_FACTS,
    SCHEMA_NAME,
    FrameEvaluationError,
    belt_engagement,
    belt_facts,
    interface_frames,
    load_catalog,
    resolve_parameters,
)

__all__ = [
    "AXIS_TOLERANCE",
    "CatalogResult",
    "catalog_status",
    "check_catalog",
    "check_part",
]

#: How far from exact a unit length or a dot product may be. Catalog vectors are written
#: as axis-aligned literals, so anything beyond float noise is an authoring error.
AXIS_TOLERANCE = 1e-9

_LANGUAGES = ("es", "en", "fr", "pt")


@dataclass
class CatalogResult:
    """The verdict on a catalog. Falsey when there are problems."""

    parts: int
    interfaces: int
    ok: bool
    problems: list[str] = field(default_factory=list)

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


def _blank_languages(block: object, what: str) -> list[str]:
    if not isinstance(block, Mapping):
        return []  # the schema already said so
    return [
        f"{what}.{lang}: blank — all four languages are required (RFC 0039 §7)"
        for lang in _LANGUAGES
        if isinstance(block.get(lang), str) and not block[lang].strip()
    ]


def _review_problems(block: object) -> list[str]:
    if not isinstance(block, Mapping) or block.get("state") != "reviewed":
        return []
    problems = []
    if not block.get("reviewers"):
        problems.append("review_status: 'reviewed' with no reviewers — a review nobody signed")
    still = sorted(k for k, v in (block.get("languages") or {}).items() if v == "generated")
    if still:
        problems.append(
            f"review_status: 'reviewed' while {', '.join(still)} still 'generated' — the "
            f"state is the WORST facet"
        )
    return problems


def _source_index_problems(part: Mapping) -> list[str]:
    count = len(part.get("sources") or [])
    out = []

    def cite(where: str, idx: object) -> None:
        if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < count:
            out.append(f"{where}: cites source {idx!r}, but the entry has {count}")

    cite("governing.source", (part.get("governing") or {}).get("source"))
    for name, dim in (part.get("dimensions") or {}).items():
        if isinstance(dim, Mapping):
            cite(f"dimensions.{name}", dim.get("source"))
    for param in part.get("parameters") or []:
        if isinstance(param, Mapping) and "source" in param:
            cite(f"parameters[{param.get('id')!r}].source", param["source"])
    for block, names in (("belt", tuple(BELT_FACTS)),
                         ("belt_engagement", ("pitch_diameter", "running_diameter"))):
        for name in names:
            dim = (part.get(block) or {}).get(name)
            if isinstance(dim, Mapping):
                cite(f"{block}.{name}", dim.get("source"))
    return out


def _parameter_problems(part: Mapping) -> list[str]:
    out, seen = [], set()
    for param in part.get("parameters") or []:
        if not isinstance(param, Mapping):
            continue
        pid = param.get("id")
        if pid in seen:
            out.append(f"parameters: {pid!r} declared twice")
        seen.add(pid)
        out += _blank_languages(param.get("label"), f"parameters[{pid!r}].label")
        low, default, high = param.get("min"), param.get("default"), param.get("max")
        if all(isinstance(v, int | float) for v in (low, default, high)) and not (
            low <= default <= high
        ):
            out.append(f"parameters[{pid!r}]: default {default} is outside [{low}, {high}]")
    return out


def _vocabulary_problems(part: Mapping, vocabularies: dict[str, dict] | None) -> list[str]:
    from hyperobjects_lexicon.fabrication import load_fabrication_vocabularies
    from hyperobjects_lexicon.membership import manifest_vocabulary_problems

    interfaces = [i for i in part.get("interfaces") or [] if isinstance(i, Mapping)]
    docs = vocabularies if vocabularies is not None else load_fabrication_vocabularies()
    # The same rule a manifest's interfaces go through: wrap the entry's interfaces as a
    # manifest's `hyperobject.cdg_interfaces` and let the membership machinery judge them.
    out = list(
        manifest_vocabulary_problems(
            {"hyperobject": {"cdg_interfaces": interfaces}}, vocabularies=docs
        )
    )
    sizes = {
        e.get("key"): e
        for e in (docs.get("interface-sizes") or {}).get("entries") or []
        if isinstance(e, Mapping)
    }
    for iface in interfaces:
        size = sizes.get(iface.get("size_key"))
        if size is not None and iface.get("geometry_type") != size.get("geometry_type"):
            out.append(
                f"interfaces[{iface.get('id')!r}]: geometry_type {iface.get('geometry_type')!r} "
                f"differs from size key {iface.get('size_key')!r}'s {size.get('geometry_type')!r}"
            )
    return out


def _names_read(component: object) -> set[str]:
    """The identifiers an expression reads (parse only; an unparseable string reads none —
    the evaluator reports why it does not parse)."""
    return expression_names(component)


def _parameter_points(part: Mapping) -> list[tuple[str, dict[str, float]]]:
    """The defaults, then each parameter at its min and its max with the others at default."""
    defaults = resolve_parameters(part)
    points = [("defaults", defaults)]
    for param in part.get("parameters") or []:
        for bound in ("min", "max"):
            value = param.get(bound)
            if isinstance(value, int | float) and not isinstance(value, bool):
                points.append((f"{param['id']}={bound}", {**defaults, param["id"]: float(value)}))
    return points


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _frame_problems(part: Mapping) -> list[str]:
    declared = {p.get("id") for p in part.get("parameters") or [] if isinstance(p, Mapping)}
    out = []
    for iface in part.get("interfaces") or []:
        if not isinstance(iface, Mapping):
            continue
        iid = iface.get("id")
        out += _blank_languages(iface.get("label"), f"interfaces[{iid!r}].label")
        frame = iface.get("frame") or {}
        if "part" in frame and frame["part"] != part.get("key"):
            out.append(
                f"interfaces[{iid!r}].frame.part {frame['part']!r} is not the entry key — a "
                f"standard part is one rigid body"
            )
        read = set()
        for vec in ("origin", "normal", "x_axis"):
            for component in frame.get(vec) or []:
                read |= _names_read(component)
        let_block = iface.get("let") or {}
        for name in sorted(set(let_block) & declared):
            out.append(f"interfaces[{iid!r}].let.{name} shadows a parameter")
        try:
            let_evaluation_order(dict(let_block))
        except LetCycleError as exc:
            out.append(f"interfaces[{iid!r}].let: {exc}")
        for expr in let_block.values():
            read |= _names_read(expr)
        read -= set(let_block)
        listed = set(iface.get("parameters") or [])
        for name in sorted(read - declared):
            out.append(f"interfaces[{iid!r}].frame reads {name!r}, which is not a parameter")
        for name in sorted(listed - declared):
            out.append(f"interfaces[{iid!r}].parameters lists {name!r}, which is not a parameter")
        for name in sorted((read & declared) - listed):
            out.append(f"interfaces[{iid!r}].frame reads {name!r} but does not list it")

    if out:
        return out
    for label, values in _parameter_points(part):
        try:
            frames = interface_frames(part, values)
        except FrameEvaluationError as exc:
            out.append(f"at {label}: {exc}")
            continue
        for iid, frame in frames.items():
            n_len = math.sqrt(_dot(frame.normal, frame.normal))
            x_len = math.sqrt(_dot(frame.x_axis, frame.x_axis))
            if abs(n_len - 1) > AXIS_TOLERANCE:
                out.append(f"interfaces[{iid!r}] at {label}: |normal| = {n_len:.12g}, not 1")
            if abs(x_len - 1) > AXIS_TOLERANCE:
                out.append(f"interfaces[{iid!r}] at {label}: |x_axis| = {x_len:.12g}, not 1")
            dot = _dot(frame.normal, frame.x_axis)
            if abs(dot) > AXIS_TOLERANCE:
                out.append(
                    f"interfaces[{iid!r}] at {label}: normal·x_axis = {dot:.12g} — x_axis is "
                    f"not orthogonal to the normal"
                )
    return out


def _belt_problems(part: Mapping) -> list[str]:
    """Rule 9: the belt block and the belt engagement (ASM-1 §9)."""
    out = []
    if "belt" in part and belt_facts(part) is None:
        out.append("belt: every stated fact must be a positive number in mm")
    block = part.get("belt_engagement")
    if not isinstance(block, Mapping):
        return out
    declared = {p.get("id") for p in part.get("parameters") or [] if isinstance(p, Mapping)}
    read = set()
    for vec in ("center", "axis"):
        for component in block.get(vec) or []:
            read |= _names_read(component)
    listed = set(block.get("parameters") or [])
    for name in sorted(read - declared):
        out.append(f"belt_engagement reads {name!r}, which is not a parameter")
    for name in sorted(listed - declared):
        out.append(f"belt_engagement.parameters lists {name!r}, which is not a parameter")
    for name in sorted((read & declared) - listed):
        out.append(f"belt_engagement reads {name!r} but does not list it")
    if out:
        return out
    for label, values in _parameter_points(part):
        try:
            engagement = belt_engagement(part, values)
        except (FrameEvaluationError, ValueError) as exc:
            out.append(f"belt_engagement at {label}: {exc}")
            continue
        length = math.sqrt(_dot(engagement.axis, engagement.axis))
        if abs(length - 1) > AXIS_TOLERANCE:
            out.append(f"belt_engagement at {label}: |axis| = {length:.12g}, not 1")
    return out


def check_part(
    part: object, *, name: str | None = None, vocabularies: dict[str, dict] | None = None
) -> list[str]:
    """Every problem with one entry. ``name`` is the file stem the entry was read from."""
    problems = _schema_errors(part)
    if not isinstance(part, Mapping):
        return problems or ["not an object"]
    if name is not None and part.get("key") != name:
        problems.append(f"key {part.get('key')!r} is in a file named {name!r}.json")
    if problems:
        # The remaining rules read the shape the schema guarantees; a malformed entry is
        # reported by the schema and not walked further.
        return problems
    problems += _blank_languages(part.get("name"), "name")
    problems += _blank_languages(part.get("description"), "description")
    problems += _review_problems(part.get("review_status"))
    problems += _source_index_problems(part)
    problems += _parameter_problems(part)
    seen: set[str] = set()
    for iface in part.get("interfaces") or []:
        if iface.get("id") in seen:
            problems.append(f"interfaces: {iface.get('id')!r} declared twice")
        seen.add(iface.get("id"))
    problems += _vocabulary_problems(part, vocabularies)
    problems += _frame_problems(part)
    problems += _belt_problems(part)
    return problems


def check_catalog(
    catalog: dict[str, dict] | None = None, *, vocabularies: dict[str, dict] | None = None
) -> CatalogResult:
    """Check every entry (bundled unless ``catalog`` is given, keyed by file stem)."""
    if catalog is None:
        catalog = load_catalog()
    problems: list[str] = []
    interfaces = 0
    for stem in sorted(catalog):
        part = catalog[stem]
        if isinstance(part, Mapping):
            interfaces += len(part.get("interfaces") or [])
        problems.extend(
            f"{stem}: {p}" for p in check_part(part, name=stem, vocabularies=vocabularies)
        )
    return CatalogResult(
        parts=len(catalog), interfaces=interfaces, ok=not problems, problems=problems
    )


def catalog_status(catalog: dict[str, dict] | None = None) -> list[str]:
    """One summary line for the catalog: parts, interfaces, cited dimensions, review state.

    The review clause says ``signed`` / ``draft`` (not ``reviewed=`` / ``generated=``) for
    the same reason the fabrication status lines do: README count checks read those two
    tokens as corpus-wide TERM counts.
    """
    if catalog is None:
        catalog = load_catalog()
    parts = list(catalog.values())
    signed = sum(1 for p in parts if (p.get("review_status") or {}).get("state") == "reviewed")
    return [
        f"standard_parts_status: parts={len(parts)} "
        f"interfaces={sum(len(p.get('interfaces') or []) for p in parts)} "
        f"dimensions={sum(len(p.get('dimensions') or {}) for p in parts)} "
        f"parameters={sum(len(p.get('parameters') or []) for p in parts)} "
        f"classes={sum(1 for p in parts if (p.get('governing') or {}).get('kind') == 'class')} "
        f"review: signed={signed} draft={len(parts) - signed}"
    ]
