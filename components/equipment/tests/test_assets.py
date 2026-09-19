import struct
import unittest
import random
from PIL import Image
from wxl_equipment.assets import encode_blp, decode_blp, inspect_blp, safe_path, DBC

class TextureTests(unittest.TestCase):
    def test_bgra_roundtrip_all_alpha_and_mips(self):
        image=Image.new('RGBA',(16,16));image.putdata([(i,255-i,i//2,i) for i in range(256)])
        data=encode_blp(image)
        self.assertEqual(decode_blp(data).tobytes(),image.tobytes())
        self.assertEqual(inspect_blp(data)['mips'],5)
        for level in range(5):
            offset=struct.unpack_from('<I',data,20+4*level)[0];size=struct.unpack_from('<I',data,84+4*level)[0]
            self.assertEqual(size,max(1,16>>level)**2*4)
            self.assertLessEqual(offset+size,len(data))
    def test_palette_separate_alpha(self):
        for depth,packed,expected in [(0,b'',[255]*4),(1,b'\x05',[255,0,255,0]),(4,b'\xf0\x87',[0,255,119,136]),(8,bytes([0,70,160,255]),[0,70,160,255])]:
            palette=bytes([30,20,10,0])*256;payload=bytes(4)+packed
            data=struct.pack('<4sI4B2I16I16I',b'BLP2',1,1,depth,8,0,2,2,1172,*([0]*15),len(payload),*([0]*15))+palette+payload
            image=decode_blp(data)
            self.assertEqual(list(image.getchannel('A').get_flattened_data()),expected)
            self.assertEqual(image.getpixel((0,0))[:3],(10,20,30))
    def test_bad_inputs(self):
        for name in ['../x','/x','C:/x','a//b','a/./b','a/../b']:
            with self.assertRaises(ValueError):safe_path(name)
        with self.assertRaises(ValueError):encode_blp(Image.new('RGB',(7,8)))
        with self.assertRaises(ValueError):DBC(struct.pack('<4s4I',b'WDBC',2,8,32,1),8)
        data=bytearray(encode_blp(Image.new('RGBA',(4,4))));struct.pack_into('<I',data,20,999999)
        with self.assertRaises(ValueError):inspect_blp(data)

    def test_palette_expansion_matches_scalar_for_all_alpha_depths(self):
        rng=random.Random(17)
        for width,height in [(1,1),(3,3),(32,16)]:
            count=width*height
            palette=bytes(rng.randrange(256) for _ in range(1024))
            indices=bytes(rng.randrange(256) for _ in range(count))
            for depth in (0,1,4,8):
                masks=bytes(rng.randrange(256) for _ in range((count*depth+7)//8))
                payload=indices+masks
                header=struct.pack('<4sI4B2I16I16I',b'BLP2',1,1,depth,8,0,width,height,1172,*([0]*15),len(payload),*([0]*15))
                expected=bytearray()
                for i,index in enumerate(indices):
                    b,g,r,_=palette[index*4:index*4+4]
                    a=255 if not depth else ((masks[i*depth//8]>>((i*depth)%8))&((1<<depth)-1))*255//((1<<depth)-1)
                    expected.extend((r,g,b,a))
                self.assertEqual(decode_blp(header+palette+payload).tobytes(),bytes(expected))
