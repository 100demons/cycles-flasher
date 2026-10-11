/* Écoute des samples (notes/46), dans quatre masques de sprites 47x47 libérés (376 o chacun, tools/sprites.py) :
 *   - 0x40183118 : la copie audio (pv_copy), la table des copies et les copies des pistes 1 et 2 ;
 *   - 0x40185018 : les copies des pistes 3 à 5 ;
 *   - 0x40185968 : la note jouée (pv_note) et la copie de la piste 6 ;
 *   - 0x40185c58 : le navigateur (pv_parse) et le son écouté qu'il construit.
 * Ces quatre masques servent aussi à chord-keys, qui exclut Model-TG : les deux tweaks ne vont jamais ensemble.
 * Les données sont écrites dans l'image : ces zones ne sont pas remises à zéro au démarrage. */
SECTIONS
{
  .cave1 0x40183118 : { *(.text.pv_copy) . = ALIGN(4); *(.data.pv_tab) *(.data.pv_b01) }
  .cave2 0x40185018 : { *(.data.pv_b234) }
  .cave3 0x40185968 : { *(.text.pv_note) . = ALIGN(4); *(.data.pv_b5) }
  .cave4 0x40185c58 : { *(.text.pv_parse) . = ALIGN(4); *(.data.pv_src) }
  /DISCARD/ : { *(.text) *(.data) *(.bss) *(.comment) *(.note*) *(.eh_frame*) }
}
