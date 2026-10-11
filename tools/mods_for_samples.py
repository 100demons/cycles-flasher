#!/usr/bin/env python3
"""OS Cycles avec mods pour un Model:Samples (notes/57, notes/41).

Le firmware est TOUJOURS l'OS du Model:Cycles, avec les mods choisis, quelle que soit la machine (notes/57) : sur un
Model:Samples, le sampling vient de Model-TG, pas de l'OS Samples. Seul l'emballage change avec la machine.

Prend un .syx Model:Cycles avec mods (sortie de build.py, ou « Télécharger le .syx » de l'onglet Mods de la page) et met
son MAIN OS (section 3) dans le conteneur officiel du Model:Samples OS 1.13 : bootstrap, updater et horodatage du
Samples gardés, signé avec la clé HMAC du Samples (tirée de TON fichier officiel du Samples, jamais stockée).

Il applique toujours le correctif de 32 octets de crossflash.py --to samples (notes/41 §3) : l'OS Cycles avec mods vérifie
les mises à jour avec la clé du Samples, donc
  * l'OS Samples officiel repasse par USB (crossflash.py --back-samples, « Model:Samples : retour à son OS ») ;
  * on peut changer de mods plus tard avec ce même script (fichier _cyc-os).

Transport (l'emballage SysEx que l'OS EN SERVICE accepte) :
  --into samples   la machine tourne sous l'OS Samples officiel (Model:Samples d'origine)  -> produit 0x0F, appareil 0x0A
  --into cycles    la machine tourne déjà sous un OS Cycles de la page ou de ce script (clé Samples)
                                                                                         -> produit 0x11, appareil 0x0C
  --into both      les deux fichiers (par défaut)

    python3 tools/build.py -i model-cycles_OS1.13.syx -t model-tg,arp -o mods.syx
    python3 tools/mods_for_samples.py --cycles model-cycles_OS1.13.syx --samples model-samples_OS1.13.syx --mods mods.syx

Puis : la page, onglet Mods, machine « Model:Samples » (ou déposer ce fichier, « envoyé tel quel »), méthode rapide,
YES sur la machine. La page ne l'envoie que si la machine répond comme le produit du fichier.

Contrôles sur la sortie, relue depuis les octets écrits : checksums des paquets, produit et octet appareil, checksum de
contenu, en-tête du conteneur et sections 2/4/5 identiques au Samples officiel, section 3 = le MAIN OS avec mods sauf
les 32 octets de la clé, HMAC valide avec la clé Samples et PAS avec la clé Cycles, la clé que l'OS dérivera = clé
Samples, tailles.

Flasher d'origine : RDS (AIM) (Discord, 10/10/2026) ; intégré à Modded Cycles par DaftMaple. Preuve : tools/emu/test_mods_for_samples.py.
"""
import argparse
import hashlib
import hmac
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from mtlib import aplib, container                 # noqa: E402
from mtlib.syx import unwrap, wrap, BYTES_PER_MSG  # noqa: E402
import crossflash as cf                             # noqa: E402

MAIN_END_LIMIT = 0x40200000      # le bootstrap copie la section 3 compressée ici : le MAIN OS doit finir avant
CONTAINER_MAX = 0x1c0000         # conteneur écrit en flash 0x20000 : il doit finir avant 0x1e0000 (notes/41 §8)
TRANSPORT = {"samples": (0x0F, 0x0A), "cycles": (0x11, 0x0C)}


def die(msg):
    raise SystemExit("!! " + msg)


def load_mods(raw, cyc):
    """.syx Model:Cycles avec mods -> (section 3 compressée, MAIN OS, ops aPLib). Seule la section 3 diffère de l'officiel."""
    try:
        stream, info = unwrap(raw)
    except ValueError as e:
        die(f"fichier de mods : {e}")
    if info["product"] != 0x11:
        die(f"fichier de mods : produit 0x{info['product']:02x}, un build Model:Cycles (0x11) est attendu")
    c = container.parse(stream)
    c_stored = cyc[2]
    got = {s["id"]: c["blob"][s["off"]:s["off"] + s["size"]] for s in c["sections"]}
    if set(got) != set(c_stored):
        die("fichier de mods : liste de sections différente de l'OS Cycles officiel")
    for sid in got:
        if sid != 3 and got[sid] != c_stored[sid]:
            die(f"fichier de mods : section {sid} différente de l'OS Cycles officiel (seule la section 3 change)")
    body, dig = c["blob"][:-container.DIGEST_LEN], c["blob"][-container.DIGEST_LEN:]
    if hmac.new(cf.host_key(cyc), body, hashlib.sha256).digest() != dig:
        die("fichier de mods : HMAC invalide avec la clé Cycles (déjà emballé pour le Samples, ou abîmé)")
    main, ops = aplib.depack(got[3])
    return got[3], main, ops


def for_samples(cyc, smp, mods_raw):
    """MAIN OS avec mods, clé de vérification = clé Samples, dans le conteneur Samples officiel.
    Renvoie (conteneur, MAIN OS installé, MAIN OS avec mods, offset des 32 octets)."""
    _, mods_main, ops = load_mods(mods_raw, cyc)
    s_c = smp[1]
    c_key, s_key = cf.host_key(cyc), cf.host_key(smp)
    off, _, new = cf.cycles_key_write(mods_main, c_key, s_key)    # vérifie le code, la chaîne et la clé d'origine
    main = bytearray(mods_main)
    main[off:off + 32] = new
    main = bytes(main)
    dirty = bytearray(len(main))
    dirty[off:off + 32] = b"\1" * 32
    s3 = aplib.repack(main, ops, dirty)
    if aplib.depack(s3)[0] != main:
        die("recompression du MAIN OS : relecture différente")
    if cf.MAIN_BASE + len(main) > MAIN_END_LIMIT:
        die(f"MAIN OS trop grand : finit en 0x{cf.MAIN_BASE + len(main):08x} (limite 0x{MAIN_END_LIMIT:08x})")
    blob = container.rebuild(s_c, {3: s3}, s_key)
    if len(blob) > CONTAINER_MAX:
        die(f"conteneur trop grand : {len(blob)} o (limite {CONTAINER_MAX} o)")
    return blob, main, mods_main, off


def pack(blob, into, cyc, smp):
    """Le conteneur dans le transport SysEx de l'OS en service (« samples » ou « cycles »)."""
    product, _ = TRANSPORT[into]
    start_seq = (smp if into == "samples" else cyc)[0]["start_seq"]
    return wrap(container.build_stream(blob, BYTES_PER_MSG), product, start_seq)


def verify(out, into, cyc, smp, main, mods_main, off):
    """Relit le fichier produit ; s'arrête au premier écart."""
    s_c, s_stored = smp[1], smp[2]
    product, dev = TRANSPORT[into]
    if out[4] != product or out[6:8] != b"\x7f\x01" or out[8] != dev:
        die("relecture : marqueur de début (produit / octet appareil)")
    stream, _ = unwrap(out)                          # checksum de chaque paquet, base = octet appareil
    c = container.parse(stream)
    blob = c["blob"]
    if int.from_bytes(stream[4:8], "big") != container.content_checksum(blob):
        die("relecture : checksum de contenu")
    if blob[:0x20] != s_c["blob"][:0x20]:
        die("relecture : en-tête du conteneur différent du Samples officiel")
    got = {s["id"]: blob[s["off"]:s["off"] + s["size"]] for s in c["sections"]}
    if set(got) != set(s_stored) or any(got[i] != s_stored[i] for i in got if i != 3):
        die("relecture : sections 2/4/5 différentes du Samples officiel")
    m = aplib.depack(got[3])[0]
    if m != main:
        die("relecture : la section 3 ne redonne pas le MAIN OS attendu")
    if len(m) != len(mods_main) or any(a != b for i, (a, b) in enumerate(zip(m, mods_main)) if not off <= i < off + 32):
        die("relecture : le MAIN OS diffère du build avec mods hors des 32 octets de la clé")
    body, dig = blob[:-container.DIGEST_LEN], blob[-container.DIGEST_LEN:]
    if hmac.new(cf.host_key(smp), body, hashlib.sha256).digest() != dig:
        die("relecture : HMAC invalide avec la clé Samples")
    if hmac.new(cf.host_key(cyc), body, hashlib.sha256).digest() == dig:
        die("relecture : HMAC valide aussi avec la clé Cycles : incohérent")
    o = cf.CYC_KEY_STR_VA - cf.MAIN_BASE
    text = m[o:o + 11]
    h, hr = hashlib.sha256(text).digest(), hashlib.sha256(text[::-1]).digest()
    if bytes(a ^ b ^ x for a, b, x in zip(h, hr, m[off:off + 32])) != cf.host_key(smp):
        die("relecture : l'OS installé ne vérifierait pas les mises à jour avec la clé Samples")
    return len(blob)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True, help="model-cycles_OS1.13.syx officiel")
    ap.add_argument("--samples", required=True, help="model-samples_OS1.13.syx officiel")
    ap.add_argument("--mods", required=True, help=".syx Model:Cycles avec mods (build.py ou téléchargé depuis la page)")
    ap.add_argument("--into", choices=("samples", "cycles", "both"), default="both",
                    help="OS qui tourne sur le Model:Samples (décide du transport SysEx)")
    ap.add_argument("-o", "--outdir", help="dossier de sortie (par défaut : à côté de --mods)")
    a = ap.parse_args()

    cyc, smp = cf.load(a.cycles, "cycles"), cf.load(a.samples, "samples")
    blob, main_os, mods_main, off = for_samples(cyc, smp, pathlib.Path(a.mods).read_bytes())
    outdir = pathlib.Path(a.outdir) if a.outdir else pathlib.Path(a.mods).resolve().parent
    stem = pathlib.Path(a.mods).stem + "_for-samples"
    print(f"MAIN OS avec mods {cf.sha(mods_main)[:16]}..., {len(mods_main)} o, fin 0x{cf.MAIN_BASE + len(mods_main):08x}")
    print(f"MAIN OS installé  {cf.sha(main_os)[:16]}... (clé de vérification = clé Samples, 32 octets)")
    for into in (("samples", "cycles") if a.into == "both" else (a.into,)):
        out = pack(blob, into, cyc, smp)
        size = verify(out, into, cyc, smp, main_os, mods_main, off)
        name = outdir / f"{stem}_{'smp-os' if into == 'samples' else 'cyc-os'}.syx"
        name.write_bytes(out)
        when = ("la machine tourne sous l'OS Samples officiel (répond Model:Samples)" if into == "samples"
                else "la machine tourne déjà sous un OS Cycles de la page ou de ce script (répond Model:Cycles)")
        print(f"écrit : {name} ({len(out)} o, conteneur {size} o, SHA-256 {cf.sha(out)[:16]}...)")
        print(f"   pour : {when}")
    print("relu et vérifié : paquets, transport, sections 2/4/5 du Samples, MAIN OS, HMAC Samples (Cycles refusé)")


if __name__ == "__main__":
    main()
