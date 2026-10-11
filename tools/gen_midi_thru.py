#!/usr/bin/env python3
"""Génère les deux tweaks « THRU qui envoie aussi le MIDI du Cycles » (notes/53), d'après le fork d'AveyCole.

Dans CONFIG › MIDI › PORTS, la ligne OUT/THRU choisit OUT (le Cycles envoie son horloge, ses notes et ses
paramètres, et ne relaie rien) ou THR (il relaie ce qu'il reçoit sur son MIDI IN, et jette ce qu'il génère
lui-même). Les deux tweaks gardent ce menu tel quel et s'excluent :
  - 50-midi-both.json (midi-both) : THR relaie ET envoie le MIDI du Cycles, toujours. Les trois portes qui jettent
    le MIDI généré en THR (0x4000154a, 0x4000156a, 0x40001590 : jsr 0x40044df8, puis tst.l d0) reçoivent
    moveq #0,d0 ; nop ; nop. Aucune place libre.
  - 51-midi-live-both.json (midi-live-both) : sur la ligne OUT/THRU qui affiche THR, FUNC + appui sur le potard
    LEVEL/DATA alterne THR (relais seul, comme à l'origine) et THR + MIDI du Cycles (valeur 2 du réglage). La touche
    de la ligne (0x4003560a) saute à midi_key, les trois portes appellent midi_gate. Code dans
    tools/machines/midi_thru/ (midi_thru.S, midi_thru.ld), lié dans le masque de sprite 34x34 libéré 0x40192ba4
    (tools/sprites.py).

Les deux viennent d'AveyCole (https://github.com/AveyCole/Modded-Cycles, commit ba5f8bb : tools/gen_midi_both.py
et tools/gen_midi_live_both.py), qui les a testés sur son Model:Cycles le 10/10/2026. Mêmes octets, sauf l'adresse du
code de midi-live-both : 0x40167c50 dans le fork, un des 4 masques 35x35 que le filtre par piste (PR #55) laisse libres
dans le groupe qu'il occupe, gardés pour sa suite ; ici un masque 34x34, dans un groupe où rien d'autre n'est pris. Le code
lui-même est identique octet pour octet (aucune adresse interne), tools/emu/test_midi_thru.py le vérifie.

Il faut les binutils m68k (as, ld, nm, objcopy : paquet binutils-m68k-linux-gnu, ou m68k-elf-*).

    python3 tools/gen_midi_thru.py --cycles model-cycles_OS1.13.syx [--check]
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build                       # noqa: E402
import sprites                     # noqa: E402

DEV = HERE.parent / "tweaks" / "model-cycles_OS1.13"
SRC = HERE / "machines" / "midi_thru"
OUT_BOTH = DEV / "50-midi-both.json"
OUT_LIVE = DEV / "51-midi-live-both.json"
BASE = build.BASE
CROSS = os.environ.get("M68K_CROSS") or next(
    (c for c in ("m68k-linux-gnu-", "m68k-elf-") if shutil.which(c + "as")), "m68k-linux-gnu-")

MASK = 0x40192ba4                  # masque 34x34 libéré (272 o), désigné par la seule constante 0x400ac276
FORK_CAVE = 0x40167c50             # où le fork d'AveyCole mettait ce code (masque 35x35, groupe du filtre par piste)
OUT_THRU = 0x404e9b50              # l'octet du réglage OUT/THRU : 0 OUT, 1 THR (2 : THR + MIDI du Cycles)
GET = bytes.fromhex("4eb940044df8")                    # jsr 0x40044df8 (getter : mvs.b OUT_THRU,d0)
GATES = (                                              # trois portes : jsr GET ; tst.l d0 ; bne <jeter>
    (0x4000154a, "envoi 0x40001544 -> 0x400012f4"),
    (0x4000156a, "envoi d'un octet 0x40001564 -> 0x40001232 (horloge, temps réel)"),
    (0x40001590, "envoi d'un message 0x40001584 -> 0x40001100 (notes, paramètres)"),
)
KEY = 0x4003560a                   # touche de la ligne OUT/THRU (enregistrée en 0x40035f60) : OUT <-> THR
KEY_OLD = bytes.fromhex("4eb940044df84a8057c0710044802f4000044ef940044dc2")   # jsr GET ; ... ; jmp 0x40044dc2
SYMBOLS = ("midi_key", "midi_gate")                    # pour tools/emu/test_midi_thru.py
SOURCE = "https://github.com/AveyCole/Modded-Cycles, commit ba5f8bb"


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def compile_helper(at=MASK):
    """(octets, symboles) du code de midi-live-both lié à l'adresse at."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        obj, elf, out = d / "mt.o", d / "mt.elf", d / "cave.bin"
        run([CROSS + "as", "-mcpu=54418", "-o", str(obj), str(SRC / "midi_thru.S")])
        run([CROSS + "ld", "-T", str(SRC / "midi_thru.ld"), f"--defsym=CAVE={at:#x}", "--no-warn-rwx-segments",
             "-o", str(elf), str(obj)])
        syms = {}
        for line in run([CROSS + "nm", str(elf)]).splitlines():
            p = line.split()
            if len(p) == 3:
                syms[p[2]] = int(p[0], 16)
        run([CROSS + "objcopy", "-O", "binary", "-j", ".cave", str(elf), str(out)])
        code = out.read_bytes()
    if syms["midi_key"] != at:
        raise SystemExit(f"!! midi_key en {syms['midi_key']:#x}, attendu {at:#x}")
    return code, syms


def stock_mainos(path):
    """MAIN OS (section 3) du fichier officiel, refusé s'il n'est pas l'OS 1.13 de référence."""
    raw = pathlib.Path(path).read_bytes()
    device = json.loads((DEV / "device.json").read_text(encoding="utf-8"))
    if build.sha(raw) != device["stock_syx_sha256"]:
        raise SystemExit("!! ce n'est pas le fichier Model:Cycles OS 1.13 officiel")
    stream, _ = build.unwrap(raw)
    c = build.container.parse(stream)
    s3 = next(s for s in c["sections"] if s["id"] == 3)
    main = build.aplib.depack(c["blob"][s3["off"]:s3["off"] + s3["size"]])[0]
    if build.sha(main) != device["section_sha256"]:
        raise SystemExit("!! la section 3 ne correspond pas à l'OS 1.13 de référence")
    return main


def write(stock, va, old, new, what):
    if stock[va - BASE:va - BASE + len(old)] != old:
        raise SystemExit(f"!! octets d'origine inattendus en {va:#x} ({what})")
    if len(old) != len(new):
        raise SystemExit(f"!! {what} : {len(new)} octets pour {len(old)}")
    return {"off": va - BASE, "old": old.hex(), "new": new.hex()}


def build_both(stock):
    """midi-both : THR envoie toujours aussi le MIDI du Cycles."""
    writes = [write(stock, va, GET, bytes.fromhex("70004e714e71"), f"porte {what}") for va, what in GATES]
    return {
        "id": "midi-both",
        "order": 50,
        "name": "THRU qui envoie aussi le MIDI du Cycles",
        "description": [
            "Avec THR choisi dans CONFIG › MIDI › PORTS › OUT/THRU, le Cycles relaie toujours le MIDI reçu sur son "
            "MIDI IN et envoie aussi son horloge, ses notes et ses paramètres. OUT ne change pas, le menu non plus.",
            "Les trois portes qui jetaient le MIDI généré en THR (0x4000154a, 0x4000156a, 0x40001590) reçoivent "
            "moveq #0,d0 au lieu de l'appel au réglage. Aucune place libre. Ne va pas avec midi-live-both.",
            f"D'AveyCole ({SOURCE}), testé sur son Model:Cycles le 10/10/2026.",
            "Généré par tools/gen_midi_thru.py, notes/53.",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
        "conflicts": ["midi-live-both"],
        "writes": writes,
    }


def build_live(stock):
    """midi-live-both : FUNC + appui sur LEVEL/DATA, en THR, ajoute ou retire le MIDI du Cycles."""
    code, syms = compile_helper(MASK)
    room = sprites.zone(MASK)[1]
    kept = sprites.MASKS[MASK][3]
    if len(code) > room:
        raise SystemExit(f"!! {len(code)} o de code pour {room} o à {MASK:#x}")
    if stock[MASK - BASE:MASK - BASE + room] != stock[kept - BASE:kept - BASE + room]:
        raise SystemExit(f"!! le masque {MASK:#x} n'est pas identique à celui qu'on garde ({kept:#x})")
    jmp = bytes.fromhex("4ef9") + syms["midi_key"].to_bytes(4, "big")
    writes = [write(stock, KEY, KEY_OLD, jmp + bytes.fromhex("4e71") * ((len(KEY_OLD) - len(jmp)) // 2),
                    "touche OUT/THRU")]
    writes += [write(stock, va, GET, bytes.fromhex("4eb9") + syms["midi_gate"].to_bytes(4, "big"), f"porte {what}")
               for va, what in GATES]
    writes.append(sprites.redirect_write(MASK))
    writes.append(write(stock, MASK, stock[MASK - BASE:MASK - BASE + len(code)], code, "code dans le masque"))
    writes.sort(key=lambda w: w["off"])
    return {
        "id": "midi-live-both",
        "order": 51,
        "name": "THRU + MIDI du Cycles, commutable (FUNC + appui)",
        "description": [
            "Dans CONFIG › MIDI › PORTS, sur la ligne OUT/THRU qui affiche THR : FUNC + appui sur le potard "
            "LEVEL/DATA ajoute au relais l'envoi de l'horloge, des notes et des paramètres du Cycles, ou le retire. "
            "L'écran reste sur THR ; un appui sans FUNC passe en OUT comme à l'origine.",
            "Valeur 2 du réglage 0x404e9b50 (0 OUT, 1 THR), écrite par la copie de l'OS 0x40044b88 ; seules les trois "
            "portes de sortie la distinguent de THR. Ne va pas avec midi-both.",
            f"D'AveyCole ({SOURCE}), testé sur son Model:Cycles le 10/10/2026 avec ce code en 0x40167c50.",
            f"Code dans le masque de sprite 34x34 libéré {MASK:#x} (tools/sprites.py) : {len(code)} o. "
            "Généré par tools/gen_midi_thru.py, notes/53.",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
        "conflicts": ["midi-both"],
        "symbols": {n: f"{syms[n]:#x}" for n in SYMBOLS},
        "writes": writes,
    }


def build_tweaks(stock):
    tweaks = [build_both(stock), build_live(stock)]
    for t in tweaks:
        build.apply_writes(stock, [t])                 # les octets d'origine collent
    return tweaks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--check", action="store_true", help="vérifie que les JSON versionnés correspondent")
    args = ap.parse_args()
    stock = stock_mainos(args.cycles)
    bad = 0
    for out, tweak in zip((OUT_BOTH, OUT_LIVE), build_tweaks(stock)):
        text = json.dumps(tweak, indent=1, ensure_ascii=False) + "\n"
        if args.check:
            ok = out.exists() and out.read_text(encoding="utf-8") == text
            bad += not ok
            print(f"  {out.name} {'est à jour' if ok else 'NE CORRESPOND PAS (autres binutils ?)'}")
        else:
            out.write_text(text, encoding="utf-8")
            print(f"  écrit : {out.relative_to(HERE.parent)} ({len(tweak['writes'])} écritures)")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
