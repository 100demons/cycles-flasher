#!/usr/bin/env python3
"""Checks SAM's descriptor-state override (Unicorn).

The registrar runtime calls SAM's sam_state_init(knob) for every knob: COLOR (0, the speaking rate),
SHAPE (1, the word), SWEEP (2, the scrub) and CONTOUR (3, the character macro) each return SAM's own
interface object. This test maps the OS's state-object area, seeds the SNARE objects, and calls the
runtime entries directly; the entry addresses come from the committed registrar.json.

    python3 tools/emu/test_sam_ui.py --cycles model-cycles_OS1.13.syx
"""
import argparse
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import test_feral9 as T          # noqa: E402

DEV = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13"
REG = HERE.parent / "machines" / "registrar" / "registrar.json"
FAIL = []


def check(ok, msg):
    print(("  ok    " if ok else "  ECHEC ") + msg, flush=True)
    if not ok:
        FAIL.append(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", required=True)
    args = ap.parse_args()
    stock = T.T.main_os_from_syx(args.cycles)
    tw = json.loads((DEV / "38-sam.json").read_text(encoding="utf-8"))
    reg = json.loads(REG.read_text(encoding="utf-8"))
    state_at = int(reg["runtime"]["entries"]["state_at"], 16)
    state_connect = int(reg["runtime"]["entries"]["state_connect"], 16)
    fw = T.Fw(stock, tw)
    e = fw.engine
    try:
        e.uc.mem_map(0x40a70000, 0x10000)
    except Exception:
        pass
    pattern = bytes((i * 7) & 0xff for i in range(100))
    for d in (51, 52, 53, 54):                       # SNARE's COLOR, SHAPE, SWEEP, CONTOUR objects
        e.uc.mem_write(0x40a71754 + 100 * d, pattern)

    # state_at: every knob -> SAM's own object (COLOR, SHAPE, SWEEP, CONTOUR).
    for desc in (76, 77, 78, 79):
        obj = e.call(state_at, desc)
        check(obj not in (0x40a71754 + 100 * 51, 0x40a71754 + 100 * 52,
                          0x40a71754 + 100 * 53, 0x40a71754 + 100 * 54)
              and struct.unpack(">I", e.uc.mem_read(obj, 100)[0x20:0x24])[0] != 0,
              f"state_at({desc}) returns SAM's own object")

    # state_connect: every knob fills the value buffer through SAM's formatter.
    for desc in (76, 77, 78, 79):
        check(e.call(state_connect, desc) == 0x40a71500,
              f"state_connect({desc}) fills the value buffer through SAM's object")

    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ECHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
