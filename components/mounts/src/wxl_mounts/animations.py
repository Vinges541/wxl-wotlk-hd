"""Prepare missing native sequence hashes without changing the shared runtime.

The build-12340 lookup uses id % count followed by cumulative square probes;
it is not an array indexed by animation ID. The runtime remap profile comes from
WarcraftXL M2Fixups.cpp. Preparation only repairs remaps that the native lookup
would otherwise fail to find; affected models must keep all remapped keys inline.
"""
import struct
from .creatures import array
from .model.chunks import read_chunks, afid_records

REMAPS = {564:37,548:41,556:42,552:43,554:44,562:45,572:39,574:187}


def buckets(animation_id,count):
    bucket=animation_id % count
    for probe in range(1,count+1):
        yield bucket
        bucket=(bucket+probe*probe) % count


def lookup_slot(ids,lookup,animation_id):
    if not lookup:return next((i for i,value in enumerate(ids) if value==animation_id),None)
    for bucket in buckets(animation_id,len(lookup)):
        slot=lookup[bucket]
        if slot==-1:return None
        if not 0<=slot<len(ids):raise ValueError('Sequence hash points outside sequence array')
        if ids[slot]==animation_id:return slot
    return None


def runtime_state(ids,lookup):
    """Model the pinned runtime's existing remap/lookup mutations literally."""
    ids=list(ids);lookup=list(lookup)
    for slot,old in enumerate(ids):
        if old not in REMAPS:continue
        target=REMAPS[old]
        prior=next((i for i,value in enumerate(ids) if value==target),-1)
        if target<len(lookup) and lookup[target]==prior:lookup[target]=slot
        else:
            at=next((i for i,value in enumerate(lookup) if value==prior),None)
            if at is not None:lookup[at]=slot
        ids[slot]=target
    return ids,lookup


def sequence_tables(model):
    chunks=read_chunks(model)
    if not chunks or chunks[0].tag!='MD21':raise ValueError('Expected MD21 model')
    body=chunks[0].payload;n,offset=array(body,28,64);count,start=array(body,36,2)
    ids=[struct.unpack_from('<H',body,offset+i*64)[0] for i in range(n)]
    lookup=list(struct.unpack_from('<'+'h'*count,body,start))
    return chunks,body,offset,ids,lookup


def unreachable_runtime_ids(model):
    _,_,_,ids,lookup=sequence_tables(model)
    ids,lookup=runtime_state(ids,lookup)
    return sorted(i for i in set(ids) if i<=505 and lookup_slot(ids,lookup,i) is None)


def repair_missing_remaps(model):
    chunks,body,offset,ids,lookup=sequence_tables(model)
    fixed_ids,fixed_lookup=runtime_state(ids,lookup)
    missing=set(unreachable_runtime_ids(model))
    if not missing:return model,{}
    if missing-set(REMAPS.values()) or missing&set(ids):
        raise ValueError('Unreachable native animation outside supported remaps')
    affected={old:new for old,new in REMAPS.items() if new in missing and old in ids}
    if set(affected.values())!=missing:raise ValueError('No source for missing native animation')
    # Prepare only the otherwise unreachable IDs. Rehash with the native probing
    # rule and preserve the original preferred slots of every other source ID.
    # A count=0 linear table would instead select an earlier swimming variant of
    # animation 41, losing the runtime's preferred flying variant in these models.
    external={r['animationId'] for c in chunks if c.tag=='AFID'
              for r in afid_records(c.payload) if r['fileDataId']}
    if external&(affected.keys()|missing):raise ValueError('External animation remap needs a reviewed alias adapter')
    result=bytearray(body);changes=[]
    for slot,old in enumerate(ids):
        if old not in affected:continue
        at=offset+slot*64;flags=struct.unpack_from('<I',body,at+12)[0]
        if (not flags&0x20 or flags&0x40 or struct.unpack_from('<H',body,at+2)[0]
                or struct.unpack_from('<h',body,at+60)[0]!=-1 or ids.count(old)!=1):
            raise ValueError('Only single inline non-alias sequence remaps are supported')
        struct.pack_into('<H',result,at,affected[old])
        changes.append({'sequenceSlot':slot,'fromId':old,'toId':affected[old]})
    prepared_ids=[affected.get(i,i) for i in ids]
    preferred={affected.get(aid,aid):lookup_slot(ids,lookup,aid) for aid in set(ids)}
    if any(slot is None for slot in preferred.values()):raise ValueError('Original sequence hash is incomplete')
    rebuilt=[-1]*len(lookup)
    for aid,slot in sorted(preferred.items()):
        for bucket in buckets(aid,len(rebuilt)):
            if rebuilt[bucket]==-1:rebuilt[bucket]=slot;break
        else:raise ValueError('Cannot rebuild native sequence hash')
    if any(lookup_slot(prepared_ids,rebuilt,aid)!=slot for aid,slot in preferred.items()):
        raise ValueError('Rebuilt sequence hash lost its selected variant')
    after_ids,after_lookup=runtime_state(prepared_ids,rebuilt)
    preserved=0
    for aid in set(fixed_ids):
        if aid>505:continue
        before=lookup_slot(fixed_ids,fixed_lookup,aid)
        after=lookup_slot(after_ids,after_lookup,aid)
        if after is None or (before is not None and after!=before):
            raise ValueError('Adaptation changes an existing native sequence choice')
        preserved+=before is not None
    result.extend(b'\0'*(-len(result)%16));start=len(result)
    result.extend(struct.pack('<'+'h'*len(rebuilt),*rebuilt));struct.pack_into('<II',result,36,len(rebuilt),start)
    output=bytes(b'MD21'+struct.pack('<I',len(result))+result+model[8+chunks[0].size:])
    if unreachable_runtime_ids(output):raise ValueError('Native runtime cannot find an adapted sequence')
    return output,{'strategy':'prepare-missing-native-remaps-and-rehash','unreachableBefore':sorted(missing),
                   'preservedNativeSequenceChoices':preserved,'remaps':changes}
