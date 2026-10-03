"""The standard-parts catalog (ASM-1 §4): the bundled entries, the loader, the lane.

Every failure class the lane claims (``hyperobjects_standard_parts.check``) has a case
here, built by mutating a deep copy of a real catalog entry.
"""

from __future__ import annotations

import copy
import json
import math

import pytest

from hyperobjects_lexicon.fabrication import load_fabrication_vocabularies
from hyperobjects_lexicon.membership import manifest_vocabulary_problems
from hyperobjects_schemas import list_schemas
from hyperobjects_standard_parts import (
    ParameterError,
    interface_frames,
    list_part_keys,
    load_catalog,
    load_part,
    part_digest,
    resolve_parameters,
)
from hyperobjects_standard_parts.check import (
    AXIS_TOLERANCE,
    catalog_status,
    check_catalog,
    check_part,
)

#: ASM-1 §4's minimum set for the two test assemblies.
ASM1_MINIMUM = {
    # A — producer (Voron 2.4-class motion frame)
    "nema-17-48mm",
    "extrusion-2020",
    "mgn12-rail",
    "mgn12h-carriage",
    "bearing-608",
    "gt2-pulley-20t-5mm",
    "psu-meanwell-lrs-200",
    "microswitch-d2f",
    # B — product (5-inch FPV quadcopter)
    "motor-2207",
    "fpv-frame-5in-x-225",
    "fc-stack-30x30",
    "fpv-camera-micro-19mm",
    "prop-5in",
    "vtx-antenna-sma",
}

KEYS = list_part_keys()


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def vocabularies():
    return load_fabrication_vocabularies()


def _bad(part, vocabularies, mutate):
    doc = copy.deepcopy(part)
    mutate(doc)
    return check_part(doc, name=doc.get("key"), vocabularies=vocabularies)


# --- the bundled catalog ------------------------------------------------------------------


def test_schema_is_registered():
    assert "standard-part" in list_schemas()


def test_catalog_covers_the_asm1_minimum_set():
    assert ASM1_MINIMUM <= set(KEYS)


def test_bundled_catalog_is_clean(catalog, vocabularies):
    result = check_catalog(catalog, vocabularies=vocabularies)
    assert result.ok, "\n".join(result.problems)
    assert result.parts == len(KEYS) >= 14
    assert result.interfaces >= 37


@pytest.mark.parametrize("key", KEYS)
def test_entry_is_clean_and_named_for_its_key(key, vocabularies):
    part = load_part(key)
    assert part["key"] == key
    assert check_part(part, name=key, vocabularies=vocabularies) == []


@pytest.mark.parametrize("key", KEYS)
def test_every_size_key_resolves_through_the_membership_rule(key, vocabularies):
    part = load_part(key)
    manifest = {"hyperobject": {"cdg_interfaces": part["interfaces"]}}
    assert manifest_vocabulary_problems(manifest, vocabularies=vocabularies) == []


@pytest.mark.parametrize("key", KEYS)
def test_frames_evaluate_with_unit_orthogonal_axes(key):
    part = load_part(key)
    for iid, frame in interface_frames(part).items():
        n, x = frame.normal, frame.x_axis
        assert math.isclose(math.hypot(*n), 1.0, abs_tol=AXIS_TOLERANCE), iid
        assert math.isclose(math.hypot(*x), 1.0, abs_tol=AXIS_TOLERANCE), iid
        assert abs(sum(a * b for a, b in zip(n, x, strict=True))) <= AXIS_TOLERANCE, iid


@pytest.mark.parametrize("key", KEYS)
def test_every_fact_is_cited(key):
    part = load_part(key)
    count = len(part["sources"])
    assert 0 <= part["governing"]["source"] < count
    for name, dim in part["dimensions"].items():
        assert 0 <= dim["source"] < count, name
    for src in part["sources"]:
        assert src["url"].startswith("https://")


def test_the_frame_class_says_it_copies_no_design():
    frame = load_part("fpv-frame-5in-x-225")
    assert frame["governing"]["kind"] == "class"
    assert "not a design" in frame["notes"]
    assert "copies no branded frame" in frame["notes"]
    mounts = [i for i in frame["interfaces"] if i["id"].startswith("motor_mount_")]
    assert len(mounts) == 4
    assert {i["size_key"] for i in mounts} == {"motor-mount-16x16-m3"}


def test_the_frame_wheelbase_is_225_at_the_defaults():
    frame = load_part("fpv-frame-5in-x-225")
    frames = interface_frames(frame)
    fl, rr = frames["motor_mount_fl"].origin, frames["motor_mount_rr"].origin
    assert math.isclose(math.dist(fl, rr), 225.0, abs_tol=0.01)


def test_catalog_status_line(catalog):
    (line,) = catalog_status(catalog)
    assert line.startswith(f"standard_parts_status: parts={len(catalog)} ")
    assert "review: signed=0 draft=" in line


# --- loader, parameters and frames --------------------------------------------------------


def test_resolve_parameters_full_injection():
    part = load_part("extrusion-2020")
    values = resolve_parameters(part, {"length_mm": 500})
    assert values == {"length_mm": 500.0, "slot_station_mm": 10.0}


def test_out_of_range_is_an_error_never_clamped():
    part = load_part("extrusion-2020")
    with pytest.raises(ParameterError, match="never clamped"):
        resolve_parameters(part, {"length_mm": 4000.5})


def test_undeclared_and_non_numeric_parameters_are_errors():
    part = load_part("extrusion-2020")
    with pytest.raises(ParameterError, match="not a parameter"):
        resolve_parameters(part, {"width_mm": 20})
    with pytest.raises(ParameterError, match="not a number"):
        resolve_parameters(part, {"length_mm": True})


def test_frames_follow_the_parameters():
    part = load_part("extrusion-2020")
    frames = interface_frames(part, resolve_parameters(part, {"length_mm": 420}))
    assert frames["end_b"].origin == (0.0, 0.0, 420.0)
    assert frames["slot_xp_b"].origin == (10.0, 0.0, 410.0)
    rail = load_part("mgn12-rail")
    track = interface_frames(rail, resolve_parameters(rail, {"length_mm": 300}))["track"]
    assert track.origin == (150.0, 0.0, 8.0)


def test_block_on_rail_puts_the_top_face_at_assembly_height():
    """H 13 = rail top (HR 8) + the block's rail_way depth (5): the two entries agree."""
    rail = interface_frames(load_part("mgn12-rail"))["track"]
    block = interface_frames(load_part("mgn12h-carriage"))["rail_way"]
    assert rail.origin[2] - block.origin[2] == 13.0


def test_part_digest_is_stable_and_content_sensitive():
    part = load_part("bearing-608")
    assert part_digest(part) == part_digest(copy.deepcopy(part))
    assert len(part_digest(part)) == 64
    changed = copy.deepcopy(part)
    changed["dimensions"]["width"]["value"] = 7.5
    assert part_digest(changed) != part_digest(part)


def test_load_part_unknown_key():
    with pytest.raises(KeyError):
        load_part("no-such-part")


def test_catalog_from_a_directory(tmp_path):
    part = load_part("prop-5in")
    (tmp_path / "prop-5in.json").write_text(json.dumps(part), encoding="utf-8")
    assert list_part_keys(tmp_path) == ["prop-5in"]
    assert check_catalog(load_catalog(tmp_path)).ok


# --- every failure class ------------------------------------------------------------------


@pytest.fixture(scope="module")
def motor():
    return load_part("nema-17-48mm")


def test_schema_failure(motor, vocabularies):
    problems = _bad(motor, vocabularies, lambda d: d.pop("frame_convention"))
    assert any("frame_convention" in p for p in problems)


def test_key_and_file_name_must_agree(motor, vocabularies):
    problems = check_part(motor, name="nema-17-40mm", vocabularies=vocabularies)
    assert any("in a file named" in p for p in problems)


def test_blank_language_fails(motor, vocabularies):
    problems = _bad(motor, vocabularies, lambda d: d["name"].update(fr="   "))
    assert any("name.fr" in p for p in problems)


def test_unsigned_review_fails(motor, vocabularies):
    problems = _bad(motor, vocabularies, lambda d: d.update(review_status={"state": "reviewed"}))
    assert any("no reviewers" in p for p in problems)


def test_dangling_citation_fails(motor, vocabularies):
    problems = _bad(motor, vocabularies, lambda d: d["dimensions"]["hole_spacing"].update(source=9))
    assert any("dimensions.hole_spacing: cites source 9" in p for p in problems)


def test_default_outside_range_fails(motor, vocabularies):
    problems = _bad(motor, vocabularies, lambda d: d["parameters"][0].update(default=30))
    assert any("outside [0, 24]" in p for p in problems)


def test_duplicate_interface_fails(motor, vocabularies):
    problems = _bad(motor, vocabularies, lambda d: d["interfaces"].append(d["interfaces"][0]))
    assert any("declared twice" in p for p in problems)


def test_unknown_size_key_fails_through_membership(motor, vocabularies):
    problems = _bad(
        motor, vocabularies, lambda d: d["interfaces"][0].update(size_key="nema-17-fac")
    )
    assert any(
        "fabrication vocabulary:" in p and "did you mean 'nema-17-face'" in p for p in problems
    )


def test_geometry_type_must_match_the_size_key(motor, vocabularies):
    problems = _bad(
        motor, vocabularies, lambda d: d["interfaces"][0].update(geometry_type="flange")
    )
    assert any("differs from size key" in p for p in problems)


def test_frame_part_must_be_the_entry(motor, vocabularies):
    problems = _bad(motor, vocabularies, lambda d: d["interfaces"][0]["frame"].update(part="body"))
    assert any("one rigid body" in p for p in problems)


def test_non_unit_normal_fails(motor, vocabularies):
    problems = _bad(
        motor, vocabularies, lambda d: d["interfaces"][0]["frame"].update(normal=[0, 0, 2])
    )
    assert any("|normal| = 2" in p for p in problems)


def test_non_orthogonal_x_axis_fails(motor, vocabularies):
    def tilt(d):
        d["interfaces"][0]["frame"]["x_axis"] = [0.6, 0, 0.8]

    problems = _bad(motor, vocabularies, tilt)
    assert any("not orthogonal" in p for p in problems)


def test_unknown_identifier_fails(motor, vocabularies):
    problems = _bad(
        motor, vocabularies, lambda d: d["interfaces"][1]["frame"].update(origin=[0, 0, "seat"])
    )
    assert any("reads 'seat', which is not a parameter" in p for p in problems)


def test_an_expression_parameter_must_be_listed(motor, vocabularies):
    problems = _bad(motor, vocabularies, lambda d: d["interfaces"][1].pop("parameters"))
    assert any("does not list it" in p for p in problems)


def test_a_listed_parameter_must_exist(motor, vocabularies):
    problems = _bad(motor, vocabularies, lambda d: d["interfaces"][0].update(parameters=["ghost"]))
    assert any("lists 'ghost'" in p for p in problems)


def test_expression_outside_the_grammar_fails(motor, vocabularies):
    def attack(d):
        d["interfaces"][1]["frame"]["origin"] = [0, 0, "shaft_seat_mm.__class__"]

    problems = _bad(motor, vocabularies, attack)
    assert any("outside the frame grammar" in p for p in problems)


def test_division_by_zero_at_a_parameter_extreme_fails(motor, vocabularies):
    def divide(d):
        d["interfaces"][1]["frame"]["origin"] = [0, 0, "1 / shaft_seat_mm"]

    problems = _bad(motor, vocabularies, divide)
    assert any("at shaft_seat_mm=min" in p and "division by zero" in p for p in problems)
