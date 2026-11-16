#!/usr/bin/env python3
"""Offline production renderer + actual native PCM; export GIF and contact sheet.

Pillow only encodes review artifacts here. Push uses cached BGR565 and stdlib.
No hardware, MIDI ports, sessions or sound output are opened.
"""
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from app import Engine,Instrument
from graphics import render,VisualState
from model import Model,NOTES
out=ROOT/'.build/mixer';out.mkdir(parents=True,exist_ok=True)
def image(frame):
 rgb=bytearray(960*160*3)
 for y in range(160):
  for x in range(960):
   offset=(y*1024+x)*2;value=frame[offset]|frame[offset+1]<<8
   pos=(y*960+x)*3;rgb[pos:pos+3]=bytes(((value&31)*255//31,((value>>5)&63)*255//63,((value>>11)&31)*255//31))
 return Image.frombytes('RGB',(960,160),bytes(rgb))
with tempfile.TemporaryDirectory() as d:
 m=Model(Path(d)/'current.json');e=Engine(ROOT/'.build/engine.so');e.lib.sw_reset();e.sync(m);i=Instrument(m,e);v=VisualState()
 e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int];pcm=(C.c_float*(4410*2))()
 frames=[];mixer_frames=[];mixer_timings=[];mixvisual=VisualState();timings=[];trace=[];hashes=[]
 i.event('cc',85,127)
 for n in range(80):
  if n%10==0:
   track=n//10;m.selected=track;e.command(5,track,NOTES[track],.9)
  e.lib.sw_render(pcm,4410);stats=e.stats();now=n*.1
  start=time.perf_counter();frame=render(m,stats['position'],now,telemetry=stats,visual=v);timings.append((time.perf_counter()-start)*1000)
  frames.append(image(frame));m.view='mixer';mixstart=time.perf_counter();mixframe=render(m,stats['position'],now,telemetry=stats,visual=mixvisual);mixer_timings.append((time.perf_counter()-mixstart)*1000);mixer_frames.append(image(mixframe));m.view='instrument';hashes.append(hashlib.sha256(frame).hexdigest())
  trace.append(dict(seconds=now,selected=m.selected,envelopes=stats['envelopes'],onsets=stats['onsets']))
 palette=frames[0].quantize(colors=128)
 encoded=[frame.quantize(palette=palette,dither=Image.Dither.NONE) for frame in frames]
 encoded[0].save(out/'pond-living-v3b.gif',save_all=True,append_images=encoded[1:],duration=100,loop=0,optimize=True)
 board=Image.new('RGB',(1920,640))
 for index,n in enumerate((0,9,19,29,39,49,59,79)):board.paste(frames[n],((index%2)*960,(index//2)*160))
 board.save(out/'pond-living-v3b-contact.png')
 mixer_frames[39].save(out/'mixer-v3b.png')
 mixpalette=mixer_frames[0].quantize(colors=128)
 mixencoded=[frame.quantize(palette=mixpalette,dither=Image.Dither.NONE) for frame in mixer_frames]
 mixencoded[0].save(out/'mixer-v3b.gif',save_all=True,append_images=mixencoded[1:],duration=100,loop=0,optimize=True)
 i.event('cc',29,127)
 for _ in range(10):e.lib.sw_render(pcm,4410)
 image(render(m,e.stats()['position'],9,telemetry=e.stats(),visual=v)).save(out/'pond-rest-v3b.png')
 recording=dict(e.stats(),recording={'state':'recording','seconds':12})
 image(render(m,e.stats()['position'],9,telemetry=recording,visual=v)).save(out/'pond-recording-v3b.png')
 m.execute(dict(op='propose_pattern',track=0,pattern=[60]+[0]*7,revision=m.revision,id='notification'))
 image(render(m,e.stats()['position'],9,telemetry=e.stats(),visual=v)).save(out/'pond-preview-v3b.png')
 result=dict(mixer_render_ms_max=max(mixer_timings),mixer_render_ms_mean=sum(mixer_timings)/len(mixer_timings),synthetic=True,production_renderer=True,fps=10,seconds=8,frames=len(frames),unique_frames=len(set(hashes)),render_ms_max=max(timings),render_ms_mean=sum(timings)/len(timings),native_onsets=e.stats()['onsets'],final_silent=e.stats()['peak']==0,trace=trace)
 (out/'animation-v3b-result.json').write_text(json.dumps(result,indent=2))
 print(json.dumps({k:v for k,v in result.items() if k!='trace'},indent=2))
