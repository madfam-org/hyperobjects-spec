"""Cross-kernel parity: do a dual-engine cartridge's two sides agree?

`--render` (since #17) renders BOTH kernels of a dual-engine mode and judges each at
the house mesh bar — watertight, positive volume, no inverted body. That proves each
side is a solid. It does not prove they are the SAME solid, and a cartridge whose
OpenSCAD side quietly models a different part passes both halves of that bar while
handing two different objects to two different users.

Until now the comparison lived only outside this package: the platform's
`scripts/qa/verify_parity.py` and the P2 sweep harness. Neither runs in the commons'
own CI, so the property the commons most needs proven — the two kernels agree — was
the one property nothing on the merge path checked.

This module is that comparison, mirrored gate for gate from
`yantra4d/scripts/qa/verify_parity.py::_check_mesh_parity` so the keystone and the
platform cannot disagree about what "agree" means. The numbers are the platform's,
not new ones:

  1. AABB extents  — max per-axis delta > `tolerance` (0.001mm) FAILS, except in the
     warn band (below).
  2. Volume        — delta > max(tolerance*100, 2% of the larger volume) FAILS.
                     Checked only when BOTH sides are watertight.
  3. Hausdorff proxy — max surface divergence, both directions, via
                     `trimesh.nearest.on_surface`. Above max(tolerance, 0.5mm) it is
                     a WARN on a pair that already passed 1 and 2 — the platform logs
                     "Assuming tessellation noise" and still returns True — but it is
                     the *deciding* gate inside the warn band.

THE FACETING WARN TIER (G27, ruled 2026-09-05)
----------------------------------------------
Gate 1 used to be a bare fail on any delta over tolerance. That failed five commons
pairs — faircap-filter, gears (herringbone), glia-diagnostic (stethoscope),
julia-vase, spiral-planter (planter/saucer) — by 0.0028–0.0367mm. None is a shape
difference: an OpenSCAD `$fn` polygon is a chord approximation of the circle CadQuery
models analytically, so the two AABBs differ by the chord error and by nothing else.
The largest such delta in the full sweep is 0.036674mm; the smallest genuine
divergence is 0.516728mm (maze coaster). 0.05mm sits an order of magnitude clear of
both edges — a separator between two non-overlapping populations rather than a tuned
constant.

The band alone would be too weak: a real 0.04mm dimensional error is inside it. So
the tier is CONJUNCTIVE. A delta is downgraded from fail to warn only when it is
within the band AND the Hausdorff proxy passes, i.e. the surfaces lie within
max(tolerance, 0.5mm) of each other everywhere. Chord error satisfies both; a
dimensional error inside the band moves a surface and fails gate 3. Anything above
the band, any volume delta over 2%, or any Hausdorff failure still FAILS outright.

A proxy that could not be MEASURED is not a pass. None is the absence of evidence,
and the warn tier requires positive evidence that the surfaces coincide.

WHICH PAIRS ARE COMPARED
------------------------
Only a (mode, part, preset) that actually RENDERED on both engines. That is a
narrower and more honest rule than the platform's `classify_mode`, which decides
pairing from the manifest before anything runs: here the renders have already
happened, so a pair exists exactly when two meshes exist. A skipped OpenSCAD lane (no
binary) yields no pairs and is reported as such rather than as agreement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "AABB_WARN_BAND",
    "PARITY_TOLERANCE",
    "ParityCheck",
    "check_mesh_parity",
    "compare_meshes",
    "pair_renders",
    "parity_checks",
]

#: The platform's default AABB tolerance (verify_parity.check_mesh_parity).
PARITY_TOLERANCE = 0.001

#: The faceting band. See the module docstring — measured, not tuned.
AABB_WARN_BAND = 0.05

#: The platform's relative volume allowance.
VOLUME_REL = 0.02

#: The platform's Hausdorff floor: max(tolerance, 0.5mm).
HAUSDORFF_FLOOR = 0.5


@dataclass
class ParityCheck:
    """The verdict on ONE (mode, part, preset) compared across both kernels."""

    mode: str
    part: str
    preset: str | None = None
    #: False only for a genuine disagreement. A warn is `ok`.
    ok: bool = True
    #: True when gate 1 was inside the faceting band and the surfaces agreed.
    warn: bool = False
    reason: str = ""
    #: What each gate measured. Keys mirror verify_parity.check_mesh_parity_report.
    report: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok

    @property
    def target(self) -> str:
        if self.preset:
            return f"({self.mode}, {self.part}, preset '{self.preset}')"
        return f"({self.mode}, {self.part})"

    @property
    def summary(self) -> str:
        if not self.ok:
            return f"parity {self.target}: FAIL — {self.reason}"
        if self.warn:
            return f"parity {self.target}: warn (faceting) — {self.reason}"
        return f"parity {self.target}: ok — {self.reason}"


def _extents(mesh) -> list[float]:
    """A mesh's AABB extents as plain floats.

    Plain, because the platform formats a numpy ARRAY here (`[40.0, 40.0, 80.0]`) and
    a list of `np.float64` scalars prints as `[np.float64(40.0), ...]` under NumPy 2.
    The sweep reports and the platform's PR bodies carry the array form, and the whole
    point of mirroring the message shape is that a reader can diff the two.
    """
    return [float(x) for x in mesh.extents]


def _hausdorff_proxy(m1, m2) -> float | None:
    """Max surface divergence in both directions, or None if it cannot be had.

    verify_parity._hausdorff_proxy. None is not zero and must never be read as a
    pass — see the module docstring.
    """
    try:
        import numpy as np

        _, d_m1_to_m2, _ = m2.nearest.on_surface(m1.vertices)
        _, d_m2_to_m1, _ = m1.nearest.on_surface(m2.vertices)
        return float(max(np.max(d_m1_to_m2), np.max(d_m2_to_m1)))
    except Exception:
        # verify_parity swallows this too ("Falling back to AABB and Volume").
        return None


def compare_meshes(m1, m2, tolerance: float = PARITY_TOLERANCE) -> tuple[bool, bool, str, dict]:
    """The three gates, on two loaded trimesh meshes.

    Returns ``(agree, warn, reason, report)``. `m1` is the A side (OpenSCAD by
    convention, matching the platform's message shape), `m2` the B side.

    The "Bounding boxes differ by X mm (A: […], B: […])" and "Volumes differ by X mm^3
    (Y %)" wordings are load-bearing: the sweep harness, the platform's PR bodies and
    the P2 reports all parse them, so neither phrase changes here.
    """
    import numpy as np

    report: dict = {
        "aabb_delta_mm": None,
        "aabb_warn": False,
        "hausdorff_proxy_mm": None,
        "hausdorff_warn": False,
        "volume_delta_mm3": None,
    }

    dist_threshold = max(tolerance, HAUSDORFF_FLOOR)

    # --- gate 1: AABB extents -------------------------------------------------
    extents_diff = float(np.max(np.abs(np.asarray(m1.extents) - np.asarray(m2.extents))))
    report["aabb_delta_mm"] = extents_diff
    aabb_warn = False

    if extents_diff > tolerance:
        if extents_diff > AABB_WARN_BAND:
            # Above the band: a hard fail, and the surfaces are not consulted —
            # nothing gate 3 could say would rescue it, so do not pay for it.
            return (
                False,
                False,
                (
                    f"Bounding boxes differ by {extents_diff:.6f}mm "
                    f"(A: {_extents(m1)}, B: {_extents(m2)})"
                ),
                report,
            )
        # Inside the band: the surfaces decide. Gate 3, brought forward.
        max_divergence = _hausdorff_proxy(m1, m2)
        report["hausdorff_proxy_mm"] = max_divergence
        if max_divergence is None or max_divergence > dist_threshold:
            report["hausdorff_warn"] = max_divergence is not None
            unmeasured = (
                " (surface divergence could not be measured)" if max_divergence is None else ""
            )
            return (
                False,
                False,
                (
                    f"Bounding boxes differ by {extents_diff:.6f}mm "
                    f"(A: {_extents(m1)}, B: {_extents(m2)}) and the surfaces "
                    f"diverge too{unmeasured}"
                ),
                report,
            )
        aabb_warn = True
        report["aabb_warn"] = True

    # --- gate 2: volume -------------------------------------------------------
    if m1.is_watertight and m2.is_watertight:
        v1, v2 = float(m1.volume), float(m2.volume)
        vol_diff = abs(v1 - v2)
        biggest = max(v1, v2)
        rel = vol_diff / biggest if biggest > 0 else 0.0
        vol_threshold = max(tolerance * 100, biggest * VOLUME_REL)
        report["volume_delta_mm3"] = vol_diff
        if vol_diff > vol_threshold:
            return (
                False,
                False,
                f"Volumes differ by {vol_diff:.6f}mm^3 ({rel * 100:.4f}%)",
                report,
            )

    # --- gate 3: Hausdorff proxy ---------------------------------------------
    # Already measured when gate 1 warned — that path only reaches here having proved
    # the surfaces agree, so do not pay for the query twice.
    if report["hausdorff_proxy_mm"] is None:
        report["hausdorff_proxy_mm"] = _hausdorff_proxy(m1, m2)
    max_divergence = report["hausdorff_proxy_mm"] or 0.0

    if max_divergence > dist_threshold:
        # Warn only, exactly as the platform: AABB and volume already agreed, so this
        # is tessellation noise on a pair that passed.
        report["hausdorff_warn"] = True

    if aabb_warn:
        return (
            True,
            True,
            (
                f"Bounding boxes differ by {extents_diff:.6f}mm "
                f"(faceting warn, within {AABB_WARN_BAND}mm; surfaces agree to "
                f"{max_divergence:.6f}mm)."
            ),
            report,
        )
    return True, False, f"Meshes are identical within {max_divergence:.6f}mm tolerance.", report


def check_mesh_parity(
    mesh1_path: str, mesh2_path: str, tolerance: float = PARITY_TOLERANCE
) -> tuple[bool, bool, str, dict]:
    """`compare_meshes` on two STLs on disk. Loading failures are failures, not warns."""
    import trimesh

    report: dict = {
        "aabb_delta_mm": None,
        "aabb_warn": False,
        "hausdorff_proxy_mm": None,
        "hausdorff_warn": False,
        "volume_delta_mm3": None,
    }
    try:
        m1 = trimesh.load(mesh1_path, force="mesh")
        m2 = trimesh.load(mesh2_path, force="mesh")
    except Exception as exc:
        return False, False, f"could not load both meshes: {type(exc).__name__}: {exc}", report

    if not isinstance(m1, trimesh.Trimesh) or not isinstance(m2, trimesh.Trimesh):
        return False, False, "Exported files are not valid 3D polygon meshes.", report

    return compare_meshes(m1, m2, tolerance)


def pair_renders(renders) -> list[tuple[object, object]]:
    """The (openscad, cadquery) render pairs a parity pass can actually compare.

    A pair exists when the SAME (mode, part, preset) produced a judged mesh on BOTH
    engines — `stl_path` set, so the mesh survived the render. A skipped lane (no
    OpenSCAD binary) and a failed render both carry no path, and neither yields a
    pair: comparing against a mesh that was never produced is not evidence of
    agreement.

    Ordered by (mode, part, preset) so output is diffable across runs. A/OpenSCAD
    first, mirroring the platform's message shape.
    """
    by_key: dict[tuple, dict[str, object]] = {}
    for check in renders:
        path = getattr(check, "stl_path", None)
        if not path or not getattr(check, "ok", False):
            continue
        engine = getattr(check, "engine", None)
        if engine not in ("openscad", "cadquery"):
            continue
        key = (check.mode, check.part, getattr(check, "preset", None))
        by_key.setdefault(key, {})[engine] = check

    pairs = []
    for key in sorted(by_key, key=lambda k: (k[0], k[1], k[2] or "")):
        sides = by_key[key]
        if "openscad" in sides and "cadquery" in sides:
            pairs.append((sides["openscad"], sides["cadquery"]))
    return pairs


def parity_checks(renders, tolerance: float = PARITY_TOLERANCE) -> list[ParityCheck]:
    """Compare every dual-engine (mode, part, preset) that rendered on both sides."""
    out: list[ParityCheck] = []
    for scad_check, cq_check in pair_renders(renders):
        agree, warn, reason, report = check_mesh_parity(
            scad_check.stl_path, cq_check.stl_path, tolerance
        )
        out.append(
            ParityCheck(
                mode=scad_check.mode,
                part=scad_check.part,
                preset=getattr(scad_check, "preset", None),
                ok=agree,
                warn=warn,
                reason=reason,
                report=report,
            )
        )
    return out
