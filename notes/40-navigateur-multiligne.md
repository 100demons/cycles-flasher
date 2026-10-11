# 40 — Le navigateur sur plusieurs lignes (tweak `multiline-browser`)

Demande d'un membre de la communauté, transmise par Maxime le 05/10/2026 : retrouver le « menu de fichiers multiligne »
qu'il avait sur son Model:Samples, avec une police de taille plus raisonnable, et en faire une option à part du flasher.
Il l'avait obtenu avec un script Python qui modifiait `30-model-tg-st.json` (§1) ; il savait que le prochain build de
Modded Cycles le casserait. Tweak `44-multiline-browser.json` (`tools/gen_multiline_browser.py`, code dans
`tools/machines/multiline_browser/`), preuve `tools/emu/test_multiline_browser.py`. Adresses : VA de l'OS 1.13.

## En bref

- Le navigateur de l'OS (ModelsFileManager : presets, dossiers, échantillons du Sampler de Model-TG) est déjà une liste
  qui sait afficher plusieurs lignes ; son constructeur règle le nombre de lignes visibles à **1**, et le dessin met
  chaque ligne en y = 20, en grande police.
- Le tweak : **3 lignes de 13 px en petite police** (celle du titre), la 1ʳᵉ en haut ; « > » devant la ligne du curseur ;
  le son chargé inversé autour de son nom, comme à l'origine ; un repère de 7 px pour un dossier à la place de son icône
  de 25 × 22 ; les flèches en face de la 1ʳᵉ et de la dernière ligne. Repris du script : 3 lignes de 13 px, la petite
  police, « > » en x 2, les noms en x 9 ; l'ordre des lignes, le son chargé, le repère de dossier et les flèches sont
  propres au tweak (§1, §3).
- Dans un sous-dossier de +Drive, l'OS remet la 1ʳᵉ ligne visible sur le curseur après chaque déplacement : avec
  3 lignes, le « > » resterait en haut. Le tweak garde la fenêtre de la liste ; le « > » suit le curseur partout (§2, §3).
- Il se combine avec tout : seule la ligne du curseur passe par l'appel que browser-scroll et Model-TG détournent pour
  faire défiler les noms longs (§4).
- 16 écritures, 370 o de code dans un masque de sprite 47 × 47 libéré.

## 1. Le script du contributeur `[FAIT]`

Lu comme une donnée (collé par Maxime ; pastebin n'est pas joignable d'ici), jamais exécuté tel quel. Il repart d'une
copie `.bak` de `30-model-tg-st.json`, puis :

| Écriture | Rôle |
|---|---|
| retire 5 écritures (offsets 676257, 1342242, 1342245, 1342372, 1343984 : `0x400a55a1`, `0x40147f22`…`0x401485f0`) | le défilement des noms longs (browser-scroll dans Model-TG) |
| 128 o en `0x400a5588` : `jmp 0x4015c044` puis 61 `nop` | remplace le dessin du nom et du son chargé, jusqu'à `0x400a5608` |
| 180 o en `0x4015c044`, et `0x400b6434` : `0x4015c044` → `0x40154ae4` | son code, dans le masque libéré du sprite 64 × 90 ; nom en x 9, y = 16 + 13 × i ; « > » en x 2 ; barre inversée x 1..126 sur le son chargé |
| `0x4003f6b8` 32 → 13, `0x4003f6bc` 44 → 54, `0x4003f6c4` 20 → 16 | géométrie de la mise en page `0x4003f6b0` |
| `0x4003f752` `0x40ea14dc` → `0x40ea14cc` | la petite police pour les noms |
| `0x400a69b4` 1 → 3 | 3 lignes visibles |
| `0x400a576c` | saute le dessin des icônes |

Tous ses octets d'origine correspondent à l'OS 1.13. Ce qui l'empêchait d'entrer tel quel dans le flasher :

1. **La liste à l'envers.** L'écran compte y depuis le bas : l'OS met la flèche du haut en y = 38 et celle du bas en
   y = 20 (`0x400a547a`, `0x400a54aa`), et la note 39 §2 l'a confirmé sur la machine. y = 16 + 13 × i met la 1ʳᵉ ligne
   en bas : le nom suivant s'affiche au-dessus du précédent, et le « > » monte quand on avance dans la liste. `[FAIT]` d'après le code ; `[HYP]` sur la machine de
   l'auteur (il n'en a rien dit).
2. **Conflit avec trig-hold** : ses 180 o en `0x4015c044` recouvrent les 166 o de `41-trig-hold.json`, au début du même
   masque. Les deux builders refusent le mélange (octets `old` différents).
3. **Plus de défilement des noms longs, plus d'icônes** : il retire browser-scroll (son unique état se remettait à zéro
   à chaque ligne, §2) et les icônes (trop hautes pour une ligne). Un dossier ne se distingue plus d'un son.
4. **Lié à `30-model-tg-st`** : seulement avec Model-TG et les moteurs du Syntakt, et à refaire à chaque build.
5. Sans effet : le constructeur de base `0x4006e4f0` (appelé seulement par `0x4003f6b0`) tire de cette géométrie le
   nombre de lignes visibles, (|y1 − y0| + 1) / h dans +28 par `0x40072c2a` : 0 d'origine, 3 avec ses valeurs. Mais le
   constructeur `0x400a68fc` le réécrit ensuite (`pea 1 ; jsr 0x40072758` en `0x400a69b2`, que le script passe aussi
   à 3). Le reste de la géométrie ne sert qu'au dessin par défaut de la liste de base (`0x4006e82e`), que le navigateur
   remplace (case 120 de sa vtable = `0x400a539c`). La case de pile que l'original retire en
   `0x400a55a4` (`lea 28`) reste à chaque ligne (4 o) ; `unlk` la rattrape en sortie (`0x400a5882`).

Repris de son script : l'idée, les 3 lignes de 13 px, la police `0x40ea14cc`, « > » en x 2 et les noms en x 9, et les
deux adresses de départ (police, lignes visibles). Aucun octet de son code n'est repris.

## 2. Le navigateur dans l'OS `[FAIT]`

| Adresse | Rôle |
|---|---|
| `0x400a68fc` | constructeur de ModelsFileManager, appelé seulement en `0x4001c9b4` ; appelle la mise en page `0x4003f6b0` (son seul appel) et règle les lignes visibles : `pea 1 ; jsr 0x40072758` en `0x400a69b2` |
| `0x4003f750` | `move.l #0x40ea14dc,d0` : police des noms (champ +652), la grande ; +648 = `0x40ea14cc`, la petite (titre, compteur) |
| `0x400a539c` | dessin du navigateur (vtable `0x401183ec`, case 120) : titre inversé, flèches, puis la boucle des lignes, puis compteur et « Fn=Menu » |
| liste de base (`0x40072524`, `0x4007266e`, `0x40072758`) | +16 sélection, +20 1ʳᵉ ligne visible, +24 sélection − 1ʳᵉ ligne, +28 lignes visibles ; `0x4007266e` (vt[36], au début du dessin) ramène la sélection dans la liste, recalcule +24 et rend la sélection ; `0x40072524` déplace de n et fait défiler d'une ligne quand le curseur sort des lignes visibles |
| `0x400a53b0`..`0x400a5406` | -48(fp) = la sélection (vt[36]), d3 = le nombre d'entrées (vt[12]) ; hors de la racine (`0x4007cce4`, chemin ≠ « / »), les deux moins un : l'entrée 0 y est le retour au dossier parent, que le compteur et les flèches ne comptent pas |
| `0x4003f5c6` | entrée dans un dossier (vt[20]) : à la racine, sélection = 1ʳᵉ ligne = +24 = 0 ; dans un sous-dossier de +Drive (vt[152] `0x400a3308` : +640 == +632, et pas la racine), les trois = a2[680] (`0x4003f616`), le curseur part de l'entrée 1. +24 y est faux (il devrait valoir 0) jusqu'au premier dessin, qui le recalcule (vt[36]) |
| `0x4004067c` | après chaque déplacement (`0x40072524` puis vt[76] `0x400a64be`, qui ensuite fait écouter le son, `0x400a63ac`) ou changement de sélection (`0x400729b0`), dans un sous-dossier de +Drive seulement : sélection = 1ʳᵉ ligne = +24 = max(sélection, 1). L'entrée 0 est ainsi interdite au curseur ; avec une ligne, la 1ʳᵉ ligne est de toute façon la sélection. Seul ModelsFileManager s'en sert (sa vtable, et celle de sa classe de base `0x40108664`, qui n'existe que pendant la construction) |
| `0x400a547a`, `0x400a54aa` | flèche du haut en (121, 38), du bas en (121, 20) ; `0x40071da4` dessine un sprite. La flèche est pleine tant que le curseur peut encore monter (-48(fp) ≠ 0) ou descendre (-48(fp) ≠ d3 − 1) : elle suit le curseur, pas les lignes visibles |
| `0x400a54c8` | `movea.w #2,a3` : x du nom |
| `0x400a5526`, `0x400a552a` | dossier vide : « <EMPTY> » en (2, 20) |
| `0x400a5612` | tête de la boucle : i = -36(fp) de 0 à min(lignes visibles (vt[64]), d3) − 1 ; l'entrée dessinée est 1ʳᵉ ligne + i (`0x400a562a`) |
| `0x400a5744`..`0x400a5776` | dossier (`vt[28]` de l'objet dossier) ou entrée spéciale (la dernière, à la racine) : icône `0x40fe2d60` (25 × 22) ou `0x40fe3824` (24 × 22) par `jsr 0x40071da4` en `0x400a576e`, puis `lea 27(a3),a3` |
| `0x400a5780`..`0x400a578c` | -32(fp) = 121 − x : la largeur qui reste avant les flèches |
| `0x400a5540`..`0x400a5584` | chaîne affichée, puis le nombre de caractères qui tiennent (`0x40072204`) dans -32(fp) |
| `0x400a559e` | `jsr 0x4007199c(écran, police, x, 20, n, chaîne)` : le nom |
| `0x400a55b2`..`0x400a5604` | son chargé (d7) : largeur `0x400722b2`, hauteur `0x40072296`, boîte arrondie inversée `0x40070f6e(écran, x − 2, 18, x + 1 + l, 21 + h, −1)` |
| `0x400a5608` | destruction de la chaîne, i + 1, retour en tête |

browser-scroll (drumkilla, et sa copie dans Model-TG et Model-TG-ST) réécrit les 3 derniers octets du `jsr` de
`0x400a559e` vers son stub `0x40147f22`. Le stub garde **un seul** état : l'empreinte du nom et l'heure de départ
(horloge `0x40a78e28`). Appelé pour chaque ligne, il verrait un nom différent à chaque appel et repartirait de zéro :
aucun nom ne défilerait.

## 3. Le tweak

Quatre accroches dans le dessin, huit constantes et deux retouches de la liste dans un sous-dossier de +Drive (`HOOKS`
et `PATCHES` de `tools/gen_multiline_browser.py`), plus le code et la redirection du masque :

| Adresse | Origine → tweak | Rôle |
|---|---|---|
| `0x4003f752` | `0x40ea14dc` → `0x40ea14cc` | police des noms : la petite |
| `0x400a547c`, `0x400a54ac` | 38 → 44, 20 → 14 | flèches en face de la 1ʳᵉ et de la dernière ligne |
| `0x400a54ca` | 2 → 9 | x du nom (« > » en x 2) |
| `0x400a5528`, `0x400a552c` | (2, 20) → (9, 40) | « <EMPTY> » sur la 1ʳᵉ ligne |
| `0x400a5588` | `move.l 652(a2),(sp) ; jsr (a5)` → `jmp ml_row` | chaque ligne |
| `0x400a55a4` | `lea 28(sp),sp ; movea.l -40(fp),a1` → `jmp ml_after` | après le nom |
| `0x400a5612` | `movea.l (a2),a0 ; move.l a2,-(sp) ; movea.l 64(a0),a0` → `jsr ml_bound ; bra.s 0x400a5624` | lignes à dessiner (`0x400a561a`..`0x400a5623` n'est plus exécuté) |
| `0x400a576e` | `jsr 0x40071da4` → `jsr ml_icon` | repère de dossier |
| `0x400a5776` | `lea 27(a3)` → `lea 9(a3)` | nom après le repère |
| `0x400a69b4` | 1 → 3 | lignes visibles |
| `0x4003f622` | `move.l d0,24(a2)` → `clr.l 24(a2)` | entrée dans un sous-dossier : +24 = 0, cohérent dès le départ |
| `0x400406a8`..`0x400406b9` | `tst.l d2 ; bgt.s ; moveq #1,d2 ; move.l d2,16/20/24(a2)` → `tst.l d2 ; bgt.s 1f ; moveq #1,d2 ; move.l d2,20(a2) ; clr.l 24(a2) ; 1: move.l d2,16(a2)` | après un déplacement dans un sous-dossier : la sélection seule ; la 1ʳᵉ ligne et +24 ne changent que si le curseur arrivait sur l'entrée 0 (alors 1, 1, 0) |
| `0x400ac784` | `0x401904b4` → `0x40172220` | le sprite pointe sur un masque identique (§4) |

- `ml_row` : y = 40 − 13 × i (l'écran compte y depuis le bas : la 1ʳᵉ ligne en haut). La ligne du curseur (i = champ +24)
  repasse par l'appel d'origine en `0x400a559e`, donc par le défilement s'il est là ; les autres appellent
  `0x4007199c` directement. Même pile que l'original (la case de la police comprise).
- `ml_after` : retire les 7 cases comme `0x400a55a4`, recharge a5 comme `0x400a55ac`, écrit « > » en x 2 sur la ligne
  du curseur, refait la boîte inversée du son chargé à la hauteur de sa ligne (mêmes appels que `0x400a55b2`..), remet
  a3 à 9 pour la ligne suivante et repart en `0x400a5608`.
- `ml_icon` : deux rectangles `0x40070dea` lus dans une petite table : un dossier (corps 7 × 5 et onglet 3 × 1), ou un
  carré creux de 7 × 7 pour l'entrée spéciale, en x 9, sur la hauteur des majuscules.
- `ml_bound` : d0 = min(3, nombre d'entrées − 1ʳᵉ ligne visible), sans borne par d3. L'original bornait par
  min(lignes visibles, d3), et d3 compte une entrée de moins hors de la racine (§2). Avec une seule ligne, c'était sans
  effet : min(1, d3) dessinait toujours l'entrée sous le curseur. Avec trois, dans un dossier de 1 ou 2 éléments revenu
  en haut (curseur passé sur l'entrée 0, 1ʳᵉ ligne = 0), la dernière entrée n'était plus dessinée, et le « > » avec
  elle quand le curseur y descendait. Trouvé à la relecture (06/10/2026), avant toute publication ; la preuve a
  maintenant ce cas (§5).
- Sous-dossier de +Drive : `0x4004067c` remettait la 1ʳᵉ ligne visible sur la sélection après chaque déplacement
  (§2). Avec une ligne, sans effet ; avec trois, le « > » serait resté sur la 1ʳᵉ ligne, la liste défilant à chaque
  pas et se vidant par le bas en fin de dossier, alors qu'à la racine il descend jusqu'à la 3ᵉ ligne. Les 18 octets de
  `0x400406a8` gardent la règle de l'OS (jamais l'entrée 0) sans écraser la fenêtre : la liste de base (`0x40072524`)
  la tient déjà, 1ʳᵉ ligne ≤ sélection < 1ʳᵉ ligne + 3, et la 1ʳᵉ ligne ne descend pas sous 1 tant que la sélection ne
  passe pas par 0. `0x4003f622` met +24 à 0 à l'entrée dans le dossier, ce que le premier dessin faisait déjà ; sans
  cela, un déplacement avant tout dessin sauterait une entrée (l'OS d'origine aussi, en émulation). Trouvé à la
  relecture (06/10/2026), avant toute publication : la preuve faisait jusque-là de vt[76] une fonction vide, elle
  exécute maintenant la vraie (§5).

Les registres d2–d7, a2 et fp ne changent pas ; `ml_after` remet a3 à 9 pour la ligne suivante et, pour le son chargé,
met sa largeur dans a4 comme l'original (`0x400a55d2`, a4 rechargé en `0x400a5634`) ; a5 = -40(fp) en repartant en
`0x400a5608`, comme l'original (`0x400a55ac`). La proposition de l'auteur (barre inversée sur toute la largeur) n'a
pas été gardée pour le son chargé : la boîte d'origine, autour du nom, reste lisible à côté du « > ».

## 4. Place libre et conflits

- Code : 370 o dans le masque 47 × 47 de `0x401904b4` (376 o), désigné par la seule constante `0x400ac784` du
  constructeur `0x400ac782`. Comme les autres masques 47 × 47 (notes/32 §11), il est identique à celui de `0x40172220` :
  le sprite pointe dessus, rendu identique. Ajouté à `tools/sprites.py`. Les masques `0x40189930` et `0x4018a220` sont
  à l'arpégiateur ; `0x4015c044` à trig-hold et 6ch-usbup.
- Aucune adresse partagée avec un autre tweak du flasher (vérifié par la preuve), `0x4003f622` et `0x400406a8` compris ; `0x400a55a1`..`0x400a55a3` n'est pas
  touché : avec browser-scroll ou Model-TG, le défilement continue sur la ligne du curseur, et seulement elle.
- Pas de `conflicts`. Le flasher le propose avec toutes les combinaisons (9 215 empreintes de référence).

## 5. Preuve en émulation `[FAIT en émulation]`

`tools/emu/test_multiline_browser.py` exécute le vrai dessin `0x400a539c`, d'origine et modifié, dans un vrai écran de
128 × 64 (un `Bitmap` construit par l'OS) avec les vraies polices (initialisation statique `0x400e7ccc`), la vraie liste
de base, la vraie entrée dans un dossier (`0x4003f5c6`), la vraie réaction à une nouvelle sélection (vt[76]
`0x400a64be`, avec `0x4004067c`) et les vraies fonctions de texte et de rectangles. Seuls les objets de données sont
factices (entrées du dossier, racine de +Drive, son chargé, écoute du son, allocation, horloge du défilement). `--png` écrit l'écran d'origine et le modifié côte à côte.

| Vérification | Origine | Modifié |
|---|---|---|
| noms à l'écran | 1, en y 20 | 3, en y 40 / 27 / 14, dans l'ordre de la liste |
| curseur | le seul nom | « > » en x 2 sur sa ligne ; jusqu'au bout et retour, le nom sous « > » est celui de l'origine, la liste défile d'une ligne |
| petits dossiers (1 à 3 entrées, à la racine et ailleurs, départ comme l'OS) | le nom sous le curseur | toutes les entrées à partir de la 1ʳᵉ ligne visible, « > » sur celle de l'origine, en montant puis en descendant |
| sous-dossier de +Drive (2, 3, 4 et 6 entrées, entrée réelle dans le dossier) | le nom sous le curseur, jamais l'entrée 0 | même suite de sélections ; « > » qui descend jusqu'à la 3ᵉ ligne puis la liste défile (1ʳᵉ ligne 1, 1, 1, 1, 2, 3 … 3, 2, 1) ; l'entrée 0 jamais à l'écran ; même suite sans dessin entre deux déplacements |
| son chargé | boîte inversée autour du nom | la même, sur sa ligne seulement ; rien d'inversé s'il est hors de l'écran |
| dossier, entrée spéciale | icône 25 × 22, nom en x 29 | repère de 7 px en x 9, nom en x 18 |
| dossier vide | « <EMPTY> » en (2, 20) | en (9, 40) |
| titre, compteur, « Fn=Menu » | — | identiques ; rien au-delà de x 120 (les flèches) |
| noms longs (browser-scroll, Model-TG) | le nom défile | un seul appel au défilement par dessin, pour la ligne du curseur, qui défile (11 positions) ; les autres lignes ne bougent pas |
| pile, registres | — | identiques à chaque tour et en sortie |
| écritures | — | octets d'origine ; aucun recouvrement ; le sprite de `0x400ac782` pointe bien sur le masque gardé (image modifiée) |

Combinaisons passées : seul ; avec browser-scroll ; avec model-tg ; avec model-tg-st, syntakt-tg-sd-cp-toy-bits-swarm,
trig-hold, arp et tempo-max ; avec 6ch-usbup, browser-scroll, latching-mute, trig-preview, trig-hold, arp, tempo-max et
syntakt-sd-cp-toy-bits-swarm.

## 6. Testé sur la machine (10/10/2026)

Maxime, le 10/10/2026 : « ça marche nickel sur ma machine » (fichiers de test : le navigateur seul, et avec
Model-TG). Le mod passe en `tested`. Reste ouvert : le nom sous lequel l'auteur du script veut être crédité.

Points qui étaient à vérifier :

- La 1ʳᵉ ligne en haut, et le « > » qui suit le curseur dans les deux sens, à la racine de +Drive comme dans un
  sous-dossier ; le retour au dossier parent comme avant.
- La lisibilité de la petite police sur l'écran réel.
- Un nom long : avec browser-scroll ou Model-TG, seul celui sous le curseur défile.
- Le son chargé en surbrillance, les dossiers (repère), un dossier vide.
- Avec Model-TG : le choix d'un échantillon pour le Sampler (même navigateur).
- Le crédit : le nom sous lequel l'auteur du script veut apparaître.
