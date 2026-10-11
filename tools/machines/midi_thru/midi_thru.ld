/* THRU commutable (notes/53) : dans un masque de sprite libéré (tools/sprites.py) ; CAVE est passé par
 * tools/gen_midi_thru.py (ld --defsym), pour pouvoir aussi lier le code à l'adresse du build testé par son auteur. */
SECTIONS
{
  .cave CAVE : {
    *(.text.midi_thru)
  }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
