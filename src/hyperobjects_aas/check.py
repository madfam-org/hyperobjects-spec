"""``aas check`` — is an AAS Environment valid, and is it true about itself?

Three layers, reported as findings with a severity (an ``error`` fails the check, a
``warning`` prints and does not):

1. **Schema** — the official AAS v3.1.2 JSON Schema (``schemas/aas.json``, vendored with
   its CC-BY-4.0 attribution). Draft 2019-09.
2. **MADFAM rules** — the SEM-1 §1 identifier scheme (shell, asset and submodel ids agree
   on kind, slug and revision; the revision prefix matches the full digest in
   ``specificAssetIds``); idShort rules the schema cannot express (AASd-117 required
   outside lists, AASd-120 absent inside them, AASd-022 unique among siblings); the
   conformance-claim rule (a submodel naming an IDTA template has every mandatory
   element, or it must not name it); and every MADFAM semanticId has a
   ConceptDescription.
3. **BaSyx round-trip** — when the ``aas-verify`` extra is installed, the environment is
   deserialized by the BaSyx Python SDK 2.2.0 in strict mode (which enforces most AASd
   constraints), serialized and read back. Absent the extra this layer reports
   ``basyx=not installed`` — it is never reported as passed.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path

from jsonschema import Draft201909Validator

from .concepts import bundled_lexicon
from .ids import BASE, is_id_short
from .templates import IDTA, MADFAM, missing_mandatory

__all__ = [
    "AasCheckResult",
    "Finding",
    "aas_schema",
    "basyx_available",
    "check_environment",
    "check_environment_file",
]

ERROR, WARNING = "error", "warning"

_SLUG = r"[a-z0-9][a-z0-9_-]*"
_SHELL = re.compile(rf"^{re.escape(BASE)}/aas/(solid|soft|material)/({_SLUG})/([0-9a-f]{{16}})$")
_ASSET = re.compile(rf"^{re.escape(BASE)}/asset/(solid|soft|material)/({_SLUG})$")
_SUBMODEL = re.compile(
    rf"^{re.escape(BASE)}/sm/(solid|soft|material)/({_SLUG})/([0-9a-f]{{16}})/([^/]+)$"
)
_CONCEPT_PREFIX = f"{BASE}/concept/"
_TEMPLATE_PREFIX = f"{BASE}/smt/"
_DIGEST_KEY = {"solid": "tree_sha256", "soft": "tree_sha256", "material": "content_sha256"}
_IDTA_BY_ID = {t.submodel_semantic_id: t for t in IDTA.values()}
_MADFAM_IDS = {t.id for t in MADFAM.values()}
_MAX_SCHEMA_FINDINGS = 50


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper()} [{self.code}] {self.path}: {self.message}"


@dataclass
class AasCheckResult:
    findings: list[Finding] = field(default_factory=list)
    basyx: str = "skipped"

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors


@cache
def aas_schema() -> dict:
    """The vendored AAS v3.1.2 JSON Schema (cached, read-only)."""
    text = resources.files("hyperobjects_aas.schemas").joinpath("aas.json").read_bytes()
    return json.loads(text)


def vendored_schema_digest() -> str:
    data = resources.files("hyperobjects_aas.schemas").joinpath("aas.json").read_bytes()
    return hashlib.sha256(data).hexdigest()


@cache
def _validator() -> Draft201909Validator:
    return Draft201909Validator(aas_schema())


def _schema_findings(env: object) -> list[Finding]:
    out = []
    errors = sorted(_validator().iter_errors(env), key=lambda e: list(map(str, e.path)))
    for err in errors[:_MAX_SCHEMA_FINDINGS]:
        path = "/".join(str(p) for p in err.absolute_path) or "$"
        out.append(Finding(ERROR, "schema", path, err.message[:300]))
    if len(errors) > _MAX_SCHEMA_FINDINGS:
        out.append(Finding(ERROR, "schema", "$",
                           f"{len(errors) - _MAX_SCHEMA_FINDINGS} more schema errors"))
    return out


def _semantic_ids(el: dict) -> list[str]:
    out = []
    for ref in [el.get("semanticId"), *(el.get("supplementalSemanticIds") or [])]:
        if isinstance(ref, dict):
            out += [k.get("value") for k in ref.get("keys") or [] if isinstance(k, dict)]
    return [v for v in out if isinstance(v, str)]


def _children(el: dict) -> tuple[list, bool]:
    """(child elements, whether they are list items)."""
    mt = el.get("modelType")
    if mt == "Submodel":
        return el.get("submodelElements") or [], False
    if mt == "Entity":
        return el.get("statements") or [], False
    if mt == "SubmodelElementCollection":
        return el.get("value") or [], False
    if mt == "SubmodelElementList":
        return el.get("value") or [], True
    return [], False


def _walk(el: dict, path: str, in_list: bool, out: list[Finding], used: set[str]) -> None:
    used.update(_semantic_ids(el))
    short = el.get("idShort")
    if in_list and short is not None:
        out.append(Finding(ERROR, "AASd-120", path, "an element inside a list has an idShort"))
    elif not in_list and not is_id_short(short):
        out.append(Finding(ERROR, "idShort", path, f"missing or invalid idShort {short!r}"))
    children, items = _children(el)
    seen: set[str] = set()
    for i, child in enumerate(children):
        if not isinstance(child, dict):
            continue
        cshort = child.get("idShort")
        if not items and isinstance(cshort, str):
            if cshort in seen:
                out.append(Finding(ERROR, "AASd-022", f"{path}/{cshort}",
                                   "idShort repeated among siblings"))
            seen.add(cshort)
        _walk(child, f"{path}/{cshort if not items else i}", items, out, used)


def _id_findings(env: dict) -> tuple[list[Finding], dict | None]:
    out: list[Finding] = []
    shells = env.get("assetAdministrationShells") or []
    if len(shells) != 1:
        out.append(Finding(ERROR, "shell-count", "assetAdministrationShells",
                           f"expected exactly one shell, found {len(shells)}"))
    if not shells or not isinstance(shells[0], dict):
        return out, None
    shell = shells[0]
    m = _SHELL.match(shell.get("id") or "")
    if not m:
        out.append(Finding(ERROR, "id-scheme", "shell", f"shell id {shell.get('id')!r} is "
                           "not https://id.madfam.io/aas/{kind}/{slug}/{16 hex}"))
        return out, None
    kind, slug, rev = m.groups()
    info = shell.get("assetInformation") or {}
    if info.get("assetKind") != "Type":
        out.append(Finding(ERROR, "asset-kind", "shell", "a commons shell must be assetKind Type"))
    am = _ASSET.match(info.get("globalAssetId") or "")
    if not am or am.groups() != (kind, slug):
        out.append(Finding(ERROR, "id-scheme", "shell/assetInformation",
                           f"globalAssetId {info.get('globalAssetId')!r} does not name "
                           f"{BASE}/asset/{kind}/{slug}"))
    specific = {s.get("name"): s.get("value") for s in info.get("specificAssetIds") or []
                if isinstance(s, dict)}
    digest = specific.get(_DIGEST_KEY[kind])
    if not isinstance(digest, str) or digest[:16] != rev:
        out.append(Finding(ERROR, "id-scheme", "shell/assetInformation",
                           f"specificAssetId {_DIGEST_KEY[kind]} does not start with the "
                           f"revision {rev} in the shell id"))
    referenced = {
        (r.get("keys") or [{}])[0].get("value")
        for r in shell.get("submodels") or [] if isinstance(r, dict)
    }
    present = set()
    for sm in env.get("submodels") or []:
        sid = sm.get("id") or ""
        present.add(sid)
        sm_m = _SUBMODEL.match(sid)
        if not sm_m or sm_m.groups() != (kind, slug, rev, sm.get("idShort")):
            out.append(Finding(ERROR, "id-scheme", f"submodel {sm.get('idShort')}",
                               f"id {sid!r} is not {BASE}/sm/{kind}/{slug}/{rev}/"
                               f"{sm.get('idShort')}"))
    for missing in sorted(referenced - present, key=str):
        out.append(Finding(ERROR, "dangling", "shell/submodels",
                           f"shell references submodel {missing!r} not in the environment"))
    for extra in sorted(present - referenced):
        out.append(Finding(ERROR, "orphan", "submodels",
                           f"submodel {extra!r} is not referenced by the shell"))
    return out, shell


def _conformance_findings(env: dict) -> list[Finding]:
    out = []
    for sm in env.get("submodels") or []:
        ids = _semantic_ids({"semanticId": sm.get("semanticId")})
        primary = ids[0] if ids else None
        where = f"submodel {sm.get('idShort')}"
        if primary in _IDTA_BY_ID:
            missing = missing_mandatory(sm, _IDTA_BY_ID[primary])
            if missing:
                out.append(Finding(ERROR, "conformance-claim", where,
                                   f"claims {primary} without mandatory element(s): "
                                   + "; ".join(missing)))
        elif primary not in _MADFAM_IDS:
            out.append(Finding(ERROR, "conformance-claim", where,
                               f"semanticId {primary!r} is neither a MADFAM template nor an "
                               "IDTA template this package can verify"))
    return out


def _concept_findings(env: dict, used: set[str]) -> list[Finding]:
    out = []
    described = {cd.get("id") for cd in env.get("conceptDescriptions") or []}
    lexicon = bundled_lexicon()
    for sid in sorted(used):
        if sid.startswith((_CONCEPT_PREFIX, _TEMPLATE_PREFIX)) and sid not in described:
            out.append(Finding(ERROR, "concept", "conceptDescriptions",
                               f"MADFAM semanticId {sid} has no ConceptDescription"))
    for cd_id in sorted(i for i in described if isinstance(i, str)):
        if cd_id.startswith(_CONCEPT_PREFIX) and cd_id[len(_CONCEPT_PREFIX):] not in lexicon:
            out.append(Finding(WARNING, "concept", cd_id,
                               "concept is not a term of the bundled lexicon"))
        elif cd_id.startswith(_TEMPLATE_PREFIX) and cd_id not in _MADFAM_IDS:
            out.append(Finding(WARNING, "concept", cd_id, "unknown MADFAM template"))
    return out


def basyx_available() -> bool:
    try:
        import basyx.aas.adapter.json  # noqa: F401
    except ImportError:
        return False
    return True


def basyx_roundtrip(env: dict) -> list[Finding]:
    """Strict BaSyx deserialization, serialization and re-read. Requires the extra."""
    from basyx.aas.adapter.json import object_store_to_json, read_aas_json_file

    try:
        store = read_aas_json_file(io.StringIO(json.dumps(env)), failsafe=False)
        again = read_aas_json_file(io.StringIO(object_store_to_json(store)), failsafe=False)
    except Exception as exc:  # the SDK raises several types; all mean "not accepted"
        return [Finding(ERROR, "basyx", "$", f"{type(exc).__name__}: {str(exc)[:400]}")]
    expected = sum(len(env.get(k) or []) for k in
                   ("assetAdministrationShells", "submodels", "conceptDescriptions"))
    if len(store) != expected or len(again) != expected:
        return [Finding(ERROR, "basyx", "$", f"round-trip kept {len(store)}/{len(again)} of "
                                             f"{expected} identifiables")]
    return []


def check_environment(env: object, basyx: str = "auto") -> AasCheckResult:
    """Check one Environment. ``basyx``: ``auto`` (run when installed), ``require``
    (error when not installed) or ``off``."""
    result = AasCheckResult()
    if not isinstance(env, dict):
        result.findings.append(Finding(ERROR, "schema", "$", "an Environment is a JSON object"))
        return result
    result.findings += _schema_findings(env)
    ids, _shell = _id_findings(env)
    result.findings += ids
    used: set[str] = set()
    for i, sm in enumerate(env.get("submodels") or []):
        if isinstance(sm, dict):
            _walk(sm, f"submodels/{sm.get('idShort', i)}", False, result.findings, used)
    for shell in env.get("assetAdministrationShells") or []:
        if isinstance(shell, dict) and not is_id_short(shell.get("idShort")):
            result.findings.append(Finding(ERROR, "idShort", "shell", "missing or invalid idShort"))
    result.findings += _conformance_findings(env)
    result.findings += _concept_findings(env, used)
    if basyx == "off":
        result.basyx = "skipped"
    elif basyx_available():
        problems = basyx_roundtrip(env)
        result.findings += problems
        result.basyx = "failed" if problems else "verified"
    else:
        result.basyx = "not installed"
        if basyx == "require":
            result.findings.append(Finding(
                ERROR, "basyx", "$",
                'BaSyx SDK not installed: pip install "hyperobjects-spec[aas-verify]"'))
    return result


def check_environment_file(path: str | Path, basyx: str = "auto") -> AasCheckResult:
    env = json.loads(Path(path).read_text(encoding="utf-8"))
    return check_environment(env, basyx)
