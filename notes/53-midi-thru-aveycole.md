# 53 — THRU qui envoie aussi le MIDI du Cycles (mods d'AveyCole)

Demande d'AveyCole, dans son fork ([AveyCole/Modded-Cycles](https://github.com/AveyCole/Modded-Cycles), commit `ba5f8bb`,
sa note `notes/50-midi-out-thru.md`) : que le Model:Cycles relaie le MIDI reçu **et** envoie son propre MIDI, pour rester au
milieu d'une chaîne MIDI. AveyCole en a tiré deux mods, testés sur son Model:Cycles le 10/10/2026. Maxime a demandé le
10/10/2026 de les intégrer au flasher, avec les preuves en émulation, sans test sur sa machine : « pas besoin de tester sur ma
machine la personne l'a fait ». Tweaks `50-midi-both.json` et `51-midi-live-both.json`, générés par `tools/gen_midi_thru.py`
(code dans `tools/machines/midi_thru/`), preuve `tools/emu/test_midi_thru.py`. Adresses : VA de l'OS 1.13.

## En bref

| Réglage OUT/THRU | OS d'origine | `midi-both` | `midi-live-both` |
|---|---|---|---|
| OUT | envoie le MIDI du Cycles, ne relaie rien | idem | idem |
| THR | relaie le MIDI reçu, jette le MIDI du Cycles | relaie **et** envoie | relaie seulement ; FUNC + appui sur LEVEL/DATA passe à « relaie et envoie », et inversement |

- Le menu ne change pas : l'écran affiche OUT ou THR, comme à l'origine.
- `midi-both` remplace trois appels par `moveq #0,d0` ; aucune place libre.
- `midi-live-both` utilise une valeur 2 du réglage, que l'OS lit déjà comme THR partout. 132 o de code dans un masque de
  sprite 34×34 libéré (`0x40192ba4`), au lieu de `0x40167c50` dans le fork (un des masques 35×35 restés libres dans le groupe du filtre par piste, PR #55).
- Les deux s'excluent (mêmes trois portes) et vont avec tous les autres mods.

## 1. Le réglage OUT/THRU dans l'OS

**`[FAIT]`** Le réglage est un octet des réglages globaux, lu et écrit par deux petites fonctions :

| VA | Rôle |
|---|---|
| `0x404e9b10` | bloc des réglages globaux : marque `COKI` (+0), somme de contrôle (+4) calculée par `0x40094e24` sur `0x4b` o à partir de `0x404e9b18` |
| `0x404e9b50` | l'octet OUT/THRU : 0 OUT, 1 THR |
| `0x40044df8` | lecture : `mvs.b 0x404e9b50,d0 ; rts`, **la valeur brute, étendue en signe** |
| `0x40044dc2` | écriture : ramène l'argument à 0 ou 1 (`tst.l ; sne ; neg.l`), puis, s'il diffère de l'octet, le copie par `0x40044b88` |
| `0x40044b88` | copie générique `(destination, source, longueur)` dans le bloc : efface la marque, copie, puis saute à `0x40044b4e`, qui recalcule la somme de contrôle (CRC-32 `0x40094e24`) et remet la marque `COKI` |
| `0x400452fc` | valeurs par défaut des réglages : écrit 0 (OUT) par l'écriture `0x40044dc2` (appel en `0x40045330`) |

La note du fork (§5.1) dit que la lecture `0x40044df8` rend un booléen ; c'est faux, elle rend l'octet tel quel. Seules
l'écriture `0x40044dc2` et la touche de la ligne (ci-dessous) le ramènent à 0 ou 1. Le reste de son analyse tient.

**`[FAIT]`** La lecture a six appelants, et aucune autre instruction ne désigne `0x404e9b50` (recherche de la constante
dans tout le MAIN OS : seulement la lecture et l'écriture). Les six testent zéro ou non zéro :

| Appel | Fonction | Ce qu'elle fait du réglage |
|---|---|---|
| `0x400012d2` | `0x400012cc` (octet reçu sur le MIDI IN) | non zéro : renvoie l'octet sur le MIDI OUT (`0x40001232`), puis passe au gestionnaire suivant (`*0x422fee70`) dans tous les cas : **le relais** |
| `0x4000154a` | `0x40001544` → `0x400012f4` | non zéro : `bne` vers `rts`, rien n'est envoyé |
| `0x4000156a` | `0x40001564` → `0x40001232` (un octet : horloge, temps réel) | idem |
| `0x40001590` | `0x40001584` → `0x40001100` (un message : notes, paramètres) | idem |
| `0x4003560a` | touche de la ligne OUT/THRU (pointeur rangé en `0x40035f60`) | `seq d0 ; mvs.b ; neg.l` : 0 → 1, non zéro → 0, puis `jmp 0x40044dc2` |
| `0x40035fd8` | affichage de la ligne | non zéro : « THR » (`0x40127281`), zéro : « OUT » (`0x40127bad`) |

Les trois portes (`0x4000154a`, `0x4000156a`, `0x40001590`) sont donc ce qui fait taire le Cycles en THR. Une valeur 2 dans
l'octet se lit comme THR partout : écran THR, relais actif, portes fermées, et un appui la ramène à 0.

## 2. `midi-both` : THR envoie toujours

Les trois portes reçoivent `moveq #0,d0 ; nop ; nop` (`70004e714e71`) à la place de `jsr 0x40044df8` (6 o chacune). Le
`tst.l d0 ; bne` qui suit voit zéro et laisse passer le message, quel que soit le réglage. Le relais, la touche et l'écran
ne changent pas. Trois écritures, identiques à celles du fork, aucune place libre.

## 3. `midi-live-both` : FUNC + appui pour choisir

### 3.1 Le geste

Sur la ligne OUT/THRU qui affiche THR, **FUNC tenu + appui sur le potard LEVEL/DATA** alterne la valeur 1 (THR d'origine,
relais seul) et la valeur 2 (relais et envoi). L'écran reste sur THR. Sans FUNC, l'appui fait ce qu'il faisait (THR → OUT,
y compris depuis 2) ; en OUT, FUNC + appui fait comme un appui seul (OUT → THR, valeur 1). Le geste vient d'AveyCole (§6
de sa note) : l'appui seul appelle déjà la touche de la ligne, il suffit d'y regarder FUNC.

### 3.2 Le code (`tools/machines/midi_thru/midi_thru.S`)

- **Accroche de la touche** : les 24 o de `0x4003560a` (`jsr 0x40044df8` … `jmp 0x40044dc2`) deviennent `jmp midi_key` et
  neuf `nop`. Aucune constante de l'OS ne vise ce bourrage (`0x40035610`..`0x40035621`, vérifié par la preuve).
- **`midi_key`** : `0x4007faf4(1)` dit si FUNC est tenu. Elle prend un **code logique** de touche : 1 est FUNC (table
  `0x4010ae5c[1]` = 10, bit 2 de l'octet +1 du tableau `0x40f95744`, [note 33](33-effacer-un-trig.md)). Le premier essai du
  fork lui passait 10 et ne voyait jamais FUNC (sa note §6.1). Sans FUNC, ou en OUT : `stock`, qui refait exactement les
  instructions déplacées (`tst.l ; seq ; mvs.b ; neg.l`, `move.l d0,4(sp)`) et saute à l'écriture `0x40044dc2` avec la même
  pile qu'à l'origine. Avec FUNC en THR : 2 si l'octet vaut 1, sinon 1, écrit par la copie de l'OS
  `0x40044b88(0x404e9b50, &octet, 1)`, qui recalcule la somme de contrôle du bloc. L'écriture `0x40044dc2` ne sert pas ici,
  puisqu'elle ramènerait 2 à 1.
- **`midi_gate`**, appelée à la place de `0x40044df8` par les trois portes (`jsr midi_gate`, 6 o pour 6 o) : rend 1 si
  l'octet vaut 1, sinon 0. La porte ne bloque donc plus qu'en THR seul ; OUT et la valeur 2 envoient.
- Seul `d0` change (comme la lecture d'origine), la pile est rendue telle quelle ; `midi_key` garde le contrat de la touche
  d'origine (adresse de retour, puis l'argument de la ligne, qu'elle ignore comme l'OS).

Le code fait 132 o, `midi_gate` à +`0x70`. Il ne contient aucune adresse de lui-même (branches relatives, adresses absolues
de l'OS seulement) : lié en `0x40167c50` ou en `0x40192ba4`, ce sont les mêmes octets. Seules les cibles des quatre
accroches changent par rapport au fork (`jmp 0x40192ba4`, `jsr 0x40192c14`).

## 4. Place utilisée

Le masque de sprite 34×34 `0x40192ba4` (272 o), que désigne la seule constante `0x400ac276` (constructeur `0x400ac274`),
est identique au masque `0x4016bfc8`, gardé intact ; `sprites.redirect_write` fait pointer la constante sur ce dernier et
libère le premier (groupe 34×34 de `sprites.GROUPS`, [note 52](52-registre-place-libre.md) ; `REGISTRY.md` le marque pris). 132 o occupés, 140 libres derrière. Le fork prenait le masque 35×35
`0x40167c50`, un des 4 masques que le filtre par piste (PR #55) laisse libres dans ce groupe, où il en prend 15 ; on les
lui laisse pour la suite de ce mod et on prend un groupe où rien d'autre n'est pris.

## 5. Conflits

- `midi-both` et `midi-live-both` écrivent les mêmes trois portes, différemment : `conflicts` dans les deux sens, `clash`
  sur les cartes du flasher.
- Aucun autre tweak n'écrit ces octets ni ce masque : `tools/check_overlaps.py` passe, sur `main` et avec les branches
  ouvertes ([note 49](49-verification-mod-par-mod.md)).

## 6. Preuve en émulation

`tools/emu/test_midi_thru.py` fait tourner, d'origine et modifiés, les vraies fonctions de l'OS : les trois portes (avec la
vraie émission UART et la vraie file DMA), le relais d'un octet reçu (jusqu'au gestionnaire suivant), l'affichage de la
ligne, et la touche sans et avec FUNC (le bitmap des touches tenues), pour chaque valeur 0, 1, 2 du réglage. Après chaque
appui : marque et somme de contrôle du bloc valides, pile et registres rendus, aucun accès hors mémoire. Il construit aussi
le build du fork (code en `0x40167c50`) et vérifie que les résultats sont les mêmes, puis que le décompresseur du bootstrap
relit l'OS modifié à l'identique.

| | porte octet (`0x40001544`) | porte horloge (`0x40001564`) | porte message (`0x40001584`) | relais (0x3c reçu) | écran | appui | FUNC + appui |
|---|---|---|---|---|---|---|---|
| origine, 0 / 1 / 2 | `fa` / rien / rien | `f8` / rien / rien | `90 3c 64` / rien / rien | rien / `3c` / `3c` | OUT / THR / THR | 1 / 0 / 0 | 1 / 0 / 0 |
| `midi-both`, 0 / 1 / 2 | `fa` / `fa` / `fa` | `f8` / `f8` / `f8` | les trois envoient | rien / `3c` / `3c` | OUT / THR / THR | 1 / 0 / 0 | 1 / 0 / 0 |
| `midi-live-both`, 0 / 1 / 2 | `fa` / rien / `fa` | `f8` / rien / `f8` | envoi / rien / envoi | rien / `3c` / `3c` | OUT / THR / THR | 1 / 0 / 0 | 1 / **2** / **1** |

```sh
python3 tools/gen_midi_thru.py --cycles model-cycles_OS1.13.syx --check
python3 tools/emu/test_midi_thru.py --cycles model-cycles_OS1.13.syx \
    [--with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,trig-hold,arp,tempo-max --syntakt Syntakt_OS1.42.syx]
```

**`[FAIT en émulation]`** Tout passe, seul et avec `6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,trig-hold,arp,
tempo-max,level-pan-values,trigless-dim`, avec `macro` et avec `model-tg-st,sample-preview-st,boot-anim,multiline-browser`. Le flasher construit les deux cartes avec
toutes les autres (`REF_MODS`, échantillon `REF_MAINOS`, `tools/webflash_smoke.sh`).

## 7. Limite : deux sources sur une seule sortie, octet par octet

Trouvé à la relecture (11/10/2026), d'après le code de l'OS ; c'est une limite de la conception du fork, pas un défaut de
son code, et le guide la dit aux utilisateurs.

- **`[FAIT]`** Le relais passe **octet par octet** : l'interruption de réception `0x40001094` appelle le gestionnaire
  installé (`*0x4049dce0` = `0x400012cc`, installé par `0x4000152c`) pour chaque octet reçu (`0x400010d4`..`0x400010e4`), qui le
  renvoie aussitôt par l'envoi d'un octet `0x40001232`. Rien ne regroupe les messages ni ne suit le « running status ».
- **`[FAIT]`** `0x40001232` écrit l'octet dans l'UART (`0xec07400c`) si la sortie est libre ; sinon (`0x4049dca0` non nul,
  un message part par le DMA) il le range dans l'anneau d'octets `*0x4049dcac`, coupe les requêtes du canal DMA 37
  (`0xfc044019`) et laisse l'interruption d'émission l'envoyer. C'est fait pour glisser un octet temps réel (`f8`, `fa`…)
  au milieu d'un message, ce que la norme MIDI permet.
- **`[FAIT]`** Les messages du Cycles partent entiers par `0x40001584` → `0x40001100` (anneau du DMA), chacun avec son octet
  de statut (par exemple la note `0x40082772` : `90 | canal`, 3 octets). Dans l'OS d'origine, ces deux flux ne se croisent
  jamais : en THR les trois portes taisent le Cycles, en OUT rien n'est relayé.
- **Conséquence** : avec `midi-both` ou la valeur 2, un octet relayé peut tomber au milieu d'un message du Cycles, et un
  message du Cycles au milieu d'un message relayé. Exemple reproduit en émulation (script ponctuel, sur l'image
  `midi-live-both`, valeur 2) : `90` reçu et relayé, puis le Cycles envoie `b0 07 7f`, puis `3c 64` reçus : l'appareil
  suivant lit `90 | b0 07 7f | 3c 64`, la note reçue est perdue et `3c 64` devient un CC 60 sur le canal du Cycles. Sans
  même de coïncidence, un appareil qui omet les statuts répétés (« running status », courant pour les notes) voit ses
  octets suivants rattachés au dernier statut du Cycles, d'où des notes fausses ou bloquées. Une SysEx relayée est coupée
  par tout statut du Cycles.
- L'horloge et le transport (`f8`..`ff`, temps réel) se mêlent sans dommage. L'usage sûr : un seul des deux côtés joue des
  notes ou des contrôles (par exemple une horloge maître en amont, le Cycles qui joue l'aval, ou l'inverse).
- **`[À FAIRE]`** si le besoin vient : un relais qui fusionne par messages (temps réel tout de suite ; le reste mis de côté
  jusqu'au message complet, statut remis devant le running status, envoyé entier par `0x40001100`), avec sa preuve. Ce
  serait du code nouveau dans l'interruption de réception, au-delà de ce qu'a testé AveyCole.

## 8. Ce qui reste à vérifier

- **`[HYP]`** La valeur 2 survit à l'extinction : le bloc `0x404e9b10` est enregistré entier (inscrit en `0x400ddef2`) et le
  chargement (`0x40044bc2`, contrôle `0x40044af4`) ne vérifie que la marque, la taille et la somme de contrôle. Pas vérifié
  sur la machine (le fork ne l'a pas vérifié non plus). Les valeurs par défaut (`0x400452fc`) remettent OUT.
- **`[FAIT]`** Avec la valeur 2 enregistrée, l'OS officiel ou `midi-both` lisent THR (§1) : rien ne casse au retour.
- **`[HYP]`** Horloge en double : si le Cycles suit l'horloge reçue et envoie aussi la sienne, le relais transmet les `f8`
  reçus et le Cycles envoie les siens. Le guide conseille de couper l'envoi d'horloge dans ce cas.
- **`[HYP]`** FUNC + rotation du potard sur cette ligne n'a pas été étudié ; le geste testé est l'appui.

## 9. Testé sur la machine (10/10/2026)

Par AveyCole, sur son Model:Cycles, avec le code du fork :

- `midi-both` : « I tested this on my Model Cycles and it functions as intended! »
- `midi-live-both`, build test `bth-func-05` (code en `0x40167c50`) : « tested and working!!! », avec FUNC tenu + appui sur
  LEVEL/DATA quand THR est affiché.

Maxime a jugé ce test suffisant (« pas besoin de tester sur ma machine la personne l'a fait », 10/10/2026). Ici, `midi-both`
est repris octet pour octet, et `midi-live-both` ne diffère que par l'adresse du code, prouvé identique en émulation (§6).
Les deux cartes sont donc marquées testées, par AveyCole.

## 10. Ce qui n'est pas repris du fork

- Le sélecteur à trois états OUT/THR/BTH (`gen_midi_bth_three_state.py`, sa note §5) : le build test 04 a gelé la machine en
  entrant dans la ligne OUT/THRU, cause inconnue.
- La page `docs/flasher-test/` et les copies du flasher du fork : les deux cartes passent par notre flasher.
- La licence : le fork n'en indique pas. **`[À FAIRE]`** la confirmer avec AveyCole avant la fusion.
