# 07 · Snippets : code prêt à l'emploi

Tout ce qui est marqué **✅ testé** a été exécuté le 25/09/2026 :
- sur les octets réels des tables de ms-multi-output ;
- contre le code C d'`elektron-firmware-tool`, via un harnais compilé : checksum de contenu identique, 50 paquets sur 50 valides, conteneur restitué à l'identique.

Ce qui ne peut être testé qu'avec l'image firmware est marqué **`[À TESTER]`**.

---

## 1. Stubs ASM relogés pour le Model:Cycles OS 1.13

Syntaxe GAS m68k (registres `%`) identique aux sources de l'auteur : ces stubs sont ceux de [ms-multi-output](https://github.com/scottmetoyer/ms-multi-output), Copyright (c) 2026 Scott Metoyer, licence MIT (texte : `tweaks/model-cycles_OS1.13/LICENSE-ms-multi-output`). Le code est le même que sur le Samples, avec les constantes du Cycles.
Chaque listing a été vérifié instruction par instruction contre les octets `write` de `cycles6.json`.
Branches en **`.w` explicite** pour retrouver les mêmes octets : GAS pourrait sinon choisir la forme `.b`.
Assemblage : voir §7.

**Pour reproduire le build de référence, appliquer la table JSON et non ces sources.** Ces sources servent de base aux nouvelles variantes.

```asm
| ---------------------------------------------------------------- prime6_mc.s
| Placé à 0x4019b136 (blob CDC n°1). Appelé par 0x400027e8: jmp 0x4019b136 + 8 x nop (bloc de 22 o).
| Entrée a2 = dTD à amorcer. Reprise 0x400027fe.
| Octets : 4e71 203c00900080 25400004 24bcdead0001 7212 e789 25410020 4ef9400027fe
        .text
        .global prime6_helper
        .equ RETURN, 0x400027fe
prime6_helper:
        nop                             | aligne la suite sur 4 o
        move.l  #0x00900080,%d0         | token : 144 o << 16 | Active(0x80)
        move.l  %d0,%a2@(4)             | dTD.token
        move.l  #0xdead0001,%a2@        | dTD.next = terminateur (bit T)
        moveq   #18,%d1
        lsl.l   #3,%d1                  | 144 (moveq ne code pas 144)
        move.l  %d1,%a2@(32)            | longueur privée du driver (lue par 0x40003f10)
        jmp     RETURN
```

```asm
| ---------------------------------------------------------------- token6_mc.s
| Placé à 0x4019b182 (blob CDC n°2). Appelé par 0x40002a42: jmp + 2 x nop (bloc de 10 o).
| Entrée d0 = POINTEUR dTD, d4 = trames. Sortie a0 = dTD, d4 = (trames*24)<<16, d0 = trames*24.
| Octets : 4e71 2040 2004 2200 e988 e789 d081 2800 4844 4244 4ef940002a4c
        .text
        .global token6_helper
        .equ RETURN, 0x40002a4c
token6_helper:
        nop
        movea.l %d0,%a0                 | a0 = dTD AVANT de réutiliser d0
        move.l  %d4,%d0                 | trames
        move.l  %d0,%d1
        lsl.l   #4,%d0
        lsl.l   #3,%d1
        add.l   %d1,%d0                 | trames*24
        move.l  %d0,%d4
        swap    %d4
        clr.w   %d4                     | (trames*24) << 16
        jmp     RETURN
```

```asm
| ---------------------------------------------------------------- tracks6_mc.s
| Placé à 0x4019b1e0 (blob MIDI n°1). Appelé par 0x40002a06: jmp + 9 x nop (boucle de copie, 24 o).
| Entrée d0 = mots longs (= trames*2), d1 = destination, d3 = offset de trame. Tous registres préservés.
| Octets : 4fefffd4 48d707ff 2241 781f 2c03 cc84 e288 6f000028 247c80001858 45f26c00 7e06 2412 02c2
|          22c2 45ea0080 5387 6600fff2 5286 cc84 5380 6e00ffdc 4cd707ff 4fef002c 4ef940002a26
        .text
        .global tracks6_stub
        .equ TRACK_BASE,   0x80001858   | Cycles (Samples : 0x80001b48)
        .equ TRACK_STRIDE, 0x80         | 32 trames x 4 o
        .equ NTRACKS,      6
        .equ REJOIN,       0x40002a26   | sortie de la boucle d'origine
tracks6_stub:
        lea     %sp@(-44),%sp           | ColdFire : pas de movem -(sp)
        movem.l %d0-%d7/%a0-%a2,%sp@
        movea.l %d1,%a1                 | destination (case du ring)
        moveq   #31,%d4                 | masque mod-32 : PORTEUR, ne pas retirer
        move.l  %d3,%d6
        and.l   %d4,%d6                 | index de trame dans le bloc de 32
        lsr.l   #1,%d0                  | mots longs -> trames
        ble.w   .Ldone
.Lframe:
        movea.l #TRACK_BASE,%a2
        lea     %a2@(0,%d6:l:4),%a2     | &piste0[trame]
        moveq   #NTRACKS,%d7
.Ltrack:
        move.l  %a2@,%d2
        .short  0x02c2                  | byterev %d2 (BE -> LE ; ISA_A+/C, absent de -mcpu=5407)
        move.l  %d2,%a1@+
        lea     %a2@(TRACK_STRIDE),%a2  | bloc de la piste suivante
        subq.l  #1,%d7
        bne.w   .Ltrack
        addq.l  #1,%d6
        and.l   %d4,%d6
        subq.l  #1,%d0
        bgt.w   .Lframe
.Ldone:
        movem.l %sp@,%d0-%d7/%a0-%a2
        lea     %sp@(44),%sp
        jmp     REJOIN
| Le mix stéréo d'origine est à 80(sp) APRÈS le prologue (36(sp)+44), plus l'offset d5 (cf. 04 §6).
```

```asm
| ---------------------------------------------------------------- dstoff6_mc.s
| Placé à 0x4019b244 (blob MIDI n°2). Appelé par 0x400029e4: jmp + 2 x nop (bloc de 10 o).
| Entrée d0 = trames déjà dans la case. Sortie d1 = [SLOT_BASE] + trames*24 (d0 mort, rechargé en 0x400029ee).
| Octets : 2200 e988 e789 d081 2239404a05e8 d280 4ef9400029ee
        .text
        .global dstoff6_helper
        .equ SLOT_BASE, 0x404a05e8      | Cycles (Samples : 0x404af45c)
        .equ RETURN,    0x400029ee
dstoff6_helper:
        move.l  %d0,%d1
        lsl.l   #4,%d0
        lsl.l   #3,%d1
        add.l   %d1,%d0                 | trames*24
        move.l  SLOT_BASE,%d1           | base de la case courante
        add.l   %d0,%d1
        jmp     RETURN
```

## 2. `mcfw.py` : helpers MAIN OS (testé)

```python
"""mcfw.py -- helpers pour le MAIN OS (section 3) du Model:Cycles.  Python 3.9+, stdlib seule
(capstone optionnel pour dis()).  Convention : VA = offset fichier + 0x40000400."""
import hashlib, json, pathlib, struct

BASE = 0x40000400

def va2off(va): return va - BASE
def off2va(off): return off + BASE
def sha256(b): return hashlib.sha256(b).hexdigest()
def be32(b, o): return struct.unpack_from(">I", b, o)[0]

# ---------------------------------------------------------------- table de patchs
def apply_table(img: bytearray, table: dict, *, check_stock=True) -> int:
    """Applique une table au format ms-multi-output ({off|va, expect, write}).
    Refuse (ValueError) si un octet 'expect' ne correspond pas."""
    if check_stock and "section3_sha256_stock" in table:
        if sha256(bytes(img)) != table["section3_sha256_stock"]:
            raise ValueError("section 3 != image d'origine attendue")
    for p in table["patches"]:
        off = p["off"] if "off" in p else va2off(int(p["va"], 16))
        exp, new = bytes.fromhex(p["expect"]), bytes.fromhex(p["write"])
        cur = bytes(img[off:off + len(exp)])
        if cur != exp:
            raise ValueError(f"{p.get('va', hex(off2va(off)))}: attendu {exp.hex()} trouvé {cur.hex()}")
        img[off:off + len(new)] = new
    return len(table["patches"])

def verify_table(img: bytes, table: dict) -> bool:
    """Rapport PRESENT / STOCK / UNKNOWN pour chaque run (à la octa-bt-pt)."""
    ok = True
    for p in table["patches"]:
        off = p["off"] if "off" in p else va2off(int(p["va"], 16))
        exp, new = bytes.fromhex(p["expect"]), bytes.fromhex(p["write"])
        cur = img[off:off + len(new)]
        st = "PRESENT" if cur == new else "STOCK" if cur == exp else f"UNKNOWN({cur.hex()})"
        ok &= st == "PRESENT"
        print(f"  [{st:>9}] {p.get('va', hex(off2va(off)))}  {exp.hex()} -> {new.hex()}")
    return ok

# ---------------------------------------------------------------- désassemblage
_CF = {0x02C0: "byterev", 0x00C0: "bitrev", 0x04C0: "ff1"}   # ISA_A+/C : Dn dans les 3 bits bas

def dis(code: bytes, va: int):
    """Liste (va, hex, texte). capstone M68K_040 + repli pour les opcodes ColdFire inconnus."""
    from capstone import Cs, CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_040
    md, out, i = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_040), [], 0
    while i + 1 < len(code):
        ins = next(md.disasm(code[i:], va + i, count=1), None)
        if ins is None:
            w = int.from_bytes(code[i:i + 2], "big")
            name = _CF.get(w & 0xFFF8)
            out.append((va + i, code[i:i + 2].hex(), f"{name} %d{w & 7}" if name else f".short 0x{w:04x}"))
            i += 2
            continue
        out.append((ins.address, ins.bytes.hex(), f"{ins.mnemonic} {ins.op_str}"))
        i += ins.size
    return out

# ---------------------------------------------------------------- références absolues
def xrefs(img: bytes, lo: int, hi: int = None):
    """Toutes les constantes BE32 (offsets pairs) dans [lo, hi) : pointeurs potentiels.
    Retourne (va_de_la_constante, valeur, 2 octets d'opcode précédents)."""
    hi = hi or lo + 1
    res = []
    for o in range(2, len(img) - 3, 2):
        v = be32(img, o)
        if lo <= v < hi:
            res.append((off2va(o), v, img[o - 2:o].hex()))
    return res

# ---------------------------------------------------------------- descripteurs USB
_DT = {1: "DEVICE", 2: "CONFIG", 4: "INTERFACE", 5: "ENDPOINT", 0x0B: "IAD",
       0x24: "CS_INTERFACE", 0x25: "CS_ENDPOINT"}

def walk_descriptors(buf: bytes, va: int = 0):
    """Découpe une suite de descripteurs USB (bLength, bDescriptorType, ...)."""
    o = 0
    while o + 2 <= len(buf):
        n, t = buf[o], buf[o + 1]
        if n < 2 or o + n > len(buf):
            print(f"  {va + o:08x}: arrêt (bLength={n})"); break
        d = buf[o:o + n]
        extra = ""
        if t == 4: extra = f" if#{d[2]} alt{d[3]} nEP={d[4]} class={d[5]:02x}/{d[6]:02x}/{d[7]:02x}"
        if t == 5: extra = f" EP=0x{d[2]:02x} attr=0x{d[3]:02x} wMaxPacketSize={d[4] | d[5] << 8}"
        if t == 2: extra = f" wTotalLength={d[2] | d[3] << 8} nIf={d[4]}"
        print(f"  {va + o:08x}: {_DT.get(t, hex(t)):<12} {d.hex(' ')}{extra}")
        o += n

def usb_mode_table(img: bytes, first=0x4013e544, n=4, stride=0x28, len_off=4):
    """Entrées (pointeur BE32, longueur BE32) de la table des modes USB (Cycles 1.13)."""
    for k in range(n):
        o = va2off(first + k * stride)
        ptr, ln = be32(img, o), be32(img, o + len_off)
        print(f"entrée {k} @0x{first + k * stride:08x}: ptr=0x{ptr:08x} len={ln}")
        walk_descriptors(img[va2off(ptr):va2off(ptr) + ln], ptr)
```

## 3. `syxcodec.py` : transport SysEx et checksums (✅ testé contre le C)

```python
"""syxcodec.py -- relecture Python du transport SysEx + checksums Elektron (ELE3).
Réimplémentation indépendante d'après elektron-firmware-tool (MIT), pour contrôles croisés."""
import hashlib, struct

def content_checksum(container: bytes) -> int:
    """preamble[4:8] : somme des mots BE32 XOR leur index (1-based), mots complets seulement."""
    acc = 0
    for k in range(len(container) // 4):
        acc = (acc + ((k + 1) ^ struct.unpack_from(">I", container, 4 * k)[0])) & 0xFFFFFFFF
    return acc

def packet_checksum(body: bytes, base: int) -> int:
    """Octet 125 d'un paquet de 126 o (corps entre F0 et F7). base = info[0] du marqueur."""
    return (base + sum(body[6 + i] ^ (base + i) for i in range(119))) & 0x7F

def decode_8in7(p: bytes) -> bytes:
    out = bytearray()
    for k in range(0, len(p), 8):
        ms, grp = p[k], p[k + 1:k + 8]
        out += bytes(b | (0x80 if (ms >> (6 - n)) & 1 else 0) for n, b in enumerate(grp))
    return bytes(out)

def syx_decode(raw: bytes):
    """-> (device_id, flux décodé = preamble 8 o + conteneur, nb paquets, nb checksums faux)."""
    msgs, i = [], 0
    while (s := raw.find(b"\xf0", i)) >= 0:
        e = raw.index(b"\xf7", s); msgs.append(raw[s + 1:e]); i = e + 1
    base = next(m[7] for m in msgs if m[5] == 0x7F)          # marqueur de début
    dev, out, bad, n = msgs[0][3], bytearray(), 0, 0
    for m in msgs:
        if m[5] == 0x7E and len(m) == 126:
            out += decode_8in7(m[9:125]); n += 1
            bad += packet_checksum(m, base) != m[125]
    return dev, bytes(out), n, bad

def derive_key(s: bytes, const32: bytes) -> bytes:
    """Clé HMAC ELE3 : SHA256(s) ^ SHA256(s inversée) ^ C (s et C lus dans le firmware, après l'ancre)."""
    h, hr = hashlib.sha256(s).digest(), hashlib.sha256(s[::-1]).digest()
    return bytes(a ^ b ^ c for a, b, c in zip(h, hr, const32))

KEY_ANCHOR = bytes.fromhex("bef9a3f7c67178f2")   # = K[62], K[63] de SHA-256
```
`syx_decode` sert à inspecter un `.syx` produit (device id, checksums) sans passer par l'outil C.
Pour reconstruire une image, **utiliser `elektron-firmware-tool`**.

## 4. Dumper la table des modes USB et les descripteurs `[À TESTER]`

```python
import mcfw, pathlib
img = pathlib.Path("build/section_3_MAIN_OS.bin").read_bytes()     # section 3 d'ORIGINE
mcfw.usb_mode_table(img)                                          # 4 entrées : MIDI, MIDI, CDC, CDC
mcfw.walk_descriptors(img[mcfw.va2off(0x4019b2b6):][:328], 0x4019b2b6)   # config audio+MIDI HS
# D'autres entrées pointent-elles déjà sur 0x4019b2b6 ? (entrées non patchées de la même table)
print([hex(v) for v, *_ in mcfw.xrefs(img, 0x4019b100, 0x4019b400)])
```
`len_off=4` suppose une longueur sur 32 bits juste après le pointeur. Le patch n'écrit que les 16 bits bas à `+6`, donc c'est cohérent, mais à confirmer.

## 5. Trouver le mixeur (pour le pan, les FX et le mode 8 canaux) `[À TESTER]`

```python
import mcfw, pathlib
img = pathlib.Path("build/section_3_MAIN_OS.bin").read_bytes()
TB = 0x80001858
for va, v, op in mcfw.xrefs(img, TB, TB + 6 * 0x80):
    print(f"0x{va:08x}: 0x{v:08x}  opcode-2={op}")    # 247c = movea.l #imm,a2 ; 41f9/43f9/45f9 = lea abs.l
# puis désassembler autour de chaque hit :
for a, h, s in mcfw.dis(img[mcfw.va2off(va) - 64: mcfw.va2off(va) + 256], va - 64): print(f"{a:08x} {h:<14} {s}")
```
À noter : le stub tracks6 patché référence lui aussi `0x80001858`. Lancer la recherche sur l'image **d'origine**.

## 6. Vérifier une capture multicanal (numpy)

```python
import numpy as np

def read_wav_i32(path):
    raw, i, fmt, data = open(path, "rb").read(), 12, None, None
    while i + 8 <= len(raw):
        cid, sz = raw[i:i + 4], int.from_bytes(raw[i + 4:i + 8], "little")
        if cid == b"fmt ": fmt = raw[i + 8:i + 8 + sz]
        if cid == b"data": data = raw[i + 8:i + 8 + sz]
        i += 8 + sz + (sz & 1)
    ch, rate, bits = (int.from_bytes(fmt[a:b], "little") for a, b in ((2, 4), (4, 8), (14, 16)))
    assert bits == 32, "capturer en pcm_s32le (entier 32 bits), pas en float"
    x = np.frombuffer(data, "<i4")
    return x[: len(x) // ch * ch].reshape(-1, ch), rate

def report(path):
    x, rate = read_wav_i32(path)
    f = x.astype(np.float64) / 2**31
    print("RMS dBFS :", np.round(20 * np.log10(np.sqrt((f**2).mean(0)) + 1e-12), 1))
    print("corrélation entre canaux :\n", np.round(np.corrcoef(f.T), 2))  # NaN si canal constant (muté)
    for lag in (24, 48):          # capacité du ring : profondeur 4 ou 8 x 6 trames
        loud = (np.abs(x[lag:]) > 2**24) & (np.abs(x[:-lag]) > 2**24)
        dup = ((x[lag:] == x[:-lag]) & loud).sum(0) / np.maximum(loud.sum(0), 1)
        print(f"doublons exacts au lag {lag} (%) :", np.round(100 * dup, 3))
```
Test rapide seulement. L'outil de référence reste `ms-multi-output/tools/analyse_dupes.py` (lags 1..128, seuil relatif au pic, cadence des rembobinages).
⚠️ Un signal **périodique pur** (sinus de test) donne ~0,4 à 1,3 % de coïncidences exactes sans aucun défaut (vérifié sur un WAV synthétique).
Tester sur du matériel musical et comparer à une capture de l'OS d'origine.

## 7. Commandes shell

```sh
# --- outil de conteneur (commit figé) -----------------------------------------
git clone https://github.com/mischa85/elektron-firmware-tool vendor/elektron-firmware-tool
git -C vendor/elektron-firmware-tool checkout a5bce9a && make -C vendor/elektron-firmware-tool
EFT=vendor/elektron-firmware-tool/elektron-firmware-tool
$EFT -i model-cycles_OS1.13.syx -v                         # sections, version, verdict, chaîne de clé
$EFT -i model-cycles_OS1.13.syx -d 3 -o build/             # build/section_3_MAIN_OS.bin
shasum -a 256 build/section_3_MAIN_OS.bin                  # attendu cc99d4f0…ee98
$EFT -i model-cycles_OS1.13.syx -c 3 build/mainos_patched.bin -o out/mc-test.syx
$EFT -i out/mc-test.syx -d 3 -o build/verify/ && cmp build/mainos_patched.bin build/verify/section_3_MAIN_OS.bin

# --- binutils ColdFire (Homebrew) ------------------------------------------------
brew install m68k-elf-binutils
m68k-elf-as -mcpu=5407 -o tracks6_mc.o tracks6_mc.s        # [À TESTER] -mcpu=54418 pour byterev natif
m68k-elf-ld -Ttext=0x4019b1e0 -o tracks6_mc.elf tracks6_mc.o
m68k-elf-objcopy -O binary tracks6_mc.elf tracks6_mc.bin
m68k-elf-nm tracks6_mc.elf                                 # adresses des symboles -> cibles des détours (R3)
xxd -p tracks6_mc.bin | tr -d '\n'; echo                   # comparer à la colonne "write" de cycles6.json
m68k-elf-objdump -D -b binary -m m68k:5407 --adjust-vma=0x40000400 build/section_3_MAIN_OS.bin | less   # [À TESTER]

# --- radare2 / Ghidra headless -------------------------------------------------
r2 -a m68k -b 32 -e cfg.bigendian=true -m 0x40000400 build/section_3_MAIN_OS.bin
"$GHIDRA_HOME/support/analyzeHeadless" ~/ghidra-proj ModelCycles113 \
    -import build/section_3_MAIN_OS.bin -loader BinaryLoader \
    -loader-baseAddr 0x40000400 -processor 68000:BE:32:Coldfire      # [À TESTER]
```

## 8. hookcheck : aucune cible à l'intérieur d'un trou

Règle R4 de la [note 05](05-methode-patch.md) : un crochet écrase N octets en supposant qu'on n'y entre que par le
premier. Avant de garder un crochet, chercher dans l'image **patchée** tout ce qui viserait l'intérieur du trou (tout
sauf son premier octet) :
- les branchements relatifs `bra`/`bsr`/`bcc` (déplacement sur 8, 16 ou 32 bits) ;
- les `jmp`/`jsr` en adresse absolue (`abs.l`) et relatifs au PC (`d16,pc`) ;
- l'adresse elle-même stockée comme donnée sur 32 bits (tables de sauts, champs de callback).

Sur l'image patchée, les branchements internes au trou sont devenus des `nop` et ne donnent plus de faux positifs. Il
en reste, car une donnée peut ressembler à un branchement : examiner chaque résultat.

Trous de ms-multi-output sur le Cycles (site, octets écrasés) : `(0x400027e8, 22)`, `(0x400029e4, 10)`,
`(0x40002a06, 24)`, `(0x40002a42, 10)`.

L'idée et l'outil d'origine viennent d'octamax ([`tools/hookcheck.py`](https://github.com/mxldyn/octamax)).
*07/10/2026 : le listing Python qui figurait ici suivait de trop près ce fichier, publié sans licence ; il a été
retiré, seule la méthode reste.*
