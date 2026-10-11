"""Papel picado banner — sheet-hyperobjects cartridge (Pliego).

A keystone TEST FIXTURE shaped exactly like a sheet commons cartridge: one tissue-paper
flag whose motif is generated with mirror symmetry (one or two folds), plus a valley
fold-over hem at the top for the string. Uses the documented kernel API (Pliego
docs/strategy/kernel.md §1-§2). Replaced by a real commons cartridge in the first re-pin.
"""

import math

import pliego


def PARAM(get, default):
    try:
        return get()
    except NameError:
        return default


width = float(PARAM(lambda: width, 280.0))  # noqa: F821
height = float(PARAM(lambda: height, 360.0))  # noqa: F821
symmetry = int(PARAM(lambda: symmetry, 2))  # noqa: F821
hem = float(PARAM(lambda: hem, 15.0))  # noqa: F821

flag = pliego.Sheet(
    "flag",
    pliego.rectangle(width, height),
    stock="papel-de-china",
    label={"en": "Flag", "es": "Banderita", "fr": "Fanion", "pt": "Bandeirinha"},
)
flag.valley((0, height - hem), (width, height - hem), angle=170)

# A ring of petals in the upper-left quarter, mirrored across the centre line (and, with
# two folds, across the horizontal centre too) — what fold-and-cut would produce.
cx, cy = width / 4.0, (height - hem) * 0.75
petals = []
for k in range(6):
    a = math.radians(60 * k)
    px, py = cx + 0.12 * width * math.cos(a), cy + 0.12 * width * math.sin(a)
    petals.append([(px, py), (px + 6, py + 10), (px - 6, py + 10)])
mirrors = [lambda x, y: (width - x, y)]
if symmetry == 2:
    mirrors += [lambda x, y: (x, height - hem - y), lambda x, y: (width - x, height - hem - y)]
for petal in petals:
    flag.hole(petal)
    for m in mirrors:
        flag.hole([m(x, y) for x, y in petal])

result = pliego.Assembly(
    [flag],
    controls=[pliego.sequence_control()],
    sequence=pliego.Sequence.fold_each(),
)
