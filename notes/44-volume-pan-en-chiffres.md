# 44 — Le volume et le pan de la piste en chiffres sur l'écran principal : le tweak `level-pan-values`

Mod de **djd_oz** (communauté), envoyé à Maxime le 06/10/2026 avec un deuxième mod (note 45) : l'archive
`Cycle_PAN_TriglessTrig_Mods.zip`, ici le fichier `model-cycles_OS1.13_PAN-Level-values-3s-turn-only.syx`, un OS 1.13
complet déjà modifié. Demande de Maxime : « Vérifie-les, dis-moi comment les tester sur ma machine pour ensuite les
intégrer au webflasher ». Tweak `46-level-pan-values.json` (`tools/gen_level_pan.py`, sources dans
`tools/machines/level_pan/`), preuve en émulation `tools/emu/test_level_pan.py`. Adresses : VA de l'OS 1.13.

## En bref

- **Sur l'écran principal, tourner LEVEL/DATA affiche le volume de la piste sélectionnée (0 à 127) en petits chiffres**
  à la place du haut-parleur de la barre de volume ; **FUNC + LEVEL/DATA affiche son pan (-64 à 63)** à la place du
  « R » de la barre de pan. Le chiffre reste 3 s après le dernier mouvement et part au redessin suivant de l'écran
  (3 à 4 s).
- **Effet de bord voulu par djd_oz et gardé** : sur l'écran principal, LEVEL/DATA avance de 1 par pas de l'encodeur au
  lieu de 2, pour que le chiffre passe par toutes les valeurs. Il faut tourner deux fois plus pour parcourir la
  plage ; le mode rapide (× 16) ne change pas.
- **Testé sur la machine (06/10/2026 et 07/10/2026)** par Maxime, avec tous les autres mods (§7).
- Le fichier de djd_oz est sain et se flashe seul (§1). Mais son code est ajouté après l'image et recopié au démarrage
  en `0x42339000`, comme celui de son autre mod : en l'état, il ne se combine ni avec Model-TG, ni avec les moteurs du
  Syntakt, ni avec l'autre mod. **Réécrit ici pour s'exécuter en place, dans deux masques de sprites libérés** : plus
  de crochet de démarrage, compatible avec tous les autres tweaks ; mêmes pixels que son fichier pour les 256 valeurs,
  même pas, même durée (§6).

## 1. Le fichier de djd_oz `[FAIT]`

Seule la section 3 (MAIN OS) diffère de l'officiel ; menu de démarrage (section 2), sections 4 et 5 et en-tête
identiques à l'octet près, HMAC valide avec la clé du Cycles. La section 3 est recompressée par un meilleur packer
aPLib (fichier plus petit que l'officiel) ; le vrai décompresseur du bootstrap la relit à l'identique.

| Écriture | Où | Quoi |
|---|---|---|
| A0 | `0x401aa140..0x401aa55c` | 1 052 o ajoutés après l'image, dans la zone remise à zéro au démarrage (BSS) : 52 o de recopie, puis 1 000 o recopiés en `0x42339000` (852 o de code, une police de 77 o, 66 o de variables à zéro) |
| P1 | `0x4000045c` | `jmp 0x401aa140` au début de la copie de `.data` en SRAM (appelée une fois, avant la remise à zéro du BSS et avant le cache) : la copie d'origine, puis celle de son code vers `0x42339000`, au-dessus de la fin du BSS (`0x423380b0`) |
| P2 | `0x400081f4` | cible du `jsr 0x40090f48` de la tâche de l'interface → compteur de ticks + 1, puis `0x40090f48` |
| P3 | `0x4001aa4e` | enveloppe du gestionnaire des encodeurs de l'écran principal |
| P4 | `0x4001aac4` | cible du `jsr 0x4006f73a` du pas de LEVEL/DATA → met le 2ᵉ argument à 1, puis `0x4006f73a` |
| P5 | `0x4001b22b` | enveloppe du dessin de l'écran principal |

Analyse et émulation de son fichier (Unicorn, vrai code de l'OS, d'origine contre modifié) : registres et pile rendus
partout, aucune écriture hors de l'écran, de la pile et de ses variables ; le démarrage laisse la SRAM et le BSS comme
l'origine. `0x42339000` est un trou de 32 Ko entre la fin du BSS et les premiers tampons DMA de l'OS (vus par l'alias
sans cache `0x4a340000`), que rien ne vise. **Verdict : se flashe seul sans risque**, et la récupération par le menu de
démarrage reste possible (seule la section 3 change).

Ce qui empêche de l'intégrer tel quel : nos tweaks Model-TG, moteurs du Syntakt et mesures de charge ajoutent leur
propre code au même endroit (`0x401aa140`) ; son autre mod (note 45) écrit les mêmes octets en `0x4000045c` et recopie
autre chose en `0x42339000`. Les combiner ferait sauter le démarrage dans le code d'un autre.

## 2. Ce que fait l'OS `[FAIT]`

| Où | Quoi |
|---|---|
| `0x40007d46` | tâche de l'interface (priorité 6, pile de 160 Ko) : boucle de messages, table de sauts `0x40008108` |
| `0x400081f2` | message 5 : `jsr 0x40090f48(0x400d0b12())`, service des minuteurs de l'interface. Le message 5 vient seul de l'interruption du minuteur DTIM3 (`0x4003eaf8`) : 135 168 000 / 16 / 281 600 = **30 Hz** |
| `0x400ffe20` | vtable de `MainScreenView` (l'écran principal : « TRn », barre de pan, barre de volume) |
| `0x4001aa4e` | case 17 : gestionnaire des encodeurs `(this, EncoderEvent*)` ; rend un octet dans d0 |
| `EncoderEvent` (vtable `0x400fbebc`) | `+12` numéro de l'encodeur (1 = LEVEL/DATA), `+16` pas (borné à ± 30 par 33 ms), `+20` mode rapide |
| `0x4001aab6..0x4001aac8` | `0x4006f73a(événement, 2, 16)` : pas × 2, × 16 en mode rapide ; décalé de 8 bits et ajouté à la valeur 8.8 |
| `0x4007faf4(1)` | FUNC tenu : LEVEL/DATA change le pan (paramètre `0x1c`, `0x4000b274`), sinon le volume (`0x4000a3ae`, borné à 0..127) |
| `0x4007faf4(2)` | TRK tenu `[HYP]` : le changement porte sur les 6 pistes |
| `0x40012412(0x4000eb90(0x400cf866()))` | piste sélectionnée (note 32) ; `0x4000eb9c(projet)` = kit |
| `vtable[28](0x400097f0(kit, piste), 0x1c)` | pan de la piste, en 8.8 centré sur 64 ; `0x40009c5a(kit, piste)` = volume (0 à 127) |
| `0x4001b22a` | case 4 : `draw(this, Bitmap*)` ; ne dessine rien quand `UIStates+88` (`0x4006b704(0x400cf9a8())`) est non nul, une fenêtre de valeur ouverte |
| `0x40076082(this)` | `View::setNeedsRedraw` |
| `0x4001bfe6..0x4001c020` | minuteur de `MainScreenView` à 1 Hz qui demande un redessin : l'écran principal est redessiné au moins une fois par seconde |
| `0x40070dea(bmp, x0, y0, x1, y1, couleur)` | rectangle plein, bornes comprises ; 0 = éteint |
| `Bitmap` | `+12` pas en mots de 32 bits par colonne (2 pour 128 × 64), `+16` données ; le pixel (x, y) est le bit `31 - (y & 31)` du mot `x × pas + y / 32` ; **y = 0 en bas** (note 39 §2) |

Tout tourne dans la tâche de l'interface : le tick (message 5), les encodeurs (message 1) et le dessin (minuteur de
rendu à 30 Hz, appelé depuis `0x40090f48`). Pas d'interruption, pas de course.

## 3. La réécriture

Même logique que djd_oz, mêmes fonctions de l'OS appelées dans le même ordre, même police, mêmes positions ; le code
s'exécute à sa place dans l'image, ses variables sont écrites à zéro dans l'image (rechargée depuis la flash à chaque
démarrage). Plus de recopie, plus de `0x42339000`.

| Accroche | Origine | Mod |
|---|---|---|
| `0x400081f2` | `jsr 0x40090f48` | `jsr lp_tick` : `lp_cnt + 1`, puis `jmp 0x40090f48` |
| `0x4001aa4e` | `lea -32(sp),sp ; movem.l d2-d7/a2-a3,(sp)` | `jmp lp_enc ; nop` |
| `0x4001aaba` | `pea 2` | `pea 1` (djd_oz détournait le `jsr` qui suit pour écrire 1 dans la pile : même effet) |
| `0x4001b22a` | `link a6,#-64 ; movem.l d2-d7/a2-a5,(sp)` | `jmp lp_draw ; nop` |

- `lp_enc` appelle l'original (les deux instructions déplacées puis `0x4001aa56`) et garde sa réponse. Pour
  l'encodeur 1 seulement : FUNC tenu → pan, sinon volume ; si la piste sélectionnée est < 6 (comparaison non signée),
  échéance = `lp_cnt + 90` (3,0 s) et drapeau de cette piste à 1, puis `setNeedsRedraw(this)`.
- `lp_draw` dessine l'original, puis, si aucune fenêtre de valeur n'est ouverte et que la piste est < 6 : le pan, puis
  le volume, s'ils sont encore à afficher. À l'échéance (`lp_cnt - échéance ≥ 0`, en signé : juste au passage de
  `0x7fffffff`), le drapeau est effacé.
- Pan : rectangle (114, 21)-(127, 29) effacé, puis à partir de x = 115 : « - » si négatif, la dizaine si non nulle,
  l'unité. Volume : rectangle (65, 8)-(77, 16) effacé, chiffres alignés à droite en x = 66, 70, 74 ; de 100 à 127,
  « 1 » puis toujours la dizaine. Chiffres de 3 × 7 points, lignes y0 à y0 + 6 (y0 = 22 pour le pan, 9 pour le volume).
- Police de djd_oz, un mot long par signe (7 lignes de 3 bits, celle du bas dans les bits de poids faible) :

```
 0   1   2   3   4   5   6   7   8   9   -
### .#. ### ### #.# ### ### ### ### ### ...
#.# ##. ..# ..# #.# #.. #.. ..# #.# #.# ...
#.# .#. ..# ..# #.# #.. #.. ..# #.# #.# ...
#.# .#. ### ### ### ### ### .#. ### ### ###
#.# .#. #.. ..# ..# ..# #.# .#. #.# ..# ...
#.# .#. #.. ..# ..# ..# #.# .#. #.# ..# ...
### ### ### ### ..# ### ### .#. ### ### ...
```

Ce que l'on voit (moitié droite de l'écran, x = 64 à 127, y = 29 à 8 ; pan -1, volume 100 ; `test_level_pan.py
--show`, sprites de l'OS) :

```
      origine                                                             avec les chiffres
y=29  ..............................##................................    ..............................##................................
y=28  ........##......################################...####.........    ........##......################################........#.......
y=27  ........##.....##################################..#####........    ........##.....##################################......##.......
y=26  ........##.....##.............##...............##..##.##........    ........##.....##.............##...............##.......#.......
y=25  ........##.....##.............##...............##..####.........    ........##.....##.............##...............##..###..#.......
y=24  ........##.....##.............##...............##..#####........    ........##.....##.............##...............##.......#.......
y=23  ........#####..##################################..##.##........    ........#####..##################################.......#.......
y=22  ........#####...################################...##.##........    ........#####...################################.......###......
y=21  ..............................##................................    ..............................##................................
  …
y=16  ............#...................................................    ................................................................
y=15  ...........##...................................................    ...#..###.###...................................................
y=14  ........#####..##.##.##.##.##.##.##.##.##.##.##.##.##.##........    ..##..#.#.#.#..##.##.##.##.##.##.##.##.##.##.##.##.##.##........
y=13  ........#####..##.##.##.##.##.##.##.##.##.##.##.................    ...#..#.#.#.#..##.##.##.##.##.##.##.##.##.##.##.................
y=12  ........#####..##.##.##.##.##.##.##.##.##.##.##.................    ...#..#.#.#.#..##.##.##.##.##.##.##.##.##.##.##.................
y=11  ........#####..##.##.##.##.##.##.##.##.##.##.##.................    ...#..#.#.#.#..##.##.##.##.##.##.##.##.##.##.##.................
y=10  ........#####..##.##.##.##.##.##.##.##.##.##.##.##.##.##........    ...#..#.#.#.#..##.##.##.##.##.##.##.##.##.##.##.##.##.##........
y= 9  ...........##...................................................    ..###.###.###...................................................
y= 8  ............#...................................................    ................................................................
```

Le « R » (x 115 à 119) et le haut-parleur (x 72 à 76) sont cachés tant que le chiffre est affiché ; les barres restent
visibles. « -64 » finit en x = 125 et « 127 » en x = 76 : tout tient dans les rectangles effacés.

Une amélioration possible, non faite pour rester fidèle au mod : demander un redessin à l'échéance ferait partir le
chiffre à 3,0 s pile au lieu de 3 à 4 s.

## 4. Place et conflits

- Code et variables dans deux masques de sprites 47 × 47 libérés (notes/14 §5, notes/32 §11 ; `tools/sprites.py`),
  identiques au masque gardé `0x40172220` et désignés seulement par la constante de leur constructeur, redirigée :
  `0x4018f4b4` (360 o sur 376 : tick, enveloppes, pan) et `0x4018fc74` (364 o sur 376 : piste, instructions
  déplacées, volume, police, puis `lp_cnt` en `0x4018fd9c`, `lp_pan` en `0x4018fda0`, `lp_lvl` en `0x4018fdc0` ;
  échéances des 6 pistes puis leurs drapeaux en +24).
- Aucune écriture commune avec les 81 autres tweaks du dépôt, ni avec chord-keys (PR #46 et #50) ; le navigateur
  multiligne en cours prend un autre masque (`0x401904b4`). Masques attribués le 07/10/2026 avec les autres branches
  en cours : les premiers choisis (`0x4018cd48`, `0x4018d1b8`) sont pris par chord-keys. `sdvintage-7th` et les moteurs du Syntakt écrivent dans
  le dessin de l'écran principal (`0x4001b69c`, le nom de la machine), loin des barres.
- Coût : 1 632 instructions par dessin quand les deux chiffres sont affichés, au plus 30 fois par seconde, dans la
  tâche de l'interface ; rien dans le chemin audio.

## 5. Le tweak

`46-level-pan-values.json`, 8 écritures : les deux masques (code), les deux constantes de leurs constructeurs, les
trois accroches et le `pea 1`. Les octets d'origine viennent du MAIN OS officiel et sont vérifiés par le générateur.

## 6. Preuve en émulation `[FAIT en émulation]`

`tools/emu/test_level_pan.py`, vrai code de l'OS, MAIN OS d'origine contre MAIN OS modifié (crochet de démarrage
exécuté), `--djd` contre le fichier de djd_oz, `--with` sur les autres mods :

| Cas | Origine | Modifié |
|---|---|---|
| Tick `0x400081f2` | `0x40090f48(arg)` | même appel, `lp_cnt + 1`, pile équilibrée |
| Pas de LEVEL/DATA, crans 1, -1, 3, 30, -7 | 2, -2, 6, 60, -14 | 1, -1, 3, 30, -7 (comme djd_oz) |
| Mode rapide, crans 1, -2 | 16, -32 | 16, -32 |
| Encodeur 1, piste 3 | — | échéance volume piste 3 = tick + 90, `setNeedsRedraw(this)`, réponse de l'original rendue |
| FUNC + encodeur 1, piste 6 | — | échéance pan piste 6 |
| Encodeurs 0 et 2, piste 6, piste -1 | — | rien |
| Dessin | — | l'original une fois, mêmes arguments ; d2-d7/a2-a6 et pile rendus ; écritures seulement dans l'écran |
| Fenêtre de valeur ouverte, échéance passée, autre piste, piste 6 | — | rien |
| Passage de `0x7fffffff` | — | affiché jusqu'à l'échéance |
| Pan -64 à 63, volume 0 à 127, sur un écran au hasard | — | rectangles effacés et chiffres du modèle (police lue à l'œil, indépendante du code) ; reste de l'écran inchangé ; **mêmes pixels que le fichier de djd_oz** |
| Un cran, puis le vrai tick | — | affiché aux ticks t à t + 89, plus à t + 90, comme djd_oz |

Avec `--with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max,boot-anim,trigless-dim
--syntakt Syntakt_OS1.42.syx`, et avec `chord-keys` (PR #50) à la place de Model-TG : tout ok.

## 7. Essais sur la machine

**Testé sur la machine (06/10/2026 et 07/10/2026)** par Maxime : avec la première version des trigless trigs
atténués, « ça marche parfaitement » ; puis avec la version 2 des trigless trigs et tous les autres mods (6 canaux,
Model-TG, les 5 moteurs du Syntakt, effacer un trig, arpégiateur, tempo 546, animation de démarrage ; MAIN OS
`366aebfc…7fe7540`) : « Tout le reste marche nickel ». La liste suivie :

- Les chiffres nets et à l'endroit, 0, 7, 99, 100, 127 pour le volume ; -64, -1, 0, 63 pour le pan.
- La durée : 3 à 4 s après le dernier mouvement.
- Le pas : combien de pas d'encodeur fait un cran de LEVEL/DATA (le décodeur `0x40059c18` en compte un toutes les deux
  transitions) ; l'origine avance donc de 2 ou 4 par cran, le mod de 1 ou 2. Maxime dit si ce pas plus fin convient.
- Le geste du mode rapide (code de touche 32, qui met `EncoderEvent+20` pour l'encodeur 1 seulement `[HYP]`).
- TRK + LEVEL/DATA : toutes les pistes bougent, seule la valeur de la piste sélectionnée s'affiche.
- Menus, navigateur, fenêtre de valeur d'un potard : aucun chiffre.

## 8. Crédit

Idée, police, positions et choix de djd_oz ; réécriture de ce projet. Crédit sur la carte du flasher et dans
`PROVENANCE.md`. Sa licence n'est pas encore connue : Maxime la lui demande avant la fusion.
