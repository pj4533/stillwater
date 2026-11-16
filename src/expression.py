"""Eight isolated manual voices; original wire identity never touches sequencer IDs."""
from model import pad_coord, melodic_note


class Expression:
    def __init__(self,engine):
        self.engine=engine;self.slots=[None]*8;self.generation=0
        self.diagnostics={'bend':{},'slide':{}};self.ambiguous_pressure=0
    def clear(self):self.slots=[None]*8
    def note_on(self,channel,pad,note,track,velocity):
        matches=[i for i,s in enumerate(self.slots) if s and s['held'] and (s['channel'],s['pad'])==(channel,pad)]
        empty=[i for i,s in enumerate(self.slots) if s is None]
        released=[i for i,s in enumerate(self.slots) if s and not s['held']]
        i=matches[0] if matches else (empty[0] if empty else min(released or range(8),key=lambda j:self.slots[j]['token']))
        # Int32 tokens are never reused within an app lifetime. Fail closed at limit.
        if self.generation>=2147483647:raise RuntimeError('manual generation exhausted; restart safely')
        self.generation+=1;token=self.generation
        self.engine.manual_on(i,token,track,note,velocity/127)
        self.slots[i]=dict(channel=channel,pad=pad,track=track,token=token,held=True)
    def note_off(self,channel,pad):
        for i,s in enumerate(self.slots):
            if s and s['held'] and (s['channel'],s['pad'])==(channel,pad):
                self.engine.command(10,i,s['token']);s['held']=False
    def pressure(self,channel,value,pad=None):
        matches=[(i,s) for i,s in enumerate(self.slots) if s and s['held'] and s['channel']==channel and (pad is None or s['pad']==pad)]
        # Shared-channel pressure cannot identify one pad: ignore rather than fan out.
        if pad is None and len(matches)!=1:
            if matches:self.ambiguous_pressure+=1
            return
        for i,s in matches:self.engine.command(9,i,s['token'],value/127)
    def snapshot(self,stats):
        result=[]
        for i,s in enumerate(self.slots):
            native=stats.get('manual',[])
            if s and len(native)>i and native[i]['token']==s['token']:
                result.append(dict(s,held=s['held'] and native[i]['held'],envelope=native[i]['envelope'],pressure=native[i]['pressure']))
        return result
    def wire(self,event,model):
        kind=event['kind'];channel=event['channel'];num=event['number'];value=event['value']
        if kind=='note_off' and 36<=num<=99:self.note_off(channel,num)
        elif kind=='poly_pressure' and 36<=num<=99:self.pressure(channel,value,num)
        elif kind=='pressure':self.pressure(channel,value)
        elif kind=='bend':self.diagnostics['bend'][channel]=value
        elif kind=='cc' and num==74:self.diagnostics['slide'][channel]=value
        elif kind=='note' and 36<=num<=99 and model.mode=='notes':
            self.note_on(channel,num,melodic_note(num,model.state['root']),model.selected,value)
            return True
        return False


def pad_leds(model,stats,expression):
    """Palette indices are explicit colors, never a numeric brightness ramp.

    Measured upstream teal family:94 dark,93 medium,15 bright. Hardware firmware
    differs here, so actual physical color acceptance remains pending.
    """
    desired={}
    for n in range(36,100):
        x,y=pad_coord(n);step=x
        if model.mode=='steps':
            active=bool(model.state['tracks'][y]['pattern'][step])
            value=93 if active else (94 if y==model.selected else 0)
            if model.playing and step==stats['position']:value=15
        else:value=93 if melodic_note(n,model.state['root'])%12==model.state['root']%12 else 94
        desired[n]=value
    # Same pad on different channels: brightest actual voice wins, independent of index order.
    stages={n:0 for n in desired}
    for voice in expression.snapshot(stats):
        env=voice['envelope']
        stage=3 if voice['held'] and env>.0005 else (3 if env>=.15 else 2 if env>=.025 else 1 if env>=.001 else 0)
        stages[voice['pad']]=max(stages[voice['pad']],stage)
    for n,stage in stages.items():
        if stage:desired[n]={1:94,2:93,3:15}[stage]
    return desired
