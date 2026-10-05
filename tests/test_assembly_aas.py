"""ASM-1 §5: the assembly AAS projection, on the golden assemblies A and B.

The inputs are byte-identical copies of solid-hyperobjects main (NOTICE.md beside them),
so the digests pinned here are the ones the commons CI computes for the same documents.
"""

from __future__ import annotations

import base64
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from aas_support import child, has_child, semantic, submodel
from hyperobjects_aas import build_solid_environment, check_environment
from hyperobjects_aas.assembly import (
    AssemblyProjectionError,
    assembly_document_from_environment,
    build_assembly_environment,
    component_type_shells,
)
from hyperobjects_aas.resolver import (
    EnvironmentCartridgeResolver,
    bundled_standard_parts_dir,
    manifest_from_submodels,
    requirements_from_submodel,
)
from hyperobjects_aas.templates import IDTA, MADFAM
from hyperobjects_schemas.generator_output import canonical_json, tree_sha256
from y4d_spec.assembly import (
    CompositeResolver,
    StandardPartsResolver,
    validate_assembly,
)

GOLDEN = Path(__file__).parent / "fixtures" / "assembly-golden"
COMMONS = GOLDEN / "commons"
A = "voron-2-4-class-350-motion-frame"
B = "fpv-5in-freestyle"
#: A's digest is the one the commons CI prints. B (solid #136: the camera cage on the side
#: plates' outer faces, 13 mates) hashes the `fpv-frame-5in-x-225` catalog entry, which #41
#: changed after the commons' SPEC_PIN (8c12194, where B is f0db7bdb…): a standard part's
#: catalog digest enters the assembly digest, so the commons CI prints this one once its
#: SPEC_PIN reaches this keystone.
DIGESTS = {
    A: "24322cc06fe30ff82dbf11515b6684a51c97a2be33c724943296844587d74614",
    B: "96166430930bbe5817f394ef382221f257f0f2de20b67cb38bec02c142e8f23c",
}
ID = "https://id.madfam.io"


def _doc(slug: str) -> dict:
    return json.loads((COMMONS / "assemblies" / slug / "assembly.json").read_text("utf-8"))


def _resolver():
    return CompositeResolver.for_directories(COMMONS, bundled_standard_parts_dir())


def _report(slug: str):
    return validate_assembly(_doc(slug), _resolver())


@pytest.fixture(scope="module")
def envs() -> dict[str, dict]:
    return {slug: build_assembly_environment(_doc(slug), _report(slug)) for slug in DIGESTS}


@pytest.fixture(scope="module")
def type_store() -> dict[str, dict]:
    """The cartridge type environments, keyed by shell id (what asset-shells stores)."""
    store = {}
    for directory in sorted(p for p in COMMONS.iterdir() if (p / "project.json").is_file()):
        env = build_solid_environment(directory)
        store[env["assetAdministrationShells"][0]["id"]] = env
    return store


def _fetch(store):
    def fetch(shell_id):
        env = store.get(shell_id)
        if env is None:
            return None
        return env["assetAdministrationShells"][0], {s["idShort"]: s for s in env["submodels"]}
    return fetch


# ── the golden assemblies validate exactly as in the commons ─────────────────
@pytest.mark.parametrize("slug,components", [(A, 15), (B, 13)])
def test_golden_assemblies_pass_with_the_commons_digests(slug, components):
    report = _report(slug)
    assert report.ok, [str(f) for f in report.findings]
    assert not report.warnings
    assert report.digest == DIGESTS[slug]
    assert len(report.placements) == components
    assert len(report.mates) == components and all(m.ok for m in report.mates)


@pytest.mark.parametrize("slug", [A, B])
def test_golden_environment_is_byte_identical(slug, envs):
    golden = (GOLDEN / "golden" / f"{slug}.aas.json").read_bytes()
    assert canonical_json(envs[slug]) == golden, (
        "the projection moved: run scripts/refresh_assembly_golden.py and review the diff")


@pytest.mark.parametrize("slug", [A, B])
def test_golden_environment_passes_aas_check(slug, envs):
    result = check_environment(envs[slug])
    assert result.ok, [str(f) for f in result.errors]
    assert result.basyx in ("verified", "not installed")


# ── shell and identifiers (ASM-1 §5) ──────────────────────────────────────────
def test_shell_is_named_by_the_assembly_digest(envs):
    (shell,) = envs[B]["assetAdministrationShells"]
    assert shell["id"] == f"{ID}/aas/assembly/{B}/{DIGESTS[B][:16]}"
    info = shell["assetInformation"]
    assert info["assetKind"] == "Type"
    assert info["globalAssetId"] == f"{ID}/asset/assembly/{B}"
    assert info["specificAssetIds"] == [
        {"name": "commons", "value": "solid-hyperobjects"},
        {"name": "slug", "value": B},
        {"name": "assembly_digest", "value": DIGESTS[B]},
    ]
    for sm in envs[B]["submodels"]:
        assert sm["id"] == f"{ID}/sm/assembly/{B}/{DIGESTS[B][:16]}/{sm['idShort']}"


def test_producer_and_product_carry_their_own_submodels(envs):
    names = {slug: [sm["idShort"] for sm in env["submodels"]] for slug, env in envs.items()}
    common = ["Nameplate", "AssemblyDocument", "BillOfMaterials", "Mates", "AssemblyPlacement"]
    assert names[A] == [*common, "CapabilityDescription"]
    assert names[B] == [*common, "RequirementProfile"]


def test_document_round_trips_through_the_blob(envs):
    for slug, env in envs.items():
        assert assembly_document_from_environment(env) == _doc(slug)
        doc_sm = submodel(env, "AssemblyDocument")
        assert child(doc_sm, "AssemblyDigest")["value"] == DIGESTS[slug]
        assert child(doc_sm, "DigestAlgorithm")["value"] == "hyperobjects-assembly-v1"
        assert child(doc_sm, "Document")["contentType"] == "application/json"


# ── BillOfMaterials (HSEBoM) ──────────────────────────────────────────────────
def test_bill_of_materials_claims_hsebom_and_has_one_node_per_component(envs):
    bom = submodel(envs[A], "BillOfMaterials")
    assert semantic(bom) == IDTA["hsebom"].submodel_semantic_id
    entry = child(bom, "EntryNode")
    assert entry["globalAssetId"] == f"{ID}/asset/assembly/{A}"
    nodes = [s for s in entry["statements"] if s["modelType"] == "Entity"]
    links = [s for s in entry["statements"] if s["modelType"] == "RelationshipElement"]
    assert [child(n, "ComponentId")["value"] for n in nodes] == [
        c["id"] for c in _doc(A)["components"]]
    assert len(links) == len(nodes)
    assert all(semantic(link) == IDTA["hsebom"].elements["HasPart"] for link in links)


def test_cartridge_node_names_its_type_shell_revision_and_instance_id(envs):
    report = _report(B)
    node = child(child(submodel(envs[B], "BillOfMaterials"), "EntryNode"), "pod_fl")
    tree = tree_sha256(COMMONS / "motor-soft-mount")
    assert node["entityType"] == "SelfManagedEntity"
    assert node["globalAssetId"] == f"{ID}/asset/solid/motor-soft-mount"
    iid = report.components["pod_fl"].identity["instance_id"]
    assert node["specificAssetIds"] == [{"name": "instance_id", "value": iid}]
    derived = child(node, "DerivedFrom")["value"]["keys"]
    assert derived == [{"type": "AssetAdministrationShell",
                        "value": f"{ID}/aas/solid/motor-soft-mount/{tree[:16]}"}]
    assert component_type_shells(envs[B])["pod_fl"] == derived[0]["value"]


def test_standard_and_external_nodes(envs):
    entry = child(submodel(envs[A], "BillOfMaterials"), "EntryNode")
    motor = child(entry, "motor_a")
    assert motor["globalAssetId"] == f"{ID}/asset/standard/nema-17-48mm"
    assert child(motor, "Key")["value"] == "nema-17-48mm"
    toolhead = child(entry, "toolhead")
    assert toolhead["entityType"] == "CoManagedEntity" and "globalAssetId" not in toolhead
    assert child(toolhead, "License")["value"] == "GPL-3.0"
    assert child(toolhead, "Url")["valueType"] == "xs:anyURI"
    counts = {child(c, "Source")["value"]: int(child(c, "Count")["value"])
              for c in child(submodel(envs[A], "BillOfMaterials"), "CountsBySource")["value"]}
    assert counts[f"{ID}/asset/standard/extrusion-2020"] == 3
    assert counts[f"{ID}/asset/solid/tslot-corner"] == 2


# ── Mates, placement, capability, requirements ────────────────────────────────
def test_mates_carry_rotation_residuals_and_verdict(envs):
    mates = submodel(envs[B], "Mates")
    assert semantic(mates) == MADFAM["assembly-mates"].id
    elements = mates["submodelElements"]
    assert [e["idShort"] for e in elements] == [m["id"] for m in _doc(B)["mates"]]
    closing = child(mates, "cage_ear_right_on_plate")
    assert closing["modelType"] == "AnnotatedRelationshipElement"
    notes = {a["idShort"]: a["value"] for a in closing["annotations"]}
    assert notes["InTree"] == "false" and notes["Validated"] == "true"
    assert notes["Symmetry"] == "0"
    assert notes["AngleDeg"] == "0" and notes["MeasuredDeg"] == "0"
    # finding 3b: the stated angle of a continuous closing mate now has a residual
    assert notes["XAxisResidualDeg"] == "0"
    assert closing["second"]["keys"][-1] == {"type": "Entity", "value": "camera_cage"}


def test_placement_root_is_identity_and_camera_sits_where_the_commons_says(envs):
    comps = child(submodel(envs[B], "AssemblyPlacement"), "Components")
    frame = [float(v["value"]) for v in child(child(comps, "frame"), "Transform")["value"]]
    assert frame == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    cage = [float(v["value"]) for v in child(child(comps, "camera_cage"), "Transform")["value"]]
    assert (cage[3], cage[7], cage[11]) == pytest.approx((62, 0, 13.75))
    camera = [float(v["value"]) for v in child(child(comps, "camera"), "Transform")["value"]]
    assert (camera[3], camera[7], camera[11]) == pytest.approx((71.3531, 0, 19.15), abs=1e-4)


def test_producer_capability_description_claims_idta_02020(envs):
    cap = submodel(envs[A], "CapabilityDescription")
    assert semantic(cap) == IDTA["capability-description"].submodel_semantic_id
    container = child(child(cap, "CapabilitySet"), "Fabrication_fff")
    assert child(container, "fff")["modelType"] == "Capability"
    props = child(container, "PropertySet")
    assert child(child(props, "toolhead_count"), "toolhead_count")["value"] == "1"


def test_product_requirement_rollup_names_the_tpu_pods(envs):
    req = submodel(envs[B], "RequirementProfile")
    assert [p["value"] for p in child(req, "Process")["value"]] == ["fff"]
    rows = child(req, "Components")["value"]
    assert [child(r, "ComponentId")["value"] for r in rows] == ["pod_fl", "pod_fr", "pod_rl",
                                                                "pod_rr"]
    part = child(child(rows[0], "Parts"), "soft_mount")
    assert [m["value"] for m in child(child(part, "Materials"), "AnyOf")["value"]] == ["tpu-95a"]


def test_a_failing_assembly_is_never_projected():
    doc = _doc(B)
    doc["mates"][11]["angle_deg"] = 40  # the cage's closing ear mate, now contradicting geometry
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    with pytest.raises(AssemblyProjectionError, match="did not pass its check"):
        build_assembly_environment(doc, report)


# ── the asset-shells seam: resolving from stored type shells ──────────────────
@pytest.mark.parametrize("slug", [A, B])
def test_environment_resolver_reproduces_digest_and_environment(slug, envs, type_store):
    env = envs[slug]
    doc = assembly_document_from_environment(env)
    resolver = CompositeResolver(
        cartridge=EnvironmentCartridgeResolver(component_type_shells(env), _fetch(type_store)),
        standard=StandardPartsResolver(bundled_standard_parts_dir()),
    )
    report = validate_assembly(doc, resolver)
    assert report.ok, [str(f) for f in report.errors]
    assert report.digest == DIGESTS[slug]
    assert canonical_json(build_assembly_environment(doc, report)) == canonical_json(env)


def test_environment_resolver_names_what_it_cannot_resolve(envs, type_store):
    env = envs[B]
    shells = component_type_shells(env)
    store = dict(type_store)
    del store[shells["battery_pad"]]
    pins = dict(shells)
    pins.pop("fc_standoffs")
    pins["pod_fl"] = shells["battery_pad"]  # a revision of another cartridge
    resolver = CompositeResolver(
        cartridge=EnvironmentCartridgeResolver(pins, _fetch(store)),
        standard=StandardPartsResolver(bundled_standard_parts_dir()),
    )
    report = validate_assembly(_doc(B), resolver)
    errors = {(f.subject, f.code): f.message for f in report.errors}
    assert "is not published" in errors[("battery_pad", "resolve")]
    assert "no type shell is named" in errors[("fc_standoffs", "resolve")]
    assert "is not a revision of the solid cartridge 'motor-soft-mount'" in errors[
        ("pod_fl", "resolve")]
    assert report.digest is None


def test_manifest_read_back_keeps_the_written_checkbox_default(tmp_path):
    """A checkbox written as 0/1 projects as a boolean Default plus DefaultAsWritten, so the
    GOC-1 identity (which hashes 1, not true) survives the round trip."""
    import shutil

    dst = tmp_path / "nema-bracket"
    shutil.copytree(COMMONS / "nema-bracket", dst)
    manifest = json.loads((dst / "project.json").read_text("utf-8"))
    gusset = next(p for p in manifest["parameters"] if p["id"] == "gusset")
    gusset["default"] = 1
    (dst / "project.json").write_text(json.dumps(manifest), "utf-8")
    env = build_solid_environment(dst)
    params = child(submodel(env, "ParametricModel"), "Parameters")
    sm_gusset = next(p for p in params["value"] if child(p, "ParameterId")["value"] == "gusset")
    assert child(sm_gusset, "Default")["value"] == "true"
    assert child(sm_gusset, "DefaultAsWritten") | {} == {
        "modelType": "Property", "idShort": "DefaultAsWritten", "valueType": "xs:integer",
        "value": "1"}
    back = manifest_from_submodels({s["idShort"]: s for s in env["submodels"]})
    assert next(p for p in back["parameters"] if p["id"] == "gusset")["default"] == 1
    units = [child(p, "Unit") for p in params["value"] if has_child(p, "Unit")]
    assert units and all(semantic(u) == f"{ID}/concept/parameter-unit" for u in units)


def test_requirements_read_back_from_a_stored_requirement_profile():
    """What the RequirementProfile carries comes back, so re-projecting it is identical
    (a per-part rationale is not projected at all, so it is not read back either)."""
    from hyperobjects_aas.solid import requirements_elements

    env = build_solid_environment(COMMONS / "motor-soft-mount")
    manifest = json.loads((COMMONS / "motor-soft-mount" / "project.json").read_text("utf-8"))
    back = requirements_from_submodel(submodel(env, "RequirementProfile"))
    assert back == {"parts": {"soft_mount": {"process": ["fff"],
                                             "materials": {"any_of": ["tpu-95a"]}}}}
    assert requirements_elements(back) == requirements_elements(manifest["requirements"])


# ── reading an assembly environment fails visibly ─────────────────────────────
def test_reading_the_document_names_every_defect(envs):
    env = copy.deepcopy(envs[B])
    blob = child(submodel(env, "AssemblyDocument"), "Document")
    blob["value"] = "not base64!"
    with pytest.raises(AssemblyProjectionError, match="not base64 JSON"):
        assembly_document_from_environment(env)
    blob["contentType"] = "text/plain"
    with pytest.raises(AssemblyProjectionError, match="not application/json"):
        assembly_document_from_environment(env)
    env["submodels"] = [s for s in env["submodels"] if s["idShort"] != "AssemblyDocument"]
    with pytest.raises(AssemblyProjectionError, match="no AssemblyDocument"):
        assembly_document_from_environment(env)


def test_aas_check_refuses_an_assembly_shell_that_lies_about_its_document(envs):
    env = copy.deepcopy(envs[B])
    blob = child(submodel(env, "AssemblyDocument"), "Document")
    doc = _doc(B)
    doc["slug"] = "another-quad"
    blob["value"] = base64.b64encode(canonical_json(doc)).decode()
    child(submodel(env, "AssemblyDocument"), "AssemblyDigest")["value"] = "0" * 64
    result = check_environment(env, basyx="off")
    messages = [f.message for f in result.errors if f.code == "assembly"]
    assert any("is not the shell's 'fpv-5in-freestyle'" in m for m in messages)
    assert any("AssemblyDigest does not equal" in m for m in messages)


# ── the console script ────────────────────────────────────────────────────────
def _cli(*args):
    return subprocess.run([sys.executable, "-m", "y4d_spec.cli", "aas", *args],
                          capture_output=True, text=True, check=False)


def test_aas_build_projects_an_assembly_directory(tmp_path):
    out = tmp_path / "b.aas.json"
    run = _cli("build", str(COMMONS / "assemblies" / B), "--out", str(out))
    assert run.returncode == 0, run.stderr
    assert out.read_bytes() == (GOLDEN / "golden" / f"{B}.aas.json").read_bytes()
    check = _cli("check", str(out), "--basyx", "off")
    assert check.returncode == 0, check.stdout


def test_aas_build_of_a_failing_assembly_is_a_check_error(tmp_path):
    doc = _doc(B)
    doc["mates"][11]["angle_deg"] = 40
    path = tmp_path / "assembly.json"
    path.write_text(json.dumps(doc), "utf-8")
    run = _cli("build", str(path), "--commons-dir", str(COMMONS), "--out",
               str(tmp_path / "x.json"))
    assert run.returncode == 1, run.stderr
    assert "stated angle_deg 40° but the geometry realises 0°" in run.stdout + run.stderr
    assert not (tmp_path / "x.json").exists()
