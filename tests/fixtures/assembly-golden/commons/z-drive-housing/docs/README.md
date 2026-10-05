# Z Drive Housing

A printed housing generated with **CadQuery** (B-Rep). It hangs under a bottom corner of a
**2020 extrusion frame joined by blind joints** and carries a **belt-reduction Z drive**:
- a NEMA 17 with a **16-tooth GT2 pulley** drives an **80-tooth GT2 pulley** through a closed
  GT2 loop, a 5:1 reduction;
- the 80-tooth pulley sits on a **Ø5 output shaft** that turns in **three 625 bearings**;
- a **20-tooth 9 mm GT2 pulley** on the same shaft drives the **Z belt**, which rises through
  the frame corner to a top-corner idler.

Two M5 T-nuts and two slot tongues fix it to the frame. The motor's slots set the loop
tension. Right- and left-hand versions cover the four corners.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and configurator:
[Yantra4D](https://app.yantra4d.com).

> **Original design.** The functional brief comes from a Voron 2.4-class printer's Z drive.
> It is cited by page and section only, from the *Voron 2.4r2 build guide*, version
> 2023-07-04 (VoronDesign/Voron-2 @ `a192410`, GPL-3.0):
> - p. 8: the 625 bearing is the Z drives' bearing;
> - pp. 32–33: a 5x60 D-cut shaft carrying a GT2 20-tooth 9 mm pulley, a GT2 80-tooth pulley,
>   three 625 bearings and M5 shims;
> - p. 34: a GT2 188 mm belt loop;
> - p. 38: a GT2 16-tooth pulley on each Z motor;
> - pp. 41–43: the drive fixed to the frame with M5 T-nuts and M5x10 BHCS;
> - p. 47: four drives, the printed parts mirrored for two of them;
> - pp. 49 and 118: the top-corner idler faces the same way as the pulley below it, and the Z
>   belt runs from the drive up over that idler.
>
> No Voron geometry, STL or CAD was copied, traced or derived. This housing's shape comes from
> the cited facts below. It is licensed CERN-OHL-W-2.0.

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **Z Drive Housing** | `z_drive` | The single housing. `mirrored` builds the opposite hand. |

## Parameters

| Group | Parameter | Default | Notes |
| :--- | :--- | :--- | :--- |
| Drive | `belt_offset` | 13 mm | The output shaft's position along the horizontal, measured from the corner plane. Match the top idler's offset (corner-idler-bracket `idler_offset`, 13 by default) so the Z belt runs vertical. |
| Drive | `belt_plane` | 17.5 mm | The Z belt's mid-plane, measured from the horizontal's inner face into the frame. 17.5 is corner-idler-bracket's idler mid-plane at its defaults. |
| Drive | `center_distance` | 40.8 mm | The motor axis to the output shaft. 40.8 closes a 188 mm loop on 16 and 80 teeth within 0.01 mm (see below). The motor slots give ±2 mm for tension. |
| Drive | `big_pulley_od` | 55 mm | The 80-tooth pulley's flange diameter. It sets how deep the shaft sits: 1.5 mm clearance under the top plate and above the floor. |
| Frame Mount | `mount_pitch` | 20 mm | The spacing of the two mount screws. A T-nut is 15 mm long. |
| Frame Mount | `mirrored` | off | Builds the left-hand housing, reflected in x. |

### Layout

Along y, measured from the Z belt's mid-plane (`belt_plane`), toward the outside of the
frame:

| Station | y − belt_plane | Comes from |
| :--- | ---: | :--- |
| Wall A outer face = bearing A face A (seat opening) | +13.65 | 6.65 + 0.5 + 1.5 shoulder + 5 bearing |
| Wall A inner face | +7.15 | the 20-tooth pulley's flange end (W/2 = 6.65) + 0.5 |
| 20-tooth pulley flange end / belt mid-plane / hub end | +6.65 / 0 / −14.35 | MISUMI GPA 9 mm: L 21, W 13.3, belt centred in W |
| Wall B bearing opening = bearing B face A | −14.85 | hub end − 0.5 |
| Wall B −y face | −21.35 | − 5 bearing − 1.5 shoulder |
| 80-tooth pulley hub end / belt mid-plane / flange end | −21.85 / −34.85 / −39.85 | listing: overall 18, hub 8, belt centred in the other 10 |
| Wall C bearing opening = bearing C face A | −40.35 | flange end − 0.5 |
| Wall C outer face = motor face | −46.85 | − 5 bearing − 1.5 shoulder |

- **The shaft** runs from wall A's outer face, 60 mm long (p. 32), to −46.35, inside wall C's
  shoulder. All three bearings face the same way (face A toward +y), so the shaft goes in
  from inside the frame after the housing is bolted on.
- **The 16-tooth pulley** goes on the motor flange end first. Its face B lands 6.85 mm off
  the motor face, which puts its belt mid-plane (5.15 from face B) at −34.85, the 80-tooth
  pulley's.
- **The shaft axis** is at z = −(10 + 7.5 + `big_pulley_od`/2 + 1.5) = −46.5 at the defaults.

### Sources and conventions

**Cited facts**
- **625 bearing:** 5 × 16 × 5 (SKF 625-2RS1).
- **The pulleys** (MISUMI GPA 2GT, 2019 MX catalog p. 1340):
  - 20 teeth, 9 mm belt: L 21, W 13.3, P.D. 12.73;
  - 16 teeth, 6 mm belt: L 18, W 10.3, P.D. 10.19.
- **The 80-tooth pulley** (Spool3D listing): overall 18, hub 8, flange 54.7–55. Its P.D. is
  50.93 (Gates 2MR-80S, 2.005 in).
- **The belt:** Gates 2MR belting, height 1.52 (design manual 17195, p. 90). The Z belt is
  9 mm wide (guide p. 111).
- **NEMA 17** (catalog `nema-17-48mm`): a 31 mm M3 square, a Ø22 × 2 pilot, a 42.3 mm body.
- **M5x10 BHCS** (ISO 7380-1, Keller & Kalmbach): dk 9.5, l 10. MISUMI HFS5 slots: a 6 mm
  opening with 2 mm lips. HNTAP5-5 T-nuts are 15 mm long.
- **The reduction's centre distance.** A closed belt on pitch diameters D and d at centre
  distance C has the pitch length L = 2C·cos φ + π(D + d)/2 + φ(D − d), with sin φ =
  (D − d)/2C. On 50.93 and 10.19, C = 40.80 gives L = 188.006.

**Conventions (not sourced)**
- A 0.5 mm gap between each pulley and the next bearing face.
- 1.5 mm bearing shoulders, each with a Ø10 hole.
- Ø16.2 bearing pockets.
- Plate thicknesses: a 7.5 mm top plate and a 4 mm floor.
- 1.5 mm of room round the 80-tooth flange.
- Holes: Ø5.5 clearance holes and Ø10.5 counterbores, 3 mm deep. 10 − 4.5 = 5.5 mm of each
  screw passes into its T-nut.
- 5.8 mm tongues, as in roller-bracket.
- Mount screw A sits 20 mm from the corner plane.
- The motor slots allow ±2 mm.
- The Z belt slot clears the belt by 1.5 mm.
- Walls A and B and the floor reach 22 mm past the shaft.

## Interfaces

Model frame:
- **Origin:** on the inside corner line, at the bottom horizontals' slot-centre height.
- **+x:** along the horizontal the housing hangs under, away from the corner.
- **+y:** out of that horizontal's inner face, into the frame.
- **+z:** up. The frame's bottom is at z = −10.
- **Mirroring:** `mirrored` reflects x. Every frame reads `s = 1 − 2·mirrored`.

| Interface | Type | Polarity / key / symmetry | Where |
| :--- | :--- | :--- | :--- |
| `z_drive_mount_a`, `_b` | `bolt_pattern` | male, `m5-screw-joint`, 0 | On the top face, on the screw axes at x = 20 and 20 + `mount_pitch`, y = −10. The normal points up, into the horizontal. These mate the catalog `tnut-2020-m5.thread`. |
| `z_drive_mount_a_head`, `_b_head` | `socket` | female, `m5-clearance-hole`, 0 | The counterbore floors, at z = −14.5. These mate a `bhcs-m5x10.head_seat`. |
| `z_drive_slot_key` | `profile` | male, `tslot-2020-6mm`, 2 | The top face at (10, −10, −10). The tongue sits in the horizontal's bottom slot (`slot_*_a` at its default station 10). |
| `z_drive_corner_key` | `profile` | male, `tslot-2020-6mm`, 2 | The top face at (−10, 10, −10). The tongue sits in the perpendicular horizontal's bottom slot, at station 10. |
| `z_drive_bearing_a`, `_b`, `_c` | `socket` | female, `bearing-625`, 0 | The seat openings at x = `belt_offset`, z = shaft axis, y = `belt_plane` + 13.65, − 14.85 and − 40.35. The normal is +y, out of each pocket. These mate `bearing-625.outer_race`. |
| `z_drive_motor_face` | `bolt_pattern` | male, `nema-17-face`, 4 | Wall C's outer face on the motor axis, at x = `belt_offset` + `center_distance`, y = `belt_plane` − 46.85. The normal is −y, toward the motor. This mates `nema-17-48mm.face`. |

**Gate results.** The render-time frame gate checks all ten interfaces at the defaults and at
every preset, mirrored ones included: 50 of 50 pass.

**Closure.** The keystone test `tests/test_catalog_z_drive.py` closes the bottom corner:
- an upright, and two horizontals on it by blind joints;
- this housing keyed into both bottom slots, with its T-nuts and M5x10s;
- three 625s, and the shaft through all three (two closed cycles);
- the 20- and 80-tooth pulleys, the NEMA 17, and its 16-tooth pulley coplanar with the
  80-tooth.

The same test then puts corner-idler-bracket at the top of the same upright and shows the
Z idler and the Z pulley share one belt plane and one vertical.

**Not modelled:**
- the belts, which are declared paths (ASM-1 §9);
- M5 shims beside the bearings (the guide's p. 33 stack), since the 0.5 mm gaps stand in for
  them;
- the motor's M3 screws.

## Presets

- **Right-Hand Corner.** The defaults, stated explicitly.
- **Left-Hand Corner (Mirrored).** The opposite hand. The render check notes that this preset
  renders "identical to the defaults". That note is expected: the check compares volume only,
  and a reflection keeps the volume.
- **Loop Tensioned (+1 mm).** `center_distance` 41.8, the motor 1 mm further out in its slots.
- **Deeper Belt Plane, Wider Offset, Left-Hand.** `belt_offset` 20, `belt_plane` 24,
  `mount_pitch` 24, mirrored. This is for a top idler set further into the frame.

## Hyperobject Profile

- **Domain:** industrial.
- **Material awareness:** `tolerance_by_material`.
- **Societal benefit:** an open, printable belt-reduction Z drive. It uses only off-the-shelf
  parts (a NEMA 17, GT2 pulleys and belts, 625 bearings, M5 screws and T-nuts), and its
  interfaces are machine-checked against the frame, the bearings and the motor.
- **License:** CERN-OHL-W-2.0.

## Engine notes

- **Engine:** CadQuery (`main.py`), one body.
- **Sandbox-safe:** it reads `PARAM(lambda: name, default)`, dispatches on `target_part`, and
  assigns the solid to `result`.
- **Keystone needed:** a keystone with the Z drive catalog (`bearing-625`, `shaft-5mm`, the GT2
  pulleys; lane P6-ZBED). Until `SPEC_PIN` moves past it, `y4d-spec check` passes, because
  this housing's own size keys (`bearing-625`, `nema-17-face`, `m5-screw-joint`,
  `m5-clearance-hole`, `tslot-2020-6mm`) already exist. Only the closure test needs the new
  keystone.

## Resumen (es)

Carcasa impresa que cuelga bajo una esquina inferior de un marco de perfil 2020 con uniones
ciegas y lleva un accionamiento Z con reducción por banda:
- **Reducción:** un NEMA 17 con polea GT2 de 16 dientes mueve una polea de 80 dientes por una
  banda GT2 cerrada de 188 mm (5:1).
- **Salida:** una flecha de Ø5 en tres rodamientos 625 lleva una polea GT2 de 20 dientes y
  9 mm que mueve la banda Z.
- **Montaje:** se fija al marco con dos tuercas en T M5 y dos lengüetas de ranura.

Es un diseño original. La guía de armado de la Voron 2.4r2 (GPL-3.0) se cita solo por página
(pp. 8, 32–34, 38, 41–43, 47); no se copia su geometría. Licencia CERN-OHL-W-2.0.
