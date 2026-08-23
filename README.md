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
pip install "hyperobjects-spec[geometry] @ git+https://github.com/madfam-org/hyperobjects-spec@v0.1.0"

y4d-spec check ./my-cartridge --render          # a Yantra4D cartridge, geometry and all
fc-spec check garment-manifest ./my-garment.json
```

Passing these checks and passing the platforms' CI are meant to be the same thing.

---

## Install

```bash
# Manifest conformance only — pure python, runs in under a second.
pip install "hyperobjects-spec @ git+https://github.com/madfam-org/hyperobjects-spec@v0.1.0"

# Plus geometry verification: actually renders your cartridge and inspects the mesh.
# Pulls a CAD kernel (~400MB), so it is opt-in.
pip install "hyperobjects-spec[geometry] @ git+https://github.com/madfam-org/hyperobjects-spec@v0.1.0"
```

Python 3.11+.

---

## `y4d-spec` — Yantra4D cartridges

```bash
y4d-spec check ./my-cartridge              # manifest + files
y4d-spec check ./my-cartridge --render     # + render every (mode, part) and judge the mesh
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

```
$ y4d-spec check ./sew-on-snap --render -v
  ok sew-on-snap (./sew-on-snap, 3 render(s) verified)
       (set, set): ok — volume 415.56mm³, 2 body/bodies, watertight
       (stud, stud): ok — volume 227.55mm³, 1 body/bodies, watertight
       (socket, socket): ok — volume 188.01mm³, 1 body/bodies, watertight
y4d-spec check: cartridges=1 failures=0 notes=0 geometry=verified renders=3
```

Without `--render`, the summary says `geometry=NOT verified` — a run that skipped the
render lane must never read like one that passed it.

**Notes vs failures.** Some things are true and worth saying but are not conformance
failures — an `include <../../libs/BOSL2/std.scad>` works inside the Yantra4D repo and
nowhere else. Those print as `note` and never change the exit code.

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

## What is in the box

| Package | What it is |
|---|---|
| `fc_spec` | the Fashion Cabinet conformance runner (`fc-spec`) |
| `y4d_spec` | the Yantra4D cartridge runner (`y4d-spec`) |
| `bridge_check` | the FC↔Yantra4D hardware-link handshake (`ho-bridge`) |
| `commons_sandbox` | the restricted-execution core both platforms run cartridges through |
| `hyperobjects_schemas` | every bundled JSON Schema, plus the identity key |

```python
import hyperobjects_schemas as hs
hs.list_schemas()               # ['body-measurements', 'cross-commons-identity',
                                #  'fabric-manifest', 'garment-manifest', 'project-manifest']
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
