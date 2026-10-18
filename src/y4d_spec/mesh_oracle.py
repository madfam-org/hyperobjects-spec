"""The mesh oracle seam: which library measures a rendered mesh for the solid gates.

The solid mesh gates in `y4d_spec.geometry._judge_stl` (watertight, volume > 0, the body
count `RenderCheck.bodies` that `y4d_spec.body_count` compares with the declaration) read
three numbers off every rendered STL. Until 0.17.0 trimesh was the only thing that
measured them. geom-core (github.com/madfam-org/geom-core, Apache-2.0) is the shared
mesh-analysis library of the geometry factories, "mesh in, numbers out", and this module
lets it measure the same three numbers, so the two can be compared before anything
relies on geom-core.

Selection is `Y4D_SPEC_MESH_ORACLE`:

  * `trimesh` (the default, and what an unset variable means): today's code, unchanged
    results.
  * `geomcore`: the verdict reads geom-core's numbers. Needs the geom-core wheel
    (`scripts/qa/install_geom_core.sh`; the `geometry-core` extra only names the seam,
    because pip extras cannot point at a release URL).
  * `both`: the verdict reads trimesh's numbers, exactly as `trimesh`, and every judged
    mesh is ALSO measured by geom-core. A disagreement beyond tolerance (signed volume
    1e-6 relative, body count exact, watertight exact) is the note `oracle-parity`. It
    is never a failure in this release; the default flips only after the parity is
    written down (CHANGELOG, "oracle-parity").

Any other value, or `geomcore`/`both` without geom-core importable, is an error
(`MeshOracleError`; `y4d-spec check --render` exits 2), never a silent fall back to
trimesh: a run that says it compared two oracles must have compared two.

What stays on trimesh under every selection, because geom-core does not compute it:
loading the mesh for the extents and the printability notes, the boundary-edge count
in a trimesh-verdict failure message, and the per-body signed volumes that name an
inverted body (geom-core reports one `inverted` flag for the whole mesh, not a volume
per body). Format conversion stays trimesh's in the whole programme.

Two geom-core facts this adapter is shaped by, both read from geom-core v0.1.0:

  * `Analyzer.get_volume()` returns the ABSOLUTE volume (`Mesh.cpp`, `std::abs`), which
    would read an inside-out solid as positive and pass the volume gate. The signed
    volume is `assess_integrity().volume`, so that is what is read.
  * geom-core counts bodies by faces that share a VERTEX (`Mesh::bodyCount`, a
    union-find over vertices); trimesh's `_bodies` counts faces that share an EDGE
    (`face_adjacency`). Two solids touching at one vertex are one body to geom-core and
    two to trimesh. The parity note exists to surface exactly that kind of difference.

`load_stl` also writes a "Loaded STL: …" line to the C++ standard output. That would land
in the middle of `y4d-spec check` output, so file descriptor 1 is pointed at /dev/null
for the duration of the load (standard error is left alone: geom-core's load errors go
there and stay visible).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

__all__ = [
    "CHOICES",
    "DEFAULT",
    "ENV_VAR",
    "RULE_ID",
    "VOLUME_RTOL",
    "GeomCoreOracle",
    "MeshMeasure",
    "MeshOracle",
    "MeshOracleError",
    "TrimeshOracle",
    "geom_core_available",
    "oracle_parity_note",
    "require_selection",
    "selected_oracle",
]

ENV_VAR = "Y4D_SPEC_MESH_ORACLE"
CHOICES = ("trimesh", "geomcore", "both")
DEFAULT = "trimesh"
RULE_ID = "oracle-parity"

#: Signed volumes agree when |a - b| <= VOLUME_RTOL × max(|a|, |b|). Both oracles read
#: the same float32 STL coordinates and sum the same signed tetrahedra in float64, so a
#: real difference is a different mesh (a merge that moved a vertex, a dropped face),
#: not rounding.
VOLUME_RTOL = 1e-6

#: The importable name of the geom-core Python extension (the wheel is `geom_core`,
#: the module it installs is `geom_core_py`; geom-core `bindings/python/PyBindEntry.cpp`).
GEOM_CORE_MODULE = "geom_core_py"


class MeshOracleError(RuntimeError):
    """An oracle selection that cannot be honoured: an unknown value, or geom-core asked
    for and not importable, or geom-core unable to load the mesh it was handed."""


@dataclass(frozen=True)
class MeshMeasure:
    """The three numbers the solid gates read off one mesh, and who measured them."""

    oracle: str
    watertight: bool
    #: Signed volume in mm³ (negative for an inside-out mesh).
    volume: float
    #: Connected bodies, or None when this oracle could not count them.
    bodies: int | None
    #: Edges used by exactly one face, when the oracle reports it (-1: could not count).
    boundary_edges: int | None = None
    #: Signed volume per body (trimesh only; geom-core reports no per-body volume).
    body_volumes: tuple[float, ...] | None = None
    #: Why the bodies could not be counted, when they could not.
    bodies_error: str | None = None


class MeshOracle(Protocol):
    """Measures a rendered mesh. `mesh` is the already-loaded, vertex-merged trimesh
    the gate holds, which an oracle may reuse instead of reading `stl_path` again."""

    name: str

    def measure(self, stl_path: str, mesh=None) -> MeshMeasure: ...


def selected_oracle(environ: Mapping[str, str] | None = None) -> str:
    """The validated `Y4D_SPEC_MESH_ORACLE` value; unset or empty means `trimesh`."""
    env = os.environ if environ is None else environ
    raw = env.get(ENV_VAR, "")
    value = raw.strip().lower()
    if not value:
        return DEFAULT
    if value not in CHOICES:
        raise MeshOracleError(
            f"{ENV_VAR}={raw!r} is not one of {', '.join(CHOICES)} (unset means {DEFAULT})"
        )
    return value


def geom_core_available() -> bool:
    """True when the geom-core extension imports."""
    try:
        __import__(GEOM_CORE_MODULE)
    except Exception:
        return False
    return True


def require_selection(environ: Mapping[str, str] | None = None) -> str:
    """`selected_oracle()`, plus a refusal when the selection needs geom-core and it is
    not importable. Called once by `y4d-spec check --render` before anything renders and
    by the gate itself, so neither entry point can fall back silently."""
    selection = selected_oracle(environ)
    if selection != "trimesh" and not geom_core_available():
        raise MeshOracleError(
            f"{ENV_VAR}={selection} needs geom-core, and `import {GEOM_CORE_MODULE}` "
            f"fails — install it with scripts/qa/install_geom_core.sh (README, "
            f"'The geom-core mesh oracle'), or unset {ENV_VAR}"
        )
    return selection


class TrimeshOracle:
    """Today's measurement, unchanged: `is_watertight`, `volume` and `_bodies` on the
    vertex-merged mesh (`process=False`, so nothing is repaired on load)."""

    name = "trimesh"

    def measure(self, stl_path: str, mesh=None) -> MeshMeasure:
        from .geometry import _bodies, _boundary_edges, _require_geometry

        if mesh is None:
            _, trimesh = _require_geometry()
            mesh = trimesh.load(stl_path, force="mesh", process=False)
            mesh.merge_vertices()
        watertight = bool(mesh.is_watertight)
        volume = float(mesh.volume)
        bodies: int | None
        body_volumes: tuple[float, ...] | None
        error = None
        try:
            components = _bodies(mesh)
        except Exception as exc:
            bodies, body_volumes = None, None
            error = f"{type(exc).__name__}: {exc}"
        else:
            bodies = len(components)
            body_volumes = tuple(bvol for _faces, bvol in components)
        return MeshMeasure(
            oracle=self.name,
            watertight=watertight,
            volume=volume,
            bodies=bodies,
            boundary_edges=None if watertight else _boundary_edges(mesh),
            body_volumes=body_volumes,
            bodies_error=error,
        )


@contextmanager
def _native_stdout_silenced():
    """Point file descriptor 1 at /dev/null, for a C++ `std::cout` write we cannot
    switch off. Python-level output is flushed first so nothing is lost or reordered."""
    try:
        sys.stdout.flush()
    except Exception:
        pass
    saved = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
        yield
    finally:
        os.dup2(saved, 1)
        os.close(devnull)
        os.close(saved)


class GeomCoreOracle:
    """geom-core's measurement of the same STL: `assess_integrity()` (yantra4d's
    `mesh_integrity.assess`, ported) for watertight, the SIGNED volume and the body
    count. It reads the file itself, so `mesh` is ignored."""

    name = "geom-core"

    def measure(self, stl_path: str, mesh=None) -> MeshMeasure:
        try:
            module = __import__(GEOM_CORE_MODULE)
        except Exception as exc:
            raise MeshOracleError(
                f"geom-core is not importable ({type(exc).__name__}: {exc})"
            ) from exc
        analyzer = module.Analyzer()
        with _native_stdout_silenced():
            loaded = analyzer.load_stl(str(stl_path))
        if not loaded:
            raise MeshOracleError(f"geom-core could not load {stl_path} (see stderr)")
        integrity = analyzer.assess_integrity()
        return MeshMeasure(
            oracle=self.name,
            watertight=bool(integrity.watertight),
            volume=float(integrity.volume),
            bodies=int(integrity.body_count),
            boundary_edges=int(integrity.boundary_edges),
        )


def _volumes_agree(a: float, b: float) -> bool:
    scale = max(abs(a), abs(b))
    return abs(a - b) <= VOLUME_RTOL * scale


def oracle_parity_note(target: str, first: MeshMeasure, second: MeshMeasure) -> str | None:
    """The `oracle-parity` note for one mesh, or None when the two measurements agree
    (watertight and body count exactly, signed volume within VOLUME_RTOL relative)."""
    diffs: list[str] = []
    if first.watertight != second.watertight:
        diffs.append(
            f"watertight {first.oracle}={first.watertight} {second.oracle}={second.watertight}"
        )
    if first.bodies is None or second.bodies is None or first.bodies != second.bodies:
        def _count(m: MeshMeasure) -> str:
            return "unmeasured" if m.bodies is None else str(m.bodies)

        diffs.append(
            f"bodies {first.oracle}={_count(first)} {second.oracle}={_count(second)}"
        )
    if not _volumes_agree(first.volume, second.volume):
        scale = max(abs(first.volume), abs(second.volume))
        rel = abs(first.volume - second.volume) / scale
        diffs.append(
            f"volume {first.oracle}={first.volume:.6f} {second.oracle}={second.volume:.6f} "
            f"(relative difference {rel:.3g} > {VOLUME_RTOL:g})"
        )
    if not diffs:
        return None
    return (
        f"{RULE_ID}: {target}: {first.oracle} and {second.oracle} disagree — "
        f"{'; '.join(diffs)}; the verdict used {first.oracle} ({ENV_VAR}=both), a note "
        f"until the parity pass is written down"
    )
