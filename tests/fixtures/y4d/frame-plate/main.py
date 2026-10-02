"""Frame Plate — test fixture for the render-time frame gate (ASM-1 §8).

Two parts, dispatched via `target_part`:
  * "plate" — a square plate on z = 0..plate_thick with a 16 x 16 mm M3 clearance
    pattern and a centre bore, so one part carries a planar face (top), a bore
    (centre) and a second planar face (underside).
  * "pin"   — a round flange (z = 0..3) with a shaft standing on it (z = 3..3+pin_len).

Sandbox contract (apps/api/services/engine/cq_runner.py): `cq` and `math` are injected,
manifest parameters arrive as bare globals, read through PARAM(lambda: name, default).
"""

import cadquery as cq


def PARAM(getter, default):
    """Return an injected global if present, else the default."""
    try:
        v = getter()
        return default if v is None else v
    except Exception:
        return default


plate_thick = float(PARAM(lambda: plate_thick, 4.0))
bore_d = float(PARAM(lambda: bore_d, 8.0))
pin_d = float(PARAM(lambda: pin_d, 5.0))
pin_len = float(PARAM(lambda: pin_len, 10.0))
target_part = str(PARAM(lambda: target_part, "plate"))

PLATE_W = 30.0
PATTERN = 16.0
M3_CLEARANCE = 3.2
FLANGE_D = 20.0
FLANGE_T = 3.0

if target_part == "pin":
    flange = cq.Workplane("XY").circle(FLANGE_D / 2.0).extrude(FLANGE_T)
    shaft = cq.Workplane("XY").workplane(offset=FLANGE_T).circle(pin_d / 2.0).extrude(pin_len)
    result = flange.union(shaft)
else:
    result = (
        cq.Workplane("XY")
        .box(PLATE_W, PLATE_W, plate_thick, centered=(True, True, False))
        .faces(">Z")
        .workplane()
        .rect(PATTERN, PATTERN, forConstruction=True)
        .vertices()
        .hole(M3_CLEARANCE)
        .faces(">Z")
        .workplane()
        .hole(bore_d)
    )
