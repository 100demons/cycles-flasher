#!/usr/bin/env python3
"""Génère les tweaks où la machine ACID (notes/54) joue avec la machine MACRO (notes/43) et les vrais moteurs du
Syntakt (notes/20), sur la même machine (notes/54 §11) :

  - 25-macro-acid.json, 32-macro-acid-tg.json : MACRO puis ACID, 7e et 8e machines, ou 8e et 9e après le Sampler
    de Model-TG. Mécanique de MACRO seule (gen_macro.added_machine, ici pour 2 machines) : charge utile rangée en
    clair, par morceaux (PACK) ;
  - 24-syntakt-<moteurs>-acid.json et 24-syntakt-<moteurs>-macro-acid.json, et leurs versions avec Model-TG
    (31-syntakt-tg-<moteurs>-…) : les moteurs du Syntakt, MACRO s'il est coché, puis ACID. Mécanique de
    gen_macro_syntakt.py (notes/50) : passerelle des moteurs reprise octet pour octet de leur tweak versionné,
    charge utile rangée compressée (aPLib), 2e étage du crochet de démarrage, régulateur de charge des moteurs
    étendu à nos machines.

ACID est toujours la dernière machine. Son code est lié à la même place dans toutes ces combinaisons (ACID_AT,
au-dessus des variables de MACRO quand MACRO est avec les moteurs), ses variables à ACID_BSS : le flasher ne range
ses octets qu'une fois (seuls, et avec Model-TG). Il est compilé avec GOV_SKIP (tools/machines/acid/acid.c) : une
voix que le régulateur des moteurs a cessé de calculer (restée faible, ou éteinte sous la surcharge) rejoue sa note
au trig suivant, au lieu de glisser depuis une note éteinte. MACRO garde sa place et ses octets : à 0 dans
macro-acid (ceux de 25-macro / 32-macro-tg), à MACRO_AT avec les moteurs (ceux des tweaks « -macro »).
Avec Model-TG, les 5 moteurs, MACRO et ACID : 14 machines, dont 7 ajoutées (rangées : gs.ROWS7).

    python3 tools/gen_acid_combos.py --cycles model-cycles_OS1.13.syx --syntakt Syntakt_OS1.42.syx \\
        --eurorack vendor/eurorack [--engines sd,cp | --engines none] [--tg] [--macro yes|no] [--check]

Sans --engines : toutes les combinaisons (126 fichiers). --engines none : macro-acid seulement. De l'OS, ces fichiers
ne portent que les courts octets d'origine (« old ») qui vérifient le fichier officiel ; la table des descripteurs
est recopiée au build depuis TON fichier (recette « cycles »), le code du Syntakt extrait au build de TON
Syntakt_OS1.42.syx. MACRO et ACID sont compilés par m68k-linux-gnu-g++/gcc 13.3 (Ubuntu 24.04), comme 25-macro.json
et 26-acid.json : un autre GCC donne d'autres octets, et --check le dit.
"""
import argparse
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "emu"))

import gen_acid as ga              # noqa: E402
import gen_macro as gm             # noqa: E402
import gen_macro_syntakt as gms    # noqa: E402
import gen_sdvintage_exact as gx   # noqa: E402
import gen_sdvintage_7th as g7     # noqa: E402
import gen_syntakt_engines as gs   # noqa: E402
import gov_asm                     # noqa: E402
import syntakt                     # noqa: E402
import usb_steady                  # noqa: E402
import voice_loop                  # noqa: E402

DEV = gs.DEV
# Place d'ACID dans la charge utile (décalages depuis son début) : au-dessus des variables de MACRO avec les moteurs
# (gms.MACRO_BSS + ses 6 voix : jusqu'à 0x743e0), le code (8 Ko au plus), puis ses variables (6 x 124 o).
ACID_AT = 0x76000
ACID_BSS = 0x78000
DEFS = ("GOV_SKIP",)
# Combinaisons testées sur un vrai Model:Cycles : (moteurs, avec MACRO), sans puis avec Model-TG. Ajouter ici après
# un test réussi (règle 3 d'AGENTS.md : seulement sur le retour de Maxime).
# 12/10/2026 : les 5 moteurs, MACRO et ACID, fichiers construits par build.py avec les mods de notes/54 §11.7, sans
# Model-TG (MAIN OS 85139773…) et avec (d823ff90…) : « c nickel sur machine ça marche parfait » (Maxime, qui n'a pas
# dit lequel des deux fichiers il a flashé).
FIVE = ("sd", "cp", "toy", "bits", "swarm")
HW_TESTED = {(FIVE, True)}
HW_TESTED_TG = {(FIVE, True)}


def tweak_id(codes, tg=False, macro=True):
    """macro-acid[-tg] sans moteurs ; syntakt[-tg]-<moteurs>[-macro]-acid avec."""
    if not codes:
        return "macro-acid-tg" if tg else "macro-acid"
    return gs.tweak_id(codes, tg=tg) + ("-macro" if macro else "") + "-acid"


def order(codes, tg):
    return (31 if tg else 24) if codes else (32 if tg else 25)


def all_ids(tg):
    """Tous les tweaks qui ajoutent des machines (ou le même bloc après l'image) : jamais avec l'un des nôtres ; sans
    Model-TG, pas non plus avec sa base (model-tg-st), dont la place après l'image est la nôtre."""
    ids = gm.other_ids() | {"macro", "macro-tg", "acid", "acid-tg", "model-tg", "macro-acid", "macro-acid-tg"}
    for codes in gs.subsets():
        for tg_ in (False, True):
            ids |= {gs.tweak_id(codes, tg=tg_), gms.tweak_id(codes, tg_)}
            ids |= {tweak_id(codes, tg_, m) for m in (False, True)}
    return ids if tg else ids | {"model-tg-st"}


_ACID = {}


def acid_part(pay):
    """ACID lié à pay + ACID_AT (variables à pay + ACID_BSS), avec GOV_SKIP : dict(machine, at, blob, end, syms)."""
    if pay not in _ACID:
        at, bss = pay + ACID_AT, pay + ACID_BSS
        with tempfile.TemporaryDirectory() as d:
            blob, syms, end = ga.compile_machine(pathlib.Path(d), at, ga.tables_header(), bss, bss, DEFS)
        machine = dict(ga.MACHINE, label="ACID", update=syms["acid_update"], render=syms["acid_render"])
        _ACID[pay] = dict(machine=machine, at=at, blob=blob, end=end, syms=syms)
    return _ACID[pay]


def symbols(out, macro_syms, acid):
    """Pour les preuves (tools/emu/test_acid_combos.py) : entrées de nos machines, rendu de Braids, voix d'ACID."""
    sy = {}
    if macro_syms:
        sy.update({k: f"{macro_syms[n]:#x}" for k, n in (("macro_update", "macro_update"),
                                                          ("macro_render", "macro_render"),
                                                          ("braids_render", gm.BRAIDS_RENDER))})
    sy.update({k: f"{acid['syms'][k]:#x}" for k in ("acid_update", "acid_render", "trk")})
    out["symbols"] = sy


def lines_end():
    return ["Généré par tools/gen_acid_combos.py. De l'OS, seuls les octets d'origine (old) qui vérifient le fichier",
            "officiel ; la table des descripteurs est recopiée au build (recette cycles)."]


def acid_line():
    return (f"ACID d'après Open303 (Robin Schmidt, licence MIT : LICENSE-Open303), lié à +{ACID_AT:#x}, compilé avec "
            "GOV_SKIP.")


def build_macro_acid(img, repo, tg=None):
    """MACRO puis ACID, sans les moteurs du Syntakt."""
    pay = gs.PAY_TG if tg else gs.PAY_ALONE
    gs.set_base(pay)
    acid = acid_part(pay)
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        mblob, msyms, mend = gm.compile_machine(tmp, repo, pay)
        if mend > acid["at"]:
            raise SystemExit(f"!! MACRO jusqu'à {mend:#x} : ACID commence à {acid['at']:#x}")
        macro = dict(gm.MACHINE, label="MACRO", update=msyms["macro_update"], render=msyms["macro_render"])
        writes, append = gm.added_machine(img, tg, [macro, acid["machine"]], tmp,
                                          [(pay, mblob), (acid["at"], acid["blob"])], acid["end"])
    if tg and acid["end"] > pay + gms.TG_ROOM:
        raise SystemExit(f"!! charge utile jusqu'à {acid['end']:#x} : au-delà de la place laissée par Model-TG")
    tid = tweak_id((), bool(tg))
    first = gs.TG_FIRST if tg else 6
    out = {
        "id": tid,
        "order": order((), bool(tg)),
        "name": ("Model-TG + " if tg else "") + "Machines MACRO (Braids, Émilie Gillet, MIT) et ACID (basse acide, "
                "d'après Open303, MIT)",
        "description": ([
            "Version combinée avec Model-TG (notes/31) : s'ajoute après model-tg-st, le Sampler reste la 7e machine.",
        ] if tg else []) + [
            f"Machines MACRO (notes/43, machine {first + 1}) et ACID (notes/54, machine {first + 2}), ensemble "
            "(notes/54 §11).",
            f"MACRO compilé comme 25-macro.json ({gm.EURORACK_REPO} {gm.EURORACK_COMMIT[:7]}, licence MIT : "
            "LICENSE-Braids), à la même place.",
            acid_line(),
        ] + lines_end(),
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
    }
    if tg:
        out["requires"] = [tg["id"]]
    out.update({"conflicts": sorted(all_ids(tg) - {tid}), "writes": writes, "append": append})
    symbols(out, msyms, acid)
    if not tg:                    # comme MACRO et ACID seules : envoi à l'USB à heure fixe (notes/35), boucle des
        out = usb_steady.add_to(out)          # voix (notes/36) ; la version combinée les a par model-tg-st
        out = voice_loop.add_to(out)
    segs = sum(n for _, n in append["pack"])
    at = int(append["at"], 16)
    return out, dict(ndesc=g7.NDESC + 10, size=append["size"], packed=segs, end=at + segs)


def build_engines(img, st_img, repo, codes, tg=None, macro=True):
    """Les moteurs codes, MACRO si macro, puis ACID (gen_macro_syntakt.build_tweak)."""
    pay = gs.PAY_TG if tg else gs.PAY_ALONE
    acid = acid_part(pay)
    out, info = gms.build_tweak(img, st_img, repo, codes, tg, macro=macro, acid=acid)
    macro_syms = gms.compile_macro(repo, pay)[1] if macro else None
    first = gs.TG_FIRST if tg else 6
    names = [gs.CATALOG[c]["name"] for c in codes]
    which = ", ".join(f"{gs.CATALOG[c]['name']} = {gs.CATALOG[c]['label']} (machine {first + i + 1})"
                      for i, c in enumerate(codes))
    k = first + len(codes)
    if macro:
        which += f", MACRO (machine {k + 1})"
        k += 1
    which += f", ACID (machine {k + 1})"
    tid = tweak_id(codes, bool(tg), macro)
    versioned = gs.tweak_id(codes, tg=bool(tg))
    gov = [gov_asm.NOTE] if gov_asm.NOTE in out["description"] else []
    out.update({
        "id": tid,
        "name": ("Model-TG + " if tg else "") + "Vrais moteurs du Syntakt (" + ", ".join(names) + ")"
                + (", machine MACRO (Braids, Émilie Gillet, MIT)" if macro else "")
                + " et machine ACID (basse acide, d'après Open303, MIT)",
        "description": ([
            "Version combinée avec Model-TG (notes/31) : s'ajoute après model-tg-st, le Sampler reste la 7e machine.",
        ] if tg else []) + [
            "Moteurs du Syntakt (OS 1.42 ou 1.41, extraits AU BUILD de TON Syntakt_OS1.42.syx)"
            + (", machine MACRO (notes/43)" if macro else "") + " et machine ACID (notes/54),",
            "ensemble (notes/54 §11) : " + which + ".",
            "Passerelle des moteurs reprise telle quelle de " + versioned
            + (f" ; MACRO compilé comme 25-macro.json ({gm.EURORACK_REPO} {gm.EURORACK_COMMIT[:7]}, licence MIT : "
               "LICENSE-Braids), à la place des tweaks -macro." if macro else "."),
            acid_line(),
            "Charge utile rangée compressée (aPLib), décompressée au démarrage ; tables d'ondes de CHORD reprises en",
            "SRAM. Le régulateur de charge des moteurs vaut aussi pour " + ("MACRO et ACID." if macro else "ACID."),
        ] + lines_end() + gov,
        "conflicts": sorted(all_ids(tg) - {tid}),
    })
    symbols(out, macro_syms, acid)
    return out, info


def todo_list(args):
    if args.engines is None:
        return ([((), tg, True) for tg in (False, True)]
                + [(tuple(c), tg, m) for tg in (False, True) for m in (False, True) for c in gs.subsets()])
    if args.engines == "none":
        codes = ()
    else:
        want = args.engines.split(",")
        if set(want) - set(gs.CATALOG):
            raise SystemExit(f"!! moteurs inconnus : {set(want) - set(gs.CATALOG)}")
        codes = tuple(c for c in gs.CATALOG if c in want)
    macros = [True] if not codes else {"yes": [True], "no": [False], "both": [False, True]}[args.macro]
    return [(codes, tg, m) for tg in ((True,) if args.tg else (False, True)) for m in macros]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--syntakt", required=True, help="Syntakt_OS1.42.syx (ou 1.41) officiel")
    ap.add_argument("--eurorack", required=True, help=f"clone de {gm.EURORACK_REPO} au commit {gm.EURORACK_COMMIT[:7]}")
    ap.add_argument("--engines", help="moteurs, séparés par des virgules, ou none (sinon toutes les combinaisons)")
    ap.add_argument("--tg", action="store_true", help="avec --engines : la version combinée avec Model-TG seulement")
    ap.add_argument("--macro", choices=("yes", "no", "both"), default="both", help="avec --engines : avec MACRO ou non")
    ap.add_argument("--check", action="store_true", help="vérifie que les JSON versionnés correspondent")
    args = ap.parse_args()
    img = g7.cycles_main(args.cycles)
    if len(img) != gx.IMAGE_LEN:
        raise SystemExit("!! ce n'est pas le MAIN OS 1.13 officiel")
    repo = pathlib.Path(args.eurorack).resolve()
    gm.check_sources(repo)
    st_img = syntakt.dsp_image(args.syntakt)
    tg_ctx = gs.tg_context(img)
    bad = 0
    for codes, tg, macro in todo_list(args):
        ctx = tg_ctx if tg else None
        if codes:
            tweak, info = build_engines(img, st_img, repo, list(codes), ctx, macro)
        else:
            tweak, info = build_macro_acid(img, repo, ctx)
        path = DEV / f"{tweak['order']}-{tweak['id']}.json"
        text = json.dumps(tweak, indent=1) + "\n"
        print(f"  {tweak['id']} : {len(tweak['writes'])} écritures, {info['ndesc']} descripteurs, charge utile "
              f"{info['size']} o, rangée en {info['packed']} o, image jusqu'à {info['end']:#x}")
        bad += gm.emit(path, text, args.check)
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
