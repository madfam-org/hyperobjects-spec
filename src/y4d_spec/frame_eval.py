"""Evaluate an interface frame at a parameter point (ASM-1 §1).

    from y4d_spec.frame_eval import evaluate_frame
    frame = evaluate_frame(manifest, "motor_bolt_pattern", {"plate_thick": 5})
    frame.origin, frame.normal, frame.x_axis      # floats; normal and x_axis unit

A frame component is a number or an expression string over parameter ids in the SEM-1
§2.3 grammar: numeric literals, parameter ids, `+ - * /`, parentheses, unary minus and
calls to `min`, `max`, `abs`. The grammar is NOT re-implemented here: every expression
is first put through `semantic_rules.frame_expression_problems`, the same parse-only
check `y4d-spec check` applies statically, and only an expression that passes it is
walked. The walk then evaluates the already-vetted `ast` tree node by node over plain
floats. Nothing is handed to `eval`, `exec` or `compile`, and no attribute, subscript,
comprehension or name outside the parameter table can be reached, because the walker
has no branch for them.

Parameters resolve as GOC-1 "full injection" (ASM-1 §1): every declared parameter
takes its manifest default, then the caller's values override it. Inside an expression
a checkbox is 1 or 0, a select is its option value, and a slider or number is itself.
A value that is not a number (a select whose option is spelled "16x16", a text field)
is an error only when an expression actually reads it.

Errors are `FrameEvaluationError` (a ValueError) and name the interface, the vector,
the component and the parameter point: an unknown identifier, a division by zero, a
non-finite intermediate or result, a zero-length normal, or an `x_axis` more than
`ORTHOGONALITY_LIMIT_DEG` from orthogonal to the normal. Within that limit `x_axis` is
projected onto the plane of the normal (Gram-Schmidt) and renormalised, so the frame
this returns is exactly orthonormal and the assembly placement (ASM-1 §3.4) can build
its matrix without re-checking.

Pure Python, no numpy: the assembly validator imports this with the base install.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping
from dataclasses import dataclass

from .semantic_rules import frame_expression_problems

__all__ = [
    "FRAME_VECTORS",
    "ORTHOGONALITY_LIMIT_DEG",
    "Frame",
    "FrameEvaluationError",
    "evaluate_expression",
    "evaluate_frame",
    "evaluate_vector",
    "expression_value",
    "find_interface",
    "resolve_parameters",
]

#: The vectors a frame declares, in the order SEM-1 §2.3 lists them.
FRAME_VECTORS = ("origin", "normal", "x_axis")
#: How far from orthogonal an evaluated `x_axis` may be before it is an error rather
#: than a rounding to correct. 1° is twice the static rule's 0.5° (semantic_rules
#: ORTHOGONALITY_TOLERANCE_DEG): an expression-driven axis can drift a little across
#: the parameter range, and the projection below removes that drift exactly.
ORTHOGONALITY_LIMIT_DEG = 1.0

Vector = tuple[float, float, float]


class FrameEvaluationError(ValueError):
    """A frame could not be evaluated at a parameter point. The message says why."""


@dataclass(frozen=True)
class Frame:
    """An evaluated interface frame, in the part's model coordinates (mm)."""

    part: str
    origin: Vector
    #: Unit length.
    normal: Vector
    #: Unit length and exactly orthogonal to `normal`, or None when the frame
    #: declares no `x_axis` (allowed only for symmetry 0).
    x_axis: Vector | None

    def reference_x_axis(self) -> Vector:
        """`x_axis`, or a deterministic unit perpendicular to `normal` when absent.

        The fallback is the world axis least aligned with `normal`, made orthogonal to
        it. It is a convention for building a matrix, not a fact about the part: an
        interface without `x_axis` has continuous symmetry, so any perpendicular is as
        good as any other for placement.
        """
        if self.x_axis is not None:
            return self.x_axis
        n = self.normal
        axes = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        seed = min(axes, key=lambda a: abs(_dot(a, n)))
        return _unit(_sub(seed, _scale(n, _dot(seed, n))))

    def homogeneous(self) -> tuple[tuple[float, float, float, float], ...]:
        """H(F) of ASM-1 §3.4: the 4×4 matrix with columns (x, y, n, o), y = n × x."""
        x = self.reference_x_axis()
        n = self.normal
        y = _cross(n, x)
        o = self.origin
        return (
            (x[0], y[0], n[0], o[0]),
            (x[1], y[1], n[1], o[1]),
            (x[2], y[2], n[2], o[2]),
            (0.0, 0.0, 0.0, 1.0),
        )


# ── small vector helpers (pure Python) ────────────────────────────────────────
def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b) -> Vector:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b) -> Vector:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a, k: float) -> Vector:
    return (a[0] * k, a[1] * k, a[2] * k)


def _norm(a) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a) -> Vector:
    length = _norm(a)
    return (a[0] / length, a[1] / length, a[2] / length)


# ── parameters ────────────────────────────────────────────────────────────────
def _declared(manifest: Mapping) -> dict[str, dict]:
    return {
        p["id"]: p
        for p in manifest.get("parameters") or []
        if isinstance(p, dict) and isinstance(p.get("id"), str)
    }


def resolve_parameters(manifest: Mapping, given: Mapping | None = None) -> dict:
    """GOC-1 full injection: every declared default, overridden by `given`.

    Returns the raw values (a checkbox stays a bool, a select its option value) — the
    same dictionary a full-injection render passes to the script. Keys of `given` that
    the manifest does not declare are carried along unchanged: they reach the script,
    but an expression can never read them (identifiers must be declared parameters).
    Range checking is the caller's: ASM-1 §3 makes an out-of-range component value an
    assembly error, and a preset is the manifest's own value.
    """
    values: dict = {}
    for pid, param in _declared(manifest).items():
        if "default" in param:
            values[pid] = param["default"]
    for key, value in (given or {}).items():
        values[key] = value
    return values


def expression_value(name: str, value: object) -> float:
    """The number a resolved parameter value stands for inside an expression.

    Checkbox (bool) → 1.0 / 0.0; int / float → itself; a string that spells a number
    (a select whose options are "4", "6") → that number. Anything else raises.
    """
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        out = float(value)
    elif isinstance(value, str):
        try:
            out = float(value.strip())
        except ValueError:
            raise FrameEvaluationError(
                f"parameter '{name}' resolves to {value!r}, which is not a number"
            ) from None
    else:
        raise FrameEvaluationError(
            f"parameter '{name}' resolves to {value!r}, which is not a number"
        )
    if not math.isfinite(out):
        raise FrameEvaluationError(f"parameter '{name}' resolves to non-finite {value!r}")
    return out


# ── expressions ───────────────────────────────────────────────────────────────
def _finite(value: float, what: str) -> float:
    if not math.isfinite(value):
        raise FrameEvaluationError(f"{what} is not finite ({value})")
    return value


def _walk(node: ast.AST, values: Mapping[str, object], expr: str) -> float:
    """Evaluate a tree frame_expression_problems has already accepted."""
    if isinstance(node, ast.Constant):
        return _finite(float(node.value), f"literal {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id not in values:
            # Declared but with no default and no given value: nothing to read.
            raise FrameEvaluationError(
                f"parameter '{node.id}' has no value (no default and none given)"
            )
        return expression_value(node.id, values[node.id])
    if isinstance(node, ast.UnaryOp):
        operand = _walk(node.operand, values, expr)
        return -operand if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.BinOp):
        left = _walk(node.left, values, expr)
        right = _walk(node.right, values, expr)
        if isinstance(node.op, ast.Add):
            out = left + right
        elif isinstance(node.op, ast.Sub):
            out = left - right
        elif isinstance(node.op, ast.Mult):
            out = left * right
        else:  # ast.Div — the only other operator the grammar admits
            if right == 0.0:
                raise FrameEvaluationError(f"division by zero in {expr!r}")
            out = left / right
        return _finite(out, f"an intermediate value of {expr!r}")
    if isinstance(node, ast.Call):
        args = [_walk(a, values, expr) for a in node.args]
        name = node.func.id  # type: ignore[attr-defined] — vetted: a FRAME_FUNCS name
        if name == "abs":
            return abs(args[0])
        return min(args) if name == "min" else max(args)
    # Unreachable for a vetted tree; refuse rather than guess if the grammar grows.
    raise FrameEvaluationError(f"unsupported syntax {type(node).__name__} in {expr!r}")


def evaluate_expression(
    component: object, values: Mapping[str, object], declared: set[str] | None = None
) -> float:
    """One frame component — a number or an expression string — as a finite float.

    `values` is the resolved parameter table (resolve_parameters). `declared` is the
    set of identifiers an expression may name; it defaults to the keys of `values`.
    The expression must pass the SEM-1 grammar check first; its problems are the error.
    """
    if isinstance(component, bool):
        raise FrameEvaluationError(f"{component!r} is a boolean, not a number")
    if isinstance(component, (int, float)):
        return _finite(float(component), f"literal {component!r}")
    if not isinstance(component, str):
        raise FrameEvaluationError(f"{component!r} is neither a number nor an expression")
    ids = set(values) if declared is None else declared
    problems = frame_expression_problems(component, ids)
    if problems:
        raise FrameEvaluationError(f"expression {component!r} {'; '.join(problems)}")
    tree = ast.parse(component, mode="eval")
    return _walk(tree.body, values, component)


def evaluate_vector(
    vector: object, values: Mapping[str, object], declared: set[str] | None = None
) -> Vector:
    """A 3-component frame vector as floats (not normalised)."""
    if not isinstance(vector, (list, tuple)) or len(vector) != 3:
        raise FrameEvaluationError(f"{vector!r} is not a list of exactly 3 components")
    out = []
    for i, component in enumerate(vector):
        try:
            out.append(evaluate_expression(component, values, declared))
        except FrameEvaluationError as exc:
            raise FrameEvaluationError(f"[{i}]: {exc}") from None
    return (out[0], out[1], out[2])


# ── frames ────────────────────────────────────────────────────────────────────
def find_interface(manifest: Mapping, interface_id: str) -> dict:
    """The `hyperobject.cdg_interfaces[]` entry with this id."""
    ho = manifest.get("hyperobject")
    for iface in (ho.get("cdg_interfaces") if isinstance(ho, dict) else None) or []:
        if isinstance(iface, dict) and iface.get("id") == interface_id:
            return iface
    raise FrameEvaluationError(f"no cdg_interface '{interface_id}' in this manifest")


def evaluate_frame(
    manifest: Mapping, interface: Mapping | str, params: Mapping | None = None
) -> Frame:
    """The interface's frame at `params` (full injection over the manifest defaults).

    `interface` is a `cdg_interfaces[]` entry or its id. Returns origin as-is, normal
    as a unit vector, and x_axis as a unit vector made exactly orthogonal to the
    normal — or None when the frame declares none. Raises FrameEvaluationError.
    """
    iface = find_interface(manifest, interface) if isinstance(interface, str) else interface
    label = f"cdg_interface '{iface.get('id', '?')}'"
    frame = iface.get("frame")
    if not isinstance(frame, Mapping):
        raise FrameEvaluationError(f"{label}: declares no frame")
    part = frame.get("part")
    if not isinstance(part, str) or not part:
        raise FrameEvaluationError(f"{label}: frame.part must name a part")

    values = resolve_parameters(manifest, params)
    declared = set(_declared(manifest))
    vectors: dict[str, Vector] = {}
    for key in FRAME_VECTORS:
        if key not in frame:
            if key == "x_axis":
                continue
            raise FrameEvaluationError(f"{label}: frame.{key} is required")
        try:
            vectors[key] = evaluate_vector(frame[key], values, declared)
        except FrameEvaluationError as exc:
            raise FrameEvaluationError(f"{label}: frame.{key}{exc}") from None

    if _norm(vectors["normal"]) == 0.0:
        raise FrameEvaluationError(f"{label}: frame.normal evaluates to the zero vector")
    normal = _unit(vectors["normal"])

    x_axis: Vector | None = None
    if "x_axis" in vectors:
        raw = vectors["x_axis"]
        if _norm(raw) == 0.0:
            raise FrameEvaluationError(f"{label}: frame.x_axis evaluates to the zero vector")
        x = _unit(raw)
        cos = max(-1.0, min(1.0, _dot(x, normal)))
        off = abs(90.0 - math.degrees(math.acos(cos)))
        if off > ORTHOGONALITY_LIMIT_DEG:
            raise FrameEvaluationError(
                f"{label}: frame.x_axis is {off:.3f}° from orthogonal to frame.normal "
                f"(limit {ORTHOGONALITY_LIMIT_DEG}°)"
            )
        x_axis = _unit(_sub(x, _scale(normal, _dot(x, normal))))

    return Frame(part=part, origin=vectors["origin"], normal=normal, x_axis=x_axis)
