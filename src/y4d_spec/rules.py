"""Pure, path-independent conformance rules for a Yantra4D cartridge manifest.

Every function takes already-parsed data (never a path, never the repo) and returns
a list of human-readable problems (empty = conformant). These are the PER-CARTRIDGE
checks Yantra4D's own lanes enforce, lifted out of the repo scripts so a third party
can run them on a cartridge that lives anywhere.

Provenance — each rule and where it comes from in the yantra4d repo:

  manifest schema             scripts/qa/validate_manifests.py:60  (jsonschema.validate)
  thumbnail is a string       apps/api/manifest.py:327  (_validate_manifest_strictness)
  tags is a string array      apps/api/manifest.py:334        "
  difficulty enum             apps/api/manifest.py:342        "
  top-level hyperobject block scripts/qa/compliance_audit.py:41 (audit_project check 1)
  hyperobject+commons tags    scripts/qa/compliance_audit.py:45 (audit_project check 2)
  cdg_interfaces params exist scripts/qa/compliance_audit.py    (audit_project check 3)
  export_formats declared     scripts/qa/compliance_audit.py    (audit_project check 4)
  no vendor/ directory        scripts/audit_compliance.py:65  (check_rule_2_no_vendor)
  no absolute/escaping paths  scripts/audit_compliance.py:38   (check_rule_1_...)
  attribution block           scripts/audit_compliance.py:72  (check_rule_3_attribution)
  material-aware coherence    scripts/audit_compliance.py:106 (check_rule_5_...)
  i18n en/es completeness     scripts/qa/i18n_audit.py  (locale parity, applied to manifests)
  commons_license declared    scripts/qa/check_licenses.py  (declared-vs-shipped, declared half)
  parity exemption reason     THIS PACKAGE (G38, 2026-09-06) — see verification_rules

Deliberately NOT here — these are repo-wide, not per-cartridge, and stay in the
platform: catalog drift (generate_commons_catalog.py), cross-cartridge slug
uniqueness (manifest.py discover_projects), and the declared-vs-SHIPPED half of the
license cross-check (needs the LICENSE file on disk; see structure.py).

OpenSCAD/CadQuery geometric parity USED to be on that list (the platform's
tests/scripts/geometric_regression.py). It came off it: whether one cartridge's two
kernels model the same solid is a property of that cartridge, so it belongs on the
merge path and now runs here under `--render --parity` (parity.py, mirroring
scripts/qa/verify_parity.py gate for gate). The manifest half of that policy — the
per-part exemption and its required reason — is `verification_rules` below, and it is
checked with no --render at all, because a check that only ran where the comparison
ran could be switched off by switching the comparison off.
"""

from __future__ import annotations

__all__ = [
    "DIFFICULTIES",
    "manifest_structural_rules",
    "dispatch_rules",
    "i18n_rules",
    "license_rules",
    "hyperobject_rules",
    "verification_rules",
    "all_manifest_rules",
    "render_targets",
    "preset_targets",
    "parameter_defaults",
    "preset_changes_anything",
]

DIFFICULTIES = ("beginner", "intermediate", "advanced")

# The locales a commons cartridge must speak. Yantra4D's i18n lane holds the studio
# locale files at key parity for exactly these two.
REQUIRED_LOCALES = ("en", "es")


def _ids(entries: object) -> set[str]:
    """The `id` values of a manifest list, ignoring malformed entries."""
    if not isinstance(entries, list):
        return set()
    return {e["id"] for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)}


def _i18n_missing(value: object, locales: tuple[str, ...] = REQUIRED_LOCALES) -> list[str]:
    """Locales absent from an i18nString. A bare string counts as `en` only — the
    schema's i18nString allows it, but a commons cartridge that ships one is
    monolingual, which the i18n lane treats as an incomplete translation."""
    if isinstance(value, str):
        return [loc for loc in locales if loc != "en"]
    if isinstance(value, dict):
        return [loc for loc in locales if not isinstance(value.get(loc), str) or not value[loc]]
    return list(locales)


# ── project block strictness (apps/api/manifest.py:307 _validate_manifest_strictness)
def manifest_structural_rules(doc: dict) -> list[str]:
    """The `project` block constraints the API enforces at load time.

    Ported at STRICT strictness. In-repo these are gated by Config.MANIFEST_STRICTNESS,
    which defaults to "warn" and silently defaults the field instead (thumbnail ->
    /logo.png, tags -> [], difficulty -> beginner). A spec runner has no app to keep
    serving, so it reports what the strict path raises: a cartridge that only passes
    because the platform patched it at runtime is not conformant.
    """
    problems: list[str] = []
    proj = doc.get("project")
    if not isinstance(proj, dict):
        return ["project: must be an object"]

    # 1. Thumbnail — manifest.py:327
    if not isinstance(proj.get("thumbnail"), str) or not proj["thumbnail"]:
        problems.append("project.thumbnail: required, must be a non-empty string")

    # 2. Tags — manifest.py:334
    tags = proj.get("tags")
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        problems.append("project.tags: required, must be an array of strings")

    # 3. Difficulty — manifest.py:342
    if proj.get("difficulty") not in DIFFICULTIES:
        problems.append(
            f"project.difficulty: must be one of {', '.join(DIFFICULTIES)} "
            f"(got {proj.get('difficulty')!r})"
        )

    return problems


# ── modes / parts / parameters cross-references + per-part dispatch ───────────
def dispatch_rules(doc: dict) -> list[str]:
    """Cross-references between modes, parts and parameters, and the dispatch-id
    alignment a CadQuery cartridge's `target_part` switch depends on.

    The cross-reference half mirrors compliance_audit.py's reference checks and the
    accessors in apps/api/manifest.py (get_parts_map / get_parts_for_mode) which will
    KeyError or render the wrong body on a dangling reference.

    The dispatch half is the house rule the CadQuery cartridges are written to (see
    any projects/*/main.py: `target_part = str(PARAM(lambda: target_part, "..."))`
    then an if/elif over part ids): a SINGLE-part mode is selected by passing its
    part id as target_part, so a single-part mode's own id must equal that part id.
    A mode named 'stud' listing parts ['socket'] renders the socket whenever the UI
    asks for 'stud'. Multi-part modes are exempt — they render an assembly and are
    dispatched by the mode's own default branch.

    That alignment applies ONLY to CadQuery modes. OpenSCAD modes dispatch by the
    `render_mode` integer on the part (apps/api/manifest.py:138 get_mode_map, and see
    projects/custom-msh/box.scad's `if (render_mode == 0 ...)`), so their mode ids are
    free-form labels and are checked for render_mode coverage instead.
    """
    problems: list[str] = []
    part_ids = _ids(doc.get("parts"))
    param_ids = _ids(doc.get("parameters"))
    modes = doc.get("modes")
    if not isinstance(modes, list):
        return ["modes: must be an array"]

    seen_mode_ids: set[str] = set()
    for i, mode in enumerate(modes):
        if not isinstance(mode, dict):
            problems.append(f"modes[{i}]: must be an object")
            continue
        # The schema offers both `id` and `slug`; the platform's accessors read
        # mode["id"] unconditionally (apps/api/manifest.py:156 get_scad_file_for_mode,
        # :163 get_parts_for_mode), so a slug-only mode is schema-valid but
        # unrenderable. Accept slug as the identifier for the reference checks, and
        # report the missing `id` once rather than cascading through every rule.
        mid = mode.get("id")
        if not isinstance(mid, str) or not mid:
            slug = mode.get("slug")
            if isinstance(slug, str) and slug:
                problems.append(
                    f"mode '{slug}': identified by 'slug' but has no 'id' — the "
                    f"platform's mode accessors read mode['id'], so this mode cannot "
                    f"be selected or rendered"
                )
                mid = slug
            else:
                problems.append(f"modes[{i}]: missing a string 'id'")

        where = f"mode '{mid}'" if mid else f"modes[{i}]"

        if isinstance(mid, str) and mid:
            if mid in seen_mode_ids:
                problems.append(f"{where}: duplicate mode id")
            else:
                seen_mode_ids.add(mid)

        mode_parts = mode.get("parts")
        if not isinstance(mode_parts, list) or not mode_parts:
            problems.append(f"{where}: 'parts' must be a non-empty array")
            mode_parts = []

        for pid in mode_parts:
            if pid not in part_ids:
                problems.append(
                    f"{where}: references unknown part '{pid}' "
                    f"(parts declare: {', '.join(sorted(part_ids)) or 'none'})"
                )

        primary = mode.get("cq_file") or mode.get("scad_file")
        if not isinstance(mode.get("scad_file"), str) or not mode["scad_file"]:
            problems.append(f"{where}: missing 'scad_file' (the mode's primary source file)")

        # Per-part dispatch alignment — CadQuery modes only (see the docstring).
        is_cq = isinstance(primary, str) and primary.endswith((".py", ".cq"))
        if is_cq and isinstance(mid, str) and len(mode_parts) == 1 and mode_parts[0] != mid:
            problems.append(
                f"{where}: single-part CadQuery mode renders part '{mode_parts[0]}' "
                f"but is dispatched as target_part='{mid}' — a single-part mode's id "
                f"must equal its part id, or the cartridge renders the wrong body"
            )

    # NOT CHECKED: render_mode uniqueness across parts. It looks like the OpenSCAD
    # counterpart of the target_part rule (parts are selected by the render_mode
    # integer — apps/api/manifest.py:138 get_mode_map), but it is not a real bar:
    # get_mode_map reads `p.get("render_mode", 0)`, so parts legitimately share the
    # default 0 whenever a mode dispatches by SOURCE FILE instead (projects/gears has
    # six parts at render_mode 0, one .scad/.py pair per mode, and is correct).
    # Enforcing uniqueness flagged 29 healthy cartridges.

    # Every declared part should be reachable from some mode, else it can never render.
    reachable = {
        pid
        for m in modes
        if isinstance(m, dict) and isinstance(m.get("parts"), list)
        for pid in m["parts"]
    }
    for pid in sorted(part_ids - reachable):
        problems.append(f"part '{pid}': not listed by any mode — it can never be rendered")

    # Parameter mode-scopes must name real modes.
    for p in doc.get("parameters") or []:
        if not isinstance(p, dict):
            continue
        for key in ("modes", "visible_in_modes"):
            scope = p.get(key)
            if not isinstance(scope, list):
                continue
            for mid in scope:
                if mid not in seen_mode_ids:
                    problems.append(
                        f"parameter '{p.get('id')}': {key} names unknown mode '{mid}'"
                    )

    # Duplicate parameter ids collide when injected as sandbox globals.
    raw_param_ids = [
        p["id"] for p in (doc.get("parameters") or [])
        if isinstance(p, dict) and isinstance(p.get("id"), str)
    ]
    for pid in sorted({x for x in raw_param_ids if raw_param_ids.count(x) > 1}):
        problems.append(f"parameter '{pid}': declared more than once")

    # A parameter id colliding with an injected KERNEL name shadows the sandbox
    # namespace — the cartridge would receive a float where it expects the `cq`
    # module. Mirrors graph_engine.py:50's reserved-name list, MINUS `target_part`:
    # declaring target_part as a select parameter whose options are the part ids is
    # the canonical way a cartridge exposes part selection in the UI (see
    # projects/body-form), not a collision.
    reserved = {"cq", "math", "result", "assembly", "part", "show_object"}
    for pid in sorted(param_ids & reserved):
        problems.append(
            f"parameter '{pid}': collides with a name the runner injects into the "
            f"sandbox ({', '.join(sorted(reserved))})"
        )

    # A declared target_part parameter must offer exactly the renderable part ids —
    # an option naming no part renders nothing, and a part with no option is
    # unreachable from the UI.
    for p in doc.get("parameters") or []:
        if not isinstance(p, dict) or p.get("id") != "target_part":
            continue
        options = {
            o.get("value")
            for o in (p.get("options") or [])
            if isinstance(o, dict) and isinstance(o.get("value"), str)
        }
        for extra in sorted(options - part_ids):
            problems.append(
                f"parameter 'target_part': option '{extra}' names no declared part"
            )

    return problems


# ── hyperobject block (scripts/qa/compliance_audit.py) ────────────────────────
def hyperobject_rules(doc: dict) -> list[str]:
    """The hyperobject metadata consistency checks — compliance_audit.py's audit_project.

    A cartridge is a hyperobject if project.hyperobject.is_hyperobject is true, or if
    a top-level `hyperobject` block carries cdg_interfaces (compliance_audit.py's
    is_hyperobject_project, which reads BOTH locations because the two coexist).
    """
    problems: list[str] = []
    proj = doc.get("project") if isinstance(doc.get("project"), dict) else {}
    top_ho = doc.get("hyperobject") if isinstance(doc.get("hyperobject"), dict) else {}
    declared = bool((proj.get("hyperobject") or {}).get("is_hyperobject"))
    is_ho = declared or bool(top_ho.get("cdg_interfaces"))

    # Check 4 — export_formats declared for every project (hyperobject or not).
    fmts = doc.get("export_formats")
    if not isinstance(fmts, list) or not fmts:
        problems.append("export_formats: required, must be a non-empty array")

    if not is_ho:
        return problems

    # Check 1 — a declared hyperobject needs the top-level block.
    if not top_ho:
        problems.append(
            "declared a hyperobject (project.hyperobject.is_hyperobject) but has no "
            "top-level 'hyperobject' block"
        )
        return problems

    # Check 2 — tag consistency. Tags live in project.tags; several cartridges mirror
    # them at top level too, so accept either.
    tags = set(proj.get("tags") or []) | set(doc.get("tags") or [])
    for required in ("hyperobject", "commons"):
        if required not in tags:
            problems.append(f"hyperobject is missing the '{required}' tag")

    # Check 3 — every cdg_interface parameter must be a real manifest parameter.
    param_ids = _ids(doc.get("parameters"))
    for iface in top_ho.get("cdg_interfaces") or []:
        if not isinstance(iface, dict):
            problems.append("hyperobject.cdg_interfaces: entry must be an object")
            continue
        iid = iface.get("id")
        if not isinstance(iid, str) or not iid:
            problems.append("hyperobject.cdg_interfaces: entry missing a string 'id'")
        for ref in iface.get("parameters") or []:
            if ref not in param_ids:
                problems.append(
                    f"cdg_interface '{iid}': references unknown parameter '{ref}' "
                    f"(parameters declare: {', '.join(sorted(param_ids)) or 'none'})"
                )

    return problems


# ── i18n (scripts/qa/i18n_audit.py, applied to the manifest's own strings) ────
def i18n_rules(doc: dict) -> list[str]:
    """Every user-visible string carries both {en, es}.

    i18n_audit.py holds the studio's locale files at key parity for en/es. The same
    bar applies to a cartridge's own strings: an es user reading an en-only mode label
    sees an untranslated UI, and the schema's i18nString only requires `en`. Checked
    on the surfaces a user actually reads: project name/description, mode labels, part
    labels, parameter labels, parameter-group labels, and preset labels.
    """
    problems: list[str] = []
    proj = doc.get("project") if isinstance(doc.get("project"), dict) else {}

    desc = proj.get("description")
    if desc is not None:
        for loc in _i18n_missing(desc):
            problems.append(f"project.description: missing '{loc}' translation")

    # `label` is the usual key, but the schema also allows `name` for a display
    # string (parameters declare both; `parts` items are not constrained by the
    # schema at all, and projects/body-form names its parts with `name`). Either
    # satisfies the rule — what matters is that SOME display string exists and is
    # translated.
    def _check_list(key: str) -> None:
        for i, entry in enumerate(doc.get(key) or []):
            if not isinstance(entry, dict):
                continue
            ident = entry.get("id", i)
            display_key = next((k for k in ("label", "name") if k in entry), None)
            if display_key is None:
                problems.append(f"{key}['{ident}']: missing a display string ('label' or 'name')")
                continue
            for loc in _i18n_missing(entry[display_key]):
                problems.append(f"{key}['{ident}'].{display_key}: missing '{loc}' translation")

    for key in ("modes", "parts", "parameters", "parameter_groups", "presets"):
        _check_list(key)

    return problems


# ── license / attribution (check_licenses.py + audit_compliance.py rule 3) ────
def license_rules(doc: dict) -> list[str]:
    """The DECLARED half of the license cross-check.

    check_licenses.py cross-checks a cartridge's declared
    `hyperobject.commons_license` against the LICENSE file it ships. Only the declared
    half is a manifest rule; the shipped half needs the directory and lives in
    structure.py.

    audit_compliance.py's check_rule_3 requires an `attribution` block only for an
    allowlist of upstream forks (gridfinity, stemfie, multiboard) — a repo-specific
    allowlist that cannot travel. Ported as the general rule behind it: a cartridge
    that declares upstream lineage must say who it came from.
    """
    problems: list[str] = []
    proj = doc.get("project") if isinstance(doc.get("project"), dict) else {}
    top_ho = doc.get("hyperobject") if isinstance(doc.get("hyperobject"), dict) else {}
    declared = bool((proj.get("hyperobject") or {}).get("is_hyperobject"))
    is_ho = declared or bool(top_ho.get("cdg_interfaces"))

    if is_ho:
        lic = top_ho.get("commons_license")
        if not isinstance(lic, str) or not lic:
            problems.append(
                "hyperobject.commons_license: required — a commons cartridge must "
                "declare the license it ships under"
            )

    attribution = proj.get("attribution")
    if attribution is not None:
        if not isinstance(attribution, dict):
            problems.append("project.attribution: must be an object")
        elif not any(attribution.get(k) for k in ("source", "author", "upstream", "url")):
            problems.append(
                "project.attribution: declares attribution but names no source "
                "(expected one of: source, author, upstream, url)"
            )

    return problems


# ── verification policy (G38, ruled 2026-09-06) ──────────────────────────────
def verification_rules(doc: dict) -> list[str]:
    """A parity exemption or a widened tolerance must say WHY, in the manifest.

    This is the enforcement half of the per-part parity policy (parity.py). It is a
    MANIFEST rule and not a geometry one on purpose: `y4d-spec check` with no
    `--render` — the thing a PR bot runs on a diff, in seconds, with no CAD kernel —
    is what catches a cartridge that switched the comparison off in silence. If the
    reason were only checked where the comparison runs, a cartridge could turn the
    comparison off and thereby turn off the check on turning it off.

    Two departures from the default need a reason, and nothing else does:

      * `enabled: false` — the comparison will not run for that part.
      * a `tolerance` above the package default — the pair is judged at a wider AABB
        bar than every other pair in the run.

    A tolerance at or BELOW the default is a tightening: it makes the bar stricter, so
    it owes no explanation. `enabled: true` with no tolerance is the default written
    out longhand and is not a departure either. Nor is `placement: "strict"` (G39) —
    that too only tightens, and it is validated for spelling here rather than left to
    fall back silently to the loose value.

    The reason must be non-empty after stripping. It is not otherwise policed here —
    "must name the kernel idiom that differs" is a review standard (`y4d-spec rules`),
    and a rule that tried to grade prose would be a rule that could be satisfied by
    padding.
    """
    from .parity import (
        PARITY_CHECK_KEY,
        PARITY_OVERRIDE_KEY,
        PARITY_TOLERANCE,
        PLACEMENT_MODES,
    )

    problems: list[str] = []
    verification = doc.get("verification")
    if not isinstance(verification, dict):
        return problems

    def _judge(block: object, where: str) -> None:
        if not isinstance(block, dict):
            problems.append(f"{where}: must be an object")
            return
        enabled = block.get("enabled")
        tolerance = block.get("tolerance")
        reason = block.get("reason")

        if enabled is not None and not isinstance(enabled, bool):
            problems.append(f"{where}.enabled: must be a boolean")
        if tolerance is not None and (
            isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
        ):
            problems.append(f"{where}.tolerance: must be a number (mm)")
            tolerance = None
        elif isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool):
            if tolerance <= 0:
                problems.append(f"{where}.tolerance: must be > 0")
        if reason is not None and not isinstance(reason, str):
            problems.append(f"{where}.reason: must be a string")
            reason = None
        placement = block.get("placement")
        if placement is not None and placement not in PLACEMENT_MODES:
            problems.append(
                f"{where}.placement: must be one of {', '.join(PLACEMENT_MODES)} "
                "— an unrecognised value would silently fall back to the loose one"
            )

        has_reason = isinstance(reason, str) and reason.strip() != ""
        widened = (
            isinstance(tolerance, (int, float))
            and not isinstance(tolerance, bool)
            and tolerance > PARITY_TOLERANCE
        )

        if enabled is False and not has_reason:
            problems.append(
                f"{where}: parity is disabled without a `reason` — an exemption from "
                "the cross-kernel comparison is visible debt and must name the kernel "
                "idiom that differs, so that it can be reviewed when either kernel "
                "changes (G38)"
            )
        elif widened and not has_reason:
            problems.append(
                f"{where}: parity tolerance is widened to {tolerance}mm (default "
                f"{PARITY_TOLERANCE}mm) without a `reason` — a pair judged at a wider "
                "bar than every other pair must say why (G38)"
            )

    stages = verification.get("stages")
    if isinstance(stages, dict):
        geometry = stages.get("geometry")
        if isinstance(geometry, dict):
            checks = geometry.get("checks")
            if isinstance(checks, dict) and PARITY_CHECK_KEY in checks:
                _judge(
                    checks[PARITY_CHECK_KEY],
                    f"verification.stages.geometry.checks.{PARITY_CHECK_KEY}",
                )

    mode_overrides = verification.get("mode_overrides")
    if isinstance(mode_overrides, dict):
        for mode_id in sorted(mode_overrides):
            entry = mode_overrides[mode_id]
            if not isinstance(entry, dict):
                continue
            part_overrides = entry.get("part_overrides")
            if not isinstance(part_overrides, dict):
                continue
            for part_id in sorted(part_overrides):
                block = part_overrides[part_id]
                if not isinstance(block, dict) or PARITY_OVERRIDE_KEY not in block:
                    continue
                _judge(
                    block[PARITY_OVERRIDE_KEY],
                    f'verification.mode_overrides.{mode_id}.part_overrides.'
                    f'{part_id}["{PARITY_OVERRIDE_KEY}"]',
                )

    return problems


def all_manifest_rules(doc: dict) -> list[str]:
    """Every per-cartridge manifest rule, in one call. Schema validation is separate
    (conformance.py); nothing short-circuits, so a caller sees all problems at once."""
    problems: list[str] = []
    problems.extend(manifest_structural_rules(doc))
    problems.extend(dispatch_rules(doc))
    problems.extend(hyperobject_rules(doc))
    problems.extend(i18n_rules(doc))
    problems.extend(license_rules(doc))
    problems.extend(verification_rules(doc))
    return problems


# ── the render surface ───────────────────────────────────────────────────────
def render_targets(doc: dict) -> list[tuple[str, str]]:
    """Every (mode_id, part_id) pair a conformant cartridge must be able to render.

    This is the geometry lane's work list: the platform renders one part at a time,
    dispatched by `target_part`, so a mode listing three parts is three renders.
    """
    targets: list[tuple[str, str]] = []
    for mode in doc.get("modes") or []:
        if not isinstance(mode, dict):
            continue
        mid = mode.get("id")
        if not isinstance(mid, str):
            continue
        for pid in mode.get("parts") or []:
            if isinstance(pid, str):
                targets.append((mid, pid))
    return targets


def preset_targets(doc: dict) -> list[tuple[str, str, str, dict]]:
    """Every (preset_id, mode_id, part_id, values) a preset render must cover.

    A preset is the parameter point a user actually CLICKS, and the default-params
    render says nothing about it: a shipped preset of extrusion-hyperobject crashed
    the CAD kernel at degradation_state=5 while the defaults render stayed green.
    This is the work list that closes that gap — the same bar, evaluated where users
    land.

    A preset usually names one mode (`presets[].mode`); that mode's declared parts each
    get a render, since the platform renders one part at a time via `target_part`.

    The schema does NOT require `mode`, and 164 of the commons' 1219 presets omit it —
    including every preset of extrusion-hyperobject, the cartridge whose shipped preset
    proved this bug class. Skipping unscoped presets would therefore skip exactly the
    case this exists for. They are instead scoped from the manifest rather than
    guessed: a preset applies to the modes in which ALL of its parameters are visible
    (`parameters[].modes` / `parameters[].visible_in_modes` — the same fields
    dispatch_rules already cross-checks). That is the UI's own answer to "where can a
    user set these values", so it renders combinations the UI can actually produce
    instead of inventing them. A value whose parameter declares no scope is visible
    everywhere and constrains nothing; when the intersection is empty, the preset is
    skipped rather than forced somewhere it does not belong.
    """
    modes = {
        m["id"]: m
        for m in doc.get("modes") or []
        if isinstance(m, dict) and isinstance(m.get("id"), str)
    }
    scopes = _parameter_mode_scopes(doc)

    targets: list[tuple[str, str, str, dict]] = []
    for i, preset in enumerate(doc.get("presets") or []):
        if not isinstance(preset, dict):
            continue
        values = preset.get("values")
        if not isinstance(values, dict):
            continue

        declared = preset.get("mode")
        if isinstance(declared, str):
            mode_ids = [declared] if declared in modes else []
        else:
            mode_ids = _implied_modes(values, scopes, list(modes))

        pid_label = str(preset.get("id") or preset.get("slug") or f"presets[{i}]")
        for mode_id in mode_ids:
            for part_id in modes[mode_id].get("parts") or []:
                if isinstance(part_id, str):
                    targets.append((pid_label, mode_id, part_id, dict(values)))
    return targets


def _parameter_mode_scopes(doc: dict) -> dict:
    """`{parameter id: set of mode ids it is visible in}`, omitting unscoped params.

    Both spellings count: `modes` is the schema's field and `visible_in_modes` is what
    several cartridges (extrusion-hyperobject among them) actually ship. dispatch_rules
    already validates both against the declared mode ids.
    """
    scopes: dict = {}
    for p in doc.get("parameters") or []:
        if not isinstance(p, dict) or not isinstance(p.get("id"), str):
            continue
        for key in ("modes", "visible_in_modes"):
            scope = p.get(key)
            if isinstance(scope, list) and scope:
                ids = {m for m in scope if isinstance(m, str)}
                if ids:
                    scopes[p["id"]] = scopes.get(p["id"], ids) & ids
    return scopes


def _implied_modes(values: dict, scopes: dict, all_modes: list) -> list:
    """The modes an unscoped preset can apply to: where every value is visible."""
    allowed = set(all_modes)
    for key in values:
        scope = scopes.get(key)
        if scope is not None:
            allowed &= scope
    return [m for m in all_modes if m in allowed]


def parameter_defaults(doc: dict) -> dict:
    """`{parameter id: default}` for every parameter that declares a default.

    Used to tell a preset that RESTATES the defaults apart from one that fails to
    apply: only the second is worth a note.
    """
    defaults: dict = {}
    for p in doc.get("parameters") or []:
        if not isinstance(p, dict) or not isinstance(p.get("id"), str):
            continue
        if "default" in p:
            defaults[p["id"]] = p["default"]
    return defaults


def preset_changes_anything(values: dict, defaults: dict) -> bool:
    """True when a preset's values differ from the manifest defaults on some key.

    A preset whose every value equals the declared default is a legitimate shape —
    thimble ships one called 'default' that restates finger_girth=56.0, and several
    cartridges use one as the UI's reset button. Such a preset SHOULD render
    identically to the defaults, so identical geometry there is correct behaviour and
    must not be noted. A preset whose values genuinely differ and still renders
    identical geometry is the real signal: the parameter never reached the script.

    A key the manifest declares no default for counts as a difference — the script
    supplies that default via the PARAM idiom, and this function cannot see it, so it
    errs toward asking the geometry rather than staying silent.
    """
    for key, value in values.items():
        if key not in defaults:
            return True
        if defaults[key] != value:
            return True
    return False
