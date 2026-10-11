"""Référence Python, au bit près, des machines VA (VA, VA KICK, VA SNARE, VA HIHAT : tools/machines/va/va.c,
notes/56 §4), d'après la description des algorithmes du firmware « Model-TG-VA-DR-v1 » de DavidCaruso.

Entiers 32 bits comme le code ColdFire : débordements modulo 2^32, décalages arithmétiques sur les signés. Sert à
tools/emu/test_va.py (le code compilé doit donner exactement ceci) et à tools/gen_va.py (les tables, par formule).

  - Track : l'état d'une piste, à la disposition de « struct trk » (84 o) ;
  - Dsp : les deux générateurs aléatoires et les 6 pistes ; fill() = va_fill (64 échantillons à 96 kHz), post() =
    va_post (gain et saturation des batteries) ; david=True refait les deux débordements 32 bits du VA HIHAT de
    son firmware (corrigés chez nous), pour la comparaison à son code ;
  - Bridge : ce que décide la passerelle à chaque bloc (potards, front de trig, voix muette, pas de la note).
"""
import math
import struct

M32 = 0xffffffff
KINDS = ("VA", "VA KICK", "VA SNARE", "VA HIHAT")
VA, KICK, SNARE, HIHAT = range(4)
MARK_OFF, MARK = 0x24, 0x56414d31            # repère dans la voix ('VAM1')
IDLE_LEVEL = 1 << 14


def u32(x):
    return x & M32


def s32(x):
    x &= M32
    return x - (1 << 32) if x & 0x80000000 else x


def s16(x):
    x &= 0xffff
    return x - 0x10000 if x & 0x8000 else x


def mulsl(a, b):                             # muls.l : 32 bits bas du produit, signé
    return s32(s32(a) * s32(b))


def mulq14(a, b):                            # a x b / 2^14 sans débordement
    a = u32(a)
    return u32(u32((a >> 14) * b) + (u32((a & 0x3fff) * b) >> 14))


def lcg(x):                                  # Numerical Recipes
    return u32(x * 1664525 + 1013904223)


def clamp(x):
    return 32767 if x > 32767 else (-32767 if x < -32767 else x)


def softclip(x):                             # 1,5 x - x^3 / 2^31 après bornage
    x = clamp(x)
    x2 = mulsl(x, x) >> 15
    x3 = mulsl(x, x2) >> 16
    return x + (x >> 1) - x3


def sine(ph):                                # sinus parabolique
    x = s16(u32(ph) >> 16)
    return (x * (32767 - abs(x))) >> 13


def shape(x, drive):                         # Drive puis bornage
    if drive:
        x = softclip(mulsl(x >> 1, drive) >> 11)
    return clamp(x)


def drive_gain(p):
    return ((((p << 7) + 4096) & 0xffff) * 2731) >> 12 if p else 0


def note_inc(step):                          # pas Q16 -> incrément de phase à 96 kHz (1,0 : 261,63 Hz)
    step = step or 0x10000
    return u32(u32(step * 357) + (u32(step * 52) >> 8)) >> 1


def dial(word):                              # mot 8.8 du paramètre -> 0..127
    d = s16(word)
    return min(max(d, 0) >> 8, 127)


def step_of(v232):                           # hauteur de TONE (voix + 232) -> pas Q16, formule de Model-TG
    return (u32((u32(v232) >> 4) * 93957) >> 12) if v232 else 0


# --- tables (formules ; tools/gen_va.py les écrit pour le code C) -------------------------------------------------
def tune_table():
    """Osc2 Tune : rapport de l'oscillateur 2 (Q16), -12..+12 demi-tons, courbe en cube (fine au centre)."""
    out = []
    for i in range(128):
        u = (i - 64) / 64 if i < 64 else (i - 64) / 63
        out.append(round(65536 * 2 ** (0.1 * u + 0.9 * u ** 3)))
    return out


def decay_table():
    """Sweep Time du KICK : facteur par bloc de 32 trames d'une constante de temps de 2 ms à 150 ms (Q15)."""
    return [round(32768 * math.exp(-(32 / 48000) / (0.002 * 75 ** (i / 127)))) for i in range(128)]


def filt_table():
    """Coefficient d'un filtre à un pôle à 96 kHz (Q15), coupure de 300 Hz à 16 kHz."""
    return [round(32768 * (1 - math.exp(-2 * math.pi * 300 * (16000 / 300) ** (i / 127) / 96000))) for i in range(128)]


TUNE, DECAY, FILT = tune_table(), decay_table(), filt_table()
HH_RATIO = (12857, 19063, 23146, 32733, 33817, 50099)      # TR-808 / 261,63 Hz, Q14
POST_GAIN = {KICK: 5461, SNARE: 6827, HIHAT: 10923}        # Q12 : x 4/3, 5/3, 8/3


def c_header():
    """va_tables.h, pour tools/machines/va/va.c."""
    def arr(name, typ, vals):
        rows = ",\n".join("\t" + ", ".join(str(v) for v in vals[k:k + 8]) for k in range(0, len(vals), 8))
        return f"static const {typ} {name}[{len(vals)}] = {{\n{rows}\n}};\n"
    return ("/* Ecrit par tools/gen_va.py d'apres les formules de tools/emu/va_ref.py : ne pas modifier. */\n"
            + arr("TUNE", "u32", TUNE) + arr("DECAY", "u32", DECAY) + arr("FILT", "s32", FILT))


# --- état --------------------------------------------------------------------------------------------------------
FIELDS = ("ph1", "ph2", "dr1", "dr2", "phase", "env", "click", "tenv", "lp1", "lp2")
TRK_SIZE = 84


class Track:
    """struct trk de va.c."""

    def __init__(self):
        for f in FIELDS:
            setattr(self, f, 0)
        self.hh = [0] * 6
        self.knob = [0] * 4
        self.trig = 0

    def words(self):
        return [getattr(self, f) for f in FIELDS] + self.hh + self.knob + [self.trig]

    def pack(self):
        return struct.pack(">21I", *[u32(w) for w in self.words()])

    @classmethod
    def unpack(cls, raw):
        t, w = cls(), struct.unpack(">21i", raw[:TRK_SIZE])
        for k, f in enumerate(FIELDS):
            setattr(t, f, w[k] if f in ("dr1", "dr2", "click", "tenv", "lp1", "lp2") else u32(w[k]))
        t.hh = [u32(x) for x in w[10:16]]
        t.knob, t.trig = list(w[16:20]), w[20]
        return t

    def same(self, other):
        return [u32(w) for w in self.words()] == [u32(w) for w in other.words()]


class Dsp:
    """Les générateurs (va_seed, dr_seed) et les 6 pistes de va.c."""

    def __init__(self, va_seed=0x6d2b79f5, dr_seed=0x1f123bb5):
        self.va_seed, self.dr_seed = va_seed, dr_seed
        self.trk = [Track() for _ in range(6)]

    def fill(self, tr, step, kind, david=False):
        """va_fill : 64 entiers signés (échantillon << 15) ; prend le trig de la piste. tr : Track ou numéro."""
        if isinstance(tr, int):
            tr = self.trk[tr]
        if kind == VA:
            return self._va(tr, step)
        if kind == KICK:
            return self._kick(tr, step)
        if kind == SNARE:
            return self._snare(tr, step)
        return self._hihat(tr, step, david)

    # VA ------------------------------------------------------------------------------------------------------
    @staticmethod
    def _walk(d, down):
        if not down:
            return d + 1 if d + 1 <= 40 else d
        return d - 1 if d - 1 >= -40 else d

    @staticmethod
    def _blep(d, k):
        x = u32(32768 - (u32((d >> 8) * k) >> 16))
        return u32(x * x) >> 15

    def _osc(self, acc, ph, inc, gain, wave):
        if gain == 0:
            return u32(ph + (inc << 6))
        k = inc >> 8
        k = 0x80000000 // (k or 1)
        for i in range(64):
            if wave == 2:
                x = s16(u32(ph + 0xc0000000) >> 16)
                x = 32768 - 2 * abs(x)
            elif wave == 0:
                x = s16(u32(ph + 0x80000000) >> 16)
                if ph < inc:
                    x += self._blep(ph, k)
                elif u32(-ph) < inc:
                    x -= self._blep(u32(-ph), k)
            else:
                p2 = ph ^ 0x80000000
                x = 32767 if ph < 0x80000000 else -32767
                if ph < inc:
                    x -= self._blep(ph, k)
                elif u32(-ph) < inc:
                    x += self._blep(u32(-ph), k)
                elif p2 < inc:
                    x += self._blep(p2, k)
                elif u32(-p2) < inc:
                    x -= self._blep(u32(-p2), k)
            acc[i] = s32(acc[i] + x * gain)
            ph = u32(ph + inc)
        return ph

    @staticmethod
    def wave_of(knob):
        return 0 if knob < 43 else (1 if knob < 86 else 2)

    def _va(self, tr, step):
        mix = 2 * tr.knob[3]
        if mix >= 254:
            mix = 256
        r = TUNE[tr.knob[2]] >> 1
        inc1 = note_inc(step)
        inc2 = u32(u32((inc1 >> 15) * r) + (u32((inc1 & 0x7fff) * r) >> 15))
        self.va_seed = seed = lcg(self.va_seed)
        tr.dr1 = self._walk(tr.dr1, seed & 0x80000000)
        inc1 = u32(inc1 + (inc1 >> 16) * tr.dr1)
        tr.dr2 = self._walk(tr.dr2, seed & 0x40000000)
        inc2 = u32(inc2 + (inc2 >> 16) * tr.dr2)
        if tr.trig:
            tr.trig = 0
            tr.ph1 = 0x80000000
            tr.ph2 = u32((seed >> 3) + 0x70000000)
        acc = [0] * 64
        tr.ph1 = self._osc(acc, tr.ph1, inc1, 256 - mix, self.wave_of(tr.knob[0]))
        tr.ph2 = self._osc(acc, tr.ph2, inc2, mix, self.wave_of(tr.knob[1]))
        return [s32(clamp(a >> 8) << 15) for a in acc]

    # batteries ------------------------------------------------------------------------------------------------
    def _kick(self, tr, step):
        drive = drive_gain(tr.knob[2])
        if tr.trig:
            tr.trig, tr.phase, tr.env, tr.click = 0, 0, 0x8000, tr.knob[3] << 23
        base = mulq14(note_inc(step), 3444)
        e0 = tr.env
        e1 = u32(e0 * DECAY[tr.knob[1]]) >> 15
        tr.env = e1
        depth = u32(tr.knob[0] * 516)
        i0 = mulq14(base, (u32(e0 * depth) >> 15) + 16384)
        i1 = mulq14(base, (u32(e1 * depth) >> 15) + 16384)
        dinc = s32(i1 - i0) >> 6
        ph, cur, clk, seed, out = tr.phase, i0, s32(tr.click), self.dr_seed, []
        for _ in range(64):
            ph = u32(ph + cur)
            cur = u32(cur + dinc)
            x = sine(ph)
            if clk:
                seed = lcg(seed)
                x += mulsl(s16(seed >> 16), clk >> 15) >> 15
                clk -= (clk >> 7) + 1
                clk = max(clk, 0)
            out.append(s32(shape(x, drive) << 15))
        tr.click, tr.phase, self.dr_seed = clk, ph, seed
        return out

    def _snare(self, tr, step):
        drive = drive_gain(tr.knob[3])
        if tr.trig:
            tr.trig, tr.phase, tr.env, tr.tenv = 0, 0, 0x8000, 0x3fffffff
        nmix = 128 if tr.knob[0] == 127 else tr.knob[0]
        tmix = 128 - nmix
        coef = FILT[tr.knob[2]]
        e0 = tr.env
        e1 = u32(e0 * 31344) >> 15
        tr.env = e1
        depth = u32(tr.knob[1] * 258)
        m0 = (u32(e0 * depth) >> 15) + 16384
        m1 = (u32(e1 * depth) >> 15) + 16384
        base = mulq14(note_inc(step), 11272)
        i0, i1 = mulq14(base, m0), mulq14(base, m1)
        dinc = s32(i1 - i0) >> 6
        te = s32(tr.tenv)
        te -= te >> 7
        tr.tenv = te
        tamp = mulsl(te >> 15, tmix) >> 7
        ph, cur, lp1, lp2, seed, out = tr.phase, i0, s32(tr.lp1), s32(tr.lp2), self.dr_seed, []
        for _ in range(64):
            ph = u32(ph + cur)
            cur = u32(cur + dinc)
            tone = mulsl(sine(ph), tamp) >> 15
            seed = lcg(seed)
            n = s16(seed >> 16)
            lp1 = s32(lp1 + (mulsl(n - lp1, coef) >> 15))
            hp = s32(lp1 - lp2)
            lp2 = s32(lp2 + (hp >> 5))
            out.append(s32(shape(s32((mulsl(hp, nmix) >> 7) + tone), drive) << 15))
        tr.phase, tr.lp1, tr.lp2, self.dr_seed = ph, lp1, lp2, seed
        return out

    @staticmethod
    def hihat_incs(step, spread, david=False):
        """Les 6 incréments du VA HIHAT. david : le calcul de son firmware (somme modulo 2^32, produit sur 32 bits)."""
        inc = note_inc(step)
        incs = [mulq14(inc, r) for r in HH_RATIO]
        mean = (u32(sum(incs)) if david else sum(incs)) // 6
        if david:
            return [u32((mulsl(s32(i - mean) >> 2, 2 * spread) >> 5) + mean) for i in incs]
        return [u32(((s32(i - mean) >> 2) * spread >> 4) + mean) for i in incs]

    @staticmethod
    def hihat_overflows(step, spread):
        """Vrai si le firmware de David déborde 32 bits pour cette note et ce Spread (fréquences fausses)."""
        return Dsp.hihat_incs(step, spread, True) != Dsp.hihat_incs(step, spread, False)

    def _hihat(self, tr, step, david):
        drive, nlev = drive_gain(tr.knob[3]), tr.knob[2]
        tr.trig = 0
        coef = FILT[73 + ((tr.knob[0] * 89) >> 8)]
        incs = self.hihat_incs(step, tr.knob[1], david)
        amp = ((128 - nlev) * 10000) >> 7
        lp1, lp2, seed, out = s32(tr.lp1), s32(tr.lp2), self.dr_seed, []
        for _ in range(64):
            cnt = 0
            for k in range(6):
                tr.hh[k] = u32(tr.hh[k] + incs[k])
                cnt += tr.hh[k] >> 31
            seed = lcg(seed)
            x = s32((mulsl(s16(seed >> 16), nlev) >> 7) + amp * (3 - cnt))
            u = s32(x - lp1)
            g = mulsl(u, coef) >> 15
            lp1 = s32(lp1 + g)
            w = s32(u - g - lp2)
            g = mulsl(w, coef) >> 15
            lp2 = s32(lp2 + g)
            out.append(s32(shape(s32(w - g), drive) << 15))
        tr.lp1, tr.lp2, self.dr_seed = lp1, lp2, seed
        return out

    @staticmethod
    def post(buf, kind):
        """va_post : 32 mots de sortie (après VCA et PUNCH) des batteries ; le VA ne passe pas par là."""
        if kind == VA:
            return list(buf)
        g = POST_GAIN[kind]
        return [s32(clamp(softclip(mulsl(s32(w) >> 16, g) >> 12)) << 16) for w in buf]


class Bridge:
    """Les décisions de la passerelle à un bloc, d'après la voix et les paramètres vus à l'entrée de va_update :
    voix (octets de la voix, au moins jusqu'à +0x238), params (octets de p, au moins jusqu'à +0x1e)."""

    def __init__(self, dsp=None):
        self.dsp = dsp or Dsp()

    @staticmethod
    def idle(vb):
        v = lambda o: struct.unpack_from(">i", vb, o)[0]
        return not v(0x34) and not v(0x38) and abs(v(0x230)) < IDLE_LEVEL and abs(v(0x234)) < IDLE_LEVEL

    def update(self, t, vb, pb):
        """va_update : rend (premier bloc, front, muette) et met l'état de la piste à jour."""
        v = lambda o: struct.unpack_from(">i", vb, o)[0]
        tr = self.dsp.trk[t]
        first = u32(v(MARK_OFF)) != MARK
        if first:
            self.dsp.trk[t] = tr = Track()
            tr.trig = 1
        tr.knob = [dial(struct.unpack_from(">h", pb, 0x16 + 2 * k)[0]) for k in range(4)]
        edge = bool(v(0x34)) and not v(0x38)
        if edge:
            tr.trig = 1
        return dict(first=first, edge=edge, idle=self.idle(vb))
