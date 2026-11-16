#!/usr/bin/env python3
"""Production renderer/native-audio visual review, 960x160 at native scale."""
import ctypes as C
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import time
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,Event,Layer
from loop_engine import LoopEngine
from loop_app import LoopInstrument
from loop_graphics import render
from roles import ROLE_IDS,DEFAULTS

def image(raw):
 return Image.frombytes('RGB',(1024,160),raw,'raw','RGB;16').crop((0,0,960,160))
def main():
 out=ROOT/'.build/v3-preview';out.mkdir(parents=True,exist_ok=True);timings=[];contact=[];motion={}
 with tempfile.TemporaryDirectory() as home:
  m=LoopModel(Path(home)/'current-v3.json',writer=False);e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  for role in ROLE_IDS:
   e.lib.sw_reset();e.generation=0
   order=(role,)+tuple(r for r in ROLE_IDS if r!=role)
   m.state=replace(m.state,role_order=order,layers=(replace(m.state.layers[0],role=role,parameters=DEFAULTS[ROLE_IDS.index(role)],events=(Event(1,50,.6,0,96000),)),));m.capture_epoch=1
   i=LoopInstrument(m,e);pcm=(C.c_float*(4410*2))();e.lib.sw_render(pcm,1)
   frames=[]
   for playing in (False,True):
    if playing:e.transport(2,True,m.capture_epoch)
    for n in range(32):
     value=.05+.9*(n/31);m.state=replace(m.state,layers=(replace(m.state.layers[0],parameters=(value,)*8),))
     for p in range(8):e.lib.sw_layer_parameter(0,p,value)
     e.lib.sw_render(pcm,4410)
     stats=e.stats();started=time.monotonic();raw=render(m,stats,i);timings.append((time.monotonic()-started)*1000);im=image(raw);frames.append(im)
     if n in (0,31):im.save(out/(role+('-playing' if playing else '-silent')+('-low' if n==0 else '-high')+'.png'))
   frames[0].save(out/(role+'.gif'),save_all=True,append_images=frames[1:],duration=100,loop=0)
   contact.append(image(render(m,e.stats(),i)))
   # Separate real-audio evidence: every knob is held fixed. These are native
   # playback voices, not injected telemetry or a time-only render animation.
   e.transport(0,False,m.capture_epoch);e.lib.sw_render(pcm,4410)
   m.overdub=False
   fixed=replace(m.state.layers[0],parameters=(.5,)*8,events=(Event(1,50,.8,0,360000),))
   m.state=replace(m.state,layers=(fixed,));e.publish(m.state,m.capture_epoch)
   for _ in range(12):e.lib.sw_render(pcm,4410)
   fixed_frames=[];material_frames=[];energies=[]
   for n in range(112):
    if n==24:e.transport(2,False,m.capture_epoch)
    if n==88:e.transport(0,False,m.capture_epoch)
    e.lib.sw_render(pcm,4410);stats=e.stats()
    started=time.monotonic();raw=render(m,stats,i);timings.append((time.monotonic()-started)*1000)
    im=image(raw);fixed_frames.append(im)
    material_frames.append(im.crop((0,48,960,112)).tobytes())
    energies.append(max(stats['envelopes'][0],stats['fx'][0][0]))
   fixed_frames[0].save(out/(role+'-fixed-silent.png'))
   differences=[sum(a!=b for a,b in zip(material_frames[0],frame)) for frame in material_frames]
   most=max(range(24,88),key=lambda n:differences[n])
   fixed_frames[most].save(out/(role+'-fixed-audition.png'))
   fixed_frames[0].save(out/(role+'-fixed-audio.gif'),save_all=True,append_images=fixed_frames[1:],duration=100,loop=0)
   motion[role]=dict(parameters=[.5]*8,frames=112,silent_frames=24,audition_frames=64,settle_frames=24,
                     max_native_energy=max(energies),audition_distinct_material_frames=len(set(material_frames[24:88])),
                     silent_distinct_material_frames=len(set(material_frames[:24])),
                     max_changed_rgb_bytes=max(differences),scope='960x64 material region; actual native playback and stopped audio')
  sheet=Image.new('RGB',(960,160*8))
  for n,im in enumerate(contact):sheet.paste(im,(0,n*160))
  sheet.save(out/'role-contact.png')
  # Sparse actual song: three roles and five empty slots, not eight copies of the selection.
  layers=tuple(Layer(n+1,r,.6,False,DEFAULTS[ROLE_IDS.index(r)],(Event(n+1,50+n*7,.7,n*96000,240000),)) for n,r in enumerate(('silt','choir','prism')))
  m.state=replace(m.state,layers=layers,role_order=('silt','choir','prism','filament','glass','oxide','backwash','spore'));m.selected=0
  e.publish(m.state,m.capture_epoch);e.transport(2,False,m.capture_epoch);e.lib.sw_render(pcm,4410)
  e.lib.sw_loop_tempo(61);e.lib.sw_render(pcm,4410)
  for view in ('overview','key','chooser','mixer'):
   m.view=view;image(render(m,e.stats(),i)).save(out/(view+'.png'))
  (out/'fixed-audio-motion.json').write_text(json.dumps(motion,indent=2)+'\n')
  (out/'render-timing.json').write_text(json.dumps(dict(scope='container aarch64; production renderer; native PCM telemetry; no hardware',frames=len(timings),mean_ms=sum(timings)/len(timings),max_ms=max(timings)),indent=2)+'\n')
if __name__=='__main__':main()
