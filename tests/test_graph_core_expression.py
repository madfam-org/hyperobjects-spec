"""The core's expression dialect is the solid engine's, formula for formula.

`hyperobject_graph.expression` is a port of the vendored engine's private parser so the soft
and sheet kernels can share the dialect without vendoring a CadQuery transpiler. A port is
a second copy, and a second copy drifts unless something holds it, so this module holds it
two ways: every formula (accepted or refused) parses to the SAME tree or the same refusal on
both sides, and the core's evaluator agrees with executing the engine's emitted Python on
every accepted one.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest

from hyperobject_graph import GraphCoreError, evaluate, expression_names, parse_expression
from y4d_spec.graph import graph_engine as ge

FIXTURES = Path(__file__).parent / "fixtures"

HANDWRITTEN = [
    "1", "1.5", ".5", "5.", "a", "a + b * c", "(a + b) * c", "a - -b", "!a", "!!a", "+a",
    "a / b", "a % b", "a < b ? a : b", "a < b ? a : b < c ? b : c", "a && b || c",
    "a == b", "a === b", "a != b", "a !== b", "a <= b && b >= c", "a > 0 ? 1 : 0",
    "w / 2 - wall", "(a)", "((a + 1) * (b - 1)) / 2", "a ? b ? 1 : 2 : 3", "$x + _y",
    # refusals, which must be refused on both sides
    "", "   ", "a +", "a ? b", "(a", "a)", "min(a, b)", "'x'", "a = b", "a & b", "a | b",
    "1e3", "a ^ b", "a ** b", "a b", "?", ":", "a ? : b", "#",
    "x" * 257, " + ".join(["a"] * 70),
]


def _commons_formulas() -> list[str]:
    """Every expression in the fifteen solid-commons graphs."""
    out: list[str] = []

    def walk(value):
        if isinstance(value, dict):
            if set(value) == {"expr"} and isinstance(value["expr"], str):
                out.append(value["expr"])
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    roots = (FIXTURES / "graph-core" / "solid-commons", FIXTURES / "assembly-golden" / "commons")
    for root in roots:
        for graph in root.glob("*/*.graph.json"):
            walk(json.loads(graph.read_text()))
    return out


def _random_formulas(n: int, seed: int = 20261120) -> list[str]:
    rng = random.Random(seed)
    atoms = ["a", "b", "c", "0", "1", "2.5", ".25", "10", "flag"]
    binops = ["+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "===", "!==", "&&", "||"]

    def gen(depth: int) -> str:
        roll = rng.random()
        if depth <= 0 or roll < 0.3:
            return rng.choice(atoms)
        if roll < 0.45:
            return rng.choice(["!", "-", "+"]) + gen(depth - 1)
        if roll < 0.6:
            return f"({gen(depth - 1)})"
        if roll < 0.7:
            return f"{gen(depth - 1)} ? {gen(depth - 1)} : {gen(depth - 1)}"
        return f"{gen(depth - 1)} {rng.choice(binops)} {gen(depth - 1)}"

    formulas = [gen(rng.randint(1, 5)) for _ in range(n)]
    # Corrupt a share of them so refusals are compared too.
    for i in range(0, n, 7):
        f = formulas[i]
        cut = rng.randint(0, max(0, len(f) - 1))
        formulas[i] = f[:cut] + rng.choice(["(", ")", "?", ":", "&", "'", ",", " "]) + f[cut:]
    return formulas


def _engine_tree(source: str):
    return ge._ExprParser(source, "e").parse()


CORPUS = HANDWRITTEN + _commons_formulas() + _random_formulas(2500)


def test_the_corpus_is_not_trivial():
    commons = _commons_formulas()
    assert len(commons) >= 100, "the commons graphs should contribute their real formulas"
    assert len(CORPUS) > 2600


def test_core_and_engine_parse_every_formula_identically():
    disagreements = []
    for source in CORPUS:
        try:
            engine = ("ok", _engine_tree(source))
        except ge.GraphError:
            engine = ("refused", None)
        try:
            core = ("ok", parse_expression(source, "e"))
        except GraphCoreError:
            core = ("refused", None)
        if engine != core:
            disagreements.append((source, engine, core))
    assert not disagreements, disagreements[:5]


def _engine_value(tree, env: dict):
    """Run the engine's emitted Python for a tree with its own helpers."""
    scope = {name: f"_v_{name}" for name in ge._expr_names(tree)}
    code = ge._EXPR_HELPERS + "\n" + "\n".join(
        f"{var} = {env[name]!r}" for name, var in scope.items()
    ) + f"\n_out = {ge._emit_expr_tree(tree, scope)}\n"
    namespace: dict = {}
    exec(compile(code, "<engine>", "exec"), namespace)  # noqa: S102 - engine's own emission
    return namespace["_out"]


def _same(left, right) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, float) and math.isnan(left):
        return math.isnan(right)
    return left == right


@pytest.mark.parametrize("env", [
    {"a": 3.0, "b": 2.0, "c": 0.0, "flag": True},
    {"a": -1.5, "b": 0.25, "c": 7.0, "flag": False},
    {"a": 0.0, "b": 0.0, "c": 1.0, "flag": True},
])
def test_core_evaluator_agrees_with_the_engines_emitted_code(env):
    compared = 0
    for source in CORPUS:
        try:
            tree = parse_expression(source, "e")
        except GraphCoreError:
            continue
        if not expression_names(tree) <= set(env):
            continue
        try:
            expected = ("ok", _engine_value(tree, env))
        except ZeroDivisionError:
            expected = ("error", None)
        try:
            got = ("ok", evaluate(tree, env))
        except GraphCoreError:
            got = ("error", None)
        assert expected[0] == got[0], source
        if expected[0] == "ok":
            assert _same(expected[1], got[1]), (source, expected[1], got[1])
        compared += 1
    assert compared > 1000


def test_limits_are_the_dialects():
    from hyperobject_graph import MAX_EXPR_LENGTH, MAX_EXPR_TOKENS

    assert (MAX_EXPR_LENGTH, MAX_EXPR_TOKENS) == (ge.MAX_EXPR_LENGTH, ge.MAX_EXPR_TOKENS)


def test_strict_equality_and_truthiness_are_javascripts():
    env = {"t": True, "one": 1.0, "zero": 0.0}
    assert evaluate(parse_expression("t == one"), env) is False
    assert evaluate(parse_expression("t + one"), env) == 2.0
    assert evaluate(parse_expression("zero || one"), env) is True
    assert evaluate(parse_expression("-7 % 3"), env) == -1.0
    with pytest.raises(GraphCoreError):
        evaluate(parse_expression("one / zero"), env)
    with pytest.raises(GraphCoreError):
        evaluate(parse_expression("nope"), env)
