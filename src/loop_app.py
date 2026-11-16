"""V2 appliance: one UI/audio/USB owner, always-musical pads, asynchronous files."""
import argparse
from dataclasses import asdict
import os
from pathlib import Path
import queue
import signal
import threading
import time
from app import atomic_metrics,ipc_server
from bottle import Bottle
from recorder import SessionRecorder
from hardware import Display,Midi
from midi import MidiDispatch,EventTap
from model import relative
from loop_model import LoopModel,pad_pitch,json_ready
from loop_engine import LoopEngine,LoopPerformance
from loop_export import LoopExport
from loop_graphics import render

class LoopInstrument:
    def __init__(self,model,engine,bottle=None,recorder=None,export=None):
        self.model=model;self.engine=engine;self.performance=LoopPerformance(model,engine)
        self.bottle=bottle;self.recorder=recorder;self.export=export
        self.exit=False;self.return_stock=False;self.gear=None;self.gear_current=True;self.shift=False;self.help=False
        self.library=None;self.library_index=0;self.transition=None;self.film_attempted=False
        model.view='instrument'
    def snapshot(self):
        m=self.model
        return dict(revision=m.revision,state=json_ready(m.state),selected=m.selected,overdub=m.overdub,octave=m.octave,view=m.view,pending=len(m.pending),dirty=m.dirty,durable_revision=m.writer.durable_revision if m.writer else None,message=m.message,undo=len(m.undo_stack),redo=len(m.redo_stack))
    def received(self,events,now):
        self.gear_current=events==[]
        for event in events or []:
            if event['kind']=='cc' and event['channel']==0 and event['number']==30:
                self.gear=now if event['value'] else None;event['received']=True
    def auto_film(self):
        if self.film_attempted:return
        self.film_attempted=True
        try:
            if not self.recorder:raise ValueError('Video unavailable')
            self.recorder.start()
        except (ValueError,RuntimeError) as exc:self.model.message='NO VIDEO: '+str(exc)
    def invalidate_library(self):
        self.transition=None;self.model.cancel_replacement()
    def wire(self,event):
        if not self.engine.lib.sw_loop_ready():return False
        if event.get('received') and event['kind']=='cc' and event['number']==30:return
        kind=event['kind'];number=event['number'];value=event['value'];m=self.model
        if kind=='sysex':
            if len(number)>=10 and number[1:7]==[0,33,29,1,1,58] and number[7]&24:self.exit=True;self.return_stock=True
        elif kind in ('note','note_off','pressure','poly_pressure'):
            if kind=='note' and value:
                self.invalidate_library()
                if self.performance.transport:self.auto_film()
            self.performance.wire(event)
        elif kind=='cc' and event['channel']==0:
            self.event(number,value)
        return True
    def event(self,number,value):
        m=self.model;p=self.performance;delta=relative(value);before=m.state
        if number==49:self.shift=bool(value);return
        if number==30:self.gear=time.monotonic() if value else None;return
        if number==79:m.set_master(max(0,min(1,m.state.master+delta*.01)));m.message='MASTER OUTPUT '+str(round(m.state.master*100))+'%'
        elif number==14:m.set_tempo(max(30,min(160,m.state.tempo+delta)));m.message='TEMPO AT NEXT LOOP'
        elif 71<=number<=78:
            i=number-71
            if self.library is not None:
                self.library_index=max(0,min(max(0,len(self.library)-1),self.library_index+delta));return
            if m.view=='mixer':
                if i<len(m.state.layers):m.set_level(i,max(0,min(1,m.state.layers[i].level+delta*.02)))
            else:m.set_parameter(m.selected,i,max(0,min(1,m.state.layers[m.selected].parameters[i]+delta*.02)))
        elif value:
            if number==85:
                self.invalidate_library()
                if not p.transport:self.auto_film()
                p.play();m.message='PLAY A NOTE TO ANCHOR LOOP' if p.transport==1 else 'LOOP RUNNING' if p.transport else 'STOPPED'
            elif number==29:p.stop();m.message='STOPPED'
            elif number==112:m.view='instrument' if m.view=='mixer' else 'mixer';self.library=None;m.message='MIX / ENCODERS SET LAYER LEVELS'
            elif number in (110,50):
                if number==50 and self.shift:m.overdub=not m.overdub;m.message='OVERDUB ON' if m.overdub else 'AUDITION / NOTES NOT RECORDED'
                else:m.view='instrument';self.library=None
            elif number==51:
                if self.shift:m.request_library();m.message='READING SONG LIBRARY'
                else:m.view='overview';self.library=None
            elif number==92:
                if self.shift:p.stop();self.transition=('new',None);m.message='ARCHIVING / NEW SONG'
                elif p.add_layer():m.message='LAYER '+str(m.selected+1)+' '+m.state.layers[m.selected].role.upper()
            elif number==119:
                self.invalidate_library();p.undo(self.shift);m.message='REDO' if self.shift else 'UNDO'
            elif 102<=number<=109:
                index=number-102
                if self.library is not None:
                    index=self.library_index+index
                    if index<len(self.library):p.stop();self.transition=('load',self.library[index]);m.message='LOADING SONG / STOPPED'
                elif index<len(m.state.layers):m.selected=index;m.message='LAYER '+str(index+1)+' '+m.state.layers[index].role.upper()
                else:m.message='PRESS NEW TO ADD NEXT ROLE'
            elif 20<=number<=27:
                index=number-20
                if index<len(m.state.layers):m.mute(index)
            elif number in (62,63):
                if self.library is not None:self.library_index=max(0,min(max(0,len(self.library)-1),self.library_index+(-8 if number==62 else 8)))
                else:
                    octave=m.octave+(-1 if number==62 else 1)
                    try:pad_pitch(36,octave);m.octave=octave;m.message='D DORIAN / OCTAVE '+str(octave)
                    except ValueError:m.message='COMPLETE SCALE WINDOW LIMIT'
            elif number==82:
                if self.shift:
                    if not self.bottle:raise ValueError('Bottle unavailable')
                    self.bottle.request(30);m.message='BOTTLING LAST 30 SECONDS'
                else:m.request_save()
            elif number==86:
                if self.shift:
                    if not self.export:raise ValueError('Loop export unavailable')
                    self.export.request(m.revision,bool(m.pending));m.message='EXPORT NEXT COMPLETE LOOP'
                else:
                    if not self.recorder:raise ValueError('Video unavailable')
                    if self.recorder.snapshot()['state']=='recording':self.recorder.stop();m.message='SAVING FILM / MUSIC CONTINUES'
                    else:self.recorder.start();m.message='RECORDING FILM'
            elif number==81:self.help=not self.help
        if m.state!=before:
            self.invalidate_library();self.engine.scalar_changes(before,m.state)
    def execute(self,request):
        if not isinstance(request,dict):raise ValueError('object required')
        op=request.get('op')
        if op in ('record_start','record_stop','record_status','record_recover'):return self.recorder.execute(request)
        if op in ('request_capture','query_capture_status'):return self.bottle.execute(request)
        if op=='status':return self.snapshot()
        if not self.engine.lib.sw_loop_ready():raise ValueError('Audio commands busy / retry')
        if op=='event':
            event=dict(kind=request['kind'],channel=request.get('channel',0),number=request['number'],value=request['value'])
            if not self.wire(event):raise ValueError('Audio commands busy / retry')
        elif op=='set_master':
            before=self.model.state;self.model.set_master(request['value']);self.engine.scalar_changes(before,self.model.state)
        elif op=='export_loop':return self.export.request(self.model.revision,bool(self.model.pending))
        else:raise ValueError('V2 uses status / event / set_master / recording / capture / export_loop')
        return self.snapshot()
    def tick(self):
        self.performance.drain();m=self.model
        if self.engine.lib.sw_loop_ready():
            if self.transition and not m.pending and not self.engine.loop_stats()['held']:
                kind,name=self.transition;self.transition=None
                if kind=='new':m.request_new()
                else:m.request_load(name)
            before=m.state
            for result in m.poll_tasks():
                if result['kind']=='list' and not result.get('error'):self.library=result['names'];self.library_index=0
                if result.get('applied'):self.film_attempted=False;self.library=None
            if m.state!=before:
                self.engine.transport(0,m.overdub,m.capture_epoch);self.engine.publish(m.state,m.capture_epoch);self.performance.slots=[None]*8;self.performance.transport=0;self.film_attempted=False
        if self.gear_current and self.gear is not None and time.monotonic()-self.gear>=2:self.exit=True;self.return_stock=True
    def close(self):
        # Silence before worker/filesystem waits. sw_stop drains the queued Stop
        # while the audio thread is alive, then closes the one ALSA owner.
        self.performance.stop();self.engine.close()
        # With no ALSA thread (offline rehearsal), explicitly drain queued Stop.
        if self.model.pending:
            import ctypes as C
            pcm=(C.c_float*2)();self.engine.lib.sw_render(pcm,1)
        self.performance.drain()
        deadline=time.monotonic()+2
        for worker in (self.recorder,self.bottle,self.export):
            if worker:worker.close(timeout=max(0,deadline-time.monotonic()))
        self.model.checkpoint(True)
        if not self.model.close(timeout=max(0,deadline-time.monotonic())):
            import sys
            print('Stillwater: session writer did not finish before shutdown deadline / latest revision may be unsaved',file=sys.stderr)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--home',type=Path,default=Path('/data/push-ambient'));parser.add_argument('--offline',action='store_true');parser.add_argument('--midi-tap-seconds',type=float,default=0);parser.add_argument('--midi-tap-count',type=int,default=256);args=parser.parse_args()
    home=args.home;home.mkdir(parents=True,exist_ok=True);os.umask(0o077)
    model=LoopModel(home/'sessions/current-v2.json',legacy=home/'sessions/current.json')
    engine=LoopEngine(home/'engine.so',None if args.offline else 'hw:A3,0')
    bottle=Bottle(engine,home/'recordings');export=LoopExport(engine,home/'recordings')
    prefix=[] if Path('/lib64/ld-linux-x86-64.so.2').exists() else ['/lib/ld-linux-x86-64.so.2']
    recorder=SessionRecorder(engine,home/'recordings',ffmpeg=prefix+[str(home/'tools/ffmpeg')],ffprobe=prefix+[str(home/'tools/ffprobe')])
    instrument=LoopInstrument(model,engine,bottle,recorder,export);display=midi=None;stop=threading.Event();requests=queue.Queue(16);dispatch=MidiDispatch();frames=events=0;lastframe=laststatus=lastpower=0;render_max=render_ms=0;leds={}
    tap=EventTap(args.midi_tap_seconds,args.midi_tap_count) if args.midi_tap_seconds else None
    def end(*unused):instrument.exit=True
    signal.signal(signal.SIGTERM,end);signal.signal(signal.SIGINT,end)
    try:
        if not args.offline:display=Display();midi=Midi(tap)
        threading.Thread(target=ipc_server,args=(home/'control.sock',requests,stop),daemon=True).start()
        capture=home/'frame.bgr565' if args.offline else Path('/run/stillwater-frame.bgr565')
        if not args.offline:
            link=home/'frame.bgr565';link.unlink(missing_ok=True);link.symlink_to(capture)
        # Publish a genuine first frame before admitting Play/notes or readiness.
        first=render(model,engine.stats(),instrument)
        temp=capture.with_suffix('.tmp');temp.write_bytes(first);os.replace(temp,capture)
        if display:display.send(first)
        recorder.displayed(first);frames=1;lastframe=time.monotonic()
        (home/'ready').write_text(str(os.getpid()))
        while not instrument.exit:
            now=time.monotonic()
            if args.offline:
                import ctypes as C
                pcm=(C.c_float*512)();engine.lib.sw_render(pcm,256)
            if midi:
                def handle(event):
                    try:return instrument.wire(event)
                    except (ValueError,queue.Full) as exc:model.message=str(exc)[:80];return True
                events+=dispatch.process(midi.read,handle,instrument.received)
            if not requests.empty():
                req,answer=requests.get_nowait()
                try:
                    result=instrument.execute(req);answer.put(dict(ok=True,state=instrument.snapshot(),result=result,audio=engine.stats(),capture=bottle.snapshot(),recording=recorder.snapshot(),export=export.snapshot(),display_frames=frames,midi_events=events))
                except (ValueError,TypeError,KeyError,RuntimeError,queue.Full) as exc:answer.put(dict(ok=False,error=str(exc)))
            instrument.tick();stats=engine.stats()
            if not args.offline and not stats['alive']:raise RuntimeError('audio thread failed')
            stats['recording']=recorder.snapshot();stats['export']=export.snapshot()
            if now-lastframe>=.1:
                started=time.monotonic();frame=render(model,stats,instrument);render_ms=(time.monotonic()-started)*1000;render_max=max(render_max,render_ms)
                temp=capture.with_suffix('.tmp');temp.write_bytes(frame);os.replace(temp,capture)
                if display:display.send(frame)
                recorder.displayed(frame);frames+=1;lastframe=now
                if midi:
                    desired={('cc',112):127 if model.view=='mixer' else 10,('cc',86):127 if stats['recording']['state']=='recording' else 4,('cc',81):127 if instrument.help else 10,('cc',85):126 if stats['loop']['transport'] else 4,('cc',50):127 if model.view=='instrument' else 10,('cc',51):127 if model.view=='overview' else 10}
                    for i in range(8):desired['cc',102+i]=127 if i==model.selected else 20 if i<len(model.state.layers) else 0;desired['cc',20+i]=2 if i<len(model.state.layers) and model.state.layers[i].muted else 60 if i<len(model.state.layers) else 0
                    held={s['pad'] for index,s in enumerate(instrument.performance.slots) if s and s['held'] and stats['manual'][index]['token']==s['token'] and stats['manual'][index]['held']}
                    for n in range(36,100):desired['note',n]=15 if n in held else 93 if pad_pitch(n,model.octave)%12==2 else 94
                    for (kind,n),value in desired.items():
                        if leds.get((kind,n))!=value and getattr(midi,kind)(n,value):leds[kind,n]=value
            if now-laststatus>=1:
                status=dict(audio=stats,display_frames=frames,midi_events=events,midi_port=midi.port if midi else None,pid=os.getpid(),playing=bool(stats['loop']['transport']),revision=model.revision,uptime=now,render_ms=render_ms,render_max_ms=render_max,capture=bottle.snapshot(),recording=recorder.snapshot(),export=export.snapshot(),session=instrument.snapshot())
                status['start_ticks']=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19];atomic_metrics(home/'metrics.json',status);laststatus=now
            if midi and now-lastpower>=1:midi.write([240,0,33,29,1,1,58,247]);lastpower=now
            time.sleep(.004)
    finally:
        stop.set()
        try:instrument.close()
        finally:
            if midi:midi.close()
            if display:display.close()
            (home/'ready').unlink(missing_ok=True)
        if tap:atomic_metrics(home/'midi-tap.json',tap.snapshot())
        if instrument.return_stock:(home/'return-stock').touch()
