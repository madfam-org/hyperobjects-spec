"""_bodies() must count components and sign volumes exactly as split() did —
without materialising a Trimesh per body (which cost 7 GB on a 2.5 M-face
multi-body render and killed CI runners)."""

import pytest

# importorskip BEFORE numpy, not after: numpy arrives with the [geometry] extra (trimesh
# depends on it) and on a base install it is absent, so a module-scope `import numpy`
# raises at COLLECTION time and interrupts the whole run — not the skip the README
# promises ("tests marked geometry skip rather than fail when cadquery/trimesh cannot
# import"). A collection error is not a skip: pytest reports it as an error and stops,
# so the base-install lane loses every other test in the suite too.
trimesh = pytest.importorskip("trimesh")
np = pytest.importorskip("numpy")

from y4d_spec.geometry import _bodies  # noqa: E402

# The suite-wide marker conftest.py keys its skip off, so this module is named in the
# `-ra` summary alongside the other geometry modules instead of quietly vanishing.
pytestmark = pytest.mark.geometry


def _three_bodies_one_inverted():
    box = trimesh.creation.box((10, 10, 10))
    ball = trimesh.creation.icosphere(3, 4.0)
    ball.apply_translation((30, 0, 0))
    inverted = trimesh.creation.box((5, 5, 5))
    inverted.apply_translation((0, 30, 0))
    inverted.invert()
    mesh = trimesh.util.concatenate([box, ball, inverted])
    mesh.merge_vertices()
    return mesh


def test_bodies_matches_split_counts_and_signed_volumes():
    mesh = _three_bodies_one_inverted()
    ours = sorted(volume for _faces, volume in _bodies(mesh))
    reference = sorted(float(body.volume) for body in mesh.split(only_watertight=False))
    assert len(ours) == len(reference) == 3
    assert np.allclose(ours, reference, rtol=1e-9)
    assert ours[0] < 0  # the inverted box reads negative, as split() reported it
    assert abs(ours[-1] - 1000.0) < 1e-6


def test_bodies_total_equals_mesh_volume():
    mesh = _three_bodies_one_inverted()
    assert abs(sum(v for _f, v in _bodies(mesh)) - float(mesh.volume)) < 1e-6


def test_bodies_empty_mesh():
    assert _bodies(trimesh.Trimesh()) == []
