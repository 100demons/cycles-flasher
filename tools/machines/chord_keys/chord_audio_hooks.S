/* Crochet de la sélection des intervalles CHORD (notes/42).
 * Remplace à 0x400ab0e4 : addal #0x4012142c,%a0 (six octets).
 * Entrée : a3 = copie locale de chord_audio_update ; a0 = SHAPE * 16.
 * Détour JMP : le chemin actif écrit les quatre rapports dans a2 (voix) puis
 * rejoint 0x400ab158, après les seuls déplacements d'octave COLOR. Les gains
 * COLOR ont déjà été calculés en 0x400ab0c4 et restent natifs. d2, a2, a3 et SP
 * sont conservés ; les scratch d0/d1/d3/d4/d5/a0 ne sont pas lus avant leur
 * remplacement à la reprise. Le premier move.l de la suite remplace CCR.
 * Chemin inactif : instruction déplacée puis reprise exacte en 0x400ab0ea.
 * Le détournement de l'entrée 0x400aae88 est obligatoire avec ce hook, même
 * lorsqu'un autre mod a recopié la table de dispatch des moteurs.
 */
#include "chord_audio.h"
    .text
    .align 2
    .global chord_audio_ratios
    .type chord_audio_ratios,@function
chord_audio_ratios:
    tst.l %a3@(CK_AUDIO_ACTIVE_OFFSET)
    beq.s 1f
    move.l %a3@(CK_AUDIO_RATIOS_OFFSET),%a2@(0x50)
    move.l %a3@(CK_AUDIO_RATIOS_OFFSET+4),%a2@(0xc8)
    move.l %a3@(CK_AUDIO_RATIOS_OFFSET+8),%a2@(0x140)
    move.l %a3@(CK_AUDIO_RATIOS_OFFSET+12),%a2@(0x1b8)
    jmp 0x400ab158
1:
    adda.l #0x4012142c,%a0
    jmp 0x400ab0ea
    .size chord_audio_ratios,.-chord_audio_ratios

/* Entrée stock détournée à 0x400aae88 par jmp chord_audio_update ; nop.
 * Rejoue les huit octets du prologue avant la suite originale à 0x400aae90.
 * ABI C identique : arguments et retour restent sur la pile du wrapper.
 */
    .align 2
    .global chord_audio_original
    .type chord_audio_original,@function
chord_audio_original:
    lea %sp@(-28),%sp
    movem.l %d2-%d5/%a2-%a4,%sp@
    jmp 0x400aae90
    .size chord_audio_original,.-chord_audio_original
