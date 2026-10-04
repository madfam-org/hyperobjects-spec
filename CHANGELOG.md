# Changelog

All notable changes to `hyperobjects-spec` are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### FPV antenna mount on the frame: rear 20 × 20 VTX seat (owner decision O3(a))

Additive catalog and vocabulary data; no grammar, gate or validator change.

#### Added

- **`fpv-frame-5in-x-225`**: `rear_vtx_mount`, the 20 × 20 mm VTX pattern (GEPRC MK5:
  "VTX mounting 30.5 × 30.5 / 20 × 20") on the top plate's UPPER face (female, symmetry 4),
  at the new parameter `rear_mount_x_mm` (default −45) — a convention, not a sourced fact,
  worded exactly like `camera_axis_x_mm`; and the dimension `vtx_hole_spacing`.
- **Vocabulary**: `vtx-mount-20x20` (in `interface-sizes.fpv.json`), cited to GEPRC MK5;
  the thread is not cited, so it is not a fact of the key.
- **Tests** (`tests/test_catalog_antenna_chain.py`): the full chain frame rear seat ↔
  antenna-mount foot (one 20 mm row, `rotation_index` 3 = the rear row) → jack seat ↔
  `sma-bulkhead-jack` → `vtx-antenna-sma` closes at back_angle 0 / 20 / 25 / 45, the two
  foot bolts landing on two of the four holes and the antenna leaning back; a foot keyed for
  another pattern, and the stack pattern, are refused.

### FPV camera cage on the frame: side plates' outer faces (owner decision O1(a))

Additive catalog and vocabulary data; no grammar, gate or validator change.

#### Added

- **`fpv-frame-5in-x-225`**: `camera_plate_left_outer` and `camera_plate_right_outer`, the
  side plates' OUTER faces on the camera side-screw axis (female: the plate's hole
  receives the screw of a part bolted on from outside; symmetry 0), and the parameter
  `side_plate_thickness_mm` (2.5, GEPRC Mark4). The outer faces stand
  `camera_bay_width_mm + 2 × side_plate_thickness_mm` apart (24 mm at the defaults).
- **Vocabulary**: `fpv-camera-side-plate-screw` (in `interface-sizes.fpv.json`): the
  camera side screw through a side plate; plate 2.5 mm, bay 19–20 mm (GEPRC). The thread
  is not cited, so it is not a fact of the key.
- **Tests** (`tests/test_catalog_camera_chain.py`): the full chain frame outer faces →
  cage ears → cage cradle ↔ camera `front_face` closes at tilt 0 / 15 / 30 / 45 / 55; the
  cage sits level and ahead of the frame, and the camera looks forward and up by the
  printed tilt; ears at the bay width (19) miss the second plate by 5 mm; a 20 mm bay
  needs ears 25 mm apart; an ear does not mate a plate's inner face.

### FPV camera chain: side plates, camera faces, two size keys (ASM-1 v1.1 follow-up)

Additive catalog and vocabulary data for assembly B (the 5-inch FPV quad); no grammar,
gate or validator change.

#### Added

- **`fpv-frame-5in-x-225`**: `camera_plate_left` and `camera_plate_right`, the side
  plates' inner faces on the camera side-screw axis (male: the plate carries the screw
  head; symmetry 0, so `angle_deg` is the camera tilt), and the parameter
  `camera_bay_width_mm` (the cited 19–20 mm; default 19).
- **`fpv-camera-micro-19mm`**: planar faces a printed part can mate:
  `side_face_left` / `side_face_right` (female, at the cited half-width), and
  `front_face` / `back_face` (male, symmetry 4). Where the side screws sit along the
  20 mm body is not published, so it is the convention parameter
  `screw_axis_to_front_mm` (default 10), not a fact.
- **Vocabulary supplement `interface-sizes.fpv.json`**: `fpv-camera-mini-21mm` (the mini
  class, cited at 21.8–22 mm; Pyrodrone, Foxeer) and `u-fl-cable-exit` (a coax route for a
  Hirose U.FL-terminated lead, Ø0.81–Ø1.37 cable, 2.5 mm max mated height; Hirose
  catalogue). Both cover options of commons selects (`fpv-camera-cage.cam_size`,
  `fpv-antenna-mount.connector`) that had no key.
- **`tests/test_catalog_camera_chain.py`**: the plates → camera cycle closes with the
  existing `camera_bay ↔ side_mount` mate at any tilt; a 20 mm bay seats a 19 mm body
  on one plate only; a cradle framed like `fpv-camera-cage`'s floor closes with the camera,
  and lens-first (`front_face`) is the face that makes it look UP by the tilt; a mini
  cradle refuses a micro camera; a cage wider than the bay (23.8 mm at the cage's
  defaults) cannot close on both plates.

### Frame grammar v1.1, gate radius, catalog and vocabulary (ASM-1 v1.1, package 0.4.0)

ASM-1 becomes v1.1.0. Every change is additive: every v1.0 manifest and assembly
validates unchanged (full-commons regression: 502 solid cartridges with `y4d-spec check`
and 516 soft ones with `fc-spec`, identical verdicts under 0.3.0 and 0.4.0).

#### Added

- **`let` on interfaces (D1)**: named derived numbers. Each is an expression, or a
  `{param, map}` lookup of a select's option value in a map of numbers.
  - Evaluated in dependency order, independent of key order.
  - Refused at check time: cycles (named in full), unknown names, a name that shadows a
    parameter or a function, and a map that does not cover the select's options exactly.
  - Accepted by the project-manifest and standard-part schemas.
- **Functions and comparisons (D2)**: `sin`, `cos`, `tan`, `asin`, `acos`, `atan` and
  `atan2(y, x)` in degrees, exact at OpenSCAD's exact angles; `sqrt`, `floor`, `ceil` and
  `round` (half away from zero); the comparisons `< <= > >= == !=`, which yield 1 or 0,
  with chains refused; and a lazy `iif(cond, a, b)`.
  - Domain errors (`asin(2)`, `sqrt(-1)`, `tan(90)`, `atan2(0, 0)`) are evaluation errors,
    never NaN.
- **Slider size keys (D3)**: `size_key {param: <slider>, map}` with exact canonical values.
  - A value with no entry has no size key.
  - The mate check names that reason (`ResolvedInterface.size_key_absent_reason`,
    `slider_size_key_miss`).
- **Version constants**: `FRAME_GRAMMAR_VERSION = "1.1.0"` and
  `FRAME_GRAMMAR_MIN_KEYSTONE = "0.4.0"`.
  - `frame_grammar_features(doc)` lists the v1.1 features a manifest uses, and
    `check_manifest` prints one note naming them and the minimum keystone.
  - An unknown call or character names the grammar version, so a newer grammar explains
    itself to this one.
- **Standard part `sma-bulkhead-jack`** (new category `connector`): a male `panel` and a
  male `coupling`, both `sma-bulkhead`. It is the part between an antenna mount's bore and
  an SMA antenna.
- **interface-sizes keys (D6)**, each cited: `tslot-3030-8mm`, `tslot-4040-8mm` (with a
  note naming MISUMI HFS8-4040's 10 mm variant, which is not minted), `nema-23-face`,
  `bearing-623` and `bearing-6900`.
- **AAS**: `MatingInterfaces` projects an interface's `let` block as a `Let` collection, so
  a service holding the stored shell can evaluate frames that read `let` names.

#### Changed

- **The frame gate's face search is progressive (D4).** It starts at 15 mm and widens ×1.5
  per step up to the part's bounding-box half-diagonal, stopping at the first ring that
  holds a face.
  - The radius used is the `search_radius_mm` residual, and the verdict message states it.
  - A verdict found within 15 mm is unchanged, so widening only turns a fail into a pass.
  - Re-gating the frames of solid-hyperobjects #111–#120 changed one verdict, from FAIL to
    ok: nema-bracket's `nema23_flat` face, at 22.5 mm.

#### Fixed

- **`bearing-608.outer_race.frame.normal` is `[0, 0, 1]` (finding C1).** The old −z normal
  placed a 608 outside a seat framed at its entrance. A placement test now puts it in the
  idler-608 seat (z 3..10).
- **`fpv-frame-5in-x-225` motor mounts**: `x_axis` points outward along each arm, through a
  catalog `let`, so a symmetry-4 clamp pod aligns at `rotation_index` 0.
- **The ASM-1 §2 example** mates the frame to the pod's `arm_clamp`, not to its
  `motor_bolt_pattern` (docs/ASSEMBLIES.md).

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
