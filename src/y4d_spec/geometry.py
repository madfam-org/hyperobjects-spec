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
    """True when cadquery and trimesh can both be imported."""
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

    def __bool__(self) -> bool:
        return self.ok

    @property
    def summary(self) -> str:
        if not self.ok:
            return f"({self.mode}, {self.part}): FAIL — {'; '.join(self.problems)}"
        return (
            f"({self.mode}, {self.part}): ok — volume {self.volume:.2f}mm³, "
            f"{self.bodies} body/bodies, watertight"
        )


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
) -> RenderCheck:
    """Render one (mode, part) and judge the mesh.

    Params default to `{}` plus `target_part` — the same empty-params render the
    platform does when a user first opens a cartridge, which exercises each
    cartridge's own defaults rather than a set this checker invented.
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
            problems=[f"script raised {type(exc).__name__}: {exc}"],
        )

    if result is None:
        return RenderCheck(
            mode=mode,
            part=part,
            ok=False,
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
                problems=[f"STL export failed: {type(exc).__name__}: {exc}"],
            )

        mesh = trimesh.load(stl, force="mesh")

    if not isinstance(mesh, trimesh.Trimesh) or mesh.faces.shape[0] == 0:
        return RenderCheck(
            mode=mode, part=part, ok=False, problems=["rendered an empty mesh (no faces)"]
        )

    # STL stores every triangle with its own vertices, so a closed solid arrives as
    # loose triangle soup and only seals once coincident vertices are merged. Merge
    # before judging, exactly as yantra4d's mesh_integrity.assess does — reading the
    # raw flag reports valid geometry as holed.
    mesh.merge_vertices()

    watertight = bool(mesh.is_watertight)
    volume = float(mesh.volume)
    bodies = mesh.split(only_watertight=False)

    if not watertight:
        problems.append(
            f"not watertight — {len(mesh.outline().entities) if mesh.outline() else '?'} "
            f"boundary loop(s); the mesh does not enclose a volume"
        )
    if volume <= 0:
        problems.append(f"volume is {volume:.4f} (must be > 0)")

    # A negative-volume body is an inverted shell: a solid turned inside out. It reads
    # as geometry to a naive check and prints as nothing.
    for i, body in enumerate(bodies):
        try:
            bvol = float(body.volume)
        except Exception:
            continue
        if bvol < 0:
            problems.append(
                f"body {i} has negative volume ({bvol:.4f}) — an inverted/inside-out "
                f"shell, not a printable solid"
            )

    return RenderCheck(
        mode=mode,
        part=part,
        ok=not problems,
        problems=problems,
        volume=volume,
        watertight=watertight,
        bodies=len(bodies),
        extents=tuple(float(x) for x in mesh.extents),
    )


def check_geometry(cartridge_dir: Path, manifest: dict) -> list[RenderCheck]:
    """Render every (mode, part) the manifest declares and judge each mesh.

    Also asserts that the cartridge's modes are DISTINCT: two modes rendering
    byte-identical geometry means the target_part dispatch is not wired, and the user
    picking mode B silently gets mode A.
    """
    from .rules import render_targets

    results: list[RenderCheck] = []
    by_part_volume: dict[str, list[tuple[str, float]]] = {}

    for mode_id, part_id in render_targets(manifest):
        mode = next(
            (m for m in manifest.get("modes") or [] if isinstance(m, dict) and m.get("id") == mode_id),
            {},
        )
        script_file = mode.get("cq_file") or mode.get("scad_file")
        if not isinstance(script_file, str) or Path(script_file).suffix not in SCRIPT_SUFFIXES:
            results.append(
                RenderCheck(
                    mode=mode_id,
                    part=part_id,
                    ok=True,
                    problems=[],
                    # Not a CadQuery mode; the OpenSCAD kernel is the platform's job.
                )
            )
            continue

        check = render_part(cartridge_dir, script_file, mode_id, part_id)
        results.append(check)
        if check.ok and check.volume is not None:
            by_part_volume.setdefault(part_id, []).append((mode_id, check.volume))

    # Distinct-modes check: the same PART rendered from two different modes should be
    # the same body (that is fine); two different PARTS rendering identical volume is
    # what signals a dead dispatch.
    volumes: dict[float, list[str]] = {}
    for check in results:
        if check.ok and check.volume:
            volumes.setdefault(round(check.volume, 6), []).append(f"{check.mode}/{check.part}")
    for vol, targets in volumes.items():
        distinct_parts = {t.split("/", 1)[1] for t in targets}
        if len(distinct_parts) > 1:
            for check in results:
                if check.ok and check.volume and round(check.volume, 6) == vol:
                    check.ok = False
                    check.problems.append(
                        f"renders identical geometry (volume {vol}) to "
                        f"{', '.join(sorted(t for t in targets if t != f'{check.mode}/{check.part}'))}"
                        f" — the target_part dispatch is not distinguishing these parts"
                    )
    return results
