"""Single-grid playback, full master range and lossless legacy rollback."""
import copy
import ctypes as C
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from app import Engine,Instrument
from expression import pad_leds
from model import Model,seeded,STEPS,GARDENS,garden,grown


class EightSteps(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'current.json';self.m=Model(self.path)
  self.e=Engine(ROOT/'.build/engine.so');self.e.lib.sw_reset();self.e.sync(self.m)
  self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
  self.i=Instrument(self.m,self.e)
 def audio(self,n):
  out=(C.c_float*(n*2))();self.e.lib.sw_render(out,n);return list(out)
 def test_full_master_both_encoders_agent_and_persistence(self):
  for encoder in (78,79):
   self.m.state['master']=.99
   self.i.execute(dict(op='event',kind='cc',number=encoder,value=1))
   self.assertEqual(self.m.state['master'],1)
   self.assertEqual(Model(self.path).state['master'],1)
   self.i.execute(dict(op='event',kind='cc',number=encoder,value=1))
   self.assertEqual(self.m.state['master'],1)
   self.i.execute(dict(op='event',kind='cc',number=encoder,value=127))
   self.assertAlmostEqual(self.m.state['master'],.99)
  self.i.execute(dict(op='set_master',value=1,revision=self.m.revision))
  self.assertEqual(Model(self.path).state['master'],1)
  for value in (1.01,-.01,float('nan')):
   with self.assertRaises(ValueError):self.m.execute(dict(op='set_master',value=value,revision=self.m.revision))
 def test_native_full_master_is_effective_finite_and_limited(self):
  energies=[]
  for master in (.7,1):
   self.e.lib.sw_reset();self.e.previous=None;self.e.playing=None
   self.m.state['space']=0;self.m.state['master']=master
   self.m.state['tracks'][4]['level']=.08;self.e.sync(self.m)
   self.e.manual_on(0,1,4,62,.2);self.audio(44100)
   pcm=self.audio(4410)
   self.assertTrue(all(math.isfinite(v) and abs(v)<=.250001 for v in pcm))
   energies.append(math.sqrt(sum(v*v for v in pcm)/len(pcm)))
  self.assertGreater(energies[1],energies[0]*1.35)
  for t in range(8):
   self.e.command(4,t,0,1);self.e.command(5,t,62,1)
  self.assertTrue(all(math.isfinite(v) and abs(v)<=.250001 for v in self.audio(44100)))
 def test_native_wrap_three_loops_and_hidden_steps_never_trigger(self):
  self.m.state['tempo']=120;self.m.state['space']=0
  for track in self.m.state['tracks']:track['pattern']=[0]*STEPS
  self.m.playing=True;self.e.sync(self.m)
  for t in range(8):
   for step in range(8,16):self.e.command(3,t,step,62)
  positions=[]
  for step in range(24):
   self.audio(1 if step==0 else 5513 if step%2 else 5512)
   positions.append(self.e.stats()['position'])
  self.assertEqual(positions,list(range(8))*3)
  self.assertEqual(self.e.stats()['onsets'],[0]*8)
  self.assertTrue(all(v==0 for v in self.audio(4410)))
  self.e.command(3,0,7,38)
  self.audio(44100*3)
  self.assertEqual(self.e.stats()['onsets'][0],3)
 def test_single_pad_grid_and_cursor_for_every_lane(self):
  for track in self.m.state['tracks']:track['pattern']=[0]*STEPS
  for pad in range(36,100):self.i.event('note',pad,100)
  self.assertTrue(all(len(t['pattern'])==8 and all(t['pattern']) for t in self.m.state['tracks']))
  for button in (63,62,63):
   self.i.event('cc',button,127);self.assertEqual(self.m.page,0)
  self.m.playing=True
  for position in range(8):
   leds=pad_leds(self.m,dict(position=position,manual=[]),self.i.expression)
   self.assertEqual([n for n,v in leds.items() if v==15],[36+row*8+position for row in range(8)])
 def test_agent_preview_and_variations_are_exactly_eight(self):
  with self.assertRaises(ValueError):self.m.execute(dict(op='propose_pattern',track=0,pattern=[62]*16,id='old',revision=0))
  self.m.execute(dict(op='propose_pattern',track=0,pattern=[62]*8,id='new',revision=0))
  self.assertEqual(len(self.m.preview['patterns'][0]),8)
  self.m.execute(dict(op='apply_pattern',id='new',revision=0))
  self.m.execute(dict(op='undo',revision=1))
  for state in [seeded(),grown(self.m.state,100)]+[garden(n) for n in GARDENS]:
   self.assertTrue(all(len(t['pattern'])==8 for t in state['tracks']))
 def legacy(self):
  state=seeded();state['schema']=1;state['master']=.13
  for t,track in enumerate(state['tracks']):track['pattern']=[38+t]*8+[74+t]*8
  history=[]
  for i in range(64):
   old=copy.deepcopy(state);old['tempo']=30+i;history.append(old)
  return dict(format='stillwater-session',version=2,revision=862,state=state,history=history)
 def test_legacy_full_history_migration_preserves_original_and_controls(self):
  legacy=self.legacy();original=json.dumps(legacy).encode();self.path.write_bytes(original)
  m=Model(self.path)
  self.assertEqual(m.migration_backup.read_bytes(),original)
  self.assertEqual(m.revision,862);self.assertEqual(len(m.history),64)
  self.assertEqual(m.state['master'],.13)
  for actual,old in zip([m.state]+m.history,[legacy['state']]+legacy['history']):
   expected=copy.deepcopy(old);expected['schema']=2
   for track in expected['tracks']:track['pattern']=track['pattern'][:8]
   self.assertEqual(actual,expected)
  m.execute(dict(op='undo',revision=862));self.assertEqual(m.state['tempo'],93)
  self.assertEqual(Model(self.path).state,m.state)
  self.assertEqual(json.loads(self.path.read_text())['version'],3)
  self.assertEqual(m.migration_backup.read_bytes(),original)
 def test_invalid_discarded_note_or_history_never_rewrites_original(self):
  for which in ('state','history'):
   legacy=self.legacy();target=legacy['state'] if which=='state' else legacy['history'][0]
   target['tracks'][0]['pattern'][15]=2
   original=json.dumps(legacy).encode();self.path.write_bytes(original)
   with self.assertRaises(ValueError):Model(self.path)
   self.assertEqual(self.path.read_bytes(),original)
   self.assertEqual(list(self.path.parent.glob('*pre-eight*')),[])
 def test_failed_atomic_migration_keeps_full_original_and_backup(self):
  original=json.dumps(self.legacy()).encode();self.path.write_bytes(original)
  with patch('model.os.replace',side_effect=OSError('simulated disk failure')):
   with self.assertRaises(OSError):Model(self.path)
  self.assertEqual(self.path.read_bytes(),original)
  backups=list(self.path.parent.glob('*pre-eight*'));self.assertEqual(len(backups),1)
  self.assertEqual(backups[0].read_bytes(),original)
  self.assertEqual(len(Model(self.path).state['tracks'][0]['pattern']),8)
 def test_backup_fsync_failure_retries_sync_before_migration(self):
  original=json.dumps(self.legacy()).encode();self.path.write_bytes(original)
  # Complete buffered write/flush, then fail the backup's first durability sync.
  with patch('model.os.fsync',side_effect=OSError('backup sync failed')):
   with self.assertRaises(OSError):Model(self.path)
  backup=next(self.path.parent.glob('*pre-eight*'))
  self.assertEqual(backup.read_bytes(),original)
  self.assertEqual(self.path.read_bytes(),original)
  # Matching existing bytes alone cannot authorize migration on the next load.
  with patch('model.os.fsync',side_effect=OSError('backup sync failed again')) as sync, patch('model.os.replace') as replace:
   with self.assertRaises(OSError):Model(self.path)
   self.assertEqual(sync.call_count,1);replace.assert_not_called()
  self.assertEqual(self.path.read_bytes(),original)
  # A successful retry must sync that backup inode before replacing current.
  events=[];real_sync=os.fsync;real_replace=os.replace;inode=backup.stat().st_ino
  def sync(fd):
   if os.fstat(fd).st_ino==inode:events.append('backup synced')
   return real_sync(fd)
  def replace(src,dst):
   self.assertEqual(events,['backup synced']);events.append('current replaced')
   return real_replace(src,dst)
  with patch('model.os.fsync',side_effect=sync),patch('model.os.replace',side_effect=replace):
   m=Model(self.path)
  self.assertEqual(events,['backup synced','current replaced'])
  self.assertEqual(backup.read_bytes(),original)
  self.assertEqual(len(m.state['tracks'][0]['pattern']),8)
 def test_legacy_two_file_disagreement_in_hidden_half_is_rejected(self):
  legacy=self.legacy();state=legacy['state'];self.path.write_text(json.dumps(state))
  legacy['state']=copy.deepcopy(state);legacy['state']['tracks'][0]['pattern'][15]=88
  self.path.with_suffix('.history.json').write_text(json.dumps(legacy))
  original=self.path.read_bytes()
  with self.assertRaises(ValueError):Model(self.path)
  self.assertEqual(self.path.read_bytes(),original)

if __name__=='__main__':unittest.main()
