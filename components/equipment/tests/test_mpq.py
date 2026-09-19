import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from wxl_equipment import mpq
from wxl_equipment.mpq_format import CRYPT, LegacyMPQ, hash_name, MASK


def encrypt(data, key):
    seed = 0xeeeeeeee
    words = []
    for (value,) in struct.iter_unpack('<I', data):
        seed = (seed + CRYPT[0x400 + (key & 255)]) & MASK
        words.append(value ^ ((key + seed) & MASK))
        key = (((~key << 21) + 0x11111111) | (key >> 11)) & MASK
        seed = (value + seed + (seed << 5) + 3) & MASK
    return struct.pack('<' + 'I' * len(words), *words)


def fixture(path, payload, mask=2, version=0, table_offset=None):
    name = 'Item/Test.blp'
    chunks = []
    offsets = [4 * ((len(payload) + 4095)//4096 + 1)]
    for start in range(0, len(payload), 4096):
        raw = payload[start:start+4096]
        compressed = bytes([mask]) + zlib.compress(raw)
        chunk = compressed if len(compressed) < len(raw) else raw
        chunks.append(chunk); offsets.append(offsets[-1] + len(chunk))
    body = struct.pack('<' + 'I' * len(offsets), *offsets) + b''.join(chunks)
    hashes = [struct.pack('<4I', MASK, MASK, MASK, MASK)] * 4
    hashes[hash_name(name, 0) & 3] = struct.pack('<IIHHI', hash_name(name, 1), hash_name(name, 2), 0, 0, 0)
    header_size = 44 if version == 1 else 32
    hp = table_offset or header_size + len(body); bp = hp + 64
    header = struct.pack('<4sIIHHIIII', b'MPQ\x1a', header_size, bp + 16, version, 3, hp, bp, 4, 1)
    if version == 1: header += bytes(12)
    block = struct.pack('<4I', header_size, len(body), len(payload), 0x80000200)
    with path.open('wb') as stream:
        stream.write(header + body); stream.seek(hp)
        stream.write(encrypt(b''.join(hashes), hash_name('(hash table)', 3)))
        stream.write(encrypt(block, hash_name('(block table)', 3)))


def fake_client(root):
    client = root.resolve()/'client'; client.mkdir()
    data = bytearray(1024)
    data[:2] = b'MZ'; struct.pack_into('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', data, 0x84, 0x14c, 1)
    struct.pack_into('<H', data, 0x94, 224)
    struct.pack_into('<H', data, 0x98, 0x10b)
    struct.pack_into('<I', data, 0x98+28, 0x400000)
    struct.pack_into('<4I', data, 0x98+224+8, 512, 0x5e2700, 512, 512)
    data[512:526] = b'patch-%s-*.MPQ\0'
    data[528:540] = b'patch-*.MPQ\0'
    (client/'Wow.exe').write_bytes(data)
    source = client/'Data'/mpq.PATCH/'Item'; source.mkdir(parents=True)
    (source/'A.blp').write_bytes(b'abcd'*2000)
    (source/'B.blp').write_bytes(bytes(range(256))*40)
    return client


class FormatTests(unittest.TestCase):
    def test_multisector_and_case_lookup(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'test.mpq'
            payload = b'A'*4096 + bytes(range(256))*16 + b'end'
            fixture(p, payload)
            reader = LegacyMPQ(p)
            try:
                self.assertEqual(reader.read('item\\TEST.BLP'), payload)
                with self.assertRaises(FileNotFoundError): reader.read('Item/missing.blp')
            finally: reader.close()

    def test_reject_other_compression_and_bad_header(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'test.mpq'; fixture(p, b'A'*8000, mask=16)
            reader = LegacyMPQ(p)
            try:
                with self.assertRaisesRegex(ValueError, 'Non-zlib'): reader.read('Item/Test.blp')
            finally: reader.close()
            data = bytearray(p.read_bytes()); struct.pack_into('<H', data, 12, 2); p.write_bytes(data)
            with self.assertRaises(ValueError): LegacyMPQ(p)

    def test_loader_and_source_guards(self):
        with tempfile.TemporaryDirectory() as d:
            client = fake_client(Path(d))
            self.assertTrue(mpq.loader(client)['namedPatchScan'])
            exe = client/'Wow.exe'; data = bytearray(exe.read_bytes()); data[537] = ord('?'); exe.write_bytes(data)
            with self.assertRaises(ValueError): mpq.loader(client)
            source = client/'Data'/mpq.PATCH
            (source/'Item'/'bad.blp').symlink_to(source/'Item'/'A.blp')
            with self.assertRaisesRegex(ValueError, 'Symlink'): mpq.inventory(source)
        for name in ['../Item/test.blp', 'Item/test.blp:stream', 'Item/a?/test.blp', 'Character/a.blp', 'Item/../x.blp']:
            with self.assertRaises(ValueError): mpq.asset_name(name)

    def test_exchange_directory_and_file(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d)/'a', Path(d)/'b'; a.mkdir(); (a/'old').write_text('old'); b.write_text('new')
            mpq.exchange(a, b)
            self.assertEqual(a.read_text(), 'new'); self.assertEqual((b/'old').read_text(), 'old')

    def test_v2_unsigned_offsets_above_two_gib(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'sparse.mpq'; payload = b'large-offset'*700
            fixture(p, payload, version=1, table_offset=3*1024**3)
            reader = LegacyMPQ(p)
            try:
                self.assertEqual(reader.read('Item/Test.blp'), payload)
            finally: reader.close()
            # High offsets beyond our 32-bit profile must be refused.
            with p.open('r+b') as stream: stream.seek(40); stream.write(b'\1\0')
            with self.assertRaisesRegex(ValueError, 'High offsets'): LegacyMPQ(p)


@unittest.skipUnless(os.environ.get('STORMLIB_TEST_LIBRARY'), 'Optional native StormLib integration')
class StormTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.client = fake_client(self.root); self.work = self.root/'package'
        self.lib = Path(os.environ['STORMLIB_TEST_LIBRARY'])
        with patch.object(mpq, 'MAX_FILES', 1): mpq.build(self.client, self.work, self.lib)

    def tearDown(self):
        self.temp.cleanup()

    def test_roundtrip_shards_determinism_and_install(self):
        import json
        first = json.loads((self.work/'manifest.json').read_text())
        other = self.root/'repeat'
        with patch.object(mpq, 'MAX_FILES', 1): mpq.build(self.client, other, self.lib)
        second = json.loads((other/'manifest.json').read_text())
        self.assertEqual(first['archives'], second['archives'])
        self.assertEqual(mpq.install(self.client, self.work, self.lib)['state'], 'preview')
        with patch.object(mpq, 'stopped') as check:
            result = mpq.install(self.client, self.work, self.lib, apply=True)
            self.assertEqual(check.call_count, 2)
        self.assertEqual(result['state'], 'installed-verified')
        self.assertEqual(result['verification']['files'], 2)
        self.assertFalse((self.work/mpq.PATCH).exists())
        self.assertFalse((self.client/'DisabledPatches').exists())
        self.assertTrue((self.client/'Data'/mpq.PATCH).is_file())

    def test_running_game_refused_before_any_write(self):
        with patch.object(mpq, 'stopped', side_effect=RuntimeError('running')):
            with self.assertRaisesRegex(RuntimeError, 'running'): mpq.install(self.client, self.work, self.lib, True)
        self.assertTrue((self.client/'Data'/mpq.PATCH).is_dir())
        self.assertFalse((self.client/'Data'/mpq.archive_name(1)).exists())

    def test_later_source_edit_and_archive_tampering_refused(self):
        item = self.client/'Data'/mpq.PATCH/'Item/A.blp'; before = item.read_bytes(); item.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'source changed'): mpq.install(self.client, self.work, self.lib, True)
        item.write_bytes(before)
        archive = self.work/mpq.PATCH
        with archive.open('r+b') as stream: stream.seek(64); stream.write(b'changed')
        with patch.object(mpq, 'stopped'):
            with self.assertRaisesRegex(ValueError, 'Archive hash'): mpq.install(self.client, self.work, self.lib, True)
        self.assertTrue((self.client/'Data'/mpq.PATCH).is_dir())

    def test_occupied_destination_and_protected_edit_refused(self):
        destination = self.client/'Data'/mpq.archive_name(1)
        destination.write_bytes(b'other owner')
        with self.assertRaisesRegex(ValueError, 'occupied'): mpq.install(self.client, self.work, self.lib, True)
        self.assertEqual(destination.read_bytes(), b'other owner')
        destination.unlink()
        (self.client/'other.dll').write_bytes(b'later runtime change')
        with self.assertRaisesRegex(ValueError, 'Protected'): mpq.install(self.client, self.work, self.lib, True)

    def test_source_change_during_final_verification_refused(self):
        original_verify = mpq.verify
        def concurrent_change(*args, **kwargs):
            result = original_verify(*args, **kwargs)
            (self.client/'Data'/mpq.PATCH/'Item/A.blp').write_bytes(b'concurrent edit')
            return result
        with patch.object(mpq, 'stopped'), patch.object(mpq, 'verify', side_effect=concurrent_change):
            with self.assertRaisesRegex(ValueError, 'Client changed'): mpq.install(self.client, self.work, self.lib, True)
        self.assertTrue((self.client/'Data'/mpq.PATCH).is_dir())
        self.assertFalse((self.client/'Data'/mpq.archive_name(1)).exists())
