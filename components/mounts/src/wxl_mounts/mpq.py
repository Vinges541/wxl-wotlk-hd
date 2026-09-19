"""Read only explicitly ordered MPQs using a caller-supplied StormLib."""
import ctypes as c
import hashlib
import os

from .dbc import DBC, LAYOUTS
from .io import checked_path, write_json


class Reader:
    def __init__(self, library, archives):
        self.handles = []
        lib = self.lib = c.CDLL(str(checked_path(library)))
        signatures = {
            'SFileOpenArchive': [c.c_char_p, c.c_uint32, c.c_uint32, c.POINTER(c.c_void_p)],
            'SFileOpenFileEx': [c.c_void_p, c.c_char_p, c.c_uint32, c.POINTER(c.c_void_p)],
            'SFileGetFileSize': [c.c_void_p, c.POINTER(c.c_uint32)],
            'SFileReadFile': [c.c_void_p, c.c_void_p, c.c_uint32, c.POINTER(c.c_uint32), c.c_void_p],
            'SFileCloseFile': [c.c_void_p], 'SFileCloseArchive': [c.c_void_p],
        }
        for name, args in signatures.items():
            fn = getattr(lib, name)
            fn.argtypes = args
            fn.restype = c.c_uint32 if name == 'SFileGetFileSize' else c.c_bool
        # StormLib exports its own error function on macOS/Linux.
        lib.SErrGetLastError.argtypes = []
        lib.SErrGetLastError.restype = c.c_uint32
        try:
            for value in archives:
                path = checked_path(value)
                if not path.is_file():
                    raise ValueError(f'Expected an archive, not a loose patch: {path}')
                handle = c.c_void_p()
                if not lib.SFileOpenArchive(os.fsencode(path), 0, 0x100, c.byref(handle)):
                    raise OSError(f'Cannot open MPQ: {path.name}')
                self.handles.append((path, handle))
        except Exception:
            self.close()
            raise

    def read(self, name):
        for path, handle in self.handles:
            file = c.c_void_p()
            if not self.lib.SFileOpenFileEx(handle, name.encode('ascii'), 0, c.byref(file)):
                error = self.lib.SErrGetLastError()
                if error == 2:  # ERROR_FILE_NOT_FOUND only; corruption must not fall through.
                    continue
                raise OSError(f'MPQ member open failed ({error}): {path.name}: {name}')
            try:
                high = c.c_uint32()
                size = self.lib.SFileGetFileSize(file, c.byref(high))
                if high.value or not 0 < size <= 128 * 1024**2:
                    raise ValueError(f'Invalid DBC size in {path.name}')
                buffer, count = c.create_string_buffer(size), c.c_uint32()
                if (not self.lib.SFileReadFile(file, buffer, size, c.byref(count), None)
                        or count.value != size):
                    raise OSError(f'Incomplete MPQ read: {name}')
                return buffer.raw, path.name
            finally:
                self.lib.SFileCloseFile(file)
        raise FileNotFoundError(name)

    def close(self):
        for _, handle in self.handles:
            self.lib.SFileCloseArchive(handle)
        self.handles.clear()


def extract(library, archives, output):
    root = checked_path(output)
    if root.exists():
        raise FileExistsError(root)
    reader = Reader(library, archives)
    tables = {}
    try:
        for name in LAYOUTS:
            data, archive = reader.read('DBFilesClient\\' + name + '.dbc')
            DBC(data, name)
            tables[name] = (data, archive)
    finally:
        reader.close()
    root.mkdir()  # All inputs validated before creating the fresh output.
    manifest = {'schemaVersion': 1, 'clientBuild': 12340,
                'archivePrecedence': [checked_path(a).name for a in archives], 'tables': {}}
    for name, (data, archive) in tables.items():
        with (root / (name + '.dbc')).open('xb') as stream:
            stream.write(data)
        manifest['tables'][name] = {'archive': archive, 'bytes': len(data),
                                   'sha256': hashlib.sha256(data).hexdigest()}
    write_json(root / 'sources.json', manifest)
    return {'tables': len(tables), 'output': str(root)}
