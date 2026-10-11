#ifndef CHORD_KEYS_H
#define CHORD_KEYS_H

/* Noyau harmonique autonome du clavier CHORD (notes/42).
 * Calcule les notes des seize touches TRIG, sans accès au firmware ni au DSP.
 * Aucun état de piste, stockage ou envoi MIDI n'est modifié ici.
 */

enum chord_keys_mode {
    CHORD_KEYS_IONIAN,
    CHORD_KEYS_DORIAN,
    CHORD_KEYS_PHRYGIAN,
    CHORD_KEYS_LYDIAN,
    CHORD_KEYS_MIXOLYDIAN,
    CHORD_KEYS_AEOLIAN,
    CHORD_KEYS_LOCRIAN,
    CHORD_KEYS_MODE_COUNT
};

enum chord_keys_extension {
    CHORD_KEYS_TRIAD,       /* 1, 3, 5 */
    CHORD_KEYS_SEVENTH,     /* 1, 3, 5, 7 */
    CHORD_KEYS_NINTH,       /* 1, 3, 7, 9 */
    CHORD_KEYS_ELEVENTH,    /* 1, 3, 7, 11 */
    CHORD_KEYS_THIRTEENTH,  /* 1, 3, 7, 13 */
    CHORD_KEYS_EXTENSION_COUNT
};

enum chord_keys_status {
    CHORD_KEYS_OK = 0,
    CHORD_KEYS_INVALID_ARGUMENT,
    CHORD_KEYS_NOTE_RANGE
};

struct chord_keys_config {
    int root; /* Tonique MIDI 0..127 ; tessiture réellement jouable de CHORD à établir. */
    enum chord_keys_mode mode;
    enum chord_keys_extension extensions[7]; /* Un réglage par degré I..VII. */
};

struct chord_keys_result {
    int degree;     /* 0..6 : degré I..VII, réutilisé à l'octave supérieure. */
    int slot;       /* 0..15 : touche TRIG 1..16. */
    int octave;     /* 0..2 : octave de la fondamentale par rapport à root. */
    int count;      /* 3 ou 4 ; les cases inutilisées valent zéro. */
    int notes[4];   /* Notes MIDI absolues, strictement croissantes. */
    int offsets[4]; /* Demi-tons au-dessus de notes[0]. */
};

/* key = 0..15 (TRIG 1..16) : I..VII, I..VII +12, puis I..II +24.
 * Chaque voix appartient à la gamme, y compris les extensions.
 * Tous les réglages sont validés. Un accord dépassant la note MIDI 127 est
 * refusé en entier, sans rabattement ni écrêtage. En cas d'erreur, result reste
 * intact. config et result doivent désigner des objets distincts et valides.
 * Aucun état global mutable, allocation, appel système ou dépendance à la libc.
 */
enum chord_keys_status chord_keys_build(const struct chord_keys_config *config,
                                       int key,
                                       struct chord_keys_result *result);

#endif
