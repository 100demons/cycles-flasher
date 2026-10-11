# Contributing to Modded-Cycles

Thanks for wanting to help. New mods, fixes, test reports and ideas are welcome: open an issue or a pull request, or
come and talk on the [Discord](https://discord.gg/hWegtJZcmm).

## License of your contribution

- By opening a pull request, you agree that your contribution is licensed under the [MIT License](LICENSE), like the
  rest of the project.
- A mod folder may carry its own permissive license instead (MIT, BSD, ISC or 0BSD) in a `LICENSE` file next to its
  sources: say so in the pull request. Copyleft code (GPL and the like) cannot go into the web flasher's bundle.
- If your work builds on someone else's code, say where it comes from and under which license, so it can be credited in
  [`tweaks/model-cycles_OS1.13/PROVENANCE.md`](tweaks/model-cycles_OS1.13/PROVENANCE.md) and
  [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md). Do not transcribe or closely paraphrase code whose license
  does not allow it (GPL code into MIT files, code with no license at all).
- Work sent privately (on Discord, as `.syx` files or scripts) is published only after its author has said yes in
  writing, with the credit they want.

## Elektron firmware

Never include Elektron firmware or bytes copied from it, apart from the short `old` bytes a tweak needs to check the
user's own file. Builds always start from the user's own official file. See [`AGENTS.md`](AGENTS.md) for the hard
rules (only the MAIN OS section is touched, every mod is proven in emulation, recovery must stay possible).

## How a mod gets in

[`AGENTS.md`](AGENTS.md) describes the usual path: a technical note, a generator, an emulation proof, the flasher card,
the guide and the release notes. A new mod ships as *Experimental*; it becomes *Tested* only after Maxime has tried it
on his own Model:Cycles.
