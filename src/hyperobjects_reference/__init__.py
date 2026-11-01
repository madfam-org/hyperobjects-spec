"""hyperobjects_reference — the keystone's reference-objects catalog.

A reference object is a real commercial product described by its published facts: a
console, a handheld, a phone, a controller, a media format, a case, a carton, a booklet.
A commons family cartridge turns those facts into a named PRESET; the geometry stays the
family's (an archetype we own), the numbers stay the maker's. The catalog is facts only —
never CAD, never artwork, never a likeness — validated by ``reference-object.schema.json``.

    from hyperobjects_reference import load_family, value_at, is_sourced, family_digest

    for obj in load_family("clamshell-dual-screen-handheld"):
        closed = value_at(obj, "dimensions_mm.states.closed")
        is_sourced(obj, "controls")      # True: the maker's control list is complete
    family_digest("clamshell-dual-screen-handheld")   # what a generator records

One JSON file per object under ``objects/``, named ``{key}.json``. Every non-null value is
covered by a ``sources[]`` entry whose ``field`` is that value's path or an ancestor of it,
and ``null`` means unresolved, never guessed. The rules that keep that honest are in
:mod:`hyperobjects_reference.check`.

The two directions this package fixes (owner ruling, 2026-11-01): geometry and the facts it
is generated from live on the geometry side (this keystone and the commons); consumers such
as Telesia read published, prerendered artifacts and hold neither.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from importlib import resources
from pathlib import Path

__all__ = [
    "SCHEMA_NAME",
    "VALUE_TIERS",
    "PathError",
    "catalog_digest",
    "covers",
    "family_digest",
    "field_exists",
    "is_sourced",
    "item_path",
    "leaves",
    "list_keys",
    "load_catalog",
    "load_family",
    "load_object",
    "object_digest",
    "value_at",
]

SCHEMA_NAME = "reference-object"
_DIR = "objects"

#: The tiers whose sources may cover a value. ``secondary`` locates a primary source and
#: covers nothing: a value it alone supports is unsourced.
VALUE_TIERS = frozenset({"primary", "museum", "regulatory", "derived", "measured"})

#: The top-level keys that hold FACTS. Identity and bookkeeping (key, kind, family, brand,
#: model, status, sources, conflicts, notes …) are not facts about the object's geometry
#: and are not required to cite a source.
FACT_ROOTS = (
    "announced", "released", "dimensions_mm", "mass_g", "displays", "hinge", "controls",
    "ports", "media", "materials", "features",
)

_STEP = re.compile(r"([a-z_][a-z0-9_]*)((?:\[[0-9]+\])*)")
_INDEX = re.compile(r"\[([0-9]+)\]")


class PathError(KeyError):
    """A path that does not name a value in the object."""


def _bundled_dir():
    return resources.files("hyperobjects_reference").joinpath(_DIR)


def list_keys(directory: str | Path | None = None) -> list[str]:
    """The keys in the catalog (bundled, or every ``*.json`` in ``directory``), sorted."""
    if directory is None:
        root = _bundled_dir()
        if not root.is_dir():
            return []
        return sorted(p.name[: -len(".json")] for p in root.iterdir() if p.name.endswith(".json"))
    return sorted(p.stem for p in Path(directory).glob("*.json"))


def load_object(key_or_path: str | Path, directory: str | Path | None = None) -> dict:
    """One object — a catalog key (bundled, or in ``directory``), or a path to a file."""
    path = Path(key_or_path)
    if isinstance(key_or_path, Path) or path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if directory is not None:
        return json.loads((Path(directory) / f"{key_or_path}.json").read_text(encoding="utf-8"))
    ref = _bundled_dir().joinpath(f"{key_or_path}.json")
    if not ref.is_file():
        raise KeyError(f"{key_or_path!r} is not a reference object in the bundled catalog")
    return json.loads(ref.read_text(encoding="utf-8"))


def load_catalog(directory: str | Path | None = None) -> dict[str, dict]:
    """Every object as ``{file stem: object}`` — bundled, or every ``*.json`` in ``directory``.

    Keyed by the FILE name, so a check can see an object whose ``key`` disagrees with it.
    """
    return {key: load_object(key, directory) for key in list_keys(directory)}


def load_family(family: str, directory: str | Path | None = None) -> list[dict]:
    """The objects that are presets of ``family``, sorted by key."""
    catalog = load_catalog(directory)
    return [catalog[k] for k in sorted(catalog) if catalog[k].get("family") == family]


def _parse(path: str) -> list[str | int]:
    steps: list[str | int] = []
    for part in path.split("."):
        m = _STEP.fullmatch(part)
        if not m:
            raise PathError(f"{path!r} is not a reference path")
        steps.append(m.group(1))
        steps.extend(int(i) for i in _INDEX.findall(m.group(2)))
    return steps


def value_at(obj: Mapping, path: str):
    """The value at a dotted, indexed path (``displays[0].active_area_mm.width``)."""
    node: object = obj
    for step in _parse(path):
        if isinstance(step, int):
            if not isinstance(node, list) or step >= len(node):
                raise PathError(path)
            node = node[step]
        else:
            if not isinstance(node, Mapping) or step not in node:
                raise PathError(path)
            node = node[step]
    return node


def _field_pattern(source_field: str) -> re.Pattern:
    # An empty index (``displays[].panel``) stands for every index of that list.
    parts = re.split(r"(\[\])", source_field)
    body = "".join(r"\[[0-9]+\]" if p == "[]" else re.escape(p) for p in parts)
    return re.compile(body + r"(?:[.\[].*)?")


def covers(source_field: str, path: str) -> bool:
    """True when a source on ``source_field`` covers ``path`` (exactly, or as a subtree).

    ``[]`` in the source field matches any index, so ``displays[].panel`` covers
    ``displays[1].panel`` and nothing else of ``displays[1]``.
    """
    if "[]" not in source_field:
        return (
            path == source_field
            or path.startswith(source_field + ".")
            or path.startswith(source_field + "[")
        )
    return _field_pattern(source_field).fullmatch(path) is not None


def field_exists(obj: Mapping, field: str) -> bool:
    """True when ``field`` names a value (or, with ``[]``, a value in at least one item)."""
    if "[]" not in field:
        try:
            value_at(obj, field)
        except PathError:
            return False
        return True
    head, _, tail = field.partition("[]")
    try:
        items = value_at(obj, head)
    except PathError:
        return False
    if not isinstance(items, list):
        return False
    return any(field_exists(obj, f"{head}[{i}]{tail}") for i in range(len(items)))


def is_sourced(obj: Mapping, field: str) -> bool:
    """True when a value-tier source covers ``field`` or anything below it.

    This is the absence rule generators rely on: a covered ``controls`` (or ``ports``,
    ``media``) list is the source's complete list, so a kind missing from it is a sourced
    zero — while an uncovered list says nothing either way.
    """
    for src in obj.get("sources") or []:
        if src.get("tier") not in VALUE_TIERS:
            continue
        f = src.get("field") or ""
        if covers(f, field) or covers(field, f):
            return True
    return False


def item_path(path: str) -> str | None:
    """For an item's identifying label (``displays[0].role``, ``ports[2].kind``), the item.

    A label names WHICH display or port an item is; it is sourced when anything about the
    item is (a source on ``displays[0].diagonal_in`` establishes that display), never on
    its own. ``None`` for every other path.
    """
    m = re.fullmatch(r"(.+\[[0-9]+\])\.(role|kind)", path)
    return m.group(1) if m else None


def leaves(obj: Mapping) -> Iterator[tuple[str, object]]:
    """Every non-null scalar under the fact roots, as ``(path, value)``.

    ``active_area_mm.derived`` is bookkeeping (whether the area is ours or the maker's),
    not a fact about the object, and is not yielded.
    """

    def walk(node: object, path: str) -> Iterator[tuple[str, object]]:
        if node is None:
            return
        if isinstance(node, Mapping):
            for k in node:
                if k == "derived" and path.endswith(".active_area_mm"):
                    continue
                yield from walk(node[k], f"{path}.{k}")
        elif isinstance(node, list):
            if node and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                            for x in node):
                yield path, node          # a numeric tuple (resolution_px) is one value
                return
            for i, item in enumerate(node):
                yield from walk(item, f"{path}[{i}]")
        else:
            yield path, node

    for root in FACT_ROOTS:
        if root in obj:
            yield from walk(obj[root], root)


def _canonical(doc: object) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def object_digest(obj: Mapping) -> str:
    """sha256 of the object's canonical JSON: any change to a fact or a source moves it."""
    return hashlib.sha256(_canonical(obj)).hexdigest()


def catalog_digest(catalog: Mapping[str, Mapping]) -> str:
    """sha256 over ``key:object_digest`` lines in key order — order- and format-free."""
    lines = "".join(f"{k}:{object_digest(catalog[k])}\n" for k in sorted(catalog))
    return hashlib.sha256(lines.encode()).hexdigest()


def family_digest(family: str, directory: str | Path | None = None) -> str:
    """The digest a generator records in ``_generated_from``: every object of one family."""
    return catalog_digest({o["key"]: o for o in load_family(family, directory)})
