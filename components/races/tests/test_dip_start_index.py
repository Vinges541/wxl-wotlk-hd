import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_runtime
import patch_dip_start_index as dip
from patch_wow import Pe32, PatchError


def synthetic_pe():
    data = bytearray(0x10000)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', data, 0x84, 0x14c, 1)
    struct.pack_into('<H', data, 0x94, 224)
    struct.pack_into('<H', data, 0x98, 0x10b)
    struct.pack_into('<I', data, 0x98+28, 0x10000000)
    struct.pack_into('<I', data, 0x98+60, 0x400)
    data[0x178:0x1a0] = struct.pack('<8sIIIIIIHHI', b'.text', len(data)-0x400,
                                  0x1000, len(data)-0x400, 0x400, 0, 0, 0, 0, 0x60000020)
    pe = Pe32(data)
    pe.write_va(pe.image_base + dip.RVA - len(dip.BEFORE), dip.BEFORE + dip.CALL + dip.AFTER)
    return bytes(data)


class DipStructureTests(unittest.TestCase):
    def test_only_call_changes(self):
        source = synthetic_pe()
        result = dip._patch_verified_image(source)
        expected = bytearray(source)
        pe = Pe32(expected)
        pe.write_va(pe.image_base + dip.RVA, dip.REPLACEMENT)
        self.assertEqual(result, expected)
        self.assertEqual(len(result), len(source))

    def test_signature_and_stack_context_required(self):
        source = synthetic_pe()
        pe = Pe32(bytearray(source))
        site = pe.va_to_offset(pe.image_base + dip.RVA)
        for offset in range(site-len(dip.BEFORE), site+len(dip.CALL)+len(dip.AFTER)):
            damaged = bytearray(source)
            damaged[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(PatchError):
                dip._patch_verified_image(damaged)

    def test_wrong_image_base_and_repeat_refused(self):
        source = bytearray(synthetic_pe())
        struct.pack_into('<I', source, 0x98+28, 0x400000)
        with self.assertRaises(PatchError):
            dip._patch_verified_image(source)
        with self.assertRaises(PatchError):
            dip._patch_verified_image(dip._patch_verified_image(synthetic_pe()))

    def test_full_input_and_output_hash_guards(self):
        source = synthetic_pe()
        for unknown in (b'', b'MZ', source):
            with self.assertRaises(PatchError):
                dip.patch(unknown)
        with patch.object(dip, 'EXPECTED', hashlib.sha256(source).hexdigest()):
            with self.assertRaises(PatchError):
                dip.patch(source)
            expected = dip._patch_verified_image(source)
            with patch.object(dip, 'RESULT', hashlib.sha256(expected).hexdigest()):
                self.assertEqual(dip.patch(source), expected)

    def test_candidate_does_not_promote_default_runtime(self):
        name = 'Extensions/wxl-modern-m2/wxl-modern-m2.dll'
        self.assertEqual(build_runtime.OUTPUT_HASHES[name], dip.EXPECTED)
        self.assertEqual(build_runtime.CANDIDATE_OUTPUT_HASHES[name], dip.RESULT)
        self.assertEqual({k: v for k, v in build_runtime.OUTPUT_HASHES.items() if k != name},
                         {k: v for k, v in build_runtime.CANDIDATE_OUTPUT_HASHES.items() if k != name})

    @unittest.skipUnless(os.environ.get('WXL_MODERN_M2_INPUT'), 'explicit original modern-M2 fixture required')
    def test_pinned_private_binary(self):
        from patch_shadow_bone_budget import patch as bone_budget
        source = bone_budget(Path(os.environ['WXL_MODERN_M2_INPUT']).read_bytes())
        result = dip.patch(source)
        self.assertEqual(hashlib.sha256(result).hexdigest(), dip.RESULT)
        pe = Pe32(bytearray(source))
        site = pe.va_to_offset(pe.image_base + dip.RVA)
        self.assertEqual(source[:site], result[:site])
        self.assertEqual(source[site+5:], result[site+5:])


@unittest.skipUnless(importlib.util.find_spec('unicorn'), 'optional Unicorn x86 emulation')
class DipEmulationTests(unittest.TestCase):
    def test_incoming_index_and_calling_frame_preserved(self):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX,
            UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP)
        # Exact caller context around the replacement, using a synthetic stack.
        code = dip.BEFORE + dip.REPLACEMENT + dip.AFTER
        for start in (0, 65535, 65536, 79635, 145171, 210707, 0xffffffff):
            with self.subTest(start=start):
                u = Uc(UC_ARCH_X86, UC_MODE_32)
                u.mem_map(0x100000, 0x1000)
                u.mem_map(0x200000, 0x1000)
                u.mem_write(0x100000, code)
                sp, bp = 0x200800, 0x200900
                u.mem_write(bp+0x1c, struct.pack('<II', start, 137))
                regs = {UC_X86_REG_ECX: 0x123, UC_X86_REG_EDX: 0x234, UC_X86_REG_ESI: 0x345,
                        UC_X86_REG_EDI: 0x456, UC_X86_REG_EBP: bp, UC_X86_REG_ESP: sp}
                for reg, value in regs.items():
                    u.reg_write(reg, value)
                before = bytes(u.mem_read(sp, 0x800))
                u.emu_start(0x100000, 0x100000+len(code), count=10)
                self.assertEqual(u.reg_read(UC_X86_REG_EAX), start)
                self.assertEqual(u.reg_read(UC_X86_REG_EBX), 137)
                for reg, value in regs.items():
                    self.assertEqual(u.reg_read(reg), value)
                self.assertEqual(bytes(u.mem_read(sp, 0x800)), before)


if __name__ == '__main__':
    unittest.main()
