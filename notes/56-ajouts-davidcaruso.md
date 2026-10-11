# 56 — Ajouts de DavidCaruso en mods séparés : machines VA, générateur de trigs, LFO 2, 3, 4

DavidCaruso a envoyé sur Discord un firmware complet, `Model-TG-VA-DR-v1.syx` : le Model-TG v1.1.0 de TinyGregAudio
avec trois ajouts de sa main, sans source ni licence publiées. Maxime l'a transmis sur le fil du projet le 10/10/2026 :
« Intègre ses ajouts en mods décomposés (n'ajoute que ce qui n'existe pas déjà dans le projet) ». Model-TG est déjà
dans le flasher : seuls les trois ajouts deviennent des mods, chacun avec sa carte, son générateur et sa preuve. Le code
est **réécrit** à partir de l'analyse de son binaire (comportement, algorithmes, accès à l'OS) : aucun de ses octets ni
aucune de ses instructions n'est dans le dépôt, et son fichier n'y est pas. Adresses : VA de l'OS 1.13 ; « chez David »
renvoie à la section 3 de son `.syx`, dépaquetée et exécutée pour l'analyse.

| Mod | Tweaks | Générateur, code | Preuve | Section |
|---|---|---|---|---|
| Générateur de trigs (SETTINGS + TRACK) | `49-generate.json` (sur `model-tg`), `49-generate-st.json` (sur `model-tg-st`) | `tools/gen_generate.py`, `tools/machines/generate/` | `tools/emu/test_generate.py` | §2 |
| LFO 2, 3, 4 | `60-lfo-plus.json` (avec ou sans Model-TG) | `tools/gen_lfo_plus.py`, `tools/machines/lfo_plus/` | `tools/emu/test_lfo_plus.py` | §3 |
| Machines VA, VA KICK, VA SNARE, VA HIHAT | `27-va.json` (seul), `36-va-tg.json` (sur `model-tg-st`) | `tools/gen_va.py`, `tools/machines/va/` | `tools/emu/test_va.py`, `tools/emu/va_ref.py` | §4 |

## En bref

- **Trois mods expérimentaux, à cocher séparément.** Le générateur demande Model-TG (il se sert de ses listes) ; les
  LFO vont partout, avec ou sans Model-TG ; les machines VA vont seules ou avec Model-TG, pas encore avec MACRO ni les
  moteurs du Syntakt (mêmes places de machines ajoutées).
- **Même comportement que chez David**, prouvé en émulation contre l'OS d'origine et, pour le son des machines VA,
  contre ses propres fonctions exécutées dans son firmware : mêmes échantillons, sauf l'aigu du VA HIHAT où deux
  calculs débordaient chez lui (§4.3.5).
- **Écarts voulus** : les accroches sont déplacées pour que les trois mods s'installent avec tous les nôtres sans
  écrire un octet qu'un autre écrit ; les machines VA ne sont plus des Samplers déguisés mais des machines ajoutées
  comme MACRO, donc aussi sans Model-TG ; les projets de David se rouvrent sur les mêmes machines avec Model-TG.
- **Place** : 7 masques 48×22 (générateur), 7 masques 34×34 et 1 180 o de mémoire au-dessus du BSS (LFO), une charge
  utile après l'image (VA). `tweaks/model-cycles_OS1.13/REGISTRY.md` est régénéré avec ces tweaks.
- **Pas encore testé sur la machine.** **Licence** : il faut l'accord de David (MIT, comme le reste du projet) avant
  de fusionner (§1.3).

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
| Menu Generate sur SETTINGS + TRACK | non | §2, demande Model-TG comme chez David |
| LFO 2, 3, 4 | non | §3, réécrit sans dépendre de Model-TG |
| Machines VA, VA KICK, VA SNARE, VA HIHAT | non | §4, machines ajoutées comme MACRO, seules ou avec Model-TG |

### 1.3 Provenance et licence

DavidCaruso n'a publié ni source ni licence. Le code d'ici est réécrit (aucun octet repris) ; pour LFO 2, le format de
rangement dans le son (octets +88..+91) est gardé pour que ses sons se rechargent. Le crédit est sur les cartes du
flasher (« based on a mod by DavidCaruso »), dans le guide, `PROVENANCE.md` et les descriptions des tweaks. Le
10/10/2026, le fil a demandé à Maxime d'obtenir l'accord de David (licence MIT) et, s'il veut bien, ses sources. Rien
n'a été envoyé à David de notre côté. `[À FAIRE]` Accord de David avant la fusion.

## 2. Générateur de trigs euclidien / aléatoire sur SETTINGS + TRACK (Model-TG)

Tweaks `49-generate.json` (sur `model-tg`) et `49-generate-st.json` (sur `model-tg-st`), mêmes écritures. Générateur `tools/gen_generate.py`, source `tools/machines/generate/generate.S` et `generate.ld`, preuve `tools/emu/test_generate.py`. Symboles de Model-TG v1.1.0 (mêmes adresses dans les deux tweaks Model-TG).

### En bref

- Tenir **SETTINGS**, appuyer sur **TRACK** : une liste « Generate » de 13 lignes s'ouvre, comme les menus
  d'options de Model-TG. La ligne **GEN** réécrit la piste sélectionnée : trigs euclidiens ou aléatoires, avec en
  option des notes tirées dans une gamme et des vélocités aléatoires, puis affiche « Trigs: N ».
- Il faut Model-TG (`requires`) : l'accord (SETTINGS tenu, relâchement avalé), la liste et sa gestion de LEVEL/DATA,
  le message, tout vient de Model-TG. Les deux versions de Model-TG ont leur tweak.
- 1 214 o de code et de données dans 7 masques de sprites 48×22 libérés ; une seule accroche, le `jmp key_hook` que
  Model-TG pose en `0x4007240c`, réécrit vers notre code qui y retourne.
- Prouvé en émulation (`TOUT OK`, les deux Model-TG, seul et avec d'autres mods). Pas encore essayé sur la machine.

### 2.1 Ce que voit le musicien

- **Ouvrir** : tenir SETTINGS, appuyer sur TRACK (SETTINGS d'abord). La liste porte sur la **piste sélectionnée à
  l'ouverture** (1 à 6, n'importe quelle machine).
- **Naviguer** : tourner LEVEL/DATA pour choisir une ligne, appuyer pour l'éditer, tourner pour changer la valeur,
  rappuyer pour sortir de l'édition. SETTINGS (ou RETURN) ferme, comme les listes de Model-TG.
- **13 lignes**, valeurs bornées (pas de rebouclage) :

| Ligne | Sens | Valeurs | Défaut |
|---|---|---|---|
| MOD | mode | RND (aléatoire) / EUC (euclidien) | RND |
| DNS | densité du mode RND, en % | 0 à 100 | 50 |
| HIT | coups du mode EUC | 1 à 64 | 4 |
| ROT | rotation du mode EUC, vers la droite, en pas | 0 à 63 | 0 |
| NOT | notes aléatoires dans la gamme | OFF / ON | OFF |
| KEY | tonique | C C# D D# E F F# G G# A A# B | C |
| SCL | gamme | MAJ MIN DOR PHR LYD MIX LOC HMI MMI PMA PMI BLU CHR | MAJ |
| OCT | octave de départ (note de départ 12 × (OCT + 1) + KEY : OCT 4 = do 60) | 0 à 8 | 4 |
| RNG | étendue en octaves | 1 à 4 | 1 |
| VEL | vélocité aléatoire | OFF / ON | OFF |
| VMN | vélocité mini | 1 à 127 | 64 |
| VMX | vélocité maxi (VMN > VMX : échangées) | 1 à 127 | 127 |
| GEN | appuyer génère | GO | — |

- **GEN** réécrit tous les pas de la piste, de 1 à sa longueur (64 au plus, toutes les pages), puis affiche
  « Trigs: N ». On peut rappuyer pour un autre tirage ; la liste reste ouverte.

### 2.2 Le code de l'OS et de Model-TG utilisé

#### 2.2.1 L'accord [FAIT]

| Adresse | Rôle |
|---|---|
| `0x4007240c` | accesseur du code d'un événement de touche (`moveal 4(sp),a0 ; movel 12(a0),d0 ; rts`), appelé par toutes les vues ; Model-TG y écrit `jmp key_hook` (`0x401ae968`) |
| événement `+12`, `+16` | code de la touche (TRACK = 2, SETTINGS = 13) ; drapeaux (bit 0 appui, bit 3 répétition, bit 4 clic, bit 5 appui long) |
| `key_hook` | teste `rtg_on` (`0x401b6d8c`, page Retrig) et `sle_on` (`0x401bcaec`, éditeur de tranches), puis SETTINGS (`kh_mod`), Preset, les touches de pas, et `set_held` → `kh_other` (code 6) → `kh_rs` (4, 9, 12) ; tout le reste rendu tel quel |
| `set_held` `0x401b235c` | SETTINGS tenu (posé et levé par `kh_mod`) |
| `mod_used` `0x401b2360` | un accord a servi : le relâchement de SETTINGS est avalé (pas de Config Menu) |
| `mm_opened` `0x401b20b4` | « la liste s'est ouverte », posé par `gm_opened` (`0x401b0b7e`) |

SETTINGS + TRACK ne sert ni à l'OS ni à Model-TG v1.1.0 : chez Model-TG, TRACK avec SETTINGS tenu traverse `kh_other`
et `kh_rs` et revient à l'OS [FAIT, source `vendor/Model-TG/src/model_tg.s`, et émulé : l'origine rend 2].

#### 2.2.2 La liste [FAIT]

| Adresse | Rôle |
|---|---|
| `gran_menu_open` `0x401b08ba` | ouverture d'une liste de Model-TG : cadre `link.w fp,#-80 ; lea -28(sp),sp ; movem.l d2-d4/a2-a5,(sp)`, puis `lm_build` ; sorties `gm_opened` (pose `mm_opened`, tombe dans `gm_done`) et `gm_done` (`0x401b0b86`, `movem` + `unlk` + `rts`) |
| `gm_live` `0x401b0c82` | une liste de Model-TG est déjà ouverte |
| `gm_track` `0x401b1218`, `gm_cur` `0x401b121c` | piste visée ; descripteur `{titre, nom de vue, nombre de lignes, lignes}`, lignes de 16 o `{libellé, valeur, rotation, appui}` |
| `lm_build` `0x401b095c` | construit la liste (classe de base des menus de réglages `0x400422a8`), un élément de menu de l'OS par ligne (`0x400734b0`, vtable `0x40103470`), l'ajoute par `0x40072ce6` → `0x4007320a`, qui écrit le **numéro de ligne en `+8`** de l'élément (seul appelant) ; présente la vue (`0x400d0974`, `0x400060d8`, `0x4007700e`) |
| élément `+24`, `+40`, `+56`, `+72` | invocateurs libellé, appui, valeur, rotation (fermeture copiée en `+12`, `+28`, `+44`, `+60`) ; `+0x50` = édition |
| `0x40073236`, `0x40073274`, `0x400732b6`, `0x4007329c` | méthodes de l'élément : libellé (`a0` = String), dessin (élément, contexte, rectangle, drapeau), rotation (élément, écart), appui (élément) ; chaque fermeture reçoit l'élément en second argument |
| `gm_lab` `0x401b0d56` | libellé : `a0` = String, `a1` = texte |
| `gm_val` `0x401b1096` | valeur : `a0` = &index, `a1` = table de textes ; dessin `0x400f85bc`, `0x40072260`, `0x40071a04`, `0x40072080` |
| `new_slot2_invoker` `0x401bb3a8` | appui d'une ligne : bascule l'édition |
| `show_popup` `0x401b2284` | message (teste l'interface prête `0x40fe4178`) |
| `gm_live`, `gm_top`, `gm_enc_gate` | reconnaissent une liste de Model-TG par `gm_obj` et sa table `gm_evt` (posées par `lm_build`), pas par son nom : notre liste reçoit LEVEL/DATA comme les siennes [FAIT, lecture de la source] |

#### 2.2.3 La grille [FAIT]

| Adresse | Rôle |
|---|---|
| `0x400cf866` | projet (`*0x40fe4228`) |
| `0x4000eb90` → `0x40012412` | piste sélectionnée |
| `0x4000f208` | pattern en cours = projet + 5 192 + 732 × pattern |
| `0x4000cfcc` | objet « piste » = pattern + 112 + 88 × piste (piste bornée à 0..5) |
| objet `vtable[40]` | données de la piste (722 o) : drapeaux des pas `+0` (mots ; bit 0 trig), vélocités `+128`, notes `+580` (octets signés, -1 = aucune), longueur `+713` (mot) |
| objet `vtable[16]` | signal de modification `(piste, {0x400ff59c, pas})` |
| `0x40016402` | longueur effective de la piste |
| `0x40017b48` | pose (1) ou efface (0) le trig de note d'un pas ; effacer remet le pas à zéro (`0x400169f0`, accroché par Model-TG pour ses slides, puis `0x400164f2`, `0x400165d6`) |
| `0x40016642`, `0x400166c2` | note, vélocité d'un pas (une valeur négative écrit -1) |
| `0x400005cc` | `vsprintf(tampon, format, va_list)` |
| `0x8000184c` | heure musicale (graine du tirage) |

Ce sont les mêmes appels, dans le même ordre, que l'enregistrement en direct de l'OS (`0x40012158`) : le résultat est
un pattern ordinaire, sauvé avec le projet [FAIT pour les appels ; HYP pour la propagation au séquenceur, par le
signal `vtable[16]` comme à la main].

### 2.3 Conception

#### 2.3.1 L'accord : `gen_key` devant `key_hook`

David a inséré son test devant `kh_rs`, en décalant le code de Model-TG : impossible en tweak, car Model-TG est une
charge utile ajoutée au bout de l'image (les écritures d'un tweak portent sur l'OS d'origine). Le `jmp key_hook` en
`0x4007240c` est, lui, une écriture ordinaire de Model-TG : notre tweak la réécrit en `jmp gen_key`, avec comme octets
d'origine ceux de Model-TG (`requires`). `gen_key` (`0x4018b9c8`) :

- code ≠ TRACK, ou `rtg_on` / `sle_on` (les mêmes tests que la tête de `key_hook`) → `jmp key_hook`, la pile
  intacte ;
- appui frais (bit 0, pas de bit 3) : `gen_ev = 0` ; si `set_held`, `gen_open` ; si `mm_opened` s'est levé : `gen_ev
  = 1`, `mod_used = 1`, bit 3 levé dans l'événement, `d0 = 0` (avalé), comme les accords de Model-TG ;
- relecture ou répétition d'un appui avalé (`gen_ev = 1`) → avalée ; sinon → `key_hook` ;
- relâchement : si `gen_ev = 1`, l'adresse de l'événement est notée dans `gen_ev` et il est avalé, ses relectures
  aussi (même adresse) ; sinon → `key_hook`.

Différence avec David : le relâchement de TRACK est avalé même si SETTINGS a été relâché avant (chez David, il passe
alors à l'OS sans l'appui qui va avec).

#### 2.3.2 La liste

- `gen_open` pousse sur la pile les 13 lignes, toutes identiques `{gen_lab, gen_val, gen_turn, gen_press}` (208 o
  sur la pile de la tâche de l'interface, 160 Ko, notes/44), les accroche à `gen_desc` et appelle `gen_build`, qui
  reprend le cadre de `gran_menu_open` pour que `lm_build` sorte par `gm_opened` / `gm_done`. Refus (TRACK rendu à
  l'OS) : en interruption, interface pas prête, piste sélectionnée ≥ 6. Une liste de Model-TG déjà ouverte
  (`gm_live`) : `gm_opened`, l'accord est avalé sans seconde liste. Sinon `gm_track` = piste, `gm_cur` = `gen_desc`,
  `jmp lm_build`. `lm_build` recopie chaque fermeture dans son élément : les lignes sur la pile ne servent plus
  après.
- **Une fermeture par sorte**, qui lit le numéro de ligne en `+8` de l'élément : 4 fermetures au lieu de 52.
- Libellés : `gm_lab` sur une table de 13 textes de 4 o. Valeurs : MOD, NOT, KEY, SCL, VEL, GEN par `gm_val` sur leur
  table de noms ; les nombres par `vsprintf("%d")` puis `gm_val` sur une table d'un texte (`gen_ptr`, index
  `gen_zero`).
- Rotation : réglage + écart, borné à [min, max] (un octet par réglage, `gen_set`). Appui : lignes 1 à 12 →
  `new_slot2_invoker` (édition) ; GEN → la génération, sans passer en édition.
- Titre « Generate » ; nom de vue = celui des listes de Model-TG (« GranularMenuView », sans effet : voir §2.2.2).

#### 2.3.3 La génération

```
piste = 0x4000cfcc(0x4000f208(0x400cf866()), gm_track)
n = min(0x40016402(piste), 64) ; si n <= 0 : fin
rng = rng + heure musicale + 0x9e3779b9 (0 -> 1)            ; xorshift32 (13, 17, 5) ; rndn(m) = ((x >> 16) × m) >> 16
si NOT : table = { 12 × (OCT+1) + KEY + d | d = 0 .. 12 × RNG inclus, d mod 12 dans la gamme, <= 127 }  (49 au plus)
k = min(HIT, n) ; r = ROT mod n
pour pas = 0 .. n-1 :
    on = RND ? rndn(100) < DNS : ((pas - r) mod n) × k mod n < k
    0x40017b48(piste, pas, on)
    0x40016642(piste, pas, on && NOT ? table[rndn(taille)] : -1)
    0x400166c2(piste, pas, on && VEL ? rndn(hi - lo + 1) + lo : -1)      ; lo, hi = VMN, VMX rangés
show_popup(vsprintf("Trigs: %d", nombre de trigs))
```

Mêmes algorithmes, même graine, même ordre des tirages et mêmes accesseurs que chez David (d'après l'analyse de son
binaire) [HYP : mêmes tirages que chez David à graine égale, non comparé à son binaire]. L'euclidien est calculé par
un accumulateur (avancé de n − r pas avant le premier) ; la preuve le compare à la forme fermée. Gammes en masques de
12 bits : MAJ `0xab5`, MIN `0x5ad`, DOR `0x6ad`, PHR `0x5ab`, LYD `0xad5`, MIX `0x6b5`, LOC `0x56b`, HMI `0x9ad`
(mineur harmonique), MMI `0xaad` (mineur mélodique), PMA `0x295`, PMI `0x4a9` (pentatoniques), BLU `0x4e9`, CHR
`0xfff`.

#### 2.3.4 L'état

Dans le premier masque, à la suite de `gen_key` : réglages (13 o), état du xorshift (`0x2545f491` au départ),
`gen_ev`, le texte d'un nombre, le descripteur. L'image est rechargée en mémoire à chaque démarrage : tout revient aux
valeurs par défaut, rien n'est sauvé dans le projet. Réglages communs aux 6 pistes.

### 2.4 Place utilisée

Sept des douze masques attribués (registre, notes/52), chacun redirigé vers la copie gardée `0x4014b364`
(`sprites.redirect_write`, même tweak) :

| Masque | Constante redirigée | Contenu | Octets |
|---|---|---|---|
| `0x4018b9c8` | `0x400ad048` | `gen_key`, l'état | 180 |
| `0x4018bb48` | `0x400ad028` | `gen_open`, `gen_build`, `gen_press`, `gen_put` | 184 |
| `0x4018cbc8` | `0x400acdce` | fermetures libellé / valeur / rotation, gammes, titre, format | 191 |
| `0x4018d038` | `0x400acd92` | `gen_go` (début de la génération) | 152 |
| `0x4018d798` | `0x400acd3a` | la boucle des pas, le message | 186 |
| `0x4018f80c` | `0x400ac894` | bornes, noms des valeurs | 159 |
| `0x40190184` | `0x400ac7e0` | table des notes, tirage, libellés | 162 |

Total 1 214 o. Six masques ne suffisent pas (1 152 o). Restent libres : `0x4019089c`, `0x40192a24`, `0x40190334`,
`0x4018a608`, `0x40188f98`. Gains possibles si la place manque : reprendre les noms OFF/ON de Model-TG (`gm_n_frz`)
et fusionner les tables de bornes (une quarantaine d'octets).

### 2.5 Conflits

- `requires` `model-tg` / `model-tg-st` : seule l'écriture de Model-TG en `0x4007240c` est recouverte, et c'est voulu
  [FAIT, `check_overlaps.py`]. Refusé seul et avec l'autre Model-TG [FAIT en émulation].
- `chord-keys` est déjà incompatible avec Model-TG.
- `sample-preview` (aussi sur Model-TG) : aucune écriture commune, accroches différentes ; prouvé ensemble [FAIT].
- Un futur mod qui voudrait aussi `0x4007240c` par-dessus Model-TG devra s'enchaîner derrière `gen_key` (le registre
  liste l'accroche).

### 2.6 Le tweak

15 écritures : l'accroche (6 o), 7 constantes de sprites (4 o), 7 masques. `gen_generate.py` compile `generate.S`
(`m68k-linux-gnu-gcc -mcpu=54418`, adresses de Model-TG en `-D`), vérifie que chaque masque est encore une copie du
masque gardé et le contrat avec Model-TG (têtes de `key_hook`, `gran_menu_open`, `gm_live`, `gm_opened`, `gm_done`,
`lm_build`, `gm_lab`, `gm_val`, `new_slot2_invoker`, `show_popup` ; `rtg_on`/`sle_on` testés en tête de `key_hook` ;
`gm_opened` pose `mm_opened` ; `lm_build` lit `gm_cur` ; variables à zéro ; nom de vue ; `jmp key_hook` en
`0x4007240c`), et refuse un écart. Pour qu'il lise les adresses dans les tweaks, `gen_model_tg.py` exporte 18
symboles de plus (`GEN_SYMBOLS`) ; seule la clé `symbols` de `30-model-tg*.json` a changé.

### 2.7 Preuve en émulation

```sh
python3 tools/gen_generate.py --cycles firmware/model-cycles_OS1.13.syx --check
python3 tools/emu/test_generate.py --cycles firmware/model-cycles_OS1.13.syx --syntakt firmware/Syntakt_OS1.42.syx
python3 tools/emu/test_generate.py --cycles firmware/model-cycles_OS1.13.syx \
    --with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max --syntakt firmware/Syntakt_OS1.42.syx
python3 tools/emu/test_generate.py --cycles firmware/model-cycles_OS1.13.syx \
    --with model-tg,sample-preview,6ch-usbup,arp,trig-hold,tempo-max
```

Le vrai code de l'OS, de Model-TG et du tweak (Unicorn), sur deux images construites depuis le .syx officiel :
l'origine (les mêmes tweaks sans Generate) et l'image modifiée. Résultat : `TOUT OK` dans les quatre jeux
(27 vérifications par version de Model-TG).

| | Origine (Model-TG) | Avec Generate |
|---|---|---|
| SETTINGS, TRACK (appui, relecture, répétition, relâchement, relecture), SETTINGS relâché | 13, 2, 2, 2, 2, 2, 13 (Config Menu) | 13, 0, 0, 0, 0, 0, 0 : liste ouverte une fois, `gm_track` = 2, `mod_used`, pas de Config Menu |
| TRACK seul ensuite | 2 | 2 |
| 409 autres cas (codes 0 à 40, drapeaux, SETTINGS tenu ou pas, page Retrig, éditeur de tranches) | `key_hook` | `key_hook` avec la même pile, aucune écriture en mémoire |
| Interface pas prête, en interruption, piste 6 | TRACK rendu | TRACK rendu, pas de liste |
| Liste de Model-TG déjà ouverte | — | accord avalé, pas de seconde liste |
| Vrai `lm_build` | — | 13 éléments de l'OS, numéro de ligne en `+8`, titre « Generate » ; libellés et valeurs par les méthodes de l'OS ; rotations bornées ; appui = édition (lignes 1 à 12) ; GEN génère |
| GEN, vrais accesseurs de la grille | — | 313 générations identiques pas à pas à une référence Python (euclidien longueurs 1 à 64, coups 1 à 64, rotations ; DNS 0 à 100 ; 13 gammes, toniques, octaves, étendues ; vélocités bornées et échangées) ; état du xorshift ; « Trigs: N » ; pas au-delà de la longueur et autres pistes intacts ; registres rendus |
| Motifs | — | 4/16 `x...x...x...x...`, 3/8 `x..x..x.`, 5/16 rot 2 `..x...x..x..x..x`, 5/12 rot 13 `.x..x.x..x.x` |
| Pas déjà remplis (EUC 4/16) | — | trigs effacés hors motif, trig de lock devenu trig de note, slide de Model-TG gardé sur un pas qui reste un trig, notes et vélocités à -1 (NOT, VEL sur OFF) |

Coût d'un GEN de 64 pas : 160 000 à 190 000 instructions (dont 4 800 dans notre code), 1 550 à 1 800 signaux de
modification (bouchés en émulation), une fois par appui, dans la tâche de l'interface ; rien dans l'audio.

### 2.8 Limites

- Réglages communs aux pistes, perdus à l'extinction, pas sauvés avec le projet.
- GEN réécrit toute la piste, sans annulation : les trigs hors motif sont effacés avec leurs p-locks ; un trig de
  lock du motif devient un trig de note.
- NOT sur OFF remet les notes des pas à « aucune », VEL sur OFF les vélocités, sur tous les pas (choix de David,
  gardé).
- La piste visée est celle de l'ouverture, même si l'on change de piste liste ouverte.
- Pas sur la page Retrig ni dans l'éditeur de tranches (TRACK y garde son rôle) ; pas d'ouverture si une autre liste
  de Model-TG est déjà ouverte.

### 2.9 À essayer sur la machine [À FAIRE]

Flasher Model-TG + Generate (puis Model-TG avec les moteurs du Syntakt + Generate) :

1. Tenir SETTINGS, appuyer sur TRACK : la liste « Generate » s'ouvre ; relâcher : pas de Config Menu. SETTINGS seul
   ouvre toujours le Config Menu ; les accords de Model-TG marchent toujours.
2. Tourner LEVEL/DATA : la sélection descend les 13 lignes ; appuyer, tourner, rappuyer : les valeurs changent et
   s'arrêtent aux bornes.
3. Sur GEN, appuyer : « Trigs: N », les touches de pas montrent le motif (dire s'il faut fermer la liste pour le
   voir) ; essayer EUC 4 coups sur 16 pas, puis RND avec NOT et VEL, écouter.
4. Dire si GEN part à l'appui ou au relâchement de DATA, et s'il y a un à-coup audible pendant la génération
   (64 pas, séquenceur en marche).
5. Sauver le projet, le recharger : le motif généré est là.

### 2.10 Questions ouvertes

- GEN au clic ou à l'appui de DATA ; affichage du motif sur les touches tout de suite après GEN.
- Coût réel des ~1 800 signaux de modification, séquenceur en marche [HYP : sans conséquence, autant que 64 saisies].
- Garder « NOT / VEL sur OFF efface », ou ne rien toucher quand c'est OFF ?
- Sauver les réglages par piste avec le pattern ?
- Variante sans Model-TG : non faite (il faudrait refaire l'accord et la liste, environ 3 Ko).

## 3. LFO 2, 3, 4 : trois LFO de plus par piste

Tweak `60-lfo-plus.json`, id `lfo-plus`, seul, avec ou sans Model-TG, et avec tous les autres mods. Générateur `tools/gen_lfo_plus.py`, code `tools/machines/lfo_plus/lfo_plus.S` (assembleur ColdFire), preuve `tools/emu/test_lfo_plus.py`.

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

**Aucun.** `tools/check_overlaps.py` passe sans `conflicts` : aucun autre tweak n'écrit ces octets (155 tweaks).
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
- `va` ;
- `model-tg-st,va-tg,generate-st` (tweaks VA et Generate en cours).

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

### 3.10 À essayer sur la machine `[À FAIRE]`

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

## 4. Machines VA : le synthé VA et les batteries VA KICK, VA SNARE, VA HIHAT de DavidCaruso, en machines ajoutées


Demande de Maxime (fil du projet, 10/10/2026) : « Intègre ses ajouts en mods décomposés (n'ajoute que ce qui
n'existe pas déjà dans le projet) ». Il s'agit du firmware « Model-TG-VA-DR-v1 » publié par DavidCaruso : Model-TG
v1.1.0 modifié, avec 4 LFO de plus, un générateur de trigs, et 4 machines « Virtual Analog » : VA (synthé léger à
2 oscillateurs, basses et leads), VA KICK, VA SNARE, VA HIHAT. Cette section traite des **4 machines**. Le générateur de
trigs est au §2, les LFO au §3.

Tweaks `27-va.json` (seul, machines 7 à 10) et `36-va-tg.json` (avec Model-TG, par-dessus `30-model-tg-st.json`,
machines 8 à 11). Générateur `tools/gen_va.py`, code `tools/machines/va/va.c`, référence `tools/emu/va_ref.py`, preuve
`tools/emu/test_va.py`. Adresses : VA de l'OS 1.13. Les adresses « chez David » sont celles de la section 3 de son
`.syx`, lu et exécuté pour l'analyse (rien de son fichier n'est dans le dépôt).

### Réponse courte

- **Chez David, les 4 machines sont des Samplers déguisés** `[FAIT]`. La voix reçoit la machine 6 (le Sampler de
  Model-TG), et une insertion au milieu de `sampler_render` remplace la lecture d'échantillon par son rendu. Elles ne
  marchent donc qu'avec Model-TG. Le calcul du son, lui, est autonome : il ne lit que les 4 potards, la hauteur de
  TONE et le front de trig.
- **Ici, ce sont des machines ajoutées, comme MACRO** (notes/43) : 4 machines après CHORD, seules ou avec Model-TG,
  même mécanique (`gs.detours_asm` pour N = 4, charge utile, crochet de démarrage PACK). Avec Model-TG, elles portent
  les numéros de David (8 à 11) : ses projets se rouvrent sur les mêmes machines.
- **Le son est celui de David, échantillon par échantillon** `[FAIT en émulation]`. Ses algorithmes sont réécrits en
  C (`va.c`), sans aucun de ses octets. Ses fonctions, exécutées à ses adresses dans son firmware, donnent les mêmes
  échantillons que notre code compilé. Dans la boucle des voix, son firmware et le nôtre (avec Model-TG) donnent la
  même sortie de piste. **Une exception** : l'aigu du VA HIHAT, où deux calculs 32 bits débordaient chez lui (§4.3.5).
- **Charge** : une voix VA coûte à peu près une voix TONE, de 0,8 à 1,1 fois. VA KICK et VA SNARE coûtent 1,4 fois,
  VA HIHAT 1,8 fois (§4.8). Une voix muette n'est pas calculée.
- **Deux défauts trouvés et corrigés** :
  - le 1er trig après un changement de machine (§4.3.2) ;
  - un appel terminal du compilateur qui privait les batteries de l'Attack et du Filtre de Model-TG (§4.3.7).
- **À trancher** : David n'a publié ni source ni licence (§4.5).

### 4.1 Le firmware de David `[FAIT]`

#### 4.1.1 Branchement

Analyse complète : `va-integration.md`, `va-synth.md`, `va-drums.md`, dans le dossier d'analyse. En bref :

- **Numéros.** Machines 7 (VA), 8 (VA KICK), 9 (VA SNARE) et 10 (VA HIHAT), après le Sampler (6) de Model-TG. Le
  numéro réel est l'octet machine du son (trackData+18), relu à chaque bloc par `sampler_pre`. La voix, elle, reçoit
  `voix@0 = 6`.
- **Chemin audio.**
  1. Le dispatch (0x401bf2fa chez David) lit les potards.
  2. Il détecte le front de trig (`*a5 ≠ 0` et `*a3 = 0`, c'est-à-dire v+0x34 posé et v+0x38 nul).
  3. Il force la machine 6 et reprend le chemin du Sampler.
  4. Ce chemin appelle l'update de TONE 0x400aa7b8, puis `sampler_render`.
  5. `sampler_render` saute au rendu VA, qui écrit 64 échantillons à 96 kHz dans `sampler_buf+32`.
  6. La suite est la queue du Sampler : décimation 0x400a9f58, enveloppe 0x400a9252, VCA 0x400a9430, puis
     `amp_hook`. Celui-ci fait PUNCH 0x400a967a, la rampe d'Attack, le gain de sortie des batteries (`ah_mid`), le
     Filtre/Résonance (`gflt_run`) et le rééchantillonnage.
- **Hauteur.** `pas = ((v232 >> 4) · 93 957) >> 12` (0 → 1,0), la formule du Sampler de Model-TG. v+232 est
  l'incrément de l'opérateur 1 de TONE, calculé par son update d'après la note, PITCH et FINE.
- **Interface.**
  - Libellés : `apply_names` change le nom des 4 potards dans la table d'origine, un jeu par machine.
  - Descripteurs : ceux du Sampler (Pitch, Amp Decay).
  - Défauts : écrits par `mc_commit_hook`. Amp Decay à 64, celui du Sampler, pour les quatre.

#### 4.1.2 Les algorithmes

Entiers 32 bits, 64 échantillons par bloc à 96 kHz, sortie `échantillon << 15`. Ils sont décrits au bit près dans
`tools/emu/va_ref.py`, leur référence exécutable, et dans les commentaires de `tools/machines/va/va.c`.

| Machine | Potards (COLOR, SHAPE, SWEEP, CONTOUR), défauts de David | Son |
|---|---|---|
| VA | Osc1 Wave 0, Osc2 Wave 0, Osc2 Tune 68, Osc Mix 64 | 2 oscillateurs scie / carré / triangle (seuils 0..42, 43..85, 86..127), PolyBLEP à 2 points sur scie et carré. Osc2 Tune : rapport 2^(0,1u + 0,9u³), d'une octave en dessous à une au-dessus, fin au centre (68 : +7,9 cents). Osc Mix 0..252 puis 256. Dérive lente ±1 cent par oscillateur, un générateur pour toutes les pistes. Phases remises au trig (oscillateur 2 un peu au hasard). |
| VA KICK | Sweep Depth 48, Sweep Time 40, Drive 24, Click 40 | Sinus parabolique, 55 Hz à la note 60. Balayage de hauteur jusqu'à ×5 à l'attaque, constante de temps 2 à 150 ms. Click : bruit de 1,33 ms à l'attaque. Drive : gain puis saturation douce. |
| VA SNARE | Noise Mix 64, Pitch Drop 32, Noise Tone 88, Drive 16 | Corps : sinus à 180 Hz à la note 60, chute de hauteur jusqu'à ×3 en 15 ms, enveloppe de 85 ms. Bruit : passe-bas 300 Hz..16 kHz puis passe-haut fixe ≈ 480 Hz. Drive. |
| VA HIHAT | Tone 80, Spread 64, Noise 16, Drive 0 | 6 carrés aux rapports du TR-808 (205,3 à 800 Hz à la note 60), Spread autour de leur moyenne (64 = 808), plus du bruit. Deux passe-haut d'un pôle (2,9 à 11,7 kHz). Drive. Oscillateurs libres, pas de remise en phase au trig. |

Batteries, après PUNCH : gain fixe ×4/3, ×5/3, ×8/3, puis saturation douce, même Drive à 0. Les deux générateurs
(dérive du VA et bruit des batteries) sont communs à toutes les pistes, dans l'ordre de rendu.

#### 4.1.3 Défauts relevés chez David

1. **VA HIHAT, Spread.** `incₖ = muls((incₖ − moyenne) >> 2, 2·Spread) >> 5` prend les 32 bits bas d'un produit qui
   dépasse 2³¹ dans l'aigu : à partir de la note 90 environ à Spread 64, de la note 78 à Spread 100 ou 127. Les
   fréquences sont alors fausses.
2. **VA HIHAT, moyenne.** La somme des 6 incréments est prise modulo 2³² avant la division par 6 : elle est fausse à
   partir de la note 105 environ.
3. **Hauteur au-delà de la note 107** (avec PITCH au milieu). `(v232 >> 4) · 93 957` déborde 32 bits à partir de
   +48 demi-tons : la hauteur retombe dans le grave. C'est la formule du Sampler de Model-TG, gardée ici telle
   quelle (§4.9).
4. **1re note après un changement de machine.** Pas de défaut chez David : son chemin applique la machine dès le bloc
   du trig, et le front y est vu. Chez nous, il faut une règle de plus (§4.3.2).

### 4.2 La mécanique : celle de MACRO, pour 4 machines

`tools/gen_va.py` est `gen_macro.build_tweak` généralisé à N = 4. La sortie de `gen_macro.py` est inchangée.
Il reprend :

- **Les détours** `gs.detours_asm(4, images, firsts, tg)`, avec 5 descripteurs par machine (76..95) sur le modèle de
  ceux de SNARE. Ils couvrent les rangées des LFO, les enregistrements, les recherches, la molette, les repères sur
  2 lignes et les icônes.
- **Les tables déplacées dans la charge utile** : descripteurs, rangées, noms, update/render, machine → enregistrement.
- **Les bornes** : 76/75 → 96/95 et 5 → 9 (seules) ou 10 (avec Model-TG).
- **Le crochet de démarrage** `stub.S` PACK.
- **Avec Model-TG** :
  - le détour du dispatch de MACRO (`gen_macro.dispatch_tg_asm`) : update, render, puis `ah_noenv` ;
  - le chaînage de `descr_hook`, `descr_b_hook`, `sampler_lfo_gate`, `sampler_amp_gate` et du crochet de
    démarrage de Model-TG.

| | Seules (`va`) | Avec Model-TG (`va-tg`) |
|---|---|---|
| Machines | 7 à 10 (index 6..9) | 8 à 11 (index 7..10) |
| Écritures dans l'OS | 122 | 114 |
| Ajout à l'image | 13 668 o, à 0x401aa140 | 14 004 o, à 0x401bf8c0 (après Model-TG) |
| Charge utile en mémoire | 0x43000000 (221 688 o, BSS compris) | 0x46700000 (idem) |
| Code et tables de `va.c` | 6 976 o | 6 976 o |
| Détours | 934 o | 1 256 o |
| Variables (6 pistes × 84 o) | 504 o à +0x36000 | idem |
| Crochet de démarrage | 104 o, masque 0x4016cae8 (sprite 0x400b1106 redirigé) | 96 o, même masque |
| Envoi USB à heure fixe, boucle des voix | notes/35, notes/36, comme MACRO (masque 0x4015c044) | ceux de model-tg-st |

La charge utile ne s'exécute qu'après l'invalidation du cache d'instructions par l'OS (0x40000548, `movec cacr`) :
il n'y a rien à vider, comme pour MACRO, testée sur la machine.

### 4.3 Conception

#### 4.3.1 La passerelle (`va.c`)

Contrat de la boucle des voix : `update(pmod, v, p)` puis `render(out, v)` (notes/14, notes/43).

- **`va_update`** (le même pour les 4 machines). Il appelle l'update de TONE 0x400aa7b8, comme le chemin du Sampler
  chez David. Elle calcule la hauteur en v+232, l'enveloppe d'ampli (DECAY, GATE) et PUNCH. Ensuite il lit les 4
  potards (mot 8.8 → 0..127, `dial`) et le front de trig.
- **`va_render_va`, `_kick`, `_snare`, `_hihat`** :
  1. le pas est calculé d'après v+232, par la formule de Model-TG ;
  2. 64 échantillons à 96 kHz vont dans le tampon de TONE (0x8000c05c + 8 mots, en SRAM) ;
  3. puis viennent la queue du render de TONE : 0x400a9f58 (décimation 2:1, avec l'historique propre à la voix),
     0x400a9252, 0x400a9430, 0x400a967a ;
  4. pour les batteries seulement, le gain et la saturation (`va_post`).
- **État** : `struct trk` de 84 o par piste (phases, dérives, enveloppes, filtres, 6 phases du hihat, potards,
  trig) et les deux générateurs. Ils ont les valeurs de départ de David (0x6d2b79f5, 0x1f123bb5).

#### 4.3.2 Front de trig et 1er bloc sur la machine `[FAIT en émulation]`

Le front est la règle de David : v+0x34 posé et v+0x38 nul. Mais l'OS ne change de machine qu'au bloc qui **suit**
le trig, quand v+0x38 ≠ 0 (0x400a7dac). À ce moment, la remise à zéro de la voix (0x400a7ab8) efface 0x00..0x3c, puis
pose v+0x38 = 1. Le 1er bloc sur une machine VA ne voit donc jamais de front. Le KICK perdrait son balayage et son
click, et le VA ses phases de départ.

Règle ajoutée : un repère `'VAM1'` est posé en **v+0x24**.

- Ce champ est effacé par la remise à zéro.
- Ni la chaîne de TONE ni Model-TG ne le lisent ni ne l'écrivent. Seul 0x400a9a74..0x400a9adc, une autre machine,
  s'en sert. Ce relevé est fait en émulation, champ par champ.
- MACRO met le sien en v+0x2c, mais l'update de TONE réécrit ce champ à chaque bloc.

Quand le repère manque, l'état de la piste repart de zéro et la note est jouée. Machine lock d'une machine VA à une
autre : l'index change, la voix est remise à zéro, l'état aussi.

#### 4.3.3 Voix muette

Une voix est muette sans trig (v+0x34, v+0x38) et avec une enveloppe d'ampli sous 2¹⁴ (v+0x230, v+0x234), comme pour
MACRO. Elle n'a ni update de TONE ni rendu, et sa sortie est nulle. Au trig, v+0x34 ou v+0x38 est posé, donc la voix
repart.

Chez David, le critère est `voice_quiet` de Model-TG : seuil, gains du mixeur, compteur de silence. Seule la toute fin
de note diffère, bien sous −100 dB.

#### 4.3.4 Arithmétique

Le C ne s'autorise aucun comportement indéfini. Les produits passent par des `u32` (`mulsl`) et les décalages à
gauche par `shl`. Il n'y a pas de 64 bits ni de bibliothèque (`-nostdlib`), et pas d'EMAC : `gen_va.py` refuse le code
qui en contiendrait, car la boucle des voix laisse MACSR en fractionnaire.

Les tables (Osc2 Tune, Sweep Time, filtres) sont **calculées par formule** (`va_ref.c_header`). Elles sont identiques
aux 128 valeurs de David : `--david` les compare. Les rapports du 808 et les gains sont des constantes.

#### 4.3.5 Les deux corrections du VA HIHAT `[FAIT en émulation]`

- **Spread** : `(d >> 4)·P + ((d & 15)·P) >> 4` avec `d = (inc − moyenne) >> 2`. C'est exactement ⌊d·P/16⌋, donc
  le calcul de David chaque fois que son produit ne déborde pas.
- **Moyenne** : `a = Σ(inc >> 3)`, `b = Σ(inc & 7)`, `moyenne = 4·(a/3) + (8·(a mod 3) + b)/6`. C'est la partie
  entière exacte de la somme complète divisée par 6.

En dehors des débordements, le son est celui de David au bit près. `va_ref.Dsp(…, david=True)` refait ses deux
débordements. `--david` vérifie que c'est exactement son code, et que les écarts entre lui et nous tombent
exactement sur ces blocs.

#### 4.3.6 Avec Model-TG

- **Le chemin.** Le détour de MACRO envoie les machines ≥ 7 à nos update/render, puis à `ah_noenv`, la fin de
  `amp_hook` : rampe d'Attack, Filtre/Résonance, rééchantillonnage, gain de piste. Le temps de calcul est compté sur
  la page System (`prof_trk`).
- **L'ordre du gain des batteries.** Chez David, il vient après la rampe d'Attack (`ah_mid`). Ici, il est dans le
  render, donc avant. Avec Attack à 0, c'est identique : `atk_step = 0`, pas de rampe, et c'est le cas comparé à son
  firmware. Avec une Attack, la saturation douce s'applique ici avant la rampe : l'attaque est un peu moins écrasée
  que chez David. `[HYP]` inaudible en pratique ; pas mesuré.
- **Attack, Filtre, Résonance.** Ils sont sous MACHINES tenue (`mod_held`), comme pour toutes les machines ajoutées.
  `tms.interface` le vérifie.

#### 4.3.7 Défaut trouvé par la preuve : l'appel terminal `[FAIT en émulation]`

Avec `-O2`, GCC compilait `va_post(out, kind)` en fin de render comme un `jmp`. Il réécrivait alors les arguments
reçus sur la pile (out, v) en (out, kind). Or notre détour avec Model-TG réutilise justement les arguments du render
pour appeler `ah_noenv(sortie, voix)`. `ah_noenv` recevait donc « voix = 1, 2 ou 3 », ne trouvait pas la piste
(`ah_find`), et sortait sans rien faire. VA KICK, VA SNARE et VA HIHAT perdaient Attack, Filtre, Résonance et le
rééchantillonnage.

Corrigé par `-fno-optimize-sibling-calls` (`gen_va.py`, `CFLAGS`). La preuve compte maintenant un appel de
`ah_noenv` par bloc de piste VA, avec la sortie attendue. Elle vérifie aussi qu'Attack 64 et Filtre 30 changent le
son des 4 machines.

MACRO n'est pas touchée : son render ne finit pas par un appel terminal. `[HYP]` à revérifier si son code change.

#### 4.3.8 Interface

- **Noms** : « VA », « VA KICK », « VA SNARE », « VA HIHAT », ceux de David. Le nom est centré à x = 32 dans la moitié
  gauche de l'écran MACHINES (police 5x9, 6 points par caractère). 8 caractères font 47 points, de x = 9 à 55, et les
  repères commencent à x = 76. Model-TG s'en tient à 7 caractères pour le nom défilant du Sampler, mais 8 tiennent.
  La preuve le vérifie, ainsi que les noms entiers en mémoire.
- **Potards** : les noms longs et courts de David (OSC1, OSC2, DTUN, MIX ; SWP, STM, SAT, CLK ; NOIS, PENV, TONE, SAT ;
  TONE, SPRD, NOIS, SAT), plage 0..127. Les seuils des formes d'onde restent 0..42 / 43..85 / 86..127, pour que ses
  projets sonnent pareil.
- **Amp Decay par défaut** (choix fait ici) :
  - VA : 64, comme chez David ;
  - batteries : celui de la machine d'origine dont elles prennent l'image, KICK 28, SNARE 40, METAL 20.

  David laisse 64, le défaut du Sampler, aux quatre. Or DECAY règle l'enveloppe d'ampli de TONE, que nos quatre
  machines suivent : mesurée en émulation sur TONE, elle passe sous le seuil de silence de la passerelle (2¹⁴) en
  15 ms à DECAY 5, 0,09 s à 12, 0,28 s à 20, 0,63 s à 28, 1,5 s à 40 et 4,7 s à 64 (22, 130, 422, 941, 2233 et
  7068 blocs de 0,67 ms). Un charleston qui s'entend plusieurs secondes ne ressemble plus à un charleston. Seul le défaut
  change : un projet de David garde ses valeurs.
- **Images** : VA → TONE, VA KICK → KICK, VA SNARE → SNARE, VA HIHAT → METAL. L'OS n'en a que 6. David en dessinait
  de nouvelles, qui ne sont pas reprises ici.

### 4.4 Place

Les écritures dans l'OS sont celles de MACRO pour N = 4. Le code tient dans la charge utile après l'image. Le seul
masque de sprite pris est celui du crochet de démarrage (0x4016cae8, partagé avec MACRO, d'où l'incompatibilité),
plus le masque 0x4015c044 de notes/35 et notes/36 (seules), mêmes octets que MACRO et Model-TG. Le registre
(`tools/registry.py --check`) l'accepte : 157 tweaks, 164 masques libérables, 125 libres.

### 4.5 Provenance et licence

- **Ce qui vient de David** :
  - les algorithmes, relus dans son firmware et réécrits ;
  - les noms des machines et des potards ;
  - les défauts des potards ;
  - les constantes (rapports du 808, gains, graines) ;
  - les formules des tables, retrouvées et vérifiées.
- **Ce qui ne vient pas de lui** : aucun de ses octets, aucune image.
- **Licence** : David n'a publié ni source ni licence. Le code est une réécriture, mais le son, les noms et le choix
  des paramètres sont les siens. **À demander à David** : son accord, et le crédit qu'il souhaite. Carte du flasher
  et `PROVENANCE.md` : « VA machines by DavidCaruso (from Model-TG-VA-DR-v1), rewritten for this project ».

### 4.6 Incompatibilités

`27-va.json` exclut 136 tweaks : MACRO, MACRO-TG, Model-TG (les deux ; il y a `va-tg` pour cela), SD VINTAGE 7th /
exact / snare, `va-tg`, et toutes les combinaisons des moteurs du Syntakt (128), seuls ou avec MACRO. `36-va-tg.json`
exclut 135 tweaks et demande `model-tg-st`. Ces mods ajoutent tous des machines au même endroit (le même bloc après
l'image, les mêmes tables). Une version combinée VA + moteurs du Syntakt ou VA + MACRO serait possible (même
mécanique, `gen_macro_syntakt.py`), mais n'est pas faite.

Elles s'installent avec tout le reste, notamment le générateur de trigs (§2, `generate-st` avec `va-tg`) et les
LFO 2 à 4 (§3, `lfo-plus`), l'arpégiateur, trig-hold, tempo-max et le 6 canaux : la preuve les joue ensemble (§4.7).

`tools/check_overlaps.py` : ok (157 tweaks, 16 575 écritures, aucune écriture partagée hors cas prévus).

### 4.7 Preuve en émulation `[FAIT en émulation]`

```sh
python3 tools/gen_va.py --cycles firmware/model-cycles_OS1.13.syx --check
python3 tools/emu/test_va.py --cycles firmware/model-cycles_OS1.13.syx \
    [--quick] [--david firmware/david/Model-TG-VA-DR-v1.syx] \
    [--with model-tg-st,generate-st,arp,tempo-max,lfo-plus | --with 6ch-usbup,arp,trig-hold,tempo-max,lfo-plus]
```

MAIN OS patché (`tools/build.py`, SHA-256) :

| `-t` | MAIN OS |
|---|---|
| `va` | `5e7ec9e18a2ad9ec0dfc5804c17be46706264cd30b31ecd54f551a81166259cc` |
| `model-tg-st,va-tg` | `af009dd2da9e70e95bb749b7363d8d21d8eeb558c839bbae387301a00d827359` |
| `6ch-usbup,va` | `cbc45da6ae0ce2accb6b7adf6143f851d89e84975f422a0e461da1171d444953` |
| `model-tg-st,va-tg,arp` | `f2de4469b70d13159857bb2756b11aab46cc8b85e10c4acfd22df5b318854ae2` |

| Vérification | Résultat |
|---|---|
| Démarrage (seules / avec Model-TG) | charge utile reconstituée octet pour octet, SRAM intacte, BSS de l'OS remis à zéro ou `boot_extra_hook` de Model-TG atteint, registres et pile intacts ; décompresseur du bootstrap sur l'OS agrandi |
| Interface | les vérifications de `test_syntakt_machines.py` (seules) et `test_model_tg_syntakt.py` (avec Model-TG) pour 4 machines : rangées, descripteurs 76..95 (noms, plages, défauts), recherches, CC 16..19, écran MACHINES (10 ou 11 repères sur 2 lignes), molette, enregistrements, changement de machine réel (défauts posés), potards, icônes, machine hors limites ; noms entiers et largeur |
| Code seul | `va_fill` et `va_post` compilés = `va_ref` au bit près, état et générateurs compris (2 040 blocs avec `--quick`, 8 000 et plus sans) |
| Boucle des voix, à chaque bloc | tampon à 96 kHz donné au décimateur = `va_ref` nourri de ce que voit la passerelle ; état identique ; potards lus = réglés ; voix muette ni mise à jour ni calculée ; 1er bloc sur la machine ; `va_post` ; sortie de piste |
| Chaîne d'ampli | mêmes lectures de la voix que TONE (DECAY, GATE, PUNCH) ; les 4 machines se taisent au bloc où TONE passe sous le seuil : DECAY 5, 12, 20, 28 → blocs 22, 130, 422, 941 |
| Hauteur | VA, KICK, SNARE : la note et PITCH (notes 36 à 96, PITCH 52 à 76), écart mesuré 0,04 % au plus (tolérance 0,4 %) ; VA note 60 = 261,5 Hz, KICK 55,0 Hz, SNARE 179,9 Hz |
| Potards | chacun des 16 change le son ; formes d'onde 0 = 42, 43 = 85, 86 = 127, 42 ≠ 43, 85 ≠ 86 |
| Machines d'origine | identiques à l'OS d'origine (ou à Model-TG seul), sans une instruction de `va.c` ; machine locks ; 6 pistes VA ; pistes mêlées (et Sampler) |
| Avec Model-TG | `ah_noenv` une fois par bloc de piste VA, avec la sortie attendue ; VA avec Model-TG = VA seule (Attack 0, filtre ouvert) ; Attack et Filtre agissent |
| `--david` | ses fonctions à ses adresses = `va_ref` « david » au bit près (état à ses adresses) ; notre code = le sien hors débordements ; dans la boucle des voix, même tampon et même sortie de piste, bloc par bloc, tant que les deux voix sont calculées ; HIHAT note 96 Spread 127 : différent dès le 1er bloc |
| Coût | §4.8 |

### 4.8 Charge `[FAIT en émulation]`

Instructions par bloc de 32 trames pour une voix : la boucle des voix entière, moins la même boucle sans voix
(`test_va.py`, section coût, seules). Les décalages de MACRO et de TONE sont mesurés de la même façon.

| Voix | En jeu | 1er bloc | Rapport à TONE |
|---|---|---|---|
| VA scie + scie (défauts) | 5 403 | 5 954 | 1,02 |
| VA carré + carré | 6 011 | 6 707 | 1,14 |
| VA triangle + triangle | 5 633 | 5 965 | 1,06 |
| VA un oscillateur (Osc Mix 0) | 4 091 | 4 642 | 0,77 |
| VA KICK | 7 358 | 7 793 | 1,39 |
| VA SNARE | 7 566 | 7 938 | 1,43 |
| VA HIHAT | 9 567 | 10 113 | 1,81 |
| TONE | 5 291 | | 1 |
| MACRO CSAW / WAVETABLES | 7 775 / 11 014 | | 1,47 / 2,08 |
| Voix VA muette | 214 | | |

Pile : 464 o au plus sous la boucle des voix. Avec Model-TG (`va-tg`), chaque voix coûte 59 instructions de plus
(VA scie + scie 5 462, VA KICK 7 417, VA SNARE 7 625, VA HIHAT 9 626), TONE 5 671.

Avec Model-TG, la boucle des 6 voix complète, une piste jouée, instructions par bloc (`--david`, David / nous) :

| Machine | David | Nous |
|---|---|---|
| VA | 7 807 | 6 988 |
| VA KICK | 10 239 | 8 943 |
| VA SNARE | 10 347 | 9 151 |
| VA HIHAT | 10 062 | 11 152 |

Nous sommes plus légers que David, sauf sur le HIHAT. Les corrections n'y coûtent que quelques dizaines
d'instructions par bloc. `[HYP]` L'écart vient de la boucle des 6 oscillateurs (64 × 6 par bloc), compilée par GCC,
moins serrée que l'assembleur de David. Le chemin de David passe en plus par 0x400a9120 (enveloppes des opérateurs de
TONE, inutiles ici) et par la plomberie du Sampler.

`[HYP]` Sur la machine, les accès à la SDRAM (code et tables hors du cache) peuvent alourdir ces chiffres, comme pour
MACRO.

### 4.9 Limites connues

- **Notes au-delà de 107** (note + PITCH − 64) : la hauteur repart du grave. C'est la formule de Model-TG, gardée pour
  être identique à David. Une correction est facile (produit en deux morceaux), mais elle s'écarterait de son
  firmware : à décider (§4.11).
- **Générateurs communs aux pistes.** Comme chez David, deux pistes VA ou batterie jouées ensemble ne sonnent pas
  exactement comme chacune seule : la dérive et le bruit sont pris dans l'ordre des pistes. C'est inaudible, mais la
  preuve compare donc au modèle et non à « la piste seule ».
- **Gain des batteries avant l'Attack de Model-TG** (§4.3.6).
- **Pas de régulateur de charge** (comme MACRO seule). Les voix sont légères.

### 4.10 À vérifier sur la machine

1. Seules (27-va) : MACHINES → les 4 machines après Chord, noms entiers, icônes. Chaque machine joue, suit les notes
   du clavier et PITCH, DECAY règle la durée, chaque potard agit.
2. Changement de machine par p-lock (machine lock) de CHORD à VA KICK : le 1er coup a bien son balayage et son click.
3. 6 pistes VA en même temps : pas de craquement.
4. Avec Model-TG (model-tg-st + va-tg) : les mêmes, puis MACHINES tenu + DECAY / SWEEP / CONTOUR (Attack, Filtre,
   Résonance) sur VA et sur VA KICK.
5. Un projet fait avec le firmware de David (machines 8 à 11) rouvert avec Model-TG + VA.
6. Avec les autres ajouts de David cochés (générateur de trigs §2, LFO 2 à 4 §3) : les machines VA jouent pareil,
   et un LFO réglé sur un de leurs potards le fait bouger.
7. CONFIG › UPGRADE par USB toujours possible (le crochet de démarrage ne change rien au chargeur).

### 4.11 Questions ouvertes

- L'accord et le crédit de David (§4.5).
- Corriger le repli de hauteur au-delà de la note 107 (§4.9) ?
- Versions combinées avec MACRO ou les moteurs du Syntakt ?
- Ordre des tweaks (27, 36) à confirmer.
