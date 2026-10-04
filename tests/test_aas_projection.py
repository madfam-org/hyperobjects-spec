"""The SEM-1 §5 projection: mapping, both shapes of every manifest, determinism."""

from __future__ import annotations

import json

from aas_support import (
    FC_MATERIAL,
    FIXTURES,
    SEM1_SOFT,
    SEM1_SOLID,
    THIMBLE,
    Y4D_MATERIAL,
    cartridge_from_json,
    child,
    has_child,
    semantic,
    strip_sem1,
    submodel,
    walk,
)
from hyperobjects_aas import (
    build_material_environment,
    build_soft_environment,
    build_solid_environment,
    check_environment,
    project_material,
    project_solid,
)
from hyperobjects_aas.templates import IDTA, MADFAM
from hyperobjects_schemas.generator_output import canonical_json, tree_sha256

SOLID_SUBMODELS = ["Nameplate", "ParametricModel", "GeometryProvision", "RequirementProfile",
                   "MatingInterfaces", "BillOfMaterials"]
SOFT_SUBMODELS = ["Nameplate", "ParametricModel", "PatternProvision", "RequirementProfile",
                  "SeamInterfaces", "Fabrics", "HardwareLinks"]


def _ok(env):
    result = check_environment(env, basyx="off")
    assert result.ok, [str(f) for f in result.errors]


def test_solid_shell_header_follows_sem1():
    env = build_solid_environment(SEM1_SOLID)
    _ok(env)
    (shell,) = env["assetAdministrationShells"]
    tree = tree_sha256(SEM1_SOLID)
    assert shell["id"] == f"https://id.madfam.io/aas/solid/sem1-bracket/{tree[:16]}"
    assert shell["idShort"] == "sem1-bracket"
    assert shell["administration"] == {"version": "2", "revision": "3"}
    info = shell["assetInformation"]
    assert info["assetKind"] == "Type"
    assert info["globalAssetId"] == "https://id.madfam.io/asset/solid/sem1-bracket"
    assert info["specificAssetIds"] == [
        {"name": "commons", "value": "solid-hyperobjects"},
        {"name": "slug", "value": "sem1-bracket"},
        {"name": "tree_sha256", "value": tree},
    ]
    assert "derivedFrom" not in shell
    assert [sm["idShort"] for sm in env["submodels"]] == SOLID_SUBMODELS
    assert [r["keys"][0]["value"] for r in shell["submodels"]] == [
        sm["id"] for sm in env["submodels"]]


def test_full_semver_goes_in_manifest_version():
    env = build_solid_environment(SEM1_SOLID)
    assert child(submodel(env, "Nameplate"), "ManifestVersion")["value"] == "2.3.4"


def test_parametric_model_maps_every_parameter():
    pm = submodel(build_solid_environment(SEM1_SOLID), "ParametricModel")
    params = child(pm, "Parameters")
    assert [p["idShort"] for p in params["value"]] == ["nema", "plate_t", "tilt", "h_", "vented"]
    h = child(params, "h_")
    assert child(h, "ParameterId")["value"] == "h"   # exact id kept beside the idShort
    plate = child(params, "plate_t")
    assert child(plate, "Default") == {
        "modelType": "Property", "idShort": "Default", "valueType": "xs:double", "value": "5"}
    assert child(plate, "Range")["min"] == "3" and child(plate, "Range")["max"] == "10"
    assert child(plate, "Unit")["value"] == "mm"
    assert child(child(params, "tilt"), "Unit")["value"] == "deg"
    nema = child(params, "nema")
    assert child(nema, "Default")["valueType"] == "xs:integer"
    assert [o["value"][0]["value"] for o in child(nema, "Options")["value"]] == ["14", "17"]
    assert child(child(params, "vented"), "Default")["value"] == "true"
    assert semantic(plate) == "https://id.madfam.io/concept/parameter"
    preset = child(child(pm, "Presets"), "nema14_thin")
    values = child(preset, "Values")
    assert {v["idShort"]: v["value"] for v in values["value"]} == {
        "h_": "35", "nema": "14", "plate_t": "3.5", "vented": "false"}
    constraints = child(pm, "Constraints")["value"]
    assert [child(c, "Expression")["value"] for c in constraints] == ["plate_t >= 3", "h > plate_t"]
    assert [child(c, "Severity")["value"] for c in constraints] == ["error", "warning"]


def test_mating_interfaces_carry_the_sem1_fields_when_present():
    mi = submodel(build_solid_environment(SEM1_SOLID), "MatingInterfaces")
    assert semantic(mi) == MADFAM["mating-interfaces"].id
    face = child(mi, "motor_face")
    assert semantic(face) == "https://id.madfam.io/concept/cdg-interface"
    assert semantic(child(face, "GeometryType")) == "https://id.madfam.io/concept/bolt-pattern"
    assert child(face, "Polarity")["value"] == "female"
    assert child(face, "Symmetry") | {} == {
        "modelType": "Property", "idShort": "Symmetry", "valueType": "xs:integer", "value": "4",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference", "value": "https://id.madfam.io/concept/interface-symmetry"}]}}
    # The P4-STD terms are attached (deviation 3 of that lane, closed by P4-GRAPH).
    concept = "https://id.madfam.io/concept/"
    assert semantic(child(face, "Polarity")) == concept + "interface-polarity"
    assert semantic(child(face, "Frame")) == concept + "interface-frame"
    assert semantic(child(face, "SizeKeyMap")) == concept + "interface-size-key"
    assert child(face, "SizeKeyParameter")["value"] == "nema"
    mapping = child(face, "SizeKeyMap")["value"]
    assert [(child(m, "ParameterValue")["value"], child(m, "SizeKey")["value"]) for m in mapping] \
        == [("14", "nema-14-face"), ("17", "nema-17-face")]
    origin = child(child(face, "Frame"), "Origin")
    # numbers stay numbers; expressions are kept as strings, never evaluated
    assert origin["valueTypeListElement"] == "xs:string"
    assert [e["value"] for e in origin["value"]] == ["0", "0", "plate_t"]
    normal = child(child(face, "Frame"), "Normal")
    assert normal["valueTypeListElement"] == "xs:double"
    assert [e["value"] for e in normal["value"]] == ["0", "0", "1"]
    refs = child(face, "Parameters")["value"]
    assert [r["value"]["keys"][-1]["value"] for r in refs] == ["nema", "plate_t"]
    assert refs[0]["value"]["keys"][0]["value"].endswith("/ParametricModel")
    compat = child(face, "CompatibleWith")["value"]
    assert [c["second"]["keys"][0]["value"] for c in compat] == [
        "https://id.madfam.io/asset/solid/motor-mount",
        "https://id.madfam.io/asset/solid/nema-damper"]
    rail = child(mi, "rail_mount")
    assert child(rail, "SizeKey")["value"] == "tslot-2020-6mm"
    assert semantic(child(rail, "SizeKey")) == concept + "interface-size-key"
    # a parameter id the manifest does not declare is reported, not dropped
    assert [p["value"] for p in child(rail, "UnresolvedParameters")["value"]] == ["ghost_param"]


def test_let_projects_so_a_stored_frame_can_be_evaluated(tmp_path):
    """ASM-1 v1.1: a frame that reads a `let` name is unevaluable without the block."""
    import shutil

    dst = tmp_path / SEM1_SOLID.name
    shutil.copytree(SEM1_SOLID, dst)
    manifest = json.loads((dst / "project.json").read_text(encoding="utf-8"))
    face = next(i for i in manifest["hyperobject"]["cdg_interfaces"] if i["id"] == "motor_face")
    face["let"] = {"lift": "plate_t * 2",
                   "pilot_r": {"param": "nema", "map": {"17": 11, "14": 9.5}}}
    (dst / "project.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    env = build_solid_environment(dst)
    _ok(env)
    let = child(child(submodel(env, "MatingInterfaces"), "motor_face"), "Let")
    lift, pilot = child(let, "lift"), child(let, "pilot_r")
    assert child(lift, "Name")["value"] == "lift"
    assert child(lift, "Expression")["value"] == "plate_t * 2"
    assert child(pilot, "LookupParameter")["value"] == "nema"
    pairs = [(child(m, "ParameterValue")["value"], child(m, "Value")["value"],
              child(m, "Value")["valueType"]) for m in child(pilot, "LookupMap")["value"]]
    assert pairs == [("14", "9.5", "xs:double"), ("17", "11", "xs:double")]
    # Absent `let`, nothing is projected (every v1.0 shell is byte-identical).
    plain = child(submodel(build_solid_environment(SEM1_SOLID), "MatingInterfaces"), "motor_face")
    assert not has_child(plain, "Let")


def test_sem1_fields_absent_project_cleanly(tmp_path):
    stripped = strip_sem1(SEM1_SOLID, tmp_path)
    env = build_solid_environment(stripped)
    _ok(env)
    mi = submodel(env, "MatingInterfaces")
    for iface in mi["submodelElements"]:
        for absent in ("Frame", "Polarity", "Symmetry", "SizeKey", "SizeKeyParameter"):
            assert not has_child(iface, absent)
    assert not any(e.get("idShort") == "Unit" for e in walk(submodel(env, "ParametricModel")))
    rp = submodel(env, "RequirementProfile")   # still emitted: the legacy hints remain
    assert [e["idShort"] for e in rp["submodelElements"]] == ["DeclaredHints"]


def test_requirement_profile_from_requirements():
    rp = submodel(build_solid_environment(SEM1_SOLID), "RequirementProfile")
    assert semantic(rp) == MADFAM["requirement-profile"].id
    assert [p["value"] for p in child(rp, "Process")["value"]] == ["fff"]
    materials = child(rp, "Materials")
    assert [p["value"] for p in child(materials, "AnyOf")["value"]] == ["petg", "asa"]
    bounds = child(rp, "ProcessParameters")
    density = child(bounds, "sparse_infill_density")
    assert child(density, "Min")["value"] == "40" and child(density, "Unit")["value"] == "percent"
    damper = child(child(rp, "Parts"), "damper")
    assert child(child(damper, "Materials"), "AnyOf")["value"][0]["value"] == "tpu-95a"
    hints = child(rp, "DeclaredHints")
    assert semantic(child(hints, "MaterialAwareness")) == (
        "https://id.madfam.io/concept/material-awareness")


def test_geometry_provision_offers_step_only_for_brep_modes(tmp_path):
    gp = submodel(build_solid_environment(SEM1_SOLID), "GeometryProvision")
    assembly = child(child(gp, "Modes"), "assembly")
    assert child(assembly, "Engine")["value"] == "cadquery"
    assert [f["value"] for f in child(assembly, "ProducibleFormats")["value"]] == [
        "stl", "3mf", "step", "glb"]
    parts = child(assembly, "Parts")["value"]
    assert [(child(p, "PartId")["value"], child(p, "Quantity")["value"]) for p in parts
            if has_child(p, "Quantity")] == [("damper", "4")]
    # an OpenSCAD-only mode cannot produce STEP
    manifest = json.loads((SEM1_SOLID / "project.json").read_text(encoding="utf-8"))
    manifest["project"]["engine"] = "openscad"
    for mode in manifest["modes"]:
        mode.pop("cq_file")
        mode["scad_file"] = "main.scad"
    root = tmp_path / "sem1-bracket"
    root.mkdir()
    (root / "project.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "main.scad").write_text("cube(1);\n", encoding="utf-8")
    gp = submodel(build_solid_environment(root), "GeometryProvision")
    formats = child(child(child(gp, "Modes"), "assembly"), "ProducibleFormats")["value"]
    assert [f["value"] for f in formats] == ["stl", "3mf", "glb"]


def test_bill_of_materials_is_hsebom_shaped_and_claims_idta():
    proj = project_solid(SEM1_SOLID)
    from hyperobjects_aas.common import build_environment

    env = build_environment(proj)
    bom = submodel(env, "BillOfMaterials")
    assert semantic(bom) == IDTA["hsebom"].submodel_semantic_id
    assert {c.submodel: c.claimed for c in proj.conformance}["BillOfMaterials"] == "idta"
    entry = child(bom, "EntryNode")
    assert entry["entityType"] == "SelfManagedEntity"
    assert entry["globalAssetId"] == "https://id.madfam.io/asset/solid/sem1-bracket"
    assembly = child(entry, "assembly")      # plate_only has one part: not a BOM node
    assert not has_child(entry, "plate_only")
    damper = child(assembly, "damper")
    assert damper["entityType"] == "CoManagedEntity"
    assert child(damper, "BulkCount")["valueType"] == "xs:unsignedLong"
    screw = child(entry, "m3_screw")
    assert screw["entityType"] == "SelfManagedEntity"
    assert screw["globalAssetId"] == "https://id.madfam.io/asset/standard/m3x8-iso-4762"
    nut = child(entry, "nut")
    assert nut["entityType"] == "CoManagedEntity"   # no size key: no standard-part asset
    assert child(nut, "QuantityFormula")["value"] == "2 * 2"
    assert not has_child(nut, "BulkCount")
    assert child(bom, "ArcheType")["value"] == "Full"


def test_nameplate_does_not_claim_idta_and_says_why():
    proj = project_solid(SEM1_SOLID)
    np = {c.submodel: c for c in proj.conformance}["Nameplate"]
    assert np.claimed == "madfam"
    assert any("AddressInformation" in m for m in np.missing)
    from hyperobjects_aas.common import build_environment

    sm = submodel(build_environment(proj), "Nameplate")
    assert semantic(sm) == MADFAM["nameplate"].id
    assert sm["supplementalSemanticIds"][0]["keys"][0]["value"] == (
        IDTA["nameplate"].submodel_semantic_id)
    assert child(sm, "URIOfTheProduct")["value"] == (
        "https://app.yantra4d.com/project/sem1-bracket")
    assert semantic(child(sm, "ManufacturerName")) == "0112/2///61987#ABA565#009"
    assert child(sm, "DesignLicense")["value"] == "CERN-OHL-W-2.0"


def test_existing_fixture_without_new_fields_projects():
    env = build_solid_environment(THIMBLE)
    _ok(env)
    assert "MatingInterfaces" in [s["idShort"] for s in env["submodels"]]


def test_concept_descriptions_cover_every_madfam_semantic_id():
    env = build_solid_environment(SEM1_SOLID)
    used = {semantic(e) for sm in env["submodels"] for e in walk(sm)} - {None}
    used |= {k["value"] for sm in env["submodels"] for r in sm.get("supplementalSemanticIds", [])
             for k in r["keys"]}
    madfam = {u for u in used if u.startswith("https://id.madfam.io/")}
    described = {cd["id"] for cd in env["conceptDescriptions"]}
    assert madfam <= described
    bolt = next(cd for cd in env["conceptDescriptions"] if cd["id"].endswith("/bolt-pattern"))
    content = bolt["embeddedDataSpecifications"][0]["dataSpecificationContent"]
    assert {ls["language"] for ls in content["preferredName"]} == {"en", "es", "fr", "pt"}
    assert content["modelType"] == "DataSpecificationIec61360"


def test_soft_projection_with_sem1_fields():
    env = build_soft_environment(SEM1_SOFT)
    _ok(env)
    assert [sm["idShort"] for sm in env["submodels"]] == SOFT_SUBMODELS
    pm = submodel(env, "ParametricModel")
    waist = child(child(pm, "Parameters"), "waist_girth")
    measurement = child(waist, "Measurement")
    assert child(measurement, "Code")["value"] == "waist_girth"
    assert child(waist, "Unit")["value"] == "mm"
    seams = submodel(env, "SeamInterfaces")
    closure = child(seams, "closure")
    assert semantic(child(closure, "Type")) == "https://id.madfam.io/concept/tape-edge"
    fabrics = child(submodel(env, "Fabrics"), "FabricMaterials")["value"]
    assert [f["value"]["keys"][0]["value"] for f in fabrics] == [
        "https://id.madfam.io/asset/material/popelina-algodon",
        "https://id.madfam.io/asset/material/mezclilla-denim"]
    link = child(child(submodel(env, "HardwareLinks"), "HardwareRef"), "RealisedBy")
    assert link["first"]["keys"][0]["value"] == "https://id.madfam.io/asset/soft/sem1-garment"
    assert link["second"]["keys"][0]["value"] == "https://id.madfam.io/asset/solid/sew-on-snap"
    pattern = submodel(env, "PatternProvision")
    back = child(child(pattern, "Pieces"), "back")
    assert child(child(back, "Cut"), "Quantity")["value"] == "2"


def test_soft_projection_without_sem1_fields(tmp_path):
    root = cartridge_from_json(tmp_path, FIXTURES / "fc" / "chainmail-panel.project.json")
    env = build_soft_environment(root)
    _ok(env)
    names = [sm["idShort"] for sm in env["submodels"]]
    assert "RequirementProfile" not in names
    assert not any(e.get("idShort") == "Unit" for e in walk(submodel(env, "ParametricModel")))


def test_material_cards_claim_idta_materials():
    for path, platform in ((Y4D_MATERIAL, "yantra4d"), (FC_MATERIAL, "fashion-cabinet")):
        proj = project_material(path)
        env = proj.environment()
        _ok(env)
        assert proj.platform == platform
        assert [c.claimed for c in proj.conformance] == ["idta"]
        sm = submodel(env, "MaterialData")
        assert semantic(sm) == IDTA["materials"].submodel_semantic_id
        assert has_child(sm, "MaterialSystemProperties") and has_child(sm, "CardData")
    env = build_material_environment(Y4D_MATERIAL)
    classification = child(submodel(env, "MaterialData"), "Classification")
    assert child(classification, "EmmoClass")["value"] == "http://emmo.info/emmo#Elastomer"
    fc = build_material_environment(FC_MATERIAL)
    card = child(submodel(fc, "MaterialData"), "CardData")
    gsm = child(child(card, "physical"), "gsm")
    assert semantic(gsm) == "https://id.madfam.io/concept/gsm"   # from the lexicon alias


def test_projection_is_byte_deterministic(tmp_path):
    a = canonical_json(build_solid_environment(SEM1_SOLID))
    b = canonical_json(build_solid_environment(SEM1_SOLID))
    assert a == b
    c = canonical_json(build_soft_environment(SEM1_SOFT))
    assert c == canonical_json(build_soft_environment(SEM1_SOFT))
    assert canonical_json(build_material_environment(Y4D_MATERIAL)) == canonical_json(
        build_material_environment(Y4D_MATERIAL))
    # a source change is a new revision: a new shell id, the asset id unchanged
    copy = strip_sem1(SEM1_SOLID, tmp_path)
    (copy / "main.py").write_text("PLATE_T = 6.0\n", encoding="utf-8")
    other = build_solid_environment(copy)["assetAdministrationShells"][0]
    this = build_solid_environment(SEM1_SOLID)["assetAdministrationShells"][0]
    assert other["id"] != this["id"]
    assert other["assetInformation"]["globalAssetId"] == this["assetInformation"]["globalAssetId"]


def test_odd_shapes_are_skipped_not_fatal(tmp_path):
    manifest = json.loads((SEM1_SOLID / "project.json").read_text(encoding="utf-8"))
    manifest["parameters"].append("not-a-dict")
    manifest["parameters"].append({"id": "nan_slider", "type": "slider", "default": None})
    manifest["hyperobject"]["material_awareness"] = True
    manifest["hyperobject"]["cdg_interfaces"].append({"id": "odd", "frame": {"origin": [1, 2]},
                                                      "compatible_with": ["Not A Slug", 3]})
    manifest["bom"] = [{"item": {"en": "Legacy screws"}, "quantity_formula": "n"}]
    manifest["project"]["description"] = "plain string description"
    root = tmp_path / "sem1-bracket"
    root.mkdir()
    (root / "project.json").write_text(json.dumps(manifest), encoding="utf-8")
    env = build_solid_environment(root)
    _ok(env)
    odd = child(submodel(env, "MatingInterfaces"), "odd")
    assert not has_child(odd, "CompatibleWith")
    assert child(child(odd, "Frame"), "Origin")["valueType"] == "xs:string"
