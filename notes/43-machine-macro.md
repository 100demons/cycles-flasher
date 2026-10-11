# 43 — Machine MACRO : les 47 modèles de synthèse de Braids sur le Model:Cycles

Demande de la communauté (forum « feedback » du Discord du projet, « Adding mutable instruments engines as machines
(Braids, Plaits, etc) », 5 votes, idée de dan303 : les macros de Plaits sur COLOR, SHAPE et SWEEP, CONTOUR pour le low
pass gate), relevée par le point hebdo du 06/10/2026 ; Maxime a choisi le même jour « Braids d'abord » : une machine
MACRO avec les modèles de Braids, les moteurs de Plaits plus tard, un par un, s'ils tiennent en charge. Tweaks
`25-macro.json` (seul) et `32-macro-tg.json` (avec Model-TG), générateur `tools/gen_macro.py`, passerelle
`tools/machines/macro/`, preuve `tools/emu/test_macro.py` (référence `tools/emu/braids_ref.cc`). Adresses : VA de l'OS
1.13.

## Réponse courte

- **Braids tourne tel quel sur le Cycles** : son code est en entiers 16 bits, fait pour un processeur sans FPU. Plaits
  calcule en flottant partout ; le ColdFire du Cycles n'a pas de FPU : chaque moteur de Plaits serait à réécrire en
  virgule fixe (§1).
- **Une seule machine ajoutée, MACRO, dont SHAPE choisit le modèle** (0 à 46, verrouillable par pas), plutôt que 47
  machines : la mécanique des machines ajoutées en accepte 6 (§2), et un modèle par pas reste un simple p-lock.
- **Le son est celui du code de Braids, à l'échantillon près** `[FAIT en émulation]` : Braids rend à 96 kHz comme sur
  le module, un filtre demi-bande ramène à 48 kHz (passe-bande 0..19 kHz à 0,04 dB près, −46 dB dès 29 kHz). DECAY,
  GATE et PUNCH sont la chaîne d'ampli d'origine, réglée comme TONE.
- **Charge** : une voix MACRO coûte environ 2 fois une voix TONE en instructions, de 0,8 fois (CLOCKED NOISE) à 3,5 fois
  (WAVE MAP) selon le modèle (§8). Pas de régulateur de charge : quelques pistes MACRO lourdes jouées ensemble peuvent
  dépasser le temps d'un bloc (son qui craque, écran ralenti, comme les moteurs du Syntakt avant leur régulateur,
  [25](25-regulateur-de-charge.md)). À écouter sur la machine.
- **Licence** : MIT, crédit à Émilie Gillet ; ni le nom du module ni celui de Mutable Instruments sur la machine.
- **Testé sur la machine** (07/10/2026) : « Ça marche nickel » (Maxime, §10) ; la carte du flasher passe en « Testé ».

## 1. Faisabilité : Braids ou Plaits `[FAIT en émulation, 06/10/2026]`

Mesures sur le code d'origine (`pichenettes/eurorack`, commit `08460a6`, stmlib `e3bd7c9`), compilé pour le ColdFire
du Cycles (`-mcpu=54418 -O2`), exécuté dans Unicorn par blocs de 32 échantillons ; sorties identiques à l'échantillon
près à la même voix compilée pour l'ordinateur (le banc est juste).

| | Plaits | Braids |
|---|---|---|
| Calcul | flottant partout | entier (16 bits), fait pour un processeur sans FPU |
| Tel quel sur le ColdFire | 8 000 à 73 000 instructions **plus 1 200 à 11 700 opérations flottantes** par bloc, chacune une routine logicielle : plus que tout le processeur | tourne tel quel |
| Sur sa propre puce (Cortex-M4F, avec FPU) | 4 604 (Speech) à 25 896 (Modal) instructions par bloc, ~13 000 en général | — |
| Travail | réécrire chaque moteur en virgule fixe (24 moteurs) | brancher sur la boucle des voix, 96 → 48 kHz |
| Place | ~48 Ko de code + 91 Ko de tables, ~25 Ko de RAM par voix | ~98 Ko de code et tables (dont 33 Ko de tables d'ondes), ~17 Ko de RAM par voix |

Une réécriture de Plaits en virgule fixe ne descendrait pas sous son coût sur sa propre puce : ~2 voix du Cycles par
voix de Plaits. D'où le choix de Maxime : Braids d'abord.

## 2. Ce que l'OS impose `[FAIT]`

| Où | Quoi |
|---|---|
| `0x400a7d4a` | boucle des voix ([14 §2](14-machine-sd-vintage.md)) : pour chaque piste, `update[m](pmod, voix, params)` puis `render[m](out, voix)`, par les tables `0x40118628` / `0x40118610` ; une machine ≥ au nombre de machines n'est pas calculée |
| `voix + 0` / `+4` | machine courante / précédente ; la machine ne change qu'au bloc qui suit un trig (`+0x38`) ; remise à zéro de la voix `0x400a7ab8` |
| `voix + 0x34` / `+0x38` | trig de ce bloc / du bloc précédent |
| `pmod` | note du trig en demi-tons `<< 16` ; toutes les machines : note = PITCH − 64 + note du trig + FINE, bornée à 0..127, 440 Hz à 69 |
| `params + 0x14..0x24` | PITCH, COLOR, SHAPE, SWEEP, CONTOUR, PUNCH, GATE, FINE, DECAY (mots 8.8) |
| `0x400a9252` / `0x400a9430` / `0x400a967a` | enveloppe d'ampli, VCA, PUNCH : fonctions feuilles, appelées par le `render` de TONE |
| `voix + 0x230..0x2a4` | état de l'enveloppe et de PUNCH, réglé par l'`update` de TONE (`0x400aa7b8`) au trig |

Les machines ajoutées reprennent la mécanique des moteurs du Syntakt ([20](20-moteurs-syntakt-a-cocher.md),
[31](31-model-tg.md)) : tables des descripteurs, des rangées, des noms et de `update`/`render` déplacées dans la charge
utile, bornes `moveq` relevées, détours de l'écran MACHINES, de la molette et des enregistrements. Elle accepte 6
machines ajoutées : MACRO en prend une, et la même place (charge utile à `0x43000000`, `0x46700000` avec Model-TG) que
les moteurs du Syntakt, d'où leur incompatibilité (§6).

## 3. Conception

### 3.1 Les potards

| Potard du Cycles | Nom affiché | Ce que reçoit Braids |
|---|---|---|
| PITCH, FINE, touches | — | note = PITCH − 64 + note du trig + FINE (±2 demi-tons), en 1/128 de demi-ton : la même convention, 440 Hz à 69 (mesuré : 439,99 Hz, SINE/TRIANGLE à la note 69) |
| COLOR | Timbre (TIMB) | TIMBRE = COLOR + CONTOUR × enveloppe |
| SHAPE | Model (MODL), 0..46 | le modèle, dans l'ordre de Braids (CSAW, MORPH, … DIGITAL MODULATION ; sans QUESTION MARK) |
| SWEEP | Color (COLR) | COLOR de Braids |
| CONTOUR | Env Timbre (ENVT) | quantité d'enveloppe d'ampli ajoutée à TIMBRE (son niveau au bloc précédent, plein au trig) ; 0 : rien |
| DECAY, GATE, PUNCH | (communs) | la chaîne d'ampli d'origine, réglée comme TONE (mêmes constantes au trig, même table de DECAY `0x4011d84c`) |

Un potard 8.8 de 0..127 devient 0..32 766 (`x + (x >> 7)`). Un trig appelle `Strike()` (les modèles percussifs et
physiques sont frappés). L'image de la machine (écran MACHINES, petite icône) est celle de TONE : l'OS n'en a que 6.

### 3.2 De 96 à 48 kHz

Braids est fait pour 96 kHz (tables de hauteur, de filtres, d'ondes) et, sur le module, rend des blocs de 24
échantillons, 4 000 fois par seconde (`kBlockSize` de `braids/braids.cc`). Une partie de son état avance d'un pas par
bloc, pas par échantillon : la décroissance des partiels de STRUCK BELL et STRUCK DRUM (`digital_oscillator.cc`), la
consonne de VOWEL (160 blocs), les lissages de paramètres sur la durée d'un bloc. La passerelle garde donc des blocs de
24 : il lui faut 64 échantillons par bloc de 32 trames, soit 3, 3 puis 2 rendus de 24 (8 × 24 = 3 × 64, 4 000 rendus
par seconde comme sur le module) ; ce qui dépasse (8 ou 16 échantillons, 0,17 ms au plus) attend le bloc suivant.
`[FAIT en émulation]` La première version rendait 24 + 24 + 16 à chaque bloc, 4 500 rendus par seconde : les cloches
et les tambours de STRUCK BELL/DRUM s'éteignaient ~11 % trop vite (relevé à la relecture du 07/10/2026, corrigé
avant la PR). Puis un filtre demi-bande de 23 coefficients
(minimax, Q15, `{10327, −3131, 1579, −820, 434, −197}`, ½ au centre ; somme 1 : gain 1 en continu) garde un
échantillon sur deux : passe-bande 0..19 kHz à 0,04 dB près, −46,2 dB au-delà de 29 kHz (ce qui se replierait sous
19 kHz), retard 5,5 échantillons à 48 kHz. Un filtre de 19 coefficients plafonnait à −39,7 dB. Sortie : la pleine
échelle de Braids donne la moitié de la pleine échelle Q31 du Cycles.

### 3.3 État, initialisation, voix muette

- Une voix de Braids par piste (`MacroOscillator`, 22 échantillons d'historique du filtre et l'avance de 16 au plus :
  17 192 o), dans le BSS de la charge utile, mis à zéro au démarrage.
- Initialisée à la première note sur la machine : repère `'MCR1'` en `voix + 0x2c`, effacé par la remise à zéro de la
  voix (`0x400a7ab8`) à chaque changement de machine.
- **Voix muette non calculée** : sans trig et avec l'enveloppe d'ampli sous 2^14 (−102 dB), la sortie est nulle et
  Braids ne tourne pas. C'est ce qui permet de mêler MACRO aux autres machines sans régulateur.
- Le générateur aléatoire de Braids (`stmlib::Random`, statique) est commun aux 6 pistes : deux pistes de bruit
  s'entremêlent ses tirages. Inaudible ; c'est pourquoi la vérification des 6 pistes ensemble prend des modèles
  analogiques (§7).
- Au changement de modèle, Braids efface l'état de sa voix numérique (194 o) et, pour BOWED, BLOWN et FLUTED, leurs
  lignes à retard (4 à 5 Ko), dans l'interruption audio : `memset` par mots de 32 bits (`rt.c`), ~2 000 instructions
  au lieu de ~25 000 octet par octet.

### 3.4 Avec Model-TG

MACRO est la 8e machine, après le Sampler de Model-TG. Un détour (`dispatch_tg_asm`) en `0x400a7dfe` envoie les
machines 0..6 au dispatch de Model-TG et MACRO à nos `update`/`render`, puis à la fin de l'étage d'amplitude de
Model-TG (`ah_noenv` : Attack, filtre, résonance) ; le temps de MACRO s'affiche sur la page System de Model-TG
(`prof_trk`). Comme pour les moteurs du Syntakt, la version combinée s'ajoute après `model-tg-st` ([31 §4](31-model-tg.md)).

## 4. Place

| | Seul (`macro`) | Avec Model-TG (`macro-tg`) |
|---|---|---|
| Charge utile au démarrage | `0x43000000..0x4304f2f0` | `0x46700000..0x4674f2f0` |
| Code, tables et données de Braids et de la passerelle | 98 230 o à `+0` | idem (33 relocalisations) |
| Détours, données, descripteurs, rangées, enregistrements | `+0x33000..0x36000` (`gs.LAYOUT`) | idem |
| Variables (6 voix de Braids) | 103 152 o à `+0x36000` | idem |
| Ajouté à l'image (morceaux tassés, stub `PACK`) | 103 552 o | 103 964 o |
| Fin de l'image décompressée (limite `0x40200000`) | `0x401c35c0` | `0x401d8edc` |
| Crochet de démarrage | masque de sprite `0x4016cae8` : à `0x400004b2` (remise à zéro du BSS) | idem, appelé par le `jsr` de `0x40000530` puis chaîné à `boot_extra_hook` de Model-TG |

Le crochet (`tools/machines/syntakt_bridge/stub.S`, `PACK`) met la zone de la charge utile à zéro puis y recopie les
morceaux : les 100 Ko de variables ne prennent pas de place dans l'image. `stub.S` a été restructuré pour chaîner
`PACK` et `CHAIN_TO` ; les configurations existantes donnent les mêmes octets.

## 5. Le tweak et sa licence

- `25-macro.json` : 122 écritures, plus l'envoi à l'USB à heure fixe ([35](35-glitches-usb-multipiste.md)) et la boucle
  des voix de [36](36-regulateur-sans-coupures-inutiles.md), comme les moteurs du Syntakt seuls.
- `32-macro-tg.json` : 114 écritures, `requires` `model-tg-st`.
- Le code de Braids est compilé **sans modification** (`braids/macro_oscillator`, `analog_oscillator`,
  `digital_oscillator`, `resources`, `stmlib/utils/random`), avec `m68k-linux-gnu-g++` 13.3 (Ubuntu 24.04) ; un autre
  GCC donne d'autres octets (`--check` le dit). Aucun octet Elektron dans les JSON : la table des descripteurs est
  recopiée au build depuis le fichier de l'utilisateur (recette `cycles`).
- Licence MIT : `tweaks/model-cycles_OS1.13/LICENSE-Braids` (copiée en `docs/flasher/LICENSE-Braids.txt`), écrite par le
  générateur depuis l'en-tête des sources. La carte du flasher, le guide et le README créditent Émilie Gillet et
  disent d'où vient le code ; la machine s'appelle MACRO.

## 6. Incompatibilités

- **Moteurs du Syntakt** (toutes les combinaisons, seuls ou avec Model-TG) : même mécanique de machines ajoutées,
  même place, donc pas `macro` avec eux. Le flasher rendait les deux cartes exclusives (`excludes`) ; depuis le
  07/10/2026, cochées ensemble, elles donnent une version combinée, une charge utile commune avec MACRO après les
  moteurs ([50](50-macro-avec-moteurs-syntakt.md)).
- **SD VINTAGE** (`sdvintage-*`, `syntakt-vintage`, `syntakt-meter`…, hors du flasher) : même crochet de démarrage
  (`0x4016cae8`) et même charge utile à `0x43000000`.
- `macro` seul ne va pas avec Model-TG : avec la carte Model-TG cochée, le flasher prend `model-tg-st` + `macro-tg`
  (son `with`), comme pour les moteurs du Syntakt.
- Avec tous les autres mods du flasher (6 canaux, arpégiateur, trig-hold, tempo, animation, drumkilla) : aucune
  écriture ne se chevauche ; les 9 503 combinaisons du flasher se construisent (`tools/ref_mainos.py`).

## 7. Preuve en émulation `[FAIT en émulation]`

`tools/emu/test_macro.py` : le vrai code de l'OS (Unicorn), avec la charge utile telle que le crochet la reconstitue ;
la référence est Braids compilé pour l'ordinateur (`g++ -O2`) depuis les mêmes sources, piloté bloc par bloc par
`braids_ref.cc` avec les réglages que la passerelle doit lui donner (calculés par le test d'après cette note), puis le
filtre demi-bande en Python.

| Vérification | Seule (`macro`) | Avec Model-TG (`macro-tg`) |
|---|---|---|
| Démarrage : le décompresseur du bootstrap relit l'OS agrandi ; le crochet reconstitue la charge utile (0xa5 partout avant), garde la SRAM, la pile et d2..d7/a2..a6 | ok, fin de l'image `0x401c35c0` | ok, chaîné à `boot_extra_hook`, fin `0x401d8edc` |
| Interface (vérifications de `test_syntakt_machines.py` / `test_model_tg_syntakt.py`) : tables, rangées, descripteurs (Model 0..46), écran MACHINES, molette, enregistrements, vrai changement de machine, potards, icône, machine hors limites | ok, 7 machines | ok, 8 machines sur 2 lignes, libellés et touche Attack de Model-TG |
| Son avant la chaîne d'ampli = Braids compilé pour l'ordinateur + filtre, échantillon par échantillon | **107 cas** : les 47 modèles et 60 variantes (COLOR, SWEEP aux bouts, CONTOUR, notes extrêmes, bornes de hauteur, PUNCH, GATE, DECAY court, voix qui se tait puis repart, modèle et potards qui bougent pendant la note, Model au-delà de 46) | **52 cas** : les 47 modèles, DECAY court, la voix qui se tait puis repart, le modèle qui change |
| Voix calculée exactement quand l'OS l'impose (trig de ce bloc ou du précédent, ou enveloppe d'ampli ≥ 2^14), bloc par bloc ; sinon sortie nulle et aucun appel de Braids | 11 576 blocs, dont 339 muets | 7 506 blocs, dont 339 muets |
| Blocs de 24 comme sur le module : 3, 3 puis 2 appels de `Render` par bloc calculé (compte remis à zéro à l'initialisation), aucun pour une voix muette | ok | ok |
| Chaîne d'ampli : mêmes lectures de la voix que TONE (24 champs ; DECAY, PUNCH, GATE) | ok | même passerelle |
| Machines d'origine identiques, aucune instruction de Braids | à l'OS d'origine | à Model-TG seul |
| Sortie finale de la piste MACRO identique à MACRO seule (5 modèles) | — | ok |
| Machine locks SNARE → MACRO (FM) → TONE → MACRO (WAVETABLES) → KICK sur une piste | ok | ok |
| 6 pistes MACRO ensemble = chacune jouée seule | ok | ok |
| Pistes mêlées KICK, MACRO, METAL, CHORD, MACRO, TONE : machines d'origine identiques sans MACRO, chaque piste MACRO = la même jouée seule | ok | ok, le Sampler sans échantillon (muet) à la place de METAL |
| Filtre demi-bande : gain 1 en continu, 0,04 dB de 0 à 19 kHz, −46,2 dB au-delà de 29 kHz | ok | ok |
| `--with 6ch-usbup,trig-hold,arp,tempo-max,boot-anim` (et `model-tg-st`) : démarrage, machines d'origine identiques aux mêmes mods sans MACRO, sortie de MACRO identique, machine locks, pistes mêlées | ok | ok |

Durée : ~45 min pour la preuve complète (59 min avec `--with` et le test du flasher en même temps, sur 4 cœurs), ~25 min
avec `--quick`. Et le flasher : les 9 503 combinaisons proposées par la page, construites par la page sur le vrai OS
(`tools/webflash_smoke.js`, en 8 parts), donnent toutes le MAIN OS de `REF_MAINOS`, lui-même calculé comme
`tools/build.py`.

## 8. Charge

Instructions par bloc de 32 trames d'une voix (la boucle des voix entière, moins la même boucle sans voix), mesurées
dans la vraie boucle des voix : 1er bloc (avec l'initialisation), puis moyenne et maximum sur les 21 blocs suivants
(7 tours de 3, 3 puis 2 rendus de 24 ; le maximum est un bloc à 3 rendus).

| Modèle | 1er bloc | moyenne | maximum | moyenne / TONE |
|---|---|---|---|---|
| 0 CSAW | 8 349 | 7 221 | 7 870 | 1,4 |
| 1 MORPH | 13 577 | 11 897 | 13 182 | 2,2 |
| 2 SAW SQUARE | 13 842 | 12 140 | 13 428 | 2,3 |
| 3 SINE TRIANGLE | 18 211 | 15 926 | 17 635 | 3,0 |
| 4 BUZZ | 11 608 | 10 057 | 11 032 | 1,9 |
| 5 SQUARE SUB | 14 170 | 12 499 | 13 861 | 2,4 |
| 6 SAW SUB | 14 196 | 12 401 | 13 741 | 2,3 |
| 7 SQUARE SYNC | 13 860 | 12 204 | 13 509 | 2,3 |
| 8 SAW SYNC | 10 110 | 8 755 | 9 617 | 1,7 |
| 9 TRIPLE SAW | 13 170 | 11 470 | 12 664 | 2,2 |
| 10 TRIPLE SQUARE | 18 621 | 16 522 | 18 502 | 3,1 |
| 11 TRIPLE TRIANGLE | 13 752 | 11 955 | 13 168 | 2,3 |
| 12 TRIPLE SINE | 12 024 | 10 419 | 11 440 | 2,0 |
| 13 TRIPLE RING MOD | 10 446 | 9 038 | 9 886 | 1,7 |
| 14 SAW SWARM | 13 759 | 11 790 | 12 982 | 2,2 |
| 15 SAW COMB | 10 020 | 8 468 | 9 253 | 1,6 |
| 16 TOY | 8 777 | 7 401 | 8 043 | 1,4 |
| 17 DIGITAL FILTER LP | 13 257 | 11 421 | 12 602 | 2,2 |
| 18 DIGITAL FILTER PK | 13 329 | 11 484 | 12 674 | 2,2 |
| 19 DIGITAL FILTER BP | 12 753 | 10 973 | 12 098 | 2,1 |
| 20 DIGITAL FILTER HP | 12 753 | 10 972 | 12 098 | 2,1 |
| 21 VOSIM | 10 872 | 9 255 | 10 138 | 1,7 |
| 22 VOWEL | 9 829 | 8 297 | 9 055 | 1,6 |
| 23 VOWEL FOF | 13 623 | 11 763 | 13 046 | 2,2 |
| 24 HARMONICS | 19 038 | 16 521 | 18 304 | 3,1 |
| 25 FM | 7 650 | 6 398 | 6 916 | 1,2 |
| 26 FEEDBACK FM | 8 268 | 6 947 | 7 534 | 1,3 |
| 27 CHAOTIC FEEDBACK FM | 8 751 | 7 377 | 8 017 | 1,4 |
| 28 PLUCKED | 8 755 | 9 100 | 10 171 | 1,7 |
| 29 BOWED | 11 472 | 7 622 | 8 293 | 1,4 |
| 30 BLOWN | 11 481 | 8 172 | 8 916 | 1,5 |
| 31 FLUTED | 16 164 | 11 899 | 13 105 | 2,2 |
| 32 STRUCK BELL | 15 972 | 13 354 | 14 798 | 2,5 |
| 33 STRUCK DRUM | 14 946 | 12 915 | 14 258 | 2,4 |
| 34 KICK | 12 860 | 10 412 | 11 695 | 2,0 |
| 35 CYMBAL | 18 266 | 15 758 | 17 449 | 3,0 |
| 36 SNARE | 14 009 | 11 705 | 12 890 | 2,2 |
| 37 WAVETABLES | 11 792 | 10 083 | 11 062 | 1,9 |
| 38 WAVE MAP | 21 054 | 18 313 | 20 320 | 3,5 |
| 39 WAVE LINE | 16 248 | 14 041 | 15 514 | 2,7 |
| 40 WAVE PARAPHONIC | 20 351 | 17 659 | 19 585 | 3,3 |
| 41 FILTERED NOISE | 8 892 | 7 502 | 8 158 | 1,4 |
| 42 TWIN PEAKS NOISE | 7 416 | 6 189 | 6 706 | 1,2 |
| 43 CLOCKED NOISE | 5 062 | 4 106 | 4 344 | 0,8 |
| 44 GRANULAR CLOUD | 15 127 | 12 963 | 14 369 | 2,5 |
| 45 PARTICLE NOISE | 7 926 | 6 613 | 7 290 | 1,2 |
| 46 DIGITAL MODULATION | 8 491 | 7 142 | 7 753 | 1,3 |

- Boucle des voix sans voix : 1 232 instructions par bloc ; **TONE : 5 291** (une voix d'origine).
- **MACRO : 4 106 à 18 313 en moyenne, médiane 10 973** (2,1 fois TONE) ; au pire 20 320 (WAVE MAP, bloc à 3 rendus).
  Les plus lourds : les cartes d'ondes (WAVE MAP, WAVE PARAPHONIC, WAVE LINE), TRIPLE SQUARE, HARMONICS, SINE
  TRIANGLE, CYMBAL ; les plus légers : les bruits et la FM.
- Voix muette : 245 ; changement de modèle FM → BOWED (lignes à retard effacées) : 10 914 ; pile : 344 o sous la boucle
  des voix.
- Avec Model-TG (CSAW, VOWEL FOF, WAVETABLES) : 7 280, 11 822 et 10 142 en moyenne, TONE 5 669 (son étage
  d'amplitude), voix muette 304.

Braids rend ici 64 échantillons par bloc en moyenne (96 kHz ; 72 aux blocs à 3 rendus, 48 à ceux à 2), deux fois plus
que les mesures de faisabilité du 06/10 (blocs de 32 échantillons : 959 à 8 031 instructions selon le modèle), plus le
filtre demi-bande et la chaîne d'ampli d'origine.

Ce sont des instructions, pas des cycles : le ColdFire n'a que 8 Ko de cache d'instructions et 8 Ko de cache de
données, et la SDRAM (DDR2 sur un bus de 8 bits) coûte cher à chaque défaut. Le code de Braids atteint par un modèle
devrait tenir à peu près dans le cache, mais pas ses tables d'ondes (33 Ko) : les modèles à tables d'ondes peuvent
coûter plus que ce rapport sur la machine `[HYP]`. Le régulateur des moteurs du Syntakt ([25](25-regulateur-de-charge.md),
[30](30-regulateur-charge-soutenue.md), [36](36-regulateur-sans-coupures-inutiles.md)) n'est pas branché ici : plusieurs
pistes MACRO lourdes jouées ensemble peuvent dépasser le temps d'un bloc et faire craquer le son. Model-TG affiche le
temps de MACRO sur sa page System.

## 9. À vérifier sur la machine

1. Flasher MACRO seule, puis avec Model-TG : MACHINES montre MACRO en 7e (8e avec Model-TG), avec l'icône de TONE.
2. SHAPE parcourt les modèles 0..46 ; COLOR, SWEEP et CONTOUR changent le son ; la note suit PITCH, FINE et les touches
   (même hauteur que TONE à réglages égaux).
3. DECAY, GATE, PUNCH comme sur TONE ; p-lock de SHAPE (modèle par pas) ; machine locks MACRO ↔ machines d'origine.
4. Une piste MACRO sur un modèle lourd (WAVE MAP, HARMONICS, CYMBAL) avec les machines d'origine, puis deux, trois… :
   craquements, écran ralenti ? Avec Model-TG, la page System donne le temps de chaque piste.
5. Remettre les pistes MACRO sur une machine d'origine avant de reflasher un autre choix ou l'OS officiel.

## 10. Testé sur la machine (07/10/2026)

Maxime a reçu au fil du projet trois firmwares de test construits depuis son OS officiel (MAIN OS : MACRO seule
`beb70b58…`, avec Model-TG `d738fafa…`, avec 6 canaux, Model-TG, trig-hold, arpégiateur, tempo et animation
`f584f099…`) et la liste du §9. Il répond : « Ça marche nickel. Ajoute le au flasher », sans préciser lesquels il a
flashés. La carte passe de « Expérimental » à « Testé ». Il n'a pas détaillé la charge (§9, point 4) : le régulateur reste à faire si des pistes
MACRO lourdes font craquer le son.

## 11. Suite

- Un régulateur de charge (celui des moteurs du Syntakt) si la machine craque.
- 10/10/2026 : 13 modèles rendus à 48 kHz (moitié moins de calcul) et le lo-fi RATE / BITS sur FINE (FUNC + PITCH) :
  [55](55-macro-allegee-et-lofi.md). FINE n'accorde plus MACRO.
- Les moteurs de Plaits en virgule fixe, un par un, comparés au Plaits d'origine, dans la même machine s'ils tiennent
  en charge (candidats : les trois percussions analogiques, VA, FM, Chords, Speech, String, Modal).
- ~~MACRO avec les moteurs du Syntakt (une charge utile commune), si on le demande.~~ Demandé par Maxime le 07/10/2026,
  fait : [50](50-macro-avec-moteurs-syntakt.md) (le régulateur des moteurs y veille aussi sur les pistes MACRO).
