/* LFO 2, 3, 4 : trois LFO de plus par piste (idée de DavidCaruso, Model-TG-VA-DR-v1 ; réécrit ici, notes/56 §3).
 *
 * Sur la page LFO, chaque appui sur [LFO] passe de LFO 1 à LFO 2, 3, 4 (un grand chiffre dans le cadre de gauche),
 * le 5e ferme la page. Chaque LFO de plus a ses réglages SPD, MULT, WAVE, DEST, DEP ; FADE, SPH, MODE (et le
 * retrig) sont ceux de LFO 1. LFO 2 est rangé dans les mots k = 28..32 du son (libres dans l'OS et sous Model-TG) :
 * sauvé avec le son (4 octets libres de l'enregistrement, +88..+91) et p-lockable. LFO 3 et LFO 4 vivent en mémoire
 * (un réglage par piste, remis aux défauts à chaque démarrage, ni sauvés ni p-lockables).
 *
 * Moteur (interruption audio) : pour chaque LFO de plus utilisé, un faux « obj » (même forme que celui de la
 * fonction audio : 14 o + 6 pistes × 66 o) reçoit ses réglages et FADE/SPH/MODE de LFO 1 ; on met son état à la
 * place de celui de l'OS (0x40fde838, 6 × 32 o), on appelle la vraie fonction des LFO (0x40091ab2), on reprend
 * l'état, puis on ajoute la modulation calculée au vrai mot de la piste (borné 0..0x7f00 comme l'OS), sauf si la
 * destination est celle de LFO 1. Les LFO de plus passent avant LFO 1 : ils peuvent moduler ses réglages.
 *
 * Mémoire de travail (états, faux obj) : SCR, au-dessus du BSS de l'OS (0x423380b0) et sous ses tampons DMA
 * (0x42340000), où ni l'OS ni aucun autre mod n'écrit (notes/56 §3) ; pas remise à zéro au démarrage : les états
 * sont mis à zéro au premier usage après chaque démarrage (drapeau « ready » dans un masque, que le démarrage
 * recharge à 0 depuis la flash ; un mot magique en SDRAM pourrait survivre à une coupure brève). Le reste (code,
 * réglages de LFO 3/4, variables de la page) est dans des masques de sprites libérés (tools/gen_lfo_plus.py les
 * place) ; ces zones de l'image sont rechargées de la flash à chaque démarrage.
 *
 * Convention de l'OS : arguments sur la pile, résultat dans d0, d0-d1/a0-a1 libres, d2-d7/a2-a6 gardés. Les
 * accroches au milieu d'une fonction de l'OS gardent en plus ce que la suite de la fonction attend (dit à chacune).
 * Les écritures sur l'OS sont dans tools/gen_lfo_plus.py (HOOKS, PTRS). */

	.equ	LFO_FN, 0x40091ab2		/* (obj, tempo, masque des retrigs) : les 6 LFO de l'OS */
	.equ	LFO_ST, 0x40fde838		/* leur état, 6 × 32 o : +16 destination, +20 quantité */
	.equ	CUR_PROJ, 0x400cf866		/* projet courant */
	.equ	PROJ_SEQ, 0x4000eb90		/* projet + 48 */
	.equ	SEL_TRACK, 0x40012412		/* piste sélectionnée */
	.equ	NEEDS_REDRAW, 0x40076082	/* View::setNeedsRedraw(vue) */
	.equ	KEY_CODE, 0x4007240c		/* code de la touche d'un événement */
	.equ	FILL_RECT, 0x40070dea		/* (bitmap, x0, y0, x1, y1, couleur) ; couleur < 0 : inverse */
	.equ	TEXT, 0x40071a04		/* (bitmap, police, x, y, drapeaux, format, ...) ; 2 = centré */
	.equ	TITLE_FONT, 0x40ea14d4		/* police du nom de la page (cadre de gauche) */

	.equ	S_LFO1, SCR			/* état de LFO 1 pendant les LFO de plus */
	.equ	S_ST2, SCR + 192		/* états des LFO 2, 3, 4 (192 o chacun) */
	.equ	S_ST3, SCR + 384
	.equ	S_ST4, SCR + 576
	.equ	S_FOBJ, SCR + 768		/* faux obj : 14 + 6 × 66 = 410 o */
	.equ	S_END, SCR + 1180

	.equ	K28, 56				/* octet du mot k = 28 dans une piste (2k) */

	.globl	lfo_audio, lfo_id2k, lfo_get, lfo_set, lfo_key, lfo_draw, lfo_ctor, lfo_dtor, lfo_gate, lfo_dest
	.globl	lfo_pack, lfo_unpack, lfo_init, lfo_plk_save, lfo_plk_load
	.globl	page, eat, ready, view, lfo34, slots, sel_track, slot_of_id, copy192, run_set, taken, audio_sets, audio_done

/* ================================================================== moteur, interruption audio ============ */

	.section .text.audio, "ax"

/* 0x400597c6, dans la fonction audio (0x4005979e) : jsr lfo_audio à la place de jsr 0x40091ab2(obj, tempo,
 * masque). a3 = l'argument de la fonction audio : (a3) = les cibles des paramètres (même forme que obj), d'où le
 * lissage 0x40058474 tire les mots de obj. Rend comme l'appel d'origine (d2-d7/a2-a6 gardés). */
lfo_audio:
	lea	-44(%sp), %sp
	movem.l	%d2-%d7/%a2-%a6, (%sp)		/* obj 48(sp), tempo 52(sp), masque 56(sp) */
	movea.l	48(%sp), %a4
	movea.l	(%a3), %a0
	/* k = 31 (destination de LFO 2) recopié brut des cibles, comme l'OS le fait pour k = 4 (0x400584d6) :
	 * sans lissage, la destination ne passe pas par les destinations intermédiaires. */
	lea	62+14(%a4), %a1
	lea	62+14(%a0), %a0
	moveq	#0, %d1
	moveq	#0, %d2				/* d2 : bit 0 LFO 2, bit 1 LFO 3, bit 2 LFO 4 utilisés */
	moveq	#6, %d0
1:	move.w	(%a0), %d1
	move.w	%d1, (%a1)
	or.l	%d1, %d2
	lea	66(%a0), %a0
	lea	66(%a1), %a1
	subq.l	#1, %d0
	bne.s	1b
	andi.l	#0xff00, %d2
	sne	%d2
	andi.l	#1, %d2
	lea	lfo34+6, %a0			/* destinations de LFO 3 puis LFO 4, 6 pistes chacun */
	moveq	#2, %d3
	moveq	#2, %d4				/* deux tables */
	moveq	#0, %d5
2:	moveq	#6, %d0
	moveq	#0, %d1
3:	move.w	(%a0), %d5
	or.l	%d5, %d1
	lea	10(%a0), %a0
	subq.l	#1, %d0
	bne.s	3b
	andi.l	#0xff00, %d1
	beq.s	4f
	or.l	%d3, %d2
4:	add.l	%d3, %d3
	subq.l	#1, %d4
	bne.s	2b
	tst.l	%d2
	bne.s	1f
audio_done:
	movem.l	(%sp), %d2-%d7/%a2-%a6		/* LFO 1 : l'appel d'origine, mêmes arguments */
	lea	44(%sp), %sp
	jmp	LFO_FN
1:	jmp	audio_sets

	.section .text.audio2, "ax"

/* Suite de lfo_audio quand au moins un LFO de plus est utilisé (d2 : lesquels ; pile de lfo_audio). */
audio_sets:
	movea.l	%d2, %a6
	move.l	52(%sp), %d6			/* tempo */
	move.l	56(%sp), %d7			/* masque des retrigs */
	tst.b	ready
	bne.s	5f
	lea	S_ST2, %a0			/* premier usage depuis le démarrage : états à zéro */
	move.l	#(192 * 3) / 4, %d0
6:	clr.l	(%a0)+
	subq.l	#1, %d0
	bne.s	6b
	moveq	#1, %d0
	move.b	%d0, ready
5:	lea	LFO_ST, %a0
	lea	S_LFO1, %a1
	jsr	copy192
	move.l	%a6, %d0
	btst	#0, %d0
	beq.s	7f
	lea	14+K28(%a4), %a0		/* LFO 2 : mots k = 28..32 des pistes */
	moveq	#66, %d0
	lea	S_ST2, %a5
	jsr	run_set
7:	move.l	%a6, %d0
	btst	#1, %d0
	beq.s	8f
	lea	lfo34, %a0			/* LFO 3 */
	moveq	#10, %d0
	lea	S_ST3, %a5
	jsr	run_set
8:	move.l	%a6, %d0
	btst	#2, %d0
	beq.s	10f
	lea	lfo34+60, %a0			/* LFO 4 */
	moveq	#10, %d0
	lea	S_ST4, %a5
	jsr	run_set
10:	lea	S_LFO1, %a0
	lea	LFO_ST, %a1
	jsr	copy192
	jmp	audio_done

	.section .text.run_set, "ax"

/* Un jeu de 6 LFO de plus. a0 = réglages de la piste 0 ({SPD, MULT, WAVE, DEST, DEP}, mots), d0 = pas entre deux
 * pistes, a5 = état du jeu (192 o), a4 = obj, d6 = tempo, d7 = masque. Détruit d0-d5/a0-a3/a5. */
run_set:
	lea	S_FOBJ+14, %a1
	lea	14(%a4), %a2
	moveq	#6, %d5
1:	move.w	(%a0), 2(%a1)			/* k1 vitesse */
	move.w	2(%a0), 4(%a1)			/* k2 multiplicateur */
	move.w	6(%a2), 6(%a1)			/* k3 fondu : celui de LFO 1 */
	move.w	6(%a0), 8(%a1)			/* k4 destination */
	move.w	4(%a0), 10(%a1)			/* k5 forme */
	move.w	12(%a2), 12(%a1)		/* k6 phase de départ, k7 mode : ceux de LFO 1 */
	move.w	14(%a2), 14(%a1)
	move.w	8(%a0), 16(%a1)			/* k8 profondeur */
	adda.l	%d0, %a0
	lea	66(%a1), %a1
	lea	66(%a2), %a2
	subq.l	#1, %d5
	bne.s	1b
	movea.l	%a5, %a0
	lea	LFO_ST, %a1
	jsr	copy192
	move.l	%d7, -(%sp)
	move.l	%d6, -(%sp)
	pea	S_FOBJ
	jsr	LFO_FN
	lea	12(%sp), %sp
	lea	LFO_ST, %a0
	movea.l	%a5, %a1
	jsr	copy192
	/* la modulation, comme l'OS l'applique (0x40091cda..0x40091d1c), aux vrais mots de la piste */
	lea	14(%a4), %a2
	moveq	#6, %d5
2:	move.l	16(%a5), %d0			/* destination calculée */
	beq.s	3f
	moveq	#32, %d1
	cmp.l	%d0, %d1
	bcs.s	3f				/* > 32 (non signé) : aucune */
	mvs.b	8(%a2), %d1			/* destination de LFO 1 (octet fort du mot k = 4) */
	cmp.l	%d1, %d0
	beq.s	3f				/* la même : LFO 1 seul la module */
	add.l	%d0, %d0
	mvs.w	(%a2, %d0.l), %d1
	add.l	20(%a5), %d1
	bpl.s	4f
	moveq	#0, %d1
4:	cmpi.l	#0x7f00, %d1
	ble.s	5f
	move.l	#0x7f00, %d1
5:	move.w	%d1, (%a2, %d0.l)
3:	lea	32(%a5), %a5
	lea	66(%a2), %a2
	subq.l	#1, %d5
	bne.s	2b
	rts

	.section .text.copy192, "ax"

/* 192 o de a0 vers a1 (6 × 32). Détruit d0-d5/a2-a3. */
copy192:
	movem.l	(%a0), %d0-%d5/%a2-%a3
	movem.l	%d0-%d5/%a2-%a3, (%a1)
	movem.l	32(%a0), %d0-%d5/%a2-%a3
	movem.l	%d0-%d5/%a2-%a3, 32(%a1)
	movem.l	64(%a0), %d0-%d5/%a2-%a3
	movem.l	%d0-%d5/%a2-%a3, 64(%a1)
	movem.l	96(%a0), %d0-%d5/%a2-%a3
	movem.l	%d0-%d5/%a2-%a3, 96(%a1)
	movem.l	128(%a0), %d0-%d5/%a2-%a3
	movem.l	%d0-%d5/%a2-%a3, 128(%a1)
	movem.l	160(%a0), %d0-%d5/%a2-%a3
	movem.l	%d0-%d5/%a2-%a3, 160(%a1)
	rts

/* ================================================================== réglages : id -> k, get/set =========== */

	.section .text.param, "ax"

/* 0x4005a4ea, dans id -> k (0x4005a4e8 : moveq #borne,d1 ; move.l 4(sp),d0 ; cmp.l d0,d1 ; ...) : jmp lfo_id2k à
 * la place de move.l 4(sp),d0 ; cmp.l d0,d1. La borne mise par 0x4005a4e8 (76 d'origine, plus avec les machines
 * ajoutées) reste dans d1. Page LFO 2 : SPD, MULT, WAVE, DEST, DEP -> k = 28..32 ; pages LFO 3/4 : -> -1 (aucun
 * mot du son ; get/set passent par lfo_get/lfo_set). Sinon les deux instructions, et la suite en 0x4005a4f0. */
lfo_id2k:
	tst.b	page
	beq.s	9f
	move.l	4(%sp), %d0
	bsr.s	slot_of_id
	bmi.s	9f
	moveq	#0, %d1
	move.b	page, %d1
	subq.l	#1, %d1
	bne.s	1f
	moveq	#28, %d1
	add.l	%d1, %d0
	rts
1:	moveq	#-1, %d0
	rts
9:	move.l	4(%sp), %d0
	cmp.l	%d0, %d1
	jmp	0x4005a4f0

/* d0 = id -> d0 = rang du réglage (0 SPD, 1 MULT, 2 WAVE, 3 DEST, 4 DEP) ou -1 (N à 1). Détruit a1. */
slot_of_id:
	subi.l	#0x1d, %d0
	cmpi.l	#7, %d0
	bhi.s	1f
	lea	slots, %a1
	mvs.b	(%a1, %d0.l), %d0
	rts
1:	moveq	#-1, %d0
	rts

	.section .text.param2, "ax"

/* d0 = id -> a0 = adresse de son réglage de LFO 3 ou 4 pour la piste sélectionnée, ou 0 (autre page, autre id,
 * piste >= 6). Détruit d0-d1/a1. */
slot34:
	moveq	#0, %d1
	move.b	page, %d1
	subq.l	#2, %d1
	bcs.s	9f
	jsr	slot_of_id
	bmi.s	9f
	add.l	%d0, %d0
	mulu.w	#60, %d1
	add.l	%d1, %d0
	move.l	%d0, -(%sp)
	bsr.s	sel_track
	move.l	(%sp)+, %d1
	cmpi.l	#6, %d0
	bcc.s	9f
	mulu.w	#10, %d0
	add.l	%d1, %d0
	lea	lfo34, %a0
	adda.l	%d0, %a0
	rts
9:	suba.l	%a0, %a0
	rts

/* d0 = piste sélectionnée. Détruit d1/a0-a1. */
sel_track:
	jsr	CUR_PROJ
	move.l	%d0, -(%sp)
	jsr	PROJ_SEQ
	move.l	%d0, (%sp)
	jsr	SEL_TRACK
	addq.l	#4, %sp
	rts

/* Pointeur 0x400fd150 (vtable 0x400fd134 [28], 0x4000ae20) : get(this, id) des réglages de la piste active.
 * Pages LFO 3/4 : la valeur de notre table ; sinon l'original. */
lfo_get:
	move.l	8(%sp), %d0
	bsr.s	slot34
	move.l	%a0, %d0
	beq.s	1f
	mvs.w	(%a0), %d0
	rts
1:	jmp	0x4000ae20

/* Pointeur 0x400fd190 (vtable 0x400fd134 [92], 0x4000ba7a) : set(this, id, valeur, ...). Pages LFO 3/4 : le mot de
 * notre table, puis redessin de la page (pas de p-lock : pas de mot du son) ; sinon l'original. */
lfo_set:
	move.l	8(%sp), %d0
	bsr.s	slot34
	move.l	%a0, %d0
	beq.s	1f
	move.w	14(%sp), (%a0)
	move.l	view, %d0
	beq.s	2f
	move.l	%d0, -(%sp)
	jsr	NEEDS_REDRAW
	addq.l	#4, %sp
2:	rts
1:	jmp	0x4000ba7a

/* ================================================================== la page LFO ============================ */

	.section .text.view, "ax"

/* Pointeur 0x401016e4 (vtable de la vue LFO 0x401016dc [2], 0x40024e86) : touche(vue, événement). Code 8 (la
 * touche [LFO]), sans FUNC : l'appui passe à la page suivante (LFO 2, 3, 4) et son relâchement est avalé ; sur
 * LFO 4, l'appui va à l'original (le relâchement ferme la page, comme d'origine). La répétition automatique va à
 * l'original (qui l'avale). Indicateurs de l'événement (+16, lus par 0x40072470/0x40072490/0x400724a0) : bit 0
 * enfoncée, bit 1 FUNC, bit 3 répétition. */
lfo_key:
	move.l	8(%sp), -(%sp)
	jsr	KEY_CODE
	addq.l	#4, %sp
	moveq	#8, %d1
	cmp.l	%d0, %d1
	bne.s	9f
	movea.l	8(%sp), %a0
	move.l	16(%a0), %d1
	btst	#1, %d1
	bne.s	9f
	btst	#0, %d1
	bne.s	1f
	tst.b	eat				/* relâchement */
	beq.s	9f
	clr.b	eat
	bra.s	8f
1:	btst	#3, %d1
	bne.s	9f
	moveq	#0, %d0
	move.b	page, %d0
	moveq	#3, %d1
	cmp.l	%d1, %d0
	beq.s	9f
	addq.l	#1, %d0
	move.b	%d0, page
	moveq	#1, %d0
	move.b	%d0, eat
	move.l	4(%sp), -(%sp)
	jsr	NEEDS_REDRAW
	addq.l	#4, %sp
8:	moveq	#1, %d0
	rts
9:	jmp	0x40024e86

	.section .text.draw, "ax"

/* Pointeur 0x401016ec (même vtable [4], 0x400426fa) : dessin(vue, bitmap). L'original, puis sur LFO 2..4 le
 * chiffre au milieu du cadre inversé de gauche, avec la police du nom de la page : cadre désinversé, chiffre,
 * cadre réinversé. */
lfo_draw:
	move.l	8(%sp), -(%sp)
	move.l	8(%sp), -(%sp)
	jsr	0x400426fa
	addq.l	#8, %sp
	moveq	#0, %d0
	move.b	page, %d0
	beq.s	9f
	lea	digits-2, %a0
	adda.l	%d0, %a0
	adda.l	%d0, %a0
	move.l	%a0, -(%sp)
	bsr.s	box
	pea	2
	pea	34
	pea	32
	pea	TITLE_FONT
	move.l	28(%sp), -(%sp)
	jsr	TEXT
	lea	20(%sp), %sp
	bsr.s	box
	addq.l	#4, %sp
9:	rts

/* Inverse le cadre de gauche (0, 0)-(63, 63) du bitmap ; appelé de lfo_draw (bitmap en 12(sp) de lfo_draw). */
box:
	pea	-1
	pea	63
	pea	63
	clr.l	-(%sp)
	clr.l	-(%sp)
	move.l	36(%sp), -(%sp)
	jsr	FILL_RECT
	lea	24(%sp), %sp
	rts

	.section .text.view2, "ax"

/* 0x4001c3dc : jsr lfo_ctor à la place de jsr 0x40025798 (constructeur de la vue LFO, seul appel). Page LFO 1 ;
 * la vue (objet + 56, comme 0x4001c3ea) est notée pour le redessin (0 si l'allocation a échoué). */
lfo_ctor:
	move.l	4(%sp), %d0
	beq.s	1f
	addi.l	#56, %d0
1:	move.l	%d0, view
	clr.b	page
	clr.b	eat
	jmp	0x40025798

/* 0x400d97f8, fin du destructeur de la vue LFO (0x400d979a ; a2 = l'objet) : jmp lfo_dtor à la place de
 * move.l a2,8(sp) ; movea.l (sp)+,a2. Si c'est notre vue : page LFO 1, plus de vue. Puis les deux instructions et
 * la suite en 0x400d97fe (jmp 0x400d96c4). */
lfo_dtor:
	lea	56(%a2), %a0
	cmpa.l	view, %a0
	bne.s	1f
	clr.l	view
	clr.b	page
	clr.b	eat
1:	move.l	%a2, 8(%sp)
	movea.l	(%sp)+, %a2
	jmp	0x400d97fe

/* 0x40025e10 : jmp lfo_gate à la place de lea -16(sp),sp ; move.l a2,-(sp). Cette fonction (appelée par 4 rappels
 * de la vue LFO pour WAVE, MULT, DEST, DEP, pas tenu) poserait un p-lock sur LFO 1 : rien sur les pages LFO 3/4,
 * qui n'ont pas de p-lock. */
lfo_gate:
	moveq	#0, %d0
	move.b	page, %d0
	subq.l	#2, %d0
	bcc.s	1f
	lea	-16(%sp), %sp
	move.l	%a2, -(%sp)
	jmp	0x40025e16
1:	rts

/* ================================================================== molette DEST ========================== */

	.section .text.dest, "ax"

/* 0x4000c140 : jmp lfo_dest ; nop à la place de link.w fp,#-32 ; move.l 12(fp),d0. Pas dans la liste des
 * destinations (this, valeur, pas, masque), appelé par 0x4000c264 pour DEST (id 32) seulement ; rend k << 8, le k
 * venant de id -> k (0x4005a4e8) appliqué à l'identifiant choisi dans la liste. Page LFO ouverte : la page est mise
 * à LFO 1 le temps du calcul (précaution : la liste de l'OS ne propose aucun réglage de LFO, mais un tel identifiant
 * y deviendrait sinon k = 28..32 ou -1), et on saute les destinations déjà prises par un autre des 4 LFO de la piste
 * (None toujours permise) ; si toutes celles qui suivent sont prises (4 essais de plus), la valeur ne change pas.
 * Page fermée : l'original. */
lfo_dest:
	tst.l	view
	beq.s	dest_orig
	lea	-24(%sp), %sp
	movem.l	%d2-%d5/%a2-%a3, (%sp)		/* this 28(sp), valeur 32, pas 36, masque 40 */
	jsr	taken
	move.l	%d0, %d4			/* destinations prises, un octet chacune */
	moveq	#0, %d0
	move.b	page, %d0
	movea.l	%d0, %a3			/* page affichée, rendue à la fin */
	clr.b	page
	move.l	32(%sp), %d3			/* valeur de départ */
	moveq	#5, %d5
1:	move.l	40(%sp), -(%sp)		/* masque */
	move.l	40(%sp), -(%sp)		/* pas */
	move.l	%d3, -(%sp)
	move.l	40(%sp), -(%sp)		/* this */
	bsr.s	dest_orig
	lea	16(%sp), %sp
	cmp.l	%d0, %d3
	beq.s	8f				/* bout de la liste */
	move.l	%d0, %d3
	bsr.s	is_taken
	beq.s	7f				/* libre */
	subq.l	#1, %d5
	bne.s	1b
8:	move.l	32(%sp), %d3			/* rien de libre plus loin : inchangée */
7:	move.l	%a3, %d0
	move.b	%d0, page
	move.l	%d3, %d0
	movem.l	(%sp), %d2-%d5/%a2-%a3
	lea	24(%sp), %sp
	rts

/* Les deux instructions déplacées, puis la suite de 0x4000c140 (aussi appelée comme sous-programme). */
dest_orig:
	link.w	%fp, #-32
	move.l	12(%fp), %d0
	jmp	0x4000c148

/* d3 = valeur (k << 8), d4 = destinations prises -> Z = 1 si libre. Détruit d0-d2/a2. */
is_taken:
	move.l	%d3, %d1
	lsr.l	#8, %d1
	andi.l	#0xff, %d1
	beq.s	9f
	move.l	%d4, %d0
	moveq	#4, %d2
1:	movea.l	%d0, %a2
	andi.l	#0xff, %d0
	cmp.l	%d0, %d1
	beq.s	8f
	move.l	%a2, %d0
	lsr.l	#8, %d0
	subq.l	#1, %d2
	bne.s	1b
9:	moveq	#0, %d0
	rts
8:	moveq	#1, %d0
	rts

	.section .text.taken, "ax"

/* d0 = destinations (k) de LFO 1, 2, 3, 4 de la piste (un octet chacune, LFO 1 en poids fort), 0 pour celui de la
 * page affichée. this en 32(sp) (appelé de lfo_dest). Détruit d1-d2/a0-a1. */
taken:
	movea.l	32(%sp), %a0
	move.l	4(%a0), %d0			/* objet de la piste, puis son son (vtable [40]), comme 0x4000ae20 */
	beq.s	9f
	movea.l	%d0, %a0
	movea.l	(%a0), %a1
	movea.l	40(%a1), %a1
	move.l	%a0, -(%sp)
	jsr	(%a1)
	addq.l	#4, %sp
	tst.l	%d0
	beq.s	9f
	movea.l	%d0, %a0
	moveq	#0, %d2
	move.b	28(%a0), %d2			/* LFO 1 : octet fort du mot k = 4 (son + 20 + 8) */
	lsl.l	#8, %d2
	move.b	82(%a0), %d2			/* LFO 2 : k = 31 */
	lsl.l	#8, %d2
	lsl.l	#8, %d2
	jsr	sel_track
	cmpi.l	#6, %d0
	bcc.s	1f
	mulu.w	#10, %d0
	lea	lfo34+6, %a0
	adda.l	%d0, %a0
	moveq	#0, %d1
	move.b	(%a0), %d1			/* LFO 3 */
	lsl.l	#8, %d1
	move.b	60(%a0), %d1			/* LFO 4 */
	or.l	%d1, %d2
1:	moveq	#0, %d0
	move.b	page, %d0
	lsl.l	#3, %d0
	move.l	#0xff000000, %d1
	lsr.l	%d0, %d1
	not.l	%d1
	and.l	%d2, %d1
	move.l	%d1, %d0
	rts
9:	moveq	#0, %d0
	rts

/* ================================================================== son et pattern ======================== */

	.section .text.store, "ax"

/* 0x4005b028 (sauvegarde du son, format 2, 0x4005afa0) et 0x4005b0dc (format 1, 0x4005b054) : jsr lfo_pack à la
 * place de move.w 94(a3),92(a2). a2 = l'enregistrement (100 o), a3 = le son. LFO 2 (k = 28..32, son + 76..85) en
 * un long en +88 (les deux dernières cases libres, que la sauvegarde vient de mettre à zéro, comme sous Model-TG) :
 * bits 31-30 = 10 (marque), 29-22 SPD >> 7, 21-17 MULT, 16-14 WAVE, 13-8 DEST, 7-0 DEP >> 7 (même format que
 * DavidCaruso : ses sons se relisent ici). Garde tout sauf d0 (d1, a1, a4 servent ensuite). */
lfo_pack:
	move.w	94(%a3), 92(%a2)
	move.l	%d1, -(%sp)
	moveq	#2, %d0				/* marque */
	moveq	#0, %d1
	move.w	76(%a3), %d1			/* SPD */
	lsr.l	#7, %d1
	andi.l	#0xff, %d1
	lsl.l	#8, %d0
	or.l	%d1, %d0
	moveq	#0, %d1
	move.b	78(%a3), %d1			/* MULT */
	andi.l	#0x1f, %d1
	lsl.l	#5, %d0
	or.l	%d1, %d0
	move.b	80(%a3), %d1			/* WAVE */
	andi.l	#7, %d1
	lsl.l	#3, %d0
	or.l	%d1, %d0
	move.b	82(%a3), %d1			/* DEST */
	andi.l	#0x3f, %d1
	lsl.l	#6, %d0
	or.l	%d1, %d0
	move.w	84(%a3), %d1			/* DEP */
	lsr.l	#7, %d1
	andi.l	#0xff, %d1
	lsl.l	#8, %d0
	or.l	%d1, %d0
	move.l	%d0, 88(%a2)
	move.l	(%sp)+, %d1
	rts

	.section .text.unpack, "ax"

/* 0x4005af1c, chargement du son (0x4005aecc ; a2 = le son, a3 = l'enregistrement, mots k = 0..32 du son déjà mis à
 * zéro par 0x4008f238) : jsr lfo_unpack à la place de lea 0x4010eea8,a0. LFO 2 relu de +88 s'il porte la marque,
 * sinon (tout son plus ancien) ses défauts. d0-d1/a1 libres ; a0 rendu comme l'instruction remplacée. */
lfo_unpack:
	move.l	88(%a3), %d0
	move.l	%d0, %d1
	andi.l	#0xc0000000, %d1
	cmpi.l	#0x80000000, %d1
	bne.s	1f
	move.l	%d0, %d1			/* DEP */
	andi.l	#0xff, %d1
	lsl.l	#7, %d1
	move.w	%d1, 84(%a2)
	lsr.l	#8, %d0
	move.l	%d0, %d1			/* DEST */
	andi.l	#0x3f, %d1
	lsl.l	#8, %d1
	move.w	%d1, 82(%a2)
	lsr.l	#6, %d0
	move.l	%d0, %d1			/* WAVE */
	andi.l	#7, %d1
	lsl.l	#8, %d1
	move.w	%d1, 80(%a2)
	lsr.l	#3, %d0
	move.l	%d0, %d1			/* MULT */
	andi.l	#0x1f, %d1
	lsl.l	#8, %d1
	move.w	%d1, 78(%a2)
	lsr.l	#5, %d0				/* SPD */
	andi.l	#0xff, %d0
	lsl.l	#7, %d0
	move.w	%d0, 76(%a2)
	bra.s	2f
1:	bsr.s	lfo2_defaults
2:	lea	0x4010eea8, %a0
	rts

/* 0x400618e2, fin de l'initialisation d'un son aux défauts (0x40061866 ; a2 = le son) : jsr lfo_init à la place de
 * lsl.l #8,d3 ; move.w d3,38(a2). Les deux instructions, puis les défauts de LFO 2 (l'OS y a mis 0 : aucun
 * descripteur ne vise k = 28..32). d0-d1/a0-a1 libres ensuite. */
lfo_init:
	lsl.l	#8, %d3
	move.w	%d3, 38(%a2)
/* Défauts de LFO 2 dans le son a2 : ceux du LFO d'origine (descripteurs 0x1d..0x24) : SPD 0x7000, MULT 4, WAVE 0,
 * DEST None, DEP 0x4000 (profondeur nulle). */
lfo2_defaults:
	move.l	#0x70000400, %d0
	move.l	%d0, 76(%a2)
	clr.l	80(%a2)
	move.w	#0x4000, 84(%a2)
	rts

	.section .text.plk, "ax"

/* 0x4005b9c6, enregistrement des p-locks dans le pattern (0x4005b95c ; d0 = k, d4 = 4k, d1 = rangées écrites,
 * d2 = piste, a3 = la rangée) : jsr lfo_plk_save ; nop à la place de move.b 3(a5,d4.l),(a3) ; move.b d2,1(a3).
 * L'OS prend l'identifiant de rangée dans 0x4010ee4c[k], qui n'a que 23 entrées : pour k = 23..32 il lisait la
 * table suivante (Model-TG : un p-lock d'Attack, Filtre, Résonance revenait en None, LFO Speed, Multiplier). Ici
 * k = 23..32 -> plk_id. Garde tout. */
lfo_plk_save:
	cmpi.l	#22, %d0
	bhi.s	1f
	move.b	3(%a5, %d4.l), (%a3)
	bra.s	2f
1:	move.b	plk_id-23(%pc, %d0.l), (%a3)
2:	move.b	%d2, 1(%a3)
	rts
/* identifiant de rangée pour k = 23..32 (0xff : rangée ignorée à la relecture ; k = 26, 27 : état du Sampler de
 * Model-TG, jamais p-locké) */
plk_id:	.byte	24, 25, 26, 0xff, 0xff, 27, 28, 29, 30, 31

/* 0x4005aa22, identifiant de rangée -> k (0x4005aa1a(piste, id) ; d2 empilé puis = 6, d1 = piste) : jmp
 * lfo_plk_load à la place de move.l 12(sp),d0 ; cmp.l d1,d2. Pistes 0..5, identifiants 24..31 (que l'OS n'écrit
 * jamais) -> plk_k ; sinon les deux instructions et la suite en 0x4005aa28. */
lfo_plk_load:
	move.l	12(%sp), %d0
	moveq	#5, %d2
	cmp.l	%d1, %d2
	bcs.s	1f
	moveq	#-24, %d2
	add.l	%d0, %d2
	cmpi.l	#7, %d2
	bhi.s	1f
	mvz.b	plk_k(%pc, %d2.l), %d0
	move.l	(%sp)+, %d2
	rts
1:	moveq	#6, %d2
	cmp.l	%d1, %d2
	jmp	0x4005aa28
plk_k:	.byte	23, 24, 25, 28, 29, 30, 31, 32

/* ================================================================== données (masques, image) ============== */

	.section .data.lfo, "aw"
	.balign	4
view:	.long	0				/* la vue LFO ouverte (objet + 56), 0 sinon */
page:	.byte	0				/* 0..3 : LFO 1..4 affiché */
eat:	.byte	0				/* avaler le relâchement de [LFO] */
ready:	.byte	0				/* états de SCR mis à zéro depuis le démarrage */
/* id 0x1d..0x24 -> rang du réglage : SPD, MULT, (FADE), DEST, WAVE, (SPH), (MODE), DEP */
slots:	.byte	0, 1, -1, 3, 2, -1, -1, 4
digits:	.asciz	"2"
	.asciz	"3"
	.asciz	"4"
	.balign	2
/* LFO 3 puis LFO 4 : 6 pistes × {SPD, MULT << 8, WAVE << 8, DEST << 8, DEP}, défauts du LFO d'origine */
lfo34:	.rept	12
	.short	0x7000, 0x0400, 0, 0, 0x4000
	.endr
