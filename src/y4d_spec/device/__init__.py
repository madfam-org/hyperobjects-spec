"""The device-control vocabulary (device-controls 1.0): its rules for a solid cartridge.

A cartridge that models a device a person operates (a handheld, a remote, a panel) can
say, in a ``device`` block of its manifest, which of its parts is a control and what it
sends. Contract: ``docs/DEVICE_CONTROLS.md``. Shape: ``device-controls.schema.json``
(``hyperobjects_schemas``). The input names are Linux input event names, checked against
``input-codes.json`` beside this file (generated from the kernel's user-space header by
``scripts/refresh_device_input_codes.py``, which records the tag and the header's sha256).

Three passes, and each checks the declaration against something the cartridge actually
has, so a declaration cannot describe a device the cartridge does not build:

* :func:`manifest_rules` — no directory, no render. The shape; every declared part
  (control or structure) is a part of the cartridge that some mode renders, and every
  part is accounted for; every input name exists and suits its role; a label carries
  both locales; every expression parses in the graph core's dialect and reads declared
  parameters; and at each parameter point a run renders (a mode at its defaults, and
  each preset in its modes) a part the mode lists is present there and a control's
  numbers are sound.
* :func:`graph_rules` — needs the directory. RFC 0067 gives every hyperobject a graph,
  and a control is one of its outputs: a mode that lists a control names a graph, the
  graph outputs that part, and a format 1.2 graph declares every parameter the
  declaration reads.
* :func:`render_checks` — after ``--render``. One verdict per (control, rendered point)
  against the mesh the cartridge produced, judged against the control's **host**: the
  structure part rendered at the same point that the control touches. The control sits
  on the host's surface (neither away from it nor buried in it), a press moves it into
  the host from the face it sits on, and a screen's lit face is the part's large face
  and looks away from the host. With no host rendered at the point, the control is
  unverified.

Every rule is a failure from birth, as the sheet commons' and the 1.2 graph's were
(AGENTS.md): no cartridge carried a ``device`` block before this module, so there is no
healthy cartridge for a rule to misfire on. The observations that could be right on a
healthy device (two controls sending one code, non-square pixels, a press deeper than the
cap is tall, a control in several bodies) are notes.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path

import hyperobject_graph as core
from hyperobjects_schemas import load as load_schema

__all__ = [
    "DeviceCheck",
    "KNOWN_MINOR",
    "ROLES",
    "RULE_ID",
    "SCHEMA",
    "VOCABULARY",
    "graph_rules",
    "input_codes",
    "manifest_rules",
    "render_checks",
    "resolve",
]

RULE_ID = "device-controls"
VOCABULARY = "device-controls"
#: The highest 1.x minor this module knows. A declaration written in a later minor is
#: checked as far as this one goes, and says so in a note.
KNOWN_MINOR = 0
SCHEMA = "device-controls"
ROLES = ("button", "stick", "trigger", "switch", "screen", "light", "port", "motor")
GRAPH_FILE_SUFFIX = ".graph.json"

#: Conventions of the render pass (labelled, as every tolerance in this package is).
#: How near a control's bounding box must come to the surface of its host's, from
#: outside or from inside. Further outside than this from every structure part's box is
#: detached; further inside its host's box than this on every side is buried; a press
#: or a lit face must reach the host's face on its side to within this. Wide enough for
#: a part that only touches its seat and for a port mouth set back into an edge.
DETACHED_MM = 1.0
#: Pixels are called non-square when the two pitches differ by more than this fraction.
PIXEL_ASPECT_BAND = 0.02

_AXES = {"x": 0, "y": 1, "z": 2}


@cache
def input_codes() -> dict:
    """The input-code table: ``{"source", "event_types", "codes": {type: {name: n}}}``."""
    text = resources.files(__name__).joinpath("input-codes.json").read_text(encoding="utf-8")
    return json.loads(text)


def _code_type(name: str) -> str | None:
    """The event type that defines ``name``, or None when no type does."""
    for ev, names in input_codes()["codes"].items():
        if name in names:
            return ev
    return None


def _axis(spec: object) -> tuple[int, int] | None:
    """``"+z"`` → ``(2, +1)``; None for anything that is not one of the six directions
    (the schema has already refused it; no pass may crash on it)."""
    if not isinstance(spec, str) or len(spec) != 2 or spec[0] not in "+-" or spec[1] not in _AXES:
        return None
    return _AXES[spec[1]], (1 if spec[0] == "+" else -1)


# ── reading the manifest defensively ─────────────────────────────────────────────────


def _block(doc: dict) -> dict | None:
    block = doc.get("device") if isinstance(doc, dict) else None
    return block if isinstance(block, dict) else None


def _controls(block: dict) -> list[dict]:
    controls = block.get("controls")
    if not isinstance(controls, list):
        return []
    return [c for c in controls if isinstance(c, dict) and isinstance(c.get("part"), str)]


def _structure_entries(block: dict) -> list[dict]:
    """Every structure entry as ``{"part": id, ...}``: a bare id, or an object that can
    carry ``present_when``."""
    structure = block.get("structure")
    entries: list[dict] = []
    for item in structure if isinstance(structure, list) else []:
        if isinstance(item, str):
            entries.append({"part": item})
        elif isinstance(item, dict) and isinstance(item.get("part"), str):
            entries.append(item)
    return entries


def _structure(block: dict) -> list[str]:
    return [entry["part"] for entry in _structure_entries(block)]


def _modes(doc: dict) -> list[dict]:
    return [
        m for m in doc.get("modes") or []
        if isinstance(m, dict) and isinstance(m.get("id"), str)
    ]


def _mode_parts(mode: dict) -> list[str]:
    return [p for p in mode.get("parts") or [] if isinstance(p, str)]


def _scope(doc: dict) -> dict[str, float | bool]:
    """Parameter id → default, for the parameters an expression can read.

    The dialect has numbers and booleans and nothing else, so a select or a text
    parameter is not in scope. Numbers become floats: the dialect's ``==`` is strict, and
    a slider declared ``2`` must equal a preset's ``2.0``.
    """
    scope: dict[str, float | bool] = {}
    for p in doc.get("parameters") or []:
        if not isinstance(p, dict) or not isinstance(p.get("id"), str):
            continue
        value = _value(p.get("default"))
        if value is not None:
            scope[p["id"]] = value
    return scope


def _value(raw: object) -> float | bool | None:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int | float) and math.isfinite(raw):
        return float(raw)
    return None


def _points(doc: dict) -> list[tuple[str, str | None, dict]]:
    """Every ``(mode id, preset id or None, values)`` a render run visits."""
    from ..rules import preset_targets

    points: list[tuple[str, str | None, dict]] = [(m["id"], None, {}) for m in _modes(doc)]
    seen: set[tuple[str, str]] = set()
    for preset_id, mode_id, _part, values in preset_targets(doc):
        if (mode_id, preset_id) not in seen:
            seen.add((mode_id, preset_id))
            points.append((mode_id, preset_id, values))
    return points


def _env(scope: dict, values: dict) -> dict[str, float | bool]:
    env = dict(scope)
    for key, raw in values.items():
        value = _value(raw)
        if key in env and value is not None:
            env[key] = value
    return env


def _where(mode: str, preset: str | None) -> str:
    return f"mode '{mode}', preset '{preset}'" if preset else f"mode '{mode}' at its defaults"


# ── expressions ──────────────────────────────────────────────────────────────────────


def _expressions(control: dict) -> list[tuple[str, object]]:
    """Every ``(field, source)`` of a control that may be an expression."""
    found: list[tuple[str, object]] = []
    if "present_when" in control:
        found.append(("present_when", control["present_when"]))
    travel = control.get("travel")
    if isinstance(travel, dict):
        for key in ("depth", "tilt"):
            if _is_expr(travel.get(key)):
                found.append((f"travel.{key}", travel[key]))
    pixels = control.get("pixels")
    if isinstance(pixels, list):
        for i, item in enumerate(pixels):
            if _is_expr(item):
                found.append((f"pixels[{i}]", item))
    return found


def _is_expr(value: object) -> bool:
    return isinstance(value, dict) and "expr" in value


def _parse(source: object, where: str):
    """``(tree, None)`` or ``(None, message)``."""
    try:
        return core.parse_expression(source, where), None
    except core.GraphCoreError as exc:
        return None, str(exc)


def _number(raw: object, env: dict) -> float:
    """A declared number at a parameter point. Raises GraphCoreError or ValueError."""
    if _is_expr(raw):
        value = core.evaluate(core.parse_expression(raw), env)
    else:
        value = raw
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("is not a number")
    if not math.isfinite(value):
        raise ValueError("is not finite")
    return float(value)


def _present(control: dict, env: dict) -> bool:
    if "present_when" not in control:
        return True
    return core.truthy(core.evaluate(core.parse_expression(control["present_when"]), env))


# ── what a control sends ─────────────────────────────────────────────────────────────


def _emissions(control: dict) -> list[tuple[str, str, str]]:
    """``(field, name, required event type)`` for every input name a control declares."""
    role = control.get("role")
    out: list[tuple[str, str, str]] = []
    code = control.get("code")
    if role == "button":
        if isinstance(code, str):
            out.append(("code", code, "EV_KEY"))
        elif isinstance(code, dict) and isinstance(code.get("axis"), str):
            out.append(("code.axis", code["axis"], "EV_ABS"))
    elif role == "stick":
        axes = control.get("axes")
        if isinstance(axes, dict):
            for key in ("x", "y"):
                if isinstance(axes.get(key), str):
                    out.append((f"axes.{key}", axes[key], "EV_ABS"))
        if isinstance(control.get("click"), str):
            out.append(("click", control["click"], "EV_KEY"))
    elif role == "trigger":
        if isinstance(code, str):
            out.append(("code", code, "EV_KEY"))
        if isinstance(control.get("axis"), str):
            out.append(("axis", control["axis"], "EV_ABS"))
    elif role == "switch" and isinstance(code, str):
        out.append(("code", code, "EV_SW|EV_KEY"))
    return out


def _signals(control: dict) -> set[str]:
    """What tells this control apart on the wire: a hat direction is its own signal."""
    signals = set()
    for field, name, _ev in _emissions(control):
        if field == "code.axis":
            signals.add(f"{name}={control['code'].get('value')}")
        else:
            signals.add(name)
    return signals


def _code_problems(control: dict) -> list[str]:
    out = []
    table = input_codes()["source"]
    for field, name, wanted in _emissions(control):
        actual = _code_type(name)
        if actual is None:
            out.append(
                f"{RULE_ID}: control '{control['part']}': {field} '{name}' is not an input "
                f"event name in {table['file']} at {table['tag']}; a name the table lacks "
                "is added by refreshing the table in the keystone, never by spelling it here"
            )
        elif actual not in wanted.split("|"):
            out.append(
                f"{RULE_ID}: control '{control['part']}': {field} '{name}' is an {actual} "
                f"name, and a {control.get('role')}'s {field} is {wanted.replace('|', ' or ')}"
            )
    if control.get("role") == "stick" and isinstance(control.get("axes"), dict):
        axes = control["axes"]
        if isinstance(axes.get("x"), str) and axes.get("x") == axes.get("y"):
            out.append(
                f"{RULE_ID}: control '{control['part']}': axes.x and axes.y are both "
                f"'{axes['x']}'; a stick reports two axes"
            )
    return out


# ── pass 1: the manifest alone ───────────────────────────────────────────────────────


def _schema_problems(block: dict) -> list[str]:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(load_schema(SCHEMA))
    out = []
    for err in sorted(validator.iter_errors(block), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"{RULE_ID} schema device/{where}: {err.message}")
    return out


def _version_note(block: dict) -> list[str]:
    declared = block.get("vocabulary")
    if not isinstance(declared, str) or not declared.startswith(f"{VOCABULARY}/1."):
        return []
    minor = declared.rsplit(".", 1)[1]
    if minor.isdigit() and int(minor) > KNOWN_MINOR:
        return [
            f"{RULE_ID}: the declaration is written in {declared}; this keystone knows "
            f"{VOCABULARY}/1.{KNOWN_MINOR} and checked it as far as that goes"
        ]
    return []


def _part_problems(doc: dict, block: dict) -> list[str]:
    out = []
    parts = [
        p["id"] for p in doc.get("parts") or []
        if isinstance(p, dict) and isinstance(p.get("id"), str)
    ]
    rendered = {pid for mode in _modes(doc) for pid in _mode_parts(mode)}
    declared: dict[str, str] = {}
    entries = [(pid, "structure") for pid in _structure(block)]
    entries += [(control["part"], "control") for control in _controls(block)]
    for pid, kind in entries:
        if pid in declared:
            out.append(
                f"{RULE_ID}: part '{pid}' is declared twice ({declared[pid]} and {kind}); "
                "one entry describes one part"
            )
            continue
        declared[pid] = kind
    for pid, kind in declared.items():
        if pid not in parts:
            out.append(
                f"{RULE_ID}: {kind} '{pid}' is not a part of this cartridge (parts[]: "
                f"{', '.join(parts) or 'none'})"
            )
        elif pid not in rendered:
            why = (
                "a control nothing renders cannot be shown or pressed" if kind == "control"
                else "structure nothing renders cannot hold a control"
            )
            out.append(f"{RULE_ID}: {kind} '{pid}' is rendered by no mode; {why}")
    for pid in parts:
        if pid not in declared:
            out.append(
                f"{RULE_ID}: part '{pid}' is neither a control nor listed in "
                "device.structure; every part of a device cartridge is one or the other"
            )
    return out


def _entries(block: dict) -> list[tuple[str, dict]]:
    """``(kind, entry)`` for every structure entry and every control."""
    return [("structure", e) for e in _structure_entries(block)] + [
        ("control", c) for c in _controls(block)
    ]


def _expression_problems(doc: dict, block: dict) -> list[str]:
    out = []
    scope = _scope(doc)
    declared = {
        p["id"] for p in doc.get("parameters") or []
        if isinstance(p, dict) and isinstance(p.get("id"), str)
    }
    for kind, entry in _entries(block):
        pid = entry["part"]
        for field, source in _expressions(entry):
            tree, error = _parse(source, f"device {kind} '{pid}' {field}")
            if tree is None:
                out.append(f"{RULE_ID}: {kind} '{pid}': {field}: {error}")
                continue
            for name in sorted(core.expression_names(tree) - set(scope)):
                reason = (
                    "is not a number or a boolean, and the dialect reads nothing else"
                    if name in declared else "is not a declared parameter"
                )
                out.append(f"{RULE_ID}: {kind} '{pid}': {field} reads '{name}', which {reason}")
    for control in _controls(block):
        pid = control["part"]
        listed = control.get("parameters")
        for name in listed if isinstance(listed, list) else []:
            if isinstance(name, str) and name not in declared:
                out.append(
                    f"{RULE_ID}: control '{pid}': parameters names '{name}', which is not "
                    "a declared parameter"
                )
    return out


def _label_problems(control: dict) -> list[str]:
    """A control's label is a surface string: it carries the commons' locales (en, es)."""
    from ..rules import _i18n_missing

    if "label" not in control:
        return []
    return [
        f"{RULE_ID}: control '{control['part']}': label is missing its '{loc}' translation"
        for loc in _i18n_missing(control["label"])
    ]


def _screen_problems(control: dict) -> list[str]:
    surface = control.get("surface")
    if control.get("role") != "screen" or not isinstance(surface, dict):
        return []
    normal, up = surface.get("normal"), surface.get("up")
    if _axis(normal) is not None and _axis(up) is not None:
        if _axis(normal)[0] == _axis(up)[0]:
            return [
                f"{RULE_ID}: control '{control['part']}': surface.normal {normal} and "
                f"surface.up {up} lie on one axis; the top of the picture is a direction "
                "in the face, not through it"
            ]
    return []


def _point_numbers(control: dict, env: dict) -> list[str]:
    """What is wrong with a present control's numbers at one parameter point."""
    out = []
    travel = control.get("travel") if isinstance(control.get("travel"), dict) else {}
    checks = []
    if "depth" in travel:
        checks.append(("travel.depth", travel["depth"], lambda v: v > 0, "must be above 0 mm"))
    if "tilt" in travel:
        checks.append(
            ("travel.tilt", travel["tilt"], lambda v: 0 < v < 90, "must be between 0 and 90°")
        )
    pixels = control.get("pixels")
    for i, item in enumerate(pixels if isinstance(pixels, list) else []):
        checks.append((
            f"pixels[{i}]", item, lambda v: v >= 1 and v == int(v),
            "must be a whole number of pixels, 1 or more",
        ))
    for field, raw, good, rule in checks:
        try:
            value = _number(raw, env)
        except (core.GraphCoreError, ValueError) as exc:
            out.append(f"{field} {exc}")
            continue
        if not good(value):
            out.append(f"{field} is {value:g}; it {rule}")
    return out


def _point_rules(doc: dict, block: dict) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    scope = _scope(doc)
    modes = {m["id"]: m for m in _modes(doc)}
    entries = _entries(block)
    for mode_id, preset_id, values in _points(doc):
        env = _env(scope, values)
        listed = set(_mode_parts(modes[mode_id]))
        here = _where(mode_id, preset_id)
        sending: dict[str, str] = {}
        for kind, control in entries:
            pid = control["part"]
            if pid not in listed:
                continue
            try:
                present = _present(control, env)
            except core.GraphCoreError as exc:
                problems.append(f"{RULE_ID}: {kind} '{pid}': present_when at {here}: {exc}")
                continue
            if not present:
                problems.append(
                    f"{RULE_ID}: {here}: the mode lists {kind} '{pid}', and the "
                    f"declaration says it is absent there (present_when "
                    f"'{control['present_when']}' is false); a mode shows only the "
                    "parts its parameter point has"
                )
                continue
            if kind == "structure":
                continue
            for message in _point_numbers(control, env):
                problems.append(f"{RULE_ID}: control '{pid}' at {here}: {message}")
            for signal in sorted(_signals(control)):
                if signal in sending:
                    notes.append(
                        f"{RULE_ID}: {here}: controls '{sending[signal]}' and '{pid}' both "
                        f"send {signal}; a program cannot tell them apart"
                    )
                else:
                    sending[signal] = pid
    return problems, notes


def manifest_rules(doc: dict) -> tuple[list[str], list[str]]:
    """``(problems, notes)`` from the manifest alone. Empty without a ``device`` block."""
    if not isinstance(doc, dict) or "device" not in doc:
        return [], []
    block = _block(doc)
    if block is None:
        return [f"{RULE_ID}: device must be an object"], []
    problems = _schema_problems(block)
    notes = _version_note(block)
    problems.extend(_part_problems(doc, block))
    for control in _controls(block):
        problems.extend(_code_problems(control))
        problems.extend(_label_problems(control))
        problems.extend(_screen_problems(control))
    expression_problems = _expression_problems(doc, block)
    problems.extend(expression_problems)
    if not expression_problems:
        # An expression that does not parse or reads an unknown name has been reported
        # once; evaluating it at every point would repeat the same finding per point.
        point_problems, point_notes = _point_rules(doc, block)
        problems.extend(point_problems)
        notes.extend(point_notes)
    return problems, notes


# ── pass 2: the graph (RFC 0067) ─────────────────────────────────────────────────────


def _graph_names(mode: dict) -> list[str]:
    names: list[str] = []
    for key in ("cq_file", "scad_file", "graph_file"):
        name = mode.get(key)
        if isinstance(name, str) and name.endswith(GRAPH_FILE_SUFFIX) and name not in names:
            names.append(name)
    return names


def _read_graph(cartridge_dir: Path, name: str) -> dict | None:
    root = cartridge_dir.resolve()
    path = (cartridge_dir / name).resolve()
    if root not in path.parents or not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _read_names(control: dict) -> set[str]:
    names: set[str] = set()
    for _field, source in _expressions(control):
        tree, _error = _parse(source, "device")
        if tree is not None:
            names |= core.expression_names(tree)
    listed = control.get("parameters")
    names |= {n for n in (listed if isinstance(listed, list) else []) if isinstance(n, str)}
    return names


def graph_rules(cartridge_dir: Path, doc: dict) -> tuple[list[str], list[str]]:
    """``(problems, notes)``: every control is an output of its mode's graph.

    A graph the render lane or the graph core refuses (missing, not JSON, not an object)
    is theirs to report; here it contributes nothing rather than a second finding.
    """
    block = _block(doc)
    if block is None:
        return [], []
    problems: list[str] = []
    controls = {c["part"]: c for c in _controls(block)}
    reads = {e["part"]: ("structure", e) for e in _structure_entries(block)}
    reads.update({pid: ("control", c) for pid, c in controls.items()})
    for mode in _modes(doc):
        shown = [pid for pid in _mode_parts(mode) if pid in controls]
        if not shown:
            continue
        listed = [pid for pid in _mode_parts(mode) if pid in reads]
        names = _graph_names(mode)
        if not names:
            problems.append(
                f"{RULE_ID}: mode '{mode['id']}' shows controls ({', '.join(shown)}) and "
                "names no graph; a control is declared as an output of its mode's graph "
                "(a graph_file beside the script, or a graph source)"
            )
            continue
        for name in names:
            graph = _read_graph(Path(cartridge_dir), name)
            if graph is None:
                continue
            outputs = graph.get("outputs") if isinstance(graph.get("outputs"), dict) else {}
            for pid in shown:
                if pid not in outputs:
                    problems.append(
                        f"{RULE_ID}: graph {name}: mode '{mode['id']}' shows control "
                        f"'{pid}', which is not one of the graph's outputs"
                    )
            declarations = graph.get("declarations")
            entries = declarations.get("parameters") if isinstance(declarations, dict) else None
            if not isinstance(entries, list):
                continue
            declared = {e["id"] for e in entries if isinstance(e, dict) and "id" in e}
            for pid in listed:
                kind, entry = reads[pid]
                for read in sorted(_read_names(entry) - declared):
                    problems.append(
                        f"{RULE_ID}: graph {name}: {kind} '{pid}' reads parameter "
                        f"'{read}', which the graph does not declare"
                    )
    return problems, []


# ── pass 3: the rendered parts ───────────────────────────────────────────────────────


@dataclass
class DeviceCheck:
    """The verdict on one control at one rendered point."""

    part: str
    role: str
    mode: str
    preset: str | None
    engine: str | None
    #: "pass", "fail", or "unverified": the render was skipped or failed (the render lane
    #: reports a failed render itself), or no structure part was rendered at the point,
    #: so nothing here judged where the control sits.
    status: str
    detail: str
    notes: tuple[str, ...] = ()
    #: The structure part the control was judged against (its host), or None.
    host: str | None = None

    @property
    def summary(self) -> str:
        suffix = f", {self.engine}" if self.engine else ""
        point = f"preset '{self.preset}'" if self.preset else "defaults"
        target = f"({self.mode}, {self.part}, {point}{suffix})"
        verdict = {"pass": "ok", "fail": "FAIL", "unverified": "unverified"}[self.status]
        return f"{RULE_ID}: {self.role} {target}: {verdict} — {self.detail}"


def _gap(a, b) -> float:
    """The distance between two axis-aligned boxes (0 when they touch or overlap)."""
    per_axis = [max(a[0][i] - b[1][i], b[0][i] - a[1][i], 0.0) for i in range(3)]
    return math.sqrt(sum(d * d for d in per_axis))


def _overlap(a, b) -> float:
    """The volume two axis-aligned boxes share (0 when they only touch or are apart)."""
    volume = 1.0
    for i in range(3):
        volume *= max(min(a[1][i], b[1][i]) - max(a[0][i], b[0][i]), 0.0)
    return volume


def _host(bounds, hosts: list[tuple[str, tuple]]) -> tuple[str, tuple, float]:
    """``(part, box, gap)`` of the structure part a control belongs to: the nearest box,
    and among boxes the control touches, the one it shares the most volume with (a
    button in its seat shares its stem with the shell, not with the lid beside it)."""
    ranked = sorted(
        enumerate(hosts),
        key=lambda item: (_gap(bounds, item[1][1]), -_overlap(bounds, item[1][1]), item[0]),
    )
    _index, (part, box) = ranked[0]
    return part, box, _gap(bounds, box)


def _centre(box, axis: int) -> float:
    return (box[0][axis] + box[1][axis]) / 2


def _side(box, axis: int, sign: int) -> float:
    """The coordinate of a box's face on one side of one axis."""
    return box[1][axis] if sign > 0 else box[0][axis]


def _reaches(bounds, host, axis: int, sign: int) -> float:
    """How far the control's face on the ``sign`` side of ``axis`` falls short of the
    host's face on that side (0 or less when it reaches it or stands proud of it)."""
    return (_side(host, axis, sign) - _side(bounds, axis, sign)) * sign


def _seated(bounds, host_id: str, host, gap: float) -> tuple[list[str], list[str]]:
    """``(failures, verified)``: the control's box comes within DETACHED_MM of the surface
    of its host's box, from outside (detached) or from inside (buried)."""
    if gap > DETACHED_MM:
        return [
            f"sits {gap:.2f} mm away from the nearest structure part, '{host_id}' (more "
            f"than {DETACHED_MM:g} mm); a control belongs on its device"
        ], []
    inside = min(
        min(bounds[0][i] - host[0][i], host[1][i] - bounds[1][i]) for i in range(3)
    )
    if inside > DETACHED_MM:
        return [
            f"lies {inside:.2f} mm inside structure part '{host_id}' on every side (more "
            f"than {DETACHED_MM:g} mm); a control reaches the surface of the part it is "
            "on"
        ], []
    return [], [f"on '{host_id}'"]


def _faces_out(bounds, host_id: str, host, spec: str, field: str, press: bool):
    """``(failures, verified)`` for a direction that must point into the host (a press)
    or out of it (a lit face), from the face of the host the control sits on."""
    axis, sign = _axis(spec)
    out = -sign if press else sign  # the side of the host the control sits on
    letter = spec[1]
    away = (_centre(bounds, axis) - _centre(host, axis)) * out
    if away <= 0:
        lies = "+" if _centre(host, axis) > _centre(bounds, axis) else "-"
        verb = "points away from" if press else "looks into"
        return [
            f"{field} {spec} {verb} structure part '{host_id}' (the structure part lies "
            f"{lies}{letter} of the control); "
            + ("a press moves a control in" if press else "a lit face looks out of its device")
        ], []
    short = _reaches(bounds, host, axis, out)
    if short > DETACHED_MM:
        return [
            f"{field} {spec}: the part's {'+' if out > 0 else '-'}{letter} side is "
            f"{short:.2f} mm short of that face of structure part '{host_id}' (more than "
            f"{DETACHED_MM:g} mm); a control sits on the face it "
            + ("is pressed into" if press else "lights")
        ], []
    return [], [f"presses in along {spec}" if press else f"looks out along {spec}"]


def _judge(control: dict, check, env: dict, hosts: list) -> tuple[list[str], list[str],
                                                                   list[str], str | None]:
    """``(failures, notes, what was verified, host)`` for one control against its mesh.

    ``hosts`` are ``(part, bounds)`` of the structure parts rendered and present at the
    same point. Without one, nothing here can say where the control sits: the host is
    None and only what the part's own extents show is judged.
    """
    failures: list[str] = []
    notes: list[str] = []
    verified: list[str] = []
    role = control.get("role")
    extents = check.extents
    bounds = getattr(check, "bounds", None)
    host_id = host = None

    if hosts and bounds is not None:
        host_id, host, gap = _host(bounds, hosts)
        found, ok = _seated(bounds, host_id, host, gap)
        failures += found
        verified += ok
        if found:
            host = None  # a control off its host has no face of it to be judged on

    travel = control.get("travel") if isinstance(control.get("travel"), dict) else {}
    if _axis(travel.get("axis")) is not None and role in ("button", "trigger", "stick"):
        axis, _sign = _axis(travel["axis"])
        if host is not None:
            found, ok = _faces_out(bounds, host_id, host, travel["axis"], "travel.axis", True)
            failures += found
            verified += ok
        if "depth" in travel and extents is not None:
            try:
                depth = _number(travel["depth"], env)
            except (core.GraphCoreError, ValueError):
                depth = None
            if depth is not None and depth > extents[axis] + 1e-6:
                notes.append(
                    f"travel.depth {depth:g} mm is more than the part's "
                    f"{extents[axis]:.3f} mm along {travel['axis'][1]}"
                )

    surface = control.get("surface") if isinstance(control.get("surface"), dict) else {}
    faces = _axis(surface.get("normal")), _axis(surface.get("up"))
    square_on = None not in faces and faces[0][0] != faces[1][0]
    if role == "screen" and extents is not None and square_on:
        normal, up = faces[0][0], faces[1][0]
        across = 3 - normal - up
        if extents[normal] >= min(extents[across], extents[up]):
            failures.append(
                f"surface.normal {surface['normal']} is not the part's thin direction "
                f"(extents {extents[0]:.3f} × {extents[1]:.3f} × {extents[2]:.3f} mm); the "
                "lit face is the large face of a screen part"
            )
        else:
            verified.append(
                f"face {extents[across]:.2f} × {extents[up]:.2f} mm looking {surface['normal']}"
            )
            if host is not None:
                found, ok = _faces_out(
                    bounds, host_id, host, surface["normal"], "surface.normal", False
                )
                failures += found
                verified += ok
            try:
                listed = control.get("pixels")
                px = [_number(i, env) for i in (listed if isinstance(listed, list) else [])]
            except (core.GraphCoreError, ValueError):
                px = []
            if len(px) == 2 and px[0] > 0 and px[1] > 0:
                pitch_x, pitch_y = extents[across] / px[0], extents[up] / px[1]
                if abs(pitch_x - pitch_y) > PIXEL_ASPECT_BAND * max(pitch_x, pitch_y):
                    notes.append(
                        f"{px[0]:g} × {px[1]:g} pixels on a {extents[across]:.2f} × "
                        f"{extents[up]:.2f} mm face are not square (pitch "
                        f"{pitch_x:.4f} × {pitch_y:.4f} mm)"
                    )

    if check.bodies is not None and check.bodies > 1:
        notes.append(f"renders as {check.bodies} bodies; a control is usually one")
    return failures, notes, verified, host_id


def _preset_values(doc: dict) -> dict[str, dict]:
    """Preset label → values, labelled exactly as the render lane labels a preset render
    (``rules.preset_targets``: the id, else the slug, else ``presets[i]``)."""
    from ..rules import preset_targets

    return {label: values for label, _mode, _part, values in preset_targets(doc)}


def render_checks(doc: dict, renders: list) -> list[DeviceCheck]:
    """One :class:`DeviceCheck` per (control a mode lists, rendered point, engine).

    ``renders`` are the run's ``RenderCheck`` objects. A control the declaration calls
    absent at a point is not judged there (pass 1 already refused a mode that lists it),
    and a structure part absent there is nobody's host.
    """
    block = _block(doc)
    if block is None:
        return []
    controls = {c["part"]: c for c in _controls(block)}
    structure = {e["part"]: e for e in _structure_entries(block)}
    scope = _scope(doc)
    presets = _preset_values(doc)

    groups: dict[tuple, list] = {}
    for check in renders:
        groups.setdefault((check.mode, check.preset, check.engine), []).append(check)

    out: list[DeviceCheck] = []
    for (mode, preset, engine), checks in groups.items():
        env = _env(scope, presets.get(preset) or {}) if preset else dict(scope)
        hosts = []
        for c in checks:
            if (
                c.part in structure and c.ok and not c.skipped
                and getattr(c, "bounds", None) is not None
            ):
                try:
                    if _present(structure[c.part], env):
                        hosts.append((c.part, c.bounds))
                except core.GraphCoreError:
                    continue
        for check in checks:
            control = controls.get(check.part)
            if control is None or not isinstance(control.get("role"), str):
                continue
            base = dict(part=check.part, role=control["role"], mode=mode, preset=preset,
                        engine=engine)
            try:
                if not _present(control, env):
                    continue
            except core.GraphCoreError:
                continue
            if check.skipped or not check.ok or check.extents is None:
                reason = check.skipped or "its render failed"
                out.append(DeviceCheck(**base, status="unverified", detail=reason))
                continue
            failures, notes, verified, host = _judge(control, check, env, hosts)
            if failures:
                status, detail = "fail", "; ".join(failures)
            elif host is None:
                status = "unverified"
                detail = "; ".join(
                    ["no structure part was rendered at this point, so nothing judged "
                     "where the control sits"] + verified
                )
            else:
                status, detail = "pass", "; ".join(verified)
            out.append(DeviceCheck(**base, status=status, detail=detail, notes=tuple(notes),
                                   host=host))
    return out


# ── for a consumer: the declaration at one parameter point ───────────────────────────


def resolve(doc: dict, values: dict | None = None) -> list[dict]:
    """The controls of a device at one parameter point, with their numbers computed.

    ``values`` are parameter values over the manifest defaults (a preset's ``values``, or
    what a visitor set). Each entry is the declared control with ``present`` added and
    every ``{"expr"}`` replaced by its value. A viewer or an input bridge that cannot run
    this module computes the same thing with the graph core's evaluator: the expressions
    are in its dialect and read nothing but parameters.
    """
    block = _block(doc)
    if block is None:
        return []
    env = _env(_scope(doc), values or {})
    resolved = []
    for control in _controls(block):
        entry = json.loads(json.dumps(control))
        entry["present"] = _present(control, env)
        travel = entry.get("travel")
        if isinstance(travel, dict):
            for key in ("depth", "tilt"):
                if key in travel:
                    travel[key] = _number(travel[key], env)
        if isinstance(entry.get("pixels"), list):
            entry["pixels"] = [int(_number(item, env)) for item in entry["pixels"]]
        resolved.append(entry)
    return resolved
