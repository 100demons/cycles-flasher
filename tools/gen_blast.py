#!/usr/bin/env python3
"""Generates BLAST: one added percussion machine built from BLAST's OPL2-style 2-operator FM voice.

  - BLAST (7th machine): 12 curated BLAST engines and two SAM banks; SWEEP steps through the ratio list on the FM
    engines and scrubs the word on SAM.

The engine is in tools/machines/blast/ (blast_dsp.h, the FM engine, blast_sam.h, the SAM voice, and blast.c, the
bridge to the voice loop); its FM tables (blast_tables.h) are computed here. The tables come from their formulas: the
OPL2's log-sine and power tables are rebuilt from the chip's published math, not copied from a ROM dump. The SAM
tables and the 32 Braids words are static in blast_sam_tables.h and blast_sam_words.h.

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

import blast_screens as ui                 # noqa: E402  (the SHAPE / SWEEP interface detours)

DEV = HERE.parent / "tweaks" / "model-cycles_OS1.13"
OUT = DEV / "67-blast.json"
SRC = HERE / "machines" / "blast"
TABLES = SRC / "blast_tables.h"
ICONS = SRC / "blast_icons.h"

CFLAGS = ["-mcpu=54418", "-Os", "-malign-int", "-U_FORTIFY_SOURCE", "-ffreestanding", "-fno-builtin",
          "-fno-tree-loop-distribute-patterns", "-nostdlib", "-fno-pic", "-fno-common", "-ffunction-sections",
          "-fdata-sections", "-fomit-frame-pointer", "-fno-asynchronous-unwind-tables",
          "-fno-unwind-tables", "-fmerge-all-constants", "-fno-inline-functions-called-once",
          "-Wall", "-Wextra", "-Werror"]
LINK = """SECTIONS
{{
  .text {code:#x} : {{ *(.text.blast_update) *(.text.blast_render) *(.text*) }}
  .rodata ALIGN(4) : {{ *(.rodata*) }}
  .data ALIGN(4) : {{ *(.data*) }}
  .bss {bss:#x} (NOLOAD) : {{ *(.bss*) *(COMMON) }}
  /DISCARD/ : {{ *(.comment) *(.note*) *(.eh_frame*) }}
}}
"""

# BLAST exposes 12 FM engines and two SAM banks, in this SHAPE order.
MODELS_BLAST = ("KIK", "TOM", "BNG", "CNG", "TAI", "TIM", "MAR", "DJB", "BLK", "GNG", "BUB", "ZAP",
                "SAM1", "SAM2")

# --- the machines (as gen_macro.MACHINE): COLOR, SHAPE, SWEEP, CONTOUR = (long name, short name, default[, min, max]);
# decay: the DECAY default; image 4: the stock TONE picture (the custom splash is not linked).
# The display names follow BLAST v3: Index/Idx, Model/MODL, Ratio/RTIO, Env/Env. Ratio defaults to 4:1 (step 11,
# whose first whole knob position is 68; see blast.c:step_value).
KNOBS_BLAST = (("Index", "Idx", 64), ("Model", "MODL", 0, 0, len(MODELS_BLAST) - 1), ("Ratio", "RTIO", 68),
               ("Env", "Env", 40))
MACHINE = dict(name="BLAST", image=ui.IMAGE, decay=50, knobs=KNOBS_BLAST)

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
    # BLAST's OPL2 multipliers plus the percussion ratios around them. 4:1 is present and is the default step;
    # 1:4, 1:3, 2:3, 5:4, 3:2, 5:2, 7:2 and 9:2 are new.
    t.append(("FM_MULT", "u16", [round(r * 256) for r in
                                 (0.25, 1 / 3, 0.5, 2 / 3, 1, 1.25, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6, 7, 8, 9,
                                  10, 12, 15)]))
    sixty = 60 * DB_UNITS
    t.append(("FM_RATE", "u32", [round(sixty * 65536 / (0.005 * 2000 ** (k / 127) * FS)) for k in range(128)]))
    t.append(("FM_PDECAY", "u16", [round(65536 * math.exp(-BLK / (0.001 * 1000 ** (k / 127) * FS))) for k in range(128)]))
    t.append(("FM_EXP2", "u32", [round(65536 * 2 ** (i / 256)) for i in range(256)]))
    t.append(("FM_CENTS", "u16", [round(65536 * (2 ** (c / 1200) - 1)) for c in range(64)]))
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
    """The bridge and engine of BLAST linked at pay (code and tables) and bss_at (variables; pay + BSS_OFF by
    default). The code and tables must end before code_end (gs.STUBS by default). Returns (bytes, symbols, end of the
    BSS)."""
    import gen_sdvintage_exact as gx
    import gen_syntakt_engines as gs
    (tmp / "blast_tables.h").write_text(tables_h)           # this generator's tables, not the repo's file
    (tmp / "blast_icons.h").write_text(icons_h)             # this generator's pictures
    for f in ("blast.c", "blast_dsp.h", "blast_sam.h", "blast_sam_tables.h", "blast_sam_words.h"):
        (tmp / f).write_bytes((SRC / f).read_bytes())
    bss_at = pay + BSS_OFF if bss_at is None else bss_at
    code_end = gs.STUBS if code_end is None else code_end
    o = tmp / "blast.o"
    gx.run([gx.CROSS + "gcc", *CFLAGS, *(f"-D{d}" for d in defs), f"-I{tmp}", "-c", str(tmp / "blast.c"), "-o", str(o)])
    ld, elf, out = tmp / "link.ld", tmp / "blast.elf", tmp / "blast.bin"
    ld.write_text(LINK.format(code=pay, bss=bss_at))
    gx.run([gx.CROSS + "ld", "-T", str(ld), "--gc-sections", "--no-warn-rwx-segments", "-e", "blast_update",
            "-u", "blast_render", *(a for k in HOOKS for a in ("-u", k)), "-o", str(elf),
            str(o)])
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
SHAPE_DESC, SWEEP_DESC = 77, 78    # BLAST's descriptors: 76..80
TURN_AT, TURN_OLD = 0x4000b82a, "2f032f002f02"     # the OS's knob turn (0x4000b7d6), before vt[20]


def blast_detours(syms):
    """gen_syntakt_engines.detours_asm with BLAST's COLOR, SHAPE and SWEEP interface objects (76, 77 and 78)."""
    import gen_syntakt_engines as gs
    orig = gs.detours_asm

    def wrapped(*a, **kw):
        return ui.patch_detours(orig(*a, **kw), syms)
    return orig, wrapped


def other_ids():
    """Tweaks never built with BLAST: everything that adds a machine or appends to the image (the payload and
    boot hook are shared), and the TINY add-on's machines (not in this repo, same place)."""
    import gen_acid as ga
    ids = ga.other_ids() | {"acid", "acid-tg", "macro", "macro-tg", "model-tg", "model-tg-st",
                            "tiny", "port", "tiny-port", "6ch-usbup", "mod-settings"}
    for path in DEV.glob("[0-9]*.json"):
        try:
            t = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if t.get("append"):
            ids.add(t["id"])
    ids.discard("blast")
    return ids


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
        machines = [dict(MACHINE, update=syms["blast_update"], render=syms["blast_render"])]
        try:
            writes, append = gm.added_machine(img, None, machines, tmp, [(pay, blob)], bss_end)
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
        "name": "Machine BLAST : FM percussion and SAM speech",
        "description": [
            "One added machine after the six stock ones, built from BLAST's OPL2-style FM voice and the SAM speech",
            "synthesizer of Braids Renaissance:",
            "BLAST (7th) has 12 percussion engines (KIK, TOM, BNG, CNG, TAI, TIM, MAR, DJB, BLK, GNG, BUB, ZAP)",
            "and steps SWEEP through the ratio list, 1:4, 1:3, 1:2, 2:3, 1:1 ... 9:1, 10X, 12X, 15X, with 4:1 as the",
            "default step. SHAPE 12 and 13 are SAM1 and SAM2: COLOR selects one of 16 words, SWEEP scrubs it,",
            "CONTOUR sets the speaking speed, PUNCH loops the word, DECAY is the release.",
            "COLOR = FM index / strike, SHAPE = model, SWEEP = ratio, CONTOUR = movement of the sound, DECAY, PUNCH =",
            "the chip's LFO, GATE holds the note. A silent voice is not computed. Generated by tools/gen_blast.py.",
            "From the OS, only the original bytes (old) that check the official file; the descriptor table is copied",
            "at build time (recipe cycles).",
        ],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
    }
    out.update({"conflicts": sorted(ids - {"blast"}), "writes": writes, "append": append})
    out["symbols"] = {k: f"{syms[k]:#x}" for k in ("blast_update", "blast_render", "trk",
                                                   "blast_state_at", "blast_turn_hook", "blast_fmt", "blast_fine",
                                                   "blast_turn", "blast_model_fmt", "ui_sweep", "ui_shape",
                                                   "ui_color", "blast_bm_a", "blast_bm_b", "blast_bm_c")}
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
        print(f"  blast: code and tables {len(blob)} bytes, variables {bss_end - gs.PAY_ALONE - BSS_OFF} "
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
