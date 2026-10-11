/* Disposition des mêmes notes, sans changer les extensions I..VII (notes/42).
 * Au plus quatre notes ; aucun flottant, allocation ou état partagé.
 */
#include "chord_voicing.h"

unsigned int ck_voicing_index(int shape_q8)
{
    if (shape_q8 < 0)
        return 0;
    if (shape_q8 >= 32 * 256)
        return 8;
    return (unsigned int)shape_q8 >> 10;
}

static __attribute__((noinline)) void sort_notes(unsigned int *notes, unsigned int count)
{
    unsigned int i, j;
    for (i = 1; i < count; ++i) {
        unsigned int note = notes[i];
        for (j = i; j && notes[j - 1] > note; --j)
            notes[j] = notes[j - 1];
        notes[j] = note;
    }
}

void ck_voicing_apply(unsigned int notes[4], unsigned int count, unsigned int index)
{
    unsigned int i, rotations;
    if (!index)
        return;
    for (i = 0; i < count; ++i)
        notes[i] %= 12u;
    sort_notes(notes, count);
    rotations = (index - 1) & 3u;
    while (rotations--) {
        notes[0] += 12;
        sort_notes(notes, count);
    }
    if (index >= 5) {
        for (i = 1; i < count; i += 2)
            notes[i] += 12;
        sort_notes(notes, count);
    }
}
