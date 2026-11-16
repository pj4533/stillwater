"""Bounded, serialized appliance libraries. Only controlled IDs, never user paths.

UI requests pin inventory identity; workers validate again before mutations.
Film deletion intents survive interruption and permanently exclude recovery.
"""
import json
import os
from pathlib import Path
import queue
import re
import stat
import threading
import time
import wave
from loop_model import atomic_write,read_envelope,PITCH_NAMES

SONG=re.compile(r'song-[0-9a-f]{32}\.json')
FILM=re.compile(r'film-[0-9a-f]{12}')
WAV=re.compile(r'(?:loop-\d{8}-\d{6}-[0-9a-f]{12}|bottle-\d{8}-\d{6}-[0-9a-f]{6})\.wav')
ALPHABET=' ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.:'

def safe(path,directory=False):
    """Refuse links in all ancestors, even a replaced library root."""
    path=Path(path)
    for parent in (path,*path.parents):
        if parent.is_symlink():raise ValueError('Symlink library path refused')
    info=path.stat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):raise ValueError('Invalid library file type')
    return info

def load_json(path,limit=65536):
    safe(path)
    with Path(path).open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Library metadata too large')
    return json.loads(raw)

def identity(path,directory=False):
    s=safe(path,directory);return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns]

def sync(directory):
    fd=os.open(directory,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def tree(path):
    safe(path,True);total=0
    for root,dirs,files in os.walk(path,followlinks=False):
        for name in dirs:safe(Path(root)/name,True)
        for name in files:total+=safe(Path(root)/name).st_size
    return total

def remove_tree(path):
    # Preflight refuses all links before removing any part of the bundle.
    tree(path)
    for root,dirs,files in os.walk(path,topdown=False,followlinks=False):
        for name in files:(Path(root)/name).unlink()
        for name in dirs:(Path(root)/name).rmdir()
    path.rmdir()

class LibraryManager:
    def __init__(self,home,recorder=None,bottle=None,export=None):
        self.home=Path(home);self.recordings=self.home/'recordings';self.saved=self.home/'sessions/saved'
        self.recorder=recorder;self.bottle=bottle;self.export=export
        self.jobs=queue.Queue(4);self.results=queue.Queue(4);self.closing=threading.Event()
        self.thread=threading.Thread(target=self._run,name='stillwater-libraries',daemon=True);self.thread.start()
    def submit(self,kind,generation,**data):
        if self.closing.is_set():raise ValueError('Library shutting down')
        reserved=False
        if kind=='delete_recording' and self.recorder:
            with self.recorder.lock:
                self.recorder._admit()
                if any(w and w.snapshot().get('busy') for w in (self.bottle,self.export)):raise ValueError('Capture/export busy')
                self.recorder.manager_busy=True;reserved=True
        try:self.jobs.put_nowait((kind,generation,data,reserved))
        except Exception:
            if reserved:
                with self.recorder.lock:self.recorder.manager_busy=False
            raise
    def _run(self):
        if self.recorder:
            with self.recorder.lock:self.recorder.manager_busy=True
        try:self.retry_deletions()
        except Exception:pass # Inventory reports persisted incomplete intents.
        finally:
            if self.recorder:
                with self.recorder.lock:self.recorder.manager_busy=False
        while not self.closing.is_set():
            try:kind,generation,data,reserved=self.jobs.get(timeout=.1)
            except queue.Empty:continue
            try:result=dict(kind=kind,generation=generation,**self.work(kind,**data))
            except Exception as exc:result=dict(kind=kind,generation=generation,error=str(exc)[:160])
            finally:
                if reserved:
                    with self.recorder.lock:self.recorder.manager_busy=False
            while not self.closing.is_set():
                try:self.results.put(result,timeout=.1);break
                except queue.Full:pass
    def work(self,kind,**data):
        if kind=='loops':return dict(rows=self.loops())
        if kind=='recordings':return dict(rows=self.inventory())
        if kind in ('rename','delete_loop'):
            row=data['row'];name=row['id']
            if not SONG.fullmatch(name):raise ValueError('Invalid song ID')
            path=self.saved/name
            if identity(path)!=row['identity']:raise ValueError('Saved loop changed; refresh')
            meta=path.with_suffix('.name.json')
            if meta.exists() or meta.is_symlink():safe(meta)
            if kind=='rename':
                label=data['label']
                if not isinstance(label,str) or not 1<=len(label)<=24 or any(c not in ALPHABET for c in label) or not label.strip():raise ValueError('Use 1-24 visible ASCII characters')
                atomic_write(meta,dict(name=label.strip()))
            else:
                path.unlink();meta.unlink(missing_ok=True);sync(self.saved)
            return dict(rows=self.loops())
        if kind=='delete_recording':
            row=data['row'];self.delete_recording(row);return dict(rows=self.inventory())
        raise ValueError('Unknown library task')
    def loops(self):
        if not self.saved.exists():return []
        safe(self.saved,True);rows=[]
        for path in sorted(self.saved.iterdir(),reverse=True):
            if not SONG.fullmatch(path.name) or path.is_symlink():continue
            info=safe(path);label='LOOP '+time.strftime('%y-%m-%d %H:%M',time.localtime(info.st_mtime))+' '+path.stem[-4:]
            row=dict(id=path.name,name=label,identity=identity(path),created=info.st_mtime,bytes=info.st_size,status='READY')
            try:
                meta=path.with_suffix('.name.json')
                if meta.exists():safe(meta);label=load_json(meta)['name']
                if not isinstance(label,str) or len(label)>24 or any(c not in ALPHABET for c in label.upper()):raise ValueError('Invalid name')
                song=read_envelope(path)['state']
                row.update(name=label,key=PITCH_NAMES[song.root%12]+' '+song.scale.upper(),tempo=song.tempo,bars=song.loop_beats//4,layers=len(song.layers))
            except Exception as exc:row.update(status='ERROR',error=str(exc)[:80])
            rows.append(row)
            if len(rows)>=256:break
        return sorted(rows,key=lambda r:r['created'],reverse=True)
    def inventory(self):
        if not self.recordings.exists():return []
        safe(self.recordings,True);rows={}
        for path in self.recordings.iterdir():
            film=path.suffix=='.mp4' and FILM.fullmatch(path.stem)
            if not (film or WAV.fullmatch(path.name)) or path.is_symlink():continue
            s=safe(path);key=path.stem if film else path.name
            row=dict(id=key,name=path.name,type='FILM' if film else 'LOOP WAV' if path.name.startswith('loop-') else 'BOTTLE WAV',created=s.st_mtime,bytes=s.st_size,identity=identity(path),status='READY',seconds=None)
            if not film:
                try:
                    with wave.open(str(path),'rb') as w:row['seconds']=w.getnframes()/w.getframerate()
                except (OSError,wave.Error):row['status']='ERROR'
            rows[key]=row
            if len(rows)>=256:break
        jobs=self.recordings/'jobs'
        if jobs.exists():
            safe(jobs,True)
            for path in jobs.iterdir():
                if not FILM.fullmatch(path.name) or path.is_symlink():continue
                try:
                    raw=tree(path);meta=path/'metadata.json';safe(meta);data=load_json(meta)
                    if data.get('job')!=path.name:raise ValueError('Job ID mismatch')
                    row=rows.setdefault(path.name,dict(id=path.name,name=path.name+'.mp4',type='FILM',created=safe(path,True).st_mtime,bytes=0,identity=None,status='INTERRUPTED',seconds=None))
                    row.update(raw_identity=identity(path,True),raw_bytes=raw,bytes=row['bytes']+raw,seconds=data['audio_frames']/44100 if type(data.get('audio_frames')) is int and 0<data['audio_frames']<=44100*1800 else None,recoverable=data.get('state') in ('interrupted','error'),status='READY' if row['identity'] else {'recording':'RECORDING','saving':'SAVING MP4','recovering':'RECOVERING','interrupted':'INTERRUPTED'}.get(data.get('state'),'ERROR'))
                except Exception:
                    rows.setdefault(path.name,dict(id=path.name,name=path.name,type='FILM',created=0,bytes=0,identity=None,seconds=None)).update(status='ERROR',error='Unsafe or unreadable raw bundle')
                if len(rows)>=256:break
        intents=self.recordings/'.deleting'
        if intents.exists():
            safe(intents,True)
            for path in intents.iterdir():
                key=path.stem
                if FILM.fullmatch(key) or WAV.fullmatch(key):
                    rows.setdefault(key,dict(id=key,name=key,type='FILM' if FILM.fullmatch(key) else 'WAV',created=0,bytes=0,seconds=None,identity=None))['status']='DELETE INCOMPLETE'
        return sorted(rows.values(),key=lambda r:r['created'],reverse=True)[:256]
    def delete_recording(self,row):
        key=row['id'];film=bool(FILM.fullmatch(key))
        if not film and not WAV.fullmatch(key):raise ValueError('Invalid recording ID')
        final=self.recordings/(key+'.mp4' if film else key);raw=self.recordings/'jobs'/key
        if row.get('identity') is not None:
            if identity(final)!=row['identity']:raise ValueError('Recording changed; refresh')
        elif final.exists() or final.is_symlink():raise ValueError('Recording changed; refresh')
        if film and row.get('raw_identity') is not None:
            if identity(raw,True)!=row['raw_identity']:raise ValueError('Raw bundle changed; refresh')
            tree(raw)
        elif film and (raw.exists() or raw.is_symlink()):raise ValueError('Raw bundle changed; refresh')
        if row.get('status')=='ERROR' and not row.get('identity') and not row.get('raw_identity'):raise ValueError('Unsafe bundle; manual operator inspection required')
        intents=self.recordings/'.deleting';intents.mkdir(exist_ok=True);safe(intents,True)
        atomic_write(intents/(key+'.json'),dict(id=key,film=film,identity=row.get('identity'),raw_identity=row.get('raw_identity')))
        self.finish_delete(key)
    def finish_delete(self,key):
        intent=self.recordings/'.deleting'/(key+'.json');safe(intent);data=load_json(intent)
        film=bool(FILM.fullmatch(key))
        if data.get('id')!=key or (not film and not WAV.fullmatch(key)):raise ValueError('Invalid deletion intent')
        final=self.recordings/(key+'.mp4' if film else key)
        if final.exists() or final.is_symlink():
            if identity(final)!=data['identity']:raise ValueError('Deletion identity changed')
            final.unlink()
        if film:
            raw=self.recordings/'jobs'/key
            if raw.exists() or raw.is_symlink():
                # Directory mtime/size change during partial cleanup; pin dev+ino.
                if identity(raw,True)[:2]!=data['raw_identity'][:2]:raise ValueError('Deletion bundle identity changed')
                remove_tree(raw);sync(raw.parent)
        else:
            side=final.with_suffix('.json')
            if side.exists() or side.is_symlink():safe(side);side.unlink()
        sync(self.recordings);intent.unlink();sync(intent.parent)
    def retry_deletions(self):
        intents=self.recordings/'.deleting'
        if not intents.exists():return
        safe(intents,True)
        for path in intents.iterdir():
            if path.suffix=='.json' and (FILM.fullmatch(path.stem) or WAV.fullmatch(path.stem)):
                try:self.finish_delete(path.stem)
                except Exception:pass
    def close(self,timeout=1):
        self.closing.set();self.thread.join(timeout);return not self.thread.is_alive()
