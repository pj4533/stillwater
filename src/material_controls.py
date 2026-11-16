"""V5 physical contacts. Pure geometry shared by the offline baker and runtime."""
import math
from graphics import INK

MATERIALS={'silt':(204,153,94),'filament':(209,192,132),'glass':(155,216,219),
 'choir':(204,190,188),'oxide':(192,137,91),'backwash':(125,171,169),
 'spore':(153,185,122),'prism':(204,167,188)}

def position(role,value):
 v=max(0,min(1,value))
 if role=='silt':return 32+round(4*math.sin(math.pi*v)),58-round(52*v)
 if role=='filament':return 8+round(48*v),43-round(16*math.sin(math.pi*v))
 if role=='glass':
  a=math.radians(135+270*v);return 32+round(23*math.cos(a)),31+round(23*math.sin(a))
 if role=='choir':return 34,58-round(52*v)
 if role=='oxide':return 8+round(48*v),22+round(13*math.sin(math.pi*v))
 if role=='backwash':return 9+round(46*v),55-round(46*v)
 if role=='spore':return 14+round(34*v)+round(3*math.sin(math.pi*v)),57-round(50*v)
 if role=='prism':
  a=math.pi*(1+v);return 32+round(24*math.cos(a)),54+round(42*math.sin(a))
 raise ValueError('Unknown V5 role '+str(role))

def protected_boxes(role,value):
 """Inclusive local boxes. Socket plus two pixels; witnesses never breathe."""
 x,y=position(role,value)
 boxes=[(max(2,x-7),max(2,y-7),min(61,x+7),min(61,y+7))]
 for v in (0,.25,.5,.75,1):
  xx,yy=position(role,v);boxes.append((max(2,xx-3),max(2,yy-3),min(61,xx+3),min(61,yy+3)))
 return boxes

def branch_state(role,column,value):
 """Only the two native discontinuities; no invented Spore freeze telemetry."""
 if role=='glass' and column==0:return 1+int(7*max(0,min(1,value)))
 if role=='prism' and column==4:return int(value>=.5)
 return None

def branches(c,role,column,value):
 state=branch_state(role,column,value);ox=column*120+28;oy=48
 rgb=MATERIALS[role]
 if role=='glass' and column==0:
  # Facet groups belong to the reverse optical face. Ratio8 appears only at1.
  for n in range(state):
   x=ox+22+(n%4)*5;y=oy+25+(n//4)*10
   c.line(x,y,x+2,y-3,rgb);c.line(x+2,y-3,x+4,y,INK)
 elif role=='prism' and column==4 and state:
  c.line(ox+40,oy+31,ox+42,oy+17,rgb)
  c.line(ox+42,oy+17,ox+51,oy+11,INK)

def landmark(c,role,column,value):
 """The contact is material attached to the object, never a generic scale."""
 x,y=position(role,value);x+=column*120+28;y+=48
 rgb=MATERIALS[role];shadow=tuple(int(a*.36) for a in rgb)
 if role=='prism':
  hx=column*120+60;hy=102
  c.line(hx+1,hy,x+1,y,shadow);c.line(hx,hy,x,y,rgb)
  c.line(hx,hy-1,x,y-1,INK)
 if role=='backwash':
  c.line(x-5,y-3,x+4,y+4,shadow);c.line(x-4,y-4,x+5,y+3,rgb)
  c.line(x-3,y-4,x+4,y+2,INK)
 elif role=='glass':
  c.disc(x,y,4,4,shadow);c.line(x-3,y+2,x+2,y-3,rgb);c.line(x-2,y+2,x+3,y-3,INK)
 elif role=='oxide':
  c.rect(x-4,y-5,9,11,shadow);c.rect(x-3,y-4,7,9,rgb)
  c.line(x-2,y-3,x+2,y-3,INK);c.line(x,y-2,x,y+3,shadow)
 elif role=='choir':
  c.rect(x-5,y-3,10,7,shadow);c.rect(x-4,y-3,8,5,rgb);c.line(x-4,y-3,x+3,y-3,INK)
 elif role=='filament':
  c.disc(x,y,4,3,shadow);c.line(x-3,y+2,x-2,y-3,rgb);c.line(x,y+2,x+1,y-3,INK)
 elif role=='silt':
  c.disc(x,y,4,3,shadow);c.disc(x,y-1,3,2,rgb);c.line(x-3,y-2,x+2,y-2,INK)
  c.line(x-5,y+2,x-2,y+3,rgb)
 else:
  c.disc(x,y,4,4,shadow);c.disc(x,y-1,3,3,rgb);c.rect(x-1,y-3,2,2,INK)
