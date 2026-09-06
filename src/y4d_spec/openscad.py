"""Rendering a cartridge's OpenSCAD side, exactly as the platform renders it.

Mirrored from yantra4d apps/api/services/engine/openscad.py. The command shape, the
``-D`` value encoding, the backend probe and the OPENSCADPATH construction are that
module's, not inventions here: a cartridge that renders green in this checker and red on
the platform (or the reverse) is worse than no check at all, because it moves the
argument from "is the cartridge broken" to "which tool do we believe".

The mesh that comes back is judged by geometry._judge_stl — the SAME bar the CadQuery
side is judged by, and deliberately not a second copy of it.

Which OpenSCAD, and what has to be installed alongside it, is y4d_spec.render_environment.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .geometry import (
    MACOS_OPENSCAD,
    OPENSCAD_TIMEOUT_S,
    GeometryUnavailable,
    RenderCheck,
    _judge_stl,
    _require_geometry,
    _stl_target,
)

__all__ = [
    "build_openscad_command",
    "openscad_available",
    "openscad_binary",
    "openscad_env",
    "openscad_probe",
    "openscad_version",
    "render_part_openscad",
    "reset_openscad_probe",
]

# Probe results, keyed by binary path. See openscad_probe.
_PROBE_CACHE: dict[str, dict] = {}

# Generated fontconfig documents, keyed by the font dirs they name.
_FONTCONFIG_CACHE: dict[str, str] = {}


def openscad_available() -> bool:
    """True when an OpenSCAD binary can be found on this machine."""
    return openscad_binary() is not None


def openscad_version() -> str | None:
    """The installed OpenSCAD's version banner, or None when there is no binary.

    Reported in ``-v`` output because the version is not a detail: the commons uses
    snapshot syntax no tagged release has, so a machine one release behind reports a
    *cartridge* failure for what is an environment problem. See
    y4d_spec.render_environment for the version the platform pins.
    """
    probe = openscad_probe()
    return probe.get("version") if probe else None


# Mirrored from yantra4d apps/api/services/engine/openscad.py. The command shape,
# the -D value encoding, the backend probe and the OPENSCADPATH construction are
# that module's, not inventions here: a cartridge that renders green in this
# checker and red on the platform (or the reverse) is worse than no check at all.


def openscad_binary() -> str | None:
    """The OpenSCAD to run, or None when this machine has none.

    Three places, in order, because three kinds of machine run this:
      1. ``$OPENSCAD`` — an explicit choice always wins, and is how a CI image with a
         non-standard path or a second version installed says which one it means.
         (The platform's own equivalent is ``OPENSCAD_PATH``, honoured too.)
      2. ``openscad`` on PATH — the Linux/CI case, and what the platform image's
         ``/usr/local/bin/openscad`` symlink produces.
      3. The macOS app bundle — a dev machine that installed the .app has a working
         binary that is on nobody's PATH.
    """
    for var in ("OPENSCAD", "OPENSCAD_PATH"):
        explicit = os.environ.get(var)
        if explicit:
            # An explicit setting that does not resolve is a configuration error worth
            # surfacing, not a reason to quietly fall through to a different binary and
            # report numbers from a version nobody asked for.
            return explicit
    found = shutil.which("openscad")
    if found:
        return found
    if os.path.isfile(MACOS_OPENSCAD) and os.access(MACOS_OPENSCAD, os.X_OK):
        return MACOS_OPENSCAD
    return None


def _probe_openscad(binary: str) -> dict:
    """Version string and --backend support for *binary*.

    Mirrors openscad.py::_probe_openscad_backend: support is decided by reading
    ``--help``, NOT by trying a render. That binary exits 0 for
    ``--backend=NotABackend`` and only mentions the rejection on stderr, so an exit
    code is not evidence the flag was honoured. Presence in the help text is.
    """
    version = None
    try:
        vproc = subprocess.run(  # noqa: S603
            [binary, "--version"], capture_output=True, text=True, timeout=30, check=False
        )
        banner = ((vproc.stdout or "") + (vproc.stderr or "")).strip().splitlines()
        version = banner[0].strip() if banner else None
    except Exception:
        version = None

    supported = False
    try:
        proc = subprocess.run(  # noqa: S603
            [binary, "--help"], capture_output=True, text=True, timeout=30, check=False
        )
        supported = "--backend" in ((proc.stdout or "") + (proc.stderr or ""))
    except Exception:
        supported = False

    return {"binary": binary, "version": version, "backend": supported}


def openscad_probe(binary: str | None = None) -> dict | None:
    """The cached probe for *binary* (default: whatever openscad_binary() finds).

    Cached because a subprocess per render would spend a real fraction of the budget
    on a question whose answer cannot change mid-run — openscad.py caches it for the
    same reason.
    """
    binary = binary or openscad_binary()
    if binary is None:
        return None
    if binary not in _PROBE_CACHE:
        _PROBE_CACHE[binary] = _probe_openscad(binary)
    return _PROBE_CACHE[binary]


def reset_openscad_probe() -> None:
    """Drop the cached probes. For tests and for an $OPENSCAD that changed."""
    _PROBE_CACHE.clear()


def build_openscad_command(
    binary: str,
    output_path: str,
    scad_path: str,
    params: dict,
    render_mode: int = 0,
    *,
    backend: str | None = "Manifold",
    export_format: str | None = "binstl",
) -> list[str]:
    """The platform's command line, byte for byte.

    openscad.py::build_openscad_command, whose encoding rules are load-bearing because
    OpenSCAD's ``-D`` takes *source text*, not a value: ``-D label=hex`` asks for an
    undefined variable named ``hex`` while ``-D label="hex"`` passes the string.

      bool          -> 1 / 0          (OpenSCAD has no bool literal in -D worth relying on)
      int / float   -> str(value)
      str           -> "quoted"
      anything else -> bare if it matches ^[a-zA-Z0-9_]+$, else numeric if it parses,
                       else true/false, else SKIPPED entirely

    Note ``isinstance(value, bool)`` is tested BEFORE the numeric branch: bool is a
    subclass of int in Python, and testing numbers first would encode True as ``True``
    — which OpenSCAD reads as an undefined variable.

    ``render_mode`` is appended only when nonzero, exactly as the platform does; mode 0
    is the script's own default branch and passing it explicitly would differ from what
    the platform sends.

    Two additions the platform does not make, both deliberate:
      * ``--export-format=binstl`` — the platform infers the format from the output
        filename. Naming it makes the export explicit for a checker whose entire
        verdict rests on parsing the file, and binary STL is what ``-o out.stl``
        already produces, so this changes nothing about the geometry.
      * the binary is a parameter rather than Config.OPENSCAD_PATH.
    """
    cmd = [binary, "-o", output_path]

    # Appended after -o/output so the platform's positional contract holds:
    # cmd[0]=binary, cmd[1]="-o", cmd[2]=output, cmd[-1]=scad.
    if backend:
        cmd.append(f"--backend={backend}")
    if export_format:
        cmd.append(f"--export-format={export_format}")

    for key, value in params.items():
        if key == "scad_file":
            continue
        if isinstance(value, bool):
            val_str = "1" if value else "0"
        elif isinstance(value, (int, float)):
            val_str = str(value)
        elif isinstance(value, str):
            val_str = f'"{value}"'
        else:
            str_val = str(value)
            if re.match(r"^[a-zA-Z0-9_]+$", str_val):
                val_str = str_val
            else:
                try:
                    float(str_val)
                    val_str = str_val
                except (TypeError, ValueError):
                    if str_val.lower() in ("true", "false"):
                        val_str = str_val.lower()
                    else:
                        continue
        cmd.extend(["-D", f"{key}={val_str}"])

    if render_mode != 0:
        cmd.extend(["-D", f"render_mode={render_mode}"])

    cmd.append(scad_path)
    return cmd


def openscad_env(scad_path: Path, library_paths: list[Path] | None = None) -> dict:
    """The render environment: OPENSCADPATH, plus fontconfig when fonts are bundled.

    openscad.py::_openscad_env prepends the cartridge's OWN directory to the configured
    OPENSCADPATH, which is what lets a cartridge ``include <helper.scad>`` beside
    itself. The rest of the path is the commons' library roots — ``libs/`` and, once it
    exists, ``commons-lib/`` — supplied by the caller (``--openscad-path``) rather than
    guessed at, because where the libraries live is a property of the checkout and not
    of the spec.

    dotSCAD is special-cased for the same reason the platform special-cases it: its
    modules resolve from ``dotSCAD/src``, not from the repo root, so a bare ``libs/`` on
    the path finds nothing. Adding it when the directory exists costs nothing and saves
    every caller from knowing.
    """
    env = os.environ.copy()

    paths = [str(scad_path.parent)]
    fonts_dirs = []
    for lib in library_paths or []:
        paths.append(str(lib))
        dotscad = Path(lib) / "dotSCAD" / "src"
        if dotscad.is_dir():
            paths.append(str(dotscad))

    # A cartridge's own fonts/ dir must win over a system face of the same name, which
    # is what the platform's generated fontconfig does. Without this a text() cartridge
    # renders in a fallback typeface: watertight, positive-volume, and the wrong shape.
    local_fonts = scad_path.parent / "fonts"
    if local_fonts.is_dir():
        fonts_dirs.append(str(local_fonts))
    if fonts_dirs:
        conf = _fontconfig_file(fonts_dirs)
        if conf:
            env["FONTCONFIG_FILE"] = conf

    env["OPENSCADPATH"] = os.pathsep.join(paths)
    return env


def _fontconfig_file(font_dirs: list[str]) -> str | None:
    """A minimal fontconfig document naming *font_dirs* first, cached per dir set.

    Mirrors openscad.py::fontconfig_xml. Returns None if it cannot be written — a font
    config that could not be created must not take the render down with it.
    """
    key = os.pathsep.join(font_dirs)
    if key in _FONTCONFIG_CACHE:
        return _FONTCONFIG_CACHE[key]
    try:
        dir_tags = "\n".join(f"  <dir>{d}</dir>" for d in font_dirs)
        doc = (
            '<?xml version="1.0"?>\n'
            '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
            "<fontconfig>\n"
            f"{dir_tags}\n"
            '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
            "</fontconfig>\n"
        )
        fd, path = tempfile.mkstemp(suffix=".conf", prefix="fc_y4d_spec_")
        with os.fdopen(fd, "w") as fh:
            fh.write(doc)
    except OSError:
        return None
    _FONTCONFIG_CACHE[key] = path
    return path


def render_part_openscad(
    cartridge_dir: Path,
    scad_file: str,
    mode: str,
    part: str,
    *,
    render_mode: int = 0,
    params: dict | None = None,
    preset: str | None = None,
    printability: bool = False,
    library_paths: list[Path] | None = None,
    timeout: int = OPENSCAD_TIMEOUT_S,
    binary: str | None = None,
    stl_dir: Path | None = None,
) -> RenderCheck:
    """Render one (mode, part) with OpenSCAD and judge the mesh at the same bar.

    ``render_mode`` is the integer the ``.scad`` dispatches on (manifest
    ``parts[].render_mode``); ``target_part`` is additionally passed as a ``-D`` string
    so a cartridge that dispatches on the name rather than the number also lands on the
    right branch. Both are what the platform sends.

    `stl_dir` keeps the rendered STL there rather than in a TemporaryDirectory that
    dies with the call — see geometry._stl_target. The parity pass is why: it compares
    this mesh against the CadQuery side's, and cannot if either is already gone.

    A binary that is absent is the CALLER's problem to classify — this function is only
    reached once one was found — so it raises rather than inventing a skip here, where
    the skip-vs-require decision does not belong.
    """
    binary = binary or openscad_binary()
    if binary is None:
        raise GeometryUnavailable(
            "no OpenSCAD binary found — set $OPENSCAD, put `openscad` on PATH, or "
            "install OpenSCAD.app"
        )
    _require_geometry()  # trimesh, for the mesh bar

    probe = openscad_probe(binary) or {"backend": False, "version": None}
    scad_path = cartridge_dir / scad_file

    call_params = dict(params or {})
    call_params["target_part"] = part

    with _stl_target(stl_dir, "openscad", mode, part, preset) as out:
        cmd = build_openscad_command(
            binary,
            out,
            str(scad_path),
            call_params,
            render_mode,
            backend="Manifold" if probe.get("backend") else None,
        )
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=openscad_env(scad_path, library_paths),
            )
        except subprocess.TimeoutExpired:
            return RenderCheck(
                mode=mode,
                part=part,
                ok=False,
                preset=preset,
                problems=[f"OpenSCAD timed out after {timeout}s"],
            )
        except OSError as exc:
            return RenderCheck(
                mode=mode,
                part=part,
                ok=False,
                preset=preset,
                problems=[f"could not run OpenSCAD ({binary}): {exc}"],
            )

        output = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if proc.returncode != 0:
            if proc.returncode < 0:
                detail = f"killed by signal {-proc.returncode}"
            else:
                detail = f"exited {proc.returncode}"
            return RenderCheck(
                mode=mode,
                part=part,
                ok=False,
                preset=preset,
                problems=[f"OpenSCAD {detail}: {_tail(output)}"],
            )

        # OpenSCAD exits 0 having written nothing when the top-level object is empty —
        # the single most common way an unwired target_part shows up. Silence plus a
        # zero exit is not a render.
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            return RenderCheck(
                mode=mode,
                part=part,
                ok=False,
                preset=preset,
                problems=[
                    "OpenSCAD exited 0 but produced no geometry (empty top-level "
                    f"object): {_tail(output)}"
                ],
            )

        return _judge_stl(
            out,
            mode=mode,
            part=part,
            preset=preset,
            printability=printability,
            engine="openscad",
            keep=stl_dir is not None,
        )


def _tail(text: str, limit: int = 400) -> str:
    """The last *limit* characters of compiler output — the part that says why."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text or "(no output)"
    return "…" + text[-limit:]

