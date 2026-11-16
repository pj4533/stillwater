#!/usr/bin/env python3
"""Actual production pixels and fixed-control real-native musical evidence."""
import ctypes as C
from dataclasses import replace
import hashlib,json,sys,tempfile,time
from pathlib import Path
from PIL import Image,ImageOps,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,Layer
from loop_engine import LoopEngine
from loop_app import LoopInstrument
from loop_graphics import render,material,background,music_pose
from material_controls import protected_boxes,position
from roles import ROLE_IDS,DEFAULTS
from graphics import Canvas

def image(raw):return Image.frombytes('RGB',(1024,160),raw,'raw','RGB;16').crop((0,0,960,160))
def support_detail(out):
 """Native GIF pixels enlarged without smoothing for targeted music review."""
 sheet=Image.new('RGB',(512,1104),(8,13,12));d=ImageDraw.Draw(sheet)
 for row,(role,value) in enumerate((('prism','0'),('filament','0'),('spore','0'),('choir','100'))):
  gif=Image.open(out/(role+'-'+value+'-fixed-music.gif'))
  d.text((6,row*276+3),role+' '+value+'% / frames0 and8',fill=(230,230,210))
  for column,n in enumerate((0,8)):
   gif.seek(n);crop=gif.convert('RGB').crop((28,48,92,112))
   sheet.paste(crop.resize((256,256),Image.Resampling.NEAREST),(column*256,row*276+20))
 sheet.save(out/'music-support-detail.png')

def main():
 out=ROOT/'.build/v5-preview';out.mkdir(parents=True,exist_ok=True)
 sheet=Image.new('RGB',(960*7,160*8));masked=sheet.copy();objects=Image.new('RGB',(960*7,64*8));before=Image.new('RGB',(960*3,160*16));timings=[];motion={}
 with tempfile.TemporaryDirectory() as temp:
  m=LoopModel(Path(temp)/'current-v3.json',writer=False);e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int];i=LoopInstrument(m,e);pcm=(C.c_float*8820)()
  def audio(n=4410):e.lib.sw_render(pcm,n)
  def frame():
   t=time.perf_counter();raw=render(m,e.stats(),i);timings.append((time.perf_counter()-t)*1000);return image(raw)
  for ri,role in enumerate(ROLE_IDS):
   m.state=replace(m.state,layers=(Layer(1,role,sound_version=2),),role_order=(role,)+tuple(r for r in ROLE_IDS if r!=role))
   for col,(name,params) in enumerate([(str(round(v*100)),(v,)*8) for v in (0,.25,.5,.75,1)]+[('mixed',(0,.15,.3,.45,.6,.75,.9,1)),('defaults',DEFAULTS[ri])]):
    m.state=replace(m.state,layers=(replace(m.state.layers[0],parameters=params),));e.lib.sw_reset();e.generation=0;e.publish(m.state,1);audio(1)
    im=frame();im.save(out/(role+'-'+name+'.png'));sheet.paste(im,(col*960,ri*160));hide=im.copy();hide.paste((7,14,13),(0,139,960,160));masked.paste(hide,(col*960,ri*160));objects.paste(im.crop((0,48,960,112)),(col*960,ri*64))
    if name in ('0','50','100'):
     j=('0','50','100').index(name);before.paste(im,(j*960,(ri*2+1)*160))
     old=ROOT/'.build/v4-preview'/(role+'-'+name+'.png')
     if old.exists():before.paste(Image.open(old),(j*960,ri*2*160))
    clips=[];regions=[];envs=[];protection=[];samples=[];audio_poses=[set() for _ in range(8)];changed=[0]*8;initial=[]
    # Fixed controls throughout. Per-role alternating note spacing, not knobs.
    on_frames=(5,27+ri%3*2);off_frames=(19,44+ri%3*2)
    for n in range(125):
     if n in on_frames:e.check(e.lib.sw_performance_on(0,n+1,0,50+ri%4*3,.65,0,1,n+1))
     if n in off_frames:
      on=on_frames[off_frames.index(n)];e.check(e.lib.sw_performance_off(0,on+1))
     if n==100:e.transport(0,False,1)
     audio();stats=e.stats();im=frame();regions.append(im.crop((0,48,960,112)).tobytes());envs.append(max(stats['envelopes'][0],stats['fx'][0][0]));samples.append(stats['loop']['sample'])
     protected=bytearray()
     for column,v in enumerate(params):
      for x0,y0,x1,y1 in protected_boxes(role,v):protected.extend(im.crop((column*120+28+x0,48+y0,column*120+29+x1,49+y1)).tobytes())
     protection.append(hashlib.sha256(protected).hexdigest())
     for column in range(8):
      crop=im.crop((column*120+28,48,column*120+92,112))
      if n==0:initial.append(crop)
      if n in (15,30,45,60):changed[column]=max(changed[column],sum(pixel!=(0,0,0) for pixel in ImageChops.difference(crop,initial[column]).getdata()))
      aux=stats['fx'][0][1 if ri>=2 else 2]
      audio_poses[column].add(music_pose(role,column,envs[-1],aux,samples[-1]/44100))
     if name in ('0','50','100','mixed','defaults') and n<75:clips.append(im)
    data=dict(parameters=list(params),envelope_min=min(envs),envelope_max=max(envs),sounding_distinct=len(set(regions[5:50])),silent_distinct=len(set(regions[:5])),settled_distinct=len(set(regions[-5:])),protected_distinct=len(set(protection)),settled_envelope=envs[-1],sample_progress=samples[-1]-samples[0],stop_frame=100,audio_pose_diversity=[len(p) for p in audio_poses],changed_material_pixels=changed)
    motion[role+'-'+name]=data
    assert data['silent_distinct']==1 and data['protected_distinct']==1,(role,name,data)
    assert data['sounding_distinct']>1,(role,name,data)
    assert data['settled_distinct']==1,(role,name,data)
    if clips:
     palette=clips[0].quantize(colors=256)
     sampled=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in clips[::3]]
     sampled[0].save(out/(role+'-'+name+'-fixed-music.gif'),save_all=True,append_images=sampled[1:],duration=300,loop=0,optimize=True)
   print(role,flush=True)
  for page in ('overview','mixer','key','library','recordings','instrument'):
   i.open_page(page);frame().save(out/(page+'.png'));i.help=True;frame().save(out/(page+'-help.png'));i.help=False
 sheet.save(out/'range-contact.png');sheet.crop((4800,0,5760,1280)).save(out/'quick-mixed.png');masked.save(out/'range-contact-masked.png');objects.save(out/'material-only.png');ImageOps.grayscale(objects).save(out/'material-only-gray.png');before.save(out/'v4-v5-storyboard.png')
 support_detail(out)
 timings.sort();report=dict(scope='Production renderer and ABI5 native PCM, fixed controls, container only',frames=len(timings),render_mean_ms=sum(timings)/len(timings),render_p99_ms=timings[round((len(timings)-1)*.99)],render_max_ms=max(timings),motion=motion)
 (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='motion'}))
if __name__=='__main__':main()
