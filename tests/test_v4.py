"""V4 production state transitions, native pitches and controlled file operations."""
import ctypes as C
from dataclasses import replace
import json
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,Event,Layer,atomic_write,pad_pitch
from loop_engine import LoopEngine,PitchSnapshot
from loop_app import LoopInstrument,led_values
from library_manager import LibraryManager,identity
from v4_controls import SlowChoice,PitchLights
from loop_graphics import render
from roles import ROLE_IDS,ROLE_PALETTE,DEFAULTS

class Choices(unittest.TestCase):
 def test_accumulate_clamp_packet_idle_reversal(self):
  c=SlowChoice()
  self.assertEqual([c.step(1,n*.01) for n in range(4)],[0,0,0,1])
  self.assertEqual(c.step(63,.05),1);self.assertEqual(c.step(1,.06),0)
  self.assertEqual(c.step(-1,.07),0);self.assertEqual(c.step(-2,.08),0)
  self.assertEqual(c.step(-1,.5),0);self.assertEqual(c.step(-3,.51),-1)

class NativeUI(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.home=Path(self.tmp.name)
  self.m=LoopModel(self.home/'sessions/current-v3.json',writer=False)
  self.e=LoopEngine(ROOT/'.build/engine.so');self.e.lib.sw_reset();self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  self.i=LoopInstrument(self.m,self.e);self.audio(1)
 def audio(self,n=256):
  while n:
   size=min(n,8192);pcm=(C.c_float*(size*2))();self.e.lib.sw_render(pcm,size);n-=size
 def wire(self,n,v=127,kind='cc'):return self.i.wire(dict(kind=kind,number=n,value=v,channel=0))
 def song(self,roles,pitches,duration=100):
  layers=tuple(Layer(n+1,r,.6,False,DEFAULTS[ROLE_IDS.index(r)],(Event(n+1,p,.7,0,duration),)) for n,(r,p) in enumerate(zip(roles,pitches)))
  self.m.state=replace(self.m.state,layers=layers,role_order=tuple(roles)+tuple(r for r in ROLE_IDS if r not in roles));self.m.selected=len(layers)-1;self.m.next_id=len(layers)+1
  self.e.publish(self.m.state,self.m.capture_epoch);self.audio(1)
 def test_short_native_notes_all_roles_duplicates_absolute_window(self):
  roles=('silt','oxide','choir','prism');pitches=(48,55,62,96);self.song(roles,pitches,1)
  self.i.pitch_lights.colors(self.m,self.e.stats(),0)
  self.i.performance.play();self.audio(1000);stats=self.e.stats()
  self.assertTrue(all(stats['pitches']['onset'][l][p-24]==1 for l,p in enumerate(pitches)))
  self.assertTrue(all(not stats['pitches']['gate'][l][p-24] for l,p in enumerate(pitches)))
  with patch('v4_controls.time.monotonic',return_value=.1):leds=led_values(self.m,stats,self.i)
  for pad in range(36,100):
   pitch=pad_pitch(pad,0,self.m.state.root,self.m.state.scale)
   if pitch in pitches:self.assertEqual(leds['note',pad],ROLE_PALETTE[roles[pitches.index(pitch)]][0])
  colors=self.i.pitch_lights.colors(self.m,stats,.3);self.assertFalse(colors)
  # No nearest-note or octave folding: imported C# and 96 do not light D/C.
  self.assertNotIn(61,{pad_pitch(p,0,self.m.state.root,self.m.state.scale) for p in range(36,100)})
 def test_manual_onset_owner_pressure_mute_level_master_stop_clear_key(self):
  self.song(('silt','oxide'),(48,55));self.m.selected=0
  self.wire(36,100,'note');self.audio(1);pitch=pad_pitch(36,0,self.m.state.root,self.m.state.scale)
  self.m.selected=1;self.wire(36,127,'poly_pressure');self.audio(1)
  with patch('v4_controls.time.monotonic',return_value=1):leds=led_values(self.m,self.e.stats(),self.i)
  self.assertEqual(leds['note',36],ROLE_PALETTE['silt'][0]);self.assertEqual(self.i.performance.slots[0]['layer'],0)
  self.e.lib.sw_loop_master(0);self.audio();self.assertIn(pitch,self.i.pitch_lights.colors(self.m,self.e.stats(),1.1))
  self.m.mute(0);self.e.lib.sw_layer_parameter(0,9,1);self.audio();self.assertNotIn(pitch,self.i.pitch_lights.colors(self.m,self.e.stats(),1.2))
  self.wire(29);self.audio();self.assertFalse(self.i.pitch_lights.colors(self.m,self.e.stats(),1.3))
  self.i.performance.rekey(60,'minor');self.audio();self.assertFalse(self.i.pitch_lights.colors(self.m,self.e.stats(),1.4))
  self.i.performance.clear();self.audio();self.assertFalse(self.i.pitch_lights.colors(self.m,self.e.stats(),1.5))
 def test_eight_role_unison_full_round_then_expiry_and_no_white(self):
  self.song(ROLE_IDS,[62]*8,1);lights=self.i.pitch_lights;lights.colors(self.m,self.e.stats(),0)
  self.i.performance.play();self.audio(1000);stats=self.e.stats()
  colors=[lights.colors(self.m,stats,.1+.201*n)[62] for n in range(8)]
  self.assertEqual(set(colors),set(ROLE_IDS));self.assertEqual(lights.collisions['62'],list(range(8)))
  self.assertNotIn(62,lights.colors(self.m,stats,1.8))
 def test_pitch_snapshot_bounded_and_retired_stolen_gates(self):
  self.song(('silt',),(62,),300000);self.i.performance.play();self.audio(256)
  out=PitchSnapshot();self.assertEqual(self.e.lib.sw_loop_pitches(C.byref(out)),0);self.assertEqual(out.gate[0][38],2)
  for n in range(70):self.e.lib.sw_performance_on(n%8,n+1,0,48+n%12,.5,0,1,n+10);self.audio(1)
  self.assertLessEqual(sum(bool(v&1) for v in self.e.pitches()['gate'][0]),8)
  self.i.performance.stop();self.audio();self.assertFalse(any(self.e.pitches()['gate'][0]))
 def test_visible_key_draft_one_undo_no_macro_edit_cancel_exit(self):
  old=self.m.state;revision=self.m.revision;self.wire(58)
  self.wire(71,1);self.wire(72,63);self.assertEqual(self.m.state,old)
  self.assertEqual(self.i.key_draft,[62,'phrygian']);self.wire(107)
  self.assertEqual(self.i.key_draft[1],'minor');self.wire(27);self.audio()
  self.assertEqual(self.m.state.scale,'minor');self.assertEqual(self.m.revision,revision+1);self.assertEqual(len(self.m.undo_stack),1)
  self.assertEqual(self.m.state.layers[0].parameters,old.layers[0].parameters)
  self.wire(27);self.assertEqual(len(self.m.undo_stack),1)
  self.wire(102);self.wire(26);self.assertEqual(self.i.key_draft[1],'minor')
  self.wire(102);self.wire(50);self.assertIsNone(self.i.key_draft);self.assertEqual(self.m.state.scale,'minor')
 def test_manager_navigation_pending_structure_no_edits_and_delete_context(self):
  self.song(('silt',),(62,));self.i.performance.play();self.audio();self.i.performance.extend();self.audio(1)
  op=self.i.performance.structural;old=self.m.state
  for page in ('library','recordings','key'):
   self.i.open_page(page)
   for n in ((71,72,73,102,104) if page=='key' else (71,72,73,102,104,118)):
    try:self.wire(n,1)
    except ValueError:pass
   self.assertIs(self.i.performance.structural,op);self.assertFalse(op['cancelling']);self.assertEqual(self.m.state,old)
  self.i.open_page('library');self.wire(29);self.audio();self.i.performance.drain();self.assertFalse(self.i.performance.structural)
 def test_loop_page_manager_buttons_and_unchanged_apply_preserve_pending(self):
  self.song(('silt',),(62,));self.i.performance.play();self.audio();self.i.performance.extend();self.audio(1)
  op=self.i.performance.structural
  self.i.open_page('overview');self.wire(20);self.assertEqual(self.m.view,'library');self.assertFalse(op['cancelling'])
  self.i.open_page('overview');self.wire(21);self.assertEqual(self.m.view,'recordings');self.assertFalse(op['cancelling'])
  self.i.open_page('key');self.wire(27);self.assertIs(self.i.performance.structural,op);self.assertFalse(op['cancelling'])
 def test_record_page_explicit_no_first_play_and_all_views_native_render(self):
  from types import SimpleNamespace
  calls=[];state=dict(state='idle',busy=False)
  self.i.recorder=SimpleNamespace(start=lambda:calls.append('start'),stop=lambda:calls.append('stop'),snapshot=lambda:state,directory=self.home/'recordings')
  self.wire(85);self.audio();self.wire(36,90,'note');self.audio();self.assertFalse(calls)
  self.wire(49);self.wire(86);self.wire(49,0);self.assertEqual(self.m.view,'recordings');self.assertFalse(calls)
  self.wire(20);self.wire(21);self.assertEqual(calls,['start','stop'])
  for view in ('library','recordings','key','overview','mixer','instrument'):
   self.i.open_page(view);self.assertEqual(len(render(self.m,self.e.stats(),self.i)),327680)
 def test_recording_tabs_match_visible_top_button_columns(self):
  from unittest.mock import Mock
  from management_graphics import manager_page
  self.i.open_page('recordings');canvas=Mock()
  manager_page(canvas,self.m,self.i,dict(state='idle'))
  columns={call.args[2]:102+call.args[0]//120 for call in canvas.text.call_args_list if call.args[1]==48 and call.args[2] in ('CURRENT','SAVED')}
  self.assertEqual(columns,dict(CURRENT=104,SAVED=105))
  revision=self.m.revision;state=self.m.state
  for label in ('SAVED','CURRENT','SAVED','CURRENT'):
   self.wire(columns[label]);self.assertEqual(self.i.record_tab,label.lower())
   self.wire(columns[label],0);self.assertEqual(self.i.record_tab,label.lower())
  self.assertEqual(self.m.revision,revision);self.assertEqual(self.m.state,state)
 def test_late_manager_reply_does_not_reopen_page(self):
  from types import SimpleNamespace
  manager=SimpleNamespace(results=queue.Queue(),submit=lambda *a,**k:None)
  self.i.manager=manager;self.i.open_page('library');generation=self.i.page_generation
  self.m.replacement_request=(5,'load');self.i.transition=('load','old')
  self.i.open_page('instrument');self.assertIsNone(self.m.replacement_request);self.assertIsNone(self.i.transition);manager.results.put(dict(kind='loops',generation=generation,rows=[dict(id='stale')]))
  self.i.management_tick();self.assertEqual(self.m.view,'instrument');self.assertFalse(self.i.rows)

class Material(unittest.TestCase):
 def test_all_worlds_fill_increases_exact_seam_fixed_under_audio(self):
  from loop_graphics import material,background,poses
  from graphics import Canvas,color
  from roles import ROLE_RGB
  for role in ROLE_IDS:
   self.assertEqual(len(poses(role)),8*17*5*8192);areas=[]
   for value in (0,.25,.5,.75,1):
    c=Canvas(background(role));material(c,background(role),role,(value,)*8,0,0,0)
    y=108-round(value*56);start=(y*1024+40)*2
    self.assertEqual(c.pixels[start:start+80],color(ROLE_RGB[role])*40)
    # Compare summed native pixels in the occupied extent, excluding text.
    raw=bytes(c.pixels);total=0
    import struct
    for yy in range(54,106):
     for xx in range(42,78):
      packed=struct.unpack_from('<H',raw,(yy*1024+xx)*2)[0]
      total+=(packed&31)+((packed>>5)&63)+(packed>>11)
    areas.append(total)
    animated=Canvas(background(role));material(animated,background(role),role,(value,)*8,1,1,1)
    self.assertEqual(animated.pixels[start:start+80],c.pixels[start:start+80])
   self.assertEqual(areas,sorted(areas),role)

class Libraries(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.home=Path(self.tmp.name)
  self.manager=LibraryManager(self.home);self.addCleanup(self.manager.close)
  self.m=LoopModel(self.home/'sessions/current-v3.json',writer=False)
 def save(self,n=1):
  name='song-'+('%032x'%n)+'.json';atomic_write(self.manager.saved/name,self.m.payload());return self.manager.loops()[0]
 def test_loop_rename_duplicate_delete_preserves_current_and_original(self):
  row=self.save();original=(self.manager.saved/row['id']).read_bytes();current=self.m.payload()
  rows=self.manager.work('rename',row=row,label='MY LOOP')['rows'];self.assertEqual(rows[0]['name'],'MY LOOP')
  self.assertEqual((self.manager.saved/row['id']).read_bytes(),original)
  self.save(2);row=self.manager.loops()[0];self.manager.work('rename',row=row,label='MY LOOP')
  self.assertEqual([r['name'] for r in self.manager.loops()],['MY LOOP','MY LOOP'])
  self.manager.work('delete_loop',row=row);self.assertEqual(len(self.manager.loops()),1);self.assertEqual(self.m.payload(),current)
 def test_stale_loop_id_symlink_corrupt_entries_and_bad_name(self):
  row=self.save();path=self.manager.saved/row['id'];path.write_text('{}')
  with self.assertRaisesRegex(ValueError,'changed'):self.manager.work('delete_loop',row=row)
  self.assertEqual(self.manager.loops()[0]['status'],'ERROR')
  with self.assertRaises(ValueError):self.manager.work('rename',row=self.manager.loops()[0],label='../../BAD')
  path.unlink();path.symlink_to(self.home/'target')
  self.assertFalse(self.manager.loops())
  with self.assertRaises(ValueError):identity(path)
 def film(self):
  job='film-012345abcdef';raw=self.manager.recordings/'jobs'/job;raw.mkdir(parents=True)
  (raw/'screen.bgr565').write_bytes(bytes(20000));(raw/'audio.s16le').write_bytes(bytes(8000))
  atomic_write(raw/'metadata.json',dict(job=job,state='ready',audio_frames=2000))
  (self.manager.recordings/(job+'.mp4')).write_bytes(bytes(123))
  return self.manager.inventory()[0]
 def test_delete_full_film_bundle_bytes_intent_retry_and_unrelated(self):
  row=self.film();self.assertGreater(row['bytes'],28123);other=self.manager.recordings/'unrelated.txt';other.write_text('keep')
  with patch('library_manager.remove_tree',side_effect=OSError('disk failure')):
   with self.assertRaises(OSError):self.manager.delete_recording(row)
  self.assertEqual(self.manager.inventory()[0]['status'],'DELETE INCOMPLETE')
  self.manager.retry_deletions();self.assertFalse(self.manager.inventory());self.assertEqual(other.read_text(),'keep')
  self.assertFalse((self.manager.recordings/'jobs'/row['id']).exists())
 def test_symlink_raw_child_refuses_before_delete_and_recovery_excluded(self):
  row=self.film();raw=self.manager.recordings/'jobs'/row['id'];(raw/'escape').symlink_to(self.home/'outside')
  with self.assertRaises(ValueError):self.manager.delete_recording(row)
  self.assertTrue((self.manager.recordings/row['name']).exists())
 def test_controlled_load_identity_failure_does_not_archive_or_replace(self):
  row=self.save();self.m.writer=__import__('loop_model').SessionWriter(self.m.path);self.addCleanup(self.m.close)
  original=self.m.state;path=self.manager.saved/row['id'];path.write_text('{}')
  self.m.request_load(row['id'],row['identity'])
  deadline=time.monotonic()+2;results=[]
  while not results and time.monotonic()<deadline:results=self.m.poll_tasks();time.sleep(.005)
  self.assertTrue(results[0].get('error'));self.assertEqual(self.m.state,original)
  self.assertEqual(len(list(self.manager.saved.glob('song-*.json'))),1)
 def test_recovery_refuses_durable_deletion_intent(self):
  from recorder import SessionRecorder
  from types import SimpleNamespace
  row=self.film();recorder=SessionRecorder(SimpleNamespace(),self.manager.recordings)
  intents=self.manager.recordings/'.deleting';intents.mkdir();atomic_write(intents/(row['id']+'.json'),dict(id=row['id']))
  with self.assertRaisesRegex(ValueError,'being deleted'):recorder._load_recovery(row['id'])
 def test_wav_inventory_reads_duration_and_deletes_controlled_sidecar(self):
  import wave
  self.manager.recordings.mkdir();path=self.manager.recordings/'loop-20261116-123456-012345abcdef.wav'
  with wave.open(str(path),'wb') as wav:wav.setparams((2,2,44100,0,'NONE',''));wav.writeframes(bytes(44100*4))
  atomic_write(path.with_suffix('.json'),dict(frames=44100))
  row=self.manager.inventory()[0];self.assertEqual(row['seconds'],1)
  self.manager.delete_recording(row);self.assertFalse(path.exists());self.assertFalse(path.with_suffix('.json').exists())
 def test_active_recorder_job_and_queue_failure_release_reservation(self):
  from recorder import SessionRecorder
  from types import SimpleNamespace
  recorder=SessionRecorder(SimpleNamespace(),self.manager.recordings);self.manager.recorder=recorder
  recorder.status['busy']=True
  with self.assertRaises(ValueError):self.manager.submit('delete_recording',1,row={})
  recorder.status['busy']=False
  with patch.object(self.manager.jobs,'put_nowait',side_effect=queue.Full):
   with self.assertRaises(queue.Full):self.manager.submit('delete_recording',1,row={})
  self.assertFalse(recorder.manager_busy)
 def test_worker_error_result_generation(self):
  self.manager.submit('invalid',71)
  reply=self.manager.results.get(timeout=2);self.assertEqual(reply['generation'],71);self.assertIn('error',reply)

if __name__=='__main__':unittest.main()
