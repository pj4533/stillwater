import ctypes as C
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import wave
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_app import LoopInstrument
from loop_engine import LoopEngine
from loop_model import LoopModel,Event,LOOP_TICKS
from loop_export import LoopExport
from loop_graphics import render
from midi import MidiParser,MidiDispatch

class Integration(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.build');self.addCleanup(self.tmp.cleanup)
  self.m=LoopModel(Path(self.tmp.name)/'current-v2.json',writer=False,seed=2)
  self.m.state=replace(self.m.state,loop_beats=16)  # Retained V2 fixture.
  self.e=LoopEngine(ROOT/'.build/engine.so');self.e.lib.sw_reset();self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  self.i=LoopInstrument(self.m,self.e);self.audio(1)
 def audio(self,n):
  out=(C.c_float*(n*2))();self.e.lib.sw_render(out,n)
 def wire(self,data):
  for event in MidiParser().feed(bytes(data)):self.assertIsNot(self.i.wire(event),False)
 def test_all_views_keep64pads_musical_and_new_never_replaces_roles(self):
  for viewcc in (50,51,112):
   self.wire([0xb0,viewcc,127]);self.wire([0x92,36,100]);self.audio(2)
   self.assertEqual(self.e.loop_stats()['held'],1);self.wire([0x82,36,0]);self.audio(1)
  self.wire([0xb0,85,127]);self.audio(100)
  self.assertEqual(self.e.loop_stats()['transport'],1)
  self.wire([0x92,99,90]);self.audio(64);self.wire([0x82,99,0]);self.audio(1);self.i.tick()
  self.assertEqual(len(self.m.state.layers[0].events),1)
  for _ in range(7):
   self.wire([0xb0,92,127]);self.audio(1)
   role=next(r for r in __import__('roles').ROLE_IDS if self.m.role_state(r)=='READY')
   self.wire([0xb0,102+__import__('roles').ROLE_IDS.index(role),127]);self.audio(1)
   self.wire([0x92,60,90]);self.audio(32);self.wire([0x82,60,0]);self.audio(1);self.i.tick()
  roles=tuple(l.role for l in self.m.state.layers);self.wire([0xb0,92,127]);self.audio(1)
  self.assertEqual(tuple(l.role for l in self.m.state.layers),roles)
  self.wire([0xb0,102,127,49,127,50,127,49,0]);self.assertFalse(self.m.overdub)
 def test_native_backpressure_keeps_ordered_release_and_observes_settings(self):
  self.wire([0x92,60,100]);self.audio(1)
  for _ in range(1020):self.assertEqual(self.e.lib.sw_loop_master(.2),0)
  dispatch=MidiDispatch();batch=MidiParser().feed(bytes([0xb0,30,127,0x82,60,0,0xb0,30,0]))
  dispatch.process(lambda:batch,self.i.wire,self.i.received)
  self.assertEqual(len(dispatch.pending),3);self.assertIsNone(self.i.gear)
  self.audio(1);dispatch.process(lambda:[],self.i.wire,self.i.received);self.audio(1)
  self.assertFalse(dispatch.pending);self.assertEqual(self.e.loop_stats()['held'],0)
 def test_status_readouts_distinct_during_recording_help_and_all_views(self):
  self.i.help=True
  for view in ('instrument','mixer','overview'):
   self.m.view=view;self.m.set_level(0,.45);self.m.set_parameter(0,0,.45)
   stats=self.e.stats();stats['recording']=dict(state='recording')
   a=render(self.m,stats,self.i);self.m.set_level(0,.99);self.m.set_parameter(0,0,.99);b=render(self.m,stats,self.i)
   if view!='overview':self.assertNotEqual(a[141*2048:155*2048],b[141*2048:155*2048])
   self.assertEqual(len(a),327680)
 def test_loop_export_cancels_on_audition_and_musical_edits(self):
  song=self.m.state;self.m.state=replace(song,tempo=160,layers=(replace(song.layers[0],events=(Event(1,62,.5,0,1000),)),));self.e.publish(self.m.state,1);self.audio(1)
  self.e.transport(2,True,1);self.audio(1)
  export=LoopExport(self.e,Path(self.tmp.name)/'exports');self.addCleanup(export.close)
  export.request(0);self.e.lib.sw_performance_on(0,1,0,62,.5,0,1,20);self.audio(1)
  export.worker.join(2);self.assertEqual(export.status['state'],'error');self.assertIn('changed',export.status['error'])
  self.assertFalse(list((Path(self.tmp.name)/'exports').glob('*.wav')))
 def test_play_cancels_deferred_new_and_library_replacement(self):
  self.i.transition=('new',None);self.m.new_revision=0;self.m.loading_revision=0
  self.wire([0xb0,85,127]);self.assertIsNone(self.i.transition);self.assertIsNone(self.m.new_revision);self.assertIsNone(self.m.loading_revision)
 def test_shutdown_drains_pending_captured_take_before_persistence(self):
  self.wire([0xb0,85,127,0x92,60,100]);self.audio(100)
  self.i.close();self.assertFalse(self.m.pending);self.assertEqual(len(self.m.state.layers[0].events),1)
