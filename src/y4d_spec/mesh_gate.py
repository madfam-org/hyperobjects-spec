"""`mesh-gate` — mesh resolution and structure, REPORT-ONLY (owner rulings M4–M7, 2026-11-22).

The render lane already fails a mesh that is not watertight, has no volume or holds an
inverted body (`geometry._judge_stl`). It never looked at resolution: an OpenSCAD wall of
48 flats on a 118 mm radius, or a CadQuery circle at 126 segments on a 200 mm radius,
passed unseen. Design and rulings: yantra4d `docs/architecture/
tessellation-profiles-and-mesh-gate.md`.

The checks, per judged mesh (each `(mode, part, preset, engine)` render):

  * `manifold`         — no edge shared by more than two triangles.
  * `zero-area`        — no triangle with zero area (twice its area at or below
                         1e-12 × the largest extent squared, or a repeated vertex), after
                         the vertex merge. The same rule geom-core's `degenerate_faces` uses.
  * `duplicate-faces`  — no triangle listed twice (same three vertices, either winding).
  * `chord-error`      — no surface deviates from the mesh by more than 0.05 mm.
  * `segments`         — every full circle of radius 1 mm or more has at least 32 segments.
  * `size`             — more than 200,000 triangles in one part. A WARNING, never a failure.

Sliver share is never judged (M4): thin triangles are what every CAD tessellator makes.

How the two resolution checks are measured:

  * CadQuery and graph parts, against the SOLID (`solid_resolution`). After the STL export
    every face of the shape carries the triangulation that was written; each triangle's
    centroid and edge midpoints are measured against the face's own surface (planes
    exactly zero, cylinders and spheres in closed form, other surfaces by projection,
    sampled when a part is very large). Segments come from the kernel's own circular
    edges: the polygon each one was meshed into, grouped by circle so a circle split into
    arcs still counts as one full circle. Faceting drawn INTO the solid (a polygon prism,
    a hand-sampled polyline) matches its own mesh exactly and passes here; that is what
    the source lint is for (M5).
  * OpenSCAD parts, against the MESH (`mesh_resolution`): there is no solid, so circles
    are fitted to rings of side faces around an axis-aligned direction. Tilted holes,
    cones and spheres are not measured, and the note says so instead of passing them.

The source lint (`facet_lint`, M5) reads a CadQuery mode's source for `polyline` built
from `sin`/`cos` and `polygon(n, ...)` with 7 ≤ n < 32. It WARNS only, never fails, and
sees only the patterns it is written for.

Report-only (M7, step 1 of 4): every finding is a NOTE unless its check is named strict,
by `--mesh-strict CHECK` (repeatable) or `Y4D_SPEC_MESH_STRICT=check,check` (or `all`);
then it is a failure. `size` and the lint are never strict. The summary line counts, per
check, the cartridges that WOULD fail it.

The opt-out (M6): `verification.stages.geometry.checks.mesh_resolution`, replaced whole by
a mode's `overrides["geometry.mesh_resolution"]`, replaced whole by a part's
`part_overrides.<part>["geometry.mesh_resolution"]`. `{"enabled": false, "reason": "..."}`
switches off `chord-error` and `segments` for that target and nothing else; the finding
is still printed, as exempt with the reason, and counted in `exempt=`. A disabled block
without a non-empty reason is a conformance failure (`mesh_resolution_policy_rules`), in
the manifest lane, with no CAD kernel.
"""

from __future__ import annotations

import ast
import math
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "CHECKS",
    "CHORD_ERROR_LIMIT_MM",
    "MIN_CIRCLE_RADIUS_MM",
    "MIN_SEGMENTS",
    "RESOLUTION_CHECKS",
    "RULE_ID",
    "SIZE_WARN_TRIANGLES",
    "STRICT_ENV",
    "Circle",
    "GateFinding",
    "MeshGateError",
    "Resolution",
    "ResolutionPolicy",
    "apply_policy",
    "cartridge_gate",
    "facet_lint",
    "mesh_resolution",
    "mesh_resolution_policy_rules",
    "resolution_findings",
    "resolve_policy",
    "solid_resolution",
    "strict_checks",
    "structure_counts",
    "structure_findings",
    "summary_clause",
]

RULE_ID = "mesh-gate"
STRICT_ENV = "Y4D_SPEC_MESH_STRICT"

#: The checks the strict switch can turn into failures, in summary order.
CHECKS = ("manifold", "zero-area", "duplicate-faces", "chord-error", "segments")
#: The two an opt-out switches off (M6). The structural checks have no opt-out.
RESOLUTION_CHECKS = ("chord-error", "segments")
#: Reported, counted, never failures.
SIZE = "size"
LINT = "facet-lint"

CHORD_ERROR_LIMIT_MM = 0.05
MIN_SEGMENTS = 32
MIN_CIRCLE_RADIUS_MM = 1.0
SIZE_WARN_TRIANGLES = 200_000

#: geom-core's degenerate-face bound (src/Integrity.cpp, `degenerateCount`): twice the
#: area at or below this × the largest extent squared.
DEGENERATE_REL = 1e-12

POLICY_CHECK_KEY = "mesh_resolution"
POLICY_OVERRIDE_KEY = "geometry.mesh_resolution"

#: Above this many projected sample points in one part, the projection is strided. Planes,
#: cylinders, cones, spheres and tori are measured in closed form and never sampled.
MAX_PROJECTED_SAMPLES = 4_000

#: `polygon(n, ...)` is flagged for 7 <= n < MIN_SEGMENTS. Triangles to hexagons are
#: almost always the shape meant (a hex nut trap), not a circle drawn coarse.
LINT_POLYGON_MIN = 7


class MeshGateError(ValueError):
    """A strict-switch value that names no check (an operator error, exit 2)."""


def strict_checks(
    requested: Iterable[str] = (), environ: Mapping[str, str] | None = None
) -> frozenset[str]:
    """The checks that FAIL this run: `requested` (the CLI) plus `Y4D_SPEC_MESH_STRICT`.

    Empty by default: step 1 of the rollout is report-only. `all` names every check in
    `CHECKS`. An unknown name is refused rather than ignored, so a typo cannot leave a
    lane report-only that meant to block.
    """
    env = os.environ if environ is None else environ
    names: list[str] = [n for n in requested if n]
    raw = env.get(STRICT_ENV, "")
    names.extend(part.strip().lower() for part in raw.split(",") if part.strip())
    chosen: set[str] = set()
    for name in names:
        if name == "all":
            chosen.update(CHECKS)
        elif name in CHECKS:
            chosen.add(name)
        else:
            raise MeshGateError(
                f"mesh-gate strict switch names {name!r}, not one of "
                f"{', '.join(CHECKS)} or all ({STRICT_ENV} / --mesh-strict)"
            )
    return frozenset(chosen)


@dataclass
class GateFinding:
    """One check that would fail on one render. Rendered into a message by the caller,
    which knows the render's target (its engine label can change after judging)."""

    check: str
    detail: str
    exempt: bool = False
    reason: str = ""

    def message(self, target: str, strict: bool = False) -> str:
        if self.exempt:
            return f"{RULE_ID} {self.check}: {target}: exempt — {self.reason} ({self.detail})"
        tier = "FAIL" if strict else "report-only"
        return f"{RULE_ID} {self.check}: {target}: {self.detail} [{tier}]"


# ── structure: manifold, zero-area, duplicate faces, size ────────────────────────────────


def structure_counts(mesh) -> dict[str, int]:
    """Non-manifold edges, degenerate faces, duplicate faces and triangles of a
    vertex-merged trimesh. The trimesh side of the oracle seam (mesh_oracle)."""
    import numpy as np

    faces = np.asarray(mesh.faces)
    if faces.shape[0] == 0:
        return {"nonmanifold_edges": 0, "degenerate_faces": 0, "duplicate_faces": 0,
                "triangles": 0}
    _, counts = np.unique(np.asarray(mesh.edges_sorted), axis=0, return_counts=True)
    nonmanifold = int((counts > 2).sum())

    v = np.asarray(mesh.vertices, dtype=float)
    repeated = (faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2]) | (
        faces[:, 2] == faces[:, 0]
    )
    a, b, c = v[faces[:, 0]], v[faces[:, 1]], v[faces[:, 2]]
    twice_area = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    extent = float(np.max(np.ptp(v, axis=0))) if len(v) else 0.0
    limit = DEGENERATE_REL * extent * extent
    degenerate = int((repeated | (twice_area <= limit)).sum())

    unique_rows = np.unique(np.sort(faces, axis=1), axis=0)
    duplicates = int(faces.shape[0] - unique_rows.shape[0])
    return {"nonmanifold_edges": nonmanifold, "degenerate_faces": degenerate,
            "duplicate_faces": duplicates, "triangles": int(faces.shape[0])}


def structure_findings(measure, duplicate_faces: int | None) -> list[GateFinding]:
    """Findings from the verdict oracle's measurement (`MeshMeasure`) plus trimesh's
    duplicate count (geom-core does not count duplicates, so trimesh always does)."""
    findings: list[GateFinding] = []
    nm = getattr(measure, "nonmanifold_edges", None)
    if nm:
        findings.append(GateFinding(
            "manifold",
            f"{nm} non-manifold edge(s) — an edge shared by more than two triangles "
            f"(measured by {measure.oracle})",
        ))
    degenerate = getattr(measure, "degenerate_faces", None)
    if degenerate:
        findings.append(GateFinding(
            "zero-area",
            f"{degenerate} zero-area triangle(s) after the vertex merge "
            f"(measured by {measure.oracle})",
        ))
    if duplicate_faces:
        findings.append(GateFinding(
            "duplicate-faces",
            f"{duplicate_faces} duplicate triangle(s) — the same three vertices listed "
            f"twice (measured by trimesh)",
        ))
    triangles = getattr(measure, "triangles", None)
    if triangles and triangles > SIZE_WARN_TRIANGLES:
        findings.append(GateFinding(
            SIZE,
            f"{triangles:,} triangles in one part (warning above "
            f"{SIZE_WARN_TRIANGLES:,}; never a failure)",
        ))
    return findings


# ── resolution: chord error and segments ────────────────────────────────────────────────


@dataclass(frozen=True)
class Circle:
    radius: float
    segments: int
    #: The sagitta of the widest segment, r(1 - cos(gap/2)).
    chord_mm: float


@dataclass
class Resolution:
    """What a resolution measurement saw on one part."""

    method: str
    chord_mm: float | None = None
    chord_where: str = ""
    circles: list[Circle] = field(default_factory=list)
    #: What was not measured, said out loud (tilted features, a strided projection).
    caveat: str = ""


def _sagitta(radius: float, gap_rad: float) -> float:
    return radius * (1.0 - math.cos(gap_rad / 2.0))


def resolution_findings(res: Resolution | None) -> list[GateFinding]:
    """`chord-error` and `segments` findings from one measurement."""
    if res is None:
        return []
    findings: list[GateFinding] = []
    caveat = f"; {res.caveat}" if res.caveat else ""
    worst_circle_chord = max((c.chord_mm for c in res.circles), default=None)
    chord = res.chord_mm
    where = res.chord_where
    if worst_circle_chord is not None and (chord is None or worst_circle_chord > chord):
        circle = max(res.circles, key=lambda c: c.chord_mm)
        chord = worst_circle_chord
        where = f"a circle of radius {circle.radius:.3f} mm at {circle.segments} segments"
    if chord is not None and chord > CHORD_ERROR_LIMIT_MM:
        findings.append(GateFinding(
            "chord-error",
            f"chord error {chord:.4f} mm > {CHORD_ERROR_LIMIT_MM} mm, worst on {where} "
            f"({res.method}{caveat})",
        ))
    coarse = [c for c in res.circles
              if c.radius >= MIN_CIRCLE_RADIUS_MM and c.segments < MIN_SEGMENTS]
    if coarse:
        worst = min(coarse, key=lambda c: (c.segments, -c.radius))
        findings.append(GateFinding(
            "segments",
            f"{len(coarse)} full circle(s) of radius >= {MIN_CIRCLE_RADIUS_MM} mm under "
            f"{MIN_SEGMENTS} segments, the coarsest {worst.segments} on radius "
            f"{worst.radius:.3f} mm ({res.method}{caveat})",
        ))
    return findings


def _flatten(result):
    """The shape `_export_stl` meshed: a Workplane's compound, an Assembly's compound."""
    import cadquery as cq
    from cadquery.occ_impl.shapes import compound

    if isinstance(result, cq.Assembly):
        return result.toCompound()
    if isinstance(result, cq.Shape):
        return result
    return compound(*result)


def solid_resolution(result) -> Resolution:
    """Chord error and circle segments of a CadQuery result, against its own B-rep.

    Call AFTER the STL export: it reads the triangulation the export left on every face,
    which is exactly what the STL holds.
    """
    import numpy as np
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Plane
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape

    shape = _flatten(result).wrapped
    res = Resolution(method="measured against the solid")

    # ── chord error, per face ──
    worst = 0.0
    worst_where = ""
    unmeshed = 0
    projected: list[tuple[object, object, object]] = []  # (face, triangulation, trsf)
    projected_triangles = 0
    analytic = _analytic_kinds()
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        explorer.Next()
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            unmeshed += 1
            continue
        adaptor = BRepAdaptor_Surface(face)
        kind = adaptor.GetType()
        if kind == GeomAbs_Plane or tri.NbTriangles() == 0:
            continue
        trsf = loc.Transformation()
        if kind not in analytic:
            projected.append((face, tri, trsf))
            projected_triangles += tri.NbTriangles()
            continue
        nodes = np.array(
            [_xyz(tri.Node(i).Transformed(trsf)) for i in range(1, tri.NbNodes() + 1)]
        )
        tris = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)]) - 1
        err, where = _analytic_error(adaptor, kind, _samples(nodes, tris))
        if err > worst:
            worst, worst_where = err, where

    # Other surfaces (B-splines, revolutions, extrusions, offsets) by projection, at most
    # MAX_PROJECTED_SAMPLES points per part: every `stride`-th triangle, four points each.
    stride = max(1, math.ceil(4 * projected_triangles / MAX_PROJECTED_SAMPLES))
    for face, tri, trsf in projected:
        surface = BRep_Tool.Surface_s(face)
        kind_name = _surface_name(BRepAdaptor_Surface(face).GetType())
        for i in range(1, tri.NbTriangles() + 1, stride):
            a, b, c = (
                np.array(_xyz(tri.Node(n).Transformed(trsf))) for n in tri.Triangle(i).Get()
            )
            for x, y, z in ((a + b + c) / 3.0, (a + b) / 2.0, (b + c) / 2.0, (c + a) / 2.0):
                proj = GeomAPI_ProjectPointOnSurf(gp_Pnt(float(x), float(y), float(z)), surface)
                if proj.NbPoints() == 0:
                    continue
                err = float(proj.LowerDistance())
                if err > worst:
                    worst, worst_where = err, f"a {kind_name} surface"
    res.chord_mm = worst
    res.chord_where = worst_where or "no curved face"
    caveats = []
    if stride > 1:
        caveats.append(f"non-analytic curved faces sampled at 1 triangle in {stride}")
    if unmeshed:
        caveats.append(f"{unmeshed} face(s) carried no triangulation and were not measured")

    # ── segments, per full circle ──
    edges = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edges)
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, ancestors)
    groups: dict[tuple, dict] = {}
    for i in range(1, edges.Extent() + 1):
        edge = TopoDS.Edge_s(edges.FindKey(i))
        curve = BRepAdaptor_Curve(edge)
        if curve.GetType() != GeomAbs_Circle:
            continue
        circ = curve.Circle()
        span = abs(curve.LastParameter() - curve.FirstParameter())
        params = None
        if ancestors.Contains(edge):
            for parent in ancestors.FindFromKey(edge):
                floc = TopLoc_Location()
                ftri = BRep_Tool.Triangulation_s(TopoDS.Face_s(parent), floc)
                if ftri is None:
                    continue
                poly = BRep_Tool.PolygonOnTriangulation_s(edge, ftri, floc)
                if poly is None:
                    continue
                if poly.HasParameters():
                    params = [poly.Parameter(j) for j in range(1, poly.NbNodes() + 1)]
                else:  # evenly spaced is the best a count alone can say
                    n = poly.NbNodes()
                    params = [curve.FirstParameter() + span * j / (n - 1) for j in range(n)]
                break
        if not params or len(params) < 2:
            continue
        gaps = [abs(q - p) for p, q in zip(params, params[1:], strict=False)]
        key = _circle_key(circ)
        group = groups.setdefault(key, {"radius": circ.Radius(), "span": 0.0, "segments": 0,
                                        "gap": 0.0})
        group["span"] += span
        group["segments"] += len(gaps)
        group["gap"] = max(group["gap"], max(gaps))
    for group in groups.values():
        if group["span"] < 2.0 * math.pi - 1e-3:
            continue  # an arc, not a full circle
        res.circles.append(Circle(
            radius=group["radius"],
            segments=group["segments"],
            chord_mm=_sagitta(group["radius"], group["gap"]),
        ))
    res.caveat = "; ".join(caveats)
    return res


def _xyz(p) -> tuple[float, float, float]:
    return (p.X(), p.Y(), p.Z())


def _analytic_kinds() -> frozenset:
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Sphere, GeomAbs_Torus

    return frozenset({GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere, GeomAbs_Torus})


def _samples(nodes, tris):
    """Each triangle's centroid and edge midpoints: where a flat facet sits farthest from
    the surface it approximates (a chord's sagitta is at its midpoint)."""
    import numpy as np

    a, b, c = nodes[tris[:, 0]], nodes[tris[:, 1]], nodes[tris[:, 2]]
    return np.concatenate([(a + b + c) / 3.0, (a + b) / 2.0, (b + c) / 2.0, (c + a) / 2.0])


def _analytic_error(adaptor, kind, samples) -> tuple[float, str]:
    """Largest distance from `samples` to a cylinder, cone, sphere or torus, in closed form."""
    import numpy as np
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Sphere

    def axial(ax1):
        origin = np.array(_xyz(ax1.Location()))
        d = np.array(_xyz(ax1.Direction()))
        rel = samples - origin
        h = rel @ d
        rho = np.linalg.norm(rel - np.outer(h, d), axis=1)
        return h, rho

    if kind == GeomAbs_Cylinder:
        cyl = adaptor.Cylinder()
        _, rho = axial(cyl.Axis())
        return float(np.max(np.abs(rho - cyl.Radius()))), (
            f"a cylinder of radius {cyl.Radius():.3f} mm"
        )
    if kind == GeomAbs_Sphere:
        sph = adaptor.Sphere()
        centre = np.array(_xyz(sph.Location()))
        dist = np.abs(np.linalg.norm(samples - centre, axis=1) - sph.Radius())
        return float(np.max(dist)), f"a sphere of radius {sph.Radius():.3f} mm"
    if kind == GeomAbs_Cone:
        cone = adaptor.Cone()
        h, rho = axial(cone.Axis())
        alpha = cone.SemiAngle()
        dist = np.abs(rho - cone.RefRadius() - h * math.tan(alpha)) * math.cos(alpha)
        return float(np.max(dist)), "a cone"
    torus = adaptor.Torus()
    h, rho = axial(torus.Axis())
    dist = np.abs(np.hypot(rho - torus.MajorRadius(), h) - torus.MinorRadius())
    return float(np.max(dist)), f"a torus of minor radius {torus.MinorRadius():.3f} mm"


def _surface_name(kind) -> str:
    from OCP import GeomAbs

    for name in ("Cone", "Torus", "BezierSurface", "BSplineSurface", "SurfaceOfRevolution",
                 "SurfaceOfExtrusion", "OffsetSurface"):
        if kind == getattr(GeomAbs, f"GeomAbs_{name}", None):
            return name
    return "curved"


def _circle_key(circ) -> tuple:
    loc = circ.Location()
    d = circ.Axis().Direction()
    axis = [d.X(), d.Y(), d.Z()]
    first = next((x for x in axis if abs(x) > 1e-9), 1.0)
    if first < 0:
        axis = [-x for x in axis]
    return (
        round(loc.X(), 4), round(loc.Y(), 4), round(loc.Z(), 4),
        *(round(x, 6) for x in axis),
        round(circ.Radius(), 4),
    )


#: What the mesh circle fit cannot see; printed with any finding it makes.
MESH_FIT_CAVEAT = (
    "circles fitted to the mesh, axis-aligned full circles only; tilted holes, cones "
    "and spheres are not measured"
)


def mesh_resolution(mesh) -> Resolution:
    """Circles fitted to an OpenSCAD mesh (there is no solid to compare with).

    For each axis direction, faces whose normal is perpendicular to it are grouped by
    adjacency (dihedral under 50°) into rings; a ring whose vertices fit a circle (RMS
    residual under 2 % of the radius) all the way round (every 30° sector reached) is a
    full circle. Its segments are 360° over its widest vertex gap, and its chord error is
    the sagitta of that gap — so an uneven ring is judged by its coarsest facet.
    """
    import numpy as np

    res = Resolution(method="mesh circle fit", caveat=MESH_FIT_CAVEAT)
    faces = np.asarray(mesh.faces)
    if faces.shape[0] == 0:
        return res
    vertices = np.asarray(mesh.vertices, dtype=float)
    normals = np.asarray(mesh.face_normals, dtype=float)
    pairs = np.asarray(mesh.face_adjacency)
    angles = np.asarray(mesh.face_adjacency_angles)
    if len(pairs) == 0:
        return res
    for ax in range(3):
        side = np.abs(normals[:, ax]) < 0.15
        keep = side[pairs[:, 0]] & side[pairs[:, 1]] & (angles < math.radians(50))
        sub = pairs[keep]
        if len(sub) == 0:
            continue
        labels = _components(len(faces), sub)
        labels[~side] = -1
        ids, counts = np.unique(labels[labels >= 0], return_counts=True)
        other = [i for i in range(3) if i != ax]
        for label in ids[counts >= 6]:
            ring = np.where(labels == label)[0]
            pts = vertices[np.unique(faces[ring].reshape(-1))][:, other]
            fit = np.c_[2 * pts, np.ones(len(pts))]
            sol, *_ = np.linalg.lstsq(fit, (pts**2).sum(1), rcond=None)
            cx, cy = sol[0], sol[1]
            r = math.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0))
            if r <= 0:
                continue
            rr = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)
            if math.sqrt(float(np.mean((rr - r) ** 2))) > 0.02 * r:
                continue
            theta = np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx)
            sectors = np.unique(np.floor((theta + math.pi) / (math.pi / 6)).astype(int) % 12)
            if len(sectors) < 12:
                continue
            # Vertices at the same azimuth (the top and bottom of one facet) are one
            # azimuth; gaps are measured between distinct ones, unrounded.
            deg = np.sort(np.degrees(theta) % 360.0)
            steps = np.diff(np.concatenate([deg, [deg[0] + 360.0]]))
            gaps = steps[steps > 0.05]
            if len(gaps) < 3:
                continue
            widest = float(np.max(gaps))
            res.circles.append(Circle(
                radius=float(r),
                segments=int(round(360.0 / widest)),
                chord_mm=_sagitta(float(r), math.radians(widest)),
            ))
    return res


def _components(n: int, pairs) -> object:
    """Connected-component label per face, from adjacency pairs (scipy, in [geometry])."""
    import numpy as np
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    pairs = np.asarray(pairs)
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    return labels


# ── the opt-out (M6) ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolutionPolicy:
    enabled: bool = True
    reason: str = ""
    source: str = "default"


def _mode_override(doc: dict, mode_id: str) -> dict:
    verification = doc.get("verification") if isinstance(doc, dict) else None
    overrides = verification.get("mode_overrides") if isinstance(verification, dict) else None
    entry = overrides.get(mode_id) if isinstance(overrides, dict) else None
    return entry if isinstance(entry, dict) else {}


def resolve_policy(doc: object, mode_id: str, part_id: str) -> ResolutionPolicy:
    """The opt-out in force for `(mode, part)`: the part's block, else the mode's, else
    the cartridge's, each replacing the others whole (the body-count and parity rule)."""
    if not isinstance(doc, dict):
        return ResolutionPolicy()
    entry = _mode_override(doc, mode_id)
    part_overrides = entry.get("part_overrides")
    part_block = part_overrides.get(part_id) if isinstance(part_overrides, dict) else None
    block: object = None
    source = "default"
    if isinstance(part_block, dict) and POLICY_OVERRIDE_KEY in part_block:
        block = part_block[POLICY_OVERRIDE_KEY]
        source = f"verification.mode_overrides.{mode_id}.part_overrides.{part_id}"
    elif isinstance(mode_block := entry.get("overrides"), dict) and (
        POLICY_OVERRIDE_KEY in mode_block
    ):
        block = mode_block[POLICY_OVERRIDE_KEY]
        source = f"verification.mode_overrides.{mode_id}.overrides"
    else:
        verification = doc.get("verification")
        stages = verification.get("stages") if isinstance(verification, dict) else None
        geometry = stages.get("geometry") if isinstance(stages, dict) else None
        checks = geometry.get("checks") if isinstance(geometry, dict) else None
        if isinstance(checks, dict) and POLICY_CHECK_KEY in checks:
            block = checks[POLICY_CHECK_KEY]
            source = f"verification.stages.geometry.checks.{POLICY_CHECK_KEY}"
    if not isinstance(block, dict):
        return ResolutionPolicy()
    reason = block.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""
    # A disabled block WITHOUT a reason is not an exemption: it is a conformance failure
    # (mesh_resolution_policy_rules), and the checks keep running until it is fixed.
    enabled = not (block.get("enabled") is False and reason)
    return ResolutionPolicy(enabled=enabled, reason=reason, source=source)


def mesh_resolution_policy_rules(doc: dict) -> list[str]:
    """A mesh-resolution opt-out must say why, in the manifest (M6)."""
    problems: list[str] = []
    verification = doc.get("verification") if isinstance(doc, dict) else None
    if not isinstance(verification, dict):
        return problems

    def _judge(block: object, where: str) -> None:
        if not isinstance(block, dict):
            problems.append(f"{where}: must be an object")
            return
        enabled = block.get("enabled")
        reason = block.get("reason")
        if enabled is not None and not isinstance(enabled, bool):
            problems.append(f"{where}.enabled: must be a boolean")
        if reason is not None and not isinstance(reason, str):
            problems.append(f"{where}.reason: must be a string")
            reason = None
        if enabled is False and not (isinstance(reason, str) and reason.strip()):
            problems.append(
                f"{where}: the mesh-resolution checks (chord-error, segments) are switched "
                "off without a `reason` — an opt-out is visible debt and must say why "
                "this part is faceted on purpose (mesh gate, ruling M6)"
            )

    stages = verification.get("stages")
    geometry = stages.get("geometry") if isinstance(stages, dict) else None
    checks = geometry.get("checks") if isinstance(geometry, dict) else None
    if isinstance(checks, dict) and POLICY_CHECK_KEY in checks:
        _judge(checks[POLICY_CHECK_KEY], f"verification.stages.geometry.checks.{POLICY_CHECK_KEY}")
    overrides = verification.get("mode_overrides")
    if isinstance(overrides, dict):
        for mode_id in sorted(overrides, key=str):
            entry = overrides[mode_id]
            if not isinstance(entry, dict):
                continue
            mode_block = entry.get("overrides")
            if isinstance(mode_block, dict) and POLICY_OVERRIDE_KEY in mode_block:
                _judge(mode_block[POLICY_OVERRIDE_KEY],
                       f'verification.mode_overrides.{mode_id}.overrides["{POLICY_OVERRIDE_KEY}"]')
            part_overrides = entry.get("part_overrides")
            if not isinstance(part_overrides, dict):
                continue
            for part_id in sorted(part_overrides, key=str):
                block = part_overrides[part_id]
                if isinstance(block, dict) and POLICY_OVERRIDE_KEY in block:
                    _judge(block[POLICY_OVERRIDE_KEY],
                           f"verification.mode_overrides.{mode_id}.part_overrides."
                           f'{part_id}["{POLICY_OVERRIDE_KEY}"]')
    return problems


def apply_policy(check, doc: object) -> None:
    """Mark a render's resolution findings exempt when its policy says so. The finding
    stays on the check: an exemption is printed and counted, never dropped."""
    findings = getattr(check, "gate", None)
    if not findings:
        return
    policy = resolve_policy(doc, check.mode, check.part)
    if policy.enabled:
        return
    for finding in findings:
        if finding.check in RESOLUTION_CHECKS:
            finding.exempt = True
            finding.reason = policy.reason


# ── the source lint (M5) ─────────────────────────────────────────────────────────────────

_TRIG = {"sin", "cos"}


def _calls_trig(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in _TRIG:
                return True
    return False


def _int_returns(fn: ast.FunctionDef) -> set[int] | None:
    """The set of int literals a function returns, or None if any return is not one."""
    values: set[int] = set()
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Return):
            v = sub.value
            if isinstance(v, ast.Constant) and isinstance(v.value, int) and not isinstance(
                v.value, bool
            ):
                values.add(v.value)
            else:
                return None
    return values or None


def _assigned_names(nodes: list[ast.AST], functions: dict) -> tuple[set[str], dict]:
    """Names bound to a trig-built sequence, and names bound to known int values.

    One pass over the whole module: names are not scoped per function. That can only ADD
    warnings (two functions reusing a name), never hide one, and a warning is a prompt
    for a person, not a verdict.
    """
    trig_names: set[str] = set()
    int_names: dict[str, set[int]] = {}
    for node in nodes:
        if isinstance(node, ast.For):
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr in {"append", "extend"}
                    and isinstance(inner.func.value, ast.Name)
                    and any(_calls_trig(arg) for arg in inner.args)
                ):
                    trig_names.add(inner.func.value.id)
            continue
        if not (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            continue
        name, value = node.targets[0].id, node.value
        if isinstance(value, ast.ListComp | ast.GeneratorExp) and _calls_trig(value):
            trig_names.add(name)
        elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            target = functions.get(value.func.id)
            if target is not None and (ints := _int_returns(target)):
                int_names[name] = ints
            elif value.func.id in {"list", "tuple"} and _calls_trig(value):
                trig_names.add(name)
        elif isinstance(value, ast.Constant) and type(value.value) is int:
            int_names[name] = {value.value}
    return trig_names, int_names


def _polygon_sides(arg: ast.AST, int_names: dict, functions: dict) -> set[int]:
    """The side counts a `polygon(...)` first argument can take, when the source says."""
    if isinstance(arg, ast.Constant) and type(arg.value) is int:
        return {arg.value}
    if isinstance(arg, ast.Name):
        return int_names.get(arg.id, set())
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
        target = functions.get(arg.func.id)
        return (_int_returns(target) or set()) if target is not None else set()
    return set()


def _lint_source(text: str, filename: str) -> list[str]:
    try:
        tree = ast.parse(text, filename=filename)
    except SyntaxError:
        return []
    nodes = list(ast.walk(tree))
    functions = {n.name: n for n in nodes if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    trig_names, int_names = _assigned_names(nodes, functions)
    findings: set[tuple[int, str]] = set()
    for node in nodes:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if node.func.attr == "polyline":
            names = {n.id for n in ast.walk(arg) if isinstance(n, ast.Name)}
            if _calls_trig(arg) or names & trig_names:
                findings.add((node.lineno, (
                    "polyline built from sin/cos — a curve sampled by hand prints with the "
                    "facets it was sampled at (an involute or another deliberate profile is "
                    "fine; judge it)"
                )))
        elif node.func.attr == "polygon":
            sides = _polygon_sides(arg, int_names, functions)
            small = sorted(v for v in sides if LINT_POLYGON_MIN <= v < MIN_SEGMENTS)
            if small:
                findings.add((node.lineno, (
                    f"polygon(n, ...) with n in {{{', '.join(map(str, small))}}} — a round "
                    "feature drawn as a polygon prints faceted (keep it only if the facets "
                    "are the design)"
                )))
    return [f"{filename}:{line}: {text}" for line, text in sorted(findings)]


def facet_lint(cartridge_dir: Path, manifest: dict) -> list[str]:
    """`facet-lint` notes for every CadQuery source a mode names (M5: warn only)."""
    from .geometry import SCRIPT_SUFFIXES, mode_sources

    seen: set[str] = set()
    notes: list[str] = []
    for mode in manifest.get("modes") or []:
        if not isinstance(mode, dict):
            continue
        for engine, source in mode_sources(mode):
            if engine != "cadquery" or source in seen:
                continue
            seen.add(source)
            path = Path(cartridge_dir) / source
            if path.suffix not in SCRIPT_SUFFIXES or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            notes.extend(
                f"{RULE_ID} {LINT}: {item} [warning]" for item in _lint_source(text, source)
            )
    return notes


# ── per cartridge, and the summary clause ───────────────────────────────────────────────


@dataclass
class CartridgeGate:
    """One cartridge's gate verdict: the messages, and which checks it would fail."""

    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: check -> True when at least one render has a non-exempt finding for it.
    would_fail: dict[str, bool] = field(default_factory=dict)
    exempt: int = 0
    size_warned: bool = False
    linted: bool = False


def cartridge_gate(
    renders: Iterable, strict: frozenset[str], lint_notes: list[str]
) -> CartridgeGate:
    """Sort one cartridge's findings into problems (strict checks) and notes."""
    gate = CartridgeGate(would_fail={c: False for c in CHECKS})
    for check in renders:
        for finding in getattr(check, "gate", None) or []:
            if finding.exempt:
                gate.exempt += 1
                gate.notes.append(finding.message(check.target))
            elif finding.check == SIZE:
                gate.size_warned = True
                gate.notes.append(finding.message(check.target))
            else:
                gate.would_fail[finding.check] = True
                is_strict = finding.check in strict
                (gate.problems if is_strict else gate.notes).append(
                    finding.message(check.target, strict=is_strict)
                )
    gate.notes.extend(lint_notes)
    gate.linted = bool(lint_notes)
    return gate


def summary_clause(gates: Iterable[CartridgeGate], strict: frozenset[str]) -> str:
    """` mesh-gate[report-only]: manifold=0 ... exempt=E size=S facet-lint=L` — every
    count but `exempt` (findings) is a number of CARTRIDGES."""
    gates = list(gates)
    tier = "report-only" if not strict else "strict=" + ",".join(c for c in CHECKS if c in strict)
    counts = " ".join(
        f"{c}={sum(1 for g in gates if g.would_fail.get(c))}" for c in CHECKS
    )
    exempt = sum(g.exempt for g in gates)
    size = sum(1 for g in gates if g.size_warned)
    lint = sum(1 for g in gates if g.linted)
    return f" mesh-gate[{tier}]: {counts} exempt={exempt} {SIZE}={size} {LINT}={lint}"
