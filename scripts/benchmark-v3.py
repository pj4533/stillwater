#!/usr/bin/env python3
"""Dense DSP + production UI + ordered eight-pad input, offline/container only."""
import ctypes as C
from dataclasses import replace
import json
import math
from pathlib import Path
import platform
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,Layer,Event
from loop_engine import LoopEngine
from loop_app import LoopInstrument
from loop_graphics import render
from roles import ROLE_IDS

def metrics(v):return dict(samples=len(v),mean=sum(v)/len(v),p99=sorted(v)[min(len(v)-1,int(len(v)*.99))],max=max(v))
def main():
 with tempfile.TemporaryDirectory(dir=ROOT/'.build') as tmp:
  m=LoopModel(Path(tmp)/'current-v3.json',writer=False)
  layers=tuple(Layer(i,r,1,False,(1,)*8,tuple(Event(i*256+j+1,38+j%24,1,0 if j<8 else (j-7)*6000,1536000) for j in range(256))) for i,r in enumerate(ROLE_IDS))
  m.state=replace(m.state,loop_beats=16,tempo=160,master=1,role_order=ROLE_IDS,layers=layers);m.next_id=2049;m.overdub=False
  e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_reset();e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  i=LoopInstrument(m,e);out=(C.c_float*512)();e.lib.sw_render(out,1);i.performance.play()
  dsp=[];ui=[];screens=[];combined=[];events=0
  for block in range(1500):
   start=time.perf_counter()
   for layer in range(8):
    m.selected=layer
    event=dict(kind='note' if block%64==0 else 'poly_pressure',channel=0,number=36+layer,value=100 if block%64==0 else block%128)
    if not i.wire(event):raise AssertionError('unexpected input backpressure')
    events+=1
   i.tick();input_ms=(time.perf_counter()-start)*1000;ui.append(input_ms)
   start=time.perf_counter();e.lib.sw_render(out,256);native_ms=(time.perf_counter()-start)*1000;dsp.append(native_ms)
   if not all(math.isfinite(x) and abs(x)<=.25 for x in out):raise AssertionError('unbounded PCM')
   if block%32==0:
    m.selected=(block//32)%8;start=time.perf_counter();render(m,e.stats(),i);ms=(time.perf_counter()-start)*1000;screens.append(ms);combined.append(ms+input_ms+native_ms)
  result=dict(device=False,platform=platform.platform(),scope='Sequential offline native DSP and UI/input; writer disabled; no ALSA/USB or device timing',blocks=1500,events=events,events_per_block=8,events_stored=2048,roles=8,playback_voices=64,manual_voices=8,steal_tails=8,all_macros=1,audio_deadline_ms=256/44100*1000,dsp_ms=metrics(dsp),ui_input_ms=metrics(ui),ui_render_and_stats_ms=metrics(screens),sequential_frame_work_ms=metrics(combined),native=e.loop_stats())
  (ROOT/'.build/v3-combined-benchmark.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
