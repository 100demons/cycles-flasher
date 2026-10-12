#!/usr/bin/env python3
"""Banc d'émulation de Model-TG (notes/31) : la vraie boucle des voix du MAIN OS modifié par Model-TG
(tweaks/model-cycles_OS1.13/30-model-tg.json), comparée au Cycles d'origine.

Ce que le banc fournit, que la machine met en place hors de la boucle des voix :
  - les gains du mixeur : le dispatch de Model-TG ne calcule pas une piste que le mixeur joue à moins de -90 dB
    (voice_quiet lit les gains 0x40a78c08.. que le mix d'origine met à jour à chaque bloc) ;
  - Attack, Filtre et Résonance (paramètres k = 23, 24, 25 de chaque piste) à leurs valeurs par défaut : 0, grand
    ouvert (32 512), 0 ;
  - l'émulation de l'EMAC dans son bloc de code (0x401ab750..), et la mémoire qu'il lit (BSS, minuteur 1).

Vérifications :
  - SNARE, METAL, PERC, TONE et CHORD identiques à l'OS d'origine, échantillon par échantillon (CHORD passe par son
    oscillateur réécrit, chord_osc) ;
  - KICK identique jusqu'à la fin de la rampe de son « click », puis à moins de -90 dB de l'OS d'origine : Model-TG
    arrête volontairement les filtres du click une fois retombés sous le silence (kick_click, docs/INTERNALS.md) ;
  - une note mutée (les gains du mixeur à zéro) puis démutée (notes/35 §3) : sans audio USB multipiste, Model-TG
    cesse de la calculer (inaudible dans le mix) ; avec 6ch-usbup, la piste USB, prise avant le mixeur, reste
    identique à la note jamais mutée : ni coupure nette, ni note figée qui repart au démute.

    python3 tools/emu/test_model_tg.py --cycles model-cycles_OS1.13.syx [--tweak ….json]
"""
import argparse
import json
import pathlib
import struct
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import mcengine as E                # noqa: E402
import test_sdvintage as T          # noqa: E402

TWEAK = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13" / "30-model-tg.json"
BLOB = 0x401ab750                   # bloc de code de Model-TG, exécuté en place
MIX_GAIN = 0x40a78c08               # gain principal de chaque piste (6 x 32 bits), mis à jour par le mix d'origine
NAMES = ["KICK", "SNARE", "METAL", "PERC", "TONE", "CHORD"]
FAIL = []


def check(ok, msg):
    print(("  ok    " if ok else "  ECHEC ") + msg, flush=True)
    if not ok:
        FAIL.append(msg)


def engine(img, end=None, payload=None, payload_code=()):
    """Moteur d'émulation pour une image qui contient Model-TG (ou l'OS d'origine). end : fin de son bloc de code
    (défaut : fin de l'image) ; payload, payload_code : charge utile de la version combinée (mcengine.Engine)."""
    tg = len(img) > E.IMAGE_LEN
    end = end or E.BASE + len(img)
    e = E.Engine(img, extra_code=[(BLOB, end - BLOB)] if tg else (), payload=payload, payload_code=payload_code)
    e.uc.mem_map(0x40800000, 0x01800000)          # BSS de l'OS (Model-TG y lit l'état du séquenceur)
    e.uc.mem_map(0x42400000, 0x00c00000)
    e.uc.mem_map(0x48000000, 0x08000000)          # vue sans cache de la SDRAM (zone d'échantillons)
    e.uc.mem_map(0xfc078000, 0x1000)              # minuteur DMA 1 : mesure par piste de la page System
    for t in range(6):
        e.uc.mem_write(MIX_GAIN + 4 * t, struct.pack(">I", 0x20000000))
        e.uc.mem_write(E.PARAMS + 0xe + t * 0x42 + 46, struct.pack(">hhh", 0, 32512, 0))   # Attack, Filtre, Résonance
    return e


def play(img, blocks, trigs):
    e = engine(img)
    for t in range(6):
        e.set(t, machine=t, note=60, pitch=64, color=64, shape=64, sweep=64, contour=64, punch=0, gate=0, finetune=64,
              decay=60)
    out = np.stack([e.block(trigs.get(b, 0)) for b in range(blocks)])
    return out, e.unmapped


def muted(img, mute_at, unmute_at, blocks=260, track=4):
    """La piste track (TONE, Decay long) jouée au bloc 1 ; ses gains de mixeur à zéro de mute_at à unmute_at,
    comme un mute d'origine (FUNC + piste). Rend la sortie de la piste (ce que prend l'audio USB multipiste)."""
    e = engine(img)
    for t in range(6):
        e.set(t, machine=t, note=60, pitch=64, color=64, shape=64, sweep=64, contour=64, punch=0, gate=0, finetune=64,
              decay=110 if t == track else 60)
    out = []
    for b in range(blocks):
        if b == mute_at:
            e.uc.mem_write(MIX_GAIN + 4 * track, bytes(4))
        if b == unmute_at:
            e.uc.mem_write(MIX_GAIN + 4 * track, struct.pack(">I", 0x20000000))
        out.append(e.block(1 << track if b == 1 else 0)[track])
    return np.stack(out).astype(np.int64), e.unmapped


def mute_test(stock, tw, usb):
    print("note mutée puis démutée (notes/35 §3), TONE")
    img = bytes(build.apply_writes(stock, [tw])[0]) + build.build_payload([tw], stock, None)[0]
    img6 = bytes(build.apply_writes(stock, [usb, tw])[0]) + build.build_payload([usb, tw], stock, None)[0]
    for name, im in (("Model-TG seul", img), ("Model-TG + 6ch-usbup", img6)):
        ref, _ = muted(im, None, None)
        mut, unm = muted(im, 40, 120)
        loud = np.abs(ref[40:120]).max(axis=1)
        cut = [b for b in range(41, 120) if not mut[b].any() and loud[b - 40] > 0]
        same = not np.any(mut != ref)
        if im is img:
            check(cut and not same and loud.min() > 1e6,
                  f"{name} : la note, encore forte (crête {loud.min():.1e} au plus bas), n'est plus calculée dès le bloc "
                  f"{cut[0] if cut else '—'} (sa piste à zéro), puis repart figée au démute (différente de la note "
                  f"jamais mutée) : inaudible dans le mix, mais c'est ce que recevait la piste USB")
        else:
            check(same and not unm, f"{name} : la piste reste identique, échantillon par échantillon, à la note jamais "
                                    f"mutée (260 blocs, mute aux blocs 40 à 120)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True)
    ap.add_argument("--tweak", default=str(TWEAK))
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    tw = json.loads(pathlib.Path(args.tweak).read_text(encoding="utf-8"))
    p, _ = build.apply_writes(stock, [tw])
    pl, _ = build.build_payload([tw], stock, None)
    img = bytes(p) + pl
    trigs = {1: 0x3f, 150: 0x3f}
    ref, _ = play(stock, 300, trigs)
    mod, unm = play(img, 300, trigs)
    print("machines d'origine sous Model-TG")
    for t in range(6):
        r, x = ref[:, t].astype(np.int64), mod[:, t].astype(np.int64)
        diff = np.nonzero(np.any(r != x, axis=1))[0]
        loud = np.abs(r).max()
        if t == 0:
            d = np.abs(r - x).max()
            check(len(diff) and diff[0] > 10 and d * 31622 < loud,       # 31 622 : -90 dB
                  f"KICK : identique jusqu'au bloc {diff[0] if len(diff) else '—'}, puis écart max "
                  f"{20 * np.log10(max(d, 1) / loud):.1f} dB sous la crête (fin du click, kick_click)")
        else:
            check(not len(diff) and loud > 1e8, f"{NAMES[t]:5s} identique à l'OS d'origine (crête {loud:.2e})")
    check(not unm, "aucun accès hors de la mémoire émulée")
    usb = json.loads((TWEAK.parent / "11-6ch-usbup.json").read_text(encoding="utf-8"))
    mute_test(stock, tw, usb)
    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ÉCHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
