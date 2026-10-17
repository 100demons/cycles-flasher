#!/usr/bin/env python3
"""Preuve de Control All Config (notes/58, tweaks/model-cycles_OS1.13/49-control-all-config.json) : le vrai code de
l'OS, sur le MAIN OS d'origine et sur le MAIN OS modifié, fonction par fonction, les fonctions de l'OS qu'il appelle
interceptées (leurs arguments notés, une réponse connue rendue).

  1. Écritures : octets d'origine ; les quatre masques identiques au masque gardé et désignés par la seule constante
     de leur constructeur, redirigée ; aucune écriture différente d'un autre tweak installable avec lui sur les mêmes
     octets ; état du mod (masque des pistes écartées, touches en cours) à zéro dans l'image.
  2. cac_skip : piste écartée -> 1, piste qui suit -> 0, piste active -> toujours 0 ; d2-d7/a2-a6 rendus intacts.
  3. Les cinq boucles de Control All (potard, valeur sur toutes les pistes, destination du LFO, PUNCH/GATE, MACHINES),
     code de l'OS d'origine contre modifié : à l'origine les six pistes ; modifié, les pistes qui suivent et toujours
     l'active, chaque appel avec les mêmes arguments qu'à l'origine ; sans piste écartée, identique à l'origine.
  4. TRACK + TRIG 1-6 (cac_keys, vraie structure de l'événement : code en +12, drapeaux en +16) : l'appui bascule la
     piste et demande le redessin des LED ; relâchement et répétition pris seulement si l'appui l'a été ; TRACK,
     TRIG 7-16 et le reste passent au consumeKeyEvent d'origine ; pile rendue.
  5. LED (cac_leds) : le producteur d'origine appelé avec ses trois arguments, puis TRIG n allumé (état 2) pour une
     piste qui suit, éteint (1) pour une piste écartée, 4e argument de l'OS passé tel quel ; bits 1..6 du mot 0 de
     l'ensemble posés, le reste intact ; pile rendue.
  6. Avec les autres mods (--with) : les mêmes vérifications sur l'image combinée.

    python3 tools/emu/test_control_all_config.py --cycles model-cycles_OS1.13.syx \\
        [--with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max,boot-anim \\
         --syntakt Syntakt_OS1.42.syx]
"""
import argparse
import json
import pathlib
import struct
import sys

from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import sprites                      # noqa: E402
import test_sdvintage as T          # noqa: E402
import test_sdvintage_7th as t7     # noqa: E402

TWEAK = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13" / "49-control-all-config.json"
BASE, STOP, STACK = t7.BASE, t7.STOP, t7.STACK
FAIL = []

# Fonctions de l'OS (notes/58)
OS_PROJECT, OS_PROJECT_TRACKS, OS_ACTIVE_TRACK = 0x400cf866, 0x4000eb90, 0x40012412
OS_KEY_HELD, OS_UISTATES, OS_HELD_STEP = 0x4007faf4, 0x400cf9a8, 0x4006bdfe
OS_LEDS, OS_LED_SET, OS_LED_ON, OS_VIEW_LEDS = 0x400cfaf4, 0x40005f86, 0x404a8c68, 0x400760ba
TSV_KEYS, TSV_LEDS = 0x40024078, 0x40023d8c
LOOP1, LOOP2, LOOP3_HEAD, LOOP3_END, LOOP4, LOOP5 = 0x4001d6e4, 0x4001d590, 0x4001ebd2, 0x4001ebfe, 0x4001ac4a, 0x400a2712
OS_LFO_DEST, OS_PUNCH_GATE, OS_TRACK_MACHINE, OS_MACHINE_WHEEL = 0x4000b274, 0x4001abe2, 0x40009c1a, 0x4001488a
# Objets et fonctions factices (dans la zone 0x90000000 de t7.UI)
FAKE = 0x92000000
THIS, VT_THIS, PS, VT_PS, GETP, GETPS, SETP = (FAKE + 0x1000, FAKE + 0x1100, FAKE + 0x1200, FAKE + 0x1300,
                                               FAKE + 0x2000, FAKE + 0x2010, FAKE + 0x2020)
PROJ, UI, LEDOBJ, VIEW, EVT, OUT, THIS5 = (FAKE + 0x3000, FAKE + 0x3100, FAKE + 0x3200, FAKE + 0x3300,
                                           FAKE + 0x3400, FAKE + 0x3500, FAKE + 0x4000)
ALL = list(range(6))


def check(ok, msg):
    print(f"  {'ok   ' if ok else 'ECHEC'} {msg}", flush=True)
    if not ok:
        FAIL.append(msg)


def follows(mask, active):
    """Les pistes que Control All touche avec le mod : celles qui ne sont pas écartées, et l'active toujours."""
    return [t for t in ALL if not (mask >> t) & 1 or t == active]


class Rig(t7.UI):
    """L'image en émulation, avec les objets factices et les fonctions de l'OS interceptées."""

    def __init__(self, img, sym):
        super().__init__(img)
        self.sym = sym
        self.w32(THIS, VT_THIS)
        self.w32(VT_THIS + 0x7c, GETP)          # getParam(this, param, funcTenu, piste) -> descripteur
        self.w32(VT_THIS + 0x80, GETPS)         # (this, piste, ...) -> jeu de paramètres de la piste
        self.w32(PS, VT_PS)
        self.w32(VT_PS + 0x20, SETP)            # set(ps, param, valeur, piste, 0, 0, 0, 0)
        self.w32(THIS5, 0)
        for t in ALL:                           # écran MACHINES : la machine affichée de chaque piste (+70 + 4·t)
            self.w32(THIS5 + 70 + 4 * t, 0)
        self.hooks.update({
            GETP: ("getParam", 0x29), GETPS: ("paramSet", PS), SETP: ("set", 0),
            OS_PROJECT: ("project", PROJ), OS_ACTIVE_TRACK: ("activeTrack", 0),
            OS_UISTATES: ("uiStates", UI), OS_HELD_STEP: ("heldStep", 0),
            OS_LFO_DEST: ("lfoDest", 0), OS_PUNCH_GATE: ("punchGate", 0),
            # la molette rend une machine (3) différente de celle affichée (0) : l'écran d'origine ne passe alors pas
            # par la mise à jour de l'icône (0x400a27ba), qui lirait les pointeurs de l'objet factice
            OS_TRACK_MACHINE: ("trackMachine", 0x77), OS_MACHINE_WHEEL: ("wheel", 3),
            OS_LEDS: ("leds", LEDOBJ), OS_LED_SET: ("ledSet", 0), OS_VIEW_LEDS: ("redraw", 0),
            TSV_KEYS: ("stockKeys", 0), TSV_LEDS: ("stockLeds", 0),
        })

    def w32(self, a, v):
        self.uc.mem_write(a, struct.pack(">I", v & 0xffffffff))

    def r32(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def r8(self, a):
        return self.uc.mem_read(a, 1)[0]

    def w8(self, a, v):
        self.uc.mem_write(a, bytes([v & 0xff]))

    def set_mask(self, mask):
        if self.sym:
            self.w8(self.sym["cac_mask"], mask)

    def held(self, ret):
        self.hooks[OS_KEY_HELD] = ("keyHeld", ret)

    def active(self, t):
        self.hooks[OS_ACTIVE_TRACK] = ("activeTrack", t)

    def named(self, name):
        return [a for n, a in self.calls if n == name]

    def go(self, fn, *args):
        """Appelle fn(args) comme t7.UI.call, et vérifie que la pile est rendue."""
        self.calls.clear()
        d0 = self.call(fn, *args)
        sp = self.uc.reg_read(mk.UC_M68K_REG_A7)
        check(sp == STACK - 0x400 + 4 and not self.bad, f"pile rendue et aucun accès hors carte ({fn:#x})")
        return d0

    def run_loop3(self, this, dest):
        """La boucle de setLFO (0x4001ebd2..0x4001ebfe) seule, avec les registres que la fonction lui donne."""
        self.calls.clear()
        uc = self.uc
        uc.reg_write(mk.UC_M68K_REG_A2, this)
        uc.reg_write(mk.UC_M68K_REG_A3, 0)              # compteur de piste
        uc.reg_write(mk.UC_M68K_REG_A4, OS_LFO_DEST)
        uc.reg_write(mk.UC_M68K_REG_A5, 1)
        uc.reg_write(mk.UC_M68K_REG_D2, dest)
        uc.reg_write(mk.UC_M68K_REG_A7, STACK - 0x400)
        self.bad.clear()
        uc.emu_start(LOOP3_HEAD, LOOP3_END, count=1_000_000)
        check(uc.reg_read(mk.UC_M68K_REG_A7) == STACK - 0x400 and not self.bad, "setLFO : pile rendue, aucun accès hors carte")

    def skip(self, t):
        """cac_skip(d0 = t) -> d0, avec d2-d7/a2-a6 surveillés."""
        uc = self.uc
        keep = {mk.UC_M68K_REG_D2 + i: 0x11111111 * (i + 2) for i in range(6)}
        keep.update({mk.UC_M68K_REG_A2 + i: FAKE + 0x8000 + 0x100 * i for i in range(5)})
        for r, v in keep.items():
            uc.reg_write(r, v)
        uc.reg_write(mk.UC_M68K_REG_D0, t)
        sp = STACK - 0x400
        self.uc.mem_write(sp, struct.pack(">I", STOP))
        uc.reg_write(mk.UC_M68K_REG_A7, sp)
        self.calls.clear()
        self.bad.clear()
        uc.emu_start(self.sym["cac_skip"], STOP, count=100_000)
        intact = all(uc.reg_read(r) == v for r, v in keep.items())
        return uc.reg_read(mk.UC_M68K_REG_D0), intact


def writes_ok(stock, img, tweak, every):
    masks = {}
    for w in tweak["writes"]:
        off, old, new = w["off"], bytes.fromhex(w["old"]), bytes.fromhex(w["new"])
        check(stock[off:off + len(old)] == old, f"octets d'origine en {off + BASE:#x}")
        if off + BASE in sprites.MASKS:
            masks[off + BASE] = len(new)
    check(len(masks) == 4, f"quatre masques de code : {', '.join(f'{m:#x}' for m in masks)}")
    for m, n in masks.items():
        size, kept = sprites.MASKS[m][0], sprites.kept_of(m)
        check(stock[m - BASE:m - BASE + size] == stock[kept - BASE:kept - BASE + size],
              f"masque {m:#x} identique au masque gardé {kept:#x}")
        check(stock.count(struct.pack(">I", m)) == 1, f"masque {m:#x} désigné une seule fois dans l'OS (constante)")
        check(sprites.redirect_write(m) in tweak["writes"], f"sprite du masque {m:#x} redirigé")
        check(n <= size, f"{n} o dans les {size} o du masque {m:#x}")
    mine = {}
    for w in tweak["writes"]:
        for i in range(len(w["new"]) // 2):
            mine[w["off"] + i] = (w["off"], w["old"], w["new"])
    clash = []
    for t in every:
        if tweak["id"] in t.get("conflicts", []) or t["id"] in tweak.get("conflicts", []):
            continue
        for w in t["writes"]:
            for i in range(len(w["new"]) // 2):
                if w["off"] + i in mine and mine[w["off"] + i] != (w["off"], w["old"], w["new"]):
                    clash.append((t["id"], w["off"] + BASE))
                    break
    check(not clash, "aucune écriture différente d'un autre mod installable avec lui" + (f" : {clash[:4]}" if clash else ""))
    sym = {k: int(v, 16) for k, v in tweak["symbols"].items()}
    check(img[sym["cac_mask"] - BASE] == 0 and img[sym["cac_held"] - BASE] == 0, "masque et touches à zéro dans l'image")
    check(img[sym["cac_mask"] - BASE - 4:sym["cac_mask"] - BASE] == b"CAC1", "marque CAC1 devant l'état")
    return sym


def skip_ok(rig):
    for mask in (0x00, 0x01, 0x3f, 0x2a, 0x15):
        for active in ALL:
            rig.set_mask(mask)
            rig.active(active)
            got = []
            for t in ALL:
                d0, intact = rig.skip(t)
                got.append(d0)
                if not intact:
                    check(False, f"cac_skip({t}) garde d2-d7/a2-a6")
            want = [1 if (mask >> t) & 1 and t != active else 0 for t in ALL]
            if got != want:
                check(False, f"cac_skip masque {mask:#04x} active {active} : {got} attendu {want}")
    check(not FAIL or all("cac_skip" not in f for f in FAIL), "cac_skip : écartée -> 1, qui suit -> 0, active -> 0, registres intacts")
    check(not rig.calls or all(n in ("project", "activeTrack") for n, _ in rig.calls), "cac_skip n'appelle que le projet et la piste active")


def loops_ok(rig, mod):
    """Les cinq boucles ; mod = False pour l'image d'origine (six pistes), True pour la modifiée."""
    cases = [(0x00, 0)] + ([(0x01, 0), (0x01, 3), (0x3f, 2), (0x2a, 1), (0x15, 4)] if mod else [])
    for mask, active in cases:
        rig.set_mask(mask)
        rig.active(active)
        want = follows(mask, active) if mod else ALL
        tag = f"masque {mask:#04x}, active {active}" if mod else "origine"
        # 1. potard tourné : controlAll(this, param, delta)
        rig.held(0)
        rig.go(LOOP1, THIS, 0x29, 3)
        sets = rig.named("set")
        check([a[3] for a in sets] == want and all(a[0] == PS and a[1] == 0x29 and a[2] == 3 for a in sets),
              f"boucle 1 (potard) : set sur les pistes {want} ({tag})")
        check([a[3] for a in rig.named("getParam")] == want and all(a[0] == THIS and a[1] == 0x29 and a[2] == 0 for a in rig.named("getParam")),
              f"boucle 1 : getParam(this, param, FUNC non tenu, piste) pour {want} ({tag})")
        # 2. une valeur sur toutes les pistes : (this, valeur, x)
        rig.go(LOOP2, THIS, 0x40, 7)
        sets = rig.named("set")
        check([a[3] for a in sets] == want and all(a[0] == PS and a[1] == 0x40 and a[2] == 7 for a in sets),
              f"boucle 2 (valeur) : set sur les pistes {want} ({tag})")
        check([a[1] for a in rig.named("paramSet")] == want, f"boucle 2 : jeu de paramètres de chaque piste {want} ({tag})")
        # 3. destination du LFO : la boucle seule
        rig.run_loop3(THIS, 5)
        dest = rig.named("lfoDest")
        check([a[3] for a in dest] == want and all(a[0] == PS and a[1] == 0x20 and a[2] == 5 and a[4] == 0 and a[5] == 0 for a in dest),
              f"boucle 3 (LFO) : destination posée sur les pistes {want} ({tag})")
        # 4. TRACK + PUNCH/GATE : (x, touche 44), TRACK tenu
        rig.held(1)
        rig.go(LOOP4, 0, 44)
        pg = rig.named("punchGate")
        check([a[1] for a in pg] == want and all(a[0] == 44 for a in pg), f"boucle 4 (PUNCH/GATE) : bascule sur les pistes {want} ({tag})")
        # 5. écran MACHINES : (this, delta, TRACK tenu)
        rig.go(LOOP5, THIS5, 1, 1)
        wh = rig.named("wheel")
        check([a[2] for a in wh] == want and all(a[0] == 0x77 and a[1] == 1 and a[3] == 0 for a in wh),
              f"boucle 5 (MACHINES) : molette sur les pistes {want} ({tag})")
        check([a[1] for a in rig.named("trackMachine")] == want, f"boucle 5 : machine lue pour {want} ({tag})")
    if mod:
        rig.set_mask(0)


def event(rig, code, flags):
    rig.uc.mem_write(EVT, bytes(32))
    rig.w32(EVT + 12, code)
    rig.w32(EVT + 16, flags)


def keys_ok(rig, sym):
    mask, held = sym["cac_mask"], sym["cac_held"]
    rig.w8(mask, 0)
    rig.w8(held, 0)
    event(rig, 16, 1)                                   # TRIG 1 appuyé
    d0 = rig.go(sym["cac_keys"], VIEW, EVT)
    check(d0 == 1 and rig.r8(mask) == 0x01 and rig.r8(held) == 0x01 and rig.named("redraw") == [(VIEW, *rig.named("redraw")[0][1:])] and not rig.named("stockKeys"),
          "TRIG 1 appuyé : piste 1 écartée, appui noté, redessin des LED, pris")
    event(rig, 16, 0)                                   # relâché
    d0 = rig.go(sym["cac_keys"], VIEW, EVT)
    check(d0 == 1 and rig.r8(mask) == 0x01 and rig.r8(held) == 0 and not rig.named("stockKeys"), "TRIG 1 relâché : pris, appui oublié, masque intact")
    event(rig, 16, 0)                                   # relâché sans appui noté
    d0 = rig.go(sym["cac_keys"], VIEW, EVT)
    check(d0 == 0 and rig.named("stockKeys") == [(VIEW, EVT, *rig.named("stockKeys")[0][2:])], "TRIG 1 relâché sans appui noté : passe à l'origine")
    event(rig, 16, 1)                                   # appuyé de nouveau : remis
    rig.go(sym["cac_keys"], VIEW, EVT)
    check(rig.r8(mask) == 0 and rig.r8(held) == 0x01, "TRIG 1 appuyé de nouveau : piste 1 remise")
    event(rig, 16, 1 | 8)                               # répétition pendant l'appui
    d0 = rig.go(sym["cac_keys"], VIEW, EVT)
    check(d0 == 1 and rig.r8(mask) == 0 and not rig.named("stockKeys"), "répétition pendant l'appui : prise, sans bascule")
    rig.w8(held, 0)
    event(rig, 16, 1 | 8)                               # répétition sans appui noté
    d0 = rig.go(sym["cac_keys"], VIEW, EVT)
    check(d0 == 0 and rig.named("stockKeys"), "répétition sans appui noté : passe à l'origine")
    for n in range(6):                                  # les six pistes
        event(rig, 16 + n, 1)
        rig.go(sym["cac_keys"], VIEW, EVT)
    check(rig.r8(mask) == 0x3f and rig.r8(held) == 0x3f, "TRIG 1-6 appuyés : les six pistes écartées")
    event(rig, 2, 0)                                    # TRACK relâché
    d0 = rig.go(sym["cac_keys"], VIEW, EVT)
    check(d0 == 0 and rig.r8(held) == 0 and rig.r8(mask) == 0x3f and rig.named("stockKeys"), "TRACK : appuis oubliés, masque gardé, passe à l'origine")
    for code in (22, 31, 9, 0):                         # TRIG 7, TRIG 16, TRACK+RECORD, autre
        event(rig, code, 1)
        d0 = rig.go(sym["cac_keys"], VIEW, EVT)
        check(d0 == 0 and rig.named("stockKeys") and rig.r8(mask) == 0x3f, f"touche {code} : passe à l'origine, masque intact")
    rig.w8(mask, 0)


def leds_ok(rig, sym):
    for mask in (0x00, 0x01, 0x3f, 0x2a):
        rig.set_mask(mask)
        rig.uc.mem_write(OUT, bytes(16))
        rig.go(sym["cac_leds"], VIEW + 0x68, 7, OUT)
        st = rig.named("stockLeds")
        check(len(st) == 1 and st[0][:3] == (VIEW + 0x68, 7, OUT), f"producteur d'origine appelé avec ses arguments (masque {mask:#04x})")
        ls = rig.named("ledSet")
        want = [(LEDOBJ, n + 1, 1 if (mask >> n) & 1 else 2, OS_LED_ON) for n in ALL]
        check([a[:4] for a in ls] == want, f"TRIG 1-6 : {'/'.join('off' if (mask >> n) & 1 else 'on' for n in ALL)} (masque {mask:#04x})")
        check(rig.r32(OUT) == 0x7e and rig.uc.mem_read(OUT + 4, 12) == bytes(12), "bits 1..6 du mot 0 posés, le reste intact")
    rig.set_mask(0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True)
    ap.add_argument("--with", dest="others", default="", help="autres tweaks appliqués avec (ex. 6ch-usbup,model-tg-st)")
    ap.add_argument("--syntakt", help="Syntakt_OS1.42.syx, pour les moteurs du Syntakt")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    files = {json.loads(f.read_text(encoding="utf-8"))["id"]: f for f in TWEAK.parent.glob("[0-9]*.json")}
    tweak = json.loads(TWEAK.read_text(encoding="utf-8"))
    every = [json.loads(f.read_text(encoding="utf-8")) for i, f in files.items() if i != tweak["id"]]
    others = [json.loads(files[i].read_text(encoding="utf-8")) for i in args.others.split(",") if i]
    pl, _ = build.build_payload(others, stock, args.syntakt)
    base = build.apply_writes(stock, sorted(others, key=lambda t: t["order"]))[0] + pl
    img = build.apply_writes(stock, sorted(others + [tweak], key=lambda t: t["order"]))[0] + pl
    print(f"firmware : {', '.join(t['id'] for t in sorted(others + [tweak], key=lambda t: t['order']))}")
    print("1. écritures")
    sym = writes_ok(stock, img, tweak, every)
    print("2. cac_skip")
    skip_ok(Rig(img, sym))
    print("3. les cinq boucles de Control All, à l'origine")
    loops_ok(Rig(base, None), False)
    print("   … modifiées")
    loops_ok(Rig(img, sym), True)
    print("4. TRACK + TRIG 1-6 (cac_keys)")
    keys_ok(Rig(img, sym), sym)
    print("5. LED (cac_leds)")
    leds_ok(Rig(img, sym), sym)
    print("TOUT OK" if not FAIL else f"{len(FAIL)} ECHEC(S)")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
