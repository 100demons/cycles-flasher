#!/usr/bin/env python3
"""Génère tweaks/model-cycles_OS1.13/47-trigless-dim.json : les trigless trigs (lock trigs) atténués sur les touches de
pas (mod de djd_oz, notes/45).

En mode grille, l'OS allume une touche de pas qui porte un trigless trig (FUNC + touche de pas) comme un trig de note
(état de LED 4 : allumée, éteinte 0,35 s toutes les 2 s). Le mod donne à ces touches l'état 260, traité comme 4 par
l'OS, et les allume seulement 1 ms sur 3 (333 Hz, 33 % de lumière) : la lumière est découpée dans l'interruption du
panneau, qui recharge les verrous des LED (notes/45 §6).

tools/machines/trigless_dim/ : trigless_dim.S (trois accroches et leur état), lié par trigless_dim.ld dans deux
masques de sprites 47x47 libérés (tools/sprites.py). Les accroches sur l'OS sont les HOOKS et RAW ci-dessous ; chaque
écriture porte ses octets d'origine, vérifiés sur le MAIN OS officiel.

    python3 tools/gen_trigless_dim.py --cycles model-cycles_OS1.13.syx [--check]

Variantes d'essai (jamais versionnées) : --defsym WAIT=68 --out essai.json (attente de 0,5 us entre deux écritures du
port au lieu de 2 us, jamais essayée sur la machine), --defsym PWM_N=2 (1 ms sur 2, 50 %).
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

SRC = HERE / "machines" / "trigless_dim"
OUT = HERE.parent / "tweaks" / "model-cycles_OS1.13" / "47-trigless-dim.json"
BASE = gx.BASE
# sections de trigless_dim.ld : (masque libéré, début de la zone utilisée, taille disponible)
CAVES = {
    ".cave_a": (0x4018dba8, 0x4018dba8, 376),
    ".cave_b": (0x40192734, 0x40192734, 376),
}
# (adresse, octets d'origine, symbole, instruction, rôle)
HOOKS = (
    (0x40059dea, "76ff781533c38c000000", "td_led", 0x4ef9,
     "interruption du panneau (PIT3, 12 kHz), étape 0 des LED (1 fois par ms, 0x40059db8) : moveq #-1,d3 ; moveq #21,d4 ; "
     "move.w d3,0x8c000000 (DIR) -> jmp td_led ; nop ; nop (rangées à allumer ou éteindre, puis la rangée du tour)"),
    (0x40006086, "4ef94008e77e", "td_frame", 0x4ef9,
     "fin de l'image des LED (0x40006044, tâche de l'interface, 30 Hz) : jmp 0x4008e77e -> jmp td_frame (relevé des "
     "LED dans l'état 260, quand les états de l'image sont complets)"),
    (0x40005f36, "b2ac00286730", "td_blink", 0x4ef9,
     "clignotement des LED (0x40005efc, 2 Hz) : cmp.l 40(a4),d1 ; beq.s 0x40005f6c (état 4) -> jmp td_blink (4 ou 260)"),
)
# (adresse, octets d'origine, nouveaux octets, rôle)
RAW = (
    (0x40021f54, "0004", "0104",
     "mode grille (0x40021d22), pas qui porte un trigless trig : movea.w #4,a5 -> movea.w #260,a5 (état de sa LED)"),
)
SYMBOLS = ("td_lock", "td_last", "td_cur", "td_ph", "td_led")    # pour tools/emu/test_trigless_dim.py


def compile_td(defsyms=()):
    """Code lié (ELF) : {section: (adresse, octets)}, symboles. defsyms : (« NOM=valeur », ...) pour les variantes."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        obj, elf = d / "td.o", d / "td.elf"
        gx.run([gx.CROSS + "gcc", "-mcpu=54418", *[f"-Wa,--defsym,{x}" for x in defsyms], "-c",
                str(SRC / "trigless_dim.S"), "-o", str(obj)])
        gx.run([gx.CROSS + "ld", "-T", str(SRC / "trigless_dim.ld"), "--no-warn-rwx-segments", "-o", str(elf),
                str(obj)])
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


def build_tweak(stock, defsyms=()):
    secs, syms = compile_td(defsyms)
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
        "id": "trigless-dim",
        "order": 47,
        "name": "Trigless trigs atténués sur les touches de pas",
        "description": [
            "Mode grille : une touche de pas qui porte un trigless trig (lock trig, FUNC + pas) s'allume à 33 % au "
            "lieu de pleine lumière ; elle garde le clignotement d'origine (éteinte 0,35 s toutes les 2 s).",
            "L'état de sa LED devient 260 au lieu de 4 (traité comme 4 par l'OS). La LED est allumée 1 ms sur 3 "
            "(333 Hz, régulier) : l'interruption du panneau recharge les verrous des rangées qui portent une touche "
            "atténuée, à chaque cycle de 1 ms, juste avant la rangée du tour. Trigs de note, trigs avec p-locks, "
            "lumière de lecture, pads : inchangés.",
            "D'après le mod de djd_oz (envoyé à Maxime le 06/10/2026) : même état 260, même clignotement ; le "
            "découpage de la lumière est refait dans l'interruption du panneau (la version 1, 16 ticks sur 25 de "
            "l'horloge des LED à 120 Hz, scintillait irrégulièrement).",
            f"Code et état dans deux masques de sprites 47x47 libérés (tools/sprites.py) : {used['.cave_a']} o en "
            f"0x4018dba8, {used['.cave_b']} o en 0x40192734. Généré par tools/gen_trigless_dim.py, notes/45.",
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
    ap.add_argument("--defsym", action="append", default=[], metavar="NOM=VALEUR",
                    help="variante d'essai (WAIT, PWM_N, PWM_ON de trigless_dim.S) ; demande --out")
    ap.add_argument("--out", type=pathlib.Path, help="écrit la variante ici (jamais dans tweaks/)")
    args = ap.parse_args()
    if args.defsym and (not args.out or args.check or args.out.resolve() == OUT):
        raise SystemExit("!! une variante --defsym s'écrit avec --out, hors de tweaks/, sans --check")
    stock = T.main_os_from_syx(args.cycles)
    if build.sha(stock) != json.loads((OUT.parent / "device.json").read_text(encoding="utf-8"))["section_sha256"]:
        raise SystemExit("!! ce n'est pas le MAIN OS 1.13 officiel")
    tweak, _ = build_tweak(stock, args.defsym)
    build.apply_writes(stock, [tweak])                # les octets d'origine collent
    text = json.dumps(tweak, indent=1, ensure_ascii=False) + "\n"
    print("  " + tweak["description"][-1])
    if args.check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"  {OUT.name} {'est à jour' if ok else 'NE CORRESPOND PAS (autre binutils ?)'}")
        raise SystemExit(0 if ok else 1)
    out = args.out or OUT
    out.write_text(text, encoding="utf-8")
    print(f"  écrit : {out} ({len(tweak['writes'])} écritures)")


if __name__ == "__main__":
    main()
