import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from wxl_equipment import batch
from wxl_equipment.assets import EmptyAsset, encode_blp, sha
from wxl_equipment.package import validate


class BatchTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        self.image=Image.new('RGBA',(4,4),(20,40,60,128))
        self.data=encode_blp(self.image);self.digest=sha(self.data)
        self.args=argparse.Namespace(workspace=self.root,weights=self.root/'weights',lock=self.root/'lock',strength=.35,output=self.root/'package')

    def fixture(self):
        rows=[]
        for name,scale in [('Item/TextureComponents/Test/A.blp',1),('ITEM/TEXTURECOMPONENTS/Test/B.blp',1),('item/ObjectComponents/Weapon/C.blp',2)]:
            rows.append({'path':name,'sha256':self.digest,'scale':scale,'outputBytes':batch.mip_bytes(4*scale,4*scale)})
        (self.root/'inventory.json').write_text(json.dumps({'state':'complete','textures':rows}))
        original=self.root/'original'/self.digest[:2]/(self.digest+'.blp');original.parent.mkdir(parents=True);original.write_bytes(self.data)
        return rows

    def test_resume_deduplication_pack_and_tamper(self):
        self.fixture()
        configuration={'model':'RealESRNet_x4plus','weightsSha256':'synthetic','strength':.35}
        with patch('wxl_equipment.batch.profile',return_value=configuration),patch('wxl_equipment.mlx_inference.MLXUpscaler') as factory:
            factory.return_value.run.side_effect=lambda image,scale,strength:(image.resize((image.width*scale,image.height*scale),resample=0),{})
            batch.process(self.args)
            self.assertEqual(factory.return_value.run.call_count,2)
            factory.return_value.run.reset_mock()
            batch.process(self.args)
            factory.return_value.run.assert_not_called()
            progress=json.loads((self.root/'progress.json').read_text())
            self.assertEqual(progress['reused'],3)
            batch.pack(self.args)
            files=validate(self.args.output)['files']
            self.assertEqual(len(files),3)
            self.assertTrue(all(name==name.casefold() for name in files))
            next((self.root/'cache').rglob('result.blp')).write_bytes(b'changed')
            with self.assertRaises(ValueError):batch.process(self.args)

    def test_empty_higher_priority_asset_is_explicitly_preserved(self):
        archive=self.root/'patch.MPQ';archive.write_bytes(b'synthetic archive')
        self.args.archive=[archive];self.args.stormlib=self.root/'library'
        good='Item/ObjectComponents/Weapon/A.blp';empty='Item/TextureComponents/TorsoLowerTexture/Deleted.blp'
        def read(name):
            if name=='(listfile)':return (good+'\n'+empty+'\n').encode(),archive.name
            if name==empty:raise EmptyAsset(name,archive.name)
            return self.data,archive.name
        with patch('wxl_equipment.batch.MPQ') as factory:
            factory.return_value.read.side_effect=read
            batch.inventory(self.args)
        result=json.loads((self.root/'inventory.json').read_text())
        self.assertEqual(result['state'],'complete')
        self.assertEqual(len(result['textures']),1)
        self.assertEqual(result['emptyEntries'][0]['path'],empty)
        self.assertEqual(result['emptyEntries'][0]['archive'],'patch.MPQ')

    def test_incomplete_processing_cannot_be_packaged(self):
        self.fixture()
        (self.root/'progress.json').write_text('{"state":"running"}')
        with self.assertRaises(ValueError):batch.pack(self.args)
        self.assertFalse(self.args.output.exists())

    def test_scope_rejects_other_assets(self):
        for name in ['Character/Human/Test.blp','Item/Test.m2','Item/../Test.blp']:
            with self.assertRaises(ValueError):batch.scope(name)
