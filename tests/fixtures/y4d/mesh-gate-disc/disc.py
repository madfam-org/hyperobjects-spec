"""The mesh gate's fixture (y4d_spec.mesh_gate, rulings M4–M7): three parts, three verdicts.

  * `disc` — a 200 mm radius disc. CadQuery's print tolerance gives every circle 126
    segments, which on this radius is a chord error of 200 × (1 − cos(π/126)) ≈ 0.062 mm,
    over the gate's 0.05 mm: the `chord-error` finding the proposal predicted above a
    radius of about 161 mm.
  * `ring` — the same over-limit rim (180 mm, ≈ 0.056 mm), EXEMPT in the manifest with a
    reason, so the opt-out is exercised on a finding that would otherwise be reported.
  * `knob` — a 12-sided prism drawn with `polygon(12, …)`. Its mesh matches its solid
    exactly, so the solid measurement passes it; the source lint is what names it.

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


disc_radius = float(PARAM(lambda: disc_radius, 200.0))
target_part = str(PARAM(lambda: target_part, "disc"))

if target_part == "disc":
    result = cq.Workplane("XY").circle(disc_radius).extrude(4)
elif target_part == "ring":
    result = cq.Workplane("XY").circle(disc_radius * 0.9).circle(disc_radius * 0.8).extrude(3)
elif target_part == "knob":
    result = cq.Workplane("XY").polygon(12, 30).extrude(12)
else:
    raise ValueError(f"Unknown target_part: {target_part}")
