"""Eight original physical worlds, native activity, readable registered controls."""
from functools import lru_cache
import math
from pathlib import Path
from graphics import Canvas,COLORS,INK,BRASS,DARK
from roles import ROLE_IDS,MACROS,ROLE_RGB
from loop_model import TICKS,PITCH_NAMES,MODES
ASSETS=Path(__file__).resolve().parents[1]/'assets'/'v2'

@lru_cache(maxsize=8)
def background(role):
    try:
        data=(ASSETS/(role+'.bin')).read_bytes()
        if len(data)!=1024*160*2:raise ValueError('Invalid role artwork')
        return data
    except (OSError,ValueError):return bytes(1024*160*2)


@lru_cache(maxsize=8)
def poses(role):
    data=(ASSETS.parent/'v3'/(role+'.poses')).read_bytes()
    if len(data)!=8*17*5*64*64*2:raise ValueError('Invalid V3 mechanism poses')
    return data


@lru_cache(maxsize=8)
def working_background(role):
    data=(ASSETS.parent/'v3'/(role+'.working')).read_bytes()
    if len(data)!=1024*160*2:raise ValueError('Invalid V3 working background')
    return data


def material(c,base,role,parameters,envelope,fx,seconds):
    """Separate macro geometry and native-audio deformation, including at both
    macro endstops. Only source material pixels inside each soft mask move."""
    data=poses(role);energy=min(1,max(0,envelope)*5)
    for i,value in enumerate(parameters):
        pose=max(0,min(16,round(value*16)))
        # Native energy gates all motion; the PCM clock supplies a slow phase
        # even when an effect metric (notably Oxide dropout) is zero.
        phase=seconds*(.65+ROLE_IDS.index(role)*.055)+i*.13+fx*.15
        breathing=.5+.5*math.sin(phase*math.tau)
        audio=max(0,min(4,round(energy*(1+3*breathing))))
        offset=((i*17+pose)*5+audio)*8192;x=i*120+28
        for y in range(64):
            start=((48+y)*1024+x)*2
            c.pixels[start:start+128]=data[offset+y*128:offset+(y+1)*128]


def render(model,stats,instrument=None):
    selected=model.state.layers[model.selected];role=selected.role
    view=getattr(model,'view','instrument')
    base=working_background(role) if view in ('overview','mixer') else background(role);c=Canvas(base)
    loop=stats.get('loop',{});fx=stats.get('fx',[[0,0,0]]*8)[model.selected]
    if view=='instrument':
        envelope=max(fx[0],stats.get('envelopes',[0]*8)[model.selected])
        material(c,base,role,selected.parameters,envelope,fx[1] if ROLE_IDS.index(role)>=2 else fx[2],loop.get('sample',0)/44100)
    playing=loop.get('transport',0)
    # All animation is below subsequent typography and selection markers.
    if view=='chooser':
        c.rect(0,45,960,115,(7,14,13))
        for i,r in enumerate(ROLE_IDS):
            x=i*120+5;state=model.role_state(r);rgb=ROLE_RGB[r]
            c.text(x,54,r.upper(),rgb,2)
            c.text(x,78,'FOUNDATION' if r in ('silt','oxide','spore') else 'MID' if r in ('choir','filament','glass') else 'ACCENT',BRASS)
            c.text(x,103,'USED' if state=='USED' else 'CHOOSE' if state=='READY' else 'LOCKED',INK,2)
            c.text(x,128,'TOP BUTTON' if state=='READY' else 'REC BASE' if state=='RECORD FOUNDATION' else 'REC MID' if state=='RECORD MID LAYER' else 'IN SONG',BRASS)
    elif view=='key':
        c.rect(0,45,960,115,(7,14,13))
        c.text(12,53,'ROOT',BRASS,2);c.text(12,80,PITCH_NAMES[model.state.root%12],ROLE_RGB[role],4)
        c.text(136,53,'MODE',BRASS,2);c.text(136,80,model.state.scale.upper(),INK,3)
        c.text(12,125,'ENCODER 1 ROOT / ENCODER 2 MODE / ALL LAYERS FOLLOW',BRASS,2)
    elif view=='overview':
        c.text(6,49,str(round(loop.get('tempo',model.state.tempo))),ROLE_RGB[role],4)
        c.text(80,53,'BPM',INK,2);c.text(126,49,str(model.state.loop_beats//4)+' BAR',BRASS,3)
        pending=loop.get('pending_tempo',0)
        c.text(260,49,'NEXT '+str(round(pending))+' BPM' if pending else 'TEMPO BUTTON / ENCODER 1',BRASS,2)
        if pending:c.text(500,49,'TEMPO / ENCODER 1',INK,2)
        for i in range(8):
            x=i*120+5
            if i<len(model.state.layers):
                layer=model.state.layers[i]
                for beat in range(model.state.loop_beats+1):c.rect(x+int(beat/model.state.loop_beats*108),84,1,29,(60,64,51) if beat%4 else BRASS)
                for event in layer.events:
                    xx=x+int(event.start_tick/(model.state.loop_beats*TICKS)*108);w=max(2,int(event.duration_tick/(model.state.loop_beats*TICKS)*108));y=108-int((event.pitch-24)/72*25)
                    c.rect(xx,y,min(w,x+110-xx),3,ROLE_RGB[layer.role] if not layer.muted else (55,58,52))
                if playing==2:c.rect(x+int(loop.get('phase',0)/max(1,loop.get('loop_frames',1))*108),83,2,31,INK)
                c.text(x,121,layer.role,ROLE_RGB[layer.role],2);c.text(x,141,str(len(layer.events))+' NOTES',BRASS,2)
            else:c.text(x,121,'EMPTY',INK,2);c.text(x,141,'NEW',BRASS,2)
    elif view=='mixer':
        for i in range(8):
            x=i*120+60
            if i<len(model.state.layers):
                layer=model.state.layers[i];height=round(layer.level*47);env=stats.get('envelopes',[0]*8)[i]
                # Filled material inside source-mounted stems; values remain the
                # fader setpoint, ENV is a separate activity bead.
                c.line(x-10,112,x-10,64,BRASS);c.line(x+10,112,x+10,64,BRASS)
                for y in range(112-height,112):c.rect(x-6,y,13,1,tuple(int(v*.55) for v in ROLE_RGB[layer.role]))
                c.disc(x+19,109-round(min(1,env)*40),2,2,ROLE_RGB[layer.role]);c.text(x+15,53,'ENV',ROLE_RGB[layer.role])
                if layer.muted:c.line(x-13,88,x+13,108,(233,126,101));c.line(x+13,88,x-13,108,(233,126,101))
                label=layer.role;value='MUTED' if layer.muted else str(round(layer.level*100))+'%'
            else:label='EMPTY';value='NEW'
            c.text(i*120+5,121,label,ROLE_RGB[layer.role] if i<len(model.state.layers) else (85,100,93),2);c.text(i*120+5,141,value,BRASS,2)
    else:
        names=MACROS[ROLE_IDS.index(role)]
        for i,(name,value) in enumerate(zip(names,selected.parameters)):
            c.text(i*120+5,121,name,INK,2);c.text(i*120+5,141,str(round(value*100))+'%',BRASS,2)
    c.text(5,4,'STILLWATER',INK,2);c.text(140,4,str(model.selected+1)+' '+role.upper(),ROLE_RGB[role],2)
    mode='REC' if playing and model.overdub else 'AUDITION' if playing else 'STOPPED REC ARMED' if model.overdub else 'STOPPED AUDITION'
    c.text(350,3,mode,INK,2)
    c.text(690,3,'MASTER OUTPUT',INK);c.text(862,3,str(round(model.state.master*100))+'%',BRASS,2)
    durable='UNSAVED' if model.dirty else 'SAVED'
    if model.writer and model.writer.error:durable='SAVE ERROR'
    c.text(6,21,f'{len(model.state.layers)}/8 {PITCH_NAMES[model.state.root%12]} {model.state.scale.upper()} {int(model.state.tempo)} BPM {model.state.loop_beats//4} BAR {durable}',INK)
    record=stats.get('recording',{});export=stats.get('export',{})
    status='FILM '+record.get('state','idle').upper()+'  LOOP '+export.get('state','idle').upper()
    if instrument and instrument.library is not None:
        names=instrument.library;status='LIBRARY '+(names[instrument.library_index] if names else 'NO SAVED SONGS')
    c.text(440,21,status[:69],BRASS)
    message=model.message
    if loop.get('pending_tempo'):message='BPM '+str(round(loop['pending_tempo']))+' / APPLIES NEXT LOOP'
    if loop.get('op_token'):message='ADD BAR / REPEAT FIRST BAR / AT NEXT LOOP'
    c.text(5,33,message[:80],INK)
    if view=='overview':
        c.rect(720,139,240,21,(7,14,13))
        c.text(726,141,'ADD BAR',BRASS,2);c.text(846,141,'WAV',BRASS,2)
    if instrument and instrument.help:
        # Help intentionally replaces the middle material only; master, brand,
        # mode and all eight current macro values remain visible.
        c.rect(0,31,960,82,(8,13,12))
        for y,text in ((34,'PLAY: LOOP / STOP  PADS: SONG KEY  VOLUME: MASTER'),(52,'NEW: CHOOSE ROLE   TOP: SELECT   LOWER: MUTE   MIX: LEVELS'),(70,'RECORD: REC ON/OFF   UNDO / SHIFT UNDO: BACK / FORWARD'),(88,'SAVE: SONG   SHIFT RECORD: FILM   CLIP: LOOP / WAV')):c.text(8,y,text,INK,2)
    return bytes(c.pixels)
