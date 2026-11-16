"""V5 registration, exact topology, asset validation and native-life regressions."""
import hashlib,importlib.util,json,math,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from roles import ROLE_IDS
from material_controls import position,protected_boxes,branch_state
from loop_graphics import background,poses,material,preload,working_background
from graphics import Canvas

class Geometry(unittest.TestCase):
 def test_paths_exact_bounded_distinct_continuous(self):
  for role in ROLE_IDS:
   points=[position(role,n/100) for n in range(101)]
   self.assertNotEqual(points[0],points[-1]);self.assertGreater(len(set(points)),40)
   for x,y in points:self.assertTrue(2<=x<=61 and 2<=y<=61,(role,x,y))
   for (x,y),(xx,yy) in zip(points,points[1:]):self.assertLessEqual(math.hypot(xx-x,yy-y),2.3)
  self.assertEqual(position('silt',0),(32,58));self.assertEqual(position('glass',.5),(32,8));self.assertEqual(position('prism',.5),(32,12))
 def test_path_progress_and_subpixel_rounding(self):
  for role in ROLE_IDS:
   points=[position(role,n/100) for n in range(101)]
   if role in ('silt','choir','spore'):
    self.assertEqual([y for x,y in points],sorted((y for x,y in points),reverse=True))
   elif role in ('filament','oxide','backwash'):
    self.assertEqual([x for x,y in points],sorted(x for x,y in points))
   else:
    cx,cy,rx,ry=(32,31,23,23) if role=='glass' else (32,54,24,42)
    angles=[math.atan2((y-cy)/ry,(x-cx)/rx) for x,y in points]
    for a,b in zip(angles,angles[1:]):self.assertGreaterEqual((b-a+math.pi)%(2*math.pi)-math.pi,-1e-9)
   for n,(x,y) in enumerate(points):
    v=n/100
    expected={
     'silt':(32+4*math.sin(math.pi*v),58-52*v),
     'filament':(8+48*v,43-16*math.sin(math.pi*v)),
     'glass':(32+23*math.cos(math.radians(135+270*v)),31+23*math.sin(math.radians(135+270*v))),
     'choir':(34,58-52*v),'oxide':(8+48*v,22+13*math.sin(math.pi*v)),
     'backwash':(9+46*v,55-46*v),'spore':(14+34*v+3*math.sin(math.pi*v),57-50*v),
     'prism':(32+24*math.cos(math.pi*(1+v)),54+42*math.sin(math.pi*(1+v)))}[role]
    self.assertLessEqual(abs(x-expected[0]),1);self.assertLessEqual(abs(y-expected[1]),.500001)
 def test_clamp(self):
  for role in ROLE_IDS:self.assertEqual(position(role,-2),position(role,0));self.assertEqual(position(role,3),position(role,1))

 def test_native_discontinuities_exact_not_coarse_pose(self):
  self.assertEqual(branch_state('glass',0,.999999),7)
  self.assertEqual(branch_state('glass',0,1),8)
  self.assertEqual(branch_state('glass',0,1/7-1e-9),1)
  self.assertEqual(branch_state('glass',0,1/7),2)
  self.assertEqual(branch_state('prism',4,.5-1e-9),0)
  self.assertEqual(branch_state('prism',4,.5),1)
  self.assertIsNone(branch_state('spore',5,.8))

class Assets(unittest.TestCase):
 def test_hashes_budget_and_cache(self):
  manifest=json.loads((ROOT/'assets/v5/manifest.json').read_text())
  self.assertEqual(len(manifest['files']),16)
  for name,entry in manifest['files'].items():
   data=(ROOT/'assets/v5'/name).read_bytes();self.assertEqual(len(data),entry['bytes']);self.assertEqual(hashlib.sha256(data).hexdigest(),entry['sha256'])
  preload();self.assertEqual(poses.cache_info().currsize,8);self.assertEqual(background.cache_info().currsize,8)
  self.assertEqual(sum(len(poses(r)) for r in ROLE_IDS),44564480)
 def test_missing_and_truncated_fail_closed(self):
  poses.cache_clear();background.cache_clear()
  with patch('pathlib.Path.read_bytes',return_value=b''):
   with self.assertRaisesRegex(ValueError,'V5 mechanism'):poses('silt')
   with self.assertRaisesRegex(ValueError,'V5 instrument'):background('silt')
  with patch('pathlib.Path.read_bytes',side_effect=FileNotFoundError('V5 missing')):
   with self.assertRaises(FileNotFoundError):poses('silt')
 def test_every_pose_two_pixel_registration_border(self):
  for role in ROLE_IDS:
   data=poses(role);base=background(role)
   for col in range(8):
    for pose in range(17):
     for audio in range(5):
      offset=((col*17+pose)*5+audio)*8192
      for y in range(64):
       row=data[offset+y*128:offset+(y+1)*128];start=((48+y)*1024+28+col*120)*2;b=base[start:start+128]
       if y in (0,1,62,63):self.assertEqual(row,b,(role,col,pose,audio,y))
       else:self.assertEqual(row[:4]+row[-4:],b[:4]+b[-4:])
 def test_exact_marker_and_witnesses_stable_at_rounding_boundaries(self):
  for role in ROLE_IDS:
   base=background(role)
   for value in sorted(set([n/100 for n in range(101)]+[(n+.5)/16 for n in range(16)])):
    c=Canvas(base);material(c,base,role,(value,)*8,0,0,0)
    animated=Canvas(base);material(animated,base,role,(value,)*8,1,0,.713)
    for x0,y0,x1,y1 in protected_boxes(role,value):
     for y in range(y0,y1+1):
      start=((48+y)*1024+28+x0)*2;end=start+(x1-x0+1)*2
      self.assertEqual(c.pixels[start:end],animated.pixels[start:end],(role,value,x0,y))
 def test_each_macro_has_local_activity_at_all_coarse_positions(self):
  for role in ROLE_IDS:
   data=poses(role)
   for col in range(8):
    for pose in range(17):
     offset=((col*17+pose)*5)*8192
     self.assertNotEqual(data[offset:offset+8192],data[offset+4*8192:offset+5*8192],(role,col,pose))
 def test_all_baked_music_changes_have_positive_material_support(self):
  from PIL import Image
  report={};total=0
  support_manifest=json.loads((ROOT/'assets/v5/support/manifest.json').read_text())
  for role in ROLE_IDS:
   path=ROOT/'assets/v5/support'/(role+'.png')
   self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),support_manifest[role]['sha256'])
   atlas=Image.open(path).convert('L');data=poses(role);counts=[]
   self.assertEqual(atlas.size,(512,1088))
   for col in range(8):
    for pose in range(17):
     allowed=bytes(atlas.crop((col*64,pose*64,(col+1)*64,(pose+1)*64)).getdata())
     offset=((col*17+pose)*5)*8192;still=data[offset:offset+8192]
     for audio in range(1,5):
      moving=data[offset+audio*8192:offset+(audio+1)*8192]
      changed=[n for n in range(4096) if still[n*2:n*2+2]!=moving[n*2:n*2+2]]
      self.assertGreaterEqual(len(changed),20,(role,col,pose,audio))
      self.assertTrue(all(allowed[n] for n in changed),(role,col,pose,audio,'unsupported music'))
      counts.append(len(changed));total+=len(changed)
   report[role]={'min_supported_changed':min(counts),'max_supported_changed':max(counts),'unsupported_changed':0,'combinations':544}
  out=ROOT/'.build/v5-validation';out.mkdir(parents=True,exist_ok=True)
  (out/'material-support-validation.json').write_text(json.dumps({'roles':report,'total_changed_pixels':total,'unsupported_changed_pixels':0,'combinations':4352},indent=2)+'\n')
 def test_positive_support_is_geometry_not_source_or_shadow(self):
  from PIL import Image
  spec=importlib.util.spec_from_file_location('v5_baker',ROOT/'scripts/prepare-v5-art.py')
  baker=importlib.util.module_from_spec(spec);spec.loader.exec_module(baker)
  source=Image.new('RGB',(1024,160),(210,170,90));tile=Image.new('RGB',(64,64),(210,170,90))
  p=baker.Painter(tile,source,'prism');p.line([(10,20),(30,20)],3)
  self.assertEqual(p.support.getpixel((20,20)),255)
  self.assertEqual(p.support.getpixel((20,23)),0) # cast shadow
  self.assertEqual(p.support.getpixel((40,40)),0) # bright inherited scenery
  for role in ROLE_IDS:
   allowed=baker.music_support(role,.5,Image.new('L',(64,64)),Image.new('L',(64,64)))
   self.assertIsNone(allowed.getbbox(),role)
 def test_prism_terminal_facet_cannot_breathe(self):
  for n in range(101):
   v=n/100;base=background('prism');frames=[]
   for env in (0,1):
    c=Canvas(base);material(c,base,'prism',(v,)*8,env,0,.713);frames.append(c.pixels)
   x,y=position('prism',v)
   for k in range(101):
    xx=round(32+(x-32)*k/100);yy=round(54+(y-54)*k/100)
    for dx,dy in ((0,0),(0,-1),(1,0)):
     start=((48+yy+dy)*1024+28+xx+dx)*2
     self.assertEqual(frames[0][start:start+2],frames[1][start:start+2],v)
 def test_quiet_native_activity_still_has_two_internal_poses(self):
  from loop_graphics import music_pose
  for role in ROLE_IDS:
   self.assertEqual({music_pose(role,0,0,1,n*.1) for n in range(30)},{0})
   self.assertGreater(len({music_pose(role,0,.001,0,n*.1) for n in range(30)}),1)
 def test_silence_stable_and_native_energy_without_fx_moves(self):
  for role in ROLE_IDS:
   for v in (0,.5,1):
    base=background(role);frames=[]
    for env,t in ((0,0),(0,9),(1,.1),(1,.6),(1,1.1)):
     c=Canvas(base);material(c,base,role,(v,)*8,env,0,t);frames.append(bytes(c.pixels))
    self.assertEqual(frames[0],frames[1]);self.assertGreater(len(set(frames[2:])),1,(role,v))
    # No typography or stride writes from mechanisms.
    self.assertEqual(frames[0][:48*2048],base[:48*2048]);self.assertEqual(frames[0][112*2048:],base[112*2048:])
    for y in range(160):self.assertEqual(frames[0][(y*1024+960)*2:(y+1)*2048],base[(y*1024+960)*2:(y+1)*2048])

class Views(unittest.TestCase):
 def test_every_role_endpoints_help_and_page_switches_preserve_state(self):
  import ctypes as C
  from dataclasses import replace
  from loop_model import LoopModel,Layer
  from loop_engine import LoopEngine
  from loop_app import LoopInstrument
  from loop_graphics import render
  with tempfile.TemporaryDirectory() as home:
   m=LoopModel(Path(home)/'current.json',writer=False)
   e=LoopEngine(ROOT/'.build/engine.so');e.lib.sw_reset();i=LoopInstrument(m,e)
   for role in ROLE_IDS:
    for v in (0,1):
     m.state=replace(m.state,layers=(Layer(1,role,parameters=(v,)*8),),role_order=(role,)+tuple(r for r in ROLE_IDS if r!=role));state=m.state
     for page in ('instrument','overview','mixer','key','library','recordings','instrument'):
      i.open_page(page)
      for help_open in (False,True):
       i.help=help_open;raw=render(m,e.stats(),i);self.assertEqual(len(raw),327680)
       self.assertEqual(m.state,state)
     i.help=False

if __name__=='__main__':unittest.main()
