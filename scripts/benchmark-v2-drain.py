#!/usr/bin/env python3
"""Actual native eight-completion -> LoopPerformance.drain dense-song benchmark."""
import ctypes as C
from dataclasses import replace
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,Layer,Event,blank,decode_song,json_ready
from loop_engine import LoopEngine,LoopPerformance
from roles import ROLE_IDS

def main():
 engine=LoopEngine(ROOT/'.build/engine.so');engine.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
 pcm=(C.c_float*128)()
 layers=tuple(Layer(i,r,parameters=(.3,)*8,events=tuple(Event(i*256+j+1,62,.5,j*6000,100) for j in range(255))) for i,r in enumerate(ROLE_IDS))
 dense=replace(blank(seed=1),loop_beats=16,role_order=ROLE_IDS,layers=layers);durations=[]
 with tempfile.TemporaryDirectory(dir=ROOT/'.build') as temp:
  for _ in range(40):
   model=LoopModel(Path(temp)/'current-v2.json',writer=False);model.state=dense;model.next_id=2049
   engine.lib.sw_reset();engine.generation=0;p=LoopPerformance(model,engine);engine.lib.sw_render(pcm,1);p.play();engine.lib.sw_render(pcm,1)
   for i in range(8):model.selected=i;p.event('note',60+i,100)
   engine.lib.sw_render(pcm,64)
   for i in range(8):p.event('note_off',60+i,0)
   engine.lib.sw_render(pcm,1)
   before=time.perf_counter();p.drain();durations.append((time.perf_counter()-before)*1000)
   assert not model.pending and [len(l.events) for l in model.state.layers]==[256]*8
  assert decode_song(json_ready(model.state))==model.state
 result=dict(device=False,platform=platform.platform(),existing_events=2040,native_completions=8,result_events=2048,runs=len(durations),drain_ms=dict(mean=sum(durations)/len(durations),p99=sorted(durations)[int(len(durations)*.99)],max=max(durations)),writer=False,scope='Actual native completions through LoopPerformance.drain; no serialization/fsync in measured UI path')
 (ROOT/'.build/v2-drain-benchmark.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
