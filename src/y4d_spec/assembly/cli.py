"""`y4d-spec assembly check <assembly.json> --commons <dir> [--standard-parts <dir>] [--json]`.

Prints the placement table (every component's world ← component transform), the mate
table with its closure residuals, every finding, and a summary line:

    y4d-spec assembly check: <slug> components=N placed=P mates=M closed=C errors=E
        warnings=W collision=not run digest=<sha256 | none>

Exit 0 iff there is no error; 1 on any error; 2 when the document cannot be read or a
directory option does not exist. `--collision` is accepted and reported as NOT run
(a warning): v1 has no mesh intersection check, and a requested check that did not
run must never read as one that passed.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

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
            x = "n/a (continuous)" if mc.x_axis_deg is None else f"{mc.x_axis_deg:.4f}"
            role = "tree" if mc.in_tree else "cycle"
            verdict = "ok" if mc.ok else "FAIL"
            print(
                f"    {mc.mate_id}: {mc.a} ↔ {mc.b}  sym={mc.symmetry} "
                f"θ={mc.theta_deg:g}° [{role}]  origin={mc.origin_mm:.4f} "
                f"normal={mc.normal_deg:.4f} x={x}  {verdict}"
            )
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
    for option, value in (("--commons", args.commons), ("--standard-parts", args.standard_parts)):
        if value is not None and not Path(value).is_dir():
            print(f"  ERROR {option} {value}: not a directory")
            return 2

    resolver = CompositeResolver.for_directories(args.commons, args.standard_parts)
    report = validate_assembly(doc, resolver, collision=args.collision)

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
            f"collision={report.collision} digest={report.digest or 'none'}"
        )
    return 0 if report.ok else 1


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
        help="a directory of standard-part JSON entries; needed by any standard component",
    )
    p_check.add_argument("--json", action="store_true", help="print the report as JSON")
    p_check.add_argument(
        "--collision",
        action="store_true",
        help="request the mesh-intersection check (ASM-1 §3.7). NOT implemented in v1: "
        "it is reported as not run, with a warning, and never as a pass",
    )
    p_check.set_defaults(func=_cmd_assembly_check)
