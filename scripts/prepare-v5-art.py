#!/usr/bin/env python3
"""Deterministic original material constructions sampled from owned V2 grain.
Pillow is build-only. The patch has an unchanged two-pixel registration border.
"""
import hashlib,json,math,struct,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from roles import ROLE_IDS,MACROS
from material_controls import MATERIALS,position,protected_boxes
from graphics import Canvas
SIZE=64;POSES=17;AUDIO=5

def packed(im):
 return b''.join(struct.pack('<H',((b>>3)<<11)|((g>>2)<<5)|(r>>3)) for r,g,b in im.getdata())
def decode(data,size):return Image.frombytes('RGB',size,bytes(data),'raw','RGB;16')
def path(role,start=0,end=1,n=40):return [position(role,start+(end-start)*i/n) for i in range(n+1)]

class Painter:
 def __init__(self,image,source,role,offset=(0,0)):
  self.im=image;self.source=source;self.role=role;self.offset=offset
  self.support=Image.new('L',image.size)
 def paint(self,shape,coords,tone=1,width=1,support=True):
  mask=Image.new('L',self.im.size);d=ImageDraw.Draw(mask)
  if shape=='line':d.line(coords,fill=255,width=width,joint='curve')
  elif shape=='polygon':d.polygon(coords,fill=255)
  else:getattr(d,shape)(coords,fill=255,width=width) if shape=='arc' else getattr(d,shape)(coords,fill=255)
  # Positive material is defined by geometry, never inherited scenery or
  # source-image differences. Cast shadows are not material support.
  self.support.paste(255 if support else 0,(0,0),mask)
  # Light comes from the upper left. Source grain is sampled on a two-pixel grid.
  tex=Image.new('RGB',self.im.size);p=tex.load();s=self.source.load();h=MATERIALS[self.role];ox,oy=self.offset
  box=mask.getbbox()
  if not box:return
  for y in range(box[1],box[3]):
   for x in range(box[0],box[2]):
    if not mask.getpixel((x,y)):continue
    r,g,b=s[((x+ox)//2*2)%1024,((y+oy)//2*2)%160]
    grain=(r+g+b)/765;noise=((x//2*37+y//2*19+ox*7)%17-8)*.8
    p[x,y]=tuple(max(0,min(255,round(c*tone*(.67+.47*grain)+noise))) for c in h)
  self.im.paste(tex,(0,0),mask)
 def line(self,points,w=3,tone=1):
  self.paint('line',[(x+1,y+2) for x,y in points],tone*.32,w+2,support=False)
  self.paint('line',points,tone,w)
  if w>=4:self.paint('line',[(x-1,y-1) for x,y in points],tone*1.25,1)
 def oval(self,box,tone=1):
  self.paint('ellipse',(box[0]+1,box[1]+2,box[2]+1,box[3]+2),tone*.3,support=False)
  self.paint('ellipse',box,tone)
 def poly(self,points,tone=1):self.paint('polygon',points,tone)

def mechanism(tile,source,role,column,v,with_support=False):
 p=Painter(tile,source,role,(column*120+28,48));name=MACROS[ROLE_IDS.index(role)][column]
 if role=='silt':
  contour=[(27,1),(39,1),(40,10),(49,19),(51,37),(46,56),(40,61),(24,61),(17,53),(13,34),(17,18),(25,10),(27,1)]
  p.poly(contour,.82);p.line(contour,3,1.1)
  p.poly([(24,16),(38,13),(44,23),(44,44),(38,57),(25,55),(20,38)],1.05)
  for y in range(57,round(58-49*v),-4):p.line([(23,y),(31,y-1),(40,y-3)],2,.73)
  p.line([(23,12),(19,24),(20,43)],2,1.4)
  if name=='Bloom':
   for n in range(1+round(v*4)):p.line([(26,5+n*3),(32,7+n*3),(39,5+n*3)],2,.8)
  elif name=='Release':p.line([(32,53),(29,56),(34,58+round(v*3))],2,1.3)
  elif name=='Shade':p.poly([(20,19),(24+round(v*15),17),(38,46),(25,51)],.62)
  elif name=='Hollow':p.oval((23,22,39+round(v*5),48),.6);p.line([(26,25),(25,41),(34,46)],2,1.2)
  elif name=='Body':
   for n in range(2+round(v*6)):p.oval((23+n%3*4,35+n*2,29+n%3*4,38+n*2),.75+n%2*.3)
  elif name=='Sub':p.oval((18,40,34+round(v*9),56),.85);p.line([(24,41),(23,50),(30,54)],2,1.3)
  elif name=='Rust':
   for n in range(2+round(v*9)):p.oval((40+n%3,19+n*3,43+n%3,21+n*3),.7)
  else:p.line([(43,17),(55,22),(56,46),(48,55),(43,48),(50,39-round(v*12))],3,.8)
 elif role=='filament':
  p.line(path(role),5,.68);p.line(path(role),2,1.35)
  p.line([(7,43),(12,52),(28,57+round(v*2)),(46,54),(57,43)],2,.78)
  p.line([(5,36),(23,44),(40,40),(59,32)],1,.9)
  if name=='Pluck':p.poly([(22,43),(27,30-round(v*7)),(30,43)],1.1)
  elif name=='Length':
   for n in range(2+round(v*4)):p.oval((17+n*4,47,25+n*4,56),.8)
  elif name=='Stiff':
   for n in range(2+round(v*5)):p.line([(15+n*5,26),(20+n*5,39)],2,.95)
  elif name in ('Echo','Return'):p.line([(8,43),(13,17-round(v*5)),(39,11),(53,20),(55,43)],2,1.1 if name=='Echo' else .8)
  elif name=='Spread':
   for sign in (-1,1):p.line([(8,43),(30,30+sign*round(4+v*12)),(56,43)],2,.9)
  elif name=='Mist':
   for n in range(6):p.line([(12+n*6,38),(20+n*5,48+round(v*8))],1,.65)
 elif role=='glass':
  p.oval((5,3,60,59),.50);p.oval((8,4,56,55),.9)
  p.oval((14-round(v*3),10,49,49),1.12)
  p.line(path(role),4,1.26)
  for n in range(8 if name=='Ratio' else 5):
   a=n/(7 if name=='Ratio' else 4);x,y=position(role,a)
   p.line([(x,y),(32+(x-32)*.6,31+(y-31)*.6),(29+n%3*3,31)],1,.58)
  if name=='Index':p.oval((19+round(v*8),13,51+round(v*4),45),.82)
  elif name=='Bloom':
   for n in range(2+round(v*4)):p.line([(15+n*4,17),(22+n*3,36)],2,.7)
  elif name=='Ring':
   for n in range(1+round(v*3)):p.line([(13+n*3,41),(20+n*2,47),(35,48-n*2)],1,1.35)
  elif name=='Sweep':p.poly([(18,18+round(v*14)),(45,16),(40,42),(24,45-round(v*13))],.9)
  elif name=='Motion':p.line([(18,37),(22,22),(32,16),(40+round(v*8),23)],2,1.4)
  elif name in ('Depth','Phase'):
   xx=17 if name=='Depth' else 37;p.poly([(xx,16),(xx+round(3+v*10),23),(xx+8,43),(xx-3,37)],1.25)
 elif role=='choir':
  p.line([(34,2),(34,61)],7,.7)
  top=56-round(v*47);p.poly([(33,top),(18-round(v*7),top+8),(14,51),(33,58)],.82)
  for n in range(7):
   yy=top+(57-top)*n/7;p.line([(34,yy),(24-n%2*3,yy-2),(14-round(v*3),yy+3)],3,1.05)
  if name=='Vowel':
   for n in range(3):p.oval((40,18+n*11,49+round(v*7)*(n==1),29+n*11),.8+n*.12)
  elif name=='Breath':p.poly([(15,29),(9-round(v*3),36),(12,50),(21,54)],.85)
  elif name=='Throat':p.line([(40,49),(43,44-round(v*24))],5,1.15)
  elif name=='Focus':p.oval((40,22,56,45),.95);p.oval((44,28+round(v*4),52,40),.62)
  elif name in ('Bloom','Release'):
   for n in range(2+round(v*4)):p.line([(40,12+n*6),(46,15+n*6),(42,18+n*6)],2,.9)
  elif name=='Drift':p.line([(39,54),(51+round(v*6),40),(42,21)],2,1.05)
  else:
   for n in range(2):p.oval((39+n*8,28-round(v*14),46+n*8,54),.82+n*.15)
 elif role=='oxide':
  p.line([(8,22),(13,45),(34,54),(53,45),(56,22)],9,.65)
  p.line(path(role),9,.88);p.line(path(role),1,1.3)
  for x in (8,56):p.oval((x-6,15,x+6,29),.95);p.oval((x-2,19,x+2,23),.52)
  for n in range(10):p.oval((12+n*4,43+n%3,14+n*4,45+n%3),1.25)
  if name=='Wear':
   for n in range(2+round(v*8)):p.line([(16+n*3,29),(18+n*3,35)],1,.5)
  elif name in ('Wow','Flutter'):
   p.line([(14+n*3,48+round(math.sin(n*(.6 if name=='Wow' else 2))*v*5)) for n in range(13)],3,1.1)
  elif name in ('Echo','Return'):p.line([(15,39),(14,8),(37,5),(49,12),(48,35-round(v*12))],3,.92)
  elif name=='Dropout':
   for n in range(round(v*7)):p.line([(17+n*4,29),(18+n*4,36)],2,1.4)
  elif name=='Width':p.line([(11,26+round(v*6)),(31,39+round(v*4)),(54,28+round(v*6))],2,1.1)
  elif name=='Bloom':
   for n in range(1+round(v*4)):p.oval((15+n*7,7,21+n*7,13),1.15)
 elif role=='backwash':
  p.line(path(role),20,.64);p.line(path(role),12,1.05)
  p.line([(8,54),(27,52),(48,32),(54,9)],10,.72)
  p.line([(8,54),(27,52),(48,32),(54,9)],4,1.28)
  for n in range(6):p.line([(10+n*7,51-n*7),(12+n*7,47-n*7)],2,.6)
  if name=='Strike':p.poly([(21,35),(15+round(v*11),28),(29,35)],1.25)
  elif name=='Release':p.oval((7,43,28+round(v*13),58),.95)
  elif name=='Reverse':p.line(path(role),2,.8+v*.5);p.line([(10,54),(32,49),(51,26)],2,1.3-v*.5)
  elif name in ('Window','Echo','Return'):p.line([(22,43),(8,28),(14,13-round(v*6)),(30,10),(37,24)],4,.9)
  elif name=='Seam':
   for n in range(2+round(v*4)):p.line([(30+n*2,36),(38+n*2,40)],1,1.4)
  else:p.poly([(19,20),(43,16),(53,32+round(v*12)),(33,40)],.75)
 elif role=='spore':
  p.line(path(role),10,.63);p.line(path(role),5,1.15)
  for n in range(5):
   x,y=position(role,n/4);sgn=1 if n%2 else -1;w=round(8+v*7) if name in ('Scatter','Width') else 11
   p.line([(x,y),(x+sgn*w,y-4),(x+sgn*(w+3),y-10)],3,.9)
   size=round(3+v*3) if name=='Grain' else 4;p.oval((x+sgn*w-3,y-8-size,x+sgn*w+3,y-5),.94)
  if name=='Bow':p.line([(8,47),(28,31),(32+round(v*7),18)],3,1.3)
  elif name=='Tone':p.line(path(role),2,.75+v*.65)
  elif name=='Density':
   for n in range(2+round(v*6)):
    x,y=position(role,n/8);p.oval((x-6,y-2,x,y+4),.85)
  elif name=='Memory':
   p.line([(9,58),(5,47),(14,31),(33,27),(49,12)],3,.85)
   for val in (.75,.85):
    x,y=position(role,val);p.line([(x-5,y),(x+5,y)],2,1.35)
  elif name=='Cloud':
   for n in range(2+round(v*5)):p.line([(12,48-n*3),(48,38-n*3)],1,.7)
 elif role=='prism':
  p.line(path(role),6,.67);p.line(path(role),2,1.2)
  for n in range(7):
   vv=v*n/7;x,y=position(role,vv);p.poly([(30,55),(x,y),(x+4,y+1),(35,55)],.76+n*.06)
   p.line([(32,54),(x,y)],1,1.25)
  p.oval((25,49,39,60),.8)
  if name=='Strike':p.line([(46,58),(45-round(v*8),47)],4,1.25)
  elif name=='Metal':
   for n in range(1+round(v*5)):p.poly([(23+n*3,36),(25+n*3,30),(30+n*2,45)],.58)
  elif name=='Damping':p.poly([(13,36),(25,29),(35+round(v*12),42),(32,49)],.55)
  elif name=='Glow':p.poly([(23,43),(28,20-round(v*6)),(38,40)],1.05+v*.25)
  elif name=='Octave':
   p.line([(32,54),(40,31),(51,24)],3,.9)
  elif name=='Room':p.line([(5,49),(3,17),(18,5),(43,3),(59,17+round(v*12))],3,.95)
  elif name=='Diffuse':
   for n in range(2+round(v*6)):p.line([(32,54),(18+n*5,23+n%3*5)],1,1.1)
  else:p.poly([(19,26),(35,18),(50,36),(39,45+round(v*8))],.75)
 # Permanent anatomical witness chips, never a detached gauge scale.
 for val in (0,.25,.5,.75,1):
  x,y=position(role,val);p.line([(x-1,y-1),(x+1,y+1)],2,1.5 if val in (0,.5,1) else 1.12)
 return (tile,p.support) if with_support else tile

def scene(source,role):
 # Calmed source stays visible; connections are composed over the entire world.
 im=source.point(lambda c:round(c*.59));p=Painter(im,source,role)
 for col in range(8):
  x=col*120
  if role=='silt':points=[(x+5,108),(x+18,102),(x+50,108),(x+72,108),(x+103,99),(x+125,102)];w=9
  elif role=='filament':points=[(x,93),(x+17,77),(x+36,91),(x+84,91),(x+104,66),(x+120,80)];w=4
  elif role=='glass':points=[(x,91),(x+16,86),(x+29,64),(x+61,48),(x+88,62),(x+105,91),(x+121,94)];w=9
  elif role=='choir':points=[(x,110),(x+18,105),(x+62,109),(x+100,105),(x+120,110)];w=8
  elif role=='oxide':points=[(x,89),(x+20,95),(x+36,70),(x+84,70),(x+104,97),(x+120,89)];w=7
  elif role=='backwash':points=[(x,109),(x+24,113),(x+37,103),(x+83,57),(x+105,50),(x+120,56)];w=14
  elif role=='spore':points=[(x,113),(x+20,110),(x+42,105),(x+76,55),(x+98,49),(x+120,52)];w=7
  else:points=[(x,112),(x+26,106),(x+60,103),(x+94,108),(x+120,112)];w=8
  p.line(points,w,.75)
  if role in ('filament','oxide'):
   for xx,yy in ((x+36,91 if role=='filament' else 70),(x+84,91 if role=='filament' else 70)):
    p.oval((xx-8,yy-9,xx+7,yy+9),.88);p.oval((xx-3,yy-3,xx+3,yy+3),.48)
  elif role=='choir':p.line([(x+62,108),(x+62,48),(x+82,46),(x+107,52)],6,.95)
  elif role=='silt':p.line([(x+55,54),(x+55,46),(x+80,46),(x+102,53)],6,.9)
 # Endpoint engravings use the production font; values never overlap contacts.
 c=Canvas(packed(im))
 for col in range(8):
  for val,label in ((0,'0'),(1,'100')):
   xx,yy=position(role,val);left=col*120+(5 if xx<32 else 95)
   c.text(left,48+max(1,min(56,yy-3)),label,(214,207,177))
 return decode(c.pixels,(1024,160))

def music_support(role,v,positive,protect):
 """Role-native interior/return surfaces, intersected with visible geometry.
 The mask is independent of both source pixels and the landmark protection.
 """
 region=Image.new('L',(64,64));d=ImageDraw.Draw(region)
 if role=='silt':
  # Suspended material in the foot pool and the occupied lower chamber.
  d.polygon([(19,51),(43,51),(40,58),(24,59)],fill=255)
  if v>.2:d.rectangle((22,max(16,58-round(49*v)),42,54),fill=255)
 elif role=='filament':d.line([(7,43),(12,52),(28,57+round(v*2)),(46,54),(57,43)],fill=255,width=2)
 elif role=='glass':d.ellipse((17,15,47,46),fill=255)
 elif role=='choir':
  top=56-round(v*47)
  d.polygon([(32,top+1),(18-round(v*7),top+8),(15,51),(32,57)],fill=255)
 elif role=='oxide':d.line([(8,22),(13,45),(34,54),(53,45),(56,22)],fill=255,width=5)
 elif role=='backwash':
  d.line(path(role),fill=255,width=7)
  d.line([(8,54),(27,52),(48,32),(54,9)],fill=255,width=3)
 elif role=='spore':
  # Side chambers and side filaments only; the indexed main root stays rigid.
  for n in range(5):
   x,y=position(role,n/4);sgn=1 if n%2 else -1
   d.rectangle((x-19,y-18,x+19,y-3),fill=255)
  d.line(path(role),fill=0,width=13)
 else:
  # Stationary basal crystal carries internal light even with leaves closed.
  d.ellipse((27,51,37,59),fill=255)
  if v>.15:
   for n in range(1,7):
    x,y=position(role,v*n/7);d.line([(32,53),(x+1,y+2)],fill=255,width=1)
 allowed=ImageChops.multiply(region,positive)
 allowed=ImageChops.subtract(allowed,protect)
 d=ImageDraw.Draw(allowed);d.rectangle((0,0,63,1),fill=0);d.rectangle((0,62,63,63),fill=0)
 d.rectangle((0,0,1,63),fill=0);d.rectangle((62,0,63,63),fill=0)
 return allowed

def animate(still,allowed,audio):
 """Localized light in existing material, never new dashes or silhouettes."""
 if not audio:return still.copy()
 pixels=[(x,y) for y in range(2,62) for x in range(2,62) if allowed.getpixel((x,y))]
 if len(pixels)<20:raise ValueError('Insufficient supported musical interior: '+str(len(pixels)))
 # Three compact material regions; ordering follows the geometry's own pixels.
 centers=[pixels[round((len(pixels)-1)*q)] for q in (.2,.5,.8)]
 selected=sorted(pixels,key=lambda pt:min((pt[0]-x)**2+(pt[1]-y)**2 for x,y in centers))[:min(32,len(pixels))]
 moving=still.copy();dest=moving.load();source=still.load()
 for x,y in selected:
  gain=.10+.035*audio+.025*math.sin((x+y)*.7+audio)
  dest[x,y]=tuple(min(255,round(c*(1+gain))+2) for c in source[x,y])
 return moving

def prepare(target=None):
 target=Path(target or ROOT/'assets/v5');target.mkdir(parents=True,exist_ok=True)
 manifest={};support_manifest={}
 support_dir=target/'support';support_dir.mkdir(exist_ok=True)
 for role in ROLE_IDS:
  source=decode((ROOT/'assets/v2'/(role+'.bin')).read_bytes(),(1024,160));base=scene(source,role)
  data=bytearray();support_atlas=Image.new('L',(64*8,64*17))
  for col in range(8):
   crop=base.crop((col*120+28,48,col*120+92,112))
   for pose in range(POSES):
    v=pose/16;still,positive=mechanism(crop.copy(),source,role,col,v,with_support=True)
    # Full registration border always equals the recomposed scene.
    still.paste(crop.crop((0,0,64,2)),(0,0));still.paste(crop.crop((0,62,64,64)),(0,62))
    still.paste(crop.crop((0,0,2,64)),(0,0));still.paste(crop.crop((62,0,64,64)),(62,0))
    protect=Image.new('L',(64,64));pd=ImageDraw.Draw(protect)
    lo=max(0,(pose-.5)/16);hi=min(1,(pose+.5)/16)
    for step in range(11):
     for box in protected_boxes(role,lo+(hi-lo)*step/10):pd.rectangle((max(2,box[0]-1),max(2,box[1]-1),min(61,box[2]+1),min(61,box[3]+1)),fill=255)
     if role=='prism':pd.line([(32,54),position(role,lo+(hi-lo)*step/10)],fill=255,width=7)
    allowed=music_support(role,v,positive,protect)
    support_atlas.paste(allowed,(col*64,pose*64))
    for audio in range(AUDIO):
     moving=animate(still,allowed,audio)
     data.extend(packed(moving))
  for suffix,raw in (('.bin',packed(base)),('.poses',data)):
   name=role+suffix;(target/name).write_bytes(raw);manifest[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
  support_file=support_dir/(role+'.png');support_atlas.save(support_file)
  support_manifest[role]={'sha256':hashlib.sha256(support_file.read_bytes()).hexdigest(),'bytes':support_file.stat().st_size}
  print(role,flush=True)
 (target/'manifest.json').write_text(json.dumps({'version':5,'source':'owned V2 BGR565 backgrounds','files':manifest},indent=2)+'\n')
 (support_dir/'manifest.json').write_text(json.dumps(support_manifest,indent=2)+'\n')
 return manifest
if __name__=='__main__':prepare(sys.argv[1] if len(sys.argv)>1 else None)
