"""Feral's machine-page pictures, in the stock Model:Cycles style.

The OS draws three pictures for the machine chosen on a track: a character card (48 x 33), an emblem
(34 x 34) on the MACHINES page, the emblem again on the track page, and a small emblem (25 x 22) in
the track strip. The six stock machines have their own; an added machine reuses one of theirs unless
it is given picture index 6. Feral takes index 6.

The card uses the same layout as the stock cards: two lines of 3 x 5 capitals on a 4-pixel pitch
("CLASS:...", "STYLE:...") and three rows of five 5 x 5 pips after "STR:", "DEX:" and "MAG:". The
emblem is a rounded square with three claw cuts; the small emblem repeats the motif.
"""
import struct

IMAGE = 6
FERAL_OFFSET = IMAGE * 28

# --- 3 x 5 capitals ------------------------------------------------------------------------------------------------
FONT = {
    "A": (".#.", "#.#", "###", "#.#", "#.#"),
    "B": ("##.", "#.#", "##.", "#.#", "##."),
    "C": (".##", "#..", "#..", "#..", ".##"),
    "D": ("##.", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "##.", "#..", "###"),
    "F": ("###", "#..", "##.", "#..", "#.."),
    "G": (".##", "#..", "#.#", "#.#", ".##"),
    "H": ("#.#", "#.#", "###", "#.#", "#.#"),
    "I": ("###", ".#.", ".#.", ".#.", "###"),
    "J": ("..#", "..#", "..#", "#.#", ".#."),
    "K": ("#.#", "#.#", "##.", "#.#", "#.#"),
    "L": ("#..", "#..", "#..", "#..", "###"),
    "M": ("#.#", "###", "###", "#.#", "#.#"),
    "N": ("#.#", "###", "###", "###", "#.#"),
    "O": (".#.", "#.#", "#.#", "#.#", ".#."),
    "P": ("##.", "#.#", "##.", "#..", "#.."),
    "Q": (".#.", "#.#", "#.#", "###", "..#"),
    "R": ("##.", "#.#", "##.", "#.#", "#.#"),
    "S": (".##", "#..", ".#.", "..#", "##."),
    "T": ("###", ".#.", ".#.", ".#.", ".#."),
    "U": ("#.#", "#.#", "#.#", "#.#", "###"),
    "V": ("#.#", "#.#", "#.#", "#.#", ".#."),
    "W": ("#.#", "#.#", "###", "###", "#.#"),
    "X": ("#.#", "#.#", ".#.", "#.#", "#.#"),
    "Y": ("#.#", "#.#", ".#.", ".#.", ".#."),
    "Z": ("###", "..#", ".#.", "#..", "###"),
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("##.", "..#", ".#.", "#..", "###"),
    "3": ("##.", "..#", ".#.", "..#", "##."),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "##.", "..#", "##."),
    "6": (".##", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", ".#.", ".#.", ".#."),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "##."),
    ":": ("...", ".#.", "...", ".#.", "..."),
    "-": ("...", "...", "###", "...", "..."),
    " ": ("...", "...", "...", "...", "..."),
}


def _text(rows, x, y, s):
    """Write a line of 3 x 5 capitals on a 4-pixel pitch."""
    for i, ch in enumerate(s):
        g = FONT[ch]
        for yy in range(5):
            for xx in range(3):
                if g[yy][xx] == "#":
                    rows[y + yy][x + i * 4 + xx] = "#"


# 5 x 5 stat pip shapes, as on the stock cards: square (STR), diamond (DEX), chevron (MAG).
PIP = {
    "square": ("#####", "#####", "#####", "#####", "#####"),
    "diamond": ("..#..", ".###.", "#####", ".###.", "..#.."),
    "chevron": ("#...#", "##.##", "#.#.#", "##.##", "#...#"),
}


def _pip(rows, x, y, on, shape):
    """A 5 x 5 stat pip: filled when on, outline otherwise."""
    g = PIP[shape]
    for yy in range(5):
        for xx in range(5):
            if g[yy][xx] != "#":
                continue
            edge = (yy == 0 or yy == 4 or xx == 0 or xx == 4
                    or g[yy - 1][xx] == "." or g[yy + 1][xx] == "."
                    or g[yy][xx - 1] == "." or g[yy][xx + 1] == ".")
            if on or edge:
                rows[y + yy][x + xx] = "#"


def _card():
    rows = [["."] * 48 for _ in range(33)]
    _text(rows, 0, 0, "CLASS:BEAST")
    _text(rows, 0, 7, "STYLE:CHAOS")
    stats = (("STR:", "square", (1, 1, 1, 1, 0)), ("DEX:", "diamond", (1, 1, 1, 1, 1)),
             ("MAG:", "chevron", (1, 1, 1, 0, 0)))
    for r, (label, shape, pips) in enumerate(stats):
        y = 14 + r * 7
        _text(rows, 0, y, label)
        for i, on in enumerate(pips):
            _pip(rows, 18 + i * 6, y, on, shape)
    return "\n".join("".join(r) for r in rows)


def _inside_round(x, y, w, h):
    """A rounded square like the stock emblems: full middle, inset corners."""
    if x < 2 or y < 2 or x >= w - 2 or y >= h - 2:
        return False
    if (x < 5 or x >= w - 5) and (y < 5 or y >= h - 5):
        return False
    return True


def _claw(x, y, w, h, cuts):
    # keep the rounded border intact: the cuts live in the middle of the emblem
    if x < 7 or x > w - 8 or y < 6 or y > h - 7:
        return False
    for c in cuts:
        if abs((x - 4) - (y - 3) - c) <= 1:
            return True
    return False


def _emblem(w, h, cuts):
    rows = [["."] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if _inside_round(x, y, w, h) and not _claw(x, y, w, h, cuts):
                rows[y][x] = "#"
    return "\n".join("".join(r) for r in rows)


ART_A = _card()
ART_B = _emblem(34, 34, (-10, 0, 10))
ART_C = _emblem(25, 22, (-6, 6))
SPRITES = (("a", ART_A, 48, 33), ("b", ART_B, 34, 34), ("c", ART_C, 25, 22))


# --- the C arrays ---------------------------------------------------------------------------------------------------
def rows_of(art, w, h):
    rows = art.strip().splitlines()
    if len(rows) != h or any(len(r) != w or set(r) - set("#.") for r in rows):
        raise SystemExit(f"!! picture: expected {w} x {h} characters of '#' and '.'")
    return rows


def bitmap(art, w, h):
    """The image plane: 32-bit words, one column after the other, (h + 31) / 32 words per column."""
    rows = rows_of(art, w, h)
    wpc = (h + 31) >> 5
    out = []
    for x in range(w):
        words = [0] * wpc
        for y in range(h):
            if rows[y][x] == "#":
                r = h - 1 - y
                words[r >> 5] |= 1 << (31 - (r & 31))
        out += words
    return out


def mask(w, h):
    """The mask plane: the whole rectangle, as on the stock pictures."""
    wpc = (h + 31) >> 5
    out = []
    for _ in range(w):
        for j in range(wpc):
            n = min(32, h - 32 * j)
            out.append(((1 << n) - 1) << (32 - n))
    return out


def icons_header():
    out = ["/* Machine icons of Feral, computed by tools/gen_tiny2.py from tools/feral_screens.py: do not edit by hand.",
           " * Image and mask planes of the OS's Bitmap class: 32-bit words, column after column, (h + 31) / 32 words",
           " * per column, the bottom row of a column in bit 31 of its first word. */",
           "#ifndef FERAL_ICONS_H", "#define FERAL_ICONS_H", ""]
    for name, art, w, h in SPRITES:
        for kind, words in (("IMG", bitmap(art, w, h)), ("MSK", mask(w, h))):
            out.append(f"static const u32 FERAL_{kind}_{name.upper()}[{len(words)}] = {{")
            for i in range(0, len(words), 6):
                out.append("\t" + ", ".join(f"{x:#010x}" for x in words[i:i + 6]) + ",")
            out.append("};")
        out.append("")
    return "\n".join(out + ["#endif", ""])


# --- the code that shows them ---------------------------------------------------------------------------------------
# The detour text of gen_syntakt_engines.detours_asm for one added machine, exactly as it is replaced here.
OLD_DRUM = """\t.globl\tdrum_icons
drum_icons:
\tmove.l %d3, %d0
\tbsr.w shown
\tmove.l %d0, %d4
\tlsl.l #2, %d0
\tlsl.l #5, %d4
\tsub.l %d0, %d4
\tpea 0x1
\tpea 0x17
\tpea 0x20
\tlea 0x40071da4, %a2
\tmovea.l 0x40fe32cc, %a1
\tadda.l %d4, %a1
\tmove.l %a1, -(%sp)
\tmove.l %d2, -(%sp)
\tjsr (%a2)
\tlea 48(%sp), %sp
\tpea 0x1
\tpea 0x22
\tadd.l 0x40fe384c, %d4
\tpea 0x60
\tmove.l %d4, -(%sp)
\tmove.l %d2, -(%sp)
\tjsr (%a2)
\tlea 20(%sp), %sp
\tjmp 0x400a2680
"""

OLD_SMALL = """\t.globl\tsmall_icon
small_icon:
\tlea 10(%a0), %a0
\tmove.l %a0, -(%sp)
\tmove.l 16(%fp), -(%sp)
\tmove.l %d2, %d0
\tbpl.s 1f
\tmoveq #0, %d0
1:
\tmoveq #5, %d1
\tcmp.l %d0, %d1
\tbge.s 3f
\tbsr.w shown
\tmoveq #5, %d1
\tcmp.l %d0, %d1
\tbge.s 3f
\tmoveq #5, %d0
3:
\tjmp 0x400a4dde
"""

NEW_DRUM = """\t.globl\tdrum_icons
drum_icons:
\tmove.l %d3, %d0
\tbsr.w shown
\tmove.l %d0, %d4
\tlsl.l #2, %d0
\tlsl.l #5, %d4
\tsub.l %d0, %d4
\tpea 0x1
\tpea 0x17
\tpea 0x20
\tlea 0x40071da4, %a2
\tmovea.l 0x40fe32cc, %a1
\tadda.l %d4, %a1
\tcmp.l #FERAL_OFFSET, %d4
\tbne.s 4f
\tlea FERAL_BM_A, %a1
4:
\tmove.l %a1, -(%sp)
\tmove.l %d2, -(%sp)
\tjsr (%a2)
\tlea 48(%sp), %sp
\tpea 0x1
\tpea 0x22
\tcmp.l #FERAL_OFFSET, %d4
\tbne.s 5f
\tmove.l #FERAL_BM_B, %d4
\tbra.s 6f
5:
\tadd.l 0x40fe384c, %d4
6:
\tpea 0x60
\tmove.l %d4, -(%sp)
\tmove.l %d2, -(%sp)
\tjsr (%a2)
\tlea 20(%sp), %sp
\tjmp 0x400a2680
"""

NEW_SMALL = """\t.globl\tsmall_icon
small_icon:
\tlea 10(%a0), %a0
\tmove.l %a0, -(%sp)
\tmove.l 16(%fp), -(%sp)
\tmove.l %d2, %d0
\tbpl.s 1f
\tmoveq #0, %d0
1:
\tmoveq #5, %d1
\tcmp.l %d0, %d1
\tbge.s 3f
\tbsr.w shown
\tmoveq #6, %d1
\tcmp.l %d0, %d1
\tbeq.s 3f
\tmoveq #5, %d0
3:
\tjmp 0x400a4dde
"""

SITES = ((0x4001b6a6, 0x40fe384c, "feral_site_b", "b"),
         (0x400a40bc, 0x40fe37f0, "feral_site_c1", "c"),
         (0x400a4de6, 0x40fe37f0, "feral_site_c2", "c"),
         (0x400a4fc6, 0x40fe37f0, "feral_site_c3", "c"))
CLAMPS = (0x4001b69c, 0x400a40a6, 0x400a4fb0)


def stub_site(label, array, bm):
    return f"""{label}:
\tcmp.l #FERAL_OFFSET, %d0
\tbne.s 1f
\tmove.l #FERAL_BM_{bm.upper()}, %d0
\tjmp {{ret:#x}}
1:
\tadd.l {array:#x}, %d0
\tjmp {{ret:#x}}
"""


def patch_detours(text, syms):
    """The detours with Feral's pictures. syms: addresses of feral_bm_a/b/c."""
    for old in (OLD_DRUM, OLD_SMALL):
        if text.count(old) != 1:
            raise SystemExit("!! the detours changed: tools/feral_screens.py replaces text that is no longer there")
    if "FERAL_OFFSET" in text:
        raise SystemExit("!! FERAL_OFFSET already defined")
    head = [f"\t.set FERAL_BM_A, {syms['feral_bm_a']:#x}",
            f"\t.set FERAL_BM_B, {syms['feral_bm_b']:#x}",
            f"\t.set FERAL_BM_C, {syms['feral_bm_c']:#x}",
            f"\t.set FERAL_OFFSET, {FERAL_OFFSET}"]
    stubs = "".join(stub_site(lab, arr, bm).format(ret=va + 6) for va, arr, lab, bm in SITES)
    text = text.replace(OLD_DRUM, NEW_DRUM).replace(OLD_SMALL, NEW_SMALL)
    return "\n".join(head) + "\n" + text + stubs


def site_writes(img, base, ssyms):
    out = []
    for va, arr, lab, _ in SITES:
        old = img[va - base:va - base + 6]
        if old != bytes.fromhex("d0b9") + struct.pack(">I", arr):
            raise SystemExit(f"!! {va:#x}: not `add.l {arr:#x}, d0`")
        out.append({"off": va - base, "old": old.hex(),
                    "new": (bytes.fromhex("4ef9") + struct.pack(">I", ssyms[lab])).hex()})
    return out


def clamp_writes(writes, base):
    seen = 0
    for w in writes:
        if w and w["off"] + base in CLAMPS:
            if (w["old"], w["new"]) != ("7005", "7001"):
                raise SystemExit(f"!! {w['off'] + base:#x}: {w['old']} -> {w['new']}, expected 7005 -> 7001")
            w["new"] = "7006"
            seen += 1
    if seen != len(CLAMPS):
        raise SystemExit("!! the clamps of the picture index are not in the writes")



if __name__ == "__main__":
    print(ART_A)
    print()
    print(ART_B)
    print()
    print(ART_C)
