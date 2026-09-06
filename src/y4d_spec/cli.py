"""y4d-spec command-line interface.

    y4d-spec check <cartridge-dir> [...] [--render] [--no-presets] [--no-printability]
                   [--openscad-path DIR] [--require-openscad] [--openscad-timeout S] [-v]
    y4d-spec identity <pair.json> [<pair.json> ...]
    y4d-spec lexicon [--catalog CATALOG] [--terms DIR] [--status] [-v]
    y4d-spec vocab [--status] [-v]
    y4d-spec article <path> [...] [--catalog bundled]
    y4d-spec reader [--out DIR] [--check] [--status]
    y4d-spec define <word> [--lang es|en|fr|pt] · lookup <repo/slug> · related <term-id>
    y4d-spec render-env [--apt] [--openscad-version] [--openscad-sha256] [--json]
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
from .geometry import OPENSCAD_TIMEOUT_S
from .parity import AABB_WARN_BAND, PARITY_TOLERANCE


def _cmd_check(args) -> int:
    library_paths = [Path(p) for p in (args.openscad_path or [])]

    if args.render:
        from .geometry import geometry_available, openscad_binary, openscad_version

        if not geometry_available():
            print(
                "  ERROR --render needs the geometry extra: "
                'pip install "hyperobjects-spec[geometry]"'
            )
            return 2

        # Say which OpenSCAD is about to be used, BEFORE any cartridge is checked. The
        # commons uses snapshot syntax no tagged release has, so a machine one release
        # behind reports a cartridge failure for what is an environment problem — and
        # the version is the only thing in the output that can tell those apart.
        binary = openscad_binary()
        if args.verbose:
            if binary:
                print(f"  openscad: {openscad_version() or 'unknown version'} ({binary})")
            else:
                print("  openscad: not found — OpenSCAD modes will be skipped")
        if binary is None and args.require_openscad:
            print(
                "  ERROR --require-openscad: no OpenSCAD binary found. Set $OPENSCAD, "
                "put `openscad` on PATH, or install OpenSCAD "
                "(`y4d-spec render-env` says which version the platform pins)"
            )
            return 2
        for lib in library_paths:
            if not lib.is_dir():
                print(f"  ERROR --openscad-path {lib}: not a directory")
                return 2
    elif args.require_openscad or args.openscad_path or args.parity:
        # These only mean something under --render, and silently ignoring them is how
        # a CI job that MEANT to require OpenSCAD — or MEANT to compare both kernels —
        # passes having rendered nothing and compared nothing.
        print(
            "  ERROR --require-openscad/--openscad-path/--parity only apply with --render"
        )
        return 2

    if args.parity_tolerance is not None and not args.parity:
        print("  ERROR --parity-tolerance only applies with --parity")
        return 2
    if args.parity_tolerance is not None and args.parity_tolerance <= 0:
        print("  ERROR --parity-tolerance must be > 0")
        return 2

    failures = 0
    rendered_targets = 0
    skipped_targets = 0
    preset_targets = 0
    total_notes = 0
    parity_pairs = 0
    parity_ok = 0
    parity_warned = 0
    parity_failed = 0
    for d in args.cartridges:
        try:
            result = check_cartridge(
                d,
                render=args.render,
                presets=args.presets,
                printability=args.printability,
                library_paths=library_paths,
                require_openscad=args.require_openscad,
                openscad_timeout=args.openscad_timeout,
                parity=args.parity,
                parity_tolerance=args.parity_tolerance,
            )
        except OSError as exc:
            print(f"  ERROR {d}: cannot read — {exc}")
            failures += 1
            continue

        name = result.slug or Path(d).name
        rendered_targets += len(result.verified_renders)
        skipped_targets += len(result.skipped_renders)
        preset_targets += len(result.preset_renders)
        total_notes += len(result.notes)
        parity_pairs += len(result.parity)
        parity_warned += len(result.parity_warnings)
        parity_failed += len(result.parity_failures)
        parity_ok += len([c for c in result.parity if c.ok and not c.warn])

        if result.ok:
            suffix = ""
            if result.rendered:
                suffix = f", {len(result.verified_renders)} render(s) verified"
                n_presets = len(result.preset_renders)
                if n_presets:
                    suffix += f" ({n_presets} preset)"
                # A skipped target is not a verified one, and the difference has to be
                # on the ok line — not only under -v — or an all-OpenSCAD cartridge
                # reads exactly like a fully rendered one.
                n_skipped = len(result.skipped_renders)
                if n_skipped:
                    suffix += f", {n_skipped} skipped"
                # A parity pass that found NO pairs is said out loud. A single-engine
                # cartridge has nothing to compare and that is fine, but silence here
                # would read exactly like a cartridge whose two kernels were checked
                # and agreed.
                if result.parity_ran:
                    n_pairs = len(result.parity)
                    if n_pairs:
                        suffix += f", {n_pairs} parity pair(s) agree"
                        n_warn = len(result.parity_warnings)
                        if n_warn:
                            suffix += f" ({n_warn} faceting warn)"
                    else:
                        suffix += ", no dual-engine pair to compare"
            print(f"  ok {name} ({d}{suffix})")
            if args.verbose:
                for check in result.renders:
                    print(f"       {check.summary}")
                for pcheck in result.parity:
                    print(f"       {pcheck.summary}")
        else:
            failures += 1
            for prob in result.problems:
                print(f"  FAIL {name}: {prob}")
            if args.verbose:
                for check in result.renders:
                    print(f"       {check.summary}")
                for pcheck in result.parity:
                    print(f"       {pcheck.summary}")

        # Notes print for pass and fail alike, and never change the exit code.
        for note in result.notes:
            print(f"  note {name}: {note}")

    geom = "verified" if args.render else "NOT verified (pass --render)"
    # `parity=N/M ok, warn=K, failures=J` — N+K+J = M by construction, so a reader can
    # see at a glance that every pair is accounted for. Absent without --parity rather
    # than printed as zero: "parity=0/0" on a run that never compared anything reads
    # like a run that compared and found nothing wrong.
    parity_part = ""
    if args.parity:
        parity_part = (
            f" parity={parity_ok}/{parity_pairs} ok, warn={parity_warned}, "
            f"failures={parity_failed}"
        )
    print(
        f"y4d-spec check: cartridges={len(args.cartridges)} failures={failures} "
        f"notes={total_notes} geometry={geom} renders={rendered_targets} "
        f"presets={preset_targets} skipped={skipped_targets}{parity_part}"
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


def _cmd_render_env(args) -> int:
    """Print the render-environment contract, whole or one field at a time.

    The single-field forms exist so a provisioning script can consume this without
    parsing prose:

        apt-get install -y $(y4d-spec render-env --apt --ci)
        wget "$(y4d-spec render-env --json | jq -r .openscad_appimage_url)"
        echo "$(y4d-spec render-env --openscad-sha256)  openscad.AppImage" | sha256sum -c -
    """
    from . import render_environment as env

    if args.apt:
        print(env.apt_install_line(ci=args.ci))
        return 0
    if args.openscad_version:
        print(env.OPENSCAD_VERSION)
        return 0
    if args.openscad_sha256:
        print(env.OPENSCAD_SHA256)
        return 0
    print(env.render_env_report(as_json=args.json))
    return 0


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
    print("       executed on EVERY engine the mode declares — CadQuery through the")
    print("       shared sandbox, OpenSCAD through the platform's own command line, and")
    print("       a dual-engine mode on BOTH sides — and each mesh must be watertight,")
    print("       have volume > 0, contain no inverted body, and be distinct per part.")
    print("       Without an OpenSCAD binary those targets are SKIPPED (never counted as")
    print("       verified); --require-openscad makes the absence a failure instead.")
    print("       BEFORE any of that, the BUILT SHAPE goes through the B-Rep gate")
    print("       (y4d_spec.brep): BRepCheck_Analyzer(shape).IsValid(), plus a signed")
    print("       volume that must not be negative on the whole shape OR on any solid")
    print("       inside a compound. Two gates because neither subsumes the other — a")
    print("       merely REVERSED solid is topologically valid and reads True to the")
    print("       analyzer, while its volume is minus the right answer. Tessellation")
    print("       destroys the evidence: OCCT turns an inverted shell into a watertight")
    print("       STL with a plausible volume (tripod-hub, solid #45), which passed")
    print("       every mesh check here and segfaulted the Linux kernel on the next")
    print("       boolean. A failing shape still exports its STL, for inspection.")
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
    print("  7. cross-kernel PARITY (--render --parity): a dual-engine target renders on")
    print("       both kernels above, and this is what proves the two are the SAME solid")
    print("       rather than merely two solids. Compared per (mode, part, preset) that")
    print("       rendered on BOTH sides, at the platform's own gates and numbers")
    print("       (yantra4d scripts/qa/verify_parity.py):")
    print(f"         a. AABB extents — max per-axis delta > {PARITY_TOLERANCE}mm FAILS,")
    print(f"            except inside the {AABB_WARN_BAND}mm faceting band (see c);")
    print("            --parity-tolerance overrides this gate and only this gate.")
    print("         b. volume — delta > max(tolerance*100, 2% of the larger) FAILS,")
    print("            checked only when both sides are watertight.")
    print("         c. Hausdorff surface proxy (max divergence, both directions). An")
    print("            AABB delta inside the band is downgraded from FAIL to a WARN")
    print("            only when this gate ALSO passes (surfaces within 0.5mm): an")
    print("            OpenSCAD $fn polygon is a chord approximation of a circle")
    print("            CadQuery models analytically, and the largest such delta in")
    print("            the commons (0.036674mm) sits an order of magnitude below the")
    print("            smallest genuine divergence (0.516728mm). A dimensional error")
    print("            inside the band moves a surface and still fails here. G27,")
    print("            ruled 2026-09-05. A warn is a NOTE, never a failure.")
    print("       A pair exists only where two meshes exist: a skipped OpenSCAD lane")
    print("       yields no pairs, and the ok line says so rather than staying silent.")
    print("  8. the render environment (`y4d-spec render-env`): the packages, OpenSCAD")
    print("       version + AppImage checksum, and fonts policy that the platform image,")
    print("       the commons CI and the CI runner image all read from here instead of")
    print("       each keeping their own copy. See y4d_spec.render_environment.")
    print("\nRepo-wide checks (catalog drift, cross-cartridge slug uniqueness) stay in")
    print("the platform — they are not properties of a single cartridge.")
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
        "--openscad-path",
        action="append",
        metavar="DIR",
        help="an OpenSCAD library root for OPENSCADPATH (the commons' libs/ and, once "
        "it exists, commons-lib/). Repeatable; the cartridge's own directory is always "
        "prepended, and a libs/dotSCAD/src beside it is added automatically",
    )
    p_check.add_argument(
        "--require-openscad",
        action="store_true",
        help="fail instead of skipping when no OpenSCAD binary is available. Turn this "
        "on in CI once the runner image carries OpenSCAD — without it an OpenSCAD lane "
        "that rendered nothing still reports green",
    )
    p_check.add_argument(
        "--openscad-timeout",
        type=int,
        default=None,
        metavar="S",
        help=f"seconds one OpenSCAD render may take (default {OPENSCAD_TIMEOUT_S})",
    )
    p_check.add_argument(
        "--parity",
        action="store_true",
        help="under --render, also COMPARE the two kernels of every dual-engine "
        "target that rendered on both — AABB extents, volume and a Hausdorff "
        "surface proxy, at the platform's own gates. A disagreement is a failure; "
        "an AABB delta inside the 0.05mm faceting band whose surfaces agree is a "
        "warn, not a failure (G27)",
    )
    p_check.add_argument(
        "--parity-tolerance",
        type=float,
        default=None,
        metavar="MM",
        help=f"under --parity, the AABB extents tolerance in mm (default "
        f"{PARITY_TOLERANCE}). The faceting warn band ({AABB_WARN_BAND}mm) and the "
        f"2%% volume allowance are NOT scaled by it: they are the platform's, and a "
        f"local override of one gate must not silently move the others",
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

    p_env = sub.add_parser(
        "render-env",
        help="the render environment this commons is verified against (packages, "
        "OpenSCAD version, fonts policy)",
    )
    p_env.add_argument(
        "--apt",
        action="store_true",
        help="just the apt package names, space-separated, ready to paste after "
        "`apt-get install -y`",
    )
    p_env.add_argument(
        "--ci",
        action="store_true",
        help="with --apt, also include the packages a CI machine needs for the "
        "[geometry] extra's CAD kernel",
    )
    p_env.add_argument(
        "--openscad-version", action="store_true", help="just the pinned OpenSCAD version"
    )
    p_env.add_argument(
        "--openscad-sha256",
        action="store_true",
        help="just the sha256 of the pinned AppImage, to verify a download",
    )
    p_env.add_argument("--json", action="store_true", help="the whole contract as JSON")
    p_env.set_defaults(func=_cmd_render_env)

    p_rules = sub.add_parser("rules", help="explain what gets checked, and where it came from")
    p_rules.set_defaults(func=_cmd_rules)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
