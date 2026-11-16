"""Real native PCM: role identity, continuous controls, bounded maximum mix."""
import ctypes as C
from dataclasses import replace
import math
from pathlib import Path
import sys
import time
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import blank,Layer
from loop_engine import LoopEngine
from roles import ROLE_IDS,DEFAULTS

class DSP(unittest.TestCase):
 def setUp(self):
  self.e=LoopEngine(ROOT/'.build/engine.so');self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
 def audio(self,n):
  out=(C.c_float*(n*2))();self.e.lib.sw_render(out,n);return list(out)
 def start(self,role,parameters=None):
  self.e.lib.sw_reset();self.e.generation=0;song=blank(seed=1)
  layer=Layer(0,ROLE_IDS[role],parameters=tuple(parameters or DEFAULTS[role]))
  song=replace(song,role_order=(ROLE_IDS[role],)+tuple(r for r in ROLE_IDS if r!=ROLE_IDS[role]),layers=(layer,))
  self.e.publish(song,1);self.audio(1);self.e.check(self.e.lib.sw_performance_on(0,1,0,62,.8,0,1,1))
 def test_roles_are_audible_distinct_and_finite(self):
  fingerprints=[]
  for role in range(8):
   self.start(role);pcm=self.audio(44100)
   self.assertTrue(all(math.isfinite(x) and abs(x)<=.25 for x in pcm));self.assertGreater(sum(x*x for x in pcm),.001)
   fingerprints.append(pcm[8000:9000])
  for a in range(8):
   for b in range(a):self.assertGreater(sum(abs(x-y) for x,y in zip(fingerprints[a],fingerprints[b])),.01)
 def test_every_role_macro_changes_real_pcm(self):
  for role in range(8):
   for macro in range(8):
    with self.subTest(role=ROLE_IDS[role],macro=macro):
     versions=[]
     for value in (.05,.95):
      params=list(DEFAULTS[role]);params[macro]=value;self.start(role,params);pcm=self.audio(22050);self.e.lib.sw_performance_off(0,1);pcm+=self.audio(22050);versions.append(pcm)
     self.assertGreater(sum(abs(a-b) for a,b in zip(*versions)),.0001)
 def test_all64_macros_respond_after_note_onset_without_retrigger(self):
  for role in range(8):
   for macro in range(8):
    with self.subTest(role=ROLE_IDS[role],macro=macro):
     versions=[]
     for value in (.05,.95):
      self.start(role);self.audio(4410);self.e.check(self.e.lib.sw_layer_parameter(0,macro,value))
      pcm=self.audio(11025);self.e.lib.sw_performance_off(0,1);pcm+=self.audio(22050);versions.append(pcm)
     self.assertGreater(sum(abs(a-b) for a,b in zip(*versions)),.000001)
 def test_held_and_released_voices_respond_to_level_and_mute(self):
  for held in (True,False):
   self.start(0);self.audio(4410)
   if not held:self.e.lib.sw_performance_off(0,1);self.audio(1)
   before=self.audio(2048);self.e.check(self.e.lib.sw_layer_parameter(0,8,0));self.audio(20000);after=self.audio(2048)
   self.assertLess(sum(x*x for x in after),sum(x*x for x in before)*.00001)
 def test_stop_reaches_exact_silence_and_restarts_without_old_tail(self):
  self.start(6);self.audio(44100);self.e.transport(0,True,1);self.audio(12000)
  self.assertTrue(all(x==0 for x in self.audio(2048)))
  self.e.transport(2,True,1);self.assertTrue(all(x==0 for x in self.audio(4096)))
 def test_all_roles_maximum_settings_stay_bounded(self):
  self.e.lib.sw_reset();self.e.generation=0;song=blank(seed=1)
  song=replace(song,role_order=ROLE_IDS,layers=tuple(Layer(i,r,level=1,parameters=(1,)*8) for i,r in enumerate(ROLE_IDS)),master=1)
  self.e.publish(song,1);self.audio(1)
  for i in range(8):self.e.lib.sw_performance_on(i,i+1,i,38+i*4,1,0,1,i+1)
  pcm=self.audio(88200);self.assertTrue(all(math.isfinite(x) and abs(x)<=.25 for x in pcm))
