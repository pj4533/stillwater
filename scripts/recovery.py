#!/usr/bin/env python3
"""Audio-free recovery surface. Never imports the instrument/native library."""
import argparse
import os
from pathlib import Path
import signal
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from graphics import recovery_frame
from hardware import Display, Midi


class RecoveryControls:
    def __init__(self):self.gear=None;self.action=None
    def receive(self,events,now):
        for e in events:
            if e['kind']=='cc' and e['channel']==0:
                if e['number']==30:self.gear=now if e['value'] else None
                elif e['number']==85 and e['value']:self.action='retry-stillwater'
            elif e['kind']=='sysex':
                n=e['number']
                if len(n)>=10 and n[1:7]==[0,33,29,1,1,58] and n[7]&24:self.action='return-stock'
        if self.gear is not None and now-self.gear>=2:self.action='return-stock'
        return self.action


def main():
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,default=Path('/data/push-ambient'));p.add_argument('--reason',default='application could not start');p.add_argument('--attempt',type=int,default=3);a=p.parse_args()
    os.umask(0o077);stopping=False
    def end(*unused):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,end);signal.signal(signal.SIGINT,end)
    display=midi=None;controls=RecoveryControls()
    try:
        display=Display();midi=Midi();frame=recovery_frame(a.reason,a.attempt)
        temp=Path('/run/stillwater-frame.tmp');temp.write_bytes(frame);temp.replace('/run/stillwater-frame.bgr565')
        display.send(frame);midi.cc(85,20);midi.cc(30,127)
        last=0
        while not stopping:
            now=time.monotonic();action=controls.receive(midi.read(),now)
            if action:(a.home/action).touch();break
            if now-last>=1:
                display.send(frame);midi.write([240,0,33,29,1,1,58,247]);last=now
            time.sleep(.02)
    finally:
        try:
            if midi:midi.close()
        finally:
            if display:display.close()

if __name__=='__main__':main()
