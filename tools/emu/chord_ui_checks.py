"""Contrôles du code ColdFire du clavier d'accords (notes/42).

Appelé par la preuve principale avec le MAIN OS modifié et les symboles du
générateur. Le stockage lit et écrit un vrai en-tête de pattern en RAM émulée ;
ses propres preuves vérifient les formats de projet. PadsView, PadEvent, KeyEvent,
le clavier stock, les relais de notes, le contrôleur de vues et le menu sont
réellement exécutés. La sélection du pattern et la notification sont simulées.
Les sélections, envois audio/MIDI et opérations de mute sont observés à leur
entrée ; la synthèse et le séquenceur sont vérifiés par les autres contrôles.
"""
import struct

from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as mk

import probe_chord_pads as pads
import test_arp as arp
import test_sdvintage_7th as t7

PROJECT, PATTERN, HEADER = 0x93100000, 0x93102000, 0x93108000
UIST, KEY_NOTES = 0x93110000, 0x93120000
KEY_CTOR, KEY_CONSUMER, KEY_VTABLE = 0x4007238C, 0x4001A0D2, 0x400FF9CC


class _HeaderWords:
    """Observation/instrumentation des mots persistants ; les menus utilisent le vrai setter."""

    def __init__(self, emulator):
        self.emulator = emulator

    def __getitem__(self, track):
        return self.emulator.r32(HEADER + 40 + 4 * track)

    def __setitem__(self, track, value):
        self.emulator.w32(HEADER + 40 + 4 * track, value)


def _header(emulator):
    emulator.chord_header_ready = True
    emulator.w32(0x40FE4228, PROJECT)
    emulator.w32(PATTERN + 44, 0x400FD8C0)
    emulator.w32(PATTERN + 60, HEADER)
    return _HeaderWords(emulator)


def _install(rig, address, handler):
    rig.uc.hook_add(UC_HOOK_CODE, rig._stub(handler), begin=address, end=address)


def _ui_rig(image, symbols=None):
    rig = pads.Rig(image)
    config = _header(rig)
    selected, machine, velocity = [2], [5], [97]
    for address, handler in {
            0x40012412: lambda a: selected[0],
            0x40012442: lambda a: selected[0],
            0x4001E318: lambda a: machine[0],
            0x40015AC4: lambda a: velocity[0],
            0x4000F23E: lambda a: pads.TRACK_DATA + 512,
            0x40016DA6: lambda a: 0,
            0x4006BDFE: lambda a: 0,  # FILL inactif, distinct des gardes réelles.
            0x40075F3C: lambda a: 0,
            0x400D0F6C: lambda a: 0,
    }.items():
        _install(rig, address, handler)
    rig.w32(0x40FE4218, UIST)
    rig.w32(pads.VIEW + 148, KEY_NOTES)
    rig.w32(pads.VIEW + 152, KEY_NOTES)
    rig.w32(pads.VIEW + 156, KEY_NOTES + 0xA00)
    if symbols:
        for track in range(6):
            rig.call(symbols["ck_ui_config_set"], track, (48 << 21) | 0x80000000)
    for operand in (0x4001D260, 0x4001A1C6):
        rate_reader = rig.r32(operand)
        if rate_reader != 0x40016086:
            # Les lecteurs Rte pads/clavier de l'arpège restent périphériques
            # à cette preuve ; les autres contrôles exécutent son audio réel.
            _install(rig, rate_reader, lambda a: rig.rate)
    return rig, config, selected, machine, velocity


def _key(rig, key, down, flags=0, velocity=127):
    rig.calls.clear()
    rig.call(KEY_CTOR, pads.EVENT, 15 + key, int(down) | flags, 123, velocity)
    return rig.call(rig.r32(KEY_VTABLE), pads.VIEW, pads.EVENT) & 255


def _on(track, note, velocity=97, rate=0xFFFFFFFF):
    return ("on", (track, note, velocity, 64, 0, 0xFFFFFFFF, rate))


def _keys(stock, image, symbols, check):
    rig, config, selected, machine, velocity = _ui_rig(image, symbols)
    check(all(rig.call(symbols["ck_ui_config_get"], t) == config[t] for t in range(6)),
          "touches : six configurations lues par la vraie API persistante")
    check(rig.r32(KEY_VTABLE) == symbols["ck_ui_key"],
          "touches : seul le consommateur KeyEvent du clavier est redirigé")
    for key in range(1, 17):
        slot = key - 1
        note = 48 + 12 * (slot // 7) + (0, 2, 4, 5, 7, 9, 11)[slot % 7]
        _key(rig, key, True, velocity=30)
        check(rig.calls == [_on(2, note)],
              f"TRIG {key} : degré {slot % 7 + 1}, octave +{slot // 7}, note {note}, vélocité de piste")
        selected[0] = 5
        rig.pressed = {1, 2, 3, 4}
        _key(rig, key, False)
        check(rig.calls == [("off", (2, note, 64))],
              f"TRIG {key} : relâchement fidèle malgré sélection et modificateurs changés")
        selected[0] = 2
        rig.pressed.clear()

    velocity[0] = 43
    rig.fixed_velocity = 111
    _key(rig, 8, True, velocity=12)
    check(rig.calls == [_on(2, 60, 43)],
          "touches : vélocité de piste conservée, indépendante du réglage fixe des grands pads")
    _key(rig, 8, False)
    velocity[0], rig.fixed_velocity = 97, None
    rig.pressed = {4}
    _key(rig, 8, True)
    check(rig.calls == [_on(2, 60)],
          "touches : RETRIG ne change plus l’octave et ne répète pas l’accord")
    _key(rig, 8, False)
    rig.pressed.clear()
    _key(rig, 1, True)
    _key(rig, 2, True)
    check(rig.calls == [("off", (2, 48, 64)), _on(2, 50)],
          "touches : la dernière frappe remplace l'accord précédent")
    _key(rig, 1, False)
    check(not rig.calls, "touches : relâcher l'ancienne touche ne coupe pas la nouvelle")
    _key(rig, 2, True, flags=8)
    check(not rig.calls, "touches : l'événement de maintien ne redéclenche pas l'accord")
    _key(rig, 2, False)
    check(rig.calls == [("off", (2, 50, 64))], "touches : relâcher la dernière touche termine son accord")
    _key(rig, 2, False)
    check(not rig.calls, "touches : double relâchement sans fin de note supplémentaire")

    # Comparer les vraies branches stock, sans remplacer le consommateur.
    for label, modifier, flags, enabled, chord, grid, secondary in (
            ("Keys OFF", 0, 0, False, True, False, False),
            ("autre machine", 0, 0, True, False, False, False),
            ("FUNC", 1, 2, True, True, False, False),
            ("TRACK", 2, 0, True, True, False, False),
            ("PATTERN", 3, 0, True, True, False, False),
            ("grille d'enregistrement", 0, 0, True, True, True, False),
            ("mode secondaire", 0, 0, True, True, False, True)):
        reference, _, _, _, _ = _ui_rig(stock)
        altered, cfg, _, mch, _ = _ui_rig(image, symbols)
        cfg[2] = (48 << 21) | (0x80000000 if enabled else 0)
        mch[0] = 5 if chord else 0
        snapshots = []
        for candidate in (reference, altered):
            candidate.pressed = {modifier} if modifier else set()
            candidate.uc.mem_write(UIST + 357, bytes([int(grid), int(grid)]))
            candidate.uc.mem_write(UIST + 389, bytes([int(secondary)]))
            events = []
            for down in (True, False):
                consumed = _key(candidate, 9, down, flags)
                events.append((consumed, candidate.calls[:]))
            snapshots.append(events)
        check(snapshots[0] == snapshots[1], f"touches : {label}, appui et relâchement identiques à l'OS stock")

    _key(rig, 16, True)
    config[2] &= 0x7FFFFFFF
    machine[0] = 0
    rig.uc.mem_write(UIST + 357, b"\1\1")
    _key(rig, 16, False)
    check(rig.calls == [("off", (2, 74, 64))],
          "touches : désactivation, autre machine et entrée en grille ne perdent pas la fin de note")
    config[2] |= 0x80000000
    machine[0] = 5
    rig.uc.mem_write(UIST + 357, b"\0\0")
    selected[0] = 0
    _key(rig, 1, True)
    selected[0] = 1
    _key(rig, 16, True)
    rig.calls.clear()
    rig.call(symbols["ck_ui_cancel_track"], 1)
    check(rig.calls == [("off", (1, 74, 64))], "touches : annulation ciblée, autre piste conservée")
    _key(rig, 16, False)
    check(not rig.calls, "touches : l'accord annulé garde son identité jusqu'au relâchement")
    _key(rig, 1, False)
    check(rig.calls == [("off", (0, 48, 64))], "touches : l'autre piste se relâche normalement")
    check(not rig.bad, "touches : aucun accès mémoire hors du banc")


def _pads(stock, image, symbols, check):
    reference, _, _, _, _ = _ui_rig(stock)
    altered, _, _, _, _ = _ui_rig(image, symbols)
    check(altered.r32(0x4010025C) == reference.r32(0x4010025C) == pads.PAD_CONSUMER and
          altered.r32(0x401002B0) == reference.r32(0x401002B0),
          "pads : les deux pointeurs de PadsView restent d'origine")
    for key, name in ((0, "normal"), (2, "TRACK"), (4, "RETRIG")):
        for pad in range(1, 7):
            snapshots = []
            for candidate in (reference, altered):
                candidate.pressed = {key} if key else set()
                events = []
                for down in (True, False):
                    consumed = candidate.event(pad, down, velocity=80 + pad)
                    events.append((consumed & 255, candidate.calls[:], candidate.held(pad)))
                snapshots.append(events)
            check(snapshots[0] == snapshots[1],
                  f"T{pad} {name} : sélection, note, vélocité, retrig et relâchement identiques au stock")
    check(not altered.bad and not reference.bad, "pads : aucun accès mémoire hors du banc")


def _dispatch(stock, image, symbols, check):
    snapshots, edits = [], []
    for source, config_symbols in ((stock, None), (image, symbols)):
        rig, _, _, _, _ = _ui_rig(source, config_symbols)
        rig.w32(pads.VIEW, 0x400FF9C4)
        heap = [0x93200000]

        def allocate(args):
            pointer = heap[0]
            heap[0] += (args[0] + 15) & ~15
            rig.uc.mem_write(pointer, bytes(args[0]))
            return pointer

        for address, handler in (
                (0x400802E0, allocate), (0x400802EC, lambda a: 0),
                (0x400E8684, lambda a: 0), (0x400D08CE, lambda a: 0)):
            _install(rig, address, handler)
        node = 0x93010100
        rig.w32(node + 8, pads.VIEW)
        rig.w32(node + 4, pads.CONTROLLER + 20)
        rig.w32(pads.CONTROLLER + 20, node)
        rig.w32(pads.CONTROLLER + 24, node)
        events = []
        for down in (True, False):
            rig.calls.clear()
            rig.call(KEY_CTOR, pads.EVENT, 23, int(down), 123, 127)  # TRIG 8
            rig.call(0x40077720, pads.CONTROLLER, pads.EVENT)
            events.append(rig.calls[:])
        snapshots.append(events)
        # KeyboardView reste devant PatternGridView : son garde doit laisser
        # la vraie grille enregistrer le pas, sans envoyer de note au moteur.
        trigs = {}

        def set_trig(args, value):
            trigs[args[1]] = value
            rig.calls.append(("trig", (args[1], value)))
            return 0

        for address, handler in {
                0x4000EE90: lambda a: 0x93101000,
                0x400124B8: lambda a: 0,
                0x40015C20: lambda a: int(trigs.get(a[1]) == "note"),
                0x40015C7C: lambda a: int(trigs.get(a[1]) == "lock"),
                0x40017B48: lambda a: set_trig(a, "note"),
                0x40017BB0: lambda a: set_trig(a, "lock"),
                0x40017C4E: lambda a: set_trig(a, None),
                0x400760BA: lambda a: 0,
                0x40069B84: lambda a: 0,
        }.items():
            _install(rig, address, handler)
        grid, grid_node = 0x93300000, 0x93010200
        rig.w32(grid, 0x40100AE8)
        rig.w32(node + 4, grid_node)
        rig.w32(grid_node + 8, grid)
        rig.w32(grid_node + 4, pads.CONTROLLER + 20)
        rig.w32(pads.CONTROLLER + 20, grid_node)
        rig.uc.mem_write(UIST + 357, b"\1\1")
        rig.calls.clear()
        rig.call(KEY_CTOR, pads.EVENT, 24, 1, 123, 127)  # TRIG 9
        rig.call(0x40077720, pads.CONTROLLER, pads.EVENT)
        edits.append((trigs, rig.calls[:]))
        check(not rig.bad, "dispatch KeyEvent réel : aucun accès mémoire hors du banc")
    check(snapshots == [[[_on(2, 59)], [("off", (2, 59, 64))]],
                        [[_on(2, 60)], [("off", (2, 60, 64))]]],
          "dispatch KeyEvent réel : TRIG 8 passe du chromatique stock à I +12, puis relâche la bonne note")
    check(edits == [({8: "note"}, [("trig", (8, "note"))])] * 2,
          "dispatch KeyEvent réel : la grille stock et modifiée pose le pas 9, sans jouer d'accord")


def _menu_rig(image, symbols):
    emulator = arp.Emu(image)
    items, drawn = [], []
    # Le constructeur stock initialise son propre projet ; on installe notre
    # en-tête isolé après sa construction, pour les callbacks du nouveau menu.
    emulator.chord_header_ready = False
    config, selected, machine = _HeaderWords(emulator), [2], [5]

    def hook(uc, address, size, user):
        sp = uc.reg_read(mk.UC_M68K_REG_A7)
        args = struct.unpack(">8I", uc.mem_read(sp + 4, 32))
        if address == 0x400734B0:
            funcs = []
            for pointer in args[1:5]:
                storage, _, manager, invoke = struct.unpack(">4I", uc.mem_read(pointer, 16))
                funcs.append((manager, invoke, emulator.r32(storage)))
            items.append(funcs)
        elif address == 0x4000F23E:
            emulator._pop(uc, emulator.track.obj)
        elif address == 0x4000F208 and emulator.chord_header_ready:
            emulator._pop(uc, PATTERN)
        elif address == 0x40012412:
            emulator._pop(uc, selected[0])
        elif address == 0x4001E318:
            emulator._pop(uc, machine[0])
        elif address == 0x40071A04:
            drawn.append(args)
            emulator._pop(uc, 0)
        elif address in (0x40072260, 0x40072080, 0x400D0F6C):
            emulator._pop(uc, 0)

    addresses = (0x400734B0, 0x4000F23E, 0x4000F208, 0x40012412, 0x4001E318,
                 0x40071A04, 0x40072260, 0x40072080, 0x400D0F6C)
    for address in addresses:
        emulator.uc.hook_add(UC_HOOK_CODE, hook, begin=address, end=address)
    return emulator, items, drawn, config, selected, machine


def _menu(image, symbols, check):
    emulator, items, drawn, config, selected, machine = _menu_rig(image, symbols)
    view = 0x93000000
    emulator.uc.mem_write(view, bytes(0x400))
    emulator.call(0x4002D138, view)
    original_count = len(items)
    items.clear()
    emulator.uc.mem_write(view, bytes(0x400))
    emulator.call(symbols["ck_ui_menu_ctor"], view)
    check(len(items) == original_count + 10,
          f"menu réel : {original_count} lignes préexistantes conservées, dix ajoutées")
    if len(items) != original_count + 10:
        return
    _header(emulator)
    emulator.call(symbols["ck_storage_reset"], HEADER)
    expected = ("Keys", "Root", "Scale", "I", "II", "III", "IV", "V", "VI", "VII")
    for field, name in enumerate(expected):
        label, press, draw, change = items[original_count + field]
        valid = all(func[0] == 0x4002CF00 for func in items[original_count + field])
        valid &= arp.cstr(emulator, label[2]) == name and press[1:] == (0x4002CCD0, view)
        valid &= draw[2] == field and change[2] == field
        # Exécuter également le vrai libellé std::string, avec son ABI a0.
        functor = arp.make_fn(emulator, label)
        string = 0x93600100
        emulator.uc.reg_write(mk.UC_M68K_REG_A0, string)
        sp = t7.STACK - 0x400
        emulator.uc.mem_write(sp, struct.pack(">II", t7.STOP, functor))
        emulator.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        emulator.uc.emu_start(label[1], t7.STOP, count=200_000)
        check(valid and arp.std_string(emulator, string) == name, f"menu : libellé {name}, vraie std::string")

        changer = arp.make_fn(emulator, change)
        shift = 31 if field == 0 else 21 if field == 1 else 28 if field == 2 else 3 * (field - 3)
        mask = 1 if field == 0 else 127 if field == 1 else 7
        for delta, target in ((99, (1, 48, 6, 4, 4, 4, 4, 4, 4, 4)[field]),
                              (-99, 24 if field == 1 else 0)):
            before = config[2]
            emulator.call(change[1], changer, 0, delta & 0xFFFFFFFF)
            check(((config[2] >> shift) & mask) == target and
                  (config[2] & ~(mask << shift)) == (before & ~(mask << shift)),
                  f"menu : {name}, borne {target}, autres champs conservés")

        config[2] = (48 << 21) | 0x80000000 | (5 << 28) | sum(4 << (3 * degree) for degree in range(7))
        drawer = arp.make_fn(emulator, draw)
        drawn.clear()
        emulator.call(draw[1], drawer, 0, 0x93700000, 0x93710000, 7)
        args = drawn[-1]
        value = arp.cstr(emulator, args[6])
        if field == 1:
            good = arp.cstr(emulator, args[5]) == "%s%d" and value == "C" and args[7] == 3
        else:
            good = arp.cstr(emulator, args[5]) == "%s" and value == ("ON" if field == 0 else "MINOR" if field == 2 else "13")
        check(good and args[2:5] == (0x93710000 + 24, 7, 4), f"menu : affichage {name} et placement stock")

    config[2] = 48 << 21
    draw = items[original_count + 2][2]
    emulator.call(draw[1], arp.make_fn(emulator, draw), 0, 0x93700000, 0x93710000, 7)
    check(arp.cstr(emulator, drawn[-1][6]) == "MAJ",
          "menu : le mode majeur affiche MAJ dans Scale")
    for extension, text in enumerate(("TRI", "7", "9", "11", "13")):
        config[2] = (48 << 21) | sum(extension << (3 * degree) for degree in range(7))
        values = []
        for field in range(3, 10):
            draw = items[original_count + field][2]
            emulator.call(draw[1], arp.make_fn(emulator, draw), 0, 0x93700000, 0x93710000, 7)
            values.append(arp.cstr(emulator, drawn[-1][6]))
        check(values == [text] * 7, f"menu : I à VII affichent directement {text}, sans Ext")
    config[2] = 48 << 21
    machine[0] = 0
    change = items[original_count][3]
    emulator.call(change[1], arp.make_fn(emulator, change), 0, 1)
    check(config[2] == 48 << 21, "menu : activation refusée sur une machine autre que CHORD")
    check(not emulator.bad, "menu : aucun accès mémoire hors du banc")


def _live(image, symbols, check):
    """TRIG -> relais stock -> vraie file audio, et messages stock de live rec.

    Le projet, les touches, les verrous et la position temporelle sont simulés.
    Ui observe la file de l'interface : cette preuve s'arrête avant l'écriture
    du trig dans le pattern ; le rendu harmonique est vérifié séparément.
    """
    audio = arp.Audio(image)
    audio.uc.mem_map(0x93000000, 0x01000000)
    ui = arp.Ui(audio)
    track, pressed = 2, set()
    _header(audio)

    def stub(handler):
        def hook(uc, address, size, user):
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            args = struct.unpack(">8I", uc.mem_read(sp + 4, 32))
            uc.reg_write(mk.UC_M68K_REG_D0, handler(args) & 0xFFFFFFFF)
            uc.reg_write(mk.UC_M68K_REG_PC, audio.r32(sp))
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        return hook

    for address, handler in {
            0x400CF866: lambda a: PROJECT,
            0x4000EB90: lambda a: 0x93101000,
            0x4000F208: lambda a: PATTERN,
            0x40012412: lambda a: track,
            0x4001E318: lambda a: 5,
            0x40013464: lambda a: 0,
            0x40015AC4: lambda a: 97,
            0x4006BDFE: lambda a: 0,
            0x4007FAF4: lambda a: int(a[0] in pressed),
            0x40001D2C: lambda a: 0,
            0x40001E4E: lambda a: 0,
            0x400CF23C: lambda a: 0,
            0x40016E90: lambda a: 0,
            0x400D0F6C: lambda a: 0,
    }.items():
        audio.uc.hook_add(UC_HOOK_CODE, stub(handler), begin=address, end=address)
    audio.w32(pads.VIEW + 44, pads.CONTROLLER)
    audio.w32(pads.CONTROLLER + 20, pads.CONTROLLER + 20)
    audio.w32(0x40A7887C, arp.BANK)
    audio.uc.mem_write(arp.BANK + 722 * track + 710, struct.pack(">H", 0x680))
    audio.uc.mem_write(0x40FB680C, b"\xff" * 4 * 128 * 6)
    audio.e.call(symbols["ck_ui_config_set"], track, 0x80000000 | (48 << 21) | (4 << 18))
    arp.live(audio, True)

    def event(down):
        audio.w32(0x8000184C, audio.now)
        audio.e.call(KEY_CTOR, pads.EVENT, 30, int(down), 123, 127)
        audio.e.call(symbols["ck_ui_key"], pads.VIEW, pads.EVENT)
        return audio.run()

    mask = event(True)
    check(mask is not None and mask & (1 << track) and audio.state(track)[:2] == (72, 72),
          "live rec : TRIG 15 atteint la vraie file audio, degré I +24 = note 72")
    check([arp.msg(m)[:5] for m in ui.os] == [("ON", track, 72, 97, -1)] and not ui.posted,
          "live rec : le message stock garde la fondamentale, la vélocité et aucun retrig")
    pressed.clear()
    audio.now += 40000
    event(False)
    check([arp.msg(m)[:5] for m in ui.os] == [("ON", track, 72, 97, -1),
                                           ("OFF", track, 72, 0, 20000)],
          "live rec : le relâchement stock garde la note et sa durée sur la touche de la troisième octave")
    check(not audio.e.unmapped, "live rec : aucun accès mémoire hors du banc")


def _shape_ui(stock, image, symbols, check):
    """Vrais formatters, mesures et dessin des glyphes dans un écran de 128×64."""
    bank, output, sprite = 0x93130000, 0x93131000, 0x93132000
    canvas, pixels, string, label_buffer = 0x93133000, 0x93134010, 0x93135000, 0x93135100

    def prepare(firmware, exported=None):
        rig, config, selected, machine, _ = _ui_rig(firmware, exported)
        # Les accesseurs de descripteurs du Syntakt résident dans sa charge
        # utile, recopiée au boot. Ce banc n'exécute pas le démarrage complet.
        payload = firmware[t7.E.IMAGE_LEN:]
        if payload:
            rig.uc.mem_map(t7.E.PAYLOAD_DST, (len(payload) + 0xFFFFF) & ~0xFFFFF)
            rig.uc.mem_write(t7.E.PAYLOAD_DST, bytes(payload))
        drawn = []
        _install(rig, 0x4000EB9C, lambda a: bank)
        _install(rig, 0x4000C0A6, lambda a: 1)  # valeur du son acceptée
        _install(rig, 0x40072058, lambda a: sprite)
        _install(rig, 0x40071DA4, lambda a: drawn.append(a[:6]) or 0)
        heap = [0x93200000]

        def allocate(args):
            pointer = heap[0]
            heap[0] += (args[0] + 15) & ~15
            rig.uc.mem_write(pointer, bytes(args[0]))
            return pointer

        _install(rig, 0x400802E0, allocate)
        _install(rig, 0x400802EC, lambda a: 0)
        # Canvas stock : largeur, hauteur, deux mots verticaux par colonne.
        rig.uc.mem_write(canvas, struct.pack(">5I", 0, 128, 64, 2, pixels))
        for track in range(6):
            rig.w32(bank + 504 + 8 * track, 0x400FD134)
        # Enregistrements de formatage que le boot construit pour les paramètres.
        # Le formatter CHORD ajoute un à l'index brut, puis appelle l'entier stock.
        rig.w32(0x40A70710, 1)
        rig.w32(0x40A70714, 0x400456C8)
        for descriptor in (51, 72):
            record = 0x40A71754 + 100 * descriptor
            rig.w32(record + 28, 1)
            rig.w32(record + 32, 0x4004DFDA if descriptor == 72 else 0x400456C8)
            rig.w32(record + 44, 1)
            rig.w32(record + 48, 0x4004611E)
        return rig, config, selected, machine, drawn

    reference, _, _, _, stock_drawn = prepare(stock)
    altered, config, selected, machine, drawn = prepare(image, symbols)
    format_fn, draw_fn = altered.r32(0x400FD170), altered.r32(0x400FD174)
    name_fn = altered.r32(0x4001E4CC)
    check((format_fn, draw_fn, name_fn) ==
          tuple(symbols[name] for name in ("ck_shape_format", "ck_shape_draw", "ck_shape_name")),
          "SHAPE UI : pointeurs du formatter, du pictogramme et du nom de popup raccordés")

    def text(rig, function, obj, descriptor, value):
        rig.uc.mem_write(output, bytes(64))
        rig.call(function, obj, descriptor, value & 0xFFFFFFFF, output)
        return bytes(rig.uc.mem_read(output, 64)).split(b"\0", 1)[0].decode("ascii")

    def cstr(rig, pointer):
        return bytes(rig.uc.mem_read(pointer, 32)).split(b"\0", 1)[0].decode("ascii")

    labels = ("BASE", "CLS0", "CLS1", "CLS2", "CLS3", "OPN0", "OPN1", "OPN2", "OPN3")
    before = bytes(altered.uc.mem_read(HEADER, 64))
    valid = True
    for track in range(6):
        obj = bank + 504 + 8 * track
        selected[0] = (track + 1) % 6
        for value in (-32768, -1, *range(0, 38 << 8, 127), 32767):
            label = labels[min(8, max(0, min(value, 37 << 8)) >> 10)]
            valid &= text(altered, format_fn, obj, 72, value) == label
        valid &= cstr(altered, altered.call(name_fn, obj, 72)) == "Chord Voicing"
        drawn.clear()
        valid &= altered.call(draw_fn, obj, 72, 7 << 8, 1, canvas, 96, 34) == 1 and not drawn
    check(valid and bytes(altered.uc.mem_read(HEADER, 64)) == before,
          "SHAPE UI : neuf noms, frontières 8.8 signées et six pistes, configuration inchangée")

    # Exécuter sprintf, std::string, les métriques, le centrage et les glyphes
    # stock : un simple retour zéro utilisait 67 px et débordait du panneau.
    valid, pictures = True, set()
    for index, label in enumerate(labels):
        altered.uc.mem_write(label_buffer, label.encode("ascii") + b"\0")
        altered.call(0x400F980C, string, label_buffer, output)
        valid &= altered.call(0x40072102, 0x401429EC, 0xFFFFFFFF, string) == 67
        valid &= altered.call(0x40072102, 0x4014120C, 0xFFFFFFFF, string) == 31
        altered.call(0x400F7D5C, string)
        altered.uc.mem_write(pixels - 16, b"\xa5" * 16 + bytes(1024) + b"\xa5" * 16)
        altered.call(draw_fn, bank + 504, 72, index << 10, 1, canvas, 96, 34)
        picture = bytes(altered.uc.mem_read(pixels, 1024))
        pictures.add(picture)
        lit = [(x, y) for x in range(128) for y in range(64)
               if struct.unpack_from(">I", picture, 8 * x + 4 * (y // 32))[0] & (1 << (31 - y % 32))]
        valid &= bool(lit) and all(81 <= x <= 111 and 40 <= y <= 48 for x, y in lit)
        valid &= bytes(altered.uc.mem_read(pixels - 16, 16)) == b"\xa5" * 16
        valid &= bytes(altered.uc.mem_read(pixels + 1024, 16)) == b"\xa5" * 16
    check(valid and len(pictures) == len(labels),
          "SHAPE UI : neuf dessins distincts, vrais glyphes de 31 px centrés et contenus dans le panneau droit")

    # Rejouer réellement les formatters et le dessinateur stock dans les replis.
    # Une sélection Keys ON ne doit pas contaminer l'objet d'une autre piste OFF.
    valid = True
    for why, track, descriptor, chord, enabled, offset in (
            ("Keys OFF", 2, 72, True, False, 0),
            ("autre piste OFF", 4, 72, True, False, 0),
            ("autre machine", 2, 72, False, True, 0),
            ("autre paramètre", 2, 51, True, True, 0),
            ("objet extérieur", 2, 72, True, True, 2)):
        selected[0] = 0
        config[track] = (48 << 21) | (0x80000000 if enabled else 0)
        machine[0] = 5 if chord else 0
        obj = bank + 504 + 8 * track + offset
        if offset:
            altered.w32(obj, 0x400FD134)
            reference.w32(obj, 0x400FD134)
        for value in (0, 3 << 8, 37 << 8):
            valid &= text(altered, format_fn, obj, descriptor, value) == \
                text(reference, 0x4000A70E, obj, descriptor, value)
            drawn.clear()
            stock_drawn.clear()
            args = (obj, descriptor, value, 1, output, 96, 34)
            valid &= altered.call(draw_fn, *args) == reference.call(0x4000A66A, *args)
            valid &= drawn == stock_drawn
        valid &= cstr(altered, altered.call(name_fn, obj, descriptor)) == \
            cstr(reference, reference.call(0x4000B22A, obj, descriptor))
        config[track] = (48 << 21) | 0x80000000
    check(valid, "SHAPE UI : Keys OFF, autre piste, machine, paramètre ou objet restent stock")


def run(stock, patched, symbols, check):
    """Exécute les contrôles ; check(bool, texte) appartient à la preuve principale."""
    symbols = {name: int(value, 16) if isinstance(value, str) else value for name, value in symbols.items()}
    _keys(stock, patched, symbols, check)
    _pads(stock, patched, symbols, check)
    _dispatch(stock, patched, symbols, check)
    _menu(patched, symbols, check)
    _shape_ui(stock, patched, symbols, check)
    _live(patched, symbols, check)
