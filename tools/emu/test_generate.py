#!/usr/bin/env python3
"""Preuve du générateur de trigs « Generate » sur SETTINGS + TRACK (tweaks/model-cycles_OS1.13/49-generate.json
pour Model-TG, 49-generate-st.json pour sa version avec les moteurs du Syntakt ; idée de DavidCaruso).

Le vrai code de l'OS, de Model-TG et du tweak, exécuté (Unicorn) sur deux images construites depuis le .syx
officiel : l'« origine » = les mêmes tweaks sans Generate (Model-TG seul par défaut), l'image modifiée = avec.
Seuls sont remplacés : l'allocateur (malloc 0x40080064, free 0x4008026a : un tas factice), le dessin (0x40071a04,
0x40072260, 0x40072080 : le texte est relevé à l'entrée de 0x400f85bc), la présentation d'une vue (0x400d0974,
0x400060d8, 0x4007700e, 0x400cf23c : notées), le pattern en cours (0x400cfd0e, 0x4006a96c) et la piste sélectionnée
(0x40012412). Le projet est un singleton factice (*0x40fe4228) ; ses six objets « piste » (le vrai 0x4000f208 puis
le vrai 0x4000cfcc les trouvent : projet + 5 192 + 732 x pattern + 112 + 88 x piste) ont une vtable factice :
vtable[40] rend leurs 722 o de données (drapeaux des pas +0, vélocités +128, notes +580, longueur +713),
vtable[16] (signal de modification) et vtable[60] sont comptés.

  1. Écritures : octets d'origine (l'OS d'origine pour les masques et leurs constantes, le jmp key_hook de Model-TG en
     0x4007240c) ; l'image ne diffère de l'origine que par ces écritures ; aucune ne recouvre un autre tweak (du jeu
     --with, et du catalogue sauf ceux qui ne vont jamais avec) sauf ce jmp ; refusé seul et avec l'autre Model-TG,
     accepté avec le sien ; le contrat avec Model-TG (gen_generate.check_contract) ; l'état dans les octets écrits.
  2. L'accord, par le vrai 0x4007240c (key_hook de Model-TG derrière) : SETTINGS puis TRACK ouvre le menu (gm_track,
     gm_cur = gen_desc, 13 lignes identiques sur la pile, lm_build atteint une fois), l'appui est avalé (d0 = 0,
     bit 3 levé, mod_used), ses relectures, ses répétitions et son relâchement (relu) aussi, et le relâchement de
     SETTINGS n'ouvre plus le Config Menu ; l'origine rend TRACK (2) à chaque lecture. Pour toute autre touche (codes
     0 à 40, drapeaux et SETTINGS tenu ou pas), et pour TRACK seul, avec la page Retrig ou l'éditeur de tranches,
     relâchement ou répétition non avalés : key_hook est atteint avec la même pile que dans l'origine et rien n'est
     écrit en mémoire (sauf gen_ev remis à 0 par un appui frais de TRACK). Accord refusé (interface pas prête, en
     interruption, piste >= 6) : TRACK passe comme dans l'origine ; liste de Model-TG déjà ouverte (gm_live) : accord
     avalé sans nouveau menu.
  3. Le menu, par le vrai lm_build de Model-TG : 13 éléments de menu de l'OS (vtable 0x40103470), titre « Generate »,
     nom de vue de Model-TG, numéro de ligne en +8, nos quatre fermetures ; puis par les méthodes de l'OS de chaque
     élément : libellés (0x40073236), valeurs dessinées (0x40073274 -> gm_val), bornes des rotations (0x400732b6),
     appui (0x4007329c) : édition basculée par l'invocateur de Model-TG (lignes 1 à 12), génération (GEN).
  4. La génération (gen_go par l'appui de GEN) sur les vrais accesseurs de la grille, comparée pas à pas à une
     référence Python de l'algorithme (forme fermée de l'euclidien, densité aléatoire, 13 gammes, octaves, étendue,
     bornes de vélocité échangées, NOT / VEL sur OFF) : trigs, notes, vélocités, pas au-delà de la longueur intacts,
     autres pistes intactes, état du xorshift, texte « Trigs: N » passé à show_popup (le vrai vsprintf), registres
     d2-d7/a2-a6 rendus.

Durée : 2 min environ par version de Model-TG.

    python3 tools/emu/test_generate.py --cycles model-cycles_OS1.13.syx \\
        [--with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max \\
         --syntakt Syntakt_OS1.42.syx]
"""
import argparse
import json
import pathlib
import random
import struct
import sys

from unicorn import UcError, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import gen_generate as G            # noqa: E402
import test_model_tg as TM          # noqa: E402
import test_sdvintage as T          # noqa: E402

TW = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13"
BASE = build.BASE
FAIL = []
M32 = 0xffffffff

# --- l'OS (1.13) ----------------------------------------------------------------------------------------------------
KEY_CODE = G.KEY_CODE             # accesseur du code d'un KeyEvent (moveal 4(sp),a0 ; movel 12(a0),d0 ; rts)
UI_READY = 0x40fe4178
PROJ_PTR = 0x40fe4228             # singleton du projet (0x400cf866)
CLOCK = 0x8000184c                # heure musicale
MALLOC, FREE = 0x40080064, 0x4008026a
FORMAT_STRING = 0x400f980c        # String(this, texte, tag)
TINYSTR_WRAP = 0x400f85bc         # (String, texte), dans gm_val
DRAW = (0x40071a04, 0x40072260, 0x40072080)
ROOT, VIEWMGR, PRESENT, RELEASE = 0x400d0974, 0x400060d8, 0x4007700e, 0x400cf23c
ITEM_VT = 0x40103470              # vtable des éléments de menu (MENUITEM_CTOR 0x400734b0)
ITEM_LABEL, ITEM_DRAW, ITEM_TURN, ITEM_PRESS = 0x40073236, 0x40073274, 0x400732b6, 0x4007329c
SELTRACK = 0x40012412
CUR_PAT_A, CUR_PAT_B = 0x400cfd0e, 0x4006a96c
VSPRINTF = 0x400005cc
KEY_TRACK, KEY_SETTINGS = 2, 13
# --- le banc --------------------------------------------------------------------------------------------------------
STOP = 0x40780000                 # mcengine.STOP
CALL_SP = 0x9000e000
STACK_POISON = 0x3000
FIX = 0x93000000                  # objets du banc (0x93000000..0x95000000)
PROJ = FIX
PATTERN = 3
OBJS = PROJ + 5192 + 732 * PATTERN + 112         # objet « piste » 0 ; les suivants tous les 88 o
VT = FIX + 0x10000                # vtables factices des pistes (une par piste, 0x40 o)
DATA = FIX + 0x11000              # données des pistes (0x400 o chacune)
EV = FIX + 0x20000                # événements de touche (0x20 o chacun)
OUT = FIX + 0x30000               # String de sortie des libellés
ITEM = FIX + 0x31000              # élément de menu factice (appels directs de gen_press)
REP = FIX + 0x32000               # représentation de chaîne rendue par 0x400f85bc (compte de références en +8)
HEAP0 = 0x94000000
CALLEE = [getattr(mk, f"UC_M68K_REG_D{i}") for i in range(2, 8)] + \
         [getattr(mk, f"UC_M68K_REG_A{i}") for i in range(2, 7)]
CALLEE_VALS = [0x22220002, 0x33330003, 0x44440004, 0x55550005, 0x66660006, 0x77770007,
               0x93f00000, 0x93f10000, 0x93f20000, 0x93f30000, 0x93f40000]
# --- Generate ---------------------------------------------------------------------------------------------------------
LABELS = ["MOD", "DNS", "HIT", "ROT", "NOT", "KEY", "SCL", "OCT", "RNG", "VEL", "VMN", "VMX", "GEN"]
DEFAULTS = [0, 50, 4, 0, 0, 0, 0, 4, 1, 0, 64, 127, 0]
MINS = [0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0]
MAXS = [1, 100, 64, 63, 1, 11, 12, 8, 4, 1, 127, 127, 0]
KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
SCL_NAMES = ["MAJ", "MIN", "DOR", "PHR", "LYD", "MIX", "LOC", "HMI", "MMI", "PMA", "PMI", "BLU", "CHR"]
# degrés (demi-tons au-dessus de la tonique), écrits à la main : les masques de generate.S doivent les redonner
SCALES = [(0, 2, 4, 5, 7, 9, 11), (0, 2, 3, 5, 7, 8, 10), (0, 2, 3, 5, 7, 9, 10), (0, 1, 3, 5, 7, 8, 10),
          (0, 2, 4, 6, 7, 9, 11), (0, 2, 4, 5, 7, 9, 10), (0, 1, 3, 5, 6, 8, 10), (0, 2, 3, 5, 7, 8, 11),
          (0, 2, 3, 5, 7, 9, 11), (0, 2, 4, 7, 9), (0, 3, 5, 7, 10), (0, 3, 5, 6, 7, 10), tuple(range(12))]
NAMES = {0: ["RND", "EUC"], 4: ["OFF", "ON"], 5: KEYS, 6: SCL_NAMES, 9: ["OFF", "ON"], 12: ["GO"]}
MOD, DNS, HIT, ROT, NOT, KEY, SCL, OCT, RNG, VEL, VMN, VMX = range(12)


def check(ok, msg):
    print(("  ok    " if ok else "  ECHEC ") + msg, flush=True)
    if not ok:
        FAIL.append(msg)


# --- la référence ---------------------------------------------------------------------------------------------------
def xorshift(x):
    x ^= (x << 13) & M32
    x ^= x >> 17
    x ^= (x << 5) & M32
    return x


def reference(st, rng, clock, length):
    """Ce que GEN doit écrire : [(trig, note, vélocité)] pour les pas 0..n-1 (-1 : aucune), l'état final du
    xorshift, le nombre de trigs. Euclidien par la forme fermée : trig si ((pas - ROT) mod n) x k mod n < k."""
    n = min(length, 64)
    if n <= 0:
        return None, rng, 0
    rng = (rng + clock + 0x9e3779b9) & M32 or 1
    notes = []
    if st[NOT]:
        base = 12 * (st[OCT] + 1) + st[KEY]
        notes = [base + d for d in range(12 * st[RNG] + 1) if d % 12 in SCALES[st[SCL]] and base + d <= 127]
    k, r = min(st[HIT], n), st[ROT] % n
    out, total = [], 0

    def rndn(m):
        nonlocal rng
        rng = xorshift(rng)
        return ((rng >> 16) * m) >> 16
    for s in range(n):
        on = rndn(100) < st[DNS] if st[MOD] == 0 else ((s - r) % n) * k % n < k
        note = notes[rndn(len(notes))] if on and st[NOT] else -1
        vel = -1
        if on and st[VEL]:
            lo, hi = sorted((st[VMN], st[VMX]))
            vel = rndn(hi - lo + 1) + lo
        out.append((int(on), note, vel))
        total += on
    return out, rng, total


# --- les images -----------------------------------------------------------------------------------------------------
class Variant:
    """Une version de Model-TG et les tweaks qui l'accompagnent : l'image d'origine et l'image modifiée."""

    def __init__(self, stock, ids, by_id, syntakt_file):
        load = (lambda i: json.loads(by_id[i].read_text(encoding="utf-8")))
        self.tweaks = sorted((load(i) for i in ids), key=lambda t: t["order"])
        st = "model-tg-st" in ids
        self.gt = load("generate-st" if st else "generate")
        self.tg = next(t for t in self.tweaks if t["id"] in ("model-tg", "model-tg-st"))
        self.label = ", ".join(t["id"] for t in self.tweaks)
        pl, _ = build.build_payload(self.tweaks, stock, syntakt_file)
        self.base = bytes(build.apply_writes(stock, self.tweaks)[0]) + pl
        self.img = bytes(build.apply_writes(stock, sorted(self.tweaks + [self.gt], key=lambda t: t["order"]))[0]) + pl
        self.end = BASE + len(stock) + self.tg["append"]["size"]
        syn = [t for t in self.tweaks if t.get("append", {}).get("syntakt")]
        mac = [t for t in self.tweaks if t["id"] in ("macro", "macro-tg")]
        self.payload = None
        if syn:
            import syntakt
            self.payload = (int(syn[0]["append"]["dest"], 16),
                            build.payload_runtime(syn[0], stock, syntakt.dsp_image(syntakt_file)))
        elif mac:
            self.payload = (int(mac[0]["append"]["dest"], 16), build.payload_runtime(mac[0], stock, None))
        self.tgs = {n: int(v, 16) for n, v in self.tg["symbols"].items()}
        self.gs = {n: int(v, 16) for n, v in self.gt["symbols"].items()}


class Rig:
    """Un Model:Cycles réduit aux touches, à la liste de Model-TG et aux pistes du pattern en cours."""

    def __init__(self, v, img, sel=2):
        self.v, self.sel = v, sel
        e = self.e = TM.engine(img, end=v.end, payload=v.payload)
        uc = self.uc = e.uc
        uc.mem_map(FIX, 0x02000000)
        self.heap, self.errors = HEAP0, []
        self.calls = {}
        self.texts, self.popups, self.labels, self.presented = [], [], [], []
        self.notify, self.v60 = 0, 0
        for addr, fn in {MALLOC: self._new, FREE: lambda a: 0, SELTRACK: lambda a: self.sel,
                         CUR_PAT_A: lambda a: 0x12345678, CUR_PAT_B: lambda a: PATTERN,
                         DRAW[0]: lambda a: 0, DRAW[1]: lambda a: 0, DRAW[2]: lambda a: 0,
                         TINYSTR_WRAP: self._wrap, ROOT: lambda a: 0x55550000, VIEWMGR: lambda a: 0x55560000,
                         PRESENT: self._present, RELEASE: lambda a: 0,
                         FORMAT_STRING: self._fmt, v.tgs["show_popup"]: self._popup,
                         VT + 0x400: self._notify, VT + 0x404: self._v60}.items():
            self.stub(addr, fn)
        self.w32(UI_READY, 1)
        self.w32(PROJ_PTR, PROJ)
        self.w32(CLOCK, 0x31415926)
        for t in range(6):                       # six pistes : vtable[40] -> données, [16] et [60] comptés
            o, vt, d = OBJS + 88 * t, VT + 0x40 * t, DATA + 0x400 * t
            uc.mem_write(o, bytes(88))
            self.w32(o, vt)
            self.w32(o + 56, t)
            self.w32(vt + 16, VT + 0x400)
            self.w32(vt + 60, VT + 0x404)
            self.w32(vt + 40, vt + 0x30)
            uc.mem_write(vt + 0x30, b"\x20\x3c" + struct.pack(">I", d) + b"\x4e\x75")
        uc.mem_write(VT + 0x400, b"\x4e\x75\x4e\x75\x4e\x75")
        self.calls_seen = []

    # -- mémoire et appels --
    def w32(self, a, v):
        self.uc.mem_write(a, struct.pack(">I", v & M32))

    def r32(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def mem(self, a, n):
        return bytes(self.uc.mem_read(a, n))

    def cstr(self, a, n=40):
        return self.mem(a, n).split(b"\0")[0].decode("latin-1")

    def stub(self, addr, fn):
        """fn(args) -> valeur rendue dans d0, ou None : le vrai code s'exécute (l'appel est seulement noté)."""
        def hook(uc, a, size, ud):
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            args = struct.unpack(">6I", uc.mem_read(sp + 4, 24))
            self.calls.setdefault(addr, []).append(args)
            r = fn(args)
            if r is None:
                return
            uc.reg_write(mk.UC_M68K_REG_D0, r & M32)
            uc.reg_write(mk.UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        self.uc.hook_add(UC_HOOK_CODE, hook, begin=addr, end=addr)

    def call(self, fn, *args, sr=0x2000, regs=False, a0=None, count=20_000_000):
        uc = self.uc
        uc.reg_write(mk.UC_M68K_REG_SR, sr)
        frame = struct.pack(">I", STOP) + b"".join(struct.pack(">I", a & M32) for a in args)
        uc.mem_write(CALL_SP - STACK_POISON, b"\xa5" * (STACK_POISON - len(frame)))
        uc.mem_write(CALL_SP - len(frame), frame)
        uc.reg_write(mk.UC_M68K_REG_A7, CALL_SP - len(frame))
        if regs:
            for r, val in zip(CALLEE, CALLEE_VALS):
                uc.reg_write(r, val)
        if a0 is not None:
            uc.reg_write(mk.UC_M68K_REG_A0, a0)
        try:
            uc.emu_start(fn, STOP, count=count)
        except UcError as ex:
            self.errors.append((hex(fn), hex(uc.reg_read(mk.UC_M68K_REG_PC)), str(ex)))
        if uc.reg_read(mk.UC_M68K_REG_PC) != STOP:
            self.errors.append((hex(fn), hex(uc.reg_read(mk.UC_M68K_REG_PC)), "n'est pas revenu"))
        self.regs_after = [uc.reg_read(r) for r in CALLEE]
        return uc.reg_read(mk.UC_M68K_REG_D0)

    def clean(self):
        return not self.errors and not self.e.unmapped

    # -- interceptions --
    def _new(self, a):
        p, n = self.heap, (a[0] + 15) & ~15
        self.heap += n
        self.uc.mem_write(p, b"\xa5" * n)
        return p

    def _wrap(self, a):                          # gm_val : (String, texte) -> le texte dessiné
        self.texts.append(self.cstr(a[1]))
        self.w32(a[0], REP)                      # une représentation factice, jamais libérée (compte élevé)
        self.w32(REP + 8, 0x10000000)
        return a[0]

    def _fmt(self, a):                           # String(this, texte, tag) : noté, le vrai code construit
        self.labels.append(self.cstr(a[1]) if a[1] else None)

    def _present(self, a):
        self.presented.append(a)
        return 0

    def _popup(self, a):                         # show_popup de Model-TG : le texte, rien n'est affiché
        self.popups.append(self.cstr(a[0]))
        return 0

    def _notify(self, a):
        self.notify += 1
        return 0

    def _v60(self, a):
        self.v60 += 1
        return 0

    # -- Generate --
    def settings(self, st=None):
        if st is not None:
            self.uc.mem_write(self.v.gs["gen_set"], bytes(st))
        return list(self.mem(self.v.gs["gen_set"], 13))

    def event(self, i, code, flags):
        a = EV + 0x20 * i
        self.uc.mem_write(a, bytes(0x20))
        self.w32(a + 12, code)
        self.w32(a + 16, flags)
        return a

    def key(self, ev, sr=0x2000):
        return self.call(KEY_CODE, ev, sr=sr)


# --- 1. écritures ---------------------------------------------------------------------------------------------------
def writes_tests(stock, v):
    gt, tg = v.gt, v.tg
    tg_img = build.apply_writes(stock, [tg])[0]
    jmp_tg = struct.pack(">HI", 0x4ef9, v.tgs["key_hook"])
    ok_old, spans = True, []
    for w in gt["writes"]:
        off, old, new = w["off"], bytes.fromhex(w["old"]), bytes.fromhex(w["new"])
        spans.append((off, off + len(new)))
        ref = tg_img if off + BASE == KEY_CODE else stock
        ok_old &= ref[off:off + len(old)] == old and len(old) == len(new)
    check(ok_old, f"{gt['id']} : {len(gt['writes'])} écritures, octets d'origine = l'OS d'origine (masques, "
                  f"constantes des sprites) et le jmp key_hook de Model-TG en {KEY_CODE:#x}")
    at = {w["off"] + BASE: bytes.fromhex(w["new"]) for w in gt["writes"]}
    check(stock[KEY_CODE - BASE:KEY_CODE - BASE + 10].hex() == G.KEY_STOCK
          and tg_img[KEY_CODE - BASE:KEY_CODE - BASE + 6] == jmp_tg
          and at.get(KEY_CODE) == struct.pack(">HI", 0x4ef9, v.gs["gen_key"]),
          f"accroche : {KEY_CODE:#x} moveal/movel/rts d'origine -> jmp key_hook (Model-TG) -> jmp gen_key")
    masks = [m for _, m in G.CAVES]
    import sprites
    redir = all(at.get(sprites.MASKS[m][1]) == sprites.MASKS[m][3].to_bytes(4, "big") for m in masks)
    inside = all(any(m - BASE <= lo and hi <= m - BASE + 192 for m in masks) for lo, hi in spans
                 if lo + BASE not in [sprites.MASKS[m][1] for m in masks] and lo + BASE != KEY_CODE)
    check(redir and inside and len(gt["writes"]) == 2 * len(masks) + 1,
          f"code et données dans {len(masks)} masques 48x22 libérés, chacun redirigé vers la copie gardée "
          f"{sprites.MASKS[masks[0]][3]:#x} dans le même tweak")
    dif = [k for k in range(len(v.base)) if v.base[k] != v.img[k]] if len(v.base) == len(v.img) else None
    check(dif is not None and all(any(lo <= k < hi for lo, hi in spans) for k in dif),
          f"l'image modifiée ne diffère de l'origine que dans ces écritures ({len(dif or [])} octets)")
    mine = [(w["off"], w["off"] + len(bytes.fromhex(w["old"]))) for w in gt["writes"]]

    def overlaps(others):
        bad = []
        for o in others:
            for w in o["writes"]:
                a, b = w["off"], w["off"] + len(bytes.fromhex(w["old"]))
                for lo, hi in mine:
                    if a < hi and lo < b and not (o["id"] == tg["id"] and lo == KEY_CODE - BASE):
                        bad.append(f"{o['id']}@{a + BASE:#x}")
        return bad
    bad = overlaps(v.tweaks)
    check(not bad, f"aucun recouvrement avec {v.label} sauf le jmp de Model-TG en {KEY_CODE:#x} {bad[:4]}")
    cat = build.load_catalog()["model-cycles_OS1.13"][1]
    never = [o["id"] for o in cat.values() if o["id"] in G.OUTS_IDS
             or o["id"] in tg.get("conflicts", []) or o["id"] in gt.get("conflicts", [])
             or {tg["id"], gt["id"]} & set(o.get("conflicts", []))]
    compat = [o for o in cat.values() if o["id"] not in never]
    bad = overlaps(compat)
    check(not bad, f"aucun recouvrement avec les {len(compat)} tweaks du catalogue compatibles avec {tg['id']} + "
                   f"{gt['id']} (sauf ce jmp ; écartés : {len(never)} tweaks qui ne vont jamais avec) {bad[:4]}")
    other = "model-tg" if tg["id"] == "model-tg-st" else "model-tg-st"
    refused = []
    for combo in ([gt], [cat[other], gt]):
        try:
            build.check_conflicts(combo)
            refused.append(False)
        except SystemExit:
            refused.append(True)
    try:
        build.check_conflicts([tg, gt])
        accepted = True
    except SystemExit:
        accepted = False
    try:
        build.apply_writes(stock, [gt])
        applies = True
    except SystemExit:
        applies = False
    check(all(refused) and accepted and not applies,
          f"build : {gt['id']} refusé seul et avec {other} (requires {gt['requires']}), accepté avec {tg['id']} ; "
          f"ses octets d'origine refusent l'OS sans Model-TG")
    syms, tgs = G.tg_symbols()
    try:
        G.check_contract(stock, syms, tgs)
        contract = True
    except SystemExit:
        contract = False
    check(contract and all(v.tgs[n] == syms[n] for n in syms),
          "contrat avec Model-TG (les deux versions, mêmes adresses) : key_hook teste rtg_on et sle_on en tête, "
          "gran_menu_open pose le cadre de lm_build et gm_done, gm_opened pose mm_opened, lm_build lit gm_cur, "
          "début de gm_live, gm_lab, gm_val, new_slot2_invoker, show_popup ; variables à zéro au départ")
    s = v.gs
    ram = (s["gen_set"], s["gen_desc"] + 16)
    st = list(v.img[ram[0] - BASE:ram[0] - BASE + 13])
    desc = struct.unpack(">4I", v.img[s["gen_desc"] - BASE:s["gen_desc"] - BASE + 16])
    check(any(lo <= ram[0] - BASE and ram[1] - BASE <= hi for lo, hi in spans) and st == DEFAULTS
          and struct.unpack(">I", v.img[s["gen_rng"] - BASE:s["gen_rng"] - BASE + 4])[0] == 0x2545f491
          and desc[:3] == (s["gen_title"], v.tgs["gm_vname"], 13)
          and v.img[s["gen_title"] - BASE:s["gen_title"] - BASE + 9] == b"Generate\0",
          f"état dans les octets écrits, valeurs de l'image (rien n'est sauvé) : réglages {st}, xorshift "
          f"0x2545f491, descripteur {{« Generate », « GranularMenuView », 13, lignes}}")


# --- 2. l'accord ----------------------------------------------------------------------------------------------------
def chord_tests(v):
    tgs, gs = v.tgs, v.gs
    rigs = {"origine": Rig(v, v.base), "modifié": Rig(v, v.img)}
    for name, r in rigs.items():
        r.built = []

        def at_lm(uc, a, size, ud, r=r):        # lm_build : noté, puis comme une liste construite (gm_opened)
            cur = r.r32(tgs["gm_cur"])
            rows = r.r32(cur + 12) if cur == gs["gen_desc"] else 0
            r.built.append((r.r32(tgs["gm_track"]), cur,
                            [struct.unpack(">4I", r.mem(rows + 16 * i, 16)) for i in range(13)] if rows else None,
                            uc.reg_read(mk.UC_M68K_REG_A7)))
            uc.reg_write(mk.UC_M68K_REG_PC, tgs["gm_opened"])
        r.uc.hook_add(UC_HOOK_CODE, at_lm, begin=tgs["lm_build"], end=tgs["lm_build"])
    # A. l'accord, puis TRACK seul
    seq = [("SETTINGS appui", 0, KEY_SETTINGS, 1), ("TRACK appui", 1, KEY_TRACK, 1), ("TRACK appui relu", 1, None, None),
           ("TRACK répétition", 2, KEY_TRACK, 9), ("TRACK relâché", 3, KEY_TRACK, 0x10),
           ("TRACK relâché relu", 3, None, None), ("SETTINGS relâché", 4, KEY_SETTINGS, 0x10),
           ("TRACK seul appui", 5, KEY_TRACK, 1), ("TRACK seul relâché", 6, KEY_TRACK, 0x10)]
    res = {}
    for name, r in rigs.items():
        out = []
        for label, i, code, flags in seq:
            ev = r.event(i, code, flags) if code is not None else EV + 0x20 * i
            d0 = r.key(ev)
            out.append((d0, r.r32(ev + 16), r.r32(tgs["set_held"]), r.r32(tgs["mod_used"]),
                        r.r32(gs["gen_ev"]) if name == "modifié" else None, len(r.built)))
        res[name] = out
    o, m = res["origine"], res["modifié"]
    want_o = [13, 2, 2, 2, 2, 2, 13, 2, 2]
    check([x[0] for x in o] == want_o and not rigs["origine"].built and rigs["origine"].clean(),
          f"origine (Model-TG) : TRACK rendu à chaque lecture, SETTINGS relâché rendu (le Config Menu s'ouvre) : "
          f"{[x[0] for x in o]}")
    rm = rigs["modifié"]
    b = rm.built[0] if rm.built else (None, None, None, None)
    row = (gs["gen_lab"], gs["gen_val"], gs["gen_turn"], gs["gen_press"])
    check(len(rm.built) == 1 and b[0] == 2 and b[1] == gs["gen_desc"] and b[2] == [row] * 13,
          f"SETTINGS + TRACK : lm_build atteint une fois, gm_track = 2 (la piste sélectionnée), gm_cur = gen_desc, "
          f"13 lignes {{gen_lab, gen_val, gen_turn, gen_press}} sur la pile")
    check([x[0] for x in m] == [13, 0, 0, 0, 0, 0, 0, 2, 2] and m[1][1] == 9 and m[1][3] == 1 and m[1][4] == 1
          and m[4][4] == EV + 0x60 and m[6][2] == 0 and m[7][4] == 0 and m[7][1] == 1 and rm.clean(),
          f"modifié : l'appui de TRACK avalé (d0 = 0, bit 3 levé, mod_used = 1, gen_ev = 1), ses relectures, sa "
          f"répétition, son relâchement (deux lectures, gen_ev = l'événement) aussi ; SETTINGS relâché avalé (pas de "
          f"Config Menu) ; TRACK seul ensuite rendu (2), gen_ev remis à 0 : {[x[0] for x in m]}")
    # B. tout le reste : key_hook atteint avec la même pile, rien d'écrit
    paths = {}
    for name, r in rigs.items():
        r.stop_at = []

        def at_kh(uc, a, size, ud, r=r):
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            r.stop_at.append((sp, r.mem(sp, 8)))
            uc.emu_stop()
        r.hk = r.uc.hook_add(UC_HOOK_CODE, at_kh, begin=tgs["key_hook"], end=tgs["key_hook"])
        r.writes = []
        r.hw = r.uc.hook_add(UC_HOOK_MEM_WRITE, lambda uc, acc, a, sz, val, ud, r=r: r.writes.append((a, sz, val)))
    cases = []
    for code in range(41):
        for flags in (1, 9, 0x10, 0x21, 0):
            for held in (0, 1):
                if code != KEY_TRACK:
                    cases.append((code, flags, held, 0, 0, 0))
    cases += [(KEY_TRACK, 1, 0, 0, 0, 0), (KEY_TRACK, 1, 1, 1, 0, 0), (KEY_TRACK, 1, 1, 0, 1, 0),
              (KEY_TRACK, 9, 1, 0, 0, 0), (KEY_TRACK, 0x10, 1, 0, 0, 0), (KEY_TRACK, 0x10, 0, 0, 0, 0),
              (KEY_TRACK, 9, 0, 0, 0, 0), (KEY_TRACK, 0x10, 1, 1, 0, 1), (KEY_TRACK, 1, 1, 0, 1, 1)]
    for name, r in rigs.items():
        out = []
        for code, flags, held, rtg, sle, ev_set in cases:
            ev = r.event(7, code, flags)
            r.w32(tgs["set_held"], held)
            r.w32(tgs["rtg_on"], rtg)
            r.w32(tgs["sle_on"], sle)
            if name == "modifié":
                r.w32(gs["gen_ev"], ev_set)
            r.stop_at.clear()
            r.writes.clear()
            r.uc.reg_write(mk.UC_M68K_REG_SR, 0x2000)
            frame = struct.pack(">II", STOP, ev)
            r.uc.mem_write(CALL_SP - 8, frame)
            r.uc.reg_write(mk.UC_M68K_REG_A7, CALL_SP - 8)
            r.uc.emu_start(KEY_CODE, STOP, count=1000)
            w = [x for x in r.writes if not (name == "modifié" and x[0] == gs["gen_ev"] and x[2] == 0)]
            out.append((r.stop_at[:1], w))
        paths[name] = out
        r.uc.hook_del(r.hk)
        r.uc.hook_del(r.hw)
        r.w32(tgs["rtg_on"], 0)
        r.w32(tgs["sle_on"], 0)
    same = [i for i, (a, b_) in enumerate(zip(paths["origine"], paths["modifié"]))
            if a[0] and a == b_ and not b_[1]]
    check(len(same) == len(cases),
          f"{len(cases)} cas (codes 0 à 40 sauf TRACK, drapeaux appui / répétition / relâché / appui long, SETTINGS "
          f"tenu ou pas ; TRACK seul, avec la page Retrig ou l'éditeur de tranches, répétition ou relâchement non "
          f"avalés) : key_hook atteint avec la même pile que dans l'origine, aucune écriture en mémoire "
          f"({len(cases) - len(same)} différences)")
    # C. accord refusé, ou liste déjà ouverte
    out = []
    for label, setup, sr in (("interface pas prête", lambda r: r.w32(UI_READY, 0), 0x2000),
                             ("en interruption", lambda r: None, 0x2700),
                             ("piste 6", lambda r: setattr(r, "sel", 6), 0x2000)):
        res = []
        for name, r in rigs.items():
            r.w32(tgs["mod_used"], 0)
            r.w32(tgs["mm_opened"], 0)
            if name == "modifié":
                r.w32(gs["gen_ev"], 0)
            n0 = len(r.built)
            setup(r)
            r.key(r.event(0, KEY_SETTINGS, 1))
            d0 = r.key(r.event(1, KEY_TRACK, 1), sr=sr)
            res.append((d0, r.r32(EV + 0x20 + 16), r.r32(tgs["mod_used"]), r.r32(tgs["mm_opened"]),
                        len(r.built) - n0))
            r.w32(UI_READY, 1)
            r.sel = 2
            r.key(r.event(2, KEY_TRACK, 0x10))
            r.key(r.event(3, KEY_SETTINGS, 0x10))
        out.append((label, res[0] == res[1] == (2, 1, 0, 0, 0)))
    check(all(ok for _, ok in out), "accord refusé (" + ", ".join(lb for lb, _ in out)
          + ") : TRACK rendu (2), drapeaux intacts, mod_used à 0, pas de menu, comme dans l'origine")
    r = rigs["modifié"]
    r.stub(tgs["gm_live"], lambda a: 1 if getattr(r, "live", False) else None)
    r.live = True
    n0 = len(r.built)
    r.w32(tgs["mod_used"], 0)
    r.key(r.event(0, KEY_SETTINGS, 1))
    d0 = r.key(r.event(1, KEY_TRACK, 1))
    ok = d0 == 0 and r.r32(tgs["mm_opened"]) == 1 and r.r32(tgs["mod_used"]) == 1 and len(r.built) == n0
    r.key(r.event(2, KEY_TRACK, 0x10))
    r.key(r.event(3, KEY_SETTINGS, 0x10))
    r.live = False
    check(ok and r.clean(), "une liste de Model-TG déjà ouverte (gm_live) : l'accord est avalé (mm_opened, "
                            "mod_used), sans second menu (lm_build pas atteint)")


# --- 3. le menu -----------------------------------------------------------------------------------------------------
def menu_tests(v):
    r = Rig(v, v.img)
    tgs, gs = v.tgs, v.gs
    r.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: r.calls_seen.append(a), begin=0x400734b0, end=0x400734b0)
    r.stub(0x400422a8, lambda a: None)           # base des menus de réglages : noté, le vrai code s'exécute
    r.key(r.event(0, KEY_SETTINGS, 1))
    d0 = r.key(r.event(1, KEY_TRACK, 1))
    pres = r.presented[-1] if r.presented else None
    menu = r.r32(pres[1]) - 0x38 if pres else 0
    beg, end = (r.r32(menu + 4), r.r32(menu + 8)) if menu else (0, 0)
    items = [r.r32(beg + 8 * i) for i in range((end - beg) // 8)] if menu else []
    want = (gs["gen_lab"], gs["gen_press"], gs["gen_val"], gs["gen_turn"])
    ok_items = len(items) == 13 and all(
        r.r32(it) == ITEM_VT and r.r32(it + 8) == i
        and (r.r32(it + 24), r.r32(it + 40), r.r32(it + 56), r.r32(it + 72)) == want for i, it in enumerate(items))
    check(d0 == 0 and r.clean() and len(r.presented) == 1 and len(r.calls_seen) == 13 and ok_items
          and "Generate" in r.labels and r.r32(tgs["mm_opened"]) == 1,
          f"vrai lm_build : menu présenté une fois, titre « Generate », 13 éléments de menu de l'OS (vtable "
          f"{ITEM_VT:#x}), numéro de ligne en +8, fermetures libellé gen_lab, appui gen_press, valeur gen_val, "
          f"rotation gen_turn ; {r.errors[:2]} {r.e.unmapped[:2]}")
    if not ok_items:
        return
    vname = [a for a in r.calls.get(0x400422a8, [])]
    check(bool(vname) and vname[0][1] == tgs["gm_vname"],
          "la liste est la classe de base des menus de réglages (0x400422a8), avec le nom de vue des listes de "
          "Model-TG")
    # libellés
    labels = []
    for it in items:
        r.labels.clear()
        r.uc.mem_write(OUT, bytes(16))
        r.call(ITEM_LABEL, it, a0=OUT)
        labels.append(r.labels[-1] if r.labels else None)
    check(labels == LABELS and r.clean(), f"libellés (méthode 0x40073236 de l'élément) : {' '.join(map(str, labels))}")

    def values():
        out = []
        for it in items:
            r.texts.clear()
            r.call(ITEM_DRAW, it, 0x93500000, 0x93510000, 7)
            out.append(r.texts[-1] if len(r.texts) == 1 else r.texts)
        return out

    def expect(st):
        return [NAMES[i][st[i]] if i in NAMES else str(st[i]) for i in range(13)]
    got = values()
    check(got == expect(DEFAULTS) and r.clean(), f"valeurs par défaut (méthode 0x40073274 -> gm_val) : {' '.join(map(str, got))}"
                                                 f" {r.errors[:1]} {r.e.unmapped[:1]}")
    bad = []
    for st in ([1, 0, 64, 63, 1, 11, 12, 8, 4, 1, 127, 1, 0], [0, 100, 1, 1, 0, 1, 1, 0, 2, 0, 1, 127, 0],
               *[[1, 7, 13, 5, 1, k, k, k % 9, 3, 1, 99, 10, 0] for k in range(12)]):
        r.settings(st)
        got = values()
        if got != expect(st):
            bad.append((st, got))
    check(not bad, f"valeurs : chaque nom (RND/EUC, OFF/ON, 12 toniques, 13 gammes, GO) et les nombres aux bornes "
                   f"{bad[:1]}")
    r.settings(DEFAULTS)
    # rotations bornées
    bad = []
    for i, it in enumerate(items):
        for delta, want_v in ((1, None), (500, MAXS[i]), (-1, max(MINS[i], MAXS[i] - 1)), (-500, MINS[i]),
                              (3, min(MAXS[i], MINS[i] + 3))):
            before = r.settings()
            r.call(ITEM_TURN, it, delta & M32)
            after = r.settings()
            exp = list(before)
            exp[i] = min(MAXS[i], max(MINS[i], before[i] + delta))
            if after != exp or (want_v is not None and after[i] != want_v):
                bad.append((LABELS[i], delta, before[i], after[i]))
    check(not bad and r.clean(), f"rotations (méthode 0x400732b6) : valeur + écart, bornée à [min, max] (HIT, RNG, "
                                 f"VMN, VMX à partir de 1 ; GEN reste 0), les autres réglages intacts {bad[:3]}")
    r.settings(DEFAULTS)
    # appui : édition, ou génération
    flips = []
    for it in items[:12]:
        r.uc.mem_write(it + 0x50, b"\0")
        r.call(ITEM_PRESS, it)
        a1 = r.mem(it + 0x50, 1)[0]
        r.call(ITEM_PRESS, it)
        flips.append((a1, r.mem(it + 0x50, 1)[0]))
    r.popups.clear()
    track = DATA + 0x400 * 2
    r.uc.mem_write(track, bytes(722))
    r.uc.mem_write(track + 713, struct.pack(">h", 16))
    r.uc.mem_write(items[12] + 0x50, b"\0")
    r.call(ITEM_PRESS, items[12])
    trig = [s for s in range(16) if r.mem(track + 2 * s, 2)[1] & 1]
    check(flips == [(1, 0)] * 12 and r.mem(items[12] + 0x50, 1) == b"\0" and len(r.popups) == 1 and r.clean(),
          f"appui (méthode 0x4007329c) : lignes 1 à 12, l'édition basculée puis rebasculée (invocateur de Model-TG) ; "
          f"GEN : génère sans passer en édition, « {r.popups[-1] if r.popups else '?'} », trigs aux pas {trig}")


# --- 4. la génération -----------------------------------------------------------------------------------------------
def fill(r, t, length, seed):
    """Données de la piste t : pas déjà remplis (trigs, trigs de lock, slides, notes, vélocités), longueur."""
    rnd = random.Random(seed)
    d = DATA + 0x400 * t
    flags = b"".join(struct.pack(">H", rnd.choice((0, 0, 0x0201, 0x6801, 0x1201, 0x0200))) for _ in range(64))
    vel = bytes(rnd.choice((0xff, rnd.randrange(1, 128))) for _ in range(64))
    note = bytes(rnd.choice((0xff, rnd.randrange(0, 128))) for _ in range(64))
    r.uc.mem_write(d, flags + vel + bytes(rnd.randrange(256) for _ in range(580 - 192)) + note
                   + bytes(rnd.randrange(256) for _ in range(722 - 644)))
    r.uc.mem_write(d + 713, struct.pack(">h", length))


def gen_tests(v):
    r = Rig(v, v.img)
    gs = v.gs
    item = ITEM
    r.uc.mem_write(item, bytes(0x54))
    r.w32(item + 8, 12)                          # la ligne GEN
    r.w32(v.tgs["gm_track"], 2)                  # la piste du menu (posée à l'ouverture)
    cases = []
    for n in (1, 2, 3, 5, 7, 8, 12, 13, 16, 24, 32, 48, 63, 64):
        for hit in (1, 2, 3, 4, 5, 7, 16, 63, 64):
            for rot in (0, 1, 2, 13, 63):
                if (n * 7 + hit * 3 + rot) % 4 == 0 or n in (8, 16):
                    cases.append((n, [1, 50, hit, rot, 0, 0, 0, 4, 1, 0, 64, 127, 0]))
    for dns in (0, 1, 25, 50, 99, 100):
        for n in (16, 64):
            cases.append((n, [0, dns, 4, 0, 0, 0, 0, 4, 1, 0, 64, 127, 0]))
    for scl in range(13):
        for key, octv, rng in ((0, 4, 1), (9, 3, 2), (11, 8, 4), (0, 0, 1), (5, 6, 3)):
            cases.append((16, [scl % 2, 60, 5, scl, 1, key, scl, octv, rng, 0, 64, 127, 0]))
    for lo, hi in ((64, 127), (1, 1), (127, 127), (20, 40), (100, 10), (1, 127)):
        cases.append((32, [0, 70, 4, 0, 0, 0, 0, 4, 1, 1, lo, hi, 0]))
        cases.append((32, [1, 70, 11, 3, 1, 7, 9, 2, 2, 1, lo, hi, 0]))
    cases.append((80, [1, 50, 5, 1, 1, 0, 0, 4, 1, 1, 64, 127, 0]))      # longueur au-delà de 64 : 64 pas
    rng0 = r.r32(gs["gen_rng"])
    bad, regs_bad, worst = [], 0, 0
    clocks = random.Random(7)
    for k, (length, st) in enumerate(cases):
        r.settings(st)
        clock = clocks.randrange(1 << 32)
        r.w32(CLOCK, clock)
        if k % 3 == 0:
            r.w32(gs["gen_rng"], clocks.randrange(1 << 32))
        rng_in = r.r32(gs["gen_rng"])
        for t in range(6):
            fill(r, t, length if t == 2 else 16, 100 * k + t)
        before = {t: r.mem(DATA + 0x400 * t, 722) for t in range(6)}
        r.popups.clear()
        r.call(gs["gen_press"], 0x93600000, item, regs=True)
        if r.regs_after != CALLEE_VALS:
            regs_bad += 1
        want, rng_out, total = reference(st, rng_in, clock, length)
        d = DATA + 0x400 * 2
        n = min(length, 64)
        got = []
        for s in range(n):
            fl = struct.unpack(">H", r.mem(d + 2 * s, 2))[0]
            got.append((fl & 1, struct.unpack(">b", r.mem(d + 580 + s, 1))[0],
                        struct.unpack(">b", r.mem(d + 128 + s, 1))[0]))
        after = r.mem(d, 722)
        beyond = all(after[2 * s:2 * s + 2] == before[2][2 * s:2 * s + 2] and after[128 + s] == before[2][128 + s]
                     and after[580 + s] == before[2][580 + s] for s in range(n, 64))
        others = all(r.mem(DATA + 0x400 * t, 722) == before[t] for t in range(6) if t != 2)
        if (got != want or r.r32(gs["gen_rng"]) != rng_out or r.popups != [f"Trigs: {total}"] or not beyond
                or not others or r.mem(gs["gen_set"], 13) != bytes(st)):
            bad.append((length, st, got[:8], want[:8] if want else None, r.popups))
    check(not bad and r.clean(), f"{len(cases)} générations comparées pas à pas à la référence : trigs (euclidien : "
                                 f"longueurs 1 à 64, 1 à 64 coups, rotations ; aléatoire : DNS 0 à 100), notes (13 "
                                 f"gammes, toniques, octaves 0 à 8, étendues 1 à 4, 127 au plus), vélocités (bornes, "
                                 f"échangées), état du xorshift, « Trigs: N » par le vrai vsprintf, pas au-delà de "
                                 f"la longueur et autres pistes intacts {bad[:1]} {r.errors[:1]}")
    check(regs_bad == 0, f"registres d2-d7/a2-a6 rendus par la génération ({regs_bad} appels fautifs)")
    # longueur 0 : rien
    r.settings(DEFAULTS)
    fill(r, 2, 0, 1)
    before = r.mem(DATA + 0x800, 722)
    r.popups.clear()
    rng_in = r.r32(gs["gen_rng"])
    r.call(gs["gen_press"], 0x93600000, item)
    check(r.mem(DATA + 0x800, 722) == before and not r.popups and r.r32(gs["gen_rng"]) == rng_in,
          "piste de longueur 0 : rien n'est écrit, pas de message, xorshift intact")
    # un exemple lisible : EUC 4/16, puis EUC 3/8 (tresillo), 5/16 rotation 2, 5/12 rotation 13
    shown = []
    for n, hit, rot, want in ((16, 4, 0, "x...x...x...x..."), (8, 3, 0, "x..x..x."), (16, 5, 2, "..x...x..x..x..x"),
                              (12, 5, 13, ".x..x.x..x.x")):
        r.settings([1, 50, hit, rot, 0, 0, 0, 4, 1, 0, 64, 127, 0])
        fill(r, 2, n, 5)
        r.call(gs["gen_press"], 0x93600000, item)
        pat = "".join("x" if r.mem(DATA + 0x800 + 2 * s, 2)[1] & 1 else "." for s in range(n))
        shown.append((pat, want))
    check(all(p == w for p, w in shown), "motifs euclidiens : " + ", ".join(p for p, _ in shown))
    # ce qui reste d'un pas effacé ou gardé (vrais accesseurs, Model-TG compris)
    r.settings([1, 50, 4, 0, 0, 0, 0, 4, 1, 0, 64, 127, 0])
    d = DATA + 0x800
    r.uc.mem_write(d, bytes(722))
    r.uc.mem_write(d + 128, b"\xff" * 64)
    r.uc.mem_write(d + 580, b"\xff" * 128)
    r.uc.mem_write(d + 713, struct.pack(">h", 16))
    for s, (fl, vel, note) in {1: (0x0201, 90, 70), 4: (0x6801, -1, -1), 5: (0x0201, 80, 65),
                               8: (0x1201, -1, 72)}.items():
        r.uc.mem_write(d + 2 * s, struct.pack(">H", fl))
        r.uc.mem_write(d + 128 + s, struct.pack(">b", vel))
        r.uc.mem_write(d + 580 + s, struct.pack(">b", note))
    r.notify = 0
    r.call(gs["gen_press"], 0x93600000, item)
    fl = [struct.unpack(">H", r.mem(d + 2 * s, 2))[0] for s in range(16)]
    check(fl[0] & 1 and not fl[1] & 1 and fl[4] & 0x6801 == 0x0001 and fl[8] & 0x1001 == 0x1001
          and not fl[5] & 1 and r.mem(d + 580, 16) == b"\xff" * 16 and r.mem(d + 128, 16) == b"\xff" * 16,
          f"EUC 4/16 sur des pas remplis : trigs aux pas 0, 4, 8, 12 ; le trig du pas 1 et celui du pas 5 effacés ; "
          f"le trig de lock du pas 4 devient un trig de note ; le slide du pas 8 (Model-TG) gardé ; notes et "
          f"vélocités remises à -1 (NOT et VEL sur OFF) ; {r.notify} signaux de modification")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True)
    ap.add_argument("--with", dest="others", default="",
                    help="autres tweaks appliqués avant (ex. 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm)")
    ap.add_argument("--syntakt", help="Syntakt_OS1.42.syx (ou 1.41), pour les moteurs du Syntakt")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    by_id = {json.loads(f.read_text(encoding="utf-8"))["id"]: f for f in TW.glob("[0-9]*.json")}
    others = [i for i in args.others.split(",") if i]
    if "model-tg" in others or "model-tg-st" in others:
        sets = [others]
    else:                                       # Model-TG seul par défaut ; les deux versions avec --syntakt
        sets = [others + ["model-tg"]] + ([others + ["model-tg-st"]] if args.syntakt else [])
    for ids in sets:
        v = Variant(stock, ids, by_id, args.syntakt)
        print(f"\n== origine : {v.label} ; modifié : + {v.gt['id']}")
        print("1. écritures")
        writes_tests(stock, v)
        print("2. l'accord SETTINGS + TRACK (vrai 0x4007240c, key_hook de Model-TG)")
        chord_tests(v)
        print("3. le menu (vrai lm_build de Model-TG, méthodes des éléments de l'OS)")
        menu_tests(v)
        print("4. la génération (vrais accesseurs de la grille) contre la référence")
        gen_tests(v)
    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ÉCHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
