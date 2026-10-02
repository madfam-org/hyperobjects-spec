"""GOC-1 — the Generator Output Contract v1 (``variables.json``), as digests and a check.

A generator instance is the geometry file(s) a render produced plus ONE document that
says exactly which cartridge, mode and part produced them, with which inputs, on which
engine, and the digest of every file. yantra4d writes it next to each artifact as
``<artifact-stem>.variables.json``; Fashion Cabinet ships it as ``variables.json`` inside
a ``format=bundle`` zip. The schema is ``generator-output`` in this package, and this
package is its only home — no platform keeps a copy.

Every producer and every checker must agree on four algorithms, so they live here:

    canonical_json(obj)                 # §3.1 the bytes every digest hashes
    variables_sha256(variables)         # §3.2 identity of the inputs, provenance excluded
    tree_sha256(cartridge_dir)          # §3.3 hyperobjects-tree-v1, the source digest
    instance_id(cartridge=..., ...)     # §3.4 deploy-independent instance identity

and ``check_generator_output(doc, base_dir=None)`` re-derives what a document claims and
reports each disagreement as a finding with a severity. An ``error`` means the document
is not true about itself (schema, a digest that does not recompute, a geometry file whose
bytes differ); a ``warning`` is true and worth saying but not a conformance failure
(``complete: false``, legacy physical inputs, a geometry file that is not present to
check). Both CLIs expose it: ``y4d-spec bundle check`` and
``fc-spec check generator-output``.

Known limitation of ``hyperobjects-tree-v1`` (by design, recorded in the contract): it
digests the cartridge DIRECTORY only. Shared libraries outside it (``libs/*``,
``commons-lib``) are not covered; ``generator.commons.sha`` and ``generator.kernel``
record those.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import load

__all__ = [
    "FORMAT",
    "SCHEMA_NAME",
    "TREE_ALGORITHM",
    "Finding",
    "GeneratorOutputResult",
    "canonical_json",
    "check_generator_output",
    "check_generator_output_file",
    "collect_generator_output_files",
    "instance_id",
    "run_cli_check",
    "tree_sha256",
    "variables_sha256",
]

SCHEMA_NAME = "generator-output"
FORMAT = "hyperobjects.generator-output"
TREE_ALGORITHM = "hyperobjects-tree-v1"

#: §3.3 step 2 — a path with any of these segments is not part of the source tree.
TREE_EXCLUDED_SEGMENTS = frozenset({".git", "__pycache__", "node_modules"})
#: §3.3 step 2 — the commons' non-geometry suffixes (compared lower-cased).
TREE_EXCLUDED_SUFFIXES = frozenset(
    {".md", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf"}
)
#: §3.3 step 2 — the cartridge's root `docs/` directory is documentation, not source.
TREE_EXCLUDED_ROOT_DIR = "docs"

#: The two file names a bundle directory is searched for (`y4d-spec bundle check DIR`).
SIDECAR_SUFFIX = ".variables.json"
BUNDLE_NAME = "variables.json"

ERROR = "error"
WARNING = "warning"


# ── §3 algorithms ─────────────────────────────────────────────────────────────
def canonical_json(obj: object) -> bytes:
    """§3.1 — the canonical UTF-8 bytes of `obj`: sorted keys, no whitespace, no NaN.

    Producers hash exactly what this returns. `allow_nan=False` makes a NaN or an
    infinity a ValueError rather than a non-JSON token two parsers would disagree on.
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pairs(variables: Iterable[Mapping] | Mapping) -> list[list]:
    if isinstance(variables, Mapping):
        items = [(k, v) for k, v in variables.items()]
    else:
        items = [(v["id"], v["value"]) for v in variables]
    items.sort(key=lambda kv: kv[0].encode("utf-8"))
    return [[k, v] for k, v in items]


def variables_sha256(variables: Iterable[Mapping] | Mapping) -> str:
    """§3.2 — sha256 hex of the canonical JSON of `[[id, value], ...]` sorted by id.

    `variables` is the document's `variables` array (each item carries `id` and
    `value`), or a plain `{id: value}` mapping. Only id and value enter the digest:
    provenance (`type`, `source`, `preset_id`, `unit`, `measurement`) is excluded, so
    the identity does not move when only the provenance of a value does. A
    `source_default` entry contributes `null`. Sorting is bytewise on the UTF-8 id.
    """
    return _sha256_hex(canonical_json(_pairs(variables)))


def _tree_files(root: Path) -> list[tuple[str, Path]]:
    """`(relative POSIX path, absolute path)` of every file `hyperobjects-tree-v1` digests."""
    out: list[tuple[str, Path]] = []
    # followlinks=False: a symlinked DIRECTORY is listed in `dirnames` and never entered,
    # so it contributes nothing. A symlinked FILE is listed in `filenames` and read
    # through, which is what "follow file symlinks" means.
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = PurePosixPath(Path(dirpath).relative_to(root).as_posix())
        dirnames[:] = [d for d in dirnames if d not in TREE_EXCLUDED_SEGMENTS]
        if rel_dir.parts[:1] == (TREE_EXCLUDED_ROOT_DIR,):
            dirnames[:] = []
            continue
        for name in filenames:
            rel = PurePosixPath(name) if rel_dir == PurePosixPath(".") else rel_dir / name
            if any(seg in TREE_EXCLUDED_SEGMENTS for seg in rel.parts):
                continue
            if rel.suffix.lower() in TREE_EXCLUDED_SUFFIXES:
                continue
            path = Path(dirpath) / name
            if not path.is_file():  # a broken symlink, a socket: not a regular file
                continue
            out.append((rel.as_posix(), path))
    out.sort(key=lambda item: item[0].encode("utf-8"))
    return out


def tree_sha256(cartridge_dir: str | Path) -> str:
    """§3.3 — `hyperobjects-tree-v1`: the digest of one cartridge directory.

    Every regular file under `cartridge_dir` (file symlinks followed, directory
    symlinks never), except paths with a `.git` / `__pycache__` / `node_modules`
    segment, anything under the cartridge's root `docs/`, and the non-geometry suffixes
    `.md .txt .png .jpg .jpeg .gif .svg .webp .pdf` (lower-cased). For each file one
    line `"<sha256 of its bytes>  <relative POSIX path>\\n"`, sorted bytewise by path,
    concatenated, and hashed. `project.json` is included.
    """
    root = Path(cartridge_dir)
    if not root.is_dir():
        raise NotADirectoryError(f"{root}: not a directory")
    lines = []
    for rel, path in _tree_files(root):
        lines.append(f"{_sha256_hex(path.read_bytes())}  {rel}\n")
    return _sha256_hex("".join(lines).encode("utf-8"))


def instance_id(
    *,
    cartridge: str,
    mode: str,
    part: str | None,
    tree_sha256: str,
    variables_sha256: str,
) -> str:
    """§3.4 — sha256 hex of the canonical JSON of the five identity fields.

    Deploy-independent by design: `platform_build` and `kernel` are not inputs, so the
    same design at the same inputs keeps the same id across deploys. The geometry
    `sha256` is what records the exact bytes a given kernel produced.
    """
    return _sha256_hex(
        canonical_json(
            {
                "cartridge": cartridge,
                "mode": mode,
                "part": part,
                "tree_sha256": tree_sha256,
                "variables_sha256": variables_sha256,
            }
        )
    )


# ── the check ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Finding:
    """One thing the checker found. `severity` is "error" or "warning"."""

    severity: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass
class GeneratorOutputResult:
    """The verdict on one document. Falsey when there is any error; warnings never
    affect `ok`."""

    findings: list[Finding] = field(default_factory=list)
    instance_id: str | None = None

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def __bool__(self) -> bool:
        return self.ok


def _schema_findings(doc: object) -> list[Finding]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise RuntimeError("jsonschema is required (pip install hyperobjects-spec)") from exc
    validator = Draft202012Validator(load(SCHEMA_NAME))
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(Finding(ERROR, "schema", f"{where}: {err.message}"))
    return out


def _well_formed_variables(doc: dict) -> list[dict] | None:
    """The `variables` array if every item has a string id and a value, else None —
    the schema findings already say why; recomputing from garbage would only add noise."""
    variables = doc.get("variables")
    if not isinstance(variables, list):
        return None
    for v in variables:
        if not isinstance(v, dict) or not isinstance(v.get("id"), str) or "value" not in v:
            return None
    return variables


def _variable_findings(doc: dict, variables: list[dict]) -> list[Finding]:
    out: list[Finding] = []
    ids = [v["id"] for v in variables]
    keys = [i.encode("utf-8") for i in ids]
    if keys != sorted(keys):
        out.append(
            Finding(
                ERROR,
                "variables-order",
                "variables are not sorted by id (bytewise); producers must emit them "
                "sorted so the document reads the same as its digest",
            )
        )
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        out.append(
            Finding(ERROR, "variables-duplicate", f"duplicate variable id(s): {', '.join(dupes)}")
        )

    try:
        recomputed = variables_sha256(variables)
    except (TypeError, ValueError) as exc:
        out.append(Finding(ERROR, "variables_sha256", f"cannot canonicalise variables: {exc}"))
        recomputed = None
    declared = doc.get("variables_sha256")
    if recomputed is not None and declared != recomputed:
        out.append(
            Finding(
                ERROR,
                "variables_sha256",
                f"declared {declared!r} but the variables recompute to {recomputed}",
            )
        )

    # §3.5: complete == no variable is a source_default.
    expected_complete = not any(v.get("source") == "source_default" for v in variables)
    complete = doc.get("complete")
    if isinstance(complete, bool) and complete != expected_complete:
        out.append(
            Finding(
                ERROR,
                "complete",
                f"complete is {str(complete).lower()} but "
                + (
                    "no variable is a source_default"
                    if expected_complete
                    else "some variables are source_default (not injected)"
                ),
            )
        )
    return out


def _instance_finding(doc: dict) -> tuple[str | None, list[Finding]]:
    gen = doc.get("generator")
    if not isinstance(gen, dict):
        return None, []
    source = gen.get("source") if isinstance(gen.get("source"), dict) else {}
    cartridge, mode = gen.get("cartridge"), gen.get("mode")
    tree, vsha = source.get("tree_sha256"), doc.get("variables_sha256")
    part = gen.get("part")
    if not all(isinstance(x, str) for x in (cartridge, mode, tree, vsha)):
        return None, []
    if part is not None and not isinstance(part, str):
        return None, []
    # Recomputed from the DECLARED variables_sha256, so a wrong variables digest and a
    # wrong instance_id are reported as the two independent faults they are.
    recomputed = instance_id(
        cartridge=cartridge, mode=mode, part=part, tree_sha256=tree, variables_sha256=vsha
    )
    declared = doc.get("instance_id")
    if declared != recomputed:
        return recomputed, [
            Finding(
                ERROR,
                "instance_id",
                f"declared {declared!r} but cartridge/mode/part/tree_sha256/"
                f"variables_sha256 recompute to {recomputed}",
            )
        ]
    return recomputed, []


def _geometry_findings(doc: dict, base_dir: Path) -> list[Finding]:
    out: list[Finding] = []
    geometry = doc.get("geometry")
    if not isinstance(geometry, list):
        return out
    for i, entry in enumerate(geometry):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            continue
        rel = entry["path"]
        posix = PurePosixPath(rel)
        if posix.is_absolute() or ".." in posix.parts or "\\" in rel:
            out.append(
                Finding(
                    ERROR,
                    "geometry-path",
                    f"geometry[{i}].path {rel!r} must be relative to the document's "
                    f"directory and stay inside it",
                )
            )
            continue
        path = base_dir / Path(*posix.parts)
        if not path.is_file():
            out.append(
                Finding(
                    WARNING,
                    "geometry-missing",
                    f"geometry[{i}] {rel}: not present under {base_dir} — its sha256 and "
                    f"size were NOT verified",
                )
            )
            continue
        data = path.read_bytes()
        if isinstance(entry.get("bytes"), int) and len(data) != entry["bytes"]:
            out.append(
                Finding(
                    ERROR,
                    "geometry-bytes",
                    f"geometry[{i}] {rel}: declared {entry['bytes']} bytes, file has {len(data)}",
                )
            )
        actual = _sha256_hex(data)
        if entry.get("sha256") != actual:
            out.append(
                Finding(
                    ERROR,
                    "geometry-sha256",
                    f"geometry[{i}] {rel}: declared sha256 {entry.get('sha256')!r}, "
                    f"file hashes to {actual}",
                )
            )
    return out


def check_generator_output(
    doc: object, base_dir: str | Path | None = None
) -> GeneratorOutputResult:
    """Check one parsed GOC-1 document. Nothing short-circuits: every finding at once.

    Errors: schema violations; `variables` not sorted by id (or a duplicate id); a
    `variables_sha256` or `instance_id` that does not recompute; `complete` that
    contradicts the variables (§3.5); and — only when `base_dir` is given and the file
    is there — a geometry file whose size or sha256 differs, or a geometry path that is
    absolute or escapes `base_dir`.

    Warnings: `complete: false` (some parameters were not injected — the instance is
    not reproducible from `variables` alone), `legacy_physical_inputs` present
    (physical values a platform still injects behind a legacy flag), and a geometry
    file missing under `base_dir` (its digest could not be verified).
    """
    result = GeneratorOutputResult()
    result.findings.extend(_schema_findings(doc))
    if not isinstance(doc, dict):
        return result

    variables = _well_formed_variables(doc)
    if variables is not None:
        result.findings.extend(_variable_findings(doc, variables))

    result.instance_id, inst = _instance_finding(doc)
    result.findings.extend(inst)

    if base_dir is not None:
        result.findings.extend(_geometry_findings(doc, Path(base_dir)))

    if doc.get("complete") is False:
        result.findings.append(
            Finding(
                WARNING,
                "incomplete",
                "complete is false: at least one parameter was not injected "
                "(source_default), so the geometry depends on a source literal "
                "variables does not record",
            )
        )
    if "legacy_physical_inputs" in doc:
        keys = doc["legacy_physical_inputs"]
        names = ", ".join(sorted(keys)) if isinstance(keys, dict) else "?"
        result.findings.append(
            Finding(
                WARNING,
                "legacy-physical-inputs",
                f"legacy_physical_inputs present ({names}): physical settings belong to "
                f"the semantic layer, not the generator (deprecated)",
            )
        )
    return result


def check_generator_output_file(path: str | Path) -> GeneratorOutputResult:
    """Read and check one document; its own directory is the geometry `base_dir`.

    Raises OSError / ValueError (json.JSONDecodeError) when the file cannot be read.
    """
    p = Path(path)
    doc = json.loads(p.read_text(encoding="utf-8"))
    return check_generator_output(doc, base_dir=p.parent)


def collect_generator_output_files(paths: Iterable[str | Path]) -> list[Path]:
    """Expand CLI arguments: a file stays itself; a directory becomes every
    `*.variables.json` and `variables.json` beneath it, sorted. Order is preserved
    across arguments and a file named twice is checked once."""
    out: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        p = Path(raw)
        found = (
            sorted(
                q
                for q in p.rglob("*.json")
                if q.is_file() and (q.name == BUNDLE_NAME or q.name.endswith(SIDECAR_SUFFIX))
            )
            if p.is_dir()
            else [p]
        )
        for q in found:
            key = q.resolve()
            if key not in seen:
                seen.add(key)
                out.append(q)
    return out


def run_cli_check(paths: Iterable[str | Path], prog: str) -> int:
    """The shared body of `y4d-spec bundle check` and `fc-spec check generator-output`.

    Prints `ok` / `FAIL` / `warn` lines and a read-proof summary. Exit 0 when no file
    has an error (warnings never fail), 1 on any error or unreadable file, 2 when the
    arguments resolve to zero documents — checking nothing is a usage error, not a pass.
    """
    args = list(paths)
    files = collect_generator_output_files(args)
    missing = [a for a in args if not Path(a).exists()]
    for a in missing:
        print(f"  ERROR {a}: no such file or directory")
    if missing:
        return 2
    if not files:
        print(f"  ERROR {' '.join(str(a) for a in args)}: no *.variables.json or "
              f"variables.json found")
        print(f"{prog} files=0 failures=0 warnings=0")
        return 2

    failures = 0
    warnings = 0
    for f in files:
        try:
            result = check_generator_output_file(f)
        except (OSError, ValueError) as exc:
            print(f"  ERROR {f}: cannot read — {exc}")
            failures += 1
            continue
        if result.ok:
            ident = f"instance {result.instance_id}" if result.instance_id else "generator-output"
            print(f"  ok {f} ({ident})")
        else:
            failures += 1
            for finding in result.errors:
                print(f"  FAIL {f}: {finding}")
        for finding in result.warnings:
            warnings += 1
            print(f"  warn {f}: {finding}")

    print(f"{prog} files={len(files)} failures={failures} warnings={warnings}")
    return 1 if failures else 0
