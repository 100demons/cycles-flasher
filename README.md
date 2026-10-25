# Demo Engines for Model Cycles

**A demonstration zone for Model:Cycles engines: four-knob machines, patched in your browser from your own
official OS file.**

It is built on model27 by durchgemacht, itself a downstream fork of
[Modded-Cycles](https://github.com/18nelli18/Modded-Cycles). This is not a complete, curated build: it shows what
the engines can do. You tick what you want, the page builds the firmware from **your own copy** of the official OS in
your browser, and sends it to the Model:Cycles over USB. Every engine and tool keeps its author's name, on the cards,
in the credits and in the third-party notices.

**Status: beta.** The web flasher uses the cycles-engines method and runs at [https://100demons.github.io/cycles-engines/flasher/](https://100demons.github.io/cycles-engines/flasher/): Feral, BLAST, PUNCH and SAM, and any combination of engines can be flashed together. The old [cycles-flasher page](https://100demons.github.io/cycles-flasher/flasher/) redirects there.
The engines are also published one by one, with their sources and a ready-made package, in
**[cycles-mods](https://github.com/100demons/cycles-mods)** for other developers to grab.
The command-line build works for every Modded-Cycles 1.55 mod still in the repository; the short list for the beta
is being chosen, and nothing has been removed from the tools yet.

> [!IMPORTANT]
> **No Elektron firmware is included in this repository**, original or modified. You bring the official OS
> file from [elektron.se](https://www.elektron.se/support-downloads/modelcycles); the mods are applied to it on your
> computer. This is an independent project, not affiliated with or endorsed by Elektron, and not affiliated with
> Modded-Cycles' maintainers. Flashing a modified OS is **at your own risk** and may void your warranty.

## What model27 is for

- **The Model:Cycles workflow stays the Model:Cycles workflow.** A machine has PITCH, four knobs, DECAY, GATE and
  PUNCH, like the six original ones. A mod adds something small and leaves everything else as it is, bit for bit.
- **A few engines, worked out to the end.** Knob ranges that mean something end to end, no clicks under a square LFO, a measured
  cost, a test on a real machine before a mod is called tested.
- **Mods that fit together.** Every mod declares what it touches, in a manifest; what can be ticked together is
  computed from those declarations, not from a hand-written list. That is the job of the companion draft, the
  **[Cycles Mod Standard](https://github.com/durchgemacht/cycles-mod-standard)** (draft 0.2), written alongside.

## What goes in first

- The maintainer's own mods: the **SAMPLE** machine of [Cycles One-Shot](https://github.com/durchgemacht/cycles-one-shot)
  (a one-shot sampler for samples on the +Drive) and
  [Control All Config](https://github.com/durchgemacht/cycles-control-all-config), which is already here.
- Then one or two mods by other authors, each with its author's agreement.
- Everything else that Modded-Cycles 1.55 ships stays buildable from the command line until it is decided, mod by
  mod, what the beta offers. Modded-Cycles' startup animation, which shows the Modded-Cycles name and logo, is that
  project's own branding and will not be offered here.

## Install from the browser

1. **Open the [web flasher](https://100demons.github.io/cycles-engines/flasher/)** in Chrome, Edge or Opera on a desktop computer (it needs Web MIDI).
2. **Tick the engines you want.** Any combination can be flashed together.
3. **Drop your official OS file**, `model-cycles_OS1.13.syx`, from the
   [Elektron download](https://www.elektron.se/support-downloads/modelcycles) (unzip it first).
4. **Connect the Model:Cycles over USB and press Flash.** Close Elektron Transfer first and leave the machine on its
   usual screen. The transfer takes about 30 seconds, then the Model:Cycles asks you to confirm with **YES**.

Everything runs in your browser: your files are never uploaded anywhere. **Before you flash**, back up your projects
and samples with Elektron Transfer.

## Building from the command line

The build is Modded-Cycles' pure-Python toolchain: no compiler and no firmware in the repository.

```sh
python3 tools/build.py --list                       # every mod the repository holds today
python3 tools/build.py -i model-cycles_OS1.13.syx -t control-all-config,latching-mute,trig-preview
./flash.sh                                           # macOS / Linux  (flash.bat on Windows)
```

Details in [`BUILD.md`](BUILD.md) and [`FLASH.md`](FLASH.md) (both in French, inherited from Modded-Cycles).

### Publishing an engine to `cycles-mods`

The public engine catalogue is generated from this repository, so the two cannot drift:

```sh
# edit tools/machines/<id>/public.json (version, prose, changelog), then:
python3 tools/export_engine.py <id> --to ../cycles-mods
python3 tools/export_engine.py <id> --to ../cycles-mods --check   # writes nothing, exits 1 if out of step
```

It copies the sources, the committed object and the tweak, rewrites the manifest for `src/` and `addon/`, and
generates the engine's `README.md`, `engine.json`, `CHANGELOG.md` and the catalogue's `index.json`. Commit this
repository and `cycles-mods` together.

<details>
<summary><b>Going back to the official firmware</b></summary>

Build nothing: send your official OS file the way you installed it. Before that, set any track that uses an added
machine (MACRO, ACID, a Syntakt engine, SAMPLE or the Model-TG Sampler) back to one of the six original machines:
a project that still names a machine the official OS does not have can freeze its MACHINES page.

</details>

<details>
<summary><b>If something goes wrong</b></summary>

If a Model:Cycles ever stops starting, it can always be recovered from its startup menu (`FUNC` + power on, then
`TRIG 4`). That menu only listens to the **MIDI IN** port, so you need a USB-MIDI interface and the scripts described
in [`FLASH.md`](FLASH.md). Only the MAIN OS section of the firmware is ever changed; the bootloader and the updater
stay as Elektron shipped them.

</details>

## How it is made

Every mod is checked in an emulator that runs the Model:Cycles' own code, then on a real Model:Cycles before it is
marked *Tested*. The tools, the emulation proofs and the technical notes are Modded-Cycles' (the
[notes](notes/README.md) are in French); model27 adds its own notes in English as it goes.

## Credits

model27 is Modded-Cycles' work with a different aim. Everything here starts from:

- **[18nelli18/Modded-Cycles](https://github.com/18nelli18/Modded-Cycles)** (MIT), by 18nelli18 and its contributors:
  the tools, the generators, the emulation, the web flasher, the notes and the mods.

And, through Modded-Cycles, on:

- **[scottmetoyer/ms-multi-output](https://github.com/scottmetoyer/ms-multi-output)** (MIT): the original 6-channel USB mod.
- **[drumkilla/elektron-model-tweaks](https://github.com/drumkilla/elektron-model-tweaks)** (MIT): latching mute, trig preview, scrolling names, and the `mtlib` toolkit and tweak format used by the build.
- **[TinyGregAudio/Model-TG](https://github.com/TinyGregAudio/Model-TG)** (MIT): the Sampler machine and everything that comes with it ([license](tweaks/model-cycles_OS1.13/LICENSE-Model-TG)).
- **[pichenettes/eurorack](https://github.com/pichenettes/eurorack)** (MIT): Émilie Gillet's Braids code, compiled as is for the synthesis models of the MACRO machine ([license](tweaks/model-cycles_OS1.13/LICENSE-Braids)).
- **[RobinSchmidt/Open303](https://github.com/RobinSchmidt/Open303)** (MIT): Robin Schmidt's TB-303 model, rewritten in fixed point for the ACID machine ([license](tweaks/model-cycles_OS1.13/LICENSE-Open303)).
- **[dagargo/elektroid](https://github.com/dagargo/elektroid)** (GPL-3.0): the Elektron Transfer update protocol behind fast USB flashing.
- **[mischa85/elektron-firmware-tool](https://github.com/mischa85/elektron-firmware-tool)** (MIT): the firmware container format and its signature, on which `mtlib` is based.
- **[mxldyn/octamax](https://github.com/mxldyn/octamax)** and **[bryantysinger/octa-bt-pt](https://github.com/bryantysinger/octa-bt-pt)**: reverse-engineering and patching methods (ideas only, no code).

The authors of the individual mods are named in the mod table of the flasher, in
[`PROVENANCE.md`](tweaks/model-cycles_OS1.13/PROVENANCE.md) and in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## License

The code, tweak files, website and notes are under the [MIT License](LICENSE): Modded-Cycles' copyright for what
comes from there, model27's for its changes. Third-party code keeps its own license, see
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). No Elektron firmware is included or licensed here; Elektron,
Model:Cycles, Model:Samples and Syntakt are trademarks of Elektron Music Machines MAV AB. To contribute, see
[CONTRIBUTING.md](CONTRIBUTING.md).
