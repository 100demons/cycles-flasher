# 56 — Ajouts de DavidCaruso : LFO 2, 3, 4

DavidCaruso a envoyé sur Discord un firmware complet, `Model-TG-VA-DR-v1.syx` : le Model-TG v1.1.0 de TinyGregAudio
avec trois ajouts de sa main, sans source ni licence publiées. Maxime l'a transmis sur le fil du projet le 10/10/2026 :
« Intègre ses ajouts en mods décomposés (n'ajoute que ce qui n'existe pas déjà dans le projet) ». Les trois ajouts ont
été réécrits en mods séparés ; le 11/10/2026, Maxime a gardé les LFO et fait retirer le générateur de trigs et les
machines VA (§2). Le code est **réécrit** à partir de l'analyse de son binaire (comportement, algorithmes, accès à
l'OS) : aucun de ses octets ni aucune de ses instructions n'est dans le dépôt, et son fichier n'y est pas. Adresses :
VA de l'OS 1.13 ; « chez David » renvoie à la section 3 de son `.syx`, dépaquetée et exécutée pour l'analyse.

| Mod | Tweak | Générateur, code | Preuve | Section |
|---|---|---|---|---|
| LFO 2, 3, 4 | `60-lfo-plus.json` (avec ou sans Model-TG) | `tools/gen_lfo_plus.py`, `tools/machines/lfo_plus/` | `tools/emu/test_lfo_plus.py` | §3 |

## En bref

- **Un mod expérimental**, LFO 2, 3, 4 : trois LFO de plus par piste, avec ou sans Model-TG, avec tous les autres mods
  sauf le filtre par piste, qui range ses réglages aux mêmes endroits du son (§3.6).
- **Même comportement que chez David**, prouvé en émulation contre l'OS d'origine ; LFO 2 est rangé dans le son au
  même format que chez lui, ses sons se rechargent.
- **Écarts voulus** : les accroches sont déplacées pour que le mod s'installe avec tous les nôtres sans écrire un
  octet qu'un autre écrit (§3.4).
- **Place** : 7 masques 34×34 et 1 180 o de mémoire au-dessus du BSS. `tweaks/model-cycles_OS1.13/REGISTRY.md` est
  régénéré avec ce tweak.
- **Testé sur la machine (11/10/2026)** par Maxime : « ça marche nickel ». **Licence** : MIT, accord de David
  transmis par Maxime le 11/10/2026 (§1.3).

## 1. Le firmware de David

### 1.1 Ce qui change par rapport au Model-TG officiel `[FAIT]`

Seule la section 3 diffère du `.syx` officiel. Son MAIN OS est le Model-TG v1.1.0 officiel (reconstruit ici avec
`gen_model_tg.export_build`, sans les retouches de ce projet) plus ses changements dans les sources de Model-TG,
reconstruits par le `build.py` de Model-TG : le bloc de Model-TG passe de `0x401bf8c0` à `0x401c2fa0` (dans les six
blocs du cache de fichiers que Model-TG réserve, limite `0x401c3750`). Environ 14 Ko de code nouveau, écrit à la main
(style GAS), dans deux blocs (`0x401bf2f8..0x401c1eea` et `0x401c2442..0x401c2e9e`), une trentaine de petites insertions
dans des fonctions de Model-TG, onze nouvelles accroches dans l'OS et la borne des machines portée à `0x0a`.

### 1.2 Décomposition

| Ajout de David | Déjà dans le projet ? | Ici |
|---|---|---|
| Model-TG v1.1.0 | oui (`30-model-tg`, `30-model-tg-st`, note 31) | rien |
| Menu Generate sur SETTINGS + TRACK | non | fait puis retiré (§2) |
| LFO 2, 3, 4 | non | §3, réécrit sans dépendre de Model-TG |
| Machines VA, VA KICK, VA SNARE, VA HIHAT | non | faites puis retirées (§2) |

### 1.3 Provenance et licence

DavidCaruso n'a publié ni source ni licence. Le code d'ici est réécrit (aucun octet repris) ; pour LFO 2, le format de
rangement dans le son (octets +88..+91) est gardé pour que ses sons se rechargent. Le crédit est sur la carte du
flasher (« based on a mod by DavidCaruso »), dans le guide, `PROVENANCE.md` et la description du tweak. Le
10/10/2026, le fil a demandé à Maxime d'obtenir l'accord de David (licence MIT) et, s'il veut bien, ses sources. Rien
n'a été envoyé à David de notre côté. `[FAIT]` Le 11/10/2026, Maxime transmet que David est d'accord pour la licence
MIT ; la contribution est inscrite dans `THIRD-PARTY-NOTICES.md`.

## 2. Générateur de trigs et machines VA : faits, puis retirés

Les deux autres ajouts de David ont été réécrits et prouvés en émulation dans la même PR (#79) : un générateur de
trigs euclidien ou aléatoire sur SETTINGS + TRACK (tweaks `49-generate`, `49-generate-st`, sur Model-TG) et quatre
machines ajoutées, VA, VA KICK, VA SNARE, VA HIHAT (tweaks `27-va`, `36-va-tg`, comme MACRO). Le 11/10/2026, Maxime :
« J'aime pas trop le générateur euclidien et les machine VA. Par contre le LFO c'est supper. Retire completement le
générateur de trigs et les machines VA mais laisse l'ajout des 4 lfo ». Générateurs, sources, preuves et tweaks sont
retirés du dépôt ; ils restent dans l'historique de la branche (commit `d7b0341`) si l'idée revient. Les numéros 27, 36
et 49 sont libérés.

## 3. LFO 2, 3, 4 : trois LFO de plus par piste

Tweak `60-lfo-plus.json`, id `lfo-plus`, seul, avec ou sans Model-TG, et avec tous les autres mods sauf `track-filter` (§3.6). Générateur `tools/gen_lfo_plus.py`, code `tools/machines/lfo_plus/lfo_plus.S` (assembleur ColdFire), preuve `tools/emu/test_lfo_plus.py`.

### En bref

- **Trois LFO de plus par piste** (LFO 2, 3, 4), à côté du LFO d'origine (LFO 1). Sur la page LFO, chaque nouvel
  appui sur [LFO] passe à la page suivante, signalée par un grand chiffre « 2 », « 3 » ou « 4 » dans le cadre de
  gauche. Le 5e appui ferme la page. C'est le comportement de David.
- **Le même LFO que celui de l'OS** `[FAIT en émulation]`. Chaque LFO de plus fait tourner la vraie fonction des LFO
  de l'OS (`0x40091ab2`) avec son propre état. Formes, synchro au tempo, multiplicateurs, fondu, phase et modes
  sont donc identiques, sortie pour sortie.
- **Réglages** :
  - propres à chaque LFO de plus : SPD, MULT, WAVE, DEST, DEP ;
  - communs avec LFO 1 : FADE, SPH, MODE et le retrig. Sur les pages 2 à 4, ces trois potards règlent LFO 1.
- **LFO 2 est sauvé avec le son et se p-locke.** Il est rangé dans 4 octets libres de l'enregistrement du son, au
  même format que chez David : ses sons se relisent ici, et inversement. L'OS d'origine relit ces sons sans rien
  perdre d'autre.
- **LFO 3 et 4 vivent en mémoire.** Ils ont un réglage par piste, ne sont pas sauvés, ne se p-lockent pas et
  reviennent aux défauts à chaque démarrage.
- **Écarts voulus avec David**, pour l'installer avec tous nos mods sans écrire un octet qu'un autre tweak écrit :
  - les accroches sont déplacées (§3.4) ;
  - LFO 2 n'est plus calculé quand aucune piste ne lui donne de destination ;
  - sa destination change d'un coup au lieu de glisser par les destinations intermédiaires (§3.3.2).
- **Correctif au passage** : avec Model-TG, un p-lock d'Attack, de Filtre ou de Résonance revenait, au rechargement
  du pattern, comme un p-lock de None, LFO Speed ou Multiplier. Il revient maintenant sur le bon paramètre (§3.3.5).
- **Coût** : +137 instructions par bloc sans LFO de plus (0,13 % d'un bloc). LFO 2 coûte 1,2 à 1,3 %, les trois
  ensemble 3,5 % (§3.8). Chez David : +1 566 instructions toujours, +4 734 avec les trois.
- **Place** :
  - 1 844 o de code et de données dans 7 masques de sprites 34×34 libérés ;
  - 1 180 o de mémoire de travail en `0x4233f000`, au-dessus du BSS (§3.5).

### 3.1 Ce que fait l'OS `[FAIT]`

#### 3.1.1 Le LFO dans la boucle audio

| Où | Quoi |
|---|---|
| `0x4005979e` | fonction audio de chaque bloc. `a3` = son argument : `(a3)` = les **cibles** des paramètres (même forme que obj), `4(a3)` = masque des retrigs. Tempo en `0x40149310` |
| `0x40058474(cibles)` | lissage : rapproche obj (`0x8000100c`) des cibles. obj = en-tête de 14 o + 7 pistes × 66 o (un mot par k, plus l'état). Seul k = 4 est recopié brut |
| `0x400597ba..0x400597cc` | appel des LFO : trois `move.l` empilés, puis `jsr 0x40091ab2(obj, tempo, masque)` en `0x400597c6` |
| `0x40091ab2` | les 6 LFO, un par piste : état en `0x40fde838 + 32 × piste` (192 o en tout). Lit SPD/MULT/FADE/DEST/WAVE/SPH/MODE/DEP dans obj et ajoute la modulation au mot visé de obj, borné à 0..0x7f00. Fondu par `0x400918b0` (EMAC, MACSR = 0x20). La forme RND tire dans le générateur global `0x40091a96` (`0x4014931c`/`0x40149320`) |

#### 3.1.2 Le son et ses réglages

| Où | Quoi |
|---|---|
| son (100 o en mémoire) | mots k = 0..32 en son + 20 + 2k, machine en son + 38. LFO 1 : k = 1..8 (SPD, MULT, FADE, DEST, WAVE, SPH, MODE, DEP). k = 28..32 (son + 76..85) : **aucun descripteur ne les vise**, l'OS les laisse à 0 |
| `0x4010dce0` | descripteurs des paramètres (56 o chacun, +4 = k) |
| `0x4005a4e8(id)` | id → k : `moveq #borne,d1` (76 d'origine, plus avec les machines ajoutées), puis `move.l 4(sp),d0 ; cmp.l d0,d1 ; …`. Les tables k → id (BSS) sont bâties par `0x4005a274` |
| vtable `0x400fd134` | accesseur des réglages de la piste active : [20] `0x4000c264` (pas de molette ; `fine_hook` sous Model-TG), [28] get `0x4000ae20`, [52] k → id, [92] set `0x4000ba7a` |
| `0x4000c140(this, valeur, pas, masque)` | pas dans la liste des destinations (DEST, id 32), appelé par `0x4000c264`. La liste vient de `0x4000bffc` (tas) ; `0x4000c23e` rend k << 8 |

La liste DEST de la machine 0 donne k = 0, 10, 17, 18, 11, 12, 13, 14, 20, 21, 19, 22, 15, 16 (avec Model-TG,
s'y ajoutent 23, 24, 25 pour Attack, Filtre et Résonance). **Aucun réglage de LFO n'y figure.**

#### 3.1.3 La page LFO

| Où | Quoi |
|---|---|
| `0x4001c3dc` | seul appel du constructeur de la vue LFO, `jsr 0x40025798`. La vue est à objet + 56 |
| `0x400d979a` | destructeur de la vue (`a2` = l'objet), suite en `0x400d97fe` |
| vtable `0x401016dc` | [2] touche `0x40024e86`, [4] dessin `0x400426fa` |
| événement de touche | code rendu par `0x4007240c`, indicateurs en +16 : bit 0 enfoncée, bit 1 FUNC, bit 3 répétition (lus par `0x40072470`, `0x40072490`, `0x400724a0`). Le code 8 ferme la page au relâchement : c'est la touche [LFO] `[HYP forte]` |
| `0x40025e10` | appelée par 4 rappels de la vue (WAVE, MULT, DEST, DEP), trig tenu : pose un p-lock sur LFO 1 |
| `0x40ea14d4` | police du nom de la page (objet en BSS) |

#### 3.1.4 Sauvegarde du son et des p-locks

| Où | Quoi |
|---|---|
| `0x4005afa0` | sauvegarde du son, format 2 : met l'enregistrement de 100 o à zéro, copie les mots. +88..+91 restent à zéro (Model-TG n'y touche pas) |
| `0x4005b054` | format 1 : ne sert qu'à remplir 64 sons vides de la réserve (`0x4005be00`), jamais relu |
| `0x4005aecc` | chargement du son : **format 2 seulement**. Les mots k = 0..32 sont mis à zéro par `0x4008f238`, puis copiés |
| `0x40061866` | son neuf aux défauts (machines 0..5) |
| `0x4005b95c(rangées, src)` | enregistrement des p-locks : `d0` = k, `d4` = 4k, pistes 0..5, 80 rangées de 130 o. L'identifiant de rangée est lu dans `0x4010ee4c[k]`, qui n'a que 23 entrées |
| `0x4005b766(dst, rangées)` | relecture : saute id > 32 ou piste > 5. Le k vient de `0x4005aa1a(piste, id)` |

Sur l'OS d'origine, les rangées de k = 23..32 lisent la table voisine de `0x4010ee4c`. Elles reviennent sur k = 0..9
et les écrasent. Rien ne s'en sert d'origine, mais Model-TG met Attack, Filtre et Résonance en k = 23, 24, 25.

### 3.2 Le firmware de David `[FAIT]`

Analyse détaillée hors dépôt (scratchpad du coordinateur, `analysis/lfo.md`). En résumé :

- **Moteur.** Il remplace l'appel des LFO en `0x400597c6`. Pour chaque LFO de plus :
  1. il fabrique un faux obj, qui porte les réglages de ce LFO et FADE/SPH/MODE de LFO 1 ;
  2. il échange l'état des LFO de l'OS (`0x40fde838`) avec le sien ;
  3. il appelle `0x40091ab2` ;
  4. il rééchange les états ;
  5. il ajoute la modulation au vrai mot de la piste. Si la destination est celle de LFO 1, il saute cette étape.

  LFO 1 passe en dernier.
- **Pages.**
  - id → k en `0x4005a4e8` : il recode la borne 76 en dur.
  - get/set des pages 3 et 4 : pointeurs `0x400fd150` et `0x400fd190`.
  - touche et dessin de la vue LFO.
  - création et destruction de la vue.
  - `0x40025e10` coupé sur les pages 3 et 4.
- **LFO 2 dans le son.** k = 28..32, empaqueté en +88..+91 de l'enregistrement par des insertions dans
  `snd_save_post` et `snd_load_post` de Model-TG. Les défauts d'un son neuf sont posés à l'entrée de `0x40061866`.
- **p-locks.** Accroches en `0x4005b9c6` et `0x4005aa1a`, avec la table k = 23..32 → identifiant qui corrige
  Model-TG.
- **Anti-doublon DEST**, dans le `fine_hook` de Model-TG.
- **Il ne marche qu'avec Model-TG.** Son code s'exécute dans les blocs de cache que Model-TG retire.

**Ce qui le rend impossible à reprendre tel quel :**

- Ses accroches en `0x4005a4e8`, `0x40061866` et `0x4005aa1a` recouvrent des octets que nos machines ajoutées, MACRO
  ou Model-TG réécrivent. La borne 76 recodée en dur casserait les descripteurs de nos machines.
- Ses insertions vivent dans le code de Model-TG.

**Ses défauts :**

- LFO 2 est calculé à chaque bloc, même sans destination.
- La destination de LFO 2 (k = 31) passe par le lissage. Au changement, son octet fort traverse les destinations
  intermédiaires pendant une cinquantaine de millisecondes, et chacune reçoit la modulation quelques blocs.

### 3.3 Conception

#### 3.3.1 Moteur (`lfo_audio`, `run_set`)

`0x400597c6` : `jsr 0x40091ab2` → `jsr lfo_audio`. La fonction rend comme l'appel d'origine : d2-d7/a2-a6 gardés.

1. **Premier usage depuis le démarrage.** Les trois états des LFO de plus sont mis à zéro, comme l'OS met
   `0x40fde838` à zéro avec son BSS. Le drapeau `ready` est dans un masque, donc rechargé à 0 depuis la flash à chaque
   démarrage. Un mot magique en SDRAM aurait pu survivre à une coupure brève.
2. **Destination de LFO 2.** k = 31 est recopié brut des cibles dans obj, comme l'OS le fait pour k = 4. LFO 3 et 4
   lisent leurs tables directement.
3. **Choix des jeux.** Un jeu de 6 LFO (un par piste) n'est calculé que si au moins une piste lui donne une
   destination. Sans LFO de plus, il reste l'appel de `0x40091ab2` et ce test (+137 instructions).
4. **Pour chaque jeu utilisé** (LFO 2, puis 3, puis 4) :
   1. sauvegarde de l'état de l'OS ;
   2. copie de l'état du jeu à sa place ;
   3. faux obj : en-tête et mots des pistes recopiés de obj, avec les réglages du jeu en k = 1, 2, 4, 5, 8 ;
   4. `0x40091ab2(faux obj, tempo, masque)` ;
   5. état du jeu repris, état de l'OS remis ;
   6. pour chaque piste, si DEST ≤ 32 et ≠ DEST de LFO 1 : le vrai mot de obj reçoit la modulation (mot du faux obj
      moins mot d'avant), borné à 0..0x7f00.
5. **Puis LFO 1**, par l'appel d'origine. Les LFO de plus passent avant lui. Ils peuvent donc moduler ses réglages
   (SPD, DEP…), mais la liste DEST de l'OS n'en propose aucun. Cette modulation croisée n'est atteignable que par
   des données, pas depuis l'interface.

Deux LFO de plus sur la même destination s'additionnent, chacun borné : `borne(borne(base + q2) + q3)`.

#### 3.3.2 Écarts avec David dans le moteur

- **LFO 2 n'est pas calculé quand aucune piste ne lui donne de destination** : +137 au lieu de +1 566 instructions.
  Sa phase s'arrête alors, comme celles de LFO 3 et 4 chez David et ici. Elle reprend où elle en était quand une
  destination revient. En mode trig, le prochain trig la recale.
- **k = 31 recopié brut.** Changer la destination de LFO 2 ne fait plus passer la modulation par les destinations
  intermédiaires. Prouvé en émulation : 0x0a80 en cours de lissage donne 0x0b00 tout de suite, la modulation va à
  k = 11 et jamais à k = 10. MULT et WAVE (k = 29, 30) glissent encore, comme k = 2 et 5 pour LFO 1 dans l'OS
  d'origine.

#### 3.3.3 Pages (`lfo_key`, `lfo_draw`, `lfo_ctor`, `lfo_dtor`, `lfo_id2k`, `lfo_get`, `lfo_set`, `lfo_gate`)

- **Variables.** `page` (0 à 3), `eat` (relâchement à avaler) et `view` (la vue ouverte, objet + 56, ou 0) sont
  dans un masque. Elles valent 0 dans l'image, donc à chaque démarrage.
- **Touche** (pointeur `0x401016e4`). Code 8 sans FUNC :
  - un appui sur LFO 1, 2 ou 3 passe à la page suivante et redessine ; son relâchement est avalé ;
  - sur LFO 4, l'appui va à l'original, qui ferme la page au relâchement, comme d'origine ;
  - la répétition automatique, FUNC et les autres touches vont à l'original.
- **Dessin** (pointeur `0x401016ec`). D'abord l'original. Puis, sur les pages 2 à 4 :
  1. le cadre gauche (0, 0)-(63, 63), inversé par l'OS, est désinversé ;
  2. le chiffre est centré en (32, 34) avec la police du nom de page ;
  3. le cadre est réinversé.
- **Création / destruction.** `0x4001c3dc` : `jsr lfo_ctor`. Le constructeur d'origine est appelé avec le même
  argument, puis la page est mise à LFO 1 et la vue notée (pas de vue si l'allocation a échoué). `0x400d97f8`, fin
  du destructeur : si c'est notre vue, retour à LFO 1 et plus de vue.
- **id → k** (`0x4005a4ea`, après la borne, qui reste dans `d1`) :
  - page LFO 2 : les identifiants de SPD, MULT, WAVE, DEST, DEP (0x1d, 0x1e, 0x21, 0x20, 0x24) donnent k = 28..32.
    Le get/set de l'OS lit et écrit alors les mots de LFO 2 du son et notifie ces k ; les p-locks portent sur ces
    k (pose du lock pas émulée de bout en bout, §3.9) ;
  - pages LFO 3 et 4 : ces 5 identifiants donnent −1 (aucun mot du son) ;
  - tout le reste suit l'original.
- **get/set** (pointeurs `0x400fd150`, `0x400fd190`). Sur les pages 3 et 4, ces 5 réglages lisent et écrivent la
  table de LFO 3 ou 4 de la piste sélectionnée, puis redessinent. Le reste passe à l'original.
- **`0x40025e10`** (rappels de la vue, trig tenu) rend la main sans rien faire sur les pages 3 et 4 : pas de p-lock.
  Un potard tourné trig tenu y change la valeur de jeu, comme chez David.

#### 3.3.4 Molette DEST (`lfo_dest`, accroche dans `0x4000c140`)

`0x4000c140` : `jmp lfo_dest ; nop`. Page fermée : l'original. Page ouverte :

1. la page est mise à LFO 1 le temps du calcul. C'est une précaution : un réglage de LFO dans la liste deviendrait
   sinon k = 28..32 ou −1. La liste de l'OS n'en propose aucun ;
2. on fait le pas d'origine. Si la destination obtenue est prise par un des 3 autres LFO de la piste, on refait un
   pas, jusqu'à 5 pas en tout :
   - LFO 1 : son + 28 ;
   - LFO 2 : son + 82 ;
   - LFO 3 et 4 : leurs tables ;
3. None reste toujours permise. Au bout de la liste, ou si les 5 destinations suivantes sont prises, la valeur ne
   change pas.

L'accroche est dans la fonction de l'OS, pas dans le `fine_hook` de Model-TG comme chez David. Elle marche donc avec
ou sans Model-TG : le `fine_hook` repasse par `0x4000c264` pour DEST. Prouvé en émulation par la vtable [20], avec
et sans Model-TG.

#### 3.3.5 LFO 2 dans le son et dans le pattern

**Sauvegarde** (`lfo_pack`). Formats 1 et 2, en `0x4005b028` et `0x4005b0dc`, à la place de
`move.w 94(a3),92(a2)`. L'instruction est refaite, puis LFO 2 est rangé en un long en +88, dans les deux dernières
cases libres :

| Bits | Contenu |
|---|---|
| 31-30 | 10 (marque) |
| 29-22 | SPD >> 7 |
| 21-17 | MULT |
| 16-14 | WAVE |
| 13-8 | DEST |
| 7-0 | DEP >> 7 |

C'est le format de David.

**Chargement** (`lfo_unpack`, `0x4005af1c`). LFO 2 est relu de +88 s'il porte la marque. Sinon (tout son plus
ancien, ou marque inconnue), il prend ses défauts. Ce sont ceux du LFO d'origine : SPD 0x7000, MULT 4, WAVE TRI,
DEST None, DEP 0x4000 (profondeur nulle).

**Son neuf** (`lfo_init`, `0x400618e2`, fin de `0x40061866`). Défauts de LFO 2 ; l'OS y mettait 0.

**p-locks**, pour les pistes 0..5 :

- enregistrement (`lfo_plk_save`, `0x4005b9c6`) : pour k = 23..32, l'identifiant de rangée vient de la table
  `plk_id` = 24, 25, 26, —, —, 27, 28, 29, 30, 31. k = 26 et 27 sont l'état du Sampler de Model-TG, jamais p-locké :
  leur rangée est marquée 0xff, ignorée à la relecture ;
- relecture (`lfo_plk_load`, `0x4005aa22`) : les identifiants 24..31, que l'OS n'écrit jamais, donnent k = 23, 24,
  25, 28..32. Le reste suit l'original.

Les rangées k = 23..25 corrigent Model-TG : Attack, Filtre et Résonance reviennent sur leur paramètre. Les projets
déjà sauvés avec le défaut gardent leurs rangées fausses.

#### 3.3.6 LFO 3 et 4

Deux tables dans un masque, de 6 pistes × {SPD, MULT << 8, WAVE << 8, DEST << 8, DEP} chacune, aux défauts dans
l'image. Une valeur par piste, globale : ni par son, ni par kit, ni par pattern, et pas de p-lock. Elle est gardée
au changement de projet et revient aux défauts au démarrage.

### 3.4 Accroches

12 instructions remplacées et 4 pointeurs. Chaque accroche au milieu d'une fonction rend ce que la suite attend :
registres, pile et drapeaux quand ils servent (§3.7, section 7 de la preuve).

| Adresse | D'origine | Devient | Rôle | Chez David |
|---|---|---|---|---|
| `0x400597c6` | `jsr 0x40091ab2` | `jsr lfo_audio` | moteur | idem |
| `0x4005a4ea` | `move.l 4(sp),d0 ; cmp.l d0,d1` | `jmp lfo_id2k` | id → k selon la page | `0x4005a4e8`, borne en dur |
| `0x4005aa22` | `move.l 12(sp),d0 ; cmp.l d1,d2` | `jmp lfo_plk_load` | rangée de p-locks → k | `0x4005aa1a` |
| `0x4005b9c6` | `move.b 3(a5,d4.l),(a3) ; move.b d2,1(a3)` | `jsr lfo_plk_save ; nop` | identifiant de rangée | idem |
| `0x4005b028` | `move.w 94(a3),92(a2)` | `jsr lfo_pack` | sauvegarde du son (format 2) | dans Model-TG |
| `0x4005b0dc` | `move.w 94(a3),92(a2)` | `jsr lfo_pack` | sauvegarde du son (format 1) | dans Model-TG |
| `0x4005af1c` | `lea 0x4010eea8,a0` | `jsr lfo_unpack` | chargement du son | dans Model-TG |
| `0x400618e2` | `lsl.l #8,d3 ; move.w d3,38(a2)` | `jsr lfo_init` | son neuf | entrée `0x40061866` |
| `0x40025e10` | `lea -16(sp),sp ; move.l a2,-(sp)` | `jmp lfo_gate` | pas de p-lock pages 3/4 | idem |
| `0x4001c3dc` | `jsr 0x40025798` | `jsr lfo_ctor` | création de la vue | idem |
| `0x400d97f8` | `move.l a2,8(sp) ; movea.l (sp)+,a2` | `jmp lfo_dtor` | destruction de la vue | entrée `0x400d979a` |
| `0x4000c140` | `link.w fp,#-32 ; move.l 12(fp),d0` | `jmp lfo_dest ; nop` | anti-doublon DEST | dans `fine_hook` de Model-TG |
| pointeur `0x400fd150` | `0x4000ae20` | `lfo_get` | get, pages 3/4 | idem |
| pointeur `0x400fd190` | `0x4000ba7a` | `lfo_set` | set, pages 3/4 | idem |
| pointeur `0x401016e4` | `0x40024e86` | `lfo_key` | touche de la vue LFO | idem |
| pointeur `0x401016ec` | `0x400426fa` | `lfo_draw` | dessin de la vue LFO | idem |

`[FAIT]` : aucun branchement ni constante de l'OS ou des charges utiles ne vise l'intérieur d'une instruction
remplacée.

### 3.5 Place

#### 3.5.1 Code et données : 7 masques de sprites 34×34 libérés

| Masque | Octets | Redirigé (constante) | Contenu |
|---|---|---|---|
| `0x4016f8c8` | 272 | `0x400b0b3c` | un jeu de 6 LFO (`run_set`, 192) ; id → k (`lfo_id2k`, 80) |
| `0x40173848` | 272 | `0x400b0350` | suite du moteur (168) ; `lfo_ctor`, `lfo_dtor`, `lfo_gate` (104) |
| `0x401780a8` | 272 | `0x400af946` | `lfo_dest` (162) ; `lfo_draw` (110) |
| `0x401784e8` | 262 | `0x400af832` | `lfo_get`, `lfo_set` et la piste sélectionnée (148) ; destinations prises (114) |
| `0x401835b8` | 270 | `0x400adedc` | données : `view`, `page`, `eat`, `ready`, tables, réglages de LFO 3/4 (142) ; `lfo_audio` (128) |
| `0x40184df8` | 248 | `0x400adbc8` | `lfo_unpack`, `lfo_init` (136) ; `lfo_key` (112) |
| `0x40185308` | 248 | `0x400adb8c` | `lfo_pack` (96) ; `lfo_plk_save`, `lfo_plk_load` (82) ; copie de 192 o (70) |

Chaque masque est identique au masque gardé `0x4016bfc8`, n'a qu'une référence, et cette référence est redirigée
(`tools/sprites.py`). Le générateur place les sections (de 70 à 192 o), les plus grosses d'abord, dans le premier
masque qui convient. Total : 1 844 o sur 1 904.

Les masques `0x40185f48`, `0x40186238` et `0x40189618`, réservés à ce mod, restent vides et ne sont pas touchés.

#### 3.5.2 Mémoire de travail : `0x4233f000..0x4233f49b` (1 180 o)

| Décalage | Taille | Contenu |
|---|---|---|
| +0 | 192 | état des LFO de l'OS, mis de côté pendant un jeu |
| +192 | 192 × 3 | états des 6 LFO 2, 3, 4 |
| +768 | 412 | faux obj (14 + 6 × 66 o) |

`[FAIT]` Placement :

- Le BSS de l'OS, `0x4019b590..0x423380b0`, est mis à zéro par `0x400004b2` (constante de fin en `0x400004c2`).
- `0x40057798` place les tampons DMA de l'OS par l'alias sans cache `0x4a340000` : 9 × 64 Ko, soit
  `0x42340000..0x423d0000`.
- Le trou `0x423380b0..0x4233ffff` n'est visé par rien :
  - aucune adresse de ce trou, ni de son alias sans cache, dans l'OS ;
  - ni dans les écritures des autres tweaks ;
  - ni dans le code et les relocalisations de leurs charges utiles.

  La preuve le vérifie à chaque combinaison. notes/44 avait déjà vu ce trou dans le mod d'origine de VOLUME/PAN.
- **`0x42380000`, proposé au départ, est le 5e tampon DMA de l'OS** : à écarter, pour ce mod comme pour les autres.
- Le haut du trou est pris ici et le bas (`0x423380b0..0x4233efff`) reste libre.
- Pas mise à zéro au démarrage : voir §3.3.1.

### 3.6 Conflits

**Le filtre par piste (`track-filter`, notes/47) : incompatible** `[FAIT en émulation]`. `tools/check_overlaps.py` ne
voit aucune écriture partagée (154 tweaks après la fusion de main du 11/10/2026), mais les deux mods rangent leurs
réglages aux mêmes endroits :

- dans le tableau des paramètres de la piste : LFO 2 en k 28..32, le filtre en k 28..31 (Cutoff, Reso, Env, Decay) ;
- dans l'enregistrement du son : LFO 2 en +88..+91 (format de David), le filtre Cutoff en +88 et Reso en +90 ;
- dans les p-locks : les deux renumérotent les rangées k ≥ 23, chacun à sa façon.

`test_lfo_plus.py --with macro,track-filter` le montre : 5 vérifications de la sauvegarde et des p-locks échouent. Le
tweak déclare donc `conflicts: ["track-filter"]` (`build.py` refuse les deux ensemble) et la carte du flasher
`excludes: ["track-filter"]`, avec sa raison propre (`clash_track-filter` dans `FEAT` ; `clashWhy` de `app.js` lit
d'abord ce texte par paire). `[À DÉCIDER]` Pour les réunir, il faudrait ranger LFO 2 ailleurs (il n'y a plus de k
libre : 0..22 l'OS, 23..27 Model-TG, 28..31 le filtre), par exemple en mémoire comme LFO 3 et 4, sans sauvegarde ni
p-lock quand le filtre est coché, ou dans d'autres octets du son au prix de la compatibilité avec les sons de David.

Les accroches évitent tout ce que réécrivent :

- Model-TG (entrées des fonctions du son, `fine_hook`) ;
- les machines ajoutées et MACRO (borne de `0x4005a4e8`, entrée de `0x40061866`, `0x4005aa1a`).

Avec Model-TG, la liste DEST contient Attack, Filtre et Résonance. L'anti-doublon les traite comme les autres
destinations.

Déclaré dans `tools/registry.py` (DECLARED) : les octets +88..+91 de l'enregistrement d'un son (LFO 2 empaqueté, format de
DavidCaruso) et la mémoire `0x4233f000..0x4233f49b` au-dessus du BSS ; un autre mod qui voudrait l'un ou l'autre le voit dans
`REGISTRY.md`.

### 3.7 Preuve en émulation `[FAIT en émulation]`

`tools/emu/test_lfo_plus.py` fait tourner le vrai code de l'OS (Unicorn), d'origine contre modifié, avec les charges
utiles des autres tweaks posées à leur place.

| Section | Ce qui est vérifié | Résultat |
|---|---|---|
| 0. écritures | octets d'origine des 30 écritures ; masques libres et redirigés ; aucun autre tweak sur ces octets ; aucun branchement vers l'intérieur d'une instruction remplacée ; mémoire de travail hors BSS et hors tampons DMA, visée par rien d'autre ; variables à zéro dans l'image | ok |
| 1. sans LFO de plus | 600 blocs avec le vrai lissage : mots des pistes, état des LFO et générateur aléatoire = l'origine ; mêmes adresses écrites (plus k = 31, même valeur) ; registres et pile rendus ; mémoire de travail pas touchée | identique |
| 2. LFO 2, 3, 4 | 3 tirages × 400 blocs : chaque LFO de plus = la fonction des LFO de l'OS réglée pareil (formes, MULT 0..23, modes 0..4), RND compris ; règles (même DEST que LFO 1 ignorée, DEST > 32 sans effet, somme bornée, LFO 2 → vitesse de LFO 1, jeux sans destination pas calculés, k = 31 brut) | identique / ok |
| 3. interface | id → k sur les 4 pages (89 identifiants) ; aucun descripteur sur k = 28..32 ; touche (appui, relâchement, répétition, FUNC, LFO 4) ; création, allocation ratée, destruction ; `0x40025e10` ; get/set des pages 3 et 4 ; vrai get/set de l'OS sur la page 2 ; dessin ; liste DEST réelle et 432 cas de destinations prises | ok |
| 4. son | 25 sons, formats 2 et 1 ; chargement ; son sauvé sans le mod (défauts) ; OS d'origine sur un son du mod ; marque inconnue ; son neuf ; un son sauvé par le `.syx` de David relu avec le même LFO 2 (avec `--david`) | ok |
| 5. p-locks | rangée → k pour chaque piste et chaque identifiant ; aller-retour de 1 143 p-locks (k = 1..32) : tous relus au même k et au même pas ; l'origine, pour mémoire, perd k = 1..9 et 23..32 | ok |
| 6. coût | §3.8 | +137 |
| 7. accroches | de chaque accroche jusqu'à la fin des instructions remplacées (ou jusqu'au retour) : même pile vivante, mêmes registres hors ceux que la suite réécrit, mêmes drapeaux là où ils servent, même mémoire | ok |

Combinaisons passées (« TOUT OK » à chaque fois, environ 40 s par passage) :

- seul, avec `--david` (81 vérifications) ;
- `model-tg` ;
- `model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm` ;
- `macro` ;
- `syntakt-sd-cp-toy-bits-swarm-macro` ;
- `model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm-macro` ;
- `6ch-usbup,model-tg-st,macro-tg,arp,trig-hold,tempo-max,boot-anim,multiline-browser,level-pan-values,trigless-dim,sample-preview-st` ;
- `chord-keys,arp,trig-hold,tempo-max,sdvintage-7th,6ch-multiout,level-pan-values` ;
- `model-tg,sample-preview,arp,tempo-max` ;
- `va` et `model-tg-st,va-tg,generate-st` (avant le retrait de ces deux mods, §2).

```sh
python3 tools/gen_lfo_plus.py --cycles firmware/model-cycles_OS1.13.syx --check
python3 tools/emu/test_lfo_plus.py --cycles firmware/model-cycles_OS1.13.syx [--david firmware/david/Model-TG-VA-DR-v1.syx]
python3 tools/emu/test_lfo_plus.py --cycles firmware/model-cycles_OS1.13.syx --syntakt firmware/Syntakt_OS1.42.syx \
    --with model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm-macro
python3 tools/check_overlaps.py
python3 tools/registry.py --check
```

`--david` est facultatif : la preuve ne demande que le `.syx` officiel.

### 3.8 Coût

Instructions par bloc pour l'appel des LFO (moyenne / max). La part est celle d'un bloc de 166 667 cycles, à
1,54 cycle par instruction, hors cache.

| Cas | Moyenne / max | En plus de l'origine |
|---|---|---|
| origine | 890 / 923 | — |
| modifié, sans LFO de plus | 1 028 / 1 060 | +137 (0,13 %) |
| LFO 2 sur une piste | 2 216 / 2 636 | +1 325 (1,22 %) |
| LFO 2 sur les 6 pistes | 2 284 / 2 702 | +1 394 (1,29 %) |
| LFO 2 + 3 + 4 | 4 699 / 5 105 | +3 808 (3,52 %) |

Chez David, mesuré de la même façon : +1 566 toujours, +4 734 avec les trois.

### 3.9 Limites et points ouverts

- **Dessin du chiffre** `[HYP]` : police, position et lisibilité. Le texte est remplacé par un bouchon en émulation,
  et la police est un objet du BSS. Seuls les appels sont vérifiés : cadre, chiffre, police, coordonnées.
- **Touche [LFO]** : le code 8 est la touche [LFO] `[HYP forte]`. L'original ferme la page LFO sur son relâchement.
- **Identifiant de LFO → −1 sur les pages 3 et 4** : vérifié pour l'accesseur (garde `blt`), les p-locks (garde
  k ≤ 32) et la liste DEST. Les autres appelants de id → k ne sont pas tous relus `[HYP]`.
- **Page LFO 2 ouverte** : les chemins qui résolvent un identifiant de LFO, comme les CC MIDI probablement, visent
  LFO 2. C'est le même comportement que chez David `[HYP]`.
- **Pas émulés de bout en bout** :
  - le passage des mots k = 28..32 du son vers les cibles audio (notification par vt[16]) ;
  - la pose du p-lock par `0x4000f4b8` sur la page 2. Le get/set de l'OS, lui, est exécuté et écrit les bons k.
- **Rappels `0x40025e10`** : on ne sait pas exactement ce qui les déclenche.
- **LFO 3 et 4** sont globaux par piste et perdus à l'extinction. Trig tenu, un potard change la valeur de jeu.
- **SPD et DEP de LFO 2** sont sauvés sur 8 bits (pas de 0x80). Les valeurs entières de l'écran reviennent
  exactement, un réglage plus fin est arrondi.
- **Phase de LFO 2** arrêtée tant qu'aucune piste ne lui donne de destination (§3.3.2).
- **Anciens projets Model-TG** : ils gardent leurs rangées fausses d'Attack, Filtre et Résonance.
- **Modulation croisée des LFO** (un LFO de plus sur la vitesse de LFO 1…) : le moteur la permet, la liste DEST de
  l'OS ne la propose pas.

### 3.10 À essayer sur la machine `[FAIT]`

Testé sur la machine (11/10/2026) : Maxime, avec les fichiers de `ajouts-david/` (LFO seul, avec Model-TG, ensemble complet) : « ça marche nickel ». La liste ci-dessous reste comme mémoire de ce qui a été essayé.

Flasher `lfo-plus` seul, puis avec `model-tg` (et MACRO ou arp, au choix).

1. **Pages.** Ouvrir la page LFO, puis appuyer encore sur [LFO] : « 2 », « 3 », « 4 » dans le cadre de gauche, et le
   5e appui ferme la page. Vérifier :
   - le chiffre : lisible et bien placé ;
   - un appui long : pas de défilement ;
   - FUNC + [LFO] : comme d'origine ;
   - quitter la page par une autre touche puis revenir : on repart de LFO 1.
2. **LFO 2.** LFO 1 sur une destination, LFO 2 sur une autre, DEP au fond. Les deux modulent. Changer la
   destination de LFO 2 en cours de lecture : pas de « glissement » audible.
3. **DEST.** La molette saute les destinations déjà prises par les autres LFO de la piste. None reste permise.
4. **Réglages partagés.** FADE, SPH et MODE sur la page 2 changent ceux de LFO 1 : vérifier en revenant sur la page 1.
5. **LFO 3 et 4.** Chaque piste a ses réglages. Changer de piste sur la page 3 : les valeurs suivent. Trig tenu, un
   potard ne pose pas de p-lock. Éteindre et rallumer : retour aux défauts.
6. **Sauvegarde.** Régler LFO 2, sauver le kit, éteindre, rallumer, recharger : LFO 2 revient. Un son ou un projet
   de l'OS d'origine : LFO 2 sans effet (DEST None).
7. **p-locks.** Trig tenu sur la page 2, tourner DEP : le lock joue. Sauver le projet, recharger : le lock est
   toujours sur DEP de LFO 2, pas sur LFO 1.
8. **Avec Model-TG.** Locker Attack, Filtre et Résonance sur un pas, sauver, recharger : ils reviennent sur le bon
   paramètre.
9. **Charge.** 6 pistes avec LFO 2, 3 et 4 sur chacune : pas de craquement de plus.
10. **Sons de David.** Si Maxime a des sons sauvés avec le firmware de David : leur LFO 2 revient.

---

*Pour l'intégrateur* — ligne proposée pour `notes/README.md` :
`| 53 | **LFO 2, 3, 4 : trois LFO de plus par piste** (idée de DavidCaruso) | [LFO] répété → pages 2/3/4 ; vraie fonction des LFO de l'OS avec son état ; LFO 2 sauvé dans le son (+88..+91) et p-lockable, LFO 3/4 en mémoire ; corrige les p-locks Attack/Filtre/Résonance de Model-TG ; 1 844 o dans 7 masques, 1 180 o en 0x4233f000 ; +0,13 % sans LFO de plus, +3,5 % avec les trois | expérimental, prouvé en émulation |`
