#!/usr/bin/env python3
"""Preuve d'ACID avec MACRO et les moteurs du Syntakt (notes/54 §11, tools/gen_acid_combos.py) : 25-macro-acid.json
et 32-macro-acid-tg.json (MACRO puis ACID), 24-syntakt-<moteurs>[-macro]-acid.json et leurs versions avec Model-TG
31-syntakt-tg-<moteurs>[-macro]-acid.json. Le vrai code de l'OS, émulé (Unicorn).

Références, toutes construites ici avec les mêmes mods de base : ACID seule (26-acid.json, 35-acid-tg.json), MACRO
seule (25-macro.json, 32-macro-tg.json), les moteurs seuls (24-/31-syntakt-<moteurs>) et avec MACRO (…-macro).

  1. Démarrage : le décompresseur du bootstrap relit l'OS agrandi ; le crochet reconstitue la charge utile (MACRO
     et ACID seules : en clair, par morceaux ; avec les moteurs : décompressée, cache d'instructions invalidé avant
     le 2e étage, tables d'ondes de CHORD reprises), puis reprend, pile et registres intacts. La partie des moteurs
     est celle des moteurs seuls (sauf ce qui compte les machines), MACRO celle de son tweak, octet pour octet.
  2. Interface : les vérifications de test_syntakt_machines.py (seul) et de test_model_tg_syntakt.py (avec
     Model-TG), pour les moteurs, MACRO et ACID après eux (jusqu'à 14 machines : rangées déplacées, gs.ROWS7).
  3. Son, la boucle des voix seule (mcengine), minuteur DMA 0 qui avance d'un bloc à chaque bloc :
     - avant la chaîne d'ampli, ACID est exactement le même cœur compilé pour l'ordinateur (test_acid.py), MACRO
       exactement Braids (test_macro.py) : quelques cas ;
     - les 6 machines d'origine et chaque moteur : identiques aux moteurs seuls ; sans ACID sur une piste, pas une
       instruction d'ACID ;
     - la piste ACID (et MACRO) : identique à ACID seule (MACRO seule), à l'arrêt d'une voix muette par le
       régulateur près ; 6 pistes ACID ; tout ensemble sur les 6 pistes (le Sampler avec Model-TG) ; machine locks
       qui passent par toutes les machines ajoutées ;
     - GOV_SKIP : une note ACID tenue, éteinte par le régulateur sous la surcharge, puis un trig : la note est
       rejouée (ACID seule, jamais éteinte, glisse ; sans le minuteur, la version combinée glisserait depuis la note
       éteinte) ;
     - régulateur de charge : en surcharge, il éteint aussi les pistes ACID, jamais le Sampler.
  4. Son, avec le séquenceur de l'OS (seqrig.py), comme test_acid.py : trigs rejoués ou liés, jeu live, verrous.
  5. Coût d'une voix ACID (informatif).
  6. Avec d'autres mods (--with) : démarrage, et les comparaisons du son.

    python3 tools/emu/test_acid_combos.py --cycles model-cycles_OS1.13.syx --syntakt Syntakt_OS1.42.syx \\
        --eurorack vendor/eurorack [--engines sd,cp,toy,bits,swarm | --engines none] [--macro yes|no|both] \\
        [--only alone|tg] [--with 6ch-usbup,model-tg-st,trig-hold,…]

--eurorack ne sert qu'avec MACRO (Braids compilé pour l'ordinateur). Durée : de 10 à 20 min par combinaison et par
version (seule, avec Model-TG).
"""
import argparse
import pathlib
import struct
import sys
import tempfile

import numpy as np
from unicorn import UC_HOOK_MEM_READ
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import gen_acid as ga               # noqa: E402
import gen_acid_combos as gac       # noqa: E402
import gen_macro as gm              # noqa: E402
import gen_macro_syntakt as gms     # noqa: E402
import gen_sdvintage_7th as g7      # noqa: E402
import gen_syntakt_engines as gs    # noqa: E402
import lofi_ui                      # noqa: E402
import mcengine as E                # noqa: E402
import seqrig as S                  # noqa: E402
import syntakt                      # noqa: E402
import test_acid as ta              # noqa: E402
import test_macro as tm             # noqa: E402
import test_macro_syntakt as tmx    # noqa: E402
import test_model_tg as TM          # noqa: E402
import test_model_tg_syntakt as tms  # noqa: E402
import test_sdvintage as T          # noqa: E402
import test_sdvintage_7th as t7     # noqa: E402
import test_syntakt_machines as tsm  # noqa: E402

BASE = E.BASE
check = t7.check
load = ta.load
KW = ta.KW
TIMER, BLOCK = tmx.TIMER, tmx.BLOCK
SKIP_TICKS = 3 * BLOCK               # acid.c, GOV_SKIP
M32 = 0xffffffff
# machine hors limites, pour les pistes éteintes : 9 est un moteur du Syntakt ici (test_syntakt_machines.out_of_range,
# la boucle des voix : rien au-delà de la dernière machine)
OFF = 100
ta.OFF = OFF


def engines_of(t):
    """Moteurs du Syntakt d'un tweak (syntakt-[tg-]<moteurs>[-macro][-acid])."""
    return [c for c in t["id"].split("-") if c in gs.CATALOG and c not in ("macro", "acid")]


tmx.engines_of = engines_of          # chord_at, avec « acid » au catalogue (interface)


class View:
    """Une machine ajoutée d'un firmware : son index et son code, le reste du firmware (test_acid, test_macro)."""

    def __init__(self, fw, **kw):
        self._fw = fw
        self.__dict__.update(kw)

    def __getattr__(self, k):
        return getattr(self._fw, k)


class Fw:
    """Un firmware : MAIN OS (avec ce qui est ajouté après), la charge utile telle qu'en mémoire après le crochet de
    démarrage, et une vue par machine ajoutée trouvée dans ses symboles (MACRO, ACID)."""

    def __init__(self, stock, tweaks, ctx):
        p, _ = build.apply_writes(stock, tweaks)
        pl, _ = build.build_payload(tweaks, stock, ctx["syntakt"])
        self.img, self.tweaks, self.packed = bytes(p) + pl, tweaks, len(pl)
        tg = [t for t in tweaks if t["id"].startswith("model-tg")]
        self.blob_end = BASE + len(stock) + tg[0]["append"]["size"] if tg else None
        self.keep = [(TM.BLOB, self.blob_end)] if tg else []
        if tg:
            self.packed -= tg[0]["append"]["size"]
        self.payload, self.views, self.emac, self.gov_skip, self.codes = None, {}, (), False, []
        ours = [t for t in tweaks if t.get("append") and not t["id"].startswith("model-tg")]
        if not ours:
            return
        t = self.mine = ours[0]
        ap_ = t["append"]
        dest = self.dest = int(ap_["dest"], 16)
        rt = bytearray(build.payload_runtime(t, stock, ctx["st_img"]))
        if ap_.get("compress"):
            self.chord_at = tmx.chord_at(t, ctx)
            rt[self.chord_at - dest:self.chord_at - dest + len(ctx["chord"])] = ctx["chord"]
        self.runtime = bytes(rt)
        self.payload = (dest, self.runtime)
        syms = {k: int(v, 16) for k, v in t.get("symbols", {}).items()}
        first = gs.TG_FIRST if tg else 6
        self.codes = engines_of(t)
        kinds = [k for k in ("macro", "acid") if k + "_update" in syms]
        self.nm = first + len(self.codes) + len(kinds)
        data = dest + gs.LAYOUT["DATA"]
        u32 = lambda va: struct.unpack_from(">I", self.runtime, va - dest)[0]
        for i, k in enumerate(kinds):
            index = first + len(self.codes) + i
            upd, rnd = u32(data + 4 * self.nm + 4 * index), u32(data + 8 * self.nm + 4 * index)
            check(upd == syms[k + "_update"] and rnd == syms[k + "_render"],
                  f"{t['id']} : la table des machines appelle {k}_update et {k}_render (machine {index + 1})")
            part = next(p_ for p_ in ap_["parts"] if "hex" in p_
                        and int(p_["dest"], 16) <= upd < int(p_["dest"], 16) + len(p_["hex"]) // 2)
            pay = int(part["dest"], 16)
            self.views[k] = View(self, index=index, pay=pay, code_end=pay + len(part["hex"]) // 2, upd=upd, rnd=rnd,
                                 braids_render=syms.get("braids_render"))
        acid = self.views.get("acid")
        if acid:
            self.emac = ((acid.pay, acid.code_end),)          # ACID calcule avec l'EMAC (acid_dsp.h)
            self.gov_skip = t["id"] not in ("acid", "acid-tg")
        self.index = self.nm - 1

    def engine(self, solo=None):
        """La boucle des voix seule, ce qu'ACID lit hors de la voix comme test_acid.Fw.engine (vélocité 100, gain de
        vélocité 100, 120 BPM, reste de longueur d'un bloc) ; le minuteur DMA 0 avance d'un bloc à chaque bloc
        (e.clock)."""
        if self.blob_end:
            e = TM.engine(self.img, end=self.blob_end, payload=self.payload, payload_code=self.emac)
        else:
            e = E.Engine(self.img, payload=self.payload, payload_code=self.emac)
        S.ensure_map(e.uc, 0x40800000, 0x01800000)
        e.uc.mem_write(S.TEMPO, struct.pack(">i", ta.T120))
        for t in range(6):
            ta.set_globals(e, t, vel=100, gain=100, left=ta.T120)
        if solo is not None:             # les autres pistes : machine hors limites, rien n'est calculé
            for t in range(6):
                if t != solo:
                    e.uc.mem_write(E.VOICE0 + t * E.VSTRIDE, struct.pack(">II", OFF, OFF))
        e.clock = dict(t=10_000_000, step=BLOCK)
        blk = e.block

        def block(*a, **k):
            e.uc.mem_write(TIMER, struct.pack(">I", e.clock["t"] & M32))
            e.clock["t"] += e.clock["step"]
            return blk(*a, **k)
        e.block = block
        return e

    def view(self, k):
        return self.views[k]


class SkipBridge(ta.Bridge):
    """test_acid.Bridge, plus GOV_SKIP : un appel plus de 3 blocs (minuteur DMA 0) après le précédent marque la voix
    tue (la note suivante est rejouée)."""

    def __init__(self, uc):
        super().__init__()
        self.seen = [0] * 6
        self.now = lambda: struct.unpack(">I", uc.mem_read(TIMER, 4))[0]     # ce qu'ACID lira

    def update(self, t, pmod, vb, pb, g):
        now = self.now()
        if (now - self.seen[t]) & M32 > SKIP_TICKS:
            self.st[t]["idle"] = 1
        self.seen[t] = now
        return super().update(t, pmod, vb, pb, g)


class Probe(ta.Probe):
    def __init__(self, fw, e, tracks=(0,), reads=False):
        super().__init__(fw, e, tracks, reads)
        if fw.gov_skip:
            self.spec = SkipBridge(e.uc)


ta.Probe = Probe                     # test_acid.play et sequence


# --- 1. démarrage ----------------------------------------------------------------------------------------------
def machine_window(n, nm):
    """Ce qui compte les machines dans la charge utile (décalages) : détours, données, descripteurs, rangées."""
    gs.set_rows(n)
    end = max(gs.DESCN + (g7.NDESC + 5 * n) * g7.DSTRIDE, gs.CCROWSN + 32 * nm, gs.RECS + 0x60 * n) - gs.PAY
    return [(gs.LAYOUT["STUBS"], end)]


def boot(fw, ref, tgs, macro_ref):
    """Le crochet, exécuté pour de vrai (test_acid.boot ou test_macro_syntakt.boot) ; MACRO octet pour octet."""
    gs.set_base(fw.dest)
    if fw.mine["append"].get("compress"):
        n = len(fw.codes) + len(fw.views)
        tmx.boot(fw, ref, tgs, machine_window(n, fw.nm))
    else:
        ta.boot(fw, tgs)
    if macro_ref is not None:
        m, r = fw.views["macro"], macro_ref.views["macro"]
        a = fw.runtime[m.pay - fw.dest:m.code_end - fw.dest]
        b = macro_ref.runtime[r.pay - macro_ref.dest:r.code_end - macro_ref.dest]
        check(m.pay == r.pay and a == b, f"MACRO à {m.pay:#x} : ses {len(a)} o, ceux de {macro_ref.mine['id']}")
    acid = fw.views["acid"]
    low = min([v.pay for v in fw.views.values()])
    check(acid.code_end <= gs.PAY + gac.ACID_BSS and acid.pay >= low,
          f"ACID à {acid.pay:#x}..{acid.code_end:#x}, ses variables à {gs.PAY + gac.ACID_BSS:#x}, au-dessus de MACRO "
          "et des moteurs")


# --- 2. interface ----------------------------------------------------------------------------------------------
def interface(stock, fw, tw, tgs, tref):
    gs.CATALOG.setdefault("macro", dict(gm.MACHINE, label="MACRO"))
    gs.CATALOG.setdefault("acid", dict(ga.MACHINE, label="ACID"))
    added = fw.codes + list(fw.views)
    gs.set_base(fw.dest)
    gs.set_rows(len(added))
    if tgs:
        tms.interface(tref, fw, added, tgs)
        return
    tsm.configure({"id": "syntakt-" + "-".join(added)})    # macro-acid : pas de moteur dans l'id
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
def same(a, b, retrig, governed):
    """Identiques ; avec le régulateur des moteurs, à l'arrêt d'une voix muette près (test_model_tg_syntakt)."""
    if governed:
        return tms.same_or_idle(a, b, retrig)
    return bool(np.array_equal(a, b)), None


def like(alone, v, label, governed):
    """Sortie finale de la piste ACID : identique à ACID seule (test_acid.like), scie, carré, GATE, DRIVE."""
    bad, cut = [], []
    for kw in (KW, dict(KW, punch=1, note=36), dict(KW, color=110, shape=127, decay=100, gate=1, contour=100)):
        a, _, _ = ta.play(alone, kw, 200, (1, 120), vels={120: 127})
        b, _, unm = ta.play(v, kw, 200, (1, 120), vels={120: 127})
        ok, f = same(a, b, 120, governed)
        cut.append(f)
        if not ok or unm or not a.any():
            bad.append(kw)
    check(not bad, f"{label} : piste ACID identique à ACID seule (scie, carré, GATE, DRIVE)"
                   f"{f', voix muette arrêtée par le régulateur aux blocs {cut}' if governed else ''} {bad[:1]}")


def together(fw, ref, alone_acid, alone_macro, label, sampler, governed):
    """Les 6 pistes : KICK, 1er moteur (ou SNARE), MACRO (ou TONE), CHORD (ou le Sampler), ACID, ACID (carré)."""
    acid, macro = fw.views["acid"], fw.views.get("macro")
    codes, first = fw.codes, gs.TG_FIRST if sampler else 6
    mach = [0, first if codes else 1, macro.index if macro else ta.TONE, 6 if sampler else 5, acid.index, acid.index]
    kw = {t: dict(KW, color=64, shape=64, decay=40, machine=m) for t, m in enumerate(mach)}
    if codes:
        e = gs.CATALOG[codes[0]]
        kw[1].update(color=e["knobs"][0][2], shape=e["knobs"][1][2], sweep=e["knobs"][2][2], contour=e["knobs"][3][2])
    ours = {4: dict(KW, decay=40), 5: dict(KW, note=36, punch=1, decay=40)}
    if macro:
        ours[2] = dict(tm.BASE_KW, shape=0, decay=40)                # CSAW : sans le générateur aléatoire
    for t, k in ours.items():
        kw[t] = dict(k, machine=mach[t])
    trigs = {1: 0x3f, 150: 0x3f}
    x, unm = tmx.multi(fw, kw, 300, trigs)
    r, unm_r = tmx.multi(ref, {t: dict(k, machine=0) if t in ours else k for t, k in kw.items()}, 300, trigs)
    ok, cut = not unm and not unm_r, []
    for t in range(6):
        if t == 2 and macro:
            y, _, _ = tm.play(alone_macro, alone_macro.index, ours[2], 300, (1, 150), track=t)
        elif t in ours:
            y, _, _ = ta.play(alone_acid, ours[t], 300, (1, 150), track=t)
        else:
            ok &= bool(np.array_equal(x[:, t], r[:, t]))
            continue
        good, f = same(y, x[:, t], 150, governed)
        ok &= good and bool(x[:, t].any())
        cut.append(f)
    if sampler:
        ok &= not x[:, 3].any()
    names = ["KICK", "moteur" if codes else "SNARE", "MACRO" if macro else "TONE", "Sampler" if sampler else "CHORD",
             "ACID", "ACID (carré)"]
    check(ok, f"{label} : pistes {', '.join(f'{n} ({m + 1})' for n, m in zip(names, mach))} ensemble ; machines "
              f"d'origine{' et moteur' if codes else ''} identiques sans ACID, ACID{' et MACRO' if macro else ''} "
              f"à leur version seule{f' (arrêt {cut})' if governed else ''}")


def locks(fw, label):
    """Machine locks sur une piste, par toutes les machines ajoutées : SNARE, 1er moteur, MACRO (FM), ACID, TONE,
    dernier moteur, ACID (carré), MACRO (WAVETABLES), KICK : tout joue ; la marque d'ACID effacée à la fin."""
    acid, macro, codes = fw.views["acid"], fw.views.get("macro"), fw.codes
    first = gs.TG_FIRST if fw.blob_end else 6
    seq = [("SNARE", dict(KW, machine=1))]
    if codes:
        seq.append(("moteur", dict(KW, machine=first)))
    if macro:
        seq.append(("MACRO (FM)", dict(tm.BASE_KW, machine=macro.index, shape=25)))
    seq += [("ACID", dict(KW, machine=acid.index)), ("TONE", dict(KW, machine=ta.TONE))]
    if codes:
        seq.append(("moteur", dict(KW, machine=first + len(codes) - 1)))
    seq.append(("ACID (carré)", dict(KW, machine=acid.index, punch=1)))
    if macro:
        seq.append(("MACRO (WAVETABLES)", dict(tm.BASE_KW, machine=macro.index, shape=37)))
    seq.append(("KICK", dict(KW, machine=0)))
    e = fw.engine(solo=0)
    e.set(0, **dict(KW, machine=1, decay=40))
    out = []
    for b in range(60 * len(seq)):
        if b % 60 == 0:
            e.set(0, **dict(seq[b // 60][1], decay=40))
        out.append(e.block(1 if b % 60 == 1 else 0)[0])
    x = np.stack(out)
    parts = [int(np.abs(x[60 * k + 2:60 * k + 60]).max()) for k in range(len(seq))]
    mark = struct.unpack(">I", e.uc.mem_read(E.VOICE0 + 0x2c, 4))[0]
    check(all(p > 1e6 for p in parts) and not e.unmapped and mark != ta.MARK,
          f"{label} : machine locks {' -> '.join(n for n, _ in seq)} sur une piste : tout joue "
          f"(crêtes {[f'{p:.2g}' for p in parts]})")


GAINS, FULL = tmx.GAINS, tmx.FULL


def governor(fw, tw, label, sampler=False):
    """Surcharge (comme test_macro_syntakt.governor) : 6 pistes ACID, ou 3 ACID et 3 MACRO (avec Model-TG, le Sampler
    en piste 3). Charge fixe de 97 % : toutes éteintes, jamais le Sampler ; 46 % + 7 % par voix calculée : une partie
    seulement ; les pistes épargnées identiques à la référence, les éteintes muettes ensuite. Le minuteur avance d'un
    bloc à chaque bloc, plus le coût des voix ; la lecture de GOV_SKIP (ACID) n'en coûte pas."""
    acid, macro = fw.views["acid"], fw.views.get("macro")
    sy = {k: int(v, 16) for k, v in tw["gov"].items()}
    setup = {}
    for t in range(6):
        if macro and t % 2:
            setup[t] = dict(tm.BASE_KW, machine=macro.index, shape=(0, 1, 2, 3, 9, 10)[t], note=48 + 5 * t,
                            decay=100)
        else:
            setup[t] = dict(KW, machine=acid.index, note=36 + 5 * t, punch=int(t % 3 == 1), color=30 + 15 * t,
                            gate=1, decay=100)
    if sampler:
        setup[2] = dict(KW, machine=6, decay=100)
    cost = 2 * 7 * BLOCK // 100

    def play_(load_):
        e = fw.engine()
        for t in range(6):
            for a in GAINS:
                e.uc.mem_write(a + 4 * t, struct.pack(">I", FULL))
        clock = {"t": 10_000_000, "fixed": None, "reads": 0}

        def read(uc, access, addr, size, value, ud):
            pc = uc.reg_read(mk.UC_M68K_REG_PC)
            if clock["fixed"] is not None:
                v = clock["fixed"]
            elif acid.pay <= pc < acid.code_end:
                v = clock["t"]
            else:
                clock["t"] += cost // 2
                clock["reads"] += 1
                v = clock["t"]
            uc.mem_write(TIMER, struct.pack(">I", v & M32))
        e.uc.hook_add(UC_HOOK_MEM_READ, read, begin=TIMER, end=TIMER + 3)
        for t, kw in setup.items():
            e.set(t, **kw)
        e.uc.mem_write(tms.gs_x(tw, "X_SLOW"), struct.pack(">I", 88 * 65536 // 100))
        out, stolen, now = [], set(), 10_000_000
        for b in range(300):
            clock["reads"], clock["t"] = 0, max(clock["t"], now)
            out.append(e.block(0x3f if b == 1 else 0))
            if load_ is not None:
                e.uc.mem_write(sy["gov_t0_audio"], struct.pack(">I", now & M32))
                clock["fixed"] = now + load_(b, clock["reads"] // 2) * BLOCK // 100
                e.call(sy["audio_end"])
                clock["fixed"] = None
            now += BLOCK
            stolen |= {t for t, v in enumerate(bytes(e.uc.mem_read(sy["gov_stolen"], 6))) if v}
        return np.stack(out), stolen, e.unmapped
    ref, _, _ = play_(None)
    ours = set(range(6)) - ({2} if sampler else set())
    silent = lambda mod, ts: all(not np.abs(mod[-50:, t]).max() and np.abs(ref[-50:, t]).max() for t in ts)
    for name, load_, want in (("charge fixe de 97 %", lambda b, n: 97 if b < 200 else 50, lambda st: st == ours),
                              ("charge de 46 % + 7 % par voix calculée", lambda b, n: 46 + 7 * n,
                               lambda st: st and st < ours)):
        mod, stolen, unm = play_(load_)
        spared = set(range(6)) - stolen
        same_ = all(np.array_equal(ref[:, t], mod[:, t]) for t in spared)
        check(want(stolen) and same_ and silent(mod, stolen) and not unm,
              f"{label} : surcharge ({name}) : pistes {'ACID et MACRO' if macro else 'ACID'} éteintes "
              f"{sorted(t + 1 for t in stolen)}, muettes ensuite{', jamais le Sampler (piste 3)' if sampler else ''} ; "
              f"les autres {sorted(t + 1 for t in spared)} identiques à la référence")


def gov_skip(fw, alone, tw, ref, label):
    """GOV_SKIP : une note ACID tenue (GATE, sans fin de note) que le régulateur éteint sous la surcharge (blocs 20 à
    49 à 97 %), puis un trig (bloc 100, autre note). Le minuteur avance d'un bloc à chaque bloc : la note est rejouée,
    cœur remis à zéro (TT). ACID seule, jamais éteinte, glisse (TS). Minuteur figé pour ACID (sans GOV_SKIP) : la
    version combinée glisserait depuis la note éteinte (TS). Avant la chaîne d'ampli, toujours la référence."""
    acid = fw.views["acid"]
    sy = {k: int(v, 16) for k, v in tw["gov"].items()}
    kw = dict(KW, decay=110, gate=1)
    cost = 2 * 7 * BLOCK // 100                    # comme governor : 7 % d'un bloc par voix calculée

    def run(f, ticking, overload):
        e = f.engine(solo=0)
        e.set(0, machine=f.index, **kw)
        pr = Probe(f, e, (0,))
        clock = {"t": 10_000_000, "acid": 0, "fixed": None}

        def read(uc, access, addr, size, value, ud):
            if clock["fixed"] is not None:
                v = clock["fixed"]
            elif acid.pay <= uc.reg_read(mk.UC_M68K_REG_PC) < acid.code_end:
                v = clock["acid"]                  # GOV_SKIP : l'heure du bloc, ou figée
            else:
                clock["t"] += cost // 2
                v = clock["t"]
            uc.mem_write(TIMER, struct.pack(">I", v & M32))
        e.uc.hook_add(UC_HOOK_MEM_READ, read, begin=TIMER, end=TIMER + 3)
        if isinstance(pr.spec, SkipBridge):
            pr.spec.now = lambda: clock["acid"] & M32
        for a in GAINS:
            e.uc.mem_write(a, struct.pack(">I", FULL))
        if overload:
            e.uc.mem_write(tms.gs_x(tw, "X_SLOW"), struct.pack(">I", 88 * 65536 // 100))
        out, stolen, called, now = [], [], [], 10_000_000
        for b in range(160):
            pr.block = b
            clock["t"], clock["acid"] = max(clock["t"], now), now if ticking else 0
            if b == 100:
                e.set(0, note=55)
            ta.set_globals(e, 0, left=0)
            n0 = len(pr.recs[0])
            out.append(e.block(1 if b in (1, 100) else 0)[0])
            called.append(len(pr.recs[0]) > n0)
            if overload:
                e.uc.mem_write(sy["gov_t0_audio"], struct.pack(">I", now & M32))
                clock["fixed"] = now + (97 if 20 <= b < 50 else 40) * BLOCK // 100
                e.call(sy["audio_end"])
                clock["fixed"] = None
                if e.uc.mem_read(sy["gov_stolen"], 1)[0]:
                    stolen.append(b)
            now += BLOCK
        return np.stack(out), pr, e.unmapped, stolen, called
    _, pa, unm_a, _, _ = run(alone, True, False)
    x, pt, unm_t, st_t, called = run(acid, True, True)
    _, pf, unm_f, st_f, _ = run(acid, False, True)
    why_t, _ = pt.verify(ref)
    why_f, _ = pf.verify(ref)
    skipped = [b for b in range(20, 100) if not called[b]]
    reset = [r["block"] for r in pt.recs[0] if r.get("reset")]
    trigs = [r["block"] for r in pt.recs[0] if r["trig"]]          # l'OS livre le trig au bloc suivant
    ok = (pa.kinds() == "TS" and pt.kinds() == "TT" and pf.kinds() == "TS" and not why_t and not why_f
          and st_t and st_f and len(skipped) > 30 and reset == trigs and trigs[-1] in (100, 101)
          and not x[skipped].any() and np.abs(x[102:]).max() > 1e7 and not (unm_a or unm_t or unm_f))
    check(ok, f"{label} : GOV_SKIP : note tenue éteinte par le régulateur (dès le bloc {st_t[:1]}, pas calculée "
              f"pendant {len(skipped)} blocs), trig suivant rejoué ({pt.kinds()}, cœur remis à zéro aux blocs "
              f"{reset}) ; ACID seule glisse ({pa.kinds()}) ; minuteur figé, la version combinée glisserait "
              f"({pf.kinds()}) ; avant la chaîne d'ampli, la référence {why_t[:1]}{why_f[:1]}")


# --- un jeu de vérifications --------------------------------------------------------------------------------------
def run_set(stock, ctx, codes, macro, tg, others, quick, label_extra=""):
    """Toutes les vérifications pour une version (seule ou avec Model-TG), avec d'autres mods éventuels."""
    first = gs.TG_FIRST if tg else 6
    tw = load(f"{gac.order(tuple(codes), tg)}-{gac.tweak_id(tuple(codes), tg, macro)}.json")
    base = ([load("30-model-tg-st.json")] if tg else []) + others
    order = lambda ts: sorted(ts, key=lambda t: t["order"])
    make = lambda *ts: Fw(stock, order(base + [t for t in ts if t]), ctx)
    fw = make(tw)
    alone_acid = make(load("35-acid-tg.json" if tg else "26-acid.json")).views["acid"]
    alone_macro = make(load("32-macro-tg.json" if tg else "25-macro.json")) if macro else None
    if codes:
        ref_eng = make(load(f"{31 if tg else 24}-{gs.tweak_id(codes, tg=tg)}.json"))
        ref_em = make(load(f"{31 if tg else 24}-{gms.tweak_id(codes, tg)}.json")) if macro else None
        without = ref_em or ref_eng
    else:
        ref_eng = ref_em = None
        without = alone_macro
    governed = bool(codes)
    acid, macro_v = fw.views["acid"], fw.views.get("macro")
    names = [gs.CATALOG[c]["name"] for c in codes] + (["MACRO"] if macro else []) + ["ACID"]
    print(f"\n== {tw['id']}{label_extra} : {', '.join(names)} en machines {first + 1}..{fw.nm}")
    print("démarrage")
    t7.X.bootstrap_depack_ok(ctx["cycles"], fw.tweaks, ctx["syntakt"]) or t7.FAIL.append("bootstrap " + tw["id"])
    tgs = None
    if tg:
        tg_tw = next(t for t in fw.tweaks if t["id"].startswith("model-tg"))
        tgs = {k: int(v, 16) for k, v in tg_tw["symbols"].items()}
        tgs["knob_vec"] = tms.knob_vec_at(tw)
    boot(fw, ref_eng, tgs, (ref_em or alone_macro) if macro else None)
    if not others:
        print("interface")
        interface(stock, fw, tw, tgs, make() if tg else None)
    if macro:                     # le lo-fi de MACRO sous FUNC + PITCH (notes/55 §8), ACID après elle
        lref = ref_eng or make()
        lofi_ui.check_lofi(lref.img, fw.img, fw.payload, macro_v.index, f"MACRO dans {tw['id']}{label_extra}", check,
                           end=fw.blob_end, base_end=lref.blob_end, base_payload=lref.payload,
                           base="les mêmes mods sans MACRO ni ACID", after=1)
    print("son")
    gs.set_base(fw.dest)
    todo = ta.cases(True)
    if not others:
        ta.exact(acid, ctx["acid_ref"], todo[:3] + todo[-5:] if quick else todo, f"ACID dans {tw['id']}")
        if macro:
            tmx.exact_some(macro_v, ctx["braids"], f"MACRO dans {tw['id']}")
    if codes:
        tmx.engines_like(fw, ref_eng, codes, first, f"avec ACID{label_extra}")
    ta.stock_unchanged(without, acid, f"{without.mine['id']}{label_extra} (sans ACID)")
    like(alone_acid, acid, f"ACID dans {tw['id']}{label_extra}", governed)
    if macro:
        tmx.macro_like(macro_v, alone_macro.views["macro"], f"MACRO dans {tw['id']}{label_extra}")
    if not quick or not others:
        ta.six_tracks(acid, f"ACID dans {tw['id']}{label_extra}")
    together(fw, without, alone_acid, alone_macro.views["macro"] if macro else None, f"ensemble{label_extra}",
             tg, governed)
    locks(fw, f"{tw['id']}{label_extra}")
    if codes:
        print("régulateur de charge")
        governor(fw, tw, f"{tw['id']}{label_extra}", sampler=tg)
        gov_skip(fw, alone_acid, tw, ctx["acid_ref"], f"{tw['id']}{label_extra}")
    if not others:
        print("séquenceur")
        ta.sequencer(acid, ctx["acid_ref"], f"ACID dans {tw['id']}", True)
        print("coût")
        ta.cost(acid, f"ACID dans {tw['id']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--syntakt", required=True, help="Syntakt_OS1.42.syx (ou 1.41) officiel")
    ap.add_argument("--eurorack", help="clone de pichenettes/eurorack (tools/gen_macro.py) : avec MACRO")
    ap.add_argument("--engines", default=",".join(gs.CATALOG), help="moteurs (défaut : les 5), ou none (macro-acid)")
    ap.add_argument("--macro", choices=("yes", "no", "both"), default="both", help="avec les moteurs : MACRO ou non")
    ap.add_argument("--with", dest="others", default="", help="ids d'autres tweaks (model-tg-st : la version "
                                                              "combinée avec Model-TG)")
    ap.add_argument("--only", choices=("alone", "tg"), help="une seule des deux versions")
    ap.add_argument("--quick", action="store_true", help="moins de cas d'ACID exacte")
    args = ap.parse_args()
    if args.engines == "none":
        codes, macros = [], [True]
    else:
        want = args.engines.split(",")
        if set(want) - set(gs.CATALOG):
            raise SystemExit(f"!! moteurs inconnus : {set(want) - set(gs.CATALOG)}")
        codes = [c for c in gs.CATALOG if c in want]
        macros = {"yes": [True], "no": [False], "both": [False, True]}[args.macro]
    if any(macros) and not args.eurorack:
        raise SystemExit("!! avec MACRO : --eurorack (Braids compilé pour l'ordinateur)")
    stock = T.main_os_from_syx(args.cycles)
    st_img = syntakt.dsp_image(args.syntakt)
    with tempfile.TemporaryDirectory() as d:
        ctx = dict(cycles=args.cycles, syntakt=args.syntakt, st_img=st_img, chord=tmx.chord_tables(stock),
                   acid_ref=ta.Ref(pathlib.Path(d)))
        if any(macros):
            repo = pathlib.Path(args.eurorack).resolve()
            gm.check_sources(repo)
            ctx["braids"] = tm.Ref(pathlib.Path(d), repo)
        others, tgs = [], (False, True)
        if args.others:
            by_id = {t["id"]: t for t in (load(f.name) for f in sorted(ta.DEV.glob("[0-9]*.json")))}
            ids = args.others.split(",")
            unknown = [i for i in ids if i not in by_id]
            if unknown:
                raise SystemExit(f"!! tweaks inconnus : {unknown}")
            others = [by_id[i] for i in ids if i != "model-tg-st"]
            tgs = ("model-tg-st" in ids,)
        for tg in tgs:
            if args.only and args.only != ("tg" if tg else "alone"):
                continue
            for macro in macros:
                extra = f" avec {args.others}" if args.others else ""
                run_set(stock, ctx, codes, macro, tg, others, args.quick, extra)
    fail = t7.FAIL + tms.FAIL
    print("\nTOUT OK" if not fail else f"\n{len(fail)} ÉCHEC(S)")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
