/* Filtre par piste (notes/47) : un filtre 2 pôles bipolaire, passe-bas à gauche, rien au centre, passe-haut à droite,
 * avec résonance et une enveloppe (quantité, decay) relancée à chaque note. Lié par track_filter.ld dans des masques de
 * sprites 35x35 libérés (tools/sprites.py) ; les écritures sur l'OS sont dans tools/gen_track_filter.py (HOOKS). Les
 * tables (tf_gtab, tf_ntab, tf_ktab, tf_dtab) sont calculées par le générateur et incluses depuis tables.inc.
 *
 * Paramètres : quatre descripteurs (1 à 4, des emplacements « Error » inutilisés) du groupe 7, donc de toutes les
 * machines, sur les mots k = 28 à 31 de chaque piste :
 *   k28 Filter Cutoff  0..0x7f00, centre 0x4000 = OFF ; à gauche LP, à droite HP, fréquence 5 Hz x 4400^(|C-centre|/0x4000)
 *                      (la loi du Model:Samples), plafonnée à 20 kHz ;
 *   k29 Filter Reso    Q = 0,5 x 100^(R/32512), de 0,5 à 50 (tf_ktab), réduit sous 30 Hz et vers 20 kHz (tf_ntab) ;
 *   k30 Filter Env     quantité de l'enveloppe, bipolaire (centre = 0) : déplace la fréquence vers le haut ou le bas,
 *                      sans changer de côté ;
 *   k31 Env Decay      constante de temps de 5 ms à 10 s.
 * Le filtre lit les mots lissés (a2 + 14 + 66 t + 2 k) une fois par bloc de 32 trames : potards glissés par l'OS,
 * p-locks, LFO et vélocité compris.
 *
 * DSP : SVF trapézoïdal (Zavalishin), écrit en espace d'état pour que toutes les sommes se fassent dans les
 * accumulateurs de l'EMAC (MACSR 0xa0 : fractionnaire, saturé) :
 *   ic1' = b1 ic1 + b2 (x - ic2)            b1 = 2 a1 - 1, b2 = 2 a2
 *   ic2' = c2 ic2 + b2 ic1 + 2 a3 x          c2 = 1 - 2 a3
 *   sortie = gx x + hl (ic2 + ic2') + hb (ic1 + ic1')
 *   a1 = 1/(1 + g (g + k)), a2 = g a1, a3 = g a2, g = tan(pi fc / 48000), k = 1/Q.
 *   LP : gx = 0, hl = 1/2, hb = 0 ; HP = x - k BP - LP : gx = 1, hl = -1/2, hb = -k/2.
 * Sur le pas de potard voisin du centre, la sortie passe de l'entrée au filtre (w de 0 à 1, dans gx/hl/hb : rien de
 * plus par trame) ; au centre exact, la piste n'est pas touchée (bit pour bit) et l'état est oublié. */

	.equ	TRK, 0x80001858			/* 6 x 32 x int32, sortie des voix */
	.equ	VOLDIST, 0x40056f58		/* Volume + Dist de l'OS (TRK, paramètres lissés) */
	.equ	OFF_C, 56			/* trackData + 2 k : k28 Filter Cutoff */
	.equ	OFF_R, 58			/* k29 Filter Reso */
	.equ	OFF_A, 60			/* k30 Filter Env */
	.equ	OFF_D, 62			/* k31 Env Decay */
	.equ	KSZ, 36				/* tf_kst : ic1 ic2 b1 b2 c2 a3 gx/2 hl hb */
	.equ	K_GX, 24
	.equ	K_HL, 28
	.equ	K_HB, 32
	.equ	CSZ, 20				/* tf_cst : clé (C<<16|R), décalage de l'enveloppe, en marche, enveloppe, côté */
	.equ	C_KEY2, 4
	.equ	C_ON, 8
	.equ	C_ENV, 12
	.equ	C_MODE, 16

	.globl	tf_post, tf_track, tf_kern, tf_coef, tf_coef2, tf_interp
	.globl	tf_kst, tf_cst, tf_trig, tf_gtab, tf_ntab, tf_ktab, tf_dtab

	.include "tables.inc"			/* macros TABLE_G, TABLE_N, TABLE_K, TABLE_D (65 longs chacune) */

/* ---- 0x40059852 : jsr tf_post à la place de jsr 0x40056f58 (Volume + Dist) -------------------------------------
 * Pile : 4(sp) = TRK, 8(sp) = a2 (paramètres lissés, 0x8000100c), comme pour l'appel remplacé. a3 = le contexte de la
 * fonction audio 0x4005979e : +16 = les pistes déclenchées dans ce bloc (3e argument de la boucle des voix).
 * Volume + Dist d'abord, puis le filtre (l'ordre d'une table de mixage DJ, celui du Model:Samples). Garde d2-d7/a2-a6
 * et MACSR ; rend acc0-acc2 à zéro (0x40056ea8 accumule ensuite sans les vider). */
	.section .text.post, "ax"
tf_post:
	move.l	8(%sp), -(%sp)
	move.l	8(%sp), -(%sp)
	jsr	VOLDIST
	addq.l	#8, %sp
	lea	-48(%sp), %sp
	movem.l	%d2-%d7/%a2-%a6, (%sp)
	move.l	%macsr, %d0
	move.l	%d0, 44(%sp)
	move.l	#0xa0, %macsr
	move.l	#0, %acc0
	move.l	#0, %acc1
	move.l	#0, %acc2
	move.l	16(%a3), %d0			/* pistes déclenchées dans ce bloc (bit t) */
	move.l	%d0, tf_trig
	lea	14(%a2), %a5			/* trackData de la piste 0 */
	lea	TRK, %a0
	lea	tf_kst, %a4
	lea	tf_cst, %a6
	moveq	#6, %d0
	move.l	%d0, -(%sp)
1:	move.l	%a0, -(%sp)
	jsr	tf_track
	movea.l	(%sp)+, %a0
	lea	128(%a0), %a0
	lea	KSZ(%a4), %a4
	lea	CSZ(%a6), %a6
	lea	66(%a5), %a5
	move.l	tf_trig, %d0
	lsr.l	#1, %d0
	move.l	%d0, tf_trig
	subq.l	#1, (%sp)
	bne.s	1b
	addq.l	#4, %sp
	move.l	44(%sp), %d0
	move.l	%d0, %macsr
	movem.l	(%sp), %d2-%d7/%a2-%a6
	lea	48(%sp), %sp
	rts

/* ---- une piste : a5 = ses mots lissés, a0 = son bloc, a4 = son état (tf_kst), a6 = sa commande (tf_cst) ----------
 * Bit 0 de tf_trig : une note est partie sur cette piste dans ce bloc. Détruit d0-d7, a1-a3 ; garde a4-a6. */
	.section .text.track, "ax"
tf_track:
	move.l	C_ENV(%a6), %d4			/* e, Q31 */
	lea	tf_trig+3, %a1
	btst	#0, (%a1)
	beq.s	1f
	move.l	#0x7fffffff, %d4		/* une note relance l'enveloppe */
	bra.s	3f
1:	tst.l	%d4
	beq.s	4f
	mvs.w	OFF_D(%a5), %d0
	bpl.s	2f
	moveq	#0, %d0
2:	lea	tf_dtab, %a1
	moveq	#9, %d1
	jsr	tf_interp			/* d0 = c(D), décroissance par bloc */
	mac.l	%d0, %d4, %acc0
	movclr.l %acc0, %d4
	cmpi.l	#0x10000, %d4
	bcc.s	3f
	moveq	#0, %d4				/* fin de l'enveloppe */
3:	move.l	%d4, C_ENV(%a6)
4:	moveq	#0, %d6				/* décalage de fréquence de l'enveloppe, en pas d'index */
	tst.l	%d4
	beq.s	5f
	mvs.w	OFF_A(%a5), %d0
	subi.l	#0x4000, %d0			/* quantité, -0x4000..0x3fff */
	mac.l	%d0, %d4, %acc0
	movclr.l %acc0, %d6
5:	mvs.w	OFF_C(%a5), %d0
	move.l	%d0, %d2
	subi.l	#0x4000, %d2			/* d = C - centre */
	bne.s	6f
	clr.l	C_ON(%a6)			/* centre : la piste reste telle quelle, l'état est oublié */
	rts
6:	mvs.w	OFF_R(%a5), %d1
	swap	%d0
	move.w	%d1, %d0			/* clé = C << 16 | R */
	cmp.l	(%a6), %d0
	bne.s	7f
	cmp.l	C_KEY2(%a6), %d6
	beq.s	8f
7:	move.l	%d0, (%a6)
	move.l	%d6, C_KEY2(%a6)
	jsr	tf_coef
8:	jmp	tf_kern

/* ---- le filtre sur les 32 trames : a0 = le bloc, a4 = tf_kst, a6 = tf_cst. Détruit d0-d7, a1-a3 ---------------- */
	.section .text.kern, "ax"
tf_kern:
	lea	128(%a0), %a1
	tst.l	C_ON(%a6)
	bne.s	2f
	moveq	#1, %d0				/* départ : le LP garde le niveau continu de l'entrée, le HP part du repos */
	move.l	%d0, C_ON(%a6)
	clr.l	(%a4)
	moveq	#0, %d0
	tst.l	C_MODE(%a6)
	bne.s	1f
	move.l	(%a0), %d0
1:	move.l	%d0, 4(%a4)
	bra.s	5f
2:	movea.l	%a0, %a2			/* en marche : un bloc nul avec un état retombé ne coûte rien */
	moveq	#0, %d0
	moveq	#7, %d1
3:	or.l	(%a2)+, %d0
	or.l	(%a2)+, %d0
	or.l	(%a2)+, %d0
	or.l	(%a2)+, %d0
	subq.l	#1, %d1
	bpl.s	3b
	tst.l	%d0
	bne.s	5f
	move.l	(%a4), %d0
	bpl.s	31f
	neg.l	%d0
31:	move.l	4(%a4), %d1
	bpl.s	32f
	neg.l	%d1
32:	or.l	%d1, %d0
	cmpi.l	#0x1000, %d0
	bcc.s	5f
	clr.l	(%a4)				/* retombé : la sortie est l'entrée nulle */
	clr.l	4(%a4)
	rts
5:	movem.l	(%a4), %d1-%d7			/* ic1 ic2 b1 b2 c2 a3 gx/2 */
	movea.l	K_HL(%a4), %a2
	movea.l	K_HB(%a4), %a3
6:	move.l	(%a0), %d0			/* x */
	mac.l	%d3, %d1, %acc0			/* b1 ic1 */
	mac.l	%d4, %d0, %acc0			/* + b2 x */
	msac.l	%d4, %d2, %acc0			/* - b2 ic2            -> ic1' */
	mac.l	%d5, %d2, %acc1			/* c2 ic2 */
	mac.l	%d4, %d1, %acc1			/* + b2 ic1 */
	mac.l	%d6, %d0, <<, %acc1		/* + 2 a3 x            -> ic2' */
	mac.l	%d7, %d0, <<, %acc2		/* gx x */
	mac.l	%a2, %d2, %acc2			/* + hl ic2 */
	mac.l	%a3, %d1, %acc2			/* + hb ic1 */
	movclr.l %acc0, %d1
	movclr.l %acc1, %d2
	mac.l	%a2, %d2, %acc2			/* + hl ic2' */
	mac.l	%a3, %d1, %acc2			/* + hb ic1' */
	movclr.l %acc2, %d0
	move.l	%d0, (%a0)+
	cmpa.l	%a1, %a0
	bne.s	6b
	movem.l	%d1-%d2, (%a4)
	rts

/* ---- coefficients, quand la clé change. d2 = C - centre (non nul), d1 = R, d6 = décalage de l'enveloppe ---------
 * Écrit tf_kst +8..+32 et le côté (tf_cst +16). Détruit d0-d7, a1-a3. */
	.section .text.coef1, "ax"
tf_coef:
	move.l	%d1, %d7			/* R */
	moveq	#0, %d5				/* côté LP */
	move.l	%d2, %d3
	bpl.s	1f
	neg.l	%d3				/* |d| */
	move.l	%d2, %d0
	addi.l	#0x4000, %d0			/* LP : index = C */
	bra.s	2f
1:	moveq	#1, %d5				/* côté HP : index = d */
	move.l	%d2, %d0
2:	move.l	%d5, C_MODE(%a6)
	move.l	#0x7fffffff, %d4		/* w : 1, ou |d| / 0x100 sur le pas voisin du centre */
	cmpi.l	#0x100, %d3
	bcc.s	3f
	move.l	%d3, %d4
	moveq	#23, %d1
	lsl.l	%d1, %d4
3:	add.l	%d6, %d0			/* + enveloppe, borné au côté choisi */
	bpl.s	4f
	moveq	#0, %d0
4:	cmpi.l	#0x3fff, %d0
	ble.s	5f
	move.l	#0x3fff, %d0
5:	move.l	%d0, %d6
	lea	tf_gtab, %a1
	moveq	#8, %d1
	bsr.s	tf_interp
	movea.l	%d0, %a2			/* G = g/4 */
	move.l	%d6, %d0
	lea	tf_ntab, %a1
	moveq	#8, %d1
	bsr.s	tf_interp			/* réduction de la résonance aux deux bouts */
	tst.l	%d7
	bpl.s	6f
	moveq	#0, %d7
6:	mac.l	%d0, %d7, %acc0
	movclr.l %acc0, %d0
	lea	tf_ktab, %a1
	moveq	#9, %d1
	bsr.s	tf_interp
	movea.l	%d0, %a3			/* K = k/2 = 1/(2Q) */
	jmp	tf_coef2

/* a1 = table de 65 longs, d0 = index >= 0, d1 = s : rend T[j] + (T[j+1] - T[j]) f, j = d0 >> s, f = les s bits du bas.
 * Détruit d1-d3. */
tf_interp:
	move.l	%d0, %d2
	asr.l	%d1, %d2
	move.l	(%a1,%d2.l*4), %d3
	move.l	4(%a1,%d2.l*4), %d2
	sub.l	%d3, %d2
	neg.l	%d1
	addi.l	#31, %d1
	lsl.l	%d1, %d0
	bclr	#31, %d0			/* f en Q31 */
	mac.l	%d2, %d0, %acc0
	movclr.l %acc0, %d0
	add.l	%d3, %d0
	rts

/* a2 = G = g/4, a3 = K = k/2, d4 = w, d5 = côté. a1 = 1/(1 + g(g + k)) par normalisation et trois pas de Newton. */
	.section .text.coef2, "ax"
tf_coef2:
	move.l	%a2, %d0
	asr.l	#1, %d0
	move.l	%a3, %d1
	asr.l	#2, %d1
	add.l	%d1, %d0			/* t = G/2 + K/4 */
	move.l	%a2, %d1
	mac.l	%d1, %d0, %acc0
	movclr.l %acc0, %d0			/* G t = g (g + k) / 32 */
	addi.l	#0x04000000, %d0		/* X = (1 + g (g + k)) / 32 */
	moveq	#0, %d1
1:	cmpi.l	#0x40000000, %d0		/* X = M 2^-s, M dans [1/2, 1) */
	bge.s	2f
	add.l	%d0, %d0
	addq.l	#1, %d1
	bra.s	1b
2:	move.l	%d0, %d2
	asr.l	#1, %d2
	move.l	#0x5d413ccd, %d3
	sub.l	%d2, %d3
	add.l	%d3, %d3			/* H0 ~ 1/(2M) */
	moveq	#2, %d6
3:	mac.l	%d0, %d3, %acc0			/* H = 2 H (1 - M H) */
	movclr.l %acc0, %d2
	move.l	#0x80000000, %d7
	sub.l	%d2, %d7
	mac.l	%d3, %d7, <<, %acc0
	movclr.l %acc0, %d3
	subq.l	#1, %d6
	bpl.s	3b
	moveq	#4, %d2
	sub.l	%d1, %d2
	asr.l	%d2, %d3			/* a1 = 2^(s-4) H */
	move.l	#0x80000000, %d0
	sub.l	%d3, %d0			/* 1 - a1 */
	move.l	%d3, %d1
	sub.l	%d0, %d1			/* b1 = 2 a1 - 1 */
	move.l	%d1, 8(%a4)
	move.l	%a2, %d0
	mac.l	%d0, %d3, %acc0
	movclr.l %acc0, %d0
	asl.l	#3, %d0				/* b2 = 2 a2 = 8 G a1 */
	move.l	%d0, 12(%a4)
	move.l	%a2, %d1
	mac.l	%d1, %d0, <<, %acc0
	movclr.l %acc0, %d1			/* a3 = 2 G b2 = g a2 */
	move.l	%d1, 20(%a4)
	move.l	#0x80000000, %d0
	sub.l	%d1, %d0
	sub.l	%d1, %d0			/* c2 = 1 - 2 a3 */
	move.l	%d0, 16(%a4)
	move.l	%d4, %d1
	asr.l	#1, %d1				/* w/2 */
	tst.l	%d5
	bne.s	5f
	move.l	#0x80000000, %d0		/* LP : (1 - w) x + w LP */
	sub.l	%d4, %d0
	lsr.l	#1, %d0
	move.l	%d0, K_GX(%a4)
	move.l	%d1, K_HL(%a4)
	clr.l	K_HB(%a4)
	rts
5:	move.l	#0x40000000, %d0		/* HP : x - w (LP + k BP) */
	move.l	%d0, K_GX(%a4)
	neg.l	%d1
	move.l	%d1, K_HL(%a4)
	move.l	%a3, %d0
	mac.l	%d4, %d0, %acc0
	movclr.l %acc0, %d0
	neg.l	%d0
	move.l	%d0, K_HB(%a4)
	rts

/* ---- tables (tools/gen_track_filter.py) et état -------------------------------------------------------------- */
	.section .rodata.gtab, "a"
	.balign	4
tf_gtab:	TABLE_G				/* G = tan(pi fc / 48000) / 4, index i = 256 j */
	.section .rodata.ntab, "a"
	.balign	4
tf_ntab:	TABLE_N				/* réduction de la résonance, index i = 256 j */
	.section .rodata.ktab, "a"
	.balign	4
tf_ktab:	TABLE_K				/* K = 1/(2Q), résonance R = 512 j */
	.section .rodata.dtab, "a"
	.balign	4
tf_dtab:	TABLE_D				/* décroissance de l'enveloppe par bloc, Decay D = 512 j */

	.section .data.kst, "aw"
	.balign	4
tf_kst:	.space	6*KSZ				/* écrit à zéro dans l'image : rien n'efface ces zones au démarrage */
	.section .data.cst, "aw"
	.balign	4
tf_cst:
	.rept	6
	.long	-1, 0, 0, 0, 0			/* clé impossible : les coefficients sont calculés au premier bloc */
	.endr
tf_trig:	.long	0
