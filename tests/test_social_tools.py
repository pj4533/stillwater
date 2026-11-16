"""Portable editor admission keeps source captures read-only and correctly timed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('social_gentle_edit',ROOT/'scripts/social-gentle-edit.py')
edit=importlib.util.module_from_spec(spec);spec.loader.exec_module(edit)

class SocialTools(unittest.TestCase):
    def test_wrong_source_timing_rejected_before_decode(self):
        probe={'streams':[{'codec_type':'video','width':960,'height':160,'avg_frame_rate':'30/1'},
                          {'codec_type':'audio','sample_rate':'44100','channels':2}]}
        with patch.object(edit.subprocess,'check_output',return_value=json.dumps(probe).encode()) as run:
            with self.assertRaisesRegex(AssertionError,'10fps'):edit.decode()
            self.assertEqual(run.call_count,1)

    def test_source_cannot_be_overwritten_by_editor(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'picture.mp4';source.write_bytes(b'capture must remain unchanged')
            with patch('sys.argv',['edit','--source',str(source),'--output-dir',temp,'--gain-db','0']),patch.object(edit,'decode') as decode:
                with self.assertRaisesRegex(AssertionError,'read-only'):edit.main()
                decode.assert_not_called()
            self.assertEqual(source.read_bytes(),b'capture must remain unchanged')
