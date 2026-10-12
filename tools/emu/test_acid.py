#!/usr/bin/env python3
"""Preuve de la machine ACID (notes/54) : une basse acide à la manière d'une TB-303 (le modèle d'Open303, MIT), en
machine ajoutée, seule (26-acid.json, 7e machine) et avec Model-TG (35-acid-tg.json par-dessus 30-model-tg-st.json,
8e machine). Le vrai code de l'OS, émulé (Unicorn), avec la charge utile telle que le crochet de démarrage la
reconstitue.

  1. Démarrage : le décompresseur du bootstrap relit l'OS agrandi ; le crochet (stub.S, PACK) remet à zéro la zone
     de la charge utile, y recopie ses morceaux, ne touche pas à la SRAM, puis reprend (comme test_macro.py).
  2. Interface : les vérifications de test_syntakt_machines.py (seul) et de test_model_tg_syntakt.py (avec
     Model-TG), appliquées à ACID.
  3. Son, la boucle des voix seule (mcengine) :
     - avant la chaîne d'ampli, la sortie d'ACID est EXACTEMENT celle du même cœur (acid_dsp.h) compilé pour
       l'ordinateur (acid_ref.c, l'EMAC reproduite), avec les réglages que la passerelle doit lui donner, calculés
       ici d'après notes/54 (Bridge : note, accord, potards, trig ou slide) : notes, potards aux bouts, scie et
       carré, DRIVE (saturation) de 0 au maximum, potards qui bougent, GATE, slide, trigless, voix qui se tait puis
       repart ;
     - une voix est calculée exactement quand l'OS l'impose (trig, ou enveloppe d'ampli au-dessus de 2^14) ;
     - la chaîne d'ampli (DECAY, GATE) lit dans la voix exactement ce qu'elle lit pour TONE ;
     - DRIVE : le son sature de plus en plus (facteur de crête qui baisse), à niveau presque constant ;
     - les machines d'origine ne changent pas (aucune instruction d'ACID sans piste ACID) ; machine locks ; 6 pistes
       ACID ; ACID mêlée aux machines d'origine (et au Sampler de Model-TG) ; ACID avec Model-TG = ACID seule.
  4. Son, avec le séquenceur de l'OS (seqrig.py : la vraie interruption audio, le vrai constructeur des pas) :
     - LEN égale à l'écart des trigs (1/16 sur des pas voisins, le défaut), plus courte, ou des pas espacés : chaque
       trig rejoue la note ; LEN qui dépasse le pas suivant (1.06, 1/8, INF) : la note glisse, l'OS ne voit pas le
       trig (pas de fondu, l'ampli continue) ; à 120, 300 et 546 BPM, trig à différents instants du bloc ;
     - jeu live : une touche jouée pendant qu'une autre est tenue glisse ;
     - trigless avec un verrou NOTE : glisse ; verrou MACHINE sur un trig lié : l'OS change bien de machine ;
     - la vélocité ne change que le gain de l'OS (pas d'accent) ; DRIVE verrouillé par pas (p-lock) ;
     - après un slide, le gain de vélocité de l'OS rejoint celui de la nouvelle note pas à pas (1/127 par bloc) ;
     - à chaque bloc, la sortie avant la chaîne d'ampli reste exactement la référence.
  5. Coût : instructions par bloc d'une voix ACID (scie, carré, slide), d'une voix muette, de TONE ; pile.
  6. Avec les autres mods (--with) : démarrage, machines d'origine identiques aux mêmes mods sans ACID, ACID
     identique à ACID seule (ou avec Model-TG seul), machine locks, pistes mêlées.

    python3 tools/emu/test_acid.py --cycles model-cycles_OS1.13.syx [--quick] \\
        [--with 6ch-usbup,model-tg-st,trig-hold,arp,tempo-max,boot-anim]

Durée : environ 25 min (10 min avec --quick), plus 5 min avec --with.
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
import gen_acid as ga               # noqa: E402
import gen_syntakt_engines as gs    # noqa: E402
import mcengine as E                # noqa: E402
import seqrig as S                  # noqa: E402
import test_model_tg as TM          # noqa: E402
import test_model_tg_syntakt as tms  # noqa: E402
import test_sdvintage as T          # noqa: E402
import test_sdvintage_7th as t7     # noqa: E402
import test_syntakt_machines as tsm  # noqa: E402

DEV = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13"
BASE = E.BASE
check = t7.check                    # échecs : t7.FAIL (et tms.FAIL pour l'interface avec Model-TG)

# la passerelle (tools/machines/acid/acid.c)
MARK = 0x41434431
IDLE_LEVEL = 1 << 14
TRIG, SLIDE = 1, 2
# chaîne d'ampli de l'OS, appelée par la passerelle comme par TONE : fonctions sans appel (début, fin)
AMP = ((0x400a9252, 0x400a9302), (0x400a9430, 0x400a9498), (0x400a967a, 0x400a9756))
TONE = 4
OFF = 9                             # machine hors limites : la voix n'est pas calculée
T120 = 120 * 120                    # 0x40149310 à 120 BPM
KW = dict(note=48, pitch=64, color=40, shape=90, sweep=80, contour=0, punch=0, gate=0, finetune=64, decay=50)


def load(name):
    return json.loads((DEV / name).read_text(encoding="utf-8"))


def knob(x):
    x = min(max(x, 0), 0x7f00)
    return x + (x >> 7)


class Fw:
    """Un firmware : MAIN OS (avec ce qui est ajouté après), et la charge utile d'ACID telle qu'en mémoire."""

    def __init__(self, stock, tweaks):
        p, _ = build.apply_writes(stock, tweaks)
        pl, _ = build.build_payload(tweaks, stock, None)
        self.img, self.tweaks = bytes(p) + pl, tweaks
        tg = [t for t in tweaks if t["id"].startswith("model-tg")]
        self.blob_end = BASE + len(stock) + tg[0]["append"]["size"] if tg else None
        self.keep = [(TM.BLOB, self.blob_end)] if tg else []
        ours = [t for t in tweaks if t["id"] in ("acid", "acid-tg")]
        self.payload = self.mine = None
        if not ours:
            return
        self.mine = ours[0]
        ap_ = self.mine["append"]
        self.pay = int(ap_["dest"], 16)
        self.runtime = build.payload_runtime(self.mine, stock, None)
        self.payload = (self.pay, self.runtime)
        self.code_end = self.pay + len(ap_["parts"][0]["hex"]) // 2          # code et tables d'ACID
        self.nm = gs.TG_FIRST + 1 if tg else 7
        self.index = self.nm - 1                                            # ACID
        data = self.pay + gs.LAYOUT["DATA"]
        u32 = lambda va: struct.unpack_from(">I", self.runtime, va - self.pay)[0]
        self.upd = u32(data + 4 * self.nm + 4 * self.index)
        self.rnd = u32(data + 8 * self.nm + 4 * self.index)
        check(self.upd == int(self.mine["symbols"]["acid_update"], 16)
              and self.rnd == int(self.mine["symbols"]["acid_render"], 16),
              f"{self.mine['id']} : la table des machines appelle acid_update et acid_render (machine {self.nm})")

    def engine(self, solo=None):
        """La boucle des voix seule ; ce que la passerelle lit hors de la voix : vélocité 100, gain de vélocité 100,
        120 BPM, reste de longueur d'un bloc (ni slide, ni fin de note)."""
        if self.blob_end:
            e = TM.engine(self.img, end=self.blob_end, payload=self.payload)
        else:
            e = E.Engine(self.img, payload=self.payload)
        S.ensure_map(e.uc, 0x40800000, 0x01800000)
        e.uc.mem_write(S.TEMPO, struct.pack(">i", T120))
        for t in range(6):
            set_globals(e, t, vel=100, gain=100, left=T120)
        if solo is not None:             # les autres pistes : machine hors limites, rien n'est calculé
            for t in range(6):
                if t != solo:
                    e.uc.mem_write(E.VOICE0 + t * E.VSTRIDE, struct.pack(">II", OFF, OFF))
        return e


def set_globals(e, t, vel=None, gain=None, left=None):
    if vel is not None:
        e.uc.mem_write(S.VEL + 2 * t, struct.pack(">h", vel << 8))
    if gain is not None:
        e.uc.mem_write(S.GAIN + 2 * t, struct.pack(">h", gain))
        e.uc.mem_write(S.GAIN_NEXT + 2 * t, struct.pack(">h", gain))
    if left is not None:
        e.uc.mem_write(S.LEN_LEFT + 4 * t, struct.pack(">i", left))


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
    packed = sum(n for _, n in fw.mine["append"]["pack"])
    check(got == rt, f"charge utile reconstituée à {dst:#x} : {len(rt)} o (code et tables d'ACID, détours, données, "
                     f"puis ses variables à zéro), rangée en {packed} o dans l'image")
    check(bytes(uc.mem_read(0x80000000, 0x10000)) == bytes(sram), "SRAM intacte")
    end = BASE + len(fw.img)
    check(end <= gs.END_LIMIT, f"image décompressée jusqu'à {end:#x} (limite {gs.END_LIMIT:#x})")


# --- 2. interface ----------------------------------------------------------------------------------------------
def interface_alone(stock, fw):
    """Les vérifications de test_syntakt_machines.py, pour une machine ajoutée : ACID."""
    tsm.SAFE = True
    tsm.ADDED = [dict(ga.MACHINE, code="acid", index=6, label="ACID")]
    tsm.N, tsm.NM, tsm.TOP = 1, 7, 6
    tsm.FIRST, tsm.REC = {6: 76}, {6: gs.RECS}
    tsm.ROWS, tsm.CCROWS = gs.ROWSN, gs.CCROWSN
    tsm.NAMES = ["Kick", "Snare", "Metal", "Perc", "Tone", "Chord", ga.MACHINE["name"]]
    patched, payload = fw.img, fw.runtime
    a, b = tsm.tables(stock, patched, payload)
    tsm.lookups(a, b)
    tsm.accessors(a, b, stock, patched)
    tsm.screens(stock, patched, payload)
    tsm.setter_and_wheel(stock, patched, payload)
    tsm.records_and_change(stock, patched, payload)
    tsm.out_of_range(stock, patched, payload)
    tsm.small_icon(stock, patched, payload)


# --- 3. son : la référence et la passerelle attendue ---------------------------------------------------------------
class Ref:
    """Le cœur d'ACID (acid_dsp.h) compilé pour l'ordinateur (acid_ref.c)."""

    def __init__(self, tmp):
        tables = ga.SRC / "acid_tables.h"
        check(tables.read_text(encoding="utf-8") == ga.tables_header(),
              "acid_tables.h : les tables du générateur (tools/gen_acid.py)")
        self.exe = tmp / "acid_ref"
        subprocess.run(["gcc", "-O2", "-Wall", "-Werror", "-I", str(ga.SRC), str(HERE / "acid_ref.c"), "-o",
                        str(self.exe)], check=True)

    def run(self, lines):
        out = subprocess.run([str(self.exe)], input="".join(lines).encode(), capture_output=True, check=True).stdout
        return np.frombuffer(out, dtype=">i4").reshape(-1, 32).astype(np.int64)


class Bridge:
    """Ce que la passerelle doit faire (notes/54 §3), d'après la voix, les paramètres et les globales de l'OS lus à
    l'entrée de acid_update et de acid_render : les réglages du cœur, et ses écritures dans l'OS."""

    def __init__(self):
        self.st = [dict(idle=0, held=0, left=0, mach=0, gain=0, ramp=0, note=0, trig=0) for _ in range(6)]

    def update(self, t, pmod, vb, pb, g):
        s = self.st[t]
        v32 = lambda o: struct.unpack_from(">i", vb, o)[0]
        p16 = lambda o: struct.unpack_from(">h", pb, o)[0]
        s8 = lambda o: struct.unpack_from(">b", pb, o)[0]
        init = v32(0x2c) != MARK
        if init:                         # 1re note sur la machine : celle du trig qui l'a choisie
            s.update(idle=1, held=int(v32(0x38) != 0), ramp=0, mach=s8(0x12))
        left, s["left"] = s["left"], g["left"]
        t34, slide, gain_next = v32(0x34), 0, g["gain_next"]
        if t34:
            slide = int(bool(s["held"] and not s["idle"] and (left == 0 or left > 2 * g["T"])
                             and s8(0x12) == s["mach"]))
            s.update(held=1, ramp=0)
            if slide:
                t34 = 0
                s.update(gain=g["gain_next"], ramp=1)
                gain_next = g["gain"]
        elif s["ramp"]:
            x = g["gain"] + (1 if g["gain"] < s["gain"] else -1 if g["gain"] > s["gain"] else 0)
            gain_next = x
            s["ramp"] = int(x != s["gain"])
        if v32(0x3c):
            s["held"] = 0
        if not t34:
            s["note"] = min(max(pmod, 0), 127 << 16)
        s["trig"] = SLIDE if slide else TRIG if v32(0x38) else 0
        return dict(note=s["note"], tune=(p16(0x14) << 8) + ((p16(0x22) - 0x4000) << 3) - (64 << 16),
                    cut=knob(p16(0x16)), res=knob(p16(0x18)), envmod=knob(p16(0x1a)), decay=knob(p16(0x24)),
                    drive=knob(p16(0x1c)), wave=int(p16(0x1e) != 0), trig=s["trig"], init=init,
                    v34=0 if slide else v32(0x34), gain_next=gain_next)

    def render(self, t, vb, rec):
        s = self.st[t]
        v32 = lambda o: struct.unpack_from(">i", vb, o)[0]
        quiet = abs(v32(0x230)) < IDLE_LEVEL and abs(v32(0x234)) < IDLE_LEVEL
        if not v32(0x34) and not v32(0x38) and s["trig"] != SLIDE and quiet:
            s["idle"] = 1
            rec.update(render=0, reset=0)
            return
        rec.update(render=1, reset=int(bool(s["idle"] and s["trig"] == TRIG)))
        if rec["reset"]:
            s["idle"] = 0

    @staticmethod
    def line(t, r):
        return (f"{t} {r['note']} {r['tune']} {r['cut']} {r['res']} {r['envmod']} {r['decay']} {r['drive']} "
                f"{r['wave']} {r['trig']} {r['reset']}\n")


class Probe:
    """Ce que reçoit la passerelle à chaque bloc (entrées de acid_update et acid_render), ce qu'elle écrit dans la
    voix et le gain de vélocité, et ce qu'elle sort avant la chaîne d'ampli (entrée de AMP_ENV appelée depuis la
    charge utile) ; les lectures de la voix par la chaîne d'ampli (reads)."""

    def __init__(self, fw, e, tracks=(0,), reads=False):
        self.spec, self.tracks, self.block = Bridge(), tuple(tracks), 0
        self.recs = {t: [] for t in self.tracks}
        self.outs = {t: [] for t in self.tracks}
        self.out_at, self.reads = {}, [] if reads else None
        uc = e.uc
        arg = lambda k: struct.unpack(">I", uc.mem_read(uc.reg_read(mk.UC_M68K_REG_A7) + 4 * k, 4))[0]
        r16 = lambda a: struct.unpack(">h", uc.mem_read(a, 2))[0]
        r32 = lambda a: struct.unpack(">i", uc.mem_read(a, 4))[0]
        track = lambda v: (v - E.VOICE0) // E.VSTRIDE if (v - E.VOICE0) % E.VSTRIDE == 0 else -1

        def upd(uc_, a, s, u):
            t = track(arg(2))
            if t not in self.tracks:
                return
            g = dict(vel=r16(S.VEL + 2 * t), gain=r16(S.GAIN + 2 * t), gain_next=r16(S.GAIN_NEXT + 2 * t),
                     left=r32(S.LEN_LEFT + 4 * t), T=r32(S.TEMPO))
            v = arg(2)
            r = self.spec.update(t, struct.unpack(">i", struct.pack(">I", arg(1)))[0], bytes(uc.mem_read(v, E.VSTRIDE)),
                                 bytes(uc.mem_read(arg(3), 0x40)), g)
            r["block"], r["vel"] = self.block, g["vel"] >> 8
            self.recs[t].append(r)

        def rnd(uc_, a, s, u):
            t = track(arg(2))
            if t not in self.tracks:
                return
            self.out_at[t] = arg(1)
            r = self.recs[t][-1]
            vb = bytes(uc.mem_read(arg(2), E.VSTRIDE))
            r["v34_got"] = struct.unpack_from(">i", vb, 0x34)[0]
            r["gain_next_got"] = r16(S.GAIN_NEXT + 2 * t)
            self.spec.render(t, vb, r)

        def amp(uc_, a, s, u):
            t = track(arg(1))
            if fw.pay <= arg(0) < fw.code_end and t in self.tracks:
                self.recs[t][-1]["done"] = 1
                self.outs[t].append(np.frombuffer(bytes(uc.mem_read(self.out_at[t], 128)), ">i4").astype(np.int64))
        uc.hook_add(UC_HOOK_CODE, upd, begin=fw.upd, end=fw.upd)
        uc.hook_add(UC_HOOK_CODE, rnd, begin=fw.rnd, end=fw.rnd)
        uc.hook_add(UC_HOOK_CODE, amp, begin=AMP[0][0], end=AMP[0][0])
        if reads:
            v0 = E.VOICE0 + self.tracks[0] * E.VSTRIDE
            uc.hook_add(UC_HOOK_MEM_READ, self._read, begin=v0, end=v0 + E.VSTRIDE - 1, user_data=v0)

    def _read(self, uc, access, addr, size, value, v0):
        pc = uc.reg_read(mk.UC_M68K_REG_PC)
        if any(lo <= pc < hi for lo, hi in AMP):
            self.reads.append((self.block, addr - v0, bytes(uc.mem_read(addr, size))))

    def kinds(self, t=0):
        return "".join("T" if r["trig"] == TRIG else "S" for r in self.recs[t] if r["trig"])

    def verify(self, ref):
        """[] si tout est conforme ; sinon ce qui ne l'est pas. Rend aussi la crête avant la chaîne d'ampli."""
        bad, peak = [], 0
        for t in self.tracks:
            recs = self.recs[t]
            for r in recs:
                if r.get("done", 0) != r.get("render"):
                    bad.append(f"piste {t + 1} bloc {r['block']} : calculée {r.get('done', 0)}, attendu "
                               f"{r.get('render')}")
                    break
                if r.get("v34_got") != r["v34"] or r.get("gain_next_got") != r["gain_next"]:
                    bad.append(f"piste {t + 1} bloc {r['block']} : v+0x34 {r.get('v34_got')} (attendu {r['v34']}), "
                               f"gain suivant {r.get('gain_next_got')} (attendu {r['gain_next']})")
                    break
            lines = [Bridge.line(t, r) for r in recs if r.get("render")]
            want = ref.run(lines) if lines else np.zeros((0, 32), np.int64)
            got = np.array(self.outs[t], np.int64).reshape(-1, 32)
            if len(want) != len(got) or not np.array_equal(want, got):
                first = next((i for i in range(min(len(want), len(got))) if not np.array_equal(want[i], got[i])),
                             None)
                bad.append(f"piste {t + 1} : {len(got)} blocs rendus / {len(want)} attendus, 1er bloc différent "
                           f"{first}")
            if len(got):
                peak = max(peak, int(np.abs(got).max()))
        return bad, peak


# --- 3. son : la boucle des voix seule ------------------------------------------------------------------------------
def play(fw, kw, blocks, trigs=(1,), changes=None, track=0, vels=None, rels=(), left=None, reads=False, idx=None):
    """Une piste sur ACID (ou idx), les autres éteintes. changes : {bloc : réglages} ; vels : {bloc : vélocité
    écrite avant le bloc} ; rels : blocs avec une fin de note ; left : reste de longueur écrit à chaque bloc."""
    e = fw.engine(solo=track)
    e.set(track, machine=fw.index if idx is None else idx, **kw)
    pr = Probe(fw, e, (track,), reads) if fw.payload else None
    out = []
    for b in range(blocks):
        for k, v in (changes or {}).get(b, {}).items():
            e.set(track, **{k: v})
        if b in (vels or {}):
            set_globals(e, track, vel=vels[b])
        if left is not None:
            set_globals(e, track, left=left)
        if pr:
            pr.block = b
        out.append(e.block(1 << track if b in trigs else 0, 1 << track if b in rels else 0)[track])
    return np.stack(out), pr, e.unmapped


def cases(quick):
    """(nom, réglages, extra pour play, trigs attendus)."""
    out = []
    for n in ((24, 36, 48, 60, 72, 96) if not quick else (36, 60)):
        out.append((f"note {n}", dict(KW, note=n), dict(trigs=(1, 90), blocks=150), "TT"))
    out += [
        ("note 30, FINE 0", dict(KW, note=30, finetune=0), dict(blocks=60), "T"),
        ("note 90, FINE 127", dict(KW, note=90, finetune=127), dict(blocks=60), "T"),
        ("PITCH 0, note 0 : borné en bas", dict(KW, pitch=0, note=0), dict(blocks=40), "T"),
        ("PITCH 127, note 127 : borné en haut", dict(KW, pitch=127, note=127), dict(blocks=40), "T"),
        ("carré (PUNCH)", dict(KW, punch=1), dict(trigs=(1, 90), blocks=150), "TT"),
        ("carré, note 24", dict(KW, punch=1, note=24), dict(blocks=80), "T"),
        ("CUTOFF 0, RESO 127", dict(KW, color=0, shape=127), dict(blocks=80), "T"),
        ("CUTOFF 127, RESO 127", dict(KW, color=127, shape=127), dict(blocks=80), "T"),
        ("CUTOFF 0, RESO 0, ENV MOD 127", dict(KW, color=0, shape=0, sweep=127), dict(blocks=80), "T"),
        ("ENV MOD 0", dict(KW, sweep=0), dict(blocks=80), "T"),
        ("DECAY 0", dict(KW, decay=0), dict(blocks=60), "T"),
        ("DECAY 127, GATE, fin de note", dict(KW, decay=127, gate=1), dict(blocks=200, rels=(120,)), "T"),
        ("DRIVE 20", dict(KW, contour=20), dict(blocks=80), "T"),
        ("DRIVE 50", dict(KW, contour=50), dict(blocks=80), "T"),
        ("DRIVE 90", dict(KW, contour=90), dict(blocks=80), "T"),
        ("DRIVE 127", dict(KW, contour=127), dict(blocks=100), "T"),
        ("DRIVE 127, VEL 127 puis 64 : pas d'accent", dict(KW, contour=127),
         dict(trigs=(1, 60), blocks=120, vels={1: 127, 60: 64}), "TT"),
        ("carré, DRIVE 64", dict(KW, punch=1, contour=64), dict(blocks=80), "T"),
        ("tout au maximum, DRIVE 127", dict(KW, color=127, shape=127, sweep=127, contour=127, decay=127),
         dict(blocks=120), "T"),
        ("carré, tout au maximum, note 24", dict(KW, punch=1, note=24, color=127, shape=110, sweep=127,
                                                 contour=127), dict(blocks=120), "T"),
        ("CUTOFF 0, RESO 0, ENV MOD 0, DRIVE 127", dict(KW, color=0, shape=0, sweep=0, contour=127),
         dict(blocks=80), "T"),
        ("potards qui bougent à chaque bloc", dict(KW, decay=100),
         dict(blocks=100, changes={b: dict(color=(3 * b) % 128, shape=127 - (5 * b) % 128, sweep=(7 * b) % 128,
                                           contour=(11 * b) % 128, decay=100 - b % 50) for b in range(100)}), "T"),
        ("voix qui se tait puis repart", dict(KW, decay=10), dict(trigs=(1, 200), blocks=260), "TT"),
        ("note tenue (sans fin), trig suivant : glisse, DRIVE 60", dict(KW, decay=110, contour=60),
         dict(trigs=(1, 60, 120), blocks=200, left=0, vels={60: 127, 120: 100},
              changes={60: dict(note=60), 120: dict(note=43)}), "TSS"),
        ("note relâchée puis trig : rejouée", dict(KW, decay=110),
         dict(trigs=(1, 60), blocks=120, left=0, rels=(40,), changes={60: dict(note=55)}), "TT"),
        ("trig et fin dans le même bloc (lié), puis trig : rejouée", dict(KW, decay=110),
         dict(trigs=(1, 30, 60), rels=(30,), blocks=100, left=0, changes={30: dict(note=55), 60: dict(note=50)}),
         "TST"),
        ("trigless : la note change sans trig, glisse", dict(KW, decay=110),
         dict(blocks=120, changes={40: dict(note=55), 80: dict(note=36)}), "T"),
    ]
    return out


def exact(fw, ref, todo, label):
    """Avant la chaîne d'ampli : identique au cœur compilé pour l'ordinateur ; voix muette non calculée ; trigs et
    slides comme prévu."""
    bad, idle_seen, peaks, blocks_seen = [], 0, [], 0
    for name, kw, ex, kinds in todo:
        ex = dict(ex)
        out, pr, unm = play(fw, kw, ex.pop("blocks"), **ex)
        why, peak = pr.verify(ref)
        recs = pr.recs[0]
        idle = [r["block"] for r in recs if not r["render"]]
        idle_seen += len(idle)
        blocks_seen += len(recs)
        silent = not out[idle].any() if idle else True
        inits = sum(r["init"] for r in recs)
        peaks.append(peak)
        if why or not silent or unm or inits != 1 or pr.kinds() != kinds or peak < 1 << 22:
            bad.append(name)
            print(f"        ECART {name} : {why[:2]}, trigs {pr.kinds()} (attendu {kinds}), crête {peak:.3g}, "
                  f"init {inits}, muets non nuls {not silent}, hors mémoire {unm[:2]}")
    check(not bad, f"{label} : avant la chaîne d'ampli, identique échantillon par échantillon au cœur compilé pour "
                   f"l'ordinateur, réglages, trigs et slides comme notes/54 ({len(todo)} cas, crêtes "
                   f"{min(peaks) / 2 ** 31:.2f} à {max(peaks) / 2 ** 31:.2f} de la pleine échelle) {bad[:5]}")
    check(idle_seen > 0 and not bad, f"{label} : voix calculée exactement quand l'OS l'impose (trig, slide, ou "
                                     f"enveloppe d'ampli au-dessus de 2^14), sur {blocks_seen} blocs ; {idle_seen} "
                                     "blocs de voix muette, sortie nulle")


def amp_like_tone(fw):
    """La chaîne d'ampli (enveloppe, VCA, PUNCH) lit dans la voix ACID exactement ce qu'elle lit dans une voix TONE,
    bloc par bloc, tant que la voix ACID est calculée (PUNCH : ACID la règle éteinte, il choisit la forme d'onde)."""
    res = []
    for kw in (dict(decay=30), dict(decay=90), dict(decay=60, gate=1), dict(decay=127, gate=1)):
        k = dict(KW, **kw)
        rels = (60,) if kw.get("gate") else ()
        _, pt, _ = play(fw, k, 120, (1, 40), rels=rels, reads=True, idx=TONE)
        _, pm, unm = play(fw, k, 120, (1, 40), rels=rels, reads=True)
        stop = next((r["block"] for r in pm.recs[0] if not r["render"]), 120)
        rt = [x for x in pt.reads if x[0] < stop]
        rm = [x for x in pm.reads if x[0] < stop]
        res.append((rt == rm and len(rm) > 0 and not unm, stop, len({o for _, o, _ in rm})))
    check(all(ok for ok, _, _ in res),
          f"chaîne d'ampli : mêmes lectures de la voix que TONE (DECAY, GATE ; {res[0][2]} champs), bloc par bloc "
          f"jusqu'au silence (blocs {[s for _, s, _ in res]})")


def drive_curve(fw):
    """DRIVE, en sortie finale de la piste (après la chaîne d'ampli de l'OS), une note de 150 blocs (100 ms) :
    le facteur de crête baisse à chaque cran (le son sature de plus en plus), le niveau efficace reste à
    quelques dB de celui de DRIVE 0 (notes/54 §3.2)."""
    rows, ok = [], True
    for name, kw in (("scie", dict(KW, decay=60)), ("carré", dict(KW, punch=1, decay=60)),
                     ("ouvert", dict(KW, color=110, shape=20, sweep=30, decay=60, note=60))):
        lv, cf = [], []
        for d in (0, 16, 32, 48, 64, 96, 127):
            x, _, unm = play(fw, dict(kw, contour=d), 152, (1,))
            y = x[2:152].astype(float).ravel()
            r = np.sqrt(np.mean(y ** 2))
            lv.append(20 * np.log10(r))
            cf.append(20 * np.log10(np.abs(y).max() / r))
            ok &= not unm
        rel = [v - lv[0] for v in lv]
        ok &= all(b < a for a, b in zip(cf, cf[1:])) and all(-4 < v < 4 for v in rel)
        rows.append(f"{name} : crête/efficace {cf[0]:.1f} -> {cf[-1]:.1f} dB, niveau {min(rel):+.1f}..{max(rel):+.1f} dB")
    check(ok, f"DRIVE 0, 16, 32, 48, 64, 96, 127 : le son sature de plus en plus, niveau presque constant ; "
              + " ; ".join(rows))


def stock_unchanged(ref_fw, fw, label):
    """6 pistes sur les machines d'origine (2 trigs) : identiques, et rien du code d'ACID ne tourne."""
    def run(f, hook):
        e = f.engine()
        for t in range(6):
            e.set(t, **dict(KW, machine=t, color=64, shape=64, contour=64, decay=60))
        ran = []
        if hook:
            e.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: ran.append(a), begin=f.pay, end=f.code_end - 1)
        x = np.stack([e.block(0x3f if b in (1, 150) else 0) for b in range(300)])
        return x, ran, e.unmapped
    r, _, _ = run(ref_fw, False)
    x, ran, unm = run(fw, True)
    check(np.array_equal(r, x) and np.abs(x).max() > 1e7 and not ran and not unm,
          f"6 machines d'origine : identiques à {label}, échantillon par échantillon, sans une instruction d'ACID")


def like(alone, fw, label):
    """Sortie finale de la piste ACID identique dans deux firmwares."""
    bad = []
    for kw in (KW, dict(KW, punch=1, note=36), dict(KW, color=110, shape=127, decay=100, gate=1, contour=100)):
        a, _, _ = play(alone, kw, 200, (1, 120), vels={120: 127})
        b, _, unm = play(fw, kw, 200, (1, 120), vels={120: 127})
        if not np.array_equal(a, b) or unm or not a.any():
            bad.append(kw)
    check(not bad, f"{label}, sortie finale de la piste (scie, carré, GATE, DRIVE) {bad[:1]}")


def locks(fw, label):
    """Machine locks sur une piste : SNARE, ACID, TONE, ACID (carré), KICK : tout joue."""
    seq = [(1, dict(machine=1)), (fw.index, dict(machine=fw.index)), (TONE, dict(machine=TONE)),
           (fw.index, dict(machine=fw.index, punch=1)), (0, dict(machine=0))]
    e = fw.engine(solo=0)
    e.set(0, **dict(KW, machine=1, decay=40))
    out = []
    for b in range(60 * len(seq)):
        if b % 60 == 0:
            e.set(0, **seq[b // 60][1])
        out.append(e.block(1 if b % 60 == 1 else 0)[0])
    x = np.stack(out)
    parts = [int(np.abs(x[60 * k + 2:60 * k + 60]).max()) for k in range(len(seq))]
    marks = struct.unpack(">I", e.uc.mem_read(E.VOICE0 + 0x2c, 4))[0]
    check(all(p > 1e6 for p in parts) and not e.unmapped and marks != MARK,
          f"{label} : machine locks SNARE -> ACID -> TONE -> ACID (carré) -> KICK sur une piste : tout joue "
          f"(crêtes {[f'{p:.2g}' for p in parts]})")


def six_tracks(fw, label):
    """6 pistes ACID, réglages différents : chacune identique à la même piste jouée seule."""
    kws = [dict(KW, note=36 + 5 * t, punch=t % 2, color=20 * t, shape=127 - 15 * t) for t in range(6)]
    e = fw.engine()
    for t, kw in enumerate(kws):
        e.set(t, **dict(kw, machine=fw.index))
    x = np.stack([e.block(0x3f if b in (1, 100) else 0) for b in range(160)])
    ok = not e.unmapped
    for t, kw in enumerate(kws):
        y, _, unm = play(fw, kw, 160, (1, 100), track=t)
        ok &= np.array_equal(x[:, t], y) and not unm and y.any()
    check(ok, f"{label} : 6 pistes ACID ensemble, chacune identique à la même piste jouée seule")


def multi(fw, setup, blocks, trigs):
    e = fw.engine()
    for t, kw in setup.items():
        e.set(t, **kw)
    return np.stack([e.block(trigs.get(b, 0)) for b in range(blocks)]), e.unmapped


def mixed(fw, ref_fw, label, sampler=False):
    """ACID mêlée aux autres machines : les pistes d'origine (et le Sampler de Model-TG) identiques au même firmware
    sans ACID, chaque piste ACID identique à la même piste jouée seule."""
    trigs = {1: 0x3f, 150: 0x3f}
    mach = [0, fw.index, 6 if sampler else 2, 5, fw.index, TONE]
    ours = {1: dict(KW, decay=40), 4: dict(KW, note=36, punch=1, decay=40)}
    setup = {t: dict(ours.get(t, dict(KW, color=64, shape=64, decay=40)), machine=m) for t, m in enumerate(mach)}
    x, unm = multi(fw, setup, 300, trigs)
    r, unm_r = multi(ref_fw, {t: dict(kw, machine=0 if t in ours else kw["machine"]) for t, kw in setup.items()},
                     300, trigs)
    ok = not unm and not unm_r
    for t in range(6):
        if t in ours:
            y, _, unm_s = play(fw, ours[t], 300, (1, 150), track=t)
            ok &= np.array_equal(x[:, t], y) and y.any() and not unm_s
        else:
            ok &= np.array_equal(x[:, t], r[:, t])
    if sampler:
        ok &= not x[:, 2].any()
    check(ok, f"{label} : pistes {[m + 1 for m in mach]} ensemble ; machines d'origine"
              f"{', Sampler sans échantillon (muet)' if sampler else ''} identiques sans ACID, chaque piste ACID "
              "identique à la même piste jouée seule")


# --- 4. son, avec le séquenceur de l'OS --------------------------------------------------------------------------
def sequence(fw, bpm, steps, frac=0.33, kw=None, live=None, tail=40, track=0):
    """La piste track sur ACID (réglages kw), jouée par le vrai séquenceur : steps = [(pas, réglages du pas)]
    (vel, length, note, word, locks {slot : valeur 8.8}), le pas 0 à frac bloc dans le bloc 2 ; live = {bloc :
    [(1 appui | 2 relâché, note, vel)]}. Rend (infos du banc par bloc, Probe, accès hors mémoire)."""
    e = fw.engine(solo=track)
    rig = S.Rig(e, bpm, keep=fw.keep)
    for k, v in dict(KW, machine=fw.index, **(kw or {})).items():
        if k in E.SLOT:
            rig.param(track, E.SLOT[k], int(round(v * 256)))
    pr = Probe(fw, e, (track,))
    t0 = rig.now + 2 * rig.blk + int(frac * rig.blk)
    last = -1
    for s, st in steps:
        st = dict(st)
        for slot, value in st.pop("locks", {}).items():
            rig.set_lock(track, s, slot, value)
        rig.set_step(track, s, **st)
        rig.schedule_step(track, s, t0 + s * S.STEP)
        last = max(last, s)
    n = int((last + 1) * S.STEP / rig.blk) + tail + 3
    if live:
        n = max(n, max(live) + tail)
    infos = []
    for b in range(n):
        pr.block = b
        for ev in (live or {}).get(b, ()):
            rig.live(ev[0], track, ev[1], *ev[2:])
        infos.append(rig.block())
    return infos, pr, e.unmapped


def seq_cases(quick):
    """(nom, tempo, pas, réglages, extra, trigs attendus)."""
    L = S
    out = []
    for bpm in ((120, 300, 546) if not quick else (300,)):
        for frac in ((0.05, 0.5, 0.95) if not quick else (0.5,)):
            out.append((f"{bpm} BPM, trig à {frac:.2f} bloc, LEN 1/16 sur des pas voisins : rejouées", bpm,
                        [(0, dict(note=48)), (1, dict(note=55)), (2, dict(note=50))], None, dict(frac=frac), "TTT"))
            out.append((f"{bpm} BPM, trig à {frac:.2f} bloc, LEN 1.06 : glissent", bpm,
                        [(0, dict(note=48, length=L.LEN_106)), (1, dict(note=55, length=L.LEN_106)),
                         (2, dict(note=50))], None, dict(frac=frac), "TSS"))
    out += [
        ("LEN .938 : rejouées", 300, [(s, dict(note=48 + 3 * s, length=L.LEN_938)) for s in range(3)], None, {},
         "TTT"),
        ("LEN INF : glissent, puis fin de note avec GATE", 300,
         [(0, dict(note=48, length=L.LEN_INF)), (1, dict(note=60, length=L.LEN_INF)), (2, dict(note=36))],
         dict(gate=1, decay=60), {}, "TSS"),
        ("LEN 1/8 sur le pas 0, trig au pas 1 : glisse ; LEN 1/16 sur les pas 4 et 6 : rejouées", 300,
         [(0, dict(note=48, length=L.LEN_1_8)), (1, dict(note=51)), (4, dict(note=53)), (6, dict(note=55))],
         dict(decay=90), {}, "TSTT"),
        ("LEN 1/8 sur les pas 0 et 2 (la LEN égale l'écart) : rejouée", 300,
         [(0, dict(note=48, length=L.LEN_1_8)), (2, dict(note=51, length=L.LEN_1_8)), (4, dict(note=53))],
         dict(decay=90), {}, "TTT"),
        ("GATE, LEN 1.06 : l'ampli tient à travers le slide", 300,
         [(0, dict(note=36, length=L.LEN_106)), (1, dict(note=48, vel=127))], dict(gate=1, decay=40), {}, "TS"),
        ("vélocité 127, 110, 100 (défaut), 64 : seul le gain de l'OS change", 300,
         [(0, dict(vel=127)), (1, dict(vel=110)), (2, dict()), (3, dict(vel=64))], dict(contour=70), {}, "TTTT"),
        ("DRIVE verrouillé par pas : 0, 40, 90, 127, puis le réglage de la piste", 300,
         [(s, dict(note=36, locks={E.SLOT["contour"]: v << 8})) for s, v in enumerate((0, 40, 90, 127))]
         + [(4, dict(note=36))], dict(contour=20), {}, "TTTTT"),
        ("slide vers une note plus forte : le gain de vélocité rejoint 127 pas à pas", 300,
         [(0, dict(note=36, length=L.LEN_106)), (1, dict(note=48, vel=127, length=L.LEN_106)), (2, dict(note=36))],
         dict(decay=110), {}, "TSS"),
        ("trigless avec un verrou NOTE : glisse", 300,
         [(0, dict(note=48, length=L.LEN_1_8)), (1, dict(note=55, word=0x6801))], dict(decay=110), {}, "T"),
        ("verrou MACHINE (TONE) sur un trig lié : l'OS change de machine, puis ACID revient", 300,
         [(0, dict(note=48, length=L.LEN_106)), (1, dict(note=55, locks={9: TONE << 8})), (2, dict(note=50))],
         None, {}, "TT"),
        ("jeu live : legato glisse, relâchements, appui et fin dans le même bloc", 120, [], dict(decay=110),
         dict(live={5: [(1, 48, 100)], 40: [(1, 51, 127)], 70: [(2, 48)], 100: [(2, 51)], 130: [(1, 55, 90)],
                    150: [(2, 55)], 160: [(1, 57, 100), (2, 57)], 190: [(1, 60, 100)], 200: [(1, 63, 100)]},
              tail=60), "TSTTTS"),
    ]
    return out


def sequencer(fw, ref, label, quick):
    """Le vrai séquenceur : trigs rejoués ou liés, vélocité, DRIVE verrouillé, gain de vélocité, verrous, jeu
    live."""
    bad, n = [], 0
    for name, bpm, steps, kw, ex, kinds in seq_cases(quick):
        infos, pr, unm = sequence(fw, bpm, steps, kw=kw, **ex)
        why, peak = pr.verify(ref)
        recs = pr.recs[0]
        n += len(infos)
        gains = [i["gain"][0] for i in infos]
        slides = [r["block"] for r in recs if r["trig"] == SLIDE]
        # un slide : la voix n'est pas fondue (sortie du bloc du slide pas plus faible que le quart du précédent)
        rms = lambda b: float(np.sqrt(np.mean(infos[b]["out"][0].astype(float) ** 2)))
        fade = [b for b in slides if rms(b) < 0.25 * rms(b - 1)]
        # après un slide, jusqu'au trig rejoué suivant : le gain de vélocité bouge de 1/127 par bloc au plus
        trig_blocks = [r["block"] for r in recs if r["trig"] == TRIG]
        steps_ok = True
        for b in slides:
            end = min([x for x in trig_blocks if x > b] + [len(gains)])
            steps_ok &= all(abs(y - x) <= 1 for x, y in zip(gains[b:end - 1], gains[b + 1:end]))
        extra = []
        if name.startswith("vélocité"):
            # le cœur reçoit les mêmes réglages aux 4 trigs ; l'OS, lui, prend la vélocité de chaque pas
            ins = {tuple(r[k] for k in ("cut", "res", "envmod", "decay", "drive")) for r in recs
                   if r["trig"] == TRIG}
            vel = [r["vel"] for r in recs if r["trig"] == TRIG]
            extra = [] if len(ins) == 1 and vel == [127, 110, 100, 64] else [f"réglages {ins}, vélocités {vel}"]
        if name.startswith("DRIVE"):
            drv = [r["drive"] for r in recs if r["trig"] == TRIG]
            want = [knob(v << 8) for v in (0, 40, 90, 127, 20)]
            extra = [] if drv == want else [f"DRIVE {drv} (attendu {want})"]
        if name.startswith("slide vers"):
            i = slides[0]
            extra = [] if gains[i] == 100 and gains[i + 28] == 127 and steps_ok else [f"gains {gains[i:i + 30]}"]
        if name.startswith("GATE"):
            stages = [x["stage"][0] for x in infos[slides[0] - 2:slides[0] + 20]] if slides else []
            extra = [] if stages and all(s == 2 for s in stages) else [f"étages {stages}"]
        if name.startswith("trigless"):
            notes = sorted({r["note"] >> 16 for r in recs})
            extra = [] if notes == [48, 55] else [f"notes {notes}"]
        if name.startswith("verrou"):
            mach = [x["machine"][0] for x in infos]
            seen = [m for k, m in enumerate(mach) if k == 0 or m != mach[k - 1]]
            extra = [] if seen[-3:] == [fw.index, TONE, fw.index] else [f"machines {seen}"]
        if why or unm or pr.kinds() != kinds or fade or not steps_ok or extra or peak < 1 << 22:
            bad.append(name)
            print(f"        ECART {name} : {why[:2]} trigs {pr.kinds()} (attendu {kinds}), fondus {fade}, "
                  f"gain {'ok' if steps_ok else 'saute'}, {extra}, hors mémoire {unm[:2]}")
    check(not bad, f"{label}, séquenceur de l'OS : {len(seq_cases(quick))} séquences ({n} blocs) : trigs rejoués ou "
                   "liés selon LEN (120, 300, 546 BPM, différents instants du bloc), jeu live, trigless, verrou "
                   "MACHINE, vélocité sans accent, DRIVE verrouillé par pas, gain de vélocité rejoint pas à pas "
                   "après un slide, sans fondu ; "
                   f"avant la chaîne d'ampli, identique à la référence à chaque bloc {bad[:3]}")


# --- 5. coût ---------------------------------------------------------------------------------------------------
def cost(fw, label):
    """Instructions par bloc d'une voix (boucle des voix entière, moins la même boucle sans voix), pile."""
    def run(idx, kw, blocks, trigs=(1,), left=None, changes=None):
        e = fw.engine(solo=0)
        e.set(0, machine=idx, **kw)
        if idx == OFF:
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
            if left is not None:
                set_globals(e, 0, left=left)
            i0 = n["i"]
            e.block(1 if b in trigs else 0)
            per.append(n["i"] - i0)
        return np.array(per), n["sp"]
    base, _ = run(OFF, KW, 4, trigs=())
    zero = int(np.median(base))
    tone, _ = run(TONE, dict(KW, color=40, shape=38, sweep=52, contour=42, decay=42), 24)
    saw, sp1 = run(fw.index, dict(KW, decay=100), 24)
    sq, sp2 = run(fw.index, dict(KW, punch=1, shape=127, decay=100), 24)
    sl, sp3 = run(fw.index, dict(KW, decay=100), 24, trigs=(1, 12), left=0, changes={12: dict(note=60)})
    drv, sp4 = run(fw.index, dict(KW, decay=100, contour=64), 24)
    idle, _ = run(fw.index, dict(KW, decay=0), 200)
    deep = E.STACK - 0x100 - min(sp1, sp2, sp3, sp4)
    m = lambda x: int(np.median(x[4:])) - zero
    check(True, f"{label} : coût d'une voix ACID {m(saw)} instructions par bloc (scie), {m(sq)} (carré), {m(drv)} "
                f"(DRIVE 64), 1er bloc {int(saw[2]) - zero}, bloc du slide {int(sl[12]) - zero} ; TONE {m(tone)} ; "
                f"voix muette "
                f"{int(np.median(idle[150:])) - zero} ; pile {deep} o sous la boucle des voix")


# --- 6. avec d'autres mods -----------------------------------------------------------------------------------------
def with_others(stock, cycles, ids, alone, tg_fw, tg, ref):
    """ACID avec d'autres mods (--with) : ACID seule, ou sa version combinée si model-tg-st est dans la liste."""
    by_id = {t["id"]: t for t in (load(f.name) for f in sorted(DEV.glob("[0-9]*.json")))}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise SystemExit(f"!! tweaks inconnus : {unknown}")
    others = [by_id[i] for i in ids]
    with_tg = any(t["id"].startswith("model-tg") for t in others)
    mine = by_id["acid-tg" if with_tg else "acid"]
    clash = [t["id"] for t in others if mine["id"] in t.get("conflicts", []) or t["id"] in mine["conflicts"]]
    if clash:
        raise SystemExit(f"!! incompatibles avec {mine['id']} : {clash}")
    fw = Fw(stock, sorted(others + [mine], key=lambda t: t["order"]))
    ref_fw = Fw(stock, sorted(others, key=lambda t: t["order"]))
    label = ", ".join(ids)
    print(f"\n== {mine['id']} avec {label} : ACID en machine {fw.index + 1}")
    print("démarrage")
    t7.X.bootstrap_depack_ok(cycles, fw.tweaks, None) or t7.FAIL.append("bootstrap avec " + label)
    boot(fw, tg if with_tg else None)
    print("son")
    stock_unchanged(ref_fw, fw, "ces mods sans ACID")
    like(tg_fw if with_tg else alone, fw, f"ACID avec {label} = ACID {'avec Model-TG seul' if with_tg else 'seule'}")
    locks(fw, f"ACID avec {label}")
    mixed(fw, ref_fw, f"ACID avec {label}", sampler=with_tg)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--quick", action="store_true", help="moins de cas et de tempos")
    ap.add_argument("--with", dest="others", default="", help="ids d'autres tweaks : ACID avec eux (section 6)")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    acid, tg_tw, acid_tg = load("26-acid.json"), load("30-model-tg-st.json"), load("35-acid-tg.json")
    off = Fw(stock, [])
    alone = Fw(stock, [acid])
    with tempfile.TemporaryDirectory() as d:
        ref = Ref(pathlib.Path(d))
        todo = cases(args.quick)

        print(f"== {acid['id']} : ACID en machine {alone.index + 1}")
        print("démarrage")
        t7.X.bootstrap_depack_ok(args.cycles, acid, None) or t7.FAIL.append("bootstrap")
        boot(alone)
        print("interface")
        interface_alone(stock, alone)
        print("son")
        exact(alone, ref, todo, "ACID seule")
        amp_like_tone(alone)
        drive_curve(alone)
        stock_unchanged(off, alone, "l'OS d'origine")
        locks(alone, "ACID seule")
        six_tracks(alone, "ACID seule")
        mixed(alone, off, "ACID seule")
        print("séquenceur")
        sequencer(alone, ref, "ACID seule", args.quick)
        print("coût")
        cost(alone, "ACID seule")

        gs.set_base(gs.PAY_TG)
        gs.CATALOG["acid"] = ga.MACHINE
        fw, ref_tg = Fw(stock, [tg_tw, acid_tg]), Fw(stock, [tg_tw])
        tg = {k: int(v, 16) for k, v in tg_tw["symbols"].items()}
        tg["knob_vec"] = tms.knob_vec_at(acid_tg)
        print(f"\n== {acid_tg['id']} : avec Model-TG, ACID en machine {fw.index + 1}")
        print("démarrage")
        t7.X.bootstrap_depack_ok(args.cycles, [tg_tw, acid_tg], None) or t7.FAIL.append("bootstrap avec Model-TG")
        boot(fw, tg)
        print("interface")
        tms.interface(ref_tg, fw, ["acid"], tg)
        print("son")
        exact(fw, ref, todo if not args.quick else todo[:3] + todo[-5:], "ACID avec Model-TG")
        stock_unchanged(ref_tg, fw, "Model-TG seul")
        like(alone, fw, "ACID avec Model-TG = ACID seule")
        locks(fw, "ACID avec Model-TG")
        six_tracks(fw, "ACID avec Model-TG")
        mixed(fw, ref_tg, "ACID avec Model-TG", sampler=True)
        print("séquenceur")
        sequencer(fw, ref, "ACID avec Model-TG", True)
        print("coût")
        cost(fw, "ACID avec Model-TG")
        if args.others:
            with_others(stock, args.cycles, args.others.split(","), alone, fw, tg, ref)
    fail = t7.FAIL + tms.FAIL
    print("\nTOUT OK" if not fail else f"\n{len(fail)} ÉCHEC(S)")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
