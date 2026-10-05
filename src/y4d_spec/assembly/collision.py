"""`--collision`: rigid-body interference at every pose of the sweep (ASM-1 §3.7, §9).

Each component becomes a solid in its own model frame:

* a **cartridge** is rendered at the assembly's parameters (its CadQuery source, every
  part the component produces; the same sandboxed execution `check --render` uses);
* a **standard part** is its catalog `envelope`: a union of boxes and cylinders built
  from cited dimensions;
* an **external design** is its declared `envelope`, an original proxy body (owner
  decision D3), when it declares one.

A component with no solid (no envelope, a graph- or OpenSCAD-only cartridge, a cartridge
that does not render) is NOT silently skipped. It is named in a `collision-unchecked`
warning, and `report.collision` reads `partial`.

Each pose (home, every limit, every Halton sample) places the solids by the validator's
own transforms and intersects every pair whose bounding boxes overlap (OpenCASCADE
boolean common, through CadQuery). A pair is computed once per relative placement: a
pair that does not move relative to itself across the sweep costs one boolean.

* An overlap above `COLLISION_TOLERANCE_MM3` (1 mm³, a CONVENTION; the bar the
  phase-4 render probes used) is an error, `collision`, unless the document declares it in
  `allowed_overlaps: [{a, b, max_mm3, reason}]` and it stays within `max_mm3`.
* A declared allowance that never sees an overlap warns `allowed-overlap-unused`, so
  stale declarations do not accumulate.

The geometry extra (CadQuery) is required. Without it the check reports
`collision=unavailable` and a warning, never a pass.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .transforms import Matrix, matmul, rigid_inverse

__all__ = [
    "COLLISION_TOLERANCE_MM3",
    "CollisionResult",
    "check_collisions",
    "component_solid",
]

#: CONVENTION: overlaps at or below this volume are numerical contact, not interference.
COLLISION_TOLERANCE_MM3 = 1.0
#: How finely a relative placement is keyed for the per-pair cache (mm, and unitless for
#: the rotation block).
_KEY_DIGITS = 6


@dataclass
class CollisionResult:
    """What `check_collisions` found. `pairs` maps "a|b" to the worst overlap (mm³) and
    the pose it was seen at, for every pair that overlapped above the tolerance."""

    status: str  # "checked" | "partial" | "unavailable"
    unchecked: dict[str, str] = field(default_factory=dict)  # component → why
    pairs: dict[str, dict] = field(default_factory=dict)
    booleans: int = 0  # boolean operations actually run (after the cache and the prune)


def _cq():
    import cadquery as cq  # noqa: PLC0415 — the geometry extra is optional

    return cq


def _to_shape(result):
    cq = _cq()
    if isinstance(result, cq.Assembly):
        return result.toCompound()
    if isinstance(result, cq.Workplane):
        vals = [v for v in result.vals() if isinstance(v, cq.Shape)]
        if not vals:
            return None
        return vals[0] if len(vals) == 1 else cq.Compound.makeCompound(vals)
    return result if isinstance(result, cq.Shape) else None


def _envelope_shape(solids: Sequence[Mapping]):
    cq = _cq()
    parts = []
    for solid in solids:
        if solid["shape"] == "box":
            lo, hi = solid["min"], solid["max"]
            parts.append(cq.Solid.makeBox(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2],
                                          pnt=cq.Vector(*lo)))
        else:
            axis = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[solid["axis"]]
            parts.append(cq.Solid.makeCylinder(solid["radius"], solid["length"],
                                               pnt=cq.Vector(*solid["base"]),
                                               dir=cq.Vector(*axis)))
    shape = parts[0]
    for other in parts[1:]:
        shape = shape.fuse(other)
    return shape


def _cartridge_shape(geometry: Mapping):
    from ..geometry import _exec_cartridge, mode_sources  # noqa: PLC0415

    sources = mode_sources(dict(geometry.get("mode") or {}))
    script = next((src for engine, src in sources if engine == "cadquery"), None)
    if script is None:
        engines = ", ".join(e for e, _ in sources) or "none"
        return None, f"the mode has no CadQuery source to render (sources: {engines})"
    shapes = []
    for part in geometry.get("parts") or [None]:
        params = dict(geometry.get("parameters") or {})
        if part is not None:
            params["target_part"] = part
        try:
            result = _exec_cartridge(str(Path(geometry["dir"]) / script), params)
        except Exception as exc:  # a cartridge raising is a reason, never a crash
            return None, f"rendering part {part!r} raised {type(exc).__name__}: {exc}"
        shape = _to_shape(result)
        if shape is None:
            return None, f"part {part!r} rendered no CadQuery shape"
        shapes.append(shape)
    cq = _cq()
    return (shapes[0] if len(shapes) == 1 else cq.Compound.makeCompound(shapes)), None


def component_solid(resolved) -> tuple[object | None, str | None]:
    """(CadQuery shape in the component's model frame, None) or (None, why not)."""
    geometry = getattr(resolved, "geometry", None)
    if not geometry:
        if resolved.source_type == "cartridge":
            return None, "the resolver supplied no cartridge to render"
        return None, f"{resolved.label} declares no envelope"
    if geometry.get("kind") == "envelope":
        return _envelope_shape(geometry["solids"]), None
    if geometry.get("kind") == "cartridge":
        return _cartridge_shape(geometry)
    return None, f"unknown geometry kind {geometry.get('kind')!r}"


def _placed(shape, matrix: Matrix):
    cq = _cq()
    from OCP.gp import gp_Trsf  # noqa: PLC0415

    trsf = gp_Trsf()
    trsf.SetValues(*[float(matrix[r][c]) for r in range(3) for c in range(4)])
    return shape.moved(cq.Location(trsf))


def _boxes_overlap(a, b) -> bool:
    return (a.xmin < b.xmax and b.xmin < a.xmax and a.ymin < b.ymax and b.ymin < a.ymax
            and a.zmin < b.zmax and b.zmin < a.zmax)


def _key(t_a: Matrix, t_b: Matrix) -> tuple:
    rel = matmul(rigid_inverse(t_a), t_b)
    return tuple(round(v, _KEY_DIGITS) + 0.0 for row in rel[:3] for v in row)


def check_collisions(
    report,
    order: Sequence[str],
    poses: Sequence[tuple[str, Mapping[str, Matrix]]],
    allowed: Sequence[Mapping],
) -> CollisionResult:
    """Intersect every pair of solids at every pose; findings go into `report`.

    `order` is the components in document order; `poses` is (pose name, placements) with
    home first; `allowed` is the document's `allowed_overlaps`."""
    try:
        _cq()
    except Exception as exc:  # the extra is absent or its kernel will not load
        report._warn("collision", "--collision was requested but the geometry extra "
                     f"(CadQuery) is unavailable ({type(exc).__name__}): no intersection "
                     "was checked")
        return CollisionResult("unavailable")

    result = CollisionResult("checked")
    solids = {}
    for cid in order:
        resolved = report.components.get(cid)
        if resolved is None:
            continue
        shape, why = component_solid(resolved)
        if shape is None:
            result.unchecked[cid] = why
        else:
            solids[cid] = shape
    if result.unchecked:
        result.status = "partial"
        names = "; ".join(f"{c}: {w}" for c, w in result.unchecked.items())
        report._warn("collision-unchecked",
                     f"{len(result.unchecked)} of {len(order)} components have no solid and "
                     f"were not checked for interference — {names}")

    allowance = {frozenset((a["a"], a["b"])): a for a in allowed}
    ids = [c for c in order if c in solids]
    cache: dict[tuple, float] = {}
    worst: dict[frozenset, tuple[float, str]] = {}
    over: dict[frozenset, list[tuple[str, float]]] = {}
    for pose, placements in poses:
        placed = {c: _placed(solids[c], placements[c]) for c in ids if c in placements}
        boxes = {c: s.BoundingBox() for c, s in placed.items()}
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if a not in placed or b not in placed or not _boxes_overlap(boxes[a], boxes[b]):
                    continue
                key = (a, b, _key(placements[a], placements[b]))
                if key not in cache:
                    try:
                        cache[key] = placed[a].intersect(placed[b]).Volume()
                    except Exception:  # an OCCT failure is a finding, never a pass
                        cache[key] = float("inf")
                    result.booleans += 1
                volume = cache[key]
                pair = frozenset((a, b))
                if volume > worst.get(pair, (0.0, ""))[0]:
                    worst[pair] = (volume, pose)
                if volume > COLLISION_TOLERANCE_MM3:
                    over.setdefault(pair, []).append((pose, volume))

    total = len(poses)
    for pair, rows in over.items():
        a, b = sorted(pair, key=order.index)
        volume, pose = worst[pair]
        result.pairs[f"{a}|{b}"] = {"max_mm3": round(volume, 3), "pose": pose,
                                    "poses": len(rows)}
        declared = allowance.get(pair)
        if declared is not None and volume <= declared["max_mm3"]:
            continue
        if declared is not None:
            report._err("collision", f"{a} and {b} overlap by {volume:.2f} mm³ at {pose}, more "
                        f"than the {declared['max_mm3']:g} mm³ the document allows "
                        f"({declared['reason']})", f"{a}|{b}")
        else:
            report._err("collision", f"{a} and {b} overlap by up to {volume:.2f} mm³ (at "
                        f"{pose}; above {COLLISION_TOLERANCE_MM3:g} mm³ at {len(rows)} of "
                        f"{total} poses) and the document declares no allowed overlap for "
                        "them", f"{a}|{b}")
    for pair, declared in allowance.items():
        if pair not in over and all(c in solids for c in pair):
            report._warn("allowed-overlap-unused",
                         f"{declared['a']} and {declared['b']} are allowed {declared['max_mm3']:g}"
                         f" mm³ but never overlap above {COLLISION_TOLERANCE_MM3:g} mm³ at any "
                         "pose: remove the declaration or say why it stays",
                         f"{declared['a']}|{declared['b']}")
    return result
