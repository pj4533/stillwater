"""One asynchronous retrospective render-output capture; no music-state mutation."""
import copy
import ctypes as C
import errno
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import threading
import time
import wave

SR=44100
MAX_SECONDS=30


def publish(temp,final):
    """Atomic no-replace rename on Linux; link/unlink fallback also never overwrites."""
    libc=C.CDLL(None,use_errno=True)
    rename=getattr(libc,'renameat2',None)
    if rename:
        rename.argtypes=[C.c_int,C.c_char_p,C.c_int,C.c_char_p,C.c_uint];rename.restype=C.c_int
        if rename(-100,os.fsencode(temp),-100,os.fsencode(final),1)==0:return
        error=C.get_errno()
        if error not in (errno.ENOSYS,errno.EINVAL):raise OSError(error,os.strerror(error))
    # Publication succeeds as soon as the link exists. Cleanup belongs to the
    # worker, so an unlink failure cannot hide a successfully saved WAV.
    os.link(temp,final)


class Bottle:
    def __init__(self,engine,directory):
        self.engine=engine;self.directory=Path(directory);self.worker=None;self.job=0;self.closed=False;self.lifecycle=threading.Lock()
        self.status=dict(job=0,state='idle',busy=False,filename=None,seconds=0,frames=0,progress=0,error=None)
    def snapshot(self):
        status=copy.deepcopy(self.status)
        status['busy']=status['busy'] or bool(self.worker and self.worker.is_alive())
        status['available_seconds']=min(30,self.engine.lib.sw_history_end()/SR)
        return status
    def execute(self,req):
        if not isinstance(req,dict):raise ValueError('object required')
        if req==dict(op='query_capture_status'):return self.snapshot()
        if set(req)!={'op','seconds'} or req['op']!='request_capture':raise ValueError('invalid capture operation or fields')
        return self.request(req['seconds'])
    def request(self,seconds=30):
        if type(seconds) is not int or not 1<=seconds<=MAX_SECONDS:raise ValueError('capture seconds must be integer1..30')
        # This lock is UI/worker lifecycle only; native render never touches it.
        with self.lifecycle:
            if self.closed:raise ValueError('Bottle is shutting down')
            if self.status['busy'] or (self.worker and self.worker.is_alive()):raise ValueError('Bottle is busy; query capture status')
            epoch,start,count=self.engine.history_window(seconds)
            if not count:raise ValueError('No output history yet')
            # Snapshot endpoints are fixed here, not later when worker scheduling begins.
            self.job+=1
            self.status=dict(job=self.job,state='filling',busy=True,filename=None,seconds=count/SR,frames=count,progress=.1,error=None)
            self.worker=threading.Thread(target=self._save,args=(epoch,start,count),name='stillwater-bottle',daemon=True)
            try:self.worker.start()
            except RuntimeError as exc:
                self.status=dict(self.status,state='error',busy=False,error=str(exc)[:160]);raise ValueError('Bottle worker could not start') from exc
            return self.snapshot()
    def filename(self):return 'bottle-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime())+'-'+secrets.token_hex(3)+'.wav'
    def _save(self,epoch,start,count):
        status=self.snapshot();temp=final=None;published=False;warning=None;outcome=None
        try:
            self.directory.mkdir(parents=True,exist_ok=True)
            if shutil.disk_usage(self.directory).free<count*4+44+1024*1024:raise OSError(errno.ENOSPC,'Not enough free space for this bottle')
            data=self.engine.history_copy(epoch,start,count)
            self.status=dict(status,progress=.65)
            fd,name=tempfile.mkstemp(prefix='.bottle-',suffix='.part',dir=self.directory);temp=Path(name)
            with os.fdopen(fd,'wb') as stream:
                with wave.open(stream,'wb') as wav:
                    wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(SR)
                    wav.writeframes(memoryview(data).cast('B'))
                stream.flush();os.fsync(stream.fileno())
            self.status=dict(status,progress=.9)
            final=self.directory/self.filename();publish(temp,final);published=True
            directory=os.open(self.directory,os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
            outcome=dict(status,state='corked',filename=final.name,progress=1,completed_at=time.monotonic())
        except Exception as exc:
            if published:
                # A complete file is already visible. Report it honestly; never
                # remove a pathname another process could have replaced.
                outcome=dict(status,state='corked',filename=final.name,progress=1,completed_at=time.monotonic())
                warning='Saved; directory durability not confirmed: '+str(exc)[:120]
            else:outcome=dict(status,state='error',progress=0,error=str(exc)[:160])
        finally:
            if temp:
                try:temp.unlink(missing_ok=True)
                except OSError as exc:warning=(warning+'; ' if warning else '')+'Temporary cleanup failed: '+str(exc)[:120]
            # Keep busy and worker ownership until all cleanup has completed.
            self.status=dict(outcome,busy=False,warning=warning)
    def close(self,timeout=3):
        # Close admission before waiting, retaining the sole owned worker even
        # while cleanup stalls. A daemon cannot hold hardware shutdown forever.
        with self.lifecycle:
            self.closed=True;worker=self.worker
        if worker:worker.join(timeout=max(0,timeout))
