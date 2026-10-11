#!/usr/bin/env python3
"""Preuve de l'écoute des samples (notes/46 ; tweaks/model-cycles_OS1.13/33-sample-preview.json pour Model-TG,
33-sample-preview-st.json pour sa version avec les moteurs du Syntakt).

Le vrai code de l'OS et de Model-TG, exécuté (Unicorn) sur deux images construites depuis le .syx officiel :
l'« origine » = les mêmes tweaks sans l'écoute des samples (Model-TG seul par défaut), l'image modifiée = avec.
Un seul banc (Rig, sur le moteur de test_model_tg) réunit le navigateur, la note jouée, la boucle des événements de
l'interruption audio et la boucle des voix. Seuls sont remplacés : le système de fichiers (fiches d'inode, ouverture,
lecture d'un preset), l'allocateur, les verrous, les boîtes aux lettres de l'interface, la case du Sound Pool (vt[76]
de l'objet pool du kit : une copie du son voulu), et le chargeur de Model-TG (ensure_loaded : un crochet Python qui
note son appel, l'état du chargeur à ce moment, et rend la case choisie). La pile sous chaque appel est remplie de 0xA5
(un mot laissé non écrit se voit). Le son de chaque piste est celui du kit (0x4f000000 + 28 + 100 * piste), rendu par
le vrai sound_obj de Model-TG (singleton du projet 0x40fe4228, objet de piste +212 + 68 * piste, vtable[40]).

  1. Écritures : octets d'origine (l'OS d'origine pour les masques et les accroches, le jmp de Model-TG en
     0x4008171e) ; l'image ne diffère de l'origine que par ces écritures ; aucune ne recouvre un autre tweak (du
     jeu --with, et du catalogue sauf ceux qui ne vont jamais avec : conflits déclarés par Model-TG, par le tweak ou
     contre l'un des deux, comme gen_sample_preview.check_overlaps) sauf ce jmp ; refusé sans Model-TG (requires, et
     octets d'origine) ; le code de sp_lock de Model-TG est celui pour lequel le tweak est écrit ; pd_mode et ld_busy
     sont ceux du préchargeur et de led_hook (gen_sample_preview.tg_uses) ; les six copies de pv_tab, pv_fail et
     pv_failp (à zéro) sont disjointes, dans les octets écrits.
  2. Navigateur (vrais 0x400a64be, curseur déplacé, et 0x400a63ac, appelé tel quel à l'ouverture en 0x400a6d12) :
     piste Sampler, fichier de 2 Mo : l'origine ne désigne rien ; le tweak désigne un tampon de 100 o = le son de la
     piste nommé « SMP » + empreinte, sans ouvrir le fichier, registres d2-d7/a2-a6 gardés, résultat {pv_src, 0}
     exactement, pv_fail remis à zéro. Preset valide : identique à l'origine. Fichier de 120 o qui n'est pas un
     preset : écouté comme un sample. Bornes : 47 o (sans lecture), 48 et 65 o (après la lecture d'origine) : rien ;
     66 et 160 o (après la lecture d'origine, refusée) et 161 o (sans lecture du preset ni bit « ouvert ») : écoutés.
     Empreinte nulle (pv_parse appelé directement, handle fait à la main) : résultat {0, 0}. Piste qui n'est pas un
     Sampler, ou sans objet son : identique (l'appel d'origine a lieu). Deux défilements : les deux tampons
     alternent, chacun avec le bon nom.
  3. Note jouée (vrai 0x4008171e jusqu'à l'envoi 0x4005894a, Model-TG note_on_hook compris) : sample en mémoire (case
     63, la dernière) -> identique à l'origine ; pas en mémoire -> un seul chargement (d0 = empreinte, pd_mode 1,
     ld_busy 1, niveau 0), puis la note part ; chargement raté -> rien n'est envoyé, pv_fail = l'empreinte et
     pv_failp = le son désigné (ARMED) ; deuxième appui : pas de nouvel essai ; le même sample désigné à nouveau par
     le Sound Pool (vrai chemin pool de 0x400a63ac, autre tampon, sans pv_parse) -> nouvel essai ; deux défilements
     du pool sans appui ramènent le tampon de l'échec -> pas d'essai (limite voulue) ; un preset désigné par le
     navigateur remet pv_fail à zéro -> nouvel essai, même dans le tampon de l'échec ; même tampon, autre sample ->
     essai. Chargeur occupé, niveau d'interruption non nul -> rien, sans essai ; autres sources, pas tenus, autre
     piste, rien de désigné, son qui ne nomme pas de sample -> identique à l'origine. Le chargeur simulé détruit tous
     les registres que son contrat lui permet (il ne garde que d2-d4/a2) : pv_note rend quand même d2-d7/a2-a6.
  4. Moteur audio (vraie boucle des événements 0x40058d46..0x400591e4, vrai sp_lock) : note d'écoute d'un son du
     Sampler, pistes 1 à 6 : l'origine efface le son de la note (CUR_SNDS = 0, puis lit l'adresse 0x60) ; le tweak y
     met sa copie (pv_tab), seule différence de tout l'état ; les écritures de la passe (tracées, hors pile de
     l'interruption) sont celles de l'origine, l'effacement devenu le pointeur suivi des 25 mots de la copie ; sp_lock
     prend alors la case du sample écouté (track_lock = 1). Note suivante normale, son qui n'est pas du Sampler, notes
     normales : état et écritures identiques. Source 0x80 avec un sample désigné absent de la mémoire : pas de
     chargement, la note part, sp_lock ne le trouve pas et la voix joue le sample de la piste (pl_dirty levé).
     pv_copy seul, pistes 7 et 8 (pv_tab[6], [7] = pv_fail, pv_failp posés à une adresse témoin) : une seule écriture,
     l'effacement d'origine. Le coût d'une passe (instructions, origine -> modifié) est affiché.
     (Les octets +96..+99 des sons de test sont à zéro, ce que l'émulation lit en 0x60 dans l'origine : le reste de
     l'état peut alors être comparé tel quel.)
  5. De bout en bout, dans le même moteur : le navigateur désigne le sample (2 Mo, pas en mémoire), le pad le charge,
     la boucle des événements le transmet, la vraie boucle des voix le joue (deux samples de niveaux opposés : le
     signe de la sortie dit lequel joue) ; la note normale suivante rejoue le sample de la piste.

Durée : 45 à 65 s par version de Model-TG (deux versions avec --syntakt sans Model-TG dans --with).

    python3 tools/emu/test_sample_preview.py --cycles model-cycles_OS1.13.syx \\
        [--with 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm,arp,trig-hold,tempo-max,boot-anim \\
         --syntakt Syntakt_OS1.42.syx]
"""
import argparse
import hashlib
import json
import pathlib
import struct
import sys
from collections import defaultdict

import numpy as np
from unicorn import UcError, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import m68k_const as mk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build                        # noqa: E402
import gen_sample_preview as G      # noqa: E402
import test_model_tg as TM          # noqa: E402
import test_sdvintage as T          # noqa: E402

TW = HERE.parent.parent / "tweaks" / "model-cycles_OS1.13"
BASE = build.BASE
FAIL = []

# --- l'OS (1.13) --------------------------------------------------------------------------------------------------
NOTE_ON = 0x4008171e              # note jouée en direct (piste, note, vélocité, source, sans envoi, -1, vitesse)
POST = 0x4005894a                 # envoi de l'événement de note au moteur audio
ACTIVE = 0x40a700c4               # piste active
ARMED = 0x40fb5a04                # son désigné pour l'écoute (0x40081bd6), emporté par la note (0x40081860)
BUFS = (0x40a78c90, 0x40a78cf4)   # les deux tampons de 100 o, en alternance (0x40058504)
PREVIEW = 0x400a63ac              # écoute de l'entrée (navigateur, index) ; appelée aussi en 0x400a6d12
CURSOR = 0x400a64be               # curseur déplacé : 0x400a63ac, sinon 0x40081bd6(0)
PARSE = 0x400a3052                # lit un preset (a0 = &résultat, &handle) ; appelé en 0x400a6426
READ = 0x400a2a28                 # lit le fichier d'un preset (tampon, &handle) : 0 / -1
SND_PARSE = 0x4005d776            # décode le preset lu dans un son
OPEN = 0x4007e3a0                 # ouvre un fichier par son handle
OPEN_BITS = 0x40fe8e10            # fichiers ouverts (un bit par inode)
CUR_SNDS = 0x800017ec             # son de la note de chaque piste, 0x800015a0 + (147 + piste) * 4
TARGETS = 0x800015ae              # 66 o du son de la note, par piste (0x40058a0a)
KITP = 0x800017e4                 # kit en cours, côté audio
CUR_KIT = 0x40a78888              # kit en cours, lu par Model-TG (le même kit)
BANK = 0x406fa040                 # banque de patterns (0x40054828)
PROJ_PTR = 0x40fe4228             # singleton du projet (0x400cf866)
UIS_PTR = 0x40fe4218              # état de l'interface (live rec : octet +359, lu par l'arpégiateur)
EV_LOOP, EV_END = 0x40058d46, 0x400591e4
# --- Model-TG v1.1.0 : adresses absentes de « symbols », les mêmes dans les deux versions ; le code de sp_lock est
# vérifié (empreinte SP_LOCK_SHA) dans la charge utile de chacune, avec ses références absolues à cet état.
SP_LOCK = 0x401ad958              # le son de la note (CUR_SNDS) nomme-t-il un sample en mémoire ?
TRACK_LOCK = 0x401ada36           # octet par piste : cette note joue le sample d'un son verrouillé
TRACK_HASH = 0x401be3a0           # sample de chaque piste ; track_slot juste après
TRACK_SLOT = 0x401be3b8           # case jouée par chaque piste (-1 : silence)
KIT_OK = 0x401befcc
PL_DIRTY = 0x401b3b84             # sp_lock n'a pas trouvé le sample nommé : le préchargeur est relancé
SP_LOCK_SHA = "724c8066261e528536b015ca2e331a5e4140bb63aecd1b6cacc093f748032a2d"   # sp_lock .. track_lock + 8
SP_LOCK_REFS = {"kit_ok": "b0b9401befcc", "track_slot": "41f9401be3b8", "track_hash": "41f9401be3a0",
                "pl_dirty": "23c0401b3b84", "slot_hash": "41f9401be4a0", "CUR_SNDS": "0680800017ec",
                "CUR_KIT": "203940a78888"}
# --- le banc ------------------------------------------------------------------------------------------------------
STOP = 0x40780000                 # mcengine.STOP
CALL_SP = 0x9000e000
FRAME = 0x9000f000                # cadre de l'interruption audio (test_arp)
KIT = 0x4f000000
POOL3 = 0x4f100000
FIX = 0x93000000                  # objets du banc (0x93000000..0x95000000)
PM, FSD, SPD, ENT, INODE, PMVT, TRKVT, UIST = (FIX + 0x1000 * i for i in range(8))
PROJ = FIX + 0x10000
POOLVT, POOLFN, POOLSND = FIX + 0x9000, FIX + 0x9100, FIX + 0x9200   # Sound Pool du kit (mode pool du navigateur)
MIDI = FIX + 0x20000
HEAP = 0x94000000
STACK_POISON = 0x3000             # octets sous CALL_SP remplis de 0xA5 avant chaque appel (pile jamais à zéro)
CALLEE = [getattr(mk, f"UC_M68K_REG_D{i}") for i in range(2, 8)] + \
         [getattr(mk, f"UC_M68K_REG_A{i}") for i in range(2, 7)]
CALLEE_VALS = [0x22220002, 0x33330003, 0x44440004, 0x55550005, 0x66660006, 0x77770007,
               0x93f00000, 0x93f10000, 0x93f20000, 0x93f30000, 0x93f40000]
CLOBBER = [getattr(mk, f"UC_M68K_REG_{r}") for r in ("D1", "D5", "D6", "D7", "A0", "A1", "A3", "A4", "A5", "A6")]
SAMPLER = 6                       # machine du Sampler de Model-TG (octet +38 du son)
OWN_H, OWN_SLOT, PV_SLOT = 0x0000AAAA, 3, 7
OWN_PCM, PV_PCM, N_PCM = 0x4c000000, 0x4c100000, 48000
# fichiers du navigateur : (taille, empreinte) ; None = dossier
H1, H2, H120 = 0x6809683D, 0x0BADF00D, 0x1234ABCD
PRESET_H = 0x11111111
# (bit 0 de l'empreinte toujours levé : 0x4007de0c n'accepte que ces fiches, une empreinte nulle n'arrive jamais ici)
FILES = [(2_000_000, H1), (120, PRESET_H), None, (2_000_000, H2), (120, H120), (65, 0x55555555), (66, 0x66666667),
         (48, 0x48484849), (161, 0x77777777), (47, 0x44444445), (160, 0xA0A0A0A1)]


def check(ok, msg):
    print(("  ok    " if ok else "  ECHEC ") + msg, flush=True)
    if not ok:
        FAIL.append(msg)


def sound(machine, name, seed):
    """Un son de 100 o (nom à +4, machine à +38) ; +96..+99 à zéro (voir 4. dans l'en-tête)."""
    s = bytearray((seed + 3 * i) & 0x3f for i in range(100))
    s[0:4] = bytes(4)
    s[4:20] = name.ljust(16, b"\0")[:16]
    s[38] = machine
    s[96:100] = bytes(4)
    return bytes(s)


def smp(h):
    return b"SMP%08X" % h


def named(snd, h):
    """Ce que pv_parse doit construire : le son de la piste, octets +4..+14 = « SMP » + empreinte."""
    return snd[:4] + smp(h) + snd[15:]


TRACK_SOUNDS = [sound(0, b"Kick", 0x01), sound(2, b"Metal", 0x05), sound(SAMPLER, smp(OWN_H), 0x09),
                sound(SAMPLER, smp(OWN_H), 0x0d), sound(4, b"Tone", 0x11), sound(SAMPLER, smp(OWN_H), 0x15)]
PRESET = sound(4, b"Tone preset", 0x21)


class Variant:
    """Une version de Model-TG et les tweaks qui l'accompagnent : l'image d'origine et l'image modifiée."""

    def __init__(self, stock, ids, by_id, syntakt_file):
        load = (lambda i: json.loads(by_id[i].read_text(encoding="utf-8")))
        self.tweaks = sorted((load(i) for i in ids), key=lambda t: t["order"])
        st = "model-tg-st" in ids
        self.pv = load("sample-preview-st" if st else "sample-preview")
        self.tg = next(t for t in self.tweaks if t["id"] in ("model-tg", "model-tg-st"))
        self.label = ", ".join(t["id"] for t in self.tweaks)
        pl, _ = build.build_payload(self.tweaks, stock, syntakt_file)
        self.base = bytes(build.apply_writes(stock, self.tweaks)[0]) + pl
        self.img = bytes(build.apply_writes(stock, sorted(self.tweaks + [self.pv], key=lambda t: t["order"]))[0]) + pl
        self.end = BASE + len(stock) + self.tg["append"]["size"]
        syn = [t for t in self.tweaks if t.get("append", {}).get("syntakt")]
        mac = [t for t in self.tweaks if t["id"] in ("macro", "macro-tg")]
        self.payload = None
        if syn:
            import syntakt
            self.payload = (int(syn[0]["append"]["dest"], 16),
                            build.payload_runtime(syn[0], stock, syntakt.dsp_image(syntakt_file)))
        elif mac:                                   # MACRO (notes/43) : sa charge utile telle qu'en mémoire
            self.payload = (int(mac[0]["append"]["dest"], 16), build.payload_runtime(mac[0], stock, None))
        self.tgs = {n: int(v, 16) for n, v in self.tg["symbols"].items()}
        self.pvs = {n: int(v, 16) for n, v in self.pv["symbols"].items()}


class Rig:
    """Un Model:Cycles réduit au navigateur, à la note jouée, à la boucle des événements et aux voix, sur une image."""

    def __init__(self, v, img, track=2):
        self.v, self.track = v, track
        e = self.e = TM.engine(img, end=v.end, payload=v.payload)
        uc = self.uc = e.uc
        uc.reg_write(mk.UC_M68K_REG_SR, 0x2700)
        # l'OS d'origine lit *(0 + 96) après une note d'écoute (0x40059160) : la page 0 est là, chaque accès noté
        uc.mem_map(0, 0x1000)
        self.low = []
        uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, self._low, begin=0, end=0xfff)
        uc.mem_map(FIX, 0x02000000)
        self.heap, self.errors = HEAP, []
        self.calls = defaultdict(list)
        self.posted, self.ui, self.loads = [], [], []
        self.post_real = False
        self.loader = lambda h: -1
        self.place = False                       # le chargeur simulé « charge » aussi le sample (5.)
        tg = v.tgs
        for addr, fn in {0x400802e0: self._new, 0x400802ec: lambda a: 0, 0x40001cc4: lambda a: 0,
                         0x40001df6: lambda a: 0, 0x4007e764: self._inode, 0x4007e68c: lambda a: 0,
                         OPEN: self._open, 0x4004067c: lambda a: 0, 0x40001fba: lambda a: 0,
                         0x40056178: self._pos, 0x40080bf6: self._ui, 0x4008a5d0: lambda a: MIDI,
                         READ: self._read, SND_PARSE: self._parse, PARSE: lambda a: None,
                         tg["ensure_loaded"]: self._load, POST: self._post,
                         v.pvs["pv_parse"]: lambda a: None}.items():     # pv_parse : appels seulement comptés
            self.stub(addr, fn)
        w = self.w32
        # file des événements et kit (test_arp.Audio)
        w(0x40fde8f8, POOL3)
        self.call(0x40091d94, 0x42)
        w(KITP, KIT)
        w(KITP + 4, KIT + 628)
        w(CUR_KIT, KIT)
        self.sounds = list(TRACK_SOUNDS)              # la piste écoutée est toujours un Sampler
        if self.sounds[track][38] != SAMPLER:
            self.sounds[track] = sound(SAMPLER, smp(OWN_H), 0x19 + track)
        for t in range(6):
            uc.mem_write(KIT + 28 + 100 * t, self.sounds[t])
            w(0x800015a0 + (153 + t) * 4, KIT)
            w(CUR_SNDS + 4 * t, KIT + 28 + 100 * t)
        w(0x40149310, 120 * 120)
        self.now = 1_000_000
        # note jouée : pattern en cours, drapeaux de piste par défaut (0x40061438), heures d'appui (test_arp)
        w(0x40a7887c, BANK)
        for t in range(6):
            uc.mem_write(BANK + 722 * t + 710, struct.pack(">H", 0x680))
        uc.mem_write(0x40fb680c, b"\xff" * 4 * 128 * 6)
        w(UIS_PTR, UIST)
        # projet : objet de chaque piste -> vtable[40] -> son de la piste dans le kit (lu par sound_obj)
        w(PROJ_PTR, PROJ)
        for t in range(6):
            vt = TRKVT + 0x40 * t
            w(PROJ + 212 + 68 * t, vt)
            w(vt + 40, vt + 0x30)
            uc.mem_write(vt + 0x30, b"\x20\x3c" + struct.pack(">I", KIT + 28 + 100 * t) + b"\x4e\x75")
        # Sound Pool (mode pool de 0x400a63ac, 0x400a6444) : 0x4000eb9c(projet) = projet + 116, objet en +628, sa
        # vt[76](index) remplit a0 = {copie du son de la case, compteur} : ici {POOLSND, 0}
        w(PROJ + 116 + 628, POOLVT)
        w(POOLVT + 76, POOLFN)
        uc.mem_write(POOLFN, b"\x20\xbc" + struct.pack(">I", POOLSND) + bytes.fromhex("42a80004" "2008" "4e75"))
        w(ACTIVE, track)
        # navigateur en mode fichier (PresetManager, FileSystemDirectory : vtables de l'OS) ; fichiers FILES
        w(0x40f07cf4, 1)                          # système de fichiers monté
        uc.mem_write(PM, bytes(0x400))
        uc.mem_write(PMVT, bytes(uc.mem_read(0x401183ec, 0x100)))
        w(PMVT + 12, 0x400a311e)                  # nombre d'entrées (getCursor) : 64
        w(PM, PMVT)
        uc.mem_write(FSD, bytes(0x200))
        w(FSD, 0x40112818)
        vec = FSD + 0x180
        for i in range(len(FILES)):
            w(vec + 8 * i, ENT + 16 * i)
            w(ENT + 16 * i, 0x100 + i)
        w(FSD + 260, vec)
        w(FSD + 264, vec + 8 * len(FILES))
        w(SPD, 0x40117a44)
        w(PM + 640, FSD)
        w(PM + 688, SPD)
        w(PM + 632, FSD)
        # Model-TG : kit vérifié, sample de la piste en mémoire (case OWN_SLOT), voix du Sampler sur la piste
        w(KIT_OK, 1)
        for s in range(64):
            w(tg["slot_hash"] + 4 * s, 0)
        self.resident(OWN_SLOT, OWN_H, OWN_PCM, 8192)
        for t in range(6):
            w(TRACK_HASH + 4 * t, OWN_H if self.sounds[t][38] == SAMPLER else 0)
            w(TRACK_SLOT + 4 * t, OWN_SLOT if self.sounds[t][38] == SAMPLER else 0xffffffff)
            e.set(t, machine=0, note=60, pitch=64, decay=127)
        e.set(track, machine=SAMPLER, color=0, shape=127, sweep=127, contour=0, decay=127)

    # -- mémoire et appels --
    def w32(self, a, v):
        self.uc.mem_write(a, struct.pack(">I", v & 0xffffffff))

    def r32(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def mem(self, a, n):
        return bytes(self.uc.mem_read(a, n))

    def _low(self, uc, access, addr, size, value, ud):
        self.low.append((uc.reg_read(mk.UC_M68K_REG_PC), addr))

    def stub(self, addr, fn):
        """fn(args) -> valeur rendue dans d0, ou None : le vrai code s'exécute (l'appel est seulement noté)."""
        def hook(uc, a, size, ud):
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            args = struct.unpack(">6I", uc.mem_read(sp + 4, 24))
            self.calls[addr].append(args)
            r = fn(args)
            if r is None:
                return
            uc.reg_write(mk.UC_M68K_REG_D0, r & 0xffffffff)
            uc.reg_write(mk.UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        self.uc.hook_add(UC_HOOK_CODE, hook, begin=addr, end=addr)

    def call(self, fn, *args, sr=0x2700, regs=False):
        """Appelle fn ; regs : registres d2-d7/a2-a6 posés à CALLEE_VALS avant, rendus après (liste). La pile sous
        l'appel est remplie de 0xA5 (sur la machine, elle n'est jamais à zéro : un mot laissé non écrit se voit)."""
        uc = self.uc
        uc.reg_write(mk.UC_M68K_REG_SR, sr)
        frame = struct.pack(">I", STOP) + b"".join(struct.pack(">I", a & 0xffffffff) for a in args)
        uc.mem_write(CALL_SP - STACK_POISON, b"\xa5" * (STACK_POISON - len(frame)))
        uc.mem_write(CALL_SP - len(frame), frame)
        uc.reg_write(mk.UC_M68K_REG_A7, CALL_SP - len(frame))
        if regs:
            for r, val in zip(CALLEE, CALLEE_VALS):
                uc.reg_write(r, val)
        try:
            uc.emu_start(fn, STOP, count=5_000_000)
        except UcError as ex:
            self.errors.append((fn, uc.reg_read(mk.UC_M68K_REG_PC), str(ex)))
        if uc.reg_read(mk.UC_M68K_REG_PC) != STOP:
            self.errors.append((fn, uc.reg_read(mk.UC_M68K_REG_PC), "n'est pas revenu"))
        self.sr_after = uc.reg_read(mk.UC_M68K_REG_SR)
        self.regs_after = [uc.reg_read(r) for r in CALLEE]
        self.d0 = uc.reg_read(mk.UC_M68K_REG_D0)
        return self.d0

    def clean(self):
        return not self.errors and not self.e.unmapped

    # -- interceptions --
    def _new(self, a):
        p, n = self.heap, (a[0] + 15) & ~15
        self.heap += n
        self.uc.mem_write(p, bytes(n))
        return p

    def _inode(self, a):
        i = a[0] - 0x100
        if not 0 <= i < len(FILES):
            return 0
        rec = INODE + 0x80 * i
        self.uc.mem_write(rec, bytes(0x80))
        size, h = FILES[i] or (0, 0x22222223 + i)
        self.w32(rec, 0x01000001 if FILES[i] is None else 0x00020001)
        self.w32(rec + 4, size)
        self.w32(rec + 12, h)
        self.w32(rec + 16, 0x1234)
        return rec

    def _open(self, a):
        iid = self.r32(a[0])
        self.w32(a[1], iid)
        return 1 if 0 <= iid - 0x100 < len(FILES) else 0xffffffff

    def _read(self, a):
        """Taille de preset : le contenu n'est pas émulé (PRESET_H se lit, les autres non) ; sinon le vrai code
        (il refuse la taille)."""
        size, h = self.r32(a[1] + 8), self.r32(a[1] + 4)
        if not 48 <= size <= 160:
            return None
        return 0 if h == PRESET_H else 0xffffffff

    def _parse(self, a):
        self.uc.mem_write(a[0], PRESET)
        return 1

    def _pos(self, a):
        self.uc.mem_write(a[2], bytes([a[0] // 1000 % 64, a[1] + 1, 0]))
        return 0

    def _ui(self, a):
        self.ui.append(self.mem(a[0], 32))
        return 0

    def _post(self, a):
        self.posted.append(self.mem(a[0], 56))
        return None if self.post_real else 0

    def _load(self, a):
        uc, tg = self.uc, self.v.tgs
        h = uc.reg_read(mk.UC_M68K_REG_D0)
        self.loads.append((h, self.r32(tg["pd_mode"]), self.r32(tg["ld_busy"]),
                           uc.reg_read(mk.UC_M68K_REG_SR) & 0x700))
        slot = self.loader(h)
        for k, reg in enumerate(CLOBBER):        # ensure_loaded ne garde que d2-d4/a2 (sample_preview.S)
            uc.reg_write(reg, 0xdead0000 + k)
        if slot >= 0:
            if self.place:
                self.resident(slot, h, PV_PCM, -8192)
            else:
                self.w32(tg["slot_hash"] + 4 * slot, h)
        return slot

    # -- Model-TG --
    def resident(self, slot, h, pcm, level):
        """Un sample en mémoire : en-tête de 64 o (+4 octets de données, +8 fréquence), niveau constant."""
        hdr = bytearray(64)
        struct.pack_into(">II", hdr, 4, 2 * N_PCM, 48000)
        self.uc.mem_write(pcm, bytes(hdr) + struct.pack(">h", level) * N_PCM)
        sh = self.v.tgs["slot_hash"]
        for k, val in enumerate((h, pcm, N_PCM, 64 + 2 * N_PCM)):   # slot_hash, slot_base, slot_count, slot_size
            self.w32(sh + 0x100 * k + 4 * slot, val)

    def lock(self, t):
        return struct.unpack(">i", self.mem(TRACK_SLOT + 4 * t, 4))[0], self.mem(TRACK_LOCK + t, 1)[0]

    # -- navigateur --
    def browse(self, cursor):
        """Curseur sur l'entrée cursor : 0x400a64be (tâche de l'interface, niveau 0)."""
        self.w32(PM + 16, cursor)
        self.call(CURSOR, PM, 0, sr=0x2000)
        return self.r32(ARMED)

    def open_at(self, index):
        """0x400a63ac(navigateur, index), comme l'appelle l'ouverture du navigateur (0x400a6d12)."""
        return self.call(PREVIEW, PM, index, sr=0x2000) & 0xff

    def pool_arm(self, snd):
        """Le navigateur en mode Sound Pool désigne snd (une case du pool, par exemple un sample lock) : le vrai
        0x400a64be -> 0x400a63ac, chemin 0x400a6444 (vt[152] = 0x400a3308 faux : +640 != +632), puis 0x400a647c
        (tampon suivant de 0x40058504, copie, 0x40081bd6) ; jamais 0x400a6426 ni pv_parse. Rend (ARMED, nombre
        d'appels de pv_parse pendant ce défilement)."""
        n = len(self.calls[self.v.pvs["pv_parse"]])
        self.uc.mem_write(POOLSND, snd)
        self.w32(PM + 640, SPD)
        armed = self.browse(0)
        self.w32(PM + 640, FSD)
        return armed, len(self.calls[self.v.pvs["pv_parse"]]) - n

    # -- note jouée --
    def press(self, t, note=60, src=0x40, held=0, sr=0x2000):
        """0x4008171e(t, note, 100, src, held, -1, -1) : pad ou touche, sans retrig ; rend le dernier événement
        envoyé ou None."""
        self.posted.clear()
        self.w32(0x8000184c, self.now)
        self.call(NOTE_ON, t, note, 100, src, held, 0xffffffff, 0xffffffff, sr=sr, regs=True)
        return self.posted[-1] if self.posted else None

    # -- boucle des événements --
    def run(self):
        """Une passe de la boucle des événements de l'interruption audio (test_arp.Audio.run) ; rend le masque des
        pistes déclenchées, ou None. self.writes : les écritures de la passe, dans l'ordre, (adresse, taille,
        valeur), hors de la pile de l'interruption (FRAME - 0x1000..FRAME) ; self.icount : instructions exécutées."""
        uc = self.uc
        uc.reg_write(mk.UC_M68K_REG_SR, 0x2700)
        uc.mem_write(FRAME - 168, bytes(168))
        self.w32(FRAME - 80, self.now)
        self.w32(0x8000184c, self.now)
        sp = FRAME - 168 - 0x100
        uc.mem_write(sp, bytes(8))
        for r, val in ((mk.UC_M68K_REG_A6, FRAME), (mk.UC_M68K_REG_A7, sp), (mk.UC_M68K_REG_D2, 0),
                       (mk.UC_M68K_REG_D5, 0), (mk.UC_M68K_REG_D6, 0)):
            uc.reg_write(r, val)
        self.writes, n = [], [0]

        def wr(uc, access, addr, size, value, ud):
            if not FRAME - 0x1000 <= addr < FRAME:
                self.writes.append((addr, size, value & ((1 << 8 * size) - 1)))

        def ins(uc, a, size, ud):
            n[0] += 1
        hooks = [uc.hook_add(UC_HOOK_MEM_WRITE, wr), uc.hook_add(UC_HOOK_CODE, ins)]
        try:
            uc.emu_start(EV_LOOP, EV_END, count=2_000_000)
        except UcError as ex:
            self.errors.append((EV_LOOP, uc.reg_read(mk.UC_M68K_REG_PC), str(ex)))
            return None
        finally:
            for h in hooks:
                uc.hook_del(h)
            self.icount = n[0]
        if uc.reg_read(mk.UC_M68K_REG_PC) != EV_END:
            return None
        return uc.reg_read(mk.UC_M68K_REG_D4)

    def ev_state(self):
        """L'état que la boucle des événements écrit : sons et paramètres des notes (SRAM), notes et retrig."""
        return (self.mem(0x800015a0, 0x2b8) + self.mem(0x40fe4c90, 0x70) + self.mem(0x40a78d58, 168)
                + self.mem(0x40a78e10, 0x20))

    def ev_addr(self, k):
        for lo, n in ((0x800015a0, 0x2b8), (0x40fe4c90, 0x70), (0x40a78d58, 168), (0x40a78e10, 0x20)):
            if k < n:
                return lo + k
            k -= n

    def listen(self, mask, blocks=30):
        """La vraie boucle des voix : le bloc du déclenchement, puis blocks - 1 ; moyenne de la piste après 8 blocs."""
        out = [self.e.block(mask)[self.track]]
        out += [self.e.block(0)[self.track] for _ in range(blocks - 1)]
        return float(np.concatenate(out)[32 * 8:].mean())


def diff_words(a, b, rig):
    return sorted({rig.ev_addr(k & ~3) for k in range(len(a)) if a[k] != b[k]})


# --- 1. écritures ---------------------------------------------------------------------------------------------------
def writes_tests(stock, v):
    pv, tg = v.pv, v.tg
    tg_img = build.apply_writes(stock, [tg])[0]
    jmp_tg = struct.pack(">HI", 0x4ef9, v.tgs["pad_load_hook"])
    ok_old, spans = True, []
    for w in pv["writes"]:
        off, old, new = w["off"], bytes.fromhex(w["old"]), bytes.fromhex(w["new"])
        spans.append((off, off + len(new)))
        ref = tg_img if off + BASE == NOTE_ON else stock
        ok_old &= ref[off:off + len(old)] == old
    check(ok_old, f"{pv['id']} : {len(pv['writes'])} écritures, octets d'origine = l'OS d'origine (masques, accroches)"
                  f" et le jmp de Model-TG en {NOTE_ON:#x}")
    at = {w["off"] + BASE: bytes.fromhex(w["new"]) for w in pv["writes"]}
    s = v.pvs
    check(stock[NOTE_ON - BASE:NOTE_ON - BASE + 6].hex() == "4e56ff98707f"
          and tg_img[NOTE_ON - BASE:NOTE_ON - BASE + 6] == jmp_tg
          and at.get(NOTE_ON) == struct.pack(">HI", 0x4ef9, s["pv_note"])
          and at.get(0x400a6426) == struct.pack(">HI", 0x4eb9, s["pv_parse"])
          and at.get(0x4005910e) == struct.pack(">HIH", 0x4eb9, s["pv_copy"], 0x600a),
          f"accroches : {NOTE_ON:#x} link.w/moveq d'origine -> jmp pad_load_hook (Model-TG) -> jmp pv_note ; "
          "0x400a6426 jsr pv_parse ; 0x4005910e jsr pv_copy ; bra.s 0x40059120")
    dif = [k for k in range(len(v.base)) if v.base[k] != v.img[k]] if len(v.base) == len(v.img) else None
    check(dif is not None and all(any(lo <= k < hi for lo, hi in spans) for k in dif),
          f"l'image modifiée ne diffère de l'origine que dans ces écritures ({len(dif or [])} octets)")
    zone = [(0x4005910f - BASE, 0x40059120 - BASE)]
    sure, doubt = build.refs_into(stock, zone)
    check(not sure and not doubt, "aucune référence de l'OS d'origine vers 0x4005910f..0x4005911f (les octets "
                                  "sautés derrière jsr pv_copy ; bra.s)")
    mine = [(w["off"], w["off"] + len(bytes.fromhex(w["old"]))) for w in pv["writes"]]

    def overlaps(others):
        bad = []
        for o in others:
            for w in o["writes"]:
                a, b = w["off"], w["off"] + len(bytes.fromhex(w["old"]))
                for lo, hi in mine:
                    if a < hi and lo < b and not (o["id"] == tg["id"] and lo == NOTE_ON - BASE):
                        bad.append(f"{o['id']}@{a + BASE:#x}")
        return bad
    bad = overlaps(v.tweaks)
    check(not bad, f"aucun recouvrement avec {v.label} sauf le jmp de Model-TG en {NOTE_ON:#x} {bad[:4]}")
    cat = build.load_catalog()["model-cycles_OS1.13"][1]
    # jamais construits avec ce tweak (comme check_overlaps de gen_sample_preview.py) : l'autre version, les conflits
    # de Model-TG et du tweak, et les tweaks qui déclarent un conflit avec l'un des deux
    never = [o["id"] for o in cat.values() if o["id"] in ("sample-preview", "sample-preview-st")
             or o["id"] in tg.get("conflicts", []) or o["id"] in pv.get("conflicts", [])
             or {tg["id"], pv["id"]} & set(o.get("conflicts", []))]
    compat = [o for o in cat.values() if o["id"] not in never]
    bad = overlaps(compat)
    check(not bad, f"aucun recouvrement avec les {len(compat)} tweaks du catalogue compatibles avec {tg['id']} + "
                   f"{pv['id']} (sauf ce jmp ; écartés : conflits déclarés d'un côté ou de l'autre, "
                   f"{len(never)} tweaks) {bad[:4]}")
    other = "model-tg" if tg["id"] == "model-tg-st" else "model-tg-st"
    refused = []
    for combo in ([pv], [cat[other], pv]):
        try:
            build.check_conflicts(combo)
            refused.append(False)
        except SystemExit:
            refused.append(True)
    try:
        build.check_conflicts([tg, pv])
        accepted = True
    except SystemExit:
        accepted = False
    try:
        build.apply_writes(stock, [pv])
        applies = True
    except SystemExit:
        applies = False
    check(all(refused) and accepted and not applies,
          f"build : {pv['id']} refusé seul et avec {other} (requires {pv['requires']}), accepté avec {tg['id']} ; "
          f"ses octets d'origine refusent l'OS sans Model-TG")
    rt = build.payload_runtime(tg, stock, None)
    d = int(tg["append"]["dest"], 16)
    span = rt[SP_LOCK - d:TRACK_LOCK + 8 - d]
    refs = {n: span.find(bytes.fromhex(p)) for n, p in SP_LOCK_REFS.items()}
    check(hashlib.sha256(span).hexdigest() == SP_LOCK_SHA and all(k >= 0 for k in refs.values())
          and v.tgs["slot_hash"] == 0x401be4a0,
          f"{tg['id']} : sp_lock ({SP_LOCK:#x}) est le code attendu (empreinte), avec kit_ok, track_slot, "
          f"track_hash, pl_dirty, slot_hash, CUR_SNDS et CUR_KIT aux adresses du banc")
    uses = G.tg_uses(rt, d, v.tgs)
    check(uses["pd_mode"] == 1 and uses["ld_busy"] >= 2,
          f"{tg['id']} : pd_mode et ld_busy sont ceux du chargeur (le préchargeur pose pd_mode autour de son jsr "
          f"ensure_loaded, led_hook prend ld_busy par lea (d16,pc) ; gen_sample_preview.tg_uses : {uses})")
    pvt = [struct.unpack(">I", v.img[s["pv_tab"] - BASE + 4 * t:][:4])[0] for t in range(6)]
    check(len(set(pvt)) == 6 and all(abs(a - b) >= 100 for a in pvt for b in pvt if a != b)
          and all(any(lo <= x - BASE and x - BASE + 100 <= hi for lo, hi in spans) for x in pvt)
          and all(0x40000000 <= x < 0x48000000 - 100 for x in pvt),
          f"pv_tab : six copies de 100 o disjointes, dans les octets écrits par le tweak, dans la plage que sp_lock "
          f"lit (0x40000000..0x48000000) : {' '.join(hex(x) for x in pvt)}")
    var = (s["pv_fail"], s["pv_failp"])
    check(var[0] != var[1] and all(struct.unpack(">I", v.img[a - BASE:a - BASE + 4])[0] == 0 for a in var)
          and all(any(lo <= a - BASE and a - BASE + 4 <= hi for lo, hi in spans) for a in var)
          and not any(x - 3 < a < x + 100 for a in var for x in pvt + [s["pv_src"]]),
          f"pv_fail ({var[0]:#x}) et pv_failp ({var[1]:#x}) : à zéro dans l'image (ces masques ne sont pas remis à "
          f"zéro au démarrage), dans les octets écrits par le tweak, hors des copies et de pv_src")
    return pvt


# --- 2. navigateur --------------------------------------------------------------------------------------------------
def browser_tests(v):
    s = v.pvs
    kit2 = TRACK_SOUNDS[2]
    # piste Sampler, fichier de 2 Mo
    res = {}
    for name, img in (("origine", v.base), ("modifié", v.img)):
        r = Rig(v, img)
        if img is v.img:
            r.w32(s["pv_fail"], H2)
        seen = {}

        def at_jsr(uc, a, size, ud, seen=seen):
            seen["in"] = [uc.reg_read(x) for x in CALLEE + [mk.UC_M68K_REG_A7]]
            seen["res"] = uc.reg_read(mk.UC_M68K_REG_D2)

        def at_ret(uc, a, size, ud, seen=seen):
            seen["out"] = [uc.reg_read(x) for x in CALLEE + [mk.UC_M68K_REG_A7]]
            seen["d0"] = uc.reg_read(mk.UC_M68K_REG_D0)
            seen["result"] = struct.unpack(">II", uc.mem_read(seen["d0"], 8))   # {son, compteur}
        r.uc.hook_add(UC_HOOK_CODE, at_jsr, begin=0x400a6426, end=0x400a6426)
        r.uc.hook_add(UC_HOOK_CODE, at_ret, begin=0x400a642c, end=0x400a642c)
        bit = 1 << (0x100 & 31)
        r.w32(ARMED, 0)
        armed = r.browse(0)
        res[name] = dict(armed=armed, data=r.mem(armed, 100) if armed else None, read=len(r.calls[READ]),
                         open=len(r.calls[OPEN]), parse=len(r.calls[PARSE]), seen=seen,
                         opened=bool(r.r32(OPEN_BITS + 4 * (0x100 >> 5)) & bit), clean=r.clean(),
                         fail=r.r32(s["pv_fail"]) if img is v.img else None)
    o, m = res["origine"], res["modifié"]
    check(o["armed"] == 0 and o["read"] == 1 and o["opened"],
          "origine, piste Sampler, fichier de 2 Mo : rien n'est désigné (0x40fb5a04 = 0) ; la lecture du preset "
          "(0x400a2a28) ouvre le fichier et refuse sa taille, sans le refermer (bit de 0x40fe8e10 resté levé)")
    check(m["armed"] == BUFS[0] and m["data"] == named(kit2, H1),
          f"modifié : 0x40fb5a04 = tampon {BUFS[0]:#x}, ses 100 o = le son de la piste, octets +4..+14 = "
          f"« {smp(H1).decode()} »")
    check(m["read"] == 0 and m["open"] == 0 and m["parse"] == 0 and not m["opened"],
          "modifié : le fichier n'est jamais ouvert (ni 0x400a3052, ni 0x400a2a28, ni 0x4007e3a0 ; aucun bit de "
          "fichier ouvert)")
    sm, so = m["seen"], o["seen"]
    check(sm.get("in") == sm.get("out") and so.get("in") == so.get("out") and sm.get("d0") == sm.get("res")
          and sm.get("result") == (s["pv_src"], 0) and m["fail"] == 0 and o["clean"] and m["clean"],
          "modifié : autour de l'appel en 0x400a6426, d2-d7/a2-a6 et la pile rendus intacts, d0 = &résultat "
          f"(comme l'original), résultat = {{pv_src, 0}} = {{{s['pv_src']:#x}, 0}} exactement (pile remplie de 0xA5 "
          f"avant l'appel) ; pv_fail remis à zéro ; aucun accès hors mémoire")
    # 0x400a6d12 : 0x400a63ac appelé tel quel, sa réponse ignorée
    out = {}
    for name, img in (("origine", v.base), ("modifié", v.img)):
        r = Rig(v, img)
        r.w32(ARMED, 0)
        ret = r.open_at(0)
        out[name] = (ret, r.r32(ARMED), r.mem(r.r32(ARMED), 100) if r.r32(ARMED) else None)
    check(out["origine"][:2] == (0, 0) and out["modifié"][0] == 1 and out["modifié"][1] == BUFS[0]
          and out["modifié"][2] == named(kit2, H1),
          "ouverture du navigateur (0x400a63ac comme en 0x400a6d12) sur ce fichier : l'origine rend faux et ne "
          "désigne rien ; le modifié rend vrai et désigne le sample")

    def one(img, cursor, active=2, nosound=False):
        r = Rig(v, img)
        r.w32(ACTIVE, active)
        if nosound:
            r.w32(TRKVT + 0x40 * active + 40, 0)          # vtable[40] nulle : sound_obj rend 0
        r.w32(ARMED, 0)
        a = r.browse(cursor)
        return (a, (r.mem(a, 100) if a else None), len(r.calls[PARSE]), len(r.calls[READ]), r.clean(),
                len(r.calls[OPEN]), any(r.mem(OPEN_BITS, 64)))
    b, p = one(v.base, 1), one(v.img, 1)
    check(b == p and p[0] == BUFS[0] and p[1] == PRESET and p[2] == 1,
          "preset valide (120 o) sur la piste Sampler : identique à l'origine (le preset est désigné, lu par "
          "l'appel d'origine)")
    b, p = one(v.base, 4), one(v.img, 4)
    check(b[0] == 0 and p[0] == BUFS[0] and p[1] == named(kit2, H120) and p[3] == 1,
          f"fichier de 120 o qui n'est pas un preset (lecture refusée) : l'origine ne désigne rien ; le modifié "
          f"essaie d'abord l'original, puis désigne « {smp(H120).decode()} »")
    for cursor, desc, want in ((5, "65 o", False), (6, "66 o", True), (9, "47 o", False),
                               (7, "48 o", False), (10, "160 o", True), (8, "161 o", True), (2, "dossier", False)):
        b, p = one(v.base, cursor), one(v.img, cursor)
        size, h = FILES[cursor] or (0, 0)
        isfile = FILES[cursor] is not None
        read = isfile and 48 <= size <= 160               # taille de preset : l'original est essayé d'abord
        good = (b[0] == 0 and (p[0] == BUFS[0] and p[1] == named(kit2, h) if want else p[0] == 0) and p[4]
                and p[3] == int(read) and p[5] == 0 and not p[6]
                and b[3] == int(isfile) and b[6] == (isfile and not read))
        how = ("après la lecture d'origine (0x400a2a28, refusée : pas un preset)" if read else
               "sans lecture du preset" if isfile else "aucune lecture")
        check(good, f"piste Sampler, {desc} : {'désigné' if want else 'rien'}, {how}, fichier jamais ouvert "
                    f"(origine : rien{', fichier ouvert et laissé ouvert' if isfile and not read else ''})")
    # garde de l'empreinte nulle (0x4007de0c ne laisse passer aucune fiche sans le bit 0 : jamais vue par le
    # navigateur) : pv_parse appelé directement, handle {entrée, empreinte, taille, 4e mot} fait à la main
    res, hd = FIX + 0x31000, FIX + 0x31100

    def direct(h):
        r = Rig(v, v.img)
        r.uc.mem_write(res, b"\xa5" * 8)
        r.uc.mem_write(hd, struct.pack(">4I", 0x100, h, 2_000_000, 0x1234))
        r.w32(s["pv_fail"], H2)
        r.uc.reg_write(mk.UC_M68K_REG_A0, res)
        r.call(s["pv_parse"], hd, sr=0x2000, regs=True)
        return (struct.unpack(">II", r.mem(res, 8)), r.d0, r.uc.reg_read(mk.UC_M68K_REG_A0), r.regs_after,
                r.mem(s["pv_src"], 100), r.r32(s["pv_fail"]), len(r.calls[READ]) + len(r.calls[PARSE]), r.clean())
    z, k = direct(0), direct(H1)
    src0 = v.img[s["pv_src"] - BASE:s["pv_src"] - BASE + 100]
    check(z[0] == (0, 0) and z[1] == z[2] == res and z[3] == CALLEE_VALS and z[4] == src0 and z[5] == 0
          and z[6] == 0 and z[7]
          and k[0] == (s["pv_src"], 0) and k[1] == k[2] == res and k[3] == CALLEE_VALS and k[4] == named(kit2, H1)
          and k[5] == 0 and k[6] == 0 and k[7],
          f"pv_parse appelé directement, 2 Mo, empreinte nulle : résultat {{0, 0}}, pv_src intact, rien de lu ; "
          f"la même avec {H1:#010x} : {{pv_src, 0}}, « {smp(H1).decode()} » ; d0 = a0 = &résultat, d2-d7/a2-a6 "
          f"gardés, pv_fail remis à zéro dans les deux cas")
    for desc, active, nosound in (("piste METAL (machine 2)", 1, False), ("piste sans objet son", 4, True)):
        b, p = one(v.base, 0, active, nosound), one(v.img, 0, active, nosound)
        check(b == p and p[0] == 0 and p[2] == 1 and p[3] == 1,
              f"{desc}, fichier de 2 Mo : identique à l'origine (rien de désigné, l'appel d'origine a lieu)")
    # deux défilements, puis un preset
    seq = {}
    for name, img in (("origine", v.base), ("modifié", v.img)):
        r = Rig(v, img)
        r.w32(ARMED, 0)
        a1 = r.browse(0)
        a2 = r.browse(3)
        seq[name] = (a1, a2, r.mem(BUFS[0], 100), r.mem(BUFS[1], 100), r.browse(1), r.mem(BUFS[0], 100))
    o, m = seq["origine"], seq["modifié"]
    check(m[0] == BUFS[0] and m[1] == BUFS[1] and m[2] == named(kit2, H1) and m[3] == named(kit2, H2)
          and m[4] == BUFS[0] and m[5] == PRESET and o[:2] == (0, 0) and o[4] == BUFS[0],
          f"défilement 2 Mo -> 2 Mo -> preset : les tampons alternent ({BUFS[0]:#x}, {BUFS[1]:#x}, {BUFS[0]:#x}), "
          f"chacun avec son nom (« {smp(H1).decode()} », « {smp(H2).decode()} », le preset)")


# --- 3. note jouée --------------------------------------------------------------------------------------------------
def note_rig(v, img, armed_snd=None, resident=False, fail=0, busy=0):
    r = Rig(v, img)
    if armed_snd is not None:
        r.uc.mem_write(BUFS[0], armed_snd)
        r.w32(ARMED, BUFS[0])
    else:
        r.w32(ARMED, 0)
    if resident:
        r.w32(v.tgs["slot_hash"] + 4 * 63, H2)              # la dernière des 64 cases
    if img is v.img:
        r.w32(v.pvs["pv_fail"], fail)
    r.w32(v.tgs["ld_busy"], busy)
    return r


def note_tests(v):
    s, tg = v.pvs, v.tgs
    snd = named(TRACK_SOUNDS[2], H2)                          # ce que pv_parse désigne pour le fichier H2
    # (a) sample déjà en mémoire
    rb, rp = note_rig(v, v.base, snd, True), note_rig(v, v.img, snd, True)
    eb, ep = rb.press(2), rp.press(2)
    check(ep is not None and ep == eb and struct.unpack_from(">I", ep, 52)[0] == BUFS[0] and not rp.loads
          and rp.regs_after == rb.regs_after == CALLEE_VALS and rp.d0 == rb.d0 and rp.ui == rb.ui
          and rb.clean() and rp.clean(),
          "sample en mémoire (case 63, la dernière lue) : pas de chargement, la note part avec le son désigné (+52), "
          "événement, message à l'interface, d0 et d2-d7/a2-a6 identiques à l'origine")
    # (b) pas en mémoire, chargement réussi
    rb, rp = note_rig(v, v.base, snd), note_rig(v, v.img, snd)
    rp.loader = lambda h: 9
    eb, ep = rb.press(2), rp.press(2)
    check(rp.loads == [(H2, 1, 1, 0)] and not rb.loads,
          f"pas en mémoire : un seul appel d'ensure_loaded, d0 = {H2:#010x}, pd_mode = 1 et ld_busy = 1 pendant "
          f"l'appel, au niveau d'interruption 0")
    check(rp.r32(tg["pd_mode"]) == 0 and rp.r32(tg["ld_busy"]) == 0 and rp.r32(tg["slot_hash"] + 36) == H2
          and rp.sr_after & 0xff00 == 0x2000 and ep is not None and ep == eb and rp.regs_after == CALLEE_VALS
          and rp.d0 == rb.d0 and rp.clean(),
          "après : pd_mode = ld_busy = 0, SR rendu ; la note part, événement identique à celui de l'origine (le son "
          "désigné en +52), d2-d7/a2-a6 gardés")
    # (c) chargement raté, deuxième appui ; nouveau son désigné : Sound Pool, navigateur
    rp = Rig(v, v.img)
    rp.w32(ARMED, 0)
    rp.browse(3)                                              # le navigateur désigne le fichier H2
    armed = rp.r32(ARMED)
    e1 = rp.press(2)
    n1, f1, p1 = len(rp.loads), rp.r32(s["pv_fail"]), rp.r32(s["pv_failp"])
    e2 = rp.press(2)
    n2 = len(rp.loads)
    rb = note_rig(v, v.base, snd)
    rb.uc.mem_write(BUFS[1], snd)
    rb.w32(ARMED, BUFS[1])
    eb = rb.press(2)
    check(armed == BUFS[0] and n1 == 1 and e1 is None and f1 == H2 and p1 == armed and rp.r32(tg["pd_mode"]) == 0
          and rp.r32(tg["ld_busy"]) == 0 and eb is not None,
          f"chargement raté (-1) : rien n'est envoyé au moteur audio (l'origine, elle, joue la note), pv_fail = "
          f"{H2:#010x}, pv_failp = le son désigné de cet appui ({armed:#x}), pd_mode = ld_busy = 0")
    check(n2 == 1 and e2 is None, "deuxième appui sur le même son désigné : pas de nouvel essai, rien n'est envoyé")
    check(len(rp.ui) == 2 and rp.ui[0] == rb.ui[0] and rp.regs_after == CALLEE_VALS and rp.clean(),
          "le reste de l'appui se déroule comme à l'origine (même message à l'interface), d2-d7/a2-a6 gardés")
    lock = named(TRACK_SOUNDS[2], H2)                         # un sample lock du Sound Pool : le même sample
    a4, np4 = rp.pool_arm(lock)
    f4 = rp.r32(s["pv_fail"])
    e4 = rp.press(2)
    check(a4 == BUFS[1] and rp.mem(a4, 100) == lock and np4 == 0 and f4 == H2 and len(rp.loads) == 2
          and rp.loads[1][0] == H2 and e4 is None
          and rp.r32(s["pv_failp"]) == BUFS[1] and rp.clean(),
          f"le même sample désigné à nouveau par le Sound Pool (vrai chemin pool de 0x400a63ac, sans pv_parse : "
          f"pv_fail reste {H2:#010x}) : autre tampon ({BUFS[1]:#x} != pv_failp), le chargement est retenté ; raté "
          f"encore, pv_failp = {BUFS[1]:#x}, rien n'est envoyé")
    a5, _ = rp.pool_arm(lock)
    a6, _ = rp.pool_arm(lock)
    e6 = rp.press(2)
    check(a5 == BUFS[0] and a6 == BUFS[1] and len(rp.loads) == 2 and e6 is None,
          "limite voulue : deux défilements du pool sans appui ramènent le tampon de l'échec (même adresse, même "
          "empreinte) : pas de nouvel essai, rien n'est envoyé, jusqu'au prochain son désigné par le navigateur")
    a7 = rp.browse(1)                                         # un preset, dans le navigateur de fichiers
    f7, np7 = rp.r32(s["pv_fail"]), len(rp.calls[s["pv_parse"]])
    rp.browse(3)
    rp.loader = lambda h: 9
    e8 = rp.press(2)
    check(rp.mem(a7, 100) == PRESET and f7 == 0 and np7 == 2 and len(rp.loads) == 3 and rp.loads[2][0] == H2
          and e8 is not None and struct.unpack_from(">I", e8, 52)[0] == rp.r32(ARMED),
          "le navigateur désigne un preset (pv_parse, original appelé) : pv_fail remis à zéro ; puis le fichier "
          "raté, revenu dans le tampon même de l'échec (= pv_failp) : le chargement est retenté, réussi, la note part")
    rp2 = Rig(v, v.img)
    rp2.uc.mem_write(BUFS[1], named(TRACK_SOUNDS[2], H1))
    rp2.w32(ARMED, BUFS[1])
    rp2.w32(s["pv_fail"], H2)
    rp2.w32(s["pv_failp"], BUFS[1])
    rp2.press(2)
    check(len(rp2.loads) == 1 and rp2.loads[0][0] == H1,
          "même tampon désigné que l'échec (pv_failp) mais un autre sample (preset du Sampler, case du pool) : "
          "pv_fail ne bloque que l'empreinte ratée, le chargement est essayé")
    # (d) chargeur occupé, (e) niveau d'interruption
    rp = note_rig(v, v.img, snd, busy=1)
    ep = rp.press(2)
    check(ep is None and not rp.loads and rp.r32(s["pv_fail"]) == 0 and rp.r32(tg["ld_busy"]) == 1
          and rp.r32(tg["pd_mode"]) == 0 and rp.sr_after & 0xff00 == 0x2000 and rp.regs_after == CALLEE_VALS,
          "chargeur de Model-TG occupé (ld_busy = 1) : pas d'essai, rien n'est envoyé, pv_fail inchangé, ld_busy "
          "toujours 1")
    for sr in (0x2700, 0x2300):
        rp = note_rig(v, v.img, snd)
        ep = rp.press(2, sr=sr)
        check(ep is None and not rp.loads and rp.r32(s["pv_fail"]) == 0 and rp.r32(tg["ld_busy"]) == 0
              and rp.sr_after & 0xff00 == sr and rp.regs_after == CALLEE_VALS,
              f"appui au niveau d'interruption {sr >> 8 & 7} : pas d'essai (le chargeur attend la carte), rien "
              f"n'est envoyé, pv_fail et ld_busy inchangés")
    # (f) hors du cas de l'écoute d'un sample : identique à l'origine
    cases = [("source 0x80", dict(src=0x80)), ("source 0x10", dict(src=0x10)), ("source 0x04", dict(src=0x04)),
             ("source 0x01", dict(src=0x01)), ("pas tenus (sans envoi = 1)", dict(held=1)),
             ("autre piste que l'active", dict(t=3)), ("rien de désigné", dict(armed=None)),
             ("son désigné : preset TONE nommé SMP…", dict(armed=sound(4, smp(H2), 0x31))),
             ("son désigné : Sampler sans « SMP »", dict(armed=sound(SAMPLER, b"Bass", 0x31))),
             ("son désigné : Sampler, hexadécimal en minuscules", dict(armed=sound(SAMPLER, b"SMP0badf00d", 0x31)))]
    for desc, kw in cases:
        a = kw.get("armed", snd)
        rb, rp = note_rig(v, v.base, a), note_rig(v, v.img, a)
        t = kw.get("t", 2)
        eb = rb.press(t, src=kw.get("src", 0x40), held=kw.get("held", 0))
        ep = rp.press(t, src=kw.get("src", 0x40), held=kw.get("held", 0))
        check(ep == eb and not rp.loads and rp.regs_after == rb.regs_after == CALLEE_VALS and rp.d0 == rb.d0
              and rp.ui == rb.ui and rp.clean() and rb.clean(),
              f"{desc} : identique à l'origine (événement {'envoyé' if eb else 'non envoyé'}, aucun chargement)")


# --- 4. moteur audio ------------------------------------------------------------------------------------------------
def preview_writes(wb, t, ptr, snd):
    """Les écritures attendues du modifié, pendant une passe de la boucle des événements, pour une note d'écoute d'un
    son du Sampler sur la piste t : celles de l'origine wb, où l'effacement de CUR_SNDS[t] devient ptr, suivi des 25
    mots du son copiés dans ptr. None si l'origine n'efface pas CUR_SNDS[t] exactement une fois."""
    cur = CUR_SNDS + 4 * t
    at = [i for i, w in enumerate(wb) if w == (cur, 4, 0)]
    if len(at) != 1:
        return None
    copy = [(ptr + 4 * k, 4, struct.unpack_from(">I", snd, 4 * k)[0]) for k in range(25)]
    return wb[:at[0]] + [(cur, 4, ptr)] + copy + wb[at[0] + 1:]


def audio_tests(v, pvt):
    tg = v.tgs
    for t in range(6):
        st, low, cur, keep, locks, masks, wr, clean = {}, {}, {}, {}, {}, {}, {}, True
        snd = sound(SAMPLER, smp(H2), 0x40 + t)
        for name, img in (("origine", v.base), ("modifié", v.img)):
            r = Rig(v, img, track=t)
            r.post_real = True
            r.w32(tg["slot_hash"] + 4 * PV_SLOT, H2)            # le sample écouté est en mémoire
            r.uc.mem_write(BUFS[1], snd)
            r.w32(ARMED, BUFS[1])
            r.press(t)
            r.press((t + 1) % 6, note=62)                       # une note normale sur une autre piste, même passe
            del r.low[:]
            masks[name] = r.run()
            st[name], low[name], wr[name] = r.ev_state(), list(r.low), r.writes
            cur[name] = r.r32(CUR_SNDS + 4 * t)
            keep[name] = r.mem(cur[name], 100) if cur[name] else None
            r.uc.reg_write(mk.UC_M68K_REG_D2, t)
            r.call(SP_LOCK)
            locks[name] = r.lock(t)
            clean &= r.clean()
        d = diff_words(st["origine"], st["modifié"], r)
        both = (1 << t) | (1 << (t + 1) % 6)
        check(masks["origine"] == masks["modifié"] == both and cur["origine"] == 0 and cur["modifié"] == pvt[t]
              and keep["modifié"] == snd and d == [CUR_SNDS + 4 * t] and clean
              and wr["modifié"] == preview_writes(wr["origine"], t, pvt[t], snd),
              f"piste {t + 1}, note d'écoute d'un son du Sampler (+ une note normale piste {(t + 1) % 6 + 1}) : "
              f"origine CUR_SNDS = 0 ; modifié CUR_SNDS = pv_b{t} ({pvt[t]:#x}) qui porte ses 100 o ; seule "
              f"différence de l'état ; écritures de la passe ({len(wr['origine'])} à l'origine, hors pile) : les "
              f"mêmes, dans le même ordre, l'effacement devenu pv_b{t} suivi des 25 mots de la copie")
        check(any(a == 0x60 for _, a in low["origine"]) and not low["modifié"],
              f"piste {t + 1} : l'origine lit l'adresse 0x60 (son effacé, lu en "
              f"{' '.join(sorted({hex(p) for p, _ in low['origine']}))}), le modifié ne touche pas la page 0")
        check(locks["origine"] == (OWN_SLOT, 0) and locks["modifié"] == (PV_SLOT, 1),
              f"piste {t + 1}, sp_lock à cette note : origine case {locks['origine'][0]} (le sample de la piste), "
              f"modifié case {locks['modifié'][0]} (le sample écouté), track_lock = {locks['modifié'][1]}")
    # note normale qui suit, son qui n'est pas du Sampler, notes normales sur les six pistes
    for desc, snd in (("son d'écoute qui n'est pas du Sampler (preset TONE)", sound(4, b"Tone preset", 0x51)),
                      ("aucun son désigné (notes normales)", None)):
        same, clean, n = True, True, 0
        for t in range(6):
            st, low, wr = {}, {}, {}
            for name, img in (("origine", v.base), ("modifié", v.img)):
                r = Rig(v, img, track=t)
                r.post_real = True
                if snd:
                    r.uc.mem_write(BUFS[1], snd)
                r.w32(ARMED, BUFS[1] if snd else 0)
                r.press(t)
                mask = r.run()
                st[name], low[name], wr[name] = r.ev_state(), r.low, r.writes
                clean &= r.clean() and mask is not None and bool(mask >> t & 1)
            same &= (st["origine"] == st["modifié"] and low["origine"] == low["modifié"]
                     and wr["origine"] == wr["modifié"])
            n += len(wr["origine"])
        check(same and clean, f"{desc}, pistes 1 à 6 : état de la boucle des événements identique à l'origine "
                              f"(sons des notes, 66 o, notes, retrig ; mêmes accès à la page 0) ; mêmes écritures, "
                              f"dans le même ordre ({n} en tout, hors pile)")
    st, locks, wr, cost = {}, {}, {}, {}
    snd = sound(SAMPLER, smp(H2), 0x61)
    for name, img in (("origine", v.base), ("modifié", v.img)):
        r = Rig(v, img, track=2)
        r.post_real = True
        r.w32(tg["slot_hash"] + 4 * PV_SLOT, H2)
        r.uc.mem_write(BUFS[1], snd)
        r.w32(ARMED, BUFS[1])
        r.press(2)
        m1 = r.run()
        w1, c1 = r.writes, r.icount
        r.uc.reg_write(mk.UC_M68K_REG_D2, 2)
        r.call(SP_LOCK)                                     # ce que fait la voix du Sampler à cette note
        l1 = r.lock(2)
        r.w32(ARMED, 0)
        r.now += 10_000
        r.press(2, note=62)
        m2 = r.run()
        wr[name], cost[name] = (w1, r.writes), (c1, r.icount)
        st[name] = (r.ev_state(), r.r32(CUR_SNDS + 8), r.mem(TARGETS + 132, 66), m1, m2)
        r.uc.reg_write(mk.UC_M68K_REG_D2, 2)
        r.call(SP_LOCK)
        locks[name] = (l1, r.lock(2), r.clean())
    o, m = st["origine"], st["modifié"]
    check(o == m and m[1] == KIT + 28 + 200 and m[2] == TRACK_SOUNDS[2][20:86] and m[3] == m[4] == 1 << 2
          and locks["origine"] == ((OWN_SLOT, 0), (OWN_SLOT, 0), True)
          and locks["modifié"] == ((PV_SLOT, 1), (OWN_SLOT, 0), True)
          and wr["modifié"][0] == preview_writes(wr["origine"][0], 2, pvt[2], snd)
          and wr["modifié"][1] == wr["origine"][1],
          "note normale après l'écoute : le son du kit est recopié (CUR_SNDS = son de la piste, ses 66 o), état "
          "identique à l'origine, mêmes écritures ; sp_lock quitte la case écoutée et revient au sample de la piste "
          "(track_lock = 0)")
    (pb, nb), (pm, nm) = cost["origine"], cost["modifié"]
    print(f"  coût  une passe de la boucle des événements de l'interruption audio, piste 3 : note d'écoute d'un son "
          f"du Sampler {pb} -> {pm} instructions ({pm - pb:+d}), note normale {nb} -> {nm} ({nm - nb:+d})")
    # source 0x80 : l'OS emporte aussi le son désigné (0x400813e2), pv_note ne charge rien pour elle
    res = {}
    snd = sound(SAMPLER, smp(H2), 0x81)                     # H2 n'est dans aucune case
    for name, img in (("origine", v.base), ("modifié", v.img)):
        r = Rig(v, img, track=2)
        r.post_real = True
        r.uc.mem_write(BUFS[1], snd)
        r.w32(ARMED, BUFS[1])
        r.w32(PL_DIRTY, 0)
        r.press(2, src=0x80)
        ev = r.posted[-1] if r.posted else None
        mask = r.run()
        cur = r.r32(CUR_SNDS + 8)
        lvl = r.listen(mask or 0)
        res[name] = dict(ev=ev, loads=list(r.loads), mask=mask, cur=cur, lock=r.lock(2), dirty=r.r32(PL_DIRTY),
                         lvl=lvl, clean=r.clean())
    o, m = res["origine"], res["modifié"]
    check(o["ev"] is not None and m["ev"] == o["ev"] and struct.unpack_from(">I", m["ev"], 52)[0] == BUFS[1]
          and not o["loads"] and not m["loads"] and o["mask"] == m["mask"] == 1 << 2 and o["cur"] == 0
          and m["cur"] == pvt[2] and o["lock"] == m["lock"] == (OWN_SLOT, 0) and o["dirty"] == 0
          and m["dirty"] == 1 and o["lvl"] > 1e7 and m["lvl"] > 1e7 and o["clean"] and m["clean"],
          f"source 0x80 (pas les pads ni les touches, mais l'OS lui fait emporter le son désigné, 0x400813e2), "
          f"sample désigné absent de la mémoire : pv_note ne charge rien et laisse partir la note (+52 = le son "
          f"désigné, comme l'origine) ; pv_copy la transmet (CUR_SNDS = pv_b2) ; sp_lock ne trouve pas le sample : "
          f"la voix joue le sample de la piste (case {m['lock'][0]}, sortie {m['lvl']:+.2e}, comme l'origine "
          f"{o['lvl']:+.2e}) et lève pl_dirty (le préchargeur de Model-TG refait un tour des samples des patterns, "
          f"dont celui-ci ne fait pas partie)")
    # pv_copy seul : contrat de registres, pistes hors de 0..5 (pv_tab[6] et [7] seraient pv_fail et pv_failp)
    for d2 in (6, 7):
        r = Rig(v, v.img)
        ev = FIX + 0x30000
        r.uc.mem_write(ev, bytes(80))
        r.w32(ev + 48, BUFS[1])
        r.uc.mem_write(BUFS[1], sound(SAMPLER, smp(H2), 0x71))
        marks = (FIX + 0x38000, FIX + 0x38800)              # en mémoire : une copie s'y verrait
        r.w32(v.pvs["pv_fail"], marks[0])
        r.w32(v.pvs["pv_failp"], marks[1])
        r.uc.mem_write(marks[0], b"\x5a" * 0x1000)
        lo, hi = min(pvt + [v.pvs["pv_tab"]]), max(pvt) + 100

        def snap():
            return r.mem(lo, hi - lo), r.mem(0, 0x1000), r.mem(marks[0], 0x1000)
        before = snap()
        cur = 0x800015a0 + (147 + d2) * 4
        r.w32(cur, 0x12345678)
        for reg, val in ((mk.UC_M68K_REG_A2, ev), (mk.UC_M68K_REG_D2, d2), (mk.UC_M68K_REG_A4, 0x800015a0)):
            r.uc.reg_write(reg, val)
        seen, writes, err = [], [], None
        del r.low[:]

        def at(uc, a, size, ud):
            seen.append([uc.reg_read(x) for x in CALLEE])

        def wr_(uc, access, addr, size, value, ud):
            writes.append((addr, size, value & ((1 << 8 * size) - 1)))
        hooks = [r.uc.hook_add(UC_HOOK_CODE, at, begin=v.pvs["pv_copy"], end=v.pvs["pv_copy"]),
                 r.uc.hook_add(UC_HOOK_MEM_WRITE, wr_)]
        sp = CALL_SP - 4
        r.uc.mem_write(sp, struct.pack(">I", STOP))
        r.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        try:
            r.uc.emu_start(v.pvs["pv_copy"], STOP, count=1000)
        except UcError as ex:
            err = f"{ex} en {r.uc.reg_read(mk.UC_M68K_REG_PC):#x}"
        for h in hooks:
            r.uc.hook_del(h)
        regs = [r.uc.reg_read(x) for x in CALLEE]
        check(err is None and r.uc.reg_read(mk.UC_M68K_REG_PC) == STOP and writes == [(cur, 4, 0)] and not r.low
              and snap() == before and seen and seen[0] == regs and r.uc.reg_read(mk.UC_M68K_REG_A7) == sp + 4,
              f"pv_copy seul, piste {d2 + 1} (hors de 0..5 ; pv_tab[{d2}] serait {('pv_fail', 'pv_failp')[d2 - 6]}, "
              f"posé à une adresse témoin) : une seule écriture, l'effacement d'origine de CUR_SNDS ; aucune copie, "
              f"page 0, pv_tab, copies et témoin intacts ; d2-d7/a2-a6 et la pile rendus (seuls d0, d1, a0, a1 "
              f"servent){' ; ' + err if err else ''}")


# --- 5. de bout en bout ---------------------------------------------------------------------------------------------
def chain_tests(v):
    for t in (2, 5):
        res = {}
        for name, img in (("origine", v.base), ("modifié", v.img)):
            r = Rig(v, img, track=t)
            r.post_real, r.place = True, True
            r.loader = lambda h: PV_SLOT
            r.w32(ACTIVE, t)
            r.w32(ARMED, 0)
            for _ in range(4):
                r.e.block(0)
            armed = r.browse(0)                                 # 2 Mo, empreinte H1, pas en mémoire
            r.press(t)
            mask = r.run()
            cur = r.r32(CUR_SNDS + 4 * t)
            lvl = r.listen(mask or 0)
            lk = r.lock(t)
            r.w32(ARMED, 0)
            r.now += 50_000
            r.press(t, note=62)
            mask2 = r.run()
            cur2 = r.r32(CUR_SNDS + 4 * t)
            lvl2 = r.listen(mask2 or 0)
            res[name] = dict(armed=armed, loads=list(r.loads), mask=mask, cur=cur, lvl=lvl, lock=lk, mask2=mask2,
                             cur2=cur2, lvl2=lvl2, lock2=r.lock(t), clean=r.clean(), low=r.low)
        o, m = res["origine"], res["modifié"]
        check(o["armed"] == 0 and not o["loads"] and o["mask"] == 1 << t and o["lvl"] > 1e7
              and o["lock"] == (OWN_SLOT, 0),
              f"origine, piste {t + 1} : le navigateur ne désigne rien, le pad joue le sample de la piste "
              f"(sortie moyenne {o['lvl']:+.2e})")
        check(m["armed"] in BUFS and m["loads"] == [(H1, 1, 1, 0)] and m["mask"] == 1 << t
              and m["cur"] == struct.unpack(">I", v.img[v.pvs["pv_tab"] - BASE + 4 * t:][:4])[0]
              and m["lock"] == (PV_SLOT, 1) and m["lvl"] < -1e7,
              f"modifié, piste {t + 1} : navigateur (« {smp(H1).decode()} ») -> pad : chargé (pd_mode 1), "
              f"note transmise (CUR_SNDS = pv_b{t}), la vraie boucle des voix joue le sample écouté "
              f"(case {m['lock'][0]}, sortie moyenne {m['lvl']:+.2e})")
        check(o["mask2"] == m["mask2"] == 1 << t and o["cur2"] == m["cur2"] == KIT + 28 + 100 * t
              and o["lock2"] == m["lock2"] == (OWN_SLOT, 0) and o["lvl2"] > 1e7 and m["lvl2"] > 1e7,
              f"note normale suivante : les deux jouent le sample de la piste (origine {o['lvl2']:+.2e}, modifié "
              f"{m['lvl2']:+.2e}), CUR_SNDS = son du kit")
        check(o["clean"] and m["clean"] and not m["low"] and all(a == 0x60 for _, a in o["low"]),
              f"aucun accès hors mémoire ; page 0 : origine {len(o['low'])} lecture(s) de 0x60, modifié aucune")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", required=True)
    ap.add_argument("--with", dest="others", default="",
                    help="autres tweaks appliqués avant (ex. 6ch-usbup,model-tg-st,syntakt-tg-sd-cp-toy-bits-swarm)")
    ap.add_argument("--syntakt", help="Syntakt_OS1.42.syx (ou 1.41), pour les moteurs du Syntakt")
    args = ap.parse_args()
    stock = T.main_os_from_syx(args.cycles)
    by_id = {json.loads(f.read_text(encoding="utf-8"))["id"]: f for f in TW.glob("[0-9]*.json")}
    others = [i for i in args.others.split(",") if i]
    if "model-tg" in others or "model-tg-st" in others:
        sets = [others]
    else:                                       # Model-TG seul par défaut ; les deux versions avec --syntakt
        sets = [others + ["model-tg"]] + ([others + ["model-tg-st"]] if args.syntakt else [])
    for ids in sets:
        v = Variant(stock, ids, by_id, args.syntakt)
        print(f"\n== origine : {v.label} ; modifié : + {v.pv['id']}")
        print("1. écritures")
        pvt = writes_tests(stock, v)
        print("2. navigateur")
        browser_tests(v)
        print("3. note jouée")
        note_tests(v)
        print("4. moteur audio")
        audio_tests(v, pvt)
        print("5. de bout en bout : navigateur, pad, boucle des événements, boucle des voix")
        chain_tests(v)
    print("\nTOUT OK" if not FAIL else f"\n{len(FAIL)} ÉCHEC(S)")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
