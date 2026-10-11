"""Built-up boards: a Pliego stock card's ``construction`` block → a classical laminate.

A stock card for corrugated board or a laminated board (folding boxboard) carries a
``construction`` block (Pliego ``docs/spec/v1/stock-card.md``, "Board constructions"),
evaluated by Pliego's ``pliego.board v1``. That model computes the card's grammage,
caliper, effective moduli and the bending stiffness D about each direction's own neutral
axis. It writes no coupling matrix B and no twisting stiffness, so ``pliego-stock/1``
rebuilds the stack here as a classical laminate, with the **same per-layer
contributions**, to give the ``laminate`` block (A, B, D about the mid-plane) and D66.

The reading, layer by layer (the card lists layers top first; the stack runs bottom up):

* **liner / ply**: an orthotropic lamina of its caliper, ``E_md``, ``E_cd``, the card's
  ν split by reciprocity (ν12 = ν·√(E_md/E_cd), so ν12·ν21 = ν² and Q11 = E_md/(1 − ν²),
  pliego.board's plate factor), and the Baum estimate G12 = 0.387·√(E_md·E_cd) that
  ``pliego.stock.derive v1`` applies to a whole card;
* **medium**: a slab as thick as its flute height ``h`` that carries load in CD only,
  Q22·h = α·E_cd,m·t_m/(1 − ν²), with own bending Q22·h·(t_m²/12 + a²/2), where
  a = (h − t_m)/2 is the sinusoid's amplitude and α its arc-length factor (take-up).
  Its MD load and its in-plane shear are neglected, as pliego.board v1 neglects them.

Reduced per direction (D − B²/A), this is pliego.board v1's D exactly; the full 3 × 3
D* = D − B·A⁻¹·B also carries the Poisson cross terms, so it agrees to a fraction of a
per cent (the mapping reports the agreement in a note, and a test holds it).

The flute table is the one pliego.board v1 uses, from public sources: flutes per metre
from Foster 1997 (Wiley Encyclopedia of Packaging Technology, as tabled in Wikipedia
"Corrugated fiberboard"); heights B 2.70, C 3.60 and E 1.30 mm measured by Rogalka,
Grabski & Garbowski 2023 (Sensors 23:6242, Table 1); A 4.7 and F 0.6 mm estimated. A
test checks that every board card's layers add up to its caliper with these heights.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import linalg as la
from .laminate import COUPLING_EPS

BOARD_MODEL = "pliego.board v1"
#: flute → (flutes per metre, flute height in mm, height status).
FLUTES: dict[str, tuple[float, float, str]] = {
    "A": (108.0, 4.7, "estimated"),
    "B": (154.0, 2.7, "measured"),
    "C": (128.0, 3.6, "measured"),
    "E": (295.0, 1.3, "measured"),
    "F": (420.0, 0.6, "estimated"),
}
#: The Baum, Brennan & Habeger (1981) shear estimate pliego.stock.derive v1 applies.
BAUM_G12 = 0.387
#: Midpoint samples over one flute period for the take-up integral (a convention).
TAKE_UP_SAMPLES = 512
_GPA = 1e9
_MM = 1e-3


class BoardError(ValueError):
    """A construction block this reading cannot use."""


def take_up(pitch_mm: float, amplitude_mm: float) -> float:
    """Arc length of z = a·sin(2πx/λ) per unit x, by the midpoint rule over one period."""
    k = amplitude_mm * 2.0 * math.pi / pitch_mm
    n = TAKE_UP_SAMPLES
    return math.fsum(math.sqrt(1.0 + (k * math.cos(2.0 * math.pi * (i + 0.5) / n)) ** 2)
                     for i in range(n)) / n


@dataclass(frozen=True)
class BoardStack:
    """The rebuilt stack: SI matrices about the mid-plane, records bottom first."""

    A: la.Matrix
    B: la.Matrix
    D: la.Matrix
    thickness_mm: float
    records: list[dict]
    statuses: list[str]
    coupling_ratio: float
    coupled: bool

    def free_bending(self) -> la.Matrix:
        """D* = D − B·A⁻¹·B: the bending of the free stack about its neutral surface."""
        return la.sub(self.D, la.matmul(la.matmul(self.B, la.inverse(self.A)), self.B))


def _positive(layer: dict, key: str, where: str) -> float:
    v = layer.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not (
        math.isfinite(v) and v > 0
    ):
        raise BoardError(f"{where}.{key} must be a positive number")
    return float(v)


def board_stack(construction: dict, nu: float, slug: str) -> BoardStack:
    """The classical laminate of a ``construction`` block (see the module docstring)."""
    if construction.get("model") != BOARD_MODEL:
        raise BoardError(f"construction.model {construction.get('model')!r}, this rule "
                         f"reads {BOARD_MODEL!r}")
    kind = construction.get("kind")
    roles = {"corrugated": ("liner", "medium"), "laminate": ("ply",)}.get(kind)
    layers = construction.get("layers")
    if roles is None or not isinstance(layers, list) or not layers:
        raise BoardError(f"construction.kind {kind!r} with layers {layers!r} is not a "
                         "corrugated or laminated board")
    plate = 1.0 / (1.0 - nu * nu)
    slabs = []        # (thickness m, Q Pa, own bending N·m, record, status), bottom first
    for k in reversed(range(len(layers))):
        layer, where = layers[k], f"construction.layers[{k}]"
        if not isinstance(layer, dict) or layer.get("role") not in roles:
            raise BoardError(f"{where}.role must be one of {roles} for {kind}")
        role = layer["role"]
        t_mm = _positive(layer, "caliper_um", where) / 1000.0
        e_md = _positive(layer, "E_md_gpa", where) * _GPA
        e_cd = _positive(layer, "E_cd_gpa", where) * _GPA
        status = "estimated" if layer.get("status") == "estimated" else "measured"
        label = f"pliego/{slug} construction.layers[{k}] {role}"
        if role == "medium":
            flute = FLUTES.get(layer.get("flute"))
            if flute is None:
                raise BoardError(f"{where}.flute must be one of {', '.join(FLUTES)}")
            per_m, h_mm, _ = flute
            if t_mm >= h_mm:
                raise BoardError(f"{where}: caliper must be below the flute height {h_mm} mm")
            amp_mm = (h_mm - t_mm) / 2.0
            alpha = take_up(1000.0 / per_m, amp_mm)
            h = h_mm * _MM
            q22 = alpha * e_cd * t_mm * _MM * plate / h
            spread = (t_mm * _MM) ** 2 / 12.0 + (amp_mm * _MM) ** 2 / 2.0
            q = [[0.0, 0.0, 0.0], [0.0, q22, 0.0], [0.0, 0.0, 0.0]]
            own = [[0.0, 0.0, 0.0], [0.0, q22 * h * spread, 0.0], [0.0, 0.0, 0.0]]
            record = {"material": f"{label} {layer['flute']} flute", "angle_deg": 0.0,
                      "thickness_mm": h_mm}
            slabs.append((h, q, own, record, status))
        else:
            t = t_mm * _MM
            nu12 = nu * math.sqrt(e_md / e_cd)
            g12 = BAUM_G12 * math.sqrt(e_md * e_cd)
            den = 1.0 - nu * nu          # ν12·ν21 = ν²
            q = [[e_md / den, nu12 * e_cd / den, 0.0],
                 [nu12 * e_cd / den, e_cd / den, 0.0],
                 [0.0, 0.0, g12]]
            record = {"material": label, "angle_deg": 0.0, "thickness_mm": t_mm,
                      "own_bending": "plate"}
            slabs.append((t, q, la.scale(q, t ** 3 / 12.0), record, status))
    h_total = sum(s[0] for s in slabs)
    A, B, D = la.zeros(3), la.zeros(3), la.zeros(3)
    z = -h_total / 2.0
    for t, q, own, _, _ in slabs:
        zbar = z + t / 2.0
        A = la.add(A, la.scale(q, t))
        B = la.add(B, la.scale(q, t * zbar))
        D = la.add(D, la.add(own, la.scale(q, t * zbar * zbar)))
        z += t
    scale_b = math.sqrt(la.max_abs(A) * la.max_abs(D))
    B = [[0.0 if abs(x) <= COUPLING_EPS * scale_b else x for x in row] for row in B]
    ratio = la.max_abs(B) / scale_b if scale_b else 0.0
    return BoardStack(A=A, B=B, D=D, thickness_mm=h_total / _MM,
                      records=[s[3] for s in slabs], statuses=[s[4] for s in slabs],
                      coupling_ratio=ratio, coupled=ratio > 0.0)
