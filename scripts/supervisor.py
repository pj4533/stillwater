#!/usr/bin/env python3
"""Exclusive-owner, quiet Stillwater retries; stock is an explicit escape only."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import health
import process


class Supervisor:
    def __init__(self,home,run=Path('/run'),clock=time.monotonic,sleep=time.sleep):
        self.home=Path(home);self.run_dir=Path(run);self.clock=clock;self.sleep=sleep
        self.shutdown=False;self.child=None;self.start=None;self.log=None
        process.REGISTRY=self.run_dir/'stillwater-owned.json'
    def status(self,state,reason='',attempt=0):
        data=dict(state=state,reason=reason,attempt=attempt,uptime=self.clock(),pid=self.child.pid if self.child else None)
        path=self.home/'recovery-status.json';temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(data));temp.replace(path)
        message='Stillwater: %s / %s / attempt %d'%(state,reason,attempt)
        print(message,flush=True)
        if self.log:self.log.write(message+'\n')
    def pause(self,seconds):
        end=self.clock()+seconds
        while not self.shutdown and self.clock()<end:self.sleep(min(.2,end-self.clock()))
    def launch(self,recovery,reason,attempt):
        for name in ('ready','return-stock','retry-stillwater'):(self.home/name).unlink(missing_ok=True)
        command=['/usr/bin/python3',str(self.home/('scripts/recovery.py' if recovery else 'src/app.py')),'--home',str(self.home)]
        if recovery:command+=['--reason',reason,'--attempt',str(attempt)]
        # Child cannot touch hardware until its PID/start is durable. If this
        # supervisor dies in the spawn/record window, EOF cancels the launch.
        gate='import os,sys; token=sys.stdin.buffer.read(1); os.execv(sys.argv[1],sys.argv[1:]) if token==b"G" else sys.exit(1)'
        self.child=subprocess.Popen(['/usr/bin/python3','-c',gate]+command,stdin=subprocess.PIPE,stdout=self.log,stderr=subprocess.STDOUT)
        self.start=process.identity(self.child.pid)
        try:
            process.record(os.getpid(),self.child.pid)
            self.child.stdin.write(b'G');self.child.stdin.flush()
        finally:self.child.stdin.close()
    def stop_child(self):
        if self.child is None:return True
        if self.start is None and self.child.poll() is None:return False
        if not process.terminate(self.child.pid,self.start):return False
        self.child.wait(timeout=1);self.child=None;self.start=None
        process.record(os.getpid());return True
    def monitor(self,recovery=False):
        start=self.clock();previous=None;healthy=False;failures=0;reason='startup timeout'
        while not self.shutdown:
            if (self.home/'return-stock').exists():return 'stock','explicit Settings / power request',False
            if recovery:
                if (self.home/'retry-stillwater').exists():return 'retry','explicit Play retry',False
            if self.child.poll() is not None:return 'fault','recovery exited' if recovery else 'application exited',healthy and self.clock()-start>=60
            if not recovery:
                if (self.home/'ready').exists() or healthy:
                    try:
                        m=json.loads((self.home/'metrics.json').read_text())
                        code,previous=health.assess(m,self.child.pid,self.start,self.clock(),previous)
                        if code==0:
                            if not healthy:self.status('ready','audio and display advancing');(self.home/'boot-pending').unlink(missing_ok=True)
                            healthy=True;failures=0
                        elif code==1:failures+=1;reason='audio or display progress stalled'
                    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
                        failures+=1;reason='health: '+str(exc)[:100]
                    if failures>=3:return 'fault',reason,healthy and self.clock()-start>=60
                if not healthy and self.clock()-start>=25:return 'fault',reason,False
            self.pause(1)
        return 'shutdown','shutdown requested',False
    def stock(self):
        self.status('stock','explicit request; hardware released')
        subprocess.run([str(self.home/'recovery/push3.stock'),'start'],check=True)
    def reconcile(self):
        """Release an orphan before replacing its durable ownership evidence."""
        if not process.REGISTRY.exists():return True
        try:
            data=json.loads(process.REGISTRY.read_text())
            owner=data['supervisor'];child=data.get('child')
            for entry in (owner,child):
                if entry is not None:
                    if not isinstance(entry,list) or len(entry)!=2 or type(entry[0]) is not int or entry[0]<=0:raise ValueError('invalid identity')
            # A live previous supervisor may still launch a child. Never steal
            # its registry, even if it predates the singleton lock.
            if owner[1] is None:
                if process.identity(owner[0]) is not None:return False
            elif process.alive(*owner):return False
            if child:
                if child[1] is None:
                    if process.identity(child[0]) is not None:return False
                elif not process.terminate(*child):return False
            return True
        except (OSError,ValueError,KeyError,TypeError):return False
    def run(self):
        self.run_dir.mkdir(parents=True,exist_ok=True)
        # Keep this inode permanently: unlinking a locked file allows a second
        # supervisor to lock a replacement inode while the first still owns USB.
        with open(self.run_dir/'stillwater-supervisor.lock','a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return 1
            return self.run_exclusive()
    def run_exclusive(self):
        self.home.mkdir(parents=True,exist_ok=True)
        self.log=open(self.home/'service.log','a',buffering=1)
        if not self.reconcile():
            self.status('ownership-blocked','prior owner not released; registry retained')
            self.log.close();return 1
        process.record(os.getpid())
        # Existing pending means an interrupted start, not permission to disable.
        attempt=0;recovery=False;reason='starting';failed_closed=False
        try:
            self.pause(max(0,35-self.clock()))
            while not self.shutdown:
                if not recovery:
                    attempt+=1;(self.home/'boot-pending').touch()
                self.status('recovery' if recovery else 'starting',reason,attempt)
                self.launch(recovery,reason,attempt)
                outcome,reason,reset=self.monitor(recovery)
                if not self.stop_child():
                    failed_closed=True;self.status('ownership-blocked','owned process did not release; no new owner',attempt);return 1
                if self.shutdown or outcome=='shutdown':break
                if outcome=='stock':self.stock();return 0
                if outcome=='retry':attempt=0;recovery=False;self.pause(1);continue
                if reset:attempt=0
                if recovery:
                    # Audio-free recovery failure (e.g. unavailable USB): retain
                    # preference, log honestly, avoid a display retry storm.
                    self.status('recovery-unavailable',reason,attempt);self.pause(30)
                else:
                    recovery=attempt>=3
                    self.status('recovering' if recovery else 'backoff',reason,attempt)
                    self.pause([1,3,8][min(attempt-1,2)])
            return 0
        finally:
            if not failed_closed and self.stop_child():
                process.REGISTRY.unlink(missing_ok=True)
                (self.run_dir/'stillwater-supervisor.pid').unlink(missing_ok=True)
                (self.home/'ready').unlink(missing_ok=True)
            self.log.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,default=Path('/data/push-ambient'));a=p.parse_args()
    supervisor=Supervisor(a.home)
    def end(*unused):supervisor.shutdown=True
    signal.signal(signal.SIGTERM,end);signal.signal(signal.SIGINT,end)
    raise SystemExit(supervisor.run())

if __name__=='__main__':main()
