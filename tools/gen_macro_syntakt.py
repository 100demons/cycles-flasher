#!/usr/bin/env python3
"""Génère les tweaks « syntakt-<moteurs>-macro » : la machine MACRO (notes/43) avec les vrais moteurs du Syntakt
(notes/20), sur la même machine (notes/50). Avec Model-TG : « syntakt-tg-<moteurs>-macro », sur model-tg-st (notes/31).

Les deux mods prennent la même place (charge utile à 0x43000000, 0x46700000 avec Model-TG ; même disposition
gs.LAYOUT des tables). Ici, une seule charge utile les porte :
  - les moteurs du Syntakt restent EXACTEMENT où les met leur tweak (24-syntakt-….json, 31-syntakt-tg-….json), et leur
    passerelle est reprise octet pour octet de ce tweak versionné : compilée par m68k-elf-gcc 16.2, régulateur de
    charge en assembleur (gov_asm.py), testée sur la machine. Elle n'est pas recompilée (un autre GCC donnerait
    d'autres octets) ; ses symboles sont relus dans le tweak, et vérifiés en réassemblant ses détours à l'identique ;
  - MACRO prend la machine suivante (après le dernier moteur coché) : son code (Braids et sa passerelle, compilés
    comme pour 25-macro.json, par m68k-linux-gnu-g++ 13.3) va au-dessus des moteurs, à MACRO_AT, ses variables à
    MACRO_BSS ;
  - les tables, détours, descripteurs et bornes sont ceux de gen_syntakt_engines.py pour N + 1 machines ; le
    régulateur de charge des moteurs vaut aussi pour les pistes MACRO.
L'ensemble ne tient plus en clair sous la zone de travail du bootstrap (0x40200000), surtout avec Model-TG : la
charge utile est rangée compressée dans l'image (append.compress = "aplib", tools/aplib_grow.py pack, même
algorithme dans le flasher), et le crochet de démarrage la décompresse (stub.S, APLIB), puis appelle son 2e étage,
rangé dans la charge utile entre les moteurs et MACRO (stub.S, BOOT2) : le crochet entier ne tiendrait pas dans les
192 o que l'arpégiateur lui laisse (gs.STUB_END). Les tables d'ondes de CHORD, que les moteurs déplacent dans la charge
utile, ne sont plus recopiées depuis TON MAIN OS : le 2e étage les reprend en SRAM, où l'OS vient de les mettre, avant
d'y ranger le code du Syntakt (CHORD_AT).

    python3 tools/gen_macro_syntakt.py --cycles model-cycles_OS1.13.syx --syntakt Syntakt_OS1.42.syx \\
        --eurorack vendor/eurorack [--engines sd,cp] [--tg] [--check]

Sans --engines : toutes les combinaisons (seules et avec Model-TG, 62 fichiers). Aucun octet Elektron dans ces
fichiers.
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

import aplib_grow                  # noqa: E402
import build                       # noqa: E402
import gen_macro as gm             # noqa: E402
import gen_sdvintage_exact as gx   # noqa: E402
import gen_sdvintage_7th as g7     # noqa: E402
import gen_syntakt_engines as gs   # noqa: E402
import gov_asm                     # noqa: E402
import syntakt                     # noqa: E402

DEV = gs.DEV
BASE = gx.BASE
# Place de MACRO dans la charge utile (décalages depuis son début, PAY) : au-dessus de tout ce que les moteurs y
# mettent (lay["end"] : 0x41c00 avec les 5), le code et les tables de Braids, puis ses variables (6 voix).
MACRO_AT = 0x42000
MACRO_BSS = 0x5a000
TG_ROOM = 0x100000           # avec Model-TG : le dernier Mo de sa zone d'échantillons est à nous (notes/31 §4)
# Combinaisons testées sur un vrai Model:Cycles (seules, puis avec Model-TG). Ajouter ici après un test réussi.
HW_TESTED = set()
# 10/10/2026 : Model-TG + les 5 moteurs + MACRO, avec 6ch-usbup, sample-preview-st, trig-hold, arp, tempo-max et
# boot-anim, construit par build.py (MAIN OS f44bfad6…), après la correction du blocage au démarrage (notes/50 §8) :
# « ça marche nickel » (Maxime).
HW_TESTED_TG = {("sd", "cp", "toy", "bits", "swarm")}


def tweak_id(codes, tg=False):
    return gs.tweak_id(codes, tg=tg) + "-macro"


def versioned(codes, tg):
    """Le tweak versionné des mêmes moteurs, sans MACRO."""
    tid = gs.tweak_id(codes, tg=tg)
    return json.loads((DEV / f"{31 if tg else 24}-{tid}.json").read_text(encoding="utf-8"))


def bridge_of(tw, codes, tg, lay):
    """Passerelle du tweak versionné tw : ses octets (à DST_BRIDGE), ses fonctions en SRAM (avec Model-TG : tg, son
    contexte), la place du régulateur en assembleur (sans Model-TG), ses symboles et son champ « gov »."""
    first = gs.TG_FIRST if tg else 6
    nm = first + len(codes)
    parts = {int(p_["dest"], 16): p_ for p_ in tw["append"]["parts"] if "hex" in p_}
    if int(tw["append"]["dest"], 16) != gx.DST_CODE or tw["append"]["size"] != lay["end"] - gx.DST_CODE:
        raise SystemExit(f"!! {tw['id']} : disposition de la charge utile différente")
    hot = [(t[0], bytes.fromhex(parts[t[0]]["hex"]), None) for t in lay["tails"] if t[0] in parts]
    if bool(tg) != bool(hot):
        raise SystemExit(f"!! {tw['id']} : fonctions de la passerelle en SRAM inattendues")
    data = bytes.fromhex(parts[gs.DATA]["hex"])
    tab = lambda k, i: struct.unpack_from(">I", data, 4 * (k * nm + i))[0]     # k : 0 noms, 1 update, 2 render
    syms = {k: int(v, 16) for k, v in tw["gov"].items()}
    for i, c in enumerate(codes):
        e = gs.CATALOG[c]["engine"]
        syms[f"bridge_update_{e}"], syms[f"bridge_render_{e}"] = tab(1, first + i), tab(2, first + i)
    extra = []
    if not tg:                                  # régulateur : la décision dans la place libre (gov_asm, X_CODE)
        extra = [{"dest": f"{gx.DST_CODE + gov_asm.X_CODE:#x}", "hex": parts[gx.DST_CODE + gov_asm.X_CODE]["hex"]}]
    # les détours du tweak, réassemblés avec ces symboles : identiques (avec Model-TG, voice_done, appelé par
    # tg_after, se lit dans ses octets)
    machines = [dict(gs.CATALOG[c], code=c, index=first + i) for i, c in enumerate(codes)]
    stubs = bytes.fromhex(parts[gs.STUBS]["hex"])
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        if tg:
            probe = 0x7ffffff0
            got, _ = gs.assemble_detours(tmp, machines, dict(syms, voice_done=probe), gs.DATA + 8 * nm, tg)
            diff = [k for k in range(len(got)) if got[k] != stubs[k]] if len(got) == len(stubs) else []
            if len(diff) != 4 or diff[3] - diff[0] != 3 or got[diff[0]:diff[0] + 4] != probe.to_bytes(4, "big"):
                raise SystemExit(f"!! {tw['id']} : voice_done introuvable dans les détours")
            syms["voice_done"] = int.from_bytes(stubs[diff[0]:diff[0] + 4], "big")
        got, _ = gs.assemble_detours(tmp, machines, syms, gs.DATA + 8 * nm, tg)
    if got != stubs:
        raise SystemExit(f"!! {tw['id']} : détours réassemblés différents (symboles de la passerelle ?)")
    return dict(bridge=bytes.fromhex(parts[gs.DST_BRIDGE]["hex"]), hot=hot, syms=syms, gov=tw["gov"], extra=extra)


def build_tweak(img, st_img, repo, codes, tg=None):
    """Tweak des moteurs codes avec MACRO après eux. tg : Model-TG (gs.tg_context), avec set_base(PAY_TG)."""
    pay = gs.PAY_TG if tg else gs.PAY_ALONE
    gs.set_base(pay)
    tw = versioned(codes, bool(tg))
    an = gs.analyse(st_img, gs.generation(codes))
    lay = an["lay"]
    if lay["end"] > pay + MACRO_AT:
        raise SystemExit(f"!! moteurs jusqu'à {lay['end']:#x} : MACRO_AT trop bas")
    br = bridge_of(tw, codes, tg, lay)
    with tempfile.TemporaryDirectory() as d:
        blob, syms, bss_end = gm.compile_machine(pathlib.Path(d), repo, pay + MACRO_AT, pay + MACRO_BSS,
                                                 pay + MACRO_BSS)
    if tg and bss_end > pay + TG_ROOM:
        raise SystemExit(f"!! charge utile jusqu'à {bss_end:#x} : au-delà de la place laissée par Model-TG")
    macro = dict(gm.MACHINE, label="MACRO", update=syms["macro_update"], render=syms["macro_render"])
    # 2e étage du crochet de démarrage (stub.S, BOOT2) : entre la fin des moteurs et MACRO
    own = dict(machines=[macro], bridge=br, end=bss_end, boot2=((lay["end"] + 15) & ~15, pay + MACRO_AT),
               parts=br["extra"] + [{"dest": f"{pay + MACRO_AT:#x}", "hex": blob.hex()}])
    out, ndesc = gs.build_tweak(img, st_img, codes, tg=tg, own=own)

    first = gs.TG_FIRST if tg else 6
    names = [gs.CATALOG[c]["name"] for c in codes]
    which = ", ".join(f"{gs.CATALOG[c]['name']} = {gs.CATALOG[c]['label']} (machine {first + i + 1})"
                      for i, c in enumerate(codes)) + f", MACRO (machine {first + len(codes) + 1})"
    tid = tweak_id(codes, bool(tg))
    ids = (gm.other_ids() | {"macro", "macro-tg", "model-tg"} | {tweak_id(c) for c in gs.subsets()}
           | {tweak_id(c, True) for c in gs.subsets()} | {"syntakt-tg-meter", "syntakt-tg-profile"})
    if not tg:
        ids.add("model-tg-st")
    meta = {
        "id": tid,
        "order": out["order"],
        "name": ("Model-TG + " if tg else "") + "Vrais moteurs du Syntakt (" + ", ".join(names)
                + ") et machine MACRO (Braids, Émilie Gillet, MIT)",
        "description": ([
            "Version combinée avec Model-TG (notes/31) : s'ajoute après model-tg-st, le Sampler reste la 7e machine.",
        ] if tg else []) + [
            "Moteurs du Syntakt (OS 1.42 ou 1.41, extraits AU BUILD de TON Syntakt_OS1.42.syx) et machine MACRO (notes/43),",
            "ensemble (notes/50) : " + which + ".",
            "Passerelle des moteurs reprise telle quelle de " + tw["id"] + " ; MACRO compilé comme 25-macro.json",
            f"({gm.EURORACK_REPO} {gm.EURORACK_COMMIT[:7]}, licence MIT : LICENSE-Braids). Charge utile rangée compressée",
            "(aPLib), décompressée au démarrage ; tables d'ondes de CHORD reprises en SRAM. Le régulateur de charge des",
            "moteurs vaut aussi pour MACRO. Généré par tools/gen_macro_syntakt.py. Aucun octet Elektron dans ce fichier.",
        ],
    }
    rest = {k: v for k, v in out.items() if k not in ("id", "order", "name", "description", "conflicts")}
    out = dict(meta, gov=rest.pop("gov"), device=rest.pop("device"), os=rest.pop("os"), section=rest.pop("section"))
    if "requires" in rest:
        out["requires"] = rest.pop("requires")
    out["conflicts"] = sorted(ids - {tid})
    out.update(rest)
    out["description"] += [d for d in tw["description"] if d == gov_asm.NOTE]
    out["symbols"] = {k: f"{syms[n]:#x}" for k, n in (("macro_update", "macro_update"), ("macro_render", "macro_render"),
                                                       ("braids_render", gm.BRAIDS_RENDER))}
    # taille rangée : la charge utile telle qu'au démarrage, compressée comme par build.py et le flasher
    rt = build.payload_runtime(out, img, st_img)
    packed = len(aplib_grow.pack(rt))
    at = int(out["append"]["at"], 16)
    if at + packed > gs.END_LIMIT:
        raise SystemExit(f"!! {tid} : {packed} o compressés, l'image dépasserait {gs.END_LIMIT:#x}")
    # place dans l'image, pour tools/check_overlaps.py (sans fichier d'Elektron) : mesurée avec le Syntakt OS du
    # générateur (1.42) ; build.py et le flasher revérifient la limite sur le vrai build
    out["append"]["stored"] = packed
    return out, dict(ndesc=ndesc, size=len(rt), packed=packed, end=at + packed, macro=len(blob))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--syntakt", required=True, help="Syntakt_OS1.42.syx (ou 1.41) officiel")
    ap.add_argument("--eurorack", required=True, help=f"clone de {gm.EURORACK_REPO} au commit {gm.EURORACK_COMMIT[:7]}")
    ap.add_argument("--engines", help="moteurs, séparés par des virgules (sinon toutes les combinaisons)")
    ap.add_argument("--tg", action="store_true", help="avec --engines : la version combinée avec Model-TG seulement")
    ap.add_argument("--check", action="store_true", help="vérifie que les JSON versionnés correspondent")
    args = ap.parse_args()
    img = g7.cycles_main(args.cycles)
    if len(img) != gx.IMAGE_LEN:
        raise SystemExit("!! ce n'est pas le MAIN OS 1.13 officiel")
    repo = pathlib.Path(args.eurorack).resolve()
    gm.check_sources(repo)
    st_img = syntakt.dsp_image(args.syntakt)
    if args.engines:
        want = args.engines.split(",")
        if set(want) - set(gs.CATALOG):
            raise SystemExit(f"!! moteurs inconnus : {set(want) - set(gs.CATALOG)}")
        todo = [([c for c in gs.CATALOG if c in want], args.tg)]
    else:
        todo = [(c, tg) for tg in (False, True) for c in gs.subsets()]
    tg_ctx = gs.tg_context(img)
    bad = 0
    for codes, tg in todo:
        tweak, info = build_tweak(img, st_img, repo, codes, tg_ctx if tg else None)
        path = DEV / f"{tweak['order']}-{tweak['id']}.json"
        text = json.dumps(tweak, indent=1) + "\n"
        print(f"  {tweak['id']} : {len(tweak['writes'])} écritures, {info['ndesc']} descripteurs, charge utile "
              f"{info['size']} o, compressée en {info['packed']} o, image jusqu'à {info['end']:#x}")
        if args.check:
            ok = path.exists() and path.read_text(encoding="utf-8") == text
            print(f"    {path.name} {'est à jour' if ok else 'NE CORRESPOND PAS (autre GCC ?)'}")
            bad += not ok
        else:
            path.write_text(text, encoding="utf-8")
            print(f"    écrit : {path}")
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
