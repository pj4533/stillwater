"""Adversarial onset-mode, replacement ordering and bounded completion checks."""
import ctypes as C
from dataclasses import replace
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_app import LoopInstrument
from loop_engine import LoopEngine,LoopPerformance
from loop_model import LoopModel,SessionWriter,Event,Layer,blank,atomic_write,decode_song,json_ready,LOOP_TICKS
from roles import ROLE_IDS
from midi import MidiParser

_v3_blank=blank
def blank(*args,**kwargs):return replace(_v3_blank(*args,**kwargs),loop_beats=16)


class DelayedWriter:
 """Real library job implementation; completions explicitly delayed by the test."""
 def __init__(self,path):self.path=path;self.results=queue.Queue();self.jobs=[]
 def task(self,*job):self.jobs.append(job)
 def submit(self,*args):pass
 def complete(self,index,error=None):
  kind,payload,name=self.jobs[index]
  result=SessionWriter._job(self,kind,payload,name) if error is None else dict(kind=kind,revision=payload['revision'],request_token=payload['request_token'],error=error)
  self.results.put(result)

class ReplacementOrder(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.m=LoopModel(Path(self.tmp.name)/'current-v2.json',writer=False,seed=2)
  self.m.state=replace(self.m.state,loop_beats=16)  # Retained V2 fixture.
  self.w=DelayedWriter(self.m.path);self.m.writer=self.w
  self.a=replace(blank(seed=1),master=.4);self.b=replace(blank(seed=3),master=.8)
  self.names=['song-'+str(i)*32+'.json' for i in (1,2)]
  for name,song in zip(self.names,(self.a,self.b)):atomic_write(self.m.path.parent/'saved'/name,dict(self.m.payload(),state=song),True)
 def test_same_revision_load_a_then_b_delayed_a_cannot_win_or_cancel_b(self):
  old=self.m.state;self.m.request_load(self.names[0]);self.m.request_load(self.names[1]);latest=self.m.replacement_request
  self.w.complete(0);self.assertFalse(self.m.poll_tasks()[0]['applied']);self.assertIs(self.m.state,old);self.assertEqual(self.m.replacement_request,latest)
  self.w.complete(1);self.assertTrue(self.m.poll_tasks()[0]['applied']);self.assertEqual(self.m.state,self.b);self.assertIsNone(self.m.replacement_request)
 def test_load_then_new_new_then_load_latest_wins(self):
  for first in ('load','new'):
   with self.subTest(first=first):
    self.w.jobs=[]
    if first=='load':self.m.request_load(self.names[0]);self.m.request_new()
    else:self.m.request_new();self.m.request_load(self.names[1])
    token=self.m.replacement_request;old=self.m.state
    self.w.complete(0);self.assertFalse(self.m.poll_tasks()[0]['applied']);self.assertIs(self.m.state,old);self.assertEqual(self.m.replacement_request,token)
    self.w.complete(1);self.assertTrue(self.m.poll_tasks()[0]['applied'])
    if first=='load':self.assertNotEqual(self.m.state.song_id,old.song_id);self.assertEqual(len(self.m.state.layers),1);self.assertFalse(self.m.state.layers[0].events)
    else:self.assertEqual(self.m.state,self.b)
 def test_stale_failure_does_not_clear_newer_token_and_rejected_job_does_not_supersede(self):
  self.m.request_load(self.names[0]);self.m.request_new();token=self.m.replacement_request
  self.w.complete(0,'old disk failure');self.m.poll_tasks();self.assertEqual(self.m.replacement_request,token)
  with patch.object(self.w,'task',side_effect=queue.Full):
   with self.assertRaises(queue.Full):self.m.request_load(self.names[1])
  self.assertEqual(self.m.replacement_request,token);self.w.complete(1);self.assertTrue(self.m.poll_tasks()[0]['applied'])
 def test_cancel_replacement_keeps_delayed_completion_stale(self):
  for kind in ('load','new'):
   self.w.jobs=[]
   if kind=='load':self.m.request_load(self.names[0])
   else:self.m.request_new()
   self.m.cancel_replacement();old=self.m.state;self.w.complete(0)
   self.assertFalse(self.m.poll_tasks()[0]['applied']);self.assertIs(self.m.state,old)

class NativeReview(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.build');self.addCleanup(self.tmp.cleanup)
  self.m=LoopModel(Path(self.tmp.name)/'current-v2.json',writer=False,seed=2)
  self.m.state=replace(self.m.state,loop_beats=16)  # Retained V2 fixture.
  self.e=LoopEngine(ROOT/'.build/engine.so');self.e.lib.sw_reset();self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  self.i=LoopInstrument(self.m,self.e);self.audio(1)
 def audio(self,n):out=(C.c_float*(n*2))();self.e.lib.sw_render(out,n)
 def wire(self,data):
  for event in MidiParser().feed(bytes(data)):self.assertIsNot(self.i.wire(event),False)
 def toggle(self):self.wire([0xb0,49,127,50,127,49,0])
 def test_audition_play_to_overdub_records_without_restart_or_orphan(self):
  self.toggle();self.wire([0xb0,85,127,0x92,60,100]);self.audio(64)
  origin=self.e.loop_stats()['origin'];self.assertFalse(self.m.pending)
  self.toggle();self.wire([0x92,61,100]);self.audio(100);self.wire([0x82,60,0,61,0]);self.audio(1);self.i.tick()
  self.assertEqual(len(self.m.state.layers[0].events),1);self.assertFalse(self.m.pending)
  self.assertEqual(self.e.loop_stats()['origin'],origin);self.assertEqual(self.e.loop_stats()['held'],0);self.assertEqual(self.e.loop_stats()['pending'],0)
 def test_captured_hold_finishes_after_off_and_audition_hold_stays_unrecorded_after_on(self):
  self.wire([0xb0,85,127,0x92,60,100]);self.audio(64);origin=self.e.loop_stats()['origin']
  self.toggle();self.wire([0x92,61,100]);self.audio(64)
  self.toggle();self.wire([0x82,60,0,61,0]);self.audio(1);self.i.tick()
  self.assertEqual(len(self.m.state.layers[0].events),1);self.assertFalse(self.m.pending)
  self.assertEqual(self.e.loop_stats()['origin'],origin);self.assertEqual(self.e.loop_stats()['pending'],0)
 def test_production_play_cancels_load_and_new_tokens(self):
  writer=DelayedWriter(self.m.path);self.m.writer=writer
  name='song-'+'1'*32+'.json';atomic_write(self.m.path.parent/'saved'/name,self.m.payload(),True)
  for kind in ('load','new'):
   writer.jobs=[]
   if kind=='load':self.m.request_load(name)
   else:self.m.request_new()
   self.assertIsNotNone(self.m.replacement_request);old=self.m.state
   self.wire([0xb0,85,127]);self.assertIsNone(self.m.replacement_request)
   writer.complete(0);self.i.tick();self.assertIs(self.m.state,old);self.audio(1)
 def test_dense_eight_native_completions_validate_only_delta_and_preserve_state(self):
  layers=tuple(Layer(i,r,parameters=(.3,)*8,events=tuple(Event(i*256+j+1,62,.5,j*6000,100) for j in range(255))) for i,r in enumerate(ROLE_IDS))
  self.m.state=replace(blank(seed=1),role_order=ROLE_IDS,layers=layers);self.m.next_id=2049
  self.e.lib.sw_reset();self.e.generation=0;self.i=LoopInstrument(self.m,self.e);self.audio(1);self.i.performance.play();self.audio(1)
  for i in range(8):self.m.selected=i;self.wire([0x92,60+i,100])
  self.audio(64)
  for i in range(8):self.wire([0x82,60+i,0])
  self.audio(1)
  with patch('loop_model.json_ready',side_effect=AssertionError('whole-song serialization in drain')):
   started=time.perf_counter();self.i.performance.drain();duration=time.perf_counter()-started
  self.assertLess(duration,.02);self.assertFalse(self.m.pending);self.assertEqual([len(l.events) for l in self.m.state.layers],[256]*8)
  self.assertEqual(decode_song(json_ready(self.m.state)),self.m.state)
 def test_invalid_completion_never_mutates_valid_state_or_drops_reservation(self):
  eid=self.m.reserve(0,1,0);take=dict(id=eid,epoch=self.m.capture_epoch,layer=0,pitch=62,velocity=.5,start_tick=0,duration_tick=1)
  for field,value in [('pitch',23),('velocity',float('nan')),('velocity',0),('id',True),('start_tick',LOOP_TICKS),('duration_tick',0),('status',2)]:
   old=self.m.state;pending=dict(self.m.pending)
   with self.assertRaises(ValueError):self.m.accept_take(dict(take,**{field:value}))
   self.assertIs(self.m.state,old);self.assertEqual(self.m.pending,pending)
  self.assertTrue(self.m.accept_take(take));self.assertFalse(self.m.accept_take(take));self.assertEqual(len(self.m.state.layers[0].events),1)
  layer=self.m.state.layers[0];self.m.state=replace(self.m.state,layers=(replace(layer,events=tuple(Event(i+1,62,.5,i*1000,10) for i in range(256))),))
  self.m.next_id=257;eid=self.m.reserve(0,2,0);old=self.m.state;pending=dict(self.m.pending)
  with self.assertRaisesRegex(ValueError,'capacity'):self.m.accept_take(dict(take,id=eid))
  self.assertIs(self.m.state,old);self.assertEqual(self.m.pending,pending)
