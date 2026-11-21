"""The graph core's rules for a solid cartridge directory (RFC 0067), no render needed.

Two postures, by graph format, and the split is the house rule that a new rule lands as
a note until a whole-commons pass licenses it:

* **1.0 / 1.1 graphs** (all 15 in the solid commons today). The vendored engine is the
  enforcing validator and the render lane already fails a graph it refuses. The core's
  findings are **notes** (`graph-core:`). The whole-commons pass of 2026-11-20 found none
  (CHANGELOG, 0.21.0), so a note here is news.
* **1.2 graphs** — the core's own format: ``kernel``, ``declarations``, ``licence``,
  ``provenance`` and the ``script`` node. None existed before the core, so its rules are
  **failures from birth**, as the sheet commons' were (AGENTS.md): there is no healthy
  cartridge for them to misfire on, and a wrapper the gate lets through is a wrapper the
  RFC's coverage count would report as configurable.

For a 1.2 graph, in order:

1. the core validates it under the solid pack (cycles, sockets, references, unbound
   inputs, expressions, the script node, declarations, licence, provenance);
2. every ``provenance.sources`` digest matches the file it names, so a script edited
   after its wrapper was made is ``source-drift`` until the wrapper is regenerated;
3. the declarations agree with the manifest: an entry the graph declares equals the
   manifest's entry of the same identity (the manifest is generated FROM the graph, so a
   difference is drift), and when every mode has a 1.2 graph, every manifest entry is
   declared by one of them;
4. a **wrapper** wraps its own mode: its source is the mode's script (``cq_file`` or
   ``scad_file``), it outputs every part the mode renders, every part it outputs is
   rendered by some mode that names it (one graph may serve several modes), and it
   passes every parameter the mode lists through under its own name and binds nothing
   else — the shape under which "renders as its script" holds at every parameter point,
   not only at the defaults and presets parity samples.
"""

from __future__ import annotations

import json
from pathlib import Path

import hyperobject_graph as core

from .graph_render import GRAPH_FILE_SUFFIX, core_problems
from .solid_pack import SOLID_PACK

__all__ = ["graph_core_rules"]

#: Where each declared list lives in a solid manifest, and how its entries are named.
_MANIFEST_LISTS = {
    "parameters": (("parameters",), ("id",)),
    "parameter_groups": (("parameter_groups",), ("id", "key", "slug")),
    "presets": (("presets",), ("id", "slug")),
    "constraints": (("constraints",), ()),
    "interfaces": (("hyperobject", "cdg_interfaces"), ("id",)),
}


def _manifest_list(manifest: dict, path: tuple[str, ...]) -> list:
    node: object = manifest
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, list) else []


def _identity(entry: object, keys: tuple[str, ...]) -> str:
    """An entry's identity: its id (or key/slug), else its canonical JSON."""
    if isinstance(entry, dict):
        for key in keys:
            if isinstance(entry.get(key), str):
                return f"{key}:{entry[key]}"
    return "json:" + json.dumps(entry, sort_keys=True)


def _read_inside(cartridge_dir: Path):
    root = cartridge_dir.resolve()

    def read(rel: str) -> bytes | None:
        path = (cartridge_dir / rel).resolve()
        if root not in path.parents or not path.is_file():
            return None
        return path.read_bytes()

    return read


def _graph_sources(mode: dict) -> list[str]:
    seen: list[str] = []
    for key in ("cq_file", "scad_file", "graph_file"):
        name = mode.get(key)
        if isinstance(name, str) and name.endswith(GRAPH_FILE_SUFFIX) and name not in seen:
            seen.append(name)
    return seen


def _script_sources(mode: dict) -> set[str]:
    return {
        mode[key] for key in ("cq_file", "scad_file")
        if isinstance(mode.get(key), str) and not mode[key].endswith(GRAPH_FILE_SUFFIX)
    }


def graph_core_rules(cartridge_dir: Path, manifest: dict) -> tuple[list[str], list[str]]:
    """``(problems, notes)`` for every graph source the manifest's modes name."""
    problems: list[str] = []
    notes: list[str] = []
    modes = [m for m in manifest.get("modes") or [] if isinstance(m, dict)]
    docs: dict[str, dict] = {}
    checked: set[str] = set()
    listed = _mode_parameters(manifest)
    rendered_by: dict[str, set[str]] = {}
    wrappers: dict = {}
    modes_with_core_graph = 0

    for mode in modes:
        mid = mode.get("id")
        mode_has_core_graph = False
        for name in _graph_sources(mode):
            if name not in docs:
                path = cartridge_dir / name
                try:
                    doc = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    # Unknown format, so a note; the render lane fails it as itself.
                    if name not in checked:
                        checked.add(name)
                        notes.append(f"graph-core: {name}: could not be read "
                                     f"({type(exc).__name__}); not checked")
                    continue
                docs[name] = doc
            doc = docs[name]
            minor = core.format_minor(doc) or 0
            if minor < 2:
                if name not in checked:
                    checked.add(name)
                    for p in core_problems(doc, manifest):
                        notes.append(f"graph-core: {name}: {p} (a note on a 1.{minor} graph; "
                                     f"the engine is the enforcing validator)")
                continue
            mode_has_core_graph = mode_has_core_graph or isinstance(
                doc.get("declarations"), dict
            )
            # Once per file (a file may serve several modes); the wrapper rules below
            # run for every mode that names it.
            if name not in checked:
                checked.add(name)
                for p in core_problems(doc, manifest):
                    problems.append(f"graph {name}: {p}")
                for p in core.source_digest_problems(doc, _read_inside(cartridge_dir)):
                    problems.append(f"graph {name}: {p}")
                problems.extend(_declaration_drift(name, doc, manifest))
            plan = core.wrapper_plan(doc, SOLID_PACK)
            if plan is not None:
                scripts = _script_sources(mode)
                if plan.source not in scripts:
                    problems.append(
                        f"graph {name}: mode '{mid}': the wrapper runs '{plan.source}', but "
                        f"the mode's script is {sorted(scripts) or 'not declared'} — a "
                        f"wrapper wraps its own mode's source"
                    )
                parts = {p for p in mode.get("parts") or [] if isinstance(p, str)}
                missing = sorted(parts - set(plan.parts))
                if missing:
                    problems.append(
                        f"graph {name}: mode '{mid}' renders {missing}, which the wrapper "
                        f"does not output ({sorted(plan.parts)})"
                    )
                rendered_by.setdefault(name, set()).update(parts)
                wrappers[name] = plan
                problems.extend(_pass_through_rules(name, mid, plan, listed.get(mid, set())))
        modes_with_core_graph += mode_has_core_graph

    # One graph may serve several modes (idler-608's does). Every output it declares must
    # be a part some mode naming it renders, or the wrapper offers a body nothing asks for.
    for name, plan in wrappers.items():
        stray = sorted(set(plan.parts) - rendered_by.get(name, set()))
        if stray:
            problems.append(
                f"graph {name}: outputs {stray}, which no mode naming this graph renders"
            )
    if modes and modes_with_core_graph == len(modes):
        problems.extend(_coverage(docs, manifest))
    return problems, notes


def _mode_parameters(manifest: dict) -> dict[str, set[str]]:
    """mode id → the parameter ids that mode lists (the scoping G-DEADPARAM uses)."""
    from .rules import parameter_mode_listings

    out: dict[str, set[str]] = {}
    for pid, modes in parameter_mode_listings(manifest).items():
        for mode in modes:
            if isinstance(mode.get("id"), str):
                out.setdefault(mode["id"], set()).add(pid)
    return out


def _pass_through_rules(name: str, mid: object, plan, mode_params: set[str]) -> list[str]:
    """A wrapper verifies AS its script only if it hands the script exactly what the
    mode would: every parameter the mode lists, passed through under its own name, and
    nothing else. Parity compares the defaults and the presets; a renamed, missing or
    added binding would differ at a parameter point no preset sets, and parity would
    report the pair identical anyway. So the shape is required here, where it is total.
    """
    out: list[str] = []
    for key, value in sorted(plan.bind.items()):
        if not (isinstance(value, dict) and value == {"param": key}):
            out.append(
                f"graph {name}: mode '{mid}': the wrapper binds '{key}' to {value!r}; a "
                f"wrapper passes each parameter through under its own name "
                f'({{"{key}": {{"param": "{key}"}}}}) and binds nothing else'
            )
    missing = sorted(mode_params - set(plan.bind) - {"target_part"})
    if missing:
        out.append(
            f"graph {name}: mode '{mid}': the wrapper does not pass {missing} through, which "
            f"the mode lists — the script would receive them alone and not through the graph"
        )
    return out


def _declaration_drift(name: str, doc: dict, manifest: dict) -> list[str]:
    """Every entry the graph declares must equal the manifest's entry of that identity."""
    out: list[str] = []
    projection = core.manifest_projection(doc)
    for key, declared in projection.items():
        path, id_keys = _MANIFEST_LISTS[key]
        in_manifest = {_identity(e, id_keys): e for e in _manifest_list(manifest, path)}
        for entry in declared:
            ident = _identity(entry, id_keys)
            if ident not in in_manifest:
                out.append(
                    f"graph {name}: declarations.{key} {ident} is not in the manifest's "
                    f"{'.'.join(path)} — the manifest is generated from the graph; "
                    f"regenerate it"
                )
            elif in_manifest[ident] != entry:
                out.append(
                    f"graph {name}: declarations.{key} {ident} differs from the "
                    f"manifest's — the manifest is generated from the graph; regenerate it"
                )
    return out


def _coverage(docs: dict[str, dict], manifest: dict) -> list[str]:
    """With a 1.2 graph on every mode, every manifest entry is declared by one."""
    out: list[str] = []
    for key, (path, id_keys) in _MANIFEST_LISTS.items():
        declared = {
            _identity(e, id_keys)
            for doc in docs.values() if (core.format_minor(doc) or 0) >= 2
            for e in core.manifest_projection(doc).get(key, [])
        }
        for entry in _manifest_list(manifest, path):
            ident = _identity(entry, id_keys)
            if ident not in declared:
                out.append(
                    f"manifest {'.'.join(path)} {ident} is declared by no graph — every "
                    f"mode has a 1.2 graph, so the graphs are the source of truth "
                    f"(RFC 0067 §2)"
                )
    return out
