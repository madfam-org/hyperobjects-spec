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
contains no inverted body.
"""

from __future__ import annotations

from .conformance import CartridgeResult, check_cartridge, check_manifest

__all__ = [
    "CartridgeResult",
    "check_cartridge",
    "check_manifest",
    "__version__",
]

__version__ = "0.1.0"
