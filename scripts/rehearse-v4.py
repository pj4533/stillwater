#!/usr/bin/env python3
"""Production wire/native/render/worker V4 rehearsal, private disposable home."""
import ctypes as C
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,Event,read_envelope
from loop_engine import LoopEngine
from loop_app import LoopInstrument,led_values
from loop_graphics import render
from recorder import SessionRecorder
from bottle import Bottle
from loop_export import LoopExport
from library_manager import LibraryManager
from midi import MidiParser

def main():
 out=ROOT/'.build/v4-rehearsal';out.mkdir(exist_ok=True);home=out/'home'
 if home.exists():shutil.rmtree(home) # Only this disposable script-owned home.
 home.mkdir();checks=[];timings=[]
 def check(name,value):
  if not value:raise AssertionError(name)
  checks.append(name)
 m=LoopModel(home/'sessions/current-v3.json');e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_reset();e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
 recorder=SessionRecorder(e,home/'recordings');bottle=Bottle(e,home/'recordings');export=LoopExport(e,home/'recordings');manager=LibraryManager(home,recorder,bottle,export)
 i=LoopInstrument(m,e,bottle,recorder,export,manager);parser=MidiParser();pcm=(C.c_float*8820)()
 def audio():e.lib.sw_render(pcm,4410);i.tick()
 def cc(n,value=127):
  for event in parser.feed(bytes([0xb0,n,value])):
   if i.wire(event) is False:audio();check('ordered wire retry',i.wire(event) is not False)
 def screen():
  stats=e.stats();stats.update(recording=recorder.snapshot(),export=export.snapshot());start=time.monotonic();raw=render(m,stats,i);timings.append((time.monotonic()-start)*1000);recorder.displayed(raw);return raw
 def wait(predicate,timeout=8):
  deadline=time.monotonic()+timeout
  while not predicate() and time.monotonic()<deadline:i.tick();time.sleep(.005)
  check('asynchronous operation completed',predicate())
 try:
  audio();screen();cc(85);audio();check('first Play remains FILM OFF',recorder.snapshot()['state']=='idle')
  cc(49);cc(86);cc(49,0);check('shift record opens manager without capture',m.view=='recordings' and recorder.snapshot()['state']=='idle')
  cc(20);check('explicit START FILM',recorder.snapshot()['state']=='recording')
  try:cc(20)
  except ValueError:check('busy start refused',True)
  else:raise AssertionError('busy start accepted')
  cc(110)
  # Play actual notes from four unique roles while the recorder copies PCM.
  for block in range(80):
   if block%20==0:
    if block:
     cc(92);role=next(r for r in __import__('roles').ROLE_IDS if m.role_state(r)=='READY');cc(102+__import__('roles').ROLE_IDS.index(role))
    for event in parser.feed(bytes([0x92,48+block//20,105])):i.wire(event)
   if block%20==5:
    for event in parser.feed(bytes([0x82,48+block//20,0])):i.wire(event)
   audio();screen();led_values(m,e.stats(),i);time.sleep(.003)
  check('four performed layers recorded',len(m.state.layers)==4 and all(l.events for l in m.state.layers))
  transport=i.performance.transport;cc(49);cc(86);cc(49,0);cc(21)
  check('STOP+SAVE music continues',i.performance.transport==transport)
  screen();wait(lambda:not recorder.snapshot()['busy'],20);record=recorder.snapshot();check('real MP4 ready',record['state']=='ready')
  final=recorder.directory/record['filename'];probe=json.loads(subprocess.check_output(['/usr/bin/ffprobe','-v','error','-show_streams','-show_format','-of','json',str(final)]))
  check('film H264 AAC and exact visible dimensions',[(s['codec_name'],s.get('width'),s.get('height')) for s in probe['streams']]==[('h264',960,160),('aac',None,None)])
  subprocess.run(['/usr/bin/ffmpeg','-v','error','-xerror','-err_detect','explode','-i',str(final),'-f','null','-'],check=True)
  check('strict full decode',True)
  cc(58);before=m.state;revision=m.revision;cc(107);check('scale candidate leaves music intact',m.state==before);cc(27);audio();check('scale Apply one undo edit',m.revision==revision+1 and m.state.scale=='minor')
  cc(51);cc(20);wait(lambda:bool(manager.saved.exists() and list(manager.saved.glob('song-*.json'))));i.refresh_manager();wait(lambda:not i.manager_busy)
  check('SAVE NEW and readable library',bool(i.rows) and i.rows[0]['status']=='READY');source=i.selected_row();source_bytes=(manager.saved/source['id']).read_bytes()
  cc(22);i.rename='V4 REHEARSAL';cc(27);wait(lambda:not i.manager_busy);check('rename immutable envelope',i.selected_row()['name']=='V4 REHEARSAL' and (manager.saved/source['id']).read_bytes()==source_bytes)
  cc(22);i.rename='DISCARD';cc(26);check('cancel rename',i.selected_row()['name']=='V4 REHEARSAL')
  cc(79,1);audio();dirty=m.state;cc(21);check('load is a confirmation',i.confirm is not None and m.state==dirty);cc(26);check('cancel load preserves music',m.state==dirty)
  cc(21);cc(27);audio();wait(lambda:m.state==read_envelope(manager.saved/source['id'])['state']);audio();check('load stops and archives dirty current',not i.performance.transport and len(list(manager.saved.glob('song-*.json')))>=2)
  cc(118);cc(118);check('physical Delete twice never confirms',i.confirm is not None and (manager.saved/source['id']).exists());cc(27);wait(lambda:not i.manager_busy)
  check('delete loaded snapshot leaves current music',not (manager.saved/source['id']).exists() and bool(m.state.layers[0].events))
  i.open_page('recordings');cc(105);wait(lambda:not i.manager_busy);film=next(r for r in i.rows if r['id']==record['job']);check('film inventory includes private raw bytes',film['raw_bytes']>1000000 and film['bytes']>final.stat().st_size)
  # Keep the genuine film as review evidence; delete only a disposable WAV.
  import wave
  copy=manager.recordings/'bottle-20261116-120000-abcdef.wav'
  with wave.open(str(copy),'wb') as wav:wav.setparams((2,2,44100,0,'NONE',''));wav.writeframes(bytes(400))
  i.refresh_manager();wait(lambda:not i.manager_busy);i.selected_id=copy.name;cc(23);cc(27);wait(lambda:not i.manager_busy);check('delete disposable recording only',not copy.exists() and final.exists())
  m.checkpoint(True);check('current durable and valid',m.writer.flush(m.revision,3) and read_envelope(m.path)['state']==m.state)
  cc(29);audio();check('quiet Stop and no xruns',not e.loop_stats()['transport'] and e.stats()['xruns']==0)
  report=dict(checks=checks,count=len(checks),render_max_ms=max(timings),film=str(final),film_sha256=hashlib.sha256(final.read_bytes()).hexdigest(),recording=record,probe=probe,scope='Local real production wire/native DSP/renderer and serialized filesystem workers; no physical hardware')
  (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
 finally:i.close()
if __name__=='__main__':main()
