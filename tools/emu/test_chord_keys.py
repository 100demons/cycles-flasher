#!/usr/bin/env python3
"""Preuve du clavier CHORD diatonique, sur le JSON final (notes/42).

Exécute le code ColdFire dans ses masques définitifs et les vraies routines OS
pour les événements de touches et pads, les menus, les patterns et le DSP. Les helpers
précisent leurs limites d'instrumentation ; ce n'est pas un démarrage complet
ni un test matériel. Durée : quelques minutes, surtout les 14 000 accords DSP.

    python3 tools/emu/test_chord_keys.py --cycles firmware/model-cycles_OS1.13.syx
    python3 tools/emu/test_chord_keys.py --cycles firmware/model-cycles_OS1.13.syx \\
        --with 6ch-usbup,latching-mute,trig-preview,browser-scroll,trig-hold,arp,tempo-max,boot-anim,syntakt-sd-cp-toy-bits-swarm \\
        --syntakt firmware/Syntakt_OS1.42.syx
"""
import argparse
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import build
from gen_chord_keys import HOOKS, load_stock
from chord_audio_checks import run_audio_checks, run_audio_storage_checks, run_audio_governor_checks
import chord_ui_checks
from probe_chord_storage import run_storage_checks

DIRECTORY = HERE.parents[1] / "tweaks/model-cycles_OS1.13"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", required=True)
    parser.add_argument("--with", dest="others", default="")
    parser.add_argument("--syntakt")
    args = parser.parse_args()
    stock = load_stock(args.cycles)
    by_id = {item["id"]: item for path in DIRECTORY.glob("*.json")
             if "id" in (item := json.loads(path.read_text()))}
    chosen = [by_id[key] for key in args.others.split(",") if key]
    tweak = by_id["chord-keys"]
    if any(item["id"] in tweak["conflicts"] for item in chosen):
        raise ValueError("Model-TG est explicitement incompatible avec chord-keys")
    symbols = {name: int(value, 0) for name, value in tweak["symbols"].items()}
    reference, _ = build.apply_writes(stock, chosen)
    patched, dirty = build.apply_writes(stock, chosen + [tweak])
    build.check_conflicts(chosen + [tweak])
    build.check_caves(stock, chosen + [tweak], False, dirty, patched,
                      json.loads((DIRECTORY / "device.json").read_text()).get("cave_refs_ok"))
    payload, _ = build.build_payload(chosen, stock, args.syntakt)
    reference, patched = bytes(reference) + payload, bytes(patched) + payload
    failures = []

    def check(condition, message):
        print(("ok    " if condition else "FAIL  ") + message, flush=True)
        if not condition:
            failures.append(message)

    print("firmware : " + ", ".join(item["id"] for item in chosen + [tweak]), flush=True)
    for address, expected, symbol, opcode in HOOKS:
        old = bytes.fromhex(expected)
        new = (struct.pack(">I", symbols[symbol]) if opcode is None else
               struct.pack(">HI", opcode, symbols[symbol]))
        new += b"\x4e\x71" * ((len(old) - len(new)) // 2)
        check(stock[address-build.BASE:address-build.BASE+len(old)] == old and
              patched[address-build.BASE:address-build.BASE+len(new)] == new and
              symbols[symbol] % 2 == 0,
              f"accroche {symbol} : contrat stock et destination paire vérifiés")
    interiors = [(address-build.BASE+2, address-build.BASE+len(bytes.fromhex(expected)))
                 for address, expected, _, opcode in HOOKS if opcode]
    sure, branches = build.refs_into(stock, interiors)
    check(not sure and not branches,
          f"aucun pointeur ni branchement vers l'intérieur des instructions détournées : {sure + branches}")
    overlap = []
    for other in by_id.values():
        if other["id"] in (tweak["id"], *tweak["conflicts"]):
            continue
        for a in tweak["writes"]:
            for b in other.get("writes", []):
                lo = max(a["off"], b["off"])
                hi = min(a["off"] + len(a["new"])//2, b["off"] + len(b["new"])//2)
                if lo < hi and bytes.fromhex(a["new"])[lo-a["off"]:hi-a["off"]] != bytes.fromhex(b["new"])[lo-b["off"]:hi-b["off"]]:
                    overlap.append((other["id"], lo))
    check(not overlap, f"aucun chevauchement avec les autres tweaks compatibles : {overlap}")
    try:
        run_storage_checks(reference, patched, symbols)
    except AssertionError as error:
        check(False, f"stockage : {error}")
    chord_ui_checks.run(reference, patched, symbols, check)
    extra_code = [(build.BASE + w["off"], len(w["new"])//2) for w in tweak["writes"]
                  if len(w["new"])//2 > 32]
    audio_failures = run_audio_checks(reference, patched, symbols["ck_audio_config"], extra_code)
    if audio_failures:
        failures.extend(["audio"] * audio_failures)
    storage_audio_failures = run_audio_storage_checks(reference, patched, extra_code)
    if storage_audio_failures:
        failures.extend(["stockage audio"] * storage_audio_failures)
    for governor in (item for item in chosen if item.get("gov")):
        governor_failures = run_audio_governor_checks(patched, governor, extra_code)
        if governor_failures:
            failures.extend(["régulateur audio"] * governor_failures)
    print("TOUT OK" if not failures else f"FAIL : {len(failures)} échecs", flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
