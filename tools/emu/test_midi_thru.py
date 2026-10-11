#!/usr/bin/env python3
"""Preuve des deux tweaks « THRU qui envoie aussi le MIDI du Cycles » (notes/53 ; tweaks/model-cycles_OS1.13/
50-midi-both.json et 51-midi-live-both.json, d'après le fork d'AveyCole).

Le vrai code de l'OS est exécuté sur le MAIN OS d'origine (ou avec les autres tweaks seuls, --with), sur le MAIN OS
avec midi-both, avec midi-live-both, et avec midi-live-both tel que l'a testé AveyCole (code en 0x40167c50), pour
chaque valeur du réglage OUT/THRU (octet 0x404e9b50 : 0 OUT, 1 THR, 2 THR + MIDI du Cycles, que seul
midi-live-both écrit) :
  1. Écritures : octets d'origine ; aucun recouvrement avec les autres tweaks (sauf écritures identiques, et entre
     les deux, qui s'excluent) ; rien ne vise le bourrage de la touche (0x40035610..0x40035621) ; le code de
     midi-live-both dans le masque 34x34 libéré, que seul son constructeur désigne et qui pointe maintenant sur un
     masque identique ; ce code est celui du build testé par AveyCole, octet pour octet (lié en 0x40167c50, il
     redonne les 132 octets du fork) ; midi-both, les écritures du fork à l'identique.
  2. Sorties : les trois portes de l'OS appelées avec un message (0x40001544 et 0x40001564 : un octet ; 0x40001584 :
     une note). L'octet seul part par le vrai envoi 0x40001232 dans le registre d'émission de l'UART MIDI
     (0xec07400c) ; les autres par le vrai envoi 0x40001100 dans l'anneau du DMA (0x4049dca8), qui démarre. Origine :
     envoyé en OUT, jeté en THR. midi-both : envoyé dans tous les cas. midi-live-both : jeté seulement en THR (1).
  3. Relais : le vrai relais du MIDI reçu (0x400012cc) renvoie l'octet reçu sur l'UART pour THR (1 et 2), pas pour
     OUT, puis passe la main au gestionnaire suivant (0x422fee70) avec l'octet intact ; partout comme à l'origine.
  4. Écran : la ligne OUT/THRU (0x40035fd8) montre « OUT » pour 0, « THR » pour 1 et 2.
  5. Touche : la vraie touche de la ligne (0x4003560a), sans et avec FUNC tenu (bitmap des touches lu par
     0x4007faf4(1)), depuis chaque valeur. Sans FUNC : comme l'origine (OUT -> THR, THR et 2 -> OUT). Avec FUNC :
     midi-live-both fait THR -> 2 -> THR et laisse OUT -> THR. Le bloc des réglages (0x404e9b10) garde sa marque
     « COKI » et une somme juste (celle que recalcule l'OS), la pile revient à sa place, d2-d7 et a2-a6 sont rendus.
  6. Démarrage : le vrai décompresseur du bootstrap relit l'OS modifié à l'identique.

    python3 tools/emu/test_midi_thru.py --cycles model-cycles_OS1.13.syx \
        [--with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,arp,trig-hold --syntakt Syntakt_OS1.42.syx]

Quelques secondes seul ; une minute environ avec Model-TG et les moteurs du Syntakt (décompresseur du bootstrap).
"""
import argparse
import json
import pathlib
import struct
import sys

from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED, UC_HOOK_MEM_WRITE
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import gen_midi_thru as G           # noqa: E402
import sprites                      # noqa: E402
import test_sdvintage_exact as X    # noqa: E402

DEV = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13"
BASE = build.BASE
FAIL = []
STOP, NEXT, STACK = 0x90000100, 0x90000200, 0x90010000
RING, MSG = 0x90100000, 0x90180000          # anneau d'émission du DMA (0x4049dca8 pointe dessus), message envoyé
VAL = G.OUT_THRU                            # 0 OUT, 1 THR, 2 THR + MIDI du Cycles
BLOCK, MAGIC = 0x404e9b10, b"COKI"          # réglages globaux : marque, somme (+4), données (+8, 0x4b octets)
RESUM = 0x40044b4e                          # recalcule la somme du bloc et pose la marque (fin de 0x40044b88)
FUNC_BYTE, FUNC_BIT = 0x40f95745, 2         # 0x4007faf4(1) : table 0x4010ae5c[1] = 10 -> bit 10 de 0x40f95744
UART_SR, UART_TB = 0xec074004, 0xec07400c   # UART du MIDI : état (bit 2 : prêt à émettre), registre d'émission
NEXT_HANDLER = 0x422fee70                   # gestionnaire suivant du MIDI reçu (le relais y saute)
SHOW = {0x40127bad: "OUT", 0x40127281: "THR"}
GATES = ((0x40001544, "porte 0x40001544 (octet)", (0xfa,)), (0x40001564, "porte 0x40001564 (octet)", (0xf8,)),
         (0x40001584, "porte 0x40001584 (note)", (0x90, 0x3c, 0x64)))
PAD = (G.KEY + 6, G.KEY + len(G.KEY_OLD))    # bourrage de nop derrière le jmp de la touche

# Le build testé par AveyCole sur son Model:Cycles le 10/10/2026 (fork, commit ba5f8bb, 45-midi-live-both.json et
# 44-midi-both.json) : code en 0x40167c50, masque 35x35 redirigé par la constante 0x400b211e.
FORK_CAVE, FORK_REDIRECT = 0x40167c50, (0x400b211e, "40167c50", "4014a660")
FORK_CODE = bytes.fromhex(
    "487800014eb94007faf4588f4a80670000484eb940044df84a806700003c1039404e9b500c0000026700000870026000000470014e56"
    "fffc1d40ffff48780001486effff4879404e9b504eb940044b884fef000c4e5e4e754eb940044df84a8057c0710044802f4000044ef9"
    "40044dc21039404e9b500c000001670470004e7570014e75")
FORK_KEY = bytes.fromhex("4ef940167c50" + "4e71" * 9)
FORK_GATE = bytes.fromhex("4eb940167cc0")
FORK_BOTH = [{"off": 4426, "old": "4eb940044df8", "new": "70004e714e71"},
             {"off": 4458, "old": "4eb940044df8", "new": "70004e714e71"},
             {"off": 4496, "old": "4eb940044df8", "new": "70004e714e71"}]


def check(ok, msg):
    print(("  ok    " if ok else "  ÉCHEC ") + msg, flush=True)
    if not ok:
        FAIL.append(msg)


class Rig:
    def __init__(self, img):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
        uc.reg_write(mk.UC_M68K_REG_SR, 0x2700)
        uc.mem_map(0x40000000, 0x01000000)
        uc.mem_write(BASE, img)
        uc.mem_map(0x42000000, 0x00400000)            # BSS haut (0x422fee70)
        uc.mem_map(0x90000000, 0x00200000)            # pile, arrêts, anneau, message
        uc.mem_map(0xec070000, 0x00010000)            # UART du MIDI
        uc.mem_map(0xfc040000, 0x00010000)            # DMA (0xfc0454xx), interruptions (0xfc04401x, 0xfc04c01d)
        uc.mem_write(STOP, b"\x4e\x71\x4e\x71")
        uc.mem_write(NEXT, b"\x4e\x71\x4e\x71")
        self.bad, self.tx, self.next = [], [], None
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: self.bad.append(addr) or False)
        uc.hook_add(UC_HOOK_MEM_WRITE, lambda u, a, addr, s, v, d: self.tx.append(v & 0xff), begin=UART_TB, end=UART_TB)
        uc.hook_add(UC_HOOK_CODE, self._next, begin=NEXT, end=NEXT)
        self.w32(NEXT_HANDLER, NEXT)

    def _next(self, uc, addr, size, ud):
        sp = uc.reg_read(mk.UC_M68K_REG_A7)
        self.next = (sp, struct.unpack(">I", uc.mem_read(sp + 4, 4))[0])
        uc.emu_stop()

    def w32(self, a, v):
        self.uc.mem_write(a, struct.pack(">I", v & 0xffffffff))

    def r32(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def call(self, fn, *args, regs=None):
        """Appelle fn(args) ; rend (pile au retour, pile de départ, registres d2-d7/a2-a6 au retour)."""
        sp = STACK - 0x200
        self.uc.mem_write(sp, struct.pack(">I" + "I" * len(args), STOP, *[x & 0xffffffff for x in args]))
        self.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        for name, v in (regs or {}).items():
            self.uc.reg_write(getattr(mk, "UC_M68K_REG_" + name.upper()), v)
        self.next = None
        self.uc.emu_start(fn, STOP, count=2_000_000)
        kept = {n: self.uc.reg_read(getattr(mk, "UC_M68K_REG_" + n.upper())) for n in (regs or {})}
        return self.uc.reg_read(mk.UC_M68K_REG_A7), sp, kept

    def setting(self, v):
        """Réglage OUT/THRU = v, bloc des réglages valide (marque et somme posées par l'OS)."""
        self.uc.mem_write(VAL, bytes([v]))
        self.call(RESUM)

    def block_ok(self):
        crc = self.r32(BLOCK + 4)
        magic = bytes(self.uc.mem_read(BLOCK, 4)) == MAGIC
        self.call(RESUM)                              # la somme que l'OS calcule pour ce contenu
        return magic and self.r32(BLOCK + 4) == crc

    def idle_io(self):
        """Sortie MIDI au repos : UART prête, DMA arrêté, anneaux vides."""
        self.uc.mem_write(UART_SR, b"\x0c")
        for a in (0x4049dca0, 0x4049dcb4, 0x4049dcb8, 0x4049dcbc, 0x4049dcc0, 0x4049dcc8, 0x4049dccc):
            self.w32(a, 0)
        self.w32(0x4049dca8, RING)
        self.uc.mem_write(0xfc0454b4, bytes(12))
        self.uc.mem_write(RING, bytes(64))
        self.tx = []

    def sent(self):
        """Ce qui est parti : octets écrits dans l'UART, puis ceux posés dans l'anneau du DMA (s'il a démarré)."""
        n = self.r32(0x4049dcb4)                      # le DMA démarré avance d'autant (0x40001218)
        dma = bytes(self.uc.mem_read(RING, n)) if self.r32(0x4049dca0) == 1 else b""
        return bytes(self.tx) + dma

    def func(self, held):
        b = self.uc.mem_read(FUNC_BYTE, 1)[0]
        self.uc.mem_write(FUNC_BYTE, bytes([b | 1 << FUNC_BIT if held else b & ~(1 << FUNC_BIT)]))


def fork_tweak(stock):
    """midi-live-both tel que l'a testé AveyCole : même code, en 0x40167c50 (masque 35x35 redirigé)."""
    a, old, new = FORK_REDIRECT
    writes = [{"off": G.KEY - BASE, "old": G.KEY_OLD.hex(), "new": FORK_KEY.hex()}]
    writes += [{"off": va - BASE, "old": G.GET.hex(), "new": FORK_GATE.hex()} for va, _ in G.GATES]
    writes.append({"off": a - BASE, "old": old, "new": new})
    writes.append({"off": FORK_CAVE - BASE, "old": stock[FORK_CAVE - BASE:FORK_CAVE - BASE + len(FORK_CODE)].hex(),
                   "new": FORK_CODE.hex()})
    return {"id": "midi-live-both-fork", "order": 51, "writes": writes}


# --- 1. écritures -------------------------------------------------------------------------------------------------
def writes(stock, both, live):
    for t in (both, live):
        try:
            build.apply_writes(stock, [t])
            check(True, f"{t['id']} : {len(t['writes'])} écritures, octets d'origine conformes")
        except SystemExit as e:
            check(False, f"{t['id']} : {e}")
    regen = G.build_tweaks(stock)
    check(regen == [both, live], "50-midi-both.json et 51-midi-live-both.json = tools/gen_midi_thru.py sur l'OS officiel")
    check(both["conflicts"] == ["midi-live-both"] and live["conflicts"] == ["midi-both"],
          "les deux s'excluent (conflicts), dans les deux sens")
    for t in (both, live):
        mine = [(w["off"] + BASE, bytes.fromhex(w["new"])) for w in t["writes"]]
        clash = []
        for f in sorted(DEV.glob("*.json")):
            o = json.loads(f.read_text(encoding="utf-8")) if f.name != "device.json" else None
            if o is None or o["id"] in (both["id"], live["id"]):
                continue
            for w in o["writes"]:
                a, n = w["off"] + BASE, bytes.fromhex(w["new"])
                for b, m in mine:
                    lo, hi = max(a, b), min(a + len(n), b + len(m))
                    if lo < hi and n[lo - a:hi - a] != m[lo - b:hi - b]:
                        clash.append((o["id"], hex(lo)))
        check(not clash, f"{t['id']} : aucun recouvrement avec les autres tweaks {sorted(set(clash))[:4]}")
    check(both["writes"] == FORK_BOTH, "midi-both : les trois écritures du fork d'AveyCole, à l'identique")

    refs = [BASE + i for i in range(0, len(stock) - 3, 2) if PAD[0] <= struct.unpack(">I", stock[i:i + 4])[0] < PAD[1]]
    check(not refs, f"aucune constante de l'OS ne vise le bourrage de la touche {PAD[0]:#x}..{PAD[1] - 1:#x}")

    va, size = sprites.zone(G.MASK)
    kept = sprites.MASKS[G.MASK][3]
    code = [(b, m) for b, m in ((w["off"] + BASE, bytes.fromhex(w["new"])) for w in live["writes"]) if len(m) > 64]
    refs = [BASE + i for i in range(0, len(stock) - 3, 2) if va <= struct.unpack(">I", stock[i:i + 4])[0] < va + size]
    same = stock[va - BASE:va - BASE + size] == stock[kept - BASE:kept - BASE + size]
    img = build.apply_writes(stock, [live])[0]
    const = sprites.MASKS[G.MASK][1]
    moved = img[const - BASE:const - BASE + 4] == kept.to_bytes(4, "big")
    check(len(code) == 1 and code[0][0] == va and len(code[0][1]) <= size and refs == [const] and same and moved,
          f"midi-live-both : code ({len(code[0][1])} o) dans le masque libéré {va:#x} ({size} o), que seul son "
          f"constructeur désigne ({const:#x}) et qui pointe maintenant sur un masque identique ({kept:#x})")

    at_fork, _ = G.compile_helper(FORK_CAVE)
    here, syms = G.compile_helper(G.MASK)
    check(at_fork == FORK_CODE and here == FORK_CODE and code[0][1] == FORK_CODE,
          f"le code de midi_thru.S est celui du build testé par AveyCole, octet pour octet ({len(FORK_CODE)} o, "
          "sans adresse interne : identique en 0x40167c50 et ici)")
    hooks = {w["off"] + BASE: bytes.fromhex(w["new"]) for w in live["writes"]}
    gate = syms["midi_gate"] - syms["midi_key"]
    check(hooks[G.KEY] == FORK_KEY[:2] + G.MASK.to_bytes(4, "big") + FORK_KEY[6:]
          and all(hooks[g] == FORK_GATE[:2] + (G.MASK + gate).to_bytes(4, "big") for g, _ in G.GATES)
          and gate == 0x70 and FORK_GATE[2:] == (FORK_CAVE + gate).to_bytes(4, "big"),
          f"accroches du fork, seule l'adresse change : jmp {G.MASK:#x} (touche), jsr {G.MASK + gate:#x} (3 portes)")


# --- 2 à 5. comportement ------------------------------------------------------------------------------------------
def behaviour(rig):
    """{(test, valeur[, FUNC]): résultat} pour un MAIN OS."""
    out = {}
    for v in (0, 1, 2):
        rig.setting(v)
        for fn, name, msg in GATES:
            rig.idle_io()
            rig.uc.mem_write(MSG, bytes(msg))
            if len(msg) == 1:
                rig.call(fn, msg[0])
            else:
                rig.call(fn, len(msg), MSG)
            out[(name, v)] = rig.sent()
        rig.idle_io()
        end, sp, _ = rig.call(0x400012cc, 0x3c)
        out[("relais", v)] = (rig.sent(), rig.next and (rig.next[0] == sp, rig.next[1]))
        rig.uc.reg_write(mk.UC_M68K_REG_A7, STACK - 0x200)
        rig.uc.emu_start(0x40035fd8, 0x40035ff0, count=10_000)
        out[("écran", v)] = SHOW.get(rig.uc.reg_read(mk.UC_M68K_REG_D3), "?")
        for held in (False, True):
            rig.setting(v)
            rig.func(held)
            regs = {f"d{i}": 0x11111111 * i for i in range(2, 8)} | {f"a{i}": 0x90020000 + 0x100 * i for i in range(2, 7)}
            end, sp, kept = rig.call(G.KEY, 0x12345678, regs=regs)
            rig.func(False)
            out[("touche", v, held)] = (rig.uc.mem_read(VAL, 1)[0], rig.block_ok(), end == sp + 4, kept == regs)
    out["hors mémoire"] = rig.bad[:]
    return out


def show(r):
    return r.hex(" ") if r else "rien"


def compare(name, got, base, gate_open, func_next):
    """got : MAIN OS modifié ; base : le même sans le tweak. gate_open(v) : la porte laisse passer ?
    func_next(v) : valeur après FUNC + appui (None : comme base)."""
    for _, g, msg in GATES:
        res = [got[(g, v)] for v in (0, 1, 2)]
        want = [bytes(msg) if gate_open(v) else b"" for v in (0, 1, 2)]
        check(res == want, f"{name}, {g} : OUT {show(res[0])} / THR {show(res[1])} / 2 {show(res[2])}")
    relay = [got[("relais", v)] for v in (0, 1, 2)]
    check(relay == [base[("relais", v)] for v in (0, 1, 2)]
          and relay == [(b"" if v == 0 else b"\x3c", (True, 0x3c)) for v in (0, 1, 2)],
          f"{name}, relais du MIDI reçu (0x3c) : OUT {show(relay[0][0])} / THR {show(relay[1][0])} / "
          f"2 {show(relay[2][0])}, puis le gestionnaire suivant avec l'octet intact, comme à l'origine")
    screen = [got[("écran", v)] for v in (0, 1, 2)]
    check(screen == ["OUT", "THR", "THR"], f"{name}, écran de la ligne OUT/THRU : {' / '.join(screen)}")
    for held in (False, True):
        res = [got[("touche", v, held)] for v in (0, 1, 2)]
        nxt = [r[0] for r in res]
        want = [base[("touche", v, False)][0] if not held or func_next(v) is None else func_next(v) for v in (0, 1, 2)]
        check(nxt == want and all(r[1:] == (True, True, True) for r in res),
              f"{name}, touche {'FUNC + appui' if held else 'appui seul'} : OUT -> {nxt[0]}, THR -> {nxt[1]}, "
              f"2 -> {nxt[2]} ; bloc des réglages valide (marque, somme), pile et registres rendus")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True)
    ap.add_argument("--with", dest="others", default="", help="autres tweaks appliqués avant (ex. model-tg-st,…)")
    ap.add_argument("--syntakt", help="Syntakt_OS1.42.syx, pour les moteurs du Syntakt")
    args = ap.parse_args()
    stock = G.stock_mainos(args.cycles)
    by_id = {json.loads(f.read_text(encoding="utf-8"))["id"]: f for f in DEV.glob("*.json") if f.name != "device.json"}
    tweaks = [json.loads(by_id[i].read_text(encoding="utf-8")) for i in args.others.split(",") if i]
    both = json.loads(G.OUT_BOTH.read_text(encoding="utf-8"))
    live = json.loads(G.OUT_LIVE.read_text(encoding="utf-8"))
    pl, _ = build.build_payload(tweaks, stock, args.syntakt)

    def image(extra):
        return bytes(build.apply_writes(stock, sorted(tweaks + extra, key=lambda t: t["order"]))[0]) + pl
    print(f"firmware : {', '.join(t['id'] for t in tweaks) or 'origine'} (+ midi-both / midi-live-both)")
    print("écritures")
    writes(stock, both, live)

    print("comportement (sorties, relais, écran, touche)")
    base = behaviour(Rig(image([])))
    check(all(base[(g, v)] == (bytes(m) if v == 0 else b"") for _, g, m in GATES for v in (0, 1, 2))
          and [base[("touche", v, False)][0] for v in (0, 1, 2)] == [1, 0, 0],
          "d'origine : les trois portes envoient en OUT et jettent en THR ; la touche fait OUT -> THR -> OUT")
    runs = [("d'origine", base, lambda v: v == 0, lambda v: None),
            ("midi-both", behaviour(Rig(image([both]))), lambda v: True, lambda v: None)]
    for name, t in (("midi-live-both", live), ("midi-live-both du fork (0x40167c50)", fork_tweak(stock))):
        runs.append((name, behaviour(Rig(image([t]))), lambda v: v != 1, lambda v: {0: None, 1: 2, 2: 1}[v]))
    for name, got, gate_open, func_next in runs:
        compare(name, got, base, gate_open, func_next)
    live_runs = [r[1] for r in runs[2:]]
    check(live_runs[0] == live_runs[1], "midi-live-both ici et dans le build testé par AveyCole : mêmes résultats")
    for name, got, _, _ in runs:
        check(not got["hors mémoire"], f"{name} : aucun accès hors mémoire {[hex(a) for a in got['hors mémoire'][:3]]}")

    print("démarrage")
    for t in (both, live):
        check(X.bootstrap_depack_ok(args.cycles, tweaks + [t], args.syntakt),
              f"{t['id']} : le décompresseur du bootstrap relit l'OS à l'identique")
    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ÉCHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
