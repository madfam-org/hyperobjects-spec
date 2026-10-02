"""Material cards -> one type shell each with a ``MaterialData`` submodel (SEM-1 §5).

Two card shapes exist, both kept in their platforms (ADR-020):

* yantra4d ``materials/<slug>/material.json`` — ``material``, ``am_compensations``,
  ``thermodynamics``, ``semantic_ontology`` (with the EMMO class), …
* Fashion Cabinet ``materials/<slug>/material.json`` — ``fabric``, ``physical``,
  ``compensations``, ``care``, ``digital_twin``, …

``MaterialData`` carries the IDTA 02034 ``MaterialSystemProperties`` collection (the only
element that template makes mandatory), a ``Classification`` collection with the EMMO
class, and ``CardData``: every block of the card mirrored as elements, so nothing the
card says is lost. Where the lexicon names a card path (a term alias such as
``physical.gsm``), that element carries the term's concept as its semanticId.

The shell id is content-addressed: ``content16`` of the card's canonical JSON.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import cache
from pathlib import Path

from hyperobjects_schemas.generator_output import canonical_json

from . import elements as el
from .concepts import Concepts, bundled_lexicon
from .ids import (
    IdShortAllocator,
    id_short,
    material_asset_id,
    material_shell_id,
    material_submodel_id,
)
from .templates import IDTA, Conformance, apply_conformance

__all__ = ["MaterialProjection", "build_material_environment", "card_source", "project_material"]

_LANG_KEY = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{1,8})*$")
_SOURCES = {"material": "yantra4d", "fabric": "fashion-cabinet"}


def card_source(card: object) -> tuple[str, str]:
    """``(platform, slug)`` of a material card. Raises ValueError if it is neither shape."""
    if isinstance(card, dict):
        for block, platform in _SOURCES.items():
            head = card.get(block)
            if isinstance(head, dict) and isinstance(head.get("slug"), str):
                return platform, head["slug"]
    raise ValueError("not a material card: expected a 'material' or 'fabric' block with a slug")


@cache
def _alias_terms(platform: str) -> dict[str, str]:
    """Card path -> lexicon term id, from term aliases written as paths."""
    out = {}
    for term_id, term in bundled_lexicon().items():
        for alias in term.get("aliases", []) or []:
            if not isinstance(alias, dict) or alias.get("repo") != platform:
                continue
            name = alias.get("name")
            if isinstance(name, str) and name and " " not in name:
                out[name] = term_id
    return out


def _is_i18n(value: object) -> bool:
    return (
        isinstance(value, dict) and bool(value)
        and all(isinstance(k, str) and _LANG_KEY.match(k) for k in value)
        and all(isinstance(v, str) for v in value.values())
    )


class _Mirror:
    """Mirrors a JSON block as AAS elements, attaching lexicon concepts by path."""

    def __init__(self, concepts: Concepts, aliases: dict[str, str]) -> None:
        self.concepts, self.aliases = concepts, aliases

    def _semantic(self, path: str) -> str | None:
        term = self.aliases.get(path)
        return self.concepts.term(term) if term else None

    def element(self, short: str | None, value: object, path: str) -> dict | None:
        sid = self._semantic(path)
        if _is_i18n(value):
            return el.mlp(short, value, semantic_id=sid)
        if isinstance(value, dict):
            alloc = IdShortAllocator()
            return el.smc(short, [
                self.element(alloc.take(k), v, f"{path}.{k}" if path else k)
                for k, v in sorted(value.items())
            ], semantic_id=sid)
        if isinstance(value, list):
            item_path = f"{path}[]"
            if all(isinstance(v, dict) for v in value):
                return el.sml(short, [self.element(None, v, item_path) for v in value],
                              type_value="SubmodelElementCollection",
                              semantic_id=sid or self._semantic(item_path))
            if all(not isinstance(v, (dict, list)) for v in value):
                return el.sml(short, [el.prop(None, v) for v in value], type_value="Property",
                              semantic_id=sid or self._semantic(item_path))
            return el.prop(short, value, semantic_id=sid)
        return el.prop(short, value, semantic_id=sid)


class MaterialProjection:
    def __init__(self, card: dict, concepts: Concepts | None = None) -> None:
        self.card = card
        self.platform, self.slug = card_source(card)
        self.concepts = concepts if concepts is not None else Concepts()
        self.conformance: list[Conformance] = []
        self.content_sha256 = hashlib.sha256(canonical_json(card)).hexdigest()

    def _head(self) -> dict:
        block = "material" if self.platform == "yantra4d" else "fabric"
        return self.card.get(block) or {}

    def material_data(self) -> dict:
        head, card = self._head(), self.card
        ontology = card.get("semantic_ontology") if isinstance(card.get("semantic_ontology"),
                                                               dict) else {}
        ids = IDTA["materials"].elements
        system = el.smc("MaterialSystemProperties", [
            el.prop("MaterialType", head.get("category") or head.get("class"),
                    semantic_id=ids["MaterialType"]),
            el.mlp("ProductName", head.get("name"), semantic_id=ids["ProductName"]),
            el.prop("MaterialNumber", self.slug, semantic_id=ids["MaterialNumber"]),
        ], semantic_id=ids["MaterialSystemProperties"])
        classification = el.smc("Classification", [
            el.prop("EmmoClass", ontology.get("emmo_class"), prefer="xs:anyURI"),
            el.prop("Iso52900Category", ontology.get("iso_52900_category")),
            el.prop("AmTechnology", head.get("am_technology")),
            el.prop("Vendor", head.get("vendor")),
            el.prop("FabricClass", head.get("class") if self.platform != "yantra4d" else None),
        ])
        mirror = _Mirror(self.concepts, _alias_terms(self.platform))
        alloc = IdShortAllocator()
        card_data = el.smc("CardData", [
            mirror.element(alloc.take(k), v, k) for k, v in sorted(card.items())
        ])
        sm = {
            "modelType": "Submodel",
            "id": material_submodel_id(self.slug, card, "MaterialData"),
            "idShort": "MaterialData",
            "kind": "Instance",
            "submodelElements": [e for e in (system, classification, card_data) if e],
        }
        self.conformance.append(apply_conformance(sm, "material-data", "materials"))
        self.concepts.template("material-data")
        return sm

    def environment(self) -> dict:
        sm = self.material_data()
        head = self._head()
        shell: dict = {
            "modelType": "AssetAdministrationShell",
            "id": material_shell_id(self.slug, self.card),
            "idShort": id_short(self.slug, "Material"),
            "assetInformation": {
                "assetKind": "Type",
                "globalAssetId": material_asset_id(self.slug),
                "specificAssetIds": [
                    {"name": "platform", "value": self.platform},
                    {"name": "slug", "value": self.slug},
                    {"name": "content_sha256", "value": self.content_sha256},
                ],
            },
            "submodels": [el.model_ref([("Submodel", sm["id"])])],
        }
        names = el.lang_strings(head.get("name"), el.NAME_LIMIT)
        if names:
            shell["displayName"] = names
        env = {"assetAdministrationShells": [shell], "submodels": [sm]}
        cds = self.concepts.descriptions()
        if cds:
            env["conceptDescriptions"] = cds
        return env


def project_material(path_or_card: str | Path | dict) -> MaterialProjection:
    card = path_or_card
    if not isinstance(card, dict):
        card = json.loads(Path(path_or_card).read_text(encoding="utf-8"))
    return MaterialProjection(card)


def build_material_environment(path_or_card: str | Path | dict) -> dict:
    return project_material(path_or_card).environment()
