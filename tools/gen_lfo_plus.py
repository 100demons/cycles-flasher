#!/usr/bin/env python3
"""Génère tweaks/model-cycles_OS1.13/60-lfo-plus.json : LFO 2, 3, 4, trois LFO de plus par piste (notes/56 §3).

Idée et premier essai de DavidCaruso (son .syx « Model-TG-VA-DR-v1 », envoyé à Maxime en octobre 2026, sans source
ni licence) : réécrit ici à partir de l'analyse de son binaire, sans reprendre ses octets. Sur la page LFO, chaque
appui sur [LFO] passe à LFO 2, 3, 4 (grand chiffre dans le cadre de gauche), le 5e ferme la page ; SPD, MULT, WAVE,
DEST, DEP sont propres à chaque LFO de plus, FADE/SPH/MODE (et le retrig) sont ceux de LFO 1. LFO 2 est sauvé avec
le son et p-lockable ; LFO 3 et 4 vivent en mémoire (pas sauvés, pas de p-lock).

Différences voulues avec la version de David, pour qu'il s'installe avec tous nos mods (avec ou sans Model-TG,
avec les machines ajoutées, MACRO, arp, accords…) sans écrire un seul octet qu'un autre tweak écrit :
  - id -> k accroché en 0x4005a4ea (pas 0x4005a4e8, dont la borne est réécrite par les machines ajoutées) ;
  - LFO 2 empaqueté/relu dans les fonctions de sauvegarde/chargement du son de l'OS, mais plus loin que leur entrée
    (que Model-TG détourne) : 0x4005b028, 0x4005b0dc, 0x4005af1c ; défauts d'un son neuf à la fin de 0x40061866 ;
  - anti-doublon de la molette DEST dans la fonction de l'OS 0x4000c140 (pas dans fine_hook de Model-TG) ;
  - LFO 2 n'est pas calculé quand aucune piste ne lui donne de destination ; sa destination (k = 31) est recopiée
    brute, comme l'OS le fait pour k = 4, et ne glisse plus par les destinations intermédiaires.

tools/machines/lfo_plus/lfo_plus.S, assemblé (m68k-linux-gnu-gcc -mcpu=54418) ; ses sections sont réparties dans
les masques de sprites 34x34 libérés de MASKS (premier qui convient, plus grosses d'abord), chacun redirigé vers le
masque gardé (tools/sprites.py). Mémoire de travail (états des LFO, faux obj) : SCR, au-dessus du BSS de l'OS.

    python3 tools/gen_lfo_plus.py --cycles model-cycles_OS1.13.syx [--check]
"""
import argparse
import json
import pathlib
import re
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

SRC = HERE / "machines" / "lfo_plus" / "lfo_plus.S"
OUT = HERE.parent / "tweaks" / "model-cycles_OS1.13" / "60-lfo-plus.json"
BASE = gx.BASE
# Les masques 34x34 (272 o) réservés à ce mod, remplis dans cet ordre ; ceux qui restent vides ne sont pas touchés.
MASKS = (0x4016f8c8, 0x40173848, 0x401780a8, 0x401784e8, 0x401835b8,
         0x40184df8, 0x40185308, 0x40185f48, 0x40186238, 0x40189618)
ROOM = 272
# Mémoire de travail (1 180 o) : trou de 32 Ko entre la fin du BSS de l'OS (0x423380b0) et ses premiers tampons
# DMA (0x42340000, alias sans cache 0x4a340000), que rien ne vise (notes/56 §3, notes/44). Pas remise à zéro au
# démarrage : lfo_plus.S la met à zéro au premier usage, tant que l'octet ready (dans un masque, donc rechargé à 0
# depuis la flash à chaque démarrage) vaut 0.
SCR = 0x4233f000
SCR_SIZE = 1180
# (adresse, octets d'origine, symbole, instruction, rôle)
HOOKS = (
    (0x400597c6, "4eb940091ab2", "lfo_audio", 0x4eb9,
     "fonction audio (0x4005979e) : jsr 0x40091ab2 (les 6 LFO) -> jsr lfo_audio"),
    (0x4005a4ea, "202f0004b280", "lfo_id2k", 0x4ef9,
     "id -> k (0x4005a4e8, après la borne) : move.l 4(sp),d0 ; cmp.l d0,d1 -> jmp lfo_id2k"),
    (0x4005aa22, "202f000cb481", "lfo_plk_load", 0x4ef9,
     "rangée de p-locks -> k (0x4005aa1a) : move.l 12(sp),d0 ; cmp.l d1,d2 -> jmp lfo_plk_load"),
    (0x4005b9c6, "16b5480317420001", "lfo_plk_save", 0x4eb9,
     "enregistrement des p-locks (0x4005b95c) : move.b 3(a5,d4.l),(a3) ; move.b d2,1(a3) -> jsr lfo_plk_save ; nop"),
    (0x4005b028, "356b005e005c", "lfo_pack", 0x4eb9,
     "sauvegarde du son, format 2 (0x4005afa0) : move.w 94(a3),92(a2) -> jsr lfo_pack"),
    (0x4005b0dc, "356b005e005c", "lfo_pack", 0x4eb9,
     "sauvegarde du son, format 1 (0x4005b054) : move.w 94(a3),92(a2) -> jsr lfo_pack"),
    (0x4005af1c, "41f94010eea8", "lfo_unpack", 0x4eb9,
     "chargement du son (0x4005aecc) : lea 0x4010eea8,a0 -> jsr lfo_unpack"),
    (0x400618e2, "e18b35430026", "lfo_init", 0x4eb9,
     "son aux défauts (0x40061866) : lsl.l #8,d3 ; move.w d3,38(a2) -> jsr lfo_init"),
    (0x40025e10, "4feffff02f0a", "lfo_gate", 0x4ef9,
     "p-lock depuis les rappels de la vue LFO : lea -16(sp),sp ; move.l a2,-(sp) -> jmp lfo_gate"),
    (0x4001c3dc, "4eb940025798", "lfo_ctor", 0x4eb9,
     "création de la vue LFO : jsr 0x40025798 -> jsr lfo_ctor"),
    (0x400d97f8, "2f4a0008245f", "lfo_dtor", 0x4ef9,
     "destruction de la vue LFO (0x400d979a) : move.l a2,8(sp) ; movea.l (sp)+,a2 -> jmp lfo_dtor"),
    (0x4000c140, "4e56ffe0202e000c", "lfo_dest", 0x4ef9,
     "pas de la liste des destinations (DEST) : link.w fp,#-32 ; move.l 12(fp),d0 -> jmp lfo_dest ; nop"),
)
# (adresse du pointeur, valeur d'origine, symbole, rôle)
PTRS = (
    (0x400fd150, 0x4000ae20, "lfo_get", "vtable 0x400fd134 [28] : get des réglages de la piste active"),
    (0x400fd190, 0x4000ba7a, "lfo_set", "vtable 0x400fd134 [92] : set des réglages de la piste active"),
    (0x401016e4, 0x40024e86, "lfo_key", "vtable de la vue LFO 0x401016dc [2] : touche"),
    (0x401016ec, 0x400426fa, "lfo_draw", "vtable de la vue LFO 0x401016dc [4] : dessin"),
)
SYMBOLS = ("lfo_audio", "lfo_id2k", "lfo_get", "lfo_set", "lfo_key", "lfo_draw", "lfo_ctor", "lfo_dtor", "lfo_gate",
           "lfo_dest", "lfo_pack", "lfo_unpack", "lfo_init", "lfo_plk_save", "lfo_plk_load", "page", "eat", "ready", "view",
           "lfo34")


CONFLICTS = ["track-filter"]   # mêmes k 28..31 et mêmes octets +88..+91 du son (notes/56 §3.6, notes/47 §4)

def sections(path):
    """[(nom, taille, adresse, alignement)] des sections non vides."""
    found = []
    for line in gx.run([gx.CROSS + "objdump", "-h", str(path)]).splitlines():
        m = re.match(r"\s*\d+\s+(\.\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+\S+\s+\S+\s+2\*\*(\d+)", line)
        if m and int(m.group(2), 16):
            found.append((m.group(1), int(m.group(2), 16), int(m.group(3), 16), 1 << int(m.group(4))))
    return found


def compile_lfo():
    """Assemble, répartit les sections dans les masques, lie. Rend ([(masque, octets)], symboles)."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        obj, elf, ld = d / "lfo.o", d / "lfo.elf", d / "lfo.ld"
        gx.run([gx.CROSS + "gcc", "-mcpu=54418", f"-Wa,--defsym,SCR={SCR:#x}", "-c", str(SRC), "-o", str(obj)])
        parts = [(n, s, max(a, 2)) for n, s, _, a in sections(obj) if n.startswith((".text.", ".data."))]
        if [n for n, *_ in sections(obj) if not n.startswith((".text.", ".data."))]:
            raise SystemExit("!! section inattendue dans lfo_plus.o")
        bins = [{"at": va, "size": 0, "parts": []} for va in MASKS]
        for name, size, align in sorted(parts, key=lambda p: (-p[1], p[0])):
            for b in bins:
                at = (b["size"] + align - 1) & -align
                if at + size <= ROOM:
                    b["parts"].append((name, align))
                    b["size"] = at + size
                    break
            else:
                raise SystemExit(f"!! {name} ({size} o) : plus de place dans les masques")
        bins = [b for b in bins if b["parts"]]
        script = ["SECTIONS {"]
        for i, b in enumerate(bins):
            script.append(f"  .m{i} {b['at']:#x} : {{")
            script.extend(f"    . = ALIGN({a}); *({n})" for n, a in b["parts"])
            script.append("  }")
        # .text/.data/.bss par défaut sont vides (vérifié ci-dessus) : on les jette
        script += ["  /DISCARD/ : { *(.text) *(.data) *(.bss) *(.comment) *(.note*) *(.eh_frame*) }", "}"]
        ld.write_text("\n".join(script) + "\n")
        gx.run([gx.CROSS + "ld", "--no-warn-rwx-segments", "--orphan-handling=error", "-T", str(ld), "-o", str(elf),
                str(obj)])
        syms = {}
        for line in gx.run([gx.CROSS + "nm", str(elf)]).splitlines():
            p = line.split()
            if len(p) == 3:
                syms[p[2]] = int(p[0], 16)
        out = []
        for name, size, addr, _ in sections(elf):
            if addr not in MASKS or size > ROOM:
                raise SystemExit(f"!! section {name} hors masque : {size} o à {addr:#x}")
            binf = d / (name.strip(".") + ".bin")
            gx.run([gx.CROSS + "objcopy", "-O", "binary", "-j", name, str(elf), str(binf)])
            out.append((addr, binf.read_bytes().ljust(size, b"\0")))
    return sorted(out), syms


def build_tweak(stock):
    placed, syms = compile_lfo()
    writes = []
    for addr, code in placed:
        size, const, _, kept = sprites.MASKS[addr]
        if size != ROOM or stock[addr - BASE:addr - BASE + size] != stock[kept - BASE:kept - BASE + size]:
            raise SystemExit(f"!! le masque {addr:#x} n'est pas identique au masque gardé {kept:#x}")
        if [m.start() for m in re.finditer(re.escape(struct.pack(">I", addr)), stock)] != [const - BASE]:
            raise SystemExit(f"!! références imprévues vers le masque {addr:#x}")
        writes.append({"off": addr - BASE, "old": stock[addr - BASE:addr - BASE + len(code)].hex(), "new": code.hex()})
        writes.append(sprites.redirect_write(addr))
    for va, old_hex, sym, op, _ in HOOKS:
        old = bytes.fromhex(old_hex)
        if stock[va - BASE:va - BASE + len(old)] != old:
            raise SystemExit(f"!! octets d'origine inattendus en {va:#x}")
        new = struct.pack(">HI", op, syms[sym])
        new += b"\x4e\x71" * ((len(old) - len(new)) // 2)
        writes.append({"off": va - BASE, "old": old_hex, "new": new.hex()})
    for va, old_val, sym, _ in PTRS:
        old = struct.pack(">I", old_val)
        if stock[va - BASE:va - BASE + 4] != old:
            raise SystemExit(f"!! pointeur d'origine inattendu en {va:#x}")
        writes.append({"off": va - BASE, "old": old.hex(), "new": struct.pack(">I", syms[sym]).hex()})
    writes.sort(key=lambda w: w["off"])
    used = sum(len(c) for _, c in placed)
    masks = ", ".join(f"{a:#x}" for a, _ in placed)
    tweak = {
        "id": "lfo-plus",
        "order": 60,
        "name": "LFO 2, 3, 4 : trois LFO de plus par piste (idée de DavidCaruso)",
        "description": [
            "Page LFO : chaque appui sur [LFO] passe à LFO 2, puis 3, puis 4 (grand chiffre dans le cadre de gauche) ; "
            "le 5e ferme la page.",
            "Chaque LFO de plus a ses SPD, MULT, WAVE, DEST, DEP ; FADE, SPH, MODE et le retrig sont ceux de LFO 1. "
            "Même calcul que LFO 1 (la fonction des LFO de l'OS, avec son état à part).",
            "LFO 2 : sauvé avec le son (kit, réserve de sons ; 4 octets libres de l'enregistrement, même format que "
            "DavidCaruso), p-lockable. LFO 3 et 4 : un réglage par piste en mémoire, pas sauvé, pas de p-lock, "
            "remis aux défauts au démarrage.",
            "Un LFO de plus réglé sur la destination de LFO 1 ne fait rien ; la molette DEST saute les destinations "
            "déjà prises par un autre LFO de la piste. LFO 2 non calculé quand aucune piste n'a de destination.",
            "Corrige au passage les p-locks d'Attack, Filtre et Résonance de Model-TG dans le pattern (relus en None, "
            "LFO Speed, Multiplier).",
            "D'après le Model-TG-VA-DR-v1 de DavidCaruso (octobre 2026), réécrit ; s'installe avec ou sans Model-TG.",
            f"Code et données : {used} o dans {len(placed)} masques de sprites 34x34 libérés ({masks}) ; "
            f"mémoire de travail {SCR:#x}..{SCR + SCR_SIZE:#x} (au-dessus du BSS). "
            "Généré par tools/gen_lfo_plus.py, notes/56 §3.",
            "Pas avec le filtre par piste : les deux rangent leurs réglages en k 28..31 et en +88..+91 du son (notes/56 §3.6).",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
        "conflicts": CONFLICTS,
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
