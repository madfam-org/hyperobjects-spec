# A/B Drive

A printed **A/B drive unit** for a CoreXY gantry whose two belts run **stacked on two levels**, a 2.4-class "flying gantry". It is generated with **CadQuery** (B-Rep).

It sits on the rear end of a gantry Y extrusion (C) and reaches the rear gantry beam (E). It is held on M5 T-nuts. A **NEMA 17** hangs under its motor plate, inboard of the C.

It carries four belt elements on two levels:

| Element | Belt contact | What it does |
| :--- | :--- | :--- |
| **P**, the motor's GT2 20T pulley | teeth | Drives this unit's belt. The belt wraps it **126°**. |
| **Q**, a backside F695 stack | the belt's back | Bends the rear run round P to make that wrap. |
| **K**, a GT2 20T toothed idler at the outboard rear corner | teeth | Turns the diagonal from P into the outer run. |
| **S**, a pass-through F695 stack on the other level | teeth | Turns the other belt from its Y run into its rear run. |

Each element sits under a roof arm, clamped by an **M5x16** axle. There are left (B) and right (A) versions.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and configurator: [Yantra4D](https://app.yantra4d.com).

> **Original design.** The functional brief comes from a Voron 2.4-class gantry. It is cited by page and section only, from the *Voron 2.4r2 build guide*, version 2023-07-04 (VoronDesign/Voron-2 @ `a192410`, GPL-3.0):
> - pp. 73–80: the A and B drives, each with a NEMA 17, a GT2 20-tooth pulley and F695 stacks on M5 screws into plastic;
> - pp. 85–87: the rear E extrusion, with the drives on M5 T-nuts;
> - p. 95: the drives on the rear ends of the C extrusions;
> - pp. 125–127: the stacked CoreXY belt path.
>
> No Voron geometry, STL or CAD was copied, traced or derived. It is licensed CERN-OHL-W-2.0.

**Version 2.0.0 (round 2, lane P6-GANTRY, 2026-10-05) is a breaking revision.**
- **Version 1** put the motor behind the C's end with the pulley at the outer corner. Inside the 350 frame, that pushes the motor into the rear Z rail and the Z belt.
- **Version 2** puts the motor inboard of the C. The pulley sits on an omega (Q, P), and a toothed corner idler K turns the belt into the outer run.
- Every element outboard of the C stays ahead of the rear keep-out, and the belts run above the C's.
- The interfaces changed; see **Interfaces**.

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **A/B Drive** | `ab_drive` | The single unit. `mirrored` builds the right (A) drive. |

## Parameters

| Group | Parameter | Default | Notes |
| :--- | :--- | :--- | :--- |
| Hand | `e_end` | 34 mm | How far E's end sits inboard of the C centre: half the C centre spacing − 340 / 2. That is 34 for the 408 spacing. |
| Hand | `mirrored` | off | The right (A) drive: x reflected, P/Q/K on the high level, S on the low level. |

## Belt geometry and the wrap rule

The model frame:
- **Origin:** on the C's top face, on its centreline, at its **rear** end face.
- **Axes:** +x is the gantry's right, +y the back, +z up. Heights are gantry z.

The "Inboard x" column below is measured from the C centre. Element positions are for the left drive; the right drive mirrors x and uses the other levels and runs.

| Element | Inboard x | y | Level (left / right) | Effective radius |
| :--- | :--- | :--- | :--- | :--- |
| P (pulley) | 32 | 8 | 54 / 70 | 6.366 (pitch radius) |
| Q (backside stack) | 45 | −8.994 / −7.994 | 54 / 70 | 7.006 (13 / 2 + back-side offset) |
| K (corner idler) | −15.372 | −25.5 | 54 / 70 | 6.366 |
| S (pass-through stack) | −1.852 | −22.514 / −23.514 | 70 / 54 | 7.514 (13 / 2 + teeth-side offset) |

**The runs.**
- **Rear runs:** B at y −16 (gantry 434) and A at −15 (435).
- **Outer run:** at gantry |x| 225.738.
- **The other belt's Y run:** at |x| 213.366.

**Pulley wrap: 126.5° (B) and 126.6° (A), measured on the paths.**
- **The rule.** SDP/SI's Technical Section §13.3 (p. T-35) asks for at least 6 teeth in mesh and 60° of wrap on a loaded pulley.
- **What it means here.** A 20-tooth pulley turns 18° per tooth, so it needs **≥ 108°**.
- **Where the offsets come from.** The belt's pitch-line offsets are in catalog `gt2-belt-6mm`:
  - B 1.52 and T 0.76, from Pfeifer 2MR/PGGT2;
  - U 0.254, from SDP/SI Table 4.

**Motor and pulley.**
- **Motor face:** at z 44 (left) / 60 (right). That is 10 under the belt.
- **Belt mid-plane:** 8 above the pulley's face A. This is a **convention**, the keystone's for `gt2-pulley-20t-5mm`.
- **The pulley's face A:** sits on the motor's 2 mm pilot (`nema-17-48mm.shaft_seat_mm` 2).

**Clearances that set the layout.**
- **Low rear run vs the right motor.** B's rear run passes in front of the right drive's motor and plate (y ≥ −14.15).
- **High rear run vs Q's head.** A's rear run passes in front of the left drive's Q head (y ≤ −13.74 against −14).
- **Q, S and the pulley vs the other level.** Their tops stay under the other level's belt.

## Sources and conventions

**Cited facts**
- **NEMA 17** (keystone `nema-17-48mm`): face 42.3, 4 × M3 on 31, pilot Ø22.
- **GT2 20T pulley:** flange Ø16 (Adafruit 1251).
- **F695 stack:** 10 tall (1 mm DIN 988 shims, NSK F695ZZ).
- **Toothed idler:** 9 wide (Motedis).
- **MISUMI HFS5:** slots 6 mm with 2 mm lips; Ø4.2 for M5.
- **Guide p. 88:** the rail ends 25 from the C's end.
- **ISO 7380-1 M5 head:** dk 9.5.

**Conventions (not sourced)**
- **Element positions and levels:** the table above.
- **E:** its y band (gantry 406–426), ahead of the motor.
- **Posts:** K's at |x| 229.5–233.5; S's beside the rail end; Q's on the motor plate.
- **Wall and screw sizes:** plate 4 thick, roof arms 3 thick, M5x10 grip 4.5.

## Interfaces

Every frame reads:
- `s = 1 − 2·mirrored`;
- `zo = 54 + 16·mirrored` (own level), `zt = 70 − 16·mirrored` (other level);
- `zm = 44 + 16·mirrored` (motor face);
- `yq = −8.994 + mirrored`, `ys = −22.514 − mirrored`.

| Interface | Type | Polarity / key / symmetry | Where |
| :--- | :--- | :--- | :--- |
| `ab_drive_motor_face` | `bolt_pattern` | male, `nema-17-face`, 4 | (32·s, 8, zm), normal −z. It mates `nema-17-48mm.face`. |
| `ab_drive_c_mount`, `_head`, `ab_drive_c_key` | screw joint / clearance / profile | — | At (0, −10, 0 / 4.5). This is the C's top slot at station 10 from the rear end. |
| `ab_drive_e_mount`, `_head`, `ab_drive_e_key` | screw joint / clearance / profile | — | At (s·(e_end + 10), −34, 0 / 4.5). This is E's top slot at station 10 from its end. |
| `ab_drive_corner_idler_{bolt,roof,floor}` | socket / surface / surface | `m5-clearance-hole` female; `m5-axle-stack-face` neutral | K at (−15.372·s, −25.5). The idler sits zo ± 4.5. |
| `ab_drive_backside_{bolt,roof,floor}` | socket / surface / surface | as above | Q at (45·s, yq). The stack sits zo ± 5. |
| `ab_drive_pass_{bolt,roof,floor}` | socket / surface / surface | as above | S at (−1.852·s, ys). The stack sits zt ± 5. |

The bolts sit on each roof arm (roof + 3) and take `bhcs-m5x16`.

**Gate results.** The render-time frame gate passes all sixteen interfaces at the defaults and both presets: 48 of 48. The cartridge uses only size keys already in the pinned keystone.

**Proof.** The gantry's round-2 proof is `claudedocs/digital-twins-mes-2026-10-02/phase6/p6gantry-v2-paths.assembly.json`. It contains:
- both belt paths, each 1682.29 mm between the X-carriage clamps, with planarity 0 and length spread 0 over the sweep;
- a `--collision` run at home, every limit and the sweep;
- the four XY corners checked separately.

**Not modelled:**
- the belt;
- the motor's wiring;
- squaring adjustment (guide p. 122).

## Presets

- **Left (B) Drive, 350 Gantry:** the defaults.
- **Right (A) Drive, 350 Gantry:** mirrored. The render check may note that this preset has the same volume as the defaults. That is expected: it compares volume only.

## Graph twin

`ab-drive.graph.json` is a node-graph twin of `main.py` (graph format 1.1). It has the same parameters, the same derivations (clamps as min/max ternary pairs) and the same operations in the same order.
- **Declaration.** The mode declares it as `graph_file` next to the script.
- **Hands.** The belt levels and rear runs are ternaries on `mirrored`. The right (A) drive is the script's `body.mirror("YZ")`: a `reflect` YZ chosen by `select` on `mirrored`.
- **Frozen values.** The three roof arms (`_bar`) take their lengths and angles from `hypot`/`atan2`, which the expression dialect does not have. Their inputs are the script's conventions (the post centres, `K_XY`, `U_Q`, `U_S`, the rear runs) and `mirrored` only, so `k_len`, `k_ang`, `q_len`, `q_ang`, `s_len` and `s_ang` are computed from the script's conventions by hypot/atan2; frozen, as exact float64 literals (a ternary on `mirrored` where they depend on it). No user-editable parameter reaches them. If those conventions change in `main.py`, parity fails at every preset, so drift cannot pass unnoticed.
- **Verification.** `y4d-spec check --render --parity` compares the two at the defaults and at every preset; they agree to 0.000000 mm.
- **Which one renders.** `main.py` stays the source the platform renders and the oracle the graph is checked against. A script retires only after parity holds across the nightly sweep (owner decision D5, 2026-10-04).

## Hyperobject Profile

- **Domain:** industrial.
- **Material awareness:** `tolerance_by_material`.
- **Societal benefit:** an open, printable A/B drive for stacked-belt CoreXY gantries. It takes a standard NEMA 17, a GT2 pulley and idler, F695 bearings and M5 hardware, and its pulley wrap follows a cited teeth-in-mesh rule.
- **License:** CERN-OHL-W-2.0.

## Engine notes

- **Engine:** CadQuery (`main.py`), one body.
- **Sandbox-safe:** it reads `PARAM(lambda: name, default)`, dispatches on `target_part`, and assigns the solid to `result`.

## Resumen (es)

Unidad de tracción A/B impresa para un pórtico CoreXY con dos bandas apiladas (tipo 2.4):
- **Montaje:** se asienta en el extremo trasero de un perfil Y del pórtico y alcanza la viga trasera, sujeta con tuercas en T M5. Un NEMA 17 cuelga bajo su placa, por dentro del perfil.
- **Banda propia:** abraza la polea GT2 de 20 dientes 126° gracias a una pila F695 por el dorso. La regla citada (SDP/SI §13.3) pide al menos 6 dientes engranados, es decir ≥ 108°. Una polea dentada de esquina la gira hacia el tramo exterior.
- **La otra banda:** una pila F695 de paso la gira en el otro nivel.
- **Versión 2.0.0:** cambio incompatible.

Es un diseño original. La guía de armado de la Voron 2.4r2 (GPL-3.0) se cita solo por página (pp. 73–80, 85–87, 95, 125–127); no se copia su geometría. Licencia CERN-OHL-W-2.0.

**Gemelo de grafo.** `ab-drive.graph.json` es un gemelo en grafo de nodos de `main.py` (formato 1.1): los
mismos parámetros, las mismas derivaciones y las mismas operaciones en el mismo orden. Las longitudes y ángulos de los tres brazos (`_bar`) se calculan a partir de las convenciones del script con hypot/atan2 y quedan congelados como literales float64 exactos (un ternario sobre `mirrored`); ningún parámetro editable los alcanza.
`y4d-spec check --render --parity` los compara en los valores por defecto y en cada preset, y
coinciden a 0.000000 mm. `main.py` sigue siendo la fuente que se renderiza y el oráculo
(decisión D5).
