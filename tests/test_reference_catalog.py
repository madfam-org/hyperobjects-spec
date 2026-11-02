"""The reference-objects catalog: the bundled objects, the loader, the lane, the CLI.

Every failure class the lane claims (``hyperobjects_reference.check``) has a case here,
built by mutating a deep copy of a real catalog object.
"""

from __future__ import annotations

import copy
import json
import re
from decimal import Decimal

import pytest

from hyperobjects_reference import (
    catalog_digest,
    covers,
    family_digest,
    field_exists,
    is_sourced,
    leaves,
    list_keys,
    load_catalog,
    load_family,
    load_object,
    object_digest,
    value_at,
)
from hyperobjects_reference.check import active_area, catalog_status, check_catalog, check_object
from hyperobjects_reference.cli import main
from hyperobjects_schemas import list_schemas

#: The families the import from Telesia's device-geometry registry carried (2026-11-01).
IMPORTED_FAMILIES = {
    "book-fold-phone": 28,
    "clamshell-dual-screen-handheld": 16,
    "dual-screen-hinge-phone": 5,
    "dual-screen-laptop": 5,
    "flip-fold-phone": 23,
    "foldable-laptop": 4,
    "swivel-dual-screen": 1,
    "tri-fold-phone": 2,
}


@pytest.fixture
def ds3():
    """Nintendo 3DS: published areas, a complete control list, eight primary sources."""
    return copy.deepcopy(load_object("nintendo-3ds"))


@pytest.fixture
def fold():
    """Xiaomi MIX Fold 3: two derived active areas."""
    return copy.deepcopy(load_object("xiaomi-mix-fold-3"))


def _index(obj, field):
    return next(i for i, s in enumerate(obj["sources"]) if s["field"] == field)


# ── the bundled catalog ────────────────────────────────────────────────────────────


def test_schema_is_bundled():
    assert "reference-object" in list_schemas()


def test_bundled_catalog_passes_the_lane():
    result = check_catalog()
    assert result.ok, "\n".join(result.problems)
    assert result.objects >= sum(IMPORTED_FAMILIES.values()) == 84


def test_every_object_is_named_for_its_key():
    for key, obj in load_catalog().items():
        assert obj["key"] == key


def test_imported_families_are_all_present():
    # Families only grow: an import is never silently dropped.
    catalog = load_catalog()
    families = {}
    for obj in catalog.values():
        families[obj["family"]] = families.get(obj["family"], 0) + 1
    for family, imported in IMPORTED_FAMILIES.items():
        assert families.get(family, 0) >= imported, family


def test_evidence_sweep_is_recorded():
    swept = [o["key"] for o in load_catalog().values()
             if any(n.startswith("EVIDENCE SWEEP 2026-11-01") for n in o.get("notes", []))]
    assert len(swept) == 17
    assert all(k.startswith(("samsung-", "oppo-", "sony-tablet-p")) for k in swept)


def test_status_line_counts_what_it_read():
    line = catalog_status()[0]
    assert re.match(
        r"reference_status: objects=[0-9]+ families=[0-9]+ values=[0-9]+ conflicts=[0-9]+ "
        r"status: .*partial=[0-9]+.* tiers: .*primary=[0-9]+", line)
    assert sum(1 for x in catalog_status() if x.startswith("  family ")) >= 8


def test_load_family_is_sorted_and_complete():
    objs = load_family("clamshell-dual-screen-handheld")
    assert [o["key"] for o in objs] == sorted(o["key"] for o in objs)
    assert len(objs) == 16


# ── paths and coverage ─────────────────────────────────────────────────────────────


def test_value_at_and_field_exists(ds3):
    assert value_at(ds3, "dimensions_mm.states.closed.width") == 74
    assert value_at(ds3, "displays[0].active_area_mm.width") == 76.8
    assert field_exists(ds3, "displays[].panel")
    assert not field_exists(ds3, "displays[9]")
    assert not field_exists(ds3, "dimensions_mm.closed")


def test_covers_subtrees_and_wildcards():
    assert covers("displays[0]", "displays[0].panel")
    assert covers("dimensions_mm.states.closed", "dimensions_mm.states.closed.depth")
    assert not covers("displays[0]", "displays[01].panel")
    assert not covers("mass", "mass_g")
    assert covers("displays[].panel", "displays[1].panel")
    assert not covers("displays[].panel", "displays[1].diagonal_in")


def test_absence_semantics(ds3):
    # The maker's control list is quoted, so it is complete: a missing kind is a zero.
    assert is_sourced(ds3, "controls")
    assert not any(c["kind"] == "trigger" for c in ds3["controls"])
    ds3["sources"] = [s for s in ds3["sources"] if s["field"] != "controls"]
    assert not is_sourced(ds3, "controls")     # now nothing is known either way


def test_secondary_sources_cover_nothing(ds3):
    i = _index(ds3, "mass_g")
    ds3["sources"][i]["tier"] = "secondary"
    del ds3["sources"][i]["quote"]
    assert not is_sourced(ds3, "mass_g")
    problems = check_object(ds3)
    assert any(p.startswith("mass_g: ") and "not covered" in p for p in problems)


def test_uncovered_value_fails(ds3):
    ds3["sources"] = [s for s in ds3["sources"] if s["field"] != "mass_g"]
    assert any(p.startswith("mass_g: 235") for p in check_object(ds3))


def test_a_label_is_sourced_by_anything_about_its_item(fold):
    # displays[0] is cited whole; cite only one of its values and the role still holds.
    i = _index(fold, "displays[0]")
    fold["sources"][i]["field"] = "displays[0].diagonal_in"
    problems = check_object(fold)
    assert not any("displays[0].role" in p for p in problems)
    assert any("displays[0].panel" in p for p in problems)


def test_a_port_with_no_source_fails(ds3):
    ds3["ports"].append({"kind": "usb_c", "position": None})
    ds3["sources"] = [s for s in ds3["sources"] if s["field"] != "ports"]
    assert any("ports[" in p and "'usb_c'" in p for p in check_object(ds3))


def test_derived_flag_is_bookkeeping(ds3):
    assert not any(p.endswith(".derived") for p, _ in leaves(ds3))


# ── schema, sources, tiers ─────────────────────────────────────────────────────────


def test_schema_refuses_unknown_keys(ds3):
    ds3["mesh"] = "a.stl"
    assert any("mesh" in p for p in check_object(ds3))


def test_file_must_be_named_for_its_key(ds3):
    assert any("is in a file named" in p for p in check_object(ds3, name="nintendo-2ds"))


def test_source_must_name_a_real_field(ds3):
    ds3["sources"][_index(ds3, "mass_g")]["field"] = "weight_g"
    problems = check_object(ds3)
    assert any("names a field that does not exist" in p for p in problems)


def test_primary_needs_its_quote(ds3):
    del ds3["sources"][_index(ds3, "mass_g")]["quote"]
    assert any("tier 'primary' needs quote" in p for p in check_object(ds3))


def test_measured_values_are_ours(ds3):
    i = _index(ds3, "mass_g")
    ds3["sources"][i] = {"field": "mass_g", "tier": "measured", "retrieved": "2026-11-01",
                         "url": "https://example.org/x", "instrument": "kitchen scale"}
    problems = check_object(ds3)
    assert any("needs resolution_mm, specimen, measurer_role" in p for p in problems)
    assert any("cites an instrument, not a URL" in p for p in problems)


def test_a_complete_measured_source_passes(ds3):
    ds3["sources"][_index(ds3, "mass_g")] = {
        "field": "mass_g", "tier": "measured", "retrieved": "2026-11-01",
        "instrument": "digital scale, calibrated 2026-10", "resolution_mm": 0.01,
        "specimen": "CTR-001 (JPN), collection unit 3", "measurer_role": "owner",
    }
    assert check_object(ds3) == []


# ── the derivation law ─────────────────────────────────────────────────────────────


def test_derivation_law_matches_the_registry():
    # Xiaomi MIX Fold 3 cover panel: 6.56 in, 2520 x 1080.
    assert active_area(6.56, Decimal(2520), Decimal(1080)) == (153.2, 65.6)


def test_derived_area_must_match_the_law(fold):
    fold["displays"][0]["active_area_mm"]["width"] = 153.3
    assert any("does not match the derivation law" in p for p in check_object(fold))


def test_derived_source_requires_the_flag(fold):
    fold["displays"][0]["active_area_mm"]["derived"] = False
    assert any("not marked derived: true" in p for p in check_object(fold))


def test_derived_needs_a_method(fold):
    del fold["sources"][_index(fold, "displays[0].active_area_mm")]["method"]
    assert any("tier 'derived' needs method" in p for p in check_object(fold))


# ── conflicts and status ───────────────────────────────────────────────────────────


def _conflict(obj, chosen_value):
    i = _index(obj, "mass_g")
    obj["sources"].append({**obj["sources"][i], "quote": "约 230 g"})
    obj["conflicts"] = [{
        "field": "mass_g",
        "candidates": [{"value": obj["mass_g"], "source": i},
                       {"value": 230, "source": len(obj["sources"]) - 1}],
        "chosen": 0 if chosen_value == obj["mass_g"] else 1,
        "reason": "the spec table is the maker's own figure; the press line rounds",
    }]


def test_a_decided_conflict_passes(ds3):
    _conflict(ds3, ds3["mass_g"])
    assert check_object(ds3) == []


def test_conflict_choice_must_match_the_value(ds3):
    _conflict(ds3, 230)
    assert any("the chosen candidate 230" in p for p in check_object(ds3))


def test_conflict_candidate_must_cover_the_field(ds3):
    _conflict(ds3, ds3["mass_g"])
    ds3["conflicts"][0]["candidates"][1]["source"] = _index(ds3, "released")
    assert any("does not cover the field" in p for p in check_object(ds3))


def test_unverified_means_no_sources(ds3):
    ds3["status"] = "unverified"
    assert any("'unverified' while value-tier sources exist" in p for p in check_object(ds3))
    tablet = copy.deepcopy(load_object("sony-tablet-p"))
    assert tablet["status"] == "unverified" and check_object(tablet) == []
    tablet["status"] = "partial"
    assert any("with no value-tier source" in p for p in check_object(tablet))


# ── digests and the CLI ────────────────────────────────────────────────────────────


def test_digests_track_facts_not_formatting(ds3):
    base = object_digest(ds3)
    assert object_digest(json.loads(json.dumps(ds3, indent=4))) == base
    ds3["mass_g"] = 236
    assert object_digest(ds3) != base


def test_family_digest_is_order_free():
    objs = load_family("tri-fold-phone")
    forward = catalog_digest({o["key"]: o for o in objs})
    backward = catalog_digest({o["key"]: o for o in reversed(objs)})
    assert forward == backward == family_digest("tri-fold-phone")


def test_cli_check_and_digest(capsys, tmp_path, ds3):
    assert main(["check"]) == 0
    # The catalog only grows (research lanes add objects); the import floor is 84.
    found = re.search(r"ho-reference check: objects=([0-9]+) values=", capsys.readouterr().out)
    assert found and int(found.group(1)) >= 84
    assert main(["digest", "--family", "tri-fold-phone"]) == 0
    assert capsys.readouterr().out.startswith(family_digest("tri-fold-phone"))
    ds3["mass_g"] = None
    ds3["sources"] = [s for s in ds3["sources"] if s["field"] != "released"]
    (tmp_path / "nintendo-3ds.json").write_text(json.dumps(ds3), encoding="utf-8")
    assert main(["check", "--objects", str(tmp_path)]) == 1
    assert "FAIL nintendo-3ds: released:" in capsys.readouterr().out
    assert main(["digest", "--family", "nope", "--objects", str(tmp_path)]) == 1


def test_list_keys_of_an_empty_directory(tmp_path):
    assert list_keys(tmp_path) == []
