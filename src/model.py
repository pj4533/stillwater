"""Versioned sessions and validated, undoable music operations. No network API."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import random

NAMES = ['Deep Tide', 'Warm Drift', 'Moon Pool', 'Slow Bloom', 'Soft Pebble', 'Cloud', 'Dusk Glow', 'Fireflies']
NOTES = [38, 50, 57, 62, 65, 50, 69, 74]
PARAMS = ('level', 'tone', 'decay')
STEPS = 8
SESSION_SCHEMA = 2
ENVELOPE_VERSION = 3


def finite(value, lo, hi):
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError('number outside [%s, %s]' % (lo, hi))
    return value


def integer(value, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError('invalid integer')
    return value


def seeded(seed=17):
    rng = random.Random(seed)
    patterns = [[0] * STEPS for _ in range(8)]
    for t, steps in enumerate([[0], [0, 10], [4, 12], [2, 11], [0, 7, 14], [0], [6], [5, 13]]):
        for s in steps:
            if s>=STEPS:continue
            patterns[t][s] = rng.choice([62,65,69,72,74] if t in (4,7) else [50,57,62,65,69]) if t>3 else NOTES[t]
    return dict(schema=SESSION_SCHEMA, tempo=58, master=.28, space=.38, root=62,
                tracks=[dict(name=n, level=[.45,.32,.24,.30,.26,.24,.23,.17][t], tone=.4, decay=.65,
                             pattern=patterns[t], muted=False) for t,n in enumerate(NAMES)])


GARDENS = ('Reed Choir', 'Lantern Pond', 'Moon Glass')


def garden(name):
    if name not in GARDENS:raise ValueError('unknown garden')
    index=GARDENS.index(name);s=seeded(31+index)
    s['tempo']=[52,58,46][index];s['space']=[.45,.38,.58][index]
    s['master']=[.25,.27,.23][index]
    for t,track in enumerate(s['tracks']):
        track['tone']=[.22,.38,.50][index]
        track['decay']=[.86,.65,.78][index]
        track['level']*= [1,.88,.80][index]
        if index==0 and t>3:track['pattern']=[n if i%2==0 else 0 for i,n in enumerate(track['pattern'])]
        if index==2 and t<2:track['pattern']=[0]*STEPS
    return s


def grown(state, seed):
    rng=random.Random(integer(seed,0,1000000));s=validate_session(state)
    notes=[n for t in s['tracks'] for n in t['pattern'] if n]
    lo,hi=(min(notes),max(notes)) if notes else (38,74)
    scale={0,2,3,5,7,9,10}
    allowed=[n for n in range(lo,hi+1) if (n-s['root'])%12 in scale]
    if not allowed:raise ValueError('current register contains no scale notes')
    for t,track in enumerate(s['tracks']):
        old=track['pattern'];positions=[i for i,n in enumerate(old) if n]
        count=max(1,min(3,len(positions)))
        # Retain the phrase's register and move one seed-driven ripple.
        positions=rng.sample(positions,count) if positions else [rng.randrange(STEPS)]
        chosen=rng.randrange(len(positions));positions[chosen]=(positions[chosen]+rng.choice([-2,-1,1,2,4]))%STEPS
        base=[n for n in old if n] or [NOTES[t]]
        low,high=min(base),max(base)
        pitches=[n for n in allowed if low<=n<=high] or [min(allowed,key=lambda n:abs(n-base[0]))]
        pattern=[0]*STEPS
        for pos in positions:pattern[pos]=rng.choice(pitches)
        track['pattern']=pattern
    return s


def validate_session(s):
    if not isinstance(s, dict) or set(s) != {'schema', 'tempo', 'master', 'space', 'root', 'tracks'} or s['schema'] != SESSION_SCHEMA:
        raise ValueError('unsupported session schema')
    finite(s['tempo'], 30, 160); finite(s['master'], 0, 1); finite(s['space'], 0, .8); integer(s['root'], 36, 84)
    if not isinstance(s['tracks'], list) or len(s['tracks']) != 8:
        raise ValueError('eight tracks required')
    for t in s['tracks']:
        if set(t) != {'name', 'level', 'tone', 'decay', 'pattern', 'muted'} or not isinstance(t['name'], str) or len(t['name']) > 24 or type(t['muted']) is not bool:
            raise ValueError('invalid track')
        for k in PARAMS: finite(t[k], 0, 1)
        validate_pattern(t['pattern'])
    return copy.deepcopy(s)


def validate_pattern(pattern, length=STEPS):
    if not isinstance(pattern, list) or len(pattern) != length:
        raise ValueError('%d steps required'%length)
    for n in pattern:
        integer(n, 0, 96)
        if 0 < n < 24: raise ValueError('note must be zero or MIDI 24..96')
    return list(pattern)


def normalize_saved_session(state):
    """Only persisted legacy scenes may shorten; new agent input is exactly8."""
    if isinstance(state,dict) and state.get('schema')==1:
        migrated=copy.deepcopy(state)
        # Validate all16 notes, including the discarded half, before preserving
        # and converting. The other controls still pass current validation.
        tracks=migrated.get('tracks')
        if not isinstance(tracks,list) or len(tracks)!=8:raise ValueError('eight tracks required')
        for track in tracks:
            if not isinstance(track,dict) or 'pattern' not in track:raise ValueError('invalid track')
            track['pattern']=validate_pattern(track['pattern'],16)[:STEPS]
        migrated['schema']=SESSION_SCHEMA
        return validate_session(migrated)
    return validate_session(state)


class Model:
    def __init__(self, path):
        self.path = Path(path)
        self.state = seeded()
        self.history = []
        self.revision = 0
        self.playing = False
        self.selected = 4
        self.page = 0
        self.mode = 'steps'
        self.view = 'instrument'
        self.master_until = 0
        self.control = None
        self.proposals = {}
        self.applied = set()
        self.message = 'PLAY: ambient demo | NOTE: play pads'
        self.journal_path = self.path.with_suffix('.history.json')
        self.migration_backup = None
        if self.path.exists():
            original=self.path.read_bytes();stored=json.loads(original)
            if stored.get('format')=='stillwater-session':
                if set(stored)!={'format','version','revision','state','history'} or stored['version'] not in (2,ENVELOPE_VERSION):
                    raise ValueError('unsupported session envelope')
                self._restore(stored)
                migrated=stored['version']!=ENVELOPE_VERSION or stored['state']!=self.state or stored['history']!=self.history
            else:
                # Compare full original pairs before normalizing; discarded steps
                # must never hide disagreement between an old state and journal.
                normalize_saved_session(stored)
                if not self.journal_path.exists():
                    raise ValueError('ambiguous legacy session: revision journal missing; files preserved')
                journal=json.loads(self.journal_path.read_text())
                if journal.get('state')!=stored:
                    raise ValueError('ambiguous legacy session: state/journal mismatch; files preserved')
                self._restore(journal);migrated=True
            if migrated:
                self._preserve_original(original)
                self.save()
                self.message='Migrated first eight steps; original and undo preserved'

    def _preserve_original(self, original):
        digest=hashlib.sha256(original).hexdigest()[:16]
        backup=self.path.with_name(self.path.stem+'.pre-eight-steps-'+digest+'.json')
        try:
            with open(backup,'xb') as f:
                f.write(original);f.flush();os.fsync(f.fileno())
        except FileExistsError:
            # A previous attempt may have flushed bytes but failed fsync.
            # Verify and sync the same open file before trusting it on retry.
            with open(backup,'rb') as f:
                if f.read()!=original:raise ValueError('migration backup mismatch')
                os.fsync(f.fileno())
        fd=os.open(self.path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        self.migration_backup=backup

    def _restore(self, stored):
        self.state=normalize_saved_session(stored['state'])
        self.revision=integer(stored['revision'],0,2**53)
        history=stored['history']
        if not isinstance(history,list) or len(history)>64:
            raise ValueError('invalid undo history')
        self.history=[normalize_saved_session(s) for s in history]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        envelope=dict(format='stillwater-session',version=ENVELOPE_VERSION,revision=self.revision,
                      state=self.state,history=self.history)
        with open(temp, 'w') as f:
            json.dump(envelope, f, allow_nan=False); f.flush(); os.fsync(f.fileno())
        os.replace(temp, self.path)
        fd = os.open(self.path.parent, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
        self.message = 'Saved locally'

    @property
    def preview(self):
        if not self.proposals:return None
        pid=next(reversed(self.proposals));p=self.proposals[pid]
        return dict(id=pid,kind=p['kind'],seed=p['seed'],
                    patterns=[list(t['pattern']) for t in p['state']['tracks']])

    def propose(self,pid,candidate,kind,seed=None):
        if not isinstance(pid,str) or not 1<=len(pid)<=64 or not all(c.isalnum() or c in '-_' for c in pid):raise ValueError('invalid proposal id')
        if pid in self.proposals or pid in self.applied:raise ValueError('duplicate proposal id')
        if len(self.proposals)>=32:raise ValueError('proposal limit')
        self.proposals[pid]=dict(revision=self.revision,state=validate_session(candidate),kind=kind,seed=seed)
        self.message='GROW PREVIEW - NEW: PLANT / UNDO: CANCEL' if kind=='grow' else 'Agent preview: '+pid

    def apply(self,pid,kind):
        if not isinstance(pid,str) or pid not in self.proposals:raise ValueError('unknown proposal')
        proposal=self.proposals[pid]
        if proposal['revision']!=self.revision or proposal['kind']!=kind:raise ValueError('stale or wrong proposal')
        self.commit(proposal['state'],'A new ripple planted' if kind=='grow' else 'Agent pattern applied')
        self.applied.add(pid)

    def snapshot(self):
        return dict(revision=self.revision, playing=self.playing, selected=self.selected,
                    page=self.page, mode=self.mode, view=self.view, session=copy.deepcopy(self.state), message=self.message,preview=self.preview,undo_depth=len(self.history))

    def commit(self, candidate, label):
        candidate = validate_session(candidate)
        old_state,old_history,old_revision=self.state,self.history,self.revision
        self.history=(self.history+[copy.deepcopy(self.state)])[-64:]
        self.state=candidate;self.revision+=1
        try:self.save()
        except OSError:
            self.state,self.history,self.revision=old_state,old_history,old_revision
            raise
        self.proposals.clear()
        self.message=label

    def execute(self, req):
        if not isinstance(req, dict): raise ValueError('object required')
        op = req.get('op')
        fields = {'query_state': {'op'}, 'set_tempo': {'op','value','revision'},
                  'set_master': {'op','value','revision'},
                  'set_track_parameters': {'op','track','parameters','revision'},
                  'propose_pattern': {'op','track','pattern','revision','id'},
                  'apply_pattern': {'op','id','revision'}, 'preset': {'op','seed','revision'},
                  'propose_grow': {'op','id','seed','revision'}, 'apply_grow': {'op','id','revision'},
                  'cancel_preview': {'op'}, 'garden': {'op','name','revision'},
                  'undo': {'op','revision'}, 'transport': {'op','playing'},
                  'save': {'op'}, 'event': {'op','kind','number','value'}}
        if op not in fields or set(req) != fields[op]: raise ValueError('unknown operation or fields')
        if 'revision' in req and integer(req['revision'],0,2**53) != self.revision: raise ValueError('stale revision')
        s=copy.deepcopy(self.state)
        if op == 'set_tempo': s['tempo']=finite(req['value'],30,160);self.commit(s,'Tempo updated')
        elif op == 'set_master':s['master']=finite(req['value'],0,1);self.commit(s,'Master output updated')
        elif op == 'set_track_parameters':
            t=integer(req['track'],0,7); params=req['parameters']
            if not isinstance(params,dict) or not params or not set(params)<=set(PARAMS)|{'muted'}: raise ValueError('invalid parameters')
            for k,v in params.items():
                if k=='muted':
                    if type(v) is not bool: raise ValueError('boolean required')
                else: finite(v,0,1)
                s['tracks'][t][k]=v
            self.commit(s,'Track updated')
        elif op == 'propose_pattern':
            t=integer(req['track'],0,7);pattern=validate_pattern(req['pattern']);pid=req['id']
            s['tracks'][t]['pattern']=pattern;self.propose(pid,s,'pattern')
        elif op == 'apply_pattern':self.apply(req['id'],'pattern')
        elif op == 'propose_grow':self.propose(req['id'],grown(s,req['seed']),'grow',req['seed'])
        elif op == 'apply_grow':self.apply(req['id'],'grow')
        elif op == 'cancel_preview':self.proposals.clear();self.message='Preview tucked away'
        elif op == 'garden':self.commit(garden(req['name']),req['name'])
        elif op == 'preset': self.commit(seeded(integer(req['seed'],0,1000000)),'New ambient scene')
        elif op == 'undo':
            if not self.history: raise ValueError('nothing to undo')
            old_state,old_history,old_revision=self.state,self.history,self.revision
            self.state=self.history[-1];self.history=self.history[:-1];self.revision+=1
            try:self.save()
            except OSError:
                self.state,self.history,self.revision=old_state,old_history,old_revision
                raise
            self.proposals.clear();self.message='Undone'
        elif op == 'transport':
            if type(req['playing']) is not bool: raise ValueError('boolean required')
            self.playing=req['playing']
        elif op=='save': self.save()
        elif op=='event':
            if req['kind'] not in ('cc','note'): raise ValueError('invalid event kind')
            integer(req['number'],0,127);integer(req['value'],0,127)
        return self.snapshot()


def pad_coord(note):
    integer(note,36,99)
    return (note-36)%8, (note-36)//8


def melodic_note(note,root):
    x,y=pad_coord(note); degree=x+y*3;scale=[0,2,3,5,7,9,10]
    return min(96,root+scale[degree%7]+12*(degree//7)-12)


def relative(value):
    integer(value,0,127)
    return value if value<64 else value-128
