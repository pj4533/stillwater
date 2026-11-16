"""Typed V2 ABI and the one shared wire/synthetic performance path.

All commands originate on the owning UI thread. Workers may only read native
snapshots/history. This module does not open another MIDI/display/audio owner.
"""
import ctypes as C
from app import Engine
from roles import ROLE_IDS
from loop_model import pad_pitch


class NativeEvent(C.Structure):
    _fields_=[('id',C.c_uint64),('start_tick',C.c_uint32),('duration_tick',C.c_uint32),('pitch',C.c_int32),('velocity',C.c_float)]


class NativeLayer(C.Structure):
    _fields_=[('role',C.c_int32),('count',C.c_int32),('level',C.c_float),('muted',C.c_int32),('parameters',C.c_float*8),('events',NativeEvent*256)]


class SongBank(C.Structure):
    _fields_=[('tempo',C.c_double),('master',C.c_float),('count',C.c_int32),('layers',NativeLayer*8)]


class Take(C.Structure):
    _fields_=[('id',C.c_uint64),('epoch',C.c_uint64),('start_tick',C.c_uint32),('duration_tick',C.c_uint32),('layer',C.c_int32),('pitch',C.c_int32),('reason',C.c_int32),('status',C.c_int32),('velocity',C.c_float)]


class Snapshot(C.Structure):
    _fields_=[(k,C.c_uint64) for k in ('sample','origin','phase','cycle','loop_frames','epoch','generation','activity','boundary')]+[('tempo',C.c_double),('pending_tempo',C.c_double)]+[(k,C.c_int32) for k in ('transport','held','pending','captures','rejected')]


def bank_for(song):
    bank=SongBank(tempo=song.tempo,master=song.master,count=len(song.layers))
    for i,layer in enumerate(song.layers):
        native=bank.layers[i];native.role=ROLE_IDS.index(layer.role);native.count=len(layer.events)
        native.level=layer.level;native.muted=layer.muted
        native.parameters[:]=layer.parameters
        for index,event in enumerate(layer.events):
            native.events[index]=NativeEvent(event.id,event.start_tick,event.duration_tick,event.pitch,event.velocity)
    return bank


class LoopEngine(Engine):
    def __init__(self,path,device=None):
        super().__init__(path,device)
        self.lib.sw_song_publish.argtypes=[C.POINTER(SongBank),C.c_uint64,C.c_uint64]
        self.lib.sw_loop_transport.argtypes=[C.c_int,C.c_int,C.c_uint64]
        self.lib.sw_performance_on.argtypes=[C.c_int,C.c_int,C.c_int,C.c_int,C.c_float,C.c_int,C.c_uint64,C.c_uint64]
        self.lib.sw_performance_off.argtypes=[C.c_int,C.c_int]
        self.lib.sw_performance_pressure.argtypes=[C.c_int,C.c_int,C.c_float]
        self.lib.sw_take_poll.argtypes=[C.POINTER(Take),C.c_int]
        self.lib.sw_loop_snapshot.argtypes=[C.POINTER(Snapshot)]
        self.lib.sw_loop_tempo.argtypes=[C.c_double]
        self.lib.sw_loop_master.argtypes=[C.c_float]
        self.lib.sw_layer_parameter.argtypes=[C.c_int,C.c_int,C.c_float]
        self.lib.sw_loop_fx.argtypes=[C.c_int,C.c_int];self.lib.sw_loop_fx.restype=C.c_float
        self.generation=0;self.last_snapshot=None
    def check(self,result):
        if result:raise RuntimeError('native loop command rejected (%d)'%result)
    def publish(self,song,epoch):
        bank=bank_for(song);generation=self.generation+1
        self.check(self.lib.sw_song_publish(C.byref(bank),generation,epoch));self.generation=generation
        return generation
    def loop_stats(self):
        snapshot=Snapshot();result=self.lib.sw_loop_snapshot(C.byref(snapshot))
        if result==-1 and self.last_snapshot is not None:return dict(self.last_snapshot)
        self.check(result);self.last_snapshot={key:getattr(snapshot,key) for key,_ in Snapshot._fields_}
        return dict(self.last_snapshot)
    def stats(self):
        result=super().stats();result['loop']=self.loop_stats()
        result['fx']=[[self.lib.sw_loop_fx(l,m) for m in range(3)] for l in range(8)]
        return result
    def takes(self):
        out=(Take*64)();count=self.lib.sw_take_poll(out,64)
        if count<0:self.check(count)
        return [{key:getattr(out[i],key) for key,_ in Take._fields_} for i in range(count)]
    def transport(self,action,overdub,epoch):self.check(self.lib.sw_loop_transport(action,int(overdub),epoch))
    def scalar_changes(self,before,after):
        if before.master!=after.master:self.check(self.lib.sw_loop_master(after.master))
        if before.tempo!=after.tempo:self.check(self.lib.sw_loop_tempo(after.tempo))
        for i,(old,new) in enumerate(zip(before.layers,after.layers)):
            for p,(a,b) in enumerate(zip(old.parameters,new.parameters)):
                if a!=b:self.check(self.lib.sw_layer_parameter(i,p,b))
            if old.level!=new.level:self.check(self.lib.sw_layer_parameter(i,8,new.level))
            if old.muted!=new.muted:self.check(self.lib.sw_layer_parameter(i,9,float(new.muted)))


class LoopPerformance:
    def __init__(self,model,engine):
        self.model=model;self.engine=engine;self.slots=[None]*8;self.token=0;self.transport=0
        self.engine.publish(model.state,model.capture_epoch)
    def drain(self):
        for take in self.engine.takes():self.model.accept_take(take)
    def stop(self):
        self.drain();self.engine.transport(0,self.model.overdub,self.model.capture_epoch);self.transport=0;self.slots=[None]*8
    def play(self):
        self.drain()
        if self.transport:self.stop();return
        self.transport=2 if any(l.events for l in self.model.state.layers) else 1
        self.engine.transport(self.transport,self.model.overdub,self.model.capture_epoch)
    def undo(self,redo=False):
        self.drain();result=self.model.redo() if redo else self.model.undo()
        if result:
            self.engine.publish(self.model.state,self.model.capture_epoch);self.slots=[None]*8
        return result
    def add_layer(self):
        self.drain()
        if self.model.add_layer():
            self.engine.publish(self.model.state,self.model.capture_epoch);return True
        return False
    def wire(self,event):
        self.drain();m=self.model;kind=event['kind'];channel=event['channel'];number=event['number'];value=event['value']
        if kind=='note' and value==0:kind='note_off'
        if kind=='note' and 36<=number<=99:
            matching=[i for i,s in enumerate(self.slots) if s and s['held'] and (s['channel'],s['pad'])==(channel,number)]
            empty=[i for i,s in enumerate(self.slots) if s is None]
            released=[i for i,s in enumerate(self.slots) if s and not s['held']]
            slot=matching[0] if matching else empty[0] if empty else min(released or range(8),key=lambda i:self.slots[i]['token'])
            self.token+=1
            if self.token>=2**31:raise RuntimeError('manual identity exhausted')
            record=self.transport!=0 and m.overdub
            if record:eid=m.reserve(slot,self.token,m.selected)
            else:eid=m.next_id;m.next_id+=1
            result=self.engine.lib.sw_performance_on(slot,self.token,m.selected,pad_pitch(number,m.octave),value/127,record,m.capture_epoch,eid)
            if result!=0:m.pending.pop((slot,self.token),None)
            if result<0:self.engine.check(result)
            self.slots[slot]=dict(channel=channel,pad=number,token=self.token,held=True)
            if self.transport==1:self.transport=2
        elif kind=='note_off':
            for i,s in enumerate(self.slots):
                if s and s['held'] and (s['channel'],s['pad'])==(channel,number):self.engine.check(self.engine.lib.sw_performance_off(i,s['token']));s['held']=False
        elif kind in ('pressure','poly_pressure'):
            slots=[(i,s) for i,s in enumerate(self.slots) if s and s['held'] and s['channel']==channel and (kind!='poly_pressure' or s['pad']==number)]
            if kind=='poly_pressure' or len(slots)==1:
                for i,s in slots:self.engine.check(self.engine.lib.sw_performance_pressure(i,s['token'],value/127))
        # CC/bend mapping belongs to the UI; channel0 CC74 is never slide.
    def event(self,kind,number,value):
        self.wire(dict(kind=kind,channel=0,number=number,value=value))
