"""hyperobjects_aas — the AAS v3.1 projection of the hyperobject commons (SEM-1 §5).

One cartridge (solid or soft) or one material card becomes one Asset Administration
Shell **Environment** in the normative JSON serialization of metamodel v3.1.2: a type
shell, its submodels and the ConceptDescriptions of every MADFAM semanticId it uses.
Plain dicts, stdlib + jsonschema only; canonical JSON makes the output deterministic.

    from hyperobjects_aas import build_solid_environment, check_environment

    env = build_solid_environment("solid-hyperobjects/tslot-corner")
    result = check_environment(env)      # aas.json + MADFAM rules (+ BaSyx if installed)

Command line: ``y4d-spec aas build|build-material|check`` and ``fc-spec aas …``.

Modules: ``ids`` (SEM-1 §1 identifiers), ``elements`` (AAS JSON builders), ``templates``
(IDTA identifiers + the conformance-claim rule), ``concepts`` (ConceptDescriptions from the
lexicon), ``common``/``solid``/``soft``/``material`` (the projections), ``check``.
"""

from __future__ import annotations

from .check import AasCheckResult, Finding, check_environment, check_environment_file
from .common import Projection, build_environment
from .material import build_material_environment, project_material
from .soft import build_soft_environment, project_soft
from .solid import build_solid_environment, project_solid

__all__ = [
    "AasCheckResult",
    "Finding",
    "Projection",
    "build_environment",
    "build_material_environment",
    "build_soft_environment",
    "build_solid_environment",
    "check_environment",
    "check_environment_file",
    "project_material",
    "project_soft",
    "project_solid",
    "__version__",
]

__version__ = "0.2.0"
