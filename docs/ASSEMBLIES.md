# Type-level assemblies (ASM-1 §2–§3, §5)

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
| 7 | `--collision`: not implemented in v1, see below | `collision` (warning) |
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
closes the camera between the side plates at +30°, the angle the geometry realises, so it
validates unchanged; stating 31° there is now:

```
FAIL closure: [camera_on_right_plate] frame.camera_plate_right ↔ camera.side_face_right
  does not hold (closes a cycle): origins 0.0000 mm apart (≤ 0.05); normals 0.0000° from
  antiparallel (≤ 0.5); stated angle_deg 31° but the geometry realises 30° (1.0000° apart, ≤ 0.5)
```

When an interface of a continuous closing mate declares no `x_axis`, the angle is only a
placement convention and cannot be compared; the mate warns `angle-unchecked` instead of
passing in silence. If a cycle-closing mate holds only at a different index of its
symmetry than the one the document states, that is a **warning** (`closes at
rotation_index 0, but the document states 2`) rather than an error. The two are the same
physical mating.

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
| Shell | `https://id.madfam.io/aas/assembly/{slug}/{digest16}`; specificAssetIds `commons`, `slug`, `assembly_digest` (the full digest) |
| `Nameplate` | as for a cartridge; the product URI is the document's folder in the solid commons |
| `AssemblyDocument` (MADFAM `smt/assembly-document/1/0`) | the document exactly as checked, as a `Blob` of its canonical JSON, plus `AssemblyDigest` and `DigestAlgorithm` |
| `BillOfMaterials` (IDTA 02011-1-1 HSEBoM when conformant) | `EntryNode` = the assembly; one `Node` per component with a `HasPart` from the entry node. A cartridge node names `asset/solid/{slug}`, carries the GOC-1 `instance_id` as a specificAssetId and a `DerivedFrom` reference to the exact type shell revision `aas/solid/{slug}/{tree16}`; a standard node names `asset/standard/{key}` (catalog key); an external node is a CoManaged entity with name, licence, URL and revision. `CountsBySource` aggregates the BoM by source |
| `Mates` (MADFAM `smt/assembly-mates/1/0`) | one `AnnotatedRelationshipElement` per mate between the two component nodes, annotated with the interfaces, the stated rotation, `ThetaDeg`, `InTree`, the residuals, `MeasuredDeg` and `Validated` |
| `AssemblyPlacement` (MADFAM) | each component's 4 × 4 world transform, row-major, mm, 9 decimals |
| `CapabilityDescription` (producers; IDTA 02020-1-0 when conformant) | one `CapabilityContainer` per process in `capability_profile.process`, the other capabilities as its `PropertySet` |
| `RequirementProfile` (products with `requirements_rollup`) | each fabricated component's `requirements` (top level and the parts it produces), and the union of their processes |

The environment is a function of the document and the report alone, so any holder of
the same components derives it byte for byte. `hyperobjects_aas.resolver` is the other
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
their eight cartridges (CERN-OHL-W-2.0, see its NOTICE.md) and the golden environments;
`scripts/refresh_assembly_golden.py [--check]` rebuilds them.

## `capability_profile`

A producer's `capability_profile` uses the `fabrication-capabilities` vocabulary, and
step 1 checks it: every key is in the vocabulary, every value has its `value_type`, an
enumerated capability uses its `allowed_values`, and `process` is a **list** of
`processes` keys (`{"process": ["fff"]}`), like `requirements.process` (SEM-1 §2.4). A
bare string is refused by the schema. The vocabulary typed `process` as a string until
0.5.0; ASM-1, this document and both commons assemblies already wrote a list (P4-ASM2
finding 5), so the vocabulary and the schema now say the same.

## Limits in v1

- **No collision check.** `--collision` adds a warning that says no mesh intersection
  was checked, and the summary line prints `collision=not run`. A requested check that
  did not run never reads as a pass. ASM-1 §3.7 makes it reported, not gating, in v1.
- **Butt joints are invisible to the mating rule** (P4-ASM2 finding 3a). An extrusion
  end pressed against another extrusion's face has no mate: the end taps are female
  interfaces with nothing male to receive them. A slot station that drives `frame_z`
  1 mm into `frame_x` still validates; the commons' render probe measured 400 mm³ of
  overlap in that case. Only a collision check (`--collision`, still a stub), or a planar
  end-face interface that two extrusions could mate on, would catch it.
- **Frames are not yet in the commons main.** At the time of writing, no cartridge on
  solid-hyperobjects main declares a frame; every interface reports `declares no frame`
  when mated. Frames arrive one cartridge per PR (solid-hyperobjects #111–#120 and on),
  each proven by the render-time frame gate.
- The standard-parts loader is tolerant about shape until the catalog's own schema
  lands. It accepts any `*.json` with a string `key`, `parameters` as a list or as a
  mapping, `interfaces` or `cdg_interfaces`, and a frame with no `part`.
