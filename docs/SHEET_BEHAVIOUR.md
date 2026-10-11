# The sheet-behaviour contract (cross-commons)

> Public reference. Every number a rule writes cites the card field it came from, a public
> source, or a named assumption; see [PUBLIC_REPO_BOUNDARY.md](PUBLIC_REPO_BOUNDARY.md).

Three platforms model thin sheets, each with its own kernel, engine, commons and material
cards: **Pliego** (paper, board, foam: stock cards), **Fashion Cabinet** (fabric, felt:
fabric cards) and **Yantra4D** (thin prints: filament cards). They stay separate. This
keystone links them with three pieces and no shared solver:

1. a **`sheet_behaviour` block** any material card may carry: a neutral, unit-explicit,
   derived description of how the sheet stretches, bends, creases and touches;
2. **`material_ref`**: a cartridge in one commons uses a material another platform owns,
   by reference, the way `hardware_ref` already links a garment to a printed part;
3. **laminates**: a sheet made of stacked layers (bookcloth on board, a print on fabric, a
   foam core between liners), reduced to one `sheet_behaviour` by classical laminate
   theory.

Code: `hyperobjects_sheet` (validator, mapping rules, resolver, laminate calculator) and
`hyperobjects_schemas/schemas/sheet-behaviour.schema.json`. CLI: `fc-spec sheet …` and
`y4d-spec sheet …` (the contract belongs to no single commons, so both tools carry it).

**Data first, enforcement later.** No commons check calls any of this yet. The goldens
below are the evidence a later gate will be calibrated against, in the order
[COMMONS_VOCABULARY.md](COMMONS_VOCABULARY.md) sets out: land the data, measure it over
the commons, write the false-positive analysis, and only then fail anything.

---

## The document

```jsonc
{
  "sheet_behaviour": "1.0",
  "units": { "caliper": "mm", "areal_density": "kg/m^2", "membrane": "N/m",
             "bending": "N*m", "angle": "deg" },          // + compression, curvature, laminate
  "axis_1": "machine",            // machine | warp | wale | print | laminate | isotropic
  "source": { "platform": "pliego", "material_slug": "cardstock-250",
              "rule": "pliego-stock/1", "card_basis": "pliego.stock.derive v1" },
  "caliper_mm": 0.3,
  "areal_density_kg_m2": 0.25,
  "membrane": { "E1t": 1350000, "E2t": 600000, "G12t": 348300, "nu12": 0.4395 },
  "bending":  { "D11": 0.0110759, "D22": 0.0049226, "D12": 0.00216349, "D66": 0.00261225 },
  "crease":   { "crease_length_scale_t": 200, "crease_yield_deg": 35,
                "crease_set_rate": 0.5, "score_factor": 0.35 },
  "regime":   { "inextensible": true, "stretchy": false, "compressible": false,
                "layered": false, "self_folding": false },
  "contact":  { "friction_static": 0.4 },
  "provenance": { "E1t": { "status": "estimated", "basis": "derived.E_md × t; …" }, … },
  "notes": [ "…" ]
}
```

### Fields and units

| Field | Unit | Meaning |
|---|---|---|
| `caliper_mm` | mm | thickness |
| `areal_density_kg_m2` | kg/m² | mass per area (g/m² ÷ 1000) |
| `membrane.E1t`, `E2t` | N/m | in-plane modulus × thickness along axis 1 and axis 2 |
| `membrane.G12t` | N/m | in-plane shear modulus × thickness |
| `membrane.nu12` | 1 | major Poisson ratio: axis-2 strain per axis-1 strain under axis-1 load |
| `bending.D11`, `D22`, `D12`, `D66` | N·m | plate bending stiffness (moment per width per curvature) |
| `bending.D16`, `D26` | N·m | optional; 0 in principal axes; written by an angle-ply stack |
| `crease.crease_length_scale_t` | 1 | crease hinge length L* in calipers (L* = value × t) |
| `crease.crease_yield_deg` | deg | spring-back opening after a crease is released |
| `crease.crease_set_rate` | 1 | how fast a held fold sets, 0–1 |
| `crease.score_factor` | 1 | a scored line's yield relative to an unscored one, (0, 1] |
| `compression.Ez` | Pa | thickness-compression modulus (felt, foam) |
| `self_folding.trigger`, `target_curvature_1_m` | –, 1/m | a 4-D sheet's trigger and target curvature [k1, k2, k12] |
| `contact.friction_static`, `friction_kinetic` | 1 | Coulomb coefficients against the same material |
| `contact.damping` | 1 | fraction of critical damping |
| `laminate.A`, `B`, `D` | N/m, N, N·m | the stack's matrices (Voigt order 1, 2, 6) |

Axis 1 is the material's principal direction: the machine direction of paper, the warp of
a woven, the wale of a knit, the printer's x axis for a thin print, the laminate x axis of
a stack. `isotropic` says the two directions carry the same numbers.

The `units` block is fixed by version 1 (the schema pins each value), and it travels with
every document so the numbers are never separated from their units. A document that
carries `compression`, `self_folding` or `laminate` must also carry that block's unit.

### Provenance: one entry per number

Every numeric field has an entry under its own name in `provenance`; an entry with no
number, or a number with no entry, is an error.

| Status | Means |
|---|---|
| `measured` | the quantity itself was measured, or stated by its maker (Pliego's `nominal`, a fabric card's value). A unit conversion keeps the status. |
| `derived` | computed by a stated formula from measured inputs only |
| `estimated` | a literature or engineering estimate, or computed from **any** estimated input |

`basis` is always required. It names the formula, the card fields, their own statuses and
sources, and any assumption. An engine can then say how far to trust a number, and a
reader can trace every one back to a card field or a citation.

### Regimes

| Flag | Engine reading |
|---|---|
| `inextensible` | membrane strain is negligible next to bending: treat the sheet as isometric (paper, board, tight wovens) |
| `stretchy` | large in-plane strain is part of the behaviour (knits, elastane, TPU) |
| `compressible` | thickness changes under load; needs `compression.Ez` (felt, foam) |
| `layered` | a stack; needs the `laminate` block |
| `self_folding` | a 4-D sheet; needs the `self_folding` block |

`inextensible` and `stretchy` exclude each other; neither means an ordinary extensible
sheet.

### What the validator says

`hyperobjects_sheet.validate(doc)` returns errors and notes.

**Errors** (the document is not admissible):
- schema violations;
- a membrane stiffness that is not positive definite (`nu12² ≥ E1t/E2t`);
- a bending matrix that is not positive definite (Cholesky on D, D16/D26 included);
- contradictory regime flags, or a flag without its block (or a block without its flag);
- a missing unit for an optional block;
- provenance that does not match the numbers one to one;
- a laminate whose `coupled` disagrees with B, or whose layers do not add up to the caliper.

**Notes** (true and worth saying, never failures):
- an implied bulk density outside 10–3000 kg/m³;
- a single-layer `D11` outside 0.1–10× the plate value `E1t·t²/(12(1−ν12ν21))`. This is
  expected for fabric, whose yarns slide; it is suspect for paper or film;
- a document whose every number is estimated.

---

## Mapping rules

Each platform keeps its card. These rules are the keystone's reading of the cards; when a
platform starts writing `sheet_behaviour` onto its own cards, a carried block takes
precedence (see `material_ref` below).

### `pliego-stock/1` — Pliego stock card → sheet_behaviour

The rule reads the card's **derived** block (`derived_basis: "pliego.stock.derive v1"`,
engine units mm, g, s) and the statuses of the `physical` measurements it came from. A card
without a derived block, or with another derive version, is refused.

| Field | From |
|---|---|
| `caliper_mm` | `derived.thickness` |
| `areal_density_kg_m2` | `derived.areal_density` (g/mm²) × 1000 |
| `E1t`, `E2t` | `derived.E_md`, `E_cd` (Pa) × t (m) |
| `G12t` | `derived.G12` × t: the Baum estimate 0.387·√(E_md·E_cd), always `estimated` |
| `nu12` | ν·√(E_md/E_cd). The card's ν is the geometric mean √(ν12·ν21); reciprocity ν12/E1 = ν21/E2 splits it. |
| `D11`, `D22` | `derived.D_md`, `D_cd` × 1e-9. That is the plate formula, or a measured bending stiffness when the card has one (then `measured`). |
| `D12` | ν21·D11 (orthotropic plate) |
| `D66` | G12·t³/12 |
| `crease.*` | `physical.crease_length_scale_t`; `derived.crease_yield_deg`, `crease_set_rate`, `score_factor`. A derive default says so in its basis. |
| `contact.friction_static` | `derived.friction` |
| regime | inextensible |

Status mapping: Pliego `measured` and `nominal` map to `measured`, and `estimated` stays
`estimated`. A computed field takes `derived` only when every input is measured.
`derived.crease_k` is cross-checked against the stated L*/t, and a mismatch is a note.

Caveats:
- the card states one paper-on-paper friction, so it is written as static, and kinetic
  friction and damping are left out;
- `tear_strain`, `perf_factor` and `collision_thickness` have no field in v1 (see open
  items);
- a stock card that one day describes foam must also map `compression.Ez`; the rule
  refuses nothing today because no foam card exists yet.

### `fc-fabric/1` — Fashion Cabinet fabric card → sheet_behaviour

A fabric card has `physical` (g/m², thickness, stretch %) and `digital_twin.physics`
(weight, a bend class, stretch %). It has no physical stiffness. Fashion Cabinet
deliberately emits none, because an elongation % means nothing without the test load it
was measured under. A sheet engine needs a stiffness anyway, so this rule produces one and
marks every such number `estimated` under the assumption that produced it.

| Field | From | Basis |
|---|---|---|
| `caliper_mm` | `physical.thickness_mm` | card value (`measured`, as FC's own preset sidecar treats it) |
| `areal_density_kg_m2` | `weight_gsm` (twin first, then `physical.gsm`) ÷ 1000 | card value |
| `E1t`, `E2t` | 490.33 N/m ÷ (stretch % ÷ 100) | **secant at an assumed 500 gf/cm**, the KES-FB1 tensile maximum. FAST's 100 gf/cm would give 5× less. |
| `G12t` | 56.19 N/m | an assumed shear rigidity of 1 gf/(cm·deg), the order of magnitude typical of apparel fabrics in KES-FB1, used for every class |
| `nu12` | 0.3 | assumed; fabric Poisson ratios vary widely |
| `D11` = `D22` | bend class → KES-FB2 B (gf·cm²/cm) × 9.80665e-5 | a geometric ladder: very-soft 0.02, soft 0.04, medium-soft 0.07, medium 0.12, medium-stiff 0.2, stiff 0.35, very-stiff 0.6. It spans the ≈0.01–1 order of magnitude apparel fabrics occupy, with one class for both directions. |
| `D12`, `D66` | ν·D, (1−ν)/2·D | isotropic plate relations |
| regime | stretchy when the larger stretch is ≥ 10 %, inextensible when it is ≤ 2 % | keystone convention |

Caveats:
- the cards record no friction or damping, so `contact` is left out rather than invented;
- `axis_1` is `wale` for a knit and `warp` otherwise;
- `tpu-panel-impreso` is mapped as the card describes it, as cloth. Its printed solid is a
  Yantra4D cartridge, and the laminate reading of a thin print is `y4d-thin-print/1`;
- the bend-class ladder is a **convention**. Calibrate it against measured KES-FB2 or
  cantilever (ASTM D1388) data before trusting a drape.

### `y4d-thin-print/1` — Yantra4D filament card + thin-print descriptor → sheet_behaviour

A filament card is not a sheet. A single- or few-layer print becomes one through its print
parameters, given in a descriptor:

```jsonc
{ "material_ref": { "platform": "yantra4d", "material_slug": "bambu-tpu-95a", "behaviour": "sheet" },
  "layers": 4, "layer_height_mm": 0.2, "pattern": "rectilinear",
  "raster_angles_deg": [45, -45], "infill": 1.0 }
```

Each layer is a lamina. The bead direction carries infill × E_xy. The cross-bead direction
carries infill × E_z: the inter-layer bond the datasheet measures stands in for the
inter-bead bond. Shear is G = √(E_L·E_T)/(2(1+ν)). The stack is reduced by the laminate
calculator below, with plate bending per layer. Everything is `estimated`.

Today's cards carry no modulus or density, so the rule keeps a small table of public
datasheet values (`hyperobjects_sheet.stack.FILAMENTS`, each with its URL) that a
descriptor can override under `filament`. `bambu-tpu-95a` uses Bambu Lab's TPU 95A HF
datasheet V1.0: E_xy 9.8 MPa, E_z 7.4 MPa (ISO 527) and 1.22 g/cm³. That is the HF grade's
sheet, not the plain 95A the card names, and the basis says so. ν = 0.45 is assumed.

The card is still read:
- a total thickness below `am_compensations.minimum_features.wall_thickness` is a note;
- an EMMO `Elastomer` class makes the print `stretchy` and suppresses the crease block.

Only `rectilinear` has a rule. Any other pattern is refused rather than guessed.
Perimeters are ignored, and infill scales the moduli linearly (an upper bound for sparse
fill).

---

## `material_ref` — using another platform's material

```json
{"platform": "fashion-cabinet", "material_slug": "popelina-algodon", "behaviour": "sheet"}
```

`resolve_material_ref(ref, {platform: materials_dir})` (CLI `sheet resolve … --materials
PLATFORM=DIR`; a platform or commons root with a `materials/` child works too) answers
name-level questions first, exactly as `ho-bridge` rule 1 does for `hardware_ref`
([BRIDGE_HANDSHAKE.md](BRIDGE_HANDSHAKE.md)):

| Verdict | Means |
|---|---|
| `carries` | the card carries a valid `sheet_behaviour` block (the keystone mapping is not consulted) |
| `maps` | a keystone rule maps the card to a valid document |
| `needs-descriptor` | a Yantra4D filament card: it is a sheet only through a thin-print descriptor |
| `unresolved` | no directory for the platform, no card, a card that names itself otherwise, an invalid carried block, or a card the rule refuses |

`role` and `linked` are accepted beside the three keys, so the sheet commons' manifest
shape (`{platform, material_slug, role[, linked]}`) can adopt `behaviour` without a second
shape. Physical checks (does this felt really drape like that) come later, with
calibration data, never before it.

---

## Laminates

`hyperobjects_sheet.laminate` is classical laminate theory with engineering shear strain,
`z` running from the bottom face (−h/2) up, layer 0 at the bottom:

    A = Σ Q̄ₖ tₖ     B = Σ Q̄ₖ tₖ z̄ₖ     D = Σ (ownₖ + Q̄ₖ tₖ z̄ₖ²)

`Q̄ = T₁⁻¹·Q·T₂` rotates each layer's stiffness into laminate axes. It is tested against
Kaw, *Mechanics of Composite Materials* (2nd ed.), Examples 2.6, 2.7 and 4.2, to the four
digits printed, and against the closed forms: an isotropic plate, B = 0 for symmetric
stacks, B11 = −B22 for an antisymmetric cross-ply, only B16/B26 for an antisymmetric
angle-ply, and Timoshenko's equal-layer bimetal strip.

- **Own bending.** A homogeneous layer's own term is the plate value `Q̄ t³/12`. A fabric
  bends orders of magnitude below that. A layer that comes from a card therefore
  contributes its **card** bending, rotated, as its own term. The parallel-axis term is
  kept, because it is membrane stiffness carried off the mid-plane. A lamina given by
  constants uses the plate. Each layer records which one it used (`own_bending`).
- **Coupling.** A non-zero B means stretching bends the stack and bending stretches it.
  It is flagged (`coupled`, `coupling_ratio` = max|B| / √(max|A|·max|D|)), never failed.
  This is how a covered board warps and how a print on fabric curls.
- **Pre-strain.** A layer may carry a stress-free strain `prestrain: [e1, e2, g12]`
  relative to the bonded state. A fabric stretched by 15 % before printing has −0.15. The
  free stack's mid-plane strain and curvature are reported (`prestrain_response`).
  Linear theory at such strains is itself an estimate.
- **The stack's `sheet_behaviour`.** Membrane constants and bending are those of the
  **free** stack, from the inverse of the 6 × 6 ABD matrix: `D* = D − B·A⁻¹·B`. The
  stack is `inextensible` or `stretchy` only when every layer says so, and a lamina
  states no regime. Crease and contact are not computed: a laminate's crease is not its
  layers' creases.

A laminate document lists layers bottom first. Each layer is a `material_ref`, an inline
`sheet` (a local stock) or a `lamina` (`E1_pa`, `E2_pa`, `G12_pa`, `nu12`,
`density_kg_m3`), with `angle_deg`, an optional `thickness_mm` (default: the card's
caliper) and optional `prestrain` and `own_bending`.

```
$ fc-spec sheet laminate tests/fixtures/sheet-behaviour/laminates/print-on-stretched-tricot.json \
    --materials fashion-cabinet=tests/fixtures/sheet-behaviour/cards/fashion-cabinet > /dev/null
fc-spec sheet laminate: layers=2 thickness_mm=0.95 coupled=yes coupling_ratio=0.697 curvature_1_m=[224.1, 225.9, 0] valid=yes
```

---

## Fixtures and goldens

`tests/fixtures/sheet-behaviour/` (provenance and licences in its `NOTICE.md`):

- `cards/` — byte-identical copies of every Pliego stock card (14), every Fashion Cabinet
  fabric card (11) and the Yantra4D `bambu-tpu-95a` card;
- `thin-prints/` — two descriptors (an antisymmetric ±45° print, coupled; a symmetric
  0/90/90/0 print, not coupled);
- `laminates/` — bookcloth on cardstock, and a TPU print on pre-stretched tricot;
- `golden/` — what each rule writes today. Regenerate them with
  `python3 scripts/refresh_sheet_behaviour_golden.py`, and `--check` in CI. Review every
  moved number: some engine reads it.

## Limits and open items

- **Calibration sources for felt and foam.** No felt fabric card or foam stock card exists
  yet. Their `compression.Ez`, bending and crease numbers need either measurements
  (thickness-compression curves, cantilever bending, crease recovery) or cited literature
  estimates. Until then the `compressible` path is exercised only by a unit test.
- **Self-folding** has a v1 shape (trigger and target curvature) and no producer yet.
- **Fields not in v1:** tear strain, perforation strength, collision thickness, a
  temperature range for heat forming, and separate static and kinetic friction for the
  cards that state one value. Add them when a producer and a consumer both exist
  (additive, minor version).
- **Processes.** The fabrication vocabulary has no sheet processes yet (cut, score, sew,
  glue, heat-form). So `material_ref` cannot check a cartridge's process needs; that check
  waits for the vocabulary.
- **Fabric stiffness is a convention** (assumed test load, bend-class ladder, one shear
  value). Fabric cards that record a test load, a KES/FAST bending value or a cantilever
  length would let the rule mark them `measured` or `derived`.
- **Thin prints:** filament moduli belong on the Yantra4D cards; `FILAMENTS` is a stopgap
  with sources. Patterns other than rectilinear need their own effective-moduli rule.
