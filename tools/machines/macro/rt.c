/*
 * Routines de la bibliotheque C appelees par le code de Braids compile pour la machine MACRO (notes/43) :
 * l'edition de liens se fait sans bibliotheque (-nostdlib). Compile avec -fno-builtin et
 * -fno-tree-loop-distribute-patterns, sinon GCC ferait de ces boucles des appels a elles-memes.
 */
typedef unsigned long size_t;

/* par mots de 32 bits, 4 par tour : au changement de modele, dans l'interruption audio, Braids efface l'etat de sa
 * voix numerique (194 o) et, pour BOWED, BLOWN et FLUTED, leurs lignes a retard (4 a 5 Ko : ~2 000
 * instructions ainsi, ~25 000 octet par octet) */
void *memset(void *d, int c, size_t n)
{
	unsigned char *a = d;
	unsigned int w = (unsigned char)c * 0x01010101u, *l;

	while (n && ((unsigned long)a & 3)) {
		*a++ = (unsigned char)c;
		n--;
	}
	for (l = (unsigned int *)a; n >= 16; n -= 16) {
		l[0] = w;
		l[1] = w;
		l[2] = w;
		l[3] = w;
		l += 4;
	}
	for (a = (unsigned char *)l; n; n--)
		*a++ = (unsigned char)c;
	return d;
}

void *memcpy(void *d, const void *s, size_t n)
{
	unsigned char *a = d;
	const unsigned char *b = s;

	while (n--)
		*a++ = *b++;
	return d;
}

void *memmove(void *d, const void *s, size_t n)
{
	unsigned char *a = d;
	const unsigned char *b = s;

	if (a < b) {
		while (n--)
			*a++ = *b++;
	} else {
		a += n;
		b += n;
		while (n--)
			*--a = *--b;
	}
	return d;
}
