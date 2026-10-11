// Reference de tools/emu/test_macro.py : la voix de Braids (pichenettes/eurorack, code MIT d'Emilie Gillet),
// compilee pour l'ordinateur depuis les memes sources que la machine MACRO, pilotee bloc par bloc comme la
// passerelle tools/machines/macro/macro.cc la pilote sur le Cycles.
//
// Entree (texte) : une ligne par bloc de 32 trames du Cycles ou macro_update a ete appelee :
//   rendu (0/1) modele hauteur (1/128 demi-ton) timbre color frappe (0/1)
// Sortie (binaire, petit-boutiste) : 64 int16 (96 kHz) par bloc rendu. Braids rend par blocs de 24, comme sur le
// module ; ce qui depasse les 64 echantillons d'un bloc attend le suivant (comme la passerelle).
#include <cstdio>
#include <cstdint>
#include <cstring>

#include "braids/macro_oscillator.h"

static braids::MacroOscillator osc;                  // a zero, comme le BSS de la charge utile
static const uint8_t no_sync[24] = { 0 };

int main()
{
	int render, shape, pitch, timbre, color, strike, fill = 0;
	int16_t x[64 + 16];

	osc.Init();
	while (scanf("%d %d %d %d %d %d", &render, &shape, &pitch, &timbre, &color, &strike) == 6) {
		osc.set_shape(static_cast<braids::MacroOscillatorShape>(shape));
		osc.set_pitch(pitch);
		osc.set_parameters(timbre, color);
		if (strike)
			osc.Strike();
		if (!render)
			continue;
		while (fill < 64) {
			osc.Render(no_sync, x + fill, 24);
			fill += 24;
		}
		fwrite(x, sizeof(x[0]), 64, stdout);
		fill -= 64;
		memmove(x, x + 64, fill * sizeof(x[0]));
	}
	return 0;
}
