#!/usr/bin/env python3
"""Preuve du navigateur multiligne (notes/40, tweaks/model-cycles_OS1.13/44-multiline-browser.json).

Le vrai dessin du navigateur (ModelsFileManager, 0x400a539c) est exécuté sur le MAIN OS d'origine (ou avec les autres
tweaks seuls) et sur le MAIN OS modifié. Il dessine dans un vrai écran de 128 x 64 (un Bitmap construit par l'OS,
0x40070172) avec les vraies polices (initialisation statique 0x400e7ccc), les vraies fonctions de texte et de
rectangles, la vraie liste de base (sélection, 1re ligne visible, 0x4007266e, 0x40072524), la vraie réaction du
navigateur à une nouvelle sélection (vt[76] 0x400a64be, et 0x4004067c dans un sous-dossier de +Drive), sa vraie entrée
dans un dossier (0x4003f5c6) et les vraies chaînes de l'OS. Seuls les objets de données sont factices : les entrées
du dossier (nombre, nom, dossier ?), la racine de +Drive (0x4007cce4), le son chargé (0x4006b736, 0x4006be48),
l'écoute du son sélectionné (0x400a63ac), l'allocation mémoire (0x400802e0, 0x400802ec) et l'horloge du défilement
(0x40a78e28).

  1. Écritures : octets d'origine, aucun recouvrement avec les autres tweaks (sauf écritures identiques), rien sur
     l'accroche du défilement des noms (0x400a55a1..0x400a55a3, browser-scroll et Model-TG), le code dans le masque
     libéré, que seul son constructeur désigne et qui pointe maintenant sur un masque identique (vérifié dans l'image
     modifiée).
  2. Écran : 3 noms dans l'ordre, le 1er en haut, « > » sur la ligne du curseur ; titre, compteur et « Fn=Menu »
     identiques à l'origine ; rien au-delà de x = 120 (les flèches) ; la pile et les registres rendus intacts.
  3. Déplacement du curseur avec la vraie liste de l'OS, jusqu'au bout et retour : le nom sous le curseur est celui
     que montre l'origine, la liste défile d'une ligne quand le curseur sort de l'écran. Petits dossiers (1 à 3
     entrées, à la racine et ailleurs, où l'OS compte une entrée de moins et part de la 2e) : toutes leurs entrées
     sont à l'écran, le curseur aussi, dans tous les sens. Sous-dossier de +Drive (l'entrée 0 y est le retour au
     dossier parent, interdite au curseur) : même suite de sélections qu'à l'origine, « > » qui suit le curseur comme
     ailleurs, l'entrée 0 jamais à l'écran, avec ou sans dessin entre deux déplacements.
  4. Son chargé : son nom inversé, sur sa ligne seulement. Dossiers et entrée spéciale : leur repère.
  5. Dossier vide : « <EMPTY> » sur la 1re ligne.
  6. Noms longs avec browser-scroll ou Model-TG (--with) : seule la ligne du curseur passe par le défilement, et
     défile ; les autres restent en place.

    python3 tools/emu/test_multiline_browser.py --cycles model-cycles_OS1.13.syx \
        [--with model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,trig-hold,arp --syntakt Syntakt_OS1.42.syx] [--png dossier]
"""
import argparse
import json
import pathlib
import struct
import sys
import zlib

from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import sprites                      # noqa: E402
import test_sdvintage as T          # noqa: E402

TWEAK = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13" / "44-multiline-browser.json"
BASE = build.BASE
STOP, STACK = 0x90000100, 0x90010000
FAIL = []

DRAW = 0x400a539c                 # ModelsFileManager : dessin (vt[120])
VTABLE, VT_LEN = 0x401183ec, 0xb8
MOVE = 0x40072524                 # liste de base : déplacer la sélection de n
ENTER = 0x4003f5c6                # entrée dans un dossier : sélection et 1re ligne
FONTS_INIT = 0x400e7ccc           # initialisation statique des polices
BITMAP = 0x40070172               # Bitmap(this, largeur, hauteur, image, masque)
SCROLL_STUB = 0x40147f22          # défilement des noms longs (browser-scroll, et sa copie dans Model-TG)
SCROLL_HOOK = 0x400a55a1          # ses 3 octets dans l'appel 0x400a559e
TICK = 0x40a78e28                 # horloge lue par le défilement
LOOP_HEAD = 0x400a5612            # tête de la boucle des lignes
SPRITES = {                       # pour les images (--png) : flèches et icônes du navigateur
    0x40fe20dc: (7, 4, 0x40153dac, 0x40153d90), 0x40fe2b58: (7, 4, 0x40162ba0, 0x40162b84),
    0x40fe1b4c: (7, 4, 0x4014a644, 0x4014a628), 0x40fe2a50: (7, 4, 0x40162328, 0x4016230c),
    0x40fe2d60: (25, 22, 0x401643ec, 0x40164388), 0x40fe3824: (24, 22, 0x4017bf2c, 0x4017becc),
}
NAMES = ["KICKS", "BD CLASSIC", "SD VINTAGE BRUSHED LONG NAME", "HH CLOSED", "CY RIDE BELL", "PERC WOODBLOCK",
         "TONE SUB BASS", "CHORD MINOR SEVENTH"]
FOLDERS = {0}


def check(ok, msg):
    print(("  ok    " if ok else "  ECHEC ") + msg, flush=True)
    if not ok:
        FAIL.append(msg)


class Browser:
    """Le navigateur de l'OS sur un objet en mémoire, et son écran."""
    THIS, VT, FOLDER, CANVAS, BUF = 0x92000000, 0x92001000, 0x92002000, 0x92004000, 0x92005000
    ITEMS, HEAP, FAKE = 0x93000000, 0x94000000, 0x95000000

    def __init__(self, img, names=NAMES, folders=FOLDERS, special=False, loaded=None, icons=False, drive=False):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
        uc.mem_map(0x40000000, 0x02400000)            # image (et l'ajout de Model-TG) + BSS
        uc.mem_write(BASE, img)
        uc.mem_map(0x90000000, 0x08000000)            # pile, objets factices, tas
        uc.mem_write(STOP, b"\x4e\x71\x4e\x71")
        self.names, self.folders, self.special, self.loaded = list(names), set(folders), special, loaded
        self.drive = drive or special                 # liste de +Drive (vt[152] : 640 == 632) ; special : sa racine
        self.bad, self.trace, self.hooks, self.watch, self.heap = [], [], {}, {}, self.HEAP
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: self.bad.append(addr) or False)
        uc.hook_add(UC_HOOK_CODE, self._hook)
        self.call(FONTS_INIT)
        self.call(BITMAP, self.CANVAS, 128, 64, self.BUF, self.BUF + 0x800)
        if icons:
            for obj, args in SPRITES.items():
                self.call(BITMAP, obj, *args)
        self._setup()

    def u32(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def w32(self, a, v):
        self.uc.mem_write(a, struct.pack(">I", v & 0xffffffff))

    def alloc(self, n):
        a, self.heap = self.heap, self.heap + ((n + 15) & ~15)
        return a

    def cow(self, s):
        """Une chaîne de la libstdc++ de l'OS (longueur, capacité, références, texte) ; rend son pointeur."""
        b = s.encode() + b"\0"
        rep = self.alloc(12 + len(b))
        self.uc.mem_write(rep, struct.pack(">III", len(s), len(s), 100) + b)
        return rep + 12

    def _hook(self, uc, addr, size, ud):
        if addr in self.watch:
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            self.trace.append((self.watch[addr], sp, struct.unpack(">6I", uc.mem_read(sp + 4, 24))))
        if addr in self.hooks:                        # fonction interceptée : rts
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            ret = self.hooks[addr](struct.unpack(">6I", uc.mem_read(sp + 4, 24)))
            uc.reg_write(mk.UC_M68K_REG_D0, (ret or 0) & 0xffffffff)
            uc.reg_write(mk.UC_M68K_REG_PC, self.u32(sp))
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)

    def call(self, fn, *args, count=20_000_000):
        sp = STACK - 0x400
        self.uc.mem_write(sp, struct.pack(">I" + "I" * len(args), STOP, *[a & 0xffffffff for a in args]))
        self.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        self.uc.emu_start(fn, STOP, count=count)
        return self.uc.reg_read(mk.UC_M68K_REG_D0)

    def fake(self, k, fn):
        """Une fonction interceptée à l'adresse factice k."""
        a = self.FAKE + 16 * k
        self.uc.mem_write(a, b"\x4e\x75")
        self.hooks[a] = fn
        return a

    def _setup(self):
        uc, t = self.uc, self.THIS
        a0 = lambda: uc.reg_read(mk.UC_M68K_REG_A0)    # noqa: E731 (retour par valeur : son adresse en a0)
        # la table virtuelle du navigateur, avec ses données factices : vt[12] nombre, vt[16] entrée
        uc.mem_write(self.VT, bytes(uc.mem_read(VTABLE, VT_LEN)))
        self.w32(self.VT + 12, self.fake(0, lambda a: len(self.names)))

        def entry(a):
            self.w32(a0(), self.ITEMS + a[1])
            self.w32(a0() + 4, 0)
        self.w32(self.VT + 16, self.fake(1, entry))

        def name_of(a):                               # 0x40073236 : le nom de l'entrée
            self.w32(a0(), self.cow(self.names[a[0] - self.ITEMS]))

        def shown(a):                                 # 0x400a425e : le nom affiché (ici le même)
            self.w32(a0(), self.cow(bytes(uc.mem_read(self.u32(a[1]), 64)).split(b"\0")[0].decode()))
        self.hooks.update({0x40073236: name_of, 0x400a425e: shown,
                           0x400802e0: lambda a: self.alloc(a[0]), 0x400802ec: lambda a: 0,
                           0x400a63ac: lambda a: 1})          # vt[76] : écoute du son sélectionné
        # le dossier : vt[28](dossier, i) -> l'entrée i est-elle un dossier ?
        fvt = self.FOLDER + 0x100
        for k in range(32):
            self.w32(fvt + 4 * k, self.fake(16 + k, lambda a: 0))
        self.w32(fvt + 28, self.fake(15, lambda a: 1 if a[1] in self.folders else 0))
        self.w32(self.FOLDER, fvt)
        rows = struct.unpack(">H", bytes(uc.mem_read(0x400a69b4, 2)))[0]    # pea du constructeur 0x400a68fc
        font = self.u32(0x4003f752)                                          # police des noms (0x4003f6b0)
        for off, v in ((16, 0), (20, 0), (24, 0), (28, rows), (32, 1), (632, self.FOLDER), (688, self.FOLDER),
                       (640, self.FOLDER if self.drive else self.FOLDER + 0x40), (648, 0x40ea14cc), (652, font),
                       (656, 1), (660, 0), (680, 1)):
            self.w32(t + off, v)
        self.w32(t, self.VT)
        self.w32(t + 584, self.cow("SOUNDS"))
        self.hooks.update({
            0x4007cce4: lambda a: 1 if self.special else 0,   # entrée spéciale en fin de liste
            0x4007cd30: lambda a: 0,                          # « Fn=Menu »
            0x400cf9a8: lambda a: self.FAKE + 0x1000,         # UIStates
            0x4006b736: lambda a: 0 if self.loaded is None else 1,
            0x4006be48: lambda a: self.w32(uc.reg_read(mk.UC_M68K_REG_A6) - 20, self.loaded),   # son chargé
            0x400cf044: lambda a: 0, 0x400cf866: lambda a: 0, 0x4000eb90: lambda a: 0, 0x40012412: lambda a: 0,
            0x40069b84: lambda a: 0,                          # défilement : demande de rafraîchissement
        })
        for a, n in ((0x4007199c, "texte"), (0x40070f6e, "inversé"), (0x40071da4, "image"), (SCROLL_STUB, "défile"),
                     (LOOP_HEAD, "boucle")):
            self.watch[a] = n

    def select(self, sel, top=0):
        self.w32(self.THIS + 16, sel)
        self.w32(self.THIS + 20, top)

    def move(self, n):
        self.call(MOVE, self.THIS, n)

    def enter(self):
        """Entrée dans le dossier (0x4003f5c6) : à la racine, sélection 0 ; dans un sous-dossier de +Drive, a2[680]."""
        self.call(ENTER, self.THIS)

    def state(self):
        return tuple(self.u32(self.THIS + k) for k in (16, 20, 24))     # sélection, 1re ligne, écart

    def draw(self, tick=0):
        self.w32(TICK, tick)
        self.uc.mem_write(self.BUF, bytes(0x800))
        self.trace.clear()
        self.bad.clear()
        regs = [mk.UC_M68K_REG_D2 + i for i in range(6)] + [mk.UC_M68K_REG_A2 + i for i in range(5)]
        for i, r in enumerate(regs):
            self.uc.reg_write(r, 0x5a5a0000 + i)
        self.call(DRAW, self.THIS, self.CANVAS)
        self.regs_ok = all(self.uc.reg_read(r) == 0x5a5a0000 + i for i, r in enumerate(regs)) and \
            self.uc.reg_read(mk.UC_M68K_REG_A7) == STACK - 0x400 + 4
        return self

    def texts(self):
        """(x, y, texte dessiné) de chaque appel 0x4007199c, hors titre et compteur."""
        out = []
        for name, _, a in self.trace:
            if name == "texte" and 10 < a[3] < 51:
                s = bytes(self.uc.mem_read(a[5], 64)).split(b"\0")[0].decode(errors="replace")
                out.append((a[2], a[3], s[:a[4]] if a[4] < 0x10000 else s))
        return out

    def pixels(self):
        buf = bytes(self.uc.mem_read(self.BUF, 1024))
        return [[(struct.unpack(">I", buf[8 * x + 4 * (y // 32):8 * x + 4 * (y // 32) + 4])[0] >> (31 - y % 32)) & 1
                 for x in range(128)] for y in range(64)]          # [y][x], y compté depuis le bas


def png(path, screens, scale=4):
    """Les écrans côte à côte (y vers le haut), en PNG, sans dépendance."""
    gap = 8
    w = len(screens) * 128 * scale + (len(screens) - 1) * gap
    h = 64 * scale
    rows = []
    for yy in range(h):
        y = 63 - yy // scale
        line = bytearray()
        for k, px in enumerate(screens):
            if k:
                line += bytes([0x40]) * gap
            for x in range(128):
                line += bytes([0xf0 if px[y][x] else 0x10]) * scale
        rows.append(b"\0" + bytes(line))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")
    pathlib.Path(path).write_bytes(data)


# --- 1. écritures -------------------------------------------------------------------------------------------------
def writes(stock, tweak):
    try:
        build.apply_writes(stock, [tweak])
        check(True, f"{len(tweak['writes'])} écritures : octets d'origine conformes")
    except SystemExit as e:
        check(False, str(e))
    mine = [(w["off"] + BASE, bytes.fromhex(w["new"])) for w in tweak["writes"]]
    clash = []
    for f in sorted(TWEAK.parent.glob("*.json")):
        if f.name in ("device.json", TWEAK.name):
            continue
        t = json.loads(f.read_text(encoding="utf-8"))
        for w in t["writes"]:
            a, n = w["off"] + BASE, bytes.fromhex(w["new"])
            for b, m in mine:
                lo, hi = max(a, b), min(a + len(n), b + len(m))
                if lo < hi and n[lo - a:hi - a] != m[lo - b:hi - b]:
                    clash.append((t["id"], hex(lo)))
    check(not clash, f"aucun recouvrement avec les autres tweaks {sorted(set(clash))[:4]}")
    check(all(b + len(m) <= SCROLL_HOOK or b >= SCROLL_HOOK + 3 for b, m in mine),
          "rien sur l'appel détourné par browser-scroll et Model-TG (0x400a55a1..0x400a55a3)")
    va, size = sprites.zone(0x401904b4)
    code = [(b, m) for b, m in mine if len(m) > 64]
    refs = [i for i in range(0, len(stock) - 3, 2) if va <= struct.unpack(">I", stock[i:i + 4])[0] < va + size]
    same = stock[va - BASE:va - BASE + size] == stock[sprites.SHARED_47 - BASE:sprites.SHARED_47 - BASE + size]
    img = build.apply_writes(stock, [tweak])[0]
    moved = img[0x400ac784 - BASE:0x400ac784 - BASE + 4] == sprites.SHARED_47.to_bytes(4, "big")
    check(len(code) == 1 and code[0][0] == va and len(code[0][1]) <= size and refs == [0x400ac784 - BASE] and same
          and moved,
          f"code ({len(code[0][1])} o) dans le masque libéré {va:#x} ({size} o), que seul son constructeur désigne "
          f"et qui pointe maintenant sur un masque identique ({sprites.SHARED_47:#x})")


# --- 2. écran -----------------------------------------------------------------------------------------------------
def screen(base, img):
    a = Browser(base).draw()
    b = Browser(img).draw()
    ta, tb = a.texts(), b.texts()
    print(f"        origine : {ta}")
    print(f"        modifié : {tb}")
    rows = [s for x, y, s in tb if x >= 9]
    ys = [y for x, y, s in tb if x >= 9]
    check(not a.bad and not b.bad and a.regs_ok and b.regs_ok,
          "dessin exécuté sans accès hors mémoire ; pile et registres d0-d7/a2-a6 rendus intacts")
    check(len(ta) == 1 and ta[0][2] == NAMES[0][:len(ta[0][2])], "origine : un seul nom")
    check(rows[:3] == ["KICKS", "BD CLASSIC", "SD VINTAGE BRUSHED"[:len(rows[2])]] and ys == sorted(ys, reverse=True)
          and len(set(ys)) == 3, f"modifié : 3 noms dans l'ordre, du haut vers le bas (y {ys})")
    check([s for x, y, s in tb if x == 2] == [">"] and [y for x, y, s in tb if x == 2] == ys[:1],
          "« > » sur la ligne du curseur (la 1re)")
    pa, pb = a.pixels(), b.pixels()
    check(pa[51:] == pb[51:] and pa[:11] == pb[:11], "titre, compteur et « Fn=Menu » identiques à l'origine")
    check(not any(pb[y][x] for y in range(11, 51) for x in range(121, 128)),
          "rien au-delà de x = 120 entre le titre et le compteur (place des flèches)")
    loops = [sp for n, sp, _ in b.trace if n == "boucle"]
    check(len(loops) == 4 and len(set(loops)) == 1, f"pile identique à chaque tour de la boucle des lignes ({len(loops)})")


# --- 3. déplacement du curseur ----------------------------------------------------------------------------------------
def moves(base, img):
    a, b = Browser(base), Browser(img)
    n = len(NAMES)
    seen, ok = [], True
    for step in [1] * n + [-1] * n:
        a.move(step)
        b.move(step)
        sa, sb = a.draw().texts(), b.draw().texts()
        sel, top = b.u32(b.THIS + 16), b.u32(b.THIS + 20)
        cur = [y for x, y, s in sb if x == 2]
        names = {y: s for x, y, s in sb if x >= 9}
        under = names.get(cur[0]) if cur else None
        ok &= a.u32(a.THIS + 16) == sel and under is not None and sa[0][2].startswith(under[:8]) and \
            0 <= sel - top < 3 and [s[:5] for s in names.values()] == [x[:5] for x in NAMES[top:top + 3]]
        seen.append((sel, top))
    print(f"        (sélection, 1re ligne) : {seen}")
    check(ok and max(s for s, t in seen) == n - 1 and seen[-1] == (0, 0) and max(t for s, t in seen) == n - 3
          and len(seen) == 2 * n,
          "jusqu'au bout et retour : le nom sous « > » est celui de l'origine, la liste défile d'une ligne à la fois")


def small(base, img):
    """Dossiers de 1 à 3 entrées. Hors de la racine, l'OS compte une entrée de moins (d3, 0x400a5404 : l'entrée 0 est
    le retour au dossier parent) et place le curseur sur l'entrée 1 (0x4003f616) ; la borne d'origine min(lignes, d3)
    y perdait la dernière entrée une fois revenu en haut."""
    names = ["KICKS", "BD CLASSIC", "SD VINTAGE"]
    seen, ok = [], True
    for root, n in ((False, 2), (False, 3), (True, 1), (True, 2), (True, 3)):
        a, b = Browser(base, names=names[:n], special=root), Browser(img, names=names[:n], special=root)
        start = 0 if root else 1
        a.select(start, start)
        b.select(start, start)
        for step in (0, -1, 1, 1, 1, -1, -1, -1):
            if step:
                a.move(step)
                b.move(step)
            sa, sb = a.draw().texts(), b.draw().texts()
            sel, top = b.u32(b.THIS + 16), b.u32(b.THIS + 20)
            rows = [s for x, y, s in sb if x >= 9]
            cur = [y for x, y, s in sb if x == 2]
            under = {y: s for x, y, s in sb if x >= 9}.get(cur[0]) if len(cur) == 1 else None
            ok &= a.u32(a.THIS + 16) == sel and not b.bad and b.regs_ok and rows == names[top:n] and \
                under is not None and sa and sa[0][2].startswith(under[:7])
            seen.append((root, n, sel, top, len(rows)))
    check(ok, "petits dossiers (1 à 3 entrées, à la racine et ailleurs) : toutes leurs entrées à l'écran, « > » sur "
              "celle de l'origine, dans les deux sens")


def subfolder(base, img):
    """Sous-dossier de +Drive : l'entrée 0 (retour au dossier parent) est interdite au curseur, et après chaque
    déplacement l'origine remettait la 1re ligne visible sur la sélection (0x4004067c) : le curseur serait resté sur
    la 1re ligne. Le tweak garde la fenêtre de la liste."""
    names = ["..", "KICKS", "BD CLASSIC", "SD VINTAGE", "HH CLOSED", "CY RIDE"]
    ok, tops, nodraw = True, [], True
    for n in (2, 3, 4, 6):
        a = Browser(base, names=names[:n], folders={0}, drive=True)
        b = Browser(img, names=names[:n], folders={0}, drive=True)
        a.enter()
        b.enter()
        ok &= b.state() == (1, 1, 0)
        sels = []
        for step in [0, -1] + [1] * n + [-1] * n:
            if step:
                a.move(step)
                b.move(step)
            sa, sb = a.draw().texts(), b.draw().texts()
            sel, top, _ = b.state()
            rows = [s for x, y, s in sb if x >= 9]
            cur = [y for x, y, s in sb if x == 2]
            under = {y: s for x, y, s in sb if x >= 9}.get(cur[0]) if len(cur) == 1 else None
            ok &= a.state()[0] == sel and top >= 1 and 0 <= sel - top < 3 and rows == names[top:min(n, top + 3)] and \
                under is not None and sa and sa[0][2].startswith(under[:7]) and not b.bad and b.regs_ok
            sels.append(sel)
            if n == 6:
                tops.append(top)
        c = Browser(img, names=names[:n], folders={0}, drive=True)        # sans dessin entre deux déplacements
        c.enter()
        for step, want in zip([1] * n + [-1] * n, sels[2:]):
            c.move(step)
            nodraw &= c.state()[0] == want and 0 <= c.state()[2] == c.state()[0] - c.state()[1] < 3
    print(f"        1re ligne, 6 entrées : {tops}")
    check(ok and tops == [1, 1, 1, 1, 2, 3, 3, 3, 3, 3, 2, 1, 1, 1],
          "sous-dossier de +Drive : sélections de l'origine, « > » qui suit le curseur, la liste défile aux bords, "
          "l'entrée 0 (dossier parent) jamais à l'écran")
    check(nodraw, "sous-dossier, sans dessin entre deux déplacements : la même suite, la fenêtre reste cohérente")


# --- 4. son chargé, dossiers, entrée spéciale -------------------------------------------------------------------------
def marks(img):
    b = Browser(img, loaded=4)
    b.select(4, 2)
    b.draw()
    inv = [a for n, _, a in b.trace if n == "inversé"]
    tb = b.texts()
    y4 = [y for x, y, s in tb if s.startswith("CY RIDE")]
    check(len(inv) == 1 and y4 and inv[0][2] == y4[0] - 2 and inv[0][1] == 7,
          f"son chargé (entrée 4, à l'écran) : son nom inversé sur sa ligne {inv[:1]}")
    b.select(0, 0)
    b.draw()
    check(not [a for n, _, a in b.trace if n == "inversé"], "son chargé hors de l'écran : rien d'inversé")
    px = b.pixels()
    y0 = [y for x, y, s in b.texts() if s == "KICKS"][0]
    folder = [[px[y0 + dy][9 + dx] for dx in range(7)] for dy in range(8, -1, -1)]
    want = [[0] * 7, [0] * 7, [1, 1, 1, 0, 0, 0, 0]] + [[1] * 7] * 5 + [[0] * 7]
    check(folder == want and [s for x, y, s in b.texts() if s == "KICKS"] and
          [x for x, y, s in b.texts() if s == "KICKS"] == [18], "dossier : repère de 7 px en x 9, nom en x 18")
    c = Browser(img, names=NAMES[:4] + ["LAST"], special=True)
    c.select(2, 2)
    c.draw()
    px, tc = c.pixels(), c.texts()
    yl = [y for x, y, s in tc if s == "LAST"]
    ring = [[px[yl[0] + dy][9 + dx] for dx in range(7)] for dy in range(7, 0, -1)] if yl else []
    want = [[1] * 7] + [[1, 0, 0, 0, 0, 0, 1]] * 5 + [[1] * 7]
    check(ring == want and [x for x, y, s in tc if s == "LAST"] == [18],
          "entrée spéciale (fin de liste, à la racine) : carré creux de 7 px, nom en x 18")


# --- 5. dossier vide ------------------------------------------------------------------------------------------------
def empty(img):
    b = Browser(img, names=["X"]).draw()
    t = [(x, y, s) for x, y, s in b.texts()]
    check(t == [(9, 40, "<EMPTY>")] and not b.bad, f"dossier vide : « <EMPTY> » sur la 1re ligne {t}")


# --- 6. noms longs ----------------------------------------------------------------------------------------------------
def scroll(img, has_scroll):
    b = Browser(img)
    b.select(2, 1)                                    # « SD VINTAGE BRUSHED LONG NAME » sur la 2e ligne
    shots = []
    for k in range(40):
        b.draw(tick=k * 0x400)
        stubs = [a for n, _, a in b.trace if n == "défile"]
        shots.append((stubs, b.texts()))
    stubs = [s for s, _ in shots]
    lines = [{y: s for x, y, s in t if x >= 9} for _, t in shots]
    cur_y = [y for x, y, s in shots[0][1] if x == 2][0]
    others = {y for y in lines[0] if y != cur_y}
    if not has_scroll:
        check(all(not s for s in stubs) and len({l[cur_y] for l in lines}) == 1,
              "sans browser-scroll ni Model-TG : aucun défilement, comme à l'origine")
        return
    firsts = sorted({l[cur_y][:3] for l in lines})
    check(all(len(s) == 1 and s[0][3] == cur_y for s in stubs),
          f"une seule ligne par dessin passe par le défilement : celle du curseur (y {cur_y})")
    check(len(firsts) > 3 and all(len({l[y] for l in lines}) == 1 for y in others),
          f"le nom sous le curseur défile ({len(firsts)} positions), les autres restent en place")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True)
    ap.add_argument("--with", dest="others", default="", help="autres tweaks appliqués avant (ex. model-tg-st,…)")
    ap.add_argument("--syntakt", help="Syntakt_OS1.42.syx, pour les moteurs du Syntakt")
    ap.add_argument("--png", help="dossier où écrire des images de l'écran (origine | modifié)")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    by_id = {json.loads(f.read_text(encoding="utf-8"))["id"]: f for f in TWEAK.parent.glob("*.json")
             if f.name != "device.json"}
    tweaks = [json.loads(by_id[i].read_text(encoding="utf-8")) for i in args.others.split(",") if i]
    tweak = json.loads(TWEAK.read_text(encoding="utf-8"))
    pl, _ = build.build_payload(tweaks, stock, args.syntakt)
    base = build.apply_writes(stock, tweaks)[0] + pl
    img = build.apply_writes(stock, sorted(tweaks + [tweak], key=lambda t: t["order"]))[0] + pl
    has_scroll = base[SCROLL_HOOK - BASE:SCROLL_HOOK - BASE + 3] != stock[SCROLL_HOOK - BASE:SCROLL_HOOK - BASE + 3]
    print(f"firmware : {', '.join(t['id'] for t in tweaks + [tweak])}")
    print("écritures")
    writes(stock, tweak)
    print("écran")
    screen(base, img)
    print("déplacement du curseur (vraie liste de l'OS)")
    moves(base, img)
    small(base, img)
    subfolder(base, img)
    print("son chargé, dossiers, entrée spéciale")
    marks(img)
    print("dossier vide")
    empty(img)
    print("noms longs" + (" (défilement de browser-scroll / Model-TG)" if has_scroll else ""))
    scroll(img, has_scroll)
    if args.png:
        out = pathlib.Path(args.png)
        out.mkdir(parents=True, exist_ok=True)
        for name, moves_, loaded in (("navigateur-multiligne.png", 2, 1), ("navigateur-multiligne-dossier.png", 0, None)):
            shots = []
            for im in (base, img):
                b = Browser(im, loaded=loaded, icons=True)
                for _ in range(moves_):
                    b.move(1)
                shots.append(b.draw(tick=0x1800).pixels())
            png(out / name, shots)
            print(f"  image : {out / name}")
    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ÉCHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
