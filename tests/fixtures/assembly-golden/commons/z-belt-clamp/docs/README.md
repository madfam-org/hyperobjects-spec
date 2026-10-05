# Z Belt Clamp

A printed clamp generated with **CadQuery** (B-Rep). It holds **both ends of a 9 mm GT2 Z
belt** on a gantry built from **2020 extrusion**, with no screws on the belt. One **M5 T-nut**
and a slot tongue fix it to the extrusion.

Each end of the belt goes down a jaw's slot, round a post and back up beside itself. The two
plies lock tooth into tooth, and the belt's pull tightens the fold:
- the **upper jaw** takes the end coming down from the top-corner idler;
- the **lower jaw** takes the end coming up from the Z drive.

Both jaws lie on one line, so the belt runs straight past the gantry.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and configurator:
[Yantra4D](https://app.yantra4d.com).

> **Original design.** The functional brief comes from a Voron 2.4-class printer's gantry.
> It is cited by page and section only, from the *Voron 2.4r2 build guide*, version
> 2023-07-04 (VoronDesign/Voron-2 @ `a192410`, GPL-3.0):
> - p. 111: the Z belt is a 9 mm GT2 belt, clamped on the gantry, at least 1200 mm cut for
>   the 350;
> - pp. 117 and 120: the top belt clamp is tightened on the pulled belt end;
> - pp. 118–119: the routing, from the gantry down round the Z drive pulley, up over the top
>   idler and back down to the gantry;
> - p. 121: four Z belts.
>
> The Voron clamps the belt with serrations under a screwed part. This clamp does not: it
> folds each end round a post, teeth into teeth. No Voron geometry, STL or CAD was copied,
> traced or derived. It is licensed CERN-OHL-W-2.0.

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **Z Belt Clamp** | `z_belt_clamp` | The single clamp, symmetric about its slot line. |

## Parameters

| Parameter | Default | Notes |
| :--- | :--- | :--- |
| `jaw_length` | 14 mm | The straight slot from the end face to the post's axis: the length of belt that locks tooth into tooth. |
| `post_d` | 6 mm | The post the belt folds round. The pocket clears it by one belt height plus 0.3. |
| `slot_w` | 2.4 mm | Two plies tooth into tooth are 2 × 1.52 − 0.76 = 2.28 mm thick (Gates 2MR). 2.4 leaves 0.12. |
| `base_t` | 3.5 mm | The floor under the slots. The belt's mid-plane stands `base_t` + 4.8 mm off the extrusion face. |

### Sources and conventions

**Cited facts**
- **The belt** (Gates PowerGrip GT 2MR belting, design manual 17195, p. 90): height B 1.52,
  tooth height T 0.76. The Z belt is 9 mm wide (guide p. 111).
- **M5x10 BHCS** (ISO 7380-1, Keller & Kalmbach): d 5, l 10, dk 9.5.
- **MISUMI HFS5 slots:** a 6 mm opening with 2 mm lips.

**Conventions (not sourced)**
- 0.3 mm each side of the belt's width in the slot depth, so the slots are 9.6 deep.
- 0.3 mm of radial room for one ply round the post.
- Holes: a Ø5.5 clearance hole and a Ø10.5 counterbore. The head seat is 4.5 mm off the
  mount face, so 5.5 mm of the screw passes into the T-nut.
- A 5.8 mm tongue, as in roller-bracket.
- The solid middle that carries the screw is 14.5 mm long.
- Walls: 2 mm between the middle and each pocket, and 3 mm round the pockets.

## Interfaces

Model frame:
- **Origin:** on the mount face, on the screw axis.
- **+x:** along the belt (the slot line).
- **+y:** across it.
- **+z:** out of the extrusion face, through the block.

The block is symmetric about its slot line, so either wall can take the belt's back. The
belt interfaces are framed on the −y wall. Turned 180° about z on its slot, which the tongue's
symmetry 2 allows, the clamp presents the other wall and swaps its upper and lower jaws.

| Interface | Type | Polarity / key / symmetry | Where |
| :--- | :--- | :--- | :--- |
| `z_belt_clamp_mount` | `bolt_pattern` | male, `m5-screw-joint`, 0 | On the mount face, on the screw axis. The normal points into the extrusion. This mates `tnut-2020-m5.thread`. |
| `z_belt_clamp_mount_head` | `socket` | female, `m5-clearance-hole`, 0 | The counterbore floor, 4.5 mm off the mount face. This mates a `bhcs-m5x10.head_seat`. |
| `z_belt_clamp_key` | `profile` | male, `tslot-2020-6mm`, 2 | The mount face, on the screw axis. The tongue runs along the slot. |
| `z_belt_clamp_upper` | `profile` | female, `z-belt-gt2-9mm-clamp`, 2 | The +x end face at x = 9.25 + (`post_d` + 3.64)/2 + `jaw_length` (28.07 at the defaults), y = −`slot_w`/2, at the belt's mid-width z = `base_t` + 4.8. The normal is +x, toward the incoming belt. This mates `gt2-belt-9mm.end_a` or `end_b`. |
| `z_belt_clamp_lower` | `profile` | female, `z-belt-gt2-9mm-clamp`, 2 | The −x end face, mirrored: normal −x. |

**Gate results.** The render-time frame gate checks all five interfaces at the defaults and at
every preset: 25 of 25 pass.

**Closure.** The keystone test `tests/test_catalog_z_drive.py` mounts this clamp on a 2020
beam with its T-nut and M5x10, and puts a `gt2-belt-9mm` end in each jaw. The two belt
entrances differ only along the slot line, and each belt leaves its jaw outward.

**For a belt path** (ASM-1 §9), the two belt interfaces are the path's anchors. They sit on
the wall the belt's back bears on. The belt's pitch line lies inside the belt from that wall
by B − T − U; U is not cited in the catalog yet.

**Not modelled:** the folded tail inside the jaw.

## Presets

- **Standard.** The defaults, stated explicitly.
- **Long Jaws.** `jaw_length` 20, for more locked belt.
- **Belt Further Out (6 mm floor).** `base_t` 6, which moves the belt's mid-plane 2.5 mm
  further off the extrusion face.
- **Gentle Fold.** A Ø8 post and a 2.6 mm slot, for a stiffer belt.

## Graph twin

`z-belt-clamp.graph.json` is a node-graph twin of `main.py` (graph format 1.1). It has the same parameters, the same derivations and the same operations in the same order. Each `_box` is a centred `box` translated to its centre, each `_cyl_z` an XY `profile_circle` extruded and translated to its start, each clamp a min/max ternary pair in `derived`, and the jaw slot's `min`/`max` ends ternaries; the jaw loop is unrolled (+x, then −x) and each pocket ring is the pocket cylinder cut by the post cylinder, as in the script. The constants keep `main.py`'s names, values and sources.
- **Declaration.** The mode declares it as `graph_file` next to the script.
- **Verification.** `y4d-spec check --render --parity` compares the two at the defaults and at every preset (`standard`, `long_jaws`, `belt_further_out`, `gentle_fold`); they agree to 0.000000 mm.
- **Which one renders.** `main.py` stays the source the platform renders and the oracle the graph is checked against. A script retires only after parity holds across the nightly sweep (owner decision D5, 2026-10-04).

## Hyperobject Profile

- **Domain:** industrial.
- **Material awareness:** `tolerance_by_material`. The slot width is exposed so the fold's
  grip can be tuned.
- **Societal benefit:** an open, printable belt clamp. It holds a standard 9 mm GT2 belt with
  no screws or proprietary parts, and its interfaces are machine-checked against the
  extrusion and the belt.
- **License:** CERN-OHL-W-2.0.

## Engine notes

- **Engine:** CadQuery (`main.py`), one body.
- **Sandbox-safe:** it reads `PARAM(lambda: name, default)`, dispatches on `target_part`, and
  assigns the solid to `result`.
- **Keystone needed:** a keystone with the Z belt key `z-belt-gt2-9mm-clamp` (lane P6-ZBED).
  Until `SPEC_PIN` moves past it, `y4d-spec check` reports that size key as unknown.

## Resumen (es)

Abrazadera impresa que sujeta ambos extremos de una banda Z GT2 de 9 mm en un pórtico de
perfil 2020, sin tornillos sobre la banda:
- **Montaje:** una tuerca en T M5 y una lengüeta de ranura la fijan al perfil.
- **Mordazas:** cada extremo baja por una ranura, rodea un poste y vuelve junto a sí mismo;
  las dos capas se traban diente con diente.
- **Línea:** ambas mordazas están en una línea, así que la banda pasa recta junto al
  pórtico.

Es un diseño original. La guía de armado de la Voron 2.4r2 (GPL-3.0) se cita solo por página
(pp. 111, 117–121); no se copia su geometría. Licencia CERN-OHL-W-2.0.
