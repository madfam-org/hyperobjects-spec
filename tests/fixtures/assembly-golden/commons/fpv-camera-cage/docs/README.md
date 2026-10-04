# FPV Camera Cage

**Protects and angles a micro FPV camera**, generated with **CadQuery** (B-Rep).
The camera drops into a cradle pocket sized to the standard form factor
(**nano 14 mm, micro 19 mm, mini 21 mm**) and the whole housing tilts to a chosen
up-angle. The cage sits **ahead of the frame**: two ears reach back along the
**outside** of the frame's camera side plates and bolt through them on the camera
side-screw axis.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and
configurator: [Yantra4D](https://app.yantra4d.com).

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **Protective Cage** | `cage` | Full shell + a rim frame and diagonal guard strut across the open (cable) side; the lens looks out through the aperture in the floor. |
| **Tilt Bracket** | `tilt_mount` | The shell only (open front) on the tilting mount — lighter, still cradles the cam. |
| **Naked Mount** | `naked_mount` | A thin backing plate with the lens aperture and board-mount holes for a "naked"/board cam. |

## Parameters

| Group | Parameter | Default | Notes |
| :--- | :--- | :--- | :--- |
| Camera | `cam_size` | micro | Form factor: `nano` 14, `micro` 19, `mini` 21 mm. |
| Camera | `tilt` | 30° | Up-tilt angle (higher = faster flight). |
| Camera | `cam_len` | 20 mm | Camera body length, lens face to back (micro class 19 × 19 × 20). The pocket takes the whole body. |
| Camera | `lens_hole` | on | Cut the lens aperture in the pocket floor. |
| Housing | `wall` | 2.0 mm | Cradle wall thickness. |
| Housing | `cam_clear` | 0.4 mm | Per-side clearance around the cam. |
| Frame Mount | `base_h` | 6.0 mm | Mount base height below the cradle. |
| Frame Mount | `mount_width` | 24 mm | Spacing across the OUTSIDE of the frame's camera side plates (19 mm bay + 2 × 2.5 mm plates); the ears' inner faces sit exactly here. |
| Frame Mount | `ear_reach` | 12 mm | How far behind the housing's pivot the ear screws sit (never less than 4 mm behind the tilted housing). Set it past how far your side plates reach ahead of their camera screw holes. |
| Frame Mount | `tab_thick` / `tab_hole_d` | 3.0 / 2.2 mm | Ear thickness and screw hole (M2). |

## Interfaces

The cradle pocket is derived directly from `cam_size` (plus `cam_clear` per side
and `wall`), so a housing generated for a *micro* cam accepts a 19 mm micro cam.
The camera seats **lens-first** on the pocket floor and looks out through the
aperture; the pocket is `cam_len + 2·cam_clear` deep, so the body never stands
proud of the open side. The whole housing is rotated up by `tilt` about the pitch
axis (through the centre of the open side) before it is joined to the base, and
the tilted pocket is cut again from the finished part, so neither the base nor
the guard bars reach where the camera sits.

The two **ears** stand `mount_width` apart (inner faces) and run from the base
back past the housing to an M2 hole on the pivot's height, `ear_y` behind it:
`ear_y = max(ear_reach, out_h/2·sin(tilt) + bar·cos(tilt) + 4)`. The base widens
to the ears' outer faces, so the ears always share solid with it.

## Presets

- **Micro Cage 30°** — the common freestyle setup.
- **Nano Tilt 40°** — light racing bracket for a nano cam.
- **Mini Naked 20°** — flat board-cam mount for a mini sensor.
- **Micro Cage 0°** — level camera.
- **Mini Cage 55° (long ears)** — the steepest tilt on the catalog frame's 24 mm plate spacing, with `ear_reach` 20 so the tilted housing clears the side plates' land round the screws (at the default 12 it clips them at 55°). For a 20 mm bay (outer spacing 25) set `mount_width` 25.

## Hyperobject Profile

- **Domain:** commercial
- **CDG interfaces:**
  - **FPV Camera Cradle** (`pocket`, *FPV micro/nano cam — nano 14 / micro 19 /
    mini 21 mm*) — the cradle pocket, defined by `cam_size`, `cam_clear`, `wall`.
    Any camera of the selected form factor drops in.
  - **Frame Mount Ears** (`bolt_pattern`, *internal*) — the two ears and their
    screw holes, defined by `mount_width`, `tab_thick`, `tab_hole_d`, `ear_reach`.
  - **Mating frames (ASM-1 v1.1):**
    - `cage_cradle_floor`, `tilt_mount_cradle_floor` — the pocket floor (the
      closed wall with the lens aperture), normal toward the open side, tilted
      with the housing (`let`: camera width from `cam_size`, pocket depth
      `cam_len + 2·cam_clear`, clamped tilt; degree trig). Female, symmetry 4,
      size key from `cam_size` (`fpv-camera-nano-14mm`, `fpv-camera-micro-19mm`,
      `fpv-camera-mini-21mm`). The camera seats here by its **front (lens) face**
      — the catalog camera's `front_face`.
    - `<part>_ear_left`, `<part>_ear_right` on all three parts — each ear's inner
      face on its screw axis, at `(±mount_width/2, ear_y, 0)`, normal toward the
      side plate, `x_axis` toward the lens side. Male (the ear carries the screw
      head), symmetry 0, size key `fpv-camera-side-plate-screw`. They mate the
      frame catalog's `camera_plate_left_outer` / `camera_plate_right_outer` at
      `angle_deg` 0 (cage level, ahead of the frame); the frame's outer faces
      stand bay + 2 × plate apart, so `mount_width` must be that spacing (24 mm
      for the 19 mm / 2.5 mm class). Needs hyperobjects-spec with the side-plate
      outer faces (O1(a)).
  - **Fit note.** The catalog cannot see where the frame's side plates end: set
    `ear_reach` so the housing clears the plates' front edges.
- **Material awareness:** `tolerance_by_material` is declared — the cam clearance
  and wall are exposed so the pocket fit can be tuned per material/printer.
- **Societal benefit:** the camera is the most-crashed and most-swapped part on
  an FPV craft; on-demand cages sized to the exact cam and tilt keep the picture
  level and the lens protected.
- **License:** CERN-OHL-W-2.0

## Engine notes

- Engine: **CadQuery** (`main.py`). Exports STL / 3MF / STEP / GLB / GLTF / OBJ.
- Self-contained (sandbox-safe): parameters read via `PARAM(lambda: name,
  default)`; `target_part` dispatches which part to build; the final solid is
  assigned to `result`. Base fillets are clamped and guarded. All modes render
  **watertight** in well under 20 s.
