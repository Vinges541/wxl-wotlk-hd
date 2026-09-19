"""Strict legacy readers. MPQ reader adapted from wxl-modern-races (GPL-3.0+)."""
import ctypes as c
import hashlib
import io
import struct
from pathlib import Path, PurePosixPath
from PIL import Image


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(name):
    name = name.replace('\\', '/')
    p = PurePosixPath(name)
    if not name or p.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')) or ':' in name:
        raise ValueError('Unsafe asset path')
    return name


class EmptyAsset(ValueError):
    """An empty higher-priority entry must never fall through to an older texture."""
    def __init__(self, name, archive):
        super().__init__(f'Empty asset in {archive}: {name}')
        self.archive = archive


class MPQ:
    def __init__(self, library, archives):
        self.archives = [Path(a) for a in archives]
        self._handles = {}
        self.lib = lib = c.CDLL(str(library))
        signatures = {
            'SFileOpenArchive': [c.c_char_p, c.c_uint32, c.c_uint32, c.POINTER(c.c_void_p)],
            'SFileOpenFileEx': [c.c_void_p, c.c_char_p, c.c_uint32, c.POINTER(c.c_void_p)],
            'SFileGetFileSize': [c.c_void_p, c.c_void_p],
            'SFileReadFile': [c.c_void_p, c.c_void_p, c.c_uint32, c.POINTER(c.c_uint32), c.c_void_p],
            'SFileCloseFile': [c.c_void_p], 'SFileCloseArchive': [c.c_void_p],
        }
        for name, args in signatures.items():
            getattr(lib, name).argtypes = args
        lib.SFileGetFileSize.restype = c.c_uint32

    def read(self, name):
        name = safe_path(name).replace('/', '\\')
        for archive in self.archives:
            handle = self._handles.get(archive)
            if handle is None:
                handle = c.c_void_p()
                if not self.lib.SFileOpenArchive(str(archive).encode(), 0, 0x100, c.byref(handle)):
                    raise OSError(f'Cannot open archive: {archive}')
                self._handles[archive] = handle
            try:
                file = c.c_void_p()
                if not self.lib.SFileOpenFileEx(handle, name.encode(), 0, c.byref(file)):
                    continue
                try:
                    size = self.lib.SFileGetFileSize(file, None)
                    if size == 0:
                        raise EmptyAsset(name, archive.name)
                    if not 0 < size <= 64 * 1024 * 1024:
                        raise ValueError('Invalid asset size')
                    buffer, count = c.create_string_buffer(size), c.c_uint32()
                    if not self.lib.SFileReadFile(file, buffer, size, c.byref(count), None) or count.value != size:
                        raise ValueError('Incomplete MPQ read')
                    return buffer.raw, archive.name
                finally:
                    self.lib.SFileCloseFile(file)
            finally:
                pass  # Cache archive tables for a batch; close() releases handles.
        raise FileNotFoundError(name)

    def close(self):
        for handle in self._handles.values():
            self.lib.SFileCloseArchive(handle)
        self._handles.clear()

    def __del__(self):
        self.close()


class DBC:
    def __init__(self, data, fields):
        magic, count, actual, size, strings = struct.unpack_from('<4s4I', data)
        if magic != b'WDBC' or actual != fields or size != fields * 4 or len(data) != 20 + count * size + strings:
            raise ValueError('Unexpected DBC layout')
        self.rows = {}
        for i in range(count):
            row = struct.unpack_from(f'<{fields}I', data, 20 + i * size)
            if row[0] in self.rows:
                raise ValueError('Duplicate DBC ID')
            self.rows[row[0]] = row
        self.strings = data[20 + count * size:]

    def string(self, offset):
        end = self.strings.find(b'\0', offset)
        if offset >= len(self.strings) or end < 0:
            raise ValueError('Bad DBC string')
        return self.strings[offset:end].decode('utf-8')


SECTIONS = ['ArmUpperTexture', 'ArmLowerTexture', 'HandTexture', 'TorsoUpperTexture',
            'TorsoLowerTexture', 'LegUpperTexture', 'LegLowerTexture', 'FootTexture']


def item_assets(item, display):
    """Return texture candidates, retaining gender suffix alternatives for MPQ resolution."""
    row = display.rows[item[5]]
    results = []
    for index, section in enumerate(SECTIONS, 15):
        stem = display.string(row[index])
        if stem:
            results.append({'kind': 'component', 'section': section, 'stem': stem,
                            'candidates': [f'Item/TextureComponents/{section}/{stem}_{suffix}.blp' for suffix in ['U', 'M', 'F']]})
    for model_index in (1, 2):
        model = display.string(row[model_index])
        texture = display.string(row[model_index + 2])
        if not model or not texture:
            continue
        folder = 'Weapon' if item[1] == 2 else {14: 'Shield', 1: 'Head', 3: 'Shoulder'}.get(item[6])
        if not folder:
            continue
        results.append({'kind': 'object', 'model': f'Item/ObjectComponents/{folder}/{Path(model).stem}.m2',
                        'candidates': [f'Item/ObjectComponents/{folder}/{texture}.blp']})
    return results


def encode_blp(image):
    """BLP2 uncompressed BGRA with full mip chain; alpha is never quantized to DXT1."""
    image = image.convert('RGBA')
    w, h = image.size
    if max(w, h) > 2048 or min(w, h) < 1 or w & (w-1) or h & (h-1):
        raise ValueError('Power-of-two dimensions up to 2048 required')
    levels = []
    while True:
        levels.append(image.tobytes('raw', 'BGRA'))
        if image.size == (1, 1):
            break
        image = image.resize((max(1, image.width//2), max(1, image.height//2)), Image.Resampling.BOX)
    offsets, sizes, cursor = [0]*16, [0]*16, 148
    for i, level in enumerate(levels):
        offsets[i], sizes[i] = cursor, len(level)
        cursor += len(level)
    return struct.pack('<4sI4B2I16I16I', b'BLP2', 1, 3, 8, 2, 1, w, h, *offsets, *sizes) + b''.join(levels)


def decode_blp(data):
    if data[:4] != b'BLP2' or len(data) < 148:
        raise ValueError('Expected BLP2')
    encoding, alpha = data[8], data[9]
    w, h = struct.unpack_from('<2I', data, 12)
    if not 0 < w <= 2048 or not 0 < h <= 2048:
        raise ValueError('Invalid dimensions')
    offset, size = struct.unpack_from('<I', data, 20)[0], struct.unpack_from('<I', data, 84)[0]
    if offset < 148 or offset+size > len(data):
        raise ValueError('Invalid mip')
    if encoding == 1:
        import numpy as np
        count=w*h
        if alpha not in (0,1,4,8) or size < count+(count*alpha+7)//8 or offset < 1172:
            raise ValueError('Invalid palette/alpha payload')
        # Equivalent integer palette/alpha expansion, without a Python loop for
        # every pixel of every source and independently validated output mip.
        indices=np.frombuffer(data,dtype=np.uint8,count=count,offset=offset)
        palette=np.frombuffer(data,dtype=np.uint8,count=1024,offset=148).reshape(256,4)
        pixels=np.empty((count,4),dtype=np.uint8)
        pixels[:,:3]=palette[indices,:3][:,::-1]
        if not alpha:
            pixels[:,3]=255
        elif alpha==8:
            pixels[:,3]=np.frombuffer(data,dtype=np.uint8,count=count,offset=offset+count)
        else:
            masks=np.frombuffer(data,dtype=np.uint8,count=(count*alpha+7)//8,offset=offset+count)
            bits=np.arange(count,dtype=np.uint32)*alpha
            pixels[:,3]=((masks[bits//8] >> (bits%8)) & ((1<<alpha)-1))*(255//((1<<alpha)-1))
        return Image.frombytes('RGBA',(w,h),pixels.tobytes())
    if encoding == 3:
        if size != w*h*4:
            raise ValueError('Invalid BGRA payload')
        return Image.frombytes('RGBA',(w,h),data[offset:offset+size],'raw','BGRA')
    return Image.open(io.BytesIO(data)).convert('RGBA')


def inspect_blp(data):
    if len(data) < 148 or data[:4] != b'BLP2':
        raise ValueError('Expected BLP2')
    w, h = struct.unpack_from('<2I', data, 12)
    offsets = struct.unpack_from('<16I', data, 20)
    sizes = struct.unpack_from('<16I', data, 84)
    for offset, size in zip(offsets, sizes):
        if (offset == 0) != (size == 0) or (size and (offset < 148 or offset + size > len(data))):
            raise ValueError('BLP mip outside file')
    image = decode_blp(data)
    return {'width': w, 'height': h, 'encoding': data[8], 'alphaDepth': data[9],
            'alphaEncoding': data[10], 'mips': sum(bool(s) for s in sizes), 'alphaRange': image.getchannel('A').getextrema()}
