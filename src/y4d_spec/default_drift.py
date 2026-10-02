"""`default-drift` — the manifest `default` against the literal the SOURCE falls back to.

A cartridge states every parameter's default twice: once in `project.json` (what the
Studio shows and what a full-parameter render injects) and once in the source (what
the engine uses when the parameter is NOT injected). yantra4d injects only the keys a
caller sends, so a render with an empty request — the landing prerender, a pravara
import, a Fashion Cabinet body render — gets the SOURCE literal, while the Studio
shows the manifest one. When they differ, the same "default" instance has two
geometries, and GOC-1 (`variables.json`) cannot record the one it rendered without
either injecting the manifest default (changing geometry) or reading the source.

The three places a source keeps its fallback, each read with a parser, not a guess:

  * CadQuery (`.py`/`.cq`): `PARAM(lambda: <id>, <literal>)` — the commons' accessor
    for an injected bare global (cq_runner.py: `exec_globals.update(params)`). Read
    with `ast`, so docstrings and comments that QUOTE the idiom are not matches. The
    literal may be a constant expression (`-2.5`) or a module-level constant name
    (`MC4_BODY_D`) bound to a literal; anything else is not a literal and is skipped.
  * OpenSCAD (`.scad`): a top-level `<id> = <literal>;`, which the platform's `-D`
    overrides, or its guarded form `<id> = is_undef(<id>) ? <literal> : <id>;`
    (rubiks-hyperobject). Assignments inside a module, function or block are not
    defaults. In-cartridge `include <>` files are followed (textual inclusion, same
    scope); `use <>` imports no variables and is not. The LAST top-level assignment
    wins, as in OpenSCAD.
  * Graph (`.graph.json`): the node literal a manifest `binding` (`"node.param"`)
    targets — the transpiler renders that literal when the parameter is not injected.

Comparison: a boolean equals 0/1 the way OpenSCAD and Python treat them; numbers are
equal within 1e-9; a numeric STRING (a select whose options are spelled "4") equals
the number it spells; other strings compare as-is.

Severity: NOTE ONLY — never a conformance failure. Per the house rule, a new rule lands
as a note, and nothing becomes a failure until its false-positive analysis against the
whole commons is written down. Some drift is deliberate per mode (one parameter, two
mode files, two defaults); the report is therefore per (file, line) with the modes that
use the file, never folded into one guessed verdict per cartridge.
"""

from __future__ import annotations

import ast
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "DriftFinding",
    "RULE_ID",
    "cadquery_param_literals",
    "default_drift_findings",
    "default_drift_rules",
    "defaults_equal",
    "graph_binding_literals",
    "scad_top_level_literals",
]

RULE_ID = "default-drift"
NUMERIC_TOLERANCE = 1e-9

_SCRIPT_SUFFIXES = (".py", ".cq")
_MAX_INCLUDE_DEPTH = 4


@dataclass(frozen=True)
class DriftFinding:
    """One parameter whose manifest default differs from one source literal."""

    param: str
    modes: tuple[str, ...]
    file: str  # relative to the cartridge directory, POSIX
    line: int
    manifest_default: object
    source_literal: object
    engine: str  # "cadquery" | "openscad" | "graph" | "fc"

    @property
    def where(self) -> str:
        return f"{self.file}:{self.line}"

    def summary(self) -> str:
        modes = ", ".join(self.modes)
        return (
            f"{RULE_ID}: parameter '{self.param}' manifest default "
            f"{_show(self.manifest_default)} != {self.engine} source literal "
            f"{_show(self.source_literal)} at {self.where} (mode(s) {modes}) — a render "
            f"that does not inject it uses the source literal, not the default the "
            f"manifest declares"
        )


def _show(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


# ── comparison ───────────────────────────────────────────────────────────────
def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def defaults_equal(manifest_default: object, source_literal: object) -> bool:
    """True when the two defaults produce the same injected value.

    bool vs 0/1 equal; numbers within 1e-9; a numeric string vs a number compared as
    numbers; two strings compared as-is (no case folding, no trimming).
    """
    if isinstance(manifest_default, str) and isinstance(source_literal, str):
        return manifest_default == source_literal
    a, b = _as_number(manifest_default), _as_number(source_literal)
    if a is None or b is None:
        return manifest_default == source_literal
    return abs(a - b) <= NUMERIC_TOLERANCE


# ── CadQuery: PARAM(lambda: <id>, <literal>) ─────────────────────────────────
_UNRESOLVED = object()


def _literal(node: ast.AST, constants: dict) -> object:
    if isinstance(node, ast.Name):
        return constants.get(node.id, _UNRESOLVED)
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return _UNRESOLVED
    if isinstance(value, (bool, int, float, str)):
        return value
    return _UNRESOLVED


def _module_constants(tree: ast.Module) -> dict:
    """Module-level `NAME = <literal>` bindings, the last assignment winning."""
    constants: dict = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target, value = stmt.targets[0], stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            target, value = stmt.target, stmt.value
        else:
            continue
        if isinstance(target, ast.Name):
            literal = _literal(value, {})
            if literal is _UNRESOLVED:
                constants.pop(target.id, None)
            else:
                constants[target.id] = literal
    return constants


def cadquery_param_literals(text: str) -> list[tuple[str, object, int]]:
    """Every `PARAM(lambda: <id>, <literal>)` call: `(id, literal, line)`, in order.

    A file that does not parse yields nothing (a syntax error is mode_source_rules'
    business and a render failure, not something this rule should guess around). A
    default that is not a literal — an expression over other parameters — is skipped.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    constants = _module_constants(tree)
    out: list[tuple[str, object, int]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and len(node.args) >= 2):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "PARAM"):
            continue
        getter = node.args[0]
        if not (
            isinstance(getter, ast.Lambda)
            and not getter.args.args
            and isinstance(getter.body, ast.Name)
        ):
            continue
        literal = _literal(node.args[1], constants)
        if literal is not _UNRESOLVED:
            out.append((getter.body.id, literal, node.lineno))
    out.sort(key=lambda item: item[2])
    return out


# ── OpenSCAD: top-level <id> = <literal>; ────────────────────────────────────
_SCAD_NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_SCAD_ASSIGN = re.compile(r"^\s*([A-Za-z_$][A-Za-z0-9_]*)\s*=(?!=)\s*(.*?)\s*$", re.S)
_SCAD_GUARDED = re.compile(
    r"^is_undef\(\s*([A-Za-z_$][A-Za-z0-9_]*)\s*\)\s*\?\s*(.+?)\s*:\s*"
    r"([A-Za-z_$][A-Za-z0-9_]*)$",
    re.S,
)
_SCAD_DIRECTIVE = re.compile(r"^\s*(include|use)\s*<([^>]+)>", re.M)


def _blank_scad_comments(text: str) -> str:
    """`//` and `/* */` comments replaced by spaces, newlines and string literals kept."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append("".join("\n" if ch == "\n" else " " for ch in text[i:j]))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _scad_literal(rhs: str) -> object:
    if _SCAD_NUMBER.match(rhs):
        number = float(rhs)
        return int(number) if number.is_integer() and not re.search(r"[.eE]", rhs) else number
    if rhs in ("true", "false"):
        return rhs == "true"
    if len(rhs) >= 2 and rhs[0] == rhs[-1] == '"' and '"' not in rhs[1:-1].replace('\\"', ""):
        return rhs[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return _UNRESOLVED


def _scad_statements(text: str) -> list[tuple[str, int]]:
    """Top-level (depth-0) statements of one OpenSCAD source: `(text, start line)`.

    A statement ends at `;` at depth 0, or at the `}` that closes a depth-0 block (a
    module/function body, an `if`). `include <>`/`use <>` carry no `;` and are blanked
    first. Strings are skipped as opaque so a `;` or brace inside one is inert.
    """
    clean = _SCAD_DIRECTIVE.sub(
        lambda m: "".join("\n" if ch == "\n" else " " for ch in m.group(0)),
        _blank_scad_comments(text),
    )
    out: list[tuple[str, int]] = []
    depth, start, line, start_line = 0, 0, 1, 1
    i, n = 0, len(clean)
    while i < n:
        c = clean[i]
        if c == '"':
            j = i + 1
            while j < n and clean[j] != '"':
                j += 2 if clean[j] == "\\" else 1
            line += clean[i : j + 1].count("\n")
            i = j + 1
            continue
        if c == "\n":
            line += 1
        elif c in "{([":
            depth += 1
        elif c in "})]":
            depth = max(0, depth - 1)
            if c == "}" and depth == 0:
                start, start_line = i + 1, line
        elif c == ";" and depth == 0:
            stmt = clean[start:i]
            lead = len(stmt) - len(stmt.lstrip())
            out.append((stmt, start_line + stmt[:lead].count("\n")))
            start, start_line = i + 1, line
        i += 1
    return out


def scad_top_level_literals(text: str) -> list[tuple[str, object, int]]:
    """Every top-level `<id> = <literal>;` of ONE file: `(id, literal, line)`, in order."""
    out: list[tuple[str, object, int]] = []
    for stmt, line in _scad_statements(text):
        match = _SCAD_ASSIGN.match(stmt)
        if not match:
            continue
        ident, rhs = match.group(1), match.group(2)
        # `N = is_undef(N) ? 3 : N;` — the guarded-default form (rubiks-hyperobject):
        # the literal is what the source falls back to when -D did not set N.
        guarded = _SCAD_GUARDED.match(rhs)
        if guarded and guarded.group(1) == ident == guarded.group(3):
            rhs = guarded.group(2)
        literal = _scad_literal(rhs)
        if literal is not _UNRESOLVED:
            out.append((ident, literal, line))
    return out


def _scad_effective_literals(
    cartridge_dir: Path, name: str, *, _depth: int = 0, _seen: set | None = None
) -> list[tuple[str, object, str, int]]:
    """`(id, literal, file, line)` in evaluation order across in-cartridge includes."""
    seen = set() if _seen is None else _seen
    path = cartridge_dir / name
    if str(path) in seen or not path.is_file() or _depth > _MAX_INCLUDE_DEPTH:
        return []
    seen.add(str(path))
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rel = path.relative_to(cartridge_dir).as_posix()

    # Interleave this file's own assignments with the includes, by line, so "last
    # assignment wins" follows the order OpenSCAD reads them in.
    events: list[tuple[int, object]] = [
        (line, (ident, literal, rel, line))
        for ident, literal, line in scad_top_level_literals(text)
    ]
    for match in _SCAD_DIRECTIVE.finditer(_blank_scad_comments(text)):
        if match.group(1) != "include":
            continue
        target = match.group(2).strip()
        if target.startswith("/") or ".." in target:
            continue  # outside the cartridge: not shipped, not read (see structure.py)
        line = text.count("\n", 0, match.start(1)) + 1
        events.append((line, ("__include__", target)))
    events.sort(key=lambda e: e[0])

    out: list[tuple[str, object, str, int]] = []
    base = path.parent.relative_to(cartridge_dir)
    for _, event in events:
        if event[0] == "__include__":
            out.extend(
                _scad_effective_literals(
                    cartridge_dir, (base / event[1]).as_posix(), _depth=_depth + 1, _seen=seen
                )
            )
        else:
            out.append(event)
    return out


# ── graph: the literal a manifest binding targets ────────────────────────────
def graph_binding_literals(graph: dict, manifest: dict) -> list[tuple[str, object, str]]:
    """`(param id, node literal, "node.param")` for every manifest binding into `graph`."""
    nodes = {
        n["id"]: n
        for n in graph.get("nodes") or []
        if isinstance(n, dict) and isinstance(n.get("id"), str)
    }
    out: list[tuple[str, object, str]] = []
    for p in manifest.get("parameters") or []:
        if not isinstance(p, dict) or not isinstance(p.get("id"), str):
            continue
        binding = p.get("binding")
        targets = binding if isinstance(binding, list) else [binding]
        for target in targets:
            if not isinstance(target, str) or target.count(".") != 1:
                continue
            node_id, param = target.split(".")
            params = (nodes.get(node_id) or {}).get("params")
            if isinstance(params, dict) and param in params:
                value = params[param]
                if isinstance(value, (bool, int, float, str)):
                    out.append((p["id"], value, target))
    return out


def _graph_line(text: str, node_id: str) -> int:
    idx = text.find(f'"{node_id}"')
    return text.count("\n", 0, idx) + 1 if idx >= 0 else 1


# ── the rule ─────────────────────────────────────────────────────────────────
#: The mode keys that name a source. `script_file` is the Fashion Cabinet (soft)
#: spelling; its scripts use the same PARAM idiom, so the rule reads them the same way.
MODE_SOURCE_KEYS = ("cq_file", "scad_file", "graph_file", "script_file")


def _mode_files(mode: dict) -> list[tuple[str, str]]:
    """`(mode key, file name)` for each source a mode names, first key winning."""
    out: list[tuple[str, str]] = []
    for key in MODE_SOURCE_KEYS:
        value = mode.get(key)
        if isinstance(value, str) and value and value not in [n for _, n in out]:
            out.append((key, value))
    return out


def _file_literals(
    cartridge_dir: Path, name: str, manifest: dict, key: str = "cq_file"
) -> list[tuple[str, object, str, int, str]]:
    """`(id, literal, file, line, engine)` for one mode source file. `key` is the mode
    field that named it; a soft `script_file` is labelled engine "fc"."""
    path = cartridge_dir / name
    if not path.is_file():
        return []
    if name.endswith(".graph.json"):
        try:
            text = path.read_text(encoding="utf-8")
            graph = json.loads(text)
        except (OSError, ValueError):
            return []
        if not isinstance(graph, dict):
            return []
        return [
            (pid, value, name, _graph_line(text, target.split(".")[0]), "graph")
            for pid, value, target in graph_binding_literals(graph, manifest)
        ]
    if path.suffix == ".scad":
        effective: dict[str, tuple] = {}
        for ident, literal, rel, line in _scad_effective_literals(cartridge_dir, name):
            effective[ident] = (ident, literal, rel, line, "openscad")
        return list(effective.values())
    if path.suffix in _SCRIPT_SUFFIXES:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        engine = "fc" if key == "script_file" else "cadquery"
        return [
            (ident, literal, name, line, engine)
            for ident, literal, line in cadquery_param_literals(text)
        ]
    return []


def default_drift_findings(cartridge_dir: str | Path, manifest: dict) -> list[DriftFinding]:
    """Every (file, line, parameter) whose literal differs from the manifest default.

    Only parameters that declare a `default` and are in scope for a mode that uses the
    file are compared. One finding per source location, carrying every mode that
    renders through that file; a parameter with two literals in one file (two code
    paths) is two findings.
    """
    from .rules import parameter_mode_listings

    root = Path(cartridge_dir)
    defaults = {
        p["id"]: p["default"]
        for p in manifest.get("parameters") or []
        if isinstance(p, dict) and isinstance(p.get("id"), str) and "default" in p
    }
    listings = parameter_mode_listings(manifest)

    hits: dict[tuple[str, int, str], dict] = {}
    literals_cache: dict[str, list] = {}
    for mode in manifest.get("modes") or []:
        if not isinstance(mode, dict) or not isinstance(mode.get("id"), str):
            continue
        mid = mode["id"]
        for key, name in _mode_files(mode):
            if name not in literals_cache:
                literals_cache[name] = _file_literals(root, name, manifest, key)
            for ident, literal, rel, line, engine in literals_cache[name]:
                if ident not in defaults:
                    continue
                if not any(m.get("id") == mid for m in listings.get(ident, [])):
                    continue
                if defaults_equal(defaults[ident], literal):
                    continue
                key = (rel, line, ident)
                entry = hits.setdefault(
                    key,
                    {"literal": literal, "engine": engine, "modes": []},
                )
                if mid not in entry["modes"]:
                    entry["modes"].append(mid)

    findings = [
        DriftFinding(
            param=ident,
            modes=tuple(entry["modes"]),
            file=rel,
            line=line,
            manifest_default=defaults[ident],
            source_literal=entry["literal"],
            engine=entry["engine"],
        )
        for (rel, line, ident), entry in hits.items()
    ]
    findings.sort(key=lambda f: (f.file, f.line, f.param))
    return findings


def default_drift_rules(cartridge_dir: Path, manifest: dict) -> list[str]:
    """default-drift (NOTE ONLY): manifest `default` vs the source's fallback literal.

    Returns notes, never problems — see the module docstring for why.
    """
    return [f.summary() for f in default_drift_findings(cartridge_dir, manifest)]
