# Hyperobjects Spec Agent Operating Guide

> Last Updated: 2026-09-06

<!-- MADFAM-AGENTS-CANONICAL v1 -->

This is the canonical instruction file for Claude, Codex, and any other LLM
agent working in this repository. `CLAUDE.md` is kept only as a compatibility
redirect and should not become the source of truth again.

## Required operating doctrine

- Read this file before making repo changes.
- Prefer existing repo conventions, scripts, and docs over introducing new
  patterns.
- Preserve user work and never revert unrelated changes.
- Treat production operations as Enclii-first: use Enclii web, API, or CLI for
  provisioning, deployment, observability, domains, secrets, provider
  operations, scaling, rollback, and remediation.
- Use direct `kubectl`, `helm`, SSH, provider CLIs/APIs, `docker exec`, or
  direct container access only for platform bootstrap or documented break-glass
  emergencies when Enclii is unavailable or lacks an implemented adapter.
- Record any missing Enclii adapter gap instead of normalizing raw production
  access in docs or runbooks.

## Repo entrypoints

- `README.md`
- `docs/`
- `.github/workflows/`

## LLM context files

- `llms.txt` is the compact context index.
- `llms-full.txt` is the durable full-context map and operating contract.
- `AGENTS.md` is canonical for agent instructions.
- `CLAUDE.md` redirects here for Claude compatibility.

## Maintenance

Regenerate or repair these files with
`internal-devops/scripts/sync-agent-docs.py` from the labspace ecosystem.

---

## Repo boundary — this repository is PUBLIC

`hyperobjects-spec` is a public, Apache-2.0 package that third parties install to
check a cartridge. The MADFAM repo-boundary contract applies with no exceptions:
**no secrets, no credentials, no internal hostnames or IPs, no client names, no
private-repo paths, and no operational runbook content.** Every rule cites a
*public* yantra4d/fashion-cabinet source; if a rule's justification can only be
stated by naming something internal, the rule does not belong here.

The commons rulings this package encodes (G27, G31, G33, G38, G39) are recorded
in the internal `repo-boundary contract` register alongside the coordination
runbooks. Cite the **ruling id and its public effect** here — never the runbook.

## What this repo is

The **keystone** of the MADFAM hyperobjects commons: the conformance bar for a
cartridge, as an installable package, with no platform checkout. Two commons
consume it — [yantra4d](https://github.com/madfam-org/yantra4d) (solid) and
[fashion-cabinet](https://github.com/madfam-org/fashion-cabinet) (soft) — and
both pin it **by SHA**. A change here reaches their CI on the next repin, so
treat every rule as a fleet-wide change.

`README.md` is the human document and stays authoritative on *why* each gate
exists. This file is the operating summary an agent needs before it edits a
cartridge or this package.

## Reading `y4d-spec check` output

Three tiers, and they are not interchangeable:

| Tier | Exit code | Means |
|---|---|---|
| `FAIL` | 1 | a conformance failure — the cartridge does not meet the bar |
| `note` | 0 | true, worth saying, not a failure (printability, an unresolved include, a placement offset, an exemption) |
| `skip` | 0 | **not verified** — a target nothing judged (e.g. no OpenSCAD binary) |

A skip is never a pass. The summary line separates them deliberately:

```
y4d-spec check: cartridges=1 failures=0 notes=1 geometry=verified renders=5 presets=2 skipped=0
```

- `geometry=NOT verified` — the run had no `--render`. It proved nothing about
  meshes; do not report it as a geometry pass.
- `renders=` counts meshes actually judged; `skipped=` counts the rest.
- With `--parity` a second clause is appended:

```
parity=N/M ok, warn=K, exempt=E, placement=P, failures=J
```

`N + K + E + J = M`. `placement=P` is a **subset of `N`**, not a fifth bucket —
those pairs agreed; `P` says how many owe that agreement to nothing but a
re-centring. An exemption is counted in `E` rather than removed from `M`, so a
manifest cannot shrink the denominator to look cleaner.

New rules land as notes first. A rule that fires on healthy cartridges is not
strict, it is wrong; nothing becomes a failure until its false-positive analysis
against the whole commons is written down (see `rules.py` for the killed ones).

## Reading a parity line

Four gates run per `(mode, part, preset)` that rendered on **both** kernels.
Gate 1 AABB extents (>0.001 mm fails, `--parity-tolerance` overrides this gate
and only this gate); gate 2 volume (>max(tolerance×100, 2 % of the larger),
watertight sides only); gate 3 **placement**; gate 4 **shape**.

```
parity (planter, planter): warn (faceting) — Bounding boxes differ by 0.033569mm
  (faceting warn, within 0.05mm; surfaces agree to 0.033569mm).
```
→ an OpenSCAD `$fn` chord approximation of a circle CadQuery models
analytically. A **note**. The downgrade is conjunctive: inside the 0.05 mm band
**and** the surfaces agree. A 0.04 mm dimensional error fits in the band, moves
a surface, and still fails.

```
parity (plaque, plaque): ok (placement) — placement offset
  d=(-40.000000, -20.000000, 0.000000) |d|=44.721360mm — the same shape at a
  different origin (surfaces agree to 0.374485mm after alignment)
```
→ same part, different origin (44.72 = √(40²+20²), half the plate diagonal). A
**note** by default: a slicer re-centres the part. Declare `"placement":
"strict"` to make it a failure — assemblies and animations place parts by their
model origin, and there the offset *is* the bug.

```
parity (slip_joint, blade): FAIL — surfaces diverge by 3.436337mm after
  alignment (placement offset d=(0.000000, 0.000000, 0.000000) |d|=0.000000mm)
```
→ zero offset, so origins explain nothing: the two kernels model a different
blade. Fix the cartridge. An **unmeasurable** shape proxy fails too — absence of
evidence is not agreement.

```
parity (block, block): exempt — the two kernels model this block with different
  idioms by design: …
```
→ declared in the manifest, printed every run, counted in `exempt=`.

## Declaring `verification`

```jsonc
"verification": {
  "stages": { "geometry": { "checks": {
    "parity": { "enabled": true, "tolerance": 0.05,
                "placement": "free", "reason": "…" }      // the base
  } } },
  "mode_overrides": { "<mode>": { "part_overrides": { "<part>": {
    "geometry.parity": { "enabled": false, "reason": "…" }  // per part
  } } } }
}
```

Rules, all enforced by `y4d-spec check` with **no `--render`** — in seconds, with
no CAD kernel, because a check that only ran where the comparison ran could be
switched off by switching the comparison off:

- A part override **replaces the base object whole**; it does not merge. One
  block carries that part's entire policy.
- `enabled: false` or a **widened** `tolerance` **requires a non-empty
  `reason`**. Silence is the thing being outlawed.
- The reason must name the **kernel idiom** that differs — "BOSL2 helical thread
  against a revolved sawtooth ring stack", never "known issue". An exemption is
  visible debt, reviewed whenever either kernel changes.
- `placement` is `"free"` (default) or `"strict"`. Strict needs no reason (it
  only tightens), but a **misspelled** value is a conformance failure rather
  than a silent fall back to the loose one.
- A **tightened** tolerance needs no reason. Writing the default longhand is not
  a departure. An explicit `--parity-tolerance` beats a manifest one; no number
  overrides an exemption.

## Every declared parameter must be referenced (G-DEADPARAM)

A `parameters[]` entry no source reads is a **conformance failure**: the UI offers a
control that changes nothing. Enforced by `y4d-spec check` with no `--render`.

**Why OpenSCAD is where this hides.** The platform passes every parameter as
`-D name=value`, and OpenSCAD accepts a `-D` for an identifier the file never
mentions **without any error**. So a `.scad` whose top says `phone_angle = 65;`
and which never reads it again renders an identical solid at every position of
the slider. Four dead sliders reached the solid commons this way.

How each dialect is asked:

- `.py` / `.cq` — the **bare identifier** in the executable text. Parameters
  arrive as bare globals (`cq_runner.py:43 exec_globals.update(params)`), so
  `PARAM(lambda: wall, 4.0)` counts because `wall` is inside it. `PARAM` is a
  cartridge-side idiom, **not** the accessor. Comments and string literals are
  stripped — naming a parameter in a docstring does not wire it. The
  `params["x"]` minority form is matched on the raw text.
- `.scad` — the identifier **outside its own declaration line**, because the
  `-D` overrides that line. `w = w * 2;` counts (the RHS reads the injected
  value); a `//` or `/* */` mention does not.
- `.graph.json` — a `parameters[].binding` naming a node param
  (`"outline.r"`, or a list of them). Graph cartridges bind from the **manifest**
  side; a graph parameter with no binding drives nothing.

Scope and exemptions:

- A parameter is judged **only against the modes that list it** (`modes` /
  `visible_in_modes`, intersected). One scoped to `over_center` and used there is
  alive even though six sibling modes never mention it.
- A reference in a library the cartridge **ships** counts — `include <>` is
  textual inclusion into the same variable scope. A target resolving outside the
  cartridge (`BOSL2/std.scad`, `../../libs/…`) is **skipped, never assumed**:
  treating an unreadable file as a reference would exempt every parameter of all
  43 BOSL2 cartridges. The rule can miss a dead parameter; it cannot invent one.
- `target_part` is exempt — the runner injects it to select a body.
- A mode whose sources are missing is not evidence; `mode_source_rules` already
  fails that cartridge.

The deliberate case, same shape and same argument as a parity exemption:

```jsonc
"intentionally_unused": { "reason": "reserved for a mode not yet written" }
```

The `reason` is **required and non-empty**, in the rule and in the schema. A
`reason` that is blank or absent is itself a failure. Do not reach for this to
quiet a finding you have not read: the three honest answers to a dead parameter
are **wire it, remove it, or allow-list it with a reason someone can review**.

## The `constraints[]` dialect — `safeFormula`, not expr-eval

`project.json`'s `constraints[]` are evaluated **client-side in the Studio** by a
hand-rolled parser, `apps/studio/src/lib/safeFormula.ts`, reached through
`hooks/editor/useConstraints.ts`. The Studio **dropped `expr-eval` on
2026-05-14**; anything (including older schema descriptions in the platform
repo) that still names it is stale.

Supported: numeric literals, bare parameter identifiers, `+ - * / %`,
`< <= > >= == != === !==`, `&& || !`, the ternary `c ? a : b`, parentheses.

**Not** supported, and this is where authored constraints go wrong:

- **No function calls.** No `min`, `max`, `abs`, `sqrt`, `floor`, `ceil`.
- **No string literals**, so a `select` parameter cannot be compared at all.
- Caps of **256 characters** and **128 tokens** per expression.

Semantics: the expression is the **satisfied** condition — truthy passes, falsy
raises `message` at the declared `severity` (`error` blocks, `warning` does
not). Either `expression` (what the commons authors) or the legacy `rule` key is
read.

**The trap:** `useConstraints` wraps evaluation in `try { … } catch {}`. An
expression that throws — unknown identifier, non-numeric parameter, division by
zero, an unsupported token such as a function call — is **swallowed and silently
never fires**. An untestable rule is indistinguishable from a satisfied one, so
a constraint that uses `min(a,b)` does not error: it simply never protects
anything. Evaluate a new rule against real parameter defaults before shipping
it.

## Changing this package

- Every ported rule **cites its origin** (file and line) in `y4d_spec/rules.py`
  and `y4d_spec/structure.py`. Keep the citation current — it is what makes a
  divergence from the platform visible instead of silent.
- The render environment (`y4d_spec/render_environment.py`) is the **single
  source** the platform image, the commons CI and the CI runner image all read.
  Do not add a fourth copy of the OpenSCAD version; read
  `y4d-spec render-env --openscad-version`. The pin is a **floor**: BOSL2
  v2.0.753 does not render below `2026.02.13`.
- Test fixtures are **real cartridges**. A rule that flags them is wrong.
- Geometry tests are marked `@pytest.mark.geometry` and **skip** (never fail)
  where the CAD kernel cannot import — `conftest.py` does that off the marker.
  Put `pytest.importorskip` **before** any module-scope `numpy`/`trimesh`
  import, or the whole run is interrupted at collection instead. CI installs the
  extra and fails the job when `geometry_available()` is False, so nothing
  skips there.
- `docs/reader/` and the count blocks in `README.md` are **generated and
  committed**; rebuild them in the same commit (`fc-spec reader`,
  `scripts/refresh_reader_counts.py`) or CI says so.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[geometry,dev]"
.venv/bin/python -m pytest -ra
.venv/bin/ruff check src tests
```
