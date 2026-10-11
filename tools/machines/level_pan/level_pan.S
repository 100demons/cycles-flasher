/* Volume et pan de la piste en chiffres sur l'écran principal (mod de djd_oz, notes/44). Lié par level_pan.ld dans
 * deux masques de sprites libérés ; les écritures sur l'OS sont dans tools/gen_level_pan.py (HOOKS).
 *
 * Écran principal (MainScreenView) : quand on tourne LEVEL/DATA, le volume de la piste sélectionnée (0 à 127)
 * s'affiche en chiffres de 3 × 7 points à la place du haut-parleur de la barre de volume ; avec FUNC tenu, le pan
 * (-64 à 63) s'affiche à la place du « R » de la barre de pan. Le chiffre reste SHOW_TICKS ticks de l'interface
 * (30 Hz) après le dernier mouvement, puis disparaît au redessin suivant (l'OS redessine l'écran principal au moins
 * une fois par seconde).
 *
 * Réécriture du code de djd_oz (son .syx « PAN-Level-values-3s-turn-only », envoyé à Maxime le 06/10/2026) : même
 * police, mêmes positions, mêmes fonctions de l'OS, appelées dans le même ordre, même échéance. Lui recopiait son code
 * au démarrage au-dessus du BSS (0x42339000) ; ici il s'exécute en place, ses variables sont écrites à zéro dans
 * l'image.
 *
 * Tout tourne dans la tâche de l'interface (0x40007d46) : le tick (message 5, minuteur DTIM3 à 30 Hz), l'encodeur et le
 * dessin. Convention de l'OS : arguments sur la pile, d0-d1/a0-a1 libres, d2-d7/a2-a6 gardés, résultat dans d0. */

	.equ	CUR_PROJ, 0x400cf866		/* projet courant */
	.equ	PROJ_SEQ, 0x4000eb90		/* projet + 48 */
	.equ	SEL_TRACK, 0x40012412		/* piste sélectionnée (0 à 5) */
	.equ	PROJ_KIT, 0x4000eb9c		/* projet + 116 */
	.equ	KEY_HELD, 0x4007faf4		/* touche tenue ? (1 = FUNC) */
	.equ	NEEDS_REDRAW, 0x40076082	/* View::setNeedsRedraw(this) */
	.equ	UISTATES, 0x400cf9a8
	.equ	POPUP, 0x4006b704		/* UIStates + 88 : la fenêtre d'un paramètre est ouverte */
	.equ	TRACK_PARAM, 0x400097f0		/* (kit, piste) -> objet des paramètres de la piste */
	.equ	TRACK_LEVEL, 0x40009c5a		/* (kit, piste) -> volume (0 à 127) */
	.equ	FILL_RECT, 0x40070dea		/* (bitmap, x0, y0, x1, y1, couleur) ; 0 = éteint */
	.equ	TIMERS, 0x40090f48		/* service des minuteurs de l'interface */
	.equ	PAN_PARAM, 0x1c
	.equ	SHOW_TICKS, 90			/* 3 s de ticks à 30 Hz */

	.globl	lp_tick, lp_enc, lp_draw, lp_cnt, lp_pan, lp_lvl

	.section .text.lp_a, "ax"

/* 0x400081f2 : jsr lp_tick à la place de jsr 0x40090f48, à chaque tick de l'interface (30 Hz). */
lp_tick:
	addq.l	#1, lp_cnt
	jmp	TIMERS

/* 0x4001aa4e : jmp lp_enc au début du gestionnaire des encodeurs de l'écran principal (this, EncoderEvent*).
 * Appelle l'original, garde sa réponse (d0), puis, pour l'encodeur 1 (LEVEL/DATA, champ +12 de l'événement) : FUNC
 * tenu -> le pan, sinon le volume ; échéance = tick + SHOW_TICKS et drapeau de la piste sélectionnée (si < 6), puis
 * demande de redessin. */
lp_enc:
	move.l	8(%sp), -(%sp)
	move.l	8(%sp), -(%sp)
	bsr.w	lp_enc_orig
	addq.l	#8, %sp
	movea.l	8(%sp), %a0
	moveq	#1, %d1
	cmp.l	12(%a0), %d1
	bne.s	9f
	move.l	%d0, -(%sp)
	move.l	%a2, -(%sp)
	pea	1
	jsr	KEY_HELD
	addq.l	#4, %sp
	lea	lp_lvl, %a2
	tst.l	%d0
	beq.s	1f
	lea	lp_pan, %a2
1:	bsr.w	track
	moveq	#6, %d1
	cmp.l	%d1, %d0
	bcc.s	8f				/* piste >= 6 (non signé) : rien */
	move.l	lp_cnt, %d1
	addi.l	#SHOW_TICKS, %d1
	move.l	%d1, (%a2, %d0.l*4)		/* échéance */
	moveq	#1, %d1
	move.b	%d1, 24(%a2, %d0.l)		/* drapeau */
	move.l	12(%sp), -(%sp)			/* this */
	jsr	NEEDS_REDRAW
	addq.l	#4, %sp
8:	movea.l	(%sp)+, %a2
	move.l	(%sp)+, %d0
9:	rts

/* 0x4001b22a : jmp lp_draw au début de MainScreenView::draw(this, Bitmap*). Dessine l'original, puis, si la fenêtre
 * d'un paramètre n'est pas ouverte et la piste sélectionnée < 6, le pan puis le volume qui sont encore à afficher. */
lp_draw:
	move.l	8(%sp), -(%sp)
	move.l	8(%sp), -(%sp)
	bsr.w	lp_draw_orig
	addq.l	#8, %sp
	lea	-20(%sp), %sp
	movem.l	%d2-%d4/%a2-%a3, (%sp)
	movea.l	28(%sp), %a2			/* le Bitmap */
	jsr	UISTATES
	move.l	%d0, -(%sp)
	jsr	POPUP
	addq.l	#4, %sp
	tst.b	%d0
	bne.s	9f
	bsr.w	track
	moveq	#6, %d1
	cmp.l	%d1, %d0
	bcc.s	9f
	move.l	%d0, %d2			/* piste */
	lea	lp_pan, %a3
	bsr.s	due
	beq.s	1f
	bsr.s	draw_pan
1:	lea	lp_lvl, %a3
	bsr.s	due
	beq.s	9f
	bsr.w	draw_lvl
9:	movem.l	(%sp), %d2-%d4/%a2-%a3
	lea	20(%sp), %sp
	rts

/* a3 = lp_pan ou lp_lvl, d2 = piste. Z = 0 si le chiffre est encore à afficher ; à l'échéance, efface le drapeau
 * (comparaison signée de tick - échéance : juste au passage de 0x7fffffff). */
due:
	tst.b	24(%a3, %d2.l)
	beq.s	9f
	move.l	lp_cnt, %d1
	sub.l	(%a3, %d2.l*4), %d1
	bmi.s	1f
	clr.b	24(%a3, %d2.l)
	moveq	#0, %d0
	rts
1:	moveq	#1, %d0
9:	rts

/* Pan de la piste d2 (-64 à 63) dans le rectangle (114, 21)-(127, 29), à partir de x = 115 : « - », dizaine si non
 * nulle, unité. Lu comme l'OS : vtable[28](objet des paramètres de la piste, 0x1c), en 8.8 centré sur 64. */
draw_pan:
	jsr	CUR_PROJ
	move.l	%d0, -(%sp)
	jsr	PROJ_KIT
	move.l	%d2, -(%sp)
	move.l	%d0, -(%sp)
	jsr	TRACK_PARAM
	lea	12(%sp), %sp
	movea.l	%d0, %a0
	movea.l	(%a0), %a1
	movea.l	28(%a1), %a1
	pea	PAN_PARAM
	move.l	%a0, -(%sp)
	jsr	(%a1)
	addq.l	#8, %sp
	asr.l	#8, %d0
	moveq	#64, %d1
	sub.l	%d1, %d0
	move.l	%d0, %d4
	clr.l	-(%sp)
	pea	29
	pea	127
	pea	21
	pea	114
	move.l	%a2, -(%sp)
	jsr	FILL_RECT
	lea	24(%sp), %sp
	moveq	#115, %d3
	tst.l	%d4
	bpl.s	1f
	neg.l	%d4
	moveq	#10, %d0			/* « - » */
	bsr.w	glyph_pan
1:	bsr.w	tens
	tst.l	%d0
	beq.s	2f
	bsr.w	glyph_pan
2:	move.l	%d4, %d0
	bra.w	glyph_pan

	.section .text.lp_b, "ax"

/* d0 = piste sélectionnée. */
track:
	jsr	CUR_PROJ
	move.l	%d0, -(%sp)
	jsr	PROJ_SEQ
	move.l	%d0, (%sp)
	jsr	SEL_TRACK
	addq.l	#4, %sp
	rts

/* Les deux instructions déplacées de chaque accroche, puis la suite de l'original. */
lp_enc_orig:
	lea	-32(%sp), %sp
	movem.l	%d2-%d7/%a2-%a3, (%sp)
	jmp	0x4001aa56

lp_draw_orig:
	link.w	%fp, #-64
	movem.l	%d2-%d7/%a2-%a5, (%sp)
	jmp	0x4001b232

/* Volume de la piste d2 (0 à 127) dans le rectangle (65, 8)-(77, 16), aligné à droite sur trois cases (x = 66, 70,
 * 74) ; de 100 à 127, « 1 » puis toujours la dizaine. */
draw_lvl:
	jsr	CUR_PROJ
	move.l	%d0, -(%sp)
	jsr	PROJ_KIT
	move.l	%d2, -(%sp)
	move.l	%d0, -(%sp)
	jsr	TRACK_LEVEL
	lea	12(%sp), %sp
	moveq	#0, %d4
	move.b	%d0, %d4
	clr.l	-(%sp)
	pea	16
	pea	77
	pea	8
	pea	65
	move.l	%a2, -(%sp)
	jsr	FILL_RECT
	lea	24(%sp), %sp
	moveq	#66, %d3
	moveq	#100, %d1
	cmp.l	%d1, %d4
	bcs.s	1f
	sub.l	%d1, %d4
	moveq	#1, %d0
	bsr.s	glyph_lvl
	bra.s	3f
1:	addq.l	#4, %d3
	moveq	#10, %d1
	cmp.l	%d1, %d4
	bcc.s	3f
	addq.l	#4, %d3
	bra.s	4f
3:	bsr.s	tens
	bsr.s	glyph_lvl
4:	move.l	%d4, %d0
	bra.s	glyph_lvl

/* d0 = d4 / 10, d4 = d4 % 10 (d4 < 128). */
tens:
	moveq	#0, %d0
	moveq	#10, %d1
1:	cmp.l	%d1, %d4
	bcs.s	9f
	sub.l	%d1, %d4
	addq.l	#1, %d0
	bra.s	1b
9:	rts

/* Signe d0 (0 à 9, 10 = « - ») en x = d3, sur les lignes y0 à y0 + 6 (y = 0 en bas de l'écran), puis d3 += 4.
 * a2 = le Bitmap : le pixel (x, y) est le bit 31 - y du mot x × pas (+12, en mots de 32 bits) de ses données (+16),
 * comme Bitmap::setPixel (0x400701b8) ; y < 32 ici. Détruit d0-d1/a0-a1. */
glyph_lvl:
	moveq	#9, %d1
	bra.s	glyph
glyph_pan:
	moveq	#22, %d1
glyph:
	lea	-16(%sp), %sp
	movem.l	%d2/%d4-%d6, (%sp)
	lea	lp_font, %a0
	move.l	(%a0, %d0.l*4), %d5		/* le signe, ligne du bas en premier */
	moveq	#31, %d6
	sub.l	%d1, %d6			/* bit de la ligne du bas */
	moveq	#7, %d4
1:	moveq	#1, %d0
	lsl.l	%d6, %d0			/* bit de la ligne */
	moveq	#2, %d2				/* bit 2 = colonne de gauche */
2:	btst	%d2, %d5
	beq.s	3f
	moveq	#2, %d1
	sub.l	%d2, %d1
	add.l	%d3, %d1			/* x */
	muls.l	12(%a2), %d1
	lsl.l	#2, %d1
	movea.l	16(%a2), %a1
	or.l	%d0, (%a1, %d1.l)
3:	subq.l	#1, %d2
	bpl.s	2b
	lsr.l	#3, %d5				/* ligne suivante, vers le haut */
	subq.l	#1, %d6
	subq.l	#1, %d4
	bne.s	1b
	movem.l	(%sp), %d2/%d4-%d6
	lea	16(%sp), %sp
	addq.l	#4, %d3
	rts

/* Police 3 × 7 de djd_oz (0 à 9, puis « - ») : un mot long par signe, ses 7 lignes de 3 bits, celle du bas dans les
 * bits de poids faible ; dans chaque ligne, bit 2 = colonne de gauche. Dessin : lignes du haut vers le bas. */
	.balign	4
lp_font:
	.long	0x1edb6f			/* « 0 » : ### #.# #.# #.# #.# #.# ### */
	.long	0x0b2497			/* « 1 » : .#. ##. .#. .#. .#. .#. ### */
	.long	0x1c9f27			/* « 2 » : ### ..# ..# ### #.. #.. ### */
	.long	0x1c9e4f			/* « 3 » : ### ..# ..# ### ..# ..# ### */
	.long	0x16de49			/* « 4 » : #.# #.# #.# ### ..# ..# ..# */
	.long	0x1e4e4f			/* « 5 » : ### #.. #.. ### ..# ..# ### */
	.long	0x1e4f6f			/* « 6 » : ### #.. #.. ### #.# #.# ### */
	.long	0x1c9492			/* « 7 » : ### ..# ..# .#. .#. .#. .#. */
	.long	0x1edf6f			/* « 8 » : ### #.# #.# ### #.# #.# ### */
	.long	0x1ede4f			/* « 9 » : ### #.# #.# ### ..# ..# ### */
	.long	0x000e00			/* « - » : ... ... ... ### ... ... ... */

	.section .data.lp, "aw"
	.balign	4
lp_cnt:	.long	0				/* ticks de l'interface (30 Hz) */
lp_pan:	.space	32				/* échéances des 6 pistes (6 mots longs), puis leurs drapeaux (+24) */
lp_lvl:	.space	32
