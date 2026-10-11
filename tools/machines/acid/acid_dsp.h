/*
 * ACID : le coeur du son (oscillateur, filtre, enveloppe, slide, saturation), en virgule fixe, sans FPU.
 *
 * Le modele est celui d'Open303 (Robin Schmidt, 2009, licence MIT, LICENSE-Open303) : le filtre « TB_303 »
 * (mystran et kunn, forum KVR) et ses approximations des coefficients, l'enveloppe du filtre (MEG) et son
 * reglage mesure (cutoff 314..2394 Hz, ENV MOD, DECAY 200..2000 ms), le slide (hauteur lissee). Reecrit ici en
 * entiers : 48 kHz sans surechantillonnage (le filtre y reste stable jusqu'a 16,6 kHz, verifie), coefficients
 * pris dans une table en 1/16 d'octave puis interpoles a chaque echantillon, oscillateur scie ou carre (rapport
 * 46,9 %, celui de SQUARE303) a bords adoucis (polyBLEP). Puis la saturation (DRIVE, la notre) : un gain, une
 * courbe cubique u - u^3 / 3 qui ecrete en douceur, un passe-bas d'un pole qui adoucit les harmoniques aigues,
 * un niveau qui compense en partie le gain. DRIVE a zero : gain 1, la courbe sert seulement de limiteur doux.
 *
 * Ce fichier sert deux fois : compile pour le Cycles (acid.c, -mcpu=54418 : l'EMAC en mode fractionnaire
 * signe sature, MACSR = 0xa0 pendant la boucle des voix) et pour l'ordinateur (tools/emu/acid_ref.c) avec la
 * meme arithmetique a l'octet pres : la preuve compare les deux echantillon par echantillon.
 *
 * Formats : signaux 1,0 = 2^28 (l'oscillateur fait +-2^25, soit 0,125) ; coefficients Q31 ; hauteurs en
 * demi-tons << 16 ; potards 0..32767.
 */
#ifndef ACID_DSP_H
#define ACID_DSP_H

typedef signed char s8;
typedef short s16;
typedef int s32;
typedef unsigned int u32;

#ifdef __mcoldfire__
/* a x b (Q31), par l'EMAC ; ACC0 est rendu vide, comme l'exige l'OS */
static inline s32 qmul(s32 a, s32 b)
{
	s32 r;
	__asm__ volatile("mac.l %1,%2,%%acc0\n\tmovclr.l %%acc0,%0" : "=d"(r) : "r"(a), "r"(b));
	return r;
}
/* a x b + c x d (Q31), une seule lecture de l'accumulateur */
static inline s32 qmac2(s32 a, s32 b, s32 c, s32 d)
{
	s32 r;
	__asm__ volatile("mac.l %1,%2,%%acc0\n\tmac.l %3,%4,%%acc0\n\tmovclr.l %%acc0,%0"
			 : "=d"(r) : "r"(a), "r"(b), "r"(c), "r"(d));
	return r;
}
#else
/* l'EMAC, a l'identique (tools/emu/emac.py) : chaque produit tronque a 2^-39 (8 bits sous le LSB), somme,
 * puis decalage de 31 et saturation a 32 bits */
static inline s32 emac_sat(long long a)
{
	return a > 0x7fffffffLL ? 0x7fffffff : (a < -0x80000000LL ? (s32)0x80000000 : (s32)a);
}
static inline s32 qmul(s32 a, s32 b)
{
	return emac_sat((((long long)a * b) >> 23) >> 8);
}
static inline s32 qmac2(s32 a, s32 b, s32 c, s32 d)
{
	return emac_sat(((((long long)a * b) >> 23) + (((long long)c * d) >> 23)) >> 8);
}
#endif

#include "acid_tables.h"

#define ACID_ONE 0x7fffffff

/* etat d'une voix */
typedef struct {
	u32 ph;            /* phase de l'oscillateur */
	s32 key;           /* note courante (demi-tons << 16), lissee vers celle du trig (slide) */
	s32 x1, h1;        /* passe-haut d'entree (44,5 Hz) : entree precedente, sortie */
	s32 f1, fh;        /* passe-haut de la contre-reaction (150 Hz) : entree precedente, sortie */
	s32 y1, y2, y3, y4;/* le filtre a 4 poles */
	s32 b, k, g;       /* coefficients atteints a la fin du bloc precedent : b0, k/128, g x gain / 16 */
	s32 env;           /* enveloppe du filtre (MEG), Q31 */
	s32 edec;          /* MEG : multiplicateur par bloc de la note en cours */
	s32 z;             /* saturation : sortie du passe-bas, Q28 (1,0 = le seuil d'ecretage) */
} acid_t;

/* reglages d'un bloc */
typedef struct {
	s32 note;          /* note du trig, demi-tons << 16 (0..127 << 16) : le slide glisse vers elle */
	s32 tune;          /* + PITCH et FINE, demi-tons << 16, sans glissement */
	s32 cut, res, envmod, decay, drive;    /* potards 0..32767 */
	s32 wave;          /* 0 : scie, 1 : carre */
	s32 trig;          /* 0 : rien ; ACID_TRIG : nouvelle note ; ACID_SLIDE : note liee (glisse, sans MEG) */
} acid_in_t;

#define ACID_TRIG  1
#define ACID_SLIDE 2

static inline s32 acid_lut17(const s32 *t, s32 x)        /* 17 points sur 0..32767, interpoles */
{
	s32 i = x >> 11;
	return t[i] + qmul(t[i + 1] - t[i], (x & 0x7ff) << 20);
}

static inline u32 acid_inc(s32 pitch)                    /* demi-tons << 16 -> increment de phase */
{
	s32 i = pitch >> 16;
	return ACID_INC[i] + (u32)qmul((s32)(ACID_INC[i + 1] - ACID_INC[i]), (pitch & 0xffff) << 15);
}

/* bord adouci d'une marche de hauteur 2 x 2^25 (polyBLEP) : d = distance au bord en echantillons, Q15 */
static inline s32 acid_blep(u32 x, u32 inc)
{
	u32 d = x / (inc >> 15);                             /* 0..32768 */
	s32 e = 32768 - (s32)(d > 32768 ? 32768 : d);
	return (e * e) >> 5;                                /* (1 - d)^2 / 2 x 2^26 */
}

static inline void acid_reset(acid_t *s)
{
	s->ph = 0;
	s->x1 = s->h1 = s->f1 = s->fh = 0;
	s->y1 = s->y2 = s->y3 = s->y4 = 0;
	s->env = s->z = 0;
	s->b = s->k = s->g = 0;
}

/* un bloc de 32 echantillons dans out (Q31, avant la chaine d'ampli de l'OS) */
static inline void acid_block(acid_t *s, const acid_in_t *in, s32 *out)
{
	s32 c, e, lc, i, f, kf, r, b1, k1, g1, db, dk, dg, am, t, m, m3, xl, lp, mk;
	u32 ph, inc;
	int n;

	/* --- note : hauteur et MEG (Open303 : triggerNote / slideToNote) */
	if (in->trig) {
		if (in->trig == ACID_TRIG) {
			s->key = in->note;
			s->env = ACID_ONE;
		}
		s->edec = acid_lut17(ACID_DEC, in->decay);
	}
	if (in->trig != ACID_TRIG)
		s->env = qmul(s->env, s->edec);
	s->key += qmul(in->note - s->key, ACID_SLIDE_A);       /* slide : 90 % en 50 ms environ */
	t = s->key + in->tune;
	inc = acid_inc(t < 0 ? 0 : (t > (127 << 16) ? 127 << 16 : t));

	/* --- frequence de coupure en fin de bloc (index de table, Q16) : cutoff x 2^MEG */
	c = in->cut;
	e = acid_lut17(ACID_ENVLO, in->envmod);              /* echelle du MEG a cutoff min / max (octaves x 2^20) */
	t = acid_lut17(ACID_ENVHI, in->envmod);
	e += qmul(t - e, c << 16);
	lc = ACID_LC0 + qmul(c << 16, ACID_LCSPAN)            /* log2(cutoff / 200 Hz) x 16, Q16 */
	   + qmul(s->env - (ACID_EOFF0 + qmul(c << 16, ACID_EOFFSPAN)), e);
	lc = lc < 0 ? 0 : (lc > ((ACID_NCUT - 1) << 16) - 1 ? ((ACID_NCUT - 1) << 16) - 1 : lc);
	i = lc >> 16;
	f = (lc & 0xffff) << 15;
	b1 = ACID_B0[i] + qmul(ACID_B0[i + 1] - ACID_B0[i], f);
	kf = ACID_KF[i] + qmul(ACID_KF[i + 1] - ACID_KF[i], f);     /* k / 128 */
	r = acid_lut17(ACID_RES, in->res);                           /* resonance « skewee » d'Open303, Q31 */
	k1 = qmul(kf, r);
	/* g = ((k/17 - 1) r + 1)(1 + r), x amplitude (1 + 0,45 MEG) : g1 = g x amp / 128 */
	t = qmul(qmul(kf, ACID_K17) - (1 << 28), r) + (1 << 28);    /* ((k/17 - 1) r + 1) / 8 */
	g1 = qmul(t, (r >> 1) + (1 << 30));                        /* g / 16 */
	/* amplitude / 8, x le niveau de sortie : (1 + 0,45 MEG) x ACID_OUT / 8 */
	am = ACID_AMP_ONE + qmul(s->env, ACID_AMP_ENV);
	g1 = qmul(g1, am);
	if (!s->b) {                                        /* 1er bloc apres acid_reset : pas de rampe depuis zero */
		s->b = b1; s->k = k1; s->g = g1;
	}
	db = (b1 - s->b) >> 5;
	dk = (k1 - s->k) >> 5;
	dg = (g1 - s->g) >> 5;

	/* --- saturation : x = la sortie du filtre a l'echelle de sortie (pleine echelle = 2^18) ; u = x x m, Q28,
	 * 1,0 = le seuil d'ecretage (1,5 x pleine echelle / le gain du DRIVE) ; |x| >= xl : u = 2/3 (le haut de la
	 * courbe) */
	m = acid_lut17(ACID_DRV_M, in->drive);
	m3 = (m << 3) / 3;                                    /* u x 8/3 : u^2 / 3 en un seul produit */
	xl = 0x0fffffff / m;
	lp = acid_lut17(ACID_DRV_LP, in->drive);              /* passe-bas, Q31 */
	mk = acid_lut17(ACID_DRV_MK, in->drive);              /* niveau, x 1,5 x 8 / 2 */

	/* --- 32 echantillons */
	{
		s32 b = s->b, k = s->k, g = s->g, z = s->z;
		s32 x1 = s->x1, h1 = s->h1, f1 = s->f1, fh = s->fh;
		s32 y1 = s->y1, y2 = s->y2, y3 = s->y3, y4 = s->y4;
		ph = s->ph;
		for (n = 0; n < 32; n++) {
			s32 x, fb, y0, u;
			u32 nx = ph + inc;
			if (in->wave) {                              /* carre : haut sur [0, 46,9 %[ */
				u32 q = ph - ACID_DUTY;
				x = ph < ACID_DUTY ? (1 << 25) : -(1 << 25);
				if (ph < inc)
					x -= acid_blep(ph, inc);             /* juste apres la montee */
				else if (nx < ph)
					x += acid_blep(0 - ph, inc);         /* juste avant */
				if (q < inc)
					x += acid_blep(q, inc);              /* juste apres la descente */
				else if (nx - ACID_DUTY < q)
					x -= acid_blep(0 - q, inc);
			} else {                                     /* scie descendante, remonte a la fin du cycle */
				x = (s32)(0x7fffffffu - ph) >> 6;
				if (ph < inc)
					x -= acid_blep(ph, inc);
				else if (nx < ph)
					x += acid_blep(0 - ph, inc);
			}
			ph = nx;
			/* passe-haut d'entree */
			h1 = qmac2(ACID_HP1_B, x - x1, ACID_HP1_A, h1);
			x1 = x;
			/* contre-reaction k y4, passe-haut 150 Hz */
			fb = qmul(k, y4) << 7;
			fh = qmac2(ACID_HPF_B, fb - f1, ACID_HPF_A, fh);
			f1 = fb;
			y0 = h1 - fh;
			y1 += qmul(b << 1, y0 - y1 + y2);
			y2 += qmul(b, y1 - (y2 << 1) + y3);
			y3 += qmul(b, y2 - (y3 << 1) + y4);
			y4 += qmul(b, y3 - (y4 << 1));
			/* saturation : u - u^3 / 3 (pente 1 a l'origine, 2/3 et pente nulle au seuil), passe-bas, niveau */
			x = qmul(g, y4);
			if (x >= xl)
				u = ACID_SAT;
			else if (x <= -xl)
				u = -ACID_SAT;
			else {
				u = x * m;
				u = qmul(u << 1, (1 << 30) - qmul(u << 2, x * m3));
			}
			z += qmul(lp, u - z);
			out[n] = qmac2(z << 3, mk, z << 3, mk);       /* z x 12 x niveau, sature a la pleine echelle */
			b += db;
			k += dk;
			g += dg;
		}
		s->z = z;
		s->x1 = x1; s->h1 = h1; s->f1 = f1; s->fh = fh;
		s->y1 = y1; s->y2 = y2; s->y3 = y3; s->y4 = y4;
	}
	s->ph = ph;
	s->b = b1; s->k = k1; s->g = g1;
}

#endif
