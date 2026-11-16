"""Gentle sound compatibility and real native PCM, no user/device state."""
import copy
import ctypes as C
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import blank,Layer,Event,LoopModel,decode_song,json_ready,envelope,atomic_write,read_envelope,variant
from loop_engine import LoopEngine,bank_for
from roles import ROLE_IDS,DEFAULTS

class Gentle(unittest.TestCase):
 def test_old_state_and_every_history_entry_load_without_write(self):
  for schema in (1,2):
   with self.subTest(schema=schema),tempfile.TemporaryDirectory() as temp:
    path=Path(temp)/'current-v3.json';raw=json_ready(replace(blank(),loop_beats=16));raw['schema']=schema
    for layer in raw['layers']:layer.pop('sound_version')
    raw['layers'][0]['events']=[dict(id=1,pitch=62,velocity=.6,start_tick=0,duration_tick=96000)]
    if schema==2:raw['layers'][0]['events'][0]['degree']=0
    payload=dict(format='stillwater-loop',version=2,revision=5,state=raw,undo=[copy.deepcopy(raw)],redo=[copy.deepcopy(raw)])
    path.write_text(json.dumps(payload));before=path.read_bytes();m=LoopModel(path,writer=True)
    try:
     self.assertEqual(path.read_bytes(),before)
     for song in (m.state,)+m.undo_stack+m.redo_stack:
      self.assertEqual(song.layers[0].sound_version,1);self.assertEqual(song.layers[0].parameters,tuple(raw['layers'][0]['parameters']))
     self.assertTrue(m.set_master(.2));self.assertTrue(m.writer.flush(m.revision,3))
     saved=read_envelope(path);self.assertEqual(saved['state'].schema,3)
     self.assertTrue(all(s.layers[0].sound_version==1 for s in (saved['state'],)+saved['undo']+saved['redo']))
    finally:m.close()
 def test_mixed_profiles_add_rekey_history_and_save(self):
  with tempfile.TemporaryDirectory() as temp:
   m=LoopModel(Path(temp)/'current-v3.json',writer=False)
   old=replace(m.state.layers[0],sound_version=1,events=(Event(1,62,.6,0,96000),));m.state=replace(m.state,layers=(old,));m.next_id=2
   self.assertTrue(m.add_layer('choir'));mixed=m.state
   self.assertEqual([l.sound_version for l in mixed.layers],[1,2]);params=tuple(l.parameters for l in mixed.layers)
   self.assertTrue(m.rekey(64,'minor'));self.assertEqual(tuple(l.parameters for l in m.state.layers),params)
   m.undo();self.assertEqual(m.state,mixed);m.undo();self.assertEqual(m.state.layers,(old,));m.redo();self.assertEqual(m.state,mixed)
   atomic_write(m.path,m.payload());loaded=read_envelope(m.path);self.assertEqual(loaded['state'],mixed)
   self.assertEqual(loaded['undo'],m.undo_stack);self.assertEqual(loaded['redo'],m.redo_stack)
 def test_version_validation_python_and_native(self):
  e=LoopEngine(ROOT/'.build/engine.so')
  for version in (0,3,-1,True,1.5,None):
   raw=json_ready(blank());raw['layers'][0]['sound_version']=version
   with self.subTest(version=version),self.assertRaises(ValueError):decode_song(raw)
  for missing in ('sound_version',):
   raw=json_ready(blank());raw['layers'][0].pop(missing)
   with self.assertRaises(ValueError):decode_song(raw)
  for version in (0,3,-1):
   bank=bank_for(blank());bank.layers[0].sound_version=version
   self.assertEqual(e.lib.sw_song_publish(C.byref(bank),1,1),-2)
  class Old:
   def sw_loop_abi(self):return 4
  with patch('loop_engine.C.CDLL',return_value=Old()),patch('app.Engine.__init__') as init:
   with self.assertRaisesRegex(RuntimeError,'ABI'):LoopEngine('old','hw:device')
   init.assert_not_called()
 def test_fresh_variants_are_bounded_and_persisted(self):
  for role_id,role in enumerate(ROLE_IDS):
   for seed in range(128):
    p=variant(role,str(seed),role_id);self.assertEqual(p,variant(role,str(seed),role_id))
    for a,b in zip(p,DEFAULTS[role_id]):self.assertLessEqual(abs(a-b),.01500001);self.assertTrue(0<=a<=1)
    if role=='oxide':self.assertEqual(p[5],0)
    if role=='glass':self.assertLess(p[0],1/7)
    if role=='prism':self.assertLess(p[4],.5)
    if role=='spore':self.assertLess(p[5],.7)
  self.assertEqual(blank().layers[0].sound_version,2);self.assertEqual(Layer(0,'silt').sound_version,1)
 def test_legacy_pcm_bitwise_baseline(self):
  import platform
  provenance=json.loads((ROOT/'tests/fixtures/gentle-legacy-provenance.json').read_text())
  if platform.machine()!=provenance['machine'] or subprocess.check_output(['gcc','--version'],text=True).splitlines()[0]!=provenance['compiler']:
   self.skipTest('PCM golden requires captured architecture/compiler; use paired pre-change render on this toolchain')
  baseline=json.loads((ROOT/'tests/fixtures/gentle-legacy-baseline.json').read_text())
  e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  def audio(n):
   out=(C.c_float*(2*n))();e.lib.sw_render(out,n);return bytes(out)
  # sw_reset retains desired level scalars; establish the original fresh-library
  # precondition before the first golden role, independent of prior tests.
  e.lib.sw_reset()
  for i,value in enumerate((.6,.36,.28,.4,.24,.28,.25,.22)):e.command(4,i,0,value)
  audio(1)
  for role,b in baseline.items():
   with self.subTest(role=role):
    e.lib.sw_reset();e.generation=0;song=replace(blank(),role_order=(role,)+tuple(r for r in ROLE_IDS if r!=role),layers=(Layer(0,role,parameters=tuple(b['parameters'])),))
    e.publish(song,1);audio(1);e.check(e.lib.sw_performance_on(0,1,0,62,.6,0,1,1));pcm=audio(88200);e.check(e.lib.sw_performance_off(0,1));pcm+=audio(88200)
    self.assertEqual(hashlib.sha256(pcm).hexdigest(),b['sha256'])
 def test_envelope_seconds_and_stop_native(self):
  # Inspect actual voice gain with a C harness so source beating/FX cannot
  # masquerade as attack time; expected seconds are independent reference data.
  with tempfile.TemporaryDirectory() as temp:
   exe=Path(temp)/'envelope'
   subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(ROOT/'tests/gentle_envelope.c'),'-lm','-lpthread','-ldl','-o',str(exe)],check=True)
   subprocess.run([str(exe)],check=True)
 def test_defaults_extremes_and_live_transitions_across_registers(self):
  import math
  e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  def audio(n):
   out=(C.c_float*(2*n))();e.lib.sw_render(out,n)
   self.assertTrue(all(math.isfinite(x) and abs(x)<=.25 for x in out));return list(out)
  for role_id,role in enumerate(ROLE_IDS):
   for pitch in (24,50,74,96):
    for params in (DEFAULTS[role_id],(0,)*8,(1,)*8):
     with self.subTest(role=role,pitch=pitch,parameters=params):
      e.lib.sw_reset();e.generation=0;s=replace(blank(),master=1,role_order=(role,)+tuple(r for r in ROLE_IDS if r!=role),layers=(Layer(0,role,level=1,parameters=params,sound_version=2),))
      e.publish(s,1);audio(1);e.check(e.lib.sw_performance_on(0,1,0,pitch,1,0,1,1));before=audio(4410)
      for macro in range(8):e.check(e.lib.sw_layer_parameter(0,macro,1-params[macro]))
      after=audio(4410)
      # Transition boundary cannot jump beyond nearby waveform slopes. This
      # relative check permits legitimate high-note slopes; it catches resets.
      boundary=abs(after[0]-before[-2]);near=before[-202:]+after[:200]
      slopes=[abs(near[n]-near[n-2]) for n in range(2,len(near),2) if n!=202]
      self.assertLessEqual(boundary,max(slopes)*1.1+1e-7)
      e.check(e.lib.sw_performance_off(0,1));audio(8820)
      e.check(e.lib.sw_layer_parameter(0,9,1));audio(8820)
      e.transport(0,False,1);audio(12000);self.assertTrue(all(x==0 for x in audio(512)))
