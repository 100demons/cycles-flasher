// docs/flasher/composer.js against the Python composer (tools/webcompose_synth.py writes the reference): part 1
// (B3a, notes/61), each package placed at every reference placement gives relocate.place's bytes, entry symbols and
// end of the variables.
//   node tools/webcompose_check.js <dir with compose.json>
const fs = require("fs"), path = require("path");
const C = require("../docs/flasher/composer.js");

const ref = JSON.parse(fs.readFileSync(path.join(process.argv[2], "compose.json")));
let ok = Object.keys(ref).length > 0;
for (const [id, { bundle, cases }] of Object.entries(ref)) {
  let same = 0;
  for (const c of cases) {
    const r = C.place(bundle, c.code_at, c.bss_at, c.values);
    const bytes = Buffer.from(r.blob).toString("hex") === c.blob;
    const syms = Object.keys(c.symbols).every((k) => r.symbols[k] === c.symbols[k]);
    const end = r.bssEnd === c.bss_end;
    if (bytes && syms && end) same++;
    else console.log(`  ${id} at 0x${c.code_at.toString(16)} / 0x${c.bss_at.toString(16)}: bytes ${bytes}, symbols ${syms}, end ${end}`);
  }
  console.log(`${id}: ${same}/${cases.length} placements identical to relocate.place (bytes, entry symbols, end of the variables)`);
  ok = ok && same === cases.length;
}
process.exit(ok ? 0 : 1);
