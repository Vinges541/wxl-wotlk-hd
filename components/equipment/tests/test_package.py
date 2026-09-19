import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from wxl_equipment.assets import encode_blp,sha
from wxl_equipment.client_blp import to_runtime
from wxl_equipment.package import PATCH,install,rollback,validate

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.client=self.root/'client';(self.client/'Data').mkdir(parents=True)
        (self.client/'Wow.exe').write_bytes(b'synthetic')
        self.package=self.root/'package';self.asset='Item/ObjectComponents/Weapon/Test.blp'
        dest=self.package/PATCH/self.asset;dest.parent.mkdir(parents=True);data,_=to_runtime(encode_blp(Image.new('RGBA',(4,4),(20,40,60,128))));dest.write_bytes(data)
        (self.package/'manifest.json').write_text(json.dumps({'schema':1,'patch':PATCH,'files':{self.asset:sha(data)}}))
    def test_preview_apply_rollback(self):
        self.assertEqual(install(self.client,self.package)['state'],'preview')
        self.assertFalse((self.client/'Data'/PATCH).exists())
        with patch('wxl_equipment.package.stopped'):
            result=install(self.client,self.package,True)
            checkpoint=Path(result['checkpoint'])
            self.assertEqual(install(self.client,self.package,True)['state'],'already-installed')
            self.assertEqual(rollback(self.client,checkpoint)['state'],'rollback-preview')
            self.assertEqual(rollback(self.client,checkpoint,True)['state'],'rolled-back')
            self.assertTrue((checkpoint.parent/'removed-patch'/self.asset).is_file())
    def test_running_blocks_and_later_changes_block_rollback(self):
        with patch('wxl_equipment.package.stopped',side_effect=RuntimeError('running')):
            with self.assertRaises(RuntimeError):install(self.client,self.package,True)
        with patch('wxl_equipment.package.stopped'):
            result=install(self.client,self.package,True)
        (self.client/'Data'/PATCH/self.asset).write_bytes(b'later edit')
        with self.assertRaises(ValueError):rollback(self.client,Path(result['checkpoint']),True)
    def test_conflicting_overlay_and_symlink(self):
        dest=self.client/'Data'/'Patch-ModernRaces-HD.MPQ'/self.asset;dest.parent.mkdir(parents=True);dest.write_bytes(b'other task')
        with self.assertRaises(ValueError):install(self.client,self.package)
        dest.unlink();dest.symlink_to(self.package/PATCH/self.asset)
        with self.assertRaises(ValueError):install(self.client,self.package)
    def test_tampered_package(self):
        (self.package/PATCH/self.asset).write_bytes(b'tampered')
        with self.assertRaises(ValueError):validate(self.package)
    def test_matching_hash_cannot_hide_invalid_gpu_format(self):
        path=self.package/PATCH/self.asset;data=bytearray(path.read_bytes());data[10]=0;path.write_bytes(data)
        manifest=json.loads((self.package/'manifest.json').read_text());manifest['files'][self.asset]=sha(data)
        (self.package/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'preferredFormat'):validate(self.package)
