import argparse
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from wxl_equipment import batch, npc
from wxl_equipment.assets import decode_blp, encode_blp, sha
from wxl_equipment.client_blp import to_runtime, validate
from wxl_equipment.recipes import deployment, direct_rgba, restore
from wxl_equipment.smooth_alpha import resample_alpha


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.source = Image.new('RGBA', (8, 4), (45, 60, 90, 0))
        self.source.paste((150, 100, 40, 255), (2, 0, 6, 4))
        self.raw = Image.new('RGB', (32, 16), (200, 140, 80))

    def test_deployment_matches_approved_order_for_both_runtime_formats(self):
        cache = encode_blp(direct_rgba(self.source, self.raw, 2))
        for component in (False, True):
            nearest, _ = to_runtime(cache, component)
            expected = resample_alpha(nearest, self.source)
            actual, _ = deployment(cache, encode_blp(self.source), component, 'direct-smooth')
            self.assertEqual(actual, expected)
            info = validate(actual, component)
            alpha = self.source.getchannel('A').resize((16, 8), Image.Resampling.BILINEAR)
            for offset, size in zip(struct.unpack_from('<16I', actual, 20), struct.unpack_from('<16I', actual, 84)):
                if not offset:
                    break
                plane = actual[offset + alpha.width * alpha.height:offset + size] if component else actual[offset + 3:offset + size:4]
                self.assertEqual(plane, alpha.tobytes())
                alpha = alpha.resize((max(1, alpha.width // 2), max(1, alpha.height // 2)), Image.Resampling.BOX)
            self.assertEqual(info['width'], 16)

    def test_direct_restore_uses_raw_neural_result(self):
        model = Mock(raw=self.raw)
        model.run.return_value = (Image.new('RGBA', (16, 8)), {'strength': .35, 'maxRgbCorrection': 8})
        image, report = restore(model, self.source, 2, .35, 'direct-smooth')
        self.assertEqual(image.tobytes(), direct_rgba(self.source, self.raw, 2).tobytes())
        self.assertIsNone(report['strength'])
        self.assertNotIn('maxRgbCorrection', report)
        with self.assertRaises(ValueError):
            restore(model, self.source, 1, .35, 'direct-smooth')

    def test_bulk_direct_components_scale_resume_and_runtime_mask(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); data = encode_blp(self.source); digest = sha(data)
            source = root / 'original' / digest[:2] / (digest + '.blp')
            source.parent.mkdir(parents=True); source.write_bytes(data)
            row = {'path': 'Item/TextureComponents/Test/A.blp', 'sha256': digest,
                   'width': 8, 'height': 4, 'scale': 1, 'outputBytes': batch.mip_bytes(8, 4)}
            (root / 'inventory.json').write_text(json.dumps({'state': 'complete', 'textures': [row]}))
            args = argparse.Namespace(workspace=root, output=root/'package', weights=root/'weights', strength=.35)
            config = {'model': 'RealESRNet_x4plus', 'weightsSha256': 'synthetic', 'recipe': 'direct-smooth', 'strength': None}
            with patch.object(batch, 'profile', return_value=config), patch('wxl_equipment.mlx_inference.MLXUpscaler') as factory:
                factory.return_value.raw = self.raw
                factory.return_value.run.return_value = (Image.new('RGBA', (16, 8)), {})
                batch.process(args); batch.process(args)
                self.assertEqual(factory.return_value.run.call_count, 1)
            batch.pack(args)
            packed = (args.output/'Patch-WXL-Equipment.MPQ'/row['path'].lower()).read_bytes()
            image = decode_blp(packed)
            self.assertEqual(image.size, (16, 8))
            self.assertEqual(image.getchannel('A').tobytes(), self.source.getchannel('A').resize((16, 8), Image.Resampling.BILINEAR).tobytes())

    def test_npc_direct_cache_and_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); data = encode_blp(self.source); digest = sha(data)
            original = root/'original'/digest[:2]/(digest+'.blp')
            original.parent.mkdir(parents=True); original.write_bytes(data)
            row = {'path': 'Textures/BakedNpcTextures/test.blp',
                   'target': 'Data/Patch-ModernRaces-HD.MPQ/Textures/BakedNpcTextures/test.blp',
                   'sha256': digest, 'beforeTargetSha256': None, 'width': 8, 'height': 4,
                   'scale': 2, 'outputBytes': batch.mip_bytes(16, 8)}
            (root/'inventory.json').write_text(json.dumps({'state': 'complete', 'textures': [row], 'locale': 'enUS', 'tables': {}}))
            args = argparse.Namespace(workspace=root, output=root/'package', weights=root/'weights')
            config = {'model': 'RealESRNet_x4plus', 'weightsSha256': 'synthetic', 'recipe': 'direct-smooth', 'protectFace': False}
            with patch.object(npc, 'profile', return_value=config), patch('wxl_equipment.mlx_inference.MLXUpscaler') as factory:
                factory.return_value.raw = self.raw
                factory.return_value.run.return_value = (Image.new('RGBA', (16, 8)), {})
                npc.process(args); npc.process(args)
                self.assertEqual(factory.return_value.run.call_count, 1)
            npc.pack(args)
            output = (args.output/row['target']).read_bytes()
            expected, _ = deployment(encode_blp(direct_rgba(self.source, self.raw, 2)), data, False, 'direct-smooth')
            self.assertEqual(output, expected)
