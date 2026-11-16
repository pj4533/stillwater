#!/usr/bin/env python3
"""Build-only, source-derived material deformations; no runtime image package.

Decode the exact prepared V2 background, preserving its pixelation and palette.
Each registered macro has 17 static geometries and five audio deformations.
"""
from pathlib import Path
import math
import struct
from PIL import Image,ImageEnhance
ROOT=Path(__file__).resolve().parents[1]
ROLES=('silt','filament','glass','choir','oxide','backwash','spore','prism')
SIZE=64;POSES=17;AUDIO=5

def packed(im):
 data=bytearray()
 for r,g,b in im.getdata():data+=struct.pack('<H',((b>>3)<<11)|((g>>2)<<5)|(r>>3))
 return data

def deform(role,x,y,v,a,column):
 dx=x-32;dy=y-32
 # The actual source vessels, wires, cracks and bellows move. No repeated
 # symbols are drawn over the image. Audio remains independent of macro endstops.
 if role=='silt':return 32+dx/(.78+.30*v+.10*a),32+dy/(.72+.32*v+.18*a)
 if role=='filament':return x+math.sin(y*.10+column)*a*4,y+math.sin(x*.13+column)*(2+v*7+a*5)
 if role=='glass':return x+(1 if (x+y)//17%2 else -1)*(v*9+a*5),y+(x//18%2)*(v*5+a*4)
 if role=='choir':return 32+dx/(.72+.30*v+.15*a),y+math.sin(x*.42)*(2+v*3+a*3)
 if role=='oxide':return x+(int(y/7)%3-1)*(2+v*12+a*9),y+a*2
 if role=='backwash':return x+math.sin(y*.15+v*4+a)*(3+v*7+a*6),y+math.sin(x*.1)*(v*4+a*5)
 if role=='spore':return x+math.sin((y//6)*9+column)*(2+v*5+a*5),y+math.sin((x//6)*7)*(2+v*5+a*5)
 return 32+dx*(.8+v*.4)+(y//16%2)*(v*8+a*5),32+dy*(1+a*.12)

def prepare():
 target=ROOT/'assets/v4';target.mkdir(exist_ok=True)
 import sys
 sys.path.insert(0,str(ROOT/'src'))
 from roles import ROLE_RGB
 for role in ROLES:
  source=Image.frombytes('RGB',(1024,160),(ROOT/'assets/v2'/(role+'.bin')).read_bytes(),'raw','RGB;16')
  data=bytearray();hue=ROLE_RGB[role]
  for column in range(8):
   tile=source.crop((column*120+28,48,column*120+92,112));original=tile.load()
   for pose in range(POSES):
    v=pose/(POSES-1);front=60-round(56*v)
    for audio in range(AUDIO):
     a=audio/(AUDIO-1);moved=tile.copy();pixels=moved.load()
     # A fixed recessed source vessel with visibly occupied material. Audio
     # transforms source grain only; it never changes the occupied boundary.
     for y in range(4,62,2):
      for x in range(8,58,2):
       widths={'silt':21-3*math.cos(y*.065),'filament':20,'glass':20+(y//12%2)*2,
               'choir':22-(y//4%2)*3,'oxide':19,'backwash':21+2*math.sin(y*.12),
               'spore':20+2*math.sin(y*.7),'prism':21-abs(y%16-8)*.3}
       if abs(x-32)>widths[role]:continue
       occupied=y>=front
       sx,sy=deform(role,x,y,.5,a,column)
       r,g,b=original[max(0,min(63,int(sx)//2*2)),max(0,min(63,int(sy)//2*2))]
       if occupied:
        grain=(r+g+b)/765
        rgb=tuple(min(255,round(c*(.85+.12*a)+h*(.20+.16*grain))) for c,h in zip((r,g,b),hue))
       else:rgb=tuple(round(c*.12+3) for c in (r,g,b))
       for yy in range(y,min(64,y+2)):
        for xx in range(x,min(64,x+2)):pixels[xx,yy]=rgb
     data+=packed(moved)
  (target/(role+'.poses')).write_bytes(data)
  # Organic continuous negative space for actual timeline/fader work, with no
  # selected-role mechanisms repeated across empty channels.
  work=source.copy();px=work.load()
  for y in range(44,160):
   for x in range(960):
    edge=48+3*math.sin(x*.045)+2*math.sin(x*.12)
    darkness=.14 if y>edge else .4
    px[x,y]=tuple(round(v*darkness) for v in px[x,y])
  (target/(role+'.working')).write_bytes(packed(work))
if __name__=='__main__':prepare()
