#!/usr/bin/env python3
"""Checks Feral's descriptor-state override in the registrar runtime (Unicorn).

The runtime's state_at/state_connect call the package's state initializer for the machine's
SHAPE descriptor (first_desc + 1), and keep the generic SNARE state for every other descriptor.
This test maps the OS's state-object area, seeds the SNARE SHAPE object, and calls both runtime
entries directly.

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
    fw = T.Fw(stock, tw)
    e = fw.engine
    try:
        e.uc.mem_map(0x40a70000, 0x10000)
    except Exception:
        pass
    pattern = bytes((i * 7) & 0xff for i in range(100))
    e.uc.mem_write(0x40a71754 + 100 * 52, pattern)       # SNARE's SHAPE state object
    d0 = e.call(0x43033028, 77)                            # runtime state_at, Feral SHAPE
    custom = e.uc.mem_read(d0, 100)
    generic = e.call(0x43033028, 76)                       # runtime state_at, COLOR
    same = custom[:0x20] == pattern[:0x20] and custom[0x24:0x30] == pattern[0x24:0x30] and custom[0x34:] == pattern[0x34:]
    check(d0 != 0x40a71754 + 100 * 52 and same and struct.unpack(">I", custom[0x20:0x24])[0] != 0
          and struct.unpack(">I", custom[0x30:0x34])[0] != 0, "state_at returns Feral's own state object")
    check(generic == 0x40a71754 + 100 * 51, "state_at keeps SNARE's object for another descriptor")
    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ECHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
