# hyperobjects-spec

**Validate a MADFAM hyperobject cartridge with zero platform code.**

The MADFAM commons has two halves. [Yantra4D](https://github.com/madfam-org/yantra4d)
holds the **solid** cartridges — printed and machined bodies, rendered from CadQuery or
OpenSCAD. [Fashion Cabinet](https://github.com/madfam-org/fashion-cabinet) holds the
**soft** ones — garments, notions, fabric cards. Both are commons: anyone may
contribute a cartridge.

Until now you could not check one without cloning a platform. The bar lived inside the
repos — half of it in an installable package, half in loose `scripts/qa/*.py` that
imported the API app. This package is that bar, extracted: one `pip install`, two
commands, no platform checkout.

```bash
pip install "hyperobjects-spec[geometry] @ git+https://github.com/madfam-org/hyperobjects-spec@v0.2.0"

y4d-spec check ./my-cartridge --render          # a Yantra4D cartridge, geometry and all
fc-spec check garment-manifest ./my-garment.json
```

Passing these checks and passing the platforms' CI are meant to be the same thing.

---

## Install

```bash
# Manifest conformance only — pure python, runs in under a second.
pip install "hyperobjects-spec @ git+https://github.com/madfam-org/hyperobjects-spec@v0.2.0"

# Plus geometry verification: actually renders your cartridge and inspects the mesh.
# Pulls a CAD kernel (~400MB), so it is opt-in.
pip install "hyperobjects-spec[geometry] @ git+https://github.com/madfam-org/hyperobjects-spec@v0.2.0"
```

Python 3.11+.

---

## `y4d-spec` — Yantra4D cartridges

```bash
y4d-spec check ./my-cartridge              # manifest + files
y4d-spec check ./my-cartridge --render     # + render every (mode, part) AND every preset
y4d-spec check ./my-cartridge --render --no-presets        # defaults only (weaker)
y4d-spec check ./my-cartridge --render --no-printability   # skip the print-time notes
y4d-spec check ./cartridges/*/ -v          # many at once
y4d-spec rules                             # what gets checked, and where each rule came from
```

A cartridge directory is anything with a `project.json`.

**What `check` does**

1. Validates the manifest against `project-manifest.schema.json`.
2. Applies the per-cartridge house rules — mode/part/parameter cross-references, the
   `target_part` dispatch alignment, `hyperobject` block coherence, `{en, es}`
   completeness, license declaration. Every rule names its source in the Yantra4D repo;
   run `y4d-spec rules` to see them.
3. Checks the files: mode sources exist, no includes escaping the cartridge, no
   vendored tree, no shipped LICENSE contradicting the declared one.

**What `--render` adds.** It executes your cartridge for every `(mode, part)` pair
through the *same restricted sandbox the platform uses*, then requires each mesh to be

- **watertight** — it encloses a volume,
- **positive volume**,
- **free of inverted bodies** — no negative-volume shell in `split()`,
- **distinct per part** — two parts rendering identical geometry means your
  `target_part` dispatch is not wired, and the platform will silently serve the wrong
  body.

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
restate the defaults (the UI's reset button) are exempt. `--no-presets` skips the lane;
OpenSCAD modes are skipped there exactly as they are in the defaults pass.

**Printability notes.** `--render` also *measures* each passing mesh for print-time
trouble and says what it found — **never as a failure**:

- **thin walls** — median local wall thickness below 0.8mm (two 0.4mm nozzle perimeters),
- **overhangs** — more than 25% of surface area in unsupported downward slope (over 45°
  from vertical, excluding the face resting on the bed),
- **build volume** — bounding box over 256mm on any axis.

Every note names the number it measured, because **every one of these thresholds is
provisional** pending a full-commons calibration. They are measurements you can argue
with, not rules you have to satisfy. `--no-printability` skips them.

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
y4d-spec check: cartridges=1 failures=0 notes=1 geometry=verified renders=5 presets=2
```

That note is a good illustration of the posture: it is *true* — the 9mm snap's
sew-hole webbing really does measure 0.76mm — and it is *marginal*, 0.04mm under a
provisional bar, on a cartridge that prints fine today. So it gets said, with its
number attached, and the exit code stays `0`.

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

---

## `fc-spec` — Fashion Cabinet contracts

```bash
fc-spec list                                     # the checkable contracts
fc-spec check garment-manifest my-cartridge.json
fc-spec check body-measurements my-body.json
fc-spec check fabric-card my-material.json
fc-spec check explode-json my-explode.json
fc-spec check hardware-ref my-notion.json --resolve yantra4d-commons-catalog.json
```

| Contract | Validates |
|---|---|
| `garment-manifest` | a cartridge's `project.json` |
| `fabric-card` | a `material.json` fabric card |
| `body-measurements` | a body / size measurement set |
| `hardware-ref` | a notion's Yantra4D `hardware_ref` link |
| `explode-json` | the native fabrication payload |

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

Exit code is nonzero on `render_fail` or `dead_params`. Renders are seconds each, so
step 3 probes at most `--max-probes` (default 3) parameters per link.

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
```

```
$ y4d-spec lexicon --catalog bundled
y4d-spec lexicon: terms=30 failures=0 embodied_by=resolved
lexicon_status: 30/30 terms quadrilingual (es/en/fr/pt) domains=6
```

Without `--catalog`, the summary says `embodied_by=NOT resolved (94 refs)` — the same
read-proof bar `--render` holds. A run that skipped a check must never read like one
that passed it.

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
| `embodied_by` | a slug does not resolve — **only when a catalog is supplied** |

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

### How platforms consume it

```python
from hyperobjects_lexicon import load_lexicon, check_lexicon, lexicon_status

lex = load_lexicon()                       # the bundled corpus, id -> term dict
lex["tape-edge"]["term"]["pt"]             # 'debrum de fita costurado'
lex["tape-edge"]["aliases"]                # both dialects, each with its repo

check_lexicon(lex).ok                      # the lane, as a library call
lexicon_status(lex)                        # the house N/M line
```

Each platform renders its own surfaces from this — term popovers on catalog facets and
parameter labels, an A–Z lexicon page, and the `define(term, lang)` MCP tool — while the
*articles* stay in each commons as each one's editorial property (RFC 0039 §2, §4).

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

```bash
.venv/bin/fc-spec lexicon --catalog bundled   # then run the lane
.venv/bin/python -m pytest tests/test_lexicon.py
```

Renaming an `id` is a **breaking change**: it is what `see_also` points at and what a
platform's `define()` resolves.

---

## What is in the box

| Package | What it is |
|---|---|
| `fc_spec` | the Fashion Cabinet conformance runner (`fc-spec`) |
| `y4d_spec` | the Yantra4D cartridge runner (`y4d-spec`) — manifest, files, geometry at defaults *and* at every declared preset, plus printability notes |
| `bridge_check` | the FC↔Yantra4D hardware-link handshake (`ho-bridge`) |
| `commons_sandbox` | the restricted-execution core both platforms run cartridges through |
| `hyperobjects_schemas` | every bundled JSON Schema, plus the identity key |
| `hyperobjects_lexicon` | the Commons Lexicon corpus and its validation lane |

```python
import hyperobjects_schemas as hs
hs.list_schemas()               # ['body-measurements', 'cross-commons-identity',
                                #  'fabric-manifest', 'garment-manifest', 'lexicon-term',
                                #  'project-manifest']
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

Repo-wide checks still stay in the platforms — catalog drift, cross-cartridge slug
uniqueness, and OpenSCAD↔CadQuery geometric parity. They are properties of a whole
commons, not of a cartridge or a pair.

The **lexicon** is the one thing here that is not per-cartridge, and it is here for the
opposite reason: it is a property of *both* commons at once, so it could not live in
either one (RFC 0039 §4). Its corpus ships with the package, so it stays checkable
without a platform checkout like everything else.

Platform maintainers: [`docs/P1B_ADOPTION.md`](docs/P1B_ADOPTION.md) is the checklist for
making `fashion-cabinet` and `yantra4d` consume this package, including every behavior
that had to be interpreted rather than copied.

---

## Contributing

```bash
git clone https://github.com/madfam-org/hyperobjects-spec
cd hyperobjects-spec
python3 -m venv .venv && .venv/bin/pip install -e ".[geometry,dev]"
.venv/bin/python -m pytest -ra
.venv/bin/ruff check src tests
```

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

Apache-2.0. The commons tooling is permissive so anyone can adopt it. The platform
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
