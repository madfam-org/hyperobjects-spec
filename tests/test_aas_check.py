"""``aas check``: the vendored schema, the dispatch view, the MADFAM rules, BaSyx."""

from __future__ import annotations

import copy
import hashlib
import json
from importlib import resources

import pytest

from aas_support import SEM1_SOFT, SEM1_SOLID, Y4D_MATERIAL, child, submodel
from hyperobjects_aas import (
    build_material_environment,
    build_soft_environment,
    build_solid_environment,
    check_environment,
)
from hyperobjects_aas.check import (
    _validator,
    aas_schema,
    basyx_available,
    dispatch_view,
    reference_validator,
    vendored_schema_digest,
)
from hyperobjects_aas.elements import external_ref
from hyperobjects_aas.templates import IDTA


def _codes(result) -> set[str]:
    return {f.code for f in result.errors}


@pytest.fixture(scope="module")
def solid_env():
    return build_solid_environment(SEM1_SOLID)


def test_vendored_schema_matches_its_lock():
    schemas = resources.files("hyperobjects_aas.schemas")
    lock = json.loads(schemas.joinpath("aas.lock.json").read_text(encoding="utf-8"))
    data = schemas.joinpath("aas.json").read_bytes()
    assert vendored_schema_digest() == lock["sha256"] == hashlib.sha256(data).hexdigest()
    assert len(data) == lock["bytes"]
    assert lock["tag"] == "v3.1.2" and lock["license"] == "CC-BY-4.0"
    git_blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    assert git_blob == lock["git_blob_sha1"]
    assert aas_schema()["$id"] == "https://admin-shell.io/aas/3/1"
    for name in ("VENDORED.md", "LICENSE-CC-BY-4.0.txt"):
        assert schemas.joinpath(name).is_file()


def test_dispatch_view_rewrites_only_the_choice_unions():
    view, original = dispatch_view(aas_schema()), aas_schema()
    changed = {k for k in original["definitions"]
               if original["definitions"][k] != view["definitions"][k]}
    assert changed == {"SubmodelElement_choice", "DataElement_choice",
                       "RelationshipElement_choice", "DataSpecificationContent_choice"}
    assert "oneOf" in original["definitions"]["SubmodelElement_choice"]  # source untouched


def _small_env():
    """Small enough for the (slow) reference validator: a material shell without the
    deep CardData mirror."""
    env = build_material_environment(Y4D_MATERIAL)
    env["submodels"][0]["submodelElements"] = env["submodels"][0]["submodelElements"][:2]
    return env


@pytest.mark.parametrize("mutate", [
    lambda e: None,
    lambda e: e["submodels"][0]["submodelElements"][0].__setitem__("modelType", "Bogus"),
    lambda e: e["submodels"][0]["submodelElements"][0].pop("modelType"),
    lambda e: e["submodels"][0]["submodelElements"][0]["value"][0].__setitem__(
        "valueType", "xs:nonsense"),
    lambda e: e["submodels"][0]["submodelElements"][0].__setitem__("idShort", "9lives"),
    lambda e: e["submodels"][0]["submodelElements"].append("not an element"),
    lambda e: e["conceptDescriptions"][0]["embeddedDataSpecifications"][0][
        "dataSpecificationContent"].__setitem__("modelType", "Nope"),
    lambda e: e["assetAdministrationShells"][0]["administration"].__setitem__("version", "1.2")
    if "administration" in e["assetAdministrationShells"][0] else
    e["assetAdministrationShells"][0].__setitem__("administration", {"version": "1.2"}),
])
def test_dispatch_view_agrees_with_the_published_schema(mutate):
    env = _small_env()
    mutate(env)
    fast = not list(_validator().iter_errors(env))
    slow = not list(reference_validator().iter_errors(env))
    assert fast == slow


def test_projected_environments_pass_every_layer(solid_env):
    for env in (solid_env, build_soft_environment(SEM1_SOFT),
                build_material_environment(Y4D_MATERIAL)):
        result = check_environment(env, basyx="off")
        assert result.ok, [str(f) for f in result.errors]
        assert result.basyx == "skipped"


def test_id_scheme_violations_are_errors(solid_env):
    env = copy.deepcopy(solid_env)
    env["assetAdministrationShells"][0]["id"] = "https://example.com/aas/1"
    assert "id-scheme" in _codes(check_environment(env, basyx="off"))
    env = copy.deepcopy(solid_env)
    env["submodels"][0]["id"] = env["submodels"][0]["id"].replace("/Nameplate", "/Other")
    codes = _codes(check_environment(env, basyx="off"))
    assert {"id-scheme", "dangling", "orphan"} <= codes
    env = copy.deepcopy(solid_env)
    specific = env["assetAdministrationShells"][0]["assetInformation"]["specificAssetIds"]
    specific[2]["value"] = "f" * 64
    assert "id-scheme" in _codes(check_environment(env, basyx="off"))
    env = copy.deepcopy(solid_env)
    env["assetAdministrationShells"][0]["assetInformation"]["globalAssetId"] = (
        "https://id.madfam.io/asset/solid/someone-else")
    assert "id-scheme" in _codes(check_environment(env, basyx="off"))


def test_id_short_rules_the_schema_cannot_express(solid_env):
    env = copy.deepcopy(solid_env)
    params = child(submodel(env, "ParametricModel"), "Parameters")
    params["value"][1]["idShort"] = params["value"][0]["idShort"]
    assert "AASd-022" in _codes(check_environment(env, basyx="off"))
    env = copy.deepcopy(solid_env)
    constraints = child(submodel(env, "ParametricModel"), "Constraints")
    constraints["value"][0]["idShort"] = "Named"
    assert "AASd-120" in _codes(check_environment(env, basyx="off"))
    env = copy.deepcopy(solid_env)
    del child(submodel(env, "Nameplate"), "Author")["idShort"]
    assert "idShort" in _codes(check_environment(env, basyx="off"))


def test_conformance_claim_rule(solid_env):
    env = copy.deepcopy(solid_env)
    # Over-claim: the nameplate lacks AddressInformation and OrderCodeOfManufacturer.
    submodel(env, "Nameplate")["semanticId"] = external_ref(
        IDTA["nameplate"].submodel_semantic_id)
    result = check_environment(env, basyx="off")
    claim = [f for f in result.errors if f.code == "conformance-claim"]
    assert claim and "AddressInformation" in claim[0].message
    env = copy.deepcopy(solid_env)
    submodel(env, "Nameplate")["semanticId"] = external_ref("https://example.com/made-up/1/0")
    assert "conformance-claim" in _codes(check_environment(env, basyx="off"))
    env = copy.deepcopy(solid_env)   # a genuine claim stays valid
    assert check_environment(env, basyx="off").ok


def test_madfam_semantic_ids_need_concept_descriptions(solid_env):
    env = copy.deepcopy(solid_env)
    env["conceptDescriptions"] = [cd for cd in env["conceptDescriptions"]
                                  if not cd["id"].endswith("/concept/parameter")]
    assert "concept" in _codes(check_environment(env, basyx="off"))


def test_basyx_states_are_honest(solid_env, monkeypatch):
    import hyperobjects_aas.check as check

    monkeypatch.setattr(check, "basyx_available", lambda: False)
    auto = check.check_environment(solid_env)
    assert auto.ok and auto.basyx == "not installed"
    required = check.check_environment(solid_env, basyx="require")
    assert not required.ok and "basyx" in _codes(required)


basyx_required = pytest.mark.skipif(
    not basyx_available(),
    reason='needs the aas-verify extra: pip install "hyperobjects-spec[aas-verify]"',
)


@basyx_required
def test_projected_environments_round_trip_through_basyx(solid_env):
    for env in (solid_env, build_soft_environment(SEM1_SOFT),
                build_material_environment(Y4D_MATERIAL)):
        result = check_environment(env, basyx="require")
        assert result.ok, [str(f) for f in result.errors]
        assert result.basyx == "verified"


@basyx_required
def test_basyx_rejects_what_the_schema_accepts(solid_env):
    """AASd-117 is not in aas.json; BaSyx enforces it — so the layer is not redundant."""
    from hyperobjects_aas.check import basyx_roundtrip

    env = copy.deepcopy(solid_env)
    bom = submodel(env, "BillOfMaterials")
    relation = next(s for s in child(bom, "EntryNode")["statements"]
                    if s["modelType"] == "RelationshipElement")
    del relation["idShort"]
    assert not list(_validator().iter_errors(env))
    assert basyx_roundtrip(env)
