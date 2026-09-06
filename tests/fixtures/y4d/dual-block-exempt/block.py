"""The same deliberately-wrong CadQuery half as ../dual-block-divergent — 0.6mm wide.

The geometry is identical to the divergent twin ON PURPOSE. The only difference
between the two cartridges is the manifest: this one declares the part exempt from the
cross-kernel comparison, with a reason. That is what makes the pair a controlled
experiment for G38 — the same two meshes go in, and the verdict changes because and
only because the manifest said so.

A fixture whose exemption applied to geometry that would have passed anyway would
prove nothing: the exemption has to be load-bearing, or the test cannot tell an
exemption that works from one that never mattered.

Sandbox contract: see ../dual-block/block.py.
"""

import cadquery as cq


def PARAM(getter, default):
    """Return an injected global if present, else the default."""
    try:
        v = getter()
        return default if v is None else v
    except Exception:
        return default


block_size = float(PARAM(lambda: block_size, 10.0))
plate_h = float(PARAM(lambda: plate_h, 2.0))
target_part = str(PARAM(lambda: target_part, "block"))

# The divergence, matching ../dual-block-divergent/block.py exactly.
SHIFT_MM = 0.6

if target_part == "plate":
    result = cq.Workplane("XY").box(block_size * 2, block_size * 2, plate_h)
else:
    result = cq.Workplane("XY").box(block_size + SHIFT_MM, block_size, block_size)
