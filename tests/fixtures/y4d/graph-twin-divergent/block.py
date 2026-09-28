"""The CadQuery half of the dual-engine fixture — the SAME solid as block.scad.

Deliberately curve-free: a centred cube's AABB and volume are the same number on both
kernels to full float precision, so a parity pass over this fixture proves the
comparison machinery works rather than measuring tessellation. The divergent twin
(../dual-block-divergent) is where a genuine disagreement is exercised.

Sandbox contract (apps/api/services/engine/cq_runner.py):
  - `cq` and `math` are pre-injected globals.
  - Manifest parameters are injected as BARE globals (e.g. `block_size`).
  - Access them via PARAM(lambda: <name>, <default>). Do NOT use globals()/eval/getattr.
  - Assign the final solid to a top-level name `result`.
"""

import cadquery as cq


def PARAM(getter, default):
    """Return an injected global if present, else the default."""
    try:
        v = getter()
        return default if v is None else v
    except Exception:
        return default


block_size = float(PARAM(lambda: block_size, 10.0))  # cube edge length (mm)
plate_h = float(PARAM(lambda: plate_h, 2.0))  # plate thickness (mm)
target_part = str(PARAM(lambda: target_part, "block"))

if target_part == "plate":
    result = cq.Workplane("XY").box(block_size * 2, block_size * 2, plate_h)
else:
    result = cq.Workplane("XY").box(block_size, block_size, block_size)
