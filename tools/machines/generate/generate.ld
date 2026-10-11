/* Générateur de trigs « Generate » (SETTINGS + TRACK), dans sept masques de sprites 48x22 libérés (192 o chacun,
 * tools/sprites.py), tous à moins de 32 Ko les uns des autres (branchements et adresses relatifs au PC) :
 *   - 0x4018b9c8 : l'accord (gen_key) et l'état (réglages, xorshift, descripteur du menu) ;
 *   - 0x4018bb48 : l'ouverture du menu (gen_open, gen_build), l'appui d'une ligne (gen_press), gen_put ;
 *   - 0x4018cbc8 : les fermetures libellé / valeur / rotation, les gammes et les textes ;
 *   - 0x4018d038 : le début de la génération (gen_go) ;
 *   - 0x4018d798 : la boucle des pas et le message (gen_step) ;
 *   - 0x4018f80c : bornes et noms des valeurs ;
 *   - 0x40190184 : la table des notes (gen_notes), le tirage (gen_rndn), les libellés.
 * Les données sont dans l'image : leurs valeurs sont celles de l'image à chaque démarrage. */
SECTIONS
{
  .cave1 0x4018b9c8 : { *(.text.gen_key) *(.data.gen_ram) }
  .cave2 0x4018bb48 : { *(.text.gen_open) *(.text.gen_press) *(.text.gen_put) }
  .cave3 0x4018cbc8 : { *(.text.gen_ui) *(.rodata.gen_str) }
  .cave4 0x4018d038 : { *(.text.gen_go) }
  .cave5 0x4018d798 : { *(.text.gen_loop) }
  .cave6 0x4018f80c : { *(.rodata.gen_tab) }
  .cave7 0x40190184 : { *(.text.gen_notes) *(.text.gen_rndn) *(.rodata.gen_lab) }
  /DISCARD/ : { *(.text) *(.data) *(.bss) *(.comment) *(.note*) *(.eh_frame*) }
}
