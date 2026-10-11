#ifndef CHORD_VOICING_H
#define CHORD_VOICING_H

/* SHAPE signé 8.8 : BASE, CLS0..3, OPN0..3. Aucun état persistant ajouté. */
unsigned int ck_voicing_index(int shape_q8);
void ck_voicing_apply(unsigned int notes[4], unsigned int count, unsigned int index);

#endif
