"""BRIDGE-HANDSHAKE: verify an FC↔Yantra4D hardware link PHYSICALLY.

`fc-spec check garment-manifest --resolve catalog.json` already answers the
STRUCTURAL question: does the slug resolve, does every `params_map` key name a real
parameter of the target, does every value expression reference real garment
parameters. That is name-level conformance, and it is where the commons stopped.

It is not enough. A link can be perfectly named and still be a lie:

  * the mapped VALUES may be values the hardware solid cannot build at — the y4d
    cartridge clamps them into range and silently returns a differently-sized part,
    or OCCT raises on a degenerate fillet. The garment says "this ring passes 38mm
    webbing"; the ring that comes out passes 25mm. Nothing in the manifest is wrong.
  * a `params_map` key may drive NOTHING. The name resolves (it IS a declared
    parameter of the target), the expression is valid, and the script never reads
    it — or reads it and clamps it to a constant. Dead wiring. This program has
    found this bug class repeatedly; it is invisible to every name-level check.

So this package renders. For each link it evaluates the `params_map` against the
garment's parameter defaults, renders the y4d cartridge AT THOSE VALUES, and then
perturbs each mapped parameter to prove the geometry actually moves.

Reuse, not fork — the two things this package deliberately does not reimplement:

  * expression parsing and structural resolution come from `fc_spec.rules`
    (`hardware_ref_rules`, `_idents`, `SAFE_MAP_FUNCS`). One parser, one grammar.
  * rendering comes from `y4d_spec.geometry.render_part`. That function replicates
    yantra4d's own `cq_runner` execution contract line for line; a second copy would
    drift from the platform within one release.

Requires the `geometry` extra for steps 2-3 (cadquery + trimesh). Step 1 is pure
python and always runs.
"""

from __future__ import annotations

from hyperobjects_version import distribution_version

from .core import (
    BridgeLink,
    LinkVerdict,
    ParamProbe,
    check_bridge,
    check_link,
    discover_links,
    load_y4d_index,
)

__all__ = [
    "BridgeLink",
    "LinkVerdict",
    "ParamProbe",
    "check_bridge",
    "check_link",
    "discover_links",
    "load_y4d_index",
    "__version__",
]

# One distribution, one version. Read from the installed metadata (or, in an
# uninstalled checkout, from pyproject.toml) rather than typed here — see
# hyperobjects_version for why a hand-written literal is the bug this ends.
__version__ = distribution_version()
