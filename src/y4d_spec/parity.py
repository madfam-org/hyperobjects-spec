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
  3. PLACEMENT + SHAPE — the surface comparison, split in two (G39, below).
                     `placement` is the offset between the two meshes' AABB centres;
                     `shape` is the Hausdorff proxy measured AFTER that offset is
                     removed. Shape divergence above max(tolerance, 0.5mm) FAILS. A
                     placement offset above 0.05mm is a note by default and a FAIL
                     only under `"placement": "strict"`.

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

SHAPE AFTER ALIGNMENT, PLACEMENT AS ITS OWN NUMBER (G39, ruled 2026-09-06)
-------------------------------------------------------------------------
Gate 3 used to be what the platform makes it: recorded, never failing on its own. On
the first full `--parity` sweep that let NINETEEN pairs through reporting
`ok - Meshes are identical within X mm tolerance` with X up to 65mm. "Identical within
65mm" is not a sentence anybody should read as agreement, and the pairs behind it were
not one problem but two:

  (a) a genuine SHAPE difference - `gears` `spur_gear` at 2.5-5.0mm was a trapezoid
      tooth on one kernel against a true involute on the other (since repaired);
  (b) a PLACEMENT offset - one kernel centres the part at the origin, the other anchors
      a corner or a face. `relief`'s 44.72mm is exactly sqrt(40^2 + 20^2), the
      half-diagonal of its plate; `soft-jaw`'s 9.525mm is 3/8 inch. The part is the
      same part, moved.

Both hid behind ONE number because the proxy samples raw vertices with no alignment,
so a rigid translation reads exactly like a deformation - and gate 1 cannot separate
them either, since translating a solid changes neither its extents nor its volume.
Extents and volume together cannot distinguish "same part, different origin" from
"different part". Only a measurement that removes the offset can.

So the measurement is split:

  placement = the vector between the two meshes' AABB centres, reported as
              `placement offset d=(dx,dy,dz) |d|=... mm`.
  shape     = the Hausdorff proxy with B translated by -d first, i.e. the two surfaces
              brought to a common origin. Same sampling as before.

and the two get different verdicts, because they mean different things to different
consumers. A slicer re-centres the part on the bed, so a placement offset costs a print
nothing; an ASSEMBLY or an animation places parts by their model origin, and there an
offset is the whole bug. A cartridge therefore OPTS IN: placement is a NOTE above
`PLACEMENT_NOTE_BAND` (0.05mm - the same faceting band, below which an offset is chord
error in the AABB rather than a decision) and a FAIL only when the manifest's parity
policy says `"placement": "strict"`.

Shape has no such excuse. Two surfaces that still diverge once they are sitting on top
of each other are two different objects, and that is a FAIL at the same
max(tolerance, 0.5mm) the proxy always used. The warn tier (G27) is unchanged in
meaning: an AABB delta inside the band is still downgraded only when the surfaces
agree - now measured after alignment, which is strictly more honest, since a pair
inside the band cannot be rescued by an offset it never had (an offset that large would
have moved the AABB out of the band).

The `ok` wording changes with it. "Meshes are identical within X mm tolerance" is
retired for any X above the tolerance in favour of "surfaces agree to X mm" - the
phrase the warn tier already used - because a line that says "identical" about a 65mm
gap misleads every reader of it, including the ones who wrote it.

THE PER-PART EXEMPTION (G38, ruled 2026-09-06)
----------------------------------------------
Two commons cartridges cannot pass this comparison without a design change that is a
RULING, not a repair:

  fasteners `bolt`  — OpenSCAD uses BOSL2's real helical thread, CadQuery a revolved
                      sawtooth ring stack, deliberately. The divergence is 0.902 x the
                      ISO thread depth on every preset; a real CadQuery helix takes
                      262 s to build and is still wrong.
  spiral-planter    — the CadQuery side has no spiral groove. Cutting one yields a
                      valid B-Rep whose tessellation carries 125 bodies / 116 boundary
                      edges, which the mesh bar rejects (six variants tried); and the
                      saucer's 0.0566mm is CadQuery's `$fn`-equivalent faceting, which
                      only a ~quadratic-cost refinement clears.

The alternative to an exemption is a permanently red nightly, and a gate that is always
red is a gate nobody reads. So a manifest may declare, per part, that this comparison
does not apply — but only OUT LOUD:

  * an exemption or a widened tolerance WITHOUT a non-empty `reason` is a CONFORMANCE
    FAILURE, caught by `y4d-spec check` with no `--render` at all. Silence is the thing
    being outlawed, so the reason is the whole mechanism and not a courtesy field.
  * `enabled: false` skips the comparison for that part and is reported as
    `parity (mode, part): exempt — <reason>`, a NOTE. It never vanishes from output,
    and it is counted separately in the summary (`exempt=E`) so a run with three
    exemptions cannot be read as a run with none.
  * a widened `tolerance` applies to the AABB gate ONLY, exactly as
    `--parity-tolerance` does, and the effective value is printed in the line.
    Widening one gate must not silently move the volume allowance or the warn band.

An exemption is VISIBLE DEBT, not an absolution: it must name the kernel idiom that
differs (not "known issue"), and it is expected to be reviewed whenever either kernel
changes — a helix OCC can sweep cheaply, or a BOSL2 rewrite, retires it.

WHERE IT IS DECLARED
--------------------
Base, applying to every part::

    "verification": {"stages": {"geometry": {"checks": {"parity": {
        "enabled": true, "tolerance": 0.05, "placement": "strict",
        "reason": "..."}}}}}

`placement` is `"free"` (the default - an offset above the band is a note) or
`"strict"` (an offset above the band is a FAIL). It needs no `reason`: strict is a
TIGHTENING, and a tightening owes no explanation, exactly like a tolerance below the
default.

Per (mode, part), mirroring how the other geometry checks are overridden::

    "verification": {"mode_overrides": {"<mode>": {"part_overrides": {"<part>": {
        "geometry.parity": {"enabled": false, "reason": "..."}}}}}}

The part override WINS WHOLE — it replaces the base object rather than merging into it,
so reading one block tells a reader the entire policy for that part. Absent both, the
default is `enabled: true` at the CLI tolerance.

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
    "PLACEMENT_NOTE_BAND",
    "PLACEMENT_MODES",
    "PARITY_CHECK_KEY",
    "PARITY_OVERRIDE_KEY",
    "PARITY_TOLERANCE",
    "ParityCheck",
    "ParityPolicy",
    "check_mesh_parity",
    "compare_meshes",
    "placement_offset",
    "pair_renders",
    "parity_checks",
    "resolve_parity_policy",
]

#: The platform's default AABB tolerance (verify_parity.check_mesh_parity).
PARITY_TOLERANCE = 0.001

#: The faceting band. See the module docstring — measured, not tuned.
AABB_WARN_BAND = 0.05

#: The platform's relative volume allowance.
VOLUME_REL = 0.02

#: The shape floor: max(tolerance, 0.5mm). The platform's Hausdorff number, now a
#: FAIL rather than a note, and measured after alignment (G39).
HAUSDORFF_FLOOR = 0.5

#: Above this, a placement offset is said out loud. The same 0.05mm as the faceting
#: band, and for the same reason: below it an AABB-centre difference is chord error in
#: the two bounding boxes, not a decision anybody made (G39).
PLACEMENT_NOTE_BAND = 0.05

#: What a manifest may say about placement. "free" (default): an offset above the band
#: is a note. "strict": it is a failure — for assemblies and animations, which place
#: parts by their model origin.
PLACEMENT_MODES = ("free", "strict")

#: Where the base policy lives: verification.stages.geometry.checks.<this>.
PARITY_CHECK_KEY = "parity"

#: Where a per-part policy lives:
#: verification.mode_overrides.<mode>.part_overrides.<part>.<this>.
PARITY_OVERRIDE_KEY = "geometry.parity"


@dataclass
class ParityCheck:
    """The verdict on ONE (mode, part, preset) compared across both kernels."""

    mode: str
    part: str
    preset: str | None = None
    #: False only for a genuine disagreement. A warn is `ok`, and so is an exemption.
    ok: bool = True
    #: True when gate 1 was inside the faceting band and the surfaces agreed.
    warn: bool = False
    #: True when the two meshes sit at different origins by more than
    #: PLACEMENT_NOTE_BAND and the manifest left placement "free" (G39). A NOTE: the
    #: pair still counts as agreement, because a slicer re-centres the part anyway —
    #: but the offset is printed on every run, never folded into the shape number.
    placement_note: bool = False
    #: True when the manifest declared this part exempt (G38). The comparison did not
    #: run; `reason` carries the manifest's own words for why.
    exempt: bool = False
    #: The AABB tolerance this pair was actually judged at, when the manifest widened
    #: it. None means the run-wide tolerance, which the line does not need to repeat.
    effective_tolerance: float | None = None
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
    def _tolerance_note(self) -> str:
        """`" (tolerance 0.06mm)"` when the manifest widened it, else empty.

        Printed because a pair that passed at a widened bar did not pass at the bar
        every other pair was held to, and a line that does not say so is a line that
        overstates what was proven.
        """
        if self.effective_tolerance is None:
            return ""
        return f" (tolerance {self.effective_tolerance:g}mm)"

    @property
    def summary(self) -> str:
        if self.exempt:
            # Never silent: an exemption prints on every run, exactly like a warn.
            return f"parity {self.target}: exempt — {self.reason}"
        if not self.ok:
            return f"parity {self.target}: FAIL{self._tolerance_note} — {self.reason}"
        if self.warn:
            return f"parity {self.target}: warn (faceting){self._tolerance_note} — {self.reason}"
        if self.placement_note:
            # The shape agreed; the part sits somewhere else. Its own tier, so a reader
            # scanning for "ok" does not have to parse the reason to notice (G39).
            return f"parity {self.target}: ok (placement){self._tolerance_note} — {self.reason}"
        return f"parity {self.target}: ok{self._tolerance_note} — {self.reason}"


def _extents(mesh) -> list[float]:
    """A mesh's AABB extents as plain floats.

    Plain, because the platform formats a numpy ARRAY here (`[40.0, 40.0, 80.0]`) and
    a list of `np.float64` scalars prints as `[np.float64(40.0), ...]` under NumPy 2.
    The sweep reports and the platform's PR bodies carry the array form, and the whole
    point of mirroring the message shape is that a reader can diff the two.
    """
    return [float(x) for x in mesh.extents]


def placement_offset(m1, m2) -> tuple[float, float, float]:
    """The vector from m1's AABB centre to m2's — how far B sits from A (G39).

    AABB centres rather than centroids on purpose. A centroid is a volume-weighted
    quantity, so a genuine shape difference moves it and the "placement" number would
    absorb part of the shape error it exists to separate out. The AABB centre depends
    only on the extremes of the surface, which gate 1 has already compared: when the
    extents agree (the case this exists for), a centre difference is a pure rigid
    translation and nothing else.
    """
    import numpy as np

    c1 = (np.asarray(m1.bounds[0], dtype=float) + np.asarray(m1.bounds[1], dtype=float)) / 2.0
    c2 = (np.asarray(m2.bounds[0], dtype=float) + np.asarray(m2.bounds[1], dtype=float)) / 2.0
    delta = c2 - c1
    return (float(delta[0]), float(delta[1]), float(delta[2]))


def _hausdorff_proxy(m1, m2, offset: tuple[float, float, float] | None = None) -> float | None:
    """Max surface divergence in both directions, or None if it cannot be had.

    verify_parity._hausdorff_proxy, plus alignment: `offset` is the placement vector
    from `placement_offset`, and m2's sample points are moved by -offset (and m1's by
    +offset) before the query, so the number that comes back is SHAPE divergence with
    the rigid translation taken out. None is not zero and must never be read as a
    pass — see the module docstring.

    The meshes themselves are never mutated; only the sampled vertex arrays are
    shifted. `nearest.on_surface` is a query against m1/m2's own trees, so shifting
    the query points one way is exactly equivalent to shifting the other mesh the
    other way, at no copy cost.
    """
    try:
        import numpy as np

        if offset is None:
            v1, v2 = m1.vertices, m2.vertices
        else:
            shift = np.asarray(offset, dtype=float)
            # m1's points into m2's frame (+shift); m2's into m1's frame (-shift).
            v1 = np.asarray(m1.vertices, dtype=float) + shift
            v2 = np.asarray(m2.vertices, dtype=float) - shift
        _, d_m1_to_m2, _ = m2.nearest.on_surface(v1)
        _, d_m2_to_m1, _ = m1.nearest.on_surface(v2)
        return float(max(np.max(d_m1_to_m2), np.max(d_m2_to_m1)))
    except Exception:
        # verify_parity swallows this too ("Falling back to AABB and Volume").
        return None


def _offset_note(offset: tuple[float, float, float], magnitude: float) -> str:
    """`placement offset d=(dx,dy,dz) |d|=X mm` — the G39 wording, one place."""
    dx, dy, dz = offset
    return f"placement offset d=({dx:.6f}, {dy:.6f}, {dz:.6f}) |d|={magnitude:.6f}mm"


def compare_meshes(
    m1,
    m2,
    tolerance: float = PARITY_TOLERANCE,
    *,
    placement: str = "free",
) -> tuple[bool, bool, str, dict]:
    """The gates, on two loaded trimesh meshes.

    Returns ``(agree, warn, reason, report)``. `m1` is the A side (OpenSCAD by
    convention, matching the platform's message shape), `m2` the B side.
    `placement` is the manifest's policy for gate 3a — ``"free"`` (an offset above
    PLACEMENT_NOTE_BAND is a note) or ``"strict"`` (it is a failure). See G39 in the
    module docstring.

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
        # G39. `hausdorff_proxy_mm` keeps its name and now carries the ALIGNED number,
        # because every consumer of it wanted shape and was being handed shape+offset.
        "placement_offset_mm": None,
        "placement_delta_mm": None,
        "placement_note": False,
        "placement_mode": placement,
    }

    dist_threshold = max(tolerance, HAUSDORFF_FLOOR)
    strict_placement = placement == "strict"

    # --- gate 3a: placement, measured first so gate 3b can subtract it -------
    # Cheap (six numbers off two bounding boxes) and needed by every path that
    # consults the surfaces, so it is taken once, up front, unconditionally.
    offset = placement_offset(m1, m2)
    offset_mm = float(np.linalg.norm(np.asarray(offset, dtype=float)))
    report["placement_offset_mm"] = list(offset)
    report["placement_delta_mm"] = offset_mm
    offset_over_band = offset_mm > PLACEMENT_NOTE_BAND
    offset_note = _offset_note(offset, offset_mm)

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
        # Inside the band: the surfaces decide. Gate 3b, brought forward.
        max_divergence = _hausdorff_proxy(m1, m2, offset)
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

    # --- gate 3b: shape, after alignment -------------------------------------
    # Already measured when gate 1 warned — that path only reaches here having proved
    # the surfaces agree, so do not pay for the query twice.
    if report["hausdorff_proxy_mm"] is None:
        report["hausdorff_proxy_mm"] = _hausdorff_proxy(m1, m2, offset)
    max_divergence = report["hausdorff_proxy_mm"]

    if max_divergence is None:
        # Unmeasurable is not a pass here either: this is now the deciding gate, and
        # None is the absence of evidence for the property it is supposed to prove.
        report["hausdorff_warn"] = True
        return (
            False,
            False,
            (
                "FAIL — surface divergence could not be measured, so the two kernels "
                f"were never shown to model the same shape ({offset_note})"
            ),
            report,
        )

    if max_divergence > dist_threshold:
        # G39: a shape difference the alignment did NOT explain. This used to be a
        # note; nineteen pairs rode through on it, one of them at 65mm.
        report["hausdorff_warn"] = True
        return (
            False,
            False,
            (
                f"surfaces diverge by {max_divergence:.6f}mm after alignment "
                f"({offset_note})"
            ),
            report,
        )

    # The shape agrees. What remains is where the part sits.
    if offset_over_band:
        if strict_placement:
            return (
                False,
                False,
                (
                    f"the two kernels place this part differently — {offset_note}, "
                    f"above {PLACEMENT_NOTE_BAND}mm, and the manifest declares "
                    f'placement "strict" (surfaces agree to {max_divergence:.6f}mm)'
                ),
                report,
            )
        report["placement_note"] = True

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

    if report["placement_note"]:
        # Shape agreed; the part sits somewhere else. The offset leads, because it is
        # the finding — a line that opened with "surfaces agree" and buried a 44.72mm
        # origin difference after a semicolon would repeat the mistake G39 fixes.
        return (
            True,
            False,
            (
                f"{offset_note} — the same shape at a different origin "
                f"(surfaces agree to {max_divergence:.6f}mm after alignment)"
            ),
            report,
        )

    # "identical within X" survives only where it is TRUE: a divergence the tolerance
    # itself covers. Above that it is the exact sentence that made a 65mm gap read as
    # agreement, so the warn tier's honest wording takes over (G39).
    if max_divergence <= tolerance:
        return True, False, f"Meshes are identical within {max_divergence:.6f}mm tolerance.", report
    return True, False, f"surfaces agree to {max_divergence:.6f}mm.", report


def check_mesh_parity(
    mesh1_path: str,
    mesh2_path: str,
    tolerance: float = PARITY_TOLERANCE,
    *,
    placement: str = "free",
) -> tuple[bool, bool, str, dict]:
    """`compare_meshes` on two STLs on disk. Loading failures are failures, not warns."""
    import trimesh

    report: dict = {
        "aabb_delta_mm": None,
        "aabb_warn": False,
        "hausdorff_proxy_mm": None,
        "hausdorff_warn": False,
        "volume_delta_mm3": None,
        "placement_offset_mm": None,
        "placement_delta_mm": None,
        "placement_note": False,
        "placement_mode": placement,
    }
    try:
        m1 = trimesh.load(mesh1_path, force="mesh")
        m2 = trimesh.load(mesh2_path, force="mesh")
    except Exception as exc:
        return False, False, f"could not load both meshes: {type(exc).__name__}: {exc}", report

    if not isinstance(m1, trimesh.Trimesh) or not isinstance(m2, trimesh.Trimesh):
        return False, False, "Exported files are not valid 3D polygon meshes.", report

    return compare_meshes(m1, m2, tolerance, placement=placement)


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


@dataclass(frozen=True)
class ParityPolicy:
    """What a manifest says about comparing ONE part's two kernels (G38).

    `enabled=True` with `tolerance=None` is the default every part gets when the
    manifest is silent, so a cartridge that declares nothing behaves exactly as it did
    before this existed.
    """

    enabled: bool = True
    #: A manifest-declared AABB tolerance in mm, or None for the run-wide one.
    tolerance: float | None = None
    #: "free" (default) or "strict" — whether a placement offset above the band is a
    #: note or a failure (G39). Strict is a TIGHTENING and needs no `reason`.
    placement: str = "free"
    #: The manifest's own words. Required whenever this policy departs from the
    #: default — enforced as a conformance rule, not here (rules.verification_rules).
    reason: str = ""
    #: Where this came from: "default", "base", or "mode_overrides.<mode>".
    source: str = "default"


def _policy_from(block: object, source: str) -> ParityPolicy | None:
    """One declared parity object → a ParityPolicy, or None if it is not one.

    Lenient about shape on purpose: a malformed block is the schema's problem and the
    conformance rules', and reporting it twice in two vocabularies helps nobody. What
    this must never do is read a malformed block as PERMISSION — an unparseable
    `enabled` stays True, so a typo cannot silently switch the gate off.
    """
    if not isinstance(block, dict):
        return None
    tolerance = block.get("tolerance")
    numeric = isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool)
    reason = block.get("reason")
    placement = block.get("placement")
    # An unrecognised value falls back to "free", the default — never to "strict". A
    # typo must not turn a note into a failure any more than it may turn the gate off.
    return ParityPolicy(
        enabled=block.get("enabled") is not False,
        tolerance=float(tolerance) if numeric else None,
        placement=placement if placement in PLACEMENT_MODES else "free",
        reason=reason if isinstance(reason, str) else "",
        source=source,
    )


def resolve_parity_policy(doc: object, mode: str, part: str) -> ParityPolicy:
    """The policy in force for one (mode, part), mirroring the geometry overrides.

    Precedence, most specific first:

      1. `verification.mode_overrides.<mode>.part_overrides.<part>["geometry.parity"]`
      2. `verification.stages.geometry.checks.parity`
      3. the default — enabled, run-wide tolerance

    The part override replaces the base object WHOLE rather than merging field by
    field. Merging would let a base `reason` justify an override that never said
    anything, and the reason is the entire mechanism: one block must carry the whole
    policy for that part, so a reader who finds it need not go looking for a second.
    """
    if not isinstance(doc, dict):
        return ParityPolicy()
    verification = doc.get("verification")
    if not isinstance(verification, dict):
        return ParityPolicy()

    mode_overrides = verification.get("mode_overrides")
    if isinstance(mode_overrides, dict):
        entry = mode_overrides.get(mode)
        if isinstance(entry, dict):
            part_overrides = entry.get("part_overrides")
            if isinstance(part_overrides, dict):
                for_part = part_overrides.get(part)
                if isinstance(for_part, dict):
                    declared = _policy_from(
                        for_part.get(PARITY_OVERRIDE_KEY), f"mode_overrides.{mode}"
                    )
                    if declared is not None:
                        return declared

    stages = verification.get("stages")
    if isinstance(stages, dict):
        geometry = stages.get("geometry")
        if isinstance(geometry, dict):
            checks = geometry.get("checks")
            if isinstance(checks, dict):
                declared = _policy_from(checks.get(PARITY_CHECK_KEY), "base")
                if declared is not None:
                    return declared

    return ParityPolicy()


def parity_checks(
    renders,
    tolerance: float = PARITY_TOLERANCE,
    doc: object = None,
    *,
    tolerance_is_explicit: bool = False,
) -> list[ParityCheck]:
    """Compare every dual-engine (mode, part, preset) that rendered on both sides.

    `doc` is the parsed manifest, consulted only for its per-part parity policy (G38).
    Omitted, every pair is compared at `tolerance` — the behaviour before exemptions
    existed.

    `tolerance_is_explicit` says the caller NAMED that tolerance (`--parity-tolerance`)
    rather than inheriting the package default. When it did, the command line wins over
    a manifest's widened tolerance: an operator asking to see the cartridge at 0.001mm
    must actually see it at 0.001mm, or the flag cannot answer the question it exists
    for. An exemption is not a tolerance and is NOT overridden by it — `enabled: false`
    says the comparison is meaningless for that part, which no number answers; run
    without the manifest (or fix it) to see that pair compared.
    """
    out: list[ParityCheck] = []
    for scad_check, cq_check in pair_renders(renders):
        policy = resolve_parity_policy(doc, scad_check.mode, scad_check.part)
        preset = getattr(scad_check, "preset", None)

        if not policy.enabled:
            # The comparison does not run — but the pair is still REPORTED, and still
            # counted. That is the difference between an exemption and a deletion.
            out.append(
                ParityCheck(
                    mode=scad_check.mode,
                    part=scad_check.part,
                    preset=preset,
                    ok=True,
                    exempt=True,
                    reason=policy.reason or "no reason declared",
                )
            )
            continue

        effective = tolerance
        declared_tolerance = None
        if policy.tolerance is not None and not tolerance_is_explicit:
            effective = policy.tolerance
            declared_tolerance = policy.tolerance
        agree, warn, reason, report = check_mesh_parity(
            scad_check.stl_path,
            cq_check.stl_path,
            effective,
            placement=policy.placement,
        )
        out.append(
            ParityCheck(
                mode=scad_check.mode,
                part=scad_check.part,
                preset=preset,
                ok=agree,
                warn=warn,
                placement_note=bool(report.get("placement_note")),
                effective_tolerance=declared_tolerance,
                reason=reason,
                report=report,
            )
        )
    return out
