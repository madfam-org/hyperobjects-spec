"""`body-count` — rendered connected bodies against the count the manifest declares.

Every solid-commons manifest declares how many separate bodies each render should be:

    "verification": {
      "stages": { "geometry": { "checks": {
        "body_count": { "enabled": true, "expected": 1 } } } },     // the base
      "mode_overrides": { "<mode>": {
        "overrides": { "geometry.body_count": { "expected": 2 } },   // all its parts
        "part_overrides": { "<part>": {
          "geometry.body_count": { "expected": 3 } } },             // one part
        "stages": ["geometry", "printability"]                      // stages that run
      } }
    }

The keystone rendered every target and judged it watertight, positive-volume and free of
inverted bodies, and counted the bodies (`RenderCheck.bodies`), but never compared that
count with the declaration. A cartridge declaring one body could render two at defaults,
or 26 at a preset, and stay `ok` with nothing said. This module makes the comparison.

How a declaration is resolved for one render `(mode, part, preset)`:

  * The most specific block wins and REPLACES the others whole (no merging), the same
    rule a parity part override follows: `part_overrides.<part>["geometry.body_count"]`,
    else the mode's `overrides["geometry.body_count"]`, else the base
    `stages.geometry.checks.body_count`. No block at all → nothing declared, nothing
    judged.
  * `enabled: false` → not judged. A mode whose `stages` list leaves out `geometry` →
    not judged (the geometry checks do not run for that mode).
  * `expected` defaults to 1 (the platform verifier's default, yantra4d
    `apps/api/tests/scripts/verify_design.py` `check_body_count`). It is a whole number
    or an expression string over parameter ids, evaluated at the render's parameter
    point: the manifest defaults, with the preset's values over them (a select whose
    option is spelled as a number reads as that number). The expression
    language is small and evaluated by walking a vetted `ast` (numbers, strings,
    booleans, parameter ids, `+ - * / // %`, unary `- + not`, comparisons, `and`/`or`
    and `a if c else b`); nothing is passed to `eval`.
  * `part_quantities` (`modes[].part_quantities.<part>`, the BOM count of that part —
    a number or an expression in the same language) widens what is accepted. A part
    whose script renders ONE copy and a part whose script lays out ALL its copies in one
    mesh are both healthy, so the render may have `expected` bodies or `expected ×
    quantity` bodies. With no quantity, or a quantity of 1, only `expected` is accepted.

A declaration that cannot be evaluated (an unknown parameter, a value that is not a whole
number ≥ 0, syntax outside the language) is reported as a note of its own and not
compared: a count nobody can compute is not evidence either way.

Only renders that PASSED and were not skipped are judged. A failed render already has
its problems, and a skipped one has no mesh.

NOTE ONLY. Every finding is a note and the exit code never changes. The rule becomes a
failure in a separate change, once a whole-commons pass over `main` of every commons that
declares counts shows no unexplained mismatch (CHANGELOG, "body-count").
"""

from __future__ import annotations

import ast
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

__all__ = [
    "RULE_ID",
    "BodyCountDeclaration",
    "BodyCountError",
    "body_count_notes",
    "declared_body_count",
    "evaluate_count",
]

RULE_ID = "body-count"
CHECK_KEY = "geometry.body_count"


class BodyCountError(ValueError):
    """A declared count or quantity that cannot be evaluated at a parameter point."""


@dataclass(frozen=True)
class BodyCountDeclaration:
    """What one render is declared to be: the count, where it came from, the quantity."""

    expected: object
    source: str
    quantity: object | None = None


def _mode(doc: dict, mode_id: str) -> dict:
    for mode in doc.get("modes") or []:
        if isinstance(mode, dict) and mode.get("id") == mode_id:
            return mode
    return {}


def declared_body_count(doc: dict, mode_id: str, part_id: str) -> BodyCountDeclaration | None:
    """The body-count declaration that governs `(mode, part)`, or None when not judged."""
    verification = doc.get("verification")
    if not isinstance(verification, dict):
        return None
    overrides = verification.get("mode_overrides")
    mode_override = overrides.get(mode_id) if isinstance(overrides, dict) else None
    mode_override = mode_override if isinstance(mode_override, dict) else {}

    stages = mode_override.get("stages")
    if isinstance(stages, list) and "geometry" not in stages:
        return None

    block: object = None
    source = ""
    part_overrides = mode_override.get("part_overrides")
    part_block = part_overrides.get(part_id) if isinstance(part_overrides, dict) else None
    if isinstance(part_block, dict) and CHECK_KEY in part_block:
        block = part_block[CHECK_KEY]
        source = f"verification.mode_overrides.{mode_id}.part_overrides.{part_id}[{CHECK_KEY!r}]"
    elif isinstance(mode_block := mode_override.get("overrides"), dict) and CHECK_KEY in mode_block:
        block = mode_block[CHECK_KEY]
        source = f"verification.mode_overrides.{mode_id}.overrides[{CHECK_KEY!r}]"
    else:
        stages_block = verification.get("stages")
        geometry = stages_block.get("geometry") if isinstance(stages_block, dict) else None
        checks = geometry.get("checks") if isinstance(geometry, dict) else None
        if isinstance(checks, dict) and "body_count" in checks:
            block = checks["body_count"]
            source = "verification.stages.geometry.checks.body_count"

    if isinstance(block, bool) or block is None:
        return None
    if isinstance(block, int | float | str):
        # The shorthand `"geometry.body_count": 2` (a bare count, no object).
        block = {"expected": block}
    if not isinstance(block, dict) or block.get("enabled", True) is False:
        return None

    quantities = _mode(doc, mode_id).get("part_quantities")
    quantity = quantities.get(part_id) if isinstance(quantities, dict) else None
    return BodyCountDeclaration(expected=block.get("expected", 1), source=source, quantity=quantity)


_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
}
_COMPARE = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


def _numeric(value: object) -> object:
    """A select whose options are spelled as numbers ("3") counts as that number.

    Without this `finger_count * 2` on a select valued "3" is Python's "33". A string that
    does not spell a number stays a string, so `joint_type == "locking"` still compares.
    """
    if isinstance(value, str):
        text = value.strip()
        for cast in (int, float):
            try:
                return cast(text)
            except ValueError:
                continue
    return value


def _walk(node: ast.AST, params: Mapping[str, object]) -> object:
    if isinstance(node, ast.Expression):
        return _walk(node.body, params)
    if isinstance(node, ast.Constant) and isinstance(node.value, bool | int | float | str):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in params:
            raise BodyCountError(f"'{node.id}' is not a parameter with a value here")
        return _numeric(params[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _walk(node.left, params), _walk(node.right, params)
        try:
            return _BINOPS[type(node.op)](left, right)
        except (TypeError, ZeroDivisionError) as exc:
            raise BodyCountError(f"{type(exc).__name__}: {exc}") from None
    if isinstance(node, ast.UnaryOp):
        operand = _walk(node.operand, params)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub | ast.UAdd) and isinstance(operand, bool | int | float):
            return -operand if isinstance(node.op, ast.USub) else +operand
    if isinstance(node, ast.Compare) and all(type(op) in _COMPARE for op in node.ops):
        left = _walk(node.left, params)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _walk(comparator, params)
            try:
                if not _COMPARE[type(op)](left, right):
                    return False
            except TypeError as exc:
                raise BodyCountError(f"TypeError: {exc}") from None
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        values = node.values
        if isinstance(node.op, ast.And):
            result: object = True
            for value in values:
                result = _walk(value, params)
                if not result:
                    return result
            return result
        result = False
        for value in values:
            result = _walk(value, params)
            if result:
                return result
        return result
    if isinstance(node, ast.IfExp):
        return _walk(node.body if _walk(node.test, params) else node.orelse, params)
    raise BodyCountError(f"`{ast.unparse(node)}` is outside the count expression language")


def evaluate_count(value: object, params: Mapping[str, object]) -> int:
    """A declared count or quantity as a whole number ≥ 0 at this parameter point."""
    if isinstance(value, str):
        try:
            tree = ast.parse(value.strip(), mode="eval")
        except SyntaxError as exc:
            raise BodyCountError(f"syntax error ({exc.msg})") from None
        value = _walk(tree, params)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise BodyCountError(f"evaluates to {value!r}, not a number")
    if not math.isfinite(value) or abs(value - round(value)) > 1e-9 or round(value) < 0:
        raise BodyCountError(f"evaluates to {value!r}, not a whole number >= 0")
    return int(round(value))


def _preset_values(doc: dict) -> dict[tuple[str, str, str], dict]:
    from .rules import preset_targets

    return {(pid, mid, part): values for pid, mid, part, values in preset_targets(doc)}


def body_count_notes(doc: dict, renders: Iterable) -> list[str]:
    """body-count (NOTE ONLY): one note per passed render whose bodies differ from the
    declaration, and one per declaration that cannot be evaluated at its point."""
    from .rules import parameter_defaults

    renders = list(renders)
    if not renders:
        return []
    defaults = parameter_defaults(doc)
    presets: dict[tuple[str, str, str], dict] | None = None
    notes: list[str] = []
    for check in renders:
        if not check.ok or check.skipped or check.bodies is None:
            continue
        declaration = declared_body_count(doc, check.mode, check.part)
        if declaration is None:
            continue
        params = dict(defaults)
        if check.preset is not None:
            if presets is None:
                presets = _preset_values(doc)
            params.update(presets.get((check.preset, check.mode, check.part), {}))
        try:
            expected = evaluate_count(declaration.expected, params)
        except BodyCountError as exc:
            notes.append(
                f"{RULE_ID}: {check.target}: declared count {declaration.expected!r} "
                f"({declaration.source}) cannot be evaluated here — {exc}; not compared "
                f"(rendered {check.bodies})"
            )
            continue
        accepted = [expected]
        quantity_text = ""
        if declaration.quantity is not None:
            try:
                quantity = evaluate_count(declaration.quantity, params)
            except BodyCountError as exc:
                notes.append(
                    f"{RULE_ID}: {check.target}: part_quantities {declaration.quantity!r} "
                    f"cannot be evaluated here — {exc}; compared with the declared count "
                    f"alone"
                )
            else:
                if quantity != 1:
                    accepted.append(expected * quantity)
                    quantity_text = (
                        f" or {expected * quantity} (× part_quantities {quantity}, all "
                        f"copies in one mesh)"
                    )
        if check.bodies in accepted:
            continue
        notes.append(
            f"{RULE_ID}: {check.target}: renders {check.bodies} body/bodies, declares "
            f"{expected}{quantity_text} ({declaration.source}) — either the declaration "
            f"or the geometry is wrong; a note until the whole-commons pass, then a failure"
        )
    return notes
