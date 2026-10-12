"""Lo-fi de MACRO sous FUNC + PITCH (notes/55 §8), sur le code de l'interface de l'OS : la recherche du descripteur
d'un potard (0x4001e814, ou le slot 124 de la vtable de ParameterPageView quand un tweak l'a remplacé), puis
l'application d'un tour de potard avec FUNC (0x4000b7d6, l'objet des paramètres d'une piste), puis le texte de la
valeur (le formateur de l'objet d'interface du descripteur, vrai sprintf), puis la fenêtre de valeur qui s'ouvre quand
on tourne le potard (0x4001d818, le slot 144 de la vtable de ParameterPageView), dessinée dans un écran de 128 × 64.

Utilisé par test_macro.py et test_macro_syntakt.py. Sur la machine, FUNC + PITCH réglait PITCH par demi-tons
(0x4004e84c) : FINE, que lit le lo-fi, n'était sous aucun potard (retour de deux utilisateurs, 11/10/2026)."""

import struct

from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn import m68k_const as mk

BASE = 0x40000400
IMAGE_LEN = 0x1a9d40
STOP, STACK, SCRATCH = 0x90000100, 0x90010000, 0x91000000
UI_INIT = 0x400de244                 # construit les objets d'interface des descripteurs
KNOB_LOOKUP = 0x4001e814             # (vue, potard, FUNC, -1) -> descripteur
KNOB_SLOT = 0x401005a8               # slot 124 de la vtable de ParameterPageView
MACHINE_OF = 0x4001e318              # (vue, piste) -> machine de la piste
EDIT = 0x4000b7d6                    # vt[32] de l'objet des paramètres d'une piste (vtable 0x400fd134)
VTABLE = 0x400fd134
UI_REC = 0x40a71754                  # objets d'interface, 100 o par descripteur
PITCH, FTUN = 42, 43
PITCH_KNOB = 2
PAGE_VT = 0x4010052c                 # vtable de ParameterPageView (slot 124 en 0x401005a8)
POPUP_SLOT = PAGE_VT + 144           # 0x4001d818 : (vue, bitmap, descripteur, valeur, drapeau, 1)
BITMAP = 0x40070172                  # Bitmap(this, largeur, hauteur, image, masque)
DRAW_TEXT = 0x40071a04               # (bitmap, police, x, y, alignement, format, ...)
DRAW_SPRITE = 0x40071da4             # (bitmap, sprite, x, y, mode)
BIG_FONT, FMT_S = 0x401429ec, 0x40124b58     # grande police de la fenêtre de valeur ; « %s »


class UI:
    """Le code de l'interface de l'OS, fonction par fonction : image, charge utile, BSS à zéro, tas factice."""

    def __init__(self, img, payload=None, end=None):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
        uc.mem_map(0x40000000, 0x02400000)
        uc.mem_write(BASE, img[:(end - BASE) if end else IMAGE_LEN])
        if payload:
            dst, data = payload
            uc.mem_map(dst, (len(data) + 0xfffff) & ~0xfffff)
            uc.mem_write(dst, data)
        uc.mem_map(0x90000000, 0x04000000)
        uc.mem_write(STOP, b"\x4e\x71\x4e\x71")
        self.bad, self.hooks, self.calls, self.heap = [], {}, [], 0x93000000
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: self.bad.append(addr) or False)
        uc.hook_add(UC_HOOK_CODE, self._hook)
        self.hooks.update({0x400802e0: ("new", 0), 0x400802ec: ("delete", 0), 0x400cf044: ("atexit", 0),
                           0x400c9afc: ("atexit", 0), 0x400f4dc6: ("guard", 1), 0x400f4e22: ("guard_done", 0)})
        self.call(UI_INIT, count=50_000_000)
        self.init_ok = not self.bad

    def _hook(self, uc, addr, size, ud):
        if addr in self.hooks:
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            args = struct.unpack(">6I", uc.mem_read(sp + 4, 24))
            name, ret = self.hooks[addr]
            if name == "new":
                ret, self.heap = self.heap, (self.heap + args[0] + 15) & ~15
            self.calls.append((name, args))
            uc.reg_write(mk.UC_M68K_REG_D0, ret)
            uc.reg_write(mk.UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)

    def u32(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def call(self, fn, *args, count=20_000_000):
        sp = STACK - 0x400
        self.uc.mem_write(sp, struct.pack(">I" + "I" * len(args), STOP, *[a & 0xffffffff for a in args]))
        self.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        self.bad.clear()
        self.uc.emu_start(fn, STOP, count=count)
        self.sp_ok = self.uc.reg_read(mk.UC_M68K_REG_A7) == sp + 4
        return self.uc.reg_read(mk.UC_M68K_REG_D0)

    def cstr(self, a):
        return bytes(self.uc.mem_read(a, 64)).split(b"\0")[0].decode("latin-1")

    def lookup(self, machine, knob, func):
        """Descripteur sous un potard pour une piste de cette machine : le vrai 0x4001e814 (par le slot 124, comme
        l'OS l'appelle), la machine de la piste et les singletons de l'écran donnés (pas de popup)."""
        view = SCRATCH
        self.uc.mem_write(view + 104, struct.pack(">I", view + 0x200))
        self.uc.mem_write(view + 0x200, b"".join(struct.pack(">I", i) for i in range(1, 7)))   # vecteur [1..6]
        self.hooks.update({MACHINE_OF: ("machine", machine), 0x400cf9a8: ("ui", 0), 0x4006b736: ("popup", 0),
                           0x4007faf4: ("key", 0)})
        d = self.call(self.u32(KNOB_SLOT), view, knob, 0xffffffff if func else 0, 0xffffffff)
        return d if self.sp_ok and not self.bad else None

    def edit_func(self, desc, cur, delta):
        """Un tour de potard avec FUNC sur ce descripteur : le vrai 0x4000b7d6 (fine = 1), sur un objet dont la
        lecture (vt[28]) rend cur et l'écriture (vt[24]) est notée ; rend la valeur écrite (bornée par 0x4000b274)."""
        obj, vt = SCRATCH + 0x400, SCRATCH + 0x800
        self.uc.mem_write(vt, bytes(self.uc.mem_read(VTABLE, 0x80)))
        get, put = SCRATCH + 0xc00, SCRATCH + 0xc10
        self.uc.mem_write(get, b"\x4e\x75"); self.uc.mem_write(put, b"\x4e\x75")
        self.uc.mem_write(vt + 28, struct.pack(">I", get)); self.uc.mem_write(vt + 24, struct.pack(">I", put))
        self.uc.mem_write(obj, struct.pack(">II", vt, 0))
        self.hooks.update({get: ("get", cur & 0xffff if cur >= 0 else cur), put: ("put", 0)})
        self.calls.clear()
        self.call(EDIT, obj, desc, delta, 0, 1, 0, 1, 1)
        puts = [c for c in self.calls if c[0] == "put"]
        return puts[0][1][2] if len(puts) == 1 and self.sp_ok and not self.bad else None

    def popup(self, desc, v, text_path=False):
        """La fenêtre de valeur de ce descripteur à cette valeur : le vrai 0x4001d818 (par le slot 144, comme l'OS),
        dans un écran 128 × 64 neuf ; rend ses pixels (colonne par colonne). La vue rend (vt[128]) un objet des
        paramètres d'une piste (vtable 0x400fd134). text_path : le chemin texte de l'OS pour ce descripteur (sans
        dessin, comme les paramètres sans jauge) : référence de ce que l'OS y écrit."""
        S = SCRATCH + 0x2000
        bmp, fb, view, pvt, stub, obj, ovt, ok = S, S + 0x100, S + 0x800, S + 0xa00, S + 0xe00, S + 0xe10, S + 0xf00, \
            S + 0xff0
        self.uc.mem_write(fb, bytes(0x400))
        self.call(BITMAP, bmp, 128, 64, fb, 0)
        self.uc.mem_write(pvt, bytes(self.uc.mem_read(PAGE_VT, 0x200)))
        self.uc.mem_write(pvt + 128, struct.pack(">I", stub))
        self.uc.mem_write(view, struct.pack(">I", pvt))
        self.uc.mem_write(ovt, bytes(self.uc.mem_read(VTABLE, 0x80)))
        self.uc.mem_write(obj, struct.pack(">II", ovt, 0))
        self.hooks[stub] = ("object", obj)
        r = UI_REC + 100 * desc
        saved = bytes(self.uc.mem_read(r + 0x2c, 4))
        if text_path:                    # sans dessin (+0x2c nul) ; la valeur est acceptée (vt[24], 0x4000c0a6)
            self.uc.mem_write(r + 0x2c, bytes(4))
            self.uc.mem_write(ovt + 24, struct.pack(">I", ok))
            self.hooks[ok] = ("valid", 1)
        self.hooks[DRAW_SPRITE] = ("sprite", 0)          # les jauges : des sprites construits au démarrage, notés
        self.calls.clear()
        self.call(self.u32(POPUP_SLOT), view, bmp, desc, v, 0, 1)
        self.uc.mem_write(r + 0x2c, saved)
        del self.hooks[DRAW_SPRITE]
        good = self.sp_ok and not self.bad
        sprites = [c[1][1] for c in self.calls if c[0] == "sprite"]
        return (bytes(self.uc.mem_read(fb, 0x400)), sprites) if good else None

    def glyph(self, ch):
        """Points allumés par ce caractère seul dans la grande police de la fenêtre de valeur (0x401429ec)."""
        S = SCRATCH + 0x6000
        bmp, fb, font, s = S, S + 0x100, S + 0x600, S + 0x700
        self.uc.mem_write(fb, bytes(0x400))
        self.call(BITMAP, bmp, 128, 64, fb, 0)
        self.call(0x40072260, font, BIG_FONT)
        self.uc.mem_write(s, ch.encode() + b"\0")
        self.call(DRAW_TEXT, bmp, font, 0x60, 0x22, 2, FMT_S, s)
        return sum(bin(x).count("1") for x in self.uc.mem_read(fb, 0x400))

    def text(self, desc, v):
        r = UI_REC + 100 * desc
        self.uc.mem_write(SCRATCH + 0x1000, bytes(32))
        self.call(self.u32(r + 0x20), r + 0x14, v, SCRATCH + 0x1000)
        return self.cstr(SCRATCH + 0x1000)


def want_text(fine):
    """Ce que macro.cc fait de FINE (notes/55) : RATE à gauche (en kHz), BITS à droite. En majuscules : la grande
    police de la fenêtre de valeur n'a pas de minuscules (sauf m)."""
    if fine == 64:
        return "OFF"
    if fine < 64:
        return f"{round(48 * 2 ** (-86 * (64 - fine) / 1536))}K"
    return f"{12 - (fine - 65) * 10 // 62}B"


def pix(fb, x, y):
    w = struct.unpack(">I", fb[(x * 2 + y // 32) * 4:(x * 2 + y // 32) * 4 + 4])[0]
    return (w >> (31 - (y & 31))) & 1


def ascii_popup(fb, x0=64, x1=124, y0=22, y1=57):
    """La moitié droite de la fenêtre (y = 0 en bas de l'écran)."""
    return "\n".join(f"        y={y:2d}  " + "".join("#" if pix(fb, x, y) else "." for x in range(x0, x1))
                     for y in range(y1 - 1, y0 - 1, -1))


def want_step(cur, delta):
    v = (cur + 0x80) & ~0xff
    s = (abs(delta) + 0xff) & ~0xff
    return min(max(v + (s if delta >= 0 else -s), 0), 0x7f00)


def check_lofi(base_img, fw_img, payload, top, label, check, end=None, base_end=None, base_payload=None,
               base="l'OS d'origine", after=0):
    """FUNC + PITCH sur une piste MACRO (machine top) : FINE, pas à pas, avec son texte ; le reste comme sans MACRO
    (base : les mêmes mods sans MACRO, ses machines 0..top-1). after : machines ajoutées après MACRO (ACID,
    tools/gen_acid_combos.py) : FUNC + PITCH y reste PITCH, FINE sous aucun potard."""
    a = UI(base_img, base_payload, end=base_end)
    b = UI(fw_img, payload, end=end)
    check(a.init_ok and b.init_ok, f"{label} : objets d'interface construits par l'OS (0x400de244)")
    # 1. la recherche : FUNC + PITCH sur MACRO -> FINE ; les autres machines comme sans MACRO
    got, same = {}, True
    for m in range(top + 1):
        for knob in range(2, 16):
            for func in (False, True):
                got[m, knob, func] = d = b.lookup(m, knob, func)
                if m < top:
                    same &= d == a.lookup(m, knob, func)
    same &= None not in got.values()
    check(got[top, PITCH_KNOB, True] == FTUN and got[top, PITCH_KNOB, False] == PITCH,
          f"{label} : piste MACRO, FUNC + PITCH -> {got[top, PITCH_KNOB, True]} (FINE, {FTUN}) ; PITCH seul -> "
          f"{got[top, PITCH_KNOB, False]} (PITCH, {PITCH})")
    check(all(got[top, k, True] == got[top, k, False] for k in range(3, 14)),
          f"{label} : les potards 3 à 13 de MACRO : avec FUNC comme sans (14 et 15 : leur 2e paramètre, comme l'OS)")
    check(same, f"{label} : machines 0..{top - 1}, les 14 potards, avec et sans FUNC : le même descripteur que "
                f"{base} (FUNC + PITCH : PITCH)")
    if after:
        later = {(m, k, f): b.lookup(m, k, f) for m in range(top + 1, top + 1 + after) for k in range(2, 16)
                 for f in (False, True)}
        check(None not in later.values() and FTUN not in later.values()
              and all(later[m, PITCH_KNOB, f] == PITCH for m in range(top + 1, top + 1 + after) for f in (False, True))
              and all(later[m, k, True] == later[m, k, False] for m in range(top + 1, top + 1 + after)
                      for k in range(3, 14)),
              f"{label} : machines {top + 1}..{top + after} (après MACRO) : FUNC + PITCH -> PITCH, FINE sous aucun "
              f"potard, potards 3 à 13 avec FUNC comme sans")
    # 2. le tour de potard avec FUNC : sans MACRO, FINE revient au centre ; ici un pas par cran (au moins)
    reset = {a.edit_func(FTUN, cur, d) for cur in (0, 0x2000, 0x5f00) for d in (0x100, -0x100)}
    check(reset == {0x4000}, f"{base} : FUNC + un tour sur FINE le remet à {sorted(reset)} (le défaut) : pourquoi "
                             f"il faut notre pas")
    cases = [(cur, d) for cur in (0, 0x100, 0x3f00, 0x4000, 0x4080, 0x4100, 0x7e00, 0x7f00, 0x1234)
             for d in (1, 0x100, 0x180, 0x300, -1, -0x100, -0x300, 0x7f00, -0x7f00)]
    bad = [(hex(c), hex(d), b.edit_func(FTUN, c, d)) for c, d in cases if b.edit_func(FTUN, c, d) != want_step(c, d)]
    check(not bad, f"{label} : FUNC + un tour sur FINE (vrai 0x4000b7d6) : arrondi au pas, plus le delta arrondi à des "
                   f"pas entiers (un cran = un pas), borné à 0..0x7f00 ({len(cases)} cas){bad[:3]}")
    pitch = [(b.edit_func(PITCH, c, d), a.edit_func(PITCH, c, d)) for c in (0x4000, 0x4080) for d in (0x100, -0x100)]
    check(all(x == y for x, y in pitch), f"{label} : FUNC + un tour sur PITCH : les demi-tons de l'OS "
                                         f"({', '.join(hex(x) for x, _ in pitch)})")
    # 3. le texte : OFF au centre, kHz à gauche, bits à droite
    shown = [b.text(FTUN, n << 8) for n in range(128)]
    check(shown == [want_text(n) for n in range(128)] and all(len(s) <= 3 for s in shown),
          f"{label} : texte des 128 pas (vrai sprintf) : {shown[0]} .. {shown[63]} {shown[64]} {shown[65]} .. "
          f"{shown[127]}, trois caractères au plus, comme macro.cc les règle")
    check(a.text(FTUN, 0x2000) == "-32", f"{base} : FINE s'affiche -64..63")
    # 4. la fenêtre de valeur (0x4001d818) : sans MACRO, FINE y est une jauge (un sprite) et aucun texte ; avec, le
    # texte, dessiné comme l'OS dessine le texte d'un paramètre sans jauge (son propre chemin, 0x4000a70e)
    gauge, plain = a.popup(FTUN, 0x2000), a.popup(FTUN, 0x2000, text_path=True)
    check(gauge is not None and plain is not None and gauge[1] and not plain[1] and plain[0] != gauge[0],
          f"{base} : la fenêtre de valeur de FINE dessine une jauge (un sprite, 0x40045fe0), "
          f"aucun texte (ce que la machine a montré)")
    steps = (0, 1, 31, 63, 64, 65, 100, 127)
    shots = {n: (b.popup(FTUN, n << 8), b.popup(FTUN, n << 8, text_path=True)) for n in steps}
    bad = [n for n, (x, y) in shots.items() if x is None or y is None or x != y or x[1] or x[0] == gauge[0]]
    check(not bad, f"{label} : fenêtre de valeur de FINE (vrai 0x4001d818) : le texte "
                   f"{', '.join(want_text(n) for n in steps)}, pixel pour pixel celui que l'OS dessine par son chemin "
                   f"texte (0x4000a70e, 0x40071a04, grande police) ; plus de jauge {bad}")
    chars = sorted(set("".join(shown)))
    missing = [c for c in chars if not b.glyph(c)]
    check(not missing and b.glyph("k") == 0, f"{label} : chaque caractère de ces textes ({''.join(chars)}) existe dans "
                                            f"la grande police de la fenêtre (elle n'a pas de minuscules) {missing}")
    if not bad:
        for n in (23, 64, 100):
            print(f"      fenêtre de valeur, FUNC + PITCH à {n - 64:+d} (« {want_text(n)} ») :")
            print(ascii_popup(b.popup(FTUN, n << 8)[0]))
    recs = [(bytes(b.uc.mem_read(UI_REC + 100 * d, 100)), bytes(a.uc.mem_read(UI_REC + 100 * d, 100)))
            for d in range(77)]
    diff = [d for d, (x, y) in enumerate(recs) if x != y]
    check(diff == [FTUN], f"{label} : objets d'interface des 77 descripteurs comme {base}, sauf FINE (pas, texte, dessin "
                          f"de la valeur) : les fenêtres des autres paramètres ne changent pas ({diff})")
