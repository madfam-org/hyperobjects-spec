# A/B Front Idler

A printed **front idler** for a CoreXY gantry whose two belts run **stacked on two levels**, a 2.4-class
"flying gantry". It is generated with **CadQuery** (B-Rep).

- **Mounting.** It sits on the front end of a gantry Y extrusion (a 2020 "C" carrying the MGN9 rail). One M5
  screw goes into a T-nut in the C's top slot, and a tongue sits in that slot.
- **The belt.** It turns one belt through 180° on a **GT2 20-tooth toothed idler**. The idler stands outboard
  of the C, on its belt's level above the C, and turns on an **M5x16** axle under a roof arm.
- **Hands.** The left idler carries the B belt on the low level. The right one, mirrored, carries the A belt on
  the high level.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and configurator:
[Yantra4D](https://app.yantra4d.com).

> **Original design.** The functional brief comes from a Voron 2.4-class gantry. It is cited by page and
> section only, from the *Voron 2.4r2 build guide*, version 2023-07-04 (VoronDesign/Voron-2 @ `a192410`,
> GPL-3.0):
> - pp. 65 and 69: the A and B idlers;
> - pp. 91–93: the idlers sit on the front ends of the C extrusions, held by M5 screws into T-nuts;
> - p. 88: the MGN9 rail starts 25 mm from that end;
> - pp. 126–127: each belt makes a U-turn round its front idler;
> - p. 141: the belts are tensioned at the X carriage, so this idler has no tension arm.
>
> No Voron geometry, STL or CAD was copied, traced or derived. It is licensed CERN-OHL-W-2.0.
>
> The guide's front idlers carry F695 stacks. This design uses the cataloged 6 mm toothed idler instead,
> because its smaller effective diameter (12.73 against 15.03 for an F695 with the belt's teeth on it) is what
> lets the X carriage reach X ±175 inside the 350 frame.

**Version 2.0.0 (round 2, lane P6-GANTRY, 2026-10-05) is a breaking revision.** Version 1 ran the belts at the
C's level and carried an F695 stack inboard, with a side screw. Version 2 runs the belts above the C's, puts the
toothed idler outboard, and keeps the body clear of the Z-joint and Z-strand keep-outs at the C's front end. Its
interfaces changed; see **Interfaces**.

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **Front Idler** | `front_idler` | The single idler. `mirrored` builds the right (A) idler. |

## Parameters

| Group | Parameter | Default | Notes |
| :--- | :--- | :--- | :--- |
| Idler | `idler_y` | 26 mm | The idler's axis, measured from the C's front end. 25.5 keeps the Ø18 flange behind the Z-joint keep-out (16); 27 keeps the boss ahead of the Y block at Y = 0. |
| Idler | `idler_width` | 9 mm | GT2 20T 6 mm-belt idler, flange to flange. 9 is the cited listing. |
| Hand | `mirrored` | off | The right (A) idler: x is reflected and the idler sits on the high level. |

## Belt geometry and keep-outs

The model frame:
- **Origin:** on the C's top face, on its centreline, at its front end face.
- **Axes:** +x is the gantry's right, +y the back, +z up. Heights are gantry z.

**Where the idler sits.** The idler's axis is 15.372 outboard of the C centre (gantry |x| 219.372). Its pitch
circle (12.73, from SDP/SI Table 33) is tangent to both runs of its belt:
- the outer run to the A/B drive, at |x| 225.738;
- the inner run to the XY joint's stack, at |x| 213.006.

That spacing (12.73) plus the joint stack's back-side radius (13 / 2 + 0.506) is what fixes those positions,
along with the X carriage's clamp reach at X ±175. The belt levels are B at 54 and A at 70 above the C top, the
same as in `xy-joint` and `ab-drive`.

**Keep-outs it respects** (the gantry proof checks them):
- **Under the X carriage.** Over the C's inboard part (|x| ≤ 210) the body is only a block at z 0–8, under the
  X carriage, which comes down to gantry z 10 at Y = 0.
- **Z-joint and Z-strand keep-out.** Outboard of the C (|x| > 214) nothing sits ahead of y 16.5.
- **Y block.** Behind the rail start, nothing sits in the Y block's path (y ≥ 29.5 at z < 10).

## Sources and conventions

**Cited facts**
- **GT2 20T 6 mm idler** (catalog `gt2-idler-20t-6mm`): OD 18, width 9, pitch diameter 12.73.
- **MISUMI HFS5-2020:** 6 mm slot, 2 mm lips, and Ø4.2 for M5.
- **Guide p. 88:** the rail starts 25 from the C's end.
- **ISO 7380-1 M5 head:** dk 9.5.

**Conventions (not sourced)**
- **Belt levels:** 54 and 70.
- **Slot station:** 10.
- **M5x10 grip:** 4.5.
- **Roof arm:** 3 thick. An M5x16 spans 3 roof + 9 idler + 4 in the pilot.
- **Post:** at |x| 229.5–233.5, outboard of the outer run.
- **Web:** y 17–29.5.

## Interfaces

Every frame reads `s = 1 − 2·mirrored` and `zf = 54 + 16·mirrored`.

| Interface | Type | Polarity / key / symmetry | Where |
| :--- | :--- | :--- | :--- |
| `front_idler_top_mount` | `bolt_pattern` | male, `m5-screw-joint`, 0 | (0, 10, 0), normal −z. It mates `tnut-2020-m5.thread` in the C's top slot. |
| `front_idler_top_mount_head` | `socket` | female, `m5-clearance-hole`, 0 | (0, 10, 4.5). It takes `bhcs-m5x10`. |
| `front_idler_top_key` | `profile` | male, `tslot-2020-6mm`, 2 | (0, 10, 0). It mates the C's top-face slot at station 10. |
| `front_idler_idler_bolt` | `socket` | female, `m5-clearance-hole`, 0 | (−15.372·s, `idler_y`, zf + idler_width / 2 + 3). It takes `bhcs-m5x16`. |
| `front_idler_idler_roof`, `_floor` | `surface` | neutral, `m5-axle-stack-face`, 0 | zf ± idler_width / 2. They take the idler's faces A and B. |

**Gate results.** The render-time frame gate passes all six interfaces at the defaults and at every preset:
24 of 24.

**Proof.** The gantry's round-2 proof is
`claudedocs/digital-twins-mes-2026-10-02/phase6/p6gantry-v2-paths.assembly.json`. It checks this idler at
every Y and X limit under `--collision`.

## Presets

- **Left (B) Idler, 350 Gantry:** the defaults.
- **Right (A) Idler, 350 Gantry:** mirrored.
- **Left (B), 10 mm-Wide Idler.**

## Hyperobject Profile

- **Domain:** industrial.
- **Material awareness:** `tolerance_by_material`.
- **Societal benefit:** an open, printable front idler for stacked-belt CoreXY gantries. It takes off-the-shelf
  M5 screws, a T-nut and a GT2 toothed idler.
- **License:** CERN-OHL-W-2.0.

## Engine notes

- **Engine:** CadQuery (`main.py`), one body.
- **Sandbox-safe:** it reads `PARAM(lambda: name, default)`, dispatches on `target_part`, and assigns the
  solid to `result`.
- **Keystone:** it needs only size keys already in the pinned keystone.

## Resumen (es)

Polea loca frontal impresa para un pórtico CoreXY con dos bandas apiladas (tipo 2.4):
- **Montaje:** se asienta en el extremo frontal de un perfil Y del pórtico, sujeta con un tornillo M5 a una
  tuerca en T.
- **Banda:** la gira 180° en una polea dentada GT2 de 20 dientes, por fuera del perfil y en el nivel de su
  banda. La polea gira en un eje M5x16 bajo un brazo.
- **Versión 2.0.0:** cambio incompatible. Las bandas van por encima de los perfiles C y el cuerpo respeta las
  zonas libres de los Z.

Es un diseño original. La guía de armado de la Voron 2.4r2 (GPL-3.0) se cita solo por página (pp. 65, 69, 88,
91–93, 126–127, 141); no se copia su geometría. Licencia CERN-OHL-W-2.0.
