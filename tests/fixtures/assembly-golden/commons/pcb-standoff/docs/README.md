# PCB Standoff / Mounting Plate

Standoffs to raise a PCB above a surface, generated with **CadQuery** (B-Rep). A
hole pattern — the four corners of a W×D rectangle, or a rows×cols grid — drives
the standoff positions; each standoff is a bored tube sized to an M2 / M2.5 / M3
screw.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and
configurator: [Yantra4D](https://app.yantra4d.com).

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **Plate** | `plate` | Standoffs standing on a solid connecting base plate — one printable mounting plate. |
| **Loose Standoffs** | `standoffs` | The same standoffs joined by a thin runner strip so they print as one set and snap apart. |
| **Single Spacer** | `spacer` | One tubular spacer/standoff, bored through. |
| **Flight-Controller Stack Plate** | `fc_stack` | A corners plate locked to a standard FC/ESC stack pattern (`stack_pattern`: 30.5×30.5 M3, 20×20 M3, 20×20 M2). |

Render each mode with `target_part` set to that mode's part id to see the
distinct part.

## Parameters

| Group | Parameter | Default | Notes |
| :--- | :--- | :--- | :--- |
| Hole Pattern | `stack_pattern` | 30.5x30.5-m3 | `fc_stack` only: `30.5x30.5-m3`, `20x20-m3` or `20x20-m2`. Sets the corner spacing and the screw size. |
| Hole Pattern | `pattern` | corners | `corners` (W×D) or `grid` (rows×cols). |
| Hole Pattern | `rect_w` / `rect_d` | 58 / 49 mm | Corner hole spacing X / Y. |
| Hole Pattern | `grid_rows` / `grid_cols` | 3 / 3 | Grid standoff count. |
| Hole Pattern | `grid_pitch` | 20 mm | Grid hole-to-hole spacing. |
| Standoff | `standoff_h` | 6.0 mm | Standoff / spacer height. |
| Standoff | `screw_size` | M3 | M2 / M2.5 / M3 — sets bore and boss diameter. |
| Base Plate | `plate_t` | 2.0 mm | Connecting plate thickness (0 → thin default slab). |

## Presets

- **Pi HAT Plate (58×49)** — corner pattern at the HAT hole rectangle, M2.5.
- **Prototype Grid (4×4)** — a 16-standoff grid at 18 mm pitch, M3.
- **Tall M3 Spacer** — a single 15 mm spacer.
- **FC Stack 30.5×30.5 (M3)** — the common 5-inch flight-controller stack.
- **FC Stack 20×20 (M2)** — the small-quad stack.

## Hyperobject Profile

- **Domain:** industrial
- **CDG interfaces:**
  - **PCB Mount Pattern** (`bolt_pattern`, internal) — the hole layout, defined
    by `pattern`, `rect_w`, `rect_d`, `grid_rows`, `grid_cols`, `grid_pitch`,
    `screw_size`. Any board sharing that hole pattern bolts to these standoffs.
  - **Standoff Screw Bore** (`socket`, ISO metric M2/M2.5/M3) — `screw_size`,
    `standoff_h`: the bore each standoff presents to the mounting screw.
  - **FC Stack Plate Underside** (`bolt_pattern`) — the `fc_stack` plate's
    bottom face, where it sits on an airframe's stack mount (see below).
- **Material awareness:** the bore is sized slightly under nominal so a
  thread-forming screw bites plastic directly; `tolerance_by_material` is
  declared for per-filament tuning.
- **Societal benefit:** the simplest reprinted electronics primitive — raise any
  board off any surface at the exact height and hole pattern needed.
- **License:** CERN-OHL-W-2.0

## Mating frames (assemblies)

`fc_stack_underside` carries a SEM-1 frame on the `fc_stack` part: origin
`(0, 0, 0)` (the centre of the hole square, on the plate's bottom face), normal
`-z`, `x_axis` `+x`, symmetry 4, polarity **female** (the airframe's stack bolts
rise through the plate). Its size key follows `stack_pattern`: `stack-30.5x30.5-m3`,
`stack-20x20-m3` or `stack-20x20-m2`. The frame is verified against the rendered
part at the defaults and every preset (`y4d-spec check --render`).

`fc_stack_top` frames the standoff tops, where the boards sit: origin
`(0, 0, t + standoff_h)` with `t` the plate thickness (1.6 mm when `plate_t` is
0), normal `+z`, `x_axis` `+x`, symmetry 4, polarity **male** (the standoffs rise
through the boards' holes), the same `stack_pattern` size key. The centre of the
hole square has no material; on a 30.5 mm square the standoff tops stand 21.6 mm
from it, so the gate's progressive search (ASM-1 v1.1, keystone 0.4.0 or later)
finds them in the 22.5 mm ring; on 20 × 20 they are found within 15 mm.

## Engine notes

- Engine: **CadQuery** (`main.py`). Exports STL / 3MF / STEP / GLB / GLTF / OBJ.
- The script is **self-contained** (sandbox-safe): parameters are read via a
  `PARAM(lambda: name, default)` guard; the final solid is assigned to `result`
  and the active part is selected through `target_part`.
- All shipped presets and defaults render **watertight**.
