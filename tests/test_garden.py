import copy
import ctypes as C
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Engine, Instrument
from graphics import VisualState, render
from model import Model, GARDENS, grown
ROOT=Path(__file__).resolve().parents[1]

class Garden(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.m=Model(Path(self.temp.name)/'session.json')
    def test_distinct_pattern_previews_show_ghost_steps_without_changing_music(self):
        old=copy.deepcopy(self.m.state)
        # Equal density keeps macro numbers identical; only the proposed steps differ.
        a=[60,0]+[0]*6;b=[0,60]+[0]*6
        frames=[]
        for pattern in (a,b):
            self.m.execute(dict(op='cancel_preview'))
            self.m.execute(dict(op='propose_pattern',id='ghost',track=0,pattern=pattern,revision=0))
            frames.append(render(self.m,0,1))
        def region(frame,x,width):
            return b''.join(frame[(y*1024+x)*2:(y*1024+x+width)*2] for y in range(107,114))
        self.assertNotEqual(region(frames[0],0,120),region(frames[1],0,120))
        self.assertEqual(region(frames[0],120,840),region(frames[1],120,840))
        self.assertEqual(self.m.state,old);self.assertEqual(self.m.revision,0)

    def test_grow_deterministic_sparse_in_key_preserves_controls(self):
        old=copy.deepcopy(self.m.state);notes=[n for t in old['tracks'] for n in t['pattern'] if n]
        for seed in range(40):
            a=grown(old,seed);self.assertEqual(a,grown(old,seed));self.assertNotEqual(a,old)
            for t,track in enumerate(a['tracks']):
                self.assertLessEqual(sum(bool(n) for n in track['pattern']),3)
                for k in track:
                    if k!='pattern':self.assertEqual(track[k],old['tracks'][t][k])
                for note in track['pattern']:
                    if note:self.assertTrue(min(notes)<=note<=max(notes) and (note-old['root'])%12 in {0,2,3,5,7,9,10})
            for k in ('tempo','master','space','root'):self.assertEqual(a[k],old[k])
        self.assertEqual(self.m.state,old)
    def test_preview_apply_undo_and_persist(self):
        old=copy.deepcopy(self.m.state)
        self.m.execute(dict(op='propose_grow',id='sprout',seed=19,revision=0))
        self.assertEqual(self.m.state,old);self.assertEqual(self.m.revision,0)
        self.assertIsNotNone(self.m.preview)
        self.m.execute(dict(op='apply_grow',id='sprout',revision=0))
        self.assertNotEqual(self.m.state,old);self.assertIsNone(self.m.preview)
        loaded=Model(self.m.path);loaded.execute(dict(op='undo',revision=1));self.assertEqual(loaded.state,old)
    def test_grow_stale_cancel_and_validation(self):
        self.m.execute(dict(op='propose_grow',id='sprout',seed=19,revision=0))
        self.m.execute(dict(op='cancel_preview'));self.assertFalse(self.m.proposals)
        for seed in (True,-1,1000001,float('nan')):
            with self.assertRaises(ValueError):self.m.execute(dict(op='propose_grow',id='bad',seed=seed,revision=0))
        self.m.execute(dict(op='propose_grow',id='sprout',seed=19,revision=0))
        self.m.execute(dict(op='set_tempo',value=63,revision=0))
        with self.assertRaises(ValueError):self.m.execute(dict(op='apply_grow',id='sprout',revision=1))
    def test_garden_known_names_and_undo_preserve_transport(self):
        for name in GARDENS:
            old=copy.deepcopy(self.m.state);self.m.playing=True
            self.m.execute(dict(op='garden',name=name,revision=self.m.revision))
            self.assertTrue(self.m.playing)
            self.assertLessEqual(self.m.state['master'],.28)
            self.m.execute(dict(op='undo',revision=self.m.revision));self.assertEqual(self.m.state,old)
        with self.assertRaises(ValueError):self.m.execute(dict(op='garden',name='unknown',revision=self.m.revision))

class NativeGarden(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.m=Model(Path(self.temp.name)/'session.json');self.e=Engine(ROOT/'.build/engine.so')
        self.e.lib.sw_reset();self.e.sync(self.m);self.inst=Instrument(self.m,self.e)
        self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
    def audio(self,n):
        out=(C.c_float*(n*2))();self.e.lib.sw_render(out,n);return list(out)
    def test_new_applies_actual_pattern_preview_and_undo(self):
        old=copy.deepcopy(self.m.state);pattern=[96]+[0]*7
        self.m.execute(dict(op='propose_pattern',id='pond',track=0,pattern=pattern,revision=0))
        self.assertEqual(self.m.state,old)
        self.inst.event('cc',92,127)
        self.assertEqual(self.m.state['tracks'][0]['pattern'],pattern)
        self.assertEqual(self.m.state['tracks'][1:],old['tracks'][1:])
        self.assertIsNone(self.m.preview);self.assertEqual(self.m.revision,1)
        self.inst.event('cc',119,127);self.assertEqual(self.m.state,old)
    def test_new_rejects_stale_pattern_preview(self):
        self.m.execute(dict(op='propose_pattern',id='stale',track=0,pattern=[96]+[0]*7,revision=0))
        self.m.proposals['stale']['revision']=-1
        old=copy.deepcopy(self.m.state)
        with self.assertRaisesRegex(ValueError,'stale'):self.inst.event('cc',92,127)
        self.assertEqual(self.m.state,old);self.assertEqual(self.m.revision,0)
    def test_delayed_native_envelope_consumes_real_onset_once(self):
        v=VisualState();zero=dict(envelopes=[0]*8,onsets=[0]*8)
        v.update(zero,0)
        delayed=dict(envelopes=[0]*8,onsets=[0,0,1,0,0,0,0,0])
        v.update(delayed,.1);self.assertFalse(v.rings[2])
        delayed['envelopes'][2]=.01
        v.update(delayed,.2);self.assertEqual(v.rings[2],[.2])
        v.update(delayed,.3);self.assertEqual(v.rings[2],[.2])
        self.assertTrue(all(not v.rings[t] for t in range(8) if t!=2))
    def test_expired_onset_does_not_create_late_or_idle_ripple(self):
        v=VisualState();state=dict(envelopes=[0]*8,onsets=[1]+[0]*7)
        for now in (0,.1,.3,.5,1):
            v.update(state,now);self.assertTrue(all(not rings for rings in v.rings))
        state['envelopes'][0]=.1
        v.update(state,1.1);self.assertFalse(v.rings[0])
    def test_positive_envelope_without_onset_never_invents_ripple(self):
        v=VisualState();state=dict(envelopes=[.1]+[0]*7,onsets=[0]*8)
        v.update(state,0);v.update(state,.1)
        self.assertTrue(all(not rings for rings in v.rings))
    def test_no_in_key_room_does_not_crash_live_grow(self):
        for track in self.m.state['tracks']:track['pattern']=[0]*8
        self.m.state['tracks'][0]['pattern'][0]=37
        before=copy.deepcopy(self.m.state);self.inst.event('cc',92,127)
        self.assertEqual(self.m.state,before);self.assertEqual(self.m.revision,0)
        self.assertIn('No scale notes',self.m.message)
    def test_real_onsets_and_envelopes_not_ui_guesses(self):
        self.audio(512);self.assertEqual(self.e.stats()['onsets'],[0]*8)
        self.e.command(5,3,62,.8);self.audio(4410);s=self.e.stats()
        self.assertEqual(s['onsets'],[0,0,0,1,0,0,0,0]);self.assertGreater(s['envelopes'][3],0)
        self.assertTrue(all(s['envelopes'][i]==0 for i in range(8) if i!=3))
        self.e.command(2,0);self.audio(10000);self.assertEqual(self.e.stats()['envelopes'],[0]*8)
    def test_grow_one_gesture_and_garden_keep_native_phase(self):
        self.m.playing=True;self.e.sync(self.m);self.audio(18000);position=self.e.stats()['position']
        old=copy.deepcopy(self.m.state)
        self.inst.event('cc',92,127);self.assertNotEqual(self.m.state,old);self.assertTrue(self.m.playing)
        self.assertIsNone(self.m.preview);self.audio(1);self.assertEqual(self.e.stats()['position'],position)
        self.inst.event('cc',119,127);self.assertEqual(self.m.state,old)
        self.inst.event('cc',49,127);self.inst.event('cc',92,127);self.inst.event('cc',49,0)
        self.audio(1);self.assertTrue(self.m.playing);self.assertEqual(self.e.stats()['position'],position)
    def test_native_visuals_settle_while_idle_creatures_breathe(self):
        v=VisualState();idle=render(self.m,0,0,telemetry=self.e.stats(),visual=v)
        self.assertNotEqual(idle,render(self.m,0,2,telemetry=self.e.stats(),visual=v))
        self.assertEqual(v.levels,[0]*8);self.assertTrue(all(not r for r in v.rings))
        self.e.command(5,2,57,.8);self.audio(4410)
        a=render(self.m,0,2.1,telemetry=self.e.stats(),visual=v)
        self.assertGreater(v.levels[2],0);self.assertTrue(all(v.levels[t]==0 for t in range(8) if t!=2))
        b=render(self.m,0,2.3,telemetry=self.e.stats(),visual=v);self.assertNotEqual(a,b)
        self.e.command(2,0);self.audio(10000)
        for i in range(50):rest=render(self.m,0,2.4+i*.1,telemetry=self.e.stats(),visual=v)
        self.assertNotEqual(rest,render(self.m,0,10,telemetry=self.e.stats(),visual=v))
        self.assertEqual(v.levels,[0]*8);self.assertTrue(all(not r for r in v.rings))
    def test_presets_remain_finite_and_soft_during_playback(self):
        import math
        self.m.playing=True;self.e.sync(self.m);previous=0
        for name in GARDENS:
            self.m.execute(dict(op='garden',name=name,revision=self.m.revision));self.e.sync(self.m)
            pcm=self.audio(22050)
            self.assertTrue(all(math.isfinite(x) and abs(x)<=.250001 for x in pcm))
            left=pcm[::2];self.assertLess(max(abs(b-a) for a,b in zip([previous]+left,left)),.02);previous=left[-1]
