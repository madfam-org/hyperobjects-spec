# Changelog

All notable changes to `hyperobjects-spec` are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Collision envelopes for MGN9 and the 6 mm XY idler; the toolhead mount key (Phase 6, lane P6-XCAR)

Additive catalog and vocabulary data; no schema, grammar, gate or validator change.

#### Added

- **Envelopes** (ASM-1 §3.7, for `--collision`), each from the entry's cited dimensions:
  `mgn9-rail` (the 9 × 6.5 section, HIWIN WR × HR, over `length_mm`); `mgn9h-carriage` (a
  top slab and two skirts down to HIWIN H1 = 2 that leave the 9 mm rail channel open, as
  `mgn12h-carriage`; the entry now cites `rail_width` 9, HIWIN WR); `gt2-idler-20t-6mm`
  (the OD 18 cylinder over `width_mm`). The Y and Z rails of a 2.4-class assembly and the
  XY joints' toothed idlers are no longer `collision-unchecked`.
- **Vocabulary** (`interface-sizes.standard-parts.json`): **`toolhead-mount-20x20-m3`**, the
  face where a printer toolhead (or a stand-in body for one) bolts to its X carriage: four
  M3 on a 20 mm square, the MGN12H's own pattern (HIWIN). Used by the commons
  `x-carriage` and `toolhead-proxy` cartridges.
- **Tests** (`tests/test_catalog_xcarriage_envelopes.py`): an MGN9H on its rail and the
  6 mm idler on its M5x40 do not interfere beyond the declared bore overlap; the block's
  envelope stays clear of the rail's at every station along it; the new key is in the
  vocabulary.

#### Not added

- Flange envelopes for `gt2-pulley-16t-5mm` and `gt2-pulley-20t-9mm`: no source this lane may
  read states the flange diameter unambiguously (P6-ZBED's MISUMI F/E question stands).
- No 6 mm belt-end clamp key: a jaw that receives a `gt2-belt-6mm` end carries that key,
  female, which mates the belt's own `end_a` / `end_b` (male) as they are.

### `bearing-f695` as a smooth belt via: its running diameter (ASM-1 §9, lane P6-GANTRY)

Catalog data and tests only. #45 gave the two GT2 entries a `belt_engagement`; a 2.4-class
gantry's A/B belts also run round F695 stacks (Voron 2.4r2 build guide, cited by page only:
pp. 65, 69, 97, 99), so a belt path through one needs the bearing's.

#### Added

- **`bearing-f695.belt_engagement`**: `running_diameter` 13 (NSK F695ZZ, D), `center`
  [0, 0, 4], axis +z. The mid-plane is **a convention**: the plain-face junction of the
  guide's flanges-outward pair, so a via may name either bearing of the pair and lands on the
  same circle. A path adds the belt's side offset: teeth 13 + 2 × 1.014 = 15.028, back
  13 + 2 × 0.506 = 14.012 for the 2 mm GT2 section.
- **Tests** (`tests/test_catalog_f695_belt.py`): the entry's cited diameter and junction
  plane; `effective_diameter` gives 15.028 / 14.012; a belt turning 90° round an M5x40 →
  shim → F695 → F695 → shim stack measures two spans plus a quarter of the effective circle
  for either side and either bearing of the pair; a belt without the side's offset is
  refused; anchors 1 mm off the junction fail planarity. No golden moves: no fixture
  assembly places an F695.

### The 2.4 gantry's standard parts: MGN9, the A/B belt, the XY-joint idler (Phase 6, lane P6-GANTRY)

Additive catalog, vocabulary and schema-enum data; no grammar, gate or validator change.
Facts cite the HIWIN MG series table, SDP/SI's Technical Section, Pfeifer's belt-profile table
and a retailer listing; the Voron 2.4r2 build guide (GPL-3.0) and the VORON 2.4 sourcing
sheet are cited by page and row only, and none of Voron's geometry is used.

#### Added

- **`mgn9-rail`** (HIWIN MGN9: WR 9, HR 6.5, P 20, E 7.5, M3x8): `track` (`mgn9-rail`,
  male, sym 2), `base_first_hole` and the new **`base_at_station`** (`tslot-2020-6mm`, male,
  sym 2, at `base_station_mm`, so a rail set back 25 mm from an extrusion end, guide p. 88,
  mates the extrusion's slot station). `length_mm` defaults to 400, the 350 build's Y rail
  (sourcing sheet).
- **`mgn9h-carriage`** (HIWIN MGN9H: H 10, W 20, B 15 × C 16, M3x3, L 39.9): `top`
  (`mgn9-carriage`, female, sym 2: the pattern is a rectangle) and `rail_way` (z −3.5).
- **`gt2-belt-6mm`**, category **`belt`** (class: Gates PowerGrip GT2 2MR, 6 mm, the A/B
  belts, guide p. 131 and sourcing sheet LL-2GT-6): pitch 2, width 6, height B 1.52, tooth
  depth T 0.76 (Pfeifer 2MR/PGGT2), pitch-line differential U 0.254 (SDP/SI Table 4), and the
  derived `teeth_side_offset` 1.014 and `back_side_offset` 0.506 that ASM-1 §9 (v1.3) belt
  paths use on smooth vias. `end_a` / `end_b` (`gt2-belt-6mm`, male, sym 1) on the pitch
  line. The belt facts sit in the ASM-1 §9 `belt` block.
- **`gt2-idler-20t-6mm`** (class: Motedis listing, 20 T, Ø5 bore, 6 mm belt, OD 18, 9 wide;
  `belt_engagement.pitch_diameter` 12.73, SDP/SI Table 33): the XY joints' toothed idlers (guide pp. 98, 100;
  the sourcing sheet lists 6 mm toothed idlers there). Same interfaces as
  `gt2-idler-20t-9mm`; belt mid-plane at `width_mm` / 2, a convention.
- **Vocabulary** (`interface-sizes.standard-parts.json`): `mgn9-rail`, `mgn9-carriage`.
- **`standard-part.schema.json`**: category `belt` (the line #45 also added; merged cleanly).
- **Tests** (`tests/test_catalog_gantry.py`): a C extrusion → MGN9 rail at its 25 mm setback
  → MGN9H block → an XY joint framed as the commons cartridge `xy-joint` frames it → M5x40 →
  shim → F695 → F695 → shim between the joint's floor and roof, and M5x40 → 6 mm idler, close
  and put the stack on the low belt level (22 above the C) and the idler on the high one
  (31); the block runs along the rail; the mirrored joint swaps the levels; a roof 1 mm low
  fails closure; an MGN12H block on an MGN9 rail, an MGN12-pattern part on an MGN9H block and
  a belt end in a bore are refused. The axis audit covers the new idler's bore.

### The 350 build plate and its M3 T-nut (Phase 6, lane P6-ZBED; owner approval 2026-10-04)

Additive catalog and vocabulary data, plus the schema category `plate` (coordinator-approved
one-liner); no grammar, gate or validator change. The guide gives the bed's mounting but not the plate's size, so the plate is cited from vendor
listings, as the frame lengths were.

#### Added

- **`bed-plate-350`** (class): 355 × 355 mm cast aluminium (Spool3D, LDO via DREMC and
  HoneyBadger via Fabreeko agree). `thickness_mm` 8–10 by maker, default 9.525 (3/8 in:
  HoneyBadger, West3D); `standoff_mm` defaults to a DIN 466 M4 thumb nut's 9.5 (Aspen
  Fasteners), the guide's spacer (p. 58). Four mount interfaces (`m3-screw-joint`, male) on
  the rail lines x = ±65 (p. 20; the plate centred on them is a convention) under the
  spacers, each with `travel` along its rail over its half of the plate: no listing
  publishes the hole pattern, so a mate offset sets each hole. Envelope: the outline over
  the thickness. The alloy (ATP5, MIC6, 5083) varies by maker and is not stated as a fact.
- **`tnut-2020-m3`** (MISUMI HNTAP5-3: M3; 15 × 8 body): `slot` (`tslot-2020-6mm`) and
  `thread` (`m3-screw-joint`), as `tnut-2020-m5`.
- **Vocabulary:** `m3-screw-joint`.
- **`standard-part.schema.json`**: category `plate` (after `structural-profile`), for the
  build plate.
- **Tests** (`tests/test_catalog_bed_plate.py`): the bottom of the 350 cube, the two bed
  rails on four `bed-extrusion-mount` plates, four M3 T-nuts and the plate close with no
  warning; the plate lands centred between the rails, 9.5 above them, its front edge 38
  behind the frame's front face (p. 60), inside the uprights; a hole station that disagrees
  with its nut fails closure; a hole beyond the plate is an `offset` error.

### The Voron 2.4-class Z drive, Z belt and bed hardware (Phase 6, lane P6-ZBED)

Additive catalog and vocabulary data; no schema, grammar, gate or validator change. Phase 6 (D1) models the full 2.4 motion system, the four Z drives and
the bed included, with belts as declared paths (ASM-1 §9, P6-JOINT). Facts cite datasheets
and listings; the Voron 2.4r2 build guide (GPL-3.0) is cited by page and section only, and
none of its geometry is used.

#### Added

- **`gt2-pulley-16t-5mm`** (class; MISUMI GPA 2GT: P.D. 10.19, O.D. 9.68, 6 mm belt, L 18,
  W 10.3; Gates 2MR-16S 0.401 in), **`gt2-pulley-20t-9mm`** (class; MISUMI GPA: P.D. 12.73,
  9 mm belt, L 21, W 13.3) and **`gt2-pulley-80t-5mm`** (class; Spool3D listing: 5 mm bore,
  overall 18, hub 8, flange 54.7; Gates 2MR-80S: P.D. 2.005 in = 50.93). Each carries a
  `belt_engagement` (ASM-1 §9): the cited `pitch_diameter` (on the 2 mm GT2 circle, N·2/π)
  and the belt mid-plane's centre, derived from cited lengths (`plane_note` says how). Interfaces `bore` (face A, the hub end) and `bore_b` (face B,
  the flange end), so a pulley mounts either way round: the 16-tooth on the NEMA 17 shaft
  (`nema-17-shaft-5mm`), the 20- and 80-tooth on the Z drive's output shaft
  (`z-drive-pulley-hub-5mm`). 80 / 16 = 5:1 (guide pp. 33, 38).
- **`bearing-625`** (SKF 625: 5 × 16 × 5): `outer_race` (`bearing-625`, male) and `bore`
  (`bearing-625-bore`, female, at face B), framed as `bearing-608`.
- **`shaft-5mm`** (MISUMI SFJ D5 g6, L 10–400; default 60, the guide's 5x60, p. 32):
  journals `journal_a/b/c` (`bearing-625-bore`, male) and pulley hubs `hub_a` / `hub_b`
  (`z-drive-pulley-hub-5mm`, male) at station parameters whose defaults are the commons
  `z-drive-housing`'s (conventions).
- **`gt2-belt-9mm`**, the open Z belt (category `belt`; its `belt` block from Gates 2MR
  long-length belting, 17195 p. 90: pitch 2, width 9, height 1.52, tooth depth 0.76): `end_a` / `end_b`
  (`z-belt-gt2-9mm-clamp`, male, sym 2) on the back face at the clamp stations;
  `length_mm` defaults to the guide's minimum cut length for the 350 (1200, p. 111). The
  pitch-line differential is not cited, so the teeth-/back-side offsets are not stated; the
  Z path runs teeth-on-toothed parts only.
- **`gt2-belt-loop-188mm`**, the Z drive's reduction loop (category `belt`, no interfaces):
  `belt.loop_length` 188 (guide p. 34), width 6 (the Voron 2.4 motion set's Gates loop),
  pitch 2, height 1.52, tooth depth 0.76 (Gates 17195 p. 90); 94 teeth.
- **`bhcs-m5x10`** and **`bhcs-m5x16`** (ISO 7380-1; Keller & Kalmbach): `head_seat` only.
  The guide fixes the Z drives and the bed extrusions with M5x10 (pp. 19, 42–43) and the
  frame's blind joints with M5x16 (p. 14).
- **Envelopes** (ASM-1 §3.7, for `--collision`): `bearing-625`, `shaft-5mm`, `bhcs-m5x10`,
  `bhcs-m5x16` and `gt2-pulley-80t-5mm`, each from its cited dimensions. The 16- and
  20-tooth pulleys have none (no flange diameter cited), and the belts have none (paths).
- **Vocabulary** (`interface-sizes.standard-parts.json`): `bearing-625-bore`,
  `z-drive-pulley-hub-5mm`, `z-belt-gt2-9mm-clamp`.
- No schema change: the `belt` category, the `belt` and `belt_engagement` blocks and
  minItems 0 for belts arrived with ASM-1 §9 (0.7.0, P6-JOINT); this lane's entries use them.
- **Tests** (`tests/test_catalog_z_drive.py`): (i) a bottom corner — upright, two
  horizontals by blind joints, the Z drive housing framed as the commons cartridge
  `z-drive-housing` frames it, keyed into both bottom slots, T-nuts and M5x10s, three 625s,
  the shaft through all three (two closed cycles), the 20- and 80-tooth pulleys, the NEMA 17
  and its 16-tooth pulley — closes; the reduction pulleys are coplanar at the 40.8 mm centre
  distance that closes a 188 mm loop within 0.05 mm; a bearing seat or a corner station 1 mm
  off fails closure; (ii) the same upright's top corner with `corner-idler-bracket`: the Z
  idler and the Z pulley share one belt plane and one vertical; (iii) a 9 mm belt end in
  `z-belt-clamp`'s jaws on a gantry beam; (iv) `bed-extrusion-mount` holding a bed
  extrusion square, flush and butted; (v) the whole 350 frame cube at its cited cut lengths
  (530 uprights, 470 horizontals, 16 blind joints; Spool3D and LDO kit listings, guide
  pp. 13, 20) with a Z drive at each bottom corner, keyed into both bottom horizontals (into
  the x-running ones by a v1.4 mate offset of ∓160, since they carry the bed rails' station
  170), and both bed rails on four bed mounts —
  64 + 6 components close; a 471 horizontal or a 469 bed rail fails; (vi) ASM-1 §9: the
  16 → 80-tooth loop declared as a closed path in the Z drive closes at 188.006 mm with no
  `path-length` warning, and 2 mm further out it warns at the open-belt formula's length.
  Negative controls for every new key.

### `--collision`: rigid-body interference at every pose (ASM-1 §3.7, package 0.9.0)

Phase 6c, lane P6-JOINT. `--collision` is no longer a stub. The phase-4 lanes' scratch clash probes
(P4-ASM2's render probe and P4-AUTH-E's `authe_probe_clash.py`) are promoted into the
keystone.

#### Added

- **`y4d_spec.assembly.collision`.** Bodies:
  - cartridges are rendered at the assembly's parameters (full injection, every part the
    component produces);
  - standard parts and external designs use their `envelope`.

  They are placed at home, at every limit and at every Halton sample of the sweep. Pairs
  whose boxes overlap are intersected (OCCT common), once per relative placement.

  An overlap above 1 mm³ (a convention: the phase-4 probes' bar) is a `collision` error,
  unless `allowed_overlaps: [{a, b, max_mm3, reason}]` declares it. Other findings:
  - `allowed-overlap-unused`, `collision-unchecked` (warnings);
  - `allowed-overlap` (errors).

  `report.collision` is `checked`, `partial` or `unavailable`, never a silent pass. The
  JSON report adds `collision_pairs` and `collision_unchecked`.
- **Catalog `envelope`** (`standard-part.schema.json`, catalog rule 10): boxes and
  cylinders, each naming the cited `dimensions` it is built from. Entries with one:
  - extrusion, rail, carriage, NEMA 17, the GT2 pulley and idler;
  - the 608 and F695 bearings, shim, shaft and the two M5 screws;
  - prop, stack, antenna and PSU.

  The rest are listed in docs/STANDARD_PARTS.md with the missing fact.
  `mgn12h-carriage` gains the cited `rail_width` (HIWIN WR 12).
- **External `envelope`** (numbers only): an original proxy body (D3).
- **Tests** (`tests/test_assembly_collision.py`):
  - a slider driven into a stop fails at `slide@upper` with exactly 2000 mm³;
  - an allowance passes within it and fails above it;
  - an unused allowance warns;
  - a body-less component is named;
  - a rendered cartridge against a catalog envelope.

#### Changed

- **Fixture A's digest moves** `35867ffd…` → `8172f814…`, through catalog digests (an
  ordinary refresh; `PROJECTION_VERSION` stays 2).


### Stations on the mate: `offset` and interface `travel` (ASM-1 §9 v1.4, package 0.8.0)

P6-ZBED found that `extrusion-2020` has one `slot_station_mm` shared by its eight slots, so
two parts on one extrusion at different stations could not both mate. The full 2.4 hits
this constantly. The coordinator approved the fix on 2026-10-04. Lane P6-JOINT.

#### Added

- **`mate.offset: {side?, axis, value, note?}`.** The named side's interface frame
  (default `a`) slides `value` mm along its own axis before the mate is formed: a
  prismatic joint fixed at that value (`H(F)·J(value)`). A mate carries an offset or a
  joint, never both (schema).
- **Interface `travel: {axis, range}`** (catalog: frame-grammar bounds; external:
  numbers), with two findings:
  - an `offset` error when an offset runs along another axis or leaves the range (never
    clamped);
  - an `offset-unchecked` warning when the interface declares no travel.
- **Catalog lane rule 7** evaluates every `travel.range` bound at each parameter point and
  requires lower < upper.
- **`extrusion-2020`**: every `slot_*` interface travels along x (the extrusion axis,
  toward end B) over the slot's run, end A to end B, measured from the station. This adds
  no new number.
- **`Mates`** carries `OffsetSide`, `OffsetAxis` and `OffsetMm` on a mate with an
  offset. Nothing is written for a mate without one, so there is no projection-version
  bump.
- **Tests** in `tests/test_assembly_offset.py`:
  - two T-nuts on one slot at different stations;
  - side b;
  - the run's bounds;
  - the wrong axis;
  - undeclared travel;
  - offset XOR joint;
  - parity with `slot_station_mm`.

#### Changed

- **Fixture A's digest moves** `296caa36…` → `35867ffd…`, through `extrusion-2020`'s
  catalog digest. This is an ordinary refresh: `PROJECTION_VERSION` stays 2.


### Kinematics: joints, axis bindings, belt paths, the pose sweep (ASM-1 §9, contract v1.3, package 0.7.0) — projection version 2

Phase 6 of the Voron live-twin programme, lane P6-JOINT. It applies owner decisions D1–D5
(2026-10-04): belts are declared paths (D1), there is one logical Z joint with followers
(D2), and forward kinematics live in the keystone as the reference and in the viewer,
never in pravara (D4). The contract lands as **ASM-1 §9**, because §8 remains the frame
authoring gate. Everything is optional: assemblies A and B validate unchanged, with one
pose each.

#### Added

- **Joints on mates** (`assembly.schema.json` `mate.joint`; `y4d_spec.assembly.kinematics`):
  - `prismatic` (mm) or `revolute` (degrees) about `x`/`y`/`z` of side a's interface
    frame;
  - value 0 is the mate;
  - `T_b = T_a · H(F_a) · J(q) · Flip · Rz(θ) · H(F_b)^-1`;
  - three roles: **driven** (`home`), **follower** (`follows: {terms, offset}`), and
    **passive** (`passive: true`, measured: its mate only closes a cycle, with the degree
    of freedom free).
- **Machine-axis bindings** (`machine: {kinematics, axes: [{axis, joint, scale, offset}]}`):
  identity by default; only a driven joint may be bound.
- **Belt paths** (`paths[]`; `y4d_spec.assembly.paths`):
  - vias are pulleys and idlers with a `belt_engagement` (`wrap` ccw/cw, `side`
    teeth/back) or clamp anchors;
  - the path must be planar at home (0.5°, 0.5 mm, conventions);
  - the pitch-line length is reported at every pose. The tests prove it against the
    textbook open-belt and crossed-belt formulas;
  - `path-length` warns on a spread above 0.1 mm across the sweep, or a loop more than
    0.5 mm off its catalog `loop_length` (conventions);
  - the belt's catalog identity enters the digest (`path_parts`) only when a document
    declares paths.
- **The pose sweep** in `assembly check`, run once home passes:
  - home, each driven joint's limits, and `--pose-samples N` (default 16, a convention)
    Halton samples, seed 1;
  - new findings: `joint`, `machine`, `pose-closure`, `joint-limit`, `path` (errors) and
    `path-length` (a warning);
  - the report gains `joints`, `poses` and `paths`; the summary line gains
    `joints= poses=ok/total paths=`;
  - the 21 poses of the 14-component fixture run in about 0.08 s.
- **The reference forward kinematics.** `pose(doc, resolver, joint_values)`,
  `pose_from_axes(...)`, `compile_kinematics`, `golden_poses(_json)` and
  `y4d-spec assembly poses`.
- **Golden pose files** (`hyperobjects.assembly-poses` 1.0.0):
  - every computed number is a string in the canonical fixed format (6 decimals, ties
    away from zero, which is JavaScript's `toFixed(6)`);
  - a `tie_guard` lists the near-boundary entries;
  - `scripts/refresh_pose_golden.py [--check]` is a new CI step;
  - goldens exist for A, B and the new `tests/fixtures/kinematics/kinematic-gantry` (a
    passive carriage closing a cycle, an X carriage, a follower pulley, a closed GT2 loop).
- **Catalog** (`standard-part.schema.json`, `hyperobjects_standard_parts`):
  - category `belt` and a `belt` block: `pitch` and `width`, plus optional `height`,
    `tooth_depth`, `pitch_line_differential`, `teeth_side_offset`, `back_side_offset` and
    `loop_length`. A belt may have no interfaces;
  - an optional `belt_engagement` holding exactly one of `pitch_diameter` and
    `running_diameter`, plus `center`, `axis`, `parameters` and `plane_note`;
  - `belt_engagement()` and `belt_facts()`, and catalog-lane rule 9.
- **`gt2-pulley-20t-5mm` and `gt2-idler-20t-9mm`** carry `belt_engagement`:
  - pitch diameter 12.73 mm, cited from the Gates 20-2MR-PS-4 stock-pulley table via
    CMT Co. (= 20 × 2 / π);
  - the mid-planes (pulley z = 8; idler z = width / 2) are labelled conventions.
- **`--standard-parts` is repeatable** (`FirstOfResolver`): directories are tried in order.

#### Changed

- **`PROJECTION_VERSION` 1 → 2.** Every assembly shell gains the **`Kinematics`**
  submodel (MADFAM `smt/assembly-kinematics/1/0`): joints, axis bindings, paths and the
  pose sweep. It is not an extension of `Mates`: followers and paths span several mates.
  The drift guard refused the new bytes under the p1 ids until the bump. All 13
  projection goldens were refreshed.
- **`gt2-idler-20t-9mm`** no longer cites guide pp. 98/100. The XY-joint idlers carry the
  6 mm A/B belt (guide p. 131); this entry keeps p. 8 and p. 48 (Z).
- **Fixture A's digest moves** `24322cc0…` → `296caa36…`, through the pulley's catalog
  digest. This is an ordinary refresh, not immutable drift.
- `y4d_spec.assembly.validate` is split: the §9 steps live in `sweep.py`, and the mating
  tolerances in `tolerances.py` (still re-exported).


### Graph engine Wave D re-vendored: graph format 1.1 (lane P8-ENGINE, 2026-10-04)

The vendored Yantra4D graph engine (`src/y4d_spec/graph/`) moves in lockstep with the
platform's Wave D. Byte-identical copies of `graph_engine.py`, `graph.schema.json` and
`graph-node-catalog.json`; `graph.lock.json` is re-pinned. No change to the parity bar,
the projection or any gate threshold.

#### Added

- **Graph format 1.1.** `{"expr": ...}` inputs in the safeFormula dialect, top-level
  `parameters` (the manifest ids a graph reads, with defaults and an option `map`) and
  ordered `derived` values; the nodes `select`, `reflect`, `profile_polyline` and a
  bounded `revolve` (angle in (0, 360], axis in the profile plane, no axis crossing,
  1000 mm reach, valid positive-volume result).
- **`tests/fixtures/y4d/graph-twin-expr`**, the 1.1 golden twin. A script and a graph
  exercise every new feature, are compared under `--parity` at the defaults and two
  presets, and are wired into CI's self-check step.

#### Changed

- **G-DEADPARAM learns the expression door.** In a `.graph.json` mode, a manifest
  parameter is now also alive when the graph declares it in its own `parameters` object
  (`rules.graph_expression_parameters`). The transpiler refuses a declaration that no
  expression reads, so a declared id is a read one.


### M5 idler hardware and the 2020 blind joint (owner instruction 2026-10-04, lane P4-AUTH-E)

Additive catalog, vocabulary and schema-enum data; no grammar, gate or validator change.
The owner asked for a GT2 20-tooth idler, its M5 screws and a Z-idler corner bracket's
hardware (a Voron-style top corner), and for the F695 + shim stack, catalogued now and placed
once an assembly models a gantry. Facts cite datasheets; the Voron 2.4r2 build guide
(GPL-3.0) is cited by page and section only, and none of its geometry is used.

#### Added

- **`bhcs-m5x30`** (ISO 7380-1; Keller & Kalmbach: d 5, l 30, dk 9.5, k 2.75, s 3) and
  **`shcs-m5x40`** (ISO 4762; d 5, l 40, dk 8.5, k 5, s 4, b 22): `head_seat`
  (`m5-clearance-hole`, male) and `journal` (`m5-bolt-axle`, male, at the convention
  `journal_offset_mm`). One entry per length: ISO lengths are discrete.
- **`gt2-idler-20t-9mm`** (class; KB-3D listing of Gates G2GT-I-20-9: 20 T, Ø5 bore, 9 mm
  belt, 14 mm overall; Makersupplies: OD 18): `bore` (`m5-bolt-axle`, female) and
  `face_a` / `face_b` (`m5-axle-stack-face`, neutral). `width_mm` defaults to the Gates 14.
- **`bearing-f695`** (NSK F695ZZ: 5 × 13 × 4, flange 15 × 1): `bore`, `flange_face`,
  `plain_face`, and `outer_race` (`bearing-f695`, male, under the flange).
- **`shim-5x10`** (DIN 988; Keller & Kalmbach: d1 5, d2 10; 0.1–1.5 mm): `bore`,
  `face_a`, `face_b`; `thickness_mm` defaults to 1, a convention (the guide names none).
- **`tnut-2020-m5`** (MISUMI HNTAP5-5 post-assembly nut: M5, thread length 5, 15 × 8):
  `slot` (`tslot-2020-6mm`, male, sym 2) and `thread` (`m5-screw-joint`, female).
- **`extrusion-2020`: the blind joint.** `end_a_blind` / `end_b_blind` (male) and eight
  side stations `blind_{xp,xn,yp,yn}_{a,b}` (female) at the new `blind_station_mm`
  (default 10, flush corner), key `tslot-2020-blind-joint-m5`, symmetry 4. The ten
  existing interfaces are unchanged. This closes P4-ASM2 finding 2 for this joint: a butt
  joint off its station now fails closure. The access hole is not modelled (no cited
  diameter or position: MISUMI's alteration pages refuse automated reads).
- **Vocabulary** (`interface-sizes.standard-parts.json`): `m5-bolt-axle`,
  `m5-clearance-hole`, `m5-screw-joint`, `m5-axle-stack-face` (the catalog's first neutral
  key), `bearing-f695`, `tslot-2020-blind-joint-m5`.
- **`standard-part.schema.json`**: categories `fastener` and `spacer`.
- **Tests** (`tests/test_catalog_m5_idlers.py`): (i) a top corner — an upright, two
  horizontals by blind joints, a T-nut, the corner idler bracket framed as the commons
  cartridge `corner-idler-bracket` frames it, keyed into the other horizontal and the
  upright, its M5x30 and the idler — closes and places every part; a blind station 1 mm off
  fails closure; (ii) M5x40 → shim → F695 → F695 → shim between two host walls closes,
  flanges outward; a thicker shim fails until the walls move. The axis audit covers the
  new axis interfaces.

#### Changed

- The assembly golden for A moves only through `extrusion-2020`'s catalog digest:
  `58caf081…` → `24322cc0…` (`scripts/refresh_assembly_golden.py`).
### The projection version in every shell id (SEM-1 §1, package 0.6.0) — BREAKING for id consumers

Owner decision 2026-10-04: "go with versioning the projection into the shell id". A shell
id named a design revision but not the projection that produced its bytes, so once a store
that keeps shells immutable (asset-shells) went live, any projection change would have been
a 409 for every revision already published (P4-GRAPH decision 7).

#### Changed

- **Every shell and submodel id carries the projection version** as a path segment after
  the revision digest: `…/aas/{kind}/{slug}/{tree16}/p{N}`,
  `…/sm/{kind}/{slug}/{tree16}/p{N}/{idShort}`, materials
  `…/aas/material/{slug}/{content16}/p{N}` (and `…/sm/material/…/p{N}/{idShort}`). Solid,
  soft, assembly and material shells alike. `N` is `hyperobjects_aas.PROJECTION_VERSION`,
  `1` for this projection (the 0.5.0 projection plus the version itself). Asset, concept,
  template and standard-part ids are unchanged.
- **The shell records its version** in a `ProjectionVersion` extension
  (`xs:positiveInteger`), so a reader need not parse the id. `administration` stays the
  manifest semver.
- **BoM `DerivedFrom`** (assembly → type shell) names the type shell at the assembly's
  own projection version. The stored-shell resolver (`resolver.py`) parses versioned ids
  of any version; a pre-0.6.0 unversioned id no longer parses.
- **`aas check`**: the shell id must be versioned, its `ProjectionVersion` extension must
  state the same version (`projection-version`), and every submodel id must carry it.
- `hyperobjects_aas` 0.3.0; `ids.py` gains `PROJECTION_VERSION`, `parse_shell_id`,
  `parse_submodel_id`, `projection_extension`, `shell_projection_version`, and a
  keyword-only `version=` on every shell/submodel id function.

#### Added

- **The drift guard** (`hyperobjects_aas.drift`). When the bytes under an id the golden
  already carries change, the projection moved for the same inputs. `scripts/refresh_assembly_golden.py`
  then refuses to write, and `--check` fails, until `PROJECTION_VERSION` is bumped.
  ConceptDescription-only changes (lexicon text) are ordinary drift. `--check` is now a CI
  step.
- **Goldens for every kind of shell** (13): assemblies A and B, now also their nine solid
  cartridges (`tests/fixtures/assembly-golden/golden/cartridges/`), a soft garment
  (`sem1-garment`) and a material card (`bambu-tpu-95a`) in `tests/fixtures/aas/golden/`.
  Each records the version it was made with (ids and extension).
- `tests/test_projection_version.py`.

### The 608 idler axle: `shaft-8mm` (assembly A's idler)

Additive catalog, vocabulary and schema-enum data; no grammar, gate or validator change.
Nothing in the catalog carried a MALE `bearing-608-bore`, so a 608 (and a pulley on its
outer ring, such as the commons `idler-608`) could not reach a frame.

#### Added

- **`shaft-8mm`** (datasheet: MISUMI SFJ / PSFJ straight linear shaft, D 8 g6
  −0.005/−0.014, L 20–800 mm in 1 mm increments): a plain ground Ø8 shaft, the idler axle.
  - `host_end` → `shaft-8mm`, male, symmetry 0: end A in a host's 8 mm bore, framed at the
    host face, `host_depth_mm` from end A (a convention, default 8).
  - `bearing_journal` → `bearing-608-bore`, male, symmetry 0: where the 608's face B
    lands, `host_depth_mm + bearing_gap_mm + 7` from end A (7 = the 608's width).
    Both normals point −z, toward end A, so the bearing lies between the journal and the
    host and its face A looks at the host across `bearing_gap_mm`, whose default is one
    ISO 7089 size-8 washer, 1.6 mm (Keller & Kalmbach datasheet).
  - Retention (collars, retaining rings, the host's press or clamp fit) is not modelled.
- **Vocabulary** (`interface-sizes.standard-parts.json`): `shaft-8mm`, the Ø8 g6 shaft in a
  host's 8 mm bore, distinct from the 608's inner ring (`bearing-608-bore`).
- **`standard-part.schema.json`**: the category `shaft`.
- **Tests** (`tests/test_catalog_idler_axle.py`): the chain host bore → axle → 608 bore,
  then 608 outer ring → pulley seat, framed as the commons frames roller-bracket's 2020
  bracket bore and idler-608's seat, closes and places each part (axle end A flush with a
  web 8 mm thick, the 608's face A 1.6 mm off the host face, the pulley's top face flush
  with face A); it spins freely about the axle; a thicker host and a wider gap move the
  bearing with them; the two male interfaces cannot be swapped, a 608 does not seat in the
  host directly, and a host bore of another size refuses the axle. The axis audit in
  `tests/test_catalog_v1_1.py` covers the two new interfaces.

### Assembly AAS projection, closing-angle check, capability `process` list (ASM-1 §5–§6, package 0.5.0)

The assembly projection the asset-shells twin graph is built from, and the two keystone
findings of P4-ASM2. Assemblies A and B (solid-hyperobjects main `00e1765`, B with the camera
cage, 13 mates) validate unchanged. A's digest is the commons CI's (`58caf081…`); B's is
`96166430…` on this catalog (`f0db7bdb…` at the commons' SPEC_PIN 8c12194: #41 changed the
`fpv-frame-5in-x-225` entry, whose catalog digest enters the assembly digest).

#### Added

- **`hyperobjects_aas.assembly`** (ASM-1 §5): a checked assembly → one AAS Environment.
  Shell `aas/assembly/{slug}/{digest16}`, asset `asset/assembly/{slug}`, specificAssetIds
  `commons`, `slug`, `assembly_digest`. Submodels: `Nameplate`; `AssemblyDocument` (the
  document as a canonical-JSON `Blob`, with its digest); `BillOfMaterials` (IDTA 02011-1-1
  HSEBoM: one `Node` per component, `HasPart` from the entry node; cartridge nodes carry
  the GOC-1 `instance_id` and a `DerivedFrom` reference to the exact type shell revision);
  `Mates` (one `AnnotatedRelationshipElement` per mate: interfaces, stated rotation,
  residuals, `Validated`); `AssemblyPlacement` (4 × 4 world transforms); producers:
  `CapabilityDescription` (IDTA 02020-1-0, identifiers copied from the published template
  at the pinned `IDTA_COMMIT`); products with `requirements_rollup`: `RequirementProfile`.
  A failing assembly is never projected.
- **`hyperobjects_aas.resolver`**: `EnvironmentCartridgeResolver` resolves cartridge
  components from stored type shells (`ParametricModel`, `GeometryProvision`,
  `MatingInterfaces`, `RequirementProfile`) at the revision a node's `DerivedFrom` names;
  `component_type_shells(env)`, `assembly_document_from_environment(env)`,
  `bundled_standard_parts_dir()`. It reproduces A's and B's digests and environments byte
  for byte, and agrees with the manifest resolver on every cartridge mode of the solid
  commons (502 cartridges, 1490 modes, 3056 interfaces at the defaults, solid `00e1765`).
- **`y4d-spec aas build <assembly-dir | assembly.json>`** with `--commons-dir` and
  `--standard-parts`; **`aas check`** applies the assembly rules (the document decodes,
  validates, names the shell's slug and states its digest).
- **Golden fixtures**: `tests/fixtures/assembly-golden/` (assemblies A and B and their
  nine cartridges copied byte-identical from the commons, CERN-OHL-W-2.0, NOTICE.md) and
  the golden environments; `scripts/refresh_assembly_golden.py [--check]`.
- `hyperobjects_lexicon.capability_profile_problems`.
- MADFAM templates `assembly-document`, `assembly-mates`, `assembly-placement`,
  `capability-description`; IDTA template `capability-description` (02020-1-0).

#### Changed

- **Continuous-symmetry closing mates are checked** (P4-ASM2 finding 3b): when both
  frames declare an `x_axis`, the stated `angle_deg` must agree with the realised angle
  within 0.5° (the x-axis residual, measured on the full circle). Before, any angle
  passed on a symmetry-0 cycle. Without an `x_axis` a closing mate warns
  `angle-unchecked`. Stricter: an assembly that stated a wrong closing angle now fails.
- **`capability_profile.process` is a list** (P4-ASM2 finding 5): the
  `fabrication-capabilities` vocabulary types `process` as `array` of `processes` keys,
  the assembly schema refuses a bare string, and step 1 of `assembly check` checks the
  whole profile against the vocabulary (`capability` findings).
- **The P4-STD lexicon terms are attached** (that lane's deviation 3): `SizeKey` /
  `SizeKeyMap` → `interface-size-key`, `Frame` → `interface-frame`, `Polarity` →
  `interface-polarity`, `Symmetry` → `interface-symmetry`, a parameter's `Unit` →
  `parameter-unit`. Every cartridge environment gains these semanticIds and their
  ConceptDescriptions.
- A checkbox default written as `0`/`1` also projects as `DefaultAsWritten` (integer), so
  the GOC-1 identity survives a read-back (`custom-msh.stack_along_y` was the one case in
  the commons).
- `CommonsManifestResolver` details carry the produced parts and the manifest
  `requirements` (informative, never hashed).
- `standard_part_id` accepts a catalog key as well as an interface-sizes key.
- Package 0.5.0; `hyperobjects_aas` 0.2.0.

#### Documented, not built

- Butt joints (an extrusion end against a face) have no mate and are invisible to the
  mating rule (P4-ASM2 finding 3a); only the `--collision` stub or a planar end-face
  interface would catch them (docs/ASSEMBLIES.md, "Limits in v1").

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
