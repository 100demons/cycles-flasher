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
  DRIVE (saturation, §3.2), DECAY = DECAY (enveloppe du filtre, et la décroissance de l'ampli), PUNCH = forme d'onde
  (éteint : scie, allumé : carré). PITCH, FINE, GATE, les touches et le clavier comme sur les autres machines.
- **Le slide vient du séquenceur, sans le modifier** : un trig plus long (LEN) que l'écart au trig suivant (1.06,
  1/8… ou INF) glisse vers la note suivante au lieu de la rejouer ; avec LEN 1/16 sur des pas voisins (le défaut),
  chaque note est rejouée. En jeu live, une touche jouée pendant qu'une autre est tenue glisse. Un trig sans note
  (trigless) avec un verrou NOTE glisse aussi.
- **Le son est un modèle de la TB-303 : celui d'Open303** (Robin Schmidt, licence MIT) : filtre « TB_303 » à 4 pôles
  et ses approximations mesurées, enveloppe du filtre, slide de 50 ms. Réécrit en virgule fixe pour le ColdFire (pas
  de FPU), à 48 kHz, oscillateur à bords adoucis. Puis une saturation, la nôtre (§3.2).
- **Pas d'accent** : la première version avait celui d'Open303 (CONTOUR = sa force, la vélocité au-dessus de 100 =
  les notes accentuées) ; Maxime ne l'entendait pas et ne le trouvait pas utile ici (§10) : remplacé par DRIVE. La
  vélocité règle le volume, par l'OS, comme sur les machines d'origine.
- **Prouvé en émulation** `[FAIT en émulation]` : la sortie avant la chaîne d'ampli est, échantillon par échantillon,
  celle du même cœur compilé pour l'ordinateur, y compris quand le vrai séquenceur de l'OS joue (slide, LEN,
  vélocité, verrous, jeu live) ; les machines d'origine ne changent pas.
- **Charge** : une voix ACID coûte un peu moins qu'une voix TONE (§8). Une voix muette n'est pas calculée.
- **Expérimental** : la première version (avec l'accent) a bien joué sur la machine le 11/10/2026 ; DRIVE pas encore
  (§10).

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
| DECAY | enveloppe du filtre de 200 ms à 2 s ; 200 ms pour une note accentuée | idem, multiplicateur par bloc (pas d'accent) |
| ACCENT | intégrateur de 15 ms de l'enveloppe (`rc2`), qui monte le cutoff, et amplitude × (1 + 0,45 env + 4 × accent × env) | retiré (§3.2) : amplitude × (1 + 0,45 env) |
| Slide | la hauteur suit la note avec une constante de 21,7 ms (90 % en 50 ms), sans relancer l'enveloppe | idem ; la note ne glisse que vers celle du trig, PITCH et FINE agissent tout de suite |
| Ampli | enveloppe propre (1,23 s) | la chaîne d'ampli de l'OS, comme TONE : DECAY et GATE (§3.1) |

À 48 kHz sans suréchantillonnage, le filtre reste stable jusqu'à 16,6 kHz (le haut de la table, vérifié sur toute la
course des potards) ; un CUTOFF au maximum avec ENV MOD au maximum y plafonne.

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
| CONTOUR | Drive (DRV), défaut 0 | DRIVE : la saturation (§3.2) |
| DECAY | (commun), défaut 50 | DECAY de l'enveloppe du filtre, et décroissance de l'ampli (la table de TONE `0x4011d84c`) |
| PUNCH | (commun) | forme d'onde : éteint scie, allumé carré ; le PUNCH de l'OS est réglé éteint |
| GATE | (commun) | la chaîne d'ampli d'origine : la note tient tant que le trig dure, puis décroît avec DECAY |

Un potard 8.8 de 0..127 devient 0..32 766 (`x + (x >> 7)`). L'image de la machine est celle de TONE. Les réglages par
défaut (CUTOFF bas, beaucoup de résonance et d'ENV MOD) donnent tout de suite le « wow » acide ; GATE allumé donne la
tenue d'une 303 (la note sonne toute sa longueur).

### 3.2 DRIVE (la saturation), à la place de l'accent

La première version avait l'accent d'Open303 sur CONTOUR : à chaque trig, `accent = ACCENT × (vel − 100) / 27`, 0 sous
100. Maxime, sur la machine (11/10/2026) : « ça marche bien. Par contre j'ai l'impression que accent ne change rien du
tout, et il est pas vraiment utile dans notre cas même s'il marchait donc remplace le par autre chose d'utile ». Cause
probable `[HYP]` : un pas a une VEL de 100 par défaut, donc sans monter la VEL pas par pas, aucune note n'était
accentuée et CONTOUR ne faisait rien. Remplacé par **DRIVE** : il agit sur tout le son sans réglage de pas, le Cycles
n'a pas d'autre distorsion, et une ligne acide passe presque toujours par une pédale de distorsion. La vélocité ne
touche plus au son de la machine : seul le gain de vélocité de l'OS (le volume) reste, comme sur les autres machines.

La saturation est dans le cœur, après le filtre, avant la chaîne d'ampli de l'OS (l'enveloppe d'ampli et la vélocité
agissent après elle). `x` est la sortie du filtre à l'échelle de sortie (pleine échelle = 2^18), `d` le potard (0..1) :

| Étape | Formule | Pourquoi |
|---|---|---|
| Gain | `G = 10^(30 × (1 − (1 − d)^1,25) / 20)` : 0 dB à 0, 9 dB au quart, 17,5 dB à la moitié, 30 dB au maximum | le son change dès le début de la course (une loi linéaire en dB laissait le premier quart presque propre) |
| Courbe | `u = G x / (1,5 × pleine échelle)`, `y = u − u³/3` (pente 1 à l'origine, 2/3 et pente nulle à `u = 1`), `y = ±2/3` au-delà | écrêtage doux, sans cassure |
| Passe-bas | un pôle, coefficient `1 − d × e^(−2π × 6000 / 48000)` : rien à 0, 6 kHz au maximum | adoucit les harmoniques aiguës de l'écrêtage, qui se replient (pas de suréchantillonnage) |
| Niveau | `sqrt(1 + (G/c)²) / G × 10^(1,5d/20)`, `c` = 15 dB ; sortie `y × 1,5 × niveau` | compense le gain que le son reçoit vraiment (tout le gain sous le seuil, plus rien au-dessus ; une note typique a ~15 dB de marge à DRIVE 0) et laisse monter une scie de 1,5 dB d'un bout à l'autre |

À DRIVE 0 (`G = 1`), la courbe remplace le coude de la première version (`acid_out` : linéaire jusqu'à la moitié de la
pleine échelle, puis un coude jusqu'à la pleine échelle à 1,5) : les deux sorties diffèrent d'au plus 0,002 de la
pleine échelle en scie, 0,007 en carré (−43 dB), sur les réglages ci-dessous : à DRIVE 0, le son testé par Maxime
reste le même à l'oreille.

En virgule fixe : par bloc, `m = G × 2^28 / (1,5 × 2^18)` (table de 17 points, interpolée), `m3 = 8m/3`,
`xl = 0x0fffffff / m` ; par échantillon, `|x| ≥ xl` donne `u = ±2/3` directement (pas de débordement), sinon `u = x m`
(Q28, 1,0 = le seuil) et `y = u (1 − u²/3)` en deux `mac.l` (`u²/3 = u × x m3 / 8`) ; la sortie `z × 12 × niveau`
passe par `qmac2`, saturée par l'EMAC. Environ 400 à 520 instructions de plus par bloc que la première version, quel que
soit le réglage de DRIVE (§8).

Mesuré sur le cœur (`acid_ref`, une note de 150 blocs à partir du trig, avant la chaîne d'ampli) : niveau efficace par
rapport à DRIVE 0 et facteur de crête (crête / efficace) :

| Réglages (CUT / RES / ENV / DECAY) | DRIVE 0 | 16 | 32 | 64 | 96 | 127 |
|---|---|---|---|---|---|---|
| défaut 40 / 90 / 80 / 50, scie, note 36 | 0 dB, 6,7 dB | +0,3, 6,5 | +0,7, 5,8 | +1,2, 1,8 | +1,3, 0,6 | +1,6, 0,4 |
| 70 / 127 / 127 / 80, scie | 0, 6,5 | +0,2, 6,3 | +0,6, 5,6 | +0,6, 1,9 | +0,6, 0,8 | +0,8, 0,6 |
| 110 / 20 / 30 / 60, scie, note 48 | 0, 7,1 | +0,3, 6,9 | +0,8, 6,4 | +1,8, 2,3 | +2,3, 0,7 | +2,7, 0,4 |
| défaut, carré | 0, 3,4 | +0,1, 3,1 | −0,1, 2,3 | −2,6, 0,5 | −3,5, 0,2 | −3,4, 0,2 |
| défaut, scie, note 60 | 0, 8,6 | +0,3, 8,4 | +0,8, 7,7 | +1,8, 3,2 | +2,5, 1,4 | +2,9, 1,0 |

Le volume reste entre −3,5 et +2,9 dB sur toute la course (jusqu'à +3,9 dB filtre grand ouvert, mesuré par la preuve,
§9.1) ; le facteur de crête tombe de 7 dB à moins de 1 dB (une
onde presque carrée au maximum). Le carré, déjà riche, perd un peu de niveau en saturant : au maximum, scie et carré
se rejoignent. Limite : sans suréchantillonnage, une note aiguë (au-dessus de C4) avec DRIVE au maximum replie un
peu d'harmoniques (grain plus dur), comme une distorsion numérique simple.

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
décroissance sinon), pas de remise à zéro par `0x400a7d16`. Le cœur reçoit ce même bloc la nouvelle note (qui
glisse), sans relancer l'enveloppe du filtre (comme `slideToNote` d'Open303).

Le gain de vélocité sauterait au bloc suivant (de 100 à 127 vers une note plus forte : une marche de 2 dB au milieu
d'une onde, un clic) : la passerelle remet dans `0x40fe4cd0` le gain en cours, puis le rapproche de celui de la
nouvelle note de 1/127 par bloc (0,07 dB, 18 ms pour 100 → 127). Un trig rejoué arrête cette rampe (l'OS a écrit son
gain).

Limites : un trig rejoué juste après un appui et relâché dans le même bloc qui a choisi la machine (le tout premier
trig sur ACID, de longueur nulle) compterait comme tenu ; seule une note MIDI de longueur nulle peut faire ça. Un
trigless avec un verrou NOTE glisse toujours (la hauteur suit la note du trig), même si la note précédente est
finie : il n'y a rien à entendre alors.

### 3.4 État, voix muette

- Une voix d'ACID par piste (`acid_t`, 64 o) et l'état de la passerelle (124 o en tout par piste), dans le BSS de la
  charge utile, mis à zéro au démarrage.
- Repère `'ACD1'` en `voix + 0x2c`, effacé par la remise à zéro de la voix à chaque changement de machine : la
  première note y lit le paramètre MACHINE et marque la voix muette (remise à zéro au premier trig).
- **Voix muette non calculée** : sans trig ni slide et avec l'enveloppe d'ampli sous 2^14 (−102 dB), sortie nulle ;
  au trig suivant, phase et filtres à zéro (comme Open303 quand la voix s'est tue). Sinon le filtre continue d'une
  note à l'autre, comme sur la 303.

## 4. Le cœur en virgule fixe (`acid_dsp.h`)

- Signaux : 1,0 = 2^28 (l'oscillateur fait ±2^25) ; coefficients Q31 ; hauteurs en demi-tons `<< 16` ; tout passe par
  l'EMAC en mode fractionnaire signé saturé (`MACSR = 0xa0` pendant la boucle des voix) : `mac.l` + `movclr.l`, ACC0
  rendu vide.
- Par bloc : enveloppe du filtre, hauteur (slide), coupure en 1/16 d'octave, `b0`, `k`, gain (avec l'amplitude
  d'Open303), réglages de la saturation. Par échantillon : coefficients interpolés de la fin du bloc précédent à la
  fin de celui-ci, oscillateur, passe-haut d'entrée, contre-réaction et son passe-haut, 4 étages, saturation (§3.2).
- Sortie : 1,0 du modèle = 4 × la pleine échelle, puis la saturation : à DRIVE 0, une courbe douce qui atteint la
  pleine échelle à 1,5 × pleine échelle (les pointes fortes s'arrondissent au lieu d'écrêter). Avec les réglages par
  défaut, une note sort à ~0,4 de la pleine échelle avant la chaîne d'ampli, comme TONE après elle.
- Le même fichier est compilé pour le Cycles (`acid.c`) et pour l'ordinateur (`acid_ref.c`, l'EMAC reproduite :
  chaque produit tronqué à 2^−39, somme, décalage de 31 et saturation) : la preuve les compare à l'échantillon près.
- Tables (`acid_tables.h`, 1,8 Ko) calculées par `gen_acid.py` d'après les constantes d'Open303 et la saturation (§3.2).

## 5. Place

| | Seul (`acid`) | Avec Model-TG (`acid-tg`) |
|---|---|---|
| Charge utile au démarrage | `0x43000000`, comme MACRO | `0x46700000` |
| Code et tables d'ACID et de la passerelle | 5 996 o à `+0` | idem |
| Détours, données, descripteurs, rangées, enregistrements | `+0x33000..0x36000` (`gs.LAYOUT`) | idem |
| Variables (6 voix) | 744 o à `+0x36000` | idem |
| Ajouté à l'image (morceaux tassés) | 11 308 o | 11 720 o |
| Fin de l'image décompressée (limite `0x40200000`) | `0x401acd6c` | `0x401c2688` |
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
même sans voix, `cost()` de la preuve) `[FAIT en émulation]` :

| Voix | Instructions par bloc |
|---|---|
| ACID, scie | 5 080 |
| ACID, carré (PUNCH) | 5 223 |
| ACID, scie, DRIVE 64 | 5 080 |
| ACID, bloc du trig (remise à zéro comprise) | 5 539 |
| ACID, bloc d'un slide | 5 110 |
| ACID muette (pas calculée) | 270 |
| TONE, pour comparer | 5 291 |

Avec Model-TG (machine 8) : 5 139 en scie, 5 282 en carré, TONE 5 669. La saturation tourne à chaque échantillon,
même à DRIVE 0 : son coût ne dépend pas du réglage. ACID coûte donc à peu près une voix de TONE (0,96 à 0,99 en
instructions ; les cycles réels dépendent des `mac.l` et des accès mémoire, `[HYP]` du même ordre). Pile : 244 o sous
la boucle des voix. Pas de régulateur de charge, comme
pour les machines d'origine : six pistes ACID coûtent à peu près six pistes TONE.

## 9. Preuve en émulation `[FAIT en émulation]`

`tools/emu/test_acid.py` : le vrai code de l'OS (Unicorn), avec la charge utile telle que le crochet la reconstitue.
La référence est le même cœur compilé pour l'ordinateur (`acid_ref.c`), piloté bloc par bloc avec les réglages que la
passerelle doit lui donner, calculés par le test d'après cette note (classe `Bridge`) ; le test vérifie aussi ce que
la passerelle écrit dans l'OS (`voix + 0x34`, `0x40fe4cd0`).

### 9.1 Résultats (11/10/2026, version avec DRIVE, `test_acid.py` complet : 65 vérifications, TOUT OK)

| Vérification | Seule (machine 7) | Avec Model-TG (machine 8) |
|---|---|---|
| Démarrage : décompresseur, crochet, charge utile reconstituée, SRAM intacte, fin d'image sous `0x40200000` | ok (`0x401acd6c`) | ok (`0x401c2688`) |
| Interface : écran MACHINES, molette, enregistrements, potards, descripteurs, CC 16..19, machine hors limites | ok | ok |
| Avant la chaîne d'ampli, identique échantillon par échantillon au cœur compilé pour l'ordinateur | 33 cas, crêtes 0,01 à 0,82 | 33 cas |
| Voix muette non calculée, sortie nulle | 3 604 blocs, 169 muets | idem |
| Chaîne d'ampli : mêmes lectures de la voix que TONE (24 champs) jusqu'au silence | ok | — |
| 6 machines d'origine identiques, sans une instruction d'ACID | ok (OS d'origine) | ok (Model-TG seul) |
| Sortie finale de la piste identique à ACID seule | — | ok (scie, carré, GATE, DRIVE) |
| Machine locks SNARE → ACID → TONE → ACID (carré) → KICK | ok | ok |
| 6 pistes ACID ensemble ; pistes mélangées avec les machines d'origine (et le Sampler) | ok | ok |
| DRIVE 0, 16, 32, 48, 64, 96, 127 : crête / efficace de plus en plus bas, niveau presque constant | scie 7,8 → 1,9 dB (niveau +0,0 à +3,1 dB) ; carré 5,1 → 1,6 dB (−1,4 à +0,5) ; filtre grand ouvert 8,6 → 1,7 dB (+0,0 à +3,9) | — |
| Vrai séquenceur (`seqrig.py`) : LEN, VEL (le volume seulement), verrous (DRIVE par pas compris), trigless, jeu live, sans fondu, gain en rampe | 29 séquences, 9 699 blocs (120, 300, 546 BPM, trig à 0,05 / 0,5 / 0,95 bloc) | 13 séquences, 4 001 blocs (300 BPM) |
| Coût (§8) | 5 080 / 5 223 instructions par bloc ; TONE 5 291 | 5 139 / 5 282 ; TONE 5 669 |

Avec d'autres mods (`with_others`, même jour, TOUT OK) : `6ch-usbup,trig-hold,arp,tempo-max,boot-anim,multiline-browser,
level-pan-values,trigless-dim` ; les mêmes avec `model-tg-st,sample-preview-st` (ACID en machine 8) ; `chord-keys,
6ch-usbup,arp,trig-hold`. Chaque fois : démarrage, machines d'origine identiques à ces mods sans ACID, ACID identique
à ACID seule (ou avec Model-TG seul), machine locks, pistes mélangées.

Filtre par piste avec ACID (`test_track_filter.py --with acid --quick`) : 61 vérifications, TOUT OK. Sur un Model:Samples
(OS Cycles avec mods emballé par `tools/mods_for_samples.py`, [57](57-os-cycles-quelle-que-soit-la-machine.md)) : les
vérifications de `test_mods_for_samples.py` sur `model-tg-st,acid-tg` et les deux plus grosses combinaisons avec ACID
(seule et avec Model-TG) passent toutes (aller, refus du Cycles, démarrage par le bootstrap Samples sous `0x40200000`,
changer de mods, transport).

Flasher : `webflash_smoke.sh` avec les deux OS officiels, les 688 combinaisons de `REF_MAINOS` (chaque mod vérifié),
ALL PARTS OK ; la carte ACID seule, avec Model-TG, et son exclusion de MACRO et des moteurs dans les deux sens.

## 10. Sur la machine

**Testé sur la machine (11/10/2026), première version (CONTOUR = accent)**, fichiers ci-dessous : « ça marche bien ».
L'accent semblait ne rien changer, et Maxime ne le trouvait pas utile ici : remplacé par DRIVE (§3.2). Fichiers de cette
première version, construits par `tools/build.py` : `6ch-usbup,acid,trig-hold,arp,tempo-max,boot-anim,
multiline-browser,level-pan-values,trigless-dim` (MAIN OS `fba63d4f…`) et `6ch-usbup,model-tg-st,sample-preview-st,
acid-tg,trig-hold,arp,tempo-max,boot-anim,multiline-browser,level-pan-values,trigless-dim` (MAIN OS `640b2fd3…`).

Version avec DRIVE, fichiers de test construits par `tools/build.py` (dossier du projet `machine-acid/`, jamais dans le
dépôt) : `6ch-usbup,acid,track-filter,trig-hold,arp,tempo-max,boot-anim,multiline-browser,level-pan-values,
trigless-dim` (`model-cycles_acid-drive.syx`, MAIN OS `9ebda722…`) et `6ch-usbup,model-tg-st,sample-preview-st,acid-tg,
trig-hold,arp,tempo-max,boot-anim,multiline-browser,level-pan-values,trigless-dim` (`model-cycles_acid-drive_model-tg.syx`,
MAIN OS `d5449543…`). `demo-acid-drive.wav` : une ligne jouée par le vrai séquenceur en émulation, DRIVE à 0, 40, 80
puis 127 toutes les deux mesures.

À vérifier sur la version avec DRIVE :

- CONTOUR (Drive) de 0 à 127 sur une ligne qui joue : à 0, le son de la première version ; de la chaleur au premier
  quart, du grain vers le milieu, un fuzz en haut ; le volume reste à peu près le même, sans saut ni craquement.
- DRIVE au maximum avec RESO haute, en scie et en carré, et sur une note aiguë ; DRIVE verrouillé sur un pas.
- Le reste comme avant : CUTOFF, RESO, ENV MOD, DECAY, slide (LEN 1.06 ou INF), GATE ; VEL ne change que le volume.
- Avec Model-TG : la même chose sur la 8e machine.
