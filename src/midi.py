"""Streaming wire parser and bounded opt-in tap; never owns a second MIDI reader."""
import time
from collections import deque


class MidiDispatch:
    """Observe new input between slices; bound ordered backlog with backpressure."""
    def __init__(self,budget=.02,clock=time.monotonic,max_pending=4096):
        self.pending=deque();self.budget=budget;self.clock=clock;self.max_pending=max_pending
    def process(self,reader,handler,received=None):
        # Raw MIDI reads are bounded to 4096 bytes. At the high-water mark,
        # stop reading rather than dropping ordered note/transport events.
        # The observer must suspend hold decisions until input is drained again.
        if len(self.pending)<self.max_pending:
            batch=reader()
            if received:received(batch,self.clock())
            self.pending.extend(batch)
        elif received:received(None,self.clock())
        start=self.clock();count=0
        while self.pending and (count==0 or self.clock()-start<self.budget):
            if handler(self.pending[0]) is False:break
            self.pending.popleft();count+=1
        return count


class EventTap:
    def __init__(self,seconds=10,count=256,clock=time.monotonic):
        if not 0<seconds<=30 or not 1<=count<=2048:raise ValueError('tap bounds: seconds<=30, count<=2048')
        self.clock=clock;self.start=clock();self.seconds=seconds;self.count=count
        self.records=[];self.ranges={};self.total=0
    @property
    def done(self):return len(self.records)>=self.count or self.clock()-self.start>=self.seconds
    def record(self,status,data):
        if self.done:return
        now=self.clock();self.total+=1
        length=len(data);data=data[:32]
        self.records.append(dict(seconds=now-self.start,status=status,channel=status&15 if status<240 else None,data=list(data),length=length,truncated=length>32))
        key='%02x'%status
        r=self.ranges.setdefault(key,dict(count=0,min=[255]*len(data),max=[0]*len(data)))
        while len(r['min'])<len(data):r['min'].append(255);r['max'].append(0)
        r['count']+=1
        for i,b in enumerate(data):r['min'][i]=min(r['min'][i],b);r['max'][i]=max(r['max'][i],b)
    def snapshot(self):return dict(duration_limit=self.seconds,count_limit=self.count,total=self.total,done=self.done,ranges=self.ranges,events=self.records)


class MidiParser:
    def __init__(self,tap=None):
        self.status=0;self.pending=[];self.sysex=None;self.tap=tap
    def feed(self,data):
        events=[]
        def emit(status,payload):
            if self.tap:self.tap.record(status,payload)
            if status==240:
                events.append(dict(kind='sysex',channel=None,number=[240]+list(payload),value=0));return
            typ=status&240;channel=status&15
            if status>=240:return
            if typ in (128,144):kind='note_off' if typ==128 or payload[1]==0 else 'note'
            else:kind={160:'poly_pressure',176:'cc',192:'program',208:'pressure',224:'bend'}[typ]
            number=payload[0] if len(payload)==2 else 0
            value=payload[1] if len(payload)==2 else payload[0]
            if kind=='bend':number=0;value=payload[0]|payload[1]<<7
            events.append(dict(kind=kind,channel=channel,number=number,value=value))
        for b in data:
            if b>=248:
                if self.tap:self.tap.record(b,[])
                continue
            if b&128:
                if b==247 and self.sysex is not None:
                    emit(240,self.sysex+[247])
                self.sysex=[] if b==240 else None
                self.pending=[];self.status=b if 128<=b<240 or b in (241,242,243) else 0
                if b==246 and self.tap:self.tap.record(b,[])
                continue
            if self.sysex is not None:
                if len(self.sysex)<8192:self.sysex.append(b)
                else:self.sysex=None;self.status=0
                continue
            if not self.status:continue
            self.pending.append(b)
            length=1 if self.status&240 in (192,208) or self.status in (241,243) else 2
            if len(self.pending)==length:
                emit(self.status,self.pending);self.pending=[]
                if self.status>=240:self.status=0
        return events
