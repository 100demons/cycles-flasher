#!/usr/bin/env python3
"""Génère les tweaks des machines VA : « VA », « VA KICK », « VA SNARE », « VA HIHAT », machines ajoutées du
Model:Cycles d'après celles du firmware « Model-TG-VA-DR-v1 » de DavidCaruso (notes/56 §4).

  - 27-va.json : machines 7 à 10, après les 6 d'origine ;
  - 36-va-tg.json : avec Model-TG, machines 8 à 11 après son Sampler (les numéros du firmware de David : ses projets
    se rouvrent sur les mêmes machines) ; s'ajoute après model-tg-st (notes/31).

David n'a publié ni source ni licence : le code (tools/machines/va/va.c) est réécrit en C d'après la description de
ses algorithmes, aucun de ses octets n'est repris. Le son est le sien, échantillon par échantillon, sauf dans l'aigu
du VA HIHAT (deux débordements 32 bits corrigés) : tools/emu/test_va.py le vérifie contre tools/emu/va_ref.py, et
contre son firmware avec --david. Les tables (Osc2 Tune, Sweep Time, filtres) sont calculées ici par formule
(va_ref.c_header) ; aucun octet Elektron : le MAIN OS officiel sert à vérifier les octets d'origine, et la table des
descripteurs est recopiée au build depuis TON fichier (recette « cycles »), comme pour MACRO.

La mécanique des machines ajoutées est celle de MACRO (tools/gen_macro.py, notes/43), pour 4 machines : mêmes détours
(gs.detours_asm), mêmes tables déplacées, mêmes adresses dans la charge utile (gs.LAYOUT), même crochet de démarrage
(stub.S, PACK : la charge utile ne s'exécute qu'après l'invalidation du cache d'instructions par l'OS, 0x40000548).
Sans Model-TG, la boucle des voix appelle update/render par les tables déplacées ; avec Model-TG, le détour de MACRO
(gen_macro.dispatch_tg_asm) envoie nos machines à update/render puis à la fin de son étage d'amplitude (ah_noenv :
Attack, Filtre/Résonance, rééchantillonnage). Une voix muette n'est pas calculée (pas de régulateur de charge).

    python3 tools/gen_va.py --cycles model-cycles_OS1.13.syx [--check]

Les JSON versionnés sont compilés par m68k-linux-gnu-gcc 13.3 (Ubuntu 24.04) : un autre GCC peut donner d'autres
octets, et --check le dit.
"""
import argparse
import json
import pathlib
import struct
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "emu"))

import build                       # noqa: E402
import gen_macro as gm             # noqa: E402
import gen_macro_syntakt as gms    # noqa: E402
import gen_sdvintage_exact as gx   # noqa: E402
import gen_sdvintage_7th as g7     # noqa: E402
import gen_syntakt_machines as g8  # noqa: E402
import gen_syntakt_engines as gs   # noqa: E402
import sprites                     # noqa: E402
import usb_steady                  # noqa: E402
import va_ref                      # noqa: E402
import voice_loop                  # noqa: E402

DEV = HERE.parent / "tweaks" / "model-cycles_OS1.13"
OUT = DEV / "27-va.json"
OUT_TG = DEV / "36-va-tg.json"
SRC = HERE / "machines" / "va"
BASE = gx.BASE
# -fno-optimize-sibling-calls : sans appel terminal, une fonction ne réécrit pas ses arguments sur la pile. Avec
# Model-TG, notre détour réutilise ceux du render (sortie, voix) pour appeler ah_noenv : un « jmp va_post » final y
# mettait (sortie, machine), et Attack, Filtre et rééchantillonnage sautaient les batteries (tools/emu/test_va.py).
CFLAGS = ["-mcpu=54418", "-O2", "-U_FORTIFY_SOURCE", "-ffreestanding", "-fno-builtin",
          "-fno-tree-loop-distribute-patterns", "-fno-optimize-sibling-calls", "-nostdlib", "-fno-pic", "-fno-common",
          "-ffunction-sections", "-fdata-sections", "-fomit-frame-pointer", "-Wall", "-Wextra", "-Werror"]

# --- les machines (comme une entrée de gs.CATALOG) -------------------------------------------------------------
# knobs : COLOR, SHAPE, SWEEP, CONTOUR = (nom long, nom court, défaut), 0..127, les noms et défauts de David ;
# decay : défaut de l'Amp Decay (David : celui du Sampler de Model-TG, 64, pour les quatre ; ici 64 pour VA, et celui
# de la machine d'origine dont la batterie prend l'image : KICK 28, SNARE 40, METAL 20) ; image : celle d'une
# machine d'origine (l'OS n'en a que 6). Les formes d'onde (Osc1/Osc2 Wave) gardent la plage 0..127 de David et ses
# seuils (0..42 scie, 43..85 carré, 86..127 triangle) : ses projets sonnent pareil.
# render : la fonction de va.c ; kind : son numéro dans va_fill.
MACHINES = (
    dict(name="VA", label="VA", image=4, decay=64, render="va_render_va",
         knobs=(("Osc1 Wave", "OSC1", 0), ("Osc2 Wave", "OSC2", 0), ("Osc2 Tune", "DTUN", 68), ("Osc Mix", "MIX", 64))),
    dict(name="VA KICK", label="VA KICK", image=0, decay=28, render="va_render_kick",
         knobs=(("Sweep Depth", "SWP", 48), ("Sweep Time", "STM", 40), ("Drive", "SAT", 24), ("Click", "CLK", 40))),
    dict(name="VA SNARE", label="VA SNARE", image=1, decay=40, render="va_render_snare",
         knobs=(("Noise Mix", "NOIS", 64), ("Pitch Drop", "PENV", 32), ("Noise Tone", "TONE", 88), ("Drive", "SAT", 16))),
    dict(name="VA HIHAT", label="VA HIHAT", image=2, decay=20, render="va_render_hihat",
         knobs=(("Tone", "TONE", 80), ("Spread", "SPRD", 64), ("Noise", "NOIS", 16), ("Drive", "SAT", 0))),
)
N = len(MACHINES)
# Écran MACHINES : le nom est centré à x = 32 dans le cadre de 64 points de la moitié gauche (0x400a2600, police 5x9,
# un caractère tous les 6 points) : 8 caractères font 47 points, de x = 9 à 55. Model-TG s'en tient à 7 pour le nom
# défilant de son Sampler (NAME_W) ; « VA SNARE » et « VA HIHAT », les noms de David, en ont 8.
NAME_MAX = 8

BSS_OFF = gm.BSS_OFF                 # variables (6 pistes, 504 o) : là où MACRO met les siennes
LINK = """SECTIONS
{{
  .text {code:#x} : {{ *(.text.va_update) *(.text.va_render_*) *(.text*) }}
  .rodata : {{ *(.rodata*) }}
  .data : {{ *(.data*) }}
  .bss {bss:#x} (NOLOAD) : {{ *(.bss*) *(COMMON) }}
  /DISCARD/ : {{ *(.comment) *(.note*) *(.eh_frame*) }}
}}
"""
EXPORT = ("va_update", "va_render_va", "va_render_kick", "va_render_snare", "va_render_hihat", "va_fill", "va_post",
          "va_trk", "va_seed", "dr_seed")


def compile_machine(tmp, pay):
    """va.c (avec ses tables) lié à pay (code, tables, données) et pay + BSS_OFF (variables). Rend (octets de pay à la
    fin des données, symboles, fin du BSS)."""
    (tmp / "va_tables.h").write_text(va_ref.c_header())
    o = tmp / "va.o"
    gx.run([gx.CROSS + "gcc", *CFLAGS, f"-I{tmp}", "-c", str(SRC / "va.c"), "-o", str(o)])
    ld, elf, out = tmp / "va.ld", tmp / "va.elf", tmp / "va.bin"
    ld.write_text(LINK.format(code=pay, bss=pay + BSS_OFF))
    gx.run([gx.CROSS + "ld", "-T", str(ld), "--gc-sections", "--no-warn-rwx-segments", "-e", "va_update",
            *[a for s in EXPORT[1:] for a in ("-u", s)], "-o", str(elf), str(o)])
    secs = {}
    for line in gx.run([gx.CROSS + "objdump", "-h", str(elf)]).splitlines():
        f = line.split()
        if len(f) > 4 and f[0].isdigit():
            secs[f[1]] = (int(f[3], 16), int(f[2], 16))
    extra = set(secs) - {".text", ".rodata", ".data", ".bss"}
    if extra:
        raise SystemExit(f"!! sections inattendues : {sorted(extra)}")
    dis = gx.run([gx.CROSS + "objdump", "-d", str(elf)])
    if any(m in dis for m in ("\tmac", "\tmsac", "\tmov.l %acc", "\tmovclr")):
        raise SystemExit("!! instructions EMAC dans le code compilé (la boucle des voix laisse MACSR en fractionnaire)")
    gx.run([gx.CROSS + "objcopy", "-O", "binary", "-R", ".bss", str(elf), str(out)])
    blob = out.read_bytes()
    syms = {}
    for line in gx.run([gx.CROSS + "nm", str(elf)]).splitlines():
        p_ = line.split()
        if len(p_) == 3:
            syms[p_[2]] = int(p_[0], 16)
    if pay + len(blob) > gs.STUBS:
        raise SystemExit(f"!! code et tables trop grands : {len(blob)} o")
    bss = secs.get(".bss", (pay + BSS_OFF, 0))
    if bss[0] != pay + BSS_OFF or syms["va_trk"] != pay + BSS_OFF:
        raise SystemExit("!! BSS")
    return blob, syms, (bss[0] + bss[1] + 3) & ~3


def tweak_ids():
    """Tweaks qui ajoutent des machines, ou le même bloc après l'image : jamais avec les machines VA."""
    ids = gm.other_ids() | {"macro", "macro-tg", "model-tg", "va", "va-tg"}
    for codes in gs.subsets():
        ids |= {gms.tweak_id(codes), gms.tweak_id(codes, tg=True)}
    return ids


def build_tweak(img, tg=None):
    """Tweak des machines VA. tg : Model-TG (gs.tg_context) pour la version combinée."""
    pay = gs.PAY_TG if tg else gs.PAY_ALONE
    gs.set_base(pay)
    first = gs.TG_FIRST if tg else 6
    nm = first + N                              # machines : 6 d'origine, le Sampler avec Model-TG, puis les nôtres
    top = nm - 1
    cur = tg["img"] if tg else img              # l'image telle que nos écritures la trouvent
    u32 = lambda va: struct.unpack_from(">I", cur, va - BASE)[0]
    firsts = [76 + 5 * i for i in range(N)]     # 1er de leurs 5 descripteurs (4 potards, Amp Decay)
    if any(len(m["name"]) > NAME_MAX for m in MACHINES):
        raise SystemExit("!! nom de machine trop long pour l'écran MACHINES")
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        blob, syms, bss_end = compile_machine(tmp, pay)
        names_at, upd_at, rnd_at, map_at = gs.DATA, gs.DATA + 4 * nm, gs.DATA + 8 * nm, gs.DATA + 16 * nm
        stubs, ssyms = gm.assemble(tmp, "det", gs.detours_asm(N, [m["image"] for m in MACHINES], firsts, tg)
                                   + (gm.dispatch_tg_asm(syms, rnd_at, tg) if tg else ""), gs.STUBS)
        if gs.STUBS + len(stubs) > gs.DATA:
            raise SystemExit("!! détours trop grands")

        # --- données (comme gs.build_tweak) : noms, tables update/render, machine -> enregistrement, chaînes
        strings = [m["name"] for m in MACHINES] + [k[i] for m in MACHINES for k in m["knobs"] for i in (0, 1)]
        at, addr = map_at + ((nm + 3) & ~3), {}
        for s_ in strings:
            if s_ not in addr:
                addr[s_] = at
                at += len(s_) + 1
        if tg:                                  # noms : ceux de Model-TG (le Sampler montre son échantillon)
            blob_u32 = lambda va: struct.unpack_from(">I", tg["blob"], va - tg["blob_at"])[0]
            names = [blob_u32(tg["sampler_name_table"] + 4 * i) for i in range(7)]
        else:
            names = [u32(g7.NAMES + 4 * i) for i in range(6)]
        names += [addr[m["name"]] for m in MACHINES]
        pad = [u32(g7.UPDATE_TAB)] * (first - 6), [u32(g7.RENDER_TAB)] * (first - 6)   # entrée 6 du Sampler : jamais lue
        upd = [u32(g7.UPDATE_TAB + 4 * i) for i in range(6)] + pad[0] + [syms["va_update"]] * N
        rnd = [u32(g7.RENDER_TAB + 4 * i) for i in range(6)] + pad[1] + [syms[m["render"]] for m in MACHINES]
        data = bytearray()
        for t in (names, upd, rnd, range(1, nm + 1)):
            data += b"".join(g7.be32(x) for x in t)
        data += cur[gs.MAP - BASE:gs.MAP - BASE + 6] + bytes(range(6, nm)) + bytes(((nm + 3) & ~3) - nm)
        for s_ in addr:
            data += s_.encode("ascii") + b"\0"
        if gs.DATA + len(data) > gs.DESCN:
            raise SystemExit("!! données")

        # --- 5 descripteurs par machine, sur le modèle de ceux de SNARE (gs.build_tweak)
        new = bytearray()
        for m in MACHINES:
            for k, (long_, short, default) in enumerate(m["knobs"]):
                e = bytearray(img[g7.DESC + (g7.SNARE_DESC + k) * g7.DSTRIDE - BASE:][:g7.DSTRIDE])
                e[0x00:0x04] = g7.be32(6)       # « propre à une machine » ; rattaché à la sienne par les détours
                e[0x10:0x14] = g7.be32(default << 8)
                e[0x2c:0x30] = g7.be32(addr[long_])
                e[0x34:0x38] = g7.be32(addr[short])
                new += e
            e = bytearray(img[g7.DESC + (g7.SNARE_DESC + 4) * g7.DSTRIDE - BASE:][:g7.DSTRIDE])
            e[0x10:0x14] = g7.be32(m["decay"] << 8)
            new += e

        # --- écritures (comme gen_macro.build_tweak, pour N machines)
        writes = []

        def w(va, old, new_):
            if cur[va - BASE:va - BASE + len(old)] != old:
                raise SystemExit(f"!! {va:#x} : {old.hex()} attendu, {cur[va - BASE:va - BASE + len(old)].hex()} trouvé")
            writes.append({"off": va - BASE, "old": old.hex(), "new": new_.hex()})

        def moveq(va, old, new_, reg_byte):
            w(va, bytes([reg_byte, old]), bytes([reg_byte, new_]))

        def jmp(va):
            return bytes.fromhex("4ef9") + g7.be32(va)

        writes.append(None)                     # crochet de démarrage : écrit plus bas (il porte la liste des morceaux)
        red = sprites.redirect_write(gx.CAVE)
        w(BASE + red["off"], bytes.fromhex(red["old"]), bytes.fromhex(red["new"]))
        if tg:                                  # notre crochet, puis le sien (stub.S, CHAIN_TO)
            w(gs.BOOT_CALL + 2, g7.be32(tg["boot_extra_hook"]), g7.be32(gx.CAVE))
        else:
            w(gx.HOOK, bytes.fromhex(gx.HOOK_OLD), jmp(gx.CAVE) + bytes.fromhex("4e71"))
        names_src = tg["sampler_name_table"] if tg else g7.NAMES
        moved = {g7.DESC: gs.DESCN, g7.DESC + 8: gs.DESCN + 8, g7.DESC + 0x20: gs.DESCN + 0x20, g7.ROWS: gs.ROWSN,
                 g7.CCROWS: gs.CCROWSN, names_src: names_at, g7.UPDATE_TAB: upd_at, g7.RENDER_TAB: rnd_at,
                 gs.MAP: map_at}
        want = {g7.DESC: 34, g7.DESC + 8: 1, g7.DESC + 0x20: 2, g7.ROWS: 4 if tg else 5, g7.CCROWS: 2, gs.MAP: 1,
                g7.RENDER_TAB: 0 if tg else 1}
        for old, new_ in moved.items():
            rs = g7.refs32(cur, old)
            if len(rs) != want.get(old, 1):
                raise SystemExit(f"!! références à {old:#x} : {len(rs)}")
            for va in rs:
                w(va, g7.be32(old), g7.be32(new_))
        if tg:
            w(gs.DISPATCH[0], cur[gs.DISPATCH[0] - BASE:gs.DISPATCH[0] - BASE + 6], jmp(ssyms["dispatch"]))
        jumps = g7.JUMPS + g8.JUMPS8
        for va in g7.BOUNDS:
            if va in {j[0] for j in jumps}:
                continue
            b0, b1 = cur[va - BASE], cur[va - BASE + 1]
            if b0 & 0xf1 != 0x70 or b1 not in (75, 76):
                raise SystemExit(f"!! {va:#x}")
            moveq(va, b1, b1 + 5 * N, b0)
        for va, reg in ((0x400a7dba, 0x72), (0x400a7df4, 0x70), (0x4005a6a6, 0x72), (0x400147a4, 0x70),
                        (0x400148aa, 0x72), (0x400148b2, 0x70), (0x400a25e0, 0x70)):
            if tg and va == 0x4005a6a6:
                continue                        # son détour sampler_lfo_gate : chaîné par lfo_gate (plus bas)
            if cur[va - BASE] != reg or cur[va - BASE + 1] not in (5, 6):
                raise SystemExit(f"!! borne {va:#x}")
            moveq(va, cur[va - BASE + 1], top, reg)
        moveq(0x4005a572, 5, 6, 0x72)
        w(0x4005a2b8, bytes.fromhex("487800c0"), bytes.fromhex("4878") + (32 * nm).to_bytes(2, "big"))
        if nm > gs.MARKS_ROW:
            w(0x400a26a2, bytes.fromhex("7850428545f9"), jmp(ssyms["marks"]))
        else:
            moveq(0x400a26e8, cur[0x400a26e8 - BASE + 1], nm, 0x70)
        if not tg:
            for va in (0x4001b69c, 0x400a40a6, 0x400a4fb0):
                moveq(va, 5, 1, 0x70)
        chained = {0x4004df5c: "descr_hook", 0x4004df76: "descr_b_hook"}
        for va, old, sym in jumps:
            old = bytes.fromhex(old)
            if tg and va in chained:
                old = jmp(tg[chained[va]])
            w(va, old, jmp(ssyms[sym]))
        if tg:
            w(gs.AMP_ROW, bytes.fromhex("20065286eb88"), jmp(ssyms["amp_row"]))
            w(0x4005a6a6, jmp(tg["sampler_lfo_gate"]), jmp(ssyms["lfo_gate"]))
            w(0x4005a6b6, jmp(tg["sampler_amp_gate"]), jmp(ssyms["amp_gate"]))
        for va, old, sym in g7.CALLS:
            w(va, bytes.fromhex(old), bytes.fromhex("4eb9") + g7.be32(ssyms[sym]) + bytes.fromhex("4e71"))

        # --- charge utile
        parts = [
            {"dest": f"{pay:#x}", "hex": blob.hex()},
            {"dest": f"{gs.STUBS:#x}", "hex": stubs.hex()},
            {"dest": f"{gs.DATA:#x}", "hex": bytes(data).hex()},
            {"dest": f"{gs.DESCN:#x}", "cycles": [f"{g7.DESC:#x}", f"{g7.DESC + g7.NDESC * g7.DSTRIDE:#x}"]},
            {"dest": f"{gs.DESCN + g7.NDESC * g7.DSTRIDE:#x}", "hex": bytes(new).hex()},
        ]
        lo_, hi_ = g7.DESC - BASE, g7.DESC - BASE + g7.NDESC * g7.DSTRIDE
        final, orig = bytearray(cur[lo_:hi_]), img[lo_:hi_]
        alg = g7.ALG_DESC * g7.DSTRIDE + 0x0c
        if struct.unpack_from(">I", final, alg)[0] != (first - 1) << 8:
            raise SystemExit("!! max du paramètre Algorithm")
        struct.pack_into(">I", final, alg, top << 8)
        reloc = [[f"{gs.DESCN + k:#x}", orig[k:k + 4].hex(), final[k:k + 4].hex()]
                 for k in range(0, len(final), 4) if final[k:k + 4] != orig[k:k + 4]]
        size = bss_end - pay
        segs = gs.segments(parts, size)
        at = tg["at"] if tg else BASE + gx.IMAGE_LEN
        if at + sum(n_ for _, n_ in segs) > gs.END_LIMIT:
            raise SystemExit(f"!! ajout de {sum(n_ for _, n_ in segs)} o : l'image dépasserait {gs.END_LIMIT:#x}")
        (tmp / "segs.inc").write_text("".join(f"\t.long\t{a:#x}, {n_ // 4}\n" for a, n_ in segs))
        stub, _ = gm.assemble(tmp, "stub", gx.SRC / "stub.S", gx.CAVE, [
            f"-DPAYLOAD_SRC={at:#x}", f"-DPAYLOAD_DST={pay:#x}", f"-DPAYLOAD_LONGS={size // 4}", "-DPACK", f"-I{tmp}",
            *([f"-DCHAIN_TO={tg['boot_extra_hook']:#x}"] if tg else [])])
    if len(stub) > sprites.zone(gx.CAVE)[1] or gx.CAVE + len(stub) > gs.STUB_END:
        raise SystemExit("!! crochet de démarrage trop grand pour sa place")
    writes[0] = {"off": gx.CAVE - BASE, "old": "ff" * len(stub), "new": stub.hex()}
    if cur[gx.CAVE - BASE:gx.CAVE - BASE + len(stub)] != b"\xff" * len(stub):
        raise SystemExit("!! place du crochet de démarrage déjà prise")
    writes.sort(key=lambda x: x["off"])
    for a_, b_ in zip(writes, writes[1:]):
        if a_["off"] + len(a_["new"]) // 2 > b_["off"]:
            raise SystemExit(f"!! écritures qui se chevauchent en {BASE + b_['off']:#x}")

    tid = "va-tg" if tg else "va"
    ids = tweak_ids() | (set() if tg else {"model-tg-st"})
    which = ", ".join(f"{m['name']} (machine {first + i + 1})" for i, m in enumerate(MACHINES))
    out = {
        "id": tid,
        "order": 36 if tg else 27,
        "name": ("Model-TG + " if tg else "") + "Machines VA de DavidCaruso : VA, VA KICK, VA SNARE, VA HIHAT",
        "description": ([
            "Version combinée avec Model-TG (notes/31, notes/56 §4) : s'ajoute après model-tg-st, le Sampler reste la",
            f"7e machine, puis {which}, les numéros du firmware Model-TG-VA-DR-v1 de",
            "David. Leur sortie passe par l'étage d'amplitude de Model-TG (Attack, filtre, rééchantillonnage).",
        ] if tg else [
            f"Machines ajoutées après les 6 d'origine (notes/56 §4) : {which}.",
        ]) + [
            "D'après le firmware Model-TG-VA-DR-v1 de DavidCaruso, réécrites en C d'après ses algorithmes (aucun de",
            "ses octets) : VA = 2 oscillateurs scie/carré/triangle (Osc1 Wave, Osc2 Wave, Osc2 Tune, Osc Mix) ;",
            "batteries « analogiques » : KICK (Sweep Depth, Sweep Time, Drive, Click), SNARE (Noise Mix, Pitch Drop,",
            "Noise Tone, Drive), HIHAT 6 carrés du TR-808 (Tone, Spread, Noise, Drive). Calcul à 96 kHz ramené à 48",
            "par le décimateur de TONE ; hauteur, DECAY, GATE et PUNCH : la chaîne de TONE. Son identique à celui de",
            "David, sauf dans l'aigu du VA HIHAT (débordements 32 bits corrigés). Une voix muette n'est pas calculée.",
            "Généré par tools/gen_va.py (tools/machines/va/va.c). Aucun octet Elektron dans ce fichier.",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
    }
    if tg:
        out["requires"] = [tg["id"]]
    out.update({"conflicts": sorted(ids - {tid}), "writes": writes, "append": {
        "at": f"{at:#x}", "dest": f"{pay:#x}", "size": size, "parts": parts, "reloc": reloc,
        "pack": [[f"{a_:#x}", n_] for a_, n_ in segs]}})
    out["symbols"] = {k: f"{syms[k]:#x}" for k in EXPORT}          # pour la preuve (tools/emu/test_va.py)
    if not tg:                    # comme MACRO seule : envoi à l'USB à heure fixe (notes/35), boucle des voix
        out = usb_steady.add_to(out)          # (notes/36) ; la version combinée les a par model-tg-st
        out = voice_loop.add_to(out)
    return out, dict(code=len(blob), bss=bss_end - pay - BSS_OFF, image=sum(n_ for _, n_ in segs), stub=len(stub),
                     detours=len(stubs), syms=syms)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--check", action="store_true", help="vérifie que les JSON versionnés correspondent")
    args = ap.parse_args()
    img = g7.cycles_main(args.cycles)
    dev = json.loads((DEV / "device.json").read_text(encoding="utf-8"))
    if len(img) != gx.IMAGE_LEN or build.sha(img) != dev["section_sha256"]:
        raise SystemExit("!! ce n'est pas le MAIN OS 1.13 officiel")
    bad = 0
    for path, tg in ((OUT, None), (OUT_TG, gs.tg_context(img))):
        tweak, info = build_tweak(img, tg)
        base = tg["img"] if tg else img
        build.apply_writes(base, [tweak])            # un « old » faux échoue ici, pas dans le build
        text = json.dumps(tweak, indent=1, ensure_ascii=False) + "\n"
        print(f"  {tweak['id']} : {len(tweak['writes'])} écritures, code et tables {info['code']} o, variables "
              f"{info['bss']} o, détours {info['detours']} o, crochet {info['stub']} o, ajout à l'image {info['image']} o")
        bad += gm.emit(path, text, args.check)
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
