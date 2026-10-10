"""Pure conformance rules for a sheet-commons manifest (``sheet-manifest``).

Every function takes already-parsed data (never a path) and returns a list of
human-readable problems; empty means conformant. Schema validation is separate
(conformance.py). These are the cross-field checks the schema cannot express.

Strict from birth — the false-positive analysis, written down
--------------------------------------------------------------
The keystone's doctrine (AGENTS.md) is that a new rule lands as a NOTE until its
false-positive analysis against the whole commons is written down, because a rule that
fires on healthy cartridges is wrong, not strict. Every rule here is a FAILURE from the
first release, and this is the analysis that licenses it:

* The sheet commons (``sheet-hyperobjects``) holds **zero** cartridges on the day these
  rules land (2026-10-10). A whole-commons false-positive analysis over an empty set is
  vacuous: no existing cartridge can be broken, and every future cartridge is authored
  against these rules rather than retro-fitted to them. That is the opposite situation
  from the solid and soft commons, where 500+ cartridges predated every rule.
* The rules are the sibling commons' own stated bars, which they could not enforce
  retroactively: both commons' contributor contracts say "born quadrilingual" and "both
  licence fields agree and are CERN-OHL-W-2.0", and the keystone verified on
  2026-10-10 that neither ``y4d-spec`` nor ``fc-spec`` checks either (358/516 soft
  descriptions are en/es/fr only). A third commons that starts with the bar enforced
  never accumulates that debt.
* The proxies for "healthy cartridges" are the faithful minimal fixtures in
  ``tests/fixtures/sheet/`` (they pass every rule); each rule also has a failing case
  in ``tests/test_pliego_spec.py``. When the first real commons cartridges land, the
  fixtures are replaced by them in the re-pin, and any rule that fires on one of them
  is re-examined before that re-pin merges.

The licence
-----------
``SHEET_COMMONS_LICENSE`` is the sheet commons' object licence: CERN-OHL-W-2.0, for
cartridges and paper stock cards (owner ruling 2026-10-10, recorded in internal-devops
as an ADR in the companion RFC 0044 PR). Both ``project.attribution.license`` and
``hyperobject.commons_license`` must equal it, and so each other.
"""

from __future__ import annotations

import ast
import re

from y4d_spec.rules import dead_parameter_problems as _y4d_dead_parameter_problems

__all__ = [
    "LANGUAGES",
    "SHEET_COMMONS_LICENSE",
    "SLUG_RE",
    "DEFAULT_SCRIPT",
    "i18n_rules",
    "license_rules",
    "slug_rules",
    "reference_rules",
    "heritage_rules",
    "hardware_ref_rules",
    "constraint_rules",
    "control_rules",
    "dead_parameter_problems",
    "safe_formula_problems",
    "all_manifest_rules",
]

#: The object licence of the sheet commons — cartridges and paper stock cards.
#: Owner ruling 2026-10-10, recorded in internal-devops as an ADR in the companion
#: RFC 0044 PR. One constant, read by the rule and by the docs test, so the value
#: lives in exactly one place.
SHEET_COMMONS_LICENSE = "CERN-OHL-W-2.0"

#: Born quadrilingual (RFC 0039 §7). Spanish is the house register.
LANGUAGES = ("en", "es", "fr", "pt")

#: Strict kebab case, the grammar of every cross-reference surface (identity, lexicon,
#: article). The y4d grammar admits `_` and the FC one a trailing `-`; a sheet slug is
#: valid wherever the object is named.
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SLUG_MAX = 80

#: A mode with no `script_file` runs this.
DEFAULT_SCRIPT = "main.py"


def _list(doc: dict, key: str) -> list[dict]:
    value = doc.get(key)
    return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []


def _hyperobject(doc: dict) -> dict:
    ho = doc.get("hyperobject")
    return ho if isinstance(ho, dict) else {}


def _project(doc: dict) -> dict:
    proj = doc.get("project")
    return proj if isinstance(proj, dict) else {}


def _ids(entries: list[dict]) -> list[str]:
    return [e["id"] for e in entries if isinstance(e.get("id"), str)]


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for v in values:
        if v in seen and v not in dupes:
            dupes.append(v)
        seen.add(v)
    return dupes


# ── i18n ─────────────────────────────────────────────────────────────────────
def _i18n_problems(value: object, where: str) -> list[str]:
    if isinstance(value, str):
        return [f"{where}: a bare string — every user-visible text is born quadrilingual "
                f"({', '.join(LANGUAGES)})"]
    if not isinstance(value, dict):
        return [f"{where}: not a four-language object"]
    return [
        f"{where}.{lang}: missing or blank — en, es, fr and pt are all required (born "
        f"quadrilingual, RFC 0039 §7)"
        for lang in LANGUAGES
        if not isinstance(value.get(lang), str) or not value[lang].strip()
    ]


def i18n_rules(doc: dict) -> list[str]:
    """Every user-visible text carries en, es, fr AND pt, none blank.

    The schema requires the four keys; this catches the failure it cannot see — a key
    present with a blank or whitespace-only value, which is what a half-finished
    translation looks like. Surfaces: project name (when an object) and description,
    and the labels of modes, sheets, parameter groups, parameters (with tooltips and
    option labels), presets, controls and interfaces, constraint messages, and the
    societal benefit.
    """
    problems: list[str] = []
    proj = _project(doc)
    if isinstance(proj.get("name"), dict):
        problems += _i18n_problems(proj["name"], "project.name")
    if "description" in proj:
        problems += _i18n_problems(proj["description"], "project.description")

    for key in ("modes", "sheets", "parameter_groups", "presets", "controls"):
        for i, entry in enumerate(_list(doc, key)):
            ident = entry.get("id", i)
            if "label" in entry:
                problems += _i18n_problems(entry["label"], f"{key}['{ident}'].label")

    for i, p in enumerate(_list(doc, "parameters")):
        ident = p.get("id", i)
        if "label" in p:
            problems += _i18n_problems(p["label"], f"parameters['{ident}'].label")
        if "tooltip" in p:
            problems += _i18n_problems(p["tooltip"], f"parameters['{ident}'].tooltip")
        for j, opt in enumerate(p.get("options") or []):
            if isinstance(opt, dict) and "label" in opt:
                problems += _i18n_problems(
                    opt["label"], f"parameters['{ident}'].options[{j}].label"
                )

    for i, c in enumerate(_list(doc, "constraints")):
        if "message" in c:
            problems += _i18n_problems(c["message"], f"constraints[{i}].message")

    ho = _hyperobject(doc)
    for i, iface in enumerate(_list(ho, "interfaces")):
        ident = iface.get("id", i)
        if "label" in iface:
            problems += _i18n_problems(iface["label"], f"hyperobject.interfaces['{ident}'].label")
    if "societal_benefit" in ho:
        problems += _i18n_problems(ho["societal_benefit"], "hyperobject.societal_benefit")
    return problems


# ── licence ──────────────────────────────────────────────────────────────────
def license_rules(doc: dict, license_id: str = SHEET_COMMONS_LICENSE) -> list[str]:
    """Both licence fields equal the sheet commons licence, and so agree.

    The two fields say the same thing from two places (who made it / what the commons
    publishes it under), and the sibling commons' contributor contracts already demand
    that they agree — without a gate. Here it is the gate. A third-party-licensed
    object would need a registered carve-out ruling; none exists for this commons, so
    none is honoured.
    """
    problems: list[str] = []
    attribution = _project(doc).get("attribution")
    declared = attribution.get("license") if isinstance(attribution, dict) else None
    commons = _hyperobject(doc).get("commons_license")

    for value, where in ((declared, "project.attribution.license"),
                         (commons, "hyperobject.commons_license")):
        if not isinstance(value, str) or not value:
            problems.append(f"{where}: required — the sheet commons licence is {license_id}")
        elif value != license_id:
            problems.append(
                f"{where}: {value!r} — every sheet-commons object is published under "
                f"{license_id} (owner ruling 2026-10-10)"
            )
    if (isinstance(declared, str) and isinstance(commons, str) and declared and commons
            and declared != commons):
        problems.append(
            f"licence fields disagree: project.attribution.license={declared!r} but "
            f"hyperobject.commons_license={commons!r} — they must be the same value"
        )
    return problems


# ── slugs ────────────────────────────────────────────────────────────────────
def _slug_problem(value: object, where: str) -> list[str]:
    if not isinstance(value, str) or not SLUG_RE.match(value) or not 2 <= len(value) <= SLUG_MAX:
        return [
            f"{where}: {value!r} is not a strict kebab-case slug (lowercase letters and "
            f"digits joined by single hyphens, 2–{SLUG_MAX} characters; no underscore, "
            f"no leading, trailing or doubled hyphen)"
        ]
    return []


def slug_rules(doc: dict) -> list[str]:
    """`project.slug`, sheet ids and stock slugs follow the strict kebab grammar.

    The schema carries the same pattern; this rule says it in words a contributor can
    act on, and covers the slugs the schema might not reach in an older pin.
    """
    problems = _slug_problem(_project(doc).get("slug"), "project.slug")
    for s in _list(doc, "sheets"):
        problems += _slug_problem(s.get("id"), f"sheets['{s.get('id')}'].id")
        if "stock" in s:
            problems += _slug_problem(s["stock"], f"sheets['{s.get('id')}'].stock")
    stock = doc.get("stock")
    if isinstance(stock, dict):
        if "default" in stock:
            problems += _slug_problem(stock["default"], "stock.default")
        for i, alt in enumerate(stock.get("alternatives") or []):
            problems += _slug_problem(alt, f"stock.alternatives[{i}]")
    return problems


# ── references ───────────────────────────────────────────────────────────────
def reference_rules(doc: dict) -> list[str]:
    """Every id a manifest names is one it declares, and no id is declared twice.

    Modes name sheets; parameters name modes and groups; presets name a mode and
    parameters; interfaces name parameters and sheet edges; an interface frame names a
    sheet.
    """
    problems: list[str] = []
    modes, sheets = _list(doc, "modes"), _list(doc, "sheets")
    params, groups = _list(doc, "parameters"), _list(doc, "parameter_groups")
    mode_ids, sheet_ids = set(_ids(modes)), set(_ids(sheets))
    param_ids, group_ids = set(_ids(params)), set(_ids(groups))
    ho = _hyperobject(doc)
    interfaces = _list(ho, "interfaces")

    for key, entries in (("modes", modes), ("sheets", sheets), ("parameters", params),
                         ("parameter_groups", groups), ("presets", _list(doc, "presets")),
                         ("controls", _list(doc, "controls")),
                         ("hyperobject.interfaces", interfaces)):
        for dup in _duplicates(_ids(entries)):
            problems.append(f"{key}: id '{dup}' is declared more than once")

    for m in modes:
        for sid in m.get("sheets") or []:
            if sid not in sheet_ids:
                problems.append(f"mode '{m.get('id')}' references unknown sheet '{sid}'")

    for p in params:
        for mid in p.get("modes") or []:
            if mid not in mode_ids:
                problems.append(f"parameter '{p.get('id')}' is scoped to unknown mode '{mid}'")
        if "group" in p and p["group"] not in group_ids:
            problems.append(f"parameter '{p.get('id')}' names unknown group '{p['group']}'")
        if p.get("type") == "select" and not p.get("options"):
            problems.append(f"parameter '{p.get('id')}': a select needs options")
        lo, hi = p.get("min"), p.get("max")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo > hi:
            problems.append(f"parameter '{p.get('id')}': min {lo} is greater than max {hi}")
        default = p.get("default")
        if (p.get("type") == "slider" and isinstance(default, (int, float))
                and not isinstance(default, bool)):
            if (isinstance(lo, (int, float)) and default < lo) or (
                    isinstance(hi, (int, float)) and default > hi):
                problems.append(
                    f"parameter '{p.get('id')}': default {default} is outside [{lo}, {hi}]"
                )
        if p.get("type") == "select" and "default" in p and p.get("options"):
            values = [o.get("value") for o in p["options"] if isinstance(o, dict)]
            if default not in values:
                problems.append(
                    f"parameter '{p.get('id')}': default {default!r} is not one of its options"
                )

    for pr in _list(doc, "presets"):
        if "mode" in pr and pr["mode"] not in mode_ids:
            problems.append(f"preset '{pr.get('id')}' names unknown mode '{pr['mode']}'")
        values = pr.get("values")
        for key in values if isinstance(values, dict) else []:
            if key not in param_ids:
                problems.append(f"preset '{pr.get('id')}' sets unknown parameter '{key}'")

    for iface in interfaces:
        iid = iface.get("id")
        for ref in iface.get("parameters") or []:
            if ref not in param_ids:
                problems.append(
                    f"interface '{iid}' references unknown parameter '{ref}' "
                    f"(parameters declare: {', '.join(sorted(param_ids)) or 'none'})"
                )
        for edge in iface.get("edges") or []:
            if isinstance(edge, dict) and edge.get("sheet") not in sheet_ids:
                problems.append(
                    f"interface '{iid}' names an edge on unknown sheet '{edge.get('sheet')}'"
                )
        frame = iface.get("frame")
        if isinstance(frame, dict) and frame.get("sheet") not in sheet_ids:
            problems.append(f"interface '{iid}': frame names unknown sheet '{frame.get('sheet')}'")
    return problems


# ── heritage ─────────────────────────────────────────────────────────────────
def heritage_rules(doc: dict) -> list[str]:
    """A heritage claim carries sources (RFC 0039 §7: no uncited cultural claim).

    The schema requires a non-empty `sources` list; this also refuses blank entries.
    Lineage is not judged here: lineage is provenance, heritage is the cultural claim,
    and only the claim engages the citation bar.
    """
    heritage = _hyperobject(doc).get("heritage")
    if heritage is None:
        return []
    if not isinstance(heritage, dict):
        return ["hyperobject.heritage: must be an object with a tradition and sources"]
    sources = heritage.get("sources")
    cited = [s for s in sources if isinstance(s, str) and s.strip()] if isinstance(
        sources, list) else []
    if not cited:
        return [
            "hyperobject.heritage: a heritage claim must cite at least one source — no "
            "uncited cultural or historical claim (RFC 0039 §7)"
        ]
    if isinstance(sources, list) and len(cited) != len(sources):
        return ["hyperobject.heritage.sources: blank entries are not citations"]
    return []


# ── bridges ──────────────────────────────────────────────────────────────────
#: Numeric builtins a params_map expression may call (the same set fc_spec allows).
SAFE_MAP_FUNCS = frozenset({"round", "ceil", "floor", "int", "min", "max", "abs"})


def _map_idents(expr: str) -> set[str]:
    tree = ast.parse(str(expr), mode="eval")
    called = {
        n.func.id for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in SAFE_MAP_FUNCS
    }
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in called}


def hardware_ref_rules(doc: dict) -> list[str]:
    """The local half of the yantra4d bridge: a linked reference names a slug, and
    every `params_map` expression parses and reads only this cartridge's parameters.

    Whether `project_slug` and the map's keys exist on the yantra4d side is the remote
    half, which needs a catalog; generalising `fc-spec check hardware-ref --resolve`
    and `ho-bridge` to a sheet source is a deferred follow-up.
    """
    hw = doc.get("hardware_ref")
    if not isinstance(hw, dict):
        return []
    problems: list[str] = []
    if hw.get("linked") and not hw.get("project_slug"):
        problems.append("hardware_ref: linked=true but project_slug is empty")
    param_ids = set(_ids(_list(doc, "parameters")))
    params_map = hw.get("params_map")
    for key, value in (params_map.items() if isinstance(params_map, dict) else []):
        try:
            refs = _map_idents(value)
        except SyntaxError as exc:
            problems.append(f"hardware_ref.params_map['{key}']: {value!r} is not a valid "
                            f"expression: {exc.msg}")
            continue
        for ref in sorted(refs - param_ids):
            problems.append(
                f"hardware_ref.params_map['{key}'] reads '{ref}', which is not a parameter "
                f"of this cartridge"
            )
    return problems


# ── constraints (safeFormula) ────────────────────────────────────────────────
_SF_TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+(?:\.\d*)?|\.\d+)|(?P<ident>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op>===|!==|==|!=|<=|>=|&&|\|\||[-+*/%<>!?:()])|(?P<bad>\S))"
)
SAFE_FORMULA_MAX_CHARS = 256
SAFE_FORMULA_MAX_TOKENS = 128


def safe_formula_problems(expression: str, numeric_params: set[str],
                          all_params: set[str]) -> list[str]:
    """Why `expression` would be swallowed by the Studio's `safeFormula` evaluator.

    The evaluator wraps evaluation in a catch-all, so an expression it cannot evaluate
    never fires and reads exactly like a satisfied one. The four ways that happens and
    the only four this checks: too long, a string literal, a function call, and an
    identifier that is not a numeric parameter (unknown, or a text/select one — the
    dialect has no strings, so it cannot compare them).
    """
    if not isinstance(expression, str):
        return ["not a string"]
    problems: list[str] = []
    if len(expression) > SAFE_FORMULA_MAX_CHARS:
        problems.append(f"longer than {SAFE_FORMULA_MAX_CHARS} characters")
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(expression):
        m = _SF_TOKEN.match(expression, pos)
        if m is None or m.end() == pos:
            break
        pos = m.end()
        kind = m.lastgroup
        if kind is None:
            continue
        tokens.append((kind, m.group(kind)))
    if len(tokens) > SAFE_FORMULA_MAX_TOKENS:
        problems.append(f"more than {SAFE_FORMULA_MAX_TOKENS} tokens")
    for i, (kind, text) in enumerate(tokens):
        if kind == "bad":
            if text in "\"'`":
                problems.append("a string literal — the dialect has none")
            else:
                problems.append(f"unsupported character {text!r}")
        elif kind == "ident":
            if i + 1 < len(tokens) and tokens[i + 1] == ("op", "("):
                problems.append(f"a function call {text}() — the dialect has no function calls")
            elif text not in all_params:
                problems.append(f"unknown identifier '{text}' (not a declared parameter)")
            elif text not in numeric_params:
                problems.append(f"'{text}' is not a numeric parameter — the dialect cannot "
                                f"compare text or select values")
    return list(dict.fromkeys(problems))


def constraint_rules(doc: dict) -> list[str]:
    params = _list(doc, "parameters")
    all_params = set(_ids(params))
    numeric: set[str] = set()
    for p in params:
        if not isinstance(p.get("id"), str):
            continue
        if p.get("type") in ("slider", "checkbox"):
            numeric.add(p["id"])
        elif p.get("type") == "select":
            values = [o.get("value") for o in p.get("options") or [] if isinstance(o, dict)]
            if values and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                              for v in values):
                numeric.add(p["id"])
    problems: list[str] = []
    for i, c in enumerate(_list(doc, "constraints")):
        for why in safe_formula_problems(c.get("expression"), numeric, all_params):
            problems.append(
                f"constraints[{i}].expression: {why} — the Studio's safeFormula evaluator "
                f"would swallow it and the constraint would never fire"
            )
    return problems


# ── controls (informational mirror) ──────────────────────────────────────────
def control_rules(doc: dict) -> list[str]:
    problems: list[str] = []
    for c in _list(doc, "controls"):
        cid, lo, hi, default = c.get("id"), c.get("min"), c.get("max"), c.get("default")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo > hi:
            problems.append(f"control '{cid}': min {lo} is greater than max {hi}")
        if (isinstance(default, (int, float)) and not isinstance(default, bool)
                and isinstance(lo, (int, float)) and isinstance(hi, (int, float))
                and not lo <= default <= hi):
            problems.append(f"control '{cid}': default {default} is outside [{lo}, {hi}]")
        if c.get("kind") == "toggle" and default is not None and not isinstance(default, bool):
            problems.append(f"control '{cid}': a toggle's default is a boolean")
    return problems


# ── dead parameters (G-DEADPARAM, reused) ────────────────────────────────────
def dead_parameter_problems(doc: dict, sources: dict[str, str]) -> list[str]:
    """G-DEADPARAM for a sheet cartridge, decided by y4d_spec's own rule.

    A Pliego script receives its parameters as bare globals, exactly like a CadQuery
    one (kernel strategy §2), so the decision is the same function: the bare identifier
    in the executable text of a source of a mode that lists the parameter, comments and
    string literals stripped. Only the field name differs — a sheet mode names its
    script in `script_file` (default main.py) — so each mode is presented to the y4d
    rule with that script as its `cq_file`. `sources` is {filename: text}.
    """
    projected = dict(doc)
    projected["modes"] = [
        {**m, "cq_file": m.get("script_file") or DEFAULT_SCRIPT} for m in _list(doc, "modes")
    ]
    return _y4d_dead_parameter_problems(projected, sources)


def all_manifest_rules(doc: dict) -> list[str]:
    """Every pure manifest rule, in one call. Nothing short-circuits."""
    problems: list[str] = []
    problems += slug_rules(doc)
    problems += license_rules(doc)
    problems += i18n_rules(doc)
    problems += reference_rules(doc)
    problems += heritage_rules(doc)
    problems += hardware_ref_rules(doc)
    problems += constraint_rules(doc)
    problems += control_rules(doc)
    return problems
