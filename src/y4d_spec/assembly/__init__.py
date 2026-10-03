"""Type-level assemblies (ASM-1 §2–§3): resolve, place, and check every mate.

    from y4d_spec.assembly import CompositeResolver, validate_assembly

    resolver = CompositeResolver.for_directories(commons="solid-hyperobjects",
                                                 standard_parts="standard-parts")
    report = validate_assembly(doc, resolver)
    report.ok, report.errors, report.placements["motor"], report.digest

`validate_assembly` is a pure function of the document and a `ComponentResolver`; it
reads no file itself. The AAS projection and the asset-shells service call it with a
resolver over whatever store holds their components. See docs/ASSEMBLIES.md.
"""

from .digest import ASSEMBLY_DIGEST_ALGORITHM, assembly_digest
from .resolution import (
    ComponentResolver,
    ResolutionError,
    ResolvedComponent,
    ResolvedInterface,
    cartridge_identity,
    goc1_variables,
    parameter_value_problems,
    resolve_interfaces,
    resolve_size_key,
)
from .resolvers import (
    CommonsManifestResolver,
    CompositeResolver,
    ExternalResolver,
    StandardPartsResolver,
)
from .validate import (
    ANGLE_TOLERANCE_DEG,
    ORIGIN_TOLERANCE_MM,
    AssemblyFinding,
    AssemblyReport,
    MateCheck,
    validate_assembly,
)

__all__ = [
    "ANGLE_TOLERANCE_DEG",
    "ASSEMBLY_DIGEST_ALGORITHM",
    "ORIGIN_TOLERANCE_MM",
    "AssemblyFinding",
    "AssemblyReport",
    "CommonsManifestResolver",
    "ComponentResolver",
    "CompositeResolver",
    "ExternalResolver",
    "MateCheck",
    "ResolutionError",
    "ResolvedComponent",
    "ResolvedInterface",
    "StandardPartsResolver",
    "assembly_digest",
    "cartridge_identity",
    "goc1_variables",
    "parameter_value_problems",
    "resolve_interfaces",
    "resolve_size_key",
    "validate_assembly",
]
