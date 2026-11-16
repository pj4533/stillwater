"""V2 immutable song banks and bounded asynchronous session persistence.

The UI is the only editor. Frozen dataclass/tuple snapshots share unchanged
layers/events; the worker serializes them, never modifies music or native state.
Legacy files are read for validated master inheritance, never migrated/written.
"""
from dataclasses import dataclass,replace,asdict
import json
import math
import os
from pathlib import Path
import queue
import random
import hashlib
import re
import threading
import time
import uuid
from roles import ROLE_IDS,DEFAULTS

TICKS=96000
LOOP_TICKS=16*TICKS  # Legacy V2 constant; active timing always uses song.loop_beats.
MODES={
    'major':(0,2,4,5,7,9,11),'dorian':(0,2,3,5,7,9,10),
    'phrygian':(0,1,3,5,7,8,10),'lydian':(0,2,4,6,7,9,11),
    'mixolydian':(0,2,4,5,7,9,10),'minor':(0,2,3,5,7,8,10),
    'locrian':(0,1,3,5,6,8,10)}
PITCH_NAMES=('C','C#','D','D#','E','F','F#','G','G#','A','A#','B')
FOUNDATIONS=('silt','oxide','spore')
MIDS=('choir','filament','glass')
ACCENTS=('backwash','prism')
MAX_EVENTS=256
MAX_HISTORY=64
MAX_FILE=16*1024*1024
ID_MAX=2**53-1


def number(value,lo,hi):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError('invalid number')
    return value


def integer(value,lo,hi):
    if type(value) is not int or not lo<=value<=hi:raise ValueError('invalid integer')
    return value


def exact(obj,fields):
    if not isinstance(obj,dict) or set(obj)!=set(fields.split()):raise ValueError('invalid fields')


@dataclass(frozen=True)
class Event:
    id:int
    pitch:int
    velocity:float
    start_tick:int
    duration_tick:int
    degree:int=None
    def __post_init__(self):
        if self.degree is None:object.__setattr__(self,'degree',pitch_degree(self.pitch))


@dataclass(frozen=True)
class Layer:
    id:int
    role:str
    level:float=.3
    muted:bool=False
    parameters:tuple=()
    events:tuple=()


@dataclass(frozen=True)
class Song:
    schema:int
    song_id:str
    tempo:float
    master:float
    root:int
    scale:str
    loop_beats:int
    role_order:tuple
    layers:tuple


def degree_pitch(degree,root=62,scale='dorian'):
    return root+12*(degree//7)+MODES[scale][degree%7]


def pitch_degree(pitch,root=62,scale='dorian'):
    # Lower degree wins exact-distance ties, including off-scale V2 imports.
    return min(range(-42,43),key=lambda d:(abs(degree_pitch(d,root,scale)-pitch),d))


def project_degree(degree,root,scale):
    pitch=degree_pitch(degree,root,scale)
    while pitch<24:pitch+=12
    while pitch>96:pitch-=12
    return pitch


def variant(role,song_id,context):
    rng=random.Random(hashlib.sha256((song_id+role+str(context)).encode()).digest())
    return tuple(max(.02,min(.85,p+rng.uniform(-.055,.055))) for p in DEFAULTS[ROLE_IDS.index(role)])


def blank(master=.28,seed=None):
    order=('silt',)+tuple(r for r in ROLE_IDS if r!='silt');sid=uuid.uuid4().hex
    return Song(2,sid,58,number(master,0,1),62,'dorian',4,order,
                (Layer(0,'silt',parameters=variant('silt',sid,0)),))


def decode_song(raw):
    raw=dict(raw)
    if raw.get('schema')==1 and 'loop_beats' not in raw:raw['loop_beats']=16
    exact(raw,'schema song_id tempo master root scale loop_beats role_order layers')
    if type(raw['schema']) is not int or raw['schema'] not in (1,2) or raw['scale'] not in MODES or type(raw['loop_beats']) is not int or raw['loop_beats'] not in range(4,33,4):raise ValueError('unsupported song')
    if raw['schema']==1 and (raw['scale']!='dorian' or raw['loop_beats']!=16):raise ValueError('unsupported V2 song')
    ticks=raw['loop_beats']*TICKS
    if not isinstance(raw['song_id'],str) or not re.fullmatch('[0-9a-f]{32}',raw['song_id']):raise ValueError('invalid song id')
    number(raw['tempo'],30,160);number(raw['master'],0,1)
    integer(raw['root'],60,71)
    if raw['schema']==1 and raw['root']!=62:raise ValueError('invalid V2 key')
    order=raw['role_order']
    if not isinstance(order,list) or len(order)!=8 or set(order)!=set(ROLE_IDS):raise ValueError('invalid role deck')
    if not isinstance(raw['layers'],list) or not 1<=len(raw['layers'])<=8:raise ValueError('invalid layers')
    layers=[];ids=set()
    for i,item in enumerate(raw['layers']):
        exact(item,'id role level muted parameters events')
        if integer(item['id'],0,7)!=i or item['role']!=order[i] or type(item['muted']) is not bool:raise ValueError('invalid layer identity')
        number(item['level'],0,1)
        params=item['parameters'];events=item['events']
        if not isinstance(params,list) or len(params)!=8:raise ValueError('eight parameters required')
        for p in params:number(p,0,1)
        if not isinstance(events,list) or len(events)>MAX_EVENTS:raise ValueError('loop full')
        decoded=[]
        for event in events:
            exact(event,'id pitch velocity start_tick duration_tick'+(' degree' if raw['schema']==2 else ''))
            eid=integer(event['id'],1,ID_MAX)
            if eid in ids:raise ValueError('duplicate event id')
            ids.add(eid);integer(event['pitch'],24,96)
            if number(event['velocity'],0,1)==0:raise ValueError('zero velocity event')
            integer(event['start_tick'],0,ticks-1);integer(event['duration_tick'],1,ticks)
            degree=integer(event['degree'],-42,42) if raw['schema']==2 else pitch_degree(event['pitch'],raw['root'],raw['scale'])
            decoded.append(Event(**dict(event,degree=degree)))
        if decoded!=sorted(decoded,key=lambda e:(e.start_tick,e.id)):raise ValueError('unsorted events')
        layers.append(Layer(item['id'],item['role'],item['level'],item['muted'],tuple(params),tuple(decoded)))
    return Song(2,raw['song_id'],raw['tempo'],raw['master'],raw['root'],raw['scale'],raw['loop_beats'],tuple(order),tuple(layers))


def envelope(revision,state,undo,redo):
    return dict(format='stillwater-loop',version=2,revision=revision,state=state,undo=undo,redo=redo)


def json_ready(value):
    if isinstance(value,Song):return json_ready(asdict(value))
    if isinstance(value,dict):return {k:json_ready(v) for k,v in value.items()}
    if isinstance(value,tuple):return [json_ready(v) for v in value]
    return value


def read_envelope(path):
    path=Path(path)
    with path.open('rb') as f:
        raw=f.read(MAX_FILE+1)
    if len(raw)>MAX_FILE:raise ValueError('session too large')
    obj=json.loads(raw)
    exact(obj,'format version revision state undo redo')
    if obj['format']!='stillwater-loop' or type(obj['version']) is not int or obj['version'] not in (1,2):raise ValueError('unsupported loop envelope')
    revision=integer(obj['revision'],0,ID_MAX)
    if not isinstance(obj['undo'],list) or not isinstance(obj['redo'],list) or len(obj['undo'])+len(obj['redo'])>MAX_HISTORY:raise ValueError('invalid history')
    return envelope(revision,decode_song(obj['state']),tuple(decode_song(s) for s in obj['undo']),tuple(decode_song(s) for s in obj['redo']))


def legacy_master(path):
    """Validate the full old envelope without invoking its mutating loader."""
    from model import normalize_saved_session
    path=Path(path)
    if not path.exists():return .28
    if path.stat().st_size>MAX_FILE:raise ValueError('legacy session too large')
    raw=json.loads(path.read_bytes())
    if raw.get('format')=='stillwater-session':
        exact(raw,'format version revision state history')
        if type(raw['version']) is not int or raw['version'] not in (2,3):raise ValueError('unsupported legacy envelope')
        state=raw['state'];history=raw['history'];integer(raw['revision'],0,ID_MAX)
    else:
        journal=path.with_suffix('.history.json')
        if not journal.exists() or journal.stat().st_size>MAX_FILE:raise ValueError('ambiguous legacy session')
        stored=json.loads(journal.read_bytes())
        if stored.get('state')!=raw:raise ValueError('legacy journal mismatch')
        state=raw;history=stored['history'];integer(stored['revision'],0,ID_MAX)
    if not isinstance(history,list) or len(history)>64:raise ValueError('invalid legacy history')
    valid=normalize_saved_session(state)
    for item in history:normalize_saved_session(item)
    return valid['master']


def pad_pitch(pad,octave=0,root=62,scale='dorian'):
    integer(pad,36,99);integer(octave,-4,4)
    degree=(pad-36)%8+(pad-36)//8*3-14+7*octave
    low=degree_pitch(-14+7*octave,root,scale);high=degree_pitch(14+7*octave,root,scale)
    if low<24 or high>96:raise ValueError('octave exceeds complete pad window')
    return degree_pitch(degree,root,scale)


def atomic_write(path,payload,no_replace=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.parent/('.'+path.name+'-'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('xb') as f:
            f.write(json.dumps(json_ready(payload),allow_nan=False,separators=(',',':')).encode())
            f.flush();os.fsync(f.fileno())
        if no_replace:os.link(temp,path);temp.unlink()
        else:os.replace(temp,path)
        fd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        try:temp.unlink()
        except FileNotFoundError:pass


class SessionWriter:
    """One coalescing checkpoint slot plus four bounded library tasks."""
    def __init__(self,path,debounce=.25,max_interval=1):
        self.path=Path(path);self.condition=threading.Condition();self.pending=None
        self.first=0.;self.changed=0.;self.force=False;self.closing=False
        self.durable_revision=-1;self.error=None;self.debounce=debounce;self.max_interval=max_interval
        self.jobs=queue.Queue(4);self.results=queue.Queue(4)
        self.thread=threading.Thread(target=self._run,name='stillwater-session-writer',daemon=True);self.thread.start()
    def submit(self,payload,force=False):
        with self.condition:
            if self.closing:raise RuntimeError('writer closed')
            now=time.monotonic()
            if self.pending is None:self.first=now
            if self.pending is None or payload['revision']>=self.pending['revision']:
                self.pending=payload;self.changed=now
            self.force=self.force or force;self.condition.notify()
    def task(self,kind,payload=None,name=None):
        if kind not in ('snapshot','archive','load','list'):raise ValueError('invalid library task')
        if kind=='load' and (not isinstance(name,str) or not re.fullmatch('song-[0-9a-f]{32}\\.json',name)):raise ValueError('invalid library id')
        self.jobs.put_nowait((kind,payload,name))
        with self.condition:self.condition.notify()
    def _job(self,kind,payload,name):
        directory=self.path.parent/'saved'
        if kind in ('snapshot','archive'):
            name='song-'+uuid.uuid4().hex+'.json';atomic_write(directory/name,payload['current'] if kind=='archive' else payload,True)
            return dict(kind=kind,name=name,revision=payload['revision'],request_token=payload.get('request_token'))
        if kind=='load':
            from library_manager import identity
            actual=identity(directory/name)
            if payload.get('file_identity') is not None and actual!=payload['file_identity']:raise ValueError('Saved loop changed; refresh')
            loaded=read_envelope(directory/name)
            archived='song-'+uuid.uuid4().hex+'.json';atomic_write(directory/archived,payload['current'],True)
            return dict(kind=kind,name=name,revision=payload['revision'],request_token=payload['request_token'],payload=loaded,archived=archived)
        names=[]
        if directory.exists():
            with os.scandir(directory) as entries:
                for entry in entries:
                    if re.fullmatch('song-[0-9a-f]{32}\\.json',entry.name) and entry.is_file(follow_symlinks=False):
                        names.append(entry.name)
                        if len(names)>=256:break
        return dict(kind=kind,names=sorted(names))
    def _run(self):
        while True:
            with self.condition:
                now=time.monotonic();payload=None;job=None
                ready=self.pending is not None and (self.force or self.closing or now>=min(self.changed+self.debounce,self.first+self.max_interval))
                if ready:
                    payload=self.pending;self.pending=None;self.force=False
                elif not self.jobs.empty() and not self.results.full():job=self.jobs.get_nowait()
                elif self.closing and self.pending is None:return
                else:
                    wait=.1 if self.pending is None else max(.001,min(self.changed+self.debounce,self.first+self.max_interval)-now)
                    self.condition.wait(wait);continue
            if job:
                try:result=self._job(*job)
                except Exception as exc:result=dict(kind=job[0],error=str(exc),revision=job[1]['revision'] if job[1] else None,request_token=job[1].get('request_token') if job[1] else None)
                self.results.put_nowait(result)
            if payload:
                try:
                    if payload['revision']>self.durable_revision:atomic_write(self.path,payload)
                    with self.condition:self.durable_revision=max(self.durable_revision,payload['revision']);self.error=None;self.condition.notify_all()
                except Exception as exc:
                    with self.condition:
                        self.error=str(exc)
                        if self.pending is None or self.pending['revision']<payload['revision']:self.pending=payload
                        self.first=self.changed=time.monotonic();self.condition.notify_all()
                    if self.closing:return
    def flush(self,revision,timeout=2):
        deadline=time.monotonic()+timeout
        with self.condition:
            self.force=True;self.condition.notify()
            while self.durable_revision<revision and self.thread.is_alive():
                left=deadline-time.monotonic()
                if left<=0:return False
                self.condition.wait(left)
            return self.durable_revision>=revision
    def close(self,timeout=2):
        with self.condition:self.closing=True;self.force=True;self.condition.notify_all()
        self.thread.join(timeout)
        return not self.thread.is_alive() and self.pending is None


class LoopModel:
    def __init__(self,path,legacy=None,seed=None,writer=True):
        self.path=Path(path);v2=self.path.with_name('current-v2.json')
        bootstrap=read_envelope(v2) if self.path.name=='current-v3.json' and not self.path.exists() and v2.exists() else None
        self.state=blank(legacy_master(legacy) if legacy and not self.path.exists() and bootstrap is None else .28,seed)
        self.revision=0;self.undo_stack=();self.redo_stack=()
        if self.path.exists() or bootstrap is not None:
            env=read_envelope(self.path) if self.path.exists() else bootstrap
            self.state=env['state'];self.revision=env['revision'];self.undo_stack=env['undo'];self.redo_stack=env['redo']
        self.selected=0;self.octave=0;self.capture_epoch=1;self.pending={};self.overdub=True
        self.next_id=1+max((e.id for s in (self.state,)+self.undo_stack+self.redo_stack for l in s.layers for e in l.events),default=0)
        self.gesture=None;self.message='PLAY THEN PLAY A NOTE';self.new_revision=None;self.loading_revision=None
        self.replacement_serial=0;self.replacement_request=None
        self.writer=SessionWriter(self.path) if writer else None
        if self.writer:
            if self.path.exists():self.writer.durable_revision=self.revision
            else:self.checkpoint()
    def payload(self):return envelope(self.revision,self.state,self.undo_stack,self.redo_stack)
    def checkpoint(self,force=False):
        if self.writer:self.writer.submit(self.payload(),force)
    @property
    def dirty(self):return self.writer is not None and self.writer.durable_revision<self.revision
    def normalize_octave(self):
        valid=[]
        for octave in range(-4,5):
            try:pad_pitch(36,octave,self.state.root,self.state.scale)
            except ValueError:continue
            valid.append(octave)
        self.octave=min(valid,key=lambda octave:(abs(octave-self.octave),octave))
    def commit(self,state,gesture=None,now=None):
        if state==self.state:return False
        now=time.monotonic() if now is None else now
        grouped=gesture is not None and self.gesture is not None and self.gesture[0]==gesture and now-self.gesture[1]<=.25
        if not grouped:self.undo_stack=(self.undo_stack+(self.state,))[-MAX_HISTORY:]
        self.redo_stack=();self.state=state;self.normalize_octave();self.revision+=1
        self.gesture=(gesture,now) if gesture is not None else None;self.checkpoint();return True
    def layer_edit(self,index,**changes):
        integer(index,0,len(self.state.layers)-1)
        layers=list(self.state.layers);layers[index]=replace(layers[index],**changes)
        return replace(self.state,layers=tuple(layers))
    def set_parameter(self,index,param,value,now=None):
        integer(param,0,7);number(value,0,1)
        params=list(self.state.layers[index].parameters);params[param]=value
        return self.commit(self.layer_edit(index,parameters=tuple(params)),('parameter',index,param),now)
    def set_level(self,index,value,now=None):
        return self.commit(self.layer_edit(index,level=number(value,0,1)),('level',index),now)
    def set_master(self,value,now=None):return self.commit(replace(self.state,master=number(value,0,1)),('master',),now)
    def set_tempo(self,value,now=None):return self.commit(replace(self.state,tempo=number(value,30,160)),('tempo',),now)
    def mute(self,index):return self.commit(self.layer_edit(index,muted=not self.state.layers[index].muted))
    def role_state(self,role):
        if any(l.role==role for l in self.state.layers):return 'USED'
        recorded={l.role for l in self.state.layers if l.events}
        if role in FOUNDATIONS:return 'READY'
        if not recorded.intersection(FOUNDATIONS):return 'RECORD FOUNDATION'
        if role in MIDS:return 'READY'
        return 'READY' if recorded.intersection(MIDS) else 'RECORD MID LAYER'
    def add_layer(self,role=None):
        i=len(self.state.layers)
        if i==8:self.message='ALL 8 LAYERS / SELECT A LAYER';return False
        if role is None:role=next((r for r in ROLE_IDS if self.role_state(r)=='READY'),None)
        if role not in ROLE_IDS or self.role_state(role)!='READY':self.message='RECORD FOUNDATION / MID TO UNLOCK';return False
        prefix=tuple(l.role for l in self.state.layers)+(role,)
        order=prefix+tuple(r for r in ROLE_IDS if r not in prefix)
        accepted=self.commit(replace(self.state,role_order=order,layers=self.state.layers+(Layer(i,role,parameters=variant(role,self.state.song_id,i)),)))
        self.selected=i;return accepted
    def rekey(self,root,scale,now=None):
        integer(root,60,71)
        if scale not in MODES:raise ValueError('invalid scale')
        layers=tuple(replace(l,events=tuple(replace(e,degree=e.degree if e.degree is not None else pitch_degree(e.pitch,self.state.root,self.state.scale),pitch=project_degree(e.degree if e.degree is not None else pitch_degree(e.pitch,self.state.root,self.state.scale),root,scale)) for e in l.events)) for l in self.state.layers)
        return self.commit(replace(self.state,root=root,scale=scale,layers=layers),('key',),now)
    def extended(self):
        s=self.state
        if s.loop_beats>=32:raise ValueError('8 BAR LIMIT')
        copies=[[e for e in l.events if e.start_tick<4*TICKS] for l in s.layers]
        if any(len(l.events)+len(es)>MAX_EVENTS for l,es in zip(s.layers,copies)):raise ValueError('LOOP FULL / ADD BAR CANCELLED')
        eid=self.next_id;layers=[]
        for l,es in zip(s.layers,copies):
            added=[]
            for e in es:integer(eid,1,ID_MAX);added.append(replace(e,id=eid,start_tick=e.start_tick+s.loop_beats*TICKS));eid+=1
            layers.append(replace(l,events=l.events+tuple(added)))
        return replace(s,loop_beats=s.loop_beats+4,layers=tuple(layers))
    def clear_layer(self):
        self.pending.clear();self.capture_epoch+=1;self.gesture=None
        return self.commit(self.layer_edit(self.selected,events=()))
    def reserve(self,slot,token,layer):
        integer(slot,0,7);integer(token,1,2**31-1);integer(layer,0,len(self.state.layers)-1)
        eid=self.next_id;integer(eid,1,ID_MAX);self.next_id+=1
        self.pending[(slot,token)]=(self.capture_epoch,layer,eid)
        return eid
    def accept_take(self,take):
        if take['epoch']!=self.capture_epoch:return False
        eid=integer(take['id'],1,ID_MAX);status=integer(take.get('status',0),0,1)
        if not status:
            index=integer(take['layer'],0,len(self.state.layers)-1)
            pitch=integer(take['pitch'],24,96);velocity=number(take['velocity'],0,1)
            if not velocity:raise ValueError('zero velocity event')
            start=integer(take['start_tick'],0,self.state.loop_beats*TICKS-1)
            duration=integer(take['duration_tick'],1,self.state.loop_beats*TICKS)
            event=Event(eid,pitch,velocity,start,duration,pitch_degree(pitch,self.state.root,self.state.scale));layer=self.state.layers[index]
            duplicate=any(e.id==eid for l in self.state.layers for e in l.events)
            if not duplicate and len(layer.events)>=MAX_EVENTS:raise ValueError('native event capacity mismatch')
        for key,value in tuple(self.pending.items()):
            if value[2]==eid:del self.pending[key]
        if status:self.message='LOOP FULL / AUDITION ONLY';return False
        if duplicate:return False
        events=tuple(sorted(layer.events+(event,),key=lambda e:(e.start_tick,e.id)))
        # Existing frozen state was validated at construction/load. Only this
        # bounded event/layer delta crosses the native trust boundary here.
        return self.commit(self.layer_edit(index,events=events))
    def cancel_pending(self):
        if not self.pending:return False
        self.pending.clear();self.capture_epoch+=1;self.gesture=None;return True
    def undo(self):
        if self.cancel_pending():return 'cancel'
        if not self.undo_stack:return False
        self.redo_stack=(self.redo_stack+(self.state,))[-MAX_HISTORY:]
        self.state=self.undo_stack[-1];self.undo_stack=self.undo_stack[:-1];self._history_changed();return True
    def redo(self):
        if not self.redo_stack:return False
        if self.pending:self.cancel_pending()
        self.undo_stack=(self.undo_stack+(self.state,))[-MAX_HISTORY:]
        self.state=self.redo_stack[-1];self.redo_stack=self.redo_stack[:-1];self._history_changed();return True
    def _history_changed(self):
        self.normalize_octave()
        self.capture_epoch+=1;self.gesture=None;self.revision+=1;self.selected=min(self.selected,len(self.state.layers)-1);self.checkpoint()
    def request_save(self):
        if not self.writer:raise RuntimeError('persistence unavailable')
        self.checkpoint(True);self.writer.task('snapshot',self.payload());self.message='SAVING SONG'
    def request_library(self):
        if not self.writer:raise RuntimeError('persistence unavailable')
        self.writer.task('list')
    def cancel_replacement(self):
        self.replacement_request=None;self.new_revision=None;self.loading_revision=None
    def _request_replacement(self,kind,name=None,file_identity=None):
        if self.pending:raise ValueError('stop and drain captured notes before replacing song')
        if not self.writer:raise RuntimeError('persistence unavailable')
        token=self.replacement_serial+1
        payload=dict(revision=self.revision,current=self.payload(),request_token=token,file_identity=file_identity)
        # Only accepted jobs supersede earlier requests; queue-full is a no-op.
        self.writer.task(kind,payload,name)
        self.replacement_serial=token;self.replacement_request=(token,kind)
        self.new_revision=self.revision if kind=='archive' else None
        self.loading_revision=self.revision if kind=='load' else None
    def request_load(self,name,file_identity=None):self._request_replacement('load',name,file_identity)
    def request_new(self):self._request_replacement('archive')
    def poll_tasks(self):
        results=[]
        if not self.writer:return results
        while True:
            try:result=self.writer.results.get_nowait()
            except queue.Empty:return results
            results.append(result)
            kind=result['kind']
            if kind in ('load','archive'):
                if self.replacement_request!=(result.get('request_token'),kind):
                    result['applied']=False;continue
                # A stale completion, including an error, cannot retire a newer
                # accepted load/New even when both began at the same revision.
                self.cancel_replacement()
                if result.get('error'):self.message=result['error'];result['applied']=False;continue
                if self.pending or result['revision']!=self.revision:
                    result['applied']=False;self.message='SONG CHANGED / '+('LOAD' if kind=='load' else 'NEW')+' CANCELLED';continue
                if kind=='load':
                    self.state=result['payload']['state'];self.undo_stack=self.redo_stack=()
                    self.selected=0;self.overdub=True;self._history_changed()
                    self.next_id=max(self.next_id,1+max((e.id for l in self.state.layers for e in l.events),default=0))
                    self.message='SONG LOADED / STOPPED'
                else:
                    self.commit(blank(self.state.master));self.selected=0;self.overdub=True;self.capture_epoch+=1
                result['applied']=True
            elif result.get('error'):self.message=result['error']
            elif kind=='snapshot':self.message='SONG SNAPSHOT SAVED'
    def close(self,timeout=2):return self.writer.close(timeout) if self.writer else True
