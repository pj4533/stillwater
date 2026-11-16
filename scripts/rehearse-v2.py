#!/usr/bin/env python3
"""Production V2 layer-building,32s export,68s film and persistence rehearsal.

Memory-only native rendering: no ALSA, MIDI, USB, live sessions or speakers.
"""
from array import array
import ctypes as C
import math
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import wave
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel,read_envelope
from loop_engine import LoopEngine
from loop_app import LoopInstrument
from loop_export import LoopExport
from loop_graphics import render
from bottle import Bottle
from recorder import SessionRecorder
from midi import MidiParser
from model import seeded

def image(frame):
    rgb=bytearray(960*160*3)
    for y in range(160):
        for x in range(960):
            value=struct.unpack_from('<H',frame,(y*1024+x)*2)[0];offset=(y*960+x)*3
            rgb[offset:offset+3]=bytes(((value&31)*255//31,((value>>5)&63)*255//63,((value>>11)&31)*255//31))
    return Image.frombytes('RGB',(960,160),bytes(rgb))

def main():
    out=ROOT/'.build/v2-rehearsal';out.mkdir(exist_ok=True)
    checks=[];timings=[];frames=[]
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix='v2-',dir=ROOT/'.build') as temp:
        home=Path(temp);legacy=home/'sessions/current.json';legacy.parent.mkdir()
        old=seeded();old['master']=.15
        raw=json.dumps(dict(format='stillwater-session',version=3,revision=12,state=old,history=[old]*4)).encode();legacy.write_bytes(raw)
        journal=legacy.with_suffix('.history.json');journal.write_bytes(b'UNTOUCHED LEGACY JOURNAL')
        m=LoopModel(home/'sessions/current-v2.json',legacy=legacy,seed=19)
        e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_reset();e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
        recorder=SessionRecorder(e,home/'recordings');bottle=Bottle(e,home/'recordings');export=LoopExport(e,home/'recordings')
        inst=LoopInstrument(m,e,bottle,recorder,export);parser=MidiParser()
        def wire(data):
            for event in parser.feed(bytes(data)):
                check('command admitted' if not checks else 'wire admitted',inst.wire(event) is not False)
        def cc(number,value=127):wire([0xb0,number,value])
        def render_audio(n):
            pcm=(C.c_float*(n*2))();e.lib.sw_render(pcm,n);return pcm
        def screen():
            stats=e.stats();stats.update(recording=recorder.snapshot(),export=export.snapshot())
            start=time.perf_counter();frame=render(m,stats,inst);timings.append((time.perf_counter()-start)*1000);recorder.displayed(frame);return frame
        render_audio(1);image(screen()).save(out/'empty-first-layer.png');before=m.state;cc(14,100) # relative-28, clamp30 from58
        render_audio(1);check('tempo30 gives32second loop',e.loop_stats()['loop_frames']==32*44100)
        cc(85);check('automatic film starts before first note',recorder.snapshot()['state']=='recording')
        start=recorder.started;expected=out/'expected.s16le';events=set();export_meta=None
        def once(name,when,fn,sample):
            if sample>=round(when*44100) and name not in events:fn();events.add(name)
        role_images={}
        with expected.open('wb') as stream:
            sample=0
            while sample<68*44100:
                for layer in range(8):
                    def begin(layer=layer):
                        if layer:cc(92)
                        wire([0x92,60+layer,100]);cc(71,3)
                    once('layer'+str(layer),layer,begin,sample)
                    once('release'+str(layer),layer+.3,lambda layer=layer:wire([0x82,60+layer,0]),sample)
                once('undo',8,lambda:cc(119),sample)
                once('redo',8.2,lambda:(cc(49),cc(119),cc(49,0)),sample)
                once('save',9,lambda:cc(82),sample)
                once('export',12,lambda:(cc(49),cc(86),cc(49,0)),sample)
                once('mixer',20,lambda:cc(112),sample)
                once('overview',24,lambda:cc(51),sample)
                once('main',28,lambda:cc(110),sample)
                once('film finish',65,lambda:cc(86),sample)
                once('stop',65.2,lambda:cc(29),sample)
                pcm=render_audio(min(4410,68*44100-sample));n=len(pcm)//2
                if sample<65*44100:
                    epoch=e.lib.sw_history_epoch();end=e.lib.sw_history_end();stream.write(memoryview(e.history_copy(epoch,end-n,n)).cast('B'))
                inst.tick();frame=screen()
                if sample%44100==4410:
                    role=m.state.layers[m.selected].role
                    if role not in role_images:role_images[role]=image(frame);role_images[role].save(out/(role+'-main.png'))
                if 20*44100<=sample<21*44100:image(frame).save(out/'mixer.png')
                if 24*44100<=sample<25*44100:image(frame).save(out/'overview.png')
                if sample<8*44100:frames.append(image(frame))
                if sample==4410:image(frame).save(out/'recording-overdub.png')
                if sample==8*44100:cc(92);image(screen()).save(out/'eight-layer-limit.png')
                sample+=n;time.sleep(.003)
        cc(81);image(screen()).save(out/'help.png');cc(81)
        image(screen()).save(out/'eight-layers-stopped.png')
        check('all8rolesbuiltwithoutreplacement',len(m.state.layers)==8 and len(set(l.role for l in m.state.layers))==8)
        check('oneplayednoteineachlayer',all(len(l.events)==1 for l in m.state.layers))
        check('legacyexactbytespreserved',legacy.read_bytes()==raw and journal.read_bytes()==b'UNTOUCHED LEGACY JOURNAL')
        check('stop exact quiet',all(x==0 for x in render_audio(2048)))
        deadline=time.monotonic()+30
        while recorder.snapshot()['busy'] or export.snapshot()['busy']:
            if time.monotonic()>deadline:raise AssertionError((recorder.snapshot(),export.snapshot()))
            time.sleep(.01)
        print('capture outcomes',recorder.snapshot(),export.snapshot(),flush=True)
        check('real film encoded',recorder.snapshot()['state']=='ready')
        check('exactloop saved',export.snapshot()['state']=='saved')
        movie=home/'recordings'/recorder.status['filename'];shutil.copyfile(movie,out/'performance.mp4')
        info=json.loads(subprocess.check_output(['/usr/bin/ffprobe','-v','error','-show_streams','-of','json',str(movie)]));video=next(s for s in info['streams'] if s['codec_type']=='video')
        check('actualH26410fps960x160',video['codec_name']=='h264' and video['width']==960 and video['height']==160 and video['r_frame_rate']=='10/1')
        audio_stream=next(s for s in info['streams'] if s['codec_type']=='audio')
        check('actualAACstereo44100',audio_stream['codec_name']=='aac' and audio_stream['sample_rate']=='44100' and audio_stream['channels']==2)
        subprocess.run(['/usr/bin/ffmpeg','-nostdin','-v','error','-y','-i',str(movie),'-map','0:a:0','-f','s16le','-ac','2','-ar','44100',str(out/'decoded.s16le')],check=True)
        reference=array('h');reference.frombytes(expected.read_bytes());decoded=array('h');decoded.frombytes((out/'decoded.s16le').read_bytes())
        correlations=[]
        for when in (2,32,64):
            indices=range(when*44100,when*44100+11025,32)
            def score(lag):
                pairs=[(reference[j*2],decoded[(j+lag)*2]) for j in indices]
                numerator=sum(a*b for a,b in pairs);denominator=math.sqrt(sum(a*a for a,b in pairs)*sum(b*b for a,b in pairs))
                return numerator/denominator if denominator else 0
            lag=max(range(-64,65),key=score);correlations.append(dict(seconds=when,lag_samples=lag,correlation=score(lag)))
        check('decodedAAC remains samplealigned throughout65s',all(abs(r['lag_samples'])<=2 and r['correlation']>.95 for r in correlations))
        job=home/'recordings/jobs'/recorder.status['job'];meta=json.loads((job/'metadata.json').read_text())
        check('film65seconds crosses45second historywrap',meta['audio_frames']==65*44100)
        check('filmPCM sampleexact',hashlib.sha256(expected.read_bytes()).hexdigest()==hashlib.sha256((job/'audio.s16le').read_bytes()).hexdigest())
        wavpath=home/'recordings'/export.status['filename'];side=json.loads(wavpath.with_suffix('.json').read_text());shutil.copyfile(wavpath,out/'loop.wav');shutil.copyfile(wavpath.with_suffix('.json'),out/'loop.json')
        with wave.open(str(wavpath),'rb') as wav:
            check('full32second loop streamed',wav.getnframes()==32*44100);pcm=wav.readframes(wav.getnframes())
        rawpcm=expected.read_bytes();reference=rawpcm[(side['start']-start)*4:(side['end']-start)*4]
        check('export endpoints and everyPCM sample exact',pcm==reference and hashlib.sha256(pcm).hexdigest()==side['pcm_sha256'])
        check('zero xruns',e.stats()['xruns']==0)
        # Actual async Save / library / controlled load / archive-New / Undo.
        saved=m.state;cc(49);cc(51);cc(49,0)
        deadline=time.monotonic()+3
        while inst.library is None and time.monotonic()<deadline:inst.tick();time.sleep(.005)
        check('saved song listed',bool(inst.library));cc(79,2);render_audio(256)
        cc(102)
        deadline=time.monotonic()+3
        while m.state!=saved and time.monotonic()<deadline:render_audio(256);inst.tick();time.sleep(.005)
        check('libraryload restores saved8layer song',m.state==saved)
        cc(49);cc(92);cc(49,0);render_audio(256)
        deadline=time.monotonic()+3
        while len(m.state.layers)!=1 and time.monotonic()<deadline:inst.tick();render_audio(256);time.sleep(.005)
        check('shiftnewarchivesblank1layer',len(m.state.layers)==1 and not m.state.layers[0].events)
        cc(119);render_audio(256);check('undoNew restores8layers',len(m.state.layers)==8)
        m.checkpoint(True);check('async current durable',m.writer.flush(m.revision,3))
        check('saved envelope history validates',read_envelope(m.path)['state']==m.state)
        check('legacy remains exact afterlibrary',legacy.read_bytes()==raw)
        inst.close()
        # The GIF is made from production frames with real native performance.
        frames[0].save(out/'v2-performance.gif',save_all=True,append_images=frames[1:],duration=100,loop=0)
        contact=Image.new('RGB',(960,160*8))
        for index,(role,im) in enumerate(role_images.items()):contact.paste(im,(0,index*160))
        contact.save(out/'role-contact.png')
        report=dict(checks=list(dict.fromkeys(checks)),count=len(set(checks)),render_ms_max=max(timings),render_ms_mean=sum(timings)/len(timings),frames=len(timings),film_frames=meta['video_frames'],film_samples=meta['audio_frames'],export=side,aac_correlations=correlations,roles=list(role_images),device=False)
        (out/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
