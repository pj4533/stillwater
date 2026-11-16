#!/usr/bin/env python3
"""Bounded signal comparison of two distinct synthetic scores, not a taste test."""
import argparse,json,math,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.build/social-v4-gentle'
def analyze(path):
 raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-vn','-f','f32le','-']);x=np.frombuffer(raw,'<f4').reshape(-1,2)[10*44100:58*44100].astype(float)
 n=4096;freq=np.fft.rfftfreq(n,1/44100);power=np.zeros(n//2+1);window=np.hanning(n)
 for i in range(0,len(x)-n,2048):power+=np.mean(abs(np.fft.rfft(x[i:i+n]*window[:,None],axis=0))**2,axis=1)
 total=power.sum();rms=float(np.sqrt(np.mean(x*x)));peak=float(abs(x).max())
 return dict(interval=[10,58],finite=bool(np.isfinite(x).all()),rms_dbfs=20*math.log10(rms),peak_dbfs=20*math.log10(peak),crest_db=20*math.log10(peak/rms),power_centroid_hz=float(np.dot(freq,power)/total),energy_above_2khz_fraction=float(power[freq>=2000].sum()/total),energy_above_4khz_fraction=float(power[freq>=4000].sum()/total),rms_normalized_max_adjacent_jump=float(abs(np.diff(x,axis=0)).max()/rms))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('old',type=Path);p.add_argument('gentle',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result=dict(scope='Old and new distinct synthetic device scores over10–58s. Gain-invariant energy ratios/crest; not controlled same-note DSP evidence, hearing, click approval or comfort proof.',old=analyze(a.old),gentle=analyze(a.gentle))
 a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
