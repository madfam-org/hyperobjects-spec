"""`y4d-spec license-body` and `fc-spec license-body`: the body check over any tree.

`y4d-spec check` judges the LICENSE files a cartridge directory ships. A commons'
ROOT licence belongs to no cartridge, and fc-spec checks manifest files rather than
directories, so neither sees it; solid-hyperobjects' root LICENSE carried the wrong
body for exactly that reason. This command takes files or directories, finds every
``LICENSE*`` / ``COPYING*`` beneath them, and prints one verdict per file.

Exit 0 whatever it finds (note-first), 2 on a missing path or when nothing was found:
checking nothing is a usage error, not a pass.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .body import LicenseBodyVerdict, classify_license_file, summary_clause

__all__ = ["add_license_body_parser", "collect_license_files", "declared_for", "run_cli"]

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__"}


def _is_license_name(name: str) -> bool:
    return name.upper().startswith(("LICENSE", "LICENCE", "COPYING"))


def collect_license_files(paths: Iterable[str | Path]) -> list[Path]:
    """A file is taken as given; a directory yields every licence-named file beneath
    it (``LICENSE*``, ``LICENCE*``, ``COPYING*``), skipping VCS and dependency trees."""
    out: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if _SKIP_DIRS.intersection(f.relative_to(p).parts):
                    continue
                if f.is_file() and _is_license_name(f.name):
                    out.append(f)
    return out


def declared_for(path: Path, default: str | None) -> str | None:
    """The licence a file is judged against: the ``hyperobject.commons_license`` of a
    ``project.json`` beside it (the file is a cartridge's), else `default`."""
    manifest = path.parent / "project.json"
    if manifest.is_file():
        try:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = None
        ho = doc.get("hyperobject") if isinstance(doc, dict) else None
        lic = ho.get("commons_license") if isinstance(ho, dict) else None
        if isinstance(lic, str) and lic:
            return lic
    return default


def _describe(v: LicenseBodyVerdict) -> str:
    what = f"{v.kind} {v.license}"
    if v.variants:
        what += f", {len(v.variants)} documented variant(s)"
    return what


def run_cli(paths: Iterable[str | Path], declared: str | None, prog: str) -> int:
    args = list(paths)
    missing = [a for a in args if not Path(a).exists()]
    for a in missing:
        print(f"  ERROR {a}: no such file or directory")
    if missing:
        return 2
    files = collect_license_files(args)
    if not files:
        print(f"  ERROR {' '.join(str(a) for a in args)}: no LICENSE*/COPYING* file found")
        print(f"{prog} {summary_clause([])}")
        return 2

    verdicts: list[LicenseBodyVerdict] = []
    for f in files:
        try:
            v = classify_license_file(f, declared_for(f, declared))
        except OSError as exc:
            print(f"  ERROR {f}: cannot read — {exc}")
            return 2
        verdicts.append(v)
        if v.clean:
            print(f"  ok {f} ({_describe(v)})")
        for note in v.notes():
            print(f"  note {note}")
    print(f"{prog} {summary_clause(verdicts)}")
    return 0


def add_license_body_parser(sub, prog: str) -> None:
    """Register `<prog> license-body` on an argparse subparsers object. The summary
    line reads `<prog> licence-body: files=N canonical=C notices=S mismatched=M
    unjudged=U`."""
    p = sub.add_parser(
        "license-body",
        help="compare shipped LICENSE/COPYING bodies with the canonical SPDX texts "
        "(notes only; exit 0 whatever is found)",
    )
    p.add_argument("paths", nargs="+", help="licence file(s), or director(ies) to search")
    p.add_argument(
        "--declared",
        metavar="SPDX_ID",
        default=None,
        help="the licence a file is judged against when no project.json beside it "
        "declares hyperobject.commons_license (e.g. CERN-OHL-W-2.0 for a commons root)",
    )
    p.set_defaults(func=lambda args: run_cli(args.paths, args.declared, prog))
