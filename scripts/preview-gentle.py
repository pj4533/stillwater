#!/usr/bin/env python3
"""Offline synthetic score only. Native float PCM, fixed per-clip measured gain.
Requires developer NumPy/ffmpeg; neither is a device runtime dependency.
Never opens ALSA, user sessions, or device control.
"""
import ctypes as C
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import wave
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_engine import LoopEngine
from loop_model import blank,Layer
from roles import ROLE_IDS,DEFAULTS,LEGACY_DEFAULTS
SR=44100

def render(engine,role,parameters,version=2,high=False,chord=False):
 engine.lib.sw_reset();engine.generation=0
 song=replace(blank(),role_order=(role,)+tuple(r for r in ROLE_IDS if r!=role),layers=(Layer(0,role,parameters=tuple(parameters),sound_version=version),))
 engine.publish(song,1)
 def audio(n):
  out=(C.c_float*(2*n))();engine.lib.sw_render(out,n);return np.ctypeslib.as_array(out).copy().reshape(-1,2)
 audio(SR//2);pieces=[]
 for num,(pitch,hold,tail) in enumerate(((74 if high else 50,2,2),(86 if high else 62,1,3))):
  pitches=[pitch,pitch+7] if chord else [pitch]
  for slot,note in enumerate(pitches):engine.check(engine.lib.sw_performance_on(slot,num*8+slot+1,0,note,.6,0,1,slot+num*8+1))
  pieces.append(audio(SR*hold))
  for slot in range(len(pitches)):engine.check(engine.lib.sw_performance_off(slot,num*8+slot+1))
  pieces.append(audio(SR*tail))
 return np.concatenate(pieces)

def spectral(pcm):
 mono=pcm.mean(axis=1);n=8192;windows=np.lib.stride_tricks.sliding_window_view(mono,n)[::4096]*np.hanning(n)
 power=(abs(np.fft.rfft(windows))**2).sum(axis=0);freq=np.fft.rfftfreq(n,1/SR)
 return dict(centroid_hz=float((freq*power).sum()/max(power.sum(),1e-30)),above_2k_fraction=float(power[freq>2000].sum()/max(power.sum(),1e-30)))

def metrics(pcm):
 active=np.concatenate((pcm[:2*SR],pcm[4*SR:5*SR]));tail=pcm[3*SR:4*SR]
 mono=pcm.mean(axis=1);delta=abs(np.diff(mono));local=np.maximum.reduce([np.roll(delta,i) for i in (-3,-2,-1,1,2,3)])
 return dict(rms_dbfs=float(20*np.log10(max(np.sqrt((pcm**2).mean()),1e-15))),first_half_second_rms_dbfs=float(20*np.log10(max(np.sqrt((pcm[:SR//2]**2).mean()),1e-15))),active_rms=float(np.sqrt((active**2).mean())),tail_to_active_db=float(10*np.log10(max((tail**2).mean(),1e-30)/max((active**2).mean(),1e-30))),peak=float(abs(pcm).max()),stereo_difference_ratio=float(np.sqrt(((pcm[:,0]-pcm[:,1])**2).mean())/max(np.sqrt((pcm**2).mean()),1e-15)),isolated_jump_ratio=float(np.max(delta[8:-8]/np.maximum(local[8:-8],1e-8))),isolated_excess_over_peak=float(np.maximum(delta[8:-8]-2*local[8:-8],0).max()/max(abs(mono).max(),1e-15)),**spectral(active))

def main():
 out=ROOT/'.build/gentle/previews';out.mkdir(parents=True,exist_ok=True)
 e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
 report={}
 # Existing macro names intentionally include combined source/FX controls.
 lower={0:{7:0},1:{4:0,5:0,7:0},2:{6:0,7:0},3:{7:0},4:{3:0,4:0},5:{2:0,5:0,6:0},6:{7:0},7:{3:0,5:0,6:0}}
 for role_id,role in enumerate(ROLE_IDS):
  dry=list(DEFAULTS[role_id])
  for index,value in lower[role_id].items():dry[index]=value
  bright=list(DEFAULTS[role_id])
  overrides=({2:0,4:.85,6:.8,3:.1},{0:.9,3:0},{0:.6,1:.9},{0:.85,1:.3,2:.8,3:.9},{0:1},{0:.9,7:0},{0:.9,1:1},{0:.9,1:1,2:.15,4:.8,7:0})
  for index,value in overrides[role_id].items():bright[index]=value
  versions={'legacy':(LEGACY_DEFAULTS[role_id],1,False,False),'gentle':(DEFAULTS[role_id],2,False,False),'bright':(bright,2,False,False),'high':(DEFAULTS[role_id],2,True,False),'less-fx':(dry,2,False,False)}
  if role in ('silt','choir','oxide'):versions['fifth']=(DEFAULTS[role_id],2,False,True)
  samples={}
  for name,(params,version,high,chord) in versions.items():
   pcm=render(e,role,params,version,high,chord);assert np.isfinite(pcm).all() and abs(pcm).max()<=.25
   samples[name]=pcm;data=metrics(pcm)
   if name in ('gentle','high','fifth'):assert data['isolated_excess_over_peak']<.005,(role,name,'isolated transition')
   # ffmpeg loudnorm measurement only; then one linear gain, capped by4x
   # oversampled true peak. No dynamic loudness processing in preview or engine.
   raw=out/f'{role}-{name}.f32';pcm.astype('<f4').tofile(raw)
   proc=subprocess.run(['ffmpeg','-hide_banner','-f','f32le','-ar',str(SR),'-ac','2','-i',str(raw),'-af','aselect=lt(t\\,2)+between(t\\,4\\,5),asetpts=N/SR/TB,loudnorm=I=-22:TP=-3:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
   loud=json.loads(proc.stderr[proc.stderr.rfind('{'):]);lufs=float(loud['input_i'])
   # Full clip intersample peak via standard ffmpeg true-peak meter.
   probe=subprocess.run(['ffmpeg','-hide_banner','-f','f32le','-ar',str(SR),'-ac','2','-i',str(raw),'-af','loudnorm=I=-22:TP=-3:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
   true_peak=float(json.loads(probe.stderr[probe.stderr.rfind('{'):])['input_tp'])
   gain_db=min(-22-lufs,-3.05-true_peak);scaled=pcm*10**(gain_db/20)
   path=out/f'{role}-{name}.wav'
   with wave.open(str(path),'wb') as wav:wav.setparams((2,2,SR,0,'NONE','not compressed'));wav.writeframes((np.clip(scaled,-1,1)*32767).astype('<i2').tobytes())
   verified=subprocess.run(['ffmpeg','-hide_banner','-i',str(path),'-af','loudnorm=I=-22:TP=-3:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
   measured_tp=float(json.loads(verified.stderr[verified.stderr.rfind('{'):])['input_tp']);assert measured_tp<=-3
   data.update(preview_measured_true_peak_dbfs=measured_tp,gain_db=gain_db,active_lufs=lufs,preview_active_lufs=lufs+gain_db,preview_true_peak_dbfs=true_peak+gain_db,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
   report[f'{role}/{name}']=data
  a,b=samples['gentle'],samples['less-fx'];report[f'{role}/fx_comparison']=dict(lowered_macro_indices=list(lower[role_id]),residual_over_default_rms=float(np.sqrt(((a-b)**2).mean())/max(np.sqrt((a*a).mean()),1e-15)),scope='same native level; controls may also affect source; preview gains reported individually')
 for role in ('silt','glass','choir','oxide'):
  assert report[role+'/bright']['centroid_hz']>report[role+'/gentle']['centroid_hz']*1.3,role
 for role in ROLE_IDS:
  assert report[role+'/fx_comparison']['residual_over_default_rms']>.1,role
 sustained=[report[r+'/gentle']['active_rms'] for r in ('silt','glass','choir','oxide','spore')]
 assert 20*np.log10(max(sustained)/min(sustained))<6
 result=dict(scope='Synthetic offline native samples; no listening/taste approval, physical output or device claim',sample_rate=SR,report=report)
 (out.parent/'audio-metrics.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k.endswith('/gentle')},indent=2))
if __name__=='__main__':main()
