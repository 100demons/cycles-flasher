#!/usr/bin/env python3
"""Preuve du volume et du pan en chiffres sur l'écran principal (notes/44,
tweaks/model-cycles_OS1.13/46-level-pan-values.json).

Le vrai code de l'OS, sur le MAIN OS d'origine et sur le MAIN OS modifié (crochet de démarrage exécuté) :
  - le tick de la tâche de l'interface (0x400081f2 -> 0x400081f8, message 5, 30 Hz) ;
  - le pas de LEVEL/DATA sur l'écran principal (0x4001aab6 -> 0x4001aac8 : 0x4006f73a(événement, pas, 16)) ;
  - le gestionnaire des encodeurs de l'écran principal (0x4001aa4e) et son dessin (0x4001b22a), avec les fonctions
    de l'OS qu'appelle le mod (touche tenue 0x4007faf4 interceptée ; fenêtre d'un paramètre 0x4006b704, rectangle
    0x40070dea, projet + 48 / + 116 exécutés). Le corps de l'original est remplacé par un remplissage connu de l'écran
    (dessin) ou une réponse connue (encodeur), avec ses registres d2-d7/a2-a5 détruits, puis l'épilogue réel.
  Intercepté aussi : projet courant, piste sélectionnée, objet des paramètres de la piste et son pan (vtable[28],
  paramètre 0x1c, 8.8 centré sur 64), volume de la piste.

  1. Écritures : octets d'origine, masques libérés identiques au masque gardé et désignés par la seule constante de
     leur constructeur, aucune écriture différente d'un autre tweak sur les mêmes octets, variables à zéro.
  2. Tick : même appel du service des minuteurs, compteur + 1, pile équilibrée.
  3. Pas : x 2 à l'origine, x 1 modifié ; x 16 en mode rapide des deux côtés.
  4. Encodeur : l'original voit ses arguments, sa réponse est rendue ; LEVEL/DATA -> échéance du volume (pan avec FUNC)
     de la piste sélectionnée = tick + 90, puis demande de redessin ; autre encodeur, piste >= 6 : rien.
  5. Dessin : l'original appelé une fois ; registres et pile rendus ; écritures seulement dans l'écran et les
     drapeaux ; fenêtre d'un paramètre ouverte, échéance passée, piste >= 6 : rien ; passage de 0x7fffffff.
  6. Pixels : pan -64 à 63 et volume 0 à 127 sur un écran rempli au hasard = le modèle (rectangles effacés par
     0x40070dea, chiffres de la police lue à l'œil ci-dessous) ; tout le reste de l'écran inchangé.
  7. Durée : un cran, puis le vrai tick ; affiché jusqu'au tick + 89, plus au tick + 90.
  (--djd) Avec le .syx de djd_oz : même pas, mêmes pixels pour toutes les valeurs, même durée.
  (--show) Dessins ASCII avec les barres d'origine (sprites de l'OS).

    python3 tools/emu/test_level_pan.py --cycles model-cycles_OS1.13.syx \
        [--with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max,boot-anim \
         --syntakt Syntakt_OS1.42.syx] [--djd model-cycles_OS1.13_PAN-Level-values-3s-turn-only.syx] [--show]
"""
import argparse
import json
import pathlib
import random
import re
import struct
import sys

from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED, UC_HOOK_MEM_WRITE
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import sprites                      # noqa: E402
import test_sdvintage as T          # noqa: E402

TWEAK = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13" / "46-level-pan-values.json"
BASE = build.BASE
FAIL = []

STOP, STACK, FAKE = 0x9f000000, 0x9e000000, 0x92000000
THIS, EVT, PROJ, UI = FAKE + 0x1000, FAKE + 0x2000, FAKE + 0x3000, FAKE + 0x4000
BMP, FB, BMP2, FB2 = FAKE + 0x6000, FAKE + 0x7000, FAKE + 0x6100, FAKE + 0x7800
PARAM_OBJ, VT, GETP, SPR = FAKE + 0x8000, FAKE + 0x8100, FAKE + 0x8200, FAKE + 0x9000
TICK_AT, TICK_END, TIMERS = 0x400081f2, 0x400081f8, 0x40090f48
STEP_AT, STEP_END = 0x4001aab6, 0x4001aac8
ENC, ENC_BODY, ENC_EPI = 0x4001aa4e, 0x4001aa56, 0x4001abce      # épilogue : move.b d5,d0 ; movem ; lea ; rts
DRAW, DRAW_BODY, DRAW_EPI = 0x4001b22a, 0x4001b232, 0x4001b84e   # épilogue : movem -64(fp) ; unlk ; rts
CUR_PROJ, SEL_TRACK, KEY_HELD, NEEDS_REDRAW = 0x400cf866, 0x40012412, 0x4007faf4, 0x40076082
UISTATES, TRACK_PARAM, TRACK_LEVEL, FILL_RECT = 0x400cf9a8, 0x400097f0, 0x40009c5a, 0x40070dea
BITMAP = 0x40070172                                             # Bitmap(this, largeur, hauteur, image, masque)
DJD_VARS = (0x423393a4, 0x423393a8, 0x423393c8)                  # compteur, pan, volume du .syx de djd_oz
SAVED = [mk.UC_M68K_REG_D2 + i for i in range(6)] + [mk.UC_M68K_REG_A2 + i for i in range(5)]

# La police de djd_oz telle qu'on la lit (ligne du haut en premier), indépendante de lp_font.
FONT = {
    "0": "### #.# #.# #.# #.# #.# ###", "1": ".#. ##. .#. .#. .#. .#. ###", "2": "### ..# ..# ### #.. #.. ###",
    "3": "### ..# ..# ### ..# ..# ###", "4": "#.# #.# #.# ### ..# ..# ..#", "5": "### #.. #.. ### ..# ..# ###",
    "6": "### #.. #.. ### #.# #.# ###", "7": "### ..# ..# .#. .#. .#. .#.", "8": "### #.# #.# ### #.# #.# ###",
    "9": "### #.# #.# ### ..# ..# ###", "-": "... ... ... ### ... ... ...",
}
PAN_RECT, LVL_RECT = (114, 21, 127, 29), (65, 8, 77, 16)        # (x0, y0, x1, y1) passés à 0x40070dea


def check(ok, msg):
    print(f"  {'ok   ' if ok else 'ECHEC'} {msg}", flush=True)
    if not ok:
        FAIL.append(msg)


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


class Rig:
    """Le MAIN OS en mémoire, le crochet de démarrage exécuté (copie de .data en SRAM ; pour le .syx de djd_oz, la
    copie de son code en 0x42339000). Les fonctions interceptées lisent self.st."""

    def __init__(self, img, var):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
        uc.mem_map(0x40000000, 0x02400000)
        uc.mem_map(0x80000000, 0x00020000)
        uc.mem_map(0x90000000, 0x10000000)
        uc.mem_write(BASE, img)
        self.cnt, self.pan, self.lvl = var
        self.bad, self.writes, self.icount, self.counting = [], [], 0, False
        self.st = {"track": 0, "func": False, "pan": 0, "level": 0, "pattern": bytes(1024), "handled": 1}
        self.seen = {}
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: self.bad.append(addr) or False)
        uc.hook_add(UC_HOOK_MEM_WRITE, lambda u, a, addr, s, v, d: self.writes.append(addr))
        uc.hook_add(UC_HOOK_CODE, self._count)
        self.call(0x4000045c)
        self.stub(CUR_PROJ, lambda a: PROJ)
        self.stub(SEL_TRACK, lambda a: self.st["track"])
        self.stub(KEY_HELD, lambda a: int(self.st["func"] and a[0] == 1))
        self.stub(NEEDS_REDRAW, lambda a: self.seen.setdefault("redraw", []).append(a[0]) or 0)
        self.stub(UISTATES, lambda a: UI)
        self.stub(TRACK_PARAM, lambda a: self.seen.setdefault("obj", []).append(a[1]) or PARAM_OBJ)
        self.stub(GETP, lambda a: self.seen.setdefault("param", []).append(a[1]) or ((self.st["pan"] + 64) << 8 | 0x7f))
        self.stub(TRACK_LEVEL, lambda a: self.seen.setdefault("lvl", []).append(a[1]) or self.st["level"])
        self.stub(TIMERS, lambda a: self.seen.setdefault("timers", []).append(a[0]) or 0)
        uc.mem_write(UI, bytes(0x200))
        uc.mem_write(GETP, b"\x4e\x71\x4e\x75")
        self.w32(PARAM_OBJ, VT)
        self.w32(VT + 28, GETP)
        uc.hook_add(UC_HOOK_CODE, self._enc_body, begin=ENC_BODY, end=ENC_BODY)
        uc.hook_add(UC_HOOK_CODE, self._draw_body, begin=DRAW_BODY, end=DRAW_BODY)
        self.call(BITMAP, BMP, 128, 64, FB, 0)
        self.call(BITMAP, BMP2, 128, 64, FB2, 0)

    def _count(self, uc, addr, size, _):
        if self.counting:
            self.icount += 1

    def r32(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def w32(self, a, v):
        self.uc.mem_write(a, struct.pack(">I", v & 0xffffffff))

    def stub(self, addr, fn):
        def hook(uc, a, size, _):
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            r = fn(struct.unpack(">6I", uc.mem_read(sp + 4, 24)))
            uc.reg_write(mk.UC_M68K_REG_D0, r & 0xffffffff)
            uc.reg_write(mk.UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        self.uc.hook_add(UC_HOOK_CODE, hook, begin=addr, end=addr)

    def _clobber(self, regs):
        for i, r in enumerate(regs):                # les registres que l'original garde, il s'en sert
            self.uc.reg_write(r, 0x0bad0000 + i)

    def _enc_body(self, uc, addr, size, _):
        """Corps du gestionnaire d'origine, après ses deux instructions déplacées."""
        sp = uc.reg_read(mk.UC_M68K_REG_A7)
        self.seen.setdefault("enc", []).append((self.r32(sp + 36), self.r32(sp + 40)))
        self._clobber(SAVED[:8])                    # d2-d7/a2-a3
        uc.reg_write(mk.UC_M68K_REG_D5, self.st["handled"])
        uc.reg_write(mk.UC_M68K_REG_PC, ENC_EPI)

    def _draw_body(self, uc, addr, size, _):
        """Corps du dessin d'origine : l'écran prend le motif connu."""
        fp = uc.reg_read(mk.UC_M68K_REG_A6)
        self.seen.setdefault("draw", []).append((self.r32(fp + 8), self.r32(fp + 12)))
        uc.mem_write(FB, self.st["pattern"])
        self._clobber(SAVED[:10])                   # d2-d7/a2-a5
        uc.reg_write(mk.UC_M68K_REG_PC, DRAW_EPI)

    def call(self, fn, *args, regs=None, count=False):
        sp = STACK - 4 * (len(args) + 1)
        self.uc.mem_write(sp, struct.pack(">I", STOP) + b"".join(struct.pack(">I", a & 0xffffffff) for a in args))
        self.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        for r, v in (regs or {}).items():
            self.uc.reg_write(r, v)
        self.writes, self.seen, self.icount, self.counting = [], {}, 0, count
        self.uc.emu_start(fn, STOP, count=5_000_000)
        self.counting = False
        return self.uc.reg_read(mk.UC_M68K_REG_D0)

    def tick(self):
        """Le vrai tick de la tâche de l'interface : 0x400081f2 (jsr) -> 0x400081f8."""
        sp = STACK - 64
        self.w32(sp, 0x5a5a0005)
        self.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        self.seen = {}
        self.uc.emu_start(TICK_AT, TICK_END, count=1000)
        return self.seen.get("timers"), self.uc.reg_read(mk.UC_M68K_REG_A7) == sp

    def step(self, delta, fast):
        """Le pas de LEVEL/DATA rendu par 0x4006f73a, avec les arguments que pousse l'écran principal."""
        self.uc.mem_write(EVT, struct.pack(">IIIIiB3x", 0x400fbebc, 0, 0, 1, delta, fast))
        sp = STACK - 64
        self.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        self.uc.reg_write(mk.UC_M68K_REG_D4, EVT)
        self.uc.emu_start(STEP_AT, STEP_END, count=1000)
        ok = self.uc.reg_read(mk.UC_M68K_REG_A7) == sp - 12
        return s32(self.uc.reg_read(mk.UC_M68K_REG_D0)), ok

    def turn(self, enc=1, delta=1):
        """Un cran d'un encodeur sur l'écran principal."""
        self.uc.mem_write(EVT, struct.pack(">IIIIiB3x", 0x400fbebc, 0, 0, enc, delta, 0))
        pre = {r: 0x01010101 * (k + 1) for k, r in enumerate(SAVED)}
        d0 = self.call(ENC, THIS, EVT, regs=pre)
        post = {r: self.uc.reg_read(r) for r in SAVED}
        return d0 & 0xff, post == pre and self.uc.reg_read(mk.UC_M68K_REG_A7) == STACK - 8

    def draw(self):
        pre = {r: 0x01010101 * (k + 1) for k, r in enumerate(SAVED)}
        self.call(DRAW, THIS, BMP, regs=pre, count=True)
        post = {r: self.uc.reg_read(r) for r in SAVED}
        return bytes(self.uc.mem_read(FB, 1024)), post == pre and self.uc.reg_read(mk.UC_M68K_REG_A7) == STACK - 8

    def arm(self, which, track, deadline, flag=1):
        v = self.pan if which == "pan" else self.lvl
        self.w32(v + 4 * track, deadline)
        self.uc.mem_write(v + 24 + track, bytes([flag]))

    def flags(self, which):
        return list(self.uc.mem_read((self.pan if which == "pan" else self.lvl) + 24, 6))

    def deadlines(self, which):
        return [self.r32((self.pan if which == "pan" else self.lvl) + 4 * t) for t in range(6)]

    def reset(self):
        self.uc.mem_write(self.pan, bytes(32))
        self.uc.mem_write(self.lvl, bytes(32))
        self.uc.mem_write(UI, bytes(0x200))
        self.st.update(track=0, func=False, handled=1)


def pix(fb, x, y):
    w = struct.unpack(">I", fb[(x * 2 + (y >> 5)) * 4:(x * 2 + (y >> 5)) * 4 + 4])[0]
    return w >> (31 - (y & 31)) & 1


def setpix(fb, x, y):
    i = (x * 2 + (y >> 5)) * 4
    w = struct.unpack(">I", fb[i:i + 4])[0] | 1 << (31 - (y & 31))
    fb[i:i + 4] = struct.pack(">I", w)


def text_pan(v):
    """(x, signe) : à partir de x = 115, « - », dizaine si non nulle, unité."""
    s = ("-" if v < 0 else "") + str(abs(v))
    return [(115 + 4 * i, c) for i, c in enumerate(s)]


def text_lvl(v):
    """(x, signe) : aligné à droite sur x = 66, 70, 74."""
    s = str(v)
    return [(78 - 4 * (len(s) - i), c) for i, c in enumerate(s)]


def model(rg, pattern, pan=None, level=None):
    """L'écran attendu : le motif, les rectangles effacés par 0x40070dea, les chiffres de FONT (ligne du haut en y0 + 6)."""
    rg.uc.mem_write(FB2, pattern)
    for on, rect in ((pan, PAN_RECT), (level, LVL_RECT)):
        if on is not None:
            rg.call(FILL_RECT, BMP2, *rect, 0)
    fb = bytearray(rg.uc.mem_read(FB2, 1024))
    for v, place, y0 in ((pan, text_pan, 22), (level, text_lvl, 9)):
        if v is None:
            continue
        for x, c in place(v):
            for r, row in enumerate(FONT[c].split()):
                for k, ch in enumerate(row):
                    if ch == "#":
                        setpix(fb, x + k, y0 + 6 - r)
    return bytes(fb)


def ascii_screen(fb, x0=64, x1=128, y0=0, y1=40):
    out = ["      " + "".join(str((x // 10) % 10) if x % 10 == 0 else " " for x in range(x0, x1))]
    for y in range(y1 - 1, y0 - 1, -1):                    # y = 0 en bas de l'écran
        out.append(f"y={y:2d}  " + "".join("#" if pix(fb, x, y) else "." for x in range(x0, x1)))
    return "\n".join(out)


def writes_ok(stock, img, tweak, others):
    for w in tweak["writes"]:
        o, old = w["off"], bytes.fromhex(w["old"])
        check(stock[o:o + len(old)] == old, f"octets d'origine en {o + BASE:#x} ({len(old)} o)")
    for mask in (0x4018f4b4, 0x4018fc74):
        size, ref, _, shared = sprites.MASKS[mask]
        check(stock[mask - BASE:mask - BASE + size] == stock[shared - BASE:shared - BASE + size],
              f"masque {mask:#x} identique au masque gardé {shared:#x}")
        refs = [m.start() + BASE for m in re.finditer(re.escape(struct.pack(">I", mask)), stock)]
        check(refs == [ref] and img[ref - BASE:ref - BASE + 4] == struct.pack(">I", shared),
              f"seule référence au masque {mask:#x} : la constante de son constructeur ({ref:#x}), redirigée")
    clash = []
    for t in others:
        for v in t["writes"]:
            a, b = v["off"], v["off"] + len(v["old"]) // 2
            for w in tweak["writes"]:
                c, d = w["off"], w["off"] + len(w["old"]) // 2
                if a < d and c < b and (v["off"], v["new"]) != (w["off"], w["new"]):
                    clash.append(f"{t['id']}@{a + BASE:#x}")
    check(not clash, f"aucun autre tweak n'écrit autre chose sur ces octets ({len(others)} tweaks) {clash[:4]}")
    lo = int(tweak["symbols"]["lp_cnt"], 16) - BASE
    check(img[lo:lo + 68] == bytes(68), "compteur et échéances à zéro dans l'image (rechargée à chaque démarrage)")


def tick(base, img, var):
    out = {}
    for name, im in (("origine", base), ("modifié", img)):
        r = Rig(im, var)
        r.w32(var[0], 0xfffffffe)
        out[name] = [r.tick() for _ in range(3)]
        cnt = r.r32(var[0])
    check(out["origine"] == out["modifié"] == [([0x5a5a0005], True)] * 3,
          "0x40090f48 appelée avec le même argument, pile équilibrée, retour en 0x400081f8")
    check(cnt == 1, f"compteur + 1 par tick (0xfffffffe + 3 = {cnt}, il fait le tour)")


def step(base, img, djd):
    cases = ((1, 0), (-1, 0), (3, 0), (30, 0), (-7, 0), (1, 1), (-2, 1))
    out = {}
    for name, (im, var) in [("origine", base), ("modifié", img)] + ([("djd_oz", djd)] if djd else []):
        r = Rig(im, var)
        out[name] = [r.step(d, f) for d, f in cases]
        print(f"     {name:8} (cran, rapide) -> pas : "
              + ", ".join(f"({d}, {f}) -> {s}" for (d, f), (s, _) in zip(cases, out[name])))
    check(all(ok for _, ok in out["origine"] + out["modifié"]), "pile : les 3 arguments, rien d'autre")
    check([s for s, _ in out["origine"]] == [2, -2, 6, 60, -14, 16, -32], "origine : 2 par cran (16 en rapide)")
    check([s for s, _ in out["modifié"]] == [1, -1, 3, 30, -7, 16, -32], "modifié : 1 par cran (16 en rapide)")
    if djd:
        check(out["djd_oz"] == out["modifié"], "même pas que le .syx de djd_oz")


def encoder(img, var):
    r = Rig(img, var)
    r.w32(var[0], 1000)
    d0, ok = r.turn()
    check(r.seen.get("enc") == [(THIS, EVT)], "l'original voit ses deux arguments (this, événement) comme à l'origine")
    check(d0 == 1 and ok, "sa réponse est rendue, d2-d7/a2-a6 et pile rendus")
    for handled in (0, 1):
        r.reset()
        r.st.update(track=2, handled=handled)
        d0, ok = r.turn()
        check(d0 == handled and r.deadlines("lvl")[2] == 1090 and r.flags("lvl") == [0, 0, 1, 0, 0, 0]
              and r.flags("pan") == [0] * 6 and r.seen.get("redraw") == [THIS],
              f"LEVEL/DATA (réponse {handled}) : volume de la piste 3, échéance tick + 90, puis 0x40076082(this)")
    r.reset()
    r.st.update(track=5, func=True)
    r.turn(delta=-1)
    check(r.deadlines("pan")[5] == 1090 and r.flags("pan") == [0, 0, 0, 0, 0, 1] and r.flags("lvl") == [0] * 6,
          "FUNC + LEVEL/DATA : pan de la piste 6")
    for enc, track, what in ((0, 0, "encodeur 0"), (2, 0, "encodeur 2"), (1, 6, "piste 6"), (1, 0xffffffff, "piste -1")):
        r.reset()
        r.st.update(track=track)
        d0, ok = r.turn(enc=enc)
        check(r.flags("pan") == r.flags("lvl") == [0] * 6 and "redraw" not in r.seen and d0 == 1 and ok and not r.bad,
              f"{what} : rien (réponse rendue)")


def draw(img, var):
    r = Rig(img, var)
    rnd = random.Random(42)
    r.st.update(pattern=bytes(rnd.randrange(256) for _ in range(1024)), pan=-5, level=100)
    r.w32(var[0], 1000)
    r.arm("pan", 0, 1050)
    r.arm("lvl", 0, 1050)
    fb, ok = r.draw()
    cost = r.icount
    check(r.seen.get("draw") == [(THIS, BMP)], "l'original est appelé une fois, mêmes arguments")
    check(ok, "d2-d7/a2-a6 et pile rendus")
    keep = set(range(FB, FB + 1024)) | set(range(STACK - 0x1000, STACK))
    out = sorted({hex(a) for a in r.writes if a not in keep})
    check(not out and not r.bad, f"écritures seulement dans l'écran et la pile {out[:4]}")
    check(r.seen.get("param") == [0x1c] and r.seen.get("obj") == [0] and r.seen.get("lvl") == [0],
          "pan lu comme l'OS : vtable[28](0x400097f0(kit, piste), 0x1c) ; volume : 0x40009c5a(kit, piste)")
    check(fb == model(r, r.st["pattern"], -5, 100), "pan -5 et volume 100 dessinés comme le modèle")
    print(f"     dessin des deux chiffres : {cost} instructions (en plus de l'original), au plus 30 fois par seconde")
    cases = [("fenêtre d'un paramètre ouverte (UIStates + 88)", dict(popup=1), (1, 1), (None, None)),
             ("tick = échéance : drapeaux effacés", dict(cnt=1050), (0, 0), (None, None)),
             ("tick = échéance - 1 : dessiné", dict(cnt=1049), (1, 1), (-5, 100)),
             ("échéance seulement pour le pan", dict(lvl=0), (1, 0), (-5, None)),
             ("échéance d'une autre piste", dict(track=3), (1, 1), (None, None)),
             ("piste 6", dict(track=6), (1, 1), (None, None)),
             ("passage de 0x7fffffff à 0x80000000", dict(cnt=0x7ffffff0, dl=0x80000010), (1, 1), (-5, 100)),
             ("échéance juste passée, après 0x7fffffff", dict(cnt=0x80000010, dl=0x80000010), (0, 0), (None, None))]
    for what, c, flags, shown in cases:
        r.reset()
        r.w32(var[0], c.get("cnt", 1000))
        r.w32(UI + 88, c.get("popup", 0))
        r.st["track"] = c.get("track", 0)
        r.arm("pan", 0, c.get("dl", 1050))
        r.arm("lvl", 0, c.get("dl", 1050), c.get("lvl", 1))
        fb, ok = r.draw()
        check(fb == model(r, r.st["pattern"], *shown) and (r.flags("pan")[0], r.flags("lvl")[0]) == flags and ok,
              f"{what} : {'chiffres ' + str(shown) if shown != (None, None) else 'rien'}, drapeaux {flags}")


def pixels(img, djd, var):
    rigs = [("modifié", Rig(img, var))] + ([("djd_oz", Rig(*djd))] if djd else [])
    rnd = random.Random(7)
    pat = bytes(rnd.randrange(256) for _ in range(1024))
    bad, diff_djd = [], []
    for which, values in (("pan", range(-64, 64)), ("lvl", range(128))):
        for v in values:
            fbs = []
            for name, r in rigs:
                r.reset()
                r.st.update(pattern=pat, pan=v if which == "pan" else 0, level=v if which == "lvl" else 0)
                r.w32(r.cnt, 500)
                r.arm(which, 0, 590)
                fbs.append(r.draw()[0])
            want = model(rigs[0][1], pat, v if which == "pan" else None, v if which == "lvl" else None)
            if fbs[0] != want:
                bad.append(f"{which} {v}")
            if djd and fbs[1] != fbs[0]:
                diff_djd.append(f"{which} {v}")
    check(not bad, f"pan -64 à 63 et volume 0 à 127 : chiffres du modèle, reste de l'écran inchangé {bad[:6]}")
    if djd:
        check(not diff_djd, f"mêmes pixels que le .syx de djd_oz, pour les 256 valeurs {diff_djd[:6]}")
    r = rigs[0][1]
    for what, rect in (("pan", PAN_RECT), ("volume", LVL_RECT)):
        r.uc.mem_write(FB2, b"\xff" * 1024)
        r.call(FILL_RECT, BMP2, *rect, 0)
        fb = bytes(r.uc.mem_read(FB2, 1024))
        off = [(x, y) for x in range(128) for y in range(64) if not pix(fb, x, y)]
        print(f"     rectangle effacé par 0x40070dea pour le {what} : x {min(x for x, _ in off)}..{max(x for x, _ in off)}"
              f", y {min(y for _, y in off)}..{max(y for _, y in off)} ({len(off)} points)")


def duration(img, djd, var):
    out = {}
    for name, (im, v) in [("modifié", (img, var))] + ([("djd_oz", djd)] if djd else []):
        r = Rig(im, v)
        r.w32(v[0], 0x7fffffc0)                            # le compteur passe 0x7fffffff pendant l'affichage
        r.st.update(pattern=bytes(1024), level=64)
        r.turn()
        seq = ""
        for _ in range(95):
            fb = r.draw()[0]
            seq += "1" if fb != bytes(1024) else "0"
            r.tick()
        out[name] = seq
    check(out["modifié"] == "1" * 90 + "0" * 5, f"un cran au tick t : affiché aux ticks t à t + 89, plus à t + 90 "
          f"({out['modifié'].count('1')} ticks = 3,0 s)")
    if djd:
        check(out["djd_oz"] == out["modifié"], "même durée que le .syx de djd_oz")


def show(base, img, var):
    """Les barres d'origine (sprites de l'OS) puis l'incrustation, moitié droite de l'écran."""
    pan_fr = [0x4017a694 + 200 * k for k in range(31)]
    lvl_fr = [0x40170e90 + 200 * k for k in range(15)]
    r = Rig(img, var)
    for pan, level in ((-64, 0), (0, 7), (63, 99), (-1, 100), (10, 127)):
        r.uc.mem_write(FB, bytes(1024))
        fp, fl = 30 * (pan + 64) // 127, (0 if level == 0 else (level - 1) * 13 // 126 + 1)
        r.call(BITMAP, SPR, 50, 9, pan_fr[fp], 0x4017a5cc)
        r.call(0x40071da4, BMP, SPR, 96, 25, 1)
        r.call(BITMAP, SPR + 32, 50, 9, lvl_fr[fl], 0x40170dc8)
        r.call(0x40071da4, BMP, SPR + 32, 96, 12, 1)
        bars = bytes(r.uc.mem_read(FB, 1024))
        r.reset()
        r.st.update(pattern=bars, pan=pan, level=level)
        r.w32(var[0], 500)
        r.arm("pan", 0, 590)
        r.arm("lvl", 0, 590)
        print(f"\n--- pan {pan:+d}, volume {level} : origine")
        print(ascii_screen(bars))
        print(f"--- pan {pan:+d}, volume {level} : avec les chiffres")
        print(ascii_screen(r.draw()[0]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True)
    ap.add_argument("--with", dest="others", default="", help="autres tweaks appliqués avant (ex. 6ch-usbup,model-tg)")
    ap.add_argument("--syntakt", help="Syntakt_OS1.42.syx (ou 1.41), pour les moteurs du Syntakt")
    ap.add_argument("--djd", help="le .syx de djd_oz (PAN-Level-values-3s-turn-only), pour comparer")
    ap.add_argument("--show", action="store_true", help="dessins ASCII avec les barres d'origine")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    files = {json.loads(f.read_text(encoding="utf-8"))["id"]: f for f in TWEAK.parent.glob("[0-9]*.json")}
    every = [json.loads(f.read_text(encoding="utf-8")) for i, f in files.items() if i != "level-pan-values"]
    tweaks = [json.loads(files[i].read_text(encoding="utf-8")) for i in args.others.split(",") if i]
    tweak = json.loads(TWEAK.read_text(encoding="utf-8"))
    pl, _ = build.build_payload(tweaks, stock, args.syntakt)  # Model-TG : son code est ajouté après l'image
    base = build.apply_writes(stock, sorted(tweaks, key=lambda t: t["order"]))[0] + pl
    img = build.apply_writes(stock, sorted(tweaks + [tweak], key=lambda t: t["order"]))[0] + pl
    var = tuple(int(tweak["symbols"][n], 16) for n in ("lp_cnt", "lp_pan", "lp_lvl"))
    djd = (T.main_os_from_syx(args.djd), DJD_VARS) if args.djd else None
    print(f"firmware : {', '.join(t['id'] for t in sorted(tweaks + [tweak], key=lambda t: t['order']))}")
    print("1. écritures")
    writes_ok(stock, img, tweak, every)
    print("2. tick de l'interface (0x400081f2)")
    tick(base, img, var)
    print("3. pas de LEVEL/DATA (0x4006f73a)")
    step((base, var), (img, var), djd)
    print("4. gestionnaire des encodeurs (0x4001aa4e)")
    encoder(img, var)
    print("5. dessin de l'écran principal (0x4001b22a)")
    draw(img, var)
    print("6. pixels, toutes les valeurs")
    pixels(img, djd, var)
    print("7. durée d'affichage")
    duration(img, djd, var)
    if args.show:
        show(base, img, var)
    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ÉCHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
