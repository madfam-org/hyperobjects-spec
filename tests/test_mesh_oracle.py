"""The mesh oracle seam (y4d_spec.mesh_oracle), the parts that need no CAD kernel.

Selection is Y4D_SPEC_MESH_ORACLE. Everything here runs on a base install: the
selection rules, the parity comparison, and the geom-core adapter driven through a fake
`geom_core_py` module, so the adapter's contract (signed volume, silenced native stdout,
a load failure that raises) is held even where the real wheel cannot be installed. The
real geom-core and trimesh measurements are in test_mesh_oracle_geometry.py.
"""

import os
import sys
import types

import pytest

from y4d_spec import mesh_oracle
from y4d_spec.mesh_oracle import (
    ENV_VAR,
    RULE_ID,
    GeomCoreOracle,
    MeshMeasure,
    MeshOracleError,
    oracle_parity_note,
    require_selection,
    selected_oracle,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "trimesh"), ("", "trimesh"), ("  ", "trimesh"), ("trimesh", "trimesh"),
     ("geomcore", "geomcore"), ("both", "both"), (" BOTH ", "both")],
)
def test_selection_reads_the_variable_and_defaults_to_trimesh(value, expected):
    env = {} if value is None else {ENV_VAR: value}
    assert selected_oracle(env) == expected


@pytest.mark.parametrize("value", ["geom-core", "trimsh", "1", "all"])
def test_an_unknown_selection_is_an_error_not_a_silent_default(value):
    with pytest.raises(MeshOracleError, match="is not one of trimesh, geomcore, both"):
        selected_oracle({ENV_VAR: value})


def test_asking_for_geom_core_without_it_is_refused(monkeypatch):
    # None in sys.modules makes `import geom_core_py` raise ImportError.
    monkeypatch.setitem(sys.modules, mesh_oracle.GEOM_CORE_MODULE, None)
    assert require_selection({}) == "trimesh"  # the default never needs geom-core
    for selection in ("geomcore", "both"):
        with pytest.raises(MeshOracleError, match="install_geom_core.sh"):
            require_selection({ENV_VAR: selection})


def _m(oracle, watertight=True, volume=1000.0, bodies=1):
    return MeshMeasure(oracle=oracle, watertight=watertight, volume=volume, bodies=bodies)


def test_agreement_is_silent():
    assert oracle_parity_note("(m, p)", _m("trimesh"), _m("geom-core")) is None
    # Inside the 1e-6 relative volume band.
    near = _m("geom-core", volume=1000.0 * (1 + 5e-7))
    assert oracle_parity_note("(m, p)", _m("trimesh"), near) is None
    zero = oracle_parity_note("(m, p)", _m("trimesh", volume=0.0), _m("geom-core", volume=0.0))
    assert zero is None


def test_each_disagreement_is_named_in_one_note():
    note = oracle_parity_note(
        "(m, p, cadquery)",
        _m("trimesh", watertight=True, volume=1000.0, bodies=2),
        _m("geom-core", watertight=False, volume=1000.01, bodies=1),
    )
    assert note.startswith(f"{RULE_ID}: (m, p, cadquery): trimesh and geom-core disagree — ")
    assert "watertight trimesh=True geom-core=False" in note
    assert "bodies trimesh=2 geom-core=1" in note
    assert "volume trimesh=1000.000000 geom-core=1000.010000" in note
    assert "> 1e-06" in note


def test_volume_outside_the_band_and_sign_flips_are_disagreements():
    outside = _m("geom-core", volume=1000.0 * (1 + 2e-6))
    assert "volume" in oracle_parity_note("t", _m("trimesh"), outside)
    flipped = _m("geom-core", volume=-1000.0)
    assert "volume" in oracle_parity_note("t", _m("trimesh"), flipped)


def test_an_unmeasured_body_count_is_a_disagreement_not_agreement():
    note = oracle_parity_note("t", _m("trimesh", bodies=None), _m("geom-core", bodies=1))
    assert "bodies trimesh=unmeasured geom-core=1" in note


def _fake_geom_core(*, loads=True, volume=-12.5, bodies=3, watertight=True, boundary=0):
    module = types.ModuleType(mesh_oracle.GEOM_CORE_MODULE)

    class Analyzer:
        def load_stl(self, path):
            # What geom-core v0.1.0 does from C++: a std::cout line on descriptor 1.
            os.write(1, b"Loaded STL: 8 vertices, 12 triangles\n")
            self.path = path
            return loads

        def get_volume(self):  # the ABSOLUTE volume; the adapter must not read it
            return abs(volume)

        def assess_integrity(self, scale_hint=None):
            return types.SimpleNamespace(
                watertight=watertight, volume=volume, body_count=bodies,
                boundary_edges=boundary,
            )

    module.Analyzer = Analyzer
    return module


def test_geom_core_adapter_reads_the_signed_volume_and_silences_native_stdout(
    monkeypatch, capfd
):
    monkeypatch.setitem(sys.modules, mesh_oracle.GEOM_CORE_MODULE, _fake_geom_core())
    print("before the load")
    measure = GeomCoreOracle().measure("part.stl")
    print("after the load")
    out = capfd.readouterr().out
    assert "Loaded STL" not in out
    assert "before the load" in out and "after the load" in out
    assert measure == MeshMeasure(
        oracle="geom-core", watertight=True, volume=-12.5, bodies=3, boundary_edges=0
    )


def test_geom_core_adapter_raises_when_the_load_fails(monkeypatch):
    monkeypatch.setitem(
        sys.modules, mesh_oracle.GEOM_CORE_MODULE, _fake_geom_core(loads=False)
    )
    with pytest.raises(MeshOracleError, match="could not load part.stl"):
        GeomCoreOracle().measure("part.stl")


def test_geom_core_adapter_raises_when_geom_core_is_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, mesh_oracle.GEOM_CORE_MODULE, None)
    with pytest.raises(MeshOracleError, match="not importable"):
        GeomCoreOracle().measure("part.stl")
