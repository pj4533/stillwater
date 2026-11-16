#!/usr/bin/env python3
"""Developer-side conversion only; instrument itself needs no Pillow."""
import argparse
from pathlib import Path
from PIL import Image
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
b=a.input.read_bytes();rgb=bytearray(960*160*3)
for y in range(160):
 for x in range(960):
  i=(y*1024+x)*2;v=b[i]|b[i+1]<<8;r=v&31;g=v>>5&63;bl=v>>11&31;o=(y*960+x)*3
  rgb[o:o+3]=bytes((r*255//31,g*255//63,bl*255//31))
Image.frombytes('RGB',(960,160),bytes(rgb)).save(a.output)
