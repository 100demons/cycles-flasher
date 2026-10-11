#!/usr/bin/env python3
"""Vérifie le noyau C chord-keys sur l'hôte, sans firmware ni émulation.

Compilation temporaire par cc, chargement via ctypes ; bibliothèque standard
uniquement. Le test vérifie le calcul harmonique, pas le DSP, les boutons ou
l'intégration au Model:Cycles. Exécution : python3 tools/test_chord_keys.py
"""

import ctypes as ct
import itertools
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile


OK, INVALID_ARGUMENT, NOTE_RANGE = range(3)
TRIAD, SEVENTH, NINTH, ELEVENTH, THIRTEENTH = range(5)
DEGREES = (0, 1, 2, 3, 4, 5, 6, 0, 1, 2, 3, 4, 5, 6, 0, 1)
OCTAVES = (0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 2, 2)


class Config(ct.Structure):
    _fields_ = [("root", ct.c_int), ("mode", ct.c_int),
                ("extensions", ct.c_int * 7)]


class Result(ct.Structure):
    _fields_ = [("degree", ct.c_int), ("slot", ct.c_int),
                ("octave", ct.c_int), ("count", ct.c_int),
                ("notes", ct.c_int * 4), ("offsets", ct.c_int * 4)]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def config(root=60, mode=0, extension=TRIAD):
    return Config(root, mode, (ct.c_int * 7)(*([extension] * 7)))


def poisoned_result():
    result = Result()
    ct.memset(ct.byref(result), 0xA5, ct.sizeof(result))
    return result


def call(build, settings, slot):
    result = poisoned_result()
    before = bytes(result)
    status = build(ct.byref(settings), slot, ct.byref(result))
    if status != OK:
        require(bytes(result) == before, "Résultat modifié malgré un refus")
    return status, result


def notes_of(build, settings, slot):
    status, result = call(build, settings, slot)
    require(status == OK, f"Accord refusé : slot {slot}, statut {status}")
    return list(result.notes[:result.count])


def concrete_chords(build):
    triads = [
        [60, 64, 67], [62, 65, 69], [64, 67, 71], [65, 69, 72],
        [67, 71, 74], [69, 72, 76], [71, 74, 77], [72, 76, 79],
        [74, 77, 81], [76, 79, 83], [77, 81, 84], [79, 83, 86],
        [81, 84, 88], [83, 86, 89], [84, 88, 91], [86, 89, 93],
    ]
    sevenths = [
        [60, 64, 67, 71], [62, 65, 69, 72], [64, 67, 71, 74],
        [65, 69, 72, 76], [67, 71, 74, 77], [69, 72, 76, 79],
        [71, 74, 77, 81], [72, 76, 79, 83], [74, 77, 81, 84],
        [76, 79, 83, 86], [77, 81, 84, 88], [79, 83, 86, 89],
        [81, 84, 88, 91], [83, 86, 89, 93], [84, 88, 91, 95],
        [86, 89, 93, 96],
    ]
    for extension, expected in ((TRIAD, triads), (SEVENTH, sevenths)):
        settings = config(extension=extension)
        for slot, chord in enumerate(expected):
            require(notes_of(build, settings, slot) == chord,
                    f"Do majeur : extension {extension}, slot {slot}")
    # TRIG 7 atteint VII ; TRIG 8 reprend I une octave plus haut.
    require(notes_of(build, config(), 6)[0] == 71
            and notes_of(build, config(), 7)[0] == 72, "Frontière VII/I")


def diatonic_extensions(build):
    examples = [
        (config(extension=NINTH), 0, [60, 64, 71, 74]),
        (config(extension=ELEVENTH), 0, [60, 64, 71, 77]),
        (config(extension=THIRTEENTH), 0, [60, 64, 71, 81]),
        (config(root=64, mode=2, extension=NINTH), 0, [64, 67, 74, 77]),
        (config(extension=NINTH), 2, [64, 67, 74, 77]),
        (config(extension=NINTH), 6, [71, 74, 81, 84]),
    ]
    for settings, slot, expected in examples:
        require(notes_of(build, settings, slot) == expected,
                f"Extension diatonique : mode {settings.mode}, slot {slot}")


def independent_settings(build):
    baseline = [notes_of(build, config(), slot) for slot in range(16)]
    for degree in range(7):
        settings = config()
        settings.extensions[degree] = THIRTEENTH
        for slot in range(16):
            actual = notes_of(build, settings, slot)
            require((actual != baseline[slot]) == (DEGREES[slot] == degree),
                    f"Le réglage du degré {degree} affecte la mauvaise touche {slot}")
    settings = config()
    settings.extensions[:] = [TRIAD, SEVENTH, NINTH, ELEVENTH,
                              THIRTEENTH, NINTH, SEVENTH]
    for degree in range(9):
        lower = notes_of(build, settings, degree)
        upper = notes_of(build, settings, degree + 7)
        require(upper == [note + 12 for note in lower],
                f"Extension non partagée à l'octave : degré {degree}")


def invalid_arguments(build):
    def refused(settings, key=0):
        result = poisoned_result()
        before = bytes(result)
        source = None if settings is None else ct.byref(settings)
        status = build(source, key, ct.byref(result))
        require(status == INVALID_ARGUMENT, "Argument invalide accepté")
        require(bytes(result) == before, "Refus d'argument avec résultat modifié")

    for value in (-2147483648, -1, 16, 2147483647):
        refused(config(), key=value)
    for value in (-2147483648, -1, 7, 2147483647):
        refused(config(mode=value))
    for value in (-2147483648, -1, 128, 2147483647):
        refused(config(root=value))
    for degree in range(7):
        for value in (-2147483648, -1, 5, 2147483647):
            settings = config()
            settings.extensions[degree] = value
            refused(settings)  # Valide aussi les degrés que la touche n'utilise pas.
    refused(None)
    settings = config()
    before = bytes(settings)
    require(build(ct.byref(settings), 0, None) == INVALID_ARGUMENT,
            "Pointeur de sortie nul accepté")
    require(bytes(settings) == before, "Configuration modifiée")
    require(build(None, 0, None) == INVALID_ARGUMENT, "Deux pointeurs nuls")


def modal_walk(mode):
    """Dérive les modes par rotation des pas majeurs, sans table du noyau C."""
    major_steps = (2, 2, 1, 2, 2, 2, 1)
    steps = major_steps[mode:] + major_steps[:mode]
    walk = [0]
    for step in itertools.islice(itertools.cycle(steps), 15):
        walk.append(walk[-1] + step)
    return walk, set(walk[:7])


def midi_boundaries(build):
    for mode, extension, slot in itertools.product(range(7), range(5), range(16)):
        base = notes_of(build, config(root=0, mode=mode, extension=extension), slot)
        # Propriété de transposition : dernière voix exactement à 127, puis 128.
        last_root = 127 - base[-1]
        settings = config(root=last_root, mode=mode, extension=extension)
        require(notes_of(build, settings, slot) == [n + last_root for n in base],
                "Accord modifié à la frontière MIDI 127")
        settings.root += 1
        status, _ = call(build, settings, slot)
        require(status == NOTE_RANGE, "Débordement MIDI écrêté ou accepté")


def exhaustive_properties(build):
    cases = 0
    for mode in range(7):
        walk, pitch_classes = modal_walk(mode)
        for extension in range(5):
            settings = config(root=0, mode=mode, extension=extension)
            baseline = [notes_of(build, settings, slot) for slot in range(16)]
            for root in range(128):
                settings.root = root
                before_config = bytes(settings)
                for slot in range(16):
                    cases += 1
                    status, result = call(build, settings, slot)
                    expected = [note + root for note in baseline[slot]]
                    require(bytes(settings) == before_config, "Entrée modifiée")
                    if expected[-1] > 127:
                        require(status == NOTE_RANGE, "Débordement non refusé")
                        continue
                    require(status == OK, "Accord valide refusé")
                    notes = list(result.notes[:result.count])
                    require(notes == expected, "Transposition incohérente")
                    require(result.count == (3 if extension == TRIAD else 4),
                            "Nombre de voix incorrect")
                    require(result.slot == slot and result.degree == DEGREES[slot]
                            and result.octave == OCTAVES[slot], "Position incorrecte")
                    require(notes[0] == root + walk[slot], "Fondamentale incorrecte")
                    require(all((note - root) % 12 in pitch_classes for note in notes),
                            "Note hors gamme")
                    require(all(0 <= note <= 127 for note in notes)
                            and all(a < b for a, b in zip(notes, notes[1:])),
                            "Voicing hors limites ou non croissant")
                    require(list(result.offsets[:result.count])
                            == [note - notes[0] for note in notes], "Écarts incohérents")
                    require(all(v == 0 for v in result.notes[result.count:])
                            and all(v == 0 for v in result.offsets[result.count:]),
                            "Cases inutilisées non nulles")
                    if slot >= 7:
                        lower = notes_of(build, settings, slot - 7)
                        require(notes == [note + 12 for note in lower],
                                "Degré non conservé à l'octave")
    require(cases == 71680, f"Balayage incomplet : {cases} cas")


def main():
    source = Path(__file__).resolve().parent / "machines/chord_keys/chord_keys.c"
    families = [
        ("triades et septièmes en do majeur, 16 touches TRIG", concrete_chords),
        ("extensions diatoniques, dont les neuvièmes mineures", diatonic_extensions),
        ("réglages indépendants et partagés à l'octave", independent_settings),
        ("arguments invalides, pointeurs nuls, sortie intacte", invalid_arguments),
        ("560 frontières MIDI 127/128, aucun écrêtage", midi_boundaries),
        ("71 680 cas : modes, transpositions, voix et octaves", exhaustive_properties),
    ]
    with tempfile.TemporaryDirectory(prefix="chord-keys-test-") as temporary:
        library_path = Path(temporary) / "chord_keys.so"
        compiler = shlex.split(os.environ.get("CC", "cc"))
        command = compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                              "-pedantic", "-ffreestanding", "-fno-stack-protector",
                              "-fPIC", "-dynamiclib" if sys.platform == "darwin" else "-shared",
                              str(source), "-o", str(library_path)]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            library = ct.CDLL(str(library_path))
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"FAIL compilation/chargement du noyau C : {error}")
            if isinstance(error, subprocess.CalledProcessError):
                print(error.stderr, end="")
            return 1
        build = library.chord_keys_build
        build.argtypes = [ct.POINTER(Config), ct.c_int, ct.POINTER(Result)]
        build.restype = ct.c_int
        failures = 0
        for label, test in families:
            try:
                test(build)
            except AssertionError as error:
                print(f"FAIL {label} : {error}")
                failures += 1
            else:
                print(f"ok {label}")
    return int(failures > 0)


if __name__ == "__main__":
    sys.exit(main())
