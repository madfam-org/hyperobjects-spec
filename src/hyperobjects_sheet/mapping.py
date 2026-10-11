"""Mapping rules: a platform's own material card → a ``sheet_behaviour`` v1 document.

Each platform keeps its card and its engine; these rules are the keystone's reading of
the cards, so a material owned by one platform can be cut, folded, draped or laminated
by another without copying the card. Every number says how far to trust it.

* ``pliego-stock/1`` — a Pliego stock card's **derived** block (``pliego.stock.derive
  v1``, engine units mm·g·s) plus the statuses of the measurements it came from.
* ``fc-fabric/1`` — a Fashion Cabinet fabric card's ``physical`` and
  ``digital_twin.physics``. The card has no physical stiffness, so bend class → D and
  stretch % → membrane stiffness are **estimated** under stated assumptions.
* ``y4d-thin-print/1`` — a Yantra4D filament card plus a thin-print descriptor (layer
  count, layer height, raster pattern, infill), through a classical laminate of the
  layers (``stack.thin_print``). Lives in :mod:`hyperobjects_sheet.stack`.
"""

from __future__ import annotations

import math
from typing import Any

from .behaviour import combine_status, provenance, round_document, skeleton

PLIEGO_DERIVE_BASIS = "pliego.stock.derive v1"
PLIEGO_RULE = "pliego-stock/1"
FC_RULE = "fc-fabric/1"

# Pliego engine units → SI.
_MM = 1e-3            # mm → m
_G_PER_MM2 = 1e3      # g/mm² → kg/m²
_ENGINE_D = 1e-9      # g·mm²/s² → N·m

# Fabric-card assumptions (each one restated in the basis of the number it produces).
GF_CM = 9.80665e-3 / 1e-2          # 1 gf/cm in N/m
#: The KES-FB1 tensile test runs to 500 gf/cm (FAST uses 100 gf/cm); fashion-cabinet's
#: own preset sidecar names both and records that the cards state neither.
ASSUMED_TEST_LOAD_N_M = 500 * GF_CM
#: In-plane shear rigidity, 1 gf/(cm·deg) in N/m per radian: an order of magnitude
#: typical of apparel fabrics in the KES-FB1 shear test, used for every class.
ASSUMED_SHEAR_N_M = 1 * GF_CM / math.radians(1.0)
ASSUMED_FABRIC_NU = 0.3
#: bend_stiffness_class → bending rigidity in gf·cm²/cm (KES-FB2 B). A geometric ladder
#: across the order of magnitude apparel fabrics span (≈0.01–1 gf·cm²/cm), one rung per
#: class, softest → stiffest. A convention of this keystone, not a measurement.
BEND_CLASS_GF_CM2_CM: dict[str, float] = {
    "very-soft": 0.02,
    "soft": 0.04,
    "medium-soft": 0.07,
    "medium": 0.12,
    "medium-stiff": 0.2,
    "stiff": 0.35,
    "very-stiff": 0.6,
}
GF_CM2_CM = 9.80665e-3 * 1e-4 / 1e-2   # 1 gf·cm²/cm in N·m
INEXTENSIBLE_MAX_STRETCH_PCT = 2.0
STRETCHY_MIN_STRETCH_PCT = 10.0


class MappingError(ValueError):
    """A card a rule cannot map; the message says what is missing."""


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


# ------------------------------------------------------------------- Pliego stock card


def _pliego_status(physical: dict, name: str) -> tuple[str, str]:
    """(sheet status, basis text) for one physical measurement of a stock card.

    Pliego's ``nominal`` (a value its maker states, e.g. a grade's g/m²) counts as
    measured here: someone stands behind the number. ``estimated`` stays estimated.
    """
    entry = physical.get(name)
    if not isinstance(entry, dict) or entry.get("status") not in (
        "measured", "nominal", "estimated"
    ):
        return "estimated", f"physical.{name} absent; rule default"
    status = entry["status"]
    why = entry.get("source") or entry.get("basis") or "no source recorded"
    sheet = "estimated" if status == "estimated" else "measured"
    return sheet, f"physical.{name} {status}: {why}"


def map_pliego_stock(card: dict) -> dict[str, Any]:
    """``pliego-stock/1``: a stock card's derived block → ``sheet_behaviour``."""
    stock = card.get("stock") or {}
    slug = stock.get("slug")
    derived = card.get("derived")
    if not isinstance(derived, dict):
        raise MappingError(f"pliego stock {slug!r}: no derived block (run pliego.stock)")
    if card.get("derived_basis") != PLIEGO_DERIVE_BASIS:
        raise MappingError(f"pliego stock {slug!r}: derived_basis "
                           f"{card.get('derived_basis')!r}, this rule reads "
                           f"{PLIEGO_DERIVE_BASIS!r}")
    need = ("thickness", "areal_density", "E_md", "E_cd", "nu", "D_md", "D_cd", "G12",
            "crease_yield_deg", "crease_set_rate", "score_factor", "friction")
    missing = [k for k in need if _num(derived.get(k)) is None]
    if missing:
        raise MappingError(f"pliego stock {slug!r}: derived block lacks {', '.join(missing)}")
    physical = card.get("physical") or {}
    d = {k: float(derived[k]) for k in need}
    t_mm = d["thickness"]
    t = t_mm * _MM
    e1, e2, nu = d["E_md"], d["E_cd"], d["nu"]
    nu12 = nu * math.sqrt(e1 / e2)
    nu21 = nu * math.sqrt(e2 / e1)

    st = {k: _pliego_status(physical, k) for k in (
        "gsm", "caliper_um", "E_md_gpa", "E_cd_gpa", "nu", "crease_length_scale_t",
        "crease_yield_deg", "crease_set_rate", "score_factor", "friction")}
    s = {k: v[0] for k, v in st.items()}
    b = {k: v[1] for k, v in st.items()}
    bend = physical.get("bending_stiffness_mNm") or {}
    bending_measured = _num(bend.get("md")) is not None and _num(bend.get("cd")) is not None

    prov: dict[str, dict[str, str]] = {
        "caliper_mm": provenance(s["caliper_um"], f"derived.thickness; {b['caliper_um']}"),
        "areal_density_kg_m2": provenance(
            s["gsm"], f"derived.areal_density (g/mm²) × 1000; {b['gsm']}"),
        "E1t": provenance(combine_status(s["E_md_gpa"], s["caliper_um"]),
                          f"derived.E_md × t; {b['E_md_gpa']}; {b['caliper_um']}"),
        "E2t": provenance(combine_status(s["E_cd_gpa"], s["caliper_um"]),
                          f"derived.E_cd × t; {b['E_cd_gpa']}; {b['caliper_um']}"),
        "G12t": provenance("estimated", "derived.G12 × t, G12 = 0.387·√(E_md·E_cd) "
                           "(Baum, Brennan & Habeger 1981, via pliego.stock.derive v1)"),
        "nu12": provenance(combine_status(s["nu"], s["E_md_gpa"], s["E_cd_gpa"]),
                           "ν12 = ν·√(E_md/E_cd): the card's ν is the geometric mean "
                           f"√(ν12·ν21), split by reciprocity ν12/E1 = ν21/E2; {b['nu']}"),
    }
    if bending_measured:
        why = f"physical.bending_stiffness_mNm measured ({bend.get('method')}): " \
              f"{bend.get('source')}"
        prov["D11"] = provenance("measured", f"derived.D_md × 1e-9 (N·m); {why}")
        prov["D22"] = provenance("measured", f"derived.D_cd × 1e-9 (N·m); {why}")
    else:
        for key, src, e_key in (("D11", "D_md", "E_md_gpa"), ("D22", "D_cd", "E_cd_gpa")):
            prov[key] = provenance(
                combine_status(s[e_key], s["nu"], s["caliper_um"]),
                f"derived.{src} × 1e-9 (N·m), plate E·t³/(12(1−ν²)) in pliego.stock.derive "
                f"v1; {b[e_key]}; {b['nu']}; {b['caliper_um']}")
    prov["D12"] = provenance(combine_status(prov["D11"]["status"], s["nu"]),
                             "ν21·D11, orthotropic plate (ν21 = ν·√(E_cd/E_md))")
    prov["D66"] = provenance("estimated", "G12·t³/12 with the estimated G12 above")
    for key in ("crease_length_scale_t", "crease_yield_deg", "crease_set_rate",
                "score_factor"):
        why = b[key]
        if key in ("crease_set_rate", "score_factor") and key not in physical:
            why = f"pliego.stock.derive v1 default (card has no physical.{key})"
        prov[key] = provenance(s[key], why)
    prov["friction_static"] = provenance(s["friction"], b["friction"])

    lt = _num((physical.get("crease_length_scale_t") or {}).get("value"))
    if lt is None:
        raise MappingError(f"pliego stock {slug!r}: physical.crease_length_scale_t missing")
    notes = [
        "friction: the card states one paper-on-paper coefficient; it is written as "
        "friction_static, and friction_kinetic and damping are left out rather than "
        "invented",
    ]
    crease_k = _num(derived.get("crease_k"))
    if crease_k:
        implied = math.sqrt(d["D_md"] * d["D_cd"]) / (crease_k * t_mm)
        if not math.isclose(implied, lt, rel_tol=1e-4):
            notes.append(f"crease: derived.crease_k implies L*/t = {implied:.6g}, the card "
                         f"states {lt:g}")

    doc = skeleton("isotropic" if e1 == e2 else "machine", t_mm, d["areal_density"] * _G_PER_MM2)
    doc["source"] = {"platform": "pliego", "material_slug": slug, "rule": PLIEGO_RULE,
                     "card_basis": PLIEGO_DERIVE_BASIS}
    doc["membrane"] = {"E1t": e1 * t, "E2t": e2 * t, "G12t": d["G12"] * t, "nu12": nu12}
    doc["bending"] = {
        "D11": d["D_md"] * _ENGINE_D,
        "D22": d["D_cd"] * _ENGINE_D,
        "D12": nu21 * d["D_md"] * _ENGINE_D,
        "D66": d["G12"] * t ** 3 / 12.0,
    }
    doc["crease"] = {
        "crease_length_scale_t": lt,
        "crease_yield_deg": d["crease_yield_deg"],
        "crease_set_rate": d["crease_set_rate"],
        "score_factor": d["score_factor"],
    }
    doc["regime"] = {"inextensible": True, "stretchy": False, "compressible": False,
                     "layered": False, "self_folding": False}
    doc["contact"] = {"friction_static": d["friction"]}
    doc["provenance"] = prov
    doc["notes"] = notes
    return round_document(doc)


# ------------------------------------------------------------------ FC fabric card


def map_fc_fabric(card: dict) -> dict[str, Any]:
    """``fc-fabric/1``: a fabric card's physical + digital_twin.physics → ``sheet_behaviour``.

    The card carries no physical stiffness (fashion-cabinet declines to invent one from a
    bare elongation, because the test load is not recorded). This rule does produce one,
    because a sheet engine needs it, and marks every such number ``estimated`` with the
    assumption that produced it.
    """
    fabric = card.get("fabric") or {}
    slug = fabric.get("slug")
    physical = card.get("physical") or {}
    physics = (card.get("digital_twin") or {}).get("physics") or {}
    stretch = physical.get("stretch_pct") or {}

    def pick(twin_key: str, phys: Any) -> float | None:
        v = _num(physics.get(twin_key))
        return v if v is not None else _num(phys)

    gsm = pick("weight_gsm", physical.get("gsm"))
    warp = pick("stretch_warp_pct", stretch.get("warp"))
    weft = pick("stretch_weft_pct", stretch.get("weft"))
    t_mm = _num(physical.get("thickness_mm"))
    bend_class = physics.get("bend_stiffness_class")
    missing = [n for n, v in (("weight_gsm/gsm", gsm), ("stretch warp", warp),
                              ("stretch weft", weft), ("thickness_mm", t_mm)) if not v]
    if missing:
        raise MappingError(f"fc fabric {slug!r}: needs positive {', '.join(missing)}")
    if bend_class not in BEND_CLASS_GF_CM2_CM:
        raise MappingError(f"fc fabric {slug!r}: bend_stiffness_class {bend_class!r} is not "
                           f"one of {', '.join(BEND_CLASS_GF_CM2_CM)}")

    nu = ASSUMED_FABRIC_NU
    d_class = BEND_CLASS_GF_CM2_CM[bend_class] * GF_CM2_CM
    card_note = "fabric-card v1 records no test method; fashion-cabinet's preset " \
                "sidecar treats card values as measured"
    load = (f"secant: assumed test load 500 gf/cm = {ASSUMED_TEST_LOAD_N_M:.2f} N/m (the "
            "KES-FB1 tensile maximum; FAST's 100 gf/cm would give 5× less) ÷ the card's "
            "stretch strain; the card does not record the load its stretch % was "
            "measured under")
    ladder = (f"bend_stiffness_class {bend_class!r} → {BEND_CLASS_GF_CM2_CM[bend_class]} "
              "gf·cm²/cm (KES-FB2 B) on the keystone's geometric ladder across ≈0.01–1 "
              "gf·cm²/cm; one class for both directions")

    doc = skeleton("wale" if fabric.get("class") == "knit" else "warp", t_mm, gsm / 1000.0)
    doc["source"] = {"platform": "fashion-cabinet", "material_slug": slug, "rule": FC_RULE,
                     "card_basis": "fabric-card v1"}
    doc["membrane"] = {
        "E1t": ASSUMED_TEST_LOAD_N_M / (warp / 100.0),
        "E2t": ASSUMED_TEST_LOAD_N_M / (weft / 100.0),
        "G12t": ASSUMED_SHEAR_N_M,
        "nu12": nu,
    }
    doc["bending"] = {
        "D11": d_class,
        "D22": d_class,
        "D12": nu * d_class,
        "D66": (1.0 - nu) / 2.0 * d_class,
    }
    biggest = max(warp, weft)
    stretchy = biggest >= STRETCHY_MIN_STRETCH_PCT
    doc["regime"] = {"inextensible": biggest <= INEXTENSIBLE_MAX_STRETCH_PCT,
                     "stretchy": stretchy, "compressible": False, "layered": False,
                     "self_folding": False}
    doc["provenance"] = {
        "caliper_mm": provenance("measured", f"card physical.thickness_mm; {card_note}"),
        "areal_density_kg_m2": provenance(
            "measured", f"card weight_gsm / 1000; {card_note}"),
        "E1t": provenance("estimated", f"{load}; warp {warp:g} %"),
        "E2t": provenance("estimated", f"{load}; weft {weft:g} %"),
        "G12t": provenance("estimated", "assumed shear rigidity 1 gf/(cm·deg) "
                           f"(= {ASSUMED_SHEAR_N_M:.2f} N/m), an order of magnitude typical "
                           "of apparel fabrics in KES-FB1; the card has no shear datum"),
        "nu12": provenance("estimated", f"assumed ν12 = {nu:g}; fabric Poisson ratios vary "
                           "widely and the card records none"),
        "D11": provenance("estimated", ladder),
        "D22": provenance("estimated", ladder),
        "D12": provenance("estimated", f"isotropic plate relation ν·D with ν = {nu:g}"),
        "D66": provenance("estimated", f"isotropic plate relation (1−ν)/2·D with ν = {nu:g}"),
    }
    notes = [
        "contact: the card records no friction or damping; the contact block is left out "
        "rather than invented",
        f"regime: inextensible when the larger stretch is ≤ {INEXTENSIBLE_MAX_STRETCH_PCT:g} "
        f"%, stretchy when it is ≥ {STRETCHY_MIN_STRETCH_PCT:g} % (keystone convention)",
    ]
    if _num(physical.get("gsm")) not in (None, gsm):
        notes.append(f"areal density: digital_twin weight_gsm {gsm:g} differs from "
                     f"physical.gsm {physical.get('gsm')}; the twin value is used, as "
                     "fashion-cabinet's own preset sidecar does")
    if fabric.get("class") == "printed_textile":
        notes.append("printed textile: the solid is a Yantra4D cartridge; this is the "
                     "card's cloth reading of it, not a laminate of the print "
                     "(see y4d-thin-print/1)")
    doc["notes"] = notes
    return round_document(doc)
