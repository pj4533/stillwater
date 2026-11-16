"""Right navigation wheel and explicit saved-file provenance, including async races."""
from dataclasses import replace
import json
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,SessionWriter,atomic_write,read_envelope
from library_manager import LibraryManager,identity
from loop_app import LoopInstrument
from loop_engine import LoopEngine
from management_graphics import manager_page
from midi import MidiParser

class Provenance(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.home=Path(self.tmp.name)
  self.path=self.home/'sessions/current-v3.json';self.m=LoopModel(self.path);self.addCleanup(self.m.close)
 def wait(self,kind):
  deadline=time.monotonic()+3
  while time.monotonic()<deadline:
   results=self.m.poll_tasks()
   for result in results:
    if result['kind']==kind:
     self.assertNotIn('error',result);return result
   time.sleep(.002)
  self.fail('missing '+kind+' completion')
 def save(self):
  self.m.request_save();return self.wait('snapshot')
 def reopen(self):
  self.assertTrue(self.m.writer.flush(self.m.revision));self.m.close();self.m=LoopModel(self.path);self.addCleanup(self.m.close)
 def test_old_autosave_is_unnamed_without_content_guessing(self):
  self.assertIsNone(self.m.source_status());saved=self.save()
  # A legacy current envelope remains unnamed even with an identical saved file.
  payload=self.m.payload();payload.pop('source');self.m.close();atomic_write(self.path,payload)
  old=LoopModel(self.path,writer=False);self.assertIsNone(old.source_status())
  self.assertTrue((self.path.parent/'saved'/saved['name']).exists())
 def test_save_edit_restart_undo_remains_honestly_edited(self):
  old=self.m.state;history=self.m.undo_stack;result=self.save();source=self.m.source_status()
  self.assertEqual(source['id'],result['name']);self.assertFalse(source['modified']);self.assertEqual(self.m.state,old);self.assertEqual(self.m.undo_stack,history)
  self.m.set_parameter(0,0,.81);self.assertTrue(self.m.source['modified']);self.reopen();self.assertTrue(self.m.source['modified'])
  self.m.undo();self.assertEqual(self.m.state,old);self.assertTrue(self.m.source['modified'])
  result=self.save();self.assertFalse(self.m.source['modified']);self.assertEqual(self.m.source['id'],result['name']);self.reopen();self.assertFalse(self.m.source['modified'])
 def test_load_tracks_selected_file_not_embedded_source_new_clears(self):
  a=self.save();self.m.set_parameter(0,0,.72);b=self.save()
  self.m.request_load(a['name']);self.wait('load');self.assertEqual(self.m.source['id'],a['name']);self.assertFalse(self.m.source['modified'])
  self.reopen();self.assertEqual(self.m.source['id'],a['name']);self.assertFalse(self.m.source['modified'])
  self.m.request_new();self.wait('archive');self.assertIsNone(self.m.source);self.m.undo();self.assertIsNone(self.m.source)
  self.reopen();self.assertIsNone(self.m.source)
 def test_save_completion_with_later_edit_marks_modified(self):
  self.m.request_save();self.m.set_parameter(0,0,.83);self.wait('snapshot');self.assertTrue(self.m.source['modified']);self.reopen();self.assertTrue(self.m.source['modified'])
 def test_delayed_save_cannot_replace_loaded_identity(self):
  a=self.save();payload=dict(revision=self.m.revision,current=self.m.payload(),request_token=self.m.replacement_serial)
  self.m.request_load(a['name']);self.wait('load');source=self.m.source_status()
  late=SessionWriter._job(self.m.writer,'snapshot',payload,None);self.m.writer.results.put(late);self.m.poll_tasks();self.assertEqual(self.m.source,source)
 def test_rename_delete_after_page_exit_update_provenance_and_restart(self):
  self.save();manager=LibraryManager(self.home);self.addCleanup(manager.close)
  e=LoopEngine(ROOT/'.build/engine.so');i=LoopInstrument(self.m,e,manager=manager)
  for kind in ('rename','delete_loop'):
   row=next(r for r in manager.loops() if r['id']==self.m.source['id'])
   result=manager.work(kind,row=row,label='MY LOOP')
   i.open_page('instrument');manager.results.put(dict(kind=kind,generation=-1,**result));i.management_tick()
   if kind=='rename':self.assertEqual(self.m.source['name'],'MY LOOP')
   else:self.assertTrue(self.m.source['deleted'])
  song=self.m.state;history=self.m.undo_stack;self.reopen();self.assertEqual(self.m.state,song);self.assertEqual(self.m.undo_stack,history);self.assertTrue(self.m.source['deleted'])
 def test_restart_resolves_sidecar_rename_or_missing_file(self):
  self.save();path=self.path.parent/'saved'/self.m.source['id'];atomic_write(path.with_suffix('.name.json'),dict(name='RENAMED'))
  self.reopen();self.assertEqual(self.m.source['name'],'RENAMED');path.unlink();self.reopen();self.assertTrue(self.m.source['deleted'])
 def test_metadata_validation_refuses_forged_paths_and_types(self):
  self.save();payload=self.m.payload()
  for change in (dict(id='../outside.json'),dict(modified=1),dict(deleted='no'),dict(name='X'*25)):
   with self.subTest(change=change):
    atomic_write(self.home/'invalid.json',dict(payload,source=dict(payload['source'],**change)))
    with self.assertRaises(ValueError):read_envelope(self.home/'invalid.json')

 def test_two_identical_queued_save_completions_ignore_metadata_revision(self):
  self.m.close();writer=self.m.writer;self.m.writer=None
  payload=dict(revision=self.m.revision,current=self.m.payload(),request_token=self.m.replacement_serial)
  results=[SessionWriter._job(writer,'snapshot',payload,None) for _ in range(2)]
  from types import SimpleNamespace
  fake=SimpleNamespace(results=queue.Queue(),submit=lambda *a:None)
  self.m.writer=fake
  for result in results:fake.results.put(result)
  self.m.poll_tasks();self.assertEqual(self.m.source['id'],results[-1]['name']);self.assertFalse(self.m.source['modified'])
  self.m.writer=None;atomic_write(self.path,self.m.payload());self.m=LoopModel(self.path);self.addCleanup(self.m.close)
  self.assertFalse(self.m.source['modified'])
 def test_late_rename_delete_metadata_does_not_cancel_pending_replacement(self):
  for kind in ('load','archive'):
   for action in ('rename','delete_loop'):
    with self.subTest(kind=kind,action=action):
     saved=self.save();before=self.m.state
     token=self.m.replacement_serial+1
     payload=dict(revision=self.m.revision,current=self.m.payload(),request_token=token)
     result=SessionWriter._job(self.m.writer,kind,payload,saved['name'] if kind=='load' else None)
     self.m.replacement_serial=token;self.m.replacement_request=(token,kind)
     self.m.reconcile_source(action,dict(id=saved['name']),'NEW NAME')
     self.assertIs(self.m.state,before);self.assertNotEqual(self.m.revision,payload['revision'])
     self.m.writer.results.put(result);applied=self.m.poll_tasks();self.assertTrue(applied[0]['applied'])
     if kind=='load':self.assertEqual(self.m.state,before)
     else:self.assertNotEqual(self.m.state.song_id,before.song_id);self.assertIsNone(self.m.source)

class Wheel(unittest.TestCase):
 def setUp(self):
  import ctypes as C
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.m=LoopModel(Path(self.tmp.name)/'current-v3.json',writer=False)
  self.e=LoopEngine(ROOT/'.build/engine.so');self.e.lib.sw_reset();self.i=LoopInstrument(self.m,self.e)
  self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int];self.e.lib.sw_render((C.c_float*512)(),256)
 def wire(self,n,v=1,channel=0):
  for event in MidiParser().feed(bytes([0xb0+channel,n,v])):self.i.wire(event)
 def rows(self,page):
  self.i.open_page(page);self.i.record_tab='saved';self.i.rows=[dict(id=str(n),name='LOOP '+str(n),created=0,bytes=0,status='READY') for n in range(8)];self.i.selected_id='0'
 def test_wheel_only_browses_both_single_selectors_bounded_and_clamped(self):
  for page in ('library','recordings'):
   self.rows(page);old=self.m.state
   for _ in range(4):self.wire(70)
   self.assertEqual(self.i.selected_id,'1');self.wire(70,63);self.assertEqual(self.i.selected_id,'2')
   self.wire(70,127);self.wire(70,127);self.wire(70,127);self.wire(70,127);self.assertEqual(self.i.selected_id,'1')
   self.wire(95,127);self.wire(95,0);self.assertEqual(self.i.selected_id,'2')
   self.wire(93,127);self.assertEqual(self.i.selected_id,'1')
   for n in (71,72,78,94,11):self.wire(n,63)
   self.assertEqual(self.i.selected_id,'1');self.assertEqual(self.m.state,old)
   for _ in range(10):self.wire(93,127)
   self.assertEqual(self.i.selected_id,'0')
   for _ in range(10):self.wire(95,127)
   self.assertEqual(self.i.selected_id,'7')
 def test_nonzero_channel_zero_packets_confirmation_rename_and_current_do_not_browse(self):
  self.rows('library');self.wire(70,63,1);self.wire(70,0);self.assertEqual(self.i.selected_id,'0')
  self.i.confirm=dict(action='delete',row=self.i.rows[0]);self.wire(70,63);self.wire(95,127);self.assertEqual(self.i.selected_id,'0')
  self.i.confirm=None;self.i.rename='NAME';self.wire(70,63);self.wire(95,127);self.assertEqual(self.i.selected_id,'0')
  self.wire(71,63);self.assertEqual(self.i.rename_cursor,1)
  self.rows('recordings');self.i.record_tab='current';self.wire(70,63);self.assertEqual(self.i.selected_id,'0')
 def test_global_volume_and_screen_eight_keep_their_meanings(self):
  self.rows('library');master=self.m.state.master;self.wire(79);self.assertAlmostEqual(self.m.state.master,master+.01)
  self.i.open_page('instrument');before=self.m.state.layers[0].parameters;self.wire(78,1);self.assertNotEqual(self.m.state.layers[0].parameters,before)
 def test_browser_does_not_cancel_pending_bar_or_replacement(self):
  self.rows('library');self.i.performance.structural=dict(token=1,cancelling=False)
  self.m.replacement_request=(9,'load')
  with patch.object(self.i.performance,'drain'),patch.object(self.i.performance,'cancel_structural') as cancel:
   for n,v in ((70,63),(93,127),(95,127),(94,127),(11,127)):self.wire(n,v)
   cancel.assert_not_called();self.assertEqual(self.m.replacement_request,(9,'load'))
 def test_provenance_checkpoint_during_native_pending_bar_preserves_apply(self):
  import ctypes as C
  from loop_model import Event
  self.m.state=replace(self.m.state,layers=(replace(self.m.state.layers[0],events=(Event(1,62,.5,0,100),)),))
  self.m.next_id=2;self.e.publish(self.m.state,self.m.capture_epoch);self.e.lib.sw_render((C.c_float*512)(),256)
  self.i.performance.play();self.e.lib.sw_render((C.c_float*512)(),256)
  self.i.performance.extend();before=self.m.state
  self.m.source_changed(dict(id='song-'+'b'*32+'.json',name='SAVED LOOP',modified=False,deleted=False))
  self.assertIs(self.m.state,before)
  for _ in range(180):
   self.e.lib.sw_render((C.c_float*8192)(),4096);self.i.performance.drain()
   if self.i.performance.structural is None:break
  self.assertIsNone(self.i.performance.structural);self.assertEqual(self.m.state.loop_beats,8);self.assertTrue(self.m.source['modified'])
 def test_selected_highlight_and_loaded_label_are_separate_and_fit(self):
  self.rows('library');self.m.source=dict(id='song-'+'a'*32+'.json',name='ABCDEFGHIJKLMNOPQRSTUVWX',modified=True,deleted=True)
  c=Mock();manager_page(c,self.m,self.i,{})
  calls=[a.args for a in c.text.call_args_list];loaded=next(a for a in calls if a[2].startswith('LOADED '))
  self.assertIn('/ ID AAAAAAAA',loaded[2].upper());self.assertIn('EDITED',loaded[2]);self.assertIn('DELETED',loaded[2]);self.assertLessEqual(loaded[0]+len(loaded[2])*6,740)
  self.assertTrue(any('RIGHT WHEEL' in a[2] for a in calls));self.assertEqual(self.i.selected_id,'0')

if __name__=='__main__':unittest.main()
