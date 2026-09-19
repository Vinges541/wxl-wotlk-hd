"""Scale both Tauren world models from the immutable build-12340 baseline."""
import math,struct
from .druids import DBC
FACTOR=0.75
PATHS={f'character/tauren/{sex}/tauren{sex}.m2' for sex in ('male','female')}
def canonical(path):
    path=path.replace('\\','/').lower()
    return path[:-4]+'.m2' if path.endswith('.mdx') else path

def apply_world_scale(original, composed):
    base=DBC(original,28,(2,));out=DBC(composed,28,(2,))
    targets=[r for r in base.rows if canonical(base.string(r[2])) in PATHS]
    if {canonical(base.string(r[2])) for r in targets} != PATHS:
        raise ValueError('Original table must contain male and female Tauren models')
    for row in targets:
        value=struct.unpack('<f',struct.pack('<I',row[4]))[0]
        if not math.isfinite(value) or value<=0:raise ValueError('Invalid original Tauren scale')
        current=out.by_id.get(row[0])
        if current is None or current[:4]+current[5:] != row[:4]+row[5:]:
            raise ValueError('Another component changed a Tauren model row')
        if out.string(current[2]) != base.string(row[2]):raise ValueError('Tauren path changed')
        scaled=struct.unpack('<I',struct.pack('<f',value*FACTOR))[0]
        if current[4] not in (row[4],scaled):raise ValueError('Conflicting Tauren scale')
        current[4]=scaled
    return out.encode()
