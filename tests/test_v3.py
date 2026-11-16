"""V3 performed-loop migration, musical controls and native atomic banks."""
import copy
import ctypes as C
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import (LoopModel,Event,Layer,blank,json_ready,read_envelope,decode_song,
                        atomic_write,TICKS,MODES,degree_pitch,pitch_degree,project_degree,pad_pitch)
from loop_engine import LoopEngine,bank_for
from loop_app import LoopInstrument,led_values
from loop_graphics import render
from roles import ROLE_IDS,ROLE_PALETTE,DEFAULTS
from midi import MidiDispatch

class ModelV3(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'current-v3.json';self.m=LoopModel(self.path,writer=False)
 def test_fresh_silt_four_beats_and_roundtrip(self):
  self.assertEqual(self.m.state.loop_beats,4);self.assertEqual(self.m.state.layers[0].role,'silt');self.assertTrue(self.m.overdub)
  self.assertEqual(decode_song(json_ready(self.m.state)),self.m.state)
 def legacy(self):
  raw=json_ready(replace(self.m.state,loop_beats=16));raw['schema']=1
  for layer in raw['layers']:layer.pop('sound_version')
  raw['layers'][0]['events']=[dict(id=10,pitch=61,velocity=.713,start_tick=1535999,duration_tick=1536000)]
  return raw
 def test_v2_migration_preserves_exact_current_history_and_bytes(self):
  raw=self.legacy();history=copy.deepcopy(raw);history['master']=.82;history.pop('loop_beats')
  old=dict(format='stillwater-loop',version=1,revision=782,state=raw,undo=[history]*32,redo=[raw]*32)
  v2=self.path.with_name('current-v2.json');v2.write_text(json.dumps(old));original=v2.read_bytes()
  m=LoopModel(self.path,writer=True);self.addCleanup(m.close);self.assertTrue(m.writer.flush(782,3))
  migrated=read_envelope(self.path);self.assertEqual(migrated['revision'],782);self.assertEqual(len(migrated['undo']),32);self.assertEqual(len(migrated['redo']),32)
  for state in (m.state,)+m.undo_stack+m.redo_stack:
   self.assertEqual(state.loop_beats,16);self.assertEqual(state.layers[0].events[0].pitch,61)
   self.assertEqual(state.layers[0].events[0].start_tick,1535999);self.assertEqual(state.layers[0].events[0].duration_tick,1536000);self.assertEqual(state.layers[0].events[0].velocity,.713)
  self.assertEqual(v2.read_bytes(),original);self.assertEqual(json.loads(self.path.read_bytes())['version'],2)
  # Once V3 exists, a later V2 save cannot replace it on restart.
  m.close();old['revision']=900;v2.write_text(json.dumps(old));self.assertEqual(LoopModel(self.path,writer=False).revision,782)
 def test_invalid_history_and_newer_envelope_fail_without_write(self):
  for mutation in ('history','newer'):
   old=dict(format='stillwater-loop',version=1,revision=7,state=self.legacy(),undo=[self.legacy()],redo=[])
   if mutation=='history':old['undo'][0]['layers'][0]['events'][0]['pitch']=100
   else:old['version']=99
   v2=self.path.with_name('current-v2.json');v2.write_text(json.dumps(old));original=v2.read_bytes()
   with self.assertRaises(ValueError):LoopModel(self.path,writer=True)
   self.assertFalse(self.path.exists());self.assertEqual(v2.read_bytes(),original)
 def test_all_keys_modes_canonical_roundtrip_offscale_and_register_edges(self):
  event=Event(1,61,.5,0,100,pitch_degree(61));self.m.state=replace(self.m.state,layers=(replace(self.m.state.layers[0],events=(event,)),))
  self.assertEqual(event.degree,-1)  # nearest lower tie: C, rather than D
  canonical=event.degree
  for root in range(60,72):
   for mode in MODES:
    self.m.rekey(root,mode,now=0)
    e=self.m.state.layers[0].events[0];self.assertEqual(e.degree,canonical);self.assertEqual(e.pitch,project_degree(canonical,root,mode))
    pitches=[pad_pitch(n,0,root,mode) for n in range(36,100)];self.assertEqual(len(set(pitches)),29)
    self.assertTrue(all(0<=p<=127 and (p-root)%12 in MODES[mode] for p in pitches))
    for d in (-22,-21,20,21):
     pitch=project_degree(d,root,mode);self.assertTrue(0<=pitch<=127);self.assertIn((pitch-root)%12,MODES[mode])
  self.m.rekey(62,'dorian');self.assertEqual(self.m.state.layers[0].events[0].pitch,60)
 def test_progression_requires_recorded_foundation_then_mid_and_relocks_unused(self):
  self.assertEqual(self.m.role_state('filament'),'RECORD FOUNDATION');self.assertFalse(self.m.add_layer('prism'))
  self.m.overdub=False;self.assertEqual(self.m.role_state('glass'),'RECORD FOUNDATION')
  self.m.commit(self.m.layer_edit(0,events=(Event(1,50,.5,0,100),)));self.m.mute(0)
  self.assertTrue(self.m.add_layer('choir'));self.assertEqual(self.m.role_state('prism'),'RECORD MID LAYER')
  self.m.commit(self.m.layer_edit(1,events=(Event(2,62,.5,0,100),)));self.assertTrue(self.m.add_layer('prism'))
  before=self.m.state;self.m.undo();self.m.redo();self.assertEqual(self.m.state,before)
  self.assertEqual(tuple(l.role for l in before.layers),before.role_order[:3]);self.assertEqual(self.m.role_state('prism'),'USED')
  self.m.selected=0;self.m.clear_layer();self.assertEqual(self.m.role_state('glass'),'RECORD FOUNDATION');self.assertEqual(self.m.role_state('prism'),'USED')
 def test_extension_first_bar_exact_unique_ids_atomic_capacity(self):
  events=(Event(1,50,.73,0,700000),Event(2,53,.32,380000,10),Event(3,57,.5,400000,100))
  self.m.state=replace(self.m.state,loop_beats=8,layers=(replace(self.m.state.layers[0],events=events),));self.m.next_id=4
  candidate=self.m.extended();self.assertEqual(candidate.loop_beats,12);self.assertEqual(candidate.layers[0].events[:3],events)
  for original,copied in zip(events,candidate.layers[0].events[3:]):self.assertEqual(replace(copied,id=original.id,start_tick=original.start_tick),original)
  self.assertEqual([e.start_tick for e in candidate.layers[0].events[3:]],[768000,1148000]);self.assertEqual(self.m.next_id,4)
  self.m.state=replace(self.m.state,layers=(replace(self.m.state.layers[0],events=tuple(Event(n+1,50,.5,n,100) for n in range(129))),));old=self.m.payload()
  with self.assertRaises(ValueError):self.m.extended()
  self.assertEqual(self.m.payload(),old)

class NativeV3(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.m=LoopModel(Path(self.tmp.name)/'current-v3.json',writer=False)
  self.e=LoopEngine(ROOT/'.build/engine.so');self.e.lib.sw_reset();self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  self.i=LoopInstrument(self.m,self.e);self.p=self.i.performance;self.audio(1)
 def audio(self,n):
  while n:
   k=min(n,8192);pcm=(C.c_float*(k*2))();self.e.lib.sw_render(pcm,k);n-=k
 def wire(self,number,value=127,kind='cc'):
  return self.i.wire(dict(kind=kind,channel=0,number=number,value=value))
 def start(self):
  self.m.state=replace(self.m.state,layers=(replace(self.m.state.layers[0],events=(Event(1,50,.5,0,100),)),));self.m.next_id=2
  self.e.publish(self.m.state,1);self.audio(1);self.p.play();self.audio(17)
 def boundary(self):
  s=self.e.loop_stats();self.audio(s['loop_frames']-s['phase']+1)
 def assert_pad_window(self):
  leds=led_values(self.m,self.e.stats(),self.i)
  for pad in range(36,100):
   self.assertIn(('note',pad),leds)
   self.assertTrue(0<=pad_pitch(pad,self.m.octave,self.m.state.root,self.m.state.scale)<=127)
 def test_window_normalizes_after_cc_undo_structural_history_load_and_new(self):
  import queue
  from types import SimpleNamespace
  self.m.state=replace(self.m.state,root=60);self.m.octave=3
  self.m.undo_stack=(replace(self.m.state,root=71),)
  self.wire(119);self.audio(1)
  self.assertEqual((self.m.state.root,self.m.octave),(71,2));self.assert_pad_window()
  # Length-changing history acknowledgment must normalize the restored key too.
  self.m.state=replace(self.m.state,root=60);self.m.octave=3
  self.m.undo_stack=(replace(self.m.state,root=71,loop_beats=8),)
  self.p.undo();self.audio(1);self.p.drain();self.assert_pad_window();self.assertEqual(self.m.octave,2)
  results=queue.Queue();self.m.writer=SimpleNamespace(results=results,submit=lambda *args:None)
  self.m.state=replace(self.m.state,root=60);self.m.octave=3
  self.m.replacement_request=(1,'load')
  results.put(dict(kind='load',request_token=1,revision=self.m.revision,payload=dict(state=replace(self.m.state,root=71))))
  self.m.poll_tasks();self.assert_pad_window();self.assertEqual(self.m.octave,2)
  self.m.state=replace(self.m.state,root=60);self.m.octave=3
  self.m.replacement_request=(2,'archive')
  results.put(dict(kind='archive',request_token=2,revision=self.m.revision))
  self.m.poll_tasks();self.assert_pad_window();self.assertEqual(self.m.octave,3)
  self.m.writer=None
 def test_bad_pad_pitch_does_not_reserve_capture(self):
  self.start();self.m.octave=4;before=(dict(self.m.pending),self.m.next_id,self.p.token)
  with self.assertRaises(ValueError):self.p.event('note',36,100)
  self.assertEqual((self.m.pending,self.m.next_id,self.p.token),before)
 def test_length_redo_refuses_held_captures_and_retries_audition_at_boundary(self):
  self.start();self.p.extend();self.audio(1);self.boundary();self.p.drain()
  self.p.undo();self.audio(1);self.boundary();self.p.drain()
  self.wire(36,100,'note');self.audio(511);redo=self.m.redo_stack
  self.wire(49);self.wire(119);self.wire(49,0);self.audio(1)
  self.assertEqual(self.m.redo_stack,redo);self.assertEqual(self.e.loop_stats()['loop_beats'],4)
  self.assertIn('RELEASE PADS',self.m.message);self.assertFalse(self.p.structural)
  # A completed capture is a new edit and legitimately invalidates old Redo.
  self.wire(36,0,'note_off');self.audio(1);self.p.drain();self.assertFalse(self.m.redo_stack)
  self.m.redo_stack=(replace(self.m.state,loop_beats=8),);self.m.overdub=False
  self.wire(37,100,'note');self.audio(1)
  self.assertFalse(self.p.undo(True));self.assertIn('RELEASE PADS',self.m.message)
  self.wire(37,0,'note_off');self.audio(1);self.p.drain();self.p.undo(True);self.audio(1)
  self.assertEqual(self.e.loop_stats()['loop_beats'],4);self.boundary();self.p.drain()
  self.assertEqual(self.e.loop_stats()['loop_beats'],8);self.assertEqual(self.m.state.loop_beats,8)
 def test_stop_settles_tempo_then_stopped_edit_extension_restart(self):
  self.start();self.wire(113);self.wire(71,2);self.audio(1)
  self.assertEqual(self.e.loop_stats()['pending_tempo'],60)
  self.wire(29);self.audio(1);self.p.drain();s=self.e.loop_stats()
  self.assertEqual((s['tempo'],s['pending_tempo']),(60,0))
  self.wire(71,1);self.audio(1);s=self.e.loop_stats()
  self.assertEqual((s['tempo'],s['pending_tempo'],self.m.state.tempo),(61,0,61))
  self.p.extend();self.audio(1);self.p.drain();self.assertEqual(self.m.state.loop_beats,8)
  self.p.play();self.audio(1);self.boundary();s=self.e.loop_stats()
  self.assertEqual((s['tempo'],s['pending_tempo'],self.m.state.tempo),(61,0,61))
  self.assertEqual(s['loop_frames'],round(44100*60/61*8))
  from loop_export import LoopExport
  start=s['boundary']+s['loop_frames'];end=start+s['loop_frames'];epoch=self.e.lib.sw_history_epoch()
  self.audio(end-s['sample'])
  storage=tempfile.TemporaryDirectory(dir=ROOT/'.build');self.addCleanup(storage.cleanup)
  export=LoopExport(self.e,Path(storage.name)/'exports')
  export._save(s,epoch,self.e.stats()['xruns'],start,end,self.m.revision)
  self.assertEqual(export.snapshot()['state'],'saved',export.snapshot())
  side=json.loads(next(export.directory.glob('*.json')).read_text())
  self.assertEqual((side['tempo'],side['loop_beats'],side['frames']),(61,8,s['loop_frames']))
 def test_record_toggle_preserves_phase_and_onset_owned_held_takes(self):
  self.start();s=self.e.loop_stats();self.wire(86);self.audio(1);after=self.e.loop_stats()
  self.assertFalse(self.m.overdub);self.assertEqual(after['origin'],s['origin']);self.assertEqual(after['phase'],s['phase']+1)
  self.wire(36,100,'note');self.audio(30);self.wire(86);self.wire(36,0,'note_off');self.audio(1);self.p.drain();self.assertEqual(len(self.m.state.layers[0].events),1)
  self.wire(37,100,'note');self.audio(30);self.wire(86);self.wire(37,0,'note_off');self.audio(1);self.p.drain();self.assertEqual(len(self.m.state.layers[0].events),2);self.assertFalse(self.m.pending)
 def test_boundary_extension_commit_ack_and_undo_shrink(self):
  self.start();before=self.m.state;revision=self.m.revision;self.p.extend();self.audio(1)
  self.assertEqual(self.m.state,before);self.assertEqual(self.e.loop_stats()['pending_beats'],8);self.assertEqual(self.e.loop_stats()['loop_beats'],4)
  self.boundary();self.assertEqual(self.m.state,before);self.p.drain()
  self.assertEqual(self.m.state.loop_beats,8);self.assertEqual(self.m.revision,revision+1);self.assertEqual(self.e.loop_stats()['loop_beats'],8)
  self.assertEqual(self.m.capture_epoch,self.e.loop_stats()['epoch'])
  self.p.undo();self.audio(1);self.assertEqual(self.m.state.loop_beats,8);self.boundary();self.p.drain();self.assertEqual(self.m.state,before);self.assertEqual(self.e.loop_stats()['loop_beats'],4)
  self.p.undo(True);self.audio(1);self.boundary();self.p.drain();self.assertEqual(self.m.state.loop_beats,8)
 def test_ordered_cancel_defers_note_and_apply_wins_commits_first(self):
  self.start();self.p.extend();self.audio(1)
  event=dict(kind='note',channel=0,number=36,value=100);dispatch=MidiDispatch();dispatch.process(lambda:[event],self.i.wire)
  self.assertEqual(len(dispatch.pending),1);self.audio(1);dispatch.process(lambda:[],self.i.wire);self.audio(1);self.assertFalse(dispatch.pending);self.assertEqual(self.m.state.loop_beats,4);self.assertEqual(self.e.loop_stats()['held'],1)
  self.wire(36,0,'note_off');self.audio(1);self.p.drain();self.p.extend();self.audio(1);self.boundary()
  self.assertTrue(self.wire(37,100,'note'));self.assertEqual(self.m.state.loop_beats,8);self.audio(1);self.assertEqual(self.e.loop_stats()['held'],1)
 def test_pending_undo_cancels_without_pop_views_do_not_cancel_stop_does(self):
  self.start();self.m.set_master(.5);self.e.scalar_changes(replace(self.m.state,master=.28),self.m.state);self.audio(1);history=self.m.undo_stack
  self.p.extend();self.audio(1)
  for cc in (58,113,92,50):self.wire(cc);self.assertIsNotNone(self.p.structural)
  self.wire(119);self.audio(1);self.p.drain();self.assertEqual(self.m.undo_stack,history)
  self.p.extend();self.audio(1);self.assertFalse(self.wire(29));self.audio(1);self.assertTrue(self.wire(29));self.audio(1);self.assertFalse(self.p.structural);self.assertEqual(self.e.loop_stats()['transport'],0)
 def test_extension_builds_after_final_capture_drain(self):
  self.start();eid=self.m.reserve(0,21,0)
  take=dict(id=eid,epoch=self.m.capture_epoch,layer=0,pitch=53,velocity=.61,start_tick=1000,duration_tick=2000,status=0)
  with patch.object(self.e,'takes',return_value=[take]):self.p.extend()
  candidate=self.p.structural['state'];self.assertEqual(len(candidate.layers[0].events),4)
  self.assertIn(eid,[e.id for e in candidate.layers[0].events]);self.assertFalse(self.m.pending)
 def test_native_guard_rejects_activity_and_unacknowledged_takes(self):
  self.start();self.p.extend();self.audio(1);self.e.lib.sw_loop_master(.6);self.audio(1);self.boundary();self.p.drain();self.assertEqual(self.m.state.loop_beats,4)
  self.wire(36,100,'note');self.audio(10);self.wire(36,0,'note_off');self.audio(1)
  guard=self.e.loop_stats();candidate=self.m.extended();self.e.stage(candidate,2,72,guard);self.audio(1);s=self.e.loop_stats();self.assertEqual(s['ack_token'],72);self.assertEqual(s['op_status'],-1)
 def test_stopped_operation_applies_at_command_block_and_queuefull_is_noop(self):
  old=self.m.state;self.p.extend();self.assertEqual(self.m.state,old);self.audio(1);self.p.drain();self.assertEqual(self.m.state.loop_beats,8)
  for _ in range(1023):self.assertEqual(self.e.lib.sw_loop_master(.2),0)
  old=self.m.payload()
  with self.assertRaises(RuntimeError):self.p.extend()
  self.assertEqual(self.m.payload(),old);self.assertFalse(self.p.structural)
 def test_clear_cancel_take_no_resurrection_retains_other_completed_and_undo(self):
  self.start();self.p.add_layer('oxide');self.audio(1);self.m.selected=0
  self.wire(36,100,'note');self.audio(30);old=self.m.state;self.wire(118);self.audio(1);self.p.drain()
  self.assertFalse(self.m.pending);self.assertFalse(self.m.state.layers[0].events);self.assertEqual(self.m.state.layers[0].parameters,old.layers[0].parameters)
  self.wire(36,0,'note_off');self.audio(1000);self.p.drain();self.assertFalse(self.m.state.layers[0].events)
  self.p.undo();self.audio(1);self.assertEqual(self.m.state,old)
 def test_key_pages_no_hidden_macro_edits_and_held_epoch_retirement(self):
  self.start();self.wire(36,100,'note');self.audio(40);old_epoch=self.m.capture_epoch;params=self.m.state.layers[0].parameters
  self.wire(58);self.wire(71,4);self.assertEqual(self.m.capture_epoch,old_epoch);self.wire(27);self.audio(1);self.assertGreater(self.m.capture_epoch,old_epoch);self.assertEqual(self.e.loop_stats()['held'],0);self.assertEqual(self.m.state.layers[0].parameters,params)
  self.audio(1000);self.assertTrue(all(not s['held'] for s in self.e.stats()['manual']));self.assertFalse(self.m.pending)
  self.wire(113);tempo=self.m.state.tempo;self.wire(72,1);self.assertEqual(self.m.state.tempo,tempo);self.assertEqual(self.m.state.layers[0].parameters,params)
  self.wire(71,1);self.audio(1);self.assertEqual(self.e.loop_stats()['pending_tempo'],tempo+1)
 def test_stopped_undo_new_restores_length_and_tempo_atomically(self):
  old=replace(self.m.state,loop_beats=32,tempo=30)
  self.m.commit(old);self.e.publish(old,1);self.audio(1)
  self.m.commit(blank(old.master));self.m.capture_epoch+=1;self.e.publish(self.m.state,self.m.capture_epoch);self.audio(1)
  self.p.undo();self.audio(1);self.p.drain()
  self.assertEqual(self.m.state,old);s=self.e.loop_stats();self.assertEqual(s['tempo'],30);self.assertEqual(s['loop_beats'],32);self.assertEqual(s['loop_frames'],64*44100)
 def test_source_material_fixed_macros_moves_only_with_native_audio_all_roles(self):
  from loop_graphics import material,background
  from graphics import Canvas
  for role in ROLE_IDS:
   self.e.lib.sw_reset();self.e.generation=0
   layer=replace(self.m.state.layers[0],role=role,parameters=(.5,)*8,events=(Event(1,50,.8,0,360000),))
   self.m.state=replace(self.m.state,layers=(layer,));self.e.publish(self.m.state,1);self.audio(1)
   still=[]
   for seconds in (0,1,2):
    c=Canvas(background(role));material(c,background(role),role,(.5,)*8,0,0,seconds);still.append(bytes(c.pixels))
   self.assertEqual(len(set(still)),1,role)
   self.e.transport(2,False,1);frames=set()
   for _ in range(32):
    self.audio(4410);stats=self.e.stats();frames.add(render(self.m,stats,self.i))
   self.assertGreater(len(frames),4,role)
   # Working pages have no selected-role material animation or macro ornaments.
   for view in ('mixer','overview'):
    self.m.view=view;a=render(self.m,stats,self.i)
    self.m.state=replace(self.m.state,layers=(replace(layer,parameters=(.95,)*8),))
    self.assertEqual(render(self.m,stats,self.i),a)
    self.m.state=replace(self.m.state,layers=(layer,))
   self.m.view='instrument'
 def test_role_led_record_off_lit_and_native_size_render(self):
  stats=self.e.stats();leds=led_values(self.m,stats,self.i);self.assertEqual(leds['cc',102],ROLE_PALETTE['silt'][0]);self.wire(86)
  self.assertEqual(led_values(self.m,stats,self.i)['cc',86],7)
  for view in ('instrument','mixer','overview','key','chooser'):
   self.m.view=view;self.assertEqual(len(render(self.m,stats,self.i)),327680)
 def test_abi_rejected_before_hardware_or_history_use(self):
  class Bad:
   def sw_loop_abi(self):return 2
  with patch('loop_engine.C.CDLL',return_value=Bad()),patch('loop_engine.Engine.__init__') as parent:
   with self.assertRaisesRegex(RuntimeError,'ABI'):LoopEngine('old.so','hw:A3,0')
   parent.assert_not_called()

class ExportV3(unittest.TestCase):
 def test_sixtyfour_second_loop_wait_survives_old_seventy_second_timeout(self):
  from loop_export import LoopExport,SR
  from types import SimpleNamespace
  end=128*SR;baseline=dict(sample=0,boundary=0,loop_frames=64*SR,activity=1,epoch=1,transport=2,generation=1,tempo=30,loop_beats=32)
  class Fake:
   lib=SimpleNamespace(sw_history_end=lambda:end,sw_history_epoch=lambda:1)
   def loop_stats(self):return dict(baseline,sample=end)
   def stats(self):return dict(xruns=0)
   def history_copy(self,epoch,start,count):return (C.c_int16*(count*2))()
  with tempfile.TemporaryDirectory(dir=ROOT/'.build') as tmp:
   export=LoopExport(Fake(),tmp);calls=iter([0])
   # 80s is inside the computed143s deadline, beyond the removed70s constant.
   with patch('loop_export.time.monotonic',side_effect=lambda:next(calls,80)):
    export._save(baseline,1,0,64*SR,end,8)
   self.assertEqual(export.snapshot()['state'],'saved')
   side=json.loads(next(Path(tmp).glob('*.json')).read_text());self.assertEqual(side['frames'],64*SR);self.assertEqual(side['loop_beats'],32)
   self.assertEqual(side['pcm_sha256'],hashlib.sha256(bytes(64*SR*4)).hexdigest())
 def test_pending_structural_operation_blocks_export(self):
  from loop_export import LoopExport
  class Fake:
   def loop_stats(self):return dict(held=0,pending=0,transport=2,pending_tempo=0,op_token=7)
  export=LoopExport(Fake(),'/unused')
  with self.assertRaises(ValueError):export.request(0)

if __name__=='__main__':unittest.main()
