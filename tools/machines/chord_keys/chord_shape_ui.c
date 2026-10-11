/* Affichage contextuel de SHAPE dans CHORD Keys, OS 1.13 (notes/42).
 * Les descripteurs et leurs bornes restent stock. L'objet de paramètres
 * identifie sa propre piste : les réglages d'une autre piste ne doivent
 * jamais changer le nom ou la valeur affichés ici.
 */
#include "chord_ui.h"
#include "chord_voicing.h"

typedef unsigned int u32;

static int shape_enabled(void *object, u32 descriptor)
{
    void *root, *bank;
    u32 offset, track;
    if (descriptor != 72u)
        return 0;
    root = ((void *(*)(void))0x400cf866)();
    bank = ((void *(*)(void *))0x4000eb9c)(root);
    /* 0x400097f0 : six objets de huit octets à banque + 504 + 8*piste. */
    offset = (u32)object - (u32)bank;
    if (offset < 504u || offset > 544u || ((offset - 504u) & 7u))
        return 0;
    track = (offset - 504u) >> 3;
    if (((int (*)(void *, u32))0x4001e318)(0, track) != 5)
        return 0;
    return (ck_ui_config_get(track) & 0x80000000u) != 0;
}

static const char *shape_text(int value)
{
    static const char *const labels[] = {
        "BASE", "CLS0", "CLS1", "CLS2", "CLS3", "OPN0", "OPN1", "OPN2", "OPN3"
    };
    /* Même conversion signée 8.8 que le calcul sonore. */
    return labels[ck_voicing_index(value)];
}

const char *ck_shape_name(void *object, u32 descriptor)
{
    if (shape_enabled(object, descriptor))
        return "Chord Voicing";
    return ((const char *(*)(void *, u32))0x4000b22a)(object, descriptor);
}

void ck_shape_format(void *object, u32 descriptor, int value, char *output)
{
    if (shape_enabled(object, descriptor)) {
        ((int (*)(char *, const char *, const char *))0x40000e6e)
            (output, "%s", shape_text(value));
        return;
    }
    ((void (*)(void *, u32, int, char *))0x4000a70e)
        (object, descriptor, value, output);
}

u32 ck_shape_draw(void *object, u32 descriptor, int value, u32 flags,
                  void *canvas, int x, int y)
{
    if (shape_enabled(object, descriptor)) {
        u32 font[2];
        /* Quatre lettres mesurent 31 px ici, contre 67 px dans le repli
         * numérique stock. Le panneau ne fait que 64 px de large ; +6 garde
         * le centre vertical de son ancienne police haute de 22 px.
         */
        ((void (*)(void *, const void *))0x40072260)
            (font, (const void *)0x4014120c);
        ((int (*)(void *, void *, int, int, u32, const char *, const char *))0x40071a04)
            (canvas, font, x, y + 6, 2, "%s", shape_text(value));
        ((void (*)(void *))0x40072080)(font);
        return 1;
    }
    return ((u32 (*)(void *, u32, int, u32, void *, int, int))0x4000a66a)
        (object, descriptor, value, flags, canvas, x, y);
}
