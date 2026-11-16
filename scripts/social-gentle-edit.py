#!/usr/bin/env python3
"""Offline V4 synthetic portrait, native-speed audio and pixel detail.
Supply your own 960x160/10fps, 63-second synthetic capture. No device calls.
No hardware photograph is used or distributed.
"""
import argparse,hashlib,json,math,subprocess
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.build/social-v4-gentle';SOURCE=OUT/'source-original.mp4'
FPS=30;DURATION=63.;W,H=1080,1920
REG=Path('/usr/share/fonts/opentype/inter/InterDisplay-Regular.otf');BOLD=REG.with_name('InterDisplay-SemiBold.otf');SERIF=Path('/usr/share/fonts/truetype/ebgaramond/EBGaramond12-Regular.ttf')
INK='#102a2c';CREAM='#eee9d8';FOAM='#a6c5b6';BRASS='#c4b487'
CARDS=[(0,6.2,'A different life','for Push 3.','An ambient instrument. On the device.'),(6.4,10,'One warm current.','','Silt / two notes begin an eight-beat loop'),(10.7,18.5,'A choir','finds its place.','Watch the notes gather in LOOP.'),(18.8,20.1,'Let it breathe.','','The knobs stay still. The sound moves.'),(20.5,25.8,'A little depth.','','Two low notes / a wider foundation'),(26.5,34.4,'Light on the water.','','Filament / four plucked notes'),(34.8,37.8,'Let the echoes','find each other.','A slow turn of Echo'),(38.5,44.3,'Two small sparks.','','Prism / soft metallic accents'),(44.9,48.8,'The pattern grows.','','Four layers / fifteen notes'),(49.2,53.1,'Leave more space.','','Choir breathes. Silt opens.'),(53.7,58.1,'Let the layers','drift away.','One current remains.'),(58.4,63,'Let it settle.','','github.com/pj4533/stillwater')]

def run(args,**kw):return subprocess.run(args,check=True,**kw)
def font(n,face=None):return ImageFont.truetype(str(REG if face is None else face),n)
def text(d,xy,s,n,fill=CREAM,face=None):
 assert d.textlength(s,font=font(n,face))<=960,(s,n)
 d.text(xy,s,font=font(n,face),fill=fill)
def ease(q):q=max(0,min(1,q));return q*q*(3-2*q)
def fade(t,a,b):return min(1,max(0,(t-a)/.4),max(0,(b-t)/.4))
def decode():
 probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(SOURCE)]))
 video=next(s for s in probe['streams'] if s['codec_type']=='video');audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
 assert (video['width'],video['height'],video['avg_frame_rate'])==(960,160,'10/1'),'Requires 960x160 at 10fps'
 assert audio['sample_rate']=='44100' and audio['channels']==2,'Requires 44.1kHz stereo'
 raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(SOURCE),'-map','0:v:0','-f','rawvideo','-pix_fmt','rgb24','-'])
 return np.frombuffer(raw,np.uint8).reshape(-1,160,960,3)
def source(frames,t):return Image.fromarray(frames[min(len(frames)-1,int(t*10))])
def detail_x(t):
 # Camera crops the same native frame; parameter targets follow actual score.
 points=[(6,0),(10.15,0),(10.5,110),(18.6,110),(18.7,0),(20.2,0),(26.1,0),(26.4,230),(34.6,230),(34.8,440),(37.7,440),(38.2,350),(44.6,350),(44.9,230),(46.6,230),(46.9,110),(49,0),(50.9,0),(51.2,640),(53.2,640),(53.7,0),(58.3,0),(63,0)]
 for (a,x),(b,y) in zip(points,points[1:]):
  if a<=t<=b:return round(x+(y-x)*ease((t-a)/(b-a)))
 return 0
BASE=None
def editorial(frames,t):
 im=BASE.copy();src=source(frames,t);x=detail_x(t);im.paste(src.crop((x,0,x+320,160)).resize((960,480),Image.Resampling.NEAREST),(60,670));im.paste(src,(60,1280))
 layer=Image.new('RGBA',im.size);d=ImageDraw.Draw(layer)
 for a,b,l1,l2,sub in CARDS:
  alpha=fade(t,a,b)
  if not alpha:continue
  color=tuple(int(CREAM.lstrip('#')[i:i+2],16) for i in (0,2,4))+(round(alpha*255),)
  text(d,(60,320),l1,82,color,SERIF)
  if l2:text(d,(60,411),l2,82,color,SERIF)
  text(d,(60,533),sub,30,tuple(int(FOAM.lstrip('#')[i:i+2],16) for i in (0,2,4))+(round(alpha*255),))
 if t>=57:
  text(d,(60,1505),'Inspired by Ambient Town — Kieran Klaassen',28,CREAM)
 im=Image.alpha_composite(im.convert('RGBA'),layer).convert('RGB');return im

def frame(frames,t):return editorial(frames,t)
def main():
 global SOURCE,OUT,REG,BOLD,SERIF,BASE
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--regular-font',type=Path,default=REG);p.add_argument('--bold-font',type=Path,default=BOLD);p.add_argument('--serif-font',type=Path,default=SERIF);p.add_argument('--preview-only',action='store_true');p.add_argument('--gain-db',type=float,required=True);a=p.parse_args()
 SOURCE=a.source.resolve();OUT=a.output_dir.resolve();REG=a.regular_font;BOLD=a.bold_font;SERIF=a.serif_font
 assert math.isfinite(a.gain_db),'Gain must be finite'
 assert SOURCE not in (OUT/'picture.mp4',OUT/'stillwater-v4-gentle-portrait.mp4'),'Source must remain read-only'
 OUT.mkdir(parents=True,exist_ok=True);frames=decode();assert len(frames)==630,'Requires exactly 63s at 10fps'
 BASE=Image.new('RGB',(W,H),INK);d=ImageDraw.Draw(BASE)
 for i in range(9):d.ellipse((200-i*95,1460-i*26,1100+i*95,1700+i*26),outline='#1b3939',width=2)
 text(d,(60,156),'STILLWATER',58,CREAM,BOLD);text(d,(856,177),'V4',25,BRASS,BOLD);d.line((60,255,1020,255),fill='#46615b',width=2)
 text(d,(60,621),'PIXEL DETAIL',23,BRASS,BOLD);text(d,(60,1227),'THE WHOLE DISPLAY',23,BRASS,BOLD)
 d.rectangle((58,668,1021,1151),outline='#66827b',width=2);d.rectangle((58,1278,1021,1441),outline='#66827b',width=2)
 text(d,(60,1584),'Actual screen + native stereo',27,FOAM)
 text(d,(60,1625),'Scripted synthetic performance',27,FOAM)
 thumbs=[]
 for t in (1,3.5,5.7,8,13.5,18.5,24.5,29.5,35.5,40,44,49,54,59):
  im=frame(frames,t);im.save(OUT/f'preview-{t:g}.png');im.thumbnail((270,480));thumbs.append(im)
 sheet=Image.new('RGB',(270*7,480*2));
 for i,im in enumerate(thumbs):sheet.paste(im,((i%7)*270,(i//7)*480))
 sheet.save(OUT/'contact.jpg',quality=90)
 manifest=dict(source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),source=SOURCE.name,continuous_source_interval=[0,DURATION],retiming=False,frames=1890,fps=FPS,native_ui_fps=10,crop='320x160 native region at 3x nearest neighbor plus uncropped 960x160 overview',cards=CARDS,fonts=[dict(path=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in (REG,BOLD,SERIF)],disclosure='Synthetic capture; actual production-renderer screen and native stereo',audio=dict(gain_db=a.gain_db,fade_in=.35,fade_out_start=60,fade_out_duration=3,other_processing='none; no overdub or retiming'))
 if a.preview_only:(OUT/'edit-manifest.json').write_text(json.dumps(manifest,indent=2));return
 video=OUT/'picture.mp4';argv=['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1080x1920','-r','30','-i','-','-an','-vf','scale=out_color_matrix=bt709:out_range=tv,setsar=1','-c:v','libx264','-preset','medium','-crf','18','-threads','4','-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',str(video)]
 with subprocess.Popen(argv,stdin=subprocess.PIPE) as proc:
  for n in range(1890):proc.stdin.write(frame(frames,n/FPS).tobytes())
  proc.stdin.close();assert proc.wait()==0
 final=OUT/'stillwater-v4-gentle-portrait.mp4';mux=['ffmpeg','-v','error','-y','-i',str(video),'-i',str(SOURCE),'-map','0:v','-map','1:a','-t',str(DURATION),'-c:v','copy','-af',f'volume={a.gain_db}dB,afade=t=in:d=0.35,afade=t=out:st=60:d=3','-c:a','aac','-b:a','256k','-movflags','+faststart','-metadata','comment=Stillwater gentle synthetic demo; production-renderer pixels/native stereo, scripted inputs. No hardware photograph or filmed hands.',str(final)];run(mux)
 manifest['video_argv']=argv;manifest['mux_argv']=mux;(OUT/'edit-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(final)
if __name__=='__main__':main()
