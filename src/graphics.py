"""Small custom pixel renderer: dark water, ripples and eight musical islands."""
import math
from model import STEPS
import json
import struct
from pathlib import Path
from functools import lru_cache
FONT = {
'#':['01010','11111','01010','01010','11111','01010','00000'],
'A':['01110','10001','10001','11111','10001','10001','10001'], 'B':['11110','10001','10001','11110','10001','10001','11110'],
'C':['01111','10000','10000','10000','10000','10000','01111'], 'D':['11110','10001','10001','10001','10001','10001','11110'],
'E':['11111','10000','10000','11110','10000','10000','11111'], 'F':['11111','10000','10000','11110','10000','10000','10000'],
'G':['01111','10000','10000','10111','10001','10001','01111'], 'H':['10001','10001','10001','11111','10001','10001','10001'],
'I':['111','010','010','010','010','010','111'], 'J':['00111','00010','00010','00010','10010','10010','01100'],
'K':['10001','10010','10100','11000','10100','10010','10001'], 'L':['10000','10000','10000','10000','10000','10000','11111'],
'M':['10001','11011','10101','10101','10001','10001','10001'], 'N':['10001','11001','10101','10011','10001','10001','10001'],
'O':['01110','10001','10001','10001','10001','10001','01110'], 'P':['11110','10001','10001','11110','10000','10000','10000'],
'Q':['01110','10001','10001','10001','10101','10010','01101'], 'R':['11110','10001','10001','11110','10100','10010','10001'],
'S':['01111','10000','10000','01110','00001','00001','11110'], 'T':['11111','00100','00100','00100','00100','00100','00100'],
'U':['10001','10001','10001','10001','10001','10001','01110'], 'V':['10001','10001','10001','10001','10001','01010','00100'],
'W':['10001','10001','10001','10101','10101','11011','10001'], 'X':['10001','10001','01010','00100','01010','10001','10001'],
'Y':['10001','10001','01010','00100','00100','00100','00100'], 'Z':['11111','00001','00010','00100','01000','10000','11111'],
'0':['01110','10001','10011','10101','11001','10001','01110'], '1':['010','110','010','010','010','010','111'],
'2':['01110','10001','00001','00010','00100','01000','11111'], '3':['11110','00001','00001','01110','00001','00001','11110'],
'4':['00010','00110','01010','10010','11111','00010','00010'], '5':['11111','10000','10000','11110','00001','00001','11110'],
'6':['01110','10000','10000','11110','10001','10001','01110'], '7':['11111','00001','00010','00100','01000','01000','01000'],
'8':['01110','10001','10001','01110','10001','10001','01110'], '9':['01110','10001','10001','01111','00001','00001','01110'],
':':['0','1','0','0','1','0','0'], '.':['0','0','0','0','0','0','1'], '-':['000','000','000','111','000','000','000'],
'/':['00001','00001','00010','00100','01000','10000','10000'], '+':['000','010','010','111','010','010','000'],
'|':['1','1','1','1','1','1','1'], '%':['10001','00010','00100','00100','01000','10001','00000']}
COLORS=[(255,133,96),(211,161,112),(146,180,160),(100,163,205),(116,218,210),(153,162,227),(220,180,230),(238,213,134)]

def color(rgb):
    r,g,b=rgb;return struct.pack('<H',((b>>3)<<11)|((g>>2)<<5)|(r>>3))

class Canvas:
    def __init__(self,base=None): self.pixels=bytearray(base) if base else bytearray(1024*160*2)
    def rect(self,x,y,w,h,c):
        x0=max(0,x);x1=min(960,x+w);y0=max(0,y);y1=min(160,y+h)
        if x1<=x0 or y1<=y0:return
        row=color(c)*(x1-x0)
        for yy in range(y0,y1):
            o=(yy*1024+x0)*2;self.pixels[o:o+len(row)]=row
    def pixel(self,x,y,c):
        if 0<=x<960 and 0<=y<160:
            o=(y*1024+x)*2;self.pixels[o:o+2]=color(c)
    def text(self,x,y,text,c=(186,204,209),scale=1):
        for ch in text.upper():
            g=FONT.get(ch)
            if not g:x+=4*scale;continue
            for yy,row in enumerate(g):
                for xx,v in enumerate(row):
                    if v=='1':self.rect(x+xx*scale,y+yy*scale,scale,scale,c)
            x+=(len(g[0])+1)*scale
    def ellipse(self,cx,cy,rx,ry,c):
        for j in range(90):
            a=j*math.tau/90;self.pixel(int(cx+rx*math.cos(a)),int(cy+ry*math.sin(a)),c)


    def line(self,x0,y0,x1,y1,c):
        length=max(abs(int(x1-x0)),abs(int(y1-y0)),1)
        for k in range(length+1):
            u=k/length;self.pixel(round(x0+(x1-x0)*u),round(y0+(y1-y0)*u),c)
    def disc(self,cx,cy,rx,ry,c):
        for y in range(-ry,ry+1):
            w=int(rx*math.sqrt(max(0,1-(y/max(ry,1))**2)))
            self.rect(cx-w,cy+y,w*2+1,1,c)

INK=(221,238,225)
BRASS=(222,180,99)
MIST=(100,230,208)
DARK=(9,23,26)


@lru_cache(maxsize=1)
def enclosure():
    try:
        base=(Path(__file__).resolve().parents[1]/'assets/organism-frame.bin').read_bytes()
        if len(base)!=1024*160*2:raise ValueError('art size')
    except (OSError,ValueError):base=None
    return bytes(Canvas(base).pixels)



class VisualState:
    """Bounded UI-only smoothing; native telemetry is the source of motion."""
    def __init__(self):
        self.last=None;self.levels=[0.0]*8;self.phases=[0.0]*8
        self.onsets=[0]*8;self.rings=[[] for _ in range(8)];self.pending=[None]*8;self.bottle_level=0;self.bottle_job=0
    def update(self,telemetry,seconds):
        dt=.1 if self.last is None else max(0,min(.2,seconds-self.last));self.last=seconds
        env=telemetry.get('envelopes',[0]*8);onsets=telemetry.get('onsets',[0]*8)
        for t in range(8):
            target=math.sqrt(max(0,min(1,env[t])));tau=.14 if target>self.levels[t] else .35
            self.levels[t]+=(target-self.levels[t])*(1-math.exp(-dt/tau))
            if self.levels[t]<.0005:self.levels[t]=0
            # Onsets publish inside the audio block; envelope publishes at its end.
            # Keep a real onset briefly until its audible envelope arrives.
            if onsets[t]!=self.onsets[t]:self.pending[t]=seconds
            self.onsets[t]=onsets[t]
            pending=self.pending[t]
            if pending is not None:
                if not 0<=seconds-pending<=.4:self.pending[t]=None
                elif target>0:
                    self.rings[t]=(self.rings[t]+[seconds])[-3:]
                    self.pending[t]=None
            if target>.00001:
                self.phases[t]+=dt*(.4+target*2)
                self.rings[t]=[born for born in self.rings[t] if 0<=seconds-born<2.4]
            else:self.rings[t]=[]
        return self


def macro_values(model):
    s=model.state;track=s['tracks'][model.selected]
    density=sum(bool(n) for n in track['pattern'])/STEPS
    values=[track['level'],track['tone'],track['decay'],s['space']/.8,(s['tempo']-30)/130,(s['root']-36)/48,density,s['master']]
    names=['C','C+','D','D+','E','F','F+','G','G+','A','A+','B']
    labels=['%02d'%round(track[k]*100) for k in ('level','tone','decay')]
    labels += ['%02d'%round(s['space']*100),'%03d BPM'%s['tempo'],names[s['root']%12]+' DORIAN','%02d /8'%round(density*STEPS),'%02d'%round(s['master']*100)]
    return values,labels


def etched(c,x,y,text,rgb=INK,scale=1):
    c.text(x+1,y+1,text,(2,8,11),scale);c.text(x,y,text,rgb,scale)


def chrome(c,model,seconds,telemetry):
    # Lettering etched directly into the quiet canopy; no header cards.
    etched(c,12,4,'STILLWATER',(160,196,151),2)
    etched(c,682,3,'MASTER OUTPUT',BRASS,2)
    etched(c,866,3,'%02d%%'%round(model.state['master']*100),INK,2)
    record=telemetry.get('recording') or {};state=record.get('state','idle')
    label={'recording':'REC %02d:%02d'%(int(record.get('seconds',0))//60,int(record.get('seconds',0))%60),'saving':'SAVING VIDEO','ready':'VIDEO READY','error':'VIDEO ERROR'}.get(state,'FLOWING' if model.playing else 'AT REST')
    etched(c,385,3,('MIX / ' if model.view=='mixer' else '')+label,(205,178,126),2)
    etched(c,12,23,model.state['tracks'][model.selected]['name'],COLORS[model.selected])
    # Needle registered to the existing corroded source meter at the left root.
    angle=math.pi+math.pi*model.state['master']
    c.line(22,119,round(22+13*math.cos(angle)),round(119+11*math.sin(angle)),(198,145,94))
    c.disc(22,119,2,2,(85,50,35))
    if seconds<model.master_until:
        c.rect(334,58,292,49,(10,21,23));c.line(337,59,622,59,BRASS)
        etched(c,352,68,'MASTER OUTPUT',BRASS,2)
        etched(c,518,68,'%02d%%'%round(model.state['master']*100),INK,2)
        etched(c,352,94,'VOLUME KNOB / GLOBAL / MAX 100%',INK)


@lru_cache(maxsize=1)
def organic_material():
    """Registered source lumen rows: dry reflection and four liquid textures."""
    try:data=json.loads((Path(__file__).resolve().parents[1]/'assets/organism-fluid.json').read_text())
    except (OSError,ValueError):return []
    return [[(y,x,bytes.fromhex(dry),[bytes.fromhex(raw) for raw in wet])
             for y,x,dry,wet in rows] for rows in data]


def pattern_reeds(c,model,t,position):
    cx=t*120+59;rgb=COLORS[t]
    for step,note in enumerate(model.state['tracks'][t]['pattern']):
        px=cx-28+step*8;c.rect(px,111,2,2,rgb if note else (33,61,56))
        if model.playing and step==position:c.rect(px,110,2,3,INK)
        if model.preview and model.preview['patterns'][t][step]!=note:c.rect(px,108,2,2,BRASS)


def organism(c,model,v,seconds,mix=False):
    materials=organic_material();values,labels=macro_values(model)
    names=['LEVEL','TONE','TAIL','SPACE','TEMPO','ROOT','SPARKLE','MASTER']
    for t,track in enumerate(model.state['tracks']):
        cx=t*120+59;rgb=COLORS[t];activity=v.levels[t]
        setting=track['level'] if mix else max(0,min(1,values[t]))
        rows=materials[t] if t<len(materials) else []
        if rows:
            top,bottom=rows[0][0],rows[-1][0];surface=bottom-round((bottom-top)*setting)
            if track['muted']:surface=bottom+1
            # Water/reflections remain within the original irregular organ silhouette.
            # Slow local texture displacement is analog drift, never a flash.
            phase=int(seconds*1.5+v.phases[t]*2+t)%4
            for y,x,dry,wet in rows:
                raw=wet[(phase+y//13)%4] if y>=surface else dry
                offset=(y*1024+x)*2;c.pixels[offset:offset+len(raw)]=raw
                if y==surface and not track['muted']:
                    c.line(x,y,x+len(raw)//2-1,y,tuple(round(k*.65) for k in rgb))
            if activity>.005:
                # Air travels up the sourced lumen, constrained by its row spans.
                for n in range(3):
                    row=rows[round(((v.phases[t]*.17+n*.31)%1)*(len(rows)-1))]
                    yy,xx,raw,_=row;bx=xx+len(raw)//4
                    c.disc(bx,yy,1,1,tuple(round(k*(.35+activity*.5)) for k in rgb))
            # Native ENV pinprick on the connected roots, separate from fill setpoint.
            envx=cx+39;envy=102
            c.disc(envx,envy,2,2,tuple(round(k*(.12+activity*.8)) for k in rgb))
            if mix:etched(c,envx-8,106,'ENV',(134,172,147))
        # Actual onset rings spread along the water/root line; no full-screen pulse.
        for born in v.rings[t]:
            age=(seconds-born)/2.4;c.ellipse(cx,123,7+age*31,1+age*3,tuple(round(k*.4) for k in rgb))
        # Labels and proposed-step marks always follow all local animation.
        # Tags are part of the source painting; readable ink has only a shadow.
        label=['TIDE','DRIFT','MOON','BLOOM','PEBBLE','CLOUD','DUSK','FIREFLY'][t] if mix else names[t]
        value='%03d%%'%round(track['level']*100) if mix else labels[t]
        etched(c,cx-len(label)*6,120,label,rgb,2)
        etched(c,cx-len(value)*6,140,value,(241,225,181),2)
        if track['muted']:
            # Cross the existing copper root as a closed valve, not a new card.
            c.line(cx-5,91,cx+5,97,(176,100,83));c.line(cx-5,97,cx+5,91,(176,100,83))
            etched(c,cx-15,98,'MUTED',(188,151,123))
        if t==model.selected:
            c.line(cx-16,156,cx+16,156,(174,189,119));c.disc(cx,157,2,1,(174,189,119))
        if not mix:pattern_reeds(c,model,t,getattr(v,'position',0))


def mixer(c,model,v,seconds):organism(c,model,v,seconds,True)
def mechanisms(c,model,v,seconds):organism(c,model,v,seconds)


def render(model,position,seconds,peak=0,hit=None,telemetry=None,visual=None):
    del peak,hit
    telemetry=telemetry or {};v=(visual or VisualState()).update(telemetry,seconds)
    c=Canvas(enclosure());values,labels=macro_values(model);preview=model.preview;v.position=position
    if model.view=='mixer':mixer(c,model,v,seconds)
    else:
        mechanisms(c,model,v,seconds)
        control=getattr(model,'control',None)
        if control and seconds<control['until']:
            idx=control['index'];name=['LEVEL','TONE','TAIL','SPACE','TEMPO','ROOT','SPARKLE','MASTER OUTPUT'][idx]
            c.rect(242,29,476,27,DARK);c.line(246,30,714,30,COLORS[model.selected])
            c.text(254,37,name,BRASS,2);c.text(455,37,labels[idx],INK,2)
            c.rect(582,40,119,4,(30,72,69));c.rect(582,40,round(119*max(0,min(1,values[idx]))),4,MIST)
    capture=telemetry.get('capture') or {};record=telemetry.get('recording') or {}
    footer=model.message
    if preview:footer=preview['kind'].upper()+' PREVIEW / NEW: PLANT / UNDO: CANCEL'
    if capture.get('busy'):footer='FILLING A BOTTLE / %.1fS'%capture['seconds']
    elif capture.get('state')=='corked':footer='CORKED %.1fS / SHIFT+SAVE: BOTTLE'%capture['seconds']
    elif capture.get('state')=='error':footer='BOTTLE: '+str(capture.get('error'))
    if record.get('state')=='recording':footer='RECORD TO FINISH VIDEO / STOP CLIPS: SILENCE'
    elif record.get('state')=='saving':footer='SAVING VIDEO / KEEP PLAYING'
    elif record.get('state')=='error':footer='VIDEO: '+str(record.get('error'))
    if capture.get('busy') or record.get('state') in ('recording','saving','error') or preview:
        # Dedicated canopy lane clears brand/master/view above and all tag values below.
        etched(c,202,23,footer[:82],INK)
    if telemetry.get('help'):
        c.rect(9,46,942,83,(7,21,26));c.line(12,47,948,47,BRASS)
        columns=[['PLAY: FLOW / REST','TURN ENCODERS: MACRO NAME + VALUE','SESSION: 8 STEPS X 8 VOICES','RECORD: START / FINISH VIDEO'],
                 ['MIX: EIGHT VOICE FADERS / POND','MIX ENCODERS: LEVEL PER VOICE','TOP BUTTONS: SELECT VOICE','BOTTOM BUTTONS: MUTE VOICE'],
                 ['VOLUME: MASTER OUTPUT / ALL VIEWS','NEW: GROW / UNDO: BACK','SAVE: MUSIC / SHIFT+SAVE: WAV','HOLD SETTINGS 2S: STOCK LIVE']]
        for col,lines in enumerate(columns):
            for row,text in enumerate(lines):c.text(22+col*312,58+row*16,text,INK)
    chrome(c,model,seconds,telemetry)
    return bytes(c.pixels)


def recovery_frame(reason,attempt=0):
    # No Model, native library or recorder needed: also works with broken app.
    c=Canvas(enclosure());c.rect(0,19,960,19,DARK);c.rect(8,38,944,94,(8,25,29))
    c.text(18,3,'STILLWATER',MIST,2);c.text(673,6,'MASTER OUTPUT / SILENT',BRASS)
    c.text(25,51,'THE POND IS RESTING',BRASS,2)
    c.text(25,75,str(reason).upper()[:145],INK)
    c.text(25,95,'PLAY: RETRY STILLWATER / HOLD SETTINGS 2S: STOCK LIVE',MIST)
    c.text(25,115,'YOUR SAVED MUSIC IS KEPT / AUDIO IS CLOSED',INK)
    c.text(20,145,'STILLWATER RECOVERY / ATTEMPT %d'%attempt,BRASS)
    return bytes(c.pixels)
