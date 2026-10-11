/*
 * MACRO : machine ajoutee du Model:Cycles (OS 1.13) qui joue les 47 modeles de synthese de Braids, le
 * module d'Emilie Gillet (code MIT, depot pichenettes/eurorack, braids/ et stmlib/, notes/43). Ce fichier
 * est notre seul code : les sources de Braids sont compilees telles quelles par tools/gen_macro.py.
 *
 * Contrat de la boucle des voix (notes/14) : update(pmod, v, p) puis render(out, v), une fois par bloc de
 * 32 trames a 48 kHz. pmod = note du trig (demi-tons << 16) ; v = voix du Cycles (0x31c o) ; p = parametres
 * de la piste (mots 8.8 : +0x14 PITCH, +0x16 COLOR, +0x18 SHAPE, +0x1a SWEEP, +0x1c CONTOUR, +0x1e PUNCH,
 * +0x22 FINE, +0x24 DECAY) ; v+0x34 / v+0x38 : trig de ce bloc / du bloc precedent ; out : 32 x int32 (Q31).
 *
 * Braids est fait pour 96 kHz (ses tables de hauteur, de filtres et d'ondes) et rend par blocs de 24 echantillons,
 * 4 000 fois par seconde sur le module : ses decroissances (STRUCK BELL, STRUCK DRUM), la consonne de VOWEL et ses
 * lissages avancent d'un pas par bloc. Il rend donc ici exactement comme sur le module, des blocs de 24 : 3, 3 puis 2
 * par bloc de 32 trames du Cycles (8 x 24 = 3 x 64), ce qui depasse attend le bloc suivant (16 echantillons au plus,
 * 0,17 ms). Les 64 echantillons du bloc sont ramenes a 48 kHz par un filtre demi-bande de 23 coefficients
 * (passe-bande 0..19 kHz a 0,04 dB pres, -46 dB des 29 kHz, ce qui se replierait sous 19 kHz). Son propre code
 * donne donc exactement le son de Braids, a 96 kHz, avant ce filtre.
 *
 * Potards : PITCH et FINE = la note, comme les machines d'origine ; COLOR = TIMBRE de Braids ; SHAPE = le
 * modele (0..46, l'ordre de Braids : CSAW, MORPH, ...) ; SWEEP = COLOR de Braids ; CONTOUR = l'enveloppe
 * d'ampli ouvre TIMBRE (0 : rien). DECAY, GATE et PUNCH : la chaine d'ampli d'origine, reglee comme TONE
 * (enveloppe 0x400a9252, VCA 0x400a9430, PUNCH 0x400a967a). Un trig frappe le modele (Strike).
 *
 * Etat : une voix de Braids par piste, ici (BSS de la charge utile, mis a zero au demarrage), initialisee a
 * la premiere note apres un changement de machine (marque en v+0x2c, effacee par la remise a zero de la voix,
 * 0x400a7ab8). Une voix muette (enveloppe d'ampli fermee, pas de trig) n'est pas calculee.
 */
#include <new>

#include "braids/macro_oscillator.h"

typedef signed char s8;
typedef short s16;
typedef int s32;
typedef unsigned int u32;

#define CYC_VOICE0  0x42308828
#define CYC_VSTRIDE 0x31c
#define MARK_OFF    0x2c
#define MARK        0x4d435231                       /* 'MCR1' */

#define AMP_ENV(v)  ((void (*)(char *))0x400a9252)(v)
#define VCA(o, v)   ((void (*)(s32 *, char *))0x400a9430)(o, v)
#define PUNCH(o, v) ((void (*)(s32 *, char *))0x400a967a)(o, v)
#define LUT_DECAY   ((const s32 *)0x4011d84c)        /* DECAY -> multiplicateur par bloc (celui de TONE) */

#define V32(o)      (*(s32 *)(v + (o)))
#define P16(o)      (*(const s16 *)(p + (o)))

#define MODELS      47                               /* CSAW .. DIGITAL_MODULATION (sans QUESTION_MARK) */
#define HIST        22                               /* echantillons du bloc precedent pour le filtre */
#define IDLE_LEVEL  (1 << 14)                        /* enveloppe d'ampli sous -102 dB : voix muette */

struct Track {
	braids::MacroOscillator osc;
	s16 x[HIST + 64 + 16];                           /* 96 kHz : fin du bloc precedent, ce bloc, puis l'avance */
	s32 fill;                                        /* echantillons rendus apres l'historique (0, 8 ou 16 au debut) */
};

/* pas de constructeurs globaux (rien ne les appellerait) : placement new a l'initialisation de la piste */
alignas(4) static unsigned char store[6][sizeof(Track)];
static const unsigned char no_sync[24] = { 0 };

/* filtre demi-bande, 23 coefficients (Q15, minimax, somme 1/2 : gain 1 en continu) : 1/2 au centre, puis +-1, +-3,
 * ... +-11 */
static const s16 HB[6] = { 10327, -3131, 1579, -820, 434, -197 };

static inline Track *track_of(const char *v)
{
	return reinterpret_cast<Track *>(store[((u32)v - CYC_VOICE0) / CYC_VSTRIDE]);
}

static inline s32 knob(s32 x)                        /* 8.8, 0..127 -> 0..32766 */
{
	x = x < 0 ? 0 : (x > 0x7f00 ? 0x7f00 : x);
	return x + (x >> 7);
}

static inline u32 mag(s32 x)
{
	return x < 0 ? 0u - (u32)x : (u32)x;
}

extern "C" void macro_update(s32 pmod, char *v, const char *p)
{
	Track *tr = track_of(v);
	s32 dec, n, shape, timbre, env;

	if (V32(MARK_OFF) != MARK) {                     /* 1re note sur cette machine */
		new (tr) Track;
		tr->osc.Init();
		for (n = 0; n < HIST; n++)
			tr->x[n] = 0;
		tr->fill = 0;
		V32(MARK_OFF) = MARK;
	}
	/* chaine d'ampli d'origine, reglee comme TONE (0x400aa7b8) */
	dec = (s8)p[0x24];
	dec = dec < 0 ? 0 : (dec > 127 ? 127 : dec);
	V32(0x250) = LUT_DECAY[dec];
	if (V32(0x38)) {
		V32(0x274) = V32(0x278) = 0x012c0f26;
		V32(0x280) = V32(0x284) = 0x001f7c5c;
		V32(0x290) = V32(0x294) = 0x7fffffff;
		V32(0x27c) = 0x82581e4b;
		V32(0x288) = 0x803ef8b8;
		if (P16(0x1e)) {
			V32(0x29c) = 0x20000000; V32(0x2a0) = 0x60000000; V32(0x2a4) = 0x20000000;
			V32(0x48) = 1;
		} else {
			V32(0x29c) = 0x7fffffff; V32(0x2a0) = 0x20000000; V32(0x2a4) = 0x20000000;
			V32(0x48) = 0;
		}
	}

	shape = P16(0x18) >> 8;
	shape = shape < 0 ? 0 : (shape >= MODELS ? MODELS - 1 : shape);
	tr->osc.set_shape(static_cast<braids::MacroOscillatorShape>(shape));

	/* note : PITCH - 64 + note du trig + FINE (+-2 demi-tons), comme les machines d'origine ; Braids : 1/128 */
	n = ((s32)P16(0x14) << 8) + (((s32)P16(0x22) - 0x4000) << 3) - (64 << 16) + pmod;
	n = n < 0 ? 0 : (n > (127 << 16) ? 127 << 16 : n);
	tr->osc.set_pitch(n >> 9);

	/* TIMBRE = COLOR + CONTOUR x enveloppe d'ampli (son niveau au bloc precedent, plein au trig) */
	env = V32(0x38) ? 32767 : (s32)(mag(V32(0x230)) >> 16);
	env = env > 32767 ? 32767 : env;
	timbre = knob(P16(0x16)) + ((env * knob(P16(0x1c))) >> 15);
	timbre = timbre > 32767 ? 32767 : timbre;
	tr->osc.set_parameters(timbre, knob(P16(0x1a)));

	if (V32(0x38))
		tr->osc.Strike();
}

extern "C" void macro_render(s32 *out, char *v)
{
	Track *tr = track_of(v);
	const s16 *x;
	int i;

	if (!V32(0x34) && !V32(0x38) && mag(V32(0x230)) < IDLE_LEVEL && mag(V32(0x234)) < IDLE_LEVEL) {
		for (i = 0; i < 32; i++)                     /* voix muette : pas calculee */
			out[i] = 0;
		return;
	}
	while (tr->fill < 64) {                          /* des blocs de 24, comme sur le module */
		tr->osc.Render(no_sync, tr->x + HIST + tr->fill, 24);
		tr->fill += 24;
	}
	/* 96 -> 48 kHz : sortie m centree sur l'echantillon 2m + 11 de x (retard de 5,5 echantillons a 48 kHz) */
	x = tr->x;
	for (i = 0; i < 32; i++, x += 2) {
		s32 acc = (s32)x[11] << 14;
		acc += HB[0] * ((s32)x[10] + x[12]);
		acc += HB[1] * ((s32)x[8] + x[14]);
		acc += HB[2] * ((s32)x[6] + x[16]);
		acc += HB[3] * ((s32)x[4] + x[18]);
		acc += HB[4] * ((s32)x[2] + x[20]);
		acc += HB[5] * ((s32)x[0] + x[22]);
		out[i] = acc;                            /* pleine echelle de Braids -> 1/2 pleine echelle (Q31) */
	}
	tr->fill -= 64;                                  /* l'historique et l'avance glissent au debut */
	for (i = 0; i < HIST + tr->fill; i++)
		tr->x[i] = tr->x[64 + i];
	AMP_ENV(v);
	VCA(out, v);
	PUNCH(out, v);
}
