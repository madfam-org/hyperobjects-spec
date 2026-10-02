"""GOC-1 — the generator-output schema, its four algorithms, the checker and the CLIs.

The golden vectors below are pinned on purpose: yantra4d and Fashion Cabinet implement
the same algorithms in their own code, and a digest that silently changed here would
fork the fleet. Recompute them only alongside a contract version bump.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

import hyperobjects_schemas as hs
from hyperobjects_schemas.generator_output import (
    FORMAT,
    TREE_ALGORITHM,
    canonical_json,
    check_generator_output,
    check_generator_output_file,
    collect_generator_output_files,
    instance_id,
    normalize_numbers,
    tree_sha256,
    variables_sha256,
)

FIXTURE = Path(__file__).parent / "fixtures" / "generator-output" / "thimble"
FIXTURE_DOC = FIXTURE / "thimble.variables.json"

# §3.2's own example: provenance excluded, `null` for a source_default entry.
CONTRACT_VARIABLES = [
    {"id": "clearance", "value": 0.3, "type": "number", "source": "request"},
    {"id": "mode_flag", "value": True, "type": "boolean", "source": "manifest_default"},
    {"id": "wall", "value": None, "type": "number", "source": "source_default"},
]
GOLDEN_CONTRACT_VARIABLES_SHA256 = (
    "c00f4dbbfbafc08f6a1866035db2d755919396e58aacaace0446f7160009fb45"
)
GOLDEN_INSTANCE_ID = "a54c274af5b200faf28cff7f3cbbfe56201fe499690c9adf3dc0558a55c4bbc5"
GOLDEN_INSTANCE_ID_NO_PART = (
    "9de127dfbe91c0bf7abcc31f840f193f86003eb3d5143d46b65a5892da46ef83"
)
GOLDEN_TREE_SHA256 = "cd14807f3f30138087008e987ef3c9e7c0dab82ac70c73cec420b7c71f0669ce"


def _doc(**overrides) -> dict:
    """A minimal valid solid document over the contract's example variables."""
    tree = "0" * 64
    vs = variables_sha256(CONTRACT_VARIABLES)
    doc = {
        "format": FORMAT,
        "format_version": "1.0.0",
        "kind": "solid",
        "generator": {
            "platform": "yantra4d",
            "cartridge": "demo",
            "mode": "m",
            "part": "p",
            "engine": "cadquery",
            "source": {"tree_sha256": tree, "tree_algorithm": TREE_ALGORITHM},
        },
        "variables": copy.deepcopy(CONTRACT_VARIABLES),
        "variables_sha256": vs,
        "complete": False,
        "geometry": [
            {"path": "p.stl", "media_type": "model/stl", "sha256": "a" * 64, "bytes": 3}
        ],
        "instance_id": instance_id(
            cartridge="demo", mode="m", part="p", tree_sha256=tree, variables_sha256=vs
        ),
    }
    doc.update(overrides)
    return doc


def _codes(result) -> set[str]:
    return {f.code for f in result.findings}


def _error_codes(result) -> set[str]:
    return {f.code for f in result.errors}


# ── the schema ───────────────────────────────────────────────────────────────
def test_the_schema_is_bundled_and_exported():
    assert "generator-output" in hs.list_schemas()
    assert hs.SCHEMAS["generator-output"] == "hyperobjects-spec"
    schema = hs.load("generator-output")
    assert schema["$id"] == "https://madfam.io/schemas/generator-output.schema.json"
    assert schema["properties"]["format"]["const"] == FORMAT


def test_the_schema_id_follows_the_sibling_convention():
    """Schemas authored here live under madfam.io/schemas — GOC-1 §2 already used it."""
    for name, repo in hs.SCHEMAS.items():
        if repo == "hyperobjects-spec":
            assert hs.load(name)["$id"] == f"https://madfam.io/schemas/{name}.schema.json"


def test_a_minimal_document_is_schema_valid():
    assert not [f for f in check_generator_output(_doc()).findings if f.code == "schema"]


@pytest.mark.parametrize("ident", ["target_material", "mat_shrinkage_x", "infill",
                                   "layer_height", "nozzle_diameter", "thermo_k",
                                   "slicer_profile_x", "printer_bed", "filament_type",
                                   "mat_clear_xy"])
def test_physical_ids_are_denied(ident):
    doc = _doc()
    doc["variables"] = [{"id": ident, "value": 1, "type": "number", "source": "request"}]
    doc["variables_sha256"] = variables_sha256(doc["variables"])
    result = check_generator_output(doc)
    assert "schema" in _error_codes(result), ident


@pytest.mark.parametrize("ident", ["mat_thick", "mat_width", "mat_length", "nozzle_bore",
                                   "material_thickness", "clearance", "wall"])
def test_geometric_ids_that_look_physical_are_allowed(ident):
    """The bare `mat_` prefix is deliberately NOT denied (boxjoint-jig, corner-clamp,
    framing-hyperobject, sweater-storage-roll use mat_thick/mat_width as geometry)."""
    doc = _doc()
    doc["variables"] = [{"id": ident, "value": 1, "type": "number", "source": "request"}]
    doc["variables_sha256"] = variables_sha256(doc["variables"])
    doc["instance_id"] = instance_id(
        cartridge="demo", mode="m", part="p", tree_sha256="0" * 64,
        variables_sha256=doc["variables_sha256"],
    )
    doc["complete"] = True
    assert check_generator_output(doc).ok, ident


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("instance_id"),
        lambda d: d.update(format="hyperobjects.something-else"),
        lambda d: d.update(format_version="2.0.0"),
        lambda d: d.update(kind="liquid"),
        lambda d: d.update(geometry=[]),
        lambda d: d.update(extra_key=1),
        lambda d: d["generator"].update(engine="blender"),
        lambda d: d["generator"].update(cartridge="Bad Slug"),
        lambda d: d["generator"]["source"].update(tree_algorithm="tree-v2"),
        lambda d: d["generator"].update(commons={"repo": "elsewhere"}),
        lambda d: d["geometry"][0].update(units="in"),
        lambda d: d["geometry"][0].update(sha256="XYZ"),
        lambda d: d.update(legacy_physical_inputs={"mat_shrinkage_x": [1]}),
    ],
)
def test_schema_rejects(mutate):
    doc = _doc()
    mutate(doc)
    assert "schema" in _error_codes(check_generator_output(doc))


def test_source_default_must_carry_null_and_others_must_not():
    doc = _doc()
    doc["variables"][2]["value"] = 4  # wall: source_default with a guessed value
    assert "schema" in _error_codes(check_generator_output(doc))
    doc = _doc()
    doc["variables"][0]["value"] = None  # clearance: request with no value
    assert "schema" in _error_codes(check_generator_output(doc))


def test_a_preset_variable_requires_its_preset_id():
    doc = _doc()
    doc["variables"][0]["source"] = "preset"
    assert "schema" in _error_codes(check_generator_output(doc))
    doc["variables"][0]["preset_id"] = "compact"
    assert "schema" not in _error_codes(check_generator_output(doc))


# ── golden vectors (§3) ──────────────────────────────────────────────────────
def test_canonical_json_matches_the_contract_example_bytes():
    pairs = [[v["id"], v["value"]] for v in CONTRACT_VARIABLES]
    assert canonical_json(pairs) == b'[["clearance",0.3],["mode_flag",true],["wall",null]]'
    assert canonical_json({"b": 1, "a": "é"}) == '{"a":"é","b":1}'.encode()


def test_canonical_json_refuses_nan():
    with pytest.raises(ValueError):
        canonical_json([["x", float("nan")]])


def test_golden_variables_sha256():
    assert variables_sha256(CONTRACT_VARIABLES) == GOLDEN_CONTRACT_VARIABLES_SHA256
    # The digest is of the sorted pairs: input order and provenance do not matter …
    shuffled = [CONTRACT_VARIABLES[2], CONTRACT_VARIABLES[0], CONTRACT_VARIABLES[1]]
    assert variables_sha256(shuffled) == GOLDEN_CONTRACT_VARIABLES_SHA256
    as_map = {"wall": None, "clearance": 0.3, "mode_flag": True}
    assert variables_sha256(as_map) == GOLDEN_CONTRACT_VARIABLES_SHA256
    # … and it is the sha256 of exactly the contract's example hash input.
    expected = hashlib.sha256(
        b'[["clearance",0.3],["mode_flag",true],["wall",null]]'
    ).hexdigest()
    assert expected == GOLDEN_CONTRACT_VARIABLES_SHA256


def test_variables_sha256_is_bytewise_sorted_not_case_folded():
    # "B" (0x42) sorts before "a" (0x61) bytewise.
    assert variables_sha256({"a": 2, "B": 1}) == hashlib.sha256(
        b'[["B",1],["a",2]]'
    ).hexdigest()


def test_integral_floats_hash_as_ints():
    """GOC-1 v1.0.1 §3.1: a platform holding a slider as 12.0 and one holding it as 12
    must produce the same identity (and match ECMAScript serialisation)."""
    assert variables_sha256({"w": 12.0}) == variables_sha256({"w": 12})
    assert canonical_json([["w", 12.0]]) == canonical_json([["w", 12]]) == b'[["w",12]]'
    assert variables_sha256({"w": 12}) == hashlib.sha256(b'[["w",12]]').hexdigest()
    doc_float = [{"id": "w", "value": 12.0, "type": "number", "source": "request"}]
    doc_int = [{"id": "w", "value": 12, "type": "number", "source": "request"}]
    assert variables_sha256(doc_float) == variables_sha256(doc_int)


@pytest.mark.parametrize(
    "value, expected",
    [
        (12.0, 12),
        (-0.0, 0),
        (-3.0, -3),
        (0.5, 0.5),
        (2.0**53 - 1, 2**53 - 1),
        (2.0**53, 2.0**53),  # at the limit: left a float
        (-(2.0**53), -(2.0**53)),
        (True, True),  # a bool is not a number here
        (7, 7),
        ("12.0", "12.0"),  # strings are never touched
        ({"a": [1.0, {"b": 2.0}]}, {"a": [1, {"b": 2}]}),
    ],
)
def test_normalize_numbers(value, expected):
    out = normalize_numbers(value)
    assert out == expected
    assert type(out) is type(expected)
    if isinstance(expected, dict):
        assert type(out["a"][0]) is int and type(out["a"][1]["b"]) is int


def test_the_checker_accepts_either_spelling_of_an_integral_value():
    doc = _doc()
    doc["variables"][0]["value"] = 3  # clearance
    doc["variables_sha256"] = variables_sha256(doc["variables"])
    doc["instance_id"] = instance_id(
        cartridge="demo", mode="m", part="p", tree_sha256="0" * 64,
        variables_sha256=doc["variables_sha256"],
    )
    assert check_generator_output(doc).ok
    doc["variables"][0]["value"] = 3.0  # same value, float spelling: same digest
    assert check_generator_output(doc).ok


def test_the_checker_does_not_scope_variables_to_the_mode():
    """GOC-1 v1.0.1 §4.1: every declared parameter is listed, whatever its UI scope.
    The document carries no manifest, and nothing here may flag an out-of-mode id."""
    doc = _doc()
    doc["variables"].append(
        {"id": "zz_other_mode_param", "value": 1, "type": "number", "source": "request"}
    )
    doc["variables_sha256"] = variables_sha256(doc["variables"])
    doc["instance_id"] = instance_id(
        cartridge="demo", mode="m", part="p", tree_sha256="0" * 64,
        variables_sha256=doc["variables_sha256"],
    )
    assert check_generator_output(doc).ok


def test_golden_instance_id():
    kwargs = dict(cartridge="demo", mode="m", tree_sha256="0" * 64,
                  variables_sha256=GOLDEN_CONTRACT_VARIABLES_SHA256)
    assert instance_id(part="p", **kwargs) == GOLDEN_INSTANCE_ID
    assert instance_id(part=None, **kwargs) == GOLDEN_INSTANCE_ID_NO_PART
    expected = hashlib.sha256(
        json.dumps(
            {"cartridge": "demo", "mode": "m", "part": "p", "tree_sha256": "0" * 64,
             "variables_sha256": GOLDEN_CONTRACT_VARIABLES_SHA256},
            sort_keys=True, separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert expected == GOLDEN_INSTANCE_ID


def _golden_tree(root: Path) -> None:
    """The tree-v1 golden input. Every excluded path is present so the vector proves
    the exclusions, not merely the happy path."""
    (root / "sub" / "docs").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "__pycache__").mkdir()
    (root / "node_modules" / "x").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "project.json").write_bytes(b'{"project":{"slug":"demo"}}\n')
    (root / "main.py").write_bytes(b"result = None\n")
    (root / "sub" / "part.scad").write_bytes(b"cube(1);\n")
    (root / "sub" / "docs" / "kept.json").write_bytes(b"{}\n")  # only ROOT docs/ is out
    (root / "LICENSE").write_bytes(b"CERN-OHL-W-2.0\n")
    (root / "README.md").write_bytes(b"# demo\n")
    (root / "notes.TXT").write_bytes(b"upper-case suffix\n")
    (root / "thumb.PNG").write_bytes(b"\x89PNG")
    (root / "docs" / "spec.json").write_bytes(b"{}\n")
    (root / "__pycache__" / "main.cpython-313.pyc").write_bytes(b"\x00")
    (root / "node_modules" / "x" / "index.js").write_bytes(b"0\n")
    (root / ".git" / "HEAD").write_bytes(b"ref: refs/heads/main\n")


GOLDEN_TREE_FILES = {
    "LICENSE": b"CERN-OHL-W-2.0\n",
    "main.py": b"result = None\n",
    "project.json": b'{"project":{"slug":"demo"}}\n',
    "sub/docs/kept.json": b"{}\n",
    "sub/part.scad": b"cube(1);\n",
}


def test_golden_tree_sha256(tmp_path):
    _golden_tree(tmp_path)
    manifest = "".join(
        f"{hashlib.sha256(GOLDEN_TREE_FILES[p]).hexdigest()}  {p}\n"
        for p in sorted(GOLDEN_TREE_FILES, key=lambda s: s.encode())
    )
    expected = hashlib.sha256(manifest.encode()).hexdigest()
    assert tree_sha256(tmp_path) == expected
    assert expected == GOLDEN_TREE_SHA256


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks on this platform")
def test_tree_follows_file_symlinks_never_directory_symlinks(tmp_path):
    root = tmp_path / "cart"
    root.mkdir()
    (root / "main.py").write_bytes(b"x\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "lib.scad").write_bytes(b"cube(2);\n")
    base = tree_sha256(root)
    os.symlink(outside, root / "linked_dir")  # a directory symlink contributes nothing
    assert tree_sha256(root) == base
    os.symlink(outside / "lib.scad", root / "lib.scad")  # a file symlink is read through
    with_file = tree_sha256(root)
    assert with_file != base
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "main.py").write_bytes(b"x\n")
    (plain / "lib.scad").write_bytes(b"cube(2);\n")
    assert tree_sha256(plain) == with_file


def test_tree_sha256_refuses_a_file(tmp_path):
    (tmp_path / "f").write_text("x")
    with pytest.raises(NotADirectoryError):
        tree_sha256(tmp_path / "f")


# ── the checker ──────────────────────────────────────────────────────────────
def test_the_fixture_is_a_clean_instance():
    result = check_generator_output_file(FIXTURE_DOC)
    assert result.ok and not result.findings, [str(f) for f in result.findings]
    assert result.instance_id == json.loads(FIXTURE_DOC.read_text())["instance_id"]


def test_incomplete_is_a_warning_not_an_error():
    result = check_generator_output(_doc())
    assert result.ok
    assert "incomplete" in {f.code for f in result.warnings}


def test_complete_must_agree_with_the_variables():
    result = check_generator_output(_doc(complete=True))
    assert "complete" in _error_codes(result)


def test_legacy_physical_inputs_warn():
    result = check_generator_output(_doc(legacy_physical_inputs={"target_material": "pla"}))
    assert result.ok
    assert "legacy-physical-inputs" in {f.code for f in result.warnings}


def test_a_wrong_variables_sha256_is_an_error():
    result = check_generator_output(_doc(variables_sha256="1" * 64))
    assert "variables_sha256" in _error_codes(result)


def test_a_changed_value_is_caught_by_the_digest():
    doc = _doc()
    doc["variables"][0]["value"] = 0.4
    assert "variables_sha256" in _error_codes(check_generator_output(doc))


def test_provenance_changes_do_not_move_the_digest():
    doc = _doc()
    doc["variables"][0].update(source="preset", preset_id="tight", unit="mm")
    assert check_generator_output(doc).ok


def test_a_wrong_instance_id_is_an_independent_error():
    result = check_generator_output(_doc(instance_id="2" * 64))
    assert _error_codes(result) == {"instance_id"}


def test_unsorted_and_duplicate_variables_are_errors():
    doc = _doc()
    doc["variables"].reverse()
    assert "variables-order" in _error_codes(check_generator_output(doc))
    doc = _doc()
    doc["variables"].insert(1, copy.deepcopy(doc["variables"][0]))
    assert "variables-duplicate" in _error_codes(check_generator_output(doc))


def test_a_nan_value_is_an_error_not_a_crash():
    doc = _doc()
    doc["variables"][0]["value"] = float("nan")
    result = check_generator_output(doc)
    assert not result.ok
    assert "variables_sha256" in _error_codes(result)


def test_geometry_is_rehashed_under_base_dir(tmp_path):
    data = b"abc"
    (tmp_path / "p.stl").write_bytes(data)
    doc = _doc()
    doc["geometry"][0].update(sha256=hashlib.sha256(data).hexdigest(), bytes=3)
    assert check_generator_output(doc, base_dir=tmp_path).ok
    doc["geometry"][0]["bytes"] = 4
    assert "geometry-bytes" in _error_codes(check_generator_output(doc, base_dir=tmp_path))
    doc["geometry"][0].update(bytes=3, sha256="b" * 64)
    assert "geometry-sha256" in _error_codes(check_generator_output(doc, base_dir=tmp_path))


def test_geometry_is_not_read_without_base_dir():
    assert "geometry-missing" not in _codes(check_generator_output(_doc()))


def test_missing_geometry_is_a_warning(tmp_path):
    result = check_generator_output(_doc(), base_dir=tmp_path)
    assert result.ok
    assert "geometry-missing" in {f.code for f in result.warnings}


@pytest.mark.parametrize("path", ["../p.stl", "/etc/passwd", "a\\b.stl"])
def test_geometry_paths_may_not_escape(tmp_path, path):
    doc = _doc()
    doc["geometry"][0]["path"] = path
    assert "geometry-path" in _error_codes(check_generator_output(doc, base_dir=tmp_path))


def test_a_non_object_is_a_schema_error():
    result = check_generator_output([1, 2])
    assert not result.ok and _error_codes(result) == {"schema"}


def test_collect_expands_directories(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.variables.json").write_text("{}")
    (tmp_path / "a" / "variables.json").write_text("{}")
    (tmp_path / "a" / "other.json").write_text("{}")
    found = collect_generator_output_files([tmp_path, tmp_path / "a" / "variables.json"])
    assert [p.name for p in found] == ["variables.json", "x.variables.json"]


# ── the CLIs ─────────────────────────────────────────────────────────────────
def test_y4d_bundle_check_passes_the_fixture_directory(capsys):
    from y4d_spec.cli import main

    assert main(["bundle", "check", str(FIXTURE.parent)]) == 0
    out = capsys.readouterr().out
    assert "  ok " in out
    assert out.strip().splitlines()[-1] == (
        "y4d-spec bundle check: files=1 failures=0 warnings=0"
    )


def test_y4d_bundle_check_exits_zero_on_warnings_and_one_on_errors(tmp_path, capsys):
    from y4d_spec.cli import main

    warn = tmp_path / "w.variables.json"
    warn.write_text(json.dumps(_doc()))  # complete:false + p.stl missing
    assert main(["bundle", "check", str(warn)]) == 0
    out = capsys.readouterr().out
    assert "  warn " in out and "warnings=2" in out

    bad = tmp_path / "b.variables.json"
    bad.write_text(json.dumps(_doc(instance_id="3" * 64)))
    assert main(["bundle", "check", str(bad)]) == 1
    assert "  FAIL " in capsys.readouterr().out

    broken = tmp_path / "c.variables.json"
    broken.write_text("{not json")
    assert main(["bundle", "check", str(broken)]) == 1


def test_y4d_bundle_check_refuses_to_check_nothing(tmp_path, capsys):
    from y4d_spec.cli import main

    assert main(["bundle", "check", str(tmp_path)]) == 2
    assert main(["bundle", "check", str(tmp_path / "nope.json")]) == 2


def test_fc_spec_check_generator_output(tmp_path, capsys):
    from fc_spec.cli import main

    assert main(["check", "generator-output", str(FIXTURE_DOC)]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == (
        "fc-spec check: contract=generator-output files=1 failures=0 warnings=0"
    )
    bad = tmp_path / "variables.json"
    bad.write_text(json.dumps(_doc(variables_sha256="4" * 64)))
    assert main(["check", "generator-output", str(tmp_path)]) == 1


def test_fc_conformance_check_reports_errors_and_warnings_apart():
    from fc_spec import conformance

    res = conformance.check("generator-output", _doc())
    assert res.ok and res.warnings and not res.problems
    res = conformance.check("generator-output", _doc(instance_id="5" * 64))
    assert not res.ok and any(p.startswith("instance_id") for p in res.problems)
