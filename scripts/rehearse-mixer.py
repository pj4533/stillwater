#!/usr/bin/env python3
"""Actual production mixer/art/recovery frames and quiet native fader evidence."""
import ctypes as C
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from app import Engine,Instrument
from graphics import render,VisualState,recovery_frame
from model import Model
spec=importlib.util.spec_from_file_location('local_rehearsal',ROOT/'scripts/rehearse-local.py');local=importlib.util.module_from_spec(spec);spec.loader.exec_module(local)
out=ROOT/'.build/mixer';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as d:
 m=Model(Path(d)/'current.json');e=Engine(ROOT/'.build/engine.so');e.lib.sw_reset();e.sync(m);i=Instrument(m,e);visual=VisualState();timings=[]
 e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
 def audio(n):
  pcm=(C.c_float*(n*2))();e.lib.sw_render(pcm,n)
 def frame(name,now,telemetry=None):
  start=time.perf_counter();f=render(m,e.stats()['position'],now,telemetry=telemetry or e.stats(),visual=visual);timings.append((time.perf_counter()-start)*1000);local.png(out/(name+'.png'),f)
 frame('pond-at-rest',0);i.event('cc',50,127);i.wire(dict(kind='note',channel=2,number=60,value=100));audio(22050);frame('pond-alight',.5)
 i.event('cc',112,127);frame('mixer',.6);i.event('cc',24,127);audio(22050);frame('mixer-muted',1.1)
 i.event('cc',79,127);m.master_until=4;frame('master-overlay',2)
 m.master_until=0;frame('help',4,dict(e.stats(),help=True,recording=dict(state='recording',seconds=72)))
 i.event('cc',29,127);audio(22050);audio(1024);frame('mixer-stopped',5)
 local.png(out/'recovery.png',recovery_frame('Native engine unavailable / retry or hold Settings',3))
 (out/'result.json').write_text(json.dumps(dict(synthetic=True,frames=8,render_ms_max=max(timings),render_ms_mean=sum(timings)/len(timings),audio=e.stats(),final_silent=e.stats()['peak']==0),indent=2))
 print((out/'result.json').read_text())
