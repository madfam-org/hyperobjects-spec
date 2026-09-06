"""The render-environment contract (G33) and its CLI.

The point of these tests is not that the constants have the values they have — that is
tautological — but that the SHAPE consumers depend on holds: `--apt` emits something a
shell can paste after `apt-get install -y`, `--json` parses, the SHA is a real sha256,
and the fonts policy actually names the two licences it claims to allow. A provisioning
script reads these outputs; a change that breaks their shape breaks a CI image, not a
test.
"""

from __future__ import annotations

import json
import re

import pytest

from y4d_spec import render_environment as env
from y4d_spec.cli import main


def test_apt_packages_are_a_tuple_of_plain_names():
    assert isinstance(env.APT_PACKAGES, tuple)
    assert env.APT_PACKAGES
    for pkg in env.APT_PACKAGES:
        # Debian package names: no spaces, no shell metacharacters. These land on an
        # `apt-get install` line unquoted.
        assert re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", pkg), pkg


def test_wget_is_not_a_runtime_package():
    """The Dockerfile installs it to FETCH the AppImage. A machine that already has
    the binary does not need it, and shipping build-only tools in a runtime contract
    is how the contract stops describing the runtime."""
    assert "wget" not in env.APT_PACKAGES


def test_ci_extras_are_disjoint_from_the_platform_list():
    """They answer different questions — the platform image's needs vs the CAD
    kernel's — and a name in both would misreport one of them."""
    assert not set(env.APT_PACKAGES) & set(env.CI_EXTRA_APT_PACKAGES)


def test_ci_extras_carry_the_soname_that_actually_broke_ci():
    """libxrender1 is not in the libgl1 dependency tree; nothing pulls it in, so it
    has to be named. See .github/workflows/ci.yml's read-proof step."""
    assert "libxrender1" in env.CI_EXTRA_APT_PACKAGES


def test_apt_packages_carry_the_two_the_runner_image_was_missing():
    """libcomerr2 and libgpg-error0 are transitive loads the EXTRACTED AppImage asks
    for, and nothing else in the list pulls them in.

    They are in this contract because the runner image did not have them: the
    render-environment drift check added to the runner's image lane (enclii #520,
    2026-09-06) compares that image's apt layers against APT_PACKAGES as a subset and
    found exactly these two missing. A contract the consumer silently under-installs
    is not a contract, so name them here — a well-meaning prune of "sonames nobody
    recognizes" is the failure mode this test exists to stop.
    """
    assert "libcomerr2" in env.APT_PACKAGES
    assert "libgpg-error0" in env.APT_PACKAGES


def test_the_gl_stack_openscad_resolves_at_load_is_named():
    """OpenSCAD links its Qt/OpenCSG GL stack at LOAD, so `-o out.stl` — which draws
    nothing — still needs them. Dropping one turns every OpenSCAD render into a
    launch failure that reads nothing like a missing library."""
    for pkg in ("libgl1", "libglu1-mesa", "libegl1"):
        assert pkg in env.APT_PACKAGES, pkg


def test_fontconfig_and_a_fallback_face_are_both_present():
    """FONTS_POLICY says an environment that copies fonts without running fc-cache has
    installed nothing fontconfig can find — which needs fontconfig installed, and a
    fallback face for the text() cartridges that bundle none."""
    assert "fontconfig" in env.APT_PACKAGES
    assert "fonts-liberation" in env.APT_PACKAGES


def test_openscad_sha256_is_a_sha256():
    assert re.fullmatch(r"[0-9a-f]{64}", env.OPENSCAD_SHA256)


def test_openscad_version_is_a_snapshot_date():
    assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", env.OPENSCAD_VERSION)


def test_openscad_version_is_at_or_above_the_bosl2_floor():
    """BOSL2 v2.0.753 (fcfce7c7) does not render under snapshots older than 2026.02.13.

    2026.02.01 aborts on every *anchored* primitive with
    ``Assertion '(is_list($tags_shown) || ($tags_shown == "ALL"))' failed in
    libs/BOSL2/attachments.scad, line 3809``, leaving an empty top-level object —
    an empty STL, not a build error, which is how it reached CI unnoticed
    (yantra4d PR #125, ruling G31).

    Snapshot versions are ``YYYY.MM.DD``, so the string comparison IS the date
    comparison. Bumping forward is fine; going back below the floor is not, while
    the BOSL2 pin stands.
    """
    assert env.OPENSCAD_VERSION >= "2026.02.13"


def test_appimage_url_is_built_from_the_pinned_version():
    assert env.OPENSCAD_VERSION in env.OPENSCAD_APPIMAGE_URL
    assert env.OPENSCAD_APPIMAGE_URL.startswith("https://")
    assert env.OPENSCAD_APPIMAGE_URL.endswith(".AppImage")


def test_appimage_url_template_takes_version_and_arch():
    built = env.OPENSCAD_APPIMAGE_URL_TEMPLATE.format(version="1970.01.01", arch="aarch64")
    assert "1970.01.01" in built and "aarch64" in built


def test_fonts_policy_names_both_permitted_licences():
    for licence in env.FONT_LICENSES:
        assert licence in env.FONTS_POLICY


def test_fonts_policy_requires_fc_cache():
    """Copying fonts without it installs nothing fontconfig can find, and a text()
    cartridge then renders watertight, positive-volume, and the wrong shape."""
    assert "fc-cache" in env.FONTS_POLICY


def test_fonts_policy_names_the_extensions_the_platform_copies():
    assert ".ttf" in env.FONTS_POLICY
    assert ".otf" in env.FONTS_POLICY


def test_environment_dict_round_trips_through_json():
    assert json.loads(json.dumps(env.environment())) == env.environment()


def test_apt_install_line_is_space_separated():
    assert env.apt_install_line() == " ".join(env.APT_PACKAGES)


def test_apt_install_line_ci_appends_the_extras():
    line = env.apt_install_line(ci=True).split()
    assert line == list(env.APT_PACKAGES) + list(env.CI_EXTRA_APT_PACKAGES)


# --- the CLI ------------------------------------------------------------------


def test_cli_apt_prints_one_pasteable_line(capsys):
    assert main(["render-env", "--apt"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.splitlines() == [out]  # exactly one line
    assert out.split() == list(env.APT_PACKAGES)


def test_cli_apt_ci(capsys):
    assert main(["render-env", "--apt", "--ci"]) == 0
    out = capsys.readouterr().out.split()
    assert out == list(env.APT_PACKAGES) + list(env.CI_EXTRA_APT_PACKAGES)


def test_cli_openscad_version_prints_only_the_version(capsys):
    assert main(["render-env", "--openscad-version"]) == 0
    assert capsys.readouterr().out.strip() == env.OPENSCAD_VERSION


def test_cli_openscad_sha256_prints_only_the_hash(capsys):
    """Shaped so `echo "$(... --openscad-sha256)  file" | sha256sum -c -` works."""
    assert main(["render-env", "--openscad-sha256"]) == 0
    assert capsys.readouterr().out.strip() == env.OPENSCAD_SHA256


def test_cli_json_parses_and_carries_every_field(capsys):
    assert main(["render-env", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["openscad_version"] == env.OPENSCAD_VERSION
    assert doc["openscad_sha256"] == env.OPENSCAD_SHA256
    assert doc["apt_packages"] == list(env.APT_PACKAGES)
    assert doc["openscad_appimage_url"] == env.OPENSCAD_APPIMAGE_URL
    assert doc["font_licenses"] == list(env.FONT_LICENSES)


def test_cli_default_report_is_human_readable(capsys):
    assert main(["render-env"]) == 0
    out = capsys.readouterr().out
    assert env.OPENSCAD_VERSION in out
    assert env.OPENSCAD_SHA256 in out
    assert "fc-cache" in out


@pytest.mark.parametrize("flag", ["--apt", "--openscad-version", "--openscad-sha256"])
def test_cli_single_field_forms_emit_exactly_one_line(capsys, flag):
    assert main(["render-env", flag]) == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 1
