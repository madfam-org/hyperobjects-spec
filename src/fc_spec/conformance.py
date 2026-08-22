"""Contract conformance: schema + semantic rules for each Fashion Cabinet contract.

Ties the bundled JSON Schemas to the pure rule functions (rules.py) into one
`check(contract, doc)` entry point returning a `ConformanceResult`. Schemas are
loaded from the package's bundled copies via importlib.resources, so the runner is
self-contained when pip-installed outside the Fashion Cabinet repo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources

from . import rules

# The five contracts a third party can check a file against. `schema` is the
# bundled schema filename (or None where the contract is enforced by rules/lane
# only, e.g. the explode-JSON payload has no standalone schema).
CONTRACTS: dict[str, dict] = {
    "garment-manifest": {"schema": "garment-manifest.schema.json"},
    "fabric-card": {"schema": "fabric-manifest.schema.json"},
    "body-measurements": {"schema": "body-measurements.schema.json"},
    "hardware-ref": {"schema": "garment-manifest.schema.json"},
    "explode-json": {"schema": None},
}


def list_contracts() -> list[str]:
    return list(CONTRACTS)


@dataclass
class ConformanceResult:
    contract: str
    ok: bool
    problems: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def _bundled_schema(name: str) -> dict:
    with resources.files("fc_spec.schemas").joinpath(name).open(encoding="utf-8") as f:
        return json.load(f)


def _schema_errors(schema_name: str, doc: dict) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise RuntimeError("jsonschema is required (pip install fashion-cabinet-spec)") from exc
    validator = Draft202012Validator(_bundled_schema(schema_name))
    problems = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        problems.append(f"{where}: {err.message}")
    return problems


def check(
    contract: str, doc: dict, *, resolve: dict[str, list[str]] | None = None,
) -> ConformanceResult:
    """Check one parsed document against one contract.

    `resolve` (hardware-ref only) maps a yantra4d slug -> its parameter ids, the
    resolution surface for a linked hardware_ref. If omitted, a linked reference is
    reported as unresolvable — a third party supplies their own catalog slice.
    """
    if contract not in CONTRACTS:
        raise ValueError(f"unknown contract {contract!r}; known: {', '.join(CONTRACTS)}")

    problems: list[str] = []
    schema_name = CONTRACTS[contract]["schema"]
    if schema_name is not None:
        problems.extend(_schema_errors(schema_name, doc))

    # Semantic rules per contract. Schema errors do not short-circuit the rules —
    # a caller sees every problem at once.
    body_schema = _bundled_schema("body-measurements.schema.json")
    if contract == "garment-manifest":
        problems.extend(rules.garment_manifest_rules(doc, body_schema))
    elif contract == "hardware-ref":
        problems.extend(rules.hardware_ref_rules(doc, resolve or {}))
    elif contract == "body-measurements":
        problems.extend(rules.body_measurements_rules(doc, body_schema))
    elif contract == "explode-json":
        problems.extend(rules.explode_json_rules(doc))
    elif contract == "fabric-card":
        problems.extend(rules.fabric_card_rules(doc))

    return ConformanceResult(contract=contract, ok=not problems, problems=problems)
