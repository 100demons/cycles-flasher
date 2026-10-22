#!/usr/bin/env bash
# docs/flasher/composer.js against the Python composer, byte for byte (notes/61). Part 1 (B3a), no firmware needed:
# every package's object placed at a set of addresses, as tools/relocate.py places it.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v node >/dev/null || { echo "node is required for this check"; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/webcompose.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

python3 tools/webcompose_synth.py "$tmp"
node tools/webcompose_check.js "$tmp"
echo "OK : composer.js places the packages as relocate.py does"
