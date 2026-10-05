"""`y4d-spec assembly check <assembly.json> --commons <dir> [--standard-parts <dir>] [--json]`.

Prints the placement table (every component's world ← component transform), the mate
table with its closure residuals, every finding, and a summary line:

    y4d-spec assembly check: <slug> components=N placed=P mates=M closed=C errors=E
        warnings=W collision=not run joints=J poses=OK/TOTAL paths=K digest=<sha256 | none>

With joints (ASM-1 §9, v1.3) it also prints the joint table, the pose sweep (one line
per pose) and every declared path with its pitch-line length. `--pose-samples N` sets
the Halton part of the sweep (default 16, a convention).

    y4d-spec assembly poses <assembly.json> --commons DIR [--standard-parts DIR] [--out F]

writes the golden pose file (`hyperobjects.assembly-poses`, see posing.py) of a passing
assembly: the reference forward kinematics at every pose of the sweep.

Exit 0 iff there is no error; 1 on any error; 2 when the document cannot be read or a
directory option does not exist. `--collision` (ASM-1 §3.7) checks rigid-body interference
at every pose of the sweep and needs the geometry extra; `collision=checked`, `partial`
(some component had no solid, named in a warning) or `unavailable` — never a silent pass.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .kinematics import POSE_SAMPLES
from .resolvers import CompositeResolver
from .transforms import round_matrix
from .validate import AssemblyReport, validate_assembly

__all__ = ["add_assembly_parser", "report_as_dict"]


def report_as_dict(doc: dict, report: AssemblyReport) -> dict:
    """The report as plain JSON (the `--json` output)."""
    return {
        "slug": doc.get("slug") if isinstance(doc, dict) else None,
        "ok": report.ok,
        "digest": report.digest,
        "collision": report.collision,
        "collision_pairs": getattr(report.collision_result, "pairs", None),
        "collision_unchecked": getattr(report.collision_result, "unchecked", None),
        "errors": [
            {"code": f.code, "subject": f.subject, "message": f.message} for f in report.errors
        ],
        "warnings": [
            {"code": f.code, "subject": f.subject, "message": f.message} for f in report.warnings
        ],
        "components": {
            cid: {
                "source": rc.source_type,
                "label": rc.label,
                "identity": rc.identity,
                "transform": round_matrix(report.placements[cid])
                if cid in report.placements
                else None,
            }
            for cid, rc in report.components.items()
        },
        "mates": [m.as_dict() for m in report.mates],
        "joints": [
            {"id": j.id, "mate": j.mate_id, "type": j.type, "axis": j.axis, "role": j.role,
             "unit": j.unit, "limits": list(j.limits) if j.limits else None, "home": j.home,
             "follows": [{"joint": k, "scale": v} for k, v in j.follows],
             "follow_offset": j.follow_offset}
            for j in report.joints
        ],
        "pose_sweep": {"sequence": "halton", "samples": report.pose_samples,
                       "seed": report.pose_seed},
        "poses": [p.as_dict() for p in report.poses],
        "paths": [p.as_dict() for p in report.paths],
    }


def _fmt(v: float) -> str:
    return f"{round(v, 4) + 0.0:.4f}"


def _rotation_summary(m) -> str:
    """Axis-angle of the rotation block, for a human reader (the matrix is in --json)."""
    trace = m[0][0] + m[1][1] + m[2][2]
    angle = math.degrees(math.acos(max(-1.0, min(1.0, (trace - 1.0) / 2.0))))
    if angle < 1e-6:
        return "none"
    if abs(angle - 180.0) < 1e-6:
        diag = [math.sqrt(max(0.0, (m[i][i] + 1.0) / 2.0)) for i in range(3)]
        k = max(range(3), key=lambda i: diag[i])
        axis = [diag[i] if i == k else m[k][i] / (2.0 * diag[k]) for i in range(3)]
    else:
        s = 2.0 * math.sin(math.radians(angle))
        axis = [(m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s]
    return f"{angle:.3f}° about ({', '.join(_fmt(a) for a in axis)})"


def _print_text(doc: dict, report: AssemblyReport) -> None:
    if report.components:
        print("  placement (world ← component, mm):")
        width = max(len(c) for c in report.components)
        for cid, rc in report.components.items():
            m = report.placements.get(cid)
            if m is None:
                print(f"    {cid:<{width}}  NOT PLACED  {rc.label}")
                continue
            t = f"({_fmt(m[0][3])}, {_fmt(m[1][3])}, {_fmt(m[2][3])})"
            print(f"    {cid:<{width}}  t={t}  R={_rotation_summary(m)}  {rc.label}")
    if report.mates:
        print("  mates (residuals: origin mm, normal °, x-axis ° modulo symmetry):")
        for mc in report.mates:
            if mc.origin_mm is None:
                print(f"    {mc.mate_id}: {mc.a} ↔ {mc.b}  NOT CHECKED (see errors)")
                continue
            if mc.x_axis_deg is not None:
                x = f"{mc.x_axis_deg:.4f}"
            else:
                x = "n/a (continuous, no x_axis)" if mc.symmetry == 0 else "n/a"
            role = "tree" if mc.in_tree else "cycle"
            verdict = "ok" if mc.ok else "FAIL"
            print(
                f"    {mc.mate_id}: {mc.a} ↔ {mc.b}  sym={mc.symmetry} "
                f"θ={mc.theta_deg:g}° [{role}]  origin={mc.origin_mm:.4f} "
                f"normal={mc.normal_deg:.4f} x={x}  {verdict}"
            )
    if report.joints:
        print("  joints (value at home; a passive joint's is measured):")
        home = report.poses[0].joints if report.poses else {}
        for j in report.joints:
            limits = f"[{j.limits[0]:g}, {j.limits[1]:g}]" if j.limits else "continuous"
            value = home.get(j.id)
            shown = f"{round(value, 4) + 0.0:g}" if value is not None else "n/a"
            print(f"    {j.id}: {j.type} along/about {j.axis} of {j.parent} → {j.child} "
                  f"({j.mate_id}) {j.role} {limits} {j.unit} home={shown}")
    if len(report.poses) > 1:
        print(f"  poses (home, limits, {report.pose_samples} Halton samples, seed "
              f"{report.pose_seed}; worst residuals):")
        for p in report.poses:
            verdict = "ok" if p.ok else "FAIL " + ", ".join(p.failing_mates + p.limit_violations)
            print(f"    {p.name}: origin={p.worst_origin_mm:.4f} angle={p.worst_angle_deg:.4f}  "
                  f"{verdict}")
    for path in report.paths:
        if path.length_mm is None:
            print(f"    path {path.path_id}: NOT MEASURED (see errors)")
            continue
        teeth = f" ({path.length_mm / path.pitch_mm:.2f} pitches)" if path.pitch_mm else ""
        loop = f" catalog loop {path.loop_length_mm:g} mm" if path.loop_length_mm else ""
        spread = path.length_spread_mm or 0.0
        print(f"  path {path.path_id}: {path.part} {'closed' if path.closed else 'open'} "
              f"length={path.length_mm:.4f} mm{teeth}{loop} planarity={path.planarity_mm:.4f} "
              f"spread={spread:.4f} {'ok' if path.ok else 'FAIL'}")
    for f in report.errors:
        print(f"  FAIL {f}")
    for f in report.warnings:
        print(f"  warn {f}")


def _cmd_assembly_check(args) -> int:
    path = Path(args.assembly)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"  ERROR {path}: cannot read — {exc}")
        return 2
    for option, value in (("--commons", args.commons),
                          *(("--standard-parts", d) for d in args.standard_parts or ())):
        if value is not None and not Path(value).is_dir():
            print(f"  ERROR {option} {value}: not a directory")
            return 2

    resolver = CompositeResolver.for_directories(args.commons, args.standard_parts)
    report = validate_assembly(doc, resolver, collision=args.collision,
                               pose_samples=args.pose_samples)

    if args.json:
        print(json.dumps(report_as_dict(doc, report), indent=2, ensure_ascii=False))
    else:
        _print_text(doc, report)
        slug = doc.get("slug") if isinstance(doc, dict) else None
        closed = sum(1 for m in report.mates if m.ok)
        print(
            f"y4d-spec assembly check: {slug or path.name} "
            f"components={len(doc.get('components') or []) if isinstance(doc, dict) else 0} "
            f"placed={len(report.placements)} mates={len(report.mates)} closed={closed} "
            f"errors={len(report.errors)} warnings={len(report.warnings)} "
            f"collision={report.collision} joints={len(report.joints)} "
            f"poses={sum(1 for p in report.poses if p.ok)}/{len(report.poses)} "
            f"paths={len(report.paths)} digest={report.digest or 'none'}"
        )
    return 0 if report.ok else 1


def _cmd_assembly_poses(args) -> int:
    from .posing import golden_poses_json

    path = Path(args.assembly)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"  ERROR {path}: cannot read — {exc}")
        return 2
    for option, value in (("--commons", args.commons),
                          *(("--standard-parts", d) for d in args.standard_parts or ())):
        if value is not None and not Path(value).is_dir():
            print(f"  ERROR {option} {value}: not a directory")
            return 2
    resolver = CompositeResolver.for_directories(args.commons, args.standard_parts)
    report = validate_assembly(doc, resolver, pose_samples=args.pose_samples)
    if not report.ok:
        for f in report.errors:
            print(f"  FAIL {f}")
        print(f"y4d-spec assembly poses: {path}: the assembly does not pass; no poses written")
        return 1
    text = golden_poses_json(doc, report)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"y4d-spec assembly poses: wrote {args.out} poses={len(report.poses)}")
    else:
        print(text, end="")
    return 0


def add_assembly_parser(sub, prog: str = "y4d-spec") -> None:
    p_asm = sub.add_parser(
        "assembly", help="type-level assemblies (ASM-1): resolve, place and check every mate"
    )
    asm_sub = p_asm.add_subparsers(dest="assembly_cmd", required=True)
    p_check = asm_sub.add_parser(
        "check",
        help="check an assembly.json: schema, component resolution, mating rule, "
        "placement, closure of every mate, reachability; exit 1 on errors",
    )
    p_check.add_argument("assembly", help="the assembly.json to check")
    p_check.add_argument(
        "--commons",
        metavar="DIR",
        help="the solid commons checkout (<DIR>/<slug>/project.json); needed by any "
        "cartridge component",
    )
    p_check.add_argument(
        "--standard-parts",
        metavar="DIR",
        action="append",
        help="a directory of standard-part JSON entries; needed by any standard component. "
        "Repeatable: directories are tried in order (e.g. the bundled catalog, then local "
        "parts)",
    )
    p_check.add_argument("--json", action="store_true", help="print the report as JSON")
    p_check.add_argument(
        "--collision",
        action="store_true",
        help="check rigid-body interference (ASM-1 §3.7) at home, every limit and the "
        "sweep: cartridges rendered at their parameters, standard parts and external "
        "designs as their envelopes; an overlap above 1 mm³ not declared in "
        "allowed_overlaps is an error (needs the geometry extra)",
    )
    p_check.add_argument(
        "--pose-samples", type=int, default=POSE_SAMPLES, metavar="N",
        help=f"Halton samples of the pose sweep (ASM-1 §9; default {POSE_SAMPLES}, a "
        "convention); home and every joint limit are always checked",
    )
    p_check.set_defaults(func=_cmd_assembly_check)

    p_poses = asm_sub.add_parser(
        "poses",
        help="write the golden pose file of a passing assembly (ASM-1 §9): the reference "
        "forward kinematics at home, every limit and every sample of the sweep",
    )
    p_poses.add_argument("assembly", help="the assembly.json")
    p_poses.add_argument("--commons", metavar="DIR", help="the solid commons checkout")
    p_poses.add_argument("--standard-parts", metavar="DIR", action="append",
                         help="a directory of standard-part JSON entries (repeatable)")
    p_poses.add_argument("--pose-samples", type=int, default=POSE_SAMPLES, metavar="N",
                         help=f"Halton samples (default {POSE_SAMPLES})")
    p_poses.add_argument("--out", metavar="FILE", help="write here instead of stdout")
    p_poses.set_defaults(func=_cmd_assembly_poses)
