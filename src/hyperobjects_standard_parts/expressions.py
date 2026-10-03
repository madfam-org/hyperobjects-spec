"""Evaluate a catalog entry's frame expressions at a parameter point — a minimal local walker.

The SEM-1 §2.3 grammar a frame component is written in: numeric literals, parameter ids,
binary ``+ - * /``, unary ``+``/``-``, parentheses, and calls to ``min``, ``max`` and
``abs``. The expression is parsed with :mod:`ast` in ``eval`` mode and walked node by node
over plain floats; nothing is handed to ``eval``, ``exec`` or ``compile``, and no attribute,
subscript, comprehension or other name is reachable, because the walker has no branch for
them.

Why a local walker
------------------
ASM-1 §1 puts THE frame evaluator in ``y4d_spec/frame_eval.py`` (lane P4-FRAMES, PR #34).
This branch is cut from PR #32, which does not have that module, so the catalog checks its
expressions with this deliberately small walker instead of copying the other lane's code.
It accepts exactly the grammar above and nothing more; once #34 lands, the catalog check
can call ``y4d_spec.frame_eval.evaluate_expression`` and this module can go. The catalog's
own data is written so either evaluator gives the same floats: every expression is a sum,
difference, product or quotient of parameters and literals.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping

__all__ = ["ExpressionError", "evaluate_component", "expression_names"]

_FUNCTIONS = {"min": min, "max": max, "abs": abs}
_MAX_LENGTH = 256


class ExpressionError(ValueError):
    """A frame component could not be parsed or evaluated. The message says why."""


def _parse(expr: str) -> ast.Expression:
    if len(expr) > _MAX_LENGTH:
        raise ExpressionError(f"{expr!r} is longer than {_MAX_LENGTH} characters")
    try:
        return ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"{expr!r} does not parse: {exc.msg}") from None


def _walk(node: ast.AST, values: Mapping[str, float], expr: str) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise ExpressionError(f"{expr!r}: {node.value!r} is not a numeric literal")
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise ExpressionError(f"{expr!r}: unknown identifier {node.id!r}")
        return float(values[node.id])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        inner = _walk(node.operand, values, expr)
        return -inner if isinstance(node.op, ast.USub) else inner
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub | ast.Mult | ast.Div):
        left = _walk(node.left, values, expr)
        right = _walk(node.right, values, expr)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise ExpressionError(f"{expr!r}: division by zero")
        return left / right
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCTIONS
        and not node.keywords
        and node.args
    ):
        args = [_walk(a, values, expr) for a in node.args]
        if node.func.id == "abs" and len(args) != 1:
            raise ExpressionError(f"{expr!r}: abs() takes exactly one argument")
        return float(_FUNCTIONS[node.func.id](*args))
    raise ExpressionError(
        f"{expr!r}: {type(node).__name__} is outside the frame grammar "
        f"(literals, parameter ids, + - * /, parentheses, min, max, abs)"
    )


def evaluate_component(component: object, values: Mapping[str, float]) -> float:
    """One frame component — a number or an expression string — as a finite float."""
    if isinstance(component, bool):
        raise ExpressionError(f"{component!r} is a boolean, not a frame component")
    if isinstance(component, int | float):
        result = float(component)
    elif isinstance(component, str):
        tree = _parse(component.strip())
        result = _walk(tree.body, values, component)
    else:
        raise ExpressionError(f"{component!r} is neither a number nor an expression string")
    if not math.isfinite(result):
        raise ExpressionError(f"{component!r} evaluates to a non-finite value")
    return result


def expression_names(component: object) -> set[str]:
    """The identifiers an expression reads (empty for a number or an unparseable string)."""
    if not isinstance(component, str):
        return set()
    try:
        tree = _parse(component.strip())
    except ExpressionError:
        return set()
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in _FUNCTIONS}
