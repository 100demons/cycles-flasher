# 62 — Level B, step 4: stable machine ids (plan)

**Status: plan, 2026-10-22; decided the same day: option C, today's numbering stays, no stable ids (§9).** This is the part of increment B4 of [notes/59](59-level-b-builder.md) (§6, §7 item 4)
that has to come before a second machine card: every machine package gets a permanent number, so that a saved sound
finds its machine whatever else the build holds. The dispatcher tables and the machine shortcuts, the other half of
B4, are only an outlook here (§8): they wait until the second machine is known. Addresses are VAs of OS 1.13. The
measurements were made on 2026-10-22 with the official `model-cycles_OS1.13.syx` and a throwaway prototype in
`_scratch/b4-measure/`, which is not committed.

## 0. In short

- **Decided (§9): option C.** The maintainer takes a machine that changes with the selection as a happy
  accident, not a fault: who wants the same sounds keeps one project per build. No registry, no placeholder; what
  the plan below measured stays as a record, should the question come back.
- **The problem.** The composer numbers the added machines 6, 7, … in the order it gets them. A sound stores the
  number of its machine, and so does a pattern's machine lock. With one machine card SAMPLE is always 6. With a
  second card X, X is 6 alone and 7 next to SAMPLE, so a sound saved with X alone plays SAMPLE after the next flash.
- **The plan: option A of the standard** ([STANDARD.md](https://github.com/durchgemacht/cycles-mod-standard) §5.1).
  A registry file gives each machine package a permanent id from 6 upward. The composer numbers by id and fills each
  gap with a silent placeholder machine named `----`.
- **Measured.** The placeholder is 22 bytes of code and costs 344 to 408 bytes in the image per gap. The composer
  already builds a gap without any change, because the placeholder is just a package: B4 changes the ordering and
  the filling, not the registrar runtime or `frame.json`.
- **For users nothing changes while SAMPLE is the only machine.** SAMPLE keeps 6 and its firmware stays the same,
  byte for byte (`27-sampler.json`, `REF_MAINOS["sampler"]`).
- **Open for the maintainer** (§7): which ids a build fills, the placeholder's look, where the registry lives, the
  reference machine, the size of the id space.

## 1. What a machine number is (measured)

### 1.1 Where it is stored

- **In the sound.** A sound is 100 bytes, and `+38` is its machine, the high byte of parameter k 9 "Algorithm"
  (standard §2.3, [notes/18](18-septieme-machine.md) §1). That covers the kit's six track sounds, its pool of 64
  sounds and the presets on the +Drive.
- **In patterns.** A step can lock the machine (machine locks, notes/18 §1), so patterns store the number too.
- **Shared parameters.** The parameter values are stored per slot and shared by every machine (notes/18 §1). A sound
  played on another machine than the one it was saved with is therefore never refused: it plays the other machine
  with the same values.

### 1.2 How the OS uses it

- Machines 0 to 5 are the stock ones. The added machines run from 6 to `top`. The maximum of the "Algorithm"
  parameter is `top`, which the composer writes for each build (the frame's `reloc`, notes/61 §11).
- A number above `top` (code reading, notes/18 §2 and §4):
  - the voice loop falls back to 5 at `0x400a7dc0`, so the track plays CHORD;
  - the MACHINES page writes "Error" and draws no icon (`0x400a25e0`);
  - the machine setter refuses the value (`0x400147a4`), so it cannot be chosen.
- The stock OS does the same with every added machine, so a project with SAMPLE on it plays CHORD there.

### 1.3 Today's numbering

- `compose.compose` and `MCComposer.compose` give the i-th machine they get number `6 + i` and descriptors from
  `76 + 5 i` (`compose.py`, `composer.js`). The page gives them in card order.
- The hardware-tested pair from the command line is SAMPLE 6, REF 7 (notes/60 §12). The other order gives REF 6,
  SAMPLE 7.

## 2. The options (standard §5.1)

| Option | How | Verdict |
|---|---|---|
| **A. Stable ids with placeholders** | a registry file gives each machine a permanent id; a build fills the gaps with a silent machine | **chosen**: nothing changes in saved data, the OS sees an ordinary build, and the composer already handles it (§3) |
| B. Translation at the record hooks | the sound keeps the build's index; the save hook writes a permanent id into a record slot and the load hook maps it back | not chosen: `sound.record` is a shared hook SAMPLE already uses (it would need the dispatcher first), sounds saved by other builds carry no mapping, and every build must get one more thing right |
| C. Today's rule, documented | the build report names each machine's number; projects belong to one build | not enough once the page offers a second machine card |

## 3. Measured with a prototype (2026-10-22)

The placeholder was written in C (`ph_update`: `rts`; `ph_render`: 32 zero frames, the idle path of `refmachine.c`)
and compiled with the reference machine's flags into an object of 22 bytes, with no variables and no patch points.
`compose.py`, unchanged, then composed it as a package. Every build below went through `compose.build_syx`
(caves checked, repacked, re-signed, read back).

| Selection given | Machines | Writes | Added to the image | MAIN OS |
|---|---|---|---|---|
| `sampler` | SAMPLE 6 | 123 | 36 096 bytes | `ccdadb37…` (release 0.2) |
| `refmachine` | REF 6 | 116 | 6 868 | `681b4b92…` |
| `placeholder,refmachine` | `----` 6, REF 7 | 116 | 7 212 (344 more than REF alone) | `4962772b…` |
| `sampler,refmachine` | SAMPLE 6, REF 7 | 123 | 37 760 | `d1765ab3…` (the tested pair) |
| `sampler,placeholder,refmachine` | SAMPLE 6, `----` 7, REF 8 | 123 | 38 168 (408 more than the pair) | `d6ea007c…` |
| `placeholder` | `----` 6 | 116 | 5 548 | `647dfab1…` |

- **What a gap costs.** Five descriptors (280 bytes), its entries in the data block and the parameter block, its
  name, its 22 bytes of code and the alignment.
- **Sharing the code.** With two gaps the composer would place the code twice. Sharing it is the one change B4 needs
  in how packages are placed (§4.4).
- **The limit.** A build holds six added machines at most (`max_machines`, `gs.check_room`), chosen machines and
  gaps together: ids 6 to 11.

## 4. Design

### 4.1 The registry file

- `tools/machines/numbers.json` (schema `model27-numbers/0.1`): one entry per machine package, its id and the date
  it was given. Ids start at 6 and run without holes. Entries are appended, never re-ordered, never reused (standard
  §5). The maintainer gives the id when the package is merged. Today it holds one entry: `sampler` is 6.
- `gen_flasher_tweaks.py` refuses a machine card whose package has no id: the page offers registered machines only.
- `compose.py` still composes packages without an id, for development (the reference machine). They are numbered
  after every registered id, in the order given, so they never take a number a user's sound can hold.

### 4.2 Numbering

- A machine's number is its id; its descriptors start at `76 + 5 (id − 6)` and its record at `RECS + 0x60 (id − 6)`.
- The composer sorts the chosen packages by id, so card order and the order given stop mattering.
- `compose.py --id <package>=<n>` gives a development package a number for a test, such as REF as 8 to make a gap.
  It exists on the command line only; the page never uses it.

### 4.3 Which ids a build fills

| | **F1: up to the highest chosen id** (the standard's wording) | **F2: every registered id** |
|---|---|---|
| A sound of a machine that is in the build | its machine | its machine |
| A sound of a registered machine that is not in the build | silent `----` if a higher id is in the build, otherwise CHORD and "Error" (§1.2) | always silent `----` |
| The MACHINES page | grows with the highest chosen machine | always the same list: the registered machines, `----` for those not installed |
| SAMPLE alone when a second machine is registered | unchanged | gets a placeholder at 7: new bytes and a new hardware test, in the release that brings the second machine anyway |
| Cost | gaps below the highest chosen id only | 344 to 408 bytes in the image per registered machine not chosen, and its RAM record |

**Recommendation: F2.** Inside model27 a sound never falls back to CHORD: a machine either plays or is a silent
`----`, and the list of machines is the same in every build. The cost is a few hundred bytes per machine not chosen,
and a slot of the id space for every registered machine (§4.6).

### 4.4 The placeholder package

- `tools/machines/placeholder/`, MIT, with sources, a committed object and a manifest. It is never a card and never
  registered.
- It is named `----`, with four knobs named `----`. It needs a stock picture and a DECAY default; both are open
  (§7).
- Its update and render functions are the prototype's.
- The composer places its code once per build and points every gap at it.

### 4.5 The page

- `tweaks.js` embeds the registry and the placeholder package. `composer.js` orders and fills exactly as `compose.py`
  does, changed in the same commit and proven by `webcompose_check.sh`.
- The composed tweak's id is the chosen packages in id order, joined by `+`; placeholders are not named. SAMPLE alone
  keeps the id `sampler`, so its key and its `REF_MODS` entry stay as they are.
- `ref_mainos.py` composes each set of machine cards in id order, as now.

### 4.6 Limits

- **The id space.** It is six numbers (6 to 11). Under F2 every registered machine takes one for good, so model27
  could offer six machine packages at most. More needs the layout to grow, which the standard recommends at 8 slots
  with 14 marks on the MACHINES page (§6).
- **Model-TG.** Builds with Model-TG start the added machines at 7. model27 does not offer Model-TG, and the registry
  assumes 6.
- **Projects from other firmwares** keep their own numbering and do not carry over, as today. That includes
  Modded-Cycles builds, where MACRO, ACID and the Syntakt engines take numbers by combination.
- **The stock OS** plays every added machine as CHORD and writes "Error", as today.

## 5. Proofs and done criteria

- **Python.**
  - `27-sampler.json` and `REF_MAINOS["sampler"]` stay unchanged while SAMPLE is the only registered machine.
  - The tested pair, SAMPLE 6 and REF 7, stays unchanged.
  - `28-refmachine.json` changes: REF alone becomes `----` 6 and REF 7, since REF is numbered after the registered
    ids. Its generator's `--check` follows.
  - Gaps are composed with `--id refmachine=8`.
- **JavaScript.** `webcompose_check.sh` gets the gap cases (a placeholder before, between and after machines, two
  gaps sharing one copy of the code): the same tweaks and MAIN OS as Python.
- **Emulation** (`tools/emu/test_compose.py`, run by the maintainer: Unicorn stops in the sandbox), for a build with
  a gap:
  - the placeholder's track renders silence;
  - REF as machine 8 plays as itself;
  - the MACHINES page's name table holds `----`.
- **Device** (maintainer):
  1. Flash SAMPLE with REF as 8. The MACHINES page shows `----` at 7, silent when chosen, and REF at 8.
  2. Save a sound with REF and a pattern with a machine lock on it.
  3. Flash REF as 8 alone (`----` at 6 and 7) and load both. They still play REF. Under today's numbering they would
     play CHORD with "Error" (§1.2).
- **Page.** The smoke test and `ref_mainos.py --check` pass with the SAMPLE keys unchanged.

## 6. Order of work

*Not carried out: option C was chosen (§9).*

| Step | Work | Done when |
|---|---|---|
| **B4a** | `numbers.json`, the placeholder package, `compose.py` (sort, fill, shared placeholder code, `--id`), its checks; `28-refmachine.json` regenerated | the Python proofs of §5; the emulation proof by the maintainer |
| **B4b** | `composer.js`, `tweaks.js` (registry, placeholder), `gen_flasher_tweaks.py` (registered cards only), `ref_mainos.py`, `webcompose_check`, smoke test | JavaScript equals Python on the gap cases; the page's SAMPLE unchanged |
| device | the test of §5 | before a second machine card is offered |
| later | a larger layout (8 slots) | only when a seventh machine is registered |

One commit per step, with the trailer. Neither step changes a byte of SAMPLE's firmware as long as SAMPLE is the only
registered machine, so B4 needs no new release on its own. The release that brings the second machine card brings
its id, and under F2 the new bytes of SAMPLE alone too.

## 7. Decisions for the maintainer

*Answered in §9: option C makes points 1 to 4 moot (no registry, no placeholder; REF stays as it is). Point 5
remains as the size of the layout, for when more than six machines come.*

1. **Which ids a build fills:** F1 or F2 (§4.3). The recommendation is F2.
2. **The placeholder's look:** its name (`----`), its picture on the MACHINES page, its DECAY default.
3. **Where the registry lives:** in model27 now. The standard says "in the repository"; whether it moves to the
   standard's repository once others build is a later question (standard §10).
4. **The reference machine stays unregistered**, numbered after the registered ids, so `28-refmachine.json` changes
   (§5).
5. **The id space:** six numbers for now; the larger layout only when a seventh machine is registered.

## 8. Outlook: dispatchers and machine shortcuts

These wait until the second machine is known, because what it needs decides what to build (notes/59 §6).

- **Shared hooks.**
  - The points are `sound.record`, `screen.tick`, `view.*` and `browser.open`.
  - Among the offered packages only SAMPLE uses them today.
  - The first second package that needs one brings the dispatcher table of the standard (§3.3): a fixed table of
    callbacks in the runtime's payload, walked by code assembled once.
- **Machine shortcuts.**
  - The registrar's `knob_vec` already calls a machine's `knob_hook` for the machine of the track only
    (`registrar.S`). Two machines can therefore hold the same "key held + knob" on their own tracks without meeting.
  - The hook is not wired yet: `compose.py` and `composer.js` write 0, and the manifest has no field for it. MACRO's
    FUNC + PITCH would be its first user.
  - The idea to weigh then: a fixed list of machine shortcuts, served by the registrar, from which a machine picks.
    Start with "key held + machine knob"; key-only combinations would need a second dispatcher in the key path.
  - Global shortcuts such as Control All Config's TRACK + TRIG 1–6 stay exclusive. No tool checks gestures yet, by
    combination and scope (standard step 4).

## 9. Decision (2026-10-22): option C, today's numbering stays

- **The maintainer's view.** A project loaded on a build with other machines ticked may play other machines on some
  tracks: a happy accident, not a fault. Who wants the same sounds keeps one project per build. That is option C of
  the standard (§2): today's rule, documented.
- **So nothing is built.** No registry, no placeholder machine, no change to the composer or the page: machines keep
  the numbers 6, 7, … in card order, SAMPLE first (§1.3).
- **Nothing worse than another machine can happen** (`registrar.S`, code reading). A number above `top` plays CHORD
  and shows "Error" (§1.2); the registrar gives it KICK's knobs (`knob_vec`) and KICK's record (`record_at`), so the OS
  never reads outside its tables. Otherwise the other machine plays with the same knob values (§1.1).
- **To do with the second machine card:** one sentence in the guide, along the lines of "a project remembers each
  track's machine slot; with other machines ticked a track may play another machine, and one project per build
  avoids that".
- **REF stays** as it is, never on the page: it is the second package of the composer's tests (`webcompose_check.sh`,
  `tools/emu/test_compose.py`, the pair tested on the device, notes/60 §12) and the template for a new machine.
- **What remains of B4** (notes/59 §6), all with the second machine: the dispatcher tables and the machine shortcuts
  (§8), and a layout for more than six added machines. The MACHINES page holds eight (two rows of seven marks, with
  the six stock machines); the maintainer notes that the page could be reworked later to hold more.
- **The prototype** (§3) and the design (§4) stay in this note as a measurement, should portable projects become a
  wish later.
