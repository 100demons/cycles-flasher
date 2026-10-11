# 45 — Les trigless trigs atténués sur les touches de pas : le tweak `trigless-dim`

Mod de **djd_oz** (communauté), envoyé à Maxime le 06/10/2026 avec un premier mod (note 44) : l'archive
`Cycle_PAN_TriglessTrig_Mods.zip`, ici le fichier `model-cycles_OS1.13_Trigless-Trigs-LED-36pct-v4-experimental.syx`,
un OS 1.13 complet déjà modifié. Demande de Maxime : « Vérifie-les, dis-moi comment les tester sur ma machine pour
ensuite les intégrer au webflasher ». Tweak `47-trigless-dim.json` (`tools/gen_trigless_dim.py`, sources dans
`tools/machines/trigless_dim/`), preuve en émulation `tools/emu/test_trigless_dim.py`. Adresses : VA de l'OS 1.13.

## En bref

- **En mode grille, une touche de pas qui porte un trigless trig (lock trig, FUNC + touche) s'allume au tiers de sa
  lumière** au lieu de pleine lumière, comme un trig de note. Elle garde son clignotement d'origine (éteinte 0,35 s
  toutes les 2 s). Trigs de note, trigs avec p-locks, lumière de lecture, pads et autres LED : inchangés.
- Comment : le mode grille donne à ces touches leur propre état de LED, 260, que le reste de l'OS traite comme 4
  (idée de djd_oz) ; l'interruption du panneau, qui charge les verrous des LED, les allume **1 ms sur 3** (333 Hz,
  régulier) en rechargeant leur rangée en plus du tour d'origine (§6).
- **Version 1** (06/10/2026) : la réécriture du fichier de djd_oz, qui éteignait ces touches 16 ticks sur 25 de
  l'horloge des LED (120 Hz). Essayée par Maxime le 06/10/2026 : « ça marche parfaitement », mais le scintillement
  « n'est pas méga régulier et fait un peu LED abîmée ». Cause (§5) : les verrous ne sont rechargés que toutes les
  7 ms, ce qui rend le motif irrégulier (paliers de 7 à 21 ms, de 28 à 49 % de lumière selon le moment).
- **Version 2** (07/10/2026, celle du tweak) : même état 260, même clignotement ; la lumière est découpée dans
  l'interruption du panneau, à chaque cycle de 1 ms. Prouvé en émulation sur le vrai code de l'interruption (§10) :
  allumée exactement 1 cycle, éteinte 2, toutes les autres LED identiques à l'origine au même instant. Écritures
  espacées de 2 µs (au lieu de 83 µs à l'origine).
- **Testé sur la machine (07/10/2026)** par Maxime, avec la version 2 à 2 µs et tous les autres mods : « Le trigless
  trig est nettement plus sombre et stable, pas de pointillés gênants, même avec les 16 en trigless trig. Tout le
  reste marche nickel » (§12).

## 1. Le fichier de djd_oz `[FAIT]`

Seule la section 3 (MAIN OS) diffère de l'officiel ; sections 2, 4 et 5 et en-tête identiques, HMAC valide. 312 o
ajoutés après l'image (`0x401aa140`), recopiés au démarrage en `0x42339000..0x42339107` par la même accroche
`0x4000045c` que son autre mod (note 44 §1).

| Écriture | Où | Quoi |
|---|---|---|
| T1 | `0x4000045c` | recopie de son code en `0x42339000` au démarrage |
| T2 | `0x40005f36` | clignotement (`0x40005efc`, 2 Hz) : l'état 260 clignote comme 4 |
| T3 | `0x40021f52` | mode grille, pas qui porte un trigless trig : `movea.w #4,a5` → `movea.w #260,a5` |
| T4 | `0x4008e754` | envoi d'une rangée de LED : l'octet envoyé perd les bits du masque |
| T5 | `0x4008e7a8` | comparaison des 7 rangées : la valeur à afficher perd les bits du masque |
| T6 | `0x4008e7ca` | tick des LED (120 Hz) : motif +9 modulo 25 ; sur un tick éteint, le masque reçoit les LED dans l'état 260 |
| T7 | `0x4008e82e` | `beq` → `nop` : les rangées sont comparées et envoyées à chaque tick, plus seulement quand un minuteur de LED expire |

Analyse, émulation et relecture contradictoire (400 tirages au hasard des états, minuteurs, registres, pointeur nul) :
aucun plantage, aucune écriture hors des LED, de son état et de la pile, registres rendus. **Verdict : se flashe seul
sans risque.**

## 2. Ce que fait l'OS `[FAIT]`

| Où | Quoi |
|---|---|
| `*0x40fe4200` | l'objet des LED (constructeur `0x40005e76`) ; `+40` : l'état des 54 LED logiques (mots longs) |
| `0x4010abf8` | LED logique → bit des 7 octets de LED (octet = bit / 8, bit = bit % 8 ; -1 = pas de LED). Les 16 touches de pas sont les LED logiques 1 à 16 |
| états | 0 : pas d'état (passe à 1 en fin d'image) ; 1 : éteinte ; 2 : allumée (trig de note) ; 3 : allumée, éteinte 50 ms toutes les 0,5 s (trig avec p-locks) ; 4 : allumée, éteinte 0,35 s toutes les 2 s (trigless trig) |
| `0x40006a4a` | une image de l'interface (30 Hz, tâche de l'interface, priorité 6) : `0x4000602a` remet les 54 états à 0, les vues posent les leurs (`0x40076ca2`), puis `0x40006044` |
| `0x40005f86(obj, led, état, …)` | pose l'état si la LED n'en a pas encore (le premier gagne) et le bit de base de la LED |
| `0x40006044(obj)` | fin de l'image : les LED sans état passent à 1, puis `jmp 0x4008e77e` (en `0x40006086`) |
| `0x40021d22` | mode grille (`PatternGridView`), boucle des pas `0x40021ed6..0x40021f8a` : a5 = 2 (trig de note), 3 (p-locks), 4 (trig qui ne joue pas la note : le trigless trig posé par `0x40017bb0`), puis `0x40005f86`. 260 n'est écrit qu'en `0x40021f52` par le mod |
| `0x40005efc` | clignotement (2 Hz, `0x4009109e(…, 2, …)`) : état 3 → `0x4008e8c4(led, 6)` ; état 4 → `0x4008e8c4(led, 42)` une fois sur quatre (phase `0x404a90f4`) |
| `0x4008e8c4(led, n)` | inverse la LED pendant n ticks de 120 Hz (minuteurs des LED) |
| `0x4008e7ca` | tick des LED (120 Hz, tâche des minuteurs `0x400020e6`, priorité 10, la plus haute), sous le verrou `0x40fde2e8` : minuteurs ; si l'un expire, `0x4008e77e` |
| `0x4008e77e` | compare les 7 rangées (base ⊕ minuteurs) au dernier envoi ; une rangée changée part par `0x4008e732(rangée)` → `*0x401492f8` = `0x40059fd2`, qui écrit l'octet inversé dans la copie `0x40140aa8` lue par l'interruption du panneau |

La tâche des minuteurs (priorité 10) interrompt la tâche de l'interface (priorité 6) n'importe où : un tick des LED
peut tomber entre la remise à zéro des états (`0x4000602a`) et leur écriture par le mode grille.


## 3. L'interruption du panneau et les verrous des LED `[FAIT]`

Lu dans le code (`0x40059cd0..0x4005a140`, initialisation `0x40059ff2`) et rejoué en émulation.

| Quoi | Détail |
|---|---|
| Matériel | 7 verrous 74HC373 (une rangée de 8 LED chacun) choisis par deux décodeurs 74HC238 (note 21 §7.2). Une LED est **allumée ou éteinte**, sans réglage de lumière : l'atténuation ne peut venir que du temps |
| Port | Rapid GPIO `0x8c000000` : `+0` DIR, `+2` DATA, `+6` CLR (les bits écrits à 0 passent à 0), `+0xa` SET (les bits écrits à 1 passent à 1) `[HYP]` (sens de CLR et SET tiré d'une source secondaire, cohérent avec le code). DATA : bits 15-8 la donnée (octet de LED, 1 = éteinte), 7-5 la rangée, 3 le strobe des verrous, 0 le balayage des touches |
| Horloge | PIT3 (INTC2 source 16, vecteur 208 en `0x40000340`, niveau 6), PMR `0x2c00` : 11 265 coups, 83,3 µs à 135,168 MHz `[HYP]` (fréquence tirée du pilote Linux du MCF5441x), soit 12 000 interruptions par seconde |
| Cycle de 12 interruptions (1,000089 ms) | début `0x40059cd0`, 8 colonnes de touches `0x40059d2c` (la 8e force l'interruption logicielle des touches, INTC1 source 2, `0x40059e64`, niveau 3), puis 3 étapes des LED `0x40059db8` ; chaque gestionnaire écrit le suivant dans `0x40000340` |
| Étapes des LED | étape 0 : DIR = `0xffff`, DATA = (`0x40140aa8`[r] << 8) \| (r << 5) ; étape 1 : SET 8 (strobe haut, le verrou r suit la donnée) ; étape 2 : CLR `0xfff7` (strobe bas, le verrou garde la donnée) ; puis r = (r + 1) mod 7 (`0x40a79194`) |
| Rafraîchissement | une rangée par cycle : **chaque verrou est rechargé toutes les 7,0006 ms** (142,8 Hz). Entre deux, il tient sa valeur |
| Copie des verrous | `0x40140aa8`, 7 octets, 1 = éteinte, écrite inversée par `0x40059fd2` depuis le tick des LED (§2) |
| Rendu audio | interruption logicielle INTC1 source 63 (`0x40058c5e`, vecteur `0x400002fc`), niveau 5 (`0x4005967a`) : le panneau, au niveau 6, l'interrompt déjà 12 000 fois par seconde à l'origine |

## 4. Version 1 : la réécriture du fichier de djd_oz

Accroches de djd_oz (T2 à T7 du §1), plus `0x40006086` : en fin d'image, `td_frame` relève les LED dans l'état 260
(`td_lock`) ; le tick des LED (120 Hz) applique un motif `td_cnt += 9`, allumé au passage de 25
(`0010010010010100100100101`, 9 sur 25) en retirant ces LED des rangées envoyées sur un tick éteint ; les rangées
partent à chaque tick (T7). Correction par rapport à djd_oz : chez lui, un tick tombé entre la remise à zéro des états
(`0x4000602a`) et le mode grille ne trouvait aucune LED dans l'état 260 et rallumait les touches à fond pendant ce tick
(la tâche des minuteurs, priorité 10, interrompt la tâche de l'interface, 6, n'importe où) ; le relevé en fin d'image
supprime ce cas. Prouvé en émulation : en régime établi, mêmes LED que son fichier, tick par tick.

Essai de Maxime le 06/10/2026 (PR #53, avec le volume et le pan en chiffres) : « ça marche parfaitement. Pour ce qui
est du scintillement, il est pas méga régulier et fait un peu "led" abîmée. Y'a pas moyen de gérer l'intensité de la
led de manière propre et stable ? »

## 5. Pourquoi la version 1 scintillait `[FAIT par le calcul]`

Le motif ne change que la copie `0x40140aa8` ; la LED ne prend la nouvelle valeur que quand l'interruption recharge
sa rangée, toutes les 7,0006 ms. La LED montre donc le motif de 120 Hz (8,334 ms par tick) échantillonné toutes les
7 ms. Calcul sur 10 s (le motif et les deux périodes ci-dessus) :

| | Version 1 | Version 2 |
|---|---|---|
| Allumée | 7 ms (348 fois) ou 14 ms (83 fois) | 1,000 ms, toujours |
| Éteinte | 7, 14 ou 21 ms (76, 230, 126 fois) | 2,000 ms, toujours |
| Lumière sur 100 ms | de 28 à 49 % (36 % en moyenne) | 33,3 % (de 32,9 à 34,0 % avec 20 µs de retard au hasard sur les interruptions) |
| Rythme | irrégulier, des périodes de 14 à 35 ms (29 à 71 Hz) | 333 Hz |

Des éclats de 7 à 21 ms dans un ordre qui ne se répète pas : c'est la « LED abîmée ». Aucun motif lent ne peut faire
mieux, puisque le verrou ne change que tous les 7 ms : à l'origine, l'atténuation la plus fine possible est
1 rafraîchissement sur 2 (71 Hz, 50 %). Pour descendre plus bas et plus vite, il faut recharger la rangée en dehors de
son tour : c'est la version 2.

## 6. Version 2 : la lumière découpée dans l'interruption du panneau

| Accroche | Origine | Mod |
|---|---|---|
| `0x40059dea` | `moveq #-1,d3 ; moveq #21,d4 ; move.w d3,0x8c000000` (étape 0 des LED) | `jmp td_led ; nop ; nop` |
| `0x40006086` | `jmp 0x4008e77e` (fin de l'image) | `jmp td_frame` : relevé des LED dans l'état 260 (`td_lock`, construit sur la pile, écrit en deux mots longs), puis `jmp 0x4008e77e` |
| `0x40005f36` | `cmp.l 40(a4),d1 ; beq.s 0x40005f6c` (clignotement) | `jmp td_blink` : 4 et 260 clignotent pareil |
| `0x40021f54` | `0004` | `0104` : `movea.w #260,a5` |

Le tick des LED, la comparaison et l'envoi des rangées sont **d'origine** (les accroches T4 à T7 de djd_oz sont
retirées) : la copie `0x40140aa8` dit la vraie lumière voulue, et une LED dans l'état 260 y est allumée comme 4.

**`td_led`** (étape 0 des LED, une fois par cycle de 1 ms, à la place des trois instructions d'origine) garde trois
tableaux de 8 octets : `td_lock` (bits des LED dans l'état 260, rangée par octet), L (`td_last`, le dernier octet que
le tour d'origine a verrouillé pour chaque rangée) et C (`td_cur`, l'octet que tient chaque verrou), plus la phase
`td_ph` (0, 1, 2).
1. Voie rapide : sans LED dans l'état 260 et sans rangée à rétablir (L = C), L = C = la copie pour la rangée du tour,
   et les écritures sur le port sont celles de l'origine (DIR puis DATA), 22 instructions plus tard.
2. Sinon, phase suivante. La rangée r est allumée quand (phase + r) mod 3 = 0 : les rangées ne s'allument pas toutes
   ensemble. Pour chaque rangée, D = L[r], plus `td_lock`[r] (forcés à 1, éteints) si la rangée est dans sa phase
   éteinte ; si D ≠ C[r], C[r] = D et le mot (D << 8) \| (r << 5) va dans la liste (strobe et balayage à 0). La
   rangée du tour passe aussi dans la boucle avec son ancien L : ses autres LED changent quand même à l'instant de
   l'origine (étape 1).
3. Rangée du tour : L = la copie, S = la copie plus `td_lock` si phase éteinte, C = S ; S repart dans d0, et l'OS
   l'écrit et le verrouille aux étapes 1 et 2 comme d'habitude.
4. Bus : DIR = `0xffff`, puis pour chaque mot de la liste une transaction complète comme celle de l'OS : DATA, attente,
   SET 8, attente, CLR `0xfff7`, attente. Puis l'écriture DATA d'origine.

`td_wait` : un `nop` (sur ColdFire, attend la fin des écritures en cours `[HYP]`, de mémoire du manuel), puis lit le
compteur de PIT3 (`0xfc08c004`, décompte) jusqu'à ce que (début − maintenant) mod 11 265 ≥ 272 coups (2,0 µs), au
plus 64 lectures.

Ce que ça donne pour une touche dans l'état 260, allumée à l'origine : allumée 1 cycle (1,000 ms), éteinte 2, quel
que soit le nombre de touches atténuées ; 333 Hz ; un tiers de la lumière (perçue vers 60 % de la pleine lumière
`[HYP]`, comme les 36 % de la version 1). Le relevé `td_lock` est fait en fin d'image (§4) : poser ou retirer un trigless trig change
l'atténuation au plus une image plus tard (33 ms). Clignotement et lumière de lecture (qui éteignent la touche à
l'origine) gagnent toujours : le mod ne fait qu'ajouter des bits « éteinte ».

Paramètres (`.equ` de `trigless_dim.S`, variantes par `--defsym` du générateur, jamais versionnées) : `PWM_N` = 3
cycles par période, `PWM_ON` = 1 cycle allumé, `WAIT` = 272 coups (2 µs, la valeur testée sur la machine ; 68, soit
0,5 µs, n'a jamais été essayé). 4/1 donnerait 250 Hz à 25 %, 2/1 500 Hz à 50 %.

## 7. Effets de bord, coût et attente active

- `[FAIT]` L'état 260 est vu par tous les lecteurs du tableau des états, qui le traitent comme 4 : `0x40005f86`
  (« ≠ 0 », « = 1 »), `0x40005ff6` (« ≠ 0 »), `0x40006044` (« = 0 »), `0x4000602a` (remise à zéro) ; la lecture
  `0x40006016` n'a pas d'appelant. Model-TG (`sld_led`, accroché juste après, en `0x40021f56`) transmet a5 tel quel.
- `[FAIT en émulation]` Sans trigless trig : mêmes écritures sur le port, dans le même ordre ; l'étape 0 passe de 32 à
  54 instructions (DIR écrit environ 0,2 µs plus tard dans l'étape, sans effet : le strobe vient à l'étape suivante).
- `[FAIT en émulation]` Avec des trigless trigs : l'étape 0 coûte 139 instructions et 1 µs sans rangée à recharger,
  puis environ 6,8 µs par rangée rechargée, presque tout en attente du compteur (modèle : 1 coup de bus par
  instruction, 8 par lecture du compteur). Les 16 touches de pas sont sur les rangées 0, 2, 3, 4 et 5 : avec les
  phases décalées, 3 ou 4 rangées rechargées par cycle, jamais plus ; 28,2 µs au pire, **23,5 µs par ms en moyenne
  (2,35 % du processeur)** avec 16 trigless trigs. Le code en accepte 7 (au plus 5 changent ensemble, environ 35 µs).
  Avec des attentes de 0,5 µs (version non essayée), c'était 9,8 µs au pire et 0,8 %.
- **Attente active dans une interruption** : c'est une exception à `tools/AGENTS.md` (« no waits »), voulue. Les
  verrous ont besoin d'un strobe d'une certaine durée ; l'OS l'étale sur trois interruptions (83 µs chacune), ce qui
  limite le tour d'origine à une rangée par ms. Ici : 3 attentes de 2 µs par rangée rechargée, au plus 5 rangées par cycle, chaque
  attente bornée à 64 lectures du compteur (si le compteur était figé, l'étape se terminerait quand même : 92 µs
  modélisés au pire, prouvé). Le temps est pris au niveau 6, sur le rendu audio (niveau 5) comme les 12 000
  interruptions du panneau d'origine : 2,35 % en moyenne avec 16 trigless trigs, seulement quand des trigless trigs
  sont affichés ; aucun craquement ni coupure en plus sur la machine avec tous les mods (07/10/2026). Le
  régulateur de charge (notes 25, 30, 36) mesure ce temps comme le reste.
- `[FAIT]` Pile : 24 octets de plus sur la pile interrompue (20 pendant `td_led`, 4 de plus pendant `td_wait`).

## 8. Place et conflits

- Deux masques de sprites 47 × 47 libérés, identiques au masque gardé `0x40172220` et désignés seulement par la
  constante de leur constructeur, redirigée (`tools/sprites.py`) :
  - `0x4018dba8` (constante `0x400accfe`) : `td_blink` et `td_frame`, 114 o sur 376 ;
  - `0x40192734` (constante `0x400ac2b2`) : `td_led`, `td_wait` et l'état, 318 o sur 376. `td_lock` en `0x40192848`,
    `td_last` en `0x40192850`, `td_cur` en `0x40192858`, `td_ph` en `0x40192860`, la liste en `0x40192864`.
- Masques attribués le 07/10/2026 avec les autres branches en cours (le premier choisi, `0x4018d4a8`, est pris par
  chord-keys). Aucune écriture commune avec les 81 autres tweaks du dépôt, ni avec ceux des branches ouvertes le
  07/10/2026 (chord-keys PR #46 et #50, navigateur multiligne #52, OS du Cycles sur le Samples #47, écoute des samples,
  filtre par piste, moteurs MACRO, choix des mods du flasher). `46-level-pan-values` (note 44) se combine avec.
  Model-TG écrit en `0x40021f56` et `0x40021f67`, à côté de `0x40021f54` sans le toucher. Aucun autre tweak ne touche
  l'interruption du panneau.
- Aucun saut ni constante de l'image ne vise l'intérieur de l'accroche (`0x40059dec..0x40059df3`).

## 9. Le tweak

`47-trigless-dim.json`, 8 écritures : les deux masques (code et état), les constantes de leurs constructeurs, les
trois accroches et `movea.w #260,a5`. Les octets d'origine viennent du MAIN OS officiel et sont vérifiés par le
générateur. La version 1 en avait 9 (un masque, cinq accroches, le `nop` de T7).

## 10. Preuve en émulation `[FAIT en émulation]`

`tools/emu/test_trigless_dim.py` : le vrai code de l'OS, d'origine contre modifié, sur une même ligne de temps
(horloge du bus) : les 12 interruptions du panneau et l'interruption logicielle des touches, le tick des LED (120 Hz),
les images de l'interface (30 Hz), le clignotement (2 Hz), la lumière de lecture. Les écritures sur le port passent
dans un modèle des verrous (le verrou de la rangée des bits 7-5 suit les bits 15-8 tant que le bit 3 est à 1 et le
bit 0 à 0, `[HYP]` câblage de la note 21) ; le compteur de PIT3 suit la ligne de temps.

| Cas | Résultat |
|---|---|
| Écritures | octets d'origine ; masques identiques et à référence unique ; interruption du panneau d'origine sauf les 10 octets ; tick des LED d'origine ; pas de saut vers l'accroche ; 260 écrit seulement en `0x40021f52` |
| Clignotement | 260 donne les mêmes appels que 4 |
| Démarrage (pointeur des LED nul), puis images sans trigless trig, avec tête de lecture | 11 900 écritures sur le port identiques (valeur, étape), octets verrouillés identiques aux mêmes instants |
| 6 trigless trigs sur 5 rangées, 1,5 s | début, colonnes, étapes 1 et 2 identiques (18 000 écritures) ; étape 0 = [DIR, (DATA, SET 8, CLR `0xfff7`) × k, DATA], k ≤ 4 ; aucun danger sur les verrous (donnée qui change strobe haut, strobe avec le balayage ou DIR ≠ `0xffff`, adresse 7) ; au moins 272 coups entre deux écritures (303 au plus court) ; les 50 autres bits de LED identiques aux mêmes instants ; touches atténuées allumées 1,00 cycle (2 136 fois), éteintes 2,00 (2 130) ; jamais allumées quand l'origine est éteinte ; tête de lecture (49 → 50 cycles) et clignotement (343 → 344,9, 350 → 353) |
| Retard des interruptions de 0 à 20 µs, 1 s | lumière de 32,7 à 34,1 % sur chaque fenêtre de 100 ms |
| Étape 0 en retard de 80 à 83 µs | le compteur se recharge pendant 234 étapes : écritures toujours espacées d'au moins 272 coups (293 au plus court) |
| Compteur figé | chaque étape 0 se termine, 64 lectures par attente |
| 16 trigless trigs | `td_lock` = bits 6, 16, 19 à 23, 28, 29, 31, 37, 38, 40, 44, 46, 47 ; chaque touche 1 cycle sur 3 (5 264 passages) |
| Coût | étape 0 : 1 µs sans rangée à recharger, 28,2 µs au pire (4 rangées) ; 23,5 µs par ms avec 16 trigless trigs |
| États remis à zéro au milieu d'une image, 70 ms | la touche reste atténuée ; à l'origine allumée |
| Registres et pile | rendus à chaque `rte` (registres au hasard), par la fin de l'image ; l'interruption n'écrit en mémoire que ce qu'écrit l'origine plus l'état du mod |

Avec `--with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max,boot-anim,level-pan-values
--syntakt Syntakt_OS1.42.syx`, avec `model-tg,6ch-multiout,arp,trig-hold,level-pan-values`, avec
`latching-mute,trig-preview,browser-scroll,6ch-usbup,tempo-max` et avec `sdvintage-7th,tempo-max,boot-anim` : tout ok.

Non émulé : la vraie vue de la grille (`0x40021d22`, qui demande un pattern en mémoire) ; l'écriture de 260 y est
vérifiée octet par octet et par la lecture du code. Et surtout le matériel lui-même (§11).

## 11. Ce qui aurait pu rater sur la machine, et le repli

L'OS espace les écritures d'une transaction de 83 µs. La version 2 a d'abord été écrite avec 0,5 µs (`WAIT` = 68) ;
Maxime a reçu le 07/10/2026 deux jeux de fichiers, à 0,5 µs et à 2 µs (le repli), et a flashé directement celui à
2 µs avec tous les mods : il marche (§12). C'est donc la valeur du tweak ; 0,5 µs n'a pas été essayé. Les 74HC373 et
74HC238 sont sur la carte principale avec le processeur (note 21) et demandent quelques dizaines de ns. Signes d'un
échec, visibles et sans danger (le tour d'origine corrige chaque verrou tous les 7 ms), à surveiller si on change
`WAIT` :
- les transactions ajoutées sont ignorées : seule la valeur du tour d'origine reste, et comme 7 mod 3 = 1, la touche
  montre 7 ms allumée, 14 éteinte, un scintillement **régulier** à 48 Hz ;
- verrouillage limite : des LED fausses ou des étincelles sur les rangées 0, 2, 3, 4 et 5, au plus 7 ms.

Replis qui restaient en réserve : des transactions au rythme de l'OS (une étape par interruption, de 333 Hz pour une
rangée à 77 Hz pour cinq) ; au pire 1 rafraîchissement sur 2 (71 Hz, 50 %).

Autres points à juger : un sifflement à 333 Hz dans le son (le courant des LED commutées ; les phases décalées par
rangée le réduisent) ; une traînée en pointillés en balayant vite le panneau des yeux dans le noir (visible jusqu'à
environ 2 kHz ; une version à 1 kHz demanderait deux fois plus de temps d'interruption).

## 12. Essais sur la machine

**Testé sur la machine (07/10/2026)** : Maxime a flashé `…_volume-pan_trigless-v2-repli-2us_avec-tout` (les deux
mods de djd_oz, `WAIT` = 272, avec 6 canaux, Model-TG, les 5 moteurs du Syntakt, effacer un trig, arpégiateur, tempo
546, animation de démarrage ; MAIN OS `366aebfc…7fe7540`) : « Le trigless trig est nettement plus sombre et stable,
pas de pointillés gênants, même avec les 16 en trigless trig. Tout le reste marche nickel. » Les deux mods seuls à
2 µs donnent le MAIN OS `c4a547df…4a68797e6`, celui du tweak. La liste suivie :

- Arrêté, une piste : des trigs de note, un trigless trig (FUNC + touche sur un pas vide), un trig avec un p-lock. Le
  trigless trig nettement plus sombre, stable, avec son clignotement de 2 s ; les autres comme à l'origine.
- Un trigless trig (pas 3), puis en ajouter sur les pas 13, 9, 1, 11 : la lumière ne change pas avec le nombre de
  touches. De face, de côté, dans le noir.
- 16 trigless trigs sur une page, 3 à 5 minutes : aucune étincelle ni LED fausse sur les pads, les touches de piste
  et les voyants des encodeurs.
- Avec 16 trigless trigs : toutes les touches, les encodeurs et les pads (plusieurs vélocités) répondent comme
  d'habitude. PLAY : la lumière de lecture éteint la touche d'un trigless trig, qui revient atténuée. Changer de
  piste et de page : l'atténuation suit.
- Casque fort, rien ne joue : 16 trigless trigs contre aucun, un sifflement à 333 Hz ? Puis un pattern chargé avec
  l'enregistrement USB 6 canaux quelques minutes : pas de nouvelle coupure.
- Si les touches scintillent régulièrement (vers 48 Hz) ou si d'autres LED étincellent : le dire (§11).

## 13. Crédit

Idée, état 260, clignotement et accroches du mode grille de djd_oz ; réécriture, correction du relevé et découpage
dans l'interruption du panneau de ce projet. Crédit sur la carte du flasher et dans `PROVENANCE.md`. Sa licence n'est
pas encore connue : Maxime la lui demande avant la fusion.
