"""Both mesh oracles on real STLs, and the oracle-parity note through THE mesh bar.

Synthetic meshes, written as binary STL exactly as a render is: a closed box, an open
box (one face removed), two disjoint boxes, a box plus a disjoint degenerate face, an
inside-out box, and two boxes touching at ONE vertex. The last is the case the two
oracles define differently: trimesh counts bodies by faces sharing an EDGE, geom-core by
faces sharing a VERTEX, so it is one body to geom-core and two to trimesh, and that is
exactly what an `oracle-parity` note must surface.

The trimesh half needs the [geometry] extra; the geom-core half also needs the geom-core
wheel (scripts/qa/install_geom_core.sh) and skips without it. CI's geom-core leg
installs both and runs this module with Y4D_SPEC_MESH_ORACLE=both.
"""

from pathlib import Path

import pytest

# importorskip BEFORE numpy/trimesh (see test_geometry_bodies.py): a base install must
# skip this module, not error at collection.
trimesh = pytest.importorskip("trimesh")
np = pytest.importorskip("numpy")

from y4d_spec.geometry import _judge_stl  # noqa: E402
from y4d_spec.mesh_oracle import (  # noqa: E402
    ENV_VAR,
    RULE_ID,
    GeomCoreOracle,
    TrimeshOracle,
    geom_core_available,
    oracle_parity_note,
)

pytestmark = pytest.mark.geometry

needs_geom_core = pytest.mark.skipif(
    not geom_core_available(),
    reason="requires geom-core (scripts/qa/install_geom_core.sh)",
)


def _box(offset=(0.0, 0.0, 0.0)):
    box = trimesh.creation.box((10, 10, 10))
    box.apply_translation(offset)
    return box


def _closed():
    return _box()


def _open():
    box = _box()
    return trimesh.Trimesh(box.vertices, box.faces[:-1], process=False)


def _two_bodies():
    return trimesh.util.concatenate([_box(), _box((30, 0, 0))])


def _degenerate_face():
    # A zero-area face (a repeated vertex) floating inside the box, touching nothing.
    box = _box()
    vertices = np.vstack([box.vertices, [[1, 1, 1], [1, 1, 1], [2, 2, 2]]])
    faces = np.vstack([box.faces, [[8, 9, 10]]])
    return trimesh.Trimesh(vertices, faces, process=False)


def _inverted():
    box = _box()
    box.invert()
    return box


def _touching_at_a_vertex():
    return trimesh.util.concatenate([_box(), _box((10, 10, 10))])


# name -> (mesh factory, watertight, signed volume, trimesh bodies, geom-core bodies)
FIXTURES = {
    "closed-box": (_closed, True, 1000.0, 1, 1),
    "open-box": (_open, False, 750.0, 1, 1),
    "two-bodies": (_two_bodies, True, 2000.0, 2, 2),
    "degenerate-face": (_degenerate_face, False, 1000.0, 2, 2),
    "inverted-box": (_inverted, True, -1000.0, 1, 1),
    "touching-at-a-vertex": (_touching_at_a_vertex, True, 2000.0, 2, 1),
}


def _stl(tmp_path, name):
    path = tmp_path / f"{name}.stl"
    FIXTURES[name][0]().export(path, file_type="stl")
    return str(path)


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_trimesh_oracle(tmp_path, name):
    _factory, watertight, volume, bodies, _gc = FIXTURES[name]
    measure = TrimeshOracle().measure(_stl(tmp_path, name))
    assert measure.oracle == "trimesh"
    assert measure.watertight is watertight
    assert measure.volume == pytest.approx(volume, rel=1e-9)
    assert measure.bodies == bodies
    assert measure.boundary_edges == (None if watertight else 3 if name == "open-box" else 1)


@needs_geom_core
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_geom_core_oracle(tmp_path, name):
    _factory, watertight, volume, _tm, bodies = FIXTURES[name]
    measure = GeomCoreOracle().measure(_stl(tmp_path, name))
    assert measure.oracle == "geom-core"
    assert measure.watertight is watertight
    # Signed: the inside-out box is -1000, which get_volume() (absolute) would hide.
    assert measure.volume == pytest.approx(volume, rel=1e-9)
    assert measure.bodies == bodies


@needs_geom_core
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_parity_note_fires_exactly_where_the_oracles_differ(tmp_path, name):
    path = _stl(tmp_path, name)
    note = oracle_parity_note(
        "(m, p)", TrimeshOracle().measure(path), GeomCoreOracle().measure(path)
    )
    if name == "touching-at-a-vertex":
        assert note is not None and "bodies trimesh=2 geom-core=1" in note
        assert "watertight" not in note and "volume" not in note
    else:
        assert note is None


@needs_geom_core
def test_both_keeps_the_trimesh_verdict_and_adds_the_note(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "both")
    agree = _judge_stl(_stl(tmp_path, "two-bodies"), mode="m", part="p", preset=None,
                       printability=False, engine="cadquery")
    assert agree.ok and agree.bodies == 2
    assert not [n for n in agree.notes if n.startswith(RULE_ID)]

    differ = _judge_stl(_stl(tmp_path, "touching-at-a-vertex"), mode="m", part="p",
                        preset=None, printability=False, engine="cadquery")
    assert differ.ok and differ.bodies == 2  # the verdict is still trimesh's
    parity = [n for n in differ.notes if n.startswith(RULE_ID)]
    assert len(parity) == 1
    assert parity[0].startswith(f"{RULE_ID}: (m, p, cadquery): trimesh and geom-core disagree")


@needs_geom_core
def test_geomcore_selection_takes_the_verdict_from_geom_core(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "geomcore")
    check = _judge_stl(_stl(tmp_path, "touching-at-a-vertex"), mode="m", part="p",
                       preset=None, printability=False, engine="cadquery")
    assert check.ok and check.bodies == 1
    assert not [n for n in check.notes if n.startswith(RULE_ID)]

    inverted = _judge_stl(_stl(tmp_path, "inverted-box"), mode="m", part="p",
                          preset=None, printability=False, engine="cadquery")
    assert not inverted.ok
    assert any("volume is -1000.0000 (must be > 0)" in p for p in inverted.problems)


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_default_selection_is_todays_trimesh_verdict(tmp_path, monkeypatch, name):
    monkeypatch.delenv(ENV_VAR, raising=False)
    _factory, watertight, volume, bodies, _gc = FIXTURES[name]
    check = _judge_stl(_stl(tmp_path, name), mode="m", part="p", preset=None,
                       printability=False, engine="cadquery")
    assert check.watertight is watertight and check.bodies == bodies
    assert check.volume == pytest.approx(volume, rel=1e-9)
    assert check.ok is (watertight and volume > 0)
    assert not [n for n in check.notes if n.startswith(RULE_ID)]


def test_check_render_refuses_an_unknown_oracle(monkeypatch, capsys):
    from y4d_spec.cli import main

    monkeypatch.setenv(ENV_VAR, "geom-core")
    thimble = Path(__file__).parent / "fixtures" / "y4d" / "thimble"
    assert main(["check", "--render", str(thimble)]) == 2
    assert f"ERROR {ENV_VAR}='geom-core' is not one of" in capsys.readouterr().out
