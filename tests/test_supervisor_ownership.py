"""Real inert subprocess gates; no device or stock code is reachable."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import supervisor

class LaunchOwnership(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.home=Path(self.tmp.name)
  (self.home/'src').mkdir();self.marker=self.home/'hardware-opened'
  (self.home/'src/app.py').write_text("from pathlib import Path\nPath(__file__).resolve().parents[1].joinpath('hardware-opened').touch()\n")
  self.s=supervisor.Supervisor(self.home,self.home)
  self.log=open(self.home/'log','w');self.addCleanup(self.log.close);self.s.log=self.log
 def test_child_waits_for_durable_pid_before_payload_runs(self):
  record=supervisor.process.record;seen=[]
  def durable(*args):
   self.assertFalse(self.marker.exists());record(*args)
   data=json.loads(supervisor.process.REGISTRY.read_text());seen.append(data)
   self.assertTrue(supervisor.process.alive(*data['child']))
  with patch.object(supervisor.process,'record',side_effect=durable):self.s.launch(False,'test',1)
  self.s.child.wait(timeout=2)
  self.assertTrue(self.marker.exists());self.assertEqual(len(seen),1);self.assertTrue(self.s.stop_child())
 def test_failed_registry_write_cancels_payload(self):
  with patch.object(supervisor.process,'record',side_effect=OSError('simulated disk failure')):
   with self.assertRaises(OSError):self.s.launch(False,'test',1)
  self.s.child.wait(timeout=2);self.assertFalse(self.marker.exists());self.assertTrue(self.s.stop_child())

if __name__=='__main__':unittest.main()
