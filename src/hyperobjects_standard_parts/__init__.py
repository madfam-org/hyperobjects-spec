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

from y4d_spec.frame_eval import FrameEvaluationError, evaluate_expression, resolve_let

__all__ = [
    "SCHEMA_NAME",
    "BELT_FACTS",
    "BeltEngagement",
    "Frame",
    "FrameEvaluationError",
    "ParameterError",
    "belt_engagement",
    "belt_facts",
    "envelope_solids",
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
        raise FrameEvaluationError(f"{where}: {raw!r} is not a list of exactly 3 components")
    out = []
    for i, component in enumerate(raw):
        try:
            # ASM-1 §1: THE evaluator — y4d_spec.frame_eval (grammar check, then a hand
            # walk; nothing reaches eval). The declared ids are the entry's parameters
            # plus the interface's `let` names.
            out.append(evaluate_expression(component, values, set(values)))
        except FrameEvaluationError as exc:
            raise FrameEvaluationError(f"{where}[{i}]: {exc}") from None
    return (out[0], out[1], out[2])


def interface_frames(part: Mapping, values: Mapping[str, float] | None = None) -> dict[str, Frame]:
    """Every interface's frame at ``values`` (defaults when omitted), by interface id.

    Components are evaluated by ``y4d_spec.frame_eval.evaluate_expression`` (ASM-1 §1).
    Raises :class:`FrameEvaluationError` naming the interface and vector when a component
    does not evaluate. The vectors are returned as written, not normalised.
    """
    if values is None:
        values = resolve_parameters(part)
    frames = {}
    for iface in part.get("interfaces") or []:
        frame = iface.get("frame") or {}
        where = f"{part.get('key')}.{iface.get('id')}.frame"
        scope: Mapping[str, float] = values
        if "let" in iface:
            # ASM-1 v1.1: the interface's derived numbers, in dependency order.
            try:
                scope = {**values, **resolve_let(iface["let"], values, set(values))}
            except FrameEvaluationError as exc:
                raise FrameEvaluationError(f"{part.get('key')}.{iface.get('id')}: {exc}") from None
        frames[iface["id"]] = Frame(
            origin=_vector(frame.get("origin"), scope, f"{where}.origin"),
            normal=_vector(frame.get("normal"), scope, f"{where}.normal"),
            x_axis=_vector(frame.get("x_axis"), scope, f"{where}.x_axis"),
        )
    return frames


@dataclass(frozen=True)
class BeltEngagement:
    """Where a belt wraps a part (ASM-1 §9), evaluated at a parameter point, in the part's
    model frame (mm). A toothed part (``toothed``) states the diameter the belt's pitch
    line runs on; a smooth part states the diameter of its running surface, and a path adds
    the belt's pitch-line offset for the side on it. ``center`` is a point on the axis in
    the belt mid-plane; ``axis`` is as written (the catalog check holds it to unit length)."""

    toothed: bool
    diameter_mm: float
    center: Vector
    axis: Vector

    @property
    def pitch_diameter_mm(self) -> float | None:
        return self.diameter_mm if self.toothed else None


def _positive_mm(dim: object) -> float | None:
    value = dim.get("value") if isinstance(dim, Mapping) else None
    if (isinstance(value, bool) or not isinstance(value, int | float) or value <= 0
            or dim.get("unit") != "mm"):
        return None
    return float(value)


def belt_engagement(part: Mapping, values: Mapping[str, float] | None = None
                    ) -> BeltEngagement | None:
    """The entry's ``belt_engagement`` at ``values`` (defaults when omitted), or None when
    the entry declares none. Raises :class:`FrameEvaluationError` when a component does not
    evaluate, or ValueError when the diameter is not one positive number in mm."""
    block = part.get("belt_engagement")
    if not isinstance(block, Mapping):
        return None
    if values is None:
        values = resolve_parameters(part)
    where = f"{part.get('key')}.belt_engagement"
    stated = [k for k in ("pitch_diameter", "running_diameter") if k in block]
    if len(stated) != 1:
        raise ValueError(f"{where} must state exactly one of pitch_diameter and "
                         f"running_diameter, not {stated or 'neither'}")
    diameter = _positive_mm(block[stated[0]])
    if diameter is None:
        raise ValueError(f"{where}.{stated[0]} must be a positive number in mm, "
                         f"not {block[stated[0]]!r}")
    return BeltEngagement(
        toothed=stated[0] == "pitch_diameter",
        diameter_mm=diameter,
        center=_vector(block.get("center"), values, f"{where}.center"),
        axis=_vector(block.get("axis"), values, f"{where}.axis"),
    )


#: The ``belt`` block's dimensions and the name each takes in :func:`belt_facts`.
BELT_FACTS = {
    "pitch": "pitch_mm",
    "width": "width_mm",
    "height": "height_mm",
    "tooth_depth": "tooth_depth_mm",
    "pitch_line_differential": "pitch_line_differential_mm",
    "teeth_side_offset": "teeth_side_offset_mm",
    "back_side_offset": "back_side_offset_mm",
    "loop_length": "loop_length_mm",
}


def belt_facts(part: Mapping) -> dict[str, float] | None:
    """A belt entry's facts in mm (ASM-1 §9) — ``pitch_mm`` and ``width_mm`` always, the
    others when stated — or None when the entry is not a belt (category ``belt`` with a
    ``belt`` block whose stated facts are all positive numbers in mm)."""
    block = part.get("belt")
    if part.get("category") != "belt" or not isinstance(block, Mapping):
        return None
    out = {}
    for name, key in BELT_FACTS.items():
        if name not in block:
            if name in ("pitch", "width"):
                return None
            continue
        value = _positive_mm(block[name])
        if value is None:
            return None
        out[key] = value
    return out


#: The envelope solid shapes (ASM-1 §3.7): an axis-aligned box, or a cylinder along a
#: model axis. Their union is the part's collision body.
ENVELOPE_SHAPES = ("box", "cylinder")


def envelope_solids(envelope: object, values: Mapping[str, float] | None = None,
                    where: str = "envelope") -> list[dict] | None:
    """An `envelope` (`{"solids": [...]}`) evaluated at `values`: every box as
    `{"shape": "box", "min": (x, y, z), "max": (x, y, z)}` and every cylinder as
    `{"shape": "cylinder", "base": (x, y, z), "axis": "x"|"y"|"z", "radius": r,
    "length": l}`, in mm in the part's model frame. None when there is no envelope.
    Raises FrameEvaluationError or ValueError naming the solid that does not evaluate
    or is degenerate (min ≥ max, radius or length ≤ 0)."""
    if not isinstance(envelope, Mapping):
        return None
    values = dict(values or {})
    out = []
    for i, solid in enumerate(envelope.get("solids") or []):
        at = f"{where}.solids[{i}]"
        shape = solid.get("shape") if isinstance(solid, Mapping) else None
        if shape == "box":
            low = _vector(solid.get("min"), values, f"{at}.min")
            high = _vector(solid.get("max"), values, f"{at}.max")
            if not all(a < b for a, b in zip(low, high, strict=True)):
                raise ValueError(f"{at}: min {low} is not below max {high} on every axis")
            out.append({"shape": "box", "min": low, "max": high})
        elif shape == "cylinder":
            base = _vector(solid.get("base"), values, f"{at}.base")
            radius = evaluate_expression(solid.get("radius"), values, set(values))
            length = evaluate_expression(solid.get("length"), values, set(values))
            if solid.get("axis") not in ("x", "y", "z") or radius <= 0 or length <= 0:
                raise ValueError(f"{at}: a cylinder needs axis x|y|z and a positive radius "
                                 f"and length (got {solid.get('axis')!r}, {radius:g}, {length:g})")
            out.append({"shape": "cylinder", "base": base, "axis": solid["axis"],
                        "radius": radius, "length": length})
        else:
            raise ValueError(f"{at}: shape {shape!r} is not one of {', '.join(ENVELOPE_SHAPES)}")
    return out


def part_digest(part: Mapping) -> str:
    """sha256 hex of the entry's canonical JSON (GOC-1 ``canonical_json``) — the standard
    part's resolved identity inside an assembly digest (ASM-1 §3.8)."""
    from hyperobjects_schemas.generator_output import canonical_json

    return hashlib.sha256(canonical_json(dict(part))).hexdigest()
