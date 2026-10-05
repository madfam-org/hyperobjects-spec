"""The assembly projection (ASM-1 §5): one checked assembly -> one AAS Environment.

An assembly is projected only once the keystone validator has passed it
(``y4d_spec.assembly.validate_assembly``): "finalizing" an assembly is that check
passing (ASM-1 §3), so a failing report raises instead of producing a shell. The whole
environment is a function of the document and the report, so any holder of the same
components — the commons checkout (``CommonsManifestResolver``), or the asset-shells
service resolving from stored type shells (``hyperobjects_aas.resolver``) — derives the
same environment byte for byte, and a service can refuse a published assembly that is not
exactly the projection of its own document.

Shell ``https://id.madfam.io/aas/assembly/{slug}/{digest16}/p{N}``, asset
``https://id.madfam.io/asset/assembly/{slug}``; ``digest16`` is the first 16 hex of the
canonical assembly digest (``hyperobjects-assembly-v1``). Submodels:

* ``Nameplate`` — as for a cartridge (the IDTA claim only when conformant).
* ``AssemblyDocument`` (MADFAM ``smt/assembly-document/1/0``) — the document exactly as
  checked, as a ``Blob`` of its canonical JSON, with the full digest. A holder of the shell
  can re-run the validator without the commons checkout; asset-shells does (ASM-1 §6).
* ``BillOfMaterials`` (IDTA 02011-1-1 HSEBoM when conformant) — the assembly as the
  ``EntryNode``; one ``Node`` entity per component, ``HasPart`` from the entry node to each.
  A cartridge node names ``asset/solid/{slug}``, carries the GOC-1 ``instance_id`` as a
  specificAssetId and a ``DerivedFrom`` reference to the exact type shell revision
  (``aas/solid/{slug}/{tree16}/p{N}``, at the assembly's own projection version) whose
  interfaces it was resolved from; a standard part names ``asset/standard/{key}``
  (catalog key); an external design is a CoManaged entity with its name, licence, URL and
  revision (no MADFAM asset exists for it).
* ``Mates`` (MADFAM ``smt/assembly-mates/1/0``) — one ``AnnotatedRelationshipElement`` per
  mate between the two component nodes, annotated with the two interface ids, the stated
  rotation, the closure residuals and ``Validated``.
* ``AssemblyPlacement`` (MADFAM) — each component's 4 × 4 world transform, row-major.
* producers: ``CapabilityDescription`` (IDTA 02020-1-0 when conformant) from
  ``capability_profile``; products with ``requirements_rollup``: ``RequirementProfile``,
  the fabricated components' ``requirements`` rolled up.

    from y4d_spec.assembly import CompositeResolver, validate_assembly
    report = validate_assembly(doc, CompositeResolver.for_directories(commons, parts))
    env = build_assembly_environment(doc, report)
"""

from __future__ import annotations

import base64
import binascii
import json
import math
from collections.abc import Mapping
from functools import cache

from hyperobjects_schemas.generator_output import canonical_json

from . import elements as el
from .common import Projection, as_dict, as_list, build_environment, nameplate
from .concepts import Concepts
from .ids import IdShortAllocator, asset_id, shell_id, standard_part_id
from .ids import id_short as _short
from .solid import requirements_elements
from .templates import IDTA

__all__ = [
    "ASSEMBLY_DOCUMENT_CONTENT_TYPE",
    "AssemblyProjectionError",
    "assembly_document_from_environment",
    "build_assembly_environment",
    "component_type_shells",
    "project_assembly",
]

ASSEMBLY_DOCUMENT_CONTENT_TYPE = "application/json"

#: Matrix entries are written to 9 decimals: the residuals the validator accepts are
#: 0.05 mm / 0.5°, and floating noise (1e-17, −0.0) must not reach the canonical JSON.
_MATRIX_DIGITS = 9


class AssemblyProjectionError(ValueError):
    """The assembly cannot be projected (it failed the check, or a field is unusable)."""


def _num(value: float | None, digits: int = _MATRIX_DIGITS) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits) + 0.0


# ── submodels ─────────────────────────────────────────────────────────────────
def _assembly_document(proj: Projection, doc: Mapping, digest: str) -> None:
    from y4d_spec.assembly import ASSEMBLY_DIGEST_ALGORITHM

    proj.add("AssemblyDocument", [
        el.prop("Format", doc.get("format")),
        el.prop("FormatVersion", doc.get("format_version")),
        el.prop("Kind", doc.get("kind")),
        el.prop("Root", doc.get("root")),
        el.prop("DigestAlgorithm", ASSEMBLY_DIGEST_ALGORITHM),
        el.prop("AssemblyDigest", digest),
        el.blob("Document", canonical_json(doc), ASSEMBLY_DOCUMENT_CONTENT_TYPE,
                semantic_id=proj.concepts.term("assembly")),
    ], "assembly-document")


def _parameters(id_short: str, values: Mapping) -> dict | None:
    alloc = IdShortAllocator()
    return el.smc(id_short, [
        el.smc(alloc.take(k, "Parameter"), [el.prop("ParameterId", k), el.prop("Value", v)])
        for k, v in sorted(as_dict(values).items())
    ])


def _component_node(proj: Projection, short: str, component: Mapping, resolved) -> dict:
    """One HSEBoM Node for one component (one component = one physical instance)."""
    hs = IDTA["hsebom"].elements
    source = as_dict(component.get("source"))
    kind = source.get("type")
    identity, details = as_dict(resolved.identity), as_dict(resolved.details)
    common = [
        el.prop("ComponentId", component["id"]),
        el.prop("SourceType", kind),
        el.mlp("Label", component.get("label")),
    ]
    bulk = el.prop("BulkCount", 1, semantic_id=hs["BulkCount"])
    bulk["valueType"] = "xs:unsignedLong"
    if kind == "cartridge":
        slug, tree = source.get("slug"), details.get("tree_sha256")
        # The type shell of the SAME projection version as this assembly's own shell.
        type_shell = shell_id("solid", slug, tree, version=proj.version)
        return el.entity(short, [
            *common,
            el.prop("Commons", source.get("commons")),
            el.prop("Slug", slug),
            el.prop("Mode", source.get("mode")),
            el.prop("Part", source.get("part")),
            _parameters("Parameters", source.get("parameters")),
            el.prop("InstanceId", identity.get("instance_id")),
            el.prop("TreeSha256", tree),
            el.reference_element("DerivedFrom", el.model_ref([("AssetAdministrationShell",
                                                                type_shell)])),
            bulk,
        ], global_asset_id=asset_id("solid", slug), semantic_id=hs["Node"],
            specific_asset_ids=[("instance_id", identity.get("instance_id"))])
    if kind == "standard":
        key = source.get("key")
        return el.entity(short, [
            *common,
            el.prop("Key", key, semantic_id=proj.concepts.term("standard-part")),
            _parameters("Parameters", identity.get("parameters")),
            el.prop("CatalogSha256", identity.get("catalog_sha256")),
            bulk,
        ], global_asset_id=standard_part_id(key), semantic_id=hs["Node"],
            specific_asset_ids=[("catalog_sha256", identity.get("catalog_sha256"))])
    return el.entity(short, [
        *common,
        el.prop("Name", source.get("name"),
                semantic_id=proj.concepts.term("external-design-reference")),
        el.prop("License", source.get("license")),
        el.prop("Url", source.get("url"), prefer="xs:anyURI"),
        el.prop("Revision", source.get("revision")),
        bulk,
    ], semantic_id=hs["Node"])


def _source_key(component: Mapping) -> str:
    source = as_dict(component.get("source"))
    kind = source.get("type")
    if kind == "cartridge":
        return asset_id("solid", source.get("slug"))
    if kind == "standard":
        return standard_part_id(source.get("key"))
    return str(source.get("url") or source.get("name"))


def _bill_of_materials(proj: Projection, doc: Mapping, report, shorts: dict[str, str]) -> None:
    hs = IDTA["hsebom"].elements
    root = [("Submodel", proj.sm_id("BillOfMaterials")), ("Entity", "EntryNode")]
    nodes, links = [], []
    for component in doc["components"]:
        short = shorts[component["id"]]
        nodes.append(_component_node(proj, short, component, report.components[component["id"]]))
        links.append(el.relationship(
            _short("HasPart_" + short), el.model_ref(root),
            el.model_ref([*root, ("Entity", short)]), semantic_id=hs["HasPart"]))
    counts: dict[str, int] = {}
    for component in doc["components"]:
        counts[_source_key(component)] = counts.get(_source_key(component), 0) + 1
    entry = el.entity("EntryNode", [*nodes, *links], global_asset_id=asset_id("assembly",
                                                                              proj.slug),
                      semantic_id=hs["EntryNode"])
    proj.add("BillOfMaterials", [
        entry,
        el.prop("ArcheType", "Full", semantic_id=hs["ArcheType"]),
        el.sml("CountsBySource", [
            el.smc(None, [el.prop("Source", src), el.prop("Count", n, prefer="xs:integer")])
            for src, n in sorted(counts.items())
        ], type_value="SubmodelElementCollection"),
    ], "bill-of-materials", "hsebom")


def _mates(proj: Projection, doc: Mapping, report, shorts: dict[str, str]) -> None:
    bom = [("Submodel", proj.sm_id("BillOfMaterials")), ("Entity", "EntryNode")]
    checks = {m.mate_id: m for m in report.mates}
    alloc = IdShortAllocator()
    out = []
    for mate in doc["mates"]:
        check = checks[mate["id"]]
        a, b = mate["a"], mate["b"]
        out.append(el.annotated_relationship(
            alloc.take(mate["id"], "Mate"),
            el.model_ref([*bom, ("Entity", shorts[a["component"]])]),
            el.model_ref([*bom, ("Entity", shorts[b["component"]])]),
            [
                el.prop("MateId", mate["id"]),
                el.prop("ComponentA", a["component"]),
                el.prop("InterfaceA", a["interface"]),
                el.prop("ComponentB", b["component"]),
                el.prop("InterfaceB", b["interface"]),
                el.prop("Symmetry", check.symmetry, prefer="xs:integer",
                        semantic_id=proj.concepts.term("interface-symmetry")),
                el.prop("RotationIndex", mate.get("rotation_index"), prefer="xs:integer"),
                el.prop("AngleDeg", mate.get("angle_deg"), prefer="xs:double"),
                el.prop("ThetaDeg", _num(check.theta_deg, 6), prefer="xs:double"),
                el.prop("InTree", check.in_tree),
                el.prop("OriginResidualMm", _num(check.origin_mm, 6), prefer="xs:double"),
                el.prop("NormalResidualDeg", _num(check.normal_deg, 6), prefer="xs:double"),
                el.prop("XAxisResidualDeg", _num(check.x_axis_deg, 6), prefer="xs:double"),
                el.prop("MeasuredDeg", _num(check.measured_deg, 6), prefer="xs:double"),
                el.prop("Validated", check.ok),
            ],
            semantic_id=proj.concepts.term("mate"),
        ))
    proj.add("Mates", out, "assembly-mates")


def _placement(proj: Projection, doc: Mapping, report, shorts: dict[str, str]) -> None:
    term = proj.concepts.term("assembly-placement")
    out = []
    for component in doc["components"]:
        matrix = report.placements[component["id"]]
        out.append(el.smc(shorts[component["id"]], [
            el.prop("ComponentId", component["id"]),
            el.sml("Transform", [el.prop(None, _num(v), prefer="xs:double")
                                 for row in matrix for v in row], type_value="Property",
                   value_type="xs:double"),
        ], semantic_id=term))
    proj.add("AssemblyPlacement", [
        el.prop("LengthUnit", "mm"),
        el.prop("MatrixLayout", "row-major 4x4, world <- component"),
        el.smc("Components", out),
    ], "assembly-placement")


@cache
def _vocabulary(name: str) -> dict[str, dict]:
    from hyperobjects_lexicon.fabrication import load_fabrication_vocabulary

    doc = load_fabrication_vocabulary(name)
    return {e["key"]: e for e in doc.get("entries", []) if isinstance(e, dict)}


def _capability_value(id_short: str, key: str, value: object, cap: Mapping) -> dict | None:
    if isinstance(value, list):
        return el.sml(id_short, [el.prop(None, v) for v in value], type_value="Property",
                      semantic_id=cap["PropertySubmodelList"])
    return el.prop(id_short, value, semantic_id=cap["PropertyProperty"])


def _capability_description(proj: Projection, doc: Mapping) -> None:
    """IDTA 02020-1-0: one CapabilityContainer per process the machine performs, each with
    the machine's other declared capabilities as its PropertySet."""
    profile = as_dict(doc.get("capability_profile"))
    if not profile:
        return
    cap = IDTA["capability-description"].elements
    capabilities = _vocabulary("fabrication-capabilities")
    processes = _vocabulary("processes")
    alloc = IdShortAllocator()
    props = []
    for key in sorted(k for k in profile if k != "process"):
        entry = as_dict(capabilities.get(key))
        props.append(el.smc(alloc.take(key, "Property"), [
            _capability_value(_short(key), key, profile[key], cap),
            el.mlp("PropertyComment", entry.get("label"), semantic_id=cap["PropertyComment"]),
        ], semantic_id=cap["PropertyContainer"]))
    containers = []
    container_alloc = IdShortAllocator()
    for process in as_list(profile.get("process")):
        entry = as_dict(processes.get(process))
        term = proj.concepts.term(entry.get("term"))
        containers.append(el.smc(container_alloc.take(f"Fabrication_{process}"), [
            el.capability(_short(process), semantic_id=cap["Capability"],
                          supplemental=[term] if term else ()),
            el.mlp("CapabilityComment", entry.get("label"), semantic_id=cap["CapabilityComment"]),
            el.smc("PropertySet", props, semantic_id=cap["PropertySet"]),
        ], semantic_id=cap["CapabilityContainer"]))
    proj.add("CapabilityDescription", [
        el.smc("CapabilitySet", containers, semantic_id=cap["CapabilitySet"]),
    ], "capability-description", "capability-description")


def _requirement_rollup(proj: Projection, doc: Mapping, report) -> None:
    if doc.get("kind") != "product" or not doc.get("requirements_rollup"):
        return
    alloc = IdShortAllocator()
    rows, processes = [], set()
    for component in doc["components"]:
        resolved = report.components[component["id"]]
        details = as_dict(resolved.details)
        req = as_dict(details.get("requirements"))
        if not req:
            continue
        produced = [p for p in as_list(details.get("parts")) if isinstance(p, str)]
        blocks = [req] + [as_dict(as_dict(req.get("parts")).get(p)) for p in produced]
        for block in blocks:
            procs = block.get("process")
            processes.update([procs] if isinstance(procs, str) else
                             [p for p in as_list(procs) if isinstance(p, str)])
        rows.append(el.smc(alloc.take(component["id"], "Component"), [
            el.prop("ComponentId", component["id"]),
            el.prop("Slug", as_dict(component.get("source")).get("slug")),
            el.sml("ProducedParts", [el.prop(None, p) for p in produced], type_value="Property",
                   value_type="xs:string"),
            *requirements_elements(req),
        ]))
    if not rows:
        return
    proj.add("RequirementProfile", [
        el.sml("Process", [el.prop(None, p) for p in sorted(processes)], type_value="Property",
               value_type="xs:string"),
        el.smc("Components", rows),
    ], "requirement-profile", "process-parameters-type")


# ── entry points ──────────────────────────────────────────────────────────────
def _pseudo_manifest(doc: Mapping) -> dict:
    """The fields the shared Nameplate and shell builders read, from the assembly."""
    return {
        "project": {"slug": doc.get("slug"), "name": doc.get("name"),
                    "description": doc.get("description")},
        "hyperobject": {"commons_license": doc.get("license")},
    }


def project_assembly(doc: Mapping, report, concepts: Concepts | None = None) -> Projection:
    """Project one assembly the validator passed. Raises AssemblyProjectionError when the
    report has an error or no digest (an assembly is final only once its check passes)."""
    if not report.ok:
        problems = "; ".join(str(f) for f in report.errors[:5])
        raise AssemblyProjectionError(
            f"the assembly did not pass its check ({len(report.errors)} error(s)): {problems}")
    if not report.digest:
        raise AssemblyProjectionError("the report carries no assembly digest")
    slug = doc.get("slug")
    if not isinstance(slug, str):
        raise AssemblyProjectionError("the assembly has no slug")
    proj = Projection("assembly", slug, report.digest, _pseudo_manifest(doc),
                      concepts if concepts is not None else Concepts())
    alloc = IdShortAllocator(reserved=("EntryNode",))
    shorts = {c["id"]: alloc.take(c["id"], "Component") for c in doc["components"]}
    nameplate(proj)
    _assembly_document(proj, doc, report.digest)
    _bill_of_materials(proj, doc, report, shorts)
    _mates(proj, doc, report, shorts)
    _placement(proj, doc, report, shorts)
    _capability_description(proj, doc)
    _requirement_rollup(proj, doc, report)
    return proj


def build_assembly_environment(doc: Mapping, report) -> dict:
    """The AAS Environment of a checked assembly (canonical JSON makes it deterministic)."""
    return build_environment(project_assembly(doc, report))


# ── reading a projected assembly back (the asset-shells seam) ─────────────────
def _submodel(env: Mapping, id_short: str) -> dict | None:
    for sm in as_list(env.get("submodels")):
        if isinstance(sm, dict) and sm.get("idShort") == id_short:
            return sm
    return None


def _children(element: Mapping) -> list[dict]:
    if element.get("modelType") == "Entity":
        return [c for c in as_list(element.get("statements")) if isinstance(c, dict)]
    if "submodelElements" in element:
        return [c for c in as_list(element.get("submodelElements")) if isinstance(c, dict)]
    value = element.get("value")
    return [c for c in value if isinstance(c, dict)] if isinstance(value, list) else []


def _child(element: Mapping, id_short: str) -> dict | None:
    return next((c for c in _children(element) if c.get("idShort") == id_short), None)


def assembly_document_from_environment(env: Mapping) -> dict:
    """The assembly document an assembly environment carries (``AssemblyDocument``).
    Raises AssemblyProjectionError naming what is missing or unreadable."""
    sm = _submodel(env, "AssemblyDocument")
    if sm is None:
        raise AssemblyProjectionError("the environment has no AssemblyDocument submodel")
    blob = _child(sm, "Document")
    if blob is None or blob.get("modelType") != "Blob":
        raise AssemblyProjectionError("AssemblyDocument has no Document Blob")
    if blob.get("contentType") != ASSEMBLY_DOCUMENT_CONTENT_TYPE:
        raise AssemblyProjectionError(
            f"AssemblyDocument/Document is {blob.get('contentType')!r}, not "
            f"{ASSEMBLY_DOCUMENT_CONTENT_TYPE}")
    try:
        doc = json.loads(base64.b64decode(blob.get("value") or "", validate=True))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise AssemblyProjectionError(
            f"AssemblyDocument/Document is not base64 JSON: {exc}") from None
    if not isinstance(doc, dict):
        raise AssemblyProjectionError("AssemblyDocument/Document is not a JSON object")
    return doc


def component_type_shells(env: Mapping) -> dict[str, str]:
    """``{component id: type shell id}`` for every cartridge node of the environment's
    BillOfMaterials (its ``DerivedFrom`` reference): the revision each cartridge component
    was resolved from. A service resolves the same revision from its own store."""
    sm = _submodel(env, "BillOfMaterials")
    entry = _child(sm, "EntryNode") if sm else None
    out: dict[str, str] = {}
    for node in _children(entry) if entry else []:
        if node.get("modelType") != "Entity":
            continue
        cid, ref = _child(node, "ComponentId"), _child(node, "DerivedFrom")
        keys = as_list(as_dict(ref.get("value")).get("keys")) if ref else []
        if cid and keys and keys[-1].get("type") == "AssetAdministrationShell":
            out[cid.get("value")] = keys[-1].get("value")
    return out

