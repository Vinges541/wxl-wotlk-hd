"""Narrow, verified MPQ packaging helpers (GPL-3.0+); see source provenance."""
import ctypes as c
import hashlib,json,os,re,stat,struct
from pathlib import Path
from .io import checked_path as no_links
from .mpq_format import hash_name, LIMIT
MAX_FILES = 60000
MAX_RESOURCE = 64 * 1024**2

def sha(data):
    return hashlib.sha256(data).hexdigest()

def digest(path):
    result = hashlib.sha256()
    with no_links(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            result.update(chunk)
    return result.hexdigest()

def asset_name(name):
    if (not isinstance(name, str) or not name or len(name) >= 260
            or any(ord(ch) < 32 or ord(ch) > 126 or ch in '\\:*?"<>|' for ch in name)
            or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in name.split('/'))):
        raise ValueError('Unsafe or non-ASCII MPQ path')
    if name.lower() in ('(listfile)', '(attributes)', '(signature)'):
        raise ValueError('Reserved MPQ metadata name')
    return name

def check_names(rows):
    names = set()
    hashes = {(hash_name('(listfile)', 1), hash_name('(listfile)', 2))}
    for row in rows:
        name = asset_name(row['path'])
        pair = (hash_name(name, 1), hash_name(name, 2))
        if name.upper() in names or pair in hashes:
            raise ValueError('Case-insensitive or MPQ name-hash collision')
        names.add(name.upper()); hashes.add(pair)
        if not isinstance(row['size'], int) or not 0 < row['size'] <= MAX_RESOURCE:
            raise ValueError('Resource outside supported size range')
        if not re.fullmatch('[0-9a-f]{64}', row['sha256']):
            raise ValueError('Invalid resource digest')
    if not rows:
        raise ValueError('Empty source')

def inventory(root, progress=False):
    root = no_links(root)
    if not root.is_dir():
        raise ValueError('Expected a loose patch directory')
    rows = []
    for path in sorted(root.rglob('*')):
        no_links(path)
        mode = path.stat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError('Non-regular filesystem entry')
        name = asset_name(path.relative_to(root).as_posix())
        rows.append({'path': name, 'size': path.stat().st_size, 'sha256': digest(path)})
        if progress and len(rows) % 5000 == 0:
            print(f'Inventory: {len(rows)} files', flush=True)
    check_names(rows)
    return rows

def read_va(data, va, size):
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[:2] != b'MZ' or data[pe:pe+4] != b'PE\0\0':
        raise ValueError('Expected a PE client')
    if struct.unpack_from('<H', data, pe+4)[0] != 0x14c:
        raise ValueError('Expected x86 client')
    opt = pe+24
    if struct.unpack_from('<H', data, opt)[0] != 0x10b:
        raise ValueError('Expected PE32')
    base = struct.unpack_from('<I', data, opt+28)[0]
    table = opt + struct.unpack_from('<H', data, pe+20)[0]
    for i in range(struct.unpack_from('<H', data, pe+6)[0]):
        _, rva, raw_size, raw = struct.unpack_from('<4I', data, table+i*40+8)
        if rva <= va-base and va-base+size <= rva+raw_size:
            offset = raw + va-base-rva
            return data[offset:offset+size]
    raise ValueError('Client VA not mapped')

class CreateInfo(c.Structure):
    _fields_ = [('cbSize', c.c_uint32), ('version', c.c_uint32), ('user', c.c_void_p)] + [
        (name, c.c_uint32) for name in ('userBytes', 'streamFlags', 'listFlags', 'attrFlags',
                                      'sigFlags', 'attributes', 'sector', 'rawChunk', 'maxFiles')]

class Storm:
    def __init__(self, library):
        self.lib = lib = c.CDLL(str(no_links(library)))
        signatures = {
            'SFileCreateArchive2': [c.c_char_p, c.POINTER(CreateInfo), c.POINTER(c.c_void_p)],
            'SFileCreateFile': [c.c_void_p, c.c_char_p, c.c_uint64, c.c_uint32, c.c_uint32, c.c_uint32, c.POINTER(c.c_void_p)],
            'SFileWriteFile': [c.c_void_p, c.c_void_p, c.c_uint32, c.c_uint32],
            'SFileFinishFile': [c.c_void_p], 'SFileCloseArchive': [c.c_void_p],
            'SFileOpenArchive': [c.c_char_p, c.c_uint32, c.c_uint32, c.POINTER(c.c_void_p)],
            'SFileOpenFileEx': [c.c_void_p, c.c_char_p, c.c_uint32, c.POINTER(c.c_void_p)],
            'SFileReadFile': [c.c_void_p, c.c_void_p, c.c_uint32, c.POINTER(c.c_uint32), c.c_void_p],
            'SFileCloseFile': [c.c_void_p],
        }
        for name, args in signatures.items():
            getattr(lib, name).argtypes = args
            getattr(lib, name).restype = c.c_bool
        lib.SFileGetFileSize.argtypes = [c.c_void_p, c.POINTER(c.c_uint32)]
        lib.SFileGetFileSize.restype = c.c_uint32

    def create(self, path, max_files=MAX_FILES):
        if no_links(path).exists():
            raise FileExistsError(path)
        info = CreateInfo()
        info.cbSize = c.sizeof(info); info.version = 1
        info.listFlags = 0x200; info.sector = 4096; info.maxFiles = max_files
        handle = c.c_void_p()
        if not self.lib.SFileCreateArchive2(os.fsencode(path), c.byref(info), c.byref(handle)):
            raise OSError('SFileCreateArchive2 failed')
        return handle

    def add(self, handle, name, data):
        member = c.c_void_p()
        if not self.lib.SFileCreateFile(handle, name.replace('/', '\\').encode('ascii'), 0, len(data), 0, 0x200, c.byref(member)):
            raise OSError('SFileCreateFile failed: '+name)
        try:
            success = self.lib.SFileWriteFile(member, data, len(data), 2)
        finally:
            finished = self.lib.SFileFinishFile(member)
        if not success or not finished:
            raise OSError('SFileWriteFile/FinishFile failed: '+name)

    def close(self, handle):
        if not self.lib.SFileCloseArchive(handle):
            raise OSError('SFileCloseArchive failed')

    def open(self, path):
        handle = c.c_void_p()
        if not self.lib.SFileOpenArchive(os.fsencode(no_links(path)), 0, 0x100, c.byref(handle)):
            raise OSError('SFileOpenArchive failed')
        return handle

    def read(self, handle, name):
        member, high = c.c_void_p(), c.c_uint32()
        if not self.lib.SFileOpenFileEx(handle, name.replace('/', '\\').encode('ascii'), 0, c.byref(member)):
            raise OSError('SFileOpenFileEx failed: '+name)
        try:
            size = self.lib.SFileGetFileSize(member, c.byref(high))
            if high.value or not 0 < size <= MAX_RESOURCE:
                raise ValueError('Unexpected MPQ resource size')
            buffer, read = c.create_string_buffer(size), c.c_uint32()
            if not self.lib.SFileReadFile(member, buffer, size, c.byref(read), None) or read.value != size:
                raise OSError('Incomplete MPQ read')
            return buffer.raw
        finally:
            self.lib.SFileCloseFile(member)
