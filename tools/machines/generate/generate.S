/* Générateur de trigs « Generate » (idée et première version : DavidCaruso, Model-TG-VA-DR-v1) : tenir SETTINGS
 * et appuyer sur TRACK ouvre une liste de réglages par-dessus l'écran ; sa dernière ligne, GEN, réécrit la piste
 * sélectionnée avec un motif euclidien ou aléatoire, des notes tirées dans une gamme et des vélocités tirées entre
 * deux bornes. Réécrit pour ce dépôt (David n'a publié ni source ni licence) ; s'installe sur Model-TG (requires
 * model-tg ou model-tg-st). Lié par generate.ld dans des masques de sprites 48x22 libérés (tools/sprites.py) ; les
 * écritures sur l'OS sont dans tools/gen_generate.py. Note : notes/56 §2.
 *
 * Accroche : 0x4007240c, l'accesseur du code d'un KeyEvent (moveal 4(sp),a0 ; movel 12(a0),d0 ; rts), que tout
 * consommateur d'une touche appelle. Model-TG y met « jmp key_hook » ; le tweak remplace ces 6 octets par
 * « jmp gen_key ». gen_key rend exactement ce que rend key_hook, sauf pour l'accord SETTINGS + TRACK :
 *   - toute touche autre que TRACK (code 2), et TRACK quand la page Retrig ou l'éditeur de tranches de Model-TG est
 *     ouvert (rtg_on, sle_on : key_hook les traite avant tout le reste) : jmp key_hook, sans rien toucher ;
 *   - un appui frais de TRACK (bit 0 levé, bit 3 « répétition » baissé) pendant que SETTINGS est tenu (set_held de
 *     Model-TG) : gen_open ; si un menu s'est ouvert (mm_opened, comme les accords de Model-TG), l'appui est avalé :
 *     bit 3 levé dans l'événement (les lectures suivantes le voient comme une répétition), d0 = 0, mod_used = 1 (le
 *     relâchement de SETTINGS n'ouvre pas le Config Menu, kh_mod de Model-TG) ;
 *   - les lectures suivantes de cet appui et ses répétitions : avalées ; son relâchement : avalé, à chaque lecture
 *     (gen_ev retient l'adresse de l'événement) ; un appui frais suivant oublie tout ;
 *   - le reste (TRACK seul, accord refusé) : jmp key_hook.
 * Registres : d0, d1, a0, a1 détruits (comme key_hook), tout le reste gardé.
 *
 * Le menu : la liste générique de Model-TG (lm_build, notes/31), qu'on prépare comme gran_menu_open : mêmes
 * prologue et cadre (link.w fp,#-80 ; 28 o de registres), refus en interruption, interface pas prête, liste de
 * Model-TG déjà ouverte (gm_live : accord avalé, rien de plus), piste sélectionnée >= 6 ; puis gm_track = la piste
 * sélectionnée, gm_cur = gen_desc, et jmp lm_build, qui construit, présente et sort par gm_done. LEVEL/DATA (gm_enc,
 * accroche 0x400081ce de Model-TG) et SETTINGS qui ferme (gm_key_th) viennent avec. lm_build lit 13 lignes de quatre
 * fermetures {libellé, valeur, rotation, appui} ; toutes les lignes ont les mêmes, construites sur la pile de gen_open
 * (la pile de la tâche de l'interface fait 160 Ko, notes/44) : chaque fermeture reçoit l'élément de menu en
 * deuxième argument, et l'élément porte son numéro de ligne en +8 (0x40072ce6 l'y écrit par 0x4007320a avant que
 * rien ne l'appelle).
 *
 * Adresses de Model-TG (symboles de 30-model-tg.json / 30-model-tg-st.json, les mêmes dans les deux), par -D :
 *   TG_KEY_HOOK, TG_SET_HELD, TG_MOD_USED, TG_RTG_ON, TG_SLE_ON, TG_MM_OPENED, TG_GM_LIVE, TG_GM_OPENED, TG_GM_DONE,
 *   TG_GM_TRACK, TG_GM_CUR, TG_LM_BUILD, TG_GM_LAB (a0 = String, a1 = texte), TG_GM_VAL (a0 = &index, a1 = table
 *   de pointeurs de textes ; dessine), TG_GM_VNAME (« GranularMenuView », le nom de vue de ses listes),
 *   TG_NEW_SLOT2 (appui : bascule l'édition de la ligne), TG_SHOW_POPUP (message à l'écran). */

#define KEY_TRACK	2
#define NROWS		13		/* 12 réglages + GEN */
#define OS_UI_READY	0x40fe4178	/* interface prête (gran_menu_open, show_popup) */
#define OS_PROJECT	0x400cf866	/* projet */
#define OS_TRKSEL	0x4000eb90	/* (projet) -> sélection */
#define OS_SELTRACK	0x40012412	/* (sélection) -> piste sélectionnée */
#define OS_PATTERN	0x4000f208	/* -> pattern en cours, côté interface */
#define OS_TRACK	0x4000cfcc	/* (pattern, piste) -> objet « piste » (notes/32) */
#define OS_LEN		0x40016402	/* (piste) -> longueur effective */
#define OS_TRIG		0x40017b48	/* (piste, pas, 0/1) : trig de note effacé / posé, comme la grille */
#define OS_NOTE		0x40016642	/* (piste, pas, note) : note du pas, -1 = aucune (+580) */
#define OS_VEL		0x400166c2	/* (piste, pas, vélocité) : vélocité du pas, -1 = aucune (+128) */
#define OS_VSPRINTF	0x400005cc	/* (texte, format, &arguments) */
#define OS_CLOCK	0x8000184c	/* heure musicale (notes/38) : la graine */

/* gen_ram : réglages (valeurs affichées), puis l'état ; R_* = décalages depuis gen_set (a3 dans gen_go) */
#define S_MOD	0
#define S_DNS	1
#define S_HIT	2
#define S_ROT	3
#define S_NOT	4
#define S_KEY	5
#define S_SCL	6
#define S_OCT	7
#define S_RNG	8
#define S_VEL	9
#define S_VMN	10
#define S_VMX	11
#define R_RNG	16

	.globl	gen_key, gen_open, gen_lab, gen_val, gen_turn, gen_press, gen_go, gen_notes, gen_step, gen_out
	.globl	gen_adv, gen_put, gen_rndn
	.globl	gen_set, gen_rng, gen_ev, gen_ptr, gen_zero, gen_num, gen_desc
	.globl	gen_min, gen_max, gen_noff, gen_labels, gen_scales, gen_title, gen_fmt

/* ---- l'accord : 0x4007240c -> jmp gen_key ---- */
	.section .text.gen_key, "ax"
gen_key:
	movea.l	4(%sp), %a0
	move.l	12(%a0), %d0		/* ce que rend l'accesseur d'origine */
	moveq	#KEY_TRACK, %d1
	cmp.l	%d1, %d0
	bne.s	.Lk_tg
	move.l	TG_RTG_ON, %d1
	or.l	TG_SLE_ON, %d1
	bne.s	.Lk_tg			/* page Retrig, éditeur de tranches : à eux */
	lea	gen_ev(%pc), %a1
	move.l	16(%a0), %d1		/* drapeaux : bit 0 appui, bit 3 répétition */
	btst	#0, %d1
	beq.s	.Lk_up
	btst	#3, %d1
	bne.s	.Lk_rep
	clr.l	(%a1)			/* appui frais : rien d'avalé en cours */
	tst.l	TG_SET_HELD
	beq.s	.Lk_tg			/* TRACK seul */
	move.l	%a0, -(%sp)
	bsr.w	gen_open
	movea.l	(%sp)+, %a0
	tst.l	TG_MM_OPENED
	beq.s	.Lk_tg			/* pas de menu : TRACK comme d'habitude */
	moveq	#1, %d1
	move.l	%d1, gen_ev		/* l'appui est à nous, et son relâchement */
	move.l	%d1, TG_MOD_USED	/* pas de Config Menu au relâchement de SETTINGS */
	moveq	#8, %d1
	or.l	%d1, 16(%a0)		/* les lectures suivantes y voient une répétition */
.Lk_eat:
	moveq	#0, %d0
	rts
.Lk_rep:
	moveq	#1, %d1
	cmp.l	(%a1), %d1
	beq.s	.Lk_eat			/* l'appui avalé, relu, ou ses répétitions */
	bra.s	.Lk_tg
.Lk_up:
	move.l	(%a1), %d1
	beq.s	.Lk_tg
	cmp.l	%a0, %d1
	beq.s	.Lk_eat			/* le relâchement avalé, relu */
	subq.l	#1, %d1
	bne.s	.Lk_tg
	move.l	%a0, (%a1)		/* le relâchement de l'appui avalé : avalé, retenu */
	bra.s	.Lk_eat
.Lk_tg:
	jmp	TG_KEY_HOOK

/* ---- ouverture : les 13 lignes sur la pile, puis la liste de Model-TG ---- */
	.section .text.gen_open, "ax"
gen_open:
	moveq	#NROWS, %d0
1:	pea	gen_press(%pc)		/* une ligne {libellé, valeur, rotation, appui}, empilée à l'envers */
	pea	gen_turn(%pc)
	pea	gen_val(%pc)
	pea	gen_lab(%pc)
	subq.l	#1, %d0
	bne.s	1b
	lea	gen_desc(%pc), %a0
	move.l	%sp, 12(%a0)		/* lu par lm_build seulement, pendant la construction */
	bsr.s	gen_build
	lea	NROWS*16(%sp), %sp
	rts
gen_build:				/* le début de gran_menu_open, sans le test « Sampler » */
	link.w	%fp, #-80
	lea	-28(%sp), %sp
	movem.l	%d2-%d4/%a2-%a5, (%sp)
	clr.l	TG_MM_OPENED
	moveq	#0, %d0
	move.w	%sr, %d0
	andi.l	#0x700, %d0
	bne.s	9f			/* en interruption : non */
	tst.l	OS_UI_READY
	beq.s	9f
	jsr	TG_GM_LIVE
	tst.l	%d0
	bne.s	8f			/* une liste de Model-TG déjà ouverte */
	jsr	OS_PROJECT
	move.l	%d0, -(%sp)
	jsr	OS_TRKSEL
	move.l	%d0, (%sp)
	jsr	OS_SELTRACK
	addq.l	#4, %sp
	moveq	#6, %d1
	cmp.l	%d1, %d0
	bcc.s	9f
	move.l	%d0, TG_GM_TRACK	/* la piste visée par GEN */
	lea	gen_desc(%pc), %a0
	move.l	%a0, TG_GM_CUR
	jmp	TG_LM_BUILD		/* construit, présente, sort par gm_opened / gm_done */
8:	jmp	TG_GM_OPENED
9:	jmp	TG_GM_DONE

/* ---- les fermetures des lignes : (stockage, élément, …) ; ligne = élément +8 ---- */
	.section .text.gen_ui, "ax"
gen_lab:				/* a0 = la String à remplir */
	movea.l	8(%sp), %a1
	move.l	8(%a1), %d0
	lea	gen_labels(%pc), %a1
	lea	(%a1,%d0.l*4), %a1
	jmp	TG_GM_LAB
gen_val:				/* (stockage, élément, contexte, cadre, état) : gm_val dessine */
	movea.l	8(%sp), %a0
	move.l	8(%a0), %d1
	lea	gen_set(%pc), %a0
	mvz.b	(%a0,%d1.l), %d0	/* la valeur */
	lea	gen_noff(%pc), %a1
	mvz.b	(%a1,%d1.l), %d1	/* ses noms (décalage depuis gen_noff), 0 = un nombre */
	beq.s	1f
	adda.l	%d1, %a1
	lea	(%a1,%d0.l*4), %a1
	bra.s	2f
1:	move.l	%d0, -(%sp)
	pea	(%sp)
	pea	gen_fmt+7(%pc)		/* « %d » */
	pea	gen_num(%pc)
	jsr	OS_VSPRINTF
	lea	16(%sp), %sp
	lea	gen_num(%pc), %a1
2:	lea	gen_ptr(%pc), %a0	/* gm_val(&0, {texte}) */
	move.l	%a1, (%a0)+
	lea	-4(%a0), %a1
	jmp	TG_GM_VAL
gen_turn:				/* (stockage, élément, écart) : valeur + écart, bornée */
	movea.l	8(%sp), %a0
	move.l	8(%a0), %d0
	lea	gen_set(%pc), %a0
	adda.l	%d0, %a0
	lea	gen_min(%pc), %a1
	adda.l	%d0, %a1
	mvz.b	(%a0), %d1
	add.l	12(%sp), %d1
	mvz.b	(%a1), %d0
	cmp.l	%d0, %d1
	bge.s	1f
	move.l	%d0, %d1
1:	mvz.b	NROWS(%a1), %d0		/* gen_max */
	cmp.l	%d0, %d1
	ble.s	2f
	move.l	%d0, %d1
2:	move.b	%d1, (%a0)
	rts

/* ---- appui : GEN génère, les autres lignes passent en édition ---- */
	.section .text.gen_press, "ax"
gen_press:				/* (stockage, élément) */
	movea.l	8(%sp), %a0
	moveq	#NROWS-1, %d0
	cmp.l	8(%a0), %d0
	beq.w	gen_go
	jmp	TG_NEW_SLOT2

/* ---- la génération, sur la piste gm_track (celle de l'ouverture) ----
 * Registres : a2 = objet « piste », a3 = gen_set, a4 = table des notes (sur la pile), a5 = k (coups euclidiens),
 * d2 = pas, d3 = n (longueur, 64 au plus), d4 = trig du pas (0/1), d5 = trigs posés, d6 = nombre de notes,
 * d7 = accumulateur euclidien. Chaque pas de 0 à n-1 est réécrit par les accesseurs de la grille, dans l'ordre de
 * l'enregistrement en direct (0x40012158) : trig (0x40017b48), note (0x40016642), vélocité (0x400166c2). */
	.section .text.gen_go, "ax"
gen_go:
	lea	-96(%sp), %sp
	movem.l	%d2-%d7/%a2-%a5, (%sp)
	lea	40(%sp), %a4		/* table des notes (49 au plus), puis le texte du message */
	lea	gen_set(%pc), %a3
	jsr	OS_PROJECT
	move.l	%d0, -(%sp)
	jsr	OS_PATTERN
	move.l	TG_GM_TRACK, (%sp)
	move.l	%d0, -(%sp)
	jsr	OS_TRACK
	addq.l	#8, %sp
	movea.l	%d0, %a2		/* objet « piste » de l'interface */
	move.l	%d0, -(%sp)
	jsr	OS_LEN
	addq.l	#4, %sp
	move.l	%d0, %d3		/* n : longueur de la piste, 64 au plus */
	ble.w	gen_out
	moveq	#64, %d0
	cmp.l	%d0, %d3
	bls.s	1f
	move.l	%d0, %d3
1:	move.l	R_RNG(%a3), %d0		/* nouvelle graine : + heure musicale + 0x9e3779b9, jamais 0 */
	add.l	OS_CLOCK, %d0
	addi.l	#0x9e3779b9, %d0
	bne.s	2f
	moveq	#1, %d0
2:	move.l	%d0, R_RNG(%a3)
	moveq	#0, %d6
	tst.b	S_NOT(%a3)
	beq.s	5f
	bsr.w	gen_notes
5:	mvz.b	S_HIT(%a3), %d0		/* euclidien : k = min(HIT, n) coups */
	cmp.l	%d3, %d0
	bls.s	6f
	move.l	%d3, %d0
6:	movea.l	%d0, %a5
	mvz.b	S_ROT(%a3), %d0		/* r = ROT mod n */
7:	cmp.l	%d3, %d0
	bcs.s	8f
	sub.l	%d3, %d0
	bra.s	7b
8:	move.l	%d3, %d2
	sub.l	%d0, %d2		/* accumulateur avancé de n - r pas (de 1 à n) : */
	moveq	#0, %d7			/* au pas s, d7 = ((s - r) mod n) x k mod n */
9:	bsr.w	gen_adv
	subq.l	#1, %d2
	bne.s	9b
	moveq	#0, %d5			/* d2 = 0 : le pas ; d5 : trigs posés */
	bra.w	gen_step

/* la table des notes : de 12 x (OCT + 1) + KEY à 12 x RNG demi-tons plus haut, inclus, les degrés de la gamme,
 * 127 au plus ; d6 = leur nombre (au moins la tonique) ; détruit d0, d1, d2, d4, a0 */
	.section .text.gen_notes, "ax"
gen_notes:
	mvz.b	S_OCT(%a3), %d0
	addq.l	#1, %d0
	mulu.w	#12, %d0
	mvz.b	S_KEY(%a3), %d1
	add.l	%d1, %d0		/* note de départ */
	mvz.b	S_SCL(%a3), %d1
	lea	gen_scales(%pc), %a0
	mvz.w	(%a0,%d1.l*2), %d1	/* degrés de la gamme, bit 0 = tonique */
	mvz.b	S_RNG(%a3), %d4
	mulu.w	#12, %d4		/* écart de 0 à 12 x RNG */
	moveq	#127, %d2
1:	lsr.l	#1, %d1			/* le bit de ce degré, remis en haut : rotation sur 12 bits */
	bcc.s	2f
	bset	#11, %d1
	cmp.l	%d2, %d0
	bhi.s	2f			/* au-dessus de 127 : non */
	move.b	%d0, (%a4,%d6.l)
	addq.l	#1, %d6
2:	addq.l	#1, %d0
	subq.l	#1, %d4
	bpl.s	1b
	rts

	.section .text.gen_loop, "ax"
gen_step:
	tst.b	S_MOD(%a3)
	bne.s	1f
	moveq	#100, %d1		/* aléatoire : trig si le tirage (0..99) < DNS */
	bsr.w	gen_rndn
	mvz.b	S_DNS(%a3), %d1
	bra.s	2f
1:	move.l	%d7, %d0		/* euclidien : trig si l'accumulateur < k */
	move.l	%a5, %d1
	bsr.w	gen_adv
2:	moveq	#0, %d4
	cmp.l	%d1, %d0
	bcc.s	3f
	moveq	#1, %d4
	addq.l	#1, %d5
3:	move.l	%d4, %d0
	lea	OS_TRIG, %a0
	bsr.w	gen_put			/* trig de note posé (1) ou effacé (0) */
	moveq	#-1, %d0
	tst.l	%d4
	beq.s	4f
	tst.b	S_NOT(%a3)
	beq.s	4f
	move.l	%d6, %d1
	bsr.w	gen_rndn
	mvz.b	(%a4,%d0.l), %d0	/* une note de la table */
4:	lea	OS_NOTE, %a0
	bsr.w	gen_put			/* note du pas (-1 : aucune) */
	moveq	#-1, %d0
	tst.l	%d4
	beq.s	6f
	tst.b	S_VEL(%a3)
	beq.s	6f
	mvz.b	S_VMN(%a3), %d0
	mvz.b	S_VMX(%a3), %d1
	cmp.l	%d0, %d1
	bcc.s	5f
	movea.l	%d0, %a0		/* VMN > VMX : échangés */
	move.l	%d1, %d0
	move.l	%a0, %d1
5:	sub.l	%d0, %d1
	addq.l	#1, %d1
	movea.l	%d0, %a0
	bsr.w	gen_rndn
	add.l	%a0, %d0		/* de VMN à VMX */
6:	lea	OS_VEL, %a0
	bsr.w	gen_put			/* vélocité du pas (-1 : aucune) */
	addq.l	#1, %d2
	cmp.l	%d3, %d2
	bcs.w	gen_step
	move.l	%d5, -(%sp)		/* « Trigs: N » */
	pea	(%sp)
	pea	gen_fmt(%pc)
	move.l	%a4, -(%sp)
	jsr	OS_VSPRINTF
	move.l	%a4, (%sp)
	jsr	TG_SHOW_POPUP
	lea	16(%sp), %sp
gen_out:
	movem.l	(%sp), %d2-%d7/%a2-%a5
	lea	96(%sp), %sp
	rts
gen_adv:				/* d7 = (d7 + k) mod n */
	add.l	%a5, %d7
	cmp.l	%d3, %d7
	bcs.s	1f
	sub.l	%d3, %d7
1:	rts

	.section .text.gen_put, "ax"
gen_put:				/* a0(piste a2, pas d2, valeur d0) */
	move.l	%d0, -(%sp)
	move.l	%d2, -(%sp)
	move.l	%a2, -(%sp)
	jsr	(%a0)
	lea	12(%sp), %sp
	rts

	.section .text.gen_rndn, "ax"
gen_rndn:				/* d1 = m (1..127) -> d0 = ((x >> 16) x m) >> 16, 0..m-1 ; détruit d1, a1 */
	movea.l	%d1, %a1
	move.l	R_RNG(%a3), %d0		/* xorshift32 (13, 17, 5) */
	move.l	%d0, %d1
	lsl.l	#8, %d1
	lsl.l	#5, %d1
	eor.l	%d1, %d0
	move.l	%d0, %d1
	swap	%d1
	mvz.w	%d1, %d1
	lsr.l	#1, %d1
	eor.l	%d1, %d0
	move.l	%d0, %d1
	lsl.l	#5, %d1
	eor.l	%d1, %d0
	move.l	%d0, R_RNG(%a3)
	swap	%d0
	move.l	%a1, %d1
	mulu.w	%d1, %d0
	swap	%d0
	mvz.w	%d0, %d0
	rts

/* ---- état : dans le masque, valeurs de l'image à chaque démarrage (rien n'est sauvé) ---- */
	.section .data.gen_ram, "aw"
gen_set:	.byte	0, 50, 4, 0, 0, 0, 0, 4, 1, 0, 64, 127, 0	/* MOD … VMX, GEN (toujours 0) */
		.byte	0, 0, 0
gen_rng:	.long	0x2545f491	/* état du xorshift32 */
gen_ev:		.long	0		/* 1 : appui de TRACK avalé ; sinon l'adresse de son relâchement avalé */
gen_ptr:	.long	0		/* gm_val(&gen_zero, &gen_ptr) : le texte de la valeur */
gen_zero:	.long	0
gen_num:	.long	0		/* « 127 » au plus */
gen_desc:	.long	gen_title, TG_GM_VNAME, NROWS, 0	/* descripteur de Model-TG ; lignes : sur la pile */

/* ---- tables ---- */
	.section .rodata.gen_tab, "a"
gen_min:	.byte	0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0
gen_max:	.byte	1, 100, 64, 63, 1, 11, 12, 8, 4, 1, 127, 127, 0
gen_noff:	.byte	n_mod-gen_noff, 0, 0, 0, n_oo-gen_noff, n_key-gen_noff, n_scl-gen_noff, 0, 0
		.byte	n_oo-gen_noff, 0, 0, n_go-gen_noff
n_mod:		.ascii	"RND\0EUC\0"
n_oo:		.ascii	"OFF\0ON\0\0"
n_key:		.ascii	"C\0\0\0C#\0\0D\0\0\0D#\0\0E\0\0\0F\0\0\0F#\0\0G\0\0\0G#\0\0A\0\0\0A#\0\0B\0\0\0"
n_scl:		.ascii	"MAJ\0MIN\0DOR\0PHR\0LYD\0MIX\0LOC\0HMI\0MMI\0PMA\0PMI\0BLU\0CHR\0"
n_go:		.ascii	"GO\0\0"

	.section .rodata.gen_lab, "a"
gen_labels:	.ascii	"MOD\0DNS\0HIT\0ROT\0NOT\0KEY\0SCL\0OCT\0RNG\0VEL\0VMN\0VMX\0GEN\0"

	.section .rodata.gen_str, "a"
/* 13 gammes, 12 bits, bit 0 = tonique : MAJ MIN DOR PHR LYD MIX LOC, mineur harmonique, mineur mélodique,
 * penta majeure, penta mineure, blues, chromatique */
gen_scales:	.short	0xab5, 0x5ad, 0x6ad, 0x5ab, 0xad5, 0x6b5, 0x56b, 0x9ad, 0xaad, 0x295, 0x4a9, 0x4e9, 0xfff
gen_title:	.asciz	"Generate"
gen_fmt:	.asciz	"Trigs: %d"
