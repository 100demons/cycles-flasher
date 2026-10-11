/* Navigateur multiligne (notes/40) : le navigateur de sons, de dossiers et d'échantillons affiche ML_ROWS lignes en
 * petite police au lieu d'un seul nom en gros caractères. Lié par multiline_browser.ld dans un masque de sprite
 * libéré ; les écritures sur l'OS sont dans tools/gen_multiline_browser.py (HOOKS, PATCHES).
 *
 * Le dessin du navigateur (ModelsFileManager, 0x400a539c) boucle déjà sur les lignes visibles (i = -36(%fp), de 0 à
 * min(lignes visibles, d3) - 1), mais dessine chacune en y = 20 : avec une seule ligne, c'était la seule. Ici :
 *   - ml_bound (jsr depuis 0x400a5612, tête de la boucle) : le nombre de lignes à dessiner (voir plus bas).
 *   - ml_row (jmp depuis 0x400a5588) : la ligne i en y = ML_Y0 - ML_ROWH * i (l'écran compte y depuis le bas : la
 *     1re ligne est en haut). La ligne du curseur (24(%a2) = sélection - 1re ligne visible, 0x4007266e) passe par
 *     l'appel d'origine en 0x400a559e, que browser-scroll et Model-TG détournent vers le défilement des noms longs :
 *     lui seul défile, comme à l'origine. Les autres lignes appellent directement 0x4007199c.
 *   - ml_after (jmp depuis 0x400a55a4, au retour de cet appel) : « > » devant la ligne du curseur, et le son chargé
 *     (d7) inversé autour de son nom comme à l'origine (0x400a55b2..0x400a5604), à la hauteur de sa ligne. Puis a3
 *     revient à ML_X pour la ligne suivante.
 *   - ml_icon (jsr depuis 0x400a576e, à la place de 0x40071da4) : l'icône de dossier (25x22) ou de l'entrée spéciale
 *     (24x22) ne tient pas sur une ligne ; un petit repère de 7 px la remplace, devant le nom.
 *
 * Contrat : on est dans le cadre de 0x400a539c (%fp, a2 = le navigateur, d2 = l'écran, a3 = x du nom, a4 = le nom,
 * d4 = la chaîne de travail -16(%fp), d7 = son chargé, -32(%fp) = caractères qui tiennent, -40(%fp) = destructeur de
 * chaîne 0x400f7d5c, -44(%fp) = constructeur 0x400f980c). En 0x400a5588, la pile garde une case que l'original
 * remplit avec la police puis retire en 0x400a55a4 (lea 28) : ml_after la retire aussi. d2-d7, a2 et %fp ne
 * changent pas. ml_after remet a3 à ML_X pour la ligne suivante et, pour le son chargé, met sa largeur dans a4 comme
 * l'original (0x400a55d2 ; a4 est rechargé en 0x400a5634) ; a5 = -40(%fp) en repartant en 0x400a5608, comme
 * l'original (0x400a55ac). */
	.globl	ml_row, ml_after, ml_icon, ml_bound

	.section .text.multiline_browser, "ax"

/* d1 = y de la ligne -36(%fp). Seul d1 change. */
row_y:
	moveq	#-ML_ROWH, %d1
	muls.l	-36(%fp), %d1
	addi.l	#ML_Y0, %d1
	rts

/* 0x400a5612 (tête de la boucle des lignes) : jsr ml_bound ; bra.s 0x400a5624, à la place de « d0 = vt[64] (lignes
 * visibles), borné par d3 ». d3 = le nombre d'entrées, moins une hors de la racine (0x400a5404 : l'entrée 0 y est le
 * retour au dossier parent). Avec une seule ligne visible, min(1, d3) dessinait toujours la ligne du curseur ; avec
 * ML_ROWS lignes, un dossier de 1 ou 2 éléments revenu en haut (1re ligne = 0) perdrait sa dernière entrée, et le
 * curseur avec elle. Rend d0 = min(ML_ROWS, nombre d'entrées - 1re ligne visible) ; d3 ne change pas (le compteur).
 * d1, a0, a1 changent, comme avec l'appel d'origine. */
ml_bound:
	move.l	%a2, -(%sp)
	movea.l	(%a2), %a0
	movea.l	12(%a0), %a0
	jsr	(%a0)				/* vt[12] : nombre d'entrées */
	addq.l	#4, %sp
	sub.l	20(%a2), %d0			/* moins la 1re ligne visible */
	moveq	#ML_ROWS, %d1
	cmp.l	%d1, %d0
	ble.s	1f
	move.l	%d1, %d0
1:	rts

/* 0x400a5588 : jmp ml_row. La case de pile de l'original reçoit la police, comme lui. */
ml_row:
	move.l	652(%a2), (%sp)
	jsr	0x400720f8			/* police -> poignée (d0) */
	bsr.w	row_y
	move.l	%a4, -(%sp)			/* le nom */
	move.l	-32(%fp), -(%sp)		/* ses caractères qui tiennent */
	move.l	%d1, -(%sp)			/* y */
	move.l	%a3, -(%sp)			/* x */
	move.l	%d0, -(%sp)
	move.l	%d2, -(%sp)			/* l'écran */
	move.l	-36(%fp), %d0
	cmp.l	24(%a2), %d0			/* la ligne du curseur ? */
	beq.s	1f
	jsr	0x4007199c
	bra.s	ml_after
1:	jmp	0x400a559e			/* l'appel d'origine, défilement compris */

/* 0x400a55a4 : jmp ml_after, au retour de l'appel d'origine. */
ml_after:
	lea	28(%sp), %sp			/* les 6 arguments et la case, comme 0x400a55a4 */
	movea.l	-40(%fp), %a5			/* comme 0x400a55ac */
	move.l	-36(%fp), %d0
	cmp.l	24(%a2), %d0
	bne.s	2f
	move.l	652(%a2), -(%sp)		/* « > » devant la ligne du curseur */
	jsr	0x400720f8
	addq.l	#4, %sp
	bsr.w	row_y
	pea	ml_gt(%pc)
	pea	1
	move.l	%d1, -(%sp)
	pea	ML_CUR_X
	move.l	%d0, -(%sp)
	move.l	%d2, -(%sp)
	jsr	0x4007199c
	lea	24(%sp), %sp
2:	tst.b	%d7				/* le son chargé : son nom inversé, comme 0x400a55b2..0x400a5604 */
	beq.s	3f
	pea	-20(%fp)
	move.l	%a4, -(%sp)
	move.l	%d4, -(%sp)
	movea.l	-44(%fp), %a0
	jsr	(%a0)				/* 0x400f980c : la chaîne affichée */
	move.l	-32(%fp), -(%sp)
	move.l	%d4, -(%sp)
	move.l	652(%a2), -(%sp)
	jsr	0x400722b2			/* sa largeur */
	move.l	%d4, -(%sp)
	movea.l	%d0, %a4
	jsr	(%a5)
	move.l	652(%a2), -(%sp)
	jsr	0x40072296			/* la hauteur de la police */
	lea	32(%sp), %sp
	bsr.w	row_y
	pea	-1
	add.l	%d1, %d0
	addq.l	#1, %d0
	move.l	%d0, -(%sp)			/* y + 1 + hauteur */
	pea	1(%a3,%a4.l)			/* x + 1 + largeur */
	subq.l	#2, %d1
	move.l	%d1, -(%sp)			/* y - 2 */
	pea	-2(%a3)				/* x - 2 */
	move.l	%d2, -(%sp)
	jsr	0x40070f6e
	lea	24(%sp), %sp
3:	movea.w	#ML_X, %a3			/* la ligne suivante repart à gauche */
	jmp	0x400a5608

/* 0x400a576e : jsr ml_icon(écran, icône, 2, 20, 0) à la place de 0x40071da4. Petit repère de 7 px en ML_X, à la
 * hauteur des majuscules (y+1..y+7) : un dossier pour un dossier (0x40fe2d60), un carré creux pour l'entrée spéciale
 * (0x40fe3824). Chaque repère : deux rectangles 0x40070dea(écran, x0, y0, x1, y1, couleur), bornes comprises. */
ml_icon:
	lea	-16(%sp), %sp
	movem.l	%d2-%d4/%a2, (%sp)
	move.l	20(%sp), %d2			/* l'écran */
	lea	mk_folder(%pc), %a2
	move.l	24(%sp), %d0			/* l'icône */
	cmpi.l	#0x40fe2d60, %d0
	beq.s	1f
	lea	mk_special(%pc), %a2
1:	bsr.w	row_y
	move.l	%d1, %d3			/* y */
	moveq	#2, %d4
2:	mvs.b	(%a2)+, %d0			/* couleur */
	move.l	%d0, -(%sp)
	mvs.b	(%a2)+, %d0			/* y1 - y */
	add.l	%d3, %d0
	move.l	%d0, -(%sp)
	mvs.b	(%a2)+, %d0			/* x1 */
	move.l	%d0, -(%sp)
	mvs.b	(%a2)+, %d0			/* y0 - y */
	add.l	%d3, %d0
	move.l	%d0, -(%sp)
	mvs.b	(%a2)+, %d0			/* x0 */
	move.l	%d0, -(%sp)
	move.l	%d2, -(%sp)
	jsr	0x40070dea
	lea	24(%sp), %sp
	subq.l	#1, %d4
	bne.s	2b
	movem.l	(%sp), %d2-%d4/%a2
	lea	16(%sp), %sp
	rts

	.section .rodata.multiline_browser, "a"
ml_gt:	.asciz	">"
/* (couleur, y1 - y, x1, y0 - y, x0) : deux rectangles par repère */
mk_folder:
	.byte	1, 5, ML_X + 6, 1, ML_X		/* le corps, 7 x 5 */
	.byte	1, 6, ML_X + 2, 6, ML_X		/* l'onglet, 3 x 1 au-dessus à gauche */
mk_special:
	.byte	1, 7, ML_X + 6, 1, ML_X		/* un carré de 7 x 7... */
	.byte	0, 6, ML_X + 5, 2, ML_X + 1	/* ... évidé */
