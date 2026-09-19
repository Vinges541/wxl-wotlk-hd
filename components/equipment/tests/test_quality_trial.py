import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from wxl_equipment.assets import encode_blp,sha
from wxl_equipment.client_blp import to_runtime
from wxl_equipment.quality_pilot import direct_rgba
from wxl_equipment.trial import install,rollback
from wxl_equipment.package import PATCH


class QualityTrialTests(unittest.TestCase):
    def test_direct_output_is_unbounded_and_alpha_is_independent(self):
        source=Image.new('RGBA',(4,4),(10,20,30,50));raw=Image.new('RGB',(16,16),(100,150,200))
        result=direct_rgba(source,raw,2)
        self.assertEqual(result.size,(8,8));self.assertEqual(result.getpixel((0,0)),(100,150,200,50))
        with self.assertRaises(ValueError):direct_rgba(source,Image.new('RGB',(4,4)),2)

    def fixture(self,root):
        root=root.resolve()
        client=root/'client';package=root/'package';name='item/texturecomponents/torsouppertexture/test.blp'
        target=client/'Data'/PATCH/name;target.parent.mkdir(parents=True);(client/'Wow.exe').write_bytes(b'synthetic')
        before,_=to_runtime(encode_blp(Image.new('RGBA',(4,4),(10,20,30,80))),True)
        after,_=to_runtime(encode_blp(Image.new('RGBA',(8,8),(100,150,200,80))),True)
        target.write_bytes(before);source=package/PATCH/name;source.parent.mkdir(parents=True);source.write_bytes(after)
        manifest={'schema':1,'kind':'wxl-equipment-trial','patch':PATCH,'files':[{'path':name,'beforeSha256':sha(before),'sha256':sha(after),'bytes':len(after)}]}
        (package/'trial-manifest.json').write_text(json.dumps(manifest))
        return client,package,target,before,after

    def test_trial_backup_apply_and_guarded_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            client,package,target,before,after=self.fixture(Path(temp))
            self.assertEqual(install(client,package)['state'],'preview');self.assertEqual(target.read_bytes(),before)
            with patch('wxl_equipment.trial.stopped'):
                result=install(client,package,True);checkpoint=Path(result['checkpoint']);self.assertEqual(target.read_bytes(),after)
                self.assertEqual(rollback(client,checkpoint)['state'],'rollback-preview')
                target.write_bytes(b'new user edit')
                with self.assertRaisesRegex(ValueError,'Later client edit'):rollback(client,checkpoint,True)
                target.write_bytes(after);rollback(client,checkpoint,True);self.assertEqual(target.read_bytes(),before)

    def test_running_and_changed_client_are_refused_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            client,package,target,before,after=self.fixture(Path(temp))
            with patch('wxl_equipment.trial.stopped',side_effect=RuntimeError('running')):
                with self.assertRaises(RuntimeError):install(client,package,True)
            self.assertEqual(target.read_bytes(),before)
            target.write_bytes(after)
            with self.assertRaisesRegex(ValueError,'Client changed'):install(client,package)
