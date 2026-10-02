"""The parts of a projection both commons share: the projection context, the shell, the
Environment, and the ``Nameplate`` and ``ParametricModel`` submodels (SEM-1 §5).

A manifest is read defensively throughout: every field is optional here even where a
manifest schema requires it, wrong-typed values are skipped, and the fields SEM-1 §2–§3
add (``unit``, interface frames, ``requirements``) are emitted when present and omitted
cleanly when absent. The projection never fails on a shape it does not recognise; it
leaves that element out.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hyperobjects_schemas.generator_output import FORMAT as GOC_FORMAT

from . import elements as el
from .concepts import Concepts
from .ids import (
    COMMONS_REPOS,
    IdShortAllocator,
    administration,
    asset_id,
    id_short,
    shell_id,
    submodel_id,
)
from .templates import IDTA, Conformance, apply_conformance

__all__ = [
    "GOC_CONTRACT",
    "GOC_FORMAT",
    "PLATFORMS",
    "Projection",
    "build_environment",
    "nameplate",
    "parametric_model",
]

#: The generator-output contract a render of any of these designs follows.
GOC_CONTRACT = "GOC-1"

#: Public platform surfaces per commons (all already published in the platform repos).
PLATFORMS = {
    "solid": {
        "platform": "yantra4d",
        "product_url": "https://app.yantra4d.com/project/{slug}",
        "render_endpoint": "https://api.yantra4d.com/api/render",
        "manufacturer": {
            "en": "MADFAM solid-hyperobjects commons",
            "es": "Común solid-hyperobjects de MADFAM",
        },
    },
    "soft": {
        "platform": "fashion-cabinet",
        "product_url": "https://fashioncabi.net/api/v1/garments/{slug}",
        "render_endpoint": "https://fashioncabi.net/api/v1/render",
        "manufacturer": {
            "en": "MADFAM soft-hyperobjects commons",
            "es": "Común soft-hyperobjects de MADFAM",
        },
    },
}


def as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list:
    return value if isinstance(value, list) else []


@dataclass
class Projection:
    """Everything one cartridge projection accumulates."""

    kind: str
    slug: str
    tree_sha256: str
    manifest: dict
    concepts: Concepts = field(default_factory=Concepts)
    submodels: list[dict] = field(default_factory=list)
    conformance: list[Conformance] = field(default_factory=list)
    #: parameter id -> its idShort inside ParametricModel/Parameters.
    param_short: dict[str, str] = field(default_factory=dict)

    @property
    def project(self) -> dict:
        return as_dict(self.manifest.get("project"))

    @property
    def hyperobject(self) -> dict:
        return as_dict(self.manifest.get("hyperobject"))

    def sm_id(self, submodel_short: str) -> str:
        return submodel_id(self.kind, self.slug, self.tree_sha256, submodel_short)

    def add(self, short: str, elements: list, madfam: str, idta: str | None = None) -> None:
        """Append a submodel unless it has no elements; apply the conformance rule."""
        body = [e for e in elements if e is not None]
        if not body:
            return
        sm = {
            "modelType": "Submodel",
            "id": self.sm_id(short),
            "idShort": short,
            "kind": "Instance",
            "submodelElements": body,
        }
        self.conformance.append(apply_conformance(sm, madfam, idta))
        self.concepts.template(madfam)
        self.submodels.append(sm)

    def param_ref(self, param: str) -> dict | None:
        """ModelReference to a parameter collection in ParametricModel, if it exists."""
        short = self.param_short.get(param)
        if short is None:
            return None
        return el.model_ref([
            ("Submodel", self.sm_id("ParametricModel")),
            ("SubmodelElementCollection", "Parameters"),
            ("SubmodelElementCollection", short),
        ])

    def param_refs(self, id_short_: str, params: object) -> list:
        """A list of ReferenceElements to known parameters plus, when any id does not
        resolve, the raw ids as strings — a dangling reference is reported, not hidden."""
        refs, unresolved = [], []
        for p in as_list(params):
            ref = self.param_ref(p) if isinstance(p, str) else None
            if ref is not None:
                refs.append(el.reference_element(None, ref))
            elif isinstance(p, str):
                unresolved.append(el.prop(None, p))
        return [
            el.sml(id_short_, refs, type_value="ReferenceElement"),
            el.sml(f"Unresolved{id_short_}", unresolved, type_value="Property"),
        ]


def nameplate(proj: Projection) -> None:
    """``Nameplate`` — the IDTA Digital Nameplate 3.0 elements we can fill truthfully."""
    project, platform = proj.project, PLATFORMS[proj.kind]
    np_ids = IDTA["nameplate"].elements
    attribution = as_dict(project.get("attribution"))
    license_ = proj.hyperobject.get("commons_license") or attribution.get("license")
    lineage = []
    for entry in as_list(attribution.get("lineage")):
        if isinstance(entry, dict):
            lineage.append(el.smc(None, [
                el.prop(id_short(k), v) for k, v in sorted(entry.items())
                if not isinstance(v, (dict, list))
            ]))
        elif isinstance(entry, str):
            lineage.append(el.smc(None, [el.prop("Source", entry)]))
    tags = project.get("tags") or proj.manifest.get("tags")
    elements = [
        el.prop("URIOfTheProduct", platform["product_url"].format(slug=proj.slug),
                prefer="xs:anyURI", semantic_id=np_ids["URIOfTheProduct"]),
        el.mlp("ManufacturerName", platform["manufacturer"],
               semantic_id=np_ids["ManufacturerName"]),
        el.mlp("ManufacturerProductDesignation", project.get("name"),
               semantic_id=np_ids["ManufacturerProductDesignation"]),
        el.mlp("ManufacturerProductFamily", proj.hyperobject.get("domain"),
               semantic_id=np_ids["ManufacturerProductFamily"]),
        el.prop("ManufacturerProductType", proj.slug,
                semantic_id=np_ids["ManufacturerProductType"]),
        el.prop("ManifestVersion", project.get("version")),
        el.prop("Commons", COMMONS_REPOS[proj.kind]),
        el.prop("Author", attribution.get("author")),
        el.prop("DesignLicense", license_, semantic_id=proj.concepts.term("commons-license")),
        el.sml("Lineage", lineage, type_value="SubmodelElementCollection",
               semantic_id=proj.concepts.term("attribution-lineage")),
        el.sml("Tags", [el.prop(None, t) for t in as_list(tags) if isinstance(t, str)],
               type_value="Property", value_type="xs:string"),
        el.mlp("SocietalBenefit", proj.hyperobject.get("societal_benefit"),
               semantic_id=proj.concepts.term("societal-benefit")),
    ]
    proj.add("Nameplate", elements, "nameplate", "nameplate")


def _option_type(options: list) -> str | None:
    """The xs type every option value of a select shares (None if mixed/absent)."""
    types = {
        (el.xsd(o.get("value")) or ("", ""))[0]
        for o in options if isinstance(o, dict) and "value" in o
    }
    if types == {"xs:integer", "xs:double"}:
        return "xs:double"
    return types.pop() if len(types) == 1 else None


def _value_type(param: dict) -> str | None:
    ptype = param.get("type")
    if ptype == "slider":
        return "xs:double"
    if ptype == "checkbox":
        return "xs:boolean"
    if ptype == "select":
        return _option_type(as_list(param.get("options")))
    return None


def _default(param: dict, prefer: str | None) -> dict | None:
    value = param.get("default")
    if param.get("type") == "checkbox" and isinstance(value, int) and value in (0, 1):
        value = bool(value)
    return el.prop("Default", value, prefer=prefer)


def _measurement(value: object) -> dict | None:
    if isinstance(value, str):
        return el.smc("Measurement", [el.prop("Code", value)])
    m = as_dict(value)
    return el.smc("Measurement", [el.prop("Standard", m.get("standard")),
                                   el.prop("Code", m.get("code"))])


def _parameter(proj: Projection, param: dict, short: str) -> dict | None:
    prefer = _value_type(param)
    options = []
    for o in as_list(param.get("options")):
        if isinstance(o, dict):
            options.append(el.smc(None, [el.prop("Value", o.get("value"), prefer=prefer),
                                         el.mlp("Label", o.get("label"))]))
        else:
            options.append(el.smc(None, [el.prop("Value", o, prefer=prefer)]))
    return el.smc(short, [
        el.prop("ParameterId", param.get("id")),
        el.prop("Type", param.get("type")),
        _default(param, prefer),
        el.range_element("Range", param.get("min"), param.get("max")),
        el.prop("Step", param.get("step"), prefer="xs:double"),
        el.prop("Unit", param.get("unit")),
        el.mlp("Label", param.get("label")),
        el.mlp("Tooltip", param.get("tooltip")),
        el.sml("Options", options, type_value="SubmodelElementCollection"),
        _measurement(param["measurement"]) if "measurement" in param else None,
    ], semantic_id=proj.concepts.term("parameter"))


def _preset(proj: Projection, preset: dict, short: str, prefer: dict[str, str | None]) -> dict:
    values = []
    for pid, value in sorted(as_dict(preset.get("values")).items()):
        values.append(el.prop(proj.param_short.get(pid) or id_short(pid), value,
                              prefer=prefer.get(pid)))
    alloc = IdShortAllocator()
    unique = []
    for v in values:  # two raw ids can map to one idShort; keep both, distinctly
        if v is not None:
            v["idShort"] = alloc.take(v["idShort"])
            unique.append(v)
    return el.smc(short, [
        el.prop("PresetId", preset.get("id")),
        el.prop("Mode", preset.get("mode")),
        el.mlp("Label", preset.get("label")),
        el.smc("Values", unique),
    ], semantic_id=proj.concepts.term("preset"))


_CONSTRAINT_KEYS = ("expression", "rule", "severity", "message", "applies_to")


def _constraint(c: dict) -> dict | None:
    rest = {k: v for k, v in c.items() if k not in _CONSTRAINT_KEYS}
    applies = c.get("applies_to")
    return el.smc(None, [
        el.prop("Expression", c.get("expression") if "expression" in c else c.get("rule")),
        el.prop("Severity", c.get("severity")),
        el.mlp("Message", c.get("message")),
        el.prop("AppliesTo", applies) if applies is not None else None,
        el.prop("Definition", rest) if rest else None,
    ])


def parametric_model(proj: Projection) -> None:
    """``ParametricModel`` — parameters, presets and constraints (MADFAM template)."""
    params = [p for p in as_list(proj.manifest.get("parameters")) if isinstance(p, dict)]
    alloc = IdShortAllocator()
    collections, prefer = [], {}
    for p in params:
        short = alloc.take(p.get("id"), "Parameter")
        if isinstance(p.get("id"), str):
            proj.param_short.setdefault(p["id"], short)
            prefer[p["id"]] = _value_type(p)
        collections.append(_parameter(proj, p, short))
    preset_alloc = IdShortAllocator()
    presets = [
        _preset(proj, pr, preset_alloc.take(pr.get("id"), "Preset"), prefer)
        for pr in as_list(proj.manifest.get("presets")) if isinstance(pr, dict)
    ]
    constraints = [
        _constraint(c) for c in as_list(proj.manifest.get("constraints")) if isinstance(c, dict)
    ]
    proj.add("ParametricModel", [
        el.smc("Parameters", collections),
        el.smc("Presets", presets),
        el.sml("Constraints", constraints, type_value="SubmodelElementCollection"),
    ], "parametric-model")


def build_environment(proj: Projection) -> dict:
    """Assemble the AAS Environment: one type shell, its submodels, the concepts."""
    project = proj.project
    info: dict = {
        "assetKind": "Type",
        "globalAssetId": asset_id(proj.kind, proj.slug),
        "specificAssetIds": [
            {"name": "commons", "value": COMMONS_REPOS[proj.kind]},
            {"name": "slug", "value": proj.slug},
            {"name": "tree_sha256", "value": proj.tree_sha256},
        ],
    }
    shell: dict = {
        "modelType": "AssetAdministrationShell",
        "id": shell_id(proj.kind, proj.slug, proj.tree_sha256),
        "idShort": id_short(proj.slug, "Shell"),
        "assetInformation": info,
        "submodels": [el.model_ref([("Submodel", sm["id"])]) for sm in proj.submodels],
    }
    names = el.lang_strings(project.get("name"), el.NAME_LIMIT)
    if names:
        shell["displayName"] = names
    desc = el.lang_strings(project.get("description"))
    if desc:
        shell["description"] = desc
    admin = administration(project.get("version"))
    if admin:
        shell["administration"] = admin
    if not shell["submodels"]:
        del shell["submodels"]
    env: dict = {"assetAdministrationShells": [shell]}
    if proj.submodels:
        env["submodels"] = proj.submodels
    cds = proj.concepts.descriptions()
    if cds:
        env["conceptDescriptions"] = cds
    return env
