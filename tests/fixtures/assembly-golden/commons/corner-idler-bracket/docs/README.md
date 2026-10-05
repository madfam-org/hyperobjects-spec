# Corner Idler Bracket

A printed bracket generated with **CadQuery** (B-Rep). It carries a **GT2 toothed idler** in
the inside top corner of a **2020 extrusion frame joined by blind joints**: an upright with two
horizontals butted on its faces, their tops flush with it. The bracket bolts to one top
horizontal's inner face with **two M5 T-nuts**. It bears on the side of the perpendicular
horizontal and, with a heel below that horizontal, on the upright, keyed into both slots. The idler turns on an
**M5x30 button head screw** in a fork that is open at the bottom, so the belt leaves the idler
downward on both sides. Right- and left-hand versions.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and configurator:
[Yantra4D](https://app.yantra4d.com).

> **Original design.** The functional brief comes from a Voron 2.4-class printer's Z idler.
> It is cited by page and section only, from the *Voron 2.4r2 build guide*, version
> 2023-07-04 (VoronDesign/Voron-2 @ `a192410`, GPL-3.0):
> - p. 48: a GT2 20-tooth, 9 mm idler on an M5x30 BHCS;
> - p. 49: two M5 T-nuts in a top extrusion, and the idler pressed into the top corner;
> - p. 50: four of them, the printed parts mirrored;
> - pp. 10 and 14–15: the frame's blind joints.
>
> No Voron geometry, STL or CAD was copied, traced or derived. This bracket's shape comes from
> the cited facts below. It is licensed CERN-OHL-W-2.0.

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **Corner Idler Bracket** | `corner_idler` | The single bracket. `mirrored` builds the opposite hand. |

## Parameters

| Group | Parameter | Default | Notes |
| :--- | :--- | :--- | :--- |
| Idler | `idler_width` | 14 mm | The idler's width from flange to flange. 14 is the Gates G2GT-I-20-9 9 mm-belt idler (catalog `gt2-idler-20t-9mm`). 10 is a 6 mm-belt idler. |
| Idler | `idler_od` | 18 mm | The idler's largest diameter. The pocket clears it by 1 mm. |
| Idler | `idler_clear` | 0.5 mm | The axial gap on each side of the idler, between the arms. |
| Idler | `idler_offset` | 13 mm | The axle's position along the horizontal, measured from the corner plane. |
| Idler | `idler_drop` | 24 mm | How far the axle sits below the top horizontals' slot centre. The frame top is 10 mm above that centre. |
| Idler | `front_arm` | 5 mm | The arm under the axle screw's head. The rear arm takes the rest of the screw's 30 mm. |
| Frame Mount | `mount_grip` | 24.5 mm | The distance from the mount face to the M5x30 head seat. 30 − 24.5 = 5.5 mm passes the face into the T-nut. |
| Frame Mount | `mount_pitch` | 20 mm | The spacing of the two mount screws. A T-nut is 15 mm long. |
| Frame Mount | `heel_reach` | 18 mm | How far the heel reaches past the corner, over the upright's 20 mm face. |
| Frame Mount | `mirrored` | off | Builds the left-hand bracket, reflected in x. |

### Sources and conventions

**Cited facts**
- **The bracket's depth is the M5x30's length.** ISO 7380-1 M5x30, from Keller & Kalmbach datasheet 157380530: d 5, l 30, dk 9.5, k 2.75. The 30 mm depth puts the axle screw's tip on the mount face.
- **Slot facts.** MISUMI HFS5 "T Slot Dimensions" (p2_0513): a 6 mm opening with 2 mm lips, and the floor 6 mm down. The tongues are 2 mm deep. The mount screw passes 5.5 mm, which clears the lip and stops short of the floor.
- **The rear-arm pilot is Ø4.2.** That is the hole MISUMI taps M5 in the 2020's end (p2_0681). The guide's XY idlers are likewise screwed into plastic (pp. 98 and 100).
- **T-nut length.** MISUMI HNTAP5-5 nuts are 15 mm long and have a 5 mm thread, so `mount_pitch` is at least 16.

**Conventions (not sourced)**
- Holes are Ø5.5, a 0.25 mm clearance per side.
- Counterbores are Ø10.5.
- Tongues are 5.8 mm wide, as in roller-bracket.
- The pocket clears the idler by 1 mm radially.
- There is 7 mm of arm under the axle.
- The heel sits 0.5 mm below the perpendicular horizontal.

## Interfaces

Model frame:
- **Origin:** on the inside corner line, at the top horizontals' slot-centre height.
- **+x:** along the horizontal the bracket mounts on, away from the corner.
- **+y:** out of that horizontal's inner face, into the frame.
- **+z:** up. The frame top is at z = 10.
- **Mirroring:** `mirrored` reflects x. Every frame reads `s = 1 − 2·mirrored`.

| Interface | Type | Polarity / key / symmetry | Where |
| :--- | :--- | :--- | :--- |
| `corner_idler_mount_a`, `_b` | `bolt_pattern` | male, `m5-screw-joint`, 0 | On the mount face, on the screw axes at x = 10 and 10 + `mount_pitch`. The normal points into the horizontal. These mate the catalog `tnut-2020-m5.thread`. |
| `corner_idler_mount_a_head`, `_b_head` | `socket` | female, `m5-clearance-hole`, 0 | The counterbore floors, at y = `mount_grip`. These mate a `bhcs-m5x30.head_seat`. |
| `corner_idler_corner_key` | `profile` | male, `tslot-2020-6mm`, 2 | The corner end face at (0, 10, 0). The tongue sits in the perpendicular horizontal's slot. It mates that extrusion's `slot_{face}_a` at its default `slot_station_mm` of 10. |
| `corner_idler_upright_key` | `profile` | male, `tslot-2020-6mm`, 2 | The heel face at (−10, 0, −20). The tongue sits in the upright's slot. It mates the upright's `slot_{face}_b`, with that extrusion's `slot_station_mm` set to 30. |
| `corner_idler_idler_bolt` | `socket` | female, `m5-clearance-hole`, 0 | The front arm's outer face, on the axle at (`idler_offset`, 30, −`idler_drop`). This mates `bhcs-m5x30.head_seat`. The screw's `journal` (`journal_offset_mm` 5.5 = `front_arm` + `idler_clear`) carries `gt2-idler-20t-9mm.bore`. |

**Gate results.** The render-time frame gate checks all seven interfaces at the defaults and at
every preset, mirrored ones included: 35 of 35 pass.

**Top-corner closure.** The keystone test `tests/test_catalog_m5_idlers.py` closes the whole top
corner:
- an upright, and two horizontals on it by blind joints;
- a T-nut, then this bracket keyed into both other slots;
- the M5x30, then the idler.

That closure is the assembly A's top corner should use.

**Not modelled:** the belt, and the blind joints' access holes.

## Presets

- **9 mm Belt Idler, Right-Hand.** The defaults stated explicitly.
- **9 mm Belt Idler, Left-Hand.** The mirrored hand. The render check notes that this preset
  renders "identical to the defaults". That note is expected: the check compares volume only,
  and a reflection keeps the volume. The bounding box moves from x −18…40 to x −40…18.
- **6 mm Belt Idler (10 mm wide).** For an idler 10 mm wide flange to flange; Filastruder's
  Gates 2GT listing gives 10 mm for 6 mm-belt idlers. The OD stays at 18; check yours.
- **Long Drop, Wide T-Nut Spacing.** Left-hand: the axle 36 mm down and 20 mm from the corner,
  with the T-nuts 30 mm apart.

## Graph twin

`corner-idler.graph.json` is a node-graph twin of `main.py` (graph format 1.1). It has the same parameters, the same derivations and the same operations in the same order. Each `_box` is a centred `box` translated to its centre, and each clamp a min/max ternary pair in `derived`. Each `_cyl_y` is an XZ `profile_circle` extruded along +Y (the XZ normal is −Y, so the height is negative), turned −90° about its own axis so the cylinder's seam sits at +Z where `makeCylinder` puts it, then translated into place; the seam decides where the tessellator puts vertices, so without the turn the two meshes differ by 0.0016 mm. `mirrored` is a `select` between the body and its pure YZ `reflect`, as `body.mirror("YZ")`. The constants keep `main.py`'s names, values and sources.
- **Declaration.** The mode declares it as `graph_file` next to the script.
- **Verification.** `y4d-spec check --render --parity` compares the two at the defaults and at every preset (`gates_9mm_right`, `gates_9mm_left`, `belt_6mm_right`, `long_drop_wide_pitch`; the two mirrored presets included); they agree to 0.000000 mm.
- **Which one renders.** `main.py` stays the source the platform renders and the oracle the graph is checked against. A script retires only after parity holds across the nightly sweep (owner decision D5, 2026-10-04).

## Hyperobject Profile

- **Domain:** industrial.
- **Material awareness:** `tolerance_by_material`. The idler clearance is exposed so the fit can
  be tuned.
- **Societal benefit:** an open, printable corner idler for belt machines built on 2020
  extrusion. It uses only off-the-shelf M5 screws, T-nuts and a standard GT2 idler, and its
  interfaces are machine-checked against the frame.
- **License:** CERN-OHL-W-2.0.

## Engine notes

- **Engine:** CadQuery (`main.py`), one body.
- **Sandbox-safe:** it reads `PARAM(lambda: name, default)`, dispatches on `target_part`, and
  assigns the solid to `result`.
- **Keystone needed:** a keystone with the M5 idler catalog (`m5-screw-joint`,
  `m5-clearance-hole`). Until `SPEC_PIN` moves past it, `y4d-spec check` reports those size keys
  as unknown.

## Resumen (es)

Soporte impreso que lleva una polea loca dentada GT2 en la esquina superior interior de un
marco de perfil 2020 con uniones ciegas:
- **Montaje:** se atornilla con dos tuercas en T M5 a la cara interior de un travesaño
  superior.
- **Esquina:** se encaja con lengüetas en la ranura del travesaño perpendicular y, con un
  talón, en la del poste.
- **Polea:** gira sobre un tornillo de cabeza de botón M5x30.

Es un diseño original. La guía de armado de la Voron 2.4r2 (GPL-3.0) se cita solo por página
(pp. 48–50); no se copia su geometría. Licencia CERN-OHL-W-2.0.
