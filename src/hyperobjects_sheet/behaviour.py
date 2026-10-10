"""The ``sheet_behaviour`` v1 document: constants, provenance helpers and the validator.

A document passes when it validates against ``sheet-behaviour.schema.json`` AND is
physically admissible: positive-definite membrane and bending stiffness, consistent
regime flags, and one provenance entry per number (no number without a basis, no basis
without a number). Everything else worth saying — an implausible density, a bending
stiffness far from the plate value of its membrane — is a **note**. No commons runs this
as a gate yet (land the data before enforcing it).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from . import linalg as la

VERSION = "1.0"

UNITS: dict[str, str] = {
    "caliper": "mm",
    "areal_density": "kg/m^2",
    "membrane": "N/m",
    "bending": "N*m",
    "angle": "deg",
}
OPTIONAL_UNITS: dict[str, str] = {
    "compression": "Pa",
    "curvature": "1/m",
    "laminate": "A N/m, B N, D N*m",
}

STATUSES = ("measured", "derived", "estimated")

#: The numeric leaves of a document, by block (``None`` = top level). Each one needs a
#: provenance entry under its own name.
NUMERIC_FIELDS: dict[str | None, tuple[str, ...]] = {
    None: ("caliper_mm", "areal_density_kg_m2"),
    "membrane": ("E1t", "E2t", "G12t", "nu12"),
    "bending": ("D11", "D22", "D12", "D66", "D16", "D26"),
    "crease": ("crease_length_scale_t", "crease_yield_deg", "crease_set_rate", "score_factor"),
    "compression": ("Ez",),
    "contact": ("friction_static", "friction_kinetic", "damping"),
    "self_folding": ("target_curvature_1_m",),
}

#: Plausible bulk density of a sheet material, kg/m³ (a note outside it, not a failure):
#: the low end admits open foams and loose felt, the high end metal foil.
DENSITY_BAND = (10.0, 3000.0)
#: A homogeneous plate's D11 is E1t·t²/(12(1 − ν12ν21)). Outside this factor of it a
#: sheet is not bending as a plate (expected for fabric and laminates; worth a note
#: on anything flagged inextensible and single-layer).
PLATE_RATIO_BAND = (0.1, 10.0)


@dataclass
class SheetCheck:
    """The verdict on one document."""

    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@cache
def _validator():
    from jsonschema import Draft202012Validator

    from hyperobjects_schemas import load

    return Draft202012Validator(load("sheet-behaviour"))


@cache
def _ref_validator():
    from jsonschema import Draft202012Validator

    from hyperobjects_schemas import load

    schema = load("sheet-behaviour")
    return Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/material_ref"})


def schema_errors(doc: Any) -> list[str]:
    out = []
    for err in sorted(_validator().iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        out.append(f"schema: {where}: {err.message}")
    return out


def material_ref_errors(ref: Any) -> list[str]:
    """Shape errors of a ``material_ref`` (``{platform, material_slug, behaviour}``)."""
    return [
        f"material_ref: {'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}"
        for e in _ref_validator().iter_errors(ref)
    ]


def numeric_paths(doc: dict) -> list[str]:
    """The provenance keys a document owes: every numeric field it carries."""
    out: list[str] = []
    for blk, names in NUMERIC_FIELDS.items():
        src = doc if blk is None else doc.get(blk)
        if not isinstance(src, dict):
            continue
        out.extend(name for name in names if name in src)
    return out


def membrane_matrix(m: dict) -> la.Matrix:
    """The membrane stiffness (N/m) implied by E1t, E2t, G12t and nu12."""
    e1, e2, g, nu12 = m["E1t"], m["E2t"], m["G12t"], m["nu12"]
    nu21 = nu12 * e2 / e1
    den = 1.0 - nu12 * nu21
    return [[e1 / den, nu12 * e2 / den, 0.0], [nu12 * e2 / den, e2 / den, 0.0], [0.0, 0.0, g]]


def bending_matrix(b: dict) -> la.Matrix:
    d16, d26 = b.get("D16", 0.0), b.get("D26", 0.0)
    return [[b["D11"], b["D12"], d16], [b["D12"], b["D22"], d26], [d16, d26, b["D66"]]]


def validate(doc: Any) -> SheetCheck:
    """Validate one ``sheet_behaviour`` document (see the module docstring)."""
    result = SheetCheck(errors=schema_errors(doc))
    if result.errors or not isinstance(doc, dict):
        return result
    errors, notes = result.errors, result.notes

    m, b, regime = doc["membrane"], doc["bending"], doc["regime"]
    # Membrane: positive definite iff nu12² < E1t/E2t (with positive moduli).
    if m["nu12"] ** 2 >= m["E1t"] / m["E2t"]:
        errors.append(
            f"membrane: nu12² = {m['nu12'] ** 2:.4g} ≥ E1t/E2t = {m['E1t'] / m['E2t']:.4g} "
            "— the in-plane stiffness is not positive definite"
        )
    if not la.is_positive_definite(bending_matrix(b)):
        errors.append("bending: the D matrix is not positive definite (|D12| too large, "
                      "or D16/D26 too large for D11, D22 and D66)")

    if regime["inextensible"] and regime["stretchy"]:
        errors.append("regime: inextensible and stretchy exclude each other")
    for flag, blk in (("compressible", "compression"), ("layered", "laminate"),
                      ("self_folding", "self_folding")):
        if regime[flag] and blk not in doc:
            errors.append(f"regime: {flag} is true but the '{blk}' block is missing")
        if not regime[flag] and blk in doc:
            errors.append(f"regime: '{blk}' is present but regime.{flag} is false")

    units = doc["units"]
    for blk, unit_key in (("compression", "compression"), ("self_folding", "curvature"),
                          ("laminate", "laminate")):
        if blk in doc and unit_key not in units:
            errors.append(f"units: the '{blk}' block needs units.{unit_key} "
                          f"({OPTIONAL_UNITS[unit_key]!r})")

    owed = set(numeric_paths(doc))
    given = set(doc["provenance"])
    for name in sorted(owed - given):
        errors.append(f"provenance: '{name}' has no entry (every number needs a basis)")
    for name in sorted(given - owed):
        errors.append(f"provenance: '{name}' names no number in this document")

    lam = doc.get("laminate")
    if isinstance(lam, dict):
        if bool(la.max_abs(lam["B"])) != lam["coupled"]:
            errors.append("laminate: 'coupled' disagrees with B "
                          f"(max |B| = {la.max_abs(lam['B']):.4g})")
        total = sum(layer["thickness_mm"] for layer in lam["layers"])
        if not math.isclose(total, doc["caliper_mm"], rel_tol=1e-4):
            errors.append(f"laminate: layer thicknesses sum to {total:.6g} mm, "
                          f"caliper_mm is {doc['caliper_mm']:.6g}")

    _notes(doc, notes)
    return result


def _notes(doc: dict, notes: list[str]) -> None:
    t_m = doc["caliper_mm"] / 1000.0
    rho = doc["areal_density_kg_m2"] / t_m
    lo, hi = DENSITY_BAND
    if not lo <= rho <= hi:
        notes.append(f"density: areal density / caliper = {rho:.4g} kg/m³, outside the "
                     f"plausible {lo:g}–{hi:g} kg/m³ of a sheet material")
    m, b = doc["membrane"], doc["bending"]
    nu21 = m["nu12"] * m["E2t"] / m["E1t"]
    plate = m["E1t"] * t_m * t_m / (12.0 * (1.0 - m["nu12"] * nu21))
    ratio = b["D11"] / plate
    lo, hi = PLATE_RATIO_BAND
    if not lo <= ratio <= hi and not doc["regime"]["layered"]:
        notes.append(f"bending: D11 is {ratio:.3g}× the plate value E1t·t²/(12(1−ν12ν21)) "
                     "— this sheet does not bend as a homogeneous plate (expected for "
                     "fabric; check the card if it is paper or film)")
    weakest = {p["status"] for p in doc["provenance"].values()}
    if weakest == {"estimated"}:
        notes.append("provenance: every number is estimated — calibrate before trusting "
                     "a simulation built on it")


def combine_status(*statuses: str) -> str:
    """The status of a value computed from inputs with these statuses.

    ``derived`` only when every input is measured or derived (a formula applied to
    measurements); any estimated input makes the result estimated.
    """
    return "derived" if all(s in ("measured", "derived") for s in statuses) else "estimated"


def provenance(status: str, basis: str) -> dict[str, str]:
    if status not in STATUSES:
        raise ValueError(f"unknown provenance status {status!r}")
    if not basis.strip():
        raise ValueError("a provenance basis must not be empty")
    return {"status": status, "basis": basis}


SIG_DIGITS = 6


def sig(x: float) -> float | int:
    """Round to six significant digits so documents are byte-stable across platforms
    (the convention Pliego's stock derivation uses); integral values become ints so
    the canonical JSON of GOC-1 §3.1 is what gets written."""
    if x == 0 or not math.isfinite(x):
        return 0 if x == 0 else x
    value = float(f"{x:.{SIG_DIGITS}g}")
    return int(value) if value.is_integer() and abs(value) < 1e15 else value


def round_document(obj: Any) -> Any:
    """``sig`` applied to every float in a document (booleans and strings untouched)."""
    if isinstance(obj, bool) or isinstance(obj, str) or obj is None:
        return obj
    if isinstance(obj, float):
        return sig(obj)
    if isinstance(obj, int):
        return obj
    if isinstance(obj, list):
        return [round_document(x) for x in obj]
    if isinstance(obj, dict):
        return {k: round_document(v) for k, v in obj.items()}
    return obj


def skeleton(axis_1: str, caliper_mm: float, areal_density_kg_m2: float) -> dict[str, Any]:
    """A document's fixed head, in the canonical key order."""
    return {
        "sheet_behaviour": VERSION,
        "units": dict(UNITS),
        "axis_1": axis_1,
        "caliper_mm": caliper_mm,
        "areal_density_kg_m2": areal_density_kg_m2,
    }
