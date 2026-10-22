#!/usr/bin/env python3
"""Reference data for tools/webcompose_check.js (notes/61): what docs/flasher/composer.js must give, computed by the
Python composer, so that the page and tools/compose.py compose the same bytes.

Part 1 (B3a), no firmware needed: every package of tools/machines/ that has an object, laid out once
(relocate.layout, relocate.bundle), and what relocate.place gives at a set of placements: the code and the variables
at 4-aligned addresses (where the composer puts the packages alone and in pairs, then random ones), the patch points
at assorted values.

    python3 tools/webcompose_synth.py <outdir>          # writes <outdir>/compose.json
"""
import json
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import relocate  # noqa: E402

MACHINES = HERE / "machines"
CODE_END = 0x48000000                       # no limit here: the composer checks the room, not this comparison


def packages():
    """(manifest, object bytes) of every package with exactly one committed object."""
    for d in sorted(p for p in MACHINES.iterdir() if p.is_dir()):
        mf = d / "manifest.json"
        if not mf.is_file():
            continue
        m = json.loads(mf.read_text(encoding="utf-8"))
        objs = m.get("build", {}).get("objects", [])
        if len(objs) == 1 and (d / objs[0]).is_file():
            yield m, (d / objs[0]).read_bytes()


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(61)
    ref = {}
    for m, obj in packages():
        b = m["build"]
        upd, rnd_sym, keep = b["symbols"]["update"], b["symbols"]["render"], b.get("keep", [])
        names = [upd, rnd_sym, *keep]
        lay = relocate.layout(obj, upd, rnd_sym, keep, m["id"])
        points = [pp["symbol"] for pp in b.get("patch_points", []) if "symbol" in pp]
        spots = [(0x43000000, 0x43036000), (0x43000518, 0x430360c0), (0x43007740, 0x4304a038)]
        spots += [(0x43000000 + 4 * rnd.randrange(0x8000), 0x43036000 + 4 * rnd.randrange(0x8000)) for _ in range(20)]
        cases = []
        for code_at, bss_at in spots:
            values = {p: rnd.randrange(200) for p in points}
            blob, syms, end = relocate.place(obj, upd, rnd_sym, keep, code_at, bss_at, CODE_END, values, m["id"])
            cases.append({"code_at": code_at, "bss_at": bss_at, "values": values, "blob": blob.hex(),
                          "symbols": {k: syms[k] for k in names}, "bss_end": end})
        ref[m["id"]] = {"bundle": relocate.bundle(lay, names), "cases": cases}
        print(f"{m['id']}: {len(lay['code'])} bytes of code and tables, {len(lay['relocs'])} relocations, "
              f"{len(cases)} placements")
    (out / "compose.json").write_text(json.dumps(ref), encoding="utf-8")


if __name__ == "__main__":
    main()
