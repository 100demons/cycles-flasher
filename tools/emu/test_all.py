#!/usr/bin/env python3
import argparse, json, pathlib, sys
import numpy as np
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE)); sys.path.insert(0,str(HERE.parent))
import build, mcengine as E, test_sdvintage as T
DEV=pathlib.Path(__file__).resolve().parent.parent.parent/'tweaks'/'model-cycles_OS1.13'
FAIL=[]
def check(ok,msg):
    print(('  ok    ' if ok else '  ECHEC ')+msg,flush=True)
    if not ok: FAIL.append(msg)
class Fw:
    def __init__(self,stock,tweak):
        p,_=build.apply_writes(stock,[tweak]); pl,_=build.build_payload([tweak],stock,None)
        self.img=bytes(p)+pl; self.pay=int(tweak['append']['dest'],16); self.rt=build.payload_runtime(tweak,stock,None)
        self.engine=E.Engine(self.img,payload=(self.pay,self.rt))
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--cycles',required=True); a=ap.parse_args()
    stock=T.main_os_from_syx(a.cycles); tw=json.loads((DEV/'90-all.json').read_text())
    fw=Fw(stock,tw); e=fw.engine
    e.uc.mem_map(0x40800000,0x01800000)  # OS BSS incl. trig velocity at 0x40fe4cdc
    check(not e.unmapped,'voice loop starts, no unmapped access')
    base=dict(note=36,pitch=64,finetune=64,gate=0,punch=0,decay=50)
    for idx,name in [(6,'Feral'),(7,'BLAST'),(8,'BLAM'),(9,'LiXR'),(10,'SAM')]:
        e.set(0,machine=idx,color=64,shape=64,sweep=64,contour=48,**base)
        try:
            x=np.stack([e.block(1 if b in (1,120) else 0) for b in range(220)])[:,0]
        except Exception as exc:
            print('FAULT', name, exc, e.unmapped[-5:])
            raise
        y=x/2147483648.0; peak=int(np.abs(x).max()); rms=float(np.sqrt(np.mean(y*y)))
        check(peak>1000000 and not e.unmapped,f'{name}: sound (peak {peak}, rms {rms:.3f})')
        check(peak<0x7ffffff0,f'{name}: no hard clip')
    e.set(0,machine=0,color=64,shape=64,sweep=64,contour=64,**base)
    x=np.stack([e.block(1 if b in (1,120) else 0) for b in range(160)])[:,0]
    check(int(np.abs(x).max())>1000000 and not e.unmapped,'stock KICK still plays')
    print('\nTOUT OK' if not FAIL else f'\n{len(FAIL)} ECHEC(S)')
    return 1 if FAIL else 0
if __name__=='__main__': sys.exit(main())
