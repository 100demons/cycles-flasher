#!/usr/bin/env python3
"""Preuve du stockage des accords : routines stock et hooks ColdFire (notes/42).

Applique le JSON généré, puis exécute le vrai chargement, la sauvegarde et la
copie des patterns OS 1.13 avec Unicorn, avec le code dans ses caves finales. Les
accès au disque et le démarrage complet ne sont pas émulés. L'état de sélection
UI et les observateurs sont contrôlés par le banc ; aucune image n'est exportée.

    python3 tools/emu/probe_chord_storage.py --cycles firmware/model-cycles_OS1.13.syx

Nécessite Unicorn. Durée habituelle : quelques secondes.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

from unicorn import (Uc, UcError, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE,
                     UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE)
from unicorn import m68k_const as mk

from probe_chord_pads import official_image
from build import apply_writes

ROOT = Path(__file__).resolve().parents[2]
BASE = 0x40000400
STACK, STOP = 0x9300E000, 0x9300F000
H1, H2, H3 = 0x92000000, 0x92001000, 0x92002000
B1, B2, SERIAL = 0x92010000, 0x92020000, 0x92030000
PROJECT = 0x92100000
TAG, DEFAULT = 0x434B01A7, 48 << 21
RESERVED = set(range(32, 36)) | set(range(40, 64))
HOOKS = ((0x4005B4A8, "ck_storage_load_hook"), (0x40061564, "ck_storage_init_hook"))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Rig:
    def __init__(self, stock, patched, symbols):
        self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        self.uc.ctl_set_cpu_model(mk.UC_CPU_M68K_ANY)
        self.uc.reg_write(mk.UC_M68K_REG_SR, 0x2000)
        self.uc.mem_map(0x40000000, 0x02400000)
        self.uc.mem_write(BASE, patched)
        self.uc.mem_map(0x92000000, 0x02000000)
        self.uc.mem_write(STOP, b"\x4e\x71")
        self.symbols = {name: int(value, 0) if isinstance(value, str) else value
                        for name, value in symbols.items()}
        self.original = {address: bytes(stock[address - BASE:address - BASE + 8])
                         for address, _ in HOOKS}
        self.hooks = {address: bytes(patched[address - BASE:address - BASE + 8])
                      for address, _ in HOOKS}
        for address, symbol in HOOKS:
            expected = b"\x4e\xf9" + struct.pack(">I", self.symbols[symbol]) + b"\x4e\x71"
            require(self.hooks[address] == expected, f"Hook final différent : {symbol}")
        for name, address in self.symbols.items():
            if name.startswith("ck_storage_") or name in ("ck_ui_config_get", "ck_ui_config_set", "ck_audio_config"):
                require(address % 2 == 0, f"Code ColdFire non aligné : {name}")
        self.patched(False)
        self.selected = 0
        self.notifications = 0
        self.reads = set()
        self.observed = None
        self.unprotected = []
        self.protected_headers = set()
        self.uc.hook_add(UC_HOOK_MEM_READ, self._read)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self._write)
        # Seule la sélection UI est simulée ; son calcul d'objet reste stock.
        self.stub(0x400CFD0E, lambda args: 1)
        self.stub(0x4006A96C, lambda args: self.selected)
        self.stub(0x400D0F6C, self._notify)

    def _notify(self, args):
        self.notifications += 1
        return 0

    def _read(self, uc, access, address, size, value, user):
        if self.observed is not None:
            for offset in range(address - self.observed, address - self.observed + size):
                if 0 <= offset < 64:
                    self.reads.add(offset)

    def _write(self, uc, access, address, size, value, user):
        for header in self.protected_headers:
            if any(address <= header + offset < address + size for offset in RESERVED):
                if uc.reg_read(mk.UC_M68K_REG_SR) & 0x700 != 0x700:
                    self.unprotected.append((uc.reg_read(mk.UC_M68K_REG_PC), address))

    def stub(self, address, handler):
        def hook(uc, pc, size, user):
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            args = struct.unpack(">8I", uc.mem_read(sp + 4, 32))
            uc.reg_write(mk.UC_M68K_REG_D0, handler(args) & 0xFFFFFFFF)
            uc.reg_write(mk.UC_M68K_REG_PC, self.word(sp))
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        self.uc.hook_add(UC_HOOK_CODE, hook, begin=address, end=address)

    def word(self, address, value=None):
        if value is None:
            return struct.unpack(">I", self.uc.mem_read(address, 4))[0]
        self.uc.mem_write(address, struct.pack(">I", value & 0xFFFFFFFF))

    def call(self, target, *args):
        address = self.symbols[target] if isinstance(target, str) else target
        self.uc.mem_write(STACK, struct.pack(">" + "I" * (len(args) + 1), STOP, *args))
        self.uc.reg_write(mk.UC_M68K_REG_A7, STACK)
        self.uc.emu_start(address, STOP, count=4_000_000)
        require(self.uc.reg_read(mk.UC_M68K_REG_PC) == STOP, "Budget d'instructions dépassé")
        return self.uc.reg_read(mk.UC_M68K_REG_D0)

    def patched(self, enabled):
        for address, _ in HOOKS:
            self.uc.mem_write(address, self.hooks[address] if enabled else self.original[address])
        self.uc.ctl_flush_tb()

    def header(self, address, config_words=None):
        self.uc.mem_write(address, bytes(64))
        self.call(0x40061526, address, 0)
        if config_words is not None:
            self.word(address + 32, TAG)
            for track, word in enumerate(config_words):
                self.word(address + 40 + 4 * track, word)

    def bytes(self, address, count=64):
        return bytes(self.uc.mem_read(address, count))


def configuration(track):
    return 0x80000000 | (track << 28) | ((24 + track) << 21) | sum(
        ((track + degree) % 5) << (3 * degree) for degree in range(7))


def install_config_fixture(uc, words, pattern=0, root=PROJECT, header=H1, active=B1):
    """Relie un pattern factice aux vrais lecteurs ; les adresses doivent être mappées.

    Écrit les pointeurs globaux, l'objet de 732 octets, l'en-tête de 64 octets et
    l'identité du pattern actif. N'appelle ni ne remplace aucune routine firmware.
    Les listes d'observateurs restent vides ; le banc choisit comment les simuler.
    """
    require(0 <= pattern < 96 and len(words) == 6, "Fixture pattern invalide")

    def write(address, value):
        uc.mem_write(address, struct.pack(">I", value))

    obj = root + 5192 + 732 * pattern
    uc.mem_write(obj, bytes(732))
    uc.mem_write(header, bytes(64))
    write(obj, 0x400FDA54)
    write(obj + 44, 0x400FD8C0)
    write(obj + 60, header)
    write(header + 32, TAG)
    for track, word in enumerate(words):
        write(header + 40 + 4 * track, word)
    write(0x40FE4228, root)
    write(0x40A7887C, active)
    write(active + 30706, pattern)
    return obj


def stock_reserved(rig):
    words = [configuration(track) for track in range(6)]
    rig.header(H1, words)
    rig.uc.mem_write(H2, b"\xa5" * 64)
    rig.observed = H1
    rig.reads.clear()
    require(rig.call(0x4005B3B4, H2, H1) == 1, "Chargement stock refusé")
    rig.observed = None
    require(not (rig.reads & RESERVED), "Le chargeur stock consomme les octets candidats")
    require(all(rig.bytes(H2)[i] == 0xA5 for i in RESERVED), "Le chargeur stock écrit les réserves")
    rig.call(0x4005B4C4, H3, H1)
    require(rig.bytes(H3) == rig.bytes(H1), "La copie/sauvegarde d'en-tête ne garde pas 64 o")
    return rig.bytes(H2)


def patched_headers(rig, stock_result):
    rig.patched(True)
    rig.uc.mem_write(H2, b"\xa5" * 64)
    rig.call(0x4005B3B4, H2, H1)
    actual = rig.bytes(H2)
    require(all(actual[i] == stock_result[i] for i in range(64) if i not in RESERVED),
            "Le hook modifie un champ stock")
    require(all(actual[i] == rig.bytes(H1)[i] for i in RESERVED), "Réglages non chargés")
    before = rig.bytes(H2)
    rig.call(0x40061526, H2, 1)
    require(rig.bytes(H2) == before, "Init avec conservation perd les réglages")
    rig.call(0x40061526, H2, 0)
    require(all(rig.call("ck_storage_read", H2, track) == DEFAULT for track in range(6)),
            "Init ne désactive pas les accords")
    for signature in (0, 0xFFFFFFFF, TAG ^ 1):
        rig.word(H1 + 32, signature)
        rig.call(0x4005B3B4, H2, H1)
        require(all(rig.call("ck_storage_read", H2, track) == DEFAULT for track in range(6)),
                "Ancien pattern/garbage active les accords")
    rig.header(H1, [configuration(t) for t in range(6)])
    rig.word(H1 + 40, (49 << 21) | 0x80000000)
    rig.call(0x4005B3B4, H2, H1)
    require(all(rig.call("ck_storage_read", H2, track) == DEFAULT for track in range(6)),
            "Configuration corrompue acceptée")


def stock_accessors(rig):
    obj = PROJECT + 44
    rig.uc.mem_write(obj, bytes(68))
    rig.word(obj, 0x400FD8C0)
    rig.word(obj + 16, H1)
    rig.header(H1, [configuration(track) for track in range(6)])
    rig.observed = H1
    rig.reads.clear()
    getters = (0x4000C816, 0x4000C8A6, 0x4000C8DC, 0x4000C964,
               0x4000C994, 0x4000CA64, 0x4000CAF2, 0x4000CB22,
               0x4000CC2A, 0x4000CCFA, 0x4000CF20, 0x4000CE54)
    for getter in getters:
        rig.call(getter, obj)
    for track in range(6):
        rig.call(0x4000CCC0, obj, track)
    rig.observed = None
    require(not (rig.reads & RESERVED), "Accesseur stock lit les réserves")
    before = rig.bytes(H1)
    setters = ((0x4000C846, 7200), (0x4000C90C, 15), (0x4000C9C4, 32),
               (0x4000CA94, 32), (0x4000CB40, 3), (0x4000CBA6, 1),
               (0x4000CC5A, 60), (0x4000CDAE, 15), (0x4000CF50, 3))
    for setter, value in setters:
        rig.call(setter, obj, value)
    rig.call(0x4000CD2A, obj, 2, 1)
    require(all(rig.bytes(H1)[i] == before[i] for i in RESERVED),
            "Setter stock détruit les réglages d'accords")


def full_roundtrip(rig):
    rig.uc.mem_write(B1, bytes(30710))
    rig.call(0x400615E8, B1, 0)
    header = B1 + 30642
    for track in range(6):
        rig.word(header + 40 + 4 * track, configuration(track))
    rig.uc.mem_write(SERIAL, bytes(14800))
    require(rig.call(0x4005BA0A, SERIAL, B1, 0) == 1, "Sauvegarde stock refusée")
    require(rig.bytes(SERIAL + 14736) == rig.bytes(header), "Sauvegarde perd l'en-tête")
    rig.uc.mem_write(B2, b"\xa5" * 30710)
    require(rig.call(0x4005B894, B2, SERIAL, 73) == 1, "Chargement pattern refusé")
    require(rig.word(B2 + 30706) == 73, "Identité du pattern changée")
    for track in range(6):
        require(rig.call("ck_storage_read", B2 + 30642, track) == configuration(track),
                "Aller-retour pattern perd un réglage")
    rig.call(0x4008F1F0, B1, B2, 30710)
    require(rig.bytes(B1, 30710) == rig.bytes(B2, 30710), "Copie pattern différente")


def stock_binding(rig):
    """Vrai setter de pattern : en-tête, pistes et plocks sont des sous-zones de B."""
    obj = PROJECT + 5192 + 732 * 95
    rig.uc.mem_write(obj, bytes(732))
    vtables = [(0, 0x400FDA54), (44, 0x400FD8C0), (640, 0x400FDDF4)]
    vtables += [(112 + 88 * track, 0x400FF894) for track in range(6)]
    for offset, vtable in vtables:
        rig.word(obj + offset, vtable)
    for raw in (B1, B2):
        rig.call(0x4000C5D0, obj, raw)
        require(rig.word(obj + 16) == raw, "Le pattern ne pointe pas vers B")
        require(rig.word(obj + 60) == raw + 30642, "L'en-tête n'est pas B+30642")
        require(rig.word(obj + 656) == raw + 4332, "Les plocks ne suivent pas les six pistes")
        require(all(rig.word(obj + 128 + 88 * track) == raw + 722 * track
                    for track in range(6)), "Les pistes ne sont pas des sous-zones de B")


def live_headers(rig):
    rig.word(0x40FE4228, PROJECT)
    # Objets stock minimaux : vraies vtables, aucune liste d'observateurs active.
    for pattern, header in ((0, H1), (1, H2), (95, H3)):
        obj = PROJECT + 5192 + 732 * pattern
        rig.uc.mem_write(obj, bytes(732))
        rig.word(obj, 0x400FDA54)
        rig.word(obj + 44, 0x400FD8C0)
        rig.word(obj + 60, header)
        rig.header(header)
        require(rig.call(0x400D2A84, obj + 44) == header, "Getter d'en-tête incorrect")
    rig.selected = 0
    rig.protected_headers = {H1, H2, H3}
    rig.word(0x40A7887C, B1)
    rig.word(B1 + 30706, 0)
    notifications = rig.notifications
    for track in range(6):
        rig.call("ck_ui_config_set", track, configuration(track))
        require(rig.call("ck_ui_config_get", track) == configuration(track), "Lecture UI différente")
        require(rig.call("ck_audio_config", track) == configuration(track), "L'audio lit une ancienne copie")
    require(rig.notifications == notifications + 6, "Notification stock manquante")
    rig.selected = 1
    rig.call("ck_ui_config_set", 0, configuration(5))
    require(rig.call("ck_audio_config", 0) == configuration(0), "Éditer un autre pattern change l'audio")
    rig.word(B1 + 30706, 1)
    require(rig.call("ck_audio_config", 0) == configuration(5), "Changement de pattern audio non suivi")
    rig.word(PROJECT + 5192 + 732 + 60, H3)
    require(rig.call("ck_audio_config", 0) == DEFAULT, "Ancienne adresse d'en-tête gardée en cache")
    rig.call("ck_storage_reset", H3)
    rig.word(B1 + 30706, 96)
    require(rig.call("ck_audio_config", 0) == DEFAULT, "Indice pattern invalide accepté")
    rig.word(0x40FE4228, 0)
    require(rig.call("ck_audio_config", 0) == DEFAULT, "Singleton nul non protégé")
    require(not rig.unprotected, f"Écritures partielles exposées à l'audio : {rig.unprotected}")
    require(rig.uc.reg_read(mk.UC_M68K_REG_SR) & 0x2700 == 0x2000,
            "Le niveau d'interruption initial n'est pas rétabli")


def run_storage_checks(stock, patched, symbols):
    """Preuve réutilisable sur les octets et adresses exacts du JSON final."""
    rig = Rig(stock, patched, symbols)
    baseline = stock_reserved(rig)
    print("ok stock : réserves non lues au chargement, 64 octets conservés à la copie", flush=True)
    patched_headers(rig, baseline)
    print("ok hooks ColdFire : stock intact, réglages chargés, initialisation et fichiers anciens désactivés", flush=True)
    stock_accessors(rig)
    print("ok accesseurs stock : aucun champ réservé lu, réglages conservés par les setters", flush=True)
    full_roundtrip(rig)
    print("ok vrai pattern complet : sauvegarde, chargement, six réglages et copie", flush=True)
    stock_binding(rig)
    print("ok raccordement stock : en-tête, six pistes et plocks suivent le buffer de pattern", flush=True)
    live_headers(rig)
    print("ok UI/audio : édition immédiate, autre pattern, changement de pattern et remplacement du buffer", flush=True)
    return rig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=Path, required=True)
    parser.add_argument("--tweak", type=Path, default=ROOT / "tweaks/model-cycles_OS1.13/45-chord-keys.json")
    args = parser.parse_args()
    stock = official_image(args.cycles)
    tweak = json.loads(args.tweak.read_text())
    patched, _ = apply_writes(stock, [tweak])
    run_storage_checks(stock, patched, tweak["symbols"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, OSError, ValueError, UcError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        sys.exit(1)
