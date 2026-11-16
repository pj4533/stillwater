#!/usr/bin/env python3
"""Production 52s performance, real H264/AAC encode/decode, clock/crop checks."""
from array import array
import copy
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from app import Engine, Instrument
from bottle import Bottle
from graphics import render,VisualState
from midi import MidiParser
from model import Model
from recorder import SessionRecorder,SR,FRAME_BYTES,TICK
png=runpy.run_path(str(ROOT/'scripts/rehearse-local.py'))['png']


def region(frame):
    # Native BGR565le to RGB, only the stable voice-label landmark region.
    result=[]
    for y in range(6,15):
        for x in range(390,635):
            val=struct.unpack_from('<H',frame,(y*1024+x)*2)[0]
            result.extend(((val&31)*255/31,((val>>5)&63)*255/63,((val>>11)&31)*255/31))
    return result


def main():
    subprocess.run(['sh',str(ROOT/'scripts/build.sh')],check=True)
    out=ROOT/'.build/recording-rehearsal';out.mkdir(parents=True,exist_ok=True)
    checks=[];render_times=[];trace=[];references={};transitions=[]
    def check(name,ok):
        if not ok:raise AssertionError(name)
        checks.append(name)
    with tempfile.TemporaryDirectory(prefix='film-',dir=ROOT/'.build') as temp:
        home=Path(temp);m=Model(home/'current.json');e=Engine(ROOT/'.build/engine.so');e.lib.sw_reset();e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
        r=SessionRecorder(e,home/'recordings');b=Bottle(e,home/'recordings');i=Instrument(m,e,b,r);e.sync(m);parser=MidiParser();visual=VisualState()
        def wire(values):
            for event in parser.feed(bytes(values)):i.wire(event)
        def screen():
            stats=e.stats();stats.update(recording=r.snapshot(),capture=b.snapshot(),help=i.help)
            start=time.perf_counter();frame=render(m,stats['position'],time.monotonic(),telemetry=stats,visual=visual);render_times.append((time.perf_counter()-start)*1000)
            # Invisible right64 padding is deliberately magenta: crop must remove it.
            padded=bytearray(frame)
            for y in range(160):padded[(y*1024+960)*2:(y+1)*1024*2]=b'\x1f\xf8'*64
            return bytes(padded)
        wire([0xb0,50,127,102,127]);first=screen();r.displayed(first);references[0]=region(first)
        old=(copy.deepcopy(m.state),m.revision,copy.deepcopy(m.history),m.playing)
        wire([0xb0,86,127]);s0=r.started
        expected=out/'expected.s16le';samples=0;phase=0;actions=set();cadence=[4530,4670,4410,4900,4200,4750,4380]
        def action(name,when,values):
            if samples>=round(when*SR) and name not in actions:wire(values);actions.add(name);trace.append(dict(action=name,sample=samples))
        with expected.open('wb') as raw:
            while samples<52*SR:
                action('held lantern',.5,[0x92,60,105]);action('pressure',1.5,[0xd2,115]);action('release',3,[0x82,60,0]);action('play',5,[0xb0,85,127])
                action('grow',15,[0xb0,92,127]);action('undo',18,[0xb0,119,127]);action('bottle',22,[0xb0,49,127,82,127,49,0])
                action('silence',24,[0xb0,29,127]);action('middle lantern',25,[0xb0,106,127,0x93,60,100]);action('middle rest',28,[0xb0,29,127]);action('play again',30,[0xb0,85,127])
                action('last lantern',49,[0xb0,109,127,0x94,64,110]);action('final rest',51,[0xb0,29,127])
                n=min(cadence[len(trace+render_times)%len(cadence)],52*SR-samples)
                block=(C.c_float*(n*2))();e.lib.sw_render(block,n);samples+=n
                epoch,end=r.clock();raw.write(memoryview(e.history_copy(epoch,end-n,n)).cast('B'))
                f=screen();r.displayed(f)
                newphase=0 if m.selected==0 else 1 if m.selected==4 else 2
                if newphase!=phase:
                    phase=newphase;transitions.append((samples/SR,phase));references[phase]=region(f);png(out/('phase-%d.png'%phase),f)
                while r.q.qsize()>2 and r.worker.is_alive():time.sleep(.001)
                if r.status['state']=='error':raise AssertionError(r.status)
                time.sleep(.001)
        # Help remains live; toggle a macro while its production overlay is shown.
        wire([0xb0,81,127]);helpframe=screen();png(out/'help.png',helpframe);wire([0xb0,81,127])
        wire([0xb0,86,127]);r.worker.join(90);check('capture and real encode finish',not r.worker.is_alive() and r.status['state']=='ready')
        job=r.status['job'];path=r.directory/'jobs'/job;metadata=json.loads((path/'metadata.json').read_text())
        check('52second capture crosses45second history wrap',metadata['audio_frames']==52*SR)
        check('exact contiguous production PCM window',hashlib.sha256(expected.read_bytes()).digest()==hashlib.sha256((path/'audio.s16le').read_bytes()).digest())
        check('sampleclock video count',metadata['video_frames']==520)
        check('video normalization repeats rather than compresses',metadata['display_frames']<520)
        check('zero native xruns',e.stats()['xruns']==0)
        check('help framebuffer correct padded size',len(helpframe)==FRAME_BYTES)
        source=r.directory/r.status['filename'];movie=out/'performance.mp4';shutil.copyfile(source,movie)
        info=json.loads(subprocess.check_output(['/usr/bin/ffprobe','-v','error','-show_streams','-show_format','-of','json',str(movie)]))
        video=next(s for s in info['streams'] if s['codec_type']=='video');audio=next(s for s in info['streams'] if s['codec_type']=='audio')
        check('real H264 AAC stereo960x160 SAR1 10fps',video['codec_name']=='h264' and video['width']==960 and video['height']==160 and video['sample_aspect_ratio']=='1:1' and video['r_frame_rate']=='10/1' and audio['codec_name']=='aac' and audio['channels']==2)
        subprocess.run(['/usr/bin/ffmpeg','-nostdin','-v','error','-y','-i',str(movie),'-map','0:a:0','-f','s16le','-ac','2','-ar','44100',str(out/'decoded.s16le')],check=True)
        subprocess.run(['/usr/bin/ffmpeg','-nostdin','-v','error','-y','-i',str(movie),'-map','0:v:0','-vf','format=rgb24,crop=245:9:390:6','-pix_fmt','rgb24','-f','rawvideo',str(out/'labels.rgb')],check=True)
        # AAC edit lists/priming are consumed by decoder; correlate independently
        # near start/middle/end against exact pre-encoder PCM, without retiming.
        raw=array('h');raw.frombytes(expected.read_bytes());decoded=array('h');decoded.frombytes((out/'decoded.s16le').read_bytes());lags=[];correlations=[]
        for when in (2,26,50):
            start=when*SR;indices=range(start,start+SR//2,32)
            def score(lag):
                pairs=[(raw[j*2],decoded[(j+lag)*2]) for j in indices if 0<=j+lag<len(decoded)//2]
                dot=sum(x*y for x,y in pairs);norm=math.sqrt(sum(x*x for x,y in pairs)*sum(y*y for x,y in pairs))
                return dot/norm if norm else -1
            coarse=max(range(-2048,2049,16),key=score);best=max(range(coarse-15,coarse+16),key=score)
            lags.append(best/SR);correlations.append(score(best))
        check('AAC matches native start middle end',min(correlations)>.98)
        check('AAC alignment and drift below codec tolerance',max(map(abs,lags))<.025 and max(lags)-min(lags)<.01)
        check('recent Stop PCM exactly silent',set(expected.read_bytes()[-4096:])=={0})
        check('decoded AAC recent silence bounded',max(map(abs,decoded[-2048:]))<=3)
        labelsize=245*9*3;labels=(out/'labels.rgb').read_bytes();observed=[];last=0
        for tick in range(len(labels)//labelsize):
            actual=labels[tick*labelsize:(tick+1)*labelsize]
            distances={key:sum((x-y)**2 for x,y in zip(actual,ref)) for key,ref in references.items()}
            selected=min(distances,key=distances.get)
            if selected!=last:observed.append((tick/10,selected));last=selected
        offsets=[next(t for t,p in observed if p==phase)-stamp for stamp,phase in transitions]
        check('decoded visual landmarks quantized under100ms',len(offsets)==2 and all(-.001<=x<.101 for x in offsets))
        check('visual sync drift under100ms',max(offsets)-min(offsets)<.1)
        # Right padding never appears: native visible width/stream dimensions
        # checked above; decode rightmost pixels and reject magenta sentinel.
        pixels=subprocess.check_output(['/usr/bin/ffmpeg','-nostdin','-v','error','-i',str(movie),'-frames:v','1','-vf','crop=8:8:952:0','-pix_fmt','rgb24','-f','rawvideo','-'])
        check('padding magenta cropped away',not any(pixels[k]>200 and pixels[k+1]<40 and pixels[k+2]>200 for k in range(0,len(pixels),3)))
        check('BT709 limited-range color tags',video.get('color_range')=='tv' and all(video.get(key)=='bt709' for key in ('color_space','color_transfer','color_primaries')))
        pixel=subprocess.check_output(['/usr/bin/ffmpeg','-nostdin','-v','error','-i',str(movie),'-frames:v','1','-vf','format=rgb24,crop=1:1:500:45','-f','rawvideo','-'])
        value=struct.unpack_from('<H',first,(45*1024+500)*2)[0]
        native=((value&31)*255//31,((value>>5)&63)*255//63,(value>>11)*255//31)
        check('native RGB color preserved after video conversion',len(pixel)==3 and max(abs(a-b) for a,b in zip(pixel,native))<=12)
        check('frame render under100ms',max(render_times)<100)
        # Record itself does not mutate music; scripted musical edits/undo were
        # intentional. Saved revision is unchanged by the final stop/encode.
        before=(copy.deepcopy(m.state),m.revision,copy.deepcopy(m.history),m.playing);r.execute({'op':'record_status'})
        check('record status leaves current music untouched',before==(m.state,m.revision,m.history,m.playing))
        b.close();r.close()
        report=dict(passed=len(checks),failed=0,checks=checks,seconds=52,audio_samples=52*SR,normalized_video_frames=metadata['video_frames'],actual_display_frames=metadata['display_frames'],
                    display_landmarks=transitions,decoded_visual_landmarks=observed,visual_offsets_seconds=offsets,aac_offsets_seconds=lags,aac_correlations=correlations,
                    render_max_ms=max(render_times),native_xruns=e.stats()['xruns'],encoder=subprocess.check_output(['/usr/bin/ffmpeg','-version'],text=True).splitlines()[0],target_encoder_tested=False,physical_input=False,trace=trace)
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));print('PRIVATE artifacts:',out)

if __name__=='__main__':main()
