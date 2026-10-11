/* Trigless trigs atténués (notes/45), dans deux masques de sprites 47x47 libérés (notes/14 §5, tools/sprites.py) :
 *   - 0x4018dba8 (376 o) : le clignotement et le relevé des LED (tâche de l'interface) ;
 *   - 0x40192734 (376 o) : le découpage de la lumière dans l'interruption du panneau, et l'état.
 * L'état (.data) est écrit dans l'image avec ses valeurs de départ : ces zones ne sont pas remises à zéro au
 * démarrage. */
SECTIONS
{
  .cave_a 0x4018dba8 : {
    *(.text.td_a)
  }
  .cave_b 0x40192734 : {
    *(.text.td_b) . = ALIGN(4); *(.data.td)
  }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
