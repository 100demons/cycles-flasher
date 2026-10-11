/* THRU qui envoie aussi le MIDI du Cycles, commutable sur la machine (notes/53, tweak midi-live-both) : FUNC + appui
 * sur le potard LEVEL/DATA, sur la ligne OUT/THRU de CONFIG › MIDI › PORTS, quand elle affiche THR. Lié par
 * midi_thru.ld dans un masque de sprite libéré ; les écritures sur l'OS sont dans tools/gen_midi_thru.py.
 *
 * Code et idée d'AveyCole (https://github.com/AveyCole/Modded-Cycles, tools/gen_midi_live_both.py, commit ba5f8bb),
 * testé sur son Model:Cycles le 10/10/2026 (build « bth-func-05 »). Récrit ici en assembleur, instruction pour
 * instruction : mêmes octets que le build testé (tools/emu/test_midi_thru.py le vérifie), seule l'adresse change.
 *
 * Le réglage OUT/THRU est l'octet 0x404e9b50 des réglages globaux (bloc 0x404e9b10, contrôlé par une somme que
 * 0x40044b4e recalcule). L'OS n'y écrit que 0 (OUT) ou 1 (THR) : son setter 0x40044dc2 ramène toute valeur non
 * nulle à 1. Son getter 0x40044df8 rend l'octet tel quel (mvs.b), et ses six appelants ne testent que « nul ou non » :
 * l'affichage (OUT / THR), le relais du MIDI reçu (0x400012d2), la touche (0x4003560a) et trois portes de sortie qui
 * jettent le MIDI généré par le Cycles en THR. On ajoute la valeur 2 : THR + le MIDI du Cycles. L'écran affiche THR
 * et le MIDI reçu est relayé, comme pour 1 ; seules les trois portes la distinguent.
 *
 *   - midi_key (jmp depuis 0x4003560a, à la place de la touche de la ligne OUT/THRU) : FUNC tenu et la ligne sur
 *     THR (1 ou 2) -> écrit 2 si c'était 1, 1 si c'était 2, par la copie 0x40044b88 du setter (qui recalcule la
 *     somme du bloc). Sinon, le code d'origine de la touche, à l'identique : OUT <-> THR (2 -> OUT).
 *   - midi_gate (jsr depuis 0x4000154a, 0x4000156a et 0x40001590, à la place du getter) : d0 = 1 (porte fermée)
 *     seulement pour la valeur 1 ; 0 (porte ouverte) pour OUT et pour 2.
 *
 * Contrat : midi_key est entrée comme la touche d'origine, (sp) = adresse de retour, 4(sp) = argument de la ligne
 * (que la touche d'origine remplace par la nouvelle valeur avant de sauter au setter). La branche FUNC rend la main
 * par rts avec la pile intacte (link/unlk) ; d0, d1, a0, a1 changent, comme avec le setter. midi_gate ne change que
 * d0 ; les portes testent d0 (tst.l) juste après. 0x4007faf4(code) rend l'état d'une touche par son code logique :
 * 1 = FUNC (notes/33 §1, et cinq appels de l'OS avec 1). Les tailles des branchements sont fixées (.w / .s) pour
 * garder les octets du build testé. */
	.globl	midi_key, midi_gate

	.equ	OUT_THRU, 0x404e9b50		/* l'octet du réglage : 0 OUT, 1 THR, 2 THR + MIDI du Cycles */
	.equ	KEY_DOWN, 0x4007faf4		/* (code logique) -> 1 si la touche est tenue */
	.equ	GET, 0x40044df8			/* getter d'origine : mvs.b OUT_THRU,d0 */
	.equ	SET, 0x40044dc2			/* setter d'origine : (valeur != 0) -> 1, copie si différent */
	.equ	COPY, 0x40044b88		/* (destination, source, longueur) : copie et somme du bloc */

	.section .text.midi_thru, "ax"

midi_key:
	pea	1.w				/* FUNC */
	jsr	KEY_DOWN
	addq.l	#4, %sp
	tst.l	%d0
	beq.w	stock				/* FUNC relâché : touche d'origine */
	jsr	GET
	tst.l	%d0
	beq.w	stock				/* OUT : touche d'origine (-> THR) */
	move.b	OUT_THRU, %d0
	cmpi.b	#2, %d0
	beq.w	1f
	moveq	#2, %d0				/* THR -> THR + MIDI du Cycles */
	bra.w	2f
1:	moveq	#1, %d0				/* THR + MIDI du Cycles -> THR */
2:	link.w	%fp, #-4
	move.b	%d0, -1(%fp)
	pea	1.w				/* 1 octet */
	pea	-1(%fp)
	pea	OUT_THRU
	jsr	COPY
	lea	12(%sp), %sp
	unlk	%fp
	rts

/* La touche d'origine (0x4003560a..0x40035621), recopiée telle quelle : nouvelle valeur = (valeur == 0). */
stock:
	jsr	GET
	tst.l	%d0
	seq	%d0
	mvs.b	%d0, %d0
	neg.l	%d0
	move.l	%d0, 4(%sp)
	jmp	SET

midi_gate:
	move.b	OUT_THRU, %d0
	cmpi.b	#1, %d0
	beq.s	1f
	moveq	#0, %d0				/* OUT ou THR + MIDI du Cycles : la porte laisse passer */
	rts
1:	moveq	#1, %d0				/* THR seul : la porte jette le MIDI du Cycles, comme à l'origine */
	rts
