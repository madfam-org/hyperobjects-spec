"""constraint-dialect (NOTE ONLY): `constraints[]` read by the Studio's safeFormula grammar.

The Studio evaluates constraints with a hand-rolled parser (yantra4d
apps/studio/src/lib/safeFormula.ts) and useConstraints swallows anything it throws, so a
rule outside the dialect never fires. solid-hyperobjects x-carriage shipped
`abs(belt_a_level - belt_b_level) >= 9` at severity error.
"""

import pytest

from y4d_spec.conformance import check_manifest
from y4d_spec.constraint_dialect import (
    MAX_FORMULA_LENGTH,
    MAX_TOKENS,
    RULE_ID,
    constraint_dialect_notes,
    expression_problems,
)

PARAMS = {"a": 1, "b": 2.5, "flag": True, "count": "3", "style": "round", "label": "x"}


@pytest.mark.parametrize(
    "expression",
    [
        "a + b <= 10",
        "a - b >= 9 || b - a >= 9",
        "!(a > b) && flag",
        "a % 2 == 0 ? b > 1 : b < 1",
        "a === 1 && b !== 2",
        "-a < +b",
        ".5 * a >= 0.25",
        "count * 2 > a",  # a numeric string default parses as a number
        "$x_1 > 0".replace("$x_1", "a"),
    ],
)
def test_dialect_expressions_have_no_problems(expression):
    assert expression_problems(expression, PARAMS) == []


@pytest.mark.parametrize(
    ("expression", "phrase"),
    [
        ("abs(a - b) >= 9", "calls a function, `abs(…)`"),
        # The tokenizer runs first, exactly as in safeFormula.ts: the comma throws before
        # the parser ever sees the call.
        ("min(a, b) > 1", "unsupported token: ','"),
        ("sqrt(a) > 1", "calls a function, `sqrt(…)`"),
        ("style == 'round'", "string literal"),
        ('style == "round"', "string literal"),
        ("a > 1 and b > 1", "unexpected trailing token 'and'"),
        ("a > 1 or b > 1", "unexpected trailing token 'or'"),
        ("(a + b > 1", "unclosed `(`"),
        ("a ? b", "`?` with no matching `:`"),
        ("a + ", "expects a value but finds 'end of expression'"),
        ("a = 1", "unsupported token: '='"),
        ("a ^ 2 > 1", "unsupported token: '^'"),
        ("1e3 > a", "unexpected trailing token 'e3'"),
    ],
)
def test_out_of_dialect_expressions_are_named(expression, phrase):
    problems = expression_problems(expression, PARAMS)
    assert len(problems) == 1 and phrase in problems[0], problems


def test_caps_are_256_characters_and_128_tokens():
    assert MAX_FORMULA_LENGTH == 256 and MAX_TOKENS == 128
    long = "a + " * 64 + "a"  # 257 characters
    assert len(long) == 257
    assert "257 characters" in expression_problems(long)[0]
    assert expression_problems("a+" * 63 + "a") == []  # 127 tokens, 127 characters
    many = "a+" * 64 + "a"  # 129 tokens, 129 characters
    assert "129 tokens" in expression_problems(many)[0]


def test_identifiers_must_be_declared_numeric_parameters():
    assert expression_problems("ghost > 1", PARAMS) == [
        "reads 'ghost', which is not a declared parameter"
    ]
    assert "is not a number" in expression_problems("style > 1", PARAMS)[0]
    assert "is not a number" in expression_problems("label > 1", PARAMS)[0]
    # Without a parameter table only the grammar is judged.
    assert expression_problems("ghost > 1") == []


def test_x_carriage_constraint_triggers_and_its_rewrite_does_not():
    doc = {
        "parameters": [
            {"id": "belt_a_level", "type": "slider", "default": 0},
            {"id": "belt_b_level", "type": "slider", "default": 9},
        ],
        "constraints": [
            {"expression": "abs(belt_a_level - belt_b_level) >= 9", "severity": "error",
             "message": {"en": "…"}},
        ],
    }
    notes = constraint_dialect_notes(doc)
    assert len(notes) == 1
    assert notes[0].startswith(
        f"{RULE_ID}: constraints[0].expression 'abs(belt_a_level - belt_b_level) >= 9' "
        "(severity error) calls a function"
    )
    doc["constraints"][0]["expression"] = (
        "belt_a_level - belt_b_level >= 9 || belt_b_level - belt_a_level >= 9"
    )
    assert constraint_dialect_notes(doc) == []


def test_legacy_rule_key_and_missing_formula():
    doc = {
        "parameters": [{"id": "a", "default": 1}],
        "constraints": [
            {"rule": "a > 1 or a < 0", "severity": "warning", "message": "…"},
            {"condition": "a > 1", "severity": "error", "message": "…"},
            {"rule": "a > 0", "message": "…"},
        ],
    }
    notes = constraint_dialect_notes(doc)
    assert len(notes) == 2
    assert notes[0].startswith(f"{RULE_ID}: constraints[0].rule 'a > 1 or a < 0'")
    assert notes[1] == (
        f"{RULE_ID}: constraints[1] (severity error) has no `expression` or `rule` string "
        "— the Studio skips it, so it never fires"
    )


def test_check_manifest_carries_the_note_and_stays_ok():
    doc = {
        "parameters": [{"id": "a", "type": "slider", "default": 1}],
        "constraints": [{"expression": "abs(a) > 0", "severity": "error", "message": "…"}],
    }
    result = check_manifest(doc)
    assert any(n.startswith(f"{RULE_ID}:") for n in result.notes)
    assert not any(RULE_ID in p for p in result.problems)
