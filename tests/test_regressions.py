import copy
import ctypes as C
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from app import atomic_metrics, Instrument
from midi import MidiDispatch, MidiParser
from model import Model,seeded

def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
health=module('sw_health',ROOT/'scripts/health.py')
process=module('sw_process',ROOT/'scripts/process.py')

class EncoderDispatch(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.m=Model(Path(self.tmp.name)/'current.json')
  class SilentEngine:
   def sync(self,model):pass
   def command(self,*args):pass
  self.i=Instrument(self.m,SilentEngine())
 def test_both_gain_encoders_save_changes_but_not_clamped_or_zero_turns(self):
  for number in (78,79):
   self.m.state['master']=0;before=self.m.revision
   with patch.object(self.m,'save',wraps=self.m.save) as save:
    for value in [127]*80+[0]:self.i.event('cc',number,value)
    self.assertEqual(save.call_count,0);self.assertEqual(self.m.revision,before)
    self.i.event('cc',number,1)
    self.assertEqual(save.call_count,1);self.assertEqual(Model(self.m.path).state['master'],.01)
   self.m.state['master']=1;before=self.m.revision
   self.i.event('cc',number,1);self.assertEqual(self.m.revision,before)
 def test_dense_gain_batch_yields_before_watchdog_and_keeps_every_event(self):
  # Device reproduction: ~19ms per synchronous full-history save. Alternating
  # turns force real edits, so this covers more than the clamped no-op shortcut.
  clock=[100.];dispatch=MidiDispatch(clock=lambda:clock[0]);parser=MidiParser()
  wire=bytes([176,78,1,176,79,127])*500
  batch=parser.feed(wire);seen=[];reads=[];samples=0
  def reader():
   reads.append(1);return batch if len(reads)==1 else []
  def handler(event):
   seen.append(event);self.i.wire(event);clock[0]+=.019
  def save():clock[0]+=.001
  counters=1
  _,state=health.assess(Health().metrics(now=100,frames=1,written=1,display=1),7,'42',100)
  with patch.object(self.m,'save',side_effect=save):
   while len(seen)<len(batch):
    start=clock[0];count=dispatch.process(reader,handler)
    self.assertLessEqual(count,2);self.assertLess(clock[0]-start,.041)
    counters+=1;samples+=1
    code,state=health.assess(Health().metrics(now=clock[0],frames=counters,written=counters,display=counters),7,'42',clock[0],state)
    self.assertEqual(code,0)
  self.assertEqual(seen,batch);self.assertGreater(len(reads),1)
  self.assertGreater(samples,400);self.assertEqual(self.m.revision,1000)
  self.assertAlmostEqual(self.m.state['master'],.28)
 def test_backlog_preserves_note_release_while_observing_next_reads(self):
  clock=[0.];dispatch=MidiDispatch(clock=lambda:clock[0]);p=MidiParser()
  batch=p.feed(bytes([176,79,1,146,60,100,130,60,0,176,29,127]));seen=[];reads=[]
  def reader():
   reads.append(1);return batch if len(reads)==1 else []
  def handler(event):seen.append(event);clock[0]+=.03
  for _ in batch:self.assertEqual(dispatch.process(reader,handler),1)
  self.assertEqual(seen,batch);self.assertGreater(len(reads),1)
  self.assertEqual([e['kind'] for e in seen],['cc','note','note_off','cc'])
 def test_empty_read_and_one_slow_event_still_return(self):
  clock=[0.];dispatch=MidiDispatch(clock=lambda:clock[0])
  self.assertEqual(dispatch.process(lambda:[],lambda e:None),0)
  def handler(event):clock[0]+=1
  self.assertEqual(dispatch.process(lambda:[1,2],handler),1)
  self.assertEqual(list(dispatch.pending),[2])
 def test_power_flags_still_request_stock_return(self):
  self.i.wire(dict(kind='sysex',number=[240,0,33,29,1,1,58,8,0,247],value=0,channel=None))
  self.assertTrue(self.i.exit)

class Health(unittest.TestCase):
 def metrics(self,now=100,frames=44100,written=44000,display=10,pid=7):
  return dict(pid=pid,start_ticks='42',uptime=now,audio=dict(alive=True,frames=frames,written_frames=written),display_frames=display)
 def test_stalled_positive_counters_expire_despite_fresh_metrics(self):
  code,state=health.assess(self.metrics(),7,'42',100);self.assertEqual(code,2)
  code,state=health.assess(self.metrics(103),7,'42',103,state);self.assertEqual(code,2)
  code,state=health.assess(self.metrics(107),7,'42',107,state);self.assertEqual(code,1)
 def test_render_and_ui_progress_without_pcm_writes_fail(self):
  _,state=health.assess(self.metrics(),7,'42',100)
  code,_=health.assess(self.metrics(107,88200,44000,80),7,'42',107,state);self.assertEqual(code,1)
 def test_successful_counters_advance(self):
  _,state=health.assess(self.metrics(),7,'42',100)
  code,state=health.assess(self.metrics(102,88200,88000,30),7,'42',102,state);self.assertEqual(code,0);self.assertEqual(state['progress_at'],102)
 def test_pid_and_start_identity_rejected(self):
  for pid,start in [(8,'42'),(7,'99')]:
   with self.assertRaises(ValueError):health.assess(self.metrics(),pid,start,100)
 def test_stale_metrics_rejected(self):
  with self.assertRaises(ValueError):health.assess(self.metrics(),7,'42',108)
 def test_atomic_metrics_concurrent_reader(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'metrics.json';atomic_metrics(p,self.metrics());errors=[];stop=threading.Event()
   def read():
    while not stop.is_set():
     try:json.loads(p.read_text())
     except Exception as e:errors.append(e)
   thread=threading.Thread(target=read);thread.start()
   try:
    for i in range(150):atomic_metrics(p,self.metrics(frames=i))
   finally:stop.set();thread.join()
   self.assertFalse(errors)

class Persistence(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'current.json';self.m=Model(self.path)
 def test_failed_replace_keeps_one_old_state_revision_and_undo(self):
  self.m.execute(dict(op='set_tempo',value=70,revision=0));old=self.path.read_bytes()
  with patch('model.os.replace',side_effect=OSError('simulated power-loss before rename')):
   with self.assertRaises(OSError):self.m.execute(dict(op='set_tempo',value=80,revision=1))
  self.assertEqual(self.path.read_bytes(),old)
  loaded=Model(self.path);self.assertEqual(loaded.revision,1);self.assertEqual(loaded.state['tempo'],70)
  loaded.execute(dict(op='undo',revision=1));self.assertEqual(loaded.state['tempo'],58)
 def test_single_envelope_does_not_depend_on_legacy_journal(self):
  self.m.execute(dict(op='set_tempo',value=80,revision=0))
  self.path.with_suffix('.history.json').write_text('invalid stale old file')
  loaded=Model(self.path);self.assertEqual(loaded.revision,1);self.assertEqual(loaded.state['tempo'],80)
  self.assertEqual(json.loads(self.path.read_text())['version'],3)
 def test_matching_legacy_preserves_scene_revision_and_undo(self):
  old=seeded();scene=seeded();scene['tempo']=80
  self.path.write_text(json.dumps(scene));self.path.with_suffix('.history.json').write_text(json.dumps(dict(state=scene,revision=7,history=[old])))
  loaded=Model(self.path);self.assertEqual(loaded.revision,7);self.assertEqual(loaded.state,scene)
  loaded.execute(dict(op='undo',revision=7));self.assertEqual(loaded.state,old)
 def test_legacy_ambiguity_fails_closed_and_preserves_files(self):
  scene=seeded();scene['tempo']=80;self.path.write_text(json.dumps(scene));before=self.path.read_bytes()
  with self.assertRaisesRegex(ValueError,'ambiguous'):Model(self.path)
  self.path.with_suffix('.history.json').write_text(json.dumps(dict(state=seeded(),revision=0,history=[])))
  with self.assertRaisesRegex(ValueError,'mismatch'):Model(self.path)
  self.assertEqual(self.path.read_bytes(),before)
 def test_proposals_do_not_accumulate_after_40_edits(self):
  for i in range(40):
   rev=self.m.revision
   self.m.execute(dict(op='propose_pattern',track=4,pattern=[62]+[0]*7,id='p%d'%i,revision=rev))
   self.m.execute(dict(op='set_tempo',value=60+i,revision=rev))
   self.assertEqual(self.m.proposals,{})
  self.m.execute(dict(op='propose_pattern',track=4,pattern=[62]+[0]*7,id='last',revision=self.m.revision))
 def test_undo_prunes_proposals(self):
  self.m.execute(dict(op='set_tempo',value=80,revision=0));self.m.execute(dict(op='propose_pattern',track=4,pattern=[62]*8,id='a',revision=1))
  self.m.execute(dict(op='undo',revision=1));self.assertFalse(self.m.proposals)

class Shutdown(unittest.TestCase):
 def test_owned_process_ignoring_term_is_killed_within_bound(self):
  with tempfile.TemporaryDirectory() as d:
   ready=Path(d)/'ready'
   child=subprocess.Popen([sys.executable,'-c','import signal,time,pathlib,sys;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path(sys.argv[1]).touch();time.sleep(60)',str(ready)])
   try:
    deadline=time.monotonic()+2
    while not ready.exists() and time.monotonic()<deadline:time.sleep(.01)
    self.assertTrue(ready.exists());start=process.identity(child.pid);before=time.monotonic()
    self.assertTrue(process.terminate(child.pid,start,grace=.1));self.assertLess(time.monotonic()-before,2.5)
   finally:child.kill() if child.poll() is None else None;child.wait(timeout=2)
 def test_reused_pid_identity_never_signalled(self):
  self.assertTrue(process.terminate(os.getpid(),'definitely-not-my-start',grace=0))
  self.assertIsNotNone(process.identity(os.getpid()))
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.lib=Path(cls.tmp.name)/'libasound.so.2'
  subprocess.run(['gcc','-shared','-fPIC',str(ROOT/'tests/fake_alsa.c'),'-o',str(cls.lib)],check=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def native_stop(self,blocked):
  env=dict(os.environ,LD_LIBRARY_PATH=self.tmp.name)
  if blocked:env['SW_TEST_BLOCK_FOREVER']='1'
  code='''import ctypes as C,time,json
lib=C.CDLL(%r);lib.sw_start.argtypes=[C.c_char_p];assert lib.sw_start(b'fake')==0
time.sleep(.05);t=time.monotonic();ret=lib.sw_stop();print(json.dumps(dict(result=ret,seconds=time.monotonic()-t)),flush=True)
'''%str(ROOT/'.build/engine.so')
  out=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=5,check=True)
  return json.loads(out.stdout)
 def test_nonblocking_pcm_eagain_stop_finishes(self):
  result=self.native_stop(False);self.assertEqual(result['result'],0);self.assertLess(result['seconds'],.5)
 def test_broken_pcm_driver_join_is_bounded(self):
  result=self.native_stop(True);self.assertEqual(result['result'],-1);self.assertLess(result['seconds'],3)

if __name__=='__main__':unittest.main()
