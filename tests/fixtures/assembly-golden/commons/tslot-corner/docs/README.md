# T-Slot Corner Bracket

A parametric corner joiner generated with **CadQuery** (B-Rep) for aluminium
T-slot extrusion (2020 / 2040 / OpenBuilds). The bracket bolts into the
extrusion's T-slots with M5 drop-in nuts on the real 20 mm module grid, with one
fastener centred on each slot's centre-line.

Part of the **Yantra4D Hyperobjects Commons**. Official visualizer and
configurator: [Yantra4D](https://app.yantra4d.com).

## Extrusion table

| Series | Module | Slot | Fastener |
| :--- | :--- | :--- | :--- |
| 2020 | 20 mm | 6 mm | M5 |
| 2040 | 20 mm | 6 mm | M5 |
| 3030 | 30 mm | 8 mm | M6 |
| 4040 | 40 mm | 8 mm | M8 |

The bolt centre lands at `module / 2` from the extrusion corner, i.e. on the
slot centre-line, so a printed bracket registers exactly like a die-cast one.

## Modes

| Mode | Part | Description |
| :--- | :--- | :--- |
| **Two-Way Brace** | `corner_2way` | Flat right-angle plate, one counter-bored M-hole per leg. |
| **Gusseted Brace** | `corner_gusset` | Two-way plate plus a triangular web across the inner angle. |
| **Three-Way Block** | `corner_3way` | Cubic vertex block joining three extrusions (X, Y, Z arms). |

## Parameters

| Group | Parameter | Default | Notes |
| :--- | :--- | :--- | :--- |
| Extrusion | `series` | 2020 | Module + fastener size from the table. |
| Bracket | `thickness` | 6.0 mm | Leg / arm thickness. |
| Bracket | `leg_len` | 30.0 mm | Length of each leg along the extrusion. |
| Bracket | `width` | 20.0 mm | Width across the extrusion face. |
| Bracket | `bolt_dia` | 0.0 mm | Override clearance; 0 = derive from series. |
| Bracket | `fillet_r` | 3.0 mm | Outer-corner radius. |

## Presets

- **2020 Two-Way Brace** — the workhorse inside-corner brace for a 2020 frame.
- **2040 Gusseted Brace** — a reinforced brace for load-bearing 2040 members.
- **3030 Three-Way Vertex** — a cubic block joining three 3030 extrusions.

## Hyperobject Profile

- **Domain:** industrial
- **CDG interfaces:**
  - **T-Slot M5 Bolt Grid** (`profile`, 2020/2040 extrusion — 20 mm module,
    6 mm slot, M5) — the interface, defined by `series`, `leg_len`, `width`,
    `bolt_dia`. Shares the T-slot extrusion standard with `tslot-2020`,
    `featherboard`, and `linear-wheel`.
  - **Mating frames** (two-way and gusseted braces): `<part>_leg_x` and
    `<part>_leg_z` sit on each leg's seat face at the bolt centre, normal
    toward the extrusion, `x_axis` along it; male, symmetry 2, size key
    `tslot-2020-6mm` for 2020/2040.
  - **Three-way block frames:** `corner_3way_arm_x`, `_arm_y` (arm undersides,
    normal −z) and `_arm_z` (the Z arm's back face, normal −x), each at its bolt
    centre, male, symmetry 2, the same `series` size key. The clamp chain
    (bolt override → width floor → cube → arm width) is a `let` block (ASM-1
    v1.1, keystone 0.4.0 or later).
  - **Arm length:** every three-way arm reaches at least 1 mm past its bolt's
    counter-bore rim (`cube + module/2 + head/2 + 1`), so the hole never breaks
    out of the arm end; a longer `leg_len` is kept as given.
- **Material awareness:** `tolerance_by_material` lets the M-clearance be tuned
  per filament so drop-in nuts thread cleanly.
- **Commons license:** CERN-OHL-W-2.0

---

# Soporte de Esquina T-Slot

Una unión de esquina paramétrica generada con **CadQuery** (B-Rep) para perfil
de aluminio T-slot (2020 / 2040 / OpenBuilds). El soporte se atornilla a las
ranuras T del perfil con tuercas M5 sobre la cuadrícula real de módulo de 20 mm,
con un tornillo centrado en la línea central de cada ranura.

Parte del **Commons de Hiperobjetos de Yantra4D**. Visualizador y configurador
oficial: [Yantra4D](https://app.yantra4d.com).

## Tabla de perfiles

| Serie | Módulo | Ranura | Tornillo |
| :--- | :--- | :--- | :--- |
| 2020 | 20 mm | 6 mm | M5 |
| 2040 | 20 mm | 6 mm | M5 |
| 3030 | 30 mm | 8 mm | M6 |
| 4040 | 40 mm | 8 mm | M8 |

El centro del tornillo cae a `módulo / 2` de la esquina del perfil, es decir
sobre la línea central de la ranura, así una escuadra impresa registra igual que
una de fundición.

## Modos

| Modo | Pieza | Descripción |
| :--- | :--- | :--- |
| **Escuadra de Dos Vías** | `corner_2way` | Placa plana en ángulo recto, un orificio M avellanado por pata. |
| **Escuadra con Refuerzo** | `corner_gusset` | Placa de dos vías más un alma triangular en el ángulo interior. |
| **Bloque de Tres Vías** | `corner_3way` | Bloque cúbico de vértice que une tres perfiles (brazos X, Y, Z). |

## Parámetros

| Grupo | Parámetro | Predeterminado | Notas |
| :--- | :--- | :--- | :--- |
| Perfil | `series` | 2020 | Módulo + tamaño de tornillo de la tabla. |
| Soporte | `thickness` | 6.0 mm | Grosor de pata / brazo. |
| Soporte | `leg_len` | 30.0 mm | Longitud de cada pata a lo largo del perfil. |
| Soporte | `width` | 20.0 mm | Ancho a lo ancho de la cara del perfil. |
| Soporte | `bolt_dia` | 0.0 mm | Sobrescribir holgura; 0 = derivar de la serie. |
| Soporte | `fillet_r` | 3.0 mm | Radio de esquina exterior. |

## Presets

- **Escuadra 2020 de Dos Vías** — la escuadra de esquina interior para un
  bastidor 2020.
- **Escuadra 2040 con Refuerzo** — una escuadra reforzada para miembros 2040 con
  carga.
- **Vértice 3030 de Tres Vías** — un bloque cúbico que une tres perfiles 3030.

## Perfil de Hiperobjeto

- **Dominio:** industrial
- **Interfaces CDG:**
  - **Cuadrícula de Pernos M5 T-Slot** (`profile`, perfil 2020/2040 — módulo de
    20 mm, ranura de 6 mm, M5) — la interfaz, definida por `series`, `leg_len`,
    `width`, `bolt_dia`. Comparte el estándar de extrusión T-slot con
    `tslot-2020`, `featherboard` y `linear-wheel`.
  - **Marcos de acople** (escuadras de dos vías y con refuerzo):
    `<part>_leg_x` y `<part>_leg_z` están en la cara de asiento de cada pata,
    en el centro del perno, normal hacia el perfil, `x_axis` a lo largo de él;
    macho, simetría 2, clave de tamaño `tslot-2020-6mm` para 2020/2040.
  - **Marcos del bloque de tres vías:** `corner_3way_arm_x`, `_arm_y` (caras
    inferiores de los brazos, normal −z) y `_arm_z` (cara trasera del brazo Z,
    normal −x), cada uno en el centro de su perno; macho, simetría 2, la misma
    clave de tamaño por `series`. La cadena de límites (perno manual → ancho
    mínimo → cubo → ancho del brazo) es un bloque `let` (ASM-1 v1.1, keystone
    0.4.0 o posterior).
  - **Largo de brazo:** cada brazo de tres vías llega al menos 1 mm más allá del
    borde del avellanado de su perno (`cube + module/2 + head/2 + 1`), así el
    barreno nunca rompe el extremo del brazo; un `leg_len` mayor se respeta.
- **Conciencia de material:** `tolerance_by_material` permite ajustar la holgura
  M por filamento para que las tuercas entren limpiamente.
- **Licencia commons:** CERN-OHL-W-2.0
