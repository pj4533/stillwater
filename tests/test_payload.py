"""Standalone payload preparation must never copy private instrument state."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_home',ROOT/'scripts/prepare-home.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)

class PayloadTests(unittest.TestCase):
    def test_fresh_payload_selects_runtime_only_and_preserves_existing_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'source';root.mkdir()
            for name in ('src','scripts','assets','sessions','recordings','recovery'):
                (root/name).mkdir();(root/name/'fixture').write_text(name)
            (root/'src/__pycache__').mkdir();(root/'src/__pycache__/private.pyc').write_bytes(b'cache')
            engine=root/'native.so';engine.write_bytes(b'native fixture')
            target=Path(temp)/'payload'
            with patch.object(prepare,'ROOT',root),patch.object(sys,'argv',['prepare-home',str(target),'--engine',str(engine)]):
                prepare.main()
                self.assertEqual({p.name for p in target.iterdir()},{'src','scripts','assets','engine.so'})
                self.assertFalse((target/'src/__pycache__').exists())
                self.assertEqual((target/'engine.so').read_bytes(),b'native fixture')
                (target/'sentinel').write_bytes(b'current music')
                with self.assertRaises(SystemExit):prepare.main()
                self.assertEqual((target/'sentinel').read_bytes(),b'current music')

    def test_incomplete_encoder_bundle_rejected_before_destination_created(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);engine=root/'native.so';engine.write_bytes(b'native')
            tools=root/'tools';tools.mkdir();(tools/'ffmpeg').write_bytes(b'partial')
            target=root/'payload'
            with patch.object(sys,'argv',['prepare-home',str(target),'--engine',str(engine),'--tools',str(tools)]):
                with self.assertRaises(SystemExit):prepare.main()
            self.assertFalse(target.exists())

    def test_v4_payload_contains_all_paired_runtime_assets_and_matching_source(self):
        import hashlib
        import json
        manifest=json.loads((ROOT/'docs/runtime-manifest.json').read_text())
        self.assertEqual(manifest['native_abi'],5)
        self.assertEqual(len(manifest['runtime_files']),45)
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);engine=base/'engine.so';engine.write_bytes(b'isolated native fixture')
            target=base/'payload'
            with patch.object(sys,'argv',['prepare-home',str(target),'--engine',str(engine)]):prepare.main()
            for name,digest in manifest['runtime_files'].items():
                self.assertTrue((target/name).is_file(),name)
                self.assertEqual(hashlib.sha256((target/name).read_bytes()).hexdigest(),digest,name)
            for role in ('silt','filament','glass','choir','oxide','backwash','spore','prism'):
                self.assertEqual((target/'assets/v4'/(role+'.poses')).stat().st_size,5570560)
                self.assertEqual((target/'assets/v4'/(role+'.working')).stat().st_size,327680)
