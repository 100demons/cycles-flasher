"""DUET's splash on the machine page, and the interface details that go with it.

The OS draws three pictures for the machine chosen on a track: a character card (48 x 33) and an emblem (34 x 34) on the
MACHINES page, the emblem again in the middle of a track's page, and a small emblem (25 x 22) in the track strip. The
six stock machines have their own; an added machine gets one of theirs unless it is given a picture index of its own.
DUET takes index 6, one past the stock ones, and this module:

  - writes the three pictures below as pixel art (# lit, . dark), turns them into image and mask planes of the OS's
    Bitmap class (constructor 0x40070172) in tools/machines/duet/duet_icons.h, linked into the machine's payload;
  - patches the detours of gen_syntakt_engines.detours_asm: the MACHINES page (drum_icons) and the small icon
    (small_icon) draw our Bitmap objects when the index is 6, and the four places that add the base of a stock picture
    array to index x 28 jump to our stubs for that index;
  - patches the three clamps that would send the index back to the stock SNARE picture (moveq #5 -> moveq #6).

The card follows the stock ones: two lines of 3 x 5 capital letters on a 4-pixel pitch ("CLASS:...", "STYLE:...") and
three rows of five 5 x 5 pips after "STR:", "DEX:" and "MAG:". The emblem is a filled rounded square with a sine wave cut
out of it, the same motif at 25 x 22 for the small icon. Nothing of the OS's pictures is copied or read here.

Used by tools/gen_duet.py and tools/emu/test_duet_os.py.
"""
import struct

IMAGE = 6                                   # DUET's picture index: one past the six stock ones
DUET_OFFSET = IMAGE * 28

# --- the character card, 48 x 33 ------------------------------------------------------------------------------------
ART_A = """
.##.#....#...##..##.....###.#.#.................
#...#...#.#.#...#....#..#...###.................
#...#...###..#...#......##..###.................
#...#...#.#...#...#..#..#...#.#.................
.##.###.#.#.##..##......#...#.#.................
................................................
................................................
...##.###.#.#.#...###.....##..#....#...##.###...
..#....#..#.#.#...#....#..#.#.#...#.#.#....#....
...#...#...#..#...##......##..#...###..#...#....
....#..#...#..#...#....#..#.#.#...#.#...#..#....
..##...#...#..###.###.....##..###.#.#.##...#....
................................................
................................................
.##.###.##.........###...###...###...###...###..
#....#..#.#..#....#...#.#...#.#...#.#...#.#...#.
.#...#..##........#...#.#...#.#...#.#...#.#...#.
..#..#..#.#..#....#...#.#...#.#...#.#...#.#...#.
##...#..#.#........###...###...###...###...###..
................................................
................................................
##..###.#.#.........#.....#.....................
#.#.#...#.#..#.....###...#.#....#...............
#.#.##...#........#####.#...#..#.#.....#...#....
#.#.#...#.#..#.....###...#.#....#...............
##..###.#.#.........#.....#.....................
................................................
................................................
#.#..#...##........#.....#.....#.....#.....#....
###.#.#.#....#....#.#...#.#...#.#...#.#...#.#...
###.###.#.#..........#.....#.....#.....#.....#..
#.#.#.#.#.#..#........#.....#.....#.....#.....#.
#.#.#.#..##..........#.....#.....#.....#.....#..
"""

# --- the emblem, 34 x 34: a rounded square, a sine wave cut out of it ------------------------------------------------
ART_B = """
..................................
..................................
.....########################.....
.....########################.....
.....########################.....
..##############################..
..##############################..
..#####################...######..
..####################.....#####..
..###################.####..####..
..##################.######.####..
..##################.#######.###..
..#################.#########.##..
..################.##########.##..
..################.###########.#..
..###############.############.#..
...##############.#############...
...#############.##############...
..#.############.###############..
..#.###########.################..
..##.##########.################..
..##.#########.#################..
..###.#######.##################..
..####.######.##################..
..####..####.###################..
..#####.....####################..
..######...#####################..
..##############################..
..##############################..
.....########################.....
.....########################.....
.....########################.....
..................................
..................................
"""

# --- the small emblem, 25 x 22: the same wave -----------------------------------------------------------------------
ART_C = """
.........................
....#################....
....#################....
....#################....
.#######################.
.###############...#####.
.##############.....####.
.#############..###..###.
.#############.#####.###.
.############.#######.##.
.#.#########.#########.#.
.#.#########.#########.#.
.##.#######.############.
.###.#####.#############.
.###..###..#############.
.####.....##############.
.#####...###############.
.#######################.
....#################....
....#################....
....#################....
.........................
"""

SPRITES = (("a", ART_A, 48, 33), ("b", ART_B, 34, 34), ("c", ART_C, 25, 22))


# --- the C arrays ---------------------------------------------------------------------------------------------------
def rows_of(art, w, h):
    rows = art.strip().splitlines()
    if len(rows) != h or any(len(r) != w or set(r) - set("#.") for r in rows):
        raise SystemExit(f"!! picture: expected {w} x {h} characters of '#' and '.'")
    return rows


def bitmap(art, w, h):
    """The image plane of the OS's Bitmap: 32-bit words, one column after the other, (h + 31) / 32 words per column;
    in a column, word 0 holds the 32 bottom rows (the bottom row in bit 31), word 1 the rows above."""
    rows = rows_of(art, w, h)
    wpc = (h + 31) >> 5
    out = []
    for x in range(w):
        words = [0] * wpc
        for y in range(h):                                     # y = 0 is the top row of the picture
            if rows[y][x] == "#":
                r = h - 1 - y                                  # the row counted from the bottom
                words[r >> 5] |= 1 << (31 - (r & 31))
        out += words
    return out


def mask(w, h):
    """The mask plane: the whole rectangle is drawn, as on all the OS's own pictures."""
    wpc = (h + 31) >> 5
    out = []
    for _ in range(w):
        for j in range(wpc):
            n = min(32, h - 32 * j)
            out.append(((1 << n) - 1) << (32 - n))
    return out


def icons_header():
    """duet_icons.h: the image and mask planes of the three pictures as C arrays."""
    out = ["/* Machine icons of DUET, computed by tools/gen_duet.py from tools/duet_screens.py: do not edit by hand.",
           " * Image and mask planes of the OS's Bitmap class: 32-bit words, column after column, (h + 31) / 32 words",
           " * per column, the bottom row of a column in bit 31 of its first word. */",
           "#ifndef DUET_ICONS_H", "#define DUET_ICONS_H", ""]
    for name, art, w, h in SPRITES:
        for kind, words in (("IMG", bitmap(art, w, h)), ("MSK", mask(w, h))):
            out.append(f"static const u32 DUET_{kind}_{name.upper()}[{len(words)}] = {{")
            for i in range(0, len(words), 6):
                out.append("\t" + ", ".join(f"{x:#010x}" for x in words[i:i + 6]) + ",")
            out.append("};")
        out.append("")
    return "\n".join(out + ["#endif", ""])


# --- the code that shows them ---------------------------------------------------------------------------------------
# The detour text of gen_syntakt_engines.detours_asm for one added machine, exactly as it is replaced here.
OLD_STATE_AT = "\t.globl\tstate_at\nstate_at:\n"
OLD_STATE_CONNECT = "\t.globl\tstate_connect\nstate_connect:\n"
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
\tcmp.l #DUET_OFFSET, %d4
\tbne.s 4f
\tlea DUET_BM_A, %a1
4:
\tmove.l %a1, -(%sp)
\tmove.l %d2, -(%sp)
\tjsr (%a2)
\tlea 48(%sp), %sp
\tpea 0x1
\tpea 0x22
\tcmp.l #DUET_OFFSET, %d4
\tbne.s 5f
\tmove.l #DUET_BM_B, %d4
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

# the places that add the base of a stock array of six Bitmaps to index x 28 (d0): (address of the 6-byte `add.l array,
# d0`, the array, the label of our stub, the picture it gives for index 6). The next instruction is at address + 6.
SITES = ((0x4001b6a6, 0x40fe384c, "duet_site_b", "b"),
         (0x400a40bc, 0x40fe37f0, "duet_site_c1", "c"),
         (0x400a4de6, 0x40fe37f0, "duet_site_c2", "c"),
         (0x400a4fc6, 0x40fe37f0, "duet_site_c3", "c"))
CLAMPS = (0x4001b69c, 0x400a40a6, 0x400a4fb0)       # `moveq #5, d0`: the clamp of the picture index


def stub_site(label, array, bm):
    return f"""{label}:
\tcmp.l #DUET_OFFSET, %d0
\tbne.s 1f
\tmove.l #DUET_BM_{bm.upper()}, %d0
\tjmp {{ret:#x}}
1:
\tadd.l {array:#x}, %d0
\tjmp {{ret:#x}}
"""


def redirect(label, cfunc):
    """The first instructions of the detoured state_at / state_connect: descriptors 77 and 78 (DUET's SHAPE and
    SWEEP) go to our own interface object; every other descriptor takes the OS's path unchanged."""
    return (f"\tmove.l 4(%sp), %d0\n\tmoveq #77, %d1\n\tcmp.l %d1, %d0\n\tbeq.s 0f\n"
            f"\tmoveq #78, %d1\n\tcmp.l %d1, %d0\n\tbne.s 1f\n0:\tjmp {cfunc:#x}\n1:\n")


def patch_detours(text, syms):
    """gen_syntakt_engines.detours_asm (one added machine) with DUET's pictures and its SHAPE / SWEEP objects.
    syms = the addresses of duet_bm_a, duet_bm_b, duet_bm_c, duet_state_at and duet_state_connect in the machine."""
    for old in (OLD_STATE_AT, OLD_STATE_CONNECT, OLD_DRUM, OLD_SMALL):
        if text.count(old) != 1:
            raise SystemExit("!! the detours of gen_syntakt_engines.py changed: tools/duet_screens.py replaces text that "
                             "is no longer there")
    if "DUET_OFFSET" in text:
        raise SystemExit("!! DUET_OFFSET already defined")
    head = [f"\t.set DUET_BM_A, {syms['duet_bm_a']:#x}",
            f"\t.set DUET_BM_B, {syms['duet_bm_b']:#x}",
            f"\t.set DUET_BM_C, {syms['duet_bm_c']:#x}",
            f"\t.set DUET_OFFSET, {DUET_OFFSET}"]
    stubs = "".join(stub_site(lab, arr, bm).format(ret=va + 6) for va, arr, lab, bm in SITES)
    text = text.replace(OLD_STATE_AT, OLD_STATE_AT + redirect("state_at", syms["duet_state_at"]))
    text = text.replace(OLD_STATE_CONNECT, OLD_STATE_CONNECT + redirect("state_connect", syms["duet_state_connect"]))
    text = text.replace(OLD_DRUM, NEW_DRUM).replace(OLD_SMALL, NEW_SMALL)
    return "\n".join(head) + "\n" + text + stubs


def site_writes(img, base, ssyms):
    """The extra writes: the four `add.l array, d0` become jumps to our stubs. Returns [{off, old, new}]; img = the
    official MAIN OS (the old bytes are checked), base = 0x40000400."""
    out = []
    for va, arr, lab, _ in SITES:
        old = img[va - base:va - base + 6]
        if old != bytes.fromhex("d0b9") + struct.pack(">I", arr):
            raise SystemExit(f"!! {va:#x}: not `add.l {arr:#x}, d0`")
        out.append({"off": va - base, "old": old.hex(),
                    "new": (bytes.fromhex("4ef9") + struct.pack(">I", ssyms[lab])).hex()})
    return out


def clamp_writes(writes, base):
    """The detours write moveq #1 (SNARE's picture) at the three clamps, over `moveq #5`: ours is `moveq #6`."""
    seen = 0
    for w in writes:
        if w and w["off"] + base in CLAMPS:
            if (w["old"], w["new"]) != ("7005", "7001"):
                raise SystemExit(f"!! {w['off'] + base:#x}: {w['old']} -> {w['new']}, expected 7005 -> 7001")
            w["new"] = "7006"
            seen += 1
    if seen != len(CLAMPS):
        raise SystemExit("!! the clamps of the picture index are not in the writes")
