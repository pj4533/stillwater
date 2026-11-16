"""Hermetic stock-to-Stillwater transition; no real processes/device paths used."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class SwitchOwnership(unittest.TestCase):
    def run_switch(self,pidfile,owners,quit_live=True):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        home=Path(temp.name)
        for name in owners:(home/(name+'.alive')).touch()
        if pidfile!='absent':(home/'launcher.pid').write_text('424242\n')
        if pidfile=='valid':(home/'launcher.alive').touch()
        (home/'app').mkdir();(home/'reboot-marker').write_bytes(b'preserve on refusal')
        reboot=home/'quit-stock'
        reboot.write_text('#!/bin/sh\nprintf "quit\\n" >> "$FIXTURE/trace"\n'+('rm -f "$FIXTURE/Live.alive"\n' if quit_live else ''))
        reboot.chmod(0o755)
        init=home/'init-stock'
        init.write_text('#!/bin/sh\nprintf "init %s\\n" "$*" >> "$FIXTURE/trace"\n');init.chmod(0o755)
        script=(ROOT/'scripts/switch-to-stillwater.sh').read_text()
        replacements={'/data/push-ambient':str(home/'app'),'/var/lib/push3.pid':str(home/'launcher.pid'),'/opt/push3/reboot.sh':str(reboot),'/data/settings/.reboot':str(home/'reboot-marker'),'/etc/init.d/push3':str(init)}
        for old,new in replacements.items():script=script.replace(old,new)
        # Override the shell builtin as well as external owner commands. No real
        # signal, sleep, device path, MIDI/USB/audio or stock service is reachable.
        fixtures='''pidof() { [ -f "$FIXTURE/$1.alive" ]; }
kill() {
 if [ "$1" = -0 ]; then [ -f "$FIXTURE/launcher.alive" ];
 else printf 'kill %s\\n' "$*" >> "$FIXTURE/trace"; rm -f "$FIXTURE/launcher.alive"; fi
}
killall() { printf 'killall %s\\n' "$*" >> "$FIXTURE/trace"; rm -f "$FIXTURE/Push3.alive"; }
sleep() { :; }
'''
        result=subprocess.run(['/bin/sh','-c',fixtures+script],env=dict(os.environ,FIXTURE=str(home)),capture_output=True,text=True,timeout=5)
        trace=(home/'trace').read_text().splitlines() if (home/'trace').exists() else []
        return home,result,trace

    def test_absent_or_stale_pidfile_checks_every_owner_before_side_effects(self):
        for pidfile in ('absent','stale'):
            for owners in (('Live',),('Push3',),('Live','Push3'),()):
                with self.subTest(pidfile=pidfile,owners=owners):
                    home,result,trace=self.run_switch(pidfile,owners)
                    if owners:
                        self.assertNotEqual(result.returncode,0)
                        self.assertIn('still owned',result.stderr)
                        self.assertEqual((home/'reboot-marker').read_bytes(),b'preserve on refusal')
                        self.assertFalse((home/'app/enabled').exists());self.assertEqual(trace,[])
                        self.assertTrue(all((home/(name+'.alive')).exists() for name in owners))
                    else:
                        self.assertEqual(result.returncode,0,result.stderr)
                        self.assertFalse((home/'reboot-marker').exists())
                        self.assertTrue((home/'app/enabled').exists());self.assertEqual(trace,['init start'])

    def test_valid_launcher_gracefully_quits_live_before_surface_stop_and_start(self):
        home,result,trace=self.run_switch('valid',('Live','Push3'))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(trace,['quit','kill -TERM 424242','killall -TERM Push3','init start'])
        self.assertFalse((home/'Live.alive').exists());self.assertFalse((home/'Push3.alive').exists())
        self.assertFalse((home/'reboot-marker').exists());self.assertTrue((home/'app/enabled').exists())

    def test_live_not_quitting_preserves_markers_and_does_not_stop_surface(self):
        home,result,trace=self.run_switch('valid',('Live','Push3'),quit_live=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('did not quit gracefully',result.stderr);self.assertEqual(trace,['quit'])
        self.assertTrue((home/'launcher.alive').exists());self.assertTrue((home/'Push3.alive').exists())
        self.assertEqual((home/'reboot-marker').read_bytes(),b'preserve on refusal')
        self.assertFalse((home/'app/enabled').exists())
