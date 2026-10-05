"""Reference forward kinematics and the golden pose files (ASM-1 §9, contract v1.3).

    from y4d_spec.assembly import pose, pose_from_axes
    transforms = pose(doc, resolver, {"x_carriage": 25.0, "gantry_y": -40.0})
    transforms["toolhead"]           # 4×4, row-major, world ← component, mm
    pose_from_axes(doc, resolver, {"x": 25.0, "y": -40.0})   # through `machine.axes`

This is the reference: the viewer (yantra4d, Phase 7) computes poses itself and proves
parity against the golden pose files written by `golden_poses` — the keystone's numbers,
formatted so that both languages produce the same strings (`format_number`).

**Golden pose file** (`hyperobjects.assembly-poses` 1.0.0), one per assembly:

    {"format": "hyperobjects.assembly-poses", "format_version": "1.0.0",
     "assembly": <slug>, "assembly_digest": <sha256>,
     "matrix_layout": "row-major 4x4, world <- component, mm",
     "number_format": "...", "sweep": {"sequence": "halton", "samples": N, "seed": S},
     "joints": [{"id", "type", "axis", "role", "unit"}...],
     "poses": [{"name": "home", "kind": "home",
                "inputs": {<driven joint>: <number>, ...},          # what the viewer is given
                "joints": {<driven or follower joint>: "<fixed>"},  # what it must compute
                "transforms": {<component>: ["<fixed>" × 16], ...}}, ...],
     "tie_guard": ["<pose>/<component>/<index>", ...]}

`inputs` are JSON numbers (shortest round-trip form, so every language parses the same
double). Every computed number is a STRING in the canonical fixed format: the exact binary
value rounded to 6 decimals, ties away from zero, "-0.000000" written "0.000000" —
JavaScript's `Number.prototype.toFixed(6)` gives exactly this. `tie_guard` lists the
entries within 1e-9 of a rounding boundary, where a last-ulp difference between two
correct implementations may flip the sixth decimal; a parity test compares those
numerically (|Δ| ≤ 1e-6) and every other entry as a string. Passive joints are not
listed: they place nothing (a viewer never needs their value).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal

from .kinematics import PoseError, axis_joint_values, pose_sweep
from .resolution import ComponentResolver
from .transforms import Matrix
from .validate import AssemblyReport, KinematicModel, validate_assembly

__all__ = [
    "POSES_FORMAT",
    "POSES_FORMAT_VERSION",
    "compile_kinematics",
    "format_number",
    "golden_poses",
    "golden_poses_json",
    "pose",
    "pose_from_axes",
]

POSES_FORMAT = "hyperobjects.assembly-poses"
POSES_FORMAT_VERSION = "1.0.0"
NUMBER_FORMAT = ("decimal string with exactly 6 places: the exact binary value rounded half "
                 "away from zero (JavaScript Number.prototype.toFixed(6)); -0.000000 is "
                 "written 0.000000")
_QUANTUM = Decimal("0.000001")
#: How close (in units of the sixth decimal) to a rounding boundary an entry is listed in
#: `tie_guard`: 1e-3 of 1e-6 mm is 1e-9 mm, far above double-precision noise at the
#: coordinates an assembly reaches.
_TIE_WINDOW = 1e-3


def format_number(value: float) -> str:
    """The canonical fixed format of the golden pose files (see the module docstring)."""
    text = str(Decimal(value).quantize(_QUANTUM, rounding=ROUND_HALF_UP))
    return "0.000000" if text == "-0.000000" else text


def _near_tie(value: float) -> bool:
    scaled = abs(value) * 1_000_000.0
    return abs((scaled - int(scaled)) - 0.5) < _TIE_WINDOW


def compile_kinematics(document: object, resolver: ComponentResolver, *, pose_samples: int = 0
                       ) -> tuple[AssemblyReport, KinematicModel]:
    """Validate the document (with `pose_samples` Halton samples; 0 checks home and the
    limits) and return the report and its kinematic model. Raises PoseError when the
    assembly does not pass: a pose of a failing assembly would describe nothing real."""
    report = validate_assembly(document, resolver, pose_samples=pose_samples)
    if not report.ok or report.kinematics is None:
        problems = "; ".join(str(f) for f in report.errors[:5]) or "it could not be placed"
        raise PoseError(f"the assembly does not pass its check ({len(report.errors)} "
                        f"error(s)): {problems}")
    return report, report.kinematics


def pose(document: object, resolver: ComponentResolver,
         joint_values: Mapping[str, object] | None = None) -> dict[str, Matrix]:
    """`{component id: 4×4}` with the driven joints at `joint_values` (any joint not
    given stays at home; followers are computed). Raises PoseError on an unknown, passive
    or follower joint, a non-finite value, a value outside a joint's limits (never
    clamped), or an assembly that does not pass."""
    _report, model = compile_kinematics(document, resolver)
    return model.place(model.values(joint_values))


def pose_from_axes(document: object, resolver: ComponentResolver,
                   axis_values: Mapping[str, object]) -> dict[str, Matrix]:
    """`pose` driven by machine axis values through the document's `machine.axes`
    (joint = scale · axis + offset). Raises PoseError on an unbound axis."""
    if not isinstance(document, Mapping):
        raise PoseError("the document is not an object")
    return pose(document, resolver, axis_joint_values(document, axis_values))


def golden_poses(document: Mapping, report: AssemblyReport) -> dict:
    """The golden pose file of a passing assembly: every pose of its sweep (home, the
    limits, the Halton samples at the report's sample count and seed)."""
    model = report.kinematics
    if not report.ok or model is None:
        raise PoseError("golden poses are written only for an assembly that passes")
    components = [c["id"] for c in document["components"]]
    listed = [j for j in report.joints if j.role != "passive"]
    poses, guard = [], []
    for spec in pose_sweep(report.joints, report.pose_samples, report.pose_seed):
        values = model.values(spec.driven)
        placements = model.place(values)
        transforms = {}
        for cid in components:
            flat = [v for row in placements[cid] for v in row]
            transforms[cid] = [format_number(v) for v in flat]
            guard += [f"{spec.name}/{cid}/{i}" for i, v in enumerate(flat) if _near_tie(v)]
        joints = {j.id: format_number(values[j.id]) for j in listed}
        guard += [f"{spec.name}/joint/{j.id}" for j in listed if _near_tie(values[j.id])]
        poses.append({"name": spec.name, "kind": spec.kind, "inputs": dict(spec.driven),
                      "joints": joints, "transforms": transforms})
    return {
        "format": POSES_FORMAT,
        "format_version": POSES_FORMAT_VERSION,
        "assembly": document.get("slug"),
        "assembly_digest": report.digest,
        "matrix_layout": "row-major 4x4, world <- component, mm",
        "number_format": NUMBER_FORMAT,
        "sweep": {"sequence": "halton", "samples": report.pose_samples,
                  "seed": report.pose_seed},
        "joints": [{"id": j.id, "type": j.type, "axis": j.axis, "role": j.role,
                    "unit": j.unit} for j in listed],
        "poses": poses,
        "tie_guard": guard,
    }


def golden_poses_json(document: Mapping, report: AssemblyReport) -> str:
    """`golden_poses` as the file's exact text: sorted keys, one-space indent, UTF-8, a
    final newline."""
    return json.dumps(golden_poses(document, report), indent=1, sort_keys=True,
                      ensure_ascii=False) + "\n"
