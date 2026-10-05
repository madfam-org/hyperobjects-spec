# Z Joint

A printed **Z joint** for a CoreXY "flying gantry", a 2.4-class machine whose gantry rides four
Z rails. It is generated with **CadQuery** (B-Rep) and does three jobs:

- it bolts to the **MGN9H block** of a Z rail on a frame upright;
- it holds one corner of the gantry by a **pad under the gantry's C extrusion**: a tongue in the
  C's bottom slot and an M5 screw into a T-nut;
- it carries that corner's **`z-belt-clamp`** on a backer, placed so the clamped belt strand runs
  vertical, tangent to the Z drive pulley below and the top idler above.

The joint is **rigid**. A machine has four, in two hands.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and configurator:
[Yantra4D](https://app.yantra4d.com).

> **Original design.** The functional brief comes from a Voron 2.4-class machine. It is cited by
> page and section only, from the *Voron 2.4r2 build guide*, version 2023-07-04
> (VoronDesign/Voron-2 @ `a192410`, GPL-3.0):
> - pp. 25 and 27: the Z rails are MGN9 rails, centred on the uprights, facing each other across
>   the frame;
> - pp. 109 and 115–116: each gantry corner joins its rail's block through a Z joint, four in all,
>   fixed to the block with M3 screws;
> - pp. 111 and 117–121: the 9 mm Z belt's two ends are clamped on the gantry, and the belt runs
>   from there round the Z drive pulley, over the top idler and back.
>
> No Voron geometry, STL or CAD was copied, traced or derived. The guide's joint is a pivot (an
> M5x40 SHCS into a bearing block, p. 115), which lets quad gantry levelling tilt the gantry. This
> one is rigid: owner decision D2 of the Digital Twins programme models one logical Z, so per-belt
> tilt is later fidelity. It is licensed CERN-OHL-W-2.0.

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **Z Joint** | `z_joint` | The single joint. The default is the front-left one, which turned 180° about z is the back-right one. `mirrored` builds the front-right and back-left ones. |

## Parameters

| Group | Parameter | Default | Notes |
| :--- | :--- | :--- | :--- |
| Gantry | `c_inboard` | 21 mm | From the block's top face to the C extrusion's centre line. The minimum is 21: the C's outer face then stays 1 mm clear of the belt's free strand (see below). |
| Gantry | `c_end` | 20 mm | From the block's centre, along the upright's face into the frame, to the C's end. The pad's T-nut sits 10 further on. |
| Hand | `mirrored` | off | Reflects x: the front-right and back-left joints. |

## Where the belt runs

The joint is placed against three merged commons cartridges at their defaults:
`z-drive-housing` (`belt_offset` 13, `belt_plane` 17.5), `corner-idler-bracket` (`idler_offset` 13)
and `z-belt-clamp`. Their numbers fix the belt:

- **The pulley and the idler** stand 13 in from the upright's inner face, on one vertical. In the
  joint's frame the upright's inner face is x = −10 (the MGN9H's assembly height H 10), so their
  axis is at x = 3.
- **The strands** run one GT2 20-tooth pitch radius (12.73 / 2) either side: x = −3.365 (outer)
  and x = 9.365 (inner).
- **The belt's mid-plane** is 17.5 in from the frame's inner face, which is half the 20 mm
  upright from the block's centre: y = 27.5. The 9 mm belt spans y 23 … 32.

The clamp holds the **outer** strand. The **inner** strand runs free, full height, past the
gantry. Its belt body spans x 8.35 … 9.87 (the pitch line plus the 2 mm GT2 belt's teeth-side
offset T + U = 1.014 and back-side offset B − T − U = 0.506; Pfeifer and SDP/SI, as in the
catalog's `gt2-belt-6mm`). So:

- the backer and the web stay at y ≤ 19.2, in front of the belt;
- the pad under the C starts at the C's outer face, x = `c_inboard` − 10 ≥ 11, 1.13 mm clear of
  the free strand at the default.

The clamp's mount face is y = 27.5 − 8.3 = 19.2 (the clamp's belt mid-width is `base_t` + 4.8 =
8.3 off its face). Its screw axis is x = −3.365 + 1.2 (the clamp's belt wall is `slot_w` / 2 =
1.2 off its axis). The belt's back then bears on the jaw wall exactly on the outer tangent line.

## Sources and conventions

**Cited facts**
- **MGN9H:** H 10, W 20, L 39.9, M3 on B 15 × C 16 (HIWIN MG series). The plate covers the block's
  top face and carries the four M3 holes.
- **GT2 20T pitch diameter 12.73:** the catalog's `gt2-pulley-20t-9mm` (MISUMI GPA) and
  `gt2-idler-20t-9mm`.
- **MISUMI HFS5 2020:** 20 square, a 6 mm slot opening, 2 mm lips. Ø4.2 is the hole MISUMI taps
  M5; the clamp's M5x10 cuts its thread in it, as the guide's joint idlers are screwed into
  plastic (pp. 98, 100).
- **ISO 7380-1 M5x10 BHCS:** d 5, l 10. The pad is 4.5 thick, so 5.5 of the screw passes into the
  T-nut, as in `bed-extrusion-mount` and `z-belt-clamp`.

**Conventions (not sourced)**
- The plate is 6 thick. Its M3 holes are Ø3.4, counterbored Ø6.5 × 3.5 from the free side.
- The backer and the web stay 0.5 clear of the block's side (y ≥ 10.5). The backer reaches back
  to the upright's face plane (x = −10) and is 56 tall, the clamp's height.
- The groove for the clamp's 5.8 tongue is 6 wide and 2.5 deep. The pilot is 7 deep: 5.5 of
  thread plus 1.5.
- The pad is flush with both side faces of the C and runs 25 along it from its end. Its tongue
  is 5.8 wide and 2 high. Its T-nut sits 10 in from the C's end.
- The C's bottom face is at the block's centre height (z = 0), so the block's centre is 10 below
  the C's centre line.

## Interfaces

Every frame reads `s = 1 − 2·mirrored`.

| Interface | Type | Polarity / key / symmetry | Where |
| :--- | :--- | :--- | :--- |
| `z_joint_carriage` | `bolt_pattern` | male, `mgn9-carriage`, 2 | At the origin, normal −s·x (into the block), x_axis +z (along the rail). It mates `mgn9h-carriage.top`. |
| `z_joint_clamp_mount` | `bolt_pattern` | female, `m5-screw-joint`, 0 | The backer's face, (s·−2.165, 19.2, 0), normal +y, x_axis s·z. It mates `z-belt-clamp.z_belt_clamp_mount`. |
| `z_joint_clamp_slot` | `profile` | female, `tslot-2020-6mm`, 2 | The same point and axes. It mates `z-belt-clamp.z_belt_clamp_key`. |
| `z_joint_c_key` | `profile` | male, `tslot-2020-6mm`, 2 | The pad's top face, (s·`c_inboard`, `c_end` + 10, 0), normal +z, x_axis +y (along the C). It mates the C's bottom `slot_*`. |
| `z_joint_c_mount` | `bolt_pattern` | male, `m5-screw-joint`, 0 | The same point and axes. It mates `tnut-2020-m5.thread`. |
| `z_joint_c_mount_head` | `socket` | female, `m5-clearance-hole`, 0 | The pad's underside, 4.5 below, normal −z. It takes a `bhcs-m5x10.head_seat`. |

With `x_axis` s·z on the clamp's frames, the mirrored joint turns the clamp 180° about its
screw, so the belt's back always bears on the outboard jaw wall. On a mirrored joint the
clamp's `z_belt_clamp_upper` jaw is the lower one.

**Gate results.** The render-time frame gate checks all six interfaces at the defaults and at
every preset, mirrored ones included: 30 of 30 pass.

**In an assembly.** Assembly A (`assemblies/voron-2-4-class-350-motion-frame`) places four of
these joints on its four Z blocks, each with a `z-belt-clamp` and an M5x10. The four Z belt paths
then run clamp → Z pulley → top idler → clamp, with a constant pitch-line length over the whole Z
sweep.

**Not modelled:**
- the quad gantry levelling pivot (D2);
- the M3 screws (not catalogued) and the belt's folded tails;
- an endstop magnet or flag.

## Presets

- **Front Left / Back Right.** The defaults, stated explicitly.
- **Front Right / Back Left.** The mirrored hand. The render check notes that this preset renders
  "identical to the defaults". That is expected: the check compares volume, and a reflection
  keeps volume. The bounding box moves from x −10 … 31 to x −31 … 10.
- **C Alongside the Block (`c_end` 6).** For a gantry whose C extrusion runs past the block.
- **Narrower Gantry, Longer Reach.** `c_inboard` 30 and `c_end` 40, mirrored.

## Hyperobject Profile

- **Domain:** industrial.
- **Material awareness:** `tolerance_by_material`.
- **Societal benefit:** an open, printable Z joint for flying-gantry printers. It uses only
  off-the-shelf M3 and M5 screws and a T-nut, and its belt geometry is derived from the cited
  pulley and belt data of the parts it meets.
- **License:** CERN-OHL-W-2.0.

## Engine notes

- **Engine:** CadQuery (`main.py`), one body.
- **Sandbox-safe:** it reads `PARAM(lambda: name, default)`, dispatches on `target_part`, and
  assigns the solid to `result`.
- **Keystone needed:** a keystone with the gantry catalog (`mgn9-carriage`, hyperobjects-spec
  PR #47). Until `SPEC_PIN` moves past it, `y4d-spec check` reports that size key as unknown.

## Resumen (es)

Unión Z impresa para un pórtico volante CoreXY (tipo 2.4):
- **Montaje:** se atornilla al carro MGN9H de un riel Z y sostiene una esquina del pórtico con un
  cojín bajo el perfil C (lengüeta en su ranura inferior y un M5 a una tuerca en T).
- **Banda:** lleva la abrazadera `z-belt-clamp` en un respaldo colocado para que el tramo sujeto
  corra vertical, tangente a la polea del accionamiento Z y a la polea loca superior; el tramo
  libre pasa a 1.13 mm del perfil C.
- **Manos:** cuatro por máquina; la versión en espejo sirve a las esquinas delantera derecha y
  trasera izquierda. Es rígida: un solo Z lógico (decisión D2).

Es un diseño original. La guía de armado de la Voron 2.4r2 (GPL-3.0) se cita solo por página
(pp. 25, 27, 98, 100, 109, 111, 115–121); no se copia su geometría. Licencia CERN-OHL-W-2.0.
