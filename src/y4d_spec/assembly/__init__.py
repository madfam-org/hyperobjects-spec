"""Type-level assemblies (ASM-1 §2–§3): resolve, place, and check every mate.

    from y4d_spec.assembly import CompositeResolver, validate_assembly

    resolver = CompositeResolver.for_directories(commons="solid-hyperobjects",
                                                 standard_parts="standard-parts")
    report = validate_assembly(doc, resolver)
    report.ok, report.errors, report.placements["motor"], report.digest

ASM-1 §9 (v1.3) adds joints on mates, machine-axis bindings, belt paths and the pose
sweep (`kinematics`, `paths`), and the reference forward kinematics:

    pose(doc, resolver, {"x_carriage": 25.0})        # {component id: 4×4}
    pose_from_axes(doc, resolver, {"x": 25.0})       # through machine.axes
    golden_poses(doc, report)                        # the parity file for viewers
    kinematic_model(doc, report)                     # what a viewer poses from

`validate_assembly` is a pure function of the document and a `ComponentResolver`; it
reads no file itself. The AAS projection and the asset-shells service call it with a
resolver over whatever store holds their components. See docs/ASSEMBLIES.md.
"""

from .digest import ASSEMBLY_DIGEST_ALGORITHM, assembly_digest
from .kinematics import (
    POSE_SAMPLES,
    POSE_SEED,
    Joint,
    PoseError,
    PoseSpec,
    joint_values,
    joints_of,
    pose_sweep,
)
from .paths import PathResult
from .posing import (
    compile_kinematics,
    format_number,
    golden_poses,
    golden_poses_json,
    kinematic_model,
    kinematic_model_json,
    pose,
    pose_from_axes,
)
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
    slider_size_key_miss,
)
from .resolvers import (
    CommonsManifestResolver,
    CompositeResolver,
    ExternalResolver,
    FirstOfResolver,
    StandardPartsResolver,
)
from .validate import (
    ANGLE_TOLERANCE_DEG,
    ORIGIN_TOLERANCE_MM,
    AssemblyFinding,
    AssemblyReport,
    KinematicModel,
    MateCheck,
    PoseResult,
    validate_assembly,
)

__all__ = [
    "ANGLE_TOLERANCE_DEG",
    "ASSEMBLY_DIGEST_ALGORITHM",
    "ORIGIN_TOLERANCE_MM",
    "POSE_SAMPLES",
    "POSE_SEED",
    "AssemblyFinding",
    "AssemblyReport",
    "CommonsManifestResolver",
    "ComponentResolver",
    "CompositeResolver",
    "ExternalResolver",
    "FirstOfResolver",
    "Joint",
    "KinematicModel",
    "MateCheck",
    "PathResult",
    "PoseError",
    "PoseResult",
    "PoseSpec",
    "ResolutionError",
    "ResolvedComponent",
    "ResolvedInterface",
    "StandardPartsResolver",
    "assembly_digest",
    "cartridge_identity",
    "compile_kinematics",
    "format_number",
    "goc1_variables",
    "golden_poses",
    "golden_poses_json",
    "joint_values",
    "joints_of",
    "kinematic_model",
    "kinematic_model_json",
    "parameter_value_problems",
    "pose",
    "pose_from_axes",
    "pose_sweep",
    "resolve_interfaces",
    "resolve_size_key",
    "slider_size_key_miss",
    "validate_assembly",
]
