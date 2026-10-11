/* Trigless trigs (lock trigs) atténués sur les touches de pas (mod de djd_oz, notes/45). Lié par trigless_dim.ld dans
 * deux masques de sprites libérés ; les écritures sur l'OS sont dans tools/gen_trigless_dim.py (HOOKS).
 *
 * L'OS montre un trigless trig comme un trig de note, allumé à fond (état de LED 4 : éteint 0,35 s toutes les 2 s).
 * Le mod lui donne son propre état, 260 (0x104, écrit par le mode grille en 0x40021f52 à la place de 4) : traité
 * comme 4 partout ailleurs, il est en plus allumé seulement 1 ms sur 3 (333 Hz, 33 %).
 *
 * Les LED sont tenues par 7 verrous 74HC373 (une rangée de 8 LED chacun, allumée ou éteinte, sans réglage de
 * lumière), chargés par l'interruption du panneau (PIT3, niveau 6, 12 interruptions par cycle de 1 ms : début,
 * 8 colonnes de touches, puis 3 étapes pour une rangée de LED ; la rangée suivante au cycle suivant, chaque rangée
 * tous les 7 ms). La version 1 (celle de djd_oz) éteignait les touches 16 ticks sur 25 de l'horloge des LED
 * (120 Hz), une impulsion vers 43 Hz que le rechargement des rangées tous les 7 ms rendait irrégulière : « une LED
 * abîmée » sur la machine. Ici la lumière est découpée dans l'interruption du panneau elle-même, à chaque cycle de
 * 1 ms : à l'étape 0 des LED, avant la rangée du tour, td_led recharge chaque rangée qui porte une touche atténuée
 * quand elle doit s'allumer ou s'éteindre, par une transaction complète comme celle de l'OS (DATA, SET du bit 3,
 * CLR du bit 3), à 2 us d'intervalle au lieu de 83 us. Les autres LED gardent la valeur que le tour d'origine leur
 * a donnée, au même instant que sans le mod. Les rangées ont des phases décalées (rangée r allumée quand
 * (phase + r) mod 3 = 0), pour que les touches ne s'allument pas toutes ensemble.
 *
 * Port du panneau : Rapid GPIO en 0x8c000000 (+0 DIR, +2 DATA, +6 CLR : les bits écrits à 0 passent à 0, +0xa SET :
 * les bits écrits à 1 passent à 1). DATA : bits 15-8 la donnée (octet de LED, 1 = éteinte), 7-5 la rangée, 3 le
 * strobe des verrous, 0 le balayage des touches (0 pour les LED).
 *
 * Contextes : td_blink et td_frame dans la tâche de l'interface (2 Hz, 30 Hz) ; td_led dans l'interruption du
 * panneau, qui ne s'imbrique pas et seule lit et écrit td_last, td_cur, td_ph et td_list. td_frame écrit td_lock en
 * deux mots longs ; un mélange de l'ancien et du nouveau relevé dure au plus 1 ms.
 *
 * Attente active dans une interruption (exception à tools/AGENTS.md, notes/45 §7) : 3 attentes de 2 us par
 * rangée rechargée, au plus 5 rangées par cycle, chacune bornée à 64 lectures du compteur de PIT3. */

	.equ	LED_BIT, 0x4010abf8		/* LED logique -> bit des 7 octets de LED (-1 : pas de LED) */
	.equ	LOCK, 260			/* état d'un trigless trig */
	.equ	RGPIO, 0x8c000000		/* +0 DIR, +2 DATA, +6 CLR, +0xa SET */
	.equ	PCNTR, 0xfc08c004		/* compteur de PIT3 (décompte, 135,168 MHz) */
	.equ	P3, 11265			/* période de PIT3 : PMR 0x2c00 + 1 */
	.ifndef PWM_N
	.equ	PWM_N, 3			/* période : 3 cycles de 1 ms, 333 Hz */
	.endif
	.ifndef PWM_ON
	.equ	PWM_ON, 1			/* allumé 1 cycle sur 3 : 33 % */
	.endif
	.ifndef WAIT
	.equ	WAIT, 272			/* coups de PIT3 entre deux écritures du port : 2,0 us (testé sur la machine ; 68 = 0,5 us, non testé) */
	.endif

	/* PAT : bit k à 1 si (k mod PWM_N) < PWM_ON ; la rangée r est allumée au cycle de phase ph si le bit r de
	 * (PAT >> ph) est à 1. */
	.set	PAT, 0
	.set	K, 0
	.set	J, 0				/* J = K mod PWM_N (« % » est le préfixe des registres) */
	.rept	16
	.if	J < PWM_ON
	.set	PAT, PAT + (1 << K)		/* (« | » ouvre un commentaire) */
	.endif
	.set	K, K + 1
	.set	J, J + 1
	.if	J == PWM_N
	.set	J, 0
	.endif
	.endr

	.globl	td_blink, td_frame, td_led, td_wait, td_lock, td_last, td_cur, td_ph

	.section .text.td_a, "ax"

/* 0x40005f36 : jmp td_blink à la place de « cmp.l 40(a4),d1 ; beq.s 0x40005f6c » (d1 = 4), dans le clignotement des
 * LED (0x40005efc, 2 Hz). Les états 4 et 260 clignotent de la même façon. d1 est libre ensuite. */
td_blink:
	move.l	40(%a4), %d1
	cmpi.l	#LOCK, %d1
	beq.s	1f
	cmpi.l	#4, %d1
	beq.s	1f
	jmp	0x40005f3c
1:	jmp	0x40005f6c

/* 0x40006086 : jmp td_frame à la place du « jmp 0x4008e77e » qui termine l'image des LED (0x40006044, tâche de
 * l'interface, 30 Hz ; 4(sp) = l'objet des LED, +40 = état des 54 LED logiques). td_lock reçoit le bit de chaque LED
 * dans l'état 260, puis l'envoi d'origine. Relevé à la fin de l'image, quand les états sont complets : un relevé au
 * milieu (entre la remise à zéro 0x4000602a et le mode grille) n'en trouverait aucun. Garde d2-d7/a2-a6. */
td_frame:
	movea.l	4(%sp), %a0
	lea	-12(%sp), %sp
	movem.l	%d2-%d4, (%sp)
	clr.l	-(%sp)				/* le relevé en construction : 8 octets sur la pile */
	clr.l	-(%sp)
	lea	40(%a0), %a0
	lea	LED_BIT, %a1
	moveq	#54, %d4
1:	move.l	(%a0)+, %d0
	move.l	(%a1)+, %d2
	cmpi.l	#LOCK, %d0
	bne.s	2f
	tst.l	%d2
	bmi.s	2f
	move.l	%d2, %d3
	lsr.l	#3, %d3				/* octet (rangée) */
	bset	%d2, (%sp, %d3.l)		/* bit (numéro modulo 8) */
2:	subq.l	#1, %d4
	bne.s	1b
	move.l	(%sp)+, td_lock
	move.l	(%sp)+, td_lock+4
	movem.l	(%sp), %d2-%d4
	lea	12(%sp), %sp
	jmp	0x4008e77e

	.section .text.td_b, "ax"

/* 0x40059dea : jmp td_led ; nop ; nop à la place de « moveq #-1,d3 ; moveq #21,d4 ; move.w d3,0x8c000000 » (DIR =
 * 0xffff), à l'étape 0 des LED de l'interruption du panneau (0x40059db8). Entrée : d0.b = shadow[rangée du tour]
 * (0x40140aa8), d1 = 0 (étape), d2 = rangée du tour 0..6, d3/d4 libres. Sortie (jmp 0x40059df4) : d0.b = octet à
 * verrouiller pour la rangée du tour (l'OS l'écrit aussitôt avec sa rangée, strobe aux étapes 1 et 2), d1 = 0,
 * d2 inchangé, d4 = 21, DIR = 0xffff écrit. Garde d5-d7/a1-a2 (l'OS garde d0-d4/a0).
 *
 * td_last (L) : dernier octet que le tour d'origine a verrouillé pour chaque rangée ; td_cur (C) : octet que tient
 * chaque verrou. Pour chaque rangée r : D = L[r], plus les bits de td_lock[r] (forcés à 1, éteints) si la rangée est
 * dans sa phase éteinte ; si D != C[r], transaction et C[r] = D. Puis la rangée du tour : L = shadow, S = shadow
 * (plus td_lock si éteinte), C = S. Sans trigless trig ni rangée à rétablir : L = C = shadow pour la rangée du tour,
 * et les écritures sur le port sont celles de l'origine. */
td_led:
	lea	-20(%sp), %sp
	movem.l	%d5-%d7/%a1-%a2, (%sp)
	lea	td_lock, %a1			/* +0 lock[8], +8 L[8], +16 C[8], +24 ph, +28 liste[7 mots] */
	moveq	#-1, %d3			/* d3 = -1 : DIR encore à écrire */
	move.l	(%a1), %d4
	or.l	4(%a1), %d4
	bne.s	2f				/* des touches atténuées */
	move.l	8(%a1), %d4
	cmp.l	16(%a1), %d4
	bne.s	2f				/* une rangée à rétablir */
	move.l	12(%a1), %d4
	cmp.l	20(%a1), %d4
	bne.s	2f
	move.b	%d0, 8(%a1, %d2.l)		/* comme l'origine : L = C = shadow */
	move.b	%d0, 16(%a1, %d2.l)
	bra.w	8f

2:	move.l	24(%a1), %d4			/* phase suivante, 0..PWM_N-1 */
	addq.l	#1, %d4
	moveq	#PWM_N, %d5
	cmp.l	%d5, %d4
	bcs.s	1f
	moveq	#0, %d4
1:	move.l	%d4, 24(%a1)
	move.l	#PAT, %d5
	lsr.l	%d4, %d5			/* d5 bit r : rangée r allumée à ce cycle */
	lea	28(%a1), %a2
	moveq	#6, %d6				/* r = 6..0 */
	moveq	#0, %d7				/* mots dans la liste */
3:	moveq	#0, %d4
	btst	%d6, %d5
	bne.s	4f				/* phase allumée : rien de forcé */
	mvz.b	(%a1, %d6.l), %d4		/* phase éteinte : lock[r] */
4:	mvz.b	8(%a1, %d6.l), %d1		/* L[r] */
	or.l	%d1, %d4			/* D */
	mvz.b	16(%a1, %d6.l), %d1		/* C[r] */
	cmp.l	%d1, %d4
	beq.s	5f
	move.b	%d4, 16(%a1, %d6.l)		/* C[r] = D */
	lsl.l	#8, %d4
	move.l	%d6, %d1
	lsl.l	#5, %d1
	or.l	%d1, %d4			/* (D << 8) | (r << 5) : strobe (bit 3) et balayage (bit 0) à 0 */
	move.w	%d4, (%a2)+
	addq.l	#1, %d7
5:	subq.l	#1, %d6
	bpl.s	3b
	move.b	%d0, 8(%a1, %d2.l)		/* rangée du tour : L = shadow */
	moveq	#0, %d4
	btst	%d2, %d5
	bne.s	6f
	mvz.b	(%a1, %d2.l), %d4
6:	or.l	%d4, %d0			/* S = shadow, plus lock si éteinte */
	move.b	%d0, 16(%a1, %d2.l)		/* C = S (verrouillé par l'OS aux étapes 1 et 2) */
	tst.l	%d7
	beq.s	8f
	lea	28(%a1), %a1
	movea.l	#RGPIO, %a2
	move.w	%d3, (%a2)			/* DIR = 0xffff (déplacé), puis aussitôt les transactions */
	moveq	#0, %d3
7:	move.w	(%a1)+, %d4
	move.w	%d4, 2(%a2)			/* DATA : donnée et rangée, strobe bas */
	bsr.w	td_wait
	moveq	#8, %d4
	move.w	%d4, 10(%a2)			/* SET bit 3 : le verrou de la rangée suit la donnée */
	bsr.w	td_wait
	moveq	#-9, %d4
	move.w	%d4, 6(%a2)			/* CLR bit 3 : le verrou garde la donnée */
	bsr.w	td_wait
	subq.l	#1, %d7
	bne.s	7b
8:	movem.l	(%sp), %d5-%d7/%a1-%a2
	lea	20(%sp), %sp
	moveq	#0, %d1				/* étape 0 */
	moveq	#21, %d4			/* (déplacé) */
	tst.l	%d3
	beq.s	9f
	move.w	%d3, RGPIO			/* (déplacé) DIR = 0xffff */
9:	jmp	0x40059df4

/* Attend WAIT coups de PIT3 après la fin de l'écriture précédente, au plus 64 lectures du compteur. Détruit d1 et
 * d4-d6. */
td_wait:
	nop					/* ColdFire : nop attend la fin des écritures en cours */
	moveq	#64, %d4
	mvz.w	PCNTR, %d5
1:	subq.l	#1, %d4
	beq.s	3f
	mvz.w	PCNTR, %d1
	move.l	%d5, %d6
	sub.l	%d1, %d6			/* écoulé = début - maintenant (décompte) */
	bpl.s	2f
	addi.l	#P3, %d6			/* le compteur s'est rechargé entre les deux lectures */
2:	cmpi.l	#WAIT, %d6
	bcs.s	1b
3:	rts

	.section .data.td, "aw"
	.balign	4
td_lock: .space	8				/* +0  bits des LED dans l'état 260 (octet = rangée), par td_frame */
td_last: .byte	0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff	/* +8  L, 1 = éteinte */
td_cur:	.byte	0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff	/* +16 C */
td_ph:	.long	0				/* +24 phase, 0..PWM_N-1 */
td_list: .space	14				/* +28 mots DATA des transactions du cycle */
