# hyperobjects-spec

**Validate a MADFAM hyperobject cartridge with zero platform code.**

The MADFAM commons has two halves. [solid-hyperobjects](https://github.com/madfam-org/solid-hyperobjects)
holds the **solid** cartridges — printed and machined bodies, rendered from CadQuery or
OpenSCAD by the [Yantra4D](https://github.com/madfam-org/yantra4d) platform.
[soft-hyperobjects](https://github.com/madfam-org/soft-hyperobjects) holds the **soft**
ones — garments, notions, fabric cards — for the
[Fashion Cabinet](https://github.com/madfam-org/fashion-cabinet) platform. Both are
commons: anyone may contribute a cartridge. Where each contract is consumed:
[Related repositories and contracts](#related-repositories-and-contracts).

Until now you could not check one without cloning a platform. The bar lived inside the
repos — half of it in an installable package, half in loose `scripts/qa/*.py` that
imported the API app. This package is that bar, extracted: one `pip install`, two
commands, no platform checkout.

```bash
pip install "hyperobjects-spec[geometry] @ git+https://github.com/madfam-org/hyperobjects-spec@main"

y4d-spec check ./my-cartridge --render          # a Yantra4D cartridge, geometry and all
fc-spec check garment-manifest ./my-garment.json
```

Passing these checks and passing the platforms' CI are meant to be the same thing.

---

## Install

```bash
# Manifest conformance only — pure python, runs in under a second.
pip install "hyperobjects-spec @ git+https://github.com/madfam-org/hyperobjects-spec@main"

# Plus geometry verification: actually renders your cartridge and inspects the mesh.
# Pulls a CAD kernel (~400MB), so it is opt-in.
pip install "hyperobjects-spec[geometry] @ git+https://github.com/madfam-org/hyperobjects-spec@main"
```

Python 3.11+.

These pin `@main` because no release tag exists for the current version; pin the tag
instead once one is cut.

**What `[geometry]` contains, and why none of it is optional inside the extra.**
`cadquery` (pinned `<2.8`) is the kernel; `trimesh` inspects the mesh; `scipy` and
`networkx` are the graph engines trimesh labels a mesh's connected components with, which
is how a body is counted and an inverted one found at all; **`rtree`** is what trimesh
builds the ray bounds tree with, and without it the thin-wall thickness measurement cannot
run. A package missing from that list does not quietly remove a measurement — see
**Printability notes** below.

**On Linux the CAD kernel also needs system libraries.** OCP's C extension links against
X and GL at import, so a Debian/Ubuntu machine needs `libgl1`, `libglib2.0-0` **and
`libxrender1`** — `libgl1` alone is not enough, because nothing in its dependency tree
pulls the `libXrender.so.1` that VTK's renderer asks for. Without them `import cadquery`
fails, and `--render` then refuses with exit `2` rather than downgrading silently. The CI
workflow installs exactly those three and fails the job if geometry still cannot import.

---

## `y4d-spec` — Yantra4D cartridges

```bash
y4d-spec check ./my-cartridge              # manifest + files
y4d-spec check ./my-cartridge --render     # + render every (mode, part) AND every preset
y4d-spec check ./my-cartridge --render --no-presets        # defaults only (weaker)
y4d-spec check ./my-cartridge --render --no-printability   # skip the print-time notes
y4d-spec check ./my-cartridge --render --openscad-path ./libs   # where OpenSCAD includes resolve
y4d-spec check ./my-cartridge --render --require-openscad       # a missing binary is a FAILURE
y4d-spec check ./my-cartridge --render --parity                 # + COMPARE both kernels of a dual-engine mode,
                                                                #   and a graph against its script twin
y4d-spec check ./my-cartridge --render --parity --parity-tolerance 0.01   # widen the AABB gate only
y4d-spec render-env                        # the render environment: packages, OpenSCAD, fonts
y4d-spec check ./cartridges/*/ -v          # many at once
y4d-spec rules                             # what gets checked, and where each rule came from
y4d-spec bundle check ./renders/           # GOC-1 variables.json + geometry (see "Generator output")
y4d-spec assembly check assembly.json --commons ../solid --standard-parts ./parts   # ASM-1 assembly
y4d-spec assembly poses assembly.json --commons ../solid --out a.poses.json   # ASM-1 §9 golden poses
y4d-spec aas build ../solid/assemblies/fpv-5in-freestyle --out b.aas.json   # ASM-1 §5 assembly shell
```

A cartridge directory is anything with a `project.json`. A directory you name that has
none is a **failure**, not a skip — deliberately: `check` verifies the paths you asked
it to verify, and an argument that silently checks nothing is how a typo'd cartridge
path reads green. So glob the level the cartridges are actually on
(`y4d-spec check ./projects/*/`, where every entry has a manifest) rather than a level
up, where a glob also sweeps in siblings like `libs/` that were never cartridges.

**What `check` does**

1. Validates the manifest against `project-manifest.schema.json`.
2. Applies the per-cartridge house rules — mode/part/parameter cross-references, the
   `target_part` dispatch alignment, `hyperobject` block coherence, `{en, es}`
   completeness, license declaration, and the structure of the semantic fields (interface
   frames, size keys, the requirement profile; see below). Every rule names its source;
   run `y4d-spec rules` to see them.
3. Checks the files: mode sources exist, no includes escaping the cartridge, no
   vendored tree, no shipped LICENSE contradicting the declared one, and **every
   declared parameter is actually referenced by a source** (below). As a note only,
   every manifest `default` that differs from the literal the source falls back to
   (`default-drift`, below).

**Every declared parameter must reach geometry.** A parameter the sources never read is
a control the UI offers that changes nothing, and it fails the check. OpenSCAD is where
this hides: the platform passes every parameter as `-D name=value`, and OpenSCAD accepts
a `-D` for a name the file never mentions **in silence** — so a `.scad` that declares
`phone_angle = 65;` at the top and never reads it renders the same solid at every
position of the slider, with no error anywhere. Four such dead sliders shipped in the
solid commons for exactly that reason.

Each dialect is asked the question its own way:

- `.py` / `.cq` — the bare identifier appears in the executable text. Parameters are
  injected as **bare globals** (`exec_globals.update(params)`), so `PARAM(lambda: wall,
  4.0)` counts because `wall` is in it, not because `PARAM` is special. Comments and
  string literals are stripped: naming a parameter in a docstring is not wiring it.
- `.scad` — the identifier is used **outside its own declaration line**, since the `-D`
  overrides that line. A use on the declaration's own right-hand side (`w = w * 2;`)
  counts; a mention in a `//` or `/* */` comment does not.
- `.graph.json` — the parameter carries a `binding` naming a node param
  (`"outline.r"`, or a list). Graph cartridges bind from the manifest side, so a graph
  parameter with no binding drives nothing.

A parameter is judged only against the modes that **list** it (`modes` /
`visible_in_modes`), so a parameter scoped to one mode and used there is alive even
though the cartridge's other modes never mention it. A reference from a library file the
cartridge **ships** counts — `include <>` is textual inclusion into the same variable
scope — while a target that resolves outside the cartridge (`BOSL2/std.scad`) is skipped
rather than assumed, so the rule can only ever miss a dead parameter, never invent one.
`target_part` is exempt: the runner injects it to select a body.

The deliberate case has a door, with the same shape and the same argument as a parity
exemption (G38) — an object whose `reason` is required and must be non-empty:

```json
{
  "id": "drainage_angle",
  "type": "slider",
  "default": 5.0,
  "intentionally_unused": {
    "reason": "reserved for the fluid-drainage mode that is not written yet"
  }
}
```

**A manifest default should be the source's default (`default-drift`, note only).** A
parameter's default is written twice: in `project.json` (what the UI shows, and what a
full-parameter render injects) and in the source (what the engine uses when the
parameter is *not* injected). A render that sends only some keys gets the source's
literal for the rest, so when the two differ the "default" instance has two geometries,
and a generator-output document (below) cannot record the one it rendered. The rule
reads the fallback the way each dialect spells it — `PARAM(lambda: id, <literal>)` in a
`.py`/`.cq` (and a Fashion Cabinet `script_file`) through `ast`, a top-level
`id = <literal>;` or `id = is_undef(id) ? <literal> : id;` in a `.scad` (following
in-cartridge `include <>`, last assignment winning), and the node literal a `binding`
targets in a `.graph.json` — and compares it with the manifest `default`: booleans equal
0/1, numbers within 1e-9, a numeric string equals the number it spells, other strings as
written. It is judged per `(file, line)` with the modes that use the file, for every declared
parameter in every mode source — `modes` / `visible_in_modes` are UI visibility hints,
and GOC-1 v1.0.1 injects every declared parameter into every mode — and never for
engine-control keys (`target_part`).
It is a **note**, never a failure: some drift is deliberate per mode, and nothing
becomes a failure before its whole-commons analysis is written down. On the solid
commons at `faaea08` it fires on 11 of 502 cartridges (34 locations); on the soft
commons at `700f9d0`, on 4 of 516.

**What `--render` adds.** It executes your cartridge for every `(mode, part)` pair —
**on every engine the mode declares** — then requires each mesh to be

- **watertight** — it encloses a volume,
- **positive volume**,
- **free of inverted bodies** — no connected component of negative signed volume,
- **distinct per part** — two parts rendering identical geometry means your
  `target_part` dispatch is not wired, and the platform will silently serve the wrong
  body.

**How a body is counted, and why it is not `mesh.split()`.** A body is a connected
component of the vertex-merged mesh, and its volume is the sum of its faces' signed
tetrahedron volumes — the same divergence-theorem formula `mesh.volume` uses, so an
inverted shell reads negative and the count reads bodies. `trimesh`'s own `mesh.split()`
returns the same answer and cannot be used for it: it rebuilds every component through
`submesh()`, copying faces per body, re-processing each new `Trimesh` and running a repair
pass on the way out. On a 2.5 M-face chainmail panel of 80 rings that took over 7 GB and
15+ minutes and killed a 6 GiB CI runner twice, while labelling the components takes
seconds. The measurement is identical; only the budget differs.

**A `cq.Assembly` result is flattened with `toCompound()`**, then exported through the
same `cq.exporters.export` a `Workplane` uses — not `Assembly.save`, which CadQuery 2.7
marks `@deprecate()`d ("will be removed in the next release") while 22 commons cartridges
return assemblies. It is not a behaviour change: `Assembly.save` forwards to
`Assembly.export`, whose STL arm *is* `self.toCompound().exportStl(...)`, and both paths
read the same deflection defaults. Verified byte-identical on `zipper` `closed/tape_left`
(36 bodies, 2 163 284 bytes, same sha256 either way).

**Every engine.** A CadQuery mode (`.py`/`.cq`) runs in the *same restricted sandbox the
platform uses*. An OpenSCAD mode (`.scad`) runs through the platform's own command line —
`-o out.stl --backend=Manifold -D k=v … file.scad`, booleans as `1`/`0`, strings quoted,
`render_mode` sent only when nonzero — and its STL goes through the *same* mesh bar. A
**graph** mode (`.graph.json`) is transpiled into a CadQuery script by the platform's own
transpiler, vendored here, and then rendered on the CadQuery path above. A mode that
declares **more than one** renders **every side**, and each is judged separately.

That last case is the reason this exists. The platform picks one engine per mode when it
serves a render, so on a dual-engine cartridge the other side is exercised by nothing —
and an OpenSCAD regression there ships unseen, because the side the platform serves stays
green. Every render line names the engine that produced it:

```
$ y4d-spec check ./superformula --render -v --openscad-path ../libs
  openscad: OpenSCAD version 2026.02.13 (/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD)
  ok superformula (./superformula, 12 render(s) verified (10 preset))
       (vase, vase, cadquery): ok — volume 60484.99mm³, 1 body/bodies, watertight
       (vase, vase, openscad): ok — volume 60484.99mm³, 1 body/bodies, watertight
       ...
```

`--openscad-path DIR` (repeatable) names the library roots an `include <>` resolves
against — the commons' `libs/` and the commons root for `<commons-lib/…>`.
Pass the parent search root, not the included directory itself. Your cartridge's
own directory is always first, and a `libs/dotSCAD/src` beside a root is added for you.

**Compiler diagnostics remain visible.** OpenSCAD can exit zero and emit a valid
partial mesh after a missing include or unknown module. Compiler `WARNING:` and
`ERROR:` lines are retained as bounded notes alongside the mesh verdict (up to ten
lines, 500 characters each; omitted lines are counted). Routine statistics and
`ECHO:` output are excluded. These notes do not change the exit code: whole-commons
false-positive analysis is required before a new diagnostic becomes blocking.
A watertight mesh with compiler notes is not proof that all intended features rendered.

**No OpenSCAD binary?** The OpenSCAD targets are **skipped**, with the reason on each
line — a cartridge is not non-conformant because the machine checking it is short a tool.
`--require-openscad` turns that same absence into a **failure**; CI passes it once the
runner image carries the binary, so a lane that rendered nothing can no longer report
green. `$OPENSCAD` (or `$OPENSCAD_PATH`) picks a specific binary, otherwise `openscad` on
`PATH`, otherwise the macOS app bundle.

**B-Rep validity (always, with `--render`).** The mesh bar above judges the STL, and
tessellation is where the evidence dies: OCCT will happily triangulate an *invalid* solid
— an inverted shell, a bad fuse — into triangles that merge, seal, and measure like a
real body. So before anything is exported, the built shape itself goes through two gates:

1. **`BRepCheck_Analyzer(shape).IsValid()`** — OCCT's own topological and geometric
   audit. A failure names the offending sub-shapes readably (`face: UnorientableShape`,
   `edge: FreeEdge ×3`), capped to a few lines with the remainder counted.
2. **Signed volume** (`BRepGProp.VolumeProperties_s`) — negative on the total, or on
   **any** solid inside a compound, is an inverted shell. This is not redundant with
   gate 1: a solid whose orientation is merely reversed is *topologically perfect*, so
   `IsValid()` returns **True** for it, while its signed volume is exactly minus the
   right answer. Each gate catches what the other cannot.

A failure is a conformance failure, but **the STL is still exported** — a gate that
withheld the artefact would be asking you to debug a shape you cannot open. A
`cq.Assembly` is checked per member, so the report names the broken part rather than the
tree.

Why this is a gate and not a note: `tripod-hub` swept its thread ribs along
`cq.Wire.makeHelix(radius=1e-6)`, and at 4.5 turns the fuse returned one inverted shell
that macOS OCCT tessellated into a watertight STL with the right body count and a
plausible volume — every mesh check passed — while the Linux OCP build **segfaulted on
the next boolean with no Python traceback**, costing two CI runners to a failure that was
blamed on the runners (solid #45). The same `radius=1e-6` idiom appears in 28 other
commons cartridges, so this had to fail on the author's machine, before tessellation.

**Cross-kernel parity (`--parity`).** Rendering both sides proves each is a solid. It
does not prove they are the **same** solid — a cartridge whose OpenSCAD side quietly
models a different part passes both halves of the mesh bar and hands two different
objects to two different users. `--parity` (only with `--render`) is the comparison: for
every `(mode, part, preset)` that rendered on **both** kernels, the two meshes go through
the platform's own three gates, with the platform's own numbers
(`yantra4d/scripts/qa/verify_parity.py`), so the keystone and the platform cannot
disagree about what "agree" means:

1. **AABB extents** — the largest per-axis difference. Over `0.001mm` fails, except
   inside the faceting band below. `--parity-tolerance MM` overrides this gate, and only
   this gate: the band and the volume allowance are the platform's and are not scaled
   with it, so widening one gate cannot silently move the others.
2. **Volume** — over `max(tolerance × 100, 2% of the larger)` fails. Checked only when
   both sides are watertight.
3. **Placement** — the offset between the two meshes' AABB centres, printed as
   `placement offset d=(dx,dy,dz) |d|=X mm`. Over `0.05mm` it is a **note**; it is a
   **failure** only when the manifest declares `"placement": "strict"`.
4. **Shape** — the Hausdorff surface proxy (maximum divergence, both directions)
   measured **after** that offset is removed. Over `max(tolerance, 0.5mm)` it **fails**.
   A proxy that could not be measured fails too.

**Why the warn tier exists.** An OpenSCAD `$fn` polygon is a chord approximation of the
circle CadQuery models analytically, so a perfectly correct dual-engine cartridge has two
AABBs that differ by the chord error and by nothing else. Five commons pairs sit there —
`faircap-filter`, `gears`, `glia-diagnostic`, `julia-vase`, `spiral-planter` — at
0.0028–0.0367mm, while the smallest **genuine** divergence measured across the whole
commons is 0.516728mm (`maze` coaster). The `0.05mm` band separates two non-overlapping
populations rather than being tuned to either. It is deliberately **not** enough on its
own: a real 0.04mm dimensional error would fit inside it, so the tier is conjunctive — a
delta is downgraded to a warn only when it is inside the band **and** the surfaces agree
(gate 3). Chord error satisfies both; a dimensional error moves a surface and still
fails. A surface divergence that could not be *measured* is not a pass either. (G27,
ruled 2026-09-05.)

**Why placement and shape are separate numbers (G39).** Gate 3 used to be what the
platform makes it — recorded, never failing on its own. On the first full `--parity`
sweep that let **nineteen** pairs through reporting `ok — Meshes are identical within
X mm tolerance` with X as large as **65 mm**. "Identical within 65 mm" is not a sentence
anyone should read as agreement, and behind that one number were two different problems.
Some pairs were a genuine **shape** difference: `gears` `spur_gear` was a trapezoid tooth
on one kernel against a true involute on the other, 2.5–5.0 mm apart (repaired in solid
#77). The rest were a **placement** offset — one kernel centres the part at the origin,
the other anchors a corner or a face. `relief`'s 44.72 mm is exactly √(40² + 20²), the
half-diagonal of its plate; `soft-jaw`'s 9.525 mm is 3/8 inch. The part is the same part,
moved.

Both hid behind one number because the proxy sampled raw vertices with **no alignment**,
so a rigid translation read exactly like a deformation — and gates 1 and 2 cannot
separate them either, since translating a solid changes neither its extents nor its
volume. **Extents and volume together cannot distinguish "same part, different origin"
from "different part."** Only a measurement that removes the offset can. So the offset is
measured first (from the two AABB centres — a centroid is volume-weighted, so a shape
error would leak into the number meant to isolate placement), reported on its own, and
subtracted before the surfaces are compared.

The two then get different verdicts, because they mean different things to different
consumers. A slicer re-centres the part on the bed, so an offset costs a print nothing;
an **assembly or an animation** places parts by their model origin, and there the offset
*is* the bug. A cartridge therefore opts in: placement is a note by default and a failure
under `"placement": "strict"`, which is a tightening and needs no `reason`. Shape has no
such excuse — two surfaces that still diverge once they sit on top of each other are two
different objects — so it fails. The `ok` wording moved with it: `Meshes are identical
within X mm` now appears only where X is inside the tolerance, and otherwise the line
reads `surfaces agree to X mm`, the phrase the warn tier already used. (G39, ruled
2026-09-06.)

```
$ y4d-spec check ./spiral-planter ./maze --render --parity -v --openscad-path ../libs
  ok spiral-planter (./spiral-planter, 4 render(s) verified, 2 parity pair(s) agree (2 faceting warn))
       parity (planter, planter): warn (faceting) — Bounding boxes differ by 0.033569mm
         (faceting warn, within 0.05mm; surfaces agree to 0.033569mm).
  FAIL maze: parity (coaster, coaster): FAIL — Bounding boxes differ by 0.516728mm
         (A: [100.0, 99.45218953682733, 5.0], B: [100.0, 99.96891784667969, 5.0])
y4d-spec check: ... parity=1/4 ok, warn=2, exempt=0, placement=0, failures=1
```

A pair whose two kernels model the same part at different origins reads like this — the
offset leads, because it is the finding:

```
  ok relief (./relief, 28 render(s) verified (22 preset), 14 parity pair(s) agree
       (12 placement offset))
       parity (plaque, plaque): ok (placement) — placement offset
         d=(-40.000000, -20.000000, 0.000000) |d|=44.721360mm — the same shape at a
         different origin (surfaces agree to 0.374485mm after alignment)
```

That `44.72` is √(40² + 20²) — half the diagonal of the plate, so one kernel puts the
plate's corner where the other puts its centre. Before G39 the same pair reported
`ok — Meshes are identical within 44.721360mm tolerance`. A pair whose surfaces really
differ now reads like this instead, and fails:

```
  FAIL locking-mechanism-hyperobject: parity (slip_joint, blade): FAIL — surfaces
         diverge by 3.436337mm after alignment (placement offset
         d=(0.000000, 0.000000, 0.000000) |d|=0.000000mm)
```

— zero offset, so nothing about origins explains it: the two kernels model a different
blade. Before G39 that too was an `ok` line.

`placement=P` in the summary counts the first kind. It is a **subset** of the `ok` count,
not a fifth bucket — those pairs agree — so `N + K + E + J = M` still holds; it is
printed so a reader can see how many passes owe themselves to nothing but a re-centring.

A failure is a **conformance failure** and exits nonzero; a faceting warn is a **note**
and never is. A pair exists only where two meshes exist, so a skipped OpenSCAD lane
yields none — and the `ok` line says `no comparable pair` rather than staying
silent, because silence there reads exactly like a cartridge whose kernels were compared
and agreed. **How CI uses it:** the commons render jobs pass `--parity` alongside
`--require-openscad`, which is what makes "both kernels agree" a property of the merge
path rather than of a sweep somebody remembers to run.

**Per-part exemptions — visible debt, not a red nightly (G38).** Some pairs cannot agree
without a design change that is a *ruling*, not a repair. `fasteners` `bolt` uses BOSL2's
real helical thread on the OpenSCAD side and a revolved sawtooth ring stack on the
CadQuery one, deliberately: the divergence is 0.902 × the ISO thread depth on every
preset, and a real CadQuery helix takes 262 s to build and is still wrong. `spiral-planter`
has no spiral groove on the CadQuery side at all; cutting one yields a valid B-Rep whose
tessellation carries 125 bodies and 116 boundary edges, which the mesh bar rejects (six
variants tried). The alternative to an exemption there is a permanently red nightly, and
a gate that is always red is a gate nobody reads. So a manifest may declare, **per part**,
that this comparison does not apply — but only out loud:

```jsonc
"verification": {
  "stages": { "geometry": { "checks": {
    "parity": { "enabled": true, "tolerance": 0.05,                   // the base
                "placement": "free", "reason": "…" }
  } } },
  "mode_overrides": { "<mode>": { "part_overrides": { "<part>": {
    "geometry.parity": { "enabled": false, "reason": "…" }            // per part
  } } } }
}
```

The part override **replaces** the base object whole rather than merging into it, so one
block carries the entire policy for that part and a reader need not go hunting for a
second. Then:

- An exemption or a widened tolerance **without a non-empty `reason` is a conformance
  failure** — caught by `y4d-spec check` with no `--render` at all, in seconds, with no
  CAD kernel. Silence is the thing being outlawed, so the reason is the whole mechanism.
  If it were checked only where the comparison runs, a cartridge could switch the
  comparison off and thereby switch off the check on switching it off.
- `enabled: false` skips the comparison and prints `parity (mode, part): exempt —
  <reason>` as a **note**, on every run. It is counted separately in the summary
  (`exempt=E`, so `N+K+E+J = M`), because an exemption that shrank the denominator would
  let a manifest make the bar look cleaner than it is.
- `placement` is `"free"` (default) or `"strict"` (G39): under `"strict"` an origin
  offset above `0.05mm` is a **failure** rather than a note. It needs no `reason` — it
  only tightens the bar, like a tolerance below the default — but a misspelled value is
  a conformance failure rather than a silent fall back to the loose one.
- A widened `tolerance` applies to **gate 1 only**, exactly as `--parity-tolerance` does,
  and the effective value is printed in the line: `parity (planter, saucer): ok
  (tolerance 0.06mm) — …`. An explicit `--parity-tolerance` beats a manifest one (an
  operator asking to see the cartridge at 0.001 mm must actually see it at 0.001 mm); an
  exemption is not a tolerance and no number overrides it.

An exemption is **visible debt, not an absolution.** The reason must name the *kernel
idiom* that differs — "BOSL2 helical thread against a revolved sawtooth ring stack", not
"known issue" — and every exemption is expected to be reviewed whenever either kernel
changes, since a cheaper OCC sweep or a rewritten `.scad` retires it. (G38, ruled
2026-09-06.)

### Graph cartridges (`.graph.json`) and the golden-twin rule

A **graph cartridge** does not hold its geometry in a script. `flange-plate/flange.graph.json`
is a node document — typed nodes (`profile_circle`, `extrude`, `cut`, `pattern_polar`,
`chamfer`), an `outputs` map from part id to node, and a manifest whose sliders `binding`
into node params (`"binding": "outline.r"`). The geometry only exists once the document is
**transpiled** into a CadQuery script, and it is that script this package judges.

So a graph is not a fourth renderer here. It is one step in front of the CadQuery one:

```text
.graph.json ──transpile──▶ .py ──▶ the same sandbox, the same bar
```

and everything downstream is untouched: bare-global parameter injection, `target_part`
dispatch, the B-Rep gate before tessellation, `toCompound()` assembly export, watertight
/ volume / body counts, the preset matrix, and `--parity`. **A graph cartridge clears the
identical bar, because after the transpile it is a CadQuery cartridge.** Until this lane
existed, `mode_sources()` returned `[]` for a `.graph.json` and the two graph cartridges
were the only two of the commons' 500 outside that bar.

```text
$ y4d-spec check ./flange-plate ./spacer-block --render --parity -v
  ok flange-plate (./flange-plate, 2 render(s) verified, no comparable pair)
       (flange, flange, graph): ok — volume 44363.67mm³, 1 body/bodies, watertight
       (blank, blank, graph): ok — volume 47140.54mm³, 1 body/bodies, watertight
  ok spacer-block (./spacer-block, 2 render(s) verified, no comparable pair)
       (spacer, spacer, graph): ok — volume 17081.68mm³, 1 body/bodies, watertight
       (solid, spacer_solid, graph): ok — volume 17932.50mm³, 1 body/bodies, watertight
```

**The transpiler is vendored, not re-implemented.** `src/y4d_spec/graph/graph_engine.py` is
a **byte-identical** copy of the platform's `apps/api/services/engine/graph_engine.py`,
pinned by sha256 in `graph.lock.json` and enforced by the blocking
`scripts/qa/check_graph_sync.py` lane (`--update` re-pins after a re-vendor). A keystone
that transpiled a graph with its own re-implementation would be judging a *different
script* than the one the platform serves — the exact class of silent disagreement this
package exists to prevent. The copy is possible because the engine is stdlib-only and its
platform package `__init__.py` is empty; the precedent is yantra4d's own
`packages/commons-sandbox`, which vendors Fashion Cabinet's sandbox core the same way.
The loop is closed on both sides: yantra4d's `spec-conformance` asserts the **installed**
keystone's hashes equal the platform's live files, so an engine change there goes red
until the copy here is refreshed and re-pinned. See `src/y4d_spec/graph/VENDORED.md`.

**The parameter contract needed no adapter.** `.py` cartridges receive parameters as
*bare globals* (`exec_globals.update(params)`, mirroring `cq_runner`), which is why they
use the `PARAM(lambda: name, default)` idiom, and `target_part` is one of those params.
The transpiler emits against exactly that contract:

```python
_n_outline = cq.Workplane("XY").center(0.0, 0.0).circle(
    float(_param(lambda: plate_radius, 45.0)))
...
_target = str(_param(lambda: target_part, "flange"))
result = _outputs.get(_target)
```

`plate_radius` is the manifest parameter, reached through its `binding`; the literal is
the node's own value. `result` is the first of the names the runner looks for. The only
keystone-side work is finding the bindings and materialising the transpiled script as a
real `.py` (the sandbox gates on the suffix) — and both are done by calling the platform's
own `extract_bindings` and `prepare_graph_script`.

**The golden-twin rule (write-up §3.7).** A graph is an *authoring format verified through
its transpiled output*, not a peer engine. But where a graph is authored for a cartridge
that **already has a script**, the script is the **oracle**: the graph must agree with it,
at the parity bar, on every preset, before the script may be retired. Declare both on the
mode (`"cq_file": "block.py"`, `"graph_file": "block.graph.json"`) and `--parity` compares
them — the *same* comparison as the cross-kernel one, gate for gate, tolerances, faceting
warn tier and per-part exemptions included, because "agrees with its script" must not mean
something weaker than "agrees with the other kernel". The pairing is named in the line
whenever it is not the cross-kernel one:

```text
  ok graph-twin (…, 6 render(s) verified (2 preset), 3 parity pair(s) agree)
       parity (block, block, cadquery vs graph): ok — Meshes are identical within 0.000000mm tolerance.
  FAIL graph-twin-divergent: parity (block, block, cadquery vs graph): FAIL —
       Bounding boxes differ by 2.000000mm (A: [10.0, 10.0, 10.0], B: [12.0, 12.0, 12.0])
```

This turns the commons' verified scripts into the test set for the graphs, which is
the strongest oracle available and already paid for. The rule was added *before* the
back-fill wave rather than after, because a rule added once the twins exist is a rule the
twins were never checked by. Since 2026-10-05 it holds ten twins: the printed cartridges of
solid-hyperobjects' assembly A (`ab-drive`, `ab-front-idler`, `bed-extrusion-mount`,
`corner-idler-bracket`, `toolhead-proxy`, `x-carriage`, `xy-joint`, `z-belt-clamp`,
`z-drive-housing`, `z-joint`), each in graph format 1.1 and each agreeing with its script
at every preset. The script stays the rendered source until parity holds across the
commons' nightly sweep; see that repo's [`assemblies/README.md`](https://github.com/madfam-org/solid-hyperobjects/blob/main/assemblies/README.md). `(openscad, graph)` is deliberately **not**
compared: on a cartridge with all three, the graph is pinned to its CadQuery script and
that script to the OpenSCAD one, so a third edge only reports one of the other two twice.

**Graph format 1.1** (the Wave D engine, re-vendored in 0.7.0). A document may declare
`parameters` and an ordered list of `derived` values, and any node input may be an
`{"expr": …}` in the restricted expression dialect, so a twin can carry its script's
derivations instead of frozen numbers. 1.1 also adds the `select`, `reflect`,
`profile_polyline` and `revolve` nodes, for 23 node types in all
(`src/y4d_spec/graph/graph-node-catalog.json`). The public contract is
[`graph.schema.json`](src/y4d_spec/graph/graph.schema.json). The platform's
[graph-cartridge guide](https://github.com/madfam-org/yantra4d/blob/main/docs/guides/graph-cartridges.md)
explains how to author and edit one.

**The preset matrix.** `--render` applies that same bar a second time: once at your
cartridge's own defaults, and again at **every preset your manifest declares**. A
preset is the parameter point a user actually clicks, and the defaults render says
nothing about it — a shipped preset of `extrusion-hyperobject` crashed the CAD kernel
at `degradation_state=5` while the default-params check stayed green. A preset that
raises or produces broken geometry is a **failure**, with no calibration excuse: it is
the existing rule evaluated somewhere new, not a new heuristic. A preset that renders
geometry *identical* to the defaults while setting values that differ from them is a
**note** — either the values never reach your script, or your `PARAM` fallbacks
already equal them and your manifest's declared defaults drifted. Presets that merely
restate the defaults (the UI's reset button) are exempt. `--no-presets` skips the lane.
Presets run on **every engine the mode declares**, exactly as the defaults pass does — a
preset that crashes the OpenSCAD side is the same class of bug as one that crashes the
CadQuery side.

**Printability notes.** `--render` also *measures* each passing mesh for print-time
trouble and says what it found — **never as a failure**:

- **thin walls** — median local wall thickness below 0.8mm (two 0.4mm nozzle perimeters),
- **overhangs** — more than 25% of surface area in unsupported downward slope (over 45°
  from vertical, excluding the face resting on the bed),
- **build volume** — bounding box over 256mm on any axis.

Every note names the number it measured, because **every one of these thresholds is
provisional** pending a full-commons calibration. They are measurements you can argue
with, not rules you have to satisfy. `--no-printability` skips them.

**A measurement that could not run says so.** The thin-wall thickness needs `rtree`
(trimesh's ray backend builds its bounds tree with it), which is why the `[geometry]`
extra declares it. If an optional package is missing anyway, the measurement is skipped
and `y4d_spec.printability` warns **once per process** — a `PrintabilityDependencyWarning`
naming the package and the extra that installs it — rather than returning the same
"nothing to report" a featureless mesh returns. It is still never a failure: a conformant
cartridge must not turn red because the machine checking it is short a package. But *no
thin walls* is a measurement and *the thickness measurement never ran* is a hole where one
should be, and a reader who cannot tell them apart reads the hole as good news. A
*geometric* failure — a degenerate mesh, a ray that lands nowhere — is still silence.

```
$ y4d-spec check ./sew-on-snap --render -v
  ok sew-on-snap (./sew-on-snap, 5 render(s) verified (2 preset))
       (set, set): ok — volume 415.56mm³, 2 body/bodies, watertight
       (stud, stud): ok — volume 227.55mm³, 1 body/bodies, watertight
       (socket, socket): ok — volume 188.01mm³, 1 body/bodies, watertight
       (set, set, preset 'bodysuit_placket'): ok — volume 180.28mm³, 2 body/bodies, watertight
       (set, set, preset 'varsity_placket'): ok — volume 1109.51mm³, 2 body/bodies, watertight
  note sew-on-snap: (set, set, preset 'bodysuit_placket'): thin walls — median local
       thickness is 0.76mm (over 400 surface samples), below 0.8mm (two 0.4mm
       perimeters). May print under-extruded or not at all on an FDM machine.
       Threshold is provisional.
y4d-spec check: cartridges=1 failures=0 notes=1 geometry=verified renders=5 presets=2 skipped=0
```

**A target that was not rendered says so.** A skip is not a failure, but it is not a
verified render either, and the two must never print the same. Under `-v` each skip names
the source that went unmeasured, `renders=` counts only meshes actually judged, and
`skipped=` counts the rest:

```
$ y4d-spec check ./custom-msh --render -v
  openscad: not found — OpenSCAD modes will be skipped
  ok custom-msh (./custom-msh, 0 render(s) verified, 9 skipped)
       (holder, holder_body, openscad): skip — OpenSCAD mode ('holder.scad') — no
       OpenSCAD binary on this machine, so the mesh was NOT verified here. Install
       OpenSCAD (`y4d-spec render-env` says which version) or set $OPENSCAD; pass
       --require-openscad to make this a failure instead of a skip
y4d-spec check: cartridges=1 failures=0 notes=0 geometry=verified renders=0 presets=0 skipped=9
```

That note is a good illustration of the posture: it is *true* — the 9mm snap's
sew-hole webbing really does measure about 0.76mm — and it is *marginal*, some 0.04mm
under a provisional bar, on a cartridge that prints fine today. So it gets said, with its
number attached, and the exit code stays `0`.

And it is *repeatable*: the thickness is a median over 400 surface samples drawn from a
fixed seed, so the same part measures the same number on every run. That is a property
rather than a detail — unseeded, this part's estimate wandered between 0.75mm and 0.86mm
and the note appeared on two runs in three, which is sampling noise wearing a
measurement's clothes. `thin_wall_note(..., seed=…)` takes another seed if you want to
see the spread for yourself.

Without `--render`, the summary says `geometry=NOT verified` — a run that skipped the
render lane must never read like one that passed it. The `presets=` count is on the
line for the same reason.

**Notes vs failures.** Some things are true and worth saying but are not conformance
failures — an `include <../../libs/BOSL2/std.scad>` works inside the Yantra4D repo and
nowhere else; a wall that measures 0.6mm may be exactly what you meant. Those print as
`note` and never change the exit code. **New rules land here first.** A rule that flags
healthy cartridges is not strict, it is wrong: `render_mode` uniqueness looked like a
real bar and flagged 29 correct cartridges, so it was killed and the reason recorded in
`rules.py`. Nothing becomes a failure until the false-positive analysis is written down.

**Exit codes:** `0` all conformant · `1` a conformance problem · `2` usage/read error
(including `--render` without the `[geometry]` extra — it refuses rather than silently
downgrading).

### Writing a cartridge the runner will accept

The dispatch contract, which most first cartridges get wrong:

```python
# main.py — parameters arrive as BARE GLOBALS, so probe them, never getattr/globals().
import cadquery as cq

def PARAM(getter, default):
    try:
        v = getter()
        return default if v is None else v
    except Exception:
        return default

width       = float(PARAM(lambda: width, 20.0))
target_part = str(PARAM(lambda: target_part, "body"))   # how a part is selected

if target_part == "lid":
    result = build_lid()          # assign to `result` — the runner looks for it
else:
    result = build_body()
```

A **single-part mode's id must equal its part id**, because that id is what arrives as
`target_part`:

```jsonc
"modes": [{"id": "lid", "parts": ["lid"]}],      // ✅ asking for 'lid' renders the lid
"modes": [{"id": "lid", "parts": ["lid_body"]}], // ❌ renders your fallback branch
```

Multi-part modes are exempt — they render an assembly through the default branch.

### Semantic fields: units, interface frames, requirements

These fields are optional and additive (SEM-1 §2.2–§2.4). They say what a cartridge
*means* to a machine: what its numbers measure, where a mating feature sits, and what
it needs to be printed well. `y4d-spec check` validates their structure; it does not
evaluate a frame against geometry (the render-time frame gate below does that, under
`--render`), and it does
not check that a key exists in the lexicon vocabularies (the lexicon rule does that).

- **`parameters[].unit`**: one of `mm`, `deg`, `count`, `ratio` or `percent`. The
  garment manifest takes the same field.
- **`hyperobject.cdg_interfaces[]`** gains four fields:
  - `frame`: `{part, origin, normal, x_axis?}`. The vectors are in mm, in the named
    part's model frame. `normal` points toward where the mating partner sits. Each
    component is a number, or an expression of at most 256 characters, parsed here and
    never evaluated. The expression grammar comes in two levels:
    - **v1.0:** the manifest's parameter ids, numeric literals, `+ - * /`, parentheses,
      `min`, `max` and `abs`.
    - **v1.1** (ASM-1 v1.1, hyperobjects-spec ≥ 0.4.0) adds:
      - the interface's `let` names;
      - `sin`, `cos`, `tan`, `asin`, `acos`, `atan` and `atan2(y, x)` in degrees;
      - `sqrt`, `floor`, `ceil` and `round`;
      - `< <= > >= == !=`, which yield 1 or 0;
      - `iif(cond, a, b)`.
  - `let` (v1.1): named derived numbers that the frame may read. Each one is an
    expression, or a `{param, map}` lookup of a select's option value in a map of
    numbers. They are evaluated in dependency order. A cycle, an unknown name, a
    shadowed parameter or function, or a map that does not cover the select's options
    is an error. See [`docs/ASSEMBLIES.md`](docs/ASSEMBLIES.md#frame-expressions-asm-1-1-grammar-v11)
    for the rules and the forward-compatibility note, which an older keystone pin needs.
  - `polarity`: `male`, `female` or `neutral`.
  - `symmetry`: the rotational order about `normal`. `0` means continuous, `1` means
    none, and `2`, `3`, `4`, `6` or `8` are the other allowed orders.
  - `size_key`: an interface-sizes key, or `{param, map}` when a select parameter
    picks the size. Since v1.1 a slider can also pick it by exact value, using
    canonical keys such as `"9.5"`. A slider value with no entry has no size key.
- **`requirements`** (top level, in both manifests): `process`, `materials`
  (`{any_of, none_of}`), `process_parameters` (`{key: {min?, max?, value?, unit?}}`),
  a `rationale` i18n string, and `parts`, which holds per-part overrides keyed by part
  id (piece id in a garment).

```jsonc
"cdg_interfaces": [{
  "id": "motor_bolt_pattern", "geometry_type": "bolt_pattern", "label": {"en": "Motor Bolt Pattern"},
  "frame": {"part": "soft_mount", "origin": [0, 0, "plate_thick + iso_gap"],
            "normal": [0, 0, 1], "x_axis": [1, 0, 0]},
  "polarity": "female", "symmetry": 4,
  "size_key": {"param": "motor_pattern",
               "map": {"9x9": "motor-mount-9x9-m2", "16x16": "motor-mount-16x16-m3",
                       "19x19": "motor-mount-19x19-m3"}}
}]
```

The rules (`y4d_spec.semantic_rules`) each report one kind of failure:

- an expression that does not parse, or that names an undeclared parameter;
- a vector that does not have 3 components;
- a zero `normal` or `x_axis`;
- a missing `x_axis` when `symmetry` is not 0;
- a numeric `x_axis` more than 0.5° from orthogonal to a numeric `normal`;
- a `frame.part` that is not declared;
- a `size_key` select whose `map` misses an option or holds a key that is not an option;
- a slider `size_key` key that is not a canonical number inside the slider's range;
- a `let` cycle, an unknown or shadowing `let` name, or a `let` lookup that is not over a
  select or does not cover its options;
- a bound whose `min` is greater than its `max`;
- a material class listed in both `any_of` and `none_of`;
- a per-part override for an undeclared part.

The complete example is `tests/fixtures/y4d/semantic-motor-mount.project.json`.

#### Evaluating a frame (`y4d_spec.frame_eval`, ASM-1 §1)

```python
from y4d_spec.frame_eval import evaluate_frame
frame = evaluate_frame(manifest, "motor_bolt_pattern", {"plate_thick": 5})
frame.origin, frame.normal, frame.x_axis   # floats; normal and x_axis are unit vectors
frame.homogeneous()                        # H(F): columns (x, y = n × x, n, origin)
```

Parameters resolve as GOC-1 full injection: every manifest default, overridden by the
values given. Inside an expression a checkbox is `1`/`0` and a select is its option
value, which reaches arithmetic only through a `let` lookup when it is spelled as text.
`let` entries resolve before the frame, in dependency order. A function outside its
domain (`asin(2)`, `sqrt(-1)`, `tan(90)`) is an error, never a NaN. Each expression is first vetted by the same grammar check as `y4d-spec check`,
then its syntax tree is walked by hand; nothing reaches `eval`. Errors
(`FrameEvaluationError`) name the interface, vector and component: an unknown
identifier, a division by zero, a non-finite value, a non-numeric value an expression
reads, a zero vector, or an `x_axis` more than 1° from orthogonal. Within 1° `x_axis` is
projected onto the normal's plane, so the returned frame is exactly orthonormal.

#### The render-time frame gate (`--render`, ASM-1 §8)

A frame that parses is well-formed, not trusted. Under `--render`, every interface with
a `frame` is evaluated at the defaults and at every preset, its part is rendered at that
same parameter point (full injection, so manifest/script default drift cannot put the
frame and the mesh at two different points), and the frame is tested against the mesh
by its `geometry_type` (`y4d_spec.frame_gate`, `y4d_spec.frame_geometry`):

| Rule | Types | Passes when |
|---|---|---|
| planar | `bolt_pattern`, `boss`, `engraving`, `flange`, `grid`, `pocket`, `profile`, `rail`, `screen`, `seal`, `surface` | faces whose normal is within 2° of `normal` and whose plane passes within 0.1mm of the origin cover at least 4mm² within 15mm of it — widening ×1.5 per step up to the part's bounding-box half-diagonal until a ring holds such a face; the radius used is reported as `search_radius_mm` (ASM-1 v1.1) |
| axis | `hinge`, `socket`, `thread`, `threaded_socket` | the innermost cylinder parallel to `normal` (fit within 0.05mm, wrapping at least 180°) that reaches the origin plane is centred within 0.1mm, lies on the right side (a bore runs into the material, a shaft toward the partner) and matches `polarity`. With no cylinder at the origin at all, the planar test applies and the verdict says `planar (no cylinder at the origin)` |
| none | `custom`, `fem_mesh`, `polyhedron`, `port`, `snap`, `spline` | never: the frame is reported **UNVERIFIED** as a note |

A mismatch is a FAILURE that names the interface, the parameter point and the residuals:

```
FAIL frame-plate-wrong: frame 'centre_bore' (plate, preset 'thick', axis): FAIL — the bore
  extends 6.000 mm to the partner side of the origin plane — the normal points the wrong
  way (residuals {"axial_extent_mm": [0.0, 6.0], "axis_offset_mm": 0.0, …})
```

The summary line gains `frames=P/M ok, unverified=U, failures=F` (`P + U + F = M`) only
when a framed interface was checked. A manifest with no frame renders nothing extra,
imports nothing extra and prints exactly what it did before. The face test cannot see an
origin slid along its own face by less than the search radius it used (15mm, or the wider
ring a NEMA 23 pilot or a standoff square's empty centre needs — printed with every
verdict); the axis test and the assembly closure check constrain in-plane position.
Widening can only turn a fail into a pass: a face found within 15mm is reported exactly
as before. Fixtures: `tests/fixtures/y4d/frame-plate`
(every frame right) and `frame-plate-wrong` (an origin 1mm off its face, a flipped bore
normal).

---

## Render environment

Three places have to agree about what a machine needs installed before it can render
this commons — the **platform image**, the **commons CI**, and the **CI runner image** —
and until now each carried its own copy of the answer. Three copies of a version number
is three chances to drift, and the drift is invisible in the direction that matters: a
runner one OpenSCAD release behind renders a cartridge that uses newer syntax as a
*failure*, and a runner one release ahead renders geometry the platform cannot reproduce.
Neither reads as an environment problem in the log; both read as the cartridge being
broken.

So this repo — the thing all of them already pin by SHA — owns the answer, and the others
read it:

```bash
y4d-spec render-env                     # the whole contract, annotated
y4d-spec render-env --apt               # just the package names, space-separated
y4d-spec render-env --apt --ci          # ...plus what the [geometry] extra's CAD kernel needs
y4d-spec render-env --openscad-version  # 2026.02.13
y4d-spec render-env --openscad-sha256   # the AppImage checksum to verify a download
y4d-spec render-env --json              # all of it, for a provisioning script
```

Shaped so a provisioning script consumes it without parsing prose:

```bash
apt-get install -y $(y4d-spec render-env --apt --ci)
wget -q "$(y4d-spec render-env --json | jq -r .openscad_appimage_url)" -O openscad.AppImage
echo "$(y4d-spec render-env --openscad-sha256)  openscad.AppImage" | sha256sum -c -
```

**OpenSCAD is pinned to a snapshot, not a release** (`2026.02.13`), because the commons
uses syntax no tagged release has yet. The SHA-256 is part of the contract: snapshot URLs
are not immutable the way a release tag is, so a script that downloads without checking it
is trusting whatever the mirror serves today.

That version is a **floor, not a preference** (G31). The commons pins BOSL2 v2.0.753
(`fcfce7c7`), and the previous pin `2026.02.01` cannot render it — two lines are enough:

```openscad
include <BOSL2/std.scad>
cube([1,1,1], anchor=[-1,-1,-1]);
```

aborts with `Assertion '(is_list($tags_shown) || ($tags_shown == "ALL"))' failed in
libs/BOSL2/attachments.scad, line 3809`, leaving an **empty top-level object** — an empty
STL rather than a build error, which is how it reached CI unnoticed. That is every
*anchored* BOSL2 primitive, i.e. most of the library. The same file renders under
`2026.02.13`. So this value may be bumped forward and must never go back below
`2026.02.13` while that BOSL2 pin stands; `test_render_environment.py` holds the floor.

**Fonts.** A cartridge may bundle typefaces in its own `fonts/` directory, and only under
**OFL-1.1 or CC0-1.0** — both redistributable with attribution, neither restricting
commercial or derivative use, which is the bar a cartridge anyone may fork has to clear.
Any other licence, "free for personal use" and every foundry EULA included, makes the
cartridge undistributable. Name each bundled face and its licence in your `NOTICE`.

The platform copies `*/fonts/*.ttf` and `*.otf` into system fontconfig at image build time
and runs `fc-cache`. **A render environment that copies fonts and does not run `fc-cache`
has installed nothing fontconfig can find** — a `text()` cartridge then renders in the
fallback face and the geometry is wrong in a way no mesh check can see: watertight,
positive-volume, and the wrong shape. At render time `y4d-spec` also points
`FONTCONFIG_FILE` at a config naming the cartridge's own `fonts/` first, so a bundled face
wins over a system one of the same name — the same thing the platform does.

The contract lives in `y4d_spec.render_environment` as plain constants
(`APT_PACKAGES`, `OPENSCAD_VERSION`, `OPENSCAD_SHA256`, `OPENSCAD_APPIMAGE_URL`,
`FONTS_POLICY`), each annotated with the line of the platform Dockerfile it mirrors.

## `fc-spec` — Fashion Cabinet contracts

```bash
fc-spec list                                     # the checkable contracts
fc-spec check garment-manifest my-cartridge.json
fc-spec check body-measurements my-body.json
fc-spec check fabric-card my-material.json
fc-spec check explode-json my-explode.json
fc-spec check hardware-ref my-notion.json --resolve yantra4d-commons-catalog.json
fc-spec check generator-output ./bundle/variables.json   # GOC-1; a directory works too
```

| Contract | Validates |
|---|---|
| `garment-manifest` | a cartridge's `project.json` |
| `fabric-card` | a `material.json` fabric card |
| `body-measurements` | a body / size measurement set |
| `hardware-ref` | a notion's Yantra4D `hardware_ref` link |
| `explode-json` | the native fabrication payload |
| `generator-output` | a render's GOC-1 `variables.json` (see "Generator output") — warnings print and never fail |

To check that a linked `hardware_ref`'s `params_map` keys are real parameters of the
target cartridge, pass a resolution surface with `--resolve`. Without it, a linked
reference is reported as unresolvable.

As a library:

```python
from fc_spec import check
result = check("garment-manifest", my_doc)
if not result.ok:
    for problem in result.problems:
        print(problem)
```

---

## `ho-bridge` — does the hardware link actually hold?

`fc-spec check hardware-ref --resolve` answers the **structural** question: the slug
resolves, every `params_map` key names a real parameter of the target, every value
expression references real garment parameters. That is name-level conformance, and
until now it was the whole of the bar.

It is not enough. A link can be perfectly named and still be a lie:

* the mapped **values** may be values the hardware solid cannot build at. The y4d
  cartridge clamps them back into range and quietly returns a differently-sized
  part, or OCCT raises on a degenerate fillet. The garment says *this ring passes
  38 mm webbing*; the ring that comes out passes 25. Nothing in either manifest is
  wrong.
* a `params_map` key may drive **nothing**. The name resolves, the expression is
  valid, and the script never reads it — or reads it and clamps it to a constant.
  Dead wiring, invisible to every name-level check.

`ho-bridge` renders. For each link it evaluates the mapping against the garment's
parameter defaults, renders the yantra4d cartridge **at those values**, then perturbs
each mapped parameter by 10 % and proves the geometry actually moves.

```bash
# every FC cartridge with a linked hardware_ref, against a local yantra4d checkout
ho-bridge check --fc ./fashion-cabinet --y4d ./yantra4d

# one link, with the per-probe evidence
ho-bridge check --fc ./fashion-cabinet --y4d ./yantra4d \
    ./fashion-cabinet/projects/duffel-bag -v

  ok   duffel-bag → strap-ring at (o_ring, o_ring) [opening=44, webbing_w=38] — 2 param(s) proven responsive
       probe opening: 44 → 48.4, volume 8526.978 → 9321.537 (responsive)
       probe webbing_w: 38 → 41.8, volume 8526.978 → 8556.723 (responsive)
bridge-check: links=1 ok=1 render_fail=0 dead_params=0 skipped=0
```

Three steps per link, each strictly stronger than the last:

| Step | What it proves | Needs |
|---|---|---|
| 1 · resolve | the slug and every mapped name exist, **and every mapped expression evaluates to a number** | nothing |
| 2 · render at mapped values | the hardware solid actually builds at what the garment asks for, watertight | `[geometry]` |
| 3 · responsiveness | each mapped key demonstrably **moves** the geometry | `[geometry]` |

Exit code is nonzero on `render_fail` or `dead_params`. Renders are seconds each and
a link costs `targets × (2 + probes)` of them — a full sweep of the commons is ~1080
renders — so `--max-probes` (default 3) and `--max-targets` (default 4) bound each
link, and every capped link says what it skipped.

One rule reports without blocking: a mapped value **outside** the target parameter's
declared `min`/`max` is printed under `MEASUREMENT (non-blocking)` and counted as
`range_notes=N`. It is a real finding — the cartridge clamps it, so the garment gets
a part of a size it did not order — but house doctrine is that a new rule is
calibrated against the whole commons and has its false-positive analysis written down
*before* it is allowed to fail a build.

**What it will not blame you for.** A yantra4d cartridge that already fails
`y4d-spec check --render` at its own defaults is skipped with a note, not reported as
a broken link — blaming a garment's mapping for a solid that was broken before the
garment existed is a finding nobody can act on. A perturbation that would leave the
parameter's declared range is clamped, and a value with no room to move in either
direction is skipped, never called dead. OpenSCAD-only targets get step 1 and an
explicit skip for the rest. Every skip is counted in the summary, so a run that
proved little can never read like one that proved a lot.

`docs/BRIDGE_HANDSHAKE.md` records the calibration: what a full sweep of the commons
found, which candidate rules were killed and why.

---

## The identity key

**One physical thing can be two cartridges.** A printed chainmail panel is a *solid* in
Yantra4D — a body you print. It is also *cloth* in Fashion Cabinet — something that
drapes, that you sew a garment from. Neither description is wrong, and neither is
complete.

The identity key says the two are the same object, and — crucially — names the
**material** under which that is true:

```json
{
  "identity_id": "chainmail-panel",
  "solid": { "repo": "yantra4d",        "slug": "tpu-chainmail-panel" },
  "soft":  { "repo": "fashion-cabinet", "slug": "chainmail-panel" },
  "material_identity": {
    "soft_material":  "tpu-panel-impreso",
    "solid_material": "bambu-tpu-95a"
  }
}
```

```bash
y4d-spec identity chainmail-panel.identity.json   # or: fc-spec identity ...
```

That record ships as [`examples/chainmail-panel.identity.json`](examples/chainmail-panel.identity.json).

The material is not decoration. **The same geometry printed in TPU-95A drapes as cloth;
printed in PLA it is a rigid plate.** Without naming the material the identity claim is
unfalsifiable — so the schema requires it.

Both CLIs expose `identity`, so a contributor on either side of the commons can check a
pair with the tool they already have.

**What is checked:** the record's shape, that `solid` is the Yantra4D side and `soft`
the Fashion Cabinet side, and that a pair genuinely spans the two commons.
**What is not:** whether either slug exists. This package has no repo to look in, and
someone pairing against their own fork must still be able to validate a record.
Existence is a platform-side lane.

---

## Generator output (GOC-1) — `variables.json`

A rendered file says nothing about how it was made. **GOC-1** (Generator Output
Contract v1) is the document a platform writes beside every render: which cartridge,
mode and part, on which engine, with exactly which inputs, plus the digest of every
file. yantra4d writes `<artifact-stem>.variables.json` next to each artifact; Fashion
Cabinet ships `variables.json` inside a `format=bundle` zip. The schema is
`generator-output` in `hyperobjects_schemas` — **this package is its only home**; no
platform keeps a copy. It carries **no material, process, slicer or printer settings**:
the schema denies `target_material`, `infill`, `layer_height`, `nozzle_diameter` and
friends, and the prefixes `mat_shrinkage_`, `mat_clear_`, `thermo_`, `slicer_`,
`printer_`, `filament_`. The bare `mat_` prefix is allowed on purpose (`mat_thick`,
`mat_width` are geometry in the solid commons).

```bash
y4d-spec bundle check ./renders/                     # every *.variables.json / variables.json below
y4d-spec bundle check part.variables.json other/variables.json
fc-spec check generator-output ./bundle/variables.json
```

Each document is checked against the geometry files in **its own directory**. Exit 1 on
any error, 0 otherwise — warnings print and never fail; naming nothing checkable is a
usage error (exit 2).

| Severity | Finding |
|---|---|
| error | schema violation (including a denied physical id) |
| error | `variables` not sorted by id, or a duplicate id |
| error | `variables_sha256` or `instance_id` does not recompute |
| error | `complete` contradicts the variables (`complete` = no `source_default` entry) |
| error | a geometry file present beside the document whose size or sha256 differs, or a geometry path that is absolute or escapes the directory |
| warning | `complete: false` — some parameter was not injected, so the geometry depends on a source literal `variables` does not record |
| warning | `legacy_physical_inputs` present (deprecated) |
| warning | a geometry file is not present — its digest was **not** verified |

The four algorithms every producer and checker must agree on live in
`hyperobjects_schemas.generator_output`:

```python
from hyperobjects_schemas.generator_output import (
    canonical_json, variables_sha256, tree_sha256, instance_id, check_generator_output,
)
canonical_json(obj)        # integral floats -> ints, then json.dumps(sort_keys, (",", ":"),
                           #   ensure_ascii=False, allow_nan=False), UTF-8
variables_sha256(doc["variables"])   # sha256 of canonical [[id, value], ...] sorted by id (bytewise)
tree_sha256("./projects/thimble")    # hyperobjects-tree-v1
instance_id(cartridge=..., mode=..., part=..., tree_sha256=..., variables_sha256=...)
check_generator_output(doc, base_dir="./renders").findings
```

- `variables_sha256` hashes **id and value only**; provenance (`type`, `source`,
  `preset_id`, `unit`, `measurement`) is excluded, and a `source_default` entry
  contributes `null`. Numbers are normalised first (GOC-1 v1.0.1 §3.1): every finite
  integral float with |x| < 2^53 hashes as an integer (`12.0` → `12`, `-0.0` → `0`), so
  a platform holding a slider as `12.0` and one holding it as `12` agree, as ECMAScript
  serialisation does. A document may record either spelling in `value`.
- `variables` lists every manifest-declared parameter (v1.0.1 §4.1, no mode scoping);
  the checker never flags a variable for being outside the rendered mode.
- `tree_sha256` (`hyperobjects-tree-v1`) digests the cartridge directory: every regular
  file (file symlinks followed, directory symlinks never), except paths with a `.git`,
  `__pycache__` or `node_modules` segment, the cartridge's root `docs/`, and the
  suffixes `.md .txt .png .jpg .jpeg .gif .svg .webp .pdf`; one line
  `"<sha256>  <path>\n"` per file, sorted bytewise, hashed. **Known limitation:**
  shared libraries outside the cartridge (`libs/*`, `commons-lib`) are not covered;
  `generator.commons.sha` and `generator.kernel` record those.
- `instance_id` excludes `platform_build` and `kernel` by design: the same design at the
  same inputs keeps its id across deploys, and the geometry `sha256` records the bytes.

`tests/fixtures/generator-output/thimble/` is a document that passes clean; the golden
vectors producers cross-check against are pinned in `tests/test_generator_output.py`.

## AAS projection (SEM-1) — `aas build` / `aas check`

A cartridge is a *type*: one design that many printed or sewn instances come from. The
Asset Administration Shell (AAS, IDTA-01001) is the industrial standard for describing
such an asset to machines. `hyperobjects_aas` projects every cartridge and every
material card to **one AAS v3.1 Environment** in the normative JSON serialization
(metamodel v3.1.2): a type shell, its submodels, and a ConceptDescription for every MADFAM
semanticId it uses. It needs only `jsonschema` at runtime, and canonical JSON (GOC-1 §3.1)
means the same input gives byte-identical output.

```bash
y4d-spec aas build ./solid-hyperobjects/tslot-corner --commons solid --out tslot-corner.aas.json
fc-spec  aas build ./soft-hyperobjects/a-line-skirt --out a-line-skirt.aas.json
y4d-spec aas build-material ./materials/bambu-tpu-95a/material.json --out tpu.aas.json
y4d-spec aas check *.aas.json            # schema + MADFAM rules (+ BaSyx when installed)

# the independent BaSyx round-trip, dev/verification only:
pip install "hyperobjects-spec[aas-verify] @ git+https://github.com/madfam-org/hyperobjects-spec@main"
```

`build` checks every environment before it writes it and prints the conformance decision
of every submodel; several inputs need `--out-dir`. Exit codes are 0 for clean, 1 for a
check error, and 2 for a usage or read error.

**Identifiers** (SEM-1 §1, permanent). The asset is `https://id.madfam.io/asset/{solid|soft}/{slug}`.
The shell is `…/aas/{kind}/{slug}/{tree16}/p{N}`, where `tree16` is the first 16 hex of the
GOC-1 `tree_sha256` and `N` is the **projection version** (`hyperobjects_aas.PROJECTION_VERSION`,
now `3`); there is one immutable shell per design revision and projection version. A
submodel is `…/sm/{kind}/{slug}/{tree16}/p{N}/{SubmodelIdShort}`. A concept is
`…/concept/{lexicon-term}`. A MADFAM template is `…/smt/{name}/1/0`. A material card's shell
uses `content16`, taken from the card's canonical JSON (`…/aas/material/{slug}/{content16}/p{N}`).
Asset, concept, template and standard-part ids carry no version: they do not depend on
the projection.

**Projection version** (owner decision 2026-10-04). A store such as asset-shells keeps
shells immutable per id, so a projection that writes different bytes for the same inputs
needs new ids. The shell records its version twice: in the id, and in a
`ProjectionVersion` extension (`xs:positiveInteger`), because `administration` already holds
the manifest semver. `aas check` fails a shell whose extension and id disagree, or whose
submodels carry another version. The **drift guard** makes the bump mandatory:
`scripts/refresh_assembly_golden.py --check` (a CI step) and `tests/test_projection_version.py`
rebuild 18 goldens (assemblies A and B, the 14 solid cartridges they use, a soft garment,
a material card). The projection version was **2** from 0.7.0, when every assembly shell
gained the ASM-1 §9 `Kinematics` submodel. It is **3** since 0.10.0: a material card is
projected in its canonical form. When the bytes under an id a golden already carries change, both fail, and
the refresh refuses to write until `PROJECTION_VERSION` is bumped.

**One digest, one projection** (lane P6-PROJFIX). A content-addressed id hashes canonical
JSON (GOC-1 §3.1), in which `20.0` and `20` are one number. That covers an assembly's
`digest16` and a material card's `content16`. So the projection reads the input in that
same canonical form, and the spelling of a whole number cannot change the bytes under the
id. A whole number's `valueType` follows its canonical value: `20` is `xs:integer`, `20.5`
is `xs:double`, and a field the projection types explicitly keeps its type. An assembly
projects its canonical document, the form its `AssemblyDocument` blob stores, so a
publisher and a store that re-projects the blob write the same bytes.
`tests/test_projection_canonical.py` holds the property `project(x) == project(canonical(x))`
over every assembly and material fixture. A cartridge id hashes file bytes (`tree_sha256`),
so a respelt manifest is a new revision with a new id.

ConceptDescription-only
changes are not drift of this kind: they follow the lexicon, and the store updates them in place. The metamodel limits `administration.version` to an
integer of at most 4 characters, so `1.2.3` becomes version `1`, revision `2`, and the full
semver goes in `Nameplate/ManifestVersion`. A manifest id that is not a valid idShort is
mapped deterministically, for example `h` becomes `h_` and `3d` becomes `x3d`, and the
exact id is kept beside it.

| Submodel | semanticId it carries | Why |
|---|---|---|
| Nameplate | MADFAM `nameplate/1/0`, with IDTA 02006-3-0 as supplemental | The IDTA template requires `AddressInformation` and `OrderCodeOfManufacturer`, which a commons design does not have. |
| ParametricModel | MADFAM `parametric-model/1/0` | No IDTA template applies. |
| GeometryProvision | MADFAM, with IDTA 02026 (3D models) as supplemental | Geometry is produced on demand, so there is no file to fill the mandatory `Model3D` list. |
| RequirementProfile | MADFAM, with IDTA 02031-1 (process parameters) as supplemental | The mandatory `Processes` structure is not the shape of a requirement profile. |
| MatingInterfaces / SeamInterfaces / PatternProvision / Fabrics / HardwareLinks | MADFAM | No IDTA template exists for physical mating. |
| BillOfMaterials | **IDTA 02011-1-1 HSEBoM** | `EntryNode`, at least one `Node` and `ArcheType` are present. |
| MaterialData | **IDTA 02034-1-0 materials** | `MaterialSystemProperties` is present. |

The rule is computed, not asserted (`hyperobjects_aas.templates`). A submodel claims an
IDTA semanticId only when every element the template marks mandatory is present, matched
by semanticId. `aas check` re-derives the same decision and fails an over-claim. Every
IDTA identifier was copied from the published template JSON, and its source path and
commit are recorded beside it.

**Validation.** `aas check` runs three layers:

1. The vendored `aas.json`, evaluated through a `modelType` dispatch of its `oneOf`
   unions. This is equivalent to the published schema and is tested against it.
2. The MADFAM rules: the id scheme, AASd-117/120/022 idShorts, the conformance claim, and
   concept coverage.
3. The BaSyx Python SDK 2.2.0 strict round-trip, when the `aas-verify` extra is installed.
   Without it the summary says `basyx=not installed`, never that the round-trip passed.

`scripts/qa/aas_fleet_gate.py --solid DIR --soft DIR --material FILES…` builds every input
twice. It compares the bytes, checks every environment and prints the totals.

The new manifest fields from SEM-1 §2–§3 are read defensively. These are `unit`, the
interface `frame` / `polarity` / `size_key` / `symmetry`, and `requirements`. Each one is
emitted when present and omitted cleanly when absent. Frame components that are
expressions over parameter ids are kept as strings and never evaluated.

---

## The Commons Lexicon

**One physical thing can also have two names.** Fashion Cabinet calls the sewn margin of
a zipper `zipper_tape`; Yantra4D calls the same surface `tape_edge`. Neither is wrong —
one names the garment's edge, the other the solid's mating face — but a reader holding
either word must land on the same entry. Shared vocabulary belongs to neither half of
the commons alone, which is why it lives here (RFC 0039 §4), the same extraction this
package already performed on the conformance bar.

The cost of *not* having it is not hypothetical. A drafting term whose semantics lived
only in five copied code comments carried a copied bug into five landed garment
cartridges — back shoulder seams up to 83.5 mm wrong at legal parameters
(fashion-cabinet #113). A term entry is where that definition, **and its constraint**,
gets written once.

```bash
fc-spec lexicon                          # or: y4d-spec lexicon
fc-spec lexicon --catalog bundled        # + resolve every embodied_by slug (hermetic)
fc-spec lexicon --status                 # just the N/M line
fc-spec lexicon -v                       # list every term

fc-spec vocab                            # the controlled + fabrication vocabularies (keys)
fc-spec article <path> --catalog bundled # article frontmatter

fc-spec define zipper_tape --lang pt     # the dictionary, on a command line
fc-spec lookup fashion-cabinet/garter-belt
fc-spec related tape-edge
```

<!-- counts:lexicon-status:start -->
```
$ y4d-spec lexicon --catalog bundled
y4d-spec lexicon: terms=157 failures=0 embodied_by=resolved
lexicon_status: 157/157 terms quadrilingual (es/en/fr/pt) domains=9 review: reviewed=0 generated=127 unmarked=30
```
<!-- counts:lexicon-status:end -->

Without `--catalog`, the summary says `embodied_by=NOT resolved (…refs)` — the same
read-proof bar `--render` holds. A run that skipped a check must never read like one
that passed it.

The `review:` clause on the status line carries the second debt, the one N/M cannot
show: **four complete languages nobody has read are still four complete languages.** The
117 terms of the G3 waves are marked `generated` and are waiting on a native pass; the 30
seed terms predate the field and claim neither. Nothing in the corpus claims a review
that did not happen, and the lane refuses an entry that tries to.

### What a term is

Terms are **born quadrilingual** — `en`, `es`, `fr`, `pt`, all four required to ship
(RFC 0039 §7). That is a gate rather than an aspiration: four languages are only cheap
at authoring time, and every entry that ships partial becomes a backfill nobody
schedules. Spanish is the house register and the quality bar; French and Portuguese are
reviewed, not merely generated.

One JSON file per term in `src/hyperobjects_lexicon/terms/`, and **the filename is the
id** — the corpus is browsable with `ls`, and the lane enforces the agreement.

```jsonc
{
  "id": "back-neck-rise",
  "domain": "pattern-drafting",
  "term":       { "en": "back-neck rise", "es": "elevación del escote trasero", ... },
  "definition": { "en": "How much higher the back neck point sits than …", ... },
  "aliases":    [{ "name": "back_neck_rise_mm", "repo": "fashion-cabinet", "note": "…" }],
  "standards":  ["ISO 8559-1"],
  "embodied_by": ["fashion-cabinet/magnetic-placket-shirt", ...],  // '<repo>/<slug>'
  "see_also":   ["shoulder-slope", "neck-drop"],                   // validated term ids
  "constraints": "The DRAWN rise must track any flattening of the shoulder run. …",
  "sources":    ["fashion-cabinet#113 — …"]
}
```

`constraints` is the field that pays for the lexicon: the clamp rule or degeneracy trap
that would otherwise live in a code comment and be copied, bug and all, into the next
cartridge. `aliases` is how a dialect split gets absorbed rather than papered over —
each spelling recorded with the repo where it is real.

> **Why JSON, not the YAML of the RFC sketch.** This package promises manifest
> conformance is "pure python, runs in under a second", and its base install declares
> exactly one dependency. Adding a YAML parser so a data file can have nicer quotes
> would tax every third party installing this package to check a cartridge. Every other
> data file here is JSON, `json` is in the standard library, and the content is
> unchanged. So: JSON files, YAML-shaped content, no new dependency.

### What the lane checks

| Check | Fails when |
|---|---|
| Schema | the entry violates `lexicon-term.schema.json` (unknown field, bad id shape, bad domain) |
| Four languages | any of `en/es/fr/pt` is missing **or blank** in `term` or `definition` |
| Cross-references | a `see_also` points at a term that does not exist, or at itself |
| Citations | a `heritage: true` entry carries no `sources` (RFC 0039 §7) |
| Identity | the filename and the `id` disagree, or two entries share an id |
| Review claims | an entry says `reviewed` with no named reviewer, or over a language facet still marked `generated` |
| `embodied_by` | a slug does not resolve — **only when a catalog is supplied** |
| External matches (contract 3) | an entry uses `exact_match` / `close_match` without declaring `spec_version: 3`, or lists one identifier in both |

That last row is deliberate. This package has no repo to look in, exactly as the
identity key does not check whether a slug exists. `--catalog bundled` uses a vendored
snapshot of both commons' slug sets, so CI runs the strict check with no platform
checkout and no network; `--catalog <path>` takes a live `commons-catalog.json`. The
snapshot goes stale in one direction only — a term naming a newly added cartridge fails
here while being correct in the commons, which asks for a refresh rather than silently
passing:

```bash
python3 scripts/refresh_catalog_snapshot.py --yantra4d ../yantra4d \
                                            --fashion-cabinet ../fashion-cabinet
```

Every capture in this repo — this snapshot, the two reader catalogs, the bridge graph and
both controlled vocabularies — is read out of a **commit** with `git show` rather than off
a working tree, and records the **full sha** it was read at. So a refresh never needs a
shared clone moved off its branch, cannot capture uncommitted work, and leaves a rev a
later reader can resolve exactly rather than guess at. Each side is named separately
(`--yantra4d-ref` / `--fashion-cabinet-ref`, both defaulting to `origin/main`) because the
two commons move independently.

### Term contract 3: external identifiers and the derived concept IRI

Contract 3 (SEM-1 §4) is additive over contract 2. A term may carry `exact_match` and
`close_match`: arrays of identifiers minted **outside** the lexicon — absolute IRIs (IDTA
submodel-template semanticIds, EMMO classes) or ECLASS IRDIs written as strings
(`0173-1#02-AAO677#002`). Identifiers only: ECLASS content is licensed and is never copied
here. An entry using either declares `spec_version: 3`.

The term's **own** IRI is not a field. It is derived from the id, so it cannot drift from
it:

```python
from hyperobjects_lexicon import concept_iri, entry_concept_iri

concept_iri("bolt-pattern")                      # 'https://id.madfam.io/concept/bolt-pattern'
entry_concept_iri("processes", "fff")            # 'https://id.madfam.io/concept/processes/fff'
```

### How platforms consume it

```python
from hyperobjects_lexicon import load_lexicon, check_lexicon, lexicon_status

lex = load_lexicon()                       # the bundled corpus, id -> term dict
lex["tape-edge"]["term"]["pt"]             # 'debrum de fita costurado'
lex["tape-edge"]["aliases"]                # both dialects, each with its repo

check_lexicon(lex).ok                      # the lane, as a library call
lexicon_status(lex)                        # the house N/M line
```

**The dictionary tools** (RFC 0039 §6.2) are the same three calls both platforms' MCP
servers wrap, so a definition cannot differ depending on which half of the commons you
asked — or on whether you asked a server or a shell:

```python
from hyperobjects_lexicon.dictionary import define, lookup, related

define("zipper_tape", "pt")                # -> the tape-edge entry, in Portuguese
define("negative_ease_knit")               # a near-duplicate key resolves too
lookup("fashion-cabinet/garter-belt")      # every term that cartridge embodies
related("tape-edge")                       # see_also, referenced_by, and the keys
```

`define` accepts a term id, a headword in any of the four languages (accents optional),
a repo spelling, or a controlled-vocabulary key — and every answer says which route
found it, and whether a human has read the entry. "I found this by a fuzzy alias" and
"you named it" are different claims.

Each platform renders its own surfaces from this — term popovers on catalog facets and
parameter labels, an A–Z lexicon page, the MCP tools above — while the *articles* stay in
each commons as each one's editorial property (RFC 0039 §2, §4).

### Adding a term — the contribution bar

1. **One file, `terms/<id>.json`**, id in kebab-case, filename matching.
2. **All four languages, written not generated.** Machine translation is acceptable as a
   draft and never as shipped copy. Write `es` to native quality; have `fr`/`pt`
   reviewed. A partial entry does not merge — there is no "add the rest later" lane.
3. **Point at real objects.** `embodied_by` names cartridges where the term is actually
   real. A term nothing embodies is a term nobody needed.
4. **Carry the constraint** if the term has one. This is the whole point.
5. **Cite cultural or historical claims.** Set `heritage: true` and give `sources` — the
   lane fails an uncited claim, by design, and it constrains velocity on purpose.
6. **Link, don't dangle.** Every `see_also` must resolve.
7. **Say whether it has been read.** A drafted entry carries
   `"review_status": {"state": "generated"}` and ships — quadrilingual completeness is
   the gate, review is not. Claiming `reviewed` requires naming a reviewer, and the
   state is the *worst* of its four language facets, never the best.

```bash
.venv/bin/fc-spec lexicon --catalog bundled   # then run the lane
.venv/bin/python -m pytest tests/test_lexicon.py
```

Renaming an `id` is a **breaking change**: it is what `see_also` points at and what a
platform's `define()` resolves.

### The controlled vocabularies

The lexicon defines **words**. The vocabularies define **keys** — the literal strings a
manifest writes. Two documents ship, and each fixes a different failure:

<!-- counts:vocabulary-status:start -->
```
$ fc-spec vocab
fc-spec vocab: vocabularies=2 entries=170 failures=0
vocabulary_status[capabilities]: entries=126 term=44 gloss=77 undefined=5 aliases=8 equivalences=0 distinct_pairs=1 provisional=1 review=generated
vocabulary_status[interfaces]: entries=44 term=44 gloss=0 undefined=0 aliases=2 equivalences=5 distinct_pairs=1 provisional=10 review=generated
```
<!-- counts:vocabulary-status:end -->

**`interfaces`** — both commons' interface names. Each repo's type set is already a
closed enum in its own schema, so the drift is not *inside* a repo but **across** the
two, which is exactly RFC 0038's B2 workstream. Those pairs are explicit, symmetric
`equivalent_to` edges:

| Fashion Cabinet | | Yantra4D | what agrees across the bridge |
|---|---|---|---|
| `zipper_tape` | ≡ | `tape_edge` | the zip length that runs along the seam |
| `panel_edge` | ≡ | `panel_edge` | the printed panel's cell count and its sewn edge |
| `strap_edge` | ≡ | `strap_slot` | `strap_w`, plus a declared clearance |
| `hem_casing` | ≡ | `cord_channel` | `cord_dia`, and the lock body sized from it |
| `custom` | ≡ | `custom` | the escape hatch, on both sides |

And one pair that looks like a sixth and is not: **`pocket` ≢ `pocket`**. On the soft
side it is a garment pocket — an opening with a bag behind it; on the solid side a recess
cut into a body to receive a part. Identical spelling, opposite topology, recorded as
`distinct_from` on both entries so no de-duplication pass can merge them from either
direction. The capture also turned up two dialect splits *inside* Yantra4D
(`sew_face`/`sew_plate`, `strap_slot`/`webbing_slot`), recorded as aliases.

**`capabilities`** — Fashion Cabinet's `hyperobject.capabilities` keys. The garment
manifest types that block as `additionalProperties: {type: boolean}`: every key is legal
and none is defined. 516 cartridges wrote **134 distinct keys**, most of them once. This
document is the missing enum, and it is additive by construction — every observed key is
present, so a compliance lane can adopt it today without failing a single cartridge that
is correct:

| relation | what it means | examples |
|---|---|---|
| `aliases` | the same claim, another spelling → rewrite it | `negative_ease_knit` → `knit_negative_ease`; `hardware_reference` → `hardware_bridge`; `one_handed_dressing`, `one_handed_clip` → `one_handed_operation`; `tailored` → `tailoring`; `uncut` → `uncut_cloth`; `insulated_quilting` → `quilted_insulation`; `princess_seamed` → `princess_seam` |
| `narrower_than` | a *more specific* claim → keep both | `graduated_compression`, `compression_zoned`, `distributed_compression` under `compression_support`; `structured_tailoring` under `tailoring`; `fully_lined`, `self_lined`, `drafted_lining` under `lined` |
| `distinct_from` | a false friend → never merge | `hook_closure` (hook-and-**eye**, 13 bras and belts) against `hook_loop_closure` (hook-and-**loop**, one hi-vis vest). They bridge to different solid cartridges |
| `needs_definition` | used, and nobody has defined it | 5 keys, named on the status line so the gap is countable rather than invisible |

The rule that keeps the two layers in step: **a key two or more cartridges write must
carry a lexicon term**, so the vocabulary a commons actually reads is quadrilingual or
it does not ship. That rule is enforced by the lane, and it is what the last six terms of
the G3 wave were written for.

```python
from hyperobjects_lexicon import canonical_key, equivalences

canonical_key("negative_ease_knit")   # 'knit_negative_ease'
canonical_key("hook_loop_closure")    # unchanged — not a duplicate of hook_closure
canonical_key("a_key_nobody_wrote")   # unchanged — never rename what you have not seen
equivalences()                        # every cross-commons pair, once each
```

[`docs/COMMONS_VOCABULARY.md`](docs/COMMONS_VOCABULARY.md) is the adoption checklist for
both platforms.

### The fabrication vocabularies (SEM-1 §4)

The commons vocabularies are readings of keys the two commons already write. The
fabrication vocabularies are the other kind: **reference lists** for the keys a manifest's
fabrication fields write — what a part is made by, what of, under which slicer bounds,
on which machine, and which standard part two interfaces mate through. Five vocabularies
ship in `src/hyperobjects_lexicon/vocabularies/fabrication/` (one file each, plus a
`{vocabulary}.{label}.json` supplement the loader merges in — the standard-parts catalog's
interface sizes are one), validated by their own schema
(`fabrication-vocabulary.schema.json`) and checked by the same `vocab` command:

<!-- counts:fabrication-status:start -->
```
$ y4d-spec vocab   # second verdict
y4d-spec vocab fabrication: vocabularies=5 entries=109 failures=0
fabrication_status[processes]: entries=7 cited=6 dimensions=0 provisional=0 review: signed=0 draft=7
fabrication_status[material-classes]: entries=22 cited=22 dimensions=0 provisional=0 review: signed=0 draft=22
fabrication_status[process-parameters]: entries=17 cited=17 dimensions=0 provisional=0 review: signed=0 draft=17
fabrication_status[fabrication-capabilities]: entries=13 cited=2 dimensions=0 provisional=0 review: signed=0 draft=13
fabrication_status[interface-sizes]: entries=50 cited=50 dimensions=174 provisional=2 review: signed=0 draft=50
```
<!-- counts:fabrication-status:end -->

Every entry carries its label and definition in es/en/fr/pt, every dimensional or
technical fact cites a public standard or manufacturer source, every process-parameter
key is OrcaSlicer's own key pinned to the line of `PrintConfig.cpp` that defines it, and
material classes list the commons' material cards that belong to them. All of it is a
drafting pass (`generated`) until a native reader signs it.
[`docs/FABRICATION_VOCABULARIES.md`](docs/FABRICATION_VOCABULARIES.md) has the field
reference, the citation rules and the membership rule below.

**Membership rule.** `y4d-spec check` and `fc-spec check garment-manifest` fail a manifest
that writes a fabrication key no vocabulary defines: an interface `size_key` (or any value
of a `{param, map}` size key), `requirements.process`, `requirements.materials.any_of` /
`none_of`, and the keys of `requirements.process_parameters`, at the top level and under
`requirements.parts.<id>`. A manifest without those fields passes silently — on
2026-10-02 that is all 502 solid and 516 soft manifests, checked.

### The standard-parts catalog (ASM-1 §4)

An assembly references a commercial off-the-shelf part with
`{"source": {"type": "standard", "key": "<key>"}}`. The keys live in
`src/hyperobjects_standard_parts/parts/`, one JSON file per part, validated by
`standard-part.schema.json`: the governing standard or datasheet with citation URLs,
cited dimensions, optional parameters (an extrusion's cut length), and mating interfaces
in the SEM-1 §2.3 shape — frame expressions over the part's own parameters, polarity, a
`size_key` from `interface-sizes`, symmetry. Facts only; no datasheet prose, no CAD.
Thirty-seven parts cover the two Phase-4 test assemblies (a Voron 2.4-class motion frame and a
5-inch FPV quad), the Phase-6 2.4 gantry (MGN9 Y rails, the A/B belt, the XY-joint idler) and the 2.4-class Z drive, Z belts, bed hardware and 350 build plate; the frame, motor, camera, prop, stack, antenna and SMA-jack entries are commercial
**classes**, stated by shared facts, never a copy of one vendor's design. Since 0.7.0
(ASM-1 §9) a pulley or idler may carry a cited `belt_engagement` (a toothed part's pitch
diameter or a smooth part's running diameter, and where the belt's mid-plane sits) and a
`belt` entry its pitch, width and pitch-line offsets, which an assembly's declared belt
paths read. An `envelope` (boxes and cylinders built from cited dimensions) is the part's
body for `assembly check --collision`.

```python
from hyperobjects_standard_parts import load_part, resolve_parameters, interface_frames
frames = interface_frames(load_part("extrusion-2020"),
                          resolve_parameters(load_part("extrusion-2020"), {"length_mm": 350}))
```

The lane — schema, citations, membership of every `size_key`, frames evaluating at the
defaults and at every parameter bound, exact unit and orthogonal axes — is the third
verdict of `y4d-spec vocab` (`vocab standard-parts: parts=37 interfaces=109 failures=0`).
[`docs/STANDARD_PARTS.md`](docs/STANDARD_PARTS.md) has the per-part table, the polarity
convention and how to add a part.

### Article frontmatter

The lexicon is the dictionary layer; the **encyclopaedia** layer is the per-cartridge
`docs/README.md` that both commons already write. RFC 0039 §2 is emphatic that those
READMEs are **single-source — no parallel corpus** — so `article-frontmatter.schema.json`
holds no article body. It holds what a catalog surface needs to render and navigate one:
the object, where the prose lives, era, provenance with named custodians, the lexicon
terms its popovers resolve, and what the cartridge **deliberately does not draw**.

```
$ fc-spec article examples --catalog bundled -v
  ok fashion-cabinet/chaleco-charro [heritage] (examples/chaleco-charro.article.json)
fc-spec article: articles=1 failures=0 objects=resolved
article_status: 1 article(s) heritage=1 cited+bounded=1/1 titles: es=1 en=1 fr=0 pt=0
```

A `heritage: true` article pays two prices, not one: the citation RFC 0039 §7 requires,
**and** an `excludes` list. The heritage cartridges already write that section in prose —
*"No botonadura de plata. No escudo… The competition dress codes belong to the Federación
Mexicana de Charrería"* — and it is machine-readable here because a boundary a platform
cannot read is a boundary a platform will cross.

Language coverage is **reported, never failed**: the lexicon is born quadrilingual
because four languages are free at authoring time, but the catalogs are en/es today and
RFC 0039's phase G-L is the backfill. The status line prints the per-language counts so
the debt is visible instead of permanent.

### The cross-commons reader

RFC 0039 G4: **one lexicon, both encyclopaedias, and the bridge graph as the navigation
between them.** `docs/reader/` is a static, JavaScript-free reader built from data
vendored in this repo, and committed, so a clone reads both commons with no build step.

```bash
fc-spec reader                 # or: y4d-spec reader — build into docs/reader
fc-spec reader --check         # fail closed if the committed tree ≠ a rebuild (CI)
fc-spec reader --status        # just the reader_status line
```

<!-- counts:reader:start -->
| Layer | Pages | Languages present (es/en/fr/pt) |
|---|--:|---|
| terms | 157 | 157 / 157 / 157 / 157 |
| yantra4d | 510 | 485 / 510 / 1 / 1 |
| fashion-cabinet | 527 | 511 / 527 / 248 / 200 |
| index, bridge and catalog index pages | 5 | — |

| Bridge | Count |
|---|--:|
| declared edges (garment → hardware) | 303 |
| resolving to a page on both ends | 302 |
| unresolved (reported, never fatal) | 1 |
| linked | 302 |
| claimed but not linked | 1 |
| published back edges (hardware → garments) | 302 |
| agreeing in both directions | 302 |

```
$ fc-spec reader --check
fc-spec reader --check: out=docs/reader pages=1199 differences=0
reader_status: pages=1199 terms=157 yantra4d=510 fashion-cabinet=527 bridges: edges=303 resolved=302 unresolved=1 unlinked=1 back=302 mirrored=302
```
<!-- counts:reader:end -->

**Where the pages come from.** The term corpus, plus three pinned snapshots refreshed by
`scripts/refresh_reader_snapshots.py`: each commons' published catalog (with its material
cards) and the bridge graph — Fashion Cabinet's `hardware_ref` claims forward, and the
back edge it publishes for Yantra4D to vendor. The build reads nothing else: no network,
no platform checkout, no clock.

```bash
python3 scripts/refresh_reader_snapshots.py --yantra4d ../yantra4d \
                                            --fashion-cabinet ../fashion-cabinet
fc-spec reader                      # then rebuild the pages in the same commit
python3 scripts/refresh_reader_counts.py    # and the count blocks above
```

Each snapshot records the **full sha** it was captured at, in its own `source.commit`, and
every entry page links to its manifest at that exact commit. So the tables above are a
statement about a specific pair of commits rather than about "the commons today", and a
refresh is reproducible: `--yantra4d-ref` and `--fashion-cabinet-ref` name the two sides
separately (default `origin/main`) because the commons move independently.

**Four things it refuses to do.**

1. **Offer a language an entry does not have.** The lexicon is quadrilingual because
   that is its ship gate; the catalogs are not, and phase G-L is the backfill. So the
   switcher on a page lists exactly the languages that page carries, the index chips
   show which languages a row has, and where a facet is missing the page says so *in
   that language*. A reader that filled the gap silently would make the debt invisible.
2. **Let a `generated` definition read as a reviewed one.** Every language section of a
   term carries its own review state.
3. **Copy an article.** RFC 0039 §2 makes each cartridge's `docs/README.md`
   single-source; every entry page links to its manifest at the exact pinned commit
   instead.
4. **Hide an edge it cannot resolve.** An unresolved bridge target or `embodied_by` is
   written out as unresolved, with the reason its author published — reported, never
   fatal, the same convention the back edge itself keeps.

`--check` renders the same pure `{path: text}` mapping the build writes and compares it
byte for byte, so a missing page, a page nobody generates and a page whose bytes moved
all fail. There is no second code path that could drift from the build.

Every count above, and in the two transcripts earlier on this page, is emitted by
`scripts/refresh_reader_counts.py` (`--check` in CI) rather than typed — the same reason
`refresh_vocabulary_counts.py` exists one layer down.

---

## Related repositories and contracts

This package defines the contracts; these documents consume them. Each link goes to the
specific document, not the repository root.

| Repository | Document | What it takes from this package |
|---|---|---|
| solid-hyperobjects | [`assemblies/README.md`](https://github.com/madfam-org/solid-hyperobjects/blob/main/assemblies/README.md) | ASM-1 assemblies checked with `y4d-spec assembly check --collision`; assembly A, the [Voron 2.4-class 350 motion system](https://github.com/madfam-org/solid-hyperobjects/blob/main/assemblies/voron-2-4-class-350-motion-frame/README.md), is posable under ASM-1 §9 and is this package's fixture A and pose golden |
| solid-hyperobjects | [`README.md`](https://github.com/madfam-org/solid-hyperobjects/blob/main/README.md) (*How CI verifies a change*) | `y4d-spec check --render --parity` at the pinned `SPEC_PIN`, graph twins included |
| soft-hyperobjects | [`README.md`](https://github.com/madfam-org/soft-hyperobjects/blob/main/README.md) | `fc-spec` checks at its own `SPEC_PIN` |
| yantra4d | [`docs/guides/graph-cartridges.md`](https://github.com/madfam-org/yantra4d/blob/main/docs/guides/graph-cartridges.md) | the graph format (1.1) and the Studio graph editor; the transpiler vendored here is a byte-identical copy of the platform's |
| yantra4d | [`docs/operations/user-projects-storage.md`](https://github.com/madfam-org/yantra4d/blob/main/docs/operations/user-projects-storage.md), [`docs/operations/render-artifact-storage.md`](https://github.com/madfam-org/yantra4d/blob/main/docs/operations/render-artifact-storage.md) | where forks are stored and how renders are produced; GOC-1 sidecars are described in [`docs/reference/generator-output.md`](https://github.com/madfam-org/yantra4d/blob/main/docs/reference/generator-output.md) |
| asset-shells | [`README.md`](https://github.com/madfam-org/asset-shells/blob/main/README.md) (*Publish API*, *Twin graph*) | the AAS projection (SEM-1), projection versions 1–3 and the stored-shell resolver; it re-validates assembly shells with its pinned keystone (ASM-1 §6) |
| pravara-mes | [`packages/sparkplug/README.md`](https://github.com/madfam-org/pravara-mes/blob/main/packages/sparkplug/README.md) | machine telemetry; raw axis values are mapped through an assembly's machine bindings (ASM-1 §9.2) by the viewer, never by the MES |

Where the package stands — what landed, open PRs in merge order, the next pin bump — is in
[`docs/STATUS.md`](docs/STATUS.md) (dated; the open-PR list on GitHub is authoritative).

---

## What is in the box

| Package | What it is |
|---|---|
| `fc_spec` | the Fashion Cabinet conformance runner (`fc-spec`) |
| `y4d_spec` | the Yantra4D cartridge runner (`y4d-spec`) — manifest, files, geometry on **both engines** (CadQuery *and* OpenSCAD) at defaults *and* at every declared preset, printability notes, and the render-environment contract (`render-env`) |
| `bridge_check` | the FC↔Yantra4D hardware-link handshake (`ho-bridge`) |
| `commons_sandbox` | the restricted-execution core both platforms run cartridges through |
| `y4d_spec.assembly` | type-level assemblies (ASM-1): component resolvers, placement, closure of every mate, and the assembly digest (`y4d-spec assembly check`); ASM-1 §9 (v1.3): joints on mates (driven, follower, passive), machine-axis bindings, belt paths, the seeded pose sweep, the reference forward kinematics `pose()` and the golden pose files (`y4d-spec assembly poses`, `scripts/refresh_pose_golden.py`); see [`docs/ASSEMBLIES.md`](docs/ASSEMBLIES.md) |
| `y4d_spec.graph` | the **vendored** Yantra4D graph transpiler (`.graph.json` → CadQuery), byte-identical to the platform's, pinned by `graph.lock.json` and guarded by `scripts/qa/check_graph_sync.py` — see its `VENDORED.md` |
| `hyperobjects_schemas` | every bundled JSON Schema, plus the identity key and the GOC-1 generator-output digests and checker |
| `hyperobjects_lexicon` | the Commons Lexicon corpus, the controlled vocabularies, the fabrication vocabularies and their manifest-membership rule (SEM-1 §4), the article-frontmatter contract, the dictionary tools, the cross-commons reader (G4), and their lanes |
| `hyperobjects_aas` | the AAS v3.1 projection (SEM-1): cartridges, material cards and checked assemblies (ASM-1 §5: BoM, Mates, placement, Kinematics (§9), capability, requirement roll-up) → AAS Environments, the resolver that reads stored type shells back for re-validation (`hyperobjects_aas.resolver`), the IDTA conformance-claim rule, and `aas check`, with the official `aas.json` v3.1.2 **vendored** under CC-BY-4.0 — see `hyperobjects_aas/schemas/VENDORED.md` |
| `hyperobjects_standard_parts` | the standard-parts catalog (ASM-1 §4): one cited JSON entry per COTS part, the loader, parameter resolution, interface frames, the part digest, and the catalog lane |

```python
import hyperobjects_schemas as hs
hs.list_schemas()               # ['article-frontmatter', 'assembly', 'body-measurements',
                                #  'commons-vocabulary', 'cross-commons-identity',
                                #  'fabric-manifest', 'fabrication-vocabulary',
                                #  'garment-manifest', 'generator-output', 'lexicon-term',
                                #  'project-manifest', 'standard-part']
hs.load("project-manifest")
```

`commons_sandbox` is defense-in-depth, **not a security boundary on its own**. It blocks
casual file/network/code-exec inside a cartridge; the platform additionally runs it as a
killable subprocess with OS-level limits. Do not treat a passing `--render` as
permission to execute untrusted cartridges unsandboxed.

---

## Scope

`fc-spec` and `y4d-spec` check properties of **one cartridge**, checkable by anyone,
anywhere. `ho-bridge` is the one deliberate exception: a link is a property of a
*pair*, so it takes two checkouts and can only run where both are present. It is a
separate command for exactly that reason — nothing about the single-cartridge lanes
changed to accommodate it.

Repo-wide checks still stay in the platforms — catalog drift and cross-cartridge slug
uniqueness. They are properties of a whole commons, not of a cartridge or a pair.

**Cross-kernel parity moved.** It used to be on that list, as a repo-wide lane
(`tests/scripts/geometric_regression.py`), and that was the wrong shelf: whether a
cartridge's two kernels model the same solid is a property of **that cartridge**, not of
the commons around it — which is why `--parity` lives here now and runs on the merge
path. The platform's own numbers and gates are mirrored from
`yantra4d/scripts/qa/verify_parity.py`, deliberately, so the keystone and the platform
cannot disagree about what "agree" means.

The **lexicon** is the one thing here that is not per-cartridge, and it is here for the
opposite reason: it is a property of *both* commons at once, so it could not live in
either one (RFC 0039 §4). Its corpus ships with the package, so it stays checkable
without a platform checkout like everything else. The same argument carries its two
neighbours: the **controlled vocabularies** are about how the two repos spell one thing,
which no single repo can settle, and the **article frontmatter** is a contract both
catalog surfaces render from — while the articles themselves stay in each commons, as
each one's editorial property.

Platform maintainers: [`docs/P1B_ADOPTION.md`](docs/P1B_ADOPTION.md) is the checklist for
making `fashion-cabinet` and `yantra4d` consume this package, including every behavior
that had to be interpreted rather than copied, and
[`docs/COMMONS_VOCABULARY.md`](docs/COMMONS_VOCABULARY.md) is the checklist for the
per-commons half of the vocabulary, dictionary and article work — including the eight
capability spellings to rewrite, the one cartridge whose rename would have hidden a
missing bridge, and the review pass all of it is waiting on.

---

## Contributing

```bash
git clone https://github.com/madfam-org/hyperobjects-spec
cd hyperobjects-spec
python3 -m venv .venv && .venv/bin/pip install -e ".[geometry,dev]"
.venv/bin/python -m pytest -ra
.venv/bin/ruff check src tests
.venv/bin/fc-spec lexicon --catalog bundled        # the corpus lanes CI runs
.venv/bin/y4d-spec vocab
.venv/bin/fc-spec article examples --catalog bundled
.venv/bin/fc-spec reader --check          # docs/reader is committed; this is the diff
python3 scripts/refresh_reader_counts.py --check   # and so are the counts in this file
```

**The geometry lane is meant to actually run.** Tests marked `geometry` *skip* rather
than fail when cadquery/trimesh cannot import, so a run that installed the extra without
the system libraries above is green and has verified none of them. Read the `-ra` summary:
with the extra and its libraries present the suite reports **no skips**. CI does not rely
on the reader noticing — it installs `libgl1 libglib2.0-0 libxrender1`, prints the import
tracebacks and any unresolved soname, and **fails the job** before pytest if
`geometry_available()` is False.

That skip is a property a new test can break, and only off CI. `conftest.py` keys the skip
off the `geometry` marker, so a geometry test needs **both** the marker and a
`pytest.importorskip` placed **before** any module-scope `numpy`/`trimesh`/`cadquery`
import — an import at module scope raises during *collection*, which pytest reports as an
error and stops on, taking the rest of the suite with it rather than skipping one module.
Two cases were live until 2026-09-06 and were invisible because CI always has the extra:
`test_geometry_bodies.py` imported `numpy` above its `importorskip`, and four CLI tests
asserted argument-error text that `_cmd_check` only reaches once the geometry check has
passed. Run `pytest -q` in a `.[dev]`-only venv before you add one.

`docs/reader/` and the count blocks in this README are **generated and committed**. If
you change the corpus, a vocabulary or a snapshot, rebuild them in the same commit —
`fc-spec reader` and `scripts/refresh_reader_counts.py` — or CI will say so.

The test fixtures are **real cartridges** copied from both commons. They are correct
today, so a rule that flags them is wrong — which is how three false-positive rules were
caught before release, by running every rule against all 417 cartridges in the Yantra4D
commons. If you add a rule, calibrate it the same way: a rule that fires on healthy
cartridges is worse than no rule, because it teaches people to ignore the output.

Every ported rule cites its origin (file and line) in `y4d_spec/rules.py` and
`y4d_spec/structure.py`. Keep that up — it is what makes a divergence from the platform
visible instead of silent.

---

## License

Apache-2.0. The commons tooling is permissive so anyone can adopt it. One third-party
file is vendored under its own licence: `src/hyperobjects_aas/schemas/aas.json`, the
IDTA AAS v3.1.2 JSON Schema, CC-BY-4.0, with its attribution and licence text beside it. The platform
repos carry their own license (source-available per RFC 0038 P1); the commons objects
carry theirs (CERN-OHL-W-2.0 for solids; the FC1 ruling for soft goods).

## Why "hyperobjects"

We borrow the word twice. From the philosopher Timothy Morton (*Hyperobjects*,
University of Minnesota Press, 2013), whose hyperobjects are entities too vast to
point at — ours are **domestic hyperobjects**, the concept scaled to the workbench:
an object here is never the artifact but the family it regenerates into, a region of
parameter space sliced per render, real only through the contracts this package
validates. And from computing — *hyper-* as in hypertext and hyperparameter, the
object that generates objects. Both meanings are load-bearing; neither is a claim to
metaphysics. The long form lives in the
[Yantra4D manifesto](https://github.com/madfam-org/yantra4d/blob/main/docs/strategy/MANIFESTO.md#on-the-word-why-hyperobjects).
