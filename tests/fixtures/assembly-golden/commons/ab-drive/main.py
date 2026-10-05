"""
A/B Drive — Yantra4D Hyperobject Cartridge (CadQuery / B-Rep).

A printed A/B drive unit for a CoreXY gantry whose two belts run stacked on two levels (a
Voron 2.4-class flying gantry). It sits on the rear end of a gantry Y extrusion (a 2020 "C"
extrusion), reaches the rear gantry beam (the "E" extrusion), hangs a NEMA 17 under a motor
plate inboard of the C, and carries four belt elements on two levels:

  - its own belt's GT2 20T motor pulley, wrapped about 126° by an omega (SDP/SI §13.3: at
    least 6 teeth in mesh on a loaded pulley, i.e. at least 108° on 20 teeth);
  - a backside F695 stack Q (the belt's back on it) that bends the rear run round the pulley;
  - a GT2 20T toothed idler K at the outboard rear corner that turns the diagonal from the
    pulley into the outer run (outboard of the C);
  - a pass-through F695 stack S on the other level that turns the other belt from its Y run
    into its rear run.

It is an ORIGINAL design built to functional facts cited by page from the Voron 2.4r2 build
guide (GPL-3.0; pp. 73–80: the A and B drives carry a NEMA 17 with a GT2 20-tooth pulley and
F695 stacks on M5 screws into plastic; pp. 85–87: the rear E extrusion and the drives on M5
T-nuts; p. 95: the drives on the rear ends of the C extrusions; pp. 125–127: the stacked
CoreXY belt path) and from datasheets. No Voron geometry is copied, traced or derived.

Round 2 (lane P6-GANTRY, 2026-10-05): the gantry's belts run above the C's (D crosses above
them); the motor sits inboard of the C so the drive stays clear of the Z rails, the Z belts
and the Z joints at the rear corners, and every element outboard of the C stays ahead of
the rear keep-out.

The default is the LEFT (B) drive: its pulley, Q and K on the low level (gantry z 54), S on
the high level (70). `mirrored` builds the RIGHT (A) drive: x reflected, levels swapped, and
the rear runs one millimetre apart (B at 434, A at 435 in gantry y), so the low belt's rear
run passes in front of the A drive's motor and the high belt's run in front of the B drive's
Q head.

Model frame: origin on the C's top face, on its centreline, at its REAR end face; +x to the
gantry's right (inboard for the left drive), +y to the back, +z up (gantry z).

Sandbox contract (apps/api/services/engine/cq_runner.py):
  - `cq` and `math` are pre-injected globals.
  - Manifest parameters are injected as BARE globals (e.g. `mirrored`).
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
# NEMA 17 (keystone nema-17-48mm): face 42.3, 4 × M3 on 31, pilot Ø22 × 2.
NEMA_FACE = 42.3
NEMA_BOLT = 31.0
NEMA_PILOT = 22.0
# GT2 20T pulley (Adafruit 1251): flange Ø16, length 16; belt mid-plane 8 above its face A
# (a convention shared with the keystone's gt2-pulley-20t-5mm belt_engagement).
PULLEY_FLANGE = 16.0
PULLEY_MID = 8.0
SHAFT_SEAT = 2.0        # the pulley's face A on the motor's pilot (nema-17-48mm default)
# F695 stack 10 tall (1 mm DIN 988 shims + 2 × 4 mm F695); GT2 20T idler 9 wide (Motedis).
STACK_H = 10.0
IDLER_W = 9.0
# MISUMI HFS5-2020: 20 profile, 6 mm slots, 2 mm lips; Ø4.2 the hole MISUMI taps M5.
PROFILE = 20.0
SLOT_LIP_T = 2.0
PILOT_D = 4.2
# Guide p. 88: the MGN9 rail ends 25 mm from the C's end. ISO 7380-1 M5 head dk 9.5.
RAIL_SETBACK = 25.0
M5_HEAD = 9.5

# ── Conventions (labelled; not sourced facts) ────────────────────────────────
Z_LOW, Z_HIGH = 54.0, 70.0          # belt mid-planes above the C top
P_XY = (32.0, 8.0)                  # pulley axis: 32 inboard of the C centre, 8 behind its end
U_Q = 45.0                          # Q axis inboard
K_XY = (-15.372, -25.5)             # K axis: tangent to the outer run (gantry |x| 225.738)
U_S = -1.852                        # S axis: tangent to the other belt's Y run (gantry 213.366)
Y_RUN_LOW, Y_RUN_HIGH = -16.0, -15.0   # rear runs: B at gantry y 434, A at 435
E_END = 34.0                        # E (340) ends 34 inboard of the C centre at a 408 spacing
E_Y0, E_Y1 = -44.0, -24.0           # E's y band: ahead of the motor (which reaches y −13.15)
GRIP = 4.5                          # M5x10 head seats 4.5 above the C / E top faces
PLATE_T = 4.0
ROOF_T = 3.0
BOSS_D = 9.0
POST_K = (-29.5, -25.5, -28.5, -22.5)   # K post outboard of the outer run
POST_S = (6.0, 10.0, -28.0, -21.0)      # S post beside the rail's end (starts above it)
POST_Q = (54.0, 58.0, -12.0, -6.0)      # Q post on the motor plate
HOLE_CLEAR = 0.25
M3_CB = 6.5
TAB_W = 5.8

# ── Parameters ───────────────────────────────────────────────────────────────
mirrored = bool(PARAM(lambda: mirrored, False))      # the right (A) drive
e_end = float(PARAM(lambda: e_end, E_END))           # E's end inboard of the C centre
target_part = str(PARAM(lambda: target_part, "ab_drive"))

e_end = max(30.0, min(e_end, 40.0))
z_own = Z_HIGH if mirrored else Z_LOW
z_oth = Z_LOW if mirrored else Z_HIGH
y_own = Y_RUN_HIGH if mirrored else Y_RUN_LOW
y_oth = Y_RUN_LOW if mirrored else Y_RUN_HIGH
z_face = z_own - PULLEY_MID - SHAFT_SEAT            # motor face = plate underside
Q_XY = (U_Q, y_own + 6.5 + 0.506)                   # back side of the own rear run
S_XY = (U_S, y_oth - 6.5 - 1.014)                   # teeth side of the other run


def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def _cyl(p, d, axis, length):
    solid = cq.Solid.makeCylinder(d / 2.0, length, cq.Vector(*p), cq.Vector(*axis))
    return cq.Workplane("XY").add(solid)


def _element(body, xy, z_floor, h, post, base_z):
    """A boss up to the element's floor, a post up to the roof, a roof arm and the axle."""
    x, y = xy
    z_roof = z_floor + h
    body = body.union(_cyl((x, y, base_z), BOSS_D, (0, 0, 1), z_floor - base_z))
    px0, px1, py0, py1 = post
    body = body.union(_box(px0, px1, py0, py1, base_z, z_roof + ROOF_T))
    cx, cy = (px0 + px1) / 2.0, (py0 + py1) / 2.0
    # The arm: a straight bar from the post's centre to the axle, 6 wide.
    body = body.union(_bar((cx, cy), (x, y), z_roof, z_roof + ROOF_T))
    body = body.union(_cyl((x, y, z_roof), 10.0, (0, 0, 1), ROOF_T))
    body = body.cut(_cyl((x, y, z_roof - 0.5), 5.0 + 2 * HOLE_CLEAR, (0, 0, 1), ROOF_T + 1.0))
    tip = z_roof + ROOF_T - 16.0                    # BHCS M5x16 on the roof
    body = body.cut(_cyl((x, y, tip - 0.5), PILOT_D, (0, 0, 1), z_floor - tip + 1.0))
    return body


def _bar(a, b, z0, z1, w=6.0):
    import math as _m
    (ax, ay), (bx, by) = a, b
    length = _m.hypot(bx - ax, by - ay)
    ang = _m.degrees(_m.atan2(by - ay, bx - ax))
    bar = (cq.Workplane("XY").box(length, w, z1 - z0, centered=(False, True, False))
           .rotate((0, 0, 0), (0, 0, 1), ang).translate((ax, ay, z0)))
    return bar


def build_ab_drive():
    half = PROFILE / 2.0
    # Base on the C's top behind the rail; a bridge out to the K column and post.
    body = _box(-half, half, -RAIL_SETBACK + 0.5, 0.0, 0.0, 6.0)
    body = body.union(_box(-2.9, 2.9, -RAIL_SETBACK + 1.5, -1.0, -SLOT_LIP_T, 0.5))
    body = body.union(_box(POST_K[0], -half + 0.5, -28.5, -20.5, 0.0, 6.0))
    # E arm: along y = E band, from the base's inboard edge to E's end.
    body = body.union(_box(half + 0.5, e_end + PROFILE, E_Y0 + 1.0, E_Y1 - 0.5, 0.0, 6.0))
    body = body.union(_box(half - 0.5, half + 6.0, E_Y1 - 1.0, -RAIL_SETBACK + 1.0, 0.0, 6.0))
    body = body.union(_box(e_end + 1.5, e_end + PROFILE - 1.5, (E_Y0 + E_Y1) / 2 - TAB_W / 2,
                           (E_Y0 + E_Y1) / 2 + TAB_W / 2, -SLOT_LIP_T, 0.5))
    # Pillar from the base up to the motor plate (inboard of the rail end, ahead of the
    # motor), and the motor plate.
    px, py = P_XY
    m0, m1 = py - NEMA_FACE / 2 - 1.0, py + NEMA_FACE / 2
    body = body.union(_box(2.0, half + 0.5, m0, -2.0, 0.0, z_face + 0.5))
    body = body.union(_box(px - NEMA_FACE / 2, POST_Q[1] + 1.0, m0, m1, z_face, z_face + PLATE_T))
    body = body.union(_box(2.0, px - NEMA_FACE / 2 + 0.5, m0, -2.0, z_face, z_face + PLATE_T))
    # Motor: pilot and pulley pass, M3 screws (counterbored from the top of the plate).
    body = body.cut(_cyl((px, py, z_face - 1.0), NEMA_PILOT + 2.0, (0, 0, 1), PLATE_T + 2.0))
    for dx in (-NEMA_BOLT / 2, NEMA_BOLT / 2):
        for dy in (-NEMA_BOLT / 2, NEMA_BOLT / 2):
            body = body.cut(_cyl((px + dx, py + dy, z_face - 1.0), 3.4, (0, 0, 1), PLATE_T + 2.0))
    # Elements.
    body = _element(body, K_XY, z_own - IDLER_W / 2, IDLER_W, POST_K, 0.0)
    body = _element(body, Q_XY, z_own - STACK_H / 2, STACK_H, POST_Q, z_face + PLATE_T - 0.5)
    # S: over the rail's end, so its boss and post start above the rail (6.5), on a block
    # behind the rail end.
    body = body.union(_box(S_XY[0] - 4.5, POST_S[1], -RAIL_SETBACK + 0.5, S_XY[1] + 4.5, 0.0, 7.5))
    body = _element(body, S_XY, z_oth - STACK_H / 2, STACK_H, POST_S, 7.0)
    # C and E screws: clearance, counterbores open to the top.
    e_mid = (E_Y0 + E_Y1) / 2.0
    for x, y in ((0.0, -10.0), (e_end + 10.0, e_mid)):
        body = body.cut(_cyl((x, y, -SLOT_LIP_T - 1.0), 5.0 + 2 * HOLE_CLEAR, (0, 0, 1),
                             GRIP + SLOT_LIP_T + 1.0))
        body = body.cut(_cyl((x, y, GRIP), M5_HEAD + 1.0, (0, 0, 1), 10.0))
    if mirrored:
        body = body.mirror("YZ")
    return body


_dispatch = {"ab_drive": build_ab_drive}

result = _dispatch.get(target_part, build_ab_drive)()
