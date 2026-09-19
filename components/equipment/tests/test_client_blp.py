import struct
import unittest
import numpy as np
from PIL import Image
from wxl_equipment.assets import encode_blp,decode_blp
from wxl_equipment.client_blp import to_runtime,validate,raw_levels


class ClientBlpTests(unittest.TestCase):
    def image(self):
        image=Image.new('RGBA',(16,16));image.putdata([(i,255-i,i//2,i) for i in range(256)]);return image

    def test_raw_gpu_format_and_every_mip_pixel(self):
        source=bytearray(encode_blp(self.image()));source[10]=0
        output,report=to_runtime(bytes(source))
        self.assertEqual(output[8:12],bytes([3,8,2,1]));self.assertEqual(struct.unpack_from('<I',output,20)[0],1172)
        for before,after in zip(raw_levels(source),raw_levels(output)):self.assertEqual(before.tobytes(),after.tobytes())
        self.assertTrue(report['allMipRgbaExact'])
        damaged=bytearray(output);damaged[10]=0
        with self.assertRaisesRegex(ValueError,'preferredFormat'):validate(damaged)

    def test_component_palette_and_separate_alpha_all_levels(self):
        source=encode_blp(self.image());output,report=to_runtime(source,True)
        self.assertEqual(output[8:12],bytes([1,8,8,1]));validate(output,True)
        for level,before in enumerate(raw_levels(source)):
            count=before.width*before.height;offset=struct.unpack_from('<I',output,20+level*4)[0]
            self.assertEqual(output[offset+count:offset+2*count],before.getchannel('A').tobytes())
        self.assertTrue(report['allMipAlphaExact']);self.assertFalse(report['allMipRgbaExact'])

    def test_dither_preserves_every_alpha_mip_and_raw_object_bytes(self):
        source=encode_blp(self.image())
        output,report=to_runtime(source,True,palette_mode='median-dither')
        validate(output,True)
        for level,before in enumerate(raw_levels(source)):
            count=before.width*before.height;offset=struct.unpack_from('<I',output,20+level*4)[0]
            self.assertEqual(output[offset+count:offset+2*count],before.getchannel('A').tobytes())
        self.assertEqual(report['paletteMode'],'median-dither')
        self.assertEqual(to_runtime(source,False)[0],to_runtime(source,False,palette_mode='median-dither')[0])
        with self.assertRaisesRegex(ValueError,'palette mode'):
            to_runtime(source,True,palette_mode='unknown')

    def test_dither_uses_spatial_mips_without_cross_level_error(self):
        y,x=np.mgrid[:32,:128]
        pixels=np.stack((x+60,y*3+20,(x+y)//2+30,np.full_like(x,255)),axis=-1).astype('uint8')
        source=encode_blp(Image.fromarray(pixels));levels=raw_levels(source)
        output,_=to_runtime(source,True,palette_mode='median-dither')
        palette=Image.new('P',(1,1));palette.putpalette([v for i in range(256) for v in output[148+i*4:151+i*4][::-1]])
        differing=False
        for level,before in enumerate(levels):
            offset=struct.unpack_from('<I',output,20+level*4)[0]
            actual=output[offset:offset+before.width*before.height]
            expected=before.convert('RGB').quantize(palette=palette,dither=Image.Dither.FLOYDSTEINBERG).tobytes()
            self.assertEqual(actual,expected)
            undithered=before.convert('RGB').quantize(palette=palette,dither=Image.Dither.NONE).tobytes()
            differing|=actual!=undithered
        self.assertTrue(differing)

    def test_component_rejects_raw_and_opaque_palette_has_no_alpha_plane(self):
        output,_=to_runtime(encode_blp(self.image()))
        with self.assertRaisesRegex(ValueError,'palettized'):validate(output,True)
        original=Image.new('RGBA',(8,8),(20,40,60,255));output,_=to_runtime(encode_blp(original),True)
        self.assertEqual(output[9],0);self.assertEqual(decode_blp(output).tobytes(),original.tobytes())

    def test_rejects_truncated_and_mis_sized_payloads(self):
        output,_=to_runtime(encode_blp(self.image()))
        with self.assertRaises(ValueError):validate(output[:-1])
        broken=bytearray(output);struct.pack_into('<I',broken,84,8)
        with self.assertRaises(ValueError):validate(broken)

    def test_component_preserves_rare_contrasting_painted_accents(self):
        pixels=np.full((64,128,4),255,dtype=np.uint8)
        pixels[:,:,:3]=np.random.default_rng(7).integers(40,120,size=(64,128,3),dtype=np.uint8)
        pixels[0,0,:3]=(255,255,255);pixels[0,1,:3]=(255,0,255)
        output,report=to_runtime(encode_blp(Image.fromarray(pixels)),True)
        restored=np.asarray(decode_blp(output))
        np.testing.assert_array_equal(restored[0,:2],pixels[0,:2])
        self.assertLessEqual(report['visibleRgbQuantizationMax'],24)
