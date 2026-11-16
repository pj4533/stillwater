import copy
import ctypes as C
import errno
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Engine, Instrument
from bottle import Bottle, publish
from model import Model
ROOT=Path(__file__).resolve().parents[1]


class Capture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.m=Model(self.home/'current.json')
        self.e=Engine(ROOT/'.build/engine.so');self.e.lib.sw_reset()
        self.b=Bottle(self.e,self.home/'recordings');self.addCleanup(self.b.close)
        self.i=Instrument(self.m,self.e,self.b);self.e.sync(self.m)
        self.e.lib.sw_render.argtypes=[C.POINTER(C.c_float),C.c_int]
    def audio(self,seconds):
        n=round(seconds*44100);out=(C.c_float*(n*2))();self.e.lib.sw_render(out,n);return out
    def wait(self):
        self.b.worker.join(3);self.assertFalse(self.b.worker.is_alive());return self.b.snapshot()
    def test_short_startup_real_ordering_and_no_state_change(self):
        self.i.event('cc',50,127);self.i.event('note',60,100);expected=self.audio(.3)
        self.i.event('cc',29,127);quiet=self.audio(.5)
        old=(copy.deepcopy(self.m.state),copy.deepcopy(self.m.history),self.m.revision,self.m.playing)
        self.i.execute(dict(op='request_capture',seconds=30));result=self.wait()
        self.assertEqual(result['state'],'corked');self.assertAlmostEqual(result['seconds'],.8)
        self.assertEqual(old,(self.m.state,self.m.history,self.m.revision,self.m.playing))
        with wave.open(str(self.b.directory/result['filename']),'rb') as wav:
            self.assertEqual(wav.getparams()[:4],(2,2,44100,35280));pcm=struct.unpack('<%dh'%(35280*2),wav.readframes(35280))
        self.assertGreater(max(pcm),0);self.assertTrue(all(abs(x)<=8192 for x in pcm))
        for j in range(0,len(expected),101):self.assertLessEqual(abs(pcm[j]-round(expected[j]*32767)),1)
        for j in range(0,len(quiet),97):self.assertLessEqual(abs(pcm[len(expected)+j]-round(quiet[j]*32767)),1)
        self.assertEqual(max(map(abs,pcm[-512:])),0)
    def test_shift_save_capture_and_plain_save_remain_separate(self):
        self.audio(.1);self.i.event('cc',49,127);self.i.event('cc',82,127);self.i.event('cc',49,0)
        self.assertEqual(self.wait()['state'],'corked');self.assertFalse(self.m.path.exists())
        self.i.event('cc',82,127);self.assertTrue(self.m.path.exists())
    def test_request_schema_empty_history_and_limits(self):
        with self.assertRaisesRegex(ValueError,'No output'):self.b.request()
        for req in [dict(op='request_capture',seconds=31),dict(op='request_capture',seconds=True),dict(op='request_capture',seconds=.5),dict(op='request_capture',seconds=0),dict(op='request_capture',seconds=1,path='/tmp/x'),dict(op='query_capture_status',path='/tmp/x')]:
            with self.assertRaises(ValueError):self.i.execute(req)
        self.assertEqual(self.i.execute(dict(op='query_capture_status'))['state'],'idle')
    def test_wrap_maximum_and_generation_failure(self):
        self.m.playing=True;self.e.sync(self.m);pcm=self.audio(46)
        epoch,start,count=self.e.history_window(30);self.assertEqual((start,count),(16*44100,30*44100))
        data=self.e.history_copy(epoch,start,count)
        for j in range(0,len(data),997):self.assertLessEqual(abs(data[j]-round(pcm[start*2+j]*32767)),1)
        with self.assertRaises(ValueError):self.e.history_copy(epoch,0,44100)
        self.audio(16)
        with self.assertRaises(ValueError):self.e.history_copy(epoch,start,count)
        self.e.lib.sw_reset()
        with self.assertRaises(ValueError):self.e.history_copy(epoch,0,1)
    def test_concurrent_render_copy_is_original_or_explicit_failure(self):
        self.m.playing=True;self.e.sync(self.m);expected=self.audio(45)
        epoch,start,count=self.e.history_window(30)
        worker=threading.Thread(target=lambda:self.audio(20));worker.start()
        try:
            try:
                data=self.e.history_copy(epoch,start,count)
                for j in range(0,len(data),991):self.assertLessEqual(abs(data[j]-round(expected[start*2+j]*32767)),1)
            except ValueError as exc:self.assertIn('expired',str(exc))
        finally:worker.join(3)
        self.assertFalse(worker.is_alive())
    def test_busy_bounded_one_job_and_no_early_published_file(self):
        self.audio(.2);entered=threading.Event();release=threading.Event();original=self.e.history_copy
        def slow(*args):entered.set();release.wait(2);return original(*args)
        with patch.object(self.e,'history_copy',side_effect=slow):
            self.b.request(1);self.assertTrue(entered.wait(1))
            try:
                self.assertFalse(list(self.b.directory.glob('*.wav')))
                with self.assertRaisesRegex(ValueError,'busy'):self.b.request(1)
            finally:release.set()
            self.assertEqual(self.wait()['state'],'corked')
    def test_capture_busy_does_not_block_new_notes_or_stop_and_fixes_endpoint(self):
        self.audio(.2);entered=threading.Event();release=threading.Event();original=self.e.history_copy
        def slow(*args):entered.set();release.wait(2);return original(*args)
        with patch.object(self.e,'history_copy',side_effect=slow):
            self.i.execute(dict(op='request_capture',seconds=30));self.assertTrue(entered.wait(1))
            try:
                self.i.event('cc',50,127);self.i.event('note',60,100)
                active=self.audio(.2);self.assertGreater(max(map(abs,active)),0)
                self.i.event('cc',29,127);quiet=self.audio(.4)
                self.assertEqual(max(map(abs,quiet[-512:])),0);self.assertTrue(self.b.snapshot()['busy'])
            finally:release.set()
            status=self.wait()
        with wave.open(str(self.b.directory/status['filename']),'rb') as wav:
            self.assertEqual(wav.getnframes(),8820);self.assertEqual(set(wav.readframes(8820)),{0})
    def test_disk_space_write_failure_and_collision_leave_no_partial_capture(self):
        self.audio(.2)
        with patch('bottle.shutil.disk_usage',return_value=type('Disk',(),{'free':0})()):
            self.b.request(1);self.assertEqual(self.wait()['state'],'error')
        with patch('bottle.wave.Wave_write.writeframes',side_effect=OSError(errno.ENOSPC,'disk full')):
            self.b.request(1);self.assertEqual(self.wait()['state'],'error')
        self.assertFalse(list(self.b.directory.iterdir()))
        old=self.b.directory/'existing.wav';old.write_bytes(b'preserve me')
        with patch.object(self.b,'filename',return_value='existing.wav'):
            self.b.request(1);self.assertEqual(self.wait()['state'],'error')
        self.assertEqual(old.read_bytes(),b'preserve me');self.assertEqual(list(self.b.directory.iterdir()),[old])
    def test_export_overrun_does_not_publish(self):
        self.audio(.1)
        with patch.object(self.e,'history_copy',side_effect=ValueError('History expired')):
            self.b.request(1);self.assertEqual(self.wait()['state'],'error')
        self.assertFalse(list(self.b.directory.iterdir()))
    def test_atomic_publisher_does_not_overwrite(self):
        temp=self.home/'temp';final=self.home/'final';temp.write_bytes(b'new');final.write_bytes(b'old')
        with self.assertRaises(FileExistsError):publish(temp,final)
        self.assertEqual(final.read_bytes(),b'old')
    def test_cleanup_owns_busy_worker_and_shutdown_closes_admission(self):
        self.audio(.1);entered=threading.Event();release=threading.Event();unlink=Path.unlink
        def blocked(path,*args,**kwargs):
            if path.suffix=='.part':entered.set();release.wait(2)
            return unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',blocked):
            self.b.request(1);owned=self.b.worker;self.assertTrue(entered.wait(1))
            try:
                self.assertTrue(self.b.snapshot()['busy']);self.assertEqual(self.b.snapshot()['state'],'filling')
                with self.assertRaisesRegex(ValueError,'busy'):self.b.request(1)
                self.assertIs(self.b.worker,owned)
                joining=threading.Event();join=owned.join
                def observed_join(*args,**kwargs):joining.set();return join(*args,**kwargs)
                with patch.object(owned,'join',side_effect=observed_join):
                    closing=threading.Thread(target=self.b.close);closing.start()
                    self.assertTrue(joining.wait(1))
                # Admission is closed before close joins the original worker.
                self.assertTrue(self.b.closed)
                with self.assertRaisesRegex(ValueError,'shutting down'):self.b.request(1)
                self.assertTrue(closing.is_alive());self.assertIs(self.b.worker,owned)
            finally:release.set()
            closing.join(3);self.assertFalse(closing.is_alive());self.assertFalse(owned.is_alive())
        self.assertFalse(self.b.snapshot()['busy']);self.assertEqual(self.b.snapshot()['state'],'corked')
    def test_fallback_published_file_survives_cleanup_error_with_warning(self):
        self.audio(.1);unlink=Path.unlink
        def denied(path,*args,**kwargs):
            if path.suffix=='.part':raise PermissionError(errno.EACCES,'cleanup denied')
            return unlink(path,*args,**kwargs)
        with patch('bottle.C.CDLL',return_value=object()),patch.object(Path,'unlink',denied):
            self.b.request(1);status=self.wait()
        self.assertEqual(status['state'],'corked');self.assertFalse(status['busy'])
        self.assertIsNone(status['error']);self.assertIn('cleanup',status['warning'])
        with wave.open(str(self.b.directory/status['filename']),'rb') as wav:self.assertEqual(wav.getnframes(),4410)
        self.assertEqual(len(list(self.b.directory.glob('*.wav'))),1)
        self.assertEqual(len(list(self.b.directory.glob('*.part'))),1)
        # A fallback collision must never delete or modify another writer's file.
        existing=self.b.directory/'other.wav';existing.write_bytes(b'other process')
        with patch('bottle.C.CDLL',return_value=object()),patch.object(self.b,'filename',return_value=existing.name):
            self.b.request(1);self.assertEqual(self.wait()['state'],'error')
        self.assertEqual(existing.read_bytes(),b'other process')
    def test_published_wav_directory_durability_failure_is_reported(self):
        self.audio(.1)
        import os
        fsync=os.fsync;calls=[]
        def directory_failure(fd):
            calls.append(fd)
            if len(calls)==2:raise OSError(errno.EIO,'directory sync failed')
            return fsync(fd)
        with patch('bottle.os.fsync',side_effect=directory_failure):
            self.b.request(1);status=self.wait()
        self.assertEqual(status['state'],'corked');self.assertIsNone(status['error'])
        self.assertIn('durability not confirmed',status['warning'])
        with wave.open(str(self.b.directory/status['filename']),'rb') as wav:self.assertEqual(wav.getnframes(),4410)
        self.assertFalse(list(self.b.directory.glob('*.part')))
