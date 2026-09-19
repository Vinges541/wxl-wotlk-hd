"""Strict WDBC layouts for build 12340; see docs/SOURCES.md."""
import struct

LAYOUTS = {'Spell': 234, 'CreatureDisplayInfo': 16, 'CreatureModelData': 28}


class DBC:
    def __init__(self, data, name):
        fields = LAYOUTS[name]
        if len(data) < 20:
            raise ValueError(f'Truncated {name} header')
        magic, count, actual, stride, strings = struct.unpack_from('<4s4I', data)
        end = 20 + count * stride
        if (magic != b'WDBC' or actual != fields or stride != fields * 4
                or count > 1_000_000 or strings < 1 or len(data) != end + strings
                or data[end] != 0 or data[-1] != 0):
            raise ValueError(f'Unsupported {name} layout; expected build 12340')
        self.strings = data[end:]
        self.rows = {}
        for row in struct.iter_unpack(f'<{fields}I', data[20:end]):
            if row[0] in self.rows:
                raise ValueError(f'Duplicate {name} ID: {row[0]}')
            self.rows[row[0]] = row

    def string(self, offset):
        if not 0 <= offset < len(self.strings):
            raise ValueError('DBC string offset out of range')
        end = self.strings.find(b'\0', offset)
        if end < 0:
            raise ValueError('Unterminated DBC string')
        return self.strings[offset:end].decode('utf-8')


def as_float(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]
