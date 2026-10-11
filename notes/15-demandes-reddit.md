# 15 · Demandes de la communauté (Reddit) : réponses et plan

Le 29/09/2026, après la validation du 6 canaux et de SD VINTAGE sur un vrai Model:Cycles, l'utilisateur a relayé quatre
demandes d'utilisateurs de r/Elektron. Cette note les traite **une par une**, dans l'ordre le plus efficace :
d'abord ce qui existe déjà et se livre vite, ensuite ce qui demande de la recherche.

## 0. En bref

| # | Demande | État | Où |
|---|---|---|---|
| 1 | Un mode mute sans tenir FUNC | ✅ **livré** : tweak `latching-mute` de drumkilla, dans le flasher web | §1 |
| 2 | Regrouper avec le tweak « trig preview » | ✅ **livré** : `trig-preview` (et `browser-scroll`), dans le flasher web | §2 |
| 3 | Flasher l'OS Model:Samples, ou une machine « samples » dans l'OS Cycles | ✅ **l'OS Samples tourne sur un vrai Model:Cycles** (29/09/2026) : onglet *Samples OS* du flasher web, ou `tools/crossflash.py`. La machine « samples » dans l'OS Cycles vient après | §3 |
| 4 | Porter les machines numériques du Syntakt | 🟡 **le vrai SD VINTAGE tourne en émulation, et le nôtre est recalé dessus** ([16](16-moteur-syntakt.md)). Les machines FM du Syntakt sont celles du Cycles | §4 |

Ordre suivi : **§3 d'abord** (fichier de 686 Ko, la comparaison des deux OS 1.13 a répondu vite à la question clé :
le matériel est le même), **puis §4** (plus long, mais il s'appuie sur le banc d'émulation de SD VINTAGE).

---

## 1. Mode mute sans tenir FUNC — ✅ livré

**Demande** : pouvoir muter sans appuyer sur FUNC, via un raccourci plutôt que par le menu.
> Source : commentaire r/Elektron relayé par l'utilisateur le 29/09/2026.

**Réponse** : le tweak `latching-mute` de [drumkilla/elektron-model-tweaks](https://github.com/drumkilla/elektron-model-tweaks)
fait exactement ça.
- Maintenir **TRK** et taper **FUNC** : le mode mute reste verrouillé, la touche FUNC s'allume. Les trigs mutent alors les pistes sans tenir FUNC.
- Un appui court sur FUNC seul en sort. Les combinaisons avec FUNC (menus, encodeurs rapides) ne le font pas sortir.
- Le comportement d'origine (tenir FUNC) est inchangé.
> Source : README de drumkilla/elektron-model-tweaks, section *Latching track mute* (commit `6e0b4df`), et la description du tweak
> `tweaks/model-cycles_OS1.13/01-latching-mute.json`.

**Ce qui a été fait** :
- Le fichier du tweak est repris **sans modification** dans `tweaks/model-cycles_OS1.13/` (licence MIT, auteur crédité).
- Notre `build.py` produit **le même MAIN OS, octet pour octet**, que le `tweak.py` de drumkilla (vérifié le 29/09/2026).
- Il est proposé dans le flasher web, combinable avec le 6 canaux, avec l'auteur affiché sur la carte.
- Testé sur du vrai matériel **par son auteur** ; pas encore par nous.

## 2. Trig preview — ✅ livré

**Demande** : regrouper nos mods avec celui qui a ajouté le « trig preview » au Model:Cycles.
> Source : commentaire r/Elektron relayé par l'utilisateur, qui l'identifie à drumkilla/elektron-model-tweaks.

**Réponse** : c'est bien le tweak `trig-preview` du même dépôt.
- Séquenceur à l'arrêt : maintenir un pas et appuyer sur PAGE fait jouer ce pas, avec sa note, sa longueur, ses p-locks et son sound-lock.
- La page ne tourne pas. Il joue même si la condition de trig ou la probabilité l'excluraient, et même sur une piste mutée.
> Source : README de drumkilla/elektron-model-tweaks, section *Trig preview*.

Retouché le 04/10/2026 : l'écoute marche aussi séquenceur en pause, où le met un Stop MIDI reçu ([note 34](34-ecoute-en-pause.md)).

Le troisième tweak du dépôt, `browser-scroll` (défilement des noms longs dans le navigateur), est livré avec.
Même vérification octet pour octet, même crédit.

### Point technique : une exception au contrôle des caves

Notre `build.py` refusait `browser-scroll` : une constante de l'OS (`0x40148564`) pointe vers la zone `0xFF` où il écrit.
Vérifié à la main :
- La zone `0x401485ee` est la **table caractère → glyphe** d'une petite police de chiffres (0-9, `%`, `.`, `/`) : 256 entrées de 16 bits, `0xFFFF` = pas de glyphe.
- Juste après, `0x401487ee` est la table des **largeurs**, qui vaut 0 pour tous les caractères sans glyphe.
- `browser-scroll` n'écrit que les entrées des caractères de contrôle 1 à 8, jamais dessinés. drumkilla a volontairement laissé l'entrée 0 intacte.
- Les caves de `latching-mute` (`0x40148662`, 396 o) sont les entrées 58 à 255 de la même table : même raisonnement, et aucune référence directe n'y pointe.

Plutôt que `--force-cave`, cette référence est déclarée dans `device.json` (`cave_refs_ok`), avec la partie réellement libre (`0x401485f0`–`0x4014862e`, caractères 1 à 31).
Le build l'accepte tant que les écritures restent dans cette partie, et refuse sinon. La règle est la même en Python et en JS, et elle est testée (`tools/webbuild_check.sh`).
> Source : octets de l'OS 1.13 officiel, décodés le 29/09/2026 (table des glyphes et des largeurs).

---

## 3. OS Model:Samples sur un Model:Cycles, ou une machine « samples » — ✅ route validée sur le matériel

**Demande** (deux idées liées) :
- une voie pour flasher le logiciel du Model:Samples sur le Model:Cycles, et idéalement faire tourner « les deux en même temps » ;
- un utilisateur de Reddit dit avoir ajouté une machine « samples » au firmware Cycles, sans jamais donner de détails.
> Source : commentaire r/Elektron relayé par l'utilisateur, avec le lien vers le fil *Flashing Model:Cycles firmware into a Model:Samples*.
> Le fil lui-même n'a pas pu être lu d'ici : Reddit bloque l'accès automatisé, et la page Gearspace sur le même sujet affiche une vérification anti-robot.

### 3.1 Ce que dit la comparaison des deux OS 1.13 (29/09/2026)

OS Model:Samples 1.13 téléchargé avec ton accord (`model-samples_OS1.13.zip`, 686 162 o, elektron.se), jamais versionné.
Comparé section par section à l'OS Cycles 1.13 :

| Section | Model:Cycles | Model:Samples | Verdict |
|---|---|---|---|
| 5 (horodatage) | `210525 16:37:28` | `210525 16:34:28` | **compilés le même jour, à 3 minutes d'écart** |
| 2 (bootstrap : menu de démarrage, init DDR) | 26 602 o | 26 602 o | **même code** : 355 octets diffèrent, tous dans l'identifiant produit, le nom, la clé de signature et une somme de contrôle |
| 3 (MAIN OS) | 1 744 192 o | 1 733 184 o | la seule vraie différence |
| 4 (updater) | 31 752 o | 31 752 o | **identique octet pour octet** |

> Source : conteneurs ELE3 des deux `.syx` officiels, dépaquetés avec `tools/mtlib` le 29/09/2026.

Détail des différences du bootstrap :
- l'identifiant produit (`0x11` contre `0x0F`), l'octet d'appareil (`0x0C` contre `0x0A`) et le nom `MODEL:CYCLES` / `MODEL:SAMPLES` ;
- la chaîne de dérivation de la clé HMAC : `REVERB SEND` pour le Cycles, `DELAY TIME` pour le Samples ;
- l'octet `0x04` de l'en-tête du conteneur : `0x15` contre `0x14`.

Tout le reste est commun, y compris la liste des touches (`ENCODER A` à `H`, `FUNCTION`, `TRACK`, les 8 pads `KICK` … `CYMBAL`…) :
**le panneau est câblé pareil**.

`[FAIT]` Le bootstrap programme le **contrôleur de RAM DDR** (45 références aux registres `0xFC0B8xxx`), avec le même code sur les deux machines.
`[HYP forte]` Le Model:Cycles a donc la même RAM que le Samples (64 Mo, dont la place des samples du projet).
Ça concorde avec l'état des voix du moteur Cycles, rangé à `0x42308828`, à plus de 35 Mo du début de la RAM ([14 §2.4](14-machine-sd-vintage.md)).
> Le Model:Samples a 1 Go de stockage et 64 Mo de RAM pour les samples. Source : test du Model:Samples par Attack Magazine.

`[FAIT]` Le MAIN OS du Cycles contient déjà **toute la couche de stockage du Samples** : système de fichiers sur carte MMC (`SafeMmcStreamWriter`, `FileSystemDirectory`, `+DRIVE`), `"sample_references"`, `verify_samples_in_bgworker`, et même des classes nommées `ModelSamplesSysex`.
Ce qui n'existe que dans l'OS Samples : `SampleManager`, `SamplePoolDirectory`, les paramètres *Sample Start/Length/Pitch/Slot*, les *Sample Locks*, « Memory full ».
**Même base de code, le Cycles sans le moteur de samples.**

### 3.2 La route de flash : `tools/crossflash.py` et l'onglet *Samples OS* `[FAIT]`, validée

> ✅ **29/09/2026** : l'utilisateur a flashé ce fichier sur son Model:Cycles et confirme que « l'OS du Model:Samples a fonctionné ».
> C'est, à notre connaissance, le premier test publié de ce sens-là. Le comportement avec les projets Cycles déjà présents
> et le retour à l'OS Cycles n'ont pas encore été rapportés en détail.
>
> Depuis, le flasher web le propose dans un 3ᵉ onglet, *Samples OS*. Il faut y déposer les deux `.syx` officiels, reconnus à leur SHA-256.
> La page construit l'image avec `MCBuilder.crossflash`, portage JS de `crossflash.py` qui donne le **même fichier, octet pour octet**.
> Elle exige le SHA-256 de référence du résultat (`614d28cf…`). Une case oblige à confirmer qu'on a une interface MIDI pour le retour.
> Le parcours complet est testé par `tools/webflash_smoke.sh model-cycles_OS1.13.syx model-samples_OS1.13.syx`.

Principe, déjà prouvé dans l'autre sens :
- le bootloader **ignore en silence** un conteneur d'un autre produit ;
- on garde donc le conteneur de la machine hôte et on ne remplace que sa section 3 ;
- le bootstrap de l'hôte n'est pas touché, donc son `.syx` officiel reste l'image de secours.
> Source : `vendor/ms-multi-output/README.md`, section *You own a Model:Samples → --target cycles-crossflash*. La technique vient d'un utilisateur de r/Elektron, et scottmetoyer l'a testée sur un Model:Samples, retour compris.

```sh
python3 tools/crossflash.py --cycles model-cycles_OS1.13.syx --samples model-samples_OS1.13.syx --to cycles
# -> model-samples_OS1.13_for-model-cycles.syx : OS Samples, conteneur/bootstrap/updater/clé du Cycles
```

- Les deux `.syx` et leurs MAIN OS doivent être les officiels (SHA-256).
- La section 3 du Samples est reprise **telle quelle** : son flux aPLib d'origine, rien n'est recompressé.
- Le fichier produit est relu en entier : paquets, sections 2/4/5 identiques à celles du Cycles, MAIN OS identique au Samples une fois décompressé, HMAC valide avec la clé du Cycles. Le vérificateur JS du flasher l'accepte aussi (6 637 paquets, environ 4,5 min sur un câble MIDI).
- `--to samples` fait l'inverse (OS Cycles pour un Model:Samples), comme la cible `cycles-crossflash` de ms-multi-output.

Protocole (celui qui a été suivi pour le premier test) :
1. **Sauvegarder** les projets et le +Drive avec Elektron Transfer. L'OS Samples va trouver des données de projet Cycles : comportement inconnu, et ms-multi-output fait la même mise en garde dans l'autre sens.
2. Garder l'**interface MIDI branchée sur le MIDI IN** : le retour passe par le menu de démarrage du Cycles, qui n'écoute que le MIDI IN.
3. Flasher le fichier par le **menu de démarrage** (FUNC + allumage, TRIG 4) avec `flash.sh` / `flash.bat`. `CONFIG > UPGRADE` par USB devrait aussi l'accepter : c'est un conteneur Cycles valide.
4. Observer le démarrage :
   - s'il bloque sur le projet Cycles, `EMPTY RESET` (TRIG 2 du menu de démarrage) est à essayer, sinon le retour ;
   - puis charger un sample avec Transfer (la machine s'annonce « Model:Samples »), le jouer, et vérifier le panneau.
5. **Ne pas utiliser `CONFIG > UPGRADE` depuis l'OS Samples** : avec un `.syx` Samples officiel, il réécrirait aussi le bootstrap, et la machine deviendrait un Model:Samples complet côté logiciel.
6. Retour : menu de démarrage du Cycles, puis `model-cycles_OS1.13.syx` officiel par le MIDI IN.

Le retour depuis l'OS Samples n'est **garanti** que par le MIDI IN : le flasher web l'écrit en toutes lettres et exige la case « interface MIDI ».

### 3.3 « Les deux en même temps » : une machine sample dans l'OS Cycles `[À FAIRE]`, plus tard

- **Double démarrage** (deux MAIN OS en flash, choisis au démarrage) : à écarter. Il faudrait modifier le bootstrap, c'est-à-dire le code même du menu de secours.
- **Machine « sample » dans le moteur Cycles** : l'analyse la rend moins lointaine que ne le disait la [note 10 §4](10-faisabilite-fonctionnalites.md). Même RAM (hyp. forte), même stockage, même bibliothèque de fichiers. Mais il faudrait greffer le `SampleManager` (chargement, liste, UI) et une voix de lecture dans le moteur.
  Le test de la route 3.2 a réussi : le matériel du Cycles fait tourner le moteur de samples. La machine « sample » dans l'OS Cycles devient donc un vrai chantier possible, qu'il reste à planifier.

### 3.4 Retour à l'OS Cycles **par USB**, sans interface MIDI — 🟠 probablement possible (corrigé le 06/10/2026, §3.4bis). MIDI conseillé

> **Mise à jour du 30/09/2026** : l'utilisateur a retrouvé l'OS Cycles **sans interface MIDI**, par un factory reset depuis le menu de démarrage (power + trig).
> La conclusion « impossible » ci-dessous vaut pour le chemin `CONFIG › UPGRADE` étudié ici, pas pour tout retour.
> Le mécanisme exact (pourquoi la réinitialisation a suffi) n'est pas élucidé : à comprendre avant de le proposer dans le flasher.
> Source : message de l'utilisateur du 30/09/2026.

**Situation** (29/09/2026) : l'utilisateur a flashé l'OS Samples sur son Cycles par USB, puis s'est aperçu qu'il n'a pas d'interface MIDI.
Le retour « officiel » passe par le menu de démarrage, donc par le MIDI IN ([§3.2](#32-la-route-de-flash--toolscrossflashpy-et-longlet-samples-os-fait-validée)).
Question : y a-t-il un retour par `CONFIG > UPGRADE` (USB) depuis l'OS Samples ?

> **Réponse (30/09/2026, après désassemblage du chemin d'écriture) : non, pas dans l'état où se trouve la machine.**
> Un `.syx` de retour a été construit et envoyé par l'utilisateur : la mise à jour « a semblé marcher » (réception jusqu'au bout, redémarrage)
> mais la machine est **restée sur l'OS Samples**. C'est le scénario « sans danger » — refus **avant** commit. La cause est structurelle (ci-dessous),
> et **la variante « MAIN OS seul » n'y change rien**. Le retour passe obligatoirement par une **interface MIDI** (menu de démarrage, [FLASH §5](../FLASH.md)).

**Le `.syx` officiel Cycles est ignoré tel quel par l'OS Samples.** Trois contrôles, tous propres au modèle, relevés en désassemblant les deux MAIN OS 1.13
(sections 3 décompressées, `tools/mtlib`, capstone ColdFire) :

| # | Contrôle de l'OS Samples | Valeur exigée | Cycles |
|---|---|---|---|
| 1 | **Routeur SysEx** : table indexée par l'octet produit du message (`0x40080356`, table `0x40144f58`) | entrées non vides : `0x04`, **`0x0F`**, `0x10`. Le gestionnaire d'OS upgrade (`0x4007fbb6`) n'est lié que dans la table `0x0F`, aux commandes `0x7E` (données) et `0x7F` (marqueurs) | `0x11` (routeur `0x40081348`, table `0x40148d08`) |
| 2 | **Marqueur de début** : octet appareil `info[0]` (octet 8 du message), aussi base du checksum des paquets (`0x40080dd8`, `moveq #$a`) | `0x0A` | `0x0C` |
| 3 | **HMAC-SHA256 du conteneur**, calculé par le MAIN OS lui-même (`0x40051728`, appelée par `0x40059104`, avant toute écriture, `0x40091488`) | clé dérivée de `"DELAY TIME"` + 32 octets en `0x4012a37e` : **la clé Samples** | clé `"REVERB SEND"` |

> Source : MAIN OS de `model-samples_OS1.13.syx` et de `model-cycles_OS1.13.syx`, désassemblés le 29/09/2026.
> La clé recalculée depuis le MAIN OS Samples est identique à celle que `mtlib` tire du bootstrap Samples (contrôle fait par `tools/crossflash.py --back`).

Conséquence : un paquet `0x11` est ignoré sans message d'erreur (l'écran reste sur « Waiting for SysEx »), et même accepté par le routeur il échouerait sur le marqueur puis sur le HMAC.
C'est cohérent avec l'aller : l'OS Cycles a accepté un conteneur Cycles (`0x11`, `0x0C`, clé Cycles) qui contenait le MAIN OS Samples.

**Le fichier de retour.** `python3 tools/crossflash.py --cycles model-cycles_OS1.13.syx --samples model-samples_OS1.13.syx --back`
produit `model-cycles_OS1.13_back-from-samples-os.syx`, qui garde **tout le contenu Cycles officiel** et ne change que ce que l'OS Samples inspecte :

- transport Samples : produit `0x0F`, octet appareil `0x0A`, checksums recalculés (6 953 paquets, comme l'officiel) ;
- 32 octets de HMAC recalculés avec la clé Samples, et le checksum de contenu du préambule qui les couvre.

Vérifié le 29/09/2026 : les octets du conteneur ne diffèrent de l'officiel Cycles **que** dans ces 32 octets (sections 2, 3, 4, 5 et en-tête ELE3 identiques, dont l'octet `0x15`).
Le script rejoue sur le fichier les contrôles ci-dessus (produit, marqueur, checksum de chaque paquet, checksum de contenu, HMAC valide avec la clé Samples et **invalide** avec la clé Cycles),
et le vérificateur JS du flasher web l'accepte (`Model:Samples`, 6 953 paquets).

Ce fichier passe **la première** vérification, mais pas la suite. Voici pourquoi (raisonnement du 30/09, **faux** : voir la correction en tête de §3.4bis).

### 3.4bis Le vrai blocage : une mise à jour USB est vérifiée **deux fois**, avec **deux clés différentes** (faux, corrigé le 06/10/2026)

> **Correction du 06/10/2026** `[FAIT]` : **il n'y a pas de « porte 2 »**. Une mise à jour USB n'est vérifiée qu'une
> fois, par l'OS qui tourne. `0x20000` n'est pas une zone de staging mais le conteneur en service : l'OS l'efface et
> y écrit le conteneur reçu, puis redémarre, et le bootstrap démarre ce qui s'y trouve **sans checksum ni HMAC**
> (chargeur `0x80000820`, exécuté en émulation sur trois conteneurs). Le HMAC du bootstrap ne sert qu'au menu de
> démarrage (MIDI IN). Adresses et preuve : [41 §1](41-os-cycles-sur-samples.md).
> Conséquences :
> - le 29/09, le `--back` (signé Samples) **a bien été écrit** par l'OS Samples. Le FACTORY RESET du 30/09 ne fait
>   que poser un bit dans l'argument de démarrage (`0x800071d8`) avant de démarrer ce qui est en `0x20000` : c'est
>   donc lui qui a ramené l'OS Cycles. Pourquoi la machine semblait d'abord rester sur l'OS Samples n'est pas
>   expliqué par le code du bootstrap ; piste la plus simple `[HYP]` : l'OS Cycles a démarré mais a buté sur les
>   données laissées par l'OS Samples jusqu'à la réinitialisation du projet actif ;
> - le retour par USB depuis l'OS Samples sur un Cycles est donc **probablement possible** avec `--back`, suivi au
>   besoin d'un EMPTY RESET ou d'un FACTORY RESET. À confirmer sur la machine avant de l'offrir dans le flasher
>   (PR séparée) ;
> - la « variante MAIN OS seul » et les contrôles `LENGTH ERROR` / `CRC CHECK` (qui portent sur une section
>   décompressée de 61 440 octets au plus, pas sur le MAIN OS) ne changent rien à cela ;
> - la suite de cette section est gardée pour l'historique ; ses conclusions « porte 2 » et « pas de retour par
>   USB » sont fausses.

`[FAIT]` En désassemblant le chemin d'écriture de l'OS Samples (`0x40091488`, appelé par `0x4006bed6`) :
- après la vérification (§3.4, contrôle 3), l'updater **n'écrit pas** section par section à leur adresse : il copie tout le conteneur reçu dans une **zone de staging** (base flash `0x20000`, `0x4008fc50` par blocs), affiche « Writing Flash », puis **réinitialise le CPU** (`move.l #0, 0x48000000` ; `move.b #0x80, 0xec090000`, `0x40091570`).
- L'installation réelle se fait donc **au redémarrage, par le bootstrap**, qui lit le staging et le pose en flash.
- `[FAIT]` Le bootstrap (section 2) **porte sa propre matière de clé HMAC** : l'ancre SHA-256 `be f9 a3 f7…` et la chaîne de dérivation (`"REVERB SEND"` dans le bootstrap Cycles, `"DELAY TIME"` dans le Samples, offset `0x6664` des deux). Il **re-vérifie** donc la signature à l'installation.

Or l'état de la machine après l'aller est **hybride** ([§3.2](#32-la-route-de-flash--toolscrossflashpy-et-longlet-samples-os-fait-validée)) :

| Ce qui est en flash | Provenance | Clé de vérification |
|---|---|---|
| **bootstrap** (menu de démarrage, installeur) | **Cycles** (le conteneur de l'aller était un conteneur Cycles) | **`"REVERB SEND"` (Cycles)** |
| **MAIN OS** (ce qui tourne) | **Samples** | **`"DELAY TIME"` (Samples)** |

Une mise à jour USB traverse donc **deux portes à clés opposées** :
1. **l'OS Samples qui tourne** reçoit le SysEx et vérifie avec la **clé Samples**, puis met en staging ;
2. **le bootstrap Cycles**, au redémarrage, installe depuis le staging et vérifie avec la **clé Cycles**.

Un fichier ne porte **qu'un seul** trailer HMAC. Il ne peut pas satisfaire les deux clés à la fois :
- signé Samples (notre `--back`) → passe la porte 1, **rejeté à la porte 2** → la machine réinstalle l'ancien OS Samples. **C'est exactement ce qu'a vu l'utilisateur.**
- signé Cycles (le `.syx` officiel) → **rejeté dès la porte 1**, jamais mis en staging.

`[FAIT]` **La variante « MAIN OS seul » ne débloque rien** : un conteneur partiel emprunte le même chemin staging → reboot → bootstrap, donc bute sur la même porte 2. Pire, un conteneur fabriqué à la main a plus de chances de déclencher les contrôles de longueur/CRC du bootstrap (`LENGTH ERROR`, `CRC CHECK`, section 2), c'est-à-dire d'aller **vers** la zone risquée, pas loin d'elle.

**Pourquoi le MIDI, lui, marche.** Le menu de démarrage court-circuite l'OS : le SysEx arrive **directement au bootstrap** (récepteur du menu), une seule porte, une seule clé — la **clé Cycles**. Et le `.syx` officiel Cycles est signé Cycles. Correspondance parfaite, un seul étage, aucune ambiguïté. C'est pour ça que c'est la voie de secours fiable, et la seule dans cet état.

> Source : chemins d'écriture et de vérification des MAIN OS et bootstraps 1.13, désassemblés le 30/09/2026 (`tools/mtlib`, capstone ColdFire).

**Conclusion opérationnelle.** Depuis l'OS Samples installé sur un Cycles, **il n'y a pas de retour par USB**. Il faut une **interface USB-MIDI** (sortie DIN ou TRS, quelques euros ; le kit **CA-3** est déjà fourni avec la machine), reliée au **MIDI IN**, puis le menu de démarrage (FUNC + allumage, TRIG 4) et l'OS Cycles officiel ([FLASH §5](../FLASH.md#5-récupération-revenir-à-loriginal)). Détails et interfaces repérées : [12](12-flash-par-jack-trs.md).
La piste « sortie casque » (§3 de la note 12) resterait à défaut, mais elle est expérimentale et son outil `syx2wav.py` n'est pas écrit.

Le mode `tools/crossflash.py --back` **est conservé** (il documente le raisonnement et produit un fichier correct pour la porte 1), mais son aide dit clairement qu'il **ne suffit pas** au retour à cause de la porte 2.

> **Suite (05/10/2026)** : dans l'autre sens (OS Cycles sur un Model:Samples), l'OS Cycles d'origine refuse l'OS
> Samples officiel (signé Samples) ; en changeant 32 octets de l'OS Cycles, qui vérifie alors avec la clé du Samples,
> le retour par USB devient possible. Voir [41](41-os-cycles-sur-samples.md).

## 4. Machines numériques du Syntakt — 🟠 recherche, premiers résultats encourageants

**Demande** : porter les moteurs numériques supplémentaires du Syntakt, en partant de la ROM (l'OS) et d'un banc d'émulation pour la comprendre.
> Source : commentaire r/Elektron relayé par l'utilisateur.

**Ce qu'on savait** :
- Les machines numériques du Syntakt sont à base de FM et dérivées de celles du Model:Cycles ([14 §1](14-machine-sd-vintage.md)).
- SD VINTAGE ([14](14-machine-sd-vintage.md)) a été écrite en **clean-room** : l'OS du Syntakt n'était pas accessible depuis
  l'environnement de travail d'alors. Elle marche sur le matériel (29/09/2026).
- Le banc d'émulation du moteur du M:C (`tools/emu/`) tourne désormais aussi sur ton Mac.

### 4.1 Premier examen de l'OS Syntakt 1.41 (29/09/2026)

Téléchargé avec ton accord : `Syntakt-OS-1.41.zip`, 28 063 003 o, elektron.se. Jamais versionné.
Le zip contient `Syntakt_OS1.41.syx` (2 571 424 o), un pack de sons et Transfer.
> Source : page de téléchargements Syntakt d'elektron.se, consultée le 29/09/2026.

`[FAIT]` **Même transport, même conteneur** que les Models :
- SysEx Elektron, produit `0x16`, paquets de 128 octets.
- Constantes de checksum : `V = 0x35`, `C0 = 0x2C`, à compléter pour mtlib. Trouvées par recherche exhaustive, elles valident les 20 089 paquets.
- Particularité : **deux flux** de paquets (octet 7 = `0x00` puis `0x01`, le second avec `C0 - 1`). Mis bout à bout, ils forment **un seul conteneur ELE3** de 2 028 880 o.

`[FAIT]` 8 sections :

| id | Taille (décompressée) | Destination | Nature probable |
|---|---|---|---|
| 5 | 15 o | — | horodatage `260908 14:39:29` |
| 2 | 30 782 o | `0x04000000` | bootstrap (même en-tête `[taille][0x80010000]` que les Models) |
| 3 | **3 438 480 o** | `0x40000400` | **MAIN OS ColdFire**, même adresse et mêmes premiers octets que celui du Cycles |
| 4 | 32 776 o | `0x80000400` | updater |
| 1, 8 | 149 516 o, 159 948 o | — | données (commencent par des `0xFF`) `[À IDENTIFIER]` |
| 6 | 1 744 o | — | `[À IDENTIFIER]` |
| 7 | 383 760 o | — | **code et tables DSP** (voir ci-dessous) |

`[FAIT]` Le MAIN OS contient la liste des machines, avec un espace de noms `Diddy` (`machineType_t`, `synthParams_t`) :
`SD VINTAGE`, `CP VINTAGE`, `BD SHARP`, `BD SILKY`, `SD NATURAL`, `SY RAW`, `SY CHIP`, `SY DUAL VCO`, `CY RIDE`, `CB METALLIC`…
`SD VINTAGE` est à `0x402535c2`.

`[FAIT]` **Indice fort de parenté avec le moteur Cycles** :
- La **table de sinus Q31 de 257 points** du moteur FM du Cycles (`0x8000eee4` en SRAM) se retrouve **à l'identique** dans la section 7 du Syntakt (offset `0x53e54`).
- Les sections 3 et 7 règlent l'EMAC en mode fractionnaire `MACSR = 0xA0` (`move.l #0xa0,MACSR`), le mode de la boucle des voix du Cycles ([14 §2.3](14-machine-sd-vintage.md)).
- En revanche, aucune fonction du moteur Cycles ne s'y retrouve octet pour octet. Le code a été recompilé ou réécrit.

> Source : sections dépaquetées de `Syntakt_OS1.41.syx` le 29/09/2026 ; comparaison avec l'OS Cycles 1.13.

`[À FAIRE]` La clé HMAC du Syntakt n'est pas retrouvée par la méthode des Models. C'est sans importance ici : on ne reconstruit pas de firmware Syntakt, on ne fait que le lire.

### 4.2 Plan

1. `[À FAIRE]` Identifier la section 7 (chargée en SRAM comme les tables du Cycles ?) et trouver les tables de dispatch des machines numériques : `update` / `render`, comme `0x40118628` / `0x40118610` sur le Cycles.
2. `[À FAIRE]` Faire tourner la voix **SD VINTAGE** du Syntakt dans un banc d'émulation, sur le modèle de `tools/emu/mcengine.py` (même CPU, même EMAC, correctif EMAC déjà écrit). Mesurer son son : hauteur, balayage, bruit, enveloppes.
3. Comparer à notre SD VINTAGE clean-room, puis **caler nos constantes** sur les mesures. C'est la voie la plus sûre (aucun code Elektron copié).
4. Ensuite, les autres machines numériques une par une, en commençant par les plus demandées. Chacune d'abord à la place d'une machine existante, puis en 7ᵉ machine ([14 §8](14-machine-sd-vintage.md)).

**Règle de publication** : aucun code Elektron dans le dépôt, comme pour le reste du projet. Deux façons de porter :
- **Réécriture clean-room** (comme SD VINTAGE), réglée sur les mesures faites dans le banc : la plus sûre ;
- **Extraction au moment du build** depuis le fichier Syntakt que l'utilisateur fournit lui-même : le dépôt ne contiendrait que des adresses et des tables de patch.
  Techniquement plausible (même CPU, même EMAC, mêmes tables), mais la licence du firmware Syntakt n'autorise peut-être pas cet usage (non vérifié).
