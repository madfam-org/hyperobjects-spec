"""Rigid 4×4 transforms for assembly placement (ASM-1 §3.4), pure Python.

A matrix is a tuple of four row tuples, row-major, acting on column vectors:
`p_world = M · p_local`. Every matrix built here is rigid (orthonormal rotation block,
last row `0 0 0 1`), so its inverse is the transpose of the rotation block and the
rotated, negated translation — no general inversion is ever needed.

The placement of one mate, `a` already placed:

    T_b = T_a · H(F_a) · Flip · Rz(θ) · H(F_b)^-1

`H(F)` is the frame's own matrix (columns x, y = n × x, n, origin), from
`y4d_spec.frame_eval.Frame.homogeneous`. `Flip` is a rotation of π about the frame
x-axis (n → −n, y → −y, x unchanged). `M = Flip · Rz(θ)` is itself a rotation of π
(about the in-plane axis at −θ/2), so `M^-1 = M` and the relation is symmetric:
traversing the same mate from `b` gives `T_a = T_b · H(F_b) · M · H(F_a)^-1`. The
validator relies on that and places a component from whichever side reaches it first.

numpy is not a base dependency of this package, and 4×4 rigid algebra does not need it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

__all__ = [
    "FLIP",
    "IDENTITY",
    "Matrix",
    "Vector",
    "angle_between_deg",
    "apply_point",
    "apply_vector",
    "column",
    "flip_rz",
    "matmul",
    "mate_transform",
    "rigid_inverse",
    "rotation_z",
    "round_matrix",
]

Vector = tuple[float, float, float]
Matrix = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]

IDENTITY: Matrix = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)

#: Rotation of π about the x-axis: maps the normal n to −n and y to −y.
FLIP: Matrix = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, -1.0, 0.0, 0.0),
    (0.0, 0.0, -1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


def _as_matrix(rows: Sequence[Sequence[float]]) -> Matrix:
    return tuple(tuple(float(v) for v in row) for row in rows)  # type: ignore[return-value]


def matmul(*matrices: Sequence[Sequence[float]]) -> Matrix:
    """The product of one or more 4×4 matrices, left to right."""
    out = _as_matrix(matrices[0])
    for m in matrices[1:]:
        out = tuple(  # type: ignore[assignment]
            tuple(sum(out[i][k] * m[k][j] for k in range(4)) for j in range(4))
            for i in range(4)
        )
    return out


def rigid_inverse(m: Sequence[Sequence[float]]) -> Matrix:
    """Inverse of a rigid transform: (R, t)^-1 = (Rᵀ, −Rᵀ t)."""
    r_t = [[m[j][i] for j in range(3)] for i in range(3)]
    t = [m[0][3], m[1][3], m[2][3]]
    inv_t = [-sum(r_t[i][k] * t[k] for k in range(3)) for i in range(3)]
    return (
        (r_t[0][0], r_t[0][1], r_t[0][2], inv_t[0]),
        (r_t[1][0], r_t[1][1], r_t[1][2], inv_t[1]),
        (r_t[2][0], r_t[2][1], r_t[2][2], inv_t[2]),
        (0.0, 0.0, 0.0, 1.0),
    )


def rotation_z(theta_rad: float) -> Matrix:
    """Rz(θ): rotation by θ (radians, right-handed) about the z-axis."""
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    # Exact zeros at the quarter turns keep hand-checked tables free of 6e-17 noise.
    c = 0.0 if abs(c) < 1e-15 else c
    s = 0.0 if abs(s) < 1e-15 else s
    return (
        (c, -s, 0.0, 0.0),
        (s, c, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def flip_rz(theta_rad: float) -> Matrix:
    """M = Flip · Rz(θ), the frame-to-frame rotation of a mate (an involution)."""
    return matmul(FLIP, rotation_z(theta_rad))


def mate_transform(
    t_a: Sequence[Sequence[float]],
    h_a: Sequence[Sequence[float]],
    h_b: Sequence[Sequence[float]],
    theta_rad: float,
) -> Matrix:
    """T_b = T_a · H(F_a) · Flip · Rz(θ) · H(F_b)^-1 (ASM-1 §3.4)."""
    return matmul(t_a, h_a, flip_rz(theta_rad), rigid_inverse(h_b))


def column(m: Sequence[Sequence[float]], j: int) -> Vector:
    """Column `j` of the upper 3 rows (0..2: the frame axes x, y, n; 3: the origin)."""
    return (m[0][j], m[1][j], m[2][j])


def apply_point(m: Sequence[Sequence[float]], p: Sequence[float]) -> Vector:
    return tuple(  # type: ignore[return-value]
        m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3)
    )


def apply_vector(m: Sequence[Sequence[float]], v: Sequence[float]) -> Vector:
    return tuple(  # type: ignore[return-value]
        m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3)
    )


def angle_between_deg(u: Sequence[float], v: Sequence[float]) -> float:
    """The angle between two non-zero vectors, in degrees (0..180).

    atan2(|u × v|, u · v) rather than acos of the dot product: acos loses all precision
    near 0° and 180°, which is exactly where a 0.5° tolerance is judged.
    """
    cross = (
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    )
    dot = u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    return math.degrees(math.atan2(math.sqrt(sum(c * c for c in cross)), dot))


def round_matrix(m: Sequence[Sequence[float]], ndigits: int = 6) -> list[list[float]]:
    """A JSON-friendly copy rounded to `ndigits`, with −0.0 written as 0.0."""
    return [[round(v, ndigits) + 0.0 for v in row] for row in m]
