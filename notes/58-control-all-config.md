# 58 — Control All : choisir les pistes qu'il touche (tweak `control-all-config`)

Mod **Control All Config** de durchgemacht ([durchgemacht/cycles-control-all-config](https://github.com/durchgemacht/cycles-control-all-config),
MIT, version 1.0 du 17/10/2026, tag `v1.0`, commit `436e308`), porté ici par son auteur. Sur le Model:Cycles, Control
All (TRACK tenu + potard) touche toujours les six pistes ; les Digitakt et Digitone laissent choisir les pistes
concernées (« Control All Config »), d'où le nom. Tweak `49-control-all-config.json` (`tools/gen_control_all_config.py`,
source dans `tools/machines/control_all_config/`), preuve en émulation `tools/emu/test_control_all_config.py`.
Adresses : VA de l'OS 1.13.

## En bref

- **TRACK + TRIG 1-6 retire la piste 1-6 de Control All, ou l'y remet.** TRACK tenu, les TRIG 1-6 s'allument pour
  les pistes qui suivent et restent éteints pour les autres. Les pistes écartées gardent aussi leur machine, leur
  destination de LFO et PUNCH/GATE quand on les change TRACK tenu.
- **La piste active suit toujours**, comme sur les Digitakt et Digitone : ce que l'écran montre, le potard le fait. Le
  choix vit en RAM : après l'allumage, toutes les pistes suivent de nouveau, comme à l'origine.
- Dans l'OS, Control All n'est pas une fonction mais **cinq boucles `for (t = 0; t < 6; t++)`** (§1). Chacune reçoit
  un `jmp` de 6 o vers un stub qui rejoue les instructions déplacées pour une piste qui suit, ou passe à la piste
  suivante. Les touches et les LED passent par les deux entrées de vtable de `TrackSelectionView`, la vue que l'OS
  affiche TRACK tenu (§2).
- 494 o de code dans **quatre masques de sprites 48×22 libérés** (§4), aucune charge utile, aucun crochet de
  démarrage : le code ne tourne que TRACK tenu.
- **Testé par l'auteur sur son Model:Cycles** (14/10/2026, même code octet pour octet en 1.0 le 17/10/2026), dans son
  dépôt, où le code est logé dans deux autres masques (`0x4018d918`, `0x4016f8c8`). Ici le code est le même, relogé :
  `[FAIT en émulation]` (§7) ; `[À FAIRE]` le test de Maxime ; `"status": "experimental"` jusque-là.
- **Deux limites connues** : les deux boucles de LEVEL/DATA TRACK tenu (volume, et pan avec FUNC) ne sont pas
  couvertes (§5) ; une piste active écartée s'affiche éteinte mais suit quand même (§3).
- **PR #75 d'AveyCole** : contient une version antérieure de ce mod (base `429563b` = 0.1, piste active écartable,
  réécrite et placée ailleurs). Ce tweak est la version de l'auteur, 1.0, inchangée ; il ne dépend pas de #75, et
  c'est Maxime qui choisit (§5).

## 1. Control All dans l'OS : cinq boucles `[FAIT]`

Bedienung : TRACK tenu (`isKeyHeld(2)` = `0x4007faf4`, table `0x4010ae5c` → bitmap `0x40f95744` ; FUNC = 1) + un
geste. Chaque site teste TRACK puis boucle sur les pistes 0..5 ; aucun ne passe par une fonction commune.

| # | Site | Fonction | Boucle | Compteur | Ce qu'elle fait par piste |
|---|---|---|---|---|---|
| 1 | Potard sur la page des paramètres | `ParameterPageView::consumeEncoderEvent` `0x4001f4f0` (TRACK testé en `0x4001f886`, liste d'exceptions `0x4005a5cc(param)`) → vtbl+0x5c = `controlAll` `0x4001d6e4` | `0x4001d6f8`–`0x4001d752` | d2 | descripteur de la piste par `getParam` (vtbl+0x7c, `0x4001e814`), jeu de paramètres (vtbl+0x80), puis `set` (ps→vtbl+0x20) avec le delta |
| 2 | Valeur absolue sur toutes les pistes (profondeur du LFO, depuis `setLFO` `0x4001ecc4`) | vtbl+0x58 = `0x4001d590` | `0x4001d5a2`–`0x4001d5d6` | d2 | jeu de paramètres (vtbl+0x80), `set` |
| 3 | Destination du LFO | `ParameterPageView::setLFO` `0x4001eaa2` (TRACK en `0x4001eb1e`) | `0x4001ebd2`–`0x4001ebfc` | a3 | jeu de paramètres, puis `0x4000b274(ps, 0x20, dest, piste, 0, 0)` |
| 4 | TRACK + PUNCH / GATE (param 44 / 45) | `0x4001ac4a` (TRACK en `0x4001ac64` ; appelants `0x4001c2d2`, `0x4001caa2`) | `0x4001ac7a`–`0x4001ac88` | d2 | `0x4001abe2(touche, piste)` bascule PUNCH ou GATE |
| 5 | Écran MACHINES, molette | `0x400a28b4` → `0x400a2712(this, delta, TRACK tenu)` | `0x400a2798`–`0x400a27e0` | d2 (d4 += 12) | `0x40009c1a(pistes, piste)` puis `0x4001488a(machine, delta, piste, 0)` |

Les six premiers octets de chaque boucle sont des instructions entières, sans saut qui y entre (vérifié dans le
désassemblage : les `bne` de fin de boucle visent le début, qui est remplacé en entier) :

| Boucle | Début | Octets rejoués | Retour |
|---|---|---|---|
| 1 | `0x4001d6f8` | `2052 2668 007c` (`move.l (a2),a0 ; move.l 124(a0),a3`) | `0x4001d6fe` ; sortie `0x4001d754` |
| 2 | `0x4001d5a2` | `2052 2f03 2f02` (`move.l (a2),a0 ; move.l d3,-(sp) ; move.l d2,-(sp)`) | `0x4001d5a8` ; sortie `0x4001d5d8` |
| 3 | `0x4001ebd2` | `2052 4878 0020` (`move.l (a2),a0 ; pea 0x20`) | `0x4001ebd8` ; sortie `0x4001ebfe` |
| 4 | `0x4001ac7a` | `2f02 2f03 4e92` (`move.l d2,-(sp) ; move.l d3,-(sp) ; jsr (a2)`) | `0x4001ac80` ; sortie `0x4001ac8a` |
| 5 | `0x400a2798` | `2f02 2f05 4e94` (`move.l d2,-(sp) ; move.l d5,-(sp) ; jsr (a4)`) | `0x400a279e` ; sortie `0x400a27e2` |

Pas Control All : le masque 64 bits en +0x15c/+0x160 de l'état de l'interface (`0x400cf9a8`) est celui des pas tenus
(p-locks), itérateur `0x4006be48`. Les deux autres boucles « toutes les pistes » de l'écran principal, LEVEL/DATA
TRACK tenu, sont au §5.

## 2. TRACK tenu : `TrackSelectionView` `[FAIT]`

- `MainScreenView` pousse `TrackSelectionView` (vtable `0x40100ee0`) quand TRACK est enfoncé sans FUNC ni PATTERN
  (`0x4001cba0`) ; FUNC + TRACK ouvre TRACK SETUP. L'empilement est un `push_back` (`0x4007700e`), et les touches comme
  les LED parcourent la liste des vues par la fin (`0x4007739e`) : cette vue est servie la première tant que TRACK
  est tenu, et les lambdas de repli des touches sont vides.
- `consumeKeyEvent` `0x40024078` (vtbl+8 = `0x40100ee8`) : le relâchement de TRACK ferme la vue ; codes 9/10/11 =
  TRACK + RECORD / PLAY / STOP (copier / effacer / coller le preset). Événement : code en +12 (2 TRACK, 16..31 TRIG
  1..16), drapeaux en +16 (bit 0 appui, bit 3 répétition, bit 5 appui long).
- Producteur de LED : thunk `0x40023d8c` (vtbl+0xb8 = `0x40100f98`, arguments `view + 0x68`, `avail`, `out`) →
  `0x40023d18`, qui allume la LED 31 (TRACK). Les LED : singleton `0x400cfaf4()`, `0x40005f86(leds, led, état, …)`
  avec état 1 éteint / 2 allumé, premier écrivain gagnant ; LED n = TRIG n (table du pilote `0x4010abf8`) ; `out` est
  un ensemble de bits dont le mot 0 porte les LED 0..31 ; `0x400760ba(view)` demande le nouveau cadre de LED.
- **TRACK + TRIG n'a aucune fonction à l'origine** : l'appui traverse comme TRIG seul (grille en GRID RECORDING,
  sinon `KeyboardView` `0x4001a0d2`). Le mod prend donc une combinaison libre.
- Piste active : `0x40012412(0x4000eb90(0x400cf866()))` (projet → sa sélection de pistes (+48) → piste active 0..5).

## 3. Conception `[FAIT]`

`tools/machines/control_all_config/control_all_config.s`, 9 sections (`.cac_state`, `.cac_skip`, `.cac_loop1..5`,
`.cac_keys`, `.cac_leds`), assemblées par `m68k-elf-gcc -mcpu=54418` :

- **État** : marque `CAC1`, puis `cac_mask` (bit t = piste t écartée) et `cac_held` (bit t = l'appui de TRIG t+1 a
  été pris). 6 o, en RAM seulement : rien n'est enregistré avec le projet.
- **`cac_skip(d0 = piste)`** → 1 si Control All la laisse, sinon 0. Piste écartée **et pas active** → 1 ; la piste
  active suit toujours. Ne touche que d0-d1 (les boucles de l'OS ont tout le reste dans d2-d7/a2-a6).
- **Cinq stubs** `cac_loopN` : `cac_skip(compteur)` ; si la piste suit, rejouer les 6 octets déplacés et `jmp`
  début + 6 ; sinon avancer le compteur comme la fin de la boucle d'origine (`addq`, pour la 5 aussi `add.l #12,d4`)
  et reboucler, puis `jmp` sortie.
- **`cac_keys(view, event)`** devant `consumeKeyEvent` : TRACK → oublie les appuis en cours, passe à l'origine (la
  vue se ferme) ; TRIG 1-6 appuyé (ni répétition ni appui long) → bascule le bit de la piste, note l'appui, demande
  le redessin des LED, répond « pris » ; relâchement et répétition → pris seulement si l'appui l'a été, sinon ils
  passent à l'origine (une touche enfoncée avant TRACK garde son relâchement dans les vues du dessous) ; tout le reste
  (TRIG 7-16, RECORD, PLAY, STOP…) → `jmp` vers l'origine, pile inchangée.
- **`cac_leds`** devant le thunk : appelle le producteur d'origine avec ses trois arguments (LED TRACK), puis pour
  n = 0..5 `0x40005f86(leds, n + 1, écartée ? 1 : 2, 0x404a8c68)` et pose le bit n + 1 du mot 0 de `out`.
- **Piste active** : à l'origine du mod, l'auteur a essayé une version 0.2 où la piste active s'écarte aussi (testée
  sur sa machine : « funktioniert ») ; il a gardé le comportement 1.0 pour rester proche d'Elektron, où la piste
  active fait toujours partie de Control All, et parce que l'écran ne peut rien montrer d'honnête quand elle est
  écartée (Control All est un delta par piste, pas une valeur commune). Conséquence assumée : une piste active
  écartée a sa LED éteinte et suit quand même ; dès qu'une autre piste devient active, elle est écartée pour de bon.

## 4. Place et accroches `[FAIT]`

Le dépôt d'origine loge le code dans `0x4018d918` (41×41) et `0x4016f8c8` (34×34). Ici `0x4016f8c8` est pris par
lfo-plus (release 1.48) et `0x4018d918` est demandé par les PR #87 et #75 : le code est relogé dans quatre masques
48×22 (192 o chacun, 42 libres, [52](52-registre-place-libre.md)) que les PR ouverts ne demandent pas non plus
(`python3 tools/registry.py --git origin/pr/75 --git origin/pr/87 --git origin/pr/92`). `cac_skip` lit `cac_mask` et
les boucles appellent `cac_skip` **en relatif au PC** (déplacement 16 bits, ± 32 Ko) : l'état, `cac_skip` et les
boucles restent voisins ; `cac_keys` et `cac_leds` désignent l'état en absolu et vont n'importe où. Avec cette
disposition, le dépôt d'origine rebâtit son image 1.0 octet pour octet.

| Masque | Constante redirigée | Contenu | Octets |
|---|---|---|---|
| `0x4018b9c8` | `0x400ad048` → `0x4014b364` | état, `cac_skip`, `cac_loop1..3` | 164 / 192 |
| `0x4018bb48` | `0x400ad028` → `0x4014b364` | `cac_loop4`, `cac_loop5` | 78 / 192 |
| `0x4018cbc8` | `0x400acdce` → `0x4014b364` | `cac_keys` | 138 / 192 |
| `0x4018d038` | `0x400acd92` → `0x4014b364` | `cac_leds` | 114 / 192 |

Les quatre masques sont identiques au masque gardé `0x4014b364` (vérifié par le générateur sur le fichier de
l'utilisateur), et chacun n'est désigné que par la constante de son constructeur. Les 15 écritures : 4 de code, 4 de
redirection, les 5 `jmp` des boucles (`4ef9` + adresse du stub) et les 2 entrées de vtable (`0x40100ee8` → `cac_keys`,
`0x40100f98` → `cac_leds`). Le générateur vérifie que chaque stub contient les 6 octets qu'il rejoue et le `jmp` de
retour vers début + 6.

## 5. Conflits, cohabitation et limites `[FAIT]`

- `tools/check_overlaps.py` : aucune écriture partagée avec un tweak de `main`. Les cinq boucles, leurs retours et
  les deux entrées de vtable ne sont écrits par personne d'autre ; level-pan-values (46) enveloppe `0x4001aa4e` sans
  toucher les boucles.
- **PR #75 (AveyCole)** : contient ce mod (`tools/gen_control_all_config.py`, source `429563b` = version 0.1, licence
  recopiée), dans sa variante « piste active écartable », réparti dans les queues libres de neuf masques, testé par
  AveyCole sur sa machine. Ce tweak est la version de l'auteur, 1.0, inchangée, dans quatre masques que les PR
  ouverts ne demandent pas. Les deux ne peuvent pas entrer ensemble (mêmes accroches) ; lequel entre, Maxime le
  décide ; ce PR ne dépend pas de #75.
- **PR #92 (djdoz, `49-octave-shortcuts`)** : TRACK + TRIG 1 / 16 = octave, par la vtable de `KeyboardView`
  (`0x400ff9cc`). Avec les deux mods, `cac_keys` prend TRIG 1 (TrackSelectionView est au-dessus) : l'octave vers le
  bas ne répond plus. `check_overlaps` ne le voit pas (pas les mêmes octets) : si les deux entrent, déclarer
  `conflicts` ou changer la touche de l'un. Le numéro 49 est aussi celui que demandent #92, #63 et #75 : à fixer au
  moment de l'intégration.
- **Non couvert** : le gestionnaire des encodeurs de l'écran principal `0x4001aa4e` a deux autres boucles « toutes les
  pistes » TRACK tenu : LEVEL/DATA = volume (`0x4001abac`–`0x4001abcc`, compteur d3, tête `2f03 2f02 4e93`) et
  FUNC + LEVEL/DATA = pan (`0x4001ab3a`–`0x4001ab76`, d3, tête `2f03 2f02 4e92`) ; Maxime a confirmé sur la machine que
  « TRK + LEVEL/DATA : toutes les pistes bougent » ([44 §7](44-volume-pan-en-chiffres.md)). Le mod 1.0 ne les
  accroche pas : volume et pan suivent Control All sur les six pistes, même pour une piste écartée. Deux stubs de
  plus dans le même moule les couvriraient (34 o chacun) ; décision de l'auteur en attente.
- **Retour à l'OS officiel** : rien n'est enregistré, rien à faire.

## 6. Le tweak `[FAIT]`

`tweaks/model-cycles_OS1.13/49-control-all-config.json`, produit par `python3 tools/gen_control_all_config.py --cycles
model-cycles_OS1.13.syx` (`--check` compare au fichier versionné) : `id` `control-all-config`, `order` 49, 15 écritures,
`symbols` (état, `cac_skip`, les stubs, `cac_keys`, `cac_leds`) pour la preuve, `version` `v1.0`, `source` = l'arbre du
commit d'origine. Le générateur assemble la source recopiée (`m68k-elf-gcc -mcpu=54418`, `ld` avec un script posant
les quatre sections de sortie), refuse une section trop grande, un masque différent du masque gardé, des octets
d'origine inattendus sous une accroche, un stub qui ne rejoue pas ses octets. `python3 tools/build.py -i
model-cycles_OS1.13.syx -t control-all-config` : toutes les vérifications du builder passent ; le MAIN OS modifié ne
diffère de l'original qu'aux 15 écritures (vérifié octet par octet).

## 7. Preuve en émulation `[FAIT en émulation]`

`tools/emu/test_control_all_config.py` (écrit d'après `test_level_pan.py` et `t7.UI`) fait tourner le vrai code de
l'OS, d'origine et modifié, les fonctions qu'il appelle interceptées (arguments notés, réponse connue) :

| Vérification | Origine | Modifié |
|---|---|---|
| 1. Écritures, masques identiques au masque gardé, redirections, aucun chevauchement, état à zéro | — | ✓ |
| 2. `cac_skip` : écartée → 1, qui suit → 0, active → 0 ; d2-d7/a2-a6 intacts | — | 5 masques × 6 pistes actives |
| 3. Les cinq boucles, fonctions de l'OS appelées avec les mêmes arguments | 6 pistes | les pistes qui suivent, l'active toujours |
| 4. `cac_keys` : appui, relâchement, répétition, TRACK, TRIG 7-16, pile rendue | — | ✓ |
| 5. `cac_leds` : producteur d'origine, TRIG 1-6 allumés/éteints, bits de `out`, pile rendue | — | ✓ |
| 6. `--with` les autres mods | idem | idem |

Exécutée le 17/10/2026 (Unicorn 2, hors sandbox) : **TOUT OK**, seule et avec `6ch-usbup, model-tg-st,
syntakt-tg-sd-cp-toy-bits-swarm, arp, trig-hold, tempo-max, boot-anim` (Syntakt 1.42). Une correction au premier
essai : la molette interceptée de l'écran MACHINES doit rendre une machine différente de celle affichée, sinon le
code d'origine passe par la mise à jour de l'icône (`0x400a27ba`) et lit les pointeurs de l'objet factice. Le
smoke test du flasher (`tools/webflash_smoke.sh` avec les deux fichiers officiels) passe aussi : 1 188
combinaisons de référence, chacune avec `control-all-config`.

## 8. Ce que Maxime doit tester

Flasher `control-all-config` seul, puis avec Model-TG, les moteurs du Syntakt et les autres mods cochés :

1. Sans rien changer : TRACK tenu + potard change les six pistes, comme à l'origine ; TRACK tenu, TRIG 1-6 allumés.
2. TRACK + TRIG 3 : la LED 3 s'éteint (TRACK tenu) ; TRACK tenu + potard : la piste 3 ne bouge plus, les autres oui.
   TRACK + TRIG 3 de nouveau : elle revient.
3. Piste 3 écartée, piste 3 sélectionnée : TRACK tenu + potard la change quand même (l'écran suit) ; sélectionner la
   piste 1 : la 3 est de nouveau écartée.
4. Piste écartée : TRACK + MACHINES (molette), TRACK + PUNCH / GATE, TRACK tenu + choix de destination du LFO ne la
   touchent pas.
5. TRIG 7-16, TRACK + RECORD / PLAY / STOP, la grille et le clavier : comme à l'origine. Éteindre et rallumer : toutes
   les pistes suivent.
6. Limite connue : TRACK tenu + LEVEL/DATA (volume) bouge encore les six pistes, écartées comprises.
