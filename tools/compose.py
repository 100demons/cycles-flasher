#!/usr/bin/env python3
"""Composes added machines into one tweak at build time (notes/59, increment B1 of the Cycles Mod Standard's
Level B).

A machine is a package: tools/machines/<id>/ with its sources and a manifest.json (schema cycles-mod/0.1). The
composer takes the packages the user names, in that order, and:

  1. places each package's committed object (tools/machines/<id>/<id>.o, written by its generator) at its address
     with tools/relocate.py, the values that depend on the build resolved as symbols (its "patch_points": the
     machine index, 6 + i, and its first descriptor, 76 + 5 i); or, with --relocator ld, compiles and links the
     sources as B1 did (--compare-ld does both and compares them, notes/60 §3);
  2. lays them out in the added machines' payload window (0x43000000, gs.PAY_ALONE): code and tables one after the
     other from the window's start, variables one after the other from +0x36000 (above the moved tables, as MACRO),
     links each one there, and refuses a layout that crosses the stubs or a package's RAM claim;
  3. registers them all at once through gen_macro.added_machine (the tables of names, update/render, records and
     descriptors, the bounds, the detours, the boot hook), then adds each package's own hooks and vtable entries
     from its manifest;
  4. computes what the result cannot be installed with: every tweak of tweaks/ that writes other bytes to the same
     address or runs a payload in the composed payload or in a claimed RAM range, plus what the manifests declare;
  5. emits one tweak in Modded-Cycles' format, which tools/build.py and the web flasher apply like any other, and
     builds the .syx with build.py's own steps (writes checked against the stock bytes, caves checked, repacked and
     re-signed, read back).

One machine alone gives the same tweak as its own generator (sampler: 27-sampler.json, byte for byte); two or more
give what no pre-built file holds. The composed tweak is written to build/ (git-ignored), not to tweaks/: it is a
build, not a mod.

    python3 tools/compose.py --cycles model-cycles_OS1.13.syx --machines sampler,refmachine \\
        [--with arp,trig-hold] [--out build/] [--emit path.json] [--compare tweaks/model-cycles_OS1.13/27-sampler.json] \\
        [--tool path/to/elektron-firmware-tool] [--relocator python|ld] [--compare-ld]

Runs with python3 alone (the relocator); --relocator ld and --compare-ld need the m68k toolchain, as the
package generators do (they compile and commit the objects).
"""
import argparse
import hashlib
import hmac
import json
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "emu"))

import build as mcb                # noqa: E402
import aplib_grow                  # noqa: E402
import gen_macro as gm             # noqa: E402
import gen_sdvintage_exact as gx   # noqa: E402
import gen_sdvintage_7th as g7     # noqa: E402
import gen_syntakt_engines as gs   # noqa: E402
import relocate                    # noqa: E402

BASE = mcb.BASE
DEV = ROOT / "tweaks" / "model-cycles_OS1.13"
MACHINES = HERE / "machines"
BUILD = ROOT / "build"
LINK = """SECTIONS
{{
  .text {code:#x} : {{ *(.text.{update}) *(.text.{render}) *(.text*) }}
  .rodata : {{ *(.rodata*) }}
  .data : {{ *(.data*) }}
  .bss {bss:#x} (NOLOAD) : {{ *(.bss*) *(COMMON) }}
  /DISCARD/ : {{ *(.comment) *(.note*) *(.eh_frame*) }}
}}
"""


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_manifest(mid):
    path = MACHINES / mid / "manifest.json"
    if not path.is_file():
        sys.exit(f"!! no package {mid}: {path} is missing")
    m = json.loads(path.read_text(encoding="utf-8"))
    if m.get("schema") != "cycles-mod/0.1":
        sys.exit(f"!! {path}: schema {m.get('schema')!r}, expected cycles-mod/0.1")
    if m["id"] != mid:
        sys.exit(f"!! {path}: id {m['id']!r} is not the folder's name")
    m["_dir"] = MACHINES / mid
    m["_machine"] = next((u for u in m["uses"] if u["point"] == "machine"), None)
    if not m["_machine"]:
        sys.exit(f"!! {mid}: no 'machine' entry in uses: not an added machine")
    return m


def align4(x):
    return (x + 3) & ~3


def patch_values(m, values):
    """The build's values for the package's patch points: (defines for the compiler, symbols for the relocator).
    A patch point is {"symbol": name, "kind": kind} (resolved like ld --defsym when the object is placed) or, the
    B1 form, {"define": NAME, "kind": kind} (a compile-time constant: the object then carries one index for ever,
    so a committed object cannot use it)."""
    defines, symbols = [], {}
    for pp in m["build"].get("patch_points", []):
        if pp["kind"] not in values:
            sys.exit(f"!! {m['id']}: patch point kind {pp['kind']!r} unknown")
        if "symbol" in pp:
            symbols[pp["symbol"]] = values[pp["kind"]]
        elif "define" in pp:
            defines.append(f"-D{pp['define']}={values[pp['kind']]}")
        else:
            sys.exit(f"!! {m['id']}: a patch point needs 'symbol' or 'define'")
    return defines, symbols


def compile_objects(m, tmp, defines=()):
    """Compiles the package's sources with its flags (and the given defines) into tmp; returns the objects in the
    manifest's order."""
    b, d = m["build"], m["_dir"]
    defs = [f"-D{k}={v}" for k, v in b.get("defines", {}).items()] + list(defines)
    incs = [f"-I{d / i}" for i in b.get("include", [])]
    objs = []
    for rel in b["sources"]:
        src = d / rel
        if not src.is_file():
            sys.exit(f"!! {m['id']}: source {src} is missing")
        o = tmp / f"{m['id']}-{src.stem}.o"
        gx.run([gx.CROSS + "gcc", *b["cflags"], *defs, *incs, "-c", str(src), "-o", str(o)])
        objs.append(o)
    return objs


def object_path(m):
    objs = m["build"].get("objects", [])
    if len(objs) != 1:
        sys.exit(f"!! {m['id']}: build.objects must name one object (ld -r of the sources), has {objs}")
    return m["_dir"] / objs[0]


def build_object(m, tmp):
    """The package's object as its generator commits it: the sources compiled with the manifest's recipe and
    joined with ld -r (one relocatable file, every function and table still a section of its own, the patch
    points still undefined symbols)."""
    objs = compile_objects(m, tmp)
    out = tmp / f"{m['id']}.o"
    gx.run([gx.CROSS + "ld", "-r", "-o", str(out), *map(str, objs)])
    return out.read_bytes()


def compile_package(m, tmp, code_at, bss_at, code_end, values):
    """The B1 path, with the toolchain: compiles the package's sources with its flags and the build's values for
    its patch points, links them at code_at (code, tables, data) and bss_at (variables); the code must end before
    code_end. Returns (bytes from code_at to the end of the data, symbols, end of the variables)."""
    b = m["build"]
    defines, symbols = patch_values(m, values)
    objs = compile_objects(m, tmp, defines)
    upd, rnd = b["symbols"]["update"], b["symbols"]["render"]
    ld, elf, out = tmp / f"{m['id']}.ld", tmp / f"{m['id']}.elf", tmp / f"{m['id']}.bin"
    ld.write_text(LINK.format(update=upd, render=rnd, code=code_at, bss=bss_at))
    keep = [a for s_ in b.get("keep", []) for a in ("-u", s_)]
    defsym = [a for k, v in symbols.items() for a in ("--defsym", f"{k}={v}")]
    gx.run([gx.CROSS + "ld", "-T", str(ld), "--gc-sections", "--no-warn-rwx-segments", "-e", upd, "-u", rnd, *keep,
            *defsym, "-o", str(elf), *map(str, objs)])
    secs = {}
    for line in gx.run([gx.CROSS + "objdump", "-h", str(elf)]).splitlines():
        f = line.split()
        if len(f) > 4 and f[0].isdigit():
            secs[f[1]] = (int(f[3], 16), int(f[2], 16))      # address, size
    if set(secs) - {".text", ".rodata", ".data", ".bss"}:
        sys.exit(f"!! {m['id']}: unexpected sections {sorted(secs)}")
    gx.run([gx.CROSS + "objcopy", "-O", "binary", "-R", ".bss", str(elf), str(out)])
    blob = out.read_bytes()
    syms = {p[2]: int(p[0], 16) for p in (l.split() for l in gx.run([gx.CROSS + "nm", str(elf)]).splitlines())
            if len(p) == 3}
    for s_ in (upd, rnd, *b.get("keep", [])):
        if s_ not in syms:
            sys.exit(f"!! {m['id']}: symbol {s_} not in the linked object")
    if code_at + len(blob) > code_end:
        sys.exit(f"!! {m['id']}: code and tables end at {code_at + len(blob):#x}, past {code_end:#x}")
    bss = secs.get(".bss", (bss_at, 0))
    if bss[0] != bss_at:
        sys.exit(f"!! {m['id']}: variables at {bss[0]:#x}, expected {bss_at:#x}")
    return blob, syms, align4(bss[0] + bss[1])


def place_package(m, code_at, bss_at, code_end, values, obj=None):
    """The B2 path, no toolchain: places the package's committed object (or obj, bytes) at code_at and bss_at with
    tools/relocate.py, the patch points resolved to the build's values. Same result as compile_package."""
    b = m["build"]
    defines, symbols = patch_values(m, values)
    if defines:
        sys.exit(f"!! {m['id']}: patch points as defines cannot be applied to a committed object: use symbols")
    if obj is None:
        path = object_path(m)
        if not path.is_file():
            sys.exit(f"!! {m['id']}: {path} is missing: run the package's generator (it writes the object)")
        obj = path.read_bytes()
    return relocate.place(obj, b["symbols"]["update"], b["symbols"]["render"], b.get("keep", []), code_at, bss_at,
                          code_end, symbols, m["id"])


def emit_bytes(path, data, check):
    """Writes a binary file, or with check compares it with the committed one (like gen_macro.emit for text)."""
    if check:
        ok = path.exists() and path.read_bytes() == data
        why = ""
        if not ok and path.exists():
            try:
                why = (f" (committed object: {relocate.Elf(path.read_bytes(), path.name).comment()}; here: "
                       f"{relocate.Elf(data, 'new').comment()})")
            except SystemExit:
                pass
        print(f"    {path.name} {'is up to date' if ok else 'DOES NOT MATCH' + why}")
        return not ok
    path.write_bytes(data)
    print(f"    wrote {path}")
    return 0


def package_writes(m, img, syms):
    """The package's own hooks (jsr/jmp into its code) and vtable entries, each checked against the stock bytes."""
    writes = []
    for u in m["uses"]:
        if "hook" in u:
            h = u["hook"]
            va, old = int(h["at"], 16), bytes.fromhex(h["stock"])
            target = g7.be32(syms[h["symbol"]])
            new = (bytes.fromhex("4eb9") + target if h["op"] == "jsr"
                   else bytes.fromhex("4ef9") + target + bytes.fromhex("4e71"))
            if len(new) != len(old):
                sys.exit(f"!! {m['id']}: hook at {va:#x}: {len(new)} bytes for {len(old)}")
            if img[va - BASE:va - BASE + len(old)] != old:
                sys.exit(f"!! {m['id']}: {va:#x}: {old.hex()} expected, {img[va - BASE:va - BASE + len(old)].hex()} found")
            writes.append({"off": va - BASE, "old": old.hex(), "new": new.hex()})
        elif "vtable" in u:
            vt = u["vtable"]
            va, method = int(vt["at"], 16), int(vt["stock_ptr"], 16)
            if g7.refs32(img, method) != [va]:
                sys.exit(f"!! {m['id']}: references to {method:#x}: {[hex(r) for r in g7.refs32(img, method)]}")
            writes.append({"off": va - BASE, "old": g7.be32(method).hex(), "new": g7.be32(syms[vt["symbol"]]).hex()})
    return writes


def ram_claims(m):
    return [(int(a, 16), int(b, 16)) for u in m["uses"] if u["point"] == "memory.ram" for a, b in [u["range"]]]


def computed_conflicts(writes, ram, declared):
    """Ids of the folder's tweaks this build cannot be installed with: other bytes at the same address, or a
    payload in one of our RAM ranges. The same whole write is not a conflict (check_overlaps.py's rule)."""
    mine = {}
    for w in writes:
        for i, b in enumerate(bytes.fromhex(w["new"])):
            mine[w["off"] + i] = b
    ids = set(declared)
    for f in sorted(DEV.glob("*.json")):
        if f.name == "device.json":
            continue
        t = json.loads(f.read_text(encoding="utf-8"))
        tid = t.get("id")
        if not tid:
            continue
        clash = any(mine.get(w["off"] + i, b) != b
                    for w in t.get("writes", []) for i, b in enumerate(bytes.fromhex(w["new"])))
        ap = t.get("append")
        if ap and not clash:
            lo, hi = int(ap["dest"], 16), int(ap["dest"], 16) + ap["size"]
            clash = any(lo < b and a < hi for a, b in ram)
        if clash:
            ids.add(tid)
    return ids


def compose(img, ids, relocator="python", compare_ld=False):
    """Builds the tweak for the machines named in ids, in that order. relocator: "python" places each
    package's committed object with tools/relocate.py (no toolchain), "ld" compiles and links it as B1 did;
    compare_ld does both and compares them byte for byte (the proof of the relocator). Returns (tweak, info)."""
    if not ids:
        sys.exit("!! name at least one machine")
    if len(ids) != len(set(ids)):
        sys.exit("!! a machine is named twice")
    mans = [load_manifest(i) for i in ids]
    pay = gs.PAY_ALONE
    gs.set_base(pay)
    first = 6
    machines, blobs, syms_of, info_pkgs = [], [], {}, []
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        code_cursor, bss_cursor = pay, pay + gm.BSS_OFF
        for i, m in enumerate(mans):
            code_at, bss_at = align4(code_cursor), align4(bss_cursor)
            values = {"machine_index": first + i, "descriptor_base": 76 + 5 * i}
            if relocator == "ld":
                blob, syms, bss_end = compile_package(m, tmp, code_at, bss_at, gs.STUBS, values)
            else:
                blob, syms, bss_end = place_package(m, code_at, bss_at, gs.STUBS, values)
            if compare_ld:
                if relocator == "ld":
                    b2, s2, e2 = place_package(m, code_at, bss_at, gs.STUBS, values)
                else:
                    b2, s2, e2 = compile_package(m, tmp, code_at, bss_at, gs.STUBS, values)
                same = blob == b2 and bss_end == e2 and all(s2.get(k) == v for k, v in syms.items() if k in s2)
                print(f"  compare-ld {m['id']:12s} {'identical' if same else 'DIFFERENT'}: relocator {len(blob)} bytes, "
                      f"ld {len(b2)} bytes, variables end {bss_end:#x} / {e2:#x}")
                if not same:
                    i_ = next((k for k in range(min(len(blob), len(b2))) if blob[k] != b2[k]), min(len(blob), len(b2)))
                    bad = {k: (f"{v:#x}", f"{s2[k]:#x}") for k, v in syms.items() if k in s2 and s2[k] != v}
                    sys.exit(f"!! {m['id']}: relocator and ld differ, first byte at +{i_:#x}; symbols {bad}")
            mc = m["_machine"]
            knobs = tuple((k["long"], k["short"], k["default"]) + ((k["min"], k["max"]) if "min" in k else ())
                          for k in mc["knobs"])
            machines.append(dict(name=mc["name"], image=mc["image"], decay=mc["decay_default"], knobs=knobs,
                                 update=syms[m["build"]["symbols"]["update"]],
                                 render=syms[m["build"]["symbols"]["render"]]))
            blobs.append((code_at, blob))
            syms_of[m["id"]] = syms
            info_pkgs.append(dict(id=m["id"], index=first + i, desc=76 + 5 * i, code_at=code_at, code=len(blob),
                                  bss_at=bss_at, bss=bss_end - bss_at))
            code_cursor, bss_cursor = code_at + len(blob), bss_end
        for m in mans:                       # a package's RAM claim must lie outside the payload
            for lo, hi in ram_claims(m):
                if lo < bss_cursor and pay < hi:
                    sys.exit(f"!! {m['id']}: the payload ({pay:#x}..{bss_cursor:#x}) runs into its RAM claim {lo:#x}..{hi:#x}")
        writes, append = gm.added_machine(img, None, machines, tmp, blobs, bss_cursor)
    for m in mans:
        writes += package_writes(m, img, syms_of[m["id"]])
    writes.sort(key=lambda x: x["off"])
    for a_, b_ in zip(writes, writes[1:]):
        if a_["off"] + len(a_["new"]) // 2 > b_["off"]:
            sys.exit(f"!! writes overlap at {BASE + b_['off']:#x}")
    ram = [(pay, bss_cursor)] + [r for m in mans for r in ram_claims(m)]
    declared = {c["with"] for m in mans for c in m.get("compat", {}).get("conflicts_declared", [])}
    tid = "+".join(ids)
    conflicts = computed_conflicts(writes, ram, declared) - {tid}
    tweak = {
        "id": tid,
        "order": min(m["order"] for m in mans),
        "name": " + ".join(m["name"] for m in mans) if len(mans) > 1 else mans[0]["name"],
        "description": [
            f"Composed by tools/compose.py (notes/59): {', '.join(f'{p['id']} as machine {p['index']}' for p in info_pkgs)},",
            "registered together through gen_macro.added_machine; each machine's code from tools/machines/<id>/",
            "(manifest.json), compiled and linked at build time at its place in the payload (%#x..%#x)." % (pay, bss_cursor),
            "Conflicts computed from the other tweaks: other bytes at the same address, or a payload in this",
            "build's payload or in a claimed RAM range.",
        ] + [f"{m['id']}: {m['name']}" for m in mans],
        "device": "Model:Cycles",
        "os": "1.13",
        "section": 3,
        "version": "+".join(m["version"] for m in mans),
        "conflicts": sorted(conflicts),
        "writes": writes,
        "append": append,
        "symbols": {k: f"{v:#x}" for m in mans for k, v in syms_of[m["id"]].items()
                    if k in (m["build"]["symbols"]["update"], m["build"]["symbols"]["render"], *m["build"].get("keep", []))},
    }
    info = dict(pay=pay, end=bss_cursor, image=sum(n for _, n in append["pack"]), packages=info_pkgs)
    return tweak, info


def build_syx(raw, tweaks, syntakt=None):
    """Applies the tweaks to the stock file with build.py's own steps; returns (syx, patched MAIN OS)."""
    stream, info = mcb.unwrap(raw)
    c = mcb.container.parse(stream)
    s3 = next(s for s in c["sections"] if s["id"] == 3)
    main_os, ops = mcb.aplib.depack(c["blob"][s3["off"]:s3["off"] + s3["size"]])
    dev = json.loads((DEV / "device.json").read_text(encoding="utf-8"))
    if sha(main_os) != dev["section_sha256"]:
        sys.exit("!! the MAIN OS is not the official 1.13")
    mcb.check_conflicts(tweaks)
    tweaks = sorted(tweaks, key=lambda t: t["order"])
    patched, dirty = mcb.apply_writes(main_os, tweaks)
    mcb.check_caves(main_os, tweaks, False, dirty, patched, dev.get("cave_refs_ok"))
    payload, _ = mcb.build_payload(tweaks, main_os, syntakt)
    orig_len = len(patched)
    patched += payload
    dirty += bytearray(b"\x01") * len(payload)
    new_s3 = aplib_grow.repack_grow(patched, ops, dirty, orig_len)
    if mcb.aplib.depack(new_s3)[0] != patched:
        sys.exit("!! the repacked MAIN OS reads back different")
    msg = c["blob"][:len(c["blob"]) - mcb.container.DIGEST_LEN]
    expect = c["blob"][len(c["blob"]) - mcb.container.DIGEST_LEN:]
    plain = []
    for s in c["sections"]:
        try:
            plain.append(mcb.aplib.depack(c["blob"][s["off"]:s["off"] + s["size"]])[0])
        except Exception:
            pass
    key = mcb.container.find_key(plain, msg, expect)
    if not key:
        sys.exit("!! HMAC key not found")
    blob = mcb.container.rebuild(c, {3: new_s3}, key)
    out = mcb.wrap(mcb.container.build_stream(blob, mcb.BYTES_PER_MSG), info["product"], info["start_seq"])
    stream2, _ = mcb.unwrap(out)
    c2 = mcb.container.parse(stream2)
    s3b = next(s for s in c2["sections"] if s["id"] == 3)
    if mcb.aplib.depack(c2["blob"][s3b["off"]:s3b["off"] + s3b["size"]])[0] != patched:
        sys.exit("!! the written file does not unpack to the patched MAIN OS")
    body = c2["blob"][:len(c2["blob"]) - mcb.container.DIGEST_LEN]
    mac = c2["blob"][len(c2["blob"]) - mcb.container.DIGEST_LEN:]
    if hmac.new(key, body, hashlib.sha256).digest() != mac:
        sys.exit("!! HMAC of the written file does not verify")
    return out, patched


def check_with_tool(tool, path, patched):
    res = subprocess.run([tool, "-i", str(path)], capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"!! elektron-firmware-tool rejects the file (exit {res.returncode}):\n{res.stdout}{res.stderr}")
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([tool, "-i", str(path), "-d", "3", "-o", d], check=True, capture_output=True)
        if (pathlib.Path(d) / "section_3_MAIN_OS.bin").read_bytes() != patched:
            sys.exit("!! elektron-firmware-tool unpacks a different MAIN OS")
    print("  elektron-firmware-tool: checksums and HMAC ok, same MAIN OS")


def compare(tweak, path):
    """The composed tweak against a committed one: writes, payload, and the entry points' addresses."""
    ref = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    same = {"writes": tweak["writes"] == ref["writes"], "append": tweak["append"] == ref["append"],
            "symbols": all(tweak["symbols"].get(k) == v for k, v in ref.get("symbols", {}).items())}
    for k, ok in same.items():
        print(f"  compare {k:8s} {'identical' if ok else 'DIFFERENT'} to {pathlib.Path(path).name}")
    return all(same.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="official model-cycles_OS1.13.syx")
    ap.add_argument("--machines", required=True, help="package ids under tools/machines/, in order, comma-separated")
    ap.add_argument("--with", dest="with_", default="", help="other tweaks of tweaks/ to install with it, comma-separated")
    ap.add_argument("--out", default=str(BUILD), help="folder for the .syx and the report (default: build/)")
    ap.add_argument("--emit", help="also write the composed tweak JSON here")
    ap.add_argument("--compare", help="a committed tweak JSON to compare writes and payload with")
    ap.add_argument("--tool", help="elektron-firmware-tool, for an independent check")
    ap.add_argument("--relocator", choices=("python", "ld"), default="python",
                    help="python: place the committed objects with tools/relocate.py (default); ld: compile and link (B1)")
    ap.add_argument("--compare-ld", action="store_true", help="do both and compare them byte for byte")
    args = ap.parse_args()
    raw = pathlib.Path(args.cycles).read_bytes()
    img = g7.cycles_main(args.cycles)
    if len(img) != gx.IMAGE_LEN:
        sys.exit("!! not the official MAIN OS 1.13")
    ids = [i.strip() for i in args.machines.split(",") if i.strip()]
    tweak, info = compose(img, ids, args.relocator, args.compare_ld)
    for p in info["packages"]:
        print(f"  {p['id']:12s} machine {p['index']}, descriptors {p['desc']}..{p['desc'] + 4}, code {p['code']} bytes at "
              f"{p['code_at']:#x}, variables {p['bss']} bytes at {p['bss_at']:#x}")
    print(f"  tweak {tweak['id']}: {len(tweak['writes'])} writes, payload {info['pay']:#x}..{info['end']:#x}, "
          f"{info['image']} bytes added to the image, {len(tweak['conflicts'])} conflicts computed")
    ok = True
    if args.compare:
        ok = compare(tweak, args.compare)
    if args.emit:
        pathlib.Path(args.emit).write_text(json.dumps(tweak, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  wrote {args.emit}")
    others = []
    for tid in (t.strip() for t in args.with_.split(",") if t.strip()):
        path = next((f for f in DEV.glob("*.json") if f.name != "device.json"
                     and json.loads(f.read_text(encoding="utf-8")).get("id") == tid), None)
        if not path:
            sys.exit(f"!! unknown tweak {tid}")
        others.append(json.loads(path.read_text(encoding="utf-8")))
    out, patched = build_syx(raw, [tweak] + others)
    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    name = "+".join([tweak["id"]] + [t["id"] for t in others])
    path = outdir / f"model-cycles_OS1.13-{name}.syx"
    path.write_bytes(out)
    report = {"machines": ids, "with": [t["id"] for t in others], "stock_sha256": sha(raw),
              "main_os": {"sha256": sha(patched), "bytes": len(patched), "end": f"{BASE + len(patched):#x}"},
              "output": {"file": path.name, "sha256": sha(out), "bytes": len(out)}, "layout": info}
    path.with_suffix(".syx.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"  wrote {path} ({len(out)} bytes)\n  MAIN OS {len(patched)} bytes, SHA-256 {sha(patched)}")
    if args.tool:
        check_with_tool(args.tool, path, patched)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
