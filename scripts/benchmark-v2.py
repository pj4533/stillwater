#!/usr/bin/env python3
"""Offline actual native64 playback+8manual+tails/allFX/full2048-event bank."""
import ctypes as C
from dataclasses import replace
import json
import math
from pathlib import Path
import platform
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_engine import LoopEngine
from loop_model import blank,Layer,Event,LOOP_TICKS
from roles import ROLE_IDS

def main():
 e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_reset();e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
 song=blank(seed=1);layers=[]
 for i,r in enumerate(ROLE_IDS):
  events=tuple(Event(i*256+j+1,38+(j%24),1,0 if j<8 else (j-7)*6000,LOOP_TICKS) for j in range(256))
  layers.append(Layer(i,r,1,False,(1,)*8,events))
 song=replace(song,role_order=ROLE_IDS,layers=tuple(layers),tempo=160,master=1)
 out=(C.c_float*512)();e.publish(song,1);e.lib.sw_render(out,1);e.transport(2,True,1)
 for i in range(8):e.lib.sw_performance_on(i,i+1,i,62,1,0,1,10000+i)
 regular=[];publication=[];admission=[]
 for block in range(1500):
  if block%32==0:
   start=time.perf_counter();e.publish(song,1);admission.append((time.perf_counter()-start)*1000)
  if block%64==0:
   for i in range(8):e.lib.sw_performance_on(i,100+block+i,i,65,1,0,1,20000+block+i)
  start=time.perf_counter();e.lib.sw_render(out,256);duration=(time.perf_counter()-start)*1000
  (publication if block%32==0 else regular).append(duration)
  if not all(math.isfinite(x) and abs(x)<=.25 for x in out):raise AssertionError("nonfinite/unbounded PCM")
 def metrics(values):return dict(mean=sum(values)/len(values),p99=sorted(values)[int(len(values)*.99)],max=max(values),samples=len(values))
 result=dict(platform=platform.platform(),device=False,budget_ms=256/44100*1000,regular_ms=metrics(regular),publication_ms=metrics(publication),python_bank_admission_ms=metrics(admission),events=2048,playback_voices=64,manual_voices=8,stolen_tails=8,roles=8,all_macros=1,native=e.loop_stats())
 (ROOT/'.build/v2-benchmark.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
