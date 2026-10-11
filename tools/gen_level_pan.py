#!/usr/bin/env python3
"""Génère tweaks/model-cycles_OS1.13/46-level-pan-values.json : le volume et le pan de la piste en chiffres sur
l'écran principal (mod de djd_oz, notes/44).

Quand on tourne LEVEL/DATA, le volume de la piste sélectionnée (0 à 127) s'affiche en petits chiffres à la place du
haut-parleur de la barre de volume ; avec FUNC tenu, son pan (-64 à 63) à la place du « R » de la barre de pan. Le
chiffre reste 3 s après le dernier mouvement. Comme dans le mod de djd_oz, LEVEL/DATA avance de 1 par cran sur
l'écran principal au lieu de 2 (le 2e argument de 0x4006f73a, 2 -> 1), pour que le chiffre passe par toutes les
valeurs.

tools/machines/level_pan/ : level_pan.S (le tick, les deux accroches, les chiffres, la police de djd_oz), lié par
level_pan.ld dans deux masques de sprites 47x47 libérés (tools/sprites.py). Les accroches sur l'OS sont les HOOKS et
RAW ci-dessous ; chaque écriture porte ses octets d'origine, vérifiés sur le MAIN OS officiel.

    python3 tools/gen_level_pan.py --cycles model-cycles_OS1.13.syx [--check]
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

SRC = HERE / "machines" / "level_pan"
OUT = HERE.parent / "tweaks" / "model-cycles_OS1.13" / "46-level-pan-values.json"
BASE = gx.BASE
# sections de level_pan.ld : (masque libéré, début de la zone utilisée, taille disponible)
CAVES = {
    ".cave_a": (0x4018f4b4, 0x4018f4b4, 376),
    ".cave_b": (0x4018fc74, 0x4018fc74, 376),
}
# (adresse, octets d'origine, symbole, instruction, rôle)
HOOKS = (
    (0x400081f2, "4eb940090f48", "lp_tick", 0x4eb9,
     "tâche de l'interface, message 5 (minuteur DTIM3, 30 Hz) : jsr 0x40090f48 (service des minuteurs) -> jsr lp_tick"),
    (0x4001aa4e, "4fefffe048d70cfc", "lp_enc", 0x4ef9,
     "début du gestionnaire des encodeurs de l'écran principal (MainScreenView, vtable 0x400ffe20 [17]) : "
     "lea -32(sp),sp ; movem.l d2-d7/a2-a3,(sp) -> jmp lp_enc ; nop"),
    (0x4001b22a, "4e56ffc048d73cfc", "lp_draw", 0x4ef9,
     "début de MainScreenView::draw (vtable [4]) : link a6,#-64 ; movem.l d2-d7/a2-a5,(sp) -> jmp lp_draw ; nop"),
)
# (adresse, octets d'origine, nouveaux octets, rôle)
RAW = (
    (0x4001aaba, "48780002", "48780001",
     "LEVEL/DATA sur l'écran principal : pea 2 -> pea 1, 2e argument de 0x4006f73a(événement, 2, 16) (pas par cran ; "
     "16 en mode rapide, inchangé)"),
)
SYMBOLS = ("lp_cnt", "lp_pan", "lp_lvl")             # pour tools/emu/test_level_pan.py


def compile_lp():
    """Code lié (ELF) : {section: (adresse, octets)}, symboles."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        obj, elf = d / "lp.o", d / "lp.elf"
        gx.run([gx.CROSS + "gcc", "-mcpu=54418", "-c", str(SRC / "level_pan.S"), "-o", str(obj)])
        gx.run([gx.CROSS + "ld", "-T", str(SRC / "level_pan.ld"), "--no-warn-rwx-segments", "-o", str(elf), str(obj)])
        syms = {}
        for line in gx.run([gx.CROSS + "nm", str(elf)]).splitlines():
            p = line.split()
            if len(p) == 3:
                syms[p[2]] = int(p[0], 16)
        heads = subprocess.run([gx.CROSS + "objdump", "-h", str(elf)], capture_output=True, text=True,
                               check=True).stdout
        secs = {}
        for name in CAVES:
            out = d / (name.strip(".") + ".bin")
            gx.run([gx.CROSS + "objcopy", "-O", "binary", "-j", name, str(elf), str(out)])
            secs[name] = (int(heads.split(name)[1].split()[1], 16), out.read_bytes())
    return secs, syms


def build_tweak(stock):
    secs, syms = compile_lp()
    writes = []
    for name, (mask, lo, room) in CAVES.items():
        addr, code = secs[name]
        if addr != lo or len(code) > room:
            raise SystemExit(f"!! {name} : {len(code)} o à {addr:#x}, place {room} o à {lo:#x}")
        size, shared = sprites.MASKS[mask][0], sprites.MASKS[mask][3]
        if stock[mask - BASE:mask - BASE + size] != stock[shared - BASE:shared - BASE + size]:
            raise SystemExit(f"!! {name} : le masque {mask:#x} n'est pas identique au masque gardé {shared:#x}")
        writes.append({"off": addr - BASE, "old": stock[addr - BASE:addr - BASE + len(code)].hex(), "new": code.hex()})
        writes.append(sprites.redirect_write(mask))
    for va, old_hex, sym, op, _ in HOOKS:
        old = bytes.fromhex(old_hex)
        if stock[va - BASE:va - BASE + len(old)] != old:
            raise SystemExit(f"!! octets d'origine inattendus en {va:#x}")
        new = struct.pack(">HI", op, syms[sym])
        new += b"\x4e\x71" * ((len(old) - len(new)) // 2)
        writes.append({"off": va - BASE, "old": old_hex, "new": new.hex()})
    for va, old_hex, new_hex, _ in RAW:
        if stock[va - BASE:va - BASE + len(old_hex) // 2].hex() != old_hex:
            raise SystemExit(f"!! octets d'origine inattendus en {va:#x}")
        writes.append({"off": va - BASE, "old": old_hex, "new": new_hex})
    writes.sort(key=lambda w: w["off"])
    used = {n: len(secs[n][1]) for n in CAVES}
    tweak = {
        "id": "level-pan-values",
        "order": 46,
        "name": "Volume et pan en chiffres sur l'écran principal",
        "description": [
            "Écran principal : en tournant LEVEL/DATA, le volume de la piste sélectionnée (0 à 127) s'affiche en "
            "chiffres à la place du haut-parleur de la barre de volume ; avec FUNC tenu, le pan (-64 à 63) à la "
            "place du « R » de la barre de pan.",
            "Le chiffre reste 3 s après le dernier mouvement (90 ticks de l'interface à 30 Hz), puis part au "
            "redessin suivant (au plus 1 s après). Pas d'affichage quand la valeur change autrement (MIDI, chargement).",
            "LEVEL/DATA avance de 1 par cran sur l'écran principal au lieu de 2 (volume et pan, une piste ou TRK pour "
            "toutes) ; le mode rapide (x16) ne change pas.",
            "D'après le mod de djd_oz (envoyé à Maxime le 06/10/2026), réécrit pour s'exécuter en place : même police, mêmes "
            "positions.",
            f"Code et état dans deux masques de sprites 47x47 libérés (tools/sprites.py) : {used['.cave_a']} o en "
            f"0x4018f4b4, {used['.cave_b']} o en 0x4018fc74. Généré par tools/gen_level_pan.py, notes/44.",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
        "symbols": {n: f"{syms[n]:#x}" for n in SYMBOLS},
        "writes": writes,
    }
    return tweak, syms


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--check", action="store_true", help="vérifie que le JSON versionné correspond")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    if build.sha(stock) != json.loads((OUT.parent / "device.json").read_text(encoding="utf-8"))["section_sha256"]:
        raise SystemExit("!! ce n'est pas le MAIN OS 1.13 officiel")
    tweak, _ = build_tweak(stock)
    build.apply_writes(stock, [tweak])                # les octets d'origine collent
    text = json.dumps(tweak, indent=1, ensure_ascii=False) + "\n"
    print("  " + tweak["description"][-1])
    if args.check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"  {OUT.name} {'est à jour' if ok else 'NE CORRESPOND PAS (autre binutils ?)'}")
        raise SystemExit(0 if ok else 1)
    OUT.write_text(text, encoding="utf-8")
    print(f"  écrit : {OUT.relative_to(HERE.parent)} ({len(tweak['writes'])} écritures)")


if __name__ == "__main__":
    main()
