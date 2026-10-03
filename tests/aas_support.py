"""Shared helpers for the hyperobjects_aas tests (imported, not a conftest)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
AAS = FIXTURES / "aas"
SEM1_SOLID = AAS / "sem1-bracket"
SEM1_SOFT = AAS / "sem1-garment"
Y4D_MATERIAL = AAS / "bambu-tpu-95a.material.json"
FC_MATERIAL = FIXTURES / "fc" / "manta-cruda.material.json"
THIMBLE = FIXTURES / "y4d" / "thimble"

#: Every field SEM-1 §2/§3 adds. A manifest without them must project cleanly.
SEM1_INTERFACE_KEYS = ("frame", "polarity", "size_key", "symmetry")


def cartridge_from_json(tmp_path: Path, manifest_path: Path) -> Path:
    """A one-file cartridge directory named after the manifest's slug."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = tmp_path / manifest["project"]["slug"]
    root.mkdir(parents=True)
    shutil.copy(manifest_path, root / "project.json")
    return root


def strip_sem1(src: Path, tmp_path: Path) -> Path:
    """Copy a SEM-1 fixture cartridge with every SEM-1 field removed."""
    dst = tmp_path / src.name
    shutil.copytree(src, dst)
    manifest = json.loads((dst / "project.json").read_text(encoding="utf-8"))
    manifest.pop("requirements", None)
    for p in manifest.get("parameters", []):
        p.pop("unit", None)
    for iface in (manifest.get("hyperobject") or {}).get("cdg_interfaces", []):
        for key in SEM1_INTERFACE_KEYS:
            iface.pop(key, None)
    (dst / "project.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dst


def submodel(env: dict, id_short: str) -> dict:
    matches = [sm for sm in env.get("submodels", []) if sm["idShort"] == id_short]
    assert matches, f"no submodel {id_short}: {[s['idShort'] for s in env.get('submodels', [])]}"
    return matches[0]


def child(element: dict, id_short: str) -> dict:
    """The child with ``id_short`` of a Submodel, collection or Entity."""
    kids = element.get("submodelElements") or element.get("statements") or element.get("value")
    for k in kids or []:
        if k.get("idShort") == id_short:
            return k
    raise AssertionError(f"no child {id_short} in {element.get('idShort')}")


def has_child(element: dict, id_short: str) -> bool:
    try:
        child(element, id_short)
    except AssertionError:
        return False
    return True


def semantic(element: dict) -> str | None:
    keys = (element.get("semanticId") or {}).get("keys") or []
    return keys[0]["value"] if keys else None


def walk(element: dict):
    """Every element below (and including) ``element``."""
    yield element
    for key in ("submodelElements", "statements", "value"):
        kids = element.get(key)
        if isinstance(kids, list):
            for k in kids:
                if isinstance(k, dict) and "modelType" in k:
                    yield from walk(k)
