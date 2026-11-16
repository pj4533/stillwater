#!/usr/bin/env python3
"""Hardware-free performance through the production model, dispatcher, DSP and UI."""
import copy
import ctypes as C
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import wave
import zlib
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from app import Engine, Instrument
from graphics import render, VisualState
from model import Model, GARDENS, grown


def png(path,frame,width=960,height=160,stride=1024):
    # Export the actual production BGR565 framebuffer; no alternate UI renderer.
    rows=bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            i=(y*stride+x)*2;v=frame[i]|frame[i+1]<<8
            rows.extend(((v&31)*255//31,((v>>5)&63)*255//63,(v>>11)*255//31))
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))


def main():
    subprocess.run(['sh',str(ROOT/'scripts/build.sh')],check=True)
    out=ROOT/'.build/rehearsal';out.mkdir(parents=True,exist_ok=True)
    checks=[];trace=[];segments={};clock=0;previous=0
    def check(name,condition):
        if not condition:raise AssertionError(name)
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix='stillwater-rehearsal-') as temp:
        path=Path(temp)/'current.json';model=Model(path)
        engine=Engine(ROOT/'.build/engine.so');engine.lib.sw_reset()
        engine.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
        instrument=Instrument(model,engine);engine.sync(model);visual=VisualState();pictures={};render_times=[]
        def event(kind,number,value):
            req=dict(op='event',kind=kind,number=number,value=value)
            model.execute(req)
            with patch('app.time.monotonic',return_value=clock):
                instrument.event(kind,number,value)
            trace.append(dict(action=req,state=model.snapshot(),audio=engine.stats()))
        def agent(req):
            model.execute(req);engine.sync(model)
            trace.append(dict(action=req,state=model.snapshot(),audio=engine.stats()))
        def picture(name,seconds=None,position=None):
            started=time.perf_counter()
            frame=render(model,engine.stats()['position'] if position is None else position,
                         clock if seconds is None else seconds,engine.stats()['peak'],instrument.hit,telemetry=engine.stats(),visual=visual)
            render_times.append((time.perf_counter()-started)*1000);pictures[name]=frame
            png(out/(name+'.png'),frame);return frame
        with wave.open(str(out/'performance.wav'),'wb') as wav:
            wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(44100)
            def audio(name,seconds):
                nonlocal clock,previous
                remain=round(seconds*44100);peak=energy=delta=0;count=0;last=0
                while remain:
                    n=min(1024,remain);data=(C.c_float*(n*2))();engine.lib.sw_render(data,n)
                    if not all(math.isfinite(v) for v in data):raise AssertionError('finite PCM')
                    peak=max(peak,max(abs(v) for v in data));energy+=sum(v*v for v in data)
                    for v in data[::2]:delta=max(delta,abs(v-previous));previous=v
                    last=max(abs(v) for v in data[-min(n,256)*2:]);count+=n*2
                    wav.writeframes(struct.pack('<%dh'%len(data),*(round(v*32767) for v in data)))
                    remain-=n;clock+=n/44100
                segments[name]=dict(peak=peak,rms=math.sqrt(energy/count),max_left_delta=delta,final_peak=last)
                check(name+' bounded PCM',peak<=.250001)
                return segments[name]
            picture('idle');check('initial silent',audio('idle',.2)['peak']==0)
            event('cc',85,127);check('Play dispatcher',model.playing)
            start=engine.stats()['position'];playing=audio('playback',3)
            check('sequencer nonzero PCM',playing['rms']>.0001)
            check('native sequencer advances',engine.stats()['position']!=start)
            frame=picture('playback');later=picture('animation',clock+.3)
            check('animation changes',frame!=later)
            # Hold visual time fixed to prove state/step graphics really respond.
            check('step graphics respond',picture('next-step',position=(engine.stats()['position']+1)%8)!=frame)
            old=copy.deepcopy(model.state);event('note',36,100)
            check('pad edits real pattern',model.state['tracks'][0]['pattern'][0]!=old['tracks'][0]['pattern'][0])
            old_level=model.state['tracks'][0]['level'];event('cc',71,1)
            check('encoder level',abs(model.state['tracks'][0]['level']-old_level-.02)<1e-9)
            audio('pad-and-encoder',1);picture('pad-and-encoder')
            event('cc',29,127)
            check('quiet before isolated pad',audio('pre-pad-stop',.3)['final_peak']==0)
            event('cc',50,127);event('note',60,100)
            check('performance mode dispatcher',model.mode=='notes')
            check('performance pad sounds',audio('performance-pad',1)['rms']>.0001)
            check('real isolated voice telemetry',engine.stats()['envelopes'][0]>0 and all(v==0 for v in engine.stats()['envelopes'][1:]))
            event('cc',85,127)
            before=copy.deepcopy(model.state);before_frame=picture('before-agent')
            pattern=[0]*8;pattern[3]=65
            agent(dict(op='propose_pattern',id='local-ripple',track=4,pattern=pattern,revision=model.revision))
            check('proposal leaves music unchanged',model.state==before)
            agent(dict(op='apply_pattern',id='local-ripple',revision=model.revision))
            check('agent applies pattern',model.state['tracks'][4]['pattern']==pattern)
            check('agent graphics respond',picture('agent-edited')!=before_frame)
            audio('agent-pattern',1)
            agent(dict(op='undo',revision=model.revision));check('undo restores scene',model.state==before)
            # Optional agent preview stays silent; hardware Grow is one expressive press.
            prior=copy.deepcopy(model.state)
            agent(dict(op='propose_grow',id='garden-preview',seed=123,revision=model.revision))
            check('Grow preview silent',model.state==prior)
            check('Grow deterministic',model.preview['patterns']==[t['pattern'] for t in grown(prior,123)['tracks']])
            picture('grow-preview')
            agent(dict(op='apply_grow',id='garden-preview',revision=model.revision))
            check('Grow applies exact preview',model.state==grown(prior,123))
            check('Grow retains transport',model.playing)
            audio('grow',.5);picture('grow')
            agent(dict(op='undo',revision=model.revision));check('Grow undo',model.state==prior)
            event('cc',92,127);check('one press live Grow',model.state!=prior and model.playing and model.preview is None)
            event('cc',119,127);check('live Grow Undo',model.state==prior)
            for name in GARDENS:
                agent(dict(op='garden',name=name,revision=model.revision));check(name+' transport',model.playing)
                segment=audio(name,.6);check(name+' smooth',segment['max_left_delta']<.02)
                picture(name.lower().replace(' ','-'))
                agent(dict(op='undo',revision=model.revision));check(name+' undo',model.state==prior)
            agent(dict(op='save'));restored=Model(path)
            check('save reload state revision undo',restored.state==model.state and restored.revision==model.revision and restored.history==model.history)
            event('cc',29,127);check('Stop dispatcher',not model.playing)
            stopped=audio('stop-fade',.5);check('stop fades to silence',stopped['final_peak']<1e-7)
            check('smooth stop',stopped['max_left_delta']<.02)
            check('remains silent',audio('silence',.2)['peak']==0)
            for i in range(50):render(model,engine.stats()['position'],clock+i*.1,telemetry=engine.stats(),visual=visual)
            clock+=5
            resting=picture('stopped');check('silent creatures breathe without audio',resting!=picture('resting',clock+1) and engine.stats()['peak']==0)
            check('native telemetry onsets',sum(engine.stats()['onsets'])>0)
        trace.append(dict(action='reload',state=restored.snapshot()))
        # Nine actual production frames form a reviewable, dependency-free storyboard.
        names=['idle','playback','animation','grow-preview','grow','reed-choir','lantern-pond','moon-glass','stopped']
        board=bytearray(2880*480*2)
        for index,name in enumerate(names):
            row,col=divmod(index,3);frame=pictures[name]
            for y in range(160):
                offset=((row*160+y)*2880+col*960)*2
                board[offset:offset+1920]=frame[y*2048:y*2048+1920]
        png(out/'storyboard.png',board,2880,480,2880)
        result=dict(render_ms=dict(max=max(render_times),mean=sum(render_times)/len(render_times)),passed=len(checks),failed=0,checks=checks,seconds=engine.stats()['frames']/44100,visual_seconds=clock,segments=segments,
                    native_library=str(ROOT/'.build/engine.so'),physical_hardware=False)
        (out/'state-trace.json').write_text(json.dumps(trace,indent=2))
        (out/'result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2));print('Artifacts: '+str(out))

if __name__=='__main__':main()
