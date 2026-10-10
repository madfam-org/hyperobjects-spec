"""Valley fold — sheet-hyperobjects cartridge (Pliego).

A keystone TEST FIXTURE shaped exactly like a sheet commons cartridge: the commons holds
no cartridge yet, so this stands in for one until the first real cartridge replaces it
in the re-pin. It uses the documented kernel API (Pliego docs/strategy/kernel.md §1-§2).

Sandbox contract: the runner makes `pliego` and `math` importable, injects the manifest
parameters as bare globals, and reads `result`.
"""

import pliego


def PARAM(get, default):
    try:
        return get()
    except NameError:
        return default


size = float(PARAM(lambda: size, 150.0))  # noqa: F821
stock = PARAM(lambda: stock, "kami")  # noqa: F821

sheet = pliego.Sheet(
    "square",
    pliego.square(size),
    stock=stock,
    label={"en": "Square", "es": "Cuadrado", "fr": "Carré", "pt": "Quadrado"},
)
sheet.valley((0, 0), (size, size), angle=180)

result = pliego.Assembly(
    [sheet],
    controls=[pliego.sequence_control()],
    sequence=pliego.Sequence.fold_each(),
)
