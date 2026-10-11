#!/usr/bin/env python3
"""Génère tweaks/model-cycles_OS1.13/49-generate.json et 49-generate-st.json : un générateur de trigs euclidien ou
aléatoire sur SETTINGS + TRACK, avec Model-TG (idée et première version : DavidCaruso, dans son firmware
« Model-TG-VA-DR-v1 » ; réécrit ici, il n'a publié ni source ni licence).

Tenir SETTINGS et appuyer sur TRACK ouvre une liste « Generate » par-dessus l'écran, comme les menus d'options de
Model-TG : 12 réglages (mode RND / EUC, densité, coups, rotation, notes dans une gamme, tonique, gamme, octave,
étendue, vélocité aléatoire et ses bornes) et une ligne GEN, dont l'appui réécrit toute la piste sélectionnée à
l'ouverture (trigs, notes et vélocités de chaque pas jusqu'à la longueur de la piste), puis affiche « Trigs: N ».

tools/machines/generate/ : generate.S (l'accord, le menu, la génération, les données), lié par generate.ld dans
sept masques de sprites 48x22 libérés (tools/sprites.py). Le code appelle des fonctions de Model-TG et lit son état,
aux adresses des « symbols » de 30-model-tg.json et 30-model-tg-st.json (GEN_SYMBOLS de tools/gen_model_tg.py, les
mêmes dans les deux) : le tweak existe en deux fichiers aux écritures identiques, l'un pour chaque version de
Model-TG (« requires »). Son accroche remplace le jmp key_hook que Model-TG écrit en 0x4007240c. Note :
notes/56 §2. Preuve : tools/emu/test_generate.py.

    python3 tools/gen_generate.py --cycles model-cycles_OS1.13.syx [--check]
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

import build                       # noqa: E402
import gen_sdvintage_exact as gx   # noqa: E402
import sprites                     # noqa: E402
import test_sdvintage as T         # noqa: E402

SRC = HERE / "machines" / "generate"
TW = HERE.parent / "tweaks" / "model-cycles_OS1.13"
BASE = gx.BASE
# version de Model-TG -> fichier de ce tweak
OUTS = {"model-tg": TW / "49-generate.json", "model-tg-st": TW / "49-generate-st.json"}
TG_FILES = {"model-tg": TW / "30-model-tg.json", "model-tg-st": TW / "30-model-tg-st.json"}
# sections liées -> masque 48x22 libéré qui les reçoit (generate.ld)
CAVES = ((".cave1", 0x4018b9c8), (".cave2", 0x4018bb48), (".cave3", 0x4018cbc8), (".cave4", 0x4018d038),
         (".cave5", 0x4018d798), (".cave6", 0x4018f80c), (".cave7", 0x40190184))
# -D de generate.S -> symbole de Model-TG
TG_DEFS = {"TG_KEY_HOOK": "key_hook", "TG_SET_HELD": "set_held", "TG_MOD_USED": "mod_used", "TG_RTG_ON": "rtg_on",
           "TG_SLE_ON": "sle_on", "TG_MM_OPENED": "mm_opened", "TG_GM_LIVE": "gm_live",
           "TG_GM_OPENED": "gm_opened", "TG_GM_DONE": "gm_done", "TG_GM_TRACK": "gm_track", "TG_GM_CUR": "gm_cur",
           "TG_LM_BUILD": "lm_build", "TG_GM_LAB": "gm_lab", "TG_GM_VAL": "gm_val", "TG_GM_VNAME": "gm_vname",
           "TG_NEW_SLOT2": "new_slot2_invoker", "TG_SHOW_POPUP": "show_popup"}
# Contrat avec Model-TG v1.1.0 (vérifié dans sa charge utile, les deux versions) : le début des fonctions appelées
# ou rejointes. key_hook relit le code (moveal 4(sp),a0 ; movel 12(a0),d0) puis teste rtg_on et sle_on avant tout ;
# gran_menu_open pose le cadre que lm_build et gm_done attendent (link.w fp,#-80 ; lea -28(sp) ;
# movem d2-d4/a2-a5), le même que gen_build ; gm_opened met mm_opened à 1 puis tombe dans gm_done, qui défait ce
# cadre ; lm_build commence par lea ALLOC,a4 ; gm_lab, gm_val, new_slot2_invoker et show_popup sont les fermetures et
# le message décrits dans generate.S.
TG_HEADS = {"key_hook": "206f00042028000c4ab9", "gran_menu_open": "4e56ffb04fefffe448d73c1c",
            "gm_live": "41fa053020106742", "gm_opened": "41fa1534700120804cd73c1c4e5e4e75",
            "gm_done": "4cd73c1c4e5e4e75", "lm_build": "49f940080064",
            "gm_lab": "4e56fffc2f02486effff2f09", "gm_val": "4e56ffd048d73c1c201020310c00",
            "new_slot2_invoker": "2f02242f000c2f024eb9400732f8", "show_popup": "4e56ffe448d7040c203940fe4178"}
TG_ZERO = ("set_held", "mod_used", "rtg_on", "sle_on", "mm_opened", "gm_track")   # à zéro au départ
KEY_CODE = 0x4007240c                                  # accesseur du code d'un KeyEvent ; Model-TG y met jmp key_hook
KEY_STOCK = "206f00042028000c4e75"                     # moveal 4(sp),a0 ; movel 12(a0),d0 ; rts
# pour tools/emu/test_generate.py
SYMBOLS = ("gen_key", "gen_open", "gen_lab", "gen_val", "gen_turn", "gen_press", "gen_go", "gen_rndn", "gen_set",
           "gen_rng", "gen_ev", "gen_ptr", "gen_zero", "gen_num", "gen_desc", "gen_min", "gen_max", "gen_noff",
           "gen_labels", "gen_scales", "gen_title", "gen_fmt")


def tg_symbols():
    """Symboles de Model-TG utilisés, identiques dans les deux versions, et le tweak de chacune."""
    syms, tgs = None, {}
    need = set(TG_DEFS.values()) | set(TG_HEADS) | set(TG_ZERO) | {"gran_menu_open"}
    for tid, f in TG_FILES.items():
        t = json.loads(f.read_text(encoding="utf-8"))
        s = {n: int(v, 16) for n, v in t.get("symbols", {}).items()}
        if need - set(s):
            raise SystemExit(f"!! {f.name} ne porte pas les symboles {sorted(need - set(s))} (tools/gen_model_tg.py)")
        s = {n: s[n] for n in sorted(need)}
        if syms is not None and s != syms:
            raise SystemExit("!! symboles de Model-TG différents entre 30-model-tg.json et 30-model-tg-st.json")
        syms, tgs[tid] = s, t
    return syms, tgs


def check_contract(stock, syms, tgs):
    """Le code de Model-TG à ces adresses est bien celui pour lequel generate.S est écrit ; renvoie, pour chaque
    version, les 6 octets que Model-TG écrit en KEY_CODE (jmp key_hook)."""
    if stock[KEY_CODE - BASE:KEY_CODE - BASE + 10].hex() != KEY_STOCK:
        raise SystemExit(f"!! l'accesseur {KEY_CODE:#x} n'est pas celui de l'OS 1.13")
    hooked = {}
    for tid, t in tgs.items():
        rt = build.payload_runtime(t, stock, None)
        dest = int(t["append"]["dest"], 16)

        def at(va, n, rt=rt, dest=dest):
            return rt[va - dest:va - dest + n]
        for n, head in TG_HEADS.items():
            if at(syms[n], len(head) // 2).hex() != head:
                raise SystemExit(f"!! {tid} : {n} ({syms[n]:#x}) n'est plus le code attendu ; relire generate.S")
        kh = syms["key_hook"]
        if (at(kh + 10, 4) != syms["rtg_on"].to_bytes(4, "big") or at(kh + 18, 6) != b"\x4a\xb9"
                + syms["sle_on"].to_bytes(4, "big")):
            raise SystemExit(f"!! {tid} : key_hook ne teste plus rtg_on puis sle_on en tête")
        go = syms["gm_opened"]
        if go + 2 + struct.unpack(">h", at(go + 2, 2))[0] != syms["mm_opened"] or go + 8 != syms["gm_done"]:
            raise SystemExit(f"!! {tid} : gm_opened ne pose plus mm_opened avant gm_done")
        for n in TG_ZERO:
            if any(at(syms[n], 4)):
                raise SystemExit(f"!! {tid} : {n} ({syms[n]:#x}) n'est pas à zéro au départ")
        if at(syms["gm_vname"], 17) != b"GranularMenuView\0":
            raise SystemExit(f"!! {tid} : gm_vname n'est plus « GranularMenuView »")
        lm = syms["lm_build"]                       # moveal gm_cur(pc),a0 : 207a d16
        reads = [va for va in range(lm, syms["gm_done"], 2) if at(va, 2) == b"\x20\x7a"
                 and va + 2 + struct.unpack(">h", at(va + 2, 2))[0] == syms["gm_cur"]]
        if len(reads) != 4:
            raise SystemExit(f"!! {tid} : lm_build ne lit plus gm_cur (le descripteur du menu) quatre fois")
        cur, _ = build.apply_writes(stock, [t])
        hooked[tid] = cur[KEY_CODE - BASE:KEY_CODE - BASE + 6]
        if hooked[tid] != struct.pack(">HI", 0x4ef9, kh):
            raise SystemExit(f"!! {tid} n'écrit plus jmp key_hook en {KEY_CODE:#x}")
    return hooked


def compile_generate(syms):
    """{section: (adresse, octets)} des caves, et les symboles."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        obj, elf = d / "gen.o", d / "gen.elf"
        defs = [f"-D{k}={syms[v]:#x}" for k, v in TG_DEFS.items()]
        gx.run([gx.CROSS + "gcc", "-mcpu=54418", *defs, "-c", str(SRC / "generate.S"), "-o", str(obj)])
        gx.run([gx.CROSS + "ld", "-T", str(SRC / "generate.ld"), "--no-warn-rwx-segments", "-o", str(elf),
                str(obj)])
        out = {}
        for line in gx.run([gx.CROSS + "nm", str(elf)]).splitlines():
            p = line.split()
            if len(p) == 3:
                out[p[2]] = int(p[0], 16)
        heads = subprocess.run([gx.CROSS + "objdump", "-h", str(elf)], capture_output=True, text=True,
                               check=True).stdout
        caves = {}
        for sec, _ in CAVES:
            b = d / (sec[1:] + ".bin")
            gx.run([gx.CROSS + "objcopy", "-O", "binary", "-j", sec, str(elf), str(b)])
            caves[sec] = (int(heads.split(sec + " ")[1].split()[2], 16), b.read_bytes())
        return caves, out


def build_writes(stock, syms, hooked):
    caves, gs = compile_generate(syms)
    writes, used = [], []
    for sec, mask in CAVES:
        addr, code = caves[sec]
        size, _, _, kept = sprites.MASKS[mask]
        if addr != mask or len(code) > size:
            raise SystemExit(f"!! {sec} : {len(code)} o à {addr:#x}, place {size} o à {mask:#x}")
        if stock[mask - BASE:mask - BASE + size] != stock[kept - BASE:kept - BASE + size]:
            raise SystemExit(f"!! le masque {mask:#x} n'est pas une copie du masque gardé {kept:#x}")
        old = stock[addr - BASE:addr - BASE + len(code)]
        writes += [{"off": addr - BASE, "old": old.hex(), "new": code.hex()}, sprites.redirect_write(mask)]
        used.append(len(code))
    if len(set(hooked.values())) != 1:
        raise SystemExit(f"!! les deux versions de Model-TG n'écrivent pas la même chose en {KEY_CODE:#x}")
    writes.append({"off": KEY_CODE - BASE, "old": hooked["model-tg"].hex(),
                   "new": struct.pack(">HI", 0x4ef9, gs["gen_key"]).hex()})
    writes.sort(key=lambda w: w["off"])
    return writes, gs, used


def make_tweak(tg, writes, gs, used):
    st = tg == "model-tg-st"
    return {
        "id": "generate-st" if st else "generate",
        "order": 49,
        "name": "Générateur de trigs euclidien / aléatoire sur SETTINGS + TRACK (Model-TG)"
                + (", avec les moteurs du Syntakt" if st else ""),
        "description": [
            "Idée et première version : DavidCaruso (firmware Model-TG-VA-DR-v1), réécrit pour ce dépôt.",
            "Tenir SETTINGS et appuyer sur TRACK ouvre la liste « Generate » (LEVEL/DATA : choisir une ligne, appuyer "
            "pour l'éditer ; SETTINGS ferme). Réglages : MOD RND/EUC, DNS (densité, %), HIT et ROT (coups et rotation "
            "euclidiens), NOT (notes tirées dans la gamme), KEY, SCL (13 gammes), OCT, RNG (octaves), VEL (vélocité "
            "tirée entre VMN et VMX).",
            "GEN (appui) réécrit toute la piste sélectionnée à l'ouverture, sur sa longueur (64 pas au plus) : trig "
            "posé ou effacé à chaque pas, note et vélocité remises à « aucune » si NOT ou VEL est sur OFF ; puis "
            "« Trigs: N ». Pas d'annulation. Réglages communs aux pistes, revenus aux défauts à chaque démarrage.",
            f"Pour {'la version de Model-TG combinée avec les moteurs du Syntakt (model-tg-st)' if st else 'Model-TG (model-tg)'} : "
            f"remplace son jmp key_hook en {KEY_CODE:#x}, appelle ses fonctions aux adresses de ses symboles. Code "
            f"et données dans sept masques de sprites 48x22 libérés (tools/sprites.py) : {' + '.join(map(str, used))} "
            f"= {sum(used)} o. Généré par tools/gen_generate.py, notes/56 §2.",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
        "requires": [tg],
        "symbols": {n: f"{gs[n]:#x}" for n in SYMBOLS},
        "writes": writes,
    }


def check_overlaps(tweaks):
    """Aucune écriture de ce tweak ne recouvre celle d'un tweak compatible, sauf le jmp de Model-TG en KEY_CODE,
    qu'il remplace (son « old » est l'écriture de Model-TG)."""
    cat = build.load_catalog()["model-cycles_OS1.13"][1]
    for t in tweaks:
        tg = cat[t["requires"][0]]
        mine = [(w["off"], w["off"] + len(bytes.fromhex(w["old"]))) for w in t["writes"]]
        for o in cat.values():
            if (o["id"] in OUTS_IDS or o["id"] in tg.get("conflicts", []) or o["id"] in t.get("conflicts", [])
                    or {tg["id"], t["id"]} & set(o.get("conflicts", []))):
                continue                               # jamais construits ensemble
            for w in o["writes"]:
                a, b = w["off"], w["off"] + len(bytes.fromhex(w["old"]))
                for lo, hi in mine:
                    if a < hi and lo < b and not (o["id"] == tg["id"] and lo == KEY_CODE - BASE):
                        raise SystemExit(f"!! {t['id']} recouvre {o['id']} en {a + BASE:#x} : déclarer un conflit")


OUTS_IDS = ("generate", "generate-st")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--check", action="store_true", help="vérifie que les JSON versionnés correspondent")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    if build.sha(stock) != json.loads((TW / "device.json").read_text(encoding="utf-8"))["section_sha256"]:
        raise SystemExit("!! ce n'est pas le MAIN OS 1.13 officiel")
    syms, tgs = tg_symbols()
    hooked = check_contract(stock, syms, tgs)
    writes, gs, used = build_writes(stock, syms, hooked)
    tweaks = [make_tweak(tg, writes, gs, used) for tg in OUTS]
    for t in tweaks:
        build.apply_writes(stock, [tgs[t["requires"][0]], t])    # les octets d'origine collent, par-dessus Model-TG
    check_overlaps(tweaks)
    print(f"  {len(CAVES)} masques : {' + '.join(map(str, used))} = {sum(used)} o ; gen_key {gs['gen_key']:#x}")
    ok = True
    for t, out in zip(tweaks, OUTS.values()):
        text = json.dumps(t, indent=1, ensure_ascii=False) + "\n"
        if args.check:
            same = out.exists() and out.read_text(encoding="utf-8") == text
            ok &= same
            print(f"  {out.name} {'est à jour' if same else 'NE CORRESPOND PAS (autre binutils ?)'}")
        else:
            out.write_text(text, encoding="utf-8")
            print(f"  écrit : {out.relative_to(HERE.parent)} ({len(t['writes'])} écritures)")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
