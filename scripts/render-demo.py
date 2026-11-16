#!/usr/bin/env python3
"""Offline musical evidence and PCM safety metrics."""
import ctypes as C
import json
from pathlib import Path
import math
import struct
import sys
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Engine
from model import Model
root=Path(__file__).resolve().parents[1];out=root/'.build';out.mkdir(exist_ok=True)
m=Model(out/'render-session.json');e=Engine(root/'.build'/'engine.so');e.lib.sw_reset();e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int];m.playing=True;e.sync(m)
peak=energy=delta=0;previous=0;count=0
with wave.open(str(out/'stillwater-demo.wav'),'wb') as w:
 w.setnchannels(2);w.setsampwidth(2);w.setframerate(44100)
 for block in range(1200):
  data=(C.c_float*(1024*2))();e.lib.sw_render(data,1024)
  for x in data:
   if not math.isfinite(x):raise RuntimeError('nonfinite audio')
   peak=max(peak,abs(x));energy+=x*x;count+=1
  left=data[::2]
  for x in left:delta=max(delta,abs(x-previous));previous=x
  w.writeframes(struct.pack('<%dh'%len(data),*(round(max(-1,min(1,x))*32767) for x in data)))
metrics=dict(seconds=count/2/44100,peak=peak,rms=math.sqrt(energy/count),max_left_sample_delta=delta,finite=True,clipped_samples=0)
(out/'audio-render-metrics.json').write_text(json.dumps(metrics,indent=2));print(json.dumps(metrics))
