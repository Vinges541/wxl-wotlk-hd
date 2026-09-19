import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_npc import validate_record
from wxl_equipment.assets import encode_blp,sha
from wxl_equipment.batch import cache_key,mip_bytes


class NpcAuditTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()
        self.profile={'strength':.35,'protectFace':False,'weightsSha256':'synthetic'}
        source=encode_blp(Image.new('RGBA',(16,16),(80,100,120,128)));digest=sha(source)
        self.row={'sha256':digest,'width':16,'height':16,'scale':2,'outputBytes':mip_bytes(32,32)}
        original=self.root/'original'/digest[:2]/(digest+'.blp');original.parent.mkdir(parents=True);original.write_bytes(source)
        key=cache_key(self.row,self.profile);self.row['cacheKey']=key;self.folder=self.root/'cache'/key[:2]/key;self.folder.mkdir(parents=True)
        self.meta={'inputSha256':digest,'device':'mlx-gpu','precision':'fp32','tile':0,'scale':2,'strength':.35,'protectFace':False,'weightsSha256':'synthetic'}
        self.output=encode_blp(Image.new('RGBA',(32,32),(84,104,124,128)));self.save()

    def save(self):
        self.row['outputSha256']=sha(self.output);self.meta['outputSha256']=sha(self.output)
        (self.folder/'result.blp').write_bytes(self.output);(self.folder/'report.json').write_text(json.dumps(self.meta))

    def test_accepts_bounded_detail_and_full_mips(self):
        self.assertEqual(validate_record(self.root,self.row,self.profile)[3],4)

    def test_rejects_valid_hash_with_wrong_mip_pixels(self):
        payload=bytearray(self.output);payload[148+32*32*4]+=1;self.output=bytes(payload);self.save()
        with self.assertRaisesRegex(ValueError,'Mip pixels'):validate_record(self.root,self.row,self.profile)

    def test_rejects_alpha_and_rgb_changes(self):
        self.output=encode_blp(Image.new('RGBA',(32,32),(84,104,124,127)));self.save()
        with self.assertRaisesRegex(ValueError,'alpha'):validate_record(self.root,self.row,self.profile)
        self.output=encode_blp(Image.new('RGBA',(32,32),(120,100,120,128)));self.save()
        with self.assertRaisesRegex(ValueError,'RGB correction'):validate_record(self.root,self.row,self.profile)

    def test_rejects_precision_metadata_change(self):
        self.meta['precision']='fp16';self.save()
        with self.assertRaisesRegex(ValueError,'profile'):validate_record(self.root,self.row,self.profile)

    def test_direct_recipe_has_no_conservative_rgb_bound(self):
        self.profile.update(recipe='direct-smooth',strength=None)
        key=cache_key(self.row,self.profile);self.row['cacheKey']=key
        self.folder=self.root/'cache'/key[:2]/key;self.folder.mkdir(parents=True)
        self.meta.update(recipe='direct-smooth',outputMode='direct-neural-rgb',strength=None)
        self.output=encode_blp(Image.new('RGBA',(32,32),(180,100,120,128)));self.save()
        self.assertEqual(validate_record(self.root,self.row,self.profile)[3],100)
        self.meta['outputMode']='bounded';self.save()
        with self.assertRaisesRegex(ValueError,'Direct recipe'):validate_record(self.root,self.row,self.profile)
