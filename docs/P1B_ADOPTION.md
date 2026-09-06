# P1b: adopting `hyperobjects-spec` in the platform repos

This package is P1a — the commons bar, extracted and installable. **P1b is the platform
side**: making `fashion-cabinet` and `yantra4d` consume it instead of carrying their own
copies. This document is the checklist for that work.

Nothing here has been done. Both platform repos are untouched by the P1a work — the
package was built read-only against them.

The ordering principle throughout: **land the dependency before deleting the original.**
A step that removes a repo's own copy in the same commit that adds the dependency has no
way back if the package is wrong.

---

## Why adopt at all

Three concrete wins, in the order they pay off:

1. **`yantra4d` gets a bar it can't currently run.** Its per-cartridge rules are spread
   across four scripts, two of which import the API app (`sys.path.insert` into
   `apps/api`). A contributor cannot run them on a cartridge outside the repo, and the
   repo cannot run them without the app importable.
2. **The sandbox vendoring can retire.** `yantra4d` vendors `commons_sandbox` from
   `fashion-cabinet` under a sha256 lock (`scripts/qa/check_sandbox_sync.py`). Once both
   repos `pip install hyperobjects-spec`, the vendored copy, the lock file, the guard
   lane, and `VENDORED.md` all go away.
3. **A third party's "it passes" and CI's "it passes" become the same sentence.** That
   is the actual precondition for outside contribution.

---

## Fashion Cabinet

FC is the easier side: its `fc_spec` and `commons_sandbox` were **ported verbatim** —
same module names, same public APIs, same CLI, same schema-loading path. Imports of
`fc_spec.rules` and invocations of `fc-spec check <contract> <file>` keep working
unchanged.

- [ ] **Add the dependency.** `pip install hyperobjects-spec` wherever
      `packages/spec` and `packages/commons-sandbox` are installed today (CI setup steps,
      dev bootstrap, any `pip install -e packages/...` line).
- [ ] **Verify the lanes still pass with the package installed and the local packages
      NOT installed.** In particular `scripts/qa/verify_hardware_links.py`, which imports
      `fc_spec.rules.hardware_ref_rules`. This is the real test of the port; do it before
      deleting anything.
- [ ] **Keep `packages/spec/tests/test_conformance.py` in FC.** Two of its guards protect
      files that live in FC and cannot travel:
      - bundled schemas vs `packages/schemas/` byte-equality,
      - `verify_hardware_links.py` still importing `fc_spec.rules` rather than forking it.
      Re-point them at the *installed* `fc_spec` instead of the local `packages/spec`.
- [ ] **Decide the schema source of truth.** FC's `packages/schemas/` currently feeds the
      bundled copy inside `fc_spec`. `hyperobjects_schemas` now carries a third copy. Pick
      one direction — most likely FC stays canonical and this package syncs from it — and
      add a drift lane on the FC side asserting it. Do not leave three copies with no
      stated direction.
- [ ] **Then, and only then, delete `packages/spec/` and `packages/commons-sandbox/`**,
      and drop their `pip install -e` lines.
- [ ] **Note the license boundary.** This package is Apache-2.0; the FC packages were
      AGPL-3.0. Confirm that relicensing the extracted tooling is intended and recorded
      (RFC 0038 §9 says the commons tooling is permissive on purpose) before the delete
      lands, because the delete is what makes Apache the only copy.

---

## Yantra4D

Y4D is the larger side: it has **no package twin** — `y4d_spec` was authored fresh from
its scripts. Nothing imports it yet, so adoption is additive first.

- [ ] **Add the dependency** to the API image and the CI setup.
- [ ] **Add a lane that runs `y4d-spec check` over `projects/*/`.** Start it
      **non-blocking**: on the commons as it stands today, 32 of 417 cartridges fail (see
      "Known failures" below). Blocking on day one would either wedge CI or pressure
      someone into weakening rules that are correct.
- [ ] **Work the 32 down, then flip the lane to blocking.** Each category is a real
      defect class, not noise — the calibration pass removed everything that was not.
- [ ] **Retire the sandbox vendoring** once the dependency is in the image:
      delete `packages/commons-sandbox/` (the vendored copy, `sandbox.lock.json`,
      `VENDORED.md`) and `scripts/qa/check_sandbox_sync.py`, then re-point
      `apps/api/services/engine/cq_runner.py`'s import at the installed package. Its
      import line does not change (`from commons_sandbox import ...`) — only where the
      module comes from.
- [ ] **Reconcile the duplicated per-cartridge rules.** These now exist twice, in the
      repo scripts and in `y4d_spec`. Either delete the repo half and call `y4d_spec`, or
      keep both and add a drift guard. Two copies with neither is how they diverge:
      - `scripts/qa/validate_manifests.py` → schema validation
      - `scripts/audit_compliance.py` rules 1, 2, 3, 5
      - `scripts/qa/compliance_audit.py` checks 1–4
      - `apps/api/manifest.py::_validate_manifest_strictness`
      - the declared half of `scripts/qa/check_licenses.py`
- [ ] **Keep the repo-wide lanes exactly where they are.** They are out of scope for this
      package by design: `generate_commons_catalog.py` (catalog drift), cross-cartridge
      slug uniqueness in `discover_projects`, and the *shipped-file* half of
      `check_licenses.py`'s nested-license scan.
- [ ] **Retire `tests/scripts/geometric_regression.py` in favour of `--parity`.** This one
      came OFF the list above: whether one cartridge's two kernels model the same solid is
      a property of that cartridge, so it belongs on the merge path rather than in a
      repo-wide sweep. `y4d-spec check --render --parity` mirrors
      `scripts/qa/verify_parity.py` gate for gate and with the platform's own numbers
      (0.001mm AABB, the 2% volume allowance, the 0.05mm faceting band), so the two cannot
      disagree about what "agree" means. Point the platform at the package or add a drift
      guard — two copies with neither is how they diverge, exactly as for the rules above.
      Note the two things the platform's sweep did NOT have: the 0.05mm **faceting warn**
      tier (G27) and the **placement/shape split** (G39), so expect pairs the old lane
      called clean to surface as placement notes, and pairs it passed as `identical within
      65mm` to fail on shape. Per-part exemptions
      (`verification…checks.parity`, `mode_overrides.<mode>.part_overrides.<part>
      ["geometry.parity"]`) are the escape hatch, and each needs a non-empty `reason`.
- [ ] **Decide on `--render` in CI.** It is the strongest check and the slowest: roughly
      15–25s per part on the reference machine, and since 0.2.0 it renders **every
      declared preset as well as the defaults** — the commons averages ~3 presets per
      cartridge, so the job is several times longer than the 0.1.x figure. Suggest
      running it on changed cartridges per-PR and the full sweep nightly.
      `--no-presets` restores roughly the 0.1.x cost and is strictly weaker; do not
      reach for it on the nightly lane, which is where the preset matrix pays. The
      printability notes (`--no-printability` to skip) add well under a second per
      render and never change the exit code, so they are safe to leave on everywhere.
      Two flags belong on the same line once the runner image carries OpenSCAD:
      `--require-openscad`, without which a lane that rendered no OpenSCAD target still
      reports green, and `--parity`, which is what makes "both kernels agree" a property
      of the merge path. The runner's OpenSCAD must match `y4d-spec render-env
      --openscad-version` — read it from there rather than pinning a fourth copy.
- [ ] **Give the runner what the CAD kernel needs, and prove it ran.** `--render` needs
      the `[geometry]` extra (cadquery, trimesh, scipy, networkx and **rtree**, which is
      what trimesh builds its ray bounds tree with) *and* the system libraries OCP's C
      extension links against — on Debian/Ubuntu `libgl1`, `libglib2.0-0` and
      `libxrender1`. `libgl1` alone leaves `libXrender.so.1` unresolved, `import cadquery`
      fails, and the entire render lane becomes unavailable. This repo's own CI learned
      that the expensive way: its geometry tests skipped on every run on main while the
      job reported green. So assert `y4d_spec.geometry.geometry_available()` in the job
      and **fail on False** rather than trusting a summary line nobody reads.
- [ ] **Decide where the printability notes go.** They are notes by construction in
      0.2.0 and every threshold is provisional (see the calibration stories in
      `printability.py`). A measurement that could not run because a package is missing
      is not silence either: it raises a once-per-process `PrintabilityDependencyWarning`
      naming the package, so a surface that swallows warnings will hide the difference
      between "no thin walls" and "nothing measured them". Before any of them is allowed
      to block, the full-commons false-positive analysis has to be written down — the
      same bar that killed the `render_mode` uniqueness rule. The overhang rule in
      particular counts a part's flat bed-contact face as overhang, which is why it is
      an area *fraction* and why it stays a note.

---

## Shared decisions to make before either side deletes anything

- [ ] **Distribution.** These install instructions use a git URL and a branch ref —
      no release tag exists for the current version, so `@main` is what resolves. If
      `hyperobjects-spec` goes to a registry (PyPI or the MADFAM registry), update the
      README, both repos' dependency pins, and the CI setup steps together.
- [ ] **Versioning policy.** Downstream CI will pin this package. Decide what a minor
      bump is allowed to do — specifically, whether *adding a rule* (which can turn a
      green repo red) is minor or major. Recommend: new rules are a minor bump, announced
      in the changelog, and land non-blocking first.
- [ ] **Where the identity records live.** The schema and the checker are here; the
      records themselves are not. Decide whether pair files live in one repo, both, or a
      third location — and add the platform-side lane that checks the slugs actually
      resolve, which this package deliberately does not do.

---

## Known failures on the Yantra4D commons today

From `y4d-spec check projects/*/` at v0.1.0 — 417 cartridges, 32 failing, 63 notes.
Every category was hand-verified against the cartridge source before the rule shipped.

| Count | Category | Notes |
|---|---|---|
| 20 | single-part CadQuery mode id ≠ its part id | Real. `hook-and-eye/main.py` branches on `target_part == "hook"` while its manifest maps mode `hook` to part `hook_plate`, so the platform renders the fallback body. |
| 14 | directories with no `project.json` | Docs/PDF folders under `projects/`. Either move them or accept the finding. |
| 10 | part listed by no mode | Unreachable parts, mostly `rubiks-hyperobject` and `locking-mechanism-hyperobject`. |
| 17 | missing `es` translations | Bare-string or English-only labels in an es-first commons. |
| 7 | mode identified by `slug`, no `id` | Only `rugged-box`. Schema-valid, but `manifest.py`'s accessors read `mode["id"]`, so those modes cannot be selected. |

The 63 notes are all one class: cartridges including the repo's shared `libs/` tree.
Correct in-repo, not portable — informational only, never blocking.

---

## Behavior interpreted rather than copied

Flagged so a reviewer can overrule any of these deliberately. Each is a place where the
platform's behavior did not translate directly.

1. **Manifest strictness is enforced at `strict`.** `_validate_manifest_strictness`
   defaults to `MANIFEST_STRICTNESS=warn`, where it *patches* the manifest in memory
   (`thumbnail` → `/logo.png`, `tags` → `[]`, `difficulty` → `beginner`) and serves it.
   A spec runner has no app to keep serving, so it reports what the strict path raises. A
   cartridge that only passes because the platform patched it is not conformant.
2. **`attribution` is checked generally, not by allowlist.** `audit_compliance.py` requires
   an attribution block only for `{gridfinity, stemfie, multiboard}` — a repo-specific
   list that cannot travel. Ported as the rule behind it: a cartridge declaring
   attribution must name a source.
3. **A missing LICENSE file is silent; a contradicting one is not.** In-repo, only
   submodule-published cartridges need their own LICENSE (`check_licenses.py`'s
   `submodule_slugs()`), and this package cannot know which those are.
4. **Escapes into `libs/` are notes, not failures.** `audit_compliance.py:61` exempts them.
   Failing them would make this runner stricter than the platform it mirrors.
5. **`{en, es}` completeness is enforced on manifest strings.** `i18n_audit.py` holds the
   *studio locale files* at en/es parity; the schema's `i18nString` only requires `en`.
   Applying the same bar to cartridge strings is an extension — it is the largest single
   source of findings, so it is the most likely one to want relaxed to a note.
6. **`--render` supplies `{}` plus `target_part` — and then every preset's `values`.**
   No code path in the API sets `target_part` explicitly — cartridges read it via the
   `PARAM` idiom, `graph_engine.py` emits it, and `cq_runner.py` injects the whole params
   dict as bare globals. Empty params exercise each cartridge's own defaults rather than a
   set this checker invented. Since 0.2.0 the same contract is replayed at each declared
   preset (preset `values` merged under `target_part`), because the defaults render is
   evidence about *one* parameter point and presets are the ones the UI ships buttons for.
   Presets that declare no `mode` — 164 of the commons' 1219, including every preset of
   `extrusion-hyperobject` — are scoped from `parameters[].modes` /
   `visible_in_modes` rather than skipped or guessed; see `rules.preset_targets`.
7. **The renderer exports STL and raises instead of `sys.exit(1)`.** `cq_runner` exits
   because it is a subprocess; a library must not. STL because that is what the mesh
   checks need.
8. **`trimesh.load(process=False)`.** trimesh's default load pipeline *repairs* the mesh —
   it would silently fill the exact hole the watertight check looks for. The merge step is
   done explicitly instead, mirroring `mesh_integrity.assess`.
9. **`render_mode` uniqueness is NOT checked.** It looks like the OpenSCAD counterpart of
   the `target_part` rule, but `get_mode_map` defaults it to `0`, so parts legitimately
   share it when modes dispatch by source file (`projects/gears`). Enforcing it flagged 29
   healthy cartridges; the rule was dropped and the reason recorded in `rules.py`.
