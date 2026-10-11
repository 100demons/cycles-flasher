#ifndef CHORD_UI_H
#define CHORD_UI_H

/* Interface du mode accords (notes/42). Ces deux adaptateurs appartiennent au
 * stockage : get rend un mot valide, ou OFF / do3 / majeur / triades par défaut ;
 * set sauvegarde, signale le changement et publie le mot pour le moteur audio.
 * Mot : actif31, mode28..30, tonique21..27, extensions I..VII sur trois bits.
 */
unsigned ck_ui_config_get(unsigned track);
void ck_ui_config_set(unsigned track, unsigned word);

/* Pointeur de KeyboardView 0x400ff9cc, repli vers 0x4001a0d2.
 * KeyEvent : code +12 (16..31), indicateurs +16. PadsView reste stock.
 */
unsigned ck_ui_key(void *view, unsigned char *event);

/* Appel du constructeur en 0x4001cb3e : constructeur stock puis lignes ajoutées. */
void ck_ui_menu_ctor(void *view);

/* Libère les notes encore actives ; conserve les identités physiques jusqu'au
 * relâchement, pour que celui-ci ne soit pas réinterprété par le mode stock.
 */
void ck_ui_cancel_track(unsigned track);

#endif
