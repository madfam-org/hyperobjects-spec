"""Skip-vs-require semantics, and one real OpenSCAD render end to end.

The skip/require tests monkeypatch discovery so they run identically on a machine with
OpenSCAD and one without — they are about the DECISION, not the binary. The integration
test needs a real binary and skips cleanly when there is none, which is the state of the
`madfam-runners-blue` CI image today (lane L-G16 is adding OpenSCAD to it; when it lands,
the commons CI turns on `--require-openscad` and an unrendered OpenSCAD lane can no
longer go green).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from y4d_spec.cli import main
from y4d_spec.conformance import check_cartridge
from y4d_spec.geometry import openscad_binary, reset_openscad_probe

FIXTURES = Path(__file__).parent / "fixtures" / "y4d"
SCAD_BLOCK = FIXTURES / "scad-block"

HAVE_OPENSCAD = openscad_binary() is not None
needs_openscad = pytest.mark.skipif(
    not HAVE_OPENSCAD, reason="no OpenSCAD binary on this machine"
)


@pytest.fixture(autouse=True)
def _clean_probe():
    reset_openscad_probe()
    yield
    reset_openscad_probe()


@pytest.fixture
def no_binary(monkeypatch):
    """A machine with no OpenSCAD, whatever the machine actually running this has."""
    monkeypatch.delenv("OPENSCAD", raising=False)
    monkeypatch.delenv("OPENSCAD_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda _n: None)
    monkeypatch.setattr("os.path.isfile", lambda _p: False)
    reset_openscad_probe()


# --- skip is the default ------------------------------------------------------


@pytest.mark.geometry
def test_missing_binary_skips_and_stays_ok(no_binary):
    """A contributor's laptop without OpenSCAD must still be able to check a cartridge:
    the cartridge is not non-conformant because the machine is short a tool."""
    result = check_cartridge(SCAD_BLOCK, render=True)
    assert result.ok
    assert result.problems == []
    assert result.verified_renders == []
    assert result.skipped_renders, "every OpenSCAD target should be recorded as skipped"


@pytest.mark.geometry
def test_a_skip_is_never_counted_as_a_verified_render(no_binary):
    """The whole reason `skipped` exists: a lane that measured nothing must not read
    like one that passed."""
    result = check_cartridge(SCAD_BLOCK, render=True)
    for check in result.skipped_renders:
        assert check.skipped
        assert check.volume is None
        assert "NOT verified" in check.skipped


@pytest.mark.geometry
def test_skip_reason_names_the_source_and_the_remedy(no_binary):
    result = check_cartridge(SCAD_BLOCK, render=True)
    reason = result.skipped_renders[0].skipped
    assert "block.scad" in reason
    assert "--require-openscad" in reason


# --- --require-openscad turns the same absence into a failure -----------------


@pytest.mark.geometry
def test_require_openscad_makes_a_missing_binary_a_failure(no_binary):
    result = check_cartridge(SCAD_BLOCK, render=True, require_openscad=True)
    assert not result.ok
    assert result.problems
    assert any("no OpenSCAD binary" in p for p in result.problems)


@pytest.mark.geometry
def test_require_openscad_records_no_skips(no_binary):
    """Under --require-openscad the unrendered target is a FAILURE, not a skip; leaving
    it in both buckets would let a green-looking `skipped=` count paper over a red run."""
    result = check_cartridge(SCAD_BLOCK, render=True, require_openscad=True)
    assert result.skipped_renders == []


# Marked `geometry`: the flag/argument errors these assert are raised AFTER the
# geometry-extra check in _cmd_check, so on a base install the exit code is still 2
# but the message is the extra's refusal. The siblings above validate BEFORE that
# check and so hold everywhere. Without the marker these went red on any machine
# without [geometry] — a lane the README promises is green.
@pytest.mark.geometry
def test_cli_require_openscad_without_a_binary_exits_2(no_binary, capsys):
    """A usage/environment error, not a conformance verdict — the same exit code
    `--render` without the geometry extra uses."""
    code = main(["check", str(SCAD_BLOCK), "--render", "--require-openscad"])
    assert code == 2
    assert "no OpenSCAD binary found" in capsys.readouterr().out


def test_cli_require_openscad_needs_render(capsys):
    """Silently ignoring it is how a CI job that MEANT to require OpenSCAD passes
    having rendered nothing."""
    code = main(["check", str(SCAD_BLOCK), "--require-openscad"])
    assert code == 2
    assert "only apply with --render" in capsys.readouterr().out


@pytest.mark.geometry
def test_cli_openscad_path_must_be_a_directory(tmp_path, capsys):
    missing = tmp_path / "nope"
    code = main(["check", str(SCAD_BLOCK), "--render", "--openscad-path", str(missing)])
    assert code == 2
    assert "not a directory" in capsys.readouterr().out


# --- the real thing -----------------------------------------------------------


@pytest.mark.geometry
@needs_openscad
def test_renders_the_bundled_openscad_fixture():
    """End to end: manifest -> command line -> subprocess -> STL -> the mesh bar."""
    result = check_cartridge(SCAD_BLOCK, render=True, presets=False)
    assert result.ok, result.problems
    assert result.skipped_renders == []
    assert len(result.verified_renders) == 2  # block, drilled

    for check in result.verified_renders:
        assert check.engine == "openscad"
        assert check.watertight
        assert check.volume > 0
        assert check.bodies == 1


@pytest.mark.geometry
@needs_openscad
def test_parameters_actually_reach_the_script():
    """A 10mm cube is 1000mm³. If `-D` were dropped the number would still be *a*
    number, so assert the exact one the parameter implies."""
    result = check_cartridge(SCAD_BLOCK, render=True, presets=False)
    block = next(c for c in result.verified_renders if c.part == "block")
    assert block.volume == pytest.approx(1000.0, rel=1e-6)


@pytest.mark.geometry
@needs_openscad
def test_render_mode_dispatches_to_a_different_body():
    """The drilled part declares render_mode 2; if the integer never arrived, both
    parts would render the same cube and the fallback-body rule would fire."""
    result = check_cartridge(SCAD_BLOCK, render=True, presets=False)
    volumes = {c.part: c.volume for c in result.verified_renders}
    assert volumes["drilled"] < volumes["block"]


@pytest.mark.geometry
@needs_openscad
def test_presets_render_on_the_openscad_side_too():
    """A preset is the parameter point a user clicks, on either engine. big_block sets
    block_size=20, so 20³ = 8000mm³."""
    result = check_cartridge(SCAD_BLOCK, render=True)
    preset = next(c for c in result.preset_renders if c.preset == "big_block")
    assert preset.ok, preset.problems
    assert preset.volume == pytest.approx(8000.0, rel=1e-6)


@pytest.mark.geometry
@needs_openscad
def test_engine_is_recorded_on_every_render():
    """Without it a dual-engine cartridge prints two indistinguishable lines."""
    result = check_cartridge(SCAD_BLOCK, render=True)
    assert {c.engine for c in result.verified_renders} == {"openscad"}
    assert all("openscad" in c.target for c in result.verified_renders)


@pytest.mark.geometry
@needs_openscad
def test_a_scad_that_produces_nothing_is_a_failure(tmp_path):
    """OpenSCAD exits 0 having written nothing when the top-level object is empty —
    the commonest shape of an unwired target_part. Zero exit is not a render."""
    cart = tmp_path / "empty-cart"
    cart.mkdir()
    (cart / "empty.scad").write_text("// nothing at all\n")

    manifest = json.loads((SCAD_BLOCK / "project.json").read_text(encoding="utf-8"))
    manifest["project"]["slug"] = "empty-cart"
    manifest["modes"] = [
        {
            "id": "block",
            "label": {"en": "Block", "es": "Bloque"},
            "scad_file": "empty.scad",
            "parts": ["block"],
            "estimate": {"base_time": 5, "per_unit": 1, "per_part": 3},
        }
    ]
    manifest["parts"] = [manifest["parts"][0]]
    manifest["presets"] = []
    (cart / "project.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = check_cartridge(cart, render=True)
    assert not result.ok
    # Which branch reports it depends on the build: OpenSCAD 2026.02.13 exits 1 with
    # "Current top level object is empty", while builds that exit 0 having written
    # nothing are caught by the empty-output check. Both are failures and the message
    # says empty either way — asserting the exact branch would pin the test to one
    # OpenSCAD version.
    assert any("empty" in prob for prob in result.problems)


@pytest.mark.geometry
@needs_openscad
def test_a_scad_that_does_not_compile_is_a_failure(tmp_path):
    cart = tmp_path / "broken-cart"
    cart.mkdir()
    (cart / "broken.scad").write_text("this is not OpenSCAD source {{{\n")

    manifest = json.loads((SCAD_BLOCK / "project.json").read_text(encoding="utf-8"))
    manifest["project"]["slug"] = "broken-cart"
    manifest["modes"] = [
        {
            "id": "block",
            "label": {"en": "Block", "es": "Bloque"},
            "scad_file": "broken.scad",
            "parts": ["block"],
            "estimate": {"base_time": 5, "per_unit": 1, "per_part": 3},
        }
    ]
    manifest["parts"] = [manifest["parts"][0]]
    manifest["presets"] = []
    (cart / "project.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = check_cartridge(cart, render=True)
    assert not result.ok
    assert any("render (block, block, openscad)" in prob for prob in result.problems)


@pytest.mark.geometry
@needs_openscad
def test_timeout_is_reported_as_a_failure_not_a_crash():
    """A pathological cartridge must bound the run, and say why it was bounded."""
    from y4d_spec.geometry import render_part_openscad

    check = render_part_openscad(
        SCAD_BLOCK, "block.scad", "block", "block", timeout=0
    )
    assert not check.ok
    assert any("timed out" in p for p in check.problems)


@pytest.mark.geometry
@needs_openscad
def test_cli_verbose_reports_the_openscad_version(capsys):
    """The version is the only thing in the output that can tell an environment
    problem apart from a cartridge failure."""
    main(["check", str(SCAD_BLOCK), "--render", "--no-presets", "-v"])
    assert "openscad:" in capsys.readouterr().out
