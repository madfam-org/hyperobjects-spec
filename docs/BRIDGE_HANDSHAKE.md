# The bridge handshake

`ho-bridge` verifies an FC↔Yantra4D hardware link **physically**. This document is
the rule record: what each rule claims, why it is allowed to claim it, what the
calibration sweep of the real commons found, and which candidate rules were killed
before they could land. It follows the style `y4d_spec/rules.py` set — a rule with no
calibration story is not a rule, it is a guess with a CI lane.

---

## Why this exists

A Fashion Cabinet notion declares its hardware in `notion.hardware_ref`:

```json
{ "platform": "yantra4d", "project_slug": "strap-ring", "linked": true,
  "params_map": { "webbing_w": "webbing_width", "opening": "webbing_width + 6" } }
```

`fc_spec.rules.hardware_ref_rules` checks that `strap-ring` resolves, that
`webbing_w` and `opening` are real parameters of it, and that `webbing_width` is a
real parameter of the garment. All three are name-level facts. All three can hold
while the link is false:

* **the values may be unbuildable.** `strap-ring`'s script contains
  `opening = max(6.0, min(opening, webbing_w * 2.0))`. Feed it a mapped `opening`
  above twice the webbing width and the ring silently comes back a different size
  than the garment asked for. No error, no warning, a wrong part.
* **a key may drive nothing.** It is declared in the target's manifest, so it
  resolves; the script never reads it. The mapping is decoration.

Neither is visible without building the solid. So this tool builds it.

---

## The three rules

### Rule 1 — RESOLVE (always runs, no CAD kernel)

Two halves.

**1a, delegated.** `fc_spec.rules.hardware_ref_rules` is called directly, with a
resolution surface built from the y4d checkout. Not reimplemented: one parser, one
grammar, no drift. If the spec's rule changes, this tool changes with it.

**1b, new.** Every `params_map` value is **evaluated** against the garment's
parameter defaults. The structural rule only *parses* the expression to collect
identifiers; it never asks whether a number comes out. A parameter declared without
a `default`, a select whose default is a string, a division by a parameter defaulting
to zero — all pass 1a and fail 1b, and all would otherwise surface as a confusing
render error three steps later.

The evaluator is a restricted AST walk over literals, names, arithmetic operators,
and calls to `fc_spec.rules.SAFE_MAP_FUNCS` — **never `eval`**. `SAFE_MAP_FUNCS` is
imported rather than re-listed so the two can never disagree about what a safe call
is. A manifest is third-party input; this is the only place the tool consumes an
expression, and it stays a parser.

### Rule 2 — RENDER AT MAPPED VALUES (needs `[geometry]`)

`y4d_spec.geometry.render_part` — imported, not forked. That function replicates
yantra4d's own `cq_runner` execution contract line for line, including the
`trimesh.load(process=False)` that keeps the default repair pipeline from sealing the
very hole being looked for. A second copy would drift from the platform inside one
release.

Params are the y4d cartridge's manifest defaults with the evaluated mapping merged
over them. Rendering with *only* the mapped values would be wrong: unmapped
parameters would arrive absent, the cartridge's `PARAM()` idiom would fall back to
the literals in its source, and any manifest↔source drift would silently change what
was measured.

The target is the `(mode, part)` set owned by the mapped parameters, read from each
y4d parameter's `modes` scope. Ownership is ambiguous in two directions — a
parameter with no `modes` is global and tells you nothing, and mapped parameters
spanning disjoint scopes mean the garment drives several variants — and **both fall
back to the first CadQuery mode's parts**, with a note. That is not a cop-out: the
platform's own default when a user opens a cartridge is its first mode, so a link
proven at the first mode is a link proven at what the user actually sees.

### Rule 3 — RESPONSIVENESS (needs `[geometry]`)

Re-render with one mapped parameter at +10 %; the summed volume across the rendered
targets must move by more than `1e-6`. A key that changes nothing is dead wiring.

The volume is **summed across targets**, not compared per part. A mapped parameter
may legitimately drive one part of a multi-part mode and not the others; judging it
against a single part would report a live parameter dead.

`1e-6` is a floating-point equality guard, not a manufacturing tolerance. STL export
is deterministic for identical input, so a genuinely responsive parameter moves the
volume by orders of magnitude more.

---

## Guards — every one of these exists because the naive rule was wrong

The responsiveness rule is the one with teeth, so it carries the most guards. Each
guard prevents a **false positive manufactured by the checker itself**, which is the
worst kind: it is indistinguishable from a finding, and it trains people to ignore
the tool.

| Guard | Without it |
|---|---|
| **Target healthy at its own defaults** | Two real yantra4d cartridges fail `y4d-spec check --render` at their defaults. Every garment linking them would be reported broken, blaming the FC side for a solid that was broken before the garment existed. Now: skipped with a note naming the tool that owns the defect. |
| **Perturbation clamped into `[min, max]`** | A +10 % probe that leaves the declared range gets clamped by the cartridge, the volume does not move, and a healthy parameter reads as dead. |
| **Default at max → perturb −10 %** | Clamping +10 % back to `max` leaves the value unchanged, producing zero signal and a false "dead" verdict on the most common boundary case. |
| **No room either way → skip, never fail** | A pinned parameter (`min == max`) proves nothing in either direction. Silence is the honest answer. |
| **Integral parameters step by ≥ 1** | `+10 %` of `hook_count = 5` is `5.5`, and the cartridge's `int(PARAM(...))` truncates it back to `5`. Zero signal, guaranteed false "dead" on **every count parameter in the commons**. Found by calibration on `ankle-gaiter → lacing-hook`. |
| **Out-of-range mapped value → its own verdict** | A value the target already rejects (`pitch = 26` against a declared max of `25`) is clamped by the cartridge, so a perturbation moves nothing and the key reads as dead. It is a real finding — the garment gets a part it did not order — but a *different* one, and giving a real problem the wrong name is its own false positive. |
| **Non-numeric parameters skipped** | "+10 %" of a select's string or a toggle's bool is meaningless. |
| **Render failure at the perturbed value is a `render_fail`, not a dead param** | It is a real finding — the link sits on a cliff edge that any real-world tolerance walks off — but it is a *different* finding, and conflating the two makes both unactionable. |
| **`MAX_PROBES = 3` per link** | The widest links map six parameters. At ~15–25 s a render, an uncapped sweep of the commons runs for many hours. |
| **`MAX_TARGETS = 4` per link** | The render count is `targets × (2 + probes)`, and ownership resolution can select several modes at once. `zipper`'s `zip_length` is scoped to both `closed` and `separating`, which declare seven parts between them, so each of the **eleven** zipper links wanted 21+ renders — of a 300 mm zipper. Measured over the commons: **1080 renders for a full sweep**, ~250 of them the zipper family alone. Capping does not weaken the claim (responsiveness is a *sum* over rendered targets, so any part moving still proves the key live) and every capped link names what it skipped. |
| **Problem lists truncated to 3 + a count** | The first calibration run emitted a single 40,000-character line for one cartridge (200+ per-body messages). Unreadable output is unread output. |

---

## Calibration — the full commons sweep

Run read-only against the real repos:

```bash
ho-bridge check --fc ./fashion-cabinet --y4d ./yantra4d -v
```

### Shape of the commons

97 Fashion Cabinet cartridges declare a `notion.hardware_ref`; 96 are `linked: true`
(`hi-vis-vest → hook-loop-tape` is declared but unlinked, so it is not a link and is
not checked). Those 96 links carry **207 `params_map` entries** between them. The
most-linked hardware is `zipper` (11 links), then `strap-buckle` (8).

Cost, measured rather than estimated: **1080 renders** for an uncapped full sweep at
`MAX_PROBES = 3`, at 15–25 s each. That is the reason both caps exist, and the reason
a full sweep is an audit you schedule rather than a pre-commit hook.

### Results

**Structural resolution (rule 1), all 96 links: zero failures.** Every linked
`hardware_ref` in the Fashion Cabinet commons resolves to a real yantra4d cartridge,
names real parameters on both sides, and evaluates to numbers. The name-level bar is
genuinely met — which is exactly why a name-level bar was not enough to keep
believing in.

**The geometric sweep (rules 2–3)** over 54 links, excluding the `zipper` family
which was run separately at a reduced budget:

```
ok 43   render_fail 2   dead_params 0   skipped 9   range_notes 10
```

**`render_fail` — 2 links, one root cause, both real:**

* **`balconette-bra → bra-underwire`** — renders clean at the cartridge's defaults,
  fails at the mapped values: not watertight, plus an inverted body. The garment
  hardcodes `wire_d: "1.4"` against a `bra-underwire` whose declared minimum is
  **1.5**. It is asking for a wire thinner than the hardware supports, and the solid
  degenerates.
* **`underwire-bra → bra-underwire`** — same hardcoded `wire_d: "1.4"`. Here the
  solid survives at the mapped `cup_width` of 130 and breaks when the probe moves it
  to 143 — a value **well inside** the declared 80–160 range. This is the cliff-edge
  case: the link sits on the edge of what the solid can build, and any real-world
  size change walks it off. It is reported as a `render_fail`, not a dead param,
  because the two need different fixes.

Both are one defect in two garments. `bra-underwire` itself is healthy —
`y4d-spec check bra-underwire --render` passes — so these are genuinely findings
about the *links*, which is the entire point of the tool.

**`dead_params` — zero.** No genuinely dead wiring survived in the swept set. The two
keys the first uncalibrated run reported as dead were both the checker's own bugs
(see the killed rules below). Reporting zero here is the honest result, and it is
worth noting that the rule still has teeth: it is exercised end-to-end by
`test_a_params_map_key_the_script_ignores_is_caught_as_dead`, on a fixture whose
structural check passes.

**`skipped` — 9 links, 3 yantra4d cartridges broken at their own defaults:**
`strap-buckle` (7 links), `magnetic-clasp` (1), `tpu-scale-mail` (1). Each fails
`y4d-spec check --render` with no garment involved — `strap-buckle` produces an
inverted body on all three of its parts. These are real bugs, but they belong to
`y4d-spec` and to the yantra4d maintainers; attributing them to the garments that
link them would be blaming the wrong side.

**`range_notes` — 10 out-of-range mappings across 8 links** (non-blocking; see the
measurement lane above). Every one is the garment asking for **more** than the
hardware declares, never less — except the two `wire_d` cases, which ask for less:

| link | mapping | declared |
|---|---|---|
| `ankle-gaiter → lacing-hook` | `pitch` = 26 | max 25 |
| `beret-structured → hat-size-reducer` | `strip_height` = 32 | max 30 |
| `pillbox-hat → hat-size-reducer` | `strip_height` = 40 | max 30 |
| `structured-fascinator → fascinator-base` | `brim_w` = 32 | max 30 |
| `suit-trousers → trouser-hook-bar` | `hook_width` = 38 | max 20 |
| `tool-roll → cord-end` | `bell_flare` = 2.5 | max 2 |
| `turban-band → headband-blank` | `band_w` = 55 | max 45 |
| `turban-band → headband-blank` | `head_width` = 190 | max 180 |
| `balconette-bra → bra-underwire` | `wire_d` = 1.4 | **min 1.5** |
| `underwire-bra → bra-underwire` | `wire_d` = 1.4 | **min 1.5** |

The pattern is informative and is why this rule is not yet a gate. Eight of the ten
overshoot a maximum by a modest margin (`hook_width` = 38 against max 20 is the
outlier), which is the signature of a y4d slider range that is narrower than the real
part rather than of eight independently broken garments. The two that *undershoot* a
minimum are different in kind: both break the render, and both are unambiguous bugs.
That split — same rule, two very different populations — is precisely what the
doctrine's calibration step exists to expose, and it means the rule should probably
land as a failure only for `min` violations, with `max` violations staying a note
until the range-vs-hint question is settled with the yantra4d side.

**Cost, measured.** The 54-link sweep ran as four parallel shards. The `zipper`
family (11 links) had to be run separately at `--max-targets 2 --max-probes 2` and is
still the dominant cost of any full sweep: `zip_length` maps from garment body
lengths of 300 mm and up, and a 300 mm zipper is an enormous solid.

### The measurement lane — out-of-range mappings

One rule is **deliberately non-blocking**, per the house doctrine that a new rule
lands as a measurement, gets calibrated against the full commons, and only flips to a
failure once its false-positive analysis is written down.

A mapped value outside the target parameter's declared `min`/`max` is reported under
`MEASUREMENT (non-blocking)` and counted as `range_notes=N` in the summary. It does
not affect the exit code and does not make the link `FAIL`.

It is a real finding: the cartridge clamps the value, and the garment receives a part
of a different size than its manifest claims. But two things must be settled before
it may block:

1. **Is the y4d `min`/`max` a hard constraint or a UI hint?** The manifest range
   drives the studio's slider. Some cartridges clamp to the same numbers in-script
   (`lacing-hook` does); others clamp to different ones, or not at all. If a
   cartridge accepts values outside its declared slider range, an out-of-range
   mapping may be entirely safe and the *manifest* is what needs widening.
2. **How many links does it fire on, and are they the same defect?** One instance
   (`ankle-gaiter → lacing-hook`) is an anecdote. The sweep count decides whether
   this is a handful of genuine bugs or a systematic mismatch between how the two
   commons declare ranges — and those need opposite fixes.

Until both are answered it measures, and says out loud that it is measuring.

### Killed rules

Recorded so they are not re-proposed.

**KILLED: "render failure at the mapped values is always a bridge finding."**
This was the first version of rule 2, and the first calibration run immediately
produced two failures that were not bridge findings at all — `magnetic-clasp` and
`tpu-scale-mail` both fail `y4d-spec check --render` at their own defaults, with no
garment involved. Attributing a pre-existing cartridge defect to the link would blame
the wrong maintainer for the wrong bug, and would bury the real findings in noise.
Replaced by the baseline: **a render problem is a bridge finding only when the
cartridge is healthy at its defaults and unhealthy at the mapped values.** The
difference is caused by the mapping, and the mapping is the only thing this tool is
entitled to judge.

**KILLED: "a mapped parameter that does not move the volume is dead."**
True in spirit, false as written — it fires on every parameter whose +10 % probe
leaves the declared range, on every parameter already at its maximum, and on every
non-numeric parameter. Those are three separate false-positive classes and all three
appear in the real commons. Replaced by the guarded form in the table above, where an
unprovable parameter is *skipped and counted*, never failed.

**KILLED: "perturb every parameter by +10 %."** Correct for continuous sliders, wrong
for counts. The commons declares integral parameters as ordinary sliders with
`step: 1` (`lacing-hook`'s `hook_count` is `type: "slider", step: 1, default: 4`) and
its script reads them through `int(PARAM(...))`. A +10 % probe of `5` produces `5.5`,
which truncates straight back to `5` — the volume cannot move, and **every count
parameter in the commons** would have been reported as dead wiring. Replaced by a
probe that moves an integral parameter by at least one whole step. This was the first
of the two false positives inside `ankle-gaiter → lacing-hook`.

**KILLED: "a mapped value the target clamps is a dead key."** The second false
positive in the same link. `ankle-gaiter` maps `pitch` = 26 to a `lacing-hook`
parameter whose declared max is 25; the cartridge clamps it, so no perturbation moves
anything and the naive rule called the key dead. It is not dead — it is
**out of range**, which is a real and arguably more serious finding (the garment
receives a part of a size it did not order), but it is a *different* finding.
Reporting a real problem under the wrong name is its own kind of false positive: it
sends the maintainer to fix wiring that is fine. Now detected separately, and — per
house doctrine — landed as a **non-blocking measurement** until it has its own
calibration sweep and false-positive write-up.

**KILLED: "compare per-part volumes."** A mapped parameter driving exactly one part
of a multi-part mode reads as dead against the other parts. Replaced by the summed
volume across rendered targets.

**KILLED: "use `eval` for the params_map expressions — the grammar is tiny."**
The grammar is tiny; the input is a third party's manifest. Replaced by the
restricted AST walk, which refuses anything outside the whitelist rather than
executing it. Covered by a test that feeds it `__import__('os').system(...)`.

---

## What phase 2 needs: true dimensional measurement

Everything above proves the link is **live**: the solid builds at the mapped values,
and the mapped keys move it. What it does *not* prove is that the two parts **fit** —
that the hardware's mating feature has the dimension the garment's edge expects.
`ho-bridge` today would pass a link that drives a zipper's tape edge to 400 mm when
the garment's opening is 300 mm, as long as both render and both respond.

`fc_spec.rules.hardware_dimensional_rules` reaches for this and stops at the honest
limit: it checks that the garment parameter feeding the hardware's flange also drives
one of the garment's own interfaces — a *coupling* claim, still name-level. Phase 2 is
the measurement that would close it.

**The blocker is not geometry, it is the interface contract.** Measuring a mating
feature requires knowing which faces of the rendered solid constitute it, and that is
per-interface knowledge no manifest currently carries. A y4d `cdg_interface` declares
an id, a `geometry_type`, and the parameters that drive it. It does not declare
*where the feature is on the body*. Without that, a checker can measure the whole
part's bounding box and nothing finer — and a bounding box is not a mating dimension
for anything but the simplest flange.

So phase 2 needs, **per interface geometry type**, a declared *measurable*. The
vocabulary is not hypothetical — every one of the 59 distinct y4d cartridges the
Fashion Cabinet bridges to already declares `cdg_interfaces`, and their types
distribute like this:

| `geometry_type` on bridged targets | count |
|---|---|
| `flange` | 42 |
| `snap` | 37 |
| `socket` | 17 |
| `profile` | 7 |
| `pocket` | 4 |
| `rail` | 4 |
| `bolt_pattern` | 4 |
| `custom`, `thread`, `boss`, `surface`, `grid` | 9 combined |

That distribution is the work order — measurables are worth defining in the order the
commons actually uses them, not in the order they are easy.

* **`flange` (42)** — the sewn mating edge: zipper tape, hook-and-loop, bias binding.
  Needs the edge's *length* and *thickness*: a face selector, the plane the length is
  measured in, or a pair of named datum points. The check is then the garment's edge
  length against the hardware's at the mapped values, plus a declared ease. Highest
  count and the most mechanical — it covers the whole zipper family (11 links).
* **`snap` (37) / `socket` (17)** — the engaging pair: snaps, magnetic clasps,
  chicago screws, grommets. Needs the *mating diameter* and *engagement depth* as a
  pair, plus which half of the pair this cartridge is. A tolerance band is
  unavoidable — an interference fit is a range, not a number — so the manifest must
  carry a **fit class**, not just a dimension. Together these are the largest group,
  and they cannot be done without the tolerance convention below.
* **`profile` (7) / `rail` (4)** — the channel families: boning stays, underwires,
  busks. Needs a *cross-section at a named station* plus a *path length*. The hardest
  measurable, because the section is a curve rather than a scalar and the garment's
  channel is sewn to a seam length that only the explode-JSON payload knows.
* **The pass-through case has no type of its own, and that is itself a finding.**
  A ring, an eyelet, or a cord lock is the place today's checker is weakest and the
  silent-clamp bug bites hardest: `strap-ring` clamps `opening` to `webbing_w * 2`,
  and the garment has no way to learn its webbing will not pass. The measurable
  wanted is a *clear opening* — the minimum inscribed circle or rectangle through the
  aperture, never the outer diameter. Today those cartridges declare `socket` or
  `custom`, which does not distinguish "something seats in this" from "something
  passes through this". Phase 2 should either add a `bore` type or require a
  `clear_opening` measurable on the sockets that are really pass-throughs.

Two supporting pieces are needed on top of the per-interface measurables:

1. **A units and datum convention.** The commons is in millimetres, which settles
   scale but not origin: a measurement is meaningless without knowing which face is
   the datum. This has to be declared once for the whole commons, not per cartridge.
2. **A declared ease per link, not per part.** A 300 mm garment opening and a 300 mm
   zipper is not a fit — the tape needs its seam allowance. Ease lives on the *link*,
   because the same zipper sews into a jacket and a cushion cover with different
   allowances. `hardware_ref` has no field for it today.

The recommended order follows the counts and the dependencies:

1. **`flange`** — 42 interfaces, one scalar (edge length), and the zipper family
   behind it. It needs the ease convention but not the tolerance one.
2. **the pass-through measurable** — a single scalar (clear opening), and it is
   where the silent clamp this tool was built to hunt actually lives. Small, and it
   closes the `strap-ring` class of failure outright.
3. **`snap` / `socket`** — the biggest group combined, but blocked on the fit-class
   convention; not expressible before it exists.
4. **`profile` / `rail`** — last, because a cross-section is not a scalar and the
   garment side of the comparison lives in explode JSON rather than the manifest.

The honest summary: phase 1 (this tool) proves a link is **live**. Phase 2 proves it
**fits**, and the blocker is a manifest contract, not a geometry algorithm.

Until then, `ho-bridge` claims exactly what it can prove — the link is live, not that
the parts fit — and the summary line counts every skip so nobody mistakes one for the
other.
