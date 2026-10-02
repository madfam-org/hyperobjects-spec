"""hyperobjects_standard_parts — the keystone's standard-parts catalog (ASM-1 §4).

A catalog entry is a commercial off-the-shelf part an assembly document references with
``{"source": {"type": "standard", "key": "<key>"}}``: a NEMA 17 stepper, a 2020 extrusion,
an MGN12 rail, a 608 bearing, a 2207 brushless motor, a 5-inch X frame class. Each entry
states facts only — the governing standard or datasheet with citation URLs, dimensions that
each cite a source, optional parameters (an extrusion's cut length), and mating interfaces in
the SEM-1 §2.3 shape — and is validated by ``standard-part.schema.json``.

    from hyperobjects_standard_parts import load_part, resolve_parameters, interface_frames

    part = load_part("extrusion-2020")
    values = resolve_parameters(part, {"length_mm": 350})   # out of range raises
    frames = interface_frames(part, values)                 # {interface id: Frame}
    frames["end_b"].origin                                   # (0.0, 0.0, 350.0)

One JSON file per part under ``parts/``, named ``{key}.json``. The data is the source of
truth; the checks in :mod:`hyperobjects_standard_parts.check` are what keep it honest
(every ``size_key`` resolves in the ``interface-sizes`` vocabulary, every frame evaluates at
the defaults, every axis is a unit vector and ``x_axis`` is orthogonal to ``normal``).

An entry's identity for an assembly digest (ASM-1 §3.8) is :func:`part_digest` — the
sha256 of the entry's canonical JSON (GOC-1 ``canonical_json``), so any change to a fact,
a frame or a parameter range changes the digest of every assembly that uses the part.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .expressions import ExpressionError, evaluate_component

__all__ = [
    "SCHEMA_NAME",
    "Frame",
    "ParameterError",
    "interface_frames",
    "list_part_keys",
    "load_catalog",
    "load_part",
    "part_digest",
    "resolve_parameters",
]

SCHEMA_NAME = "standard-part"
_DIR = "parts"

Vector = tuple[float, float, float]


class ParameterError(ValueError):
    """A component gave a parameter the entry does not declare, or a value out of range."""


@dataclass(frozen=True)
class Frame:
    """An interface frame evaluated at a parameter point, in the part's model frame (mm).

    The vectors are returned exactly as the entry states them; the catalog's own check
    holds every entry to unit ``normal`` / ``x_axis`` and orthogonality, so no
    normalisation happens here.
    """

    origin: Vector
    normal: Vector
    x_axis: Vector


def _bundled_dir():
    return resources.files("hyperobjects_standard_parts").joinpath(_DIR)


def list_part_keys(directory: str | Path | None = None) -> list[str]:
    """The keys in the catalog (bundled, or every ``*.json`` in ``directory``), sorted."""
    if directory is None:
        return sorted(
            p.name[: -len(".json")] for p in _bundled_dir().iterdir() if p.name.endswith(".json")
        )
    return sorted(p.stem for p in Path(directory).glob("*.json"))


def load_part(key_or_path: str | Path, directory: str | Path | None = None) -> dict:
    """One entry — a catalog key (bundled, or in ``directory``), or a path to a file."""
    path = Path(key_or_path)
    if isinstance(key_or_path, Path) or path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if directory is not None:
        return json.loads((Path(directory) / f"{key_or_path}.json").read_text(encoding="utf-8"))
    ref = _bundled_dir().joinpath(f"{key_or_path}.json")
    if not ref.is_file():
        raise KeyError(f"{key_or_path!r} is not a standard part in the bundled catalog")
    return json.loads(ref.read_text(encoding="utf-8"))


def load_catalog(directory: str | Path | None = None) -> dict[str, dict]:
    """Every entry as ``{file stem: entry}`` — bundled, or every ``*.json`` in ``directory``.

    Keyed by the FILE name, so a check can see an entry whose ``key`` disagrees with it.
    """
    return {key: load_part(key, directory) for key in list_part_keys(directory)}


def resolve_parameters(part: Mapping, given: Mapping | None = None) -> dict[str, float]:
    """ASM-1 §1 full injection: every declared default, overridden by ``given``.

    A given parameter the entry does not declare, a non-number, or a value outside
    ``[min, max]`` raises :class:`ParameterError` — out of range is an error, never clamped.
    """
    declared = {
        p["id"]: p for p in part.get("parameters") or [] if isinstance(p, Mapping) and "id" in p
    }
    values = {pid: float(p["default"]) for pid, p in declared.items()}
    key = part.get("key")
    for pid, value in (given or {}).items():
        if pid not in declared:
            raise ParameterError(f"{key}: {pid!r} is not a parameter of this standard part")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ParameterError(f"{key}: {pid}={value!r} is not a number")
        low, high = declared[pid]["min"], declared[pid]["max"]
        if not low <= value <= high:
            raise ParameterError(
                f"{key}: {pid}={value} is outside [{low}, {high}] — out of range is an error, "
                f"never clamped (ASM-1 §1)"
            )
        values[pid] = float(value)
    return values


def _vector(raw: object, values: Mapping[str, float], where: str) -> Vector:
    if not isinstance(raw, list | tuple) or len(raw) != 3:
        raise ExpressionError(f"{where}: {raw!r} is not a list of exactly 3 components")
    out = []
    for i, component in enumerate(raw):
        try:
            out.append(evaluate_component(component, values))
        except ExpressionError as exc:
            raise ExpressionError(f"{where}[{i}]: {exc}") from None
    return (out[0], out[1], out[2])


def interface_frames(part: Mapping, values: Mapping[str, float] | None = None) -> dict[str, Frame]:
    """Every interface's frame at ``values`` (defaults when omitted), by interface id.

    Raises :class:`~hyperobjects_standard_parts.expressions.ExpressionError` naming the
    interface and vector when a component does not evaluate.
    """
    if values is None:
        values = resolve_parameters(part)
    frames = {}
    for iface in part.get("interfaces") or []:
        frame = iface.get("frame") or {}
        where = f"{part.get('key')}.{iface.get('id')}.frame"
        frames[iface["id"]] = Frame(
            origin=_vector(frame.get("origin"), values, f"{where}.origin"),
            normal=_vector(frame.get("normal"), values, f"{where}.normal"),
            x_axis=_vector(frame.get("x_axis"), values, f"{where}.x_axis"),
        )
    return frames


def part_digest(part: Mapping) -> str:
    """sha256 hex of the entry's canonical JSON (GOC-1 ``canonical_json``) — the standard
    part's resolved identity inside an assembly digest (ASM-1 §3.8)."""
    from hyperobjects_schemas.generator_output import canonical_json

    return hashlib.sha256(canonical_json(dict(part))).hexdigest()
