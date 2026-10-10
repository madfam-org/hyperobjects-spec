"""Compare a shipped licence file's BODY with the canonical SPDX text.

The title-line check (`y4d_spec.structure.shipped_license_rules`) reads only the
first lines of a LICENSE. On 2026-10-10 that let solid-hyperobjects ship the full
CERN-OHL-S-2.0 body under a "Weakly Reciprocal" title, in its root LICENSE and 12
cartridge copies, with CI green (fixed by solid-hyperobjects#177). This module reads
the whole file and puts it in exactly one of four buckets:

``canonical``
    The SPDX license-list-data text of a licence, word for word, after
    normalisation (Unicode NFC, every run of whitespace collapsed to one space, a
    leading BOM and surrounding blank lines dropped) and after folding the
    documented variants in `DOCUMENTED_VARIANTS`. Nothing else is tolerated.
``notice``
    A CERN-OHL v2 short notice: a few lines that name the licence and repeat its
    warranty disclaimer, pointing at the full text rather than carrying it. The
    exact shape is `_classify_notice`'s docstring. CERN-OHL v2 §1 counts "notices
    that refer to this Licence and to the disclaimer of warranties" as Notices, so a
    notice is a legitimate thing to ship; a malformed URL in one is still reported.
``mismatch``
    Anything else. The verdict names the canonical text the body is closest to (by
    word-sequence similarity), so an S body under a W title reads "body is
    CERN-OHL-S-2.0" and a reworded text reads "not a canonical licence text,
    closest CERN-OHL-W-2.0 at 24%".
``unjudged``
    The declared licence has no vendored canonical text, so nothing here can say
    whether the body is right. Counted apart: an unjudged file is not a pass.

Every verdict is a NOTE today. New rules land as notes first (AGENTS.md); this one
becomes a failure only after the whole-commons false-positive analysis is written
down and the commons texts it flags have been replaced.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path

__all__ = [
    "BODY_MATCH_FLOOR",
    "CANONICAL_IDS",
    "DOCUMENTED_VARIANTS",
    "LicenseBodyVerdict",
    "Variant",
    "canonical_text",
    "classify_license_text",
    "classify_license_file",
    "lock",
    "normalize",
    "summary_clause",
]


@dataclass(frozen=True)
class Variant:
    """One tolerated spelling difference, given as the phrase in the SPDX text and
    the phrase in the alternative rendering, each with enough context to occur in one
    place only. Both sides are folded to the SPDX phrase before comparing."""

    spdx: str
    alternative: str
    why: str


# GitHub's licence catalogue renders CERN-OHL-W-2.0 with three spellings that differ
# from the SPDX text. A file copied from GitHub's "Add a licence" picker (custom-msh
# and julia-vase in solid-hyperobjects; sheet-hyperobjects' LICENSE) differs from SPDX
# in exactly these places and nowhere else. The phrases also occur in CERN-OHL-P-2.0
# (the first) and CERN-OHL-S-2.0 (the second and third). Keep this list small: every
# entry is a place where two texts that differ are treated as equal.
DOCUMENTED_VARIANTS: tuple[Variant, ...] = (
    Variant(
        spdx="CERN- OHL-W (weakly reciprocal)",
        alternative="CERN-OHL-W (weakly reciprocal)",
        why="preamble: SPDX keeps a line-break hyphen ('CERN- OHL-W'); GitHub joins it",
    ),
    Variant(
        spdx="3 Copying, modifying and Conveying Covered Source",
        alternative="3 Copying, Modifying and Conveying Covered Source",
        why="section 3 heading: SPDX 'modifying', GitHub 'Modifying'",
    ),
    Variant(
        spdx="patent license to Make",
        alternative="patent licence to Make",
        why="section 7.2 (W, S) / 7.1 (P): SPDX 'license', GitHub 'licence'",
    ),
)

# Above this word-sequence similarity a body is "the text of X, with differences";
# below it, "not a canonical licence text". CERN-OHL-W-2.0 and CERN-OHL-S-2.0 are 94%
# similar to EACH OTHER (measured on the SPDX texts), so a floor below that could not
# tell an S body from a W one. Measured above it: the S body under a W title is 99.85%
# similar to S; the GitHub rendering of W is 99.84% similar to SPDX W before folding.
BODY_MATCH_FLOOR = 0.98

# A notice is a few lines, not a licence. The real commons notice is 70 words.
NOTICE_MAX_WORDS = 150

_PKG = "hyperobjects_licenses"
_ALIASES = {"GPL-2.0": "GPL-2.0-only"}


@cache
def lock() -> dict:
    """The lock file: SPDX license-list-data commit, and per text its sha256."""
    with resources.files(_PKG).joinpath("licenses.lock.json").open(encoding="utf-8") as f:
        return json.load(f)


CANONICAL_IDS: tuple[str, ...] = tuple(lock()["files"])


def _canonical_id(spdx_id: str | None) -> str | None:
    if not spdx_id:
        return None
    spdx_id = _ALIASES.get(spdx_id, spdx_id)
    return spdx_id if spdx_id in CANONICAL_IDS else None


@cache
def canonical_text(spdx_id: str) -> str:
    """The vendored SPDX text for `spdx_id`, exactly as shipped by license-list-data."""
    sid = _canonical_id(spdx_id)
    if sid is None:
        raise KeyError(f"no vendored canonical text for {spdx_id!r}")
    with resources.files(_PKG).joinpath("texts", f"{sid}.txt").open(encoding="utf-8") as f:
        return f.read()


def normalize(text: str) -> str:
    """NFC, drop a BOM, collapse every whitespace run (line wraps, indentation, blank
    lines, CRLF) to one space, strip the ends. Case and punctuation are kept."""
    text = unicodedata.normalize("NFC", text).replace("﻿", "")
    return re.sub(r"\s+", " ", text).strip()


def _fold(norm: str) -> str:
    for v in DOCUMENTED_VARIANTS:
        norm = norm.replace(v.alternative, v.spdx)
    return norm


@cache
def _canonical_folded(sid: str) -> str:
    return _fold(normalize(canonical_text(sid)))


@dataclass(frozen=True)
class LicenseBodyVerdict:
    """The verdict on one shipped licence file."""

    path: str
    declared: str | None
    #: canonical | notice | mismatch | unjudged
    kind: str
    #: The licence whose text (canonical) or notice (notice) this is, or the
    #: canonical text the body is closest to (mismatch). None when unjudged.
    license: str | None = None
    #: Word-sequence similarity to `license`'s canonical text, 0..1.
    similarity: float = 0.0
    #: Names (`why`) of the documented variants the file uses.
    variants: tuple[str, ...] = ()
    #: Human-readable findings. Empty on a clean canonical or notice verdict.
    findings: tuple[str, ...] = field(default=())

    @property
    def clean(self) -> bool:
        """Canonical or notice, of the declared licence, with nothing to report."""
        return self.kind in ("canonical", "notice") and not self.findings

    def notes(self) -> list[str]:
        return [f"{self.path}: licence body — {f}" for f in self.findings]


def _words(norm: str) -> list[str]:
    return norm.split(" ") if norm else []


def _ratio(a: list[str], b: list[str]) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _first_difference(canon: list[str], shipped: list[str]) -> str:
    sm = difflib.SequenceMatcher(None, canon, shipped, autojunk=False)
    runs = [op for op in sm.get_opcodes() if op[0] != "equal"]
    if not runs:
        return ""
    _, i1, i2, j1, j2 = runs[0]
    want = " ".join(canon[i1:i2])[:80] or "(nothing)"
    got = " ".join(shipped[j1:j2])[:80] or "(nothing)"
    return f"{len(runs)} differing run(s), first: SPDX '{want}' vs shipped '{got}'"


_CERN_TITLE = {"Permissive": "P", "Weakly Reciprocal": "W", "Strongly Reciprocal": "S"}
_DISCLAIMER = (
    "WITHOUT ANY EXPRESS OR IMPLIED WARRANTY, INCLUDING OF MERCHANTABILITY, "
    "SATISFACTORY QUALITY AND FITNESS FOR A PARTICULAR PURPOSE"
)
_URL = re.compile(r"\bhttps?:[^\s()<>\"']*", re.IGNORECASE)


def _classify_notice(norm: str) -> tuple[str | None, list[str]]:
    """Is `norm` a CERN-OHL v2 short notice? Returns (spdx id, findings) or (None, []).

    The shape, all of it required, on the normalised text:

    * at most `NOTICE_MAX_WORDS` words;
    * ``licensed under the CERN-OHL-<V> v2`` and ``under the terms of the CERN-OHL-<V>
      v2`` (V is P, W or S);
    * the CERN-OHL v2 warranty disclaimer, ``WITHOUT ANY EXPRESS OR IMPLIED WARRANTY,
      INCLUDING OF MERCHANTABILITY, SATISFACTORY QUALITY AND FITNESS FOR A PARTICULAR
      PURPOSE``.

    Every ``CERN-OHL-<V>`` it names, and a ``Version 2 - <Weakly Reciprocal|...>``
    title if it has one, must name the same variant; a notice that says W in its title
    and S in its body is a mismatch, not a notice. Findings (still a notice): a URL
    whose scheme is not followed by ``//`` (``https:/cern.ch/cern-ohl``), or no URL.
    """
    if len(_words(norm)) > NOTICE_MAX_WORDS:
        return None, []
    m1 = re.search(r"licensed under the CERN-OHL-([PWS]) v2\b", norm)
    m2 = re.search(r"under the terms of the CERN-OHL-([PWS]) v2\b", norm)
    if not (m1 and m2) or _DISCLAIMER not in norm:
        return None, []
    named = set(re.findall(r"CERN-OHL-([PWS])\b", norm))
    named |= {v for t, v in _CERN_TITLE.items() if f"Version 2 - {t}" in norm}
    if len(named) != 1:
        return None, []
    sid = f"CERN-OHL-{named.pop()}-2.0"
    findings: list[str] = []
    urls = _URL.findall(norm)
    for url in urls:
        if not re.match(r"https?://", url, re.IGNORECASE):
            findings.append(
                f"short {sid} notice has a malformed URL '{url.rstrip('.,;')}' "
                "(the scheme must be followed by '//')"
            )
    if not urls:
        findings.append(f"short {sid} notice names no URL where the licence text is found")
    return sid, findings


def classify_license_text(text: str, declared: str | None = None, path: str = "") -> \
        LicenseBodyVerdict:
    """Classify one licence file's text against `declared` (an SPDX id, or None)."""
    norm = normalize(text)
    decl = _ALIASES.get(declared, declared) if declared else None
    folded = _fold(norm)

    # 1. Canonical: equal to SOME vendored text after folding.
    for sid in CANONICAL_IDS:
        if folded == _canonical_folded(sid):
            canon_norm = normalize(canonical_text(sid))
            used = tuple(
                v.why for v in DOCUMENTED_VARIANTS if v.alternative in norm and v.spdx in canon_norm
            )
            if decl and sid != decl:
                return LicenseBodyVerdict(
                    path, declared, "mismatch", sid, 1.0, used,
                    (f"body is the canonical {sid} text, not the declared {decl}",),
                )
            return LicenseBodyVerdict(path, declared, "canonical", sid, 1.0, used)

    # 2. A short notice.
    nsid, nfind = _classify_notice(norm)
    if nsid is not None:
        if decl and nsid != decl:
            return LicenseBodyVerdict(
                path, declared, "mismatch", nsid, 0.0, (),
                (f"is a short {nsid} notice, not one for the declared {decl}", *nfind),
            )
        return LicenseBodyVerdict(path, declared, "notice", nsid, 0.0, (), tuple(nfind))

    # 3. Nothing to judge it against: the declared licence is not vendored, and the
    #    text is none of the vendored ones. Not a pass and not a mismatch.
    if decl and _canonical_id(decl) is None:
        return LicenseBodyVerdict(
            path, declared, "unjudged", None, 0.0, (),
            (f"no canonical text for the declared licence {decl} is vendored here, "
             "so its body is not judged",),
        )

    # 4. Mismatch: say which canonical body it is closest to.
    shipped = _words(folded)
    scored = sorted(
        ((_ratio(_words(_canonical_folded(sid)), shipped), sid) for sid in CANONICAL_IDS),
        reverse=True,
    )
    best_ratio, best = scored[0]
    if best_ratio >= BODY_MATCH_FLOOR:
        detail = _first_difference(_words(_canonical_folded(best)), shipped)
        if decl and best != decl:
            msg = (f"body is {best} ({best_ratio:.2%} word-sequence match to SPDX {best}), "
                   f"not the declared {decl}; {detail}")
        else:
            msg = (f"body is {best} but not the canonical text ({best_ratio:.2%}); "
                   f"{detail}")
    else:
        if norm.startswith("<"):
            what = "is HTML, not a licence text"
        else:
            what = "is not a canonical licence text (a paraphrase, a fragment or another text)"
        msg = (f"{what} — closest canonical text is {best} at {best_ratio:.0%} "
               "word-sequence similarity")
    return LicenseBodyVerdict(path, declared, "mismatch", best, best_ratio, (), (msg,))


def classify_license_file(path: Path, declared: str | None = None, rel: str | None = None) \
        -> LicenseBodyVerdict:
    """Read `path` (UTF-8, undecodable bytes replaced) and classify it."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return classify_license_text(text, declared, rel if rel is not None else str(path))


def summary_clause(verdicts: list[LicenseBodyVerdict]) -> str:
    """``licence-body: files=N canonical=C notices=S mismatched=M unjudged=U``.

    C + S + M + U = N by construction. `canonical` and `notices` count only texts of
    the DECLARED licence (or of any vendored licence when nothing is declared); the
    canonical text or a notice of another licence is `mismatched`. A notice with a
    malformed URL is still a notice, and its note says so.
    """
    n = len(verdicts)
    c = sum(v.kind == "canonical" for v in verdicts)
    s = sum(v.kind == "notice" for v in verdicts)
    m = sum(v.kind == "mismatch" for v in verdicts)
    u = sum(v.kind == "unjudged" for v in verdicts)
    return f"licence-body: files={n} canonical={c} notices={s} mismatched={m} unjudged={u}"
