/* Filtre par piste (notes/47), dans quinze masques de sprites 35x35 libérés (tools/sprites.py, gardé : 0x4014a660).
 * Chaque masque fait 280 o et n'est pas contigu au suivant (l'image du sprite est entre les deux) : une section par
 * masque, appels absolus de l'une à l'autre. L'état (.data) est écrit dans l'image avec ses valeurs de départ : ces
 * zones ne sont pas remises à zéro au démarrage. tools/gen_track_filter.py vérifie que chaque section tient. */
SECTIONS
{
  .tf_post  0x4014ab5c : { *(.text.post) }
  .tf_track 0x4014b85c : { *(.text.track) }
  .tf_kern  0x4014d74c : { *(.text.kern) }
  .tf_coef1 0x401542f8 : { *(.text.coef1) }
  .tf_coef2 0x401548b4 : { *(.text.coef2) }
  .tf_gtab  0x4015b8f8 : { *(.rodata.gtab) }
  .tf_ntab  0x4015f50c : { *(.rodata.ntab) }
  .tf_ktab  0x401601fc : { *(.rodata.ktab) }
  .tf_dtab  0x40160864 : { *(.rodata.dtab) }
  .tf_kst   0x40160b6c : { *(.data.kst) }
  .tf_cst   0x40160e6c : { *(.data.cst) . = ALIGN(4); *(.rodata.ptab) }
  .tf_knob  0x401625bc : { *(.text.knob) }
  .tf_fmt   0x40163fb8 : { *(.text.fmt) }
  .tf_save  0x4016616c : { *(.text.save) }
  .tf_load  0x40166760 : { *(.text.load) }
  .text 0x40167c50 : { *(.text) *(.data) *(.bss) *(COMMON) }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
