"""The solid (yantra4d) projection: one cartridge directory -> one AAS Environment.

Submodels (SEM-1 §5): Nameplate, ParametricModel, GeometryProvision, RequirementProfile,
MatingInterfaces, BillOfMaterials. A submodel with nothing truthful to say is omitted
(a cartridge with no interfaces has no MatingInterfaces), never emitted empty.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from hyperobjects_schemas.generator_output import tree_sha256
from y4d_spec.geometry import mode_sources

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
from .ids import IdShortAllocator, asset_id, standard_part_id
from .ids import id_short as el_id_short
from .templates import IDTA

__all__ = ["project_solid", "build_solid_environment"]

#: Engines whose kernel is B-rep, so STEP is producible (SEM-1 §5.3).
_BREP_ENGINES = frozenset({"cadquery", "graph"})
_STEP = "step"


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _platform_engine(mode: dict, project: dict) -> str | None:
    """The engine the platform renders a mode with: ``mode.engine``, else the source
    suffix of ``scad_file``, else ``project.engine`` (yantra4d ``manifest.py::mode_engine``)."""
    if _str(mode.get("engine")):
        return mode["engine"]
    by_suffix = mode_sources({"scad_file": mode.get("scad_file")})
    if by_suffix:
        return by_suffix[0][0]
    return _str(project.get("engine"))


def geometry_provision(proj: Projection) -> None:
    m, project = proj.manifest, proj.project
    platform = PLATFORMS["solid"]
    formats = [f for f in as_list(m.get("export_formats")) if isinstance(f, str)]
    parts = {p["id"]: p for p in as_list(m.get("parts"))
             if isinstance(p, dict) and isinstance(p.get("id"), str)}
    alloc = IdShortAllocator()
    modes = []
    for mode in as_list(m.get("modes")):
        if not isinstance(mode, dict):
            continue
        engines = sorted({eng for eng, _ in mode_sources(mode)})
        platform_engine = _platform_engine(mode, project)
        brep = bool(_BREP_ENGINES & (set(engines) | {platform_engine}))
        producible = [f for f in formats if f != _STEP or brep]
        quantities = as_dict(mode.get("part_quantities"))
        part_list = []
        for pid in as_list(mode.get("parts")):
            if not isinstance(pid, str):
                continue
            part = as_dict(parts.get(pid))
            part_list.append(el.smc(None, [
                el.prop("PartId", pid),
                el.mlp("Label", part.get("label")),
                el.prop("Quantity", quantities.get(pid), prefer="xs:integer"),
                el.prop("RenderMode", part.get("render_mode"), prefer="xs:integer"),
            ]))
        modes.append(el.smc(alloc.take(mode.get("id"), "Mode"), [
            el.prop("ModeId", mode.get("id")),
            el.mlp("Label", mode.get("label")),
            el.prop("Engine", platform_engine),
            el.sml("SourceEngines", [el.prop(None, e) for e in engines], type_value="Property"),
            el.sml("ProducibleFormats", [el.prop(None, f) for f in producible],
                   type_value="Property", semantic_id=proj.concepts.term("export-format")),
            el.sml("Parts", part_list, type_value="SubmodelElementCollection"),
        ], semantic_id=proj.concepts.term("mode")))
    proj.add("GeometryProvision", [
        el.prop("Platform", platform["platform"]),
        el.prop("RenderEndpoint", platform["render_endpoint"], prefer="xs:anyURI"),
        el.prop("GeneratorOutputContract", GOC_CONTRACT),
        el.prop("GeneratorOutputFormat", GOC_FORMAT),
        el.prop("ProjectEngine", project.get("engine")),
        el.prop("LengthUnit", "mm"),
        el.smc("Modes", modes),
    ], "geometry-provision", "models3d")


def _bound(id_short: str, key: str, spec: object) -> dict | None:
    """One process-parameter bound: ``{min?, max?, value?, unit?}`` or a bare scalar."""
    if not isinstance(spec, dict):
        return el.smc(id_short, [el.prop("ParameterKey", key), el.prop("Value", spec)])
    return el.smc(id_short, [
        el.prop("ParameterKey", key),
        el.prop("Min", spec.get("min"), prefer="xs:double"),
        el.prop("Max", spec.get("max"), prefer="xs:double"),
        el.prop("Value", spec.get("value")),
        el.prop("Unit", spec.get("unit")),
    ])


def _string_list(id_short: str, values: object) -> dict | None:
    return el.sml(id_short, [el.prop(None, v) for v in as_list(values) if isinstance(v, str)],
                  type_value="Property", value_type="xs:string")


def _materials(spec: object) -> dict | None:
    spec = as_dict(spec)
    return el.smc("Materials", [_string_list("AnyOf", spec.get("any_of")),
                                _string_list("NoneOf", spec.get("none_of"))])


def requirements_elements(req: dict) -> list:
    """The SEM-1 §2.4 ``requirements`` block as elements (shared with the soft side)."""
    alloc = IdShortAllocator()
    bounds = [_bound(alloc.take(k, "Parameter"), k, v)
              for k, v in sorted(as_dict(req.get("process_parameters")).items())]
    part_alloc = IdShortAllocator()
    parts = [
        el.smc(part_alloc.take(pid, "Part"), [
            el.prop("PartId", pid),
            _string_list("Process", as_dict(spec).get("process")),
            _materials(as_dict(spec).get("materials")),
        ])
        for pid, spec in sorted(as_dict(req.get("parts")).items())
    ]
    return [
        _string_list("Process", req.get("process")),
        _materials(req.get("materials")),
        el.smc("ProcessParameters", bounds),
        el.mlp("Rationale", req.get("rationale")),
        el.smc("Parts", parts),
    ]


def requirement_profile(proj: Projection) -> None:
    m, ho = proj.manifest, proj.hyperobject
    awareness = ho.get("material_awareness")
    declared = []
    if isinstance(awareness, dict):
        declared.append(el.smc("MaterialAwareness", [
            el.prop(k, v) for k, v in sorted(awareness.items())
            if isinstance(v, bool) and isinstance(k, str)
        ], semantic_id=proj.concepts.term("material-awareness")))
    estimation = as_dict(m.get("print_estimation"))
    declared.append(el.prop("DefaultMaterial", estimation.get("default_material")))
    mats = [mt.get("id") for mt in as_list(m.get("materials")) if isinstance(mt, dict)]
    declared.append(_string_list("MaterialOptions", mats))
    proj.add("RequirementProfile", [
        *requirements_elements(as_dict(m.get("requirements"))),
        el.smc("DeclaredHints", declared),
    ], "requirement-profile", "process-parameters-type")


def _vector(id_short: str, vec: object) -> dict | None:
    """A 3-vector as an ordered list ``[x, y, z]`` (single-letter idShorts are invalid in
    v3.1). Numbers are ``xs:double``; when any component is an expression over parameter
    ids, every component is carried as ``xs:string`` — kept, never evaluated."""
    items = as_list(vec)
    if len(items) != 3:
        return el.prop(id_short, vec) if vec is not None else None
    return el.sml(id_short, [el.prop(None, v, prefer="xs:double") for v in items],
                  type_value="Property")


def _size_key(value: object) -> list:
    if isinstance(value, str):
        return [el.prop("SizeKey", value)]
    spec = as_dict(value)
    mapping = [
        el.smc(None, [el.prop("ParameterValue", k), el.prop("SizeKey", v)])
        for k, v in sorted(as_dict(spec.get("map")).items())
    ]
    return [
        el.prop("SizeKeyParameter", spec.get("param")),
        el.sml("SizeKeyMap", mapping, type_value="SubmodelElementCollection"),
    ]


def mating_interfaces(proj: Projection) -> None:
    alloc = IdShortAllocator()
    submodel = proj.sm_id("MatingInterfaces")
    vocab = _geometry_terms()
    out = []
    for iface in as_list(proj.hyperobject.get("cdg_interfaces")):
        if not isinstance(iface, dict):
            continue
        short = alloc.take(iface.get("id"), "Interface")
        here = el.model_ref([("Submodel", submodel), ("SubmodelElementCollection", short)])
        compatible = [
            el.relationship(None, here, el.external_ref(asset_id("solid", slug)))
            for slug in as_list(iface.get("compatible_with"))
            if isinstance(slug, str) and _valid_slug(slug)
        ]
        frame = as_dict(iface.get("frame"))
        frame_el = el.smc("Frame", [
            el.prop("Part", frame.get("part")),
            _vector("Origin", frame.get("origin")),
            _vector("Normal", frame.get("normal")),
            _vector("XAxis", frame.get("x_axis")),
        ]) if frame else None
        gtype = iface.get("geometry_type")
        out.append(el.smc(short, [
            el.prop("InterfaceId", iface.get("id")),
            el.mlp("Label", iface.get("label")),
            el.prop("GeometryType", gtype, semantic_id=proj.concepts.term(vocab.get(gtype))),
            el.prop("Standard", iface.get("standard"),
                    semantic_id=proj.concepts.term("standard-ref")),
            *(_size_key(iface["size_key"]) if "size_key" in iface else []),
            el.prop("Polarity", iface.get("polarity")),
            el.prop("Symmetry", iface.get("symmetry"), prefer="xs:integer"),
            frame_el,
            *proj.param_refs("Parameters", iface.get("parameters")),
            el.sml("CompatibleWith", compatible, type_value="RelationshipElement"),
        ], semantic_id=proj.concepts.term("cdg-interface")))
    proj.add("MatingInterfaces", out, "mating-interfaces")


def _valid_slug(slug: str) -> bool:
    try:
        asset_id("solid", slug)
    except ValueError:
        return False
    return True


@cache
def _geometry_terms() -> dict[str, str]:
    from hyperobjects_lexicon import load_vocabulary

    doc = load_vocabulary("interfaces")
    return {
        e["key"]: e["term"] for e in doc.get("entries", [])
        if e.get("repo") == "yantra4d" and e.get("role") == "geometry_type" and e.get("term")
    }


def _bom_node(short: str, statements: list, *, asset: str | None = None,
              description: object = None) -> dict:
    return el.entity(short, statements, global_asset_id=asset,
                     semantic_id=IDTA["hsebom"].elements["Node"], description=description)


def _bulk_count(qty: object) -> dict | None:
    """HSEBoM ``BulkCount`` (xs:unsignedLong) for a literal non-negative integer only;
    a quantity formula is carried as ``QuantityFormula`` instead, never evaluated."""
    if isinstance(qty, int) and not isinstance(qty, bool) and qty >= 0:
        bulk = el.prop("BulkCount", qty, semantic_id=IDTA["hsebom"].elements["BulkCount"])
        bulk["valueType"] = "xs:unsignedLong"
        return bulk
    return None


def _has_part(parent: list, child: list) -> dict:
    """HSEBoM ``HasPart`` from ``parent`` to ``child``, idShort ``HasPart_<child>``
    (AASd-117: every element outside a list needs an idShort)."""
    short = el_id_short("HasPart_" + child[-1][1])
    return el.relationship(short, el.model_ref(parent), el.model_ref(child),
                           semantic_id=IDTA["hsebom"].elements["HasPart"])


def bill_of_materials(proj: Projection) -> None:
    """``BillOfMaterials`` (HSEBoM shape): the cartridge's multi-part modes and its
    purchased hardware. Modes are alternatives, so each is a Node of its own rather than
    a part of the others."""
    m, hs = proj.manifest, IDTA["hsebom"].elements
    parts = {p["id"]: p for p in as_list(m.get("parts"))
             if isinstance(p, dict) and isinstance(p.get("id"), str)}
    root = [("Submodel", proj.sm_id("BillOfMaterials")), ("Entity", "EntryNode")]
    nodes, relations = [], []
    alloc = IdShortAllocator()
    for mode in as_list(m.get("modes")):
        mode_parts = [p for p in as_list(as_dict(mode).get("parts")) if isinstance(p, str)]
        if len(mode_parts) < 2:
            continue
        mode_short = alloc.take(mode.get("id"), "Mode")
        mode_path = [*root, ("Entity", mode_short)]
        quantities = as_dict(mode.get("part_quantities"))
        part_alloc, part_nodes, part_links = IdShortAllocator(), [], []
        for pid in mode_parts:
            short = part_alloc.take(pid, "Part")
            part_nodes.append(_bom_node(short, [
                el.prop("PartId", pid),
                el.mlp("Label", as_dict(parts.get(pid)).get("label")),
                _bulk_count(quantities.get(pid)),
            ]))
            part_links.append(_has_part(mode_path, [*mode_path, ("Entity", short)]))
        nodes.append(_bom_node(mode_short, [
            el.prop("ModeId", mode.get("id")), el.mlp("Label", mode.get("label")),
            *part_nodes, *part_links,
        ], description={"en": "Configuration produced by one mode; modes are alternatives."}))
        relations.append(_has_part(root, mode_path))
    bom = m.get("bom")
    hardware = as_dict(bom).get("hardware") if isinstance(bom, dict) else bom
    for i, item in enumerate(as_list(hardware)):
        if not isinstance(item, dict):
            continue
        short = alloc.take(item.get("id") or f"Hardware{i + 1}", "Hardware")
        qty = item.get("quantity_formula")
        size_key = item.get("size_key")
        try:
            asset = standard_part_id(size_key) if isinstance(size_key, str) else None
        except ValueError:
            asset = None
        nodes.append(_bom_node(short, [
            el.prop("HardwareId", item.get("id")),
            el.mlp("Label", item.get("label") or item.get("item")),
            _bulk_count(qty),
            el.prop("QuantityFormula", qty) if isinstance(qty, str) else None,
            el.prop("Unit", item.get("unit")),
            el.prop("SizeKey", size_key),
            el.prop("SupplierUrl", item.get("supplier_url"), prefer="xs:anyURI"),
            el.mlp("Condition", item.get("conditional")),
        ], asset=asset))
        relations.append(_has_part(root, [*root, ("Entity", short)]))
    if not nodes:
        return
    entry = el.entity("EntryNode", [*nodes, *relations],
                      global_asset_id=asset_id("solid", proj.slug), semantic_id=hs["EntryNode"])
    proj.add("BillOfMaterials", [entry, el.prop("ArcheType", "Full", semantic_id=hs["ArcheType"])],
             "bill-of-materials", "hsebom")


def project_solid(cartridge_dir: str | Path, manifest: dict | None = None,
                  concepts: Concepts | None = None) -> Projection:
    """Project one solid cartridge directory. Raises ValueError on a missing slug."""
    root = Path(cartridge_dir)
    if manifest is None:
        import json

        manifest = json.loads((root / "project.json").read_text(encoding="utf-8"))
    slug = as_dict(manifest.get("project")).get("slug")
    if not isinstance(slug, str):
        raise ValueError(f"{root}: project.slug is missing")
    proj = Projection("solid", slug, tree_sha256(root), manifest,
                      concepts if concepts is not None else Concepts())
    nameplate(proj)
    parametric_model(proj)
    geometry_provision(proj)
    requirement_profile(proj)
    mating_interfaces(proj)
    bill_of_materials(proj)
    return proj


def build_solid_environment(cartridge_dir: str | Path) -> dict:
    return build_environment(project_solid(cartridge_dir))
