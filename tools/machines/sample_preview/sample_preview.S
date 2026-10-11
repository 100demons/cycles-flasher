/* Écoute des samples dans le navigateur de presets, avec le Sampler de Model-TG (notes/46). Lié par
 * sample_preview.ld dans quatre masques de sprites 47x47 libérés (tools/sprites.py) ; les écritures sur l'OS sont
 * dans tools/gen_sample_preview.py (HOOKS).
 *
 * L'OS d'origine écoute un preset ainsi : quand le curseur du navigateur bouge, la routine 0x400a63ac charge le son
 * sous le curseur, le copie dans l'un de ses deux tampons de 100 o (0x40058504) et le désigne par le pointeur
 * ARMED (0x40081bd6). Rien ne joue tout seul : la note suivante jouée sur le pad de la piste active (ou ses touches
 * en mode clavier) emporte ce pointeur (0x40081860) et joue ce son à la place de celui de la piste, pour cette note.
 * Un fichier de sample n'est pas un preset : la lecture du preset échoue (taille hors de 48..160 o) et rien n'est
 * désigné. Trois accroches :
 *   - pv_parse (navigateur, tâche de l'interface) : sur une piste Sampler, un fichier qui n'est pas un preset est
 *     écouté comme un sample : une copie du son de la piste, nommée « SMP » + 8 chiffres hexadécimaux de son
 *     empreinte, comme les sample locks de Model-TG ; cette copie et ce nom reprennent, instruction pour
 *     instruction, ceux de son pool_store_hook (TinyGregAudio, licence MIT, texte dans
 *     tweaks/model-cycles_OS1.13/LICENSE-Model-TG). L'OS la désigne ensuite comme un preset ;
 *   - pv_note (note jouée sur le pad, tâche de l'interface) : si le son désigné nomme un sample qui n'est pas en
 *     mémoire, il est chargé avant la note, comme le préchargement de Model-TG (pd_mode 1 : seulement dans la place
 *     libre, en ne chassant que des samples que le projet n'utilise pas). S'il ne se charge pas (ou si le chargeur
 *     est occupé), la note n'est pas envoyée au moteur audio : rien ne joue, plutôt que le sample de la piste ;
 *   - pv_copy (boucle des événements de l'interruption audio) : l'OS efface le pointeur du son de la piste
 *     (0x800015a0 + (147 + piste) * 4) après une note d'écoute, avant que le Sampler de Model-TG (sp_lock) le lise
 *     pour trouver le sample de la note. Pour un son du Sampler, on y met une copie du son écouté à la place de
 *     zéro : sp_lock joue alors ce sample pour cette note, et la note suivante reprend le son de la piste (la copie
 *     n'est jamais le son d'une note, donc l'OS le recopie, comme après l'effacement d'origine).
 *
 * Adresses de Model-TG (symboles de 30-model-tg.json / 30-model-tg-st.json), passées par -D :
 *   TG_TOK_OF(a0 = son) -> d0 = l'empreinte nommée par « SMP… » si machine 6, sinon 0 ; garde d1-d7, détruit a0
 *   TG_SOUND_OBJ(d0 = piste) -> d0 = son de la piste, ou 0 ; garde d2-d5/a2-a3
 *   TG_ENSURE_LOADED(d0 = empreinte) -> d0 = case, ou -1 ; garde d2-d4/a2
 *   TG_SLOT_HASH : empreintes des 64 cases d'échantillons en mémoire ; TG_PD_MODE, TG_LD_BUSY : mode du chargeur,
 *   chargeur occupé (led_hook) */

#define ACTIVE	0x40a700c4		/* piste active, celle des notes d'écoute (0x40081760) */
#define ARMED	0x40fb5a04		/* son désigné pour l'écoute, ou 0 */
#define PARSE	0x400a3052		/* lit un preset : (a0 = &résultat, &handle) */

	.globl	pv_parse, pv_note, pv_copy, pv_tab, pv_src, pv_fail, pv_failp

/* 0x400a6426, dans 0x400a63ac : jsr pv_parse à la place de jsr 0x400a3052.
 * Entrée : a0 = &résultat (fp-24 : son, compteur), 4(sp) = &handle {id, empreinte, taille, …} de getEntry.
 * Sortie : comme l'original, le résultat rempli et d0 = a0 = &résultat. Un compteur nul est sans danger : l'OS libère
 * un compteur nul sans rien faire (0x400cf23c). Sur une piste qui n'est pas un Sampler : l'original, tel quel. */
	.section .text.pv_parse, "ax"
pv_parse:
	clr.l	pv_fail			/* nouveau son désigné : on retentera un chargement raté */
	lea	-16(%sp), %sp
	movem.l	%d2-%d3/%a2-%a3, (%sp)
	movea.l	%a0, %a2		/* &résultat */
	movea.l	20(%sp), %a1		/* &handle */
	move.l	8(%a1), %d2		/* taille du fichier */
	move.l	4(%a1), %d3		/* son empreinte */
	move.l	ACTIVE, %d0
	jsr	TG_SOUND_OBJ
	tst.l	%d0
	beq.w	.Lstock
	movea.l	%d0, %a3		/* le son de la piste active */
	mvz.b	38(%a3), %d0
	moveq	#6, %d1
	cmp.l	%d1, %d0
	bne.s	.Lstock			/* pas un Sampler : l'original */
	move.l	%d2, %d0
	subi.l	#48, %d0
	cmpi.l	#112, %d0
	bhi.s	.Lsample		/* hors de 48..160 o : ce n'est pas un preset */
	bsr.s	.Lorig
	tst.l	(%a2)
	bne.s	.Lout			/* un preset : son écoute d'origine */
.Lsample:
	moveq	#66, %d0
	cmp.l	%d0, %d2
	bcs.s	.Lnone			/* moins que l'en-tête de 64 o et un échantillon */
	tst.l	%d3
	beq.s	.Lnone
	lea	pv_src, %a0		/* le son de la piste… (d'après pool_store_hook de Model-TG, MIT) */
	movea.l	%a3, %a1
	moveq	#24, %d0
1:	move.l	(%a1)+, (%a0)+
	subq.l	#1, %d0
	bpl.s	1b
	lea	pv_src+4, %a0		/* …qui nomme le sample : « SMP » + 8 chiffres */
	move.b	#'S', (%a0)+
	move.b	#'M', (%a0)+
	move.b	#'P', (%a0)+
	moveq	#28, %d1
2:	move.l	%d3, %d0
	lsr.l	%d1, %d0
	andi.l	#15, %d0
	addi.l	#'0', %d0
	cmpi.l	#'9'+1, %d0
	bcs.s	3f
	addq.l	#7, %d0			/* 'A'..'F' */
3:	move.b	%d0, (%a0)+
	subq.l	#4, %d1
	bpl.s	2b
	move.l	#pv_src, (%a2)
	clr.l	4(%a2)
	bra.s	.Lout
.Lnone:
	clr.l	(%a2)
	clr.l	4(%a2)
	bra.s	.Lout
.Lstock:
	bsr.s	.Lorig
.Lout:
	move.l	%a2, %d0
	movea.l	%a2, %a0
	movem.l	(%sp), %d2-%d3/%a2-%a3
	lea	16(%sp), %sp
	rts
/* L'original : 0x400a3052(a0 = &résultat, &handle). Pile : retour d'ici, 16 o sauvés, retour de pv_parse, &handle. */
.Lorig:
	move.l	24(%sp), -(%sp)
	movea.l	%a2, %a0
	jsr	PARSE
	addq.l	#4, %sp
	rts

/* 0x4008171e, entrée de la note jouée en direct (piste, note, vélocité, source, sans envoi, -1, vitesse) : jmp pv_note
 * à la place du jmp pad_load_hook de Model-TG, qui ne fait que rejouer les deux instructions déplacées (link.w et
 * moveq #127) avant 0x40081724. Même filtre que l'OS pour emporter le son désigné (0x40081760, 0x4008180e), et
 * seulement la source 0x40 (pads et touches, tâche de l'interface, où le chargeur de Model-TG est appelé aussi). */
	.section .text.pv_note, "ax"
pv_note:
	move.l	ARMED, %d0
	beq.w	.Lgo
	moveq	#0x40, %d1
	cmp.l	16(%sp), %d1
	bne.w	.Lgo
	tst.l	20(%sp)
	bne.w	.Lgo
	move.l	4(%sp), %d1
	cmp.l	ACTIVE, %d1
	bne.w	.Lgo
	movea.l	%d0, %a0
	jsr	TG_TOK_OF		/* le son désigné nomme-t-il un sample ? */
	tst.l	%d0
	beq.w	.Lgo
	lea	TG_SLOT_HASH, %a0
	moveq	#63, %d1
1:	cmp.l	(%a0)+, %d0
	beq.w	.Lgo			/* déjà en mémoire */
	subq.l	#1, %d1
	bpl.s	1b
	move.l	ARMED, %d1
	cmp.l	pv_failp, %d1
	bne.s	2f			/* un autre son désigné depuis : on retente */
	cmp.l	pv_fail, %d0
	beq.s	.Lmute			/* déjà raté sur ce son désigné */
2:
	lea	-44(%sp), %sp
	movem.l	%d2-%d7/%a2-%a6, (%sp)
	move.l	%d0, %d2
	move.w	%sr, %d3
	moveq	#0, %d1
	move.w	%d3, %d1
	andi.l	#0x0700, %d1
	bne.s	.Lrest			/* seulement au niveau 0 : le chargeur attend la carte mémoire */
	move.w	#0x2700, %sr		/* prendre le chargeur sans être interrompu (led_hook le prend aussi) */
	tst.l	TG_LD_BUSY
	bne.s	.Lbusy
	moveq	#1, %d0
	move.l	%d0, TG_LD_BUSY
	move.w	%d3, %sr
	move.l	%d0, TG_PD_MODE		/* comme le préchargement : place libre, samples inutilisés seulement */
	move.l	%d2, %d0
	jsr	TG_ENSURE_LOADED
	clr.l	TG_PD_MODE
	clr.l	TG_LD_BUSY
	tst.l	%d0
	bpl.s	.Lok			/* chargé : la note joue le sample */
	move.l	%d2, pv_fail		/* raté : plus d'essai sur ce son désigné */
	move.l	ARMED, %d0
	move.l	%d0, pv_failp
	bra.s	.Lrest
.Lbusy:
	move.w	%d3, %sr		/* chargeur occupé : pas d'essai cette fois */
.Lrest:
	movem.l	(%sp), %d2-%d7/%a2-%a6
	lea	44(%sp), %sp
.Lmute:
	moveq	#1, %d0			/* « sans envoi » : la note ne va pas au moteur audio, rien ne joue */
	move.l	%d0, 20(%sp)
	bra.s	.Lgo
.Lok:
	movem.l	(%sp), %d2-%d7/%a2-%a6
	lea	44(%sp), %sp
.Lgo:
	link.w	%fp, #-104
	moveq	#127, %d0
	jmp	0x40081724

/* 0x4005910e, boucle des événements de l'interruption audio : jsr pv_copy ; bra.s 0x40059120, à la place de
 *   tst.l 48(a2) ; beq.s 0x40059120 ; move.l d2,d0 ; addi.l #147,d0 ; clr.l (a4,d0.l*4)
 * a2 = l'événement (+48 : le son d'écoute, ou 0), d2 = la piste, a4 = 0x800015a0. d0, d1, a0 et a1 sont libres
 * (réécrits après 0x40059120 avant d'être lus). Un son qui n'est pas du Sampler : l'effacement d'origine. */
	.section .text.pv_copy, "ax"
pv_copy:
	move.l	48(%a2), %d0
	beq.s	9f			/* pas une note d'écoute */
	movea.l	%d0, %a1
	move.l	%d2, %d0
	addi.l	#147, %d0
	mvz.b	38(%a1), %d1
	subq.l	#6, %d1
	bne.s	8f
	moveq	#6, %d1
	cmp.l	%d1, %d2
	bcc.s	8f
	lea	pv_tab, %a0
	movea.l	(%a0, %d2.l*4), %a0
	move.l	%a0, (%a4, %d0.l*4)	/* le son de la note : notre copie du son écouté */
	moveq	#24, %d0
1:	move.l	(%a1)+, (%a0)+
	subq.l	#1, %d0
	bpl.s	1b
	rts
8:	clr.l	(%a4, %d0.l*4)
9:	rts

/* Données, écrites dans l'image (ces masques ne sont pas remis à zéro au démarrage). Les copies doivent rester sous
 * 0x48000000, sinon sp_lock les prend pour le son de la piste : les masques y sont. */
	.section .data.pv_tab, "aw"
	.balign	4
pv_tab:	.long	pv_b0, pv_b1, pv_b2, pv_b3, pv_b4, pv_b5
pv_fail: .long	0			/* empreinte dont le chargement a raté… */
pv_failp: .long	0			/* …sur ce son désigné (ARMED à ce moment) */
	.section .data.pv_b01, "aw"
	.balign	4
pv_b0:	.space	100
pv_b1:	.space	100
	.section .data.pv_b234, "aw"
	.balign	4
pv_b2:	.space	100
pv_b3:	.space	100
pv_b4:	.space	100
	.section .data.pv_b5, "aw"
	.balign	4
pv_b5:	.space	100
	.section .data.pv_src, "aw"
	.balign	4
pv_src:	.space	100			/* le son écouté que pv_parse construit */
