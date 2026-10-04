"""The ``aas`` subcommand, shared by both console scripts.

    y4d-spec aas build <cartridge-dir | assembly-dir | assembly.json> [...] [--commons solid|soft]
                       [--commons-dir DIR] [--standard-parts DIR] [--out F | --out-dir D]
    y4d-spec aas build-material <material.json> [...] [--out F | --out-dir D]
    y4d-spec aas check <env.json> [...] [--basyx auto|require|off]

``fc-spec aas …`` is the same command with ``--commons soft`` as its default. ``build``
writes canonical JSON (GOC-1 §3.1): the same input gives byte-identical output. Every
environment it builds is also checked (schema + MADFAM rules) before it is written, and
the conformance decision of every submodel is printed, so a build that would publish an
invalid or over-claiming environment fails here, visibly.

An input that is an assembly (a directory holding ``assembly.json``, or that file itself)
is checked by the keystone validator first (ASM-1 §3) and projected only if it passes
(ASM-1 §5): its cartridges are read from ``--commons-dir`` (default: the commons root two
levels above ``assemblies/<slug>/``) and its standard parts from ``--standard-parts``
(default: the catalog bundled with this package). A failing assembly is a check error,
printed with the validator's findings. ``aas check`` reads an assembly environment like
any other, plus the assembly rules (its document decodes, validates and states the
shell's digest).

Exit codes: 0 every file built/checked clean; 1 a check error; 2 a usage or read error.
With a single input and no ``--out``/``--out-dir``, the JSON goes to stdout and every
report line to stderr.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hyperobjects_schemas.generator_output import canonical_json

from .check import check_environment, check_environment_file

__all__ = ["add_aas_parser", "run_aas"]


def add_aas_parser(sub, prog: str, default_commons: str) -> None:
    p = sub.add_parser(
        "aas", help="project cartridges and material cards to AAS v3.1 environments (SEM-1)"
    )
    aas_sub = p.add_subparsers(dest="aas_cmd", required=True)

    b = aas_sub.add_parser("build", help="one AAS Environment per cartridge directory")
    b.add_argument("cartridges", nargs="+", help="cartridge director(ies) with a project.json")
    b.add_argument("--commons", choices=("solid", "soft"), default=default_commons,
                   help=f"which commons the cartridges belong to (default {default_commons})")
    b.add_argument("--commons-dir", metavar="DIR",
                   help="assemblies only: the solid commons checkout holding the cartridges "
                        "(default: two levels above assemblies/<slug>/)")
    b.add_argument("--standard-parts", metavar="DIR",
                   help="assemblies only: a standard-parts directory (default: the bundled "
                        "catalog)")
    _add_outputs(b)

    m = aas_sub.add_parser("build-material", help="one AAS Environment per material card")
    m.add_argument("cards", nargs="+", help="material.json file(s) (yantra4d or Fashion Cabinet)")
    _add_outputs(m)

    c = aas_sub.add_parser("check", help="check AAS Environment JSON file(s)")
    c.add_argument("files", nargs="+", help="environment JSON file(s)")
    c.add_argument("--basyx", choices=("auto", "require", "off"), default="auto",
                   help="BaSyx SDK round-trip: run when installed (auto), fail when not "
                        "installed (require), or skip (off)")
    p.set_defaults(func=lambda args: run_aas(args, prog))


def _add_outputs(parser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--out", metavar="FILE", help="write the environment here (one input)")
    group.add_argument("--out-dir", metavar="DIR", help="write <slug>.aas.json files here")


def _report(line: str, to_stderr: bool) -> None:
    print(line, file=sys.stderr if to_stderr else sys.stdout)


def _emit(env: dict, slug: str, args) -> None:
    data = canonical_json(env)
    if args.out:
        Path(args.out).write_bytes(data)
    elif args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{slug}.aas.json").write_bytes(data)
    else:
        sys.stdout.write(data.decode("utf-8") + "\n")


def _build(args, prog: str, inputs: list[str], make, noun: str) -> int:
    if len(inputs) > 1 and not args.out_dir:
        print(f"  ERROR {len(inputs)} inputs need --out-dir (--out takes one input)",
              file=sys.stderr)
        return 2
    to_stderr = not (args.out or args.out_dir)
    built = errors = read_errors = submodels = idta_claims = 0
    for item in inputs:
        try:
            slug, env, conformance = make(item)
        except _AssemblyFailed as exc:
            for finding in exc.findings:
                _report(f"  FAIL {finding}", to_stderr)
            _report(f"  ERROR {item}: the assembly did not pass its check; nothing projected",
                    to_stderr)
            errors += 1
            continue
        except (OSError, ValueError) as exc:
            _report(f"  ERROR {item}: cannot build — {exc}", to_stderr)
            read_errors += 1
            continue
        result = check_environment(env, basyx="off")
        for finding in result.findings:
            _report(f"  {finding}", to_stderr)
        if not result.ok:
            errors += 1
            continue
        _emit(env, slug, args)
        built += 1
        submodels += len(env.get("submodels") or [])
        claims = [f"{c.submodel}={c.claimed}" for c in conformance]
        idta_claims += sum(c.claimed == "idta" for c in conformance)
        if len(inputs) == 1:
            _report(f"  ok {item} -> {slug}: " + " ".join(claims), to_stderr)
    _report(
        f"{prog} aas {noun}: inputs={len(inputs)} built={built} submodels={submodels} "
        f"idta_claims={idta_claims} check_errors={errors} read_errors={read_errors}",
        to_stderr,
    )
    if read_errors:
        return 2
    return 1 if errors else 0


class _AssemblyFailed(Exception):
    """An assembly input failed the keystone validator: a check error (exit 1)."""

    def __init__(self, findings):
        super().__init__("the assembly did not pass its check")
        self.findings = list(findings)


def _assembly_file(path: Path) -> Path | None:
    if path.is_dir() and (path / "assembly.json").is_file():
        return path / "assembly.json"
    if path.is_file() and path.suffix == ".json" and path.name != "project.json":
        return path
    return None


def _make_assembly(file: Path, args):
    from y4d_spec.assembly import CompositeResolver, validate_assembly

    from .assembly import AssemblyProjectionError, project_assembly
    from .common import build_environment
    from .resolver import bundled_standard_parts_dir

    doc = json.loads(file.read_text(encoding="utf-8"))
    commons = Path(args.commons_dir) if args.commons_dir else file.resolve().parent.parent.parent
    parts = Path(args.standard_parts) if args.standard_parts else Path(bundled_standard_parts_dir())
    for option, value in (("--commons-dir", commons), ("--standard-parts", parts)):
        if not value.is_dir():
            raise ValueError(f"{option} {value}: not a directory")
    report = validate_assembly(doc, CompositeResolver.for_directories(commons, parts))
    if not report.ok:
        raise _AssemblyFailed(report.errors)
    try:
        proj = project_assembly(doc, report)
    except AssemblyProjectionError as exc:
        raise ValueError(f"{file}: {exc}") from None
    return proj.slug, build_environment(proj), proj.conformance


def _make_cartridge(commons: str, args=None):
    def make(path: str):
        from .common import build_environment
        from .soft import project_soft
        from .solid import project_solid

        root = Path(path)
        assembly = _assembly_file(root) if args is not None else None
        if assembly is not None:
            return _make_assembly(assembly, args)
        if not (root / "project.json").is_file():
            raise ValueError(f"no project.json (nor assembly.json) in {root}")
        proj = (project_solid if commons == "solid" else project_soft)(root)
        return proj.slug, build_environment(proj), proj.conformance
    return make


def _make_material(path: str):
    from .material import project_material

    proj = project_material(path)
    return proj.slug, proj.environment(), proj.conformance


def _check(args, prog: str) -> int:
    errors = warnings = read_errors = 0
    states = set()
    for f in args.files:
        try:
            result = check_environment_file(f, basyx=args.basyx)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ERROR {f}: cannot read — {exc}")
            read_errors += 1
            continue
        states.add(result.basyx)
        for finding in result.findings:
            print(f"  {f}: {finding}")
        errors += len(result.errors)
        warnings += len(result.warnings)
        if result.ok:
            print(f"  ok {f} (schema=aas-3.1.2 madfam=ok basyx={result.basyx})")
    basyx = ",".join(sorted(states)) or "skipped"
    if "not installed" in states:
        basyx += ' (pip install "hyperobjects-spec[aas-verify]")'
    print(f"{prog} aas check: files={len(args.files)} errors={errors} warnings={warnings} "
          f"read_errors={read_errors} basyx={basyx}")
    if read_errors:
        return 2
    return 1 if errors else 0


def run_aas(args, prog: str) -> int:
    if args.aas_cmd == "build":
        return _build(args, prog, args.cartridges, _make_cartridge(args.commons, args), "build")
    if args.aas_cmd == "build-material":
        return _build(args, prog, args.cards, _make_material, "build-material")
    if args.aas_cmd == "check":
        return _check(args, prog)
    raise AssertionError(args.aas_cmd)
