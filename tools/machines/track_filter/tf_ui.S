/* Filtre par piste (notes/47) : potards, affichage, sauvegarde. Lié avec track_filter.S par track_filter.ld ; les
 * écritures sur l'OS sont dans tools/gen_track_filter.py (HOOKS, DESCRIPTORS).
 *
 *   tf_knob   : MACHINES tenu + COLOR / SHAPE / SWEEP / CONTOUR = Filter Env / Env Decay / Filter Cutoff / Filter Reso
 *               (le geste de l'Attack de Model-TG), en remplaçant la recherche du descripteur d'un potard ;
 *   tf_objs   : l'affichage des quatre valeurs (L64..OFF..H63, 0..127, -64..OFF..+63) ;
 *   tf_save*, tf_load : les quatre réglages dans l'enregistrement du son (emplacements 30, 31 et 18), et les
 *               destinations du LFO et de la vélocité vers eux (emplacement 27, comme Model-TG) ;
 *   tf_ptab, tf_conv : leurs p-locks dans le pattern (l'OS d'origine les range sur d'autres paramètres) ;
 *   tf_boot   : recopie nos descripteurs dans la table active quand un tweak l'a déplacée (moteurs du Syntakt). */

	.equ	KNOB_LOOKUP, 0x4001e814		/* vt[124] de ParameterPageView : descripteur sous un potard */
	.equ	KEY_HELD, 0x4007faf4		/* (code) -> 1 si la touche est tenue */
	.equ	KEY_MACHINES, 5
	.equ	REC, 0x40a71754			/* objets d'interface des descripteurs, 100 o chacun */
	.equ	FMT_INT, 0x400456c8		/* "%d" de v >> 8 */
	.equ	FMT_OFF, 0x40045bd6		/* "OFF" au centre, sinon "+n" / "-n" */
	.equ	SPRINTF, 0x40000e6e
	.equ	S_OFF, 0x40124b67		/* "OFF" */
	.equ	S_FMT, 0x40127767		/* "%s%d" */
	.equ	DESC, 0x4010dce0		/* table des descripteurs de l'OS, 0x38 o par entrée */
	.equ	DESC_OP, 0x4005a2de		/* opérande de lea DESC,a4 dans 0x4005a274 (déplacé par les moteurs du Syntakt) */
	.equ	BUILDER, 0x4005a274		/* construit les tables des paramètres (CC, LFO, machines) depuis les descripteurs */

	.globl	tf_knob, tf_objs, tf_fmt_cut, tf_save2, tf_save1, tf_load, tf_save_post, tf_load_post
	.globl	tf_boot, tf_conv, tf_ptab
	.globl	tf_s_cut, tf_s_res, tf_s_env, tf_s_dec, tf_s_freq, tf_s_reso, tf_s_fenv, tf_s_fdec

/* ---- vtable de ParameterPageView, slot 124 (0x401005a8) : tf_knob à la place de 0x4001e814 -----------------------
 * (vue, potard, FUNC, -1) -> d0 = descripteur. Les trois appels de l'OS passent par ce slot : potard tourné
 * (0x4001f6ee), TRACK + potard sur toutes les pistes (0x4001d716), popup quand la piste change (0x4001f090). */
	.section .text.knob, "ax"
tf_knob:
	bsr.s	tf_objs
	move.l	16(%sp), -(%sp)
	move.l	16(%sp), -(%sp)
	move.l	16(%sp), -(%sp)
	move.l	16(%sp), -(%sp)
	jsr	KNOB_LOOKUP
	lea	16(%sp), %sp
	move.l	8(%sp), %d1			/* potard : 4..7 = COLOR, SHAPE, SWEEP, CONTOUR */
	subq.l	#4, %d1
	cmpi.l	#3, %d1
	bhi.s	9f
	move.l	%d0, -(%sp)
	move.l	%d1, -(%sp)
	pea	KEY_MACHINES
	jsr	KEY_HELD
	addq.l	#4, %sp
	move.l	(%sp)+, %d1
	movea.l	%d0, %a1			/* MACHINES tenu ? */
	move.l	(%sp)+, %d0			/* le descripteur de l'OS */
	cmpa.l	#0, %a1
	beq.s	9f
	lea	knobmap, %a0
	mvz.b	(%a0,%d1.l), %d0
9:	rts
knobmap:	.byte	3, 4, 1, 2

/* Nos quatre objets d'interface (descripteurs 1 à 4) : le formateur de la valeur (invocateur, +0x20) et pas de
 * dessin spécial (+0x2c, gestionnaire : 0 = aucun ; les emplacements « Error » dessinent une image à la place du
 * texte). Rien d'autre ne les écrit ; on le refait à chaque appel. */
tf_objs:
	lea	REC+100, %a0
	lea	tf_fmts, %a1
	moveq	#4, %d1
1:	move.l	(%a1)+, %d0
	move.l	%d0, 32(%a0)
	clr.l	44(%a0)
	lea	100(%a0), %a0
	subq.l	#1, %d1
	bne.s	1b
	rts
	.balign	4
tf_fmts:	.long	tf_fmt_cut, FMT_INT, FMT_OFF, FMT_INT

/* ---- formateur de Filter Cutoff, comme celui de Pan (0x40045aee) : (fonction, v, tampon) -> "L64".."OFF".."H63".
 * Trois caractères au plus, comme Pan (L64, CEN, R63) : l'écran n'en montre pas plus (« LP64 » s'y lisait « LP6 »). */
	.section .text.fmt, "ax"
tf_fmt_cut:
	move.l	8(%sp), %d0
	subi.l	#0x4000, %d0
	beq.s	2f
	lea	tf_s_hp, %a0
	tst.l	%d0
	bpl.s	1f
	neg.l	%d0
	lea	tf_s_lp, %a0
1:	asr.l	#8, %d0
	move.l	%d0, -(%sp)
	move.l	%a0, -(%sp)
	pea	S_FMT
	move.l	24(%sp), -(%sp)
	jsr	SPRINTF
	lea	16(%sp), %sp
	rts
2:	move.l	12(%sp), %d0
	pea	S_OFF
	move.l	%d0, -(%sp)
	jsr	SPRINTF
	addq.l	#8, %sp
	rts
tf_s_lp:	.asciz	"L"
tf_s_hp:	.asciz	"H"
tf_s_cut:	.asciz	"Filter Cutoff"
tf_s_res:	.asciz	"Filter Reso"
tf_s_env:	.asciz	"Filter Env"
tf_s_dec:	.asciz	"Env Decay"
tf_s_freq:	.asciz	"FREQ"
tf_s_reso:	.asciz	"RESO"
tf_s_fenv:	.asciz	"FENV"
tf_s_fdec:	.asciz	"FDEC"

/* ---- enregistrement du son (100 o) : 0x4005afa0 (version 2), 0x4005b054 (version 1), 0x4005aecc (chargement) -----
 * Les trois commencent par lea -12(sp),sp ; movem.l a2-a4,(sp) : l'accroche (jmp, 6 o) refait ces deux instructions,
 * empile une copie des arguments et sa suite comme adresse de retour, puis saute 8 o plus loin. Le corps revient
 * dans la suite avec les arguments en 0(sp), 4(sp) ; d0 (son résultat) est gardé.
 * Emplacements de l'enregistrement (+28 + 2 s) que l'OS laisse à zéro (sa sauvegarde ne range que k <= 22) :
 *   30 (+88) Filter Cutoff XOR 0x4000 (zéro = OFF : les anciens sons se chargent filtre ouvert),
 *   31 (+90) Filter Reso,
 *   18 (+64) Filter Env (octet haut) et Env Decay (octet bas), entiers 0..127 XOR 64 (zéro = 64) ; le chargement de
 *      l'OS envoie cet emplacement sur k = 0 (inutilisé), qu'on remet à zéro,
 *   27 (+82, +83) destinations du LFO et de la vélocité quand ce sont les nôtres (k 28..31), sinon 0 : le format de
 *      Model-TG (son octet +82 pour Attack, Filter et Res, k 23..25).
 * Mots du son en mémoire : k à +20 + 2 k (k28 +76 ... k31 +82), destination du LFO = octet haut de k4 (+28),
 * destination de la vélocité = long +88. */
	.section .text.save, "ax"
tf_save2:
	move.l	8(%sp), -(%sp)			/* (enregistrement, son) */
	move.l	8(%sp), -(%sp)
	pea	tf_save_post
	lea	-12(%sp), %sp
	movem.l	%a2-%a4, (%sp)
	jmp	0x4005afa8
tf_save1:
	move.l	8(%sp), -(%sp)
	move.l	8(%sp), -(%sp)
	pea	tf_save_post
	lea	-12(%sp), %sp
	movem.l	%a2-%a4, (%sp)
	jmp	0x4005b05c

tf_save_post:
	movea.l	(%sp), %a0			/* enregistrement */
	movea.l	4(%sp), %a1			/* son */
	move.l	%d0, (%sp)
	move.w	76(%a1), %d1
	eori.l	#0x4000, %d1
	move.w	%d1, 88(%a0)
	move.w	78(%a1), %d1
	move.w	%d1, 90(%a0)
	mvz.b	80(%a1), %d1
	eori.l	#0x40, %d1
	lsl.l	#8, %d1
	mvz.b	82(%a1), %d0
	eori.l	#0x40, %d0
	or.l	%d0, %d1
	move.w	%d1, 64(%a0)
	mvz.b	28(%a1), %d0
	bsr.s	tf_dst
	move.b	%d0, 82(%a0)
	move.l	88(%a1), %d0
	bsr.s	tf_dst
	move.b	%d0, 83(%a0)
	move.l	(%sp), %d0
	addq.l	#8, %sp
	rts

/* d0 = la destination si c'est un des nôtres (28..31), sinon 0. Détruit d1. */
tf_dst:
	move.l	%d0, %d1
	subi.l	#28, %d1
	moveq	#3, %d0
	cmp.l	%d1, %d0
	bcs.s	1f
	moveq	#28, %d0
	add.l	%d1, %d0
	rts
1:	moveq	#0, %d0
	rts

	.section .text.load, "ax"
tf_load:
	move.l	8(%sp), -(%sp)			/* (son, enregistrement) */
	move.l	8(%sp), -(%sp)
	pea	tf_load_post
	lea	-12(%sp), %sp
	movem.l	%a2-%a4, (%sp)
	jmp	0x4005aed4

tf_load_post:
	movea.l	(%sp), %a1			/* son */
	movea.l	4(%sp), %a0			/* enregistrement */
	move.l	%d0, (%sp)
	move.w	88(%a0), %d1
	eori.l	#0x4000, %d1
	move.w	%d1, 76(%a1)
	move.w	90(%a0), %d1
	move.w	%d1, 78(%a1)
	mvz.b	64(%a0), %d1
	eori.l	#0x40, %d1
	lsl.l	#8, %d1
	move.w	%d1, 80(%a1)
	mvz.b	65(%a0), %d1
	eori.l	#0x40, %d1
	lsl.l	#8, %d1
	move.w	%d1, 82(%a1)
	clr.w	20(%a1)				/* k0 : l'OS y a mis l'emplacement 18 */
	mvz.b	82(%a0), %d0
	jsr	tf_dst
	tst.l	%d0
	beq.s	1f
	lsl.l	#8, %d0
	move.w	%d0, 28(%a1)			/* comme le chargement l'écrit : index << 8 */
1:	mvz.b	83(%a0), %d0
	jsr	tf_dst
	tst.l	%d0
	beq.s	2f
	move.l	%d0, 88(%a1)
2:	move.l	(%sp), %d0
	addq.l	#8, %sp
	rts

/* ---- 0x4005aa34, dans 0x4005aa1a (piste, index du fichier -> k), pistes 0..5 : jmp tf_conv à la place de
 * moveq #23,d2 ; cmp.l d0,d2 ; bcc.s 0x4005aa46. Les index 24..32 (nos p-locks, tf_ptab) reviennent sur k = index - 1.
 * d2 est empilé par la fonction (0x4005aa50 le dépile). */
tf_conv:
	moveq	#23, %d2
	cmp.l	%d0, %d2
	bcc.s	1f
	moveq	#32, %d2
	cmp.l	%d0, %d2
	bcs.s	2f
	subq.l	#1, %d0
	jmp	0x4005aa50
1:	jmp	0x4005aa46			/* 0..23 : la table d'origine */
2:	jmp	0x4005aa3a			/* au-delà : 0, comme avant */

/* ---- 0x4004486c : jsr tf_boot à la place de jsr 0x4005a274, qui construit une fois les tables des paramètres.
 * Si un tweak a déplacé la table des descripteurs (moteurs du Syntakt : une copie dans leur charge utile), on y recopie
 * nos quatre entrées avant. */
tf_boot:
	movea.l	DESC_OP, %a0
	cmpa.l	#DESC, %a0
	beq.s	2f
	lea	0x38(%a0), %a0
	lea	DESC+0x38, %a1
	moveq	#56, %d0			/* 4 entrées de 14 longs */
1:	move.l	(%a1)+, (%a0)+
	subq.l	#1, %d0
	bne.s	1b
2:	jmp	BUILDER

/* ---- k -> index dans le fichier des p-locks du pattern, à la place de 0x4010ee4c (23 entrées, lues sans borne par
 * 0x4005b95c et 0x4005ba90 : un p-lock de k >= 23 tombait sur LFO Speed, Multiplier...). 0..22 : comme l'OS ;
 * 23..31 : 24..32, des index que l'OS n'écrit jamais ; 32 : 0 (aucun paramètre). */
	.section .rodata.ptab, "a"
	.balign	4
tf_ptab:
	.long	0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19, 20, 21, 22, 23
	.long	24, 25, 26, 27, 28, 29, 30, 31, 32, 0
