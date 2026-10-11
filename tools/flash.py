#!/usr/bin/env python3
"""Envoie un firmware .syx au Model:Cycles (ou Model:Samples) par son entrée MIDI IN.

Par défaut : essai à blanc (rien n'est envoyé). Ajoute --send pour transmettre.
L'appareil doit être dans le STARTUP MENU en mode OS UPGRADE :
    éteindre → maintenir [FUNC] → allumer → [TRIG 4] (OS UPGRADE)

⚠️ L'upgrade par le STARTUP MENU ne fonctionne QUE par l'entrée MIDI IN de
l'appareil (jack TRS 3,5 mm), pas par son port USB. Il faut une interface MIDI
dont la sortie est reliée à ce MIDI IN : sortie TRS + câble jack stéréo, ou
sortie DIN + adaptateur TRS -> DIN fourni avec l'appareil.

Vérifie le fichier avant l'envoi : identifiant fabricant/produit, chaque
checksum de paquet SysEx (via mtlib). Refuse d'envoyer un fichier douteux.

    python3 tools/flash.py --list
    python3 tools/flash.py mon.syx --verify
    python3 tools/flash.py mon.syx --port "USB MIDI" --send

Adapté du tools/flash.py de ms-multi-output (https://github.com/scottmetoyer/ms-multi-output),
Copyright (c) 2026 Scott Metoyer, licence MIT : tweaks/model-cycles_OS1.13/LICENSE-ms-multi-output.
"""
import argparse
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ELEKTRON = (0x00, 0x20, 0x3C)
PRODUCTS = {0x0F: "Model:Samples", 0x11: "Model:Cycles", 0x05: "Octatrack",
            0x0A: "Digitakt", 0x0D: "Digitone"}
DIN_BYTES_PER_SEC = 31250 / 10          # 8N1 sur le fil MIDI
DEFAULT_PACE = 1.4


def split_sysex(raw):
    """Découpe un .syx en messages F0..F7."""
    msgs, i = [], 0
    while True:
        a = raw.find(b"\xf0", i)
        if a < 0:
            break
        b = raw.find(b"\xf7", a)
        if b < 0:
            raise SystemExit(f"!! SysEx non terminé à l'offset {a}")
        msgs.append(raw[a:b + 1])
        i = b + 1
    return msgs


def verify(raw, path):
    """Contrôle le fichier avec mtlib (identifiant + tous les checksums). Renvoie le device id."""
    msgs = split_sysex(raw)
    if len(msgs) < 3:
        raise SystemExit("!! pas un .syx Elektron (trop peu de messages)")
    head = msgs[0]
    if tuple(head[1:4]) != ELEKTRON:
        raise SystemExit(f"!! pas un SysEx Elektron : en-tête {head[1:5].hex(' ')}")
    dev = head[4]
    name = PRODUCTS.get(dev, "inconnu")
    print(f"fichier        : {path}")
    print(f"  octets       : {len(raw):,}")
    print(f"  messages     : {len(msgs):,}")
    print(f"  fabricant    : Elektron (00 20 3c)")
    print(f"  produit      : 0x{dev:02x} ({name})")
    # vérification profonde via mtlib : chaque checksum de paquet + structure
    try:
        from mtlib.syx import unwrap
        from mtlib import container
        stream, info = unwrap(raw)          # lève une erreur si un checksum est faux
        c = container.parse(stream)
        print(f"  conteneur    : {c['version']}, {len(c['sections'])} sections  [checksums OK]")
    except ImportError:
        print("  (mtlib absent : vérification structurelle complète ignorée)")
    except Exception as e:
        raise SystemExit(f"!! le fichier ne se vérifie pas : {e}\n"
                         "   NE PAS le flasher — reconstruis-le avec tools/build.py")
    wire = len(raw) / DIN_BYTES_PER_SEC
    print(f"  durée fil     : ~{wire/60:.1f} min à la vitesse MIDI (plancher)")
    return dev, name


def list_ports():
    import mido
    try:
        outs = mido.get_output_names()
    except Exception as e:
        raise SystemExit(f"!! backend MIDI indisponible ({e}).\n"
                         "   Installe python-rtmidi (les scripts flash.sh / flash.bat le font).")
    return outs


def pick_port(outs, want):
    if not want:
        return None
    m = [p for p in outs if want.lower() in p.lower()]
    if len(m) == 1:
        return m[0]
    if not m:
        raise SystemExit(f"!! aucun port ne contient {want!r}. Ports : {outs}")
    raise SystemExit(f"!! {want!r} correspond à plusieurs ports : {m}\n   précise davantage.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("syx", nargs="?", help="le fichier .syx à envoyer")
    ap.add_argument("-p", "--port", help="port MIDI de sortie (sous-chaîne suffit)")
    ap.add_argument("--list", action="store_true", help="liste les ports MIDI de sortie")
    ap.add_argument("--verify", action="store_true", help="vérifie le fichier sans rien envoyer")
    ap.add_argument("--send", action="store_true", help="envoie réellement (sinon essai à blanc)")
    ap.add_argument("--pace", type=float, default=DEFAULT_PACE,
                    help=f"marge de cadence (défaut {DEFAULT_PACE} ; augmente si l'appareil se fige)")
    ap.add_argument("--yes", action="store_true", help="ne pas demander de confirmation avant l'envoi")
    args = ap.parse_args()

    if args.list:
        for p in list_ports():
            print("   ", p)
        return
    if not args.syx:
        ap.print_help()
        return

    raw = pathlib.Path(args.syx).read_bytes()
    dev, name = verify(raw, args.syx)
    if args.verify:
        print("\n✅ Vérification OK.")
        return

    outs = list_ports()
    if not outs:
        raise SystemExit("!! aucun port MIDI de sortie détecté. Branche ton interface MIDI USB.")
    port = pick_port(outs, args.port)
    if not port:
        print("\nPorts MIDI de sortie disponibles :")
        for i, p in enumerate(outs, 1):
            print(f"   {i}. {p}")
        print("Choisis le port de TON INTERFACE MIDI (pas le port USB de l'appareil).")
        if not args.send:
            raise SystemExit("\n(Essai à blanc : relance avec --send, ou passe --port.)")
        try:
            sel = input("Numéro du port : ").strip()
            port = outs[int(sel) - 1]
        except (ValueError, IndexError, EOFError):
            raise SystemExit("Choix invalide.")
    print(f"  port         : {port}")

    # garde-fou : le port USB propre de l'appareil ne marche PAS en STARTUP MENU
    low = port.lower()
    if "model:cycles" in low or "model:samples" in low or "model cycles" in low:
        print("\n!! Ce port est le port USB de l'appareil lui-même.")
        print("   Le STARTUP MENU n'accepte l'upgrade QUE par son entrée MIDI IN (jack TRS).")
        print("   Branche une interface MIDI (sa sortie -> MIDI IN de l'appareil) et choisis SON port.")
        if args.send:
            raise SystemExit("   Envoi refusé sur le port USB de l'appareil.")

    if not args.send:
        print("\nESSAI À BLANC — rien n'a été envoyé.")
        print("Quand l'appareil affiche « READY TO RECEIVE » (STARTUP MENU → OS UPGRADE),")
        print("relance avec --send.")
        return

    print("\n  Sur l'appareil : éteindre, maintenir [FUNC], allumer, [TRIG 4] (OS UPGRADE).")
    print("  L'écran doit afficher « READY TO RECEIVE ».")
    if not args.yes:
        r = input("  Prêt à envoyer ? Tape OUI pour continuer : ").strip().lower()
        if r not in ("oui", "o", "yes", "y"):
            raise SystemExit("  Annulé.")

    import mido
    msgs = split_sysex(raw)
    print("\n  Envoi. NE PAS éteindre, surtout quand l'écran indique « UPDATING FLASH ».", flush=True)
    print("  Surveille l'écran : il doit passer de READY TO RECEIVE à RECEIVING… en quelques secondes.")
    print("  S'il reste sur READY TO RECEIVE, l'image est ignorée (mauvais port ou mauvais appareil).",
          flush=True)
    t0 = time.monotonic()
    with mido.open_output(port) as out:
        for n, m in enumerate(msgs, 1):
            out.send(mido.Message("sysex", data=m[1:-1]))
            time.sleep(args.pace * len(m) / DIN_BYTES_PER_SEC)
            if n % 250 == 0 or n == len(msgs):
                el = time.monotonic() - t0
                print(f"    {n:>6,}/{len(msgs):,}  {100*n/len(msgs):5.1f}%  {el:6.0f}s", flush=True)
    print(f"\n  Terminé en {time.monotonic()-t0:.0f}s. Attends la fin de « UPDATING FLASH » "
          "et le redémarrage.")
    print("  Si l'appareil reste bloqué sur RECEIVING… : un paquet a été perdu (sans danger) —")
    print(f"  éteins/rallume, re-entre en OS UPGRADE, et relance avec --pace {args.pace+0.6:.1f}.")


if __name__ == "__main__":
    main()
