"""Derive required runtime aliases from the M2 itself, independently of manifests."""
import struct
from .model.chunks import read_chunks,u32_array,afid_records,texture_records


def required_members(model_path,model):
    chunks=read_chunks(model)
    if not chunks or chunks[0].tag!='MD21' or chunks[0].payload[:4]!=b'MD20':raise ValueError('Expected MD21/MD20 model')
    tags={c.tag:c for c in chunks}
    if len(tags)!=len(chunks):raise ValueError('Duplicate model chunk')
    body=chunks[0].payload;count=struct.unpack_from('<I',body,68)[0];stem=model_path[:-3]
    sfid=u32_array(tags['SFID'].payload) if 'SFID' in tags else []
    if not 0<count<=len(sfid) or any(not i for i in sfid):raise ValueError('Missing/invalid skin profile map')
    required={f'{stem}{i:02}.skin' for i in range(count)}
    # This package profile carries every supplied LOD, never silently drops one.
    required.update(f'{stem}_lod{i+1:02}.skin' for i in range(len(sfid)-count))
    anims={}
    for r in afid_records(tags['AFID'].payload) if 'AFID' in tags else []:
        if not r['fileDataId']:continue
        key=(r['animationId'],r['subAnimationId'])
        if key in anims and anims[key]!=r['fileDataId']:raise ValueError('Conflicting animation alias')
        anims[key]=r['fileDataId']
        required.add(f'{stem}{key[0]:04}-{key[1]:02}.anim')
    if 'SKID' in tags:raise ValueError('Split skeleton is outside this package profile')
    for t in texture_records(body):
        if t['type']!=0 or not t['name']:raise ValueError('Unbound material')
        required.add(t['name'])
    return required
