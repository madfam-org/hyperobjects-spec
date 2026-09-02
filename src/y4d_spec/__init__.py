"""y4d-spec — the Yantra4D cartridge conformance runner.

A self-contained, runnable conformance check for a Yantra4D hyperobject cartridge. A
third party can install this package and validate their own cartridge OUTSIDE the
yantra4d repo:

    y4d-spec check /path/to/my-cartridge            # manifest + files
    y4d-spec check /path/to/my-cartridge --render   # + render every (mode, part)
    y4d-spec rules                                  # what gets checked, and why
    y4d-spec identity my-pair.json                  # the cross-commons identity key

Each check applies the project-manifest JSON Schema (bundled) plus the same
per-cartridge rules Yantra4D's own lanes enforce — ported from
scripts/qa/validate_manifests.py, scripts/audit_compliance.py,
scripts/qa/compliance_audit.py, scripts/qa/check_licenses.py, and the manifest
strictness gate in apps/api/manifest.py. Each rule names its source in `rules.py`.

Repo-WIDE checks (catalog drift, cross-cartridge slug uniqueness, OpenSCAD/CadQuery
geometric parity) deliberately stay in the platform: they are not properties of a
cartridge, so a third party could not run them anyway.

With the [geometry] extra installed, `--render` executes the cartridge through the
same restricted sandbox the platform uses (commons_sandbox, per cq_runner.py) for
every (mode, part) and asserts the mesh is watertight, has positive volume, and
contains no inverted body. It does that at TWO parameter points: the cartridge's own
defaults, and every PRESET the manifest declares — the points a user actually clicks
(`--no-presets` opts out). It also reports printability MEASUREMENTS — thin walls,
overhangs, build volume — as notes that never fail a cartridge (`--no-printability`
opts out); their thresholds are provisional pending full-commons calibration.
"""

from __future__ import annotations

from hyperobjects_version import distribution_version

from . import printability, rules, structure
from .conformance import CartridgeResult, check_cartridge, check_manifest

__all__ = [
    "CartridgeResult",
    "check_cartridge",
    "check_manifest",
    "printability",
    "rules",
    "structure",
    "__version__",
]

# One distribution, one version. Read from the installed metadata (or, in an
# uninstalled checkout, from pyproject.toml) rather than typed here — see
# hyperobjects_version for why a hand-written literal is the bug this ends.
__version__ = distribution_version()
