"""LiXR's splash on the machine page (48 x 33 card, 34 x 34 emblem, 25 x 22 small emblem).

The card follows the stock ones: two lines of 3 x 5 capitals and three rows of five pips. The
emblem is a rounded square with a diagonal cross cut out of it, the small one the same motif.
Used by tools/gen_all.py; the arrays are written as an OS Bitmap by that generator.
"""
from feral_screens import _text, _pip


def _card():
    rows = [["."] * 48 for _ in range(33)]
    _text(rows, 0, 0, "CLASS:SYNTH")
    _text(rows, 0, 7, "STYLE:LIXR")
    stats = (("STR:", "square", (1, 1, 1, 1, 1)), ("DEX:", "diamond", (1, 1, 1, 1, 0)),
             ("MAG:", "chevron", (1, 1, 1, 0, 0)))
    for r, (label, shape, pips) in enumerate(stats):
        y = 14 + r * 7
        _text(rows, 0, y, label)
        for i, on in enumerate(pips):
            _pip(rows, 18 + i * 6, y, on, shape)
    return "\n".join("".join(r) for r in rows)


def _inside_round(x, y, w, h):
    if x < 2 or y < 2 or x >= w - 2 or y >= h - 2:
        return False
    if (x < 5 or x >= w - 5) and (y < 5 or y >= h - 5):
        return False
    return True


def _emblem(w, h, cut):
    rows = [["."] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if not _inside_round(x, y, w, h):
                continue
            # a diagonal cross, with a little margin from the rounded border
            if (x < w - 7 and y < h - 7 and
                    (abs((x - 4) - (y - 4)) <= cut or abs((x - 4) + (y - 4) - (w - 8)) <= cut)):
                continue
            rows[y][x] = "#"
    return "\n".join("".join(r) for r in rows)


ART_A = _card()
ART_B = _emblem(34, 34, 1)
ART_C = _emblem(25, 22, 1)
SPRITES = (("a", ART_A, 48, 33), ("b", ART_B, 34, 34), ("c", ART_C, 25, 22))
