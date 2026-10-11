# 52 — Registre de la place libre et des points d'accroche

Étape 2 du chemin vers des mods modulaires, rédigé pour Maxime le 07/10/2026 (fil du projet sur le guide « comment
fonctionne un mod ») après sa question « à chaque mod, je génère toutes les combinaisons ? » et son souhait que les
gens puissent ajouter leurs propres mods. L'étape 1 (notes/49, PR #62, flasher 1.33) vérifie le flasher mod par mod.
Celle-ci répond à la question suivante : **où un nouveau mod peut-il mettre son code, et sur quoi s'accroche-t-il,
sans marcher sur les autres ?** Maxime a demandé de l'engager le 07/10/2026 (« Fusion la PR 62, et lance l'étape
2 »). Outils : `tools/registry.py` (nouveau), `tools/sprites.py` (table `GROUPS`),
`tweaks/model-cycles_OS1.13/REGISTRY.md` (généré). Aucun octet de firmware ne change. Adresses : VA de l'OS 1.13.

## Réponse courte

- Jusqu'ici la place libre se répartissait **à la main** : une note par mod, une liste des 21 masques 47×47 dans la
  mémoire partagée des fils de travail, un relevé des autres groupes de masques dans un fichier du projet
  (`espace-libre-masques.md`, 07/10/2026). Deux PR ouvertes se sont retrouvées sur les mêmes 732 octets, vu en
  comparant les branches à la main (notes/49 §1). [FAIT]
- `tools/registry.py` construit maintenant **le registre à partir des tweaks eux-mêmes** : le classement de chaque
  écriture se lit dans ses octets (§3). Il écrit `tweaks/model-cycles_OS1.13/REGISTRY.md` : qui utilise quel masque
  de sprite libéré, et lesquels sont libres ; les écritures dans des octets 0xFF ; les charges utiles ajoutées après
  l'OS ; les crochets posés sur l'OS ; les pointeurs réécrits ; ce que chaque mod touche. `--check` le vérifie dans
  la validation, `--git <branche>` y ajoute les mods des branches ouvertes. [FAIT]
- Il **refuse** une écriture dans un masque dont le sprite n'est pas redirigé (le sprite afficherait le code), une
  écriture dans une copie gardée, une redirection qui ne vise pas la copie gardée. `tools/check_overlaps.py`
  (notes/49) garde son rôle : deux mods installables ensemble n'écrivent jamais les mêmes octets. [FAIT]
- La place : **164 masques libérables, 35 960 o**, dont 10 pris par les mods de `main` (5 400 o) et **154 libres
  (30 560 o)**. Avec les quatre branches de mods ouvertes (clavier d'accords, mods de djd_oz, cue casque, filtre par
  piste) : 44 pris, **120 libres (20 136 o)**. Le relevé des masques est vérifié sur l'OS officiel (`--cycles`) :
  174 masques, copies identiques, une seule référence chacun. [FAIT]
- Un auteur extérieur lit `REGISTRY.md`, prend un masque marqué *libre* avec `sprites.redirect_write`, régénère le
  registre et le commet avec son tweak : c'est ce qu'il faut connaître pour écrire un mod compatible.

## 1. Ce que l'OS fait des masques de sprites

- Chaque sprite est un `Bitmap` (constructeur `0x40070172`) à deux plans de même taille : l'image (`+0x10`) et le
  masque (`+0x14`). Quatre masques sont entièrement à 0xFF et beaucoup d'autres sont des **copies identiques** d'un
  même dessin : un carré opaque de 47 colonnes pour les 22 sprites 47×47, et de même pour d'autres tailles
  (notes/14 §5, notes/32 §11, notes/46 §7). [FAIT]
- Chaque masque n'est désigné que par **une constante 32 bits** dans le constructeur du sprite (`pea abs.l` ou
  `move.l #imm,(sp)`). Faire pointer cette constante sur une copie gardée ne change rien au rendu (mêmes octets lus)
  et rend le plan d'origine libre ; le destructeur ne libère pas ces plans (sprite statique). [FAIT]
- Le MAIN OS est chargé en SDRAM (`0x40000400`) : un masque libéré est donc de la place pour du code **et** pour des
  variables (trig-hold y range ses 32 o d'heures d'appui, notes/33 §4). [FAIT]

## 2. Le relevé : 10 groupes, 171 masques

Relevé du 07/10/2026 sur le MAIN OS officiel (fil « Filtre demandé sur Discord »), repris dans `tools/sprites.py`
(`GROUPS`) et vérifié par `tools/registry.py --cycles` : pour chaque masque, les octets sont ceux de la copie gardée
de son groupe, la constante de son constructeur le désigne, et c'est **la seule** référence 32 bits alignée vers lui
dans l'image. [FAIT]

| groupe | copies | libérables | taille | place | copie gardée |
|---|---:|---:|---:|---:|---|
| 47×47 | 22 | 21 | 376 o | 7 896 o | `0x40172220` (`SHARED_47`) |
| 48×22 | 43 | 42 | 192 o | 8 064 o | `0x4014b364` |
| 35×35 | 20 | 19 | 280 o | 5 320 o | `0x4014a660` |
| 34×34 | 15 | 14 | 272 o | 3 808 o | `0x4016bfc8` |
| 27×27 | 25 | 24 | 108 o | 2 592 o | `0x4014a550` |
| 31×22 | 19 | 18 | 124 o | 2 232 o | `0x4016e980` |
| 26×26 | 15 | 14 | 104 o | 1 456 o | `0x4014b4e4` |
| 46×31 | 8 | 7 | 184 o | 1 288 o | `0x4016be58` |
| 41×41 | 2 | 1 | 328 o | 328 o | `0x40187298` |
| 52×22 | 2 | 1 | 208 o | 208 o | `0x4014bfe4` |
| masques 0xFF (notes/14 §5) | 4 | 3 | 720 à 1 024 o | 2 768 o | `0x40154ae4` (`SHARED_MASK`, 1 040 o) |
| **total** | | **164** | | **35 960 o** | |

`sprites.MASKS` garde son format (taille, constante, description, copie gardée) et ses neuf anciennes entrées à
l'identique : les générateurs existants (`gen_arp.py`, `gen_trig_hold.py`, `gen_sample_preview.py`,
`gen_sdvintage*.py`, `gen_syntakt_*.py`, `gen_macro*.py`, `gen_multiline_browser.py`) produisent les mêmes tweaks
(`--check` vérifié pour trig-hold, sample-preview et multiline-browser). Les 154 autres masques s'y ajoutent,
construits depuis `GROUPS`. [FAIT]

## 3. Le registre : lire le rôle d'une écriture dans ses octets

Le registre ne demande rien de plus aux tweaks : chaque écriture porte déjà ses octets d'origine (`old`) et ses
nouveaux octets (`new`), et c'est assez pour la classer. [FAIT]

| classe | comment on la reconnaît | exemple |
|---|---|---|
| redirection | 4 octets à l'adresse de la constante d'un masque, `old` = l'adresse du masque | `0x400ad328` : `40189930` → `40172220` (arp) |
| masque | l'adresse tombe dans un masque libérable | arp, 354 o dans `0x40189930` |
| copie gardée | l'adresse tombe dans une copie gardée : **refusé** | — |
| cave | `old` entièrement à 0xFF, hors masque | glyphes de la petite police (`0x401485f0`, browser-scroll) |
| crochet | `new` commence par `jsr`/`jmp abs.l` (`4eb9`/`4ef9`) ou `bsr.l`/`bra.l` (`61ff`/`60ff`) | `0x4002249c` : `jsr 0x40072490` → `jsr th_press` |
| pointeur | 4 octets dont la nouvelle valeur vise un masque, une charge utile ou une cave | `0x40000532` → `0x4016cae8` (crochet de démarrage) |
| patch | tout le reste | les 12 écritures de tempo-max |

Pour les crochets et les pointeurs, la cible est nommée : masque et décalage (avec le symbole si le tweak le porte
dans `symbols`), charge utile (image ou mémoire) et décalage, ou adresse de l'OS. Les 124 combinaisons de moteurs du
Syntakt (seuls, sur Model-TG, et avec MACRO depuis notes/50) visent des décalages différents dans leur charge utile :
une ligne par adresse et par zone, avec le nombre de cibles, et les moteurs résumés en quatre familles (`syntakt-*`,
`syntakt-tg-*`, `syntakt-*-macro`, `syntakt-tg-*-macro`, présents/total).

Ce que les écritures ne montrent pas, les octets des structures sauvegardées qu'un mod s'attribue, est déclaré à la
main dans `DECLARED` (`tools/registry.py`), avec la note qui le prouve : l'octet +512 de la piste pour l'arpégiateur
(notes/32 §4). Un nouveau mod qui en prend un l'y ajoute.

### 3.1 Les règles vérifiées

| règle | pourquoi | résultat sur `main` |
|---|---|---|
| une écriture dans un masque libérable exige la redirection de son sprite, dans le même tweak ou dans un tweak qu'il demande (`requires`) | sinon le sprite affiche le code du mod | 10 masques écrits, 10 redirigés |
| personne n'écrit dans une copie gardée | tous les sprites redirigés la lisent | aucune |
| une redirection vise la copie gardée de son groupe | c'est la seule copie dont on sait qu'elle reste intacte | les redirections des 10 masques visent toutes la copie gardée |
| (remarque) une redirection sans écriture dans le masque | place prise pour rien | aucune |

Deux mods peuvent écrire dans le même masque : `check_overlaps.py` garantit qu'ils n'écrivent pas les mêmes octets
s'ils s'installent ensemble (trig-hold devant les stubs de 6ch-usbup dans `0x4015c044` ; l'arpégiateur après le
crochet de démarrage des moteurs dans `0x4016cae8`), ou qu'ils ne s'installent jamais ensemble (sample-preview et
chord-keys sur quatre masques 47×47). Le registre montre pour chaque masque les octets écrits par chacun et ceux
qu'aucun mod n'écrit.

## 4. Ce que le registre dit de `main` (1.37)

- 147 tweaks (dont 124 combinaisons de moteurs du Syntakt), 16 217 écritures. Masques : 10 pris (5 400 o), 154
  libres (30 560 o). Les 21 masques 47×47 ne sont pas tous pris sur `main` (7 : arp 2, sample-preview 4, navigateur
  multiligne 1), mais le sont avec les branches ouvertes (§5).
- Masques 0xFF : `0x4015c044` 550/720 o écrits (6ch-usbup, trig-hold, et les 208 o des stubs USB communs à
  Model-TG, MACRO et aux moteurs) ; `0x4016cae8` 1 016/1 024 o (arp 824 o, crochet de démarrage et stubs des
  moteurs, avec ou sans MACRO, sdvintage-snare 973 o, qui exclut les autres) ; `0x4018a788` 1 016/1 024 o (arp,
  sdvintage-snare).
- 69 adresses de l'OS détournées, dont 56 à l'identique par des mods de familles différentes (le crochet de
  démarrage `0x400004b2`, les stubs USB `0x40058ca0`, `0x40059392`, `0x400593ce`, l'aiguillage des voix
  `0x4004df40`…) ; 51 pointeurs réécrits ; 14 zones 0xFF hors masques (tables de glyphes de drumkilla, reprises par
  Model-TG).
- 134 tweaks à charge utile ; la plus haute finit en `0x401fb180`, 20 096 o avant la limite `0x40200000`.

## 5. Avec les branches ouvertes (`--git`, 10/10/2026)

`python3 tools/registry.py --git origin/claude/chord-keys-flasher-ozqjas --git origin/claude/djd-oz-mods-0vgnze
--git origin/claude/headphone-cue-k48r6s --git origin/claude/discord-filter-439loo` (le navigateur multiligne est
sur `main` depuis) : 153 tweaks, 44 masques pris (15 824 o), 120 libres (20 136 o). Les 21 masques 47×47 sont tous
pris : `main` 7 (arp 2, sample-preview 4, navigateur multiligne 1), chord-keys 14 (dont les 4 de sample-preview,
qui l'exclut), trigless-dim 2, level-pan-values 2 ; le cue casque prend 5 masques 48×22 (37 libres), le filtre par
piste 15 masques 35×35 (4 libres). C'est exactement la répartition tenue à la main dans la mémoire des fils
(`sprite-mask-allocation`), qu'il remplace. [FAIT]

## 6. Ce qui reste

- `[À FAIRE]` Déclarer dans `DECLARED` les octets de structures sauvegardées des autres mods à mesure que leurs notes
  les nomment (Model-TG, notes/31).
- `[À FAIRE]` Étape 3 du chemin : importer un mod perso (`.json`) dans le flasher avec ces mêmes contrôles ; décisions
  de Maxime attendues (règles 5 et 6 d'AGENTS.md, licence, catalogue).
- La place qui reste (20 Ko avec les branches ouvertes) borne ce qu'on peut encore ajouter en masques ; au-delà, la
  charge utile après l'OS (20 Ko aussi, après les moteurs sur Model-TG) ou l'étape 4 (une page qui place le code).
