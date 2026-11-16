#!/usr/bin/env python3
"""Stillwater native appliance. All state/engine commands have one UI owner."""
import argparse
import copy
import ctypes as C
import json
import os
from pathlib import Path
import queue
import signal
import socket
import threading
import time
from model import Model, NOTES, PARAMS, melodic_note, pad_coord, relative, seeded, GARDENS, STEPS
from graphics import render, VisualState
from hardware import Display, Midi
from midi import EventTap, MidiDispatch
from expression import Expression, pad_leds
from bottle import Bottle
from recorder import SessionRecorder

def atomic_metrics(path, status):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(status,allow_nan=False))
    os.replace(temp,path)


class Engine:
    def __init__(self,path,device=None):
        self.lib=C.CDLL(str(path));self.previous=None;self.playing=None
        self.lib.sw_command.argtypes=[C.c_int,C.c_int,C.c_int,C.c_float]
        self.lib.sw_start.argtypes=[C.c_char_p];self.lib.sw_peak.restype=C.c_float
        self.lib.sw_envelope.argtypes=[C.c_int];self.lib.sw_envelope.restype=C.c_float
        self.lib.sw_onsets.argtypes=[C.c_int];self.lib.sw_onsets.restype=C.c_ulong
        self.lib.sw_frames.restype=C.c_ulong;self.lib.sw_xruns.restype=C.c_ulong;self.lib.sw_written.restype=C.c_ulong
        self.lib.sw_manual_on.argtypes=[C.c_int,C.c_int,C.c_int,C.c_int,C.c_float]
        self.lib.sw_manual_snapshot.argtypes=[C.c_int,C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_float),C.POINTER(C.c_float)]
        self.lib.sw_history_end.restype=C.c_uint64;self.lib.sw_history_epoch.restype=C.c_uint64
        self.lib.sw_history_copy.argtypes=[C.c_uint64,C.c_uint64,C.c_int,C.POINTER(C.c_int16)]
        if self.lib.sw_history_prepare():raise RuntimeError('history preparation requires stopped audio')
        self.on_stop=None
        if device:
            e=self.lib.sw_start(device.encode())
            if e:raise RuntimeError('ALSA start failed %d'%e)
    def command(self,op,a=0,b=0,value=0):
        if self.lib.sw_command(op,a,b,value):raise RuntimeError('audio command queue full')
    def manual_on(self,slot,token,track,note,velocity):
        if self.lib.sw_manual_on(slot,token,track,note,velocity):raise RuntimeError('manual command rejected')
    def history_window(self,seconds):
        epoch=self.lib.sw_history_epoch();end=self.lib.sw_history_end()
        if epoch!=self.lib.sw_history_epoch():raise ValueError('History changed; try again')
        count=min(end,int(seconds*44100));return epoch,end-count,count
    def history_copy(self,epoch,start,count):
        if type(count) is not int or not 1<=count<=30*44100:raise ValueError('invalid history length')
        data=(C.c_int16*(count*2))()
        if self.lib.sw_history_copy(epoch,start,count,data):raise ValueError('History expired or overwritten; capture again')
        return data
    def sync(self,model):
        s=model.state;prev=self.previous or {}
        for k,op in [('tempo',1),('master',6),('space',7)]:
            if s[k]!=prev.get(k):self.command(op,value=s[k])
        for t,track in enumerate(s['tracks']):
            old=prev.get('tracks',[{}]*8)[t]
            for i,k in enumerate(PARAMS):
                value=0 if k=='level' and track['muted'] else track[k]
                old_value=0 if k=='level' and old.get('muted') else old.get(k)
                if value!=old_value:self.command(4,t,i,value)
            for step,n in enumerate(track['pattern']):
                if n!=old.get('pattern',[-1]*STEPS)[step]:self.command(3,t,step,n)
        if model.playing!=self.playing:
            self.command(2,int(model.playing));self.playing=model.playing
            if not model.playing and self.on_stop:self.on_stop()
        self.previous=copy.deepcopy(s)
    def manual_stats(self):
        result=[]
        for i in range(8):
            token=C.c_int();held=C.c_int();track=C.c_int();env=C.c_float();pressure=C.c_float()
            valid=self.lib.sw_manual_snapshot(i,C.byref(token),C.byref(held),C.byref(track),C.byref(env),C.byref(pressure))
            result.append(dict(track=track.value,token=token.value if valid else 0,held=bool(held.value) if valid else False,envelope=env.value if valid else 0,pressure=pressure.value if valid else 0))
        return result
    def stats(self):
        return dict(frames=self.lib.sw_frames(),written_frames=self.lib.sw_written(),xruns=self.lib.sw_xruns(),position=self.lib.sw_position(),peak=self.lib.sw_peak(),alive=bool(self.lib.sw_alive()),envelopes=[self.lib.sw_envelope(t) for t in range(8)],onsets=[self.lib.sw_onsets(t) for t in range(8)],manual=self.manual_stats())
    def close(self):
        if self.lib.sw_stop():raise RuntimeError('audio shutdown timed out; process must exit')

class Instrument:
    def __init__(self,model,engine,bottle=None,recorder=None):
        self.model=model;self.engine=engine;self.exit=False;self.return_stock=False;self.gear=None;self.gear_current=True;self.hit=None;self.seed=(model.revision+18)%1000000;self.shift=False;self.garden_index=0
        self.bottle=bottle;self.recorder=recorder;self.help=False
        self.expression=Expression(engine);engine.on_stop=self.expression.clear
    def execute(self,req):
        if isinstance(req,dict) and req.get('op') in ('record_start','record_stop','record_status','record_recover'):
            if not self.recorder:raise ValueError('Video is not configured')
            return self.recorder.execute(req)
        if isinstance(req,dict) and req.get('op') in ('request_capture','query_capture_status'):
            if not self.bottle:raise ValueError('Capture is not configured')
            return self.bottle.execute(req)
        self.model.execute(req)
        if req['op']=='event':self.event(req['kind'],req['number'],req['value'])
        if req['op']=='transport' and not self.model.playing:self.silence()
        self.engine.sync(self.model)
        return self.model.snapshot()
    def silence(self):
        self.expression.clear();self.engine.command(2,0)
    def received(self,events,now):
        # Button duration is measured at receipt, not after slow saved edits.
        # A hold is actionable only after a drained read, never while input is
        # unread (including dispatcher backpressure). Releases bypass saved edits.
        self.gear_current=events==[]
        for event in events or []:
            if event['kind']=='cc' and event['channel']==0 and event['number']==30:
                self.gear=now if event['value'] else None
                event['received']=True
    def wire(self,event):
        if event.get('received') and event['kind']=='cc' and event['number']==30:return
        if event['kind']=='sysex':
            num=event['number']
            # Relinquish the surface for the stock power dialog.
            if len(num)>=10 and num[1:7]==[0,33,29,1,1,58] and num[7]&24:self.exit=True;self.return_stock=True
        elif self.expression.wire(event,self.model):
            self.model.message='Hold a lantern - pressure warms its light'
        elif event['kind']=='note' or (event['kind']=='cc' and event['channel']==0):
            self.event(event['kind'],event['number'],event['value'])
    def event(self,kind,num,value):
        m=self.model;s=copy.deepcopy(m.state)
        if kind=='note' and not value:
            self.expression.note_off(0,num);return
        if kind=='note' and value and 36<=num<=99:
            col,row=pad_coord(num)
            if m.mode=='steps':
                track=row;step=col;m.selected=track
                old=s['tracks'][track]['pattern'][step]
                note=old or NOTES[track]
                s['tracks'][track]['pattern'][step]=0 if old else note
                m.commit(s,'Ripple %d - step %d'%(track+1,step+1))
                if not old:self.engine.command(5,track,note,value/127)
            else:
                track=m.selected;note=melodic_note(num,s['root']);self.expression.note_on(0,num,note,track,value)
                m.message='A little ripple in D Dorian'
            self.hit=(time.monotonic(),track)
        elif kind=='cc':
            delta=relative(value)
            if num==49:self.shift=bool(value);return
            if num==30:self.gear=time.monotonic() if value else None;return
            if num in (14,79,70) or 71<=num<=78:
                if num==14:s['tempo']=max(30,min(160,s['tempo']+delta))
                elif num==79:s['master']=max(0,min(1,s['master']+delta*.01))
                elif num==70:s['tracks'][m.selected]['tone']=max(0,min(1,s['tracks'][m.selected]['tone']+delta*.02))
                elif m.view=='mixer':s['tracks'][num-71]['level']=max(0,min(1,s['tracks'][num-71]['level']+delta*.02))
                else:
                    idx=num-71
                    if idx<3:
                        k=PARAMS[idx];s['tracks'][m.selected][k]=max(0,min(1,s['tracks'][m.selected][k]+delta*.02))
                    elif idx==3:s['space']=max(0,min(.8,s['space']+delta*.02))
                    elif idx==4:s['tempo']=max(30,min(160,s['tempo']+delta))
                    elif idx==5:s['root']=max(36,min(84,s['root']+delta))
                    elif idx==6:
                        pattern=s['tracks'][m.selected]['pattern'];indices=[i for i,n in enumerate(pattern) if bool(n)==(delta<0)]
                        if indices:
                            i=indices[(m.revision*7)%len(indices)];pattern[i]=0 if delta<0 else NOTES[m.selected]
                    elif idx==7:s['master']=max(0,min(1,s['master']+delta*.01))
                if m.view=='instrument':
                    index=7 if num==79 else 4 if num==14 else 1 if num==70 else num-71
                    m.control=dict(index=index,until=time.monotonic()+2.5)
                if num==79 or (num==78 and m.view=='instrument'):m.master_until=time.monotonic()+2
                if s!=m.state:m.commit(s,'Mixer level' if m.view=='mixer' and 71<=num<=78 else 'LEVEL TONE TAIL SPACE TEMPO ROOT SPARKLE MASTER')
            elif value:
                if num==112:m.view='instrument' if m.view=='mixer' else 'mixer';m.message='MIX: eight encoders / eight voice levels'
                elif num==110:m.view='instrument';m.message='Pond instrument / MIX opens levels'
                elif num==85:
                    m.playing=not m.playing;m.message='Let it drift' if m.playing else 'Water at rest'
                    if not m.playing:self.silence()
                elif num==29:m.playing=False;m.message='Water at rest';self.silence()
                elif num==81:self.help=not self.help
                elif num==86:
                    try:
                        if not self.recorder:raise ValueError('Video is not configured')
                        if self.recorder.status['state']=='recording' and not self.recorder.stop_event.is_set():self.recorder.stop()
                        else:self.recorder.start()
                    except (ValueError,RuntimeError) as exc:m.message=str(exc)[:80]
                elif num==50:m.mode='notes';m.message='Pads bloom in D Dorian - top buttons pick a voice'
                elif num in (51,34):m.mode='steps';m.message='Rows are voices. Pads add/remove ripples.'
                elif num in (62,63):m.page=0;m.message='Eight steps / all voices on one grid'
                elif 102<=num<=109:m.selected=num-102;m.message='Meet '+s['tracks'][m.selected]['name']
                elif 20<=num<=27:
                    t=num-20;s['tracks'][t]['muted']=not s['tracks'][t]['muted'];m.commit(s,'Voice tucked away' if s['tracks'][t]['muted'] else 'Voice awake')
                elif num==82:
                    if self.shift:
                        try:
                            if not self.bottle:raise ValueError('Capture is not configured')
                            self.bottle.request(30)
                        except (ValueError,RuntimeError) as exc:m.message=str(exc)[:80]
                    else:m.save()
                elif num==119:
                    try:m.execute(dict(op='cancel_preview') if m.preview else dict(op='undo',revision=m.revision))
                    except ValueError:m.message='No ripples to undo yet'
                elif num==92:
                    if self.shift:
                        name=GARDENS[self.garden_index%len(GARDENS)];self.garden_index+=1
                        m.execute(dict(op='garden',name=name,revision=m.revision))
                    elif m.preview:
                        preview=m.preview
                        op='apply_grow' if preview['kind']=='grow' else 'apply_pattern'
                        m.execute(dict(op=op,id=preview['id'],revision=m.revision))
                    else:
                        self.seed=(self.seed+1)%1000001
                        pid='grow-%d-%d'%(m.revision,self.seed)
                        try:
                            m.execute(dict(op='propose_grow',id=pid,seed=self.seed,revision=m.revision))
                            m.execute(dict(op='apply_grow',id=pid,revision=m.revision))
                        except ValueError:m.message='No scale notes in this register - try a garden'
                elif num==118:s['tracks'][m.selected]['pattern']=[0]*STEPS;m.commit(s,'A quiet space for something new')
        self.engine.sync(m)
    def tick(self):
        if self.gear_current and self.gear is not None and time.monotonic()-self.gear>=2:self.exit=True;self.return_stock=True;self.model.message='Returning to Ableton Live'


def ipc_server(path,requests,stop):
    if path.exists():path.unlink()
    sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.bind(str(path));os.chmod(path,0o600);sock.listen(4);sock.settimeout(.3)
    try:
        while not stop.is_set():
            try:conn,_=sock.accept()
            except socket.timeout:continue
            with conn:
                try:
                    conn.settimeout(1);data=b''
                    while b'\n' not in data and len(data)<=16384:
                        part=conn.recv(4096)
                        if not part:break
                        data+=part
                    if len(data)>16384:raise ValueError('request too large')
                    req=json.loads(data);answer=queue.Queue(1);requests.put_nowait((req,answer))
                    result=answer.get(timeout=3);conn.sendall((json.dumps(result,allow_nan=False)+'\n').encode())
                except Exception as exc:
                    try:conn.sendall((json.dumps(dict(ok=False,error=str(exc)))+'\n').encode())
                    except OSError:pass
    finally:sock.close();path.unlink(missing_ok=True)


def quiet_and_close(instrument,engine,recorder,bottle,timeout=2):
    """Quiet/release audio before a shared bounded capture shutdown budget."""
    instrument.model.playing=False
    try:instrument.silence();engine.sync(instrument.model)
    finally:
        try:engine.close()
        finally:
            deadline=time.monotonic()+timeout
            try:recorder.close(timeout=max(0,deadline-time.monotonic()))
            finally:bottle.close(timeout=max(0,deadline-time.monotonic()))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--home',type=Path,default=Path('/data/push-ambient'));parser.add_argument('--offline',action='store_true');parser.add_argument('--midi-tap-seconds',type=float,default=0);parser.add_argument('--midi-tap-count',type=int,default=256);args=parser.parse_args()
    home=args.home;home.mkdir(parents=True,exist_ok=True);os.umask(0o077)
    tap=EventTap(args.midi_tap_seconds,args.midi_tap_count) if args.midi_tap_seconds else None;tap_saved=False
    model=Model(home/'sessions'/'current.json')
    engine=Engine(home/'engine.so',None if args.offline else 'hw:A3,0')
    bottle=Bottle(engine,home/'recordings')
    # Pinned x86 tools live on /data; use existing loader if /lib64 is absent.
    prefix=[] if Path('/lib64/ld-linux-x86-64.so.2').exists() else ['/lib/ld-linux-x86-64.so.2']
    recorder=SessionRecorder(engine,home/'recordings',ffmpeg=prefix+[str(home/'tools/ffmpeg')],ffprobe=prefix+[str(home/'tools/ffprobe')])
    instrument=Instrument(model,engine,bottle,recorder);engine.sync(model)
    display=midi=None;dispatch=MidiDispatch();requests=queue.Queue(16);stop=threading.Event();frames=events=0;leds={};lastframe=laststatus=lastpower=0;visual=VisualState();render_ms=render_max_ms=0
    def end(*unused):instrument.exit=True
    signal.signal(signal.SIGTERM,end);signal.signal(signal.SIGINT,end)
    try:
        if not args.offline:display=Display();midi=Midi(tap)
        thread=threading.Thread(target=ipc_server,args=(home/'control.sock',requests,stop),daemon=True);thread.start()
        capture=home/'frame.bgr565' if args.offline else Path('/run/stillwater-frame.bgr565')
        if not args.offline:
            link=home/'frame.bgr565'
            link.unlink(missing_ok=True);link.symlink_to(capture)
        (home/'ready').write_text(str(os.getpid()))
        while not instrument.exit:
            now=time.monotonic()
            if midi:
                events+=dispatch.process(midi.read,instrument.wire,instrument.received)
            while not requests.empty():
                req,answer=requests.get_nowait()
                try:
                    instrument.execute(req)
                    answer.put(dict(ok=True,state=model.snapshot(),audio=engine.stats(),capture=bottle.snapshot(),recording=recorder.snapshot(),display_frames=frames,midi_events=events))
                except (ValueError,TypeError,KeyError,RuntimeError) as exc:answer.put(dict(ok=False,error=str(exc)))
            instrument.tick();stats=engine.stats()
            if not args.offline and not stats['alive']:raise RuntimeError('audio thread failed')
            if now-lastframe>=.1:
                render_start=time.monotonic()
                stats['capture']=bottle.snapshot();stats['recording']=recorder.snapshot();stats['help']=instrument.help
                frame=render(model,stats['position'],now,stats['peak'],instrument.hit,telemetry=stats,visual=visual)
                render_ms=(time.monotonic()-render_start)*1000;render_max_ms=max(render_max_ms,render_ms)
                temp=capture.with_suffix('.tmp');temp.write_bytes(frame);os.replace(temp,capture)
                if display:display.send(frame)
                recorder.displayed(frame)
                frames+=1;lastframe=now
                if midi:
                    desired={('cc',112):127 if model.view=='mixer' else 10,('cc',86):127 if recorder.status['state']=='recording' else 4,('cc',81):127 if instrument.help else 10,('cc',85):126 if model.playing else 4,('cc',50):127 if model.mode=='notes' else 10,('cc',51):127 if model.mode=='steps' else 10}
                    for t in range(8):desired['cc',102+t]=127 if t==model.selected else 20;desired['cc',20+t]=2 if model.state['tracks'][t]['muted'] else 60
                    for n,v in pad_leds(model,stats,instrument.expression).items():desired['note',n]=v
                    for (kind,n),v in desired.items():
                        if leds.get((kind,n))!=v and getattr(midi,kind)(n,v):leds[kind,n]=v
            if now-laststatus>=1:
                status=dict(audio=stats,display_frames=frames,midi_events=events,midi_port=midi.port if midi else None,pid=os.getpid(),playing=model.playing,revision=model.revision,uptime=now,render_ms=render_ms,render_max_ms=render_max_ms,capture=bottle.snapshot(),recording=recorder.snapshot())
                status['start_ticks']=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]
                atomic_metrics(home/'metrics.json',status);laststatus=now
            if midi and now-lastpower>=1:
                midi.write([240,0,33,29,1,1,58,247]);lastpower=now
            if tap and tap.done and not tap_saved:
                atomic_metrics(home/'midi-tap.json',tap.snapshot());tap_saved=True
            time.sleep(.004)
    finally:
        stop.set()
        # Every music edit is already durably saved. No extra scene filesystem
        # work may delay quieting audio or terminating the owned encoder.
        try:quiet_and_close(instrument,engine,recorder,bottle)
        finally:
            try:
                if midi:midi.close()
            finally:
                if display:display.close()
                (home/'ready').unlink(missing_ok=True)
        if tap and not tap_saved:atomic_metrics(home/'midi-tap.json',tap.snapshot())
        if instrument.return_stock:(home/'return-stock').touch()

if __name__=='__main__':
    from loop_app import main as v2_main
    v2_main()
