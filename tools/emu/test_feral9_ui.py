#!/usr/bin/env python3
"""Checks Feral's descriptor-state override in the registrar runtime (Unicorn).

The runtime's state_at/state_connect call the package's state initializer for every knob of the
machine (COLOR .. CONTOUR, i.e. descriptors first_desc .. first_desc + 3), passing the knob index
(0 .. 3), and keep the generic SNARE state for a knob the initializer answers 0. This test maps the
OS's state-object area, seeds the SNARE objects, and calls both runtime entries directly, for all
four knobs. The entry addresses are read from the committed registrar.json (they shift when the
runtime is reassembled), so the test never hard-codes them.

    python3 tools/emu/test_feral9_ui.py --cycles model-cycles_OS1.13.syx
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
    tw = json.loads((DEV / "64-feral9.json").read_text(encoding="utf-8"))
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

    # state_at: SHAPE (descriptor 77) -> Feral's own object; COLOR/SWEEP/CONTOUR (76, 78, 79) -> generic SNARE.
    custom = e.call(state_at, 77)
    obj = e.uc.mem_read(custom, 100)
    same = (obj[:0x20] == pattern[:0x20] and obj[0x24:0x30] == pattern[0x24:0x30]
            and obj[0x34:] == pattern[0x34:])
    check(custom != 0x40a71754 + 100 * 52 and same
          and struct.unpack(">I", obj[0x20:0x24])[0] != 0
          and struct.unpack(">I", obj[0x30:0x34])[0] != 0,
          "state_at(77) returns Feral's own SHAPE object")
    for desc, idx in ((76, 51), (78, 53), (79, 54)):
        check(e.call(state_at, desc) == 0x40a71754 + 100 * idx,
              f"state_at({desc}) keeps SNARE's generic object (knob answered 0)")

    # state_connect: the value text goes through the object's formatter for SHAPE, the generic one otherwise.
    # The generic path runs the OS's formatter invoker (0x400ddf60) on the SNARE object, which jumps to the
    # object's formatter at +0x20. Give the generic SNARE objects a trivial "rts" formatter (and a nonzero
    # lazy-init flag at +0x1c) so the path completes and state_connect returns the value buffer.
    rts = 0x40a70000
    e.uc.mem_write(rts, b"\x4e\x75")                 # rts: the trivial formatter
    for d in (51, 53, 54):
        obj = bytearray(pattern)
        obj[0x1c:0x20] = b"\x00\x00\x00\x01"         # nonzero flag: skip the OS's lazy init (0x400f692a)
        obj[0x20:0x24] = rts.to_bytes(4, "big")      # the formatter = rts
        e.uc.mem_write(0x40a71754 + 100 * d, bytes(obj))

    check(e.call(state_connect, 77) == 0x40a71500, "state_connect(77) fills the value buffer through Feral's object")
    for desc in (76, 78, 79):
        check(e.call(state_connect, desc) == 0x40a71500,
              f"state_connect({desc}) fills the value buffer through the generic object")

    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ECHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
