"""On-disk rules for a cartridge DIRECTORY — the checks that need the files, not
just the manifest.

Ported from yantra4d/scripts/audit_compliance.py:

  check_rule_1_no_absolute_or_escaped_paths  (:38)  -> source_path_rules
  check_rule_2_no_vendor                     (:65)  -> vendor_rules
  (declared-vs-shipped license, shipped half; scripts/qa/check_licenses.py)
                                                    -> shipped_license_rules

Plus one rule this package originates: `dead_parameter_rules` (G-DEADPARAM), which
needs the mode SOURCES and so cannot live in `rules.py` with the pure manifest checks.
It reads the files and hands their text to `rules.dead_parameter_problems`, where the
decision is made — the same split the render lane uses, so the judgement stays testable
without a directory.

Each returns a list of problems; empty means conformant. Paths are reported relative
to the cartridge directory so the output is the same wherever the cartridge lives.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "SOURCE_SUFFIXES",
    "source_path_rules",
    "vendor_rules",
    "shipped_license_rules",
    "mode_source_rules",
    "dead_parameter_rules",
    "all_structure_rules",
]

# The source files a cartridge ships. audit_compliance.py scans .scad and .py.
SOURCE_SUFFIXES = (".scad", ".py")

# Bounded scan depth, mirroring check_licenses.py's bounded nested-LICENSE scan.
_MAX_DEPTH = 4


def _sources(cartridge_dir: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(cartridge_dir.rglob("*")):
        if ".git" in p.parts or "__pycache__" in p.parts:
            continue
        if p.is_file() and p.suffix in SOURCE_SUFFIXES:
            if len(p.relative_to(cartridge_dir).parts) <= _MAX_DEPTH:
                out.append(p)
    return out


def source_path_rules(cartridge_dir: Path) -> tuple[list[str], list[str]]:
    """No absolute include paths, and no include that escapes the cartridge.

    audit_compliance.py:38. A cartridge that reaches outside its own directory is not
    portable — it renders in the platform repo and nowhere else, which is precisely
    what this package exists to stop.

    Returns (problems, notes). An escape into a shared `libs` directory is a NOTE, not
    a problem: audit_compliance.py:61 exempts it, ~40 cartridges in the yantra4d
    commons legitimately `include <../../libs/BOSL2/std.scad>`, and a runner that
    failed them would be stricter than the platform it is meant to mirror — which
    would block adoption rather than enable it. It is still worth saying out loud,
    because that cartridge will not render outside a repo that provides libs/.
    """
    problems: list[str] = []
    notes: list[str] = []
    for path in _sources(cartridge_dir):
        if path.suffix != ".scad":
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(cartridge_dir)
        for i, line in enumerate(lines, start=1):
            s = line.strip()
            if not (s.startswith("use <") or s.startswith("include <")):
                continue
            if "<" not in s or ">" not in s:
                continue
            target = s.split("<", 1)[1].split(">", 1)[0]
            if target.startswith("/"):
                problems.append(f"{rel}:{i}: absolute path in include/use: {target}")
            elif "../" in target:
                resolved = (path.parent / target).resolve()
                if str(resolved).startswith(str(cartridge_dir.resolve())):
                    continue
                if "libs" in resolved.parts:
                    notes.append(
                        f"{rel}:{i}: includes the shared library tree ({target}) — "
                        f"allowed in the yantra4d repo, but this cartridge will not "
                        f"render anywhere that does not provide libs/"
                    )
                else:
                    problems.append(
                        f"{rel}:{i}: include/use escapes the cartridge: {target}"
                    )
    return problems, notes


def vendor_rules(cartridge_dir: Path) -> list[str]:
    """No vendored third-party tree inside a cartridge — audit_compliance.py:65.

    In-repo this is gated by a VENDOR_WHITELIST which is deliberately empty ("empty
    for now to enforce strictness"), so the rule travels unconditionally.
    """
    vendor = cartridge_dir / "vendor"
    if vendor.is_dir():
        return [
            "vendor/: a cartridge must not vendor a third-party tree — declare the "
            "dependency instead"
        ]
    return []


def shipped_license_rules(cartridge_dir: Path, manifest: dict) -> list[str]:
    """The SHIPPED half of check_licenses.py's declared-vs-shipped cross-check.

    Only reports when the cartridge ships a LICENSE file at all: in the yantra4d repo
    a LICENSE of its own is required only of cartridges published as their own
    submodule (check_licenses.py's submodule_slugs()), and this package cannot know
    that. So a missing LICENSE is silent, while a PRESENT one that contradicts the
    declared commons_license is a conflict — which is the failure the lane exists to
    catch.
    """
    problems: list[str] = []
    ho = manifest.get("hyperobject") if isinstance(manifest.get("hyperobject"), dict) else {}
    declared = ho.get("commons_license")
    if not isinstance(declared, str) or not declared:
        return problems

    candidates = [
        p
        for p in sorted(cartridge_dir.iterdir())
        if p.is_file() and p.name.upper().startswith(("LICENSE", "COPYING"))
    ]
    if not candidates:
        return problems

    for lic in candidates:
        try:
            head = lic.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError as exc:
            problems.append(f"{lic.name}: unreadable — {exc}")
            continue
        if head.lstrip().startswith("<"):
            problems.append(
                f"{lic.name}: is HTML, not a license text (a saved web page, "
                f"probably a 404)"
            )
            continue
        if not _license_matches(declared, head):
            problems.append(
                f"{lic.name}: does not look like the declared license "
                f"'{declared}' — declared-vs-shipped conflict"
            )
    return problems


# Distinctive title text per license family, used to tell a shipped LICENSE apart
# from its declaration. Substring matching on the license's own title line only —
# never a full-text diff, so a license with a filled-in copyright line still matches.
_LICENSE_MARKERS: dict[str, tuple[str, ...]] = {
    "CERN-OHL-W": ("cern open hardware licence", "cern-ohl-w"),
    "CERN-OHL-S": ("cern open hardware licence", "cern-ohl-s"),
    "CERN-OHL-P": ("cern open hardware licence", "cern-ohl-p"),
    "Apache-2.0": ("apache license",),
    "MIT": ("mit license", "permission is hereby granted, free of charge"),
    "GPL-3.0": ("gnu general public license",),
    "AGPL-3.0": ("gnu affero general public license",),
    "LGPL-3.0": ("gnu lesser general public license",),
    "MPL-2.0": ("mozilla public license",),
    "BSD-3-Clause": ("redistribution and use in source and binary forms",),
    "BSD-2-Clause": ("redistribution and use in source and binary forms",),
    "CC-BY-SA-4.0": ("creative commons attribution-sharealike",),
    "CC-BY-4.0": ("creative commons attribution",),
    "CC0-1.0": ("cc0 1.0", "creative commons zero"),
}


def _license_matches(declared: str, text: str) -> bool:
    """Does `text` look like the license `declared` names? Unknown identifiers pass —
    reporting an unrecognized-but-valid SPDX id as a conflict would be a false alarm.
    """
    low = text.lower()
    for prefix, markers in _LICENSE_MARKERS.items():
        if declared.upper().startswith(prefix.upper()):
            return any(m in low for m in markers)
    return True


def mode_source_rules(cartridge_dir: Path, manifest: dict) -> list[str]:
    """Every file a mode names must exist in the cartridge.

    apps/api/manifest.py:123 (get_allowed_files) builds {filename: project_dir/filename}
    for every mode; a name that does not resolve is a render-time failure, not a
    manifest-time one. Checked here so it surfaces before anyone tries to render.
    """
    problems: list[str] = []
    for mode in manifest.get("modes") or []:
        if not isinstance(mode, dict):
            continue
        mid = mode.get("id")
        for key in ("scad_file", "cq_file"):
            fname = mode.get(key)
            if not isinstance(fname, str) or not fname:
                continue
            if not (cartridge_dir / fname).is_file():
                problems.append(f"mode '{mid}': {key} '{fname}' does not exist in the cartridge")
    return problems


def _include_targets(text: str) -> list[str]:
    """The `include <>` / `use <>` targets named by one OpenSCAD source."""
    return re.findall(r"^\s*(?:include|use)\s*<([^>]+)>", text, flags=re.M)


def _read_mode_source(
    cartridge_dir: Path, name: str, *, _depth: int = 0, _seen: set[str] | None = None
) -> str | None:
    """One mode source's text, with the text of the in-cartridge files it includes.

    THE LIBRARY DECISION (G-DEADPARAM). A reference from a library file DOES count, and
    only from a library the cartridge SHIPS.

    Why it counts: `include <>` in OpenSCAD is textual inclusion into the same variable
    scope, so an identifier read inside `profiles/classic.scad` is reading the very
    global the platform's `-D` sets. That parameter reaches geometry. Calling it dead
    because the read happens one file along would be false, and this rule's whole
    premise is that a parameter which reaches geometry is alive wherever it does so.

    Why only a shipped one: a target outside the cartridge (`BOSL2/std.scad`,
    `../../libs/...`) resolves against an OpenSCAD library path this package does not
    have and the cartridge does not carry — `source_path_rules` already notes that such
    a cartridge will not render anywhere that does not provide `libs/`. Reading a file
    that is not there is impossible; treating its ABSENCE as a reference would exempt
    every parameter of every BOSL2 cartridge — 43 of them — and turn the rule off where
    it is most needed. Unresolvable targets are therefore skipped, and the rule stays
    conservative in the one direction that matters: it can only ever miss a dead
    parameter, never invent one.

    Measured before it was decided: following in-cartridge includes changes the verdict
    on ZERO of the solid commons' 500 cartridges, and rescues none of the 20 dead
    parameters found there. So this is not what produced the measurement — it is what
    keeps the rule right for the cartridge that has not been written yet.

    Depth-bounded and cycle-safe: `portacosas` both `include <desk_organizer.scad>` and
    `use <desk_organizer.scad>`, and a pair of files that include each other is legal.
    """
    if _seen is None:
        _seen = set()
    path = cartridge_dir / name
    key = str(path)
    if key in _seen or not path.is_file():
        return None
    _seen.add(key)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    if path.suffix != ".scad" or _depth >= _MAX_DEPTH:
        return text

    parts = [text]
    for target in _include_targets(text):
        if target.startswith("/") or ".." in target:
            continue  # outside the cartridge — see the docstring
        included = _read_mode_source(
            cartridge_dir, target, _depth=_depth + 1, _seen=_seen
        )
        if included is not None:
            parts.append(included)
    return "\n".join(parts)


def dead_parameter_rules(cartridge_dir: Path, manifest: dict) -> list[str]:
    """Every declared parameter must be referenced by a source of a mode that lists it.

    G-DEADPARAM. The disk half: resolve each mode's declared sources (plus the
    in-cartridge files they include, per `_read_mode_source`) and hand the text to
    `rules.dead_parameter_problems`, which owns the decision and is testable without a
    directory.
    """
    from . import rules as _rules

    sources: dict[str, str] = {}
    for mode in manifest.get("modes") or []:
        if not isinstance(mode, dict):
            continue
        for key in ("cq_file", "scad_file", "graph_file"):
            name = mode.get(key)
            if not isinstance(name, str) or not name or name in sources:
                continue
            text = _read_mode_source(cartridge_dir, name)
            if text is not None:
                sources[name] = text
    return _rules.dead_parameter_problems(manifest, sources)


def all_structure_rules(cartridge_dir: Path, manifest: dict) -> tuple[list[str], list[str]]:
    """Every on-disk rule, in one call. Returns (problems, notes)."""
    problems: list[str] = []
    problems.extend(mode_source_rules(cartridge_dir, manifest))
    path_problems, notes = source_path_rules(cartridge_dir)
    problems.extend(path_problems)
    problems.extend(vendor_rules(cartridge_dir))
    problems.extend(shipped_license_rules(cartridge_dir, manifest))
    problems.extend(dead_parameter_rules(cartridge_dir, manifest))
    return problems, notes
