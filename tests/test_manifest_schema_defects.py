"""The project-manifest schema defect fixes (SEM-1 §2.1).

Until this fix, `hyperobject`, `materials`, `source` and `estimate_constants` sat at the
schema ROOT, beside `properties`. JSON Schema ignores unknown root keywords, so none of
the four was ever applied: `hyperobject.cdg_interfaces` was not validated at all, and
`parts` was `required` without a definition. These tests pin the fix: each block now
VALIDATES (a wrong value fails), and each relaxation measured against the 502 solid
manifests is still accepted.
"""

from __future__ import annotations

import copy

import pytest
from jsonschema import Draft202012Validator

import hyperobjects_schemas as hs

MOVED = ("materials", "source", "hyperobject", "estimate_constants")

BASE = {
    "project": {"name": "Plate", "slug": "plate", "version": "1.0.0"},
    "modes": [{"scad_file": "plate.py", "label": {"en": "Plate"}, "parts": ["plate"],
               "estimate": "1"}],
    "parts": [{"id": "plate", "label": {"en": "Plate", "es": "Placa"}, "render_mode": 0,
               "color": "#a0a0a0"}],
    "parameters": [],
    "hyperobject": {
        "domain": "industrial",
        "cdg_interfaces": [
            {"id": "base", "label": {"en": "Base"}, "geometry_type": "surface"}
        ],
        "material_awareness": {"tolerance_by_material": True},
        "commons_license": "CERN-OHL-W-2.0",
    },
}


def _errors(doc: dict) -> list[str]:
    validator = Draft202012Validator(hs.load("project-manifest"))
    return [
        "/".join(str(p) for p in e.absolute_path) + ": " + e.message
        for e in validator.iter_errors(doc)
    ]


def _with(**changes) -> dict:
    doc = copy.deepcopy(BASE)
    doc.update(changes)
    return doc


def test_the_base_manifest_is_valid():
    assert _errors(BASE) == []


def test_no_definition_is_left_at_the_schema_root():
    schema = hs.load("project-manifest")
    for key in MOVED:
        assert key not in schema, f"{key} sits at the schema root, where it is ignored"
        assert key in schema["properties"], key
    assert "parts" in schema["properties"], "parts is required, so it must be defined"


def test_hyperobject_is_validated_now():
    doc = _with()
    doc["hyperobject"]["domain"] = "tool"
    assert any("hyperobject/domain" in e for e in _errors(doc))


def test_cdg_interface_shape_is_validated_now():
    doc = _with()
    del doc["hyperobject"]["cdg_interfaces"][0]["geometry_type"]
    assert any("geometry_type" in e for e in _errors(doc))


def test_estimate_constants_is_validated_now():
    assert _errors(_with(estimate_constants={"base_time": 1, "per_unit": 2, "per_part": 3})) == []
    assert _errors(_with(estimate_constants={"base_time": 1}))


def test_source_is_validated_now():
    assert _errors(_with(source={"type": "github"})) == []
    assert _errors(_with(source={"type": "ftp"}))


@pytest.mark.parametrize(
    "part",
    [
        {"id": "plate", "label": "Plate"},
        {"id": "plate", "name": {"en": "Plate"}},
        {"id": "plate", "label": "Plate", "default_color": "#ffffff", "glass": True},
    ],
)
def test_parts_accepts_the_observed_shapes(part):
    assert _errors(_with(parts=[part])) == []


@pytest.mark.parametrize(
    "part",
    [
        {"label": "Plate"},  # no id
        {"id": "plate"},  # no display string
        {"id": "plate", "label": "Plate", "render_mode": -1},
        {"id": "plate", "label": "Plate", "color": "grey"},
    ],
)
def test_parts_rejects_malformed_entries(part):
    assert _errors(_with(parts=[part]))


def test_i18n_string_allows_all_four_commons_locales():
    """RFC 0039's quadrilingual ruling: fr and pt are declared, not merely tolerated."""
    obj = hs.load("project-manifest")["$defs"]["i18nString"]["oneOf"][1]
    assert set(obj["properties"]) == {"en", "es", "fr", "pt"}
    doc = _with()
    doc["project"]["description"] = {"en": "a", "es": "b", "fr": "c", "pt": "d"}
    assert _errors(doc) == []


# --- relaxations measured against the 502 solid manifests -----------------------


def test_relaxation_material_awareness_bare_true():
    """2 cartridges (flange-plate, spacer-block) ship the legacy `true` shorthand; the
    platform copy of this schema accepts it, so the keystone does too."""
    doc = _with()
    doc["hyperobject"]["material_awareness"] = True
    assert _errors(doc) == []
    doc["hyperobject"]["material_awareness"] = "yes"
    assert _errors(doc)


def test_relaxation_materials_label_and_density_g_cm3():
    """1 cartridge (locking-mechanism-hyperobject, 3 entries) spells `name` as an i18n
    `label` and `density` as `density_g_cm3`. Either spelling satisfies the entry; one
    of each pair is still required."""
    alt = {"id": "pla", "label": {"en": "PLA"}, "density_g_cm3": 1.24, "cost_per_kg": 20}
    std = {"id": "pla", "name": "PLA", "density": 1.24, "cost_per_kg": 20}
    assert _errors(_with(materials=[alt, std])) == []
    assert _errors(_with(materials=[{"id": "pla", "density": 1.24, "cost_per_kg": 20}]))
    assert _errors(_with(materials=[{"id": "pla", "name": "PLA", "cost_per_kg": 20}]))
