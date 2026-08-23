"""Cartridge conformance: schema + house rules + optional geometry, in one call.

    from y4d_spec import check_cartridge
    result = check_cartridge("/path/to/my-cartridge", render=False)
    if not result.ok:
        for problem in result.problems:
            print(problem)

Ties the bundled project-manifest schema (hyperobjects_schemas) to the pure rule
functions (rules.py), the on-disk rules (structure.py), and — when asked, and when
the [geometry] extra is installed — the render lane (geometry.py).

Nothing short-circuits: schema errors do not suppress rule problems, so a caller sees
every problem at once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from hyperobjects_schemas import load as load_schema

from . import rules, structure

__all__ = ["CartridgeResult", "check_manifest", "check_cartridge", "MANIFEST_SCHEMA"]

MANIFEST_SCHEMA = "project-manifest"


@dataclass
class CartridgeResult:
    """The verdict on one cartridge. Falsey when there are problems."""

    slug: str | None
    ok: bool
    problems: list[str] = field(default_factory=list)
    #: Non-blocking observations — true, worth saying, but not a conformance failure
    #: (e.g. an include of the repo's shared libs/ tree). Never affects `ok`.
    notes: list[str] = field(default_factory=list)
    #: One RenderCheck per (mode, part), plus one per (preset, part) when the preset
    #: matrix ran. Empty when geometry did not run.
    renders: list = field(default_factory=list)
    #: True when geometry verification actually executed.
    rendered: bool = False

    def __bool__(self) -> bool:
        return self.ok

    @property
    def preset_renders(self) -> list:
        """Just the preset renders — the parameter points a user clicks."""
        return [c for c in self.renders if getattr(c, "preset", None)]


def _schema_errors(doc: object) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise RuntimeError("jsonschema is required (pip install hyperobjects-spec)") from exc
    validator = Draft202012Validator(load_schema(MANIFEST_SCHEMA))
    problems = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        problems.append(f"schema {where}: {err.message}")
    return problems


def check_manifest(doc: dict) -> CartridgeResult:
    """Check a parsed project.json alone — schema + every per-cartridge house rule.

    Path-independent: no directory, no rendering. This is what a manifest editor or a
    PR bot can run on a diff.
    """
    problems = _schema_errors(doc)
    problems.extend(rules.all_manifest_rules(doc))
    slug = (doc.get("project") or {}).get("slug") if isinstance(doc.get("project"), dict) else None
    return CartridgeResult(slug=slug, ok=not problems, problems=problems)


def check_cartridge(
    cartridge_dir: str | Path,
    *,
    render: bool = False,
    presets: bool = True,
    printability: bool = True,
) -> CartridgeResult:
    """Check a cartridge DIRECTORY: its manifest, its files, and optionally its geometry.

    `render=True` requires the [geometry] extra; without it, a GeometryUnavailable is
    raised rather than silently skipped — a checker that quietly downgrades its own
    strictness is how an unverified cartridge ships green.

    `presets` and `printability` only mean anything under `render=True`. Both default
    ON so the strongest available check is the one a caller gets by asking for
    geometry — the same reason `--render` refuses rather than downgrading. Presets are
    part of the conformance verdict; printability is notes only and never is.
    """
    path = Path(cartridge_dir).resolve()
    manifest_path = path / "project.json"

    if not path.is_dir():
        return CartridgeResult(
            slug=None, ok=False, problems=[f"{path}: not a directory"]
        )
    if not manifest_path.is_file():
        return CartridgeResult(
            slug=None, ok=False, problems=[f"{path}: no project.json — not a cartridge"]
        )

    try:
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CartridgeResult(
            slug=None, ok=False, problems=[f"project.json: invalid JSON — {exc}"]
        )

    if not isinstance(doc, dict):
        return CartridgeResult(
            slug=None, ok=False, problems=["project.json: top level must be an object"]
        )

    result = check_manifest(doc)
    structure_problems, notes = structure.all_structure_rules(path, doc)
    result.problems.extend(structure_problems)
    result.notes.extend(notes)

    if render:
        from .geometry import check_geometry  # imports cadquery; keep it lazy

        result.renders = check_geometry(
            path, doc, presets=presets, printability=printability
        )
        result.rendered = True
        for check in result.renders:
            if not check.ok:
                result.problems.append(f"render {check.summary}")
            # Per-render notes (preset-vs-default sameness, printability
            # measurements) join the cartridge's notes and never touch `ok`.
            result.notes.extend(check.notes)

    result.ok = not result.problems
    return result
