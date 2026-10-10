"""The laminate calculator against textbook cases.

Two kinds of check: closed forms that hold for any material (a single isotropic plate,
symmetric stacks have B = 0, an antisymmetric cross-ply has B11 = −B22, an antisymmetric
angle-ply has only B16/B26), and the worked examples of Kaw, *Mechanics of Composite
Materials* (2nd ed., CRC 2006) for a graphite/epoxy lamina (E1 = 181 GPa, E2 = 10.3 GPa,
ν12 = 0.28, G12 = 7.17 GPa): Example 2.6 (Q), Example 2.7 (Q̄ at 60°) and Example 4.2
(the [0/30/−45] laminate, 5 mm plies), compared to the four significant digits printed.
"""

from __future__ import annotations

import math

import pytest

from hyperobjects_sheet.laminate import (
    Layer,
    isotropic_layer,
    laminate,
    reduced_stiffness,
    rotate,
)

GPA = 1e9
T300 = {"E1": 181 * GPA, "E2": 10.3 * GPA, "G12": 7.17 * GPA, "nu12": 0.28}


def ply(angle: float, t: float = 0.005) -> Layer:
    return Layer(name=f"ply{angle:g}", thickness=t, angle_deg=angle, **T300)


def close4(actual: float, printed: float) -> bool:
    """Equal to the four significant digits a textbook prints."""
    return math.isclose(actual, printed, rel_tol=6e-4)


def test_kaw_example_2_6_reduced_stiffness():
    q = reduced_stiffness(**T300)
    printed = [[181.8, 2.897, 0], [2.897, 10.35, 0], [0, 0, 7.17]]
    for i in range(3):
        for j in range(3):
            if printed[i][j] == 0:
                assert q[i][j] == 0
            else:
                assert close4(q[i][j] / GPA, printed[i][j]), (i, j, q[i][j])


def test_kaw_example_2_7_transformed_stiffness_at_60_degrees():
    qbar = rotate(reduced_stiffness(**T300), 60)
    printed = [[23.65, 32.46, 20.05], [32.46, 109.4, 54.19], [20.05, 54.19, 36.74]]
    for i in range(3):
        for j in range(3):
            assert close4(qbar[i][j] / GPA, printed[i][j]), (i, j, qbar[i][j])


def test_kaw_example_4_2_abd_of_0_30_m45():
    r = laminate([ply(0), ply(30), ply(-45)])
    a = [[1.739e9, 3.884e8, 5.663e7], [3.884e8, 4.533e8, -1.141e8],
         [5.663e7, -1.141e8, 4.525e8]]
    b = [[-3.129e6, 9.855e5, -1.072e6], [9.855e5, 1.158e6, -1.072e6],
         [-1.072e6, -1.072e6, 9.855e5]]
    d = [[3.343e4, 6.461e3, -5.240e3], [6.461e3, 9.320e3, -5.596e3],
         [-5.240e3, -5.596e3, 7.663e3]]
    for mine, printed in ((r.A, a), (r.B, b), (r.D, d)):
        for i in range(3):
            for j in range(3):
                assert close4(mine[i][j], printed[i][j]), (i, j, mine[i][j], printed[i][j])
    assert r.coupled
    assert any("D16/D26" in n for n in r.notes)


def test_single_isotropic_plate_is_the_plate_formula():
    E, nu, t = 4.5e9, 0.3, 3e-4
    r = laminate([isotropic_layer("plate", E, nu, t)])
    q11 = E / (1 - nu * nu)
    assert math.isclose(r.A[0][0], q11 * t)
    assert math.isclose(r.D[0][0], q11 * t ** 3 / 12)
    assert math.isclose(r.D[0][1], nu * q11 * t ** 3 / 12)
    assert r.B == [[0.0] * 3 for _ in range(3)]
    assert not r.coupled
    eff = r.effective()
    assert math.isclose(eff["E1t"], E * t)
    assert math.isclose(eff["nu12"], nu)
    assert math.isclose(eff["G12t"], E / (2 * (1 + nu)) * t)


@pytest.mark.parametrize("angles", [(0, 90, 90, 0), (45, -45, -45, 45), (30, 0, 30)])
def test_symmetric_stacks_have_no_coupling(angles):
    r = laminate([ply(a) for a in angles])
    assert not r.coupled and r.coupling_ratio == 0.0
    assert r.B == [[0.0] * 3 for _ in range(3)]


def test_antisymmetric_cross_ply_b11_is_minus_b22():
    h = 0.005
    r = laminate([ply(0, h), ply(90, h)])
    q = reduced_stiffness(**T300)
    expected = h * h / 2 * (q[1][1] - q[0][0])
    assert math.isclose(r.B[0][0], expected, rel_tol=1e-12)
    assert math.isclose(r.B[1][1], -expected, rel_tol=1e-12)
    assert r.B[0][1] == 0 and r.B[2][2] == 0 and r.B[0][2] == 0
    assert r.coupled


def test_antisymmetric_angle_ply_couples_only_through_b16_b26():
    r = laminate([ply(45), ply(-45), ply(45), ply(-45)])
    for i, j in ((0, 0), (1, 1), (0, 1), (2, 2)):
        assert r.B[i][j] == 0, (i, j)
    assert r.B[0][2] != 0 and r.B[1][2] != 0
    assert r.A[0][2] == 0 and r.D[0][2] == 0   # but no A16 and no D16


def test_rotation_by_90_swaps_the_axes_and_360_is_identity():
    q = reduced_stiffness(**T300)
    q90 = rotate(q, 90)
    assert math.isclose(q90[0][0], q[1][1]) and math.isclose(q90[1][1], q[0][0])
    q360 = rotate(q, 360)
    for i in range(3):
        for j in range(3):
            assert math.isclose(q360[i][j], q[i][j], abs_tol=1e-6 * q[0][0])


def test_bimetal_prestrain_curls_towards_the_shrinking_layer():
    """Two equal isotropic layers, the bottom one wanting to shrink by e: Timoshenko's
    bimetal strip gives κ = 3e / (2h) for equal thickness and modulus (h = total)."""
    E, nu, t, e = 2e9, 0.3, 1e-4, -0.01
    bottom = Layer(name="b", E1=E, E2=E, G12=E / 2.6, nu12=nu, thickness=t, prestrain=(e, e, 0))
    top = Layer(name="t", E1=E, E2=E, G12=E / 2.6, nu12=nu, thickness=t)
    r = laminate([bottom, top])
    assert not r.coupled   # identical layers: B = 0, the curl comes from asymmetric strain
    k = r.prestrain_curvature
    assert math.isclose(k[0], 3 * (-e) / (2 * (2 * t)), rel_tol=1e-9)   # +75 1/m
    assert math.isclose(k[0], k[1]) and k[2] == 0
    assert math.isclose(r.prestrain_strain[0], e / 2)


def test_card_bending_replaces_only_the_own_term():
    E, nu, t = 1e6, 0.3, 1e-3
    q11 = E / (1 - nu * nu)
    own = [[1e-6, 0, 0], [0, 1e-6, 0], [0, 0, 1e-7]]
    soft = Layer(name="cloth", E1=E, E2=E, G12=E / 2.6, nu12=nu, thickness=t, own_bending=own)
    r = laminate([soft, soft])
    zbar = t / 2
    assert math.isclose(r.D[0][0], 2 * (1e-6 + q11 * t * zbar * zbar))
    assert soft.bending_source == "card"


def test_a_non_positive_definite_lamina_is_refused():
    with pytest.raises(ValueError, match="positive definite"):
        Layer(name="bad", E1=1.0, E2=1.0, G12=1.0, nu12=1.2, thickness=1e-3)
    with pytest.raises(ValueError, match="positive"):
        Layer(name="bad", E1=0.0, E2=1.0, G12=1.0, nu12=0.1, thickness=1e-3)
    with pytest.raises(ValueError):
        laminate([])
