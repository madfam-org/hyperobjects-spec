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
| **Non-numeric parameters skipped** | "+10 %" of a select's string or a toggle's bool is meaningless. |
| **Render failure at the perturbed value is a `render_fail`, not a dead param** | It is a real finding — the link sits on a cliff edge that any real-world tolerance walks off — but it is a *different* finding, and conflating the two makes both unactionable. |
| **`MAX_PROBES = 3` per link** | The widest links map six parameters. At ~15–25 s a render, an uncapped sweep of the commons runs for many hours. |
| **Problem lists truncated to 3 + a count** | The first calibration run emitted a single 40,000-character line for one cartridge (200+ per-body messages). Unreadable output is unread output. |

---

## Calibration — the full commons sweep

Run read-only against the real repos:

```bash
ho-bridge check --fc ./fashion-cabinet --y4d ./yantra4d -v
```

**Structural resolution (rule 1), all 96 links: zero failures.** Every linked
`hardware_ref` in the Fashion Cabinet commons resolves to a real yantra4d cartridge,
names real parameters on both sides, and evaluates to numbers. The name-level bar is
genuinely met — which is exactly why a name-level bar was not enough to keep
believing in.

Findings from the geometric sweep are recorded in the release notes for this rule
set; the load-bearing ones are the **dead `params_map` keys**, because they are
invisible to every other tool in the commons and they mean a garment maker adjusting
a slider gets a hardware part that does not change.

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

So phase 2 needs, per interface geometry type, a declared **measurable**:

* **`flange`** (a sewn edge — zipper tape, hook-and-loop, bias binding). Needs the
  edge's *length* and *thickness* as a measurable: a face selector, a plane the
  length is measured in, or a pair of named datum points. Then the check is the
  garment's edge length against the hardware's, at the mapped values, with a declared
  ease. This is the highest-value type — it covers the zipper (11 links), the
  hook-loop tape, and the binding families.
* **`bore` / `pass-through`** (a ring, an eyelet, a cord lock). Needs the *clear
  opening* — a minimum inscribed circle or rectangle through the aperture, not the
  outer diameter. This is where today's tool is weakest and the clamping bug bites
  hardest: `strap-ring` clamps `opening` to `webbing_w * 2`, and the garment has no
  way to learn that its webbing will not pass. A measured clear opening compared
  against the garment's webbing width would catch it directly.
* **`stud` / `socket`** (snaps, magnetic clasps, chicago screws). Needs the *mating
  diameter and engagement depth* as a pair, plus which of the pair this cartridge is.
  A tolerance band is unavoidable here — an interference fit is a range, not a
  number — so the manifest must carry a fit class, not just a dimension.
* **`channel`** (a boning stay, an underwire, a busk). Needs the *cross-section
  profile* at a named station and the channel's *path length*. The hardest of the
  four, because the profile is a curve rather than a scalar, and a garment's channel
  is sewn to a seam length that only the explode-JSON payload knows.

Two supporting pieces are needed on top of the per-interface measurables:

1. **A units and datum convention.** The commons is in millimetres, which settles
   scale but not origin: a measurement is meaningless without knowing which face is
   the datum. This has to be declared once for the whole commons, not per cartridge.
2. **A declared ease per link, not per part.** A 300 mm garment opening and a 300 mm
   zipper is not a fit — the tape needs its seam allowance. Ease lives on the *link*,
   because the same zipper sews into a jacket and a cushion cover with different
   allowances. `hardware_ref` has no field for it today.

The recommended order is `bore` first: it is a single scalar, it has the most links
behind it, and it is where the silent-clamp failure this tool was built to hunt
actually lives. `flange` second, on link count. `stud`/`socket` and `channel` after
the ease and datum conventions exist, because neither is expressible without them.

Until then, `ho-bridge` claims exactly what it can prove — the link is live, not that
the parts fit — and the summary line counts every skip so nobody mistakes one for the
other.
