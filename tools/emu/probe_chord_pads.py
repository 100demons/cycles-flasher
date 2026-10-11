#!/usr/bin/env python3
"""Sonde de recherche des pads de l'OS 1.13, pour le clavier d'accords (notes/42).

Exécute le vrai constructeur de PadEvent, PadsView::consumePadEvent et ses deux
relais de note. Vérifie T1 à T6, les notes mémorisées jusqu'au relâchement, TRACK
et RETRIG. Aucune modification du firmware : ce n'est pas une preuve du mod.

Interceptés : accès au projet/pattern et à leurs réglages, lecture des touches
modificatrices, verrous du contrôleur de vues, libération des références, demande
de sélection de piste et envoi des notes. Le contrôleur ne contient aucune vue
superposée ; le dispatch, les mutes, FILL, les menus, l'audio, le MIDI et le live
rec ne sont pas émulés. Les appels d'envoi sont observés avant leurs effets.

L'image officielle est vérifiée et décompressée en mémoire, jamais écrite.
Durée habituelle : moins d'une seconde après la décompression.

    python3 tools/emu/probe_chord_pads.py --cycles firmware/model-cycles_OS1.13.syx
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from unicorn import Uc, UcError, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn import m68k_const as mk

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
sys.path.insert(0, str(TOOLS))

from mtlib import aplib, container  # noqa: E402
from mtlib.syx import unwrap  # noqa: E402

BASE = 0x40000400
PAD_CTOR, PAD_CONSUMER = 0x40074072, 0x4001D180
VIEW, EVENT, CONTROLLER = 0x93000000, 0x93001000, 0x93002000
STOP, STACK = 0x9300F000, 0x9300E000
TRACK_DATA = 0x93103000


def official_image(path):
    """Refuse une autre version ou une image déjà modifiée, avant toute émulation."""
    device = json.loads((TOOLS.parent / "tweaks/model-cycles_OS1.13/device.json").read_text())
    syx = Path(path).read_bytes()
    if hashlib.sha256(syx).hexdigest() != device["stock_syx_sha256"]:
        raise ValueError("le fichier n'est pas le .syx officiel Model:Cycles OS 1.13")
    stream, _ = unwrap(syx)
    parsed = container.parse(stream)
    section = next(s for s in parsed["sections"] if s["id"] == 3)
    image, _ = aplib.depack(parsed["blob"][section["off"]:section["off"] + section["size"]])
    if len(image) != device["section_len"] or hashlib.sha256(image).hexdigest() != device["section_sha256"]:
        raise ValueError("la section 3 ne correspond pas au MAIN OS 1.13 officiel")
    return image


class Rig:
    """PadsView réel, six pistes factices, sans vue superposée au contrôleur."""

    def __init__(self, image):
        self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        self.uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
        self.uc.reg_write(mk.UC_M68K_REG_SR, 0x2700)
        self.uc.mem_map(0x40000000, 0x02400000)
        self.uc.mem_write(BASE, image)
        self.uc.mem_map(0x90000000, 0x04000000)
        self.uc.mem_write(STOP, b"\x4e\x71")
        self.bad, self.calls = [], []
        self.notes = [60 + track for track in range(6)]
        self.pressed = set()
        self.rate = 7
        self.fixed_velocity = None
        self.uc.hook_add(UC_HOOK_MEM_UNMAPPED, self._unmapped)
        self.w32(VIEW + 44, CONTROLLER)
        self.w32(CONTROLLER + 20, CONTROLLER + 20)  # liste vide de vues
        for track in range(6):
            self.w32(VIEW + 88 + 4 * track, -1)
        stubs = {
            0x400CF866: lambda a: 0x93100000,       # racine du projet
            0x4000EB90: lambda a: 0x93101000,       # état du projet
            0x40013464: lambda a: int(self.fixed_velocity is not None),
            0x4001351E: lambda a: self.fixed_velocity or 0,
            0x4000F208: lambda a: 0x93102000,       # kit/pattern
            0x4000CFCC: lambda a: TRACK_DATA + 256 * a[1],
            0x40015A34: lambda a: self.notes[(a[0] - TRACK_DATA) // 256],
            0x4007FAF4: lambda a: int(a[0] in self.pressed),
            0x4000D0DC: lambda a: 0x93104000,       # réglages de retrig du kit
            0x4000CCC0: lambda a: 0,                # A.On désactivé
            0x40016086: lambda a: self.rate,
            0x40001D2C: lambda a: 0,                # verrou du contrôleur
            0x40001E4E: lambda a: 0,                # déverrouillage
            0x400CF23C: lambda a: 0,                # référence partagée vide
            0x40023C90: self._capture("select", 1),
            0x4008171E: self._capture("on", 7),
            0x4008145E: self._capture("off", 3),
            0x40016E90: lambda a: 0,                # sortie MIDI de piste désactivée
        }
        for address, handler in stubs.items():
            self.uc.hook_add(UC_HOOK_CODE, self._stub(handler), begin=address, end=address)

    def _unmapped(self, uc, access, address, size, value, user):
        self.bad.append(address)
        return False

    def _capture(self, name, count):
        def handler(args):
            self.calls.append((name, args[:count]))
            return 0
        return handler

    def _stub(self, handler):
        def hook(uc, address, size, user):
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            args = struct.unpack(">8I", uc.mem_read(sp + 4, 32))
            uc.reg_write(mk.UC_M68K_REG_D0, handler(args) & 0xFFFFFFFF)
            uc.reg_write(mk.UC_M68K_REG_PC, self.r32(sp))
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        return hook

    def w32(self, address, value):
        self.uc.mem_write(address, struct.pack(">I", value & 0xFFFFFFFF))

    def r32(self, address):
        return struct.unpack(">I", self.uc.mem_read(address, 4))[0]

    def held(self, pad):
        return self.r32(VIEW + 88 + 4 * (pad - 1))

    def call(self, address, *args):
        self.uc.mem_write(STACK, struct.pack(">I" + "I" * len(args), STOP, *args))
        self.uc.reg_write(mk.UC_M68K_REG_A7, STACK)
        self.uc.emu_start(address, STOP, count=100_000)
        if self.uc.reg_read(mk.UC_M68K_REG_PC) != STOP:
            raise RuntimeError(f"budget d'instructions dépassé à {address:#x}")
        if self.bad:
            raise RuntimeError(f"accès hors mémoire : {self.bad!r}")
        return self.uc.reg_read(mk.UC_M68K_REG_D0)

    def event(self, pad, down, velocity=100):
        self.calls.clear()
        self.call(PAD_CTOR, EVENT, pad, int(down), velocity, 123, 0)
        return self.call(PAD_CONSUMER, VIEW, EVENT)


def probe(image):
    failures = []

    def check(ok, message):
        print(f"{'ok' if ok else 'FAIL'} {message}", flush=True)
        if not ok:
            failures.append(message)

    rig = Rig(image)
    check(rig.r32(0x4010025C) == PAD_CONSUMER,
          "la vtable de PadsView désigne bien le gestionnaire étudié")
    for pad in range(1, 7):
        track, note, velocity = pad - 1, 59 + pad, 80 + pad
        consumed = rig.event(pad, True, velocity)
        fields = struct.unpack(">5I", rig.uc.mem_read(EVENT + 8, 20))
        check(fields == (123, 1, 1, pad, velocity),
              f"T{pad} : vrai constructeur, PadEvent horodaté, source pad, appui, numéro et vélocité")
        expected = [("select", (track,)), ("on", (track, note, velocity, 64, 0, 0xFFFFFFFF, 0xFFFFFFFF))]
        check(consumed == 1 and rig.calls == expected and rig.held(pad) == note,
              f"T{pad} : demande la piste {track + 1}, joue sa note {note}, garde cette note")
        rig.notes[track] = 90  # le relâchement doit utiliser la note gardée
        consumed = rig.event(pad, False)
        check(consumed == 1 and rig.calls == [("off", (track, note, 64))] and rig.held(pad) == 0xFFFFFFFF,
              f"T{pad} : relâche la note mémorisée malgré le réglage changé, puis vide sa case")
        rig.event(pad, False)
        check(not rig.calls, f"T{pad} : un second relâchement n'envoie aucune autre fin de note")
        rig.notes[track] = note

    rig.event(1, True)
    rig.event(6, True)
    check(rig.held(1) == 60 and rig.held(6) == 65, "T1 et T6 : deux notes tenues dans des cases distinctes")
    rig.event(1, False)
    check(rig.calls == [("off", (0, 60, 64))] and rig.held(6) == 65,
          "relâcher T1 après T6 garde la note mémorisée de T6")
    rig.event(6, False)

    rig.pressed = {2}  # TRACK : le consommateur lit ce modificateur
    rig.event(3, True)
    check(rig.calls == [("select", (2,))] and rig.held(3) == 0xFFFFFFFF,
          "TRACK + T3 : demande la sélection sans envoyer de note")
    rig.event(3, False)
    check(not rig.calls, "TRACK + T3 : le relâchement n'envoie aucune fin de note")

    rig.pressed = {4}  # RETRIG
    rig.event(2, True)
    check(rig.calls == [("select", (1,)), ("on", (1, 61, 100, 64, 0, 0xFFFFFFFF, rig.rate))],
          "RETRIG + T2 : transmet la vitesse de retrig de la piste")
    rig.pressed.clear()
    rig.event(2, False)
    check(rig.calls == [("off", (1, 61, 64))], "RETRIG relâché avant T2 : fin de note correspondante")
    check(not rig.bad, "aucun accès hors des zones de mémoire du banc")
    return bool(failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cycles", required=True, help=".syx officiel Model:Cycles OS 1.13")
    args = parser.parse_args()
    try:
        image = official_image(args.cycles)
        print("ok SHA-256 du .syx officiel et de sa section 3", flush=True)
        return probe(image)
    except (OSError, ValueError, RuntimeError, UcError) as exc:
        print(f"FAIL {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
