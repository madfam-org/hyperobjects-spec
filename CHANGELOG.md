# Changelog

All notable changes to `hyperobjects-spec` are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Standard-parts catalog (ASM-1 §4)

#### Added

- `standard-part.schema.json` and the `hyperobjects_standard_parts` package: one JSON
  entry per COTS part under `parts/`, a loader, GOC-1 full-injection
  `resolve_parameters` (out of range is an error, never clamped), `interface_frames`
  (evaluated with `y4d_spec.frame_eval`, ASM-1 §1), and `part_digest` (sha256 of the canonical JSON, for the assembly digest).
- Fourteen entries covering ASM-1 §4's minimum set: `nema-17-48mm`, `extrusion-2020`,
  `mgn12-rail`, `mgn12h-carriage`, `bearing-608`, `gt2-pulley-20t-5mm`,
  `psu-meanwell-lrs-200`, `microswitch-d2f`, `motor-2207`, `fpv-frame-5in-x-225`
  (a COTS class, not a copied design), `fc-stack-30x30`, `fpv-camera-micro-19mm`,
  `prop-5in`, `vtx-antenna-sma`. 37 interfaces; 106 dimensions, each citing a source.
- The catalog lane runs as the third verdict of `vocab`
  (`vocab standard-parts: …`; `--standard-parts DIR` checks another directory). It checks
  schema, citations, `size_key` membership, geometry types, frame evaluation at the
  defaults and at every parameter bound, and exact unit, orthogonal axes.
- `interface-sizes.standard-parts.json`, a supplement of `interface-sizes` with eight cited
  draft keys: `tslot-2020-end-tap-m5`, `mgn12-rail`, `bearing-608-bore`, `prop-shaft-m5`,
  `battery-strap-20mm` (provisional), `meanwell-lrs-200-base-m4`,
  `meanwell-lrs-200-side-m4`, `omron-d2f-mount-m2`. The fabrication loader now merges
  `{vocabulary}.{label}.json` supplements.
- Ten draft lexicon terms for the field concepts the AAS projection needs ids for:
  `interface-polarity`, `interface-size-key`, `interface-frame`, `interface-symmetry`,
  `parameter-unit`, `assembly`, `mate`, `assembly-placement`, `standard-part`,
  `external-design-reference`. The reader and the README counts are rebuilt.
- `docs/STANDARD_PARTS.md`.

### Frame evaluator and render-time frame gate (ASM-1 §1, §8)

#### Added

- `y4d_spec.frame_eval`: `evaluate_frame(manifest, interface, params)` returns a
  `Frame(part, origin, normal, x_axis)` with unit vectors and an `x_axis` made exactly
  orthogonal to the normal. Expressions are vetted by the SEM-1 grammar check, then
  walked by hand; nothing is passed to `eval`. Parameters resolve as GOC-1 full
  injection (checkbox 1/0, select option value).
- The render-time frame gate in `y4d-spec check --render` (`y4d_spec.frame_gate`,
  `y4d_spec.frame_geometry`). It runs for every interface with a `frame`, at the
  defaults and at every preset. It uses a planar test for face types and an axis test
  for `socket`, `thread`, `threaded_socket` and `hinge`. Other types are reported as
  UNVERIFIED notes. A mismatch is a failure with residuals. The summary line gains
  `frames=P/M ok, unverified=U, failures=F` only when frames were checked.
- Fixtures `frame-plate` and `frame-plate-wrong`.

#### Unchanged

- A manifest without frames is checked exactly as before, which is every commons
  cartridge today.

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

### Lexicon contract 3 and the fabrication vocabularies (SEM-1 §4)

- **Term contract 3** (additive over 2): optional `exact_match` / `close_match` arrays of
  external identifiers — absolute IRIs, or ECLASS IRDIs as strings (identifiers only, no
  ECLASS content). The lane refuses a contract-3 field without `spec_version: 3` and an
  identifier listed in both arrays. `concept_iri(id)` derives a term's permanent IRI,
  `https://id.madfam.io/concept/{id}`; it is never stored. All 147 shipped terms are
  unchanged.
- **Five fabrication vocabularies** under `hyperobjects_lexicon/vocabularies/fabrication/`
  with a sibling schema, `fabrication-vocabulary.schema.json`: `processes` (7, mapped to
  Cotiza's codes), `material-classes` (22, cross-mapped to the yantra4d and Fashion Cabinet
  material cards and their EMMO classes), `process-parameters` (17 OrcaSlicer keys, each
  pinned to its `PrintConfig.cpp` line), `fabrication-capabilities` (13, machine-side and
  distinct from the garment `capabilities` vocabulary), `interface-sizes` (19, every
  dimension citing a public source). Labels and definitions in es/en/fr/pt, all
  `generated` (drafts) pending native review. `entry_concept_iri(vocabulary, key)` derives
  `https://id.madfam.io/concept/{vocabulary}/{key}`.
- **The fabrication lane** runs on the existing `vocab` command as a second verdict
  (`<tool> vocab fabrication: …`); `--fabrication DIR` checks another set. `--status`
  output is unchanged.
- **Vocabulary-membership rule** (`manifest_vocabulary_problems`): every interface
  `size_key` (including each value of a `{param, map}`), `requirements.process`,
  `requirements.materials.any_of` / `none_of` and `requirements.process_parameters` key —
  at the top level and per part — must resolve. Runs in `y4d-spec check` and
  `fc-spec check garment-manifest`; silent on manifests without the fields (all 502 solid
  and 516 soft manifests on 2026-10-02).
