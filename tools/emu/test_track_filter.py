#!/usr/bin/env python3
"""Banc d'émulation du filtre par piste (notes/47, tweaks/model-cycles_OS1.13/48-track-filter.json).

Le MAIN OS modifié tourne dans Unicorn (ColdFire + EMAC émulée, mcengine.py) ; on le compare à l'OS sans le filtre
(l'officiel, ou l'officiel avec les autres tweaks de --with).

Le son : la vraie boucle des 6 voix (0x400a7d4a), puis le vrai site H3 de la fonction audio 0x4005979e
(0x4005984a..0x40059858 : move.l a2,(sp) ; pea 0x80001858 ; jsr), avec a2 = les mots lissés des pistes et a3 = un
contexte dont +16 porte les pistes déclenchées dans le bloc, comme l'OS les passe à la boucle des voix.
  - filtre au centre (Filter Cutoff = OFF) : les 6 pistes identiques bit pour bit à l'OS sans le filtre, même avec une
    enveloppe et une résonance réglées ; registres d2-d7/a2-a6, pile, MACSR et accumulateurs rendus comme l'appel
    d'origine ;
  - filtre en marche (LP, HP, pas voisin du centre, résonance, enveloppe montante et descendante, balayage qui passe
    d'un côté à l'autre) : la sortie comparée à un modèle en flottant double du même filtre, nourri par la sortie de
    l'OS sans le filtre ;
  - l'enveloppe (relance à chaque note, décroissance par bloc) comparée à la loi de tools/gen_track_filter.py ;
  - fréquence et Q tirés des coefficients calculés par le code, comparés à la loi (Model:Samples) ;
  - coût : instructions exécutées dans notre code, par bloc.
L'interface et la sauvegarde, fonction par fonction (image + BSS) :
  - MACHINES tenu + COLOR / SHAPE / SWEEP / CONTOUR -> nos descripteurs 3, 4, 1, 2 ; sinon la recherche d'origine ;
  - l'affichage des valeurs (objets d'interface construits par le vrai constructeur 0x400de244, vrai sprintf) ;
  - les tables des paramètres construites au démarrage (0x4004486c -> tf_boot -> 0x4005a274) : k 28..31 sur toutes
    les machines, CC 74 / 71, NRPN 1:20 / 1:21, rien d'autre de changé ; avec les moteurs du Syntakt, nos descripteurs
    recopiés dans leur table déplacée ;
  - un son sauvegardé puis rechargé (0x4005afa0, 0x4005b054, 0x4005aecc) : les quatre réglages et les destinations du
    LFO et de la vélocité vers eux reviennent ; un son d'avant le filtre se charge filtre OFF ;
  - les p-locks du pattern (sauvegarde 0x4005b95c, mise à jour 0x4005ba90, chargement 0x4005b766) : k 23..31
    reviennent sur eux-mêmes ; les autres fichiers identiques à l'OS sans le filtre.

    python3 tools/emu/test_track_filter.py --cycles model-cycles_OS1.13.syx
        [--with 6ch-usbup,syntakt-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max,boot-anim --syntakt Syntakt_OS1.42.syx]
"""
import argparse
import json
import math
import pathlib
import struct
import sys

import numpy as np
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import gen_track_filter as G        # noqa: E402
import mcengine as E                # noqa: E402
import test_sdvintage as T          # noqa: E402

TWEAK = G.OUT
BASE = E.BASE
CODE = [(G.CAVES[s], 280) for s in (".tf_post", ".tf_track", ".tf_kern", ".tf_coef1", ".tf_coef2", ".tf_knob",
                                     ".tf_fmt", ".tf_save", ".tf_load")]
H3_FROM, H3_TO = 0x4005984a, 0x40059858
CTX = 0x40760000                    # contexte factice de la fonction audio (+16 : pistes déclenchées)
KST, KSZ, CST, CSZ = G.CAVES[".tf_kst"], 36, G.CAVES[".tf_cst"], 20
NAMES = ["KICK", "SNARE", "METAL", "PERC", "TONE", "CHORD"]
SAVED = [mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4, mk.UC_M68K_REG_D5, mk.UC_M68K_REG_D6,
         mk.UC_M68K_REG_D7, mk.UC_M68K_REG_A4, mk.UC_M68K_REG_A5, mk.UC_M68K_REG_A6]
FAIL = []


def check(ok, msg):
    print(("  ok    " if ok else "  ECHEC ") + msg, flush=True)
    if not ok:
        FAIL.append(msg)
    return ok


def db(err, peak):
    return 20 * math.log10(max(err, 1e-30) / max(peak, 1e-30))


# ---- le son : boucle des voix puis le site H3 ---------------------------------------------------------------------
class Audio:
    def __init__(self, img, payload=None, count=False):
        e = self.e = E.Engine(img, extra_code=CODE, payload=payload)
        e.uc.mem_map(0x40800000, 0x01800000)          # BSS de l'OS
        self.contract = True
        self.instr = 0
        if count:
            def hk(uc, a, s, u):
                self.instr += 1
            for va, n in CODE:
                e.uc.hook_add(UC_HOOK_CODE, hk, begin=va, end=va + n - 1)

    def setw(self, t, k, v):
        self.e.uc.mem_write(E.PARAMS + 0xe + 0x42 * t + 2 * k, struct.pack(">h", v))

    def filt(self, t, c=0x4000, r=0, a=0x4000, d=0x4000):
        for k, v in zip((28, 29, 30, 31), (c, r, a, d)):
            self.setw(t, k, v)

    def block(self, trig=0):
        e, uc = self.e, self.e.uc
        e.block(trig)
        uc.mem_write(CTX + 16, struct.pack(">I", trig))
        sp0 = E.STACK - 0x300
        uc.mem_write(sp0, struct.pack(">I", 0xdeadbeef))
        marks = {r: 0x1111 * (i + 1) for i, r in enumerate(SAVED)}
        for r, v in marks.items():
            uc.reg_write(r, v)
        uc.reg_write(mk.UC_M68K_REG_A2, E.PARAMS)
        uc.reg_write(mk.UC_M68K_REG_A3, CTX)
        uc.reg_write(mk.UC_M68K_REG_A7, sp0)
        e.emac.macsr = 0x20
        e.emac.acc[:] = [0, 0, 0, 0]
        uc.emu_start(H3_FROM, H3_TO, count=2_000_000)
        ok = all(uc.reg_read(r) == v for r, v in marks.items())
        ok &= uc.reg_read(mk.UC_M68K_REG_A2) == E.PARAMS and uc.reg_read(mk.UC_M68K_REG_A3) == CTX
        ok &= uc.reg_read(mk.UC_M68K_REG_A7) == sp0 - 4
        ok &= struct.unpack(">II", uc.mem_read(sp0 - 4, 8)) == (E.TRACK_BASE, E.PARAMS)
        ok &= e.emac.macsr == 0x20 and not any(e.emac.acc)
        self.contract &= ok
        return np.frombuffer(bytes(uc.mem_read(E.TRACK_BASE, 6 * 128)), dtype=">i4").reshape(6, 32).astype(np.int64)

    def cst(self, t):
        """(clé, décalage de l'enveloppe, en marche, enveloppe, côté) de la piste t."""
        return struct.unpack(">IiiIi", self.e.uc.mem_read(CST + CSZ * t, CSZ))

    def kst(self, t):
        """ic1 ic2 b1 b2 c2 a3 gx/2 hl hb de la piste t (Q31)."""
        return struct.unpack(">9i", self.e.uc.mem_read(KST + KSZ * t, KSZ))


def voices(a, decay=90):
    for t in range(6):
        a.e.machine_defaults(t, t)
        a.e.set(t, note=48 + 3 * t, decay=decay)


def run(img, payload, blocks, trigs, setup, per_block=None, count=False, decay=90):
    """Rend (sorties [bloc, piste, 32], états {piste: [(e, décalage)]}, Audio, instructions par bloc)."""
    a = Audio(img, payload, count)
    voices(a, decay)
    setup(a)
    out, env, cost = [], {t: [] for t in range(6)}, []
    for b in range(blocks):
        if per_block:
            per_block(a, b)
        n0 = a.instr
        out.append(a.block(trigs.get(b, 0)))
        cost.append(a.instr - n0)
        for t in range(6):
            c = a.cst(t)
            env[t].append((c[3], c[1]))
    return np.stack(out), env, a, cost


# ---- modèle flottant du même filtre (notes/47 §5) ------------------------------------------------------------
TAB = {n: [v for v in vals] for n, vals in G.TABLES.items()}


def interp(name, i, s):
    """Comme tf_interp : interpolation linéaire entière (EMAC fractionnaire, troncature)."""
    t = TAB[name]
    j, f = i >> s, (i << (31 - s)) & 0x7fffffff
    return t[j] + (((t[j + 1] - t[j]) * f) >> 31)


class Model:
    def __init__(self):
        self.on, self.key, self.ic1, self.ic2 = False, None, 0.0, 0.0

    def coef(self, c, r, d6):
        d = c - 0x4000
        self.mode, idx = (0, c) if d < 0 else (1, d)
        w = 1.0 if abs(d) >= 0x100 else abs(d) / 256
        i = min(max(idx + d6, 0), 0x3fff)
        g = 4 * interp("TABLE_G", i, 8) / 2 ** 31
        reff = (max(r, 0) * interp("TABLE_N", i, 8)) >> 31
        k = 2 * interp("TABLE_K", reff, 9) / 2 ** 31
        a1 = 1 / (1 + g * (g + k))
        a2 = g * a1
        a3 = g * a2
        self.b1, self.b2, self.c2, self.a3 = 2 * a1 - 1, 2 * a2, 1 - 2 * a3, a3
        self.gx, self.hl, self.hb = ((1 - w), w / 2, 0.0) if self.mode == 0 else (1.0, -w / 2, -w * k / 2)

    def block(self, xi, c, r, d6):
        """xi : 32 entiers (Q31) ; rend 32 flottants (échelle Q31)."""
        if c == 0x4000:
            self.on = False
            return xi.astype(np.float64)
        if (c, r, d6) != self.key:
            self.key = (c, r, d6)
            self.coef(c, r, d6)
        x = xi.astype(np.float64) / 2 ** 31
        if not self.on:
            self.on = True
            self.ic1, self.ic2 = 0.0, (x[0] if self.mode == 0 else 0.0)
        elif not xi.any() and max(abs(self.ic1), abs(self.ic2)) < 0x1000 / 2 ** 31:
            self.ic1 = self.ic2 = 0.0
            return xi.astype(np.float64)
        y = np.empty(32)
        ic1, ic2 = self.ic1, self.ic2
        for n in range(32):
            i1 = self.b1 * ic1 + self.b2 * (x[n] - ic2)
            i2 = self.c2 * ic2 + self.b2 * ic1 + 2 * self.a3 * x[n]
            y[n] = self.gx * x[n] + self.hl * (ic2 + i2) + self.hb * (ic1 + i1)
            ic1, ic2 = i1, i2
        self.ic1, self.ic2 = ic1, ic2
        return y * 2 ** 31


# ---- 1. le son ----------------------------------------------------------------------------------------------------
TRIGS = {1: 0x3f, 100: 0x3f, 180: 0x15}
BLOCKS = 240


def centre_tests(base, img, payload):
    print("au centre (Filter Cutoff = OFF) : la piste n'est pas touchée")
    for vol in (0x4000, 0x6c00):
        def setup(a):
            for t in range(6):
                a.setw(t, 19, vol)
                a.filt(t, c=0x4000, r=0x1000 * t, a=(0x7f00, 0, 0x6000, 0x2000, 0x4000, 0x7f00)[t], d=0x800 * t)
        x, _, a0, _ = run(base, payload, BLOCKS, TRIGS, setup)
        y, _, a1, _ = run(img, payload, BLOCKS, TRIGS, setup)
        check(np.array_equal(x, y) and np.abs(x).max() > 1e8,
              f"Volume + Dist {vol >> 8:3d} : les 6 pistes identiques bit pour bit sur {BLOCKS} blocs (3 séries de notes, "
              f"enveloppe et résonance réglées), crête {np.abs(x).max() / 2 ** 31:.2f} FS")
        check(a1.contract, "à chaque bloc : d2-d7/a2-a6 gardés, 0x80001858 et a2 laissés sur la pile comme l'appel "
                           "d'origine, MACSR rendu à 0x20, accumulateurs à zéro")
        check(not a0.e.unmapped and not a1.e.unmapped, "aucun accès hors de la mémoire émulée")


SETTINGS = [  # (Cutoff, Reso, Env, Decay) par piste
    (0x2000, 0x2000, 0x4000, 0x4000),        # KICK : LP
    (0x6000, 0x4000, 0x4000, 0x4000),        # SNARE : HP résonant
    (0x3f80, 0x0000, 0x4000, 0x4000),        # METAL : LP, pas voisin du centre (moitié filtré)
    (0x5000, 0x3000, 0x2000, 0x3000),        # PERC : HP, enveloppe descendante
    (0x1800, 0x7000, 0x7f00, 0x5000),        # TONE : LP très résonant, enveloppe montante
    (0x4040, 0x6000, 0x4000, 0x4000),        # CHORD : HP, quart de filtre près du centre
]


def sweep_cr(t, b):
    """Balayage façon LFO, différent par piste, qui traverse le centre (LP -> OFF -> HP) : (Cutoff, Reso)."""
    c = int(0x4000 + 0x3e00 * math.sin(2 * math.pi * b / (60 + 13 * t) + t))
    c = 0x4000 if abs(c - 0x4000) < 0x80 and b % 7 == 0 else c
    return min(max(c, 0), 0x7f00), 0x1000 * t + 0x800


def sweep(a, b):
    for t in range(6):
        a.filt(t, *sweep_cr(t, b), a=0x4000 + 0x600 * (t - 3), d=0x3000)


def model_tests(base, img, payload):
    print("filtre en marche : sortie comparée au modèle flottant (entrée : la sortie de l'OS sans le filtre)")
    for name, setup, per_block in (
            ("réglages fixes", lambda a: [a.filt(t, *SETTINGS[t]) for t in range(6)], None),
            ("balayage à chaque bloc", lambda a: None, sweep)):
        x, _, _, _ = run(base, payload, BLOCKS, TRIGS, lambda a: None)
        y, env, a, _ = run(img, payload, BLOCKS, TRIGS, setup, per_block)
        check(a.contract and not a.e.unmapped, f"{name} : contrat de l'appel tenu à chaque bloc, aucun accès hors "
                                               f"mémoire")
        for t in range(6):
            m, z = Model(), []
            for b in range(x.shape[0]):
                c, r = sweep_cr(t, b) if per_block else SETTINGS[t][:2]
                z.append(m.block(x[b, t], c, r, env[t][b][1]))
            z = np.stack(z)
            got = y[:, t].astype(np.float64)
            clip = np.abs(z) >= 2 ** 31 - 1
            ok = ~clip.any(axis=1)
            err = np.abs(z - got)[ok].max() if ok.any() else 0
            peak = np.abs(z).max()
            check(db(err, peak) < -90 and peak > 1e7,
                  f"{name}, {NAMES[t]:5s} : écart max au modèle {db(err, peak):6.1f} dB sous la crête "
                  f"({peak / 2 ** 31:.2f} FS){f', {int((~ok).sum())} blocs saturés exclus' if (~ok).any() else ''}")
        if not per_block:
            dry = [db(np.abs(y[:, t] - x[:, t]).max(), np.abs(x[:, t]).max()) for t in range(6)]
            check(min(dry[:2]) > -15, f"{name} : KICK (LP 332 Hz) et SNARE (HP 332 Hz) nettement changés ; écart à la "
                                      f"piste d'origine par piste : {', '.join(f'{v:.0f}' for v in dry)} dB")


def envelope_tests(img, payload):
    print("enveloppe : relancée à chaque note, décroissance de la loi")
    decays = (0x0000, 0x2000, 0x4000, 0x6000, 0x7f00, 0x5000)

    def setup(a):
        for t in range(6):
            a.filt(t, c=0x2000, r=0, a=(0x7f00, 0x0000, 0x6000, 0x2000, 0x4800, 0x7f00)[t], d=decays[t])
    trigs = {1: 0x3f, 400: 0x01}
    _, env, a, _ = run(img, payload, 420, trigs, setup)
    for t in range(6):
        e = np.array([v[0] for v in env[t]], dtype=np.float64)
        d6 = np.array([v[1] for v in env[t]])
        amt = (0x7f00, 0x0000, 0x6000, 0x2000, 0x4800, 0x7f00)[t] - 0x4000
        tau = G.decay_tau(decays[t]) * G.BLOCK_HZ           # en blocs
        ref = np.zeros(len(e))
        for b in range(1, len(e)):
            ref[b] = 2 ** 31 - 1 if trigs.get(b, 0) >> t & 1 else (
                0 if ref[b - 1] * interp("TABLE_D", decays[t], 9) / 2 ** 31 < 0x10000 else
                ref[b - 1] * interp("TABLE_D", decays[t], 9) / 2 ** 31)
        live = ref > 2 ** 31 * 1e-3
        rel = np.abs(e - ref)[live].max() / 2 ** 31
        n37 = int(np.argmax(e[2:] < (2 ** 31) / math.e)) + 1 if (e[2:] < (2 ** 31) / math.e).any() else None
        exact_d6 = np.abs(d6 - np.floor(amt * e / 2 ** 31)).max()
        retrig = (e[400] == 2 ** 31 - 1) == bool(trigs[400] >> t & 1)
        when = f"1/e en {n37} blocs, loi {tau:.1f}" if n37 else "plus long que l'essai"
        check(rel < 1e-6 and exact_d6 <= 1 and retrig and e[1] == 2 ** 31 - 1 and not e[0]
              and (n37 is None or abs(n37 - tau) <= 1),
              f"{NAMES[t]:5s} Env Decay {decays[t] >> 8:3d} : tau {tau / G.BLOCK_HZ * 1000:7.1f} ms ("
              f"{when}), écart à la loi {rel:.1e} ; "
              f"décalage de fréquence = quantité x "
              f"enveloppe (±{exact_d6:.0f}) ; relance au bloc 400 {'oui' if trigs[400] >> t & 1 else 'non (pas de note)'}")


def ringdown_tests(img, payload):
    """Q 50 sur un signal plein échelle : les états saturent (EMAC en mode saturé) au lieu de se replier, et le filtre
    retombe au silence à la vitesse de sa loi, sans oscillation entretenue (notes/47 §5.2)."""
    print("résonance au maximum (Q 50) sur un signal plein échelle (après Volume + Dist 108), puis silence")
    on, off, w = 120, 400, 50                                   # 80 ms de signal, 267 ms de silence, fenêtres de 33 ms
    rng = np.random.default_rng(1)
    n = np.arange(on * 32)
    for name, c, r in (("LP 947 Hz", 0x2800, 0x7f00), ("HP 2,7 kHz", 0x7000, 0x7f00)):
        idx = c if c < 0x4000 else c - 0x4000
        fc = G.cutoff_hz(idx)
        sig = (np.sign(np.sin(2 * np.pi * 110 * n / G.FS) + 1e-9),           # carré 110 Hz
               np.sin(2 * np.pi * fc * n / G.FS),                             # sinus à la coupure
               rng.uniform(-1, 1, n.size),                                    # bruit blanc
               (n % 480 == 0) * 1.0,                                          # impulsions
               np.sin(2 * np.pi * 20 * (500 ** (n / n.size) - 1) / math.log(500) * n.size / G.FS),  # 20 Hz à 10 kHz
               np.ones(n.size))                                               # échelon
        x = np.zeros((6, (on + off) * 32), dtype=np.int64)
        for t in range(6):
            x[t, :on * 32] = np.round(0.9 * 2 ** 31 * sig[t])
        a = Audio(img, payload)
        voices(a)
        for t in range(6):
            a.setw(t, 19, 0x6c00)
            a.filt(t, c=c, r=r)
        nb = [0]

        def synth(trig=0, release_mask=0):                    # à la place de la boucle des voix
            a.e.uc.mem_write(E.TRACK_BASE, x[:, nb[0] * 32:(nb[0] + 1) * 32].astype(">i4").tobytes())
            nb[0] += 1
        a.e.block = synth
        y = np.stack([a.block(0x3f if b == 0 else 0) for b in range(on + off)])
        pk = np.abs(y[on:]).reshape(off // w, w, 6, 32).max(axis=(1, 3)) / 2 ** 31
        law = 20 * math.log10(math.e) * math.pi * fc / G.q_of(r * G.reso_scale(idx)) * 0.1   # dB par 100 ms
        rates = []
        for t in range(6):
            nz = [k for k in range(len(pk)) if pk[k, t] > 1e-7]
            if len(nz) >= 3:
                rates.append(20 * math.log10(pk[nz[0], t] / pk[nz[-1], t]) / ((nz[-1] - nz[0]) * w / G.BLOCK_HZ) * 0.1)
        mono = all(pk[k + 1, t] <= pk[k, t] * 1.05 for k in range(len(pk) - 1) for t in range(6))
        check(a.contract and not a.e.unmapped, f"{name} : contrat de l'appel tenu à chaque bloc, crête "
                                               f"{np.abs(y).max() / 2 ** 31:.2f} FS (saturée, sans repli)")
        check(mono and not pk[-1].any() and all(abs(v / law - 1) < 0.03 for v in rates),
              f"{name} : après le signal, les 6 pistes décroissent à {min(rates):.1f}..{max(rates):.1f} dB/100 ms "
              f"(loi analogique {law:.1f}, à 3 % près : la transformée bilinéaire amortit un peu moins dans l'aigu) "
              f"jusqu'à zéro exactement")
        if c < 0x4000:
            jumps = int((np.abs(np.diff(y.transpose(1, 0, 2).reshape(6, -1), axis=1)) > 1.5 * 2 ** 31).sum())
            check(jumps == 0, f"{name} : aucun saut de plus de 1,5 FS d'une trame à l'autre (un repli de signe en ferait)")


def law_tests(img, payload):
    print("fréquence et Q réalisés (tirés des coefficients calculés par le code) contre la loi")
    pts = [(c, r) for c in list(range(0x0000, 0x4000, 0x0400)) + [0x3f00] + list(range(0x4100, 0x7f01, 0x0400))
           + [0x7f00] for r in (0, 0x2000, 0x4000, 0x6000, 0x7f00)]
    a = Audio(img, payload)
    voices(a)
    worst_c, worst_q, rows = 0, 0, []
    for i in range(0, len(pts), 6):
        grp = pts[i:i + 6]
        for t, (c, r) in enumerate(grp):
            a.filt(t, c=c, r=r)
        a.block(0)
        for t, (c, r) in enumerate(grp):
            _, _, b1, b2, c2, a3, gx2, hl, hb = a.kst(t)
            a1 = (b1 / 2 ** 31 + 1) / 2
            g = (b2 / 2 ** 31 / 2) / a1
            k = (1 / a1 - 1 - g * g) / g
            fc, q = math.atan(g) * G.FS / math.pi, 1 / k
            idx = c if c < 0x4000 else c - 0x4000
            fl = G.cutoff_hz(idx)
            ql = G.q_of(r * G.reso_scale(idx))
            cents = 1200 * math.log2(fc / fl)
            qerr = q / ql - 1
            worst_c, worst_q = max(worst_c, abs(cents)), max(worst_q, abs(qerr))
            rows.append((c, r, fc, fl, q, ql))
    check(worst_c < 5 and worst_q < 0.01,
          f"{len(pts)} réglages, 5 Hz à 20 kHz des deux côtés, Q {G.Q_MIN:g} à {G.Q_MAX:g} : fréquence à {worst_c:.2f} cent près, "
          f"Q à {worst_q * 100:.2f} % près")
    for c, r, fc, fl, q, ql in rows:
        if (c, r) in ((0x0000, 0), (0x2000, 0x4000), (0x3f00, 0x7f00), (0x4100, 0x7f00), (0x6000, 0x2000),
                      (0x7f00, 0x7f00)):
            print(f"        {'L' if c < 0x4000 else 'H'}{abs(c - 0x4000) >> 8:<3d} Reso {r >> 8:3d} : "
                  f"{fc:8.1f} Hz (loi {fl:8.1f}), Q {q:6.2f} (loi {ql:6.2f})")


def cost_tests(img, payload):
    print("coût : instructions exécutées dans le code du filtre, par bloc (6 pistes)")
    cases = (
        ("6 pistes au centre", lambda a: [a.filt(t) for t in range(6)], None, {1: 0x3f}),
        ("1 piste LP, 5 au centre", lambda a: [a.filt(t, c=0x2000 if t == 0 else 0x4000, r=0x3000)
                                              for t in range(6)], None, {1: 0x3f}),
        ("6 pistes filtrées, réglages fixes", lambda a: [a.filt(t, *SETTINGS[t][:2]) for t in range(6)], None,
         {1: 0x3f}),
        ("6 pistes filtrées, enveloppe en cours", lambda a: [a.filt(t, c=0x2000, r=0x3000, a=0x7000, d=0x7f00)
                                                            for t in range(6)], None, {1: 0x3f}),
        ("6 pistes filtrées, réglages changés à chaque bloc", lambda a: None, sweep, {1: 0x3f}),
    )
    out = {}
    for name, setup, pb, trigs in cases:
        _, _, _, cost = run(img, payload, 80, trigs, setup, pb, count=True)
        c = np.array(cost[3:])
        out[name] = (c.mean(), c.max())
        print(f"        {name:50s} moyenne {c.mean():6.0f}  max {c.max():5d}  "
              f"= {c.max() * 1.54 / 166667 * 100:.2f} % d'un bloc (1,54 cycle par instruction, 250 MHz)")
    y, _, _, cost = run(img, payload, 400, {1: 0x3f}, lambda a: [a.filt(t, *SETTINGS[t][:2]) for t in range(6)],
                        count=True, decay=10)
    out["après les notes"] = np.mean(cost[360:])
    print(f"        {'6 pistes filtrées, notes finies (Decay 10, blocs 360..400)':50s} moyenne {np.mean(cost[360:]):6.0f}"
          f"  (blocs nuls : {sum(not y[b].any() for b in range(360, 400))} sur 40)")
    check(out["6 pistes filtrées, réglages changés à chaque bloc"][1] * 1.54 / 166667 < 0.05,
          "au pire, moins de 5 % d'un bloc audio")
    return out


# ---- 2. interface, sauvegarde ------------------------------------------------------------------------------------
STOP, STACK, SCRATCH = 0x90000100, 0x90010000, 0x91000000


class UI:
    """Le code de l'interface de l'OS, exécuté fonction par fonction (image + BSS + charge utile)."""

    def __init__(self, img, payload=None):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
        uc.mem_map(0x40000000, 0x02400000)
        uc.mem_write(BASE, img[:E.IMAGE_LEN])
        if payload:
            dst, data = payload
            uc.mem_map(dst, (len(data) + 0xfffff) & ~0xfffff)
            uc.mem_write(dst, data)
        uc.mem_map(0x90000000, 0x04000000)
        uc.mem_write(STOP, b"\x4e\x71\x4e\x71")
        self.bad, self.hooks, self.calls, self.heap = [], {}, [], 0x93000000
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: self.bad.append(addr) or False)
        uc.hook_add(UC_HOOK_CODE, self._hook)

    def _hook(self, uc, addr, size, ud):
        if addr in self.hooks:
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            args = struct.unpack(">4I", uc.mem_read(sp + 4, 16))
            name, ret = self.hooks[addr]
            if name == "new":                         # operator new : un tas factice
                ret, self.heap = self.heap, (self.heap + args[0] + 15) & ~15
            self.calls.append((name, args))
            uc.reg_write(mk.UC_M68K_REG_D0, ret)
            uc.reg_write(mk.UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)

    def u32(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def call(self, fn, *args, count=20_000_000):
        self.uc.reg_write(mk.UC_M68K_REG_A0, SCRATCH)
        sp = STACK - 0x400
        self.uc.mem_write(sp, struct.pack(">I" + "I" * len(args), STOP, *[a & 0xffffffff for a in args]))
        self.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        self.bad.clear()
        self.uc.emu_start(fn, STOP, count=count)
        self.sp_ok = self.uc.reg_read(mk.UC_M68K_REG_A7) == sp + 4
        return self.uc.reg_read(mk.UC_M68K_REG_D0)

    def cstr(self, a):
        return bytes(self.uc.mem_read(a, 64)).split(b"\0")[0].decode("latin-1")


KNOB_LOOKUP, KEY_TABLE, KEY_BITS = 0x4001e814, 0x4010ae5c, 0x40f95744
REC = 0x40a71754


def machines_key(u, held):
    bit = struct.unpack(">i", u.uc.mem_read(KEY_TABLE + 4 * 5, 4))[0]
    v = u.uc.mem_read(KEY_BITS + (bit >> 3), 1)[0]
    v = v | 1 << (bit & 7) if held else v & ~(1 << (bit & 7))
    u.uc.mem_write(KEY_BITS + (bit >> 3), bytes([v]))


def knob_tests(img, syms):
    print("potards : MACHINES tenu + COLOR / SHAPE / SWEEP / CONTOUR")
    u = UI(img)
    u.hooks[KNOB_LOOKUP] = ("lookup", 0x55)
    slot = u.u32(0x401005a8)
    check(slot == syms["tf_knob"], f"slot 124 de la vtable de ParameterPageView (0x401005a8) -> tf_knob "
                                   f"({slot:#x})")
    got, fwd = {}, True
    for held in (False, True):
        machines_key(u, held)
        for knob in range(12):
            u.calls.clear()
            d = u.call(slot, 0x90200000, knob, 1, 0xffffffff)
            fwd &= u.calls == [("lookup", (0x90200000, knob, 1, 0xffffffff))] and u.sp_ok and not u.bad
            got[held, knob] = d
    want = {(h, k): ({4: 3, 5: 4, 6: 1, 7: 2}[k] if h and 4 <= k <= 7 else 0x55) for h in (False, True)
            for k in range(12)}
    check(got == want, "MACHINES tenu : COLOR -> 3 Filter Env, SHAPE -> 4 Env Decay, SWEEP -> 1 Filter Cutoff, "
                       "CONTOUR -> 2 Filter Reso ; les 8 autres potards, et tous sans MACHINES : la recherche "
                       "d'origine")
    check(fwd, "la recherche d'origine est appelée une fois, avec les mêmes arguments, à chaque fois ; pile rendue")


def display_tests(img, syms):
    print("affichage des valeurs (objets d'interface du vrai constructeur, vrai sprintf)")
    u = UI(img)
    u.hooks[0x400802e0] = ("new", 0)
    u.hooks[0x400cf044] = ("atexit", 0)
    u.call(0x400de244, count=50_000_000)
    ok = not u.bad
    u.hooks[KNOB_LOOKUP] = ("lookup", 0)
    u.call(syms["tf_knob"], 0x90200000, 0, 0, 0xffffffff)
    want = {1: (syms["tf_fmt_cut"], 0x400456c8, 0x40045bd6, 0x400456c8)}
    recs = [(u.u32(REC + 100 * i + 0x1c), u.u32(REC + 100 * i + 0x20), u.u32(REC + 100 * i + 0x2c))
            for i in range(1, 5)]
    check(ok and [r[1] for r in recs] == list(want[1]) and all(r[0] and not r[2] for r in recs),
          "objets 1 à 4 : nos formateurs installés, pas de dessin spécial (l'image « Error » n'est plus dessinée)")
    vals = {1: (0x0000, 0x2000, 0x3f00, 0x3fff, 0x4000, 0x4100, 0x6000, 0x7f00), 2: (0, 0x4000, 0x7f00),
            3: (0x0000, 0x3f00, 0x4000, 0x4100, 0x7f00), 4: (0, 0x4000, 0x7f00)}
    shown = {}
    for i, vs in vals.items():
        inv = u.u32(REC + 100 * i + 0x20)
        for v in vs:
            u.uc.mem_write(SCRATCH + 0x100, bytes(32))
            u.call(inv, REC + 100 * i + 0x14, v, SCRATCH + 0x100)
            shown[i, v] = u.cstr(SCRATCH + 0x100)
    print("        " + " | ".join(f"{['', 'FREQ', 'RESO', 'FENV', 'FDEC'][i]} " +
                                  " ".join(shown[i, v] for v in vs) for i, vs in vals.items()))
    check([shown[1, v] for v in vals[1]] == ["L64", "L32", "L1", "L0", "OFF", "H1", "H32", "H63"],
          "Filter Cutoff : L64 .. L1, OFF au centre, H1 .. H63")
    check(all(len(shown[i, v]) <= 3 for i, vs in vals.items() for v in vs),
          "trois caractères au plus, comme Pan (L64, CEN, R63) : l'écran n'en montre pas plus")
    # chaque pas du potard (0..127) : son étiquette, différente de ses voisines (« LP64 » se lisait « LP6 » sur la machine)
    inv, steps = u.u32(REC + 100 + 0x20), []
    for n in range(128):
        u.uc.mem_write(SCRATCH + 0x100, bytes(32))
        u.call(inv, REC + 100 + 0x14, n << 8, SCRATCH + 0x100)
        steps.append(u.cstr(SCRATCH + 0x100))
    check(steps == [f"L{64 - n}" for n in range(64)] + ["OFF"] + [f"H{n - 64}" for n in range(65, 128)],
          "les 128 pas de Filter Cutoff : L64 .. L1, OFF, H1 .. H63, tous différents, 3 caractères au plus")
    check([shown[2, v] for v in vals[2]] == ["0", "64", "127"] and [shown[4, v] for v in vals[4]] == ["0", "64", "127"],
          "Filter Reso et Env Decay : 0 .. 127")
    check(shown[3, 0x4000] in ("OFF", "0") and shown[3, 0] == "-64" and shown[3, 0x7f00] == "+63",
          f"Filter Env : -64 .. {shown[3, 0x4000]} .. +63")


def desc_rows(u, base):
    return [struct.unpack(">14I", u.uc.mem_read(base + 0x38 * i, 0x38)) for i in range(1, 5)]


def maps(u, nm):
    pid = {(k, m): u.call(0x4005a692, k, m) for k in range(33) for m in range(nm)}
    cc = {(t, cc): u.call(0x4005a8ce, t, 0, cc) for t in range(7) for cc in range(128)}
    nr = {n: u.call(0x4005a92e, 0, 0, n) for n in range(0x180)}
    return pid, cc, nr


def table_tests(base, img, syms, payload, nm):
    print("tables des paramètres construites au démarrage (0x4004486c -> tf_boot -> 0x4005a274)")
    a, b = UI(base, payload), UI(img, payload)
    site = bytes(b.uc.mem_read(0x4004486c, 6))
    check(site == b"\x4e\xb9" + struct.pack(">I", syms["tf_boot"]), f"0x4004486c : jsr tf_boot ({site.hex()})")
    dop_b = b.u32(0x4005a2de)
    a.call(0x4005a274)
    b.call(syms["tf_boot"])
    check(not a.bad and not b.bad and b.sp_ok, "construites sans accès hors mémoire, pile rendue")
    rows = desc_rows(b, dop_b)
    names = [(b.cstr(r[11]), b.cstr(r[13])) for r in rows]
    check([r[:11] for r in rows] == [(7, k, 0, 32512, d, 0, cc, nr, 0, 0x600, key)
                                     for k, d, cc, nr, key, _, _ in G.DESCRIPTORS] and
          names == [("Filter Cutoff", "FREQ"), ("Filter Reso", "RESO"), ("Filter Env", "FENV"), ("Env Decay", "FDEC")],
          f"descripteurs 1 à 4 de la table active ({dop_b:#x}{', déplacée par les moteurs du Syntakt' if dop_b != G.DESC else ''}) : "
          f"{', '.join(n for n, _ in names)}, groupe 7 (toutes les machines), 0..127, LFO et vélocité")
    pa, ca, na = maps(a, nm)
    pb, cb, nb = maps(b, nm)
    ours = {(k, m): k - 27 for k in range(28, 32) for m in range(nm)}
    check(all(pb[km] == v for km, v in ours.items()) and all(pa[km] == 0 for km in ours),
          f"k 28..31 -> descripteurs 1..4 sur les {nm} machines (sans le filtre : aucun)")
    check({km: v for km, v in pb.items() if km not in ours} == {km: v for km, v in pa.items() if km not in ours},
          "tous les autres k de toutes les machines : comme sans le filtre")
    diff_cc = {k: (ca[k], cb[k]) for k in ca if ca[k] != cb[k]}
    check(diff_cc == {(t, 74): (0, 1) for t in range(6)} | {(t, 71): (0, 2) for t in range(6)},
          f"CC : 74 -> Filter Cutoff et 71 -> Filter Reso sur les pistes 1 à 6 (libres avant), rien d'autre de changé "
          f"({len(diff_cc)} écarts)")
    diff_nr = {k: (na[k], nb[k]) for k in na if na[k] != nb[k]}
    check(diff_nr == {0x94: (0, 1), 0x95: (0, 2)}, f"NRPN 1:20 -> Filter Cutoff, 1:21 -> Filter Reso, rien d'autre "
                                                   f"({diff_nr})")
    # un son initialisé (nouveau projet, son effacé, changement de machine : 0x400618f2 -> 0x40061866) prend les
    # défauts des descripteurs : Filter Cutoff au centre, pas à zéro (qui serait un passe-bas fermé à 5 Hz)
    same, ours = True, set()
    for m in range(nm):
        for u in (a, b):
            u.uc.mem_write(SOUND, b"\xcc" * 100)
            u.call(0x400618f2, SOUND, m)
        sa, sb = bytes(a.uc.mem_read(SOUND, 100)), bytes(b.uc.mem_read(SOUND, 100))
        same &= sa[:76] == sb[:76] and sa[84:] == sb[84:]
        ours.add((kw(sb, 28), kw(sb, 29), kw(sb, 30), kw(sb, 31)))
    check(same and ours == {(0x4000, 0, 0x4000, 0x4000)},
          f"son initialisé, {nm} machines : Filter Cutoff OFF, Reso 0, Env OFF, Decay 64 ; tout le reste comme sans le "
          f"filtre")


SOUND, RECORD = 0x91100000, 0x91200000


def sound_bytes(rng, k28=0x1234, k29=0x5600, k30=0x2a00, k31=0x7100, lfo=29, vel=30):
    s = bytearray(rng.integers(0, 256, 100, dtype=np.uint8).tobytes())
    for k in range(33):
        struct.pack_into(">H", s, 20 + 2 * k, int(rng.integers(0, 0x7f01)))
    for k, v in zip((28, 29, 30, 31), (k28, k29, k30, k31)):
        struct.pack_into(">H", s, 20 + 2 * k, v)
    struct.pack_into(">H", s, 28, lfo << 8)
    struct.pack_into(">I", s, 88, vel)
    struct.pack_into(">H", s, 92, 0x3000)
    struct.pack_into(">I", s, 96, 0x40)
    return bytes(s)


def save_load(u, sound, fn=0x4005afa0):
    u.uc.mem_write(SOUND, sound)
    u.uc.mem_write(RECORD, b"\xee" * 100)
    r1 = u.call(fn, RECORD, SOUND)
    rec = bytes(u.uc.mem_read(RECORD, 100))
    u.uc.mem_write(SOUND, b"\xcc" * 100)
    r2 = u.call(0x4005aecc, SOUND, RECORD)
    return r1, rec, r2, bytes(u.uc.mem_read(SOUND, 100))


def kw(s, k):
    return struct.unpack_from(">H", s, 20 + 2 * k)[0]


def save_tests(base, img):
    print("son sauvegardé puis rechargé (kit, réserve de sons, copier-coller)")
    rng = np.random.default_rng(47)
    a, b = UI(base), UI(img)
    for fn, ver in ((0x4005afa0, 2), (0x4005b054, 1)):
        snd = sound_bytes(rng)
        ra, reca, _, _ = save_load(a, snd, fn)
        rb, recb, lb, back = save_load(b, snd, fn)
        diff = [i for i in range(100) if reca[i] != recb[i]]
        check(ra == rb and set(diff) <= {64, 65, 82, 83, 88, 89, 90, 91} and b.sp_ok and not b.bad,
              f"sauvegarde version {ver} : même enregistrement que sans le filtre, plus nos emplacements 18, 27, 30, "
              f"31 (octets {diff})")
        if ver == 1:
            continue
        check((kw(back, 28), kw(back, 29), kw(back, 30), kw(back, 31)) == (0x1234, 0x5600, 0x2a00, 0x7100) and lb == 1,
              "rechargé : Filter Cutoff (valeur fine 0x1234 d'un NRPN), Reso, Env et Decay reviennent")
        check(struct.unpack_from(">H", back, 28)[0] == 29 << 8 and struct.unpack_from(">I", back, 88)[0] == 30,
              "rechargé : LFO -> Filter Reso et vélocité -> Filter Env reviennent")
        _, _, _, back_a = save_load(a, snd, fn)
        same = [k for k in range(28) if k not in (0, 4) and kw(back, k) == kw(back_a, k)]
        check(len(same) == 26 and back[92:100] == back_a[92:100] and kw(back, 0) == 0,
              "rechargé : tous les autres paramètres comme sans le filtre (k 0, inutilisé, à zéro)")
        snd2 = sound_bytes(rng, lfo=13, vel=17)
        _, _, _, back_a = save_load(a, snd2)
        _, _, _, back_b = save_load(b, snd2)
        check(back_a[28:30] == back_b[28:30] and back_a[88:92] == back_b[88:92],
              "destinations du LFO (Sweep) et de la vélocité (k 17) d'origine : comme sans le filtre")
    # un son sauvegardé sans le filtre (ses emplacements 18, 24..31 à zéro) se charge filtre OFF
    snd = sound_bytes(rng)
    _, reca, _, _ = save_load(a, snd)
    b.uc.mem_write(RECORD, reca)
    b.call(0x4005aecc, SOUND, RECORD)
    old = bytes(b.uc.mem_read(SOUND, 100))
    check((kw(old, 28), kw(old, 29), kw(old, 30), kw(old, 31)) == (0x4000, 0, 0x4000, 0x4000),
          "un son d'avant le filtre se charge Filter Cutoff OFF, Reso 0, Env 0 (OFF), Decay 64")


RAM, FILE = 0x91300000, 0x91400000


def plock_tests(base, img):
    print("p-locks du pattern sauvegardés puis rechargés")

    def ram_init(u):
        u.uc.mem_write(RAM, (b"\xff\xff" * (34 * 64) + b"\x00" * 33) * 6)

    def lock(u, t, step, k, v):
        u.uc.mem_write(RAM + t * 4385 + step * 68 + 2 * k, struct.pack(">h", v))
        u.uc.mem_write(RAM + t * 4385 + 4352 + k, b"\x01")

    def dump(u):
        out = {}
        for t in range(6):
            blk = bytes(u.uc.mem_read(RAM + t * 4385, 4385))
            for k in range(33):
                if blk[4352 + k]:
                    out[t, k] = {s: struct.unpack_from(">h", blk, s * 68 + 2 * k)[0] for s in range(64)
                                 if struct.unpack_from(">h", blk, s * 68 + 2 * k)[0] != -1}
        return out

    def recs(u):
        return bytes(u.uc.mem_read(FILE, 80 * 130))

    locks = [(2, 5, 28, 0x1234), (2, 7, 29, 0x2000), (2, 9, 23, 0x0800), (2, 1, 1, 0x3000), (3, 4, 31, 0x0400),
             (3, 6, 30, 0x0500), (1, 3, 13, 0x4400), (0, 0, 24, 0x7f00), (5, 63, 27, 0x0100)]
    res = {}
    for name, img_ in (("sans", base), ("avec", img)):
        u = UI(img_)
        ram_init(u)
        for l in locks:
            lock(u, *l)
        before = dump(u)
        u.uc.mem_write(FILE, b"\x00" * 10400)
        u.call(0x4005b95c, FILE, RAM, 0)
        full = recs(u)
        ram_init(u)
        u.call(0x4005b766, RAM, FILE)
        res[name] = (before, dump(u), full)
        # mise à jour d'un seul p-lock, sur un fichier qui en a déjà un de LFO Speed (piste 3)
        ram_init(u)
        lock(u, 2, 1, 1, 0x3000)
        u.uc.mem_write(FILE, b"\x00" * 10400)
        u.call(0x4005b95c, FILE, RAM, 0)
        lock(u, 2, 5, 28, 0x1234)
        u.call(0x4005ba90, FILE, RAM, 0, 28, 2)
        ram_init(u)
        u.call(0x4005b766, RAM, FILE)
        res[name] += (dump(u), not u.bad)
    before, after, _, inc, nobad = res["avec"]
    check(after == before and nobad, "toutes les pistes de p-locks reviennent sur leur paramètre (k 1, 13, 23, 24, 27, "
                                     "28..31)")
    sb, sa, _, _, _ = res["sans"]
    lost = sorted(k for k in sb if sa.get(k) != sb[k])
    check(bool(lost), f"(sans le filtre, ces p-locks se perdaient ou tombaient sur d'autres paramètres : "
                      f"pistes {lost})")
    check(inc == {(2, 1): {1: 0x3000}, (2, 28): {5: 0x1234}},
          "mise à jour d'un seul p-lock (0x4005ba90, k 28) : il revient sur Filter Cutoff, LFO Speed reste seul")
    # sans p-lock k >= 23, fichiers identiques
    files = []
    for img_ in (base, img):
        u = UI(img_)
        ram_init(u)
        for t, s, k, v in locks:
            if k < 23:
                lock(u, t, s, k, v)
        u.uc.mem_write(FILE, b"\x00" * 10400)
        u.call(0x4005b95c, FILE, RAM, 0)
        files.append(recs(u))
    check(files[0] == files[1], "p-locks des paramètres d'origine : fichier identique octet pour octet")


# ---- programme ----------------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True)
    ap.add_argument("--with", dest="others", default="",
                    help="autres tweaks appliqués aussi (ex. 6ch-usbup,syntakt-sd-cp-toy-bits-swarm,arp,trig-hold)")
    ap.add_argument("--syntakt", help="Syntakt_OS1.42.syx (ou 1.41), pour les moteurs du Syntakt")
    ap.add_argument("--quick", action="store_true", help="sans la mesure du coût (lente)")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    dev = TWEAK.parent
    by_id = {json.loads(f.read_text(encoding="utf-8"))["id"]: f for f in dev.glob("*.json") if f.name != "device.json"}
    others = [json.loads(by_id[i].read_text(encoding="utf-8")) for i in args.others.split(",") if i]
    tw = json.loads(TWEAK.read_text(encoding="utf-8"))
    syms = {k: int(v, 16) for k, v in tw["symbols"].items()}
    p0, _ = build.apply_writes(stock, others)
    pl0, _ = build.build_payload(others, stock, args.syntakt)
    p1, _ = build.apply_writes(stock, others + [tw])
    pl1, _ = build.build_payload(others + [tw], stock, args.syntakt)
    base, img = bytes(p0) + pl0, bytes(p1) + pl1
    # charge utile ajoutée après l'OS (moteurs du Syntakt, MACRO, ou les deux), telle qu'en mémoire après le démarrage
    app_ = [t for t in others if t.get("append") and not t["id"].startswith("model-tg")]
    payload, nm = None, 6
    if app_:
        t = app_[0]
        st_img = None
        if t["append"].get("syntakt"):
            import syntakt
            st_img = syntakt.dsp_image(args.syntakt)
        dest = int(t["append"]["dest"], 16)
        rt = bytearray(build.payload_runtime(t, stock, st_img))
        if t["append"].get("compress"):         # MACRO avec les moteurs : les tables de CHORD, copiées au démarrage
            import test_macro_syntakt as tms    # (notes/50)
            ctx = dict(st_img=st_img, chord=tms.chord_tables(stock))
            at = tms.chord_at(t, ctx)
            rt[at - dest:at - dest + len(ctx["chord"])] = ctx["chord"]
        payload = (dest, bytes(rt))
        nm = 6 + len(t["id"].split("-")) - 1 if st_img else 7       # syntakt-sd-…[-macro] ; macro : 7 machines
    print(f"firmware : {', '.join(t['id'] for t in others + [tw])}")
    centre_tests(base, img, payload)
    model_tests(base, img, payload)
    envelope_tests(img, payload)
    law_tests(img, payload)
    ringdown_tests(img, payload)
    if not args.quick:
        cost_tests(img, payload)
    knob_tests(img, syms)
    display_tests(img, syms)
    table_tests(base, img, syms, payload, nm)
    save_tests(base, img)
    plock_tests(base, img)
    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ÉCHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
