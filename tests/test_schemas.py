"""Tests for hyperobjects_schemas — the bundled contracts and their loaders."""

import json

import pytest

import hyperobjects_schemas as hs


def test_every_declared_schema_is_actually_bundled():
    for name in hs.list_schemas():
        assert hs.schema_path(name).is_file(), f"{name} is declared but not shipped"


def test_every_bundled_schema_is_valid_json_schema():
    from jsonschema import Draft202012Validator

    for name in hs.list_schemas():
        Draft202012Validator.check_schema(hs.load(name))


def test_load_accepts_both_name_forms():
    assert hs.load("project-manifest") == hs.load("project-manifest.schema.json")


def test_unknown_schema_raises_keyerror():
    with pytest.raises(KeyError):
        hs.load("no-such-schema")
    with pytest.raises(KeyError):
        hs.schema_path("no-such-schema")


def test_the_y4d_manifest_schema_is_the_real_one():
    schema = hs.load("project-manifest")
    assert schema["required"] == ["project", "modes", "parts", "parameters"]


def test_provenance_is_recorded_for_every_schema():
    """Each bundled schema says which repo publishes it — without that a contributor
    cannot tell where to send a fix."""
    assert set(hs.SCHEMAS) == set(hs.list_schemas())
    for name, repo in hs.SCHEMAS.items():
        assert repo in {"yantra4d", "fashion-cabinet", "hyperobjects-spec"}, name


def test_loaded_schemas_are_cached_by_identity():
    assert hs.load("project-manifest") is hs.load("project-manifest")


def test_schema_files_are_utf8_and_parse():
    for name in hs.list_schemas():
        json.loads(hs.schema_path(name).read_text(encoding="utf-8"))
