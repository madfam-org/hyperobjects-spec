"""Candy-bar handheld: a plain upright slab with a screen above its controls.

A generic device archetype for a viewer that shows a handheld and lets a visitor press
it. It models no product: no outline, logo, glyph or surface detail of any maker's
device is drawn, and the two presets are illustrative sizes, not measurements.

Frame (mm): X across the face, centred. Y up the face, centred. Z through the body,
rear face at z = 0 and the front face at z = body_depth.

Every control is its own part: the screen, four D-pad arms, four face buttons, two
shoulders, two triggers, two sticks with a light ring each, three menu buttons, two
function buttons, power, volume up and down, a slide switch, a port on the bottom edge,
the top edge and the rear, two light bars on the rear, and a land on the rear that a
module bolts to. `body` is the shell, with a seat cut for each control the parameters
switch on (stick_count, shoulder_rows, menu_button_count, function_button_count,
light_bar_count and the *_present switches).

A part's builder does not read those switches: asked for `stick_right`, the script
returns the right stick where it would sit, whatever stick_count says. The manifest's
`device` block says where each control is present, and a mode lists the parts it shows.

Each part is one body. A seat is cut a little wider than the part that sits in it (0.1
to 0.3 mm a side), and every cutter runs 1 mm past the surface it opens, so no cut ends
on a face.

Sandbox: `cq` and `math` are injected, parameters arrive as bare globals, the solid is
`result`.
"""
import math

import cadquery as cq


def PARAM(getter, default):
    """Return an injected global if present, else the default."""
    try:
        value = getter()
        return default if value is None else value
    except Exception:
        return default


def count_value(value, name, top):
    """A count arrives as a float from the configurator; refuse a fraction, never round."""
    if (not isinstance(value, (int, float)) or not math.isfinite(value)
            or value != int(value) or not 0 <= value <= top):
        raise ValueError(f"{name} must be a whole number from 0 to {top}")
    return int(value)


body_width = float(PARAM(lambda: body_width, 88.0))
body_height = float(PARAM(lambda: body_height, 164.0))
body_depth = float(PARAM(lambda: body_depth, 18.0))
corner_radius = float(PARAM(lambda: corner_radius, 10.0))
screen_diagonal = float(PARAM(lambda: screen_diagonal, 3.5))
screen_aspect_w = max(float(PARAM(lambda: screen_aspect_w, 4.0)), 1.0)
screen_aspect_h = max(float(PARAM(lambda: screen_aspect_h, 3.0)), 1.0)
screen_center_y = float(PARAM(lambda: screen_center_y, 44.0))
control_x = float(PARAM(lambda: control_x, 24.0))
control_y = float(PARAM(lambda: control_y, -12.0))
dpad_span = float(PARAM(lambda: dpad_span, 24.0))
dpad_arm = float(PARAM(lambda: dpad_arm, 8.0))
face_button_diameter = float(PARAM(lambda: face_button_diameter, 8.0))
face_button_spread = float(PARAM(lambda: face_button_spread, 9.0))
button_height = float(PARAM(lambda: button_height, 1.4))
button_travel = float(PARAM(lambda: button_travel, 0.6))
stick_count = count_value(
    PARAM(lambda: stick_count, 2), "stick_count", 2)
stick_x = float(PARAM(lambda: stick_x, 22.0))
stick_y = float(PARAM(lambda: stick_y, -46.0))
stick_cap_diameter = float(PARAM(lambda: stick_cap_diameter, 13.0))
stick_height = float(PARAM(lambda: stick_height, 5.0))
stick_tilt = float(PARAM(lambda: stick_tilt, 18.0))
light_ring_present = bool(PARAM(lambda: light_ring_present, True))
light_ring_width = float(PARAM(lambda: light_ring_width, 1.6))
shoulder_rows = count_value(
    PARAM(lambda: shoulder_rows, 2), "shoulder_rows", 2)
shoulder_width = float(PARAM(lambda: shoulder_width, 24.0))
shoulder_inset = float(PARAM(lambda: shoulder_inset, 12.0))
shoulder_thickness = float(PARAM(lambda: shoulder_thickness, 6.0))
menu_button_count = count_value(
    PARAM(lambda: menu_button_count, 3), "menu_button_count", 3)
menu_button_diameter = float(PARAM(lambda: menu_button_diameter, 4.5))
menu_pitch = float(PARAM(lambda: menu_pitch, 12.0))
menu_y = float(PARAM(lambda: menu_y, -70.0))
function_button_count = count_value(
    PARAM(lambda: function_button_count, 2), "function_button_count", 2)
function_x = float(PARAM(lambda: function_x, 34.0))
function_y = float(PARAM(lambda: function_y, 8.0))
side_button_length = float(PARAM(lambda: side_button_length, 9.0))
side_button_y = float(PARAM(lambda: side_button_y, 40.0))
slide_switch_present = bool(PARAM(lambda: slide_switch_present, True))
slide_switch_throw = float(PARAM(lambda: slide_switch_throw, 3.0))
port_bottom_present = bool(PARAM(lambda: port_bottom_present, True))
port_top_present = bool(PARAM(lambda: port_top_present, True))
port_rear_present = bool(PARAM(lambda: port_rear_present, True))
port_width = float(PARAM(lambda: port_width, 9.0))
port_height = float(PARAM(lambda: port_height, 3.2))
port_rear_y = float(PARAM(lambda: port_rear_y, -62.0))
light_bar_count = count_value(
    PARAM(lambda: light_bar_count, 2), "light_bar_count", 2)
light_bar_length = float(PARAM(lambda: light_bar_length, 40.0))
light_bar_width = float(PARAM(lambda: light_bar_width, 3.0))
light_bar_y = float(PARAM(lambda: light_bar_y, 62.0))
rear_mount_present = bool(PARAM(lambda: rear_mount_present, True))
rear_mount_width = float(PARAM(lambda: rear_mount_width, 44.0))
rear_mount_height = float(PARAM(lambda: rear_mount_height, 30.0))
rear_mount_y = float(PARAM(lambda: rear_mount_y, 14.0))
rear_mount_hole = float(PARAM(lambda: rear_mount_hole, 2.7))
target_part = str(PARAM(lambda: target_part, "body"))

W, H, D = body_width, body_height, body_depth
GAP = 0.3    # clearance between a control and its seat, each side
OVER = 1.0   # how far a cutter runs past the surface it opens
SEAT = button_travel + 0.4          # depth of a face button's seat
STICK_SEAT = 1.2                    # depth of the dish a stick stands in
EDGE_SEAT, EDGE_PROUD = 2.0, 1.5    # a shoulder: let into the top edge, proud of it
SIDE_SEAT, SIDE_PROUD = 1.5, 0.8    # a side button: let into the side, proud of it
INSET = 1.0                         # depth of a port mouth, a light bar seat, the mount seat
SIDE_T = min(3.0, max(D - 2.0, 1.0))                  # a side button, through the body
EDGE_T = min(shoulder_thickness, max(D - 2.0, 1.0))   # a shoulder, through the body
PORT_T = min(port_height, max(D - 2.0, 1.0))          # an edge port, through the body

_diag = math.hypot(screen_aspect_w, screen_aspect_h)
SCREEN_W = screen_diagonal * 25.4 * screen_aspect_w / _diag
SCREEN_H = screen_diagonal * 25.4 * screen_aspect_h / _diag
ARM = max((dpad_span - dpad_arm) / 2.0, 1.0)          # length of one D-pad arm
STICK_R = stick_cap_diameter / 2.0
WELL_R = STICK_R + (stick_height + STICK_SEAT) * math.tan(math.radians(stick_tilt)) + GAP
RING_IN = WELL_R + 0.8
SWITCH_Y = side_button_y - side_button_length / 2.0 - 5.0 - (slide_switch_throw + 4.0) / 2.0
BAR_LOWER_Y = light_bar_y - light_bar_width - 4.0


def box(cx, cy, z0, sx, sy, sz):
    """A box centred on (cx, cy), from z0 up."""
    return (cq.Workplane("XY").box(sx, sy, sz, centered=(True, True, False))
            .translate((cx, cy, z0)))


def cyl(cx, cy, z0, r, h):
    return cq.Workplane("XY").circle(r).extrude(h).translate((cx, cy, z0))


def ring(cx, cy, z0, r_in, r_out, h):
    return cq.Workplane("XY").circle(r_out).circle(r_in).extrude(h).translate((cx, cy, z0))


# ── face controls: a plunger in a seat, (shape, cx, cy, sx, sy) ──────────────────────
PLUNGERS = {
    "dpad_up": ("box", -control_x, control_y + dpad_arm / 2 + ARM / 2, dpad_arm, ARM),
    "dpad_down": ("box", -control_x, control_y - dpad_arm / 2 - ARM / 2, dpad_arm, ARM),
    "dpad_left": ("box", -control_x - dpad_arm / 2 - ARM / 2, control_y, ARM, dpad_arm),
    "dpad_right": ("box", -control_x + dpad_arm / 2 + ARM / 2, control_y, ARM, dpad_arm),
    "button_south": ("cyl", control_x, control_y - face_button_spread, face_button_diameter, 0),
    "button_east": ("cyl", control_x + face_button_spread, control_y, face_button_diameter, 0),
    "button_west": ("cyl", control_x - face_button_spread, control_y, face_button_diameter, 0),
    "button_north": ("cyl", control_x, control_y + face_button_spread, face_button_diameter, 0),
    "menu_left": ("cyl", -menu_pitch, menu_y, menu_button_diameter, 0),
    "menu_center": ("cyl", 0.0, menu_y, menu_button_diameter, 0),
    "menu_right": ("cyl", menu_pitch, menu_y, menu_button_diameter, 0),
    "function_left": ("cyl", -function_x, function_y, menu_button_diameter, 0),
    "function_right": ("cyl", function_x, function_y, menu_button_diameter, 0),
}


def plunger(name, grow=0.0, top=None):
    shape, cx, cy, sx, sy = PLUNGERS[name]
    height = (SEAT + button_height) if top is None else top
    if shape == "cyl":
        return cyl(cx, cy, D - SEAT, sx / 2 + grow, height)
    return box(cx, cy, D - SEAT, sx + 2 * grow, sy + 2 * grow, height)


def dpad_seat():
    """One cross-shaped seat for the four arms, with the hub left standing in it."""
    reach = dpad_arm + 2 * ARM + 2 * GAP
    cross = box(-control_x, control_y, D - SEAT, reach, dpad_arm + 2 * GAP, SEAT + OVER).union(
        box(-control_x, control_y, D - SEAT, dpad_arm + 2 * GAP, reach, SEAT + OVER))
    hub = max(dpad_arm - 2 * GAP, 1.0)
    return cross.cut(box(-control_x, control_y, D - SEAT - OVER, hub, hub, SEAT + 3 * OVER))


# ── sticks and their light rings ─────────────────────────────────────────────────────
def stick(side):
    cx = side * stick_x
    stem = cyl(cx, stick_y, D - STICK_SEAT, STICK_R * 0.45, STICK_SEAT + stick_height - 0.6)
    return stem.union(cyl(cx, stick_y, D + stick_height - 2.0, STICK_R, 2.0))


def light_ring(side, grow=0.0, top=0.8):
    return ring(side * stick_x, stick_y, D - 0.6, RING_IN - grow,
                RING_IN + light_ring_width + grow, top)


# ── the top edge: shoulders near the face, triggers near the rear ────────────────────
def edge_button(side, z0, grow=0.0, proud=EDGE_PROUD):
    cx = side * (W / 2 - shoulder_inset - shoulder_width / 2)
    depth = EDGE_SEAT + proud
    return box(cx, H / 2 - EDGE_SEAT + depth / 2, z0 - grow,
               shoulder_width + 2 * grow, depth, EDGE_T + 2 * grow)


SHOULDER_Z, TRIGGER_Z = D - 1.0 - EDGE_T, 1.0


# ── the sides: power and the slide switch on +X, volume on -X ────────────────────────
def side_button(side, cy, length, thick, seat, proud, grow=0.0):
    depth = seat + proud
    cx = side * (W / 2 - seat + depth / 2)
    return box(cx, cy, D / 2 - thick / 2 - grow, depth, length + 2 * grow, thick + 2 * grow)


VOLUME_DY = side_button_length / 2 + 1.0
SWITCH_T = min(2.4, max(D - 2.0, 1.0))


def switch_knob():
    return side_button(1, SWITCH_Y + slide_switch_throw / 2, 4.0, SWITCH_T, 1.2, 1.0)


def switch_slot():
    return side_button(1, SWITCH_Y, 4.0 + slide_switch_throw, SWITCH_T, 1.2, OVER, GAP)


# ── ports, light bars and the module mount ───────────────────────────────────────────
def edge_port(side):
    """A port mouth in the bottom (side -1) or top (side +1) edge, set back 0.3 mm."""
    return box(0.0, side * (H / 2 - 0.3 - INSET / 2), D / 2 - PORT_T / 2,
               port_width, INSET, PORT_T)


def edge_port_seat(side):
    depth = 0.3 + INSET + OVER
    return box(0.0, side * (H / 2 - 0.3 - INSET + depth / 2), D / 2 - PORT_T / 2 - 0.1,
               port_width + 0.2, depth, PORT_T + 0.2)


def rear_slab(cy, sx, sy, z0, sz, grow=0.0):
    return box(0.0, cy, z0, sx + 2 * grow, sy + 2 * grow, sz)


def rear_mount():
    """A land proud of the rear with four clearance holes for a module's screws."""
    plate = rear_slab(rear_mount_y, rear_mount_width, rear_mount_height, -2.0, 2.0 + INSET)
    inset = min(4.0, rear_mount_width / 4, rear_mount_height / 4)
    for sx in (-1, 1):
        for sy in (-1, 1):
            plate = plate.cut(cyl(sx * (rear_mount_width / 2 - inset),
                                  rear_mount_y + sy * (rear_mount_height / 2 - inset),
                                  -2.0 - OVER, rear_mount_hole / 2, 2.0 + INSET + 2 * OVER))
    return plate


# ── which seats the body carries ─────────────────────────────────────────────────────
def present(name):
    if name in ("stick_left", "stick_right"):
        return stick_count >= (1 if name.endswith("left") else 2)
    if name in ("light_ring_left", "light_ring_right"):
        return light_ring_present and present("stick" + name[len("light_ring"):])
    if name.startswith("shoulder_"):
        return shoulder_rows >= 1
    if name.startswith("trigger_"):
        return shoulder_rows >= 2
    if name == "menu_center":
        return menu_button_count == 1 or menu_button_count >= 3
    if name in ("menu_left", "menu_right"):
        return menu_button_count >= 2
    if name in ("function_left", "function_right"):
        return function_button_count >= (1 if name.endswith("left") else 2)
    if name in ("light_bar_upper", "light_bar_lower"):
        return light_bar_count >= (1 if name.endswith("upper") else 2)
    switches = {"slide_switch": slide_switch_present, "port_bottom": port_bottom_present,
                "port_top": port_top_present, "port_rear": port_rear_present,
                "rear_mount": rear_mount_present}
    return switches.get(name, True)


def seats():
    """The cutters that open the body, one per present control."""
    yield box(0.0, screen_center_y, D - 0.8, SCREEN_W + 2 * GAP, SCREEN_H + 2 * GAP, 0.8 + OVER)
    yield dpad_seat()
    for name in PLUNGERS:
        if not name.startswith("dpad_") and present(name):
            yield plunger(name, GAP, SEAT + OVER)
    for side, tag in ((-1, "left"), (1, "right")):
        if present("stick_" + tag):
            yield cyl(side * stick_x, stick_y, D - STICK_SEAT, WELL_R, STICK_SEAT + OVER)
        if present("light_ring_" + tag):
            yield light_ring(side, 0.15, 0.6 + OVER)
        if present("shoulder_" + tag):
            yield edge_button(side, SHOULDER_Z, GAP, OVER)
        if present("trigger_" + tag):
            yield edge_button(side, TRIGGER_Z, GAP, OVER)
    yield side_button(1, side_button_y, side_button_length, SIDE_T, SIDE_SEAT, OVER, GAP)
    for dy in (VOLUME_DY, -VOLUME_DY):
        yield side_button(-1, side_button_y + dy, side_button_length, SIDE_T, SIDE_SEAT, OVER, GAP)
    if present("slide_switch"):
        yield switch_slot()
    if present("port_bottom"):
        yield edge_port_seat(-1)
    if present("port_top"):
        yield edge_port_seat(1)
    if present("port_rear"):
        yield rear_slab(port_rear_y, port_width, port_height, -OVER, 0.3 + INSET + OVER, 0.1)
    for name, cy in (("light_bar_upper", light_bar_y), ("light_bar_lower", BAR_LOWER_Y)):
        if present(name):
            yield rear_slab(cy, light_bar_length, light_bar_width, -OVER, 0.8 + OVER, 0.15)
    if present("rear_mount"):
        yield rear_slab(rear_mount_y, rear_mount_width, rear_mount_height, -OVER,
                        INSET + OVER, 0.15)


def body():
    shell = cq.Workplane("XY").box(W, H, D, centered=(True, True, False))
    radius = min(corner_radius, min(W, H) / 2 - 0.5)
    if radius > 0.2:
        shell = shell.edges("|Z").fillet(radius)
    for cutter in seats():
        shell = shell.cut(cutter)
    return shell


PARTS = {
    "body": body,
    "rear_mount": rear_mount,
    "screen": lambda: box(0.0, screen_center_y, D - 0.8, SCREEN_W, SCREEN_H, 1.0),
    "stick_left": lambda: stick(-1),
    "stick_right": lambda: stick(1),
    "light_ring_left": lambda: light_ring(-1),
    "light_ring_right": lambda: light_ring(1),
    "shoulder_left": lambda: edge_button(-1, SHOULDER_Z),
    "shoulder_right": lambda: edge_button(1, SHOULDER_Z),
    "trigger_left": lambda: edge_button(-1, TRIGGER_Z),
    "trigger_right": lambda: edge_button(1, TRIGGER_Z),
    "power_button": lambda: side_button(1, side_button_y, side_button_length, SIDE_T,
                                        SIDE_SEAT, SIDE_PROUD),
    "volume_up": lambda: side_button(-1, side_button_y + VOLUME_DY, side_button_length,
                                     SIDE_T, SIDE_SEAT, SIDE_PROUD),
    "volume_down": lambda: side_button(-1, side_button_y - VOLUME_DY, side_button_length,
                                       SIDE_T, SIDE_SEAT, SIDE_PROUD),
    "slide_switch": switch_knob,
    "port_bottom": lambda: edge_port(-1),
    "port_top": lambda: edge_port(1),
    "port_rear": lambda: rear_slab(port_rear_y, port_width, port_height, 0.3, INSET),
    "light_bar_upper": lambda: rear_slab(light_bar_y, light_bar_length, light_bar_width,
                                         -0.2, 1.0),
    "light_bar_lower": lambda: rear_slab(BAR_LOWER_Y, light_bar_length, light_bar_width,
                                         -0.2, 1.0),
}
for _name in PLUNGERS:
    PARTS[_name] = lambda n=_name: plunger(n)

if target_part not in PARTS:
    raise ValueError("Unknown target_part: " + target_part)
result = PARTS[target_part]()
