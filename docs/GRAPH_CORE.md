# The hyperobject graph core

> Package `hyperobject_graph` (core 1.0.1, graph format 1.2, script-node contract 1.0).
> Canonical here, in `src/hyperobject_graph/`; vendored by hash into each kernel.

Every hyperobject in the solid, soft and sheet commons is to have a **configurable graph**:
a `.graph.json` that declares every parameter a visitor can set, every preset, constraint
and interface, and that a kernel can render. One format serves all three commons. What
differs per commons is the **node vocabulary** — the solid kernel's 23 nodes, the soft
kernel's drafting nodes, the sheet kernel's fold nodes — and each kernel supplies its own
as a **node pack**. This document is the contract between the core and a pack, the
`script` node every pack can offer, and how a kernel vendors the core.

## 1. What the core is, and is not

The core is the kernel-neutral half: the document format, typed sockets, parameters and
derived values, the expression dialect, validation, declarations with i18n label keys,
licence and provenance, the node-pack interface and the `script` node. It is stdlib-only
and imports nothing outside its own directory, so a copy of the directory is the whole
dependency.

It knows no geometry. Literal value ranges, a revolve axis that must lie in its profile's
plane, a sheet that must fit its stock: those are a pack's, and its transpiler refuses them
in its own words.

```python
import hyperobject_graph as core

problems = core.validate(doc, pack, parameters=manifest["parameters"])  # [] when valid
plan = core.wrapper_plan(doc, pack)       # a pure wrapper: render plan.source
program = core.transpile(doc, pack, parameters=manifest["parameters"])  # a native graph
catalogue = core.export_catalogue(pack)   # the pack's vocabulary as JSON, for an editor
```

## 2. The format

A graph document is a JSON object. Format **1.0** is nodes and outputs; **1.1** adds
expressions; **1.2** adds the core fields and the `script` node. A 1.0 or 1.1 document
remains valid and is a solid graph (the only kind that existed); it may not carry 1.2
fields. The schema is `src/hyperobject_graph/graph-core.schema.json`; the enforcing
validator is `hyperobject_graph.validate`.

| Key | Since | Meaning |
| :-- | :-- | :-- |
| `version` | 1.0 | `1.x` |
| `units` | 1.0 | `mm` |
| `nodes` | 1.0 | `[{id, type, params, inputs, meta}]`; `inputs` maps a socket to a node id |
| `outputs` | 1.0 | part id → node id |
| `meta` | 1.0 | free-form; a node's `meta.label` is its i18n label |
| `parameters` | 1.1 | the expression scope: id → `{default, map?}` |
| `derived` | 1.1 | ordered `[{id, expr}]` |
| `kernel` | 1.2 | `solid`, `soft` or `sheet`; required in 1.2 |
| `declarations` | 1.2 | parameters, groups, presets, constraints, interfaces (§5) |
| `licence` | 1.2 | `{spdx, notice?}` |
| `provenance` | 1.2 | `{authored, generator?, sources: [{path, sha256, role}]}` |

### Validation

`validate(doc, pack)` returns every problem, each with a `code` and a JSON-pointer-like
`where`, so an editor can show them all at once:

| Code | Rule |
| :-- | :-- |
| `cycle` | the node graph is acyclic; an input may not reference its own node |
| `socket-type` | an input's socket type equals the referenced node's output type; an output's type is one the pack accepts as a part |
| `dangling-ref` | every input, output, binding and interface `node` names a node that exists, and every binding a param it has |
| `unbound-input` | every **required** input socket is connected (a pack may mark a socket optional) |
| `fan-out` | a socket type the pack limits (solid: a `profile` feeds one node) is not over-consumed |
| `expression` | every `{"expr"}` parses in the dialect, reads only declared names, and appears only where the param's kind takes one |
| `unread-declaration` | every `parameters`/`derived` name is read by some expression |
| `binding` | a `binding` targets a bindable param that does not also carry an expression |
| `identifier` | ids are plain identifiers that shadow none of the pack's reserved names |
| `script-node` | the script-node contract (§4) |
| `declarations`, `dead-parameter`, `i18n` | §5 |
| `licence`, `provenance` | §6 |
| `kernel`, `version`, `document`, `node`, `parameters`, `derived`, `units` | the document's shape |

The caps (500 nodes, 50 outputs, 128 parameters, 256 derived, 64 map entries) are the
solid engine's, so no document passes one validator and fails the other.

### The expression dialect

Unchanged from format 1.1, and the constraint dialect of every commons: numbers,
identifiers, `+ - * / %`, comparisons, `&& || !`, `?:`, parentheses; no strings, no calls;
at most 256 characters and 128 tokens. Values follow JavaScript (strict `==`, truncating
`%`, both sides of `&& || ?:` evaluated, division by zero an error). The core's parser is a
port of the solid engine's, held to it by a differential test over every formula in the
solid commons plus 2,500 generated ones (`tests/test_graph_core_expression.py`), and the
core adds an evaluator with the same semantics, so a kernel or a configurator computes a
value without a CAD kernel.

## 3. The node-pack interface

A kernel implements one object (`hyperobject_graph.NodePack`, a Protocol):

| Attribute | Meaning |
| :-- | :-- |
| `kernel`, `name`, `version` | which commons, a stable pack name, the vocabulary's version |
| `catalogue()` | node type → `NodeSpec(output, params: {name: ParamSpec(kind, default, bindable, expr)}, inputs: {socket: SocketSpec(type, required)})` |
| `param_kinds()` | kind → `ParamKind(bindable, expr, literal)` |
| `socket_types`, `output_types` | the socket types it speaks, and those a part may be |
| `fan_out` | socket type → most consumers |
| `reserved_identifiers` | names its emitted program defines |
| `script` | its `ScriptContract`, or `None` |
| `embedded_scripts` | whether `transpile` lowers a `script` node inside a native graph |
| `transpile(pack_doc, bindings, source_name)` | the kernel program for a validated document |

`catalogue_from_json` builds the catalogue from the JSON node catalogue a kernel already
publishes (Yantra4D's `graph-node-catalog.json` shape), so a kernel never describes its
nodes twice. `export_catalogue(pack)` gives an editor palette the vocabulary as neutral
JSON, the `script` node included.

The core hands `transpile` the document **with the core-only keys removed and nothing
else touched** (`pack_document`). For a 1.0/1.1 document that is the document itself.

The core's `dead-parameter` check sees only the graph: a script pass-through counts as
wiring there, because the core cannot read a source. **A kernel must also check that the
wrapped source reads each parameter**, or a wrapper that passes everything through hides
a dead control. The keystone does it for solid by holding the wrapped script to
G-DEADPARAM; the soft and sheet adapters must do the same with their own source readers.

### The solid pack

`y4d_spec.solid_pack.SOLID_PACK` is Yantra4D's graph engine behind this interface: the
catalogue is the engine's own generated catalogue, `transpile` is the engine's
`transpile`, sockets are `solid` and `profile` (a profile feeds one node), and the script
contract is CadQuery (`.py`, `.cq`) and OpenSCAD (`.scad`) yielding `solid`, with
`target_part` as the part parameter. Moving the engine behind the interface changed no
output: every graph in the solid commons validates with zero problems and transpiles
byte-identically to the engine called directly (`scripts/qa/check_graph_core_solid.py`,
`tests/test_graph_core_solid.py`; the fifteen program digests are pinned).

### The soft and sheet packs

Not built yet (RFC 0067 P3). Each implements the table above. The socket types RFC 0067
names are a starting point, not a commitment: soft `curve`, `piece`, `seam` (and the
measurements its drafting starts from); sheet `sheet`, crease pattern, fold sequence,
net. Each declares its script contract: the language its sandbox already runs for a
cartridge (Python on the `fc` drafting kernel; Python on the sheet kernel), the socket
type a script yields, and its part parameter.

## 4. The `script` node (contract 1.0)

RFC 0067 ruling G-1: a **wrapper graph** — one `script` node running the cartridge's own
source, with everything a visitor sees declared by the graph — counts as a configurable
graph now. Native nodes replace it later, by value, under the golden-twin rule. The same
node is the escape hatch inside a native graph.

```json
{ "id": "body", "type": "script",
  "params": {
    "source": "main.py",
    "language": "cadquery",
    "output": "solid",
    "bind": {
      "width": { "param": "width" },
      "half":  { "expr": "width / 2" },
      "style": "round"
    },
    "part": "lid"
  },
  "inputs": {} }
```

| Param | Required | Meaning |
| :-- | :-- | :-- |
| `source` | yes | a plain relative path inside the cartridge (no root, no `..`), carrying a suffix of `language` |
| `language` | yes | one of the pack's script languages |
| `output` | yes | one of the pack's script output socket types |
| `bind` | no | the source's parameter globals: `{"param": id}`, `{"expr": ...}`, or a literal (number, boolean, option value) |
| `part` | no | always render this part |

Semantics every kernel implements identically:

1. **Pass-through is exact.** `{"param": id}` hands the source the injected value with its
   type unchanged, and **absent stays absent**: when the render injects nothing for `id`,
   the global is not defined and the source's own fallback applies, exactly as when the
   source runs alone. This is what makes a wrapper render identically at the defaults
   (which inject nothing) and at every preset.
2. **Expressions and literals are always defined.** An `expr` reads the graph's
   `parameters`/`derived` scope with 1.1 semantics (injected value or declared default).
   They are for script nodes inside native graphs: a **wrapper** a kernel verifies as its
   script binds only pass-throughs, each under its own name, covering every parameter its
   mode lists (the keystone refuses anything else for a wrapper).
3. **The part.** Without `part`, the node passes the render's selected part through (the
   pack's `part_parameter`), so one node serves every output that names it, and it may
   feed only `outputs`. With `part`, it renders that part and may feed other nodes.
4. **The part parameter is the runner's.** A graph may declare it as a parameter (a part
   picker); it counts as wired, and a preset may set it whether or not it is declared.
5. **No capability is added.** The source runs in the kernel's existing render sandbox,
   behind its suffix gate, exactly as the cartridge's mode runs it. A binding may not
   name the part parameter or a name the runner defines for every source (solid: `cq`,
   `math`).
6. **Provenance.** Every script source is listed in `provenance.sources` with its sha256
   and role `script`. A kernel that can read the cartridge compares the digest
   (`source_digest_problems`), so an edit to the source without regenerating its graph is
   `source-drift`, not silence.
7. **Inputs are empty** in contract 1.0: the node takes parameters, not sockets.

**Lowering.** A *pure wrapper* (one script node, no `part`, every output naming it) is
not transpiled: `wrapper_plan(doc, pack)` returns the source, language, parts and
`script_params(injected)`, and the kernel renders the source on its own path with those
parameters. `transpile` refuses a pure wrapper (`code="wrapper"`). A script node inside a
native graph is lowered only by a pack with `embedded_scripts`; the solid pack does not
lower one yet (RFC 0067 P5), and the core refuses it before the engine sees an unknown
node type.

**How the keystone verifies a wrapper** (`y4d-spec check`):

- with no render: the core validates the 1.2 graph; every source digest matches; the
  declarations equal the manifest's entries of the same identity, and when every mode has
  a 1.2 graph every manifest entry is declared by one; the wrapper's source is its mode's
  script, it outputs every part the mode renders, and every part it outputs is rendered by
  some mode naming it; and it passes **every parameter its mode lists through under its
  own name and binds nothing else** — the shape under which it renders as its script at
  every parameter point, not only at the ones parity samples (`y4d_spec.graph_core_rules`).
  Failures from birth: no 1.2 graph existed before the core. A pass-through is not a
  G-DEADPARAM reference: a generated wrapper passes everything through, so the wrapped
  script's own reads decide whether a parameter is alive.
- with `--render --parity`: the wrapper renders its source with its script parameters,
  filed as `graph` with `wraps` naming the source's engine; the parity pass pairs it with
  that engine's render of the same target and requires the two STLs to be **identical byte
  for byte** — not within a tolerance, and not exemptable, because nothing differs but the
  route (`y4d_spec.parity.wrapper_identity`):

```
parity (block, block, preset 'big_block', cadquery vs graph): ok — wrapper identical —
  the graph's mesh is the script's, byte for byte (sha256 <first 12 hex>…)
```

The two fixtures `tests/fixtures/y4d/graph-wrapper` (CadQuery; a slider, a string select
and a boolean checkbox, two modes with a graph each) and `graph-wrapper-scad` (OpenSCAD;
one graph for two modes) are the reference shapes.

## 5. Declarations

```json
"declarations": {
  "parameters": [ ... ], "parameter_groups": [ ... ], "presets": [ ... ],
  "constraints": [ ... ], "interfaces": [ ... ]
}
```

Each entry has exactly the shape the commons' manifest gives it, so the manifest's lists
are a copy (`manifest_projection`) and a manifest that drifted from its graph is a plain
inequality. The core checks only what the graph's meaning depends on, and leaves value
ranges and widget details to the manifest's own checker:

- parameters: plain unique ids, a known `type` (`slider`, `checkbox`, `select`, `text`), a
  `default`, an i18n `label`, a `group` that is declared (when the graph declares groups),
  a `visible_when` that is a 1.1 expression over declared parameters; and every parameter **drives
  something** — a script pass-through, a `binding`, or the expression scope — unless it is
  `intentionally_unused` with a reason (`dead-parameter`);
- groups: an id, key or slug, and a label; presets: unique ids, a label, `values` naming
  declared parameters only; constraints: the expression parses in the dialect and reads
  declared parameters only, a valid severity; interfaces: unique ids, a label, declared
  `parameters`, and an optional `node` that exists;
- in a graph with declarations, every `parameters` (expression-scope) id is a declared
  parameter;
- a pure wrapper ignores `binding` in its declarations: it has no node to bind, and a
  binding there belongs to a native graph of the same cartridge (copied because the
  declarations equal the manifest's entries). A native graph resolves its own.

Other keys an entry carries (`unit`, `min`/`max`/`step`, `options`, `order`, `advanced`,
`widget`, `preview_hint`, `applies_to`, …) pass through untouched: they are the surface's
and the manifest's. Surface data that is not a manifest list today — sweeps, export
formats, a hero still — is not a declaration in format 1.2; adding it is an additive
minor of the core when the generated surfaces (RFC 0067 P2) need it.

**i18n.** A label is a plain string (English only) or `{"en", "es", "fr", "pt"}` with
`en` required (RFC 0039). `label_keys(doc)` gives every surface string a stable key —
`parameters.<id>.label|tooltip`, `parameters.<id>.options.<value>.label`,
`parameter_groups.<id>.label`, `presets.<id>.label`, `constraints.<n>.message`,
`interfaces.<id>.label`, `nodes.<id>.label` — and `i18n_gaps(doc)` lists the missing
`(key, locale)` pairs. A report, not a refusal: the surface checks of RFC 0067 §5 decide
what a gap costs.

## 6. Licence and provenance

`licence.spdx` is an SPDX expression (shape-checked; which ids a commons accepts is the
commons' rule). `provenance.authored` is `hand` or `generated`; a generated graph names its
`generator` `{name, version}`. `provenance.sources` lists `{path, sha256, role}` with role
`script` (a file a script node runs), `oracle` (a retired script kept as a parity oracle,
RFC 0067 G-5) or `reference`.

## 7. Vendoring the core

The core is canonical **here**. A kernel takes a copy, the way this repository takes a copy
of the solid engine from Yantra4D, with the same two-way drift guard:

1. Copy every file of `src/hyperobject_graph/` (the `.py` modules, `graph-core.schema.json`
   and `core.lock.json`) into one directory of the kernel's repo, unmodified. Keep the
   package name `hyperobject_graph`; it imports nothing outside itself.
2. **Guard the copy** (kernel side, blocking): every vendored file's sha256 equals
   `core.lock.json`, and the lock lists exactly the vendored files. An edit to the copy
   goes red.
3. **Guard the source** (kernel side, where the keystone is installed at the kernel's
   `SPEC_PIN`): the installed `hyperobject_graph/core.lock.json` hashes equal the
   vendored lock's. A core change here goes red there at the next re-pin until the copy is
   refreshed. A pin older than the core (no `hyperobject_graph` installed) stands down with
   one line, as `check_spec_graph_vendor.py` does for the engine.
4. Here, `scripts/qa/check_graph_core_lock.py` (blocking in CI) keeps `core.lock.json` the
   truth about the files beside it, and `CORE_VERSION`/`FORMAT_VERSION` in step with it.

Changing the core: edit, run `python scripts/qa/check_graph_core_lock.py --update` in the
same commit, bump `CORE_VERSION` when what a valid document is moves, and say in the PR
that the kernels must re-vendor. Re-vendoring does not move any `SPEC_PIN`; moving pins is
its own step.

Once a shared MADFAM Python registry exists, replace the copies with a plain dependency
and delete the guards, as `y4d_spec/graph/VENDORED.md` says for the engine.
