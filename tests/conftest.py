"""Shared pytest wiring.

The `geometry` marker is declared in pyproject, but a declared marker does nothing on
its own. This hook is what gives it teeth: any test marked `@pytest.mark.geometry` is
skipped — not failed — when cadquery/trimesh cannot import (the [geometry] extra is
absent, or its CAD kernel is missing a system library such as libGL). That matches the
posture the suite already takes with `test_y4d_spec`'s `@geometry_required` skipif: the
geometry lane is opt-in, and its absence is a skip the summary names, never a red run.
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
