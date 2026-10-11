/*
 * Machines VA : « VA », « VA KICK », « VA SNARE », « VA HIHAT », quatre machines ajoutees du Model:Cycles (OS 1.13),
 * d'apres celles du firmware « Model-TG-VA-DR-v1 » de DavidCaruso (synthe soustractif leger a 2 oscillateurs,
 * grosse caisse, caisse claire et charleston « analogiques »). Reecrites ici en C a partir de la description de
 * leurs algorithmes (notes/56 §4) : aucun octet de son firmware. Le son est le meme, echantillon par echantillon
 * (tools/emu/test_va.py le compare a tools/emu/va_ref.py, et a son firmware avec --david), sauf dans l'aigu du
 * VA HIHAT, ou deux calculs debordaient 32 bits (corriges, voir hihat()).
 *
 * Contrat de la boucle des voix (notes/14, comme MACRO, notes/43) : update(pmod, v, p) puis render(out, v), une fois
 * par bloc de 32 trames a 48 kHz. pmod = note du trig (demi-tons << 16) ; v = voix du Cycles (0x31c o) ; p =
 * parametres de la piste (mots 8.8 : +0x16 COLOR, +0x18 SHAPE, +0x1a SWEEP, +0x1c CONTOUR) ; v+0x34 / v+0x38 : trig
 * de ce bloc / du bloc precedent ; out : 32 x int32.
 *
 * update (le meme pour les 4 machines) : l'update de TONE (0x400aa7b8 : la hauteur en v+232, l'enveloppe d'ampli
 * reglee par DECAY et GATE, PUNCH), comme le firmware de David, puis les 4 potards (0..127) et le front de trig.
 * render : 64 echantillons a 96 kHz (va_fill) dans le tampon de TONE (0x8000c05c : 8 mots d'historique, puis les 64),
 * puis la fin du render de TONE : decimation 2:1 (0x400a9f58), enveloppe d'ampli (0x400a9252), VCA (0x400a9430),
 * PUNCH (0x400a967a) ; pour les batteries, un gain fixe et une saturation douce (va_post).
 *
 * Front de trig : un trig dans ce bloc qui ne suit pas celui du bloc precedent (v+0x34 pose, v+0x38 nul), comme le
 * firmware de David ; et le 1er bloc d'une voix passee sur l'une de ces machines (repere en v+0x24, efface par la
 * remise a zero de la voix, 0x400a7ab8, a chaque changement de machine : l'OS ne change de machine qu'au bloc qui
 * suit le trig, ou v+0x34 est deja retombe). L'etat de la piste repart alors de zero.
 *
 * Voix muette (ni trig, enveloppe d'ampli sous 2^14) : ni l'update de TONE ni le rendu, sortie nulle (comme MACRO).
 *
 * Arithmetique : entiers 32 bits, debordements modulo 2^32 (multiplications par mulsl/mulul, sans comportement
 * indefini), decalages arithmetiques sur les signes. Pas de 64 bits (pas de bibliotheque : -nostdlib).
 */
typedef signed char s8;
typedef short s16;
typedef int s32;
typedef unsigned int u32;

#include "va_tables.h"                           /* TUNE, DECAY, FILT : ecrits par tools/gen_va.py (formules) */

#define CYC_VOICE0  0x42308828
#define CYC_VSTRIDE 0x31c
#define MARK_OFF    0x24                         /* champ efface par la remise a zero, que TONE n'utilise pas */
#define MARK        0x56414d31                   /* 'VAM1' */
#define IDLE_LEVEL  (1 << 14)                    /* enveloppe d'ampli sous -102 dB : voix muette (comme MACRO) */

#define TONE_UPDATE(m, v, p) ((void (*)(s32, char *, const char *))0x400aa7b8)(m, v, p)
#define DECIMATE(v, b, o)    ((void (*)(char *, s32 *, s32 *))0x400a9f58)(v, b, o)
#define AMP_ENV(v)           ((void (*)(char *))0x400a9252)(v)
#define VCA(o, v)            ((void (*)(s32 *, char *))0x400a9430)(o, v)
#define PUNCH(o, v)          ((void (*)(s32 *, char *))0x400a967a)(o, v)
#define TONE_BUF             ((s32 *)0x8000c05c)  /* tampon 2x du render de TONE (SRAM), 8 + 64 mots */

#define V32(o)      (*(s32 *)(v + (o)))
#define P16(o)      (*(const s16 *)(p + (o)))

enum { VA, KICK, SNARE, HIHAT };

/* etat d'une piste (84 o ; tools/emu/va_ref.py, Track, a la meme disposition) */
struct trk {
	u32 ph1, ph2;        /* VA : phases des oscillateurs 1 et 2 */
	s32 dr1, dr2;        /* VA : derives lentes (-40..40) */
	u32 phase;           /* KICK, SNARE : phase du sinus */
	u32 env;             /* KICK, SNARE : enveloppe de hauteur (Q15) */
	s32 click;           /* KICK : bruit d'attaque */
	s32 tenv;            /* SNARE : enveloppe du corps */
	s32 lp1, lp2;        /* SNARE, HIHAT : filtres */
	u32 hh[6];           /* HIHAT : phases des 6 oscillateurs carres */
	s32 knob[4];         /* COLOR, SHAPE, SWEEP, CONTOUR du bloc, 0..127 */
	s32 trig;            /* front de trig, pris par le prochain rendu */
};

struct trk va_trk[6];
u32 va_seed = 0x6d2b79f5;                        /* derives du VA : un generateur pour toutes les pistes */
u32 dr_seed = 0x1f123bb5;                        /* bruit des batteries : un generateur pour toutes les pistes */

static inline s32 mulsl(s32 a, s32 b)            /* muls.l : 32 bits bas du produit */
{
	return (s32)((u32)a * (u32)b);
}

static inline u32 mulq14(u32 a, u32 b)           /* a x b / 2^14 sans debordement (b < 2^18) */
{
	return (a >> 14) * b + (((a & 0x3fff) * b) >> 14);
}

static inline u32 lcg(u32 x)                     /* generateur congruentiel de Numerical Recipes */
{
	return x * 1664525u + 1013904223u;
}

static inline s32 shl(s32 x, int n)            /* decalage a gauche d'un signe, sans comportement indefini */
{
	return (s32)((u32)x << n);
}

static inline s32 clamp(s32 x)
{
	return x > 32767 ? 32767 : (x < -32767 ? -32767 : x);
}

static inline s32 softclip(s32 x)                /* 1,5 x - x^3 / 2^31 apres bornage : saturation douce */
{
	s32 x2, x3;

	x = clamp(x);
	x2 = (x * x) >> 15;
	x3 = (x * x2) >> 16;
	return x + (x >> 1) - x3;
}

static inline s32 sine(u32 ph)                   /* sinus parabolique : +-32 766, harmonique 3 a -28,6 dB */
{
	s32 x = (s16)(ph >> 16);

	return (x * (32767 - (x < 0 ? -x : x))) >> 13;
}

static inline s32 shape(s32 x, s32 drive)        /* Drive (gain puis saturation douce), puis bornage */
{
	if (drive)
		x = softclip(mulsl(x >> 1, drive) >> 11);
	return clamp(x);
}

static inline u32 note_inc(u32 step)             /* pas Q16 de la note -> increment de phase a 96 kHz */
{
	if (!step)
		step = 0x10000;
	return (step * 357u + ((step * 52u) >> 8)) >> 1;        /* 1,0 : 261,63 Hz (do 4) */
}

/* ---- VA : deux oscillateurs (scie, carre, triangle), PolyBLEP, derive lente ------------------------------------- */

static inline s32 walk(s32 d, u32 down)          /* marche aleatoire bornee a +-40 */
{
	if (!down)
		return d + 1 <= 40 ? d + 1 : d;
	return d - 1 >= -40 ? d - 1 : d;
}

static inline s32 blep(u32 d, u32 k)             /* (1 - d / increment)^2 en Q15 : PolyBLEP a 2 points */
{
	u32 x = 32768u - (((d >> 8) * k) >> 16);

	return (s32)((x * x) >> 15);
}

static u32 osc(s32 *acc, u32 ph, u32 inc, s32 gain, s32 wave)
{
	u32 k;
	int i;

	if (!gain)                                   /* oscillateur coupe : il avance quand meme */
		return ph + (inc << 6);
	k = inc >> 8;
	k = 0x80000000u / (k ? k : 1);
	for (i = 0; i < 64; i++) {
		s32 x;

		if (wave == 2) {                         /* triangle, 0 en phase 0, montant (sans BLEP) */
			x = (s16)((ph + 0xc0000000u) >> 16);
			x = 32768 - 2 * (x < 0 ? -x : x);
		} else if (wave == 0) {                  /* scie montante */
			x = (s16)((ph + 0x80000000u) >> 16);
			if (ph < inc)
				x += blep(ph, k);
			else if (0u - ph < inc)
				x -= blep(0u - ph, k);
		} else {                                 /* carre 50 % */
			u32 p2 = ph ^ 0x80000000u;

			x = (s32)ph >= 0 ? 32767 : -32767;
			if (ph < inc)
				x -= blep(ph, k);
			else if (0u - ph < inc)
				x += blep(0u - ph, k);
			else if (p2 < inc)
				x += blep(p2, k);
			else if (0u - p2 < inc)
				x -= blep(0u - p2, k);
		}
		acc[i] += x * gain;
		ph += inc;
	}
	return ph;
}

static inline s32 wave_of(s32 knob)              /* Osc Wave : 0..42 scie, 43..85 carre, 86..127 triangle */
{
	return knob < 43 ? 0 : (knob < 86 ? 1 : 2);
}

static void va(s32 *x, struct trk *tr, u32 step)
{
	s32 acc[64], mix;
	u32 inc1, inc2, r, seed;
	int i;

	mix = 2 * tr->knob[3];                       /* Osc Mix : 0..252, puis 256 au bout */
	if (mix >= 254)
		mix = 256;
	r = TUNE[tr->knob[2]] >> 1;                  /* Osc2 Tune : rapport de l'oscillateur 2, Q15 */
	inc1 = note_inc(step);
	inc2 = (inc1 >> 15) * r + (((inc1 & 0x7fff) * r) >> 15);
	seed = va_seed = lcg(va_seed);
	tr->dr1 = walk(tr->dr1, seed & 0x80000000u);
	inc1 += (inc1 >> 16) * (u32)tr->dr1;         /* +-40 / 65 536 : +-1 cent au plus */
	tr->dr2 = walk(tr->dr2, seed & 0x40000000u);
	inc2 += (inc2 >> 16) * (u32)tr->dr2;
	if (tr->trig) {                              /* phases remises au trig, l'oscillateur 2 un peu au hasard */
		tr->trig = 0;
		tr->ph1 = 0x80000000u;
		tr->ph2 = (seed >> 3) + 0x70000000u;
	}
	for (i = 0; i < 64; i++)
		acc[i] = 0;
	tr->ph1 = osc(acc, tr->ph1, inc1, 256 - mix, wave_of(tr->knob[0]));
	tr->ph2 = osc(acc, tr->ph2, inc2, mix, wave_of(tr->knob[1]));
	for (i = 0; i < 64; i++)
		x[i] = shl(clamp(acc[i] >> 8), 15);
}

/* ---- batteries --------------------------------------------------------------------------------------------- */

static inline s32 drive_gain(s32 knob)           /* Drive : 4 096 x (P + 32) / 48 environ ; 0 : coupe */
{
	return knob ? (s32)(((u32)((knob << 7) + 4096) & 0xffff) * 2731u >> 12) : 0;
}

static void kick(s32 *x, struct trk *tr, u32 step)
{
	s32 drive = drive_gain(tr->knob[2]), clk, dinc;
	u32 base, e0, e1, depth, i0, i1, ph, cur, seed = dr_seed;
	int i;

	if (tr->trig) {
		tr->trig = 0;
		tr->phase = 0;
		tr->env = 0x8000;
		tr->click = tr->knob[3] << 23;               /* Click : bruit d'amplitude P x 256 */
	}
	base = mulq14(note_inc(step), 3444);         /* x 0,2102 : 55 Hz a la note 60 */
	e0 = tr->env;
	e1 = (e0 * DECAY[tr->knob[1]]) >> 15;        /* Sweep Time : 2 a 150 ms */
	tr->env = e1;
	depth = tr->knob[0] * 516u;                  /* Sweep Depth : jusqu'a x 5 a l'attaque */
	i0 = mulq14(base, ((e0 * depth) >> 15) + 16384);
	i1 = mulq14(base, ((e1 * depth) >> 15) + 16384);
	dinc = (s32)(i1 - i0) >> 6;
	ph = tr->phase;
	cur = i0;
	clk = tr->click;
	for (i = 0; i < 64; i++) {
		s32 s;

		ph += cur;
		cur += (u32)dinc;
		s = sine(ph);
		if (clk) {
			seed = lcg(seed);
			s += mulsl((s16)(seed >> 16), clk >> 15) >> 15;
			clk -= (clk >> 7) + 1;           /* 1,33 ms */
			if (clk < 0)
				clk = 0;
		}
		x[i] = shl(shape(s, drive), 15);
	}
	tr->click = clk;
	tr->phase = ph;
	dr_seed = seed;
}

static void snare(s32 *x, struct trk *tr, u32 step)
{
	s32 drive = drive_gain(tr->knob[3]), nmix, tmix, coef, dinc, te, tamp, lp1, lp2;
	u32 base, e0, e1, depth, m0, m1, i0, i1, ph, cur, seed = dr_seed;
	int i;

	if (tr->trig) {
		tr->trig = 0;
		tr->phase = 0;
		tr->env = 0x8000;
		tr->tenv = 0x3fffffff;
	}
	nmix = tr->knob[0] == 127 ? 128 : tr->knob[0];   /* Noise Mix : 127 = bruit seul */
	tmix = 128 - nmix;
	coef = FILT[tr->knob[2]];                    /* Noise Tone : passe-bas 300 Hz .. 16 kHz */
	e0 = tr->env;
	e1 = (e0 * 31344u) >> 15;                    /* chute de hauteur en 15 ms */
	tr->env = e1;
	depth = tr->knob[1] * 258u;                  /* Pitch Drop : jusqu'a x 3 a l'attaque */
	m0 = ((e0 * depth) >> 15) + 16384;
	m1 = ((e1 * depth) >> 15) + 16384;
	base = mulq14(note_inc(step), 11272);        /* x 0,688 : 180 Hz a la note 60 */
	i0 = mulq14(base, m0);
	i1 = mulq14(base, m1);
	dinc = (s32)(i1 - i0) >> 6;
	te = tr->tenv;
	te -= te >> 7;                               /* corps : 85 ms */
	tr->tenv = te;
	tamp = mulsl(te >> 15, tmix) >> 7;
	ph = tr->phase;
	cur = i0;
	lp1 = tr->lp1;
	lp2 = tr->lp2;
	for (i = 0; i < 64; i++) {
		s32 tone, n, hp;

		ph += cur;
		cur += (u32)dinc;
		tone = mulsl(sine(ph), tamp) >> 15;
		seed = lcg(seed);
		n = (s16)(seed >> 16);
		lp1 += mulsl(n - lp1, coef) >> 15;
		hp = lp1 - lp2;
		lp2 += hp >> 5;                          /* passe-haut fixe, 480 Hz environ */
		x[i] = shl(shape((mulsl(hp, nmix) >> 7) + tone, drive), 15);
	}
	tr->phase = ph;
	tr->lp1 = lp1;
	tr->lp2 = lp2;
	dr_seed = seed;
}

/* rapports des 6 oscillateurs du TR-808 (205,3 / 304,4 / 369,6 / 522,7 / 540 / 800 Hz) a 261,63 Hz, Q14 */
static const u32 HH_RATIO[6] = { 12857, 19063, 23146, 32733, 33817, 50099 };

static void hihat(s32 *x, struct trk *tr, u32 step)
{
	s32 drive = drive_gain(tr->knob[3]), nlev = tr->knob[2], coef, amp, lp1, lp2;
	u32 inc = note_inc(step), incs[6], h[6], a = 0, b = 0, q, mean, seed = dr_seed;
	int i, k;

	tr->trig = 0;                                /* oscillateurs libres : pas de remise en phase au trig */
	coef = FILT[73 + ((tr->knob[0] * 89) >> 8)]; /* Tone : passe-haut 2,9 .. 11,7 kHz */
	for (k = 0; k < 6; k++) {
		incs[k] = mulq14(inc, HH_RATIO[k]);
		a += incs[k] >> 3;
		b += incs[k] & 7;
	}
	/* moyenne des 6 increments, sans debordement : (8a + b) / 6 = 4 (a / 3) + (8 (a % 3) + b) / 6. Le firmware de
	 * David divisait la somme prise modulo 2^32 : fausse au-dela de la note 122 environ. Identique en dessous. */
	q = a / 3;
	mean = 4 * q + (8 * (a - 3 * q) + b) / 6;
	for (k = 0; k < 6; k++) {
		/* Spread : ecart a la moyenne x P / 64, soit (d x 2P) >> 5 avec d = ecart >> 2. Le firmware de David
		 * prenait les 32 bits bas de d x 2P (muls.l) : faux des que le produit depasse 2^31 (note ~86 a Spread 64,
		 * ~74 a 127). Ici sans debordement : (d >> 4) x P + ((d & 15) x P) >> 4, egal a la partie entiere de
		 * d x P / 16, donc au calcul de David tant qu'il ne deborde pas. */
		s32 d = (s32)(incs[k] - mean) >> 2;
		incs[k] = (u32)(d >> 4) * (u32)tr->knob[1] + (u32)(((d & 15) * tr->knob[1]) >> 4) + mean;
	}
	amp = ((128 - nlev) * 10000) >> 7;           /* Noise : part du metal, 0 = metal seul */
	for (k = 0; k < 6; k++)
		h[k] = tr->hh[k];
	lp1 = tr->lp1;
	lp2 = tr->lp2;
	for (i = 0; i < 64; i++) {
		s32 cnt = 0, s, u, g, w;

		for (k = 0; k < 6; k++) {
			h[k] += incs[k];
			cnt += h[k] >> 31;
		}
		seed = lcg(seed);
		s = (mulsl((s16)(seed >> 16), nlev) >> 7) + amp * (3 - cnt);   /* bruit + somme des 6 carres */
		u = s - lp1;                             /* deux passe-haut d'un pole, meme coupure */
		g = mulsl(u, coef) >> 15;
		lp1 += g;
		w = u - g - lp2;
		g = mulsl(w, coef) >> 15;
		lp2 += g;
		x[i] = shl(shape(w - g, drive), 15);
	}
	for (k = 0; k < 6; k++)
		tr->hh[k] = h[k];
	tr->lp1 = lp1;
	tr->lp2 = lp2;
	dr_seed = seed;
}

/* 64 echantillons a 96 kHz, au format (echantillon << 15), pour la piste tr ; step : pas Q16 de la note (0 : 1,0) */
void va_fill(s32 *x, struct trk *tr, u32 step, s32 kind)
{
	if (kind == VA)
		va(x, tr, step);
	else if (kind == KICK)
		kick(x, tr, step);
	else if (kind == SNARE)
		snare(x, tr, step);
	else
		hihat(x, tr, step);
}

/* batteries, apres le VCA et PUNCH : gain fixe (x 4/3, 5/3, 8/3) puis saturation douce, sur les 32 echantillons */
void va_post(s32 *out, s32 kind)
{
	static const s32 GAIN[3] = { 5461, 6827, 10923 };
	s32 g = GAIN[kind - KICK];
	int i;

	for (i = 0; i < 32; i++)
		out[i] = shl(clamp(softclip(mulsl(out[i] >> 16, g) >> 12)), 16);
}

/* ---- la passerelle ----------------------------------------------------------------------------------------- */

static inline struct trk *trk_of(const char *v)
{
	return &va_trk[((u32)v - CYC_VOICE0) / CYC_VSTRIDE];
}

static inline u32 mag(s32 x)
{
	return x < 0 ? 0u - (u32)x : (u32)x;
}

static inline int idle(const char *v)            /* ni trig, enveloppe d'ampli eteinte */
{
	return !V32(0x34) && !V32(0x38) && mag(V32(0x230)) < IDLE_LEVEL && mag(V32(0x234)) < IDLE_LEVEL;
}

static inline s32 dial(s32 w)                    /* mot 8.8 -> 0..127 */
{
	w = w < 0 ? 0 : w >> 8;
	return w > 127 ? 127 : w;
}

void va_update(s32 pmod, char *v, const char *p)
{
	struct trk *tr = trk_of(v);
	int k;

	if (V32(MARK_OFF) != MARK) {                 /* 1er bloc sur l'une de ces machines (trig qui l'a choisie) */
		u32 *s = (u32 *)tr;

		for (k = 0; k < (int)(sizeof(*tr) / 4); k++)
			s[k] = 0;
		tr->trig = 1;
		V32(MARK_OFF) = MARK;
	}
	for (k = 0; k < 4; k++)
		tr->knob[k] = dial(P16(0x16 + 2 * k));
	if (V32(0x34) && !V32(0x38))
		tr->trig = 1;
	if (!idle(v))
		TONE_UPDATE(pmod, v, p);
}

static inline void render(s32 *out, char *v, s32 kind)
{
	u32 step;
	int i;

	if (idle(v)) {                               /* voix muette : pas calculee */
		for (i = 0; i < 32; i++)
			out[i] = 0;
		return;
	}
	step = (u32)V32(232);                        /* hauteur de TONE -> pas Q16 (formule de Model-TG) */
	step = step ? ((step >> 4) * 93957u) >> 12 : 0;
	va_fill(TONE_BUF + 8, trk_of(v), step, kind);
	DECIMATE(v, TONE_BUF, out);
	AMP_ENV(v);
	VCA(out, v);
	PUNCH(out, v);
	if (kind != VA)
		va_post(out, kind);
}

void va_render_va(s32 *out, char *v)
{
	render(out, v, VA);
}

void va_render_kick(s32 *out, char *v)
{
	render(out, v, KICK);
}

void va_render_snare(s32 *out, char *v)
{
	render(out, v, SNARE);
}

void va_render_hihat(s32 *out, char *v)
{
	render(out, v, HIHAT);
}
