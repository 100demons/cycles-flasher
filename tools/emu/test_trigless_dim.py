#!/usr/bin/env python3
"""Preuve des trigless trigs atténués (notes/45 §10, tweaks/model-cycles_OS1.13/47-trigless-dim.json).

Le vrai code de l'OS, MAIN OS d'origine contre MAIN OS modifié, sur une même ligne de temps (horloge du bus,
135,168 MHz) :
  - l'interruption du panneau (PIT3, 12 kHz) : début 0x40059cd0, 8 colonnes 0x40059d2c, 3 étapes des LED
    0x40059db8 ; l'interruption logicielle des touches 0x40059e64, forcée par la 8e colonne ;
  - le tick des LED (0x4008e7ca, 120 Hz) ; une image de l'interface (30 Hz) : remise à zéro des états (0x4000602a),
    états posés comme le fait le mode grille (0x40005f86 : 2 = trig de note, 3 = trig avec p-locks, 4 ou 260 =
    trigless trig), fin de l'image (0x40006044, relevé du mod) ; le clignotement (0x40005efc, 2 Hz) ; la tête de
    lecture (0x4008e8c4).
Intercepté : le verrou des LED (0x40001cc4, 0x40001df6). Les écritures sur le port du panneau (Rapid GPIO
0x8c000000 : +0 DIR, +2 DATA, +6 CLR, +0xa SET) passent dans un modèle des verrous des LED (notes/21) : le verrou de
la rangée choisie par les bits 7-5 de DATA suit les bits 15-8 tant que le bit 3 est à 1 et le bit 0 à 0. Le compteur
de PIT3 (0xfc08c004) suit la ligne de temps : 1 coup par instruction, 8 par lecture du compteur (modèle grossier ;
les attentes du mod lisent ce compteur, la durée minimale entre deux écritures ne dépend donc pas du modèle).

  1. Écritures : octets d'origine ; masques libérés identiques au masque gardé et désignés par la seule constante de
     leur constructeur ; aucun autre tweak n'écrit sur ces octets ; l'interruption du panneau identique à l'origine
     sauf les 10 octets de l'accroche, sur lesquels aucun saut ne tombe ; le tick des LED identique à l'origine.
  2. Mode grille : un trigless trig prend l'état 260 (movea.w #260,a5 en 0x40021f52), écrit nulle part ailleurs.
  3. Clignotement : l'état 260 (modifié) donne les mêmes appels que 4 (origine) ; 3, 5 et 0x10004 inchangés.
  4. Démarrage (objet des LED nul, aucun relevé) puis images sans trigless trig, avec ticks, clignotement et tête de
     lecture : chaque écriture sur le port identique (valeur et étape), chaque octet verrouillé identique au même
     instant.
  5. Trigless trigs sur 5 rangées, tête de lecture et clignotement :
     - début, colonnes et étapes 1 et 2 des LED : identiques à l'origine, écriture pour écriture ;
     - étape 0 des LED : [DIR, (DATA, SET 8, CLR 0xfff7) x k, DATA], k <= 5 ; dans chaque DATA ajouté, bits 0 et 3 à
       0 et rangée 0..6 ; jamais d'adresse ou de donnée qui change avec le strobe haut, ni de strobe avec le bit 0 ou
       avec DIR != 0xffff ; au moins 272 coups de PIT3 (2,0 us) entre deux écritures ;
     - les autres LED : mêmes valeurs aux mêmes instants qu'à l'origine ;
     - chaque touche atténuée : allumée 1 cycle de 1 ms, éteinte 2 (333 Hz), jamais allumée quand l'origine est
       éteinte ; tête de lecture et clignotement : éteinte au moins aussi longtemps qu'à l'origine, au plus 4 cycles
       de plus ;
     - registres et pile rendus à chaque rte ; aucun accès invalide ; l'interruption n'écrit en mémoire que ce
       qu'écrit l'origine, plus td_last, td_cur, td_ph et la liste.
  6. Latence des interruptions de 0 à 20 us : 1/3 de lumière sur chaque fenêtre de 100 ms (à 0,01 près).
  7. Étape 0 en retard de 80 à 83 us (le compteur se recharge pendant les transactions) : toujours >= 272 coups.
     Compteur figé : l'étape 0 se termine, 64 lectures par attente.
  8. 16 trigless trigs : td_lock = les bits des 16 touches ; chacune allumée 1 cycle sur 3.
  9. États remis à zéro au milieu d'une image (0x4000602a), puis 70 ms d'interruptions et de ticks : la touche reste
     atténuée, les autres LED comme l'origine.
 10. Fin de l'image : d2-d7/a2-a6 et pile rendus.
 11. Coût de l'étape 0 selon le nombre de rangées rechargées (0 à 5) : instructions, durée modélisée (< 30 us).

    python3 tools/emu/test_trigless_dim.py --cycles model-cycles_OS1.13.syx \
        [--with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max,boot-anim \
         --syntakt Syntakt_OS1.42.syx]
"""
import argparse
import collections
import json
import pathlib
import random
import re
import struct
import sys

from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED, UC_HOOK_MEM_READ, \
    UC_HOOK_MEM_WRITE
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import sprites                      # noqa: E402
import test_sdvintage as T          # noqa: E402

TWEAK = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13" / "47-trigless-dim.json"
BASE = build.BASE
FAIL = []

STOP, STACK, OBJ, ISR_SP, STUB = 0x9f000000, 0x9e000000, 0x93000000, 0x9d000000, 0x9f001000
MUTEX = (0x40001cc4, 0x40001df6)
LED_OBJ, LED_BIT, SHADOW = 0x40fe4200, 0x4010abf8, 0x40140aa8
SEND_FN, SEND_LATCH = 0x401492f8, 0x40059fd2           # pointeur posé au démarrage (0x4000556c)
CLEAR, SET_STATE, END_FRAME = 0x4000602a, 0x40005f86, 0x40006044
BLINK, BLINK_PHASE, TICK, FLIP = 0x40005efc, 0x404a90f4, 0x4008e7ca, 0x4008e8c4
KEYS = list(range(1, 17))                              # LED logiques des 16 touches de pas
CALLEE = [mk.UC_M68K_REG_D2 + i for i in range(6)] + [mk.UC_M68K_REG_A2 + i for i in range(5)]
REGS = [mk.UC_M68K_REG_D0 + i for i in range(8)] + [mk.UC_M68K_REG_A0 + i for i in range(7)]
MASKS = (0x4018dba8, 0x40192734)                       # masques 47x47 libérés (tools/sprites.py)
HOOK = (0x40059dea, 10)                                # accroche de l'étape 0 des LED

# interruption du panneau
VEC_PIT3, VEC_SOFT = 0x40000340, 0x40000208
START, SCAN, LED, SOFT = 0x40059cd0, 0x40059d2c, 0x40059db8, 0x40059e64
RTE = {START: 0x40059d2a, SCAN: 0x40059db6, LED: 0x40059e62, SOFT: 0x40059fd0}
STEP, ROW = 0x40a79190, 0x40a79194                     # étape des LED (0..2), rangée du tour (0..6)
CALLBACKS = (0x40a7925c, 0x40a79258, 0x40a79254)       # touches, encodeurs, pads (interruption logicielle)
F_BUS = 135_168_000                                    # coups de PIT3 par seconde
P3 = 11265                                             # période de PIT3 (PMR 0x2c00 + 1) : 12 kHz
CYCLE = 12 * P3                                        # un cycle du panneau : 1,000089 ms
PT, PF = 64 * 17601, 16 * 281_601                      # tick des LED (120 Hz), image de l'interface (30 Hz)
PCNTR_COST, WAIT = 8, 272                            # WAIT : 2,0 us, comme trigless_dim.S


def check(ok, msg):
    print(f"  {'ok   ' if ok else 'ECHEC'} {msg}", flush=True)
    if not ok:
        FAIL.append(msg)


class Rig:
    """Le MAIN OS en mémoire (crochet de démarrage exécuté : copie de .data), le port du panneau et le compteur de
    PIT3 simulés, les verrous des LED modélisés."""

    def __init__(self, img, frozen=False):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
        uc.mem_map(0x40000000, 0x02400000)
        uc.mem_map(0x80000000, 0x00020000)
        uc.mem_map(0x90000000, 0x10000000)
        uc.mem_map(0x8c000000, 0x1000)                 # Rapid GPIO
        uc.mem_map(0xfc000000, 0x00100000)             # périphériques
        uc.mem_write(BASE, img)
        uc.mem_write(STUB, b"\x4e\x75")                # rts
        self.bad, self.in_irq, self.frozen = [], False, frozen
        self.t_irq, self.ic, self.reads, self.phi3, self.slot, self.clock = 0, 0, 0, 0, 0, 0
        self.data, self.dir, self.q = 0, 0xffff, [0xff] * 8
        self.qlog = [(0, tuple(self.q))]               # (instant, octets tenus par les 7 verrous)
        self.wlog = []                                 # (instant, étape 0..11, registre, valeur)
        self.hazards, self.regfail, self.isr_mem = [], [], set()
        self.led0 = []                                 # (transactions, instructions, durée, lectures du compteur)
        uc.hook_add(UC_HOOK_CODE, self._code)
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: self.bad.append(addr) or False)
        uc.hook_add(UC_HOOK_MEM_WRITE, self._port, begin=0x8c000000, end=0x8c000fff)
        uc.hook_add(UC_HOOK_MEM_READ, self._pcntr, begin=0xfc08c004, end=0xfc08c005)
        self.call(0x4000045c)
        uc.hook_add(UC_HOOK_MEM_WRITE, self._ram, begin=0x40000000, end=0x423fffff)
        self.w32(SEND_FN, SEND_LATCH)
        self.w32(LED_OBJ, OBJ)
        uc.mem_write(SHADOW, b"\xff" * 8)
        for cb in CALLBACKS:
            self.w32(cb, STUB)
        self.w32(VEC_PIT3, START)
        self.w32(STEP, 0)
        self.w32(ROW, 0)
        self.table = struct.unpack(">54l", bytes(uc.mem_read(LED_BIT, 216)))

    # -- crochets ----------------------------------------------------------------------------------------------
    def _code(self, uc, addr, size, _):
        if self.in_irq:
            self.ic += 1
        elif addr in MUTEX:
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            uc.reg_write(mk.UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)

    def now(self):
        return self.t_irq + self.ic + self.reads * PCNTR_COST

    def _pcntr(self, uc, access, addr, size, value, _):
        self.reads += 1
        v = 1234 if self.frozen else P3 - 1 - (self.now() - self.phi3) % P3
        uc.mem_write(0xfc08c004, struct.pack(">H", v))

    def _ram(self, uc, access, addr, size, value, _):
        if self.in_irq:
            self.isr_mem.add(addr)

    def _port(self, uc, access, addr, size, value, _):
        t, reg, v, old = self.now(), addr - 0x8c000000, value & 0xffff, self.data
        self.wlog.append((t, self.slot, reg, v))
        if reg == 0:
            self.dir = v
            return
        new = {2: v, 6: old & v, 0xa: old | v}.get(reg)
        if new is None:
            self.hazards.append((t, f"registre {reg:#x}"))
            return
        ch = (old ^ new) & 0xfff7
        if old & 8 and new & 8 and ch:
            self.hazards.append((t, "adresse ou donnée changée strobe haut", hex(old), hex(new)))
        if not old & 8 and new & 8 and ch:
            self.hazards.append((t, "strobe levé avec un changement d'adresse ou de donnée", hex(old), hex(new)))
        if new & 8 and new & 1:
            self.hazards.append((t, "strobe des LED avec le balayage des touches", hex(new)))
        if new & 8 and self.dir != 0xffff:
            self.hazards.append((t, "strobe des LED avec DIR != 0xffff", hex(self.dir)))
        if new & 8 and (new >> 5) & 7 == 7:
            self.hazards.append((t, "strobe sur l'adresse 7", hex(new)))
        self.data = new
        if new & 8 and not new & 1:
            row = (new >> 5) & 7
            if self.q[row] != new >> 8:
                self.q[row] = new >> 8
                self.qlog.append((t, tuple(self.q)))

    # -- outils ------------------------------------------------------------------------------------------------
    def r32(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def w32(self, a, v):
        self.uc.mem_write(a, struct.pack(">I", v & 0xffffffff))

    def call(self, fn, *args, regs=None):
        sp = STACK - 4 * (len(args) + 1)
        self.uc.mem_write(sp, struct.pack(">I", STOP) + b"".join(struct.pack(">I", a & 0xffffffff) for a in args))
        self.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        for r, v in (regs or {}).items():
            self.uc.reg_write(r, v)
        self.uc.emu_start(fn, STOP, count=50_000_000)
        return self.uc.reg_read(mk.UC_M68K_REG_D0)

    def frame(self, states):
        """Une image de l'interface : remise à zéro, états posés, fin de l'image."""
        self.call(CLEAR, OBJ)
        for idx, st in states.items():
            self.call(SET_STATE, OBJ, idx, st, 0x404a8cb8)
        self.call(END_FRAME, OBJ)

    def irq(self, handler, t, rng):
        """Une interruption : registres au hasard, pile à part, jusqu'au rte."""
        uc = self.uc
        self.t_irq, self.ic, self.reads = t, 0, 0
        uc.reg_write(mk.UC_M68K_REG_A7, ISR_SP)
        seed = [rng.getrandbits(32) for _ in REGS]
        for rg, v in zip(REGS, seed):
            uc.reg_write(rg, v)
        self.in_irq = True
        uc.emu_start(handler, RTE[handler], count=100_000)
        self.in_irq = False
        if [uc.reg_read(rg) for rg in REGS] != seed or uc.reg_read(mk.UC_M68K_REG_A7) != ISR_SP \
                or uc.reg_read(mk.UC_M68K_REG_PC) != RTE[handler]:
            self.regfail.append((t, hex(handler)))

    def pit3(self, t, rng):
        h, slot = self.r32(VEC_PIT3), self.slot
        led0 = h == LED and self.r32(STEP) == 0
        n0 = len(self.wlog)
        self.irq(h, t, rng)
        if led0:
            k = sum(1 for w in self.wlog[n0:] if w[2] == 0xa)
            self.led0.append((k, self.ic, self.now() - t, self.reads))
        if self.r32(0xfc04c014) & 4:                   # interruption logicielle forcée (niveau 3, juste après)
            self.slot = 12
            self.irq(SOFT, self.now() + 10, rng)
        self.slot = (slot + 1) % 12


def timeline(rig, seconds, seed, states, lat_us=0.0, led0_lat=None, events=(), frames=True, blinks=True):
    """Interruptions du panneau, ticks, images, clignotement et événements (instants en s depuis le début de cet
    appel), dans l'ordre du temps ; reprend là où l'appel précédent s'est arrêté. Rend l'instant de la fin."""
    rng = random.Random(seed)
    if rig.clock == 0:
        rig.phi3 = rng.randrange(P3)
    start = rig.clock
    end = rig.clock = start + int(seconds * F_BUS)
    phi2, phif = start + rng.randrange(PT), start + rng.randrange(PF)
    ev, k = [], max(0, -(-(start - rig.phi3) // P3))
    while rig.phi3 + k * P3 < end:
        lat = rng.uniform(0, lat_us) if lat_us else 0.0
        if led0_lat and k % 12 == 9:
            lat = rng.uniform(*led0_lat)
        ev.append((rig.phi3 + k * P3 + int(lat * F_BUS / 1e6), 0, None))
        k += 1
    m = 0
    while phi2 + m * PT < end:
        ev.append((phi2 + m * PT + rng.randrange(int(0.0002 * F_BUS)), 1, None))
        m += 1
    j = 0
    while frames and phif + j * PF < end:
        ev.append((phif + j * PF, 2, None))
        j += 1
    b = 0
    while frames and blinks and phif + 1000 + b * (F_BUS // 2) < end:
        ev.append((phif + 1000 + b * (F_BUS // 2), 3, None))
        b += 1
    for ts, fn in events:
        ev.append((start + int(ts * F_BUS), 4, fn))
    ev.sort(key=lambda e: (e[0], e[1]))
    if frames:
        rig.frame(states)
    for t, kind, fn in ev:
        if kind == 0:
            rig.pit3(t, rng)
        elif kind == 1:
            rig.call(TICK)
        elif kind == 2:
            rig.frame(states)
        elif kind == 3:
            rig.call(BLINK, OBJ)
        else:
            fn(rig)
    return end


def wave(qlog, bit, t_end):
    """[(début, fin, allumée)] d'un bit de LED (allumée = bit verrouillé à 0)."""
    row, b = bit >> 3, bit & 7
    runs, cur, t0 = [], None, 0
    for t, q in qlog:
        lit = not (q[row] >> b) & 1
        if lit != cur:
            if cur is not None:
                runs.append((t0, t, cur))
            cur, t0 = lit, t
    runs.append((t0, t_end, cur))
    return runs


def lit_time(w, lo, hi):
    return sum(max(0, min(t1, hi) - max(t0, lo)) for t0, t1, lit in w if lit)


# -- 1-3 : écritures, mode grille, clignotement ----------------------------------------------------------------
def writes_ok(stock, img, tweak, others):
    for w in tweak["writes"]:
        o, old = w["off"], bytes.fromhex(w["old"])
        check(stock[o:o + len(old)] == old, f"octets d'origine en {o + BASE:#x} ({len(old)} o)")
    for mask in MASKS:
        size, ref, _, shared = sprites.MASKS[mask]
        check(stock[mask - BASE:mask - BASE + size] == stock[shared - BASE:shared - BASE + size],
              f"masque {mask:#x} identique au masque gardé {shared:#x}")
        refs = [m.start() + BASE for m in re.finditer(re.escape(struct.pack(">I", mask)), stock)]
        check(refs == [ref] and img[ref - BASE:ref - BASE + 4] == struct.pack(">I", shared),
              f"seule référence au masque {mask:#x} : la constante de son constructeur ({ref:#x}), redirigée")
    clash = []
    for t in others:
        for v in t["writes"]:
            a, b = v["off"], v["off"] + len(v["old"]) // 2
            for w in tweak["writes"]:
                c, d = w["off"], w["off"] + len(w["old"]) // 2
                if a < d and c < b and (v["off"], v["new"]) != (w["off"], w["new"]):
                    clash.append(f"{t['id']}@{a + BASE:#x}")
    check(not clash, f"aucun autre tweak n'écrit autre chose sur ces octets ({len(others)} tweaks) {clash[:4]}")
    lo, hi = 0x40059c00 - BASE, 0x4005a140 - BASE
    h0, h1 = HOOK[0] - BASE, HOOK[0] - BASE + HOOK[1]
    check(img[lo:h0] == stock[lo:h0] and img[h1:hi] == stock[h1:hi],
          "interruption du panneau (0x40059c00..0x4005a140) identique à l'origine, sauf les 10 octets de l'accroche")
    lo, hi = 0x4008e700 - BASE, 0x4008eac0 - BASE
    check(img[lo:hi] == stock[lo:hi], "tick, comparaison et envoi des LED (0x4008e700..0x4008eac0) : d'origine")
    hits = []
    for i in range(0, len(stock) - 6, 2):
        w = struct.unpack_from(">H", stock, i)[0]
        if w >> 12 == 6:
            b, pc = w & 0xff, i + BASE + 2
            t = pc + (struct.unpack_from(">h", stock, i + 2)[0] if b == 0 else
                      struct.unpack_from(">i", stock, i + 2)[0] if b == 0xff else (b - 256 if b > 127 else b))
            if HOOK[0] < t < HOOK[0] + HOOK[1]:
                hits.append(hex(i + BASE))
        if HOOK[0] < struct.unpack_from(">I", stock, i)[0] < HOOK[0] + HOOK[1]:
            hits.append(hex(i + BASE))
    check(not hits, f"aucun branchement ni constante vers l'intérieur de l'accroche (0x40059dec..0x40059df3) {hits[:4]}")
    i = 0x40021f52 - BASE
    check(img[i:i + 4] == bytes.fromhex("3a7c0104"), "mode grille, trigless trig : movea.w #260,a5 en 0x40021f52")
    imm = [m.start() + BASE for m in re.finditer(re.escape(bytes.fromhex("0104")), img)
           if img[m.start() - 2:m.start()] in (b"\x3a\x7c", b"\x2a\x7c", b"\x7a\x00")]
    check(imm == [0x40021f54], f"l'état 260 n'est écrit qu'en 0x40021f52 (movea #260 : {[hex(a) for a in imm]})")


def blink(base, img):
    out = {}
    for name, im, lock in (("origine", base, 4), ("modifié", img, 260)):
        for phase in (0, 1):
            r = Rig(im)
            calls = []

            def h(uc, addr, size, _, calls=calls):
                sp = uc.reg_read(mk.UC_M68K_REG_A7)
                _, a1, a2 = struct.unpack(">III", uc.mem_read(sp, 12))
                calls.append((a1, a2))
            r.uc.hook_add(UC_HOOK_CODE, h, begin=FLIP, end=FLIP)
            for idx, st in {1: 2, 2: 3, 3: lock, 4: 1, 5: 5, 6: 0x10004}.items():
                r.w32(OBJ + 40 + 4 * idx, st)
            r.w32(BLINK_PHASE, phase)
            r.call(BLINK, OBJ)
            out[name, phase] = (calls, r.r32(BLINK_PHASE))
    for phase in (0, 1):
        check(out["origine", phase] == out["modifié", phase],
              f"clignotement, phase {phase} : mêmes appels de 0x4008e8c4 (état 4 / 260) {out['modifié', phase][0]}")


# -- 4 : sans trigless trig --------------------------------------------------------------------------------------
def no_dim(base, img):
    res = {}
    for name, im in (("origine", base), ("modifié", img)):
        r = Rig(im)
        r.w32(LED_OBJ, 0)                              # démarrage : pas encore d'objet des LED, pas d'image
        timeline(r, 0.25, 3, {}, frames=False)
        n_boot = len(r.wlog)
        r.w32(LED_OBJ, OBJ)
        flips = [(0.40, lambda s: s.call(FLIP, 8, 6)), (0.45, lambda s: s.call(FLIP, 2, 42))]
        timeline(r, 0.6, 7, {1: 2, 2: 3, 5: 4, 8: 2}, events=flips)
        res[name] = (r, n_boot)
    (a, na), (b, nb) = res["origine"], res["modifié"]
    check([w[1:] for w in a.wlog[:na]] == [w[1:] for w in b.wlog[:nb]] and na > 3000,
          f"démarrage (pointeur des LED nul) : {na} écritures sur le port, identiques à l'origine (valeur, étape)")
    check([w[1:] for w in a.wlog] == [w[1:] for w in b.wlog] and len(a.wlog) > 10000,
          f"sans trigless trig : chaque écriture sur le port identique à l'origine ({len(a.wlog)} écritures)")
    check(a.qlog == b.qlog and len(a.qlog) > 10, f"sans trigless trig : octets verrouillés identiques, aux mêmes "
                                                 f"instants ({len(a.qlog)} changements)")
    check(not a.hazards and not b.hazards and not a.regfail and not b.regfail and not a.bad and not b.bad,
          "aucun danger sur les verrous, registres et pile rendus, aucun accès invalide")
    return b


# -- 5-7 : trigless trigs ----------------------------------------------------------------------------------------
def led0_writes(rig):
    """Les écritures de chaque étape 0 des LED (étape 9 du cycle)."""
    out, cur = [], None
    for t, slot, reg, v in rig.wlog:
        if slot == 9:
            if reg == 0 or cur is None:
                cur = []
                out.append(cur)
            cur.append((t, reg, v))
    return out


def gaps(rig):
    g = []
    for ws in led0_writes(rig):
        g += [ws[i][0] - ws[i - 1][0] for i in range(2, len(ws))]
    return g


def dim(base, img, syms):
    table = Rig(base).table
    dim_keys = [1, 3, 8, 11, 13, 16]
    rows = sorted({table[k] >> 3 for k in dim_keys})
    st_o = {1: 4, 3: 4, 8: 4, 11: 4, 13: 4, 16: 4, 2: 2, 4: 3, 9: 2, 14: 2}
    st_m = {k: (260 if v == 4 else v) for k, v in st_o.items()}
    events = [(0.40, lambda s: s.call(FLIP, 8, 6)),    # tête de lecture sur une touche atténuée (6 ticks)
              (0.40, lambda s: s.call(FLIP, 6, 6)),    # ... et sur une touche éteinte
              (0.90, lambda s: s.call(FLIP, 13, 42))]  # clignotement d'origine (0,35 s) d'une touche atténuée
    seconds = 1.5
    res = {}
    for name, im, st in (("origine", base, st_o), ("modifié", img, st_m)):
        r = Rig(im)
        end = timeline(r, seconds, 11, st, events=events)
        res[name] = r
    a, b = res["origine"], res["modifié"]
    print(f"     touches atténuées {dim_keys} : rangées {rows}")
    check(not a.hazards and not b.hazards, f"aucun danger sur les verrous {b.hazards[:2]}")
    check(not a.regfail and not b.regfail and not a.bad and not b.bad,
          "registres d0-d7/a0-a6 et pile rendus à chaque rte, aucun accès invalide")
    lo, hi = int(syms["td_last"], 16), int(syms["td_lock"], 16) + 42
    extra = sorted(x for x in b.isr_mem - a.isr_mem if not lo <= x < hi)
    check(not extra, f"l'interruption n'écrit que ce qu'écrit l'origine, plus l'état du mod {[hex(x) for x in extra[:4]]}")

    def other(rig):
        return [(w[1], w[2], w[3]) for w in rig.wlog if w[1] != 9]
    check(other(a) == other(b) and len(other(a)) > 15000,
          f"début, colonnes, étapes 1 et 2 des LED : identiques à l'origine, écriture pour écriture ({len(other(a))})")
    la, lb = led0_writes(a), led0_writes(b)
    ok, ks = len(la) == len(lb), collections.Counter()
    for x, y in zip(la, lb):
        k = (len(y) - 2) // 3
        ks[k] += 1
        ok &= len(x) == 2 and x[0][1:] == y[0][1:] == (0, 0xffff) and len(y) == 2 + 3 * k and k <= 5
        ok &= y[-1][1] == 2 and (x[1][2] & 0xff) == (y[-1][2] & 0xff)
        for i in range(k):
            d, s, c = y[1 + 3 * i:4 + 3 * i]
            ok &= d[1] == 2 and not d[2] & 9 and (d[2] >> 5) & 7 < 7 and s[1:] == (0xa, 8) and c[1:] == (6, 0xfff7)
    check(ok, f"étape 0 : origine [DIR, DATA] ; modifié [DIR, (DATA, SET 8, CLR 0xfff7) x k, DATA], k <= 5 "
              f"({len(la)} étapes, k : {dict(sorted(ks.items()))})")
    g = gaps(b)
    check(g and min(g) >= WAIT, f"au moins {WAIT} coups de PIT3 entre deux écritures de l'étape 0 (minimum {min(g)})")
    dimbits = {table[k] for k in dim_keys}
    others = [bit for bit in range(56) if bit not in dimbits]
    check(all(wave(a.qlog, x, end) == wave(b.qlog, x, end) for x in others),
          f"les {len(others)} autres bits de LED : mêmes valeurs aux mêmes instants qu'à l'origine")

    allon, alloff, bad, dark = collections.Counter(), collections.Counter(), 0, []
    for key in dim_keys:
        wa, wb = wave(a.qlog, table[key], end), wave(b.qlog, table[key], end)
        bad += sum(1 for t0, t1, lit in wb if lit and lit_time(wa, t0, t1) != t1 - t0)
        for i, (t0, t1, lit) in enumerate(wb[1:-1], 1):
            steady = lit_time(wa, t0 - 3 * CYCLE, t1 + 3 * CYCLE) == t1 - t0 + 6 * CYCLE
            if steady:
                (allon if lit else alloff)[round((t1 - t0) / CYCLE, 1)] += 1
        for t0, t1, lit in wa[1:-1]:
            if not lit:                                # éteinte à l'origine : tête de lecture ou clignotement
                run = [(u0, u1) for u0, u1, l in wb if not l and u0 <= t0 and u1 >= t1]
                dark.append((key, (t1 - t0) / CYCLE, (run[0][1] - run[0][0]) / CYCLE if run else None))
    print(f"     allumée (cycles de 1 ms) : {dict(allon)} ; éteinte : {dict(alloff)}")
    check(set(allon) == {1.0} and set(alloff) == {2.0} and sum(allon.values()) > 2000,
          "touches atténuées : allumées 1 cycle, éteintes 2 (333 Hz, 1/3), en régime établi")
    check(bad == 0, "jamais allumée quand l'origine est éteinte")
    print("     éteinte (tête de lecture, clignotement), cycles : "
          + ", ".join(f"touche {k} : {o:.1f} -> {m:.1f}" for k, o, m in dark))
    check(len(dark) >= 2 and all(m is not None and o <= m <= o + 4 for _, o, m in dark),
          "tête de lecture et clignotement : éteinte au moins aussi longtemps qu'à l'origine, au plus 4 cycles de plus")

    r = Rig(img)                                       # latence des interruptions
    end = timeline(r, 1.0, 23, st_m, lat_us=20.0, blinks=False)
    duty = []
    for key in dim_keys:
        w = wave(r.qlog, table[key], end)
        duty += [lit_time(w, t, t + F_BUS // 10) / (F_BUS // 10) for t in range(F_BUS // 10, end - F_BUS // 10,
                                                                                  F_BUS // 20)]
    g = gaps(r)
    check(min(duty) > 0.323 and max(duty) < 0.343 and min(g) >= WAIT and not r.hazards,
          f"latence de 0 à 20 us : 1/3 de lumière sur chaque fenêtre de 100 ms ({min(duty):.4f} à {max(duty):.4f}), "
          f"écritures espacées d'au moins {min(g)} coups")

    r = Rig(img)                                       # étape 0 en retard : rechargement du compteur
    timeline(r, 0.3, 29, st_m, led0_lat=(80.0, 83.0), blinks=False)
    g, wrapped = gaps(r), sum(1 for ws in led0_writes(r) if len(ws) > 2 and
                              (ws[-1][0] - r.phi3) // P3 != (ws[0][0] - r.phi3) // P3)
    check(min(g) >= WAIT and wrapped > 100, f"étape 0 en retard de 80 à 83 us : compteur rechargé pendant {wrapped} "
                                           f"étapes, écritures toujours espacées d'au moins {min(g)} coups")

    r = Rig(img, frozen=True)                          # compteur figé
    timeline(r, 0.05, 31, st_m)
    with_k = [x for x in r.led0 if x[0]]
    check(with_k and not r.regfail and all(x[3] == 3 * 64 * x[0] for x in with_k),
          f"compteur de PIT3 figé : chaque étape 0 se termine, 64 lectures par attente "
          f"({max(x[2] for x in with_k) / F_BUS * 1e6:.0f} us modélisés au pire)")
    return a, b


def sixteen(base, img, syms):
    r = Rig(img)
    end = timeline(r, 0.5, 41, {k: 260 for k in KEYS}, blinks=False)
    lock = bytes(r.uc.mem_read(int(syms["td_lock"], 16), 8))
    bits = sorted(x for x in range(64) if lock[x >> 3] >> (x & 7) & 1)
    check(bits == sorted(r.table[k] for k in KEYS), f"16 trigless trigs : td_lock = les bits des 16 touches {bits}")
    runs = collections.Counter()
    for k in KEYS:
        w = wave(r.qlog, r.table[k], end)
        runs.update((lit, round((t1 - t0) / CYCLE, 1)) for t0, t1, lit in w[2:-1])
    check(set(runs) == {(True, 1.0), (False, 2.0)}, f"16 trigless trigs : chaque touche allumée 1 cycle, éteinte 2 "
                                                    f"({sum(runs.values())} passages)")
    ks = collections.Counter(x[0] for x in r.led0)
    rows = sorted({r.table[k] >> 3 for k in KEYS})
    print(f"     rangées {rows} ; rangées rechargées par étape 0 : {dict(sorted(ks.items()))}")
    return r


def midframe(base, img):
    res = {}
    for name, im, lock in (("origine", base, 4), ("modifié", img, 260)):
        r = Rig(im)
        r.frame({1: 2, 3: lock})
        timeline(r, 0.05, 43, {}, frames=False)
        r.call(CLEAR, OBJ)                             # image commencée : états à zéro, mode grille pas passé
        end = timeline(r, 0.07, 47, {}, frames=False)
        res[name] = (r, end)
    (a, end), (b, _) = res["origine"], res["modifié"]
    bit3, others = a.table[3], [x for x in range(56) if x != a.table[3]]
    runs = collections.Counter((lit, round((t1 - t0) / CYCLE, 1)) for t0, t1, lit in wave(b.qlog, bit3, end)[2:-1])
    check(set(runs) == {(True, 1.0), (False, 2.0)}, f"états remis à zéro au milieu d'une image, 70 ms : la touche "
                                                    f"reste atténuée {dict(runs)}")
    check(wave(a.qlog, bit3, end)[-1][2] and all(wave(a.qlog, x, end) == wave(b.qlog, x, end) for x in others),
          "origine : allumée à fond ; les autres LED comme l'origine")


def frame_regs(img):
    r = Rig(img)
    pre = {reg: 0x01010101 * (k + 1) for k, reg in enumerate(CALLEE)}
    r.call(CLEAR, OBJ)
    for i in KEYS:
        r.call(SET_STATE, OBJ, i, 260, 0x404a8cb8)
    r.call(END_FRAME, OBJ, regs=pre)
    post = {reg: r.uc.reg_read(reg) for reg in CALLEE}
    check(post == pre and r.uc.reg_read(mk.UC_M68K_REG_A7) == STACK - 4,
          "fin de l'image : d2-d7/a2-a6 et pile rendus")


def cost(a, b, r16, r0):
    stock = collections.Counter(x[1] for x in a.led0)
    fast = collections.Counter(x[1] for x in r0.led0)
    by = collections.defaultdict(list)
    for x in b.led0 + r16.led0:
        by[x[0]].append(x)
    print(f"     étape 0 des LED, origine : {min(stock)}..{max(stock)} instructions ; modifié sans trigless trig : "
          f"{min(fast)}..{max(fast)}")
    worst = 0
    for k in sorted(by):
        xs = by[k]
        us = [x[2] / F_BUS * 1e6 for x in xs]
        worst = max(worst, max(us))
        print(f"     {k} rangée(s) rechargée(s) : {min(x[1] for x in xs)}..{max(x[1] for x in xs)} instructions, "
              f"{min(us):.1f}..{max(us):.1f} us modélisés ({len(xs)} étapes)")
    per_ms = sum(x[2] for x in r16.led0) / len(r16.led0) / F_BUS * 1e6
    print(f"     16 trigless trigs : {per_ms:.1f} us par ms en moyenne ({per_ms / 10:.2f} % du processeur, niveau 6)")
    check(worst < 30, f"durée de l'étape 0 bornée (< 30 us modélisés, au pire {worst:.1f} us)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True)
    ap.add_argument("--with", dest="others", default="", help="autres tweaks appliqués avant (ex. 6ch-usbup,model-tg)")
    ap.add_argument("--syntakt", help="Syntakt_OS1.42.syx (ou 1.41), pour les moteurs du Syntakt")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    files = {json.loads(f.read_text(encoding="utf-8"))["id"]: f for f in TWEAK.parent.glob("[0-9]*.json")}
    every = [json.loads(f.read_text(encoding="utf-8")) for i, f in files.items() if i != "trigless-dim"]
    tweaks = [json.loads(files[i].read_text(encoding="utf-8")) for i in args.others.split(",") if i]
    tweak = json.loads(TWEAK.read_text(encoding="utf-8"))
    pl, _ = build.build_payload(tweaks, stock, args.syntakt)  # Model-TG : son code est ajouté après l'image
    base = build.apply_writes(stock, sorted(tweaks, key=lambda t: t["order"]))[0] + pl
    img = build.apply_writes(stock, sorted(tweaks + [tweak], key=lambda t: t["order"]))[0] + pl
    syms = tweak["symbols"]
    print(f"firmware : {', '.join(t['id'] for t in sorted(tweaks + [tweak], key=lambda t: t['order']))}")
    print("1-2. écritures")
    writes_ok(stock, img, tweak, every)
    print("3. clignotement (0x40005efc)")
    blink(base, img)
    print("4. démarrage et images sans trigless trig")
    r0 = no_dim(base, img)
    print("5-7. trigless trigs sur 5 rangées")
    a, b = dim(base, img, syms)
    print("8. 16 trigless trigs")
    r16 = sixteen(base, img, syms)
    print("9. états remis à zéro au milieu d'une image")
    midframe(base, img)
    print("10. fin de l'image")
    frame_regs(img)
    print("11. coût")
    cost(a, b, r16, r0)
    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ÉCHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
