#!/usr/bin/env python3
"""Checks BLAST's descriptor-state override and its stepped-SWEEP turn hook (Unicorn).

The registrar runtime calls BLAST's blast_state_init(knob) for SHAPE (1) and SWEEP (2), which return
BLAST's own interface objects, and 0 for COLOR/CONTOUR (the generic SNARE objects). Its turn entry calls
blast_turn(cur, delta) for the SWEEP knob, which steps the ratio list one detent at a time. This test maps
the OS's state-object area, seeds the SNARE objects, and calls the runtime entries directly; the entry
addresses come from the committed registrar.json (they shift when the runtime is reassembled).

    python3 tools/emu/test_blast_ui.py --cycles model-cycles_OS1.13.syx
"""
import argparse
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import test_feral9 as T          # noqa: E402  (Fw, main_os_from_syx)
from unicorn import m68k_const as mk  # noqa: E402

DEV = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13"
REG = HERE.parent / "machines" / "registrar" / "registrar.json"
FAIL = []


def check(ok, msg):
    print(("  ok    " if ok else "  ECHEC ") + msg, flush=True)
    if not ok:
        FAIL.append(msg)


def call_turn(e, turn, desc, delta, cur):
    """Sets up the turn entry's contract (d2 = desc, d3 = delta, d0 = cur, a2 = object, a3 = vt[20], the
    stack holding a2 and desc) and returns the uc, ready to run to 0x4000b834 (replaced) or 0x4000b830
    (replayed)."""
    uc = e.uc
    a2 = 0x40a71754
    sp = 0x9000e000
    uc.mem_write(sp, struct.pack(">II", a2, desc))
    uc.reg_write(mk.UC_M68K_REG_A7, sp)
    uc.reg_write(mk.UC_M68K_REG_D2, desc)
    uc.reg_write(mk.UC_M68K_REG_D3, delta)
    uc.reg_write(mk.UC_M68K_REG_D0, cur)
    uc.reg_write(mk.UC_M68K_REG_A2, a2)
    uc.reg_write(mk.UC_M68K_REG_A3, 0x4000b830)
    uc.mem_write(0x4000b830, b"\x4e\x71\x4e\x71")
    uc.mem_write(0x4000b834, b"\x4e\x71\x4e\x71")
    return uc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", required=True)
    args = ap.parse_args()
    stock = T.T.main_os_from_syx(args.cycles)
    tw = json.loads((DEV / "66-blast.json").read_text(encoding="utf-8"))
    reg = json.loads(REG.read_text(encoding="utf-8"))
    state_at = int(reg["runtime"]["entries"]["state_at"], 16)
    state_connect = int(reg["runtime"]["entries"]["state_connect"], 16)
    turn = int(reg["runtime"]["entries"]["turn"], 16)
    fw = T.Fw(stock, tw)
    e = fw.engine
    try:
        e.uc.mem_map(0x40a70000, 0x10000)
    except Exception:
        pass
    pattern = bytes((i * 7) & 0xff for i in range(100))
    for d in (51, 52, 53, 54):                       # SNARE's COLOR, SHAPE, SWEEP, CONTOUR objects
        e.uc.mem_write(0x40a71754 + 100 * d, pattern)

    # state_at: SHAPE (77) and SWEEP (78) -> BLAST's own objects; COLOR/CONTOUR (76, 79) -> generic SNARE.
    for desc in (77, 78):
        obj = e.call(state_at, desc)
        check(obj not in (0x40a71754 + 100 * 52, 0x40a71754 + 100 * 53)
              and struct.unpack(">I", e.uc.mem_read(obj, 100)[0x20:0x24])[0] != 0,
              f"state_at({desc}) returns BLAST's own object")
    for desc, idx in ((76, 51), (79, 54)):
        check(e.call(state_at, desc) == 0x40a71754 + 100 * idx,
              f"state_at({desc}) keeps SNARE's generic object (knob answered 0)")

    # state_connect: SHAPE and SWEEP go through BLAST's formatter, COLOR/CONTOUR through the generic one.
    rts = 0x40a70000
    e.uc.mem_write(rts, b"\x4e\x75")
    for d in (51, 54):
        obj = bytearray(pattern)
        obj[0x1c:0x20] = b"\x00\x00\x00\x01"
        obj[0x20:0x24] = rts.to_bytes(4, "big")
        e.uc.mem_write(0x40a71754 + 100 * d, bytes(obj))
    for desc in (77, 78):
        check(e.call(state_connect, desc) == 0x40a71500,
              f"state_connect({desc}) fills the value buffer through BLAST's object")
    for desc in (76, 79):
        check(e.call(state_connect, desc) == 0x40a71500,
              f"state_connect({desc}) fills the value buffer through the generic object")

    # turn: SWEEP (78) steps the ratio one detent; COLOR (76) and CONTOUR (79) keep the OS's own step.
    uc = call_turn(e, turn, 78, 0x100, 0)
    uc.emu_start(turn, 0x4000b834, count=1_000_000)
    check(uc.reg_read(mk.UC_M68K_REG_PC) == 0x4000b834 and uc.reg_read(mk.UC_M68K_REG_D0) == 0x0a00,
          "turn(78) replaces the value with the next ratio step (0x0a00)")
    uc = call_turn(e, turn, 76, 0x100, 0x1234)
    uc.emu_start(turn, 0x4000b830, count=1_000_000)
    check(uc.reg_read(mk.UC_M68K_REG_PC) == 0x4000b830 and uc.reg_read(mk.UC_M68K_REG_D0) == 0x1234,
          "turn(76) replays the OS's own step (value unchanged)")
    uc = call_turn(e, turn, 79, 0x100, 0x1234)
    uc.emu_start(turn, 0x4000b830, count=1_000_000)
    check(uc.reg_read(mk.UC_M68K_REG_PC) == 0x4000b830 and uc.reg_read(mk.UC_M68K_REG_D0) == 0x1234,
          "turn(79) replays the OS's own step (value unchanged)")

    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ECHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
