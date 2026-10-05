"""The script half of the graph-format-1.1 golden twin (ring.graph.json).

A test fixture, not a design: a lathe-turned ring with a wedge tab, sized by a
non-numeric select, clamped by derived values and handed by a checkbox. Every Wave D
graph feature has a counterpart here, so --parity proves the expression evaluator,
`select`, `reflect`, `profile_polyline` and the bounded `revolve` reproduce the script
they twin, not merely that they render.

Sandbox contract (apps/api/services/engine/cq_runner.py): parameters arrive as bare
globals, read through PARAM(lambda: <name>, <default>); the solid is `result`.
"""

import cadquery as cq


def PARAM(getter, default):
    """Return an injected global if present, else the default."""
    try:
        v = getter()
        return default if v is None else v
    except Exception:
        return default


size = str(PARAM(lambda: size, "S"))  # S | L
bore = float(PARAM(lambda: bore, 8.0))  # bore diameter (mm)
height = float(PARAM(lambda: height, 5.0))  # ring height (mm)
handed = bool(PARAM(lambda: handed, False))  # mirror the tab to the other side

r_out = 20.0 if size == "L" else 12.0
r_in = max(2.0, min(bore / 2.0, r_out - 2.0))
cx = (r_in + r_out) / 2.0

ring = (
    cq.Workplane("XZ")
    .center(cx, height / 2.0)
    .rect(r_out - r_in, height)
    .revolve(360, (-cx, -height / 2.0), (-cx, -height / 2.0 + 1.0))
)
tab = (
    cq.Workplane("XZ")
    .polyline([(r_out - 1.0, 0.0), (r_out + 6.0, 0.0), (r_out - 1.0, height)])
    .close()
    .extrude(-4.0)
    .translate((0.0, -2.0, 0.0))
)
body = ring.union(tab)
if handed:
    body = body.mirror("YZ")
result = body
