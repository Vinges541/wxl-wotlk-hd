import struct
import unittest
import numpy as np
from PIL import Image
from wxl_equipment.assets import encode_blp, decode_blp
from wxl_equipment.client_blp import assemble, to_runtime, validate
from wxl_equipment.quality_pilot import direct_rgba
from wxl_equipment.smooth_alpha import resample_alpha


class SmoothAlphaTests(unittest.TestCase):
    def test_runtime_mips_against_separate_decoders(self):
        pixels = np.zeros((4, 8, 4), dtype=np.uint8)
        pixels[:, :, :3] = (220, 170, 30)
        pixels[:, :, 3] = np.array([[0, 0, 0, 90, 255, 255, 255, 255],
                                    [0, 0, 90, 255, 255, 255, 255, 255],
                                    [0, 90, 255, 255, 255, 255, 255, 255],
                                    [90, 255, 255, 255, 255, 255, 255, 255]], dtype=np.uint8)
        source = Image.fromarray(pixels)
        for component in (False, True):
            before, _ = to_runtime(encode_blp(direct_rgba(source, source.convert('RGB').resize((32, 16)), 2)), component)
            after = resample_alpha(before, source)
            self.assertNotEqual(before, after)
            self.assertEqual(before[:1172], after[:1172])
            alpha = source.getchannel('A').resize((16, 8), Image.Resampling.BILINEAR)
            offsets = struct.unpack_from('<16I', before, 20)
            sizes = struct.unpack_from('<16I', before, 84)
            for offset, length in zip(offsets, sizes):
                if not offset:
                    continue
                decoded = []
                for data in (before, after):
                    if data[8] == 3:
                        decoded.append(Image.frombytes('RGBA', alpha.size, data[offset:offset + length], 'raw', 'BGRA'))
                    else:
                        single = assemble(alpha.size, data[8], data[9], data[10], [data[offset:offset + length]], data[148:1172])
                        decoded.append(decode_blp(single))
                self.assertEqual(decoded[0].convert('RGB').tobytes(), decoded[1].convert('RGB').tobytes())
                self.assertEqual(decoded[1].getchannel('A').tobytes(), alpha.tobytes())
                if alpha.size != (1, 1):
                    alpha = alpha.resize((max(1, alpha.width // 2), max(1, alpha.height // 2)), Image.Resampling.BOX)
            validate(after, component)

    def test_opaque_components_are_identical_and_wrong_scale_is_rejected(self):
        source = Image.new('RGBA', (4, 4), (20, 40, 60, 255))
        data, _ = to_runtime(encode_blp(source.resize((8, 8))), True)
        self.assertEqual(resample_alpha(data, source), data)
        with self.assertRaisesRegex(ValueError, '2x dimensions'):
            resample_alpha(data, source.resize((8, 8)))
        with self.assertRaisesRegex(ValueError, 'nonopaque'):
            resample_alpha(data, Image.new('RGBA', (4, 4), (20, 40, 60, 0)))
