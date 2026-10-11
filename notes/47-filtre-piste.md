# 47 — Un filtre par piste : passe-bas, OFF, passe-haut (`track-filter`)

Demande du serveur Discord (forum *feature-requests*, fil « High-pass filter per track / machine », 05/10/2026) : un
passe-haut par piste, puis un filtre bipolaire « DJ » : passe-bas d'un côté, rien au centre, passe-haut de l'autre.
Maxime (06/10/2026) : le développer, puis, une fois testé sur sa machine, retirer le filtre par piste de Model-TG, que
celui-ci remplace. Tweak `48-track-filter.json`, généré par `tools/gen_track_filter.py` depuis
`tools/machines/track_filter/` (`track_filter.S` le filtre, `tf_ui.S` les potards, l'affichage et la sauvegarde,
`track_filter.ld`), preuve `tools/emu/test_track_filter.py`. Étude préalable (OS Cycles 1.13, Samples 1.13,
Syntakt 1.42, Model-TG v1.1.0) dans `/mnt/project-files/filtre-piste/faisabilite.md`. Adresses : VA de l'OS 1.13.

## En bref

**Testé sur la machine (11/10/2026)**, après une correction de l'affichage et de la résonance (§10).

- **MACHINES tenu + SWEEP = Filter Cutoff** : L64 … L1, **OFF**, H1 … H63. Passe-bas à gauche (5 Hz à 20 kHz),
  passe-haut à droite (5 Hz à 19 kHz), la loi du potard du Model:Samples. **+ CONTOUR = Filter Reso** (Q 0,5 à 50),
  **+ COLOR = Filter Env** (quantité d'une enveloppe, bipolaire), **+ SHAPE = Env Decay** (5 ms à 10 s). L'enveloppe
  repart à chaque note de la piste.
- Quatre **vrais paramètres de toutes les machines** (k 28 à 31, descripteurs 1 à 4 de l'OS, des emplacements
  « Error » inutilisés) : p-locks, destinations du LFO et de la vélocité, CC 74 et 71, NRPN 1:20 et 1:21, valeurs par
  défaut d'un son neuf, sauvegarde avec le son et le pattern.
- Le filtre est un **SVF 2 pôles trapézoïdal** (12 dB/oct), appliqué **après Volume + Dist** et avant le panoramique,
  le niveau et les envois (l'ordre du Model:Samples) : l'audio USB 6 canaux reçoit les pistes filtrées.
- **Au centre, la piste n'est pas touchée, bit pour bit** (prouvé sur le vrai code, avec les autres mods).
- Corrige au passage la sauvegarde des **p-locks des paramètres k ≥ 23** dans le pattern : l'OS d'origine les rangeait
  sur LFO Speed, LFO Multiplier… ou les perdait (§4.3).
- Place : 3 001 o de code, tables et état dans **quinze masques de sprites 35×35** libérés (§6). Coût : §9.
- **Incompatible avec Model-TG** pour l'instant (même geste, mêmes accroches de sauvegarde) : étape 2 (§11).

## 1. Sur la machine

| Geste | Paramètre (nom court) | Affichage | Défaut |
|---|---|---|---|
| MACHINES tenu + SWEEP | Filter Cutoff (FREQ) | `L64` … `L1`, `OFF`, `H1` … `H63` | OFF |
| MACHINES tenu + CONTOUR | Filter Reso (RESO) | 0 … 127 | 0 |
| MACHINES tenu + COLOR | Filter Env (FENV) | −64 … OFF … +63 | OFF |
| MACHINES tenu + SHAPE | Env Decay (FDEC) | 0 … 127 | 64 |

C'est le geste de l'Attack de Model-TG, et la place des potards CUTOFF / RESONANCE du Model:Samples. MACHINES appuyé
seul ouvre toujours le menu des machines. Un pas de potard (256 en 8.8) vaut environ 2 demi-tons de fréquence (64 pas
de chaque côté). Entre OFF et le pas voisin (L1, H1), la sortie passe de l'entrée au filtre (w = |C − centre| / 256,
pour les valeurs fines du lissage des paramètres, d'un NRPN ou d'un LFO ; elles s'affichent `L0` / `H0`) : le
passage par le centre ne claque pas.

## 2. Où brancher le filtre `[FAIT]`

Fonction audio par bloc `0x4005979e` (32 trames à 48 kHz, 1 500 blocs par seconde ; pistes mono Q31 en SRAM,
`0x80001858 + 128 t`) :

| Site | Appel | Rôle |
|---|---|---|
| `0x400597a8` | `0x40058474` | lisse les mots des paramètres (les 33 mots k 0..32 des 6 pistes) ; rend a2 = `0x8000100c` |
| `0x4005981e` | `0x400a7d4a(0x80001858, a2, déclenchées, relâchées)` | boucle des 6 voix ; a3 = contexte : +16 pistes déclenchées dans le bloc, +20 relâchées |
| `0x4005982a` | `0x40056d9c` | gain de vélocité |
| **`0x40059852`** | **`0x40056f58(0x80001858, a2)`** | **Volume + Dist** (k 19), en place |
| `0x4005985c` | `0x40056ea8` | comptabilité du bloc ; accumule dans l'EMAC sans le vider avant |
| `0x40059872` | `0x400567ba` | mixeur : niveau, panoramique, envois delay/reverb |

L'accroche est **H3** : `jsr 0x40056f58` → `jsr tf_post`, qui appelle Volume + Dist avec les deux mêmes arguments puis
filtre les 6 pistes. Aucun tweak n'écrit ce site ; il voit les 6 pistes dans toutes les configurations (moteurs du
Syntakt, audio USB). Contrat : garder d2-d7/a2-a6, rendre MACSR (0x20 à cet endroit) et laisser **acc0-acc3 à
zéro** (`0x40056ea8` accumule ensuite). `tf_post` passe MACSR à 0xa0 (fractionnaire, saturé) pour le filtre.

Les mots lissés d'une piste sont à `a2 + 14 + 66 t + 2 k` : les potards tournés glissent déjà (lissage de l'OS), et
un p-lock, un LFO ou la vélocité y arrivent comme pour les autres paramètres.

## 3. Les paramètres `[FAIT]`

### 3.1 Descripteurs

Table `0x4010dce0`, 0x38 o par entrée (notes/14 §2.1). Les entrées 1 à 4 sont des « Error » du groupe −1, que le
constructeur des tables saute ; leurs objets d'interface sont verrouillables d'origine (+0 = 0). Réécrites :

| Desc. | k | Groupe | Défaut | CC | NRPN | Tri | Nom long / court |
|---|---|---|---|---|---|---|---|
| 1 | 28 | 7 (toutes les machines) | 16 384 (OFF) | 74 | 1:20 | 72 | Filter Cutoff / FREQ |
| 2 | 29 | 7 | 0 | 71 | 1:21 | 73 | Filter Reso / RESO |
| 3 | 30 | 7 | 16 384 | — | — | 74 | Filter Env / FENV |
| 4 | 31 | 7 | 16 384 | — | — | 75 | Env Decay / FDEC |

Plage 0..32 512 (0..127), drapeaux 0x600 (destinations du LFO et de la vélocité), groupe affiché « Amp »
(`0x40129882`). CC 74 / 71 et NRPN 1:20 / 1:21 : ceux du filtre du Model:Samples, libres sur le Cycles.

### 3.2 Le geste : MACHINES tenu

Le slot 124 de la vtable de `ParameterPageView` (`0x401005a8`, d'origine `0x4001e814`) rend le descripteur sous un
potard ; les trois appels de l'OS passent par lui (potard tourné `0x4001f6ee`, TRACK + potard `0x4001d716`, popup au
changement de piste `0x4001f090`). `tf_knob` appelle la recherche d'origine, puis, si le potard est COLOR, SHAPE,
SWEEP ou CONTOUR (4..7) et que MACHINES (touche 5, `0x4007faf4`) est tenu, rend 3, 4, 1 ou 2.

### 3.3 Affichage

Objets d'interface `0x40a71754 + 100 i` : formateur à +0x20 (appelé avec +0x14, la valeur et le tampon, par
`0x4000a70e`), dessin spécial à +0x2c (les « Error » dessinent une image à la place du texte). `tf_knob` (via
`tf_objs`) installe à chaque appel : `tf_fmt_cut` (`L`/`H` + |v − 0x4000| >> 8 par `sprintf "%s%d"`, `OFF` au
centre), `0x400456c8` (entier), `0x40045bd6` (`OFF` au centre, ±n) et `0x400456c8` ; et efface +0x2c.

L'écran ne montre que **trois caractères** de la valeur, comme ceux des formateurs de l'OS (Pan : `L64`, `CEN`,
`R63` ; défaut : `ERR`). La première version écrivait `LP64` : sur la machine, `LP10` à `LP64` se lisaient `LP1` à
`LP6` (essai de Maxime, 10/10/2026, §10.1). Les tampons passés au formateur (16 o à `0x4001e4d0`, 12 o à
`0x4001d890`) contenaient bien les 5 octets : c'est l'affichage qui coupe, pas un débordement.

### 3.4 Tables construites au démarrage, son neuf

`0x4005a274`, appelé une fois depuis `0x4004486c`, construit depuis les descripteurs : k → descripteur par machine
(`0x4005a692`), CC (`0x4005a8ce`), NRPN (`0x4005a92e`), liste des destinations du LFO (drapeaux 0x600, triée sur la clé).
Les moteurs du Syntakt (notes/28) remplacent l'opérande de `lea 0x4010dce0,a4` (`0x4005a2de`) par une copie de la
table dans leur charge utile, faite sur la table d'origine : `tf_boot` (accroché à `0x4004486c`) y recopie nos quatre
entrées quand l'opérande ne pointe plus sur `0x4010dce0`, puis saute au constructeur.

Un son initialisé (`0x400618f2` → `0x40061866` : nouveau projet, son effacé, changement de machine) prend pour chaque
k le défaut de son descripteur : Filter Cutoff au centre. Sans descripteur, le mot serait 0, un passe-bas fermé à
5 Hz : c'est pour cela que les quatre paramètres passent par des descripteurs, et que la sauvegarde range Cutoff
en XOR 0x4000 (§4.1).

## 4. Sauvegarde `[FAIT]`

### 4.1 Le son

Enregistrement de 100 o (`0x4005afa0` version 2, `0x4005b054` version 1, chargement `0x4005aecc`). La sauvegarde
efface +28..+91 (32 emplacements de 16 bits) puis ne range que k 0..22 par la table `0x4010ee4c` ; le chargement
efface k 0..32 puis relit les emplacements 0..23 par `0x4010eea8` (l'emplacement 18 va sur k 0, inutilisé). Les
trois fonctions commencent par `lea -12(sp),sp ; movem.l a2-a4,(sp)` : l'accroche (`jmp`, 6 o) refait ces deux
instructions, empile une copie des arguments et sa suite comme adresse de retour, et saute 8 o plus loin.

| Emplacement | Octets | Contenu |
|---|---|---|
| 30 | +88 | Filter Cutoff XOR 0x4000 : un son d'avant le mod (zéro) se charge **OFF** |
| 31 | +90 | Filter Reso |
| 18 | +64 / +65 | Filter Env / Env Decay, entiers 0..127 XOR 64 (zéro = 64) ; le chargement remet k 0 à zéro |
| 27 | +82 / +83 | destination du LFO / de la vélocité quand c'est l'un des nôtres (28..31), sinon 0 |

Les emplacements 24..29 restent libres (Model-TG s'y range : §11). Cutoff et Reso gardent la valeur fine (NRPN),
Env et Decay l'entier du potard (ils n'ont ni CC ni NRPN).

### 4.2 Destinations du LFO et de la vélocité

Le LFO (octet haut de k 4, +28 du son) et la vélocité (long +88) passent par les mêmes tables k → emplacement, lues
**sans borne** : pour k ≥ 23 l'OS d'origine range un index pris au-delà de la table. Le chargement relit ce qu'il
peut ; notre suite rétablit la destination quand +82 / +83 porte 28..31.

### 4.3 P-locks du pattern : un défaut de l'OS d'origine

Fichier des p-locks : jusqu'à 80 enregistrements de 130 o `[index, piste, 64 mots]`. La sauvegarde complète
`0x4005b95c` et la mise à jour d'un p-lock `0x4005ba90` lisent l'index dans la table `0x4010ee4c` (opérandes
`0x4005b998` et `0x4005baca`), **sans borne** : k 23 → index 0, k 24 → 1 (LFO Speed), k 25 → 2 (LFO Multiplier)…
Le chargement `0x4005b766` repasse l'index par `0x4005aa1a` (index ≤ 23, sinon 0) et refuse les index > 32. Prouvé
en émulation sur l'OS d'origine : un p-lock de k ≥ 23 revient sur LFO Speed, ailleurs, ou se perd, et la mise à jour
d'un tel p-lock **écrase les p-locks de LFO Speed** de la piste. Le filtre de Model-TG (k 24) en souffre aujourd'hui.

Correction : les deux opérandes pointent sur `tf_ptab` (33 entrées : k 0..22 comme l'OS ; 23..31 → 24..32, des index
que l'OS n'écrit jamais ; 32 → 0) et `0x4005aa34` (pistes 0..5) saute à `tf_conv`, qui rend k = index − 1 pour
24..32. Le format du fichier ne change pas ; relu par l'OS d'origine, un tel enregistrement tombe sur k 0, inutilisé.

### 4.4 Le récepteur des changements

`0x4001461c` (slot 17 de la vtable de `Sound`) recopie chaque changement dans une copie rangée par emplacements, avec
`0x4005aa54` (k ≤ 22, sinon emplacement 0) : pour k ≥ 23 il écrit l'emplacement 0, sans effet (k 0). La persistance
de nos paramètres repose donc sur la sauvegarde complète (kit, réserve de sons, copier-coller), comme l'Attack de
Model-TG, qui reste avec le projet. `[HYP]` à confirmer sur la machine (§10).

## 5. Le filtre

### 5.1 Lois

- Fréquence : index i = C pour le passe-bas (C < 0x4000), i = C − 0x4000 pour le passe-haut ;
  fc = 5 Hz × 4 400^(i / 16 384), plafonnée à 20 kHz (L1 : 19,3 kHz ; H63 : 19,3 kHz). Celle du Model:Samples.
- Résonance : Q = 0,5 × 100^(R′ / 32 512), de 0,5 à 50, avec R′ = R × réduction(i) : rien sous 10 Hz (pas de bosse
  subsonique, un défaut du Model:Samples), tout à 30 Hz, moins vers 20 kHz (1 − (fc / 24 000)^2,5). La bosse à fc
  (gain Q) monte d'environ 10 dB par quart de tour : +4 dB à 32, +14 dB à 64, +24 dB à 96, +34 dB à 127. La
  première version suivait le Model:Samples (Q 0,501 × (22,36 / 0,501)^(R′ / 32 512), +11 dB à 64, +27 dB à 127) :
  trop discrète à l'essai (§10.1).
- Enveloppe : e = 1 à la note (bit t de a3+16), puis e × exp(−1 / (1 500 τ)) par bloc, τ = 5 ms × 2 000^(D / 32 512) ;
  arrêtée sous 2⁻¹⁵. Décalage d'index = (A − 0x4000) × e, ajouté à i et borné au côté choisi (0..0x3fff) : la
  quantité monte ou baisse la fréquence, sans changer de côté.

Quatre tables de 65 points (Q31) calculées par le générateur et interpolées linéairement : G = tan(π fc / 48 000) / 4
(i = 256 j), réduction de la résonance (i = 256 j), K = 1 / (2Q) (R′ = 512 j), décroissance par bloc (D = 512 j).

### 5.2 Le SVF en espace d'état

SVF trapézoïdal (Zavalishin) écrit pour que tout se fasse dans les accumulateurs de l'EMAC :

```
ic1' = b1 ic1 + b2 (x − ic2)          b1 = 2 a1 − 1, b2 = 2 a2
ic2' = c2 ic2 + b2 ic1 + 2 a3 x        c2 = 1 − 2 a3
y    = gx x + hl (ic2 + ic2') + hb (ic1 + ic1')
a1 = 1 / (1 + g (g + k)), a2 = g a1, a3 = g a2, g = tan(π fc / fs), k = 1 / Q
LP : gx = 1 − w, hl = w / 2, hb = 0          HP = x − k BP − LP : gx = 1, hl = −w / 2, hb = −w k / 2
```

18 instructions par trame (11 `mac`/`msac`, 3 `movclr`). Les coefficients sont recalculés quand (C, R, décalage de
l'enveloppe) change, une fois par bloc au plus : 1 / (1 + g (g + k)) par normalisation et trois pas de Newton. Au
premier bloc filtré, le passe-bas part du niveau de l'entrée (pas de clic), le passe-haut du repos ; un bloc nul avec
un état retombé (< 2⁻¹⁹) ne coûte presque rien. Saturation par l'EMAC (MACSR 0xa0) : à Q 50 une sinusoïde à fc
monte de 34 dB, sans repli du signe (le défaut du Model:Samples). Les états (Q31) saturent aussi : sur un son fort à
forte résonance, le filtre écrête (il distord) au lieu de suivre le modèle linéaire, puis retombe au silence à la
vitesse de sa loi, sans oscillation entretenue (§8).

Au centre exact (C = 0x4000), la piste reste telle quelle et l'état est oublié ; l'enveloppe continue de tourner.

## 6. Place : quinze masques 35×35 `[FAIT]`

Dix-neuf sprites 35×35 ont des masques identiques de 280 o (35 colonnes opaques, `ff ff ff ff e0 00 00 00` par ligne).
On garde celui de `0x4014a660` ; `tools/sprites.py` les déclare (`SHARED_35`) et chaque masque utilisé est redirigé
(constante 32 bits du constructeur réécrite). Une section par masque, appels absolus de l'une à l'autre :

| Section | Masque | Octets | Contenu |
|---|---|---|---|
| `.tf_post` | `0x4014ab5c` | 152 | accroche H3, boucle des 6 pistes |
| `.tf_track` | `0x4014b85c` | 148 | enveloppe, clé des coefficients |
| `.tf_kern` | `0x4014d74c` | 164 | départ, repos, boucle des 32 trames |
| `.tf_coef1` | `0x401542f8` | 162 | index, G, résonance, K ; `tf_interp` |
| `.tf_coef2` | `0x401548b4` | 206 | réciproque, b1 b2 c2 a3, gx hl hb |
| `.tf_gtab` … `.tf_dtab` | `0x4015b8f8`, `0x4015f50c`, `0x401601fc`, `0x40160864` | 4 × 260 | tables |
| `.tf_kst` | `0x40160b6c` | 216 | état et coefficients, 6 × 36 o |
| `.tf_cst` | `0x40160e6c` | 256 | commande, 6 × 20 o, `tf_trig`, `tf_ptab` |
| `.tf_knob` | `0x401625bc` | 136 | `tf_knob`, `tf_objs` |
| `.tf_fmt` | `0x40163fb8` | 149 | `tf_fmt_cut`, chaînes |
| `.tf_save` | `0x4016616c` | 164 | `tf_save1/2`, `tf_save_post` |
| `.tf_load` | `0x40166760` | 208 | `tf_load`, `tf_conv`, `tf_boot` |

Encore libres : `0x40167c50`, `0x401696a0`, `0x401699a8`, `0x4016aa28`. L'état (`.data`) est écrit dans l'image avec
ses valeurs de départ : rien n'efface ces zones au démarrage.

## 7. Le tweak

Écritures (toutes avec leurs octets d'origine) : six accroches (`0x40059852` jsr tf_post, `0x4004486c` jsr tf_boot,
`0x4005aecc` / `0x4005afa0` / `0x4005b054` jmp, `0x4005aa34` jmp tf_conv), trois pointeurs (`0x401005a8`,
`0x4005b998`, `0x4005baca`), les descripteurs 1 à 4 (224 o à `0x4010dd18`), quinze redirections de sprites et le code.
40 écritures en tout.

`conflicts` : `model-tg`, `model-tg-st` (mêmes accroches de sauvegarde `0x4005aecc`, `0x4005afa0`, `0x4005b054`, même
geste ; les `syntakt-tg-*` demandent `model-tg-st`). Recouvrement vérifié octet par octet avec tous les tweaks du
dépôt et ceux des branches en cours (sample-preview, multiline-browser, chord-keys, level-pan-values,
trigless-dim) : aucun autre. Les masques 35×35 ne sont utilisés par aucun autre tweak.

## 8. Preuve en émulation

`tools/emu/test_track_filter.py`, sur le MAIN OS officiel, seul et avec
`--with 6ch-usbup,syntakt-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max,boot-anim,latching-mute,trig-preview,browser-scroll`
(`--syntakt Syntakt_OS1.42.syx`). Le son : la vraie boucle des voix puis le vrai site H3 (`0x4005984a..0x40059858`).

Chaque essai compare l'image avec le filtre à l'OS d'origine, sur le même motif (6 pistes, KICK SNARE METAL PERC
TONE CHORD, trois séries de notes aux blocs 1, 100 et 180) :

| Essai | Résultat |
|---|---|
| Centre (Filter Cutoff OFF), Volume + Dist 64 et 108, enveloppe et résonance réglées | les 6 pistes identiques bit pour bit à l'OS d'origine sur 240 blocs |
| Contrat de l'appel, à chaque bloc | d2-d7/a2-a6 gardés, `0x80001858` et a2 laissés sur la pile comme l'appel d'origine, MACSR rendu à 0x20, accumulateurs à zéro, aucun accès hors de la mémoire émulée |
| Six réglages fixes (LP 332 Hz, HP 332 Hz, LP près de 20 kHz, HP 41 Hz enveloppe −32, LP 116 Hz résonance 112 enveloppe +63, HP 5 Hz) | sortie comparée à un modèle flottant (SVF en double, mêmes lois) : écart max −111 à −167 dB sous la crête ; KICK et SNARE nettement changés |
| Balayage à chaque bloc, de LP à HP en passant par le centre | écart au modèle −110 à −120 dB sous la crête |
| Enveloppe, Decay 0 à 127 | relancée à chaque note (bit t de a3+16), τ de 5 ms à 10 s, écart à la loi < 10⁻⁷, décalage = quantité × enveloppe exactement |
| Résonance au maximum (Q 50) : signal plein échelle (carré, sinus à fc, bruit, impulsions, balayage, échelon) après Volume + Dist 108, puis silence ; LP 947 Hz et HP 2,7 kHz | contrat tenu, sortie saturée à 1 FS sans repli (LP : aucun saut de plus de 1,5 FS d'une trame à l'autre) ; après le signal, décroissance régulière à la vitesse de la loi (51,7 et 147,4 dB par 100 ms, à 3 % près) jusqu'à zéro exactement |
| Lois | 170 réglages, 5 Hz à 20 kHz des deux côtés, Q 0,5 à 50 : fréquence à 0,01 cent près, Q à 0,08 % près (tirés des coefficients calculés par le code) |
| Potards | MACHINES tenu : SWEEP, CONTOUR, COLOR, SHAPE → paramètres 1 à 4 ; les 8 autres potards et tout sans MACHINES : la recherche d'origine, mêmes arguments |
| Affichage (vrai constructeur, vrai `sprintf`) | les 128 pas : `L64` … `L1`, `OFF` au centre, `H1` … `H63`, trois caractères au plus ; Reso et Decay 0..127 ; Env −64..OFF..+63 ; l'image « Error » n'est plus dessinée |
| Tables construites au démarrage | descripteurs 1 à 4, k 28..31 sur les 6 machines, CC 74/71 sur les pistes 1 à 6, NRPN 1:20 et 1:21, rien d'autre ; un son neuf : Cutoff OFF, Reso 0, Env OFF, Decay 64, le reste comme sans le filtre |
| Sauvegarde du son, versions 2 et 1 | même enregistrement plus 7 octets (emplacements 18, 27, 30, 31) ; relu : valeurs, LFO → Filter Reso, vélocité → Filter Env ; un son d'avant le filtre se charge filtre OFF |
| P-locks du pattern | aller-retour complet et mise à jour d'un seul p-lock : tout revient (sur l'OS d'origine, 7 pistes de p-locks k ≥ 23 se perdaient ou changeaient de paramètre) ; p-locks d'origine : fichier identique octet pour octet |
| Avec les autres mods et le Syntakt | tous les essais ci-dessus refaits : mêmes résultats que seul (écarts au modèle identiques) ; descripteurs trouvés dans la table déplacée par les moteurs du Syntakt (`0x43034000`), k 28..31 et son initialisé sur les 11 machines |
| Avec MACRO (11/10/2026, après la fusion de main) | mêmes essais, mêmes résultats, avec `macro` (7 machines) puis `syntakt-sd-cp-toy-bits-swarm-macro` (12 machines), chacun avec `6ch-usbup`, `chord-keys`, `level-pan-values`, `trigless-dim`, `multiline-browser`, `midi-both` ou `midi-live-both`, `arp`, `trig-hold`, `tempo-max`, `boot-anim` et les trois de drumkilla ; k 28..31 et son initialisé sur toutes les machines |

## 9. Coût

Instructions exécutées dans le code du filtre, par bloc, 6 pistes ; part d'un bloc audio au modèle de la note 27
(1,54 cycle par instruction, 250 MHz, 166 667 cycles par bloc) :

| Cas | Instructions par bloc | Part d'un bloc |
|---|---|---|
| 6 pistes au centre (OFF) | 350 | 0,32 % |
| 1 piste filtrée, 5 au centre | 993 | 0,92 % |
| 6 pistes filtrées, réglages fixes | 4 208 | 3,9 % |
| 6 pistes filtrées, enveloppe en cours | 4 949 (max 5 114) | 4,7 % |
| 6 pistes filtrées, réglages changés à chaque bloc | 5 197 (max 5 220) | 4,8 % |
| 6 pistes filtrées, notes finies (Decay 10) | 3 983 | 3,7 % |

Une piste filtrée coûte 643 instructions de plus qu'au centre (0,6 % d'un bloc), jusqu'à 812 (0,75 %) quand les
coefficients sont recalculés à chaque bloc (enveloppe, LFO, potard qui tourne). Pour comparer, la charge lourde
mesurée en note 36 (moteurs Syntakt, Model-TG, régulateur) prend environ 44 % d'un bloc : six pistes filtrées et
modulées y ajoutent moins de 5 %, borne vérifiée par l'essai.

## 10. Sur la machine

### 10.1 Premier essai (10/10/2026)

Maxime, build « filtre seul » (MAIN OS `bf1f9fb3…`) : « c'est pas mal », mais :

- **Affichage** : en tournant à gauche, `LP8` puis de nouveau `LP1`, alors que le son continue de se fermer. Cause :
  l'écran ne montre que trois caractères (§3.3) ; `LP10` à `LP19` se lisaient `LP1`. Corrigé : `L64` … `OFF` …
  `H63`, comme Pan (`L64` … `R63`) ; la preuve vérifie les 128 pas.
- **Résonance** « qui ne s'entend pas beaucoup » : la loi du Model:Samples ne donne que +11 dB à mi-course. Passée
  à Q 0,5 à 50 (§5.1), environ 10 dB de plus par quart de tour. À réessayer : builds `-v2` envoyés le 11/10/2026
  (filtre seul : MAIN OS `f5db0133…` ; avec les autres mods : `f0d77915…`).

### 10.2 Second essai : testé sur la machine (11/10/2026)

Maxime, builds `-v2` : « ça marche nickel sur la machine ». Le mod passe de « expérimental » à « testé ».

### 10.3 Limites, et points à surveiller

- Le geste : MACHINES tenu + SWEEP / CONTOUR / COLOR / SHAPE, l'affichage (`L32`, `OFF`, `H20`…), le menu des
  machines qui s'ouvre toujours sur un appui seul.
- Le son : passe-bas, passe-haut, résonance (Q 50 près de fc : +34 dB ; sur un son fort, au-dessus de 100, la piste
  sature : à écouter, sinon une marge interne ou un Q plus bas), l'enveloppe à chaque note, le passage
  par le centre sans clic, un LFO qui balaie de LP à HP.
- La sauvegarde : son (kit), projet rechargé, réserve de sons, copier-coller d'un son, p-locks rechargés ; le
  récepteur des changements (§4.4) ne range pas k ≥ 23 : si un chemin de l'OS recharge un son depuis cette copie
  plutôt que par la sauvegarde complète, nos réglages y reviendraient à leur dernière sauvegarde. `[HYP]`
- Sur un `SoundConfigChangedInfo`, le même récepteur réécrit l'octet +94 de sa copie (destination de la vélocité)
  par la table bornée : pour nos destinations il y range un autre index. La sauvegarde complète le refait et range
  la nôtre en +83 ; `[HYP]` une vélocité vers FREQ survit donc aux mêmes chemins que nos réglages.
- Coefficients par bloc : une enveloppe ou un LFO très rapides à forte résonance avancent par marches de 0,67 ms.
- Un son relu sur l'OS d'origine (ou un autre firmware) perd son filtre, sans autre effet ; ses p-locks k ≥ 23 y
  tombent sur k 0, inutilisé.

## 11. Suite : Model-TG (étape 2)

Après le test de Maxime : retirer le filtre par piste de Model-TG (13 retouches de sa source dans
`tools/gen_model_tg.py`, déjà construites et vérifiées en émulation pendant l'étude ; Attack, le filtre du Sampler et
le filtre des effets master restent), puis faire tourner ce filtre avec Model-TG : côté stéréo du Sampler
(`sx_on`, `sx_side`), destinations 23..31 dans l'emplacement 27 partagé, accroches de sauvegarde chaînées. La
correction des p-locks (§4.3) répare alors aussi ceux de l'Attack de Model-TG.
