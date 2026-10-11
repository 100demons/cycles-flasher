#!/usr/bin/env python3
"""Génère 45-chord-keys.json : accords diatoniques sur TRIG 1–16 (notes/42).

Compile les sources ColdFire, les répartit dans des masques 47x47 identiques
redirigés vers leur exemplaire conservé, puis vérifie chaque écriture sur l'OS
officiel. Aucun code Elektron n'est incorporé hors des octets attendus des
écritures. Aucun firmware n'est exporté par ce générateur.

    python3 tools/gen_chord_keys.py --cycles firmware/model-cycles_OS1.13.syx [--check]
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

import build
import sprites
from mtlib import aplib, container
from mtlib.syx import unwrap

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = HERE / "machines/chord_keys"
OUT = ROOT / "tweaks/model-cycles_OS1.13/45-chord-keys.json"
BASE = 0x40000400
# m68k-elf uniquement : m68k-linux-gnu-gcc (ABI SVR4) lit dans a0 le pointeur rendu par une fonction, alors que
# l'OS le rend dans d0 (0x4000eb90 par exemple) ; ses appels à l'OS seraient faux (notes/42 §6).
CROSS = os.environ.get("M68K_CROSS") or "m68k-elf-"
CFLAGS = ["-mcpu=54418", "-Os", "-ffreestanding", "-fno-builtin", "-nostdlib", "-fno-pic", "-fno-common",
          "-ffunction-sections", "-fdata-sections", "-fomit-frame-pointer", "-fno-stack-protector",
          "-Wall", "-Wextra", "-Werror"]
# Les quatorze masques réservés à chord-keys (tools/AGENTS.md) ; les autres masques 47x47 libérés appartiennent à
# d'autres mods. Le placement remplit les masques dans cet ordre : un code plus gros échoue au lieu de déborder.
MASKS = (0x4016b6f8, 0x4016b9e8, 0x40171f30, 0x40172608, 0x40179730,
         0x40182b38, 0x40182e28, 0x40183118, 0x40185018, 0x40185968,
         0x40185c58, 0x4018cd48, 0x4018d1b8, 0x4018d4a8)
# Adresse, contrat attendu, symbole, opcode (None = pointeur de vtable).
HOOKS = (
    (0x400aae88, "4fefffe448d71c3c", "chord_audio_update", 0x4ef9),
    (0x400ab0e4, "d1fc4012142c", "chord_audio_ratios", 0x4ef9),
    (0x400ff9cc, "4001a0d2", "ck_ui_key", None),
    (0x400fd170, "4000a70e", "ck_shape_format", None),
    (0x400fd174, "4000a66a", "ck_shape_draw", None),
    (0x4001e4ca, "4eb94000b22a", "ck_shape_name", 0x4eb9),
    (0x4001cb3e, "4eb94002d138", "ck_ui_menu_ctor", 0x4eb9),
    (0x4005b4a8, "7001156b001c001c", "ck_storage_load_hook", 0x4ef9),
    (0x40061564, "1140001b48780010", "ck_storage_init_hook", 0x4ef9),
)


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def load_stock(path):
    device = json.loads((OUT.parent / "device.json").read_text())
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != device["stock_syx_sha256"]:
        raise ValueError("Le .syx n'est pas l'OS officiel 1.13 attendu")
    stream, _ = unwrap(raw)
    parsed = container.parse(stream)
    section = next(s for s in parsed["sections"] if s["id"] == 3)
    stock = aplib.depack(parsed["blob"][section["off"]:section["off"] + section["size"]])[0]
    if len(stock) != device["section_len"] or build.sha(stock) != device["section_sha256"]:
        raise ValueError("Le MAIN OS n'est pas l'image officielle attendue")
    return stock


def sections(path):
    found = []
    for line in run([CROSS + "objdump", "-h", str(path)]).splitlines():
        match = re.match(r"\s*\d+\s+(\.\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+\S+\s+\S+\s+2\*\*(\d+)", line)
        if match:
            name, size, address, align = match.groups()
            if int(size, 16):
                found.append((name, int(size, 16), int(address, 16), 1 << int(align)))
    return found


def compile_code():
    """Placement déterministe par section, sans casser une fonction entre deux masques."""
    if "linux" in CROSS or not shutil.which(CROSS + "gcc"):
        raise ValueError(f"{CROSS}gcc refusé ou introuvable : il faut m68k-elf-gcc (16.2.0 et binutils 2.47 pour "
                         "reproduire le JSON) ; m68k-linux-gnu-gcc lit dans a0 les pointeurs que l'OS rend dans d0")
    with tempfile.TemporaryDirectory(prefix="chord-keys-build-") as directory:
        tmp = Path(directory)
        objects, inputs = [], []
        for source in sorted((*SRC.glob("*.c"), *SRC.glob("*.S"))):
            obj = tmp / (source.name + ".o")
            run([CROSS + "gcc", *CFLAGS, "-c", str(source), "-o", str(obj)])
            objects.append(obj)
            for name, size, _, align in sections(obj):
                if name.startswith((".text", ".rodata", ".data", ".bss")):
                    # Le ColdFire exige une adresse paire à chaque entrée. Les tables
                    # locales prennent aussi le type T dans le masque mixte final ;
                    # les aligner évite de confondre leurs symboles avec du code impair.
                    align = max(align, 2)
                    inputs.append((obj, name, size, align))
        bins = [{"at": va, "size": 0, "parts": []} for va in MASKS]
        for obj, name, size, align in sorted(inputs, key=lambda s: (-s[2], s[0].name, s[1])):
            for block in bins:
                offset = (block["size"] + align - 1) & -align
                if offset + size <= 376:
                    block["parts"].append((obj, name, align))
                    block["size"] = offset + size
                    break
            else:
                raise ValueError(f"Section {obj.name}:{name} ({size} o) trop grande ou place épuisée")
        bins = [block for block in bins if block["parts"]]
        script = ["SECTIONS {"]
        for i, block in enumerate(bins):
            script.append(f"  .ck{i} {block['at']:#x} : {{")
            script.extend(f'    . = ALIGN({align}); "{obj}"({name})' for obj, name, align in block["parts"])
            script.append("  }")
        script.extend(("  /DISCARD/ : { *(.text) *(.data) *(.bss) *(.comment) *(.note*) *(.eh_frame*) }", "}"))
        linker = tmp / "chord_keys.ld"
        linker.write_text("\n".join(script) + "\n")
        elf = tmp / "chord_keys.elf"
        run([CROSS + "ld", "--no-warn-rwx-segments", "--orphan-handling=error", "-T", str(linker),
             "-o", str(elf), *map(str, objects)])
        symbols = {}
        for line in run([CROSS + "nm", str(elf)]).splitlines():
            fields = line.split()
            if len(fields) == 3 and fields[1].upper() in ("T", "D", "B", "R"):
                if fields[1].upper() == "T" and int(fields[0], 16) & 1:
                    raise ValueError(f"Symbole de code non aligné : {fields[2]}")
                # Deux tableaux statiques portent le même nom (scales) : garder la plus basse adresse, car l'ordre
                # de nm entre noms égaux dépend du tri de la libc de l'hôte (macOS et Linux diffèrent).
                address = int(fields[0], 16)
                symbols[fields[2]] = min(address, symbols.get(fields[2], address))
        result = []
        for name, size, address, _ in sections(elf):
            if not name.startswith(".ck"):
                raise ValueError(f"Section imprévue : {name}")
            if address not in MASKS or size > 376:
                raise ValueError(f"Section hors masque : {name}, {address:#x}, {size} o")
            binary = tmp / (name + ".bin")
            run([CROSS + "objcopy", "-O", "binary", "-j", name, str(elf), str(binary)])
            # Une section contenant uniquement du BSS doit aussi être initialisée.
            code = binary.read_bytes()
            if len(code) > size:
                raise ValueError("Taille extraite incohérente")
            result.append((address, code.ljust(size, b"\0")))
        return sorted(result), symbols


def build_tweak(stock):
    compiled, symbols = compile_code()
    writes = []
    for address, code in compiled:
        _, pointer, _, shared = sprites.MASKS[address]
        old = stock[address - BASE:address - BASE + 376]
        if old != stock[shared - BASE:shared - BASE + 376]:
            raise ValueError(f"Masque {address:#x} différent de l'exemplaire conservé")
        encoded = struct.pack(">I", address)
        locations = [m.start() for m in re.finditer(re.escape(encoded), stock)]
        if locations != [pointer - BASE]:
            raise ValueError(f"Références imprévues vers le masque {address:#x}")
        at = pointer - BASE
        if (stock[at - 2:at] not in (b"\x48\x79", b"\x2e\xbc") or
                stock[at + 4:at + 6] != b"\x48\x79" or
                stock[at + 10:at + 18] != bytes.fromhex("4878002f4878002f")):
            raise ValueError(f"Le constructeur du sprite {address:#x} a changé")
        writes.extend(({"off": address - BASE, "old": old[:len(code)].hex(), "new": code.hex()},
                       sprites.redirect_write(address)))
    for address, expected, symbol, opcode in HOOKS:
        old = bytes.fromhex(expected)
        if stock[address - BASE:address - BASE + len(old)] != old:
            raise ValueError(f"Contrat d'accroche inattendu à {address:#x}")
        new = struct.pack(">I", symbols[symbol]) if opcode is None else struct.pack(">HI", opcode, symbols[symbol])
        new += b"\x4e\x71" * ((len(old) - len(new)) // 2)
        writes.append({"off": address - BASE, "old": old.hex(), "new": new.hex()})
    tweak = {
        "id": "chord-keys", "order": 45, "name": "Accords de gamme sur TRIG 1–16",
        "description": [
            "Mode Keys dans FUNC + RETRIG : une piste CHORD, gamme et tonique, extensions par degré.",
            "TRIG 1–7 jouent I–VII, 8–14 les mêmes degrés une octave plus haut, 15–16 I–II deux octaves plus haut.",
            "Les grands pads T1–T6 gardent leur sélection et leur jeu stock. L'édition des pas reste disponible.",
            "Sept modes ; triades, septièmes, neuvièmes, onzièmes ou treizièmes diatoniques, quatre voix au plus.",
            "Les accords 9/11/13 omettent la quinte (et les extensions intermédiaires pour 11/13).",
            "SHAPE choisit BASE, CLS0–3 ou OPN0–3 ; COLOR règle le mélange sans déplacer les octaves.",
            "I–VII restent seuls responsables des extensions.",
            "Réglages par piste sauvegardés avec le pattern. Dernière touche prioritaire, sans retour à la précédente.",
            "Model-TG incompatible : son Scale Lock transforme les notes avant le moteur. Expérimental.",
            f"Code et état dans {len(compiled)} masques 47×47 redirigés, {sum(len(c) for _, c in compiled)} octets.",
            "Généré par tools/gen_chord_keys.py ; sources tools/machines/chord_keys/ ; notes/42.",
        ],
        "device": "Model:Cycles", "os": "1.13", "section": 3,
        "conflicts": ["model-tg", "model-tg-st"],
        "symbols": {name: f"{value:#x}" for name, value in sorted(symbols.items())},
        "writes": sorted(writes, key=lambda w: w["off"]),
    }
    build.apply_writes(stock, [tweak])
    for path in OUT.parent.glob("*.json"):
        other = json.loads(path.read_text())
        # un conflit déclaré d'un côté ou de l'autre (sample-preview partage quatre masques) : jamais construits ensemble
        if other.get("id") in (tweak["id"], *tweak["conflicts"]) or tweak["id"] in other.get("conflicts", []):
            continue
        for a in tweak["writes"]:
            for b in other.get("writes", []):
                lo, hi = max(a["off"], b["off"]), min(a["off"] + len(a["new"]) // 2, b["off"] + len(b["new"]) // 2)
                if lo < hi and bytes.fromhex(a["new"])[lo-a["off"]:hi-a["off"]] != bytes.fromhex(b["new"])[lo-b["off"]:hi-b["off"]]:
                    raise ValueError(f"Chevauchement avec {other['id']} à {BASE + lo:#x}")
    return tweak


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        tweak = build_tweak(load_stock(args.cycles))
        text = json.dumps(tweak, indent=1, ensure_ascii=False) + "\n"
        if args.check:
            if not OUT.exists() or OUT.read_text() != text:
                raise ValueError("Le JSON ne correspond pas aux sources / à cette version du compilateur")
            print("ok 45-chord-keys.json est à jour")
        else:
            OUT.write_text(text)
            print(f"ok {OUT.name} : {len(tweak['writes'])} écritures vérifiées")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"FAIL {error}\n{getattr(error, 'stderr', '')}") from error


if __name__ == "__main__":
    main()
