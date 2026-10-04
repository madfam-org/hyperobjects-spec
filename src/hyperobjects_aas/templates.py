"""Submodel templates: the IDTA identifiers we copy, the MADFAM ones we mint, and the
conformance-claim rule that chooses between them (SEM-1 §1, R85).

IDTA identifiers are COPIED, never typed from memory: every string below was read from
the template JSON published in ``admin-shell-io/submodel-templates`` at commit
:data:`IDTA_COMMIT`, at the path recorded beside it. Where the published template carries
a malformed identifier (two element ids in the materials template begin ``ttps://`` or
are doubled), the projection does not use that element at all rather than copy the
defect or silently repair it.

A submodel claims an IDTA template's semanticId only if every element the template
marks mandatory (cardinality ``One`` / ``OneToMany``) is present. Elements are matched
by **semanticId**, not idShort, because several templates let the idShort be chosen
freely (``EditIdShort``). Otherwise the submodel carries the MADFAM template id and lists
the IDTA id in ``supplementalSemanticIds`` — a pointer, not a claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .elements import external_ref
from .ids import template_id

__all__ = [
    "DATA_SPECIFICATION_IEC61360",
    "IDTA",
    "IDTA_COMMIT",
    "IDTA_REPO",
    "MADFAM",
    "Conformance",
    "IdtaTemplate",
    "MadfamTemplate",
    "apply_conformance",
    "missing_mandatory",
]

IDTA_REPO = "https://github.com/admin-shell-io/submodel-templates"
IDTA_COMMIT = "e088e13699ce018e8c2069a261bbe4c310ce570b"

#: Copied from the v3.1 IDTA templates above (embeddedDataSpecifications of their
#: ConceptDescriptions), e.g. the HSEBoM ``_forAASMetamodelV3.1.json`` file.
DATA_SPECIFICATION_IEC61360 = (
    "https://admin-shell.io/DataSpecificationTemplates/DataSpecificationIec61360/3/0"
)


@dataclass(frozen=True)
class IdtaTemplate:
    key: str
    title: str
    source_path: str
    submodel_semantic_id: str
    version: tuple[str, str]
    #: Mandatory elements, each a path of semanticIds from the submodel down.
    mandatory: tuple[tuple[str, ...], ...]
    #: Element semanticIds the projection uses, by the template's idShort.
    elements: dict[str, str] = field(default_factory=dict)


_NP = "0112/2///61987#"
_HS = "https://admin-shell.io/idta/HierarchicalStructures/"
_MAT = "https://admin-shell.io/idta/BackendSpecificMaterialInformation/"
_CAP = "https://admin-shell.io/idta/CapabilityDescription/"

IDTA: dict[str, IdtaTemplate] = {
    t.key: t
    for t in (
        IdtaTemplate(
            key="nameplate",
            title="IDTA 02006-3-0 Digital Nameplate for Industrial Equipment",
            source_path="published/Digital nameplate/3/0/2/"
            "IDTA 02006-3-0-2_Template_Digital Nameplate.json",
            submodel_semantic_id="https://admin-shell.io/idta/nameplate/3/0/Nameplate",
            version=("3", "0"),
            mandatory=(
                (_NP + "ABN590#002",),  # URIOfTheProduct
                (_NP + "ABA565#009",),  # ManufacturerName
                (_NP + "ABA567#009",),  # ManufacturerProductDesignation
                ("https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/"
                 "AddressInformation",),
                (_NP + "ABA950#008",),  # OrderCodeOfManufacturer
            ),
            elements={
                "URIOfTheProduct": _NP + "ABN590#002",
                "ManufacturerName": _NP + "ABA565#009",
                "ManufacturerProductDesignation": _NP + "ABA567#009",
                "ManufacturerProductFamily": _NP + "ABP464#002",
                "ManufacturerProductType": _NP + "ABA300#008",
            },
        ),
        IdtaTemplate(
            key="models3d",
            title="IDTA 02026-1-0 Provision of 3D Models",
            source_path="published/Provision of 3D Models/1/0/2/"
            "IDTA 02026-1-0-2_Template_ProvisionOf3DModels_forAASMetamodelV3.1.json",
            submodel_semantic_id="https://admin-shell.io/idta/Models3D/1/0",
            version=("1", "0"),
            mandatory=(("https://admin-shell.io/idta/Models3D/Model3D/1/0",),),
        ),
        IdtaTemplate(
            key="process-parameters-type",
            title="IDTA 02031-1 Process Parameters Type",
            source_path="published/Process Parameters Type/1/0/"
            "IDTA 02031-1_Template_ProcessParameters_Type_forAASMetamodelV3.1.json",
            # Verbatim, including the template's `admin-shell-io` host spelling.
            submodel_semantic_id="https://admin-shell-io/idta/SubmodelTemplate/ProcessParameters/1/0",
            version=("1", "0"),
            mandatory=(("https://admin-shell.io/idta/ProcessParameters/Processes/1/0",),),
        ),
        IdtaTemplate(
            key="hsebom",
            title="IDTA 02011-1-1 Hierarchical Structures enabling Bills of Material",
            source_path="published/Hierarchical Structures enabling Bills of Material/1/1/2/"
            "IDTA 02011-1-1-2_Template_HSEBoM_forAASMetamodelV3.1.json",
            submodel_semantic_id=_HS + "1/1/Submodel",
            version=("1", "1"),
            mandatory=(
                (_HS + "EntryNode/1/0",),
                (_HS + "EntryNode/1/0", _HS + "Node/1/0"),
                (_HS + "ArcheType/1/0",),
            ),
            elements={
                "EntryNode": _HS + "EntryNode/1/0",
                "Node": _HS + "Node/1/0",
                "HasPart": _HS + "HasPart/1/0",
                "BulkCount": _HS + "BulkCount/1/0",
                "ArcheType": _HS + "ArcheType/1/0",
            },
        ),
        IdtaTemplate(
            key="materials",
            title="IDTA 02034-1-0 Creation and Classification of Materials "
            "(Backend Specific Material Information)",
            source_path="published/Creation and Classification of Materials/1/0/1/"
            "IDTA 02034-1-0-1 Template_BackendSpecificMaterialInformation"
            "_forAASMetamodelV3.1.json",
            submodel_semantic_id=_MAT + "1/0",
            version=("1", "0"),
            mandatory=((_MAT + "MaterialSystemProperties/1/0",),),
            elements={
                "MaterialSystemProperties": _MAT + "MaterialSystemProperties/1/0",
                "MaterialType": _MAT + "MaterialSystemProperties/MaterialType/1/0",
                "ProductName": _MAT + "MaterialSystemProperties/ProductName/1/0",
                "MaterialNumber": _MAT + "MaterialSystemProperties/MaterialNumber/1/0",
                "Description": _MAT + "MaterialSystemProperties/Description/1/0",
            },
        ),
        IdtaTemplate(
            key="capability-description",
            title="IDTA 02020-1-0 Capability Description",
            source_path="published/Capability Description/1/0/"
            "IDTA 02020_Template_Capability_Description.json",
            submodel_semantic_id=(
                "https://admin-shell.io/idta/SubmodelTemplate/CapabilityDescription/1/0"
            ),
            version=("1", "0"),
            mandatory=(
                (_CAP + "CapabilitySet/1/0",),
                (_CAP + "CapabilitySet/1/0", _CAP + "CapabilityContainer/1/0"),
                (_CAP + "CapabilitySet/1/0", _CAP + "CapabilityContainer/1/0",
                 _CAP + "Capability/1/0"),
            ),
            elements={
                "CapabilitySet": _CAP + "CapabilitySet/1/0",
                "CapabilityContainer": _CAP + "CapabilityContainer/1/0",
                "Capability": _CAP + "Capability/1/0",
                "CapabilityComment": _CAP + "CapabilityComment/1/0",
                "PropertySet": _CAP + "PropertySet/1/0",
                "PropertyContainer": _CAP + "PropertyContainer/1/0",
                "PropertyComment": _CAP + "PropertyComment/1/0",
                "PropertyProperty": "https://admin-shell.io/idta/CapabilityPropertyType/Property/1/0",
                "PropertySubmodelList": (
                    "https://admin-shell.io/idta/CapabilityPropertyType/SubmodelElementList/1/0"
                ),
            },
        ),
    )
}


@dataclass(frozen=True)
class MadfamTemplate:
    name: str
    major: int
    minor: int
    preferred_name: dict[str, str]
    definition: dict[str, str]

    @property
    def id(self) -> str:
        return template_id(self.name, self.major, self.minor)


def _t(name: str, en: str, es: str, fr: str, pt: str, def_en: str, def_es: str):
    return MadfamTemplate(
        name, 1, 0, {"en": en, "es": es, "fr": fr, "pt": pt}, {"en": def_en, "es": def_es}
    )


MADFAM: dict[str, MadfamTemplate] = {
    t.name: t
    for t in (
        _t("nameplate", "Design nameplate", "Placa de identificación del diseño",
           "Plaque signalétique de la conception", "Placa de identificação do projeto",
           "Identity, designation, licence and provenance of a commons design type.",
           "Identidad, designación, licencia y procedencia de un tipo de diseño del común."),
        _t("parametric-model", "Parametric model", "Modelo paramétrico", "Modèle paramétrique",
           "Modelo paramétrico",
           "Every parameter of a design with its default, range, unit, options and labels, "
           "the named presets, and the constraint expressions with their severity.",
           "Cada parámetro de un diseño con su valor por omisión, rango, unidad, opciones y "
           "etiquetas, los preajustes y las expresiones de restricción con su severidad."),
        _t("geometry-provision", "Geometry provision", "Provisión de geometría",
           "Mise à disposition de la géométrie", "Provisão de geometria",
           "How the geometry of a parametric solid design is produced on demand: modes, "
           "parts, engines, producible formats and the render endpoint.",
           "Cómo se produce bajo demanda la geometría de un diseño sólido paramétrico: modos, "
           "piezas, motores, formatos producibles y el punto de renderizado."),
        _t("requirement-profile", "Requirement profile", "Perfil de requisitos",
           "Profil d'exigences", "Perfil de requisitos",
           "The fabrication requirements a design states: processes, material classes, "
           "process-parameter bounds and their rationale.",
           "Los requisitos de fabricación que declara un diseño: procesos, clases de "
           "material, límites de parámetros de proceso y su justificación."),
        _t("mating-interfaces", "Mating interfaces", "Interfaces de acoplamiento",
           "Interfaces d'accouplement", "Interfaces de acoplamento",
           "The physical interfaces by which a part mates with others: type, standard, size "
           "key, polarity, symmetry, frame and the parameters that size it.",
           "Las interfaces físicas por las que una pieza se acopla con otras: tipo, norma, "
           "clave de tamaño, polaridad, simetría, marco y los parámetros que la dimensionan."),
        _t("bill-of-materials", "Bill of materials", "Lista de materiales",
           "Nomenclature", "Lista de materiais",
           "The parts of each multi-part mode and the purchased hardware of a design; for an "
           "assembly, one node per component.",
           "Las piezas de cada modo de varias piezas y la ferretería comprada de un diseño; "
           "en un ensamble, un nodo por componente."),
        _t("pattern-provision", "Pattern provision", "Provisión de patrón",
           "Mise à disposition du patron", "Provisão de molde",
           "How the flat pattern of a parametric garment is produced on demand: modes, "
           "pieces, cutting instructions, formats and the render endpoint.",
           "Cómo se produce bajo demanda el patrón plano de una prenda paramétrica: modos, "
           "piezas, instrucciones de corte, formatos y el punto de renderizado."),
        _t("seam-interfaces", "Seam interfaces", "Interfaces de costura",
           "Interfaces de couture", "Interfaces de costura",
           "The named seams of a garment: type, the piece edges that form each one and the "
           "parameters that size it.",
           "Las costuras nombradas de una prenda: tipo, los bordes de pieza que la forman y "
           "los parámetros que la dimensionan."),
        _t("fabrics", "Fabrics", "Telas", "Tissus", "Tecidos",
           "The fabric material assets a garment design is drafted for.",
           "Los activos de material textil para los que se trazó un diseño de prenda."),
        _t("hardware-links", "Hardware links", "Vínculos de herraje",
           "Liens de quincaillerie", "Ligações de aviamento",
           "Relations from a garment notion to the solid type asset that realises it, with "
           "the parameter mapping.",
           "Relaciones de un avío de prenda con el activo sólido que lo realiza, con el "
           "mapeo de parámetros."),
        _t("assembly-document", "Assembly document", "Documento de ensamble",
           "Document d'assemblage", "Documento de montagem",
           "The authored assembly document (ASM-1 §2) exactly as checked, its format and the "
           "canonical digest that names this assembly revision.",
           "El documento de ensamble (ASM-1 §2) tal como se verificó, su formato y el "
           "resumen canónico que nombra esta revisión del ensamble."),
        _t("assembly-mates", "Assembly mates", "Acoplamientos del ensamble",
           "Accouplements de l'assemblage", "Acoplamentos da montagem",
           "Every mate of an assembly between two component interfaces, with its stated "
           "rotation, the closure residuals the keystone measured and the verdict.",
           "Cada acoplamiento de un ensamble entre dos interfaces de componentes, con su "
           "rotación declarada, los residuos de cierre que midió la piedra angular y el "
           "veredicto."),
        _t("assembly-placement", "Assembly placement", "Colocación del ensamble",
           "Placement de l'assemblage", "Posicionamento da montagem",
           "The world transform of each component of an assembly: a 4 × 4 matrix from the "
           "component's model frame to the assembly's, in millimetres.",
           "La transformación al mundo de cada componente de un ensamble: una matriz 4 × 4 "
           "del marco de modelo del componente al del ensamble, en milímetros."),
        _t("capability-description", "Capability description", "Descripción de capacidades",
           "Description des capacités", "Descrição de capacidades",
           "What a producer machine can fabricate, keyed by the fabrication-capabilities "
           "vocabulary.",
           "Lo que una máquina productora puede fabricar, con las claves del vocabulario "
           "fabrication-capabilities."),
        _t("material-data", "Material data", "Datos de material", "Données matériau",
           "Dados de material",
           "A material card: identity, classification (EMMO class) and the card's "
           "compensation, physical and thermal blocks.",
           "Una ficha de material: identidad, clasificación (clase EMMO) y los bloques de "
           "compensación, físicos y térmicos de la ficha."),
    )
}


@dataclass(frozen=True)
class Conformance:
    submodel: str
    claimed: str  # "idta" | "madfam"
    semantic_id: str
    idta_semantic_id: str | None
    missing: tuple[str, ...]


def _semantic(el: dict) -> str | None:
    sid = el.get("semanticId") or {}
    keys = sid.get("keys") or []
    return keys[0].get("value") if keys else None


def _children(el: dict) -> list[dict]:
    if el.get("modelType") == "Entity":
        return el.get("statements") or []
    if "submodelElements" in el:
        return el.get("submodelElements") or []
    value = el.get("value")
    return value if isinstance(value, list) and el.get("modelType") in (
        "SubmodelElementCollection", "SubmodelElementList") else []


def missing_mandatory(submodel: dict, template: IdtaTemplate) -> list[str]:
    """The mandatory semanticId paths of ``template`` absent from ``submodel``."""
    missing = []
    for path in template.mandatory:
        level = [submodel]
        for sid in path:
            level = [c for parent in level for c in _children(parent) if _semantic(c) == sid]
            if not level:
                break
        if not level:
            missing.append(" / ".join(path))
    return missing


def apply_conformance(submodel: dict, madfam: str, idta: str | None) -> Conformance:
    """Set ``semanticId`` (and the supplemental one) by the conformance-claim rule."""
    template = MADFAM[madfam]
    idta_t = IDTA[idta] if idta else None
    missing = missing_mandatory(submodel, idta_t) if idta_t else []
    claim_idta = idta_t is not None and not missing
    if claim_idta:
        semantic, version = idta_t.submodel_semantic_id, idta_t.version
        supplemental = [template.id]
    else:
        semantic, version = template.id, (str(template.major), str(template.minor))
        supplemental = [idta_t.submodel_semantic_id] if idta_t else []
    submodel["semanticId"] = external_ref(semantic)
    if supplemental:
        submodel["supplementalSemanticIds"] = [external_ref(s) for s in supplemental]
    else:
        submodel.pop("supplementalSemanticIds", None)
    submodel["administration"] = {
        "version": version[0], "revision": version[1], "templateId": semantic,
    }
    return Conformance(
        submodel=submodel.get("idShort", ""),
        claimed="idta" if claim_idta else "madfam",
        semantic_id=semantic,
        idta_semantic_id=idta_t.submodel_semantic_id if idta_t else None,
        missing=tuple(missing),
    )
