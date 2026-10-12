/*
 * ACID : machine ajoutee du Model:Cycles (OS 1.13), une basse acide a la maniere d'une TB-303 (notes/54).
 * Le son est dans acid_dsp.h (modele d'Open303, MIT) ; ce fichier le branche sur la boucle des voix.
 *
 * Contrat de la boucle des voix (notes/14) : update(pmod, v, p) puis render(out, v), une fois par bloc de
 * 32 trames a 48 kHz. pmod = note du trig (demi-tons << 16) ; v = voix du Cycles (0x31c o) ; p = parametres
 * de la piste (mots 8.8 : +0x12 MACHINE, +0x14 PITCH, +0x16 COLOR, +0x18 SHAPE, +0x1a SWEEP, +0x1c CONTOUR,
 * +0x1e PUNCH, +0x20 GATE, +0x22 FINE, +0x24 DECAY) ; v+0x34 / v+0x38 : trig de ce bloc / du bloc precedent,
 * v+0x3c : fin de la note (LEN ecoulee, touche relachee) ; out : 32 x int32.
 *
 * Potards : PITCH et FINE = l'accord, comme les machines d'origine ; COLOR = CUTOFF ; SHAPE = RESONANCE ;
 * SWEEP = ENV MOD ; CONTOUR = DRIVE (la saturation) ; DECAY = la decroissance de l'enveloppe du filtre
 * (200 ms .. 2 s) et celle de l'ampli (la table de TONE) ; PUNCH = forme d'onde (eteint : scie, allume : carre).
 * GATE : la chaine d'ampli d'origine (la note tient tant que le trig dure). La velocite (VEL) regle le volume de la
 * note, par l'OS, comme sur les machines d'origine.
 *
 * Slide : un trig dont la longueur (LEN) depasse le pas suivant, ou INF, ou une touche tenue en jeu live, glisse
 * vers la note suivante au lieu de la rejouer. La boucle des voix ne voit alors pas ce trig (v+0x34 efface) : ni
 * fondu, ni relance de l'ampli, ni remise a zero des champs de la voix (0x400a7d16). Le test : le reste de la
 * longueur du trig precedent, lu au bloc d'avant (0x800017b4), depasse deux pas du decompte (0x40149310), ou
 * vaut 0 alors que la note n'a pas ete relachee. Une LEN egale a l'ecart des trigs (1/16 sur des pas voisins,
 * le defaut) reste toujours sous deux pas et rejoue la note. Un trig qui change de machine (verrou MACHINE)
 * n'est jamais lie, pour que l'OS change bien de machine au bloc suivant. Le gain de la velocite (0x40fe4c90,
 * applique apres la boucle des voix, puis remplace par 0x40fe4cd0) rejoint celui de la note liee pas a pas
 * (1/127 par bloc) au lieu de sauter d'un coup. Un verrou NOTE sur un trig sans note (trigless) glisse aussi.
 *
 * Etat : une voix d'ACID par piste, ici (BSS de la charge utile, mis a zero au demarrage), remise a zero a la
 * premiere note apres un changement de machine (marque en v+0x2c, effacee par la remise a zero de la voix,
 * 0x400a7ab8) et quand la voix s'est tue. Une voix muette (enveloppe d'ampli fermee, pas de trig) n'est pas
 * calculee.
 *
 * GOV_SKIP (avec les moteurs du Syntakt, notes/54 par. 11) : leur regulateur de charge cesse d'appeler update et
 * render d'une voix restee faible, ou eteinte par un fondu sous la surcharge, jusqu'a son prochain trig. ACID ne
 * voit alors ni la fin de la note, ni que la voix s'est tue : sans ce test, ce trig glisserait depuis une note
 * eteinte. Un ecart de plus de 3 blocs entre deux appels (minuteur DMA 0, 90 112 ticks par bloc) vaut une voix tue :
 * le trig rejoue la note, comme apres un silence.
 */
#include "acid_dsp.h"

#define CYC_VOICE0  0x42308828
#define CYC_VSTRIDE 0x31c
#define MARK_OFF    0x2c
#define MARK        0x41434431                       /* 'ACD1' */

#define AMP_ENV(v)  ((void (*)(char *))0x400a9252)(v)
#define VCA(o, v)   ((void (*)(s32 *, char *))0x400a9430)(o, v)
#define PUNCH(o, v) ((void (*)(s32 *, char *))0x400a967a)(o, v)
#define LUT_DECAY   ((const s32 *)0x4011d84c)        /* DECAY -> multiplicateur par bloc (celui de TONE) */
#define VGAIN       ((const s16 *)0x40fe4c90)        /* gain de la velocite de ce bloc (0..127) */
#define VGAIN_NEXT  ((s16 *)0x40fe4cd0)              /* celui des blocs suivants */
#define LEN_LEFT    ((const s32 *)0x800017b4)        /* reste de la longueur du trig (0 : INF, live ou fini) */
#define LEN_STEP    (*(const s32 *)0x40149310)       /* ce que le decompte perd a chaque bloc */

#define V32(o)      (*(s32 *)(v + (o)))
#define P16(o)      (*(const s16 *)(p + (o)))

#define IDLE_LEVEL  (1 << 14)                        /* enveloppe d'ampli sous -102 dB : voix muette */
#ifdef GOV_SKIP
#define TIMER       (*(volatile u32 *)0xfc07000c)     /* minuteur DMA 0, 135,168 MHz */
#define SKIP_TICKS  (3 * 90112)                      /* 3 blocs de 32 trames */
#endif

struct track {
	acid_t s;
	acid_in_t in;
	s32 idle;                                        /* la voix s'est tue : remise a zero a la prochaine note */
	s32 held;                                        /* une note joue et n'a pas ete relachee */
	s32 left;                                        /* LEN_LEFT lu au bloc precedent */
	s32 mach;                                        /* MACHINE (p+0x12) qui a choisi ACID sur cette voix */
	s32 gain;                                        /* gain de velocite vise apres un slide ; ramp : en route */
	s32 ramp;
#ifdef GOV_SKIP
	u32 seen;                                        /* minuteur au dernier appel */
#endif
};

static struct track trk[6];

static inline s32 knob(s32 x)                        /* 8.8, 0..127 -> 0..32766 */
{
	x = x < 0 ? 0 : (x > 0x7f00 ? 0x7f00 : x);
	return x + (x >> 7);
}

static inline u32 mag(s32 x)
{
	return x < 0 ? 0u - (u32)x : (u32)x;
}

void acid_update(s32 pmod, char *v, const char *p)
{
	s32 t = ((u32)v - CYC_VOICE0) / CYC_VSTRIDE;
	struct track *tr = &trk[t];
	s32 dec, left, slide = 0;

	if (V32(MARK_OFF) != MARK) {                     /* 1re note sur cette machine : celle du trig qui l'a choisie, */
		tr->idle = 1;                                /* au bloc precedent (l'OS y appelait encore l'ancienne) */
		tr->held = V32(0x38) != 0;
		tr->ramp = 0;
		tr->mach = (s8)p[0x12];
		V32(MARK_OFF) = MARK;
	}
#ifdef GOV_SKIP
	{
		u32 now = TIMER;
		if (now - tr->seen > SKIP_TICKS)             /* pas appelee depuis plus de 3 blocs : la voix s'est tue */
			tr->idle = 1;
		tr->seen = now;
	}
#endif
	/* chaine d'ampli d'origine, reglee comme TONE (0x400aa7b8), sans PUNCH (il choisit la forme d'onde) */
	dec = (s8)p[0x24];
	dec = dec < 0 ? 0 : (dec > 127 ? 127 : dec);
	V32(0x250) = LUT_DECAY[dec];
	if (V32(0x38)) {
		V32(0x274) = V32(0x278) = 0x012c0f26;
		V32(0x280) = V32(0x284) = 0x001f7c5c;
		V32(0x290) = V32(0x294) = 0x7fffffff;
		V32(0x27c) = 0x82581e4b;
		V32(0x288) = 0x803ef8b8;
		V32(0x29c) = 0x7fffffff; V32(0x2a0) = 0x20000000; V32(0x2a4) = 0x20000000;
		V32(0x48) = 0;
	}

	/* trig : slide si la note precedente tient encore */
	left = tr->left;
	tr->left = LEN_LEFT[t];
	if (V32(0x34)) {
		slide = tr->held && !tr->idle && (left == 0 || left > 2 * LEN_STEP) && (s8)p[0x12] == tr->mach;
		tr->held = 1;
		tr->ramp = 0;
		if (slide) {
			V32(0x34) = 0;                       /* l'OS ne voit pas ce trig */
			tr->gain = VGAIN_NEXT[t];            /* le gain de la nouvelle velocite, rejoint pas a pas */
			VGAIN_NEXT[t] = VGAIN[t];
			tr->ramp = 1;
		}
	} else if (tr->ramp) {
		s32 g = VGAIN[t];
		g += g < tr->gain ? 1 : (g > tr->gain ? -1 : 0);
		VGAIN_NEXT[t] = (s16)g;
		tr->ramp = g != tr->gain;
	}
	if (V32(0x3c))                                   /* note relachee (avec un trig dans le meme bloc : apres) */
		tr->held = 0;

	/* note du trig, glissee ; au bloc d'un trig rejoue, l'ancienne note finit (fondu de l'ampli) */
	if (!V32(0x34))
		tr->in.note = pmod < 0 ? 0 : (pmod > (127 << 16) ? 127 << 16 : pmod);
	/* accord : PITCH - 64 et FINE (+-2 demi-tons), comme les machines d'origine */
	tr->in.tune = ((s32)P16(0x14) << 8) + (((s32)P16(0x22) - 0x4000) << 3) - (64 << 16);
	tr->in.cut = knob(P16(0x16));
	tr->in.res = knob(P16(0x18));
	tr->in.envmod = knob(P16(0x1a));
	tr->in.drive = knob(P16(0x1c));
	tr->in.decay = knob(P16(0x24));
	tr->in.wave = P16(0x1e) != 0;
	tr->in.trig = slide ? ACID_SLIDE : (V32(0x38) ? ACID_TRIG : 0);
}

void acid_render(s32 *out, char *v)
{
	struct track *tr = &trk[((u32)v - CYC_VOICE0) / CYC_VSTRIDE];
	int i;

	if (!V32(0x34) && !V32(0x38) && tr->in.trig != ACID_SLIDE
	    && mag(V32(0x230)) < IDLE_LEVEL && mag(V32(0x234)) < IDLE_LEVEL) {
		for (i = 0; i < 32; i++)                     /* voix muette : pas calculee */
			out[i] = 0;
		tr->idle = 1;
		return;
	}
	if (tr->idle && tr->in.trig == ACID_TRIG) {      /* comme Open303 : phase et filtres a zero si la voix s'etait tue */
		acid_reset(&tr->s);
		tr->idle = 0;
	}
	acid_block(&tr->s, &tr->in, out);
	AMP_ENV(v);
	VCA(out, v);
	PUNCH(out, v);
}
