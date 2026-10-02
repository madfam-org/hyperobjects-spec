"""Shared builders for the assembly tests (ASM-1). Not a test module."""

from __future__ import annotations

import math
from pathlib import Path

from y4d_spec.assembly import CompositeResolver

FIX = Path(__file__).parent / "fixtures" / "assembly"
COMMONS = FIX / "commons"
STANDARD = FIX / "standard-parts"
SEMANTIC_MOUNT = Path(__file__).parent / "fixtures" / "y4d" / "semantic-motor-mount.project.json"


def resolver(commons=COMMONS, standard=STANDARD):
    return CompositeResolver.for_directories(commons, standard)


def cartridge(cid, slug="nema-bracket", mode="flat", part=None, **params):
    source = {"type": "cartridge", "commons": "solid", "slug": slug, "mode": mode, "part": part}
    if params:
        source["parameters"] = params
    return {"id": cid, "source": source}


def standard(cid, key, **params):
    source = {"type": "standard", "key": key}
    if params:
        source["parameters"] = params
    return {"id": cid, "source": source}


def mate(mid, a, b, rotation_index=0, angle_deg=None):
    ca, ia = a.split(".")
    cb, ib = b.split(".")
    out = {"id": mid, "a": {"component": ca, "interface": ia},
           "b": {"component": cb, "interface": ib}}
    if angle_deg is None:
        out["rotation_index"] = rotation_index
    else:
        out["angle_deg"] = angle_deg
    return out


def assembly(components, mates, root=None, kind="product", **extra):
    doc = {
        "format": "hyperobjects.assembly",
        "format_version": "1.0.0",
        "slug": "test-assembly",
        "kind": kind,
        "name": {"en": "Test assembly", "es": "Ensamble de prueba"},
        "license": "CERN-OHL-W-2.0",
        "root": root or components[0]["id"],
        "components": components,
        "mates": mates,
    }
    doc.update(extra)
    return doc


def assert_matrix(actual, expected, tol=1e-9):
    assert len(actual) == 4
    for i in range(4):
        for j in range(4):
            assert math.isclose(actual[i][j], expected[i][j], abs_tol=tol), (
                f"[{i}][{j}] = {actual[i][j]} != {expected[i][j]}\n{actual}"
            )


def codes(report, severity="error"):
    items = report.errors if severity == "error" else report.warnings
    return [(f.code, f.subject) for f in items]
