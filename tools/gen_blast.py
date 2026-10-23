#!/usr/bin/env python3
"""Generates the BLAST machine: 15 OPL2-style 2-operator FM models on SHAPE, as an added machine of the Model:Cycles.

  - 27-blast.json: the 7th machine, after the 6 stock ones.

Every model has a fixed modulator:carrier ratio, set in steps on SWEEP; the percussion models of the first BLAST
(which took a free ratio) and PLUCK, VIBES, ORGAN and FLUTE are gone. The engine is in tools/machines/blast/
(blast_dsp.h, the engine, and blast.c, the bridge to the voice loop); its tables (blast_tables.h) and its splash
pictures (blast_icons.h, tools/blast_screens.py) are computed here. The tables come from their formulas: the OPL2's
log-sine and power tables are rebuilt from the chip's published math, not copied from a ROM dump.

The machinery is ACID's and MACRO's (gen_macro.added_machine, notes/43 and notes/54): the same detours, the same moved
tables, the same place in the payload. The tweak carries, from the OS, only the short original bytes ("old") that
check the official file; the descriptor table is copied at build time from YOUR file (recipe "cycles").

    python3 tools/gen_blast.py                                        # blast_tables.h only
    python3 tools/gen_blast.py --cycles model-cycles_OS1.13.syx [--check]
    python3 tools/gen_blast.py --compile-only                         # compile and link, no OS needed

Built with m68k-linux-gnu-gcc 13.3 (Ubuntu 24.04), like ACID: another GCC gives other bytes, and --check says so.
"""
import argparse
import json
import math
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "emu"))

import blast_screens as ui                 # noqa: E402  (the splash pictures and the machine page)

DEV = HERE.parent / "tweaks" / "model-cycles_OS1.13"
OUT = DEV / "66-blast.json"
SRC = HERE / "machines" / "blast"
TABLES = SRC / "blast_tables.h"
ICONS = SRC / "blast_icons.h"

CFLAGS = ["-mcpu=54418", "-O2", "-malign-int", "-U_FORTIFY_SOURCE", "-ffreestanding", "-fno-builtin",
          "-fno-tree-loop-distribute-patterns", "-nostdlib", "-fno-pic", "-fno-common", "-ffunction-sections",
          "-fdata-sections", "-fomit-frame-pointer", "-Wall", "-Wextra", "-Werror"]
LINK = """SECTIONS
{{
  .text {code:#x} : {{ *(.text.blast_update) *(.text.blast_render) *(.text*) }}
  .rodata ALIGN(4) : {{ *(.rodata*) }}
  .data ALIGN(4) : {{ *(.data*) }}
  .bss {bss:#x} (NOLOAD) : {{ *(.bss*) *(COMMON) }}
  /DISCARD/ : {{ *(.comment) *(.note*) *(.eh_frame*) }}
}}
"""

MODELS = ("SIN", "HLF", "ABS", "PLS", "BAS", "PIA", "MAR", "GLK", "BRS", "ACC", "STR", "STL", "TMP", "ZAP")

# --- the machine (as gen_macro.MACHINE): COLOR, SHAPE, SWEEP, CONTOUR = (long name, short name, default[, min, max]);
# decay: the DECAY default; image: our own splash, index 6 (tools/blast_screens.py). Defaults: the first model.
MACHINE = dict(name="BLAST", image=ui.IMAGE, decay=50,
               knobs=(("Index", "Idx", 64), ("Model", "MODL", 0, 0, len(MODELS) - 1), ("Ratio", "RTIO", 80),
                      ("Env", "Env", 40)))

BSS_OFF = 0x36000                  # as MACRO and ACID: variables above the moved tables (gs.LAYOUT)

FS = 48000.0
BLK = 32
DB_UNITS = 256 / (20 * math.log10(2))             # log units per dB (256 = one octave of amplitude)
LFO_CLOCK = 49716.0                               # the OPL2's sample rate (14.318 MHz / 288)


def tables():
    """(name, C type, values) of blast_tables.h, and the #defines."""
    t = []
    # TINY's tables (gen_tables.py of the TINY add-on), same formulas
    t.append(("FM_SEMI_INC", "u32", [round(2 ** 32 * 440.0 * 2 ** ((n - 69) / 12.0) / FS) for n in range(13)]))
    t.append(("FM_LOGSIN", "u16", [round(-math.log2(math.sin((2 * i + 1) * math.pi / 1024.0)) * 256)
                                   for i in range(256)]))
    t.append(("FM_POW", "u16", [round(8192 * 2 ** (-(i + 1) / 256.0)) for i in range(256)]))
    # BLAST
    t.append(("FM_WZERO", "u16", [0, 0x200, 0, 0x100]))            # sine, half-sine, abs-sine, pulse
    t.append(("FM_WSIGN", "u16", [0x200, 0x200, 0, 0]))
    t.append(("FM_MULT", "u16", [round(r * 256) for r in (0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15)]))
    sixty = 60 * DB_UNITS
    t.append(("FM_RATE", "u32", [round(sixty * 65536 / (0.005 * 2000 ** (k / 127) * FS)) for k in range(128)]))
    t.append(("FM_ATK", "u32", [min(65536, round(65536 * (1 - math.exp(-5 * BLK / (0.0005 * 4000 ** (k / 127) * FS)))))
                                for k in range(128)]))
    t.append(("FM_PDECAY", "u32", [round(65536 * math.exp(-BLK / (0.001 * 1000 ** (k / 127) * FS))) for k in range(128)]))
    t.append(("FM_EXP2", "u32", [round(65536 * 2 ** (i / 256)) for i in range(256)]))
    t.append(("FM_CENTS", "u32", [round(65536 * (2 ** (c / 1200) - 1)) for c in range(64)]))
    k = {
        "FM_LFO_VIB": round(2 ** 32 * (LFO_CLOCK / 8192) * BLK / FS),     # 6.07 Hz
        "FM_LFO_AM": round(2 ** 32 * (LFO_CLOCK / 13432) * BLK / FS),     # 3.70 Hz
    }
    return t, k


def tables_header():
    t, k = tables()
    out = ["/* BLAST's tables, computed by tools/gen_blast.py: do not edit by hand. */",
           "#ifndef BLAST_TABLES_H", "#define BLAST_TABLES_H", ""]
    for name, v in k.items():
        out.append(f"#define {name} {v:#x}u")
    out.append("")
    for name, typ, v in t:
        out.append(f"static const {typ} {name}[{len(v)}] = {{")
        for i in range(0, len(v), 10):
            out.append("\t" + ", ".join(str(x) for x in v[i:i + 10]) + ",")
        out.append("};")
    return "\n".join(out + ["", "#endif", ""])


def compile_machine(tmp, pay, tables_h, icons_h, bss_at=None, code_end=None, defs=()):
    """The bridge, engine and splash pictures of BLAST linked at pay (code, tables, pictures) and bss_at (variables;
    pay + BSS_OFF by default). The code and tables must end before code_end (gs.STUBS by default). Returns (bytes,
    symbols, end of the BSS)."""
    import gen_sdvintage_exact as gx
    import gen_syntakt_engines as gs
    (tmp / "blast_tables.h").write_text(tables_h)           # this generator's tables, not the repo's file
    (tmp / "blast_icons.h").write_text(icons_h)             # this generator's pictures
    for f in ("blast.c", "blast_dsp.h"):
        (tmp / f).write_bytes((SRC / f).read_bytes())
    bss_at = pay + BSS_OFF if bss_at is None else bss_at
    code_end = gs.STUBS if code_end is None else code_end
    o = tmp / "blast.o"
    gx.run([gx.CROSS + "gcc", *CFLAGS, *(f"-D{d}" for d in defs), f"-I{tmp}", "-c", str(tmp / "blast.c"), "-o", str(o)])
    ld, elf, out = tmp / "link.ld", tmp / "blast.elf", tmp / "blast.bin"
    ld.write_text(LINK.format(code=pay, bss=bss_at))
    gx.run([gx.CROSS + "ld", "-T", str(ld), "--gc-sections", "--no-warn-rwx-segments", "-e", "blast_update",
            "-u", "blast_render", *(a for k in HOOKS for a in ("-u", k)), "-o", str(elf), str(o)])
    secs = {}
    for line in gx.run([gx.CROSS + "objdump", "-h", str(elf)]).splitlines():
        f = line.split()
        if len(f) > 4 and f[0].isdigit():
            secs[f[1]] = (int(f[3], 16), int(f[2], 16))
    if set(secs) - {".text", ".rodata", ".data", ".bss"}:
        raise SystemExit(f"!! unexpected sections: {sorted(secs)}")
    if secs.get(".data", (0, 0))[1]:
        raise SystemExit("!! initialised variables: the boot hook would not copy them")
    gx.run([gx.CROSS + "objcopy", "-O", "binary", "-R", ".bss", str(elf), str(out)])
    blob = out.read_bytes()
    syms = {q[2]: int(q[0], 16) for q in (l.split() for l in gx.run([gx.CROSS + "nm", str(elf)]).splitlines())
            if len(q) == 3}
    if pay + len(blob) > code_end:
        raise SystemExit(f"!! code too large: {len(blob)} bytes")
    bss = secs.get(".bss", (bss_at, 0))
    if bss[0] != bss_at:
        raise SystemExit("!! BSS")
    return blob, syms, (bss[0] + bss[1] + 3) & ~3


# called only from the detours (outside the C), kept by the linker: SWEEP's interface object, the knob turn's hook and
# the machine's three Bitmap objects (their addresses go into the detour stubs)
HOOKS = ("blast_state_at", "blast_state_connect", "blast_turn_hook", "blast_bm_a", "blast_bm_b", "blast_bm_c")
SHAPE_DESC, SWEEP_DESC = 77, 78    # BLAST's descriptors (gen_macro.added_machine, one added machine): 76..80
TURN_AT, TURN_OLD = 0x4000b82a, "2f032f002f02"     # the OS's knob turn (0x4000b7d6), before vt[20]


def blast_detours(syms):
    """gen_syntakt_engines.detours_asm with BLAST's screens: descriptors 77 and 78 (SHAPE and SWEEP) go to our own
    interface objects, and the machine's pictures (index 6) to our Bitmap objects (tools/blast_screens.py)."""
    import gen_syntakt_engines as gs
    orig = gs.detours_asm

    def wrapped(*a, **kw):
        return ui.patch_detours(orig(*a, **kw), syms)
    return orig, wrapped


def other_ids():
    """Tweaks never built with BLAST: everything ACID alone excludes (BLAST takes the same place and hooks), ACID
    itself and every tweak that excludes ACID, and the TINY add-on's machines (not in this repo, same place)."""
    import glob
    acid = json.loads((DEV / "26-acid.json").read_text(encoding="utf-8"))
    ids = set(acid["conflicts"]) | {"acid", "tiny", "port", "tiny-port", "6ch-usbup", "6ch-multiout", "blam"}
    for f in glob.glob(str(DEV / "[0-9]*.json")):
        t = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        if "acid" in t.get("conflicts", ()):
            ids.add(t["id"])
    return ids - {"blast"}


def build_tweak(img):
    """The BLAST tweak: the 7th machine, alone (no Model-TG version yet)."""
    import gen_macro as gm
    import gen_syntakt_engines as gs
    import usb_steady
    import voice_loop
    pay = gs.PAY_ALONE
    gs.set_base(pay)
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        blob, syms, bss_end = compile_machine(tmp, pay, tables_header(), ui.icons_header())
        ssyms = {}
        detours, assemble = gs.detours_asm, gm.assemble

        def detours_with_screens(*a, **kw):
            return ui.patch_detours(detours(*a, **kw), syms)

        def assemble_keeping_symbols(tmp_, name, src, at, defs=()):
            blob_, syms_ = assemble(tmp_, name, src, at, defs)
            if name == "det":
                ssyms.update(syms_)
            return blob_, syms_

        gs.detours_asm, gm.assemble = detours_with_screens, assemble_keeping_symbols
        try:
            writes, append = gm.added_machine(img, None, [dict(MACHINE, update=syms["blast_update"],
                                                               render=syms["blast_render"])], tmp, [(pay, blob)],
                                              bss_end)
        finally:
            gs.detours_asm, gm.assemble = detours, assemble
        ui.clamp_writes(writes, gm.BASE)
        writes += ui.site_writes(img, gm.BASE, ssyms)
    old = img[TURN_AT - 0x40000400:][:6]
    if old.hex() != TURN_OLD:
        raise SystemExit(f"!! {TURN_AT:#x}: {TURN_OLD} expected, {old.hex()} found")
    writes.append({"off": TURN_AT - 0x40000400, "old": TURN_OLD,
                   "new": "4ef9" + f"{syms['blast_turn_hook']:08x}"})
    writes.sort(key=lambda w: w["off"])
    for a_, b_ in zip(writes, writes[1:]):
        if a_["off"] + len(a_["new"]) // 2 > b_["off"]:
            raise SystemExit(f"!! overlapping writes at {0x40000400 + b_['off']:#x}")
    ids = other_ids() | {"model-tg", "model-tg-st"}
    out = {
        "id": "blast",
        "order": 27,
        "name": "Machine BLAST : 14 modèles FM à la manière de l'OPL2",
        "description": [
            "Machine BLAST en 7e machine, après les 6 d'origine : 14 modèles FM à deux opérateurs à la manière de",
            "l'OPL2 sur SHAPE, tous à rapport fixe (SIN, HLF, ABS, PLS, BAS, PIA, MAR, GLK, BRS, ACC, STR, STL, TMP,",
            "ZAP) et une image de machine à nous. COLOR = indice de modulation, SWEEP = rapport affiché 1:2, 1:1 …",
            "9:1, 10X, 12X, 15X (par crans, comme le Digitone), CONTOUR = mouvement du son, DECAY, PUNCH = LFO de",
            "la puce,",
            "GATE tient la note. Une voix muette n'est pas calculée. Généré par tools/gen_blast.py. De l'OS, seuls",
            "les octets d'origine (old) qui vérifient le fichier officiel ; la table des descripteurs est recopiée au",
            "build (recette cycles).",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
    }
    out.update({"conflicts": sorted(ids - {"blast"}), "writes": writes, "append": append})
    out["symbols"] = {k: f"{syms[k]:#x}" for k in ("blast_update", "blast_render", "trk", "blast_shape",
                                                   "blast_state_at", "blast_turn_hook", "blast_fmt", "blast_fine",
                                                   "blast_turn", "blast_model_fmt", "ui_sweep", "ui_shape",
                                                   "blast_bm_a", "blast_bm_b", "blast_bm_c")}
    out = usb_steady.add_to(out)           # as MACRO and ACID alone: USB sent on time (notes/35), voice loop (notes/36)
    out = voice_loop.add_to(out)
    segs = sum(n for _, n in append["pack"])
    return out, dict(code=len(blob), bss=bss_end - pay - BSS_OFF, image=segs, syms=syms)


def emit(path, text, check):
    if check:
        ok = path.exists() and path.read_text(encoding="utf-8") == text
        print(f"    {path.name} {'is up to date' if ok else 'DOES NOT MATCH (another GCC?)'}")
        return not ok
    path.write_text(text, encoding="utf-8")
    print(f"    wrote {path}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", help="the official model-cycles_OS1.13.syx (without it: blast_tables.h only)")
    ap.add_argument("--check", action="store_true", help="check that the files in the repo match")
    ap.add_argument("--compile-only", action="store_true", help="compile and link the machine, no OS needed")
    args = ap.parse_args()
    bad = emit(TABLES, tables_header(), args.check)
    bad += emit(ICONS, ui.icons_header(), args.check)
    if args.compile_only:
        import gen_syntakt_engines as gs
        gs.set_base(gs.PAY_ALONE)
        with tempfile.TemporaryDirectory() as d:
            blob, syms, bss_end = compile_machine(pathlib.Path(d), gs.PAY_ALONE, tables_header(), ui.icons_header())
        print(f"  blast: code, tables and pictures {len(blob)} bytes, variables {bss_end - gs.PAY_ALONE - BSS_OFF} "
              f"bytes, update {syms['blast_update']:#x}, render {syms['blast_render']:#x}")
    if args.cycles:
        import gen_sdvintage_7th as g7
        import gen_sdvintage_exact as gx
        img = g7.cycles_main(args.cycles)
        if len(img) != gx.IMAGE_LEN:
            raise SystemExit("!! this is not the official MAIN OS 1.13")
        tweak, info = build_tweak(img)
        import build
        build.apply_writes(img, [tweak])           # a wrong "old" byte fails here, not in the build
        text = json.dumps(tweak, indent=1, ensure_ascii=False) + "\n"
        print(f"  {tweak['id']}: {len(tweak['writes'])} writes, code and tables {info['code']} bytes, variables "
              f"{info['bss']} bytes, added to the image {info['image']} bytes")
        bad += emit(OUT, text, args.check)
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
