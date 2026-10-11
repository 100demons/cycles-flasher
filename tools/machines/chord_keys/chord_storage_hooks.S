/* Stockage du clavier d'accords, OS 1.13, notes/42.
 * Les stubs ne modifient que les octets réservés via le noyau C.
 * Chargement : a2=en-tête destination, a3=source ; replay exact de 8 octets.
 * Initialisation : a0=en-tête, d0=0 ; replay exact de 8 octets, dont un pea.
 * Registres volatils préservés ; d2-d7/a2-a6 préservés par l'ABI du code C.
 */
    .section .text.ck_storage_irq_save,"ax"
    .balign 2
    .global ck_storage_irq_save
ck_storage_irq_save:
    moveq #0,%d0
    move.w %sr,%d0
    move.w #0x2700,%sr
    rts

    .section .text.ck_storage_irq_restore,"ax"
    .balign 2
    .global ck_storage_irq_restore
ck_storage_irq_restore:
    move.l %sp@(4),%d0
    move.w %d0,%sr
    rts

    .section .text.ck_storage_load_hook,"ax"
    .balign 2
    .global ck_storage_load_hook
ck_storage_load_hook:
    lea %sp@(-16),%sp
    movem.l %d0-%d1/%a0-%a1,%sp@
    move.l %a3,%sp@-
    move.l %a2,%sp@-
    jsr ck_storage_load
    addq.l #8,%sp
    movem.l %sp@,%d0-%d1/%a0-%a1
    lea %sp@(16),%sp
    moveq #1,%d0
    move.b %a3@(28),%a2@(28)
    jmp 0x4005b4b0

    .section .text.ck_storage_init_hook,"ax"
    .balign 2
    .global ck_storage_init_hook
ck_storage_init_hook:
    lea %sp@(-16),%sp
    movem.l %d0-%d1/%a0-%a1,%sp@
    move.l %a0,%sp@-
    jsr ck_storage_reset
    addq.l #4,%sp
    movem.l %sp@,%d0-%d1/%a0-%a1
    lea %sp@(16),%sp
    move.b %d0,%a0@(27)
    pea 16
    jmp 0x4006156c
