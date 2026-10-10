"""Small dense linear algebra for the laminate calculator (stdlib only).

The package's only runtime dependency is ``jsonschema``; a laminate is at most a 6 × 6
system, so this is Gaussian elimination with partial pivoting and nothing more.
"""

from __future__ import annotations

import math

Matrix = list[list[float]]
Vector = list[float]


def zeros(n: int, m: int | None = None) -> Matrix:
    return [[0.0] * (n if m is None else m) for _ in range(n)]


def add(a: Matrix, b: Matrix) -> Matrix:
    return [[x + y for x, y in zip(ra, rb, strict=True)] for ra, rb in zip(a, b, strict=True)]


def sub(a: Matrix, b: Matrix) -> Matrix:
    return [[x - y for x, y in zip(ra, rb, strict=True)] for ra, rb in zip(a, b, strict=True)]


def scale(a: Matrix, k: float) -> Matrix:
    return [[k * x for x in row] for row in a]


def matmul(a: Matrix, b: Matrix) -> Matrix:
    cols = list(zip(*b, strict=True))
    return [[sum(x * y for x, y in zip(row, col, strict=True)) for col in cols] for row in a]


def matvec(a: Matrix, v: Vector) -> Vector:
    return [sum(x * y for x, y in zip(row, v, strict=True)) for row in a]


def solve(a: Matrix, b: Matrix) -> Matrix:
    """Solve ``a · x = b`` for ``x`` (``b`` may have several columns).

    Raises ``ValueError`` when ``a`` is singular to working precision: a laminate whose
    stiffness cannot be inverted is a finding, never a silent zero.
    """
    n = len(a)
    m = [list(map(float, row)) + list(map(float, rhs)) for row, rhs in zip(a, b, strict=True)]
    width = len(m[0])
    norm = max((abs(x) for row in a for x in row), default=0.0)
    if norm == 0.0:
        raise ValueError("singular matrix (all zero)")
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) <= 1e-13 * norm:
            raise ValueError("singular matrix")
        m[col], m[pivot] = m[pivot], m[col]
        p = m[col][col]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col] / p
            if f:
                for c in range(col, width):
                    m[r][c] -= f * m[col][c]
    return [[m[r][c] / m[r][r] for c in range(n, width)] for r in range(n)]


def inverse(a: Matrix) -> Matrix:
    n = len(a)
    return solve(a, [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)])


def block(a: Matrix, b: Matrix, c: Matrix, d: Matrix) -> Matrix:
    """``[[a, b], [c, d]]`` for square blocks of equal size."""
    return [ra + rb for ra, rb in zip(a, b, strict=True)] + [
        rc + rd for rc, rd in zip(c, d, strict=True)
    ]


def split(m: Matrix, n: int) -> tuple[Matrix, Matrix, Matrix, Matrix]:
    """The four ``n × n`` blocks of a ``2n × 2n`` matrix."""
    return (
        [row[:n] for row in m[:n]],
        [row[n:] for row in m[:n]],
        [row[:n] for row in m[n:]],
        [row[n:] for row in m[n:]],
    )


def is_positive_definite(a: Matrix) -> bool:
    """Cholesky test on the symmetric part (Sylvester would be fooled by rounding)."""
    n = len(a)
    sym = [[(a[i][j] + a[j][i]) / 2.0 for j in range(n)] for i in range(n)]
    low = zeros(n)
    for i in range(n):
        for j in range(i + 1):
            s = sym[i][j] - sum(low[i][k] * low[j][k] for k in range(j))
            if i == j:
                if s <= 0.0 or not math.isfinite(s):
                    return False
                low[i][i] = math.sqrt(s)
            else:
                low[i][j] = s / low[j][j]
    return True


def max_abs(a: Matrix) -> float:
    return max((abs(x) for row in a for x in row), default=0.0)
