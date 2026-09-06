"""The DELIBERATELY WRONG CadQuery half — 0.6mm larger in X than block.scad's cube.

This fixture exists to prove `--parity` FAILS when it should. A cartridge whose two
kernels model different solids passes both halves of the mesh bar — each side is
watertight, positive-volume, single-body — and so goes green on `--render` alone. It
is exactly the class of defect parity exists to catch, and a gate nothing ever
exercises in the failing direction is a gate nobody can trust.

0.6mm is chosen to clear the 0.05mm faceting band by an order of magnitude, so the
failure is unambiguously gate 1 refusing outright and not the warn tier declining to
rescue it. The same delta also carries the volume past 2%, so the pair would fail even
if the AABB gate were widened.

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

# The divergence. Everything else is ../dual-block/block.py verbatim.
SHIFT_MM = 0.6

if target_part == "plate":
    result = cq.Workplane("XY").box(block_size * 2, block_size * 2, plate_h)
else:
    result = cq.Workplane("XY").box(block_size + SHIFT_MM, block_size, block_size)
