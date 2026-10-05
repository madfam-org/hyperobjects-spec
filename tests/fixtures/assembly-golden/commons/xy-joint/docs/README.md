# XY Joint

A printed **XY joint** for a CoreXY gantry whose two belts run **stacked on two levels**: a 2.4-class "flying
gantry". It is generated with **CadQuery** (B-Rep). The joint does three things:

- it screws onto the **MGN9H block** of a Y rail, which runs on top of the gantry's Y extrusion (C);
- it holds the end of the **2020 X beam (D)**, so that D crosses **above** the C's;
- on a shelf over D, it turns both belts through 90°: one on a **GT2 20-tooth toothed idler**, the other on a
  stack of **two F695 flanged bearings**. Each element is clamped under a roof arm by an M5x16 axle.

There are left- and right-hand versions; the right hand swaps the belt levels.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and configurator:
[Yantra4D](https://app.yantra4d.com).

> **Original design.** The functional brief comes from a Voron 2.4-class gantry. It is cited by page and
> section only, from the *Voron 2.4r2 build guide*, version 2023-07-04 (VoronDesign/Voron-2 @ `a192410`,
> GPL-3.0):
> - pp. 97–100: each XY joint carries an F695 stack (M5 shim, F695, F695, M5 shim) and a GT2 20-tooth idler,
>   each on a screw driven into plastic;
> - p. 101: the X beam's MGN12 rail ends 15 mm from D's end;
> - pp. 104–106: the X axis is held in the joints, and the joints are screwed onto the Y carriages with M3
>   screws, with D above the Y extrusions;
> - p. 125: the two belts are stacked, without the CoreXY crossing;
> - p. 131: the A/B belts are 6 mm wide.
>
> No Voron geometry, STL or CAD was copied, traced or derived. It is licensed CERN-OHL-W-2.0.

**Version 2.0.0 (round 2, lane P6-GANTRY, 2026-10-05) is a breaking revision.** Version 1 held D *between* the
C's, at their level. That made the gantry 475 mm wide, wider than the 350 frame's clear width between its Z
rails. Version 2 holds D above the C's (the guide's function) and moves both belt elements outboard of the X
carriage's reach, so the carriage reaches X ±175 (Klipper 0…350). The interfaces changed: see **Interfaces**.

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **XY Joint** | `xy_joint` | The single joint. `mirrored` builds the right hand. |

## Parameters

| Group | Parameter | Default | Notes |
| :--- | :--- | :--- | :--- |
| Idler | `idler_width` | 9 mm | The toothed idler's width, flange to flange. 9 is the cited listing (catalog `gt2-idler-20t-6mm`). |
| Hand | `d_end` | 11 mm | How far D's end sits outboard of the Y rail's centre: 430 / 2 − half the C centre spacing. That is 11 for the 408 spacing. |
| Hand | `mirrored` | off | Builds the right joint. x is reflected and the stack and idler swap belt levels. |

## Layout and the cited derivations

**Model frame and heights.**
- Origin at the centre of the MGN9H block's top face.
- +x is the gantry's right (inboard for the left joint), +y is the back, +z is up.
- Gantry z (from the C's top face) = this z + 10. The 10 is the MGN9 assembly height H (HIWIN MG series).
- The belt line (both X runs) is y = 0, over D's centre.

**Vertical stack (gantry z).** All of these are conventions unless cited:

| Item | Gantry z |
| :--- | :--- |
| Base on the block | 10–18. M3x8 head seats at 15: 8 minus the 3 mm M3x3 thread depth of the MGN9H. |
| Saddle | 18–22 |
| D | 22–42 (centre 32) |
| Shelf | 42.5–49 |
| Low belt (B) | 54 |
| High belt (A) | 70 |
| Roof arms | 3 thick, over each element. A − B = 16 keeps the low stack's M5x16 head under the high idler's Ø18 flange (they overlap in plan). |
| Highest axle head | 80.75 (right joint) |

**D held over its last 15 mm.** The MGN12 rail ends 15 mm from D's end (guide p. 101), so the joint holds D only
over that 15 mm: the saddle and walls all stop at the rail's start.
- A tongue sits in D's bottom slot.
- An M5x10 BHCS through the back wall goes into a T-nut in D's back slot, 10 from D's end.

**Belt geometry (cited).**
- **The F695 stack** sits 7.006 in front of the belt line. That is the F695's Ø13 outer ring (NSK F695ZZ) plus
  the belt's back-side offset, B − T − U = 0.506:
  - B 1.52 and T 0.76 come from Pfeifer's 2MR/PGGT2 row;
  - U 0.254 comes from SDP/SI Table 4.

  The belt's back runs on the stack.
- **The toothed idler** sits 6.366 behind the belt line: the GT2 20T pitch radius, from SDP/SI Table 33
  (pd 12.73).
- **Hands.** On the left joint the stack carries B (low) and the idler carries A (high); the right joint swaps
  them.
- **Lateral positions.** The stack is 2 outboard of the rail centre (gantry |x| 206) and the idler 3 outboard
  (|x| 207). This keeps their flanges at |x| ≥ 198.5 and 198.0, outside the X carriage's reach. Its clamp
  tower reaches 175 + 20 at X ±175 (P6-XCAR), which leaves ≥ 3.

**What the joint clears** (all verified in the gantry's proof document):
- the MGN12H and the carriage's front plate, at X ±175;
- the outer belt run, at |x| 225.7. The joint stops at |x| 222.

## Interfaces

Every frame reads `s = 1 − 2·mirrored`, `zs = 44 + 16·mirrored` (the stack's level) and
`zi = 60 − 16·mirrored` (the idler's level).

| Interface | Type | Polarity / key / symmetry | Where |
| :--- | :--- | :--- | :--- |
| `xy_joint_carriage` | `bolt_pattern` | male, `mgn9-carriage`, 2 | The origin, normal −z. It mates `mgn9h-carriage.top`. |
| `xy_joint_beam_key` | `profile` | male, `tslot-2020-6mm`, 2 | (s·(10 − d_end), 0, 12), normal +z. It mates D's bottom slot at its station 10. |
| `xy_joint_beam_mount` | `bolt_pattern` | male, `m5-screw-joint`, 0 | (s·(10 − d_end), 10, 22) on D's back face, normal −y. It mates `tnut-2020-m5.thread` in D's back slot. |
| `xy_joint_beam_mount_head` | `socket` | female, `m5-clearance-hole`, 0 | 4.5 behind D's back face. It takes `bhcs-m5x10`. |
| `xy_joint_stack_bolt` | `socket` | female, `m5-clearance-hole`, 0 | (−2·s, −7.006, zs + 8), on the roof arm. It takes `bhcs-m5x16`. |
| `xy_joint_stack_roof` | `surface` | neutral, `m5-axle-stack-face`, 0 | zs + 5, the roof's underside. The upper shim bears here. |
| `xy_joint_stack_floor` | `surface` | neutral, `m5-axle-stack-face`, 0 | zs − 5. The lower shim bears here. |
| `xy_joint_idler_bolt` | `socket` | female, `m5-clearance-hole`, 0 | (−3·s, 6.366, zi + idler_width / 2 + 3). It takes `bhcs-m5x16`. |
| `xy_joint_idler_roof`, `_floor` | `surface` | neutral, `m5-axle-stack-face`, 0 | zi ± idler_width / 2. These take the idler's faces A and B. |

**Gate results.** The render-time frame gate passes all ten interfaces at the defaults and at every preset:
50 of 50.

**Proof.** The gantry's round-2 proof places this joint on both Y blocks of the 350 gantry, with D, both belt
stacks and idlers, and P6-XCAR's carriage. The document is
`claudedocs/digital-twins-mes-2026-10-02/phase6/p6gantry-v2-paths.assembly.json`.

**Not modelled:**
- the belt;
- the endstop and its wiring channel.

## Presets

- **Left Joint, 350 Gantry:** the defaults.
- **Right Joint, 350 Gantry:** mirrored.
- **Left / Right Joint, 10 mm-Wide Idler.**

## Graph twin

`xy-joint.graph.json` is a node-graph twin of `main.py` (graph format 1.1). It has the same parameters, the same derivations (clamps as min/max ternary pairs) and the same operations in the same order.
- **Declaration.** The mode declares it as `graph_file` next to the script.
- **Hands.** The script's `if mirrored:` branches become ternaries (the boss under the raised element) and a `select` (the seat ring under the low idler). The right-hand joint is the script's `body.mirror("YZ")`: a `reflect` YZ chosen by `select` on `mirrored`.
- **Seam.** D's back-slot screw runs along +Y. The twin lays a Z cylinder down with `rotate` x −90 and spins it with `rotate` y −90, so the B-rep seam lands where `makeCylinder` puts it (x direction +Z) and the meshes stay vertex-identical.
- **Verification.** `y4d-spec check --render --parity` compares the two at the defaults and at every preset; they agree to 0.000000 mm.
- **Which one renders.** `main.py` stays the source the platform renders and the oracle the graph is checked against. A script retires only after parity holds across the nightly sweep (owner decision D5, 2026-10-04).

## Hyperobject Profile

- **Domain:** industrial.
- **Material awareness:** `tolerance_by_material`.
- **Societal benefit:** an open, printable XY joint for stacked-belt CoreXY gantries. It takes only
  off-the-shelf M3 and M5 screws, a T-nut, F695 bearings and a standard GT2 idler.
- **License:** CERN-OHL-W-2.0.

## Engine notes

- **Engine:** CadQuery (`main.py`), one body.
- **Sandbox-safe:** it reads `PARAM(lambda: name, default)`, dispatches on `target_part`, and assigns the
  solid to `result`.
- **Keystone:** it needs the gantry catalog (`mgn9-carriage`), which lands with hyperobjects-spec #47.

## Resumen (es)

Unión XY impresa para un pórtico CoreXY con dos bandas apiladas (tipo 2.4):
- **Montaje:** se atornilla sobre el bloque MGN9H del riel Y y sostiene el extremo de la viga X (D) de modo que
  D cruza por encima de los perfiles Y (C).
- **Bandas:** sobre D, una repisa lleva una polea dentada GT2 de 20 dientes y una pila de dos F695, que giran
  las bandas 90° en sus dos niveles; cada elemento queda sujeto bajo un brazo por un eje M5x16.
- **Versión 2.0.0:** cambio incompatible. El carro X alcanza X ±175 y el pórtico cabe entre los rieles Z.

Es un diseño original. La guía de armado de la Voron 2.4r2 (GPL-3.0) se cita solo por página (pp. 97–106, 125,
131); no se copia su geometría. Licencia CERN-OHL-W-2.0.

**Gemelo de grafo.** `xy-joint.graph.json` es un gemelo en grafo de nodos de `main.py` (formato 1.1): los
mismos parámetros, las mismas derivaciones y las mismas operaciones en el mismo orden. Las ramas `if mirrored:` son ternarios y un `select`; la mano derecha es un `reflect` YZ elegido por `select` sobre `mirrored`.
`y4d-spec check --render --parity` los compara en los valores por defecto y en cada preset, y
coinciden a 0.000000 mm. `main.py` sigue siendo la fuente que se renderiza y el oráculo
(decisión D5).
