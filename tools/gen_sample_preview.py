#!/usr/bin/env python3
"""Génère tweaks/model-cycles_OS1.13/33-sample-preview.json et 33-sample-preview-st.json : écouter les samples dans
le navigateur, avec le Sampler de Model-TG (notes/46).

L'OS d'origine écoute les presets du navigateur : le preset sous le curseur est désigné, et la note suivante jouée
sur le pad de la piste active le joue à la place du son de la piste. Un fichier de sample n'est pas un preset : rien
n'est désigné, et le pad joue le son de la piste. Ce tweak désigne, sur une piste Sampler de Model-TG, un son qui
nomme le sample sous le curseur ; le pad le joue alors, après l'avoir chargé s'il n'est pas en mémoire.

tools/machines/sample_preview/ : sample_preview.S (trois accroches, la copie audio, les données), lié par
sample_preview.ld dans quatre masques de sprites 47x47 libérés (tools/sprites.py). Le code appelle des fonctions de
Model-TG et lit son état, aux adresses des « symbols » de 30-model-tg.json et 30-model-tg-st.json (les mêmes dans les
deux) : le tweak existe en deux fichiers aux écritures identiques, l'un pour chaque version de Model-TG (« requires »).

    python3 tools/gen_sample_preview.py --cycles model-cycles_OS1.13.syx [--check]
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

SRC = HERE / "machines" / "sample_preview"
TW = HERE.parent / "tweaks" / "model-cycles_OS1.13"
BASE = gx.BASE
# version de Model-TG -> fichier de ce tweak
OUTS = {"model-tg": TW / "33-sample-preview.json", "model-tg-st": TW / "33-sample-preview-st.json"}
TG_FILES = {"model-tg": TW / "30-model-tg.json", "model-tg-st": TW / "30-model-tg-st.json"}
# sections liées -> masque 47x47 libéré qui les reçoit (sample_preview.ld)
# (ceux aussi de chord-keys, qui exclut Model-TG : déclaré dans « conflicts »)
CAVES = ((".cave1", 0x40183118), (".cave2", 0x40185018), (".cave3", 0x40185968), (".cave4", 0x40185c58))
# -D de sample_preview.S -> symbole de Model-TG
TG_DEFS = {"TG_TOK_OF": "tok_of", "TG_SOUND_OBJ": "sound_obj", "TG_ENSURE_LOADED": "ensure_loaded",
           "TG_SLOT_HASH": "slot_hash", "TG_PD_MODE": "pd_mode", "TG_LD_BUSY": "ld_busy"}
# Contrat avec Model-TG v1.1.0 (vérifié dans sa charge utile) : début des fonctions appelées, données à zéro au départ,
# et pad_load_hook, l'accroche de Model-TG en 0x4008171e que pv_note remplace, qui ne fait que rejouer les deux
# instructions déplacées (link.w %fp,#-104 ; moveq #127,%d0) puis jmp 0x40081724.
TG_HEADS = {"tok_of": "4feffff448d7000e", "sound_obj": "4fefffe848d70c3c", "ensure_loaded": "4feffff048d7041c",
            "pad_load_hook": "4e56ff98707f4ef940081724"}
TG_ZERO = {"slot_hash": 256, "pd_mode": 4, "ld_busy": 4}
NOTE_ON = 0x4008171e                                   # entrée de la note jouée en direct ; Model-TG y met un jmp
# (adresse, octets d'origine vérifiés, nombre d'octets réécrits, accroche, rôle)
HOOKS = (
    (0x4005910e, "4aaa0030670c2002068000000093" "42b40c00", 8, "copy",
     "boucle des événements audio : tst.l 48(a2) ; beq.s ; move.l d2,d0 ; addi.l #147,d0 ; clr.l (a4,d0.l*4) "
     "-> jsr pv_copy ; bra.s 0x40059120"),
    (0x400a6426, "4eb9400a3052", 6, "parse",
     "navigateur, écoute d'un preset : jsr 0x400a3052 (lit le preset) -> jsr pv_parse"),
)
SYMBOLS = ("pv_parse", "pv_note", "pv_copy", "pv_tab", "pv_src", "pv_fail", "pv_failp")   # pour tools/emu/test_sample_preview.py


def tg_symbols():
    """Symboles de Model-TG utilisés, identiques dans les deux versions, et la charge utile de chacune."""
    syms, tgs = None, {}
    for tid, f in TG_FILES.items():
        t = json.loads(f.read_text(encoding="utf-8"))
        s = {n: int(v, 16) for n, v in t.get("symbols", {}).items()}
        need = set(TG_DEFS.values()) | set(TG_HEADS)
        if need - set(s):
            raise SystemExit(f"!! {f.name} ne porte pas les symboles {sorted(need - set(s))} (tools/gen_model_tg.py)")
        s = {n: s[n] for n in sorted(need)}
        if syms is not None and s != syms:
            raise SystemExit("!! symboles de Model-TG différents entre 30-model-tg.json et 30-model-tg-st.json")
        syms, tgs[tid] = s, t
    return syms, tgs


def check_contract(stock, syms, tgs):
    """Le code de Model-TG à ces adresses est bien celui pour lequel sample_preview.S est écrit ; renvoie, pour chaque
    version, les 6 octets que Model-TG écrit en NOTE_ON."""
    hooked = {}
    for tid, t in tgs.items():
        rt = build.payload_runtime(t, stock, None)
        dest = int(t["append"]["dest"], 16)
        for n, head in TG_HEADS.items():
            h = bytes.fromhex(head)
            if rt[syms[n] - dest:syms[n] - dest + len(h)] != h:
                raise SystemExit(f"!! {tid} : {n} ({syms[n]:#x}) n'est plus le code attendu ; relire notes/46 §4")
        for n, size in TG_ZERO.items():
            if any(rt[syms[n] - dest:syms[n] - dest + size]):
                raise SystemExit(f"!! {tid} : {n} ({syms[n]:#x}) n'est pas à zéro au départ")
        uses = tg_uses(rt, dest, syms)
        if uses["pd_mode"] != 1 or uses["ld_busy"] < 2:
            raise SystemExit(f"!! {tid} : pd_mode / ld_busy ne sont plus ceux du préchargeur et de led_hook ({uses})")
        cur, _ = build.apply_writes(stock, [t])
        hooked[tid] = cur[NOTE_ON - BASE:NOTE_ON - BASE + 6]
        if hooked[tid] != struct.pack(">HI", 0x4ef9, syms["pad_load_hook"]):
            raise SystemExit(f"!! {tid} n'écrit plus jmp pad_load_hook en {NOTE_ON:#x}")
    return hooked


def tg_uses(rt, dest, syms):
    """Que pd_mode et ld_busy sont bien les variables du chargeur de Model-TG, dans sa charge utile rt (à dest) :
    pl_step fait move.l %d0,pd_mode ; … ; jsr ensure_loaded ; clr.l pd_mode (à moins de 64 o), et led_hook prend
    ld_busy par lea (d16,%pc) (deux fois : test-and-set, puis remise à zéro). Renvoie le nombre de chaque."""
    def at(va, n):
        return rt[va - dest:va - dest + n]

    def call_to(va):                                   # jsr (d16,pc), bsr.w ou jsr abs.l vers ensure_loaded
        op = at(va, 2)
        if op in (b"\x4e\xba", b"\x61\x00"):
            return va + 2 + struct.unpack(">h", at(va + 2, 2))[0] == syms["ensure_loaded"]
        return op == b"\x4e\xb9" and int.from_bytes(at(va + 2, 4), "big") == syms["ensure_loaded"]
    pd = syms["pd_mode"].to_bytes(4, "big")
    code = range(dest, dest + len(rt) - 6, 2)
    sets = [va for va in code if at(va, 6) == b"\x23\xc0" + pd]
    clrs = [va for va in code if at(va, 6) == b"\x42\xb9" + pd]
    pl = [a for a in sets for b in clrs if a < b < a + 64 and any(call_to(va) for va in range(a, b, 2))]
    lea = [va for va in code if at(va, 2) == b"\x41\xfa"
           and va + 2 + struct.unpack(">h", at(va + 2, 2))[0] == syms["ld_busy"]]
    return {"pd_mode": len(pl), "ld_busy": len(lea)}


def compile_preview(syms):
    """{section: (adresse, octets)} des quatre caves, et les symboles."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        obj, elf = d / "pv.o", d / "pv.elf"
        defs = [f"-D{k}={syms[v]:#x}" for k, v in TG_DEFS.items()]
        gx.run([gx.CROSS + "gcc", "-mcpu=54418", *defs, "-c", str(SRC / "sample_preview.S"), "-o", str(obj)])
        gx.run([gx.CROSS + "ld", "-T", str(SRC / "sample_preview.ld"), "--no-warn-rwx-segments", "-o", str(elf),
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
    caves, pv = compile_preview(syms)
    shared = stock[sprites.SHARED_47 - BASE:sprites.SHARED_47 - BASE + 376]
    writes, used = [], []
    for sec, mask in CAVES:
        addr, code = caves[sec]
        size = sprites.MASKS[mask][0]
        if addr != mask or len(code) > size:
            raise SystemExit(f"!! {sec} : {len(code)} o à {addr:#x}, place {size} o à {mask:#x}")
        old = stock[addr - BASE:addr - BASE + len(code)]
        if stock[mask - BASE:mask - BASE + size] != shared:
            raise SystemExit(f"!! le masque {mask:#x} n'est pas une copie du masque partagé {sprites.SHARED_47:#x}")
        writes += [{"off": addr - BASE, "old": old.hex(), "new": code.hex()}, sprites.redirect_write(mask)]
        used.append(len(code))
    target = {"copy": struct.pack(">HIH", 0x4eb9, pv["pv_copy"], 0x600a),     # bra.s 0x40059120
              "parse": struct.pack(">HI", 0x4eb9, pv["pv_parse"])}
    for va, old_hex, n, what, _ in HOOKS:
        old = bytes.fromhex(old_hex)
        if stock[va - BASE:va - BASE + len(old)] != old:
            raise SystemExit(f"!! octets d'origine inattendus en {va:#x}")
        if len(target[what]) != n:
            raise SystemExit(f"!! accroche {what} : {len(target[what])} o au lieu de {n}")
        writes.append({"off": va - BASE, "old": old[:n].hex(), "new": target[what].hex()})
    if len(set(hooked.values())) != 1:
        raise SystemExit(f"!! les deux versions de Model-TG n'écrivent pas la même chose en {NOTE_ON:#x}")
    writes.append({"off": NOTE_ON - BASE, "old": hooked["model-tg"].hex(),
                   "new": struct.pack(">HI", 0x4ef9, pv["pv_note"]).hex()})
    writes.sort(key=lambda w: w["off"])
    return writes, pv, used


def make_tweak(tg, writes, pv, used):
    st = tg == "model-tg-st"
    return {
        "id": "sample-preview-st" if st else "sample-preview",
        "order": 33,
        "name": "Écoute des samples (Model-TG)" + (", avec les moteurs du Syntakt" if st else ""),
        "description": [
            "Navigateur de presets d'une piste Sampler de Model-TG : le pad de la piste (ou ses touches en mode "
            "clavier) joue le sample sous le curseur, comme l'OS d'origine joue le preset sous le curseur.",
            "Un sample qui n'est pas en mémoire est chargé au premier appui, seulement dans la place libre ou à la "
            "place de samples que le projet n'utilise pas. S'il ne se charge pas, l'appui ne joue rien.",
            "Les presets du Sampler qui gardent leur sample (nom « SMP » + empreinte) devraient aussi faire entendre "
            "ce sample plutôt que celui de la piste (prouvé en émulation pour le son, pas encore sur la machine).",
            f"Pour {'la version de Model-TG combinée avec les moteurs du Syntakt (model-tg-st)' if st else 'Model-TG (model-tg)'} ; "
            f"appelle ses fonctions aux adresses de ses symboles. Code dans quatre masques de sprites 47x47 libérés "
            f"(tools/sprites.py) : {' + '.join(map(str, used))} o. Généré par tools/gen_sample_preview.py, notes/46.",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
        "requires": [tg],
        "conflicts": ["chord-keys"],                   # mêmes masques ; chord-keys exclut déjà Model-TG
        "symbols": {n: f"{pv[n]:#x}" for n in SYMBOLS},
        "writes": writes,
    }


def check_overlaps(tweaks):
    """Aucune écriture de ce tweak ne recouvre celle d'un tweak compatible, sauf le jmp de Model-TG en NOTE_ON,
    qu'il remplace (son « old » est l'écriture de Model-TG)."""
    cat = build.load_catalog()["model-cycles_OS1.13"][1]
    for t in tweaks:
        tg = cat[t["requires"][0]]
        mine = [(w["off"], w["off"] + len(bytes.fromhex(w["old"]))) for w in t["writes"]]
        for o in cat.values():
            if (o["id"] in ("sample-preview", "sample-preview-st") or o["id"] in tg.get("conflicts", [])
                    or o["id"] in t.get("conflicts", []) or {tg["id"], t["id"]} & set(o.get("conflicts", []))):
                continue                               # jamais construits ensemble
            for w in o["writes"]:
                a, b = w["off"], w["off"] + len(bytes.fromhex(w["old"]))
                for lo, hi in mine:
                    if a < hi and lo < b and not (o["id"] == tg["id"] and lo == NOTE_ON - BASE):
                        raise SystemExit(f"!! {t['id']} recouvre {o['id']} en {a + BASE:#x} : déclarer un conflit")


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
    writes, pv, used = build_writes(stock, syms, hooked)
    tweaks = [make_tweak(tg, writes, pv, used) for tg in OUTS]
    for t in tweaks:
        build.apply_writes(stock, [tgs[t["requires"][0]], t])    # les octets d'origine collent, par-dessus Model-TG
    check_overlaps(tweaks)
    print("  " + tweaks[0]["description"][-1])
    ok = True
    for t, out in zip(tweaks, OUTS.values()):
        text = json.dumps(t, indent=1) + "\n"
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
