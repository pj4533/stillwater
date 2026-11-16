#!/usr/bin/env python3
"""Offline original-art pixelation; Pillow is never needed on the instrument."""
from pathlib import Path
import math
import struct
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
FILES=dict(silt='391df789-a886-4935-a447-c1838e5ec93c',filament='678611d2-5853-4fbc-9076-ecba6911256b',glass='9180d6c2-496a-4427-8b57-2aaf23fc921d',choir='c54c234c-f951-47f6-88b0-609389cee03e',oxide='872bc6d2-2b1b-4142-9910-b20d213131b9',backwash='627a202e-e1fa-4d66-bd1e-07cb7f547654',spore='3defd7b6-4f17-4599-9903-9ae0972bc1c3',prism='05404728-f6bd-4d08-8c6a-95fdc588b443')
def main():
 directory=ROOT/'assets'/'v2';directory.mkdir(exist_ok=True)
 for role,ident in FILES.items():
  original=directory/(role+'-original.png')
  if not original.exists():raise FileNotFoundError('Missing bundled original: '+str(original))
  im=Image.open(original).convert('RGB').resize((480,80),Image.Resampling.LANCZOS).resize((960,160),Image.Resampling.NEAREST)
  pixels=bytearray(1024*160*2)
  for y in range(160):
   for x in range(960):
    # Continuous, rough-edged negative space connected to the source rootbed.
    edge=116+3*math.sin(x*.045)+2*math.sin(x*.12)
    amount=.22 if y<43 else .35 if y>edge else 1
    r,g,b=(round(c*amount) for c in im.getpixel((x,y)))
    struct.pack_into('<H',pixels,(y*1024+x)*2,((b>>3)<<11)|((g>>2)<<5)|(r>>3))
  (directory/(role+'.bin')).write_bytes(pixels)
if __name__=='__main__':main()
