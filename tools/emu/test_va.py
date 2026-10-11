#!/usr/bin/env python3
"""Preuve des machines VA (notes/56 §4) : VA, VA KICK, VA SNARE et VA HIHAT, d'après le firmware « Model-TG-VA-DR-v1 »
de DavidCaruso, en machines ajoutées : seules (27-va.json, machines 7 à 10) et avec Model-TG (36-va-tg.json
par-dessus 30-model-tg-st.json, machines 8 à 11). Le vrai code de l'OS, émulé (Unicorn), avec la charge utile telle
que le crochet de démarrage la reconstitue.

  1. Démarrage : comme MACRO (stub.S, PACK) : la charge utile remise à zéro puis recopiée, la SRAM intacte, puis la
     remise à zéro du BSS de l'OS (seules) ou boot_extra_hook de Model-TG (avec), pile et registres intacts.
  2. Interface : les vérifications de test_syntakt_machines.py (seules) et de test_model_tg_syntakt.py (avec
     Model-TG) pour les 4 machines : rangées, recherches, descripteurs (noms, défauts, 0..127), écran MACHINES,
     molette, enregistrements, changement de machine réel, potards, icônes ; les noms en entier (8 caractères).
  3. Le code seul : va_fill et va_post compilés, exécutés hors de l'OS, = tools/emu/va_ref.py au bit près (4 machines,
     potards aux bouts et au hasard, notes de 0 à 127 et au-delà, trigs, pistes entrelacées ; état des pistes et des
     deux générateurs comparé après chaque appel).
  4. Dans la boucle des voix de l'OS :
     - à chaque bloc, ce que reçoit la passerelle (entrée de va_update) et les 64 échantillons à 96 kHz qu'elle donne
       au décimateur de TONE = va_ref (Bridge + Dsp) nourri de ce qu'elle voit ; état et générateurs identiques après
       chaque bloc ; potards lus = ceux réglés (COLOR, SHAPE, SWEEP, CONTOUR -> potards 1 à 4) ;
     - une voix muette (ni trig, enveloppe d'ampli sous 2^14) : ni update de TONE ni rendu, sortie nulle ;
     - le 1er bloc sur une machine VA (celui où l'OS applique la machine, après le trig) : état remis à zéro, note
       jouée (sinon la 1re note après un changement de machine serait perdue) ;
     - batteries : gain et saturation (va_post) sur la sortie de PUNCH, puis la boucle divise par 2 ;
     - la chaîne d'ampli lit dans la voix VA ce qu'elle lit dans une voix TONE ; DECAY : la voix se tait au bloc où
       TONE se tairait ; hauteur mesurée (VA, KICK, SNARE) : la note, PITCH ; seuils des formes d'onde ; chaque potard
       change le son ;
     - machines d'origine identiques (aucune instruction VA sans piste VA) ; machine locks ; 6 pistes VA ; pistes VA
       mêlées aux machines d'origine.
  5. Avec Model-TG : la même passerelle (3 et 4), plus ah_noenv (Attack, Filtre/Résonance, rééchantillonnage) une
     fois par bloc de piste VA, avec la sortie attendue ; Sampler et machines d'origine identiques à Model-TG seul ;
     VA avec Model-TG = VA seule (Attack 0, filtre ouvert) ; Attack et Filtre agissent sur les pistes VA.
  6. --david (facultatif) : le firmware de David, exécuté. Ses fonctions de rendu (à ses adresses, avec ses tables)
     = va_ref en mode « david » au bit près, état à ses adresses compris ; notre code compilé = le sien au bit près
     hors des débordements du VA HIHAT (notes aiguës), qui sont exactement les écarts trouvés ; dans la boucle des
     voix, son firmware et le nôtre (va-tg) : même tampon à 96 kHz et même sortie de piste, bloc par bloc, tant que
     les deux voix sont calculées ; coût comparé.
  7. Coût : instructions par bloc (VA, KICK, SNARE, HIHAT ; TONE ; MACRO si son tweak est là), voix muette, pile.
  8. Avec d'autres mods (--with) : démarrage, machines d'origine identiques aux mêmes mods sans VA, VA identique à
     VA seule (ou avec Model-TG seul, si model-tg-st est dans la liste), machine locks, pistes mêlées.

    python3 tools/emu/test_va.py --cycles model-cycles_OS1.13.syx [--quick] \
        [--david firmware/david/Model-TG-VA-DR-v1.syx] [--with model-tg-st,arp,tempo-max]

Durée : environ 15 min, 6 min avec --quick, plus 5 min avec --david et autant avec --with.
"""
import argparse
import json
import pathlib
import random
import struct
import sys

import numpy as np
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_UNMAPPED
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import gen_syntakt_engines as gs    # noqa: E402
import gen_va as gv                 # noqa: E402
import mcengine as E                # noqa: E402
import test_model_tg as TM          # noqa: E402
import test_model_tg_syntakt as tms  # noqa: E402
import test_sdvintage as T          # noqa: E402
import test_sdvintage_7th as t7     # noqa: E402
import test_syntakt_machines as tsm  # noqa: E402
import va_ref as R                  # noqa: E402

DEV = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13"
BASE = E.BASE
A7 = mk.UC_M68K_REG_A7
check = t7.check                    # échecs : t7.FAIL (et tms.FAIL pour l'interface avec Model-TG)

# ce que la passerelle appelle dans l'OS (tools/machines/va/va.c)
DECIMATE, TONE_UPDATE, TONE_BUF = 0x400a9f58, 0x400aa7b8, 0x8000c05c
# chaîne d'ampli de l'OS, appelée par la passerelle comme par TONE : fonctions sans appel (début, fin)
AMP = ((0x400a9252, 0x400a9302), (0x400a9430, 0x400a9498), (0x400a967a, 0x400a9756))
TONE = 4
OFF = 12                            # machine hors limites (seules ou avec Model-TG) : la voix n'est pas calculée
KNOBS = ("color", "shape", "sweep", "contour")
BASE_KW = dict(note=60, pitch=64, punch=0, gate=0, finetune=64)
NAMES = [m["name"] for m in gv.MACHINES]


def load(name):
    return json.loads((DEV / name).read_text(encoding="utf-8"))


def kw_of(i, **over):
    """Réglages de la machine VA i (0..3) : ses défauts (potards, Amp Decay), puis over."""
    m = gv.MACHINES[i]
    kw = dict(BASE_KW, decay=m["decay"], **{k: d for k, (_, _, d) in zip(KNOBS, m["knobs"])})
    kw.update(over)
    return kw


class Fw:
    """Un firmware : MAIN OS (avec ce qui est ajouté après), et la charge utile des machines VA telle qu'en mémoire."""

    def __init__(self, stock, tweaks):
        p, _ = build.apply_writes(stock, tweaks)
        pl, _ = build.build_payload(tweaks, stock, None)
        self.img, self.tweaks = bytes(p) + pl, tweaks
        tg = [t for t in tweaks if t["id"].startswith("model-tg")]
        self.tg = tg[0] if tg else None
        self.blob_end = BASE + len(stock) + tg[0]["append"]["size"] if tg else None
        ours = [t for t in tweaks if t["id"] in ("va", "va-tg")]
        self.payload = None
        if not ours:
            return
        tw = self.tweak = ours[0]
        ap_ = tw["append"]
        self.pay = int(ap_["dest"], 16)
        self.runtime = build.payload_runtime(tw, stock, None)
        self.payload = (self.pay, self.runtime)
        self.code_end = self.pay + len(ap_["parts"][0]["hex"]) // 2          # code et tables de va.c
        self.first = gs.TG_FIRST if tg else 6
        self.nm = self.first + gv.N
        self.idx = list(range(self.first, self.nm))
        self.sym = {k: int(v, 16) for k, v in tw["symbols"].items()}
        data = self.pay + gs.LAYOUT["DATA"]
        u32 = lambda va: struct.unpack_from(">I", self.runtime, va - self.pay)[0]
        upd = [u32(data + 4 * self.nm + 4 * i) for i in self.idx]
        rnd = [u32(data + 8 * self.nm + 4 * i) for i in self.idx]
        if upd != [self.sym["va_update"]] * gv.N or rnd != [self.sym[m["render"]] for m in gv.MACHINES]:
            raise SystemExit("!! tables update/render de la charge utile")
        self.kind_of = {a: k for k, a in enumerate(rnd)}
        self.seeds = (u32(self.sym["va_seed"]), u32(self.sym["dr_seed"]))
        self.ah_noenv = int(self.tg["symbols"]["ah_noenv"], 16) if tg else None

    def engine(self, keep=None):
        """keep : les pistes calculées (les autres : machine hors limites, rien n'est calculé)."""
        if self.blob_end:
            e = TM.engine(self.img, end=self.blob_end, payload=self.payload)
        else:
            e = E.Engine(self.img, payload=self.payload)
        if keep is not None:
            for t in range(6):
                if t not in keep:
                    e.uc.mem_write(E.VOICE0 + t * E.VSTRIDE, struct.pack(">II", OFF, OFF))
        return e


# --- 1. démarrage ----------------------------------------------------------------------------------------------
def boot(fw, tg=None):
    """Le crochet de démarrage, exécuté pour de vrai : seul, au début de la remise à zéro du BSS (0x400004b2, jusqu'à
    son retour) ; avec Model-TG, par le jsr de 0x40000530, jusqu'à boot_extra_hook de Model-TG (test_macro.boot)."""
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
        uc.reg_write(A7, sp0)
        uc.emu_start(gs.BOOT_CALL, tg["boot_extra_hook"], count=5_000_000)
        pc, sp = uc.reg_read(mk.UC_M68K_REG_PC), uc.reg_read(A7)
        ret = struct.unpack(">I", uc.mem_read(sp, 4))[0]
        regs = all(uc.reg_read(r) == v for r, v in keep.items())
        check(pc == tg["boot_extra_hook"] and sp == sp0 - 4 and ret == gs.BOOT_CALL + 6 and regs and not bad,
              f"jsr 0x40000530 -> notre crochet -> boot_extra_hook {tg['boot_extra_hook']:#x}, pile et d2..d7/a2..a6 "
              "intactes")
        check(bytes(uc.mem_read(BASE, len(fw.img))) == fw.img, "image (OS, Model-TG, nos morceaux) inchangée")
    else:
        uc.mem_write(sp0, struct.pack(">I", E.STOP))
        uc.reg_write(A7, sp0)
        uc.emu_start(0x400004b2, E.STOP, count=100_000_000)
        regs = all(uc.reg_read(r) == v for r, v in keep.items())
        tail = BASE + E.IMAGE_LEN
        cleared = not any(uc.mem_read(tail, len(fw.img) - E.IMAGE_LEN)) and not any(uc.mem_read(0x42338000, 0xb0))
        check(uc.reg_read(mk.UC_M68K_REG_PC) == E.STOP and uc.reg_read(A7) == sp0 + 4 and regs and cleared
              and not bad, "0x400004b2 -> notre crochet -> remise à zéro du BSS de l'OS (nos morceaux rangés compris), "
                           "retour normal, d2..d7/a2..a6 intacts")
    got = bytes(uc.mem_read(dst, len(rt)))
    packed = sum(n for _, n in fw.tweak["append"]["pack"])
    check(got == rt, f"charge utile reconstituée à {dst:#x} : {len(rt)} o (code et tables, détours, données, puis "
                     f"les variables à zéro), rangée en {packed} o dans l'image")
    check(bytes(uc.mem_read(0x80000000, 0x10000)) == bytes(sram), "SRAM intacte")
    end = BASE + len(fw.img)
    check(end <= gs.END_LIMIT, f"image décompressée jusqu'à {end:#x} (limite {gs.END_LIMIT:#x})")


# --- 2. interface ----------------------------------------------------------------------------------------------
def interface_alone(stock, fw):
    """Les vérifications de test_syntakt_machines.py, pour 4 machines ajoutées."""
    tsm.SAFE = True
    tsm.ADDED = [dict(m, code=f"va{i}", index=6 + i) for i, m in enumerate(gv.MACHINES)]
    tsm.N, tsm.NM, tsm.TOP = gv.N, 6 + gv.N, 5 + gv.N
    tsm.FIRST = {6 + i: 76 + 5 * i for i in range(gv.N)}
    tsm.REC = {6 + i: gs.RECS + 0x60 * i for i in range(gv.N)}
    tsm.ROWS, tsm.CCROWS = gs.ROWSN, gs.CCROWSN
    tsm.NAMES = ["Kick", "Snare", "Metal", "Perc", "Tone", "Chord"] + NAMES
    patched, payload = fw.img, fw.runtime
    a, b = tsm.tables(stock, patched, payload)
    tsm.lookups(a, b)
    tsm.accessors(a, b, stock, patched)
    tsm.screens(stock, patched, payload)
    tsm.setter_and_wheel(stock, patched, payload)
    tsm.records_and_change(stock, patched, payload)
    tsm.out_of_range(stock, patched, payload)
    tsm.small_icon(stock, patched, payload)
    name_width(fw)


def name_width(fw):
    """Les noms sur l'écran MACHINES (texte centré à x = 32, police 5x9 : 6 points par caractère) : dans la moitié
    gauche (64 points), sans toucher les repères de la moitié droite."""
    ok, shown = True, []
    for m, want in zip(fw.idx, NAMES):
        calls = tms.machines_screen(fw, m) if fw.tg else screen_alone(fw, m)
        txt = [a for k, a in calls if k == "texte"]
        marks = [a[1] for k, a in calls if k.startswith("repère")]
        if len(txt) != 1 or not marks:
            ok = False
            continue
        x, w = txt[0][2], 6 * len(want) - 1          # (this, ?, x, y, alignement, police, texte)
        lo = x - w // 2
        ok &= x == 32 and lo >= 0 and lo + w <= 64 <= min(marks)
        shown.append(f"{want} x = {lo}..{lo + w - 1}")
    check(ok and len(shown) == gv.N, f"noms de l'écran MACHINES centrés à x = 32 dans la moitié gauche ({', '.join(shown)} ;"
                                     " repères à partir de x = 64)")


def screen_alone(fw, m):
    """Appels de dessin de l'écran MACHINES pour la machine m, sans Model-TG (tms.machines_screen, avec t7.UI)."""
    u = t7.UI(fw.img, fw.runtime)
    u.hooks = {0x40071a04: "texte", 0x40071da4: "image", 0x40070c4e: "repère", 0x40070efc: "repère plein",
               0x93000000: "a5", 0x93000010: "a4"}
    for a_ in (0x93000000, 0x93000010):
        u.uc.mem_write(a_, b"\x4e\x75")
    u.uc.mem_write(0x40fe32cc, struct.pack(">I", 0x92000000))
    u.uc.mem_write(0x40fe384c, struct.pack(">I", 0x92100000))
    u.uc.mem_write(0x91001000 + 108, struct.pack(">I", 0x91002000))
    sp = t7.STACK - 0x800
    u.uc.mem_write(sp, struct.pack(">I", t7.STOP) * 64)
    for r, v in {mk.UC_M68K_REG_D3: m, mk.UC_M68K_REG_D2: 0x91000000, mk.UC_M68K_REG_A2: 0x91001000,
                 mk.UC_M68K_REG_A5: 0x93000000, mk.UC_M68K_REG_A4: 0x93000010, A7: sp}.items():
        u.uc.reg_write(r, v)
    u.uc.emu_start(0x400a25e0, t7.STOP, count=1_000_000)
    return u.calls


def interface_tg(ref_tg, fw, tg):
    """Les vérifications de test_model_tg_syntakt.py (qui lit 6 octets par nom), puis les noms en entier."""
    codes = [f"va{i}" for i in range(gv.N)]
    for c, m in zip(codes, gv.MACHINES):
        gs.CATALOG[c] = dict(m, name=m["name"][:6])
    tms.interface(ref_tg, fw, codes, tg)
    for c in codes:
        del gs.CATALOG[c]
    b = tms.UI(fw)
    names = bytes(b.uc.mem_read(gs.DATA, 4 * fw.nm))
    strs = [bytes(b.uc.mem_read(struct.unpack_from(">I", names, 4 * m)[0], 16)).split(b"\0")[0].decode()
            for m in fw.idx]
    check(strs == NAMES, f"noms entiers des machines {[m + 1 for m in fw.idx]} : {strs}")
    name_width(fw)


# --- 3. le code seul -------------------------------------------------------------------------------------------
class Code:
    """Le code compilé de la charge utile, exécuté seul (sans l'OS) : va_fill, va_post."""
    STOP = 0x9001fff0
    X = 0x90008000                  # tampon d'échantillons

    def __init__(self, fw):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
        uc.mem_map(fw.pay, (len(fw.runtime) + 0xfffff) & ~0xfffff)
        uc.mem_write(fw.pay, fw.runtime)
        uc.mem_map(0x90000000, 0x20000)
        uc.mem_write(self.STOP, b"\x4e\x71\x4e\x71")
        self.bad, self.fw, self.n = [], fw, 0
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: self.bad.append(addr) or False)

    def call(self, fn, *args):
        sp = 0x90010000 - 0x100
        self.uc.mem_write(sp, struct.pack(">I" + "I" * len(args), self.STOP, *[a & 0xffffffff for a in args]))
        self.uc.reg_write(A7, sp)
        self.uc.emu_start(fn, self.STOP, count=2_000_000)
        return self.uc.reg_read(A7) == sp + 4

    def trk_at(self, t):
        return self.fw.sym["va_trk"] + R.TRK_SIZE * t

    def track(self, t):
        return R.Track.unpack(bytes(self.uc.mem_read(self.trk_at(t), R.TRK_SIZE)))

    def set_track(self, t, tr):
        self.uc.mem_write(self.trk_at(t), tr.pack())

    def seeds(self):
        g = lambda s: struct.unpack(">I", self.uc.mem_read(self.fw.sym[s], 4))[0]
        return g("va_seed"), g("dr_seed")

    def fill(self, t, step, kind):
        ok = self.call(self.fw.sym["va_fill"], self.X, self.trk_at(t), step, kind)
        self.n += 1
        return list(struct.unpack(">64i", self.uc.mem_read(self.X, 256))), ok

    def post(self, buf, kind):
        self.uc.mem_write(self.X, struct.pack(">32I", *[R.u32(w) for w in buf]))
        ok = self.call(self.fw.sym["va_post"], self.X, kind)
        return list(struct.unpack(">32i", self.uc.mem_read(self.X, 128))), ok


STEPS = (0, 1, 0x10000, 2048, 0x8000, 0x20000, 0x40000, 0x80000, 0x100000, 0x200000, 0x31c000, 0x400000, 0xffffff,
         0x1000000, 0x3fffffff, 0xffffffff)


def note_step(n):
    """Pas Q16 d'une note (60 : 1,0) comme le calcule la passerelle d'après la hauteur de TONE (à l'arrondi près)."""
    return int(round(65536 * 2 ** ((n - 60) / 12)))


def unit(fw, label, quick):
    """va_fill et va_post compilés = va_ref, au bit près."""
    rnd = random.Random(53)
    c = Code(fw)
    dsp = R.Dsp(*c.seeds())
    blocks, bad, regs = 0, [], True
    kinds_seen = [0] * 4
    overflow = 0

    def one(t, kind, knobs, step, trig):
        nonlocal blocks, regs
        tr = dsp.trk[t]
        tr.knob, tr.trig = list(knobs), tr.trig | trig
        c.set_track(t, tr)
        got, ok = c.fill(t, step, kind)
        want = dsp.fill(t, step, kind)
        regs &= ok
        blocks += 1
        kinds_seen[kind] += 1
        same = got == want and c.track(t).same(tr) and c.seeds() == (dsp.va_seed, dsp.dr_seed)
        if not same and len(bad) < 5:
            i = next((k for k in range(64) if got[k] != want[k]), None)
            bad.append(f"{KINDS_SHORT[kind]} piste {t} potards {knobs} pas {step:#x} trig {trig} : échantillon {i}")
        return same

    # chaque machine, chaque potard à chaque bout et au milieu, plusieurs notes, une suite de blocs
    n_blk = 3 if quick else 8
    for kind in range(4):
        for k in range(4):
            for v in (0, 1, 42, 43, 63, 64, 85, 86, 126, 127):
                knobs = [m[2] for m in gv.MACHINES[kind]["knobs"]]
                knobs[k] = v
                for step in (0x10000, note_step(24), note_step(96)):
                    for b in range(n_blk):
                        one(rnd.randrange(6), kind, knobs, step, int(b == 0))
    # au hasard : pistes entrelacées, potards et notes qui changent, trigs, pas extrêmes (débordements modulo 2^32)
    t_state = {t: dict(kind=rnd.randrange(4), knobs=[rnd.randrange(128) for _ in range(4)], step=0x10000)
               for t in range(6)}
    for _ in range(600 if quick else 3000):
        t = rnd.randrange(6)
        s = t_state[t]
        r = rnd.random()
        if r < 0.03:
            s["kind"] = rnd.randrange(4)
        if r < 0.15:
            s["knobs"] = [rnd.choice((0, 127, rnd.randrange(128))) for _ in range(4)]
        if r < 0.1:
            s["step"] = rnd.choice((rnd.choice(STEPS), note_step(rnd.randrange(128)), rnd.randrange(1 << 32)))
        if s["kind"] == R.HIHAT and R.Dsp.hihat_overflows(s["step"], s["knobs"][1]):
            overflow += 1
        one(t, s["kind"], s["knobs"], s["step"], int(rnd.random() < 0.05))
    # va_post : 3 batteries, échantillons au hasard, aux bouts, petits
    pb = 0
    for _ in range(100 if quick else 400):
        kind = rnd.randrange(1, 4)
        buf = [rnd.choice((rnd.randrange(-1 << 31, 1 << 31), rnd.randrange(-3000, 3000) << 16,
                           rnd.choice((-1 << 31, (1 << 31) - 1, 0, -1)))) for _ in range(32)]
        got, ok = c.post(buf, kind)
        regs &= ok
        if got != [R.s32(w) for w in R.Dsp.post(buf, kind)]:
            bad.append(f"va_post {KINDS_SHORT[kind]}")
        pb += 1
    check(not bad and regs and not c.bad,
          f"{label} : va_fill compilé = va_ref, échantillon par échantillon, état des pistes et générateurs compris "
          f"({blocks} blocs de 64 : VA {kinds_seen[0]}, KICK {kinds_seen[1]}, SNARE {kinds_seen[2]}, HIHAT "
          f"{kinds_seen[3]}, dont {overflow} dans l'aigu où le firmware de David débordait) ; va_post = va_ref "
          f"({pb} blocs) ; pile rendue, aucun accès hors mémoire {bad[:3]}")


KINDS_SHORT = ("VA", "KICK", "SNARE", "HIHAT")


# --- 4. dans la boucle des voix --------------------------------------------------------------------------------
class Probe:
    """La passerelle observée à chaque bloc, comparée à va_ref (Bridge + Dsp) nourri de ce qu'elle voit : entrée de
    va_update (voix, paramètres), entrée du rendu (voix), appel du décimateur depuis notre code (le tampon à 96 kHz),
    update de TONE appelée depuis notre code, va_post, ah_noenv (avec Model-TG). Toutes les voix (les générateurs
    sont communs aux pistes, comme chez David)."""

    def __init__(self, fw, e):
        self.fw, self.e, self.uc = fw, e, e.uc
        self.dsp = R.Dsp(*fw.seeds)
        self.bridge = R.Bridge(self.dsp)
        self.block, self.recs, self.cur, self.bad = 0, [], {}, []
        self.in_upd = None               # voix dont va_update est en cours (l'update de TONE y est un saut final)
        uc = self.uc
        for a, f in ([(fw.sym["va_update"], self._upd), (DECIMATE, self._dec), (TONE_UPDATE, self._tone),
                      (fw.sym["va_post"], self._post)] + [(a, self._rnd) for a in fw.kind_of]
                     + ([(fw.ah_noenv, self._ah)] if fw.tg else [])):
            uc.hook_add(UC_HOOK_CODE, f, begin=a, end=a)

    def arg(self, k):                    # k = 0 : adresse de retour
        return struct.unpack(">I", self.uc.mem_read(self.uc.reg_read(A7) + 4 * k, 4))[0]

    def ours(self):
        return self.fw.pay <= self.arg(0) < self.fw.code_end

    def voice(self, v):
        t, r = divmod(v - E.VOICE0, E.VSTRIDE)
        return t if r == 0 and 0 <= t < 6 else None

    def _upd(self, uc, a, s, u):
        v, p = self.arg(2), self.arg(3)
        t = self.voice(v)
        vb, pb = bytes(uc.mem_read(v, E.VSTRIDE)), bytes(uc.mem_read(p, 0x40))
        info = self.bridge.update(t, vb, pb)
        rec = dict(block=self.block, t=t, kind=None, uidle=info["idle"], first=info["first"], edge=info["edge"],
                   knobs=list(self.dsp.trk[t].knob), ridle=None, want=None, dec=0, dec_ok=None, tone=0, post=[],
                   pre=None, ah=[], words=[struct.unpack_from(">h", pb, 0x16 + 2 * k)[0] for k in range(4)])
        self.cur[t] = rec
        self.recs.append(rec)
        self.in_upd = v

    def _rnd(self, uc, a, s, u):
        self.in_upd = None
        t = self.voice(self.arg(2))
        rec = self.cur.get(t)
        if rec is None or rec["block"] != self.block or rec["kind"] is not None:
            self.bad.append(f"bloc {self.block} piste {t} : rendu sans update")
            return
        rec["kind"] = self.fw.kind_of[a]
        self.last_rnd = t
        vb = bytes(uc.mem_read(self.arg(2), E.VSTRIDE))
        rec["ridle"] = R.Bridge.idle(vb)
        if not rec["ridle"]:
            rec["step"] = R.step_of(struct.unpack_from(">I", vb, 232)[0])
            rec["want"] = self.dsp.fill(t, rec["step"], rec["kind"])

    def _dec(self, uc, a, s, u):
        if not self.ours():
            return
        t, buf = self.voice(self.arg(1)), self.arg(2)
        rec = self.cur[t]
        rec["dec"] += 1
        x = list(struct.unpack(">64i", uc.mem_read(buf + 32, 256)))
        rec["dec_ok"] = buf == TONE_BUF and rec["want"] is not None and x == rec["want"]
        rec["x"] = x

    def _tone(self, uc, a, s, u):
        if self.in_upd is not None and self.arg(2) == self.in_upd:
            self.cur[self.voice(self.in_upd)]["tone"] += 1

    def _post(self, uc, a, s, u):
        out, kind = self.arg(1), self.arg(2)
        rec = self.cur[self.last_rnd]
        rec["post"].append(kind)
        rec["pre"] = list(struct.unpack(">32i", uc.mem_read(out, 128)))

    def _ah(self, uc, a, s, u):
        t = self.voice(self.arg(2))
        rec = self.cur.get(t)
        if rec is not None and rec["block"] == self.block and rec["kind"] is not None:
            rec["ah"].append(list(struct.unpack(">32i", uc.mem_read(self.arg(1), 128))))

    def end(self, out):
        """Fin d'un bloc : état et générateurs en mémoire = modèle ; sortie (seules) = celle attendue."""
        fw, uc = self.fw, self.uc
        for t in range(6):
            raw = bytes(uc.mem_read(fw.sym["va_trk"] + R.TRK_SIZE * t, R.TRK_SIZE))
            if not R.Track.unpack(raw).same(self.dsp.trk[t]):
                self.bad.append(f"bloc {self.block} piste {t} : état de la piste")
        g = lambda s_: struct.unpack(">I", uc.mem_read(fw.sym[s_], 4))[0]
        if (g("va_seed"), g("dr_seed")) != (self.dsp.va_seed, self.dsp.dr_seed):
            self.bad.append(f"bloc {self.block} : générateurs")
        for rec in (r for r in self.recs if r["block"] == self.block):
            rec["out"] = out[rec["t"]].copy()

    def verdict(self):
        """Écarts (liste) et compteurs."""
        bad = list(self.bad)
        n = dict(blocks=0, computed=0, idle=0, first=0, edge=0, post=0, ah=0)
        for r in self.recs:
            where = f"bloc {r['block']} piste {r['t']}"
            n["blocks"] += 1
            if r["kind"] is None:
                bad.append(f"{where} : update sans rendu")
                continue
            n["first"] += r["first"]
            n["edge"] += r["edge"]
            computed = not r["ridle"]
            n["computed" if computed else "idle"] += 1
            if r["uidle"] != r["ridle"]:
                bad.append(f"{where} : muette à l'update {r['uidle']}, au rendu {r['ridle']}")
            if r["tone"] != (0 if r["uidle"] else 1):
                bad.append(f"{where} : update de TONE {r['tone']} fois")
            if r["dec"] != int(computed) or (computed and not r["dec_ok"]):
                first = None
                if r.get("x") and r["want"]:
                    first = next((k for k in range(64) if r["x"][k] != r["want"][k]), None)
                bad.append(f"{where} {KINDS_SHORT[r['kind']]} : tampon à 96 kHz (décimateur {r['dec']}, 1er écart "
                           f"{first})")
            if r["knobs"] != [R.dial(w) for w in r["words"]]:
                bad.append(f"{where} : potards {r['knobs']}")
            want_post = [r["kind"]] if computed and r["kind"] != R.VA else []
            if r["post"] != want_post:
                bad.append(f"{where} : va_post {r['post']}")
            n["post"] += len(r["post"])
            exp = None                   # sortie de la passerelle (avant ah_noenv) : nulle si muette, post si batterie
            if not computed:
                exp = [0] * 32
            elif r["kind"] != R.VA and r["pre"] is not None:
                exp = [R.s32(w) for w in R.Dsp.post(r["pre"], r["kind"])]
            if self.fw.tg:
                n["ah"] += len(r["ah"])
                if len(r["ah"]) != 1 or (exp is not None and r["ah"][0] != exp):
                    bad.append(f"{where} : ah_noenv {len(r['ah'])} fois, sortie attendue {exp is not None}")
            elif exp is not None and "out" in r and not np.array_equal(r["out"], np.array(exp, np.int64) >> 1):
                bad.append(f"{where} : sortie de piste")
        return bad, n


def run(fw, setup, blocks, trigs, changes=None, probe=True, keep=None):
    """setup : {piste : réglages} (les autres : hors limites, pas calculées, sauf keep) ; trigs : {bloc : masque} ;
    changes : {bloc : {piste : réglages}}. Rend (sorties [bloc, piste, 32], sonde, moteur)."""
    e = fw.engine(keep=set(setup) if keep is None else keep)
    for t, kw in setup.items():
        e.set(t, **kw)
    pr = Probe(fw, e) if probe and fw.payload else None
    out = []
    for b in range(blocks):
        for t, kw in (changes or {}).get(b, {}).items():
            e.set(t, **kw)
        if pr:
            pr.block = b
        out.append(e.block(trigs.get(b, 0)))
        if pr:
            pr.end(out[-1])
    return np.stack(out), pr, e


def cases(fw, quick):
    """(nom, machine 0..3, réglages, trigs, changements, blocs)."""
    out = [(f"{NAMES[i]} défauts", i, kw_of(i), (1, 70), None, 140) for i in range(4)]
    waves = [(0, 0), (64, 64), (127, 127)] if quick else [(a, b) for a in (0, 64, 127) for b in (0, 64, 127)]
    out += [(f"VA Osc1 Wave {a}, Osc2 Wave {b}", 0, kw_of(0, color=a, shape=b), (1,), None, 40) for a, b in waves]
    extremes = []
    for i in range(4):
        for k, (long_, _, d) in enumerate(gv.MACHINES[i]["knobs"]):
            for v in ((0, 127) if not quick else (0 if d >= 64 else 127,)):
                extremes.append((f"{NAMES[i]} {long_} {v}", i, kw_of(i, **{KNOBS[k]: v}), (1,), None, 40))
    out += extremes
    for i in range(4) if not quick else (0, 3):
        out += [(f"{NAMES[i]} note 24", i, kw_of(i, note=24), (1,), None, 40),
                (f"{NAMES[i]} note 108", i, kw_of(i, note=108), (1,), None, 40)]
    out += [
        ("VA PITCH 0, note 0 : en bas", 0, kw_of(0, pitch=0, note=0), (1,), None, 30),
        ("VA PITCH 127, note 127 : en haut", 0, kw_of(0, pitch=127, note=127), (1,), None, 30),
        ("VA HIHAT note 96, Spread 127 (David : débordement)", 3, kw_of(3, note=96, shape=127), (1,), None, 30),
        ("VA potards qui bougent à chaque bloc", 0, kw_of(0, decay=100), (1,),
         {b: {k: (s * b + o) % 128 for k, s, o in zip(KNOBS, (7, 13, 5, 3), (0, 9, 30, 60))} for b in range(90)}, 90),
        ("VA KICK potards qui bougent à chaque bloc", 1, kw_of(1, decay=100), (1, 30, 60),
         {b: {k: (s * b + o) % 128 for k, s, o in zip(KNOBS, (5, 11, 3, 7), (0, 9, 30, 60))} for b in range(90)}, 90),
        ("VA retrig tous les 3 blocs", 0, kw_of(0), tuple(range(1, 60, 3)), None, 70),
        ("VA SNARE retrig à chaque bloc", 2, kw_of(2), tuple(range(1, 30)), None, 40),
        ("VA PUNCH", 0, kw_of(0, punch=1), (1,), None, 60),
        ("VA KICK PUNCH", 1, kw_of(1, punch=1), (1,), None, 60),
        ("VA GATE", 0, kw_of(0, gate=1, decay=20), (1,), {50: {"gate": 0}}, 120),
        ("VA DECAY 10 : se tait, puis repart", 0, kw_of(0, decay=10), (1, 150), None, 190),
        ("VA HIHAT DECAY 5 : se tait, puis repart", 3, kw_of(3, decay=5), (1, 100), None, 130),
        ("VA -> VA KICK -> VA HIHAT au trig (machine lock)", 0, kw_of(0, decay=60), (1, 40, 80),
         {40: {"machine": fw.idx[1], **kw_of(1)}, 80: {"machine": fw.idx[3], **kw_of(3)}}, 120),
    ]
    return out


def exact(fw, todo, label):
    """Bloc par bloc, la passerelle = va_ref ; une voix muette n'est pas calculée."""
    bad, tot, peaks = [], dict(blocks=0, computed=0, idle=0, first=0, edge=0, post=0, ah=0), []
    for name, i, kw, trigs, changes, blocks in todo:
        ch = {b: {0: c} for b, c in (changes or {}).items()}
        x, pr, e = run(fw, {0: dict(kw, machine=fw.idx[i])}, blocks, {b: 1 for b in trigs}, ch)
        errs, n = pr.verdict()
        for k in tot:
            tot[k] += n[k]
        peak = int(np.abs(x[:, 0]).max())
        peaks.append(peak)
        if errs or e.unmapped or peak < 1 << 16 or n["first"] < 1:
            bad.append(name)
            print(f"        ECART {name} : {errs[:3]} hors mémoire {e.unmapped[:2]} crête {peak} 1ers blocs {n['first']}")
    check(not bad, f"{label} : à chaque bloc, le tampon à 96 kHz donné au décimateur = va_ref nourri de ce que voit la "
                   f"passerelle, état et générateurs identiques, potards lus = réglés ({len(todo)} cas, {tot['blocks']} "
                   f"blocs, crêtes {min(peaks):.2g} à {max(peaks):.2g}) {bad[:4]}")
    check(not bad and tot["idle"] > 0, f"{label} : {tot['computed']} blocs calculés, {tot['idle']} blocs de voix "
          f"muette (ni update de TONE, ni rendu, sortie nulle) ; {tot['first']} 1ers blocs sur une machine VA "
          f"(état remis à zéro, note jouée), {tot['edge']} fronts de trig ; va_post sur chaque bloc de batterie "
          f"({tot['post']})" + (f" ; ah_noenv une fois par bloc ({tot['ah']}), sortie attendue" if fw.tg else
                                " ; sortie de piste = sortie attendue / 2"))


def amp_like_tone(fw):
    """La chaîne d'ampli (enveloppe, VCA, PUNCH) lit dans une voix VA exactement ce qu'elle lit dans une voix TONE,
    bloc par bloc, tant que la voix VA est calculée."""
    def reads(idx, kw, changes):
        e = fw.engine(keep={0})
        e.set(0, machine=idx, **kw)
        v, got, b = E.VOICE0, [], [0]

        def hk(uc, access, addr, size, value, ud):
            pc = uc.reg_read(mk.UC_M68K_REG_PC)
            if any(lo <= pc < hi for lo, hi in AMP):
                got.append((b[0], addr - v, bytes(uc.mem_read(addr, size))))
        e.uc.hook_add(UC_HOOK_MEM_READ, hk, begin=v, end=v + E.VSTRIDE - 1)
        idle = None
        for b[0] in range(120):
            for k, val in (changes or {}).get(b[0], {}).items():
                e.set(0, **{k: val})
            e.block(1 if b[0] in (1, 40) else 0)
            vb = bytes(e.uc.mem_read(v, E.VSTRIDE))
            if idle is None and b[0] > 41 and R.Bridge.idle(vb):
                idle = b[0] + 1
        return got, idle, e.unmapped
    res = []
    for i, kw in ((0, dict(decay=30)), (0, dict(decay=90, punch=1)), (1, dict(decay=60, gate=1)),
                  (2, dict(decay=127, punch=1, gate=1)), (3, dict(decay=50))):
        k = kw_of(i, **kw)
        changes = {60: {"gate": 0}} if kw.get("gate") else None
        rt, _, _ = reads(TONE, k, changes)
        rv, stop, unm = reads(fw.idx[i], k, changes)
        stop = stop or 120
        rt = [x for x in rt if x[0] < stop]
        rv = [x for x in rv if x[0] < stop]
        res.append((rt == rv and len(rv) > 0 and not unm, stop, len({o for _, o, _ in rv})))
    check(all(ok for ok, _, _ in res), f"chaîne d'ampli : mêmes lectures de la voix que TONE (DECAY, PUNCH, GATE ; "
          f"{res[0][2]} champs ; VA, KICK, SNARE, HIHAT), bloc par bloc jusqu'au silence (blocs {[s for _, s, _ in res]})")


def computed(fw, setup, blocks, trigs):
    """Sorties, et blocs où la piste 0 est calculée (décimateur appelé depuis notre code), sans le modèle."""
    e = fw.engine(keep=set(setup))
    for t, kw in setup.items():
        e.set(t, **kw)
    seen, b = set(), [0]

    def dec(uc, a, s, u):
        sp = uc.reg_read(A7)
        ret, v = struct.unpack(">II", uc.mem_read(sp, 8))
        if fw.pay <= ret < fw.code_end and v == E.VOICE0:
            seen.add(b[0])
    e.uc.hook_add(UC_HOOK_CODE, dec, begin=DECIMATE, end=DECIMATE)
    out = []
    for b[0] in range(blocks):
        out.append(e.block(trigs.get(b[0], 0)))
    return np.stack(out), seen, e


def decay_like_tone(fw, quick):
    """DECAY = la décroissance du volume, celle de TONE : la voix VA se tait au bloc où l'enveloppe d'ampli d'une voix
    TONE réglée pareil passe sous le seuil (et plus tard quand DECAY monte). Mesuré sur TONE : DECAY 5 -> 22 blocs,
    20 -> 422, 40 -> 2233 (1,5 s) ; on s'arrête à 28, au-delà la preuve devient longue sans rien montrer de plus."""
    rows, ok, limit = [], True, 1500
    for d in (5, 20) if quick else (5, 12, 20, 28):
        e = fw.engine(keep={0})
        e.set(0, machine=TONE, **kw_of(0, decay=d))
        tone_idle = None
        for b in range(limit):
            e.block(1 if b == 1 else 0)
            if b > 2 and R.Bridge.idle(bytes(e.uc.mem_read(E.VOICE0, E.VSTRIDE))):
                tone_idle = b + 1
                break
        if tone_idle is None:
            check(False, f"DECAY {d} : la voix TONE ne se tait pas en {limit} blocs")
            return
        got = []
        for i in range(4):
            n = tone_idle + 3
            x, seen, e2 = computed(fw, {0: dict(kw_of(i, decay=d), machine=fw.idx[i])}, n, {1: 1})
            first_idle = next((b for b in range(3, n) if b not in seen), None)
            got.append(first_idle)
            ok &= not e2.unmapped and first_idle is not None and x[2:first_idle, 0].any() and not x[first_idle:, 0].any()
        ok &= all(g == tone_idle for g in got)
        rows.append((d, tone_idle, got))
    ok &= all(a[1] < b[1] for a, b in zip(rows, rows[1:]))
    check(ok, "DECAY : la voix VA (les 4 machines) se tait au bloc où TONE passerait sous le seuil, et plus tard quand "
              "DECAY monte (DECAY -> bloc, 1 bloc = 0,67 ms : " + ", ".join(f"{d} -> {t}" for d, t, _ in rows) + ")")


def f0(x, lo, hi):
    """Fréquence du plus grand pic du spectre entre lo et hi (Hz), interpolée."""
    x = x.astype(float) - np.mean(x)
    n = 1 << 19
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)), n))
    f = np.fft.rfftfreq(n, 1 / 48000)
    m = np.flatnonzero((f > lo) & (f < hi))
    i = m[np.argmax(X[m])]
    a, b, c = np.log(X[i - 1:i + 2] + 1e-12)
    return (i + 0.5 * (a - c) / (a - 2 * b + c)) * 48000 / n


def pitch(fw):
    """La hauteur suit la note et PITCH (1 demi-ton par pas) : VA (Osc Mix 0, scie : l'oscillateur 1 seul), KICK
    (sans balayage ni click : 55 Hz à la note 60), SNARE (sans bruit ni chute : 180 Hz à la note 60)."""
    rows, worst = [], 0.0
    plan = [(0, dict(contour=0, color=0, decay=127), 261.63, [(36, 64), (48, 64), (60, 64), (72, 64), (84, 64),
                                                                (96, 64), (60, 52), (60, 76), (66, 64)], 4, 200),
            (1, dict(color=0, sweep=0, shape=0, contour=0, decay=127), 261.63 * 3444 / 16384,
             [(48, 64), (60, 64), (72, 64), (84, 64), (60, 76)], 6, 300),
            (2, dict(color=0, shape=0, contour=0, decay=127), 261.63 * 11272 / 16384,
             [(48, 64), (60, 64), (72, 64), (60, 70)], 3, 90)]
    ok = True
    for i, kw, f60, notes, b0, b1 in plan:
        got = []
        for note, p in notes:
            x, _, e = run(fw, {0: dict(kw_of(i, **kw), note=note, pitch=p, machine=fw.idx[i])}, b1, {1: 1},
                          probe=False)
            want = f60 * 2 ** ((note + p - 64 - 60) / 12)
            f = f0(x[b0:b1, 0].reshape(-1), want / 1.4, want * 1.4)
            err = f / want - 1
            worst = max(worst, abs(err))
            ok &= abs(err) < 0.004 and not e.unmapped
            got.append(f"{note}/{p}: {f:.1f}")
        rows.append(f"{NAMES[i]} ({', '.join(got)} Hz)")
    check(ok, f"hauteur mesurée = note et PITCH (note/PITCH : Hz), écart au plus {100 * worst:.2f} % : " + " ; ".join(rows))


def knobs_matter(fw):
    """Chaque potard change le son ; les seuils des formes d'onde (0..42 scie, 43..85 carré, 86..127 triangle)."""
    def track(i, **kw):
        x, _, e = run(fw, {0: dict(kw_of(i, decay=60), machine=fw.idx[i], **kw)}, 50, {1: 1}, probe=False)
        return x[:, 0], e.unmapped
    ok, moved = True, []
    for i in range(4):
        base, unm = track(i)
        ok &= not unm and base.any()
        for k, (long_, short, d) in enumerate(gv.MACHINES[i]["knobs"]):
            other, _ = track(i, **{KNOBS[k]: 0 if d >= 64 else 127})
            ok &= not np.array_equal(base, other)
            moved.append(short)
    same = []
    for a, b in ((0, 42), (43, 85), (86, 127)):
        for k in (0, 1):
            x, _ = track(0, **{KNOBS[k]: a})
            y, _ = track(0, **{KNOBS[k]: b})
            same.append(np.array_equal(x, y))
    diff = [not np.array_equal(track(0, color=a)[0], track(0, color=b)[0]) for a, b in ((42, 43), (85, 86))]
    check(ok and all(same) and all(diff), f"chaque potard change le son ({len(moved)} : {', '.join(moved)}) ; Osc1 et Osc2 "
                                          "Wave : 0 = 42 (scie), 43 = 85 (carré), 86 = 127 (triangle), 42 != 43, 85 != 86")


def stock_unchanged(ref_fw, fw, label):
    """6 pistes sur les machines d'origine (2 trigs) : identiques, et aucune instruction de va.c."""
    def go(f, hook):
        e = f.engine()
        for t in range(6):
            e.set(t, **dict(BASE_KW, machine=t, color=64, shape=64, sweep=64, contour=64, decay=60))
        ran = []
        if hook:
            e.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: ran.append(a), begin=f.pay, end=f.code_end - 1)
        x = np.stack([e.block(0x3f if b in (1, 150) else 0) for b in range(300)])
        return x, ran, e.unmapped
    r, _, _ = go(ref_fw, False)
    x, ran, unm = go(fw, True)
    check(np.array_equal(r, x) and np.abs(x).max() > 1e7 and not ran and not unm,
          f"6 machines d'origine : identiques à {label}, échantillon par échantillon, sans une instruction de va.c")


def like(a_fw, b_fw, label):
    """Sortie finale de chaque machine VA identique dans deux firmwares."""
    bad = []
    for i in range(4):
        kw = kw_of(i, decay=40)
        a, _, _ = run(a_fw, {0: dict(kw, machine=a_fw.idx[i])}, 200, {1: 1, 120: 1}, probe=False)
        b, _, e = run(b_fw, {0: dict(kw, machine=b_fw.idx[i])}, 200, {1: 1, 120: 1}, probe=False)
        if not np.array_equal(a[:, 0], b[:, 0]) or e.unmapped or not a.any():
            bad.append(NAMES[i])
    check(not bad, f"{label}, sortie finale de la piste (VA, VA KICK, VA SNARE, VA HIHAT) {bad}")


def locks(fw, label):
    """Machine locks sur une piste : SNARE, VA, TONE, VA KICK, VA SNARE, VA HIHAT, VA, KICK : tout joue, chaque
    bloc VA = va_ref, chaque arrivée sur une machine VA = un 1er bloc."""
    seq = [dict(machine=1), dict(machine=fw.idx[0], **kw_of(0)), dict(machine=TONE), dict(machine=fw.idx[1], **kw_of(1)),
           dict(machine=fw.idx[2], **kw_of(2)), dict(machine=fw.idx[3], **kw_of(3)),
           dict(machine=fw.idx[0], **kw_of(0, color=127)), dict(machine=0)]
    x, pr, e = run(fw, {0: dict(BASE_KW, machine=1, decay=40)}, 60 * len(seq), {60 * k + 1: 1 for k in range(len(seq))},
                   {60 * k: {0: s} for k, s in enumerate(seq)})
    parts = [int(np.abs(x[60 * k + 2:60 * k + 60, 0]).max()) for k in range(len(seq))]
    errs, n = pr.verdict()
    check(all(p > 1e6 for p in parts) and not e.unmapped and not errs and n["first"] == 5,
          f"{label} : machine locks SNARE -> VA -> TONE -> VA KICK -> VA SNARE -> VA HIHAT -> VA -> KICK sur une piste : "
          f"tout joue (crêtes {[f'{p:.2g}' for p in parts]}), chaque bloc VA = va_ref, {n['first']} 1ers blocs {errs[:2]}")


def six_tracks(fw, label):
    """6 pistes VA ensemble (générateurs communs) : chaque bloc de chaque piste = va_ref."""
    mach = [0, 1, 2, 3, 0, 1]
    setup = {t: dict(kw_of(i, note=48 + 5 * t, color=64 if t == 4 else kw_of(i)["color"]), machine=fw.idx[i])
             for t, i in enumerate(mach)}
    x, pr, e = run(fw, setup, 160, {1: 0x3f, 60: 0x15, 100: 0x3f})
    errs, n = pr.verdict()
    peaks = [int(np.abs(x[:, t]).max()) for t in range(6)]
    check(not errs and not e.unmapped and min(peaks) > 1e6,
          f"{label} : 6 pistes VA ensemble (VA, KICK, SNARE, HIHAT, VA, KICK), {n['computed']} blocs calculés, chacun = "
          f"va_ref (générateurs communs aux pistes, comme chez David) {errs[:2]}")


def mixed(fw, ref_fw, label, sampler=False):
    """VA mêlée aux autres machines : les pistes d'origine (et le Sampler de Model-TG) identiques au même firmware
    sans VA, chaque bloc VA = va_ref."""
    trigs = {1: 0x3f, 150: 0x3f}
    mach = [0, fw.idx[0], 6 if sampler else 2, 5, fw.idx[3], TONE]
    vat = {1: 0, 4: 3}
    setup = {t: (dict(kw_of(vat[t], decay=40), machine=m) if t in vat else
                 dict(BASE_KW, machine=m, color=64, shape=64, sweep=64, contour=64, decay=40)) for t, m in enumerate(mach)}
    x, pr, e = run(fw, setup, 300, trigs)
    r, _, e_r = run(ref_fw, {t: dict(kw, machine=0 if t in vat else kw["machine"]) for t, kw in setup.items()}, 300,
                    trigs)
    errs, n = pr.verdict()
    ok = not e.unmapped and not e_r.unmapped and not errs and all(x[:, t].any() for t in vat)
    for t in range(6):
        if t not in vat:
            ok &= np.array_equal(x[:, t], r[:, t])
    if sampler:
        ok &= not x[:, 2].any()
    check(ok, f"{label} : pistes {[m + 1 for m in mach]} ensemble ; machines d'origine"
              f"{', Sampler sans échantillon (muet)' if sampler else ''} identiques sans VA, chaque bloc VA = va_ref "
              f"{errs[:2]}")


def attack_filter(fw):
    """Avec Model-TG : Attack et Filtre (touche PRESET tenue) agissent sur les pistes VA, par ah_noenv."""
    def go(i, atk, flt):
        e = fw.engine(keep={0})
        e.set(0, machine=fw.idx[i], **kw_of(i, decay=80))
        e.uc.mem_write(E.PARAMS + 0xe + 46, struct.pack(">hhh", atk, flt, 0))
        x = np.stack([e.block(1 if b == 1 else 0)[0] for b in range(40)])
        return x, e.unmapped
    ok, rows = True, []
    for i in range(4):
        base, unm = go(i, 0, 32512)
        slow, _ = go(i, 64 << 8, 32512)
        dark, _ = go(i, 0, 30 << 8)
        e_b, e_s = np.abs(base[2:6]).sum(), np.abs(slow[2:6]).sum()
        ok &= not unm and e_s < 0.7 * e_b and not np.array_equal(base, dark)
        rows.append(f"{NAMES[i]} {e_s / e_b:.2f}")
    check(ok, "avec Model-TG, Attack 64 adoucit l'attaque (énergie des blocs 2 à 5 / Attack 0 : "
              + ", ".join(rows) + ") ; Filtre 30 change le son")


# --- 5. le firmware de David (facultatif) ----------------------------------------------------------------------
class David:
    """Adresses dans le MAIN OS de « Model-TG-VA-DR-v1 » (analyse en lecture seule, notes/56 §4.1). Rien de son fichier
    n'est recopié : il est lu et exécuté ici seulement."""
    LEN = 1846176
    VA_PARAMS, VA_RENDER = 0x401bf330, 0x401bf3b6       # (d2 = piste, a2 = trackData) ; (piste, pas)
    DR_PARAMS, DR_RENDER, POST = 0x401bf9b0, 0x401bfa38, 0x401c0006   # ; (piste, pas, machine 8..10) ; (sortie, piste)
    OUT = 0x401c1c0c                                    # sampler_buf + 32 : les 64 échantillons à 96 kHz
    WV_TRIG, DR_TRIG, TRK_MACH = 0x401bce94, 0x401c0504, 0x401be60c
    WV_PH, DRIFT, VA_RNG = 0x401bce4c, 0x401bf774, 0x401bf7a4
    DR = dict(phase=0x401c03a0, env=0x401c03d0, click=0x401c03e8, tenv=0x401c0400, lp1=0x401c0418, lp2=0x401c0430)
    HH, DR_SEED = 0x401c0448, 0x401c04f0
    TABLES = ((0x401bf7b0, R.TUNE), (0x401c053c, R.DECAY), (0x401c073c, R.FILT), (0x401c0524, R.HH_RATIO),
              (0x401c04f8, [R.POST_GAIN[k] for k in (1, 2, 3)]))
    TD = 0x40700000                                      # trackData factice (BSS libre de l'OS)
    STOP, STACK = 0x40780000, 0x90010000

    def __init__(self, img):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
        uc.mem_map(0x40000000, 0x00800000)
        uc.mem_map(0x90000000, 0x00020000)
        uc.mem_write(BASE, img)
        uc.mem_write(self.STOP, b"\x4e\x71\x4e\x71")
        self.bad = []
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: self.bad.append(addr) or False)

    @classmethod
    def verify(cls, img):
        """Le bon fichier : sa taille, et à ces adresses les tables et les graines que va_ref calcule."""
        if len(img) != cls.LEN:
            return f"MAIN OS de {len(img)} o ({cls.LEN} attendus)"
        for at, vals in cls.TABLES:
            if list(struct.unpack_from(f">{len(vals)}i", img, at - BASE)) != list(vals):
                return f"table en {at:#x} différente"
        if struct.unpack_from(">I", img, cls.VA_RNG - BASE)[0] != 0x6d2b79f5 or \
                struct.unpack_from(">I", img, cls.DR_SEED - BASE)[0] != 0x1f123bb5:
            return "graines différentes"
        return None

    def call(self, fn, *args, regs=None):
        sp = self.STACK - 0x400
        self.uc.mem_write(sp, struct.pack(">I" + "I" * len(args), self.STOP, *[a & 0xffffffff for a in args]))
        self.uc.reg_write(A7, sp)
        for r, v in (regs or {}).items():
            self.uc.reg_write(r, v & 0xffffffff)
        self.uc.emu_start(fn, self.STOP, count=2_000_000)

    def l32(self, a, n=1):
        return list(struct.unpack(f">{n}i", self.uc.mem_read(a, 4 * n)))

    def fill(self, t, kind, words, step, trig):
        self.uc.mem_write(self.TD + 22, struct.pack(">4h", *words))
        regs = {mk.UC_M68K_REG_D2: t, mk.UC_M68K_REG_A2: self.TD}
        self.call(self.VA_PARAMS if kind == R.VA else self.DR_PARAMS, regs=regs)
        if trig:
            self.uc.mem_write((self.WV_TRIG if kind == R.VA else self.DR_TRIG) + t, b"\x01")
        if kind == R.VA:
            self.call(self.VA_RENDER, t, step)
        else:
            self.call(self.DR_RENDER, t, step, 7 + kind)
        return self.l32(self.OUT, 64)

    def track(self, t):
        """L'état de la piste t, rangé comme Track (ses tableaux séparés)."""
        tr = R.Track()
        tr.ph1, tr.ph2 = [R.u32(x) for x in self.l32(self.WV_PH + 12 * t, 2)]
        tr.dr1, tr.dr2 = self.l32(self.DRIFT + 8 * t, 2)
        for f, at in self.DR.items():
            setattr(tr, f, self.l32(at + 4 * t)[0])
        tr.phase, tr.env = R.u32(tr.phase), R.u32(tr.env)
        tr.hh = [R.u32(x) for x in self.l32(self.HH + 24 * t, 6)]
        return tr

    def seeds(self):
        return R.u32(self.l32(self.VA_RNG)[0]), R.u32(self.l32(self.DR_SEED)[0])

    def post(self, buf, t, kind):
        self.uc.mem_write(self.TRK_MACH + 4 * t, struct.pack(">I", 7 + kind))
        self.uc.mem_write(self.TD + 0x1000, struct.pack(">32I", *[R.u32(w) for w in buf]))
        self.call(self.POST, self.TD + 0x1000, t)
        return self.l32(self.TD + 0x1000, 32)


def same_state(a, b):
    """État des deux côtés (sans les potards ni le trig, rangés autrement chez David)."""
    return [R.u32(w) for w in a.words()[:16]] == [R.u32(w) for w in b.words()[:16]]


def david_unit(dimg, fw, quick):
    """Ses fonctions de rendu = va_ref en mode « david » (débordements compris), état et graines à ses adresses ; notre
    code compilé = le sien, hors des blocs où son VA HIHAT déborde."""
    rnd = random.Random(1053)
    d, c = David(dimg), Code(fw)
    model = R.Dsp(*d.seeds())
    if (c.seeds() != d.seeds()) or not all(c.track(t).same(R.Track()) for t in range(6)):
        check(False, "--david : graines et état de départ identiques")
        return
    n, n_ov, n_eq, bad, diverged = 0, 0, 0, [], set()
    tstate = {t: dict(kind=rnd.randrange(4), words=[rnd.randrange(32768) for _ in range(4)], step=0x10000)
              for t in range(6)}
    for blk in range(800 if quick else 4000):
        t = rnd.randrange(6)
        s = tstate[t]
        r = rnd.random()
        if r < 0.03:
            s["kind"] = rnd.randrange(4)
        if r < 0.15:
            s["words"] = [rnd.choice((rnd.randrange(-32768, 32768), rnd.randrange(32768), 0, 0x7f00, 32767))
                          for _ in range(4)]
        if r < 0.1:
            s["step"] = rnd.choice((note_step(rnd.randrange(128)), rnd.choice(STEPS[:12]), rnd.randrange(0x400000)))
        kind, step, trig = s["kind"], s["step"], int(rnd.random() < 0.05)
        knobs = [R.dial(w) for w in s["words"]]
        ov = kind == R.HIHAT and R.Dsp.hihat_overflows(step, knobs[1])
        n_ov += ov
        if ov:
            diverged.add(t)
        got_d = d.fill(t, kind, s["words"], step, trig)
        tr = model.trk[t]
        tr.knob, tr.trig = knobs, tr.trig | trig
        want_d = model.fill(t, step, kind, david=True)
        mt = c.track(t)
        mt.knob, mt.trig = knobs, mt.trig | trig
        c.set_track(t, mt)
        got_o, _ = c.fill(t, step, kind)
        n += 1
        if got_d != want_d or not same_state(d.track(t), model.trk[t]) or d.seeds() != (model.va_seed, model.dr_seed):
            bad.append(f"David {KINDS_SHORT[kind]} bloc {blk}")
        if t not in diverged:
            n_eq += 1
            if got_o != got_d:
                bad.append(f"nous {KINDS_SHORT[kind]} bloc {blk}")
        elif ov and got_o == got_d:
            bad.append(f"débordement sans écart, bloc {blk}")
    pb = 0
    for _ in range(300):
        kind, t = rnd.randrange(1, 4), rnd.randrange(6)
        buf = [rnd.choice((rnd.randrange(-1 << 31, 1 << 31), rnd.randrange(-3000, 3000) << 16)) for _ in range(32)]
        got_o, _ = c.post(buf, kind)
        if d.post(buf, t, kind) != got_o:
            bad.append(f"va_post {KINDS_SHORT[kind]}")
        pb += 1
    check(not bad and not d.bad and not c.bad,
          f"--david, fonctions seules : son rendu (à ses adresses) = va_ref « david » au bit près, état et graines à "
          f"ses adresses compris ({n} blocs, dont {n_ov} où son VA HIHAT déborde) ; notre code = le sien sur les "
          f"{n_eq} blocs hors débordement ; son gain de sortie = va_post ({pb} blocs) {bad[:3]}")


def david_loop(dimg, fw, quick):
    """Dans la boucle des voix : son firmware (Model-TG + ses machines, exécuté en place) et le nôtre (va-tg), la même
    piste, la même voix au départ (déjà sur la machine, muette), les mêmes trigs. Le tampon à 96 kHz et la sortie de
    piste comparés tant que les deux voix sont calculées ; ensuite (la fin de note), son critère de voix muette
    (voice_quiet de Model-TG) et le nôtre (MACRO) diffèrent."""
    def go(which, i, kw, trigs, changes, blocks):
        if which == "david":
            e = TM.engine(dimg)
            pre = struct.pack(">II", 6, 6)                 # chez David : la voix d'un Sampler
        else:
            e = fw.engine(keep={0})
            pre = struct.pack(">II", fw.idx[i], fw.idx[i])
        e.uc.mem_write(E.VOICE0, pre)
        if which != "david":
            e.uc.mem_write(E.VOICE0 + R.MARK_OFF, struct.pack(">I", R.MARK))
        for t in range(1, 6):
            e.set(t, machine=0)
        e.set(0, machine=gs.TG_FIRST + i, **kw)
        bufs, b = {}, [0]

        def dec(uc, a, s, u):
            sp = uc.reg_read(A7)
            v, buf = struct.unpack(">II", uc.mem_read(sp + 4, 8))
            if v == E.VOICE0:
                bufs[b[0]] = list(struct.unpack(">64i", uc.mem_read(buf + 32, 256)))
        e.uc.hook_add(UC_HOOK_CODE, dec, begin=DECIMATE, end=DECIMATE)
        out = []
        for b[0] in range(blocks):
            for k, v in (changes or {}).get(b[0], {}).items():
                e.set(0, **{k: v})
            out.append(e.block(1 if b[0] in trigs else 0)[0])
        return np.stack(out), bufs, e.unmapped
    todo = [(f"{NAMES[i]} défauts", i, kw_of(i), (1,), None, 200) for i in range(4)]
    todo += [("VA carré + triangle, Osc2 Tune 20", 0, kw_of(0, color=64, shape=127, sweep=20), (1, 30), None, 120),
             ("VA potards qui bougent, PUNCH", 0, kw_of(0, punch=1, decay=90), (1,),
              {b: {"color": (7 * b) % 128, "contour": (3 * b) % 128} for b in range(80)}, 80),
             ("VA KICK Drive 127, Click 127, note 48", 1, kw_of(1, sweep=127, contour=127, note=48), (1, 40), None, 120),
             ("VA SNARE Noise Mix 127, Drive 127", 2, kw_of(2, color=127, contour=127), (1,), None, 80),
             ("VA HIHAT Spread 127, note 72", 3, kw_of(3, shape=127, note=72, decay=60), (1, 20), None, 80)]
    if quick:
        todo = todo[:4]
    bad, rows, n_cmp, n_tail = [], [], 0, 0
    for name, i, kw, trigs, changes, blocks in todo:
        xd, bd, ud = go("david", i, kw, trigs, changes, blocks)
        xo, bo, uo = go("ours", i, kw, trigs, changes, blocks)
        both = sorted(set(bd) & set(bo))
        stop = next((b for b in range(1, blocks) if b not in both), blocks)    # jusqu'à la 1re fin de calcul
        span = [b for b in both if b < stop]
        same_buf = all(bd[b] == bo[b] for b in span)
        same_out = np.array_equal(xd[:stop], xo[:stop])
        n_cmp += len(span)
        tail = int(max(np.abs(xd[stop:]).max(initial=0), np.abs(xo[stop:]).max(initial=0)))
        n_tail += 1
        rows.append(f"{name} : blocs 1..{stop - 1}, fin de note {tail:.1g}")
        if not (same_buf and same_out and len(span) > 10 and not ud and not uo):
            first = next((b for b in span if bd[b] != bo[b]), None)
            fo = next((b for b in range(stop) if not np.array_equal(xd[b], xo[b])), None)
            bad.append(f"{name} (tampon {first}, sortie {fo})")
    check(not bad, f"--david, boucle des voix : son firmware et le nôtre (avec Model-TG), même tampon à 96 kHz et même "
                   f"sortie de piste, échantillon par échantillon, sur {n_cmp} blocs calculés des deux côtés "
                   f"({len(todo)} cas) {bad[:3]}")
    for r in rows:
        print("        " + r)
    # le VA HIHAT aigu : chez David, des fréquences fausses
    i, kw = 3, kw_of(3, shape=127, note=96)
    xd, bd, _ = go("david", i, kw, (1,), None, 20)
    xo, bo, _ = go("ours", i, kw, (1,), None, 20)
    diff = [b for b in sorted(set(bd) & set(bo)) if bd[b] != bo[b]]
    check(bool(diff) and diff[0] == 1, f"--david : VA HIHAT note 96, Spread 127 : tampons différents dès le 1er bloc "
                                       f"(son débordement 32 bits, corrigé ici) {diff[:3]}")
    # coût, avec Model-TG des deux côtés
    def cost_of(which, i, kw):
        e = TM.engine(dimg) if which == "david" else fw.engine(keep={0})
        e.uc.mem_write(E.VOICE0, struct.pack(">II", *((6, 6) if which == "david" else (fw.idx[i],) * 2)))
        if which != "david":
            e.uc.mem_write(E.VOICE0 + R.MARK_OFF, struct.pack(">I", R.MARK))
        for t in range(1, 6):
            e.set(t, machine=0)
        e.set(0, machine=gs.TG_FIRST + i, **kw)
        n = [0]
        e.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: n.__setitem__(0, n[0] + 1))
        per = []
        for b in range(14):
            n0 = n[0]
            e.block(1 if b == 1 else 0)
            per.append(n[0] - n0)
        return int(np.median(per[4:]))
    rows = []
    for i in range(4):
        cd, co = cost_of("david", i, kw_of(i, decay=100)), cost_of("ours", i, kw_of(i, decay=100))
        rows.append(f"{NAMES[i]} {cd} / {co}")
    check(True, "--david, coût de la boucle des 6 voix, une piste jouée, instructions par bloc (David / nous, avec "
                "Model-TG) : " + ", ".join(rows))


# --- 6. coût ---------------------------------------------------------------------------------------------------
def cost(fw, label, quick, macro=None):
    """Instructions par bloc d'une voix (boucle des voix entière, moins la même boucle sans voix), pile."""
    def go(make, idx, kw, blocks, trigs=(1,), rng=None):
        e = make()
        e.set(0, machine=idx, **kw)
        if idx == OFF:
            e.uc.mem_write(E.VOICE0, struct.pack(">II", OFF, OFF))
        n = {"i": 0, "sp": 1 << 32}
        lo, hi = rng or (0, 0)

        def hk(uc, a, s, u):
            n["i"] += 1
            if lo <= a < hi:
                n["sp"] = min(n["sp"], uc.reg_read(A7))
        e.uc.hook_add(UC_HOOK_CODE, hk)
        per = []
        for b in range(blocks):
            i0 = n["i"]
            e.block(1 if b in trigs else 0)
            per.append(n["i"] - i0)
        return np.array(per), n["sp"]
    ours = lambda: fw.engine(keep={0})
    rng = (fw.pay, fw.code_end)
    base, _ = go(ours, OFF, BASE_KW, 4, trigs=())
    zero = int(np.median(base))
    tone, _ = go(ours, TONE, dict(BASE_KW, color=40, shape=38, sweep=52, contour=42, decay=100), 14)
    tone_c = int(np.median(tone[4:])) - zero
    rows, deep = [], 0
    todo = [("VA scie + scie", 0, {}), ("VA carré + carré", 0, dict(color=64, shape=64)),
            ("VA triangle + triangle", 0, dict(color=127, shape=127)), ("VA un oscillateur", 0, dict(contour=0)),
            ("VA KICK", 1, {}), ("VA SNARE", 2, {}), ("VA HIHAT", 3, {})]
    if quick:
        todo = [todo[0], todo[1]] + todo[4:]
    for name, i, kw in todo:
        per, sp = go(ours, fw.idx[i], kw_of(i, decay=100, **kw), 14, rng=rng)
        per = per - zero
        rows.append((name, int(per[2]), int(np.median(per[4:])), int(per[4:].max())))
        deep = max(deep, E.STACK - 0x100 - sp)
    idle, _ = go(ours, fw.idx[0], kw_of(0, decay=0), 40, rng=rng)
    idle_c = int(np.median(idle[20:])) - zero
    mac = ""
    if macro is not None:
        mk_ = lambda: macro.engine(solo=0)
        mb, _ = go(mk_, OFF, BASE_KW, 4, trigs=())
        mz = int(np.median(mb))
        got = []
        for m, nm in ((0, "CSAW"), (37, "WAVETABLES")):
            per, _ = go(mk_, macro.index, dict(BASE_KW, color=64, shape=m, sweep=64, contour=0, decay=100), 14)
            got.append(f"{nm} {int(np.median(per[4:])) - mz}")
        mac = " ; MACRO " + ", ".join(got)
    for name, f, typ, mx in rows:
        print(f"        {name:<24} 1er bloc {f:6}, en jeu {typ:6}, au plus {mx:6}")
    check(True, f"{label} : coût d'une voix, instructions par bloc de 32 trames : "
                + ", ".join(f"{n} {t}" for n, _, t, _ in rows)
                + f" ; TONE {tone_c}{mac} ; voix muette {idle_c} ; pile {deep} o sous la boucle des voix")
    return rows


# --- 7. avec d'autres mods -------------------------------------------------------------------------------------
def with_others(stock, cycles, ids, alone, tg_fw, tg):
    by_id = {t["id"]: t for t in (load(f.name) for f in sorted(DEV.glob("[0-9]*.json")))}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise SystemExit(f"!! tweaks inconnus : {unknown}")
    others = [by_id[i] for i in ids]
    with_tg = any(t["id"].startswith("model-tg") for t in others)
    mine = by_id["va-tg" if with_tg else "va"]
    clash = [t["id"] for t in others if mine["id"] in t.get("conflicts", []) or t["id"] in mine["conflicts"]]
    if clash:
        raise SystemExit(f"!! incompatibles avec {mine['id']} : {clash}")
    fw = Fw(stock, sorted(others + [mine], key=lambda t: t["order"]))
    ref_fw = Fw(stock, sorted(others, key=lambda t: t["order"]))
    label = ", ".join(ids)
    print(f"\n== {mine['id']} avec {label} : machines {fw.idx[0] + 1} à {fw.idx[-1] + 1}")
    print("démarrage")
    t7.X.bootstrap_depack_ok(cycles, fw.tweaks, None) or t7.FAIL.append("bootstrap avec " + label)
    boot(fw, tg if with_tg else None)
    print("son")
    stock_unchanged(ref_fw, fw, "ces mods sans VA")
    like(tg_fw if with_tg else alone, fw, f"VA avec {label} = VA {'avec Model-TG seul' if with_tg else 'seule'}")
    locks(fw, f"VA avec {label}")
    mixed(fw, ref_fw, f"VA avec {label}", sampler=with_tg)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--quick", action="store_true", help="moins de cas")
    ap.add_argument("--david", help="Model-TG-VA-DR-v1.syx de DavidCaruso (facultatif) : comparaison à son firmware")
    ap.add_argument("--with", dest="others", default="", help="ids d'autres tweaks : VA avec eux (section 8)")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    va, tg_tw, va_tg = load("27-va.json"), load("30-model-tg-st.json"), load("36-va-tg.json")
    dimg = None
    if args.david:
        dimg = T.main_os_from_syx(args.david)
        why = David.verify(dimg)
        if why:
            raise SystemExit(f"!! {args.david} : pas le firmware Model-TG-VA-DR-v1 attendu ({why})")
    off = Fw(stock, [])
    alone = Fw(stock, [va])
    print(f"== {va['id']} : machines {alone.idx[0] + 1} à {alone.idx[-1] + 1} ({', '.join(NAMES)})")
    print("démarrage")
    t7.X.bootstrap_depack_ok(args.cycles, va, None) or t7.FAIL.append("bootstrap")
    boot(alone)
    print("interface")
    interface_alone(stock, alone)
    print("le code seul")
    unit(alone, "seules", args.quick)
    print("son")
    todo = cases(alone, args.quick)
    exact(alone, todo, "seules")
    amp_like_tone(alone)
    decay_like_tone(alone, args.quick)
    pitch(alone)
    knobs_matter(alone)
    stock_unchanged(off, alone, "l'OS d'origine")
    locks(alone, "seules")
    six_tracks(alone, "seules")
    mixed(alone, off, "seules")
    print("coût")
    macro_fw = None
    if (DEV / "25-macro.json").exists():
        import test_macro as TMAC         # noqa: E402
        macro_fw = TMAC.Fw(stock, [load("25-macro.json")])
    cost(alone, "seules", args.quick, macro_fw)

    gs.set_base(gs.PAY_TG)
    fw, ref_tg = Fw(stock, [tg_tw, va_tg]), Fw(stock, [tg_tw])
    tg = {k: int(v, 16) for k, v in tg_tw["symbols"].items()}
    tg["knob_vec"] = tms.knob_vec_at(va_tg)
    print(f"\n== {va_tg['id']} : avec Model-TG, machines {fw.idx[0] + 1} à {fw.idx[-1] + 1}")
    print("démarrage")
    t7.X.bootstrap_depack_ok(args.cycles, [tg_tw, va_tg], None) or t7.FAIL.append("bootstrap avec Model-TG")
    boot(fw, tg)
    print("interface")
    interface_tg(ref_tg, fw, tg)
    print("le code seul")
    unit(fw, "avec Model-TG", True)
    print("son")
    tg_todo = [c for c in todo if c[0].endswith("défauts") or "se tait" in c[0] or "machine lock" in c[0]
               or "bougent" in c[0]]
    exact(fw, tg_todo, "avec Model-TG")
    stock_unchanged(ref_tg, fw, "Model-TG seul")
    like(alone, fw, "VA avec Model-TG = VA seule")
    attack_filter(fw)
    locks(fw, "avec Model-TG")
    six_tracks(fw, "avec Model-TG")
    mixed(fw, ref_tg, "avec Model-TG", sampler=True)
    print("coût")
    cost(fw, "avec Model-TG", True)
    if dimg is not None:
        print(f"\n== --david : {pathlib.Path(args.david).name}")
        david_unit(dimg, fw, args.quick)
        david_loop(dimg, fw, args.quick)
    if args.others:
        with_others(stock, args.cycles, args.others.split(","), alone, fw, tg)
    fail = t7.FAIL + tms.FAIL
    print("\nTOUT OK" if not fail else f"\n{len(fail)} ÉCHEC(S)")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
