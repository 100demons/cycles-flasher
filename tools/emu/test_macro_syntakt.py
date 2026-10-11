#!/usr/bin/env python3
"""Preuve de MACRO avec les moteurs du Syntakt (notes/50) : 24-syntakt-<moteurs>-macro.json, et avec Model-TG
31-syntakt-tg-<moteurs>-macro.json par-dessus 30-model-tg-st.json (tools/gen_macro_syntakt.py). Le vrai code de l'OS,
émulé (Unicorn).

Références : les moteurs seuls (24-syntakt-….json, 31-syntakt-tg-….json : même passerelle, mêmes adresses) et MACRO
seule (25-macro.json, 32-macro-tg.json).

  1. Démarrage : le décompresseur du bootstrap relit l'OS agrandi ; le crochet (stub.S, APLIB) décompresse la
     charge utile de l'image, reprend les tables d'ondes de CHORD en SRAM à leur place dans la charge utile, remplit
     les deux zones de SRAM avec le code et les voix du Syntakt, puis reprend (seul : la remise à zéro du BSS ; avec
     Model-TG : boot_extra_hook), pile et registres intacts. La charge utile en mémoire est celle des moteurs seuls
     octet pour octet (sauf les tables, détours, données et descripteurs, qui comptent MACRO), plus MACRO.
  2. Interface : les vérifications de test_syntakt_machines.py (seul) et de test_model_tg_syntakt.py (avec
     Model-TG), pour les moteurs et MACRO après eux.
  3. Son :
     - avant la chaîne d'ampli, MACRO est exactement Braids compilé pour l'ordinateur (test_macro.py) : quelques
       modèles et variantes ;
     - les 6 machines d'origine (CHORD et ses tables d'ondes compris) et chaque moteur du Syntakt : identiques,
       échantillon par échantillon, aux moteurs seuls ;
     - MACRO : identique à MACRO seule jusqu'à l'arrêt de la voix muette par le régulateur (la référence reste
       sous le seuil), puis après le trig suivant ;
     - tout ensemble sur les 6 pistes (avec Model-TG, le Sampler) ; machine locks ;
  4. Régulateur de charge : en surcharge, il éteint aussi des pistes MACRO (jamais le Sampler) ; les autres restent
     identiques à la référence.
  5. Avec d'autres mods (--with) : démarrage, et les mêmes comparaisons.

    python3 tools/emu/test_macro_syntakt.py --cycles model-cycles_OS1.13.syx --syntakt Syntakt_OS1.42.syx \\
        --eurorack vendor/eurorack [--engines sd,cp,toy,bits,swarm] [--with 6ch-usbup,arp,trig-hold,…]
"""
import argparse
import json
import pathlib
import struct
import sys
import tempfile

import numpy as np
from unicorn import (Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_BLOCK, UC_HOOK_CODE, UC_HOOK_MEM_READ,
                     UC_HOOK_MEM_UNMAPPED, UC_HOOK_MEM_WRITE)
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import gen_macro as gm              # noqa: E402
import gen_macro_syntakt as gms     # noqa: E402
import gen_syntakt_engines as gs    # noqa: E402
import mcengine as E                # noqa: E402
import syntakt                      # noqa: E402
import test_macro as tm             # noqa: E402
import test_model_tg as TM          # noqa: E402
import test_model_tg_syntakt as tms  # noqa: E402
import test_sdvintage as T          # noqa: E402
import test_sdvintage_7th as t7     # noqa: E402
import test_syntakt_machines as tsm  # noqa: E402

BASE = E.BASE
check = t7.check
BASE_KW = tm.BASE_KW
load = tm.load


class Fw(tm.Fw):
    """Un firmware : MAIN OS (avec ce qui est ajouté après) et la charge utile telle qu'en mémoire après le crochet de
    démarrage (pour une charge utile compressée : tables d'ondes de CHORD reprises en SRAM)."""

    def __init__(self, stock, tweaks, ctx):
        p, _ = build.apply_writes(stock, tweaks)
        pl, _ = build.build_payload(tweaks, stock, ctx["syntakt"])
        self.img, self.tweaks, self.packed = bytes(p) + pl, tweaks, len(pl)
        tg = [t for t in tweaks if t["id"].startswith("model-tg")]
        self.blob_end = BASE + len(stock) + tg[0]["append"]["size"] if tg else None
        if tg:
            self.packed -= tg[0]["append"]["size"]
        ours = [t for t in tweaks if t.get("append") and not t["id"].startswith("model-tg")]
        self.payload = None
        if not ours:
            return
        t = ours[0]
        ap_ = t["append"]
        dest = int(ap_["dest"], 16)
        rt = bytearray(build.payload_runtime(t, stock, ctx["st_img"]))
        if ap_.get("compress"):
            self.chord_at = chord_at(t, ctx)
            rt[self.chord_at - dest:self.chord_at - dest + len(ctx["chord"])] = ctx["chord"]
        self.runtime = bytes(rt)
        self.payload = (dest, self.runtime)
        self.dest = dest
        if "symbols" not in t:                  # moteurs seuls
            return
        code = next(p_ for p_ in ap_["parts"] if "hex" in p_ and int(p_["dest"], 16) == dest + (gms.MACRO_AT if
                                                                                             ap_.get("compress") else 0))
        self.pay = int(code["dest"], 16)
        self.code_end = self.pay + len(code["hex"]) // 2
        first = gs.TG_FIRST if tg else 6
        self.nm = first + len(engines_of(t)) + 1
        self.index = self.nm - 1
        data = dest + gs.LAYOUT["DATA"]
        u32 = lambda va: struct.unpack_from(">I", self.runtime, va - dest)[0]
        self.upd = u32(data + 4 * self.nm + 4 * self.index)
        self.rnd = u32(data + 8 * self.nm + 4 * self.index)
        self.braids_render = int(t["symbols"]["braids_render"], 16)


def engines_of(t):
    """Moteurs du Syntakt d'un tweak (syntakt-[tg-]<moteurs>[-macro])."""
    return [c for c in t["id"].split("-") if c in gs.CATALOG and c != "macro"]   # "macro" : ajouté au catalogue pour l'interface


def chord_at(t, ctx):
    gs.set_base(int(t["append"]["dest"], 16))
    return gs.analyse(ctx["st_img"], gs.generation(engines_of(t)))["lay"]["chord_at"]


def chord_tables(stock):
    """Tables d'ondes de CHORD, telles que l'OS les met en SRAM au démarrage (0x4000045c) : les deux zones."""
    out = b""
    for lo, hi in gs.CHORD_BANKS:
        src = next(s_ + lo - d_ for s_, e_, d_ in gs.CY_SRAM_INIT if d_ <= lo and hi <= d_ + e_ - s_)
        out += stock[src - BASE:src - BASE + hi - lo]
    return out


# --- 1. démarrage ----------------------------------------------------------------------------------------------
def icache_watch(uc, fw, dst):
    """Le cache d'instructions, qu'Unicorn n'a pas (notes/50 §8) : le bootstrap le laisse actif, sans cohérence avec
    les écritures. Toute ligne de 16 o écrite dans la charge utile est « périmée » jusqu'au prochain movec …,cacr
    avec ICINVA (0x100) ; exécuter une ligne périmée est une faute (sur la machine : l'ancien contenu de la SDRAM).
    Rend ([adresses fautives], [movec avec ICINVA vus])."""
    dirty, faults, inval = set(), [], []

    def wr(u, access, addr, size, value, d):
        if dst <= addr < dst + 0x00100000:
            dirty.update(range(addr >> 4, ((addr + size - 1) >> 4) + 1))

    def blk(u, addr, size, d):
        if dirty and dst <= addr < dst + 0x00100000 and \
                any(k in dirty for k in range(addr >> 4, ((addr + size - 1) >> 4) + 1)):
            faults.append(addr)

    def movec(u, addr, size, d):
        r = struct.unpack(">H", u.mem_read(addr + 2, 2))[0] >> 12
        if u.reg_read((mk.UC_M68K_REG_D0 + r) if r < 8 else (mk.UC_M68K_REG_A0 + r - 8)) & 0x100:
            dirty.clear()
            inval.append(addr)

    uc.hook_add(UC_HOOK_MEM_WRITE, wr, begin=dst, end=dst + 0x00100000 - 1)
    uc.hook_add(UC_HOOK_BLOCK, blk, begin=dst, end=dst + 0x00100000 - 1)
    lo, hi = gs.gx.CAVE, gs.STUB_END
    for a in range(lo, hi, 2):
        k = a - BASE
        if fw.img[k:k + 2] == b"\x4e\x7b" and struct.unpack(">H", fw.img[k + 2:k + 4])[0] & 0xfff == 0x002:
            uc.hook_add(UC_HOOK_CODE, movec, begin=a, end=a)
    return faults, inval


def boot(fw, ref, tg=None):
    """Le crochet de démarrage, exécuté pour de vrai (comme test_macro.boot)."""
    uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
    uc.mem_map(0x40000000, 0x02400000)
    uc.mem_write(BASE, fw.img)
    dst, rt = fw.payload
    uc.mem_map(dst, 0x00100000)
    uc.mem_write(dst, b"\xa5" * 0x00100000)              # ce que la SDRAM contient avant : n'importe quoi
    uc.mem_map(0x80000000, 0x00010000)
    sram = bytearray(0x10000)                             # SRAM après son initialisation par l'OS (0x4000045c)
    for lo, hi, d in gs.CY_SRAM_INIT:
        sram[d - 0x80000000:d - 0x80000000 + hi - lo] = fw.img[lo - BASE:hi - BASE]
    uc.mem_write(0x80000000, bytes(sram))
    uc.mem_map(0x90000000, 0x00020000)
    uc.mem_write(E.STOP, b"\x4e\x71\x4e\x71")
    bad, n = [], [0]
    uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: bad.append(addr) or False)
    keep = {r: 0x11110000 + i for i, r in enumerate((mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4,
                                                     mk.UC_M68K_REG_D5, mk.UC_M68K_REG_D6, mk.UC_M68K_REG_D7,
                                                     mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3, mk.UC_M68K_REG_A4,
                                                     mk.UC_M68K_REG_A5, mk.UC_M68K_REG_A6))}
    for r, v in keep.items():
        uc.reg_write(r, v)
    stale = icache_watch(uc, fw, dst)
    uc.reg_write(mk.UC_M68K_REG_SR, 0x2700)              # superviseur, comme au démarrage (movec)
    sp0 = 0x90010000
    if tg:
        uc.reg_write(mk.UC_M68K_REG_A7, sp0)
        uc.emu_start(gs.BOOT_CALL, tg["boot_extra_hook"], count=50_000_000)
        pc, sp = uc.reg_read(mk.UC_M68K_REG_PC), uc.reg_read(mk.UC_M68K_REG_A7)
        ret = struct.unpack(">I", uc.mem_read(sp, 4))[0]
        regs = all(uc.reg_read(r) == v for r, v in keep.items())
        check(pc == tg["boot_extra_hook"] and sp == sp0 - 4 and ret == gs.BOOT_CALL + 6 and regs and not bad,
              f"jsr 0x40000530 -> notre crochet -> boot_extra_hook {tg['boot_extra_hook']:#x}, pile et d2..d7/a2..a6 "
              "intactes")
    else:
        uc.mem_write(sp0, struct.pack(">I", E.STOP))
        uc.reg_write(mk.UC_M68K_REG_A7, sp0)
        uc.emu_start(0x400004b2, E.STOP, count=200_000_000)
        regs = all(uc.reg_read(r) == v for r, v in keep.items())
        tail = BASE + E.IMAGE_LEN
        cleared = not any(uc.mem_read(tail, len(fw.img) - E.IMAGE_LEN)) and not any(uc.mem_read(0x42338000, 0xb0))
        check(uc.reg_read(mk.UC_M68K_REG_PC) == E.STOP and uc.reg_read(mk.UC_M68K_REG_A7) == sp0 + 4 and regs
              and cleared and not bad,
              "0x400004b2 -> notre crochet -> remise à zéro du BSS de l'OS (charge utile rangée comprise), retour "
              "normal, d2..d7/a2..a6 intacts")
    check(stale[1] and not stale[0],
          f"cache d'instructions : le crochet l'invalide (movec cacr, ICINVA) avant d'exécuter le code qu'il vient "
          f"d'écrire (2e étage) ; Unicorn n'a pas de cache, la machine si (notes/50 §8) "
          f"{[hex(a) for a in stale[0][:4]]}")
    got = bytes(uc.mem_read(dst, len(rt)))
    check(got == rt, f"charge utile décompressée à {dst:#x} : {len(rt)} o (moteurs, MACRO et ses variables à zéro), "
                     f"rangée en {fw.packed} o dans l'image ; tables d'ondes de CHORD reprises en SRAM")
    # la partie des moteurs : celle des moteurs seuls, sauf ce qui compte les machines (détours, données,
    # descripteurs, rangées) ; les tables d'ondes de CHORD aux mêmes adresses, mêmes octets
    rref = ref.runtime
    diff = [k for k in range(0, len(rref), 4) if rref[k:k + 4] != got[k:k + 4]]
    allowed = [(gs.LAYOUT["STUBS"], gs.LAYOUT["DESCN"] + 0x1730)]
    off = [k for k in diff if not any(lo <= k < hi for lo, hi in allowed)]
    c0 = fw.chord_at - dst
    check(not off and rref[c0:c0 + 0x7878] == got[c0:c0 + 0x7878],
          f"partie des moteurs identique à celle des moteurs seuls ({len(rref)} o), sauf détours, données et "
          f"descripteurs ({len(diff) * 4} o au plus) ; tables d'ondes de CHORD aux mêmes adresses, mêmes octets "
          f"{[hex(dst + k) for k in off[:4]]}")
    want = bytearray(sram)
    for stage, run, n_ in E.SRAM_BANKS:
        o = stage - E.PAYLOAD_DST
        want[run - 0x80000000:run - 0x80000000 + n_] = rt[o:o + n_]
    check(bytes(uc.mem_read(0x80000000, 0x10000)) == bytes(want),
          "SRAM : les deux zones (code et voix du Syntakt) remplies, le reste intact")
    end = BASE + len(fw.img)
    check(end <= gs.END_LIMIT, f"image décompressée jusqu'à {end:#x} (limite {gs.END_LIMIT:#x}, marge "
                               f"{gs.END_LIMIT - end} o)")


# --- 2. interface ----------------------------------------------------------------------------------------------
def interface_alone(stock, fw, tw):
    gs.CATALOG.setdefault("macro", dict(gm.MACHINE, label="MACRO"))
    tsm.configure(tw)
    tsm.N = len(tsm.ADDED)
    patched, payload = fw.img, fw.runtime
    a, b = tsm.tables(stock, patched, payload)
    tsm.lookups(a, b)
    tsm.accessors(a, b, stock, patched)
    tsm.screens(stock, patched, payload)
    tsm.setter_and_wheel(stock, patched, payload)
    tsm.records_and_change(stock, patched, payload)
    tsm.out_of_range(stock, patched, payload)
    tsm.small_icon(stock, patched, payload)


# --- 3. son ------------------------------------------------------------------------------------------------------
def multi(fw, setup, blocks, trigs):
    return tm.multi(fw, setup, blocks, trigs)


def same_or_idle(r, x, retrig):
    """Comme test_model_tg_syntakt.same_or_idle : identique jusqu'à l'arrêt d'une voix muette par le régulateur (la
    référence restant ensuite sous le seuil jusqu'au trig suivant), puis à 1e-3 de la crête près."""
    return tms.same_or_idle(r, x, retrig)


def engines_like(fw, ref, codes, first, label):
    """Les 6 machines d'origine, puis chaque moteur du Syntakt : identiques aux moteurs seuls."""
    trigs = {1: 0x3f, 150: 0x3f}
    setup = {t: dict(BASE_KW, machine=t, shape=64, contour=64, decay=60) for t in range(6)}
    r, _ = multi(ref, setup, 300, trigs)
    x, unm = multi(fw, setup, 300, trigs)
    check(np.array_equal(r, x) and np.abs(x).max() > 1e7 and not unm,
          f"{label} : 6 machines d'origine (CHORD et ses tables d'ondes compris), identiques aux moteurs seuls")
    bad = []
    for i, c in enumerate(codes):
        m = gs.CATALOG[c]
        kw = dict(BASE_KW, color=m["knobs"][0][2], shape=m["knobs"][1][2], sweep=m["knobs"][2][2],
                  contour=m["knobs"][3][2], decay=40, machine=first + i)
        t = i % 6
        r, _ = multi(ref, {t: kw}, 300, {1: 1 << t, 150: 1 << t})
        x, unm = multi(fw, {t: kw}, 300, {1: 1 << t, 150: 1 << t})
        if not (np.array_equal(r, x) and np.abs(x[:, t]).max() > 1e7 and not unm):
            bad.append(m["name"])
    check(not bad, f"{label} : chaque moteur ({', '.join(gs.CATALOG[c]['name'] for c in codes)}, machines "
                   f"{first + 1}..{first + len(codes)}) identique aux moteurs seuls {bad}")


def macro_like(fw, alone, label, models=(0, 9, 21, 25, 28, 34, 37, 41, 44)):
    """La piste MACRO, sortie finale : identique à MACRO seule (à l'arrêt de la voix muette près)."""
    bad, cut = [], []
    for m in models:
        kw = dict(BASE_KW, shape=m, decay=40)
        a, _, _ = tm.play(alone, alone.index, kw, 400, (1, 300))
        b, _, unm = tm.play(fw, fw.index, kw, 400, (1, 300))
        ok, f = same_or_idle(a, b, 300)
        cut.append(f)
        if not ok or unm or not b.any():
            bad.append(tm.NAMES[m])
    check(not bad, f"{label} : piste MACRO identique à MACRO seule, {len(models)} modèles (voix muette arrêtée par le "
                   f"régulateur aux blocs {cut}, la référence sous le seuil jusqu'au trig suivant) {bad}")


def together(fw, ref, alone, codes, first, label, sampler=False):
    """Les 6 pistes ensemble : KICK, 1er moteur, MACRO, CHORD (ou le Sampler), dernier moteur, MACRO."""
    k = len(codes)
    mach = [0, first, fw.index, 6 if sampler else 5, first + k - 1, fw.index]
    models = {2: 0, 5: 9}                                   # CSAW, TRIPLE SAW : sans le générateur aléatoire
    kw = {}
    for t, m in enumerate(mach):
        kw[t] = dict(BASE_KW, machine=m, shape=models.get(t, 64), decay=40)
        if first <= m < first + k:
            e = gs.CATALOG[codes[m - first]]
            kw[t].update(color=e["knobs"][0][2], shape=e["knobs"][1][2], sweep=e["knobs"][2][2],
                         contour=e["knobs"][3][2])
    trigs = {1: 0x3f, 150: 0x3f}
    x, unm = multi(fw, kw, 300, trigs)
    r, _ = multi(ref, {t: dict(v, machine=0) if t in models else v for t, v in kw.items()}, 300, trigs)
    ok, res = not unm, []
    for t in range(6):
        if t in models:
            y, _, _ = tm.play(alone, alone.index, dict(BASE_KW, shape=models[t], decay=40), 300, (1, 150), track=t)
            good, f = same_or_idle(y, x[:, t], 150)
            ok &= good and x[:, t].any()
            res.append(f)
        else:
            ok &= np.array_equal(x[:, t], r[:, t])
    if sampler:
        ok &= not x[:, 3].any()
    names = ["KICK", "moteur", "MACRO", "Sampler" if sampler else "CHORD", "moteur", "MACRO"]
    check(ok, f"{label} : pistes {', '.join(f'{n} ({m + 1})' for n, m in zip(names, mach))} ensemble ; machines "
              f"d'origine et moteurs identiques aux moteurs seuls, pistes MACRO à MACRO seule (arrêt {res})")


def locks(fw, codes, first, label):
    """Machine locks sur une piste : SNARE, 1er moteur, MACRO (FM), TONE, dernier moteur, MACRO (WAVETABLES), KICK."""
    seq = [dict(machine=1), dict(machine=first), dict(machine=fw.index, shape=25), dict(machine=4),
           dict(machine=first + len(codes) - 1), dict(machine=fw.index, shape=37), dict(machine=0)]
    e = fw.engine(solo=0)
    e.set(0, **dict(BASE_KW, machine=1, decay=40))
    out = []
    for b in range(60 * len(seq)):
        if b % 60 == 0:
            e.set(0, **seq[b // 60])
        out.append(e.block(1 if b % 60 == 1 else 0)[0])
    x = np.stack(out)
    parts = [int(np.abs(x[60 * k + 2:60 * k + 60]).max()) for k in range(len(seq))]
    check(all(p > 1e6 for p in parts) and not e.unmapped,
          f"{label} : machine locks SNARE -> moteur -> MACRO (FM) -> TONE -> moteur -> MACRO (WAVETABLES) -> KICK "
          f"sur une piste : tout joue (crêtes {[f'{p:.2g}' for p in parts]})")


TIMER, BLOCK = 0xfc07000c, 90112
GAINS = (0x40a78c08, 0x40a78be8, 0x40a78bd0, 0x40a78bb8, 0x40a78b9c, 0x40a78b80)   # gov_gains.S, comme test_governor
FULL = 0x20000000


def governor(fw, tw, label, sampler=False):
    """Surcharge (comme test_model_tg_syntakt.governor et test_governor) : 6 pistes MACRO (avec Model-TG, le Sampler en
    piste 3). Charge fixe de 97 % : le régulateur éteint toutes les pistes MACRO, jamais le Sampler. Charge qui suit les
    voix calculées (46 % + 7 % par voix, comme test_governor) : il en éteint une partie seulement, puis la charge
    retombe ; les pistes épargnées restent identiques à la référence, les pistes éteintes se taisent."""
    sy = {k: int(v, 16) for k, v in tw["gov"].items()}
    setup = {t: dict(BASE_KW, machine=fw.index, shape=(0, 1, 2, 3, 9, 10)[t], note=48 + 5 * t, decay=100)
             for t in range(6)}
    if sampler:
        setup[2] = dict(BASE_KW, machine=6, decay=100)
    cost = 2 * 7 * BLOCK // 100                    # par voix calculée, la moitié entre voice_gate et voice_after

    def play_(load_):
        """load_ : None ou fonction (bloc, voix calculées dans ce bloc) -> charge en %."""
        e = fw.engine()
        if fw.blob_end is None:
            e.uc.mem_map(0x40800000, 0x00800000)   # BSS de l'OS (Model-TG l'a déjà) : le régulateur y lit les gains
        for t in range(6):
            for a in GAINS:
                e.uc.mem_write(a + 4 * t, struct.pack(">I", FULL))
        clock = {"t": 10_000_000, "fixed": None, "reads": 0}

        def read(uc, access, addr, size, value, ud):
            if clock["fixed"] is None:
                clock["t"] += cost // 2
                clock["reads"] += 1
                v = clock["t"]
            else:
                v = clock["fixed"]
            uc.mem_write(TIMER, struct.pack(">I", v & 0xffffffff))
        e.uc.hook_add(UC_HOOK_MEM_READ, read, begin=TIMER, end=TIMER + 3)
        for t, kw in setup.items():
            e.set(t, **kw)
        e.uc.mem_write(tms.gs_x(tw, "X_SLOW"), struct.pack(">I", 88 * 65536 // 100))
        out, stolen, now = [], set(), 10_000_000
        for b in range(300):
            clock["reads"] = 0
            out.append(e.block(0x3f if b == 1 else 0))
            if load_ is not None:
                e.uc.mem_write(sy["gov_t0_audio"], struct.pack(">I", now & 0xffffffff))
                clock["fixed"] = now + load_(b, clock["reads"] // 2) * BLOCK // 100
                e.call(sy["audio_end"])
                clock["fixed"] = None
                now += BLOCK
            stolen |= {t for t, v in enumerate(bytes(e.uc.mem_read(sy["gov_stolen"], 6))) if v}
        return np.stack(out), stolen, e.unmapped
    ref, _, _ = play_(None)
    macro = set(range(6)) - ({2} if sampler else set())
    silent = lambda mod, ts: all(not np.abs(mod[-50:, t]).max() and np.abs(ref[-50:, t]).max() for t in ts)
    for name, load_, want in (("charge fixe de 97 %", lambda b, n: 97 if b < 200 else 50, lambda st: st == macro),
                              ("charge de 46 % + 7 % par voix calculée", lambda b, n: 46 + 7 * n,
                               lambda st: st and st < macro)):
        mod, stolen, unm = play_(load_)
        spared = set(range(6)) - stolen
        same = all(np.array_equal(ref[:, t], mod[:, t]) for t in spared)
        check(want(stolen) and same and silent(mod, stolen) and not unm,
              f"{label} : surcharge ({name}) : pistes MACRO éteintes {sorted(t + 1 for t in stolen)}, muettes ensuite"
              f"{', jamais le Sampler (piste 3)' if sampler else ''} ; les autres "
              f"{sorted(t + 1 for t in spared)} identiques à la référence")


def exact_some(fw, ref_braids, label):
    """Avant la chaîne d'ampli, exactement Braids (test_macro.exact) : quelques modèles et variantes."""
    todo = [c for c in tm.cases(True) if c[0][:2].strip().isdigit() or c[0].startswith(("DECAY 10", "modèle qui"))]
    tm.exact(fw, ref_braids, todo, label)


def run_set(stock, ctx, codes, tg_ctx, others, label_extra=""):
    """Toutes les vérifications pour une version (seule ou avec Model-TG), avec d'autres mods éventuels."""
    tg = tg_ctx is not None
    first = gs.TG_FIRST if tg else 6
    tw = load(f"{31 if tg else 24}-{gms.tweak_id(codes, tg)}.json")
    tw_ref = load(f"{31 if tg else 24}-{gs.tweak_id(codes, tg=tg)}.json")
    tw_macro = load("32-macro-tg.json" if tg else "25-macro.json")
    base = ([load("30-model-tg-st.json")] if tg else []) + others
    order = lambda ts: sorted(ts, key=lambda t: t["order"])
    fw, ref, alone = Fw(stock, order(base + [tw]), ctx), Fw(stock, order(base + [tw_ref]), ctx), \
        Fw(stock, order(base + [tw_macro]), ctx)
    names = ", ".join(gs.CATALOG[c]["name"] for c in codes)
    print(f"\n== {tw['id']}{label_extra} : {names} en machines {first + 1}..{first + len(codes)}, MACRO en machine "
          f"{fw.index + 1}")
    print("démarrage")
    t7.X.bootstrap_depack_ok(ctx["cycles"], fw.tweaks, ctx["syntakt"]) or t7.FAIL.append("bootstrap " + tw["id"])
    tgs = None
    if tg:
        tg_tw = next(t for t in fw.tweaks if t["id"].startswith("model-tg"))     # pas forcément le 1er (6ch-usbup)
        tgs = {k: int(v, 16) for k, v in tg_tw["symbols"].items()}
        tgs["knob_vec"] = tms.knob_vec_at(tw)
    boot(fw, ref, tgs)
    if not others:
        print("interface")
        if tg:
            gs.set_base(gs.PAY_TG)
            gs.CATALOG.setdefault("macro", dict(gm.MACHINE, label="MACRO"))
            tref = Fw(stock, [base[0]], ctx)
            tms.interface(tref, fw, codes + ["macro"], tgs)
        else:
            interface_alone(stock, fw, tw)
    print("son")
    gs.set_base(fw.dest)
    if not others:
        exact_some(fw, ctx["braids"], f"MACRO avec {names}")
    engines_like(fw, ref, codes, first, f"avec MACRO{label_extra}")
    macro_like(fw, alone, f"MACRO avec {names}{label_extra}")
    together(fw, ref, alone, codes, first, f"ensemble{label_extra}", sampler=tg)
    locks(fw, codes, first, f"avec {names}{label_extra}")
    print("régulateur de charge")
    governor(fw, tw, f"MACRO avec {names}{label_extra}", sampler=tg)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--syntakt", required=True, help="Syntakt_OS1.42.syx (ou 1.41) officiel")
    ap.add_argument("--eurorack", required=True, help="clone de pichenettes/eurorack (tools/gen_macro.py)")
    ap.add_argument("--engines", default=",".join(gs.CATALOG), help="moteurs (défaut : les 5)")
    ap.add_argument("--with", dest="others", default="", help="ids d'autres tweaks (sans Model-TG : model-tg-st "
                                                              "ajoute la version combinée)")
    ap.add_argument("--only", choices=("alone", "tg"), help="une seule des deux versions")
    args = ap.parse_args()
    repo = pathlib.Path(args.eurorack).resolve()
    gm.check_sources(repo)
    codes = [c for c in gs.CATALOG if c in args.engines.split(",")]
    stock = T.main_os_from_syx(args.cycles)
    st_img = syntakt.dsp_image(args.syntakt)
    tg_ctx = gs.tg_context(stock)
    with tempfile.TemporaryDirectory() as d:
        ctx = dict(cycles=args.cycles, syntakt=args.syntakt, st_img=st_img, chord=chord_tables(stock),
                   braids=tm.Ref(pathlib.Path(d), repo))
        if args.others:
            by_id = {t["id"]: t for t in (load(f.name) for f in sorted(tm.DEV.glob("[0-9]*.json")))}
            ids = args.others.split(",")
            tg = "model-tg-st" in ids
            others = [by_id[i] for i in ids if i != "model-tg-st"]
            run_set(stock, ctx, codes, tg_ctx if tg else None, others, f" avec {', '.join(ids)}")
        else:
            for tg in (False, True):
                if args.only and args.only != ("tg" if tg else "alone"):
                    continue
                run_set(stock, ctx, codes, tg_ctx if tg else None, [])
    fail = t7.FAIL + tms.FAIL
    print("\nTOUT OK" if not fail else f"\n{len(fail)} ÉCHEC(S)")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
