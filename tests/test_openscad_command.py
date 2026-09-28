"""The OpenSCAD command line must be the PLATFORM's, argument for argument.

Every expected string in this file was copied from yantra4d
apps/api/services/engine/openscad.py::build_openscad_command rather than derived from
our own implementation — a test written against the code it tests proves only that the
code is self-consistent, and self-consistency is exactly what a mirrored contract does
not need. The encoding rules are load-bearing because OpenSCAD's `-D` takes SOURCE
TEXT, not a value: `-D label=hex` asks for an undefined variable named `hex`, while
`-D label="hex"` passes a string.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from y4d_spec.geometry import (
    MACOS_OPENSCAD,
    build_openscad_command,
    mode_sources,
    openscad_binary,
    openscad_env,
    openscad_probe,
    part_render_modes,
    reset_openscad_probe,
)

BIN = "/usr/local/bin/openscad"
OUT = "/tmp/out.stl"
SCAD = "/cartridge/main.scad"


def _dvalues(cmd: list[str]) -> list[str]:
    """The `-D` payloads, in order."""
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-D"]


# --- the encoding rules -------------------------------------------------------


def test_numbers_are_bare():
    cmd = build_openscad_command(BIN, OUT, SCAD, {"grid_x": 2, "wall": 1.2})
    assert _dvalues(cmd) == ["grid_x=2", "wall=1.2"]


def test_bools_become_one_and_zero():
    """1/0, never True/False — OpenSCAD reads `True` as an undefined variable."""
    cmd = build_openscad_command(BIN, OUT, SCAD, {"on": True, "off": False})
    assert _dvalues(cmd) == ["on=1", "off=0"]


def test_bool_is_tested_before_number():
    """bool subclasses int in Python; a numeric-first branch would emit `on=True`."""
    cmd = build_openscad_command(BIN, OUT, SCAD, {"on": True})
    assert _dvalues(cmd) == ["on=1"]
    assert "on=True" not in " ".join(cmd)


def test_strings_are_quoted():
    cmd = build_openscad_command(BIN, OUT, SCAD, {"label": "hex"})
    assert _dvalues(cmd) == ['label="hex"']


def test_non_scalar_alphanumeric_passes_bare():
    """openscad.py's fallback branch: ^[a-zA-Z0-9_]+$ goes through unquoted."""

    class Token:
        def __str__(self):
            return "some_token"

    cmd = build_openscad_command(BIN, OUT, SCAD, {"k": Token()})
    assert _dvalues(cmd) == ["k=some_token"]


def test_non_scalar_numeric_string_passes_bare():
    class Numeric:
        def __str__(self):
            return "-2.5"

    cmd = build_openscad_command(BIN, OUT, SCAD, {"k": Numeric()})
    assert _dvalues(cmd) == ["k=-2.5"]


def test_non_scalar_alphanumeric_truthy_word_passes_bare_not_lowercased():
    """`TRUE` matches ^[a-zA-Z0-9_]+$, so the platform emits it BEFORE the
    lower-casing branch is ever reached. Asserted because the obvious expectation
    (`true`) is the wrong one, and a mirror that "fixed" it would diverge."""

    class Word:
        def __str__(self):
            return "TRUE"

    cmd = build_openscad_command(BIN, OUT, SCAD, {"k": Word()})
    assert _dvalues(cmd) == ["k=TRUE"]


@pytest.mark.parametrize("text", ["True ", "True!", "TRUE.", "false-"])
def test_non_scalar_truthy_word_with_punctuation_is_dropped(text):
    """openscad.py's `str_val.lower() in ("true","false")` branch is UNREACHABLE, and
    this mirror reproduces that rather than repairing it.

    Any string that spells a boolean exactly ("true", "TRUE") already matched
    ^[a-zA-Z0-9_]+$ and left bare on the branch above; anything that does NOT match
    that pattern carries a character which also makes `.lower()` unequal to "true" or
    "false", so the comparison fails and the value is skipped. Repairing it here would
    make this checker accept a `-D` the platform silently drops — the two would then
    render different geometry from the same manifest, which is the one outcome a
    mirrored contract exists to prevent. Recorded as a test so the dead branch is a
    known property rather than a latent surprise.
    """

    class Word:
        def __str__(self):
            return text

    cmd = build_openscad_command(BIN, OUT, SCAD, {"good": 1, "k": Word()})
    assert _dvalues(cmd) == ["good=1"]


def test_unencodable_value_is_skipped_entirely():
    """openscad.py drops a value it cannot encode rather than emitting broken source."""

    class Junk:
        def __str__(self):
            return "not a value!"

    cmd = build_openscad_command(BIN, OUT, SCAD, {"good": 1, "bad": Junk()})
    assert _dvalues(cmd) == ["good=1"]


def test_scad_file_key_is_never_passed():
    """openscad.py skips it: it is a manifest field, not a script parameter."""
    cmd = build_openscad_command(BIN, OUT, SCAD, {"scad_file": "main.scad", "a": 1})
    assert _dvalues(cmd) == ["a=1"]


# --- render_mode --------------------------------------------------------------


def test_render_mode_appended_when_nonzero():
    cmd = build_openscad_command(BIN, OUT, SCAD, {"a": 1}, 3)
    assert _dvalues(cmd) == ["a=1", "render_mode=3"]


def test_render_mode_zero_is_not_sent():
    """Mode 0 is the script's own default branch; the platform sends nothing."""
    cmd = build_openscad_command(BIN, OUT, SCAD, {"a": 1}, 0)
    assert _dvalues(cmd) == ["a=1"]


# --- positional contract ------------------------------------------------------


def test_positional_contract_holds():
    """openscad.py's own documented invariant: binary, -o, output, ..., scad."""
    cmd = build_openscad_command(BIN, OUT, SCAD, {"a": 1}, 2)
    assert cmd[0] == BIN
    assert cmd[1] == "-o"
    assert cmd[2] == OUT
    assert cmd[-1] == SCAD


def test_backend_flag_follows_output():
    cmd = build_openscad_command(BIN, OUT, SCAD, {}, backend="Manifold")
    assert cmd[:4] == [BIN, "-o", OUT, "--backend=Manifold"]


def test_backend_omitted_when_unsupported():
    """A binary with no --backend must not be handed the flag: every render would abort."""
    cmd = build_openscad_command(BIN, OUT, SCAD, {}, backend=None)
    assert not any(a.startswith("--backend") for a in cmd)


def test_export_format_is_binstl():
    cmd = build_openscad_command(BIN, OUT, SCAD, {})
    assert "--export-format=binstl" in cmd


def test_full_command_matches_the_platform_shape():
    """One end-to-end assertion of the whole line, as the sweep harness documents it:
    `-o out.stl --backend=Manifold -D k=v ... file.scad`."""
    cmd = build_openscad_command(
        BIN, OUT, SCAD, {"n": 2, "flag": True, "label": "hex", "f": 1.5}, 4
    )
    assert cmd == [
        BIN,
        "-o",
        OUT,
        "--backend=Manifold",
        "--export-format=binstl",
        "-D",
        "n=2",
        "-D",
        "flag=1",
        "-D",
        'label="hex"',
        "-D",
        "f=1.5",
        "-D",
        "render_mode=4",
        SCAD,
    ]


# --- OPENSCADPATH -------------------------------------------------------------


def test_env_prepends_the_cartridge_directory(tmp_path):
    """_openscad_env's rule — it is what lets a cartridge `include <helper.scad>`."""
    scad = tmp_path / "cart" / "main.scad"
    scad.parent.mkdir()
    scad.write_text("cube(1);")
    env = openscad_env(scad, [])
    assert env["OPENSCADPATH"].split(os.pathsep)[0] == str(scad.parent)


def test_env_appends_library_roots_in_order(tmp_path):
    scad = tmp_path / "cart" / "main.scad"
    scad.parent.mkdir()
    scad.write_text("cube(1);")
    libs = tmp_path / "libs"
    commons = tmp_path / "commons-lib"
    libs.mkdir()
    commons.mkdir()
    env = openscad_env(scad, [libs, commons])
    assert env["OPENSCADPATH"].split(os.pathsep) == [
        str(scad.parent),
        str(libs),
        str(commons),
    ]


def test_env_adds_dotscad_src_when_present(tmp_path):
    """dotSCAD's modules resolve from dotSCAD/src, so a bare libs/ finds nothing."""
    scad = tmp_path / "cart" / "main.scad"
    scad.parent.mkdir()
    scad.write_text("cube(1);")
    libs = tmp_path / "libs"
    (libs / "dotSCAD" / "src").mkdir(parents=True)
    env = openscad_env(scad, [libs])
    assert str(libs / "dotSCAD" / "src") in env["OPENSCADPATH"].split(os.pathsep)


def test_env_sets_fontconfig_only_when_fonts_are_bundled(tmp_path):
    scad = tmp_path / "cart" / "main.scad"
    scad.parent.mkdir()
    scad.write_text("cube(1);")
    assert "FONTCONFIG_FILE" not in openscad_env(scad, [])

    (scad.parent / "fonts").mkdir()
    env = openscad_env(scad, [])
    conf = env.get("FONTCONFIG_FILE")
    assert conf and Path(conf).is_file()
    assert str(scad.parent / "fonts") in Path(conf).read_text()


# --- binary discovery ---------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_probe():
    reset_openscad_probe()
    yield
    reset_openscad_probe()


def test_openscad_env_var_wins(monkeypatch):
    monkeypatch.setenv("OPENSCAD", "/custom/openscad")
    monkeypatch.setattr("shutil.which", lambda _n: "/usr/bin/openscad")
    assert openscad_binary() == "/custom/openscad"


def test_openscad_path_var_is_honoured(monkeypatch):
    """The platform's own variable name, so an image configured for it just works."""
    monkeypatch.delenv("OPENSCAD", raising=False)
    monkeypatch.setenv("OPENSCAD_PATH", "/opt/openscad")
    monkeypatch.setattr("shutil.which", lambda _n: "/usr/bin/openscad")
    assert openscad_binary() == "/opt/openscad"


def test_path_lookup_is_next(monkeypatch):
    monkeypatch.delenv("OPENSCAD", raising=False)
    monkeypatch.delenv("OPENSCAD_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda _n: "/usr/bin/openscad")
    assert openscad_binary() == "/usr/bin/openscad"


def test_macos_app_bundle_is_the_last_resort(monkeypatch):
    monkeypatch.delenv("OPENSCAD", raising=False)
    monkeypatch.delenv("OPENSCAD_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda _n: None)
    monkeypatch.setattr("os.path.isfile", lambda p: p == MACOS_OPENSCAD)
    monkeypatch.setattr("os.access", lambda p, _m: p == MACOS_OPENSCAD)
    assert openscad_binary() == MACOS_OPENSCAD


def test_no_binary_anywhere_is_none(monkeypatch):
    monkeypatch.delenv("OPENSCAD", raising=False)
    monkeypatch.delenv("OPENSCAD_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda _n: None)
    monkeypatch.setattr("os.path.isfile", lambda _p: False)
    assert openscad_binary() is None


def test_probe_reads_help_not_an_exit_code(monkeypatch):
    """openscad.py's documented reason: the binary exits 0 for --backend=NotABackend."""
    import subprocess as sp

    class Result:
        def __init__(self, out):
            self.stdout = out
            self.stderr = ""
            self.returncode = 1  # nonzero on purpose — the TEXT is what matters

    def fake_run(cmd, **_kw):
        if "--version" in cmd:
            return Result("OpenSCAD version 2026.02.01")
        return Result("  --backend arg   3D rendering backend to use")

    monkeypatch.setattr(sp, "run", fake_run)
    probe = openscad_probe("/fake/openscad")
    assert probe["backend"] is True
    assert probe["version"] == "OpenSCAD version 2026.02.01"


def test_probe_reports_no_backend_when_help_lacks_it(monkeypatch):
    import subprocess as sp

    class Result:
        stdout = "usage: openscad [options] file.scad"
        stderr = ""
        returncode = 0

    monkeypatch.setattr(sp, "run", lambda *_a, **_kw: Result())
    assert openscad_probe("/fake/openscad")["backend"] is False


def test_probe_survives_a_binary_that_will_not_run(monkeypatch):
    """A failed probe must degrade to 'no backend', never raise into the render path."""
    import subprocess as sp

    def boom(*_a, **_kw):
        raise OSError("no such file")

    monkeypatch.setattr(sp, "run", boom)
    probe = openscad_probe("/fake/openscad")
    assert probe == {"binary": "/fake/openscad", "version": None, "backend": False}


# --- manifest enumeration -----------------------------------------------------


def test_mode_sources_returns_both_for_dual_engine():
    """The G31 case: the side the platform does not pick is the one that ships broken."""
    assert mode_sources({"id": "m", "scad_file": "a.scad", "cq_file": "a.py"}) == [
        ("cadquery", "a.py"),
        ("openscad", "a.scad"),
    ]


def test_mode_sources_openscad_only():
    assert mode_sources({"id": "m", "scad_file": "a.scad"}) == [("openscad", "a.scad")]


def test_mode_sources_cadquery_only_declared_in_scad_file():
    """A CadQuery-only cartridge that never had a .scad still uses the legacy field."""
    assert mode_sources({"id": "m", "scad_file": "main.py", "cq_file": "main.py"}) == [
        ("cadquery", "main.py")
    ]


def test_mode_sources_recognises_a_graph_document():
    """WAS: `== []`, asserted as intended behaviour, and it is how the commons' two
    graph cartridges came to sit outside the bar the other 498 clear.

    A `.graph.json` is a renderable source: the vendored platform transpiler compiles it
    to CadQuery and the CadQuery path judges the result. The engine label is `graph`
    (not `cadquery`) because a report has to say which of a cartridge's sources produced
    a mesh, and because the golden-twin comparison is defined between the two labels.
    """
    assert mode_sources({"id": "m", "scad_file": "flange.graph.json"}) == [
        ("graph", "flange.graph.json")
    ]


def test_mode_sources_still_ignores_a_suffix_nothing_renders():
    """The fall-through branch survives — a `.json` that is not a graph is not a source,
    and neither is anything else the three engines do not read."""
    assert mode_sources({"id": "m", "scad_file": "notes.json"}) == []
    assert mode_sources({"id": "m", "scad_file": "readme.md"}) == []


def test_part_render_modes_defaults_to_zero():
    manifest = {"parts": [{"id": "a", "render_mode": 3}, {"id": "b"}]}
    assert part_render_modes(manifest) == {"a": 3, "b": 0}


def test_part_render_modes_rejects_non_integers():
    """A bool or a string is not a render_mode; 0 means the script's default branch."""
    manifest = {"parts": [{"id": "a", "render_mode": True}, {"id": "b", "render_mode": "2"}]}
    assert part_render_modes(manifest) == {"a": 0, "b": 0}
