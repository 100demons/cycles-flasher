#!/usr/bin/env python3
"""Places a package's committed object at its address in the payload, without the toolchain (notes/60 §3, B2a).

A package's object is one relocatable m68k ELF file (ELF32, big endian, type REL; `m68k-elf-ld -r` of the package's
compiled sources, written by its generator and committed next to its manifest). It is compiled with
-ffunction-sections -fdata-sections, so every function and every table is a section of its own, and with -fno-pic,
so the only relocation type in it is R_68K_32: an absolute 32-bit address, symbol + addend, to write where the code
or a table refers to another section. This module does what the linker script of the B1 path (compose.LINK) did:

  1. reads the sections, the symbol table and the .rela.* tables;
  2. keeps only what the roots reach (--gc-sections): the sections holding the update and render entries and the
     "keep" symbols of the manifest, then everything their relocations point to;
  3. places the kept sections in the linker script's order: the update entry's section, the render entry's
     section, the other .text* in file order, then .rodata*, then .data*, each at its own alignment, from code_at;
     the .bss* from bss_at (not emitted: the boot hook zeroes the payload);
  4. resolves every symbol: a section symbol to its section's address, a defined symbol to its section's address
     plus its value, an undefined symbol to the value the composer gives for that patch point (the machine index,
     the first descriptor: what `ld --defsym` would do), anything else is an error naming the symbol;
  5. writes symbol + addend, 4 bytes big endian, at each relocation's place.

place() returns what compose.compile_package returns, (bytes from code_at to the end of the data, symbols, end of
the variables), so the composer uses one or the other. With the same object the two give the same bytes: that is
what compose.py --compare-ld checks, and the proof of this module.

    python3 tools/relocate.py tools/machines/refmachine/refmachine.o      # lists sections, symbols, relocations
"""
import struct
import sys

R_68K_32 = 1
SHT_PROGBITS, SHT_SYMTAB, SHT_STRTAB, SHT_RELA, SHT_NOBITS = 1, 2, 3, 4, 8
SHF_ALLOC = 2
SHN_UNDEF, SHN_ABS, SHN_COMMON = 0, 0xfff1, 0xfff2
STT_SECTION = 3
EM_68K = 4
IGNORED = (".comment", ".note", ".eh_frame", ".rela", ".symtab", ".strtab", ".shstrtab", ".debug", ".m68k")


class ObjectError(SystemExit):
    pass


class Elf:
    """A relocatable m68k ELF32 big-endian object: sections, symbols, relocations."""

    def __init__(self, data, name="object"):
        self.data, self.name = data, name
        if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 2:
            raise ObjectError(f"!! {name}: not an ELF32 big-endian file")
        (e_type, e_machine, _v, _entry, _phoff, shoff, _flags, _ehsize, _phentsize, _phnum, shentsize, shnum,
         shstrndx) = struct.unpack_from(">HHIIIIIHHHHHH", data, 16)
        if e_type != 1 or e_machine != EM_68K:
            raise ObjectError(f"!! {name}: not a relocatable m68k object (type {e_type}, machine {e_machine})")
        if shentsize != 40:
            raise ObjectError(f"!! {name}: section header size {shentsize}")
        raw = [struct.unpack_from(">10I", data, shoff + 40 * i) for i in range(shnum)]
        shstr = raw[shstrndx]
        names = [self._str(shstr[4], shstr[5], r[0]) for r in raw]
        self.sections = [dict(index=i, name=names[i], type=r[1], flags=r[2], off=r[4], size=r[5], link=r[6],
                              info=r[7], align=max(r[8], 1)) for i, r in enumerate(raw)]
        sym = next((s for s in self.sections if s["type"] == SHT_SYMTAB), None)
        if not sym:
            raise ObjectError(f"!! {name}: no symbol table")
        strtab = self.sections[sym["link"]]
        self.symbols = []
        for i in range(sym["size"] // 16):
            st_name, value, size, info, _other, shndx = struct.unpack_from(">IIIBBH", data, sym["off"] + 16 * i)
            self.symbols.append(dict(index=i, name=self._str(strtab["off"], strtab["size"], st_name), value=value,
                                     size=size, type=info & 0xf, bind=info >> 4, shndx=shndx))
        self.relocs = {}                                 # target section index -> [(offset, symbol index, addend)]
        for s in self.sections:
            if s["type"] != SHT_RELA:
                continue
            if s["link"] != sym["index"]:
                raise ObjectError(f"!! {name}: {s['name']} uses another symbol table")
            rs = []
            for i in range(s["size"] // 12):
                r_offset, r_info, r_addend = struct.unpack_from(">IIi", data, s["off"] + 12 * i)
                if r_info & 0xff != R_68K_32:
                    raise ObjectError(f"!! {name}: relocation type {r_info & 0xff} in {s['name']} at {r_offset:#x}: "
                                      "only R_68K_32 is supported (absolute 32-bit; compile with -fno-pic)")
                rs.append((r_offset, r_info >> 8, r_addend))
            self.relocs[s["info"]] = rs
        self.by_name = {}
        for s_ in self.symbols:
            if s_["name"] and s_["type"] != STT_SECTION:
                self.by_name.setdefault(s_["name"], s_)

    def _str(self, off, size, i):
        end = self.data.index(b"\0", off + i, off + size)
        return self.data[off + i:end].decode("ascii", "replace")

    def comment(self):
        """The compiler's signature (.comment section), e.g. 'GCC: (GNU) 16.2.0'."""
        s = next((s for s in self.sections if s["name"] == ".comment"), None)
        if not s:
            return ""
        return " ".join(p.decode("ascii", "replace") for p in self.data[s["off"]:s["off"] + s["size"]].split(b"\0") if p)

    def alloc_sections(self):
        """The sections that take room in memory, by kind: 'text', 'rodata', 'data', 'bss'."""
        out = []
        for s in self.sections:
            if not s["flags"] & SHF_ALLOC or s["size"] == 0 and s["name"] in (".text", ".data", ".bss"):
                continue
            kind = next((k for k in ("text", "rodata", "data", "bss") if s["name"] == "." + k
                         or s["name"].startswith("." + k + ".")), None)
            if kind is None:
                raise ObjectError(f"!! {self.name}: unexpected section {s['name']} (size {s['size']})")
            if kind == "bss" and s["type"] != SHT_NOBITS or kind != "bss" and s["type"] != SHT_PROGBITS:
                raise ObjectError(f"!! {self.name}: section {s['name']} has type {s['type']}")
            out.append((kind, s))
        return out


def align(x, a):
    return (x + a - 1) & ~(a - 1)


def place(obj, update, render, keep, code_at, bss_at, code_end, values, name="object"):
    """Relocates the object (bytes) at code_at (code, tables, data) and bss_at (variables). update and render are
    the entry symbols, keep the other symbols the composer's writes need (hooks, view methods); values maps an
    undefined symbol (a patch point) to its value. The code must end before code_end. Returns (blob, symbols,
    end of the variables), like compose.compile_package."""
    elf = Elf(obj, name)
    roots = []
    for s_ in (update, render, *keep):
        sym = elf.by_name.get(s_)
        if not sym or sym["shndx"] in (SHN_UNDEF, SHN_ABS, SHN_COMMON):
            raise ObjectError(f"!! {name}: symbol {s_} is not defined in the object")
        roots.append(sym["shndx"])
    # --- garbage collection: what the roots reach through their relocations
    kept, todo = set(), list(roots)
    while todo:
        i = todo.pop()
        if i in kept:
            continue
        kept.add(i)
        for _off, si, _add in elf.relocs.get(i, ()):
            sym = elf.symbols[si]
            if sym["shndx"] not in (SHN_UNDEF, SHN_ABS, SHN_COMMON):
                todo.append(sym["shndx"])
    if any(s["shndx"] == SHN_COMMON for s in elf.symbols):
        raise ObjectError(f"!! {name}: COMMON symbols (compile with -fno-common)")
    # --- placement, in the linker script's order
    secs = [(k, s) for k, s in elf.alloc_sections() if s["index"] in kept]
    first = [s for s in secs if s[1]["index"] == elf.by_name[update]["shndx"]]
    second = [s for s in secs if s[1]["index"] == elf.by_name[render]["shndx"] and s not in first]
    rest_text = [s for s in secs if s[0] == "text" and s not in first and s not in second]
    groups = [("text", first + second + rest_text)] + [(k, [s for s in secs if s[0] == k]) for k in ("rodata", "data")]
    addr, cur = {}, code_at
    for _kind, group in groups:
        if not group:
            continue
        cur = align(cur, max(s["align"] for _k, s in group))
        for _k, s in group:
            cur = align(cur, s["align"])
            addr[s["index"]] = cur
            cur += s["size"]
    code_stop = cur
    if code_stop > code_end:
        raise ObjectError(f"!! {name}: code and tables end at {code_stop:#x}, past {code_end:#x}")
    bss = [s for k, s in secs if k == "bss"]
    cur = align(bss_at, max([s["align"] for s in bss] + [1]))
    for s in bss:
        cur = align(cur, s["align"])
        addr[s["index"]] = cur
        cur += s["size"]
    bss_end = align(cur, 4)
    # --- symbols
    symbols = {}
    for s_ in elf.symbols:
        if s_["type"] == STT_SECTION or not s_["name"]:
            continue
        if s_["shndx"] in addr:
            symbols[s_["name"]] = addr[s_["shndx"]] + s_["value"]
        elif s_["shndx"] == SHN_ABS:
            symbols[s_["name"]] = s_["value"]

    def value_of(si):
        sym = elf.symbols[si]
        if sym["shndx"] == SHN_UNDEF:
            if sym["name"] in values:
                return values[sym["name"]]
            raise ObjectError(f"!! {name}: undefined symbol {sym['name']}: not one of this build's patch points "
                              f"({', '.join(sorted(values)) or 'none'})")
        if sym["shndx"] == SHN_ABS:
            return sym["value"]
        if sym["shndx"] not in addr:
            raise ObjectError(f"!! {name}: symbol {sym['name'] or si} in a section that was not placed")
        return addr[sym["shndx"]] + sym["value"]
    # --- the blob, relocated
    blob = bytearray(code_stop - code_at)
    for k, s in secs:
        if k == "bss":
            continue
        lo = addr[s["index"]] - code_at
        blob[lo:lo + s["size"]] = elf.data[s["off"]:s["off"] + s["size"]]
    for k, s in secs:
        for off, si, add in elf.relocs.get(s["index"], ()):
            if k == "bss":
                raise ObjectError(f"!! {name}: relocation in {s['name']}")
            if off + 4 > s["size"]:
                raise ObjectError(f"!! {name}: relocation at {off:#x} past the end of {s['name']}")
            struct.pack_into(">I", blob, addr[s["index"]] - code_at + off, (value_of(si) + add) & 0xffffffff)
    return bytes(blob), symbols, bss_end


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    import pathlib
    p = pathlib.Path(sys.argv[1])
    elf = Elf(p.read_bytes(), p.name)
    print(f"{p.name}: {len(elf.sections)} sections, {len(elf.symbols)} symbols, "
          f"{sum(len(r) for r in elf.relocs.values())} relocations (all R_68K_32); {elf.comment()}")
    for k, s in elf.alloc_sections():
        print(f"  {k:6s} {s['name']:32s} {s['size']:6d} bytes, align {s['align']}, {len(elf.relocs.get(s['index'], ()))} relocations")
    undef = sorted(s["name"] for s in elf.symbols if s["shndx"] == SHN_UNDEF and s["name"])
    print(f"  undefined: {', '.join(undef) or 'none'}")


if __name__ == "__main__":
    main()
