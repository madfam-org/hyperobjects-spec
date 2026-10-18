"""`constraint-dialect` — every `constraints[]` expression read by the Studio's grammar.

A manifest's `constraints[]` are evaluated client-side by the Studio's hand-rolled
parser (yantra4d `apps/studio/src/lib/safeFormula.ts`, reached through
`apps/studio/src/hooks/editor/useConstraints.ts`). `useConstraints` wraps every
evaluation in `try { … } catch {}`, so an expression the parser rejects does not
error: it is swallowed and the constraint silently never fires. An untestable rule is
indistinguishable from a satisfied one (AGENTS.md, "The `constraints[]` dialect").

This module is a STATIC port of that parser. It tokenises and parses each expression
exactly as `safeFormula.ts` does (yantra4d 827ad49f, 2026-05-13) and reports what would
throw before any value is read:

  * the source is longer than 256 characters        (safeFormula.ts MAX_FORMULA_LENGTH)
  * a character no token starts with — a quote, `[`, `,`, `^`, `=` alone …
                                                     (tokenize: "Unsupported token")
  * more than 128 tokens                             (safeFormula.ts MAX_TOKENS)
  * a function call: an identifier followed by `(`. There are no calls in the dialect,
    so `abs(x)` throws at `abs` ("Missing numeric parameter") — no `min`, `max`, `abs`,
    `sqrt`, `floor`, `ceil`
  * a syntax error: a missing `)` or `:`, a trailing token, an operator with no operand
  * an identifier that is not a declared parameter   (parsePrimary: "Missing numeric
    parameter") — `target_part` included, which the Studio never puts in `params`
  * an identifier naming a parameter whose default is not numeric (a select whose
    options are words, a text field): parsePrimary only accepts a number, a boolean or a
    string that parses as a finite number, so the rule throws at the default
  * a constraint with neither `expression` nor `rule` — useConstraints skips it.

Division by zero is NOT judged: it depends on the values a user picks, and a rule that
divides by a parameter whose default is non-zero is legitimate.

NOTE ONLY. Every finding is a note; nothing here changes the exit code. A new rule lands
as a note until a whole-commons false-positive analysis is written down (CHANGELOG,
"constraint-dialect"), and only then may it become a failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "MAX_FORMULA_LENGTH",
    "MAX_TOKENS",
    "RULE_ID",
    "constraint_dialect_notes",
    "expression_problems",
]

RULE_ID = "constraint-dialect"

#: safeFormula.ts `MAX_FORMULA_LENGTH` / `MAX_TOKENS`.
MAX_FORMULA_LENGTH = 256
MAX_TOKENS = 128

#: safeFormula.ts `OPERATORS`, in its order: the tokenizer takes the FIRST operator the
#: source starts with, so `===` must be tried before `==` and `<=` before `<`.
OPERATORS = (
    "===", "!==", "<=", ">=", "&&", "||", "==", "!=", "+", "-", "*", "/", "%", "<", ">", "!",
)

_COMPARISON = ("<", "<=", ">", ">=", "==", "!=", "===", "!==")

# JS `Number(string)` for the strings a manifest default can hold: a decimal literal with
# an optional exponent, or a 0x/0o/0b integer, surrounded by optional whitespace. Python's
# float() is NOT the same test — it accepts "1_000", "nan" and "infinity", which Number()
# turns into NaN or a non-finite value, and both throw in parsePrimary.
_JS_DECIMAL = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_JS_RADIX = re.compile(r"^(?:0[xX][0-9a-fA-F]+|0[oO][0-7]+|0[bB][01]+)$")


@dataclass(frozen=True)
class _Token:
    type: str  # number | identifier | operator | leftParen | rightParen | question | colon | eof
    value: str


class _DialectError(ValueError):
    """What safeFormula.ts would throw, in its own words where it has them."""


def _is_identifier_start(char: str) -> bool:
    return bool(char) and (char.isascii() and (char.isalpha() or char in "_$"))


def _is_identifier_part(char: str) -> bool:
    return bool(char) and (char.isascii() and (char.isalnum() or char in "_$"))


def _is_digit(char: str) -> bool:
    return bool(char) and char in "0123456789"


def _tokenize(source: str) -> list[_Token]:
    """safeFormula.ts `tokenize`, line for line."""
    if len(source) > MAX_FORMULA_LENGTH:
        raise _DialectError(
            f"is {len(source)} characters, over the {MAX_FORMULA_LENGTH}-character cap"
        )
    tokens: list[_Token] = []
    index = 0
    n = len(source)
    while index < n:
        char = source[index]
        if char.isspace():
            index += 1
            continue
        nxt = source[index + 1] if index + 1 < n else ""
        if _is_digit(char) or (char == "." and _is_digit(nxt)):
            start = index
            index += 1
            while index < n and _is_digit(source[index]):
                index += 1
            if index < n and source[index] == ".":
                index += 1
                while index < n and _is_digit(source[index]):
                    index += 1
            tokens.append(_Token("number", source[start:index]))
            continue
        if _is_identifier_start(char):
            start = index
            index += 1
            while index < n and _is_identifier_part(source[index]):
                index += 1
            tokens.append(_Token("identifier", source[start:index]))
            continue
        single = {"(": "leftParen", ")": "rightParen", "?": "question", ":": "colon"}
        if char in single:
            tokens.append(_Token(single[char], char))
            index += 1
            continue
        operator = next((op for op in OPERATORS if source.startswith(op, index)), None)
        if operator is None:
            what = "a string literal" if char in "\"'`" else f"'{char}'"
            raise _DialectError(f"has an unsupported token: {what} at column {index + 1}")
        tokens.append(_Token("operator", operator))
        index += len(operator)
    if len(tokens) > MAX_TOKENS:
        raise _DialectError(f"has {len(tokens)} tokens, over the {MAX_TOKENS}-token cap")
    tokens.append(_Token("eof", ""))
    return tokens


class _Parser:
    """safeFormula.ts `SafeFormulaParser`, without the arithmetic: it walks the same
    grammar and collects the identifiers a value would be read for."""

    def __init__(self, tokens: list[_Token]):
        self.tokens = tokens
        self.cursor = 0
        self.identifiers: list[str] = []

    def parse(self) -> None:
        self._conditional()
        if self._current().type != "eof":
            raise _DialectError(f"has an unexpected trailing token '{self._current().value}'")

    def _current(self) -> _Token:
        return self.tokens[self.cursor]

    def _match(self, *values: str) -> bool:
        token = self._current()
        if token.type != "operator" or token.value not in values:
            return False
        self.cursor += 1
        return True

    def _conditional(self) -> None:
        self._or()
        if self._current().type != "question":
            return
        self.cursor += 1
        self._conditional()
        if self._current().type != "colon":
            raise _DialectError("has a `?` with no matching `:`")
        self.cursor += 1
        self._conditional()

    def _or(self) -> None:
        self._and()
        while self._match("||"):
            self._and()

    def _and(self) -> None:
        self._comparison()
        while self._match("&&"):
            self._comparison()

    def _comparison(self) -> None:
        self._additive()
        while self._current().type == "operator" and self._current().value in _COMPARISON:
            self.cursor += 1
            self._additive()

    def _additive(self) -> None:
        self._multiplicative()
        while self._current().type == "operator" and self._current().value in ("+", "-"):
            self.cursor += 1
            self._multiplicative()

    def _multiplicative(self) -> None:
        self._unary()
        while self._current().type == "operator" and self._current().value in ("*", "/", "%"):
            self.cursor += 1
            self._unary()

    def _unary(self) -> None:
        if self._match("!") or self._match("-") or self._match("+"):
            self._unary()
            return
        self._primary()

    def _primary(self) -> None:
        token = self._current()
        if token.type == "number":
            self.cursor += 1
            return
        if token.type == "identifier":
            following = self.tokens[self.cursor + 1]
            if following.type == "leftParen":
                raise _DialectError(
                    f"calls a function, `{token.value}(…)` — the dialect has no function "
                    f"calls, so this throws at '{token.value}'"
                )
            self.identifiers.append(token.value)
            self.cursor += 1
            return
        if token.type == "leftParen":
            self.cursor += 1
            self._conditional()
            if self._current().type != "rightParen":
                raise _DialectError("has an unclosed `(`")
            self.cursor += 1
            return
        shown = token.value or "end of expression"
        raise _DialectError(f"expects a value but finds '{shown}'")


def _js_number_ok(value: object) -> bool:
    """Would parsePrimary accept this parameter value? (number, boolean, numeric string)"""
    if isinstance(value, bool | int | float):
        return True
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        return bool(_JS_DECIMAL.match(text) or _JS_RADIX.match(text))
    return False


def expression_problems(expression: str, parameters: dict[str, object] | None = None) -> list[str]:
    """What safeFormula.ts would throw on this expression, as short phrases.

    `parameters` maps each declared parameter id to its default. When given, an
    identifier that is not a key, or whose default parsePrimary would refuse, is a
    problem too. Without it only the grammar is judged.
    """
    try:
        parser = _Parser(_tokenize(expression))
        parser.parse()
    except _DialectError as exc:
        return [str(exc)]
    if parameters is None:
        return []
    problems: list[str] = []
    for ident in dict.fromkeys(parser.identifiers):
        if ident not in parameters:
            problems.append(f"reads '{ident}', which is not a declared parameter")
        elif not _js_number_ok(parameters[ident]):
            problems.append(
                f"reads '{ident}', whose default {parameters[ident]!r} is not a number — "
                f"the dialect has no strings, so the rule throws there"
            )
    return problems


def constraint_dialect_notes(doc: dict) -> list[str]:
    """constraint-dialect (NOTE ONLY): one note per constraint the Studio cannot evaluate."""
    constraints = doc.get("constraints")
    if not isinstance(constraints, list):
        return []
    parameters = {
        p["id"]: p.get("default")
        for p in doc.get("parameters") or []
        if isinstance(p, dict) and isinstance(p.get("id"), str)
    }
    notes: list[str] = []
    for i, constraint in enumerate(constraints):
        if not isinstance(constraint, dict):
            continue
        # useConstraints reads `expression ?? rule` and skips a constraint with neither.
        formula = constraint.get("expression")
        key = "expression"
        if formula is None:
            formula, key = constraint.get("rule"), "rule"
        severity = constraint.get("severity", "unset")
        if not isinstance(formula, str) or not formula:
            notes.append(
                f"{RULE_ID}: constraints[{i}] (severity {severity}) has no `expression` or "
                f"`rule` string — the Studio skips it, so it never fires"
            )
            continue
        for problem in expression_problems(formula, parameters):
            notes.append(
                f"{RULE_ID}: constraints[{i}].{key} {formula!r} (severity {severity}) "
                f"{problem}; the Studio's safeFormula parser throws, useConstraints "
                f"swallows it, and the constraint never fires"
            )
    return notes
