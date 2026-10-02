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
