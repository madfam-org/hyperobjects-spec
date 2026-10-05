"""The projection-version drift guard (SEM-1 §1, owner decision 2026-10-04).

A shell or submodel id names a revision *and* a projection version, and a store of shells
(asset-shells) keeps every id immutable: different bytes under a stored id are a 409. So
the projection must never change the bytes it writes under an id it has already minted.
This module states that rule once, for the golden environments
(``scripts/refresh_assembly_golden.py --check``, ``tests/test_projection_version.py``):

* the same bytes → nothing to do;
* an id both environments carry, with different bytes → **immutable drift**: the
  projection moved for the same inputs, so ``hyperobjects_aas.ids.PROJECTION_VERSION``
  must be bumped (the refresh refuses to write until it is);
* otherwise the ids moved (an input changed, or the version was bumped) or only
  ConceptDescriptions changed (they follow the lexicon and are mutable in the store) →
  an ordinary refresh.
"""

from __future__ import annotations

from collections.abc import Mapping

from hyperobjects_schemas.generator_output import canonical_json

__all__ = ["identifiables", "immutable_drift"]


def identifiables(env: Mapping) -> dict[str, bytes]:
    """``{id: canonical JSON}`` of the environment's shells and submodels — the
    identifiables a store keeps immutable (ConceptDescriptions are not among them)."""
    out: dict[str, bytes] = {}
    for key in ("assetAdministrationShells", "submodels"):
        for item in env.get(key) or []:
            if isinstance(item, Mapping) and isinstance(item.get("id"), str):
                out[item["id"]] = canonical_json(item)
    return out


def immutable_drift(recorded: Mapping, fresh: Mapping) -> list[str]:
    """The ids ``recorded`` and ``fresh`` both carry with different bytes, sorted. Empty
    means a refresh is safe; anything else needs a ``PROJECTION_VERSION`` bump."""
    old, new = identifiables(recorded), identifiables(fresh)
    return sorted(ident for ident in old.keys() & new.keys() if old[ident] != new[ident])
