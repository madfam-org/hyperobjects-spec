# The reference-objects catalog

> Public reference data. Every fact here cites a maker's page, a manual, a museum record, a
> filing, a computation over cited inputs, or our own measurement of a specimen; see
> [PUBLIC_REPO_BOUNDARY.md](PUBLIC_REPO_BOUNDARY.md).

A **reference object** is a real commercial product described by its published facts:
- a console, a handheld or a phone;
- a controller;
- a media format, a case, a carton or a booklet;
- an accessory;
- one published **edition** of a game title, which joins the others by key (below).

A commons **family** cartridge is an archetype we own and license. It turns those facts into a
named **preset**: the geometry is the family's, the numbers are the maker's. The catalog lives
in `src/hyperobjects_reference/objects/`, one JSON file per object named `{key}.json`. Each file
is validated by `reference-object.schema.json` and checked by `ho-reference check`.

```python
from hyperobjects_reference import load_family, value_at, is_sourced, family_digest

for obj in load_family("clamshell-dual-screen-handheld"):
    closed = value_at(obj, "dimensions_mm.states.closed")   # {"width", "height", "depth"}
    is_sourced(obj, "controls")                             # the maker's list is complete
family_digest("clamshell-dual-screen-handheld")             # what a generator records
```

## Why it lives here

Owner ruling, 2026-11-01: *all geometry lives under yantra4d, the hyperobjects commons and the
adjacent 3D/4D platforms; consumers ingest prerendered models and never hold geometry.* The
facts a preset is generated from are part of that geometry.

They sit in the keystone, beside the standard-parts catalog, for three reasons:
- the catalog has the same contract as standard parts: facts only, every number cited, never
  CAD;
- both commons already pin the keystone, so a solid preset (a cartridge) and a sheet preset (the
  box it ships in) can read the same object without one commons pinning the other;
- no consumer keeps a second copy.

| Concern | Lives in |
|---|---|
| The facts, with their sources | this catalog |
| The family geometry and its generated presets | the solid and sheet commons |
| Rendering and prerendering | yantra4d and Pliego |
| Showing it | consumers, which read published artifacts only |

## The rules

1. **`null` = unresolved, never guessed.**
2. **Every non-null value is covered by a source.**
   - The source's `field` must be the value's path or an ancestor of it:
     `dimensions_mm.states.closed`, `displays[0]`, `features.page_count`.
   - An empty index covers that path in every item of the list: `displays[].panel` covers
     `displays[1].panel` and nothing else of `displays[1]`.
   - An item's identifying label (`role`, `kind`) is sourced when anything about the item is.
3. **A covered list is complete.**
   - A covered `controls`, `ports` or `media` list is the source's own complete list, so a kind
     it does not contain is a **sourced absence**. Generators read it as a zero.
   - An uncovered list says nothing either way (`is_sourced`).
4. **Tiers.** Each tier has fields that make it checkable:

   | Tier | What it is | Must carry |
   |---|---|---|
   | `primary` | the maker's own spec page, press release, manual or press kit | `url`, `quote` |
   | `museum` | a collection record that publishes the object's measurements | `url`, `quote` |
   | `regulatory` | a filing (FCC and the like) | `url`, `quote` |
   | `derived` | a computation over cited inputs | `method` (the formula and its inputs' sources) |
   | `measured` | our instrument on a physical specimen | `instrument`, `resolution_mm`, `specimen`, `measurer_role`, and **no** URL |
   | `secondary` | a page that **locates** a primary source | `url`; it covers **no** value |

5. **Derived display areas obey one law.**
   - `width = 25.4·D·a/√(a²+b²)` and `height = 25.4·D·b/√(a²+b²)`, with `a:b` taken from
     `resolution_px` (else `aspect`), rounded half-up to 0.1 mm.
   - An area covered by a `derived` source must equal it and be marked `derived: true`.
   - Correcting an input is a recomputation, never a hand edit.
6. **Conflicts are decided in the open.**
   - Where sources disagree (Nintendo's own pages give two Game Boy masses), `conflicts[]`
     lists every candidate with its source, the chosen one, and why.
   - The object's value must equal the choice.
7. **Status is honest.** `unverified` holds exactly when no value-tier source exists.
8. **A booklet's page count is printable.** It is positive, and a multiple of 4 when the
   binding is `saddle_stitch` (nested sheets of four pages each).
9. **A container holds other objects, once each.** No `contents[]` key is the object's own,
   and no key appears twice: one item carries the count.
10. **An edition's keys resolve to the right kind** (below). A key the catalog does not hold is
    a `note`, never a failure.

Never in an object:
- CAD, artwork or logos;
- a likeness fitted from photographs;
- a person's name (a measurement records the measurer's **role**);
- leaked or confidential documents.

Review sites, fan wikis and retailer listings may only locate a primary source.

## Editions, containers and the fit (gate G-X2)

### The `edition` kind

An **edition** is one published release of a game title on one platform in one region. Its
physical parts are other catalog objects, so an edition carries no `dimensions_mm` (every other
kind must). It carries an `edition` block instead, and only an edition may:

| Field | What it holds |
|---|---|
| `title` | the title as printed |
| `platform` | the key of the console it runs on: kind `device` |
| `region` | a market region (`JP`, `NA`, `EU`, `AU`, `KR`, `CN`, `global`) or, for a country release, its ISO 3166-1 alpha-2 code |
| `product_code` | as printed on the box, label or spine |
| `released` | the date, to the precision the source gives |
| `media` | `{key, count}`: a kind `media` object (a `plug-in-media` or `disc-media` preset) and how many |
| `package` | the key of a kind `case` or `carton` object |
| `booklet` | `{pages, page_width_mm, page_height_mm, binding, cover_stock?}`; `binding` is `saddle_stitch`, `perfect`, `folded` or `none` |
| `inserts[]` | `{kind, width_mm, height_mm, folds?}`, flat sizes; `kind` is `poster`, `map`, `registration_card`, `catalog`, `overlay`, `sticker` or `other` |
| `bundled[]` | keys of the other objects in the box (a Rumble Pak, a stand) |

- Every value is a fact. `edition` is a fact root like `dimensions_mm`, so each of its values is
  covered by a source (a specimen in hand is `measured`).
- `null` is unresolved. A source on a null `booklet` records a sourced "no manual". A covered
  `inserts` or `bundled` list is complete.
- **References resolve when the catalog holds them** (rule 10). `platform` must name a `device`,
  `media.key` a `media` object, `package` a `case` or a `carton`, and a `bundled` key anything
  but another edition. A key the catalog does not hold yet is a note, so an edition can land
  before its formats do:

  ```
  note fixture-rally-64-na: edition.package names 'nintendo-64-carton', which this catalog does not hold yet — its kind is not checked
  ho-reference check: objects=4 values=52 failures=0 notes=5
  ```

- `tests/fixtures/reference/` holds two fictional editions, a game card and a keep case. They
  show the shape and drive the tests. Real editions join the bundled catalog only with measured
  or cited data.

### Containers: `contents[]` and the inside

- Any container object (a case, a carton) may state what it holds as `contents[]`, a list of
  `{key, count}` items. An item's `key` is sourced when anything about the item is, as a port's
  `kind` is. Its keys resolve like an edition's, note-only.
- A container's **inside**, per axis, is `features.inside_width_mm` / `inside_height_mm` /
  `inside_depth_mm` when not null. Otherwise it is the `closed` state less twice
  `features.wall_mm` (one wall each side).

### The fit: `ho-reference fit`

```
ho-reference fit --container KEY --content KEY [--clearance-mm X] [--objects DIR] [--json]
```

```python
from hyperobjects_reference import load_object
from hyperobjects_reference.fit import fit

result = fit(load_object(container_key), load_object(content_key), clearance_mm=0.5)
result.verdict      # "fits" | "does not fit" | "unknown (null input)"
```

This is the keystone half of gate G-X2. A box comes from the sheet commons and its cartridge
from the solid commons, and neither commons pins the other, so the fit is decided here, over
the facts both read. Pliego's `content_ref` and the commons' title-edition kits call it.

- **Content envelope**: the content's `shell` state, else `body`, else `closed`.
- **Required**, per axis: the content plus twice `--clearance-mm`. The clearance is **per side**,
  and defaults to 0.
- **Axes compare as labelled.** Both objects label `width`, `height` and `depth` in the same frame
  (face width and height, then thickness). A rotated fit is never inferred.
- Arithmetic is decimal, and a zero margin fits.

| Verdict | When | Exit |
|---|---|---|
| `fits` | every axis has room | 0 |
| `does not fit` | an axis with known inputs is short, whatever the others say | 1 |
| `unknown (null input)` | no axis is short, but an input is null; each null path is listed | 3, never a pass |
| (usage) | a key the catalog does not hold, or a negative clearance | 2 |

```
ho-reference fit: container=fixture-keep-case content=fixture-game-card envelope=shell clearance=0.5mm/side
  width  inside=121 (features.inside_width_mm) required=36 margin=85 ok
  height inside=133 (features.inside_height_mm) required=34 margin=99 ok
  depth  inside=11 (features.inside_depth_mm) required=4.8 margin=6.2 ok
ho-reference fit: fits
```

A container that holds several objects (a carton with a case, a booklet and a tray) is checked
one content at a time today. Stacking them into one envelope is the consumer's composition.

## Measuring a specimen (`measured`)

- Calipers at 0.01 mm resolution, plus a steel rule for spans over 150 mm.
- Each value is measured twice and the mean recorded. A spread over 0.1 mm goes in `notes`.
- `specimen` names the unit: model number, region and a collection id, never an owner's name.
- `measurer_role` is a role: owner, volunteer or curator.
- Makers measure bodies **excluding projecting parts** (sticks, feet, buttons), and a measured
  envelope says the same in `dimensions_mm.excludes_projections`.

## How a commons consumes it

A family's generator (`tools/presets/<family>.py` in the commons):
1. reads `load_family(<family>)` at the keystone pin;
2. maps the object's labelled axes onto its own parameters (each family README states the map);
3. applies the archetype rules that are the family's own;
4. writes `presets[]` together with `_generated_from`, which records the keystone version and
   `family_digest(<family>)`.

The digest is order- and formatting-free, so it moves only when a fact or a source does. A
corrected measurement is one PR here, then a regenerated preset on the next pin.

## Provenance of the first 84 objects

The catalog opened, on 2026-11-01, with the 84 dual-screen and foldable devices of Telesia's
`data/registry/device-geometry.json` (`telesia.device_geometry.v1`, snapshot 2026-09-13,
sha256 `ce75eed4ecfe7e3078a4a05eac9ebd720653cd0f2923cd46f022440d8008e0f0`). That is the snapshot
the commons' `clamshell-dual-screen-handheld` and `book-fold-phone` presets were generated from.

The import moved the facts without changing them, apart from four kinds of edit:
- `dimensions_mm.closed` / `.open` became `dimensions_mm.states.closed` / `.open`.
- `telesia_platform_hint` became `external_ids.igdb_platform`, in the data and in the notes that name it.
- An all-null `resolution_px` (`[null, null]`) became `null`, and a source's null URL was
  omitted.
- **Evidence sweep.** 17 objects carried list items that no source covered: one port in each of
  14 Samsung entries, and placeholder display slots in two OPPO entries and the Sony Tablet P.
  They were removed under the registry's own rule (a value without a citation is an assertion,
  not evidence). Each object's `notes` keeps them verbatim for re-sourcing.

A round trip back to the original format differs only by those four.
