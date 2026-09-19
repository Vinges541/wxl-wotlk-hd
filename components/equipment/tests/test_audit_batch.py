import importlib.util
from pathlib import Path
import struct
import unittest
from PIL import Image
from wxl_equipment.assets import encode_blp

spec=importlib.util.spec_from_file_location('audit_batch',Path(__file__).resolve().parents[1]/'tools'/'audit_batch.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class MipAuditTests(unittest.TestCase):
    def test_pixels_and_rectangular_chains(self):
        for size in [(1,1),(1,32),(32,1),(16,32)]:
            image=Image.new('RGBA',size)
            image.putdata([(i%256,(i*3)%256,(i*7)%256,(i*11)%256) for i in range(size[0]*size[1])])
            data=encode_blp(image);audit.verify_mips(data,*size)
            if max(size)>1:
                altered=bytearray(data);offset=struct.unpack_from('<I',data,24)[0];altered[offset+3]^=128
                with self.assertRaises(ValueError):audit.verify_mips(altered,*size)
            with self.assertRaises(ValueError):audit.verify_mips(data+b'extra',*size)
