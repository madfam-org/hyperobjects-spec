"""Shared pytest wiring.

The `geometry` marker is declared in pyproject, but a declared marker does nothing on
its own. This hook is what gives it teeth: any test marked `@pytest.mark.geometry` is
skipped — not failed — when cadquery/trimesh cannot import: the [geometry] extra is
absent, or the CAD kernel's C extension cannot resolve one of the system libraries it
links against. WHICH library is missing depends on the machine and is never worth
guessing at — libgl1 is the one people install and libXrender.so.1 is the one that was
actually unresolved on the CI runner — so the workflow prints the import traceback and
the unresolved soname instead. This matches the posture the suite already takes with
`test_y4d_spec`'s `@geometry_required` skipif: the geometry lane is opt-in, and its
absence is a skip the summary names, never a red run.

That leniency is for a contributor's machine and not for CI, where a skip is invisible
inside a green build: the workflow installs the kernel's system libraries and fails the
job outright when `geometry_available()` is False, so the geometry tests either run there
or nothing reports success.
"""

import pytest


def _geometry_available() -> bool:
    try:
        from y4d_spec.geometry import geometry_available
    except Exception:
        return False
    return geometry_available()


GEOMETRY_AVAILABLE = _geometry_available()


def pytest_collection_modifyitems(config, items):
    if GEOMETRY_AVAILABLE:
        return
    skip = pytest.mark.skip(
        reason="requires the [geometry] extra (cadquery + trimesh, importable)"
    )
    for item in items:
        if "geometry" in item.keywords:
            item.add_marker(skip)
