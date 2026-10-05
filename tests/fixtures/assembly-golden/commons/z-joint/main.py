"""
Z Joint — Yantra4D Hyperobject Cartridge (CadQuery / B-Rep).

A printed joint that hangs one corner of a flying CoreXY gantry (a Voron 2.4-class
machine) on the MGN9H block of a Z rail, and carries that corner's Z belt clamp. It is an
ORIGINAL design built to the functional facts the Voron 2.4r2 build guide states (GPL-3.0,
cited by page only): the Z rails are MGN9 rails centred on the frame uprights, facing each
other across the frame (pp. 25, 27); each gantry corner is joined to its rail's block by a
Z joint (pp. 109, 115–116), four in all; the Z belt's two ends are clamped on the gantry
(pp. 111, 117–121). No Voron geometry is copied, traced or derived. The Voron joint is a
pivot that lets quad gantry levelling tilt the gantry; this joint is rigid (owner decision
D2: one logical Z for the live twin).

The body is one piece:
  - a plate on the MGN9H block's top face (HIWIN MGN9H: B 15 across, C 16 along, M3);
  - a backer standing beside the block, whose face carries `z-belt-clamp` (a groove for the
    clamp's tongue and a Ø4.2 pilot its M5x10 cuts its thread in), placed so the anchored
    belt strand runs vertical, tangent to the corner's Z drive pulley and top idler;
  - a pad under the gantry's C extrusion, keyed into its bottom slot and held by an M5x10
    into a T-nut, reached by a web that stays behind the belt plane, clear of the free
    strand.

Model frame: origin at the centre of the MGN9H block's top face; +x away from the block
(into the frame, toward the gantry), +z up along the rail; for the front-left corner +y
points into the frame (backward). The default is the FRONT-LEFT joint; turned 180° about z
it is the BACK-RIGHT one. `mirrored` reflects x and builds the front-right and back-left
joints.

Sandbox contract (apps/api/services/engine/cq_runner.py):
  - `cq` and `math` are pre-injected globals.
  - Manifest parameters are injected as BARE globals (e.g. `c_inboard`).
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
# HIWIN MG series, MGN9H: H 10, W 20, L 39.9, B 15 (across), C 16 (along), M3.
BLOCK_H = 10.0
BLOCK_W = 20.0
BLOCK_L = 39.9
HOLE_B = 15.0
HOLE_C = 16.0
# GT2 20T pitch diameter 12.73 (the catalog's gt2-pulley-20t-9mm, MISUMI GPA, and
# gt2-idler-20t-9mm): each strand runs one pitch radius from the pulley's axis.
PITCH_R = 12.73 / 2.0
# MISUMI HFS5 2020: 20 square, 6 mm slot opening, 2 mm lips; Ø4.2 is the hole MISUMI taps
# M5 (the pilot an M5 cuts its thread in).
PROFILE = 20.0
SLOT_LIP_T = 2.0
PILOT_D = 4.2
# ISO 7380-1 M5x10 BHCS (Keller & Kalmbach): d 5, l 10.
SCREW_D = 5.0
SCREW_L = 10.0
# ISO 4762 M3: d 3.
M3_D = 3.0

# ── The neighbours this joint is placed against: merged commons cartridges at their
# defaults; each number is cited or labelled in that cartridge's own README ──────────
# z-drive-housing belt_offset 13 and corner-idler-bracket idler_offset 13: the Z pulley and
# the top idler stand 13 in from the upright's inner face. That face is H = 10 behind this
# frame's origin plane (the MGN9 rail's base sits on it).
BELT_AXIS_X = -BLOCK_H + 13.0
BELT_X = BELT_AXIS_X - PITCH_R              # the anchored (outer) strand: x = −3.365
# z-drive-housing belt_plane 17.5: the belt's mid-plane 17.5 in from the frame's inner face,
# which is half the 20 mm upright from the block's centre along the upright.
BELT_PLANE_Y = PROFILE / 2.0 + 17.5
# z-belt-clamp at its defaults: the belt's wall slot_w / 2 = 1.2 off the clamp's screw axis,
# its mid-width base_t + 4.8 = 8.3 off its mount face, its tongue 2 deep and its body
# ±28.07 along the belt; its M5x10 head seat 4.5 off its mount face.
CLAMP_WALL = 1.2
CLAMP_MID = 8.3
CLAMP_TONGUE = 2.0
CLAMP_HALF_L = 28.07
CLAMP_SEAT = 4.5

# ── Conventions (labelled; not sourced facts) ────────────────────────────────
PLATE_T = 6.0           # the plate on the block
BACKER_Y0 = 10.5        # the backer and web stay 0.5 clear of the block's side (W / 2 = 10)
BACKER_X0 = -BLOCK_H    # the backer reaches back to the upright's inner face plane
BACKER_HALF_H = 28.0    # the backer carries the clamp's full height
CLAMP_FACE_Y = BELT_PLANE_Y - CLAMP_MID     # 19.2: the clamp's mount face
CLAMP_X = BELT_X + CLAMP_WALL               # the clamp's screw axis: x = −2.165
PAD_T = 4.5             # under the C: 10 − 4.5 = 5.5 of the M5x10 into its T-nut
PAD_LEN = 25.0          # the pad reaches 25 along the C from its end
NUT_STATION = 10.0      # the C's T-nut 10 in from its end
TAB_W = 5.8             # tongue in the 6 mm slot (as roller-bracket, z-belt-clamp)
GROOVE_W = 6.0          # groove for the clamp's 5.8 tongue
GROOVE_D = CLAMP_TONGUE + 0.5
GROOVE_HALF_L = CLAMP_HALF_L - 2.0 + 0.5
PILOT_DEPTH = SCREW_L - CLAMP_SEAT + 1.5    # 5.5 of thread plus 1.5 of room
HOLE_CLEAR = 0.25       # Ø5.5 for M5
M3_CLEAR = 0.2          # Ø3.4 for M3
M3_CB_D = 6.5           # M3 socket-head counterbore, 3.5 deep
M3_CB_T = 3.5

# ── Parameters ───────────────────────────────────────────────────────────────
c_inboard = float(PARAM(lambda: c_inboard, 21.0))   # block top face to the C's centre line
c_end = float(PARAM(lambda: c_end, 20.0))           # block centre to the C's end, along y
mirrored = bool(PARAM(lambda: mirrored, False))
target_part = str(PARAM(lambda: target_part, "z_joint"))

c_inboard = max(21.0, min(c_inboard, 45.0))
c_end = max(0.0, min(c_end, 60.0))


def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def _cyl(axis, c, d, a0, a1):
    """A cylinder along `axis` ('x', 'y' or 'z') through point c, from a0 to a1."""
    v = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]
    base = [c[0], c[1], c[2]]
    base["xyz".index(axis)] = a0
    solid = cq.Solid.makeCylinder(d / 2.0, a1 - a0, cq.Vector(*base), cq.Vector(*v))
    return cq.Workplane("XY").add(solid)


def build_joint():
    c_out = c_inboard - PROFILE / 2.0        # the C's outer face
    c_in = c_inboard + PROFILE / 2.0
    pad_y0 = min(c_end, BACKER_Y0)
    pad_y1 = c_end + PAD_LEN
    nut_y = c_end + NUT_STATION

    # The plate on the block, and the backer beside it carrying the clamp face.
    body = _box(0.0, PLATE_T, -BLOCK_W / 2.0, CLAMP_FACE_Y, -BLOCK_L / 2.0, BLOCK_L / 2.0)
    body = body.union(_box(BACKER_X0, PLATE_T, BACKER_Y0, CLAMP_FACE_Y, -BACKER_HALF_H, BACKER_HALF_H))
    # The web from the plate to the C's outer face: below the C, in front of the belt plane.
    body = body.union(_box(0.0, c_out, BACKER_Y0, CLAMP_FACE_Y, -BLOCK_L / 2.0, 0.0))
    # The pad under the C, its top on the C's bottom face (z = 0), flush with the C's sides.
    body = body.union(_box(c_out, c_in, pad_y0, pad_y1, -PAD_T, 0.0))
    # Its tongue in the C's bottom slot.
    body = body.union(_box(c_inboard - TAB_W / 2.0, c_inboard + TAB_W / 2.0, pad_y0 + 1.0, pad_y1 - 1.0,
                           0.0, SLOT_LIP_T))
    # The pad's M5: a clearance hole from below; the BHCS head bears on the pad's underside.
    body = body.cut(_cyl("z", (c_inboard, nut_y, 0), SCREW_D + 2 * HOLE_CLEAR, -PAD_T - 1.0, SLOT_LIP_T + 1.0))
    # Four M3 through the plate into the block, counterbored from the free side.
    for hy in (-HOLE_B / 2.0, HOLE_B / 2.0):
        for hz in (-HOLE_C / 2.0, HOLE_C / 2.0):
            body = body.cut(_cyl("x", (0, hy, hz), M3_D + 2 * M3_CLEAR, -1.0, PLATE_T + 1.0))
            body = body.cut(_cyl("x", (0, hy, hz), M3_CB_D, PLATE_T - M3_CB_T, PLATE_T + 1.0))
    # The clamp: a groove for its tongue along z, and the pilot its M5x10 threads into.
    body = body.cut(_box(CLAMP_X - GROOVE_W / 2.0, CLAMP_X + GROOVE_W / 2.0, CLAMP_FACE_Y - GROOVE_D,
                         CLAMP_FACE_Y + 1.0, -GROOVE_HALF_L, GROOVE_HALF_L))
    body = body.cut(_cyl("y", (CLAMP_X, 0, 0), PILOT_D, CLAMP_FACE_Y - GROOVE_D - PILOT_DEPTH,
                         CLAMP_FACE_Y + 1.0))
    if mirrored:
        body = body.mirror("YZ")
    return body


_dispatch = {"z_joint": build_joint}

result = _dispatch.get(target_part, build_joint)()
