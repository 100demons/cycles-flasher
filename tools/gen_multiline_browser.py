#!/usr/bin/env python3
"""Génère tweaks/model-cycles_OS1.13/44-multiline-browser.json : le navigateur affiche plusieurs lignes (notes/40).

L'OS d'origine montre un seul nom à la fois, en gros caractères, dans le navigateur de sons, de dossiers et
d'échantillons (ModelsFileManager) : son constructeur règle à 1 le nombre de lignes visibles de sa liste. Le tweak en
met ROWS, en petite police, la première en haut, avec « > » devant la ligne du curseur ; le son chargé reste inversé
autour de son nom, et seul le nom sous le curseur défile s'il est trop long (browser-scroll, Model-TG). Les icônes de
dossier, trop hautes pour une ligne, deviennent un repère de 7 px.

Idée et adresses de départ : un script d'un membre de la communauté qui modifiait 30-model-tg-st.json (notes/40 §1).

tools/machines/multiline_browser/ : multiline_browser.S (dessin des lignes, quatre accroches), lié par
multiline_browser.ld dans le masque de sprite 47x47 libéré 0x401904b4 (tools/sprites.py).

    python3 tools/gen_multiline_browser.py --cycles model-cycles_OS1.13.syx [--check]
"""
import argparse
import json
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "emu"))

import build                       # noqa: E402
import gen_sdvintage_exact as gx   # noqa: E402
import sprites                     # noqa: E402
import test_sdvintage as T         # noqa: E402

SRC = HERE / "machines" / "multiline_browser"
OUT = HERE.parent / "tweaks" / "model-cycles_OS1.13" / "44-multiline-browser.json"
BASE = gx.BASE
MASK = 0x401904b4                                      # masque 47x47 libéré (376 o)
ROWS = 3                                               # lignes visibles (1 à l'origine)
ROW_H = 13                                             # pas entre deux lignes (px)
Y0 = 40                                                # y de la 1re ligne (l'écran compte y depuis le bas)
X_TEXT = 9                                             # x du nom (2 à l'origine) ; « > » en CUR_X
CUR_X = 2
X_MARK = 9                                             # un dossier : repère en X_TEXT, nom décalé de X_MARK
UP_Y, DOWN_Y = Y0 + 4, Y0 - (ROWS - 1) * ROW_H        # flèches de défilement (38 et 20 à l'origine)
FONT_SMALL = 0x40ea14cc                                # petite police (celle du titre)
# (adresse, octets d'origine, symbole, jmp/jsr, octets qui suivent, rôle), dans le dessin du navigateur 0x400a539c
HOOKS = (
    (0x400a5588, "2eaa028c4e95", "ml_row", 0x4ef9, "",
     "chaque ligne : move.l 652(a2),(sp) ; jsr (a5) -> jmp ml_row (sa hauteur ; la ligne du curseur repasse par "
     "l'appel d'origine 0x400a559e, que browser-scroll et Model-TG détournent)"),
    (0x400a55a4, "4fef001c226e", "ml_after", 0x4ef9, "",
     "après le nom : lea 28(sp),sp ; movea.l -40(fp),a1 -> jmp ml_after (« > », son chargé inversé)"),
    (0x400a5612, "20522f0a20680040", "ml_bound", 0x4eb9, "600a",
     "tête de la boucle des lignes : movea.l (a2),a0 ; move.l a2,-(sp) ; movea.l 64(a0),a0 -> jsr ml_bound ; "
     "bra.s 0x400a5624 (lignes à dessiner : min(ROWS, nombre d'entrées - 1re ligne), au lieu de min(lignes, d3) ; "
     "0x400a561a..0x400a5623 n'est plus exécuté)"),
    (0x400a576e, "4eb940071da4", "ml_icon", 0x4eb9, "",
     "icône de dossier ou d'entrée spéciale : jsr 0x40071da4 -> jsr ml_icon (repère de 7 px)"),
)
# (adresse, octets d'origine, nouveaux octets, rôle) : des constantes, et la liste dans un sous-dossier de +Drive
PATCHES = (
    (0x4003f622, "25400018", "42aa0018",
     "entrée dans un sous-dossier (0x4003f5c6) : move.l d0,24(a2) -> clr.l 24(a2) (curseur sur la 1re ligne "
     "visible : sélection = 1re ligne = a2[680])"),
    (0x400406a8, "4a826e027401254200102542001425420018", "4a826e0a74012542001442aa001825420010",
     "après chaque déplacement dans un sous-dossier (0x4004067c, appelé par vt[76] 0x400a64be) : l'origine met "
     "sélection = 1re ligne = max(sélection, 1), ce qui laisserait le curseur sur la 1re ligne ; désormais "
     "tst.l d2 ; bgt.s 1f ; moveq #1,d2 ; move.l d2,20(a2) ; clr.l 24(a2) ; 1: move.l d2,16(a2) : l'entrée 0 (retour "
     "au dossier parent) reste interdite, la fenêtre de la liste n'est plus écrasée"),
    (0x4003f752, "40ea14dc", f"{FONT_SMALL:08x}", "police des noms : la grande -> la petite (celle du titre)"),
    (0x400a547c, "0026", f"{UP_Y:04x}", "flèche du haut : y 38 -> en face de la 1re ligne"),
    (0x400a54ac, "0014", f"{DOWN_Y:04x}", "flèche du bas : y 20 -> en face de la dernière ligne"),
    (0x400a54ca, "0002", f"{X_TEXT:04x}", "x du nom : movea.w #2,a3 -> #X_TEXT"),
    (0x400a5528, "0014", f"{Y0:04x}", "dossier vide : « <EMPTY> » en y 20 -> sur la 1re ligne"),
    (0x400a552c, "0002", f"{X_TEXT:04x}", "dossier vide : « <EMPTY> » en x 2 -> X_TEXT"),
    (0x400a5776, "001b", f"{X_MARK:04x}", "décalage après une icône : lea 27(a3),a3 -> lea X_MARK(a3),a3"),
    (0x400a69b4, "0001", f"{ROWS:04x}", "lignes visibles de la liste : pea 1 -> pea ROWS (constructeur 0x400a68fc)"),
)
SYMBOLS = ("ml_row", "ml_after", "ml_icon", "ml_bound")            # pour tools/emu/test_multiline_browser.py


def compile_browser():
    """(adresse, octets) de la section .cave, et les symboles."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        obj, elf, out = d / "ml.o", d / "ml.elf", d / "cave.bin"
        gx.run([gx.CROSS + "gcc", "-mcpu=54418", f"-DML_X={X_TEXT}", f"-DML_CUR_X={CUR_X}", f"-DML_Y0={Y0}",
                f"-DML_ROWH={ROW_H}", f"-DML_ROWS={ROWS}", "-c", str(SRC / "multiline_browser.S"), "-o", str(obj)])
        gx.run([gx.CROSS + "ld", "-T", str(SRC / "multiline_browser.ld"), "--no-warn-rwx-segments", "-o", str(elf),
                str(obj)])
        syms = {}
        for line in gx.run([gx.CROSS + "nm", str(elf)]).splitlines():
            p = line.split()
            if len(p) == 3:
                syms[p[2]] = int(p[0], 16)
        gx.run([gx.CROSS + "objcopy", "-O", "binary", "-j", ".cave", str(elf), str(out)])
        addr = int(subprocess.run([gx.CROSS + "objdump", "-h", str(elf)], capture_output=True, text=True,
                                  check=True).stdout.split(".cave")[1].split()[1], 16)
        return addr, out.read_bytes(), syms


def build_tweak(stock):
    addr, code, syms = compile_browser()
    room = sprites.zone(MASK)[1]
    if addr != MASK or len(code) > room:
        raise SystemExit(f"!! {len(code)} o à {addr:#x}, place {room} o à {MASK:#x}")
    old = stock[addr - BASE:addr - BASE + len(code)]
    writes = [{"off": addr - BASE, "old": old.hex(), "new": code.hex()}, sprites.redirect_write(MASK)]
    for va, old_hex, sym, op, tail, _ in HOOKS:
        if stock[va - BASE:va - BASE + len(old_hex) // 2] != bytes.fromhex(old_hex):
            raise SystemExit(f"!! octets d'origine inattendus en {va:#x}")
        writes.append({"off": va - BASE, "old": old_hex, "new": struct.pack(">HI", op, syms[sym]).hex() + tail})
    for va, old_hex, new_hex, _ in PATCHES:
        if stock[va - BASE:va - BASE + len(old_hex) // 2] != bytes.fromhex(old_hex):
            raise SystemExit(f"!! octets d'origine inattendus en {va:#x}")
        writes.append({"off": va - BASE, "old": old_hex, "new": new_hex})
    writes.sort(key=lambda w: w["off"])
    tweak = {
        "id": "multiline-browser",
        "order": 44,
        "name": "Navigateur sur plusieurs lignes",
        "description": [
            f"Le navigateur de sons, de dossiers et d'échantillons affiche {ROWS} noms à la fois, en petite police, "
            "au lieu d'un seul en gros caractères.",
            "« > » devant le nom sous le curseur ; le son chargé reste inversé ; un dossier a un petit repère devant "
            "son nom. Avec browser-scroll ou Model-TG, seul le nom sous le curseur défile.",
            "Idée et adresses de départ : un script d'un membre de la communauté (notes/40).",
            f"Code dans le masque de sprite 47x47 libéré 0x401904b4 (tools/sprites.py) : {len(code)} o. "
            "Généré par tools/gen_multiline_browser.py, notes/40.",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
        "symbols": {n: f"{syms[n]:#x}" for n in SYMBOLS},
        "writes": writes,
    }
    return tweak


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--check", action="store_true", help="vérifie que le JSON versionné correspond")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    if build.sha(stock) != json.loads((OUT.parent / "device.json").read_text(encoding="utf-8"))["section_sha256"]:
        raise SystemExit("!! ce n'est pas le MAIN OS 1.13 officiel")
    tweak = build_tweak(stock)
    build.apply_writes(stock, [tweak])                # les octets d'origine collent
    text = json.dumps(tweak, indent=1, ensure_ascii=False) + "\n"
    print("  " + tweak["description"][-1])
    if args.check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"  {OUT.name} {'est à jour' if ok else 'NE CORRESPOND PAS (autre binutils ?)'}")
        raise SystemExit(0 if ok else 1)
    OUT.write_text(text, encoding="utf-8")
    print(f"  écrit : {OUT.relative_to(HERE.parent)} ({len(tweak['writes'])} écritures, {ROWS} lignes)")


if __name__ == "__main__":
    main()
