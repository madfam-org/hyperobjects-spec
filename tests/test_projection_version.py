"""The projection version in every shell and submodel id (SEM-1 §1, owner decision
2026-10-04), and the drift guard that makes a projection change bump it.

The goldens (``scripts/refresh_assembly_golden.py``) are one of every kind of shell the
projection mints: assemblies A and B, their nine solid cartridges, a soft garment and a
material card. Each records the version it was made with, in its ids and in the shell's
``ProjectionVersion`` extension.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from hyperobjects_aas import (
    PROJECTION_VERSION,
    build_material_environment,
    build_solid_environment,
    check_environment,
    ids,
)
from hyperobjects_aas.assembly import build_assembly_environment, component_type_shells
from hyperobjects_aas.drift import identifiables, immutable_drift
from hyperobjects_aas.resolver import EnvironmentCartridgeResolver, bundled_standard_parts_dir
from hyperobjects_schemas.generator_output import canonical_json
from y4d_spec.assembly import CompositeResolver, StandardPartsResolver, validate_assembly

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "refresh_assembly_golden", REPO / "scripts" / "refresh_assembly_golden.py")
refresh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refresh)

TARGETS = refresh.targets()
MATERIAL = REPO / "tests" / "fixtures" / "aas" / "bambu-tpu-95a.material.json"
A = "voron-2-4-class-350-motion-frame"


def _name(target) -> str:
    return str(target[0].relative_to(REPO))


def test_the_goldens_cover_every_kind_of_shell():
    kinds = set()
    for path, _builder in TARGETS:
        shell = json.loads(path.read_bytes())["assetAdministrationShells"][0]
        kinds.add(ids.parse_shell_id(shell["id"]).kind)
    assert kinds == {"solid", "soft", "assembly", "material"}
    # A and B, the 14 cartridges they use (A: the 2.4-class motion system), a soft garment
    # and a material card.
    assert len(TARGETS) == 18


@pytest.mark.parametrize("target", TARGETS, ids=_name)
def test_golden_is_byte_identical_to_the_projection(target):
    path, builder = target
    fresh = canonical_json(builder())
    if path.read_bytes() == fresh:
        return
    frozen = immutable_drift(json.loads(path.read_bytes()), json.loads(fresh))
    assert not frozen, (
        f"the projection changed the bytes under ids it already minted ({frozen[:3]}…): bump "
        f"hyperobjects_aas.ids.PROJECTION_VERSION (now {PROJECTION_VERSION}), then run "
        "scripts/refresh_assembly_golden.py")
    pytest.fail("the golden moved (an input, the lexicon or the version changed): run "
                "scripts/refresh_assembly_golden.py and review the diff")


@pytest.mark.parametrize("target", TARGETS, ids=_name)
def test_golden_records_the_version_it_was_made_with(target):
    env = json.loads(target[0].read_bytes())
    (shell,) = env["assetAdministrationShells"]
    parts = ids.parse_shell_id(shell["id"])
    assert parts is not None and parts.version == PROJECTION_VERSION
    assert ids.shell_projection_version(shell) == PROJECTION_VERSION
    for sm in env["submodels"]:
        assert sm["id"] == parts.submodel_prefix + sm["idShort"]
    result = check_environment(env, basyx="off")
    assert result.ok, [str(f) for f in result.errors]


# ── the guard itself ──────────────────────────────────────────────────────────
def test_changed_bytes_under_a_minted_id_are_immutable_drift():
    env = build_material_environment(MATERIAL)
    moved = copy.deepcopy(env)
    moved["submodels"][0]["submodelElements"][0]["idShort"] = "Renamed"
    assert immutable_drift(env, moved) == [env["submodels"][0]["id"]]
    shell_only = copy.deepcopy(env)
    shell_only["assetAdministrationShells"][0]["idShort"] = "Other"
    assert immutable_drift(env, shell_only) == [env["assetAdministrationShells"][0]["id"]]


def test_concept_description_changes_are_not_immutable_drift():
    """The store updates ConceptDescriptions in place (they follow the lexicon)."""
    env = build_material_environment(MATERIAL)
    edited = copy.deepcopy(env)
    edited["conceptDescriptions"][0]["idShort"] = "EditedText"
    assert immutable_drift(env, edited) == []
    assert set(identifiables(env)) == {
        env["assetAdministrationShells"][0]["id"], env["submodels"][0]["id"]}


def test_a_bumped_version_mints_new_ids_and_passes_the_guard(monkeypatch):
    before = build_material_environment(MATERIAL)
    monkeypatch.setattr(ids, "PROJECTION_VERSION", PROJECTION_VERSION + 1)
    after = build_material_environment(MATERIAL)
    assert not set(identifiables(before)) & set(identifiables(after))
    assert immutable_drift(before, after) == []
    shell = after["assetAdministrationShells"][0]
    assert shell["id"].endswith(f"/p{PROJECTION_VERSION + 1}")
    assert ids.shell_projection_version(shell) == PROJECTION_VERSION + 1
    assert check_environment(after, basyx="off").ok


def test_the_refresh_refuses_immutable_drift_and_writes_moved_ids(tmp_path, capsys, monkeypatch):
    env = build_material_environment(MATERIAL)
    golden = tmp_path / "card.aas.json"
    stale = copy.deepcopy(env)
    stale["submodels"][0]["submodelElements"][0]["idShort"] = "Renamed"
    golden.write_bytes(canonical_json(stale))
    target = [(golden, lambda: build_material_environment(MATERIAL))]
    # Same ids, different bytes: refused in BOTH modes, the file untouched.
    assert refresh.main([], goldens=target) == 1
    assert refresh.main(["--check"], goldens=target) == 1
    assert golden.read_bytes() == canonical_json(stale)
    assert "Bump hyperobjects_aas.ids.PROJECTION_VERSION" in capsys.readouterr().out
    # After the bump the ids move: --check reports drift, a refresh writes it.
    monkeypatch.setattr(ids, "PROJECTION_VERSION", PROJECTION_VERSION + 1)
    assert refresh.main(["--check"], goldens=target) == 1
    assert refresh.main([], goldens=target) == 0
    assert refresh.main(["--check"], goldens=target) == 0
    assert "immutable_drift=0" in capsys.readouterr().out


def test_check_fails_a_shell_whose_extension_and_id_disagree():
    env = build_material_environment(MATERIAL)
    env["assetAdministrationShells"][0]["extensions"][0]["value"] = "9"
    codes = {f.code for f in check_environment(env, basyx="off").errors}
    assert "projection-version" in codes
    del env["assetAdministrationShells"][0]["extensions"]
    assert "projection-version" in {f.code for f in check_environment(env, basyx="off").errors}


def test_check_fails_a_submodel_of_another_version():
    env = build_material_environment(MATERIAL)
    sm = env["submodels"][0]
    other = sm["id"].replace(f"/p{PROJECTION_VERSION}/", f"/p{PROJECTION_VERSION + 1}/")
    sm["id"] = other
    env["assetAdministrationShells"][0]["submodels"][0]["keys"][0]["value"] = other
    assert "id-scheme" in {f.code for f in check_environment(env, basyx="off").errors}


def test_check_fails_an_unversioned_shell_id():
    env = build_material_environment(MATERIAL)
    shell = env["assetAdministrationShells"][0]
    shell["id"] = shell["id"].rsplit("/", 1)[0]
    assert "id-scheme" in {f.code for f in check_environment(env, basyx="off").errors}


# ── the BoM under a bumped version ────────────────────────────────────────────
def test_bom_derived_from_names_type_shells_of_the_same_version(monkeypatch):
    """At any version, DerivedFrom names the type shells of THAT version, the resolver
    parses them, and the assembly digest (a function of the document and the components'
    identities, not of the projection) does not move."""
    commons = refresh.COMMONS
    doc = json.loads((commons / "assemblies" / A / "assembly.json").read_text("utf-8"))
    digest = validate_assembly(
        doc, CompositeResolver.for_directories(commons, bundled_standard_parts_dir())).digest
    bumped = PROJECTION_VERSION + 1
    monkeypatch.setattr(ids, "PROJECTION_VERSION", bumped)
    store = {}
    for directory in refresh.cartridges():
        env = build_solid_environment(directory)
        store[env["assetAdministrationShells"][0]["id"]] = env
    report = validate_assembly(doc, CompositeResolver.for_directories(
        commons, bundled_standard_parts_dir()))
    env = build_assembly_environment(doc, report)
    shells = component_type_shells(env)
    assert shells and all(ids.parse_shell_id(s).version == bumped for s in shells.values())
    assert set(shells.values()) <= set(store)

    def fetch(shell_id):
        found = store.get(shell_id)
        if found is None:
            return None
        return found["assetAdministrationShells"][0], {s["idShort"]: s for s in found["submodels"]}

    again = validate_assembly(doc, CompositeResolver(
        cartridge=EnvironmentCartridgeResolver(shells, fetch),
        standard=StandardPartsResolver(bundled_standard_parts_dir())))
    assert again.ok and again.digest == report.digest == digest
    assert canonical_json(build_assembly_environment(doc, again)) == canonical_json(env)
