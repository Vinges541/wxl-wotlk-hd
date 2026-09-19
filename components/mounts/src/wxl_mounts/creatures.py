"""Display-specific creature adaptation, derived from the verified druid pipeline (GPL-3.0+)."""
import math
import struct
from .model.chunks import read_chunks, texture_records
NAMESPACE = 'WXL/ModernMounts'

def array(data, at, stride):
    if at + 8 > len(data): raise ValueError('Array header out of bounds')
    n, off = struct.unpack_from('<II', data, at)
    if n and (off < 8 or off + n * stride > len(data)): raise ValueError('Array out of bounds')
    return n, off

def bind_textures(model, texture_ids, namespace=NAMESPACE):
    """Bake a display's replaceable creature textures into its private model."""
    chunks = read_chunks(model)
    if chunks[0].tag != 'MD21':
        raise ValueError('Expected MD21 model')
    body = bytearray(chunks[0].payload)
    bindings = []
    for record in texture_records(body):
        kind = record['type']
        if kind == 0:
            if not record['name']:
                raise ValueError('Static texture still has no inline path')
            continue
        if not 11 <= kind <= 13 or len(texture_ids) <= kind - 11 or not texture_ids[kind - 11]:
            raise ValueError(f'Unresolved replaceable material type {kind}')
        file_id = texture_ids[kind - 11]
        name = f'{namespace}/Textures/{file_id}.blp'
        encoded = name.encode('ascii') + b'\0'
        offset = len(body)
        body.extend(encoded)
        struct.pack_into('<I', body, record['recordOffset'], 0)
        struct.pack_into('<II', body, record['recordOffset'] + 8, len(encoded), offset)
        bindings.append(file_id)
    return b'MD21' + struct.pack('<I', len(body)) + body + model[8 + chunks[0].size:], bindings

def select_sections(data, extra_geosets=None):
    """Apply wow.export's creature selection policy to draw AND shadow batches."""
    if len(data) < 64 or data[:4] != b'SKIN':
        raise ValueError('Expected modern SKIN')
    count, start = array(data, 28, 48)
    sections, mapping, removed = [], {}, []
    for i in range(count):
        row = bytearray(data[start + i*48:start + (i+1)*48])
        gid = struct.unpack_from('<H', row)[0]
        keep = (not 0 < gid < 900 or gid in extra_geosets) if extra_geosets is not None else (
            gid % 10 == 0 or gid % 100 == 1)
        if not keep:
            removed.append(gid)
            continue
        mapping[i] = len(sections)
        # All retained sections are intentional defaults, not client-toggleable.
        struct.pack_into('<H', row, 0, 0)
        sections.append(row)
    if not sections:
        raise ValueError('Geoset selection removed the entire model')
    if not removed and all(struct.unpack_from('<H', data, start+i*48)[0] == 0 for i in range(count)):
        return data, []
    result = bytearray(data)
    arrays = [(28, sections)]
    for at, stride in ((36, 24), (48, 12)):
        n, offset = array(data, at, stride)
        records = []
        for i in range(n):
            row = bytearray(data[offset+i*stride:offset+(i+1)*stride])
            old = struct.unpack_from('<H', row, 4)[0]
            if old >= count:
                raise ValueError('Batch section out of bounds')
            if old in mapping:
                struct.pack_into('<H', row, 4, mapping[old])
                records.append(row)
        arrays.append((at, records))
    for at, records in arrays:
        result.extend(b'\0' * (-len(result) % 16))
        offset = len(result)
        result.extend(b''.join(records))
        struct.pack_into('<II', result, at, len(records), offset)
    return bytes(result), removed

def validate_geometry(model, skin):
    chunks = read_chunks(model)
    if chunks[0].tag != 'MD21' or skin[:4] != b'SKIN':
        raise ValueError('Expected MD21/SKIN')
    body = chunks[0].payload
    nv, vertices = array(body, 0x3c, 48)
    textures = texture_records(body)
    if not nv or any(t['type'] != 0 or not t['name'] or not t['name'].startswith(('WXL/ModernMounts/','WXL/DruidForms/')) for t in textures):
        raise ValueError('Model has no geometry or unresolved/outside texture bindings')
    for i in range(nv):
        for at, count in ((0,3),(20,7)):
            if not all(math.isfinite(v) for v in struct.unpack_from('<'+'f'*count, body, vertices+i*48+at)):
                raise ValueError('Non-finite vertex data')
    ni, indices = array(skin,4,2)
    nt, triangles = array(skin,12,2)
    ns, sections = array(skin,28,48)
    if nt % 3 or not ns:
        raise ValueError('Invalid triangle/section count')
    base = struct.unpack_from('<I',skin,44)[0] if any(c.tag == 'LDV1' for c in chunks) else 0
    for i in range(ni):
        if base + struct.unpack_from('<H',skin,indices+i*2)[0] >= nv:
            raise ValueError('Skin vertex outside M2 vertex buffer')
    for i in range(nt):
        if struct.unpack_from('<H',skin,triangles+i*2)[0] >= ni:
            raise ValueError('Triangle outside skin index buffer')
    for i in range(ns):
        at = sections+i*48
        level = struct.unpack_from('<H',skin,at+2)[0]
        start, count = struct.unpack_from('<HH',skin,at+8)
        if start + (level << 16) + count > nt:
            raise ValueError('Section triangle range outside skin')
    for header, stride in ((36,24),(48,12)):
        n, at = array(skin,header,stride)
        for i in range(n):
            if struct.unpack_from('<H',skin,at+i*stride+4)[0] >= ns:
                raise ValueError('Draw/shadow batch references a removed section')
    return {'vertices':nv, 'skinVertices':ni, 'triangles':nt//3, 'sections':ns}

class DBC:
    def __init__(self, data: bytes, fields: int, string_columns=()):
        if len(data) < 20 or data[:4] != b'WDBC':
            raise ValueError('Expected WDBC')
        count, columns, stride, size = struct.unpack_from('<4I', data, 4)
        end = 20 + count * stride
        if (columns != fields or stride != fields * 4 or not 0 < count < 1000000
                or size < 1 or end + size != len(data) or data[end] != 0 or data[-1] != 0):
            raise ValueError('Unsupported DBC layout')
        self.fields = fields
        self.rows = [list(r) for r in struct.iter_unpack('<' + 'I' * fields, data[20:end])]
        self.strings = bytearray(data[end:])
        self.by_id = {r[0]: r for r in self.rows}
        if len(self.by_id) != count:
            raise ValueError('Duplicate DBC IDs')
        for r in self.rows:
            for col in string_columns:
                self.string(r[col])

    def string(self, offset):
        if not 0 <= offset < len(self.strings):
            raise ValueError('String offset out of bounds')
        return self.strings[offset:self.strings.index(0, offset)].decode('utf-8')

    def add_string(self, value):
        if not isinstance(value, str) or '\0' in value:
            raise ValueError('Invalid string')
        offset = len(self.strings)
        self.strings.extend(value.encode('utf-8') + b'\0')
        return offset

    def encode(self):
        return (b'WDBC' + struct.pack('<4I', len(self.rows), self.fields, self.fields * 4, len(self.strings))
                + b''.join(struct.pack('<' + 'I' * self.fields, *r) for r in self.rows) + self.strings)
