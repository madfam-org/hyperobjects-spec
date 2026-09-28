"""Fixture: the CadQuery half of the `stand` mode.

Parameters arrive as BARE GLOBALS (cq_runner.py:43 `exec_globals.update(params)`), and
`PARAM(lambda: name, default)` is the commons idiom for probing one. Either way the
thing that makes a parameter alive here is the bare identifier appearing in the
executable text — which `base_w` does and `mat_width` does not.
"""

import cadquery as cq


def PARAM(getter, default):
    try:
        v = getter()
        return default if v is None else v
    except Exception:
        return default


base_w = float(PARAM(lambda: base_w, 40.0))

result = cq.Workplane("XY").box(base_w, base_w, 4.0)
