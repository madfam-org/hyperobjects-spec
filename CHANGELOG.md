# Changelog

Notable changes to `hyperobjects-spec`, newest first. Each lane of a coordinated wave
records its change under its own heading.

## Unreleased

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
