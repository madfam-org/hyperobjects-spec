"""ASM-1 v1.1 frame grammar: `let`, degree trig, rounding, comparisons, `iif`, domain
errors and slider size keys (rulings D1–D3, D7's feature detection).

Every negative case starts from the SEM-1 fixture and breaks exactly one thing, like
test_semantic_rules.py.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from y4d_spec import check_manifest
from y4d_spec.assembly import (
    ResolvedComponent,
    resolve_interfaces,
    resolve_size_key,
    validate_assembly,
)
from y4d_spec.frame_eval import (
    FrameEvaluationError,
    evaluate_expression,
    evaluate_frame,
    resolve_let,
)
from y4d_spec.semantic_rules import (
    FRAME_EXPRESSION_MAX_LENGTH,
    FRAME_GRAMMAR_MIN_KEYSTONE,
    FRAME_GRAMMAR_VERSION,
    LetCycleError,
    canonical_number_key,
    frame_expression_problems,
    frame_grammar_features,
    interface_frame_rules,
    let_evaluation_order,
)

FIXTURE = Path(__file__).parent / "fixtures" / "y4d" / "semantic-motor-mount.project.json"
SOLID = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _doc() -> dict:
    return copy.deepcopy(SOLID)


def _iface(doc: dict, i: int = 0) -> dict:
    return doc["hyperobject"]["cdg_interfaces"][i]


def _ev(expr, **values):
    return evaluate_expression(expr, values)


# ── D2: functions ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "expr, expected",
    [
        # Degrees, exact where OpenSCAD's are exact.
        ("sin(0)", 0.0), ("sin(30)", 0.5), ("sin(45)", math.sqrt(0.5)), ("sin(90)", 1.0),
        ("sin(150)", 0.5), ("sin(180)", 0.0), ("sin(270)", -1.0), ("sin(-90)", -1.0),
        ("sin(390)", 0.5), ("cos(0)", 1.0), ("cos(60)", 0.5), ("cos(90)", 0.0),
        ("cos(180)", -1.0), ("cos(-60)", 0.5), ("tan(45)", 1.0), ("tan(0)", 0.0),
        ("tan(180)", 0.0),
        ("asin(1)", 90.0), ("asin(0.5)", 30.0), ("acos(0)", 90.0), ("acos(-1)", 180.0),
        ("atan(1)", 45.0), ("atan2(1, 1)", 45.0), ("atan2(1, -1)", 135.0),
        ("atan2(-1, 0)", -90.0),
        ("sqrt(16)", 4.0), ("sqrt(0)", 0.0),
        ("floor(2.7)", 2.0), ("floor(-2.2)", -3.0), ("ceil(2.1)", 3.0), ("ceil(-2.7)", -2.0),
        # round: half away from zero, as OpenSCAD's round().
        ("round(2.5)", 3.0), ("round(-2.5)", -3.0), ("round(2.4)", 2.0), ("round(0.5)", 1.0),
    ],
)
def test_functions(expr, expected):
    assert _ev(expr) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(
    "expr, expected",
    [("sin(30)", 0.5), ("sin(180)", 0.0), ("cos(90)", 0.0), ("cos(60)", 0.5),
     ("sin(45)", math.sqrt(0.5)), ("tan(45)", 1.0), ("cos(270)", 0.0), ("sin(-180)", 0.0)],
)
def test_forward_trig_is_exact_at_openscads_exact_angles(expr, expected):
    # Exact, not approximately: a frame at 90° must not carry a 6e-17 x component.
    assert _ev(expr) == expected


def test_trig_off_the_exact_angles_matches_radian_maths():
    assert _ev("sin(55)") == pytest.approx(math.sin(math.radians(55)), abs=1e-15)
    assert _ev("cos(55)") == pytest.approx(math.cos(math.radians(55)), abs=1e-15)
    assert _ev("tan(20)") == pytest.approx(math.tan(math.radians(20)), abs=1e-15)


def test_trig_round_trips():
    for deg in (0, 10, 25, 30, 45, 55, 80):
        assert _ev(f"asin(sin({deg}))") == pytest.approx(deg, abs=1e-9)
        assert _ev(f"atan2(sin({deg}), cos({deg}))") == pytest.approx(deg, abs=1e-9)


def test_round_never_returns_negative_zero():
    assert math.copysign(1.0, _ev("round(-0.4)")) == 1.0


@pytest.mark.parametrize(
    "expr, fragment",
    [
        ("asin(2)", "asin(2) is outside its domain"),
        ("acos(0 - 1.1)", "acos(-1.1) is outside its domain"),
        ("sqrt(0 - 1)", "sqrt(-1) is outside its domain"),
        ("tan(90)", "tan(90) is undefined"),
        ("tan(270)", "tan(270) is undefined"),
        ("tan(0 - 90)", "tan(-90) is undefined"),
        ("atan2(0, 0)", "atan2(0, 0) is undefined"),
        ("1 / (a - a)", "division by zero"),
    ],
)
def test_domain_errors_are_evaluation_errors_never_nan(expr, fragment):
    with pytest.raises(FrameEvaluationError) as info:
        _ev(expr, a=3)
    assert fragment in str(info.value)


def test_asin_tolerates_float_noise_past_one():
    # a / sqrt(a*a) can land a hair above 1; that is noise, not a domain error.
    assert _ev("asin(1 + 0.0000000000001)") == 90.0


@pytest.mark.parametrize(
    "expr, fragment",
    [
        ("sin(1, 2)", "calls sin() with 2 argument(s), needs 1"),
        ("atan2(1)", "calls atan2() with 1 argument(s), needs 2"),
        ("iif(1, 2)", "calls iif() with 2 argument(s), needs 3"),
        ("hypot(3, 4)", "calls 'hypot'"),
        ("pow(2, 3)", f"frame grammar v{FRAME_GRAMMAR_VERSION}"),
        ("exp(1)", f"hyperobjects-spec >= {FRAME_GRAMMAR_MIN_KEYSTONE}"),
        ("a.sin(1)", "calls '<expression>'"),
        ("sin(x=1)", "keyword arguments"),
    ],
)
def test_calls_outside_the_allow_list_are_refused(expr, fragment):
    problems = frame_expression_problems(expr, {"a"})
    assert any(fragment in p for p in problems), problems


# ── D2: comparisons and iif ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    "expr, expected",
    [
        ("a < b", 1.0), ("a <= a", 1.0), ("a > b", 0.0), ("b >= a", 1.0),
        ("a == 2", 1.0), ("a != 2", 0.0), ("(a < b) + (b < a)", 1.0),
        ("iif(a > b, 10, 20)", 20.0), ("iif(a < b, 10, 20)", 10.0),
        ("iif(0, 1, 2)", 2.0), ("iif(0.5, 1, 2)", 1.0),
        # A step function, the way n_straps needs one.
        ("1 + iif(pack_l >= 45, 1, 0)", 2.0),
    ],
)
def test_comparisons_and_iif(expr, expected):
    assert _ev(expr, a=2, b=3, pack_l=60) == expected


def test_iif_is_lazy_so_the_branch_not_taken_cannot_fail():
    assert _ev("iif(x > 0, sqrt(x), 0)", x=-4) == 0.0
    assert _ev("iif(x > 0, sqrt(x), 1 / 0)", x=4) == 2.0
    with pytest.raises(FrameEvaluationError, match="division by zero"):
        _ev("iif(x > 0, sqrt(x), 1 / 0)", x=-4)


@pytest.mark.parametrize(
    "expr, fragment",
    [
        ("a < b < 3", "chains comparisons"),
        ("a < b and b < 3", "unsupported syntax (BoolOp)"),
        ("not a", "unsupported operator Not"),
        ("a is b", "unsupported operator Is"),
        ("!a", "does not parse"),
        ("a = 1", "does not parse"),
        ("'NEMA17' == a", "outside the grammar"),
        ("a % 2 > 1", "outside the grammar"),
    ],
)
def test_grammar_stays_numeric_and_safe(expr, fragment):
    problems = frame_expression_problems(expr, {"a", "b"})
    assert any(fragment in p for p in problems), problems


def test_the_length_limit_still_applies():
    long = "1 + " * 70 + "1"
    assert len(long) > FRAME_EXPRESSION_MAX_LENGTH
    assert frame_expression_problems(long, set()) == [
        f"is longer than {FRAME_EXPRESSION_MAX_LENGTH} characters"
    ]


# ── D1: let ───────────────────────────────────────────────────────────────────
NEMA_LET = {
    "pilot_r": {"param": "motor_pattern", "map": {"9x9": 4.5, "16x16": 8, "19x19": 9.5}},
    "half_span": "pilot_r / 2",
    "lift": "plate_thick + iso_gap + half_span * 0",
}


def _with_let(let_block, origin=None):
    doc = _doc()
    iface = _iface(doc)
    iface["let"] = copy.deepcopy(let_block)
    if origin is not None:
        iface["frame"]["origin"] = origin
    return doc


def test_let_lookup_and_expression_drive_a_frame():
    doc = _with_let(NEMA_LET, origin=["half_span", 0, "lift"])
    assert interface_frame_rules(doc) == []
    assert check_manifest(doc).ok
    for pattern, half in (("9x9", 2.25), ("16x16", 4.0), ("19x19", 4.75)):
        frame = evaluate_frame(doc, "motor_bolt_pattern", {"motor_pattern": pattern})
        assert frame.origin == (half, 0.0, 6.4)


def test_let_order_is_by_dependency_not_by_key_order():
    block = {"c": "b * 2", "b": "a + 1", "a": "plate_thick"}
    assert let_evaluation_order(block) == ["a", "b", "c"]
    assert resolve_let(block, {"plate_thick": 4.0}) == {"a": 4.0, "b": 5.0, "c": 10.0}
    # The same block with its keys sorted the other way (what jsonb would do) agrees.
    reordered = dict(sorted(block.items()))
    assert resolve_let(reordered, {"plate_thick": 4.0}) == {"a": 4.0, "b": 5.0, "c": 10.0}


@pytest.mark.parametrize(
    "block, cycle",
    [
        ({"a": "a + 1"}, ["a", "a"]),
        ({"a": "b + 1", "b": "a + 1"}, ["a", "b", "a"]),
        ({"x": "1", "a": "c", "b": "a", "c": "b"}, ["a", "c", "b", "a"]),
    ],
)
def test_let_cycles_are_named(block, cycle):
    with pytest.raises(LetCycleError) as info:
        let_evaluation_order(block)
    assert info.value.cycle == cycle
    problems = interface_frame_rules(_with_let(block))
    assert any("dependency cycle: " + " → ".join(cycle) in p for p in problems), problems
    with pytest.raises(FrameEvaluationError, match="dependency cycle"):
        evaluate_frame(_with_let(block), "motor_bolt_pattern")


@pytest.mark.parametrize(
    "block, fragment",
    [
        ({"x": "ghost + 1"}, "references unknown parameter 'ghost'"),
        ({"plate_thick": "2"}, "shadows the parameter 'plate_thick'"),
        ({"sin": "2"}, "shadows the function 'sin'"),
        ({"Bad-Name": "2"}, "name must match"),
        ({"x": 3}, "must be an expression string or {param, map}"),
        ({"x": "sin(1, 2)"}, "needs 1"),
        ({"x": "1" + " + 1" * 70}, "is longer than 256 characters"),
        ({"x": {"param": "plate_thick", "map": {"4": 1}}}, "reads a select's option values"),
        ({"x": {"param": "ghost", "map": {"a": 1}}}, "'ghost' is not a declared parameter"),
        ({"x": {"param": "motor_pattern", "map": {}}}, "must be a non-empty object"),
        ({"x": {"param": "motor_pattern",
                "map": {"9x9": 1, "16x16": "8", "19x19": 2}}}, "is not a finite number"),
        ({"x": {"param": "motor_pattern",
                "map": {"9x9": 1, "16x16": True, "19x19": 2}}}, "is not a finite number"),
        ({"x": {"param": "motor_pattern", "map": {"9x9": 1, "16x16": 2}}},
         "option '19x19' of 'motor_pattern' has no entry"),
        ({"x": {"param": "motor_pattern",
                "map": {"9x9": 1, "16x16": 2, "19x19": 3, "30x30": 4}}},
         "key '30x30' is not an option"),
        ({"x": {"param": "motor_pattern", "map": {"9x9": 1, "16x16": 2, "19x19": 3},
                "default": 1}}, "unexpected key 'default'"),
    ],
)
def test_let_problems_fail_visibly_at_check_time(block, fragment):
    problems = interface_frame_rules(_with_let(block))
    assert any(fragment in p for p in problems), problems
    assert not check_manifest(_with_let(block)).ok


def test_let_must_be_an_object():
    problems = interface_frame_rules(_with_let(["pilot_r"]))
    assert any("let: must be an object" in p for p in problems), problems


def test_a_frame_may_read_let_names_but_not_unknown_ones():
    assert interface_frame_rules(_with_let({"z": "plate_thick"}, ["0", 0, "z"])) == []
    problems = interface_frame_rules(_with_let({"z": "plate_thick"}, [0, 0, "zz"]))
    assert any("unknown parameter 'zz'" in p for p in problems), problems
    # Without the let block the same frame does not know `z`.
    doc = _doc()
    _iface(doc)["frame"]["origin"] = [0, 0, "z"]
    assert any("unknown parameter 'z'" in p for p in interface_frame_rules(doc))


def test_a_select_value_missing_from_the_map_is_an_evaluation_error_there():
    # The checker refuses an incomplete map; a hand-built manifest that skipped the
    # check still fails at the parameter point, never silently.
    block = {"r": {"param": "motor_pattern", "map": {"16x16": 8}}}
    doc = _with_let(block, [0, 0, "r"])
    assert evaluate_frame(doc, "motor_bolt_pattern").origin == (0.0, 0.0, 8.0)
    with pytest.raises(FrameEvaluationError) as info:
        evaluate_frame(doc, "motor_bolt_pattern", {"motor_pattern": "9x9"})
    assert "motor_pattern = '9x9' has no entry in its map" in str(info.value)


def test_let_errors_name_the_entry():
    with pytest.raises(FrameEvaluationError, match=r"let 'r': .*sqrt\(-4\)"):
        resolve_let({"r": "sqrt(0 - plate_thick)"}, {"plate_thick": 4.0})
    with pytest.raises(FrameEvaluationError, match="shadow a parameter"):
        resolve_let({"plate_thick": "1"}, {"plate_thick": 4.0})
    with pytest.raises(FrameEvaluationError, match="must be an object"):
        resolve_let(["x"], {})


def test_strings_never_enter_an_expression():
    # A select's string value is unreadable in an expression; only a lookup turns it
    # into a number.
    doc = _with_let({}, [0, 0, "motor_pattern"])
    with pytest.raises(FrameEvaluationError, match="not a number"):
        evaluate_frame(doc, "motor_bolt_pattern")


def test_let_is_schema_valid_and_the_schema_refuses_strings_on_the_right():
    from jsonschema import Draft202012Validator

    import hyperobjects_schemas as hs

    validator = Draft202012Validator(hs.load("project-manifest"))
    assert not list(validator.iter_errors(_with_let(NEMA_LET)))
    bad = _with_let({"r": {"param": "motor_pattern", "map": {"9x9": "4.5"}}})
    assert list(validator.iter_errors(bad))


# ── D3: slider size keys ──────────────────────────────────────────────────────
SLIDER_KEY = {"param": "plate_thick", "map": {"4": "tslot-2020-6mm", "6.5": "bearing-608"}}


def _slider_doc(size_key=SLIDER_KEY):
    doc = _doc()
    _iface(doc)["size_key"] = copy.deepcopy(size_key)
    return doc


def test_a_slider_size_key_is_well_formed():
    assert interface_frame_rules(_slider_doc()) == []


@pytest.mark.parametrize(
    "mapping, fragment",
    [
        ({"4.0": "tslot-2020-6mm"}, "key '4.0' is not in canonical form; write '4'"),
        ({"6.50": "bearing-608"}, "write '6.5'"),
        ({"thick": "bearing-608"}, "key 'thick' is not a number"),
        ({"9": "bearing-608"}, "outside 'plate_thick' [2.0, 8.0]"),
        ({"4": ""}, "must be a non-empty key string"),
    ],
)
def test_slider_size_key_problems(mapping, fragment):
    problems = interface_frame_rules(_slider_doc({"param": "plate_thick", "map": mapping}))
    assert any(fragment in p for p in problems), problems


@pytest.mark.parametrize(
    "value, canonical",
    [(12.0, "12"), (9.5, "9.5"), ("9.50", "9.5"), (-0.0, "0"), (0.1, "0.1"), ("x", None),
     (True, None), (float("nan"), None)],
)
def test_canonical_number_key(value, canonical):
    assert canonical_number_key(value) == canonical


def test_slider_resolution_matches_exact_values_otherwise_none():
    params = {"plate_thick": {"type": "slider"}}
    assert resolve_size_key(SLIDER_KEY, {"plate_thick": 4.0}, params) == ("tslot-2020-6mm", None)
    assert resolve_size_key(SLIDER_KEY, {"plate_thick": 4}, params) == ("tslot-2020-6mm", None)
    assert resolve_size_key(SLIDER_KEY, {"plate_thick": 6.5}, params) == ("bearing-608", None)
    # 4.5 has no entry: no key, and that is not a problem.
    assert resolve_size_key(SLIDER_KEY, {"plate_thick": 4.5}, params) == (None, None)
    # A select keeps its old rule: a missing option IS a problem.
    sel = {"param": "m", "map": {"a": "k"}}
    assert resolve_size_key(sel, {"m": "b"}, {"m": {"type": "select"}})[1] == (
        "size_key.map has no entry for m = 'b'"
    )


def test_resolve_interfaces_records_why_a_slider_has_no_key():
    doc = _slider_doc()
    at_4 = resolve_interfaces(doc, {"plate_thick": 4.0})["motor_bolt_pattern"]
    assert at_4.size_key == "tslot-2020-6mm" and at_4.size_key_absent_reason is None
    at_5 = resolve_interfaces(doc, {"plate_thick": 5.0})["motor_bolt_pattern"]
    assert at_5.size_key is None and at_5.problems == ()
    assert at_5.size_key_absent_reason.startswith("has no size_key at plate_thick = 5.0")


class _Store:
    def __init__(self, manifest):
        self.manifest = manifest

    def resolve(self, component):
        given = component["source"].get("parameters")
        return ResolvedComponent(
            component_id=component["id"], source_type="standard", label="store",
            identity={"type": "standard", "key": component["id"]},
            interfaces=resolve_interfaces(self.manifest, given, default_part="body"),
        )


def test_a_mate_that_needs_a_missing_slider_key_fails_there_by_name():
    plate = {
        "parameters": [{"id": "t", "type": "slider", "default": 4, "min": 2, "max": 8}],
        "hyperobject": {"cdg_interfaces": [
            {"id": "top", "polarity": "male", "symmetry": 0,
             "size_key": {"param": "t", "map": {"4": "bearing-608"}},
             "frame": {"origin": [0, 0, "t"], "normal": [0, 0, 1]}},
            {"id": "seat", "polarity": "female", "symmetry": 0, "size_key": "bearing-608",
             "frame": {"origin": [0, 0, 0], "normal": [0, 0, -1]}},
        ]},
    }

    def doc(t):
        a = {"id": "a", "source": {"type": "standard", "key": "plate", "parameters": {"t": t}}}
        b = {"id": "b", "source": {"type": "standard", "key": "plate"}}
        return {
            "format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "x",
            "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
            "root": "a", "components": [a, b],
            "mates": [{"id": "m1", "a": {"component": "a", "interface": "top"},
                       "b": {"component": "b", "interface": "seat"}, "angle_deg": 0}],
        }

    assert validate_assembly(doc(4), _Store(plate)).ok
    report = validate_assembly(doc(5), _Store(plate))
    assert not report.ok
    messages = [f.message for f in report.errors]
    assert any("'a.top' has no size_key at t = 5" in m for m in messages), messages
    assert not any("declares no size_key" in m for m in messages), messages


# ── D7: feature detection ─────────────────────────────────────────────────────
def test_a_v1_0_manifest_uses_no_v1_1_feature():
    assert frame_grammar_features(_doc()) == []
    assert not any("needs hyperobjects-spec" in n for n in check_manifest(_doc()).notes)


def test_v1_1_features_are_detected_and_named_in_a_note():
    doc = _with_let(NEMA_LET, origin=["half_span * cos(0)", 0, "iif(lift > 1, lift, 1)"])
    _iface(doc, 1)["frame"]["origin"] = [0, 0, "-max(foot_drop, round(2 * plate_thick))"]
    _iface(doc, 1)["size_key"] = {"param": "foot_drop", "map": {"14": "tslot-2020-6mm"}}
    features = frame_grammar_features(doc)
    assert features == ["comparison", "iif", "let", "slider size_key", "sqrt/rounding", "trig"]
    result = check_manifest(doc)
    assert result.ok, result.problems
    note = [n for n in result.notes if "needs hyperobjects-spec" in n]
    assert len(note) == 1
    assert f">= {FRAME_GRAMMAR_MIN_KEYSTONE}" in note[0]
    assert "comparison, iif, let, slider size_key, sqrt/rounding, trig" in note[0]
