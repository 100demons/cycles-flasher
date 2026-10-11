"""Banc du séquenceur : la vraie interruption audio du Model:Cycles OS 1.13, bloc par bloc, avec ses événements.

mcengine.Engine n'appelle que la boucle des voix, avec des masques de trig et de fin de note posés à la main. Ici
tourne ce qui les fabrique, tel quel :
  - le constructeur d'événements du séquenceur (0x400548ce), sur un pattern factice (pas, vélocité, longueur LEN,
    note, verrous), et la file des événements (0x4009203c) datés en heure musicale (un pas = 5 400 000) ;
  - les notes jouées en direct (pads, clavier : 0x4005894a) ;
  - le corps de l'interruption audio (0x40058ca0 .. 0x40059382 : décompte des longueurs, événements, vélocité,
    masques ; la sauvegarde du contexte EMAC est sautée, et le détour de l'envoi USB de usb_steady.py s'il y est),
    puis 0x4005979e (lissage des paramètres, modulation de vélocité, LFO, boucle des voix, gain de vélocité) ;
  - mixeur, effets et sortie codec sautés (0x40056f58, 0x40056ea8, 0x400567ba) : la sortie lue est celle des voix
    après le gain de vélocité (0x80001858), ce que le mixeur reçoit.

Ce que ce banc a établi (notes/54 §2) : la vélocité du trig en 0x40fe4cdc dès le bloc du trig, son gain (vel/127
par défaut) appliqué après la boucle des voix à partir du bloc suivant ; la fin de note (release_mask, v+0x3c)
quand la longueur LEN est écoulée, jamais quand le trig suivant arrive avant ou dans le même bloc ; le reste de la
longueur en 0x800017b4, décompté de 0x40149310 (BPM x 120) à chaque bloc.

    rig = Rig(engine, bpm=120)          # engine : un mcengine.Engine (OS d'origine ou modifié)
    rig.set_step(t, 0, vel=127, length=15, note=48); rig.schedule_step(t, 0, rig.now + rig.blk)
    info = rig.block()                  # masques, vélocité, décomptes, sortie des voix...
"""
import struct

import numpy as np
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as mk

BASE, IMAGE_LEN = 0x40000400, 0x1a9d40   # MAIN OS d'origine ; au-delà : le BSS de l'OS
KIT = 0x4f000000                    # kit factice : 6 sons de 100 o
POOL = 0x4f100000                   # réserve d'événements
PAT = 0x4f200000                    # pattern factice : 6 pistes de 722 o, puis les verrous
MSG = 0x4e300000                    # message d'une note en direct
OFFP = 0x4e310000                   # décalage (micro-timing) rendu par le constructeur
ISTACK = 0x9000c000
VOICE0, VSTRIDE = 0x42308828, 0x31c
STEP = 5_400_000                    # un pas (double croche) en heure musicale
TEMPO = 0x40149310                  # BPM x 120 : ce que le décompte de LEN perd par bloc (l'heure musicale avance du double)
NOW = 0x8000184c
TARGETS, SMOOTH, PARAMS = 0x800015a0, 0x800011e8, 0x8000100c   # paramètres : cibles, lissage, valeurs lues
VEL, GAIN, GAIN_NEXT = 0x40fe4cdc, 0x40fe4c90, 0x40fe4cd0       # par piste, int16
ISR_FIRST = bytes.fromhex("a93c00000020")                         # 0x40058ca0 : movel #32,%macsr
LEN_LEFT = 0x800017b4                                            # par piste, int32
# LEN (index du menu TRIG) : 6 = 1/32, 13 = .938, 14 = 1/16 (défaut), 15 = 1.06, 30 = 1/8, 127 = INF
LEN_1_32, LEN_938, LEN_1_16, LEN_106, LEN_1_8, LEN_INF = 6, 13, 14, 15, 30, 127


def ensure_map(uc, addr, size):
    """Projette [addr, addr + size[ sauf ce qui l'est déjà."""
    regions = sorted((b, e + 1) for b, e, _ in uc.mem_regions())
    a, end = addr, addr + size
    for b, e in regions:
        if e <= a or b >= end:
            continue
        if b > a:
            uc.mem_map(a, b - a)
        a = max(a, e)
    if a < end:
        uc.mem_map(a, end - a)


class Rig:
    def __init__(self, engine, bpm=120, keep=()):
        """keep : [(début, fin)] de ce qui reste après l'image d'origine une fois l'OS démarré (le bloc de Model-TG) ;
        le reste est le BSS de l'OS, que le démarrage remet à zéro (morceaux d'une charge utile compris)."""
        e = self.e = engine
        uc = self.uc = e.uc
        a = BASE + IMAGE_LEN
        for lo, hi in sorted(keep) + [(BASE + len(e.img), BASE + len(e.img))]:
            if lo > a:
                uc.mem_write(a, bytes(lo - a))
            a = max(a, hi)
        ensure_map(uc, 0x40800000, 0x01800000)       # BSS de l'OS (séquenceur, vélocité, file d'événements)
        ensure_map(uc, 0x42400000, 0x00c00000)
        ensure_map(uc, 0x4e000000, 0x01400000)       # kit, pattern, messages factices
        ensure_map(uc, 0xfc040000, 0x10000)
        uc.reg_write(mk.UC_M68K_REG_SR, 0x2700)
        w = self.w32
        w(0x40fde8f8, POOL)
        e.call(0x40091d94, 0x42)                     # file et réserves d'événements
        w(0x800017e4, KIT)
        w(0x800017e8, KIT + 628)
        for t in range(6):
            s = self.sound(t)
            w(0x800015a0 + (153 + t) * 4, KIT)
            w(0x800015a0 + (147 + t) * 4, s)
            w(s + 88, 0)                             # son par défaut (0x40061866) : pas de modulation de vélocité,
            w(s + 92, 16384)
            w(s + 96, 127)                           # gain = vélocité / 127
        self.tempo = bpm * 120
        self.blk = 2 * self.tempo                    # heure musicale d'un bloc de 32 trames
        w(TEMPO, self.tempo)
        self.now = 1_000_000
        w(NOW, self.now)
        uc.hook_add(UC_HOOK_CODE, self._ret0, begin=0x40001fba, end=0x40001fba)   # boîte aux lettres de l'interface
        for fn in (0x40056f58, 0x40056ea8, 0x400567ba):                          # mixeur, effets, codec
            uc.hook_add(UC_HOOK_CODE, self._ret0, begin=fn, end=fn)
        uc.mem_write(PAT, bytes(30710))
        for t in range(6):
            b = PAT + 722 * t
            for off in (128, 192, 516, 580, 644):    # vélocité, longueur, ..., note : celles de la piste
                uc.mem_write(b + off, b"\xff" * 64)
            e.call(0x40061418, b, 0)                 # défauts de piste de l'OS (note 60, VEL 100, LEN 1/16)
        uc.mem_write(PAT + 4332, b"\xff" * (6 * 4385))   # aucun verrou
        uc.mem_write(PAT + 30667, bytes([0, 2]))         # vitesse commune 1x
        self.blocks = []

    @staticmethod
    def sound(t):
        return KIT + 0x1c + 100 * t

    def _ret0(self, uc, addr, size, ud):
        sp = uc.reg_read(mk.UC_M68K_REG_A7)
        uc.reg_write(mk.UC_M68K_REG_D0, 0)
        uc.reg_write(mk.UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
        uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)

    def w32(self, a, v):
        self.uc.mem_write(a, struct.pack(">I", v & 0xffffffff))

    def r32(self, a, signed=False):
        return struct.unpack(">i" if signed else ">I", self.uc.mem_read(a, 4))[0]

    def r16(self, a, signed=True):
        return struct.unpack(">h" if signed else ">H", self.uc.mem_read(a, 2))[0]

    def w8(self, a, v):
        self.uc.mem_write(a, bytes([v & 0xff]))

    # --- paramètres et pattern ---------------------------------------------------------------------------------
    def param(self, t, slot, value):
        """Paramètre de la piste (slot du descripteur, notes/14 §1 : 9 MACHINE, 0xa PITCH ... 0x12 DECAY ; valeur
        8.8), posé sans lissage : son, cible, état du lissage et valeur lue par la boucle des voix."""
        j = (0xe + 0x42 * t + 2 * slot) // 2
        v = struct.pack(">h", value)
        self.uc.mem_write(self.sound(t) + 20 + 2 * slot, v)
        self.uc.mem_write(TARGETS + 2 * j, v)
        self.uc.mem_write(SMOOTH + 4 * j, struct.pack(">i", value << 16))
        self.uc.mem_write(PARAMS + 2 * j, v)

    def set_step(self, t, step, vel=None, length=None, note=None, word=0x0081):
        """Un pas : word 0x0081 = trig, 0x6801 = trigless ; vel 1..127, length (index LEN), note : verrous du pas
        (sinon ceux de la piste)."""
        b = PAT + 722 * t
        self.uc.mem_write(b + 2 * step, struct.pack(">H", word))
        if vel is not None:
            self.w8(b + 128 + step, vel)
        if length is not None:
            self.w8(b + 192 + step, length)
        if note is not None:
            self.w8(b + 580 + step, note)

    def set_lock(self, t, step, slot, value):
        """Verrou de paramètre (p-lock) du pas : slot du descripteur, valeur 8.8."""
        self.uc.mem_write(PAT + 4332 + 4385 * t + 68 * step + 2 * slot, struct.pack(">h", value))

    def schedule_step(self, t, step, at):
        """Comme le séquenceur (0x400551a6 puis 0x4009203c) : l'événement du pas, daté de at (heure musicale)."""
        self.w32(OFFP, 0)
        ev = self.e.call(0x400548ce, t, PAT, KIT, step, 0, OFFP)
        assert ev, "pas de trig"
        self.e.call(0x4009203c, ev, at + self.r32(OFFP, True))
        return ev

    def live(self, onoff, t, note, vel=100):
        """Note en direct (pad, clavier), comme 0x4008171e / 0x4008145e sans retrig : onoff 1 appui, 2 relâché."""
        m = [0] * 14
        m[0], m[1], m[2], m[3] = t, note, vel, onoff
        m[5], m[8] = 0xffffffff, 0x40
        if onoff == 1:
            m[4] = self.r16(PAT + 722 * t + 710, False) | 0x30001
            m[9], m[10] = 0xffffffff, 127
        self.uc.mem_write(MSG, struct.pack(">14I", *[x & 0xffffffff for x in m]))
        self.w32(NOW, self.now)
        self.e.call(0x4005894a, MSG)

    # --- un bloc ---------------------------------------------------------------------------------------------------
    def block(self):
        """Un bloc de 32 trames : l'interruption audio, puis le traitement des voix. Rend ce que la machine voit et
        ce qui sort."""
        uc = self.uc
        self.w32(NOW, self.now)
        fp0 = ISTACK - 4                              # comme linkw %fp,#-168
        uc.reg_write(mk.UC_M68K_REG_A6, fp0)
        uc.reg_write(mk.UC_M68K_REG_A7, fp0 - 168)
        uc.reg_write(mk.UC_M68K_REG_D7, 0)
        start = 0x40058ca0
        if bytes(uc.mem_read(start, 6)) != ISR_FIRST:     # détour de l'envoi USB à heure fixe (usb_steady.py) :
            self.e.emac.macsr = 0x20                      # sans USB ici, son instruction d'origine seulement
            start += 6
        uc.emu_start(start, 0x40059382, count=5_000_000)
        pc = uc.reg_read(mk.UC_M68K_REG_PC)
        assert pc == 0x40059382 and not self.e.unmapped, (hex(pc), self.e.unmapped[:4])
        fp = uc.reg_read(mk.UC_M68K_REG_A6)
        fr = [self.r32(fp - 44 + 4 * k) for k in range(11)]
        six = lambda f: [f(t) for t in range(6)]
        info = dict(trig=fr[4], rel=fr[5],
                    vel=six(lambda t: self.r16(VEL + 2 * t) >> 8),
                    left=six(lambda t: self.r32(LEN_LEFT + 4 * t, True)),
                    pmod=six(lambda t: self.r32(0x80001830 + 4 * t, True)),
                    gain=six(lambda t: self.r16(GAIN + 2 * t)))      # appliqué à ce bloc
        self.e.call(0x4005979e, fp - 44)
        assert not self.e.unmapped, self.e.unmapped[:4]
        v32 = lambda t, o: self.r32(VOICE0 + VSTRIDE * t + o, True)
        info.update(machine=six(lambda t: v32(t, 0)), v34=six(lambda t: v32(t, 0x34)), v38=six(lambda t: v32(t, 0x38)),
                    amp=six(lambda t: v32(t, 0x230)), stage=six(lambda t: v32(t, 0x23c)),
                    gain_next=six(lambda t: self.r16(GAIN + 2 * t)),      # au suivant
                    out=np.frombuffer(bytes(uc.mem_read(0x80001858, 6 * 0x80)), ">i4").reshape(6, 32)
                    .astype(np.int64))
        self.blocks.append(info)
        self.now += self.blk
        return info
