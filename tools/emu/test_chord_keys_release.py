#!/usr/bin/env python3
"""Preuve : un relâchement de TRIG perdu ne doit pas bloquer la note suivante de cette touche (Chord Keys, notes/42).

Le défaut (point 9, vu sur le désassemblage et sur la machine) : PATTERN tenu, PatternAndBankSelectView (avant
KeyboardView dans l'ordre de distribution) consomme le relâchement d'un TRIG ; KeyboardView ne le voit jamais.
Chord Keys garde alors held[touche] valide. Au prochain appui de la même touche sur une piste qui n'est pas CHORD
(ou avec Keys OFF), la note part par le chemin stock (0x4001a0d2), mais son relâchement est avalé par ck_ui_key
(held[touche] encore valide) : la fin de note stock 0x40019d00, le seul chemin qui coupe une note jouée au clavier,
n'est jamais atteinte.

On appelle la cible du pointeur de KeyboardView::consumeKeyEvent (0x400ff9cc), lue dans chaque image, avec une
vraie KeyEvent (constructeur 0x4007238c) et une vue factice (liste des notes jouées en +0x94/+0x98/+0x9c).
Exécutés pour de vrai : ck_ui_key, handle_press, release_key, play_key, ck_ui_cancel_track, ck_ui_item_change,
ck_ui_config_get/set (le code compilé du JSON), et dans l'OS : 0x4001a0d2, 0x40019f44, 0x40019e7a, 0x40019d00,
0x40019c84, les accesseurs (piste sélectionnée 0x40012412/0x40012442, machine 0x4001e318, pattern 0x4000f208,
piste du pattern 0x4000cfcc, vélocité 0x40015ac4, Rte 0x40016086, MIDI 0x40016e90/0x40012e82, modificateurs
0x4007faf4, UIStates 0x4006b978/0x4006bb18/0x4006bdfe), les singletons 0x400cf866/0x400cf9a8/0x400cfd0e et
la recopie de la liste 0x4008f1f0.
L'état que ces fonctions lisent est écrit en mémoire, pas simulé dans leur code : singletons (0x40fe4228 projet,
0x40fe4218 UIStates, 0x40fe41e8, 0x40a7887c pattern actif = 0), objets « valeur » factices aux adresses que l'OS
calcule (vtable[10] rend le pointeur de données rangé en +16), données des pistes (machine +38, vélocité +708,
Rte +514, MIDI +720), en-tête du pattern (mots Chord Keys +40, signature +32), touches tenues (0x40f95744).
Interceptés, à l'entrée de fonctions de l'OS seulement (jamais dans le code ck_*) : note du moteur 0x4008171e et fin
de note 0x4008145e, note MIDI 0x4008273c et fin 0x400827a8 (enregistrées), View::consumeKeyEvent de base
0x40075f3c (touches hors TRIG, enregistrée, rend 0), operator new/delete (tas factice, par précaution : la liste
de la vue a déjà sa capacité).

  S1. Piste 1 CHORD, Keys ON, sélectionnée : appui TRIG 1 (accord) ; relâchement perdu (PATTERN tenu) ; piste 2
      (TONE) sélectionnée ; appui TRIG 1 (note stock sur la piste 2) ; relâchement TRIG 1 : 0x40019d00 doit être
      atteinte et la note de la piste 2 finir, l'accord de la piste 1 doit avoir reçu sa fin au plus tard là.
  S2. Même début, puis Keys OFF par le menu FUNC + RETRIG (ck_ui_item_change) au lieu du changement de piste.
  Origine : la même suite sur l'OS sans Chord Keys (avec les autres tweaks) finit toutes les notes.
  Régressions (doivent passer avec et sans la correction) : appui/relâchement Keys ON sur les 16 TRIG,
  répétitions de maintien, touches qui se chevauchent, codes hors TRIG, Keys OFF et piste non CHORD comme
  l'origine, mode grille, FUNC et KEY 1..3.

Sur le JSON actuel, les contrôles marqués [défaut] de S1 et S2 échouent (c'est la reproduction) ; tous les autres
passent. Après la correction (appui neuf : release_key(&held[touche]) et held[touche].valid = 0 avant handle_press),
tout doit passer. Durée : quelques secondes.

    python3 tools/emu/test_chord_keys_release.py --cycles model-cycles_OS1.13.syx [--tweak 45-chord-keys.json] \\
        [--with 6ch-usbup,arp,trig-hold,tempo-max,boot-anim,syntakt-sd-cp-toy-bits-swarm --syntakt Syntakt_OS1.42.syx]
"""
import argparse
import json
import pathlib
import struct
import sys

from unicorn import Uc, UcError, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import test_sdvintage as T          # noqa: E402

DEV = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13"
TWEAK = DEV / "45-chord-keys.json"
BASE = build.BASE
FAIL = []                           # (groupe, message)
EMU_ERRORS = []                     # accès hors mémoire ou arrêt imprévu, dans n'importe quel appel

# --- l'OS 1.13 --------------------------------------------------------------------------------------------------
SLOT = 0x400ff9cc                   # KeyboardView : pointeur de consumeKeyEvent (vtable 0x400ff9c4, entrée 2)
KB_KEY = 0x4001a0d2                 # KeyboardView::consumeKeyEvent d'origine
KB_END = 0x40019d00                 # (vue, touche) : fin de toutes les notes de la liste jouées par cette touche
VIEW_KEY = 0x40075f3c               # View::consumeKeyEvent de base (touches hors TRIG 1..16)
KEYEV_CTOR = 0x4007238c             # KeyEvent(objet, code, indicateurs, heure, vélocité)
ENGINE_ON = 0x4008171e              # (piste, note, vélocité, ...) : note du moteur
ENGINE_OFF = 0x4008145e             # (piste, note, 0x40) : fin de note du moteur
MIDI_ON = 0x4008273c                # (canal, note, vélocité)
MIDI_OFF = 0x400827a8               # (canal, note)
NEW, DELETE = 0x400802e0, 0x400802ec
ROOT_PTR = 0x40fe4228               # singleton du projet (0x400cf866)
UIS_PTR = 0x40fe4218                # singleton UIStates (0x400cf9a8)
SEQ_PTR = 0x40fe41e8                # singleton de 0x400cfd0e (lu par 0x4000f208)
ACTIVE_PTR = 0x40a7887c             # bloc du pattern actif : numéro en +30706 (0x40054828)
KEYS_DOWN = 0x40f95744              # touches tenues, un bit par touche (0x4007faf4)
KEY_TABLE = 0x4010ae5c              # code -> numéro de bit
CK_MAGIC = 0x434b01a7               # signature des réglages Chord Keys dans l'en-tête du pattern (chord_storage.c)
ENABLED = 0x80000000
CK_DEFAULT = 48 << 21               # OFF, tonique 48, majeur, triades

# Indicateurs des KeyEvent, comme les construisent 0x4007fbde (appui, relâchement) et 0x4007f914 (maintien) :
PRESS, FUNC_PRESS = 0x01, 0x03      # bit 0 : appuyé ; bit 1 : FUNC tenu
HOLD, HOLD_LONG = 0x09, 0x29        # bit 3 : maintien ; bit 5 : maintien long (64 ticks de 0x4007f914)
RELEASE, RELEASE_LAST = 0x00, 0x10  # bit 0 à 0 ; bit 4 : relâchement de la dernière touche appuyée
TRIG = {n: 15 + n for n in range(1, 17)}   # TRIG 1..16 = codes 16..31
CHORD, TONE = 5, 4                  # machines (0x4001e318)

# --- mémoire de l'émulateur ----------------------------------------------------------------------------------------
STOP, STACK = 0x9f000000, 0x9e000000
ROOT = 0x91000000                   # projet ; état (+48), sons (+116), patterns (+5192)
UIS = 0x91100000
SEQ = 0x91180000
ACTIVE = 0x91200000
VT = 0x91300000                     # vtable commune des objets « valeur » factices
F_DATA = 0x91300400                 # vtable[10] : rend *(this + 16)
F_NOTIFY = 0x91300410               # vtable[4] : signal de changement (ck_ui_config_set)
GUARD = 0xdead0000                  # autres entrées : hors mémoire, tout appel imprévu s'arrête et est signalé
DATA = 0x91400000                   # données des objets, 0x1000 chacune
VIEW, LIST, EVT, CLOSURE = 0x93000000, 0x93001000, 0x93002000, 0x93003000
HEAP = 0x94000000
PATTERN = ROOT + 5192               # 0x4000f208 : projet + 5192 + 732 * pattern actif (0)
STATE_OBJ = ROOT + 48               # 0x4000eb90
STATE_DATA, HEADER = DATA, DATA + 0x1000


def SOUND_OBJ(t):                   # 0x4000eb9c puis 0x40009c1a : projet + 116 + 68 t + 96
    return ROOT + 116 + 68 * t + 96


def TRACK_OBJ(t):                   # 0x4000cfcc : pattern + 112 + 88 t
    return PATTERN + 112 + 88 * t


def SOUND_DATA(t):
    return DATA + 0x2000 + 0x1000 * t


def TRACK_DATA(t):
    return DATA + 0x8000 + 0x1000 * t


def check(group, ok, msg):
    print(("  ok    " if ok else "  ECHEC ") + msg, flush=True)
    if not ok:
        FAIL.append((group, msg))
    return ok


class Rig:
    """KeyboardView et ce qu'elle lit de l'OS : projet, pattern, pistes, UIStates, en mémoire."""

    def __init__(self, img, syms):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
        uc.reg_write(mk.UC_M68K_REG_SR, 0x2700)               # superviseur : ck_storage_irq_save/restore
        uc.mem_map(0x40000000, 0x02400000)                    # image + BSS
        uc.mem_write(BASE, img)
        uc.mem_map(0x90000000, 0x10000000)                    # pile, objets factices
        uc.mem_write(STOP, b"\x4e\x71\x4e\x71")
        self.img, self.syms = img, syms
        self.target = struct.unpack(">I", img[SLOT - BASE:SLOT - BASE + 4])[0]
        self.bad, self.log, self.heap, self.ts = [], [], HEAP, 0
        self.sounding, self.midi = {}, {}                    # (piste, note) / (canal, note) -> nombre de notes
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: self.bad.append(addr) or False)
        stubs = {ENGINE_ON: self._on, ENGINE_OFF: self._off, MIDI_ON: self._midi_on, MIDI_OFF: self._midi_off,
                 VIEW_KEY: self._view_key, NEW: self._new, DELETE: lambda a: 0}
        for addr, fn in stubs.items():
            uc.hook_add(UC_HOOK_CODE, self._stub(fn), begin=addr, end=addr)
        probes = {KB_KEY: lambda a: ("stock",), KB_END: lambda a: ("fin", a[1]), F_NOTIFY: lambda a: ("signal",)}
        for addr, fn in probes.items():                        # observés seulement : l'exécution continue
            uc.hook_add(UC_HOOK_CODE, self._probe(fn), begin=addr, end=addr)
        self._objects()

    # -- état de l'OS, écrit là où ses fonctions le lisent --
    def _objects(self):
        w = self.w32
        w(ROOT_PTR, ROOT)
        w(UIS_PTR, UIS)
        w(SEQ_PTR, SEQ)
        w(ACTIVE_PTR, ACTIVE)                                  # pattern actif 0 (+30706 à zéro)
        for k in range(64):
            w(VT + 4 * k, GUARD + 4 * k)
        w(VT + 40, F_DATA)
        w(VT + 16, F_NOTIFY)
        # movea.l 4(sp),a0 ; move.l 16(a0),d0 ; rts
        self.uc.mem_write(F_DATA, bytes.fromhex("206f0004" "20280010" "4e75"))
        self.uc.mem_write(F_NOTIFY, b"\x4e\x75")

        def obj(at, data):
            w(at, VT)
            w(at + 16, data)
        obj(STATE_OBJ, STATE_DATA)
        obj(PATTERN + 44, HEADER)                              # en-tête du pattern (0x4000d0dc ; ck_ui_config_*)
        for t in range(6):
            obj(SOUND_OBJ(t), SOUND_DATA(t))
            obj(TRACK_OBJ(t), TRACK_DATA(t))
            w(STATE_DATA + 96 + 4 * t, t)                      # canal MIDI de la piste (0x40012e82)
            self.uc.mem_write(TRACK_DATA(t) + 708, bytes([100]))   # vélocité (0x40015ac4)
            self.uc.mem_write(TRACK_DATA(t) + 720, b"\x01")        # sortie MIDI (0x40016e90)
            self.uc.mem_write(SOUND_DATA(t) + 38, bytes([t if t < 4 else TONE]))
        w(HEADER + 32, CK_MAGIC)
        for t in range(6):
            w(HEADER + 40 + 4 * t, CK_DEFAULT)
        w(VIEW, 0x400ff9c4)                                    # vtable de KeyboardView (non appelée ici)
        w(VIEW + 0x94, LIST)                                   # liste des notes jouées : début, fin, capacité
        w(VIEW + 0x98, LIST)
        w(VIEW + 0x9c, LIST + 20 * 64)

    def setup(self, machines=(CHORD, TONE), keys=(0,), selected=0):
        """Machines des pistes 1, 2... (KICK 0, SNARE 1, METAL 2, PERC 3, TONE 4, CHORD 5), Keys ON, sélection."""
        for t, m in enumerate(machines):
            self.uc.mem_write(SOUND_DATA(t) + 38, bytes([m]))
        for t in keys:
            self.set_keys(t, True)
        self.select(selected)
        return self

    def select(self, t):
        self.w32(STATE_DATA + 4, t)                            # 0x40012412 / 0x40012442 : piste sélectionnée

    def set_keys(self, t, on):
        word = self.r32(HEADER + 40 + 4 * t)
        self.w32(HEADER + 40 + 4 * t, word | ENABLED if on else word & ~ENABLED)

    def keys_word(self, t):
        return self.r32(HEADER + 40 + 4 * t)

    def set_grid(self, on):
        self.uc.mem_write(UIS + 357, bytes([on, on]))         # 0x4006b978 : mode grille

    def set_modifier(self, code, down):
        idx = struct.unpack(">i", self.img[KEY_TABLE - BASE + 4 * code:][:4])[0]
        byte, bit = KEYS_DOWN + (idx >> 3), 1 << (idx & 7)
        cur = self.uc.mem_read(byte, 1)[0]
        self.uc.mem_write(byte, bytes([cur | bit if down else cur & ~bit]))

    # -- mémoire, appels --
    def w32(self, a, v):
        self.uc.mem_write(a, struct.pack(">I", v & 0xffffffff))

    def r32(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def _args(self, uc):
        sp = uc.reg_read(mk.UC_M68K_REG_A7)
        return sp, struct.unpack(">8I", uc.mem_read(sp + 4, 32))

    def _stub(self, fn):
        def hook(uc, addr, size, ud):
            sp, args = self._args(uc)
            uc.reg_write(mk.UC_M68K_REG_D0, fn(args) & 0xffffffff)
            uc.reg_write(mk.UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        return hook

    def _probe(self, fn):
        def hook(uc, addr, size, ud):
            self.log.append(fn(self._args(uc)[1]))
        return hook

    @staticmethod
    def _add(d, k, n):
        d[k] = d.get(k, 0) + n
        if d[k] <= 0:
            del d[k]

    def _on(self, a):
        self.log.append(("on", a[0], a[1], a[2]))
        self._add(self.sounding, (a[0], a[1]), 1)
        return 0

    def _off(self, a):
        self.log.append(("off", a[0], a[1]))
        if (a[0], a[1]) in self.sounding:
            self._add(self.sounding, (a[0], a[1]), -self.sounding[(a[0], a[1])])
        return 0

    def _midi_on(self, a):
        self.log.append(("midi on", a[0], a[1]))
        self._add(self.midi, (a[0], a[1]), 1)
        return 0

    def _midi_off(self, a):
        self.log.append(("midi off", a[0], a[1]))
        if (a[0], a[1]) in self.midi:
            self._add(self.midi, (a[0], a[1]), -self.midi[(a[0], a[1])])
        return 0

    def _view_key(self, a):
        self.log.append(("base", self.r32(a[1] + 12)))
        return 0

    def _new(self, a):
        at, self.heap = self.heap, (self.heap + a[0] + 15) & ~15
        return at

    def call(self, fn, *args):
        sp = STACK - 0x400
        self.uc.mem_write(sp, struct.pack(">I" + "I" * len(args), STOP, *[x & 0xffffffff for x in args]))
        self.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        n = len(self.bad)
        try:
            self.uc.emu_start(fn, STOP, count=2_000_000)
        except UcError as e:
            self.bad.append(f"{e} @ {self.uc.reg_read(mk.UC_M68K_REG_PC):#x}")
        if self.uc.reg_read(mk.UC_M68K_REG_PC) != STOP:
            self.bad.append(f"arrêt à {self.uc.reg_read(mk.UC_M68K_REG_PC):#x}")
        if len(self.bad) > n:
            EMU_ERRORS.append((fn, self.bad[n:]))
        return self.uc.reg_read(mk.UC_M68K_REG_D0)

    def key(self, code, flags):
        """Une KeyEvent (vrai constructeur) passée à la cible du pointeur de KeyboardView ; rend (octet rendu,
        événements observés pendant l'appel)."""
        self.ts += 135_168                                     # 1 ms du minuteur DMA 0
        self.call(KEYEV_CTOR, EVT, code, flags, self.ts, 0x7f)
        start = len(self.log)
        ret = self.call(self.target, VIEW, EVT) & 0xff
        return ret, self.log[start:]

    def menu_keys(self, delta):
        """FUNC + RETRIG, ligne « Keys » : la vraie ck_ui_item_change (champ 0), comme la molette du menu."""
        self.w32(CLOSURE, CLOSURE + 8)
        self.w32(CLOSURE + 8, 0)
        start = len(self.log)
        self.call(self.syms["ck_ui_item_change"], CLOSURE, 0, delta)
        return self.log[start:]

    def view_list(self):
        """Notes de la liste de KeyboardView : (touche, piste, note) des entrées actives."""
        b, e = self.r32(VIEW + 0x94), self.r32(VIEW + 0x98)
        out = []
        for a in range(b, e, 20):
            act, key, note, track, live = struct.unpack(">5I", self.uc.mem_read(a, 20))
            if act == 1:
                out.append((key, track, note))
        return out

    def held(self, key):
        """(valid, active) de held[touche] de Chord Keys, si le JSON donne son adresse (entrées de 14 o)."""
        if "held" not in self.syms:
            return None
        e = bytes(self.uc.mem_read(self.syms["held"] + 14 * key, 14))
        return e[12], e[13]

    def silent(self):
        return not self.sounding and not self.midi


# --- description des événements -------------------------------------------------------------------------------
def describe(ev):
    out = []
    for e in ev:
        if e[0] == "on":
            out.append(f"note p{e[1] + 1}/{e[2]}")
        elif e[0] == "off":
            out.append(f"fin p{e[1] + 1}/{e[2]}")
        elif e[0] == "midi on":
            out.append(f"MIDI c{e[1] + 1}/{e[2]}")
        elif e[0] == "midi off":
            out.append(f"MIDI fin c{e[1] + 1}/{e[2]}")
        elif e[0] == "stock":
            out.append("0x4001a0d2")
        elif e[0] == "fin":
            out.append(f"0x40019d00(touche {e[1]})")
        elif e[0] == "base":
            out.append(f"vue de base (code {e[1]})")
        elif e[0] == "signal":
            out.append("signal de l'en-tête")
    return ", ".join(out) or "rien"


def show(label, ret, ev):
    print(f"    {label} : {describe(ev)} ; rendu {ret}")


def ons(ev, track=None):
    return [(e[1], e[2]) for e in ev if e[0] == "on" and (track is None or e[1] == track)]


def offs(ev):
    return {(e[1], e[2]) for e in ev if e[0] == "off"}


def midi_offs(ev):
    return {(e[1], e[2]) for e in ev if e[0] == "midi off"}


def reached(ev, what):
    return any(e[0] == what for e in ev)


def notes(ev):
    """Ce qui sort vers le moteur et le MIDI."""
    return [e for e in ev if e[0] in ("on", "off", "midi on", "midi off")]


def held_info(r, key):
    h = r.held(key)
    if h is not None:
        print(f"    (held[{key}] de Chord Keys : valid={h[0]}, active={h[1]})")


# --- 1. le pointeur de KeyboardView ---------------------------------------------------------------------------
def slot_tests(base, img, syms):
    a = struct.unpack(">I", base[SLOT - BASE:SLOT - BASE + 4])[0]
    b = struct.unpack(">I", img[SLOT - BASE:SLOT - BASE + 4])[0]
    check("accroche", a == KB_KEY, f"{SLOT:#x} : {a:#x} sans Chord Keys (KeyboardView::consumeKeyEvent d'origine)")
    want = syms.get("ck_ui_key")
    check("accroche", b != KB_KEY and (want is None or b == want),
          f"{SLOT:#x} : {b:#x} avec Chord Keys" + (f" (ck_ui_key des symboles du JSON : {want:#x})" if want else ""))


# --- 2. S1 : relâchement perdu, puis la même touche sur une piste non CHORD -------------------------------------
def s1(img, syms, group, stock_like=False):
    name = "origine S1" if stock_like else "S1"
    r = Rig(img, syms).setup()
    ret, e1 = r.key(TRIG[1], PRESS)
    show("appui TRIG 1 (piste 1 CHORD" + ("" if stock_like else ", Keys ON") + ")", ret, e1)
    print("    relâchement TRIG 1 perdu (PATTERN tenu : consommé par PatternAndBankSelectView)")
    if not stock_like:
        held_info(r, 0)
    r.select(1)
    print("    piste 2 (TONE) sélectionnée")
    ret2, e2 = r.key(TRIG[1], PRESS)
    show("appui TRIG 1", ret2, e2)
    ret3, e3 = r.key(TRIG[1], RELEASE_LAST)
    show("relâchement TRIG 1", ret3, e3)
    first = ons(e1, 0)
    t2 = ons(e2, 1)
    if stock_like:
        check(group, len(first) == 1 and reached(e1, "stock") and not r.bad,
              f"{name} : appui TRIG 1 sur la piste 1 : note stock {first}")
    else:
        check(group, len(first) == 1 and not reached(e1, "stock") and ret == 1 and not r.bad,
              f"{name} : appui TRIG 1 : accord de Chord Keys sur la piste 1 {first}, KeyboardView stock non appelée")
    check(group, reached(e2, "stock") and len(t2) == 1,
          f"{name} : appui TRIG 1 sur la piste 2 : note stock jouée sur la piste 2 {t2} (0x4001a0d2 atteinte)")
    tag = "" if stock_like else "[défaut] "
    check(group, ("fin", 0) in e3,
          f"{name} : {tag}relâchement TRIG 1 : la fin de note stock 0x40019d00 (touche 0) est atteinte")
    mid2 = {(1, n) for _, n in t2}
    check(group, bool(t2) and set(t2) <= offs(e3) and mid2 <= midi_offs(e3),
          f"{name} : {tag}relâchement TRIG 1 : la note de la piste 2 {t2} reçoit sa fin (moteur et MIDI)")
    when = "à l'appui" if set(first) <= offs(e2) else "au relâchement" if set(first) <= offs(e3) else "jamais"
    check(group, bool(first) and set(first) <= offs(e2) | offs(e3),
          f"{name} : la note de la piste 1 {first} a reçu sa fin au plus tard au relâchement ({when})")
    check(group, r.silent() and not r.view_list() and not r.bad,
          f"{name} : {tag}silence à la fin : notes tenues {sorted(r.sounding)}, MIDI {sorted(r.midi)}, "
          f"liste de KeyboardView {r.view_list()}")


# --- 3. S2 : relâchement perdu, puis Keys OFF par le menu -----------------------------------------------------------
def s2(img, syms, group, stock_like=False):
    name = "origine S2" if stock_like else "S2"
    r = Rig(img, syms).setup()
    ret, e1 = r.key(TRIG[1], PRESS)
    show("appui TRIG 1 (piste 1 CHORD" + ("" if stock_like else ", Keys ON") + ")", ret, e1)
    print("    relâchement TRIG 1 perdu (PATTERN tenu)")
    if not stock_like:
        held_info(r, 0)
    first = ons(e1, 0)
    em = []
    if stock_like:
        print("    (pas de menu Keys sans Chord Keys : la même touche est rejouée)")
    elif "ck_ui_item_change" in syms:
        em = r.menu_keys(-1)
        print(f"    FUNC + RETRIG, Keys -> OFF (ck_ui_item_change) : {describe(em)} ; mot {r.keys_word(0):#010x}")
        held_info(r, 0)
        check(group, not r.keys_word(0) & ENABLED and set(first) <= offs(em),
              "S2 : Keys OFF par le menu : l'accord tenu est coupé (ck_ui_cancel_track), Keys enregistré OFF")
    else:
        r.set_keys(0, False)
        print("    Keys OFF écrit dans l'en-tête (ck_ui_item_change absent des symboles du JSON)")
    ret2, e2 = r.key(TRIG[1], PRESS)
    show("appui TRIG 1", ret2, e2)
    ret3, e3 = r.key(TRIG[1], RELEASE_LAST)
    show("relâchement TRIG 1", ret3, e3)
    t1 = ons(e2, 0)
    tag = "" if stock_like else "[défaut] "
    check(group, reached(e2, "stock") and len(t1) == 1,
          f"{name} : appui TRIG 1{'' if stock_like else ' (Keys OFF)'} : note stock sur la piste 1 {t1} "
          f"(0x4001a0d2 atteinte)")
    check(group, ("fin", 0) in e3,
          f"{name} : {tag}relâchement TRIG 1 : la fin de note stock 0x40019d00 (touche 0) est atteinte")
    check(group, bool(t1) and set(t1) <= offs(e3) and {(0, n) for _, n in t1} <= midi_offs(e3),
          f"{name} : {tag}relâchement TRIG 1 : la note stock {t1} reçoit sa fin (moteur et MIDI)")
    check(group, r.silent() and not r.view_list() and not r.bad,
          f"{name} : {tag}silence à la fin : notes tenues {sorted(r.sounding)}, MIDI {sorted(r.midi)}, "
          f"liste de KeyboardView {r.view_list()}")


# --- 4. régressions ---------------------------------------------------------------------------------------------
G = "régression"


def normal(img, syms):
    r = Rig(img, syms).setup()
    rows, good = [], True
    for n in range(1, 17):
        ra, ea = r.key(TRIG[n], PRESS)
        rb, eb = r.key(TRIG[n], RELEASE_LAST)
        on = ons(ea)
        rows.append(on[0][1] if len(on) == 1 else None)
        good &= (len(on) == 1 and on[0][0] == 0 and ra == 1 and rb == 1 and not reached(ea + eb, "stock")
                 and offs(eb) == set(on) and midi_offs(eb) == {(0, on[0][1])} and r.silent())
    check(G, good and not r.view_list() and not r.bad,
          f"Keys ON, TRIG 1..16 appuyés puis relâchés : une note de Chord Keys sur la piste 1 puis sa fin, rendu 1, "
          f"KeyboardView stock jamais appelée (notes {rows})")


def hold(img, syms):
    r = Rig(img, syms).setup()
    _, ea = r.key(TRIG[5], PRESS)
    rep = [r.key(TRIG[5], f) for f in (HOLD, HOLD, HOLD_LONG, HOLD)]
    rb, eb = r.key(TRIG[5], RELEASE_LAST)
    quiet = all(ret == 1 and not notes(ev) and not reached(ev, "stock") for ret, ev in rep)
    check(G, len(ons(ea)) == 1 and quiet,
          "maintien de TRIG 5 (4 répétitions, bit 3) : consommé, ni nouvel accord, ni fin, ni KeyboardView stock")
    check(G, rb == 1 and offs(eb) == set(ons(ea)) and r.silent() and not reached(eb, "stock") and not r.bad,
          f"relâchement de TRIG 5 après le maintien : fin de son accord {ons(ea)}")


def overlap(img, syms):
    r = Rig(img, syms).setup()
    _, e1 = r.key(TRIG[1], PRESS)
    _, e3 = r.key(TRIG[3], PRESS)
    a, b = ons(e1), ons(e3)
    show("appui TRIG 1", 1, e1)
    show("appui TRIG 3, TRIG 1 tenu", 1, e3)
    r1, f1 = r.key(TRIG[1], RELEASE)
    show("relâchement TRIG 1", r1, f1)
    check(G, len(b) == 1 and set(b) <= set(r.sounding) and not offs(f1) and r1 == 1 and not reached(f1, "stock"),
          f"TRIG 1 tenu, TRIG 3 appuyé, TRIG 1 relâché : l'accord de TRIG 3 {b} sonne encore, "
          f"relâchement consommé")
    r3, f3 = r.key(TRIG[3], RELEASE_LAST)
    show("relâchement TRIG 3", r3, f3)
    check(G, set(a) <= offs(e3) | offs(f1) and offs(f3) == set(b) and r.silent() and not r.view_list()
          and not r.bad, "relâchement de TRIG 3 : silence (l'accord de TRIG 1 avait fini à l'appui de TRIG 3)")


def cross_track(img, syms):
    """Deux pistes CHORD : l'accord tenu sur la piste 1 ne doit pas finir quand on joue la piste 3."""
    r = Rig(img, syms).setup(machines=(CHORD, TONE, CHORD), keys=(0, 2), selected=0)
    _, e1 = r.key(TRIG[1], PRESS)
    r.select(2)
    _, e3 = r.key(TRIG[3], PRESS)
    show("appui TRIG 1 (piste 1), puis TRIG 3 (piste 3)", 1, e3)
    r3, f3 = r.key(TRIG[3], RELEASE_LAST)
    r1, f1 = r.key(TRIG[1], RELEASE)
    a, b = ons(e1), ons(e3)
    check(G, len(a) == 1 and len(b) == 1 and not (set(a) & (offs(e3) | offs(f3))) and offs(f3) == set(b) and r3 == 1,
          f"accord de la piste 1 {a} tenu pendant l'appui et le relâchement de TRIG 3 sur la piste 3 {b}")
    check(G, offs(f1) == set(a) and r1 == 1 and r.silent() and not r.bad,
          "puis relâchement de TRIG 1 : fin de l'accord de la piste 1, silence")


def other_codes(img, syms):
    r = Rig(img, syms).setup()
    _, e1 = r.key(TRIG[1], PRESS)
    bad = []
    for code in list(range(16)) + list(range(32, 41)):
        for flags in (PRESS, HOLD, RELEASE):
            ret, ev = r.key(code, flags)
            if not (reached(ev, "stock") and ("base", code) in ev and not notes(ev) and ret == 0):
                bad.append((code, flags, describe(ev)))
    _, ef = r.key(TRIG[1], RELEASE_LAST)
    check(G, not bad and not r.bad, f"codes 0..15 et 32..40 (appui, maintien, relâchement), TRIG 1 tenu : tous à "
                                    f"KeyboardView stock puis à la vue de base, aucune note {bad[:3]}")
    check(G, offs(ef) == set(ons(e1)) and r.silent(), "puis relâchement de TRIG 1 : fin de son accord")


def like_stock(base, img, syms, label, prep, seq):
    """La même suite sur l'OS sans Chord Keys et avec : mêmes notes, mêmes fins, même liste, mêmes rendus."""
    out = []
    for im in (base, img):
        r = Rig(im, syms).setup()
        prep(r)
        run = [r.key(code, flags) for code, flags in seq]
        out.append(([(ret, [e for e in ev if e[0] != "signal"]) for ret, ev in run], r.view_list(), bool(r.bad)))
    (a, la, ba), (b, lb, bb) = out
    played = sum(len(ons(ev)) for _, ev in a)
    check(G, a == b and la == lb and not ba and not bb and all(reached(ev, "stock") for _, ev in b),
          f"{label} : comme l'origine, chaque touche à KeyboardView stock ({played} note(s), liste finale {lb})")
    return a


def regressions(base, img, syms):
    print("Keys ON, appui et relâchement normaux")
    normal(img, syms)
    print("maintien")
    hold(img, syms)
    print("touches qui se chevauchent")
    overlap(img, syms)
    print("accord tenu sur une piste CHORD pendant le jeu sur une autre")
    cross_track(img, syms)
    print("touches hors TRIG 1..16")
    other_codes(img, syms)
    print("Keys OFF, piste non CHORD, mode grille, modificateurs : comme l'origine")
    seq = [(TRIG[1], PRESS), (TRIG[1], RELEASE_LAST), (TRIG[1], PRESS), (TRIG[3], PRESS), (TRIG[3], HOLD_LONG),
           (TRIG[1], RELEASE), (TRIG[3], RELEASE_LAST), (TRIG[16], PRESS), (TRIG[16], RELEASE_LAST)]
    like_stock(base, img, syms, "piste 1 CHORD, Keys OFF", lambda r: r.set_keys(0, False), seq)
    like_stock(base, img, syms, "piste 2 TONE sélectionnée (Keys ON dans son en-tête)",
               lambda r: (r.set_keys(1, True), r.select(1)), seq)
    a = like_stock(base, img, syms, "mode grille, piste 1 CHORD Keys ON", lambda r: r.set_grid(True), seq)
    check(G, all(ret == 0 and not notes(ev) for ret, ev in a), "mode grille : aucune note, rendu 0 (comme l'origine)")
    like_stock(base, img, syms, "FUNC tenu (bit 1), piste 1 CHORD Keys ON",
               lambda r: None, [(TRIG[1], FUNC_PRESS), (TRIG[1], RELEASE | 2)])
    for k in (1, 2, 3):
        like_stock(base, img, syms, f"KEY {k} tenu (code {k}), piste 1 CHORD Keys ON",
                   lambda r, k=k: r.set_modifier(k, True), [(TRIG[1], PRESS), (TRIG[1], RELEASE_LAST)])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True)
    ap.add_argument("--tweak", default=str(TWEAK),
                    help="JSON de Chord Keys (défaut : le 45-chord-keys.json du dépôt), ex. un JSON régénéré")
    ap.add_argument("--with", dest="others", default="", help="autres tweaks appliqués avant (ex. 6ch-usbup,arp)")
    ap.add_argument("--syntakt", help="Syntakt_OS1.42.syx (ou 1.41), pour les moteurs du Syntakt")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    by_id = {json.loads(f.read_text(encoding="utf-8"))["id"]: f for f in DEV.glob("[0-9]*.json")}
    others = [json.loads(by_id[i].read_text(encoding="utf-8")) for i in args.others.split(",") if i]
    tweak = json.loads(pathlib.Path(args.tweak).read_text(encoding="utf-8"))
    build.check_conflicts(others + [tweak])
    syms = {k: int(v, 16) for k, v in tweak.get("symbols", {}).items()}
    pl, _ = build.build_payload(others, stock, args.syntakt)
    base = build.apply_writes(stock, others)[0] + pl           # l'« origine » : les autres tweaks seuls
    img = build.apply_writes(stock, others + [tweak])[0] + pl
    print(f"firmware : {', '.join(t['id'] for t in others + [tweak])} ({args.tweak})")
    print("pointeur de KeyboardView::consumeKeyEvent")
    slot_tests(base, img, syms)
    print("origine (sans Chord Keys) : S1, relâchement perdu puis TRIG 1 sur la piste 2")
    s1(base, syms, "origine", stock_like=True)
    print("origine (sans Chord Keys) : S2, relâchement perdu puis TRIG 1 rejoué")
    s2(base, syms, "origine", stock_like=True)
    print("S1 avec Chord Keys : relâchement perdu, piste 2 non CHORD, TRIG 1")
    s1(img, syms, "S1")
    print("S2 avec Chord Keys : relâchement perdu, Keys OFF, TRIG 1")
    s2(img, syms, "S2")
    regressions(base, img, syms)
    print("émulation")
    check("émulation", not EMU_ERRORS, f"aucun accès hors mémoire ni arrêt imprévu dans tous les appels "
                                       f"{[(hex(f), e) for f, e in EMU_ERRORS[:3]]}")
    defect = [m for g, m in FAIL if g in ("S1", "S2")]
    rest = [m for g, m in FAIL if g not in ("S1", "S2")]
    print(f"\ncontrôles de S1/S2 en échec : {len(defect)}")
    for m in defect:
        print(f"  - {m}")
    print(f"autres contrôles en échec : {len(rest)}")
    for m in rest:
        print(f"  - {m}")
    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ÉCHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
