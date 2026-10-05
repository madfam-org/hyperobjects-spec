"""
X Carriage — Yantra4D Hyperobject Cartridge (CadQuery / B-Rep).

A printed X carriage for a CoreXY gantry whose two belts run stacked on two levels (a
Voron 2.4-class "flying gantry"). It bolts to an MGN12H block on the X rail, holds the four
ends of the two belts (A and B) with no screws on the belt, and presents a face a toolhead
(or the commons toolhead-proxy) bolts to. It is an ORIGINAL design built to functional facts
cited by page from the Voron 2.4r2 build guide (GPL-3.0; p. 101: the X axis runs on an
MGN12 rail; p. 131: both 6 mm A/B belts are clamped in the X carriage; p. 141: both belt
ends are pulled tight at the carriage) and from datasheets. No Voron geometry is copied,
traced or derived: the Voron clamps the belt ends under screwed printed parts; this
carriage folds each end teeth-to-teeth round a post (the commons z-belt-clamp's principle).

The body is one piece:
  - a front plate on the MGN12H block (four M3 screws, HIWIN B 20 × C 20), whose front face
    is the toolhead face (four M3 heat-set inserts on a 20 mm square);
  - a tower that reaches back from the plate over the block and the X beam to the belt line,
    carrying four jaws: at each belt level, one jaw at +x for the end coming from +x and one
    at −x for the end coming from −x. A jaw is a slot two belt plies wide running in from
    the tower's end face to a round pocket with a post. The belt end goes down the slot,
    round the post and back beside itself, so the plies lock tooth into tooth and the belt's
    pull tightens the fold. The upper level's jaws open upward, the lower level's downward
    (into a window under the tower), so each fold is put in from outside.

Where the belts are is the gantry's business, so it is all parameters: the belt line's
depth behind the block face, each belt's level above the block centre, the jaws' x, and
which way the teeth face. The defaults are the commons gantry's (lane P6-GANTRY, round 2).

Model frame (the frames in project.json use it): origin at the centre of the MGN12H block's
top face (the carriage's mount face); +x along the rail; +y up; +z out of the block face,
toward the toolhead. The belt line is at z = −belt_line; the X beam is behind the block.

Sandbox contract (apps/api/services/engine/cq_runner.py):
  - `cq` and `math` are pre-injected globals.
  - Manifest parameters are injected as BARE globals (e.g. `belt_line`).
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
# HIWIN MG series, MGN12H: W 27, L 45.4, B 20 × C 20, M3x3.5; H 13 on a 12 × 8 rail. On a
# 2020 face (MISUMI HFS5) with the rail centred, the block's top edge stands 3.5 above the
# beam's top face: 27 / 2 = 13.5 against 10.
BLOCK_HALF_L = 45.4 / 2.0
BLOCK_HALF_W = 27.0 / 2.0
HOLE_PITCH = 20.0
# Gates PowerGrip GT2 2MR (Pfeifer 2MR/PGGT2): belt height B 1.52, tooth height T 0.76;
# SDP/SI Table 4: U 0.254. The pitch line lies B − T − U = 0.506 inside the back face.
BELT_B = 1.52
BELT_T = 0.76
BACK_OFFSET = 1.52 - 0.76 - 0.254
BELT_WIDTH = 6.0            # the A/B belts (guide p. 131)
# ISO 4762 M3 socket head: dk 5.5, k 3 (Keller & Kalmbach).
M3_CLEAR = 3.4              # house clearance, 0.2 per side
M3_CB_D, M3_CB_DEPTH = 6.5, 3.5

# ── Conventions (labelled; not sourced facts) ────────────────────────────────
WIDTH_CLEAR = 0.3           # each side of the belt's width in a slot
PLY_CLEAR = 0.3             # radial room for one ply round the post
RIB = 2.4                   # material between the two belt levels' slots
TOP_WALL = 1.2              # over the upper slot's clearance
TOWER_GAP = 1.0             # tower underside above the block's top edge
REAR_WALL = 2.5             # behind the pockets
PLATE_HALF_W = BLOCK_HALF_L + 0.5   # the plate covers the block's length, +0.5
PLATE_BOTTOM = -(BLOCK_HALF_W + 8.5)
INSERT_D, INSERT_DEPTH = 4.0, 6.0   # M3 heat-set insert holes (the guide's X carriage
                                    # takes heat-set inserts, p. 129; size a convention)

# ── Parameters ───────────────────────────────────────────────────────────────
belt_line = float(PARAM(lambda: belt_line, 23.0))        # block face to the pitch line
belt_a_level = float(PARAM(lambda: belt_a_level, 38.0))  # A belt mid-plane, above block centre
belt_b_level = float(PARAM(lambda: belt_b_level, 22.0))  # B belt mid-plane
clamp_x = float(PARAM(lambda: clamp_x, 20.0))            # jaw entrances at ±clamp_x
teeth_toward_toolhead = bool(PARAM(lambda: teeth_toward_toolhead, False))
jaw_length = float(PARAM(lambda: jaw_length, 12.0))      # entrance to post axis
post_d = float(PARAM(lambda: post_d, 5.0))
slot_w = float(PARAM(lambda: slot_w, 2.4))               # two plies, tooth in tooth
plate_t = float(PARAM(lambda: plate_t, 8.0))
toolhead_y = float(PARAM(lambda: toolhead_y, 30.0))      # toolhead pattern centre height
toolhead_y = max(26.0, min(toolhead_y, 40.0))
target_part = str(PARAM(lambda: target_part, "x_carriage"))

# ── Derived / clamped ────────────────────────────────────────────────────────
belt_line = max(15.0, min(belt_line, 40.0))
belt_a_level = max(22.0, min(belt_a_level, 70.0))
belt_b_level = max(22.0, min(belt_b_level, 70.0))
clamp_x = max(12.0, min(clamp_x, 30.0))
jaw_length = max(6.0, min(jaw_length, 16.0))
post_d = max(4.0, min(post_d, 8.0))
slot_w = max(2.0 * BELT_B - BELT_T, min(slot_w, 3.2))
plate_t = max(6.0, min(plate_t, 14.0))

HALF_H = BELT_WIDTH / 2.0 + WIDTH_CLEAR          # a slot's half-height (3.3)
LO, HI = min(belt_a_level, belt_b_level), max(belt_a_level, belt_b_level)
TOP = HI + HALF_H + TOP_WALL
PLATE_TOP = max(TOP, toolhead_y + HOLE_PITCH / 2.0 + INSERT_D / 2.0 + 2.0)  # covers the toolhead pattern
FLOOR = BLOCK_HALF_W + TOWER_GAP                  # tower underside (14.5)
POCKET_D = post_d + 2.0 * (BELT_B + PLY_CLEAR)
X_POST = clamp_x - jaw_length
# The belt's back bears on one slot wall; its pitch line is BACK_OFFSET off that wall.
_back = -1.0 if teeth_toward_toolhead else 1.0    # +1: the back faces the toolhead (+z)
Z_WALL = -belt_line + _back * BACK_OFFSET
Z_SLOT = Z_WALL - _back * slot_w / 2.0            # slot centreline
Z_REAR = min(Z_SLOT - POCKET_D / 2.0, Z_WALL - _back * slot_w) - REAR_WALL
Z_FRONT_OF_POCKETS = max(Z_SLOT + POCKET_D / 2.0, Z_WALL)


def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def _cyl(axis, x, y, z, d, length):
    direction = {"y": cq.Vector(0, 1, 0), "z": cq.Vector(0, 0, 1)}[axis]
    solid = cq.Solid.makeCylinder(d / 2.0, length, cq.Vector(x, y, z), direction)
    return cq.Workplane("XY").add(solid)


def _jaw(body, sign, y0, y1):
    """A slot from the end face at x = sign·clamp_x to a pocket round a post, over y0..y1."""
    xe, xp = sign * (clamp_x + 1.0), sign * X_POST
    xs = xp + sign * post_d / 2.0     # the slot stops at the post; the pocket does the rest
    zs0, zs1 = sorted((Z_WALL, Z_WALL - _back * slot_w))
    body = body.cut(_box(min(xs, xe), max(xs, xe), y0, y1, zs0, zs1))
    pocket = _cyl("y", xp, y0, Z_SLOT, POCKET_D, y1 - y0).cut(
        _cyl("y", xp, y0 - 1.0, Z_SLOT, post_d, y1 - y0 + 2.0))
    return body.cut(pocket)


def build_carriage():
    # Front plate on the block; its front face (z = plate_t) is the toolhead face.
    body = _box(-PLATE_HALF_W, PLATE_HALF_W, PLATE_BOTTOM, PLATE_TOP, 0.0, plate_t)
    # Tower: back from the plate over the block and the beam to behind the pockets.
    body = body.union(_box(-clamp_x, clamp_x, FLOOR, TOP, Z_REAR, 0.5))
    # Window under the lower level's jaws (front of it and a middle rib stay), so the lower
    # folds go in from below.
    rib_half = X_POST - POCKET_D / 2.0
    for sign in (1.0, -1.0):
        x0, x1 = sorted((sign * rib_half, sign * (clamp_x + 1.0)))
        body = body.cut(_box(x0, x1, FLOOR - 1.0, LO - HALF_H,
                             Z_REAR - 1.0, Z_FRONT_OF_POCKETS + 1.0))
    # Jaws: the lower level open downward, the upper level open upward.
    for sign in (1.0, -1.0):
        body = _jaw(body, sign, LO - HALF_H - 0.5, LO + HALF_H)
        body = _jaw(body, sign, HI - HALF_H, TOP + 1.0)
    # MGN12H screws: clearance through the plate, counterbored from the front.
    for sx in (-HOLE_PITCH / 2.0, HOLE_PITCH / 2.0):
        for sy in (-HOLE_PITCH / 2.0, HOLE_PITCH / 2.0):
            body = body.cut(_cyl("z", sx, sy, -1.0, M3_CLEAR, plate_t + 2.0))
            body = body.cut(_cyl("z", sx, sy, plate_t - M3_CB_DEPTH, M3_CB_D, M3_CB_DEPTH + 1.0))
    # Toolhead face: four M3 heat-set insert holes on a 20 mm square.
    for sx in (-HOLE_PITCH / 2.0, HOLE_PITCH / 2.0):
        for sy in (-HOLE_PITCH / 2.0, HOLE_PITCH / 2.0):
            body = body.cut(_cyl("z", sx, toolhead_y + sy, plate_t - INSERT_DEPTH,
                                 INSERT_D, INSERT_DEPTH + 1.0))
    return body


_dispatch = {"x_carriage": build_carriage}

result = _dispatch.get(target_part, build_carriage)()
