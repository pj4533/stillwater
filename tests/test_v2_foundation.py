"""Offline V2 foundation acceptance: immutable persistence and sample timing."""
import copy
import ctypes as C
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,SessionWriter,Event,blank,json_ready,decode_song,pad_pitch,read_envelope,atomic_write,LOOP_TICKS
from loop_engine import LoopEngine,LoopPerformance,SongBank,bank_for
from midi import MidiParser
from model import seeded
from roles import ROLE_IDS


_v3_blank=blank
def blank(*args,**kwargs):return replace(_v3_blank(*args,**kwargs),loop_beats=16)


class ModelV2(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'current-v2.json'
  self.m=LoopModel(self.path,writer=False,seed=31)
  self.m.state=replace(self.m.state,loop_beats=16)  # Retained V2 fixture.
 def test_blank_deck_and_unique_roles_undo_redo_exact(self):
  self.assertEqual(len(self.m.state.layers),1);self.assertFalse(self.m.state.layers[0].events)
  # This regression isolates identity/history; V3 progression is tested separately.
  self.m.role_state=lambda role:'USED' if any(l.role==role for l in self.m.state.layers) else 'READY'
  states=[self.m.state]
  for _ in range(7):self.assertTrue(self.m.add_layer());states.append(self.m.state)
  self.assertEqual(set(l.role for l in self.m.state.layers),set(ROLE_IDS));self.assertFalse(self.m.add_layer())
  for state in reversed(states[:-1]):self.assertTrue(self.m.undo());self.assertEqual(self.m.state,state)
  for state in states[1:]:self.assertTrue(self.m.redo());self.assertEqual(self.m.state,state)
 def test_shared_layers_and_encoder_grouping_dont_swallow_note_edits(self):
  self.m.add_layer();original=self.m.state
  self.m.set_parameter(0,0,.1,now=1);self.m.set_parameter(0,0,.2,now=1.1)
  self.assertIs(self.m.state.layers[1],original.layers[1]);self.m.undo();self.assertEqual(self.m.state,original)
  self.m.set_parameter(0,0,.1,now=2)
  eid=self.m.reserve(0,1,0)
  self.m.accept_take(dict(id=eid,epoch=self.m.capture_epoch,layer=0,pitch=62,velocity=.5,start_tick=0,duration_tick=96000))
  self.m.set_parameter(0,0,.2,now=2.1);self.m.undo()
  self.assertEqual(self.m.state.layers[0].parameters[0],.1);self.assertEqual(len(self.m.state.layers[0].events),1)
  self.m.undo();self.assertFalse(self.m.state.layers[0].events)
 def test_capture_epoch_cancel_prevents_delayed_ack_resurrection(self):
  eid=self.m.reserve(0,1,0);epoch=self.m.capture_epoch;old=self.m.state
  self.assertEqual(self.m.undo(),'cancel');self.assertFalse(self.m.accept_take(dict(id=eid,epoch=epoch)))
  self.assertEqual(self.m.state,old);self.assertFalse(self.m.redo())
 def test_empty_redo_is_noop_with_pending_capture(self):
  self.m.reserve(0,1,0);epoch=self.m.capture_epoch;pending=dict(self.m.pending)
  self.assertFalse(self.m.redo());self.assertEqual(self.m.capture_epoch,epoch);self.assertEqual(self.m.pending,pending)
 def test_new_archive_completion_cannot_replace_new_pending_note(self):
  self.m.writer=type('Writer',(),dict(results=queue.Queue(),task=lambda *args:None))()
  self.m.request_new();old=self.m.state;self.m.reserve(0,1,0);pending=dict(self.m.pending)
  self.m.writer.results.put(dict(kind='archive',revision=self.m.revision,request_token=self.m.replacement_request[0]))
  self.m.poll_tasks();self.assertIs(self.m.state,old);self.assertEqual(self.m.pending,pending)
  self.assertIn('CANCELLED',self.m.message)
 def test_history_bound_and_redo_invalidated_by_new_edit(self):
  for i in range(100):self.m.set_master((i%2)*.1,now=i)
  self.assertEqual(len(self.m.undo_stack),64)
  for _ in range(64):self.m.undo()
  self.assertEqual(len(self.m.redo_stack),64);self.m.set_master(.9)
  self.assertFalse(self.m.redo_stack)
 def test_pad_surface_whole_octaves_no_ceiling_clipping(self):
  for octave in (0,):
   pitches=[pad_pitch(n,octave) for n in range(36,100)]
   self.assertTrue(all(0<=p<=127 and (p-62)%12 in (0,2,3,5,7,9,10) for p in pitches))
   self.assertEqual(len(set(pitches)),64)
  for octave in (-1,1):
   with self.assertRaises(ValueError):pad_pitch(36,octave)
 def test_legacy_full_files_unchanged_master_inherited(self):
  legacy=self.path.with_name('current.json');state=seeded();state['master']=.7
  raw=json.dumps(dict(format='stillwater-session',version=3,revision=1380,state=state,history=[state]*64)).encode();legacy.write_bytes(raw)
  journal=legacy.with_suffix('.history.json');journal.write_bytes(b'original legacy journal bytes')
  model=LoopModel(self.path,legacy=legacy,writer=False)
  self.assertEqual(model.state.master,.7);self.assertEqual(legacy.read_bytes(),raw);self.assertEqual(journal.read_bytes(),b'original legacy journal bytes')
  self.assertFalse(self.path.exists());self.assertFalse(any(l.events for l in model.state.layers))
 def test_invalid_legacy_history_fails_without_rewriting(self):
  legacy=self.path.with_name('current.json');state=seeded();bad=copy.deepcopy(state);bad['tracks'][0]['pattern'][7]=2
  raw=json.dumps(dict(format='stillwater-session',version=3,revision=2,state=state,history=[bad])).encode();legacy.write_bytes(raw)
  with self.assertRaises(ValueError):LoopModel(self.path,legacy=legacy,writer=False)
  self.assertEqual(legacy.read_bytes(),raw);self.assertFalse(self.path.exists())
 def test_malformed_song_rejected(self):
  for mutate in (lambda s:s.update(tempo=float('nan')),lambda s:s['role_order'].__setitem__(0,s['role_order'][1]),lambda s:s['layers'][0].update(events=[dict(id=1,pitch=62,velocity=.5,start_tick=LOOP_TICKS,duration_tick=1)])):
   raw=json_ready(self.m.state);mutate(raw)
   with self.assertRaises(ValueError):decode_song(raw)
 def test_worker_slow_fsync_never_blocks_edits_and_older_write_cant_win(self):
  started=threading.Event();release=threading.Event();real_sync=os.fsync
  def sync(fd):started.set();release.wait(3);return real_sync(fd)
  writer=SessionWriter(self.path,debounce=0);self.addCleanup(writer.close)
  self.m.writer=writer
  with patch('loop_model.os.fsync',side_effect=sync):
   self.m.set_master(.3);self.assertTrue(started.wait(1))
   before=time.monotonic()
   for i in range(100):self.m.set_master(.4+i*.001,now=i)
   self.assertLess(time.monotonic()-before,.1)
   target=self.m.revision;release.set();self.assertTrue(writer.flush(target,3))
  self.assertEqual(read_envelope(self.path)['state'],self.m.state)
  writer.submit(dict(self.m.payload(),revision=0));time.sleep(.05)
  self.assertEqual(read_envelope(self.path)['revision'],target)
 def test_disk_failure_keeps_dirty_music_retryable(self):
  writer=SessionWriter(self.path,debounce=.01);self.addCleanup(writer.close);self.m.writer=writer
  with patch('loop_model.atomic_write',side_effect=OSError('disk full')):
   self.m.set_master(.8);self.assertFalse(writer.flush(self.m.revision,.05));self.assertTrue(self.m.dirty);self.assertEqual(self.m.state.master,.8)
  self.m.checkpoint(True);self.assertTrue(writer.flush(self.m.revision,2));self.assertFalse(self.m.dirty)
 def test_atomic_library_snapshot_and_new_archive(self):
  self.m.writer=SessionWriter(self.path,debounce=0);self.addCleanup(self.m.close)
  self.m.set_master(.67);self.m.request_new()
  deadline=time.monotonic()+2
  while self.m.new_revision is not None and time.monotonic()<deadline:self.m.poll_tasks();time.sleep(.002)
  self.assertIsNone(self.m.new_revision);self.assertEqual(self.m.state.master,.67)
  saved=list((self.path.parent/'saved').glob('*.json'));self.assertEqual(len(saved),1)
  archived=read_envelope(saved[0]);self.assertEqual(archived['state'].master,.67)
  self.assertTrue(self.m.undo());self.assertEqual(self.m.state,archived['state'])
  with self.assertRaises(FileExistsError):atomic_write(saved[0],self.m.payload(),True)
 def test_load_validates_on_worker_and_refuses_stale_completion(self):
  writer=SessionWriter(self.path,debounce=0);self.m.writer=writer;self.addCleanup(self.m.close)
  self.m.request_save()
  deadline=time.monotonic()+2
  while not list((self.path.parent/'saved').glob('*.json')) and time.monotonic()<deadline:time.sleep(.002)
  self.m.poll_tasks();name=next((self.path.parent/'saved').glob('*.json')).name
  self.m.set_master(.8);self.m.request_load(name)
  deadline=time.monotonic()+2;applied=False
  while time.monotonic()<deadline:
   results=self.m.poll_tasks()
   if any(r['kind']=='load' and r.get('applied') for r in results):applied=True;break
   time.sleep(.002)
  self.assertTrue(applied);self.assertEqual(self.m.state.master,.28)
  self.m.request_load(name);self.m.set_master(.9)
  deadline=time.monotonic()+2;stale=False
  while time.monotonic()<deadline:
   results=self.m.poll_tasks()
   if any(r['kind']=='load' and r.get('applied') is False for r in results):stale=True;break
   time.sleep(.002)
  self.assertTrue(stale);self.assertEqual(self.m.state.master,.9)
  with self.assertRaises(ValueError):self.m.request_load('../current.json')
 def test_archive_failure_never_replaces_current_song(self):
  self.m.writer=SessionWriter(self.path,debounce=0);self.addCleanup(self.m.close);old=self.m.state
  with patch('loop_model.atomic_write',side_effect=OSError('archive disk full')):
   self.m.request_new();deadline=time.monotonic()+2
   while self.m.new_revision is not None and time.monotonic()<deadline:self.m.poll_tasks();time.sleep(.002)
  self.assertEqual(self.m.state,old);self.assertIn('disk full',self.m.message)
 def test_roundtrip_history_and_full_file_validation(self):
  self.m.add_layer();self.m.set_master(1);self.m.undo()
  atomic_write(self.path,self.m.payload());loaded=LoopModel(self.path,writer=False)
  self.assertEqual(loaded.state,self.m.state);self.assertEqual(loaded.redo_stack,self.m.redo_stack)
  self.assertTrue(loaded.redo());self.assertEqual(loaded.state.master,1)
  raw=json.loads(self.path.read_text());raw['redo'][0]['layers'][0]['events']=[dict(id=1,pitch=3,velocity=1,start_tick=0,duration_tick=1)];self.path.write_text(json.dumps(raw));old=self.path.read_bytes()
  with self.assertRaises(ValueError):LoopModel(self.path,writer=False)
  self.assertEqual(self.path.read_bytes(),old)


class NativeV2(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.m=LoopModel(Path(self.tmp.name)/'current-v2.json',writer=False,seed=2)
  self.m.state=replace(self.m.state,loop_beats=16)  # Retained V2 fixture.
  self.e=LoopEngine(ROOT/'.build/engine.so');self.e.lib.sw_reset();self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  self.p=LoopPerformance(self.m,self.e);self.audio(1)
 def audio(self,n,chunk=256):
  pcm=[]
  while n:
   length=min(n,chunk);out=(C.c_float*(length*2))();self.e.lib.sw_render(out,length);pcm.extend(out);n-=length
  return pcm
 def wire(self,bytes_):
  for event in MidiParser().feed(bytes(bytes_)):self.p.wire(event)
 def close_note(self,frames=4410):
  self.wire([0x92,60,100]);self.audio(frames);self.wire([0x82,60,0]);self.audio(1);self.p.drain()
 def test_first_note_anchors_after_long_wait_sample_accuracy_all_buffers(self):
  for chunk in (1,64,256,137):
   with self.subTest(chunk=chunk):
    self.e.lib.sw_reset();self.e.generation=0;self.p=LoopPerformance(self.m,self.e);self.audio(1)
    self.p.play();self.audio(44100,chunk);before=self.e.loop_stats()
    self.assertEqual(before['transport'],1);self.assertEqual(before['phase'],0)
    self.wire([0x92,60,1]);self.audio(512,chunk);self.wire([0x82,60,0]);self.audio(1,chunk)
    take=self.e.takes()[0];self.m.pending.clear()
    self.assertEqual(take['start_tick'],0);self.assertAlmostEqual(take['duration_tick']*before['loop_frames']/LOOP_TICKS,512,delta=.5)
    self.assertAlmostEqual(take['velocity'],1/127,places=8)
 def test_master_and_bank_follow_one_ordered_queue(self):
  def render(order,split):
   self.e.lib.sw_reset();self.e.generation=0
   song=self.m.state;changed=replace(song,master=.9)
   self.e.publish(song,1);self.audio(1)
   for operation in order:
    if operation=='bank':self.e.publish(song,1)
    else:self.e.scalar_changes(song,changed)
    if split:self.audio(1)
   if not split:self.audio(len(order))
   self.e.lib.sw_performance_on(0,1,0,62,.5,0,1,100)
   return self.audio(4096),self.e.loop_stats()['activity']
  # Match exactly the same sample timing with explicitly interleaved blocks.
  for order in (('bank','master'),('master','bank')):
   queued,activity=render(order,False);separate,_=render(order,True)
   self.assertAlmostEqual(sum(x*x for x in queued)/sum(x*x for x in separate),1,delta=.001);self.assertEqual(activity,4)
  high,_=render(('bank','master'),False);low,_=render(('master','bank'),False)
  self.assertGreater(sum(x*x for x in high),sum(x*x for x in low)*5)
 def test_stopped_audition_and_all_channel_release(self):
  self.wire([0x92,60,100]);pcm=self.audio(2000);self.assertGreater(max(map(abs,pcm)),0)
  self.wire([0x83,60,0]);self.audio(1);self.assertEqual(self.e.loop_stats()['held'],1)
  self.wire([0x92,60,0]);self.audio(1);self.assertEqual(self.e.loop_stats()['held'],0)
  self.assertFalse(self.e.takes());self.assertFalse(self.m.state.layers[0].events)
 def test_layer_change_during_hold_keeps_onset_layer(self):
  self.p.play();self.wire([0x92,60,100]);self.audio(2000);self.p.add_layer();self.audio(1)
  self.assertEqual(self.e.loop_stats()['held'],1)
  self.wire([0x82,60,0]);self.audio(1);self.p.drain()
  self.assertEqual(len(self.m.state.layers[0].events),1);self.assertFalse(self.m.state.layers[1].events)
 def test_add_layer_before_queued_noteoff_ack_preserves_native_event(self):
  self.p.play();self.wire([0x92,60,100]);self.audio(100)
  self.wire([0x82,60,0]);self.p.add_layer()  # off and full bank are both queued.
  self.audio(1);self.p.drain()
  self.assertEqual(len(self.m.state.layers[0].events),1)
  self.assertEqual(self.e.loop_stats()['captures'],1)
  self.assertEqual(self.e.loop_stats()['generation'],2)
  before=self.e.stats()['onsets'][0];self.audio(self.e.loop_stats()['loop_frames'])
  self.assertEqual(self.e.stats()['onsets'][0],before+1)
 def test_consumed_ack_cannot_be_erased_by_stale_additive_bank(self):
  self.p.play();self.wire([0x92,60,100]);self.audio(100)
  self.m.add_layer();stale=self.m.state
  self.wire([0x82,60,0]);self.audio(1);self.p.drain()
  self.e.publish(stale,self.m.capture_epoch);self.audio(1)
  self.assertEqual(self.e.loop_stats()['captures'],1)
  before=self.e.stats()['onsets'][0];self.audio(self.e.loop_stats()['loop_frames'])
  self.assertEqual(self.e.stats()['onsets'][0],before+1)
  self.assertTrue(self.p.undo());self.audio(1)
  self.assertEqual(self.e.loop_stats()['captures'],0)
 def test_current_unrendered_sample_event_survives_release_and_publish(self):
  for chunk in (1,64,256,137):
   for operation in ('release','publish'):
    with self.subTest(chunk=chunk,operation=operation):
     self.e.lib.sw_reset();self.e.generation=0
     song=self.m.state;length=round(44100*60*16/song.tempo)
     tick=round(256*LOOP_TICKS/length)
     song=replace(song,layers=(replace(song.layers[0],events=(Event(500,62,.5,tick,1000),)),))
     self.e.publish(song,1);self.audio(1);self.e.transport(2,True,1)
     self.e.lib.sw_performance_on(0,1,0,65,.5,1,1,501);self.audio(256,chunk)
     before=self.e.stats()['onsets'][0]
     if operation=='release':self.e.lib.sw_performance_off(0,1)
     else:self.e.publish(song,1)
     self.audio(1,chunk);self.assertEqual(self.e.stats()['onsets'][0],before+1)
 def test_active_capture_reservation_rejects_full_publication_atomically(self):
  self.p.play();self.wire([0x92,60,100]);self.audio(64)
  generation=self.e.loop_stats()['generation']
  song=self.m.state
  full=replace(song,layers=(replace(song.layers[0],events=tuple(Event(i+1000,62,.5,i*5000,10) for i in range(256))),))
  self.e.publish(full,1);self.audio(1)
  self.assertEqual(self.e.loop_stats()['generation'],generation);self.assertEqual(self.e.loop_stats()['captures'],0)
  self.wire([0x82,60,0]);self.audio(1);self.p.drain()
  self.assertEqual(self.e.loop_stats()['captures'],1);self.assertEqual(len(self.m.state.layers[0].events),1)
  # A conflicting 256-event bank also cannot discard an already-consumed take.
  self.e.publish(full,1);self.audio(1)
  self.assertEqual(self.e.loop_stats()['generation'],generation);self.assertEqual(self.e.loop_stats()['captures'],1)
 def test_eight_active_capture_reservations_fit_exactly_256_events(self):
  self.e.transport(1,True,1)
  for i in range(8):self.e.lib.sw_performance_on(i,i+1,0,62,.5,1,1,i+1)
  self.audio(100)
  song=self.m.state
  full=replace(song,layers=(replace(song.layers[0],events=tuple(Event(i+1000,62,.5,i*5000,10) for i in range(248))),))
  self.e.publish(full,1);self.audio(1);self.assertEqual(self.e.loop_stats()['captures'],248)
  for i in range(8):self.e.lib.sw_performance_off(i,i+1)
  self.audio(1);self.assertEqual(self.e.loop_stats()['captures'],256)
  self.assertEqual(len(self.e.takes()),8);self.assertEqual(self.e.loop_stats()['held'],0)
 def test_same_sample_capture_does_not_retrigger_itself(self):
  self.p.play();self.wire([0x92,60,100,0x82,60,0]);self.audio(1)
  self.assertEqual(self.e.stats()['onsets'][0],1);self.assertEqual(self.e.loop_stats()['captures'],1)
 def test_maxhold_one_loop_then_replay_without_duplicate(self):
  self.p.play();self.wire([0x92,60,100]);length=self.e.loop_stats()['loop_frames'];self.audio(length+1,chunk=777)
  takes=self.e.takes();self.assertEqual(len(takes),1);self.assertEqual(takes[0]['duration_tick'],LOOP_TICKS);self.assertEqual(takes[0]['reason'],3)
  self.assertEqual(self.e.loop_stats()['held'],0);self.assertEqual(self.e.stats()['onsets'][0],2)
  self.wire([0x82,60,0]);self.audio(1);self.assertEqual(self.e.stats()['onsets'][0],2)
 def test_cross_wrap_duration_and_only_next_corresponding_onset(self):
  song=self.m.state;event=Event(500,62,.5,0,1000);self.m.state=replace(song,layers=(replace(song.layers[0],events=(event,)),));self.m.next_id=501
  self.e.publish(self.m.state,self.m.capture_epoch);self.audio(1);self.p.play();length=self.e.loop_stats()['loop_frames']
  self.audio(length-100);self.wire([0x92,61,100]);self.audio(200);self.wire([0x82,61,0]);self.audio(1)
  take=self.e.takes()[0];self.assertAlmostEqual(take['duration_tick']*length/LOOP_TICKS,200,delta=.5)
  self.assertAlmostEqual(take['start_tick']*length/LOOP_TICKS,length-100,delta=.5)
  onsets=self.e.stats()['onsets'][0];self.audio(length-201);self.assertEqual(self.e.stats()['onsets'][0],onsets)
  self.audio(1);self.assertEqual(self.e.stats()['onsets'][0],onsets+1)
 def test_ninth_steal_completes_old_capture_and_stale_release_cannot_kill_new(self):
  self.p.play()
  for pad in range(36,45):self.wire([0x92,pad,100]);self.audio(64)
  self.p.drain();self.assertEqual(len(self.m.state.layers[0].events),1);self.assertEqual(self.e.loop_stats()['held'],8)
  self.wire([0x82,36,0]);self.audio(1);self.assertEqual(self.e.loop_stats()['held'],8)
 def test_undo_before_native_command_consumed_cancels_epoch(self):
  self.p.play();self.wire([0x92,60,100]);self.assertEqual(self.p.undo(),'cancel')
  self.audio(1000);self.wire([0x82,60,0]);self.audio(1);self.p.drain()
  self.assertFalse(self.m.state.layers[0].events);self.assertEqual(self.e.loop_stats()['held'],0)
 def test_empty_redo_keeps_native_and_model_capture_epoch_aligned(self):
  self.p.play();self.wire([0x92,60,100]);self.audio(64)
  epoch=self.m.capture_epoch;self.assertFalse(self.p.undo(True))
  self.assertEqual(self.m.capture_epoch,epoch);self.audio(1)
  self.assertEqual(self.e.loop_stats()['epoch'],epoch)
  self.wire([0x82,60,0]);self.audio(1);self.p.drain()
  self.assertEqual(len(self.m.state.layers[0].events),1)
 def test_valid_redo_cancels_pending_and_publishes_new_epoch(self):
  self.p.add_layer();self.audio(1);self.p.undo();self.audio(1)
  self.p.play();self.wire([0x92,60,100]);self.audio(64)
  self.assertTrue(self.p.undo(True));self.audio(1)
  self.assertEqual(self.e.loop_stats()['epoch'],self.m.capture_epoch)
  self.assertEqual(self.e.loop_stats()['held'],0);self.assertFalse(self.m.pending)
  self.wire([0x82,60,0]);self.audio(1);self.p.drain()
  self.assertFalse(any(l.events for l in self.m.state.layers))
 def test_undo_after_ack_drains_then_redo_exact(self):
  self.p.play();self.close_note();song=self.m.state
  self.assertTrue(self.p.undo());self.audio(1);self.assertFalse(self.m.state.layers[0].events)
  self.assertTrue(self.p.undo(True));self.audio(1);self.assertEqual(self.m.state,song)
 def test_stop_play_retires_tokens_and_preserves_pcm_clock(self):
  self.p.play();self.wire([0x92,60,100]);self.audio(100);clock=self.e.stats()['frames']
  self.p.stop();self.p.play();self.audio(1);self.p.drain()
  self.assertEqual(self.e.loop_stats()['held'],0);self.assertGreater(self.e.stats()['frames'],clock)
  self.wire([0xd2,127,0x82,60,0]);self.audio(100);self.assertEqual(self.e.loop_stats()['held'],0)
 def test_tempo_applies_only_wrap_and_closes_crossing_capture(self):
  self.p.play();self.wire([0x92,60,100]);self.audio(100);self.e.check(self.e.lib.sw_loop_tempo(120));self.audio(1)
  stats=self.e.loop_stats();self.assertEqual(stats['tempo'],58);self.assertEqual(stats['pending_tempo'],120)
  self.audio(stats['loop_frames']-101+1);take=self.e.takes()[0]
  self.assertEqual(take['duration_tick'],LOOP_TICKS);self.assertEqual(self.e.loop_stats()['tempo'],120)
 def test_bank_validation_and_three_mailbox_backpressure_all_or_nothing(self):
  old=self.e.loop_stats()['generation'];bank=bank_for(self.m.state);bank.layers[0].events[0].velocity=float('nan');bank.layers[0].count=1
  self.assertEqual(self.e.lib.sw_song_publish(C.byref(bank),10,1),-2);self.audio(1);self.assertEqual(self.e.loop_stats()['generation'],old)
  for _ in range(3):self.e.publish(self.m.state,self.m.capture_epoch)
  with self.assertRaises(RuntimeError):self.e.publish(self.m.state,self.m.capture_epoch)
  self.audio(1);self.assertEqual(self.e.loop_stats()['generation'],old+3)
 def test_ack_capacity_preserves_all_admitted_notes_and_auditions_rejected(self):
  self.e.transport(1,True,1);self.audio(1);accepted=0
  for index in range(100):
   result=self.e.lib.sw_performance_on(0,index+1,0,62,.5,1,1,index+1)
   accepted+=result==0;self.audio(2);self.e.lib.sw_performance_off(0,index+1);self.audio(1)
  takes=self.e.takes();self.assertEqual(len(takes),accepted);self.assertEqual(accepted,63)
  self.assertEqual(self.e.loop_stats()['held'],0);self.assertEqual(self.e.loop_stats()['captures'],accepted)
 def test_full_event_layer_rejects_capture_without_lost_release(self):
  layer=replace(self.m.state.layers[0],events=tuple(Event(i+1,62,.5,i*5000,10) for i in range(256)))
  self.m.state=replace(self.m.state,layers=(layer,));self.e.publish(self.m.state,1);self.audio(1)
  self.e.transport(2,True,1);self.e.lib.sw_performance_on(0,1,0,62,.5,1,1,1000);self.audio(10)
  takes=self.e.takes();self.assertEqual(takes[0]['status'],1);self.assertEqual(self.e.loop_stats()['held'],1)
  self.e.lib.sw_performance_off(0,1);self.audio(1);self.assertEqual(self.e.loop_stats()['held'],0);self.assertEqual(self.e.loop_stats()['captures'],256)

if __name__=='__main__':unittest.main()
