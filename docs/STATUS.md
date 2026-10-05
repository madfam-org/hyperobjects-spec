# hyperobjects-spec: status as of 2026-10-05

A dated snapshot for someone resuming from a fresh clone. **The
[open-PR list](https://github.com/madfam-org/hyperobjects-spec/pulls) is
authoritative**; when this file and GitHub disagree, GitHub wins. Operator
runbooks are kept privately. This package deploys nothing: consumers pin it by
full SHA and advance their own pins.

## Where it stands

- `main` is `20b636e7`: package **0.10.0**, `PROJECTION_VERSION` **3**.
- Consumer pins: solid-hyperobjects and soft-hyperobjects (`SPEC_PIN`) and
  yantra4d (`ci.yml` and `spec-nightly.yml`) are on `142db18`; asset-shells
  (`pyproject.toml`) is on `32cb58c`.

## Landed recently

| PR | What it did |
|---|---|
| [#45](https://github.com/madfam-org/hyperobjects-spec/pull/45) | ASM-1 §9 kinematics: joints, axis bindings, belt paths, the pose sweep (0.7.0, projection version 2) |
| [#46](https://github.com/madfam-org/hyperobjects-spec/pull/46) | Re-vendors the graph engine (graph format 1.1) |
| [#49](https://github.com/madfam-org/hyperobjects-spec/pull/49) | Stations on the mate: mate offset and interface travel (0.8.0) |
| [#50](https://github.com/madfam-org/hyperobjects-spec/pull/50) | `--collision`: rigid-body interference at every pose (ASM-1 §3.7, 0.9.0) |
| [#47](https://github.com/madfam-org/hyperobjects-spec/pull/47), [#48](https://github.com/madfam-org/hyperobjects-spec/pull/48), [#51](https://github.com/madfam-org/hyperobjects-spec/pull/51), [#52](https://github.com/madfam-org/hyperobjects-spec/pull/52), [#53](https://github.com/madfam-org/hyperobjects-spec/pull/53) | Standard parts for the 2.4-class motion system: gantry rail and blocks, A/B belt, idlers, Z drive and bed hardware, collision envelopes |
| [#54](https://github.com/madfam-org/hyperobjects-spec/pull/54) | The full 2.4-class motion system becomes fixture A and the pose golden |
| [#55](https://github.com/madfam-org/hyperobjects-spec/pull/55) | Projects from the canonical document (assemblies and material cards); `PROJECTION_VERSION` 3 (0.10.0) |
| [#56](https://github.com/madfam-org/hyperobjects-spec/pull/56) | Fixture A carries the ten graph twins |

## Open PRs, in merge order

None of them deploys; land one at a time.

| PR | Purpose | Precondition |
|---|---|---|
| [#57](https://github.com/madfam-org/hyperobjects-spec/pull/57) | Exports the compiled kinematic model for viewers (ASM-1 §9, 0.11.0) | CI green |
| [#58](https://github.com/madfam-org/hyperobjects-spec/pull/58) | The graph transpiler writes the source name as an escaped literal (re-vendor) | After #57. Expect a CHANGELOG and version conflict: keep both entries and bump the version once |
| [#59](https://github.com/madfam-org/hyperobjects-spec/pull/59) | Docs: commons topology, graph format 1.1, related contracts, and this status file | CI green; any order. Keep both CHANGELOG entries |
| [#12](https://github.com/madfam-org/hyperobjects-spec/pull/12) | `pyproject.toml` as the single version source | Older draft, gated; not part of this queue |

## Next steps

1. Merge #57, then #58.
2. **One pin bump in every consumer**, to the SHA that contains both:
   - solid-hyperobjects and soft-hyperobjects `SPEC_PIN`;
   - yantra4d `ci.yml` and `spec-nightly.yml`, in the same PR as the matching
     platform graph-engine change (the graph-vendor guard requires the
     vendored engine and the platform's engine to be byte-identical);
   - asset-shells `pyproject.toml` and its fixture-A digest.
   After it, yantra4d#230's forward-kinematics parity can go green.
3. Keep the ported `commons_sandbox` module in step with the platform's copy:
   a re-sync plus a drift guard.

## Cross-repo contracts

The README's [Related repositories and contracts](../README.md#related-repositories-and-contracts)
table links the consuming document in each repository. The contracts defined
here: [`docs/ASSEMBLIES.md`](ASSEMBLIES.md) (ASM-1, kinematics §9),
[`graph.schema.json`](../src/y4d_spec/graph/graph.schema.json) and
[`VENDORED.md`](../src/y4d_spec/graph/VENDORED.md) (graph format 1.x), and the
README sections *Generator output (GOC-1)* and *AAS projection (SEM-1)*.
