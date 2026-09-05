"""The render environment, as data: what a machine needs installed to render this commons.

RFC 0040 / Commons Topology P2 (G33). Three places have to agree about the render
environment, and until now each carried its own copy of the answer:

  * the **platform image** — yantra4d `apps/api/Dockerfile`, which installs OpenSCAD and
    the shared libraries its headless renders link against,
  * the **commons CI** — the workflows in solid-hyperobjects / soft-hyperobjects that run
    ``y4d-spec check --render`` over every cartridge,
  * the **CI runner image** — the self-hosted runner that has to carry the same OpenSCAD
    before ``--require-openscad`` can be turned on.

Three copies of a version number is three chances to drift, and the drift is invisible
in the direction that matters: a runner one OpenSCAD release behind renders a cartridge
that uses newer syntax as a *failure*, and a runner one release ahead renders geometry
the platform cannot reproduce. Neither reads as an environment problem in the log; both
read as the cartridge being broken.

So the spec — the thing all four repos already pin by SHA — owns the answer, and the
others read it:

    y4d-spec render-env --apt               # the apt-get install line
    y4d-spec render-env --openscad-version  # 2026.02.01
    y4d-spec render-env --openscad-sha256   # the AppImage checksum to verify
    y4d-spec render-env --json              # all of it, for a provisioning script

Provenance for every constant below is the platform Dockerfile at
``apps/api/Dockerfile``; each is annotated with the line it mirrors. When the platform
moves, this module is what moves with it, and the SHA pin in the consuming repos is
what makes the move deliberate rather than silent.
"""

from __future__ import annotations

import json

__all__ = [
    "APT_PACKAGES",
    "CI_EXTRA_APT_PACKAGES",
    "OPENSCAD_VERSION",
    "OPENSCAD_SHA256",
    "OPENSCAD_APPIMAGE_URL",
    "OPENSCAD_APPIMAGE_URL_TEMPLATE",
    "FONTS_POLICY",
    "FONT_LICENSES",
    "environment",
    "apt_install_line",
]

#: The runtime packages the platform image installs so a headless OpenSCAD render works.
#:
#: Mirrors the single ``apt-get install`` in yantra4d ``apps/api/Dockerfile`` (the block
#: under "Install OpenSCAD snapshot"), MINUS ``wget``, which is a build-only tool used to
#: fetch the AppImage and is not needed by a machine that already has the binary.
#:
#: Why each is here, since a list of sonames invites well-meaning pruning:
#:   libgl1, libglu1-mesa, libegl1  — the GL stack the AppImage's Qt/OpenCSG links against.
#:                                    OpenSCAD needs them even for ``-o out.stl``, which
#:                                    draws nothing: the binary resolves them at load.
#:   libwayland-client0             — Qt's platform plugin resolves it at load on Debian.
#:   libharfbuzz0b                  — text shaping; a ``text()`` cartridge is unrenderable
#:                                    without it.
#:   fonts-liberation, fontconfig   — the fallback typefaces and the cache that finds
#:                                    them (see FONTS_POLICY).
#:   libcomerr2, libgpg-error0      — transitive loads the extracted AppImage asks for.
#:   xvfb                           — the virtual framebuffer. Not needed by the STL path
#:                                    today, but the image ships it and a PNG/preview
#:                                    render does need it; an environment that omits it is
#:                                    not the platform's.
APT_PACKAGES = (
    "fonts-liberation",
    "fontconfig",
    "libgl1",
    "libglu1-mesa",
    "libharfbuzz0b",
    "libegl1",
    "libwayland-client0",
    "libcomerr2",
    "libgpg-error0",
    "xvfb",
)

#: Packages a CI machine needs ON TOP of APT_PACKAGES, and the platform image does not.
#:
#: These belong to the OTHER engine: the ``[geometry]`` extra pulls OCP (OpenCascade),
#: whose C extension links against libXrender and libglib. The platform's API image does
#: not install them because it does not import OCP — the CadQuery renders happen in a
#: different image. Kept separate from APT_PACKAGES rather than merged, because the two
#: lists answer different questions and a merged list would misreport the platform's.
#:
#: Provenance: ``.github/workflows/ci.yml`` in this repo, whose read-proof step found
#: ``ImportError: libXrender.so.1`` on a runner that had libgl1 and nothing in the libgl1
#: dependency tree pulls libxrender1 in.
CI_EXTRA_APT_PACKAGES = (
    "libglib2.0-0",
    "libxrender1",
)

#: The OpenSCAD snapshot the platform renders with.
#:
#: A snapshot, not a release: the commons uses syntax (Gridfinity's extended forms among
#: them) that no tagged release has yet. Mirrors ``ARG OPENSCAD_VERSION`` in the platform
#: Dockerfile.
#:
#: 2026-09-05, ruling G31 — bumped 2026.02.01 -> 2026.02.13. 2026.02.01 CANNOT RENDER the
#: platform's pinned BOSL2 v2.0.753 (``fcfce7c7``). Two lines are enough::
#:
#:     include <BOSL2/std.scad>
#:     cube([1,1,1], anchor=[-1,-1,-1]);
#:
#: aborts with ``Assertion '(is_list($tags_shown) || ($tags_shown == "ALL"))' failed in
#: libs/BOSL2/attachments.scad, line 3809`` and an empty top-level object — i.e. every
#: *anchored* BOSL2 primitive, which is most of the library. The same file renders a
#: 1443-byte STL under 2026.02.13. The floor is therefore the library, not taste: BOSL2
#: v2.0.753 requires a snapshot newer than 2026.02.01, so this value may be bumped
#: forward but must never go back below 2026.02.13 while that BOSL2 pin stands.
OPENSCAD_VERSION = "2026.02.13"

#: SHA-256 of the x86_64 AppImage for OPENSCAD_VERSION. Mirrors ``ARG OPENSCAD_SHA256``.
#:
#: Snapshot URLs are not immutable the way a release tag is, so a provisioning script that
#: downloads without checking this is trusting whatever the mirror serves today. The
#: platform Dockerfile pipes it through ``sha256sum -c -``; so should anything else.
OPENSCAD_SHA256 = "01e4bdeb00518b20ba00d5acc1d3df9c62813d9f64bb68a1fd0a546c7e46ab28"

#: Where the AppImage comes from. ``{version}`` and ``{arch}`` are the substitutions.
OPENSCAD_APPIMAGE_URL_TEMPLATE = (
    "https://files.openscad.org/snapshots/OpenSCAD-{version}-{arch}.AppImage"
)

#: The concrete URL for the pinned version on the architecture the platform builds for.
OPENSCAD_APPIMAGE_URL = OPENSCAD_APPIMAGE_URL_TEMPLATE.format(
    version=OPENSCAD_VERSION, arch="x86_64"
)

#: The licences a cartridge may ship a font under. Both are redistributable with
#: attribution and neither restricts commercial or derivative use — the two properties a
#: commons cartridge that anyone may fork actually needs.
FONT_LICENSES = ("OFL-1.1", "CC0-1.0")

FONTS_POLICY = """\
Fonts in the commons.

A cartridge MAY bundle typefaces in its own `fonts/` directory, and only under OFL-1.1
or CC0-1.0. Both are redistributable with attribution and neither restricts commercial
or derivative use, which is the bar a cartridge anyone may fork has to clear. Any other
licence — including "free for personal use" and every foundry EULA — makes the cartridge
undistributable, and it is the commons that ships it, not the person who downloaded the
font. Name each bundled face and its licence in the cartridge's NOTICE.

The platform installs them system-wide at image build time:

    find /app/projects /app/private-projects -path '*/fonts/*.ttf' -exec cp {} DEST \\;
    find /app/projects /app/private-projects -path '*/fonts/*.otf' -exec cp {} DEST \\;
    fc-cache -f DEST

so `.ttf` and `.otf` are the two extensions that reach a render. A render environment
that copies fonts and does NOT run `fc-cache` has installed nothing fontconfig can find:
a `text()` cartridge then renders in the fallback face and the geometry is wrong in a way
no mesh check can see — it is watertight, positive-volume, and the wrong shape. At render
time the platform additionally points FONTCONFIG_FILE at a generated config naming the
cartridge's own `fonts/` dir first, so a bundled face wins over a system one of the same
name (yantra4d services/engine/openscad.py::_openscad_env).\
"""


def environment() -> dict:
    """The whole contract as a plain dict — what ``render-env --json`` prints."""
    return {
        "apt_packages": list(APT_PACKAGES),
        "ci_extra_apt_packages": list(CI_EXTRA_APT_PACKAGES),
        "openscad_version": OPENSCAD_VERSION,
        "openscad_sha256": OPENSCAD_SHA256,
        "openscad_appimage_url": OPENSCAD_APPIMAGE_URL,
        "openscad_appimage_url_template": OPENSCAD_APPIMAGE_URL_TEMPLATE,
        "font_licenses": list(FONT_LICENSES),
        "fonts_policy": FONTS_POLICY,
    }


def apt_install_line(*, ci: bool = False) -> str:
    """The packages, space-separated, ready to paste after ``apt-get install -y``."""
    packages = list(APT_PACKAGES)
    if ci:
        packages += list(CI_EXTRA_APT_PACKAGES)
    return " ".join(packages)


def render_env_report(*, as_json: bool = False) -> str:
    """The human-readable form: every constant with the reason it is pinned."""
    if as_json:
        return json.dumps(environment(), indent=2, sort_keys=True)

    lines = [
        "The render environment this commons is verified against.",
        "Source of truth: hyperobjects-spec (y4d_spec.render_environment), mirroring",
        "yantra4d apps/api/Dockerfile. Consumers pin this repo by SHA.",
        "",
        f"OpenSCAD version : {OPENSCAD_VERSION}  (snapshot, not a release)",
        f"AppImage sha256  : {OPENSCAD_SHA256}",
        f"AppImage URL     : {OPENSCAD_APPIMAGE_URL}",
        "",
        "apt packages (runtime, mirrors the platform image):",
        f"  {apt_install_line()}",
        "",
        "apt packages a CI machine also needs (the [geometry] extra's OCP kernel):",
        f"  {' '.join(CI_EXTRA_APT_PACKAGES)}",
        "",
        FONTS_POLICY,
    ]
    return "\n".join(lines)
