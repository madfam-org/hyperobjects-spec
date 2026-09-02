"""Printability MEASUREMENTS on a rendered mesh — notes only, never failures.

A cartridge can be perfectly conformant, render a watertight positive-volume solid,
and still be unprintable on the FDM machine most of the commons is aimed at: walls
thinner than the nozzle can lay down, overhangs that need supports nobody warned the
user about, a part that does not fit the bed.

These are NOT conformance rules and this module deliberately cannot fail a cartridge.
Every threshold here is PROVISIONAL: picked from FDM practice, then calibrated against
a 36-cartridge slice of the yantra4d commons (217 renders, 101 of them presets). None
has been through a FULL-commons false-positive analysis, which is the precondition this
program sets before any rule is allowed to block. Until that is written down, they land
as measurements and every note names the number it measured so a reader can judge the
threshold rather than trust it.

Calibration outcome on that slice, after tuning — the story behind each number is on
the constant it tuned:

    thin_wall      0/35 cartridges   (was: nearly all at p5, then 3 at p25 — all three
                                      shipped and printed, so the statistic was moved
                                      to the median; see THIN_WALL_PERCENTILE. The one
                                      finding it keeps in the test fixtures is TRUE and
                                      marginal: sew-on-snap's 9mm 'bodysuit_placket'
                                      preset webbing at 0.76mm. Left standing — a
                                      true-but-marginal measurement is what a note is
                                      for, and hiding it by moving the bar to 0.7mm
                                      would be tuning to the answer, not to the data.)
    overhang       0/35 cartridges   (was: 12/35 = 38%, a flood, because a part's flat
                                      BED-CONTACT face counted as overhang; see
                                      BED_FACE_COS)
    build_volume   4/35 cartridges   (11% — all genuine: corset-busk is a 300mm busk,
                                      drawer-divider's cutlery_tray preset is 400mm.
                                      Untuned; it was right the first time.)

The house doctrine this follows is recorded in rules.py: a rule that flags healthy
cartridges is not a strict rule, it is a wrong one (the killed `render_mode`
uniqueness rule flagged 29 healthy cartridges). A note costs a line of output; a
premature failure costs the commons its green build and teaches contributors to
ignore the runner.

Build direction is assumed +Z: the cartridges are authored with the print bed at
Z=0, which is also what the platform's own slicing preview assumes. A part the user
reorients on their own bed will have different overhangs, which is a second reason
the overhang measurement is a note.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

__all__ = [
    "PrintabilityNote",
    "PrintabilityDependencyWarning",
    "THIN_WALL_MM",
    "THIN_WALL_PERCENTILE",
    "OVERHANG_ANGLE_DEG",
    "OVERHANG_AREA_FRACTION",
    "BED_FACE_COS",
    "BUILD_VOLUME_MM",
    "THICKNESS_SAMPLES",
    "thin_wall_note",
    "overhang_note",
    "build_volume_note",
    "printability_notes",
]

# ── provisional thresholds ───────────────────────────────────────────────────
# Two perimeters of a 0.4mm nozzle. Below this an FDM slicer either drops the wall
# entirely or lays a single under-extruded bead.
THIN_WALL_MM = 0.8

# Which percentile of the sampled local thickness is compared against THIN_WALL_MM.
#
# CALIBRATION — tuned TWICE, both times because the low percentiles measure edges
# rather than walls, and both times against cartridges known to print correctly.
#
# trimesh.proximity.thickness casts a ray along the inward surface normal, so a
# sample landing near any convex edge or corner reports the short distance to the
# ADJACENT face, not the wall. Every part therefore has a low-percentile tail that
# says nothing about its walls.
#
#   * p5 (the value first proposed) is a pure edge detector: a solid 20mm cube
#     measures p5 = 0.49mm and a 3mm plate p5 = 0.18mm. Both would be flagged and
#     neither is thin. Over the calibration slice it flagged nearly everything.
#   * p25 cut that to 3 of 32 cartridges (9%) — under the >20% flood bar, but the
#     three were aerator-cache, garter-clip and SEW-ON-SNAP: all shipped, printed,
#     correct. Their measurements clustered at 0.60–0.78mm, just under the bar,
#     which is the edge-poisoning signature and not a wall finding. Under-flooding
#     is not the same as being right; a rule that flags a printed part is wrong.
#   * p50 (the shipped value) separates cleanly, because a genuinely thin part is
#     thin nearly EVERYWHERE while an edge tail is a minority of samples: the 0.4mm
#     shelled box measures 0.40mm flat across p5/p25/p50, while sew-on-snap's stud
#     rises 0.12 -> 0.58 -> 1.24 and thimble's 0.48 -> 1.57 -> 1.59. The median
#     silences all three healthy cartridges and still catches the 0.4mm wall.
#
# At p50 the rule finds NOTHING in the 35-cartridge slice (0%). That is honest, not
# broken — it still fires at 0.40mm on the synthetic 0.4mm-shelled fixture, and the
# commons genuinely has no part that is thin at its median. But it is also the
# rule's known weakness: the median cannot see a part that is thin in ONE PLACE and
# chunky elsewhere, which is the failure a printer actually hits. Only the
# ray-validity fix below recovers that, and until then this rule is a floor check,
# not a thin-spot check. Do not promote it to a failure on the strength of 0%.
#
# Still provisional. The right fix is to reject samples whose ray exits through a
# neighbouring face rather than the opposite wall, which would make the low
# percentiles meaningful again and catch a part that is thin only in one spot. That
# is more mesh work than a note is worth today, and it is the main reason this
# stays a note.
THIN_WALL_PERCENTILE = 50

# Faces steeper than this from vertical are unsupported overhang. 45° is the FDM
# rule of thumb — each layer can bridge about half its own width to the one below.
OVERHANG_ANGLE_DEG = 45.0

# Fraction of total surface area in overhang before it is worth saying anything.
OVERHANG_AREA_FRACTION = 0.25

# A downward normal within this of straight-down (normal.z <= -BED_FACE_COS) is the
# part's BED-CONTACT face, not an overhang.
#
# CALIBRATION: without this exclusion the rule flagged 3 of the first 10 cartridges in
# the calibration slice — sew-on-snap among them, which is a correct, shipped, PRINTED
# cartridge whose parts are flat discs. Measured, every one of those 32% "overhang"
# areas was the flat bottom face RESTING ON THE BED, which needs no support by
# definition. A rule that flags a printed part for having a bottom is not strict, it is
# wrong (the doctrine rules.py records for the killed render_mode rule).
#
# Excluding bed-flat faces takes sew-on-snap from 32% to 0.0% and thimble from 12% to
# 7%, while a genuinely downward-facing cone stays at 52% and a sphere's unsupported
# lower quarter stays at 15% — so it removes the false positives without blunting the
# signal. It is an approximation: a flat face floating in mid-air (a bridge) is
# excluded too, and bridges DO need support. Catching those needs a per-face height
# check against what is below it, which is more mesh work than a note is worth today.
# That tradeoff is deliberate and it is why the measurement stays a note.
BED_FACE_COS = 0.999

# A common consumer bed/gantry envelope (Prusa MK-series, Ender 3 class is 220–256).
BUILD_VOLUME_MM = 256.0

# Cap on surface samples for the thickness measurement. Thickness is a ray cast per
# sample, so cost is linear: 400 samples measures in well under 2s on meshes up to
# the ~100k faces the commons produces, and the percentile is stable at that count
# (the statistic moves by <0.05mm between 400 and 1600 samples on the fixtures).
THICKNESS_SAMPLES = 400


class PrintabilityDependencyWarning(UserWarning):
    """A printability measurement was skipped because a PACKAGE is missing.

    Not a failure, deliberately. The module contract above is that printability
    measures and never blocks — `y4d-spec check --render` must not turn a conformant
    cartridge red because the machine running it is short an optional package — so a
    missing dependency cannot raise here. But it must not be SILENT either: without
    this warning a missing package is indistinguishable from a mesh that had nothing
    to say, and the difference matters enormously. "No thin walls" is a measurement.
    "The thickness measurement never ran" is a hole where a measurement should be, and
    a reader who cannot tell the two apart will read the hole as the good news.

    This is exactly how the `rtree` gap hid: trimesh's default `max_sphere` thickness
    reaches for `rtree` through `mesh.ray`, the `[geometry]` extra did not declare it,
    and the broad `except Exception` below turned the ModuleNotFoundError into the same
    `None` a featureless mesh returns. Two tests asserting the note FIRES went green
    everywhere the geometry lane was skipped, and said nothing anywhere else.
    """


# Missing-package reports already made, keyed by (rule, package). The report is
# once-per-process: a cartridge measures every (mode, part, preset), so a 40-render
# cartridge would otherwise bury the one line that matters under forty copies of it.
_REPORTED_MISSING: set[tuple[str, str]] = set()


def _report_missing_dependency(rule: str, exc: ImportError) -> None:
    """Warn ONCE that `rule` was skipped for a missing package, naming the package."""
    package = (getattr(exc, "name", None) or "").split(".")[0]
    if not package:
        package = "an optional package"
    if (rule, package) in _REPORTED_MISSING:
        return
    _REPORTED_MISSING.add((rule, package))
    warnings.warn(
        f"printability: the {rule} measurement was SKIPPED because the package "
        f"{package!r} is not installed — this is a missing dependency, not a mesh "
        f"with nothing to report. Install the geometry extra to measure it: "
        f'pip install "hyperobjects-spec[geometry]"',
        PrintabilityDependencyWarning,
        stacklevel=3,
    )


@dataclass
class PrintabilityNote:
    """One printability observation about one rendered mesh.

    Carries the measured number, not just the verdict — a reader has to be able to
    argue with a provisional threshold, and that needs the measurement.
    """

    rule: str
    message: str
    measured: float

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


def _prefix(mode: str, part: str, preset: str | None) -> str:
    """Where the note came from, in the same shape RenderCheck.summary uses."""
    if preset:
        return f"({mode}, {part}, preset '{preset}')"
    return f"({mode}, {part})"


def thin_wall_note(mesh, *, mode: str, part: str, preset: str | None = None):
    """Local wall thickness: note when the part is thinner than two nozzle widths.

    Samples points on the surface and casts a ray inward along the local normal
    (trimesh.proximity.thickness) — the distance to the opposite wall. The sample
    count is capped at THICKNESS_SAMPLES so a large mesh still measures in under two
    seconds.

    THRESHOLD IS PROVISIONAL, pending full-commons calibration: THIN_WALL_MM (0.8mm,
    two 0.4mm perimeters) at the THIN_WALL_PERCENTILE'th percentile. See
    THIN_WALL_PERCENTILE for why the percentile is the MEDIAN and not the 5th
    originally proposed: the low percentiles measure convex edges rather than walls,
    and flagged three cartridges that print correctly today.

    Returns None when nothing is worth saying, or when the measurement cannot be
    made (degenerate mesh, a ray that never lands) — an unmeasurable part gets
    silence, not a guess. A missing PACKAGE is not that case: it also returns None,
    because this module never blocks, but it says so first through
    PrintabilityDependencyWarning. `max_sphere` thickness needs `rtree` (trimesh's
    ray backend builds its bounds tree with it), which is why the [geometry] extra
    declares it.
    """
    try:
        import numpy as np
        import trimesh
    except ImportError as exc:
        _report_missing_dependency("thin_wall", exc)
        return None
    except Exception:
        return None

    try:
        if mesh.faces.shape[0] == 0 or float(mesh.area) <= 0:
            return None
        n = min(THICKNESS_SAMPLES, max(64, mesh.faces.shape[0]))
        points, face_index = trimesh.sample.sample_surface(mesh, n)
        thickness = trimesh.proximity.thickness(
            mesh=mesh,
            points=points,
            exterior=False,
            normals=mesh.face_normals[face_index],
        )
        thickness = np.asarray(thickness, dtype=float)
        # A ray that escapes the solid returns inf/nan; a sample exactly on an edge
        # returns 0. Neither is a wall measurement, so neither votes.
        thickness = thickness[np.isfinite(thickness) & (thickness > 0)]
        if thickness.size < 16:
            return None
        measured = float(np.percentile(thickness, THIN_WALL_PERCENTILE))
    except ImportError as exc:
        # trimesh reaches for rtree lazily, from inside proximity.thickness — so the
        # missing-package case surfaces HERE, not at the import block above.
        _report_missing_dependency("thin_wall", exc)
        return None
    except Exception:
        return None

    if measured >= THIN_WALL_MM:
        return None

    return PrintabilityNote(
        rule="thin_wall",
        measured=measured,
        message=(
            f"{_prefix(mode, part, preset)}: thin walls — median local thickness is "
            f"{measured:.2f}mm (over {THICKNESS_SAMPLES} surface samples), below "
            f"{THIN_WALL_MM}mm (two 0.4mm perimeters). May print under-extruded or not "
            f"at all on an FDM machine. Threshold is provisional."
        ),
    )


def overhang_note(mesh, *, mode: str, part: str, preset: str | None = None):
    """Downward-facing area: note when a large fraction may need supports.

    Measures the share of total surface area whose face normal points downward by
    more than OVERHANG_ANGLE_DEG from vertical, i.e. `normal.z < -cos(45°)` — the
    standard FDM support test against a +Z build direction — EXCLUDING faces that
    point straight down, which are the part's bed contact and need no support. See
    BED_FACE_COS for the calibration story behind that exclusion; without it the rule
    flagged correct printed cartridges for having a bottom.

    Phrased as "may need supports" and never as a failure: the user can reorient the
    part on their own bed, which changes the answer entirely.

    THRESHOLD IS PROVISIONAL, pending full-commons calibration: OVERHANG_AREA_FRACTION
    (25%) at OVERHANG_ANGLE_DEG (45°), bed faces excluded at BED_FACE_COS.
    """
    try:
        import numpy as np
    except ImportError as exc:
        _report_missing_dependency("overhang", exc)
        return None
    except Exception:
        return None

    try:
        areas = np.asarray(mesh.area_faces, dtype=float)
        total = float(areas.sum())
        if total <= 0:
            return None
        normals = np.asarray(mesh.face_normals, dtype=float)
        if normals.shape[0] != areas.shape[0]:
            return None
        limit = -np.cos(np.radians(OVERHANG_ANGLE_DEG))
        down = (normals[:, 2] < limit) & (normals[:, 2] > -BED_FACE_COS)
        measured = float(areas[down].sum() / total)
    except ImportError as exc:
        _report_missing_dependency("overhang", exc)
        return None
    except Exception:
        return None

    if measured <= OVERHANG_AREA_FRACTION:
        return None

    return PrintabilityNote(
        rule="overhang",
        measured=measured,
        message=(
            f"{_prefix(mode, part, preset)}: overhangs — {measured * 100:.0f}% of "
            f"surface area is unsupported downward-facing slope (more than "
            f"{OVERHANG_ANGLE_DEG:.0f}° from vertical, excluding the bed-contact "
            f"face); may need supports, or reorienting on the bed. Threshold is "
            f"provisional."
        ),
    )


def build_volume_note(mesh, *, mode: str, part: str, preset: str | None = None):
    """Bounding box: note when the part will not fit a common printer bed.

    THRESHOLD IS PROVISIONAL, pending full-commons calibration: BUILD_VOLUME_MM
    (256mm on any axis). Deliberately generous — a 256mm envelope covers the
    consumer machines the commons targets, so a part that exceeds it is telling the
    user something real even though plenty of larger machines exist. It is a note
    because "too big" is a property of the reader's printer, not of the cartridge.
    """
    try:
        extents = [float(x) for x in mesh.extents]
    except ImportError as exc:
        _report_missing_dependency("build_volume", exc)
        return None
    except Exception:
        return None
    if not extents:
        return None

    measured = max(extents)
    if measured <= BUILD_VOLUME_MM:
        return None

    dims = " x ".join(f"{e:.0f}" for e in extents)
    return PrintabilityNote(
        rule="build_volume",
        measured=measured,
        message=(
            f"{_prefix(mode, part, preset)}: build volume — bounding box is {dims}mm, "
            f"exceeding {BUILD_VOLUME_MM:.0f}mm on at least one axis (a common bed). "
            f"Will not fit a consumer printer without splitting. Threshold is "
            f"provisional."
        ),
    )


def printability_notes(
    mesh, *, mode: str, part: str, preset: str | None = None
) -> list[PrintabilityNote]:
    """Every printability measurement on one rendered mesh, in cost order.

    Called only for renders that already PASSED the conformance bar: measuring the
    wall thickness of a mesh with holes in it produces numbers that mean nothing, and
    a broken cartridge already has a failure to read.
    """
    notes: list[PrintabilityNote] = []
    for fn in (build_volume_note, overhang_note, thin_wall_note):
        note = fn(mesh, mode=mode, part=part, preset=preset)
        if note is not None:
            notes.append(note)
    return notes
