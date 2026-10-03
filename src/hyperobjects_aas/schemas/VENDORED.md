# Vendored: the AAS v3.1 JSON Schema (IDTA-01001-3-1)

`aas.json` in this directory is a **byte-identical copy** of the official JSON
Schema of the Asset Administration Shell metamodel, Part 1, version 3.1.2. This
package does not author it.

<!-- markdownlint-disable MD013 -->

| Vendored here | Canonical source |
|:--|:--|
| `aas.json` | `admin-shell-io/aas-specs-metamodel`, tag `v3.1.2` (commit `a93e41c07c4018e864cba6016b760b9c7e0d849f`), `schemas/json/aas.json` |
| `LICENSE-CC-BY-4.0.txt` | the same repository and tag, `LICENSE.txt` |

<!-- markdownlint-enable MD013 -->

`aas.lock.json` records the source, tag, commit, git blob id, sha256 and size.
`tests/test_aas_check.py` asserts the vendored bytes still hash to that sha256, so a
hand-edit turns the suite red. Do **not** edit `aas.json` here. To move to a newer
metamodel release, replace the file from the new tag, update `aas.lock.json`, and
re-run the fleet gate (`hyperobjects_aas` targets v3.1.2, see SEM-1 §0).

## Attribution (CC-BY-4.0)

- **Title:** AAS JSON Schema (`IDTA-01001-3-1 AAS JSON Schema`,
  `$id: https://admin-shell.io/aas/3/1`)
- **Author:** Industrial Digital Twin Association (IDTA) and the contributors to
  `admin-shell-io/aas-specs-metamodel`
- **Source:** <https://github.com/admin-shell-io/aas-specs-metamodel/blob/v3.1.2/schemas/json/aas.json>
- **Licence:** Creative Commons Attribution 4.0 International
  (<https://creativecommons.org/licenses/by/4.0/>). The full licence text ships beside
  the file as `LICENSE-CC-BY-4.0.txt`.
- **Changes:** none. The file is copied unmodified.

This file is licensed under CC-BY-4.0, not under this package's Apache-2.0 licence.
Everything else in `hyperobjects_aas` is authored here and is Apache-2.0.

## Validating with Python `jsonschema`: UTF-16 patterns

The schema spells the XML `Char` production over UTF-16 code units
(`\ud800[\udc00-\udfff]` and so on), the way an ECMAScript engine sees a string. Python
holds a character outside the Basic Multilingual Plane (an emoji, for example) as one
code point, which matches none of those alternatives, so plain `jsonschema` would reject
valid AAS text. The fleet gate found `🤚` in a solid cartridge's preset label, and BaSyx
accepts it. `hyperobjects_aas.check` therefore evaluates **only the `pattern` keyword**
against the string's UTF-16 code units. `maxLength` still counts code points, as JSON
Schema defines. The file itself is unchanged.

## IDTA submodel templates

The IDTA submodel templates are **not** vendored. `hyperobjects_aas.templates` copies
only their identifiers (submodel and element semanticIds) and the list of elements each
template marks mandatory, and records the source path of every identifier. The templates
are published by the IDTA under CC-BY-4.0 at
<https://github.com/admin-shell-io/submodel-templates>.
