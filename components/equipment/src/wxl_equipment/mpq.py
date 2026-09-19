"""Lossless equipment MPQs: build, independently verify, preview and install.

Only the dedicated Item overlay is owned here. Installation exchanges the first
archive and the loose directory atomically, then removes the replaced directory.
No rollback copy is made. A physical client path is required (resolve app aliases).
"""
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import time

from .assets import MPQ, safe_path, sha
from .batch import write_json
from .package import PATCH, no_links, stopped
from .mpq_format import LegacyMPQ, hash_name, LIMIT

MAX_FILES = 30000
TABLE_RESERVE = 16 * 1024**2
PROFILE = {'formatVersion': 1, 'sectorBytes': 4096, 'compression': 'zlib',
           'locale': 0, 'fileTimes': 0, 'maxArchiveBytes': LIMIT - 1,
           'maxFilesPerArchive': MAX_FILES, 'lossless': True}


def digest(path):
    with no_links(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def asset_name(name):
    if safe_path(name) != name or any(ch in name for ch in '\\:*?"<>|') or any(ord(ch) < 32 or ord(ch) > 126 for ch in name):
        raise ValueError('Unsupported MPQ path')
    if len(name) >= 260 or not name.lower().startswith('item/') or not name.lower().endswith('.blp') or any(p.endswith((' ', '.')) for p in name.split('/')):
        raise ValueError('Outside equipment scope')
    return name


def inventory(root):
    no_links(root)
    rows, names, hashes = [], set(), set()
    for path in sorted(root.rglob('*')):
        no_links(path)
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('Special filesystem entry')
        name = asset_name(path.relative_to(root).as_posix())
        pair = (hash_name(name, 1), hash_name(name, 2))
        if name.upper() in names or pair in hashes:
            raise ValueError('Case-insensitive or MPQ name-hash collision')
        names.add(name.upper()); hashes.add(pair)
        size = path.stat().st_size
        if not 0 < size <= 64 * 1024**2:
            raise ValueError('Unsupported input size')
        rows.append({'path': name, 'size': size, 'sha256': digest(path)})
    if not rows:
        raise ValueError('Empty equipment directory')
    return sorted(rows, key=lambda row: row['path'])


def loader(client):
    data = no_links(client / 'Wow.exe').read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[:2] != b'MZ' or data[pe:pe+4] != b'PE\0\0' or struct.unpack_from('<H', data, pe+4)[0] != 0x14c:
        raise ValueError('Expected x86 PE client')
    opt = pe + 24
    if struct.unpack_from('<H', data, opt)[0] != 0x10b:
        raise ValueError('Expected PE32')
    base = struct.unpack_from('<I', data, opt+28)[0]
    sections = opt + struct.unpack_from('<H', data, pe+20)[0]
    def read_va(va, size):
        for i in range(struct.unpack_from('<H', data, pe+6)[0]):
            _, rva, raw_size, raw = struct.unpack_from('<4I', data, sections+i*40+8)
            if rva <= va-base and va-base+size <= rva+raw_size:
                start = raw + va-base-rva
                return data[start:start+size]
        raise ValueError('Client address not mapped')
    for va, expected in [(0x9e2700, b'patch-%s-*.MPQ\0'), (0x9e2710, b'patch-*.MPQ\0')]:
        if read_va(va, len(expected)) != expected:
            raise ValueError('Build-12340 named-patch scan not present')
    return {'exeSha256': sha(data), 'namedPatchScan': True,
            'evidence': 'PE scan patterns; actual game loading is not executed'}


def protected(client):
    """Digest protected file contents without recording account/config names."""
    paths = [p for p in client.iterdir() if p.is_file() and p.suffix.lower() in ('.exe', '.dll', '.wtf')]
    if (client / 'WTF').exists():
        paths += [p for p in (client / 'WTF').rglob('*') if p.is_file()]
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.relative_to(client).as_posix().encode() + b'\0' + bytes.fromhex(digest(p)))
    return {'files': len(paths), 'sha256': h.hexdigest()}


class CreateInfo(c.Structure):
    _fields_ = [('cbSize', c.c_uint32), ('version', c.c_uint32), ('user', c.c_void_p)] + [
        (name, c.c_uint32) for name in ('userBytes', 'streamFlags', 'listFlags', 'attrFlags',
                                      'sigFlags', 'attributes', 'sector', 'rawChunk', 'maxFiles')]


class Writer:
    def __init__(self, library, path):
        self.lib = lib = c.CDLL(str(library))
        for name, args in {
            'SFileCreateArchive2': [c.c_char_p, c.POINTER(CreateInfo), c.POINTER(c.c_void_p)],
            'SFileCreateFile': [c.c_void_p, c.c_char_p, c.c_uint64, c.c_uint32, c.c_uint32, c.c_uint32, c.POINTER(c.c_void_p)],
            'SFileWriteFile': [c.c_void_p, c.c_void_p, c.c_uint32, c.c_uint32],
            'SFileFinishFile': [c.c_void_p], 'SFileCloseArchive': [c.c_void_p],
        }.items():
            getattr(lib, name).argtypes = args
            getattr(lib, name).restype = c.c_bool
        info = CreateInfo()
        info.cbSize = c.sizeof(info); info.version = PROFILE['formatVersion']; info.listFlags = 0x200
        info.sector = 4096; info.maxFiles = PROFILE['maxFilesPerArchive']
        self.handle = c.c_void_p()
        if path.exists() or not lib.SFileCreateArchive2(os.fsencode(path), c.byref(info), c.byref(self.handle)):
            raise OSError('Cannot create fresh MPQ')

    def add(self, name, data):
        file = c.c_void_p()
        if not self.lib.SFileCreateFile(self.handle, name.replace('/', '\\').encode('ascii'), 0, len(data), 0, 0x200, c.byref(file)):
            raise OSError('Cannot create MPQ member')
        written = self.lib.SFileWriteFile(file, data, len(data), 2)
        finished = self.lib.SFileFinishFile(file)
        if not written or not finished:
            raise OSError('Cannot finish MPQ member')

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            if not self.lib.SFileCloseArchive(handle):
                raise OSError('Cannot close MPQ')


def archive_name(index):
    return PATCH if index == 0 else f'Patch-WXL-Equipment-{index+1:03d}.MPQ'


def validate_manifest(manifest):
    if manifest['schema'] != 1 or manifest['profile'] != PROFILE:
        raise ValueError('Unsupported packing profile')
    names, pairs = set(), set()
    for i, archive in enumerate(manifest['archives']):
        if archive['name'] != archive_name(i) or not 0 < archive['size'] < LIMIT or not 0 < len(archive['files']) <= MAX_FILES:
            raise ValueError('Invalid archive entry')
        for row in archive['files']:
            name = asset_name(row['path']); pair = (hash_name(name, 1), hash_name(name, 2))
            if name.upper() in names or pair in pairs:
                raise ValueError('Duplicate/colliding member')
            names.add(name.upper()); pairs.add(pair)
    if not names:
        raise ValueError('Empty package')


def verify(workspace, library, manifest, archive_root=None):
    validate_manifest(manifest)
    total = 0
    for entry in manifest['archives']:
        path = no_links((archive_root or workspace) / entry['name'])
        if path.stat().st_size != entry['size'] or digest(path) != entry['sha256']:
            raise ValueError('Archive hash changed')
        native = MPQ(library, [path]); independent = LegacyMPQ(path)
        try:
            if independent.header['formatVersion'] != PROFILE['formatVersion']:
                raise ValueError('Archive version differs from the manifest profile')
            listed = independent.read('(listfile)').decode('ascii').splitlines()
            actual = {n.replace('\\', '/') for n in listed if n != '(listfile)'}
            expected = {r['path'] for r in entry['files']}
            if actual != expected or len(actual) != len([n for n in listed if n != '(listfile)']) or len(independent.blocks) != len(expected)+1:
                raise ValueError('Listfile/coverage mismatch')
            for row in entry['files']:
                first = independent.read(row['path'].swapcase())
                second, _ = native.read(row['path'].swapcase())
                if len(first) != row['size'] or sha(first) != row['sha256'] or second != first:
                    raise ValueError('Member readback mismatch: ' + row['path'])
                total += 1
        finally:
            independent.close(); native.close()
    return {'files': total, 'readers': ['StormLib', 'independent-legacy-zlib'], 'caseInsensitiveLookup': True}


def build(client, workspace, library, max_bytes=LIMIT-1):
    no_links(client); no_links(workspace); no_links(library)
    if workspace.exists() or workspace.absolute().is_relative_to(client.absolute()) or not TABLE_RESERVE + 64*1024**2 < max_bytes < LIMIT:
        raise ValueError('Fresh workspace and compatible size limit required')
    source = no_links(client / 'Data' / PATCH)
    if not source.is_dir():
        raise ValueError('Expected the current loose equipment patch')
    guard = protected(client); scan = loader(client)
    rows = inventory(source)
    workspace.mkdir(parents=True)
    manifest = {'schema': 1, 'profile': PROFILE, 'loader': scan, 'protected': guard,
                'sourceBytes': sum(r['size'] for r in rows), 'sourceAllocatedBytes': sum((source/r['path']).stat().st_blocks*512 for r in rows),
                'archives': []}
    writer = None
    try:
        for row in rows:
            # Compressed sectors are stored raw when compression does not help.
            # Reserve the uncompressed upper bound, sector offsets and tables.
            bound = row['size'] + ((row['size']+4095)//4096+1)*4
            if writer is None or path.stat().st_size + bound + TABLE_RESERVE >= max_bytes or len(entry['files']) >= MAX_FILES:
                if writer is not None:
                    writer.close(); entry.update(size=path.stat().st_size, sha256=digest(path))
                path = workspace / archive_name(len(manifest['archives']))
                entry = {'name': path.name, 'files': []}; manifest['archives'].append(entry)
                writer = Writer(library, path)
            data = no_links(source/row['path']).read_bytes()
            if len(data) != row['size'] or sha(data) != row['sha256']:
                raise ValueError('Input changed during packing')
            writer.add(row['path'], data); entry['files'].append(row)
        writer.close(); entry.update(size=path.stat().st_size, sha256=digest(path))
    finally:
        if writer is not None:
            writer.close()
    if inventory(source) != rows or protected(client) != guard or loader(client) != scan:
        raise ValueError('Client changed during packing')
    manifest['verification'] = verify(workspace, library, manifest)
    manifest['state'] = 'verified'
    write_json(workspace/'manifest.json', manifest)
    return {'state': 'verified', 'files': len(rows), 'sourceBytes': manifest['sourceBytes'],
            'archives': [{k: v for k, v in a.items() if k != 'files'} for a in manifest['archives']]}


def exchange(first, second):
    """Atomic same-volume swap, including a directory and a regular file."""
    lib = c.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        fn = lib.renamex_np; fn.argtypes = [c.c_char_p, c.c_char_p, c.c_uint]
        result = fn(os.fsencode(first), os.fsencode(second), 2)
    elif sys.platform.startswith('linux'):
        fn = lib.renameat2; fn.argtypes = [c.c_int, c.c_char_p, c.c_int, c.c_char_p, c.c_uint]
        result = fn(-100, os.fsencode(first), -100, os.fsencode(second), 2)
    else:
        raise RuntimeError('Atomic exchange unavailable on this platform')
    if result:
        raise OSError(c.get_errno(), 'Atomic exchange failed')


def install(client, workspace, library, apply=False):
    no_links(client); no_links(workspace)
    manifest = json.loads(no_links(workspace/'manifest.json').read_text())
    validate_manifest(manifest)
    if manifest.get('state') != 'verified':
        raise ValueError('Verified build required')
    if protected(client) != manifest['protected'] or loader(client) != manifest['loader']:
        raise ValueError('Protected client files changed')
    source = no_links(client/'Data'/PATCH)
    rows = sorted([r for a in manifest['archives'] for r in a['files']], key=lambda r: r['path'])
    if inventory(source) != rows:
        raise ValueError('Loose source changed')
    for a in manifest['archives'][1:]:
        if no_links(client/'Data'/a['name']).exists():
            raise ValueError('Archive destination occupied')
    if source.stat().st_dev != workspace.stat().st_dev:
        raise ValueError('Atomic installation requires the same volume')
    result = {'state': 'preview', 'files': len(rows), 'beforeBytes': manifest['sourceBytes'],
              'afterBytes': sum(a['size'] for a in manifest['archives']),
              'archives': [a['name'] for a in manifest['archives']], 'backupsCreated': False,
              'gameplayVerified': False}
    if not apply:
        return result
    stopped()
    verify(workspace, library, manifest)
    # Recheck after full decompression, immediately before filesystem mutation.
    if inventory(source) != rows or protected(client) != manifest['protected']:
        raise ValueError('Client changed before installation')
    stopped()
    # Extra shards contain only identical copies of the still-active loose files.
    for a in manifest['archives'][1:]:
        dest = no_links(client/'Data'/a['name'])
        if dest.exists():
            raise ValueError('Archive destination became occupied')
        os.link(workspace/a['name'], dest)  # Exclusive creation, no overwrite.
        (workspace/a['name']).unlink()
    exchange(workspace/PATCH, source)
    result['state'] = 'installed-awaiting-final-verification'
    write_json(workspace/'installation.json', result)
    result['verification'] = verify(workspace, library, manifest, client/'Data')
    if protected(client) != manifest['protected']:
        raise ValueError('Protected files changed after installation')
    # The exchanged old directory is removed, never retained as a rollback copy.
    shutil.rmtree(workspace/PATCH)
    result.update(state='installed-verified', completedAt=time.time(),
                  beforeAllocatedBytes=manifest['sourceAllocatedBytes'],
                  afterAllocatedBytes=sum((client/'Data'/a['name']).stat().st_blocks*512 for a in manifest['archives']))
    write_json(workspace/'installation.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'verify', 'install'])
    parser.add_argument('--client', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--stormlib', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--max-archive-bytes', type=int, default=LIMIT-1)
    args = parser.parse_args()
    if args.action == 'build':
        result = build(args.client, args.workspace, args.stormlib, args.max_archive_bytes)
    elif args.action == 'verify':
        result = verify(args.workspace, args.stormlib, json.loads((args.workspace/'manifest.json').read_text()))
    else:
        result = install(args.client, args.workspace, args.stormlib, args.apply)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
