"""Continuous keyboard, idle input ownership and the complete Push button map."""
import ctypes as C
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,MODES,pad_pitch,degree_pitch,json_ready,decode_song,Event
from loop_engine import LoopEngine
from loop_app import LoopInstrument,led_values
from midi import MidiParser
from roles import ROLE_PALETTE,ROLE_IDS,DEFAULTS

class PlayControls(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
  self.m=LoopModel(Path(temp.name)/'current-v3.json',writer=False)
  self.e=LoopEngine(ROOT/'.build/engine.so');self.e.lib.sw_reset()
  self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  self.i=LoopInstrument(self.m,self.e);self.audio()
 def audio(self,n=256):
  pcm=(C.c_float*(n*2))();self.e.lib.sw_render(pcm,n)
  self.assertTrue(all(abs(x)<2 for x in pcm))
 def wire(self,kind,number,value,channel=0):
  return self.i.wire(dict(kind=kind,number=number,value=value,channel=channel))
 def test_all_roots_modes_windows_have_64_contiguous_unique_degrees(self):
  for root in range(60,72):
   for scale in MODES:
    for octave in range(-4,5):
     low=degree_pitch(-31+7*octave,root,scale);high=degree_pitch(32+7*octave,root,scale)
     if not 0<=low<=high<=127:
      for pad in (36,99):
       with self.assertRaises(ValueError):pad_pitch(pad,octave,root,scale)
      continue
     pitches=[pad_pitch(p,octave,root,scale) for p in range(36,100)]
     self.assertEqual(len(set(pitches)),64)
     self.assertEqual(pitches,sorted(pitches));self.assertTrue(all(0<=p<=127 for p in pitches))
     self.assertEqual(pitches,[degree_pitch(d,root,scale) for d in range(-31+7*octave,33+7*octave)])
 def test_every_pad_native_pitch_and_led_is_one_exact_absolute_note(self):
  for pad in range(36,100):
   self.wire('note',pad,70);self.audio(1)
   pitch=pad_pitch(pad);stats=self.e.stats()
   self.assertTrue(stats['pitches']['gate'][0][pitch]&1)
   with patch('v4_controls.time.monotonic',return_value=pad):leds=led_values(self.m,stats,self.i)
   active=[p for p in range(36,100) if leds['note',p]==ROLE_PALETTE['silt'][0]]
   self.assertEqual(active,[pad])
   self.wire('note_off',pad,0);self.audio(1)
 def test_full_native_range_capture_validation_and_legacy_song_unchanged(self):
  before=json_ready(self.m.state)
  for pitch in (0,8,24,96,117,127):
   song=replace(self.m.state,layers=(replace(self.m.state.layers[0],events=(Event(1,pitch,.5,0,100),)),))
   self.assertEqual(decode_song(json_ready(song)),song)
   self.e.publish(song,self.m.capture_epoch);self.audio(1)
   self.e.lib.sw_performance_on(0,pitch+1,0,pitch,.5,0,self.m.capture_epoch,pitch+1);self.audio(1)
   self.assertTrue(self.e.pitches()['gate'][0][pitch]&1)
   self.e.lib.sw_performance_off(0,pitch+1);self.audio(1)
  self.assertEqual(json_ready(self.m.state),before)
  self.assertEqual(self.e.lib.sw_loop_abi(),6)
 def test_extended_range_records_exact_pitch_and_all_roles_remain_finite(self):
  self.i.performance.play();self.wire('note',36,90);self.audio(2048)
  self.wire('note_off',36,0);self.audio(1);self.i.performance.drain()
  self.assertEqual(self.m.state.layers[0].events[0].pitch,pad_pitch(36))
  self.assertEqual(decode_song(json_ready(self.m.state)),self.m.state)
  self.i.performance.stop();self.audio(1)
  for r,role in enumerate(ROLE_IDS):
   song=replace(self.m.state,layers=(replace(self.m.state.layers[0],role=role,parameters=DEFAULTS[r],events=()),))
   self.e.publish(song,self.m.capture_epoch);self.audio(1)
   for pitch in (0,127):
    self.e.lib.sw_performance_on(0,pitch+1,0,pitch,.5,0,self.m.capture_epoch,pitch+1)
    for _ in range(4):self.audio(8192)
    self.e.lib.sw_performance_off(0,pitch+1);self.audio(1)
  for pitch in (-1,128):
   self.assertEqual(self.e.lib.sw_performance_on(0,1,0,pitch,.5,0,self.m.capture_epoch,1),-2)
 def test_stopped_pressure_never_edits_parameters_history_or_records(self):
  self.m.state=replace(self.m.state,layers=(replace(self.m.state.layers[0],role='spore'),))
  self.e.publish(self.m.state,self.m.capture_epoch);self.audio(1)
  before=(self.m.state,self.m.revision,self.m.undo_stack)
  parser=MidiParser()
  for raw in ([208,127],[160,36,127],[144,0,127],[128,0,0]):
   for event in parser.feed(raw):self.i.wire(event)
  self.wire('note',36,90);self.audio(1)
  for value in (1,127,32,0):
   self.wire('poly_pressure',36,value);self.audio(256)
  self.assertTrue(self.e.stats()['manual'][0]['pressure']>0)
  self.wire('note_off',36,0);self.audio(1);self.i.performance.stop();self.audio(1)
  for value in range(128):
   self.wire('pressure',0,value);self.wire('poly_pressure',36,value)
  self.audio();self.i.performance.drain()
  self.assertEqual((self.m.state,self.m.revision,self.m.undo_stack),before)
  self.assertFalse(self.m.pending);self.assertFalse(self.m.state.layers[0].events)
 def test_idle_pressure_and_encoder_touch_do_not_cancel_pending_replacement(self):
  self.m.replacement_request=(1,'load');self.i.transition=('load','fixture')
  for raw in ([208,127],[160,36,127],[144,0,127],[128,0,0]):
   for event in MidiParser().feed(raw):self.i.wire(event)
  self.assertEqual(self.m.replacement_request,(1,'load'));self.assertEqual(self.i.transition,('load','fixture'))
 def test_channel_filter_neutral_encoder_sysex_and_no_autonomous_tick_edit(self):
  before=self.m.state;revision=self.m.revision
  for event in MidiParser().feed([177,72,1,176,72,0,144,1,127,128,1,0,240,0,33,29,1,1,58,34,100,247]):self.i.wire(event)
  for _ in range(10):self.audio();self.i.tick()
  self.assertEqual(self.m.state,before);self.assertEqual(self.m.revision,revision)
  self.wire('cc',72,1);self.assertAlmostEqual(self.m.state.layers[0].parameters[1],before.layers[0].parameters[1]+.02)
 def test_all_action_buttons_lit_in_every_page_and_shift_record_distinct(self):
  global_buttons=(29,30,49,50,51,56,58,62,63,81,82,85,86,92,110,112,113,118,119)
  for page in ('instrument','mixer','chooser','overview','key','library','recordings'):
   self.i.open_page(page)
   for shift in (False,True):
    self.i.shift=shift
    for overdub in (False,True):
     self.m.overdub=overdub;leds=led_values(self.m,self.e.stats(),self.i)
     self.assertTrue(all(leds['cc',n]>0 for n in global_buttons),(page,shift,overdub))
  self.m.overdub=False;off=led_values(self.m,self.e.stats(),self.i)['cc',86]
  self.m.overdub=True;on=led_values(self.m,self.e.stats(),self.i)['cc',86]
  self.assertNotEqual(on,off)
 def test_manager_action_buttons_and_confirmation_and_rename_lit(self):
  for page,buttons in (('overview',(20,21,26,27)),('key',tuple(range(102,110))+(26,27)),('library',(20,21,22,23,24,25,27,109)),('recordings',(20,21,22,23,24,25,27,104,105,109))):
   self.i.open_page(page);leds=led_values(self.m,self.e.stats(),self.i)
   self.assertTrue(all(leds['cc',n]>0 for n in buttons),page)
  self.i.open_page('library');self.i.rename='NAME'
  leds=led_values(self.m,self.e.stats(),self.i);self.assertTrue(all(leds['cc',n]>0 for n in (20,21,22,26,27)))
  self.i.rename=None;self.i.confirm=dict(action='delete')
  leds=led_values(self.m,self.e.stats(),self.i);self.assertTrue(all(leds['cc',n]>0 for n in (26,27)))
 def test_nonzero_channel_apply_does_not_cancel_key_draft_replacement_or_structure(self):
  self.i.open_page('key');self.i.key_draft=[60,'minor']
  self.m.replacement_request=(1,'load');self.i.transition=('load','fixture')
  before=self.m.state
  self.wire('cc',27,127,channel=1)
  self.assertEqual(self.m.state,before);self.assertEqual(self.m.replacement_request,(1,'load'))
  self.assertEqual(self.i.transition,('load','fixture'));self.assertEqual(self.i.key_draft,[60,'minor'])
  self.i.performance.structural=dict(token=1,cancelling=False)
  with patch.object(self.i.performance,'drain'),patch.object(self.i.performance,'cancel_structural') as cancel:
   self.wire('cc',27,127,channel=1);cancel.assert_not_called()
  self.i.performance.structural=None
  self.i.open_page('library');self.i.confirm=dict(action='load',row=dict(id='fixture'))
  self.m.replacement_request=(1,'load');self.i.transition=('load','fixture')
  self.wire('cc',27,127,channel=1)
  self.assertEqual(self.m.replacement_request,(1,'load'));self.assertEqual(self.i.transition,('load','fixture'))
 def test_opt_in_input_diagnostic_bounded_and_reports_actual_revision_changes(self):
  self.assertEqual(self.i.execute(dict(op='input_diagnostic_status')),dict(active=False,events=[]))
  self.i.execute(dict(op='input_diagnostic_start',seconds=30,count=2))
  self.wire('pressure',0,127);self.wire('cc',72,1);self.wire('cc',72,127)
  result=self.i.execute(dict(op='input_diagnostic_status'));self.assertFalse(result['active'])
  self.assertEqual(len(result['events']),2)
  self.assertEqual(result['events'][0]['before_revision'],result['events'][0]['after_revision'])
  self.assertEqual(result['events'][1]['after_revision'],result['events'][1]['before_revision']+1)
  for request in (dict(seconds=31),dict(count=2049)):
   with self.assertRaises(ValueError):self.i.execute(dict(op='input_diagnostic_start',**request))
