"""Reject assets and unexpected files in public wheel/sdist archives without extraction."""

import argparse
import fnmatch
from pathlib import Path
import re
import stat
import tarfile
import zipfile


SOURCE_PATHS = (
    'AGENTS.md', 'CONTRIBUTING.md', 'LICENSE', 'MANIFEST.in', 'README.md',
    'THIRD-PARTY-NOTICES.md', 'dependencies.lock.json', 'pyproject.toml',
    'PKG-INFO', 'setup.cfg', 'docs/*.md', 'tests/test_*.py',
    'tools/*.py', 'tools/*.cjs', 'runtime/creature_redirect.c',
    'catalog/creature-adapter-source.json', 'catalog/model-reader-source.json',
    'catalog/families.json', 'catalog/replacements.json',
    'src/wxl_mounts/*.py', 'src/wxl_modern_mounts.egg-info/*.txt',
    'src/wxl_modern_mounts.egg-info/PKG-INFO',
)
WHEEL_PATHS = (
    'wxl_mounts/*.py', 'wxl_modern_mounts-*.dist-info/METADATA',
    'wxl_modern_mounts-*.dist-info/WHEEL', 'wxl_modern_mounts-*.dist-info/RECORD',
    'wxl_modern_mounts-*.dist-info/entry_points.txt',
    'wxl_modern_mounts-*.dist-info/top_level.txt',
    'wxl_modern_mounts-*.dist-info/licenses/LICENSE',
    'wxl_modern_mounts-*.dist-info/licenses/THIRD-PARTY-NOTICES.md',
)
MAX_SOURCE_BYTES = 1024 * 1024


def check_archive(path):
    path = Path(path)
    wheel = path.name.endswith('.whl')
    if not wheel and not path.name.endswith('.tar.gz'):
        raise ValueError('Expected a wheel or source tarball')
    root = path.name.removesuffix('.tar.gz')
    patterns = WHEEL_PATHS if wheel else SOURCE_PATHS
    seen = set()
    count = 0
    with zipfile.ZipFile(path) if wheel else tarfile.open(path, 'r:gz') as archive:
        for member in archive.infolist() if wheel else archive.getmembers():
            name = member.filename if wheel else member.name
            parts = name.rstrip('/').split('/')
            if any(not re.fullmatch(r'[A-Za-z0-9_.+-]+', p) or p in ('.', '..') for p in parts):
                raise ValueError(f'Unsafe member path: {name}')
            if name.casefold().rstrip('/') in seen:
                raise ValueError(f'Duplicate member: {name}')
            seen.add(name.casefold().rstrip('/'))
            if wheel:
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError(f'Symlink member: {name}')
                directory = member.is_dir()
                size = member.file_size
            else:
                if parts[0] != root or not (member.isfile() or member.isdir()):
                    raise ValueError(f'Unexpected tar member: {name}')
                directory = member.isdir()
                size = member.size
            if directory:
                continue
            relative = name if wheel else '/'.join(parts[1:])
            if not any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns):
                raise ValueError(f'File outside public source layout: {name}')
            if size > MAX_SOURCE_BYTES:
                raise ValueError(f'Oversized source file: {name}')
            data = archive.read(member) if wheel else archive.extractfile(member).read()
            if b'\x00' in data:
                raise ValueError(f'Binary payload: {name}')
            data.decode('utf-8')
            count += 1
    if not count:
        raise ValueError('Empty distribution')
    return count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='+', type=Path)
    for source in parser.parse_args().archives:
        print(f'{source.name}: {check_archive(source)} source/metadata files checked')
