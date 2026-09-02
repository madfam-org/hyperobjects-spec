"""hyperobjects_version — the one place this distribution's version is read from.

Every package in this repo (``fc_spec``, ``y4d_spec``, ``bridge_check``,
``commons_sandbox``, ``hyperobjects_lexicon``, ``hyperobjects_schemas``) ships inside a
SINGLE distribution — ``hyperobjects-spec``, declared once in ``pyproject.toml``. There
is one artifact, one wheel, one ``pip install``, and therefore one version.

Before this module each package carried a hand-typed ``__version__`` string, and the six
of them had drifted into four different answers while ``pyproject.toml`` said a fifth.
A literal in a source file is a claim nobody re-checks: it is written once at release
and then silently outlives every change made after it. So no package types a version
any more. They all ask here, and here asks the packaging metadata that ``pip`` actually
installed.

Two paths, in order:

1. **Installed (the normal path).** ``importlib.metadata.version("hyperobjects-spec")``
   reads the version out of the ``.dist-info`` that ``pip`` wrote. This is the true
   answer for anyone who installed the package — including ``pip install -e .``, which
   is how CI and every contributor run it — because it is the same string the installer
   resolved the distribution under.

2. **Uninstalled source checkout (the fallback).** Someone reading the tree with
   ``PYTHONPATH=src`` and no install has no ``.dist-info`` to read, so
   ``importlib.metadata`` raises ``PackageNotFoundError``. Rather than invent a
   placeholder, parse ``project.version`` straight out of ``pyproject.toml`` — located
   RELATIVE TO THIS FILE (``src/hyperobjects_version/__init__.py`` → two parents up), so
   it is found regardless of the working directory — with stdlib ``tomllib`` (Python
   3.11+, which this package already requires; no new dependency).

Both paths read the same declaration, so they agree by construction; a test in
``tests/test_version.py`` holds them to it rather than trusting the argument.

If BOTH fail the module raises rather than guessing. A wrong version that looks right is
the failure mode this module exists to end, and a quiet ``"0.0.0"`` would be exactly
that bug wearing a different literal.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from functools import cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version
from pathlib import Path

__all__ = [
    "DISTRIBUTION",
    "PYPROJECT_PATH",
    "distribution_version",
    "version_from_pyproject",
]

#: The distribution name declared as ``project.name`` in pyproject.toml. Every package
#: in ``src/`` is packaged under it; none of them is its own distribution.
DISTRIBUTION = "hyperobjects-spec"

#: ``src/hyperobjects_version/__init__.py`` → ``src/hyperobjects_version`` → ``src`` →
#: the repo root. Resolved from ``__file__`` so the fallback does not depend on where
#: the interpreter was started.
PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"


def version_from_pyproject(path: Path | None = None) -> str | None:
    """Return ``project.version`` from pyproject.toml, or None if it cannot be read.

    Returns None — rather than raising — when the file is absent, which is the ordinary
    case for an installed wheel: the wheel ships the packages, not the source tree's
    pyproject.toml, and on that install path this function is never consulted anyway.
    """
    target = PYPROJECT_PATH if path is None else path
    try:
        with open(target, "rb") as handle:
            data = tomllib.load(handle)
    except OSError:
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    declared = project.get("version")
    return declared if isinstance(declared, str) else None


def _resolve(installed_lookup: Callable[[str], str]) -> str:
    """Resolve the version, installed metadata first and pyproject.toml second.

    ``installed_lookup`` is a parameter so the fallback branch is reachable from a test
    without uninstalling the package or monkeypatching a module global.
    """
    try:
        return installed_lookup(DISTRIBUTION)
    except PackageNotFoundError:
        pass
    declared = version_from_pyproject()
    if declared is not None:
        return declared
    raise RuntimeError(
        f"cannot determine the version of {DISTRIBUTION}: it is not installed "
        f"(no importlib.metadata entry) and no project.version could be read from "
        f"{PYPROJECT_PATH}. Install the package (`pip install -e .`) or run from a "
        f"checkout that still has its pyproject.toml."
    )


@cache
def distribution_version() -> str:
    """The version of the ``hyperobjects-spec`` distribution. See the module docstring."""
    return _resolve(_installed_version)
