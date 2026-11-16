#!/usr/bin/env python3
"""Counter-progress watchdog: 0 healthy, 2 bounded grace, 1 failed sample."""
import argparse
import json
from pathlib import Path
import sys
import time


def assess(m, pid, start_ticks, now, previous=None, grace=6):
    if m['pid']!=pid or str(m['start_ticks'])!=str(start_ticks):raise ValueError('wrong process identity')
    if not m['audio']['alive'] or not 0<=now-m['uptime']<4:raise ValueError('stale/dead metrics')
    counters=[m['audio']['frames'],m['audio']['written_frames'],m['display_frames']]
    if any(type(v) is not int or v<=0 for v in counters):raise ValueError('no successful audio/display work')
    identity=[pid,str(start_ticks)]
    if previous is None or previous.get('identity')!=identity:
        return 2,dict(identity=identity,counters=counters,progress_at=now)
    old=previous['counters']
    if any(v<last for v,last in zip(counters,old)):raise ValueError('counter regressed')
    if all(v>last for v,last in zip(counters,old)):
        return 0,dict(identity=identity,counters=counters,progress_at=now)
    return (2 if now-previous['progress_at']<grace else 1),previous


def main():
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);p.add_argument('start_ticks');p.add_argument('--home',type=Path,default=Path('/data/push-ambient'));p.add_argument('--state',type=Path,default=Path('/run/stillwater-health.json'));a=p.parse_args()
    try:
        actual=Path('/proc/%d/stat'%a.pid).read_text().rsplit(')',1)[1].split()[19]
        if actual!=a.start_ticks:raise ValueError('process replaced')
        previous=json.loads(a.state.read_text()) if a.state.exists() else None
        result,state=assess(json.loads((a.home/'metrics.json').read_text()),a.pid,a.start_ticks,time.monotonic(),previous)
        temp=a.state.with_suffix('.tmp');temp.write_text(json.dumps(state));temp.replace(a.state)
        return result
    except (OSError,ValueError,KeyError,TypeError,IndexError):return 1

if __name__=='__main__':sys.exit(main())
