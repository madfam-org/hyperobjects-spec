# Vendored: the Pliego sheet-document and stock-card contracts

The two schemas in this directory are **vendored, byte-identical copies** of files the
Pliego platform publishes ([madfam-org/pliego](https://github.com/madfam-org/pliego)):

- `sheet-document.schema.json`: the JSON Schema of a *sheet document*. That is a FOLD 1.2
  file with `pliego:` extensions, the one artifact the Pliego kernel writes, the engine
  simulates, the exporters read and `pliego-spec check sheet-document` validates.
- `stock-card.schema.json`: the JSON Schema of a paper stock card
  (`materials/<slug>/stock.json`), checked by `pliego-spec check stock-card`.

<!-- markdownlint-disable MD013 -->

| Vendored here | Canonical source | Vendored at | Last changed in |
|:--|:--|:--|:--|
| `sheet-document.schema.json` | `packages/schemas/sheet-document.schema.json` | `pliego@2f85906` (main, kernel 0.3.0) | `f8d6677` (the `trace` finish, §5.30, pliego#23; before it `624b12f`, lane E's `keys`, `period`, `ride`, `active_from` and `release_joins`, §5.18–§5.20, pliego#18; and `ef377a0`, lane H's sheet `presentation`, §5.16, pliego#19) |
| `stock-card.schema.json` | `packages/schemas/stock-card.schema.json` | `pliego@2f85906` (main, kernel 0.3.0) | `944adcb` (the board `construction` block, `pliego.board`; pliego#8) |

<!-- markdownlint-enable MD013 -->

Do **not** hand-edit a vendored file. Change the canonical source in Pliego and
re-vendor. `pliego.lock.json` and this file are written by the keystone.

This is the third re-vendor. The first (`pliego@4b3fbfe`) predates madfam-org/pliego#8
(packaging) and #9 (papercraft print layout); the second (`pliego@6b6243a`) predates kernel
0.3.0, that is lane H's hardening (pliego#19: §5.13–§5.17, of which only §5.16
`presentation` touches the schema; art sources and split cuts are rules on fields that were
already there), lane E's engine wave (pliego#18: §5.18–§5.20) and lane X's trace finish
(pliego#23: §5.30). All are merged at `2f85906`, so nothing published is missing from this
copy. The stock card is unchanged since `6b6243a`; only its lock commit moves.
`last_changed` is the last commit that touched each file (`git log -1 <commit> -- <path>`).

## Lock and drift guard

- `tests/test_pliego_spec.py::test_vendored_pliego_contracts_match_their_lock` asserts
  each file's sha-256, size and git blob id equal `pliego.lock.json`. An edit here, or a
  re-vendor without a re-pin, turns the suite red.
- The reverse direction does not exist yet: Pliego's own CI would assert that the
  installed keystone's hash equals its live file, as yantra4d does for the graph
  engine. It belongs in Pliego's spec-conformance job once Pliego pins this package.

Re-vendor, for each file:

```bash
git -C <pliego> show <commit>:packages/schemas/<file> > src/pliego_spec/schemas/<file>
shasum -a 256 src/pliego_spec/schemas/<file>                 # -> lock "hashes"
git -C <pliego> rev-parse <commit>:packages/schemas/<file>   # -> lock "git_blob_sha1"
wc -c < src/pliego_spec/schemas/<file>                       # -> lock "bytes"
```

Record `<commit>` as the lock's `commit`, and the last commit that touched each file as
its `last_changed`. Do it in one commit, with no other change.

## Licence

The files are authored by Innovaciones MADFAM S.A.S. de C.V., the copyright holder of both
Pliego and this package. Pliego's platform code is AGPL-3.0-only. Vendoring it into this
Apache-2.0 package follows the existing precedent of the yantra4d graph contract
(`src/y4d_spec/graph/`) and the Fashion Cabinet manifest schemas, which are copies of files
from AGPL-3.0 platform repos by the same copyright holder.
