"""What a component resolver yields, and the manifest-shaped helpers every resolver shares.

The validator never reads a file. It asks a `ComponentResolver` for each component and
gets back a `ResolvedComponent`: the component's interfaces with their frames already
evaluated (`y4d_spec.frame_eval.Frame`), their `size_key` already resolved against the
component's parameters, and an `identity` — the canonical-JSON-able object that enters
the assembly digest (ASM-1 §3.8). Three resolvers ship in `resolvers.py` (commons
manifests, a standard-parts directory, external inline facts); any other store — the
asset-shells service resolving from stored MatingInterfaces and ParametricModel
submodels — implements the same one-method protocol and reuses the helpers here, so
the frame arithmetic, parameter checks and instance identity stay in one place.

    resolve_interfaces(manifest, values, available_parts=...)  -> {id: ResolvedInterface}
    parameter_value_problems(parameters, given)                -> [problem, ...]
    goc1_variables(parameters, values)                          -> {id: value | None}
    cartridge_identity(slug=, mode=, part=, tree_sha256=, variables=) -> identity dict
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from hyperobjects_schemas import load as load_schema
from hyperobjects_schemas.generator_output import instance_id, variables_sha256

from ..frame_eval import Frame, FrameEvaluationError, evaluate_frame, resolve_parameters
from ..semantic_rules import canonical_number_key

__all__ = [
    "ENGINE_CONTROL_KEYS",
    "ComponentResolver",
    "ResolutionError",
    "ResolvedComponent",
    "ResolvedInterface",
    "cartridge_identity",
    "goc1_variables",
    "parameter_value_problems",
    "resolve_interfaces",
    "resolve_size_key",
    "slider_size_key_miss",
]

#: GOC-1 §4 rule 3 — engine-control keys select a mode or a body; they are not
#: variables and do not enter `variables_sha256`.
ENGINE_CONTROL_KEYS = frozenset({"render_mode", "target_part", "mode"})


class ResolutionError(ValueError):
    """A component could not be resolved. `problems` lists every reason."""

    def __init__(self, problems: Iterable[str]):
        self.problems = list(problems) or ["could not be resolved"]
        super().__init__("; ".join(self.problems))


@dataclass(frozen=True)
class ResolvedInterface:
    """One interface of a resolved component, ready to mate (or saying why it is not).

    `problems` is empty when the interface can take part in a mate check. A missing
    `polarity` / `size_key` / `symmetry` is NOT a problem here: the mate check names
    each missing field itself, with the mate it blocks.
    """

    id: str
    frame: Frame | None
    polarity: str | None
    size_key: str | None
    symmetry: int | None
    problems: tuple[str, ...] = ()
    #: Why `size_key` is None at this point when the interface DOES declare one: a
    #: slider map (ASM-1 v1.1) with no entry for the slider's value. A mate that needs
    #: the key names this reason instead of "declares no size_key".
    size_key_absent_reason: str | None = None


@dataclass(frozen=True)
class ResolvedComponent:
    """A component as the validator sees it.

    `identity` enters the assembly digest and must be canonical-JSON-able and
    deterministic. `details` is informative only (printed, never hashed).
    """

    component_id: str
    source_type: str
    label: str
    identity: Mapping
    interfaces: Mapping[str, ResolvedInterface]
    details: Mapping = field(default_factory=dict)


@runtime_checkable
class ComponentResolver(Protocol):
    """Resolve one `components[]` entry of an assembly document.

    Return a ResolvedComponent, or raise ResolutionError naming every problem
    (unknown cartridge, undeclared or out-of-range parameter, unknown standard key…).
    A resolver must be deterministic: the same entry and the same store give the same
    identity, or the assembly digest is meaningless.
    """

    def resolve(self, component: Mapping) -> ResolvedComponent: ...


# ── parameters ────────────────────────────────────────────────────────────────
def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _declared(parameters: object) -> dict[str, Mapping]:
    if not isinstance(parameters, list):
        return {}
    return {
        p["id"]: p
        for p in parameters
        if isinstance(p, Mapping) and isinstance(p.get("id"), str)
    }


def parameter_value_problems(parameters: object, given: Mapping | None) -> list[str]:
    """Why `given` is not a valid point of this parameter list (empty = valid).

    ASM-1 §3.2: every key must be a declared parameter and every value must be
    admissible — inside [min, max] for a slider or number, an option value for a
    select, a boolean for a checkbox, a string for text. Nothing is clamped: an
    out-of-range value is a problem, because the assembly would otherwise silently
    describe a part other than the one it names.
    """
    declared = _declared(parameters)
    problems: list[str] = []
    for key in sorted((given or {}).keys()):
        value = (given or {})[key]
        param = declared.get(key)
        if param is None:
            known = ", ".join(sorted(declared)) or "none"
            problems.append(f"parameter '{key}' is not declared (declared: {known})")
            continue
        ptype = param.get("type")
        if ptype == "checkbox":
            if not isinstance(value, bool):
                problems.append(f"parameter '{key}' is a checkbox; {value!r} is not a boolean")
        elif ptype == "select":
            options = [o.get("value") for o in param.get("options") or []
                       if isinstance(o, Mapping) and "value" in o]
            if isinstance(value, bool) or value not in options:
                shown = ", ".join(repr(o) for o in options) or "none"
                problems.append(
                    f"parameter '{key}' = {value!r} is not one of its options ({shown})"
                )
        elif ptype == "text":
            if not isinstance(value, str):
                problems.append(f"parameter '{key}' is text; {value!r} is not a string")
        else:  # slider, number, or an untyped standard-part dimension
            if not _is_number(value) or not math.isfinite(value):
                problems.append(f"parameter '{key}' = {value!r} is not a finite number")
                continue
            lo, hi = param.get("min"), param.get("max")
            if _is_number(lo) and value < lo:
                problems.append(
                    f"parameter '{key}' = {value:g} is below its minimum {lo:g} "
                    "(out of range is an error, never clamped)"
                )
            if _is_number(hi) and value > hi:
                problems.append(
                    f"parameter '{key}' = {value:g} is above its maximum {hi:g} "
                    "(out of range is an error, never clamped)"
                )
    return problems


def _physical_denylist() -> tuple[frozenset[str], tuple[re.Pattern, ...]]:
    """GOC-1 §4 rule 4, read from the generator-output schema rather than copied."""
    id_schema = load_schema("generator-output")["$defs"]["variable"]["properties"]["id"]
    exact: set[str] = set()
    patterns: list[re.Pattern] = []
    for clause in id_schema.get("not", {}).get("anyOf", []):
        exact.update(clause.get("enum", []))
        if "pattern" in clause:
            patterns.append(re.compile(clause["pattern"]))
    return frozenset(exact), tuple(patterns)


def goc1_variables(parameters: object, values: Mapping) -> dict[str, object]:
    """The GOC-1 `variables` of a full-injection render, as `{id: value}`.

    Every declared parameter (no mode scoping, GOC-1 §4.1) except the engine-control
    keys and the physical denylist (§4.3–4.4). A parameter with neither a default nor
    a given value was not injected and contributes `None` (a `source_default` entry).
    """
    exact, patterns = _physical_denylist()
    out: dict[str, object] = {}
    for pid in _declared(parameters):
        if pid in ENGINE_CONTROL_KEYS or pid in exact or any(p.search(pid) for p in patterns):
            continue
        out[pid] = values.get(pid)
    return out


def cartridge_identity(
    *, slug: str, mode: str, part: str | None, tree_sha256: str, variables: Mapping
) -> tuple[dict, dict]:
    """(identity, details) of a cartridge component. The identity is the GOC-1
    `instance_id` (§3.4) of the render this component stands for; details add its
    two inputs for the placement table."""
    v_sha = variables_sha256(variables)
    iid = instance_id(
        cartridge=slug, mode=mode, part=part, tree_sha256=tree_sha256, variables_sha256=v_sha
    )
    identity = {"type": "cartridge", "instance_id": iid}
    details = {"tree_sha256": tree_sha256, "variables_sha256": v_sha, "instance_id": iid}
    return identity, details


# ── interfaces ────────────────────────────────────────────────────────────────
def resolve_size_key(
    size_key: object, values: Mapping, parameters: Mapping[str, Mapping] | None = None
) -> tuple[str | None, str | None]:
    """(resolved key, problem). A string is itself; {param, map} looks the parameter's
    resolved value up in `map`.

    A select is looked up by its option value's string form (SEM-1 §2.3); a value with
    no entry is a problem. A slider or number (ASM-1 v1.1) is looked up by its GOC-1
    canonical spelling (`12.0` → `"12"`): an exact value or nothing, and nothing is NOT
    a problem — the interface simply has no size key at that point (use
    `slider_size_key_miss` to say why). `parameters` ({id: declaration}) tells the two
    apart; without it the lookup tries the string form, then the canonical one.
    """
    if size_key is None:
        return None, None
    if isinstance(size_key, str):
        return (size_key, None) if size_key else (None, "size_key is empty")
    if isinstance(size_key, Mapping):
        param, mapping = size_key.get("param"), size_key.get("map")
        if not isinstance(param, str) or not isinstance(mapping, Mapping):
            return None, "size_key must be a key or {param, map}"
        if param not in values:
            return None, f"size_key.param '{param}' has no value"
        value = values[param]
        ptype = (parameters or {}).get(param, {}).get("type")
        canonical = canonical_number_key(value)
        if ptype in ("slider", "number"):
            key = mapping.get(canonical) if canonical is not None else None
            if key is None:
                return None, None  # exact values only; otherwise no size key here
        else:
            key = mapping.get(str(value))
            if key is None and ptype is None and canonical is not None:
                key = mapping.get(canonical)
        if not isinstance(key, str) or not key:
            return None, f"size_key.map has no entry for {param} = {value!r}"
        return key, None
    return None, f"size_key {size_key!r} is neither a key nor {{param, map}}"


def slider_size_key_miss(size_key: object, values: Mapping) -> str:
    """The reason a slider size_key resolved to nothing at `values`, for a mate error."""
    param = size_key.get("param") if isinstance(size_key, Mapping) else None
    mapping = size_key.get("map") if isinstance(size_key, Mapping) else None
    keys = ", ".join(map(str, mapping)) if isinstance(mapping, Mapping) else ""
    return (
        f"has no size_key at {param} = {values.get(param)!r}: its slider map matches "
        f"exact values only ({keys or 'none'})"
    )


def resolve_interfaces(
    manifest: Mapping,
    given: Mapping | None = None,
    *,
    available_parts: Iterable[str] | None = None,
    default_part: str | None = None,
) -> dict[str, ResolvedInterface]:
    """Every `hyperobject.cdg_interfaces[]` entry of a manifest-shaped mapping, resolved
    at `given` over the defaults (GOC-1 full injection).

    `available_parts`, when given, is the set of parts the component actually produces
    (its mode's parts, or the one part it names): an interface whose frame sits on
    another part is kept but carries that as a problem. `default_part` fills a frame
    that names no part (a standard part or an external design is one body).
    """
    values = resolve_parameters(manifest, given)
    declared = _declared(manifest.get("parameters"))
    parts = set(available_parts) if available_parts is not None else None
    ho = manifest.get("hyperobject")
    raw = ho.get("cdg_interfaces") if isinstance(ho, Mapping) else None
    out: dict[str, ResolvedInterface] = {}
    for iface in raw if isinstance(raw, list) else []:
        if not isinstance(iface, Mapping) or not isinstance(iface.get("id"), str):
            continue
        problems: list[str] = []
        frame: Frame | None = None
        raw_frame = iface.get("frame")
        if raw_frame is None:
            problems.append("declares no frame (SEM-1 §2.3), so it cannot be placed")
        else:
            if (
                default_part
                and isinstance(raw_frame, Mapping)
                and not raw_frame.get("part")
            ):
                iface = {**iface, "frame": {**raw_frame, "part": default_part}}
            try:
                frame = evaluate_frame(manifest, iface, given)
            except FrameEvaluationError as exc:
                problems.append(f"frame does not evaluate: {exc}")
            if frame is not None and parts is not None and frame.part not in parts:
                problems.append(
                    f"frame sits on part '{frame.part}', which this component does not "
                    f"produce (it produces: {', '.join(sorted(parts)) or 'nothing'})"
                )
        size_key, sk_problem = resolve_size_key(iface.get("size_key"), values, declared)
        if sk_problem:
            problems.append(sk_problem)
        absent = (
            slider_size_key_miss(iface.get("size_key"), values)
            if size_key is None and not sk_problem and iface.get("size_key") is not None
            else None
        )
        symmetry = iface.get("symmetry")
        out[iface["id"]] = ResolvedInterface(
            id=iface["id"],
            frame=frame,
            polarity=iface.get("polarity") if isinstance(iface.get("polarity"), str) else None,
            size_key=size_key,
            symmetry=symmetry if _is_number(symmetry) else None,
            problems=tuple(problems),
            size_key_absent_reason=absent,
        )
    return out
