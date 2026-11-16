import ctypes as C
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Engine, Instrument
from model import Model
from recorder import SessionRecorder, FRAME_BYTES, SR, TICK, encoder_argv
from graphics import render
ROOT=Path(__file__).resolve().parents[1]


class Recording(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'.build');self.addCleanup(self.temp.cleanup);self.home=Path(self.temp.name)
        self.e=Engine(ROOT/'.build/engine.so');self.e.lib.sw_reset();self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
        self.r=SessionRecorder(self.e,self.home/'recordings');self.addCleanup(self.r.close)
        self.m=Model(self.home/'current.json');self.i=Instrument(self.m,self.e,recorder=self.r);self.e.sync(self.m)
        self.frame=bytes(FRAME_BYTES);self.r.displayed(self.frame)
    def audio(self,n):
        block=(C.c_float*(n*2))();self.e.lib.sw_render(block,n);return block
    def wait(self):
        self.r.worker.join(5);self.assertFalse(self.r.worker.is_alive());return self.r.snapshot()
    def noencode(self,path,data):return None
    def test_record_help_controls_do_not_touch_transport_or_state(self):
        self.i.event('cc',50,127)
        old=(self.m.state.copy(),self.m.revision,list(self.m.history));self.m.playing=True;self.e.sync(self.m)
        self.i.event('cc',81,127);self.assertTrue(self.i.help)
        self.i.event('note',60,100);self.audio(TICK)
        self.assertTrue(any(v['held'] for v in self.e.stats()['manual']))
        with patch.object(self.r,'_encode',side_effect=self.noencode):
            self.i.event('cc',86,127);self.assertTrue(self.m.playing);self.audio(TICK)
            self.r.displayed(render(self.m,0,0));self.i.event('cc',86,127);self.assertTrue(self.m.playing)
            self.assertEqual(self.wait()['state'],'ready')
        self.assertEqual(old,(self.m.state,self.m.revision,self.m.history))
        self.i.event('cc',29,127);self.assertFalse(self.m.playing)
        self.i.event('cc',81,127);self.assertFalse(self.i.help)
    def test_sample_clock_irregular_frames_and_latest_ties(self):
        with patch.object(self.r,'_encode',side_effect=self.noencode):
            self.r.start();start=self.r.started
            self.audio(2000);self.r.displayed(bytes([1])*FRAME_BYTES)
            self.r.displayed(bytes([2])*FRAME_BYTES)
            self.audio(8000);self.r.displayed(bytes([3])*FRAME_BYTES)
            self.audio(1001);self.r.stop();self.assertEqual(self.wait()['state'],'ready')
        p=self.r.directory/'jobs'/self.r.status['job'];data=json.loads((p/'metadata.json').read_text())
        self.assertEqual(data['audio_frames'],11001);self.assertEqual(data['video_frames'],3)
        with (p/'screen.bgr565').open('rb') as stream:
            self.assertEqual([stream.read(FRAME_BYTES)[0] for _ in range(3)],[0,2,2])
        self.assertEqual((p/'audio.s16le').stat().st_size,11001*4)
        self.assertEqual(data['start'],start)
    def test_schema_and_busy(self):
        for req in [dict(op='record_start',path='/tmp/x'),dict(op='record_stop',extra=1),dict(op='record_status',value=1),dict(op='record_recover',job='../x')]:
            with self.assertRaises(ValueError):self.r.execute(req)
        self.r.start()
        with self.assertRaisesRegex(ValueError,'busy'):self.r.start()
        self.r.close(.1)
        with self.assertRaisesRegex(ValueError,'shutting down'):self.r.start()
    def test_queue_overflow_retains_explicit_error(self):
        entered=threading.Event();release=threading.Event();original=self.e.history_copy
        def blocked(*args):entered.set();release.wait(2);return original(*args)
        with patch.object(self.e,'history_copy',side_effect=blocked):
            self.r.start();self.audio(TICK);self.r.displayed(self.frame);self.assertTrue(entered.wait(1))
            for _ in range(9):self.r.displayed(self.frame)
            release.set();self.assertEqual(self.wait()['state'],'error')
        self.assertIn('overflow',self.r.status['error']);self.assertFalse(list(self.r.directory.glob('*.mp4')))
    def test_epoch_reset_and_history_overrun_fail(self):
        self.r.start();self.e.lib.sw_reset();self.assertEqual(self.wait()['state'],'error')
        self.assertIn('epoch',self.r.status['error'])
        self.r=SessionRecorder(self.e,self.home/'overrun');self.addCleanup(self.r.close);self.r.displayed(self.frame)
        entered=threading.Event();release=threading.Event();original=self.e.history_copy
        def blocked(*args):entered.set();release.wait(3);return original(*args)
        with patch.object(self.e,'history_copy',side_effect=blocked):
            self.r.start();self.audio(TICK);self.r.displayed(self.frame);self.assertTrue(entered.wait(1))
            self.audio(46*SR);release.set();self.assertEqual(self.wait()['state'],'error')
        self.assertIn('expired',self.r.status['error'])
    def test_disk_admission_and_runtime_reserve(self):
        with patch('recorder.shutil.disk_usage',return_value=type('Disk',(),{'free':0})()):
            self.r.start();self.assertEqual(self.wait()['state'],'error')
        self.assertIn('1GiB',self.r.status['error'])
        self.r=SessionRecorder(self.e,self.home/'reserve');self.addCleanup(self.r.close);self.r.displayed(self.frame)
        def space(path):return type('Disk',(),{'free':2**31 if not (Path(path)/'audio.s16le').exists() else 0})()
        with patch('recorder.shutil.disk_usage',side_effect=space):
            self.r.start();self.audio(TICK);self.r.displayed(self.frame);self.assertEqual(self.wait()['state'],'error')
        self.assertIn('reserve',self.r.status['error'])
    def test_encoder_failure_and_restart_recovery(self):
        with patch.object(self.r,'_encode',side_effect=RuntimeError('encoder failed')):
            self.r.start();self.audio(TICK*2);self.r.displayed(self.frame);self.r.stop();self.assertEqual(self.wait()['state'],'error')
        job=self.r.status['job'];p=self.r.directory/'jobs'/job;data=json.loads((p/'metadata.json').read_text())
        data['state']='saving';(p/'metadata.json').write_text(json.dumps(data))
        r=SessionRecorder(self.e,self.r.directory);self.addCleanup(r.close)
        self.assertEqual(json.loads((p/'metadata.json').read_text())['state'],'interrupted')
        with patch.object(r,'_encode',side_effect=self.noencode):
            r.recover(job);r.worker.join(3);self.assertEqual(r.status['state'],'ready')
        with self.assertRaises(ValueError):r.recover('../../x')
    def test_shutdown_terminates_owned_encoder_and_stops_admission(self):
        entered=threading.Event()
        def hang(path,data):entered.set();self.r._run([sys.executable,'-c','import time;time.sleep(60)'],path,60,'hang')
        with patch.object(self.r,'_encode',side_effect=hang):
            self.r.start();self.audio(TICK);self.r.displayed(self.frame);self.r.stop();self.assertTrue(entered.wait(1))
            deadline=time.monotonic()+1
            while self.r.process is None and time.monotonic()<deadline:time.sleep(.005)
            proc=self.r.process;self.assertIsNotNone(proc)
            start=time.monotonic();self.r.close(.6);self.assertLess(time.monotonic()-start,1.2)
            self.assertIsNotNone(proc.poll());self.assertEqual(self.wait()['state'],'error')
        with self.assertRaisesRegex(ValueError,'shutting down'):self.r.start()
    def test_shutdown_with_blocked_io_keeps_music_stoppable(self):
        entered=threading.Event();release=threading.Event();original=self.e.history_copy
        def blocked(*args):entered.set();release.wait(2);return original(*args)
        with patch.object(self.e,'history_copy',side_effect=blocked):
            self.r.start();self.audio(TICK);self.r.displayed(self.frame);self.assertTrue(entered.wait(1))
            start=time.monotonic();self.r.close(.1);self.assertLess(time.monotonic()-start,.5)
            self.i.event('cc',29,127);pcm=self.audio(SR//2);self.assertEqual(max(map(abs,pcm[-512:])),0)
            self.assertTrue(self.r.worker.is_alive());release.set();self.wait()
        self.assertTrue(self.r.closed)
    def test_fixed_encoder_arguments_and_padding_crop(self):
        argv=encoder_argv(['/usr/bin/ffmpeg'],Path('v'),Path('a'),Path('p'),SR)
        self.assertIn('libx264',argv);self.assertEqual(argv[argv.index('-video_size')+1],'1024x160')
        self.assertIn('crop=960:160:0:0',argv[argv.index('-vf')+1]);self.assertIn('1.000000000',argv)
    def test_xrun_and_clock_stall_are_explicit_failures(self):
        self.r.start()
        with patch.object(self.e,'stats',return_value={'xruns':1}):
            self.assertEqual(self.wait()['state'],'error')
        self.assertIn('xrun',self.r.status['error'])
        r=SessionRecorder(self.e,self.home/'stall');self.addCleanup(r.close);r.displayed(self.frame)
        with patch('recorder.time.monotonic',side_effect=[0,0,0,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4]):
            r.start();r.worker.join(1)
        self.assertFalse(r.worker.is_alive());self.assertIn('stalled',r.status['error'])
    def test_limit_auto_stops_without_transport_change(self):
        with patch('recorder.MAX_FRAMES',TICK*2),patch.object(self.r,'_encode',side_effect=self.noencode):
            self.r.start();self.audio(TICK*3);self.r.displayed(self.frame)
            self.assertEqual(self.wait()['state'],'ready')
        self.assertEqual(self.r.status['seconds'],.2)
    def test_stop_clips_works_during_encode(self):
        entered=threading.Event();release=threading.Event()
        def saving(path,data):entered.set();release.wait(2)
        with patch.object(self.r,'_encode',side_effect=saving):
            self.i.event('cc',50,127);self.i.event('note',60,100)
            self.r.start();self.audio(TICK);self.r.displayed(self.frame);self.r.stop();self.assertTrue(entered.wait(1))
            try:
                self.i.event('cc',29,127);quiet=self.audio(SR//2);self.assertEqual(max(map(abs,quiet[-512:])),0)
            finally:release.set()
            self.assertEqual(self.wait()['state'],'ready')
    def test_encode_publication_collision_preserves_other_file(self):
        # Exercise real no-replace publication after mocked child/probe results.
        from recorder import encoder_argv
        self.r.directory.mkdir(parents=True);path=self.r.directory/'fixture';path.mkdir()
        job='film-'+'a'*12;other=self.r.directory/(job+'.mp4');other.write_bytes(b'other writer')
        def run(argv,path,timeout,label):
            if label=='encode':Path(argv[-1]).write_bytes(b'complete MP4'*100)
            if label=='probe':(path/'probe.stdout').write_text(json.dumps({'streams':[{'codec_type':'video','codec_name':'h264','width':960,'height':160,'sample_aspect_ratio':'1:1','r_frame_rate':'10/1'},{'codec_type':'audio','codec_name':'aac','sample_rate':'44100','channels':2}],'format':{'duration':'1'}}))
        with patch.object(self.r,'_run',side_effect=run):
            with self.assertRaises(FileExistsError):self.r._encode(path,{'job':job,'audio_frames':SR})
        self.assertEqual(other.read_bytes(),b'other writer')
    def test_production_shutdown_quiets_before_shared_capture_wait(self):
        from app import quiet_and_close
        from unittest.mock import Mock
        events=[]
        self.i.event('cc',50,127);self.i.event('note',60,100);self.audio(TICK)
        engine_close=self.e.close
        def closed():events.append('audio closed');engine_close()
        def recording_close(timeout):
            events.append('recorder');self.assertEqual(events[0],'audio closed');time.sleep(.03)
        def bottle_close(timeout):events.append(('bottle',timeout))
        with patch.object(self.e,'close',side_effect=closed):
            quiet_and_close(self.i,self.e,Mock(close=recording_close),Mock(close=bottle_close),timeout=.05)
        self.assertFalse(self.m.playing);self.assertLess(events[-1][1],.03)
    def test_valid_mp4_publication_reports_cleanup_warning(self):
        self.r.directory.mkdir(parents=True);path=self.r.directory/'fixture';path.mkdir();unlink=Path.unlink
        def run(argv,path,timeout,label):
            if label=='encode':Path(argv[-1]).write_bytes(b'complete MP4'*100)
            if label=='probe':(path/'probe.stdout').write_text(json.dumps({'streams':[{'codec_type':'video','codec_name':'h264','width':960,'height':160,'sample_aspect_ratio':'1:1','r_frame_rate':'10/1'},{'codec_type':'audio','codec_name':'aac','sample_rate':'44100','channels':2}],'format':{'duration':'1'}}))
        def denied(path,*args,**kwargs):
            if path.suffix=='.part':raise PermissionError('temp cleanup denied')
            return unlink(path,*args,**kwargs)
        with patch.object(self.r,'_run',side_effect=run),patch('bottle.C.CDLL',return_value=object()),patch.object(Path,'unlink',denied):
            warning=self.r._encode(path,{'job':'film-'+'b'*12,'audio_frames':SR})
        self.assertIn('cleanup',warning);self.assertTrue((self.r.directory/('film-'+'b'*12+'.mp4')).exists())
    def test_stop_endpoint_does_not_grow_while_queue_drains(self):
        entered=threading.Event();release=threading.Event();original=self.e.history_copy
        def blocked(*args):entered.set();release.wait(2);return original(*args)
        with patch.object(self.r,'_encode',side_effect=self.noencode),patch.object(self.e,'history_copy',side_effect=blocked):
            self.r.start();self.audio(TICK);self.r.displayed(self.frame);self.assertTrue(entered.wait(1))
            self.audio(TICK);self.r.displayed(self.frame);self.audio(TICK);self.r.displayed(self.frame)
            self.r.stop();self.audio(TICK*5);self.r.displayed(self.frame);release.set();self.wait()
        p=self.r.directory/'jobs'/self.r.status['job'];data=json.loads((p/'metadata.json').read_text())
        self.assertEqual(data['audio_frames'],TICK*3);self.assertEqual(data['video_frames'],3)
        self.assertEqual((p/'audio.s16le').stat().st_size,TICK*3*4)
    def test_recovery_disk_validation_does_not_block_ui(self):
        entered=threading.Event();release=threading.Event()
        def blocked(job):entered.set();release.wait(2);raise ValueError('No recoverable job')
        with patch.object(self.r,'_load_recovery',side_effect=blocked):
            start=time.monotonic();self.r.recover('film-'+'c'*12);self.assertLess(time.monotonic()-start,.2)
            self.assertTrue(entered.wait(1));self.r.displayed(self.frame)
            self.i.event('cc',29,127);self.assertFalse(self.m.playing)
            release.set();self.assertEqual(self.wait()['state'],'error')
    def test_checkpoint_keeps_recoverable_av_prefix_when_audio_leads(self):
        self.r.start();self.audio(SR);self.r.displayed(self.frame);self.audio(SR)
        path=self.r.directory/'jobs'/self.r.status['job'];deadline=time.monotonic()+2;data={}
        while time.monotonic()<deadline:
            try:data=json.loads((path/'metadata.json').read_text())
            except (OSError,ValueError):pass
            if data.get('audio_frames')==SR:break
            time.sleep(.01)
        self.assertEqual(data.get('audio_frames'),SR);self.assertEqual(data['video_frames'],10)
        self.assertGreaterEqual((path/'audio.s16le').stat().st_size,2*SR*4)
        self.r.close();self.assertFalse(self.r.worker.is_alive())
        with patch.object(self.r,'_encode',side_effect=self.noencode):
            # Closed recorder cannot reopen admission; a new one may recover.
            r=SessionRecorder(self.e,self.r.directory);self.addCleanup(r.close)
            with patch.object(r,'_encode',side_effect=self.noencode):r.recover(data['job']);r.worker.join(2)
        self.assertEqual(r.status['state'],'ready');self.assertEqual(r.status['seconds'],1)
    def test_partial_pcm_disk_write_is_not_published(self):
        opened=Path.open
        class FullDisk:
            def __init__(self,stream):self.stream=stream
            def __getattr__(self,name):return getattr(self.stream,name)
            def write(self,data):
                self.stream.write(data[:100]);raise OSError('ENOSPC simulated partial PCM write')
        def file_open(path,*args,**kwargs):
            stream=opened(path,*args,**kwargs)
            return FullDisk(stream) if path.name=='audio.s16le' and args==('xb',) else stream
        with patch.object(Path,'open',file_open):
            self.r.start();self.audio(TICK);self.r.displayed(self.frame);self.assertEqual(self.wait()['state'],'error')
        self.assertIn('ENOSPC',self.r.status['error']);self.assertFalse(list(self.r.directory.glob('*.mp4')))
        path=self.r.directory/'jobs'/self.r.status['job']
        self.assertEqual((path/'audio.s16le').stat().st_size,0)
    def test_worker_start_failure_is_retryable_and_close_safe(self):
        with patch('recorder.threading.Thread.start',side_effect=RuntimeError('no threads')):
            with self.assertRaisesRegex(ValueError,'could not start'):self.r.start()
        self.assertEqual(self.r.status['state'],'error');self.assertFalse(self.r.snapshot()['busy'])
        self.assertIsNone(self.r.worker)
        with patch.object(self.r,'_encode',side_effect=self.noencode):
            self.r.start();self.audio(TICK);self.r.displayed(self.frame);self.r.stop();self.assertEqual(self.wait()['state'],'ready')

class RealRecordingPublication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir=ROOT/'.build');cls.fixture=Path(cls.temp.name)/'fixture.mp4'
        subprocess.run(['/usr/bin/ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=960x160:rate=10',
                        '-f','lavfi','-i','sine=frequency=220:sample_rate=44100','-t','12','-c:v','libx264',
                        '-threads','1','-preset','veryfast','-pix_fmt','yuv420p','-bf','0','-g','20',
                        '-c:a','aac','-ac','2',str(cls.fixture)],check=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        import shutil
        self.copy=shutil.copyfile
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'.build');self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.e=Engine(ROOT/'.build/engine.so')
        self.r=SessionRecorder(self.e,self.home);self.addCleanup(self.r.close)
        self.job='film-'+'d'*12;self.path=self.home/'jobs'/self.job;self.path.mkdir(parents=True)
        self.data=dict(version=1,job=self.job,state='saving',start=0,endpoint=12*SR,audio_frames=12*SR,video_frames=120)
        for name,size in [('audio.s16le',12*SR*4),('screen.bgr565',120*FRAME_BYTES)]:
            with (self.path/name).open('wb') as stream:stream.truncate(size)
    def encode_fixture(self,fixture):
        run=self.r._run
        def child(argv,path,timeout,label):
            if label=='encode':self.copy(fixture,argv[-1])
            else:run(argv,path,timeout,label)
        with patch.object(self.r,'_run',side_effect=child):return self.r._encode(self.path,self.data)
    def test_real_damaged_h264_packet_rejected_and_raw_retained(self):
        damaged=self.home/'damaged.mp4';self.copy(self.fixture,damaged)
        packets=json.loads(subprocess.check_output(['/usr/bin/ffprobe','-v','error','-select_streams','v:0',
                           '-show_packets','-show_entries','packet=pos,size','-of','json',str(damaged)]))['packets']
        packet=packets[100];self.assertGreater(int(packet['size']),100)
        with damaged.open('r+b') as stream:
            stream.seek(int(packet['pos'])+10);blob=stream.read(50);stream.seek(-50,1)
            stream.write(bytes(value^255 for value in blob))
        # Demonstrate the old non-strict decoder reports corruption but exits 0.
        old=subprocess.run(['/usr/bin/ffmpeg','-nostdin','-v','error','-threads','1','-i',str(damaged),'-f','null','-'],capture_output=True)
        self.assertEqual(old.returncode,0);self.assertTrue(old.stderr)
        with self.assertRaisesRegex(RuntimeError,'decode failed'):self.encode_fixture(damaged)
        self.assertFalse((self.home/(self.job+'.mp4')).exists())
        self.assertEqual((self.path/'audio.s16le').stat().st_size,12*SR*4)
        self.assertEqual((self.path/'screen.bgr565').stat().st_size,120*FRAME_BYTES)
        self.assertNotIn('publication',self.data)
    def test_real_publication_crash_window_recovers_matching_file_without_encode(self):
        self.encode_fixture(self.fixture) # Publication completed; no ready checkpoint.
        final=self.home/(self.job+'.mp4');before=final.stat();original=final.read_bytes()
        self.assertEqual(json.loads((self.path/'metadata.json').read_text())['state'],'saving')
        restarted=SessionRecorder(self.e,self.home);self.addCleanup(restarted.close);run=restarted._run;labels=[]
        def child(argv,path,timeout,label):labels.append(label);run(argv,path,timeout,label)
        with patch.object(restarted,'_run',side_effect=child):
            restarted.recover(self.job);restarted.worker.join(10)
        self.assertFalse(restarted.worker.is_alive());self.assertEqual(restarted.status['state'],'ready')
        self.assertEqual(restarted.status['filename'],final.name);self.assertEqual(labels,['probe','decode'])
        self.assertEqual(final.read_bytes(),original);self.assertEqual(final.stat().st_ino,before.st_ino)
        self.assertEqual(final.stat().st_mtime_ns,before.st_mtime_ns)
    def test_real_publication_hash_mismatch_preserves_collision(self):
        self.encode_fixture(self.fixture);final=self.home/(self.job+'.mp4')
        with final.open('r+b') as stream:stream.seek(-1,2);last=stream.read(1);stream.seek(-1,2);stream.write(bytes([last[0]^1]))
        original=final.read_bytes();restarted=SessionRecorder(self.e,self.home);self.addCleanup(restarted.close)
        restarted.recover(self.job);restarted.worker.join(5)
        self.assertEqual(restarted.status['state'],'error');self.assertIsNone(restarted.status['filename'])
        self.assertIn('collision',restarted.status['error']);self.assertEqual(final.read_bytes(),original)
