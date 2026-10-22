#!/usr/bin/env bash
# docs/flasher/composer.js against the Python composer, byte for byte (notes/61). Part 1 (B3a), no firmware needed:
# every package's object placed at a set of addresses, as tools/relocate.py places it. Part 2 (B3b), with the official
# file: the composed tweaks and the MAIN OS built from them, as tools/compose.py makes them.
#
#   tools/webcompose_check.sh                              # part 1
#   tools/webcompose_check.sh model-cycles_OS1.13.syx      # parts 1 and 2
set -euo pipefail
cycles=""
[ $# -eq 0 ] || cycles="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
cd "$(dirname "$0")/.."
command -v node >/dev/null || { echo "node is required for this check"; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/webcompose.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

if [ -z "$cycles" ]; then
  python3 tools/webcompose_synth.py "$tmp"
  node tools/webcompose_check.js "$tmp"
  echo "OK : composer.js places the packages as relocate.py does (part 2 needs model-cycles_OS1.13.syx)"
else
  python3 tools/webcompose_synth.py "$tmp" --cycles "$cycles"
  node tools/webcompose_check.js "$tmp" "$cycles"
  echo "OK : composer.js places and composes the machines as compose.py does"
fi
