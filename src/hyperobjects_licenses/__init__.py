"""hyperobjects_licenses — canonical licence texts, and a shipped-LICENSE body check.

``texts/`` holds byte-identical copies of SPDX license-list-data texts for the
licences the commons declare (``VENDORED.md``; pinned by sha256 in
``licenses.lock.json``). ``body`` compares a shipped LICENSE against them and
classifies it as canonical, a short notice, a mismatch, or unjudged. Its verdicts are
notes, never failures, until the whole-commons false-positive analysis is written
down (AGENTS.md: new rules land as notes first).

    from hyperobjects_licenses import classify_license_file
    classify_license_file(Path("LICENSE"), declared="CERN-OHL-W-2.0").kind
"""

from .body import (
    BODY_MATCH_FLOOR,
    CANONICAL_IDS,
    DOCUMENTED_VARIANTS,
    LicenseBodyVerdict,
    Variant,
    canonical_text,
    classify_license_file,
    classify_license_text,
    lock,
    normalize,
    summary_clause,
)
from .cli import add_license_body_parser, collect_license_files, run_cli

__all__ = [
    "add_license_body_parser",
    "BODY_MATCH_FLOOR",
    "CANONICAL_IDS",
    "DOCUMENTED_VARIANTS",
    "LicenseBodyVerdict",
    "Variant",
    "canonical_text",
    "classify_license_file",
    "classify_license_text",
    "collect_license_files",
    "lock",
    "normalize",
    "run_cli",
    "summary_clause",
]
