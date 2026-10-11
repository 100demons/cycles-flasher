// Reference de tools/emu/test_macro.py : la voix de Braids (pichenettes/eurorack, code MIT d'Emilie Gillet),
// compilee pour l'ordinateur depuis les memes sources que la machine MACRO, pilotee bloc par bloc comme la
// passerelle tools/machines/macro/macro.cc la pilote sur le Cycles.
//
// Entree (texte) : une ligne par bloc de 32 trames du Cycles ou macro_update a ete appelee :
//   rendu (0/1) modele hauteur (1/128 demi-ton) timbre color frappe (0/1) mode k taille
// Sortie (binaire, petit-boutiste), par bloc rendu :
//   - mode 0 (96 kHz) : 64 int16. Braids rend par blocs de 24, comme sur le module ; ce qui depasse les 64
//     echantillons d'un bloc attend le suivant (comme la passerelle) ;
//   - mode 1 (48 kHz ou moins, notes/55) : les k echantillons suivants, rendus par blocs de « taille » quand le
//     precedent est epuise.
// Quand le mode change d'un bloc rendu a l'autre, ce qui attendait est jete (comme la passerelle).
#include <cstdio>
#include <cstdint>
#include <cstring>

#include "braids/macro_oscillator.h"

static braids::MacroOscillator osc;                  // a zero, comme le BSS de la charge utile
static const uint8_t no_sync[24] = { 0 };

int main()
{
	int render, shape, pitch, timbre, color, strike, mode, k, size, last = -1, fill = 0, rd = 0, avail = 0;
	int16_t x[64 + 16], y[24];

	osc.Init();
	while (scanf("%d %d %d %d %d %d %d %d %d", &render, &shape, &pitch, &timbre, &color, &strike, &mode, &k,
		     &size) == 9) {
		osc.set_shape(static_cast<braids::MacroOscillatorShape>(shape));
		osc.set_pitch(pitch);
		osc.set_parameters(timbre, color);
		if (strike)
			osc.Strike();
		if (!render)
			continue;
		if (mode != last) {
			fill = rd = avail = 0;
			last = mode;
		}
		if (mode == 0) {
			while (fill < 64) {
				osc.Render(no_sync, x + fill, 24);
				fill += 24;
			}
			fwrite(x, sizeof(x[0]), 64, stdout);
			fill -= 64;
			memmove(x, x + 64, fill * sizeof(x[0]));
			continue;
		}
		while (k--) {
			if (rd == avail) {
				osc.Render(no_sync, y, size);
				rd = 0;
				avail = size;
			}
			fwrite(y + rd++, sizeof(y[0]), 1, stdout);
		}
	}
	return 0;
}
