"""
Toolhead Proxy — Yantra4D Hyperobject Cartridge (CadQuery / B-Rep).

A deliberately simple stand-in body for a 3-D printer toolhead, for a machine's digital
twin: it gives the twin something to look at and something for the collision check to
test, and it carries the frame of the nozzle tip. It is a PROXY, NOT A TOOLHEAD: it has no
extruder, hotend, fans or ducts, and nothing here describes a real toolhead's shape.

It exists because the toolhead a Voron 2.4-class printer uses (the StealthBurner) is
GPL-3.0 and kept in a separate manual (Voron 2.4r2 build guide, pp. 146–147), and the
programme's owner decision D3 calls for original proxy bodies instead of upstream files.
No StealthBurner or Voron geometry is copied, traced or derived; no StealthBurner file
or manual was read. Every size below is a labelled CONVENTION, sized to bound a typical
toolhead generously for collision, and adjustable.

The body is one piece, in front of the X carriage's toolhead face, bolted to it by four M3
screws on a 20 mm square (the interface key toolhead-mount-20x20-m3; HIWIN's MGN12H
pattern):
  - a narrow column (band_w wide) from band_top above the mount centre down to body_drop
    below it: the part that passes the gantry's rails, blocks and idlers at the ends of X
    travel, so it is kept narrow (a CONVENTION chosen so a full X travel fits the gantry);
  - a wider cap (body_w) above the column, up to body_top;
  - a round nozzle under the column whose flat end is the nozzle tip.

Model frame (the frames in project.json use it): origin at the centre of the mount
pattern, on the face that bears on the carriage; +x along the X axis the carriage runs
on; +y up; +z forward, away from the carriage, through the body.

Sandbox contract (apps/api/services/engine/cq_runner.py):
  - `cq` and `math` are pre-injected globals.
  - Manifest parameters are injected as BARE globals (e.g. `body_w`).
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
# The mount pattern (key toolhead-mount-20x20-m3): four M3 on a 20 mm square, HIWIN MG
# series MGN12H B 20 × C 20.
HOLE_SPACING = 20.0
M3_CLEAR = 3.4          # Ø3.4 clearance for M3 (house clearance, 0.2 per side)

# ── Conventions (labelled; not sourced facts) ────────────────────────────────
HOLE_DEPTH = 8.0        # blind marks for the pattern; the proxy models no screws
NOZZLE_D = 8.0          # the nozzle's round body
TIP_D = 3.0             # its flat end, the nozzle tip (area 7.1 mm²)
TIP_TAPER = 3.0         # the cone from NOZZLE_D to TIP_D

# ── Parameters (all conventions; see docs/README.md) ─────────────────────────
body_w = float(PARAM(lambda: body_w, 56.0))              # the cap, across X
band_w = float(PARAM(lambda: band_w, 36.0))              # the column, across X
band_top = float(PARAM(lambda: band_top, 1.0))           # column top above the mount centre
body_d = float(PARAM(lambda: body_d, 56.0))              # forward from the mount face
body_top = float(PARAM(lambda: body_top, 25.0))          # above the mount centre
body_drop = float(PARAM(lambda: body_drop, 94.0))        # column bottom below the mount centre
nozzle_drop = float(PARAM(lambda: nozzle_drop, 102.0))   # mount centre to the tip
nozzle_reach = float(PARAM(lambda: nozzle_reach, 12.0))  # mount face to the nozzle axis
target_part = str(PARAM(lambda: target_part, "toolhead_proxy"))

# ── Derived / clamped ────────────────────────────────────────────────────────
body_w = max(30.0, min(body_w, 90.0))
band_w = max(26.0, min(band_w, body_w))
band_top = max(-12.0, min(band_top, body_top - 4.0))
body_d = max(30.0, min(body_d, 90.0))
body_top = max(12.0, min(body_top, 80.0))
body_drop = max(12.0, min(body_drop, 160.0))
nozzle_drop = max(body_drop + TIP_TAPER + 1.0, min(nozzle_drop, 180.0))
nozzle_reach = max(NOZZLE_D / 2.0 + 2.0, min(nozzle_reach, body_d - NOZZLE_D / 2.0 - 2.0))


def _box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def build_proxy():
    body = _box(-band_w / 2.0, band_w / 2.0, -body_drop, band_top + 0.5, 0.0, body_d)
    body = body.union(_box(-body_w / 2.0, body_w / 2.0, band_top, body_top, 0.0, body_d))
    # The nozzle: a round body down from the column, then a short cone to the flat tip.
    straight = nozzle_drop - TIP_TAPER - body_drop
    body = body.union(cq.Workplane("XY").add(cq.Solid.makeCylinder(
        NOZZLE_D / 2.0, straight + 0.5, cq.Vector(0, -body_drop + 0.5, nozzle_reach),
        cq.Vector(0, -1, 0))))
    body = body.union(cq.Workplane("XY").add(cq.Solid.makeCone(
        NOZZLE_D / 2.0, TIP_D / 2.0, TIP_TAPER,
        cq.Vector(0, -(nozzle_drop - TIP_TAPER), nozzle_reach), cq.Vector(0, -1, 0))))
    # The mount pattern, marked by four blind holes from the mount face.
    for sx in (-HOLE_SPACING / 2.0, HOLE_SPACING / 2.0):
        for sy in (-HOLE_SPACING / 2.0, HOLE_SPACING / 2.0):
            body = body.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(
                M3_CLEAR / 2.0, HOLE_DEPTH + 1.0, cq.Vector(sx, sy, -1.0),
                cq.Vector(0, 0, 1))))
    return body


_dispatch = {"toolhead_proxy": build_proxy}

result = _dispatch.get(target_part, build_proxy)()
