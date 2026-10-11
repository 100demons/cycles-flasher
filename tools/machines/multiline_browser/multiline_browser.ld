/* Navigateur multiligne (notes/40), dans le masque de sprite 47x47 libéré 0x401904b4 (tools/sprites.py) : 376 o. */
SECTIONS
{
  .cave 0x401904b4 : {
    *(.text.multiline_browser) . = ALIGN(2); *(.rodata.multiline_browser)
  }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
