#!/usr/bin/env python3
"""Embarque les tables de patchs dans docs/flasher/tweaks.js pour le flasher web.

Le flasher web (docs/flasher/) construit le .syx dans le navigateur ; il lui
faut les tweaks. Plutot que de les lire par fetch (chemins fragiles sous GitHub
Pages, ne marche pas en file://), on les embarque dans un petit .js genere ici,
a partir des JSON canoniques de tweaks/. Source unique : ce script recopie, il
n'invente rien.

    python3 tools/gen_flasher_tweaks.py           # (re)genere docs/flasher/tweaks.js
    python3 tools/gen_flasher_tweaks.py --check    # verifie qu'il est a jour (CI)
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DEV_DIR = ROOT / "tweaks" / "model-cycles_OS1.13"
OUT = ROOT / "docs" / "flasher" / "tweaks.js"

# Fonctionnalites proposees dans le flasher web, en cases a cocher. Une fonctionnalite peut
# avoir plusieurs variantes mutuellement exclusives : elles s'affichent en sous-choix quand la
# case est cochee. Chaque variante pointe vers un tweak de tweaks/.
# Le flasher web n'envoie que par USB (CONFIG > UPGRADE) : il ne propose que des tweaks qui gardent
# cette mise a jour par USB. 6ch-multiout (la casse) et sdvintage-snare restent dans build.py.
# Vrais moteurs du Syntakt ("engines") : une case par moteur du catalogue de gen_syntakt_engines.py ;
# chaque combinaison cochee pointe vers son tweak syntakt-<moteurs> ; la carte est « testee » si au moins une
# combinaison l'est (HW_TESTED de gen_syntakt_engines.py).
# excludes : cartes qu'on ne peut pas cocher ensemble (cocher l'une decoche l'autre).
# includes : tweaks deja contenus dans cette fonctionnalite ; ils s'en excluent comme avec excludes, et le flasher
# les affiche coches et verrouilles, « inclus avec … », tant qu'elle est cochee.
# Les moteurs s'ajoutent en machines supplementaires : sdvintage-exact (a la place de SNARE) reste dans build.py.
# status : "tested" (flashe sur un vrai Model:Cycles) ou "experimental".
# credit : auteur du travail d'origine, affiche sur la carte (voir aussi les credits de la page).
# Pour ajouter une fonctionnalite : ecrire son tweak JSON, puis l'ajouter ici.
FEATURES = [
    {
        "id": "usb6",
        "label": "Sortie USB 6 canaux separes",
        "desc": "Chaque piste sort sur son propre canal USB (48 kHz / 32 bits). Le mix stereo "
                "n'est plus envoye en USB : tu melanges les 6 pistes dans ton logiciel.",
        "status": "tested",
        "credit": {"kind": "based", "who": "scottmetoyer", "repo": "scottmetoyer/ms-multi-output"},
        "variants": [
            {"file": "11-6ch-usbup", "label": None},
        ],
    },
    {
        "id": "model-tg",
        "label": "Model-TG",
        "desc": "Machine Sampler, reechantillonnage, retrig et effets master, et plus.",
        "status": "experimental",
        "credit": {"kind": "by", "who": "TinyGregAudio", "repo": "TinyGregAudio/Model-TG"},
        # Model-TG contient deja les tweaks de drumkilla : le flasher les affiche coches et verrouilles
        # (« inclus avec Model-TG ») tant que Model-TG est coche, sans les ajouter au build
        "includes": ["latching-mute", "trig-preview", "browser-scroll"],
        "license": "LICENSE-Model-TG",
        "variants": [
            {"file": "30-model-tg", "label": None},
        ],
        # avec les moteurs du Syntakt : la base de la version combinee (notes/31), et pour chaque combinaison de
        # moteurs son tweak syntakt-tg-<moteurs> (« tg » des combinaisons de la carte des moteurs)
        "with": {"syntakt": "30-model-tg-st"},
    },
    {
        "id": "latching-mute",
        "label": "Mode mute verrouille",
        "desc": "Maintiens TRK et tape FUNC : le mode mute reste actif, tu mutes les pistes sans tenir FUNC. "
                "Un appui court sur FUNC en sort.",
        "status": "tested",
        "credit": {"kind": "by", "who": "drumkilla", "repo": "drumkilla/elektron-model-tweaks"},
        "variants": [
            {"file": "01-latching-mute", "label": None},
        ],
    },
    {
        "id": "trig-preview",
        "label": "Ecoute d'un pas (TRIG + PAGE)",
        "desc": "Sequenceur a l'arret (ou en pause), maintiens un pas et appuie sur PAGE : le pas joue avec sa note, "
                "sa longueur et ses p-locks.",
        "status": "tested",
        "credit": {"kind": "by", "who": "drumkilla", "repo": "drumkilla/elektron-model-tweaks"},
        "variants": [
            {"file": "02-trig-preview", "label": None},
        ],
    },
    {
        "id": "browser-scroll",
        "label": "Defilement des noms longs",
        "desc": "Dans le navigateur de sons, un nom trop long pour l'ecran defile.",
        "status": "tested",
        "credit": {"kind": "by", "who": "drumkilla", "repo": "drumkilla/elektron-model-tweaks"},
        "variants": [
            {"file": "03-browser-scroll", "label": None},
        ],
    },
    {
        "id": "trig-hold",
        "label": "Effacer un trig plus facilement",
        "desc": "Un appui sur une touche de pas qui porte deja un trig l'efface si tu relaches en moins d'une "
                "demi-seconde (0,2 s avec l'OS d'origine). Tenu plus longtemps, le trig reste et ses reglages s'affichent.",
        "status": "tested",
        "credit": None,
        "variants": [
            {"file": "41-trig-hold", "label": None},
        ],
    },
    {
        "id": "arp",
        "label": "Arpegiateur",
        "desc": "Le retrig devient un arpegiateur : plusieurs notes tenues avec RETRIG (ou A.On) se jouent l'une "
                "apres l'autre. FUNC + RETRIG : sens (Arp) et octaves (Oct), enregistres avec le pattern. "
                "En live rec, les notes jouees par l'arpege sont enregistrees une a une.",
        "status": "tested",
        "credit": None,
        "variants": [
            {"file": "40-arp", "label": None},
        ],
    },
    {
        "id": "tempo-max",
        "label": "Tempo jusqu'a 546 BPM",
        "desc": "Le tempo monte jusqu'a 546 BPM au lieu de 300 (molette, tap tempo, horloge MIDI recue). "
                "546 est le plafond du format des projets.",
        "status": "tested",
        "credit": None,
        "variants": [
            {"file": "42-tempo-max", "label": None},
        ],
    },
    {
        "id": "boot-anim",
        "label": "Animation de demarrage modded-cycles",
        "desc": "Au demarrage, les quatre carres du logo apparaissent un par un puis modded-cycles s'ecrit "
                "dessous, a la place des carreaux qui clignotent. Meme duree qu'a l'origine.",
        "status": "tested",
        "credit": None,
        "variants": [
            {"file": "43-boot-anim", "label": None},
        ],
    },
    {
        "id": "track-filter",
        "label": "Filtre par piste (LP / OFF / HP)",
        "desc": "MACHINES tenu + SWEEP : un filtre par piste, passe-bas a gauche, rien au centre, passe-haut a droite. "
                "CONTOUR : resonance ; COLOR et SHAPE : enveloppe du filtre (quantite, decay). P-locks, LFO, CC 74 / 71.",
        "status": "tested",
        "credit": None,
        # meme geste que le filtre de Model-TG (MACHINES + SWEEP / CONTOUR) : pas ensemble pour l'instant (notes/47 §7, §11)
        "excludes": ["model-tg"],
        "variants": [
            {"file": "48-track-filter", "label": None},
        ],
    },
    {
        "id": "syntakt",
        "label": "Vrais moteurs du Syntakt",
        "desc": "Les moteurs du Syntakt, extraits de TON fichier Syntakt_OS1.42.syx (a deposer a l'etape 2), "
                "en machines supplementaires apres les 6 d'origine : coche ceux que tu veux. "
                "Identiques au Syntakt en emulation.",
        "status": "tested",
        "credit": None,
        "needs": "syntakt",
        "engines": True,
    },
]


def engine_feature(f, load):
    """Carte des vrais moteurs du Syntakt : les moteurs du catalogue et le tweak de chaque combinaison."""
    import gen_syntakt_engines as gs
    engines = [{"code": c, "name": m["name"], "label": m["label"]} for c, m in gs.CATALOG.items()]
    combos = []
    for codes in gs.subsets():
        t = load(gs.subset_id(codes))
        combos.append({"id": t["id"], "engines": codes, "tested": tuple(codes) in gs.HW_TESTED,
                       "label": ", ".join(gs.CATALOG[c]["name"] for c in codes),
                       "tg": load(gs.tweak_id(codes, tg=True))["id"],      # avec Model-TG (notes/31)
                       "tg_tested": tuple(codes) in gs.HW_TESTED_TG})
    return engines, combos


def render():
    from crossflash import OFFICIAL            # empreintes des OS officiels, source unique (tools/crossflash.py)
    device = json.loads((DEV_DIR / "device.json").read_text(encoding="utf-8"))
    tweaks, seen, features = [], {}, []
    by_id = {}
    for p in sorted(DEV_DIR.glob("*.json")):
        if p.name != "device.json":
            t = json.loads(p.read_text(encoding="utf-8"))
            by_id[t["id"]] = t

    def load(tid):
        t = by_id[tid]
        if tid not in seen:
            seen[tid] = True
            tweaks.append(t)
        return t
    for f in FEATURES:
        feat = {"id": f["id"], "label": f["label"], "desc": f["desc"], "status": f["status"], "credit": f["credit"]}
        if f.get("engines"):
            feat["engines"], feat["combos"] = engine_feature(f, load)
            feat["status"] = "tested" if any(c["tested"] or c["tg_tested"] for c in feat["combos"]) else "experimental"
        else:
            by_file = {json.loads((DEV_DIR / f"{v['file']}.json").read_text(encoding="utf-8"))["id"]: v for v in f["variants"]}
            feat["variants"] = [{"id": load(tid)["id"], "label": v["label"]} for tid, v in by_file.items()]
        if f.get("needs"):
            feat["needs"] = f["needs"]
        if f.get("excludes"):
            feat["excludes"] = f["excludes"]
        if f.get("includes"):
            feat["includes"] = f["includes"]
        if f.get("with"):                       # autre tweak quand une autre carte est cochee aussi
            feat["with"] = {g: load(json.loads((DEV_DIR / f"{v}.json").read_text(encoding="utf-8"))["id"])["id"]
                            for g, v in f["with"].items()}
        if f.get("license"):                    # texte de la licence, servi a cote de la page (licenses())
            feat["license"] = f["license"] + ".txt"
        features.append(feat)
    payload = {
        "device": {k: device[k] for k in ("device", "os", "section_sha256", "stock_syx_sha256", "cave_refs_ok")
                   if k in device},
        "tweaks": tweaks,
        "features": features,
        # onglet « OS Samples » : l'OS Model:Samples officiel, mis dans le conteneur du Cycles (crossflash)
        "samples": {"syx_sha256": OFFICIAL["samples"]["syx"], "main_sha256": OFFICIAL["samples"]["main"],
                    "download": "https://www.elektron.se/support-downloads/modelsamples"},
        # fonctionnalités « needs: syntakt » : le fichier officiel Syntakt_OS1.42.syx de l'utilisateur
        "syntakt": {"download": "https://www.elektron.se/support-downloads/syntakt"},
    }
    body = json.dumps(payload, ensure_ascii=False, indent=1)
    return (
        "/* Genere par tools/gen_flasher_tweaks.py depuis tweaks/model-cycles_OS1.13/.\n"
        " * NE PAS editer a la main : relance le script apres avoir change un tweak. */\n"
        "window.MC_TWEAKS = " + body + ";\n"
    )


def licenses():
    """Licences a publier avec la page (code tiers embarque dans tweaks.js) : {fichier servi : texte}."""
    return {OUT.parent / (f["license"] + ".txt"): (DEV_DIR / f["license"]).read_text(encoding="utf-8")
            for f in FEATURES if f.get("license")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verifie sans ecrire")
    args = ap.parse_args()
    text = render()
    if args.check:
        stale = [p.name for p, t in licenses().items() if not p.exists() or p.read_text(encoding="utf-8") != t]
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text or stale:
            sys.exit("!! docs/flasher/tweaks.js (ou une licence) n'est pas a jour : relance tools/gen_flasher_tweaks.py")
        print("docs/flasher/tweaks.js est a jour")
        return
    for p, t in licenses().items():
        p.write_text(t, encoding="utf-8")
    OUT.write_text(text, encoding="utf-8")
    print(f"ecrit : {OUT.relative_to(ROOT)} ({len(text)} o, {len(FEATURES)} fonctionnalites)")


if __name__ == "__main__":
    main()
