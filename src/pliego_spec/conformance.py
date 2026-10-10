"""Contract conformance for the sheet commons: one entry point per contract.

    from pliego_spec import check, check_cartridge
    check("sheet-manifest", doc)        # schema + house rules + vocabulary membership
    check("sheet-document", doc)        # vendored schema + structural §8 subset
    check_cartridge("path/to/slug")     # the triple, the manifest, the on-disk rules

Nothing short-circuits: schema errors do not suppress rule problems, so a caller sees
every problem at once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from hyperobjects_lexicon.membership import manifest_vocabulary_problems
from hyperobjects_schemas import load as load_schema

from . import rules, structure
from .document import UNCHECKED_RULES, check_document, check_stock_card

__all__ = [
    "CONTRACTS",
    "ConformanceResult",
    "CartridgeResult",
    "list_contracts",
    "check",
    "check_manifest",
    "check_stock_card",
    "check_cartridge",
]

#: The contracts a third party can check a file against, and where each schema lives.
#: `sheet-manifest` is authored in the keystone (hyperobjects_schemas); `sheet-document`
#: and `stock-card` are Pliego's, vendored and hash-locked in pliego_spec/schemas
#: (VENDORED.md).
CONTRACTS: dict[str, dict] = {
    "sheet-manifest": {"schema": "sheet-manifest", "home": "hyperobjects-spec"},
    "sheet-document": {"schema": "sheet-document.schema.json", "home": "pliego (vendored)"},
    "stock-card": {"schema": "stock-card.schema.json", "home": "pliego (vendored)"},
}


def list_contracts() -> list[str]:
    return list(CONTRACTS)


@dataclass
class ConformanceResult:
    contract: str
    ok: bool
    problems: list[str] = field(default_factory=list)
    #: Read-proof counts for a sheet document (sheets, vertices, edges, faces, joins).
    counts: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class CartridgeResult:
    slug: str | None
    ok: bool
    problems: list[str] = field(default_factory=list)
    #: True, worth saying, never a failure.
    notes: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def _manifest_schema_problems(doc: object) -> list[str]:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(load_schema("sheet-manifest"))
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"schema {where}: {err.message}")
    return out


def check_manifest(doc: object) -> list[str]:
    """Every problem with a parsed sheet manifest: schema, house rules, and SEM-1 §4
    vocabulary membership (an interface `size_key` must be a key of the interface-sizes
    vocabulary — the same shared rule the solid and soft checkers apply)."""
    if not isinstance(doc, dict):
        return ["<root>: a sheet manifest is a JSON object"]
    problems = _manifest_schema_problems(doc)
    problems += rules.all_manifest_rules(doc)
    problems += manifest_vocabulary_problems(doc)
    return problems


def check(contract: str, doc: object) -> ConformanceResult:
    if contract not in CONTRACTS:
        raise ValueError(f"unknown contract {contract!r}; known: {', '.join(CONTRACTS)}")
    if contract == "sheet-manifest":
        problems = check_manifest(doc)
        return ConformanceResult(contract=contract, ok=not problems, problems=problems)
    if contract == "stock-card":
        problems = check_stock_card(doc)
        return ConformanceResult(contract=contract, ok=not problems, problems=problems)
    res = check_document(doc)
    return ConformanceResult(
        contract=contract,
        ok=res.ok,
        problems=res.problems,
        counts={"sheets": res.sheets, "vertices": res.vertices, "edges": res.edges,
                "faces": res.faces, "joins": res.joins},
    )


def check_cartridge(cartridge_dir: str | Path) -> CartridgeResult:
    """Check a cartridge DIRECTORY: the triple, the manifest and the on-disk rules.

    A directory without a project.json is a FAILURE, never a skip — the same verdict
    `y4d-spec check` gives, because a commons CI that globbed one in by mistake must say
    so rather than report a green it never earned.

    This does not run the cartridge: no sheet document is built here (that needs the
    Pliego kernel, which the keystone does not depend on). The note says so on every run.
    """
    path = Path(cartridge_dir)
    if not path.is_dir():
        return CartridgeResult(slug=None, ok=False, problems=[f"{path}: not a directory"])
    manifest_path = path / "project.json"
    if not manifest_path.is_file():
        return CartridgeResult(
            slug=None, ok=False, problems=[f"{path}: no project.json — not a cartridge"]
        )
    problems = structure.triple_rules(path)
    try:
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return CartridgeResult(
            slug=None, ok=False, problems=problems + [f"project.json: invalid JSON — {exc}"]
        )
    slug = (doc.get("project") or {}).get("slug") if isinstance(doc, dict) and isinstance(
        doc.get("project"), dict) else None
    problems += check_manifest(doc)
    if isinstance(doc, dict):
        problems += structure.all_structure_rules(path, doc)

    notes = [
        "documents: NOT built — the cartridge's scripts were not run (the keystone does not "
        "run the Pliego kernel); check emitted sheet documents with "
        "`pliego-spec check sheet-document`"
    ]
    hw = doc.get("hardware_ref") if isinstance(doc, dict) else None
    if isinstance(hw, dict) and hw.get("linked"):
        notes.append(
            f"hardware_ref: the yantra4d side ('{hw.get('project_slug')}') was NOT resolved — "
            "only the local half (params_map reads declared parameters) was checked"
        )
    if isinstance(doc, dict) and isinstance(doc.get("material_ref"), list):
        notes.append("material_ref: the Fashion Cabinet fabric cards were NOT resolved")
    return CartridgeResult(slug=slug, ok=not problems, problems=problems, notes=notes)


#: Re-exported so the CLI's `rules` listing and the docs name the same gap.
UNVERIFIED_DOCUMENT_RULES = UNCHECKED_RULES
