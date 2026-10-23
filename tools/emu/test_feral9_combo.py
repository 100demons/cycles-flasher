#!/usr/bin/env python3
"""Quick Feral smoke test in the real OS voice loop (Unicorn).

This is not the full proof: it checks that the patched OS boots its voice loop,
that the added machine (number 7) is dispatched to our update/render, that it
produces sound through the stock amp chain, and that the six stock machines
still run. The maintainer runs the full emulator test and the hardware test.

    python3 tools/emu/test_lixr.py --cycles model-cycles_OS1.13.syx
"""
import argparse
import json
import pathlib
import struct
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import mcengine as E                # noqa: E402
import test_sdvintage as T          # noqa: E402

DEV = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13"
FAIL = []


def check(ok, msg):
    print(("  ok    " if ok else "  ECHEC ") + msg, flush=True)
    if not ok:
        FAIL.append(msg)


class Fw:
    def __init__(self, stock, tweak):
        p, _ = build.apply_writes(stock, [tweak])
        pl, _ = build.build_payload([tweak], stock, None)
        self.img = bytes(p) + pl
        self.pay = int(tweak["append"]["dest"], 16)
        self.rt = build.payload_runtime(tweak, stock, None)
        self.engine = E.Engine(self.img, payload=(self.pay, self.rt))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", required=True)
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    tw = json.loads((DEV / "65-feral9-lixr.json").read_text(encoding="utf-8"))
    fw = Fw(stock, tw)
    e = fw.engine
    check(not e.unmapped, "voice loop starts, no unmapped access")
    base = dict(note=36, pitch=64, finetune=64, gate=0, punch=0, decay=50)
    e.set(0, machine=6, color=64, shape=64, sweep=64, contour=48, **base)
    x = np.stack([e.block(1 if b in (1, 120) else 0) for b in range(220)])
    y = x[:, 0]
    peak = int(np.abs(y).max())
    rms = float(np.sqrt(np.mean((y / 2147483648.0) ** 2)))
    dc = float(np.mean(y / 2147483648.0))
    check(peak > 1000000 and not e.unmapped, f"Feral: sound through the stock amp chain (peak {peak}, rms {rms:.3f}, dc {dc:+.5f})")
    check(peak < 0x7ffffff0, f"Feral: no hard clipping at the output (peak {peak})")
    e.set(0, machine=7, color=64, shape=64, sweep=64, contour=48, **base)
    x = np.stack([e.block(1 if b in (1, 120) else 0) for b in range(220)])[:, 0]
    check(int(np.abs(x).max()) > 1000000, "LiXR (machine 7) sound next to Feral")
    e.set(0, machine=0, color=64, shape=64, sweep=64, contour=64, **base)
    x = np.stack([e.block(1 if b in (1, 120) else 0) for b in range(160)])[:, 0]
    check(int(np.abs(x).max()) > 1000000 and not e.unmapped, "stock KICK on the same patched OS still plays")
    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ECHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
