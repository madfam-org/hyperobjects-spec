"""
Z Drive Housing — Yantra4D Hyperobject Cartridge (CadQuery / B-Rep).

A printed housing that hangs under a bottom corner of a 2020 extrusion frame joined by
blind joints and carries a belt-reduction Z drive: a NEMA 17 motor with a 16-tooth GT2
pulley drives an 80-tooth GT2 pulley through a closed GT2 loop (5:1), on a Ø5 output
shaft turning in three 625 bearings; a 20-tooth 9 mm GT2 pulley on the same shaft drives
the Z belt, which leaves upward through the frame corner to a top-corner idler. It is an
ORIGINAL design built to the functional facts a Voron 2.4-class printer's Z drive states
(Voron 2.4r2 build guide, GPL-3.0, cited by page only): the 5x60 shaft, three 625
bearings, M5 shims, the GT2 80-tooth and 20-tooth 9 mm pulleys (pp. 32–33), the GT2
188 mm loop (p. 34), the 16-tooth motor pulley (p. 38), M5x10 BHCS into M5 T-nuts in the
frame (pp. 41–43), four drives with the printed parts mirrored for two of them (p. 47).
No Voron geometry is copied, traced or derived.

The body is one open box under the corner:
  - a top plate against the frame's bottom faces: two counterbored M5 holes for M5x10
    button head screws into T-nuts in the horizontal's bottom slot, a tongue in that
    slot and a tongue in the perpendicular horizontal's bottom slot, and a slot the Z
    belt rises through;
  - three walls across the output shaft, each with a 625 bearing seat: wall A (frame
    side) and wall B either side of the 20-tooth Z pulley, wall C beyond the 80-tooth
    pulley; wall C's outer face carries the motor (pilot slot and four M3 slots for the
    belt tension);
  - a floor tying the walls, with access holes under the mount screws.

Model frame (the frames in project.json use it): origin on the inside corner line at
the bottom horizontals' slot-centre height; +x along the horizontal the housing mounts
under, away from the corner; +y out of that horizontal's inner face, into the frame; +z
up, the frame's bottom at z = −10. This is the commons corner-idler-bracket's frame at
the bottom corner, so belt_offset and belt_plane equal that bracket's idler_offset and
idler mid-plane and the Z belt runs vertical. `mirrored` builds the opposite hand by
reflecting x.

Sandbox contract (apps/api/services/engine/cq_runner.py):
  - `cq` and `math` are pre-injected globals.
  - Manifest parameters are injected as BARE globals (e.g. `belt_offset`).
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
# 625 bearing (SKF 625-2RS1): 5 × 16 × 5.
BEARING_OD = 16.0
BEARING_W = 5.0
# MISUMI GPA 2GT (2019 MX p. 1340): 20 teeth, 9 mm belt, shape A: L 21, W 13.3
# (the belt centred in W); P.D. 12.73. 16 teeth, 6 mm belt: L 18, W 10.3; P.D. 10.19.
P20_L, P20_W, P20_PD = 21.0, 13.3, 12.73
P16_PD = 10.19
# 80-tooth 2GT pulley (Spool3D listing, 'Small'): overall 18, hub 8; P.D. 50.93 (Gates
# 2MR-80S, 2.005 in).
P80_L, P80_HUB = 18.0, 8.0
P80_PD = 50.93
# Gates 2MR belting: height B 1.52 mm; the Z belt is 9 mm wide (guide p. 111).
BELT_B = 1.52
BELT_WIDTH = 9.0
# NEMA 17 (catalog nema-17-48mm): 31 mm hole square, M3, Ø22 × 2 pilot, 42.3 square.
NEMA_HOLES = 31.0
NEMA_PILOT = 22.0
NEMA_HALF = 42.3 / 2.0
# ISO 7380-1 M5 button head (Keller & Kalmbach 157380510): dk 9.5, k 2.75; M5x10 l 10.
HEAD_DK = 9.5
SCREW_D = 5.0
SCREW_L = 10.0
# 2020 series-5 (MISUMI HFS5): 6 mm slot opening, 2 mm lips; the profile square 20.
SLOT_LIP_T = 2.0
PROFILE = 20.0
# MISUMI HNTAP5-5 post-assembly T-nut: 15 mm long.
TNUT_L = 15.0

# ── Conventions (labelled; not sourced facts) ────────────────────────────────
GAP = 0.5            # axial gap between a pulley's end face and a bearing face
LIP = 1.5            # bearing shoulder behind each pocket
POCKET_CLEAR = 0.1   # per side on the Ø16 bearing pockets: Ø16.2
LIP_HOLE = 10.0      # through the shoulder, clears the inner ring and the shaft
TOP_T = 7.5          # top plate thickness
FLOOR_T = 4.0        # floor thickness
PULLEY_CLEAR = 1.5   # radial room round the 80-tooth flange under the plate and above the floor
HOLE_CLEAR = 0.25    # per side on the M5 clearance holes: Ø5.5
HEAD_CLEAR = 0.5     # per side on the counterbores: Ø10.5
GRIP = 4.5           # mount face to the M5x10 head seat: 10 − 4.5 = 5.5 into the T-nut
TAB_W = 5.8          # tongue width in the 6 mm opening (as roller-bracket)
MOUNT_X1 = 20.0      # first mount screw from the corner plane
M3_CLEAR = 3.4       # motor screw slots
TENSION = 2.0        # motor slot travel each side of center_distance
BELT_SLOT_MARGIN = 1.5
ACCESS_D = 11.0      # floor access hole under each mount screw
EDGE = 4.0
WALL_REACH = 22.0    # walls A, B and the floor reach this far past the shaft axis in x
CORNER_KEY_Y0, CORNER_KEY_Y1 = 2.0, 30.0
SLOT_KEY_X0, SLOT_KEY_X1 = 2.0, 48.0

# ── Parameters ───────────────────────────────────────────────────────────────
belt_offset = float(PARAM(lambda: belt_offset, 13.0))         # output shaft x
belt_plane = float(PARAM(lambda: belt_plane, 17.5))           # Z belt mid-plane y
center_distance = float(PARAM(lambda: center_distance, 40.8))  # 80T ↔ 16T axes
big_pulley_od = float(PARAM(lambda: big_pulley_od, 55.0))     # 80T flange
mount_pitch = float(PARAM(lambda: mount_pitch, 20.0))         # T-nut spacing
mirrored = bool(PARAM(lambda: mirrored, False))               # opposite hand
target_part = str(PARAM(lambda: target_part, "z_drive"))

# ── Derived / clamped ────────────────────────────────────────────────────────
belt_offset = max(10.0, min(belt_offset, 30.0))
belt_plane = max(12.0, min(belt_plane, 29.0))
center_distance = max(38.8, min(center_distance, 42.8))
big_pulley_od = max(50.0, min(big_pulley_od, 60.0))
mount_pitch = max(TNUT_L + 1.0, min(mount_pitch, 30.0))

TOP = -PROFILE / 2.0                       # the frame's bottom face, z = −10
Z = -(10.0 + TOP_T + big_pulley_od / 2.0 + PULLEY_CLEAR)   # output shaft axis
Y = belt_plane
BX = belt_offset
MX = BX + center_distance                  # motor axis x

# Stations along y, relative to the Z belt mid-plane (README "Layout").
A_IN = P20_W / 2.0 + GAP                   # wall A inner face
A_OUT = A_IN + LIP + BEARING_W             # wall A outer face = bearing A face A
B_OPEN = -(P20_L - P20_W / 2.0) - GAP      # wall B bearing opening (+y face)
B_BACK = B_OPEN - BEARING_W - LIP          # wall B −y face
C_OPEN = B_BACK - GAP - P80_L - GAP        # wall C bearing opening (+y face)
C_OUT = C_OPEN - BEARING_W - LIP           # wall C outer face = motor face

floor_top = Z - big_pulley_od / 2.0 - PULLEY_CLEAR
z_bot = floor_top - FLOOR_T
x2 = MOUNT_X1 + mount_pitch
X0 = min(-PROFILE / 2.0 - TAB_W / 2.0 - 1.0, BX - big_pulley_od / 2.0 - 2.0)
X1 = max(x2 + HEAD_DK / 2.0 + HEAD_CLEAR + EDGE, MX + NEMA_HALF + 3.0)
Y0 = Y + C_OUT
Y1 = Y + A_OUT


def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def _cyl_y(x, z, d, y0, y1):
    """A cylinder of diameter d along +y from y0 to y1, axis at (x, z)."""
    solid = cq.Solid.makeCylinder(d / 2.0, y1 - y0, cq.Vector(x, y0, z), cq.Vector(0, 1, 0))
    return cq.Workplane("XY").add(solid)


def _cyl_z(x, y, d, z0, z1):
    """A cylinder of diameter d along +z from z0 to z1, axis at (x, y)."""
    solid = cq.Solid.makeCylinder(d / 2.0, z1 - z0, cq.Vector(x, y, z0), cq.Vector(0, 0, 1))
    return cq.Workplane("XY").add(solid)


def _slot_y(x0, x1, z, d, y0, y1):
    """A slot of width d along x (x0 → x1), cut along +y from y0 to y1, at height z."""
    body = _cyl_y(x0, z, d, y0, y1).union(_cyl_y(x1, z, d, y0, y1))
    return body.union(_box(x0, x1, y0, y1, z - d / 2.0, z + d / 2.0))


def build_z_drive():
    # Top plate (the full footprint), floor, and the three walls (each overlaps the
    # plate and the floor by 0.5 so every join is a real union).
    # Walls A and B and the floor reach WALL_REACH past the shaft; wall C runs the full
    # width, since it carries the motor.
    xr = BX + WALL_REACH
    body = _box(X0, X1, Y0, Y1, TOP - TOP_T, TOP)
    body = body.union(_box(X0, xr, Y0, Y1, z_bot, floor_top))
    for y0, y1, x1 in ((Y + A_IN, Y + A_OUT, xr), (Y + B_BACK, Y + B_OPEN, xr), (Y + C_OUT, Y + C_OPEN, X1)):
        body = body.union(_box(X0, x1, y0, y1, floor_top - 0.5, TOP - TOP_T + 0.5))
    # Tongues: in the mounting horizontal's bottom slot (along x, on y = −10), and in
    # the perpendicular horizontal's bottom slot (along y, on x = −10).
    body = body.union(_box(SLOT_KEY_X0, SLOT_KEY_X1, -PROFILE / 2.0 - TAB_W / 2.0,
                           -PROFILE / 2.0 + TAB_W / 2.0, TOP - 0.5, TOP + SLOT_LIP_T))
    body = body.union(_box(-PROFILE / 2.0 - TAB_W / 2.0, -PROFILE / 2.0 + TAB_W / 2.0,
                           CORNER_KEY_Y0, min(CORNER_KEY_Y1, Y1 - 1.0), TOP - 0.5, TOP + SLOT_LIP_T))
    # The Z belt rises through the plate: both strands of the 20-tooth pulley, ± margin.
    half = P20_PD / 2.0 + BELT_B + BELT_SLOT_MARGIN
    body = body.cut(_box(BX - half, BX + half, Y - BELT_WIDTH / 2.0 - BELT_SLOT_MARGIN,
                         Y + BELT_WIDTH / 2.0 + BELT_SLOT_MARGIN, TOP - TOP_T - 1.0, TOP + 3.0))
    # Mount screws on the horizontal's slot line, counterbored from below, with floor
    # access holes under them.
    for x in (MOUNT_X1, x2):
        body = body.cut(_cyl_z(x, -PROFILE / 2.0, SCREW_D + 2 * HOLE_CLEAR, TOP - TOP_T - 1.0, TOP + 3.0))
        body = body.cut(_cyl_z(x, -PROFILE / 2.0, HEAD_DK + 2 * HEAD_CLEAR, TOP - TOP_T - 1.0, TOP - GRIP))
        body = body.cut(_cyl_z(x, -PROFILE / 2.0, ACCESS_D, z_bot - 1.0, floor_top + 1.0))
    # Bearing seats: a Ø16.2 pocket from each opening face (toward −y), then the shoulder
    # with a Ø10 through-hole.
    for opening in (A_OUT, B_OPEN, C_OPEN):
        body = body.cut(_cyl_y(BX, Z, BEARING_OD + 2 * POCKET_CLEAR,
                               Y + opening - BEARING_W, Y + opening + 1.0))
        body = body.cut(_cyl_y(BX, Z, LIP_HOLE, Y + opening - BEARING_W - LIP - 1.0,
                               Y + opening - BEARING_W + 0.5))
    # Motor on wall C's outer face: the pilot and the four M3 holes as slots along x for
    # the loop tension (± TENSION about center_distance).
    yc0, yc1 = Y + C_OUT - 1.0, Y + C_OPEN + 1.0
    body = body.cut(_slot_y(MX - TENSION, MX + TENSION, Z, NEMA_PILOT + 1.0, yc0, yc1))
    for dz in (-NEMA_HOLES / 2.0, NEMA_HOLES / 2.0):
        for dx in (-NEMA_HOLES / 2.0, NEMA_HOLES / 2.0):
            body = body.cut(_slot_y(MX + dx - TENSION, MX + dx + TENSION, Z + dz, M3_CLEAR, yc0, yc1))
    if mirrored:
        body = body.mirror("YZ")
    return body


_dispatch = {"z_drive": build_z_drive}

result = _dispatch.get(target_part, build_z_drive)()
