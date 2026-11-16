"""UI-owned drafts/navigation and recent native note indications; no file I/O."""
import queue
import time
from loop_model import MODES
from library_manager import ALPHABET

class SlowChoice:
    def __init__(self):self.reset()
    def reset(self):self.total=0;self.last=0;self.sign=0
    def step(self,delta,now=None):
        now=time.monotonic() if now is None else now
        sign=1 if delta>0 else -1 if delta<0 else 0
        if now-self.last>.35 or sign!=self.sign:self.total=0
        self.last=now;self.sign=sign;self.total+=delta
        if abs(self.total)<4:return 0
        self.total=0;return sign

class PitchLights:
    def __init__(self):
        self.identity=None;self.seen=[[0]*128 for _ in range(8)];self.until={};self.rotation={};self.collisions={}
    def colors(self,model,stats,now=None):
        now=time.monotonic() if now is None else now;t=stats.get('pitches');self.collisions={}
        if not t or t['epoch']!=model.capture_epoch:
            self.until.clear();return {}
        ident=(t['epoch'],t['reset'])
        if self.identity!=ident:
            self.identity=ident;self.until.clear();self.rotation.clear()
            # On a new epoch, gates describe current starts. Baseline counters
            # prevents old pre-replacement onsets reappearing in a new key.
            self.seen=[[0]*128 for _ in range(8)]
        pitches={}
        for p in range(128):
            fresh=[];roles=[]
            for l,layer in enumerate(model.state.layers):
                enabled=bool(t['enabled']&(1<<l)) and not layer.muted and layer.level>0
                count=t['onset'][l][p];changed=count!=self.seen[l][p];self.seen[l][p]=count
                key=(l,p)
                if not enabled:self.until.pop(key,None);continue
                if changed:self.until[key]=now+.15;fresh.append(l)
                if t['gate'][l][p] or self.until.get(key,0)>now:roles.append(l)
            if not roles:
                self.rotation.pop(p,None);continue
            if len(roles)>1:
                self.collisions[str(p)]=roles
                if fresh:
                    # One complete round for short multi-role unisons.
                    for l in roles:self.until[l,p]=max(self.until.get((l,p),0),now+.2*len(roles))
                previous=self.rotation.get(p)
                if previous is None:
                    owner=roles[-1] if fresh else roles[0];deadline=now+.2;interrupted=True
                    base=owner
                else:
                    base,deadline,interrupted=previous;advanced=False
                    index=roles.index(base) if base in roles else 0
                    if now>=deadline:
                        base=roles[(index+max(1,int((now-deadline)/.2)+1))%len(roles)]
                        deadline=now+.2;interrupted=False;advanced=True
                    owner=base
                    # An arrival gets an immediate turn within this time slot,
                    # without resetting the fair rotation's deadline. Repeated
                    # dense onsets cannot indefinitely postpone another role.
                    if fresh and not interrupted and not advanced and now<deadline-.001:
                        owner=fresh[-1];interrupted=True
                self.rotation[p]=(base,deadline,interrupted)
            else:
                owner=roles[0];self.rotation.pop(p,None)
            pitches[p]=model.state.layers[owner].role
        return pitches

class ManagementUI:
    """Mixin; all task completions are pinned to a page/request generation."""
    def init_management(self,manager):
        self.manager=manager;self.page_generation=0;self.rows=[];self.selected_id=None;self.manager_busy=False
        self.confirm=None;self.details=False;self.record_tab='current';self.return_view='instrument'
        self.key_draft=None;self.slow=[SlowChoice() for _ in range(8)];self.rename=None;self.rename_cursor=0;self.character=1
        self.pitch_lights=PitchLights()
    def open_page(self,page):
        if page not in ('library','recordings','key','instrument','mixer','overview','chooser'):raise ValueError('Invalid page')
        if self.model.view=='library':self.invalidate_library()
        if self.model.view not in ('library','recordings','key'):self.return_view=self.model.view
        self.page_generation+=1;self.manager_busy=False;self.confirm=None;self.details=False;self.rename=None
        for slow in self.slow:slow.reset()
        self.key_draft=[self.model.state.root,self.model.state.scale] if page=='key' else None
        self.model.view=page;self.library=None
        if page in ('library','recordings'):
            self.rows=[];self.selected_id=None
            if page=='library':self.refresh_manager()
            else:self.record_tab='current'
    def refresh_manager(self):
        if not self.manager:self.rows=[];return
        self.page_generation+=1;self.confirm=None;self.manager_busy=True
        try:self.manager.submit('loops' if self.model.view=='library' else 'recordings',self.page_generation)
        except Exception:self.manager_busy=False;raise
    def selected_row(self):return next((r for r in self.rows if r['id']==self.selected_id),None)
    def select_row(self,step):
        if not self.rows:return
        index=next((i for i,r in enumerate(self.rows) if r['id']==self.selected_id),0)
        self.selected_id=self.rows[max(0,min(len(self.rows)-1,index+step))]['id']
        self.confirm=None
    def manager_task(self,kind,**data):
        if not self.manager:raise ValueError('Library unavailable')
        if self.manager_busy:raise ValueError('Library busy; wait')
        self.page_generation+=1;self.manager_busy=True
        try:self.manager.submit(kind,self.page_generation,**data)
        except Exception:self.manager_busy=False;raise
    def management_tick(self):
        if not self.manager:return
        while True:
            try:result=self.manager.results.get_nowait()
            except queue.Empty:break
            if result['generation']!=self.page_generation or self.model.view not in ('library','recordings'):continue
            self.manager_busy=False
            if result.get('error'):self.model.message=result['error'];continue
            if 'rows' in result:
                self.rows=result['rows']
                if not any(r['id']==self.selected_id for r in self.rows):self.selected_id=self.rows[0]['id'] if self.rows else None
            self.model.message='LIBRARY READY' if result['kind'] in ('loops','recordings') else 'NAME SAVED' if result['kind']=='rename' else 'DELETED / STORAGE RECLAIMED'
    def manager_mutation(self,event):
        return event['kind']=='cc' and event['channel']==0 and bool(event['value']) and ((self.model.view=='key' and event['number']==27 and self.key_draft is not None and tuple(self.key_draft)!=(self.model.state.root,self.model.state.scale)) or (self.model.view=='library' and self.confirm and self.confirm['action']=='load' and event['number']==27))
    def management_event(self,number,value,delta):
        """Return True when page consumes a control; global controls pass through."""
        m=self.model;view=m.view
        if view=='key':
            if self.key_draft is None:self.key_draft=[m.state.root,m.state.scale]
            if 71<=number<=78:
                index=number-71;step=self.slow[index].step(delta)
                if index==0:self.key_draft[0]=max(60,min(71,self.key_draft[0]+step))
                elif index==1:self.key_draft[1]=tuple(MODES)[max(0,min(6,tuple(MODES).index(self.key_draft[1])+step))]
                return True
            if not value:return number in range(102,110) or number in range(20,28)
            if 102<=number<=108:self.key_draft[1]=tuple(MODES)[number-102];return True
            if number==109:self.open_page(self.return_view);return True
            if number==26:self.key_draft=[m.state.root,m.state.scale];return True
            if number==27:
                if self.performance.rekey(*self.key_draft):m.message='KEY APPLIED / UNDO TO RESTORE'
                return True
            if 20<=number<=27:return True
            return False
        if view not in ('library','recordings'):return False
        if number in range(71,79):
            index=number-71;step=self.slow[index].step(delta)
            if self.rename is not None:
                if index==0:self.rename_cursor=max(0,min(len(self.rename),self.rename_cursor+step))
                elif index==1:self.character=max(0,min(len(ALPHABET)-1,self.character+step))
            elif index==0 and not self.confirm:self.select_row(step)
            return True
        owned=number in range(20,28) or number in range(102,110) or number in (62,63,118)
        if not owned:return False
        if not value:return True
        if self.rename is not None:
            if number==20:
                if len(self.rename)<24:self.rename=self.rename[:self.rename_cursor]+ALPHABET[self.character]+self.rename[self.rename_cursor:];self.rename_cursor+=1
            elif number==21:
                if len(self.rename)<24:self.rename=self.rename[:self.rename_cursor]+' '+self.rename[self.rename_cursor:];self.rename_cursor+=1
            elif number==22 and self.rename_cursor:
                self.rename=self.rename[:self.rename_cursor-1]+self.rename[self.rename_cursor:];self.rename_cursor-=1
            elif number==26:self.rename=None
            elif number==27:
                self.manager_task('rename',row=self.rename_row,label=self.rename);self.rename=None
            return True
        if self.confirm:
            if number==26:self.confirm=None
            elif number==27:
                confirmation=self.confirm
                if confirmation['action']=='load':
                    self.performance.stop();self.transition=('load',confirmation['row']);m.message='ARCHIVING CURRENT / LOADING'
                else:self.manager_task('delete_loop' if view=='library' else 'delete_recording',row=confirmation['row'])
                self.confirm=None
            return True # Delete again cannot confirm.
        if number in (62,63):self.select_row(-4 if number==62 else 4);return True
        if number==109 or number==27:self.open_page(self.return_view);return True
        if view=='recordings':
            if number in (104,105):
                self.record_tab='current' if number==104 else 'saved'
                if self.record_tab=='saved':self.refresh_manager()
                return True
            if self.record_tab=='current':
                if number==20:
                    if not self.recorder:raise ValueError('Video unavailable')
                    self.recorder.start();m.message='FILM RECORDING / MUSIC INDEPENDENT'
                elif number==21:
                    if not self.recorder:raise ValueError('Video unavailable')
                    self.recorder.stop();m.message='SAVING MP4 / KEEP PLAYING'
                elif number==22:self.export.request(m.revision,bool(m.pending) or bool(self.performance.structural))
                elif number==23:self.bottle.request(30)
                elif number==24:self.record_tab='saved';self.refresh_manager()
                elif number==25:self.details=not self.details
                return True
            if number==20:self.refresh_manager()
            elif number==21:self.details=not self.details
            elif number==22:
                row=self.selected_row()
                if row and row.get('recoverable'):self.recorder.recover(row['id']);m.message='RECOVERING FILM / KEEP PLAYING'
                else:raise ValueError('No recoverable film selected')
            elif number in (23,118):self.ask_delete()
        else:
            if number==20:m.request_save()
            elif number==21:
                row=self.selected_row()
                if not row:raise ValueError('Select a saved loop')
                if row['status']!='READY':raise ValueError('Selected loop is invalid')
                self.confirm=dict(action='load',row=dict(row))
            elif number==22:
                row=self.selected_row()
                if not row:raise ValueError('Select a saved loop')
                self.rename_row=dict(row);self.rename=row['name'].upper()[:24];self.rename_cursor=len(self.rename)
            elif number in (23,118):self.ask_delete()
            elif number==24:self.refresh_manager()
            elif number==25:self.details=not self.details
        return True
    def ask_delete(self):
        if self.manager_busy:raise ValueError('Library busy; wait')
        row=self.selected_row()
        if not row:raise ValueError('Select a saved item')
        self.confirm=dict(action='delete',row=dict(row))
    def manager_status(self):
        return dict(generation=self.page_generation,busy=self.manager_busy,selected_id=self.selected_id,rows=self.rows,
                    confirm=self.confirm,rename=self.rename,record_tab=self.record_tab,key_draft=self.key_draft,
                    collisions=self.pitch_lights.collisions)
