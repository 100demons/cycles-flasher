"""Tables de la machine TINY2 (tools/machines/tiny2/tiny2_tables.h), calculées ici : ne pas modifier le .h à la main.

Un module à part pour que gen_tiny2.py --check et les épreuves (tools/emu/) les recalculent sans l'OS ni la chaîne
m68k. Tout est déterministe : mêmes entiers sur toute machine (math de Python, arrondis explicites).

Conventions : Qn = entier signé 32 bits valant x * 2^n ; « inc » = incrément de phase 2^32 * f / 48000 ; un potard
est un indice 0..127 (129 points, le dernier répète le 127) ; une table « par potard » se lit par interpolation
linéaire du potard 8.8 (lutk).
"""
import math

FS = 48000.0
MODELS = ("NYB", "GND", "BNJ", "RYT", "FRS", "RNG", "PLS", "SCN", "KOS")
# La fenetre de valeur de SHAPE tient trois caracteres, comme les autres noms.
SHAPE_NAMES = MODELS
# niveau de chaque modèle (Q29 : 1,0 = 1 << 29), mesuré à l'ordinateur (tools/emu/tiny2_levels.py : intensité sonore
# BS.1770 d'un riff dans le réglage d'usine, 64 . 64 . 64) pour que les modèles sonnent à 3 dB près.
# Trims Feral : NYB -6 dB, FRS +6 dB, KOS -6 dB, PLS +6 dB, SCN +6 dB.
GAIN = [0.421, 0.58, 0.39, 1.82, 1.8157, 0.41, 2.953, 1.9155, 0.4461]

def s32c(v):
    return max(-2 ** 31, min(2 ** 31 - 1, int(v)))


def u32c(v):
    return max(0, min(2 ** 32 - 1, int(v)))


def qn(x, n):
    """x en Qn, arrondi, saturé à 32 bits signés."""
    return s32c(round(x * 2 ** n))


def q31(x):
    return qn(x, 31)


def inc_of(hz):
    return u32c(round(2 ** 32 * hz / FS))


def knobs(fn):
    """129 points, potard 0..127 (le 129e répète le 127 : l'interpolation lit toujours i + 1)."""
    return [fn(float(min(k, 127))) for k in range(129)]


def kexp3(k, a, m, b):
    """Exponentielle par (0, a) (64, m) (127, b)."""
    return a * (m / a) ** (k / 64.0) if k <= 64 else m * (b / m) ** ((k - 64.0) / 63.0)


def klin3(k, a, m, b):
    return a + (m - a) * k / 64.0 if k <= 64 else m + (b - m) * (k - 64.0) / 63.0


# --- noyau commun ---------------------------------------------------------------------------------------------
def t_sin():
    return [q31(math.sin(2 * math.pi * i / 1024)) for i in range(1025)]


def t_inc():
    return [inc_of(440.0 * 2 ** ((n - 69) / 12)) for n in range(129)]


def t_exp2():
    """2^(i/256), i = 0..256, en Q30 (de 1,0 à 2,0)."""
    return [qn(2 ** (i / 256), 30) if i < 256 else 2 ** 31 for i in range(257)]


def t_log2():
    """log2(1 + i/128), i = 0..128, en Q16."""
    return [int(round(math.log2(1 + i / 128) * 65536)) for i in range(129)]


def t_lp1():
    """Coefficient d'un passe-bas à un pôle (Q31) pour une coupure de i x 93,75 Hz (indice = inc >> 23), i = 0..256."""
    return [q31(min(1 - math.exp(-2 * math.pi * i * 93.75 / FS), 0.999999)) for i in range(257)]


# --- BYTE : banque de formules (les 16 du prototype, constantes d'origine, bits de décalage) -----------------------
# (nom, constantes, masque des constantes qui sont des décalages)
BYTE_BANK = (
    ("t&t>>8", (8,), 1),
    ("t*(42&t>>10)", (42, 10), 2),
    ("t*((t>>12|t>>8)&63&t>>4)", (12, 8, 63, 4), 11),
    ("t*5&t>>7|t*3&t>>10", (5, 7, 3, 10), 10),
    ("(t*3&t>>6)%76", (3, 6, 76), 2),
    ("t*(t>>11&t>>8&123&t>>3)", (11, 8, 123, 3), 11),
    ("t*(t>>9&10|t>>11&24^t>>10&15&t>>15)", (9, 10, 11, 24, 10, 15, 15), 85),
    ("t*(3+(1^t>>10&5))*(5+(3&t>>14))>>(t>>8&3)", (3, 10, 5, 5, 3, 14, 8, 3), 98),
    ("t*(t>>8|t>>9)&46&t>>8^(t&t>>13|t>>6)", (8, 9, 46, 8, 13, 6), 59),
    ("(t>>7|t|t>>6)*10+4*(t&t>>13|t>>6)", (7, 6, 10, 4, 13, 6), 51),
    ("t%125&t>>8|t>>4|t*t>>8&t>>8", (125, 8, 4, 8, 8), 30),
    ("t*(t>>12)*64+(t>>1)*(t>>10)*(t>>11)*48>>(t>>16|t>>17&1)", (12, 64, 1, 10, 11, 48, 16, 17), 221),
    ("t%(t/(t>>9|t>>13))", (9, 13), 3),
    ("t/(t%(t>>8|t>>16))", (8, 16), 3),
    ("t*-(t>>8|t|t>>9|t>>13)^t", (8, 9, 13), 7),
    ("(t<<5)^-(t>>3&1)", (5, 3), 3),
)
BYTE_ORDER = (15, 0, 3, 1, 6, 11, 8, 12, 5, 7, 14, 9, 13, 4, 2, 10)    # du clairsemé au dense (platitude spectrale)


def t_byte():
    k = []
    for _, c, _ in BYTE_BANK:
        k += list(c) + [0] * (8 - len(c))
    return dict(T_BB_K=k, T_BB_N=[len(c) for _, c, _ in BYTE_BANK], T_BB_SH=[m for _, _, m in BYTE_BANK],
                T_BB_ORDER=list(BYTE_ORDER))

# --- FOUR -----------------------------------------------------------------------------------------------------
def sym_of(s):
    return 0.5 - 0.15 * s / 64.0 if s <= 64 else 0.35 - 0.30 * (s - 64.0) / 63.0


def t_four():
    spread = lambda c: 1.5 ** (c / 64.0) if c <= 64 else 1.5 * 2 ** ((c - 64.0) / 63.0)
    return dict(T_FOUR_SPREAD=knobs(lambda c: qn(spread(c), 16)),
                T_FOUR_RUP=knobs(lambda s: qn(1.0 / sym_of(s), 26)),        # 1 / symétrie (jusqu'à 20)
                T_FOUR_RDN=knobs(lambda s: qn(1.0 / (1.0 - sym_of(s)), 26)))

# --- CHAO -----------------------------------------------------------------------------------------------------
CHAO_SNAP = (3.20, 3.50, 3.555, 3.835, 3.6285, 3.7397)      # périodes 2, 4, 8, 3, 6, 5 (mesurées)


def chao_r(c):
    if c <= 40:
        return CHAO_SNAP[int(max(0.0, min(5.0, c / 41.0 * 6.0)))]
    return 3.570 + 0.430 * (c - 41.0) / 86.0


def t_chao():
    return dict(T_CHAO_R4=knobs(lambda c: q31(chao_r(c) / 4.0)))

# --- PLSR -----------------------------------------------------------------------------------------------------
def t_plsr():
    return dict(T_PLSR_SMUL=knobs(lambda c: qn(kexp3(c, 1.0, 4.0, 32.0), 16)),
                T_PLSR_WMUL=knobs(lambda c: qn(max(kexp3(c, 1.0, 4.0, 32.0) / 2.0, 1.0), 16)))

# --- RATI : 1 / n^0,8 -----------------------------------------------------------------------------------------------
def t_rati():
    return dict(T_RATI_NORM=[q31(1.0) if n == 0 else q31(min(0.9999999, n ** -0.8)) for n in range(17)])

# --- CA ---------------------------------------------------------------------------------------------------------------
# --- GNDY ---------------------------------------------------------------------------------------------------------
def t_gndy():
    def dstep(s):
        return (0.3 * s / 64.0 if s <= 64 else 0.3 + 0.7 * (s - 64.0) / 63.0) * 10.0

    at = math.atan(10.0)
    return dict(
        T_GN_N=knobs(lambda k: max(3, min(24, int(round(kexp3(k, 3.0, 10.0, 24.0)))))),
        T_GN_AST=knobs(lambda k: qn(kexp3(k, 0.005, 0.05, 0.25) * 10.0, 28)),             # pas d'amplitude, Q28
        T_GN_WS=knobs(lambda k: q31(min(k / 64.0, 1.0))),
        T_GN_DST=knobs(lambda k: qn(dstep(k), 25)),                                       # pas de duree, Q25
        T_GN_NW=knobs(lambda k: qn(1.0 if k <= 64 else 1.0 - (k - 64.0) / 63.0, 16)),
        T_CAUCHY=[qn(0.1 * math.tan(at * (i / 128.0 - 1.0)), 30) for i in range(258)])    # 0,1 tan(atan(10) x), x = -1..1


# --- filtres : tan(pi f / fs) et tanh ----------------------------------------------------------------------------
def t_tan():
    """g = tan(pi f / fs) en Q24 pour une coupure de i x 93,75 Hz (indice = inc >> 23), i = 0..256, plafonnee a 0,45 fs."""
    return [qn(math.tan(math.pi * min(i * 93.75, 0.45 * FS) / FS), 24) for i in range(257)]


def t_tanh():
    """tanh(u) en Q30 pour u = i / 64, i = 0..256 (u de 0 a 4)."""
    return [qn(math.tanh(i / 64.0), 30) for i in range(257)]

# --- SCAN : synthese par balayage ---------------------------------------------------------------------------------
def t_scan():
    n = 32                                        # masses de l'anneau (NMASS de tiny2_eng_d.h)
    wide = [0.5 - 0.5 * math.cos(2 * math.pi * i / n) for i in range(n)]
    quarter = [0.5 + 0.5 * math.cos(math.pi * (i - n / 4.0) / (n / 8.0)) if abs(i - n / 4.0) < n / 8.0 else 0.0
               for i in range(n)]
    # raideur : celle d'un anneau de 64 masses (0,0003 ; 0,01 ; 0,5) divisee par 4, les modes gardent leur frequence
    return dict(T_SC_K=knobs(lambda k: q31(min(kexp3(k, 0.0003, 0.01, 0.5) / 4.0, 0.95))),
                T_SC_WIDE=[qn(v, 30) for v in wide], T_SC_QUART=[qn(v, 30) for v in quarter])

# --- BENJ : le Benjolin -------------------------------------------------------------------------------------------
def t_benj():
    def fc0(k):
        # FINE : 120 Hz -> 6 kHz au centre -> 16 kHz. Le centre etait a 700 Hz (BNJ etouffe).
        return kexp3(k, 120.0, 6000.0, 16000.0)

    return dict(T_BJ_F2=knobs(lambda k: inc_of(kexp3(k, 0.1, 8.0, 4000.0))),            # OSC 2 : COLOR
                T_BJ_RUN=knobs(lambda k: qn(4.0 * (k / 127.0) ** 2, 16)),               # RUN 1 / RUN 2 : octaves, Q16
                T_BJ_FC=knobs(lambda k: inc_of(fc0(k))),                                # coupure du filtre : FINE
                T_BJ_FR=[round(2.0 ** (2.5 * (j / 7.0 - 0.5)) * 65536) for j in range(8)])   # le rungler deplace la coupure de 2,5 octaves

# --- HAVC : arpeges qui bouclent ----------------------------------------------------------------------------------
HV_INJECT = ((3, 2), (4, 3), (5, 4), (9, 5), (7, 6), (8, 7), (13, 8))        # (rapport p/q) : boucle de q pas
HV_XOR = ((5, 4), (3, 2), (4, 3), (9, 5), (7, 5))


def hv_q(k):
    """Q du filtre de la voix HAVC : 1,2 (pincee) -> 2,6 (rebond) -> 1,6 (glissando)."""
    return 1.2 + 1.4 * k / 64.0 if k <= 64 else 2.6 - (k - 64.0) / 63.0


def hv_alpha(k):
    """Decroissance de l'enveloppe par echantillon : tau 30 ms (pincee) -> 150 ms (rebond), puis tend vers 0 (glissando)."""
    u = min(k, 64.0) / 64.0
    v = max(0.0, (k - 64.0) / 63.0)
    return 1.0 / (0.03 * 5.0 ** u * FS) * (1.0 - v) ** 2


def t_havc():
    def frac32(x):
        return u32c(round((x - math.floor(x)) * 2 ** 32)) & 0xffffffff

    drift = [frac32(1.5 * 2 ** ((3.0 * 20.0 ** (i / 31.0)) / 1200.0)) for i in range(32)]
    return dict(T_HV_INJ=[frac32(p / q) for p, q in HV_INJECT],
                T_HV_XOR=[frac32(p / q) for p, q in HV_XOR],
                T_HV_DRIFT=drift,
                T_HV_PNEW=knobs(lambda k: u32c(round(min(max(0.0, (k - 41.0) / 59.0), 1.0) * 0.25 * 2 ** 32))),
                # CONTOUR : pincee (0) -> rebond (64) -> glissando (127), par potard
                T_HV_V=knobs(lambda k: q31(max(0.0, (k - 64.0) / 63.0))),                      # part de glissando
                T_HV_K=knobs(lambda k: qn(1.0 / hv_q(k), 24)),                                  # 1 / Q du filtre, Q24
                T_HV_D1=knobs(lambda k: q31(math.exp(-hv_alpha(k)))),                           # decroissance de l'enveloppe par echantillon
                T_HV_D07=knobs(lambda k: q31(math.exp(-0.7 * hv_alpha(k)))),                    # idem, a la puissance 0,7 (le gain)
                T_HV_E07=knobs(lambda k: q31((1.0 - 0.15 * max(0.0, (k - 64.0) / 63.0)) ** 0.7)),   # niveau de depart ^ 0,7
                T_HV_ATT=[q31((i / 96.0) ** 0.7) for i in range(97)])                          # attaque de 2 ms, ^ 0,7


# --- assemblage -----------------------------------------------------------------------------------------------
def all_tables():
    """(constantes, tableaux) dans l'ordre d'émission : tableaux = [(nom, type C, valeurs)]."""
    t = [("T_SIN", "s32", t_sin()), ("T_INC", "u32", t_inc()), ("T_EXP2", "u32", t_exp2()),
         ("T_LOG2", "s32", t_log2()), ("T_LP1", "s32", t_lp1()), ("T_TAN", "s32", t_tan()),
         ("T_TANH", "s32", t_tanh()), ("T_GAIN", "s32", [qn(g, 29) for g in GAIN])]
    for part in (t_byte(), t_four(), t_chao(), t_plsr(), t_rati(), t_gndy(), t_scan(), t_benj(), t_havc(),
                 ):
        for name, vals in part.items():
            t.append((name, "u32" if name in ("T_BJ_F2", "T_BJ_FC", "T_BJ_FR", "T_HV_INJ", "T_HV_XOR",
                                        "T_HV_DRIFT", "T_HV_PNEW") else "s32", vals))
    consts = {}
    return consts, t


def header():
    consts, tabs = all_tables()
    out = ["/* Tables de TINY2, calculees par tools/tiny2_tables.py (via gen_tiny2.py) : ne pas modifier a la main. */",
           "#ifndef TINY2_TABLES_H", "#define TINY2_TABLES_H", ""]
    for name, v in consts.items():
        out.append(f"#define {name} ({v})")
    out.append("")
    for name, typ, vals in tabs:
        out.append(f"static const {typ} {name}[{len(vals)}] = {{")
        for i in range(0, len(vals), 6):
            out.append("\t" + ", ".join(f"{x:#010x}u" if typ == "u32" else str(x) for x in vals[i:i + 6]) + ",")
        out.append("};")
    return "\n".join(out + ["", "#endif", ""])
