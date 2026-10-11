"""Classical laminate theory: the A, B and D matrices of a stack of thin layers.

The textbook statement (Jones, *Mechanics of Composite Materials*, ch. 4; Kaw, *Mechanics
of Composite Materials*, ch. 4), with engineering shear strain and Voigt order
``(1, 2, 6)``:

    N = A·ε⁰ + B·κ          A = Σ Q̄ₖ tₖ
    M = B·ε⁰ + D·κ          B = Σ Q̄ₖ tₖ z̄ₖ
                            D = Σ (Q̄ₖ tₖ³/12 + Q̄ₖ tₖ z̄ₖ²)

``z`` runs from the bottom face (−h/2) to the top (+h/2); layer 0 is the bottom (the bed
side of a print, the board side of a covered board). Units are SI throughout: Q in Pa,
t and z in m, so A is N/m, B is N and D is N·m.

Two extensions, both reducing to the textbook when unused:

* **own bending.** A homogeneous elastic layer bends as a plate about its own mid-plane
  (``Q̄ t³/12``). A fabric does not: its yarns slide, and its bending stiffness is orders
  of magnitude below the plate value of its membrane modulus. A layer that comes from a
  ``sheet_behaviour`` card may therefore contribute its **card** bending (rotated into
  the laminate axes) in place of the plate term; the parallel-axis term ``Q̄ t z̄²`` is
  kept, because it is membrane stiffness carried off the mid-plane. The default is
  ``card`` for a card-backed layer and ``plate`` for a lamina given by its constants, and
  the result records which one each layer used.
* **pre-strain.** A layer may carry a stress-free strain ``e`` relative to the bonded
  state (a fabric stretched before a print was laid on it has ``e = −stretch``). The free
  stack then settles at ``[ε⁰; κ] = [[A, B], [B, D]]⁻¹ · [Nₚ; Mₚ]`` with
  ``Nₚ = Σ Q̄ₖ eₖ tₖ`` and ``Mₚ = Σ Q̄ₖ eₖ tₖ z̄ₖ``. A non-zero curvature is the curl that
  print-on-fabric shaping relies on; it needs B ≠ 0 or an asymmetric pre-strain.

A non-zero **B** couples stretching and bending: the stack curls under in-plane load or
pre-strain. It is flagged (``coupled``), never failed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import linalg as la

#: |B| relative to √(|A|·|D|) below which B is floating-point noise (a convention).
COUPLING_EPS = 1e-9


@dataclass(frozen=True)
class Layer:
    """One layer in laminate axes. Moduli in Pa, thickness in m, angle in degrees
    (axis 1 of the layer measured from laminate x, counter-clockwise)."""

    name: str
    E1: float
    E2: float
    G12: float
    nu12: float
    thickness: float
    angle_deg: float = 0.0
    own_bending: list[list[float]] | None = None   # N·m, layer axes; None → plate
    prestrain: tuple[float, float, float] | None = None
    areal_density: float | None = None             # kg/m², for the stack's mass

    def __post_init__(self) -> None:
        for label in ("E1", "E2", "G12", "thickness"):
            value = getattr(self, label)
            if not (isinstance(value, (int, float)) and math.isfinite(value) and value > 0):
                raise ValueError(f"layer {self.name!r}: {label} must be a positive number")
        if self.nu12 * self.nu12 >= self.E1 / self.E2:
            raise ValueError(
                f"layer {self.name!r}: nu12² ≥ E1/E2 — the lamina stiffness is not "
                "positive definite"
            )

    @property
    def bending_source(self) -> str:
        return "plate" if self.own_bending is None else "card"


def reduced_stiffness(E1: float, E2: float, G12: float, nu12: float) -> la.Matrix:
    """The plane-stress reduced stiffness Q of an orthotropic lamina in its own axes."""
    nu21 = nu12 * E2 / E1
    den = 1.0 - nu12 * nu21
    return [
        [E1 / den, nu12 * E2 / den, 0.0],
        [nu12 * E2 / den, E2 / den, 0.0],
        [0.0, 0.0, G12],
    ]


def rotate(q: la.Matrix, angle_deg: float) -> la.Matrix:
    """Q̄ = T₁⁻¹ · Q · T₂: a stiffness in layer axes seen from the laminate axes.

    T₁ transforms stress, T₂ engineering strain; the layer's axis 1 sits at ``angle_deg``
    from laminate x. Works for any symmetric 3 × 3 stiffness (Q or a bending D), so a
    layer whose own bending already has D16/D26 rotates correctly too.
    """
    t = math.radians(angle_deg)
    m, n = math.cos(t), math.sin(t)
    t1 = [[m * m, n * n, 2 * m * n], [n * n, m * m, -2 * m * n], [-m * n, m * n, m * m - n * n]]
    t2 = [[m * m, n * n, m * n], [n * n, m * m, -m * n], [-2 * m * n, 2 * m * n, m * m - n * n]]
    out = la.matmul(la.matmul(la.inverse(t1), q), t2)
    return [[_clean(x, q) for x in row] for row in out]


def _clean(x: float, ref: la.Matrix) -> float:
    """Zero the round-off that cos(90°) ≠ 0 leaves (relative to the matrix's scale)."""
    return 0.0 if abs(x) <= 1e-14 * la.max_abs(ref) else x


@dataclass
class LaminateResult:
    A: la.Matrix
    B: la.Matrix
    D: la.Matrix
    thickness: float
    layers: list[Layer]
    coupling_ratio: float
    coupled: bool
    prestrain_strain: list[float] | None = None
    prestrain_curvature: list[float] | None = None
    notes: list[str] = field(default_factory=list)

    def abd(self) -> la.Matrix:
        return la.block(self.A, self.B, self.B, self.D)

    def effective(self) -> dict[str, float]:
        """Engineering membrane constants and bending of the FREE stack.

        From the inverse of the 6 × 6 ABD matrix, so a coupled stack is allowed to bend
        while it is stretched (and to stretch while it is bent): membrane from
        A* = A − B·D⁻¹·B, bending from D* = D − B·A⁻¹·B. Both reduce to A and D when
        B = 0.
        """
        inv = la.inverse(self.abd())
        a, _, _, d = la.split(inv, 3)
        dstar = la.inverse(d)
        return {
            "E1t": 1.0 / a[0][0],
            "E2t": 1.0 / a[1][1],
            "G12t": 1.0 / a[2][2],
            "nu12": -a[0][1] / a[0][0],
            "D11": dstar[0][0],
            "D22": dstar[1][1],
            "D12": dstar[0][1],
            "D66": dstar[2][2],
            "D16": dstar[0][2],
            "D26": dstar[1][2],
        }


def laminate(layers: list[Layer]) -> LaminateResult:
    """A, B and D of ``layers`` (bottom first); see the module docstring."""
    if not layers:
        raise ValueError("a laminate needs at least one layer")
    h = sum(layer.thickness for layer in layers)
    A, B, D = la.zeros(3), la.zeros(3), la.zeros(3)
    Np, Mp = [0.0] * 3, [0.0] * 3
    has_prestrain = False
    z = -h / 2.0
    for layer in layers:
        t = layer.thickness
        zbar = z + t / 2.0
        qbar = rotate(reduced_stiffness(layer.E1, layer.E2, layer.G12, layer.nu12),
                      layer.angle_deg)
        own = (la.scale(qbar, t ** 3 / 12.0) if layer.own_bending is None
               else rotate(layer.own_bending, layer.angle_deg))
        A = la.add(A, la.scale(qbar, t))
        B = la.add(B, la.scale(qbar, t * zbar))
        D = la.add(D, la.add(own, la.scale(qbar, t * zbar * zbar)))
        if layer.prestrain is not None:
            has_prestrain = True
            force = la.matvec(qbar, list(layer.prestrain))
            Np = [x + f * t for x, f in zip(Np, force, strict=True)]
            Mp = [x + f * t * zbar for x, f in zip(Mp, force, strict=True)]
        z += t
    # A symmetric stack cancels B exactly in real arithmetic; zero the round-off, so that
    # "coupled" and "B has a non-zero entry" are one and the same fact.
    scale_b = math.sqrt(la.max_abs(A) * la.max_abs(D))
    B = [[0.0 if abs(x) <= COUPLING_EPS * scale_b else x for x in row] for row in B]
    ratio = la.max_abs(B) / scale_b if scale_b else 0.0
    result = LaminateResult(A=A, B=B, D=D, thickness=h, layers=list(layers),
                            coupling_ratio=ratio, coupled=ratio > 0.0)
    if has_prestrain:
        sol = la.solve(result.abd(), [[x] for x in Np + Mp])
        result.prestrain_strain = [row[0] for row in sol[:3]]
        result.prestrain_curvature = [row[0] for row in sol[3:]]
    if result.coupled:
        result.notes.append(
            f"B is non-zero (|B|/√(|A|·|D|) = {ratio:.3g}): stretching and bending are "
            "coupled, so the stack curls under in-plane load or layer pre-strain"
        )
    eff = result.effective()
    if abs(eff["D16"]) > 1e-6 * eff["D11"] or abs(eff["D26"]) > 1e-6 * eff["D22"]:
        result.notes.append(
            "D16/D26 are non-zero: axis 1 is not a principal bending axis of this stack "
            "(bend-twist coupling); engines that read only D11/D22/D12/D66 lose it"
        )
    return result


def isotropic_layer(name: str, E: float, nu: float, thickness: float,
                    angle_deg: float = 0.0) -> Layer:
    """Convenience: an isotropic lamina (G = E / (2(1 + ν)))."""
    return Layer(name=name, E1=E, E2=E, G12=E / (2.0 * (1.0 + nu)), nu12=nu,
                 thickness=thickness, angle_deg=angle_deg)
