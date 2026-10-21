# 60 — Level B, step 2: a relocator and a table-driven registrar, no toolchain at build time (plan)

**Status: plan, 2026-10-21. Nothing of it is built.** This is increment B2 of [notes/59](59-level-b-builder.md)
(§3 the registrar runtime, §4 steps 4 and 6 of the composer, §7 item 2), written after B1 landed (`91edc68`:
`tools/compose.py`, the manifests, the reference machine, `28-refmachine.json`). It says what B1 still needs the
m68k toolchain for, measured in the code, how each of those uses becomes committed data plus Python, in which order
to build it, and how to prove each piece without an emulator first. Addresses are VAs of OS 1.13; payload offsets
from `gs.PAY_ALONE` (`0x43000000`); sizes measured on 2026-10-21 with `m68k-elf-gcc` 16.2.

## 0. In short

- **B1 calls the toolchain in two places.** (a) `compose.compile_package`: `gcc`, `ld`, `objcopy`, `nm` for every
  package, every build. (b) `gm.added_machine`: two `assemble()` calls, the detours (`gs.detours_asm`, 606 bytes
  for one machine, 774 for two, 1 094 for six) and the boot stub (`stub.S`, 64 bytes of code plus 8 per segment).
  Everything else in `added_machine` is Python already: the data block, the five descriptors per machine, the
  moved-table references, the 43 bounds, the 7 jumps and the call, the payload parts and the conflict list.
- **B2 replaces both.** (a) becomes a committed relocatable object per package and a relocator in Python (the
  objects carry only `R_68K_32`, §1); (b) becomes two committed binaries with parameter areas, a **registrar
  runtime** that loops over a machine table instead of carrying its constants in `moveq` chains, and a **stub
  template** whose three immediates and segment table the composer fills. After B2, `compose.py` runs with
  `python3` alone; the toolchain is needed only by the generators that build the committed pieces
  (`gen_sampler.py`, `gen_refmachine.py`, a new `gen_registrar.py`), each with `--check`.
- **Two proofs need no emulator.** The relocator is proven against `ld` byte for byte: with the same section order
  and only absolute relocations, the two must produce the same bytes (§3). The runtime is proven by a differential
  against B1: for every selection, the same writes and the same payload except the detour part and the eight sites
  that jump to it (§5). Behaviour is then digiemu and the device; Unicorn when a Python with a wheel exists (§8).
- **Three sub-steps, each committed alone:** B2a the relocator and patch points as symbols, B2b the stub template,
  B2c the runtime and the composer's own writes. After B2c, `27-sampler.json` and `28-refmachine.json` are
  regenerated through the composer (their detour bytes change, nothing else), so SAMPLE alone needs a hardware
  test again before a release.

## 1. What was measured (2026-10-21)

| What | Measured |
|---|---|
| `refmachine.o` | 2 388 bytes; 5 relocations, all `R_68K_32`, in `.rela.*` sections (RELA: type, symbol, addend); sections `.text.ref_update` 0x286, `.text.ref_render` 0x25e, `.rodata.semi` 0x34, `.bss.trk` 0xc0 |
| SAMPLE's 9 objects after `ld -r` | one object of 39 100 bytes; 69 input sections kept apart (`-ffunction-sections`); 132 relocations, all `R_68K_32`, 101 against section symbols, 31 against named symbols; no undefined symbol; alignments 1 and 2 |
| ELF | ELF32, big endian, `e_machine` 68000, type REL. No `pyelftools` here; the reader is `struct` (about 80 lines) |
| Detours (`gs.detours_asm`, `tg=None`, no lo-fi) | n = 1: 606 bytes; n = 2: 774; n = 3: 854; n = 6: 1 094. Room `STUBS..DATA` 2 048 bytes |
| Per-build instructions in the detours | `map_state` (`cmp.l #last`), `cc_bounds` (`moveq #top`), `shown` (one compare per machine), `record_at` / `record_of` and `rec_i` (one compare and one `lea RECS + 0x60 i` per machine, `moveq #first_desc − 51`), `knob_vec` (`top`, `first`, `lea DATA + 12 nm`), `desc_machine` / `builder_row` (two compares per machine), `marks` (`moveq #nm`, only when nm > 7). Constant: `state_at`, `state_connect`, `drum_icons`, `small_icon`, `rec_build` |
| Boot stub (`PACK`, 4 segments) | 104 bytes: 64 of code, 8 per segment, 8 of terminator. Immediates: `lea PAYLOAD_DST` at offset 2, `move.l #PAYLOAD_LONGS` at 8, `lea PAYLOAD_SRC` at 24; the segment table follows the code (`lea segs(%pc)`). Room: `STUB_END − CAVE` = 192 bytes, so 15 segments at most (today 4 or 5) |
| Python | 3.14.2; neither `unicorn` nor `elftools` installed; no 3.12/3.13 on the path |
| Patch points in One-Shot | `SAMPLE_MACHINE` in `pool.c:60` and `view.c:172`; `DESC_START` in `view.c:190` (and `DESC_LENGTH`); both `#ifndef` defaults 6 / 76 |

## 2. The package after B2: a committed object

- **`build.objects`** (standard §4: `objects`, `symbols`, `patch_points`) names one relocatable object,
  `tools/machines/<id>/<id>.o`, produced by the package's generator: compile the sources with the package's flags,
  then `m68k-elf-ld -r` into one file. The object is **committed**, like the tweak JSONs are, and `--check`
  rebuilds and compares it. The sources stay next to it, for reading and for rebuilding. `build.sources`,
  `cflags`, `include` and `defines` stay in the manifest as the recipe of the object; `symbols` and `keep` are the
  relocator's roots.
- **Patch points become symbols, not defines.** Today `SAMPLE_MACHINE` and `DESC_START` are compile-time constants,
  so an object compiled once would carry one index for ever. In B2 the package declares them as undefined symbols
  whose *address* is the value:

  ```c
  extern char cm_machine_index[];                     /* defined by the composer, value = the index */
  #define SAMPLE_MACHINE ((int)(long)cm_machine_index)
  ```

  The compiler emits `move.l #cm_machine_index, %d0` with an `R_68K_32` against the undefined symbol, and the
  composer resolves it like `ld --defsym` would. Cost: 6 bytes instead of 2 at three sites, nothing at run time
  beyond that. Manifest: `"patch_points": [{"symbol": "cm_machine_index", "kind": "machine_index"}, {"symbol":
  "cm_descriptor_base", "kind": "descriptor_base"}]` (the standard's table says symbol + kind; its SAMPLE example
  still shows the define names and is aligned when the standard moves to 0.2). The relocator refuses any other
  undefined symbol by name. For the B1 path (`ld`) the same manifest entries become `--defsym` arguments.
- **This touches One-Shot.** `pool.h` and `view.c` are One-Shot's; the change is a few lines, keeps One-Shot's own
  `machine/build.py` working (it passes `--defsym`), and ships as One-Shot 0.8, which model27 then pins (the
  `UPSTREAM_COMMIT` of `gen_sampler.py`). The reference machine has no patch point.
- **The object's fingerprint.** The `.comment` section of the object names the compiler (`GCC: (GNU) 16.2.0`);
  `--check` reads it, so a package rebuilt with another compiler is refused before the bytes are compared, and the
  message says which compiler the committed object came from.

## 3. B2a: the relocator

`tools/relocate.py` (standard library only), used by `compose.py` in place of `compile_package` and returning the
same triple (blob from `code_at` to the end of the data, symbols, end of the variables):

1. **Read** the ELF32 big-endian object: section headers, `.symtab` + `.strtab`, every `.rela.*` section (`r_offset`,
   `r_info` → symbol index and type, `r_addend`). Refuse a type other than `R_68K_32` (1), naming the section and
   offset.
2. **Collect garbage** like `ld --gc-sections`: roots are the sections of `symbols.update`, `symbols.render` and
   every `keep` symbol; follow relocations from root sections to the sections they reference (section symbols
   and named symbols alike); drop the rest. Without this, SAMPLE's unused helpers would be placed (B1's `ld`
   drops them, so the comparison of step 6 would fail; that is how the rule is checked).
3. **Place** the kept sections in B1's order, which is the linker script's: the section holding `update`, then the
   one holding `render`, then the other `.text*` in file order, then `.rodata*`, then `.data*`, each at its
   `sh_addralign` (1 or 2 here; `ld` honours the same field), from `code_at`; `.bss*` from `bss_at`, not emitted.
   Refuse when the code end passes `code_end` (`gs.STUBS`) as today.
4. **Resolve** every symbol: section symbol → the section's placed address; defined symbol → its section's address
   plus `st_value`; undefined symbol → the composer's value for its patch point, else an error naming it.
5. **Apply**: for each relocation, write `S + A` as 4 bytes big endian at the placed address of the section plus
   `r_offset`. Nothing else: no PC-relative, no 16-bit, no GOT.
6. **Prove against `ld`**: `compose.py --compare-ld` builds every package both ways (B1's `compile_package` and
   the relocator over the object `ld -r` produced from the same compile) and compares blob, symbols and BSS end
   **byte for byte**, for `sampler`, `refmachine`, and the two pairs. Because every relocation is absolute, equal
   placement means equal bytes; a difference is a placement or alignment rule the relocator got wrong, and the
   diff says where. This is B2a's done criterion and needs no emulator and no device.

About 200 lines of Python. The relocator is also the specification of B3's JavaScript relocator (notes/59 §5):
the same steps over the same object bytes.

## 4. B2b: the boot stub template

`gen_registrar.py` assembles `stub.S` once with `PACK` and placeholder values, and commits the 64 bytes of code
with the offsets of its three immediates (2: destination, 8: length in longs, 24: source) in
`tools/machines/registrar/registrar.json`. The composer copies the template, writes the three values, appends the
segment table (`.long address, longs` per segment, then `0, 0`) and checks `CAVE + length ≤ STUB_END` (192 bytes,
15 segments). Proof: for every B1 selection the result equals the stub B1 assembles, byte for byte (same source,
same values). `stub.S` keeps its other variants (`APLIB`, `BOOT2`, `CHAIN_TO`, the SRAM copies) for the Syntakt and
Model-TG generators; B2 uses the plain `PACK` form only.

## 5. B2c: the registrar runtime

### 5.1 Code assembled once, a parameter block filled per build

`tools/machines/registrar/registrar.S`, written by hand from `gs.detours_asm(n, …, tg=None, lofi=None)`, assembled
once at `gs.STUBS` (`0x43033000`) by `gen_registrar.py`, committed as hex in `registrar.json` with its symbol
table (`state_at`, `state_connect`, `cc_bounds`, `drum_icons`, `small_icon`, `record_at`, `record_of`,
`knob_vec`, `desc_machine`, `builder_row`, `marks`: the targets of `g7.JUMPS`, `g8.JUMPS8` and `g7.CALLS`), which
are now **fixed addresses**. The parameter block `regs` lives at a fixed offset in the same area, the last 128 bytes
(`STUBS + 0x780`), away from the code:

```
regs+0   .byte  n, first (6), top (first + n − 1), last (76 + 5 n)
regs+4   .long  knob_tab                 ; DATA + 12 (first + n): knob_vec's table machine -> record
regs+8   machine[6], 16 bytes each:
         .byte  image, first_desc, rec_param (first_desc − 51), 0
         .long  rec                      ; RECS + 0x60 i
         .long  knob_hook                ; 0; MACRO's lo-fi would go here (notes/59 §3)
         .long  0
```

What each entry does with it (register contract of the generated detour kept, see 5.2):

| Entry | Today | B2c |
|---|---|---|
| `map_state` | `cmp.l #last` | reads `last` from `regs+3` |
| `cc_bounds` | `moveq #top` | reads `top` |
| `shown` | n unrolled compares | loop over `machine[]`, returns `image` of the entry whose index is `first + i` |
| `record_at`, `record_of` | n compares each, `rec_i` stubs with `lea RECS + 0x60 i` and `moveq #first_desc − 51` | one loop, `rec` and `rec_param` from the entry, then `rec_build` unchanged |
| `knob_vec` | `moveq #top`, `moveq #first`, `lea DATA + 12 nm` | reads `top`, `first`, `knob_tab`; calls `knob_hook` when non-zero |
| `desc_machine`, `builder_row` | two compares per machine | loop: `first_desc ≤ d ≤ first_desc + 3` → `first + i` |
| `marks` | assembled only when nm > 7, `moveq #nm` | always present, reads `first + n`; the composer still writes the `jmp marks` at `0x400a26a2` only when nm > 7 and the `moveq` at `0x400a26e8` otherwise, as today |
| `state_at`, `state_connect`, `drum_icons`, `small_icon`, `rec_build` | constant | unchanged |

Expected size: 700 to 800 bytes constant (the unrolled n = 6 version is 1 094; loops are shorter), well inside the
2 048 minus 128. Limits unchanged: n ≤ 6 (`gs.check_room`), nm ≤ 14 (two rows of marks). With Model-TG the
runtime is not used: model27 does not offer Model-TG, and the TG variant stays in `gen_macro.added_machine` for
the generators that still need it.

### 5.2 Register contract per entry `[À FAIRE in B2c]`

Each generated detour clobbers a known set of registers because its caller's live registers were read when the
detour was written (notes/18, 20, 43). A loop needs one more register than an unrolled compare; the runtime must
not clobber more than today's detour does at that entry, or must save and restore (and then fix every
`4(%sp)`-style argument offset). Before writing `registrar.S`, table for each entry: registers the generated
detour uses today (from `detours_asm`: `shown` d0 d1; `record_at` / `record_of` d0 d1 a0; `desc_machine` d0 d1 a0;
`builder_row` d0 d2 d5; `knob_vec` d0 d1 a1 (+ d2 d3 d5 read); `cc_bounds` d0 d1 d2; `map_state` d0 d1) and what
the caller holds live after the detour returns or jumps on. That table goes into this note's §5.2 when done.

### 5.3 The composer's own writes

`compose.registrar_writes(img, machines, blobs, bss_end)` replaces the call to `gm.added_machine` for the
alone layout: a port of its Python arithmetic (data block, descriptors, moved references with `refs32`, bounds,
small bounds, jumps and the call to the **fixed** runtime symbols, the `Algorithm` maximum, `reloc`, `segments`,
the stub from the template, the parameter block as one more payload part at `STUBS + 0x780`). `gm.added_machine`
itself is not changed: `gen_macro.py`, `gen_acid.py` and the Syntakt generators keep using it.

### 5.4 Proof

1. **Differential against B1**, `compose.py --compare-b1`, for `sampler`, `refmachine`, `sampler+refmachine`,
   `refmachine+sampler`, and each with `arp` and `trig-hold`: the two tweaks have the same writes except the eight
   sites of `JUMPS` / `JUMPS8` / `CALLS` (whose targets are now the runtime's fixed symbols) and the same payload
   parts except the `STUBS` part (runtime + block instead of generated detours). The stub write is identical
   (B2b). Anything else that differs is a bug in the port.
2. **digiemu**, by the maintainer: boot, MACHINES page (names, marks, pictures), knob names and ranges, machine
   locks across the added machines, a sound saved and reloaded, and each machine's sound against the B1 image.
3. **Unicorn**, when available (§8): the UI checks of `test_syntakt_machines.py` adapted to the runtime (they
   already walk the MACHINES page, the rows and the records) and `mcengine` for the sound, track by track, B2 image
   against B1 image, bit for bit.
4. **Hardware**, by the maintainer, before `27-sampler.json` is regenerated for the flasher.

## 6. The composer after B2

- `compose.py --relocator python` (default once B2a is proven) or `--relocator ld` (development, toolchain);
  `--compare-ld` and `--compare-b1` as above. `compose.py` imports neither `gen_macro` nor the assembler any more;
  it reads `registrar.json`, the packages' objects and manifests, and the user's official OS.
- `gen_sampler.py` and `gen_refmachine.py` become: compile, `ld -r`, write `<id>.o` (`--check`), then call
  `compose.compose` for the tweak JSON, so the committed JSON is the composer's output and `build.py -t sampler`
  equals `compose.py --machines sampler` by construction.
- `ref_mainos.py`, `check_overlaps.py`, `registry.py`, `gen_flasher_tweaks.py`, `build.py` and the flasher:
  unchanged, they consume the JSON. `REF_MODS` / `REF_MAINOS` regenerate when the JSONs change.
- No toolchain: `compose.py`, `build.py`, the flasher checks. Toolchain: the three generators, with `--check` in
  the same place the tweak checks run today.

## 7. Order of work and done criteria

| Step | Work | Done when |
|---|---|---|
| **B2a** | `tools/relocate.py`; `compose.py --relocator`, `--compare-ld`; patch points as symbols in One-Shot (0.8, re-pinned) and in the manifests; `gen_sampler.py` / `gen_refmachine.py` emit and check `<id>.o` | relocator = `ld` byte for byte for both packages and both pairs; `compose.py --machines sampler` still reproduces `27-sampler.json` |
| **B2b** | `gen_registrar.py` (stub part), `registrar.json` with the template; composer fills it | stub bytes = B1's for every selection |
| **B2c** | `registrar.S`, the runtime part of `gen_registrar.py` / `registrar.json`, `compose.registrar_writes`, `--compare-b1`; regenerate `27-sampler.json` and `28-refmachine.json` | differential clean; digiemu by the maintainer; then hardware for SAMPLE alone and the pair |

One commit per step, with the trailer. Each step leaves B1's path working until its own is proven, so a
half-finished step never blocks a build.

## 8. Risks and open points

- **Placement rules of `ld`** (order inside `*(.text*)`, alignment, `.data` after `.rodata`): `--compare-ld`
  settles them; until equal, B2a is not done. `[HYP]` file order and `sh_addralign` are the whole rule.
- **Register contract** when unrolled compares become loops (§5.2): read the callers again; a wrong clobber
  shows in digiemu as a wrong knob name or record, not as a crash, so the UI checks matter.
- **Emulation harness**: `mcengine.PAYLOAD_CODE` is fixed (`0x43000000..0x43007298`, `0x43031000..0x43032000`) and
  SAMPLE's code runs to `0x43007727`; the harness must take the code ranges from the tweak's parts before it can
  place EMAC hooks in a composed image `[À FAIRE with Unicorn]`.
- **Unicorn**: no wheel for Python 3.14; `brew install python@3.13` and a venv (outside the sandbox, the
  maintainer's call) is the known way. Until then the proofs are §3 step 6, §5.4 step 1 and digiemu.
- **One-Shot 0.8** is a prerequisite of composing SAMPLE at an index other than 6 from a committed object. The
  convention of notes/59 §6 (SAMPLE first, index 6) holds anyway until B4's registry.
- **Byte changes for users**: after B2c the SAMPLE tweak's detour bytes differ from the hardware-tested 0.7 build;
  `tests.hardware` of the sampler manifest and the flasher card's `HW_TESTED` go back to "not yet" until the
  maintainer flashes the regenerated build.
