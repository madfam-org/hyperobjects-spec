"""y4d-spec command-line interface.

    y4d-spec check <cartridge-dir> [...] [--render] [--no-presets] [--no-printability] [-v]
    y4d-spec identity <pair.json> [<pair.json> ...]
    y4d-spec lexicon [--catalog CATALOG] [--terms DIR] [--status] [-v]
    y4d-spec vocab [--status] [-v]
    y4d-spec article <path> [...] [--catalog bundled]
    y4d-spec reader [--out DIR] [--check] [--status]
    y4d-spec define <word> [--lang es|en|fr|pt] · lookup <repo/slug> · related <term-id>
    y4d-spec rules

Exit code 0 iff every cartridge conforms; 1 on any conformance problem; 2 on a
usage / read error. Output is read-proof: it prints how many cartridges it checked,
and says explicitly whether geometry was verified, how many renders ran and how many
of those were PRESETS — a run that skipped a lane must never read like one that
passed it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hyperobjects_lexicon.cli import (
    add_article_parser,
    add_dictionary_parsers,
    add_lexicon_parser,
    add_reader_parser,
    add_vocabulary_parser,
)
from hyperobjects_schemas.identity import check_identity_file

from .conformance import check_cartridge


def _cmd_check(args) -> int:
    if args.render:
        from .geometry import geometry_available

        if not geometry_available():
            print(
                "  ERROR --render needs the geometry extra: "
                'pip install "hyperobjects-spec[geometry]"'
            )
            return 2

    failures = 0
    rendered_targets = 0
    preset_targets = 0
    total_notes = 0
    for d in args.cartridges:
        try:
            result = check_cartridge(
                d,
                render=args.render,
                presets=args.presets,
                printability=args.printability,
            )
        except OSError as exc:
            print(f"  ERROR {d}: cannot read — {exc}")
            failures += 1
            continue

        name = result.slug or Path(d).name
        rendered_targets += len(result.renders)
        preset_targets += len(result.preset_renders)
        total_notes += len(result.notes)

        if result.ok:
            suffix = ""
            if result.rendered:
                suffix = f", {len(result.renders)} render(s) verified"
                n_presets = len(result.preset_renders)
                if n_presets:
                    suffix += f" ({n_presets} preset)"
            print(f"  ok {name} ({d}{suffix})")
            if args.verbose:
                for check in result.renders:
                    print(f"       {check.summary}")
        else:
            failures += 1
            for prob in result.problems:
                print(f"  FAIL {name}: {prob}")

        # Notes print for pass and fail alike, and never change the exit code.
        for note in result.notes:
            print(f"  note {name}: {note}")

    geom = "verified" if args.render else "NOT verified (pass --render)"
    print(
        f"y4d-spec check: cartridges={len(args.cartridges)} failures={failures} "
        f"notes={total_notes} geometry={geom} renders={rendered_targets} "
        f"presets={preset_targets}"
    )
    return 1 if failures else 0


def _cmd_identity(args) -> int:
    failures = 0
    for f in args.files:
        try:
            result = check_identity_file(f)
        except (OSError, ValueError) as exc:
            print(f"  ERROR {f}: cannot read — {exc}")
            failures += 1
            continue
        if result.ok:
            print(f"  ok {f} (identity '{result.identity_id or 'multiple'}')")
        else:
            failures += 1
            for prob in result.problems:
                print(f"  FAIL {f}: {prob}")

    print(f"y4d-spec identity: files={len(args.files)} failures={failures}")
    return 1 if failures else 0


def _cmd_rules(args) -> int:
    from . import rules, structure

    print("y4d-spec checks a cartridge against, in order:\n")
    print("  1. the project-manifest JSON Schema (bundled from yantra4d/packages/schemas)")
    print("  2. manifest rules — every rule names its yantra4d source in y4d_spec.rules:")
    for fn in (
        rules.manifest_structural_rules,
        rules.dispatch_rules,
        rules.hyperobject_rules,
        rules.i18n_rules,
        rules.license_rules,
    ):
        first = (fn.__doc__ or "").strip().splitlines()[0]
        print(f"       {fn.__name__:28} {first}")
    print("  3. on-disk rules — y4d_spec.structure:")
    for fn in (
        structure.mode_source_rules,
        structure.source_path_rules,
        structure.vendor_rules,
        structure.shipped_license_rules,
    ):
        first = (fn.__doc__ or "").strip().splitlines()[0]
        print(f"       {fn.__name__:28} {first}")
    print("  4. geometry (--render, needs the [geometry] extra): every (mode, part) is")
    print("       executed through the shared sandbox and the mesh must be watertight,")
    print("       have volume > 0, contain no inverted body, and be distinct per part.")
    print("  5. the preset matrix (--render, skip with --no-presets): every declared")
    print("       preset is rendered at that SAME bar — a preset is the parameter point")
    print("       a user clicks, and the defaults render says nothing about it. A")
    print("       preset that renders identically to the defaults while setting values")
    print("       that differ from them is a note, not a failure.")
    print("  6. printability (--render, skip with --no-printability) — NOTES ONLY,")
    print("       never failures; every threshold is provisional pending full-commons")
    print("       calibration. See y4d_spec.printability:")
    from . import printability

    for fn in (
        printability.thin_wall_note,
        printability.overhang_note,
        printability.build_volume_note,
    ):
        first = (fn.__doc__ or "").strip().splitlines()[0]
        print(f"       {fn.__name__:28} {first}")
    print("\nRepo-wide checks (catalog drift, cross-cartridge slug uniqueness,")
    print("OpenSCAD/CadQuery geometric parity) stay in the platform — they are not")
    print("properties of a single cartridge.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="y4d-spec", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="check cartridge director(ies)")
    p_check.add_argument("cartridges", nargs="+", help="cartridge director(ies) to check")
    p_check.add_argument(
        "--render",
        action="store_true",
        help="also render every (mode, part) and verify the mesh "
        '(needs: pip install "hyperobjects-spec[geometry]")',
    )
    p_check.add_argument(
        "--no-presets",
        dest="presets",
        action="store_false",
        help="under --render, skip the declared presets and check default params only "
        "(faster, and strictly weaker — a preset is the parameter point users click)",
    )
    p_check.add_argument(
        "--no-printability",
        dest="printability",
        action="store_false",
        help="under --render, skip the printability measurements (thin walls, "
        "overhangs, build volume). They are notes only and never fail a cartridge",
    )
    p_check.add_argument(
        "-v", "--verbose", action="store_true", help="print each render's measurements"
    )
    p_check.set_defaults(func=_cmd_check)

    p_id = sub.add_parser("identity", help="check a cross-commons identity pair file")
    p_id.add_argument("files", nargs="+", help="pair record JSON file(s)")
    p_id.set_defaults(func=_cmd_identity)

    add_lexicon_parser(sub, "y4d-spec")
    add_vocabulary_parser(sub, "y4d-spec")
    add_article_parser(sub, "y4d-spec")
    add_dictionary_parsers(sub, "y4d-spec")
    add_reader_parser(sub, "y4d-spec")

    p_rules = sub.add_parser("rules", help="explain what gets checked, and where it came from")
    p_rules.set_defaults(func=_cmd_rules)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
