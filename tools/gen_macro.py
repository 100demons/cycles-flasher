#!/usr/bin/env python3
"""Génère les tweaks de la machine MACRO : les 47 modèles de synthèse de Braids, le module d'Émilie Gillet (code MIT),
en machine ajoutée du Model:Cycles (notes/43).

  - 25-macro.json : 7e machine, après les 6 d'origine ;
  - 32-macro-tg.json : avec Model-TG, 8e machine après son Sampler ; s'ajoute après model-tg-st (notes/31).

Le code de Braids (braids/ et stmlib/ de pichenettes/eurorack, au commit épinglé) est compilé tel quel avec notre
passerelle (tools/machines/macro/macro.cc), et ses octets sont dans le tweak (licence MIT : LICENSE-Braids, recopiée
à côté du flasher). Aucun octet Elektron : le MAIN OS officiel sert à vérifier les octets d'origine, et la table des
descripteurs est recopiée au build depuis TON fichier (recette « cycles », comme pour les moteurs du Syntakt).

La mécanique des machines ajoutées est celle des moteurs du Syntakt (gen_syntakt_engines.py, notes/20, notes/31) :
mêmes détours (gs.detours_asm), mêmes tables déplacées, mêmes adresses dans la charge utile (gs.LAYOUT). Ce qui
change : la machine est notre code, sans le Syntakt ; sans Model-TG, la boucle des voix appelle update/render par les
tables déplacées, sans détour ; avec Model-TG, un détour (dispatch_tg_asm) envoie la machine 7 chez nous et les autres
au dispatch de Model-TG. Pas de régulateur de charge : la passerelle ne calcule pas une voix muette.

    git clone https://github.com/pichenettes/eurorack vendor/eurorack
    git -C vendor/eurorack checkout 08460a69a7e1f7a81c5a2abcc7189c9a6b7208d4
    git -C vendor/eurorack submodule update --init stmlib
    python3 tools/gen_macro.py --cycles model-cycles_OS1.13.syx --eurorack vendor/eurorack [--check]

Les JSON versionnés sont compilés par m68k-linux-gnu-g++ 13.3 (Ubuntu 24.04) : un autre GCC donne d'autres octets,
et --check le dit.
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

import gen_sdvintage_exact as gx   # noqa: E402
import gen_sdvintage_7th as g7     # noqa: E402
import gen_syntakt_machines as g8  # noqa: E402
import gen_syntakt_engines as gs   # noqa: E402
import sprites                     # noqa: E402
import usb_steady                  # noqa: E402
import voice_loop                  # noqa: E402

DEV = HERE.parent / "tweaks" / "model-cycles_OS1.13"
OUT = DEV / "25-macro.json"
OUT_TG = DEV / "32-macro-tg.json"
LICENSE_OUT = DEV / "LICENSE-Braids"
SRC = HERE / "machines" / "macro"
BASE = gx.BASE

# --- Braids ------------------------------------------------------------------------------------------------
EURORACK_REPO = "pichenettes/eurorack"
EURORACK_COMMIT = "08460a69a7e1f7a81c5a2abcc7189c9a6b7208d4"     # 16/08/2023
STMLIB_COMMIT = "e3bd7c9cc00e4364166f9905c0509b6ffd0535ec"       # 30/05/2023, son sous-module stmlib à ce commit
SOURCES = ("braids/macro_oscillator.cc", "braids/analog_oscillator.cc", "braids/digital_oscillator.cc",
           "braids/resources.cc", "stmlib/utils/random.cc")
# -O2 : le coût mesuré d'une voix (notes/43 §8) ; pas d'exceptions ni de constructeurs globaux (rien ne les appelle)
CXXFLAGS = ["-mcpu=54418", "-O2", "-U_FORTIFY_SOURCE", "-fno-exceptions", "-fno-rtti", "-fno-threadsafe-statics",
            "-fno-use-cxa-atexit", "-fno-pic", "-fno-common", "-ffunction-sections", "-fdata-sections",
            "-fomit-frame-pointer"]
CFLAGS_RT = ["-mcpu=54418", "-O2", "-U_FORTIFY_SOURCE", "-ffreestanding", "-fno-builtin",
             "-fno-tree-loop-distribute-patterns", "-nostdlib", "-fno-pic", "-fno-common", "-ffunction-sections",
             "-fdata-sections", "-Wall", "-Wextra", "-Werror"]
# Modèles, dans l'ordre de Braids (SHAPE = 0..46 ; enum MacroOscillatorShape de braids/settings.h, sans QUESTION_MARK)
MODELS = ("CSAW", "MORPH", "SAW_SQUARE", "SINE_TRIANGLE", "BUZZ", "SQUARE_SUB", "SAW_SUB", "SQUARE_SYNC", "SAW_SYNC",
          "TRIPLE_SAW", "TRIPLE_SQUARE", "TRIPLE_TRIANGLE", "TRIPLE_SINE", "TRIPLE_RING_MOD", "SAW_SWARM", "SAW_COMB",
          "TOY", "DIGITAL_FILTER_LP", "DIGITAL_FILTER_PK", "DIGITAL_FILTER_BP", "DIGITAL_FILTER_HP", "VOSIM", "VOWEL",
          "VOWEL_FOF", "HARMONICS", "FM", "FEEDBACK_FM", "CHAOTIC_FEEDBACK_FM", "PLUCKED", "BOWED", "BLOWN", "FLUTED",
          "STRUCK_BELL", "STRUCK_DRUM", "KICK", "CYMBAL", "SNARE", "WAVETABLES", "WAVE_MAP", "WAVE_LINE",
          "WAVE_PARAPHONIC", "FILTERED_NOISE", "TWIN_PEAKS_NOISE", "CLOCKED_NOISE", "GRANULAR_CLOUD", "PARTICLE_NOISE",
          "DIGITAL_MODULATION")

# --- la machine (comme une entrée de gs.CATALOG) -----------------------------------------------------------
# knobs : COLOR, SHAPE, SWEEP, CONTOUR = (nom long, nom court, défaut[, min, max]) ; decay : défaut de l'Amp Decay ;
# image : celle de TONE (l'OS n'en a que 6), dont MACRO reprend la chaîne d'ampli
MACHINE = dict(name="MACRO", image=4, decay=50,
               knobs=(("Timbre", "TIMB", 64), ("Model", "MODL", 0, 0, len(MODELS) - 1), ("Color", "COLR", 64),
                      ("Env Timbre", "ENVT", 0)))

# --- charge utile : gs.LAYOUT (détours, données, descripteurs, rangées et enregistrements à PAY + 0x33000..) ---
# Le code de Braids, ses tables et ses données vont au début (jusqu'à STUBS) ; ses variables (6 voix de Braids, en BSS)
# après les enregistrements, là où les moteurs du Syntakt mettent leurs tables (TABLES_AT). Le crochet de démarrage
# met tout à zéro et recopie les morceaux (stub.S, PACK) : le BSS ne prend pas de place dans l'image.
BSS_OFF = 0x36000
LINK = """SECTIONS
{{
  .text {code:#x} : {{ *(.text.macro_update) *(.text.macro_render) *(.text*) }}
  .rodata : {{ *(.rodata*) }}
  .data : {{ *(.data*) }}
  .bss {bss:#x} (NOLOAD) : {{ *(.bss*) *(COMMON) }}
  /DISCARD/ : {{ *(.comment) *(.note*) *(.eh_frame*) }}
}}
"""
TG_FIRST = gs.TG_FIRST
BRAIDS_RENDER = "_ZN6braids15MacroOscillator6RenderEPKhPsj"      # MacroOscillator::Render(sync, buffer, size)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def check_sources(repo):
    """Le clone de pichenettes/eurorack au commit épinglé, sous-module stmlib compris, sans modification."""
    for path, want in ((repo, EURORACK_COMMIT), (repo / "stmlib", STMLIB_COMMIT)):
        if git(path, "rev-parse", "HEAD") != want:
            raise SystemExit(f"!! {path} : commit {want[:7]} attendu (git checkout, submodule update --init stmlib)")
        if git(path, "status", "--porcelain", "--untracked-files=no"):
            raise SystemExit(f"!! {path} : fichiers modifiés")


def license_text(repo):
    """Licence MIT de Braids, telle que dans les en-têtes de ses fichiers compilés ici."""
    head = (repo / SOURCES[0]).read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(head) if l.startswith("// Permission is hereby granted"))
    end = next(i for i, l in enumerate(head) if l.startswith("// THE SOFTWARE."))
    body = "\n".join(l[3:] if l.startswith("// ") else l[2:] for l in head[start:end + 1])
    return ("Machine MACRO of Modded-Cycles: compiled code of Braids by Emilie Gillet (files braids/macro_oscillator,\n"
            "analog_oscillator, digital_oscillator, resources and stmlib/utils/random of\n"
            f"https://github.com/{EURORACK_REPO}, commit {EURORACK_COMMIT[:7]}), under the MIT license:\n\n"
            "Copyright 2012-2013 Emilie Gillet.\n\n" + body + "\n")


def compile_machine(tmp, repo, pay, bss_at=None, code_end=None):
    """Braids + la passerelle, liés à pay (code, tables, données) et bss_at (variables ; pay + BSS_OFF par défaut).
    Le code et les données doivent finir avant code_end (gs.STUBS par défaut). Renvoie (octets de pay à la fin des
    données, symboles, fin du BSS)."""
    bss_at = pay + BSS_OFF if bss_at is None else bss_at
    code_end = gs.STUBS if code_end is None else code_end
    objs = []
    for s in SOURCES + (SRC / "macro.cc",):
        src = s if isinstance(s, pathlib.Path) else repo / s
        o = tmp / (src.stem + ".o")
        gx.run([gx.CROSS + "g++", *CXXFLAGS, f"-I{repo}", "-c", str(src), "-o", str(o)])
        objs.append(o)
    o = tmp / "rt.o"
    gx.run([gx.CROSS + "gcc", *CFLAGS_RT, "-c", str(SRC / "rt.c"), "-o", str(o)])
    objs.append(o)
    ld, elf, out = tmp / "link.ld", tmp / "macro.elf", tmp / "macro.bin"
    ld.write_text(LINK.format(code=pay, bss=bss_at))
    gx.run([gx.CROSS + "ld", "-T", str(ld), "--gc-sections", "--no-warn-rwx-segments", "-e", "macro_update",
            "-u", "macro_render", "-o", str(elf), *map(str, objs)])
    secs = {}
    for line in gx.run([gx.CROSS + "objdump", "-h", str(elf)]).splitlines():
        f = line.split()
        if len(f) > 4 and f[0].isdigit():
            secs[f[1]] = (int(f[3], 16), int(f[2], 16))      # adresse, taille
    extra = set(secs) - {".text", ".rodata", ".data", ".bss"}
    if extra:
        raise SystemExit(f"!! sections inattendues (constructeurs globaux ?) : {sorted(extra)}")
    gx.run([gx.CROSS + "objcopy", "-O", "binary", "-R", ".bss", str(elf), str(out)])
    blob = out.read_bytes()
    syms = {}
    for line in gx.run([gx.CROSS + "nm", str(elf)]).splitlines():
        p_ = line.split()
        if len(p_) == 3:
            syms[p_[2]] = int(p_[0], 16)
    if pay + len(blob) > code_end:
        raise SystemExit(f"!! code et tables de Braids trop grands : {len(blob)} o")
    bss = secs.get(".bss", (bss_at, 0))
    if bss[0] != bss_at:
        raise SystemExit("!! BSS")
    return blob, syms, (bss[0] + bss[1] + 3) & ~3


def dispatch_tg_asm(syms, rnd_at, tg):
    """Avec Model-TG : détour de l'appel update/render (0x400a7dfe, registres : gs.dispatch_asm). Les machines
    d'origine et le Sampler (index < 7) passent par le dispatch de Model-TG ; MACRO par nos update/render, puis par la
    fin de son étage d'amplitude (ah_noenv : Attack, Filtre/Résonance, rééchantillonnage) ; son temps va sur la page
    System de Model-TG (prof_trk). Comme gs.dispatch_tg_asm, sans le régulateur des moteurs du Syntakt."""
    return f"""
	.globl	dispatch
dispatch:
	cmp.l	%d4, %d0
	bcs.w	9f			/* machine hors borne : rien, comme l'OS */
	moveq	#{TG_FIRST}, %d0
	cmp.l	%d0, %d4
	bcc.s	4f
	jmp	{tg['sampler_dispatch']:#x}	/* machines d'origine, Sampler */
4:	move.l	0xfc07800c, %d0		/* minuteur de la page System de Model-TG */
	move.l	%d0, {tg['prof_ta']:#x}
	movea.l	%d6, %a0		/* update puis render, comme l'OS */
	movea.l	(%a0,%d4.l*4), %a1
	move.l	%a2, -(%sp)
	move.l	%fp, -(%sp)
	move.l	%d1, -(%sp)
	jsr	(%a1)
	move.l	%fp, -(%sp)
	move.l	%d3, -(%sp)
	lea	{rnd_at:#x}, %a0
	movea.l	(%a0,%d4.l*4), %a1
	jsr	(%a1)
	jsr	{tg['ah_noenv']:#x}		/* (sortie, voix) */
	lea	20(%sp), %sp
	move.l	0xfc07800c, %d0
	sub.l	{tg['prof_ta']:#x}, %d0
	bmi.s	9f
	lea	{tg['prof_trk']:#x}, %a0
	add.l	%d0, (%a0,%d2.l*4)
9:	jmp	{gs.DISPATCH[1]:#x}
"""


def assemble(tmp, name, src, at, defs=()):
    """Assemble src (texte, ou fichier .S) à l'adresse at : (octets, symboles)."""
    o, e, b = (tmp / (name + x) for x in (".o", ".elf", ".bin"))
    if isinstance(src, str):
        (tmp / (name + ".S")).write_text(src)
        src = tmp / (name + ".S")
    gx.run([gx.CROSS + "gcc", "-mcpu=54418", *defs, "-c", str(src), "-o", str(o)])
    gx.run([gx.CROSS + "ld", "-Ttext", f"{at:#x}", "-o", str(e), str(o)])
    gx.run([gx.CROSS + "objcopy", "-O", "binary", "-j", ".text", str(e), str(b)])
    syms = {p_[-1]: int(p_[0], 16) for p_ in (l.split() for l in gx.run([gx.CROSS + "nm", str(e)]).splitlines())
            if len(p_) == 3}
    return b.read_bytes(), syms


def other_ids():
    """Tweaks qui ajoutent des machines, ou le même bloc après l'image : jamais avec MACRO."""
    ids = {"sdvintage-snare", "sdvintage-exact", "sdvintage-7th", "syntakt-vintage", "syntakt-meter",
           "syntakt-tg-meter", "syntakt-tg-profile"}
    for codes in gs.subsets():
        ids |= {gs.subset_id(codes), gs.tweak_id(codes, tg=True)}
    return ids


def build_tweak(img, repo, tg=None):
    """Tweak de la machine MACRO. tg : Model-TG (gs.tg_context) pour la version combinée."""
    pay = gs.PAY_TG if tg else gs.PAY_ALONE
    gs.set_base(pay)
    first = TG_FIRST if tg else 6
    nm = first + 1                              # machines : 6 d'origine, le Sampler avec Model-TG, puis MACRO
    top = nm - 1
    n = 1
    cur = tg["img"] if tg else img              # l'image telle que nos écritures la trouvent
    u32 = lambda va: struct.unpack_from(">I", cur, va - BASE)[0]
    m = MACHINE
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        blob, syms, bss_end = compile_machine(tmp, repo, pay)
        names_at, upd_at, rnd_at, map_at = gs.DATA, gs.DATA + 4 * nm, gs.DATA + 8 * nm, gs.DATA + 16 * nm
        stubs, ssyms = assemble(tmp, "det", gs.detours_asm(n, [m["image"]], [76], tg)
                                + (dispatch_tg_asm(syms, rnd_at, tg) if tg else ""), gs.STUBS)
        if gs.STUBS + len(stubs) > gs.DATA:
            raise SystemExit("!! détours trop grands")

        # --- données (comme gs.build_tweak) : noms, tables update/render, machine -> enregistrement, chaînes
        strings = [m["name"]] + [k[i] for k in m["knobs"] for i in (0, 1)]
        at, addr = map_at + ((nm + 3) & ~3), {}
        for s_ in strings:
            if s_ not in addr:
                addr[s_] = at
                at += len(s_) + 1
        if tg:                                  # noms : ceux de Model-TG (le Sampler montre son échantillon)
            blob_u32 = lambda va: struct.unpack_from(">I", tg["blob"], va - tg["blob_at"])[0]
            names = [blob_u32(tg["sampler_name_table"] + 4 * i) for i in range(7)] + [addr[m["name"]]]
        else:
            names = [u32(g7.NAMES + 4 * i) for i in range(6)] + [addr[m["name"]]]
        pad = [u32(g7.UPDATE_TAB)] * (first - 6), [u32(g7.RENDER_TAB)] * (first - 6)   # entrée 6 du Sampler : jamais lue
        upd = [u32(g7.UPDATE_TAB + 4 * i) for i in range(6)] + pad[0] + [syms["macro_update"]]
        rnd = [u32(g7.RENDER_TAB + 4 * i) for i in range(6)] + pad[1] + [syms["macro_render"]]
        data = bytearray()
        for t in (names, upd, rnd, range(1, nm + 1)):
            data += b"".join(g7.be32(x) for x in t)
        data += cur[gs.MAP - BASE:gs.MAP - BASE + 6] + bytes(range(6, nm)) + bytes(((nm + 3) & ~3) - nm)
        for s_ in addr:
            data += s_.encode("ascii") + b"\0"
        if gs.DATA + len(data) > gs.DESCN:
            raise SystemExit("!! données")

        # --- 5 descripteurs, sur le modèle de ceux de SNARE (gs.build_tweak)
        new = bytearray()
        for k, (long_, short, default, *rng) in enumerate(m["knobs"]):
            e = bytearray(img[g7.DESC + (g7.SNARE_DESC + k) * g7.DSTRIDE - BASE:][:g7.DSTRIDE])
            e[0x00:0x04] = g7.be32(6)
            if rng:
                e[0x08:0x0c], e[0x0c:0x10] = g7.be32(rng[0] << 8), g7.be32(rng[1] << 8)
            e[0x10:0x14] = g7.be32(default << 8)
            e[0x2c:0x30] = g7.be32(addr[long_])
            e[0x34:0x38] = g7.be32(addr[short])
            new += e
        e = bytearray(img[g7.DESC + (g7.SNARE_DESC + 4) * g7.DSTRIDE - BASE:][:g7.DSTRIDE])
        e[0x10:0x14] = g7.be32(m["decay"] << 8)
        new += e

        # --- écritures (comme gs.build_tweak, sans ce qui est propre au Syntakt)
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
        # sans Model-TG, la référence à la table render est dans l'appel de la boucle des voix (0x400a7e14), que l'on
        # garde ; avec Model-TG, son dispatch l'a remplacé (et notre détour lit rnd_at)
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
            moveq(va, b1, b1 + 5 * n, b0)
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
        stub, _ = assemble(tmp, "stub", gx.SRC / "stub.S", gx.CAVE, [
            f"-DPAYLOAD_SRC={at:#x}", f"-DPAYLOAD_DST={pay:#x}", f"-DPAYLOAD_LONGS={size // 4}", "-DPACK", f"-I{tmp}",
            *([f"-DCHAIN_TO={tg['boot_extra_hook']:#x}"] if tg else [])])
    if len(stub) > sprites.zone(gx.CAVE)[1]:
        raise SystemExit("!! crochet de démarrage trop grand pour sa place")
    writes[0] = {"off": gx.CAVE - BASE, "old": "ff" * len(stub), "new": stub.hex()}
    if cur[gx.CAVE - BASE:gx.CAVE - BASE + len(stub)] != b"\xff" * len(stub):
        raise SystemExit("!! place du crochet de démarrage déjà prise")
    writes.sort(key=lambda x: x["off"])
    for a_, b_ in zip(writes, writes[1:]):
        if a_["off"] + len(a_["new"]) // 2 > b_["off"]:
            raise SystemExit(f"!! écritures qui se chevauchent en {BASE + b_['off']:#x}")

    tid = "macro-tg" if tg else "macro"
    ids = other_ids() | {"macro", "macro-tg", "model-tg"} | (set() if tg else {"model-tg-st"})
    out = {
        "id": tid,
        "order": 32 if tg else 25,
        "name": ("Model-TG + " if tg else "") + "Machine MACRO : les 47 modèles de synthèse de Braids (Émilie Gillet, MIT)",
        "description": ([
            "Version combinée avec Model-TG (notes/31, notes/43) : s'ajoute après model-tg-st, le Sampler reste la",
            f"7e machine, MACRO est la 8e. Sa sortie passe par l'étage d'amplitude de Model-TG (Attack, filtre).",
        ] if tg else [
            "Machine MACRO en 7e machine, après les 6 d'origine (notes/43).",
        ]) + [
            "SHAPE choisit le modèle (0..46, l'ordre de Braids), COLOR = TIMBRE, SWEEP = COLOR, CONTOUR : l'enveloppe",
            "d'ampli ouvre TIMBRE. Braids rend à 96 kHz, ramené à 48 kHz par un filtre demi-bande ; DECAY, GATE et",
            "PUNCH : la chaîne d'ampli d'origine, réglée comme TONE. Une voix muette n'est pas calculée.",
            f"Code de Braids compilé tel quel ({EURORACK_REPO} {EURORACK_COMMIT[:7]}, licence MIT : LICENSE-Braids)",
            "avec tools/machines/macro/macro.cc. Généré par tools/gen_macro.py. Aucun octet Elektron dans ce fichier.",
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
    # pour la preuve (tools/emu/test_macro.py) : les entrées de la passerelle et le rendu d'un bloc de Braids
    out["symbols"] = {k: f"{syms[n]:#x}" for k, n in (("macro_update", "macro_update"), ("macro_render", "macro_render"),
                                                       ("braids_render", BRAIDS_RENDER))}
    if not tg:                    # comme les moteurs du Syntakt seuls : envoi à l'USB à heure fixe (notes/35, la
        out = usb_steady.add_to(out)          # charge varie avec les voix muettes), boucle des voix (notes/36) ;
        out = voice_loop.add_to(out)          # la version combinée les a par model-tg-st
    return out, dict(code=len(blob), bss=bss_end - pay - BSS_OFF, image=sum(n_ for _, n_ in segs), syms=syms)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--eurorack", required=True, help=f"clone de {EURORACK_REPO} au commit {EURORACK_COMMIT[:7]}")
    ap.add_argument("--check", action="store_true", help="vérifie que les JSON versionnés correspondent")
    args = ap.parse_args()
    img = g7.cycles_main(args.cycles)
    if len(img) != gx.IMAGE_LEN:
        raise SystemExit("!! ce n'est pas le MAIN OS 1.13 officiel")
    repo = pathlib.Path(args.eurorack).resolve()
    check_sources(repo)
    bad = 0
    outs = [(OUT, None), (OUT_TG, gs.tg_context(img))]
    for path, tg in outs:
        tweak, info = build_tweak(img, repo, tg)
        text = json.dumps(tweak, indent=1) + "\n"
        print(f"  {tweak['id']} : {len(tweak['writes'])} écritures, code et tables {info['code']} o, variables "
              f"{info['bss']} o, ajout à l'image {info['image']} o")
        bad += emit(path, text, args.check)
    bad += emit(LICENSE_OUT, license_text(repo), args.check)
    if bad:
        raise SystemExit(1)


def emit(path, text, check):
    if check:
        ok = path.exists() and path.read_text(encoding="utf-8") == text
        print(f"    {path.name} {'est à jour' if ok else 'NE CORRESPOND PAS (autre GCC ?)'}")
        return not ok
    path.write_text(text, encoding="utf-8")
    print(f"    écrit : {path}")
    return 0


if __name__ == "__main__":
    main()
