#!/usr/bin/env python3
"""Offline native response evidence, not listening or perceptual-quality claims."""
import ctypes as C
from dataclasses import replace
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_engine import LoopEngine
from loop_model import blank,Layer
from roles import ROLE_IDS,DEFAULTS,MACROS

def main():
 e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
 def audio(n):
  pcm=(C.c_float*(n*2))();e.lib.sw_render(pcm,n);return pcm
 def start(role,parameters):
  e.lib.sw_reset();e.generation=0;song=blank(seed=1)
  song=replace(song,role_order=(ROLE_IDS[role],)+tuple(r for r in ROLE_IDS if r!=ROLE_IDS[role]),layers=(Layer(0,ROLE_IDS[role],parameters=tuple(parameters)),))
  e.publish(song,1);audio(1);e.check(e.lib.sw_performance_on(0,1,0,62,.8,0,1,1))
 results=[]
 for role in range(8):
  for macro in range(8):
   onset=[];live=[]
   for value in (.05,.95):
    params=list(DEFAULTS[role]);params[macro]=value;start(role,params)
    pcm=list(audio(22050));e.lib.sw_performance_off(0,1);onset.append(pcm+list(audio(22050)))
    start(role,DEFAULTS[role]);audio(4410);e.check(e.lib.sw_layer_parameter(0,macro,value))
    pcm=list(audio(11025));e.lib.sw_performance_off(0,1);live.append(pcm+list(audio(22050)))
   initial=sum(abs(a-b) for a,b in zip(*onset));held=sum(abs(a-b) for a,b in zip(*live))
   assert initial>.0001 and held>.000001,(role,macro,initial,held)
   results.append(dict(role=ROLE_IDS[role],macro=MACROS[role][macro],initial_pcm_l1_difference=initial,held_release_pcm_l1_difference=held))
 report=dict(device=False,note=62,velocity=.8,compared_values=[.05,.95],macros=len(results),results=results)
 (ROOT/'.build/v2-macro-response.json').write_text(json.dumps(report,indent=2));print('64/64 initial and live-held/release native PCM responses pass')
if __name__=='__main__':main()
