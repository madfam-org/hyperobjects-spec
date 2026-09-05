"""Optional geometry verification: does the cartridge actually render a solid?

A manifest can be perfectly conformant and still describe a cartridge that renders
nothing, or renders a shell with a hole in it. This module executes the cartridge for
every (mode, part) and judges the mesh — the check the whole commons rests on.

Requires the `geometry` extra:  pip install "hyperobjects-spec[geometry]"

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
from dataclasses import dataclass, field
from pathlib import Path

from commons_sandbox import build_sandbox_builtins, read_script, validate_script_path

__all__ = [
    "GeometryUnavailable",
    "RenderCheck",
    "geometry_available",
    "render_part",
    "check_geometry",
]

# Suffixes cq_runner accepts for a CadQuery cartridge (cq_runner.py:26).
SCRIPT_SUFFIXES = {".py", ".cq"}

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
    #: Why this target was NOT rendered, or None when it was. A skip is `ok` — it is
    #: not a conformance failure that this checker has no OpenSCAD kernel — but it is
    #: NOT a verified render either, and the difference has to survive into the output
    #: or a reader counts a skipped lane as a passed one. Same posture as
    #: bridge_check.LinkVerdict.geometry_skipped.
    skipped: str | None = None

    def __bool__(self) -> bool:
        return self.ok

    @property
    def target(self) -> str:
        """The parameter point this render describes, for messages."""
        if self.preset:
            return f"({self.mode}, {self.part}, preset '{self.preset}')"
        return f"({self.mode}, {self.part})"

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
    """Export to STL. Mirrors cq_runner's Assembly-vs-Workplane branch (cq_runner:100)."""
    cq, _ = _require_geometry()
    if isinstance(result, cq.Assembly):
        result.save(out_path, "STL")
    else:
        cq.exporters.export(result, out_path, "STL")


def render_part(
    cartridge_dir: Path,
    script_file: str,
    mode: str,
    part: str,
    *,
    params: dict | None = None,
    preset: str | None = None,
    printability: bool = False,
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

    with tempfile.TemporaryDirectory() as tmp:
        stl = os.path.join(tmp, "out.stl")
        try:
            _export_stl(result, stl)
        except Exception as exc:
            return RenderCheck(
                mode=mode,
                part=part,
                ok=False,
                preset=preset,
                problems=[f"STL export failed: {type(exc).__name__}: {exc}"],
            )

        # process=False is load-bearing, not a speed knob: trimesh's default load
        # pipeline REPAIRS the mesh (merges vertices, fills holes, fixes winding).
        # Loading with it on would silently seal the exact hole this check exists to
        # find, and report a broken cartridge as watertight. Merge is done
        # explicitly below, at a tolerance we choose; nothing else is healed.
        mesh = trimesh.load(stl, force="mesh", process=False)

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
    for i, (_faces, bvol) in enumerate(bodies):
        if bvol < 0:
            problems.append(
                f"body {i} has negative volume ({bvol:.4f}) — an inverted/inside-out "
                f"shell, not a printable solid"
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
    )

    # Printability runs only on a mesh that already passed: these measurements are
    # about a printable solid, and on a holed or inverted one they report noise on top
    # of a failure the reader already has.
    if printability and check.ok:
        from .printability import printability_notes

        check.notes = [
            n.message for n in printability_notes(mesh, mode=mode, part=part, preset=preset)
        ]

    return check


def _skip_reason(mode_id: str, modes: list[dict]) -> str:
    """Why a mode was not rendered here, naming the source that would have been run.

    Two shapes reach this: an OpenSCAD mode (the common one — this runner has no
    OpenSCAD kernel and never pretends otherwise), and a mode whose source is neither
    .py/.cq nor declared at all, which is a manifest problem structure.py already
    reports. Either way the message names the mode so a reader knows what was left
    unverified rather than seeing a bare "skip".
    """
    mode = next((m for m in modes if m.get("id") == mode_id), {})
    scad = mode.get("scad_file")
    if isinstance(scad, str):
        return (
            f"OpenSCAD mode ('{scad}') — this checker has no OpenSCAD kernel, so the "
            f"mesh was NOT verified here; the platform renders it"
        )
    return (
        "no CadQuery source (.py/.cq) declared for this mode — nothing to render, so "
        "the mesh was NOT verified"
    )


def check_geometry(
    cartridge_dir: Path,
    manifest: dict,
    *,
    presets: bool = True,
    printability: bool = False,
) -> list[RenderCheck]:
    """Render every (mode, part) the manifest declares and judge each mesh.

    With `presets=True` (the default under --render), ALSO renders every declared
    preset at the same bar — see preset_targets() for why the defaults render is not
    evidence about the parameter points users click.

    Also asserts that the cartridge's modes are DISTINCT: two modes rendering
    byte-identical geometry means the target_part dispatch is not wired, and the user
    picking mode B silently gets mode A.
    """
    from .rules import parameter_defaults, preset_changes_anything, preset_targets, render_targets

    results: list[RenderCheck] = []
    modes = [m for m in manifest.get("modes") or [] if isinstance(m, dict)]

    def _script_for(mode_id: str) -> str | None:
        """The mode's CadQuery source, or None when it is not a CadQuery mode."""
        mode = next((m for m in modes if m.get("id") == mode_id), {})
        script_file = mode.get("cq_file") or mode.get("scad_file")
        if not isinstance(script_file, str) or Path(script_file).suffix not in SCRIPT_SUFFIXES:
            return None
        return script_file

    for mode_id, part_id in render_targets(manifest):
        script_file = _script_for(mode_id)
        if script_file is None:
            # Not a CadQuery mode; the OpenSCAD kernel is the platform's job. That is
            # a SKIP, not a pass: `ok` stays True because an OpenSCAD cartridge is not
            # non-conformant for being OpenSCAD, but `skipped` records why no mesh was
            # judged, so nothing downstream can read this as a verified render (and
            # nothing formats its absent volume).
            results.append(
                RenderCheck(
                    mode=mode_id,
                    part=part_id,
                    ok=True,
                    problems=[],
                    skipped=_skip_reason(mode_id, modes),
                )
            )
            continue

        results.append(
            render_part(
                cartridge_dir, script_file, mode_id, part_id, printability=printability
            )
        )

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
    fallback_vol: float | None = None
    fb_script = next(
        (
            m.get("cq_file")
            for m in modes
            if isinstance(m.get("cq_file"), str)
            and Path(m["cq_file"]).suffix in SCRIPT_SUFFIXES
        ),
        None,
    )
    if fb_script:
        fb = render_part(
            cartridge_dir, fb_script, "__y4d_spec_fallback__", "__y4d_spec_fallback__"
        )
        if fb.ok and fb.volume:
            fallback_vol = round(fb.volume, 6)

    if fallback_vol is not None:
        declared_parts = {p for m in modes for p in m.get("parts") or []}
        matching = [
            c
            for c in results
            if c.ok
            and c.volume
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
                script_for=_script_for,
                printability=printability,
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
    script_for,
    printability: bool,
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

    OpenSCAD modes stay skipped exactly as in the defaults pass: this runner has no
    OpenSCAD kernel and never pretends otherwise.

    CALIBRATION (36-cartridge slice, 101 preset renders): zero preset FAILURES — the
    lane does not turn the commons red, so it is safe to land as part of the verdict.
    The sameness NOTE fired on 2 of 35 cartridges (6%), well under the flood bar, and
    both are true findings: extrusion-hyperobject (manifest/script default drift, see
    above) and tpu-hinge-collar's 'mandarin' preset, which sets band_h and stand_h to
    values the collar body does not consume. Untuned — the rule was right as written.
    """
    by_target = {
        (c.mode, c.part): c for c in default_renders if c.preset is None and c.volume is not None
    }
    checks: list[RenderCheck] = []

    for preset_id, mode_id, part_id, values in targets:
        script_file = script_for(mode_id)
        if script_file is None:
            continue  # OpenSCAD mode — skipped, same as the defaults pass.

        check = render_part(
            cartridge_dir,
            script_file,
            mode_id,
            part_id,
            params=values,
            preset=preset_id,
            printability=printability,
        )

        if check.ok and check.volume is not None and changes_anything(values, defaults):
            baseline = by_target.get((mode_id, part_id))
            if (
                baseline is not None
                and baseline.ok
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

        checks.append(check)

    return checks
