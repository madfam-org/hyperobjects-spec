# X Carriage

A printed **X carriage** for a CoreXY gantry whose two **6 mm GT2 belts run stacked on two
levels**, a 2.4-class "flying gantry". It is generated with **CadQuery** (B-Rep) and does
three jobs:

- it bolts to an **MGN12H block** on the X rail;
- it holds **all four belt ends** (both ends of belt A and of belt B), with no screws on the
  belt;
- it presents a **toolhead face**: four M3 heat-set inserts on a 20 mm square. The commons
  `toolhead-proxy`, or any toolhead with that pattern, bolts to it.

Each belt end goes down a slot two plies wide, round a post and back beside itself. The plies
lock tooth into tooth, and the belt's pull tightens the fold. The upper level's jaws open
upward; the lower level's open downward, into a window under the carriage. Each fold therefore
goes in from outside.

Where the belts are is the gantry's business, so it is all parameters:
- the belt line's depth behind the block face;
- each belt's level;
- the jaws' x;
- which way the teeth face.

The defaults are the commons gantry's.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and configurator:
[Yantra4D](https://app.yantra4d.com).

> **Original design.** The functional brief comes from a Voron 2.4-class gantry. It is cited by
> page and section only, from the *Voron 2.4r2 build guide*, version 2023-07-04
> (VoronDesign/Voron-2 @ `a192410`, GPL-3.0):
> - p. 101: the X axis runs on an MGN12 rail centred on the X beam;
> - pp. 129–130: the X carriage takes heat-set inserts;
> - p. 131: both A/B belts are 6 mm GT2, clamped in the X carriage, teeth away from the
>   extrusion;
> - pp. 139–141: the belt ends are captured at the carriage and pulled tight there, equal
>   lengths on both belts.
>
> The Voron clamps the belt ends under screwed printed parts. This carriage does not: it folds
> each end round a post, teeth into teeth, the principle of the commons `z-belt-clamp`. No
> Voron geometry, STL or CAD was copied, traced or derived. It is licensed CERN-OHL-W-2.0.

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **X Carriage** | `x_carriage` | The single carriage: a front plate on the block and a tower carrying the four jaws. |

## Parameters

| Group | Parameter | Default | Notes |
| :--- | :--- | :--- | :--- |
| Gantry | `belt_line` | 23 mm | From the MGN12H's top face back to the belts' pitch line. |
| Gantry | `belt_a_level` | 38 mm | The A belt's mid-plane above the MGN12H's centre. |
| Gantry | `belt_b_level` | 22 mm | The B belt's mid-plane above the MGN12H's centre. |
| Gantry | `clamp_x` | 20 mm | The jaw entrances at ±`clamp_x`. This is also the carriage's half-width at the belt levels. |
| Gantry | `teeth_toward_toolhead` | off | Off: the belts' backs face the toolhead (+z). On: the reverse. |
| Jaws | `jaw_length` | 12 mm | The slot from the entrance to the post's axis: 6 teeth locked tooth into tooth. |
| Jaws | `post_d` | 5 mm | The post each end folds round. The pocket clears it by one belt height plus 0.3. |
| Jaws | `slot_w` | 2.4 mm | Two plies tooth into tooth are 2 × 1.52 − 0.76 = 2.28 thick (Gates 2MR); 2.4 leaves 0.12. |
| Toolhead face | `plate_t` | 8 mm | From the block face to the toolhead face. At 8, M3x8 SHCS hold the block (3.5 counterbore + 3.5 into HIWIN's M3x3.5 thread). It is also part of the toolhead's forward reach; see the note below. |
| Toolhead face | `toolhead_y` | 30 mm | The toolhead pattern's centre above the block's centre, clear of the block's screws. The plate grows upward to carry the pattern when it sits above the jaws. |

The gantry defaults follow the commons gantry of lane P6-GANTRY, round 2. On that gantry the X
beam (D) rides above the C extrusions, its centre 32 above their top faces, so the block's centre
is at gantry z 32. Relative to that gantry, the defaults are:
- the MGN12 on the X beam's front face, centred on it (guide p. 101);
- the belts' pitch line over the beam's centre line, 23 behind the block's top face;
- B at gantry z 54 and A at gantry z 70, which is 22 and 38 above the block's centre;
- the clamp points at ±20;
- the teeth facing the gantry's back (+y), away from the carriage's plate.

These are that gantry's conventions, not the guide's numbers.

### Sources and conventions

**Cited facts**
- **MGN12H** (HIWIN MG series): W 27, L 45.4, B 20 × C 20, M3x3.5; rail 12 × 8.
- **The belt** (Gates PowerGrip GT2 2MR, Pfeifer's 2MR/PGGT2 row): B 1.52, T 0.76.
  SDP/SI Technical Section, Table 4: U 0.254. The pitch line lies B − T − U = 0.506 inside the
  back face. The A/B belts are 6 mm wide (guide p. 131).
- **M3 SHCS** (ISO 4762, Keller & Kalmbach): dk 5.5, k 3.
- **Heat-set inserts in the X carriage** (guide pp. 129–130).

**Conventions (not sourced)**
- Slot fit: 0.3 mm each side of the belt's width, and 0.3 mm radial room for a ply round the
  post.
- A 2.4 mm rib between the levels' slots, so the levels must be at least 9 apart.
- A 1.2 mm top wall and a 2.5 mm wall behind the pockets.
- The tower's underside stands 1 mm above the block's top edge. With the rail centred on a
  2020 face, that is 4.5 above the beam's top face.
- The plate covers the block's length plus 0.5 each end (half-width 23.2) and reaches 8.5 below
  it.
- Holes: Ø3.4 M3 clearance; Ø6.5 × 3.5 counterbores; Ø4.0 × 6 insert holes.

**The toolhead's reach (a convention).** With `belt_line` 23 and `plate_t` 8, the toolhead face
stands 31 ahead of the X beam's centre line. The commons `toolhead-proxy` puts its nozzle 12
further forward (its `nozzle_reach`), so the tip is **43.0 ahead of the beam's centre line**,
which is also the Y blocks' centre. That reach is a convention: it maps the machine's Y 0..350
(Voron's Klipper reference configuration, `Voron2_Octopus_Config.cfg` lines 95 and 107–108)
onto the bed plate, whose front edge is 38 behind the frame's front face (guide p. 60). Change
`plate_t` and that reach moves with it.

**Tension (guide p. 141).** The belt is tensioned at the carriage by re-folding: pull the end,
then put the fold one tooth further in. That is 2 mm of belt per step, per end, and each belt
has two ends. Both belts are cut to one length and routed equal, so the same number of teeth
per jaw gives equal tension.

**Teeth (guide p. 131).** On the commons gantry, the routing puts each belt's teeth toward the
X beam's far side (−z), away from the carriage's plate and the rail face. The backs bear on the
jaws' front walls.

## Interfaces

Model frame:
- **Origin:** the centre of the MGN12H's top face, the carriage's mount face.
- **+x:** along the rail.
- **+y:** up.
- **+z:** out of the block face, toward the toolhead.

| Interface | Type | Polarity / key / symmetry | Where |
| :--- | :--- | :--- | :--- |
| `x_carriage_block` | `bolt_pattern` | male, `mgn12-carriage`, 4 | The plate's back face, at the origin. The normal is −z, into the block. This mates `mgn12h-carriage.top`. |
| `x_carriage_toolhead` | `bolt_pattern` | female, `toolhead-mount-20x20-m3`, 4 | (0, `toolhead_y`, `plate_t`): the front face. The normal is +z. This mates `toolhead-proxy.toolhead_proxy_mount`. |
| `x_carriage_belt_a_xp` | `profile` | female, `gt2-belt-6mm`, 1 | (`clamp_x`, `belt_a_level`, −`belt_line`): the A belt's +x jaw entrance, on the pitch line at mid-width. The normal is +x, toward the incoming belt. The x_axis points to the belt's back. |
| `x_carriage_belt_a_xn` | `profile` | female, `gt2-belt-6mm`, 1 | (−`clamp_x`, `belt_a_level`, −`belt_line`): as above, normal −x. |
| `x_carriage_belt_b_xp` | `profile` | female, `gt2-belt-6mm`, 1 | (`clamp_x`, `belt_b_level`, −`belt_line`), normal +x. |
| `x_carriage_belt_b_xn` | `profile` | female, `gt2-belt-6mm`, 1 | (−`clamp_x`, `belt_b_level`, −`belt_line`), normal −x. |

**The belt interfaces are ASM-1 §9 path anchors.**
- **In a path.** An open belt path starts at one of a belt's two jaws and ends at the other. The
  pitch-line length is measured from these origins.
- **Mating a belt end.** They also mate a `gt2-belt-6mm` end (`end_a` / `end_b`, male, framed on
  the pitch line).

**Gate results.** The render-time frame gate checks all six interfaces at the defaults and at
each of the four presets: **30 of 30 pass**.

**X budget.** These are the carriage's half-widths along x, by height in the model frame:

| Part | Half-width | Extent |
| :--- | :--- | :--- |
| Front plate | 23.2 | y from −22 to the top, in front of the block face |
| MGN12H block | 22.7 | y ±13.5 (catalog) |
| Tower and jaws | `clamp_x` | y from 14.5 to the upper level + 4.5, z from 0 back to the belt line + 7.5 |

The belt tails beyond the jaw entrances are not modelled.

**At the commons gantry's defaults** the lower (B) level's slots start 4.2 above the tower's
underside, so the window the B folds go in through is 4.2 tall. Fold the B ends before the
carriage goes on the block, or use a gantry with the B level higher.

## Presets

| Preset | Values | Notes |
| :--- | :--- | :--- |
| **Commons Gantry (350)** | the defaults, stated explicitly | It renders the same volume as the defaults by construction. |
| **Compact Jaws** | `clamp_x` 16, `jaw_length` 9 | 4.5 teeth locked; the carriage is 4 mm narrower at the belt levels. |
| **Gentle Fold** | Ø6 post, 2.6 slot, `jaw_length` 11 | — |
| **Teeth Forward, 10 mm Plate** | `teeth_toward_toolhead` on, `plate_t` 10 | — |

## Hyperobject Profile

- **Domain:** industrial.
- **Material awareness:** `tolerance_by_material`. The slot width is exposed so the fold's grip
  can be tuned.
- **Societal benefit:** an open, printable X carriage for stacked-belt CoreXY gantries:
  - it holds standard 6 mm GT2 belts with no screws on the belt;
  - it takes an off-the-shelf MGN12H;
  - it follows the gantry through its parameters;
  - its six interfaces are machine-checked against the rendered part.
- **License:** CERN-OHL-W-2.0.

## Engine notes

- **Engine:** CadQuery (`main.py`), one body.
- **Sandbox-safe:** it reads `PARAM(lambda: name, default)`, dispatches on `target_part`, and
  assigns the solid to `result`.
- **Keystone needed:** a keystone with the key `toolhead-mount-20x20-m3` (hyperobjects-spec#53,
  lane P6-XCAR). Until `SPEC_PIN` moves past it, `y4d-spec check` reports that key as unknown.

## Resumen (es)

Carro X impreso para un pórtico CoreXY con dos bandas GT2 de 6 mm apiladas:
- **Montaje:** se atornilla a un bloque MGN12H.
- **Bandas:** sujeta los cuatro extremos de banda sin tornillos sobre la banda. Cada extremo
  baja por una ranura de dos capas, rodea un poste y vuelve junto a sí mismo, de modo que las
  capas se traban diente con diente.
- **Tensado:** se dobla la banda un diente más.
- **Cara de cabezal:** cuatro insertos M3 en un cuadrado de 20 mm.
- **Parámetros:** la línea de banda, los niveles, la x de las mordazas y el lado de los
  dientes, para seguir al pórtico.

Es un diseño original. La guía de armado de la Voron 2.4r2 (GPL-3.0) se cita solo por página
(pp. 101, 129–131, 139–141); no se copia su geometría. Licencia CERN-OHL-W-2.0.
