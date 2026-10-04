"""SEM-1 §2.2–§2.4 and §3: the semantic manifest fields, schema and static rules.

The fixture `fixtures/y4d/semantic-motor-mount.project.json` is the full example: a
bolt-pattern interface with an expression frame, 4-fold symmetry and a size key mapped
from a select parameter; a second interface with continuous symmetry and no x_axis;
every parameter `unit`; and a requirement profile with a per-part override. Every
negative test below starts from that fixture and breaks exactly one thing.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import hyperobjects_schemas as hs
from y4d_spec import check_manifest
from y4d_spec.cli import main
from y4d_spec.semantic_rules import (
    frame_expression_problems,
    interface_frame_rules,
    requirements_rules,
)

FIXTURES = Path(__file__).parent / "fixtures"
SOLID = json.loads(
    (FIXTURES / "y4d" / "semantic-motor-mount.project.json").read_text(encoding="utf-8")
)
PARAMS = {p["id"] for p in SOLID["parameters"]}


def _doc() -> dict:
    return copy.deepcopy(SOLID)


def _iface(doc: dict, i: int = 0) -> dict:
    return doc["hyperobject"]["cdg_interfaces"][i]


def _schema_errors(doc: dict, name: str = "project-manifest") -> list[str]:
    validator = Draft202012Validator(hs.load(name))
    return [
        "/".join(str(p) for p in e.absolute_path) + ": " + e.message
        for e in validator.iter_errors(doc)
    ]


# --- the full example -----------------------------------------------------------


def test_the_full_example_is_conformant():
    result = check_manifest(_doc())
    assert result.ok, result.problems


def test_the_full_example_uses_every_new_field():
    """Guards the fixture itself: if someone trims it, these tests stop proving much."""
    doc = _doc()
    assert {p.get("unit") for p in doc["parameters"]} >= {"mm", "deg", "count", "ratio",
                                                          "percent"}
    iface = _iface(doc)
    assert isinstance(iface["frame"]["origin"][2], str)
    assert iface["symmetry"] == 4
    assert iface["size_key"]["param"] == "motor_pattern"
    assert doc["requirements"]["parts"]


# --- schema: unit ---------------------------------------------------------------


def test_schema_rejects_an_unknown_unit():
    doc = _doc()
    doc["parameters"][1]["unit"] = "inch"
    assert any("parameters/1/unit" in e for e in _schema_errors(doc))


# --- schema: interface fields ---------------------------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda f: f.update(origin=[0, 0]),
        lambda f: f.update(origin=[0, 0, 0, 0]),
        lambda f: f.update(normal=[0, 0, True]),
        lambda f: f.update(normal=[0, 0, ""]),
        lambda f: f.pop("part"),
        lambda f: f.pop("normal"),
        lambda f: f.update(rotation=[0, 0, 0]),
    ],
    ids=["2-components", "4-components", "bool", "empty-expr", "no-part", "no-normal",
         "unknown-key"],
)
def test_schema_rejects_a_malformed_frame(mutate):
    doc = _doc()
    mutate(_iface(doc)["frame"])
    assert _schema_errors(doc)


@pytest.mark.parametrize(
    "field,value",
    [
        ("polarity", "positive"),
        ("symmetry", 5),
        ("symmetry", "4"),
        ("size_key", ""),
        ("size_key", {"param": "motor_pattern"}),
        ("size_key", {"param": "motor_pattern", "map": {}}),
        ("size_key", {"param": "motor_pattern", "map": {"9x9": "a"}, "default": "a"}),
    ],
)
def test_schema_rejects_a_malformed_interface_field(field, value):
    doc = _doc()
    _iface(doc)[field] = value
    assert _schema_errors(doc)


def test_schema_requires_x_axis_when_symmetry_is_not_zero():
    doc = _doc()
    del _iface(doc)["frame"]["x_axis"]
    assert _schema_errors(doc)
    _iface(doc)["symmetry"] = 0
    assert _schema_errors(doc) == []


# --- schema: requirements -------------------------------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(processes=["fff"]),
        lambda r: r.update(process=[]),
        lambda r: r["materials"].update(all_of=["pla"]),
        lambda r: r["process_parameters"].update(wall_loops={"unit": "count"}),
        lambda r: r["process_parameters"].update(wall_loops={"min": "3"}),
        lambda r: r["parts"].update(rigid_mount={}),
        lambda r: r["parts"].update(rigid_mount={"parts": {}}),
    ],
    ids=["unknown-key", "empty-process", "unknown-selector", "no-bound", "string-min",
         "empty-override", "nested-parts"],
)
def test_schema_rejects_malformed_requirements(mutate):
    doc = _doc()
    mutate(doc["requirements"])
    assert _schema_errors(doc)


# --- rule: frame expressions ----------------------------------------------------


@pytest.mark.parametrize(
    "expr",
    ["plate_thick + iso_gap", "-max(foot_drop, 2 * plate_thick)", "abs(arm_angle) / 2",
     "(plate_thick - 1.5e-1) * min(iso_gap, 3, flex_slots)", "4"],
)
def test_a_grammatical_expression_has_no_problems(expr):
    assert frame_expression_problems(expr, PARAMS) == []


@pytest.mark.parametrize(
    "expr,needle",
    [
        ("plate_thick + bogus", "unknown parameter 'bogus'"),
        ("plate_thick ** 2", "unsupported operator Pow"),
        ("plate_thick % 2", "character outside the grammar"),
        ("plate_thick % 2 > 1", "character outside the grammar"),
        ("plate_thick // 2", "unsupported operator FloorDiv"),
        ("hypot(plate_thick, 1)", "calls 'hypot'"),
        ("abs(plate_thick, iso_gap)", "abs() with 2 argument(s)"),
        ("min(plate_thick)", "min() with 1 argument(s)"),
        ("plate_thick.real", "unsupported syntax"),
        ("__import__('os')", "character outside the grammar"),
        ("plate_thick +", "does not parse"),
        ("   ", "is empty"),
        ("1+" * 200 + "1", "longer than 256"),
    ],
)
def test_an_ungrammatical_expression_is_named(expr, needle):
    problems = frame_expression_problems(expr, PARAMS)
    assert any(needle in p for p in problems), problems


def test_a_bad_expression_in_a_frame_is_reported_with_its_place():
    doc = _doc()
    _iface(doc)["frame"]["origin"][2] = "plate_thick + nope"
    problems = interface_frame_rules(doc)
    assert any("frame.origin[2]" in p and "'nope'" in p for p in problems), problems


# --- rule: vectors, normal, x_axis, symmetry ------------------------------------


def test_rule_requires_three_components_without_the_schema():
    doc = _doc()
    _iface(doc)["frame"]["normal"] = [0, 1]
    assert any("exactly 3 components" in p for p in interface_frame_rules(doc))


@pytest.mark.parametrize("key", ["normal", "x_axis"])
def test_rule_rejects_a_zero_direction(key):
    doc = _doc()
    _iface(doc)["frame"][key] = [0, 0, 0.0]
    assert any(f"frame.{key}: is the zero vector" in p for p in interface_frame_rules(doc))


def test_rule_requires_x_axis_when_symmetric():
    doc = _doc()
    del _iface(doc)["frame"]["x_axis"]
    assert any("x_axis: required when symmetry is 4" in p for p in interface_frame_rules(doc))


def test_rule_requires_a_frame_when_symmetric():
    doc = _doc()
    del _iface(doc)["frame"]
    assert any("declares no frame" in p for p in interface_frame_rules(doc))


def test_rule_does_not_require_x_axis_for_continuous_symmetry():
    doc = _doc()
    assert "x_axis" not in _iface(doc, 1)["frame"]
    assert interface_frame_rules(doc) == []


@pytest.mark.parametrize(
    "x_axis,ok",
    [
        ([1, 0, 0], True),
        ([0, -2, 0], True),
        ([1, 0, 0.005], True),  # 0.29 degrees off
        ([1, 0, 0.01], False),  # 0.57 degrees off
        ([1, 0, 1], False),
        ([1, 0, "plate_thick"], True),  # an expression is the render gate's to judge
    ],
)
def test_rule_x_axis_orthogonal_to_normal(x_axis, ok):
    doc = _doc()
    _iface(doc)["frame"]["x_axis"] = x_axis
    problems = [p for p in interface_frame_rules(doc) if "orthogonal" in p]
    assert (problems == []) is ok, problems


def test_rule_frame_part_must_be_declared():
    doc = _doc()
    _iface(doc)["frame"]["part"] = "skid_mount"
    assert any("'skid_mount' is not a declared part" in p for p in interface_frame_rules(doc))


def test_rule_polarity_and_symmetry_enums():
    doc = _doc()
    _iface(doc)["polarity"] = "plug"
    _iface(doc, 1)["symmetry"] = 5
    problems = interface_frame_rules(doc)
    assert any("polarity: 'plug'" in p for p in problems)
    assert any("symmetry: 5" in p for p in problems)


# --- rule: size_key -------------------------------------------------------------


def test_rule_size_key_param_must_be_a_declared_select():
    doc = _doc()
    _iface(doc)["size_key"]["param"] = "plate_thick"
    # ASM-1 v1.1 (D3): a slider may key a size by EXACT value, so the select's option
    # spellings ("9x9", …) are now reported as non-numeric slider keys.
    assert any("is not a number" in p for p in interface_frame_rules(doc))
    _iface(doc)["size_key"]["param"] = "ghost"
    assert any("'ghost' is not a declared parameter" in p for p in interface_frame_rules(doc))


def test_rule_size_key_map_covers_every_option_and_nothing_else():
    doc = _doc()
    mapping = _iface(doc)["size_key"]["map"]
    del mapping["9x9"]
    mapping["22x22"] = "motor-mount-22x22-m3"
    problems = interface_frame_rules(doc)
    assert any("option '9x9' of 'motor_pattern' has no entry" in p for p in problems)
    assert any("key '22x22' is not an option" in p for p in problems)


def test_rule_size_key_compares_numeric_options_as_strings():
    doc = _doc()
    doc["parameters"][0]["options"] = [
        {"value": 9, "label": {"en": "9", "es": "9"}},
        {"value": 16, "label": {"en": "16", "es": "16"}},
    ]
    _iface(doc)["size_key"]["map"] = {"9": "motor-mount-9x9-m2", "16": "motor-mount-16x16-m3"}
    assert interface_frame_rules(doc) == []


# --- rule: requirements ---------------------------------------------------------


def test_rule_min_must_not_exceed_max():
    doc = _doc()
    doc["requirements"]["process_parameters"]["sparse_infill_density"] = {"min": 90, "max": 40}
    doc["requirements"]["parts"]["rigid_mount"]["process_parameters"] = {
        "wall_loops": {"min": 5, "max": 2}
    }
    problems = requirements_rules(doc)
    assert any("requirements.process_parameters.sparse_infill_density: min 90" in p
               for p in problems)
    assert any("requirements.parts['rigid_mount'].process_parameters.wall_loops" in p
               for p in problems)


def test_rule_override_keys_must_be_declared_parts():
    doc = _doc()
    doc["requirements"]["parts"]["skid_mount"] = {"process": ["fff"]}
    assert any("'skid_mount' is not a declared part" in p for p in requirements_rules(doc))


def test_rule_material_cannot_be_both_accepted_and_refused():
    doc = _doc()
    doc["requirements"]["materials"]["none_of"] = ["tpu-95a"]
    assert any("both accepted" in p for p in requirements_rules(doc))


@pytest.mark.parametrize(
    "requirements,needle",
    [
        ([], "requirements: must be an object"),
        ({"parts": []}, "requirements.parts: must be an object"),
        ({"process_parameters": {"wall_loops": {}}}, "states no bound"),
        ({"process_parameters": {"wall_loops": 3}}, "must be an object"),
    ],
)
def test_rule_requirements_shape_without_the_schema(requirements, needle):
    doc = _doc()
    doc["requirements"] = requirements
    assert any(needle in p for p in requirements_rules(doc))


def test_no_requirements_and_no_interface_fields_is_silent():
    doc = _doc()
    del doc["requirements"]
    for iface in doc["hyperobject"]["cdg_interfaces"]:
        for key in ("frame", "polarity", "size_key", "symmetry"):
            iface.pop(key, None)
    assert interface_frame_rules(doc) == []
    assert requirements_rules(doc) == []


# --- wiring ---------------------------------------------------------------------


def test_check_manifest_runs_both_rules():
    doc = _doc()
    _iface(doc)["frame"]["normal"] = [0, 0, 0]
    doc["requirements"]["parts"]["ghost"] = {"process": ["fff"]}
    problems = check_manifest(doc).problems
    assert any("zero vector" in p for p in problems)
    assert any("'ghost' is not a declared part" in p for p in problems)


def test_the_rules_listing_names_both_rules(capsys):
    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "interface_frame_rules" in out and "requirements_rules" in out


# --- soft: unit and requirements in the garment manifest ------------------------


def _garment() -> dict:
    return json.loads((FIXTURES / "fc" / "bodice-block.project.json").read_text("utf-8"))


def test_garment_accepts_unit_and_requirements():
    doc = _garment()
    doc["parameters"][0]["unit"] = "mm"
    piece = doc["pieces"][0]["id"]
    doc["requirements"] = {
        "process": ["laser_2d"],
        "materials": {"any_of": ["cotton-woven"]},
        "process_parameters": {"seam_allowance": {"min": 10, "unit": "mm"}},
        "rationale": {"en": "Woven cotton holds the block's shape.", "es": "El algodón."},
        "parts": {piece: {"materials": {"none_of": ["knit"]}}},
    }
    assert _schema_errors(doc, "garment-manifest") == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["parameters"][0].update(unit="cm"),
        lambda d: d.update(requirements={"process": "fff"}),
        lambda d: d.update(requirements={"parts": {"x": {"parts": {}}}}),
        lambda d: d.update(requirements={"unknown": 1}),
    ],
)
def test_garment_rejects_malformed_unit_or_requirements(mutate):
    doc = _garment()
    mutate(doc)
    assert _schema_errors(doc, "garment-manifest")


def test_both_garment_schema_copies_carry_the_new_fields():
    from fc_spec.conformance import _bundled_schema

    for schema in (hs.load("garment-manifest"), _bundled_schema("garment-manifest.schema.json")):
        assert "requirements" in schema["properties"]
        assert "unit" in schema["properties"]["parameters"]["items"]["properties"]
