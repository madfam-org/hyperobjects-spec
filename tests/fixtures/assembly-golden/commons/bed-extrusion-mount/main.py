"""
Bed Extrusion Mount — Yantra4D Hyperobject Cartridge (CadQuery / B-Rep).

A printed T-plate that joins the end of a bed-support 2020 extrusion to the frame's bottom
horizontal it butts against, tops flush. It is an ORIGINAL design built to the functional
facts a Voron 2.4-class printer's bed supports state (Voron 2.4r2 build guide, GPL-3.0,
cited by page only): two bed extrusions span the frame between its bottom horizontals,
130 mm apart on the printer's centreline, each end fixed with an M5x10 BHCS, an M5 shim
and an M5 T-nut (pp. 19–20); the bed plate then stands on them (pp. 58–60). No Voron
geometry is copied, traced or derived.

The body is one plate lying on the two top faces:
  - a crossbar along the frame horizontal, with two M5 holes for M5x10 button head
    screws into T-nuts in its top slot and a tongue in that slot;
  - a stem along the bed extrusion, with one M5 hole for an M5x10 into a T-nut in its
    top slot and a tongue in that slot.
Both tongues key the plate to both slots, so the bed extrusion is held square to the
horizontal, at its butt, with its top flush.

Model frame (the frames in project.json use it): origin where the bed extrusion's
centreline meets the horizontal's inner face, in the plane of the two top faces; +x
along the horizontal, +y along the bed extrusion into the frame, +z up. The plate is
symmetric in x, so one part serves all four ends.

Sandbox contract (apps/api/services/engine/cq_runner.py):
  - `cq` and `math` are pre-injected globals.
  - Manifest parameters are injected as BARE globals (e.g. `stem_length`).
  - Access them via PARAM(lambda: <name>, <default>) so the script also runs
    standalone / with any subset of params. Do NOT use globals()/eval/getattr.
  - Assign the final solid to a top-level name `result`.
"""

import cadquery as cq


# ── Sandbox-safe parameter access ────────────────────────────────────────────
def PARAM(getter, default):
    """Return an injected global if present, else the default."""
    try:
        v = getter()
        return default if v is None else v
    except Exception:
        return default


# ── Cited facts ──────────────────────────────────────────────────────────────
# ISO 7380-1 M5x10 button head (Keller & Kalmbach 157380510): d 5, l 10, dk 9.5.
SCREW_D = 5.0
SCREW_L = 10.0
HEAD_DK = 9.5
# 2020 series-5 (MISUMI HFS5): 6 mm opening, 2 mm lips; the profile square 20.
SLOT_LIP_T = 2.0
PROFILE = 20.0
# MISUMI HNTAP5-5 post-assembly T-nut: 15 mm long.
TNUT_L = 15.0

# ── Conventions (labelled; not sourced facts) ────────────────────────────────
HOLE_CLEAR = 0.25     # Ø5.5 clearance holes
TAB_W = 5.8           # tongue width in the 6 mm opening (as roller-bracket)
EDGE = 3.5            # plate beyond a screw head
BED_SCREW_Y = 10.0    # the bed extrusion's screw: its slot_station_mm 10
CROSS_IN = 2.0        # the crossbar stops 2 mm short of the horizontal's outer edge

# ── Parameters ───────────────────────────────────────────────────────────────
screw_offset = float(PARAM(lambda: screw_offset, 14.0))   # frame screws at ±offset
stem_length = float(PARAM(lambda: stem_length, 17.5))     # stem along the bed extrusion
plate_t = float(PARAM(lambda: plate_t, 4.5))              # plate = the screws' grip
target_part = str(PARAM(lambda: target_part, "bed_mount"))

# ── Derived / clamped ────────────────────────────────────────────────────────
screw_offset = max(TNUT_L / 2.0 + 0.5, min(screw_offset, 30.0))
stem_length = max(BED_SCREW_Y + HEAD_DK / 2.0 + 1.0, min(stem_length, 40.0))
plate_t = max(4.0, min(plate_t, 5.0))
half_cross = screw_offset + HEAD_DK / 2.0 + EDGE


def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def _cyl_z(x, y, d, z0, z1):
    solid = cq.Solid.makeCylinder(d / 2.0, z1 - z0, cq.Vector(x, y, z0), cq.Vector(0, 0, 1))
    return cq.Workplane("XY").add(solid)


def build_bed_mount():
    # Crossbar over the horizontal's top face, stem over the bed extrusion's (the stem
    # overlaps the crossbar by 0.5 so the join is a real union).
    body = _box(-half_cross, half_cross, -PROFILE + CROSS_IN, 0.0, 0.0, plate_t)
    body = body.union(_box(-PROFILE / 2.0, PROFILE / 2.0, -0.5, stem_length, 0.0, plate_t))
    # Tongues in both top slots.
    body = body.union(_box(-half_cross + 2.0, half_cross - 2.0, -PROFILE / 2.0 - TAB_W / 2.0,
                           -PROFILE / 2.0 + TAB_W / 2.0, -SLOT_LIP_T, 0.5))
    body = body.union(_box(-TAB_W / 2.0, TAB_W / 2.0, 1.0, stem_length - 1.0, -SLOT_LIP_T, 0.5))
    # Screws: heads on the top face, shanks through the plate and the tongue.
    for x, y in ((-screw_offset, -PROFILE / 2.0), (screw_offset, -PROFILE / 2.0), (0.0, BED_SCREW_Y)):
        body = body.cut(_cyl_z(x, y, SCREW_D + 2 * HOLE_CLEAR, -SLOT_LIP_T - 1.0, plate_t + 1.0))
    return body


_dispatch = {"bed_mount": build_bed_mount}

result = _dispatch.get(target_part, build_bed_mount)()
