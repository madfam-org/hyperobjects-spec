"""Assembly placement and closure (ASM-1 §3.4–3.6), against hand-computed transforms.

Conventions used in the expected matrices below. A frame's matrix H(F) has columns
(x, y = n × x, n, origin). A mate places b with T_b = T_a · H(F_a) · Flip · Rz(θ) ·
H(F_b)^-1, Flip = diag(1, -1, -1). Every expected matrix is derived by hand in the test's
docstring, by pushing a model point through those factors right to left.
"""

import math

import pytest

from assembly_helpers import (
    assembly,
    assert_matrix,
    cartridge,
    codes,
    mate,
    resolver,
    standard,
)
from y4d_spec.assembly import validate_assembly
from y4d_spec.assembly.transforms import (
    IDENTITY,
    flip_rz,
    mate_transform,
    matmul,
    rigid_inverse,
    rotation_z,
)


# ── transforms ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("deg", [0, 30, 90, 137.5, 180, 270])
def test_flip_rz_is_an_involution(deg):
    """M = Flip·Rz(θ) is a half-turn, so M·M = I — the mate relation is symmetric."""
    m = flip_rz(math.radians(deg))
    assert_matrix(matmul(m, m), IDENTITY)


def test_rigid_inverse():
    m = matmul(((1, 0, 0, 3), (0, 1, 0, -4), (0, 0, 1, 5), (0, 0, 0, 1)), rotation_z(0.7))
    assert_matrix(matmul(m, rigid_inverse(m)), IDENTITY)
    assert_matrix(matmul(rigid_inverse(m), m), IDENTITY)


def test_mate_transform_matches_the_contract_formula():
    t_a = matmul(((1, 0, 0, 1), (0, 1, 0, 2), (0, 0, 1, 3), (0, 0, 0, 1)), rotation_z(0.3))
    h_a = ((0, 1, 0, 0), (0, 0, 1, 0), (1, 0, 0, 10), (0, 0, 0, 1))
    h_b = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 48), (0, 0, 0, 1))
    got = mate_transform(t_a, h_a, h_b, math.radians(90))
    want = matmul(t_a, h_a, ((1, 0, 0, 0), (0, -1, 0, 0), (0, 0, -1, 0), (0, 0, 0, 1)),
                  rotation_z(math.radians(90)), rigid_inverse(h_b))
    assert_matrix(got, want)


# ── two parts: a NEMA 17 face on a bracket ────────────────────────────────────
def _bracket_and_motor(rotation_index=0, **bracket_params):
    return assembly(
        [cartridge("bracket", **bracket_params), standard("motor", "nema-17-48mm-test")],
        [mate("m1", "bracket.motor_face", "motor.face", rotation_index)],
    )


# The motor face sits at z = 48 of the motor's model (body 0..48, shaft above), normal
# +z. The bracket's face is its plate top, z = plate_thick = 5, normal +z. Right to left
# for rotation_index k (θ = 90°·k): translate by -48, Rz(θ), Flip (x, y, z) → (x, -y, -z),
# translate by +5. So a motor point (x, y, z) lands at:
#   k=0: ( x, -y, 53 - z)      k=1: Rz90 (x,y)→(-y, x) then Flip → (-y, -x, 53 - z)
#   k=2: (-x,  y, 53 - z)      k=3: Rz270 (x,y)→( y,-x) then Flip → ( y,  x, 53 - z)
# The motor body hangs upside down above the plate with its face on the plate top and
# its shaft pointing down through it — a motor bolted to a flat bracket.
EXPECTED_FLAT = {
    0: ((1, 0, 0, 0), (0, -1, 0, 0), (0, 0, -1, 53), (0, 0, 0, 1)),
    1: ((0, -1, 0, 0), (-1, 0, 0, 0), (0, 0, -1, 53), (0, 0, 0, 1)),
    2: ((-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, -1, 53), (0, 0, 0, 1)),
    3: ((0, 1, 0, 0), (1, 0, 0, 0), (0, 0, -1, 53), (0, 0, 0, 1)),
}


@pytest.mark.parametrize("k", [0, 1, 2, 3])
def test_two_parts_place_exactly_for_every_rotation_of_symmetry_4(k):
    report = validate_assembly(_bracket_and_motor(k), resolver())
    assert report.ok, report.findings
    assert_matrix(report.placements["bracket"], IDENTITY)
    assert_matrix(report.placements["motor"], EXPECTED_FLAT[k])
    (m1,) = report.mates
    assert m1.in_tree and m1.ok and m1.symmetry == 4 and m1.theta_deg == 90 * k
    assert m1.origin_mm < 1e-9 and m1.normal_deg < 1e-9 and m1.x_axis_deg < 1e-9


def test_rotation_index_must_be_below_the_symmetry():
    report = validate_assembly(_bracket_and_motor(4), resolver())
    assert ("rotation", "m1") in codes(report)
    assert ("unreachable", "motor") in codes(report)


def test_a_parameter_moves_the_frame_and_so_the_part():
    """plate_thick = 7.5 → the face is at z = 7.5, so the motor's z offset is 55.5."""
    report = validate_assembly(_bracket_and_motor(0, plate_thick=7.5), resolver())
    assert report.ok, report.findings
    assert_matrix(report.placements["motor"],
                  ((1, 0, 0, 0), (0, -1, 0, 0), (0, 0, -1, 55.5), (0, 0, 0, 1)))


def _wall(root="bracket"):
    return assembly(
        [cartridge("bracket", mode="angle", plate_thick=6), standard("motor", "nema-17-48mm-test")],
        [mate("m1", "bracket.wall_face", "motor.face")],
        root=root,
    )


# Wall face: origin (plate_thick, 0, wall_height) = (6, 0, 30), n = (1, 0, 0),
# x = (0, 1, 0), so y = n × x = (0, 0, 1). A local point (u, v, w) of that frame is
# (w + 6, u, v + 30) in the bracket. Flip·H(F_motor)^-1 sends a motor point (x, y, z) to
# (x, -y, 48 - z), hence world = (54 - z, x, 30 - y). The motor face centre (0, 0, 48)
# lands on (6, 0, 30); its normal +z becomes -x, against the wall's +x; the body (z < 48)
# extends to x > 6, on the partner side of the wall.
EXPECTED_WALL = ((0, 0, -1, 54), (1, 0, 0, 0), (0, -1, 0, 30), (0, 0, 0, 1))


def test_a_vertical_wall_face_places_the_motor_sideways():
    report = validate_assembly(_wall(), resolver())
    assert report.ok, report.findings
    assert_matrix(report.placements["motor"], EXPECTED_WALL)


def test_traversing_a_mate_from_b_gives_the_inverse_placement():
    """Root = motor: the bracket gets EXPECTED_WALL^-1, i.e. R^T and -R^T·t =
    (0, 30, 54) — the same relative pose seen from the other side."""
    report = validate_assembly(_wall(root="motor"), resolver())
    assert report.ok, report.findings
    assert_matrix(report.placements["motor"], IDENTITY)
    assert_matrix(report.placements["bracket"],
                  ((0, 1, 0, 0), (0, 0, -1, 30), (-1, 0, 0, 54), (0, 0, 0, 1)))
    assert_matrix(report.placements["bracket"], rigid_inverse(EXPECTED_WALL))


# ── continuous symmetry: a pulley on a shaft at angle_deg ─────────────────────
def test_angle_deg_on_a_continuous_interface():
    """Shaft tip at (0, 0, 48 + 24) normal +z; with no x_axis the reference x is the
    world axis least aligned with n, (1, 0, 0). The pulley bore: origin 0, n = -z, x =
    (1, 0, 0), so y = n × x = (0, -1, 0) and H(F_bore) = Flip. Then T = T(0,0,72)·Flip·
    Rz(θ)·Flip = T(0,0,72)·Rz(-θ): the pulley sits upright on the tip, turned by -θ."""
    doc = assembly(
        [standard("motor", "nema-17-48mm-test"), standard("pulley", "gt2-pulley-test")],
        [mate("m1", "motor.shaft", "pulley.bore", angle_deg=30)],
    )
    report = validate_assembly(doc, resolver())
    assert report.ok, report.findings
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    assert_matrix(report.placements["pulley"],
                  ((c, s, 0, 0), (-s, c, 0, 0), (0, 0, 1, 72), (0, 0, 0, 1)))
    assert report.mates[0].x_axis_deg is None  # continuous: no x-axis residual


def test_shaft_length_parameter_moves_the_pulley():
    doc = assembly(
        [standard("motor", "nema-17-48mm-test", shaft_length=30),
         standard("pulley", "gt2-pulley-test")],
        [mate("m1", "motor.shaft", "pulley.bore", angle_deg=0)],
    )
    report = validate_assembly(doc, resolver())
    assert report.ok, report.findings
    assert report.placements["pulley"][2][3] == pytest.approx(78)


def test_rotation_index_on_continuous_and_angle_on_discrete_are_errors():
    cont = assembly(
        [standard("motor", "nema-17-48mm-test"), standard("pulley", "gt2-pulley-test")],
        [mate("m1", "motor.shaft", "pulley.bore", rotation_index=0)],
    )
    assert ("rotation", "m1") in codes(validate_assembly(cont, resolver()))
    disc = assembly(
        [cartridge("bracket"), standard("motor", "nema-17-48mm-test")],
        [mate("m1", "bracket.motor_face", "motor.face", angle_deg=90)],
    )
    assert ("rotation", "m1") in codes(validate_assembly(disc, resolver()))


# ── a 4-cycle of elbows ───────────────────────────────────────────────────────
def _ring(e3_arm=None, m3_rotation=0, m4_rotation=0):
    """Four elbows, each turning 90° in the XY plane: inlet at 0 facing -x, outlet at
    (arm, arm, 0) facing +y, x-axis +z. Chained outlet → inlet and back to e1."""
    e3 = standard("e3", "elbow-test", arm=e3_arm) if e3_arm else standard("e3", "elbow-test")
    return assembly(
        [standard("e1", "elbow-test"), standard("e2", "elbow-test"), e3,
         standard("e4", "elbow-test")],
        [
            mate("m1", "e1.outlet", "e2.inlet"),
            mate("m2", "e2.outlet", "e3.inlet"),
            mate("m3", "e3.outlet", "e4.inlet", m3_rotation),
            mate("m4", "e4.outlet", "e1.inlet", m4_rotation),
        ],
    )


def test_a_square_ring_closes():
    """e2 = T(50,50,0)·Rz(90°): its inlet normal -x turns to -y, against e1's outlet +y,
    and the x-axis (+z) is unchanged (θ = 0). Continuing: e3 = T(0,100,0)·Rz(180°),
    e4 = T(-50,50,0)·Rz(270°), whose outlet lands at (0,0,0) facing +x — exactly e1's
    inlet. BFS from e1 places e2 (m1) and e4 (m4) first, then e3 (m2), so m3 is the
    mate that closes the cycle, and it holds."""
    report = validate_assembly(_ring(), resolver())
    assert report.ok, report.findings
    rz = {d: rotation_z(math.radians(d)) for d in (90, 180, 270)}

    def placed(tx, ty, deg):
        return matmul(((1, 0, 0, tx), (0, 1, 0, ty), (0, 0, 1, 0), (0, 0, 0, 1)), rz[deg])

    assert_matrix(report.placements["e2"], placed(50, 50, 90))
    assert_matrix(report.placements["e3"], placed(0, 100, 180))
    assert_matrix(report.placements["e4"], placed(-50, 50, 270))
    tree = {m.mate_id: m.in_tree for m in report.mates}
    assert tree == {"m1": True, "m2": True, "m3": False, "m4": True}
    for m in report.mates:
        assert m.ok and m.origin_mm < 1e-9 and m.normal_deg < 1e-9 and m.x_axis_deg < 1e-9


def test_a_ring_that_does_not_close_reports_its_residuals():
    """e3's arm = 55 (in range): its outlet moves to (-55, 45, 0) while e4's inlet,
    placed from e1 through m4, stays at (-50, 50, 0). The closing mate m3 is off by
    √(5² + 5²) = 7.0711 mm, with the orientation still exact."""
    report = validate_assembly(_ring(e3_arm=55), resolver())
    assert not report.ok
    assert codes(report) == [("closure", "m3")]
    m3 = next(m for m in report.mates if m.mate_id == "m3")
    assert not m3.in_tree and not m3.ok
    assert m3.origin_mm == pytest.approx(math.sqrt(50))
    assert m3.normal_deg == pytest.approx(0, abs=1e-9)
    assert m3.x_axis_deg == pytest.approx(0, abs=1e-9)
    assert "7.0711 mm" in report.errors[0].message and "a cycle" in report.errors[0].message


def test_a_twisted_ring_fails_on_orientation():
    """m4 at rotation_index 1 turns e4 a quarter turn about e1's inlet normal (the x
    axis), so e4's inlet normal, which should face e3 in the XY plane, points along z:
    m3's normals are 90° from antiparallel, and the origins no longer meet."""
    report = validate_assembly(_ring(m4_rotation=1), resolver())
    assert codes(report) == [("closure", "m3")]
    m3 = next(m for m in report.mates if m.mate_id == "m3")
    assert m3.normal_deg == pytest.approx(90)
    assert m3.origin_mm > 0.05


def test_a_closing_mate_at_another_index_of_the_symmetry_warns():
    """m3 is not in the BFS tree, so its rotation_index never placed anything: the ring
    still closes (x-axes agree modulo 90°), but the document's index 2 is not the one
    the geometry realises (0) — a warning, not an error."""
    report = validate_assembly(_ring(m3_rotation=2), resolver())
    assert report.ok, report.findings
    assert codes(report, "warning") == [("rotation", "m3")]
    assert "closes at rotation_index 0" in report.warnings[0].message
