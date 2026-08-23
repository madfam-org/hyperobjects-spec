"""The bridge handshake: resolve, render at mapped values, prove responsiveness.

Three steps per link, each strictly stronger than the last:

  1. RESOLVE (pure python, always runs)
     Delegated wholesale to `fc_spec.rules.hardware_ref_rules` — the same function
     `fc-spec check garment-manifest --resolve` calls. Then each value expression is
     EVALUATED against the garment's parameter defaults, which the structural rule
     does not do (it only parses to collect identifiers).

  2. RENDER AT MAPPED VALUES (needs [geometry])
     `y4d_spec.geometry.render_part` with `params = defaults | mapped`. The mesh bar
     is that function's house bar — watertight, volume > 0, no inverted body. A link
     whose values the solid cannot build at fails here.

  3. RESPONSIVENESS (needs [geometry])
     Re-render with one mapped parameter at +10% and compare volume. A key that
     changes nothing is dead wiring. Heavily guarded — see `_perturb_value`.

Cost: renders are seconds each, and a link has up to `MAX_PROBES + 1` of them. The
per-link cap is a real constraint, not a nicety; see MAX_PROBES.
"""

from __future__ import annotations

import ast
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from fc_spec.rules import SAFE_MAP_FUNCS, hardware_ref_rules

__all__ = [
    "BridgeLink",
    "LinkVerdict",
    "ParamProbe",
    "MAX_PROBES",
    "MAX_TARGETS",
    "VOLUME_EPSILON",
    "PERTURB_FRACTION",
    "check_bridge",
    "check_link",
    "discover_links",
    "load_y4d_index",
    "evaluate_params_map",
]

# ── tuning constants, each with the reason it is what it is ──────────────────

# Mapped parameters probed for responsiveness per link. A full duffel-bag link maps
# 2 params; the widest links in the commons map 6. At ~15-25s per render, probing
# every one of a 6-param link costs over two minutes for that link alone, and a full
# 97-link sweep would run for hours. Three probes catch dead wiring in practice: a
# link with a dead key almost always has it among its first parameters, because the
# dead key is usually the one added last-but-declared-first when the mapping was
# written from the hardware's parameter order. Raise it with --max-probes when you
# are auditing one link rather than sweeping the commons.
MAX_PROBES = 3

# Volume delta below which two renders are "the same body". Deliberately tiny: this
# is not a tolerance on manufacturing, it is a floating-point equality guard. STL
# export is deterministic for identical input, so a genuinely responsive parameter
# moves the volume by orders of magnitude more than this. Anything at or under it is
# a parameter the script did not read (or read and clamped to a constant).
VOLUME_EPSILON = 1e-6

# Perturbation size. 10% is large enough that no tessellation or fillet-approximation
# noise can account for the delta, and small enough that it usually stays inside the
# parameter's declared range — which matters, because an out-of-range perturbation
# proves nothing (see _perturb_value).
PERTURB_FRACTION = 0.10

# A render problem list is truncated to this many entries in the reported message.
# Not cosmetic: `articulated-scale-mail → tpu-scale-mail` emits 200+ per-body problems
# for one render, and the calibration run's first output was a single unreadable
# 40,000-character line. The count is always stated, so nothing is hidden.
MAX_REPORTED_PROBLEMS = 3

# Distinct (mode, part) targets rendered per link. Ownership resolution can select
# SEVERAL modes when the mapped parameters are scoped to all of them, and the render
# count is targets × (2 + probes) — it multiplies fast. Measured across the real
# commons: 1080 renders for a full sweep, of which the eleven `zipper` links alone
# are ~250, because `zip_length` is scoped to both the `closed` and `separating`
# modes and those declare seven parts between them. At 15-25s a render that is over
# an hour for one hardware family.
#
# Capping the targets does not weaken the claim: the responsiveness comparison is a
# SUM over whatever was rendered, so a parameter that moves any rendered part is
# still proven live, and the parts are taken in manifest order — the order the
# cartridge author considered primary. What the cap does is bound the cost of a link
# so a sweep of the commons finishes. Raise it with --max-targets when auditing one
# link. Every capped link says so in its notes; nothing is silently dropped.
MAX_TARGETS = 4


# ── data ─────────────────────────────────────────────────────────────────────
@dataclass
class ParamProbe:
    """One responsiveness probe: a mapped parameter perturbed, and what happened."""

    param: str
    base_value: float | None = None
    probe_value: float | None = None
    base_volume: float | None = None
    probe_volume: float | None = None
    responsive: bool | None = None  # None = not concluded (skipped)
    skipped: str | None = None      # why, when skipped

    @property
    def delta(self) -> float | None:
        if self.base_volume is None or self.probe_volume is None:
            return None
        return abs(self.probe_volume - self.base_volume)


@dataclass
class BridgeLink:
    """One FC cartridge's declared hardware_ref, with everything needed to check it."""

    fc_dir: Path
    fc_slug: str
    target_slug: str
    params_map: dict[str, str]
    fc_manifest: dict
    y4d_dir: Path | None = None
    y4d_manifest: dict | None = None


@dataclass
class LinkVerdict:
    """The verdict on one link, plus the evidence."""

    fc_slug: str
    target_slug: str
    resolve_problems: list[str] = field(default_factory=list)
    render_problems: list[str] = field(default_factory=list)
    dead_params: list[str] = field(default_factory=list)
    # Mapped values already outside the target parameter's declared min/max. A REAL
    # finding (the cartridge clamps, and the garment gets a part of a size it did
    # not order) but it lands as a MEASUREMENT, not a failure — house doctrine: a new
    # rule is calibrated against the full commons and its false-positive analysis is
    # written down BEFORE it is allowed to block. Counted separately in the summary
    # and excluded from `ok` on purpose.
    range_problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    mapped_values: dict[str, float] = field(default_factory=dict)
    probes: list[ParamProbe] = field(default_factory=list)
    rendered: tuple[str, str] | None = None   # (mode, part) actually rendered
    geometry_skipped: str | None = None       # why steps 2-3 did not run

    @property
    def ok(self) -> bool:
        # NOTE: range_problems are deliberately NOT here. See `status`.
        return not (self.resolve_problems or self.render_problems or self.dead_params)

    @property
    def status(self) -> str:
        if self.resolve_problems:
            return "resolve_fail"
        if self.render_problems:
            return "render_fail"
        if self.dead_params:
            return "dead_params"
        if self.geometry_skipped:
            return "skipped"
        return "ok"

    @property
    def summary(self) -> str:
        head = f"{self.fc_slug} → {self.target_slug}"
        if self.resolve_problems:
            return f"FAIL {head}: {'; '.join(self.resolve_problems)}"
        if self.render_problems:
            return f"FAIL {head}: {'; '.join(self.render_problems)}"
        if self.dead_params:
            keys = ", ".join(self.dead_params)
            return (
                f"FAIL {head}: dead params_map key(s) [{keys}] — the mapped value "
                f"changes nothing in the rendered solid"
            )
        if self.geometry_skipped:
            return f"skip {head}: resolved; geometry {self.geometry_skipped}"
        vals = ", ".join(f"{k}={v:g}" for k, v in sorted(self.mapped_values.items()))
        probed = sum(1 for p in self.probes if p.responsive)
        where = f" at ({self.rendered[0]}, {self.rendered[1]})" if self.rendered else ""
        tail = f" [range: {len(self.range_problems)}]" if self.range_problems else ""
        return (
            f"ok   {head}{where} [{vals}] — {probed} param(s) proven responsive{tail}"
        )


# ── step 1: resolve ──────────────────────────────────────────────────────────
def _param_defaults(manifest: dict) -> dict[str, float]:
    """`{parameter id: default}` for every numeric-defaulted parameter of a manifest.

    Non-numeric defaults (a select's string, a toggle's bool) are kept as-is: an
    expression may legitimately reference a boolean parameter, and `True + 0` is 1.
    A parameter with no default at all is absent, which surfaces as a NameError the
    caller reports rather than a silent zero.
    """
    out: dict[str, float] = {}
    for p in manifest.get("parameters") or []:
        if isinstance(p, dict) and isinstance(p.get("id"), str) and "default" in p:
            out[p["id"]] = p["default"]
    return out


class _ExprError(ValueError):
    """A params_map value that cannot be evaluated against the garment defaults."""


def _eval_expr(expr: str, names: dict[str, float]):
    """Evaluate a params_map value expression against `names`.

    A restricted AST walk, NOT `eval`. The grammar accepted is exactly the grammar
    `fc_spec.rules._idents` parses — literals, names, the arithmetic operators, and
    a call to one of `fc_spec.rules.SAFE_MAP_FUNCS`. Anything else raises rather
    than evaluating, so this can never become an execution vector even though its
    input is a third party's manifest.

    `SAFE_MAP_FUNCS` is imported, never re-listed: if the spec widens the whitelist,
    this evaluator widens with it and cannot fall behind.
    """
    _FUNCS = {
        "round": round, "ceil": math.ceil, "floor": math.floor, "int": int,
        "min": min, "max": max, "abs": abs,
    }

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return node.value
            raise _ExprError(f"non-numeric literal {node.value!r}")
        if isinstance(node, ast.Name):
            if node.id not in names:
                raise _ExprError(f"references '{node.id}', which has no default value")
            val = names[node.id]
            if isinstance(val, bool):
                return int(val)
            if not isinstance(val, (int, float)):
                raise _ExprError(
                    f"references '{node.id}', whose default {val!r} is not numeric"
                )
            return val
        if isinstance(node, ast.BinOp):
            left, right = ev(node.left), ev(node.right)
            op = node.op
            if isinstance(op, ast.Add):
                return left + right
            if isinstance(op, ast.Sub):
                return left - right
            if isinstance(op, ast.Mult):
                return left * right
            if isinstance(op, ast.Div):
                if right == 0:
                    raise _ExprError("division by zero")
                return left / right
            if isinstance(op, ast.FloorDiv):
                if right == 0:
                    raise _ExprError("division by zero")
                return left // right
            if isinstance(op, ast.Mod):
                if right == 0:
                    raise _ExprError("modulo by zero")
                return left % right
            if isinstance(op, ast.Pow):
                return left**right
            raise _ExprError(f"unsupported operator {type(op).__name__}")
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return -ev(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +ev(node.operand)
            raise _ExprError(f"unsupported unary operator {type(node.op).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_MAP_FUNCS:
                name = getattr(node.func, "id", "<expr>")
                raise _ExprError(f"call to '{name}' is not one of the safe map functions")
            if node.keywords:
                raise _ExprError("keyword arguments are not supported in a map expression")
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise _ExprError(f"unsupported expression node {type(node).__name__}")

    try:
        tree = ast.parse(str(expr), mode="eval")
    except SyntaxError as exc:
        raise _ExprError(f"not a valid expression: {exc}") from exc
    return ev(tree)


def evaluate_params_map(
    params_map: dict[str, str], fc_manifest: dict
) -> tuple[dict[str, float], list[str]]:
    """Evaluate every params_map value against the garment's parameter defaults.

    Returns `(values, problems)`. This is the half of step 1 the structural rule does
    not do: `hardware_ref_rules` proves every identifier NAMES a garment parameter,
    which is not the same as proving the expression produces a number. A parameter
    declared without a default, a select whose default is a string, a division by a
    parameter that defaults to zero — all resolve structurally and all fail here.
    """
    names = _param_defaults(fc_manifest)
    values: dict[str, float] = {}
    problems: list[str] = []
    for key, expr in (params_map or {}).items():
        try:
            values[key] = float(_eval_expr(expr, names))
        except _ExprError as exc:
            problems.append(f"params_map['{key}'] = {expr!r} does not evaluate: {exc}")
        except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
            problems.append(
                f"params_map['{key}'] = {expr!r} does not evaluate: "
                f"{type(exc).__name__}: {exc}"
            )
    return values, problems


# ── discovery ────────────────────────────────────────────────────────────────
def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_y4d_index(y4d_repo: Path) -> dict[str, tuple[Path, dict]]:
    """`{slug: (cartridge_dir, manifest)}` for every cartridge in a yantra4d checkout.

    The slug is `project.slug` when the manifest declares one, else the directory
    name — the same fallback `apps/api/manifest.py:discover_projects` uses, so a
    cartridge that resolves on the platform resolves here.
    """
    index: dict[str, tuple[Path, dict]] = {}
    projects = Path(y4d_repo) / "projects"
    if not projects.is_dir():
        return index
    for d in sorted(projects.iterdir()):
        mf = d / "project.json"
        if not (d.is_dir() and mf.is_file()):
            continue
        try:
            doc = _read_json(mf)
        except (OSError, json.JSONDecodeError):
            continue
        slug = ((doc.get("project") or {}).get("slug")) or doc.get("slug") or d.name
        index[str(slug)] = (d, doc)
    return index


def discover_links(
    fc_repo: Path, y4d_index: dict[str, tuple[Path, dict]], only: list[Path] | None = None
) -> list[BridgeLink]:
    """Every FC cartridge declaring a LINKED hardware_ref, resolved where possible.

    `only` restricts to specific cartridge directories. An FC cartridge whose
    hardware_ref exists but is `linked: false` is a declared intent, not a claim
    about a real target, and is not a link — the same exemption
    `fc_spec.rules.hardware_ref_rules` makes.
    """
    if only:
        dirs = [Path(p) for p in only]
    else:
        proj = Path(fc_repo) / "projects"
        dirs = sorted(d for d in proj.iterdir() if d.is_dir()) if proj.is_dir() else []

    links: list[BridgeLink] = []
    for d in dirs:
        mf = d / "project.json"
        if not mf.is_file():
            continue
        try:
            doc = _read_json(mf)
        except (OSError, json.JSONDecodeError):
            continue
        hw = (doc.get("notion") or {}).get("hardware_ref")
        if not isinstance(hw, dict) or not hw.get("linked"):
            continue
        slug = hw.get("project_slug") or ""
        entry = y4d_index.get(slug)
        links.append(
            BridgeLink(
                fc_dir=d,
                fc_slug=((doc.get("project") or {}).get("slug")) or d.name,
                target_slug=slug,
                params_map=dict(hw.get("params_map") or {}),
                fc_manifest=doc,
                y4d_dir=entry[0] if entry else None,
                y4d_manifest=entry[1] if entry else None,
            )
        )
    return links


# ── step 2: pick what to render ──────────────────────────────────────────────
_SCRIPT_SUFFIXES = {".py", ".cq"}


def _owning_targets(y4d_manifest: dict, mapped_keys: set[str]) -> tuple[list[tuple[str, str]], str]:
    """The (mode, part) targets to render for a set of mapped parameters.

    A y4d parameter declares `modes` — the modes it is visible in. The modes that own
    ALL the mapped parameters are the ones the garment is actually driving, so those
    are what we render.

    Ownership is ambiguous in two directions, and both fall back to the FIRST CadQuery
    mode's parts rather than guessing:

      * a parameter declaring no `modes` is global (visible everywhere) — which tells
        us nothing about which mode to pick;
      * mapped parameters spanning disjoint mode sets means the garment drives several
        variants and there is no single right answer.

    Rendering the first CadQuery mode is not a cop-out: the platform's own default
    when a user opens a cartridge is its first mode, so a link that works at the
    first mode is a link that works at what a user sees. Returns
    `(targets, ownership_note)`.
    """
    modes = [m for m in y4d_manifest.get("modes") or [] if isinstance(m, dict)]
    cq_modes = [
        m for m in modes
        if isinstance(m.get("cq_file"), str) and Path(m["cq_file"]).suffix in _SCRIPT_SUFFIXES
    ]
    if not cq_modes:
        return [], "no CadQuery mode"

    scopes: list[set[str]] = []
    unscoped: list[str] = []
    for p in y4d_manifest.get("parameters") or []:
        if not isinstance(p, dict) or p.get("id") not in mapped_keys:
            continue
        scope = p.get("modes")
        if isinstance(scope, list) and scope:
            scopes.append({s for s in scope if isinstance(s, str)})
        else:
            unscoped.append(p.get("id"))

    note = ""
    owning: set[str] = set()
    if scopes:
        owning = set.intersection(*scopes)
    if unscoped and not owning:
        note = (
            f"mapped parameter(s) {sorted(unscoped)} declare no mode scope (global) — "
            f"rendering the first CadQuery mode"
        )
    elif scopes and not owning:
        note = (
            "mapped parameters span disjoint mode scopes — rendering the first "
            "CadQuery mode"
        )

    chosen = [m for m in cq_modes if m.get("id") in owning] if owning else []
    if not chosen:
        chosen = [cq_modes[0]]
        if not note:
            note = "no mode owns the mapped parameters — rendering the first CadQuery mode"

    targets: list[tuple[str, str]] = []
    for m in chosen:
        for part in m.get("parts") or []:
            if isinstance(part, str):
                targets.append((str(m.get("id")), part))
    if not targets:
        return [], "chosen mode declares no parts"
    return targets, note


def _cap_targets(targets: list[tuple[str, str]], limit: int) -> tuple[list, str | None]:
    """Bound a link's render budget. See MAX_TARGETS."""
    if limit <= 0 or len(targets) <= limit:
        return targets, None
    kept = targets[:limit]
    dropped = ", ".join(f"({m}, {p})" for m, p in targets[limit:])
    return kept, (
        f"render budget: {len(targets)} targets owned the mapped parameters, "
        f"rendering the first {limit} in manifest order; not rendered: {dropped} "
        f"(raise with --max-targets)"
    )


def _y4d_defaults(y4d_manifest: dict) -> dict:
    """The y4d cartridge's own parameter defaults — the base the mapping merges over.

    Rendering with ONLY the mapped values would be wrong: the un-mapped parameters
    would arrive absent, the cartridge's PARAM() idiom would fall back to the
    literal defaults baked in its source, and any drift between manifest and source
    would silently change what we measured. Merging over the manifest defaults renders
    what the platform renders.
    """
    out: dict = {}
    for p in y4d_manifest.get("parameters") or []:
        if isinstance(p, dict) and isinstance(p.get("id"), str) and "default" in p:
            out[p["id"]] = p["default"]
    return out


# ── step 3: responsiveness ───────────────────────────────────────────────────
def _brief(problems: list[str]) -> str:
    """Join a render's problems, truncated. See MAX_REPORTED_PROBLEMS."""
    if len(problems) <= MAX_REPORTED_PROBLEMS:
        return "; ".join(problems)
    head = "; ".join(problems[:MAX_REPORTED_PROBLEMS])
    return f"{head}; (+{len(problems) - MAX_REPORTED_PROBLEMS} more of the same kind)"


def _param_meta(y4d_manifest: dict, pid: str) -> dict:
    for p in y4d_manifest.get("parameters") or []:
        if isinstance(p, dict) and p.get("id") == pid:
            return p
    return {}


def _is_integral(meta: dict) -> bool:
    """Does this y4d parameter take whole numbers only?

    Declared `type: "integer"`/`"int"`, or an integral `step` with an integral
    default — the manifest idiom the commons actually uses (lacing-hook's
    `hook_count` is `type: "slider"`, `step: 1`, `default: 4`, and its script does
    `int(PARAM(...))`).
    """
    if meta.get("type") in ("integer", "int"):
        return True
    step = meta.get("step")
    default = meta.get("default")
    return (
        isinstance(step, int)
        and not isinstance(step, bool)
        and step >= 1
        and isinstance(default, int)
        and not isinstance(default, bool)
    )


def _out_of_range(meta: dict, value: float) -> str | None:
    """Is the MAPPED value already outside the target parameter's declared range?

    Not a perturbation concern — a finding in its own right. The garment is asking
    the hardware for a value its own manifest says it does not accept, so the
    cartridge clamps and returns a part of a different size than the garment
    believes it ordered. Silent, and exactly the failure class this tool exists for.
    Calibration found it in the wild (ankle-gaiter maps `pitch` = 26 to a parameter
    declared max 25), where the naive responsiveness rule misreported it as a dead
    key — a real problem given the wrong name, which is its own kind of false
    positive.
    """
    lo, hi = meta.get("min"), meta.get("max")
    lo = float(lo) if isinstance(lo, (int, float)) and not isinstance(lo, bool) else None
    hi = float(hi) if isinstance(hi, (int, float)) and not isinstance(hi, bool) else None
    if hi is not None and value > hi + VOLUME_EPSILON:
        return f"maps {value:g}, above the target parameter's declared max {hi:g}"
    if lo is not None and value < lo - VOLUME_EPSILON:
        return f"maps {value:g}, below the target parameter's declared min {lo:g}"
    return None


def _perturb_value(meta: dict, value: float) -> tuple[float | None, str | None]:
    """The +10% probe value for a mapped parameter, or `(None, reason)` to skip.

    This guard is why the responsiveness rule can be trusted, and every clause of it
    exists because the naive version produced a false failure on the real commons:

      * NON-NUMERIC parameter (a select's string, a toggle's bool): "+10%" is
        meaningless. Skip.
      * PERTURBATION OUTSIDE THE DECLARED RANGE: the cartridge will clamp it back,
        the volume will not move, and the parameter will look dead when it is not.
        This is a false positive produced by the CHECK, not a finding. So the probe
        is clamped into [min, max] first.
      * VALUE ALREADY AT MAX: clamping +10% back to max leaves the value unchanged
        — no signal. Perturb -10% instead, which is inside the range by construction.
      * INTEGRAL PARAMETER: +10% of 5 is 5.5, and the cartridge's `int(...)`
        truncates it straight back to 5 — a guaranteed false "dead" on every count
        parameter in the commons. Calibration caught this on lacing-hook's
        `hook_count`. An integral parameter moves by at least one whole step.
      * NO ROOM IN EITHER DIRECTION (min == max, a range narrower than one step,
        or a range narrower than the float epsilon): nothing proves anything. Note
        and skip.

    A skipped probe is never a failure. It is recorded so the run says out loud how
    much of the link it actually proved.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None, "mapped value is not numeric"

    lo = meta.get("min")
    hi = meta.get("max")
    lo = float(lo) if isinstance(lo, (int, float)) and not isinstance(lo, bool) else None
    hi = float(hi) if isinstance(hi, (int, float)) and not isinstance(hi, bool) else None

    ptype = meta.get("type")
    if ptype in ("select", "toggle", "boolean", "text", "color"):
        return None, f"parameter type '{ptype}' is not continuously perturbable"

    integral = _is_integral(meta)
    step = meta.get("step")
    step = float(step) if isinstance(step, (int, float)) and step else 1.0

    def _quantize(cand: float, away_from: float) -> float:
        """Round an integral probe AWAY from the base value, so a sub-step
        perturbation still lands a whole step out instead of truncating back."""
        if not integral:
            return cand
        return math.ceil(cand) if cand > away_from else math.floor(cand)

    if value == 0:
        # A zero value has no multiplicative neighbourhood; step by the declared
        # step, or by 1mm — the commons is in millimetres.
        up = step
    else:
        up = value * (1.0 + PERTURB_FRACTION)
        if integral and abs(up - value) < step:
            up = value + step

    cand = _quantize(up, value)
    if hi is not None:
        cand = min(cand, hi)
    if lo is not None:
        cand = max(cand, lo)
    if integral:
        cand = float(math.floor(cand)) if cand < value else float(math.ceil(cand))
        if hi is not None and cand > hi:
            cand = float(math.floor(hi))
    if abs(cand - value) > VOLUME_EPSILON:
        return cand, None

    if value == 0:
        down = -step
    else:
        down = value * (1.0 - PERTURB_FRACTION)
        if integral and abs(value - down) < step:
            down = value - step

    cand = _quantize(down, value)
    if hi is not None:
        cand = min(cand, hi)
    if lo is not None:
        cand = max(cand, lo)
    if integral:
        cand = float(math.ceil(cand)) if cand > value else float(math.floor(cand))
        if lo is not None and cand < lo:
            cand = float(math.ceil(lo))
    if abs(cand - value) > VOLUME_EPSILON:
        return cand, None

    rng = f"[{lo}, {hi}]" if (lo is not None or hi is not None) else "unbounded"
    unit = f" (integral, step {step:g})" if integral else ""
    return None, (
        f"no perturbation moves the value: {value:g} with declared range {rng}"
        f"{unit} (±{int(PERTURB_FRACTION * 100)}% clamps back to itself)"
    )


# ── the check ────────────────────────────────────────────────────────────────
def check_link(
    link: BridgeLink,
    y4d_index: dict[str, tuple[Path, dict]],
    *,
    render: bool = True,
    max_probes: int = MAX_PROBES,
    max_targets: int = MAX_TARGETS,
) -> LinkVerdict:
    """Run the three-step handshake on one link."""
    v = LinkVerdict(fc_slug=link.fc_slug, target_slug=link.target_slug)

    # ── step 1a: structural resolution — delegated, never reimplemented.
    resolve_surface = {slug: _param_ids(doc) for slug, (_d, doc) in y4d_index.items()}
    v.resolve_problems.extend(hardware_ref_rules(link.fc_manifest, resolve_surface))
    if v.resolve_problems:
        return v

    # ── step 1b: the mapped values must actually be numbers.
    values, expr_problems = evaluate_params_map(link.params_map, link.fc_manifest)
    v.resolve_problems.extend(expr_problems)
    v.mapped_values = values
    if v.resolve_problems:
        return v

    y4d_manifest = link.y4d_manifest
    y4d_dir = link.y4d_dir
    if y4d_manifest is None or y4d_dir is None:
        # hardware_ref_rules already reports an unresolvable slug; reaching here means
        # the resolve surface knew the slug but discovery did not — a repo the caller
        # supplied inconsistently.
        v.resolve_problems.append(
            f"target '{link.target_slug}' resolved by name but has no cartridge "
            f"directory in the supplied yantra4d checkout"
        )
        return v

    if not render:
        v.geometry_skipped = "not requested (--no-render)"
        return v

    # ── OpenSCAD-only targets: structural resolution is all we can honestly claim.
    targets, note = _owning_targets(y4d_manifest, set(link.params_map))
    if not targets:
        v.geometry_skipped = (
            f"skipped ({note}) — the OpenSCAD kernel is the platform's job; "
            f"only structural resolution was verified"
        )
        return v
    if note:
        v.notes.append(note)
    targets, budget_note = _cap_targets(targets, max_targets)
    if budget_note:
        v.notes.append(budget_note)

    from y4d_spec.geometry import render_part  # local: only step 2+ needs [geometry]

    # Each target carries its own source file: when the mapped parameters are owned
    # by several modes, those modes may name DIFFERENT cq_files, and rendering them
    # all through the first mode's script would silently measure the wrong cartridge
    # half. Resolved per target, not once.
    script_of = {
        m.get("id"): m.get("cq_file")
        for m in y4d_manifest.get("modes") or []
        if isinstance(m, dict)
    }

    defaults = _y4d_defaults(y4d_manifest)
    base_params = dict(defaults)
    base_params.update(values)
    mapped_desc = ", ".join(f"{k}={x:g}" for k, x in sorted(values.items()))

    # ── step 2a: BASELINE — render at the y4d cartridge's OWN defaults first.
    #
    # This is the single most important false-positive control in the tool, and it
    # was added because the first calibration run produced two failures that were not
    # findings about the bridge at all. `magnetic-clasp` and `tpu-scale-mail` both
    # fail `y4d-spec check --render` at their own defaults — pre-existing cartridge
    # defects in yantra4d, with no garment involved. Reporting them as broken LINKS
    # would blame the FC side for a solid that was already broken, and would bury the
    # real findings under noise the FC maintainer cannot act on.
    #
    # So: a render problem is a BRIDGE finding only when the cartridge is healthy at
    # its defaults and unhealthy at the mapped values. That difference is caused by
    # the mapping, which is the only thing this tool is entitled to judge. A target
    # already broken at defaults is recorded as skipped-with-a-note and belongs to
    # `y4d-spec check --render`, which is where it will be found and fixed.
    baseline_ok: dict[tuple[str, str], bool] = {}
    for m_id, part in targets:
        check = render_part(y4d_dir, script_of[m_id], m_id, part, params=dict(defaults))
        baseline_ok[(m_id, part)] = check.ok

    if not any(baseline_ok.values()):
        v.geometry_skipped = (
            f"skipped — the yantra4d cartridge '{link.target_slug}' does not render "
            f"cleanly at its OWN defaults, so nothing here can be attributed to the "
            f"mapping; run `y4d-spec check {link.target_slug} --render`"
        )
        return v

    # ── step 2b: render at the mapped values.
    base_volumes: dict[tuple[str, str], float] = {}
    for m_id, part in targets:
        if not baseline_ok[(m_id, part)]:
            v.notes.append(
                f"({m_id}, {part}) already fails at the cartridge's own defaults — "
                f"excluded from the handshake (a y4d-spec finding, not a bridge one)"
            )
            continue
        check = render_part(y4d_dir, script_of[m_id], m_id, part, params=dict(base_params))
        if not check.ok:
            v.render_problems.append(
                f"({m_id}, {part}) renders clean at the cartridge's defaults but FAILS "
                f"at the mapped values [{mapped_desc}]: {_brief(check.problems)}"
            )
        elif check.volume is not None:
            base_volumes[(m_id, part)] = float(check.volume)
    if v.render_problems:
        return v
    if not base_volumes:
        v.geometry_skipped = "skipped — no baseline-healthy target produced a volume"
        return v

    # Report a target that was ACTUALLY measured. targets[0] may have been excluded
    # for failing at the cartridge's own defaults, and naming it would credit the
    # verdict to a render that never happened.
    v.rendered = next(iter(base_volumes))

    # ── step 3: responsiveness, one mapped parameter at a time.
    #
    # The probe compares the SUM of volumes across the rendered targets, not one
    # part's. A mapped parameter may legitimately drive only one part of a multi-part
    # mode (a strap-ring's bar thickness moves the ring, not the tab), and judging it
    # against a single part would report it dead. Summing means any part moving counts
    # as the parameter being live, which is exactly the claim being made.
    base_total = sum(base_volumes.values())

    for key in sorted(link.params_map)[:max_probes]:
        if key not in values:
            continue
        meta = _param_meta(y4d_manifest, key)

        # OUT-OF-RANGE MAPPING — a MEASUREMENT, not a failure (see the class doc on
        # `range_problems` and docs/BRIDGE_HANDSHAKE.md). Recorded, reported, and
        # deliberately non-blocking until it has been calibrated against the whole
        # commons and its false-positive analysis is written down. It also ends this
        # parameter's responsiveness probe: the cartridge is clamping the value, so
        # nothing a perturbation does can prove anything about the wiring.
        oor = _out_of_range(meta, values[key])
        if oor is not None:
            v.range_problems.append(f"params_map['{key}'] {oor}")
            v.probes.append(
                ParamProbe(
                    param=key, base_value=values[key],
                    skipped=f"{oor} — the cartridge clamps it, so responsiveness "
                            f"is unprovable here",
                )
            )
            v.notes.append(f"RANGE params_map['{key}'] {oor}")
            continue

        probe_value, skip = _perturb_value(meta, values[key])
        if probe_value is None:
            v.probes.append(ParamProbe(param=key, base_value=values[key], skipped=skip))
            v.notes.append(f"probe '{key}' skipped: {skip}")
            continue

        probe_params = dict(base_params)
        probe_params[key] = probe_value
        total = 0.0
        failed = None
        for m_id, part in base_volumes:
            check = render_part(y4d_dir, script_of[m_id], m_id, part, params=dict(probe_params))
            if not check.ok or check.volume is None:
                failed = f"({m_id}, {part}): {_brief(check.problems) or 'no volume'}"
                break
            total += float(check.volume)

        if failed is not None:
            # A render that succeeds at the mapped value and FAILS 10% away is a real
            # finding, not a probe artefact: the link sits on the edge of what the
            # solid can build, and any real-world tolerance walks it off the cliff.
            v.render_problems.append(
                f"perturbing '{key}' {values[key]:g} → {probe_value:g} (inside the "
                f"declared range) breaks the render — {failed}"
            )
            v.probes.append(
                ParamProbe(
                    param=key, base_value=values[key], probe_value=probe_value,
                    base_volume=base_total, responsive=None,
                    skipped="render failed at the perturbed value",
                )
            )
            continue

        responsive = abs(total - base_total) > VOLUME_EPSILON
        v.probes.append(
            ParamProbe(
                param=key, base_value=values[key], probe_value=probe_value,
                base_volume=base_total, probe_volume=total, responsive=responsive,
            )
        )
        if not responsive:
            v.dead_params.append(key)

    return v


def _param_ids(y4d_manifest: dict) -> list[str]:
    return [
        p["id"] for p in y4d_manifest.get("parameters") or []
        if isinstance(p, dict) and isinstance(p.get("id"), str)
    ]


def check_bridge(
    fc_repo: Path,
    y4d_repo: Path,
    *,
    only: list[Path] | None = None,
    render: bool = True,
    max_probes: int = MAX_PROBES,
    max_targets: int = MAX_TARGETS,
    on_verdict=None,
) -> list[LinkVerdict]:
    """Check every bridged FC cartridge against a yantra4d checkout.

    `on_verdict(verdict)` is called as each link finishes. A full sweep of the
    commons is minutes of renders per handful of links; collecting silently and
    printing at the end makes a long run indistinguishable from a hung one, and an
    operator who ctrl-Cs at minute forty loses every finding. Streaming is not a
    nicety here.
    """
    index = load_y4d_index(Path(y4d_repo))
    links = discover_links(Path(fc_repo), index, only=only)
    verdicts: list[LinkVerdict] = []
    for link in links:
        v = check_link(
            link, index, render=render, max_probes=max_probes, max_targets=max_targets
        )
        verdicts.append(v)
        if on_verdict is not None:
            on_verdict(v)
    return verdicts
