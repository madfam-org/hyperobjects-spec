"""Cartridge conformance: schema + house rules + optional geometry, in one call.

    from y4d_spec import check_cartridge
    result = check_cartridge("/path/to/my-cartridge", render=False)
    if not result.ok:
        for problem in result.problems:
            print(problem)

Ties the bundled project-manifest schema (hyperobjects_schemas) to the pure rule
functions (rules.py), the on-disk rules (structure.py), and — when asked, and when
the [geometry] extra is installed — the render lane (geometry.py).

Nothing short-circuits: schema errors do not suppress rule problems, so a caller sees
every problem at once.
"""

from __future__ import annotations

import contextlib
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from hyperobjects_schemas import load as load_schema

from . import rules, structure

__all__ = ["CartridgeResult", "check_manifest", "check_cartridge", "MANIFEST_SCHEMA"]

MANIFEST_SCHEMA = "project-manifest"


@dataclass
class CartridgeResult:
    """The verdict on one cartridge. Falsey when there are problems."""

    slug: str | None
    ok: bool
    problems: list[str] = field(default_factory=list)
    #: Non-blocking observations — true, worth saying, but not a conformance failure
    #: (e.g. an include of the repo's shared libs/ tree). Never affects `ok`.
    notes: list[str] = field(default_factory=list)
    #: One RenderCheck per (mode, part), plus one per (preset, part) when the preset
    #: matrix ran. Empty when geometry did not run.
    renders: list = field(default_factory=list)
    #: True when geometry verification actually executed.
    rendered: bool = False
    #: One ParityCheck per (mode, part, preset) that rendered on BOTH kernels. Empty
    #: unless `parity=True` — and empty on a single-engine cartridge even then, which
    #: is why `parity_ran` exists to say the pass happened at all.
    parity: list = field(default_factory=list)
    #: True when the cross-kernel parity pass ran (whether or not it found any pairs).
    parity_ran: bool = False

    def __bool__(self) -> bool:
        return self.ok

    @property
    def preset_renders(self) -> list:
        """Just the preset renders — the parameter points a user clicks."""
        return [c for c in self.renders if getattr(c, "preset", None)]

    @property
    def verified_renders(self) -> list:
        """The renders whose mesh was actually judged.

        `renders` also holds SKIPPED targets (an OpenSCAD mode — this package has no
        OpenSCAD kernel). Those are `ok` and must not fail a cartridge, but counting
        them as verified is how a cartridge nothing measured reads as one that passed:
        an all-OpenSCAD cartridge would report "6 render(s) verified" having rendered
        nothing at all.
        """
        return [c for c in self.renders if not getattr(c, "skipped", None)]

    @property
    def skipped_renders(self) -> list:
        """The targets geometry did NOT judge, each carrying its reason."""
        return [c for c in self.renders if getattr(c, "skipped", None)]

    @property
    def parity_warnings(self) -> list:
        """The pairs that agreed only through the faceting warn tier (G27)."""
        return [c for c in self.parity if c.ok and c.warn and not c.exempt]

    @property
    def parity_failures(self) -> list:
        """The pairs whose two kernels genuinely disagree."""
        return [c for c in self.parity if not c.ok and not c.exempt]

    @property
    def parity_exemptions(self) -> list:
        """The pairs the manifest declared exempt, with the reason it gave (G38)."""
        return [c for c in self.parity if getattr(c, "exempt", False)]

    @property
    def parity_placement_notes(self) -> list:
        """The pairs whose shapes agree but whose two kernels place them apart (G39).

        Agreement, not debt: a slicer re-centres the part. Counted and printed anyway,
        because an assembly does not, and a cartridge that means to be assembled
        should be able to see the number before it declares `placement: "strict"`.
        """
        return [
            c
            for c in self.parity
            if c.ok and getattr(c, "placement_note", False) and not c.exempt and not c.warn
        ]


def _schema_errors(doc: object) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise RuntimeError("jsonschema is required (pip install hyperobjects-spec)") from exc
    validator = Draft202012Validator(load_schema(MANIFEST_SCHEMA))
    problems = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        problems.append(f"schema {where}: {err.message}")
    return problems


def check_manifest(doc: dict) -> CartridgeResult:
    """Check a parsed project.json alone — schema + every per-cartridge house rule.

    Path-independent: no directory, no rendering. This is what a manifest editor or a
    PR bot can run on a diff.
    """
    problems = _schema_errors(doc)
    problems.extend(rules.all_manifest_rules(doc))
    slug = (doc.get("project") or {}).get("slug") if isinstance(doc.get("project"), dict) else None
    return CartridgeResult(slug=slug, ok=not problems, problems=problems)


def check_cartridge(
    cartridge_dir: str | Path,
    *,
    render: bool = False,
    presets: bool = True,
    printability: bool = True,
    library_paths: list[Path] | None = None,
    require_openscad: bool = False,
    openscad_timeout: int | None = None,
    parity: bool = False,
    parity_tolerance: float | None = None,
) -> CartridgeResult:
    """Check a cartridge DIRECTORY: its manifest, its files, and optionally its geometry.

    `render=True` requires the [geometry] extra; without it, a GeometryUnavailable is
    raised rather than silently skipped — a checker that quietly downgrades its own
    strictness is how an unverified cartridge ships green.

    `presets` and `printability` only mean anything under `render=True`. Both default
    ON so the strongest available check is the one a caller gets by asking for
    geometry — the same reason `--render` refuses rather than downgrading. Presets are
    part of the conformance verdict; printability is notes only and never is.

    `library_paths` are the OpenSCAD library roots (`--openscad-path`) an OpenSCAD
    cartridge's `include <>` resolves against; `require_openscad=True` makes a missing
    OpenSCAD binary a failure rather than a skip. Both only mean anything under
    `render=True`.

    `parity=True` (also `render=True` only) additionally COMPARES the two kernels of
    every dual-engine target that rendered on both, at the platform's own gates — see
    parity.py. Rendering both sides proves each is a solid; parity is what proves they
    are the SAME solid. A genuine disagreement is a conformance failure; a delta
    inside the faceting band whose surfaces agree is a note (G27).
    `parity_tolerance` overrides the AABB tolerance (default 0.001mm) for EVERY pair,
    manifest policy included: an operator who names a bar on the command line is asking
    to see the cartridge measured at that bar, and a manifest that could quietly widen
    it again would make `--parity-tolerance 0.001` unable to say what the cartridge
    looks like at 0.001mm. A part the manifest declares exempt is not compared at all
    and is reported as a note (G38 — see parity.py); an exemption is a declaration that
    the comparison is meaningless for that part, which no tolerance answers.
    """
    path = Path(cartridge_dir).resolve()
    manifest_path = path / "project.json"

    if not path.is_dir():
        return CartridgeResult(
            slug=None, ok=False, problems=[f"{path}: not a directory"]
        )
    if not manifest_path.is_file():
        return CartridgeResult(
            slug=None, ok=False, problems=[f"{path}: no project.json — not a cartridge"]
        )

    try:
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CartridgeResult(
            slug=None, ok=False, problems=[f"project.json: invalid JSON — {exc}"]
        )

    if not isinstance(doc, dict):
        return CartridgeResult(
            slug=None, ok=False, problems=["project.json: top level must be an object"]
        )

    result = check_manifest(doc)
    structure_problems, notes = structure.all_structure_rules(path, doc)
    result.problems.extend(structure_problems)
    result.notes.extend(notes)

    if render:
        # Lazy: geometry pulls cadquery on first render, and a manifest-only check
        # must not pay for a CAD kernel it never uses.
        from .geometry import OPENSCAD_TIMEOUT_S, check_geometry

        timeout = OPENSCAD_TIMEOUT_S if openscad_timeout is None else openscad_timeout

        # Under --parity the STLs must outlive their own renders so the two kernels
        # can be put side by side. This directory is where they go, and it dies with
        # this call: the meshes are evidence for one comparison, not an artifact.
        # Without --parity nothing is retained and the render path is byte-for-byte
        # what it was.
        with contextlib.ExitStack() as stack:
            stl_dir = (
                Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="y4d-parity-")))
                if parity
                else None
            )
            result.renders = check_geometry(
                path,
                doc,
                presets=presets,
                printability=printability,
                library_paths=library_paths,
                require_openscad=require_openscad,
                openscad_timeout=timeout,
                stl_dir=stl_dir,
            )
            result.rendered = True

            if parity:
                from .parity import PARITY_TOLERANCE, parity_checks

                # `parity_tolerance is None` is passed on rather than collapsed here:
                # parity_checks needs to tell "the default" from "the operator asked
                # for this bar", because only the second overrides a manifest policy.
                result.parity = parity_checks(
                    result.renders,
                    PARITY_TOLERANCE if parity_tolerance is None else parity_tolerance,
                    doc,
                    tolerance_is_explicit=parity_tolerance is not None,
                )
                result.parity_ran = True

        for check in result.renders:
            if not check.ok:
                result.problems.append(f"render {check.summary}")
            # Per-render notes (preset-vs-default sameness, printability
            # measurements) join the cartridge's notes and never touch `ok`.
            result.notes.extend(check.notes)

        for pc in result.parity:
            if pc.exempt:
                # An exemption is TRUE, declared, and never a failure — but it is also
                # never silent: it lands where the other true-but-not-fatal findings
                # do, so every run prints the debt it is carrying (G38).
                result.notes.append(pc.summary)
            elif not pc.ok:
                result.problems.append(pc.summary)
            elif pc.warn or getattr(pc, "placement_note", False):
                # A faceting warn is TRUE and worth saying — the two kernels do differ,
                # by chord error — but it is not a conformance failure, so it lands
                # where the other true-but-not-fatal findings do. A placement offset
                # (G39) is in the same tier and for the same reason: real, printed on
                # every run, and not fatal unless the manifest asked for it to be.
                result.notes.append(pc.summary)

    result.ok = not result.problems
    return result
