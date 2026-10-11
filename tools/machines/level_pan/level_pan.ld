/* Volume et pan en chiffres (notes/44), dans deux masques de sprites 47x47 libérés (notes/14 §5, tools/sprites.py) :
 *   - 0x4018f4b4 (376 o) : le tick, l'encodeur, le dessin et le pan ;
 *   - 0x4018fc74 (376 o) : la piste sélectionnée, les instructions déplacées, le volume, les chiffres, la police
 *     et l'état.
 * L'état (.data) est écrit à zéro dans l'image : ces zones ne sont pas remises à zéro au démarrage. */
SECTIONS
{
  .cave_a 0x4018f4b4 : {
    *(.text.lp_a)
  }
  .cave_b 0x4018fc74 : {
    *(.text.lp_b) . = ALIGN(4); *(.data.lp)
  }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
