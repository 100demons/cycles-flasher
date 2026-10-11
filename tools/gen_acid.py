#!/usr/bin/env python3
"""Génère les tweaks de la machine ACID : une basse acide à la manière de la TB-303, en machine ajoutée du
Model:Cycles (notes/54).

  - 26-acid.json : 7e machine, après les 6 d'origine ;
  - 35-acid-tg.json : avec Model-TG, 8e machine après son Sampler ; s'ajoute après model-tg-st (notes/31).

Le son est notre code (tools/machines/acid/ : acid_dsp.h, le cœur, et acid.c, la passerelle), écrit en virgule
fixe d'après le modèle d'Open303 de Robin Schmidt (licence MIT : LICENSE-Open303, recopiée à côté du flasher) :
filtre « TB_303 », enveloppe du filtre, slide ; puis une saturation (DRIVE) qui est la nôtre. Ses tables
(acid_tables.h) sont calculées ici. Le tweak ne porte, de l'OS, que les courts octets d'origine (« old ») qui
vérifient le fichier officiel ; la table des descripteurs est recopiée au build depuis TON fichier (recette
« cycles », comme pour MACRO).

La mécanique est celle de MACRO (gen_macro.added_machine, notes/43) : mêmes détours, mêmes tables déplacées, même
place dans la charge utile. Avec MACRO et les moteurs du Syntakt : tools/gen_acid_combos.py (notes/54 §11), qui
reprend compile_machine à une autre place.

    python3 tools/gen_acid.py --cycles model-cycles_OS1.13.syx [--check]

Les JSON versionnés sont compilés par m68k-linux-gnu-gcc 13.3 (Ubuntu 24.04) : un autre GCC donne d'autres octets,
et --check le dit (acid_tables.h et LICENSE-Open303, eux, ne dépendent pas du compilateur).
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

import gen_macro as gm             # noqa: E402
import gen_macro_syntakt as gms    # noqa: E402
import gen_sdvintage_exact as gx   # noqa: E402
import gen_sdvintage_7th as g7     # noqa: E402
import gen_syntakt_engines as gs   # noqa: E402
import usb_steady                  # noqa: E402
import voice_loop                  # noqa: E402

DEV = HERE.parent / "tweaks" / "model-cycles_OS1.13"
OUT = DEV / "26-acid.json"
OUT_TG = DEV / "35-acid-tg.json"
LICENSE_OUT = DEV / "LICENSE-Open303"
SRC = HERE / "machines" / "acid"
TABLES = SRC / "acid_tables.h"

CFLAGS = ["-mcpu=54418", "-O2", "-malign-int", "-U_FORTIFY_SOURCE", "-ffreestanding", "-fno-builtin",
          "-fno-tree-loop-distribute-patterns", "-nostdlib", "-fno-pic", "-fno-common", "-ffunction-sections",
          "-fdata-sections", "-fomit-frame-pointer", "-Wall", "-Wextra", "-Werror"]
LINK = """SECTIONS
{{
  .text {code:#x} : {{ *(.text.acid_update) *(.text.acid_render) *(.text*) }}
  .rodata ALIGN(4) : {{ *(.rodata*) }}
  .data ALIGN(4) : {{ *(.data*) }}
  .bss {bss:#x} (NOLOAD) : {{ *(.bss*) *(COMMON) }}
  /DISCARD/ : {{ *(.comment) *(.note*) *(.eh_frame*) }}
}}
"""
BSS_OFF = gm.BSS_OFF               # comme MACRO : variables au-dessus des tables déplacées (gs.LAYOUT)

# --- la machine (comme gm.MACHINE) : COLOR, SHAPE, SWEEP, CONTOUR = (nom long, nom court, défaut) ; decay : DECAY
MACHINE = dict(name="ACID", image=4, decay=50,
               knobs=(("Cutoff", "CUT", 40), ("Reso", "RES", 90), ("Env Mod", "ENV", 80), ("Drive", "DRV", 0)))

# --- le modèle d'Open303 (rosic_Open303.cpp, rosic_TeeBeeFilter.h), à 48 kHz ---------------------------------
OPEN303 = "RobinSchmidt/Open303"
OPEN303_COMMIT = "313bf0d9ade7c1dcb6b3a74f5ea1780a29d70074"    # 29/03/2024
FS = 48000.0
BLK = 32                           # trames par bloc de la boucle des voix
NCUT = 103                         # table des coefficients : 200 Hz x 2^(i/16), i = 0..102 (16,6 kHz)
F0 = 200.0                         # plancher de la fréquence de coupure d'Open303
C0, C1 = 313.8152786059267, 2394.411986817546      # CUTOFF au minimum, au maximum (mesures d'Open303)
DECAY_MS = (200.0, 2000.0)         # DECAY : décroissance de l'enveloppe du filtre
SLIDE_TAU = 0.0217                 # slide : 90 % de l'écart en 50 ms
DUTY = (1 - 4.37 / 70.0) / 2       # SQUARE303 = -tanh(70 x scie + 4,37) : haut sur 46,9 % du cycle
# niveau de sortie : 1,0 du modèle (sortie du filtre d'Open303 pour une scie de +-0,125) = 4 x pleine échelle, avant
# la saturation. Réglages résonants (~0,1 du modèle) : ~0,4 de la pleine échelle (notes/54).
OUT_LEVEL = 4.0
X_FS = 18                          # qmul(g, y4) = modèle x 2^20 x OUT_GAIN : pleine échelle = 2^18
OUT_GAIN = OUT_LEVEL * 2 ** X_FS / 2 ** 20
# saturation (DRIVE, potard CONTOUR, notes/54 §3.2) : gain 1 .. DRIVE_GAIN dB, plus vite au début de la course,
# courbe u - u^3 / 3 dont le seuil (u = 1) est à 1,5 x pleine échelle / gain (la sortie y vaut 2/3 x 1,5 = la
# pleine échelle), passe-bas d'un pôle, de « pas de filtre » (DRIVE à 0) à DRIVE_LP Hz (DRIVE au maximum). Le
# niveau compense le gain que le son reçoit vraiment : tout le gain tant qu'il reste sous le seuil, plus rien
# au-delà (une note typique a DRIVE_HEADROOM dB de marge avant le seuil, DRIVE à 0), et laisse monter le niveau
# efficace d'une scie de DRIVE_RISE dB d'un bout à l'autre (mesuré : notes/54 §3.2)
DRIVE_GAIN = 30.0
DRIVE_LP = 6000.0
DRIVE_HEADROOM = 15.0
DRIVE_RISE = 1.5


def q31(x):
    v = int(round(x * 2 ** 31))
    return max(-2 ** 31, min(2 ** 31 - 1, v))


def kfull(fx):
    """Open303, TB_303 : k (résonance à 100 %) pour fx = fc / fs / sqrt(2)."""
    return fx * (fx * (fx * (fx * (fx * (fx + 7198.6997) - 5837.7917) - 476.47308) + 614.95611) + 213.87126) + 16.998792


def b0f(fx):
    """Open303, TB_303 : coefficient b0 des 4 étages."""
    return (0.00045522346 + 6.1922189 * fx) / (1.0 + 12.358354 * fx + 4.4156345 * fx * fx)


def drive_gain(d):
    """Gain de la saturation pour le potard d (0..1) : 1 .. DRIVE_GAIN dB, en DRIVE_GAIN x (1 - (1 - d)^1,25) dB
    (le premier quart de la course donne déjà près du tiers du gain : le son change dès le début)."""
    return 10 ** (DRIVE_GAIN * (1 - (1 - d) ** 1.25) / 20)


def drive_level(d):
    """Niveau après la saturation (1 à DRIVE 0) : l'inverse du gain reçu, qui plafonne à DRIVE_HEADROOM dB."""
    g, c = drive_gain(d), 10 ** (DRIVE_HEADROOM / 20)
    return math.sqrt(1 + (g / c) ** 2) / g * 10 ** (DRIVE_RISE * d / 20)


def tables():
    """(tableaux, constantes) d'acid_tables.h."""
    lut = lambda f: [f(j / 16) for j in range(17)]        # 17 points sur la course d'un potard
    fx = [F0 * 2 ** (i / 16) / FS / math.sqrt(2) for i in range(NCUT)]
    t = {
        "ACID_B0": [q31(b0f(x)) for x in fx],
        "ACID_KF": [q31(kfull(x) / 128) for x in fx],
        "ACID_INC": [int(round(2 ** 32 * 440 * 2 ** ((n - 69) / 12) / FS)) for n in range(129)],
        "ACID_RES": lut(lambda x: q31((1 - math.exp(-3 * x)) / (1 - math.exp(-3)))),
        "ACID_DEC": lut(lambda x: q31(math.exp(-BLK / (FS * DECAY_MS[0] / 1000 * (DECAY_MS[1] / DECAY_MS[0]) ** x)))),
        "ACID_ENVLO": lut(lambda e: int(round((3.773996325111173 * e + 0.736965594166206) * 2 ** 20))),
        "ACID_ENVHI": lut(lambda e: int(round((4.194548788411135 * e + 0.864344900642434) * 2 ** 20))),
        # saturation : u = x x m (Q28, 1,0 = le seuil), passe-bas (Q31), niveau x 0,75 (z x 8 x niveau, compté
        # deux fois par qmac2 : z x 12 x niveau)
        "ACID_DRV_M": lut(lambda d: int(round(drive_gain(d) * 2 ** 28 / (1.5 * 2 ** X_FS)))),
        "ACID_DRV_LP": lut(lambda d: q31(1 - d * math.exp(-2 * math.pi * DRIVE_LP / FS))),
        "ACID_DRV_MK": lut(lambda d: q31(0.75 * drive_level(d))),
    }
    k = {
        "ACID_NCUT": NCUT,
        "ACID_EOFF0": q31(0.294391201442418), "ACID_EOFFSPAN": q31(0.048292930943553),
        "ACID_LC0": int(round(16 * math.log2(C0 / F0) * 2 ** 16)),
        "ACID_LCSPAN": int(round(16 * math.log2(C1 / C0) * 2 ** 16)),
        "ACID_K17": q31(128 / (17 * 8)),
        "ACID_AMP_ENV": q31(0.45 / 8 * OUT_GAIN), "ACID_AMP_ONE": q31(1 / 8 * OUT_GAIN),
        "ACID_SLIDE_A": q31(1 - math.exp(-BLK / (FS * SLIDE_TAU))),
        "ACID_DUTY": int(round(DUTY * 2 ** 32)),
        "ACID_SAT": 2 ** 29 // 3,                      # 2/3 en Q28 : le haut de la courbe
    }
    for name, fc in (("HP1", 44.486), ("HPF", 150.0)):     # passe-haut d'entrée, passe-haut de la contre-réaction
        x = math.exp(-2 * math.pi * fc / FS)
        k[f"ACID_{name}_B"] = q31(0.5 * (1 + x))
        k[f"ACID_{name}_A"] = q31(x)
    return t, k


def tables_header():
    t, k = tables()
    out = ["/* Tables d'ACID, calculees par tools/gen_acid.py (modele d'Open303, 48 kHz) : ne pas modifier a la main. */",
           "#ifndef ACID_TABLES_H", "#define ACID_TABLES_H", ""]
    for name, v in k.items():
        out.append(f"#define {name} {v:#x}u" if name == "ACID_DUTY" else f"#define {name} ({v})")
    out.append("")
    for name, v in t.items():
        typ = "u32" if name == "ACID_INC" else "s32"
        out.append(f"static const {typ} {name}[{len(v)}] = {{")
        for i in range(0, len(v), 6):
            out.append("\t" + ", ".join(f"{x:#010x}" if typ == "u32" else str(x) for x in v[i:i + 6]) + ",")
        out.append("};")
    return "\n".join(out + ["", "#endif", ""])


LICENSE = """Machine ACID of Modded-Cycles: fixed-point code written after the model of Open303 by Robin Schmidt
(https://github.com/{repo}, commit {commit}: its TB_303 filter, filter envelope and slide, with their
measured constants), under the MIT license:

The MIT License

Copyright (c) 2009 Robin Schmidt (www.rs-met.com)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
""".format(repo=OPEN303, commit=OPEN303_COMMIT[:7])


def compile_machine(tmp, pay, tables_h, bss_at=None, code_end=None, defs=()):
    """La passerelle et le cœur d'ACID liés à pay (code, tables) et bss_at (variables ; pay + BSS_OFF par défaut).
    Le code et les tables doivent finir avant code_end (gs.STUBS par défaut). defs : options -D du compilateur
    (GOV_SKIP avec les moteurs du Syntakt, gen_acid_combos.py). Renvoie (octets, symboles, fin du BSS)."""
    (tmp / "acid_tables.h").write_text(tables_h)          # les tables de ce générateur, pas celles du dépôt
    for f in ("acid.c", "acid_dsp.h"):
        (tmp / f).write_bytes((SRC / f).read_bytes())
    bss_at = pay + BSS_OFF if bss_at is None else bss_at
    code_end = gs.STUBS if code_end is None else code_end
    o = tmp / "acid.o"
    gx.run([gx.CROSS + "gcc", *CFLAGS, *(f"-D{d}" for d in defs), f"-I{tmp}", "-c", str(tmp / "acid.c"), "-o", str(o)])
    ld, elf, out = tmp / "link.ld", tmp / "acid.elf", tmp / "acid.bin"
    ld.write_text(LINK.format(code=pay, bss=bss_at))
    gx.run([gx.CROSS + "ld", "-T", str(ld), "--gc-sections", "--no-warn-rwx-segments", "-e", "acid_update",
            "-u", "acid_render", "-o", str(elf), str(o)])
    secs = {}
    for line in gx.run([gx.CROSS + "objdump", "-h", str(elf)]).splitlines():
        f = line.split()
        if len(f) > 4 and f[0].isdigit():
            secs[f[1]] = (int(f[3], 16), int(f[2], 16))
    if set(secs) - {".text", ".rodata", ".data", ".bss"}:
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
    """Tweaks qui ajoutent des machines, ou le même bloc après l'image : jamais avec ACID."""
    ids = gm.other_ids() | {"macro", "macro-tg"}
    for codes in gs.subsets():
        ids |= {gms.tweak_id(codes), gms.tweak_id(codes, tg=True)}
    return ids


def build_tweak(img, tg=None):
    """Tweak de la machine ACID. tg : Model-TG (gs.tg_context) pour la version combinée."""
    pay = gs.PAY_TG if tg else gs.PAY_ALONE
    gs.set_base(pay)
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        blob, syms, bss_end = compile_machine(tmp, pay, tables_header())
        writes, append = gm.added_machine(img, tg, [dict(MACHINE, update=syms["acid_update"],
                                                         render=syms["acid_render"])], tmp, [(pay, blob)], bss_end)
    tid = "acid-tg" if tg else "acid"
    ids = other_ids() | {"acid", "acid-tg", "model-tg"} | (set() if tg else {"model-tg-st"})
    out = {
        "id": tid,
        "order": 35 if tg else 26,
        "name": ("Model-TG + " if tg else "") + "Machine ACID : une basse acide à la manière de la TB-303",
        "description": ([
            "Version combinée avec Model-TG (notes/31, notes/54) : s'ajoute après model-tg-st, le Sampler reste la",
            "7e machine, ACID est la 8e. Sa sortie passe par l'étage d'amplitude de Model-TG (Attack, filtre).",
        ] if tg else [
            "Machine ACID en 7e machine, après les 6 d'origine (notes/54).",
        ]) + [
            "COLOR = CUTOFF, SHAPE = RESONANCE, SWEEP = ENV MOD, CONTOUR = DRIVE (saturation), DECAY = décroissance",
            "du filtre (et de l'ampli), PUNCH = forme d'onde (scie / carré). Filtre « TB_303 », enveloppe et slide",
            "d'Open303 (Robin Schmidt, MIT : LICENSE-Open303), réécrits en virgule fixe (tools/machines/acid/).",
            "Une voix muette n'est pas calculée. Généré par tools/gen_acid.py. De l'OS, seuls les octets d'origine (old)",
            "qui vérifient le fichier officiel ; la table des descripteurs est recopiée au build (recette cycles).",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
    }
    if tg:
        out["requires"] = [tg["id"]]
    out.update({"conflicts": sorted(ids - {tid}), "writes": writes, "append": append})
    # pour la preuve (tools/emu/test_acid.py) : les entrées de la passerelle et ses voix
    out["symbols"] = {k: f"{syms[k]:#x}" for k in ("acid_update", "acid_render", "trk")}
    if not tg:                    # comme MACRO seule : envoi à l'USB à heure fixe (notes/35), boucle des voix
        out = usb_steady.add_to(out)          # (notes/36) ; la version combinée les a par model-tg-st
        out = voice_loop.add_to(out)
    segs = sum(n for _, n in append["pack"])
    return out, dict(code=len(blob), bss=bss_end - pay - BSS_OFF, image=segs, syms=syms)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", help="model-cycles_OS1.13.syx officiel (sans lui : acid_tables.h et la licence)")
    ap.add_argument("--check", action="store_true", help="vérifie que les fichiers versionnés correspondent")
    args = ap.parse_args()
    bad = gm.emit(TABLES, tables_header(), args.check)
    bad += gm.emit(LICENSE_OUT, LICENSE, args.check)
    if args.cycles:
        img = g7.cycles_main(args.cycles)
        if len(img) != gx.IMAGE_LEN:
            raise SystemExit("!! ce n'est pas le MAIN OS 1.13 officiel")
        for path, tg in ((OUT, None), (OUT_TG, gs.tg_context(img))):
            tweak, info = build_tweak(img, tg)
            text = json.dumps(tweak, indent=1) + "\n"
            print(f"  {tweak['id']} : {len(tweak['writes'])} écritures, code et tables {info['code']} o, variables "
                  f"{info['bss']} o, ajout à l'image {info['image']} o")
            bad += gm.emit(path, text, args.check)
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
