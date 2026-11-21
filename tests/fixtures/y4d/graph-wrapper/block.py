"""A WRAPPER-graph test cartridge (RFC 0067 G-1): this script, and `block.graph.json`, a
graph with one `script` node that runs it.

The script takes one parameter of each kind a commons manifest has — a slider, a select
(a STRING value) and a checkbox (a BOOLEAN) — because the script node's pass-through
binding must hand each to the source with its type unchanged, and must leave an absent
one absent so the script's own fallback applies. A fixture of sliders alone would not
notice a pass-through that turned "chamfer" into a number or True into 1.0.

Sandbox contract (apps/api/services/engine/cq_runner.py): `cq` and `math` are
pre-injected; parameters arrive as BARE globals; the final solid is `result`.
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
finish = str(PARAM(lambda: finish, "square"))  # "square" | "chamfer"
hollow = bool(PARAM(lambda: hollow, False))  # shell the block
target_part = str(PARAM(lambda: target_part, "block"))

if target_part == "plate":
    result = cq.Workplane("XY").box(block_size * 2, block_size * 2, plate_h)
else:
    result = cq.Workplane("XY").box(block_size, block_size, block_size)
    if hollow:
        result = result.faces(">Z").shell(-1.0)
if finish == "chamfer":
    result = result.edges("|Z").chamfer(min(1.0, plate_h / 4))
