#!/usr/bin/env bash
# Install the geom-core Python wheel (the optional mesh oracle, extra `geometry-core`)
# from its GitHub Release into the interpreter that runs y4d-spec.
#
# Why a script and not an extra: pip extras cannot point at a URL, and geom-core is not
# on PyPI yet (publishing is an owner step). The `geometry-core` extra in pyproject.toml
# is therefore empty and exists to name the seam; this script is the install.
#
# It picks the wheel for the running interpreter and OS, pins it by sha256 (pip checks
# the `#sha256=` fragment), installs it and proves the import. Anything it cannot serve
# (an interpreter or platform the release has no wheel for) is an error that names what
# exists, never a silent skip: a geometry leg that "ran with geom-core" without it would
# report parity it never measured.
#
#   scripts/qa/install_geom_core.sh                 # uses $PYTHON, else python3
#   PYTHON=.venv/bin/python scripts/qa/install_geom_core.sh
#   scripts/qa/install_geom_core.sh --print-url     # resolve only, install nothing
set -euo pipefail

VERSION="0.1.0"
BASE="https://github.com/madfam-org/geom-core/releases/download/v${VERSION}"
PYTHON="${PYTHON:-python3}"

# The v0.1.0 release assets this package can use (requires-python >= 3.11), with the
# sha256 digests GitHub records for them. cp38-cp310 wheels exist too, but no
# hyperobjects-spec interpreter can load them.
#
# The macOS wheel is TAGGED universal2 but its extension is arm64 only (`lipo -info`:
# "Non-fat file ... architecture: arm64"; checked 2026-10-18 on an Intel Mac, where it
# installs and then fails to import). So Intel macOS is refused here, before pip, rather
# than installed broken. Build from source there: `pip install <geom-core checkout>`.
declare_wheel() {
  case "$1" in
    cp311-linux-x86_64)
      echo "geom_core-${VERSION}-cp311-cp311-linux_x86_64.whl 6a286ba8365c98f238eca2fca8008eb3d646586d87e49ce6c6ca8c141c5590e1" ;;
    cp311-darwin-arm64)
      echo "geom_core-${VERSION}-cp311-cp311-macosx_11_0_universal2.whl 871295027cc6c9d1eb2c710a3d46c3bf3ebd0d123deb273b687e1d10ba7fa18a" ;;
    *) return 1 ;;
  esac
}

tag="$("$PYTHON" -c 'import sys; print(f"cp{sys.version_info[0]}{sys.version_info[1]}")')"
os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"
key="${tag}-${os}-${arch}"

if ! entry="$(declare_wheel "$key")"; then
  echo "install_geom_core: geom-core v${VERSION} ships no wheel for ${key}." >&2
  echo "  Wheels usable here: CPython 3.11 on Linux x86_64 and on Apple-silicon macOS" >&2
  echo "  (the macOS 'universal2' wheel holds arm64 only)." >&2
  echo "  Run with PYTHON=<a python3.11>, or build geom-core from source:" >&2
  echo "    git clone https://github.com/madfam-org/geom-core && pip install ./geom-core" >&2
  exit 1
fi

wheel="${entry% *}"
sha="${entry#* }"
url="${BASE}/${wheel}#sha256=${sha}"

if [[ "${1:-}" == "--print-url" ]]; then
  echo "$url"
  exit 0
fi

echo "install_geom_core: ${wheel} for ${key}"
"$PYTHON" -m pip install --no-deps "$url"
"$PYTHON" -c 'import geom_core_py; print("geom_core_py import ok:", geom_core_py.__file__)'
