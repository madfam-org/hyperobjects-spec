"""The soft (Fashion Cabinet) projection: one garment cartridge -> one AAS Environment.

Submodels (SEM-1 §5): Nameplate, ParametricModel (with the ISO 8559 measurement codes),
PatternProvision, SeamInterfaces, Fabrics, HardwareLinks — plus RequirementProfile when
the garment carries the SEM-1 §3 ``requirements`` block (no garment does yet). Soft
interfaces stay 2-D seams: there are no frames on this side.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from hyperobjects_lexicon import load_vocabulary
from hyperobjects_schemas.generator_output import tree_sha256

from . import elements as el
from .common import (
    GOC_CONTRACT,
    GOC_FORMAT,
    PLATFORMS,
    Projection,
    as_dict,
    as_list,
    build_environment,
    nameplate,
    parametric_model,
)
from .concepts import Concepts
from .ids import IdShortAllocator, asset_id, material_asset_id
from .solid import requirements_elements

__all__ = ["project_soft", "build_soft_environment"]

#: The hardware_ref platform whose slugs are solid type assets.
_SOLID_PLATFORM = "yantra4d"


def pattern_provision(proj: Projection) -> None:
    m, platform = proj.manifest, PLATFORMS["soft"]
    pieces = {p["id"]: p for p in as_list(m.get("pieces"))
              if isinstance(p, dict) and isinstance(p.get("id"), str)}
    alloc = IdShortAllocator()
    modes = [
        el.smc(alloc.take(mode.get("id"), "Mode"), [
            el.prop("ModeId", mode.get("id")),
            el.mlp("Label", mode.get("label")),
            el.sml("Pieces", [el.prop(None, p) for p in as_list(mode.get("pieces"))
                              if isinstance(p, str)], type_value="Property"),
        ], semantic_id=proj.concepts.term("mode"))
        for mode in as_list(m.get("modes")) if isinstance(mode, dict)
    ]
    piece_alloc = IdShortAllocator()
    piece_els = []
    for pid, piece in pieces.items():
        cut = as_dict(piece.get("cut"))
        piece_els.append(el.smc(piece_alloc.take(pid, "Piece"), [
            el.prop("PieceId", pid),
            el.mlp("Label", piece.get("label")),
            el.smc("Cut", [
                el.prop("Quantity", cut.get("quantity"), prefer="xs:integer"),
                el.prop("Mirror", cut.get("mirror")),
                el.prop("OnFold", cut.get("on_fold")),
                el.prop("FoldEdge", cut.get("fold_edge")),
            ]),
        ]))
    formats = [f for f in as_list(m.get("export_formats")) if isinstance(f, str)]
    proj.add("PatternProvision", [
        el.prop("Platform", platform["platform"]),
        el.prop("RenderEndpoint", platform["render_endpoint"], prefer="xs:anyURI"),
        el.prop("GeneratorOutputContract", GOC_CONTRACT),
        el.prop("GeneratorOutputFormat", GOC_FORMAT),
        el.prop("ProjectEngine", proj.project.get("engine")),
        el.prop("LengthUnit", "mm"),
        el.sml("ProducibleFormats", [el.prop(None, f) for f in formats], type_value="Property",
               semantic_id=proj.concepts.term("export-format")),
        el.smc("Modes", modes),
        el.smc("Pieces", piece_els),
    ], "pattern-provision")


@cache
def _interface_terms() -> dict[str, str]:
    doc = load_vocabulary("interfaces")
    return {
        e["key"]: e["term"] for e in doc.get("entries", [])
        if e.get("repo") == "fashion-cabinet" and e.get("role") == "interface_type"
        and e.get("term")
    }


def seam_interfaces(proj: Projection) -> None:
    terms = _interface_terms()
    alloc = IdShortAllocator()
    out = []
    for iface in as_list(proj.hyperobject.get("interfaces")):
        if not isinstance(iface, dict):
            continue
        edges = [
            el.smc(None, [el.prop("Piece", e.get("piece")), el.prop("Edge", e.get("edge"))])
            for e in as_list(iface.get("edges")) if isinstance(e, dict)
        ]
        itype = iface.get("type")
        out.append(el.smc(alloc.take(iface.get("id"), "Interface"), [
            el.prop("InterfaceId", iface.get("id")),
            el.mlp("Label", iface.get("label")),
            el.prop("Type", itype, semantic_id=proj.concepts.term(terms.get(itype))),
            el.prop("GeometryType", iface.get("geometry_type")),
            el.sml("Edges", edges, type_value="SubmodelElementCollection"),
            *proj.param_refs("Parameters", iface.get("parameters")),
        ]))
    proj.add("SeamInterfaces", out, "seam-interfaces")


def _slug_ok(slug: object, make) -> bool:
    if not isinstance(slug, str):
        return False
    try:
        make(slug)
    except ValueError:
        return False
    return True


def fabrics(proj: Projection) -> None:
    refs = [
        el.reference_element(None, el.external_ref(material_asset_id(slug)))
        for slug in as_list(proj.manifest.get("fabrics")) if _slug_ok(slug, material_asset_id)
    ]
    proj.add("Fabrics", [el.sml("FabricMaterials", refs, type_value="ReferenceElement")],
             "fabrics")


def hardware_links(proj: Projection) -> None:
    notion = as_dict(proj.manifest.get("notion"))
    if not notion:
        return
    ref = as_dict(notion.get("hardware_ref"))
    mapping = [
        el.smc(None, [el.prop("Parameter", k), el.prop("Expression", v)])
        for k, v in sorted(as_dict(ref.get("params_map")).items())
    ]
    target = ref.get("project_slug")
    linked = ref.get("linked") is True
    realised_by = None
    if linked and ref.get("platform") == _SOLID_PLATFORM and _slug_ok(target, lambda s: asset_id(
            "solid", s)):
        realised_by = el.relationship(
            "RealisedBy",
            el.external_ref(asset_id("soft", proj.slug)),
            el.external_ref(asset_id("solid", target)),
            semantic_id=proj.concepts.term("hardware-ref"),
        )
    hardware = el.smc("HardwareRef", [
        el.prop("Platform", ref.get("platform")),
        el.prop("ProjectSlug", target),
        el.prop("Linked", ref.get("linked")),
        el.sml("ParamsMap", mapping, type_value="SubmodelElementCollection",
               semantic_id=proj.concepts.term("params-map")),
        realised_by,
    ], semantic_id=proj.concepts.term("hardware-ref")) if ref else None
    proj.add("HardwareLinks", [
        el.smc("Notion", [el.prop("Kind", notion.get("kind")),
                          el.prop("Subtype", notion.get("subtype"))],
               semantic_id=proj.concepts.term("notion")),
        hardware,
    ], "hardware-links")


def project_soft(cartridge_dir: str | Path, manifest: dict | None = None,
                 concepts: Concepts | None = None) -> Projection:
    """Project one soft cartridge directory. Raises ValueError on a missing slug."""
    root = Path(cartridge_dir)
    if manifest is None:
        manifest = json.loads((root / "project.json").read_text(encoding="utf-8"))
    slug = as_dict(manifest.get("project")).get("slug")
    if not isinstance(slug, str):
        raise ValueError(f"{root}: project.slug is missing")
    proj = Projection("soft", slug, tree_sha256(root), manifest,
                      concepts if concepts is not None else Concepts())
    nameplate(proj)
    parametric_model(proj)
    pattern_provision(proj)
    req = as_dict(manifest.get("requirements"))
    if req:
        proj.add("RequirementProfile", requirements_elements(req), "requirement-profile",
                 "process-parameters-type")
    seam_interfaces(proj)
    fabrics(proj)
    hardware_links(proj)
    return proj


def build_soft_environment(cartridge_dir: str | Path) -> dict:
    return build_environment(project_soft(cartridge_dir))
