"""Does an evaluated interface frame sit on the rendered geometry? (ASM-1 §8)

Two tests, picked by the interface's `geometry_type` (RULE_BY_GEOMETRY_TYPE):

PLANAR — the frame names a mating FACE. Take the mesh triangles whose outward normal
agrees with the frame normal within NORMAL_TOLERANCE_DEG and whose own plane passes
within PLANE_OFFSET_TOLERANCE_MM of the origin. Project them onto the frame plane
and measure how much of them lies within the search radius of the origin; at least
FACE_MIN_AREA_MM2 must, or there is no face there. The search radius starts at
FACE_SEARCH_RADIUS_MM and widens ×FACE_SEARCH_GROWTH per step up to the part's
bounding-box half-diagonal (ASM-1 v1.1, ruling D4), stopping at the first radius that
satisfies the rule; the radius used is the `search_radius_mm` residual. A frame that
passed at 15 mm passes at the first step with the same residuals, so widening can only
turn a fail into a pass, never a pass into a fail. The area is measured by sampling the
disc on a FACE_SAMPLE_PITCH_MM grid restricted to the candidate triangles' bounding
box, which bounds the work no matter how large or how finely tessellated the face is.

AXIS — the frame names a BORE or a SHAFT whose axis is the normal (socket, thread,
threaded_socket, hinge). Take the triangles whose normal is perpendicular to the frame
normal within NORMAL_TOLERANCE_DEG (the walls of anything parallel to the axis) within
AXIS_SEARCH_RADIUS_MM of the axis, split them into connected patches, and fit a
circle to each patch's vertices in the frame plane. A patch is a CYLINDER when the fit
is tight (CYLINDER_FIT_TOLERANCE_MM), it wraps at least CYLINDER_MIN_COVERAGE_DEG, and
the frame axis passes inside it. Of the cylinders whose axial extent reaches the
origin plane the innermost is judged — that is the bore of a counterbored hole whose
origin sits at the counterbore floor, the pin rather than the flange it stands on —
and it must be centred on the origin (AXIS_OFFSET_TOLERANCE_MM), reach the origin
plane (same tolerance), lie on the correct side of it (a bore runs into the material,
away from the partner; a shaft runs toward the partner), and agree with `polarity`
(female = bore, male = shaft). When NO cylinder is found the face test is applied
instead and the verdict says so (rule `planar (no cylinder at the origin)`): a hex
socket is still a socket, and its entrance face is still a face.

Everything else (snap, spline, port, polyhedron, fem_mesh, custom, or no type) is
UNVERIFIED: reported as a warning, never as a pass.

Why these numbers:
  * 2° and 0.1 mm are ASM-1 §8's own. 0.1 mm also equals the STL export's chordal
    deflection, and a planar face tessellates with its vertices exactly on the plane,
    so the tolerance is spent only on authoring rounding.
  * 15 mm first search radius, widened ×1.5 to the half-diagonal: an origin is usually
    the CENTRE of a pattern, and that centre is often a hole — a NEMA 17 face has a
    Ø22 mm pilot (radius 11), an FPV motor pad a Ø5–9 mm shaft clearance. 15 mm reaches
    past those, but not past a NEMA 23 pilot (radius 19.25) or the empty centre of a
    30.5 mm standoff square (21.6 mm to a pillar top): those pass at the first wider
    ring (22.5 or 33.75 mm). The price: an origin slid ALONG its own face by less than
    the radius used is not caught by the face test. Nothing planar can see that; the
    radius is printed so a reviewer can, and the axis test and the assembly closure
    check (ASM-1 §3.5) are what constrain in-plane position.
  * 4 mm² minimum area: a 2 × 2 mm land. Larger than the slivers a fillet or chamfer
    leaves parallel to a face; smaller than the land around the smallest screw in the
    target set (M2 on a 9 × 9 pattern).
  * cylinder fit 0.05 mm: STL vertices of a CadQuery/OpenSCAD cylinder lie ON the
    surface, so a true cylinder fits to ~1e-6 mm; a hexagon fits to ~0.1·r. Half the
    gate tolerance separates the two.
  * 180° coverage: a half-cylinder is the least that still fixes an axis; a fillet or a
    rounded edge, which also has axis-parallel facets, wraps 90°.

Needs numpy and trimesh (the [geometry] extra); imported only under --render.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

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
    "GeometryVerdict",
    "axis_check",
    "frame_rule",
    "planar_check",
    "search_radii",
    "verify_frame_on_mesh",
]

from .frame_gate import (  # the thresholds and the rule map live numpy-free
    AXIS_OFFSET_TOLERANCE_MM,
    AXIS_SEARCH_RADIUS_MM,
    CYLINDER_FIT_TOLERANCE_MM,
    CYLINDER_MIN_COVERAGE_DEG,
    FACE_MIN_AREA_MM2,
    FACE_SAMPLE_PITCH_MM,
    FACE_SEARCH_GROWTH,
    FACE_SEARCH_RADIUS_MM,
    NORMAL_TOLERANCE_DEG,
    PLANE_OFFSET_TOLERANCE_MM,
    RULE_BY_GEOMETRY_TYPE,
    UNVERIFIED_GEOMETRY_TYPES,
    frame_rule,
)

_COVERAGE_BINS = 36


@dataclass
class GeometryVerdict:
    """The result of testing one frame against one mesh."""

    status: str  # "pass" | "fail" | "unverified"
    rule: str  # "planar" | "axis" | "planar (no cylinder at the origin)" | "none"
    message: str
    residuals: dict = field(default_factory=dict)


def _basis(frame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    o = np.asarray(frame.origin, dtype=float)
    n = np.asarray(frame.normal, dtype=float)
    u = np.asarray(frame.reference_x_axis(), dtype=float)
    v = np.cross(n, u)
    return o, n, u, v


# ── planar ────────────────────────────────────────────────────────────────────
def _covered_area(tri2: np.ndarray, radius: float, pitch: float) -> tuple[float, float]:
    """Area of the 2-D triangles inside the disc |p| <= radius, and the nearest
    covered sample's distance to the centre (inf when nothing is covered)."""
    if len(tri2) == 0:
        return 0.0, math.inf
    ticks = np.arange(-radius + pitch / 2, radius, pitch)
    # Only lattice points inside the triangles' bounding box can be covered; dropping the
    # rest keeps the SAME lattice (so a verdict at 15 mm is unchanged) while bounding the
    # work at a wide radius.
    lo, hi = tri2.reshape(-1, 2).min(axis=0) - pitch, tri2.reshape(-1, 2).max(axis=0) + pitch
    tx = ticks[(ticks >= lo[0]) & (ticks <= hi[0])]
    ty = ticks[(ticks >= lo[1]) & (ticks <= hi[1])]
    if len(tx) == 0 or len(ty) == 0:
        return 0.0, math.inf
    gx, gy = np.meshgrid(tx, ty)
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    dist = np.hypot(pts[:, 0], pts[:, 1])
    pts, dist = pts[dist <= radius], dist[dist <= radius]
    covered = np.zeros(len(pts), dtype=bool)
    a, b, c = tri2[:, 0], tri2[:, 1], tri2[:, 2]
    for start in range(0, len(tri2), 256):
        sl = slice(start, start + 256)
        v0, v1 = (b[sl] - a[sl]), (c[sl] - a[sl])
        det = v0[:, 0] * v1[:, 1] - v0[:, 1] * v1[:, 0]
        ok = np.abs(det) > 1e-12
        if not ok.any():
            continue
        v0, v1, det, a0 = v0[ok], v1[ok], det[ok], a[sl][ok]
        d = pts[:, None, :] - a0[None, :, :]
        s = (d[..., 0] * v1[:, 1] - d[..., 1] * v1[:, 0]) / det
        t = (v0[:, 0] * d[..., 1] - v0[:, 1] * d[..., 0]) / det
        eps = 1e-9
        inside = (s >= -eps) & (t >= -eps) & (s + t <= 1 + eps)
        covered |= inside.any(axis=1)
    area = float(covered.sum()) * pitch * pitch
    nearest = float(dist[covered].min()) if covered.any() else math.inf
    return area, nearest


def search_radii(mesh) -> list[float]:
    """The face-search radii, in order: FACE_SEARCH_RADIUS_MM, then ×FACE_SEARCH_GROWTH
    per step, the last one clamped to the part's bounding-box half-diagonal."""
    half_diagonal = 0.5 * float(np.linalg.norm(np.asarray(mesh.extents, dtype=float)))
    radii = [FACE_SEARCH_RADIUS_MM]
    while radii[-1] < half_diagonal:
        radii.append(min(radii[-1] * FACE_SEARCH_GROWTH, half_diagonal))
    return radii


def planar_check(mesh, frame) -> GeometryVerdict:
    """A planar mating face at the frame origin, facing along the frame normal.

    The search radius widens (search_radii) until a ring satisfies the rule; the
    verdict records the radius used, and a failure is diagnosed at the widest radius.
    """
    o, n, u, v = _basis(frame)
    tri = np.asarray(mesh.triangles, dtype=float)
    fn = np.asarray(mesh.face_normals, dtype=float)
    rel = tri - o
    # Plane offset = how far the ORIGIN is from each face's own plane, measured along
    # that face's normal: (centroid - origin) · face normal. Signed so that a face
    # BELOW an origin it should carry reads negative. Measured against the face plane,
    # not as vertex heights above the frame plane — a frame normal 1.5° off (inside the
    # 2° tolerance) would otherwise tip the frame plane 0.4 mm away from the rim of a
    # 15 mm face and fail a frame the tolerance means to accept.
    h = np.einsum("ij,ij->i", rel.mean(axis=1), fn)
    angle = np.degrees(np.arccos(np.clip(fn @ n, -1.0, 1.0)))
    cen2 = np.column_stack([rel.mean(axis=1) @ u, rel.mean(axis=1) @ v])
    cen_dist = np.hypot(cen2[:, 0], cen2[:, 1])
    tri2 = np.stack([rel @ u, rel @ v], axis=-1)  # (F, 3, 2) projected on the plane
    # A triangle can cover the disc while its centroid is far away (one large face in
    # two triangles); its circumscribing radius bounds how far.
    reach = cen_dist - np.linalg.norm(tri2 - cen2[:, None, :], axis=-1).max(axis=1)

    parallel = angle <= NORMAL_TOLERANCE_DEG
    abs_h = np.abs(h)
    on_plane = abs_h <= PLANE_OFFSET_TOLERANCE_MM
    radii = search_radii(mesh)
    for radius in radii:
        near = reach <= radius
        sel = parallel & on_plane & near
        area, nearest = _covered_area(tri2[sel], radius, FACE_SAMPLE_PITCH_MM)
        if area >= FACE_MIN_AREA_MM2:
            residuals = {
                "area_mm2": round(area, 3),
                "search_radius_mm": round(radius, 4),
                "normal_deg": round(float(angle[sel].max()), 4),
                "plane_offset_mm": round(float(abs_h[sel].max()), 4),
                "nearest_material_mm": round(nearest, 3),
            }
            return GeometryVerdict(
                "pass",
                "planar",
                f"face of {area:.1f} mm² within {radius:g} mm "
                f"(normal ≤ {residuals['normal_deg']:.3f}°, plane offset ≤ "
                f"{residuals['plane_offset_mm']:.3f} mm)",
                residuals,
            )

    # Say WHY, at the widest radius searched: the nearest parallel face's offset, and
    # the best normal in the plane.
    radius = radii[-1]
    residuals = {"area_mm2": round(area, 3), "search_radius_mm": round(radius, 4)}
    reasons = []
    par_near = parallel & near
    if par_near.any():
        k = int(np.argmin(np.where(par_near, abs_h, np.inf)))
        residuals["plane_offset_mm"] = round(float(h[k]), 4)
        if not on_plane[k]:
            reasons.append(
                f"the nearest face parallel to the normal (≤ {NORMAL_TOLERANCE_DEG:g}°) "
                f"is {h[k]:+.3f} mm from the origin along its normal "
                f"(tolerance {PLANE_OFFSET_TOLERANCE_MM:g} mm)"
            )
    plane_near = on_plane & near
    if plane_near.any():
        # The LARGEST triangle whose plane passes through the origin speaks for the face
        # there. Not the best angle: thin wall facets of any nearby hole include two
        # whose planes are tangent lines through the origin, at 90°, and they would
        # mask the 180° of a flipped face.
        area_f = np.asarray(mesh.area_faces, dtype=float)
        k = int(np.argmax(np.where(plane_near, area_f, -1.0)))
        residuals["normal_deg"] = round(float(angle[k]), 4)
        if angle[k] > NORMAL_TOLERANCE_DEG:
            reasons.append(
                f"the largest face through the origin is {angle[k]:.2f}° off the normal "
                f"(tolerance {NORMAL_TOLERANCE_DEG:g}°)"
            )
    if area > 0:
        reasons.append(
            f"only {area:.2f} mm² of matching face within {radius:g} mm "
            f"(need {FACE_MIN_AREA_MM2:g} mm²)"
        )
    if not reasons:
        reasons.append(
            f"no face within {radius:g} mm of the origin is parallel to "
            "the normal or passes through the origin plane"
        )
    return GeometryVerdict("fail", "planar", "; ".join(reasons), residuals)


# ── axis ──────────────────────────────────────────────────────────────────────
@dataclass
class _Cylinder:
    radius: float
    centre: np.ndarray  # 2-D, in the frame plane, relative to the origin
    rms: float
    coverage_deg: float
    min_a: float
    max_a: float
    bore: bool
    tilt_deg: float

    @property
    def lateral(self) -> float:
        return float(np.hypot(*self.centre))

    @property
    def axial_gap(self) -> float:
        return max(0.0, self.min_a, -self.max_a)


def _components(mesh, faces: np.ndarray) -> list[np.ndarray]:
    """Connected patches among `faces` (indices), by shared edges."""
    import trimesh

    keep = np.zeros(len(mesh.faces), dtype=bool)
    keep[faces] = True
    adj = np.asarray(mesh.face_adjacency)
    edges = adj[keep[adj[:, 0]] & keep[adj[:, 1]]] if len(adj) else np.empty((0, 2), int)
    return trimesh.graph.connected_components(edges, nodes=faces, min_len=1)


def _fit_cylinder(mesh, comp, o, n, u, v) -> _Cylinder | None:
    vidx = np.unique(np.asarray(mesh.faces)[comp].ravel())
    rel = np.asarray(mesh.vertices, dtype=float)[vidx] - o
    p = np.column_stack([rel @ u, rel @ v])
    if len(p) < 4:
        return None
    # Kåsa algebraic circle fit: x² + y² = a·x + b·y + c.
    lhs = np.column_stack([p, np.ones(len(p))])
    sol, *_ = np.linalg.lstsq(lhs, (p**2).sum(axis=1), rcond=None)
    centre = sol[:2] / 2.0
    r2 = sol[2] + centre @ centre
    if not r2 > 0:
        return None
    radius = math.sqrt(r2)
    dist = np.hypot(*(p - centre).T)
    rms = float(np.sqrt(np.mean((dist - radius) ** 2)))
    az = np.degrees(np.arctan2(*(p - centre).T[::-1])) % 360.0
    bins = np.unique((az // (360.0 / _COVERAGE_BINS)).astype(int))
    tri = np.asarray(mesh.triangles, dtype=float)[comp] - o
    cen = np.column_stack([tri.mean(axis=1) @ u, tri.mean(axis=1) @ v]) - centre
    fn = np.asarray(mesh.face_normals, dtype=float)[comp]
    radial = (fn @ u) * cen[:, 0] + (fn @ v) * cen[:, 1]
    a = rel @ n
    return _Cylinder(
        radius=radius,
        centre=centre,
        rms=rms,
        coverage_deg=len(bins) * 360.0 / _COVERAGE_BINS,
        min_a=float(a.min()),
        max_a=float(a.max()),
        bore=bool((radial < 0).sum() > (radial > 0).sum()),
        tilt_deg=float(np.degrees(np.arcsin(np.clip(np.abs(fn @ n), 0, 1))).max()),
    )


def axis_check(mesh, frame, polarity: object = None) -> GeometryVerdict | None:
    """A bore or shaft whose axis is the frame normal, entering at the origin.

    Returns None when there is no cylinder parallel to the normal around the origin at
    all — the caller then falls back to the face test.
    """
    o, n, u, v = _basis(frame)
    fn = np.asarray(mesh.face_normals, dtype=float)
    rel_c = np.asarray(mesh.triangles_center, dtype=float) - o
    lateral = np.hypot(rel_c @ u, rel_c @ v)
    walls = np.nonzero(
        (np.abs(fn @ n) <= math.sin(math.radians(NORMAL_TOLERANCE_DEG)))
        & (lateral <= AXIS_SEARCH_RADIUS_MM)
    )[0]
    if len(walls) == 0:
        return None
    cylinders = []
    for comp in _components(mesh, walls):
        cyl = _fit_cylinder(mesh, comp, o, n, u, v)
        if (
            cyl is not None
            and cyl.rms <= CYLINDER_FIT_TOLERANCE_MM
            and cyl.coverage_deg >= CYLINDER_MIN_COVERAGE_DEG
            and cyl.lateral < cyl.radius
        ):
            cylinders.append(cyl)
    if not cylinders:
        return None

    tol = AXIS_OFFSET_TOLERANCE_MM
    touching = [c for c in cylinders if c.axial_gap <= tol]
    cyl = (
        min(touching, key=lambda c: c.radius)
        if touching
        else min(cylinders, key=lambda c: c.axial_gap)
    )
    kind = "bore" if cyl.bore else "shaft"
    residuals = {
        "kind": kind,
        "radius_mm": round(cyl.radius, 4),
        "axis_offset_mm": round(cyl.lateral, 4),
        "axial_gap_mm": round(cyl.axial_gap, 4),
        "axial_extent_mm": [round(cyl.min_a, 4), round(cyl.max_a, 4)],
        "tilt_deg": round(cyl.tilt_deg, 4),
        "coverage_deg": cyl.coverage_deg,
        "fit_rms_mm": round(cyl.rms, 5),
    }
    reasons = []
    if cyl.lateral > tol:
        reasons.append(
            f"the {kind} axis is {cyl.lateral:.3f} mm from the origin (tolerance {tol:g} mm)"
        )
    if cyl.axial_gap > tol:
        reasons.append(
            f"the {kind} ends {cyl.axial_gap:.3f} mm from the origin plane along the normal "
            f"(tolerance {tol:g} mm)"
        )
    # A bore runs into the material, away from the partner; a shaft toward it.
    wrong_side = cyl.max_a if cyl.bore else -cyl.min_a
    if wrong_side > tol:
        reasons.append(
            f"the {kind} extends {wrong_side:.3f} mm to the "
            f"{'partner' if cyl.bore else 'material'} side of the origin plane — "
            "the normal points the wrong way"
        )
    expected = {"female": "bore", "male": "shaft"}.get(polarity)
    if expected and expected != kind:
        reasons.append(f"polarity is {polarity} but the cylinder at the origin is a {kind}")
    if reasons:
        return GeometryVerdict("fail", "axis", "; ".join(reasons), residuals)
    return GeometryVerdict(
        "pass",
        "axis",
        f"{kind} Ø{2 * cyl.radius:.3f} mm on the normal (axis offset "
        f"{cyl.lateral:.3f} mm, gap {cyl.axial_gap:.3f} mm, tilt ≤ {cyl.tilt_deg:.2f}°)",
        residuals,
    )


def verify_frame_on_mesh(mesh, frame, interface: dict) -> GeometryVerdict:
    """Apply the rule the interface's geometry_type selects."""
    gtype = interface.get("geometry_type")
    rule = frame_rule(gtype)
    if rule is None:
        return GeometryVerdict(
            "unverified",
            "none",
            f"geometry_type {gtype!r} has no render-time frame rule "
            f"(rules exist for: {', '.join(sorted(RULE_BY_GEOMETRY_TYPE))}) — the frame "
            "was NOT verified against the geometry",
        )
    if rule == "axis":
        verdict = axis_check(mesh, frame, interface.get("polarity"))
        if verdict is not None:
            return verdict
        fallback = planar_check(mesh, frame)
        fallback.rule = "planar (no cylinder at the origin)"
        return fallback
    return planar_check(mesh, frame)
