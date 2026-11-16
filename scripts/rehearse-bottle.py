#!/usr/bin/env python3
"""Actual retrospective capture, production controls/rendering, plus native A/B cost."""
import copy
import ctypes as C
import json
from pathlib import Path
import runpy
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import wave
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from app import Engine, Instrument
from bottle import Bottle
from graphics import render, VisualState
from midi import MidiParser
from model import Model
png=runpy.run_path(str(ROOT/'scripts/rehearse-local.py'))['png']


def main():
    subprocess.run(['sh',str(ROOT/'scripts/build.sh')],check=True)
    out=ROOT/'.build/bottle-rehearsal';out.mkdir(parents=True,exist_ok=True);checks=[];frames={};times=[]
    def check(name,ok):
        if not ok:raise AssertionError(name)
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix='stillwater-bottle-') as temp:
        m=Model(Path(temp)/'current.json');e=Engine(ROOT/'.build/engine.so');e.lib.sw_reset()
        e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
        b=Bottle(e,Path(temp)/'recordings');inst=Instrument(m,e,b);e.sync(m);v=VisualState();parser=MidiParser()
        def wire(data):
            for event in parser.feed(bytes(data)):inst.wire(event)
        def audio(seconds):
            data=(C.c_float*(round(seconds*44100)*2))();e.lib.sw_render(data,len(data)//2);return data
        def frame(name):
            stats=e.stats();stats['capture']=b.snapshot();start=time.perf_counter()
            f=render(m,stats['position'],time.monotonic(),telemetry=stats,visual=v);times.append((time.perf_counter()-start)*1000)
            png(out/(name+'.png'),f);frames[name]=f;return f
        wire([0xb0,50,127,0x92,60,100]);audio(2)
        wire([0xd2,127]);audio(.5);wire([0x82,60,0]);audio(1)
        wire([0xb0,29,127]);audio(.5)
        old=(copy.deepcopy(m.state),copy.deepcopy(m.history),m.revision,m.playing)
        idle=frame('available');wire([0xb0,49,127,82,127,49,0]);filling=frame('filling')
        b.worker.join(3);check('worker finishes',not b.worker.is_alive());status=b.snapshot()
        check('capture corked',status['state']=='corked');saved=frame('corked')
        check('capture motion changes framebuffer',idle!=filling and filling!=saved)
        check('music state undo transport unchanged',old==(m.state,m.history,m.revision,m.playing))
        check('startup duration honest',status['seconds']==4)
        with wave.open(str(b.directory/status['filename']),'rb') as wav:
            check('stereo PCM16 44100',wav.getparams()[:3]==(2,2,44100));raw=wav.readframes(wav.getnframes())
        samples=struct.unpack('<%dh'%(len(raw)//2),raw)
        check('earlier music rescued',max(map(abs,samples[:44100*2]))>0)
        check('recent stopped output zero',max(map(abs,samples[-512:]))==0)
        check('captured samples bounded',max(map(abs,samples))<=8192)
        # Private/generated output stays under ignored .build, never evidence/git.
        (out/'bottle-performance.wav').write_bytes((b.directory/status['filename']).read_bytes())
        frame('settled');check('render fits frame budget',max(times)<100)
        png(out/'storyboard.png',b''.join(frames[name] for name in ['available','filling','corked','settled']),height=640)
        b.close()
    # Compile same production DSP with history writes disabled only for A/B measurement.
    subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DSTILLWATER_HISTORY=0','-shared','-fPIC',str(ROOT/'src/engine.c'),'-o',str(ROOT/'.build/engine-nohistory.so'),'-lm','-lpthread','-ldl'],check=True)
    def benchmark(path):
        eng=Engine(path);eng.lib.sw_reset();eng.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
        for i in range(8):eng.manual_on(i,i+1,i,48+i,.6)
        block=(C.c_float*512)();measure=[]
        for repeat in range(5):
            started=time.perf_counter()
            for _ in range(173):eng.lib.sw_render(block,256)
            measure.append(time.perf_counter()-started)
        return dict(median_seconds=statistics.median(measure),samples=measure,audio_seconds=173*256/44100)
    with_history=benchmark(ROOT/'.build/engine.so');without_history=benchmark(ROOT/'.build/engine-nohistory.so')
    check('native render comfortably realtime locally',with_history['median_seconds']<with_history['audio_seconds']*.5)
    result=dict(passed=len(checks),failed=0,checks=checks,render_max_ms=max(times),capture_seconds=4,history_bytes=45*44100*16,
                benchmark=dict(with_history=with_history,without_history=without_history,overhead_seconds_per_audio_second=(with_history['median_seconds']-without_history['median_seconds'])/with_history['audio_seconds']),
                physical_input=False,device_deployment=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));print('Artifacts:',out)

if __name__=='__main__':main()
