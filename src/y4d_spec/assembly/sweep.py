"""The ASM-1 §9 (v1.3) steps of `validate_assembly`: belt paths and the pose sweep.

`validate.py` places the assembly and checks closure at the home pose; this module checks
the declared paths (statically, at resolution, and at every pose) and runs the rest of the
pose sweep through the compiled `KinematicModel`, turning failures into findings:

* `path` (error) — a path that names no belt, a via that is not a pulley with a
  `belt_engagement`, a side a part cannot take, overlapping circles, a non-planar path;
* `pose-closure` (error) — a mate that holds at home but not at some pose of the sweep,
  one finding per mate naming the first failing pose and the count;
* `joint-limit` (error) — a passive joint's measured value, or a follower's computed one,
  outside its limits (within the mating rule's tolerance);
* `path-length` (warning) — a path whose length varies across the sweep, or a closed-loop
  belt whose home length differs from its catalog loop length.

The functions take the report and the model by duck type, so this module never imports
`validate` (which imports it).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .kinematics import pose_sweep
from .paths import (
    PATH_PLANARITY_MM,
    PathGeometryError,
    PathResult,
    effective_diameter,
    path_length,
    path_vias,
)
from .resolution import ResolutionError
from .tolerances import ANGLE_TOLERANCE_DEG, ORIGIN_TOLERANCE_MM
from .transforms import Matrix

__all__ = [
    "PoseResult",
    "limit_findings",
    "measure_paths",
    "path_static_step",
    "pose_result",
    "resolve_paths",
    "sweep_step",
]


@dataclass
class PoseResult:
    """One pose of the sweep (ASM-1 §9): the joint values, and whether everything closed."""

    name: str
    kind: str  # "home" | "limit" | "sample"
    joints: dict[str, float] = field(default_factory=dict)  # every joint, passive measured
    ok: bool = True
    worst_origin_mm: float = 0.0
    worst_angle_deg: float = 0.0
    failing_mates: list[str] = field(default_factory=list)
    limit_violations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pose": self.name, "kind": self.kind,
            "joints": {k: round(v, 6) + 0.0 for k, v in self.joints.items()},
            "ok": self.ok, "worst_origin_mm": round(self.worst_origin_mm, 6) + 0.0,
            "worst_angle_deg": round(self.worst_angle_deg, 6) + 0.0,
            "failing_mates": self.failing_mates, "limit_violations": self.limit_violations,
        }




def path_static_step(doc: Mapping, report) -> None:
    ids = {c["id"] for c in doc["components"]}
    seen: set[str] = set()
    for path in doc.get("paths") or []:
        pid = path["id"]
        if pid in seen:
            report._err("path", "path id is used more than once", pid)
        seen.add(pid)
        vias = path_vias(path)
        for via in vias:
            if via.component not in ids:
                report._err("path", f"via '{via.component}' is not a component", pid)
        anchors = [i for i, v in enumerate(vias) if v.is_anchor]
        if path["closed"]:
            if anchors:
                report._err("path", "a closed path has no anchors: every via is a pulley "
                                    "or an idler", pid)
        else:
            if anchors != [0, len(vias) - 1]:
                report._err("path", "an open path starts and ends at an anchor "
                                    "({component, interface}) and has none between", pid)


def resolve_paths(doc: Mapping, resolver, report) -> dict[str, dict]:
    """Resolve every path's belt part and vias; returns, per resolvable path, what the
    length needs. Problems are `path` errors; the belt's identity enters the digest."""
    out: dict[str, dict] = {}
    report._path_parts = {}
    for path in doc.get("paths") or []:
        pid, vias = path["id"], path_vias(path)
        result = PathResult(pid, path["part"], path["closed"], vias)
        report.paths.append(result)
        problems: list[str] = []
        belt = None
        try:
            resolved = resolver.resolve({"id": pid, "source": {"type": "standard",
                                                               "key": path["part"]}})
            report._path_parts[pid] = resolved.identity
            belt = resolved.belt
            if belt is None:
                problems.append(f"part '{path['part']}' is not a belt (category belt with a "
                                "belt block of pitch and width in mm)")
            else:
                result.pitch_mm = belt["pitch_mm"]
                result.loop_length_mm = belt.get("loop_length_mm")
                if result.loop_length_mm is not None and not path["closed"]:
                    problems.append(f"part '{path['part']}' is a closed-loop belt (loop_length "
                                    f"{result.loop_length_mm:g} mm): its path must be closed")
        except ResolutionError as exc:
            problems += [f"part: {p}" for p in exc.problems]
        except Exception as exc:  # a resolver bug is a finding, never a crash
            problems.append(f"part: the resolver failed: {type(exc).__name__}: {exc}")
        engagements, anchors, diameters = {}, {}, []
        for via in vias:
            comp = report.components.get(via.component)
            if comp is None:
                problems.append(f"via '{via.component}' did not resolve")
                diameters.append(None)
                continue
            if via.is_anchor:
                iface = comp.interfaces.get(via.interface)
                if iface is None or iface.frame is None:
                    problems.append(f"anchor '{via.component}.{via.interface}' is not an "
                                    "interface with a frame")
                else:
                    anchors[(via.component, via.interface)] = iface.frame.homogeneous()
                diameters.append(None)
                continue
            engagement = comp.belt_engagement
            if engagement is None:
                problems.append(f"via '{via.component}' ({comp.label}) declares no "
                                "belt_engagement: a belt path passes only through catalog "
                                "parts with a cited pitch or running diameter")
                diameters.append(None)
                continue
            engagements[via.component] = engagement
            if belt is None:
                diameters.append(None)
                continue
            try:
                diameters.append(effective_diameter(via, engagement, belt))
            except PathGeometryError as exc:
                problems.append(str(exc))
                diameters.append(None)
        for problem in problems:
            report._err("path", problem, pid)
        if not problems:
            out[pid] = {"vias": vias, "closed": path["closed"], "engagements": engagements,
                        "anchors": anchors, "diameters": diameters, "result": result}
    return out


def measure_paths(paths: Mapping[str, dict], placements: Mapping[str, Matrix],
                   pose: str, report, failed: set[str]) -> None:
    for pid, p in paths.items():
        if pid in failed or any(v.component not in placements for v in p["vias"]):
            continue
        result: PathResult = p["result"]
        try:
            length, planarity, axis_deg, normal = path_length(
                p["vias"], p["closed"], placements, p["engagements"], p["anchors"],
                p["diameters"])
        except PathGeometryError as exc:
            report._err("path", f"at pose {pose}: {exc}", pid)
            failed.add(pid)
            continue
        result.lengths[pose] = length
        if pose == "home":
            result.length_mm, result.planarity_mm = length, planarity
            result.axis_deg, result.normal = axis_deg, normal
            if planarity > PATH_PLANARITY_MM:
                report._err("path", f"the vias spread {planarity:.4f} mm along the path normal "
                                    f"at home (≤ {PATH_PLANARITY_MM} mm, a convention): the "
                                    "path is not planar", pid)
                failed.add(pid)


def _limit_violations(report, values: Mapping[str, float]) -> list[str]:
    out = []
    for j in report.joints:
        if j.role == "driven" or j.id not in values:
            continue
        tolerance = ORIGIN_TOLERANCE_MM if j.type == "prismatic" else ANGLE_TOLERANCE_DEG
        if not j.within_limits(values[j.id], tolerance):
            out.append(j.id)
    return out


def pose_result(name: str, kind: str, values: Mapping[str, float], checks: list,
                 report) -> PoseResult:
    joints = dict(values)
    for check in checks:
        if check.joint is not None and check.joint_value is not None:
            joints[check.joint] = check.joint_value
    order = [j.id for j in report.joints]
    result = PoseResult(name, kind, {k: joints[k] for k in order if k in joints})
    for check in checks:
        if check.origin_mm is None:
            continue
        result.worst_origin_mm = max(result.worst_origin_mm, check.origin_mm)
        result.worst_angle_deg = max(result.worst_angle_deg, check.normal_deg,
                                     check.x_axis_deg or 0.0)
        if not check.ok:
            result.failing_mates.append(check.mate_id)
    result.limit_violations = _limit_violations(report, result.joints)
    result.ok = not result.failing_mates and not result.limit_violations
    return result


def _describe(values: Mapping[str, float], report) -> str:
    units = {j.id: j.unit for j in report.joints}
    return ", ".join(f"{k}={round(v, 4) + 0.0:g} {units.get(k, '')}".rstrip()
                     for k, v in values.items())


def sweep_step(model, report, paths: Mapping[str, dict],
                failed_paths: set[str]) -> None:
    """Every pose but home (already checked): limits, then the Halton samples."""
    failures: dict[str, list[tuple[PoseResult, object]]] = {}
    limits: dict[str, list[PoseResult]] = {}
    for spec in pose_sweep(report.joints, report.pose_samples, report.pose_seed)[1:]:
        values = model.values(spec.driven, check_limits=False)
        placements, checks = model.evaluate(values)
        result = pose_result(spec.name, spec.kind, values, checks, report)
        report.poses.append(result)
        for check in checks:
            if check.origin_mm is not None and not check.ok:
                failures.setdefault(check.mate_id, []).append((result, check))
        for jid in result.limit_violations:
            limits.setdefault(jid, []).append(result)
        measure_paths(paths, placements, spec.name, report, failed_paths)
    total = len(report.poses)
    for mate_id, rows in failures.items():
        result, check = rows[0]
        parts = [f"origins {check.origin_mm:.4f} mm apart (≤ {ORIGIN_TOLERANCE_MM})",
                 f"normals {check.normal_deg:.4f}° from antiparallel (≤ {ANGLE_TOLERANCE_DEG})"]
        if check.x_axis_deg is not None:
            parts.append(f"x-axes {check.x_axis_deg:.4f}° apart (≤ {ANGLE_TOLERANCE_DEG})")
        report._err(
            "pose-closure",
            f"{check.a} ↔ {check.b} does not hold at {len(rows)} of {total} poses; first at "
            f"{result.name} ({_describe(result.joints, report)}): " + "; ".join(parts),
            mate_id,
        )
    limit_findings(report, limits, total)


def limit_findings(report, limits: Mapping[str, list[PoseResult]],
                    total: int) -> None:
    by_id = {j.id: j for j in report.joints}
    for jid, rows in limits.items():
        joint, first = by_id[jid], rows[0]
        report._err(
            "joint-limit",
            f"the {joint.role} joint's value leaves its limits [{joint.limits[0]:g}, "
            f"{joint.limits[1]:g}] {joint.unit} at {len(rows)} of {total} poses; first at "
            f"{first.name}: {jid} = {round(first.joints[jid], 4) + 0.0:g} {joint.unit}",
            jid,
        )
