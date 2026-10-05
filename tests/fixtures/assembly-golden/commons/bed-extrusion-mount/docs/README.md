# Bed Extrusion Mount

A printed T-plate generated with **CadQuery** (B-Rep). It joins the end of a **bed-support
2020 extrusion** to the **frame's bottom horizontal** it butts against, with their tops flush:
- the crossbar bolts to the horizontal's top slot with **two M5 T-nuts**;
- the stem bolts to the bed extrusion's top slot with **one M5 T-nut**;
- a tongue in each slot holds the bed extrusion square to the horizontal and at its butt.

The plate is symmetric, so one part serves all four ends of a printer's two bed extrusions.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and configurator:
[Yantra4D](https://app.yantra4d.com).

> **Original design.** The functional brief comes from a Voron 2.4-class printer's bed
> supports. It is cited by page and section only, from the *Voron 2.4r2 build guide*,
> version 2023-07-04 (VoronDesign/Voron-2 @ `a192410`, GPL-3.0):
> - p. 19: each bed extrusion's ends are fixed with an M5x10 BHCS, an M5 shim and an M5
>   T-nut;
> - p. 20: the two bed extrusions are 130 mm apart, centred on the printer's centreline;
> - p. 58: the bed plate stands on them, on M3 T-nuts and M4 thumb nuts used as spacers;
> - p. 60: the plate's front edge is 38 mm behind the frame's front edge.
>
> No Voron geometry, STL or CAD was copied, traced or derived. This plate's shape comes from
> the cited facts below. It is licensed CERN-OHL-W-2.0.

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **Bed Extrusion Mount** | `bed_mount` | The single plate. |

## Parameters

| Parameter | Default | Notes |
| :--- | :--- | :--- |
| `screw_offset` | 14 mm | Each frame screw's distance from the bed extrusion's centreline, along the horizontal. The two T-nuts, each 15 mm long, must not overlap. |
| `stem_length` | 17.5 mm | How far the plate runs along the bed extrusion from the butt. |
| `plate_t` | 4.5 mm | The plate's thickness, which is also the M5x10's grip: 10 − 4.5 = 5.5 mm passes into the T-nut. |

### Sources and conventions

**Cited facts**
- **M5x10 BHCS** (ISO 7380-1, Keller & Kalmbach): d 5, l 10, dk 9.5.
- **MISUMI HFS5:** a 6 mm slot opening with 2 mm lips, on a 20 mm profile. HNTAP5-5 T-nuts
  are 15 mm long.
- **The stem's default.** The guide puts the bed plate's front edge 38 mm behind the frame's
  front edge (p. 60). That is 18 mm past a 20 mm horizontal's inner face. The default 17.5
  keeps the plate inside that 18 mm.

**Conventions (not sourced)**
- Ø5.5 clearance holes, with the heads on the top face.
- 5.8 mm tongues, as in roller-bracket.
- 3.5 mm of plate beyond each screw head.
- The bed screw sits 10 mm from the butt (the bed extrusion's `slot_station_mm` 10).
- The crossbar stops 2 mm short of the horizontal's outer edge.
- **No M5 shim** under the heads. The guide uses one (p. 19); here the printed plate takes
  the head.

## Interfaces

Model frame:
- **Origin:** where the bed extrusion's centreline meets the horizontal's inner face, in the
  plane of the two top faces.
- **+x:** along the horizontal.
- **+y:** along the bed extrusion, into the frame.
- **+z:** up.

| Interface | Type | Polarity / key / symmetry | Where |
| :--- | :--- | :--- | :--- |
| `bed_mount_frame_a`, `_b` | `bolt_pattern` | male, `m5-screw-joint`, 0 | The plate's underside at (∓`screw_offset`, −10, 0). The normal points down, into the horizontal. These mate `tnut-2020-m5.thread`. |
| `bed_mount_bed` | `bolt_pattern` | male, `m5-screw-joint`, 0 | The underside at (0, 10, 0), over the bed extrusion. |
| `bed_mount_frame_a_head`, `_b_head`, `bed_mount_bed_head` | `socket` | female, `m5-clearance-hole`, 0 | The top face over each screw, z = `plate_t`. These mate a `bhcs-m5x10.head_seat`. |
| `bed_mount_frame_key` | `profile` | male, `tslot-2020-6mm`, 2 | The underside at (0, −10, 0). The tongue runs along the horizontal's top slot, at the station of the bed extrusion's centreline. |
| `bed_mount_bed_key` | `profile` | male, `tslot-2020-6mm`, 2 | The underside at (0, 10, 0). The tongue runs along the bed extrusion's top slot. It mates `slot_*_a` at that extrusion's default station 10, which puts end A against the horizontal. |

**Gate results.** The render-time frame gate checks all eight interfaces at the defaults and
at every preset: 32 of 32 pass.

**Closure.** The keystone test `tests/test_catalog_z_drive.py` places a 470 mm bed extrusion
through this plate alone, from a frame horizontal joined to an upright by a blind joint:
- its end A butts the horizontal's inner face;
- its axis runs square to the horizontal;
- its top is flush with the horizontal's.

A wrong slot station moves the bed extrusion by exactly that error.

**Placement in a 2.4-class 350 frame** (for the assembly):
- the frame horizontals are 470 mm long between the uprights;
- the bed extrusions' centrelines are 255 − 65 = 190 mm from the frame's outer edge (p. 20);
- so on a horizontal's top slot, the station is 170 mm from end A.

**Not modelled:**
- the bed plate. The guide names no plate dimensions, so no catalog entry exists for it.
- the bed's M3 T-nuts and thumb-nut spacers (p. 58).

## Presets

- **Standard.** The defaults, stated explicitly.
- **Wide and Long.** `screw_offset` 20, `stem_length` 26.
- **Thin Plate.** `plate_t` 4, so 6 mm of each M5x10 passes into its T-nut.

## Graph twin

`bed-mount.graph.json` is a node-graph twin of `main.py` (graph format 1.1). It has the same parameters, the same derivations and the same operations in the same order. Each `_box` is a centred `box` translated to its centre, each `_cyl_z` an XY `profile_circle` extruded and translated to its start, and each clamp a min/max ternary pair in `derived`; the constants keep `main.py`'s names, values and sources.
- **Declaration.** The mode declares it as `graph_file` next to the script.
- **Verification.** `y4d-spec check --render --parity` compares the two at the defaults and at every preset (`standard`, `wide_long`, `thin_plate`); they agree to 0.000000 mm.
- **Which one renders.** `main.py` stays the source the platform renders and the oracle the graph is checked against. A script retires only after parity holds across the nightly sweep (owner decision D5, 2026-10-04).

## Hyperobject Profile

- **Domain:** industrial.
- **Material awareness:** `tolerance_by_material`.
- **Societal benefit:** an open, printable joint for a printer's bed supports on 2020
  extrusion. It uses only M5 screws and T-nuts, and its interfaces are machine-checked against
  both extrusions it joins.
- **License:** CERN-OHL-W-2.0.

## Engine notes

- **Engine:** CadQuery (`main.py`), one body.
- **Sandbox-safe:** it reads `PARAM(lambda: name, default)`, dispatches on `target_part`, and
  assigns the solid to `result`.
- **Keystone:** every size key it writes (`m5-screw-joint`, `m5-clearance-hole`,
  `tslot-2020-6mm`) is in the pinned keystone. The `bhcs-m5x10` the closure test uses arrives
  with lane P6-ZBED's keystone PR.

## Resumen (es)

Placa en T impresa que une el extremo de un perfil 2020 de soporte de cama con el travesaño
inferior del marco contra el que apoya, con las caras superiores a ras:
- **Travesaño de la T:** dos tuercas en T M5 en la ranura superior del travesaño.
- **Vástago:** una tuerca en T M5 en la ranura superior del perfil de la cama.
- **Lengüetas:** una en cada ranura mantiene el perfil a escuadra y en su tope.

Es un diseño original. La guía de armado de la Voron 2.4r2 (GPL-3.0) se cita solo por página
(pp. 19–20, 58, 60); no se copia su geometría. Licencia CERN-OHL-W-2.0.
