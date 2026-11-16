#!/usr/bin/env python3
"""Fresh synthetic growing-loop rehearsal, sample-clock time, no device access."""
import ctypes as C
from dataclasses import replace
import hashlib,json
from pathlib import Path
import subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,pad_pitch
from loop_engine import LoopEngine
from loop_app import LoopInstrument
from loop_graphics import render
from midi import MidiParser
from roles import ROLE_IDS

def main():
 out=ROOT/'.build/gentle/loop';out.mkdir(parents=True,exist_ok=True)
 frames=out/'frames';frames.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory(dir=ROOT/'.build') as temp:
  m=LoopModel(Path(temp)/'current-v3.json',writer=False);m.state=replace(m.state,tempo=60,master=.2)
  e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_reset();e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  i=LoopInstrument(m,e);parser=MidiParser();position=0;markers=[];poses=[];pcm=(C.c_float*8820)()
  def advance(seconds):
   nonlocal position
   target=round(seconds*44100)
   while position<target:
    n=min(4410,target-position);e.lib.sw_render(pcm,n);position+=n;i.tick()
  def wire(code,number,value):
   for event in parser.feed(bytes([code,number,value])):assert i.wire(event) is not False
  def cc(number,value=127):wire(176,number,value)
  def pad(pitch):return next(n for n in range(36,100) if pad_pitch(n,m.octave,m.state.root,m.state.scale)==pitch)
  def frame(label):
   raw=render(m,e.stats(),i);f=out/(label+'.bgr565');f.write_bytes(raw)
   subprocess.run([sys.executable,str(ROOT/'scripts/capture-frame.py'),str(f),str(frames/(label+'.png'))],check=True)
   markers.append(dict(label=label,seconds=position/44100,view=m.view,counts=[len(l.events) for l in m.state.layers],parameters=[list(l.parameters) for l in m.state.layers],sha256=hashlib.sha256(raw).hexdigest()))
  advance(.1);cc(56);advance(.2);assert m.state.loop_beats==8 and e.loop_stats()['loop_beats']==8
  cc(113);frame('00-empty-eight-beats');advance(2);cc(85)
  # Events preserve the brief's source-time score; notes drained before count.
  notes=[(2,50,1.8),(6,57,1),(11,62,1.4),(14,69,1.5),(17,65,.6),(21,45,1),(24,53,.9),(27,69,.4),(29,65,.4),(31,74,.4),(33,62,.4),(39,74,.45),(43,69,.5),(45,72,.4),(47,57,1)]
  actions=[]
  for n,(t,p,d) in enumerate(notes):
   actions.extend([(t,'on',p,n),(t+d,'off',p,n),(t+d+.03,'frame',p,n)])
  for t,role in ((10.2,'choir'),(26.1,'filament'),(38,'prism')):actions.append((t,'role',role,0))
  actions.extend([(18.1,'pose',0,0),(19,'pose',0,1),(20,'select',0,0),(34,'pose',0,2),(35,'pose',0,3),(44.7,'select',2,0),(46.7,'select',1,0)])
  for t,kind,value,n in sorted(actions):
   advance(t)
   if kind=='on':wire(144,pad(value),55)
   elif kind=='off':wire(128,pad(value),0)
   elif kind=='role':cc(92);cc(102+ROLE_IDS.index(value));cc(113)
   elif kind=='select':cc(102+value);cc(113)
   elif kind=='pose':
    cc(50);frame('pose-'+str(n));poses.append(markers[-1]);cc(113)
   else:frame('%02d-notes'% (n+1))
  advance(50);frame('50-complete');assert [len(l.events) for l in m.state.layers]==[4,4,5,2]
  for a,b in ((poses[0],poses[1]),(poses[2],poses[3])):
   assert a['parameters']==b['parameters'] and a['sha256']!=b['sha256']
  advance(60);cc(29);advance(63);assert e.loop_stats()['transport']==0 and e.stats()['xruns']==0
  result=dict(scope='Offline production parser/dispatcher/native/render, synthetic fresh score; no device frames or listening claim',loop_beats=8,notes=15,markers=markers,stationary_instrument_animation=True,native=e.loop_stats())
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');i.close();print('15 notes across4layers,8beats; LOOP frames and stationary instrument poses passed')
if __name__=='__main__':main()
