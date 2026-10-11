# 55 — MACRO plus légère, et le lo-fi RATE / BITS sur FUNC + PITCH

Suite de la machine MACRO ([43](43-machine-macro.md)), le 10/10/2026, dans le fil « Intégration de Plaits » : Maxime a
relayé des conseils lus ailleurs (calculer Braids à 48 kHz plutôt qu'à 96 kHz, EMAC, retirer des modèles lourds, SRAM
interne). Proposé en retour : calculer à 48 kHz les modèles où cela ne change pas le son, et un réglage RATE/BITS qui
calcule *vraiment* moins d'échantillons, comme le RATE de Braids mais en allégeant la charge. Maxime : « go », puis
« En faisant function + pitch si c possible ». Mêmes tweaks que MACRO (`25-macro.json`, `32-macro-tg.json`, et les
62 `syntakt-…-macro` de [50](50-macro-avec-moteurs-syntakt.md)), générateurs `tools/gen_macro.py` et
`tools/gen_macro_syntakt.py`, passerelle `tools/machines/macro/macro.cc`, preuve `tools/emu/test_macro.py` (référence
`tools/emu/braids_ref.cc`). Adresses : VA de l'OS 1.13.

## Réponse courte

- **13 modèles calculés à 48 kHz** (CSAW, SAW SQUARE, SQUARE SUB, SAW SUB, les quatre TRIPLE sauf RING MOD, WAVETABLES,
  WAVE MAP, WAVE LINE, WAVE PARAPHONIC, DIGITAL MODULATION) : Braids les rend une octave plus haut, à 48 kHz, sans le
  filtre demi-bande. Même spectre qu'avant à environ 1 dB près par tiers d'octave (§2), pour **52 à 58 % du calcul
  d'avant** : WAVE MAP, le plus lourd, passe de 3,5 à 1,8 fois une voix TONE (§6). Ce sont justement les plus lourds
  (cartes d'ondes, TRIPLE SQUARE). Les 34 autres modèles restent à 96 kHz, échantillon pour échantillon comme avant.
- **FUNC + PITCH (FINE) devient le lo-fi des pistes MACRO** `[HYP]` (que ce geste règle FINE vient de la table des
  paramètres, [14 §1](14-machine-sd-vintage.md), pas lu dans le code de l'interface ; à confirmer sur la machine) :
  - au centre (64, la valeur par défaut) : rien ne change, les projets existants sonnent comme avant ;
  - à gauche, **RATE** : 64 pas de 48 kHz × 2^(−86/1536) chacun, de 46 kHz à 4 kHz. Les 13 modèles allégés sont alors
    vraiment rendus à cette fréquence (encore moins de calcul : 32 % d'avant vers 24 kHz, 17 % vers 7,5 kHz pour WAVE
    MAP) ; les autres sont échantillonnés-bloqués comme sur le module (leur calcul ne change pas) ;
  - à droite, **BITS** : de 12 bits à 2 bits, arrondis au plus près.
- En échange, **FINE n'accorde plus MACRO**. Un projet dont une piste MACRO a FINE ≠ 64 sonne maintenant lo-fi au lieu
  d'être désaccordé (MACRO existe depuis la version 1.31).
- **Testé sur la machine (11/10/2026)** : « ça marche nickel sur machine » (Maxime, §7). La carte MACRO et Model-TG +
  les 5 moteurs + MACRO repassent en « Testé » (expérimentales entre-temps : le test du 10/10/2026 portait sur la
  version d'avant).

## 1. Pourquoi 96 kHz, et ce que change 48 kHz `[FAIT]`

Braids est écrit pour son module, qui sort à 96 kHz : ses tables de hauteur (`lut_oscillator_increments`), ses filtres,
ses formants et ses modèles physiques comptent en échantillons à 96 kHz. MACRO le rend donc à 96 kHz, puis un filtre
demi-bande ramène à 48 kHz ([43 §3](43-machine-macro.md)). Rendre à 48 kHz en montant la note d'une octave donne la
même fréquence pour tout ce qui suit la note :

- `ComputePhaseIncrement` (`analog_oscillator.cc`, `digital_oscillator.cc`) lit la table à `(note − 16384) mod 1536` et
  décale de `⌈(16384 − note) / 1536⌉` : à note + 1536 (+12 demi-tons, la hauteur de Braids est en 1/128 de demi-ton),
  même case, un décalage de moins, donc exactement le double de l'incrément (au bit de poids faible près) ;
- Braids avance ses lissages, enveloppes et décroissances d'un pas par appel de `Render` : les rendus restent 4 000 par
  seconde, par blocs de 12 échantillons au lieu de 24 ;
- ce qui ne suit pas la note change : la coupure des filtres (DIGITAL FILTER), les formants (VOSIM, VOWEL), les
  pertes des modèles physiques, les percussions, les bruits filtrés ; et ce qui dépasse 24 kHz se replie au lieu
  d'être filtré (FM, BUZZ, SYNC). HARMONICS se tait (ses partiels au-dessus de la moitié de la fréquence d'échantillonnage
  sont coupés).

Plutôt que de trier à la lecture du code, chaque modèle a été mesuré (§2).

Le plafond : les oscillateurs de Braids bornent la note à 16 383 (note 128). À 48 kHz, la note + 1536 doit tenir
dessous, plus ce que le modèle y ajoute : jusqu'à +24 demi-tons pour les voix désaccordées des TRIPLE (table
`intervals`, `macro_oscillator.cc`), jusqu'à 19 demi-tons + 5 pour les accords de WAVE PARAPHONIC (table `chords`,
`digital_oscillator.cc`), rien pour les autres (SQUARE SUB et SAW SUB ajoutent une sous-octave, DIGITAL MODULATION
compte sa cadence de symboles en dessous de la note). Au-delà, le modèle reste à 96 kHz : à partir de la note 92
(1,66 kHz) pour les TRIPLE, de la note 97 pour WAVE PARAPHONIC, de la note 116 (6,6 kHz) pour les autres.

## 2. Mesure, modèle par modèle `[FAIT sur ordinateur]`

Braids compilé pour l'ordinateur, chaque modèle rendu des deux façons (96 kHz + filtre demi-bande, et 48 kHz une
octave plus haut, blocs de 12) : notes 24, 43, 60, 77 et 96, cinq réglages TIMBRE/COLOR (0/0, 16 384/16 384,
4 000/28 000, 28 000/4 000, 32 767/32 767), 1,6 s chacun, frappé toutes les 0,8 s. Écart par bandes d'un tiers
d'octave de 50 Hz à 16 kHz, sur des fenêtres de 85 ms, pour les bandes à moins de 30 dB du maximum (médiane et 95 %
des fenêtres) ; écart de niveau global (le pire réglage).

| Modèle | bandes, médiane (dB) | bandes, 95 % (dB) | niveau (dB) | Rendu |
|---|---|---|---|---|
| 0 CSAW | 1,1 | 2,9 | 1,4 | **48 kHz** |
| 1 MORPH | 1,4 | 3,9 | 2,5 | 96 kHz |
| 2 SAW SQUARE | 1,0 | 1,5 | 0,4 | **48 kHz** |
| 3 SINE TRIANGLE | 0,1 | 12,1 | 1,9 | 96 kHz |
| 4 BUZZ | 0,1 | 46,4 | 5,6 | 96 kHz |
| 5 SQUARE SUB | 1,0 | 1,9 | 0,2 | **48 kHz** |
| 6 SAW SUB | 1,0 | 2,2 | 0,2 | **48 kHz** |
| 7 SQUARE SYNC | 1,1 | 19,1 | 0,9 | 96 kHz |
| 8 SAW SYNC | 1,1 | 7,7 | 0,9 | 96 kHz |
| 9 TRIPLE SAW | 0,9 | 1,5 | 1,1 | **48 kHz** |
| 10 TRIPLE SQUARE | 1,0 | 2,7 | 0,2 | **48 kHz** |
| 11 TRIPLE TRIANGLE | 0,1 | 2,4 | 0,1 | **48 kHz** |
| 12 TRIPLE SINE | 0,0 | 1,2 | 0,0 | **48 kHz** |
| 13 TRIPLE RING MOD | 0,0 | 25,3 | 1,5 | 96 kHz |
| 14 SAW SWARM | 1,6 | 11,7 | 16,0 | 96 kHz |
| 15 SAW COMB | 3,1 | 10,6 | 5,8 | 96 kHz |
| 16 TOY | 3,6 | 9,5 | 0,1 | 96 kHz |
| 17 DIGITAL FILTER LP | 0,6 | 37,2 | 0,7 | 96 kHz |
| 18 DIGITAL FILTER PK | 3,0 | 35,5 | 0,6 | 96 kHz |
| 19 DIGITAL FILTER BP | 1,7 | 72,9 | 0,5 | 96 kHz |
| 20 DIGITAL FILTER HP | 2,5 | 73,8 | 0,9 | 96 kHz |
| 21 VOSIM | 13,7 | 24,2 | 1,6 | 96 kHz |
| 22 VOWEL | 9,3 | 13,8 | 7,8 | 96 kHz |
| 23 VOWEL FOF | 11,9 | 14,5 | 8,4 | 96 kHz |
| 24 HARMONICS | 0,1 | 128,3 | 264,5 | 96 kHz |
| 25 FM | 0,0 | 20,8 | 4,9 | 96 kHz |
| 26 FEEDBACK FM | 3,7 | 36,9 | 1,8 | 96 kHz |
| 27 CHAOTIC FEEDBACK FM | 0,0 | 12,4 | 0,3 | 96 kHz |
| 28 PLUCKED | 9,0 | 75,7 | 4,7 | 96 kHz |
| 29 BOWED | 11,1 | 144,9 | 39,0 | 96 kHz |
| 30 BLOWN | 5,1 | 11,1 | 9,4 | 96 kHz |
| 31 FLUTED | 6,2 | 24,2 | 5,4 | 96 kHz |
| 32 STRUCK BELL | 0,1 | 24,8 | 0,2 | 96 kHz |
| 33 STRUCK DRUM | 0,5 | 18,3 | 0,5 | 96 kHz |
| 34 KICK | 6,8 | 98,5 | 11,0 | 96 kHz |
| 35 CYMBAL | 6,9 | 10,5 | 6,0 | 96 kHz |
| 36 SNARE | 11,3 | 84,4 | 6,3 | 96 kHz |
| 37 WAVETABLES | 0,0 | 2,2 | 0,6 | **48 kHz** |
| 38 WAVE MAP | 0,0 | 1,5 | 0,7 | **48 kHz** |
| 39 WAVE LINE | 0,5 | 2,3 | 0,2 | **48 kHz** |
| 40 WAVE PARAPHONIC | 0,0 | 3,0 | 0,8 | **48 kHz** |
| 41 FILTERED NOISE | 3,9 | 6,2 | 4,9 | 96 kHz |
| 42 TWIN PEAKS NOISE | 8,5 | 15,5 | 5,4 | 96 kHz |
| 43 CLOCKED NOISE | 1,8 | 37,5 | 0,4 | 96 kHz |
| 44 GRANULAR CLOUD | 12,3 | 20,0 | 1,7 | 96 kHz |
| 45 PARTICLE NOISE | 9,4 | 116,7 | 9,8 | 96 kHz |
| 46 DIGITAL MODULATION | 0,0 | 0,5 | 0,0 | **48 kHz** |

Retenus : médiane ≤ 1,1 dB, 95 % ≤ 3 dB, niveau ≤ 1,4 dB. L'écart restant est le repliement des harmoniques les plus
hautes et la phase des battements lents. L'enveloppe (niveau par fenêtres de 10 ms, 95 %) suit aussi, à 2,6 dB près,
sauf deux réglages extrêmes qui ne changent pas le son : SQUARE SUB à TIMBRE au maximum et note 36 (l'impulsion
s'amincit jusqu'à disparaître, au même rythme lent mais pas au même instant, 6,9 dB) et TRIPLE SINE à TIMBRE 0 et note
36 (trois sinus à la même note, battement lent dont la phase diffère, 4,2 dB). Écartés de justesse : MORPH (niveau
2,5 dB), SAW SYNC (repliement de la synchro, 7,7 dB à 95 %), STRUCK BELL et STRUCK DRUM (partiels aigus, 25 et 18 dB à
95 %).

Les mêmes chiffres se refont avec `test_macro.py --spectres` (notes 36, 60 et 84, trois réglages : plus court) ; la
preuve vérifie les 13 modèles retenus à chaque passage (§5).

## 3. Conception

### 3.1 Rendu à 48 kHz

- Table `LITE` (47 entrées) : ce que le modèle ajoute au-dessus de sa note (0, 3 072 pour les TRIPLE, 2 437 pour WAVE
  PARAPHONIC), −1 pour les modèles à 96 kHz.
- `macro_update` choisit le rendu à chaque bloc (le modèle et la note peuvent changer à chaque bloc) : 48 kHz si
  `note + 1536 + LITE ≤ 16383`, sinon 96 kHz comme avant.
- `macro_render`, à 48 kHz : un rendu de 12 échantillons dans `x[0..12)` quand le précédent est épuisé, puis
  `x << 15` (même échelle que la sortie du filtre : pleine échelle de Braids → ½ en Q31). Trois, trois puis deux rendus
  par bloc de 32 trames : toujours 4 000 par seconde.
- Changement de rendu (modèle allégé ↔ non allégé, note qui passe le plafond) : ce qui attendait est jeté, l'historique
  du filtre remis à zéro. Le changement de modèle est déjà une rupture ; une note qui passe le plafond est rare.

### 3.2 RATE (FINE sous 64)

- `d = 64 − FINE` pas (1 à 64), fréquence `48 kHz × 2^(−86 d / 1536)` : 46 kHz au premier pas, 24 kHz vers FINE 46,
  7,5 kHz vers FINE 16, 4 kHz à FINE 0. Table `RATE_STEP` (Q24, 65 valeurs).
- Modèle allégé : rendu à cette fréquence, note + 1536 + 86 d (fréquence exacte à 0,4 centième de demi-ton près,
  arrondi de la note de Braids). Un accumulateur de phase (Q24) avance de `RATE_STEP[d]` par échantillon de sortie ;
  à chaque débordement, l'échantillon suivant du rendu, tenu jusqu'au suivant. Taille d'un rendu :
  `2 × arrondi(6 × RATE_STEP[d])` (paire, car WAVE PARAPHONIC rend deux échantillons par tour ; environ 4 000 rendus
  par seconde, 2 000 aux plus basses fréquences).
- Si la note est trop haute pour `d` pas sous le plafond, le rendu se fait au plus grand `d' < d` qui tient (à 48 kHz
  au pire), puis un échantillonneur-bloqueur (sa propre phase) ramène à la fréquence de RATE. Au-dessus de la limite
  à 48 kHz, 96 kHz puis l'échantillonneur-bloqueur. Exemple : TRIPLE SAW, note 60, FINE 16 (7,46 kHz) : rendu à
  `d' = 47` (7,7 kHz), puis bloqué à 7,46 kHz.
- Modèles non allégés : 96 kHz et filtre comme avant, puis l'échantillonneur-bloqueur à `RATE_STEP[d]`. C'est le RATE
  du module (qui garde un échantillon sur N du rendu à 96 kHz), en continu au lieu de 7 valeurs.

### 3.3 BITS (FINE au-dessus de 64)

- `bits = 12 − (FINE − 65) × 10 / 62` : 12 bits à FINE 65, 2 bits à FINE 127, environ 6 pas par bit.
- Sur la sortie (Q31, pleine échelle de Braids à 2^30) : `(x + 2^(30 − bits)) & −2^(31 − bits)`, les `bits` bits de
  poids fort de l'échantillon 16 bits de Braids, arrondis au plus près. Le module masque (`sample & mask`), ce qui
  arrondit vers le bas et ajoute un décalage continu d'un demi-pas : au travers du VCA du Cycles, il claquerait à chaque
  note. Pas de débordement : la sortie du filtre reste sous 1,51 × 2^30, plus 2^28 au plus.
- RATE et BITS ne se cumulent pas (un seul réglage).

### 3.4 FINE

- `FINE` (mot 8.8 en `p + 0x22`, 0..127) est arrondi à l'entier ; il ne s'ajoute plus à la note. Un p-lock de FINE
  donne un lo-fi par pas ; avec le mod slide, il glisse.
- `[HYP]` FUNC + PITCH règle FINE (table des paramètres, [14 §1](14-machine-sd-vintage.md)) : à confirmer, avec ce que
  l'écran affiche.

## 4. Place

| | Avant | Maintenant |
|---|---|---|
| Code et tables de Braids et de la passerelle | 98 230 o | 99 408 o |
| Variables (6 voix) | 103 368 o | 103 392 o |
| Ajouté à l'image, `macro` / `macro-tg` | 103 552 o / 103 964 o | 104 728 o / 105 140 o |

Avec les moteurs du Syntakt ([50](50-macro-avec-moteurs-syntakt.md)), le code de MACRO ne tenait plus entre `MACRO_AT`
(`PAY + 0x42000`) et ses variables (`PAY + 0x5a000` : 98 304 o, il en restait 74) : les variables passent à
`PAY + 0x5b000` (102 400 o pour le code). Fin de la charge utile `PAY + 0x743e0` (476 128 o), toujours sous
`PAY_TG + 0x100000` avec Model-TG. Rangée compressée : 230 056 à 241 604 o seuls, 230 323 à 241 869 o avec Model-TG
(avant : 229 134 à 240 674 o, 229 403 à 240 948 o) ; fin de l'image décompressée au plus `0x401e5104` seuls (marge
110 332 o sous `0x40200000`) et `0x401fa98d` avec Model-TG (marge 22 131 o, contre 23 052).

## 5. Preuve en émulation `[FAIT en émulation]`

`tools/emu/test_macro.py`, comme en [43 §7](43-machine-macro.md) : le vrai code de l'OS (Unicorn), avec la charge utile
telle que le crochet la reconstitue. La référence est Braids compilé pour l'ordinateur (`braids_ref.cc`), qui rend
maintenant aussi à la demande (mode 1 : 48 kHz ou moins, par rendus de la taille donnée) ; le test calcule d'après cette
note ce que la passerelle doit demander à chaque bloc (`settings`, `simulate` : rendu à 96 ou à 48 kHz, hauteur, pas
du rendu, phase de l'échantillonneur-bloqueur, BITS), fait rendre la référence de la même façon et compare la sortie
échantillon par échantillon.

| Vérification | Seule (`macro`) | Avec Model-TG (`macro-tg`) |
|---|---|---|
| Son avant la chaîne d'ampli = Braids compilé pour l'ordinateur, rendu comme ci-dessus, échantillon par échantillon | **173 cas** : les 107 d'avant (FINE au centre) ; FINE 0, 21, 48, 63, 65, 90, 127 sur CSAW, TRIPLE SAW, WAVETABLES, WAVE MAP, WAVE PARAPHONIC, DIGITAL MODULATION, FM, PLUCKED ; FINE qui balaie 0 → 127 et 127 → 0 pendant la note ; FINE fractionnaire (37,4 et 64,6) ; plafonds (TRIPLE SAW notes 80, 91,5 et 100 avec FINE 0, CSAW note 120, WAVE PARAPHONIC note 105) ; note qui franchit le plafond ; modèle allégé ↔ non allégé pendant la note | **72 cas** : les 47 modèles, WAVE MAP et FM aux 7 valeurs de FINE, les plafonds, l'allégé ↔ non allégé, la voix qui se tait, le modèle qui change |
| Blocs rendus à 48 kHz ou moins / dont plus lents (RATE) / échantillonnés-bloqués / BITS | 7 369 / 2 582 / 1 548 / 2 674 | 2 857 / 498 / 614 / 528 |
| Voix calculée exactement quand l'OS l'impose ; sinon sortie nulle et aucun appel de Braids | 17 364 blocs, dont 339 muets | 9 146 blocs, dont 339 muets |
| Rendus de Braids : 3, 3 puis 2 de 24 échantillons par bloc à 96 kHz, 12 échantillons à 48 kHz (4 000 rendus par seconde dans les deux cas, comme le module) | ok | ok |
| Modèles allégés : spectre à 48 kHz contre 96 kHz puis filtre demi-bande (tiers d'octave : médiane, 95 %, niveau ; seuils 1,5, 4 et 2 dB) | au pire 1,1 / 2,4 / 0,6 dB (§2) | même code |
| Démarrage, interface, chaîne d'ampli, machines d'origine identiques, machine locks, 6 pistes MACRO, pistes mêlées (comme [43 §7](43-machine-macro.md)) | ok, fin de l'image `0x401c3a58` | ok, fin `0x401d9374` ; sortie de la piste = MACRO seule |
| `--with 6ch-usbup,model-tg-st,sample-preview-st,trig-hold,arp,tempo-max,boot-anim,multiline-browser,level-pan-values,trigless-dim` | — | ok : démarrage, machines d'origine identiques aux mêmes mods sans MACRO, sortie de MACRO identique, machine locks, pistes mêlées |

Résultat : **TOUT OK** (73 vérifications).

Avec les moteurs du Syntakt, `tools/emu/test_macro_syntakt.py` ([50 §6](50-macro-avec-moteurs-syntakt.md)) : les deux
versions (5 moteurs, seuls et avec Model-TG) **TOUT OK** (66 vérifications) ; avec `--with 6ch-usbup,trig-hold,arp,
tempo-max,boot-anim,multiline-browser,level-pan-values,trigless-dim` **TOUT OK** (14) ; la même liste avec
`model-tg-st,sample-preview-st` **TOUT OK** (14). La comparaison de la piste MACRO avec MACRO seule y ajoute 4 réglages
lo-fi (FINE 16 sur WAVE MAP, 40 sur TRIPLE SAW, 30 sur FM, 100 sur CSAW) : la passerelle y est liée à une autre adresse,
avec d'autres relocalisations. Fin de l'image décompressée : `0x401e5104` seuls, `0x401fa98d` avec Model-TG.

Avec le filtre par piste ([47](47-filtre-piste.md), après la fusion de main, 11/10/2026) :
`test_track_filter.py --with macro` **TOUT OK** (62) ; `--with syntakt-sd-cp-toy-bits-swarm-macro,6ch-usbup,chord-keys,
level-pan-values,trigless-dim,multiline-browser` **TOUT OK** (62) ; la section 5 de `test_macro.py` avec `track-filter,
6ch-usbup,trig-hold,arp,tempo-max,boot-anim,multiline-browser,level-pan-values,trigless-dim` **TOUT OK**. Avec
`chord-keys`, cette section s'arrête sur une lecture hors de la mémoire du moteur de `test_macro.py` (Chord Keys lit
le BSS de l'OS sur une piste CHORD, que ce moteur ne place pas) : limite du banc, pas du firmware ; Chord Keys avec
MACRO est couvert par la preuve du filtre ci-dessus.

Flasher (`tools/webflash_smoke.sh` avec les deux fichiers officiels, après la fusion de main) : **ALL OK**, 758
vérifications ; les 627 combinaisons de l'échantillon construites dans la page, chacune à son empreinte.

## 6. Charge

Instructions par bloc de 32 trames d'une voix, mesurées comme en [43 §8](43-machine-macro.md) (moyenne sur 21 blocs,
note 60, réglages par défaut), avant, maintenant (FINE au centre), puis avec RATE vers 24 kHz (FINE 46) et vers 7,5 kHz
(FINE 16). TONE : 5 291.

| Modèle | Avant | Maintenant | RATE ~24 kHz | RATE ~7,5 kHz |
|---|---|---|---|---|
| 0 CSAW | 7 221 | 3 945 (55 %) | 2 864 (40 %) | 2 006 (28 %) |
| 2 SAW SQUARE | 12 140 | 6 590 (54 %) | 4 366 (36 %) | 2 690 (22 %) |
| 5 SQUARE SUB | 12 499 | 6 788 (54 %) | 4 481 (36 %) | 2 747 (22 %) |
| 6 SAW SUB | 12 401 | 6 740 (54 %) | 4 459 (36 %) | 2 742 (22 %) |
| 9 TRIPLE SAW | 11 470 | 6 599 (58 %) | 4 678 (41 %) | 3 382 (29 %) |
| 10 TRIPLE SQUARE | 16 522 | 9 141 (55 %) | 5 972 (36 %) | 3 822 (23 %) |
| 11 TRIPLE TRIANGLE | 11 955 | 6 797 (57 %) | 4 732 (40 %) | 3 342 (28 %) |
| 12 TRIPLE SINE | 10 419 | 6 029 (58 %) | 4 348 (42 %) | 3 218 (31 %) |
| 37 WAVETABLES | 10 083 | 5 450 (54 %) | 3 681 (37 %) | 2 342 (23 %) |
| 38 WAVE MAP | 18 313 | 9 583 (52 %) | 5 766 (31 %) | 3 024 (17 %) |
| 39 WAVE LINE | 14 041 | 7 455 (53 %) | 4 710 (34 %) | 2 701 (19 %) |
| 40 WAVE PARAPHONIC | 17 659 | 9 442 (53 %) | 5 865 (33 %) | 3 228 (18 %) |
| 46 DIGITAL MODULATION | 7 142 | 4 034 (56 %) | 3 022 (42 %) | 2 193 (31 %) |

- Les 34 autres modèles : +44 instructions par bloc (le choix du rendu, +0,4 %) ; avec RATE, +204 (FINE 16) à
  +226 (FINE 46) de plus (l'échantillonneur-bloqueur, +1 à 5 %), le calcul de Braids ne change pas.
- **Pire cas** : WAVE MAP était le plus lourd (18 313 en moyenne, 20 320 au pire) ; maintenant HARMONICS (16 565,
  18 348 au pire). Médiane des 47 : 10 973 → 9 082.
- Voix muette : 245 → 300 ; pile : 344 → 356 o sous la boucle des voix.

Ce sont des instructions ; sur la machine, les modèles à tables d'ondes paient aussi les défauts de cache (tables de
33 Ko), deux fois moins nombreux à 48 kHz `[HYP]`. La page System de Model-TG donne le temps de MACRO.

## 7. Sur la machine `[FAIT]`

Ce qui était à vérifier :

1. Sur une piste MACRO, FUNC + PITCH : que montre l'écran ? Au centre (valeur par défaut), le son est celui d'avant.
2. Les modèles allégés sonnent comme avant (comparer avec le firmware d'avant, ou avec un modèle voisin) : CSAW,
   TRIPLE SQUARE, WAVE MAP, WAVE PARAPHONIC, à plusieurs notes.
3. FUNC + PITCH à gauche : le son devient granuleux, de plus en plus en descendant ; à droite, écrasé (8 bits, puis 2).
   Un p-lock de FINE sur un pas.
4. Charge : 4 à 6 pistes WAVE MAP ensemble, au centre puis avec RATE à gauche ; avec Model-TG, la page System.
5. MACRO avec les moteurs du Syntakt (Model-TG + les 5 moteurs, comme le 10/10/2026) : démarrage et son.

Testé sur la machine le 11/10/2026 : « ça marche nickel sur machine je viens de testé. Si c ok pour toi tu peux
fusionner » (Maxime). Il n'a pas détaillé les points un par un : ce que l'écran affiche avec FUNC + PITCH (§3.4,
`[HYP]`) reste à noter.
