import copy
import ctypes as C
import importlib.util
import json
import math
import os
import subprocess
import fcntl
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from app import Engine,Instrument
from model import Model
from midi import MidiParser,MidiDispatch
from graphics import render,recovery_frame
import supervisor
from recovery import RecoveryControls


class Mixer(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.m=Model(Path(self.tmp.name)/'current.json');self.e=Engine(ROOT/'.build/engine.so');self.e.lib.sw_reset();self.e.sync(self.m);self.i=Instrument(self.m,self.e)
  self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
 def audio(self,seconds):
  n=round(seconds*44100);out=(C.c_float*(n*2))();self.e.lib.sw_render(out,n);return list(out)
 def rms(self,pcm):return math.sqrt(sum(v*v for v in pcm)/len(pcm))
 def test_mixer_all_eight_levels_global_master_and_undo(self):
  self.i.event('cc',112,127);self.assertEqual(self.m.view,'mixer');old=copy.deepcopy(self.m.state)
  for t in range(8):
   before=copy.deepcopy(self.m.state);self.i.event('cc',71+t,1)
   self.assertAlmostEqual(self.m.state['tracks'][t]['level'],before['tracks'][t]['level']+.02)
   self.assertEqual(self.m.state['master'],old['master'])
   self.i.event('cc',119,127);self.assertEqual(self.m.state,before)
  self.i.event('cc',79,1);self.assertAlmostEqual(self.m.state['master'],old['master']+.01)
  self.assertGreater(self.m.master_until,0);self.assertEqual(Model(self.m.path).state,self.m.state)
  self.i.event('cc',112,127);self.assertEqual(self.m.view,'instrument')
  self.i.event('cc',78,1);self.assertAlmostEqual(self.m.state['master'],old['master']+.02)
 def test_held_voice_fader_and_mute_are_continuous_and_smoothed(self):
  self.m.state['space']=0;self.e.sync(self.m);self.i.event('cc',50,127)
  self.i.wire(dict(kind='note',channel=2,number=60,value=100));self.audio(.7)
  base=self.rms(self.audio(.1));old=copy.deepcopy(self.m.state);last=self.audio(.01)[-2]
  self.m.execute(dict(op='set_track_parameters',track=4,parameters={'level':0},revision=self.m.revision));self.e.sync(self.m)
  fade=self.audio(.4);self.assertLess(self.rms(fade[-4000:]),base*.0001)
  self.assertLess(max(abs(b-a) for a,b in zip([last]+fade[::2],fade[::2])),.01)
  self.assertTrue(self.e.stats()['manual'][0]['held'])
  self.m.execute(dict(op='undo',revision=self.m.revision));self.e.sync(self.m);self.audio(.3)
  self.assertGreater(self.rms(self.audio(.1)),base*.7);self.assertEqual(self.m.state,old)
  self.i.event('cc',24,127);self.audio(.4);self.assertLess(self.rms(self.audio(.1)),base*.0001)
  self.i.event('cc',24,127);self.audio(.3);self.assertGreater(self.rms(self.audio(.1)),base*.6)
 def test_released_voice_level_changes_without_new_onset_or_squared_level(self):
  self.m.state['space']=0;self.e.sync(self.m);self.i.event('cc',50,127)
  self.i.wire(dict(kind='note',channel=2,number=60,value=100));self.audio(.5)
  before=self.e.stats()['onsets'];self.i.wire(dict(kind='note_off',channel=2,number=60,value=0))
  self.m.execute(dict(op='set_track_parameters',track=4,parameters={'level':0},revision=self.m.revision));self.e.sync(self.m);self.audio(.25)
  self.assertLess(self.rms(self.audio(.05)),1e-7);self.assertEqual(self.e.stats()['onsets'],before)
  # Compare deterministic, mature held notes at two levels: gain ratio should
  # be ~2, not4. Low master avoids limiter compression.
  energy=[]
  for level in (.2,.4):
   self.e.lib.sw_reset();self.e.previous=None;self.e.playing=None
   self.m.state['tracks'][4]['level']=level;self.m.state['master']=.05;self.e.sync(self.m)
   self.e.manual_on(0,123,4,62,.5);self.audio(.8);energy.append(self.rms(self.audio(.1)))
  self.assertAlmostEqual(energy[1]/energy[0],2,delta=.03)
 def test_view_frames_brand_master_and_help_remain_visible(self):
  def header(frame):return b''.join(frame[y*2048:y*2048+1920] for y in range(19))
  main=render(self.m,0,0);self.m.view='mixer';mix=render(self.m,0,0)
  helpframe=render(self.m,0,0,telemetry={'help':True,'recording':dict(state='saving',seconds=3)})
  self.assertNotEqual(main,mix);self.assertEqual(len(mix),327680)
  # Help overlays never cover the fixed brand/master strip.
  self.assertEqual(header(helpframe),header(render(self.m,0,0,telemetry={'recording':dict(state='saving',seconds=3)})))
  self.assertEqual(len(recovery_frame('missing native engine',3)),327680)
 def test_recording_capture_and_preview_keep_tag_values_and_selection_visible(self):
  def lower(frame):return b''.join(frame[y*2048:y*2048+1920] for y in range(144,160))
  def first_value(frame):return b''.join(frame[y*2048:y*2048+240] for y in range(144,151))
  self.m.selected=0
  for view in ('instrument','mixer'):
   self.m.view=view
   for status in ({'recording':{'state':'recording'}},{'recording':{'state':'saving'}},{'capture':{'busy':True,'seconds':2}},{}):
    for preview in (False,True):
     with self.subTest(view=view,status=status,preview=preview):
      self.m.execute(dict(op='cancel_preview'))
      if preview:self.m.execute(dict(op='propose_pattern',track=0,pattern=[60]+[0]*7,revision=self.m.revision,id='readable'))
      self.m.state['tracks'][0]['level']=.45
      plain=render(self.m,0,1)
      a=render(self.m,0,1,telemetry=status)
      self.m.state['tracks'][0]['level']=.99
      b=render(self.m,0,1,telemetry=status)
      self.assertNotEqual(first_value(a),first_value(b))
      self.assertEqual(lower(plain),lower(a))

 def test_recent_onset_rings_never_overwrite_label_or_value_glyphs(self):
  from graphics import VisualState,FONT,macro_values
  def glyphs(x,y,text):
   for ch in text:
    glyph=FONT.get(ch)
    if not glyph:x+=8;continue
    for yy,row in enumerate(glyph):
     for xx,bit in enumerate(row):
      if bit=='1':
       for dy in range(2):
        for dx in range(2):yield ((y+yy*2+dy)*1024+x+xx*2+dx)*2
    x+=(len(glyph[0])+1)*2
  for view in ('instrument','mixer'):
   self.m.view=view
   def visual(rings):
    v=VisualState();v.last=.4;v.levels=[.5]*8;v.rings=[list(rings) for _ in range(8)];return v
   stats=dict(envelopes=[.25]*8,onsets=[0]*8)
   plain=render(self.m,0,.5,telemetry=stats,visual=visual([]))
   active=render(self.m,0,.5,telemetry=stats,visual=visual([0,.1,.2]))
   self.assertNotEqual(plain,active)
   names=['TIDE','DRIFT','MOON','BLOOM','PEBBLE','CLOUD','DUSK','FIREFLY'] if view=='mixer' else ['LEVEL','TONE','TAIL','SPACE','TEMPO','ROOT','SPARKLE','MASTER']
   values=['%03d%%'%round(t['level']*100) for t in self.m.state['tracks']] if view=='mixer' else macro_values(self.m)[1]
   for t,(name,value) in enumerate(zip(names,values)):
    for y,text in ((120,name),(140,value)):
     for offset in glyphs(t*120+59-len(text)*6,y,text):
      self.assertEqual(plain[offset:offset+2],active[offset:offset+2],(view,t,y))

 def test_existing_sequencer_tail_responds_to_track_mute(self):
  self.m.state['space']=0;self.e.sync(self.m);self.e.command(5,0,38,.8)
  self.assertGreater(self.rms(self.audio(.3)),.0001)
  before=self.e.stats()['onsets'];self.i.event('cc',20,127);self.audio(.4)
  self.assertLess(self.rms(self.audio(.1)),1e-7);self.assertEqual(self.e.stats()['onsets'],before)
 def test_macro_feedback_is_transient_and_native_motion_is_local(self):
  self.i.event('cc',72,1);self.assertEqual(self.m.control['index'],1)
  until=self.m.control['until'];self.assertGreater(until,0)
  edited=render(self.m,0,until-1);expired=render(self.m,0,until+1)
  self.assertNotEqual(edited,expired)
  from graphics import VisualState
  v=VisualState();quiet=dict(envelopes=[0]*8,onsets=[0]*8)
  render(self.m,0,0,telemetry=quiet,visual=v)
  active=dict(envelopes=[0,0,.6,0,0,0,0,0],onsets=[0,0,1,0,0,0,0,0])
  frame=render(self.m,0,.1,telemetry=active,visual=v)
  self.assertGreater(v.levels[2],0);self.assertTrue(v.rings[2])
  self.assertTrue(all(v.levels[t]==0 and not v.rings[t] for t in range(8) if t!=2))
  self.assertEqual(len(frame),327680)



class ReceiptTiming(unittest.TestCase):
 def test_short_settings_tap_around_slow_gain_backlog_never_exits(self):
  with tempfile.TemporaryDirectory() as d:
   m=Model(Path(d)/'current.json')
   class Silent:
    def sync(self,m):pass
    def command(self,*args):pass
   i=Instrument(m,Silent());clock=[100.];dispatch=MidiDispatch(clock=lambda:clock[0]);p=MidiParser()
   batch=p.feed(bytes([176,30,127])+bytes([176,79,1,176,79,127])*100+bytes([176,30,0]))
   def save():clock[0]+=.020
   batches=iter([batch])
   def reader():return next(batches,[])
   with patch.object(m,'save',side_effect=save),patch('app.time.monotonic',side_effect=lambda:clock[0]):
    while dispatch.pending or m.revision==0:
     dispatch.process(reader,i.wire,i.received);i.tick();self.assertFalse(i.exit)
   self.assertEqual(m.revision,200);self.assertIsNone(i.gear)
 def test_next_read_settings_release_bypasses_slow_ordered_edits(self):
  with tempfile.TemporaryDirectory() as d:
   m=Model(Path(d)/'current.json')
   class Silent:
    def sync(self,m):pass
    def command(self,*args):pass
   i=Instrument(m,Silent());clock=[100.];dispatch=MidiDispatch(clock=lambda:clock[0]);p=MidiParser()
   batches=iter([p.feed(bytes([176,30,127])+bytes([176,79,1,176,79,127])*100),p.feed(bytes([176,30,0,146,60,100,130,60,0]))])
   seen=[];reads=[]
   def reader():reads.append(1);return next(batches,[])
   def handle(event):
    seen.append(event)
    if event['kind']=='cc':i.wire(event)
   with patch.object(m,'save',side_effect=lambda:clock.__setitem__(0,clock[0]+.020)),patch('app.time.monotonic',side_effect=lambda:clock[0]):
    dispatch.process(reader,handle,i.received)
    while dispatch.pending:
     dispatch.process(reader,handle,i.received);i.tick();self.assertFalse(i.return_stock)
   self.assertGreater(len(reads),2);self.assertEqual(m.revision,200);self.assertIsNone(i.gear)
   self.assertEqual([e['kind'] for e in seen[-2:]],['note','note_off'])
 def test_backpressure_bounds_queue_and_suspends_stale_hold(self):
  clock=[100.];dispatch=MidiDispatch(clock=lambda:clock[0],max_pending=4);seen=[];observed=[];reads=[]
  batches=iter([[0,1,2,3],[4,5,6,7],[8,9]])
  def reader():reads.append(1);return next(batches,[])
  def handle(event):seen.append(event);clock[0]+=.03
  for _ in range(10):
   dispatch.process(reader,handle,lambda batch,now:observed.append(batch))
   self.assertLess(len(dispatch.pending),8)
  self.assertIn(None,observed);self.assertEqual(seen,list(range(10)))

 def test_real_received_hold_and_recovery_release(self):
  controls=RecoveryControls();p=MidiParser()
  self.assertIsNone(controls.receive(p.feed(bytes([176,30,127])),10))
  self.assertEqual(controls.receive([],12.1),'return-stock')
  controls=RecoveryControls()
  self.assertIsNone(controls.receive(p.feed(bytes([176,30,127,30,0])),20))
  self.assertIsNone(controls.receive([],24))
  self.assertEqual(controls.receive(p.feed(bytes([176,85,127])),25),'retry-stillwater')


class Lifecycle(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.home=Path(self.tmp.name);(self.home/'enabled').touch();(self.home/'boot-pending').touch()
  self.clock=[100.];self.events=[]
 def harness(self,outcomes,blocked=False):
  test=self
  class Fake(supervisor.Supervisor):
   def launch(self,recovery,reason,attempt):
    test.events.append(('launch',recovery,attempt));self.child=type('Child',(),{'pid':123})()
   def stop_child(self):
    if self.child:
     test.events.append(('stop',));
     if blocked:return False
     self.child=None
    return True
   def monitor(self,recovery=False):
    outcome=outcomes.pop(0)
    if outcome[0]=='shutdown':self.shutdown=True
    return outcome
   def stock(self):test.events.append(('stock',))
  return Fake(self.home,self.home,clock=lambda:self.clock[0],sleep=lambda seconds:self.clock.__setitem__(0,self.clock[0]+seconds))
 def run_fake(self,s):
  with patch.object(supervisor.process,'record'):return s.run()
 def test_startup_stall_crash_enter_quiet_recovery_keep_enabled(self):
  s=self.harness([('fault','startup timeout',False),('fault','stalled',False),('fault','crash',False),('shutdown','stop',False)])
  self.assertEqual(self.run_fake(s),0)
  self.assertEqual([e for e in self.events if e[0]=='launch'],[('launch',False,1),('launch',False,2),('launch',False,3),('launch',True,3)])
  self.assertNotIn(('stock',),self.events);self.assertTrue((self.home/'enabled').exists())
  for n,e in enumerate(self.events):
   if e[0]=='launch' and n:self.assertEqual(self.events[n-1],('stop',))
 def test_explicit_stock_only_after_release_keeps_boot_preference(self):
  s=self.harness([('stock','Settings',False)]);self.assertEqual(self.run_fake(s),0)
  self.assertEqual(self.events,[('launch',False,1),('stop',),('stock',)])
  self.assertTrue((self.home/'enabled').exists())
 def test_unreleased_owner_blocks_stock_and_retries(self):
  s=self.harness([('stock','Settings',False)],blocked=True)
  self.assertEqual(self.run_fake(s),1);self.assertNotIn(('stock',),self.events)
  self.assertEqual(sum(e[0]=='launch' for e in self.events),1)
  self.assertEqual(json.loads((self.home/'recovery-status.json').read_text())['state'],'ownership-blocked')
 def test_recovery_explicit_retry_resets_attempt_budget(self):
  fault=('fault','broken engine',False)
  s=self.harness([fault,fault,fault,('retry','Play',False),('shutdown','stop',False)])
  self.assertEqual(self.run_fake(s),0);self.assertEqual([e for e in self.events if e[0]=='launch'][-1],('launch',False,1))
  self.assertNotIn(('stock',),self.events)
 def test_shutdown_during_backoff_does_not_launch_or_stock(self):
  s=self.harness([('fault','broken',False)])
  def pause(seconds):
   if seconds>0:s.shutdown=True
  s.pause=pause;self.assertEqual(self.run_fake(s),0);self.assertEqual(self.events,[('launch',False,1),('stop',)])
 def test_actual_monitor_sees_explicit_request_even_if_child_exited(self):
  s=supervisor.Supervisor(self.home,self.home);s.child=type('Child',(),{'poll':lambda self:1})()
  (self.home/'return-stock').touch();self.assertEqual(s.monitor()[0],'stock')
  (self.home/'return-stock').unlink();(self.home/'retry-stillwater').touch()
  self.assertEqual(s.monitor(True)[0],'retry')
 def test_actual_monitor_startup_timeout_crash_and_stale_metrics(self):
  s=supervisor.Supervisor(self.home,self.home,clock=lambda:self.clock[0],sleep=lambda seconds:self.clock.__setitem__(0,self.clock[0]+seconds))
  s.child=type('Child',(),{'pid':7,'poll':lambda self:None})();s.start='42'
  self.assertEqual(s.monitor()[:2],('fault','startup timeout'))
  self.clock[0]=100;s.child=type('Child',(),{'pid':7,'poll':lambda self:1})()
  self.assertEqual(s.monitor()[:2],('fault','application exited'))
  self.clock[0]=100;s.child=type('Child',(),{'pid':7,'poll':lambda self:None})();(self.home/'ready').touch()
  (self.home/'metrics.json').write_text(json.dumps(dict(pid=7,start_ticks='42',uptime=90,audio=dict(alive=True,frames=1,written_frames=1),display_frames=1)))
  outcome,reason,_=s.monitor();self.assertEqual(outcome,'fault');self.assertIn('stale/dead',reason)
  self.assertLess(self.clock[0],104)
 def test_monitor_requires_actual_audio_and_display_progress(self):
  s=supervisor.Supervisor(self.home,self.home,clock=lambda:self.clock[0]);s.child=type('Child',(),{'pid':7,'poll':lambda self:None})();s.start='42'
  (self.home/'ready').touch()
  def update(seconds):
   self.clock[0]+=seconds
   (self.home/'metrics.json').write_text(json.dumps(dict(pid=7,start_ticks='42',uptime=self.clock[0],audio=dict(alive=True,frames=100,written_frames=100),display_frames=int(self.clock[0]))))
  s.pause=update;update(0)
  result=s.monitor();self.assertEqual(result[0],'fault');self.assertIn('progress stalled',result[1])
 def test_stop_with_unknown_live_identity_fails_closed(self):
  s=supervisor.Supervisor(self.home,self.home);s.child=type('Child',(),{'pid':7,'poll':lambda self:None})();s.start=None
  with patch.object(supervisor.process,'terminate') as terminate:
   self.assertFalse(s.stop_child());terminate.assert_not_called()
 def test_inherited_live_child_is_released_before_new_registry(self):
  child=subprocess.Popen(['/usr/bin/python3','-c','import time;time.sleep(60)'])
  self.addCleanup(child.wait);self.addCleanup(lambda:child.poll() is None and child.kill())
  s=self.harness([('shutdown','stop',False)])
  old=dict(supervisor=[99999999,'1'],child=[child.pid,supervisor.process.identity(child.pid)])
  registry=self.home/'stillwater-owned.json';registry.write_text(json.dumps(old))
  original=s.launch
  def launch(*args):
   self.assertFalse(supervisor.process.alive(*old['child']));original(*args)
  s.launch=launch
  self.assertEqual(self.run_fake(s),0)
 def test_blocked_inherited_child_retains_exact_registry(self):
  child=subprocess.Popen(['/usr/bin/python3','-c','import time;time.sleep(60)'])
  self.addCleanup(child.wait);self.addCleanup(lambda:child.poll() is None and child.kill())
  s=self.harness([]);registry=self.home/'stillwater-owned.json'
  original=json.dumps(dict(supervisor=[99999999,'1'],child=[child.pid,supervisor.process.identity(child.pid)]))
  registry.write_text(original)
  with patch.object(supervisor.process,'terminate',return_value=False):self.assertEqual(self.run_fake(s),1)
  self.assertEqual(registry.read_text(),original);self.assertEqual(self.events,[])
  self.assertIsNotNone(supervisor.process.identity(child.pid))
 def test_live_prior_supervisor_and_singleton_fail_closed(self):
  s=self.harness([]);registry=self.home/'stillwater-owned.json'
  original=json.dumps(dict(supervisor=[os.getpid(),supervisor.process.identity(os.getpid())],child=None));registry.write_text(original)
  self.assertEqual(self.run_fake(s),1);self.assertEqual(registry.read_text(),original)
  with open(self.home/'stillwater-supervisor.lock','a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   self.assertEqual(self.run_fake(s),1)
  self.assertEqual(self.events,[]);self.assertEqual(registry.read_text(),original)

 def test_real_child_failures_recover_and_explicit_escape_releases_owners(self):
  # Real subprocesses/identity/termination with inert temporary payloads. No
  # ALSA, USB, live state or actual stock commands are reachable from this tree.
  for directory in ('src','scripts','recovery'):(self.home/directory).mkdir()
  (self.home/'src/app.py').write_text("raise RuntimeError('simulated missing native engine')\n")
  (self.home/'scripts/recovery.py').write_text("from pathlib import Path\nPath(__file__).resolve().parents[1].joinpath('return-stock').touch()\n")
  stock=self.home/'recovery/push3.stock';stock.write_text('#!/bin/sh\ntouch "$(dirname "$0")/stock-explicit"\n');stock.chmod(0o700)
  class Fast(supervisor.Supervisor):
   def pause(self,seconds):
    if seconds<=1:super().pause(min(seconds,.01))
  s=Fast(self.home,self.home)
  self.assertEqual(s.run(),0)
  self.assertTrue((self.home/'recovery/stock-explicit').exists());self.assertTrue((self.home/'enabled').exists())
  self.assertFalse((self.home/'stillwater-owned.json').exists());self.assertIsNone(s.child)
  log=(self.home/'service.log').read_text();self.assertEqual(log.count('simulated missing native engine'),6)
  self.assertIn('Stillwater: recovery',log)

if __name__=='__main__':unittest.main()
