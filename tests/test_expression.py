import copy
import ctypes as C
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Engine, Instrument
from midi import MidiParser, EventTap
from hardware import Midi
from expression import pad_leds
from graphics import render, VisualState
from model import Model
ROOT=Path(__file__).resolve().parents[1]


class Parser(unittest.TestCase):
    def test_running_status_realtime_channels_pressure_and_release(self):
        p=MidiParser();events=[]
        for part in (b'\x92\x3c',b'\xf8\x64\x3d\x50\xd2',b'\x40\xf8\x60\xa2\x3c\x7f\x82\x3c\x20\x92\x3d\x00'):
            events+=p.feed(part)
        self.assertEqual([(e['kind'],e['channel'],e['number'],e['value']) for e in events],[('note',2,60,100),('note',2,61,80),('pressure',2,0,64),('pressure',2,0,96),('poly_pressure',2,60,127),('note_off',2,60,32),('note_off',2,61,0)])
    def test_system_common_and_sysex_cancel_running_status(self):
        p=MidiParser()
        for boundary in (b'\xf1\x01',b'\xf2\x01\x02',b'\xf3\x01',b'\xf4',b'\xf5',b'\xf6',b'\xf7',b'\xf0\x01\xf8\x02\xf7'):
            p.feed(b'\x91\x3c\x64')
            out=p.feed(boundary+b'\x3d\x64')
            self.assertFalse(any(e['kind']=='note' for e in out))
        self.assertEqual(p.feed(b'\xe3\x00\x40\xb3\x4a\x7f'),[dict(kind='bend',channel=3,number=0,value=8192),dict(kind='cc',channel=3,number=74,value=127)])
    def test_variable_sysex_tap_is_bounded(self):
        tap=EventTap(10,3);p=MidiParser(tap)
        p.feed(b'\xf0\x01\xf7\xf0'+b'\x01'*100+b'\xf7')
        self.assertEqual(len(tap.records[1]['data']),32)
        self.assertTrue(tap.records[1]['truncated']);self.assertEqual(tap.records[1]['length'],101)
    def test_chunking_does_not_cross_contaminate_running_status(self):
        wire=b'\x93\x3c\x50\xf8\x3d\x60\xd4\x10\x20\xf2\x01\x02\x22\x33\xb2\x4a\x7f\xa3\x3c\x40'
        expected=MidiParser().feed(wire);p=MidiParser();actual=[]
        for b in wire:actual+=p.feed(bytes([b]))
        self.assertEqual(actual,expected)
    def test_status_interrupts_partial_message(self):
        p=MidiParser();self.assertEqual(p.feed(b'\x90\x3c\xd4\x7f'),[dict(kind='pressure',channel=4,number=0,value=127)])
    def test_sysex_bounded_recovers_at_next_status(self):
        p=MidiParser();self.assertFalse(p.feed(b'\xf0'+b'\x01'*9000+b'\xf7'))
        self.assertEqual(len(p.feed(b'\x90\x3c\x64')),1)
    def test_tap_count_time_bounds_and_ranges(self):
        clock=[0.];tap=EventTap(.5,3,lambda:clock[0]);p=MidiParser(tap)
        p.feed(b'\x92\x3c\x40\x3d\x60\xf8\xd2\x7f')
        self.assertEqual(tap.total,3);self.assertTrue(tap.done)
        self.assertEqual(tap.ranges['92'],dict(count=2,min=[60,64],max=[61,96]))
        self.assertEqual(tap.records[0]['channel'],2)
        tap=EventTap(.5,3,lambda:clock[0]);clock[0]=1;p=MidiParser(tap);p.feed(b'\x90\x3c\x64')
        self.assertFalse(tap.records)
        with self.assertRaises(ValueError):EventTap(31,100)


class Output(unittest.TestCase):
    def test_nonblocking_partial_output_preserves_message_bytes_and_bounds(self):
        class Alsa:
            def __init__(self):self.allow=0;self.sent=bytearray()
            def snd_rawmidi_write(self,output,data,size):
                if self.allow==0:return -11
                n=min(size,self.allow);self.sent.extend(data[:n]);return n
        m=Midi.__new__(Midi);m.lib=Alsa();m.output=None;m.outgoing=bytearray()
        self.assertTrue(m.note(60,15));self.assertTrue(m.note(61,93))
        m.lib.allow=1
        for _ in range(6):m.flush()
        self.assertEqual(m.lib.sent,bytes([0x90,60,15,0x90,61,93]))
        m.lib.allow=0;self.assertTrue(m.write(bytes(1024)));self.assertFalse(m.note(62,94))
        self.assertEqual(len(m.outgoing),1024)


class NativeExpression(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.m=Model(Path(self.temp.name)/'current.json');self.e=Engine(ROOT/'.build/engine.so')
        self.e.lib.sw_reset();self.i=Instrument(self.m,self.e);self.e.sync(self.m);self.i.event('cc',50,127)
        self.p=MidiParser();self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
    def wire(self,data):
        for e in self.p.feed(bytes(data)):self.i.wire(e)
    def audio(self,seconds):
        out=(C.c_float*(int(seconds*44100)*2))();self.e.lib.sw_render(out,len(out)//2)
        self.assertTrue(all(math.isfinite(v) and abs(v)<=.250001 for v in out))
        return list(out)
    def test_pressure_warms_held_voice_smoothly(self):
        self.wire([0x92,60,100]);self.audio(.4);before=self.e.stats()['manual'][0]
        self.wire([0xd2,127]);pcm=self.audio(.5);after=self.e.stats()['manual'][0]
        self.assertGreater(after['pressure'],.99);self.assertGreater(after['envelope'],before['envelope'])
        self.assertLess(max(abs(a-b) for a,b in zip(pcm[::2],pcm[2::2])),.02)
    def test_release_fades_and_velocity_zero_releases(self):
        for off in ([0x82,60,64],[0x92,60,0]):
            self.wire([0x92,60,100]);self.audio(.3);self.wire(off);self.audio(.1)
            self.assertFalse(self.e.stats()['manual'][0]['held'])
            self.audio(4);self.assertEqual(self.e.stats()['manual'][0]['envelope'],0)
    def test_eight_simultaneous_and_stolen_identity_isolated(self):
        for channel in range(1,9):self.wire([0x90+channel,60+channel,100])
        self.audio(.3);self.assertEqual(sum(m['held'] for m in self.e.stats()['manual']),8)
        old=self.i.expression.slots[0]['token'];self.wire([0x99,75,100]);self.audio(.2)
        new=self.e.stats()['manual'][0]['token'];self.assertNotEqual(old,new)
        self.wire([0x81,61,0,0xd1,127]);self.e.command(10,0,old);self.e.command(9,0,old,1);self.audio(.2)
        current=self.e.stats()['manual'][0];self.assertTrue(current['held']);self.assertEqual(current['pressure'],0)
    def test_poly_pressure_exact_note_and_shared_channel_conservative(self):
        self.wire([0x92,60,100,61,100,0xd2,127]);self.audio(.2)
        self.assertEqual([m['pressure'] for m in self.e.stats()['manual'][:2]],[0,0])
        self.assertEqual(self.i.expression.ambiguous_pressure,1)
        self.wire([0xa2,61,127]);self.audio(.5)
        self.assertEqual(self.e.stats()['manual'][0]['pressure'],0);self.assertGreater(self.e.stats()['manual'][1]['pressure'],.99)
    def test_sequencer_unaffected_by_manual_release_pressure(self):
        self.m.playing=True;self.e.sync(self.m);self.audio(.1)
        self.wire([0x92,60,100,0xd2,127,0x82,60,0]);self.audio(.5)
        stats=self.e.stats();self.assertTrue(self.m.playing);self.assertGreater(stats['envelopes'][0],0)
        self.assertGreater(stats['peak'],0)
    def test_stop_while_transport_already_stopped_clears_manual(self):
        self.wire([0x92,60,100]);self.audio(.3);self.assertFalse(self.m.playing)
        self.i.event('cc',29,127);pcm=self.audio(.4)
        self.assertEqual(max(abs(v) for v in pcm[-512:]),0)
        self.assertFalse(any(m['held'] for m in self.e.stats()['manual']));self.assertFalse(any(self.i.expression.slots))
    def test_rapid_stop_new_note_does_not_resurrect_old_manual(self):
        self.wire([0x92,60,100,0x93,61,100]);self.audio(.3)
        old=[s['token'] for s in self.i.expression.slots[:2]]
        self.wire([0xb0,29,127]);self.audio(256/44100)
        self.assertFalse(any(s['held'] for s in self.e.stats()['manual']))
        self.assertEqual([s['token'] for s in self.e.stats()['manual'][:2]],[0,0])
        self.wire([0x94,62,100]);self.audio(.1)
        current=self.e.stats()['manual'][0]['token'];self.assertNotIn(current,old)
        self.wire([0x82,60,0,0x83,61,0,0xd2,127,0xd3,127])
        self.e.command(9,0,old[0],1);self.e.command(10,0,old[0]);self.e.command(9,1,old[1],1)
        self.audio(.1)
        self.assertTrue(self.e.stats()['manual'][0]['held'])
        self.assertEqual(self.e.stats()['manual'][0]['pressure'],0)
        self.wire([0x84,62,0]);pcm=self.audio(5)
        self.assertFalse(any(s['held'] for s in self.e.stats()['manual']))
        self.assertTrue(all(s['envelope']==0 for s in self.e.stats()['manual']))
        self.assertLess(max(map(abs,pcm[-512:])),.0001)
    def test_rapid_stop_play_releases_old_manual_independent_of_global_fade(self):
        for track in self.m.state['tracks']:track['pattern']=[0]*8
        self.e.sync(self.m)
        self.wire([0x92,60,100,0x93,61,100]);self.audio(.3)
        old=[s['token'] for s in self.i.expression.slots[:2]]
        # No intervening render: Stop and Play share one native command drain.
        self.wire([0xb0,29,127,85,127]);self.audio(256/44100)
        self.assertTrue(self.m.playing)
        self.assertFalse(any(s['held'] for s in self.e.stats()['manual']))
        self.wire([0xd2,127,0xd3,127,0x82,60,0,0x83,61,0])
        for slot,token in enumerate(old):self.e.command(9,slot,token,1)
        pcm=self.audio(5)
        self.assertTrue(all(s['token']==0 and not s['held'] and s['envelope']==0 for s in self.e.stats()['manual']))
        self.assertLess(max(map(abs,pcm[-512:])),.0001)
    def test_presets_held_and_diagnostic_pitch_slide_no_retune(self):
        self.wire([0x92,60,100]);self.audio(.2);slot=copy.deepcopy(self.i.expression.slots[0]);space=self.m.state['space']
        self.wire([0xe2,127,127,0xb2,74,127]);self.audio(.1)
        self.assertEqual(self.m.state['space'],space);self.assertEqual(self.i.expression.diagnostics,dict(bend={2:16383},slide={2:127}))
        self.m.execute(dict(op='garden',name='Moon Glass',revision=self.m.revision));self.e.sync(self.m)
        self.audio(.2);self.assertEqual(self.i.expression.slots[0],slot)
        self.wire([0x82,60,0]);self.audio(.1);self.assertFalse(self.e.stats()['manual'][0]['held'])
    def test_generation_telemetry_is_coherent_during_render(self):
        import threading
        import time
        failures=[]
        def renderer():
            try:
                out=(C.c_float*512)()
                for _ in range(300):self.e.lib.sw_render(out,256);time.sleep(0)
            except Exception as exc:failures.append(exc)
        worker=threading.Thread(target=renderer);worker.start()
        try:
            for token in range(1,201):
                self.e.manual_on(0,token,token%8,60,.7)
                for _ in range(3):
                    state=self.e.stats()['manual'][0]
                    if state['token']:self.assertEqual(state['track'],state['token']%8)
                time.sleep(0)
        finally:worker.join(3)
        self.assertFalse(worker.is_alive());self.assertFalse(failures)
    def test_released_afterglow_uses_other_empty_slots_before_reuse(self):
        self.wire([0x92,60,100]);self.audio(.2);self.wire([0x82,60,0,0x93,61,100]);self.audio(.1)
        self.assertEqual([s['pad'] for s in self.i.expression.slots[:2]],[60,61])
        self.assertGreater(self.e.stats()['manual'][0]['envelope'],0)
    def test_space_encoder_channel_zero_works_while_held_member_ccs_ignored(self):
        self.wire([0x90,60,100]);self.audio(.1);before=self.m.state['space']
        self.wire([0xb0,74,1]);self.assertGreater(self.m.state['space'],before)
        state=copy.deepcopy(self.m.state)
        self.wire([0xb2,74,127,71,127,78,127]);self.assertEqual(self.m.state,state)
    def test_manual_lantern_renderer_and_stop_idle(self):
        v=VisualState();idle=render(self.m,0,0,telemetry=self.e.stats(),visual=v)
        self.wire([0x92,60,100,0xd2,127]);self.audio(.4)
        frame=render(self.m,0,.4,telemetry=self.e.stats(),visual=v)
        self.assertNotEqual(frame,idle)
        self.i.event('cc',29,127);self.audio(.4)
        for i in range(60):rest=render(self.m,0,1+i*.1,telemetry=self.e.stats(),visual=v)
        self.assertNotEqual(rest,render(self.m,0,10,telemetry=self.e.stats(),visual=v))
        self.assertEqual(v.levels,[0]*8);self.assertTrue(all(not r for r in v.rings))
    def test_touch_notes_excluded_and_led_color_stages(self):
        self.wire([0x90,0,100,35,100,100,100,127,100]);self.audio(.1)
        self.assertFalse(any(self.i.expression.slots))
        self.wire([0x92,60,100]);self.audio(.4)
        self.assertEqual(pad_leds(self.m,self.e.stats(),self.i.expression)[60],15)
        self.wire([0x82,60,0]);stages=[]
        for _ in range(40):
            self.audio(.1);stages.append(pad_leds(self.m,self.e.stats(),self.i.expression)[60])
        self.assertTrue(set(stages)<={94,93,15});self.assertIn(93,stages);self.assertIn(94,stages)
