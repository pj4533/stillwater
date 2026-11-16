"""Sample-clock screen/output recording. UI admission only; all I/O is worker-owned."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time

from bottle import publish

SR=44100
TICK=4410
FRAME_BYTES=1024*160*2
MAX_FRAMES=SR*1800
RESERVE=512*1024*1024
ADMISSION=1024*1024*1024
JOB=re.compile(r'film-[0-9a-f]{12}')
FILTER='crop=960:160:0:0,scale=iw:ih:in_range=full:out_range=tv:out_color_matrix=bt709,setsar=1,format=yuv420p'


def checkpoint(path,data):
    temp=path.with_suffix('.tmp')
    with temp.open('w') as stream:
        json.dump(data,stream,allow_nan=False);stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)
    directory=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(directory)
    finally:os.close(directory)


def encoder_argv(tool,video,audio,output,samples):
    return ['nice','-n','15',*tool,'-nostdin','-hide_banner','-loglevel','error','-n','-filter_threads','1',
            '-f','rawvideo','-pixel_format','bgr565le','-video_size','1024x160','-framerate','10','-i',str(video),
            '-f','s16le','-ar','44100','-ac','2','-i',str(audio),'-map','0:v:0','-map','1:a:0','-vf',FILTER,
            '-c:v','libx264','-preset','veryfast','-crf','18','-threads:v','1','-profile:v','main','-level:v','3.1',
            '-bf','0','-g','20','-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709',
            '-c:a','aac','-b:a','160k','-ar','44100','-ac','2','-t','%.9f'%(samples/SR),'-movflags','+faststart','-f','mp4',str(output)]


class SessionRecorder:
    def __init__(self,engine,directory,ffmpeg=None,ffprobe=None):
        self.engine=engine;self.directory=Path(directory)
        self.ffmpeg=list(ffmpeg or ['/usr/bin/ffmpeg']);self.ffprobe=list(ffprobe or ['/usr/bin/ffprobe'])
        self.lock=threading.Lock();self.process_lock=threading.Lock();self.worker=None;self.closed=False;self.process=None
        self.status=dict(state='idle',busy=False,job=None,seconds=0,error=None,warning=None,filename=None)
        self.visible=None;self.q=None;self.stop_event=threading.Event();self.cancel=threading.Event()
        self.endpoint=None;self.failure=None;self.started=0;self.epoch=0;self.last_clock=0
        # Startup only, before UI loop: no encoding/resumption of interrupted jobs.
        jobs=self.directory/'jobs'
        if jobs.is_symlink():raise ValueError('Symlink job directory is not allowed')
        if jobs.exists():
            for path in jobs.iterdir():
                if not JOB.fullmatch(path.name) or path.is_symlink():continue
                meta=path/'metadata.json'
                try:
                    if meta.is_symlink():continue
                    data=json.loads(meta.read_text())
                    if data.get('state') in ('recording','saving','recovering'):
                        data.update(state='interrupted',error='Interrupted; recover this job explicitly')
                        checkpoint(meta,data)
                except (OSError,ValueError):pass
    def clock(self):
        epoch=self.engine.lib.sw_history_epoch();end=self.engine.lib.sw_history_end()
        if epoch!=self.engine.lib.sw_history_epoch():raise ValueError('Audio clock reset; try again')
        return epoch,end
    def snapshot(self):
        status=copy.deepcopy(self.status)
        status['busy']=status['busy'] or bool(self.worker and self.worker.is_alive())
        if status['state']=='recording':
            status['seconds']=max(0,min(1800,(self.engine.lib.sw_history_end()-self.started)/SR))
        if status['state']=='recording' and self.stop_event.is_set():status['state']='saving'
        if status['state']=='saving':status['encoding_seconds']=max(0,time.monotonic()-status.get('encoding_started',time.monotonic()))
        return status
    def execute(self,req):
        if not isinstance(req,dict):raise ValueError('object required')
        if req==dict(op='record_status'):return self.snapshot()
        if req==dict(op='record_start'):return self.start()
        if req==dict(op='record_stop'):return self.stop()
        if set(req)=={'op','job'} and req['op']=='record_recover':return self.recover(req['job'])
        raise ValueError('Invalid recording operation or fields')
    def _admit(self):
        if self.closed:raise ValueError('Recorder is shutting down')
        if self.status['busy'] or (self.worker and self.worker.is_alive()):raise ValueError('Video busy; wait for saving')
    def start(self):
        with self.lock:
            self._admit()
            if self.visible is None:raise ValueError('Wait for a displayed frame, then Record')
            self.epoch,self.started=self.clock();self.last_clock=self.started
            self.q=queue.Queue(8);self.stop_event=threading.Event();self.cancel=threading.Event();self.endpoint=None;self.failure=None
            self.xrun=self.engine.stats()['xruns'];initial=self.visible
            job='film-'+secrets.token_hex(6)
            self.status=dict(state='recording',busy=True,job=job,seconds=0,error=None,warning=None,filename=None)
            self._launch(self._capture,(job,initial))
            return self.snapshot()
    def _launch(self,target,args):
        self.worker=threading.Thread(target=target,args=args,name='stillwater-film',daemon=True)
        try:self.worker.start()
        except RuntimeError as exc:
            self.worker=None;self.status=dict(self.status,state='error',busy=False,error=str(exc)[:160])
            raise ValueError('Video worker could not start; retry') from exc
    def displayed(self,frame):
        # Called only AFTER successful hardware send. Immutable bytes, no I/O.
        if not isinstance(frame,bytes) or len(frame)!=FRAME_BYTES:raise ValueError('Padded1024x160 BGR565 frame required')
        with self.lock:
            self.visible=frame
            if self.status['state']!='recording' or self.stop_event.is_set():return
            try:
                epoch,end=self.clock()
                if epoch!=self.epoch:raise ValueError('Audio epoch reset')
                self.q.put_nowait((end,frame))
            except queue.Full:self.failure='Display queue overflow; partial job retained';self.stop_event.set()
            except ValueError as exc:self.failure=str(exc);self.stop_event.set()
    def stop(self):
        with self.lock:
            if self.status['state']!='recording' or self.stop_event.is_set():raise ValueError('No active video recording')
            epoch,end=self.clock()
            if epoch!=self.epoch:self.failure='Audio epoch reset'
            self.endpoint=min(end,self.started+MAX_FRAMES);self.stop_event.set()
            return self.snapshot()
    def _check(self):
        if self.cancel.is_set():raise RuntimeError('Shutdown interrupted video; recover job explicitly')
        if self.failure:raise RuntimeError(self.failure)
        if self.engine.lib.sw_history_epoch()!=self.epoch:raise RuntimeError('Audio epoch reset; partial job retained')
        if self.engine.stats()['xruns']!=self.xrun:raise RuntimeError('Audio xrun; partial job retained')
    def _capture(self,job,initial):
        path=self.directory/'jobs'/job;meta=None;audio=video=journal=None
        cursor=self.started;tick=self.started;current=initial;watermark=self.started;video_count=0;last_checkpoint=last_fsync=time.monotonic();last_progress=time.monotonic();warning=None
        data=dict(version=1,job=job,state='recording',epoch=self.epoch,start=self.started,endpoint=None,audio_frames=0,video_frames=0,display_frames=0,xruns_start=self.xrun,error=None)
        def commit(durable=False):
            nonlocal last_checkpoint,last_fsync
            for stream in (audio,video,journal):
                stream.flush()
                if durable:os.fsync(stream.fileno())
            # Audio may lead the latest display watermark. Checkpoint only
            # the prefix already covered by complete normalized video frames.
            committed=min(cursor-self.started,video_count*TICK)
            data.update(audio_frames=committed,video_frames=video_count,endpoint=self.started+committed,xruns_end=self.engine.stats()['xruns'])
            checkpoint(meta,data);last_checkpoint=time.monotonic()
            if durable:last_fsync=last_checkpoint
        def audio_to(end):
            nonlocal cursor,last_progress
            while cursor<end:
                self._check()
                if shutil.disk_usage(path).free<RESERVE:raise OSError('Disk reserve reached; partial job retained')
                n=min(SR,end-cursor);pcm=self.engine.history_copy(self.epoch,cursor,n)
                if audio.write(memoryview(pcm).cast('B'))!=n*4:raise OSError('Short PCM write')
                cursor+=n;last_progress=time.monotonic()
        def video_to(end):
            nonlocal tick,video_count
            while tick<end:
                self._check()
                if video.write(current)!=FRAME_BYTES:raise OSError('Short video write')
                tick+=TICK;video_count+=1
        try:
            path.mkdir(parents=True,exist_ok=False);meta=path/'metadata.json'
            if shutil.disk_usage(path).free<ADMISSION:raise OSError('Need1GiB free to start video')
            audio=(path/'audio.s16le').open('xb');video=(path/'screen.bgr565').open('xb');journal=(path/'frames.jsonl').open('x')
            checkpoint(meta,data)
            journal.write(json.dumps(dict(sample=self.started,initial=True,sha256=hashlib.sha256(current).hexdigest()))+'\n')
            while True:
                self._check()
                epoch,end=self.clock()
                if epoch!=self.epoch:raise RuntimeError('Audio epoch reset')
                with self.lock:
                    if end>=self.started+MAX_FRAMES and not self.stop_event.is_set():
                        self.endpoint=self.started+MAX_FRAMES;self.stop_event.set()
                try:item=self.q.get(timeout=.02)
                except queue.Empty:item=None
                if item:
                    stamp,frame=item
                    if stamp<watermark:raise RuntimeError('Display clock moved backwards')
                    if self.endpoint is None or stamp<=self.endpoint:
                        stamp=min(stamp,self.started+MAX_FRAMES)
                        audio_to(stamp);video_to(stamp);current=frame;watermark=stamp
                        journal.write(json.dumps(dict(sample=stamp,sha256=hashlib.sha256(frame).hexdigest()))+'\n');data['display_frames']+=1
                if self.stop_event.is_set() and self.q.empty():
                    if self.endpoint is None:raise RuntimeError(self.failure or 'Recording interrupted')
                    audio_to(self.endpoint);video_to(self.endpoint);break
                # Copy continuously, even between USB frames, but defer video
                # ticks until their display watermark is known (ties use latest).
                audio_to(min(end,self.started+MAX_FRAMES,self.endpoint if self.endpoint is not None else end))
                if time.monotonic()-last_progress>3:raise RuntimeError('Audio clock stalled; partial job retained')
                if time.monotonic()-last_checkpoint>=1:commit(time.monotonic()-last_fsync>=5)
            if cursor==self.started:raise RuntimeError('No audio elapsed; nothing to save')
            data['state']='saving';commit(True)
            for stream in (audio,video,journal):stream.close()
            self.status=dict(self.status,state='saving',seconds=(cursor-self.started)/SR,encoding_started=time.monotonic())
            warning=self._encode(path,data)
            result=self._ready(path,data,warning)
        except Exception as exc:
            # Recover only a prefix with both known display and committed audio.
            prefix=min(cursor,watermark);count=max(0,prefix-self.started)
            try:
                if audio and not audio.closed:
                    audio.truncate(count*4);video.truncate(min(video_count,math.ceil(count/TICK))*FRAME_BYTES)
                    cursor=prefix;video_count=min(video_count,math.ceil(count/TICK))
                    data.update(state='interrupted' if self.cancel.is_set() else 'error',error=str(exc)[:200]);commit(True)
                elif meta and meta.exists():
                    data.update(state='interrupted' if self.cancel.is_set() else 'error',error=str(exc)[:200]);checkpoint(meta,data)
            except OSError:pass
            result=dict(self.status,state='error',error=str(exc)[:160],seconds=data.get('audio_frames',0)/SR)
        finally:
            for stream in (audio,video,journal):
                if stream and not stream.closed:
                    try:stream.close()
                    except OSError:pass
            self.status=dict(result,busy=False)
    def _run(self,argv,path,timeout,label):
        # File-backed output avoids pipe deadlock or unbounded Python buffers.
        with (path/(label+'.stdout')).open('wb') as out,(path/(label+'.stderr')).open('wb') as err:
            with self.process_lock:
                if self.closed or self.cancel.is_set():raise RuntimeError('Video shutdown')
                proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,close_fds=True)
                self.process=proc
            deadline=time.monotonic()+timeout;space_checked=0
            try:
                while proc.poll() is None:
                    if time.monotonic()-space_checked>=1:
                        if shutil.disk_usage(path).free<RESERVE:raise RuntimeError('Disk reserve reached during '+label)
                        space_checked=time.monotonic()
                    if self.cancel.wait(.05) or time.monotonic()>deadline:raise RuntimeError(label+' cancelled or timed out')
                if proc.returncode:
                    with (path/(label+'.stderr')).open('rb') as stream:stream.seek(max(0,stream.seek(0,2)-1000));message=stream.read().decode(errors='replace')
                    raise RuntimeError(label+' failed: '+message[-180:])
            finally:
                if proc.poll() is None:self._terminate(proc,.3)
                with self.process_lock:
                    if self.process is proc:self.process=None
    @staticmethod
    def _terminate(proc,grace):
        if proc.poll() is not None:return
        try:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:return
        try:proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:proc.wait(timeout=.3)
            except subprocess.TimeoutExpired:pass
    @staticmethod
    def _identity(output):
        if output.is_symlink():raise ValueError('Symlink video output is not allowed')
        digest=hashlib.sha256()
        with output.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        return dict(filename=output.name,size=output.stat().st_size,sha256=digest.hexdigest())
    def _verify(self,path,output,samples):
        self._run([*self.ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(output)],path,30,'probe')
        info=json.loads((path/'probe.stdout').read_text());streams=info['streams'];v=next(s for s in streams if s['codec_type']=='video');a=next(s for s in streams if s['codec_type']=='audio')
        if not (v['codec_name']=='h264' and v['width']==960 and v['height']==160 and v.get('sample_aspect_ratio')=='1:1' and v['r_frame_rate']=='10/1' and a['codec_name']=='aac' and a['sample_rate']=='44100' and a['channels']==2):raise RuntimeError('Encoded stream validation failed')
        if abs(float(info['format']['duration'])-samples/SR)>.15 or output.stat().st_size<100:raise RuntimeError('Encoded duration/size validation failed')
        self._run([*self.ffmpeg,'-nostdin','-v','error','-xerror','-err_detect','explode','-threads','1','-i',str(output),'-f','null','-'],path,300,'decode')
    def _encode(self,path,data):
        samples=data['audio_frames'];final=self.directory/(data['job']+'.mp4')
        # The durable identity precedes publication. A restart can recognize only
        # this exact verified output; a different writer's file is never adopted.
        if final.exists() or final.is_symlink():
            expected=data.get('publication')
            if not expected or expected!=self._identity(final):raise FileExistsError('Video output collision; existing file preserved')
            self._verify(path,final,samples)
            return self._sync_directory()
        output=path/('encode-'+secrets.token_hex(6)+'.part')
        self._run(encoder_argv(self.ffmpeg,path/'screen.bgr565',path/'audio.s16le',output,samples),path,3600,'encode')
        self._verify(path,output,samples)
        with output.open('rb') as stream:os.fsync(stream.fileno())
        data['publication']=dict(self._identity(output),filename=final.name)
        checkpoint(path/'metadata.json',data)
        publish(output,final)
        warning=self._sync_directory()
        try:output.unlink(missing_ok=True)
        except OSError as exc:warning=(warning+'; ' if warning else '')+'Temporary cleanup failed: '+str(exc)[:100]
        return warning
    def _sync_directory(self):
        warning=None
        try:
            directory=os.open(self.directory,os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
        except OSError as exc:warning='Saved; directory durability unconfirmed: '+str(exc)[:100]
        return warning
    def _ready(self,path,data,warning):
        data.update(state='ready',filename=data['job']+'.mp4',warning=warning)
        try:checkpoint(path/'metadata.json',data)
        except OSError as exc:warning=(warning+'; ' if warning else '')+'Saved; metadata checkpoint failed: '+str(exc)[:100]
        return dict(self.status,state='ready',filename=data['filename'],warning=warning,error=None,completed_at=time.monotonic())
    def recover(self,job):
        if not isinstance(job,str) or not JOB.fullmatch(job):raise ValueError('Invalid controlled video job ID')
        with self.lock:
            self._admit();self.cancel=threading.Event()
            self.status=dict(state='saving',busy=True,job=job,seconds=0,encoding_started=time.monotonic(),filename=None,error=None,warning=None)
            self._launch(self._recover,(job,));return self.snapshot()
    def _load_recovery(self,job):
        path=self.directory/'jobs'/job
        for entry in (self.directory/'jobs',path,path/'metadata.json',path/'audio.s16le',path/'screen.bgr565'):
            if entry.is_symlink():raise ValueError('Symlink recovery is not allowed')
        try:
            data=json.loads((path/'metadata.json').read_text());n=data['audio_frames'];v=data['video_frames']
            if not (data['version']==1 and data['job']==job and data['state'] in ('interrupted','error') and type(n) is int and 0<n<=MAX_FRAMES and type(v) is int and v==math.ceil(n/TICK) and type(data['start']) is int and data['start']>=0 and data['endpoint']==data['start']+n and (path/'audio.s16le').stat().st_size>=n*4 and (path/'screen.bgr565').stat().st_size>=v*FRAME_BYTES):raise ValueError('No complete recoverable AV prefix')
        except (OSError,KeyError,TypeError,ValueError) as exc:raise ValueError('No complete recoverable AV prefix') from exc
        return path,data
    def _recover(self,job):
        data=path=None
        try:
            path,data=self._load_recovery(job)
            self.status=dict(self.status,seconds=data['audio_frames']/SR)
            data['state']='recovering';checkpoint(path/'metadata.json',data)
            warning=self._encode(path,data);result=self._ready(path,data,warning)
        except Exception as exc:
            if data:
                data.update(state='error',error=str(exc)[:200])
                try:checkpoint(path/'metadata.json',data)
                except OSError:pass
            result=dict(self.status,state='error',error=str(exc)[:160])
        self.status=dict(result,busy=False)
    def close(self,timeout=1.5):
        deadline=time.monotonic()+timeout
        with self.lock:
            self.closed=True;self.cancel.set();self.stop_event.set();worker=self.worker
        # Process creation never holds the UI admission/frame lock.
        acquired=self.process_lock.acquire(timeout=max(0,deadline-time.monotonic()))
        if acquired:
            try:proc=self.process
            finally:self.process_lock.release()
            if proc:self._terminate(proc,min(.3,max(0,deadline-time.monotonic())))
        if worker:worker.join(max(0,deadline-time.monotonic()))
