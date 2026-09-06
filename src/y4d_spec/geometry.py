"""Optional geometry verification: does the cartridge actually render a solid?

A manifest can be perfectly conformant and still describe a cartridge that renders
nothing, or renders a shell with a hole in it. This module executes the cartridge for
every (mode, part) and judges the mesh — the check the whole commons rests on.

Requires the `geometry` extra:  pip install "hyperobjects-spec[geometry]"

BOTH ENGINES (G31)
------------------
A cartridge's modes may be CadQuery, OpenSCAD, or both, and all of them are rendered:

  * CadQuery (.py/.cq) — executed in-process through the shared sandbox, contract
    below.
  * OpenSCAD (.scad)   — run as a subprocess with the platform's own command shape,
    contract in render_part_openscad / build_openscad_command.
  * dual-engine        — a mode declaring both renders BOTH SIDES, each judged
    separately and each tagged with its engine.

That last case is the reason this exists. The platform picks ONE engine per mode at
render time, so on a dual-engine cartridge the other side is never exercised by
anything — and an OpenSCAD regression there ships unseen because the CadQuery side, the
one the platform serves, stays green. A verifier's job is the opposite of a renderer's:
render everything the cartridge claims it can.

An OpenSCAD binary that is ABSENT is a skip, not a failure — a contributor's laptop
without OpenSCAD must still be able to check a cartridge — unless `require_openscad`
is set, which is what CI passes once its image carries the binary. A skip is never
counted as a verified render (see RenderCheck.skipped).

THE RENDER ENVIRONMENT (G33)
----------------------------
Which OpenSCAD, which system packages, which fonts — that contract is data, in
y4d_spec.render_environment, and is what the commons CI, the platform image and the CI
runner image all read instead of each keeping their own copy. The version matters more
than it looks: the commons uses snapshot syntax no tagged release has, so a machine one
release behind reports a *cartridge* failure for an environment problem. `y4d-spec
render-env` prints the contract; `--render -v` prints the version actually in use.

The execution contract is replicated from yantra4d/apps/api/services/engine/cq_runner.py
(run_cadquery_script), so a cartridge that renders here renders on the platform:

  * the script runs through commons_sandbox — validate_script_path(path, {".py", ".cq"}),
    build_sandbox_builtins("CadQuery scripts"), read_script, exec       (cq_runner:26-51)
  * exec globals carry `cq`, `math`, `__file__`, `__name__ = "__main__"` (cq_runner:36-42)
  * PARAMETERS ARE INJECTED AS BARE GLOBALS via exec_globals.update(params)
    (cq_runner:43) — this is why cartridges use the PARAM(lambda: name, default) idiom
  * `target_part` is one of those params — it is how a per-part render is dispatched
  * the result is the first of `result`, `assembly`, `part`, `show_object` that holds a
    cq.Workplane / cq.Assembly / cq.Shape, else the last such object in the namespace
    (cq_runner:54-65)
  * sys.argv is mocked so a cartridge's argparse does not explode  (cq_runner:47-48)

Two deliberate departures from cq_runner, both because this is a checker and not a
render service: it raises instead of sys.exit(1), and it exports STL (the format the
mesh checks need) instead of the caller's requested format.

The mesh bar is the house one: watertight, volume > 0, and no negative-volume body
in split(only_watertight=False) — an inverted/inside-out shell reads as a solid to a
naive volume check but prints as nothing.

That bar is applied at TWO parameter points, not one:

  * the cartridge's own defaults ({} plus target_part), and
  * every PRESET the manifest declares (preset values merged over the defaults).

The second exists because a preset is a parameter point a user actually clicks. A
shipped preset of extrusion-hyperobject crashed OCCT at degradation_state=5 while the
default-params check stayed green — the defaults render is not evidence about the
values the UI offers. Presets are judged at exactly the same bar; a crash at a
declared preset is a failure with no calibration excuse, because it is the existing
rule evaluated somewhere new rather than a new heuristic.
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from commons_sandbox import build_sandbox_builtins, read_script, validate_script_path

# The B-Rep gate. Its own module because this one is already 960 lines and the check is
# a self-contained contract with the CAD kernel — everything OCP-shaped lives there, and
# every OCP import inside a function so a manifest-only install never touches the C
# extension (brep.py imports nothing at module scope either).
from .brep import brep_available
from .brep import check_result as brep_check_result

__all__ = [
    "GeometryUnavailable",
    "RenderCheck",
    "brep_available",
    "geometry_available",
    "render_part",
    "check_geometry",
    # The pre-tessellation gate, re-exported for the same reason as the OpenSCAD half:
    # one import for the render lane.
    "brep_check_result",
    # Re-exported from .openscad so callers have ONE import for the render lane. The
    # OpenSCAD half lives in its own module because it is a subprocess contract with a
    # foreign binary, not a variation on executing Python.
    "build_openscad_command",
    "openscad_available",
    "openscad_binary",
    "openscad_env",
    "openscad_probe",
    "openscad_version",
    "render_part_openscad",
    "reset_openscad_probe",
]

# Suffixes cq_runner accepts for a CadQuery cartridge (cq_runner.py:26).
SCRIPT_SUFFIXES = {".py", ".cq"}

# The suffix an OpenSCAD mode's source carries.
SCAD_SUFFIX = ".scad"

# Where a macOS dev machine keeps the binary the .app installs — on nobody's PATH.
MACOS_OPENSCAD = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"

# Wall clock for one OpenSCAD render. The platform's RENDER_TIMEOUT_S is the sibling
# constant; a checker sweeping a whole commons unattended wants a bound that a single
# pathological cartridge cannot blow past, and 10 minutes is far above the slowest
# render measured in the P2 sweep.
OPENSCAD_TIMEOUT_S = 600

# How many inverted bodies a failure names individually. One degenerate boolean can
# shatter a shape into hundreds of inverted shells, and a report that prints a line per
# body is a report whose actual finding — usually the B-Rep status naming the cause —
# scrolls off the top. The total is always stated.
MAX_INVERTED_BODY_LINES = 3

# The sandbox label cq_runner passes, kept identical so a blocked-import error message
# reads the same here as on the platform (cq_runner.py:34).
SANDBOX_LABEL = "CadQuery scripts"

# Result variable names, in the order cq_runner probes them (cq_runner.py:55).
RESULT_NAMES = ("result", "assembly", "part", "show_object")


class GeometryUnavailable(RuntimeError):
    """Raised when a geometry check is requested without the [geometry] extra."""


def geometry_available() -> bool:
    """True when cadquery and trimesh can both be imported.

    False covers two different situations that a bool cannot tell apart: the [geometry]
    extra is not installed, or it is and the CAD kernel's C extension cannot resolve a
    system library it links against. The reason is deliberately swallowed here — this is
    a predicate, and its callers (the pytest skip hook, `--render`'s refusal) only need
    the verdict. Anything that has to report WHY must import the modules itself and show
    the traceback, which is exactly what the CI read-proof step does before it fails the
    job on a False.
    """
    try:
        import cadquery  # noqa: F401
        import trimesh  # noqa: F401
    except Exception:
        return False
    return True


def _require_geometry():
    try:
        import cadquery as cq
        import trimesh
    except ImportError as exc:
        raise GeometryUnavailable(
            "geometry verification needs cadquery and trimesh — "
            'install them with: pip install "hyperobjects-spec[geometry]"'
        ) from exc
    return cq, trimesh


@dataclass
class RenderCheck:
    """The verdict on one (mode, part) render, plus the evidence behind it."""

    mode: str
    part: str
    ok: bool
    problems: list[str] = field(default_factory=list)
    volume: float | None = None
    watertight: bool | None = None
    bodies: int | None = None
    extents: tuple[float, float, float] | None = None
    #: The preset id this render used, or None for the cartridge's own defaults.
    #: Present so a failure names the parameter point the user would have clicked.
    preset: str | None = None
    #: Non-blocking printability observations (printability.py). Never affects `ok`.
    notes: list[str] = field(default_factory=list)
    #: Which engine produced this mesh — "cadquery" or "openscad". A dual-engine
    #: cartridge yields one check PER ENGINE for the same (mode, part), and without
    #: this the two are indistinguishable in the output, which is the whole reason
    #: both are rendered.
    engine: str | None = None
    #: Why this target was NOT rendered, or None when it was. A skip is `ok` — it is
    #: not a conformance failure that this checker has no OpenSCAD kernel — but it is
    #: NOT a verified render either, and the difference has to survive into the output
    #: or a reader counts a skipped lane as a passed one. Same posture as
    #: bridge_check.LinkVerdict.geometry_skipped.
    skipped: str | None = None
    #: Where this render's STL was kept, when the caller asked for it (`stl_dir`).
    #: Normally None: a render exports into a TemporaryDirectory that dies with the
    #: call, because the verdict is the product and the mesh is scratch. The one
    #: caller that needs the mesh AFTERWARDS is the cross-kernel parity pass
    #: (parity.py), which has nothing to compare unless both sides survive.
    stl_path: str | None = None

    def __bool__(self) -> bool:
        return self.ok

    @property
    def target(self) -> str:
        """The parameter point this render describes, for messages.

        The engine is named whenever one is recorded: a dual-engine cartridge renders
        the SAME (mode, part) twice, and two lines that differ only in their volume
        with nothing saying which kernel produced which is a report nobody can act on.
        """
        suffix = f", {self.engine}" if self.engine else ""
        if self.preset:
            return f"({self.mode}, {self.part}, preset '{self.preset}'{suffix})"
        return f"({self.mode}, {self.part}{suffix})"

    @property
    def summary(self) -> str:
        if not self.ok:
            return f"{self.target}: FAIL — {'; '.join(self.problems)}"
        if self.skipped:
            return f"{self.target}: skip — {self.skipped}"
        if self.volume is None:
            # An `ok` render with no volume is not a thing this module produces on
            # purpose: a measured render always carries a float, and an unmeasured one
            # carries `skipped`. Reaching here means a producer forgot to say which,
            # so say THAT rather than formatting a None into a TypeError and taking
            # the whole run down with it. A verification tool that crashes on an
            # unexpected value reports nothing about the other cartridges.
            return (
                f"{self.target}: ok — volume not measured (no reason recorded); "
                f"this render is UNVERIFIED"
            )
        return (
            f"{self.target}: ok — volume {self.volume:.2f}mm³, "
            f"{self.bodies} body/bodies, watertight"
        )


def _bodies(mesh) -> list[tuple[int, float]]:
    """Connected components of a (vertex-merged) mesh with their signed volumes.

    Deliberately NOT ``mesh.split()``: split() rebuilds every component through
    ``submesh()``, which copies faces per body, re-processes each new Trimesh and
    runs a repair pass on the way out. On a large multi-body render that is the
    whole budget — a 2.5 M-face chainmail panel of 80 rings took over 7 GB and
    15+ minutes there and killed a 6 GiB CI runner twice, while the component
    labelling itself takes seconds. The signed volume of a component is the sum
    of its faces' signed tetrahedron volumes (the divergence-theorem formula
    ``mesh.volume`` uses), so an inverted shell still reads negative and the
    count still reads bodies, without materialising a Trimesh per body.
    """
    import numpy as np

    _, trimesh = _require_geometry()
    faces = mesh.faces
    if faces.shape[0] == 0:
        return []
    try:
        components = trimesh.graph.connected_components(
            mesh.face_adjacency, nodes=np.arange(faces.shape[0]), engine="scipy"
        )
    except BaseException:  # scipy missing or refusing — let trimesh pick an engine
        components = trimesh.graph.connected_components(
            mesh.face_adjacency, nodes=np.arange(faces.shape[0])
        )
    tri = mesh.triangles
    signed = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0
    return [(int(len(c)), float(signed[c].sum())) for c in components]


def _boundary_edges(mesh) -> int:
    """Edges used by exactly one face — the holes. Mirrors yantra4d's
    mesh_integrity._edge_face_counts, without the graph-engine dependency."""
    try:
        import numpy as np

        edges = np.sort(mesh.edges_sorted, axis=1)
        _, counts = np.unique(edges, axis=0, return_counts=True)
        return int((counts == 1).sum())
    except Exception:
        return -1


def _exec_cartridge(script_path: str, params: dict):
    """Execute a cartridge in the shared sandbox and return its result object.

    Faithful to cq_runner.run_cadquery_script's execution half.
    """
    cq, _ = _require_geometry()

    # cq_runner.py:26 — realpath-checked, suffix-gated.
    real = validate_script_path(script_path, SCRIPT_SUFFIXES)
    script_content = read_script(real)

    # cq_runner.py:34-43 — the sandbox namespace, then params as BARE globals.
    exec_globals = {
        "__builtins__": build_sandbox_builtins(SANDBOX_LABEL),
        "cq": cq,
        "math": math,
        "__file__": real,
        "__name__": "__main__",
    }
    exec_globals.update(params)

    # cq_runner.py:47-48 — mock argv so a cartridge's argparse does not break.
    old_argv = sys.argv
    sys.argv = [real, "--params", json.dumps(params), "--out", ""]
    try:
        exec(script_content, exec_globals)  # noqa: S102 — sandboxed via restricted builtins
    finally:
        sys.argv = old_argv

    # cq_runner.py:54-65 — named results first, then the last CAD object in scope.
    cad_types = (cq.Workplane, cq.Assembly, cq.Shape)
    for name in RESULT_NAMES:
        val = exec_globals.get(name)
        if isinstance(val, cad_types):
            return val
    for _key, val in reversed(list(exec_globals.items())):
        if isinstance(val, cad_types):
            return val
    return None


def _export_stl(result, out_path: str) -> None:
    """Export to STL. Mirrors cq_runner's Assembly-vs-Workplane branch (cq_runner:100).

    The Assembly branch flattens to a compound FIRST and then goes through the same
    `cq.exporters.export` the Workplane branch uses, instead of `Assembly.save`.
    `Assembly.save` is `@deprecate()`d in CadQuery 2.7 — "will be removed in the next
    release" — and 22 commons cartridges return assemblies, so every one of them rides
    this branch: leaving `save` here is a fleet-wide break at the next kernel bump, for
    nothing. It is not a behaviour change either. `Assembly.save` forwards to
    `Assembly.export`, whose STL arm is literally
    `self.toCompound().exportStl(path, tolerance, angularTolerance, ascii)`, and
    `cq.exporters.export(shape, path, "STL")` calls the same
    `shape.exportStl(fname, tolerance, angularTolerance, useascii)` with the same
    defaults (0.1 deflection / 0.1 angular / binary). The tolerances stay implicit here
    precisely because both paths read them from the same `export` defaults — pinning
    them on one side only would be the change. Verified byte-identical on the `zipper`
    cartridge (`closed/tape_left`, 36 bodies): sha256 05a22cc0…, 2 163 284 bytes both
    ways.
    """
    cq, _ = _require_geometry()
    if isinstance(result, cq.Assembly):
        cq.exporters.export(result.toCompound(), out_path, "STL")
    else:
        cq.exporters.export(result, out_path, "STL")



@contextmanager
def _stl_target(stl_dir: Path | None, engine: str, mode: str, part: str, preset: str | None):
    """Where one render writes its STL: a caller-owned dir, else a scratch one.

    Two shapes behind one `with`, so neither renderer grows an if/else around its
    whole body. With no `stl_dir` the behaviour is exactly what it was — a
    TemporaryDirectory that takes the mesh with it.
    """
    if stl_dir is None:
        with tempfile.TemporaryDirectory() as tmp:
            yield os.path.join(tmp, "out.stl")
        return
    stl_dir.mkdir(parents=True, exist_ok=True)
    yield str(stl_dir / stl_name(engine, mode, part, preset))


def stl_name(engine: str, mode: str, part: str, preset: str | None) -> str:
    """A collision-free filename for a retained STL.

    Retention (`stl_dir`) exists for the parity pass, which must hold BOTH kernels'
    meshes for the same (mode, part, preset) at once — so the engine has to be in the
    name, and so does the preset, or a preset render silently overwrites the
    default-params one it is meant to be distinguished from. Non-`[A-Za-z0-9._-]`
    characters are replaced: a mode or part id is manifest data, not a filename.
    """
    def _safe(text: str) -> str:
        return "".join(c if (c.isalnum() or c in "._-") else "_" for c in text)

    stem = f"{_safe(engine)}__{_safe(mode)}__{_safe(part)}"
    if preset:
        stem += f"__preset_{_safe(preset)}"
    return stem + ".stl"


def _brep_problems(result) -> list[str]:
    """The B-Rep gate's findings on a cartridge's result, ready for a RenderCheck.

    Lives here rather than in brep.py because the shape of a *message* is this module's
    business — brep.py returns verdicts, geometry.py decides how a verdict reads in a
    report. An Assembly's members are named, since one broken part in a tree of eight is
    unactionable if the report only names the tree.

    Missing OCP is silence, not a finding. The [geometry] extra installs it alongside
    cadquery, so an install that got this far has it; if some future packaging splits
    them, a checker that could not run one gate must not invent a cartridge failure out
    of its own incompleteness. `geometry_available()` already gates the whole lane.
    """
    if not brep_available():
        return []

    problems: list[str] = []
    try:
        verdicts = brep_check_result(result)
    except Exception as exc:
        # The gate itself failing is worth saying — a silent skip here would restore
        # exactly the blind spot the gate exists to close — but it is not the
        # cartridge's failure, and it does not fail the render.
        return [
            f"B-Rep validity gate did not run ({type(exc).__name__}: {exc}) — "
            f"this shape is UNVERIFIED at the B-Rep level"
        ]

    for label, verdict in verdicts:
        prefix = f"part '{label}': " if label else ""
        problems.extend(f"{prefix}{problem}" for problem in verdict.problems)
    return problems


def render_part(
    cartridge_dir: Path,
    script_file: str,
    mode: str,
    part: str,
    *,
    params: dict | None = None,
    preset: str | None = None,
    printability: bool = False,
    stl_dir: Path | None = None,
) -> RenderCheck:
    """Render one (mode, part) and judge the mesh.

    Params default to `{}` plus `target_part` — the same empty-params render the
    platform does when a user first opens a cartridge, which exercises each
    cartridge's own defaults rather than a set this checker invented. A preset render
    passes that preset's `values` as `params` and names the preset in `preset`, so a
    failure says which UI button reproduces it.

    `printability=True` adds the non-blocking measurements from printability.py to
    `notes` — only on a render that already passed, because wall thickness measured on
    a holed mesh is a number that means nothing.

    `stl_dir` keeps the exported STL there instead of in a TemporaryDirectory that
    dies with the call, and records the path on the check. The parity pass is the
    caller that needs it: it has nothing to compare unless both kernels' meshes
    outlive their own renders.
    """
    _, trimesh = _require_geometry()

    call_params = dict(params or {})
    call_params["target_part"] = part

    script_path = str(cartridge_dir / script_file)
    problems: list[str] = []

    try:
        result = _exec_cartridge(script_path, call_params)
    except Exception as exc:  # a cartridge raising IS the failure
        return RenderCheck(
            mode=mode,
            part=part,
            ok=False,
            preset=preset,
            problems=[f"script raised {type(exc).__name__}: {exc}"],
        )

    if result is None:
        return RenderCheck(
            mode=mode,
            part=part,
            ok=False,
            preset=preset,
            problems=[
                "script produced no CadQuery Workplane/Assembly/Shape — assign the "
                f"final solid to one of: {', '.join(RESULT_NAMES)}"
            ],
        )

    # THE B-REP GATE, before tessellation (brep.py; solid #45, tripod-hub).
    # Order matters and is the whole point: the mesh bar below judges the STL, and
    # tessellation is where the evidence dies — OCCT triangulates an inverted or
    # self-inconsistent shell into triangles that merge, seal and measure like a solid,
    # so the STL passes while the shape that produced it segfaults the next boolean on
    # a Linux OCP build. The shape is judged here, while it still exists.
    #
    # The findings are collected into `problems` rather than returned: the STL is still
    # exported below so the author can OPEN what the kernel produced, and a gate that
    # withheld the artefact would be asking someone to debug a shape they cannot see.
    # `_judge_stl` carries these into its verdict, so the render still fails.
    problems.extend(_brep_problems(result))

    with _stl_target(stl_dir, "cadquery", mode, part, preset) as stl:
        try:
            _export_stl(result, stl)
        except Exception as exc:
            return RenderCheck(
                mode=mode,
                part=part,
                ok=False,
                preset=preset,
                problems=problems + [f"STL export failed: {type(exc).__name__}: {exc}"],
            )

        return _judge_stl(
            stl,
            mode=mode,
            part=part,
            preset=preset,
            printability=printability,
            engine="cadquery",
            problems=problems,
            keep=stl_dir is not None,
        )


def _judge_stl(
    stl_path: str,
    *,
    mode: str,
    part: str,
    preset: str | None,
    printability: bool,
    engine: str | None = None,
    problems: list[str] | None = None,
    keep: bool = False,
) -> RenderCheck:
    """The mesh bar, applied to an STL on disk. THE bar — there is exactly one.

    Both engines land here: CadQuery exports through cq.exporters and OpenSCAD through
    ``-o out.stl``, and from that point on nothing distinguishes them. That is the whole
    point of the function existing rather than the OpenSCAD path growing its own copy of
    the checks — two implementations of "watertight, positive volume, no inverted body"
    is two bars, and the one that drifts is the one nobody is reading.
    """
    _, trimesh = _require_geometry()
    problems = list(problems or [])

    # process=False is load-bearing, not a speed knob: trimesh's default load
    # pipeline REPAIRS the mesh (merges vertices, fills holes, fixes winding).
    # Loading with it on would silently seal the exact hole this check exists to
    # find, and report a broken cartridge as watertight. Merge is done
    # explicitly below, at a tolerance we choose; nothing else is healed.
    mesh = trimesh.load(stl_path, force="mesh", process=False)

    if not isinstance(mesh, trimesh.Trimesh) or mesh.faces.shape[0] == 0:
        return RenderCheck(
            mode=mode,
            part=part,
            ok=False,
            preset=preset,
            problems=["rendered an empty mesh (no faces)"],
        )

    # STL stores every triangle with its own vertices, so a closed solid arrives as
    # loose triangle soup and only seals once coincident vertices are merged. Merge
    # before judging, exactly as yantra4d's mesh_integrity.assess does — reading the
    # raw flag reports valid geometry as holed.
    mesh.merge_vertices()

    watertight = bool(mesh.is_watertight)
    volume = float(mesh.volume)

    # Bodies = connected components of the merged mesh, each with its signed
    # volume — computed directly (see _bodies) rather than via split()/submesh(),
    # whose per-body rebuild and repair pass cost 7 GB on a large multi-body render
    # and could never decide the verdict anyway. A failure here degrades to
    # "could not split" and the watertight/volume findings stand on their own.
    try:
        bodies = _bodies(mesh)
    except Exception as exc:
        bodies = []
        problems.append(f"could not split into bodies ({type(exc).__name__}: {exc})")

    if not watertight:
        # Count boundary edges directly rather than via mesh.outline(), which needs a
        # graph engine and would turn a plain finding into an ImportError.
        problems.append(
            f"not watertight — {_boundary_edges(mesh)} boundary edge(s); the mesh "
            f"does not enclose a volume"
        )
    if volume <= 0:
        problems.append(f"volume is {volume:.4f} (must be > 0)")

    # A negative-volume body is an inverted shell: a solid turned inside out. It reads
    # as geometry to a naive check and prints as nothing.
    #
    # Capped, because a single bad fuse produces them by the hundred: the tripod-hub
    # shape yields 200+ identical lines that push every OTHER finding — including the
    # B-Rep status that names the CAUSE — off the top of the report. The count and the
    # worst offenders are what a reader acts on; the remaining repetitions are not.
    inverted = [(i, bvol) for i, (_faces, bvol) in enumerate(bodies) if bvol < 0]
    for i, bvol in inverted[:MAX_INVERTED_BODY_LINES]:
        problems.append(
            f"body {i} has negative volume ({bvol:.4f}) — an inverted/inside-out "
            f"shell, not a printable solid"
        )
    if len(inverted) > MAX_INVERTED_BODY_LINES:
        problems.append(
            f"(+{len(inverted) - MAX_INVERTED_BODY_LINES} further inverted "
            f"body/bodies, {len(inverted)} of {len(bodies)} in total)"
        )

    check = RenderCheck(
        mode=mode,
        part=part,
        ok=not problems,
        problems=problems,
        volume=volume,
        watertight=watertight,
        bodies=len(bodies),
        extents=tuple(float(x) for x in mesh.extents),
        preset=preset,
        engine=engine,
        # Only a mesh that WILL still be on disk is recorded. `keep` is the caller
        # saying it owns the directory; without it the path is about to be deleted and
        # a recorded path would be a promise this function cannot keep.
        stl_path=stl_path if keep else None,
    )

    # Printability runs only on a mesh that already passed: these measurements are
    # about a printable solid, and on a holed or inverted one they report noise on top
    # of a failure the reader already has.
    if printability and check.ok:
        from .printability import printability_notes

        check.notes = [
            n.message
            for n in printability_notes(
                mesh, mode=mode, part=part, preset=preset, engine=engine
            )
        ]

    return check


def _no_source_skip() -> str:
    """The one remaining reason a target goes unrendered for lack of a source."""
    return (
        "no renderable source (.py/.cq/.scad) declared for this mode — nothing to "
        "render, so the mesh was NOT verified"
    )


def _no_binary_skip(scad_file: str) -> str:
    """Why an OpenSCAD target went unrendered on a machine without the binary."""
    return (
        f"OpenSCAD mode ('{scad_file}') — no OpenSCAD binary on this machine, so the "
        f"mesh was NOT verified here. Install OpenSCAD "
        f"(`y4d-spec render-env` says which version) or set $OPENSCAD; pass "
        f"--require-openscad to make this a failure instead of a skip"
    )


def mode_sources(mode: dict) -> list[tuple[str, str]]:
    """The (engine, source file) pairs to render for one mode — BOTH for dual-engine.

    A cartridge may declare a ``.scad`` and a ``.py``/``.cq`` for the same mode. The
    platform picks ONE at render time (manifest.py::mode_engine: an explicit
    ``mode.engine``, else the suffix of ``scad_file``, else ``project.engine``), because
    it is serving one mesh to one user. A verifier has the opposite job: an OpenSCAD
    regression on a cartridge whose CadQuery side is the platform default ships unseen
    precisely because nothing renders the other half. So both sides are rendered and
    both are judged.

    Returns pairs in a stable order (cadquery first, then openscad) so output is
    diffable across runs.
    """
    sources: list[tuple[str, str]] = []

    cq_file = mode.get("cq_file")
    scad_file = mode.get("scad_file")

    # `scad_file` is the historical field and holds whatever the mode's primary source
    # is — including a .py, for a CadQuery-only cartridge that never had a .scad.
    for candidate in (cq_file, scad_file):
        if not isinstance(candidate, str) or not candidate:
            continue
        suffix = Path(candidate).suffix
        if suffix in SCRIPT_SUFFIXES:
            pair = ("cadquery", candidate)
        elif suffix == SCAD_SUFFIX:
            pair = ("openscad", candidate)
        else:
            continue
        if pair not in sources:
            sources.append(pair)

    sources.sort(key=lambda p: 0 if p[0] == "cadquery" else 1)
    return sources


def part_render_modes(manifest: dict) -> dict[str, int]:
    """``{part id: render_mode}`` — the integer the .scad dispatches on.

    manifest.py::get_mode_map. A part that declares none is 0, which the platform reads
    as "the script's own default branch" and therefore does not send at all.
    """
    out: dict[str, int] = {}
    for part in manifest.get("parts") or []:
        if not isinstance(part, dict) or not isinstance(part.get("id"), str):
            continue
        value = part.get("render_mode", 0)
        out[part["id"]] = value if isinstance(value, int) and not isinstance(value, bool) else 0
    return out


def check_geometry(
    cartridge_dir: Path,
    manifest: dict,
    *,
    presets: bool = True,
    printability: bool = False,
    library_paths: list[Path] | None = None,
    require_openscad: bool = False,
    openscad_timeout: int = OPENSCAD_TIMEOUT_S,
    stl_dir: Path | None = None,
) -> list[RenderCheck]:
    """Render every (mode, part) the manifest declares and judge each mesh.

    BOTH engines. A CadQuery mode runs through the shared sandbox; an OpenSCAD mode
    runs through the platform's own command shape (see render_part_openscad); a
    dual-engine mode renders BOTH sides and judges each at the same bar, because the
    side the platform does not pick by default is exactly the side whose regressions
    ship unseen.

    With `presets=True` (the default under --render), ALSO renders every declared
    preset at the same bar — see preset_targets() for why the defaults render is not
    evidence about the parameter points users click.

    `require_openscad=True` turns a missing binary from a skip into a failure. The
    default is the skip, because a contributor's laptop without OpenSCAD must still be
    able to check a cartridge; CI passes the flag once its image carries the binary,
    and then a silently unrendered OpenSCAD lane cannot go green.

    Also asserts that the cartridge's modes are DISTINCT: two modes rendering
    byte-identical geometry means the target_part dispatch is not wired, and the user
    picking mode B silently gets mode A.

    `stl_dir` retains every rendered STL there and records the path on each check.
    That is what the cross-kernel parity pass (parity.py) consumes — it compares the
    two kernels' meshes for the same target, and cannot if either was thrown away
    with its render. The directory is the CALLER's to create and clean up; passing
    None (the default) is the old behaviour exactly.
    """
    from .openscad import openscad_binary, render_part_openscad
    from .rules import parameter_defaults, preset_changes_anything, preset_targets, render_targets

    results: list[RenderCheck] = []
    modes = [m for m in manifest.get("modes") or [] if isinstance(m, dict)]
    render_mode_of = part_render_modes(manifest)
    binary = openscad_binary()

    def _sources_for(mode_id: str) -> list[tuple[str, str]]:
        mode = next((m for m in modes if m.get("id") == mode_id), {})
        return mode_sources(mode)

    def _render(
        engine: str,
        source: str,
        mode_id: str,
        part_id: str,
        *,
        params: dict | None = None,
        preset: str | None = None,
        keep_stl: bool = True,
    ) -> RenderCheck:
        """One render, on whichever engine, tagged with the engine that produced it.

        `keep_stl=False` renders into scratch even under `stl_dir`. The fallback
        render (the sentinel target the distinct-modes check probes with) is the one
        caller that wants that: it is a diagnostic body no user can ask for, its two
        engines' else-branches are unrelated meshes by construction, and retaining it
        would hand the parity pass a pair to compare that is not a declared target.
        """
        target_stl_dir = stl_dir if keep_stl else None
        if engine == "openscad":
            if binary is None:
                # No kernel here. A skip stays `ok` — a cartridge is not
                # non-conformant because the machine checking it lacks OpenSCAD — but
                # it is NOT a verified render, and `skipped` is what keeps the two
                # apart downstream. Under --require-openscad the same absence is a
                # failure, which is how CI refuses to go green on an unrendered lane.
                return RenderCheck(
                    mode=mode_id,
                    part=part_id,
                    ok=not require_openscad,
                    preset=preset,
                    engine=engine,
                    problems=(
                        [
                            f"--require-openscad: no OpenSCAD binary found, so "
                            f"'{source}' was not rendered. Set $OPENSCAD or put "
                            f"`openscad` on PATH"
                        ]
                        if require_openscad
                        else []
                    ),
                    skipped=None if require_openscad else _no_binary_skip(source),
                )
            check = render_part_openscad(
                cartridge_dir,
                source,
                mode_id,
                part_id,
                render_mode=render_mode_of.get(part_id, 0),
                params=params,
                preset=preset,
                printability=printability,
                library_paths=library_paths,
                timeout=openscad_timeout,
                binary=binary,
                stl_dir=target_stl_dir,
            )
        else:
            check = render_part(
                cartridge_dir,
                source,
                mode_id,
                part_id,
                params=params,
                preset=preset,
                printability=printability,
                stl_dir=target_stl_dir,
            )
        check.engine = engine
        return check

    for mode_id, part_id in render_targets(manifest):
        sources = _sources_for(mode_id)
        if not sources:
            results.append(
                RenderCheck(
                    mode=mode_id,
                    part=part_id,
                    ok=True,
                    problems=[],
                    skipped=_no_source_skip(),
                )
            )
            continue

        for engine, source in sources:
            results.append(_render(engine, source, mode_id, part_id))

    # Distinct-modes check: the same PART rendered from two different modes should
    # be the same body (that is fine). Pairwise-identical volumes across different
    # parts are NOT evidence of a dead dispatch either: parts may legitimately
    # coincide (an assembly mode reusing a single-mode plate — hook-and-eye's
    # tape_hook_plate IS the hook plate by design). The precise signal is the
    # FALLBACK body — the else-branch a missed target_part falls into. Render it
    # once with a sentinel target_part no manifest declares, then flag when TWO OR
    # MORE distinct declared parts equal it: at most one part can legitimately BE
    # the else-branch (a "set"/assembly default mode), so a second match means some
    # part's branch is not wired and silently renders the default. A script that
    # instead RAISES on unknown target_part has no silent fallthrough to catch, and
    # skips this check (the fallback render fails, which is the correct exemption).
    #
    # Done PER ENGINE. A dual-engine cartridge has two fallback bodies — the .py's
    # else-branch and the .scad's — and they are different meshes with different
    # volumes. Comparing a CadQuery render against an OpenSCAD fallback volume would
    # be comparing two unrelated numbers: never equal, so the rule would simply stop
    # firing on exactly the cartridges that have the most ways to go wrong.
    declared_parts = {p for m in modes for p in m.get("parts") or []}

    for engine in ("cadquery", "openscad"):
        fb_source = next(
            (src for m in modes for eng, src in mode_sources(m) if eng == engine), None
        )
        if fb_source is None:
            continue
        if engine == "openscad" and binary is None:
            continue  # nothing rendered on this side; nothing to compare against

        fb = _render(
            engine,
            fb_source,
            "__y4d_spec_fallback__",
            "__y4d_spec_fallback__",
            keep_stl=False,
        )
        if not (fb.ok and fb.volume):
            continue
        fallback_vol = round(fb.volume, 6)

        matching = [
            c
            for c in results
            if c.ok
            and c.volume
            and c.engine == engine
            and round(c.volume, 6) == fallback_vol
            and c.part in declared_parts
        ]
        if len({c.part for c in matching}) >= 2:
            parts_list = ", ".join(sorted({c.part for c in matching}))
            for check in matching:
                check.ok = False
                check.problems.append(
                    f"renders the cartridge's fallback body (volume {fallback_vol}), "
                    f"as do other parts ({parts_list}) — at most one part can be the "
                    f"else-branch default; the target_part dispatch is not "
                    f"distinguishing these parts"
                )

    if presets:
        results.extend(
            _check_presets(
                cartridge_dir,
                manifest,
                default_renders=results,
                sources_for=_sources_for,
                render=_render,
                defaults=parameter_defaults(manifest),
                changes_anything=preset_changes_anything,
                targets=preset_targets(manifest),
            )
        )

    return results


def _check_presets(
    cartridge_dir: Path,
    manifest: dict,
    *,
    default_renders: list[RenderCheck],
    sources_for,
    render,
    defaults: dict,
    changes_anything,
    targets: list[tuple[str, str, str, dict]],
) -> list[RenderCheck]:
    """Render each declared preset and judge it at the SAME bar as the defaults.

    Two distinct findings come out of here, and they are deliberately different in
    kind:

      * A preset that RAISES, exports nothing, or produces broken geometry is a
        FAILURE. That is not a new heuristic needing calibration — it is the existing
        watertight/positive-volume bar evaluated at a parameter point the UI ships a
        button for. There is no calibration excuse for a crash a user can reproduce
        in one click.

      * A preset whose geometry is INDISTINGUISHABLE from the default-params render
        (volumes equal within 1e-6) is a NOTE. Two things produce it, and this checker
        cannot tell them apart from the outside: the preset's values never reached the
        script, or the SCRIPT's own PARAM fallback already equals the preset while the
        manifest declares a different default — real drift found in the calibration
        sweep, where extrusion-hyperobject's manifest declares extrusion_length=100
        and rail.py falls back to 150, so the preset that sets 150 renders the
        "default" body. Either is worth saying and neither is worth blocking on.
        Presets that merely restate the manifest defaults are exempt outright — see
        rules.preset_changes_anything.

    Presets run on EVERY engine the mode declares, exactly as the defaults pass does —
    a preset that crashes the OpenSCAD side of a dual-engine cartridge is the same
    class of bug as one that crashes the CadQuery side, and rendering only one half
    would leave the other's presets unexercised. Where no binary is available the
    OpenSCAD preset render carries the same skip (or, under --require-openscad, the
    same failure) as the defaults pass.

    CALIBRATION (36-cartridge slice, 101 preset renders): zero preset FAILURES — the
    lane does not turn the commons red, so it is safe to land as part of the verdict.
    The sameness NOTE fired on 2 of 35 cartridges (6%), well under the flood bar, and
    both are true findings: extrusion-hyperobject (manifest/script default drift, see
    above) and tpu-hinge-collar's 'mandarin' preset, which sets band_h and stand_h to
    values the collar body does not consume. Untuned — the rule was right as written.
    """
    # Keyed by engine as well as target: a preset's OpenSCAD render must be compared
    # against the OpenSCAD default, never the CadQuery one. Two kernels tessellate
    # differently, so a cross-engine comparison is a difference that means nothing and
    # would suppress the note on every dual-engine cartridge.
    by_target = {
        (c.engine, c.mode, c.part): c
        for c in default_renders
        if c.preset is None and c.volume is not None
    }
    checks: list[RenderCheck] = []

    for preset_id, mode_id, part_id, values in targets:
        for engine, source in sources_for(mode_id):
            check = render(
                engine,
                source,
                mode_id,
                part_id,
                params=values,
                preset=preset_id,
            )
            _note_if_indistinguishable(
                check, values, defaults, changes_anything, by_target
            )
            checks.append(check)

    return checks


def _note_if_indistinguishable(
    check: RenderCheck,
    values: dict,
    defaults: dict,
    changes_anything,
    by_target: dict,
) -> None:
    """Add the sameness NOTE when a preset renders the default body anyway."""
    if check.ok and check.volume is not None and changes_anything(values, defaults):
        baseline = by_target.get((check.engine, check.mode, check.part))
        if (
            baseline is not None
            and baseline.ok
            and baseline.volume is not None
            and abs(check.volume - baseline.volume) <= 1e-6
        ):
            changed = ", ".join(sorted(values))
            check.notes.append(
                f"{check.target}: renders geometry identical to the default-params "
                f"render (volume {check.volume:.6f}mm³) despite setting "
                f"{changed} — either those values never reach the script, or the "
                f"script's own PARAM fallbacks already equal them and the "
                f"manifest's declared defaults are the ones that drifted"
            )


# Re-exported last, and imported here rather than at the top, because .openscad imports
# _judge_stl and RenderCheck from THIS module: at the top the two would import each other
# mid-definition. By this line everything .openscad needs already exists.
from .openscad import (  # noqa: E402
    build_openscad_command,
    openscad_available,
    openscad_binary,
    openscad_env,
    openscad_probe,
    openscad_version,
    render_part_openscad,
    reset_openscad_probe,
)
