#!/usr/bin/env python3
"""Génère le tweak de la machine Feral : 10 moteurs de synthèse bruités, imprévisibles et peu coûteux, en machine
ajoutée du Model:Cycles (notes/58).

  - 27-feral.json : 7e machine, après les 6 d'origine. Feral s'installe seule (comme MACRO et ACID elle ajoute une
    machine : jamais avec elles, ni avec les moteurs du Syntakt, ni avec Model-TG).

SHAPE choisit le modèle (0..9) ; COLOR et SWEEP sont les deux macros du modèle, CONTOUR l'enveloppe de coup
(ou un troisième réglage pour BNJ, CEL et RNG), PUNCH = FREE, DECAY et GATE : la chaîne d'ampli d'origine.

Le son est notre code (tools/machines/tiny2/ : tiny2_dsp.h, le cœur, et tiny2.c, la passerelle), écrit en virgule
fixe, sans FPU. Ses tables (tiny2_tables.h) sont calculées ici. Le tweak ne porte, de l'OS, que les courts octets
d'origine (« old ») qui vérifient le fichier officiel ; la table des descripteurs est recopiée au build depuis TON
fichier (recette « cycles », comme pour MACRO et ACID).

La mécanique est celle de MACRO et d'ACID (gen_macro.added_machine, notes/43 et 54) : mêmes détours, mêmes tables
déplacées, même place dans la charge utile.

    python3 tools/gen_tiny2.py --compile-only          # compile et mesure la taille (sans l'OS)
    python3 tools/gen_tiny2.py --cycles model-cycles_OS1.13.syx [--check]

Les JSON versionnés sont compilés par m68k-linux-gnu-gcc 13.3 (Ubuntu 24.04) : un autre GCC donne d'autres octets,
et --check le dit (tiny2_tables.h, lui, ne dépend pas du compilateur).
"""
import argparse
import json
import math
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "emu"))

import tiny2_tables as tt            # noqa: E402  (les tables : tools/tiny2_tables.py)
import feral_screens as ui            # noqa: E402  (les images de la page MACHINES)

DEV = HERE.parent / "tweaks" / "model-cycles_OS1.13"
OUT = DEV / "63-feral9.json"
SRC = HERE / "machines" / "feral"
TABLES = SRC / "tiny2_tables.h"
SOURCES = ("tiny2.c", "tiny2_dsp.h", "tiny2_eng_a.h", "tiny2_eng_b.h", "tiny2_eng_c.h", "tiny2_eng_d.h",
           "tiny2_eng_e.h")
ICON_HOOKS = ("feral_bm_a", "feral_bm_b", "feral_bm_c")

CFLAGS = ["-mcpu=54418", "-O2", "-malign-int", "-U_FORTIFY_SOURCE", "-ffreestanding", "-fno-builtin",
          "-fno-tree-loop-distribute-patterns", "-nostdlib", "-fno-pic", "-fno-common", "-ffunction-sections",
          "-fdata-sections", "-fomit-frame-pointer", "-fwrapv", "-Wall", "-Wextra", "-Werror"]
LINK = """SECTIONS
{{
  .text {code:#x} : {{ *(.text.tiny2_update) *(.text.tiny2_render) *(.text*) }}
  .rodata ALIGN(4) : {{ *(.rodata*) }}
  .data ALIGN(4) : {{ *(.data*) }}
  .bss {bss:#x} (NOLOAD) : {{ *(.bss*) *(COMMON) }}
  /DISCARD/ : {{ *(.comment) *(.note*) *(.eh_frame*) }}
}}
"""

# --- la machine (comme gm.MACHINE) : COLOR, SHAPE, SWEEP, CONTOUR = (nom long, nom court, défaut[, min, max]) ----
# Tout le monde à 64 au repos : le réglage d'usine de chaque modèle y est son meilleur son (notes/58 §3).
MACHINE = dict(name="Feral", image=ui.IMAGE, decay=50, lofi=True,
               knobs=(("Color", "COLR", 64), ("Model", "MODL", 0, 0, len(tt.SHAPE_NAMES) - 1), ("Sweep", "SWP", 64),
                      ("Contour", "CNT", 64)))


def tables_header():
    return tt.header()


# --- UI : les noms des 10 modeles dans la fenetre de valeur de SHAPE ----------------------------------------------
# L'objet d'interface du descripteur SHAPE est, comme ceux des machines ajoutees, celui de SNARE (etat 52). On lui
# donne un objet propre (dans les detours) : copie de celui de SNARE au premier usage, puis texte et dessin a nous.
# Le reste de l'OS ne change pas : SNARE garde son objet, et les autres descripteurs leurs leurs.
def tiny2_detours(text, model_desc):
    """Detours de gs.detours_asm, avec state_at/state_connect qui donnent a SHAPE son objet d'interface propre, et
    le texte/dessin des noms (trois caracteres, MAJUSCULES : la grande police n'a pas de minuscules)."""
    if any(len(n) != 3 for n in tt.SHAPE_NAMES):
        raise SystemExit("!! les noms affiches par SHAPE doivent faire trois caracteres")
    names = "".join(f'\ttiny2_n{m}: .asciz "{n}"\n' for m, n in enumerate(tt.SHAPE_NAMES))
    a = text
    at0 = "\t.globl\tstate_at\n"
    at1 = "\t.globl\tstate_connect\n"
    co1 = "\t.globl\tcc_bounds\n"
    i, j = a.find(at0), a.find(at1, a.find(at0))
    k = a.find(co1, a.find(at1))
    if not 0 <= i < j < k:
        raise SystemExit("!! gs.detours_asm n'a plus la forme attendue (state_at, state_connect, cc_bounds)")
    state_at = f"""{at0}state_at:
\tmove.l\t4(%sp), %d0
\tcmpi.l\t#{model_desc}, %d0
\tbeq.w\ttiny2_model_state
\tbsr.w\tmap_state
\tmoveq\t#100, %d1
\tmuls.l\t%d1, %d0
\tadd.l\t#0x40a71754, %d0
\trts
tiny2_model_state:
\tlea\ttiny2_model_ui, %a0
\ttst.l\ttiny2_model_ui_ready
\tbne.s\t2f
\tlea\t0x40a71754+{100 * 52}, %a1
\tmoveq\t#24, %d1
1:\tmove.l\t(%a1)+, (%a0)+
\tsubq.l\t#1, %d1
\tbpl.s\t1b
\tlea\ttiny2_model_ui, %a0
\tmove.l\t#tiny2_model_fmt, %d1
\tmove.l\t%d1, 0x20(%a0)
\tmove.l\t#tiny2_model_draw, %d1
\tmove.l\t%d1, 0x30(%a0)
\tmoveq\t#1, %d1
\tmove.l\t%d1, tiny2_model_ui_ready
2:\tmove.l\t%a0, %d0
\trts
"""
    state_connect = f"""{at1}state_connect:
\tmove.l\t4(%sp), %d0
\tcmpi.l\t#{model_desc}, %d0
\tbeq.s\ttiny2_model_connect
\tbsr.w\tmap_state
\tmoveq\t#100, %d1
\tmuls.l\t%d1, %d0
\tadd.l\t#0x40a71768, %d0
tiny2_connect_common:
\tpea\t0x40a71500
\tmove.l\t12(%sp), -(%sp)
\tmove.l\t%d0, -(%sp)
\tjsr\t0x400ddf60
\tlea\t12(%sp), %sp
\tmove.l\t#0x40a71500, %d0
\trts
tiny2_model_connect:
\tmove.l\t#{model_desc}, -(%sp)
\tbsr.w\tstate_at
\taddq.l\t#4, %sp
\tadd.l\t#0x14, %d0
\tbra.s\ttiny2_connect_common
"""
    ui = f"""
tiny2_model_fmt:
\tmove.l\t8(%sp), %d0
\taddi.l\t#0x80, %d0
\tasr.l\t#8, %d0
\tbpl.s\t1f
\tmoveq\t#0, %d0
1:\tcmpi.l\t#{len(tt.SHAPE_NAMES) - 1}, %d0
\tble.s\t2f
\tmoveq\t#{len(tt.SHAPE_NAMES) - 1}, %d0
2:\tlsl.l\t#2, %d0
\tlea\ttiny2_model_names, %a0
\tadda.l\t%d0, %a0
\tmove.l\t%a0, -(%sp)
\tpea\ttiny2_s_s
\tmove.l\t20(%sp), -(%sp)
\tjsr\t0x40000e6e
\tlea\t12(%sp), %sp
\trts
tiny2_model_draw:
\tlea\t-24(%sp), %sp
\tmove.l\t%sp, %d0
\tmove.l\t%d0, -(%sp)
\tmove.l\t36(%sp), -(%sp)
\tclr.l\t-(%sp)
\tbsr.w\ttiny2_model_fmt
\tlea\t12(%sp), %sp
\tpea\t0x401429ec
\tpea\t20(%sp)
\tjsr\t0x40072260
\taddq.l\t#8, %sp
\tmove.l\t%sp, %d0
\tmove.l\t%d0, -(%sp)
\tpea\t0x40124b58
\tpea\t2
\tmove.l\t56(%sp), -(%sp)
\tmove.l\t56(%sp), -(%sp)
\tpea\t36(%sp)
\tmove.l\t60(%sp), -(%sp)
\tjsr\t0x40071a04
\tlea\t28(%sp), %sp
\tpea\t16(%sp)
\tjsr\t0x40072080
\tlea\t28(%sp), %sp
\trts
tiny2_s_s:\t.asciz\t"%s"
\t.balign\t2
\t.balign\t4
tiny2_model_names:
{names}\t.balign\t4
tiny2_model_ui:\t.space\t100
tiny2_model_ui_ready:\t.space\t4
"""
    return a[:i] + state_at + state_connect + a[k:] + ui


def import_machine_tools():
    """Les outils du dépôt qui demandent l'OS officiel ou la chaîne m68k (importés à la demande : --tables n'en a pas
    besoin)."""
    global gm, gms, gx, g7, gs, usb_steady, voice_loop
    import gen_macro as gm                  # noqa: F401
    import gen_macro_syntakt as gms         # noqa: F401
    import gen_sdvintage_exact as gx        # noqa: F401
    import gen_sdvintage_7th as g7          # noqa: F401
    import gen_syntakt_engines as gs        # noqa: F401
    import usb_steady                       # noqa: F401
    import voice_loop                       # noqa: F401


def compile_machine(tmp, pay, tables_h, icons_h=None, bss_at=None, code_end=None, defs=(), cflags=()):
    """La passerelle et le cœur de Feral liés à pay (code, tables) et bss_at (variables ; pay + BSS_OFF par défaut).
    Le code et les tables doivent finir avant code_end (gs.STUBS par défaut). defs : -D en plus ; cflags : options en
    plus (-g pour le profil, tiny2_profile.py ; le tmp garde alors tiny2.elf). Renvoie (octets, symboles, fin du BSS)."""
    (tmp / "tiny2_tables.h").write_text(tables_h)         # les tables de ce générateur, pas celles du dépôt
    if icons_h is not None:
        (tmp / "feral_icons.h").write_text(icons_h)
    for f in SOURCES:
        (tmp / f).write_bytes((SRC / f).read_bytes())
    bss_at = pay + gm.BSS_OFF if bss_at is None else bss_at
    code_end = gs.STUBS if code_end is None else code_end
    o = tmp / "tiny2.o"
    gx.run([gx.CROSS + "gcc", *CFLAGS, *cflags, *(f"-D{d}" for d in defs), f"-I{tmp}", "-c", str(tmp / "tiny2.c"), "-o", str(o)])
    ld, elf, out = tmp / "link.ld", tmp / "tiny2.elf", tmp / "tiny2.bin"
    ld.write_text(LINK.format(code=pay, bss=bss_at))
    gx.run([gx.CROSS + "ld", "-T", str(ld), "--gc-sections", "--no-warn-rwx-segments", "-e", "tiny2_update",
            "-u", "tiny2_render", *(a for k in ICON_HOOKS for a in ("-u", k)), "-o", str(elf), str(o)])
    secs = {}
    for line in gx.run([gx.CROSS + "objdump", "-h", str(elf)]).splitlines():
        f = line.split()
        if len(f) > 4 and f[0].isdigit():
            secs[f[1]] = (int(f[3], 16), int(f[2], 16))
    if {k for k in secs if not k.startswith(".debug")} - {".text", ".rodata", ".data", ".bss"}:
        raise SystemExit(f"!! sections inattendues : {sorted(secs)}")
    if secs.get(".data", (0, 0))[1]:
        raise SystemExit("!! variables initialisées : le crochet de démarrage ne les recopierait pas à part")
    gx.run([gx.CROSS + "objcopy", "-O", "binary", "-R", ".bss", str(elf), str(out)])
    blob = out.read_bytes()
    syms = {p[2]: int(p[0], 16) for p in (l.split() for l in gx.run([gx.CROSS + "nm", str(elf)]).splitlines())
            if len(p) == 3}
    if pay + len(blob) > code_end:
        raise SystemExit(f"!! code trop grand : {len(blob)} o")
    bss = secs.get(".bss", (bss_at, 0))
    if bss[0] != bss_at:
        raise SystemExit("!! BSS")
    return blob, syms, (bss[0] + bss[1] + 3) & ~3


def other_ids():
    """Tweaks qui ajoutent des machines, ou le même bloc après l'image : jamais avec Feral."""
    ids = gm.other_ids() | {"macro", "macro-tg", "acid", "acid-tg", "model-tg", "model-tg-st",
                            "6ch-usbup", "6ch-multiout"}
    for codes in gs.subsets():
        ids |= {gms.tweak_id(codes), gms.tweak_id(codes, tg=True)}
    # model27: every tweak that appends a payload shares Feral's window and boot hook.
    for f in sorted(DEV.glob("*.json")):
        if f.name == "device.json":
            continue
        t = json.loads(f.read_text(encoding="utf-8"))
        if t.get("append") and t.get("id"):
            ids.add(t["id"])
    return ids


# FINE sous FUNC + PITCH : le texte de la valeur. Celui de MACRO dit « OFF », des kHz et des bits (son FINE est la
# réduction de fréquence et de résolution) ; celui de TINY2 dit le potard, 0..127 (64 : juste ; BENJ : 127 = filtre
# ouvert). Le pas d'un tour de potard (lofi_step) et le dessin (lofi_draw) sont ceux de MACRO, tels quels.
LOFI_FMT = """lofi_fmt:
	move.l	8(%sp), %d0
	addi.l	#0x80, %d0
	asr.l	#8, %d0
	bpl.s	1f
	moveq	#0, %d0
1:	moveq	#127, %d1
	cmp.l	%d1, %d0
	ble.s	2f
	move.l	%d1, %d0
2:	move.l	%d0, -(%sp)
	pea	lofi_s_d
	move.l	20(%sp), -(%sp)
	jsr	0x40000e6e
	lea	12(%sp), %sp
	rts
"""
LOFI_TAIL = """lofi_s_d:	.asciz	"%d"
	.balign	2
"""


def lofi_asm_tiny2(orig):
    """Le texte assembleur de MACRO (gs.lofi_asm), avec lofi_fmt et ses chaînes remplacés."""
    text = orig()
    a, b, c = text.find("lofi_fmt:\n"), text.find("lofi_draw:\n"), text.find("lofi_s_k:")
    if not 0 < a < b < c:
        raise SystemExit("!! gs.lofi_asm n'a plus la forme attendue (lofi_fmt, lofi_draw, chaînes)")
    return text[:a] + LOFI_FMT + text[b:c] + LOFI_TAIL


def build_tweak(img):
    """Tweak de la machine Feral (seule : pas de version avec Model-TG)."""
    pay = gs.PAY_ALONE
    gs.set_base(pay)
    orig = gs.lofi_asm
    orig_det = gs.detours_asm

    def det(*a, **k):
        firsts = a[2] if len(a) > 2 else k["firsts"]
        return ui.patch_detours(tiny2_detours(orig_det(*a, **k), firsts[0] + 1), syms)

    gs.lofi_asm = lambda: lofi_asm_tiny2(orig)          # le texte de FINE de Feral, le temps de la construction
    gs.detours_asm = det                                 # SHAPE affiche le nom du modele
    ssyms = {}
    assemble = gm.assemble

    def assemble_keeping_symbols(tmp_, name, src, at, defs=()):
        blob_, syms_ = assemble(tmp_, name, src, at, defs)
        if name == "det":
            ssyms.update(syms_)
        return blob_, syms_

    try:
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            blob, syms, bss_end = compile_machine(tmp, pay, tables_header(), ui.icons_header())
            gm.assemble = assemble_keeping_symbols
            writes, append = gm.added_machine(img, None, [dict(MACHINE, update=syms["tiny2_update"],
                                                               render=syms["tiny2_render"])], tmp, [(pay, blob)],
                                              bss_end)
        ui.clamp_writes(writes, gm.BASE)
        writes += ui.site_writes(img, gm.BASE, ssyms)
    finally:
        gm.assemble = assemble
        gs.lofi_asm = orig
        gs.detours_asm = orig_det
    tid = "feral9"
    ids = other_ids() | {"feral9"}
    out = {
        "id": tid,
        "order": 27,
        "name": "Machine Feral : 9 moteurs de synthèse bruités et imprévisibles, légers pour le processeur",
        "description": [
            "Machine Feral en 7e machine, après les 6 d'origine (notes/58). SHAPE choisit le modèle (0..8) :",
            "NYB, GND, BNJ, RYT, FRS, RNG, PLS, SCN, KOS.",
            "COLOR et SWEEP : les deux macros du modèle (la fenêtre de valeur nomme le vrai réglage de chaque",
            "modèle) ; CONTOUR : enveloppe de coup, sauf BNJ, CEL et RNG ; PUNCH : FREE (le moteur continue entre",
            "les trigs) ; FUNC + PITCH : réglage fin (BNJ : coupure de son filtre) ; DECAY et GATE : la chaîne d'ampli",
            "d'origine, réglée comme TONE. Une voix muette n'est pas calculée.",
            "Généré par tools/gen_feral.py. De l'OS, seuls les octets d'origine (old) qui vérifient le fichier",
            "officiel ; la table des descripteurs est recopiée au build (recette cycles).",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
        "status": "experimental",
    }
    out.update({"conflicts": sorted(ids - {tid}), "writes": writes, "append": append})
    # pour la preuve (tools/emu/test_tiny2_os.py) : les entrées de la passerelle et ses voix
    out["symbols"] = {k: f"{syms[k]:#x}" for k in ("tiny2_update", "tiny2_render", "trk")}
    out = usb_steady.add_to(out)          # envoi à l'USB à heure fixe (notes/35), boucle des voix (notes/36) :
    out = voice_loop.add_to(out)          # la charge varie avec les voix muettes, comme pour MACRO et ACID seules
    segs = sum(n for _, n in append["pack"])
    return out, dict(code=len(blob), bss=bss_end - pay - gm.BSS_OFF, image=segs, syms=syms)


def emit(path, text, check):
    """Écrit le fichier, ou avec check le compare à celui du dépôt. Renvoie 1 s'il diffère."""
    if check:
        if not path.exists() or path.read_text() != text:
            print(f"  {path.name} : ne correspond pas")
            return 1
        print(f"  {path.name} : ok")
        return 0
    path.write_text(text)
    print(f"  {path.name} : écrit")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", help="model-cycles_OS1.13.syx officiel (sans lui : tiny2_tables.h seulement)")
    ap.add_argument("--check", action="store_true", help="vérifie que les fichiers versionnés correspondent")
    ap.add_argument("--compile-only", action="store_true",
                    help="compile la machine pour le ColdFire à l'adresse de la charge utile et donne sa taille")
    args = ap.parse_args()
    bad = emit(TABLES, tables_header(), args.check)
    if args.compile_only:
        import_machine_tools()
        with tempfile.TemporaryDirectory() as d:
            blob, syms, bss_end = compile_machine(pathlib.Path(d), gs.PAY_ALONE, tables_header(), ui.icons_header())
        print(f"  code et tables {len(blob)} o, variables {bss_end - gs.PAY_ALONE - gm.BSS_OFF} o")
        for k in ("tiny2_update", "tiny2_render", "trk"):
            print(f"  {k} = {syms[k]:#x}")
    if args.cycles:
        import_machine_tools()
        img = g7.cycles_main(args.cycles)
        if len(img) != gx.IMAGE_LEN:
            raise SystemExit("!! ce n'est pas le MAIN OS 1.13 officiel")
        tweak, info = build_tweak(img)
        text = json.dumps(tweak, indent=1) + "\n"
        print(f"  {tweak['id']} : {len(tweak['writes'])} écritures, code et tables {info['code']} o, variables "
              f"{info['bss']} o, ajout à l'image {info['image']} o")
        bad += emit(OUT, text, args.check)
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
