# Changelog

All notable changes to `hyperobjects-spec` are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Assemblies (ASM-1 §2–§3)

#### Added

- `assembly.schema.json` (`hyperobjects_schemas.load("assembly")`). It describes a
  type-level assembly made of cartridge, standard and external components, with one
  instance per component and mates that state either `rotation_index` or `angle_deg`.
  It also carries a `capability_profile` (for producers) and the document licence.
- `y4d_spec.assembly`:
  - `validate_assembly(doc, resolver)` covers schema, resolution, the mating rule, BFS
    placement with `T_b = T_a·H(F_a)·Flip·Rz(θ)·H(F_b)^-1`, closure of every mate
    (0.05 mm, 0.5°, x-axis modulo symmetry), reachability and the
    `hyperobjects-assembly-v1` digest.
  - The `ComponentResolver` protocol, with commons-manifest, standard-parts and external
    resolvers. Parameters are checked and never clamped; frames are evaluated with
    `y4d_spec.frame_eval`; a cartridge's identity is its GOC-1 `instance_id`.
- `y4d-spec assembly check <assembly.json> --commons DIR [--standard-parts DIR] [--json]`.
  `--collision` is accepted and reported as not run, because it is not implemented in v1.
- `docs/ASSEMBLIES.md`: the document, the checks, the math with worked examples, and
  the resolver API.

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
