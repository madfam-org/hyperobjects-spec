"""Tests for the single version source.

pyproject.toml declares ``project.version`` once, and this repo ships ONE distribution
(``hyperobjects-spec``) containing all six packages. These tests are what keep that a
fact rather than an intention: before ``hyperobjects_version`` existed, the six packages
carried hand-typed literals that had drifted to 0.1.0, 0.2.0 and 1.0.0 while pyproject
said 0.3.0, and nothing in the suite noticed. Now a package that reintroduces a literal
turns this file red the moment it disagrees with pyproject.
"""

import importlib
import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

import pytest

import hyperobjects_version as hv

# Every package in src/ that exposes a __version__. Kept explicit rather than globbed:
# a new package must be added here deliberately, which is the point.
VERSIONED_PACKAGES = [
    "bridge_check",
    "commons_sandbox",
    "fc_spec",
    "hyperobjects_lexicon",
    "hyperobjects_schemas",
    "y4d_spec",
]


def pyproject_version() -> str:
    """Read project.version straight from the repo's pyproject.toml.

    Deliberately does NOT go through hyperobjects_version: this is the independent
    reading the rest of the file is compared against, so it must not share the code
    under test.
    """
    path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with open(path, "rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def test_pyproject_declares_exactly_one_version():
    declared = pyproject_version()
    assert isinstance(declared, str) and declared, "pyproject.toml has no project.version"


def test_the_distribution_name_matches_pyproject():
    path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with open(path, "rb") as handle:
        assert tomllib.load(handle)["project"]["name"] == hv.DISTRIBUTION


@pytest.mark.parametrize("package", VERSIONED_PACKAGES)
def test_every_exposed_version_equals_the_pyproject_version(package):
    module = importlib.import_module(package)
    assert module.__version__ == pyproject_version(), (
        f"{package}.__version__ is {module.__version__!r} but pyproject.toml declares "
        f"{pyproject_version()!r}. Versions are not typed per package any more — see "
        f"hyperobjects_version."
    )


@pytest.mark.parametrize("package", VERSIONED_PACKAGES)
def test_every_package_exports_version_in_all(package):
    module = importlib.import_module(package)
    assert "__version__" in module.__all__


def test_all_packages_agree_with_each_other():
    seen = {p: importlib.import_module(p).__version__ for p in VERSIONED_PACKAGES}
    assert len(set(seen.values())) == 1, f"packages disagree about the version: {seen}"


def test_installed_metadata_agrees_with_pyproject():
    """The installed path. Runs against the editable install CI and contributors use."""
    assert installed_version(hv.DISTRIBUTION) == pyproject_version()


def test_fallback_path_agrees_with_the_installed_path():
    """The uninstalled-checkout path resolves to the same string as the installed one.

    ``_resolve`` takes the metadata lookup as a parameter precisely so this branch is
    reachable: hand it a lookup that raises PackageNotFoundError — exactly what
    importlib.metadata does with no .dist-info present — and the pyproject.toml fallback
    must produce the same answer the real lookup does.
    """

    def not_installed(_name: str) -> str:
        raise PackageNotFoundError(_name)

    fallback = hv._resolve(not_installed)
    assert fallback == hv._resolve(installed_version)
    assert fallback == hv.distribution_version()
    assert fallback == pyproject_version()


def test_version_from_pyproject_reads_the_repo_file_without_an_argument():
    assert hv.version_from_pyproject() == pyproject_version()
    assert hv.PYPROJECT_PATH.is_file()


def test_version_from_pyproject_returns_none_for_a_missing_file(tmp_path):
    assert hv.version_from_pyproject(tmp_path / "nope.toml") is None


def test_version_from_pyproject_returns_none_when_the_table_is_absent(tmp_path):
    empty = tmp_path / "pyproject.toml"
    empty.write_text("[build-system]\nrequires = []\n")
    assert hv.version_from_pyproject(empty) is None


def test_resolution_raises_rather_than_guessing_when_both_paths_fail(monkeypatch):
    """No placeholder version. A wrong version that looks right is the bug being fixed."""

    def not_installed(_name: str) -> str:
        raise PackageNotFoundError(_name)

    monkeypatch.setattr(hv, "PYPROJECT_PATH", Path("/nonexistent/pyproject.toml"))
    with pytest.raises(RuntimeError, match="cannot determine the version"):
        hv._resolve(not_installed)


def test_no_package_hardcodes_a_version_literal():
    """The regression guard: the literals are gone and must not come back."""
    src = Path(__file__).resolve().parents[1] / "src"
    offenders = []
    for init in sorted(src.glob("*/__init__.py")):
        for lineno, line in enumerate(init.read_text().splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("__version__") and "distribution_version" not in stripped:
                offenders.append(f"{init.relative_to(src)}:{lineno}: {stripped}")
    assert not offenders, (
        "these packages type a version instead of deriving it from the distribution: "
        + "; ".join(offenders)
    )
