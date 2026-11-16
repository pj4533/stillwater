#!/usr/bin/env python3
"""Synthetic wire bytes through production parser/dispatcher/DSP/renderer/LEDs."""
import copy
import ctypes as C
import json
import math
from pathlib import Path
import runpy
import struct
import subprocess
import sys
import tempfile
import time
import wave
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from app import Engine, Instrument
from model import Model
from midi import MidiParser, EventTap
from expression import pad_leds
from graphics import render, VisualState
png=runpy.run_path(str(ROOT/'scripts/rehearse-local.py'))['png']


def main():
    subprocess.run(['sh',str(ROOT/'scripts/build.sh')],check=True)
    out=ROOT/'.build/expression-rehearsal';out.mkdir(parents=True,exist_ok=True)
    checks=[];trace=[];ledtrace=[];clock=0.;previous=0.;render_times=[];native_times=[];frames={}
    def check(name,ok):
        if not ok:raise AssertionError(name)
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix='stillwater-expression-') as temp:
        m=Model(Path(temp)/'current.json');e=Engine(ROOT/'.build/engine.so');e.lib.sw_reset()
        e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
        inst=Instrument(m,e);e.sync(m);v=VisualState();tap=EventTap(30,512,lambda:clock);parser=MidiParser(tap)
        def wire(data):
            events=parser.feed(bytes(data))
            for event in events:inst.wire(event)
            trace.append(dict(seconds=clock,wire=list(data),parsed=events,state=m.snapshot(),audio=e.stats()))
        def frame(name):
            stats=e.stats();start=time.perf_counter();f=render(m,stats['position'],clock,telemetry=stats,visual=v)
            render_times.append((time.perf_counter()-start)*1000);frames[name]=f;png(out/(name+'.png'),f)
            ledtrace.append(dict(seconds=clock,name=name,palette=pad_leds(m,stats,inst.expression),voices=inst.expression.snapshot(stats)))
            return f
        with wave.open(str(out/'expression.wav'),'wb') as wav:
            wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(44100)
            def audio(seconds):
                nonlocal clock,previous
                remaining=round(seconds*44100);pcm=[]
                while remaining:
                    n=min(256,remaining);data=(C.c_float*(n*2))();start=time.perf_counter();e.lib.sw_render(data,n);native_times.append(time.perf_counter()-start)
                    pcm.extend(data);remaining-=n;clock+=n/44100
                check('finite bounded PCM',all(math.isfinite(x) and abs(x)<=.250001 for x in pcm))
                left=pcm[::2];delta=max(abs(a-b) for a,b in zip([previous]+left,left));previous=left[-1]
                check('soft adjacent samples',delta<.02)
                wav.writeframes(struct.pack('<%dh'%len(pcm),*(round(x*32767) for x in pcm)))
                return pcm
            frame('idle');check('silent initial PCM',max(map(abs,audio(.1)))==0)
            wire([0xb0,50,127]);wire([0x92,60]);wire([0xf8,100]);audio(.4);low=frame('held-low-pressure')
            lowenv=e.stats()['manual'][0]['envelope'];check('held lantern palette',pad_leds(m,e.stats(),inst.expression)[60]==15)
            wire([0xd2,127]);audio(.5);high=frame('held-pressure-bloom')
            check('pressure native response',e.stats()['manual'][0]['pressure']>.99 and e.stats()['manual'][0]['envelope']>lowenv)
            check('pressure changes actual visual',high!=low)
            before=copy.deepcopy(m.state);wire([0xb2,74,127,0xe2,0,64]);check('slide bend diagnostic only',m.state==before)
            wire([0xb0,74,1]);check('Space encoder remains live',m.state['space']>before['space'])
            m.execute(dict(op='garden',name='Moon Glass',revision=m.revision));e.sync(m);audio(.1)
            check('preset retains held identity',inst.expression.slots[0]['channel']==2 and e.stats()['manual'][0]['held'])
            wire([0x82,60,32]);stages=[]
            for index in range(35):
                audio(.1);stages.append(pad_leds(m,e.stats(),inst.expression)[60]);frame('release-%02d'%index)
            check('release fades native manual',e.stats()['manual'][0]['envelope']==0)
            check('explicit teal afterglow stages',93 in stages and 94 in stages and set(stages)<={15,93,94})
            # Eight channels, exact poly expression and conservative ambiguous channel pressure.
            for channel in range(1,9):wire([0x90+channel,60+channel,90])
            audio(.3);frame('eight-lanterns');check('eight held manual voices',sum(x['held'] for x in e.stats()['manual'])==8)
            victim=min(range(8),key=lambda i:inst.expression.slots[i]['token']);stolen=inst.expression.slots[victim]['token']
            wire([0x99,75,100]);audio(.1)
            wire([0x81,61,0,0xd1,127]);e.command(10,victim,stolen);e.command(9,victim,stolen,1);audio(.1)
            check('stolen generation isolated',e.stats()['manual'][victim]['held'] and e.stats()['manual'][victim]['pressure']==0)
            frame('new-lantern-old-released');wire([0xb0,85,127]);audio(.3)
            check('sequencer still advancing',m.playing and sum(e.stats()['onsets'])>8)
            wire([0xb0,29,127]);pcm=audio(.5);frame('stopped')
            check('Stop exact zero',max(map(abs,pcm[-512:]))==0)
            check('Stop clears held',not any(x['held'] for x in e.stats()['manual']))
            # Stop retirement must survive new notes/Play reopening global gain.
            wire([0x92,60,100,0x93,61,100]);audio(.3)
            wire([0xb0,29,127]);audio(256/44100)
            check('Stop immediately retires held identities',not any(x['held'] for x in e.stats()['manual']))
            wire([0x94,62,100]);audio(.1)
            wire([0x82,60,0,0x83,61,0,0xd2,127,0xd3,127]);audio(.1)
            check('new generation survives retired releases',e.stats()['manual'][0]['held'])
            wire([0x84,62,0]);pcm=audio(5)
            check('Stop newnote no resurrection',all(not x['held'] and x['envelope']==0 for x in e.stats()['manual']))
            check('retired voices decay after newnote',max(map(abs,pcm[-512:]))<.0001)
            before=copy.deepcopy(m.state);quiet=copy.deepcopy(before)
            for track in quiet['tracks']:track['pattern']=[0]*8
            m.commit(quiet,'Quiet loop for Stop restart rehearsal');e.sync(m)
            wire([0x92,60,100,0x93,61,100]);audio(.3)
            wire([0xb0,29,127,85,127]);audio(256/44100)
            check('Stop Play immediately retires held identities',m.playing and not any(x['held'] for x in e.stats()['manual']))
            wire([0xd2,127,0xd3,127,0x82,60,0,0x83,61,0]);pcm=audio(5)
            check('Stop Play no resurrection',all(x['token']==0 and not x['held'] and x['envelope']==0 for x in e.stats()['manual']))
            check('retired voices decay after Play',max(map(abs,pcm[-512:]))<.0001)
            wire([0xb0,29,127]);m.execute(dict(op='undo',revision=m.revision));e.sync(m);audio(.5)
            check('replay restores scene',m.state==before)
            for index in range(60):
                clock+=.1;render(m,e.stats()['position'],clock,telemetry=e.stats(),visual=v)
            rest=frame('settled')
            check('silent visual has no native voice activity',not any(e.stats()['envelopes']) and all(x['envelope']==0 for x in e.stats()['manual']))
            check('same-moment silent visual is deterministic',frame('settled-same-time')==rest)
            clock+=1;frame('settled-later')  # Reviewed decorative idle breathing is intentional.
        # Identical elapsed/sample sequence A/B: pressure modifies actual PCM, not just telemetry.
        def pressure_variant(value):
            e.lib.sw_reset();e.previous=None;e.playing=None;fresh=Instrument(m,e);e.sync(m)
            for event in MidiParser().feed(bytes([0x92,60,100])):fresh.wire(event)
            data=(C.c_float*(17640*2))();e.lib.sw_render(data,17640)
            for event in MidiParser().feed(bytes([0xd2,value])):fresh.wire(event)
            data=(C.c_float*(22050*2))();e.lib.sw_render(data,22050)
            return list(data)
        a=pressure_variant(0);b=pressure_variant(127)
        check('pressure changes real PCM',sum((x-y)**2 for x,y in zip(a,b))>1e-6)
        check('pressure gain remains gentle',math.sqrt(sum(x*x for x in b)/sum(x*x for x in a))<1.3)
        check('local render fits 100ms budget',max(render_times)<100)
        summary=dict(passed=len(checks),failed=0,checks=checks,render_ms=dict(max=max(render_times),mean=sum(render_times)/len(render_times)),
                     native_render_seconds=sum(native_times),audio_seconds=(clock-7),physical_input=False,device_deployment=False,
                     pressure_pcm_difference_rms=math.sqrt(sum((x-y)**2 for x,y in zip(a,b))/len(a)))
        (out/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
        (out/'wire-state-trace.json').write_text(json.dumps(trace,indent=2)+'\n')
        (out/'pad-led-trace.json').write_text(json.dumps(ledtrace,indent=2)+'\n')
        (out/'midi-tap.json').write_text(json.dumps(tap.snapshot(),indent=2)+'\n')
        names=['idle','held-low-pressure','held-pressure-bloom','release-04','release-12','eight-lanterns','new-lantern-old-released','stopped','settled']
        png(out/'storyboard.png',b''.join(frames[name] for name in names),height=160*len(names))
        print(json.dumps(summary,indent=2));print('Artifacts:',out)

if __name__=='__main__':main()
