# 76 — The descriptor-state override covers all four knobs (not just SHAPE)

**Problem:** an added machine's custom value-window text (the 3-character model names on SHAPE for Feral, BLAST,
PUNCH, SAM; the 3-character FM ratios on SWEEP for BLAST and PUNCH) was wired only for **SHAPE**. The registrar
runtime's `state_at`/`state_connect` dispatched to a package's initializer for `first_desc + 1` only, `compose.py`
and `composer.js` rejected any `descriptor.state` whose `descriptor` was not `1`, and each machine entry held one
initializer slot. SWEEP (and COLOR/CONTOUR) had no override path at all, so a machine composed at a slot showed the
raw number instead of its names. The old standalone machines (BLAST, PUNCH, SAM) worked around it by detouring the
OS's `state_at`/`state_connect` with hard-coded descriptors 76–79, which only holds for the 7th machine.

**Fix:** the override is now one **knob-state initializer per machine, for all four knobs at once** — there is no
per-knob `descriptor` field left to get wrong, and no hard-coded descriptor number.

- `manifest.json`: one `uses` entry `{ "point": "descriptor.state", "init": "<symbol>", "why": "…" }`.
- `init` has the signature `init(knob) -> state*`, `knob` = **0 = COLOR, 1 = SHAPE, 2 = SWEEP, 3 = CONTOUR** (the
  position among the machine's four knobs, not a descriptor number). It returns that knob's interface object, or **0**
  to keep the generic SNARE object.
- `registrar.S` `state_at`/`state_connect`: for a descriptor in `[first_desc, first_desc + 3]`, call `init(desc −
  first_desc)`; a **0** return falls back to `map_state` (SNARE's object). Amp Decay (`first_desc + 4`) is never
  overridden.
- `compose.py` and `docs/flasher/composer.js` accept the entry as-is and write the `init` address into the machine
  entry (its `state_init` long), unchanged from before apart from the removed SHAPE-only check.

The contract is also written into the new-repo architecture (`FLASHER REDO/ARCHITECTURE.md` §2.3) so a future repo
implements it this way from the start. The knob-turn stepping for the stepped SWEEP ratios (BLAST, PUNCH) is a
separate, still-to-generalize hook, not part of this change.

**What still needs the toolchain (not done here — no m68k cross-compiler in this environment):** recompiling
`feral9.o` (its `feral_state_init` now reads the knob index and returns 0 for non-SHAPE), regenerating
`registrar.json`/`frame.json`, `64-feral9.json`, `docs/flasher/tweaks.js`, and the emulation proofs; then the BLAST,
PUNCH and SAM packages can use the same entry (their old `*_state_at` already take a descriptor — they become the
initializer). See the commands below.

Addresses: VA of OS 1.13. `state_at` `0x4004df40`, `state_connect` `0x4004dfa2` (replaced by the registrar runtime
entries); interface objects `0x40a71754 + 100 i`; a package's machine entry `REGS + 16 + 16 i`, its initializer in
the last long (`+12`).

## Regeneration (with the m68k toolchain)

```sh
python3 tools/gen_registrar.py --cycles firmware/model-cycles_OS1.13.syx   # registrar.json + frame.json
python3 tools/gen_feral9.py --cycles firmware/model-cycles_OS1.13.syx --check  # feral9.o + 64-feral9.json
python3 tools/emu/test_feral9_ui.py --cycles firmware/model-cycles_OS1.13.syx  # state override for all four knobs
python3 tools/gen_flasher_tweaks.py                                        # docs/flasher/tweaks.js
python3 tools/check_overlaps.py
tools/webcompose_check.sh firmware/model-cycles_OS1.13.syx
python3 tools/ref_mainos.py --cycles firmware/model-cycles_OS1.13.syx --syntakt firmware/Syntakt_OS1.42.syx
```
