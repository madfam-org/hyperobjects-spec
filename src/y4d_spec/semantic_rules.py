"""Static rules for the semantic manifest fields of SEM-1 §2.3–§2.4.

Two families, both pure functions over a parsed manifest, in the house shape of
rules.py (a list of human-readable problems; empty = conformant):

  interface_frame_rules   hyperobject.cdg_interfaces[].{frame, polarity, size_key, symmetry}
  requirements_rules      the top-level `requirements` profile and its per-part overrides

The schema already says what TYPE each field is. These rules say what the schema
cannot: that a frame expression parses and names real parameters, that a numeric
normal is not the zero vector, that `x_axis` is orthogonal to `normal`, that a
`size_key` driven by a select covers every option, that `min <= max`, and that a
per-part override names a part this cartridge declares. Each rule also re-checks the
shape it depends on, so a manifest checked without the schema still gets a verdict
rather than a traceback.

Deliberately NOT here:
  * vocabulary membership (is `nema-17-face` an interface-sizes key, is `tpu-95a` a
    material class) — the lexicon rule owns it (SEM-1 §4);
  * whether a frame matches the geometry — the render-time frame gate owns it. A frame
    that passes these rules is well-formed, not trusted.

The frame expression grammar is SEM-1 §2.3's: numeric literals, parameter ids,
`+ - * /`, parentheses, unary minus, and calls to `min`, `max`, `abs`. It is the
arithmetic core of the Studio's constraint dialect (see the `constraints` description
in project-manifest.schema.json) plus the three numeric builtins SEM-1 names, which
are a subset of `fc_spec.rules.SAFE_MAP_FUNCS`. Like that params_map check, it is
PARSED with Python's `ast` and walked node by node; nothing is ever evaluated.
"""

from __future__ import annotations

import ast
import math
import re

__all__ = [
    "FRAME_FUNCS",
    "FRAME_EXPRESSION_MAX_LENGTH",
    "ORTHOGONALITY_TOLERANCE_DEG",
    "POLARITIES",
    "SYMMETRY_ORDERS",
    "frame_expression_problems",
    "interface_frame_rules",
    "requirements_rules",
]

#: Calls a frame expression may make, with their (min, max) argument counts.
FRAME_FUNCS: dict[str, tuple[int, int | None]] = {"min": (2, None), "max": (2, None),
                                                    "abs": (1, 1)}
#: The constraint dialect's source cap, applied to frame expressions too.
FRAME_EXPRESSION_MAX_LENGTH = 256
#: How far from orthogonal a numeric x_axis may sit against a numeric normal. The same
#: angle SEM-1 §2.3 uses for antiparallel normals in the mating rule.
ORTHOGONALITY_TOLERANCE_DEG = 0.5
POLARITIES = ("male", "female", "neutral")
SYMMETRY_ORDERS = (0, 1, 2, 3, 4, 6, 8)

_FRAME_VECTORS = ("origin", "normal", "x_axis")
_EXPR_CHARS = re.compile(r"^[A-Za-z0-9_.+\-*/(),\s]+$")
_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_UNARYOPS = (ast.USub, ast.UAdd)


def _ids(entries: object) -> set[str]:
    if not isinstance(entries, list):
        return set()
    return {e["id"] for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ── frame expressions ─────────────────────────────────────────────────────────
def frame_expression_problems(expr: str, param_ids: set[str]) -> list[str]:
    """Why `expr` is not a valid frame component expression (empty = valid).

    Parse-only. A name is a parameter reference unless it is the target of a call to
    one of FRAME_FUNCS; every reference must be one of `param_ids`.
    """
    if len(expr) > FRAME_EXPRESSION_MAX_LENGTH:
        return [f"is longer than {FRAME_EXPRESSION_MAX_LENGTH} characters"]
    if not expr.strip():
        return ["is empty"]
    if not _EXPR_CHARS.match(expr):
        return ["uses a character outside the grammar (digits, parameter ids, + - * / ( ) ,)"]
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        return [f"does not parse: {exc.msg}"]

    problems: list[str] = []

    def walk(node: ast.AST) -> None:
        if isinstance(node, ast.Constant):
            if not _is_number(node.value):
                problems.append(f"has a non-numeric literal {node.value!r}")
        elif isinstance(node, ast.Name):
            if node.id not in param_ids:
                problems.append(f"references unknown parameter '{node.id}'")
        elif isinstance(node, ast.BinOp):
            if not isinstance(node.op, _BINOPS):
                problems.append(f"uses unsupported operator {type(node.op).__name__}")
            walk(node.left)
            walk(node.right)
        elif isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, _UNARYOPS):
                problems.append(f"uses unsupported operator {type(node.op).__name__}")
            walk(node.operand)
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name not in FRAME_FUNCS:
                problems.append(
                    f"calls '{name or '<expression>'}', not one of {', '.join(FRAME_FUNCS)}"
                )
            else:
                lo, hi = FRAME_FUNCS[name]
                n = len(node.args)
                if n < lo or (hi is not None and n > hi):
                    want = str(lo) if hi == lo else f"at least {lo}"
                    problems.append(f"calls {name}() with {n} argument(s), needs {want}")
            if node.keywords:
                problems.append("uses keyword arguments")
            for arg in node.args:
                walk(arg)
        else:
            problems.append(f"uses unsupported syntax ({type(node).__name__})")

    walk(tree.body)
    return problems


# ── interface frame / polarity / size_key / symmetry ─────────────────────────
def _vector_problems(where: str, vec: object, param_ids: set[str]) -> tuple[list[str], list]:
    """Problems with one frame vector, and its numeric value when fully numeric."""
    if not isinstance(vec, list) or len(vec) != 3:
        return [f"{where}: must be a list of exactly 3 components"], []
    problems: list[str] = []
    numeric: list[float] = []
    for i, comp in enumerate(vec):
        if _is_number(comp):
            if not math.isfinite(comp):
                problems.append(f"{where}[{i}]: must be finite")
            numeric.append(float(comp))
        elif isinstance(comp, str):
            for p in frame_expression_problems(comp, param_ids):
                problems.append(f"{where}[{i}]: expression {comp!r} {p}")
        else:
            problems.append(f"{where}[{i}]: must be a number or an expression string")
    return problems, (numeric if len(numeric) == 3 and not problems else [])


def _frame_problems(label: str, frame: object, doc: dict, symmetry: object) -> list[str]:
    if not isinstance(frame, dict):
        return [f"{label} frame: must be an object"]
    problems: list[str] = []
    part_ids = _ids(doc.get("parts"))
    part = frame.get("part")
    if not isinstance(part, str) or not part:
        problems.append(f"{label} frame.part: required, must name a part")
    elif part not in part_ids:
        problems.append(
            f"{label} frame.part: '{part}' is not a declared part "
            f"(parts declare: {', '.join(sorted(part_ids)) or 'none'})"
        )

    param_ids = _ids(doc.get("parameters"))
    numeric: dict[str, list] = {}
    for key in _FRAME_VECTORS:
        if key not in frame:
            if key != "x_axis":
                problems.append(f"{label} frame.{key}: required")
            continue
        vec_problems, value = _vector_problems(f"{label} frame.{key}", frame[key], param_ids)
        problems.extend(vec_problems)
        if value:
            numeric[key] = value

    for key in ("normal", "x_axis"):
        if key in numeric and math.hypot(*numeric[key]) == 0.0:
            problems.append(f"{label} frame.{key}: is the zero vector, which has no direction")

    needs_x = _is_number(symmetry) and symmetry != 0
    if needs_x and "x_axis" not in frame:
        problems.append(
            f"{label} frame.x_axis: required when symmetry is {symmetry} — without a "
            "reference direction the orientation cannot be compared modulo the symmetry"
        )

    n, x = numeric.get("normal"), numeric.get("x_axis")
    if n and x and math.hypot(*n) > 0 and math.hypot(*x) > 0:
        cos = sum(a * b for a, b in zip(n, x, strict=True)) / (math.hypot(*n) * math.hypot(*x))
        off = abs(90.0 - math.degrees(math.acos(max(-1.0, min(1.0, cos)))))
        if off > ORTHOGONALITY_TOLERANCE_DEG:
            problems.append(
                f"{label} frame.x_axis: is {off:.3f}° from orthogonal to frame.normal "
                f"(tolerance {ORTHOGONALITY_TOLERANCE_DEG}°)"
            )
    return problems


def _size_key_problems(label: str, size_key: object, doc: dict) -> list[str]:
    if isinstance(size_key, str):
        return [] if size_key else [f"{label} size_key: must not be empty"]
    if not isinstance(size_key, dict):
        return [f"{label} size_key: must be a key string or an object {{param, map}}"]
    param_id, mapping = size_key.get("param"), size_key.get("map")
    if not isinstance(mapping, dict) or not mapping:
        return [f"{label} size_key.map: required, must be a non-empty object"]
    problems = [
        f"{label} size_key.map['{k}']: must be a non-empty key string"
        for k, v in mapping.items()
        if not isinstance(v, str) or not v
    ]
    params = {p["id"]: p for p in doc.get("parameters") or []
              if isinstance(p, dict) and isinstance(p.get("id"), str)}
    if not isinstance(param_id, str) or param_id not in params:
        problems.append(f"{label} size_key.param: {param_id!r} is not a declared parameter")
        return problems
    param = params[param_id]
    if param.get("type") != "select":
        problems.append(
            f"{label} size_key.param: '{param_id}' is a {param.get('type')!r} parameter; "
            "only a select chooses among sizes"
        )
        return problems
    values = [str(o["value"]) for o in param.get("options") or []
              if isinstance(o, dict) and "value" in o]
    for v in values:
        if v not in mapping:
            problems.append(f"{label} size_key.map: option '{v}' of '{param_id}' has no entry")
    for k in mapping:
        if k not in values:
            problems.append(
                f"{label} size_key.map: key '{k}' is not an option of '{param_id}' "
                f"(options: {', '.join(values) or 'none'})"
            )
    return problems


def interface_frame_rules(doc: dict) -> list[str]:
    """Interface frames parse, point somewhere, and agree with their symmetry (SEM-1 §2.3).

    Per hyperobject.cdg_interfaces[] entry, for whichever of the four fields it declares:
    `frame` — `part` names a declared part, `origin`/`normal`/`x_axis` are 3 components
    each a number or a parseable expression over declared parameters, a numeric
    `normal`/`x_axis` is non-zero, `x_axis` is present when `symmetry` != 0, and a numeric
    `x_axis` is orthogonal to a numeric `normal` within ORTHOGONALITY_TOLERANCE_DEG;
    `polarity` — one of POLARITIES; `symmetry` — one of SYMMETRY_ORDERS; `size_key` — a
    key, or {param, map} where `param` is a declared select and `map` covers exactly its
    options.
    """
    top_ho = doc.get("hyperobject") if isinstance(doc.get("hyperobject"), dict) else {}
    interfaces = top_ho.get("cdg_interfaces")
    if not isinstance(interfaces, list):
        return []
    problems: list[str] = []
    for i, iface in enumerate(interfaces):
        if not isinstance(iface, dict):
            continue
        label = f"cdg_interface '{iface.get('id', i)}':"
        symmetry = iface.get("symmetry")
        if "symmetry" in iface and (not _is_number(symmetry) or symmetry not in SYMMETRY_ORDERS):
            problems.append(
                f"{label} symmetry: {symmetry!r} is not one of "
                f"{', '.join(map(str, SYMMETRY_ORDERS))}"
            )
        if "polarity" in iface and iface["polarity"] not in POLARITIES:
            problems.append(
                f"{label} polarity: {iface['polarity']!r} is not one of {', '.join(POLARITIES)}"
            )
        if "frame" in iface:
            problems.extend(_frame_problems(label, iface["frame"], doc, symmetry))
        elif _is_number(symmetry) and symmetry != 0:
            problems.append(
                f"{label} frame.x_axis: required when symmetry is {symmetry}, and the "
                "interface declares no frame"
            )
        if "size_key" in iface:
            problems.extend(_size_key_problems(label, iface["size_key"], doc))
    return problems


# ── requirements ──────────────────────────────────────────────────────────────
def _requirement_set_problems(where: str, req: dict) -> list[str]:
    problems: list[str] = []
    mats = req.get("materials")
    if isinstance(mats, dict):
        any_of, none_of = mats.get("any_of"), mats.get("none_of")
        if isinstance(any_of, list) and isinstance(none_of, list):
            both = sorted({m for m in any_of if isinstance(m, str)} & set(none_of))
            if both:
                problems.append(
                    f"{where}.materials: {', '.join(both)} is both accepted (any_of) and "
                    "refused (none_of)"
                )
    params = req.get("process_parameters")
    if isinstance(params, dict):
        for key, bound in params.items():
            if not isinstance(bound, dict):
                problems.append(f"{where}.process_parameters.{key}: must be an object")
                continue
            if not any(k in bound for k in ("min", "max", "value")):
                problems.append(
                    f"{where}.process_parameters.{key}: states no bound (min, max or value)"
                )
            lo, hi = bound.get("min"), bound.get("max")
            if _is_number(lo) and _is_number(hi) and lo > hi:
                problems.append(
                    f"{where}.process_parameters.{key}: min {lo:g} is greater than max {hi:g}"
                )
    return problems


def requirements_rules(doc: dict) -> list[str]:
    """The requirement profile is satisfiable and its overrides name real parts (SEM-1 §2.4).

    Every `process_parameters` bound states one of min/max/value and has `min <= max`; no
    material class is both in `any_of` and `none_of`; every key of `requirements.parts`
    is a declared part id, and each override obeys the same rules. Whether the keys are
    vocabulary terms is the lexicon rule's question, not this one's.
    """
    req = doc.get("requirements")
    if req is None:
        return []
    if not isinstance(req, dict):
        return ["requirements: must be an object"]
    problems = _requirement_set_problems("requirements", req)
    overrides = req.get("parts")
    if overrides is None:
        return problems
    if not isinstance(overrides, dict):
        return [*problems, "requirements.parts: must be an object keyed by part id"]
    part_ids = _ids(doc.get("parts"))
    for part, override in overrides.items():
        where = f"requirements.parts['{part}']"
        if part not in part_ids:
            problems.append(
                f"{where}: '{part}' is not a declared part "
                f"(parts declare: {', '.join(sorted(part_ids)) or 'none'})"
            )
        if not isinstance(override, dict):
            problems.append(f"{where}: must be an object")
            continue
        problems.extend(_requirement_set_problems(where, override))
    return problems
