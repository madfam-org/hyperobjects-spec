"""One digest, one projection (SEM-1 §1, ASM-1 §5; finding F1 of lane P6-ASM).

A shell id names a revision by a digest of the *canonical* JSON (GOC-1 §3.1: an integral
float is an integer, so ``20.0`` and ``20`` hash the same). A store keeps the bytes under
an id immutable (asset-shells answers a 409). So the bytes must be a function of the
canonical input too: if the spelling of a whole number could reach the projection, the
same id would carry two byte projections.

Two kinds are content-addressed through canonical JSON:

* an assembly: ``digest16`` hashes the document and the resolved identities (ASM-1 §3.8);
* a material card: ``content16`` hashes the card.

A cartridge (solid, soft) is addressed by ``tree_sha256``, the digest of its file *bytes*,
so a respelt ``project.json`` is a new revision with a new id: it cannot collide.

The failure F1 found, reproduced on both paths a projection is made on:

* the golden refresh (``scripts/refresh_assembly_golden.py``), projecting the document as
  the author wrote it;
* the asset-shells seam: ``assembly_document_from_environment`` (the canonical blob) →
  ``EnvironmentCartridgeResolver`` → ``build_assembly_environment``.

Before the fix, a cartridge parameter written ``20.0`` projected ``xs:double`` from the
document and ``xs:integer`` from the blob, under one shell id.
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path

import pytest

from hyperobjects_aas import build_solid_environment
from hyperobjects_aas.assembly import (
    assembly_document_from_environment,
    build_assembly_environment,
    component_type_shells,
)
from hyperobjects_aas.drift import immutable_drift
from hyperobjects_aas.resolver import EnvironmentCartridgeResolver, bundled_standard_parts_dir
from hyperobjects_schemas.generator_output import canonical_json, normalize_numbers
from y4d_spec.assembly import CompositeResolver, StandardPartsResolver, validate_assembly

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
GOLDEN = FIXTURES / "assembly-golden"
COMMONS = GOLDEN / "commons"
KIN = FIXTURES / "kinematics"
A = "voron-2-4-class-350-motion-frame"
B = "fpv-5in-freestyle"
GANTRY = "kinematic-gantry"

#: Every assembly document fixture of the keystone, with the resolver it validates against.
ASSEMBLIES = {
    A: (COMMONS / "assemblies" / A / "assembly.json",
        lambda: CompositeResolver.for_directories(COMMONS, bundled_standard_parts_dir())),
    B: (COMMONS / "assemblies" / B / "assembly.json",
        lambda: CompositeResolver.for_directories(COMMONS, bundled_standard_parts_dir())),
    GANTRY: (KIN / "kinematic-gantry.assembly.json",
             lambda: CompositeResolver.for_directories(
                 standard_parts=[bundled_standard_parts_dir(), KIN / "standard-parts"])),
}
#: Every material card fixture (a yantra4d card and a Fashion Cabinet card).
MATERIALS = {
    "bambu-tpu-95a": FIXTURES / "aas" / "bambu-tpu-95a.material.json",
    "manta-cruda": FIXTURES / "fc" / "manta-cruda.material.json",
}

#: The fabrication vocabulary checks a capability value against its declared value_type
#: as written, so ``toolhead_count: 1.0`` is a validator finding (fail-visible: no shell is
#: minted). The respelling below leaves that block alone; it is a validator rule, not the
#: projection this file guards.
_VALIDATOR_STRICT = ("capability_profile",)


def _load(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _respell(obj: object, rng: random.Random | None = None, path: str = "") -> object:
    """``obj`` with its integers written as floats (``20`` -> ``20.0``): every one, or with
    ``rng``, a seeded half of them. Booleans stay booleans. The canonical JSON is unchanged."""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int):
        return float(obj) if rng is None or rng.random() < 0.5 else obj
    if isinstance(obj, dict):
        return {k: v if (not path and k in _VALIDATOR_STRICT)
                else _respell(v, rng, f"{path}.{k}") for k, v in obj.items()}
    if isinstance(obj, list):
        return [_respell(v, rng, f"{path}[]") for v in obj]
    return obj


def _variants(doc: dict) -> list[tuple[str, dict]]:
    return [("every-integer", _respell(doc)),
            *[(f"seed-{seed}", _respell(doc, random.Random(seed))) for seed in (1, 2)]]


def _project(doc: dict, resolver) -> bytes:
    report = validate_assembly(doc, resolver)
    assert report.ok, [str(f) for f in report.errors]
    return canonical_json(build_assembly_environment(doc, report))


def _float_spelled(doc: dict, component_id: str, parameter: str) -> dict:
    """``doc`` with one whole-number parameter of one component written as a float."""
    out = copy.deepcopy(doc)
    source = next(c for c in out["components"] if c["id"] == component_id)["source"]
    value = source["parameters"][parameter]
    assert isinstance(value, int) and not isinstance(value, bool)
    source["parameters"][parameter] = float(value)
    assert canonical_json(out) == canonical_json(doc)  # the digest cannot tell them apart
    return out


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


# ── F1, reproduced on both paths ──────────────────────────────────────────────
#: A cartridge parameter (F1's own example) and a standard-part parameter: the BoM projects
#: the first from the document and the second from the resolved identity.
F1_CASES = [("z0_z_joint", "c_end"), ("u0", "length_mm")]


@pytest.mark.parametrize("component_id,parameter", F1_CASES)
def test_golden_refresh_path_float_spelled_parameter_projects_the_golden_bytes(
        component_id, parameter):
    """The golden refresh path: the document as written. A float-spelled whole number must
    project the golden's bytes, else the drift guard reports immutable drift under an id
    the golden already carries (F1, step 3)."""
    path, resolver = ASSEMBLIES[A]
    doc = _float_spelled(_load(path), component_id, parameter)
    fresh = _project(doc, resolver())
    golden = (GOLDEN / "golden" / f"{A}.aas.json").read_bytes()
    assert immutable_drift(json.loads(golden), json.loads(fresh)) == []
    assert fresh == golden


@pytest.mark.parametrize("component_id,parameter", F1_CASES)
def test_blob_round_trip_path_float_spelled_parameter_reprojects_the_same_bytes(
        component_id, parameter, type_store):
    """The asset-shells path: the stored AssemblyDocument blob (canonical JSON) resolved
    from stored type shells and projected again must give the published bytes."""
    path, resolver = ASSEMBLIES[A]
    published = json.loads(_project(_float_spelled(_load(path), component_id, parameter),
                                     resolver()))
    stored = assembly_document_from_environment(published)
    report = validate_assembly(stored, CompositeResolver(
        cartridge=EnvironmentCartridgeResolver(component_type_shells(published),
                                               _fetch(type_store)),
        standard=StandardPartsResolver(bundled_standard_parts_dir()),
    ))
    assert report.ok, [str(f) for f in report.errors]
    again = canonical_json(build_assembly_environment(stored, report))
    assert immutable_drift(published, json.loads(again)) == []
    assert again == canonical_json(published)


# ── the property: project(doc) == project(canonical(doc)) ─────────────────────
@pytest.mark.parametrize("name", sorted(ASSEMBLIES))
def test_assembly_projection_is_a_function_of_the_canonical_document(name):
    path, make_resolver = ASSEMBLIES[name]
    resolver = make_resolver()
    doc = _load(path)
    canonical = _project(normalize_numbers(doc), resolver)
    assert _project(doc, resolver) == canonical
    for label, variant in _variants(doc):
        assert canonical_json(variant) == canonical_json(doc), label
        assert _project(variant, resolver) == canonical, f"{name}: {label}"


def test_a_respelt_cartridge_is_a_new_revision_not_a_collision(tmp_path):
    """A cartridge's id hashes its file bytes (``tree_sha256``), not canonical JSON, so a
    respelt manifest mints a new id rather than new bytes under the old one."""
    import shutil

    src = COMMONS / "z-joint"
    dst = tmp_path / "z-joint"
    shutil.copytree(src, dst)
    manifest = _load(dst / "project.json")
    (dst / "project.json").write_text(json.dumps(normalize_numbers(manifest), indent=2) + "\n",
                                      encoding="utf-8")
    before = build_solid_environment(src)["assetAdministrationShells"][0]["id"]
    after = build_solid_environment(dst)["assetAdministrationShells"][0]["id"]
    assert before != after
