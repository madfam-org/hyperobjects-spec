# Vendored: the Pliego sheet-document contract

`sheet-document.schema.json` in this directory is a **vendored, byte-identical copy**
of the Pliego platform's `packages/schemas/sheet-document.schema.json` — the JSON
Schema of a *sheet document* (a FOLD 1.2 file with `pliego:` extensions: the one
artifact the Pliego kernel writes, the engine simulates, the exporters read and
`pliego-spec check sheet-document` validates).

<!-- markdownlint-disable MD013 -->

| Vendored here | Canonical source | Source commit |
|:--|:--|:--|
| `sheet-document.schema.json` | Pliego `packages/schemas/sheet-document.schema.json` | `pliego@e99db11` (local; not yet on GitHub) |

<!-- markdownlint-enable MD013 -->

Do **not** hand-edit the vendored file. Change the canonical source in Pliego and
re-vendor. `sheet-document.lock.json` and this file are keystone-authored.

## The source is not published yet — re-pin when it is

Pliego is not on GitHub yet, so the recorded commit (`e99db11`, "feat(spec):
translate mechanism and driven pins", the last commit to touch the file) is a commit
of a local repository that nobody else can fetch. That is recorded on purpose
(`"published": false` in the lock) rather than dressed up as a URL. **When Pliego is
published, re-vendor from the published repository, record its commit, set
`"published": true`, and re-pin the hash** — in one commit, with no other change.

## Lock and drift guard

- `tests/test_pliego_spec.py::test_vendored_sheet_document_matches_its_lock` asserts the
  file's sha256 and size equal `sheet-document.lock.json`. An edit here, or a
  re-vendor without a re-pin, turns the suite red.
- The reverse direction (Pliego's own CI asserting the installed keystone's hash
  equals its live file, as yantra4d does for the graph engine) does not exist yet;
  it belongs in Pliego's spec-conformance job once Pliego pins this package.

Re-vendor:

```bash
git -C <pliego> show <commit>:packages/schemas/sheet-document.schema.json \
  > src/pliego_spec/schemas/sheet-document.schema.json
shasum -a 256 src/pliego_spec/schemas/sheet-document.schema.json   # -> lock "hashes"
git -C <pliego> rev-parse <commit>:packages/schemas/sheet-document.schema.json  # -> "git_blob_sha1"
```

## Licence

The file is authored by Innovaciones MADFAM S.A.S. de C.V., the copyright holder of
both Pliego and this package. Pliego's platform code is AGPL-3.0-only; vendoring it
into this Apache-2.0 package follows the existing precedent of the yantra4d graph
contract (`src/y4d_spec/graph/`) and the Fashion Cabinet manifest schemas, which are
copies of files from AGPL-3.0 platform repos by the same copyright holder.

## Not vendored

The stock-card schema (`packages/schemas/stock-card.schema.json`, specified in
Pliego's `docs/spec/v1/stock-card.md`) does not exist yet. It is vendored the same
way, with its own lock entry, when it does.
