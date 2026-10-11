# 50 — MACRO et les moteurs du Syntakt sur la même machine

Demande de Maxime, le 07/10/2026 dans le fil de la machine MACRO, après l'avoir testée : « J'aimerai que le mod MACRO
soit combinable avec les mod syntakt. Les avoirs sur la machine tout les deux. » Jusqu'ici le flasher rendait les deux
cartes exclusives ([43 §6](43-machine-macro.md)). Tweaks `24-syntakt-<moteurs>-macro.json` (seuls) et
`31-syntakt-tg-<moteurs>-macro.json` (avec Model-TG), 31 combinaisons de moteurs chacun ; générateur
`tools/gen_macro_syntakt.py` ; preuve `tools/emu/test_macro_syntakt.py`. Adresses : VA de l'OS 1.13.

## Réponse courte

- **Les deux ensemble, MACRO en dernier** : les moteurs cochés gardent leurs numéros (à partir de la 7ᵉ machine, de la
  8ᵉ avec Model-TG), MACRO prend la machine suivante. Avec Model-TG et les 5 moteurs : Sampler 7ᵉ, moteurs 8ᵉ à 12ᵉ,
  MACRO 13ᵉ.
- **Une seule charge utile** porte les deux : la partie des moteurs est exactement celle de leur tweak (passerelle
  reprise octet pour octet, celle qui a été testée sur la machine), MACRO est posée au-dessus.
- **La place** : en clair, moteurs + MACRO dépassent la limite de l'image décompressée (`0x40200000`) d'environ 80 Ko
  avec Model-TG. La charge utile entière est donc rangée **compressée** (aPLib, la variante d'Elektron déjà utilisée
  pour la section 3) et décompressée au démarrage : 471 792 o en mémoire, 229 à 241 Ko dans l'image ; pire cas
  (Model-TG + 5 moteurs + MACRO) fin à `0x401fa5f4`, **23 052 o de marge** (§3).
- **Le régulateur de charge des moteurs** ([25](25-regulateur-de-charge.md), [36](36-regulateur-sans-coupures-inutiles.md))
  **veille aussi sur les pistes MACRO** dans ces combinaisons ; MACRO seule n'en a toujours pas.
- **Flasher** : les deux cartes se cochent ensemble ; la combinaison de moteurs prend alors sa version avec MACRO.
- **Prouvé en émulation** `[FAIT en émulation]` (§6). 1er essai sur la machine (10/10/2026) : blocage au logo
  Elektron, dû au cache d'instructions, corrigé (§8). **Testé sur la machine (10/10/2026)** avec Model-TG et les 5
  moteurs (§9) ; les autres combinaisons, en émulation seulement.

## 1. Pourquoi ce n'était pas possible tel quel `[FAIT]`

Les deux mods sont construits de la même façon (machines ajoutées, [20](20-moteurs-syntakt-a-cocher.md),
[43 §2](43-machine-macro.md)) et prennent les mêmes places :

| | Moteurs du Syntakt | MACRO seule |
|---|---|---|
| Charge utile au démarrage | `0x43000000` (`0x46700000` avec Model-TG) | idem |
| Disposition des tables, détours, descripteurs (`gs.LAYOUT`) | `+0x33000..0x36000` | idem |
| Crochet de démarrage | masque `0x4016cae8`, appelé à `0x400004b2` (ou par le `jsr` de `0x40000530` avec Model-TG) | idem |
| 1ʳᵉ machine ajoutée | 6 (7 avec Model-TG) | idem |

Les poser l'une après l'autre ne marche donc pas : il faut une charge utile commune, une seule table des machines
ajoutées (N moteurs + 1) et un seul crochet.

## 2. Montage

`gen_macro_syntakt.py` appelle `gen_syntakt_engines.build_tweak(…, own=…)` : les machines « à nous » (`own`) viennent
après les moteurs, avec leurs propres `update`/`render` et leurs morceaux de charge utile.

- **Moteurs** : exactement à la place que leur donne leur tweak (`24-syntakt-….json`, `31-syntakt-tg-….json`). Leur
  passerelle (`tools/machines/syntakt_bridge/`, compilée par `m68k-elf-gcc` 16.2, régulateur en assembleur `gov_asm.py`)
  **n'est pas recompilée** : un autre GCC donnerait d'autres octets, et ceux-là ont été testés sur la machine. Ses
  octets sont repris du tweak versionné ; ses symboles aussi (champ `gov`, tables `update`/`render` des données), et
  vérifiés en réassemblant ses détours : ils doivent redonner les octets du tweak. Avec Model-TG, l'adresse de
  `voice_done` se lit en assemblant les détours avec une valeur bidon et en comparant les 4 octets qui changent.
- **MACRO** : son code (Braids et sa passerelle, `tools/machines/macro/`) est compilé comme pour `25-macro.json`
  (`m68k-linux-gnu-g++` 13.3) à `PAY + 0x42000`, ses variables (6 voix de Braids) à `PAY + 0x5a000` ; fin de la charge
  utile à `PAY + 0x732f0` (471 792 o). Avec Model-TG, tout reste sous `PAY_TG + 0x100000`, le dernier Mo de la zone
  d'échantillons que Model-TG nous laisse ([31 §4](31-model-tg.md)).
- **Tables, détours, descripteurs, bornes** : ceux de `gen_syntakt_engines.py` pour N + 1 machines (au plus
  `MAX_EXTRA` = 6 : 5 moteurs + MACRO). Le dispatch envoie MACRO à ses `update`/`render` ; ses potards, son icône (celle
  de TONE) et sa chaîne d'ampli sont ceux de [43 §2](43-machine-macro.md).
- **Régulateur de charge** : celui de la passerelle des moteurs ([36](36-regulateur-sans-coupures-inutiles.md)) passe
  par le détour de la boucle des voix, que MACRO emprunte aussi : les pistes MACRO y entrent comme les autres (quand la
  charge reste trop haute, la voix qu'on entend le moins s'éteint en fondu ; jamais le Sampler ni la piste que Model-TG
  enregistre ou édite). MACRO seule n'a toujours pas de régulateur ([43 §11](43-machine-macro.md)).

## 3. Place : charge utile compressée `[FAIT]`

Les moteurs rangent leur charge utile en clair (seuls) ou en morceaux non nuls (avec Model-TG, `PACK`) ; MACRO seule
en morceaux (103 552 o). Ensemble, en morceaux, il manque environ 80 Ko avec Model-TG sous `0x40200000`. Toute la charge
utile est donc rangée compressée (`append.compress = "aplib"`) :

- au build (`tools/build.py`, `docs/flasher/builder.js`) : `aplib_grow.pack` / `aplibPack`, le même compresseur glouton
  que pour la section agrandie ([17](17-portage-exact-syntakt.md)), sans l'en-tête de 8 o ; même flux en
  Python et dans la page (`tools/webbuild_check.sh`) ;
- au démarrage : le crochet (`stub.S`, `APLIB`) décompresse de la fin de l'image vers `PAY` (zéros compris : les
  variables de MACRO et du Syntakt n'ont plus à être remises à zéro), puis appelle son **2ᵉ étage** (`BOOT2`), rangé
  dans la charge utile entre la fin des moteurs et MACRO.

Le crochet entier (décompression, tables de CHORD, deux copies vers la SRAM) faisait 252 o ; le masque `0x4016cae8`
n'en laisse que 192 au crochet, l'arpégiateur ayant la suite (`gen_arp.py`, `.cave_menu` à `0x4016cba8`) :
`tools/ref_mainos.py` l'a trouvé (octets `old` de l'arpégiateur). D'où les deux étages : 188 o au masque (180 avec
Model-TG, qui finit par `jmp boot_extra_hook`), `gen_syntakt_engines.py` vérifie la limite (`STUB_END`). Le 2ᵉ étage
(`BOOT2`, 60 o environ) :

1. **recopie les tables d'ondes de CHORD** de la SRAM (`0x80001c5c`, 22 tables, et `0x8000cac0`, 8 tables), où l'OS
   vient de les mettre (`0x4000045c`), à leur place dans la charge utile (`chord_at`, [28](28-code-syntakt-en-sram.md)). Le
   tweak des moteurs les recopie au build depuis le MAIN OS de l'utilisateur (morceaux `cycles`) ; ici, les reprendre
   en SRAM évite de ranger 30 840 o peu compressibles dans l'image ;
2. **copie le code du Syntakt en SRAM**, puis les états de voix, comme le crochet des moteurs.

| | Seuls (`syntakt-<moteurs>-macro`) | Avec Model-TG (`syntakt-tg-<moteurs>-macro`) |
|---|---|---|
| Charge utile en mémoire | 471 792 o à `0x43000000` | 471 792 o à `0x46700000` |
| Dans l'image (compressée) | 229 134 o (SYToy) à 240 674 o (les 5) | 229 403 o (SYToy) à 240 948 o (les 5) |
| Fin de l'image décompressée (limite `0x40200000`) | `0x401e4d62` au plus (marge 111 262 o) | `0x401fa5f4` au plus (marge 23 052 o) |
| Crochet au masque `0x4016cae8` (192 o au plus) | 188 o | 180 o |
| Décompression au démarrage (émulation, flux de 241 Ko) | ~4,4 millions d'instructions | idem |

La décompression ajoute au démarrage quelques dizaines de millisecondes `[HYP]` (4,4 millions d'instructions à
250 MHz), cachées par le chargement du projet ; à vérifier à l'oreille et à l'œil sur la machine.

## 4. Le flasher

- `tools/gen_flasher_tweaks.py` : la carte MACRO perd `excludes` et gagne `joins: "syntakt"` ; chaque combinaison de
  moteurs porte sa version avec MACRO (`combo.macro` : `id`, `tg`, `tested`, `tg_tested`, d'après `HW_TESTED` et
  `HW_TESTED_TG` de `gen_macro_syntakt.py`). Dans `app.js`, MACRO cochée avec les moteurs n'ajoute aucun tweak
  (`joinedTo`), les moteurs prennent `combo.macro` (`versionOf`), Model-TG prend toujours `model-tg-st`. Les badges
  suivent les essais de la combinaison avec MACRO ; la carte des moteurs dit « + MACRO » et que MACRO vient en dernier.
- **Valeurs partagées dans `tweaks.js`** : le code de MACRO (196 Ko en hexadécimal) est le même dans les 31 tweaks
  seuls, et dans les 31 avec Model-TG. `gen_flasher_tweaks.py` range une seule fois toute valeur d'au moins 2 Ko qui se
  répète (`shared`, `{"$shared": k}`) et `tweaks.js` les remet en place au chargement ; `read_js()` fait de même en
  Python (`tools/ref_mainos.py`) et vérifie qu'on retrouve les tweaks de `tweaks/` à l'identique. `tweaks.js` passe de
  3,5 Mo à 4,5 Mo au lieu de 18 Mo. Les JSON de `tweaks/` restent complets.
- Vérification mod par mod ([49](49-verification-mod-par-mod.md)) : chaque tweak combiné a son empreinte dans
  `REF_MODS` (écritures, et charge utile telle que rangée, donc compressée) ; l'échantillon de `REF_MAINOS` compte
  chaque combinaison de moteurs avec MACRO (les paires de cartes) et les plus grandes combinaisons ; `tools/ref_mainos.py`
  suit `joins` comme `app.js`. `tools/check_overlaps.py` compte une charge utile compressée pour sa taille rangée,
  `append.stored`, que `gen_macro_syntakt.py` mesure avec le Syntakt OS 1.42 (le build revérifie la limite).

## 5. Incompatibilités

- **SD VINTAGE** hors du flasher (`sdvintage-*`, `syntakt-vintage`, `syntakt-meter`…) : même crochet, même charge
  utile, comme pour les moteurs seuls.
- Une version combinée ne va ni avec `macro`/`macro-tg`, ni avec les tweaks des moteurs seuls, ni avec une autre
  version combinée (`conflicts`) : le flasher n'en prend qu'une. Sans Model-TG, elle ne va pas avec `model-tg-st`.
- Avec les autres mods du flasher (6 canaux, arpégiateur, trig-hold, tempo, animation, drumkilla, écoute des samples
  `sample-preview-st` avec Model-TG, [46](46-ecoute-des-samples.md)) : les écritures communes sont identiques
  (redirections de sprites, envoi USB à heure fixe), aucune ne diffère.

## 6. Preuve en émulation `[FAIT en émulation]`

`tools/emu/test_macro_syntakt.py`, sur le vrai code de l'OS (Unicorn), avec la charge utile telle que le crochet la
décompresse. Références : les moteurs seuls (leur tweak) et MACRO seule (`25-macro`, `32-macro-tg`, elle-même identique
à Braids compilé pour l'ordinateur, [43 §7](43-machine-macro.md)).

Résultats avec les 5 moteurs (`--only alone`, `--only tg`) : **TOUT OK** (36 et 28 vérifications) ; avec SDVtg seul
(`--engines sd`, les deux versions) : **TOUT OK** (64).

| Vérification | Seuls (MACRO 12ᵉ) | Avec Model-TG (MACRO 13ᵉ) |
|---|---|---|
| Décompresseur du bootstrap : l'OS agrandi relu à l'identique | fin `0x401e4d62` | fin `0x401fa5f4` |
| Crochet : appelé, décompresse, appelle le 2ᵉ étage, rend la main ; pile et d2..d7/a2..a6 intacts | `0x400004b2`, reprise à `0x400004ba` | `jsr 0x40000530`, puis `boot_extra_hook` |
| Charge utile décompressée (471 792 o, zéros compris), tables de CHORD reprises en SRAM | rangée en 240 674 o | rangée en 240 948 o |
| Partie des moteurs identique à celle des moteurs seuls (hors détours, données, descripteurs) | 1 952 o diffèrent au plus | 2 268 o au plus |
| SRAM : code et voix du Syntakt en place, le reste intact | oui | oui |
| Interface : tables de l'OS, descripteurs, CC, écran MACHINES, molette, potards, changement de machine, icônes | 12 machines | 13 machines, Sampler compris |
| MACRO avant la chaîne d'ampli : identique échantillon par échantillon à Braids compilé pour l'ordinateur (12 cas) | oui | oui |
| Voix MACRO calculée exactement quand l'OS l'impose (1 799 blocs), par blocs de 24 échantillons | oui | oui |
| Les 6 machines d'origine (CHORD compris) et chaque moteur : identiques aux moteurs seuls | oui | oui |
| Piste MACRO identique à MACRO seule (9 modèles) ; 6 pistes mêlées (origine, moteurs, MACRO) | oui | oui (Sampler compris) |
| Machine locks SNARE → moteur → MACRO → TONE → moteur → MACRO → KICK sur une piste | tout joue | tout joue |
| Régulateur, charge fixe de 97 % : toutes les pistes MACRO éteintes, muettes ensuite | 6 sur 6 | 5 sur 5, jamais le Sampler |
| Régulateur, charge de 46 % + 7 % par voix calculée : une partie seulement, les autres identiques à la référence | 1 éteinte | 1 éteinte, jamais le Sampler |

Le régulateur lit les gains du mixeur de l'OS (`gov_gains.S`) : la preuve met le BSS de l'OS en mémoire et ces gains
au maximum, comme `test_governor.py`. Avec les autres mods (`--with 6ch-usbup,trig-hold,arp,tempo-max,boot-anim`, et
avec `model-tg-st,sample-preview-st` en plus) : **TOUT OK** (13 vérifications chacune : démarrage, charge utile et
SRAM, machines d'origine et moteurs, MACRO, pistes mêlées, machine locks, régulateur ; l'interface n'y est pas refaite).
L'écoute des samples avec cette combinaison (`tools/emu/test_sample_preview.py --with 6ch-usbup,model-tg-st,
syntakt-tg-sd-cp-toy-bits-swarm-macro,trig-hold,arp,tempo-max,boot-anim`) : **TOUT OK** (84 vérifications).

Flasher (`tools/webflash_smoke.sh` avec les fichiers officiels) : **ALL OK**, 646 vérifications ; les 495 combinaisons
de l'échantillon construites dans la page, chacune à son empreinte, dont 93 avec les moteurs et MACRO.

## 7. À vérifier sur la machine

1. Flasher Model-TG + les 5 moteurs + MACRO (le pire cas pour la place) : démarrage normal, sans attente visible de
   plus. MACHINES : Sampler 7ᵉ, SDVtg … SYSwm, puis MACRO 13ᵉ, avec l'icône de TONE.
2. Chaque moteur sonne comme avant ; MACRO comme avant (SHAPE, COLOR, SWEEP, CONTOUR, DECAY/GATE/PUNCH) ; CHORD sonne
   juste (ses tables d'ondes sont reprises de la SRAM au démarrage).
3. Machine locks entre un moteur, MACRO et une machine d'origine sur une même piste.
4. Charge : deux ou trois pistes MACRO lourdes (WAVE MAP) avec des moteurs : le régulateur doit éteindre en fondu une
   voix plutôt que de laisser craquer le son.
5. Sans Model-TG, une petite combinaison (SDVtg + MACRO : MACRO 8ᵉ).
6. Avant de reflasher autre chose, remettre sur une machine d'origine les pistes qui utilisent une machine ajoutée.

## 8. Essai du 10/10/2026 : blocage au logo Elektron, cache d'instructions `[FAIT]`

**Essai de Maxime** (fichier Model-TG + les 5 moteurs + MACRO, avec 6ch-usbup, sample-preview, trig-hold, arp,
tempo-max, boot-anim) : la mise à jour passe, puis la machine reste sur le logo Elektron, avant l'animation de
démarrage (carrés), et ne répond plus. En émulation, le même fichier démarrait jusqu'à l'animation.

**Diagnostic** (fichier jamais versionné) : 6 marques à l'écran, la 1ʳᵉ juste après la décompression, les autres
dans `main` et la tâche de démarrage. Sur la machine, **aucune** ne s'affiche. Écartés : la place (une image plus
grande, `0x401fae10`, a déjà été testée), le bootstrap (relit et décompresse les deux conteneurs à l'identique,
`0x80000820` ; rien n'écrit dans la zone de la charge utile après), le chien de garde, des instructions hors
ColdFire (`-mcpu=54418`), la SDRAM non initialisée (démarrage émulé avec une mémoire pleine de valeurs au hasard :
même parcours que la version testée).

**Cause** : le bootstrap, avant de sauter dans l'OS, laisse le **cache d'instructions actif** (`CACR = 0x0008c000`,
`0x80000886` : IEC + BEC, cache de données coupé ; adresses de la SDRAM cachables par défaut). Ce cache n'est pas
cohérent avec les écritures. Le crochet décompresse le 2ᵉ étage (`BOOT2`, `0x46741b00` avec Model-TG) comme des
données, puis y saute **sans invalider** le cache. Or le crochet passe des centaines de milliers de fois sur
`jsr AFTER` en lecture anticipée (juste après le `rts` de la lecture du gamma) : le pipeline de lecture d'instructions
du V4e, qui prédit les changements de flot, peut remplir le cache avec ces adresses **avant** qu'elles soient écrites,
donc avec l'ancien contenu de la SDRAM. Au saut, le processeur exécute ces lignes périmées. La marque 0 du diagnostic était
elle aussi du code fraîchement écrit (`0x46741c00`), d'où aucun carré. Les versions testées (moteurs seuls, avec ou
sans Model-TG, MACRO seule) n'exécutent jamais pendant le crochet du code qu'il vient d'écrire : leur code ne tourne
qu'après le `movec cacr` de l'OS (`0x40000548`, `0xa50ce100` : ICINVA + BCINVA). Cohérent avec tout ce qui est
observé ; le fichier corrigé démarre (§9).

**Correction** (`stub.S`, `APLIB`) : avant `jsr AFTER`, `nop` (écritures terminées), `movec` de `0x000cc100` dans
`CACR` (la valeur du bootstrap à `0x80000c40` : caches d'instructions et de branchements invalidés, toujours actifs,
cache de données toujours coupé), `nop`. 14 o de plus : crochet de 188 o (180 avec Model-TG), sous les 192 o.

**Preuve** : Unicorn n'a pas de cache ; `test_macro_syntakt.py` (démarrage) le modélise : toute ligne de 16 o écrite
dans la charge utile est périmée jusqu'au prochain `movec …,cacr` avec ICINVA, et exécuter une ligne périmée est une
faute. Ancien crochet : **ÉCHEC** (`0x43041b00`, `0x46741b00`) ; crochet corrigé : ok.

## 9. Testé sur la machine (10/10/2026)

Fichier corrigé (`…_avec-model-tg_v2.syx`, MAIN OS `f44bfad6…`) : Model-TG + les 5 moteurs + MACRO, avec 6ch-usbup,
sample-preview-st, trig-hold, arp, tempo-max et boot-anim, construit par `build.py`. Retour de Maxime : « ça marche
nickel ». La combinaison des 5 moteurs avec Model-TG est marquée testée (`HW_TESTED_TG` de `gen_macro_syntakt.py`) ;
les autres combinaisons, et la version sans Model-TG, restent vérifiées en émulation seulement.
