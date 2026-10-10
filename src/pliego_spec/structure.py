"""On-disk rules for a sheet cartridge DIRECTORY — the checks that need the files.

The sheet commons' layout is the soft commons' (architecture §4 of Pliego; the soft
commons' CI ``manifests`` job): one ``<slug>/`` per object holding the triple
``project.json`` / ``main.py`` / ``docs/README.md``, and no per-cartridge licence file
(the licence lives once, at the commons root). What the soft commons enforces in its own
CI, the keystone enforces here, so a third party gets the same bar from ``pip install``.

Each rule returns a list of problems; empty means conformant. Paths are reported
relative to the cartridge directory. All are FAILURES from birth — see the
false-positive analysis in ``pliego_spec.rules`` (the commons is empty).
"""

from __future__ import annotations

import ast
from pathlib import Path

from y4d_spec.structure import vendor_rules

from .rules import DEFAULT_SCRIPT, dead_parameter_problems

__all__ = [
    "REQUIRED_FILES",
    "ALLOWED_IMPORTS",
    "triple_rules",
    "license_file_rules",
    "slug_directory_rules",
    "mode_script_rules",
    "import_rules",
    "dead_parameter_rules",
    "all_structure_rules",
]

#: The cartridge triple (soft commons CI; Pliego kernel strategy §2).
REQUIRED_FILES = ("project.json", "main.py", "docs/README.md")

#: The only modules the Pliego runner makes importable (kernel strategy §2: "injects
#: `pliego` and `math` as the only importable modules"). An import of anything else is
#: a render-time failure in the sandbox — and a reach outside the cartridge.
ALLOWED_IMPORTS = frozenset({"pliego", "math"})

_MAX_DEPTH = 4


def _scripts(cartridge_dir: Path) -> list[Path]:
    out = []
    for p in sorted(cartridge_dir.rglob("*.py")):
        if "__pycache__" in p.parts or ".git" in p.parts:
            continue
        if len(p.relative_to(cartridge_dir).parts) <= _MAX_DEPTH:
            out.append(p)
    return out


def triple_rules(cartridge_dir: Path) -> list[str]:
    """project.json, main.py and docs/README.md must all be present (and non-empty)."""
    problems = []
    for name in REQUIRED_FILES:
        path = cartridge_dir / name
        if not path.is_file():
            problems.append(f"{name}: missing — a sheet cartridge is the triple "
                            f"{', '.join(REQUIRED_FILES)}")
        elif path.stat().st_size == 0:
            problems.append(f"{name}: empty")
    return problems


def license_file_rules(cartridge_dir: Path) -> list[str]:
    """No LICENSE or COPYING file at any depth inside the cartridge.

    The commons licence is declared in the manifest (two agreeing fields) and shipped
    once at the commons root. A per-cartridge licence file is a second, unchecked
    statement that can disagree with both — the soft commons forbids it for that reason.
    """
    problems = []
    for p in sorted(cartridge_dir.rglob("*")):
        if ".git" in p.parts or not p.is_file():
            continue
        if p.name.upper().startswith(("LICENSE", "COPYING")):
            problems.append(
                f"{p.relative_to(cartridge_dir)}: a cartridge must not ship its own licence "
                f"file — the commons licence is declared in project.json and shipped once at "
                f"the commons root"
            )
    return problems


def slug_directory_rules(cartridge_dir: Path, manifest: dict) -> list[str]:
    """The directory name equals `project.slug` — the platform mounts the commons at
    `projects/` and finds an object by its slug, so a mismatch is an object nobody can
    load by its own name."""
    slug = (manifest.get("project") or {}).get("slug") if isinstance(
        manifest.get("project"), dict) else None
    if isinstance(slug, str) and slug and cartridge_dir.name != slug:
        return [f"directory '{cartridge_dir.name}' does not match project.slug '{slug}'"]
    return []


def mode_script_rules(cartridge_dir: Path, manifest: dict) -> list[str]:
    """Every mode's script exists in the cartridge and resolves inside it."""
    problems = []
    root = cartridge_dir.resolve()
    for mode in manifest.get("modes") or []:
        if not isinstance(mode, dict):
            continue
        name = mode.get("script_file") or DEFAULT_SCRIPT
        if not isinstance(name, str):
            continue
        target = (cartridge_dir / name).resolve()
        if name.startswith("/") or not str(target).startswith(str(root) + "/"):
            problems.append(f"mode '{mode.get('id')}': script_file '{name}' escapes the cartridge")
        elif not target.is_file():
            problems.append(
                f"mode '{mode.get('id')}': script_file '{name}' does not exist in the cartridge"
            )
    return problems


def import_rules(cartridge_dir: Path) -> list[str]:
    """Scripts import only what the runner provides: `pliego` and `math`.

    The Python analogue of an escaping `include <../..>`: a cartridge that imports
    another module renders in the author's environment and nowhere else. A script that
    does not parse is reported as such — the runner would refuse it too.
    """
    problems = []
    for path in _scripts(cartridge_dir):
        rel = path.relative_to(cartridge_dir)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError as exc:
            problems.append(f"{rel}:{exc.lineno}: does not parse — {exc.msg}")
            continue
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{rel}: unreadable — {exc}")
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = ["." * node.level + (node.module or "")]
            for name in names:
                if name.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append(
                        f"{rel}:{node.lineno}: imports '{name}' — the Pliego runner makes "
                        f"only {', '.join(sorted(ALLOWED_IMPORTS))} importable"
                    )
    return problems


def dead_parameter_rules(cartridge_dir: Path, manifest: dict) -> list[str]:
    sources: dict[str, str] = {}
    for mode in manifest.get("modes") or []:
        if not isinstance(mode, dict):
            continue
        name = mode.get("script_file") or DEFAULT_SCRIPT
        if not isinstance(name, str) or name in sources:
            continue
        path = cartridge_dir / name
        if path.is_file():
            sources[name] = path.read_text(encoding="utf-8", errors="replace")
    return dead_parameter_problems(manifest, sources)


def all_structure_rules(cartridge_dir: Path, manifest: dict) -> list[str]:
    """Every on-disk rule that needs a parsed manifest, in one call (the triple is
    checked by the caller before the manifest is read)."""
    problems: list[str] = []
    problems += slug_directory_rules(cartridge_dir, manifest)
    problems += mode_script_rules(cartridge_dir, manifest)
    problems += license_file_rules(cartridge_dir)
    problems += vendor_rules(cartridge_dir)
    problems += import_rules(cartridge_dir)
    problems += dead_parameter_rules(cartridge_dir, manifest)
    return problems
