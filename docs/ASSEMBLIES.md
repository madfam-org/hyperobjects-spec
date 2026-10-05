# Type-level assemblies (ASM-1 §2–§3, §5, §9)

An **assembly** says which components are mated at which interfaces: commons cartridges
at given parameters, standard (COTS) parts from a catalog, and external third-party
designs that are referenced by name, licence and URL. `y4d-spec assembly check`
resolves every component, places it in world space, and then checks every mate against
the SEM-1 mating rule. "Finalising" an assembly means that this check passes.

```bash
y4d-spec assembly check assemblies/fpv-5in-freestyle/assembly.json \
    --commons ../solid-hyperobjects --standard-parts ./standard-parts
y4d-spec assembly check assembly.json --commons DIR --json   # the report as JSON
y4d-spec assembly check assembly.json --commons DIR --collision
y4d-spec assembly check assembly.json --standard-parts A --standard-parts B   # tried in order
y4d-spec assembly check assembly.json --commons DIR --pose-samples 64         # ASM-1 §9 sweep
y4d-spec assembly poses assembly.json --commons DIR --out a.poses.json        # golden poses
y4d-spec assembly kinematics assembly.json --commons DIR --out a.kinematics.json  # compiled model
```

The exit code is 0 when there are no errors, 1 when there is any error, and 2 when the
document cannot be read or a directory option does not exist. `--commons` is needed
only by cartridge components, and `--standard-parts` only by standard components. If a
component needs a directory that was not given, it gets a resolution error that names
the option.

## The document (`assembly.schema.json`)

```jsonc
{
  "format": "hyperobjects.assembly", "format_version": "1.0.0",
  "slug": "fpv-5in-freestyle",
  "kind": "product",                       // or "producer" (a fabrication machine model)
  "name": {"en": "…", "es": "…"},
  "license": "CERN-OHL-W-2.0",             // this document's licence
  "root": "frame",                         // placed at the world origin
  "components": [
    {"id": "frame", "source": {"type": "standard", "key": "fpv-frame-5in-x-225"}},
    {"id": "pod_fl", "source": {"type": "cartridge", "commons": "solid",
      "slug": "motor-soft-mount", "mode": "soft_mount", "part": null,
      "parameters": {"motor_pattern": "16x16"}}},
    {"id": "motor_fl", "source": {"type": "standard", "key": "motor-2207"}},
    {"id": "toolhead", "source": {"type": "external", "name": "…", "license": "GPL-3.0",
      "url": "https://…", "interfaces": [ /* SEM-1 interface facts, numbers only */ ]}}
  ],
  "mates": [
    // The frame's motor mount carries the pod's underside clamp; the motor then bolts
    // to the pod's top bolt pattern (ASM-1 v1.1 §2 corrects v1.0's example, which
    // mated the frame to the pod's motor-side pattern).
    {"id": "m1", "a": {"component": "frame", "interface": "motor_mount_fl"},
     "b": {"component": "pod_fl", "interface": "arm_clamp"}, "rotation_index": 0},
    {"id": "m2", "a": {"component": "pod_fl", "interface": "motor_bolt_pattern"},
     "b": {"component": "motor_fl", "interface": "base"}, "rotation_index": 0}
  ],
  "capability_profile": {"process": ["fff"]},   // producers only
  "requirements_rollup": true
}
```

- One component entry is one physical instance. There is no `quantity`; a bill of
  materials counts entries by source.
- A mate states exactly one rotation. Use `rotation_index` (0 ≤ i < symmetry) for
  interfaces with discrete symmetry (1, 2, 3, 4, 6, 8). Use `angle_deg` for continuous
  symmetry (0). The schema rejects a mate that states both or neither. The validator
  rejects a rotation that does not fit the interfaces' symmetry.
- An external interface declares `frame`, `polarity`, `size_key` and `symmetry`, and its
  frame components are plain numbers because there are no parameters to read. No CAD is
  vendored.
- A `product` must not carry a `capability_profile`.

## Frame expressions (ASM-1 §1, grammar v1.1)

Frames on cartridges and standard parts are expressions the keystone evaluates with a
safe AST walker (`y4d_spec.frame_eval`: an allow-list, no attribute access, no `eval`).

| Since | Grammar |
|---|---|
| v1.0 (SEM-1 §2.3) | numeric literals, parameter ids, `+ - * /`, parentheses, unary minus, `min`, `max`, `abs` |
| v1.1 (hyperobjects-spec 0.4.0) | `let` names; `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2(y, x)` in **degrees** (the OpenSCAD convention; exact at 0/30/45/90° and their reflections); `sqrt`, `floor`, `ceil`, `round` (half away from zero); `< <= > >= == !=` yielding 1 or 0 (a chain such as `a < b < c` is refused); `iif(cond, a, b)` (lazy: only the chosen branch is evaluated) |

- **Purely numeric.** No string ever enters an expression. A select whose options are
  spelled `"NEMA17"` reaches a frame only through a `let` lookup.
- **Domain errors are errors.** `asin(2)`, `sqrt(-1)`, `tan(90)`, `atan2(0, 0)` and a
  division by zero raise `FrameEvaluationError` at that parameter point; nothing returns
  NaN. `asin`/`acos` absorb 1e-12 of float noise past ±1.
- **256 characters** per expression and per `let` entry.

### `let`: derived values

```jsonc
"let": {
  "pilot_r": {"param": "motor_size", "map": {"NEMA17": 11.0, "NEMA23": 19.25}},
  "half_span": "hole_span / 2"
},
"frame": {"part": "l_bracket", "origin": [0, "pilot_r + wall", "half_span"], …}
```

- **Placement.** `let` is a key of a `cdg_interfaces[]` entry (and of a standard-part
  interface). It sits beside `frame` and `size_key {param, map}` rather than once per
  manifest, because the interface is the unit that travels: into the AAS
  `MatingInterfaces` element (projected as `Let`), into the standard-parts shape, and
  into a service that re-evaluates one stored interface.
- **Entries.** An entry is either:
  - an expression over parameters and the block's other names; or
  - `{param, map}`, a lookup of a **select**'s option value. Its right-hand values are
    numbers only.
- **Order rule.** Entries are evaluated in **dependency order**, not key order. A JSON
  object is unordered (RFC 8259), and Postgres `jsonb` re-sorts keys, so the order the
  keys were written in is not a fact that survives storage. Any entry may read any other
  entry, provided there is no cycle.
- **Check-time errors** (`y4d-spec check`):
  - a cycle, named in full (`a → b → a`, including an entry that reads itself);
  - an unknown name;
  - a name that shadows a parameter or a function;
  - a right-hand value that is not a number;
  - a map that does not cover **exactly** the select's options. A missing option is an
    error here, so the gap fails visibly before anything evaluates.
- **Evaluation-time error.** A select value with no map entry is still an error at that
  parameter point, for a manifest that skipped the check.

### Slider size keys

`size_key: {"param": <slider or number>, "map": {"9.5": "omron-d2f-mount-m2"}}` matches the
slider's value **exactly**, after GOC-1 canonical number normalisation (`12.0` → `"12"`).
The rules:

- **Map keys** must be written in canonical form and must lie inside the slider's range.
- **Coverage.** Coverage is not required.
- **A value with no entry.** The interface has *no size key* at that point. A mate that
  needs one fails there and names the value: `has no size_key at hole_span = 7.3: its
  slider map matches exact values only (…)`.
- **Selects** keep their `{param, map}` form, with full coverage required.

### Forward compatibility

A manifest that uses any v1.1 feature needs **hyperobjects-spec ≥ 0.4.0**.

- **Under 0.4.0 or later.** `y4d-spec check` prints one note naming the features:
  `frame grammar: uses ASM-1 v1.1.0 features (comparison, iif, let, slider size_key, trig) —
  needs hyperobjects-spec >= 0.4.0; …`.
- **Under an older pin.** The pin does not know the features and fails the manifest on
  them. Captured from pin `6737b81` (0.3.0):

```
FAIL …: frame.origin[0]: expression 'pilot_r * cos(0)' references unknown parameter 'pilot_r'
FAIL …: frame.origin[0]: expression 'pilot_r * cos(0)' calls 'cos', not one of min, max, abs
FAIL …: frame.origin[2]: expression 'iif(plate_thick > 3, …)' uses a character outside the grammar (…)
FAIL …: size_key.param: 'foot_drop' is a 'slider' parameter; only a select chooses among sizes
```

So a commons repins before it merges the first cartridge that uses v1.1. From 0.4.0 on,
an unknown function or character names the grammar version and the minimum keystone
(`… (frame grammar v1.1.0, hyperobjects-spec >= 0.4.0; a newer keystone may define it)`),
so the next grammar step will explain itself to this one.

## What the check does

| Step | What is checked | Finding codes |
|---|---|---|
| 1 | The schema; unique component and mate ids; `root` exists; every mate endpoint exists; no component mates with itself; a producer's `capability_profile` is in the `fabrication-capabilities` vocabulary | `schema`, `component-id`, `mate-id`, `root`, `mate-endpoint`, `capability` |
| 2 | Every component resolves. A cartridge's mode must exist. A named part must be one the mode produces. Every given parameter must be declared and admissible. | `resolve` |
| 3 | For each mate: both interfaces exist and can mate (their frame evaluates and sits on a part the component produces, and they declare `polarity`, `size_key` and `symmetry`); the `size_key` values are equal; the polarities are complementary (male with female, neutral with neutral); the symmetries are equal; the rotation fits | `interface`, `size_key`, `polarity`, `symmetry`, `rotation` |
| 4 | Placement by BFS from the root over the mates that passed step 3 | — |
| 5 | Closure: every mate, including the ones the BFS tree did not use, is re-checked in world space; on continuous symmetry the stated `angle_deg` too, when both frames declare an `x_axis` | `closure` (error), `rotation`, `angle-unchecked` (warnings) |
| 6 | Every component is reachable from the root | `unreachable` |
| 6b | ASM-1 §9 (v1.3): joints, machine bindings and paths are consistent; the pose sweep (each limit, then the Halton samples) re-checks every mate and cycle, passive and follower joints stay inside their limits, and every belt path is planar at home with its length reported at every pose. See [Kinematics](#kinematics-joints-axis-bindings-belt-paths-the-pose-sweep-asm-1-9-v13) | `joint`, `machine`, `pose-closure`, `joint-limit`, `path` (errors), `path-length` (warning) |
| 7 | `--collision`: rigid-body interference at every pose (see [Collision](#collision---collision-asm-1-37)) | `collision`, `allowed-overlap` (errors), `collision-unchecked`, `allowed-overlap-unused` (warnings) |
| 8 | The report, the placement table and the assembly digest | — |

A parameter value is **never clamped**. A value outside `[min, max]`, an option that a
select does not offer, a non-boolean checkbox, or an undeclared key is a resolution
error. A clamped value would describe a different part from the one the document names.

The check does **not** test whether a `size_key` is a term in the `interface-sizes`
vocabulary. That is the lexicon's rule. The check also cannot tell whether a frame
matches the rendered geometry. That is the job of the render-time frame gate
(ASM-1 §8). A frame that this validator accepts is self-consistent, but that does not
make it trusted.

## The placement math

Each component `c` has a world transform `T_c`, a 4×4 rigid matrix that maps
component coordinates to world coordinates. The root has `T_root = I`. An interface frame
`F` has origin `o`, unit normal `n` and unit in-plane axis `x`, with `y = n × x`. Its
matrix `H(F)` has the columns `(x, y, n, o)`. When the frame has no `x_axis` (which is
allowed only for symmetry 0), `y4d_spec.frame_eval` supplies a deterministic
perpendicular.

When a mate `a → b` is traversed from an already-placed `a`:

```
T_b = T_a · H(F_a) · Flip · Rz(θ) · H(F_b)^-1
Flip = diag(1, -1, -1)        (a half-turn about the frame x-axis: n → −n)
θ    = 360° · rotation_index / symmetry      (or angle_deg when symmetry = 0)
```

`M = Flip · Rz(θ)` is itself a half-turn, about the in-plane axis at −θ/2, so `M⁻¹ = M`
and **the relation is symmetric**. Traversing the same mate from `b` gives
`T_a = T_b · H(F_b) · M · H(F_a)^-1`, so the validator places a component from whichever
side reaches it first. The BFS visits mates in document order, which makes the tree
deterministic, and with it the placement of an over-constrained assembly.

### Worked example 1: a NEMA 17 face on a flat bracket

The motor's face is at `z = 48` of its own model (the body occupies z 0–48 and the shaft
points up), with the normal +z and x = +x. The bracket's face is the top of its plate,
at `z = plate_thick = 5`, with the normal +z. Both have symmetry 4. Push a motor point
`(x, y, z)` through the factors from right to left with `rotation_index = 1`
(θ = 90°):

```
H(F_b)^-1  : (x, y, z − 48)
Rz(90°)    : (−y, x, z − 48)
Flip       : (−y, −x, 48 − z)
H(F_a)     : (−y, −x, 53 − z)            T_motor = [[0,−1,0,0],[−1,0,0,0],[0,0,−1,53]]
```

The motor hangs upside down above the plate. Its face rests on the plate top, and its
shaft points down through the plate, which is how a motor bolted to a flat bracket sits.
For `rotation_index` 0, 2 and 3 the first row is `(x, −y)`, `(−x, y)` and `(y, x)`
respectively. `tests/test_assembly_placement.py` asserts all four.

### Worked example 2: the same motor on a vertical wall

The angle bracket's face is at `(plate_thick, 0, wall_height) = (6, 0, 30)`, with
`n = (1, 0, 0)`, `x = (0, 1, 0)` and therefore `y = (0, 0, 1)`. A local point `(u, v, w)`
of that frame is the bracket point `(w + 6, u, v + 30)`. `Flip · H(F_b)^-1` sends a motor
point to `(x, −y, 48 − z)`, so the world point is `(54 − z, x, 30 − y)`:

```
T_motor = [[0,0,−1,54],[1,0,0,0],[0,−1,0,30]]
```

The face centre `(0,0,48)` lands at `(6,0,30)`. The motor normal +z becomes −x, which
is antiparallel to the wall's +x. When the motor is the root instead, the bracket gets
the inverse `[[0,1,0,0],[0,0,−1,30],[−1,0,0,54]]`.

### Worked example 3: continuous symmetry

A pulley bore (origin 0, `n = −z`, reference x = +x, so `H = Flip`) on a shaft tip at
`(0, 0, 72)` gives `T = T(0,0,72) · Flip · Rz(θ) · Flip = T(0,0,72) · Rz(−θ)`. The pulley
sits upright on the tip and is turned by `−angle_deg`.

## Closure (step 5)

For every mate whose two components are placed, both frames are taken to world space:
`W_a = T_a · H(F_a)` and `W_b = T_b · H(F_b)`. The mate holds when all of the following
are true:

| Residual | Definition | Tolerance |
|---|---|---|
| origin | `|o_a − o_b|` | ≤ 0.05 mm |
| normal | the angle between `n_b` and `−n_a` | ≤ 0.5° |
| x-axis | `φ` is the rotation the geometry realises: b's x-axis seen from `W_a` reads `(cos φ, −sin φ, ·)`. The residual is the distance from `φ − θ` to the nearest multiple of `360°/symmetry`; for symmetry 0 the period is 360°, so it is the distance from the stated `angle_deg` | ≤ 0.5°; for symmetry 0 only when both frames declare an `x_axis` |

Angles are measured with `atan2(|u × v|, u · v)`, because `acos` loses its precision
near 0° and 180°, which is exactly where a 0.5° tolerance is judged.

A mate in the BFS tree holds by construction (its residuals are about 1e-13), but it is
checked anyway. A mate that closes a cycle is the real test.

### Worked example 4: a ring of four elbows

Each elbow has its inlet at the origin facing −x and its outlet at `(arm, arm, 0)`
facing +y, with x = +z and symmetry 4. Four of them are chained outlet to inlet and
back to the first one. From `e1 = I`, the BFS places `e2 = T(50,50,0)·Rz(90°)` and,
through the last mate, `e4 = T(−50,50,0)·Rz(270°)`. Then it places
`e3 = T(0,100,0)·Rz(180°)`. The mate m3 (from e3 to e4) closes the cycle: e3's outlet
is at `(−50, 50, 0)`, exactly where e4's inlet is, so every residual is 0.

When e3's `arm` is set to 55 (which is in range), its outlet moves to `(−55, 45, 0)` and
e4's inlet stays where it was. The report then contains:

```
FAIL closure: [m3] e3.outlet ↔ e4.inlet does not hold (closes a cycle):
  origins 7.0711 mm apart (≤ 0.05); normals 0.0000° from antiparallel (≤ 0.5);
  x-axes 0.0000° apart modulo symmetry 4 (≤ 0.5)
```

`7.0711 = √(5² + 5²)`.

### Continuous symmetry closes too (0.5.0)

On a symmetry-0 mate the stated `angle_deg` is a fact about the geometry as soon as both
frames declare an `x_axis`: `φ` is measured on the full circle and must agree with it
within 0.5°. A mate in the BFS tree agrees by construction (it was placed at that angle);
a mate that closes a cycle is the real test. Before 0.5.0 any `angle_deg` passed there,
because the x-axis residual was skipped for symmetry 0 (P4-ASM2 finding 3b). Assembly B
closes the camera cage on the side plates' outer faces at 0°, the angle the geometry
realises, so it validates unchanged; stating 1° on the closing ear mate is now:

```
FAIL closure: [cage_ear_right_on_plate] frame.camera_plate_right_outer ↔
  camera_cage.cage_ear_right does not hold (closes a cycle): origins 0.0000 mm apart (≤ 0.05);
  normals 0.0000° from antiparallel (≤ 0.5); stated angle_deg 1° but the geometry realises 0°
  (1.0000° apart, ≤ 0.5)
```

When an interface of a continuous closing mate declares no `x_axis`, the angle is only a
placement convention and cannot be compared; the mate warns `angle-unchecked` instead of
passing in silence. If a cycle-closing mate holds only at a different index of its
symmetry than the one the document states, that is a **warning** (`closes at
rotation_index 0, but the document states 2`) rather than an error. The two are the same
physical mating.

## Kinematics: joints, axis bindings, belt paths, the pose sweep (ASM-1 §9, v1.3)

Contract v1.3 (hyperobjects-spec 0.7.0) makes an assembly posable. Everything here is
**optional and additive**: a document without `joint`, `machine` or `paths` validates
exactly as before, with one pose (home), and its digest does not move.

### Joints on mates

A mate may carry a `joint`, one degree of freedom between its two components:

```jsonc
{"id": "x_block_on_rail", "a": {"component": "x_rail", "interface": "track"},
 "b": {"component": "x_block", "interface": "rail_way"}, "rotation_index": 0,
 "joint": {"id": "x_carriage", "type": "prismatic", "axis": "x",
           "limits": [-100, 100], "home": 0, "note": "where the numbers come from"}}
```

- **Value 0 is the mate.** The mate's frames coincide at joint value 0. At value q the child
  (side **b**) is displaced from the parent (side **a**):
  - `prismatic`: along the named axis, in mm;
  - `revolute`: about it, in degrees, right-handed.
- **The axis** is `x`, `y` or `z` of side a's interface frame, where `z` is that frame's
  normal.
- **Direction.** Parent → child is the mate's a → b. Swap the sides to reverse it; the
  mating relation is symmetric.
- **Placement** extends the ASM-1 §3.4 formula with `J(q)`:

  ```
  T_b = T_a · H(F_a) · J(q) · Flip · Rz(θ) · H(F_b)^-1      (from a)
  T_a = T_b · H(F_b) · Flip · Rz(θ) · J(q)^-1 · H(F_a)^-1   (from b)
  ```

- **Limits.** `limits` is `[lower, upper]` with lower < upper. A prismatic joint must state
  it. A revolute joint without limits is continuous. `home` lies inside the limits.
- **Values are never clamped.** A value outside the limits is an error, as a parameter is.
- **Roles.** Every joint has exactly one:

| Role | Declared by | Its value |
|---|---|---|
| driven | `home` | set: a machine axis, a sample of the sweep, or `home` |
| follower | `follows: {terms: [{joint, scale}], offset}` (no `home`) | `offset + Σ scale · value(joint)`, from driven joints and earlier followers. D2: the four Z drives follow one logical Z joint; CoreXY motors follow `x ± y` |
| passive | `passive: true` (no `home`, no `follows`) | **measured** from the geometry. Its mate never places a component: it only closes a cycle, with the joint's degree of freedom free |

**A passive joint is how a closed chain moves.** The right carriage of a gantry beam rides
its rail passively: the beam places it, and its rail mate checks everything except the
travel along the rail. The travel must stay inside the joint's limits. A driven joint that
ends up closing a cycle is still checked at its set value, so declaring a carriage driven
where it should be passive fails the sweep, not home (a test pins this).

**Closure with a joint** compares `W_a · J(q)` with `W_b`, using the ASM-1 §3.5 residuals
and tolerances (0.05 mm, 0.5°). For a passive joint, q is first measured from
`W_a^-1 · W_b · Flip·Rz(θ)`:
- prismatic: the translation along the axis;
- revolute: the rotation about the axis, by `atan2`.

### Stations on the mate: `offset` (v1.4)

A part whose interface is a **run**, such as a slot along an extrusion, used to put every
partner at one station: `extrusion-2020`'s `slot_station_mm`, shared by its eight slots.
Two parts on the same extrusion at different stations could not both mate. With v1.4
(hyperobjects-spec 0.8.0), the station lives on the mate:

```jsonc
{"id": "bed_mount_on_front", "a": {"component": "frame_front", "interface": "slot_yp_a"},
 "b": {"component": "bed_mount", "interface": "foot_slot"}, "rotation_index": 0,
 "offset": {"axis": "x", "value": 160, "note": "160 mm past the station toward end B"}}
```

- **What it does.** Before the mate is formed, the named side's interface frame (`side`,
  default `a`) slides `value` mm along its own `axis`. Placement and closure use
  `H(F)·J(value)`, a prismatic joint fixed at that value, so the pose sweep, `pose()` and
  the golden poses need nothing new.
- **One or the other.** A mate carries an `offset` or a `joint`, never both (the schema
  says so).
- **Travel.** The interface may declare
  `travel: {axis, range: [lower, upper]}` (catalog: frame-grammar expressions over its
  parameters; external: numbers). The offset must be along that axis and inside the
  range, or the mate is an `offset` error; the value is never clamped. An interface
  without `travel` cannot be checked: the offset still places the part and the mate
  warns `offset-unchecked`.
- **`extrusion-2020`.** Every `slot_*` interface travels along **x**, its frame's x axis,
  which is the extrusion axis pointing toward end B. The run is the whole slot, end A
  (z = 0) to end B (z = `length_mm`), measured from the station:
  - `slot_*_a`: `[−slot_station_mm, length_mm − slot_station_mm]`;
  - `slot_*_b`: `[slot_station_mm − length_mm, slot_station_mm]`.

  The blind-joint stations declare no travel, because a blind joint's access hole is
  drilled at its station.
- **Not checked in v1.4:** the partner's footprint. A part whose station is inside the
  run but whose body overhangs the extrusion end is the collision check's to find, since
  no cited footprint exists yet.
- **Backward compatible.** `slot_station_mm` stays. A mate without an offset places
  exactly as before, so A and B validate unchanged. A's digest moves only because the
  `extrusion-2020` entry gained `travel` (an ordinary refresh).
- **Projection.** A mate with an offset carries `OffsetSide`, `OffsetAxis` and
  `OffsetMm` in `Mates`. A mate without one writes nothing new, so no projection version
  bump is needed.

### Machine-axis bindings

```jsonc
"machine": {"kinematics": "corexy",
            "axes": [{"axis": "x", "joint": "x_carriage"},
                     {"axis": "y", "joint": "gantry_y"},
                     {"axis": "z", "joint": "gantry_z", "scale": 1, "offset": 0}]}
```

- **Mapping.** `joint = scale · axis + offset`. The default is the identity; any other value
  is a convention and says so in `note`.
- **`kinematics`** names the class the firmware names, Klipper's `[printer] kinematics`
  (`cartesian`, `corexy`, …).
- **What the validator checks:**
  - every bound joint exists and is **driven**;
  - no axis is bound twice;
  - no joint is bound to two axes;
  - every scale is finite and non-zero.
- **Who computes poses (owner decision D4).** pravara forwards raw axis values. The viewer
  maps them through these bindings and computes the pose itself. pravara never computes
  kinematics.

### Belt paths

```jsonc
"paths": [{"id": "belt_a", "kind": "belt", "part": "gt2-belt-6mm", "closed": false,
           "via": [{"component": "toolhead", "interface": "belt_clamp_a"},
                   "idler_front_left",
                   {"component": "xy_joint_left_stack", "wrap": "cw", "side": "back"},
                   {"component": "motor_a_pulley"},
                   {"component": "toolhead", "interface": "belt_clamp_b"}]}]
```

- **`part`** is a catalog entry of category `belt`. Its `belt` block cites `pitch` and
  `width`, and optionally:
  - `height` (B), `tooth_depth` (T), `pitch_line_differential` (U);
  - `teeth_side_offset` (T + U) and `back_side_offset` (B − T − U);
  - `loop_length`, for a closed-loop belt. A belt may declare no interfaces at all.
- **A pulley or idler via** must resolve to a catalog part with a `belt_engagement`, which
  holds exactly one of:
  - `pitch_diameter`, for a toothed part;
  - `running_diameter`, for a smooth part (its running surface).

  It also holds the circle's `center` (a frame-grammar point in the belt mid-plane), its
  unit `axis`, and a `plane_note` saying whether the mid-plane is cited or a convention.
- **The via's side.** `side` is `teeth` (the default) or `back`. A toothed part takes only
  the teeth. On a smooth part the pitch line runs at `running_diameter + 2 · offset`, using
  the belt's offset for that side.
- **Wrap.** `wrap` is `ccw` (the default) or `cw`, seen from the path normal.
- **Anchors.** An anchor (`{component, interface}`, a belt clamp) is that frame's origin.
  - An open path starts and ends at an anchor and has none in between.
  - A closed path has none.
  - A belt with `loop_length` must be closed.
- **The path normal** is the first pulley's world axis, signed so that its largest world
  component is positive (a horizontal belt is seen from +z).
- **Planarity at home.** Every pulley axis is within 0.5° of the normal, and every via
  point is within **0.5 mm** of one plane. Both tolerances are conventions.
- **The length** is the pitch-line length: tangent spans plus wrapped arcs. Seen from the
  normal, use signed radii `s·r` (s = +1 for ccw, −1 for cw, 0 for an anchor). The span
  from circle i to i+1 leaves at `φ = atan2(Δ) − atan2(k, L)`, where
  `k = s₁r₁ − s₀r₀` and `L = √(|Δ|² − k²)`. The arc at a pulley is r times its turn,
  mod 2π, in the wrap's sense. The tests prove the textbook open-belt and crossed-belt
  formulas for two pulleys.
- **Reported:**
  - the length at home, with its tooth count (length / pitch);
  - the length at every pose of the sweep;
  - a closed-loop belt's catalog `loop_length` beside the computed one.
- **Warnings** (`path-length`, conventions):
  - the length spreads more than **0.1 mm** across the sweep (a CoreXY loop keeps its
    length);
  - a loop differs from its catalog length by more than **0.5 mm**. This is a warning, not
    an error, because a tensioner makes the centre distance a choice.
- **The digest.** The belt's catalog identity enters the assembly digest as `path_parts`,
  only when a document declares a path.

### The pose sweep

`assembly check` poses the assembly at:
1. **home**: every driven joint at `home`. This is the placement table, and the pose the
   AAS `AssemblyPlacement` records;
2. **the limits**: each driven joint at its lower, then its upper limit, with the others
   at home;
3. **the samples**: `--pose-samples N` (default **16**, a convention) points of a Halton
   sequence over every driven joint at once.

The sample formula: driven joint i (document order, from 0) takes
`lower + (upper − lower) · φ_p(k + seed − 1)` at sample k = 1 … N, where:
- φ_p is the radical inverse in the i-th prime base (2, 3, 5, …);
- the seed is 1, a convention;
- the value is rounded to 4 decimals;
- a continuous revolute joint is sampled over [−180, 180) and has no limit poses.

The sequence needs no random-number generator, so any language reproduces it.

At every pose, every mate and cycle must close within the ASM-1 §3.5 tolerances. Every
passive and follower joint must stay within its limits, with the same tolerance. The
sweep runs once home passes.

| Finding | Severity | When |
|---|---|---|
| `offset` | error | a mate offset along another axis than its interface's travel, or outside it (v1.4) |
| `offset-unchecked` | warning | a mate offset on an interface that declares no travel (v1.4) |
| `joint` | error | a duplicate joint id; limits not lower < upper; home outside the limits; `follows` naming an unknown, passive or own joint, a zero scale, or a cycle of followers |
| `machine` | error | an axis bound twice; a joint that is not driven or does not exist; a zero scale |
| `pose-closure` | error | a mate that holds at home fails at some pose; one finding per mate: the count and the first failing pose with its joint values |
| `joint-limit` | error | a passive (measured) or follower (computed) value outside its limits |
| `path` | error | the path problems above |
| `path-length` | warning | the length spreads across the sweep, or a loop differs from its catalog length |

**Budget.** 16 samples cost one placement and one closure pass per pose, in pure Python.
The 14-component fixture's 21 poses take about 0.08 s on a laptop, so the default fits
every-PR CI. Raise `--pose-samples` for a nightly.

### Reference forward kinematics and golden poses

```python
from y4d_spec.assembly import pose, pose_from_axes, golden_poses
pose(doc, resolver, {"x_carriage": 25.0})          # {component id: 4×4 world ← component}
pose_from_axes(doc, resolver, {"x": 25.0, "y": 3})  # through machine.axes
```

`pose` raises `PoseError` in any of these cases:
- an unknown joint;
- a follower or passive joint is given a value;
- a value that is not finite or lies outside its limits;
- an assembly that does not pass.

Joints that are not given stay at home, and followers are computed.

`y4d-spec assembly poses <assembly.json> --out F` (or `golden_poses_json`) writes the
**golden pose file**, `hyperobjects.assembly-poses` 1.0.0:

```jsonc
{"format": "hyperobjects.assembly-poses", "format_version": "1.0.0",
 "assembly": "<slug>", "assembly_digest": "<sha256>",
 "matrix_layout": "row-major 4x4, world <- component, mm",
 "number_format": "decimal string with exactly 6 places: …",
 "sweep": {"sequence": "halton", "samples": 16, "seed": 1},
 "joints": [{"id": "x_carriage", "type": "prismatic", "axis": "x", "role": "driven", "unit": "mm"}],
 "poses": [{"name": "sample-1", "kind": "sample",
            "inputs": {"gantry_y": 0.0, "x_carriage": -33.3333},
            "joints": {"gantry_y": "0.000000", "motor_rotation": "-299.999700", "x_carriage": "-33.333300"},
            "transforms": {"toolhead": ["1.000000", "0.000000", …16 entries]}}],
 "tie_guard": []}
```

- **`inputs`** are JSON numbers, which every language parses to the same double. They are
  what a viewer is given.
- **`joints`** holds the driven and follower values. A viewer computes the followers.
- **`transforms`** holds every component, 16 entries row-major.
- **The canonical number format.** Every computed number is a **string**: the exact binary
  value rounded to 6 decimals, ties away from zero. This is exactly JavaScript's
  `Number.prototype.toFixed(6)`; `"-0.000000"` is written `"0.000000"`.
- **`tie_guard`** lists the entries within 1e-9 of a rounding boundary, where a last-ulp
  difference between two correct implementations could flip the sixth decimal. Compare
  those numerically (|Δ| ≤ 1e-6) and every other entry as a string.
- **Passive joints** are not listed, since they place nothing.

The goldens are written by `scripts/refresh_pose_golden.py`; `--check` is a CI step:
- `tests/fixtures/assembly-golden/poses/` (A and B, rigid: home only);
- `tests/fixtures/kinematics/kinematic-gantry.poses.json`, a gantry fixture with a passive
  carriage closing a cycle, a follower pulley and a closed belt loop.

### The compiled kinematic model (a consumable export)

A viewer cannot pose from the golden pose file alone: placement needs every mate's frame
matrices, and those come from resolving the components (catalog, cartridge manifests,
interface expressions). Re-implementing that resolution in a viewer would be a second
copy of the keystone. So the keystone exports the compiled model instead:
`y4d-spec assembly kinematics <assembly.json> --out F` (or `kinematic_model_json`) writes
`hyperobjects.assembly-kinematics` 1.0.0:

```jsonc
{"format": "hyperobjects.assembly-kinematics", "format_version": "1.0.0",
 "assembly": "<slug>", "assembly_digest": "<sha256>",
 "matrix_layout": "row-major 4x4 flattened to 16, column vectors, mm",
 "number_format": "JSON numbers: the shortest decimal that round-trips …",
 "placement": "<the placement rule, stated in words>",
 "root": "u0",
 "components": [{"id", "source_type", "label",
                 "geometry": {"kind": "envelope", "solids": […]}
                           | {"kind": "cartridge", "commons", "slug", "mode", "instance_id", "parts", "parameters"}
                           | null}],
 "edges": [{"mate", "a", "b", "theta_deg", "h_a": [16], "h_b": [16], "joint": "<id>" | null}],
 "joints": [{"id", "mate", "type", "axis", "role", "unit", "parent", "child", "limits", "home",
             "follows": {"terms": [{"joint", "scale"}], "offset"} | null}],
 "machine": {"kinematics": "corexy", "axes": [{"axis", "joint", "scale", "offset"}]} | null}
```

- **`edges`** are `KinematicModel.edges` in order: the mates that passed, each with
  `H(F_a)` and `H(F_b)` after any mate `offset`, and the mate angle `theta_deg`.
- **`placement`** is `validate._place` in words: breadth-first from the root, edges in
  order, a passive joint's edge skipped; `T_b = T_a·H_a·J(q)·M·H_b⁻¹` from side a,
  `T_a = T_b·H_b·M·J(q)⁻¹·H_a⁻¹` from side b, with `M = Flip·Rz(θ)`.
- **Numbers** are JSON numbers in their shortest round-trip form, so a JavaScript
  `JSON.parse` reads exactly the doubles the keystone used.
- **`geometry`** is what a viewer can draw: a standard part's or external design's
  evaluated envelope (boxes and cylinders in the component's model frame, the same
  solids `--collision` uses), or the cartridge to render (its GOC-1 `instance_id`), or
  `null` when nothing is cited.

`scripts/refresh_pose_golden.py` writes `<name>.kinematics.json` beside every
`<name>.poses.json`, and `--check` guards both. `tests/test_assembly_kinematic_model.py`
proves the export is complete: a consumer reading only the model file reproduces every
string of every golden pose file. To match the goldens to the last digit, a consumer in
another language must also reproduce two Python details: `math.radians(x)` is
`x * (π / 180)` with the constant computed once, and `sum()` of floats (CPython ≥ 3.12)
is Neumaier-compensated, starting from the integer 0.

### Projection (projection version 2)

Every assembly shell gains a **`Kinematics`** submodel (MADFAM `smt/assembly-kinematics/1/0`):
- `KinematicsClass`, `JointCount`;
- `Joints`: per joint, the id, mate, type, axis, `AxisFrame` (`component.interface` of side
  a), role, unit, `Parent` and `Child` references to the BoM nodes, limits or
  `Continuous`, `Home`, `Follows` and `FollowOffset`, `Note`;
- `AxisBindings`;
- `Paths`: per path, the part and its asset id, `Closed`, `Via` (component, interface,
  wrap, side), `PitchLengthMm` at home, `LoopLengthMm`, `PlanarityMm`, `LengthSpreadMm`,
  `Validated`;
- `PoseSweep`: `Sequence`, `Samples`, `Seed`, `PoseCount`, `FailedPoses`, `Validated`.

It is a separate submodel rather than an extension of `Mates`, for three reasons:
- the joints, bindings and paths are facts about the mechanism, not about any one mate
  (a follower couples joints on different mates, and a path crosses many components);
- a reader that only needs the rigid structure keeps reading `Mates` unchanged;
- Phase 7 reads one submodel to pose the twin.

A rigid assembly carries it with no joints and one pose. The bytes of every assembly shell
change, so `PROJECTION_VERSION` is **2**.

**Projection version 3** (package 0.10.0, lane P6-PROJFIX). An assembly's bytes do not move:
the assembly half of the canonical-projection fix needs no bump, because every fixture already
writes whole numbers as integers. The bump comes from material cards, which are now projected
in the canonical form their `content16` hashes. That changes the `valueType` of a card's
whole-float values (`220.0` becomes `xs:integer`). The version is one for the whole package,
so every id moves to `…/p3`. See [The AAS projection](#the-aas-projection-asm-1-5).

## The assembly digest (`hyperobjects-assembly-v1`)

```
sha256( canonical_json({
  "algorithm":  "hyperobjects-assembly-v1",
  "document":   <the document as parsed>,
  "components": {<component id>: <resolved identity>}
}) )
```

`canonical_json` follows GOC-1 §3.1: integral floats become ints, keys are sorted, there
is no whitespace, and the output is UTF-8. Key order and `5` vs `5.0` therefore do not
matter. The document is hashed as written, so stating a default explicitly does change
the digest. The resolved identity of each source type is:

| Source | Identity |
|---|---|
| cartridge | `{"type": "cartridge", "instance_id": …}`: the GOC-1 `instance_id` over the cartridge's `tree_sha256`, mode, part and `variables_sha256` at full injection. `variables` covers every declared parameter except the engine-control keys (`render_mode`, `target_part`, `mode`) and the physical denylist read from `generator-output.schema.json` |
| standard | `{"type": "standard", "key", "catalog_sha256", "parameters"}`: the sha256 of the catalog entry's canonical JSON and the resolved parameter values |
| external | `{"type": "external", "facts": {…}}`: the declared name, licence, URL, revision and interfaces |

A document that declares belt paths (ASM-1 §9) adds `"path_parts": {<path id>: <the belt's
standard identity>}` to the hashed object; without paths the payload, and so every earlier
digest, is unchanged.

The digest is computed whenever every component resolves, even when a mate fails, so a
failing report still names the exact revision it judged. A cartridge's identity changes
when any file in its GOC-1 tree changes. A README does not count, because GOC-1 excludes
it. `tests/test_assembly_resolvers.py` pins a golden vector for an external-only
document.

## Calling it from another service

`validate_assembly(doc, resolver, *, collision=False) -> AssemblyReport` reads no files.
A resolver is any object with `resolve(component) -> ResolvedComponent`. On failure it
raises `ResolutionError(problems)`.

```python
from y4d_spec.assembly import (CompositeResolver, ResolvedComponent, resolve_interfaces,
                               cartridge_identity, goc1_variables, validate_assembly)

class StoredShellResolver:                      # e.g. over stored AAS submodels
    def resolve(self, component):
        manifest = {"parameters": [...], "hyperobject": {"cdg_interfaces": [...]}}
        given = component["source"].get("parameters")
        identity, details = cartridge_identity(slug=..., mode=..., part=...,
                                               tree_sha256=..., variables=goc1_variables(...))
        return ResolvedComponent(component["id"], "cartridge", "label", identity,
                                 resolve_interfaces(manifest, given), details)

report = validate_assembly(doc, CompositeResolver(cartridge=StoredShellResolver()))
report.ok, report.errors, report.warnings, report.placements, report.mates, report.digest
```

`resolve_interfaces(manifest, given, available_parts=…, default_part=…)` evaluates every
frame through `y4d_spec.frame_eval` and resolves every `size_key`. That keeps the frame
arithmetic in the keystone for every caller.

## The AAS projection (ASM-1 §5)

A checked assembly projects to one AAS v3.1 Environment:

```bash
y4d-spec aas build ../solid-hyperobjects/assemblies/fpv-5in-freestyle --out b.aas.json
y4d-spec aas check b.aas.json --basyx require
```

`aas build` recognises an assembly (a directory with `assembly.json`, or the file),
runs `assembly check` first, and projects only a passing assembly; a failing one is a
check error (exit 1) that prints the validator's findings. Cartridges come from
`--commons-dir` (default: the commons root two levels above `assemblies/<slug>/`) and
standard parts from `--standard-parts` (default: the catalog bundled with the package).

| | Identifier / content |
|---|---|
| Asset | `https://id.madfam.io/asset/assembly/{slug}` |
| Shell | `https://id.madfam.io/aas/assembly/{slug}/{digest16}/p{N}` (`N` = the projection version, SEM-1 §1; also the shell's `ProjectionVersion` extension); specificAssetIds `commons`, `slug`, `assembly_digest` (the full digest). Submodels are `…/sm/assembly/{slug}/{digest16}/p{N}/{idShort}` |
| `Nameplate` | as for a cartridge; the product URI is the document's folder in the solid commons |
| `AssemblyDocument` (MADFAM `smt/assembly-document/1/0`) | the document exactly as checked, as a `Blob` of its canonical JSON, plus `AssemblyDigest` and `DigestAlgorithm` |
| `BillOfMaterials` (IDTA 02011-1-1 HSEBoM when conformant) | `EntryNode` = the assembly; one `Node` per component with a `HasPart` from the entry node. A cartridge node names `asset/solid/{slug}`, carries the GOC-1 `instance_id` as a specificAssetId and a `DerivedFrom` reference to the exact type shell revision `aas/solid/{slug}/{tree16}/p{N}`, at the assembly's own projection version (the stored-shell resolver parses any version); a standard node names `asset/standard/{key}` (catalog key); an external node is a CoManaged entity with name, licence, URL and revision. `CountsBySource` aggregates the BoM by source |
| `Mates` (MADFAM `smt/assembly-mates/1/0`) | one `AnnotatedRelationshipElement` per mate between the two component nodes, annotated with the interfaces, the stated rotation, `ThetaDeg`, `InTree`, the residuals, `MeasuredDeg` and `Validated` |
| `AssemblyPlacement` (MADFAM) | each component's 4 × 4 world transform at the home pose, row-major, mm, 9 decimals |
| `Kinematics` (MADFAM `smt/assembly-kinematics/1/0`, ASM-1 §9, projection version 2) | the joints, machine-axis bindings, belt paths and the pose sweep's verdict; see [Kinematics](#projection-projection-version-2) |
| `CapabilityDescription` (producers; IDTA 02020-1-0 when conformant) | one `CapabilityContainer` per process in `capability_profile.process`, the other capabilities as its `PropertySet` |
| `RequirementProfile` (products with `requirements_rollup`) | each fabricated component's `requirements` (top level and the parts it produces), and the union of their processes |

The environment is a function of the document and the report alone, so any holder of
the same components derives it byte for byte. More precisely, it is a function of the
**canonical** document (GOC-1 §3.1), the form the digest hashes and the
`AssemblyDocument` blob stores. Before projecting, `project_assembly` normalises the
document, and a standard part's resolved parameter values, with `normalize_numbers`. So
`"c_end": 20.0` and `"c_end": 20` write the same bytes under the same id, and a whole
number's untyped `Value` is `xs:integer`. Before this fix, F1 of lane P6-ASM, the first
spelling projected `xs:double` from the author's document and `xs:integer` from the blob:
one digest, two byte projections, a latent 409. `tests/test_projection_canonical.py`
covers both paths and the property `project(doc) == project(canonical(doc))`. `hyperobjects_aas.resolver` is the other
half of that seam: `EnvironmentCartridgeResolver` resolves cartridge components from
**stored type shells** (`ParametricModel`, `GeometryProvision`, `MatingInterfaces`,
`RequirementProfile`), at the revision each node's `DerivedFrom` names
(`hyperobjects_aas.assembly.component_type_shells`). On assemblies A and B it reproduces
the commons digest and the whole environment; over the whole solid commons (502
cartridges, 1490 modes at their defaults) it gives the same identity and interfaces as
the manifest resolver. That is what lets asset-shells re-validate an assembly at publish
time without a commons checkout (ASM-1 §6):

```python
from hyperobjects_aas.assembly import (assembly_document_from_environment,
                                       build_assembly_environment, component_type_shells)
from hyperobjects_aas.resolver import EnvironmentCartridgeResolver, bundled_standard_parts_dir
from y4d_spec.assembly import CompositeResolver, StandardPartsResolver, validate_assembly

doc = assembly_document_from_environment(env)
resolver = CompositeResolver(
    cartridge=EnvironmentCartridgeResolver(component_type_shells(env), fetch),  # fetch(shell id)
    standard=StandardPartsResolver(bundled_standard_parts_dir()))
report = validate_assembly(doc, resolver)
assert report.ok and build_assembly_environment(doc, report) == env
```

A checkbox written as `0`/`1` projects as a boolean `Default` plus `DefaultAsWritten`
(the integer), because the GOC-1 identity hashes the value as written.

`tests/fixtures/assembly-golden/` holds byte-identical copies of assemblies A and B and
their nine cartridges (CERN-OHL-W-2.0, see its NOTICE.md) and the golden environments;
`scripts/refresh_assembly_golden.py [--check]` rebuilds them.

## `capability_profile`

A producer's `capability_profile` uses the `fabrication-capabilities` vocabulary, and
step 1 checks it: every key is in the vocabulary, every value has its `value_type`, an
enumerated capability uses its `allowed_values`, and `process` is a **list** of
`processes` keys (`{"process": ["fff"]}`), like `requirements.process` (SEM-1 §2.4). A
bare string is refused by the schema. The vocabulary typed `process` as a string until
0.5.0; ASM-1, this document and both commons assemblies already wrote a list (P4-ASM2
finding 5), so the vocabulary and the schema now say the same.

## Collision (`--collision`, ASM-1 §3.7)

`--collision` checks rigid-body interference at **every pose the sweep checks**: home, each
limit and each Halton sample. It needs the geometry extra (CadQuery).

- **The bodies.** Each component becomes a solid in its model frame:
  - a **cartridge** is rendered at the assembly's parameters (full injection, every part
    the component produces), through the same sandboxed execution `check --render` uses;
  - a **standard part** is its catalog `envelope`: a union of axis-aligned boxes and
    cylinders, each naming the cited `dimensions` it is built from (catalog rule 10);
  - an **external design** is its declared `envelope`, an original proxy body (owner
    decision D3), when it has one.
  A component with no solid (no envelope, a graph- or OpenSCAD-only cartridge, a render
  that raises) is named in a `collision-unchecked` warning and the summary reads
  `collision=partial`; nothing is skipped in silence.
- **The test.** The solids are placed by the validator's own transforms; every pair whose
  bounding boxes overlap is intersected (OpenCASCADE boolean common). A pair is computed
  once per relative placement, so a pair that does not move against itself costs one
  boolean for the whole sweep. Flush contact has zero volume.
- **The verdict.** An overlap above **1 mm³** (a convention: the bar the phase-4 render
  probes used) is a `collision` error naming the pair, the worst volume, its pose and how
  many poses it occurs at — unless the document declares it:

  ```jsonc
  "allowed_overlaps": [
    {"a": "z_idler_axle", "b": "z_idler_bracket", "max_mm3": 60,
     "reason": "the M5 shank cuts its thread in the Ø4.2 pilot"}
  ]
  ```

  A declared pair may overlap up to `max_mm3` at every pose; more is an error. A declared
  pair that never overlaps warns `allowed-overlap-unused`. `allowed-overlap` errors name a
  declaration of an unknown component, of a component with itself, or of a pair twice.
- **What envelopes leave out, and why it shows up as declared overlaps.** An envelope is
  built only from cited dimensions. A 2020 extrusion is its 20 × 20 profile: no source the
  catalog cites gives the slot depth, so a key or a T-nut seated in a slot overlaps the
  profile. Bores are not hollowed (a union of solids has no holes), so a shaft in a
  pulley, bearing or idler overlaps it. Each is a designed overlap the assembly declares
  with its reason; the measured volumes match the phase-4 probes (the roller-bracket key
  in the slot 208.8 mm³; the M5 axle in the Ø4.2 pilot 57.8 mm³).
- **Cost.** Assembly A (29 components) runs in about 7 s, B in about 3 s, on a laptop.

## Limits

- **Collision is opt-in.** Without `--collision` the summary prints `collision=not run`;
  the commons CI passes it. Components without a solid are reported, not checked.
- **Butt joints are invisible to the mating rule** (P4-ASM2 finding 3a). An extrusion
  end pressed against another extrusion's face has no mate: the end taps are female
  interfaces with nothing male to receive them. A slot station that drives `frame_z`
  1 mm into `frame_x` still validates; the commons' render probe measured 400 mm³ of
  overlap in that case. `--collision` now catches it (an undeclared overlap); a planar
  end-face interface that two extrusions could mate on would catch it in the mate rule.
- **Frames are not yet in the commons main.** At the time of writing, no cartridge on
  solid-hyperobjects main declares a frame; every interface reports `declares no frame`
  when mated. Frames arrive one cartridge per PR (solid-hyperobjects #111–#120 and on),
  each proven by the render-time frame gate.
- The standard-parts loader is tolerant about shape until the catalog's own schema
  lands. It accepts any `*.json` with a string `key`, `parameters` as a list or as a
  mapping, `interfaces` or `cdg_interfaces`, and a frame with no `part`.
