# Vendored: canonical licence texts (SPDX license-list-data)

Every file in `texts/` is a **byte-identical copy** of the plain-text licence in
[`spdx/license-list-data`](https://github.com/spdx/license-list-data), tag `v3.29.0`
(commit `31ba1a50e5397e00a304dbadc76531740e89ee48`), path `text/<SPDX-ID>.txt`. This
package does not author them.

`licenses.lock.json` records the source, tag, commit and, per file, the git blob id,
sha256 and size. `tests/test_license_body.py` asserts the vendored bytes still hash to
those values, so a hand-edit turns the suite red. Do **not** edit a text here: the
texts are the definition of "canonical" for the shipped-LICENSE body check, and a
local edit would silently redefine it. A spelling that legitimately differs from SPDX
belongs in `body.DOCUMENTED_VARIANTS`, with a test, not in the text.

## Which licences, and why

Derived read-only from the two commons at their `main` on 2026-10-10
(solid-hyperobjects `b299908`, soft-hyperobjects `c7edcd9`):

| SPDX id | Why it is here |
|:--|:--|
| `CERN-OHL-W-2.0` | every cartridge's `hyperobject.commons_license`, in both commons; the title of every shipped LICENSE |
| `CERN-OHL-S-2.0` | the body solid's root LICENSE and 12 cartridges shipped under a W title until solid-hyperobjects#177 |
| `CERN-OHL-P-2.0` | the third CERN-OHL v2 variant, so a P body is named rather than called "unknown" |
| `Apache-2.0`, `CC-BY-SA-4.0`, `CC-BY-NC-ND-4.0`, `GPL-2.0-only` | upstream licences solid manifests cite in attribution `license` fields (`GPL-2.0`, deprecated, resolves to `GPL-2.0-only`) |

To refresh, re-download each file at a newer license-list-data commit with
`gh api -H 'Accept: application/vnd.github.raw'
'repos/spdx/license-list-data/contents/text/<ID>.txt?ref=<commit>'`, update the lock
and re-run the whole-commons false-positive analysis before landing.

## Terms

Each text is reproduced unmodified and is governed by its own terms, not by this
package's Apache-2.0 licence. The CERN-OHL v2 texts say of themselves: "Anyone is
welcome to use it, in unmodified form only."
