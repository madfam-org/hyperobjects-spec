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

The frame expression grammar is ASM-1 §1 v1.1 (FRAME_GRAMMAR_VERSION): numeric
literals, parameter ids, `let` names, `+ - * /`, parentheses, unary minus, the
comparisons `< <= > >= == !=` (1 or 0; never chained), and calls to FRAME_FUNCS —
`min`, `max`, `abs` (v1.0, SEM-1 §2.3); `sin`, `cos`, `tan`, `asin`, `acos`, `atan`,
`atan2(y, x)` in DEGREES (the OpenSCAD convention); `sqrt`, `floor`, `ceil`, `round`;
and `iif(cond, a, b)`. It stays purely numeric: no string literal ever enters an
expression; a select's string option reaches a frame only through a `let` lookup
(`{param, map}` with numbers on the right). Like the params_map check, it is PARSED
with Python's `ast` and walked node by node; nothing is ever evaluated here.

`let` (ASM-1 v1.1, on a cdg_interface): named derived numbers a frame may read. Each
entry is an expression (the same grammar, which may read parameters and other `let`
names of the same block) or a `{param, map}` lookup over a select's option values with
numbers on the right. ORDER RULE: evaluation follows dependencies, not the order the
keys are written — a JSON object is unordered (RFC 8259), and a store such as Postgres
`jsonb` re-sorts keys, so declaration order is not a fact that survives a round trip.
A dependency cycle (including an entry that reads itself) is an error naming the cycle;
an unknown name is an error; a `let` name may not shadow a parameter or a function.
"""

from __future__ import annotations

import ast
import math
import re

__all__ = [
    "COMPARISON_OPS",
    "FRAME_FUNCS",
    "FRAME_EXPRESSION_MAX_LENGTH",
    "FRAME_GRAMMAR_MIN_KEYSTONE",
    "FRAME_GRAMMAR_V1_0_FUNCS",
    "FRAME_GRAMMAR_VERSION",
    "LET_NAME_PATTERN",
    "LetCycleError",
    "expression_names",
    "frame_grammar_features",
    "let_evaluation_order",
    "let_problems",
    "ORTHOGONALITY_TOLERANCE_DEG",
    "POLARITIES",
    "SYMMETRY_ORDERS",
    "frame_expression_problems",
    "canonical_number_key",
    "interface_frame_rules",
    "requirements_rules",
]

#: The frame grammar this keystone implements (ASM-1 §1). 1.0.0 was SEM-1 §2.3
#: (literals, ids, + - * /, min/max/abs); 1.1.0 adds `let`, degree trig, sqrt and the
#: rounding functions, comparisons, `iif` and slider size-key maps — all additive.
FRAME_GRAMMAR_VERSION = "1.1.0"
#: The first hyperobjects-spec release that implements FRAME_GRAMMAR_VERSION. A manifest
#: that uses any v1.1 feature needs a keystone at least this new; an older pin does not
#: know the feature and reports it as an unknown name, call, character or select-only
#: size_key (docs/ASSEMBLIES.md, "Forward compatibility").
FRAME_GRAMMAR_MIN_KEYSTONE = "0.4.0"
#: The calls of grammar v1.0 (SEM-1 §2.3).
FRAME_GRAMMAR_V1_0_FUNCS = frozenset({"min", "max", "abs"})
#: Calls a frame expression may make, with their (min, max) argument counts. Trig is in
#: DEGREES (the OpenSCAD convention): sin(90) = 1, atan2(1, 1) = 45.
FRAME_FUNCS: dict[str, tuple[int, int | None]] = {
    "min": (2, None),
    "max": (2, None),
    "abs": (1, 1),
    "sin": (1, 1),
    "cos": (1, 1),
    "tan": (1, 1),
    "asin": (1, 1),
    "acos": (1, 1),
    "atan": (1, 1),
    "atan2": (2, 2),
    "sqrt": (1, 1),
    "floor": (1, 1),
    "ceil": (1, 1),
    "round": (1, 1),
    "iif": (3, 3),
}
#: Comparison operators (each yields 1 or 0). A chain such as `a < b < c` is refused:
#: Python reads it as `a < b and b < c`, OpenSCAD as `(a < b) < c`.
COMPARISON_OPS = {
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=",
}
#: The constraint dialect's source cap, applied to frame expressions too — per
#: expression, and per `let` entry.
FRAME_EXPRESSION_MAX_LENGTH = 256
#: A `let` name: the parameter-id pattern.
LET_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
#: How far from orthogonal a numeric x_axis may sit against a numeric normal. The same
#: angle SEM-1 §2.3 uses for antiparallel normals in the mating rule.
ORTHOGONALITY_TOLERANCE_DEG = 0.5
POLARITIES = ("male", "female", "neutral")
SYMMETRY_ORDERS = (0, 1, 2, 3, 4, 6, 8)

_FRAME_VECTORS = ("origin", "normal", "x_axis")
_EXPR_CHARS = re.compile(r"^[A-Za-z0-9_.+\-*/(),<>=!\s]+$")
_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_UNARYOPS = (ast.USub, ast.UAdd)


def _ids(entries: object) -> set[str]:
    if not isinstance(entries, list):
        return set()
    return {e["id"] for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ── frame expressions ─────────────────────────────────────────────────────────
_GRAMMAR_TAG = (
    f"frame grammar v{FRAME_GRAMMAR_VERSION}, hyperobjects-spec >= {FRAME_GRAMMAR_MIN_KEYSTONE}"
)


def frame_expression_problems(expr: str, param_ids: set[str]) -> list[str]:
    """Why `expr` is not a valid frame component expression (empty = valid).

    Parse-only. A name is a reference unless it is the target of a call to one of
    FRAME_FUNCS; every reference must be one of `param_ids` (the declared parameters,
    plus the interface's `let` names where the caller allows them).
    """
    if len(expr) > FRAME_EXPRESSION_MAX_LENGTH:
        return [f"is longer than {FRAME_EXPRESSION_MAX_LENGTH} characters"]
    if not expr.strip():
        return ["is empty"]
    if not _EXPR_CHARS.match(expr):
        return [
            "uses a character outside the grammar (digits, names, + - * / ( ) , and the "
            f"comparisons < <= > >= == !=; {_GRAMMAR_TAG})"
        ]
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
        elif isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                problems.append(
                    "chains comparisons; write each comparison on its own (a < b < c is "
                    "read differently by Python and OpenSCAD)"
                )
            elif type(node.ops[0]) not in COMPARISON_OPS:
                problems.append(f"uses unsupported operator {type(node.ops[0]).__name__}")
            walk(node.left)
            for comparator in node.comparators:
                walk(comparator)
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
                    f"calls '{name or '<expression>'}', not one of {', '.join(FRAME_FUNCS)} "
                    f"({_GRAMMAR_TAG}; a newer keystone may define it)"
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


def expression_names(expr: object) -> set[str]:
    """The names an expression READS (parse only): every `ast.Name` that is not the
    target of a call. A non-string or an unparseable string reads nothing — the grammar
    check says why it does not parse."""
    if not isinstance(expr, str):
        return set()
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return set()
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in called}


def _calls(expr: object) -> set[str]:
    if not isinstance(expr, str):
        return set()
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return set()
    return {
        n.func.id for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }


def _has_comparison(expr: object) -> bool:
    if not isinstance(expr, str):
        return False
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False
    return any(isinstance(n, ast.Compare) for n in ast.walk(tree))


# ── let ───────────────────────────────────────────────────────────────────────
class LetCycleError(ValueError):
    """A `let` block whose dependencies form a cycle. `cycle` lists it, first name last."""

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        super().__init__("let entries form a dependency cycle: " + " → ".join(cycle))


def _let_dependencies(let_block: dict) -> dict[str, list[str]]:
    """{let name: the OTHER let names its expression reads}, in declaration order."""
    names = set(let_block)
    deps: dict[str, list[str]] = {}
    for name, entry in let_block.items():
        read = expression_names(entry) if isinstance(entry, str) else set()
        deps[name] = sorted(read & names)
    return deps


def let_evaluation_order(let_block: dict) -> list[str]:
    """The order to evaluate a `let` block in: every entry after the entries it reads.

    Dependency order, not key order (see the module docstring); ties keep the order
    the keys are written in, so the result is deterministic. Raises LetCycleError.
    """
    deps = _let_dependencies(let_block)
    order: list[str] = []
    state: dict[str, int] = {}  # 1 = on the current path, 2 = done

    def visit(name: str, path: list[str]) -> None:
        if state.get(name) == 2:
            return
        if state.get(name) == 1:
            start = path.index(name)
            raise LetCycleError([*path[start:], name])
        state[name] = 1
        for dep in deps[name]:
            visit(dep, [*path, name])
        state[name] = 2
        order.append(name)

    for name in let_block:
        visit(name, [])
    return order


def _select_option_keys(param: dict) -> list[str]:
    """A select's option values as the strings a map is keyed by (SEM-1 §2.3)."""
    return [str(o["value"]) for o in param.get("options") or []
            if isinstance(o, dict) and "value" in o]


def let_problems(label: str, let_block: object, doc: dict) -> list[str]:
    """Why an interface's `let` block is not well-formed (empty = well-formed).

    Checked here, at manifest-check time, so that a gap fails visibly before any
    evaluation: a name that is not an identifier, shadows a parameter or a function; an
    expression outside the grammar or reading an unknown name; a dependency cycle; a
    `{param, map}` whose `param` is not a declared select, whose right-hand values are
    not finite numbers, or whose `map` does not cover exactly the select's options.
    """
    if not isinstance(let_block, dict):
        return [f"{label} let: must be an object of name → expression or {{param, map}}"]
    params = {p["id"]: p for p in doc.get("parameters") or []
              if isinstance(p, dict) and isinstance(p.get("id"), str)}
    names = set(let_block)
    problems: list[str] = []
    for name, entry in let_block.items():
        where = f"{label} let.{name}"
        if not LET_NAME_PATTERN.match(name):
            problems.append(f"{where}: name must match {LET_NAME_PATTERN.pattern}")
        if name in params:
            problems.append(f"{where}: shadows the parameter '{name}' — pick another name")
        if name in FRAME_FUNCS:
            problems.append(f"{where}: shadows the function '{name}' — pick another name")
        if isinstance(entry, str):
            for problem in frame_expression_problems(entry, set(params) | names):
                problems.append(f"{where}: expression {entry!r} {problem}")
        elif isinstance(entry, dict):
            problems.extend(_let_map_problems(where, entry, params))
        else:
            problems.append(f"{where}: must be an expression string or {{param, map}}")
    try:
        let_evaluation_order(let_block)
    except LetCycleError as exc:
        problems.append(f"{label} let: {exc}")
    return problems


def _let_map_problems(where: str, entry: dict, params: dict) -> list[str]:
    extra = sorted(set(entry) - {"param", "map"})
    problems = [f"{where}: unexpected key '{k}' (a lookup is {{param, map}})" for k in extra]
    param_id, mapping = entry.get("param"), entry.get("map")
    if not isinstance(mapping, dict) or not mapping:
        problems.append(f"{where}.map: required, must be a non-empty object")
        mapping = {}
    for key, value in mapping.items():
        if not _is_number(value) or not math.isfinite(value):
            problems.append(
                f"{where}.map['{key}']: {value!r} is not a finite number — a lookup maps "
                "option values to numbers only, so no string ever enters an expression"
            )
    if not isinstance(param_id, str) or param_id not in params:
        problems.append(f"{where}.param: {param_id!r} is not a declared parameter")
        return problems
    param = params[param_id]
    if param.get("type") != "select":
        problems.append(
            f"{where}.param: '{param_id}' is a {param.get('type')!r} parameter; a lookup "
            "reads a select's option values (use an expression for a number)"
        )
        return problems
    options = _select_option_keys(param)
    for option in options:
        if option not in mapping:
            problems.append(
                f"{where}.map: option '{option}' of '{param_id}' has no entry — at that "
                "option the frame could not evaluate"
            )
    for key in mapping:
        if key not in options:
            problems.append(
                f"{where}.map: key '{key}' is not an option of '{param_id}' "
                f"(options: {', '.join(options) or 'none'})"
            )
    return problems


def _let_names(iface: dict) -> set[str]:
    block = iface.get("let")
    return set(block) if isinstance(block, dict) else set()


# ── grammar features (forward compatibility, ASM-1 v1.1) ─────────────────────
def frame_grammar_features(doc: dict) -> list[str]:
    """The ASM-1 v1.1 frame-grammar features a manifest uses, sorted (empty = v1.0 only).

    `let`, `trig` (sin … atan2), `sqrt/rounding` (sqrt, floor, ceil, round),
    `comparison`, `iif`, `slider size_key` — each needs FRAME_GRAMMAR_MIN_KEYSTONE.
    """
    ho = doc.get("hyperobject") if isinstance(doc.get("hyperobject"), dict) else {}
    interfaces = ho.get("cdg_interfaces")
    params = {p["id"]: p for p in doc.get("parameters") or []
              if isinstance(p, dict) and isinstance(p.get("id"), str)}
    trig = {"sin", "cos", "tan", "asin", "acos", "atan", "atan2"}
    rounding = {"sqrt", "floor", "ceil", "round"}
    found: set[str] = set()
    for iface in interfaces if isinstance(interfaces, list) else []:
        if not isinstance(iface, dict):
            continue
        exprs: list[object] = []
        if "let" in iface:
            found.add("let")
            block = iface["let"]
            if isinstance(block, dict):
                exprs.extend(v for v in block.values() if isinstance(v, str))
        frame = iface.get("frame")
        if isinstance(frame, dict):
            for key in _FRAME_VECTORS:
                vec = frame.get(key)
                if isinstance(vec, list):
                    exprs.extend(c for c in vec if isinstance(c, str))
        for expr in exprs:
            calls = _calls(expr)
            if calls & trig:
                found.add("trig")
            if calls & rounding:
                found.add("sqrt/rounding")
            if "iif" in calls:
                found.add("iif")
            if _has_comparison(expr):
                found.add("comparison")
        size_key = iface.get("size_key")
        if isinstance(size_key, dict):
            param = params.get(size_key.get("param"))
            if isinstance(param, dict) and param.get("type") in _NUMERIC_PARAM_TYPES:
                found.add("slider size_key")
    return sorted(found)


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


def _frame_problems(
    label: str, frame: object, doc: dict, symmetry: object, let_names: set[str] = frozenset()
) -> list[str]:
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

    param_ids = _ids(doc.get("parameters")) | set(let_names)
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
    if param.get("type") in _NUMERIC_PARAM_TYPES:
        return problems + _slider_size_key_problems(label, param_id, param, mapping)
    if param.get("type") != "select":
        problems.append(
            f"{label} size_key.param: '{param_id}' is a {param.get('type')!r} parameter; "
            "only a select or a slider (exact values) chooses among sizes"
        )
        return problems
    values = _select_option_keys(param)
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


#: Parameter types a size_key map may follow by EXACT value (ASM-1 v1.1, D3).
_NUMERIC_PARAM_TYPES = ("slider", "number")


def canonical_number_key(value: object) -> str | None:
    """The GOC-1 canonical spelling of a number (`12.0` → `"12"`, `9.50` → `"9.5"`), or
    None when `value` is not a finite number or a string that spells one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    from hyperobjects_schemas.generator_output import canonical_json

    return canonical_json(float(value)).decode("utf-8")


def _slider_size_key_problems(label: str, param_id: str, param: dict, mapping: dict) -> list[str]:
    """A slider size_key map: exact values → keys, otherwise none (ASM-1 v1.1, D3).

    Each key must spell a number in its GOC-1 canonical form (so two keys can never
    normalise to the same value) and lie inside the slider's range (a key outside it can
    never match). Coverage is NOT required: a value with no entry resolves to no size
    key, and a mate that needs one fails there, by name.
    """
    problems: list[str] = []
    lo, hi = param.get("min"), param.get("max")
    for key in mapping:
        canonical = canonical_number_key(key)
        if canonical is None:
            problems.append(
                f"{label} size_key.map: key '{key}' is not a number, and '{param_id}' is a "
                f"{param.get('type')} — a slider map is keyed by exact values"
            )
            continue
        if canonical != key:
            problems.append(
                f"{label} size_key.map: key '{key}' is not in canonical form; write "
                f"'{canonical}' (GOC-1 number normalisation)"
            )
        number = float(key)
        if (_is_number(lo) and number < lo) or (_is_number(hi) and number > hi):
            problems.append(
                f"{label} size_key.map: key '{key}' is outside '{param_id}' "
                f"[{lo}, {hi}], so it can never match"
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
    options, or a slider/number whose `map` keys are canonical in-range values (no
    coverage: an unmatched value has no size key); `let` — see `let_problems`.
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
        if "let" in iface:
            problems.extend(let_problems(label, iface["let"], doc))
        if "frame" in iface:
            problems.extend(
                _frame_problems(label, iface["frame"], doc, symmetry, _let_names(iface))
            )
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
