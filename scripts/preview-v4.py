#!/usr/bin/env python3
"""Production V4 native-size range, management and real-audio visual evidence."""
import ctypes as C
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import time
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,Event,atomic_write
from loop_engine import LoopEngine
from loop_app import LoopInstrument
from loop_graphics import render
from library_manager import LibraryManager
from roles import ROLE_IDS

def image(raw):return Image.frombytes('RGB',(1024,160),raw,'raw','RGB;16').crop((0,0,960,160))
def main():
 out=ROOT/'.build/v4-preview';out.mkdir(parents=True,exist_ok=True);timings=[];motion={};sheet=Image.new('RGB',(960*5,160*8));masked=sheet.copy()
 with tempfile.TemporaryDirectory() as temp:
  home=Path(temp);m=LoopModel(home/'sessions/current-v3.json',writer=False);e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  manager=LibraryManager(home);i=LoopInstrument(m,e,manager=manager);pcm=(C.c_float*8820)()
  def audio():e.lib.sw_render(pcm,4410)
  def frame():
   started=time.monotonic();im=image(render(m,e.stats(),i));timings.append((time.monotonic()-started)*1000);return im
  for role_index,role in enumerate(ROLE_IDS):
   e.lib.sw_reset();e.generation=0;m.capture_epoch=1
   order=(role,)+tuple(r for r in ROLE_IDS if r!=role)
   m.state=replace(m.state,role_order=order,layers=(replace(m.state.layers[0],role=role,events=(Event(1,50,.8,0,360000),)),));i.open_page('instrument')
   e.publish(m.state,1);audio()
   for column,value in enumerate((0,.25,.5,.75,1)):
    m.state=replace(m.state,layers=(replace(m.state.layers[0],parameters=(value,)*8),));im=frame();im.save(out/(role+'-'+str(round(value*100))+'.png'))
    sheet.paste(im,(column*960,role_index*160));hidden=im.copy();hidden.paste((7,14,13),(0,139,960,160));masked.paste(hidden,(column*960,role_index*160))
   m.state=replace(m.state,layers=(replace(m.state.layers[0],parameters=(0,.15,.3,.45,.6,.75,.9,1)),));frame().save(out/(role+'-mixed.png'))
   m.state=replace(m.state,layers=(replace(m.state.layers[0],parameters=(.5,)*8),));e.publish(m.state,1);audio()
   frames=[];regions=[]
   for n in range(100):
    if n==20:e.transport(2,False,1)
    if n==75:e.transport(0,False,1)
    audio();im=frame();frames.append(im);regions.append(im.crop((0,48,960,112)).tobytes())
   frames[0].save(out/(role+'-fixed-audio.gif'),save_all=True,append_images=frames[1:],duration=100,loop=0)
   motion[role]=dict(silent_distinct=len(set(regions[:20])),playing_distinct=len(set(regions[20:75])),settled_distinct=len(set(regions[-5:])),parameters=[.5]*8)
  sheet.save(out/'range-contact.png');masked.save(out/'range-contact-masked.png')
  # Real saved envelopes in the bounded worker inventory, rather than mock rows.
  for n in range(6):atomic_write(manager.saved/('song-'+('%032x'%n)+'.json'),m.payload())
  i.open_page('library')
  deadline=time.monotonic()+3
  while i.manager_busy and time.monotonic()<deadline:i.management_tick();time.sleep(.005)
  frame().save(out/'library.png');i.management_event(22,127,0);frame().save(out/'rename.png');i.management_event(26,127,0)
  i.management_event(118,127,0);frame().save(out/'delete-loop.png');i.management_event(26,127,0)
  i.management_event(21,127,0);frame().save(out/'load-confirm.png')
  i.open_page('key');i.key_draft=[60,'minor'];frame().save(out/'key.png')
  i.open_page('recordings');frame().save(out/'recordings-off.png')
  manager.recordings.mkdir(exist_ok=True)
  import wave
  with wave.open(str(manager.recordings/'bottle-20261116-123456-012abc.wav'),'wb') as wav:wav.setparams((2,2,44100,0,'NONE',''));wav.writeframes(bytes(44100*4))
  i.record_tab='saved';i.refresh_manager()
  deadline=time.monotonic()+3
  while i.manager_busy and time.monotonic()<deadline:i.management_tick();time.sleep(.005)
  frame().save(out/'recordings-saved.png');i.ask_delete();frame().save(out/'delete-recording.png')
  manager.close()
 (out/'validation.json').write_text(json.dumps(dict(scope='Production V4 renderer/native PCM; container ARM; no physical device',frames=len(timings),mean_ms=sum(timings)/len(timings),max_ms=max(timings),motion=motion),indent=2)+'\n')
if __name__=='__main__':main()
