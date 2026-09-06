"""A CadQuery half 0.1mm wider than block.scad's cube — inside no band, over gate 1.

0.1mm is chosen to sit in the one place a widened tolerance can actually be tested:

  * ABOVE the 0.05mm faceting band, so the warn tier cannot rescue it and the default
    run FAILS outright at gate 1. A shift inside the band would pass as a faceting
    warn with or without a manifest tolerance, and the fixture would prove nothing.
  * BELOW the volume allowance — 0.99% of 1000mm^3, against the 2% bar — so gate 2
    still passes once gate 1 is widened past it. A larger shift (the divergent twin's
    0.6mm is 5.7%) fails gate 2 no matter what the AABB tolerance says, which is the
    correct behaviour and exactly why widening one gate must not move the others.
  * BELOW the 0.5mm Hausdorff floor, so gate 3 passes: the surfaces really are within
    0.1mm of each other.

So `--parity` alone fails this cartridge and `"tolerance": 0.2` in the manifest turns
it green — the narrow claim the widened-tolerance path is allowed to make.

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

SHIFT_MM = 0.1

if target_part == "plate":
    result = cq.Workplane("XY").box(block_size * 2, block_size * 2, plate_h)
else:
    result = cq.Workplane("XY").box(block_size + SHIFT_MM, block_size, block_size)
