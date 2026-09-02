# Adopting the controlled vocabularies and the article layer

RFC 0039's phases **G2** (article elevation) and **G3** (term waves + the MCP dictionary
tools) each have two halves. One half is shared — a contract, a corpus, a lane — and it
lives in this package. The other half is per-commons: a compliance check inside Fashion
Cabinet, an article view inside each catalog surface, an MCP tool registration inside
each server. **This document is the checklist for that second half.**

Nothing here has been done. The vocabularies were built read-only against both platform
repos, exactly as the conformance bar was.

The ordering principle throughout, same as [P1B_ADOPTION.md](P1B_ADOPTION.md): **land the
data before enforcing it.** A lane that starts failing cartridges in the same commit that
introduces the vocabulary has no way back if the vocabulary is wrong.

---

## What shipped here

| Artifact | What it is |
|---|---|
| `hyperobjects_lexicon/vocabularies/interfaces.json` | 44 entries: both commons' interface types and the recurring ids, with 5 cross-commons `equivalent_to` pairs and 1 `distinct_from` pair |
| `hyperobjects_lexicon/vocabularies/capabilities.json` | 126 entries + 8 aliases = every one of the 134 capability keys the 516 FC cartridges write |
| `commons-vocabulary.schema.json` | the contract both documents validate against |
| `article-frontmatter.schema.json` | G2's frontmatter contract, plus `examples/chaleco-charro.article.json` as the exemplar |
| `fc-spec vocab` / `y4d-spec vocab` | the vocabulary lane |
| `fc-spec article <path>…` | the article lane, which scans directories |
| `define` / `lookup` / `related` | RFC 0039 §6.2, as library functions and as CLI subcommands |
| `docs/reader/` + `fc-spec reader` / `y4d-spec reader` | G4's cross-commons reader: one lexicon, both encyclopaedias, the bridge graph as navigation — built from pinned snapshots, committed, `--check` in CI |

The capture behind the counts: yantra4d 500 cartridges (`docs/commons-catalog.json`),
fashion-cabinet 516 (`projects/*/project.json`), both at 2026-09-02. Each side is read out
of a **commit** with `git show` — never off a working tree — and each document's own
`captured.sources` block records the **full sha** it was read at, so the capture is
reproducible and the rev is one a later reader can resolve exactly. Re-run it with
`scripts/refresh_vocabulary_counts.py` (`--yantra4d-ref` / `--fashion-cabinet-ref`, both
defaulting to `origin/main`), which rewrites the counts, leaves every editorial field
alone, and **fails on a key nobody has placed** — that failure is the drift alarm.

## What the reader publishes about itself

G4's reader is built from snapshots pinned in this repo, so its counts are a statement
about a specific pair of commits and not about "the commons today". They are emitted by
`scripts/refresh_reader_counts.py`, never typed.

<!-- counts:reader:start -->
| Layer | Pages | Languages present (es/en/fr/pt) |
|---|--:|---|
| terms | 147 | 147 / 147 / 147 / 147 |
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
fc-spec reader --check: out=docs/reader pages=1189 differences=0
reader_status: pages=1189 terms=147 yantra4d=510 fashion-cabinet=527 bridges: edges=303 resolved=302 unresolved=1 unlinked=1 back=302 mirrored=302
```
<!-- counts:reader:end -->

The reader is the shared half of G4, the same way the frontmatter contract is the shared
half of G2. The per-commons half is unchanged and unstarted: each platform still renders
its own article view and its own term popovers from this package's data. What the reader
adds is the one surface where a visitor can hold both commons at once — and, in doing so,
a place where every unresolved cross-commons claim is visible on a page rather than only
in a lane's output.

---

## Fashion Cabinet

FC is where the capability drift lives, because its manifest schema types the block as
`additionalProperties: {type: boolean}` — every key legal, none defined.

- [ ] **Add the dependency** (already required by P1b) and nothing else, first. Run
      `fc-spec vocab` in CI so the documents are exercised before anything depends on them.
- [ ] **Add check 6 to `scripts/qa/verify_compliance.py`: capability keys are vocabulary.**
      The check is small, and it is *reporting* before it is enforcing:

      ```python
      from hyperobjects_lexicon import canonical_key, load_vocabulary

      vocab = load_vocabulary("capabilities")
      known = {e["key"] for e in vocab["entries"]}
      aliases = {a["name"]: e["key"] for e in vocab["entries"] for a in e.get("aliases", [])}

      for slug, key in every_capability_key():
          if key in aliases:
              print(f"  note {slug}: '{key}' is a near-duplicate of "
                    f"'{canonical_key(key)}' — rewrite it")
          elif key not in known:
              print(f"  FAIL {slug}: '{key}' is not in the capability vocabulary")
      ```

      An unknown key is a **failure** on day one: the vocabulary contains every key that
      exists today, so the only way to hit it is to invent a new one — which is a
      decision that deserves a vocabulary entry rather than a silent commit. An alias is
      a **note** until the rewrite below lands, then it becomes a failure too.
- [ ] **Rewrite the eight alias spellings.** They touch about twenty cartridges:

      | rewrite | to | cartridges |
      |---|---|---|
      | `negative_ease_knit` | `knit_negative_ease` | 12 |
      | `hardware_reference` | `hardware_bridge` | 1 |
      | `tailored` | `tailoring` | 1 |
      | `one_handed_dressing`, `one_handed_clip` | `one_handed_operation` | 2 |
      | `uncut` | `uncut_cloth` | 1 |
      | `insulated_quilting` | `quilted_insulation` | 1 |
      | `princess_seamed` | `princess_seam` | 1 |

      **`swim-trunks` is not only a rename.** It declares `hardware_reference: true` and
      carries no `notion.hardware_ref` block at all, so it reads as bridged and is not.
      Fix the bridge or drop the claim; the rename alone would hide it.
- [ ] **Do NOT merge `hook_closure` into `hook_loop_closure`.** They look like a
      near-duplicate pair and are not: the first is hook-and-**eye** (13 bras, belts and
      the chaleco charro, bridging to `yantra4d/hook-and-eye`), the second is
      hook-and-**loop** (one hi-vis vest, bridging to `yantra4d/hook-loop-tape`). The
      vocabulary records them as `distinct_from` each other in both directions precisely
      so an automated de-duplication pass cannot do this.
- [ ] **Define the five keys nobody has defined.** `maru_corner`, `three_web`,
      `stabilised_island`, `full_fashioned_marking` and `seam_ease_shaping` carry
      `needs_definition: true` — used once each, and their meaning is not established
      from the evidence. Each is one sentence from whoever wrote the cartridge. Two of
      them (`maru_corner`, `three_web`) are a tradition's own words and the definition
      should come from the tradition, not from a guess.
- [ ] **Later, and only after the rewrite: tighten the schema.** With the aliases gone,
      `hyperobject.capabilities` can move from `additionalProperties: {type: boolean}` to
      a `propertyNames.enum` generated from the vocabulary. That is the point at which
      the drift stops being possible rather than merely being caught.

---

## Yantra4D

Y4D's interface types are already a schema enum, so its drift is smaller and different in
kind.

- [ ] **Reconcile the `geometry_type` enum with the catalog.** Three values are used in
      the commons and absent from `project-manifest.schema.json`'s eleven: **`flange`**
      (49 interfaces, and the type the whole cross-commons handshake keys on), **`boss`**
      (2) and **`fem_mesh`** (1). The catalog is ahead of its schema. Either add them or
      rule that the cartridges should be using an enumerated type — but the current state
      means a manifest that validates can still declare a type the schema does not know.
- [ ] **Pick one spelling for the two within-repo dialect splits.** `sew_face` (6
      cartridges) against `sew_plate` (3) is one region under two names, and `strap_slot`
      (4) against `webbing_slot` (4) is one passage under two. The vocabulary records the
      second of each as an alias of the first; that is a proposal, not a ruling.
- [ ] **Keep the cross-commons ids stable.** `tape_edge`, `panel_edge`, `sew_face`,
      `strap_slot` and `cord_channel` are the ids the soft side's bridges resolve
      against. Renaming one is a breaking change for the other commons, which is exactly
      the property the vocabulary exists to make visible.

---

## Both servers: the dictionary tools (§6.2)

The three tools are implemented here so that a definition cannot differ depending on
which half of the commons was asked. Registering them is a thin wrapper:

```python
from hyperobjects_lexicon.dictionary import define, lookup, related

@mcp.tool()
def define_term(term: str, lang: str | None = None) -> dict | None:
    """Define a commons term, an alias, or a manifest key, in es/en/fr/pt."""
    return define(term, lang)

@mcp.tool()
def lookup_object(slug: str) -> dict:
    """Every lexicon term a cartridge or material card embodies, with its constraints."""
    return lookup(slug)

@mcp.tool()
def related_terms(term_id: str) -> dict | None:
    """What a term points at, what points back, and the manifest keys that write it."""
    return related(term_id)
```

Two properties worth preserving in the wrapper:

* **Every answer carries `matched.route`** — `id`, `headword`, `alias`, `vocabulary_key`
  or `vocabulary_alias`. An agent that found a term through a fuzzy alias should be able
  to say so.
* **Every answer carries `review`** — `generated`, `reviewed` or `unmarked`. An LLM
  quoting a definition to a user is quoting text that, today, mostly no native speaker
  has read yet. Do not strip that field on the way out.

---

## Both catalogs: the article view (G2's other half)

The frontmatter contract is here; the surface is yours.

- [ ] **Put one `*.article.json` next to each article** you elevate — the natural home is
      beside the README it points at, e.g.
      `projects/chaleco-charro/docs/chaleco-charro.article.json`.
- [ ] **Start with the heritage set.** RFC 0039 §8 names heritage entries as G2's
      exemplar set for a reason: they are the entries that exercise every rule — the
      citation bar, the `excludes` bar, provenance with named custodians. FC has 33
      cartridges flagged `heritage: true` today.
- [ ] **Run the lane in CI**: `fc-spec article projects --catalog bundled`. It scans
      directories, so this stays one line as the corpus grows.
- [ ] **Render the view from the frontmatter, and the prose from the README.** Never copy
      the prose into the JSON — RFC 0039 §2's single-source rule is what stops the
      commons from acquiring a second corpus nobody keeps in step. The schema has no
      field to put it in, deliberately.
- [ ] **Wire `related.terms` to the term popovers.** That list is what an article's
      vocabulary resolves to, and the lane already guarantees every id in it exists.
- [ ] **Report the language coverage; do not gate on it.** `article_status` prints
      `titles: es=… en=… fr=… pt=…`. The lexicon is born quadrilingual because four
      languages are free at authoring time; the catalogs are en/es and phase **G-L** is
      the backfill.

---

## The review pass this work is waiting on

Everything in the G3 wave is marked `generated`, and that is a claim about who has read
it, not about who wrote it:

* **147 terms, 117 of them from the G3 waves** (110 from wave 1, 7 from the
  drawing-vocabulary wave), each quadrilingual and each
  `review_status: {state: generated}`. RFC 0039 §5 is explicit that machine or agent
  drafting is acceptable as a draft and never as shipped copy without a review pass, and
  §7 asks that fr/pt be *reviewed, not merely generated* — with es as the house register
  and the quality bar.
* **Both vocabularies** carry `review: {state: generated}`. Their counts are
  measurements; their canonicalisations are **proposals about meaning**. Every `aliases`
  entry asserts that two spellings make one claim, and every `distinct_from` asserts that
  two similar spellings do not. Those are rulings, and a maintainer should read them
  before the vocabulary is used to rewrite anything.
* **The exemplar article** carries the same flag, including a provenance note that
  deserves a reader who knows the tradition.

Marking a review is deliberately not free: `state: reviewed` requires at least one named
reviewer, and the state is the **worst** of the four language facets, never the best. A
reviewer who has read only the French marks `languages: {fr: reviewed}` and leaves the
entry's state alone. The lane refuses the shortcut.
