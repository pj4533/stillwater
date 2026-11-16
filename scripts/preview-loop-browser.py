#!/usr/bin/env python3
"""Render synthetic browser states with the production UI; no hardware or user files."""
import ctypes as C
import json
from pathlib import Path
import sys
import tempfile
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from loop_model import LoopModel
from loop_engine import LoopEngine
from loop_app import LoopInstrument
from loop_graphics import render

def main():
 out=ROOT/'.build/browser-review';out.mkdir(parents=True,exist_ok=True);images=[]
 with tempfile.TemporaryDirectory() as temp:
  model=LoopModel(Path(temp)/'current-v3.json',writer=False)
  engine=LoopEngine(ROOT/'.build/engine.so');engine.lib.sw_reset();instrument=LoopInstrument(model,engine)
  engine.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int];engine.lib.sw_render((C.c_float*512)(),256)
  instrument.open_page('library')
  instrument.rows=[dict(id='song-'+str(n)*32+'.json',name='LOOP SELECTED '+str(n),created=1794860000,bytes=12345,status='READY',key='D DORIAN',tempo=58,bars=1,layers=3) for n in range(1,6)]
  instrument.selected_id=instrument.rows[1]['id']
  for state in ('unknown','loaded','edited','deleted','rename','confirm','recordings'):
   model.source=None if state=='unknown' else dict(id=instrument.rows[0]['id'],name='ABCDEFGHIJKLMNOPQRSTUVWX',modified=state in ('edited','deleted'),deleted=state=='deleted')
   instrument.rename='ABCDEFGHIJKLMNOPQRSTUVWX' if state=='rename' else None;instrument.rename_cursor=24
   instrument.confirm=dict(action='load',row=instrument.rows[1]) if state=='confirm' else None
   if state=='recordings':
    instrument.open_page('recordings');instrument.record_tab='saved'
    instrument.rows=[dict(id='film-'+'a'*12,name='film-'+'a'*12+'.mp4',type='FILM',status='READY',created=1794860000,bytes=123456,seconds=60)]
    instrument.selected_id=instrument.rows[0]['id']
   image=Image.frombytes('RGB',(1024,160),render(model,engine.stats(),instrument),'raw','RGB;16').crop((0,0,960,160))
   image.save(out/(state+'.png'));images.append(image)
 sheet=Image.new('RGB',(960,160*len(images)))
 for n,image in enumerate(images):sheet.paste(image,(0,n*160))
 sheet.save(out/'contact.png');print(out/'contact.png')
if __name__=='__main__':main()
