#!/usr/bin/env python3
"""Génère tweaks/model-cycles_OS1.13/49-control-all-config.json : choisir les pistes que touche Control All (notes/58).

Control All (TRACK tenu + potard) change le paramètre sur les six pistes à la fois. Avec ce tweak, TRACK + TRIG 1-6
retire une piste de Control All ou l'y remet ; TRACK tenu, les TRIG 1-6 s'allument pour les pistes qui suivent et
restent éteints pour les autres. La piste active suit toujours, comme sur les Digitakt et Digitone. Le choix vit en
RAM : après l'allumage, toutes les pistes suivent de nouveau, comme à l'origine. Les pistes écartées gardent aussi
leur machine, leur destination de LFO et PUNCH/GATE quand on les change TRACK tenu.

Code : « Control All Config » 1.0 de durchgemacht (MIT, https://github.com/durchgemacht/cycles-control-all-config,
tag v1.0), testé sur un Model:Cycles dans ce dépôt d'origine. Sa source, telle que le commit fb3969b l'a découpée en
une section par routine (même image que v1.0, octet pour octet), est recopiée telle quelle dans
tools/machines/control_all_config/ avec sa licence ; ses neuf sections sont posées dans quatre masques de sprites
48×22 libérés (tools/sprites.py, notes/52). Les cinq accroches (un jmp de 6 o au début de chaque boucle de Control
All) et les deux entrées de vtable de TrackSelectionView sont celles du dépôt d'origine ; seules les adresses du code
changent. Les octets « old » viennent du fichier officiel de l'utilisateur, jamais du dépôt.

    python3 tools/gen_control_all_config.py --cycles model-cycles_OS1.13.syx [--check]
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

import build                        # noqa: E402
import gen_sdvintage_exact as gx    # noqa: E402  (CROSS, run)
import sprites                      # noqa: E402
from mtlib import aplib, container  # noqa: E402
from mtlib.syx import unwrap        # noqa: E402

SRC = HERE / "machines" / "control_all_config" / "control_all_config.s"
OUT = HERE.parent / "tweaks" / "model-cycles_OS1.13" / "49-control-all-config.json"
BASE = build.BASE
UPSTREAM = "https://github.com/durchgemacht/cycles-control-all-config"
UPSTREAM_TAG, UPSTREAM_COMMIT = "v1.0", "fb3969bc98c6496a45cd9b5bd639c88b70a6dd50"   # v1.0 = image 17ead2b6… ; ce commit : la même source, une section par routine

# (section de sortie, masque 48×22 libéré, sections de la source). cac_skip lit cac_mask et les boucles appellent
# cac_skip en relatif au PC (±32 Ko) : l'état, cac_skip et les boucles restent donc voisins. cac_keys et cac_leds
# désignent cac_mask et cac_held en absolu et vont n'importe où.
PLACEMENT = (
    (".m1", 0x4018b9c8, (".cac_state", ".cac_skip", ".cac_loop1", ".cac_loop2", ".cac_loop3")),
    (".m2", 0x4018bb48, (".cac_loop4", ".cac_loop5")),
    (".m3", 0x4018cbc8, (".cac_keys",)),
    (".m4", 0x4018d038, (".cac_leds",)),
)
# (début de boucle, 6 octets d'origine rejoués par le stub, symbole, rôle) : les cinq boucles « for (t = 0; t < 6) »
# de Control All (notes/58 §1)
HOOKS = (
    (0x4001d6f8, "20522668007c", "cac_loop1",
     "ParameterPageView::controlAll 0x4001d6e4 : potard tourné, delta sur chaque piste (compteur d2)"),
    (0x4001d5a2, "20522f032f02", "cac_loop2",
     "ParameterPageView 0x4001d590 : une valeur sur chaque piste, p. ex. profondeur du LFO (compteur d2)"),
    (0x4001ebd2, "205248780020", "cac_loop3",
     "ParameterPageView::setLFO 0x4001eaa2 : destination du LFO sur chaque piste (compteur a3)"),
    (0x4001ac7a, "2f022f034e92", "cac_loop4",
     "0x4001ac4a : TRACK + PUNCH/GATE sur chaque piste (compteur d2)"),
    (0x400a2798, "2f022f054e94", "cac_loop5",
     "écran MACHINES 0x400a2712 : la machine de chaque piste (compteur d2, d4 += 12)"),
)
# (entrée de la vtable de TrackSelectionView 0x40100ee0, fonction d'origine, symbole, rôle)
VTABLE = (
    (0x40100ee8, 0x40024078, "cac_keys", "consumeKeyEvent(view, event)"),
    (0x40100f98, 0x40023d8c, "cac_leds", "producteur de LED (thunk : view + 0x68, avail, out)"),
)
SYMBOLS = ("cac_mask", "cac_held", "cac_skip", "cac_loop1", "cac_loop2", "cac_loop3", "cac_loop4", "cac_loop5",
           "cac_keys", "cac_leds")               # pour tools/emu/test_control_all_config.py


def main_os_from_syx(path):
    """Section 3 (MAIN OS) décompressée du .syx officiel ; sans numpy ni Unicorn (tools/emu/test_sdvintage.py en a)."""
    stream, _ = unwrap(pathlib.Path(path).read_bytes())
    c = container.parse(stream)
    s3 = next(s for s in c["sections"] if s["id"] == 3)
    return aplib.depack(c["blob"][s3["off"]:s3["off"] + s3["size"]])[0]


def assemble():
    """{section de sortie: (adresse, octets)}, symboles."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        obj, elf, ld = d / "cac.o", d / "cac.elf", d / "cac.ld"
        gx.run([gx.CROSS + "gcc", "-mcpu=54418", "-c", str(SRC), "-o", str(obj)])
        ld.write_text("SECTIONS\n{\n" + "".join(
            f"    {out} {mask:#x} : {{ {' '.join('*(' + s + ')' for s in secs)} }}\n" for out, mask, secs in PLACEMENT)
            + "    /DISCARD/ : { *(*) }\n}\n")
        gx.run([gx.CROSS + "ld", "-T", str(ld), "--no-warn-rwx-segments", "-o", str(elf), str(obj)])
        syms = {}
        for line in gx.run([gx.CROSS + "nm", str(elf)]).splitlines():
            p = line.split()
            if len(p) == 3:
                syms[p[2]] = int(p[0], 16)
        headers = subprocess.run([gx.CROSS + "objdump", "-h", str(elf)], capture_output=True, text=True,
                                 check=True).stdout
        secs = {}
        for out, _, _ in PLACEMENT:
            raw = d / (out.strip(".") + ".bin")
            gx.run([gx.CROSS + "objcopy", "-O", "binary", "-j", out, str(elf), str(raw)])
            secs[out] = (int(headers.split(out + " ")[1].split()[1], 16), raw.read_bytes())
    return secs, syms


def build_tweak(stock):
    secs, syms = assemble()
    writes, used = [], {}
    for out, mask, _ in PLACEMENT:
        addr, code = secs[out]
        size, kept = sprites.MASKS[mask][0], sprites.kept_of(mask)
        if addr != mask or len(code) > size:
            raise SystemExit(f"!! {out} : {len(code)} o à {addr:#x}, place {size} o à {mask:#x}")
        if stock[mask - BASE:mask - BASE + size] != stock[kept - BASE:kept - BASE + size]:
            raise SystemExit(f"!! le masque {mask:#x} n'est pas identique au masque gardé {kept:#x}")
        writes.append({"off": addr - BASE, "old": stock[addr - BASE:addr - BASE + len(code)].hex(), "new": code.hex()})
        writes.append(sprites.redirect_write(mask))
        used[mask] = len(code)
    code_all = b"".join(secs[out][1] for out, _, _ in PLACEMENT)
    for va, old_hex, sym, _ in HOOKS:
        old = bytes.fromhex(old_hex)
        if stock[va - BASE:va - BASE + 6] != old:
            raise SystemExit(f"!! octets d'origine inattendus en {va:#x}")
        if old not in code_all or b"\x4e\xf9" + struct.pack(">I", va + 6) not in code_all:
            raise SystemExit(f"!! {sym} ne rejoue pas les octets de {va:#x} ou ne revient pas en {va + 6:#x}")
        writes.append({"off": va - BASE, "old": old_hex, "new": struct.pack(">HI", 0x4ef9, syms[sym]).hex()})
    for va, fn, sym, _ in VTABLE:
        old = struct.pack(">I", fn)
        if stock[va - BASE:va - BASE + 4] != old:
            raise SystemExit(f"!! la vtable en {va:#x} ne pointe pas sur {fn:#x}")
        writes.append({"off": va - BASE, "old": old.hex(), "new": struct.pack(">I", syms[sym]).hex()})
    writes.sort(key=lambda w: w["off"])
    place = ", ".join(f"{n} o en {m:#x}" for m, n in used.items())
    tweak = {
        "id": "control-all-config",
        "order": 49,
        "name": "Control All : choix des pistes",
        "description": [
            "TRACK + TRIG 1-6 retire la piste 1-6 de Control All (TRACK tenu + potard) ou l'y remet ; TRACK tenu, les "
            "TRIG 1-6 s'allument pour les pistes qui suivent et restent éteints pour les autres.",
            "La piste active suit toujours, comme sur les Digitakt et Digitone. Les pistes écartées gardent aussi leur "
            "machine, leur destination de LFO et PUNCH/GATE quand on les change TRACK tenu.",
            "Choix en RAM seulement : après l'allumage, toutes les pistes suivent de nouveau, comme à l'origine.",
            f"Code de Control All Config {UPSTREAM_TAG} (durchgemacht, MIT, {UPSTREAM}) dans quatre masques de sprites "
            f"48×22 libérés (tools/sprites.py) : {place}. Généré par tools/gen_control_all_config.py, notes/58.",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
        "conflicts": [],
        "version": UPSTREAM_TAG,
        "source": f"{UPSTREAM}/tree/{UPSTREAM_COMMIT}",
        "symbols": {n: f"{syms[n]:#x}" for n in SYMBOLS},
        "writes": writes,
    }
    return tweak


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--check", action="store_true", help="vérifie que le JSON versionné correspond")
    args = ap.parse_args()
    stock = main_os_from_syx(args.cycles)
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
    print(f"  écrit : {OUT.relative_to(HERE.parent)} ({len(tweak['writes'])} écritures)")


if __name__ == "__main__":
    main()
