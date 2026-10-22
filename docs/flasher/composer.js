/* Composes added machines in the browser: the port of tools/compose.py's path without the toolchain (notes/61,
 * increments B3a to B3c). The Python composer is the reference; tools/webcompose_check.sh compares the two byte for
 * byte, and a change to how one composes goes into the other in the same commit.
 *
 * B3a: a package's object reaches the page laid out once at offset 0 by tools/relocate.py (layout(), bundle()):
 * its code and tables in hex, each relocation as [position, base, addend] (base "code", "bss", "abs", or the name of
 * a patch point), the symbols the composer needs as [base, offset], the variables' size. place() puts it at the
 * build's addresses, as relocate.apply() does.
 *
 * License: MIT (the repository's LICENSE).
 *
 * Wrapped in an IIFE: in a classic <script>, top-level declarations are global and would collide.
 */
(function () {
"use strict";

function fromHex(s) {
  // two hexadecimal digits per byte, as everywhere in the page (builder.js); anything else is refused
  if (typeof s !== "string" || s.length % 2 || /[^0-9a-fA-F]/.test(s))
    throw new Error(`invalid hexadecimal: ${String(s).slice(0, 24)}`);
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.substr(i * 2, 2), 16);
  return out;
}

// relocate.apply(): the bundle's code at codeAt, its variables at bssAt (both 4-aligned), its patch points' symbols
// from values ({ symbol: number }). Returns { blob, symbols, bssEnd }.
function place(bundle, codeAt, bssAt, values = {}) {
  if (codeAt % 4 || bssAt % 4)
    throw new Error(`placed at 0x${codeAt.toString(16)} / 0x${bssAt.toString(16)}: code and variables start 4-aligned`);
  const bases = Object.assign(Object.create(null), { code: codeAt, bss: bssAt, abs: 0 });
  const blob = fromHex(bundle.code);
  const dv = new DataView(blob.buffer);
  for (const [pos, base, add] of bundle.relocs) {
    let v;
    if (base in bases) v = bases[base] + add;
    else if (Object.prototype.hasOwnProperty.call(values, base)) v = values[base] + add;
    else throw new Error(`undefined symbol ${base}: not one of this build's patch points`);
    dv.setUint32(pos, v >>> 0, false);
  }
  const symbols = {};
  for (const [name, [base, off]] of Object.entries(bundle.symbols)) symbols[name] = bases[base] + off;
  return { blob, symbols, bssEnd: bssAt + bundle.bss };
}

const API = { place, fromHex };
if (typeof module !== "undefined" && module.exports) module.exports = API;
if (typeof window !== "undefined") window.MCComposer = API;
})();
