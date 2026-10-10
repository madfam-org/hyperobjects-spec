"""pliego-spec — the sheet commons' conformance runner (the keystone's third kernel).

The sheet commons (``sheet-hyperobjects``: origami, kirigami, papercut, pop-up and paper
engineering, book structures, paper dioramas) is rendered by the Pliego platform. This
package checks its objects with zero platform code, as ``y4d-spec`` does for the solid
commons and ``fc-spec`` for the soft one:

    pliego-spec check cartridge my-object/
    pliego-spec check sheet-manifest my-object/project.json
    pliego-spec check sheet-document my-object.fold

Contracts (``CONTRACTS``): ``sheet-manifest`` (authored in the keystone,
``hyperobjects_schemas``) and ``sheet-document`` (Pliego's FOLD-based document,
vendored and sha-256-locked in ``pliego_spec/schemas``).
"""

from __future__ import annotations

__version__ = "0.1.0"

from .conformance import (  # noqa: E402 - __version__ first, the CLI imports it
    CONTRACTS,
    CartridgeResult,
    ConformanceResult,
    check,
    check_cartridge,
    check_manifest,
    list_contracts,
)
from .rules import SHEET_COMMONS_LICENSE  # noqa: E402

__all__ = [
    "CONTRACTS",
    "CartridgeResult",
    "ConformanceResult",
    "SHEET_COMMONS_LICENSE",
    "check",
    "check_cartridge",
    "check_manifest",
    "list_contracts",
    "__version__",
]
