"""fc-spec — the Fashion Cabinet spec conformance runner.

A self-contained, runnable conformance check for the Fashion Cabinet v1 contracts
(docs/spec/v1). A third party can install this package and validate their own files
against the published spec, outside the Fashion Cabinet repo:

    fc-spec check garment-manifest my-cartridge.json
    fc-spec check body-measurements my-body.json
    fc-spec list

Each contract check applies the contract's JSON Schema (bundled with the package)
plus the same cross-field / semantic rules Fashion Cabinet's own CI enforces — the
rule functions live here (`rules.py`) and are imported by both this runner and the
in-repo CI lanes, so the two can never diverge.

The contracts (see `CONTRACTS`): garment-manifest, fabric-card, body-measurements,
hardware-ref, explode-json.
"""

from __future__ import annotations

from hyperobjects_version import distribution_version

from .conformance import CONTRACTS, ConformanceResult, check, list_contracts

__all__ = ["CONTRACTS", "ConformanceResult", "check", "list_contracts", "__version__"]

# One distribution, one version. Read from the installed metadata (or, in an
# uninstalled checkout, from pyproject.toml) rather than typed here — see
# hyperobjects_version for why a hand-written literal is the bug this ends.
__version__ = distribution_version()
