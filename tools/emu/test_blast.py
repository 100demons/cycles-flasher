#!/usr/bin/env python3
"""Proves the BLAST package renders the same audio, sample for sample, as the standalone BLAST machine.

The standalone BLAST (the committed 66-blast.json before this port) built the machine with
gen_macro.added_machine (B1 detours), hard-coded descriptors 77/78 and a detour at 0x4000b82a. The
package renders the same DSP (blast_update/blast_render, unchanged) through the registrar runtime, with
blast_state_init(knob) for the display and blast_turn for the stepped SWEEP. This test renders the same
notes and knob sweeps through the OLD standalone build (git HEAD's 66-blast.json) and the NEW package
(the regenerated 66-blast.json) in the real OS voice loop (Unicorn) and compares the audio sample for
sample.

    python3 tools/emu/test_blast.py --cycles model-cycles_OS1.13.syx
"""
import argparse
import json
import pathlib
import subprocess
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


def render(e, machine, color, shape, sweep, contour, note, gate=0, punch=0, decay=50):
    e.set(0, machine=machine, color=color, shape=shape, sweep=sweep, contour=contour,
          note=note, pitch=64, finetune=64, gate=gate, punch=punch, decay=decay)
    return np.stack([e.block(1 if b in (1, 120) else 0) for b in range(220)])[:, 0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", required=True)
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    new = json.loads((DEV / "66-blast.json").read_text(encoding="utf-8"))
    old = json.loads(subprocess.run(["git", "show", f"HEAD:tweaks/model-cycles_OS1.13/66-blast.json"],
                                    capture_output=True, text=True, cwd=HERE.parent.parent, check=True).stdout)
    fnew, fold = Fw(stock, new), Fw(stock, old)
    for fw in (fnew, fold):
        fw.engine.uc.mem_map(0x40800000, 0x01800000)   # OS BSS, incl. the trig velocity at 0x40fe4cdc
    check(not fnew.engine.unmapped, "new package: voice loop starts, no unmapped access")
    check(not fold.engine.unmapped, "old standalone: voice loop starts, no unmapped access")

    # a sweep of models and a few knob settings; each must render identical audio
    cases = [(0, 40, 0, 30, 36), (4, 100, 6, 60, 48), (13, 20, 12, 110, 60), (7, 64, 9, 40, 41)]
    for color, sweep, shape, contour, note in cases:
        a = render(fnew.engine, 6, color, shape, sweep, contour, note)
        b = render(fold.engine, 6, color, shape, sweep, contour, note)
        diff = int(np.abs(a.astype(np.int64) - b.astype(np.int64)).max())
        peak = int(np.abs(a).max())
        check(diff == 0 and peak > 1000000,
              f"shape {shape} sweep {sweep}: identical audio, peak {peak}, max diff {diff}")

    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ECHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
