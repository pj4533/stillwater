#!/usr/bin/env python3
"""Dense production DSP baseline plus UI rendering during library I/O."""
import ctypes as C
import json
from pathlib import Path
import runpy
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from library_manager import LibraryManager
from loop_model import LoopModel,atomic_write,read_envelope,envelope
from loop_engine import LoopEngine
from loop_app import LoopInstrument
from loop_graphics import render,preload

def main():
 runpy.run_path(str(ROOT/'scripts/benchmark-v3.py'))['main']()
 dense=json.loads((ROOT/'.build/v3-combined-benchmark.json').read_text())
 source=read_envelope(ROOT/'.build/v4-rehearsal/home/sessions/current-v3.json')
 # Use a real performed song and64 validated history snapshots. This is an
 # explicit representative workload, not a maximum-size adversarial library.
 payload=envelope(1,source['state'],(source['state'],)*64,())
 with tempfile.TemporaryDirectory(dir=ROOT/'.build') as temp:
  home=Path(temp);m=LoopModel(home/'sessions/current-v3.json',writer=False)
  manager=LibraryManager(home)
  try:
   for n in range(64):atomic_write(manager.saved/('song-'+('%032x'%n)+'.json'),payload)
   e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_reset();i=LoopInstrument(m,e,manager=manager);preload()
   e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int];pcm=(C.c_float*512)();e.lib.sw_render(pcm,1)
   i.open_page('library');timings=[];started=time.monotonic();deadline=started+15
   while i.manager_busy and time.monotonic()<deadline:
    e.lib.sw_render(pcm,256);begin=time.monotonic();i.tick();render(m,e.stats(),i);timings.append((time.monotonic()-begin)*1000)
   if i.manager_busy or len(i.rows)!=64:raise AssertionError('Library benchmark did not finish')
   worker=dict(scope='Container ARM;64 real performed-song envelopes, each64history entries; concurrent serialized list parse and production UI render/stats',files=64,file_bytes=next(manager.saved.glob('song-*.json')).stat().st_size,frames=len(timings),elapsed_seconds=time.monotonic()-started,render_and_tick_max_ms=max(timings),frame_budget_ms=100)
   if worker['render_and_tick_max_ms']>=100:raise AssertionError('UI frame exceeded100ms in representative worker workload')
  finally:manager.close()
 result=dict(dense=dense,worker=worker)
 (ROOT/'.build/v4-benchmark.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
