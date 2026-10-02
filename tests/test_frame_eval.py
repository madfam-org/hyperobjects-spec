"""The safe frame-expression evaluator (ASM-1 §1): y4d_spec.frame_eval."""

import copy
import json
import math
from pathlib import Path

import pytest

from y4d_spec.frame_eval import (
    ORTHOGONALITY_LIMIT_DEG,
    Frame,
    FrameEvaluationError,
    evaluate_expression,
    evaluate_frame,
    evaluate_vector,
    expression_value,
    find_interface,
    resolve_parameters,
)

FIXTURE = Path(__file__).parent / "fixtures" / "y4d" / "semantic-motor-mount.project.json"


@pytest.fixture
def manifest():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _with_frame(manifest, frame, iface_id="motor_bolt_pattern"):
    doc = copy.deepcopy(manifest)
    find_interface(doc, iface_id)["frame"] = frame
    return doc


# ── expressions ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "expr, expected",
    [
        ("1 + 2 * 3", 7.0),
        ("(1 + 2) * 3", 9.0),
        ("-a", -2.0),
        ("+a", 2.0),
        ("a / 4", 0.5),
        ("a - b", -1.0),
        ("min(a, b, 10)", 2.0),
        ("max(a, b)", 3.0),
        ("abs(a - b)", 1.0),
        ("-max(a, 2 * b) / 2", -3.0),
        ("0.5", 0.5),
        ("1e3", 1000.0),
    ],
)
def test_expression_values(expr, expected):
    assert evaluate_expression(expr, {"a": 2, "b": 3}) == pytest.approx(expected)


def test_numbers_pass_through():
    assert evaluate_expression(4, {}) == 4.0
    assert evaluate_expression(-1.5, {}) == -1.5


@pytest.mark.parametrize("bad", [True, None, [1], {"a": 1}])
def test_non_numeric_component_rejected(bad):
    with pytest.raises(FrameEvaluationError):
        evaluate_expression(bad, {})


@pytest.mark.parametrize(
    "expr, fragment",
    [
        ("c + 1", "unknown parameter 'c'"),
        ("a ** 2", "unsupported operator Pow"),
        ("a % 2", "outside the grammar"),
        ("__import__('os')", "outside the grammar"),
        ("a.real", "unsupported syntax"),
        ("round(a)", "calls 'round'"),
        ("abs(a, b)", "needs 1"),
        ("min(a)", "needs at least 2"),
        ("a < b", "outside the grammar"),
        ("", "is empty"),
        ("a +", "does not parse"),
        ("x" * 300, "longer than 256"),
    ],
)
def test_grammar_violations_are_errors(expr, fragment):
    with pytest.raises(FrameEvaluationError, match="") as info:
        evaluate_expression(expr, {"a": 2, "b": 3})
    assert fragment in str(info.value)


def test_unknown_identifier_even_when_value_given():
    # `declared` narrows what may be read: a given value is not a declaration.
    with pytest.raises(FrameEvaluationError, match="unknown parameter 'z'"):
        evaluate_expression("z", {"z": 1}, declared={"a"})


def test_division_by_zero():
    with pytest.raises(FrameEvaluationError, match="division by zero"):
        evaluate_expression("a / (b - 3)", {"a": 2, "b": 3})


def test_non_finite_literal_and_intermediate():
    with pytest.raises(FrameEvaluationError, match="not finite"):
        evaluate_expression("1e400", {})
    with pytest.raises(FrameEvaluationError, match="not finite"):
        evaluate_expression("a * a * a", {"a": 1e200})
    with pytest.raises(FrameEvaluationError, match="not finite"):
        evaluate_expression(float("nan"), {})


def test_declared_without_value():
    with pytest.raises(FrameEvaluationError, match="has no value"):
        evaluate_expression("a", {}, declared={"a"})


# ── parameter resolution ──────────────────────────────────────────────────────
def test_expression_value_kinds():
    assert expression_value("c", True) == 1.0
    assert expression_value("c", False) == 0.0
    assert expression_value("s", 3) == 3.0
    assert expression_value("sel", "6") == 6.0
    with pytest.raises(FrameEvaluationError, match="not a number"):
        expression_value("sel", "16x16")
    with pytest.raises(FrameEvaluationError, match="not a number"):
        expression_value("t", None)


def test_resolve_full_injection_overrides_defaults(manifest):
    values = resolve_parameters(manifest, {"plate_thick": 6.0, "extra": 1})
    assert values["plate_thick"] == 6.0
    assert values["iso_gap"] == 2.4  # default kept
    assert values["motor_pattern"] == "16x16"  # select: option value
    assert values["extra"] == 1  # carried to the script, never readable in a frame
    assert resolve_parameters(manifest) == resolve_parameters(manifest, {})


def test_checkbox_reads_as_one_or_zero():
    doc = {
        "parameters": [{"id": "flip", "type": "checkbox", "default": True}],
        "hyperobject": {"cdg_interfaces": [{"id": "i", "frame": {
            "part": "p", "origin": [0, 0, "10 * flip"], "normal": [0, 0, 1]}}]},
    }
    assert evaluate_frame(doc, "i").origin == (0.0, 0.0, 10.0)
    assert evaluate_frame(doc, "i", {"flip": False}).origin == (0.0, 0.0, 0.0)


def test_numeric_select_option_reads_as_number():
    doc = {
        "parameters": [{"id": "n", "type": "select", "default": "4",
                        "options": [{"value": "4"}, {"value": "6"}]}],
        "hyperobject": {"cdg_interfaces": [{"id": "i", "frame": {
            "part": "p", "origin": ["n", 0, 0], "normal": [0, 0, 1]}}]},
    }
    assert evaluate_frame(doc, "i", {"n": "6"}).origin == (6.0, 0.0, 0.0)


def test_non_numeric_select_in_expression_is_an_error(manifest):
    doc = _with_frame(manifest, {"part": "soft_mount", "origin": [0, 0, "motor_pattern"],
                                 "normal": [0, 0, 1]})
    with pytest.raises(FrameEvaluationError, match="frame.origin\\[2\\].*'16x16'"):
        evaluate_frame(doc, "motor_bolt_pattern")


# ── frames ────────────────────────────────────────────────────────────────────
def test_fixture_frame_at_defaults(manifest):
    frame = evaluate_frame(manifest, "motor_bolt_pattern")
    assert isinstance(frame, Frame)
    assert frame.part == "soft_mount"
    assert frame.origin == pytest.approx((0.0, 0.0, 6.4))
    assert frame.normal == (0.0, 0.0, 1.0)
    assert frame.x_axis == (1.0, 0.0, 0.0)


def test_fixture_frame_follows_parameters(manifest):
    frame = evaluate_frame(manifest, "motor_bolt_pattern", {"plate_thick": 6, "iso_gap": 1})
    assert frame.origin == pytest.approx((0.0, 0.0, 7.0))
    foot = evaluate_frame(manifest, "landing_foot", {"foot_drop": 5, "plate_thick": 4})
    assert foot.origin == pytest.approx((0.0, 0.0, -8.0))  # -max(5, 2*4)
    assert foot.normal == (0.0, 0.0, -1.0)
    assert foot.x_axis is None


def test_interface_given_as_dict(manifest):
    iface = find_interface(manifest, "landing_foot")
    assert evaluate_frame(manifest, iface).origin == pytest.approx((0, 0, -14.0))


def test_normalises_vectors(manifest):
    doc = _with_frame(manifest, {"part": "soft_mount", "origin": [0, 0, 0],
                                 "normal": [0, 0, "2 * plate_thick"], "x_axis": [3, 0, 0]})
    frame = evaluate_frame(doc, "motor_bolt_pattern")
    assert frame.normal == (0.0, 0.0, 1.0)
    assert frame.x_axis == (1.0, 0.0, 0.0)


def test_orthogonalises_a_slightly_skewed_x_axis(manifest):
    tilt = math.tan(math.radians(0.6))  # inside the 1° limit
    doc = _with_frame(manifest, {"part": "soft_mount", "origin": [0, 0, 0],
                                 "normal": [0, 0, 1], "x_axis": [1, 0, tilt]})
    frame = evaluate_frame(doc, "motor_bolt_pattern")
    assert abs(sum(a * b for a, b in zip(frame.x_axis, frame.normal, strict=True))) < 1e-12
    assert math.hypot(*frame.x_axis) == pytest.approx(1.0)
    assert frame.x_axis[0] == pytest.approx(1.0)


def test_rejects_x_axis_beyond_the_limit(manifest):
    tilt = math.tan(math.radians(ORTHOGONALITY_LIMIT_DEG + 0.5))
    doc = _with_frame(manifest, {"part": "soft_mount", "origin": [0, 0, 0],
                                 "normal": [0, 0, 1], "x_axis": [1, 0, tilt]})
    with pytest.raises(FrameEvaluationError, match="from orthogonal"):
        evaluate_frame(doc, "motor_bolt_pattern")


def test_parameter_driven_x_axis_checked_at_the_point(manifest):
    # Orthogonal at the defaults (arm_angle 0), 45° off at arm_angle 45.
    doc = _with_frame(manifest, {"part": "soft_mount", "origin": [0, 0, 0],
                                 "normal": [0, 0, 1], "x_axis": [1, 0, "arm_angle / 45"]})
    assert evaluate_frame(doc, "motor_bolt_pattern").x_axis == (1.0, 0.0, 0.0)
    with pytest.raises(FrameEvaluationError, match="from orthogonal"):
        evaluate_frame(doc, "motor_bolt_pattern", {"arm_angle": 45})


@pytest.mark.parametrize("key", ["normal", "x_axis"])
def test_zero_vectors_rejected(manifest, key):
    frame = {"part": "soft_mount", "origin": [0, 0, 0], "normal": [0, 0, 1],
             "x_axis": [1, 0, 0]}
    frame[key] = [0, 0, "plate_thick - plate_thick"]
    with pytest.raises(FrameEvaluationError, match=f"frame.{key} evaluates to the zero"):
        evaluate_frame(_with_frame(manifest, frame), "motor_bolt_pattern")


def test_missing_frame_and_parts(manifest):
    doc = copy.deepcopy(manifest)
    del find_interface(doc, "motor_bolt_pattern")["frame"]
    with pytest.raises(FrameEvaluationError, match="declares no frame"):
        evaluate_frame(doc, "motor_bolt_pattern")
    with pytest.raises(FrameEvaluationError, match="no cdg_interface 'nope'"):
        evaluate_frame(manifest, "nope")
    with pytest.raises(FrameEvaluationError, match="frame.normal is required"):
        evaluate_frame(_with_frame(manifest, {"part": "soft_mount", "origin": [0, 0, 0]}),
                       "motor_bolt_pattern")
    with pytest.raises(FrameEvaluationError, match="frame.part"):
        evaluate_frame(_with_frame(manifest, {"origin": [0, 0, 0], "normal": [0, 0, 1]}),
                       "motor_bolt_pattern")


def test_error_names_vector_and_component(manifest):
    doc = _with_frame(manifest, {"part": "soft_mount", "origin": [0, "1 / (iso_gap - 2.4)", 0],
                                 "normal": [0, 0, 1]})
    with pytest.raises(FrameEvaluationError) as info:
        evaluate_frame(doc, "motor_bolt_pattern")
    assert "cdg_interface 'motor_bolt_pattern': frame.origin[1]" in str(info.value)
    assert "division by zero" in str(info.value)


def test_vector_shape():
    with pytest.raises(FrameEvaluationError, match="exactly 3"):
        evaluate_vector([1, 2], {})
    assert evaluate_vector((1, "a", 3), {"a": 2}) == (1.0, 2.0, 3.0)


# ── H(F) ──────────────────────────────────────────────────────────────────────
def test_homogeneous_columns_are_x_y_n_o():
    frame = Frame(part="p", origin=(1.0, 2.0, 3.0), normal=(0.0, 0.0, 1.0),
                  x_axis=(1.0, 0.0, 0.0))
    h = frame.homogeneous()
    assert [row[0] for row in h] == [1.0, 0.0, 0.0, 0.0]  # x
    assert [row[1] for row in h] == [0.0, 1.0, 0.0, 0.0]  # y = n × x
    assert [row[2] for row in h] == [0.0, 0.0, 1.0, 0.0]  # n
    assert [row[3] for row in h] == [1.0, 2.0, 3.0, 1.0]  # o


@pytest.mark.parametrize("normal", [(0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0),
                                    (0.6, 0.0, 0.8)])
def test_reference_x_axis_fallback_is_unit_and_orthogonal(normal):
    frame = Frame(part="p", origin=(0.0, 0.0, 0.0), normal=normal, x_axis=None)
    x = frame.reference_x_axis()
    assert math.hypot(*x) == pytest.approx(1.0)
    assert abs(sum(a * b for a, b in zip(x, normal, strict=True))) < 1e-12
    assert frame.reference_x_axis() == x  # deterministic


def test_no_eval_reachable():
    # The module never calls eval/exec/compile: an expression is data, walked by hand.
    source = (Path(__file__).parents[1] / "src" / "y4d_spec" / "frame_eval.py").read_text()
    for forbidden in ("eval(", "exec(", "compile("):
        assert forbidden not in source.replace("evaluate", "").replace("_eval", "")
