#!/usr/bin/env python3
"""Offline authored source registration and fluid masks; Pillow is not on Push."""
from pathlib import Path
import json,math,struct
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
source=Image.open(ROOT/'assets/organism-original.png').convert('RGB')
anchors=[0,260,495,735,970,1210,1460,1690,1890,2048]
dest=[0,60,180,300,420,540,660,780,900,960]
def mapped(x):
 for k in range(len(anchors)-1):
  if x<=anchors[k+1]:return dest[k]+(x-anchors[k])*(dest[k+1]-dest[k])/(anchors[k+1]-anchors[k])
 return 960
image=Image.new('RGB',(960,160))
for k in range(len(anchors)-1):
 tile=source.crop((anchors[k],0,anchors[k+1],550)).resize((dest[k+1]-dest[k],160),Image.Resampling.LANCZOS)
 image.paste(tile,(dest[k],0))
image=image.resize((480,80),Image.Resampling.LANCZOS).resize((960,160),Image.Resampling.NEAREST)
# Continuous irregular canopy/root-bed negative space, authored into the scene.
# Keep source roots/material visible at low contrast instead of adding UI cards.
for y in range(160):
 for x in range(960):
  canopy=24+3*math.sin(x*.021)+2*math.sin(x*.085)
  peat=115+3*math.sin(x*.043)+2*math.sin(x*.137)
  shade=min(1,max(.12,(y-canopy+6)/6)) if y<canopy else 1
  if y>peat:shade=min(shade,max(.12,1-(y-peat)/5))
  if shade<1:image.putpixel((x,y),tuple(round(v*shade) for v in image.getpixel((x,y))))
def packed(rgb):
 r,g,b=rgb;return struct.pack('<H',((b>>3)<<11)|((g>>2)<<5)|(r>>3))
raw=bytearray(1024*160*2)
for y in range(160):
 for x in range(960):raw[(y*1024+x)*2:(y*1024+x+1)*2]=packed(image.getpixel((x,y)))
(ROOT/'assets/organism-frame.bin').write_bytes(raw)
polygons=[[(250,125),(290,120),(282,390),(271,427),(241,415),(236,205)],[(493,138),(538,140),(541,175),(505,214),(532,238),(534,273),(510,305),(541,333),(525,386),(499,420),(477,390),(468,336),(483,307),(464,274),(464,242),(483,211),(467,174)],[(718,122),(758,122),(754,393),(736,432),(714,395)],[(958,123),(990,135),(1002,183),(1033,260),(1023,310),(989,410),(957,430),(930,369),(913,300),(920,236),(950,171)],[(1170,105),(1230,105),(1232,370),(1202,430),(1175,395)],[(1440,80),(1477,82),(1476,380),(1440,432),(1420,402),(1423,190)],[(1675,135),(1711,122),(1717,240),(1703,382),(1681,430),(1658,384),(1658,240)],[(1880,95),(1915,84),(1934,116),(1930,152),(1890,220),(1883,320),(1850,422),(1827,395),(1848,298),(1851,217),(1892,148)]]
accents=[(117,143,96),(161,110,76),(127,144,89),(151,91,102),(153,147,66),(88,155,140),(185,134,72),(92,152,117)]
organs=[]
for n,polygon in enumerate(polygons):
 mask=Image.new('1',(960,160));ImageDraw.Draw(mask).polygon([(round(mapped(x)),round(y*160/550)) for x,y in polygon],fill=1)
 rows=[]
 for y in range(160):
  xs=[x for x in range(960) if mask.getpixel((x,y))]
  if not xs:continue
  lo,hi=min(xs),max(xs);dry=bytearray();wet=[bytearray() for _ in range(4)]
  for x in range(lo,hi+1):
   rgb=image.getpixel((x,y));dry+=packed(tuple(round(v*.58) for v in rgb))
   for phase in range(4):
    # Preserve sourced reflections/material; color is absorbed into the same glass.
    shimmer=math.sin(y*.33+x*.18+phase*math.pi/2)*.065
    sx=x+round(math.sin(y*.12+phase*math.pi/2))
    sy=y+round(math.sin(x*.14+phase*math.pi/2))
    sampled=image.getpixel((sx,sy)) if 0<=sx<960 and 0<=sy<160 and mask.getpixel((sx,sy)) else rgb
    wet[phase]+=packed(tuple(max(0,min(255,round(v*(.94+shimmer)+accents[n][j]*.14))) for j,v in enumerate(sampled)))
  rows.append([y,lo,dry.hex(),[v.hex() for v in wet]])
 organs.append(rows)
(ROOT/'assets/organism-fluid.json').write_text(json.dumps(organs,separators=(',',':')))
image.save(ROOT/'.build/organism-art-preview.png')
