/* Accord diatonique dans le véritable update CHORD de l'OS 1.13 (notes/42).
 * Le réglage SHAPE est remplacé dans une copie locale des paramètres ; l'OS
 * conserve enveloppes, timbre, Pitch/Fine et gains de COLOR. SHAPE choisit
 * la disposition des notes ; les déplacements d'octave de COLOR sont sautés.
 * Aucun état de calcul partagé : chaque appel possède sa propre pile.
 */
#include "chord_audio.h"
#include "chord_voicing.h"

/* Trampoline du prologue stock, évite de repasser par le détournement d'entrée. */
extern void chord_audio_original(int pitch_q16, void *voice, const unsigned short *params);

struct chord_audio_frame {
    unsigned short params[34]; /* 33 mots OS, puis deux octets d'alignement. */
    unsigned int ratios[4];
    unsigned int active;
    unsigned int count;
};

_Static_assert(__builtin_offsetof(struct chord_audio_frame, ratios) == CK_AUDIO_RATIOS_OFFSET,
               "offset des rapports");
_Static_assert(__builtin_offsetof(struct chord_audio_frame, active) == CK_AUDIO_ACTIVE_OFFSET,
               "offset du marqueur");
_Static_assert(__builtin_offsetof(struct chord_audio_frame, count) == CK_AUDIO_COUNT_OFFSET,
               "offset du nombre de voix");
_Static_assert(sizeof(struct chord_audio_frame) == 92, "taille de la copie locale");

/* Mêmes modes et voicings que le noyau portable chord_keys.c, vérifiés par les
 * preuves du noyau et de l'audio ; aucun calcul flottant dans l'interruption.
 */
static const unsigned char scales[7][7] = {
    {0, 2, 4, 5, 7, 9, 11},
    {0, 2, 3, 5, 7, 9, 10},
    {0, 1, 3, 5, 7, 8, 10},
    {0, 2, 4, 6, 7, 9, 11},
    {0, 2, 4, 5, 7, 9, 10},
    {0, 2, 3, 5, 7, 8, 10},
    {0, 1, 3, 5, 6, 8, 10}
};
static const unsigned char positions[5][4] = {
    {0, 2, 4, 0}, {0, 2, 4, 6}, {0, 2, 6, 8},
    {0, 2, 6, 10}, {0, 2, 6, 12}
};

/* round(2**(n / 12) * 2**26), n = 0..23. Calcul indépendant du firmware. */
static const unsigned int semitone_ratios[24] = {
    67108864u, 71099365u, 75327153u, 79806339u,
    84551870u, 89579586u, 94906266u, 100549686u,
    106528681u, 112863206u, 119574402u, 126684666u,
    134217728u, 142198729u, 150654306u, 159612677u,
    169103741u, 179159172u, 189812531u, 201099372u,
    213057363u, 225726413u, 239148804u, 253369332u
};

/* Fonction séparée pour tenir dans les masques libérés de 376 octets. */
static void __attribute__((noinline))
chord_audio_prepare(struct chord_audio_frame *frame, unsigned int cfg, unsigned int note)
{
    unsigned int i, mode = (cfg >> 28) & 7u;
    unsigned int tonic, relative, degree, extension, intervals[4];
    if (!(cfg & 0x80000000u) || mode >= 7)
        return;
    tonic = ((cfg >> 21) & 127u) % 12u;
    relative = ((unsigned int)note + 12u - tonic) % 12u;
    for (degree = 0; degree < 7; ++degree)
        if (scales[mode][degree] == relative)
            break;
    /* Une note extérieure à la gamme reste un accord SHAPE stock. */
    if (degree == 7)
        return;
    extension = (cfg >> (3 * degree)) & 7u;
    if (extension >= 5)
        return;
    frame->count = extension == 0 ? 3 : 4;
    for (i = 0; i < 4; ++i) {
        unsigned int position = degree + positions[extension][i];
        unsigned int interval = 12u * (position / 7u)
                             + scales[mode][position % 7u] - relative;
        intervals[i] = interval;
    }
    ck_voicing_apply(intervals, frame->count,
                     ck_voicing_index((short)frame->params[12]));
    for (i = 0; i < 4; ++i) {
        unsigned int interval = intervals[i];
        /* BASE conserve exactement les rapports arrondis historiques. Les
         * dispositions ouvertes peuvent dépasser 23 demi-tons, au plus 35.
         */
        frame->ratios[i] = interval < 24 ? semitone_ratios[interval]
                                       : semitone_ratios[interval - 12] << 1;
    }
    frame->params[12] = 7u << 8; /* m7 : gain des quatre opérateurs disponible. */
    frame->active = 1;
}

void chord_audio_update(int pitch_q16, void *voice, const unsigned short *params)
{
    struct chord_audio_frame frame;
    unsigned int i, track = 0;
    unsigned int voice_offset = (unsigned int)voice - 0x42308828u;
    int note = pitch_q16 >> 16;

    /* La copie existe AUSSI en mode inactif : le crochet interne peut toujours
     * lire son marqueur, sans dépasser le tableau de paramètres natif.
     */
    for (i = 0; i < 33; ++i)
        frame.params[i] = params[i];
    frame.active = 0;

    /* Six soustractions au plus, sans division ou appel à une bibliothèque. */
    while (voice_offset >= 0x31cu && track < 6) {
        voice_offset -= 0x31cu;
        ++track;
    }
    if (track < 6 && voice_offset == 0 && note >= 0 && note <= 127)
        chord_audio_prepare(&frame, ck_audio_config(track), (unsigned int)note);

    /* Au-delà du seuil aigu, l'OS garde l'ancien incrément de l'opérateur 0,
     * contrairement aux autres voix qu'il rend muettes. Préparer son plafond
     * évite une note périmée avec les inversions ; en plage normale, l'update
     * le réécrit. Conversion stock : ((0x454800 * 0x57619f10) >> 31) >> 2.
     */
    if (frame.active)
        ((unsigned int *)voice)[0x70 / 4] = 0x000bd2f1u;
    chord_audio_original(pitch_q16, voice, frame.params);
    if (frame.active && frame.count == 3)
        ((unsigned int *)voice)[5] = 0; /* Triade : quatrième opérateur inaudible. */
}
