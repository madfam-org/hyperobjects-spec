# Changelog

All notable changes to `hyperobjects-spec` are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Manifest semantic fields (SEM-1 §2–§3)

#### Fixed

- `project-manifest.schema.json`: `hyperobject`, `materials`, `source` and
  `estimate_constants` were defined at the schema root, where JSON Schema ignores them.
  They now sit under `properties` and are applied. As a result,
  `hyperobject.cdg_interfaces` is validated for the first time.
- `parts` was required but not defined. It is now defined as
  `{id, label|name, render_mode?, color?, default_color?, glass?}`.
- `i18nString` declares `fr` and `pt`, following the quadrilingual ruling in RFC 0039.
- Two relaxations keep all 502 solid manifests valid, with no commons content changed:
  - `material_awareness` accepts a bare `true` (2 cartridges);
  - `materials[]` accepts `label` and `density_g_cm3` as alternative spellings
    (1 cartridge, 3 entries).

#### Added

- `parameters[].unit` (`mm`, `deg`, `count`, `ratio`, `percent`) in both the project
  and garment manifests.
- `cdg_interfaces[]` gains `frame`, `polarity`, `size_key` and `symmetry`.
  - `frame` is `{part, origin, normal, x_axis?}`. Each component is a number or an
    expression.
  - The schema requires `frame.x_axis` when `symmetry` is not 0.
- A top-level `requirements` profile with per-part overrides, in both manifests.
- `y4d_spec.semantic_rules`, which provides `interface_frame_rules` and
  `requirements_rules`. Both are wired into `check` and listed by `y4d-spec rules`.
  Vocabulary membership is out of scope here; the lexicon rule owns it.
