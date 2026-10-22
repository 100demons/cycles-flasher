#!/usr/bin/env bash
# Verifie que docs/flasher/flasher.js valide les .syx comme tools/mtlib/syx.py.
# Fabrique un .syx valide et un .syx corrompu avec le Python, puis les passe au node.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v node >/dev/null || { echo "node est requis pour ce test"; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/webflash.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

python3 - "$tmp" <<'PYEOF' > "$tmp/meta"
import sys, random
sys.path.insert(0, "tools")
from mtlib.syx import wrap, BYTES_PER_MSG, unwrap
tmp = sys.argv[1]
raw = wrap(bytes(random.Random(3).getrandbits(8) for _ in range(37 * BYTES_PER_MSG)), 0x11)
open(f"{tmp}/good.syx", "wb").write(raw)
bad = bytearray(raw)
pos = 0
for _ in range(5):
    pos = bad.find(0xF0, pos) + 1
bad[pos + 20] ^= 0x01                                  # 7 bits : reste un octet SysEx valide
open(f"{tmp}/bad.syx", "wb").write(bad)
info = unwrap(raw)[1]                                  # controle de reference (Python)
print(info["name"], info["count"])
PYEOF

read -r NAME COUNT < "$tmp/meta"
node tools/webflash_check.js "$tmp/good.syx" "$tmp/bad.syx" "$NAME" "$COUNT"
echo "OK : le verificateur JS concorde avec mtlib/syx.py"
