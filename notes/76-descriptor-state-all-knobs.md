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
separate hook, generalized the same way as this change and committed with the BLAST/PUNCH package ports (see
§Done below): a `turn` entry in the registrar runtime plus a per-machine `turn` initializer, never a hard-coded
descriptor.

## Done (2026-10-24) — compiled and proven in emulation

Built with `m68k-elf-gcc 16.2.0` + `binutils 2.47`, compiled from source into `~/m68k-elf-16.2` (no Homebrew: its
install needs the admin password; the host SDK was pinned to MacOSX26.5 because the default 27.0 SDK's `.tbd` files
broke the host linker). `--check` reproduces the committed objects byte for byte.

One fix to the never-compiled source: `feral_ui.S` compared the knob with `cmpi.l #1, 4(%sp)`, which is not a
ColdFire instruction (operand mismatch). It now loads the knob into a register first (`move.l 4(%sp), %d0;
cmpi.l #1, %d0`). The proof (`test_feral9_ui.py`) also seeds the generic SNARE objects with a trivial `rts`
formatter so the `state_connect` generic path runs.

Proven, all green: `gen_registrar.py --check`, `gen_feral9.py --check`, `test_feral9_ui.py` (SHAPE -> Feral names,
COLOR/SWEEP/CONTOUR -> generic), `test_feral9.py` (sound), `test_compose.py` (composed machines), `webcompose_check`
(`composer.js` == `compose.py`), and the flasher/registry/hash checks.

The BLAST, PUNCH and SAM package ports use the same `descriptor.state` entry: `blast_state_init(knob)` (SHAPE +
SWEEP), `punch_state_init(knob)` (COLOR + SHAPE + SWEEP) and `sam_state_init(knob)` (all four). The stepped SWEEP of
BLAST and PUNCH is a per-machine `turn` initializer (`blast_turn`, `punch_turn`) reached through the runtime's new
`turn` entry at the OS's knob turn `0x4000b82a`; the machine entry grew from 16 to 20 bytes to hold it. Each port
renders the same audio as its standalone build, sample for sample.

Addresses: VA of OS 1.13. `state_at` `0x4004df40`, `state_connect` `0x4004dfa2` (replaced by the registrar runtime
entries); interface objects `0x40a71754 + 100 i`; a package's machine entry `REGS + 16 + 20 i`, its descriptor-state
initializer in the long at `+12` and its turn hook at `+16`.

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
