"""ho-bridge command-line interface.

    ho-bridge check --fc <fc-repo> --y4d <y4d-repo> [fc-cartridge-dirs...]

Checks every Fashion Cabinet cartridge that declares a linked
`notion.hardware_ref` against a local yantra4d checkout: the slug resolves, the
mapped values evaluate, the hardware solid RENDERS at those values, and each mapped
parameter demonstrably moves the geometry.

Exit code 0 when no link fails; 1 when any link render_fails or has dead params;
2 on a usage / read error. Output is read-proof: it prints how many links it checked
and how many it SKIPPED, so a run that verified nothing can never read like a pass.

A resolve failure is reported and exits nonzero too — but note the summary counts it
separately, because a resolve failure is a manifest bug `fc-spec check` already
catches, while render_fail and dead_params are findings only this tool can make.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import MAX_PROBES, check_bridge


def _cmd_check(args) -> int:
    fc = Path(args.fc)
    y4d = Path(args.y4d)
    for label, path in (("--fc", fc), ("--y4d", y4d)):
        if not path.is_dir():
            print(f"  ERROR {label} {path} is not a directory")
            return 2
    if not (y4d / "projects").is_dir():
        print(f"  ERROR --y4d {y4d} has no projects/ directory — not a yantra4d checkout")
        return 2

    render = not args.no_render
    if render:
        from y4d_spec.geometry import geometry_available

        if not geometry_available():
            print(
                "  ERROR the render steps need the geometry extra: "
                'pip install "hyperobjects-spec[geometry]"  (or pass --no-render for '
                "structural resolution only)"
            )
            return 2

    only = [Path(p) for p in args.cartridges] if args.cartridges else None
    if only:
        for p in only:
            if not (p / "project.json").is_file():
                print(f"  ERROR {p}: no project.json")
                return 2

    counts = {"ok": 0, "resolve_fail": 0, "render_fail": 0, "dead_params": 0, "skipped": 0}
    range_notes: list[str] = []

    def report(v) -> None:
        counts[v.status] += 1
        range_notes.extend(f"{v.fc_slug} → {v.target_slug}: {r}" for r in v.range_problems)
        print(f"  {v.summary}", flush=True)
        if not args.verbose:
            return
        for note in v.notes:
            print(f"       note: {note}", flush=True)
        for probe in v.probes:
            if probe.skipped:
                print(f"       probe {probe.param}: skipped — {probe.skipped}", flush=True)
            else:
                print(
                    f"       probe {probe.param}: {probe.base_value:g} → "
                    f"{probe.probe_value:g}, volume {probe.base_volume:.3f} → "
                    f"{probe.probe_volume:.3f} "
                    f"({'responsive' if probe.responsive else 'DEAD'})",
                    flush=True,
                )

    verdicts = check_bridge(
        fc, y4d, only=only, render=render, max_probes=args.max_probes,
        on_verdict=report,
    )

    total = len(verdicts)
    if range_notes:
        # A measurement lane, not a gate — see docs/BRIDGE_HANDSHAKE.md. Printed
        # after the verdicts so it reads as the calibration record it is.
        print(
            f"\n  MEASUREMENT (non-blocking) — {len(range_notes)} mapped value(s) "
            f"outside the target parameter's declared range; the cartridge clamps "
            f"these, so the garment gets a part of a size it did not order:"
        )
        for note in range_notes:
            print(f"    {note}")
        print()

    print(
        f"bridge-check: links={total} ok={counts['ok']} "
        f"render_fail={counts['render_fail']} dead_params={counts['dead_params']} "
        f"skipped={counts['skipped']}"
        + (f" resolve_fail={counts['resolve_fail']}" if counts["resolve_fail"] else "")
        + (f" range_notes={len(range_notes)}" if range_notes else "")
    )
    if not render:
        print("  NOTE geometry was NOT verified (--no-render): resolution only")
    if total == 0:
        print("  ERROR checked=0 links")
        return 2
    return 1 if (counts["render_fail"] or counts["dead_params"] or counts["resolve_fail"]) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ho-bridge", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="verify FC↔Yantra4D hardware links physically")
    p.add_argument("--fc", required=True, metavar="DIR", help="a fashion-cabinet checkout")
    p.add_argument("--y4d", required=True, metavar="DIR", help="a yantra4d checkout")
    p.add_argument(
        "cartridges", nargs="*", metavar="FC_CARTRIDGE_DIR",
        help="specific FC cartridge directories (default: every one with a hardware_ref)",
    )
    p.add_argument(
        "--no-render", action="store_true",
        help="structural resolution only — do not render (no [geometry] needed)",
    )
    p.add_argument(
        "--max-probes", type=int, default=MAX_PROBES, metavar="N",
        help=f"responsiveness probes per link (default {MAX_PROBES}; renders are seconds each)",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="print per-probe evidence")

    args = parser.parse_args(argv)
    if args.cmd == "check":
        return _cmd_check(args)
    parser.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
