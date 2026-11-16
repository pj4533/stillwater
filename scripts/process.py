#!/usr/bin/env python3
"""Bounded termination of recorded service-owned processes, including PID reuse checks."""
import json
import os
from pathlib import Path
import signal
import sys
import time

REGISTRY=Path('/run/stillwater-owned.json')

def identity(pid):
    try:
        fields=Path('/proc/%d/stat'%pid).read_text().rsplit(')',1)[1].split()
        return None if fields[0]=='Z' else fields[19]
    except (OSError,IndexError):return None


def alive(pid,start):return start is not None and identity(pid)==str(start)


def wait_dead(pid,start,timeout):
    deadline=time.monotonic()+timeout
    while alive(pid,start):
        if time.monotonic()>=deadline:return False
        time.sleep(.05)
    return True


def terminate(pid,start,grace=5):
    if not alive(pid,start):return True
    try:os.kill(pid,signal.SIGTERM)
    except ProcessLookupError:return True
    if wait_dead(pid,start,grace):return True
    if alive(pid,start):
        try:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:return True
    return wait_dead(pid,start,2)


def record(supervisor,child=None):
    data=dict(supervisor=[supervisor,identity(supervisor)],child=[child,identity(child)] if child else None)
    temp=REGISTRY.with_suffix('.tmp');temp.write_text(json.dumps(data));temp.replace(REGISTRY)


def stop_service():
    data=json.loads(REGISTRY.read_text())
    # Ask supervisor to save/release; then explicitly check its recorded child.
    # A killed supervisor never grants permission to overlap hardware owners.
    ok=terminate(*data['supervisor'],grace=7)
    if data.get('child'):ok=terminate(*data['child'],grace=3) and ok
    if ok:
        REGISTRY.unlink(missing_ok=True)
        Path('/run/stillwater-supervisor.pid').unlink(missing_ok=True)
        Path('/data/push-ambient/ready').unlink(missing_ok=True)
    return ok


def main():
    op=sys.argv[1]
    if op=='identity':
        start=identity(int(sys.argv[2]))
        if start is None:return 1
        print(start);return 0
    if op=='record':record(int(sys.argv[2]),int(sys.argv[3]) if len(sys.argv)>3 else None);return 0
    if op=='stop':return 0 if terminate(int(sys.argv[2]),sys.argv[3]) else 1
    if op=='stop-service':return 0 if stop_service() else 1
    return 1

if __name__=='__main__':sys.exit(main())
