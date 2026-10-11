# 46 — Écouter les samples dans le navigateur, avec le Sampler de Model-TG : le tweak `sample-preview`

Demande de la communauté : fil Discord
[« Sample preview with Model-TG sampler »](https://discord.com/channels/1556268411947057252/1556790452106174504),
remonté par le rapport hebdomadaire du 06/10/2026 (6 votes) : « Samples can be easily previewed in sample menu, just
like engine presets ». Tweaks `33-sample-preview.json` (sur `model-tg`) et `33-sample-preview-st.json` (sur
`model-tg-st`, mêmes écritures), générés par `tools/gen_sample_preview.py` depuis `tools/machines/sample_preview/` (`sample_preview.S`,
`sample_preview.ld`), preuve en émulation `tools/emu/test_sample_preview.py`. Adresses : VA de l'OS 1.13 ; celles de
Model-TG sont celles de sa v1.1.0 telle que la construit `tools/gen_model_tg.py` (identiques dans ses deux versions).

**Statut : testé sur la machine (07/10/2026), voir §12.**

## Réponse courte

- **Oui, comme les presets.** L'OS d'origine ne joue rien quand le curseur bouge : il *désigne* le preset sous le
  curseur, et la note suivante jouée sur le pad de la piste active (ou ses touches en mode clavier) le joue à la place
  du son de la piste, pour cette note seulement. Le tweak fait pareil pour un fichier de sample, sur une piste Sampler.
- **Deux maillons manquaient** `[FAIT]` : le navigateur lit chaque fichier comme un preset, et un sample échoue au
  contrôle de taille, donc rien n'est désigné (§3.1) ; et même désigné, le moteur audio efface le pointeur du son de la
  note avant que le Sampler de Model-TG le lise pour trouver le sample, qui joue alors celui de la piste (§3.2).
- **Trois accroches** (§5) : `pv_parse` fait désigner « le son de la piste, nommé d'après le sample » ; `pv_note`
  charge le sample au premier appui s'il n'est pas en mémoire, sans chasser un sample du projet (une réserve au §10,
  point 12), et ne joue rien s'il ne se charge pas ; `pv_copy` garde une copie du son écouté là où le Sampler la
  cherche.
- **Un tweak à part, qui exige Model-TG** (§6) : les firmwares Model-TG déjà construits et testés ne changent pas d'un
  octet. 1 236 o dans quatre masques de sprites 47×47 libérés, partagés avec Chord Keys, qui exclut Model-TG ;
  11 écritures (§7).

## 1. La demande

Avec Model-TG, on charge un sample sur une piste Sampler en l'ouvrant dans le navigateur de presets (FUNC + MACHINES,
« Sample loaded to Sampler », guide §9). Pour savoir ce que contient un fichier, il fallait donc le charger : cela
change le sample de la piste et le nom enregistré dans le son (`preset_fail_hook` → `name_store`, notes/31). Les presets,
eux, s'écoutent avant d'être choisis. La demande : la même chose pour les samples.

## 2. L'écoute des presets dans l'OS d'origine `[FAIT]`

Lu dans le code et rejoué en émulation (rapports d'enquête, puis `tools/emu/test_sample_preview.py`).

| Où | Quoi |
|---|---|
| `0x400a63ac(navigateur, index)` | écoute de l'entrée sous le curseur. `vt[32]` du dossier courant (`+632`) vérifie l'entrée (dans les bornes, un fichier). Mode fichier (`vt[152]` = `0x400a3308`, `+640 == +632`) : `getEntry` `0x4007cdd4` remplit un handle de 16 o à `fp-16` (`+0` numéro d'entrée, −1 = invalide ; `+4` **empreinte**, champ +12 de la fiche d'inode ; `+8` **taille** ; `+12` un 4ᵉ mot comparé à l'ouverture), `0x4007e548` le valide, `0x400a3052` (a0 = `&fp-24`) lit le preset, `0x400f47e8` le range en `fp-32/fp-28`. Mode pool : `(kit+628)->vt[76](index)` rend une copie du son de la case |
| `0x400a647c` | si un son a été lu : `0x40058504` donne l'un des deux tampons de 100 o (`0x40a78c90` / `0x40a78cf4`, en alternance, sélecteur `0x40a78c8c`, interruptions masquées), `0x4008f1f0` y copie les 100 o (le `pea 0x64` est cette longueur, pas une vélocité), `0x40081bd6(tampon)` écrit `*0x40fb5a04` : le son est **désigné** |
| `0x400a64be` (`vt[76]` du PresetManager, slot `0x40118438`) | curseur déplacé (`vt[24]` molette, `vt[28]` setCursor) : `0x4004067c`, puis `0x400a63ac` ; s'il échoue, `0x40081bd6(0)` : plus rien de désigné. Un seul appel par événement de molette : un saut × 8 ou × 10 n'écoute que l'entrée d'arrivée |
| `0x400a6d12` (dans `0x400a6c20`) | ouverture du navigateur : `0x400a63ac` sur l'entrée sous le curseur, résultat ignoré |
| `0x400a40e4` | fermeture du navigateur : `0x40081bd6(0)` |
| `0x4008171e(piste, note, vélocité, source, sans envoi, −1, vitesse)` | note jouée en direct : pads (`0x4001d08e`) et touches de pas en mode clavier (`0x40019edc`), source `0x40`. L'événement porte `*0x40fb5a04` en +52 (`0x40081860`) si la piste est `*0x40a700c4` (`0x40081760`) et si `0x400813e2(source)` (sources `0x40`, `0x80`, `0x10`, `0x04`) ; si « sans envoi » (5ᵉ argument, `20(sp)`) est non nul, **aucun événement n'est envoyé** (`0x4008180e` saute `0x4005894a`) |
| `0x4005894a` | copie l'événement +52 en +48 du message pour l'interruption audio (`0x40058982`) |
| boucle des événements `0x40058d46..0x400591e4` (`a4` = `0x800015a0`, `a2` = message, `d2` = piste) | son de la note : message +48 (écoute), sinon +44 (lock du séquenceur), sinon le son du kit (`*0x800017e4 + 28 + 100 t`). S'il diffère de `CUR_SNDS[t]` (`0x800015a0 + (147 + t) × 4` = `0x800017ec + 4 t`, comparaison `0x400590d6`), `0x40058a0a` l'y écrit et copie ses **66 o de paramètres** (+20..+85, machine en +38) dans la voix ; **`0x4005910e..0x4005911f` : après une note d'écoute, `CUR_SNDS[t] = 0`**, pour que la note suivante recopie le son de la piste ; `0x40059160` lit ensuite `CUR_SNDS[t]` + 96, donc l'adresse `0x60` |

- Rien ne joue tout seul au défilement ; le son désigné ne sert qu'aux notes jouées en direct sur la piste active.
  Vélocité et durée sont celles de la note jouée (tenue tant que le pad est enfoncé).
- Les trigs du séquenceur ne portent jamais de son d'écoute : le pool des messages efface +48 (`0x40091ede`) et le
  séquenceur ne remplit que +44 (`0x40054c0a`).
- `[HYP]` Tant que le navigateur est ouvert, un pad ne sélectionne pas sa piste (`dynamic_cast` vers le PresetManager
  en `0x4001d2ac`, branche pas entièrement suivie) : chaque pad joue sa propre piste, seul celui de la piste active
  porte l'écoute (vérifié en émulation pour l'événement : autre piste → +52 = 0).
- `*0x40a700c4` n'est jamais écrit à une adresse absolue ; c'est la piste active vue par le code des notes `[HYP]`.

## 3. Pourquoi un fichier de sample ne fait rien entendre

### 3.1 Côté navigateur `[FAIT, émulation]`

`0x400a3052` → `0x400a2a28` ouvre le fichier (`0x4007e4f4`, qui allume le bit de l'inode dans `0x40fe8e10`), puis
exige **48 ≤ taille ≤ 160 o** (`0x400a2a5c..0x400a2a68`, `taille − 48 ≤ 112` non signé). Un sample échoue là, avant
toute lecture : `0x400a3052` rend {0, 0}, `0x400a63ac` rend faux, `0x400a64be` ne désigne plus rien, et le pad joue le son
de la piste (avec Model-TG : le sample de la piste). Testé en émulation pour 2 000 000, 47 et 161 o.

Effet de bord de l'OS d'origine : cette sortie saute la fermeture (`0x4007bc1c`), le bit « ouvert » de l'inode reste
allumé. `0x4007eda6` le teste et `0x4007a5d8` rend −1 quand il l'est (appelants `0x4007a6a8`, `0x4007a8d2`,
`0x4007aa10` ; `0x4007a8a4` est appelé en boucle sur les entrées choisies du navigateur en `0x4003f838`, `[HYP]` la
suppression). Chaque fichier de sample sur lequel le curseur s'arrête (ou qu'on ouvre) le laisse allumé, jusqu'au
redémarrage `[HYP sur la conséquence]`.

### 3.2 Côté audio `[FAIT, émulation]`

Même si l'OS désignait un son du Sampler nommé « SMP… » : `0x40058a0a` ne copie dans la voix que les 66 o de
paramètres, **pas le nom** (+4..+19). Model-TG a donc besoin du pointeur `CUR_SNDS[t]` pour lire le nom du son de la note,
et l'OS l'efface en `0x4005911c`, dans la boucle des événements, avant le rendu des voix du même bloc (`0x40059382` →
`0x4005979e` → `0x400a7d4a`, appelé en `0x4005981e` après la boucle `[FAIT]`). `sp_lock` y lit 0, prend le chemin « son
de la piste » et joue le sample de la piste avec les paramètres du son écouté. Rejoué en émulation sur l'image Model-TG.

## 4. Ce que Model-TG fournit `[FAIT, source v1.1.0]`

`vendor/Model-TG/src/model_tg.s` ; adresses des symboles exportés dans les `symbols` de `30-model-tg.json` et
`30-model-tg-st.json` (`PV_SYMBOLS` de `tools/gen_model_tg.py` : des métadonnées, les empreintes ne changent pas).

| Symbole | Adresse | Rôle |
|---|---|---|
| `sp_lock` | `0x401ad958` | à chaque front de trig d'une voix Sampler (`sampler_pre`, après l'arrivée d'une case en attente) : si `kit_ok` = 1, lit `CUR_SNDS[t]` ; un pointeur dans `0x40000000..0x48000000`, autre que le son du kit (`*0x40a78888 + 28 + 100 t`), dont `tok_of` donne une empreinte présente dans `slot_hash` → `track_slot[t]` = cette case, `track_lock[t]` = 1 : **cette note joue ce sample** ; absente → `pl_dirty` = 1 et sample de la piste ; sinon (`spl_own`, `0x401ad9e8`) retour au sample de la piste si la note d'avant était verrouillée |
| `tok_of` | `0x401b2d96` | empreinte nommée par un son : machine (+38) = 6, « SMP » en +4..+6, puis 8 chiffres hexadécimaux **majuscules** en +7..+14 ; sinon 0. Garde d1-d7, détruit a0 |
| `sound_obj` | `0x401b32a2` | son vivant de la piste d0 (objet de piste du projet, `vtable[40]`), ou 0. Garde d2-d5/a2-a3 |
| `ensure_loaded` | `0x401b27d0` | rend la case du sample d'empreinte d0, en le chargeant s'il n'est pas en mémoire (lecture synchrone de la carte : `load_at` → `readBlocks` `0x4008b24a`, verrou `0x4233409c`), ou −1. Refuse pendant un enregistrement, une prise en attente ou une sauvegarde (`rs_state`, `rs_pending`, `rs_sv_state`) ; contrôle l'en-tête (+8 = 48 000, +4 ≠ 0). Garde d2-d4/a2. Non réentrant (`want_hash`, `el_slot`, `TBL_BUF`…) |
| `pd_mode` | `0x401befc8` | 1 = le mode du préchargement : `find_gap` laisse les 16 Mo du haut libres (`PL_RESERVE`, pour les prises) et `evict_one` ne chasse que les samples de **niveau 0**, que rien dans le projet n'utilise (« pd_mode 1 evicts only the unused ») ; `slot_level` ne compte les autres patterns (niveau 1) que par `proj_has`, qui rend 0 si `kit_ok` ≠ 1 (§10, point 12) |
| `ld_busy` | `0x401beff4` | chargeur occupé : `led_hook` (horloge des LED, niveau d'interruption 0, une fois par bloc audio) le prend autour de `name_probe`, `load_pending`, `pl_step`… |
| `slot_hash` | `0x401be4a0` | empreintes des 64 cases d'échantillons en mémoire, partagées entre pistes |
| `pad_load_hook` | `0x401b3210` | l'accroche de Model-TG en `0x4008171e` (`jmp`) : rejoue `link.w %fp,#-104 ; moveq #127,%d0` et saute en `0x40081724`. Son commentaire : « Empty, permanently » — un chargement à cet endroit causait la pause au premier appui |

- **Le nom des sample locks** : `pool_store_hook` copie le son de la piste dans `psh_snd` et écrit à +4 « SMP » + les 8
  chiffres hexadécimaux de l'empreinte (`psh_h`). C'est ce nom que `sp_lock` reconnaît. L'empreinte est celle du handle
  du navigateur (+4, toujours impaire : `getEntry` exige `fiche+12 & 1`, `0x4007de0a`).
- **Retour au sample de la piste** : pendant une note verrouillée, `slot_hash[track_slot] ≠ track_hash`, donc
  `load_pending` remet la case de la piste en attente, qui arrive dès que la voix est au repos (`sp_pidle`) : le sample
  de la piste revient quand la note se tait, comme après un sample lock.
- **Contextes** : `tick_hook` (KeyboardView, tâche de l'interface) appelle `load_pending` et `pl_step` sans `ld_busy` ;
  `preset_fail_hook` et `pool_store_hook` appellent `ensure_loaded` depuis le navigateur, sans `ld_busy` non plus.

## 5. La conception

### 5.1 Trois accroches

| Adresse | Avant | Après | Contexte |
|---|---|---|---|
| `0x400a6426` (dans `0x400a63ac`) | `jsr 0x400a3052` (6 o) | `jsr pv_parse` | navigateur, tâche de l'interface |
| `0x4008171e` | `jmp pad_load_hook`, écrit par Model-TG (6 o) | `jmp pv_note` | note jouée, tâche de l'interface |
| `0x4005910e` | `tst.l 48(a2) ; beq.s 0x40059120 ; move.l d2,d0 ; addi.l #147,d0 ; clr.l (a4,d0.l*4)` (18 o, dont 8 réécrits) | `jsr pv_copy ; bra.s 0x40059120` | boucle des événements de l'interruption audio |

Aucun branchement ni pointeur ne vise l'intérieur des octets remplacés (balayage des deux images) ; les seules cibles
voisines sont `0x4005910e` lui-même, `0x40059120` (la fin) et, dans `0x400a63ac`, `0x400a6444`, `0x400a647c`, `0x400a64a8`,
`0x400a64aa`, `0x400a64b2` `[FAIT]`. Les 10 o qui suivent le `bra.s` en `0x40059116` restent en place, sans plus rien
pour y mener.

### 5.2 `pv_parse` : faire désigner le sample

Entrée comme `0x400a3052` : a0 = `&résultat` (`fp-24`), `4(sp)` = `&handle`. Sortie comme lui : le résultat rempli,
d0 = a0 = `&résultat`, d2-d7/a2-a6 gardés. Dès l'entrée, `pv_fail` = 0 : chaque écoute du navigateur de fichiers,
preset ou pas, sur n'importe quelle piste, permet de retenter un chargement raté (§5.3).

1. Piste active `*0x40a700c4`, son `sound_obj(piste)`. Pas d'objet son, ou machine (+38) ≠ 6 : **l'appel d'origine,
   tel quel** (presets des autres machines inchangés, effet de bord du §3.1 compris).
2. Piste Sampler, taille dans 48..160 o : l'appel d'origine ; s'il rend un son, c'est un preset, écouté comme avant.
3. Sinon (taille hors de 48..160 o, ou preset illisible) : moins de 66 o (en-tête de 64 o plus un échantillon) ou
   empreinte nulle → {0, 0}, rien n'est désigné. Autrement, `pv_src` (100 o) = copie du son de la piste, nommée à +4
   « SMP » + 8 chiffres hexadécimaux majuscules de l'empreinte (comme `psh_h`), résultat {`pv_src`, 0}. Un compteur
   nul est sans danger : `0x400cf23c` ne fait rien sur un compteur nul (`0x400cf244`).
4. L'OS continue tout seul : il copie `pv_src` dans son tampon d'écoute et le désigne (§2). Hors de 48..160 o, le
   fichier n'est **pas ouvert** : plus de bit « ouvert » laissé allumé sur une piste Sampler.

Le son écouté garde tous les réglages de la piste (mode de lecture, Start, End, filtre…) ; seul le nom change. Le
hook couvre les deux appelants de `0x400a63ac` : curseur déplacé et ouverture du navigateur. Il ne touche pas
l'ouverture d'un fichier (`0x400a6602`), donc ni `sel_hash` ni le chargement de Model-TG.

### 5.3 `pv_note` : charger le sample au premier appui

À l'entrée de `0x4008171e`, avant tout le reste. Il ne fait quelque chose que si **toutes** ces conditions tiennent,
les mêmes que celles de l'OS pour emporter le son désigné, en plus strict :

- un son est désigné (`*0x40fb5a04` ≠ 0) ;
- source `0x40` (pads et touches : tâche de l'interface, d'où Model-TG appelle déjà son chargeur depuis le
  navigateur) ; les sources `0x80`, `0x10`, `0x04` passent sans chargement ;
- « sans envoi » = 0 ; piste = `*0x40a700c4` ;
- `tok_of(son désigné)` ≠ 0 et cette empreinte n'est pas dans `slot_hash[0..63]`.

Alors :

| Cas | Ce qui se passe |
|---|---|
| son désigné = `pv_failp` **et** empreinte = `pv_fail` (déjà ratée sur ce son désigné) | note muette, sans essai |
| niveau d'interruption ≠ 0 | note muette, sans essai (le chargeur attend la carte : jamais hors du niveau 0, comme `led_hook`) |
| `ld_busy` déjà pris | note muette, sans essai ; l'appui suivant réessaie |
| sinon | `ld_busy` pris au niveau 7 (test puis écriture sans interruption possible), `pd_mode` = 1, `ensure_loaded(empreinte)`, puis `pd_mode` et `ld_busy` remis à 0 |
| … chargé (case ≥ 0) | **la note part et joue le sample** (le chargement finit avant l'envoi de la note) |
| … raté (−1) | `pv_fail` = empreinte, `pv_failp` = son désigné (`*0x40fb5a04` à ce moment), note muette |

« Muette » = 1 dans « sans envoi » (`20(sp)`) : l'OS n'envoie pas la note au moteur audio (`0x4008180e`), rien ne
joue. Puis, dans tous les cas, `link.w %fp,#-104 ; moveq #127,%d0 ; jmp 0x40081724`, comme `pad_load_hook` ; le
`note_on_hook` de Model-TG (`0x4008173c`, Scale Lock) passe ensuite comme avant. d2-d7/a2-a6 sont sauvés autour du
chargeur.

Choix :

- **Charger à l'appui, pas au défilement.** Au défilement, rien ne joue (comme les presets) ; charger à chaque pas de
  molette figerait l'interface sur chaque gros fichier traversé. L'enquête avait proposé un chargement différé dans
  `led_hook` après un temps de repos : il faut alors du code dans le bloc de Model-TG (§6), écarté.
- **Le silence plutôt que le sample de la piste** quand le chargement est impossible : entendre le sample de la piste
  en parcourant d'autres fichiers tromperait.
- **`pd_mode` 1** : jamais un sample du projet chassé (tant que `kit_ok` = 1, §10 point 12), 16 Mo gardés pour les
  prises, comme le préchargement.
- **`pv_fail` et `pv_failp`** : un essai raté (index de la carte parcouru pour rien, mémoire pleine) n'est pas refait à
  chaque appui sur le **même son désigné**. `pv_note` retient l'empreinte ratée (`pv_fail`) et le tampon désigné à ce
  moment (`pv_failp`) ; un appui suivant ne saute le chargement que si les deux correspondent. Toute nouvelle
  désignation, par le navigateur de fichiers, le Sound Pool ou un autre chemin, passe par l'autre tampon de 100 o de
  l'OS (`0x40058504` les alterne, §2) et donne donc un nouvel essai. Seule exception : deux désignations sans appui
  entre elles (deux pas de molette dans le pool, par exemple) ramènent le tampon de l'échec à la même adresse ; si
  aucune n'est passée par le navigateur de fichiers, l'appui reste muet sans essai. `pv_parse` remet `pv_fail` à zéro
  dès son entrée (§5.2) : toute écoute du navigateur de fichiers, preset ou pas, rouvre l'essai. Les deux mots sont à
  zéro dans l'image (§7), donc à chaque démarrage.
- **Jamais `rebuild_slots`, `refresh_tracks` ni `name_store`** : la piste, son nom et ses cases ne bougent pas.

### 5.4 `pv_copy` : que le Sampler trouve le son écouté

À la place de l'effacement de `0x4005910e` (registres : `a2` = message, `d2` = piste, `a4` = `0x800015a0` ; d0, d1,
a0 et a1 sont réécrits après `0x40059120` avant d'être lus `[FAIT]`) :

- pas de son d'écoute (+48 = 0) : rien, comme d'origine ;
- son d'écoute dont la machine (+38) est 6, piste < 6 : copie de ses 100 o dans `pv_b[t]` (table `pv_tab`) et
  `CUR_SNDS[t]` = `pv_b[t]` ;
- autre son d'écoute : l'effacement d'origine.

`sp_lock` trouve alors le nom « SMP… » dans la copie, la case dans `slot_hash` (chargée par `pv_note`) et verrouille la
case pour cette note. La copie n'est jamais le son d'une note (`a5`) : la note normale suivante diffère, l'OS recopie le
son de la piste comme après l'effacement d'origine, et `sp_lock` (`spl_own`) revient au sample de la piste. Les copies
sont sous `0x48000000`, sinon `sp_lock` les prendrait pour « pas de son » : les masques sont en `0x4018….`.

Coût dans l'interruption audio : `jsr`, une lecture, un test et `rts` par note ; 25 `move.l` de plus par note d'écoute
d'un son du Sampler. Mesuré en émulation sur une passe de la boucle des événements (§11) : +3 instructions pour une note
normale, +88 pour une note d'écoute d'un son du Sampler. Rien dans la boucle des voix, rien pour le régulateur de
charge.

### 5.5 Au passage : presets du Sampler et sons du Sound Pool

`pv_note` et `pv_copy` regardent le son désigné, d'où qu'il vienne. Un son du Sound Pool fait par un sample lock (mode
pool du navigateur, que l'OS écoute déjà), ou un preset du Sampler dont le son nomme un sample, fait maintenant
entendre son propre sample (chargé au besoin) au lieu de celui de la piste `[FAIT en émulation pour le chemin audio]`.
Seulement pour un son dont le nom est encore celui de Model-TG (« SMP » + 8 chiffres hexadécimaux), et le cas du pool
reste à jouer sur la machine (§12) : le site le présente au conditionnel, pour les presets du Sampler seulement, sans
parler du Sound Pool.

## 6. Pourquoi un tweak à part (option B)

**Option A, une retouche de la source de Model-TG** (`MC_PATCHES` de `tools/gen_model_tg.py`) : le bloc grossit, donc
`reserved_end` bouge `[FAIT]`. Il faudrait régénérer les 31 `31-syntakt-tg-*`, `32-macro-tg`, `91` et `92`, ce qui demande
`m68k-elf-gcc` 16.2 (avec GCC 13.3, `gen_syntakt_engines.py --all --tg --check` échoue `[FAIT]`) ; les 1 056 empreintes
Model-TG de `REF_MAINOS` changeraient, et l'étiquette « testé » de Model-TG + 5 moteurs (`HW_TESTED_TG`) serait remise en
cause.

**Option B, retenue** : un tweak séparé, ordre 33, appliqué après Model-TG (`requires`).

- Les builds de Model-TG ne changent pas : MAIN OS `aa0740d7…` (`model-tg`), `d5e73e10…`
  (`model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm`), les 9 503 empreintes d'avant (main avec MACRO) restent dans `REF_MAINOS` ; qui ne coche
  pas l'option garde exactement son firmware.
- Ses écritures ne peuvent pas atteindre le bloc de Model-TG : `apply_writes` (`tools/build.py`, et `applyWrites` de
  `builder.js`) ne travaille que sur l'image d'origine, le bloc est un `append` posé après `[FAIT]`. D'où une copie
  (`pv_copy`) plutôt qu'une retouche de `sp_lock`. Il peut en revanche appeler les fonctions de Model-TG, lire et écrire
  son état, et remplacer un de ses `jmp` posés dans l'OS (`0x4008171e`, dont l'`old` est l'écriture de Model-TG).
- Il dépend des adresses internes de Model-TG : le générateur les lit dans les `symbols` de `30-model-tg*.json` et
  vérifie le contrat dans la charge utile (début de `tok_of`, `sound_obj`, `ensure_loaded`, `pad_load_hook` ; `slot_hash`,
  `pd_mode`, `ld_busy` à zéro au départ ; `jmp pad_load_hook` en `0x4008171e`), et que `pd_mode` et `ld_busy` sont bien
  les variables du chargeur (`tg_uses` : `pl_step` pose `pd_mode` autour de son `jsr ensure_loaded`, `led_hook` prend
  `ld_busy` par deux `lea (d16,pc)`). Une mise à jour de Model-TG impose de le régénérer, comme les `syntakt-tg`.
- **Deux fichiers aux écritures identiques**, parce que `requires` veut dire « tous ceux-là » : `33-sample-preview`
  exige `model-tg`, `33-sample-preview-st` exige `model-tg-st`. Le code de Model-TG est aux mêmes adresses dans les deux ;
  seules 18 constantes dérivées de `REGION_END` diffèrent (56 octets isolés dans la charge utile), inutilisées ici
  `[FAIT]`.
- Flasher : une ligne « Écoute des samples (Model-TG) » dans la rubrique Écran et navigation (`cat: screen`, depuis le
  nouveau choix des mods de la release 1.28), `"requires": "model-tg"` (la cocher coche Model-TG, décocher Model-TG la
  décoche ; Détails : « Marche avec Model-TG seulement »), `with: {"syntakt": "33-sample-preview-st", "macro":
  "33-sample-preview-st"}` (les mêmes clés que Model-TG, vérifié par `check_requires`) ; `REF_MAINOS` passe de 9 503
  à 10 559 combinaisons (main avec MACRO : 9 503).

## 7. Le code et la place

Assembleur (`--check` ne dépend que des binutils), lié par `sample_preview.ld` dans quatre masques 47×47 de 376 o,
identiques au masque gardé `0x40172220` (`sprites.SHARED_47`), libérés en redirigeant la constante de leur
constructeur (`sprites.redirect_write`, même principe que [32 §11.3](32-arpegiateur.md)) :

| Masque | Constante | Contenu | Occupé |
|---|---|---|---|
| `0x40183118` | `0x400adf9e` | `pv_copy` (60 o), `pv_tab` (6 pointeurs), `pv_fail`, `pv_failp`, copies des pistes 1 et 2 | 292 / 376 o |
| `0x40185018` | `0x400adba8` | copies des pistes 3 à 5 | 300 / 376 o |
| `0x40185968` | `0x400ada00` | `pv_note` (232 o), copie de la piste 6 | 332 / 376 o |
| `0x40185c58` | `0x400ad9e0` | `pv_parse` (212 o), `pv_src` | 312 / 376 o |

**1 236 o sur 1 504** (292 + 300 + 332 + 312 ; 504 o de code, 732 o de données). Les données sont écrites dans
l'image : ces zones ne sont pas remises à zéro au démarrage. Les masques ne sont pas à `0xFF` : le contrôle des caves ne
les voit pas ; le générateur vérifie que chacun est une copie du masque partagé, et les `old`.

Combien de masques `[FAIT]` (balayage de l'image d'origine, 07/10/2026) : **22** blocs de 376 o sont identiques au
masque 47×47 gardé (un carré opaque de 47 colonnes), chacun désigné par une seule constante, de `0x400ac2b2` à
`0x400b133e`. On garde `0x40172220` : **21** sont libérables. `tools/sprites.py` et [32 §11.3](32-arpegiateur.md)
parlent de onze sprites 47×47 en tout (d'où « huit autres » après les deux de l'arpégiateur) : à corriger.

Choix des masques (07/10/2026) : la première version prenait `0x4018cd48`, `0x4018d1b8`, `0x4018d4a8` et `0x4018dba8`.
Les 21 masques sont tous pris ou réclamés, vérifié sur les fichiers de tweak des PR ouvertes :

| Qui | Masques |
|---|---|
| arpégiateur (`main`) | `0x40189930`, `0x4018a220` |
| Chord Keys (#50, commit `6db6dec` : 14 masques) | `0x4016b6f8`, `0x4016b9e8`, `0x40171f30`, `0x40172608`, `0x40179730`, `0x40182b38`, `0x40182e28`, `0x40183118`, `0x40185018`, `0x40185968`, `0x40185c58`, `0x4018cd48`, `0x4018d1b8`, `0x4018d4a8` |
| l'écoute des samples (ce tweak) | `0x40183118`, `0x40185018`, `0x40185968`, `0x40185c58`, partagés avec Chord Keys |
| affichage en chiffres et trigless trigs atténués de djd_oz (#53, commit `02cd68d`) | `0x4018f4b4`, `0x4018fc74` (`46-level-pan-values`), `0x4018dba8` (`47-trigless-dim`) ; `0x40192734` leur est gardé |
| navigateur multiligne (#52) | `0x401904b4` |

La PR #53 prenait d'abord `0x4018cd48`, `0x4018d1b8`, `0x4018d4a8`, que Chord Keys prend aussi ; elle est passée sur
`0x4018dba8`, `0x4018f4b4` et `0x4018fc74`, libérés par le déplacement de ce tweak. Le tweak occupe donc quatre des
masques 47×47 qu'utilise aussi Chord Keys : Chord Keys exclut Model-TG, que l'écoute des samples exige, les deux ne
peuvent jamais être cochés ensemble (`conflicts: ["chord-keys"]` le dit aux deux constructeurs). Cette répartition est
aussi tenue dans la mémoire du projet (« sprite-mask-allocation »). `tools/sprites.py` devra fusionner les listes de
ces PR.

## 8. Conflits

- **Exige Model-TG** (`model-tg` ou `model-tg-st`) : mêmes exclusions que lui (les trois tweaks de drumkilla, qu'il
  contient ; les moteurs du Syntakt hors version combinée ; SD VINTAGE).
- **Seul octet commun : `0x4008171e`**, où Model-TG écrit `jmp pad_load_hook` ; l'`old` du tweak est cette écriture, et
  `check_overlaps` du générateur n'accepte que ce recouvrement-là. Il écarte les tweaks qui ne vont jamais avec : ceux
  avec lesquels Model-TG ou ce tweak déclare un conflit, et ceux qui en déclarent un avec l'un des deux (Chord Keys,
  une fois fusionné). Aucun autre tweak du dépôt n'écrit dans les trois accroches ni dans les quatre masques `[FAIT]`.
  L'arpégiateur écrit en `0x40058e28`, ailleurs dans la même boucle des événements, et en `0x40081908` ; ils se
  combinent.
- **Chord Keys** (PR #50, `45-chord-keys`, commit `6db6dec`) : nos quatre masques parmi ses 14 (§7), et leurs quatre
  constantes de sprites ; il exclut `model-tg` et `model-tg-st`, et ce tweak déclare `conflicts: ["chord-keys"]`
  `[FAIT]`.
- **PR ouvertes, vérifiées le 07/10/2026 sur leurs fichiers de tweak** :
  - le navigateur multiligne (#52, `44-multiline-browser`) touche le navigateur en `0x400a547c..0x400a5776` et
    `0x400a69b4`, pas `0x400a63ac..0x400a64f8`. Il écrit aussi en `0x4003f622` (4 o, un `clr.l` à la place d'une
    écriture de registre), `0x4003f752` (4 o, l'adresse de la petite police) et `0x400406a8` (18 o, la règle de la
    première ligne visible). Ce dernier est **dans `0x4004067c`**, que `0x400a64be` appelle juste avant `0x400a63ac`
    quand le curseur bouge (§2) : le même chemin que l'écoute, mais aucun octet commun, et `pv_parse` ne lit que le
    handle que remplit `0x400a63ac` lui-même, la piste active et le son de la piste ; son masque est `0x401904b4` ;
  - l'affichage en chiffres et les trigless trigs atténués de djd_oz (#53, `46-level-pan-values`, `47-trigless-dim`,
    commit `02cd68d`) : masques `0x4018f4b4`, `0x4018fc74`, `0x4018dba8`, aucun octet commun non plus `[FAIT]`.

  À revérifier à la fusion, avec la preuve `--with` de ces tweaks (pour #52, une note d'écoute après un défilement
  dans un sous-dossier).
- **La machine MACRO** (#57, `25-macro`, `32-macro-tg`, notes/43), fusionnée pendant la relecture : avec Model-TG,
  MACRO prend `32-macro-tg`, posé sur `30-model-tg-st` ; l'écoute prend alors `33-sample-preview-st` (champ `with` de
  la carte, `"macro"` comme `"syntakt"`). Aucun octet commun entre `32-macro-tg` et `33-sample-preview-st` ; la preuve
  passe avec `--with model-tg-st,macro-tg` et avec `6ch-usbup,model-tg-st,macro-tg,arp,trig-hold,tempo-max,boot-anim`
  (le banc charge la charge utile de MACRO en `0x46700000`, que la boucle des voix appelle) `[FAIT en émulation]`.
  Pas d'essai sur la machine de cette combinaison.
- **Numérotation** : note 46, ordre 33, version 1.32, tampon `2026-10-07-10`. Prévus d'abord en 1.26 / `2026-10-07-01`
  (les notes 40 à 45, l'ordre 32 et les versions 1.22 à 1.25 étaient réclamés par des PR en cours), renumérotés à la
  fusion de main (1.28 du sélecteur de mods, 1.31 de MACRO).

## 9. Le tweak

- `33-sample-preview.json` (`requires: ["model-tg"]`) et `33-sample-preview-st.json` (`requires: ["model-tg-st"]`),
  ordre 33, `conflicts: ["chord-keys"]`, écritures identiques.
- 11 écritures : les trois accroches, les quatre constantes de sprites, les quatre zones de code et de données.
- `symbols` : `pv_parse`, `pv_note`, `pv_copy`, `pv_tab`, `pv_src`, `pv_fail`, `pv_failp` (pour la preuve).
- Construction et empreintes du MAIN OS : [BUILD.md](../BUILD.md#écoute-des-samples-model-tg). `model-tg,sample-preview` :
  `b7342804…` ; `model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,sample-preview-st` : `cde4365f…` (recalculées le
  07/10/2026 avec `tools/build.py`). Versions précédentes : la première, dans les masques `0x4018cd48`…, donnait
  `852f25e2…` et `97908683…` ; la deuxième, dans les masques actuels mais avec `pv_fail` seul (§10, point 7),
  `a1b59a3c…` et `17846da5…`.

## 10. Risques et points ouverts

1. `[HYP]` **Attente au premier appui.** `ensure_loaded` est synchrone : l'interface attend la fin de la lecture, puis
   la note part. Pas de mesure sur la machine ; estimation : 10 à 60 ms de données pour un fichier mono de 1 à 5 s
   (le double en stéréo), plus le parcours de l'index de la carte (jusqu'à 128 pages de 64 Ko, environ 0,8 s au pire).
   L'audio continue pendant ce temps (interruptions). À mesurer avec le compteur de blocs `0x8000184c`.
2. `[HYP]` **Concurrence du chargeur.** `ensure_loaded` n'est pas réentrant. `pv_note` prend `ld_busy` comme
   `led_hook`, mais `tick_hook` appelle `load_pending` et `pl_step` sans lui, comme `preset_fail_hook` et
   `pool_store_hook` appellent `ensure_loaded` : le même risque que dans Model-TG lui-même, sans danger si tous tournent
   dans la tâche de l'interface. De même, `led_hook` teste puis écrit `ld_busy` sans masquer les interruptions.
3. `[HYP]` **Aucun verrou du système de fichiers tenu** quand le pad appelle `0x4008171e` (vérifié seulement pour le
   navigateur en `0x400a6426` : `getEntry` prend et rend `0x40fe6df0` par paires) ; sinon le chargement attendrait un
   verrou tenu par sa propre tâche.
4. `[FAIT en émulation]` **Bit « ouvert » du §3.1** : évité sur une piste Sampler (hors de 48..160 o, `pv_parse`
   n'appelle pas la lecture du preset) ; inchangé sur les autres pistes et à l'ouverture d'un fichier. Un fichier de
   48..160 o qui n'est pas un preset passe d'abord par la lecture d'origine, comme sans le tweak : son bit n'a pas été
   regardé `[HYP]`.
5. `[HYP]` **Lecture en +96.** Après une note d'écoute, l'OS lit `CUR_SNDS[t]` + 96 (`0x40059160`), donc l'adresse
   `0x60` ; avec le tweak, pour un son du Sampler, il lit le +96 de la copie (la même valeur que `a5@(96)`, déjà lue en
   `0x4005913c`), passé à `0x400585a8` (qui ne compte que pour les retrigs, notes/32). Sans doute neutre, voire plus
   juste ; pas prouvé sur la machine.
6. `[HYP]` **Preset du Sampler ou son du Sound Pool « SMP… » écouté sur une piste qui n'est pas un Sampler** : l'OS
   donne déjà à cette note la machine du son écouté (66 o) ; le tweak charge en plus son sample et `sp_lock` verrouille
   la case de cette piste. La note normale suivante (autre machine) ne passe pas par `sp_lock` : `track_lock` peut rester
   à 1 jusqu'à la prochaine note du Sampler sur cette piste. Au pire, ce sample reste en mémoire ; à vérifier.
7. `[FAIT en émulation]` **Un essai raté est lié au son désigné** (`pv_fail` + `pv_failp`, §5.3). Correction du
   07/10/2026, après revue : la première version ne gardait que `pv_fail`, remis à zéro seulement quand `pv_parse`
   désignait un fichier de sample. Un échec passager (prise en cours, mémoire pleine) laissait alors muet, sans nouvel
   essai, tout son désigné qui nommait le même sample par un autre chemin (case du Sound Pool, preset du Sampler),
   jusqu'à l'écoute d'un fichier de sample ou au redémarrage. Maintenant toute nouvelle désignation retente, sauf le
   cas rare où le tampon de l'OS revient à la même adresse sans désignation par le navigateur de fichiers entre-temps
   (vérifié en émulation, « limite voulue »).
8. `[FAIT, lecture]` **Un fichier qui n'est ni un preset ni un sample**, de 66 o ou plus, est désigné sur une piste
   Sampler comme un sample (`pv_parse` ne regarde que la taille). Le premier appui fait lire **tout le fichier** par
   `load_at` avant le contrôle de l'en-tête (`ensure_loaded` le refuse ensuite) : l'interface attend pendant cette
   lecture, et `pick_dest` peut d'abord chasser des samples inutilisés (niveau 0) pour faire la place. Puis
   `pv_fail` / `pv_failp` arrêtent les essais sur ce son désigné ; reposer le curseur sur le fichier relance une
   lecture complète. Une mémoire en morceaux (`el_frag` : le tweak n'appelle jamais `rebuild_slots`) : l'appui ne joue
   rien. `kit_ok` ≠ 1 (`sp_lock` ne fait rien) : le sample de la piste.
9. `[HYP]` Si la piste écoutée est la source du rééchantillonnage pendant une capture, la note d'écoute est enregistrée
   comme toute note jouée ; les chargements sont de toute façon refusés pendant l'enregistrement.
10. `[FAIT, lecture et émulation ; conséquences HYP]` **Un appui rendu muet ne l'est pas partout.** « Sans envoi » ne
    coupe que l'envoi au moteur audio, comme pour un pas tenu dans l'OS d'origine : le reste de `0x4008171e` se
    déroule comme à l'origine.
    - Il envoie toujours la note en **MIDI** (`0x400817aa..0x400817d6`).
    - Il envoie toujours le message de la touche à l'interface (`0x40080bf6`, le chemin des touches du live rec) : en
      enregistrement live, navigateur ouvert, un appui muet pourrait poser un trig comme un appui normal. Avec
      l'arpégiateur actif sur la piste, son accroche `0x40081908` lit ce même argument comme « pas tenus » : le
      message part alors au lieu d'être retenu par l'arpège.
    - Au relâchement, `0x4008145e` (qui n'a pas d'argument « sans envoi ») envoie la **fin de note** : elle peut
      arrêter une note de cette piste qui sonnait encore.
11. `[FAIT en émulation pour la source 0x80, lecture pour le MIDI]` **Les autres sources qui emportent le son
    désigné** (`0x80`, `0x10`, `0x04`, `0x400813e2` ; le MIDI reçu sur le canal auto, `[HYP]` pour la correspondance) :
    `pv_note` ne charge rien et ne rend rien muet. Un sample déjà en mémoire joue ; sinon `sp_lock` ne le trouve pas et
    la voix joue le sample de la piste, comme l'OS d'origine. Seule différence : `sp_lock` lève alors `pl_dirty` (pas
    l'origine, où il lit 0), et le préchargeur de Model-TG refait un tour des samples des patterns, sans effet de plus.
12. `[FAIT, source de Model-TG]` **« Jamais un sample du projet » tient si `kit_ok` = 1.** `slot_level` ne voit les
    samples des autres patterns que par `proj_has`, qui rend 0 si `kit_ok` ≠ 1 (`model_tg.s`, vers la ligne 10299).
    Dans ce cas, un sample que seuls d'autres patterns utilisent compte comme inutilisé et une écoute peut le chasser ;
    il se recharge depuis la carte quand un pattern le redemande.
13. `[FAIT, source de Model-TG]` **16 Mo restent réservés aux prises** (`PL_RESERVE`, `pd_mode` 1) : l'appui devient
    muet avant que la mémoire soit pleine au sens propre.
14. `[HYP]` **Le préchargeur peut reprendre la case tout juste chargée.** Le sample écouté reste au niveau 0 :
    `pl_step` (même tâche, après l'appui) peut le chasser pour un sample des patterns avant le bloc audio suivant ;
    cet appui joue alors le sample de la piste, et le suivant attend un nouveau chargement. D'où « en général tout de
    suite » sur le site.
15. Que le gestionnaire des pads tourne au niveau d'interruption 0 : sinon chaque appui sur un sample pas en mémoire
    resterait muet (`pv_note` ne charge qu'au niveau 0). **Vu sur la machine (07/10/2026)**, implicitement : la liste
    de §12 demandait de signaler un appui toujours muet sur un sample pas en mémoire, et Maxime répond « Tout marche
    nickel ». La marge de pile de la tâche de l'interface (le chargement y descend environ 250 o plus bas que depuis
    `tick_hook`) reste `[HYP]` : aucun plantage signalé.

| Établi | Comment |
|---|---|
| Écoute des presets, échec d'un sample au contrôle de taille, effacement de `CUR_SNDS` avant `sp_lock` | `[FAIT]` code + émulation (§2, §3) |
| `sp_lock`, `tok_of`, `pd_mode`, `ld_busy`, `pad_load_hook`, nom des sample locks | `[FAIT]` source de Model-TG v1.1.0 (§4) |
| Les trois accroches et leur effet, du navigateur à la boucle des voix ; `pv_fail` / `pv_failp` ; source `0x80` | `[FAIT en émulation]` §11 (TOUT OK, Model-TG seul et avec les autres tweaks, les deux versions) |
| `kit_ok` et `proj_has`, réserve de 16 Mo, lecture complète d'un fichier qui n'est pas un sample | `[FAIT]` source de Model-TG (§10, points 8, 12, 13) |
| Durée du chargement, concurrence, verrous, lecture en +96, pistes non Sampler, live rec et fin de note d'un appui muet, case reprise par `pl_step`, pile | `[HYP]` (§10) |
| Sur la machine | `[FAIT]` 07/10/2026, les deux fichiers : « Tout marche nickel » (§12), dont le niveau d'interruption des pads (§10, point 15) |

## 11. Preuve en émulation (`tools/emu/test_sample_preview.py`)

Le vrai code de l'OS et de Model-TG (Unicorn), sur l'image avec le tweak et sur « l'origine » (les mêmes tweaks sans
l'écoute des samples). Un seul banc réunit le navigateur, la note jouée, la boucle des événements de l'interruption audio
et la boucle des voix ; seuls sont simulés le système de fichiers (fiches d'inode, ouverture, lecture d'un preset),
l'allocateur, les verrous, les boîtes aux lettres de l'interface, la case du Sound Pool (`vt[76]` de l'objet pool du
kit : une routine de 4 instructions qui rend une copie du son voulu ; à partir de `0x400a6444`, le chemin pool est
celui de l'OS) et le chargeur de Model-TG (`ensure_loaded` : un crochet Python qui note son appel, l'état du chargeur à
ce moment, et rend la case choisie). La pile sous chaque appel est remplie de `0xA5` : un mot laissé non écrit se voit.

| Vérification | Origine | Avec le tweak |
|---|---|---|
| Écritures : `old` (OS d'origine ; `jmp` de Model-TG en `0x4008171e`), aucune autre différence, aucun recouvrement sauf ce `jmp`, refusé sans Model-TG, `sp_lock` attendu, `pd_mode` et `ld_busy` ceux du chargeur | — | 11 écritures, 1 063 octets différents ; aucun recouvrement avec les tweaks choisis ni avec le catalogue (41 tweaks compatibles avec `model-tg-st`, dont `macro-tg` depuis la fusion de MACRO, 7 avec `model-tg` ; écartés : conflit déclaré d'un côté ou de l'autre) ; refusé seul et avec l'autre version de Model-TG ; `tg_uses` = {`pd_mode` : 1, `ld_busy` : 2} ; les six copies disjointes et sous `0x48000000` ; `pv_fail` et `pv_failp` à zéro dans l'image, hors des copies |
| Navigateur (vrais `0x400a64be` et `0x400a63ac`), piste Sampler, fichier de 2 Mo | rien de désigné, fichier laissé ouvert | tampon de 100 o = son de la piste nommé « SMP » + empreinte, fichier pas ouvert, registres gardés, résultat {`pv_src`, 0} exactement (pile remplie de `0xA5`), `pv_fail` à 0 |
| Preset valide ; piste qui n'est pas un Sampler ou sans objet son | — | identique à l'origine (l'appel d'origine a lieu) |
| Fichier de 120 o qui n'est pas un preset ; 47, 48, 65 o ; 66 et 160 o ; 161 o | — | écouté ; rien ; écoutés après la lecture d'origine (refusée) ; écouté sans lecture du preset ni bit « ouvert » |
| Empreinte nulle (`pv_parse` appelé directement, handle fait à la main) | — | {0, 0}, `pv_src` intact ; la même avec une empreinte non nulle : {`pv_src`, 0} |
| Deux défilements | — | les deux tampons alternent, chacun avec le bon nom |
| Note jouée (vrai `0x4008171e` jusqu'à `0x4005894a`, `note_on_hook` compris), sample en mémoire (case 63, la dernière) | — | identique à l'origine |
| Sample pas en mémoire | — | un seul chargement (d0 = empreinte, `pd_mode` 1, `ld_busy` 1, niveau 0), puis la note part |
| Chargement raté ; appui suivant | la note joue | rien n'est envoyé, `pv_fail` = empreinte, `pv_failp` = son désigné ; pas de nouvel essai |
| Le même sample redésigné par le Sound Pool (autre tampon, sans `pv_parse`) | — | nouvel essai |
| Deux désignations du pool sans appui (retour au tampon de l'échec) | — | pas d'essai (limite voulue, §5.3) |
| Un preset désigné par le navigateur, puis le fichier raté revenu dans le tampon de l'échec ; même tampon, autre empreinte | — | `pv_fail` remis à zéro, nouvel essai ; essai |
| Chargeur occupé ; niveau d'interruption 3 ou 7 | — | rien, sans essai, `pv_fail` et `ld_busy` inchangés |
| Sources `0x80`, `0x10`, `0x04`, `0x01`, pas tenus, autre piste, rien de désigné, son qui ne nomme pas de sample | — | identique à l'origine |
| Registres autour d'un chargeur qui détruit tout ce que son contrat permet | — | d2-d7/a2-a6 intacts |
| Boucle des événements (vraie), note d'écoute d'un son du Sampler, pistes 1 à 6 | `CUR_SNDS` = 0, puis lecture en `0x60` | `CUR_SNDS` = la copie, seule différence de l'état ; écritures de la passe (tracées, hors pile de l'interruption) : celles de l'origine, dans le même ordre, l'effacement devenu le pointeur suivi des 25 mots de la copie ; `sp_lock` prend la case du sample écouté (`track_lock` = 1) |
| Note normale suivante, son qui n'est pas du Sampler, notes normales | — | état et écritures identiques |
| Source `0x80`, sample désigné absent de la mémoire | sample de la piste | pas de chargement, la note part, `sp_lock` ne trouve pas le sample : sample de la piste (même sortie) ; `pl_dirty` levé (§10, point 11) |
| `pv_copy` seul, pistes 7 et 8 (`pv_tab[6]`, `[7]` seraient `pv_fail`, `pv_failp`, posés à une adresse témoin) | — | une seule écriture, l'effacement d'origine ; ni copie, ni page 0 |
| Coût d'une passe de la boucle des événements, piste 3 (instructions) | — | note d'écoute d'un son du Sampler 616 → 704 (+88), note normale 619 → 622 (+3) ; avec le jeu `--with` : 683 → 771, 686 → 689 |
| De bout en bout : le navigateur désigne un sample de 2 Mo absent, le pad le charge, la boucle des événements le transmet, la vraie boucle des voix le joue (deux samples de signes opposés) ; la note suivante rejoue le sample de la piste | sample de la piste | sample écouté, puis sample de la piste |

**Résultats** (07/10/2026, version avec `pv_failp`, `33-sample-preview*.json` à jour d'après `--check`) :

| Exécution | Vérifications | Résultat | Durée |
|---|---|---|---|
| `--cycles` seul (origine `model-tg`) | 84 | TOUT OK | 43 s |
| `--with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max,boot-anim --syntakt …` | 84 | TOUT OK | 65 s (trois exécutions en parallèle) |
| `--syntakt …` sans `--with` : les deux versions, `model-tg` puis `model-tg-st` | 168 | TOUT OK | 83 s (idem) |
| `--with model-tg-st,macro-tg` (après la fusion de MACRO, le banc charge sa charge utile) | 84 | TOUT OK | — |
| `--with 6ch-usbup,model-tg-st,macro-tg,arp,trig-hold,tempo-max,boot-anim` | 84 | TOUT OK | — |

La version précédente (`pv_fail` seul) passait 76 vérifications par version de Model-TG.

De bout en bout (pistes 3 et 6) : l'origine joue le sample de la piste (sortie moyenne +6,68e7), le modifié le sample
écouté (−6,68e7, case 7, `track_lock` = 1), et la note normale suivante rejoue le sample de la piste dans les deux.

**La preuve sait échouer.** Première version des masques : trois défauts injectés dans l'image modifiée (script
jetable) la faisaient tomber : `ld_busy` jamais remis à zéro (3 échecs), `pv_copy` qui fait toujours l'effacement
d'origine (23 échecs), test du niveau d'interruption retiré (2 échecs). Version finale : **40 mutations** de l'image
modifiée (harnais jetable, adresses tirées des `symbols`, octets d'origine vérifiés), dont 36 venues de la revue :
chacune fait tomber au moins une vérification, de 1 à 24 ; l'image non modifiée par le harnais passe. Les six
premières lignes ci-dessous passaient la preuve telle qu'elle était à la revue ; les dernières visent `pv_failp` :

| Mutation | Échecs |
|---|---|
| balayage de 63 cases au lieu de 64 | 1 |
| compteur du résultat de `pv_parse` laissé non écrit | 8 |
| garde de l'empreinte nulle retirée | 1 |
| borne de la piste (< 6) retirée dans `pv_copy` | 2 |
| `bra.s` après `jsr pv_copy` vers une mauvaise cible | 9 |
| borne haute 161 au lieu de 160 (ou 159) | 1 |
| `pv_failp` jamais écrit | 5 |
| comparaison du son désigné à `pv_failp` retirée | 3 |
| comparaison de l'empreinte à `pv_fail` retirée | 2 |

**Limites de la preuve** :

- Le chargeur est simulé : `ensure_loaded` est un crochet Python (il détruit aussi tous les registres que son contrat
  permet) ; la vraie lecture de la carte, sa durée, ses verrous, la promesse de `pd_mode` 1 (place libre ou samples
  inutilisés seulement) et la profondeur de pile ne sont pas exercés (§10, points 1 à 3, 12 à 15).
- La case du Sound Pool est simulée à l'entrée : le contrôle de l'entrée (`vt[32]`) reste celui du dossier de fichiers,
  et `vt[76]` est une routine de 4 instructions qui rend {son, 0} ; la suite (`0x400a6444` et après) est le code de
  l'OS.
- La « limite voulue » (§5.3) est vérifiée telle quelle : la vérification devra changer si cette conception change.
- L'ouverture du navigateur (`0x400a6d12`) est couverte en appelant `0x400a63ac` directement (elle en ignore le
  résultat), pas en faisant tourner toute `0x400a6c20`.
- Le son vivant de la piste est supposé être celui du kit (`KIT + 28 + 100 t`), et le kit de Model-TG (`0x40a78888`) le
  même que celui du côté audio (`0x800017e4`).
- Les octets +96..+99 des sons de test sont nuls : le modifié lit ce champ dans la copie quand l'origine lit l'adresse
  `0x60` (§10, point 5) ; c'est ce qui permet de comparer le reste de l'état octet par octet.
- L'empreinte nulle ne passe pas par le vrai chemin : l'OS n'accepte que les fiches d'empreinte impaire
  (`0x4007de0c`) ; la garde de `pv_parse` est vérifiée en l'appelant directement, avec un handle fait à la main.
- Observations sans défaut du tweak : la lecture de preset d'origine (`0x400a2a28`) laisse le bit « ouvert » d'un
  fichier de 2 Mo (le chemin modifié ne l'ouvre pas ; pour 48..160 o, pas regardé, §10 point 4) ; un appui rendu muet
  envoie toujours le message de la touche à l'interface, comme l'origine (§10 point 10).

Flasher (fait par ailleurs, `tools/gen_flasher_tweaks.py`, `docs/flasher/app.js`) : la ligne `sample-preview`
(`cat: screen`, `"requires": "model-tg"`, `with: {"syntakt": …, "macro": "33-sample-preview-st"}` ; `setOn` coche la
carte demandée, `dropOrphans` décoche l'ajout resté seul, annulable avec le reste), et `REF_MAINOS` qui passe de 9 503 à
10 559 combinaisons (les 1 056 nouvelles, une par combinaison de main qui contient Model-TG, ajoutent l'écoute des
samples ; aucune ancienne ne change). `tools/webflash_smoke.sh` vérifie que cocher la carte coche Model-TG, que décocher
Model-TG la décoche, et qu'avec les moteurs du Syntakt ou MACRO elle prend `sample-preview-st`.

```sh
python3 tools/gen_sample_preview.py --cycles model-cycles_OS1.13.syx --check
python3 tools/emu/test_sample_preview.py --cycles model-cycles_OS1.13.syx \
    [--with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max,boot-anim] \
    [--syntakt Syntakt_OS1.42.syx]
```

## 12. Testé sur la machine (07/10/2026)

**Testé sur la machine (07/10/2026).** Maxime a flashé les deux fichiers de test du dossier `ecoute-samples/` du
projet (Model-TG + l'écoute seule, MAIN OS `b7342804…` ; l'écoute avec tout le reste, Model-TG version Syntakt et les
5 moteurs, audio 6 canaux, trig hold, arpégiateur, tempo, animation, MAIN OS `20a116b1…`) avec la liste ci-dessous, et
répond : « Tout marche nickel, tu peux fusionner ». La carte passe de Expérimental à Testé (release 1.32). Il n'a pas
détaillé chaque point ; ceux qu'il n'a pas commentés (durée du premier chargement, live rec, Sound Pool) restent les
points à surveiller si un utilisateur signale un souci.

Liste envoyée pour l'essai :

Firmware : Model-TG + l'écoute des samples (et, à part, la version combinée avec les moteurs du Syntakt).

- Piste Sampler, FUNC + MACHINES, curseur sur un sample déjà chargé dans le projet : le pad de la piste le joue tout
  de suite ; rien ne joue en faisant défiler.
- Curseur sur un sample pas en mémoire : premier appui, une attente (combien ?), puis **le sample doit sonner**. Si
  chaque appui sur un sample pas en mémoire reste muet, le gestionnaire des pads ne tourne pas au niveau
  d'interruption 0 (§10, point 15) : à signaler, il faudra revoir la conception. Les appuis suivants : en général tout
  de suite. Avec un long fichier stéréo aussi.
- Sortir du menu sans rien choisir : la note suivante joue le sample de la piste, son nom n'a pas changé ; choisir le
  fichier le charge comme avant (« Sample loaded to Sampler »).
- Les touches de pas en mode clavier jouent aussi le sample écouté ; le pad d'une autre piste joue son propre son.
- Une piste qui n'est pas un Sampler : les presets s'écoutent comme avant ; sur un fichier de sample, rien n'est désigné
  et le pad joue le son de la piste, comme avant.
- Un pas qui porte un sample lock, tenu, puis FUNC + MACHINES : le navigateur s'ouvre sur le Sound Pool, la case du lock
  sous le curseur (§2, `0x400a6c20`) ; jouée sur la piste, cette case doit faire entendre son propre sample, plus celui
  de la piste (comment la jouer avec le pas tenu : à voir). Même chose pour un preset du Sampler qui nomme un sample.
- Mémoire pleine de samples du projet, ou pendant un rééchantillonnage : l'appui ne joue rien, sans figer la machine ;
  déplacer le curseur et revenir réessaie.
- Live rec, navigateur ouvert sur un sample : un appui qui joue le sample, puis un appui rendu muet (pendant un
  rééchantillonnage, par exemple) ; regarder si chacun pose un trig, quelle note, et si la fin de note d'un appui muet
  coupe une note de la piste qui sonnait encore (§10, point 10). Même chose avec l'arpégiateur actif sur la piste.
- La même chose avec la version combinée (Model-TG + les 5 moteurs du Syntakt, audio 6 canaux).
