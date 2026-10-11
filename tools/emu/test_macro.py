#!/usr/bin/env python3
"""Preuve de la machine MACRO (notes/43) : les 47 modèles de Braids (code MIT d'Émilie Gillet) en machine ajoutée,
seule (25-macro.json, 7e machine) et avec Model-TG (32-macro-tg.json par-dessus 30-model-tg-st.json, 8e machine).
Le vrai code de l'OS, émulé (Unicorn), avec la charge utile telle que le crochet de démarrage la reconstitue.

  1. Démarrage : le décompresseur du bootstrap relit l'OS agrandi ; le crochet (stub.S, PACK) remet à zéro la zone
     de la charge utile, y recopie ses morceaux, ne touche pas à la SRAM, puis reprend : seul, la remise à zéro du
     BSS de l'OS ; avec Model-TG, boot_extra_hook, pile et registres intacts.
  2. Interface : les vérifications de test_syntakt_machines.py (seul) et de test_model_tg_syntakt.py (avec
     Model-TG), appliquées à MACRO : rangées, recherches, descripteurs (Model de 0 à 46), écran MACHINES, molette,
     enregistrements, changement de machine réel, potards, icône.
  3. Son :
     - avant la chaîne d'ampli, la sortie de MACRO est EXACTEMENT celle de Braids compilé pour l'ordinateur depuis
       les mêmes sources (braids_ref.cc), avec les réglages que la passerelle doit lui donner (calculés ici d'après
       notes/43 : modèle, note, TIMBRE, COLOR, frappe), passée par le filtre demi-bande calculé ici : les 47 modèles,
       et des variantes (potards aux bouts, enveloppe sur TIMBRE, modèle et potards qui bougent pendant la note,
       notes extrêmes, PUNCH, GATE, voix qui se tait puis repart) ;
     - Braids rend par blocs de 24 échantillons, comme sur le module (4 000 par seconde) : 3, 3 puis 2 appels de
       MacroOscillator::Render par bloc du Cycles, comptés à son entrée ;
     - une voix est calculée exactement quand l'OS l'impose (trig, ou enveloppe d'ampli au-dessus de 2^14, lue dans
       la voix à l'entrée de macro_render) ; muette : sortie nulle, aucun appel de Render ;
     - la chaîne d'ampli (DECAY, GATE, PUNCH) lit dans la voix exactement ce qu'elle lit pour TONE ;
     - les machines d'origine ne changent pas (OS d'origine ; avec Model-TG, Model-TG seul) et aucune instruction
       de Braids ne tourne sans piste MACRO ;
     - MACRO avec Model-TG = MACRO seule ; machine locks ; 6 pistes MACRO ensemble ; MACRO mêlée aux machines
       d'origine (et au Sampler de Model-TG, qui reste muet sans échantillon), chaque piste identique à sa référence ;
     - le filtre demi-bande tient sa spécification.
  4. Coût : instructions par bloc de chaque modèle (une voix, une voix muette, un changement de modèle), pile.
  5. Avec les autres mods (--with) : démarrage, machines d'origine identiques aux mêmes mods sans MACRO, et MACRO
     identique à MACRO seule (ou avec Model-TG seul, si model-tg-st est dans la liste).

    python3 tools/emu/test_macro.py --cycles model-cycles_OS1.13.syx --eurorack vendor/eurorack [--quick] \
        [--with 6ch-usbup,model-tg-st,trig-hold,arp,tempo-max,boot-anim]

Durée : environ 45 min (les 47 modèles, seule et avec Model-TG), 25 min avec --quick, plus 5 min avec --with.

--eurorack : le clone de pichenettes/eurorack au commit de tools/gen_macro.py (référence compilée avec g++).
"""
import argparse
import json
import pathlib
import struct
import subprocess
import sys
import tempfile

import numpy as np
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_UNMAPPED
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import gen_macro as gm              # noqa: E402
import gen_syntakt_engines as gs    # noqa: E402
import mcengine as E                # noqa: E402
import test_model_tg as TM          # noqa: E402
import test_model_tg_syntakt as tms  # noqa: E402
import test_sdvintage as T          # noqa: E402
import test_sdvintage_7th as t7     # noqa: E402
import test_syntakt_machines as tsm  # noqa: E402

DEV = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13"
BASE = E.BASE
check = t7.check                    # échecs : t7.FAIL (et tms.FAIL pour l'interface avec Model-TG)

# la passerelle (tools/machines/macro/macro.cc)
HB = (10327, -3131, 1579, -820, 434, -197)
HIST = 22
IDLE_LEVEL = 1 << 14
MARK = 0x4d435231
# chaîne d'ampli de l'OS, appelée par la passerelle comme par TONE : fonctions sans appel (début, fin)
AMP = ((0x400a9252, 0x400a9302), (0x400a9430, 0x400a9498), (0x400a967a, 0x400a9756))
TONE = 4
OFF = 9                             # machine hors limites : la voix n'est pas calculée
NAMES = gm.MODELS
BASE_KW = dict(note=60, pitch=64, color=64, shape=0, sweep=64, contour=0, punch=0, gate=0, finetune=64, decay=50)


def load(name):
    return json.loads((DEV / name).read_text(encoding="utf-8"))


class Fw:
    """Un firmware : MAIN OS (avec ce qui est ajouté après), et la charge utile de MACRO telle qu'en mémoire."""

    def __init__(self, stock, tweaks):
        p, _ = build.apply_writes(stock, tweaks)
        pl, _ = build.build_payload(tweaks, stock, None)
        self.img, self.tweaks = bytes(p) + pl, tweaks
        tg = [t for t in tweaks if t["id"].startswith("model-tg")]
        self.blob_end = BASE + len(stock) + tg[0]["append"]["size"] if tg else None
        ours = [t for t in tweaks if t["id"].startswith("macro")]
        self.payload = None
        if not ours:
            return
        ap_ = ours[0]["append"]
        self.pay = int(ap_["dest"], 16)
        self.runtime = build.payload_runtime(ours[0], stock, None)
        self.payload = (self.pay, self.runtime)
        self.code_end = self.pay + len(ap_["parts"][0]["hex"]) // 2          # code et tables de Braids
        self.nm = gs.TG_FIRST + 1 if tg else 7
        self.index = self.nm - 1                                            # MACRO
        data = self.pay + gs.LAYOUT["DATA"]
        u32 = lambda va: struct.unpack_from(">I", self.runtime, va - self.pay)[0]
        self.upd = u32(data + 4 * self.nm + 4 * self.index)
        self.rnd = u32(data + 8 * self.nm + 4 * self.index)
        self.braids_render = int(ours[0]["symbols"]["braids_render"], 16)       # MacroOscillator::Render

    def engine(self, solo=None):
        if self.blob_end:
            e = TM.engine(self.img, end=self.blob_end, payload=self.payload)
        else:
            e = E.Engine(self.img, payload=self.payload)
        if solo is not None:             # les autres pistes : machine hors limites, rien n'est calculé
            for t in range(6):
                if t != solo:
                    e.uc.mem_write(E.VOICE0 + t * E.VSTRIDE, struct.pack(">II", OFF, OFF))
        return e


# --- 1. démarrage ----------------------------------------------------------------------------------------------
def boot(fw, tg=None):
    """Le crochet de démarrage, exécuté pour de vrai : seul, au début de la remise à zéro du BSS (0x400004b2, jusqu'à
    son retour) ; avec Model-TG, par le jsr de 0x40000530, jusqu'à boot_extra_hook de Model-TG."""
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
    bad = []
    uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: bad.append(addr) or False)
    keep = {r: 0x11110000 + i for i, r in enumerate((mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4,
                                                     mk.UC_M68K_REG_D5, mk.UC_M68K_REG_D6, mk.UC_M68K_REG_D7,
                                                     mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3, mk.UC_M68K_REG_A4,
                                                     mk.UC_M68K_REG_A5, mk.UC_M68K_REG_A6))}
    for r, v in keep.items():
        uc.reg_write(r, v)
    sp0 = 0x90010000
    if tg:
        uc.reg_write(mk.UC_M68K_REG_A7, sp0)
        uc.emu_start(gs.BOOT_CALL, tg["boot_extra_hook"], count=5_000_000)
        pc, sp = uc.reg_read(mk.UC_M68K_REG_PC), uc.reg_read(mk.UC_M68K_REG_A7)
        ret = struct.unpack(">I", uc.mem_read(sp, 4))[0]
        regs = all(uc.reg_read(r) == v for r, v in keep.items())
        check(pc == tg["boot_extra_hook"] and sp == sp0 - 4 and ret == gs.BOOT_CALL + 6 and regs and not bad,
              f"jsr 0x40000530 -> notre crochet -> boot_extra_hook {tg['boot_extra_hook']:#x}, pile et d2..d7/a2..a6 "
              "intactes")
        check(bytes(uc.mem_read(BASE, len(fw.img))) == fw.img, "image (OS, Model-TG, nos morceaux) inchangée")
    else:
        uc.mem_write(sp0, struct.pack(">I", E.STOP))
        uc.reg_write(mk.UC_M68K_REG_A7, sp0)
        uc.emu_start(0x400004b2, E.STOP, count=100_000_000)
        regs = all(uc.reg_read(r) == v for r, v in keep.items())
        tail = BASE + E.IMAGE_LEN
        cleared = not any(uc.mem_read(tail, len(fw.img) - E.IMAGE_LEN)) and not any(uc.mem_read(0x42338000, 0xb0))
        check(uc.reg_read(mk.UC_M68K_REG_PC) == E.STOP and uc.reg_read(mk.UC_M68K_REG_A7) == sp0 + 4 and regs
              and cleared and not bad,
              "0x400004b2 -> notre crochet -> remise à zéro du BSS de l'OS (nos morceaux rangés compris), retour "
              "normal, d2..d7/a2..a6 intacts")
    got = bytes(uc.mem_read(dst, len(rt)))
    packed = sum(n for _, n in next(t for t in fw.tweaks if t["id"].startswith("macro"))["append"]["pack"])
    check(got == rt, f"charge utile reconstituée à {dst:#x} : {len(rt)} o (code et tables de Braids, détours, "
                     f"données, puis ses variables à zéro), rangée en {packed} o dans l'image")
    check(bytes(uc.mem_read(0x80000000, 0x10000)) == bytes(sram), "SRAM intacte")
    end = BASE + len(fw.img)
    check(end <= gs.END_LIMIT, f"image décompressée jusqu'à {end:#x} (limite {gs.END_LIMIT:#x})")


# --- 2. interface ----------------------------------------------------------------------------------------------
def interface_alone(stock, fw):
    """Les vérifications de test_syntakt_machines.py, pour une machine ajoutée : MACRO."""
    tsm.SAFE = True
    tsm.ADDED = [dict(gm.MACHINE, code="macro", index=6, label="MACRO")]
    tsm.N, tsm.NM, tsm.TOP = 1, 7, 6
    tsm.FIRST, tsm.REC = {6: 76}, {6: gs.RECS}
    tsm.ROWS, tsm.CCROWS = gs.ROWSN, gs.CCROWSN
    tsm.NAMES = ["Kick", "Snare", "Metal", "Perc", "Tone", "Chord", gm.MACHINE["name"]]
    patched, payload = fw.img, fw.runtime
    a, b = tsm.tables(stock, patched, payload)
    tsm.lookups(a, b)
    tsm.accessors(a, b, stock, patched)
    tsm.screens(stock, patched, payload)
    tsm.setter_and_wheel(stock, patched, payload)
    tsm.records_and_change(stock, patched, payload)
    tsm.out_of_range(stock, patched, payload)
    tsm.small_icon(stock, patched, payload)


# --- 3. son : la référence -------------------------------------------------------------------------------------
class Ref:
    """Braids compilé pour l'ordinateur (braids_ref.cc + les sources compilées dans le tweak)."""

    def __init__(self, tmp, repo):
        self.exe = tmp / "braids_ref"
        subprocess.run(["g++", "-O2", "-I", str(repo), str(HERE / "braids_ref.cc"),
                        *[str(repo / s) for s in gm.SOURCES], "-o", str(self.exe)], check=True)

    def run(self, recs):
        lines = "".join(f"{r['render']} {r['shape']} {r['pitch']} {r['timbre']} {r['color']} {r['strike']}\n"
                        for r in recs)
        out = subprocess.run([str(self.exe)], input=lines.encode(), capture_output=True, check=True).stdout
        return np.frombuffer(out, dtype="<i2").reshape(-1, 64).astype(np.int64)


def knob(x):
    x = min(max(x, 0), 0x7f00)
    return x + (x >> 7)


def spec(pmod, vb, pb):
    """Les réglages que la passerelle doit donner à Braids (notes/43 §3), d'après la voix et les paramètres de la
    piste à l'entrée de macro_update."""
    s16 = lambda o: struct.unpack_from(">h", pb, o)[0]
    s32 = lambda o: struct.unpack_from(">i", vb, o)[0]
    trig = s32(0x38) != 0
    n = (s16(0x14) << 8) + ((s16(0x22) - 0x4000) << 3) - (64 << 16) + pmod
    n = min(max(n, 0), 127 << 16)
    env = 32767 if trig else min(abs(s32(0x230)) >> 16, 32767)
    return dict(shape=min(max(s16(0x18) >> 8, 0), len(NAMES) - 1), pitch=n >> 9,
                timbre=min(knob(s16(0x16)) + ((env * knob(s16(0x1c))) >> 15), 32767), color=knob(s16(0x1a)),
                strike=int(trig), render=0, init=s32(0x2c) != MARK)


def decimate(x64):
    """Le filtre demi-bande de la passerelle, en entiers : 64 échantillons à 96 kHz par bloc -> 32 à 48 kHz."""
    hist, out = np.zeros(HIST, np.int64), []
    c = HIST // 2 + 2 * np.arange(32)
    for blk in x64:
        x = np.concatenate([hist, blk])
        acc = x[c] << 14
        for k, h in enumerate(HB):
            acc = acc + h * (x[c - 2 * k - 1] + x[c + 2 * k + 1])
        out.append(acc)
        hist = x[64:64 + HIST]
    return np.array(out, np.int64).reshape(-1, 32)


class Probe:
    """Ce que reçoit la passerelle à chaque bloc (entrée de macro_update) et ce qu'elle sort avant la chaîne d'ampli
    (entrée de AMP_ENV appelée depuis la charge utile) ; les lectures de la voix par la chaîne d'ampli."""

    def __init__(self, fw, e, track, reads=False):
        self.recs, self.outs, self.block, self.reads = [], [], 0, [] if reads else None
        self.v = E.VOICE0 + track * E.VSTRIDE
        self.out_at = None
        uc = e.uc
        arg = lambda k: struct.unpack(">I", uc.mem_read(uc.reg_read(mk.UC_M68K_REG_A7) + 4 * k, 4))[0]

        def upd(uc_, a, s, u):
            if arg(2) != self.v:
                return
            pmod = struct.unpack(">i", uc.mem_read(uc.reg_read(mk.UC_M68K_REG_A7) + 4, 4))[0]
            r = spec(pmod, bytes(uc.mem_read(self.v, E.VSTRIDE)), bytes(uc.mem_read(arg(3), 0x40)))
            r["block"], r["calls"] = self.block, 0
            self.recs.append(r)

        def rnd(uc_, a, s, u):
            if arg(2) == self.v:
                self.out_at = arg(1)
                v32 = lambda o: struct.unpack(">i", uc.mem_read(self.v + o, 4))[0]
                # ce que l'OS impose : une voix déclenchée, ou dont l'enveloppe d'ampli n'est pas encore éteinte
                self.recs[-1]["expected"] = int(bool(v32(0x34) or v32(0x38) or abs(v32(0x230)) >= IDLE_LEVEL
                                                     or abs(v32(0x234)) >= IDLE_LEVEL))

        def calls(uc_, a, s, u):
            if self.recs:
                self.recs[-1]["calls"] += 1

        def amp(uc_, a, s, u):
            if fw.pay <= arg(0) < fw.code_end and arg(1) == self.v:
                self.recs[-1]["render"] = 1
                self.outs.append(np.frombuffer(bytes(uc.mem_read(self.out_at, 128)), ">i4").astype(np.int64))
        uc.hook_add(UC_HOOK_CODE, upd, begin=fw.upd, end=fw.upd)
        uc.hook_add(UC_HOOK_CODE, rnd, begin=fw.rnd, end=fw.rnd)
        uc.hook_add(UC_HOOK_CODE, calls, begin=fw.braids_render, end=fw.braids_render)
        uc.hook_add(UC_HOOK_CODE, amp, begin=AMP[0][0], end=AMP[0][0])
        if reads:
            uc.hook_add(UC_HOOK_MEM_READ, self._read, begin=self.v, end=self.v + E.VSTRIDE - 1)

    def _read(self, uc, access, addr, size, value, ud):
        pc = uc.reg_read(mk.UC_M68K_REG_PC)
        if any(lo <= pc < hi for lo, hi in AMP):
            self.reads.append((self.block, addr - self.v, bytes(uc.mem_read(addr, size))))


def play(fw, idx, kw, blocks, trigs=(1,), changes=None, track=0, reads=False):
    """Une piste sur la machine idx, les autres éteintes. changes : {bloc : réglages} (p-locks, potards)."""
    e = fw.engine(solo=track)
    e.set(track, machine=idx, **kw)
    pr = Probe(fw, e, track, reads) if fw.payload else None
    out = []
    for b in range(blocks):
        for k, v in (changes or {}).get(b, {}).items():
            e.set(track, **{k: v})
        if pr:
            pr.block = b
        out.append(e.block(1 << track if b in trigs else 0)[track])
    return np.stack(out), pr, e.unmapped


def cases(quick):
    """(nom, réglages, trigs, changements, blocs) : chaque modèle, puis des variantes."""
    out = [(f"{m:2} {NAMES[m]}", dict(BASE_KW, shape=m), (1, 70), None, 140)
           for m in (range(len(NAMES)) if not quick else (0, 9, 23, 28, 34, 37, 44))]
    some = (0, 21, 25, 28, 34, 37, 44) if not quick else (0, 28)
    for m in some:
        n = NAMES[m]
        out += [
            (f"{n} COLOR 0", dict(BASE_KW, shape=m, color=0), (1,), None, 60),
            (f"{n} COLOR 127", dict(BASE_KW, shape=m, color=127), (1,), None, 60),
            (f"{n} SWEEP 0", dict(BASE_KW, shape=m, sweep=0), (1,), None, 60),
            (f"{n} SWEEP 127", dict(BASE_KW, shape=m, sweep=127), (1,), None, 60),
            (f"{n} CONTOUR 127, DECAY 25", dict(BASE_KW, shape=m, color=10, contour=127, decay=25), (1, 90), None, 180),
            (f"{n} note 24, FINE 0", dict(BASE_KW, shape=m, note=24, finetune=0), (1,), None, 60),
            (f"{n} note 96, FINE 127", dict(BASE_KW, shape=m, note=96, finetune=127), (1,), None, 60),
        ]
    out += [
        ("PITCH 0, note 0 : borné en bas", dict(BASE_KW, shape=0, pitch=0, note=0), (1,), None, 40),
        ("PITCH 127, note 127 : borné en haut", dict(BASE_KW, shape=0, pitch=127, note=127), (1,), None, 40),
        ("PUNCH", dict(BASE_KW, shape=34, punch=1), (1,), None, 60),
        ("GATE", dict(BASE_KW, shape=1, gate=1, decay=20), (1,), {50: {"gate": 0}}, 120),
        ("DECAY 10 : la voix se tait, puis repart", dict(BASE_KW, shape=25, decay=10), (1, 200), None, 260),
        ("DECAY 10, PLUCKED : la voix se tait, puis repart", dict(BASE_KW, shape=28, decay=10), (1, 200), None, 260),
        ("DECAY 10, WAVETABLES : la voix se tait, puis repart", dict(BASE_KW, shape=37, decay=10), (1, 200), None,
         260),
        ("modèle qui change pendant la note", dict(BASE_KW, shape=0, decay=100), (1,),
         {30: {"shape": 23}, 60: {"shape": 37}, 90: {"shape": 37.4}, 100: {"shape": 2}}, 130),
        ("modèle qui change avec des trigs", dict(BASE_KW, shape=24, decay=60), (1, 40, 80),
         {40: {"shape": 30}, 80: {"shape": 14}}, 120),
        ("COLOR et SWEEP qui bougent à chaque bloc", dict(BASE_KW, shape=21, decay=100), (1,),
         {b: {"color": (3 * b) % 128, "sweep": 127 - (5 * b) % 128} for b in range(100)}, 100),
        ("Model au-delà de 46 (d'une autre machine) : 46", dict(BASE_KW, shape=127), (1,), None, 40),
    ]
    return out


# --- 3. son : les vérifications --------------------------------------------------------------------------------
def exact(fw, ref, todo, label):
    """Avant la chaîne d'ampli : identique à Braids (référence), et une voix muette n'est pas calculée."""
    bad, idle_seen, peaks, gate_bad, calls_bad, blocks_seen = [], 0, [], [], [], 0
    for name, kw, trigs, changes, blocks in todo:
        out, pr, unm = play(fw, fw.index, kw, blocks, trigs, changes)
        x = ref.run(pr.recs)
        want, got = decimate(x), np.array(pr.outs, np.int64).reshape(-1, 32)
        idle = [r["block"] for r in pr.recs if not r["render"]]
        silent = not out[idle].any() if idle else True
        idle_seen += len(idle)
        blocks_seen += len(pr.recs)
        if any(r.get("expected") != r["render"] for r in pr.recs):
            gate_bad.append(name)
        # des blocs de 24 : à chaque bloc calculé, juste assez d'appels pour 64 échantillons ; aucun sinon
        fill = 0
        for r in pr.recs:
            want_calls = 0
            if r["init"]:
                fill = 0
            if r["render"]:
                while fill < 64:
                    fill, want_calls = fill + 24, want_calls + 1
                fill -= 64
            if r["calls"] != want_calls:
                calls_bad.append(name)
                break
        inits = sum(r["init"] for r in pr.recs)
        peak = int(np.abs(got).max()) if len(got) else 0
        peaks.append(peak)
        ok = len(want) == len(got) > 0 and np.array_equal(want, got) and silent and not unm and inits == 1 \
            and peak > 1 << 20
        if not ok:
            first = next((i for i in range(min(len(want), len(got))) if not np.array_equal(want[i], got[i])), None)
            bad.append(name)
            print(f"        ECART {name} : {len(got)} blocs rendus / {len(want)} attendus, 1er bloc différent {first},"
                  f" crête {peak:.3g}, init {inits}, muets non nuls {not silent}, hors mémoire {unm[:2]}")
    check(not bad, f"{label} : avant la chaîne d'ampli, identique échantillon par échantillon à Braids compilé pour "
                   f"l'ordinateur, puis filtre demi-bande ({len(todo)} cas : les modèles et des variantes, crêtes "
                   f"{min(peaks):.2g} à {max(peaks):.2g} sur 2^31) {bad[:5]}")
    check(idle_seen > 0 and not gate_bad, f"{label} : voix calculée exactement quand l'OS l'impose (trig, ou enveloppe "
          f"d'ampli au-dessus de 2^14), sur {blocks_seen} blocs ; {idle_seen} blocs de voix muette, sortie nulle "
          f"{gate_bad[:5]}")
    check(not calls_bad, f"{label} : Braids rend par blocs de 24 échantillons comme sur le module (3, 3 puis 2 appels "
                         f"de Render par bloc calculé, aucun pour une voix muette) {calls_bad[:5]}")


def amp_like_tone(fw):
    """La chaîne d'ampli (enveloppe, VCA, PUNCH) lit dans la voix MACRO exactement ce qu'elle lit dans une voix TONE,
    bloc par bloc, tant que la voix MACRO est calculée."""
    res = []
    for kw in (dict(decay=30), dict(decay=90, punch=1), dict(decay=60, gate=1), dict(decay=127, punch=1, gate=1)):
        k = dict(BASE_KW, shape=3, **kw)
        changes = {60: {"gate": 0}} if kw.get("gate") else None
        _, pt, _ = play(fw, TONE, k, 120, (1, 40), changes, reads=True)
        _, pm, unm = play(fw, fw.index, k, 120, (1, 40), changes, reads=True)
        stop = next((r["block"] for r in pm.recs if not r["render"]), 120)
        rt = [x for x in pt.reads if x[0] < stop]
        rm = [x for x in pm.reads if x[0] < stop]
        res.append((rt == rm and len(rm) > 0 and not unm, stop, len({o for _, o, _ in rm})))
    check(all(ok for ok, _, _ in res),
          f"chaîne d'ampli : mêmes lectures de la voix que TONE (DECAY, PUNCH, GATE ; {res[0][2]} champs), bloc par "
          f"bloc jusqu'au silence (blocs {[s for _, s, _ in res]})")


def stock_unchanged(ref_fw, fw, label):
    """6 pistes sur les machines d'origine (2 trigs) : identiques, et rien du code de Braids ne tourne."""
    def run(f, hook):
        e = f.engine()
        for t in range(6):
            e.set(t, **dict(BASE_KW, machine=t, color=64, shape=64, contour=64, decay=60))
        ran = []
        if hook:
            e.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: ran.append(a), begin=f.pay, end=f.code_end - 1)
        x = np.stack([e.block(0x3f if b in (1, 150) else 0) for b in range(300)])
        return x, ran, e.unmapped
    r, _, _ = run(ref_fw, False)
    x, ran, unm = run(fw, True)
    check(np.array_equal(r, x) and np.abs(x).max() > 1e7 and not ran and not unm,
          f"6 machines d'origine : identiques à {label}, échantillon par échantillon, sans une instruction de Braids")


def like(alone, fw, label):
    """Sortie finale de la piste MACRO identique dans deux firmwares (avec Model-TG : son étage d'amplitude, Attack 0,
    filtre ouvert)."""
    bad = []
    for m in (0, 21, 28, 34, 37):
        kw = dict(BASE_KW, shape=m, decay=40)
        a, _, _ = play(alone, alone.index, kw, 200, (1, 120))
        b, _, unm = play(fw, fw.index, kw, 200, (1, 120))
        if not np.array_equal(a, b) or unm or not a.any():
            bad.append(NAMES[m])
    check(not bad, f"{label}, sortie finale de la piste (5 modèles) {bad}")


def with_others(stock, cycles, ids, alone, tg_fw, tg):
    """MACRO avec d'autres mods (--with) : MACRO seule, ou sa version combinée si model-tg-st est dans la liste."""
    by_id = {t["id"]: t for t in (load(f.name) for f in sorted(DEV.glob("[0-9]*.json")))}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise SystemExit(f"!! tweaks inconnus : {unknown}")
    others = [by_id[i] for i in ids]
    with_tg = any(t["id"].startswith("model-tg") for t in others)
    mine = by_id["macro-tg" if with_tg else "macro"]
    clash = [t["id"] for t in others if mine["id"] in t.get("conflicts", []) or t["id"] in mine["conflicts"]]
    if clash:
        raise SystemExit(f"!! incompatibles avec {mine['id']} : {clash}")
    fw = Fw(stock, sorted(others + [mine], key=lambda t: t["order"]))
    ref_fw = Fw(stock, sorted(others, key=lambda t: t["order"]))
    label = ", ".join(ids)
    print(f"\n== {mine['id']} avec {label} : MACRO en machine {fw.index + 1}")
    print("démarrage")
    t7.X.bootstrap_depack_ok(cycles, fw.tweaks, None) or t7.FAIL.append("bootstrap avec " + label)
    boot(fw, tg if with_tg else None)
    print("son")
    stock_unchanged(ref_fw, fw, "ces mods sans MACRO")
    like(tg_fw if with_tg else alone, fw, f"MACRO avec {label} = MACRO {'avec Model-TG seul' if with_tg else 'seule'}")
    locks(fw, f"MACRO avec {label}")
    mixed(fw, ref_fw, f"MACRO avec {label}", sampler=with_tg)


def locks(fw, label):
    """Machine locks sur une piste : SNARE, MACRO, TONE, MACRO (un autre modèle), KICK : tout joue."""
    seq = [(1, dict(machine=1)), (fw.index, dict(machine=fw.index, shape=25)), (TONE, dict(machine=TONE)),
           (fw.index, dict(machine=fw.index, shape=37)), (0, dict(machine=0))]
    e = fw.engine(solo=0)
    e.set(0, **dict(BASE_KW, machine=1, decay=40))
    out = []
    for b in range(60 * len(seq)):
        if b % 60 == 0:
            e.set(0, **seq[b // 60][1])
        out.append(e.block(1 if b % 60 == 1 else 0)[0])
    x = np.stack(out)
    parts = [int(np.abs(x[60 * k + 2:60 * k + 60]).max()) for k in range(len(seq))]
    marks = struct.unpack(">I", e.uc.mem_read(E.VOICE0 + 0x2c, 4))[0]
    check(all(p > 1e6 for p in parts) and not e.unmapped and marks != MARK,
          f"{label} : machine locks SNARE -> MACRO (FM) -> TONE -> MACRO (WAVETABLES) -> KICK sur une piste : tout "
          f"joue (crêtes {[f'{p:.2g}' for p in parts]})")


def six_tracks(fw, label):
    """6 pistes MACRO, 6 modèles (analogiques : sans le générateur aléatoire de Braids, partagé par les voix) :
    chacune identique à la même piste jouée seule."""
    models = (0, 1, 2, 3, 9, 10)
    e = fw.engine()
    for t, m in enumerate(models):
        e.set(t, **dict(BASE_KW, machine=fw.index, shape=m, note=48 + 5 * t))
    x = np.stack([e.block(0x3f if b in (1, 100) else 0) for b in range(160)])
    ok = not e.unmapped
    for t, m in enumerate(models):
        y, _, unm = play(fw, fw.index, dict(BASE_KW, shape=m, note=48 + 5 * t), 160, (1, 100), track=t)
        ok &= np.array_equal(x[:, t], y) and not unm and y.any()
    check(ok, f"{label} : 6 pistes MACRO ensemble ({', '.join(NAMES[m] for m in models)}), chacune identique à la "
              "même piste jouée seule")


def multi(fw, setup, blocks, trigs):
    """Les 6 pistes, chacune avec ses réglages (setup : {piste : réglages}) ; trigs : {bloc : masque des pistes}."""
    e = fw.engine()
    for t, kw in setup.items():
        e.set(t, **kw)
    return np.stack([e.block(trigs.get(b, 0)) for b in range(blocks)]), e.unmapped


def mixed(fw, ref_fw, label, sampler=False):
    """MACRO mêlée aux autres machines : les pistes d'origine (et le Sampler de Model-TG) identiques au même firmware
    sans MACRO, chaque piste MACRO identique à la même piste jouée seule."""
    trigs = {1: 0x3f, 150: 0x3f}
    mach = [0, fw.index, 6 if sampler else 2, 5, fw.index, TONE]
    models = {1: 0, 4: 9}                                   # CSAW, TRIPLE SAW : sans le générateur aléatoire
    setup = {t: dict(BASE_KW, machine=m, shape=models.get(t, 64), decay=40) for t, m in enumerate(mach)}
    x, unm = multi(fw, setup, 300, trigs)
    r, unm_r = multi(ref_fw, {t: dict(kw, machine=0 if t in models else kw["machine"])     # ses pistes : ignorées
                              for t, kw in setup.items()}, 300, trigs)
    ok = not unm and not unm_r
    for t in range(6):
        if t in models:
            y, _, unm_s = play(fw, fw.index, dict(BASE_KW, shape=models[t], decay=40), 300, (1, 150), track=t)
            ok &= np.array_equal(x[:, t], y) and y.any() and not unm_s
        else:
            ok &= np.array_equal(x[:, t], r[:, t])
    if sampler:
        ok &= not x[:, 2].any()
    check(ok, f"{label} : pistes {[m + 1 for m in mach]} ensemble ; machines d'origine"
              f"{', Sampler sans échantillon (muet)' if sampler else ''} identiques sans MACRO, chaque piste MACRO "
              "identique à la même piste jouée seule")


def halfband():
    n, c = 4 * len(HB) - 1, 2 * len(HB) - 1
    h = np.zeros(n)
    h[c] = 0.5
    for k, v in enumerate(HB):
        h[c - 2 * k - 1] = h[c + 2 * k + 1] = v / 32768
    f = np.linspace(0, 48000, 9601)
    H = np.abs(np.exp(-2j * np.pi * np.outer(f / 96000, np.arange(n))) @ h)
    db = 20 * np.log10(np.maximum(H, 1e-12))
    ripple = np.abs(db[f <= 19000]).max()
    stop = db[f >= 29000].max()
    check(abs(H[0] - 1) < 1e-12 and ripple < 0.1 and stop < -45,
          f"filtre demi-bande ({n} coefficients) : gain 1 en continu, {ripple:.2f} dB au plus de 0 à 19 kHz, {stop:.1f} dB au plus "
          "au-delà de 29 kHz (ce qui se replierait sous 19 kHz)")


# --- 4. coût ---------------------------------------------------------------------------------------------------
def cost(fw, label, quick):
    """Instructions par bloc d'une voix (boucle des voix entière, moins la même boucle sans voix), pile."""
    def run(idx, kw, blocks, trigs=(1,), changes=None):
        e = fw.engine(solo=0)
        e.set(0, machine=idx, **kw)
        if idx == OFF:                   # la boucle des voix seule : aucune piste calculée
            e.uc.mem_write(E.VOICE0, struct.pack(">II", OFF, OFF))
        n = {"i": 0, "sp": 1 << 32}

        def hk(uc, a, s, u):
            n["i"] += 1
            if fw.pay <= a < fw.code_end:
                n["sp"] = min(n["sp"], uc.reg_read(mk.UC_M68K_REG_A7))
        e.uc.hook_add(UC_HOOK_CODE, hk)
        per = []
        for b in range(blocks):
            for k, v in (changes or {}).get(b, {}).items():
                e.set(0, **{k: v})
            i0 = n["i"]
            e.block(1 if b in trigs else 0)
            per.append(n["i"] - i0)
        return np.array(per), n["sp"]
    base, _ = run(OFF, BASE_KW, 4, trigs=())
    zero = int(np.median(base))
    tone, _ = run(TONE, dict(BASE_KW, color=40, shape=38, sweep=52, contour=42, decay=42), 24)
    rows, worst, deep = [], (0, ""), 0
    for m in (range(len(NAMES)) if not quick else (0, 23, 37)):
        per, sp = run(fw.index, dict(BASE_KW, shape=m, decay=100), 25)
        per = per - zero
        typ, mx = int(round(per[4:25].mean())), int(per[4:25].max())     # 7 cycles de 3, 3 puis 2 rendus de 24
        rows.append((NAMES[m], int(per[2]), typ, mx))
        worst = max(worst, (mx, NAMES[m]))
        deep = max(deep, E.STACK - 0x100 - sp)
    idle, _ = run(fw.index, dict(BASE_KW, decay=0), 200, trigs=(1,))
    idle = int(np.median(idle[150:])) - zero
    sw, _ = run(fw.index, dict(BASE_KW, shape=25, decay=127), 24, changes={12: {"shape": 29}})
    typ_all = sorted(r[2] for r in rows)
    print(f"        boucle des voix sans voix : {zero} instructions par bloc ; TONE : {int(np.median(tone[4:])) - zero}")
    for k in range(0, len(rows), 3):
        print("        " + " | ".join(f"{n:<20} {f:6} {t:6} {x:6}" for n, f, t, x in rows[k:k + 3]))
    print("        (par modèle : 1er bloc avec l'initialisation, moyenne, maximum ; instructions par bloc de 32 trames)")
    check(True, f"{label} : coût moyen d'une voix MACRO {typ_all[0]} à {typ_all[-1]} instructions par bloc (médiane "
                f"{typ_all[len(typ_all) // 2]}, pire {worst[0]} : {worst[1]}) ; TONE {int(np.median(tone[4:])) - zero} ; "
                f"voix muette {idle} ; changement de modèle (FM -> BOWED, lignes à retard effacées) {int(sw[12]) - zero} ; "
                f"pile {deep} o sous la boucle des voix")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--eurorack", required=True, help="clone de pichenettes/eurorack (tools/gen_macro.py)")
    ap.add_argument("--quick", action="store_true", help="quelques modèles seulement")
    ap.add_argument("--with", dest="others", default="", help="ids d'autres tweaks : MACRO avec eux (section 5)")
    args = ap.parse_args()
    repo = pathlib.Path(args.eurorack).resolve()
    gm.check_sources(repo)
    stock = T.main_os_from_syx(args.cycles)
    macro, tg_tw, macro_tg = load("25-macro.json"), load("30-model-tg-st.json"), load("32-macro-tg.json")
    off = Fw(stock, [])
    alone = Fw(stock, [macro])
    with tempfile.TemporaryDirectory() as d:
        ref = Ref(pathlib.Path(d), repo)
        todo = cases(args.quick)

        print(f"== {macro['id']} : MACRO en machine {alone.index + 1}")
        print("démarrage")
        t7.X.bootstrap_depack_ok(args.cycles, macro, None) or t7.FAIL.append("bootstrap")
        boot(alone)
        print("interface")
        interface_alone(stock, alone)
        print("son")
        halfband()
        exact(alone, ref, todo, "MACRO seule")
        amp_like_tone(alone)
        stock_unchanged(off, alone, "l'OS d'origine")
        locks(alone, "MACRO seule")
        six_tracks(alone, "MACRO seule")
        mixed(alone, off, "MACRO seule")
        print("coût")
        cost(alone, "MACRO seule", args.quick)

        gs.set_base(gs.PAY_TG)
        gs.CATALOG["macro"] = gm.MACHINE
        fw, ref_tg = Fw(stock, [tg_tw, macro_tg]), Fw(stock, [tg_tw])
        tg = {k: int(v, 16) for k, v in tg_tw["symbols"].items()}
        tg["knob_vec"] = tms.knob_vec_at(macro_tg)
        print(f"\n== {macro_tg['id']} : avec Model-TG, MACRO en machine {fw.index + 1}")
        print("démarrage")
        t7.X.bootstrap_depack_ok(args.cycles, [tg_tw, macro_tg], None) or t7.FAIL.append("bootstrap avec Model-TG")
        boot(fw, tg)
        print("interface")
        tms.interface(ref_tg, fw, ["macro"], tg)
        print("son")
        # la passerelle est la même : avec Model-TG, chaque modèle, la voix qui se tait, le modèle qui change
        tg_todo = [c for c in todo if c[0][:2].strip().isdigit() or c[0].startswith(("DECAY 10", "modèle qui"))]
        exact(fw, ref, tg_todo if not args.quick else tg_todo[:1] + tg_todo[-3:], "MACRO avec Model-TG")
        stock_unchanged(ref_tg, fw, "Model-TG seul")
        like(alone, fw, "MACRO avec Model-TG = MACRO seule")
        locks(fw, "MACRO avec Model-TG")
        six_tracks(fw, "MACRO avec Model-TG")
        mixed(fw, ref_tg, "MACRO avec Model-TG", sampler=True)
        print("coût")
        cost(fw, "MACRO avec Model-TG", True)
        if args.others:
            with_others(stock, args.cycles, args.others.split(","), alone, fw, tg)
    fail = t7.FAIL + tms.FAIL
    print("\nTOUT OK" if not fail else f"\n{len(fail)} ÉCHEC(S)")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
