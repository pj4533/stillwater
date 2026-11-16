#!/usr/bin/env python3
"""Offline-only original artwork conversion. Pillow is never needed on Push."""
from pathlib import Path
import struct
from PIL import Image, ImageEnhance
root=Path(__file__).resolve().parents[1]
image=Image.open(root/'assets/pond-original.png').convert('RGB').crop((0,120,2048,535))
image=image.resize((480,80),Image.Resampling.LANCZOS).resize((960,160),Image.Resampling.NEAREST)
image=ImageEnhance.Color(image).enhance(1.15)
raw=bytearray(1024*160*2)
for y in range(160):
 for x in range(960):
  r,g,b=image.getpixel((x,y));struct.pack_into('<H',raw,(y*1024+x)*2,((b>>3)<<11)|((g>>2)<<5)|(r>>3))
(root/'assets/pond-frame.bin').write_bytes(raw)
image.save(root/'.build/pond-art-preview.png')

# Offline alpha-span atlas: eight subtle squash variants, two useful sizes.
# Each row stores opaque BGR565 runs, so Push needs no Pillow or alpha blending.
import json
atlas=Image.open(root/'assets/creatures-original.png').convert('RGBA')
sprites=[]
for index in range(4):
 x=(index%2)*(atlas.width//2);y=(index//2)*(atlas.height//2)
 tile=atlas.crop((x,y,x+atlas.width//2,y+atlas.height//2))
 tile=tile.crop(tile.getchannel('A').getbbox());sizes={}
 for height in (44,64):
  variants=[]
  for squash in range(5):
   h=height-2+squash;w=round(tile.width/tile.height*height)+(2-squash)
   small=tile.resize((max(1,w//2),max(1,h//2)),Image.Resampling.LANCZOS).resize((w,h),Image.Resampling.NEAREST)
   rows=[]
   for yy in range(h):
    runs=[];start=None;data=bytearray()
    for xx in range(w+1):
     rgba=small.getpixel((xx,yy)) if xx<w else (0,0,0,0)
     if rgba[3]>=128:
      if start is None:start=xx
      r,g,b=rgba[:3];data+=struct.pack('<H',((b>>3)<<11)|((g>>2)<<5)|(r>>3))
     elif start is not None:runs.append([start,data.hex()]);start=None;data=bytearray()
    rows.append(runs)
   variants.append({'width':w,'height':h,'rows':rows})
  sizes[str(height)]=variants
 sprites.append(sizes)
(root/'assets/creatures-spans.json').write_text(json.dumps(sprites,separators=(',',':')))
