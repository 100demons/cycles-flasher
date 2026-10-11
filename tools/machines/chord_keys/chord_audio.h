#ifndef CHORD_AUDIO_H
#define CHORD_AUDIO_H

/* Contrat partagé avec chord_audio_hooks.S : offsets depuis params[0]. */
#define CK_AUDIO_RATIOS_OFFSET 68
#define CK_AUDIO_ACTIVE_OFFSET 84
#define CK_AUDIO_COUNT_OFFSET 88

#ifndef __ASSEMBLER__
/* Lecture atomique du réglage déjà synchronisé avec le pattern courant.
 * 31 : actif ; 30..28 : mode ; 27..21 : tonique ; 20..0 : 7 extensions.
 * L'implémentation de stockage ne doit ni bloquer ni allouer dans cet appel.
 */
unsigned int ck_audio_config(unsigned int track);

/* ABI identique à l'update CHORD stock, appelé par sa table de dispatch. */
void chord_audio_update(int pitch_q16, void *voice, const unsigned short *params);
#endif

#endif
