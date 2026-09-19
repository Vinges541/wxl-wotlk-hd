"""Synthetic archives exercise publication boundaries without any game data."""

import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile


spec = importlib.util.spec_from_file_location(
    'check_distribution', Path(__file__).resolve().parents[1] / 'tools/check_distribution.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class DistributionTests(unittest.TestCase):
    def wheel(self, name, data=b'# source\n', *, symlink=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'example.whl'
            with zipfile.ZipFile(path, 'w') as archive:
                member = zipfile.ZipInfo(name)
                if symlink:
                    member.external_attr = 0o120777 << 16
                archive.writestr(member, data)
            return checker.check_archive(path)

    def test_python_source_accepted(self):
        self.assertEqual(self.wheel('wxl_mounts/model/chunks.py'), 1)

    def test_private_payload_rejected(self):
        for name in ['wxl_mounts/model.m2', '_local/report.json', 'catalog/private.json']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.wheel(name)

    def test_binary_disguised_as_source_rejected(self):
        with self.assertRaises(ValueError):
            self.wheel('wxl_mounts/data.py', b'\x00')

    def test_unsafe_paths_rejected(self):
        for name in ['../wxl_mounts/a.py', '/wxl_mounts/a.py', 'wxl_mounts/../a.py']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.wheel(name)

    def test_zip_symlink_rejected(self):
        with self.assertRaises(ValueError):
            self.wheel('wxl_mounts/a.py', symlink=True)

    def test_tar_links_rejected(self):
        for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'example.tar.gz'
                with tarfile.open(path, 'w:gz') as archive:
                    source = tarfile.TarInfo('example/README.md')
                    source.size = 8
                    archive.addfile(source, io.BytesIO(b'# source'))
                    link = tarfile.TarInfo('example/docs/BUILD.md')
                    link.type = kind
                    link.linkname = 'example/README.md'
                    archive.addfile(link)
                with self.assertRaises(ValueError):
                    checker.check_archive(path)
