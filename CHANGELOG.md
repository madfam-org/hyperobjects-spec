# Changelog

All notable changes to `hyperobjects-spec` are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**One version, one place.** `pyproject.toml`'s `project.version` is the single source of
truth. Every package in `src/` derives its `__version__` from the installed distribution
metadata (see `src/hyperobjects_version/__init__.py`); none of them types a version
string, and `tests/test_version.py` fails if one starts to.

**On the release history below.** The tag history and `main` are discontinuous, and this
file does not pretend otherwise. `v0.1.0` and `v0.1.1` were published on 2026-08-22 and
are **not ancestors of the current `main`**; the line that `main` descends from begins at
the Commons Soundness v2 work below. Nothing was ever tagged `v0.2.0` or `v0.3.0`, so the
`0.2.0` this repo's packages used to claim and the `0.3.0` `pyproject.toml` declares have
never corresponded to a published release. Everything under **[Unreleased]** is therefore
exactly that: unreleased.

## [Unreleased]

### Added

- **A single version source.** New `hyperobjects_version` package resolves the
  distribution version from `importlib.metadata` and falls back to parsing
  `project.version` out of `pyproject.toml` (stdlib `tomllib`, path resolved relative to
  the module) for an uninstalled source checkout. `bridge_check`, `commons_sandbox`,
  `fc_spec`, `hyperobjects_lexicon`, `hyperobjects_schemas` and `y4d_spec` all derive
  `__version__` from it. `tests/test_version.py` holds every exposed `__version__` to the
  pyproject declaration, checks that the fallback path and the installed path agree, and
  fails if any package reintroduces a literal.
- **This changelog.**
- Four tests pinning full shas across every vendored capture, and coverage of the
  refresh script end to end (#10).
- Determinism tests for the thin-wall sampler (#11).
- `PrintabilityDependencyWarning`: a printability measurement that could not run because
  a package is missing now says so once per process, naming the package and the extra
  that installs it, instead of returning the same `None` a featureless mesh returns (#8).
- **G4 — the unified cross-commons reader.** One lexicon over both catalogs with the
  bridge graph as navigation, built hermetically from vendored snapshots and committed,
  so `fc-spec reader --check` is a fail-closed diff (#6).
- Drawing-vocabulary term wave: style-line, yoke, notch, pleat, vent, facing, godet
  (140 → 147 terms), wiring four capability keys to terms (#6).
- **G3 wave 1.** Corpus 30 → 140 terms, the RFC 0039 §6.2 dictionary tools, the B2
  controlled vocabularies, term contract v2 (`review_status`, `capability` domain), and
  the shared half of G2 article elevation (#4).
- **Commons Soundness v2.** Preset-matrix rendering under `y4d-spec check --render`
  (every declared preset held to the watertight / positive-volume / no-inverted-body
  bar), `y4d_spec.printability` notes for thin walls, unsupported overhangs and build
  volume (notes only, never failures), and the `ho-bridge` handshake that renders an
  FC↔Yantra4D link and perturbs each mapped parameter to prove the geometry moves (#1).

### Changed

- README's three install commands pin `@main` rather than `@v0.3.0`, a tag that has
  never existed and could not resolve; `docs/P1B_ADOPTION.md` no longer describes them as
  pinning a tag (#13).
- CI installs `libxrender1` alongside `libgl1` and `libglib2.0-0`, and the read-proof
  step now **fails the job** when `geometry_available()` is `False` rather than printing
  it and moving on. The geometry lane runs on the runner instead of skipping (#9).
- `scripts/refresh_catalog_snapshot.py` reads through `git show` at a `--ref` and records
  full shas; docstrings and docs brought current with #6–#9 (#10).
- Reader catalog and bridge snapshots re-pinned to yantra4d `f0cdb74e` and
  fashion-cabinet `4feb3ec5`: bridge back edges 299 → 302, unlinked claims 3 → 1 (#7).
- `garment-manifest.schema.json` mirrors catch up with fashion-cabinet:
  `project.attribution.commons_license` is required and the `dxf-aama` export format is
  accepted. Both copies are byte-identical to upstream again (#5).

### Fixed

- Thin-wall thickness sampling is seeded (`THICKNESS_SAMPLE_SEED = 0`), so the
  measurement repeats: the marginal `bodysuit_placket` preset reads 0.7614 mm on every
  call rather than 0.7534–0.8628 mm, and the test asserting the note does not block
  stopped flaking. No threshold moved (#11).
- The `[geometry]` extra declares `rtree`, which `trimesh.proximity.thickness` reaches
  for at its default `method="max_sphere"`. Without it the thin-wall measurement raised
  `ModuleNotFoundError` on every mesh (#8).
- G3 controlled-vocabulary pins record full shas (#8).

## Earlier tagged releases

These predate the current `main` lineage and are listed for completeness. Neither tag is
an ancestor of `main`.

### [0.1.1] - 2026-08-22

#### Fixed

- `y4d_spec`'s distinctness rule compares each rendered body against the fallback body
  rather than pairwise.

### [0.1.0] - 2026-08-22

#### Added

- Initial extraction of the commons bar into an installable package: `fc_spec` and
  `commons_sandbox` ported verbatim from fashion-cabinet, `y4d_spec` authored as the
  Yantra4D twin, the commons schemas bundled, and the cross-commons identity key
  authored.
- The geometry lane hardened against trimesh's silent auto-repair.
- 133 tests and CI; README, the P1b adoption checklist, and the worked identity example.

[Unreleased]: https://github.com/madfam-org/hyperobjects-spec/commits/main
[0.1.1]: https://github.com/madfam-org/hyperobjects-spec/releases/tag/v0.1.1
[0.1.0]: https://github.com/madfam-org/hyperobjects-spec/releases/tag/v0.1.0
