"""The render-time frame gate (ASM-1 §8), run by `y4d-spec check --render`.

For every `hyperobject.cdg_interfaces[]` entry that declares a `frame`, at the
manifest defaults and at every declared preset:

  1. evaluate the frame (frame_eval, full injection over the manifest defaults);
  2. render the frame's part AT THAT SAME PARAMETER POINT through the keystone's own
     render path (render_part / render_part_graph / render_part_openscad);
  3. test the frame against the mesh by the interface's geometry_type
     (frame_geometry: a planar face, or a bore/shaft axis).

A mismatch is a conformance FAILURE that names the interface, the parameter point and
the residuals. A geometry_type with no rule, or a part that could not be rendered on
this machine (an OpenSCAD-only part without the binary), is UNVERIFIED: a note, never a
pass, and counted separately in the summary line.

The parameter point is full injection, not the geometry lane's `{}` render. A frame
is an expression over the MANIFEST defaults; the `{}` render uses the SCRIPT's own
PARAM fallbacks, and where the two drift (default_drift.py finds such cartridges) a
frame would be compared against geometry from another parameter point entirely. So
the gate renders what it evaluates: every declared parameter, its default or the
preset's value. Renders are cached per (part, point), so interfaces sharing a part
share a render.

Which source renders the part: the first mode (in manifest order) that lists it, on
that mode's first engine that can run here (cadquery, then openscad when a binary is
present, then graph). One engine is enough: cross-kernel agreement is --parity's job.

A manifest without any frame costs nothing: `check_frames` returns [] before it
imports a CAD kernel or renders anything, so every commons cartridge checks exactly
as before until frames are authored.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .frame_eval import FrameEvaluationError, evaluate_frame, resolve_parameters

__all__ = [
    "AXIS_OFFSET_TOLERANCE_MM",
    "AXIS_SEARCH_RADIUS_MM",
    "CYLINDER_FIT_TOLERANCE_MM",
    "CYLINDER_MIN_COVERAGE_DEG",
    "FACE_MIN_AREA_MM2",
    "FACE_SAMPLE_PITCH_MM",
    "FACE_SEARCH_GROWTH",
    "FACE_SEARCH_RADIUS_MM",
    "NORMAL_TOLERANCE_DEG",
    "PLANE_OFFSET_TOLERANCE_MM",
    "RULE_BY_GEOMETRY_TYPE",
    "UNVERIFIED_GEOMETRY_TYPES",
    "FrameCheck",
    "check_frames",
    "describe_rules",
    "frame_rule",
    "framed_interfaces",
    "parameter_points",
]

DEFAULTS_POINT = "defaults"

# The thresholds and the rule map. Why each number is what it is: frame_geometry's
# docstring. They live here, numpy-free, so `y4d-spec rules` can print them on a base
# install; frame_geometry (numpy, trimesh) imports them.
NORMAL_TOLERANCE_DEG = 2.0
PLANE_OFFSET_TOLERANCE_MM = 0.1
#: The FIRST face-search radius. The search widens from here (ASM-1 v1.1, ruling D4):
#: ×FACE_SEARCH_GROWTH per step, up to the part's bounding-box half-diagonal, and stops
#: at the first radius whose ring holds a face that satisfies the rule. The radius used
#: is recorded as `search_radius_mm`.
FACE_SEARCH_RADIUS_MM = 15.0
FACE_SEARCH_GROWTH = 1.5
FACE_MIN_AREA_MM2 = 4.0
FACE_SAMPLE_PITCH_MM = 0.25
AXIS_SEARCH_RADIUS_MM = 15.0
AXIS_OFFSET_TOLERANCE_MM = 0.1
CYLINDER_FIT_TOLERANCE_MM = 0.05
CYLINDER_MIN_COVERAGE_DEG = 180.0
#: geometry_type → "planar" | "axis". A type not listed is UNVERIFIED. All 21 types
#: of the project-manifest enum are accounted for here or in
#: UNVERIFIED_GEOMETRY_TYPES (a test holds the two against the schema).
RULE_BY_GEOMETRY_TYPE: dict[str, str] = {
    # A face the partner seats on.
    "bolt_pattern": "planar",
    "flange": "planar",
    "grid": "planar",
    "surface": "planar",
    "pocket": "planar",  # the floor; the partner sits on it
    "boss": "planar",  # the end face
    "seal": "planar",  # a face seal's land
    "screen": "planar",  # the mounting face
    "profile": "planar",  # an extrusion's end / seating face
    "engraving": "planar",
    # The commons' 20+ rails are DIN TS35 rails, dovetails, T-tracks and slots —
    # prismatic, seated on a face, never round — so the seat face is what is checked.
    "rail": "planar",
    # Round features whose axis is the normal.
    "socket": "axis",
    "threaded_socket": "axis",
    "thread": "axis",
    "hinge": "axis",
}
UNVERIFIED_GEOMETRY_TYPES = ("snap", "spline", "port", "polyhedron", "fem_mesh", "custom")




def frame_rule(geometry_type: object) -> str | None:
    """'planar', 'axis', or None (unverified) for an interface's geometry_type."""
    return RULE_BY_GEOMETRY_TYPE.get(geometry_type) if isinstance(geometry_type, str) else None


def describe_rules() -> list[str]:
    """The `y4d-spec rules` paragraph for this gate, built from the live constants."""
    planar = ", ".join(sorted(k for k, r in RULE_BY_GEOMETRY_TYPE.items() if r == "planar"))
    axis = ", ".join(sorted(k for k, r in RULE_BY_GEOMETRY_TYPE.items() if r == "axis"))
    return [
        "  8. the FRAME GATE (--render; ASM-1 §8, y4d_spec.frame_gate): every",
        "       cdg_interface with a `frame` is evaluated (y4d_spec.frame_eval, full",
        "       injection) at the defaults and at every preset, its part is rendered at",
        "       that same point, and the frame is tested against the mesh:",
        f"         planar ({planar}):",
        f"            face normals within {NORMAL_TOLERANCE_DEG:g}°, the face plane within "
        f"{PLANE_OFFSET_TOLERANCE_MM:g}mm",
        f"            of the origin, and at least {FACE_MIN_AREA_MM2:g}mm² of such face "
        f"within {FACE_SEARCH_RADIUS_MM:g}mm",
        f"            of the origin — widening ×{FACE_SEARCH_GROWTH:g} per step up to the "
        "part's",
        "            bounding-box half-diagonal until a ring holds such a face (the",
        "            radius used is recorded as search_radius_mm).",
        f"         axis ({axis}):",
        "            the innermost cylinder parallel to the normal that reaches the origin",
        f"            plane (fit within {CYLINDER_FIT_TOLERANCE_MM:g}mm, wrapping >= "
        f"{CYLINDER_MIN_COVERAGE_DEG:g}°) must be centred",
        f"            within {AXIS_OFFSET_TOLERANCE_MM:g}mm, lie on the correct side "
        "(a bore into the material,",
        "            a shaft toward the partner) and match polarity; with no cylinder",
        "            there at all, the planar test applies and the verdict says so.",
        f"         other types ({', '.join(UNVERIFIED_GEOMETRY_TYPES)}):",
        "            UNVERIFIED — a note, never a pass. A mismatch is a FAILURE.",
        "       A manifest with no frame renders nothing extra and prints no `frames=`",
        "       clause; with frames the summary adds `frames=P/M ok, unverified=U,",
        "       failures=F`.",
    ]


@dataclass
class FrameCheck:
    """The verdict on one interface frame at one parameter point."""

    interface: str
    part: str
    #: "defaults" or the preset id.
    point: str
    status: str  # "pass" | "fail" | "unverified"
    rule: str
    message: str
    residuals: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Not a failure. An unverified check is ok — and is NOT a pass."""
        return self.status != "fail"

    @property
    def summary(self) -> str:
        where = "defaults" if self.point == DEFAULTS_POINT else f"preset '{self.point}'"
        head = f"frame '{self.interface}' ({self.part}, {where}, {self.rule})"
        if self.status == "pass":
            return f"{head}: ok — {self.message}"
        if self.status == "unverified":
            return f"{head}: UNVERIFIED — {self.message}"
        residuals = json.dumps(self.residuals, sort_keys=True, ensure_ascii=False)
        return f"{head}: FAIL — {self.message} (residuals {residuals})"


def framed_interfaces(manifest: dict) -> list[dict]:
    """The cdg_interfaces entries that declare a frame object."""
    ho = manifest.get("hyperobject")
    interfaces = ho.get("cdg_interfaces") if isinstance(ho, dict) else None
    return [
        iface
        for iface in interfaces or []
        if isinstance(iface, dict) and isinstance(iface.get("frame"), dict)
    ]


def parameter_points(manifest: dict, presets: bool = True) -> list[tuple[str, dict]]:
    """(point id, given values): the defaults, then every declared preset in order.

    Every preset, whatever mode it names: a frame follows the parameters, and a preset
    is a parameter point the UI ships whichever mode it was authored in.
    """
    points: list[tuple[str, dict]] = [(DEFAULTS_POINT, {})]
    if not presets:
        return points
    for i, preset in enumerate(manifest.get("presets") or []):
        if isinstance(preset, dict) and isinstance(preset.get("values"), dict):
            pid = str(preset.get("id") or preset.get("slug") or f"presets[{i}]")
            points.append((pid, preset["values"]))
    return points


class _PartRenderer:
    """Renders (part, parameter point) once and keeps the mesh for every interface."""

    def __init__(self, cartridge_dir, manifest, tmp, *, library_paths, require_openscad,
                 openscad_timeout):
        from .geometry import mode_sources, part_render_modes
        from .openscad import openscad_binary

        self.dir = Path(cartridge_dir)
        self.manifest = manifest
        self.tmp = Path(tmp)
        self.library_paths = library_paths
        self.require_openscad = require_openscad
        self.timeout = openscad_timeout
        self.binary = openscad_binary()
        self.render_mode_of = part_render_modes(manifest)
        self.mode_sources = mode_sources
        self.cache: dict[str, tuple[object, str | None, str | None]] = {}

    def _source(self, part: str) -> tuple[str, str, str] | str:
        """(mode, engine, source) to render `part`, or why there is none."""
        listed = False
        for mode in self.manifest.get("modes") or []:
            if not isinstance(mode, dict) or part not in (mode.get("parts") or []):
                continue
            listed = True
            for engine, source in self.mode_sources(mode):
                if engine == "openscad" and self.binary is None:
                    continue
                return mode.get("id"), engine, source
        if not listed:
            return f"part '{part}' is listed in no mode, so nothing renders it"
        return (
            f"no source for part '{part}' can render here (OpenSCAD-only without an "
            "OpenSCAD binary, or no renderable source)"
        )

    def mesh(self, part: str, params: dict) -> tuple[object, str | None, str | None]:
        """(trimesh mesh or None, failure, unverified reason)."""
        key = json.dumps([part, params], sort_keys=True, default=str)
        if key in self.cache:
            return self.cache[key]
        self.cache[key] = out = self._render(part, params, len(self.cache))
        return out

    def _render(self, part, params, n):
        import trimesh

        from .geometry import render_part, render_part_graph
        from .openscad import render_part_openscad

        found = self._source(part)
        if isinstance(found, str):
            if self.require_openscad and "OpenSCAD" in found:
                return None, f"--require-openscad: {found}", None
            return None, None, found
        mode, engine, source = found
        stl_dir = self.tmp / f"r{n}"
        if engine == "openscad":
            check = render_part_openscad(
                self.dir, source, mode, part, render_mode=self.render_mode_of.get(part, 0),
                params=params, library_paths=self.library_paths, timeout=self.timeout,
                binary=self.binary, stl_dir=stl_dir,
            )
        elif engine == "graph":
            check = render_part_graph(
                self.dir, source, mode, part, manifest=self.manifest, params=params,
                stl_dir=stl_dir,
            )
        else:
            check = render_part(self.dir, source, mode, part, params=params, stl_dir=stl_dir)
        if not check.ok or not check.stl_path:
            why = "; ".join(check.problems) or "no mesh was produced"
            return None, f"part did not render at this parameter point ({engine}): {why}", None
        return trimesh.load(check.stl_path, force="mesh"), None, None


def check_frames(
    cartridge_dir: str | Path,
    manifest: dict,
    *,
    presets: bool = True,
    library_paths: list[Path] | None = None,
    require_openscad: bool = False,
    openscad_timeout: int | None = None,
) -> list[FrameCheck]:
    """Verify every interface frame against the rendered part. [] when none exist."""
    interfaces = framed_interfaces(manifest)
    if not interfaces:
        return []

    from .frame_geometry import verify_frame_on_mesh
    from .geometry import OPENSCAD_TIMEOUT_S

    checks: list[FrameCheck] = []
    points = parameter_points(manifest, presets)
    with tempfile.TemporaryDirectory(prefix="y4d-frames-") as tmp:
        renderer = _PartRenderer(
            cartridge_dir, manifest, tmp, library_paths=library_paths,
            require_openscad=require_openscad,
            openscad_timeout=OPENSCAD_TIMEOUT_S if openscad_timeout is None else openscad_timeout,
        )
        for iface in interfaces:
            iid = str(iface.get("id", "?"))
            part = str(iface["frame"].get("part", "?"))
            rule = frame_rule(iface.get("geometry_type")) or "none"
            for point, given in points:
                try:
                    frame = evaluate_frame(manifest, iface, given)
                except FrameEvaluationError as exc:
                    checks.append(FrameCheck(iid, part, point, "fail", rule,
                                             f"frame does not evaluate: {exc}"))
                    continue
                params = resolve_parameters(manifest, given)
                mesh, failure, unverified = renderer.mesh(frame.part, params)
                if failure:
                    checks.append(FrameCheck(iid, part, point, "fail", rule, failure))
                    continue
                if unverified:
                    checks.append(FrameCheck(iid, part, point, "unverified", rule,
                                             f"{unverified} — the frame was NOT verified"))
                    continue
                verdict = verify_frame_on_mesh(mesh, frame, iface)
                residuals = dict(verdict.residuals)
                residuals["origin"] = [round(c, 4) for c in frame.origin]
                residuals["normal"] = [round(c, 6) for c in frame.normal]
                checks.append(FrameCheck(iid, part, point, verdict.status, verdict.rule,
                                         verdict.message, residuals))
    return checks
