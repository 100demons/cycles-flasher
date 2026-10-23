import json, pathlib, sys, tempfile, struct
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import compose, gen_macro as gm, gen_sdvintage_exact as gx, gen_sdvintage_7th as g7
import gen_syntakt_engines as gs
import gen_blast, gen_blam
import all_ui

def align4(x): return (x+3)&~3
def mdict(m, name, image=4):
    mc=m['_machine']; knobs=tuple((k['long'],k['short'],k['default'])+((k['min'],k['max']) if 'min' in k else ()) for k in mc['knobs'])
    return dict(name=name,image=image,decay=mc['decay_default'],knobs=knobs)

def unified_detours(text, fs, bs, ls):
    # fs/bs/ls: symbols of the Feral, BLAST and BLAM blobs (BLAST and BLAM use the same C names)
    def setv(name, syms, key): return f"\t.set {name}, {syms[key]:#x}"
    head = "\n".join([setv('FERAL_INIT', fs, 'feral_state_init'),
                      setv('BLAST_STATE_AT', bs, 'blast_state_at'), setv('BLAST_STATE_CONNECT', bs, 'blast_state_connect'),
                      setv('BLAST_TURN_HOOK', bs, 'blast_turn_hook'),
                      setv('BLAM_STATE_AT', ls, 'blast_state_at'), setv('BLAM_STATE_CONNECT', ls, 'blast_state_connect'),
                      setv('BLAM_TURN_HOOK', ls, 'blast_turn_hook')]) + "\n"
    dispatch_at = """
\tmove.l 4(%sp), %d0
\tcmp.l #77, %d0
\tbeq.w all_state_feral
\tcmp.l #82, %d0
\tbeq.w all_state_blast_shape
\tcmp.l #83, %d0
\tbeq.w all_state_blast_sweep
\tcmp.l #87, %d0
\tbeq.w all_state_blam_shape
\tcmp.l #88, %d0
\tbeq.w all_state_blam_sweep
"""
    dispatch_connect = """
\tmove.l 4(%sp), %d0
\tcmp.l #77, %d0
\tbeq.w all_connect_feral
\tcmp.l #82, %d0
\tbeq.w all_connect_blast_shape
\tcmp.l #83, %d0
\tbeq.w all_connect_blast_sweep
\tcmp.l #87, %d0
\tbeq.w all_connect_blam_shape
\tcmp.l #88, %d0
\tbeq.w all_connect_blam_sweep
"""
    stubs = """
all_state_feral:
\tjsr FERAL_INIT
\trts
all_state_blast_shape:
\tmove.l #77, -(%sp)
\tjsr BLAST_STATE_AT
\taddq.l #4, %sp
\trts
all_state_blast_sweep:
\tmove.l #78, -(%sp)
\tjsr BLAST_STATE_AT
\taddq.l #4, %sp
\trts
all_state_blam_shape:
\tmove.l #77, -(%sp)
\tjsr BLAM_STATE_AT
\taddq.l #4, %sp
\trts
all_state_blam_sweep:
\tmove.l #78, -(%sp)
\tjsr BLAM_STATE_AT
\taddq.l #4, %sp
\trts

all_connect_feral:
\tjsr FERAL_INIT
\taddi.l #0x14, %d0
\tpea 0x40a71500
\tmove.l 12(%sp), -(%sp)
\tmove.l %d0, -(%sp)
\tjsr 0x400ddf60
\tlea 12(%sp), %sp
\tmove.l #0x40a71500, %d0
\trts
all_connect_blast_shape:
\tmove.l #77, -(%sp)
\tjsr BLAST_STATE_CONNECT
\taddq.l #4, %sp
\trts
all_connect_blast_sweep:
\tmove.l #78, -(%sp)
\tjsr BLAST_STATE_CONNECT
\taddq.l #4, %sp
\trts
all_connect_blam_shape:
\tmove.l #77, -(%sp)
\tjsr BLAM_STATE_CONNECT
\taddq.l #4, %sp
\trts
all_connect_blam_sweep:
\tmove.l #78, -(%sp)
\tjsr BLAM_STATE_CONNECT
\taddq.l #4, %sp
\trts

all_turn_hook:
\tcmp.l #83, %d2
\tbne.s 1f
\tjmp BLAST_TURN_HOOK
1:
\tcmp.l #88, %d2
\tbne.s 2f
\tjmp BLAM_TURN_HOOK
2:
\tmove.l %d3, -(%sp)
\tmove.l %d0, -(%sp)
\tmove.l %d2, -(%sp)
\tjmp 0x4000b830
"""
    text = text.replace("\t.globl\tstate_at\nstate_at:\n", "\t.globl\tstate_at\nstate_at:\n" + dispatch_at, 1)
    text = text.replace("\t.globl\tstate_connect\nstate_connect:\n", "\t.globl\tstate_connect\nstate_connect:\n" + dispatch_connect, 1)
    return head + text + stubs

img=g7.cycles_main('firmware/model-cycles_OS1.13.syx')
gs.set_base(gs.PAY_ALONE); pay=gs.PAY_ALONE
fe=compose.load_manifest('feral9'); lx=compose.load_manifest('lixr')
with tempfile.TemporaryDirectory() as d:
    tmp=pathlib.Path(d)
    feral_at=align4(pay); feral_bss=align4(pay+gm.BSS_OFF)
    fb,fs,fend=compose.place_package(fe,feral_at,feral_bss,gs.STUBS,{'descriptor_base':76})
    blast_at=align4(feral_at+len(fb)); blast_bss=align4(fend)
    bb,bs,bend=gen_blast.compile_machine(tmp,blast_at,gen_blast.tables_header(),gen_blast.ui.icons_header(),bss_at=blast_bss,defs=("SHAPE_DESC=82","SWEEP_DESC=83"))
    blam_at=align4(blast_at+len(bb)); blam_bss=align4(bend)
    lb,ls,lend=gen_blam.compile_machine(tmp,blam_at,gen_blam.tables_header(),gen_blam.ui.icons_header(),bss_at=blam_bss,defs=("COLOR_DESC=86","SHAPE_DESC=87","SWEEP_DESC=88"))
    lixr_at=align4(blam_at+len(lb)); lixr_bss=align4(lend)
    xb,xs,xend=compose.place_package(lx,lixr_at,lixr_bss,gs.STUBS,{})
    ui_at=align4(lixr_at+len(xb))
    ub,us=all_ui.compile_ui(tmp,ui_at)
    syms={**fs,**bs,**ls,**xs}
    machines=[dict(mdict(fe,'Feral',image=6),update=fs['tiny2_update'],render=fs['tiny2_render']),
              dict(name='BLAST',image=7,decay=gen_blast.MACHINE['decay'],knobs=gen_blast.MACHINE['knobs'],update=bs['blast_update'],render=bs['blast_render']),
              dict(name='BLAM',image=8,decay=gen_blam.MACHINE['decay'],knobs=gen_blam.MACHINE['knobs'],update=ls['blast_update'],render=ls['blast_render']),
              dict(mdict(lx,'LiXR',image=9),update=xs['lixr_update'],render=xs['lixr_render'])]
    detsyms={}
    orig_assemble=gm.assemble
    def assemble_capture(tmp_, name, src, at, defs=()):
        if name=='det':
            src=all_ui.patch_detours(src,us)
            src=unified_detours(src,fs,bs,ls)
            pathlib.Path('/tmp/all_det.S').write_text(src)
        blob,sy=orig_assemble(tmp_,name,src,at,defs)
        if name=='det': detsyms.update(sy)
        return blob,sy
    old_assemble=gm.assemble; gm.assemble=assemble_capture
    try:
        writes,append=gm.added_machine(img,None,machines,tmp,[(feral_at,fb),(blast_at,bb),(blam_at,lb),(lixr_at,xb),(ui_at,ub)],xend)
    finally:
        gm.assemble=old_assemble
    writes += all_ui.site_writes(img,gm.BASE,detsyms)
    all_ui.clamp_writes(writes,gm.BASE)
    old=img[0x4000b82a-0x40000400:][:6]
    assert old.hex()=='2f032f002f02', old.hex()
    writes.append({'off':0x4000b82a-0x40000400,'old':old.hex(),'new':'4ef9'+f"{detsyms['all_turn_hook']:08x}"})
    writes.sort(key=lambda w:w['off'])
    for a,b in zip(writes,writes[1:]):
        assert a['off']+len(a['new'])//2 <= b['off'], (hex(a['off']),hex(b['off']))
    tweak=dict(id='all',order=90,name='All four machines',description=['One firmware with all four machines: Feral, Blast, Blam and LiXR.'],
               device='Model:Cycles',os='1.13',section=3,status='experimental',
               conflicts=['lixr','feral9','blast','blam'],writes=writes,append=append,
               symbols={**{k:f'{v:#x}' for k,v in syms.items() if k in ('tiny2_update','tiny2_render','blast_update','blast_render','lixr_update','lixr_render')}, **{k:f'{v:#x}' for k,v in detsyms.items() if k in ('state_at','state_connect','all_turn_hook')}})
    pathlib.Path('tweaks/model-cycles_OS1.13/90-all.json').write_text(json.dumps(tweak,indent=1)+'\n')
    print('wrote 90-all',len(writes),append['size'],append['dest'],'bss end',hex(xend),'turn',hex(detsyms['all_turn_hook']))
