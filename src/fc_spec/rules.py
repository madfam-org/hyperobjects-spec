"""Pure, path-independent conformance rules for the Fashion Cabinet v1 contracts.

Every function takes already-parsed data (never a path, never the repo) and returns
a list of human-readable problems (empty = conformant). These are the SAME rules
Fashion Cabinet's CI lanes enforce; keeping them here, importable, means the
third-party runner and the in-repo lanes can never drift. Schema validation is done
separately (conformance.py); these are the cross-field / semantic checks the schema
cannot express.
"""

from __future__ import annotations

import ast


# ── shared vocabulary ────────────────────────────────────────────────────────
def canonical_landmark_codes(body_schema: dict) -> set[str]:
    """The canonical landmark-code vocabulary, read from the body-measurements
    schema's enum (the single source of truth)."""
    return set(body_schema["$defs"]["landmark_code"]["enum"])


# ── garment manifest ─────────────────────────────────────────────────────────
def garment_manifest_rules(doc: dict, body_schema: dict) -> list[str]:
    """Cross-field rules for a garment manifest (mirrors validate_manifests'
    _check_mode_piece_refs + the measurement-code vocabulary rule)."""
    problems: list[str] = []
    piece_ids = {p["id"] for p in doc.get("pieces", []) if isinstance(p, dict)}
    param_ids = {p["id"] for p in doc.get("parameters", []) if isinstance(p, dict)}

    for mode in doc.get("modes", []):
        for pid in mode.get("pieces", []):
            if pid not in piece_ids:
                problems.append(f"mode '{mode.get('id')}' references unknown piece '{pid}'")

    for iface in doc.get("hyperobject", {}).get("interfaces", []):
        for ref in iface.get("parameters", []):
            if ref not in param_ids:
                problems.append(
                    f"interface '{iface.get('id')}' references unknown parameter '{ref}'"
                )

    # A parameter bound to a body landmark must use a canonical code.
    canonical = canonical_landmark_codes(body_schema)
    for p in doc.get("parameters", []):
        if not isinstance(p, dict):
            continue
        code = (p.get("measurement") or {}).get("code")
        if code is not None and code not in canonical:
            problems.append(
                f"parameter '{p.get('id')}' measurement.code '{code}' is not a "
                f"canonical landmark code"
            )
    return problems


# ── hardware reference ───────────────────────────────────────────────────────
# Pure, side-effect-free numeric builtins a params_map value expression may call to
# turn a garment dimension into a hardware count/size (e.g. `round(width / pitch)` for
# a ring column count). These are call TARGETS, not parameters — they must not be
# required to resolve to a notion parameter. The set is deliberately tiny and purely
# arithmetic; the expression is still only ever parsed, never evaluated.
SAFE_MAP_FUNCS = frozenset({"round", "ceil", "floor", "int", "min", "max", "abs"})


def _idents(expr: str) -> set[str]:
    """Bare operand identifiers in a params_map value expression (parse-only, never
    eval). A name used as a call target from the SAFE_MAP_FUNCS whitelist is a numeric
    builtin, not a parameter reference, so it is excluded."""
    tree = ast.parse(str(expr), mode="eval")
    called_safe = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in SAFE_MAP_FUNCS
    }
    return {
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id not in called_safe
    }


def hardware_ref_rules(doc: dict, resolve: dict[str, list[str]]) -> list[str]:
    """Conformance rules for a manifest's notion.hardware_ref, per the Hardware
    Reference spec. `resolve` maps a yantra4d slug -> its parameter ids (the
    resolution surface — the pinned snapshot in-repo, or any catalog slice a
    third party supplies). Returns problems for a LINKED reference; an unlinked or
    absent reference yields no problems.
    """
    notion = doc.get("notion")
    if not isinstance(notion, dict):
        return []
    hw = notion.get("hardware_ref")
    if not isinstance(hw, dict) or not hw.get("linked"):
        return []

    problems: list[str] = []
    if hw.get("platform") != "yantra4d":
        return [f"linked hardware_ref has platform={hw.get('platform')!r} (expected 'yantra4d')"]
    target_slug = hw.get("project_slug") or ""
    if not target_slug:
        return ["linked=true but project_slug is empty"]

    if target_slug not in resolve:
        known = ", ".join(sorted(resolve)) or "none"
        return [f"project_slug '{target_slug}' does not resolve to a known yantra4d "
                f"cartridge (known: {known})"]

    target_params = set(resolve[target_slug])
    notion_params = {p["id"] for p in doc.get("parameters", []) if isinstance(p, dict)}
    for key, value in (hw.get("params_map") or {}).items():
        if key not in target_params:
            problems.append(
                f"params_map key '{key}' is not a parameter of yantra4d "
                f"'{target_slug}' (has: {', '.join(sorted(target_params)) or 'none'})"
            )
        try:
            refs = _idents(value)
        except SyntaxError as exc:
            problems.append(f"params_map['{key}'] value {value!r} is not a valid expression: {exc}")
            continue
        for ref in sorted(refs):
            if ref not in notion_params:
                problems.append(
                    f"params_map['{key}'] value references '{ref}', which is not a "
                    f"parameter of this notion (has: {', '.join(sorted(notion_params)) or 'none'})"
                )
    return problems


def hardware_dimensional_rules(doc: dict, resolve_full: dict[str, dict]) -> list[str]:
    """The DIMENSIONAL half of the hardware handshake (beyond name resolution).

    A bridged hardware object declares its sewn mating edge as a `flange`-type
    cdg_interface driven by a length parameter (e.g. the zipper's `tape_edge` ←
    `zip_length`). This checks that the garment's params_map feeds that edge's
    dimension from a garment parameter which ALSO drives one of the garment's own
    interfaces — so the same dimension flows to both the garment's edge and the
    hardware's edge, not just a name that happens to resolve.

    `resolve_full` maps slug -> the full snapshot entry (with `cdg_interfaces` +
    `parameter_ids`). Reports a problem only when the garment declares interfaces
    (a garment with none is out of scope, not a violation) and the coupling is
    absent. Returns [] for unlinked/absent refs.
    """
    notion = doc.get("notion")
    if not isinstance(notion, dict):
        return []
    hw = notion.get("hardware_ref")
    if not isinstance(hw, dict) or not hw.get("linked"):
        return []
    target = resolve_full.get(hw.get("project_slug") or "")
    if not isinstance(target, dict):
        return []  # name-resolution failures are hardware_ref_rules' job, not this

    # The flange (sewn-edge) interfaces of the target and the length parameters
    # that drive them.
    flange_params: set[str] = set()
    for iface in target.get("cdg_interfaces") or []:
        if iface.get("geometry_type") == "flange":
            flange_params.update(iface.get("parameters") or [])
    if not flange_params:
        return []  # no sewn edge declared — nothing dimensional to couple

    # The garment parameters that drive the garment's OWN interfaces.
    garment_iface_params: set[str] = set()
    garment_ifaces = (doc.get("hyperobject") or {}).get("interfaces") or []
    for iface in garment_ifaces:
        garment_iface_params.update(iface.get("parameters") or [])
    if not garment_ifaces:
        return []  # garment declares no interfaces — out of scope for the handshake

    params_map = hw.get("params_map") or {}
    problems: list[str] = []
    for key, value in params_map.items():
        if key not in flange_params:
            continue  # this mapping doesn't drive the sewn edge
        # value's identifiers are the garment params feeding the sewn-edge dimension.
        try:
            refs = _idents(value)
        except SyntaxError:
            continue  # a malformed expr is hardware_ref_rules' problem
        if not refs:
            continue  # a numeric literal (e.g. a fixed count) — nothing to couple
        if not (refs & garment_iface_params):
            problems.append(
                f"dimensional handshake: hardware '{hw.get('project_slug')}' sews to the "
                f"garment via '{key}' driven by {sorted(refs)}, but none of those drive "
                f"any garment interface ({sorted(garment_iface_params)}) — the garment's "
                f"own edge and the hardware's sewn edge are not dimensionally coupled"
            )
    return problems


# ── body measurements ────────────────────────────────────────────────────────
def body_measurements_rules(doc: dict, body_schema: dict) -> list[str]:
    """Semantic rules for a measurement set beyond the schema: every landmark key is
    canonical (the schema's propertyNames already enforces this, but a third party
    running against a partial schema copy benefits from the explicit check), and
    units, if present, are mm."""
    problems: list[str] = []
    canonical = canonical_landmark_codes(body_schema)
    for code in (doc.get("landmarks") or {}):
        if code not in canonical:
            problems.append(f"landmark '{code}' is not a canonical landmark code")
    units = doc.get("units")
    if units is not None and units != "mm":
        problems.append(f"units must be 'mm' (got {units!r})")
    return problems


# ── explode JSON ─────────────────────────────────────────────────────────────
def explode_json_rules(doc: dict) -> list[str]:
    """Conformance rules for an explode-JSON payload, per the Explode JSON spec:
    has name + mm units + a non-empty pieces list, every declared seam is ok
    (delta within tolerance), and no error-level issue is present."""
    problems: list[str] = []
    if not doc.get("name"):
        problems.append("missing 'name'")
    if doc.get("units") != "mm":
        problems.append(f"units must be 'mm' (got {doc.get('units')!r})")
    pieces = doc.get("pieces")
    if not isinstance(pieces, list) or not pieces:
        problems.append("'pieces' must be a non-empty array")
    for i, seam in enumerate(doc.get("seams") or []):
        if isinstance(seam, dict) and seam.get("ok") is False:
            a, b = seam.get("a"), seam.get("b")
            problems.append(
                f"seam[{i}] {a}↔{b} is not ok "
                f"(length_a={seam.get('length_a_mm')} length_b={seam.get('length_b_mm')} "
                f"ease={seam.get('ease_mm')} tol={seam.get('tol_mm')})"
            )
    for issue in doc.get("issues") or []:
        sev = issue.get("severity") if isinstance(issue, dict) else None
        if sev in (None, "error"):
            msg = issue.get("message") if isinstance(issue, dict) else issue
            problems.append(f"error-level issue: {msg}")
    return problems


# ── fabric card ──────────────────────────────────────────────────────────────
def fabric_card_rules(doc: dict) -> list[str]:
    """Semantic rules for a fabric card beyond the schema: e_textile flags are
    booleans (the manifest-rules invariant), and the two required identity/physical
    blocks carry a slug and a gsm respectively."""
    problems: list[str] = []
    et = doc.get("e_textile")
    if isinstance(et, dict):
        flag = et.get("conductive_thread_compatible")
        if flag is not None and not isinstance(flag, bool):
            problems.append("e_textile.conductive_thread_compatible must be a boolean")
    if not (doc.get("fabric") or {}).get("slug"):
        problems.append("fabric.slug is required")
    if (doc.get("physical") or {}).get("gsm") is None:
        problems.append("physical.gsm is required")
    return problems
