#!/usr/bin/env bash
# Verifie que docs/flasher/builder.js construit un .syx modifie identique, a
# l'octet pres, au pipeline Python de tools/build.py + tools/mtlib/.
#
# Fabrique une image ELE3 synthetique (bonne taille, octets 'old' aux bons
# offsets, cave 0xFF, materiel de cle HMAC), construit les deux variantes avec
# le Python (reference), puis compare la sortie du node a ces references.
# N'a besoin d'AUCUNE image firmware Elektron.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v node >/dev/null || { echo "node est requis pour ce test"; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/webbuild.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

python3 tools/webbuild_synth.py "$tmp"
node tools/webbuild_check.js "$tmp"
echo "OK : builder.js concorde avec build.py (aPLib + conteneur + HMAC)"
