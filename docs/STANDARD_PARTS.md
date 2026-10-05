# The standard-parts catalog (ASM-1 §4)

> Public reference data. Every fact here cites a public standard, a manufacturer page or a
> public datasheet; see [PUBLIC_REPO_BOUNDARY.md](PUBLIC_REPO_BOUNDARY.md).

An assembly document (ASM-1 §2) names three kinds of component: a commons cartridge, an
external design referenced by name, licence and URL, and a **standard part** — a
commercial off-the-shelf part such as a NEMA 17 stepper, a 2020 extrusion or a 2207 motor.
Standard parts live here, in `src/hyperobjects_standard_parts/parts/`, one JSON file per
part named `{key}.json`, validated by
`src/hyperobjects_schemas/schemas/standard-part.schema.json`.

```json
{"id": "motor_fl", "source": {"type": "standard", "key": "motor-2207"}}
```

**Facts only.** An entry states the governing standard or datasheet with citation URLs,
dimensions that each cite a source by index, optional parameters, and its mating
interfaces. It never copies datasheet prose and never carries CAD.

## What an entry holds

| Field | What it is |
|---|---|
| `key` | the catalog key an assembly writes; the asset id derives from it (`https://id.madfam.io/asset/standard/{key}`, ASM-1 §5) |
| `category` | a grouping for readers (`stepper-motor`, `structural-profile`, `airframe`, …), not a mating rule |
| `name`, `description` | es/en/fr/pt (RFC 0039), all `generated` drafts until a native reader signs them |
| `governing` | `kind` (`standard`, `datasheet` or `class`), a `designation`, and the index of its primary source |
| `sources` | public citations, with the facts each one `supports` stated as facts |
| `frame_convention` | the part's model frame in words: origin, axes, and which face or axis each interface sits on |
| `dimensions` | facts by name: `{value, unit, source, tolerance?, note?}`; a derived value says so in `note` |
| `parameters` | choices an assembly may make for one instance (`length_mm` of an extrusion); `{id, type: number, label, default, min, max, unit, source?, note?}` |
| `interfaces` | the SEM-1 §2.3 shape: `{id, label, geometry_type, size_key, polarity, symmetry, frame: {origin, normal, x_axis}, parameters?}` |

A `class` entry (the 5-inch X frame, the 2207 motor, the micro camera, the 5-inch prop,
the 30.5 stack, the SMA antenna) states only what members of a commercial class share,
cited from vendor listings; anything a member varies is a parameter with a conventional
default, and its `note` says it is a convention. **`fpv-frame-5in-x-225` is a class, not
a design:** it copies no branded frame's outline, arm shape or plate geometry.

### Frames and parameters

Frame components are numbers or expressions over the entry's own parameters in the ASM-1
§1 frame grammar (literals, parameter ids, `+ - * /`, parentheses, `min`, `max`, `abs`;
from v1.1 also degree trig, `sqrt`, `floor`, `ceil`, `round`, comparisons and `iif`). An
interface may declare a `let` block of named derived numbers its frame reads — always an
expression here, since a standard part has no select — evaluated in dependency order
(`fpv-frame-5in-x-225` uses one for the arm length). An assembly resolves them by GOC-1 full injection (ASM-1 §1): the default, overridden by the
component's given value; out of range is an error, never clamped.

```python
from hyperobjects_standard_parts import load_part, resolve_parameters, interface_frames, part_digest

rail = load_part("mgn12-rail")
values = resolve_parameters(rail, {"length_mm": 300})
interface_frames(rail, values)["track"].origin     # (150.0, 0.0, 8.0)
part_digest(rail)                                  # sha256 of the canonical JSON (ASM-1 §3.8)
```

Every `normal` and `x_axis` in the catalog is an exact unit vector (axis-aligned, except the
FPV frame's motor-mount `x_axis`, which points along its arm) and every
`x_axis` is orthogonal to its normal — at the defaults and at every parameter's `min` and
`max`. The catalog carries no normalisation slack, so the placement (ASM-1 §3.4) can build
its matrices from the vectors as written.

### Polarity convention

The mating rule pairs male with female and neutral with neutral. In this catalog:

- **female** receives: a tapped or plain hole a fastener's thread or a partner's stud
  enters, a bore, a slot, a bay (the NEMA 17 face, an extrusion slot, a prop hub);
- **male** inserts, or carries the fastener head: a shaft, a stud or standoff, a body that
  goes into a bay or a housing, the clearance-hole side a screw passes through into a
  female partner (a frame's motor mount, a D2F switch's holes, a bearing's outer ring,
  an SMA bulkhead jack's threaded body);
- **neutral** is face-to-face contact with no inserting side: the faces of parts stacked on
  one M5 axle (`m5-axle-stack-face` on `shim-5x10`, `bearing-f695`, `gt2-idler-20t-9mm`).
  Only the first part of a stack mates the screw's `journal`; the rest follow face to face,
  so a stack's order and height are what its mates check.

Polarity is mechanical: an SMA antenna's coupling nut is female here, whatever RF naming
calls the plug.

### Size keys are the shared fit

Two interfaces mate only when their resolved `size_key`s are **equal**, so a size key
names the fit both sides share, not one side's diameter. A pulley's 5 mm bore therefore
carries `nema-17-shaft-5mm`, and an MGN12 rail bolted into a 2020 slot carries
`tslot-2020-6mm`. Every key resolves in the `interface-sizes` vocabulary through the same
membership rule a manifest goes through, and an interface's `geometry_type` must equal its
size key's.

## The catalog

| Key | Governing | Interfaces → size key, polarity, symmetry | Parameters | Sources |
|---|---|---|---|---|
| `bearing-f695` | datasheet | `bore` → `m5-bolt-axle` female, sym 0 (at the flange face)<br>`flange_face`, `plain_face` → `m5-axle-stack-face` neutral, sym 0<br>`outer_race` → `bearing-f695` male, sym 0 (under the flange) | — | NSK, VoronDesign |
| `bhcs-m5x30` | standard | `head_seat` → `m5-clearance-hole` male, sym 0<br>`journal` → `m5-bolt-axle` male, sym 0 (where a carried part's face A lands) | `journal_offset_mm` | Keller & Kalmbach, VoronDesign |
| `bed-plate-350` | class (category `plate`) | `mount_{left,right}_{front,back}` → `m3-screw-joint` male, sym 0, on the rail lines x = ±65 under the spacers, `travel` along the rail over each half of the plate | `thickness_mm`, `standoff_mm` | Spool3D, LDO (DREMC), HoneyBadger (Fabreeko), West3D, Aspen Fasteners, VoronDesign |
| `bearing-625` | standard | `outer_race` → `bearing-625` male, sym 0<br>`bore` → `bearing-625-bore` female, sym 0 (at face B) | — | SKF (Quality Bearings Online), VoronDesign, West3D |
| `bhcs-m5x10`, `bhcs-m5x16` | standard | `head_seat` → `m5-clearance-hole` male, sym 0 (no journal: fasteners, not axles) | — | Keller & Kalmbach, VoronDesign |
| `bearing-608` | standard | `outer_race` → `bearing-608` male, sym 0<br>`bore` → `bearing-608-bore` female, sym 0 | — | 123Bearing |
| `extrusion-2020` | datasheet | `end_a, end_b` → `tslot-2020-end-tap-m5` female, sym 4<br>`slot_xp_a … (8)` → `tslot-2020-6mm` female, sym 2<br>`end_a_blind, end_b_blind` → `tslot-2020-blind-joint-m5` male, sym 4<br>`blind_xp_a … (8)` → `tslot-2020-blind-joint-m5` female, sym 4 | `length_mm`, `slot_station_mm`, `blind_station_mm` | MISUMI, VoronDesign |
| `fc-stack-30x30` | class | `mount` → `stack-30.5x30.5-m3` female, sym 4 | — | Matek Systems |
| `fpv-camera-micro-19mm` | class | `side_mount` → `fpv-camera-micro-19mm` male, sym 0<br>`side_face_left`, `side_face_right` → `fpv-camera-micro-19mm` female, sym 0 (planar, y = ±9.5)<br>`front_face`, `back_face` → `fpv-camera-micro-19mm` male, sym 4 (planar) | `screw_axis_to_front_mm` | Rotorama, Team BlackSheep |
| `fpv-frame-5in-x-225` | class | `motor_mount_fl … (4)` → `motor-mount-16x16-m3` male, sym 4, `x_axis` outward along the arm<br>`stack_mount` → `stack-30.5x30.5-m3` male, sym 4<br>`camera_bay` → `fpv-camera-micro-19mm` female, sym 0<br>`camera_plate_left`, `camera_plate_right` → `fpv-camera-micro-19mm` male, sym 0 (side plates' inner faces)<br>`camera_plate_left_outer`, `camera_plate_right_outer` → `fpv-camera-side-plate-screw` female, sym 0 (outer faces, for a cage's ears)<br>`rear_vtx_mount` → `vtx-mount-20x20` female, sym 4 (top plate's upper face, at the convention `rear_mount_x_mm`)<br>`battery_strap` → `battery-strap-20mm` female, sym 2 | `motor_half_x_mm`, `motor_half_y_mm`, `top_plate_z_mm`, `camera_axis_x_mm`, `camera_bay_width_mm`, `side_plate_thickness_mm`, `rear_mount_x_mm` | GEPRC |
| `gt2-idler-20t-9mm` | class | `bore` → `m5-bolt-axle` female, sym 0<br>`face_a`, `face_b` → `m5-axle-stack-face` neutral, sym 0 | `width_mm` | KB-3D (Gates), Makersupplies, VoronDesign |
| `gt2-belt-loop-188mm` | datasheet (category `belt`) | none: a closed loop, `belt.loop_length` 188 | — | Gates (17195), VoronDesign, West3D |
| `gt2-belt-9mm` | datasheet (category `belt`) | `end_a`, `end_b` → `z-belt-gt2-9mm-clamp` male, sym 2 (on the back face at the clamp stations) | `length_mm` | Gates (17195), VoronDesign, West3D |
| `gt2-pulley-16t-5mm` | class | `bore` (face A, hub end), `bore_b` (face B, flange end) → `nema-17-shaft-5mm` female, sym 0 | — | MISUMI, Gates (Royal Supply), West3D, VoronDesign |
| `gt2-pulley-20t-9mm` | class | `bore`, `bore_b` → `z-drive-pulley-hub-5mm` female, sym 0 | — | MISUMI, West3D, VoronDesign |
| `gt2-pulley-80t-5mm` | class | `bore`, `bore_b` → `z-drive-pulley-hub-5mm` female, sym 0 | — | Spool3D, Gates (Royal Supply), West3D, VoronDesign |
| `gt2-pulley-20t-5mm` | datasheet | `bore` → `nema-17-shaft-5mm` female, sym 0 | — | Adafruit Industries, ServoCity |
| `mgn12-rail` | datasheet | `track` → `mgn12-rail` male, sym 2<br>`base_first_hole` → `tslot-2020-6mm` male, sym 2 | `length_mm`, `carriage_offset_mm` | HIWIN |
| `mgn12h-carriage` | datasheet | `top` → `mgn12-carriage` female, sym 4<br>`rail_way` → `mgn12-rail` female, sym 2 | — | HIWIN |
| `microswitch-d2f` | datasheet | `mount_a, mount_b` → `omron-d2f-mount-m2` male, sym 2 | — | Omron |
| `motor-2207` | class | `base` → `motor-mount-16x16-m3` female, sym 4<br>`prop_shaft` → `prop-shaft-m5` male, sym 0 | `prop_seat_mm` | iFlight, BrotherHobby |
| `nema-17-48mm` | datasheet | `face` → `nema-17-face` female, sym 4<br>`shaft` → `nema-17-shaft-5mm` male, sym 0 | `shaft_seat_mm` | LDO Motors, Nanotec Electronic |
| `prop-5in` | class | `hub` → `prop-shaft-m5` female, sym 0 | — | HQProp |
| `sma-bulkhead-jack` | class | `panel` → `sma-bulkhead` male, sym 0<br>`coupling` → `sma-bulkhead` male, sym 0 | `mating_face_z_mm` | Amphenol RF |
| `shcs-m5x40` | standard | `head_seat` → `m5-clearance-hole` male, sym 0<br>`journal` → `m5-bolt-axle` male, sym 0 | `journal_offset_mm` | Keller & Kalmbach, VoronDesign |
| `shaft-5mm` | datasheet | `journal_a/b/c` → `bearing-625-bore` male, sym 0 (at each 625's face B)<br>`hub_a` (pulley toward end A), `hub_b` (toward end B) → `z-drive-pulley-hub-5mm` male, sym 0 | `length_mm`, `journal_{a,b,c}_mm`, `hub_{a,b}_mm` | MISUMI, SKF, VoronDesign, West3D |
| `shim-5x10` | standard | `bore` → `m5-bolt-axle` female, sym 0<br>`face_a`, `face_b` → `m5-axle-stack-face` neutral, sym 0 | `thickness_mm` | Keller & Kalmbach, VoronDesign |
| `shaft-8mm` | datasheet | `host_end` → `shaft-8mm` male, sym 0 (end A in the host bore, at the host face)<br>`bearing_journal` → `bearing-608-bore` male, sym 0 (where the 608's face B lands) | `length_mm`, `host_depth_mm`, `bearing_gap_mm` | MISUMI, Keller & Kalmbach, 123Bearing |
| `psu-meanwell-lrs-200` | datasheet | `base` → `meanwell-lrs-200-base-m4` female, sym 2<br>`side_pos_y, side_neg_y` → `meanwell-lrs-200-side-m4` female, sym 2 | — | Mean Well |
| `tnut-2020-m3` | datasheet | `slot` → `tslot-2020-6mm` male, sym 2<br>`thread` → `m3-screw-joint` female, sym 0 | — | MISUMI, VoronDesign |
| `tnut-2020-m5` | datasheet | `slot` → `tslot-2020-6mm` male, sym 2<br>`thread` → `m5-screw-joint` female, sym 0 | — | MISUMI, VoronDesign |
| `vtx-antenna-sma` | class | `connector` → `sma-bulkhead` female, sym 0 | — | Amphenol RF, Drone-FPV-Racer |

### The blind joint (2020 frames joined without brackets)

A 2020 frame joined by blind joints (Voron 2.4r2 build guide pp. 10, 14–15) has an M5 button
head screw in each tapped end of one extrusion, its head slid into the slot of the other, which
the end butts. `extrusion-2020` carries it as `end_a_blind` / `end_b_blind` (male, on the end
face) and eight side stations `blind_{xp,xn,yp,yn}_{a,b}` (female, on each face's centreline at
`blind_station_mm` from each end; the default 10 puts a butted partner flush with the end, as at
a frame corner), key `tslot-2020-blind-joint-m5`, symmetry 4. A butt joint is therefore a mate
the closure check sees: a station 1 mm off breaks a closed corner. The access hole the screw is
tightened through is not modelled: no source read gives its diameter or position.

### The Z drive and the Z belt (a Voron 2.4-class belt-reduction drive)

A Voron 2.4-class Z drive (build guide pp. 32–38) turns a Ø5 output shaft (`shaft-5mm`) in
three 625 bearings (`bearing-625`). The shaft carries an 80-tooth pulley
(`gt2-pulley-80t-5mm`), driven 5:1 by a 16-tooth pulley (`gt2-pulley-16t-5mm`) on the
NEMA 17 through a closed 188 mm GT2 loop, and a 20-tooth 9 mm pulley (`gt2-pulley-20t-9mm`)
that drives the Z belt (`gt2-belt-9mm`). The Z belt runs up to the top-corner idler
(`gt2-idler-20t-9mm`) and both its ends are clamped on the gantry
(`z-belt-gt2-9mm-clamp`). Every pulley carries a `belt_engagement`: its cited
`pitch_diameter` and the centre of its belt's mid-plane, derived from cited lengths. The
reduction loop (`gt2-belt-loop-188mm`) has no ends, so no interfaces: a Z drive declares it
as a closed path (`belt.loop_length` 188) round the two pulleys.

Frame conventions, in brief (each entry's `frame_convention` is the full statement):

| Key | Origin and axes |
|---|---|
| `nema-17-48mm` | centre of the mounting face; +z out along the shaft toward the bracket; holes at (±15.5, ±15.5, 0) |
| `extrusion-2020` | centre of end A; +z along the extrusion to end B at `length_mm`; faces at x, y = ±10 |
| `mgn12-rail` | bottom face at end A, on the centreline; +x along the rail; top at z = 8 |
| `mgn12h-carriage` | centre of the top mounting face; +z up; rail top at z = −5 (H 13 − HR 8) |
| `bearing-608` | centre of side face A; +z along the axis to face B at z = 7 (both interface normals +z since v1.1) |
| `gt2-pulley-20t-5mm` | centre of end face A (toward the motor); +z along the bore, away from the motor |
| `psu-meanwell-lrs-200` | centre of the base footprint; +x away from the terminal block; top at z = 30 |
| `microswitch-d2f` | midway between the hole centres on the mid-plane; +y through the thickness; +z toward the actuator |
| `motor-2207` | centre of the base; +z along the shaft toward the propeller |
| `fpv-frame-5in-x-225` | centre of the stack pattern on the arms' top face; +x forward, +y left, +z up; motor-mount `x_axis` outward along each arm |
| `fc-stack-30x30` | centre of the hole square on the lowest board's bottom face; +x toward the board arrow |
| `fpv-camera-micro-19mm` | on the side-screw axis, midway between the side faces; +x along the optical axis |
| `prop-5in` | centre of the hub's bottom face; +z up through the hub |
| `vtx-antenna-sma` | centre of the coupling nut's mating face; +z along the antenna |
| `sma-bulkhead-jack` | centre of the panel shoulder face; +z along the threaded body to the mating face at `mating_face_z_mm` |
| `shaft-8mm` | centre of end A; +z along the axis to end B at `length_mm`; host face at `host_depth_mm`, the 608's face A `bearing_gap_mm` (one ISO 7089 washer, 1.6) beyond it; both normals −z |
| `bhcs-m5x30`, `shcs-m5x40` | centre of the under-head face; +z along the shank to the tip (30 / 40); the journal `journal_offset_mm` along it; both normals +z |
| `gt2-idler-20t-9mm`, `shim-5x10` | centre of face A; +z through to face B at `width_mm` / `thickness_mm`; the bore and face A share the origin, normals −z |
| `bearing-f695` | centre of the flange face (face A); +z to the plain face at z = 4; the outer-ring seat under the flange at z = 1 |
| `bearing-625` | centre of side face A; +z to face B at z = 5; the bore framed at face B, as `bearing-608` |
| `gt2-pulley-16t-5mm`, `gt2-pulley-20t-9mm`, `gt2-pulley-80t-5mm` | centre of face A, the hub end; +z through the hub and the flanged toothed section to face B at z = 18 / 21 / 18; the belt mid-plane at z = 12.85 / 14.35 / 13 (`belt_engagement.center`) |
| `shaft-5mm` | centre of end A; +z to end B at `length_mm`; journals where a 625's face B lands (normal −z), hubs where a pulley's bore face lands (normal toward the pulley) |
| `gt2-belt-loop-188mm` | no frame: a closed loop has no ends; its geometry is the declared path |
| `gt2-belt-9mm` | the belt laid straight: end A's clamp station on the back face at mid-width; +x along the belt to end B at `length_mm`, +y across the width (±4.5), +z through the belt toward the teeth |
| `tnut-2020-m5`, `tnut-2020-m3` | on the slotted face over the thread axis; +z out of the extrusion; +x along the slot |
| `bed-plate-350` | centre of the underside; +z to the build surface at `thickness_mm`; +x across the printer, +y front to back; mounts `standoff_mm` below, at x = ±65 |

### Interface sizes added for the catalog

The base `interface-sizes.json` did not define every fit the catalog needs, so nineteen cited
keys ship in a **supplement**, `interface-sizes.standard-parts.json`, which the loader
merges into the `interface-sizes` vocabulary (a supplement is a whole document of the same
vocabulary named `{vocabulary}.{label}.json`; only its entries are used):

| Key | Facts | Source |
|---|---|---|
| `tslot-2020-end-tap-m5` | M5, 15 mm deep, in the Ø4.2 mm centre hole | MISUMI (alterations table; HFS5 page) |
| `mgn12-rail` | 12 × 8 mm rail; holes every 25 mm, E = 10; Ø6 × 4.5 counterbore, Ø3.5 through, M3×8 | HIWIN MG series |
| `bearing-608-bore` | Ø8 bore, 7 mm wide | SKF 608 listing (123Bearing) |
| `prop-shaft-m5` | M5 shaft thread; Ø5 shaft; Ø5 hub hole | BrotherHobby, iFlight, HQProp |
| `battery-strap-20mm` (provisional) | 20 mm strap width | GEPRC GEP-MK5 |
| `meanwell-lrs-200-base-m4` | 4-M4, 3 mm deep, on 150 × 50 mm, 32.5 from the ends | Mean Well LRS-200 spec |
| `meanwell-lrs-200-side-m4` | 2-M4 per side, 5 mm deep, 150 apart, 12.5 above the base | Mean Well LRS-200 spec |
| `omron-d2f-mount-m2` | 2 × Ø2 (+0.12/0) holes, 6.5 ±0.15 apart, M2 screws | Omron D2F datasheet |
| `shaft-8mm` | Ø8 g6 (−0.005/−0.014) plain shaft in a host's 8 mm bore (the idler axle seat) | MISUMI SFJ / PSFJ |
| `m5-bolt-axle` | an M5 screw's shank (d 5) as the axle of a 5 mm bore (idler, F695, DIN 988 shim) | Keller & Kalmbach, NSK, KB-3D |
| `m5-clearance-hole` | an M5 screw through a host's clearance hole, head on the face (ISO 7380-1 dk 9.5, ISO 4762 dk 8.5) | Keller & Kalmbach |
| `m5-screw-joint` | bolt pattern of one M5 screw: the clamped part's clearance-hole side (male) into an M5 thread under the face (female), e.g. a T-nut (thread length 5); both framed on the clamped face | MISUMI HNTAP5, Keller & Kalmbach |
| `m5-axle-stack-face` | neutral face contact of parts stacked on one M5 axle (d1 5, the 5 × 10 shim's annulus) | Keller & Kalmbach (DIN 988), VoronDesign |
| `bearing-f695` | 5 × 13 × 4 flanged bearing, flange 15 × 1, in a Ø13 housing | NSK F695ZZ |
| `bearing-625-bore` | a Ø5 shaft through a 625's 5 mm inner ring | SKF 625-2RS1, MISUMI SFJ |
| `z-drive-pulley-hub-5mm` | a GT2 pulley's Ø5 set-screw hub (M3 set screws) on the Z drive's Ø5 D-cut shaft; kept apart from `nema-17-shaft-5mm` so no Z-shaft pulley mates a motor by accident | MISUMI GPA and SFJ, VoronDesign |
| `z-belt-gt2-9mm-clamp` | a 9 mm GT2 belt end in a clamp's jaw, framed on the wall its back bears on (2 mm pitch, B 1.52, T 0.76) | Gates 17195, VoronDesign |
| `m3-screw-joint` | as `m5-screw-joint`, at M3: a clamped part or stack into an M3 thread under its face (a T-nut) | MISUMI (HNTAP5 in M3/M4/M5) |
| `tslot-2020-blind-joint-m5` | 2020 blind joint: M5 tapped end (15 deep) with an ISO 7380-1 M5 head in the partner's 6 mm slot; sym 4; the access hole is not modelled (no cited number) | MISUMI, Keller & Kalmbach, VoronDesign |

## What the lane checks

`hyperobjects_standard_parts.check` runs as the third verdict of the existing `vocab`
command, so CI's Vocabulary step covers it with no workflow change:

```
$ y4d-spec vocab
…
y4d-spec vocab standard-parts: parts=33 interfaces=99 failures=0
standard_parts_status: parts=33 interfaces=99 dimensions=214 parameters=32 classes=12 review: signed=0 draft=33
```

1. Schema-valid; the file is named for its `key`.
2. `name`, `description` and every label non-blank in es/en/fr/pt.
3. `reviewed` names a reviewer and has no `generated` language facet.
4. The governing citation, every dimension and every parameter `source` index exists.
5. Parameter ids are unique and `min ≤ default ≤ max`.
6. Interface ids are unique; every `size_key` resolves through the membership rule;
   `geometry_type` equals the size key's; `frame.part`, if written, is the entry key.
7. Every frame component (and every `travel.range` bound, with lower < upper) evaluates at
   the defaults and at each parameter's `min` and `max`; every identifier an expression reads is a declared parameter listed in the
   interface's `parameters`, or one of the interface's `let` names (no `let` may shadow a
   parameter or form a cycle).
8. At each of those points the normal and `x_axis` are unit vectors and orthogonal
   (`AXIS_TOLERANCE = 1e-9`).
9. Belt facts (ASM-1 §9, 0.7.0): a `belt` block (category `belt` only, and required there)
   and a `belt_engagement` cite sources that exist and state positive numbers in mm; the
   engagement's `center` and `axis` read only the parameters it lists, evaluate at the
   same points, and give a unit `axis`.

`y4d-spec vocab --standard-parts DIR` checks another catalog directory.

**Frame evaluator.** Frame components are evaluated by `y4d_spec.frame_eval`, the ASM-1 §1
evaluator the assembly validator and the render-time frame gate also use: the grammar
check first, then a hand walk over floats; nothing reaches `eval`.

## Belts and belt engagement (ASM-1 §9)

An assembly's declared belt paths ([ASSEMBLIES.md](ASSEMBLIES.md#belt-paths)) read two
optional blocks:

- **`belt_engagement`** on a pulley, an idler or a bearing used as one: exactly one of
  - `pitch_diameter`: a toothed part; the diameter the belt's pitch line runs on;
  - `running_diameter`: a smooth part; the surface the belt runs on.

  It also holds `center` (a frame-grammar point on the axis, in the belt mid-plane),
  `axis` (an exact unit vector), `parameters` (the ones `center` reads) and `plane_note`,
  which says whether the mid-plane position is cited or a convention.
- **`belt`** on an entry of category `belt` (required there, refused elsewhere): `pitch`
  and `width`, and optionally `height` (B), `tooth_depth` (T), `pitch_line_differential`
  (U), the derived `teeth_side_offset` (T + U) and `back_side_offset` (B − T − U) that a
  smooth via needs, and `loop_length` for a closed loop. A belt may declare no
  interfaces: a closed loop has no end or seat to mate.

| Entry | `belt_engagement` | Mid-plane |
|---|---|---|
| `gt2-pulley-20t-5mm` | `pitch_diameter` 12.73 mm (Gates 20-2MR-PS-4, the 2 mm GT2 stock-pulley table via CMT Co.; = 20 × 2 / π) | z = 8, **a convention** (mid-length; no source places the toothed section) |
| `gt2-idler-20t-9mm` | `pitch_diameter` 12.73 mm (the same table: a 20-tooth 2 mm GT2 wheel) | z = `width_mm` / 2, **a convention** (flanged both sides) |
| `gt2-pulley-16t-5mm` | `pitch_diameter` 10.19 mm (MISUMI GPA 2GT table; Gates 2MR-16S 0.401 in) | z = 12.85, **derived** from MISUMI's L 18 and W 10.3 (L − W/2) |
| `gt2-pulley-20t-9mm` | `pitch_diameter` 12.73 mm (MISUMI GPA 2GT table) | z = 14.35, **derived** from MISUMI's L 21 and W 13.3 |
| `gt2-pulley-80t-5mm` | `pitch_diameter` 50.93 mm (Gates 2MR-80S, 2.005 in) | z = 13, **derived** from the listing's hub 8 and overall 18 |

Adding `belt_engagement` changed both entries' catalog digest, so assembly A's digest
moved (`24322cc0…` → `296caa36…` on the keystone's fixture A).

## Envelopes (ASM-1 §3.7, `--collision`)

`envelope: {solids, parameters?, note}` is the part's collision body: a union of
axis-aligned boxes (`min`, `max`) and cylinders (`base`, `axis` x|y|z, `radius`,
`length`) in the model frame, in the frame grammar over the entry's parameters. Every
solid names the cited `dimensions` it is built from in `from` (catalog rule 10). A shape
no cited dimension bounds is left out and `note` says so — never guessed.

| Entry | Solids | Left out (and why) |
|---|---|---|
| `extrusion-2020` | the 20 × 20 profile over `length_mm` | the slots (no cited depth): a key or nut in a slot is a declared overlap |
| `mgn12-rail` | the 12 × 8 section over `length_mm` | counterbores |
| `mgn12h-carriage` | a top slab and two skirts that leave the 12 mm rail channel open (`rail_width` now cited on the entry, HIWIN WR) | end seals, grease nipple |
| `nema-17-48mm` | body, pilot, shaft | — (a pulley on the shaft is a declared overlap) |
| `gt2-pulley-20t-5mm`, `gt2-idler-20t-9mm`, `bearing-608`, `bearing-f695`, `shim-5x10`, `shaft-8mm` | cylinders at the cited diameters and widths | bores (a union has no holes) |
| `bhcs-m5x30`, `shcs-m5x40` | head and shank | sockets |
| `bearing-625`, `shaft-5mm` (over `length_mm`) | cylinders at the cited diameters and widths | bores, the shaft's D cut |
| `bhcs-m5x10`, `bhcs-m5x16` | head and shank | sockets |
| `gt2-pulley-80t-5mm` | the Ø20 × 8 hub, then the Ø54.7 flanged section to 18 (the listing's 'Small' variant) | the bore |
| `prop-5in` | the swept disc (5 in) over the hub thickness | blade shape |
| `fc-stack-30x30`, `vtx-antenna-sma`, `psu-meanwell-lrs-200` | the cited board, body or case | — |
| `bed-plate-350` | the 355 × 355 outline over `thickness_mm` | holes and chamfers (no hole pattern is published) |

**No envelope yet** (no source the entry cites bounds the body): `microswitch-d2f` (no
body height), `tnut-2020-m5` and `tnut-2020-m3` (no nut height under the face), `motor-2207` (whether
Ø28.5 × 33.1 includes the shaft protrusion is not stated), `fpv-frame-5in-x-225` (a
class: arm shape varies), `fpv-camera-micro-19mm` (the body's position along the
optical axis from the screw axis), `sma-bulkhead-jack`, `gt2-pulley-16t-5mm` and `gt2-pulley-20t-9mm` (their entries cite
the tooth O.D. but no flange diameter), `gt2-belt-9mm` and `gt2-belt-loop-188mm` (a belt
is a declared path, not a rigid body). A component of one of these
reads `collision-unchecked`.

## Interface travel (ASM-1 §9, v1.4)

An interface that is a run may declare `travel: {axis, range: [lower, upper]}`, in mm,
along one axis of its own frame. The range is in the frame grammar over the entry's
parameters, which the interface lists in `parameters`. An assembly mate's `offset`
(a station on the mate) must stay inside it. `extrusion-2020`'s eight `slot_*`
interfaces travel along x, the extrusion axis toward end B, over the whole slot,
measured from the station. Its blind stations do not travel.

## Adding a part

1. Read the facts from a public datasheet, standard or manufacturer page; record each
   source with what it `supports`. A retailer listing is acceptable when the maker's page
   is unreachable; say so in the source title.
2. Write the frame convention first, then the interface frames in it. Prefer frames tied
   to features (a hole-pattern centre, a screw axis) over uncited offsets.
3. Use an existing `interface-sizes` key when the fit is the same; otherwise add a cited,
   quadrilingual draft key to the supplement.
4. Run `y4d-spec vocab` and `pytest tests/test_standard_parts.py`.
