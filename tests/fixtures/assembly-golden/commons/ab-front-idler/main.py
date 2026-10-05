"""
A/B Front Idler — Yantra4D Hyperobject Cartridge (CadQuery / B-Rep).

A printed front idler for a CoreXY gantry whose two belts run stacked on two levels (a
Voron 2.4-class flying gantry). It sits on the front end of a gantry Y extrusion (a 2020 "C"
extrusion carrying the MGN9 rail) and turns one belt through 180° on a GT2 20-tooth toothed
idler (the belt's teeth run on it), outboard of the C, on its belt level above the C. It is
an ORIGINAL design built to functional facts cited by page from the Voron 2.4r2 build guide
(GPL-3.0; pp. 65 and 69: the A and B idlers at the gantry's front corners; pp. 91–93: on
the front ends of the C extrusions, on M5 screws into T-nuts; p. 88: the rail starts 25 mm
from that end; pp. 126–127: each belt makes a U-turn round its front idler) and from
datasheets. No Voron geometry is copied, traced or derived. The guide's front idlers carry
F695 stacks; this design uses the cataloged 6 mm toothed idler instead, whose smaller
effective diameter (12.73 against 15.03) is what lets the X carriage reach X ±175.

Round 2 (lane P6-GANTRY, 2026-10-05): the gantry's belts run above the C's (D crosses
above them), outboard of the C's outer face, and the body stays out of the Z-joint and
Z-strand keep-outs at the C's front end.

The body is one piece:
  - a block on the C's top face before the rail, held by an M5 screw into a T-nut at the
    C's slot station (10 from its end) and keyed into the slot (everything over the C's
    inboard half stays below gantry z 10, under the X carriage at Y = 0);
  - a web behind it, outboard, carrying a boss under the idler and a post past the outer
    belt run;
  - a roof arm from the post over the idler; the idler's BHCS M5x16 axle sits on the roof
    and cuts its thread in a pilot in the boss.

Belt geometry (cited, see docs/README.md): the idler's pitch circle (12.73 / 2) is tangent
to both runs of its belt: the outer run (to the A/B drive) at gantry |x| 225.738 and the
inner run (to the XY joint's stack) at 213.006. The default is the LEFT (B) idler on the
low belt level (gantry z 54); `mirrored` builds the RIGHT (A) idler on the high level (70).

Model frame: origin on the C's top face, on its centreline, at its front end face; +x to
the gantry's right (inboard for the left idler), +y to the back, +z up (gantry z).

Sandbox contract (apps/api/services/engine/cq_runner.py):
  - `cq` and `math` are pre-injected globals.
  - Manifest parameters are injected as BARE globals (e.g. `idler_y`).
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
# GT2 20T toothed idler (catalog gt2-idler-20t-6mm: Motedis OD 18, width 9; pitch diameter
# 12.73, SDP/SI Table 33).
IDLER_OD = 18.0
IDLER_R = 12.7324 / 2.0
# MISUMI HFS5-2020: 20 profile, 6 mm slots, 2 mm lips; Ø4.2 the hole MISUMI taps M5.
PROFILE = 20.0
SLOT_LIP_T = 2.0
PILOT_D = 4.2
# Guide p. 88: the MGN9 rail starts 25 mm from the C's end. ISO 7380-1 M5 head dk 9.5.
RAIL_SETBACK = 25.0
M5_HEAD = 9.5

# ── Conventions (labelled; not sourced facts) ────────────────────────────────
Z_LOW, Z_HIGH = 54.0, 70.0      # belt mid-planes above the C top (as xy-joint and ab-drive)
U_IDLER = 15.372                # idler axis outboard of the C centre (gantry |x| 219.372)
STATION = 10.0                  # the C's slot station (extrusion-2020 default)
GRIP = 4.5                      # M5x10 head seat above the C top: 5.5 passes into the nut
BLOCK_T = 8.0                   # the block over the C's inboard half stays under z 10
BOSS_D = 9.0
ROOF_T = 3.0                    # roof arm: M5x16 = 3 roof + 9 idler + 4 in the pilot
POST_X0, POST_X1 = -29.5, -25.5  # post outboard of the outer run (gantry |x| 229.5…233.5)
WEB_Y0, WEB_Y1 = 17.0, 29.5     # behind the front keep-out (y > 16), ahead of the Y block
HOLE_CLEAR = 0.25
TAB_W = 5.8

# ── Parameters ───────────────────────────────────────────────────────────────
idler_y = float(PARAM(lambda: idler_y, 26.0))       # idler axis from the C's front end
idler_width = float(PARAM(lambda: idler_width, 9.0))
mirrored = bool(PARAM(lambda: mirrored, False))     # the right (A) idler, high level
target_part = str(PARAM(lambda: target_part, "front_idler"))

idler_y = max(25.5, min(idler_y, 27.0))
idler_width = max(6.0, min(idler_width, 10.0))
z_belt = Z_HIGH if mirrored else Z_LOW
z_floor = z_belt - idler_width / 2.0
z_roof = z_belt + idler_width / 2.0


def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def _cyl(p, d, axis, length):
    solid = cq.Solid.makeCylinder(d / 2.0, length, cq.Vector(*p), cq.Vector(*axis))
    return cq.Workplane("XY").add(solid)


def build_front_idler():
    half = PROFILE / 2.0
    xi = -U_IDLER
    # Block on the C top before the rail, under z 10 over the C's inboard half.
    body = _box(-half, half, 0.5, RAIL_SETBACK - 1.0, 0.0, BLOCK_T)
    body = body.union(_box(-2.9, 2.9, 1.0, RAIL_SETBACK - 2.0, -SLOT_LIP_T, 0.5))
    # Web: outboard of the rail, from the block's outboard half out to the post.
    body = body.union(_box(POST_X0, -6.0, WEB_Y0, WEB_Y1, 0.0, z_floor - 1.5))
    # Boss under the idler (it may reach past the web's back edge).
    body = body.union(_cyl((xi, idler_y, 0.0), BOSS_D, (0, 0, 1), z_floor))
    # Post past the outer run, and the roof arm over the idler.
    body = body.union(_box(POST_X0, POST_X1, WEB_Y0 + 1.0, WEB_Y1, 0.0, z_roof + ROOF_T))
    body = body.union(_box(POST_X0 + 0.5, xi, idler_y - 3.0, idler_y + 3.0, z_roof,
                           z_roof + ROOF_T))
    body = body.union(_cyl((xi, idler_y, z_roof), 10.0, (0, 0, 1), ROOF_T))
    # The C screw: clearance through block and tongue, counterbore open to the top.
    body = body.cut(_cyl((0.0, STATION, -SLOT_LIP_T - 1.0), 5.0 + 2 * HOLE_CLEAR, (0, 0, 1),
                         GRIP + SLOT_LIP_T + 1.0))
    body = body.cut(_cyl((0.0, STATION, GRIP), M5_HEAD + 1.0, (0, 0, 1), BLOCK_T))
    # Axle: clearance through the roof, pilot in the boss for the M5x16 tip.
    body = body.cut(_cyl((xi, idler_y, z_roof - 0.5), 5.0 + 2 * HOLE_CLEAR, (0, 0, 1),
                         ROOF_T + 1.0))
    tip = z_roof + ROOF_T - 16.0
    body = body.cut(_cyl((xi, idler_y, tip - 0.5), PILOT_D, (0, 0, 1), z_floor - tip + 1.0))
    if mirrored:
        body = body.mirror("YZ")
    return body


_dispatch = {"front_idler": build_front_idler}

result = _dispatch.get(target_part, build_front_idler)()
