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

__all__ = ["capability_profile_problems", "manifest_vocabulary_problems", "RULE_PREFIX"]

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


#: JSON type tests for a capability's ``value_type`` (fabrication-vocabulary schema).
_VALUE_TYPES = {
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "string": lambda v: isinstance(v, str),
    "array": lambda v: isinstance(v, list),
}


def capability_profile_problems(
    profile: object, *, vocabularies: dict[str, dict] | None = None
) -> list[str]:
    """Every way a producer's ``capability_profile`` (ASM-1 §2) disagrees with the
    ``fabrication-capabilities`` vocabulary: an unknown key, a value of the wrong JSON
    type (``value_type``), an item outside ``allowed_values``, or an item that is not a key
    of its ``value_vocabulary``. ``process`` is a LIST of ``processes`` keys, like
    ``requirements.process`` (settled in 0.5.0; P4-ASM2 finding 5). Empty for no profile.
    """
    if profile is None:
        return []
    docs = vocabularies if vocabularies is not None else _bundled()
    checker = _Checker(docs)
    where = "capability_profile"
    if not isinstance(profile, dict):
        checker._say(where, "is not an object")
        return checker.problems
    entries = {
        e["key"]: e
        for e in docs.get("fabrication-capabilities", {}).get("entries", [])
        if isinstance(e, dict) and isinstance(e.get("key"), str)
    }
    for key in sorted(profile):
        value, at = profile[key], f"{where}.{key}"
        entry = entries.get(key)
        if entry is None:
            checker._say(
                at, f"{key!r} is not a key of the fabrication-capabilities vocabulary"
                f"{_hint(key, set(entries))}"
            )
            continue
        value_type = entry.get("value_type")
        test = _VALUE_TYPES.get(value_type)
        if test is not None and not test(value):
            checker._say(at, f"{value!r} is not a {value_type} (the vocabulary's value_type)")
            continue
        items = value if isinstance(value, list) else [value]
        allowed = entry.get("allowed_values")
        for i, item in enumerate(items):
            item_at = f"{at}[{i}]" if isinstance(value, list) else at
            if entry.get("value_vocabulary"):
                checker.member(item_at, item, entry["value_vocabulary"])
            elif isinstance(allowed, list) and item not in allowed:
                checker._say(item_at, f"{item!r} is not one of {', '.join(allowed)}")
    return checker.problems


_CACHE: dict[str, dict] | None = None


def _bundled() -> dict[str, dict]:
    """The bundled vocabularies, read once per process — a fleet check runs this rule on
    every manifest, and the documents do not change under it."""
    global _CACHE
    if _CACHE is None:
        _CACHE = load_fabrication_vocabularies()
    return _CACHE
