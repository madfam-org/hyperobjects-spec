"""The three component resolvers ASM-1 §3.2 names, and the composite the CLI uses.

    CommonsManifestResolver(commons_dir)    cartridge  → <commons>/<slug>/project.json
    StandardPartsResolver(directory)        standard   → a directory of standard-part JSON
    ExternalResolver()                      external   → the interfaces declared inline
    CompositeResolver(cartridge=, standard=, external=)   dispatch on source.type

Every one returns a `ResolvedComponent` or raises `ResolutionError`; see resolution.py.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from hyperobjects_schemas.generator_output import canonical_json, tree_sha256

from ..frame_eval import resolve_parameters
from .resolution import (
    ComponentResolver,
    ResolutionError,
    ResolvedComponent,
    cartridge_identity,
    goc1_variables,
    parameter_value_problems,
    resolve_interfaces,
)

__all__ = [
    "CommonsManifestResolver",
    "CompositeResolver",
    "ExternalResolver",
    "StandardPartsResolver",
]


def _source(component: Mapping) -> Mapping:
    source = component.get("source")
    if not isinstance(source, Mapping):
        raise ResolutionError(["has no source object"])
    return source


# ── cartridges ────────────────────────────────────────────────────────────────
class CommonsManifestResolver:
    """Cartridges of the solid commons, read from `<commons_dir>/<slug>/project.json`.

    Checks that the mode exists, that a named part is one the mode produces, and that
    every given parameter is declared and admissible (never clamped); evaluates every
    interface frame at full injection (manifest defaults overridden by the given
    values). The identity is the GOC-1 `instance_id` over the cartridge directory's
    `tree_sha256` — computed once per slug and cached, as it reads every file.
    """

    def __init__(self, commons_dir: str | Path, commons: str = "solid"):
        self.commons_dir = Path(commons_dir)
        self.commons = commons
        self._manifests: dict[str, dict] = {}
        self._trees: dict[str, str] = {}

    def manifest(self, slug: str) -> dict:
        if slug not in self._manifests:
            path = self.commons_dir / slug / "project.json"
            if not path.is_file():
                raise ResolutionError(
                    [f"cartridge '{slug}' not found ({path} does not exist)"]
                )
            try:
                self._manifests[slug] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ResolutionError([f"cartridge '{slug}': cannot read {path}: {exc}"]) from None
        return self._manifests[slug]

    def resolve(self, component: Mapping) -> ResolvedComponent:
        source = _source(component)
        commons, slug = source.get("commons"), source.get("slug")
        if commons != self.commons:
            raise ResolutionError(
                [f"commons {commons!r} is not served here (this resolver reads {self.commons!r})"]
            )
        if not isinstance(slug, str) or not slug or "/" in slug or slug.startswith("."):
            raise ResolutionError([f"cartridge slug {slug!r} is not a single directory name"])
        manifest = self.manifest(slug)
        mode_id, part = source.get("mode"), source.get("part")
        given = source.get("parameters") or {}

        problems: list[str] = []
        modes = {m.get("id"): m for m in manifest.get("modes") or [] if isinstance(m, Mapping)}
        mode = modes.get(mode_id)
        produced: list[str] = []
        if mode is None:
            problems.append(
                f"cartridge '{slug}' has no mode {mode_id!r} "
                f"(modes: {', '.join(sorted(str(m) for m in modes)) or 'none'})"
            )
        else:
            produced = [p for p in mode.get("parts") or [] if isinstance(p, str)]
            if not produced:  # a mode that lists no parts produces the manifest's parts
                produced = [p["id"] for p in manifest.get("parts") or []
                            if isinstance(p, Mapping) and isinstance(p.get("id"), str)]
            if part is not None and part not in produced:
                problems.append(
                    f"cartridge '{slug}' mode '{mode_id}' does not produce part {part!r} "
                    f"(it produces: {', '.join(produced) or 'nothing'})"
                )
        problems.extend(
            f"cartridge '{slug}': {p}"
            for p in parameter_value_problems(manifest.get("parameters"), given)
        )
        if problems:
            raise ResolutionError(problems)

        if slug not in self._trees:
            self._trees[slug] = tree_sha256(self.commons_dir / slug)
        values = resolve_parameters(manifest, given)
        identity, details = cartridge_identity(
            slug=slug,
            mode=mode_id,
            part=part,
            tree_sha256=self._trees[slug],
            variables=goc1_variables(manifest.get("parameters"), values),
        )
        available = [part] if part is not None else produced
        # Informative only (never hashed): the AAS projection rolls requirements up for the
        # parts this component produces (ASM-1 §5).
        details = {**details, "parts": list(available)}
        if isinstance(manifest.get("requirements"), Mapping):
            details["requirements"] = manifest["requirements"]
        return ResolvedComponent(
            component_id=component["id"],
            source_type="cartridge",
            label=f"{commons}/{slug}:{mode_id}" + (f"/{part}" if part else ""),
            identity=identity,
            interfaces=resolve_interfaces(manifest, given, available_parts=available),
            details=details,
        )


# ── standard parts ────────────────────────────────────────────────────────────
def _normalise_parameters(raw: object) -> list[dict]:
    """A standard part's parameters as a manifest-style list of {id, default, min, max…}.

    Tolerant on purpose (ASM-1 §4 fixes the meaning, not yet the exact shape): a list
    of objects with `id`; a mapping id → object; or a mapping id → bare default value.
    """
    if isinstance(raw, list):
        return [dict(p) for p in raw if isinstance(p, Mapping) and isinstance(p.get("id"), str)]
    if isinstance(raw, Mapping):
        out = []
        for pid, spec in raw.items():
            if isinstance(spec, Mapping):
                out.append({**spec, "id": pid})
            else:
                out.append({"id": pid, "default": spec})
        return out
    return []


class StandardPartsResolver:
    """Standard (COTS) parts from a directory of JSON files, one entry per file.

    Every `*.json` beneath the directory that is an object with a string `key` is an
    entry; anything else (a schema, an index) is ignored, so the loader keeps working
    when the real catalog lands beside other files. An entry declares `parameters`
    (optional) and `interfaces` (SEM-1 §2.3 shape; `cdg_interfaces` is accepted too),
    with frame expressions over the part's own parameters. A frame naming no `part`
    sits on the part itself. The identity is the key, the sha256 of the entry's
    canonical JSON (the catalog digest) and the resolved parameter values.
    """

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self._entries: dict[str, dict] | None = None
        self._load_problems: list[str] = []
        self._duplicates: dict[str, list[str]] = {}

    def entries(self) -> dict[str, dict]:
        if self._entries is None:
            entries: dict[str, dict] = {}
            where: dict[str, Path] = {}
            if not self.directory.is_dir():
                self._load_problems.append(f"standard-parts directory {self.directory} not found")
            for path in sorted(self.directory.rglob("*.json")) if self.directory.is_dir() else []:
                try:
                    doc = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(doc, dict) or not isinstance(doc.get("key"), str):
                    continue
                key = doc["key"]
                if key in entries:
                    self._duplicates.setdefault(key, []).append(
                        f"standard part '{key}' is defined twice ({where[key]} and {path})"
                    )
                    continue
                entries[key], where[key] = doc, path
            self._entries = entries
        return self._entries

    def resolve(self, component: Mapping) -> ResolvedComponent:
        source = _source(component)
        key = source.get("key")
        entries = self.entries()
        if key not in entries:
            raise ResolutionError(
                [*self._load_problems, f"standard part {key!r} is not in {self.directory}"]
            )
        if key in self._duplicates:
            # Which of two entries is meant is unknowable; picking one would be a guess.
            raise ResolutionError(self._duplicates[key])
        entry = entries[key]
        parameters = _normalise_parameters(entry.get("parameters"))
        given = source.get("parameters") or {}
        problems = [f"standard part '{key}': {p}"
                    for p in parameter_value_problems(parameters, given)]
        if problems:
            raise ResolutionError(problems)
        interfaces = entry.get("interfaces")
        if interfaces is None:
            interfaces = entry.get("cdg_interfaces")
        manifest = {"parameters": parameters, "hyperobject": {"cdg_interfaces": interfaces or []}}
        values = resolve_parameters(manifest, given)
        identity = {
            "type": "standard",
            "key": key,
            "catalog_sha256": hashlib.sha256(canonical_json(entry)).hexdigest(),
            "parameters": {p["id"]: values.get(p["id"]) for p in parameters},
        }
        return ResolvedComponent(
            component_id=component["id"],
            source_type="standard",
            label=f"standard/{key}",
            identity=identity,
            interfaces=resolve_interfaces(manifest, given, default_part=key),
            details={"catalog_sha256": identity["catalog_sha256"]},
        )


# ── external designs ──────────────────────────────────────────────────────────
class ExternalResolver:
    """A third-party design: its interface facts are declared inline (numbers only).

    No CAD is read. The identity is the declared facts themselves — name, licence, URL,
    revision and interfaces — so changing any stated fact changes the digest.
    """

    def resolve(self, component: Mapping) -> ResolvedComponent:
        source = _source(component)
        facts = {k: v for k, v in source.items() if k != "type"}
        manifest = {"parameters": [], "hyperobject": {"cdg_interfaces": source.get("interfaces")}}
        return ResolvedComponent(
            component_id=component["id"],
            source_type="external",
            label=f"external/{source.get('name', '?')} ({source.get('license', '?')})",
            identity={"type": "external", "facts": facts},
            interfaces=resolve_interfaces(manifest, {}, default_part="external"),
            details={"url": source.get("url")},
        )


# ── dispatch ──────────────────────────────────────────────────────────────────
class CompositeResolver:
    """Dispatch on `source.type` to one resolver per source kind.

    A kind with no resolver configured is a resolution error that says which option
    would supply it (e.g. `--standard-parts`), never a silent skip.
    """

    def __init__(
        self,
        *,
        cartridge: ComponentResolver | None = None,
        standard: ComponentResolver | None = None,
        external: ComponentResolver | None = None,
    ):
        self.by_type: dict[str, ComponentResolver | None] = {
            "cartridge": cartridge,
            "standard": standard,
            "external": external if external is not None else ExternalResolver(),
        }

    @classmethod
    def for_directories(
        cls, commons: str | Path | None = None, standard_parts: str | Path | None = None
    ) -> CompositeResolver:
        return cls(
            cartridge=CommonsManifestResolver(commons) if commons is not None else None,
            standard=StandardPartsResolver(standard_parts) if standard_parts is not None else None,
        )

    def resolve(self, component: Mapping) -> ResolvedComponent:
        kind = _source(component).get("type")
        if kind not in self.by_type:
            raise ResolutionError([f"unknown source type {kind!r}"])
        resolver = self.by_type[kind]
        if resolver is None:
            hint = {"cartridge": "--commons", "standard": "--standard-parts"}.get(kind, "")
            raise ResolutionError(
                [f"no {kind} resolver is configured" + (f" (pass {hint})" if hint else "")]
            )
        return resolver.resolve(component)
