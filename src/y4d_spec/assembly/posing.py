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
    "KINEMATICS_FORMAT",
    "KINEMATICS_FORMAT_VERSION",
    "POSES_FORMAT",
    "POSES_FORMAT_VERSION",
    "compile_kinematics",
    "format_number",
    "golden_poses",
    "golden_poses_json",
    "kinematic_model",
    "kinematic_model_json",
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


# ── the compiled kinematic model, a consumable export (ASM-1 §9) ───────────────
KINEMATICS_FORMAT = "hyperobjects.assembly-kinematics"
KINEMATICS_FORMAT_VERSION = "1.0.0"
KINEMATICS_NUMBER_FORMAT = ("JSON numbers: the shortest decimal that round-trips the binary64 "
                            "value (Python repr), so every IEEE-754 parser reads the same "
                            "double")
#: How a consumer places the components, stated in the file so that it travels with the
#: numbers. It is `validate._place`, word for word.
KINEMATICS_PLACEMENT = (
    "Breadth-first from `root` (placed at the identity). Pop a component; walk `edges` in "
    "order; skip an edge that does not touch it or whose joint is passive. With "
    "M = Flip·Rz(theta_deg) (Flip: a turn of pi about x) and J = J(q) of the edge's joint "
    "(q = its value, 0 when absent; prismatic: q mm along the axis; revolute: q degrees "
    "about it, right-handed): if the popped component is side a and b is unplaced, "
    "T_b = T_a·H_a·J·M·H_b^-1 (no J for a rigid edge); if it is side b and a is unplaced, "
    "T_a = T_b·H_b·M·J^-1·H_a^-1. Enqueue the newly placed component. H_a and H_b already "
    "carry any mate offset. Joint values: a driven joint takes its input (else `home`); a "
    "follower is offset + sum(scale·leader), leaders first; a machine axis gives "
    "joint = scale·axis + offset.")


def _geometry_export(resolved, component: Mapping) -> dict | None:
    """What a viewer can draw for a component: an evaluated envelope (numbers in the
    component's model frame), a cartridge to render (no local path), or None."""
    geometry = getattr(resolved, "geometry", None)
    if not geometry:
        return None
    if geometry.get("kind") == "envelope":
        return {"kind": "envelope", "solids": geometry["solids"]}
    if geometry.get("kind") == "cartridge":
        source = component.get("source") or {}
        return {"kind": "cartridge", "commons": source.get("commons"),
                "slug": source.get("slug"), "mode": source.get("mode"),
                "instance_id": (resolved.identity or {}).get("instance_id"),
                "parts": list(geometry.get("parts") or []),
                "parameters": dict(geometry.get("parameters") or {})}
    return None


def kinematic_model(document: Mapping, report: AssemblyReport) -> dict:
    """The compiled kinematic model of a passing assembly, as plain data: everything
    `KinematicModel.place` uses (the root, the edges in order with their frame matrices
    and mate angles, the joints) plus the machine bindings and each component's drawable
    geometry. A viewer that applies `placement` to it reproduces `golden_poses`.

    `hyperobjects.assembly-kinematics` 1.0.0: matrices are row-major 4×4 flattened to 16
    numbers; every number is a JSON number (`KINEMATICS_NUMBER_FORMAT`)."""
    from .kinematics import machine_bindings  # noqa: PLC0415 — keep the import list short
    from .validate import _frames  # noqa: PLC0415 — the same frames `_place` uses

    model = report.kinematics
    if not report.ok or model is None:
        raise PoseError("a kinematic model is written only for an assembly that passes")
    edges = []
    for mate, check, ia, ib, joint in model.edges:
        h_a, h_b = _frames(mate, ia, ib)
        edges.append({
            "mate": mate["id"], "a": mate["a"]["component"], "b": mate["b"]["component"],
            "theta_deg": check.theta_deg,
            "h_a": [v for row in h_a for v in row], "h_b": [v for row in h_b for v in row],
            "joint": None if joint is None else joint.id,
        })
    joints = [{
        "id": j.id, "mate": j.mate_id, "type": j.type, "axis": j.axis, "role": j.role,
        "unit": j.unit, "parent": j.parent, "child": j.child,
        "limits": None if j.limits is None else list(j.limits), "home": j.home,
        "follows": None if not j.follows else {
            "terms": [{"joint": leader, "scale": scale} for leader, scale in j.follows],
            "offset": j.follow_offset},
    } for j in model.joints]
    machine = document.get("machine")
    components = []
    for component in document["components"]:
        resolved = report.components[component["id"]]
        components.append({"id": component["id"], "source_type": resolved.source_type,
                           "label": resolved.label,
                           "geometry": _geometry_export(resolved, component)})
    return {
        "format": KINEMATICS_FORMAT,
        "format_version": KINEMATICS_FORMAT_VERSION,
        "assembly": document.get("slug"),
        "assembly_digest": report.digest,
        "matrix_layout": "row-major 4x4 flattened to 16, column vectors, mm",
        "number_format": KINEMATICS_NUMBER_FORMAT,
        "placement": KINEMATICS_PLACEMENT,
        "root": model.root,
        "components": components,
        "edges": edges,
        "joints": joints,
        "machine": None if machine is None else {
            "kinematics": machine.get("kinematics"),
            "axes": [{"axis": b["axis"], "joint": b["joint"], "scale": b["scale"],
                      "offset": b["offset"]} for b in machine_bindings(document)],
        },
    }


def kinematic_model_json(document: Mapping, report: AssemblyReport) -> str:
    """`kinematic_model` as the file's exact text: sorted keys, one-space indent, UTF-8,
    a final newline (the same layout as the golden pose files)."""
    return json.dumps(kinematic_model(document, report), indent=1, sort_keys=True,
                      ensure_ascii=False, allow_nan=False) + "\n"
