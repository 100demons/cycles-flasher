# 41 — L'OS Cycles sur un Model:Samples, avec retour par USB

Demande de Maxime (05/10/2026, fil du projet) : « dans le même fonctionnement que pour flasher son Cycles avec le
webflasher, une section qui permet de flasher son Model:Samples avec l'OS du Cycles, en USB, retour en arrière en USB
possible, via l'onglet Samples OS ».
Générateur : `tools/crossflash.py --to samples` (aller) et `--back-samples` (retour) ; portage JS
`MCBuilder.cyclesForSamples` / `MCBuilder.samplesBack` (`docs/flasher/builder.js`).
Preuve : `tools/emu/test_crossflash_samples.py`. Adresses : VA de l'OS 1.13.

## En bref

- **Une mise à jour USB n'est vérifiée qu'une fois, par l'OS qui tourne**, avec sa propre clé : il écrit ensuite le
  conteneur tel quel en flash `0x20000`, à la place de celui en service, et le bootstrap le démarre sans rien vérifier
  (§1). La « porte 2 » de [15 §3.4bis](15-demandes-reddit.md) n'existe pas (relecture du 06/10/2026).
- **L'aller par USB marche tel quel** : le conteneur officiel du Samples (bootstrap, updater, signature Samples) avec
  le MAIN OS du Cycles passe la vérification de l'OS Samples.
- **Le retour par USB est impossible** avec l'OS Cycles d'origine : il n'accepte qu'un fichier signé Cycles, et
  l'OS Samples officiel est signé Samples.
- **Correctif : 32 octets dans le MAIN OS Cycles.** Sa clé de vérification vient d'une constante de 32 octets
  (`0x401296b2`) lue par une seule fonction. On la recalcule pour qu'elle donne la **clé du Samples** : l'OS Samples
  officiel, inchangé, repasse par USB, et les firmwares Model:Cycles sont refusés (§3).
- La clé n'est jamais dans le dépôt : la page et le script la dérivent du `.syx` officiel du Samples de l'utilisateur,
  comme `mtlib` le fait pour toute signature.
- `[FAIT en émulation]` sur le vrai code de vérification des deux OS et sur le chargeur du bootstrap Samples ;
  **pas encore essayé sur un vrai Model:Samples**.
  Le menu de démarrage du Samples n'est jamais touché : par le MIDI IN, il reste la voie de secours.

## 1. Une mise à jour USB : une seule vérification, par l'OS qui tourne `[FAIT]`

L'OS qui tourne reçoit le `.syx` (SysEx de `CONFIG › UPGRADE` ou protocole de Transfer, [37](37-flash-rapide-usb.md)),
vérifie le conteneur avec **sa** clé (§2), puis l'écrit tel quel en flash `0x20000` et redémarre. `0x20000` n'est pas
une zone d'attente : c'est le conteneur que le bootstrap démarre.

- Écriture : `0x40092304` dans l'OS Cycles (appelée par `0x4006cf28`, seule commande qui écrit, pour les deux
  transports), `0x40091488` dans l'OS Samples (`movea.l #0x20000,a3` en `0x400914b2`). Effacement puis écriture à
  partir de `0x20000`, longueur = celle du conteneur reçu, puis `move.l #0,0x48000000` et
  `move.b #0x80,0xec090000` (redémarrage).
- Démarrage normal (bootstrap, section 2, code identique sur les deux machines à 3 octets près : produit et octet
  appareil) : `0x80000820` lit l'en-tête du conteneur en `0x20000` (`0x80004a12`), sa table de sections en
  `0x20020` (`0x80004a5a`), copie la section 3 en `0x40200000` (`0x8000f010`, lecture de la flash SPI), la
  décompresse en `0x40000400` (`0x800006bc`) et saute à son point d'entrée. **Ni checksum, ni HMAC, ni limite de
  taille.**
- La vérification du bootstrap (`0x80003b36` : checksum de contenu, puis HMAC `0x800059fa` avec sa clé, appelé en
  `0x80003b76`) n'a qu'un appelant, `0x80003ed8`, dans `0x80003d18` : l'installation par le **menu de démarrage**
  (TRIG 4, MIDI IN), qui vérifie une copie en RAM avant d'écrire.
- EMPTY RESET et FACTORY RESET ne font que poser des bits dans l'argument de démarrage (`0x800071d8`, en
  `0x8000208e` et `0x800020b0`) : ils n'écrivent pas la flash, c'est l'OS démarré qui réinitialise le projet.
- La mise à jour du bootstrap lui-même (`0x8000214c`) n'a lieu que si la version de la section 2 reçue dépasse celle
  en place : `0x0400` partout en 1.13, donc jamais ici.

> Source : bootstraps et MAIN OS 1.13 désassemblés, relecture contradictoire du 06/10/2026 (8 relectures et une
> synthèse) ; chargeur `0x80000820` exécuté dans Unicorn sur les trois conteneurs (§5, groupe 6).
> Conséquence pour [15 §3.4bis](15-demandes-reddit.md) : le `--back` du 29/09 a bien été écrit (voir la correction
> en tête de 15 §3.4bis).

| Situation | Vérification (l'OS qui tourne) | Fichier qui passe |
|---|---|---|
| Samples d'origine, aller | OS Samples, clé Samples | conteneur Samples + MAIN OS Cycles (`--to samples`) |
| Samples sous OS Cycles **d'origine**, retour | OS Cycles, **clé Cycles** | aucun fichier Samples officiel |
| Samples sous OS Cycles **de la page**, retour | OS Cycles, **clé Samples** (32 octets changés) | l'OS Samples officiel, transport Cycles (`--back-samples`) |

## 2. La vérification dans l'OS Cycles `[FAIT]`

`0x4005a0e4 (a2 = [longueur][checksum][conteneur])` est appelée par les trois chemins de mise à jour du MAIN OS :

| Appelant | Rôle |
|---|---|
| `0x400860a0` | réception SysEx (`CONFIG › UPGRADE`) |
| `0x4006ce92` | protocole d'Elektron Transfer (le `.syx` reçu en mémoire, extrait par `0x400813c2`) |
| `0x40092314` | écriture en flash (`0x40092304` : re-vérifie, efface et écrit à partir de `0x20000`) |

Elle renvoie 1 si tout va bien, sinon :

| Étape | Fonction | Échec |
|---|---|---|
| checksum de contenu (somme des mots `(i+1) ^ w`) | `0x40081e26` | 3 |
| HMAC-SHA256 du conteneur | `0x40052750` | 4 |
| alimentation suffisante (broches, tension) | `0x400530ca` | 5 |

**Rien n'y dépend du modèle, sauf la clé.** Aucun contrôle de l'en-tête du conteneur (octet `0x04`), du nom ou des
sections : un conteneur Samples bien signé passerait.

`0x40052750 (données, longueur)` dérive la clé exactement comme `mtlib.container.find_key` :

```
40052758  pea 0xc ; pea 0x40129650        copie "REVERB SEND\0" (12 o) sur la pile
40052788  move.b (a0)+,-(a1)              la même chaîne à l'envers
40052792  … jsr 0x400786fc (x2)           SHA-256 des 11 octets, à l'endroit et à l'envers
400527c0  lea 0x401296b2,a1               C : 32 octets
400527c6  … eor …                         clé = SHA(s) ^ SHA(s inversée) ^ C
400527fa  jsr 0x400785b8                  HMAC-SHA256(clé, données[0 .. longueur-32])
4005280a  …                               comparaison avec les 32 derniers octets
```

- `"REVERB SEND"` (`0x40129650`) est aussi un **nom de paramètre affiché** (deux références : `0x4005275e` et
  `0x4010a924`, la table des noms) : on n'y touche pas.
- `C` (`0x401296b2`) n'a **qu'une** référence dans tout le MAIN OS : `0x400527c2`. La changer ne change que la clé.
- Contrôle : avec le `C` d'origine, la formule redonne la clé que `mtlib` tire du bootstrap Cycles
  (`8c0e4553…9a0b98bd`) ; le script refuse de continuer sinon.

## 3. Le correctif

```
C' = cléSamples ^ SHA-256("REVERB SEND") ^ SHA-256("DNES BREVER")
```

écrit à la place de `C` (`0x401296b2`, 32 octets). `cléSamples` est celle que `mtlib` tire du `.syx` officiel du
Samples (son bootstrap) ; elle est aussi celle que dérive le MAIN OS Samples ([15 §3.4](15-demandes-reddit.md),
`"DELAY TIME"` + `0x4012a37e`).

- Aucune place libre utilisée, aucun code ajouté : 32 octets de données.
- La section 3 est recompressée avec `aplib.repack` (seuls les octets touchés deviennent des littéraux), relue et
  comparée.
- Ce n'est **pas** un tweak JSON : ses octets dépendent de la clé du Samples, qu'on ne versionne pas (règle 1 du
  dépôt). Le script et la page la calculent depuis le fichier de l'utilisateur.

Effets de bord, voulus :
- l'OS Cycles de la page **refuse** l'OS Cycles officiel et tout firmware Model:Cycles avec mods (signés Cycles),
  y compris une mise à jour proposée par Elektron Transfer : rien n'est écrit. C'est une protection : un firmware
  Model:Cycles accepté serait démarré tel quel, et l'OS Cycles d'origine qu'il contient fermerait le retour par USB
  (`[HYP]` une future version dont la section 2 serait plus récente remplacerait même le bootstrap du Samples) ;
- il **accepte** `--to samples` (signé Samples) : une future version se met à jour par USB, à condition de l'emballer
  dans le transport Cycles (§4) ; la page ne le propose pas encore.

## 4. Le fichier de retour : l'OS Samples officiel dans le transport Cycles

L'OS Cycles ne route la mise à jour que pour l'identifiant produit `0x11` et l'octet appareil `0x0C`, base des sommes
de contrôle des paquets (miroir des contrôles 1 et 2 de [15 §3.4](15-demandes-reddit.md)). `--back-samples` reprend
le flux décodé de l'OS Samples officiel **tel quel** (préambule, conteneur, signature Samples) et le réemballe avec
`syx.wrap(…, 0x11, séquence de départ du Cycles)` : le même emballage que tous les firmwares Model:Cycles que la page
envoie déjà.

Une fois reçu, c'est octet pour octet le conteneur officiel du Samples : la flash se retrouve dans l'état d'une
mise à jour officielle du Model:Samples.

## 5. Preuve en émulation `[FAIT en émulation]`

`tools/emu/test_crossflash_samples.py` (20 contrôles) fait tourner `0x4005a0e4` (Cycles) et son équivalent dans l'OS
Samples (trouvé par son appel au HMAC `0x40051728`), vérification d'alimentation court-circuitée :

| Fichier | OS Samples d'origine | OS Cycles d'origine | OS Cycles de la page |
|---|---|---|---|
| OS Samples officiel | accepte | — | — |
| `--to samples` (aller) | **accepte** | refuse (4) | accepte |
| `--back-samples` (retour) | — | **refuse (4)** : le verrou | **accepte** |
| OS Cycles officiel | — | accepte | **refuse (4)** |
| retour avec un octet changé | — | — | refuse |

Et en plus :
- `--to samples` : sections 2, 4, 5 et en-tête du conteneur identiques à l'officiel Samples, HMAC valide avec la clé
  du Samples (celle que vérifie aussi le menu de démarrage) ;
- son MAIN OS ne diffère de l'OS Cycles officiel que dans les 32 octets de `0x401296b2` ;
- `--back-samples` décodé = flux de l'OS Samples officiel, en-tête SysEx `F0 00 20 3C 11 00 7F 01 0C` ;
- groupe 6, démarrage : le chargeur du bootstrap Samples (`0x80000820`), avec chaque conteneur écrit en `0x20000`,
  pose en `0x40000400` le MAIN OS attendu (OS Cycles de la page, fin `0x401aa140` ; OS Samples officiel pour le
  retour et le témoin, fin `0x401a7640`), sans passer par `0x80003b36` ni `0x800059fa`. Le flux compressé est lu en
  `0x40200000`, au-delà de la fin du MAIN OS décompressé.

Ce qui n'est **pas** émulé : la réception SysEx/Transfer elle-même (même transport que les firmwares Cycles déjà
envoyés par la page, testés sur la machine ; relue sans trouver de contrôle du modèle ni de taille), l'écriture en
flash, la vérification d'alimentation (registre `0xec094018`) et le démarrage de l'OS Cycles sur le matériel du
Samples.

Empreintes (SHA-256) :

| Fichier | SHA-256 |
|---|---|
| `model-cycles_OS1.13_for-model-samples.syx` (`--to samples`) | `c06c23f31e50fac6ad40cd0f633acd4a7da4f63c929dff563dae887b93105dd4` |
| son MAIN OS | `b6fbc48f7d7d07cecae3859e07270fa2298f393e8afa2643144bdb4efc317aad` |
| `model-samples_OS1.13_back-from-cycles-os.syx` (`--back-samples`) | `d63ce13dd1a5039d11b60d3f69d4e88e9d0f56fb2e7350c105ec641d32083680` |

## 6. Dans le flasher

Onglet *Samples OS*, trois choix : *Model:Cycles → OS Samples* (l'existant, [15 §3.2](15-demandes-reddit.md)),
*Model:Samples → OS Cycles* et *Model:Samples : retour à son OS*, ces deux-là étiquetés **expérimental**. Les deux
fichiers officiels sont demandés (Cycles puis Samples). La page refuse un résultat dont le SHA-256 diffère de la
référence (`REF_CYCLES_ON_SAMPLES`, `REF_SAMPLES_BACK`).

Avec la méthode rapide, la page demande qui répond : l'aller ne part que vers une machine qui répond Model:Samples, le
retour que vers une machine qui répond Model:Cycles. Cas qu'elle ne peut pas distinguer :
- le retour envoyé à un **vrai Model:Cycles** : refusé (signature), rien n'est écrit ;
- l'aller envoyé à un **Model:Cycles sous OS Samples** (il répond Model:Samples) : l'OS Samples l'accepte (clé
  Samples) et l'écrit ; le bootstrap Cycles démarre alors l'OS Cycles de la page. Sans danger, mais ce Cycles
  refuse ensuite les firmwares Model:Cycles par USB : retour par le menu de démarrage et le MIDI IN. La carte et le
  guide disent donc « seulement sur un vrai Model:Samples ».

- le retour envoyé à un **Model:Samples sous un OS Cycles installé autrement** (autre outil, ou un build Model:Cycles
  avec mods, clé Cycles d'origine : aucun tweak ne touche la vérification) : refusé (HMAC, « Upgrade Failed »), rien
  n'est écrit. Un tel OS accepte en revanche `--to cycles` (choix *Model:Cycles → OS Samples*, signé Cycles), dont le
  bootstrap Samples tire l'OS Samples officiel (groupe 7 de la preuve) ; c'est ce que disent `sback_w1`,
  `dev_fwd_on_cycles` et le guide. Avec Model-TG en identité Transfer SMP, la machine répond Model:Samples (25) :
  `dev_back_on_samples` le signale.

Après l'envoi, la carte et le guide disent aussi quoi faire si la machine démarre mal (OS précédent toujours là,
écran figé, cf. le 29/09 en [15 §3.4bis](15-demandes-reddit.md)) : l'éteindre et la rallumer ; sinon, [FUNC] à
l'allumage puis [TRIG 2] EMPTY RESET, qui vide le projet actif (d'où la sauvegarde avec Transfer).

## 7. Ce qui reste à vérifier sur la machine `[À FAIRE]`

Sur un vrai Model:Samples (Maxime) :
1. sauvegarde des samples et projets avec Transfer ;
2. *Model:Samples → OS Cycles*, méthode rapide : la machine redémarre en Model:Cycles (Transfer la voit Model:Cycles),
   les machines du Cycles jouent, le panneau répond. Noter ce qu'elle fait juste après le redémarrage : nouvel OS
   tout de suite, ou ancien OS jusqu'à un arrêt, ou écran figé jusqu'à EMPTY RESET (le 29/09 reste inexpliqué) ;
3. ce que l'OS Cycles fait des données du Samples (projets, +Drive) ;
4. *Model:Samples : retour à son OS*, méthode rapide : retour au Model:Samples, samples et projets présents ;
5. en secours si 4 échoue : menu de démarrage du Samples et l'OS Samples officiel par le MIDI IN.

## 8. Premier rapport sur un vrai Model:Samples (akrism, Discord, 06/10/2026)

> Source : message d'akrism dans le forum *feature-requests* du Discord (fil « Web Flasher: Model:Samples → Model:Cycles
> conversion »), relayé par Maxime le 06/10/2026. Rapport d'un tiers, non reproduit par nous ; son script
> (`wrap_for_samples.py`) n'a pas pu être lu (CDN de Discord bloqué ici).

Ce qu'il a fait : `build.py -t model-tg,6ch-usbup`, puis sa section 3 dans le conteneur officiel du Samples, signé
avec la clé Samples (comme `--to samples`, mais **sans** le correctif de 32 octets), envoyé par l'onglet Mods de la
page (méthode rapide). Résultat rapporté : la machine démarre en Cycles, le Sampler de Model-TG marche, Transfer
charge des samples en identité SMP.

- `[FAIT, matériel, rapporté]` L'OS Cycles (avec mods) démarre et tourne sur un Model:Samples installé par USB dans
  le conteneur Samples : c'est le chemin de l'aller de cette note, et cela confirme sur la machine qu'il n'y a qu'une
  vérification (§1).
- Ce que ça ne prouve pas : le correctif de 32 octets et le retour par USB.
- `[FAIT en émulation]` Dans son état (OS Cycles avec mods, clé Cycles) : l'OS Samples officiel, le retour et l'aller
  de cette note sont refusés (4), une build Mods normale est acceptée (1), et `--to cycles` est accepté puis démarré
  en OS Samples officiel, qui accepte ensuite l'OS Samples officiel (1). Son retour par USB passe donc par le premier
  choix de l'onglet ; refaire son propre emballage depuis cet état est refusé (sans danger).
- Piste, PR séparée après le test de Maxime : *OS Cycles avec mods pour Model:Samples*. Vérifié en émulation sur les
  plus grosses combinaisons : aucun tweak, recette Syntakt ou cave ne touche la vérification ni `0x401296b2` ;
  restaurer les 32 octets redonne l'entrée de `REF_MAINOS` ; `C'` est le même pour toutes les combinaisons (une seule
  référence) ; la plus grosse finit en `0x401fae10` (< `0x40200000`) et son conteneur (948 928 o) s'arrête en
  `0x107ac0`, loin de `0x1e0000`. `cyclesForSamples` accepte déjà un `.syx` modifié. À prévoir : changer de mods plus
  tard demande un nouveau type de fichier (conteneur signé Samples dans le transport Cycles), et créditer akrism.
