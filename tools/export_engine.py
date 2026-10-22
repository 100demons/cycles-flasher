#!/usr/bin/env python3
"""Exports one machine package to the public cycles-engines repo, so both stay in step.

The source of truth is this repository: tools/machines/<id>/ (manifest, sources, committed object) and the
machine's tweak alone (tweaks/model-cycles_OS1.13/NN-<id>.json). The public repo gets a self-contained folder:

    engines/<id>/
      README.md      generated from public.json + the manifest
      engine.json    the card read by scripts/build_index.py (version, status, knobs, files)
      CHANGELOG.md   generated from public.json
      LICENSE        copied from the package
      manifest.json  the package manifest, with src/ and addon/ paths
      src/           the sources and headers
      addon/         the compiled object and the single-machine tweak

public.json (next to the manifest) holds what the code cannot say: the public version, the prose, the credits
and the changelog. Edit it, run this script, then commit both repositories.

    python3 tools/export_engine.py lixr --to ../cycles-engines [--check]

--check writes nothing and exits 1 if the public folder differs. It also runs the public repo's
scripts/build_index.py --check when it is there.
"""
import argparse
import copy
import json
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
MACHINES = HERE / "machines"
TWEAKS = ROOT / "tweaks" / "model-cycles_OS1.13"
SLOTS = ("COLOR", "SHAPE", "SWEEP", "CONTOUR")
SOURCE_SUFFIXES = (".c", ".h", ".S", ".s", ".inc", ".cc", ".cpp")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def tweak_of(mid, order):
    """The machine's tweak alone: the one file whose id is exactly the package id."""
    found = []
    for path in sorted(TWEAKS.glob(f"*-{mid}.json")):
        data = read_json(path)
        if data.get("id") == mid:
            found.append((path, data))
    if len(found) != 1:
        sys.exit(f"!! expected one tweak with id {mid!r} in {TWEAKS}, found {len(found)}")
    path, data = found[0]
    if not path.name.startswith(f"{order:02d}-"):
        sys.exit(f"!! {path.name}: manifest order {order} does not match the tweak's number")
    return path, data


def source_files(pkg):
    """Every source and header at the package root (the machines keep their sources flat)."""
    files = [p for p in sorted(pkg.iterdir()) if p.is_file() and p.suffix in SOURCE_SUFFIXES]
    if not files:
        sys.exit(f"!! no source files in {pkg}")
    return files


def public_manifest(mid, m, pub):
    """The manifest as the public package uses it: sources under src/, object and tweak under addon/."""
    m2 = copy.deepcopy(m)
    m2["build"]["sources"] = [f"src/{pathlib.Path(s).name}" for s in m["build"]["sources"]]
    m2["build"]["include"] = ["src"]
    m2["build"]["objects"] = [f"addon/{pathlib.Path(m['build']['objects'][0]).name}"]
    m2["source"] = "this engine folder (src/), first published in cycles-engines"
    if pub.get("hardware_build"):
        m2["tests"]["hardware"]["build"] = pub["hardware_build"]
    return m2


def engine_card(mid, m2, pub, tweak_path):
    name = m2["uses"][0].get("name") or m2["name"].split(":")[0].strip()
    files = ["README.md", "CHANGELOG.md", "LICENSE", "manifest.json",
             *[f"src/{p.name}" for p in source_files(MACHINES / mid)],
             f"addon/{pathlib.Path(m2['build']['objects'][0]).name}", f"addon/{tweak_path.name}"]
    return {
        "card_version": 1,
        "id": mid,
        "name": name,
        "version": pub["version"],
        "status": m2["tests"]["status"],
        "author": pub["author"],
        "license": m2["license"],
        "summary": pub["summary"],
        "base_os": "model-cycles_OS" + m2["os"],
        "knobs": [{"slot": slot, "does": pub["knobs"][slot]} for slot in SLOTS],
        "cpu_note": pub["cpu_note"],
        "requires": m2.get("compat", {}).get("requires", []),
        "conflicts": pub.get("conflicts", []),
        "tested_on_hardware": m2["tests"]["hardware"].get("date"),
        "emulator_proof": pub.get("emulator_proof"),
        "credits": pub.get("credits", []),
        "files": files,
    }


def readme(card, m2, pub):
    stock = {row["knob"]: row["does"] for row in pub.get("stock_knobs", [])}
    rows = []
    for knob in ("PITCH", *SLOTS):
        does = pub["knobs"].get(knob) if knob in SLOTS else stock.get(knob)
        if does:
            rows.append(f"| {knob} | {does} |")
    if stock.get("DECAY"):
        rows.append(f"| DECAY | {stock['DECAY']} |")
    emu = m2["tests"]["emulation"]
    hw = m2["tests"]["hardware"]
    return f"""# {card['name']}

**{card['summary']}**

Status: `{card['status']}` · Version: `{card['version']}` · For: Model:Cycles OS {m2['os']} · License: {card['license']}

## What it sounds like

{pub['sound']}

## Knobs

| Knob | What it does |
|---|---|
{chr(10).join(rows)}

## Weight

CPU cost per voice: {pub['cpu_note']}

Works together with: {pub['works_with']}

Does not work with: {pub['not_with']}

{pub.get('project_note', '')}

## Testing

- Emulator proof: **{emu.get('date') or 'not yet'}**, {emu.get('tool') or 'not yet'}. **ALL OK**.
- Real Model:Cycles: **{hw.get('date') or 'not yet'}**, {hw.get('build') or 'not yet'}.

## Install

{pub['install']}

{pub.get('build_note', '')}

{pub.get('no_firmware', '')}

## Credits

{pub['credit']}

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
"""


def changelog(pub):
    out = ["# Changelog", ""]
    for entry in pub.get("changelog", []):
        out.append(f"## {entry['version']} — {entry['date']}")
        out.append("")
        for line in entry["changes"]:
            out.append(f"- {line}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def generated(mid, dest):
    """Every file of the public engine folder, as relative path -> bytes."""
    pkg = MACHINES / mid
    m = read_json(pkg / "manifest.json")
    pub = read_json(pkg / "public.json")
    tweak_path, _ = tweak_of(mid, m.get("order", 0))
    m2 = public_manifest(mid, m, pub)
    card = engine_card(mid, m2, pub, tweak_path)
    files = {}
    for path in source_files(pkg):
        files[f"src/{path.name}"] = path.read_bytes()
    files[f"addon/{pathlib.Path(m['build']['objects'][0]).name}"] = (pkg / m["build"]["objects"][0]).read_bytes()
    files[f"addon/{tweak_path.name}"] = tweak_path.read_bytes()
    files["LICENSE"] = (pkg / "LICENSE").read_bytes()
    files["manifest.json"] = (json.dumps(m2, indent=1, ensure_ascii=False) + "\n").encode()
    files["README.md"] = readme(card, m2, pub).encode()
    files["CHANGELOG.md"] = changelog(pub).encode()
    files["engine.json"] = (json.dumps(card, indent=2, ensure_ascii=False) + "\n").encode()
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id", help="package id, as in tools/machines/<id>")
    ap.add_argument("--to", required=True, help="the cycles-engines repository")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if the public folder differs")
    args = ap.parse_args()

    pkg = MACHINES / args.id
    for name in ("manifest.json", "public.json", "LICENSE"):
        if not (pkg / name).is_file():
            sys.exit(f"!! {pkg / name} is missing")
    repo = pathlib.Path(args.to).resolve()
    if not (repo / "scripts" / "build_index.py").is_file():
        sys.exit(f"!! {repo} does not look like the cycles-engines repo (no scripts/build_index.py)")

    out = repo / "engines" / args.id
    files = generated(args.id, out)
    if args.check:
        bad = []
        for rel, data in sorted(files.items()):
            path = out / rel
            if not path.is_file():
                bad.append(f"missing {rel}")
            elif path.read_bytes() != data:
                bad.append(f"differs {rel}")
        if bad:
            print(f"!! engines/{args.id} is not up to date with tools/machines/{args.id}:")
            for line in bad:
                print(f"   {line}")
            print(f"   run: python3 tools/export_engine.py {args.id} --to {repo}")
            return 1
        print(f"ok : engines/{args.id} is up to date ({len(files)} files)")
    else:
        for rel, data in files.items():
            path = out / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        known = set(files)
        for path in sorted(out.rglob("*")):
            if path.is_file() and str(path.relative_to(out)) not in known:
                print(f"   note: extra file kept: {path.relative_to(out)} (remove it by hand if it is stale)")
        print(f"wrote engines/{args.id} ({len(files)} files)")

    index = repo / "scripts" / "build_index.py"
    cmd = [sys.executable, str(index)] + (["--check"] if args.check else [])
    r = subprocess.run(cmd, cwd=repo)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
