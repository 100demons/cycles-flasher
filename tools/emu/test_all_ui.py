#!/usr/bin/env python3
import argparse,json,pathlib,struct,sys
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE)); sys.path.insert(0,str(HERE.parent))
import test_all as T
DEV=pathlib.Path(__file__).resolve().parent.parent.parent/'tweaks'/'model-cycles_OS1.13'
FAIL=[]
def check(ok,msg):
 print(('  ok    ' if ok else '  ECHEC ')+msg,flush=True)
 if not ok: FAIL.append(msg)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--cycles',required=True); a=ap.parse_args()
 stock=T.T.main_os_from_syx(a.cycles); tw=json.loads((DEV/'90-all.json').read_text()); fw=T.Fw(stock,tw); e=fw.engine
 try: e.uc.mem_map(0x40a70000,0x10000)
 except Exception: pass
 pat=bytes((i*7)&0xff for i in range(100))
 for d in (51,52,53): e.uc.mem_write(0x40a71754+100*d,pat)
 st=int(tw['symbols']['state_at'],16)
 for desc,name in [(77,'Feral SHAPE'),(82,'BLAST SHAPE'),(83,'BLAST SWEEP'),(87,'PUNCH SHAPE'),(88,'PUNCH SWEEP'),(96,'SAM COLOR'),(97,'SAM SHAPE'),(98,'SAM SWEEP'),(99,'SAM CONTOUR')]:
  p=e.call(st,desc)
  obj=e.uc.mem_read(p,100)
  same=obj[:0x20]==pat[:0x20] and obj[0x24:0x30]==pat[0x24:0x30] and obj[0x34:]==pat[0x34:]
  if not same:
   print('DIFF', name, [(i,obj[i],pat[i]) for i in range(100) if i not in range(0x20,0x24) and i not in range(0x30,0x34) and obj[i]!=pat[i]][:10])
  fn=struct.unpack('>I',obj[0x20:0x24])[0]; dr=struct.unpack('>I',obj[0x30:0x34])[0]
  print(name, hex(p), 'same',same,'fn',hex(fn),'dr',hex(dr),'obj',obj[:12].hex()); check(p not in (0x40a71754+100*51,0x40a71754+100*52,0x40a71754+100*53) and same and fn and dr, name+' uses its own state object')
 p=e.call(st,76); check(p==0x40a71754+100*51,'generic COLOR stays on SNARE state')
 print('\nTOUT OK' if not FAIL else f'\n{len(FAIL)} ECHEC(S)'); return 1 if FAIL else 0
if __name__=='__main__': sys.exit(main())
