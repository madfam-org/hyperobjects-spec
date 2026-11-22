# The device-control vocabulary

> `device-controls/1.0`. Schema: `device-controls.schema.json` (`hyperobjects_schemas`).
> Rules: `y4d_spec.device`. Input names: `src/y4d_spec/device/input-codes.json`.

Some solid cartridges model a device a person operates: a handheld, a remote, a control
panel. Such a cartridge already splits the device into named parts. This vocabulary lets it
say **which part is a control and what the control sends**, in a `device` block of its
`project.json`. Two kinds of program read the block:

- a **viewer** lights a control when a visitor points at it, moves it by its travel when it
  is pressed, lists the controls beside the model, and draws a picture on a screen part;
- an **input bridge** turns a press on the model into the input event the real device's
  driver would send, so the software that runs on the device can run against the model.

The block declares. It draws nothing and runs nothing: the geometry stays in the
cartridge's source, and the behaviour stays in the programs that read the block.

## 1. The block

```json
"device": {
  "vocabulary": "device-controls/1.0",
  "structure": ["body"],
  "controls": [
    { "part": "button_south", "role": "button",
      "label": { "en": "South face button", "es": "Botón frontal sur" },
      "code": "BTN_SOUTH",
      "travel": { "axis": "-z", "depth": { "expr": "button_travel" } },
      "parameters": ["button_height", "button_travel"] },
    { "part": "stick_left", "role": "stick",
      "axes": { "x": "ABS_X", "y": "ABS_Y" }, "click": "BTN_THUMBL",
      "travel": { "axis": "-z", "depth": 0.6, "tilt": { "expr": "stick_tilt" } },
      "present_when": "stick_count >= 1" },
    { "part": "screen", "role": "screen",
      "pixels": [640, 480], "surface": { "normal": "+z", "up": "+y" } }
  ]
}
```

| Key | Meaning |
| :-- | :-- |
| `vocabulary` | `device-controls/1.<minor>`. A keystone that knows an earlier minor checks what it knows and says so in a note. |
| `structure` | The parts that are not controls: a body, a trim, a mount. |
| `controls` | One entry per control part. |

**Every part of the cartridge is in exactly one of the two lists.** A viewer never has to
guess whether a part can be pressed.

### Fields every control has

| Field | Required | Meaning |
| :-- | :-- | :-- |
| `part` | yes | The part's id, as in `parts[]` and in the graph's `outputs`. |
| `role` | yes | One of the eight roles below. |
| `label` | no | A display string. In the solid commons it carries `en` and `es`, like every other surface string. |
| `present_when` | no | An expression over the cartridge's parameters. The control exists on the device where it is true. Absent means always. |
| `parameters` | no | The parameters that size or place the control. |

### Roles

| Role | Required | Optional | What it declares |
| :-- | :-- | :-- | :-- |
| `button` | `code`, `travel.axis`, `travel.depth` | | A key: `code` is an `EV_KEY` name. For a button the driver reports as one direction of an axis (a hat switch), `code` is `{"axis": "ABS_HAT0Y", "value": -1}`. |
| `stick` | `axes.x`, `axes.y`, `travel.axis`, `travel.tilt` | `click`, `travel.depth` | Two `EV_ABS` axes. `tilt` is the largest tilt from rest, in degrees. `click` is the `EV_KEY` name of a press on the stick, and `depth` how far that press goes along `axis`. |
| `trigger` | `code` or `axis` (or both), `travel.axis`, `travel.depth` | | `code` is an `EV_KEY` name, `axis` an `EV_ABS` name for an analogue pull. Many pads send both. |
| `switch` | `code`, `positions`, `travel.axis`, `travel.depth` | | `code` is an `EV_SW` name, or an `EV_KEY` name for a switch the driver reports as a key. `positions` is 2 to 8. `depth` is the throw from the first position to the last. |
| `screen` | `pixels`, `surface.normal`, `surface.up` | `touch` | `pixels` is `[across, down]`. The picture is drawn on the part's outermost face along `normal`, with `up` at the top. |
| `light` | `colours` | | `"rgb"` for any colour, or a list of the `#rrggbb` colours it can show. |
| `port` | `connector` | | `usb-c`, `usb-a`, `usb-micro-b`, `audio-3.5mm`, `card-microsd`, `card-sd`, `video-hdmi`, `video-hdmi-mini`, `video-hdmi-micro`, `power-barrel`, `contacts`, `other`. |
| `motor` | `effect` | | `rumble`. |

A role takes only its own fields: a `code` on a light is a schema failure.

An **axis** is `+x`, `-x`, `+y`, `-y`, `+z` or `-z` in the cartridge's model frame, the frame
its parts are rendered in. `travel.axis` is the way the part moves when it is pressed or
thrown. `travel.depth` is in millimetres.

A **number** is a number or `{"expr": "..."}`, an expression over the cartridge's
parameters. `travel.depth`, `travel.tilt` and each of `pixels` take one.

### Input names

A control names what it sends by its **Linux input event name**: `BTN_SOUTH`, `KEY_POWER`,
`ABS_X`, `SW_LID`. The event type follows from the name (`KEY_` and `BTN_` are `EV_KEY`,
`ABS_` is `EV_ABS`, `SW_` is `EV_SW`). The keystone carries the names and their numbers in
`input-codes.json`, generated from the kernel's user-space header
`include/uapi/linux/input-event-codes.h` by `scripts/refresh_device_input_codes.py`; the
table records the kernel tag and the header's sha256. `y4d_spec.device.input_codes()`
returns it.

**A name the table lacks is a failure.** A misspelt code is a control that sends nothing,
and nothing downstream would say so. A name a newer kernel added is taken up by refreshing
the table here, the same way an interface size key is added here before a cartridge uses it.

Which name a button sends is the device's choice. The names say what the driver reports,
not what is printed on the cap.

## 2. Tied to the graph (RFC 0067)

RFC 0067 gives every hyperobject a configurable graph (`docs/GRAPH_CORE.md`). The
declaration is written against it in three ways:

1. **A control is an output.** A graph's `outputs` map part ids to nodes. Every mode that
   lists a control names a graph (a `graph_file` beside its script, or a graph source), and
   that graph outputs the control's part.
2. **Expressions are the core's.** `present_when` and every `{"expr"}` are in the graph
   core's expression dialect (`docs/GRAPH_CORE.md` › "The expression dialect"), parsed and
   evaluated by `hyperobject_graph`. They read the cartridge's parameters whose default is
   a number or a boolean; the dialect has no strings, so a `select` cannot be read. A
   viewer that has the core has everything it needs to compute a control's presence and
   numbers at the visitor's parameters.
3. **A 1.2 graph declares what the declaration reads.** Where the mode's graph carries
   `declarations`, every parameter an expression reads or `parameters` lists is one of the
   graph's declared parameters.

The block itself lives in the manifest in 1.0. `docs/GRAPH_CORE.md` §5 says that surface
data which is not a manifest list is not a declaration in graph format 1.2, and that adding
one is an additive minor of the core. Moving the block into a graph's `declarations` is that
step. It changes the core every kernel vendors, so it is left for a ruling; nothing here
depends on it.

## 3. Absent controls

A device family differs in which controls it has, and the solid runner has no notion of a
part that is absent: it renders every part a mode lists, at the mode's defaults and at each
of its presets, and an empty mesh is a failure. So:

- **A mode lists the controls its layout has.** A cartridge with a layout parameter
  (a stick count) gives each layout it ships a mode, and each preset names its mode.
- **`present_when` states where a control exists.** A mode that lists a control at a
  parameter point where the declaration says it is absent is a failure. A mode may list
  fewer controls than are present: a mode of one part is still a mode.
- A viewer that reads the block can hide a control whose `present_when` is false at the
  visitor's parameters, whatever the mode lists.

A cartridge is free in how its source treats a switched-off control. The reference
cartridge returns the part where it would sit, so a render never fails on a slider.

## 4. What `y4d-spec check` verifies

Nothing runs on a manifest without a `device` block. With one, three passes run, and each
holds the declaration to something the cartridge has. A finding is prefixed
`device-controls:`.

**With no render** (seconds, no CAD kernel), from the manifest:

| Failure | Rule |
| :-- | :-- |
| schema | the block's shape, including a role's required fields and no field of another role |
| not a part | a control or a structure entry names no entry of `parts[]` |
| declared twice | one part has two entries |
| unaccounted part | a part is neither a control nor structure |
| rendered by no mode | a control no mode lists |
| input name | a name the table lacks, or one of the wrong event type for its field; a stick whose two axes are one |
| label | a label without `en` or `es` |
| expression | does not parse, or reads a name that is not a declared number or boolean parameter |
| `parameters` | names a parameter the manifest does not declare |
| screen surface | `normal` and `up` on one axis |
| absent where listed | at a mode's defaults, or at a preset in its mode, a control the mode lists has a false `present_when` |
| number | at one of those points, `travel.depth` is not above 0, `travel.tilt` is not between 0 and 90, a pixel count is not a whole number of 1 or more, or an expression divides by zero |

and from the cartridge directory:

| Failure | Rule |
| :-- | :-- |
| no graph | a mode lists a control and names no graph |
| not an output | the mode's graph does not output a control the mode lists |
| undeclared parameter | a 1.2 graph's declarations lack a parameter the control reads |

A graph the render lane or the graph core refuses is theirs to report, once.

**With `--render`**, one verdict per (control a mode lists, rendered point, engine), against
the mesh the cartridge produced. `bounds` on a render is the mesh's bounding box in the
model frame:

| Failure | Rule |
| :-- | :-- |
| detached | the control's bounding box is more than 1 mm from every structure part's |
| travel points out | for a button, a trigger or a stick, `travel.axis` points away from the structure; a press moves a control in |
| screen face | `surface.normal` is not the screen part's thin direction |

A control whose render failed or was skipped is **unverified**: a note, never a pass. The
failed render is already a failure. A control the declaration calls absent at a point is
not judged there.

The summary line gains a clause when a declaration was checked against renders:

```
device=P/M ok, unverified=U, failures=F
```

`P + U + F = M`. A run without `--render` prints no `device=` clause.

**Notes**, which never fail a run: two controls a mode shows that send one code; pixels
that are not square on the rendered face (pitches more than 2 % apart); a press deeper than
the part is long along its travel; a control that renders as more than one body; a
declaration written in a later minor.

Every failure here is a failure from birth. No cartridge carried a `device` block before
the vocabulary, so there was no healthy cartridge for a rule to misfire on (the same
footing as the sheet commons' rules and the 1.2 graph's). The observations that can be
true of a healthy device are the notes.

## 5. For a program that reads the block

```python
from y4d_spec.device import resolve

for control in resolve(manifest, values):   # values: a preset's, or the visitor's
    control["present"]                      # is it on the device at these parameters
    control["travel"]["depth"]              # numbers computed
```

`resolve` returns each control with `present` added and every `{"expr"}` replaced by its
value at the given parameters. A program that cannot run Python does the same with the
graph core it already vendors: parse with `parse_expression`, evaluate with `evaluate`
over the parameter defaults overlaid with the current values, numbers as floats.

## 6. Versioning

`device-controls/1.x` is additive: a new role, a new connector, a new optional field. A
change to what an existing field means is 2.0. A cartridge states the version it was
written in; a keystone checks every 1.x declaration as far as the minor it knows.

Refreshing `input-codes.json` to a newer kernel tag only adds names (the kernel does not
renumber input events) and is not a vocabulary change.

## 7. The reference cartridge

`tests/fixtures/device/candybar-handheld` is a copy of the solid commons' generic handheld:
thirty-one controls in seven of the eight roles (it has no motor), layout parameters with
`present_when`, two modes, two presets and a wrapper graph. It passes all three passes, and
the tests break a copy of it to show each failure.
