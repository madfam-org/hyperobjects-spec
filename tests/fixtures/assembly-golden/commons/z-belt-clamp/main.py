"""
Z Belt Clamp — Yantra4D Hyperobject Cartridge (CadQuery / B-Rep).

A printed clamp that holds both ends of a 9 mm GT2 Z belt on a gantry built from 2020
extrusion, with no screws on the belt. It is an ORIGINAL design built to the functional
facts a Voron 2.4-class printer's gantry states (Voron 2.4r2 build guide, GPL-3.0, cited
by page only): each Z belt is a 9 mm GT2 belt whose two ends are clamped on the gantry,
one coming down from the top-corner idler and one coming up from the Z drive (pp. 111,
117–121). No Voron geometry is copied, traced or derived: the Voron clamps the belt with
serrations under a screwed part; this clamp folds each end teeth-to-teeth round a post.

The body is one block on a 2020 face:
  - an M5 hole counterbored from the outer face, for an M5x10 button head screw into a
    T-nut in the extrusion's slot, and a tongue along that slot;
  - two jaws, one at each end, on one line: a slot from the end face, as wide as two belt
    plies folded teeth into teeth, running into a round pocket with a post. The belt end
    goes down the slot, round the post and back up the slot beside itself; the two plies
    interlock tooth in tooth and the pull on the belt tightens the fold.

The block is symmetric about its slot line, so either wall can take the belt's back;
the clamp's two belt interfaces are framed on the −y wall (y = −w/2) at the jaw
entrances, at the belt's mid-width. Turned 180° about z on its slot (the tongue's
symmetry), the clamp presents the other wall and swaps its upper and lower jaws.

Model frame (the frames in project.json use it): origin on the mount face on the screw
axis; +x along the belt (the slot line), +y across it, +z out of the extrusion face
through the block.

Sandbox contract (apps/api/services/engine/cq_runner.py):
  - `cq` and `math` are pre-injected globals.
  - Manifest parameters are injected as BARE globals (e.g. `jaw_length`).
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
# Gates PowerGrip GT 2MR belting (design manual 17195, p. 90): height B 1.52, tooth
# height T 0.76; the Z belt is 9 mm wide (guide p. 111).
BELT_B = 1.52
BELT_T = 0.76
BELT_WIDTH = 9.0
# ISO 7380-1 M5x10 button head (Keller & Kalmbach 157380510): d 5, l 10, dk 9.5.
SCREW_D = 5.0
HEAD_DK = 9.5
# 2020 series-5 (MISUMI HFS5): 6 mm opening, 2 mm lips.
SLOT_LIP_T = 2.0

# ── Conventions (labelled; not sourced facts) ────────────────────────────────
WIDTH_CLEAR = 0.3     # each side of the belt's width in the slot depth
PLY_CLEAR = 0.3       # radial room for one ply round the post
HOLE_CLEAR = 0.25     # Ø5.5 clearance hole
HEAD_CLEAR = 0.5      # Ø10.5 counterbore
GRIP = 4.5            # mount face to the head seat: 10 − 4.5 = 5.5 into the T-nut
TAB_W = 5.8           # tongue width in the 6 mm opening (as roller-bracket)
MID_HALF = 7.25       # half the solid middle that carries the screw
WALL = 2.0            # material between the middle and a pocket, and round the pockets
SIDE_WALL = 3.0       # beyond the pocket across y

# ── Parameters ───────────────────────────────────────────────────────────────
jaw_length = float(PARAM(lambda: jaw_length, 14.0))    # slot, end face to post axis
post_d = float(PARAM(lambda: post_d, 6.0))             # post the belt folds round
slot_w = float(PARAM(lambda: slot_w, 2.4))             # two plies, tooth in tooth
base_t = float(PARAM(lambda: base_t, 3.5))             # floor under the slots
target_part = str(PARAM(lambda: target_part, "z_belt_clamp"))

# ── Derived / clamped ────────────────────────────────────────────────────────
jaw_length = max(10.0, min(jaw_length, 24.0))
post_d = max(4.0, min(post_d, 10.0))
slot_w = max(2.0 * BELT_B - BELT_T, min(slot_w, 3.2))
base_t = max(2.5, min(base_t, 8.0))

DEPTH = base_t + BELT_WIDTH + 2.0 * WIDTH_CLEAR          # z extent of the block
pocket_d = post_d + 2.0 * (BELT_B + PLY_CLEAR)
x_post = MID_HALF + WALL + pocket_d / 2.0                 # each post's distance from the axis
HALF_L = x_post + jaw_length                              # end faces at ±HALF_L
HALF_W = pocket_d / 2.0 + SIDE_WALL


def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def _cyl_z(x, y, d, z0, z1):
    solid = cq.Solid.makeCylinder(d / 2.0, z1 - z0, cq.Vector(x, y, z0), cq.Vector(0, 0, 1))
    return cq.Workplane("XY").add(solid)


def build_clamp():
    body = _box(-HALF_L, HALF_L, -HALF_W, HALF_W, 0.0, DEPTH)
    # Tongue along the extrusion's slot (x), under the mount face.
    body = body.union(_box(-HALF_L + 2.0, HALF_L - 2.0, -TAB_W / 2.0, TAB_W / 2.0, -SLOT_LIP_T, 0.5))
    # The mount screw: clearance through, counterbored from the outer face to the seat.
    body = body.cut(_cyl_z(0.0, 0.0, SCREW_D + 2 * HOLE_CLEAR, -SLOT_LIP_T - 1.0, DEPTH + 1.0))
    body = body.cut(_cyl_z(0.0, 0.0, HEAD_DK + 2 * HEAD_CLEAR, GRIP, DEPTH + 1.0))
    # The jaws: a slot from each end face into a round pocket round a post. Slots and
    # pockets are cut from the outer face down to the floor at base_t, so the belt goes
    # in from above; the posts are left standing on the floor.
    for sign in (1.0, -1.0):
        xp = sign * x_post
        xe = sign * (HALF_L + 1.0)
        body = body.cut(_box(min(xp, xe), max(xp, xe), -slot_w / 2.0, slot_w / 2.0, base_t, DEPTH + 1.0))
        pocket = _cyl_z(xp, 0.0, pocket_d, base_t, DEPTH + 1.0).cut(
            _cyl_z(xp, 0.0, post_d, base_t - 1.0, DEPTH + 2.0))
        body = body.cut(pocket)
    return body


_dispatch = {"z_belt_clamp": build_clamp}

result = _dispatch.get(target_part, build_clamp)()
