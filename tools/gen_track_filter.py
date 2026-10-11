#!/usr/bin/env python3
"""Génère tweaks/model-cycles_OS1.13/48-track-filter.json : un filtre par piste, passe-bas / OFF / passe-haut (notes/47).

Demande du Discord (forum feature-requests, « High-pass filter per track / machine ») : un passe-haut par piste, puis un
filtre bipolaire « DJ » (centre = rien, d'un côté LP, de l'autre HP). Sur la machine : MACHINES tenu + SWEEP = Filter
Cutoff (L64..OFF..H63), + CONTOUR = Filter Reso, + COLOR = Filter Env (quantité), + SHAPE = Env Decay. Quatre vrais
paramètres de toutes les machines : p-locks, LFO, vélocité, CC 74 et 71, sauvegardés avec le son et le pattern.

tools/machines/track_filter/ : track_filter.S (le filtre, appelé une fois par bloc après Volume + Dist) et tf_ui.S
(potards, affichage, sauvegarde), liés par track_filter.ld dans quinze masques de sprites 35x35 libérés
(tools/sprites.py). Les tables sont calculées ici (TABLES) et passées à l'assembleur dans tables.inc. Les accroches
sur l'OS sont HOOKS et POINTERS ; les quatre descripteurs remplacent les emplacements « Error » 1 à 4 (DESCRIPTORS).
Chaque écriture porte ses octets d'origine, vérifiés sur le MAIN OS officiel.

    python3 tools/gen_track_filter.py --cycles model-cycles_OS1.13.syx [--check]
"""
import argparse
import json
import math
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

SRC = HERE / "machines" / "track_filter"
OUT = HERE.parent / "tweaks" / "model-cycles_OS1.13" / "48-track-filter.json"
BASE = gx.BASE
FS = 48000                                             # trames par seconde
BLOCK_HZ = FS / 32                                     # blocs par seconde (le filtre lit ses réglages une fois par bloc)

# sections de track_filter.ld -> masque 35x35 libéré (280 o chacun)
CAVES = {
    ".tf_post": 0x4014ab5c, ".tf_track": 0x4014b85c, ".tf_kern": 0x4014d74c, ".tf_coef1": 0x401542f8,
    ".tf_coef2": 0x401548b4, ".tf_gtab": 0x4015b8f8, ".tf_ntab": 0x4015f50c, ".tf_ktab": 0x401601fc,
    ".tf_dtab": 0x40160864, ".tf_kst": 0x40160b6c, ".tf_cst": 0x40160e6c, ".tf_knob": 0x401625bc,
    ".tf_fmt": 0x40163fb8, ".tf_save": 0x4016616c, ".tf_load": 0x40166760,
}
# (adresse, octets d'origine, instruction, symbole, rôle)
HOOKS = (
    (0x40059852, "4eb940056f58", 0x4eb9, "tf_post",
     "fonction audio 0x4005979e : jsr 0x40056f58 (Volume + Dist) -> jsr tf_post (Volume + Dist, puis le filtre)"),
    (0x4004486c, "4eb94005a274", 0x4eb9, "tf_boot",
     "démarrage : jsr 0x4005a274 (tables des paramètres) -> jsr tf_boot (nos descripteurs dans la table active)"),
    (0x4005aecc, "4feffff448d7", 0x4ef9, "tf_load", "chargement d'un son : lea -12(sp),sp ; movem... -> jmp tf_load"),
    (0x4005afa0, "4feffff448d7", 0x4ef9, "tf_save2", "sauvegarde d'un son (version 2) -> jmp tf_save2"),
    (0x4005b054, "4feffff448d7", 0x4ef9, "tf_save1", "sauvegarde d'un son (version 1) -> jmp tf_save1"),
    (0x4005aa34, "7417b480640c", 0x4ef9, "tf_conv",
     "index du fichier des p-locks -> k (0x4005aa1a), pistes 0..5 : moveq #23,d2 ; cmp.l ; bcc.s -> jmp tf_conv"),
)
# (adresse, valeur d'origine, symbole, rôle) : pointeurs 32 bits
POINTERS = (
    (0x401005a8, 0x4001e814, "tf_knob", "vtable de ParameterPageView, slot 124 : descripteur sous un potard"),
    (0x4005b998, 0x4010ee4c, "tf_ptab", "sauvegarde des p-locks du pattern (0x4005b95c) : lea table k -> index,a5"),
    (0x4005baca, 0x4010ee4c, "tf_ptab", "mise à jour d'un p-lock (0x4005ba90) : lea table k -> index,a1"),
)
DESC, DSTRIDE = 0x4010dce0, 0x38                       # table des descripteurs (notes/14 §2.1)
AMP = 0x40129882                                       # "Amp" (groupe des paramètres communs, comme Pan)
# descripteurs 1..4 (« Error », groupe -1 : inutilisés) : (k, défaut, CC, NRPN, clé de tri, nom long, nom court)
DESCRIPTORS = (
    (28, 16384, 0x004affff, 0x94, 72, "tf_s_cut", "tf_s_freq"),   # Filter Cutoff, CC 74, NRPN 1:20 (Model:Samples)
    (29, 0, 0x0047ffff, 0x95, 73, "tf_s_res", "tf_s_reso"),       # Filter Reso, CC 71, NRPN 1:21
    (30, 16384, 0xffffffff, 0xffffffff, 74, "tf_s_env", "tf_s_fenv"),
    (31, 16384, 0xffffffff, 0xffffffff, 75, "tf_s_dec", "tf_s_fdec"),
)
CONFLICTS = ["model-tg", "model-tg-st"]                # leur filtre par piste (MACHINES + SWEEP / CONTOUR) ; notes/47 §8
SYMBOLS = ("tf_post", "tf_knob", "tf_objs", "tf_fmt_cut", "tf_boot", "tf_load", "tf_save2", "tf_save1", "tf_conv",
           "tf_ptab", "tf_kst", "tf_cst", "tf_trig")   # pour tools/emu/test_track_filter.py


def cutoff_hz(i):
    """Fréquence du filtre pour l'index i = |C - 0x4000| (LP : C ; HP : C - 0x4000), loi du Model:Samples."""
    return min(5.0 * 4400 ** (i / 16384), 20000.0)


Q_MIN, Q_MAX = 0.5, 50.0


def q_of(r):
    """Q pour Filter Reso r (0..32512) : exponentielle de Q_MIN à Q_MAX, environ 10 dB de bosse de plus par quart de
    tour. Plus forte que celle du Model:Samples (0,5 à 22, la première version), trop discrète à l'essai de Maxime
    (10/10/2026, notes/47 §5.1)."""
    return Q_MIN * (Q_MAX / Q_MIN) ** (r / 32512)


def reso_scale(i):
    """Part de la résonance gardée : rien sous 10 Hz (pas de bosse subsonique), tout à 30 Hz, moins vers 20 kHz."""
    fc = cutoff_hz(i)
    return (1 - (fc / 24000) ** 2.5) * min(max((fc - 10) / 20, 0.0), 1.0)


def decay_tau(d):
    """Constante de temps de l'enveloppe (s) pour Env Decay d (0..32512) : 5 ms à 10 s."""
    return 0.005 * 2000 ** (d / 32512)


def q31(x):
    return max(min(round(x * 2 ** 31), 0x7fffffff), -0x80000000)


TABLES = {
    "TABLE_G": [q31(math.tan(math.pi * cutoff_hz(256 * j) / FS) / 4) for j in range(65)],
    "TABLE_N": [q31(reso_scale(256 * j)) for j in range(65)],
    "TABLE_K": [q31(1 / (2 * q_of(512 * j))) for j in range(65)],
    "TABLE_D": [q31(math.exp(-1 / (BLOCK_HZ * decay_tau(512 * j)))) for j in range(65)],
}


def tables_inc():
    out = []
    for name, vals in TABLES.items():
        out.append(f".macro {name}")
        for k in range(0, len(vals), 8):
            out.append("\t.long\t" + ", ".join(f"{v & 0xffffffff:#010x}" for v in vals[k:k + 8]))
        out.append(".endm")
    return "\n".join(out) + "\n"


def compile_filter():
    """Code lié (ELF) : {section: (adresse, octets)}, symboles."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "tables.inc").write_text(tables_inc(), encoding="ascii")
        objs = []
        for src in ("track_filter.S", "tf_ui.S"):
            obj = d / (src[:-2] + ".o")
            gx.run([gx.CROSS + "gcc", "-mcpu=54418", "-Wa,-I" + str(d), "-c", str(SRC / src), "-o", str(obj)])
            objs.append(str(obj))
        elf = d / "tf.elf"
        gx.run([gx.CROSS + "ld", "-T", str(SRC / "track_filter.ld"), "--no-warn-rwx-segments", "-o", str(elf), *objs])
        syms = {}
        for line in gx.run([gx.CROSS + "nm", str(elf)]).splitlines():
            p = line.split()
            if len(p) == 3:
                syms[p[2]] = int(p[0], 16)
        heads = gx.run([gx.CROSS + "objdump", "-h", str(elf)])
        secs = {}
        for line in heads.splitlines():
            p = line.split()
            if len(p) >= 4 and p[1].startswith("."):
                secs[p[1]] = (int(p[3], 16), int(p[2], 16))
        out = {}
        for name in secs:
            if name not in CAVES and secs[name][1]:
                raise SystemExit(f"!! section {name} ({secs[name][1]} o) hors des masques prévus")
        for name in CAVES:
            b = d / (name.strip(".") + ".bin")
            gx.run([gx.CROSS + "objcopy", "-O", "binary", "-j", name, str(elf), str(b)])
            out[name] = (secs[name][0], b.read_bytes())
    return out, syms


def descriptor_rows(syms):
    rows = b""
    for k, dflt, cc, nrpn, key, long_, short in DESCRIPTORS:
        rows += struct.pack(">14I", 7, k, 0, 32512, dflt, 0, cc, nrpn, 0, 0x600, key, syms[long_], AMP, syms[short])
    return rows


def build_tweak(stock):
    secs, syms = compile_filter()
    writes = []
    used = {}
    for name, mask in CAVES.items():
        addr, code = secs[name]
        size, shared = sprites.MASKS[mask][0], sprites.MASKS[mask][3]
        if addr != mask or len(code) > size:
            raise SystemExit(f"!! {name} : {len(code)} o à {addr:#x}, place {size} o à {mask:#x}")
        if stock[mask - BASE:mask - BASE + size] != stock[shared - BASE:shared - BASE + size]:
            raise SystemExit(f"!! {name} : le masque {mask:#x} n'est pas identique au masque gardé {shared:#x}")
        writes.append({"off": addr - BASE, "old": stock[addr - BASE:addr - BASE + len(code)].hex(), "new": code.hex()})
        writes.append(sprites.redirect_write(mask))
        used[name] = len(code)
    for va, old_hex, op, sym, _ in HOOKS:
        old = bytes.fromhex(old_hex)
        if stock[va - BASE:va - BASE + len(old)] != old:
            raise SystemExit(f"!! octets d'origine inattendus en {va:#x}")
        writes.append({"off": va - BASE, "old": old_hex, "new": struct.pack(">HI", op, syms[sym]).hex()})
    for va, old_val, sym, _ in POINTERS:
        old = struct.pack(">I", old_val)
        if stock[va - BASE:va - BASE + 4] != old:
            raise SystemExit(f"!! pointeur d'origine inattendu en {va:#x}")
        writes.append({"off": va - BASE, "old": old.hex(), "new": struct.pack(">I", syms[sym]).hex()})
    lo = DESC + DSTRIDE                                 # entrées 1..4
    old = stock[lo - BASE:lo - BASE + DSTRIDE * len(DESCRIPTORS)]
    for i in range(len(DESCRIPTORS)):
        if struct.unpack_from(">i", old, DSTRIDE * i)[0] != -1:
            raise SystemExit(f"!! le descripteur {i + 1} n'est pas un emplacement libre (groupe -1)")
    writes.append({"off": lo - BASE, "old": old.hex(), "new": descriptor_rows(syms).hex()})
    writes.sort(key=lambda w: w["off"])
    total = sum(used.values())
    tweak = {
        "id": "track-filter",
        "order": 48,
        "name": "Filtre par piste : passe-bas, OFF, passe-haut",
        "description": [
            "Un filtre 2 pôles par piste, après Volume + Dist et avant le panoramique, les envois et le mixage (comme "
            "sur le Model:Samples) :",
            "MACHINES tenu + SWEEP = Filter Cutoff (L64..OFF..H63 : passe-bas à gauche, rien au centre, passe-haut à "
            "droite, 5 Hz à 20 kHz), + CONTOUR = Filter Reso (Q 0,5 à 50),",
            "+ COLOR = Filter Env (l'enveloppe, relancée à chaque note, monte ou descend la fréquence), + SHAPE = Env "
            "Decay (5 ms à 10 s).",
            "Quatre paramètres de toutes les machines (descripteurs 1 à 4, k 28 à 31) : p-locks, LFO, vélocité, CC 74 "
            "et 71 ; sauvegardés avec le son (emplacements 30, 31, 18) et le pattern.",
            "Corrige au passage les p-locks des paramètres k >= 23 dans le pattern (ils revenaient sur LFO Speed).",
            "Au centre, la piste n'est pas touchée (bit pour bit) ; environ 640 instructions par bloc et par piste "
            "filtrée (0,6 % d'un bloc).",
            f"Code, tables et état dans quinze masques de sprites 35x35 libérés (tools/sprites.py) : {total} o. "
            "Généré par tools/gen_track_filter.py, notes/47.",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
        "conflicts": CONFLICTS,
        "symbols": {n: f"{syms[n]:#x}" for n in SYMBOLS},
        "writes": writes,
    }
    return tweak, syms, used


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--check", action="store_true", help="vérifie que le JSON versionné correspond")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    if build.sha(stock) != json.loads((OUT.parent / "device.json").read_text(encoding="utf-8"))["section_sha256"]:
        raise SystemExit("!! ce n'est pas le MAIN OS 1.13 officiel")
    tweak, syms, used = build_tweak(stock)
    build.apply_writes(stock, [tweak])                # les octets d'origine collent
    text = json.dumps(tweak, indent=1) + "\n"
    print("  " + ", ".join(f"{n.strip('.')} {u} o" for n, u in used.items()))
    if args.check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"  {OUT.name} {'est à jour' if ok else 'NE CORRESPOND PAS (autre binutils ?)'}")
        raise SystemExit(0 if ok else 1)
    OUT.write_text(text, encoding="utf-8")
    print(f"  écrit : {OUT.relative_to(HERE.parent)} ({len(tweak['writes'])} écritures)")


if __name__ == "__main__":
    main()
