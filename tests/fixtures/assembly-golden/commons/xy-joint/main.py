"""
XY Joint — Yantra4D Hyperobject Cartridge (CadQuery / B-Rep).

A printed XY joint for a CoreXY gantry whose two belts run stacked on two levels (a
Voron 2.4-class "flying gantry"). It is screwed onto the MGN9H block of a Y rail on top of
the gantry's Y extrusion (C), holds the end of the X beam (D) so that D crosses ABOVE the
C's, and turns both belts through 90° on a shelf above D: one belt on a GT2 20-tooth
toothed idler, the other on a stack of two F695 flanged bearings. It is an ORIGINAL design
built to functional facts cited by page from the Voron 2.4r2 build guide (GPL-3.0; pp.
97–100: an F695 stack and a GT2 20T idler per joint; p. 101: the MGN12 rail ends 15 mm from
D's end; pp. 104–106: the X beam held in the joints, the joints screwed onto the Y
carriages with M3 screws; p. 125: the belts stacked, the crossing omitted) and from
datasheets. No Voron geometry is copied, traced or derived.

Round 2 (lane P6-GANTRY, 2026-10-05): D now sits above the C's (the guide's function), so
the gantry fits between the Z rails and the X carriage reaches X ±175 (Klipper 350).

The body is one piece:
  - a base on the MGN9H block (four M3 screws, HIWIN B 15 × C 16, M3x3 threads);
  - a saddle under D's last 15 mm (the part of D without rail), keyed into D's bottom
    slot; an outboard wall past D's end, a front wall and a back wall that holds D with an
    M5 screw into a T-nut in D's back slot;
  - a shelf over D carrying the F695 stack directly and the toothed idler on a boss, each
    clamped under a 3 mm roof arm from the outboard post by a BHCS M5x16 axle whose head
    sits on the roof.

Belt geometry (cited, see docs/README.md): the stack sits one F695 running radius plus the
belt's back-side offset (13 / 2 + 0.506) in front of the belt line, the idler one GT2 20T
pitch radius (12.73 / 2) behind it. The low belt (B) runs at gantry z 54, the high (A) at
70 (C top = 0); mirrored, the stack and the idler swap levels.

Model frame: origin at the centre of the MGN9H block's top face; +x to the gantry's right
(inboard for the default LEFT joint), +y to the back, +z up. Gantry z = this z + 10 (the
MGN9 assembly height H). `mirrored` builds the RIGHT joint: x reflected, levels swapped.

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
# HIWIN MG series MGN9H: W 20, B 15 (across), C 16 (along), M3x3 threads.
BLOCK_W = 20.0
HOLE_B = 15.0
HOLE_C = 16.0
# GT2 20T pitch diameter 12.73 (SDP/SI Table 33); F695 OD 13 (NSK); GT2 2 mm belt
# B 1.52, T 0.76 (Pfeifer 2MR/PGGT2), U 0.254 (SDP/SI Table 4): back-side offset 0.506.
IDLER_R = 12.7324 / 2.0
STACK_R = 13.0 / 2.0 + (1.52 - 0.76 - 0.254)
STACK_H = 10.0          # 1 mm DIN 988 shim + 2 × 4 mm F695 (NSK B) + shim
# D: a 20 × 20 2020 (MISUMI HFS5): 6 mm slots, 2 mm lips. Guide p. 101: the MGN12 rail
# ends 15 mm from D's end, so the joint holds D only over that last 15 mm.
PROFILE = 20.0
SLOT_LIP_T = 2.0
RAIL_SETBACK = 15.0
# ISO 7380-1 M5 button head: dk 9.5, k 2.75. ISO 4762 M3: dk 5.5, k 3.
M5_HEAD = 9.5
M3_HEAD = 5.5
PILOT_D = 4.2           # the hole MISUMI taps M5 (p2_0681): the axles' pilots

# ── Conventions (labelled; not sourced facts) ────────────────────────────────
BASE_T = 8.0            # base on the block (M3x8 head seats 5 up, counterbored)
M3_SEAT = 5.0           # M3x8: 8 − 3 (thread depth M3x3) = 5 mm of base under the head
D_BOTTOM = 12.0         # D's bottom face: 4 mm saddle on the base
SHELF_GAP = 0.5         # shelf clears D's top face
SHELF_T = 6.5           # shelf thickness: the low element's floor is the shelf top
Z_LOW = 44.0            # low belt mid-plane (gantry 54)
Z_HIGH = 60.0           # high belt mid-plane (gantry 70)
U_STACK = 2.0           # stack axis outboard of the rail centre (gantry |x| 206)
U_IDLER = 3.0           # idler axis outboard (gantry |x| 207)
BOSS_D = 9.0            # bosses under the raised element
ROOF_T = 3.0            # roof arm over each element: M5x16 = 3 roof + 10 stack + 3 in the pilot
ARM_W = 6.0             # roof arm width
WALL_T = 4.5            # back wall: the M5x10 BHCS grip (10 − 5.5 into the T-nut)
OUT_X = -18.0           # outboard extent (gantry |x| 222): 3.7 inside the outer belt run
IN_X = 5.5              # inboard extent of the shelf (gantry |x| 198.5)
FRONT_Y, BACK_Y = -18.0, 16.0
HOLE_CLEAR = 0.25
TAB_W = 5.8

# ── Parameters ───────────────────────────────────────────────────────────────
idler_width = float(PARAM(lambda: idler_width, 9.0))     # toothed idler, flange to flange
d_end = float(PARAM(lambda: d_end, 11.0))                 # D's end outboard of the rail centre
mirrored = bool(PARAM(lambda: mirrored, False))           # the right-hand joint
target_part = str(PARAM(lambda: target_part, "xy_joint"))

idler_width = max(6.0, min(idler_width, 10.0))
d_end = max(8.0, min(d_end, 13.0))
z_stack = Z_HIGH if mirrored else Z_LOW
z_idler = Z_LOW if mirrored else Z_HIGH
D_TOP = D_BOTTOM + PROFILE
SHELF_Z0 = D_TOP + SHELF_GAP
SHELF_Z1 = SHELF_Z0 + SHELF_T
D_END_X = -d_end
D_HELD_X = D_END_X + RAIL_SETBACK          # where D's rail starts (gantry |x| 200)
Y_STACK, Y_IDLER = -STACK_R, IDLER_R


def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def _cyl(p, d, axis, length):
    solid = cq.Solid.makeCylinder(d / 2.0, length, cq.Vector(*p), cq.Vector(*axis))
    return cq.Workplane("XY").add(solid)


def build_xy_joint():
    half = PROFILE / 2.0
    held_in = D_HELD_X - 0.5                         # saddle and walls stop at the rail
    # Base on the block, out past the C to the outboard wall.
    body = _box(OUT_X, BLOCK_W / 2.0, FRONT_Y, -FRONT_Y, 0.0, BASE_T)
    # Saddle under D's held end (narrow in y, clear of the M3 heads at y ±8), with a
    # tongue in D's bottom slot.
    body = body.union(_box(D_END_X - 0.5, held_in, -5.0, 5.0, BASE_T - 0.5, D_BOTTOM))
    body = body.union(_box(D_END_X + 1.0, held_in, -TAB_W / 2, TAB_W / 2,
                           D_BOTTOM - 0.5, D_BOTTOM + SLOT_LIP_T))
    # Outboard wall past D's end, base to shelf.
    body = body.union(_box(OUT_X, D_END_X - 0.5, -14.0, 14.0, BASE_T - 0.5, SHELF_Z0 + 0.5))
    # Back wall (holds D by its back slot) and front wall, both stopping at the rail start.
    body = body.union(_box(OUT_X, held_in, half, half + WALL_T, BASE_T - 0.5, SHELF_Z0 + 0.5))
    body = body.union(_box(OUT_X, held_in, -half - WALL_T, -half, BASE_T - 0.5, SHELF_Z0 + 0.5))
    # Shelf over D.
    body = body.union(_box(OUT_X, IN_X, -17.0, BACK_Y, SHELF_Z0, SHELF_Z1))
    # Boss under the raised element (the high one), from the shelf.
    if mirrored:
        boss_xy, boss_top = (-U_STACK, Y_STACK), z_stack - STACK_H / 2.0
    else:
        boss_xy, boss_top = (-U_IDLER, Y_IDLER), z_idler - idler_width / 2.0
    body = body.union(_cyl((boss_xy[0], boss_xy[1], SHELF_Z1 - 0.5), BOSS_D, (0, 0, 1),
                           boss_top - SHELF_Z1 + 0.5))
    # The low element on the shelf: a 0.5 mm seat ring under the idler (the stack sits on
    # the shelf top directly).
    if mirrored:
        body = body.union(_cyl((-U_IDLER, Y_IDLER, SHELF_Z1 - 0.5), BOSS_D, (0, 0, 1),
                               z_idler - idler_width / 2.0 - SHELF_Z1 + 0.5))
    # M3 screws into the block: clearance, counterbores open to the top of the base.
    for sx in (-HOLE_B / 2.0, HOLE_B / 2.0):
        for sy in (-HOLE_C / 2.0, HOLE_C / 2.0):
            body = body.cut(_cyl((sx, sy, -1.0), 3.0 + 2 * 0.2, (0, 0, 1), BASE_T + 2.0))
            body = body.cut(_cyl((sx, sy, M3_SEAT), M3_HEAD + 0.5, (0, 0, 1),
                                 BASE_T - M3_SEAT + 1.0))
    # D's back-slot screw: horizontal M5 through the back wall at D's centre height.
    z_d = D_BOTTOM + half
    x_m = D_END_X + 10.0
    body = body.cut(_cyl((x_m, half - 1.0, z_d), 5.0 + 2 * HOLE_CLEAR, (0, 1, 0), WALL_T + 2.0))
    # Outboard post (past D's end) up to the highest roof, and a roof arm over each element.
    roofs = (((-U_STACK, Y_STACK), z_stack + STACK_H / 2.0),
             ((-U_IDLER, Y_IDLER), z_idler + idler_width / 2.0))
    top = max(z for _, z in roofs) + ROOF_T
    body = body.union(_box(OUT_X, min(D_END_X - 0.5, -12.5), -12.0, 12.0, SHELF_Z1 - 0.5, top))
    for (x, y), z0 in roofs:
        body = body.union(_box(OUT_X + 0.5, x, y - ARM_W / 2.0, y + ARM_W / 2.0, z0, z0 + ROOF_T))
        body = body.union(_cyl((x, y, z0), 10.0, (0, 0, 1), ROOF_T))
    # Axles: clearance through each roof, pilot below each element's floor.
    for ((x, y), z_top), z_floor in zip(roofs, (z_stack - STACK_H / 2.0,
                                               z_idler - idler_width / 2.0)):
        body = body.cut(_cyl((x, y, z_top - 0.5), 5.0 + 2 * HOLE_CLEAR, (0, 0, 1), ROOF_T + 1.0))
        tip = z_top + ROOF_T - 16.0                 # BHCS M5x16 head on the roof
        body = body.cut(_cyl((x, y, tip - 0.5), PILOT_D, (0, 0, 1), z_floor - tip + 1.0))
    if mirrored:
        body = body.mirror("YZ")
    return body


_dispatch = {"xy_joint": build_xy_joint}

result = _dispatch.get(target_part, build_xy_joint)()
