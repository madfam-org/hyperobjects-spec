"""
Corner Idler Bracket — Yantra4D Hyperobject Cartridge (CadQuery / B-Rep).

A printed bracket that carries a GT2 toothed idler in the inside top corner of a
2020 extrusion frame joined by blind joints (an upright with two horizontals butted
on its faces, tops flush). It is an ORIGINAL design built to the functional facts a
Voron 2.4-class printer's Z idler states (Voron 2.4r2 build guide, GPL-3.0, cited by
page only, pp. 48–50): a GT2 20-tooth 9 mm idler on an M5x30 button head screw, the
bracket fixed by two M5 T-nuts to a top horizontal and pressed into the corner. No
Voron geometry is copied, traced or derived.

The body is one block on the horizontal's inner face:
  - two counterbored M5 holes on the slot line, for M5x30 button head screws into
    two T-nuts in the horizontal's slot;
  - a tongue on its corner end that keys into the slot of the perpendicular top
    horizontal, whose side it bears on;
  - a heel that reaches past the corner, below that horizontal, onto the upright's
    inner face, with a tongue keyed into the upright's slot ("against the upright");
  - a fork under the slot line: a pocket open at the bottom (the belt leaves the
    idler downward on both sides) between a front arm, with a clearance hole for the
    M5x30's head, and a rear arm the screw cuts its own thread into.

Model frame (the frames in project.json use it): origin on the inside corner line at
the top horizontals' slot-centre height; +x along the horizontal the bracket mounts
on, away from the corner; +y out of that horizontal's inner face, into the frame; +z
up, with the frame's top at z = +10. `mirrored` builds the opposite hand (the guide's
mirrored pair, p. 50) by reflecting x.

Sandbox contract (apps/api/services/engine/cq_runner.py):
  - `cq` and `math` are pre-injected globals.
  - Manifest parameters are injected as BARE globals (e.g. `idler_width`).
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
# ISO 7380-1 M5x30 button head screw (Keller & Kalmbach datasheet 157380530):
# d 5, l 30, head dk 9.5, k 2.75. The bracket's depth along the idler axle is the
# screw's length, so the tip ends on the mount face.
SCREW_D = 5.0
SCREW_L = 30.0
HEAD_DK = 9.5
HEAD_K = 2.75
# MISUMI HFS5 "T Slot Dimensions" (https://us.misumi-ec.com/pdf/fa/2012/p2_0513.pdf,
# as cited by roller-bracket): a 6 mm opening between lips 2 mm thick; Ø4.2 centre
# hole that MISUMI taps M5 (end tapping, p2_0681) — used here as the pilot the axle
# screw cuts its thread in (the guide's XY idlers are screwed into plastic, pp. 98, 100).
SLOT_LIP_T = 2.0
PILOT_D = 4.2
# The 20 mm profile square (MISUMI HFS5-2020): the corner station 10 from the end.
PROFILE = 20.0
# MISUMI HNTAP5-5 post-assembly T-nut: 15 mm long (two nuts must not overlap).
TNUT_L = 15.0

# ── Conventions (labelled; not sourced facts) ────────────────────────────────
HOLE_CLEAR = 0.25        # per side on the M5 clearance holes: Ø5.5
HEAD_CLEAR = 0.5         # per side on the counterbore: Ø10.5
TAB_W = 5.8              # tongue width in the 6 mm opening (as roller-bracket)
POCKET_RADIAL = 1.0      # pocket clearance round the idler's outside diameter
AXLE_WALL = 7.0          # material below the axle centre in the arms
HEEL_GAP = 0.5           # heel top below the perpendicular horizontal's underside
MOUNT_X1 = 10.0          # first mount hole from the corner plane
UPRIGHT_KEY_Z = -20.0    # heel tongue station: the upright's slot_station_mm 30
CORNER_KEY_Y = 10.0      # corner tongue station: the horizontal's slot_station_mm 10
EDGE = 4.75              # wall beyond the last counterbore

# ── Parameters ───────────────────────────────────────────────────────────────
idler_width = float(PARAM(lambda: idler_width, 14.0))   # GT2 idler flange to flange
idler_od = float(PARAM(lambda: idler_od, 18.0))         # GT2 idler outside diameter
idler_clear = float(PARAM(lambda: idler_clear, 0.5))    # axial clearance each side
idler_offset = float(PARAM(lambda: idler_offset, 13.0))  # axle x from the corner plane
idler_drop = float(PARAM(lambda: idler_drop, 24.0))     # axle below the slot centre
front_arm = float(PARAM(lambda: front_arm, 5.0))        # head-side arm thickness
mount_grip = float(PARAM(lambda: mount_grip, 24.5))     # under-head to mount face
mount_pitch = float(PARAM(lambda: mount_pitch, 20.0))   # T-nut spacing
heel_reach = float(PARAM(lambda: heel_reach, 18.0))     # heel past the corner plane
mirrored = bool(PARAM(lambda: mirrored, False))         # opposite hand
target_part = str(PARAM(lambda: target_part, "corner_idler"))

# ── Derived / clamped ────────────────────────────────────────────────────────
idler_width = max(9.0, min(idler_width, 20.0))
idler_od = max(12.0, min(idler_od, 24.0))
idler_clear = max(0.2, min(idler_clear, 2.0))
front_arm = max(3.0, min(front_arm, 8.0))
gap = idler_width + 2.0 * idler_clear
rear_arm = SCREW_L - front_arm - gap                     # ≥ 4 over the manifest ranges
pocket_r = idler_od / 2.0 + POCKET_RADIAL
idler_offset = max(pocket_r + 1.0, min(idler_offset, 40.0))
idler_drop = max(pocket_r + 8.0, min(idler_drop, 60.0))
mount_grip = max(SCREW_L - 8.0, min(mount_grip, SCREW_L - HEAD_K - 0.5))
mount_pitch = max(TNUT_L + 1.0, min(mount_pitch, 60.0))
heel_reach = max(PROFILE / 2.0 + TAB_W / 2.0 + 2.0, min(heel_reach, PROFILE))

DEPTH = SCREW_L                                          # y extent of the body
TOP = PROFILE / 2.0                                      # frame top, z = +10
z_axle = -idler_drop
z_bottom = z_axle - AXLE_WALL
x2 = MOUNT_X1 + mount_pitch
length = max(x2 + (HEAD_DK / 2.0 + HEAD_CLEAR) + EDGE, idler_offset + pocket_r + 4.0)
heel_top = -PROFILE / 2.0 - HEEL_GAP


def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def _cyl_y(x, z, d, y0, y1):
    """A cylinder of diameter d along +y from y0 to y1, axis at (x, z)."""
    solid = cq.Solid.makeCylinder(d / 2.0, y1 - y0, cq.Vector(x, y0, z), cq.Vector(0, 1, 0))
    return cq.Workplane("XY").add(solid)


def build_corner_idler():
    # Block on the horizontal's inner face, the full depth, from the frame top down
    # through the fork.
    body = _box(0.0, length, 0.0, DEPTH, z_bottom, TOP)
    # Heel past the corner plane, below the perpendicular horizontal (overlaps the
    # block by 0.5 so the join is a real union, not a touching face).
    body = body.union(_box(-heel_reach, 0.5, 0.0, DEPTH, z_bottom, heel_top))
    # Corner tongue into the perpendicular horizontal's slot (along y).
    body = body.union(_box(-SLOT_LIP_T, 0.5, 2.0, DEPTH - 2.0, -TAB_W / 2.0, TAB_W / 2.0))
    # Heel tongue into the upright's slot (along z).
    body = body.union(_box(-PROFILE / 2.0 - TAB_W / 2.0, -PROFILE / 2.0 + TAB_W / 2.0,
                           -SLOT_LIP_T, 0.5, z_bottom + 2.0, heel_top - 2.0))
    # Mount holes on the slot line, counterbored from the inside face for the heads.
    for x in (MOUNT_X1, x2):
        body = body.cut(_cyl_y(x, 0.0, SCREW_D + 2 * HOLE_CLEAR, -1.0, DEPTH + 1.0))
        body = body.cut(_cyl_y(x, 0.0, HEAD_DK + 2 * HEAD_CLEAR, mount_grip, DEPTH + 1.0))
    # The idler pocket, open at the bottom, between the arms.
    body = body.cut(_box(idler_offset - pocket_r, idler_offset + pocket_r,
                         rear_arm, rear_arm + gap, z_bottom - 1.0, z_axle + pocket_r))
    # Axle: clearance through the front arm, pilot through the rear arm.
    body = body.cut(_cyl_y(idler_offset, z_axle, SCREW_D + 2 * HOLE_CLEAR,
                           rear_arm + gap - 0.5, DEPTH + 1.0))
    body = body.cut(_cyl_y(idler_offset, z_axle, PILOT_D, -1.0, rear_arm + 0.5))
    if mirrored:
        body = body.mirror("YZ")
    return body


_dispatch = {"corner_idler": build_corner_idler}

result = _dispatch.get(target_part, build_corner_idler)()
