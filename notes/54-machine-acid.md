# 54 — Machine ACID : une basse acide à la manière de la TB-303

Demande de Maxime (fil du projet, 10/10/2026) : « Je veux que tu crée un engine qui de TB303, garde le intuitif et
avec les parametre les plus utile ». Tweaks `26-acid.json` (seul) et `35-acid-tg.json` (avec Model-TG), générateur
`tools/gen_acid.py`, sources `tools/machines/acid/` (`acid_dsp.h` le cœur, `acid.c` la passerelle), preuve
`tools/emu/test_acid.py` (référence `tools/emu/acid_ref.c`, banc du séquenceur `tools/emu/seqrig.py`). Adresses : VA de
l'OS 1.13.

## En bref

- **Une machine ajoutée, ACID**, après Chord (après le Sampler avec Model-TG), avec la mécanique de MACRO
  ([43](43-machine-macro.md)) : même place, mêmes détours. Elle exclut donc MACRO et les moteurs du Syntakt.
- **Les réglages d'une 303, sur les potards du Cycles** : COLOR = CUTOFF, SHAPE = RESO, SWEEP = ENV MOD, CONTOUR =
  ACCENT, DECAY = DECAY (enveloppe du filtre, et la décroissance de l'ampli), PUNCH = forme d'onde (éteint : scie,
  allumé : carré). PITCH, FINE, GATE, les touches et le clavier comme sur les autres machines.
- **L'accent et le slide viennent du séquenceur, sans le modifier** :
  - accent = la vélocité du trig (VEL dans le menu du trig, ou un pad frappé fort) : 100 (le défaut) et moins, pas
    d'accent ; 127, tout l'ACCENT ; entre les deux, une part ;
  - slide = la longueur du trig (LEN) : un trig plus long que l'écart au trig suivant (1.06, 1/8… ou INF) glisse
    vers la note suivante au lieu de la rejouer ; avec LEN 1/16 sur des pas voisins (le défaut), chaque note est
    rejouée. En jeu live, une touche jouée pendant qu'une autre est tenue glisse. Un trig sans note (trigless) avec
    un verrou NOTE glisse aussi.
- **Le son est un modèle de la TB-303 : celui d'Open303** (Robin Schmidt, licence MIT) : filtre « TB_303 » à 4 pôles
  et ses approximations mesurées, enveloppe du filtre, accent (intégrateur, +4 × l'enveloppe sur l'amplitude),
  slide de 50 ms. Réécrit en virgule fixe pour le ColdFire (pas de FPU), à 48 kHz, oscillateur à bords adoucis.
- **Prouvé en émulation** `[FAIT en émulation]` : la sortie avant la chaîne d'ampli est, échantillon par échantillon,
  celle du même cœur compilé pour l'ordinateur, y compris quand le vrai séquenceur de l'OS joue (accent, slide,
  LEN, jeu live, verrous) ; les machines d'origine ne changent pas.
- **Charge** : une voix ACID coûte un peu moins qu'une voix TONE (§8). Une voix muette n'est pas calculée.
- **Expérimental** : pas encore joué sur la machine (§10).

## 1. Le modèle : Open303

Open303 (`RobinSchmidt/Open303`, commit `313bf0d9`, 29/03/2024, MIT) est un émulateur libre de la TB-303 dont les
constantes ont été mesurées sur une vraie 303 (courbes de cutoff, de résonance, d'ENV MOD et des enveloppes). On en
reprend le modèle, pas le code (il calcule en double et suréchantillonne) :

| Partie | Open303 | ACID |
|---|---|---|
| Oscillateur | scie ; carré = `-tanh(70 × scie + 4,37)` (SQUARE303) | scie, ou carré haut sur 46,9 % du cycle (le même rapport), bords adoucis (polyBLEP) |
| Filtre | « TB_303 » (mystran et kunn) : 4 étages à un pôle, `b0` et `k` d'après des polynômes en `fc`, gain `g = ((k/17 − 1) r + 1)(1 + r)`, passe-haut de 150 Hz dans la contre-réaction, passe-haut de 44,5 Hz en entrée | les mêmes formules ; `b0` et `k` en table (1/16 d'octave de 200 Hz à 16,6 kHz) puis interpolés à chaque échantillon |
| CUTOFF | 313,8 à 2 394 Hz, exponentiel | idem |
| RESO | courbe « skewée » `(1 − e^(−3x)) / (1 − e^(−3))` | idem, table de 17 points |
| ENV MOD | échelle et décalage de l'enveloppe du filtre qui dépendent de CUTOFF (droites mesurées) | idem |
| DECAY | enveloppe du filtre de 200 ms à 2 s ; 200 ms pour une note accentuée | idem, multiplicateur par bloc |
| ACCENT | intégrateur de 15 ms de l'enveloppe (`rc2`), qui monte le cutoff, et amplitude × (1 + 0,45 env + 4 × accent × env) | idem |
| Slide | la hauteur suit la note avec une constante de 21,7 ms (90 % en 50 ms), sans relancer l'enveloppe | idem ; la note ne glisse que vers celle du trig, PITCH et FINE agissent tout de suite |
| Ampli | enveloppe propre (1,23 s) | la chaîne d'ampli de l'OS, comme TONE : DECAY et GATE (§3.1) |

À 48 kHz sans suréchantillonnage, le filtre reste stable jusqu'à 16,6 kHz (le haut de la table, vérifié sur toute la
course des potards) ; un CUTOFF au maximum avec ENV MOD et accent au maximum y plafonne.

## 2. Ce que l'OS donne à une machine `[FAIT en émulation]`

Établi avec le banc du séquenceur (`tools/emu/seqrig.py`) : la vraie interruption audio (`0x40058ca0..0x40059382`),
le vrai constructeur des pas du séquenceur (`0x400548ce`) sur un pattern factice, les notes live (`0x4005894a`), puis
`0x4005979e` (paramètres, LFO, boucle des voix, gain de vélocité). À 30, 120, 300 et 546 BPM, trig à différents
instants du bloc, avec micro-décalage.

| Où | Quoi |
|---|---|
| `0x40fe4cdc` + 2 × piste | vélocité du dernier trig, `<< 8` (1..127) : écrite avant la boucle des voix, au bloc du trig (`voix + 0x34`) ; elle reste jusqu'au trig suivant ; un trigless ne la change pas. Défaut d'un pas : 100 (`0x40061418`) |
| `0x40fe4c90` / `0x40fe4cd0` + 2 × piste | gain de vélocité (0..127) : `0x40056d9c` multiplie la sortie de chaque voix par `gain / 127` juste après la boucle des voix, puis `0x40059840` recopie `0x40fe4cd0` (écrit au trig) dans `0x40fe4c90` : le nouveau gain s'applique au bloc qui suit le trig, d'un coup. Avec le son par défaut, `gain = vel` (`127 − d + vel × d / 127`, `d = son + 96` = 127) |
| `0x800017b4` + 4 × piste | reste de la longueur du trig (LEN) : `0x4010d814[LEN + 1]` au trig (1/16 = 2 700 000, INF = 0 : pas de fin) ; chaque bloc lui retire `0x40149310` (BPM × 120) ; à 0, fin de note |
| `release_mask` → `voix + 0x3c` | fin de note, un bloc : `(décomptes écoulés & ~trigs) | relâchements live de la note en cours`. Avec GATE éteint, elle arrive quand même |
| Trig suivant avant la fin | la fin de la note précédente n'est jamais donnée : le trig suivant remplace le décompte ; s'il tombe dans le bloc où le décompte s'écoule, `~trigs` la masque. Avec une LEN égale à l'écart des trigs, pas de fin non plus |
| Jeu live | appui = trig ; un 2e appui pendant que le 1er est tenu = trig sans fin ; relâcher le 1er : rien ; relâcher le 2e : fin. Appui et relâché dans le même bloc : `+0x34` et `+0x3c` ensemble ; les notes live ont un décompte nul |
| `0x80001830` + 4 × piste (`pmod`) | note du trig `<< 16` ; un trigless avec un verrou NOTE la change sans trig ni fin |
| Boucle des voix `0x400a7d4a` | pour chaque voix : `+0x34` (trig) et `+0x3c` (fin) posés ; si `+0x38` (trig au bloc précédent) : changement de machine éventuel (paramètre MACHINE, remise à zéro `0x400a7ab8`) ; `+0x24c` = GATE ; `0x400a7d16` efface des champs de la voix si `+0x38` ; `update`, `render` ; puis `+0x38 = +0x34` |

Ce que le séquenceur sait de l'accent et du slide d'une 303 : rien en propre (ni bit, ni paramètre). Les trigs
conditionnels et la probabilité sont tranchés avant l'événement ; les retrigs sont des trigs comme les autres.
Model-TG a des « slide trigs » ([31 §9](31-model-tg.md)), mais par des crochets dans le séquenceur qui sont les siens,
et ils font glisser les paramètres, pas la note.

## 3. La passerelle (`acid.c`)

### 3.1 Potards

| Potard du Cycles | Nom affiché | Ce que reçoit le cœur |
|---|---|---|
| PITCH, FINE | — | accord : PITCH − 64 + FINE (±2 demi-tons), ajouté à la note sans glisser |
| touches, trigs | — | la note du trig (`pmod`), 0..127, 440 Hz à 69 ; c'est elle qui glisse |
| COLOR | Cutoff (CUT), défaut 40 | CUTOFF |
| SHAPE | Reso (RES), défaut 90 | RESONANCE |
| SWEEP | Env Mod (ENV), défaut 80 | ENV MOD |
| CONTOUR | Accent (ACC), défaut 80 | ACCENT : sa force, la vélocité dit quelles notes |
| DECAY | (commun), défaut 50 | DECAY de l'enveloppe du filtre, et décroissance de l'ampli (la table de TONE `0x4011d84c`) |
| PUNCH | (commun) | forme d'onde : éteint scie, allumé carré ; le PUNCH de l'OS est réglé éteint |
| GATE | (commun) | la chaîne d'ampli d'origine : la note tient tant que le trig dure, puis décroît avec DECAY |

Un potard 8.8 de 0..127 devient 0..32 766 (`x + (x >> 7)`). L'image de la machine est celle de TONE. Les réglages par
défaut (CUTOFF bas, beaucoup de résonance et d'ENV MOD) donnent tout de suite le « wow » acide ; GATE allumé donne la
tenue d'une 303 (la note sonne toute sa longueur).

### 3.2 Accent

À chaque trig, la passerelle lit la vélocité (`0x40fe4cdc`) : `accent = ACCENT × (vel − 100) / 27`, 0 sous 100.
Au premier trig sur la machine (l'OS appelle encore l'ancienne au bloc du trig, ACID ne voit que le bloc suivant),
elle la lit au bloc suivant : la vélocité est toujours là. Le gain de vélocité de l'OS reste appliqué : une note à
127 sonne aussi 2 dB plus fort qu'une note à 100, ce qui va dans le sens de l'accent.

### 3.3 Slide

Par piste : `held` (une note joue et n'a pas été relâchée : mis au trig, effacé par `+0x3c`), `left` (le reste de
longueur lu au bloc précédent : au bloc du trig, `0x800017b4` porte déjà la longueur du nouveau). Un trig glisse si

```
held && voix pas muette && (left == 0 || left > 2 × 0x40149310) && MACHINE inchangée
```

- `left > 2 pas du décompte` : la note précédente dure au-delà de ce trig. Mesuré avec le vrai séquenceur : une LEN
  égale à l'écart des trigs laisse 0,21 à 1,5 pas au bloc d'avant (jamais 2), LEN 1.06 en laisse 2,8 (546 BPM) à
  48 (30 BPM) ; LEN .938 s'est déjà écoulée (fin de note : `held` effacé).
- `left == 0` avec `held` : une note INF, ou une touche tenue en live.
- MACHINE (`p + 0x12`, valeur brute) égale à celle qui a choisi ACID : un trig verrouillé sur une autre machine est
  rejoué, pour que l'OS change de machine au bloc suivant.

Un trig lié est caché à l'OS : la passerelle efface `voix + 0x34` dans `update`. Le VCA ne fond pas la voix (il le
fait au bloc d'un trig), le bloc suivant n'a pas `+0x38` : l'enveloppe d'ampli continue (tenue avec GATE, sa
décroissance sinon), pas de remise à zéro par `0x400a7d16`. Le cœur reçoit ce même bloc la nouvelle note (qui glisse)
et l'accent de la note, sans relancer l'enveloppe du filtre (comme `slideToNote` d'Open303).

Le gain de vélocité sauterait au bloc suivant (de 100 à 127 vers une note accentuée : une marche de 2 dB au milieu
d'une onde, un clic) : la passerelle remet dans `0x40fe4cd0` le gain en cours, puis le rapproche de celui de la
nouvelle note de 1/127 par bloc (0,07 dB, 18 ms pour 100 → 127). Un trig rejoué arrête cette rampe (l'OS a écrit son
gain).

Limites : un trig rejoué juste après un appui et relâché dans le même bloc qui a choisi la machine (le tout premier
trig sur ACID, de longueur nulle) compterait comme tenu ; seule une note MIDI de longueur nulle peut faire ça. Un
trigless avec un verrou NOTE glisse toujours (la hauteur suit la note du trig), même si la note précédente est
finie : il n'y a rien à entendre alors.

### 3.4 État, voix muette

- Une voix d'ACID par piste (`acid_t`, 68 o) et l'état de la passerelle (132 o en tout par piste), dans le BSS de la
  charge utile, mis à zéro au démarrage.
- Repère `'ACD1'` en `voix + 0x2c`, effacé par la remise à zéro de la voix à chaque changement de machine : la
  première note y lit le paramètre MACHINE, la vélocité, et marque la voix muette (remise à zéro au premier trig).
- **Voix muette non calculée** : sans trig ni slide et avec l'enveloppe d'ampli sous 2^14 (−102 dB), sortie nulle ;
  au trig suivant, phase et filtres à zéro (comme Open303 quand la voix s'est tue). Sinon le filtre continue d'une
  note à l'autre, comme sur la 303.

## 4. Le cœur en virgule fixe (`acid_dsp.h`)

- Signaux : 1,0 = 2^28 (l'oscillateur fait ±2^25) ; coefficients Q31 ; hauteurs en demi-tons `<< 16` ; tout passe par
  l'EMAC en mode fractionnaire signé saturé (`MACSR = 0xa0` pendant la boucle des voix) : `mac.l` + `movclr.l`, ACC0
  rendu vide.
- Par bloc : enveloppe du filtre, accent, hauteur (slide), coupure en 1/16 d'octave, `b0`, `k`, gain (avec
  l'amplitude d'Open303). Par échantillon : coefficients interpolés de la fin du bloc précédent à la fin de celui-ci,
  oscillateur, passe-haut d'entrée, contre-réaction et son passe-haut, 4 étages.
- Sortie : 1,0 du modèle = 4 × la pleine échelle, linéaire jusqu'à la moitié de la pleine échelle puis un coude qui
  l'atteint en douceur (`acid_out`) : les accents les plus forts saturent un peu au lieu d'écrêter. Avec les réglages
  par défaut, une note sans accent sort à ~0,4 de la pleine échelle avant la chaîne d'ampli, comme TONE après elle.
- Le même fichier est compilé pour le Cycles (`acid.c`) et pour l'ordinateur (`acid_ref.c`, l'EMAC reproduite :
  chaque produit tronqué à 2^−39, somme, décalage de 31 et saturation) : la preuve les compare à l'échantillon près.
- Tables (`acid_tables.h`, 1,9 Ko) calculées par `gen_acid.py` d'après les constantes d'Open303.

## 5. Place

| | Seul (`acid`) | Avec Model-TG (`acid-tg`) |
|---|---|---|
| Charge utile au démarrage | `0x43000000`, comme MACRO | `0x46700000` |
| Code et tables d'ACID et de la passerelle | 6 304 o à `+0` | idem |
| Détours, données, descripteurs, rangées, enregistrements | `+0x33000..0x36000` (`gs.LAYOUT`) | idem |
| Variables (6 voix) | 792 o à `+0x36000` | idem |
| Ajouté à l'image (morceaux tassés) | 11 616 o | 12 028 o |
| Fin de l'image décompressée (limite `0x40200000`) | `0x401acea0` | `0x401c27bc` |
| Crochet de démarrage | masque `0x4016cae8` (104 o), comme MACRO | 96 o, chaîné à `boot_extra_hook` |

Aucun masque libre de plus : `REGISTRY.md` (notes/52) range ACID avec MACRO dans le masque `0x4016cae8` et, seul,
l'envoi USB à heure fixe dans `0x4015c044`. `gen_macro.py` a été découpé (`added_machine`) pour que les deux machines
partagent la mécanique ; les octets de MACRO n'ont pas changé (`gen_macro.py --check`).

## 6. Le tweak et sa licence

- `26-acid.json` : 122 écritures, plus l'envoi à l'USB à heure fixe ([35](35-glitches-usb-multipiste.md)) et la boucle
  des voix de [36](36-regulateur-sans-coupures-inutiles.md), comme MACRO seule.
- `35-acid-tg.json` : 114 écritures, `requires` `model-tg-st`.
- Compilé avec `m68k-linux-gnu-gcc` 13.3 (Ubuntu 24.04) ; un autre GCC donne d'autres octets (`--check` le dit).
  Aucun octet Elektron dans les JSON (table des descripteurs recopiée au build, recette `cycles`).
- Licence MIT d'Open303 : `tweaks/model-cycles_OS1.13/LICENSE-Open303` (copiée en `docs/flasher/LICENSE-Open303.txt`).
  Le code d'ACID est le nôtre ; le modèle et ses constantes viennent d'Open303 : crédit à Robin Schmidt sur la carte,
  dans le guide et le README. La machine s'appelle ACID (ni « TB-303 » ni Roland sur la machine).

## 7. Incompatibilités

- **MACRO, moteurs du Syntakt** (seuls ou avec Model-TG), **SD VINTAGE** : même mécanique de machines ajoutées, même
  place et même crochet de démarrage. Le flasher rend la carte ACID exclusive de MACRO et des moteurs (`excludes`).
  Une version combinée (comme [50](50-macro-avec-moteurs-syntakt.md)) reste possible plus tard.
- Avec Model-TG cochée, le flasher prend `model-tg-st` + `acid-tg` (son `with`).
- Avec les autres mods du flasher : aucune écriture ne se chevauche (`tools/check_overlaps.py`).

## 8. Charge

Instructions par bloc de 32 trames d'une voix, mesurées dans la vraie boucle des voix (la boucle entière moins la
même sans voix) : voir le tableau de §9, ligne « Coût ». Pas de régulateur de charge : ACID coûte moins que TONE.

## 9. Preuve en émulation `[FAIT en émulation]`

`tools/emu/test_acid.py` : le vrai code de l'OS (Unicorn), avec la charge utile telle que le crochet la reconstitue.
La référence est le même cœur compilé pour l'ordinateur (`acid_ref.c`), piloté bloc par bloc avec les réglages que la
passerelle doit lui donner, calculés par le test d'après cette note (classe `Bridge`) ; le test vérifie aussi ce que
la passerelle écrit dans l'OS (`voix + 0x34`, `0x40fe4cd0`).

Résultats : §9.1 (rempli à la fin de la preuve).

## 10. À vérifier sur la machine

- Le son : CUTOFF, RESO, ENV MOD, DECAY, ACCENT sur toute leur course ; scie et carré (PUNCH) ; niveau à côté des
  autres machines ; les accents forts (VEL 127, ACCENT 127, RESO haute) saturent un peu, sans craquer.
- Accent : un pas à VEL 127 (menu du trig) sonne plus brillant et plus fort ; à 100, rien.
- Slide : LEN 1.06 (ou plus) sur un pas, la note suivante glisse, sans clic ; LEN 1/16, chaque note est rejouée.
  INF ; un pad tenu en live pendant qu'on en joue un autre. Avec GATE allumé, l'ampli tient à travers le slide.
- Avec Model-TG : la même chose sur la 8e machine.
