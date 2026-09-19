import argparse
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from wxl_equipment import npc
from wxl_equipment.assets import encode_blp,sha,decode_blp


def table(names):
    strings=bytearray(b'\0');rows=[]
    for i,name in enumerate(names):
        row=[0]*21;row[0]=i+1;row[1]=1;row[20]=len(strings);strings.extend(name.encode()+b'\0');rows.append(struct.pack('<21I',*row))
    return struct.pack('<4s4I',b'WDBC',len(rows),21,84,len(strings))+b''.join(rows)+strings


class NpcTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve();self.client=self.root/'client';self.workspace=self.root/'work'
        self.args=argparse.Namespace(workspace=self.workspace,client=self.client,locale='ruRU',stormlib=self.root/'lib',archive=[self.root/'patch.MPQ'],protect_face=False,weights=self.root/'weights',lock=self.root/'lock',output=self.root/'package')
        self.args.archive[0].write_bytes(b'synthetic archive')
        self.data=encode_blp(Image.new('RGBA',(16,16),(20,40,60,128)))
        folder=self.client/npc.TARGET/npc.VIRTUAL;folder.mkdir(parents=True);(folder/'Modern.blp').write_bytes(self.data)
        self.tables=[self.client/npc.TARGET/npc.TABLE,self.client/'Data/ruRU/patch-ruRU-ModernRaces.MPQ'/npc.TABLE]
        for p in self.tables:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(table(['Modern.blp','Legacy.blp']))

    def inventory(self):
        with patch('wxl_equipment.npc.MPQ') as reader:
            reader.return_value.read.return_value=(self.data,'common.MPQ')
            npc.inventory(self.args)

    def test_active_bakes_resume_and_package_guards(self):
        self.inventory();inv=json.loads((self.workspace/'inventory.json').read_text())
        self.assertEqual(len(inv['textures']),2)
        self.assertEqual(sum(r['beforeTargetSha256'] is not None for r in inv['textures']),1)
        config={'model':'RealESRNet_x4plus','weightsSha256':'synthetic','protectFace':False}
        with patch('wxl_equipment.npc.profile',return_value=config),patch('wxl_equipment.mlx_inference.MLXUpscaler') as model:
            model.return_value.run.side_effect=lambda before,*_:(before.resize((32,32),Image.Resampling.NEAREST),{})
            npc.process(self.args);self.assertEqual(model.return_value.run.call_count,1)
            model.return_value.run.reset_mock();npc.process(self.args);model.return_value.run.assert_not_called()
        npc.pack(self.args)
        manifest=json.loads((self.args.output/'release-manifest.json').read_text());guards=json.loads((self.args.output/'source-guards.json').read_text())
        self.assertEqual(len(manifest['files']),2)
        self.assertEqual(guards['targets'][npc.TARGET+'/'+npc.VIRTUAL+'/Modern.blp'],sha(self.data))
        self.assertIsNone(guards['targets'][npc.TARGET+'/'+npc.VIRTUAL+'/legacy.blp'])
        self.assertTrue(all(f['path'].endswith('.blp') for f in manifest['files']))
        self.assertEqual(len(guards['tables']),2)
        self.args.package=self.args.output;npc.check_guards(self.args)
        (self.client/npc.TARGET/npc.VIRTUAL/'Modern.blp').write_bytes(b'changed')
        with self.assertRaises(ValueError):npc.check_guards(self.args)
        for f in manifest['files']:
            payload=(self.args.output/f['path']).read_bytes();self.assertEqual(sha(payload),f['sha256']);self.assertEqual(decode_blp(payload).size,(32,32))

    def test_table_mismatch_and_unsafe_names_rejected(self):
        self.tables[1].write_bytes(table(['Different.blp']))
        with self.assertRaises(ValueError):self.inventory()
        for p in self.tables:p.write_bytes(table(['../escape.blp']))
        with self.assertRaises(ValueError):self.inventory()

    def test_face_protection_preserves_only_documented_rectangle(self):
        before=Image.new('RGBA',(256,256),(25,50,75,128));after=Image.new('RGBA',(512,512),(200,190,180,128))
        npc.protect_face(before,after)
        self.assertEqual(after.getpixel((0,320)),(25,50,75,128));self.assertEqual(after.getpixel((255,511)),(25,50,75,128))
        self.assertEqual(after.getpixel((256,400)),(200,190,180,128));self.assertEqual(after.getpixel((0,319)),(200,190,180,128))
        with self.assertRaises(ValueError):npc.protect_face(Image.new('RGBA',(16,16)),after)

    def test_missing_exception_requires_absent_source_and_exact_names(self):
        self.inventory();path=self.workspace/'inventory.json';inv=json.loads(path.read_text());name=npc.VIRTUAL+'/Absent.blp';inv['state']='failed';inv['failed']=[{'path':name,'error':'missing','references':[]}];path.write_text(json.dumps(inv));self.args.name=[name]
        with patch('wxl_equipment.npc.MPQ') as reader:
            reader.return_value.read.return_value=(self.data,'common.MPQ')
            with self.assertRaises(ValueError):npc.accept_missing(self.args)
            reader.return_value.read.side_effect=FileNotFoundError(name)
            npc.accept_missing(self.args)
        final=json.loads(path.read_text());self.assertEqual(final['state'],'complete');self.assertEqual(final['missingSources'][0]['path'],name)
