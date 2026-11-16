"""Eight original physical worlds, native activity, readable registered controls."""
from functools import lru_cache
import math
from pathlib import Path
from graphics import Canvas,COLORS,INK,BRASS,DARK
from roles import ROLE_IDS,MACROS
from loop_model import LOOP_TICKS
ASSETS=Path(__file__).resolve().parents[1]/'assets'/'v2'

@lru_cache(maxsize=8)
def background(role):
    try:
        data=(ASSETS/(role+'.bin')).read_bytes()
        if len(data)!=1024*160*2:raise ValueError('Invalid role artwork')
        return data
    except (OSError,ValueError):return bytes(1024*160*2)


def material(c,base,role,envelope,fx):
    """Displace source material itself; no animation cards or pasted mascots."""
    if envelope<.0001:return
    amount=min(1,envelope*12);index=ROLE_IDS.index(role)
    # Individual materials occupy different registered parts of their source.
    regions=((240,650,35,84),(155,790,54,91),(130,835,30,83),(210,785,36,90),
             (45,900,38,91),(155,850,40,88),(160,830,42,92),(170,825,26,88))
    x0,x1,y0,y1=regions[index]
    for y in range(y0,y1,2):
        offset=round(math.sin(y*.16+fx*math.tau)*(1+index%3)*amount)
        if role=='oxide':offset=round((fx-.5)*4*amount) if y%14<3 else 0
        if role=='backwash':offset=-abs(offset)
        for yy in (y,y+1):
            start=(yy*1024+x0)*2;source=(yy*1024+x0+offset)*2
            c.pixels[start:start+(x1-x0)*2]=base[source:source+(x1-x0)*2]
    if role=='spore':
        for i in range(round(fx*6)):
            x=260+i*89;y=64+round(math.sin(i+fx*6)*14)
            c.disc(x,y,2,2,(135,180,97))


def render(model,stats,instrument=None):
    selected=model.state.layers[model.selected];role=selected.role;base=background(role);c=Canvas(base)
    loop=stats.get('loop',{});fx=stats.get('fx',[[0,0,0]]*8)[model.selected]
    material(c,base,role,fx[0],fx[1] if ROLE_IDS.index(role)>=2 else fx[2])
    view=getattr(model,'view','instrument');playing=loop.get('transport',0)
    # All animation is below subsequent typography and selection markers.
    if view=='overview':
        for i in range(8):
            x=i*120+5
            if i<len(model.state.layers):
                layer=model.state.layers[i]
                for beat in range(17):c.rect(x+int(beat/16*108),49,1,62,(60,64,51) if beat%4 else BRASS)
                for event in layer.events:
                    xx=x+int(event.start_tick/LOOP_TICKS*108);w=max(2,int(event.duration_tick/LOOP_TICKS*108));y=106-int((event.pitch-24)/72*54)
                    c.rect(xx,y,min(w,x+110-xx),3,COLORS[i] if not layer.muted else (55,58,52))
                if playing==2:c.rect(x+int(loop.get('phase',0)/max(1,loop.get('loop_frames',1))*108),47,2,66,INK)
                c.text(x,121,layer.role,INK,2);c.text(x,141,str(len(layer.events))+' NOTES',BRASS,2)
            else:c.text(x,121,'EMPTY',INK,2);c.text(x,141,'NEW',BRASS,2)
    elif view=='mixer':
        for i in range(8):
            x=i*120+60
            if i<len(model.state.layers):
                layer=model.state.layers[i];height=round(layer.level*47);env=stats.get('envelopes',[0]*8)[i]
                # Filled material inside source-mounted stems; values remain the
                # fader setpoint, ENV is a separate activity bead.
                c.line(x-10,112,x-10,64,BRASS);c.line(x+10,112,x+10,64,BRASS)
                for y in range(112-height,112):c.rect(x-6,y,13,1,tuple(int(v*.55) for v in COLORS[i]))
                c.disc(x+19,109-round(min(1,env)*40),2,2,COLORS[i]);c.text(x+15,53,'ENV',COLORS[i])
                if layer.muted:c.line(x-13,88,x+13,108,(233,126,101));c.line(x+13,88,x-13,108,(233,126,101))
                label=layer.role;value='MUTED' if layer.muted else str(round(layer.level*100))+'%'
            else:label='EMPTY';value='NEW'
            c.text(i*120+5,121,label,INK,2);c.text(i*120+5,141,value,BRASS,2)
    else:
        names=MACROS[ROLE_IDS.index(role)]
        for i,(name,value) in enumerate(zip(names,selected.parameters)):
            x=i*120+60;angle=(value*.75+.625)*math.tau
            # A small physical needle registered over the source's valve row.
            c.line(x,108,x+round(math.cos(angle)*10),108+round(math.sin(angle)*7),BRASS)
            c.disc(x,108,2,2,INK)
            c.text(i*120+5,121,name,INK,2);c.text(i*120+5,141,str(round(value*100))+'%',BRASS,2)
    c.text(5,4,'STILLWATER',INK,2);c.text(140,4,str(model.selected+1)+' '+role.upper(),COLORS[model.selected],2)
    mode='ARM FIRST NOTE' if playing==1 else 'OVERDUB' if playing==2 and model.overdub else 'AUDITION' if playing==2 else 'STOPPED'
    c.text(350,4,mode,INK,2)
    c.text(690,3,'MASTER OUTPUT',INK);c.text(862,3,str(round(model.state.master*100))+'%',BRASS,2)
    durable='UNSAVED' if model.dirty else 'SAVED'
    if model.writer and model.writer.error:durable='SAVE ERROR'
    c.text(6,21,f'{len(model.state.layers)}/8 LAYERS  D DORIAN  {int(model.state.tempo)} BPM  {durable}',INK)
    record=stats.get('recording',{});export=stats.get('export',{})
    status='REC '+record.get('state','idle').upper()+'  LOOP '+export.get('state','idle').upper()
    if instrument and instrument.library is not None:
        names=instrument.library;status='LIBRARY '+(names[instrument.library_index] if names else 'NO SAVED SONGS')
    c.text(440,21,status[:69],BRASS)
    c.text(5,33,model.message[:80],INK)
    if instrument and instrument.help:
        # Help intentionally replaces the middle material only; master, brand,
        # mode and all eight current macro values remain visible.
        c.rect(0,31,960,82,(8,13,12))
        for y,text in ((34,'PLAY: LOOP / STOP  PADS: D DORIAN  VOLUME: MASTER'),(52,'NEW: NEXT ROLE   TOP: SELECT   LOWER: MUTE   MIX: LEVELS'),(70,'SHIFT NOTE: AUDITION   UNDO / SHIFT UNDO: BACK / FORWARD'),(88,'SAVE: SONG   RECORD: FILM   SHIFT RECORD: LOOP WAV')):c.text(8,y,text,INK,2)
    return bytes(c.pixels)
