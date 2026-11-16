import copy
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from model import Model, seeded, validate_session, melodic_note, pad_coord, relative
from app import Engine, Instrument
from graphics import render
ROOT=Path(__file__).resolve().parents[1]

class Sessions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.m=Model(Path(self.tmp.name)/'current.json')
    def test_atomic_roundtrip(self):
        self.m.save();self.assertEqual(Model(self.m.path).state,self.m.state)
        self.assertFalse(self.m.path.with_suffix('.tmp').exists())
    def test_persistent_undo_and_revision(self):
        old=copy.deepcopy(self.m.state)
        self.m.execute(dict(op='set_tempo',revision=0,value=90))
        loaded=Model(self.m.path);self.assertEqual(loaded.revision,1)
        loaded.execute(dict(op='undo',revision=1));self.assertEqual(loaded.state,old)
    def test_tempo_undo(self):
        old=copy.deepcopy(self.m.state)
        self.m.execute(dict(op='set_tempo',revision=0,value=92))
        self.m.execute(dict(op='undo',revision=1));self.assertEqual(self.m.state,old)
    def test_reject_stale_nonfinite_and_unknown(self):
        for req in [dict(op='set_tempo',revision=1,value=80),dict(op='set_tempo',revision=0,value=float('nan')),dict(op='set_tempo',revision=0,value=180),dict(op='query_state',shell='oops')]:
            with self.assertRaises(ValueError):self.m.execute(req)
        self.assertEqual(self.m.revision,0)
    def test_propose_apply_and_replay(self):
        pattern=[62]+[0]*7
        self.m.execute(dict(op='propose_pattern',track=4,pattern=pattern,revision=0,id='gentle'))
        self.assertNotEqual(self.m.state['tracks'][4]['pattern'],pattern)
        self.m.execute(dict(op='apply_pattern',id='gentle',revision=0))
        self.assertEqual(self.m.state['tracks'][4]['pattern'],pattern)
        with self.assertRaises(ValueError):self.m.execute(dict(op='apply_pattern',id='gentle',revision=1))
    def test_stale_proposal(self):
        self.m.execute(dict(op='propose_pattern',track=4,pattern=[62]*8,revision=0,id='a'))
        self.m.execute(dict(op='set_tempo',value=80,revision=0))
        with self.assertRaises(ValueError):self.m.execute(dict(op='apply_pattern',id='a',revision=1))
    def test_invalid_pattern_and_parameters(self):
        for pattern in [[0]*9,[2]*8,[float('nan')]*8]:
            with self.assertRaises(ValueError):self.m.execute(dict(op='propose_pattern',track=4,pattern=pattern,revision=0,id='a'))
        for params in [{'level':1.2},{'muted':1},{'x':.5}]:
            with self.assertRaises(ValueError):self.m.execute(dict(op='set_track_parameters',track=0,parameters=params,revision=0))
    def test_schema_reject(self):
        s=seeded();s['tracks'][0]['pattern'][0]=True
        with self.assertRaises(ValueError):validate_session(s)
    def test_track_update_save(self):
        self.m.execute(dict(op='set_track_parameters',track=4,parameters={'level':.2,'muted':True},revision=0))
        self.assertTrue(Model(self.m.path).state['tracks'][4]['muted'])
    def test_graphics_animation(self):
        a=render(self.m,0,1);b=render(self.m,0,2)
        self.assertEqual(len(a),327680);self.assertNotEqual(a,b)  # decorative local breathing
        self.assertEqual(b,render(self.m,0,2))  # same moment is deterministic
        self.m.playing=True;c=render(self.m,4,2);self.assertNotEqual(b,c)

class Audio(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.m=Model(Path(self.tmp.name)/'song.json');self.e=Engine(ROOT/'.build/engine.so');self.e.lib.sw_reset();self.e.sync(self.m)
        self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
    def render(self,n):
        out=(C.c_float*(n*2))();self.e.lib.sw_render(out,n);return list(out)
    def test_silent_then_demo(self):
        self.assertTrue(all(x==0 for x in self.render(512)))
        self.m.playing=True;self.e.sync(self.m);x=self.render(44100)
        self.assertTrue(all(math.isfinite(v) and abs(v)<=.250001 for v in x));self.assertGreater(max(map(abs,x)),.005)
    def test_sequencer_sample_clock(self):
        self.m.state['tempo']=120;self.m.playing=True;self.e.sync(self.m)
        self.render(5512);self.assertEqual(self.e.stats()['position'],0)
        self.render(2);self.assertEqual(self.e.stats()['position'],1)
    def test_stop_silences_tails(self):
        self.m.playing=True;self.e.sync(self.m);self.render(1024)
        self.m.playing=False;self.e.sync(self.m);self.render(10000);self.assertTrue(all(x==0 for x in self.render(1024)))
    def test_input_dispatch_and_note(self):
        inst=Instrument(self.m,self.e);inst.event('cc',50,127);self.assertEqual(self.m.mode,'notes')
        inst.event('note',60,100);self.assertGreater(max(map(abs,self.render(4410))),0)
        inst.event('cc',85,127);self.assertTrue(self.m.playing)
        inst.event('cc',79,127);self.assertAlmostEqual(self.m.state['master'],.27)
        inst.event('cc',51,127);before=self.m.state['tracks'][0]['pattern'][0]
        inst.event('note',36,100);self.assertNotEqual(before,self.m.state['tracks'][0]['pattern'][0])
    def test_queue_bounded(self):
        self.render(1)
        results=[self.e.lib.sw_command(1,0,0,74) for _ in range(1100)]
        self.assertIn(-1,results)
    def test_all_tracks_finite_at_max(self):
        for t in range(8):
            self.e.command(4,t,0,1);self.e.command(4,t,2,1)
            for note in [36,50,62,74,86]:self.e.command(5,t,note,1)
        self.e.command(6,value=.7);self.e.command(7,value=.8)
        x=self.render(44100);self.assertTrue(all(math.isfinite(v) and abs(v)<=.250001 for v in x));self.assertGreater(max(map(abs,x)),.01)

class Mapping(unittest.TestCase):
    def test_pad_corners(self):
        self.assertEqual(pad_coord(36),(0,0));self.assertEqual(pad_coord(99),(7,7))
    def test_relative(self):
        self.assertEqual(relative(1),1);self.assertEqual(relative(127),-1);self.assertEqual(relative(117),-11)
    def test_scale_bounded(self):
        self.assertTrue(all(24<=melodic_note(n,62)<=96 for n in range(36,100)))

if __name__=='__main__':unittest.main()
