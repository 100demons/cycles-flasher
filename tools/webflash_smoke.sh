#!/usr/bin/env bash
# Browser smoke test of the web flasher (docs/flasher/) with jsdom: loads the real
# page and its scripts, fakes Web MIDI, and walks through the 4 steps (choose, OS file,
# connect, flash, stop). Checks there is NO JS error, that each step says what is
# missing, and that building then sending works.
#
#   tools/webflash_smoke.sh                               # synthetic OS only
#   tools/webflash_smoke.sh model-cycles_OS1.13.syx       # + the REF_MAINOS sample vs its reference hashes, each mod checked
#   tools/webflash_smoke.sh model-cycles_OS1.13.syx model-samples_OS1.13.syx   # + the "Samples OS" tab
#   tools/webflash_smoke.sh model-cycles_OS1.13.syx Syntakt_OS1.42.syx         # + the Syntakt engines (1.41 too)
#   SMOKE_JOBS=4 tools/webflash_smoke.sh ...                                  # real-OS combinations in 4 parallel parts
# (official files are told apart by their names; any order)
#
# jsdom is installed in a temporary folder (npm): nothing is added to the repository.
# Needs node, npm and network access (registry.npmjs.org).
set -euo pipefail
cd "$(dirname "$0")/.."
command -v node >/dev/null || { echo "node is required"; exit 1; }
command -v npm >/dev/null || { echo "npm is required"; exit 1; }
REAL=()
for f in "$@"; do REAL+=("$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"); done

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

python3 tools/webbuild_synth.py "$tmp" >/dev/null       # makes synth.syx + meta.json
( cd "$tmp" && npm init -y >/dev/null 2>&1 && npm install jsdom >/dev/null 2>&1 )
JOBS="${SMOKE_JOBS:-1}"                                 # SMOKE_JOBS=4 : the real-OS combinations in 4 parallel parts
if [ "$JOBS" -le 1 ] || [ ${#REAL[@]} -eq 0 ]; then
  NODE_PATH="$tmp/node_modules" node tools/webflash_smoke.js "$tmp" ${REAL[@]+"${REAL[@]}"}
  exit
fi
pids=()
for k in $(seq 0 $((JOBS - 1))); do
  SMOKE_SHARD="$k/$JOBS" SMOKE_SEEN="$tmp/seen$k.json" NODE_PATH="$tmp/node_modules" \
    node tools/webflash_smoke.js "$tmp" "${REAL[@]}" > "$tmp/part$k.log" 2>&1 &
  pids+=("$!")
done
status=0
for p in "${pids[@]}"; do wait "$p" || status=1; done
for k in $(seq 0 $((JOBS - 1))); do echo "== part $((k + 1))/$JOBS"; cat "$tmp/part$k.log"; done
node -e '
  const parts = process.argv.slice(1).map((f) => JSON.parse(require("fs").readFileSync(f, "utf8")));
  const seen = new Set(parts.flatMap((p) => p.seen)), offered = parts[0].offered;
  const ok = seen.size === offered.length && offered.every((k) => seen.has(k));
  console.log((ok ? "  ok  " : "  FAIL ") + `REF_MAINOS: the ${seen.size} combinations of the sample all built (all parts)`);
  process.exit(ok ? 0 : 1);' "$tmp"/seen*.json || status=1
echo
[ "$status" -eq 0 ] && echo "ALL PARTS OK" || echo "SOME PART FAILED"
exit "$status"
