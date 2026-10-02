"""Vocabulary membership for manifests (SEM-1 §4): every fabrication key resolves.

A manifest may now say what it needs to be made (``requirements``) and how its interfaces
mate (``size_key``). Their STRUCTURE is the manifest schema's job; whether each key a
manifest writes is a key anybody defined is this rule's. Four places are read:

* every interface ``size_key`` — a literal key, or ``{"param": …, "map": {value: key}}``,
  in which case every value of ``map`` is a key the interface can resolve to;
* ``requirements.process`` (a list, or a single string);
* ``requirements.materials.any_of`` / ``none_of``;
* the keys of ``requirements.process_parameters``;

and the same three requirement fields again under each ``requirements.parts.<part id>``
override.

The rule reads the manifest DEFENSIVELY — it does not assume the schema has already
accepted the shape, because a manifest can be checked by a schema that predates these
fields. Absent fields contribute nothing, so every manifest written before SEM-1 passes
silently; a field present in a shape the rule cannot read is reported, never skipped, so a
malformed key cannot pass by being unreadable.

Interfaces are read from ``hyperobject.cdg_interfaces`` (solid, yantra4d) and
``hyperobject.interfaces`` (soft, Fashion Cabinet) — whichever the manifest has.
"""

from __future__ import annotations

import difflib

from .fabrication import load_fabrication_vocabularies, vocabulary_keys

__all__ = ["manifest_vocabulary_problems", "RULE_PREFIX"]

#: How each problem starts, so a reader of `check` output can tell this rule's findings
#: from the schema's and from the other house rules'.
RULE_PREFIX = "fabrication vocabulary:"

_INTERFACE_LISTS = ("cdg_interfaces", "interfaces")


def _hint(value: str, known: set[str]) -> str:
    close = difflib.get_close_matches(value, sorted(known), n=1, cutoff=0.75)
    return f" (did you mean {close[0]!r}?)" if close else ""


class _Checker:
    def __init__(self, docs: dict[str, dict]):
        self.keys = {name: vocabulary_keys(name, docs) for name in docs}
        self.problems: list[str] = []

    def _say(self, where: str, msg: str) -> None:
        self.problems.append(f"{RULE_PREFIX} {where}: {msg}")

    def member(self, where: str, value: object, vocabulary: str) -> None:
        known = self.keys.get(vocabulary, set())
        if not isinstance(value, str):
            self._say(where, f"{value!r} is not a string key of the {vocabulary} vocabulary")
        elif value not in known:
            self._say(
                where,
                f"{value!r} is not a key of the {vocabulary} vocabulary{_hint(value, known)}",
            )

    def size_key(self, where: str, value: object) -> None:
        if isinstance(value, str):
            self.member(where, value, "interface-sizes")
            return
        if isinstance(value, dict) and isinstance(value.get("map"), dict):
            mapping = value["map"]
            if not mapping:
                self._say(where, "a {param, map} size_key with an empty map resolves to nothing")
            for option, key in mapping.items():
                self.member(f"{where}.map[{option!r}]", key, "interface-sizes")
            return
        self._say(where, "is neither a size key nor a {param, map} object — it cannot resolve")

    def requirement_block(self, where: str, block: object) -> None:
        if not isinstance(block, dict):
            self._say(where, "is not an object")
            return
        if "process" in block:
            procs = block["process"]
            procs = [procs] if isinstance(procs, str) else procs
            if isinstance(procs, list):
                for i, proc in enumerate(procs):
                    self.member(f"{where}.process[{i}]", proc, "processes")
            else:
                self._say(f"{where}.process", "is neither a process key nor a list of them")
        if "materials" in block:
            materials = block["materials"]
            if isinstance(materials, dict):
                for field_name in ("any_of", "none_of"):
                    values = materials.get(field_name)
                    if values is None:
                        continue
                    if not isinstance(values, list):
                        self._say(f"{where}.materials.{field_name}", "is not a list")
                        continue
                    for i, cls in enumerate(values):
                        self.member(
                            f"{where}.materials.{field_name}[{i}]", cls, "material-classes"
                        )
            else:
                self._say(f"{where}.materials", "is not an object")
        if "process_parameters" in block:
            params = block["process_parameters"]
            if isinstance(params, dict):
                for name in params:
                    self.member(f"{where}.process_parameters.{name}", name, "process-parameters")
            else:
                self._say(f"{where}.process_parameters", "is not an object")


def manifest_vocabulary_problems(
    doc: object, *, vocabularies: dict[str, dict] | None = None
) -> list[str]:
    """Every fabrication key a manifest writes that no vocabulary defines.

    Returns an empty list for a manifest that writes none — which, on 2026-10-02, is every
    manifest in both commons. ``vocabularies`` defaults to the bundled set.
    """
    if not isinstance(doc, dict):
        return []
    checker = _Checker(vocabularies if vocabularies is not None else _bundled())

    hyperobject = doc.get("hyperobject")
    if isinstance(hyperobject, dict):
        for list_name in _INTERFACE_LISTS:
            interfaces = hyperobject.get(list_name)
            if not isinstance(interfaces, list):
                continue
            for pos, iface in enumerate(interfaces):
                if isinstance(iface, dict) and "size_key" in iface:
                    label = iface.get("id") if isinstance(iface.get("id"), str) else pos
                    checker.size_key(
                        f"hyperobject.{list_name}[{label!r}].size_key", iface["size_key"]
                    )

    if "requirements" in doc:
        requirements = doc["requirements"]
        checker.requirement_block("requirements", requirements)
        parts = requirements.get("parts") if isinstance(requirements, dict) else None
        if isinstance(parts, dict):
            for part_id, override in parts.items():
                checker.requirement_block(f"requirements.parts.{part_id}", override)
        elif parts is not None:
            checker._say("requirements.parts", "is not an object keyed by part id")

    return checker.problems


_CACHE: dict[str, dict] | None = None


def _bundled() -> dict[str, dict]:
    """The bundled vocabularies, read once per process — a fleet check runs this rule on
    every manifest, and the documents do not change under it."""
    global _CACHE
    if _CACHE is None:
        _CACHE = load_fabrication_vocabularies()
    return _CACHE
