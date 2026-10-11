#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# The functions transcribed from Elektroid (src/connectors/elektron.c) are
# Copyright (C) 2019 David García Goñi, GPL-3.0-or-later; translated to Python for Modded-Cycles in 2026.
# Unlike the rest of the repository (MIT), this file is under the GPL-3.0-or-later: LICENSES/GPL-3.0-or-later.txt.
"""Checks the fast USB path of the web flasher (docs/flasher/flasher.js) against a line by line
transcription of Elektroid's C (src/connectors/elektron.c, https://github.com/dagargo/elektroid):
7-bit packing both ways, the CRC of a block, and the bytes of the OS upgrade messages.

    python3 tools/webxfer_check.py          # needs node

The transcription below follows the C names, so a reviewer can put them side by side.
"""
import json
import math
import pathlib
import random
import subprocess
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MSG_HEADER = bytes([0xF0, 0, 0x20, 0x3C, 0x10, 0])
OS_TRANSF_BLOCK_BYTES = 0x800
OS_UPGRADE_START_REQUEST = bytes([0x50, 0, 0, 0, 0]) + b"sysex\0" + bytes([1])
OS_UPGRADE_WRITE_RESPONSE = bytes([0x51] + [0] * 12)


def elektron_encode_payload(src):
    dst = bytearray(len(src) + math.ceil(len(src) / 7))
    i = j = 0
    while j < len(src):
        accum = 0
        for k in range(7):
            accum <<= 1
            if j + k < len(src):
                if src[j + k] & 0x80:
                    accum |= 1
                dst[i + k + 1] = src[j + k] & 0x7F
        dst[i] = accum
        i += 8
        j += 7
    return bytes(dst)


def elektron_decode_payload(src):
    dst = bytearray(len(src) - math.ceil(len(src) / 8))
    i = j = 0
    while i < len(src):
        shift = 0x40
        k = 0
        while k < 7 and i + k + 1 < len(src):
            dst[j + k] = src[i + k + 1] | (0x80 if src[i] & shift else 0)
            shift >>= 1
            k += 1
        i += 8
        j += 7
    return bytes(dst)


def elektron_new_msg(data):
    return bytearray(b"\0\0\0\0" + data)


def elektron_tx(msg, seq):
    """elektron_tx + elektron_msg_to_raw: sequence number in front, packed, framed."""
    msg = bytearray(msg)
    msg[0:2] = seq.to_bytes(2, "big")
    return MSG_HEADER + elektron_encode_payload(bytes(msg)) + b"\xf7"


def elektron_new_msg_upgrade_os_start(size):
    msg = elektron_new_msg(OS_UPGRADE_START_REQUEST)
    msg[5:9] = size.to_bytes(4, "little")       # memcpy of a guint32 on a little-endian host
    return msg


def elektron_crc(data):
    return zlib.crc32(data, 0xFFFFFFFF)          # crc32 (0xffffffff, data, len)


def elektron_new_msg_upgrade_os_write(os_data, offset):
    msg = elektron_new_msg(OS_UPGRADE_WRITE_RESPONSE)
    n = OS_TRANSF_BLOCK_BYTES if offset + OS_TRANSF_BLOCK_BYTES < len(os_data) else len(os_data) - offset
    msg[5:9] = elektron_crc(os_data[offset:offset + n]).to_bytes(4, "big")
    msg[9:13] = n.to_bytes(4, "big")
    msg[13:17] = offset.to_bytes(4, "big")
    msg += os_data[offset:offset + n]
    return msg, offset + n


def main():
    rnd = random.Random(37)
    payloads = [bytes(rnd.getrandbits(8) for _ in range(n)) for n in (0, 1, 5, 6, 7, 8, 13, 14, 15, 100, 2061)]
    os_data = bytes(rnd.getrandbits(8) for _ in range(3 * OS_TRANSF_BLOCK_BYTES + 777))

    # what Elektroid would send for an OS upgrade of os_data, starting at sequence number 5
    want_frames = [elektron_tx(elektron_new_msg_upgrade_os_start(len(os_data)), 5).hex()]
    offset, seq = 0, 6
    while offset < len(os_data):
        msg, offset = elektron_new_msg_upgrade_os_write(os_data, offset)
        want_frames.append(elektron_tx(msg, seq).hex())
        seq += 1

    js = r"""
const F = require(process.argv[1]);
const inp = JSON.parse(require("fs").readFileSync(0, "utf8"));
const hex = (u) => Buffer.from(u).toString("hex");
const un = (h) => new Uint8Array(Buffer.from(h, "hex"));
const out = { enc: [], dec: [], crc: [] };
for (const p of inp.payloads) {
  out.enc.push(hex(F.encode7(un(p))));
  out.dec.push(hex(F.decode7(F.encode7(un(p)))));
  out.crc.push(F.crc32(un(p), 0xffffffff));
}
// record the frames upgradeFast sends to a machine that accepts every block
const frames = [];
let seq = 5;
const session = { request(body) {
  const payload = new Uint8Array(4 + body.length);
  payload[0] = seq >> 8; payload[1] = seq & 0xff; payload.set(body, 4); seq++;
  frames.push(hex(F.xferFrame(payload)));
  const r = new Uint8Array(16); r[4] = body[0] | 0x80;
  return Promise.resolve(r);
} };
F.upgradeFast(session, un(inp.os), { restMs: 0 }).then((res) => {
  out.frames = frames; out.res = res;
  process.stdout.write(JSON.stringify(out));
});
"""
    inp = json.dumps({"payloads": [p.hex() for p in payloads], "os": os_data.hex()})
    r = subprocess.run(["node", "-e", js, str(ROOT / "docs" / "flasher" / "flasher.js")],
                       input=inp, capture_output=True, text=True, check=True)
    got = json.loads(r.stdout)

    fails = 0

    def check(cond, msg):
        nonlocal fails
        print(("  ok  " if cond else "  FAIL ") + msg)
        fails += not cond

    check(got["enc"] == [elektron_encode_payload(p).hex() for p in payloads],
          f"encode7 = elektron_encode_payload on {len(payloads)} payloads (0 to 2061 bytes)")
    check(got["dec"] == [p.hex() for p in payloads]
          and all(elektron_decode_payload(elektron_encode_payload(p)) == p for p in payloads),
          "decode7 = elektron_decode_payload, and both undo the packing")
    check(got["crc"] == [elektron_crc(p) for p in payloads], "crc32(block, 0xffffffff) = zlib crc32 (0xffffffff, ...)")
    check(got["frames"] == want_frames,
          f"upgradeFast sends Elektroid's exact bytes: start + {len(want_frames) - 1} blocks of 0x800 (last one short)")
    check(got["res"]["sent"] == len(os_data) and not got["res"]["cancelled"], "the whole file is sent")
    print("\nALL OK" if not fails else f"\nFAILED ({fails})")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
