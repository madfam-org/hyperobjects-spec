"""Declared belt paths (ASM-1 §9, contract v1.3): which pulleys a belt wraps, its length.

    {"id": "belt_a", "kind": "belt", "part": "<catalog belt key>", "closed": false,
     "via": [{"component": "carriage", "interface": "belt_clamp_a"},   # an anchor
             "idler_front_left",                                       # wrapped ccw
             {"component": "pulley_a", "wrap": "cw"},
             {"component": "carriage", "interface": "belt_clamp_b"}]}

A pulley or idler via must resolve to a part with a `belt_engagement`: a toothed part's
cited pitch diameter, or a smooth part's cited running diameter (the belt's pitch line then
runs `teeth_side_offset` or `back_side_offset` outside it, by the via's `side`), and the
circle's centre and axis. An anchor (`{component, interface}`, a belt
clamp) is the interface frame's origin; it may only open and close an open path. A closed
path has only pulleys.

**The path plane.** Every pulley's world axis must be parallel to the first one's within
`PATH_AXIS_TOLERANCE_DEG`. The path normal `n` is that axis, signed so that its
largest-magnitude world component is positive (a horizontal belt is seen from +z). Every
via's point (pitch-circle centre or anchor origin) lies within `PATH_PLANARITY_MM` of the
plane through the first pulley's centre (the spread along `n`). Both tolerances are
CONVENTIONS, checked at the home pose.

**The length** is the belt's pitch-line length: tangent segments between consecutive
pitch circles plus the arcs it wraps. A via wrapped `ccw` turns the belt counter-clockwise
seen from `n` (the pulley is on the belt's left); `cw` the other way. Seen from `n`, with
signed radii s·r (s = +1 ccw, −1 cw, 0 for an anchor), the segment from circle i to i+1
leaves at angle `φ = atan2(Δ) − atan2(k, L)`, `k = s₁r₁ − s₀r₀`, `L = √(|Δ|² − k²)`; the
arc at a pulley is r times the turn from its incoming to its outgoing direction (mod 2π,
in the wrap's sense). The length is reported at every pose; a spread above
`PATH_LENGTH_TOLERANCE_MM` across the sweep is a warning (a CoreXY loop keeps its length).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .transforms import Matrix, angle_between_deg, apply_point, apply_vector, column, matmul

__all__ = [
    "PATH_AXIS_TOLERANCE_DEG",
    "PATH_LENGTH_TOLERANCE_MM",
    "PATH_LOOP_TOLERANCE_MM",
    "PATH_PLANARITY_MM",
    "PathGeometryError",
    "PathResult",
    "Via",
    "effective_diameter",
    "path_length",
    "path_vias",
]

#: CONVENTION: how far the pulleys' axes may be from parallel (the mate rule's angle).
PATH_AXIS_TOLERANCE_DEG = 0.5
#: CONVENTION: how far the vias may spread along the path normal, at home.
PATH_PLANARITY_MM = 0.5
#: CONVENTION: a length spread across the pose sweep above this is a warning.
PATH_LENGTH_TOLERANCE_MM = 0.1
#: CONVENTION: a closed-loop belt whose computed home length differs from its catalog
#: `loop_length` by more than this warns (a tensioner makes the centre distance a choice).
PATH_LOOP_TOLERANCE_MM = 0.5


class PathGeometryError(ValueError):
    """The path's geometry has no belt length (overlapping circles, axes not parallel)."""


@dataclass(frozen=True)
class Via:
    component: str
    wrap: str | None = None  # "ccw" | "cw" for a pulley; None for an anchor
    interface: str | None = None  # set for an anchor
    side: str | None = None  # "teeth" | "back" for a pulley; None for an anchor

    @property
    def is_anchor(self) -> bool:
        return self.interface is not None

    def label(self) -> str:
        if self.is_anchor:
            return f"{self.component}.{self.interface}"
        return f"{self.component} ({self.wrap}, {self.side})"


@dataclass
class PathResult:
    """One path's verdict. Lengths are pitch-line lengths in mm."""

    path_id: str
    part: str
    closed: bool
    vias: list[Via]
    pitch_mm: float | None = None
    loop_length_mm: float | None = None  # a closed-loop belt's catalog length
    length_mm: float | None = None  # at home
    planarity_mm: float | None = None
    axis_deg: float | None = None
    normal: tuple[float, float, float] | None = None
    lengths: dict[str, float] = field(default_factory=dict)  # by pose name
    ok: bool = False

    @property
    def length_spread_mm(self) -> float | None:
        if not self.lengths:
            return None
        return max(self.lengths.values()) - min(self.lengths.values())

    def as_dict(self) -> dict:
        def r(v):
            return None if v is None else round(v, 6) + 0.0
        spread = self.length_spread_mm
        return {
            "path": self.path_id, "part": self.part, "closed": self.closed,
            "via": [v.label() for v in self.vias], "length_mm": r(self.length_mm),
            "loop_length_mm": r(self.loop_length_mm),
            "teeth": r(self.length_mm / self.pitch_mm)
            if self.length_mm is not None and self.pitch_mm else None,
            "planarity_mm": r(self.planarity_mm), "axis_deg": r(self.axis_deg),
            "length_spread_mm": r(spread), "ok": self.ok,
        }


def path_vias(path: Mapping) -> list[Via]:
    out = []
    for item in path.get("via") or []:
        if isinstance(item, str):
            out.append(Via(item, wrap="ccw", side="teeth"))
        elif "interface" in item:
            out.append(Via(item["component"], interface=item["interface"]))
        else:
            out.append(Via(item["component"], wrap=item.get("wrap", "ccw"),
                           side=item.get("side", "teeth")))
    return out


def effective_diameter(via: Via, engagement, belt: Mapping | None) -> float:
    """The diameter the belt's pitch line runs on at this via (ASM-1 §9): a toothed part's
    pitch diameter (teeth only), or a smooth part's running diameter plus twice the belt's
    pitch-line offset for the side on it. Raises PathGeometryError naming what is missing."""
    if engagement.toothed:
        if via.side != "teeth":
            raise PathGeometryError(
                f"{via.component}: runs the belt's {via.side} on a toothed part; only the "
                "teeth mesh a pitch diameter")
        return engagement.diameter_mm
    key = f"{via.side}_side_offset_mm"
    offset = (belt or {}).get(key)
    if offset is None:
        raise PathGeometryError(
            f"{via.component}: a smooth part (running diameter "
            f"{engagement.diameter_mm:g} mm) with the belt's {via.side} on it needs the belt's "
            f"`{via.side}_side_offset`, which its catalog entry does not state")
    return engagement.diameter_mm + 2.0 * offset


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def path_normal(axis) -> tuple[float, float, float]:
    """The axis signed so that its largest-magnitude world component is positive."""
    k = max(range(3), key=lambda i: abs(axis[i]))
    return tuple(-v if axis[k] < 0 else v for v in axis)  # type: ignore[return-value]


def _basis(n):
    axes = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    seed = min(axes, key=lambda a: abs(_dot(a, n)))
    d = _dot(seed, n)
    u = _unit((seed[0] - d * n[0], seed[1] - d * n[1], seed[2] - d * n[2]))
    return u, _cross(n, u)


def path_length(
    vias: Sequence[Via],
    closed: bool,
    placements: Mapping[str, Matrix],
    engagements: Mapping[str, object],
    anchors: Mapping[tuple[str, str], Matrix],
    diameters: Sequence[float | None],
) -> tuple[float, float, float, tuple[float, float, float]]:
    """(length, planarity spread, worst axis angle, normal) of one path at one pose.

    `engagements[component]` is a BeltEngagement in the component's model frame;
    `anchors[(component, interface)]` is that interface's H(F); `diameters[i]` is via i's
    effective diameter (`effective_diameter`; None for an anchor). Raises
    PathGeometryError."""
    points, radii, axes = [], [], []
    for via, diameter in zip(vias, diameters, strict=True):
        t = placements[via.component]
        if via.is_anchor:
            w = matmul(t, anchors[(via.component, via.interface)])
            points.append(column(w, 3))
            radii.append(0.0)
            axes.append(None)
        else:
            e = engagements[via.component]
            points.append(apply_point(t, e.center))
            sign = 1.0 if via.wrap == "ccw" else -1.0
            radii.append(sign * diameter / 2.0)
            axes.append(_unit(apply_vector(t, e.axis)))
    first_axis = next(a for a in axes if a is not None)
    n = path_normal(first_axis)
    worst_axis = 0.0
    for a in axes:
        if a is not None:
            worst_axis = max(worst_axis, min(angle_between_deg(a, n),
                                             angle_between_deg(a, tuple(-v for v in n))))
    if worst_axis > PATH_AXIS_TOLERANCE_DEG:
        raise PathGeometryError(
            f"the pulley axes are {worst_axis:.4f}° from parallel (≤ {PATH_AXIS_TOLERANCE_DEG}°, "
            "a convention): the path does not lie in one plane")
    origin = next(p for p, a in zip(points, axes, strict=True) if a is not None)
    heights = [_dot(_sub(p, origin), n) for p in points]
    planarity = max(heights) - min(heights)
    u, v = _basis(n)
    flat = [(_dot(p, u), _dot(p, v)) for p in points]

    count = len(vias)
    segments = count if closed else count - 1
    directions: list[float] = []
    length = 0.0
    for i in range(segments):
        j = (i + 1) % count
        dx, dy = flat[j][0] - flat[i][0], flat[j][1] - flat[i][1]
        k = radii[j] - radii[i]
        dist2 = dx * dx + dy * dy
        if dist2 - k * k <= 1e-12:
            raise PathGeometryError(
                f"{vias[i].label()} → {vias[j].label()}: the pitch circles overlap or touch "
                f"({math.sqrt(dist2):.4f} mm apart for a radius difference {abs(k):.4f} mm); no "
                "straight span joins them")
        span = math.sqrt(dist2 - k * k)
        length += span
        directions.append(math.atan2(dy, dx) - math.atan2(k, span))
    two_pi = 2.0 * math.pi
    for i, r in enumerate(radii):
        if r == 0.0:
            continue
        # Closed: directions[-1] is the span into via 0. Open: pulleys sit between the
        # anchors, so both spans exist.
        d_in, d_out = directions[i - 1], directions[i]
        turn = (d_out - d_in) % two_pi if r > 0 else (d_in - d_out) % two_pi
        length += abs(r) * turn
    return length, planarity, worst_axis, n
