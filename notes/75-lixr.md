# 75 — Machine LiXR : une voix de percussion d'après les « drum voices » du LXR

Demande (fil du projet, 21/10/2026) : porter la « Multipurpose Drum Model » du LXR-02 en une machine du
Model:Cycles, avec quatre potards seulement (COLOR, SHAPE, SWEEP, CONTOUR), sans doubler PITCH ni DECAY, en restant
léger. Deux versions avaient été construites : LIXR avec un filtre, LIX2 avec un décimateur à la place du filtre.
Après écoute, **LIX2 est la version retenue** ; LIXR (le filtre) est retiré et la machine s'appelle **LiXR**.

## 0. En bref

| | État |
|---|---|
| Source LXR trouvée | `SonicPotions/LXR` (0.37, commit `dee4968`) et son portage LXR-02 `brendanclarke/LXR02Open` (commit `c896bfd`) ; le firmware LXR-02 d'Erica Synths est fermé |
| Modèle | `DrumVoice` (voix 1–3), pas de symbole « MultipurposeDrumModel » ; le manuel les appelle « drum voices » |
| Licence LXR | non commerciale, code source complet pour toute redistribution : incompatible avec la licence MIT du projet |
| Choix | **clean-room** : le source LXR sert de spécification ; code, tables et échantillons sont neufs, en virgule fixe |
| Machine | **LiXR**, 7e machine, sur l'OS d'origine uniquement (conflit avec tous les autres ajouts de machine) |
| Filtre | **aucun** : un décimateur (échantillonneur-bloqueur) le remplace, commandé par CONTOUR |
| Générateur | `tools/gen_lixr.py` ; sources `tools/machines/lixr/` ; tweak `36-lixr.json` |
| Preuve rapide | `tools/emu/test_lixr.py` (boucle des voix réelle, Unicorn) ; test hôte `tools/emu/lixr_host.c` |
| Coût mesuré (émulation) | 6,34–6,50 k instructions par bloc et par voix ; TONE 6,57 k, ACID 6,53 k ; voix muette 1,86 k |
| Mémoire | 5 296 o de code et tables, 576 o d'état pour 6 voix, +10 608 o dans l'image |
| Test matériel | **testé le 22/10/2026** sur un Model:Cycles, seule et avec SAMPLE, sur les images bâties à partir de ce paquet (commit `20db5b5`) ; rien n'a été flashé par l'assistant |

## 1. Ce qui a été trouvé, et ce qui manque

- Le firmware de la LXR-02 vendue par Erica Synths est **fermé**. Le seul code ouvert est le portage de la version
  Sonic Potions **0.37** sur le matériel LXR-02 (`brendanclarke/LXR02Open`). C'est ce code, et le manuel LXR, qui
  décrivent la voix utilisée ici.
- Le nom exact « Multipurpose Drum Model » n'existe pas dans le code : la classe est `DrumVoice` (`Core/DSPAudio/
  DrumVoice.c`), utilisée par les **voix 1 à 3**. Les autres voix (caisse claire, cymbale/clap, charley) sont des
  modèles séparés. Le manuel les appelle « drum voices » ; les revendeurs disent « multipurpose drum voices ».
- Le fichier `Hrtl_LXR-02_DLC.zip` trouvé dans les téléchargements ne contient que des kits et des patterns, pas de
  source. Il n'a pas été utilisé.
- Aucun ajout nommé **FMLLM** n'existe dans ce dépôt ni dans ses branches locales. Le modèle de départ est ACID
  (`tools/machines/acid/`, `tools/gen_acid.py`) et la mécanique commune `gen_macro.added_machine`.

## 2. Le modèle LXR (spécification, pas code repris)

Chaîne des voix 1–3 :

1. **Oscillateur principal** : sinus, triangle, scie, rectangle, bruit, cymbale ou sample ; accord fin/coarse.
2. **Oscillateur de modulation** : même famille d'ondes ; en mode MIX il est mélangé à l'oscillateur principal, en
   mode FM il le module en phase. Le paramètre « FM amount » est le dosage de mélange ou l'indice FM ; il suit
   l'enveloppe de hauteur.
3. **Générateur de transitoire** : deux modes de clic et douze échantillons courts (Snp, Ofs, Clk, Ck2, Tik, Kik,
   Rim, Drp, Hat, Clp, Kk2, Snr, Tom, Sp2), volume et vitesse de lecture ; ajouté avant le filtre.
4. **Filtre à variable d'état** : LP, HP, BP, BP unitaire, notch, peak, LP 2 pôles, off ; fréquence, résonance,
   type et drive d'entrée.
5. **VCA** : enveloppe de volume (attaque, décroissance, pente), vélocité, volume.
6. **Distorsion** douce `(1+s)x/(1+s|x|)`, forme 0…254.
7. **Réducteur de fréquence d'échantillonnage** : échantillonneur-bloqueur, taux 1…0.
8. **Pan, sortie, dither** ; **LFO** et **matrice de modulation** par voix.

Paramètres de la voix, 0…127 sauf mention :

| Groupe | Paramètres |
|---|---|
| Oscillateur | Coarse (demi-tons), Fine (±50 cents), Wave (Sin/Tri/Saw/Rec/Noi/Cym/samples) |
| Enveloppe d'ampli | Attack, Decay (0,67 ms…∞), Slope (exp…lin…log) |
| Enveloppe de hauteur | Decay, Slope, Amount (0…+5 octaves, `val²×32`) |
| Vélocité | Destination, Amount, Volume on/off |
| FM | Amount (0…1 ; mélange ou indice), Freq (note MIDI absolue, défaut 70), Wave, Mode MIX/FM |
| Transitoire | Wave (0…13), Volume (0…1), Freq (0,25…4×) |
| Filtre | Freq (0…0,45×fs, exponentiel), Reso (q 1…0,02), Type (8 choix), Drive (0,4…6,4) |
| Mixer | Volume, Pan, Sample rate (1…0), Drive (0…254), Output, Track length, MIDI channel, Note |
| LFO | Freq (0…200 Hz), Sync, Amount, Wave (8), Retrigger, Offset |

Le portage abandonne ce qui double le Cycles : Coarse/Fine (PITCH/FINE), Decay d'ampli (DECAY), Volume/Pan/Output
(mixer de l'OS), LFO et matrice de modulation (demande de l'utilisateur). Le filtre est remplacé par le décimateur,
version retenue à l'écoute.

## 3. Licence

La licence LXR (`SonicPotions/LXR/LICENSE.txt`, reprise par `LXR02Open`) permet la redistribution et les œuvres
dérivées à trois conditions : **pas de vente ni d'activité commerciale**, **code source complet** avec toute
redistribution modifiée, et reproduction de la notice. Ce n'est ni MIT ni une licence OSI. Un portage littéral
imposerait donc ces termes à l'ajout, et le projet ne pourrait pas le distribuer sous MIT ; `CONTRIBUTING.md`
n'accepte que MIT/BSD/ISC/0BSD.

Le code LXR est de plus écrit en **float** pour un Cortex-M4F/M7 avec FPU ; le ColdFire MCF54415 n'en a pas. Un
portage littéral ne serait pas utilisable.

Décision : **clean-room**. Le source LXR et le manuel donnent la structure, les plages et le comportement ; le code
ColdFire, les tables et le bruit sont écrits ici, en virgule fixe, sans copier une ligne, un tableau ni un
échantillon. Crédit à Julian Schmidt / Sonic Potions et à Brendan Clarke dans
`PROVENANCE.md` ; licence MIT du projet.

## 4. La machine LiXR

- **COLOR** : **bipolaire** autour du milieu (64). À gauche, triangle → sinus et aucun bruit ; au centre, triangle
  propre ; à droite, triangle → scie → rectangle, avec du bruit seulement au-delà de 0,65, jusqu'à 0,31 (au lieu de
  0,75), encore réduit de moitié quand SHAPE est au maximum. Un transitoire court (1 à 3 impulsions, 10…80 ms) et le
  clap restent dans le dernier quart. Le bruit ne monte donc plus fort d'un coup, et il baisse quand SHAPE monte.
  Le niveau de l'oscillateur principal ne descend pas sous 0,625 : aucun potard ne coupe le son.
- **SHAPE** : retour FM (feedback FM) borné sur l'oscillateur unique. L'indice suit une **loi carrée** et plafonne à
  **un quart de cycle** de déphasage (0,0625 au milieu de la course, 0,25 au maximum), au lieu de 1 cycle linéaire
  dans la version précédente : au-delà de la moitié, le potard reste utilisable et ne part plus dans le bruit. C'est
  le compromis qui remplace le second oscillateur et le rapport FM de la première version : un seul produit par
  échantillon, sans deuxième oscillateur.
- **Hauteur** : tout le moteur est transposé **une octave plus bas** (PITCH − 12 demi-tons) ; la note est bornée à
  0. Le blocage DC est descendu de 60 Hz à 7,5 Hz (`dcy - dcy >> 10`) : le fondamental des notes graves n'est plus
  coupé, et le niveau ne chute plus quand on descend. Une compensation de grave par note a été essayée puis retirée
  (trop de CPU) ; la coupure DC corrige la cause. La sortie est à 1,375× pour garder le niveau d'ensemble.
- **SWEEP** : profondeur de l'enveloppe de hauteur 0…4 octaves (`x²`) et temps 5…150 ms (`x^1,5`), pente
  exponentielle fixe. À 0, aucune modulation de hauteur.
- **Rate** (le potard CONTOUR) : décimation 1×…32×, loi `2^(5x)`, échantillonneur-bloqueur après la voix. À 0,
  aucun décimateur ; à 1, environ 1,5 kHz de fréquence effective. Le taux ne descend jamais à zéro. Comme le filtre
  est absent, aucun réglage ne peut rendre le filtre instable ; un mélange sec n'est pas nécessaire.
- **DECAY, GATE, PITCH, FINE, PUNCH** : ceux de l'OS. Le fondu d'entrée interne fait 32 échantillons (0,67 ms) et
  ne double pas DECAY ; la décroissance reste celle de la chaîne d'ampli d'origine.

### 4.1 Comparaison avec le LXR

Dans `calcDrumVoiceSyncBlock`, le LXR calcule l'oscillateur de modulation avec un gain `fmModAmount`, puis, en mode
FM, `calcNextOscSampleFmBlock` multiplie encore le tampon par `osc->fmMod` (= `fmModAmount × egPitchVal`). L'indice
est donc **quadratique** en `fmModAmount`, plafonné à environ **un quart de cycle** de déphasage, et il est réduit
par l'enveloppe de hauteur. La version LiXR précédente utilisait un feedback **linéaire jusqu'à un cycle complet**,
d'où le côté inutilisable au-delà de la moitié de SHAPE. La version actuelle garde un feedback (pour le CPU) mais
applique la même loi carrée et le même plafond d'un quart de cycle. Le LXR passe aussi son bruit dans son filtre SVF ;
LiXR n'a plus de filtre, donc le bruit de COLOR est dosé plus bas (0,31 au lieu de 0,75) et réduit de moitié quand
SHAPE monte.

## 5. Code et tables

- `tools/machines/lixr/lixr_dsp.h` : cœur, virgule fixe Q28 (1,0 = 2^28), hauteurs en demi-tons << 16. EMAC en
  mode fractionnaire signé saturé, ACC0 vidé (`qmul`). Un seul oscillateur, sans table d'onde : triangle, scie et
  rectangle sont calculés depuis la phase ; le feedback FM utilise la sortie précédente.
- `tools/machines/lixr/lixr.c` : passerelle OS. Même contrat que `acid.c` : `update(pmod, v, p)` puis
  `render(out, v)`, chaîne d'ampli d'origine (`AMP_ENV`, `VCA`, `PUNCH`), marqueur `LXR1` en `v+0x2c`, voix muette
  non calculée.
- `tools/machines/lixr/lixr_tables.h` : pas de tables d'ondes ; pas de hauteur, lois d'enveloppe de hauteur, de
  transitoire, de feedback FM et de décimateur, table de saturation de 129 points. Calculé par
  `tools/gen_lixr.py`.
- Bruit : LFSR 1664525/1013904223, jamais remis à zéro par un trig ; transitoire à 0/6/12/18 ms, les trois
  dernières impulsions dosées par COLOR (clap).
- Saturation : table de 129 points de `a − 0,213333 a³` (maximum 0,7867), puis blocage DC à 7,5 Hz, fondu de 32
  échantillons et écrêtage de sûreté à 0,875. Sortie 1,375× (deux décalages) pour compenser le bruit réduit et
  garder une marge avant la chaîne d'ampli.
- Décimateur : accumulateur Q16 et échantillon tenu ; aucune rétroaction, aucune division dans la boucle.
- Aucune division dans la boucle par échantillon ; l'état chaud (phase, bruit, enveloppes, décimateur, DC, fondu)
  reste dans des variables locales pendant les 32 échantillons, puis est recopié dans la voix.

## 6. Construction

```sh
export PATH=/chemin/vers/m68k-elf-16.2/bin:$PATH
python3 tools/gen_lixr.py --cycles firmware/model-cycles_OS1.13.syx
python3 tools/gen_lixr.py --cycles firmware/model-cycles_OS1.13.syx --check
python3 tools/build.py -i firmware/model-cycles_OS1.13.syx -t lixr -o build/lixr.syx
```

Le tweak est seul sur l'OS d'origine : il conflit avec `model-tg`, `macro`, `acid` et toutes les versions des
moteurs du Syntakt (même charge utile et même crochet de démarrage). MAIN OS construit ici :
`304356a94ef96cf5aaf097a2cdd9fd7fa5461e1075ca6772d394c19b5c7489f8`.

## 7. Coût mesuré

Instructions par bloc de 32 échantillons, une voix, boucle des voix réelle (Unicorn), autres voix hors limites :

| Voix | Instructions / bloc | Rapport à TONE |
|---|---:|---:|
| TONE | 6 572 | 1,00 |
| ACID | 6 532 | 0,99 |
| LiXR | 6 335…6 499 | 0,96…0,99 |
| LiXR muette | 1 858 | 0,28 |

État : 576 o pour 6 voix (96 o/voix). Code et tables : 5 296 o. Ajout à l'image : 10 608 o. La voix muette est
sautée ; une piste LiXR coûte donc un peu moins qu'une piste TONE quand elle joue, et presque rien quand elle est
muette. Le prix de ce coût : un seul oscillateur avec feedback FM au lieu de deux oscillateurs et du rapport FM, et
un morph triangle/scie/rectangle sans tables au lieu de quatre tables d'ondes ; le filtre était déjà remplacé par le
décimateur.

## 8. Vérifications faites ici

- Compilation croisée `m68k-elf-gcc` 16.2.0 / binutils 2.47, `--check` du générateur.
- `tools/emu/test_lixr.py` : la boucle des voix réelle démarre, LiXR sonne par la chaîne d'ampli, aucun accès non
  mappé, pas d'écrêtage dur, KICK d'origine intact.
- `tools/emu/lixr_host.c` : 81 combinaisons (COLOR/SHAPE/SWEEP/CONTOUR aux trois extrémités, 0,5 s), crête
  0,495…0,788 de la pleine échelle, aucun NaN, aucun échantillon nul, décalage DC max 0,0029.
- **Non vérifié** : la machine réelle, le rendu complet du séquenceur, la charge sur le ColdFire, l'écran MACHINES.
  Maxime fait le test émulateur complet et le test matériel.

## 9. Limites

- Une seule machine sur l'OS d'origine ; pas de version avec Model-TG, MACRO, ACID ou les moteurs du Syntakt.
- Le nom LXR n'est pas affiché sur la machine (LiXR) ; le crédit est dans la documentation.
- Le second oscillateur et son rapport FM ont disparu pour tenir le budget CPU : SHAPE est un feedback FM, plus
  rugueux qu'un FM à deux oscillateurs. Le morph d'onde est triangle/scie/rectangle, sans sinus ni tables d'ondes.
- Le décimateur n'a pas de filtre anti-repliement : c'est l'effet recherché du moteur retenu.
