"""V-fold pop-up — sheet-hyperobjects cartridge (Pliego).

A keystone TEST FIXTURE shaped exactly like a sheet commons cartridge (two sheets, glue
joins, a hinge mechanism driving the spread, an `open` control), using the documented
kernel API (Pliego docs/strategy/kernel.md §1-§2). Replaced by a real commons cartridge
in the first re-pin.
"""

import math

import pliego


def PARAM(get, default):
    try:
        return get()
    except NameError:
        return default


spread_width = float(PARAM(lambda: spread_width, 200.0))  # noqa: F821
piece_height = float(PARAM(lambda: piece_height, 60.0))  # noqa: F821
v_angle = float(PARAM(lambda: v_angle, 60.0))  # noqa: F821
tab_width = float(PARAM(lambda: tab_width, 10.0))  # noqa: F821

half = spread_width / 2.0
base = pliego.Sheet(
    "base",
    pliego.rectangle(spread_width, spread_width * 0.7),
    stock="cardstock-250",
    label={"en": "Base spread", "es": "Pliego base", "fr": "Double page de base",
           "pt": "Página dupla de base"},
)
gutter = base.valley((half, 0), (half, spread_width * 0.7), angle=180)

# The piece: a rhombus folded on its long diagonal, with a glue tab on each lower edge.
reach = piece_height / math.tan(math.radians(v_angle))
piece = pliego.Sheet(
    "piece",
    [(0, 0), (reach, piece_height), (0, 2 * piece_height), (-reach, piece_height)],
    stock="cardstock-250",
    label={"en": "V-fold piece", "es": "Pieza en V", "fr": "Pièce en V", "pt": "Peça em V"},
)
piece.mountain((0, 0), (0, 2 * piece_height), angle=-180)
left = piece.tab(0, width=tab_width, taper=45)
right = piece.tab(3, width=tab_width, taper=45)

result = pliego.Assembly(
    [base, piece],
    joins=[
        pliego.glue(left, onto=base, side="front"),
        pliego.glue(right, onto=base, side="front"),
    ],
    mechanisms=[pliego.hinge("spread", gutter, control="open", rest=180, moving=[base])],
    controls=[pliego.angle_control("open", 0, 180, default=180)],
)
