/* Noyau harmonique de chord-keys. Ce fichier ne contient ni hook,
 * ni octet du firmware, ni conversion vers les paramètres SHAPE/COLOR.
 * Il calcule uniquement un voicing diatonique de trois ou quatre notes.
 */
#include "chord_keys.h"

static const unsigned char scales[CHORD_KEYS_MODE_COUNT][7] = {
    {0, 2, 4, 5, 7, 9, 11},  /* Ionien. */
    {0, 2, 3, 5, 7, 9, 10},  /* Dorien. */
    {0, 1, 3, 5, 7, 8, 10},  /* Phrygien. */
    {0, 2, 4, 6, 7, 9, 11},  /* Lydien. */
    {0, 2, 4, 5, 7, 9, 10},  /* Mixolydien. */
    {0, 2, 3, 5, 7, 8, 10},  /* Éolien. */
    {0, 1, 3, 5, 6, 8, 10}   /* Locrien. */
};

/* Positions diatoniques depuis la fondamentale, indexées à partir de zéro.
 * Les accords étendus omettent la quinte pour rester à quatre voix.
 */
static const unsigned char voicings[CHORD_KEYS_EXTENSION_COUNT][4] = {
    {0, 2, 4, 0},
    {0, 2, 4, 6},
    {0, 2, 6, 8},
    {0, 2, 6, 10},
    {0, 2, 6, 12}
};

enum chord_keys_status chord_keys_build(const struct chord_keys_config *config,
                                       int key,
                                       struct chord_keys_result *result)
{
    int i, slot, degree, extension, count;
    int notes[4];

    if (!config || !result || key < 0 || key > 15)
        return CHORD_KEYS_INVALID_ARGUMENT;
    if (config->root < 0 || config->root > 127 ||
        (unsigned int)config->mode >= CHORD_KEYS_MODE_COUNT)
        return CHORD_KEYS_INVALID_ARGUMENT;
    for (i = 0; i < 7; ++i)
        if ((unsigned int)config->extensions[i] >= CHORD_KEYS_EXTENSION_COUNT)
            return CHORD_KEYS_INVALID_ARGUMENT;

    slot = key;
    degree = slot % 7;
    extension = config->extensions[degree];
    count = extension == CHORD_KEYS_TRIAD ? 3 : 4;
    notes[3] = 0; /* Seule case potentiellement inutilisée, sans appel implicite à memset. */
    for (i = 0; i < count; ++i) {
        int position = slot + voicings[extension][i];
        /* Calcul entier avant validation, sans conversion prématurée en octet. */
        notes[i] = config->root + 12 * (position / 7)
                 + scales[config->mode][position % 7];
        if (notes[i] > 127)
            return CHORD_KEYS_NOTE_RANGE;
    }

    /* Ne publier le résultat qu'après validation de l'accord entier. */
    result->degree = degree;
    result->slot = slot;
    result->octave = slot / 7;
    result->count = count;
    for (i = 0; i < 4; ++i) {
        result->notes[i] = notes[i];
        result->offsets[i] = i < count ? notes[i] - notes[0] : 0;
    }
    return CHORD_KEYS_OK;
}
