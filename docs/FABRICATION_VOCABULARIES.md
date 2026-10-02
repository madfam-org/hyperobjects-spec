# The fabrication vocabularies (SEM-1 §4)

> Public reference data. Every fact here cites a public standard, a manufacturer page or a
> public source file; see [PUBLIC_REPO_BOUNDARY.md](PUBLIC_REPO_BOUNDARY.md).

A manifest can now say how it must be made (`requirements`) and how its interfaces mate
(`size_key`). The **keys** those fields write live in five reference vocabularies, shipped
in `src/hyperobjects_lexicon/vocabularies/fabrication/` and validated by
`src/hyperobjects_schemas/schemas/fabrication-vocabulary.schema.json`.

| Vocabulary | What a key names | Where a manifest writes it |
|---|---|---|
| `processes` | a manufacturing process (`fff`, `sla`, `sls`, `mjf`, `cnc_3axis`, `cnc_router`, `laser_2d`) | `requirements.process`; a machine's `process` capability |
| `material-classes` | a class of material (`pla`, `tpu-95a`, `pa12`, …; and the six fabric classes) | `requirements.materials.any_of` / `none_of` |
| `process-parameters` | an OrcaSlicer setting a requirement bounds (`wall_loops`, `sparse_infill_density`, …) | the keys of `requirements.process_parameters` |
| `fabrication-capabilities` | what a producer **machine** declares (`build_volume_x_mm`, `enclosure`, `connectivity`, …) | a machine-model declaration |
| `interface-sizes` | a standard part or pattern two interfaces mate through (`nema-17-face`, `stack-30.5x30.5-m3`, …) | an interface's `size_key` |

## Why a sibling schema

`commons-vocabulary.schema.json` describes a **reading of a corpus**: keys the two commons
already write, how many cartridges write them, a one-line English gloss, and a pointer at
a lexicon term for the four languages. None of that fits here. No manifest writes these
keys yet, so there is nothing to count; their outside worlds already fixed their spelling
(OrcaSlicer's `snake_case`, `tpu-95a`, the dotted pitch in `stack-30.5x30.5-m3`); and each
entry needs its own quadrilingual label and definition plus cited facts. So the family has
its own schema and its own verdict on the same `vocab` command.

## An entry

```jsonc
{
  "key": "motor-mount-16x16-m3",
  "label":      { "en": "Motor mount 16×16 M3", "es": "Montaje de motor 16×16 M3", "fr": "…", "pt": "…" },
  "definition": { "en": "Four M3 holes on a 16 mm square, …", "es": "…", "fr": "…", "pt": "…" },
  "review_status": { "state": "generated" },
  "geometry_type": "bolt_pattern",                       // an `interfaces` geometry_type key
  "dimensions": {
    "hole_spacing": { "value": 16, "unit": "mm", "source": 0 },   // index into sources
    "thread":       { "value": "M3", "unit": "thread", "source": 0 }
  },
  "sources": [{ "title": "…", "url": "https://…", "publisher": "…", "accessed": "2026-10-02",
                "supports": "bolt pattern M3 (16 × 16 mm) on a 22xx-class motor" }],
  "notes": "…"
}
```

Common fields: `key`, `label`, `definition`, `review_status` (required); `status`
(`canonical` | `provisional`), `term` (a lexicon term id), `exact_match` / `close_match`
(external IRIs or ECLASS IRDIs), `sources`, `notes`. Per vocabulary:

- **processes** — `family` (`additive` | `subtractive` | `cutting`), `iso_52900_category`,
  `cotiza_code` (`3d_fff`, `3d_sla`, `cnc_3axis`, `laser_2d`; absent where Cotiza cannot
  quote the process yet — `sls`, `mjf`, `cnc_router` — rather than borrowing the nearest).
- **material-classes** — `kind` (`filament` | `resin` | `powder` | `sheet` | `fabric`),
  `processes`, `cards` (`'<repo>/<slug>'`, resolved against the bundled catalog snapshot;
  one card, one class), `emmo_class` (copied from the cards, never asserted on its own).
- **process-parameters** — `unit`, `value_type`, `processes`, and an `orcaslicer` binding:
  the key, its `ConfigOption` type, the preset that carries it (`print` | `filament` |
  `printer` | `placeholder`), and the revision, path and line of its definition.
- **fabrication-capabilities** — `value_type`, `unit`, `allowed_values`,
  `value_vocabulary`. Never shares a key with the garment `capabilities` vocabulary.
- **interface-sizes** — `geometry_type` and `dimensions`, each citing a source by index.

## The citation rules

1. A dimension is a fact and carries the index of the source that states it. Prose is
   never copied from a datasheet; numbers are.
2. A source is a public URL. A standard that is not freely published (NEMA ICS 16,
   ISO 15) is named in `notes`, and the numbers cite a manufacturer drawing that applies
   it.
3. A value nobody publishes is not written. `gopro-3-prong` states only its M5 × 0.8
   thumbscrew; finger width and gap are left out and the entry is `provisional` until a
   frame is verified against a physical mount.
4. A derived number says so (`gt2-pulley-20t-5mm` pitch diameter: teeth × pitch / π).
5. OrcaSlicer keys are verified against `src/libslic3r/PrintConfig.cpp` at a pinned
   revision. `bed_temperature` is OrcaSlicer's custom-G-code **placeholder**, not a stored
   setting; the stored keys are per plate type (`hot_plate_temp`, `textured_plate_temp`,
   `cool_plate_temp`, `eng_plate_temp`) and ship alongside it.

## The membership rule

`hyperobjects_lexicon.manifest_vocabulary_problems(doc)` returns every fabrication key a
manifest writes that no vocabulary defines. It reads:

- each `size_key` under `hyperobject.cdg_interfaces` (solid) or `hyperobject.interfaces`
  (soft) — a literal key, or every value of a `{"param": …, "map": {…}}`;
- `requirements.process` (a list or a single string);
- `requirements.materials.any_of` and `none_of`;
- the keys of `requirements.process_parameters`;
- the same three requirement fields under each `requirements.parts.<part id>`.

It runs inside `y4d-spec check` (with the other manifest rules) and inside
`fc-spec check garment-manifest`, and its findings start with `fabrication vocabulary:`.
It reads defensively: an absent field contributes nothing, and a field present in a shape
it cannot read is reported rather than skipped. Structure validation of these fields is
the manifest schemas' job; this rule only asks whether each key exists.

**False-positive analysis (house rule: a new rule is a failure only once this is
written down).** Run over every manifest at the commons' `origin/main` on 2026-10-02 —
502 solid (`solid-hyperobjects@faaea08e`) and 516 soft (`soft-hyperobjects@700f9d03`) —
zero manifests carry any of the fields and zero are flagged. The rule cannot fire on a
manifest written before SEM-1.

## Concept IRIs

Keys are permanent names. Their concept IRIs are derived, never stored:
`entry_concept_iri("interface-sizes", "nema-17-face")` →
`https://id.madfam.io/concept/interface-sizes/nema-17-face`. Lexicon terms derive
`https://id.madfam.io/concept/{term-id}`; term ids contain no `/`, so the two never collide.

## Review state

Every label and definition is a one-pass draft (`generated`) — machine-written text is a
draft only (RFC 0039 §5). A native reader signs an entry by setting `review_status` to
`reviewed` with their name in `reviewers`; Spanish is the bar to read first.
