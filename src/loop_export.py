"""One bounded worker streams exactly the next complete native loop to WAV.

Only reads the existing post-limiter history. Never submits audio commands.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import threading
import time
import wave
from bottle import publish

SR=44100

class LoopExport:
    def __init__(self,engine,directory):
        self.engine=engine;self.directory=Path(directory);self.worker=None;self.closed=False;self.cancel=threading.Event()
        self.status=dict(state='idle',busy=False,error=None,filename=None)
    def snapshot(self):return dict(self.status)
    def request(self,revision,pending=False):
        if self.closed or (self.worker and self.worker.is_alive()):raise ValueError('Loop export busy')
        s=self.engine.loop_stats()
        if pending or s['held'] or s['pending'] or s['transport']!=2 or s['pending_tempo']:raise ValueError('Release pads / finish takes / start loop before export')
        epoch=self.engine.lib.sw_history_epoch();xruns=self.engine.stats()['xruns']
        start=s['boundary']+s['loop_frames'];end=start+s['loop_frames']
        self.cancel=threading.Event();self.status=dict(state='armed',busy=True,error=None,filename=None,start=start,end=end,revision=revision)
        self.worker=threading.Thread(target=self._save,args=(s,epoch,xruns,start,end,revision),name='stillwater-loop-export',daemon=True)
        self.worker.start();return self.snapshot()
    def _save(self,baseline,epoch,xruns,start,end,revision):
        temp=side=None;final=None;published=False
        try:
            self.directory.mkdir(parents=True,exist_ok=True)
            if shutil.disk_usage(self.directory).free<(end-start)*4+512*1024*1024:raise OSError('Loop export needs free disk reserve')
            name='loop-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime())+'-'+secrets.token_hex(6)
            temp=self.directory/('.'+name+'.wav.part');side=self.directory/('.'+name+'.json.part');final=self.directory/(name+'.wav')
            cursor=start;digest=hashlib.sha256();deadline=time.monotonic()+70
            with temp.open('xb') as stream:
                with wave.open(stream,'wb') as wav:
                    wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(SR)
                    while cursor<end:
                        if self.cancel.is_set():raise ValueError('Loop export cancelled during shutdown')
                        if time.monotonic()>deadline:raise ValueError('Loop export timed out')
                        s=self.engine.loop_stats()
                        if (s['activity']!=baseline['activity'] or s['epoch']!=baseline['epoch'] or s['transport']!=2 or self.engine.stats()['xruns']!=xruns or self.engine.lib.sw_history_epoch()!=epoch):raise ValueError('Music changed / export cancelled / try again')
                        # Snapshot publication follows complete history publication. Do not
                        # consume a block whose configuration snapshot is not visible yet.
                        available=min(end,self.engine.lib.sw_history_end(),s['sample'])
                        if available<=cursor:self.cancel.wait(.005);continue
                        n=min(SR,available-cursor);pcm=self.engine.history_copy(epoch,cursor,n);raw=memoryview(pcm).cast('B')
                        wav.writeframesraw(raw);digest.update(raw);cursor+=n
                        self.status=dict(self.status,state='exporting',frames=cursor-start)
                    # A final coherent check also catches edits during the last copy.
                    s=self.engine.loop_stats()
                    if s['activity']!=baseline['activity'] or self.engine.stats()['xruns']!=xruns:raise ValueError('Music changed / export cancelled / try again')
                stream.flush();os.fsync(stream.fileno())
            metadata=dict(version=1,kind='stillwater-exact-loop',sample_rate=SR,channels=2,start=start,end=end,frames=end-start,pcm_sha256=digest.hexdigest(),history_epoch=epoch,native_epoch=baseline['epoch'],generation=baseline['generation'],activity=baseline['activity'],revision=revision,tempo=baseline['tempo'],xruns=xruns)
            with side.open('x') as stream:json.dump(metadata,stream,allow_nan=False);stream.flush();os.fsync(stream.fileno())
            publish(side,self.directory/(name+'.json'));publish(temp,final);published=True
            fd=os.open(self.directory,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
            self.status=dict(self.status,state='saved',busy=False,filename=final.name,pcm_sha256=digest.hexdigest())
        except Exception as exc:self.status=dict(self.status,state='saved' if published else 'error',busy=False,filename=final.name if published else None,error=str(exc)[:160])
        finally:
            for path in (temp,side):
                if path:
                    try:path.unlink(missing_ok=True)
                    except OSError:pass
    def close(self,timeout=1):
        self.closed=True;self.cancel.set()
        if self.worker:self.worker.join(max(0,timeout))
