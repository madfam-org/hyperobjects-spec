"""The cross-commons identity key — RFC 0038 §9's semi-rigid rule, as a check.

One physical thing can be TWO cartridges: a solid one in Yantra4D and a soft one in
Fashion Cabinet. A pair record says so, and names the material identity under which
the claim holds:

    {
      "identity_id": "chainmail-panel",
      "solid": {"repo": "yantra4d",        "slug": "tpu-chainmail-panel"},
      "soft":  {"repo": "fashion-cabinet", "slug": "chainmail-panel"},
      "material_identity": {
        "soft_material":  "tpu-panel-impreso",
        "solid_material": "bambu-tpu-95a"
      }
    }

Both CLIs expose this as ``<tool> identity <file>`` so a contributor on either side of
the commons can check a pair with the tool they already have installed.

The rule is SEMI-rigid on purpose. What is rigid: the record's shape, that ``solid``
is the Yantra4D side and ``soft`` the Fashion Cabinet side, and that the two slugs are
not the same string in the same repo. What is NOT checked here: that either slug
actually exists — this package has no repo to look in, and a third party pairing
against their own fork must still be able to validate the record. Existence is a
platform-side lane (see the P1b checklist in the README).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import load

__all__ = ["IdentityResult", "check_identity", "check_identity_file"]

SCHEMA_NAME = "cross-commons-identity"


@dataclass
class IdentityResult:
    """The verdict on one pair record. Falsey when there are problems."""

    identity_id: str | None
    ok: bool
    problems: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def _schema_errors(doc: object) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise RuntimeError("jsonschema is required (pip install hyperobjects-spec)") from exc
    validator = Draft202012Validator(load(SCHEMA_NAME))
    problems = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        problems.append(f"{where}: {err.message}")
    return problems


def check_identity(doc: object) -> IdentityResult:
    """Validate one parsed pair record: the schema, plus the semantic rules the
    schema cannot express."""
    problems = _schema_errors(doc)

    identity_id = doc.get("identity_id") if isinstance(doc, dict) else None
    if not isinstance(doc, dict):
        return IdentityResult(identity_id=None, ok=False, problems=problems or ["not an object"])

    solid = doc.get("solid") if isinstance(doc.get("solid"), dict) else {}
    soft = doc.get("soft") if isinstance(doc.get("soft"), dict) else {}

    # Side/repo alignment: the record's two halves are not interchangeable. A pair
    # with both halves in one repo is not a cross-commons identity at all.
    if solid.get("repo") not in (None, "yantra4d"):
        problems.append(
            f"solid.repo is {solid.get('repo')!r} — the solid side of an identity pair "
            f"lives in yantra4d"
        )
    if soft.get("repo") not in (None, "fashion-cabinet"):
        problems.append(
            f"soft.repo is {soft.get('repo')!r} — the soft side of an identity pair "
            f"lives in fashion-cabinet"
        )
    if solid.get("repo") and solid.get("repo") == soft.get("repo"):
        problems.append(
            f"solid and soft are both in {solid.get('repo')!r} — an identity pair "
            f"spans the two commons, it does not pair a repo with itself"
        )
    if (
        solid.get("slug")
        and solid.get("slug") == soft.get("slug")
        and solid.get("repo") == soft.get("repo")
    ):
        problems.append(f"solid and soft name the same cartridge {solid.get('slug')!r}")

    return IdentityResult(identity_id=identity_id, ok=not problems, problems=problems)


def check_identity_file(path: str | Path) -> IdentityResult:
    """Read and check a pair file. A file holding a LIST of records checks each one;
    the result carries every problem, prefixed by the record's index."""
    text = Path(path).read_text(encoding="utf-8")
    doc = json.loads(text)

    if isinstance(doc, list):
        problems: list[str] = []
        for i, rec in enumerate(doc):
            r = check_identity(rec)
            problems.extend(f"[{i}] {p}" for p in r.problems)
        return IdentityResult(identity_id=None, ok=not problems, problems=problems)

    return check_identity(doc)
