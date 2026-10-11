"""hyperobjects_sheet — the sheet-behaviour contract (cross-commons).

Three platforms model thin sheets with their own kernels, engines and material cards:
Pliego (paper, board, foam), Fashion Cabinet (fabric, felt) and Yantra4D (thin prints).
This package is the keystone's link between them, with no shared solver:

* ``sheet-behaviour.schema.json`` (in ``hyperobjects_schemas``) and :func:`validate` —
  a neutral, unit-explicit, derived description any card may carry;
* mapping rules from each platform's own cards (:func:`map_pliego_stock`,
  :func:`map_fc_fabric`, :func:`thin_print`), with golden tests on real cards;
* :func:`resolve_material_ref` — use another platform's material by reference;
* :mod:`hyperobjects_sheet.laminate` / :func:`build_laminate` — classical laminate
  theory for stacks.

See ``docs/SHEET_BEHAVIOUR.md``. Data first, enforcement later: no commons check fails
on any of this yet.
"""

from __future__ import annotations

from .behaviour import VERSION, SheetCheck, material_ref_errors, validate
from .cli import add_sheet_parser
from .laminate import LaminateResult, Layer
from .mapping import MappingError, map_fc_fabric, map_pliego_stock
from .resolve import Resolution, parse_materials_args, resolve_material_ref, resolver_for
from .stack import (
    StackBuild,
    StackError,
    behaviour_from_laminate,
    build_laminate,
    laminate_behaviour,
    thin_print,
)

__all__ = [
    "VERSION",
    "LaminateResult",
    "Layer",
    "MappingError",
    "Resolution",
    "SheetCheck",
    "StackBuild",
    "StackError",
    "add_sheet_parser",
    "behaviour_from_laminate",
    "build_laminate",
    "laminate_behaviour",
    "map_fc_fabric",
    "map_pliego_stock",
    "material_ref_errors",
    "parse_materials_args",
    "resolve_material_ref",
    "resolver_for",
    "thin_print",
    "validate",
]
