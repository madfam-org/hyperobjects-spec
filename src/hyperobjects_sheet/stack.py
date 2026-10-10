"""Stacks: laminate documents and thin prints → classical laminate → ``sheet_behaviour``.

A **laminate document** names its layers bottom first. Each layer is one of

* ``{"material_ref": {platform, material_slug, behaviour: "sheet"}}`` — resolved against
  the supplied materials directories (:mod:`hyperobjects_sheet.resolve`);
* ``{"sheet": {…a sheet_behaviour document…}}`` — a local stock written inline;
* ``{"lamina": {name, E1_pa, E2_pa, G12_pa, nu12, density_kg_m3}}`` — textbook constants;

with ``angle_deg`` (default 0), ``thickness_mm`` (default: the card's caliper; required
for a lamina), and optionally ``prestrain`` ``[e1, e2, g12]`` in laminate axes and
``own_bending`` (``card`` | ``plate``).

A **thin-print descriptor** (rule ``y4d-thin-print/1``) is a Yantra4D filament card plus
the print: layer count, layer height, rectilinear raster angles cycled per layer and the
infill fraction. Each layer becomes a lamina whose bead direction carries the filament's
in-plane (X-Y) modulus and whose cross-bead direction carries the Z modulus, both scaled
by infill — every step an estimate, and each one said so in the basis.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import laminate as lam
from .behaviour import (
    OPTIONAL_UNITS,
    combine_status,
    material_ref_errors,
    provenance,
    round_document,
    skeleton,
    validate,
)

THIN_PRINT_RULE = "y4d-thin-print/1"
LAMINATE_RULE = "laminate/1"

#: Filament constants the Yantra4D cards do not carry yet, each with its public source.
#: A thin-print descriptor may override any of them under ``filament``.
FILAMENTS: dict[str, dict[str, Any]] = {
    "bambu-tpu-95a": {
        "E_xy_mpa": 9.8,
        "E_z_mpa": 7.4,
        "density_kg_m3": 1220.0,
        "nu": 0.45,
        "source": (
            "Bambu Lab, TPU 95A HF Technical Data Sheet V1.0: Young's modulus X-Y 9.8 ± 0.7 "
            "MPa and Z 7.4 ± 0.6 MPa (ISO 527), density 1.22 g/cm³ (ISO 1183) — "
            "https://store.bblcdn.com/58df32731eab4c90a7dac9b12e13ba88.pdf; that sheet is "
            "the HF grade, the card names TPU 95A"
        ),
        "nu_basis": "assumed ν = 0.45: a 95A elastomer is nearly incompressible (ν → 0.5) "
                    "and printed voids lower it; no datasheet states it",
    },
}

Resolver = Callable[[dict], dict]


class StackError(ValueError):
    """A laminate document or thin-print descriptor that cannot be computed."""


def _positive(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not (
        math.isfinite(value) and value > 0
    ):
        raise StackError(f"{what} must be a positive number, got {value!r}")
    return float(value)


def layer_from_behaviour(name: str, doc: dict, angle_deg: float, thickness_mm: float | None,
                         prestrain: Any = None, own_bending: str | None = None
                         ) -> tuple[lam.Layer, list[str], list[str]]:
    """A laminate layer from a ``sheet_behaviour`` document; returns (layer, statuses, notes).

    Moduli are the document's membrane stiffness over its caliper. A thickness other than
    the caliper keeps the moduli and rescales the stiffness (a note says so).
    """
    check = validate(doc)
    if not check.ok:
        raise StackError(f"layer {name!r}: its sheet_behaviour is invalid: "
                         + "; ".join(check.errors[:3]))
    cal = doc["caliper_mm"]
    t_mm = cal if thickness_mm is None else _positive(thickness_mm, f"{name}: thickness_mm")
    notes = []
    if not math.isclose(t_mm, cal, rel_tol=1e-9):
        notes.append(f"layer {name}: thickness {t_mm:g} mm differs from its caliper {cal:g} mm; "
                     "moduli are held and the stiffness rescaled")
    cal_m = cal * 1e-3
    m = doc["membrane"]
    mode = own_bending or "card"
    if mode not in ("card", "plate"):
        raise StackError(f"layer {name!r}: own_bending must be 'card' or 'plate'")
    own = None
    if mode == "card":
        b = doc["bending"]
        k = (t_mm / cal) ** 3   # a card's bending belongs to its caliper; rescale as t³
        d16, d26 = b.get("D16", 0.0), b.get("D26", 0.0)
        own = [[k * b["D11"], k * b["D12"], k * d16], [k * b["D12"], k * b["D22"], k * d26],
               [k * d16, k * d26, k * b["D66"]]]
    layer = lam.Layer(
        name=name, E1=m["E1t"] / cal_m, E2=m["E2t"] / cal_m, G12=m["G12t"] / cal_m,
        nu12=m["nu12"], thickness=t_mm * 1e-3, angle_deg=float(angle_deg),
        own_bending=own, prestrain=_prestrain(prestrain, name),
        areal_density=doc["areal_density_kg_m2"] * t_mm / cal,
    )
    statuses = [p["status"] for k, p in doc["provenance"].items()
                if k in ("E1t", "E2t", "G12t", "nu12", "caliper_mm", "areal_density_kg_m2")
                or (mode == "card" and k.startswith("D"))]
    return layer, statuses, notes


def _prestrain(value: Any, name: str) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if (not isinstance(value, list) or len(value) != 3
            or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value)):
        raise StackError(f"layer {name!r}: prestrain must be [e1, e2, g12]")
    return (float(value[0]), float(value[1]), float(value[2]))


def layer_from_lamina(spec: dict, angle_deg: float, thickness_mm: Any,
                      prestrain: Any = None) -> lam.Layer:
    name = str(spec.get("name") or "lamina")
    t = _positive(thickness_mm, f"lamina {name}: thickness_mm")
    rho = spec.get("density_kg_m3")
    return lam.Layer(
        name=name,
        E1=_positive(spec.get("E1_pa"), f"lamina {name}: E1_pa"),
        E2=_positive(spec.get("E2_pa"), f"lamina {name}: E2_pa"),
        G12=_positive(spec.get("G12_pa"), f"lamina {name}: G12_pa"),
        nu12=float(spec.get("nu12", 0.0)),
        thickness=t * 1e-3, angle_deg=float(angle_deg),
        prestrain=_prestrain(prestrain, name),
        areal_density=None if rho is None else _positive(rho, f"{name}: density") * t * 1e-3,
    )


@dataclass
class StackBuild:
    """A computed stack: the laminate, one record per layer, the provenance statuses of
    every input that entered it, mapping notes, and the regime its layers agree on."""

    result: lam.LaminateResult
    records: list[dict]
    statuses: list[str]
    notes: list[str] = field(default_factory=list)
    regime: dict[str, bool] = field(default_factory=dict)


def build_laminate(doc: dict, resolver: Resolver | None = None) -> StackBuild:
    """Compute a laminate document (see the module docstring)."""
    layers_in = doc.get("layers")
    if not isinstance(layers_in, list) or not layers_in:
        raise StackError("a laminate document needs a non-empty 'layers' list")
    layers, records, statuses, notes = [], [], [], []
    regimes: list[dict | None] = []   # None: a lamina, whose regime nobody stated
    for i, spec in enumerate(layers_in):
        if not isinstance(spec, dict):
            raise StackError(f"layers[{i}] must be an object")
        angle = spec.get("angle_deg", 0.0)
        if isinstance(angle, bool) or not isinstance(angle, (int, float)):
            raise StackError(f"layers[{i}]: angle_deg must be a number")
        kinds = [k for k in ("material_ref", "sheet", "lamina") if k in spec]
        if len(kinds) != 1:
            raise StackError(f"layers[{i}]: give exactly one of material_ref, sheet, lamina")
        kind = kinds[0]
        if kind == "lamina":
            layer = layer_from_lamina(spec["lamina"], angle, spec.get("thickness_mm"),
                                      spec.get("prestrain"))
            label = f"lamina:{layer.name}"
            statuses.append("measured" if spec["lamina"].get("measured") else "estimated")
            regimes.append(None)
        else:
            if kind == "material_ref":
                ref = spec["material_ref"]
                errs = material_ref_errors(ref)
                if errs:
                    raise StackError(f"layers[{i}]: " + "; ".join(errs))
                if resolver is None:
                    raise StackError(f"layers[{i}]: a material_ref needs materials "
                                     "directories to resolve against")
                try:
                    behaviour = resolver(ref)
                except ValueError as exc:
                    raise StackError(f"layers[{i}]: {exc}") from exc
                label = f"{ref['platform']}/{ref['material_slug']}"
            else:
                behaviour = spec["sheet"]
                label = f"local:{spec.get('name') or i}"
            layer, st, ns = layer_from_behaviour(
                label, behaviour, angle, spec.get("thickness_mm"), spec.get("prestrain"),
                spec.get("own_bending"))
            statuses.extend(st)
            notes.extend(ns)
            regimes.append(behaviour["regime"])
        layers.append(layer)
        rec = {"material": label, "angle_deg": float(angle),
               "thickness_mm": layer.thickness * 1e3, "own_bending": layer.bending_source}
        if layer.prestrain is not None:
            rec["prestrain"] = list(layer.prestrain)
        records.append(rec)
    try:
        result = lam.laminate(layers)
    except ValueError as exc:
        raise StackError(str(exc)) from exc
    known = [r for r in regimes if r is not None]
    agreed = len(known) == len(regimes)
    regime = {flag: agreed and all(r[flag] for r in known)
              for flag in ("inextensible", "stretchy")}
    return StackBuild(result, records, statuses, notes + result.notes, regime)


def laminate_behaviour(doc: dict, resolver: Resolver | None = None) -> dict[str, Any]:
    """A laminate document → its ``sheet_behaviour`` (rule ``laminate/1``)."""
    build = build_laminate(doc, resolver)
    name = doc.get("name")
    source = None
    if isinstance(name, str) and name:
        source = {"platform": "hyperobjects-spec", "material_slug": name,
                  "rule": LAMINATE_RULE}
    return behaviour_from_laminate(
        build, axis_1="laminate", source=source,
        basis=f"laminate document {name!r}, {len(build.records)} layers")


def behaviour_from_laminate(build: StackBuild, *, axis_1: str, source: dict | None,
                            basis: str) -> dict[str, Any]:
    """The ``sheet_behaviour`` of a computed stack (membrane of the free stack, bending
    D* = D − B·A⁻¹·B; see ``LaminateResult.effective``). The stack is inextensible
    (or stretchy) only when every layer says so; a lamina states no regime."""
    result, records, statuses, notes = build.result, build.records, build.statuses, build.notes
    masses = [layer.areal_density for layer in result.layers]
    if any(m is None for m in masses):
        raise StackError("every layer needs a density (lamina: density_kg_m3) to give the "
                         "stack an areal density")
    eff = result.effective()
    doc = skeleton(axis_1, result.thickness * 1e3, sum(masses))
    doc["units"]["laminate"] = OPTIONAL_UNITS["laminate"]
    if result.prestrain_curvature is not None:
        doc["units"]["curvature"] = OPTIONAL_UNITS["curvature"]
    if source:
        doc["source"] = source
    doc["membrane"] = {k: eff[k] for k in ("E1t", "E2t", "G12t", "nu12")}
    bending = {k: eff[k] for k in ("D11", "D22", "D12", "D66")}
    for k in ("D16", "D26"):
        if abs(eff[k]) > 1e-6 * min(eff["D11"], eff["D22"]):
            bending[k] = eff[k]
    doc["bending"] = bending
    regime = {"inextensible": False, "stretchy": False, "compressible": False,
              "layered": True, "self_folding": False}
    regime.update(build.regime)
    doc["regime"] = regime
    block: dict[str, Any] = {"layers": records, "A": result.A, "B": result.B, "D": result.D,
                             "coupled": result.coupled,
                             "coupling_ratio": result.coupling_ratio}
    if result.prestrain_curvature is not None:
        block["prestrain_response"] = {"midplane_strain": result.prestrain_strain,
                                       "curvature_1_m": result.prestrain_curvature}
    doc["laminate"] = block
    status = combine_status(*statuses) if statuses else "estimated"
    prov = {}
    for key in ("caliper_mm", "areal_density_kg_m2"):
        prov[key] = provenance(status, f"sum over the layers; {basis}")
    for key in list(doc["membrane"]) + list(bending):
        prov[key] = provenance(status, f"classical laminate theory "
                               f"(hyperobjects_sheet.laminate), free stack; {basis}")
    doc["provenance"] = prov
    doc["notes"] = notes + ["crease and contact are not computed for a stack: a laminate's "
                            "crease is not its layers' creases"]
    return round_document(doc)


def thin_print(descriptor: dict, card: dict) -> dict[str, Any]:
    """``y4d-thin-print/1``: a Yantra4D filament card + print descriptor → ``sheet_behaviour``."""
    ref = descriptor.get("material_ref")
    errs = material_ref_errors(ref)
    if errs:
        raise StackError("thin print: " + "; ".join(errs))
    if ref["platform"] != "yantra4d":
        raise StackError("thin print: material_ref.platform must be 'yantra4d'")
    slug = ref["material_slug"]
    material = card.get("material") or {}
    if material.get("slug") != slug:
        raise StackError(f"thin print: card slug {material.get('slug')!r} is not {slug!r}")
    count = descriptor.get("layers")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise StackError("thin print: 'layers' must be a positive integer")
    h = _positive(descriptor.get("layer_height_mm"), "thin print: layer_height_mm")
    infill = _positive(descriptor.get("infill", 1.0), "thin print: infill")
    if infill > 1:
        raise StackError("thin print: infill is a fraction in (0, 1]")
    if descriptor.get("pattern") != "rectilinear":
        raise StackError(f"thin print: pattern {descriptor.get('pattern')!r} has no "
                         "effective-moduli rule (only 'rectilinear' does)")
    angles = descriptor.get("raster_angles_deg")
    if not isinstance(angles, list) or not angles or not all(
        isinstance(a, (int, float)) and not isinstance(a, bool) for a in angles
    ):
        raise StackError("thin print: raster_angles_deg must be a non-empty list of numbers")
    fil = dict(FILAMENTS.get(slug, {}))
    fil.update(descriptor.get("filament") or {})
    for key in ("E_xy_mpa", "E_z_mpa", "density_kg_m3", "nu"):
        if key not in fil:
            raise StackError(f"thin print: no {key} for filament {slug!r} (the card does not "
                             "carry it; give it under 'filament')")
    e_l = _positive(fil["E_xy_mpa"], "E_xy_mpa") * 1e6 * infill
    e_t = _positive(fil["E_z_mpa"], "E_z_mpa") * 1e6 * infill
    nu = float(fil["nu"])
    g = math.sqrt(e_l * e_t) / (2.0 * (1.0 + nu))
    rho = _positive(fil["density_kg_m3"], "density_kg_m3")
    layers = [
        lam.Layer(name=f"layer-{k + 1}", E1=e_l, E2=e_t, G12=g, nu12=nu, thickness=h * 1e-3,
                  angle_deg=float(angles[k % len(angles)]), areal_density=rho * infill * h * 1e-3)
        for k in range(count)
    ]
    result = lam.laminate(layers)
    records = [{"material": f"yantra4d/{slug}", "angle_deg": layer.angle_deg,
                "thickness_mm": h, "own_bending": "plate"} for layer in layers]
    basis = (f"{count} layers × {h:g} mm, rectilinear rasters {angles} (cycled), infill "
             f"{infill:g}; lamina: bead direction E = infill × E_xy, cross-bead E = infill × "
             "E_z (the inter-layer bond standing in for the inter-bead bond), "
             "G = √(E_L·E_T)/(2(1+ν)), linear in infill (an upper bound for sparse fill); "
             f"{fil.get('source', 'filament constants given in the descriptor')}; "
             f"{fil.get('nu_basis', 'ν given in the descriptor')}")
    notes = [
        "perimeters and walls are ignored: the print is treated as its raster infill",
    ]
    wall = _min_wall(card)
    if wall is not None and count * h < wall - 1e-9:
        notes.append(f"thickness {count * h:g} mm is below the card's minimum wall "
                     f"{wall:g} mm")
    emmo = ((card.get("semantic_ontology") or {}).get("emmo_class") or "")
    stretchy = emmo.endswith("Elastomer")
    if stretchy:
        notes.append("crease: an elastomer print recovers rather than creases; no crease "
                     "block")
    source = {"platform": "yantra4d", "material_slug": slug, "rule": THIN_PRINT_RULE,
              "card_basis": "yantra4d material card"}
    build = StackBuild(result, records, ["estimated"], notes + result.notes,
                       {"stretchy": stretchy})
    return behaviour_from_laminate(build, axis_1="print", source=source, basis=basis)


def _min_wall(card: dict) -> float | None:
    feats = ((card.get("am_compensations") or {}).get("minimum_features") or {})
    v = feats.get("wall_thickness")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
