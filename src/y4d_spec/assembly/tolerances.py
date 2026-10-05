"""The mating rule's tolerances (ASM-1 §3.5 / SEM-1 §2.3), shared by closure and the sweep."""

from __future__ import annotations

__all__ = ["ANGLE_TOLERANCE_DEG", "ORIGIN_TOLERANCE_MM"]

#: Origins of two mated frames coincide within this, in mm.
ORIGIN_TOLERANCE_MM = 0.05
#: Normals antiparallel and x-axes agreeing (modulo symmetry) within this, in degrees.
ANGLE_TOLERANCE_DEG = 0.5
