#!/usr/bin/env python3
"""Sonde de recherche du moteur CHORD de l'OS officiel 1.13 (notes/42).

Exécute son vrai update dans Unicorn : catalogue SHAPE, rapports de fréquence,
gains des opérateurs. L'option --inject-intervals remplace uniquement des valeurs
dans la RAM émulée entre le choix des intervalles et le calcul des fréquences.
Elle examine les douze neuvièmes diatoniques de do majeur, à quatre notes.

Ce n'est PAS une preuve d'un mod : aucun crochet ColdFire, pad, menu, sauvegarde,
enregistrement ou rendu audio n'est testé ici. Aucun firmware n'est exporté.
L'image officielle reste inchangée. Durée habituelle : quelques secondes.
La plage MIDI 0..127 du noyau C décrit des notes abstraites : elle ne garantit
pas leur jouabilité par CHORD, qui borne la fondamentale et coupe des voix aiguës.

    python3 tools/emu/probe_chord_keys.py --cycles firmware/model-cycles_OS1.13.syx
    python3 tools/emu/probe_chord_keys.py --cycles firmware/model-cycles_OS1.13.syx --inject-intervals

Nécessite unicorn, numpy et m68k-linux-gnu-objdump, comme mcengine.py. Sur le Mac
de développement, Unicorn 2.1.4 doit s'exécuter hors du sandbox : son initialisation
de mémoire peut sinon recevoir SIGILL avant d'exécuter la moindre instruction OS.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as mk

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

import mcengine as E  # noqa: E402
from mtlib import aplib, container  # noqa: E402
from mtlib.syx import unwrap  # noqa: E402

UPDATE = 0x400aae88
AFTER_INTERVALS = 0x400ab158
RATIO_TABLE = 0x4012142c
RATIO_OFFSET = 0x50
PHASE_OFFSET = 0x70
OPERATOR_STRIDE = 0x78
Q26 = 1 << 26

# Noms du manuel, intervalles musicaux vérifiés dans le moteur ; aucun octet
# Elektron recopié. Les trois unissons (0..2) utilisent d'autres tables.
CHORDS = (
    ("minor", (0, 3, 7, 12)), ("Major", (0, 4, 7, 12)),
    ("sus2", (0, 2, 7, 12)), ("sus4", (0, 5, 7, 12)),
    ("m7", (0, 3, 7, 10)), ("M7", (0, 4, 7, 10)),
    ("mMaj7", (0, 3, 7, 11)), ("Maj7", (0, 4, 7, 11)),
    ("7sus4", (0, 5, 7, 10)), ("dim7", (0, 3, 6, 9)),
    ("madd9", (0, 3, 7, 14)), ("Madd9", (0, 4, 7, 14)),
    ("m6", (0, 3, 7, 9)), ("M6", (0, 4, 7, 9)),
    ("mb5", (0, 3, 6, 12)), ("Mb5", (0, 4, 6, 12)),
    ("m7b5", (0, 3, 6, 10)), ("M7b5", (0, 4, 6, 10)),
    ("M#5", (0, 4, 8, 12)), ("m7#5", (0, 3, 8, 10)),
    ("M7#5", (0, 4, 8, 10)), ("mb6", (0, 3, 7, 8)),
    ("m9no5", (0, 3, 10, 14)), ("M9no5", (0, 4, 10, 14)),
    ("Madd9b5", (0, 4, 6, 14)), ("Maj7b5", (0, 4, 6, 11)),
    ("M7b9no5", (0, 4, 10, 13)), ("sus4#5b9", (0, 1, 5, 8)),
    ("sus4add#5", (0, 5, 7, 8)), ("Maddb5", (0, 4, 6, 7)),
    ("M6add4no5", (0, 4, 5, 9)), ("Maj7/6no5", (0, 4, 9, 11)),
    ("Maj9no5", (0, 4, 11, 14)), ("Fourths", (0, 5, 12, 17)),
    ("Fifths", (0, 7, 12, 19)),
)


def frequency_ratios(intervals):
    """Rapports calculés indépendamment des octets de l'OS : tempérament égal."""
    return tuple(round(Q26 * 2 ** (n / 12)) for n in intervals)


def load_stock(path):
    device = json.loads((HERE.parent.parent / "tweaks/model-cycles_OS1.13/device.json").read_text())
    syx = path.read_bytes()
    if hashlib.sha256(syx).hexdigest() != device["stock_syx_sha256"]:
        raise ValueError("Le fichier n'est pas le .syx officiel Model:Cycles OS 1.13 attendu.")
    stream, _ = unwrap(syx)
    parsed = container.parse(stream)
    section = next(s for s in parsed["sections"] if s["id"] == 3)
    main_os = aplib.depack(parsed["blob"][section["off"]:section["off"] + section["size"]])[0]
    if len(main_os) != device["section_len"] or hashlib.sha256(main_os).hexdigest() != device["section_sha256"]:
        raise ValueError("L'empreinte de la section MAIN OS ne correspond pas au stock attendu.")
    return main_os


class Probe:
    def __init__(self, main_os):
        self.engine = E.Engine(main_os)
        self.voice = E.VOICE0
        self.params = E.PARAMS + 0xe
        self.pending = None
        self.failures = 0
        self.engine.uc.hook_add(UC_HOOK_CODE, self.inject, begin=AFTER_INTERVALS, end=AFTER_INTERVALS)

    def inject(self, uc, address, size, userdata):
        """Instrumentation Python du laboratoire, pas du code destiné au firmware."""
        if self.pending is not None:
            for i, ratio in enumerate(self.pending):
                uc.mem_write(self.voice + RATIO_OFFSET + i * OPERATOR_STRIDE, struct.pack(">I", ratio))

    def update(self, root=60, shape=7, color=32, intervals=None):
        e = self.engine
        e.machine_defaults(0, "CHORD")
        e.set(0, note=root, pitch=64, finetune=64, shape=shape, color=color)
        e._write_params()
        self.pending = frequency_ratios(intervals) if intervals is not None else None
        e.emac.macsr = 0xa0  # Le vrai appelant règle ce mode EMAC avant les update.
        try:
            e.call(UPDATE, root << 16, self.voice, self.params)
        finally:
            self.pending = None
        if e.uc.reg_read(mk.UC_M68K_REG_PC) != E.STOP:
            raise RuntimeError("L'update CHORD n'a pas terminé dans le budget d'instructions.")
        ratios = tuple(self.word(RATIO_OFFSET + i * OPERATOR_STRIDE) for i in range(4))
        phases = tuple(self.word(PHASE_OFFSET + i * OPERATOR_STRIDE) for i in range(4))
        gains = tuple(self.word(12 + 4 * i) for i in range(3))
        return ratios, phases, gains

    def word(self, offset):
        return int.from_bytes(self.engine.uc.mem_read(self.voice + offset, 4), "big", signed=True)

    def check(self, ok, message):
        print(("ok    " if ok else "FAIL  ") + message, flush=True)
        self.failures += not ok

    def stock(self, main_os):
        for shape, (name, intervals) in enumerate(CHORDS, 3):
            expected = frequency_ratios(intervals)
            table = struct.unpack_from(">4I", main_os, RATIO_TABLE - E.BASE + 16 * shape)
            actual, _, _ = self.update(shape=shape)
            self.check(table == expected and actual == expected,
                       f"stock SHAPE {shape:2d} {name:13s} : intervalles {intervals}, COLOR 32")
        _, _, triad_gains = self.update(shape=4)
        _, _, seventh_gains = self.update(shape=7)
        self.check(triad_gains[-1] == 0 and all(g > 0 for g in seventh_gains),
                   "Major coupe le 4e opérateur ; m7 / COLOR 32 garde les trois gains supérieurs positifs")
        for shape in (38, 43, 127):
            actual, _, gains = self.update(shape=shape)
            self.check(actual == frequency_ratios(CHORDS[-1][1]) and gains[-1] == 0,
                       f"stock SHAPE {shape} : rapports bornés sur Fifths, 4e opérateur coupé")
        high = {root: self.update(root=root) for root in (96, 97, 108, 127)}
        self.check(all(result[1][0] == high[96][1][0] for result in high.values()),
                   "stock : fondamentales 96/97/108/127, même incrément de phase avec Pitch 64 / Fine 64")
        self.check(all(not any(result[2]) for result in high.values()),
                   "stock : m7 / COLOR 32, les trois gains supérieurs sont nuls pour ces fondamentales aiguës")

    def injected_ninths(self):
        scale = (0, 2, 4, 5, 7, 9, 11)

        def note(degree):
            return 60 + 12 * (degree // 7) + scale[degree % 7]

        untouched = bytes(self.engine.uc.mem_read(self.voice + E.VSTRIDE, 5 * E.VSTRIDE))
        worst_cents = 0.0
        for degree in range(12):
            # Fondamentale, tierce, septième, neuvième de la gamme ; quinte omise.
            notes = tuple(note(degree + d) for d in (0, 2, 6, 8))
            intervals = tuple(n - notes[0] for n in notes)
            ratios, phases, gains = self.update(root=notes[0], intervals=intervals)
            references = tuple(self.update(root=n)[1][0] for n in notes)
            error = max(abs(1200 * math.log2(got / ref)) for got, ref in zip(phases, references))
            worst_cents = max(worst_cents, error)
            self.check(ratios == frequency_ratios(intervals) and all(g > 0 for g in gains) and error < 0.6,
                       f"RAM instrumentée, case {degree + 1:2d} : notes MIDI {notes}, "
                       f"4e opérateur actif, écart vs fondamentales stock {error:.3f} cent")
        self.check(bytes(self.engine.uc.mem_read(self.voice + E.VSTRIDE, 5 * E.VSTRIDE)) == untouched,
                   "Les cinq autres états de voix restent inchangés")
        print(f"Écart maximal aux notes stock : {worst_cents:.3f} cent (table exponentielle stock quantifiée).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=Path, required=True, help="OS officiel Model:Cycles 1.13")
    parser.add_argument("--inject-intervals", action="store_true", help="instrumenter la RAM émulée, sans produire de mod")
    args = parser.parse_args()
    main_os = load_stock(args.cycles)
    print("Sonde de recherche CHORD — OS officiel vérifié ; aucun firmware produit.")
    probe = Probe(main_os)
    probe.stock(main_os)
    if args.inject_intervals:
        probe.injected_ninths()
    probe.check(not probe.engine.unmapped, "Aucun accès mémoire hors des zones émulées")
    print("Limites : update seul ; aucun rendu audio, pad, menu, enregistrement ou test matériel.")
    print("MIDI 0..127 dans le noyau C est une plage abstraite ; la tessiture jouable complète reste à établir.")
    return 1 if probe.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
