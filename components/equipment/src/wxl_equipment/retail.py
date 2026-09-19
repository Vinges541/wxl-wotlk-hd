"""Evidence-based Retail comparison: same ItemID is a lookup key, never UV proof."""
import argparse,json,struct,math
from pathlib import Path
import numpy as np
from .assets import decode_blp,inspect_blp,sha,SECTIONS


def model_evidence(data):
    if data[:4]==b'MD21':
        length=struct.unpack_from('<I',data,4)[0]
        if length+8>len(data):raise ValueError('Truncated MD21')
        data=data[8:8+length]
    if data[:4]!=b'MD20' or len(data)<0x88:raise ValueError('Expected M2')
    count,offset=struct.unpack_from('<2I',data,0x3c)
    if count>1000000 or offset+count*48>len(data):raise ValueError('Invalid vertices')
    vertices=[struct.unpack_from('<2f',data,offset+i*48+32) for i in range(count)]
    if any(not math.isfinite(v) for uv in vertices for v in uv):raise ValueError('Invalid UV')
    textures,at=struct.unpack_from('<2I',data,0x50)
    if at+textures*16>len(data):raise ValueError('Invalid materials')
    types=[struct.unpack_from('<2I',data,at+i*16) for i in range(textures)]
    return {'vertices':count,'uvSha256':sha(b''.join(struct.pack('<2f',*uv) for uv in vertices)),
            'textureTypesAndFlags':types,'uvMin':list(map(min,zip(*vertices))) if vertices else [],'uvMax':list(map(max,zip(*vertices))) if vertices else []}


def compare(workspace,retail):
    inventory=json.loads((workspace/'inventory.json').read_text())
    mapping=json.loads((retail/'mapping.json').read_text())
    build=json.loads((retail/'build.json').read_text())
    if build['BuildConfig']!=mapping['BuildConfig']:raise ValueError('Mixed Retail builds')
    result={'BuildConfig':build['BuildConfig'],'items':[]}
    for item in inventory['items']:
        plans=[r for r in mapping['items'] if r['itemId']==item['itemId']]
        entry={'itemId':item['itemId'],'category':item['category'],'legacyDisplayId':item['displayId'],'textures':[],'models':[]}
        for original in item['textures']:
            data=(workspace/'original'/original['path']).read_bytes()
            if sha(data)!=original['sha256']:raise ValueError('Changed original')
            image=decode_blp(data);candidates=[]
            for plan in plans:
                for binding in plan['textureBindings']:
                    if original['kind']=='component' and binding['binding'].get('ComponentSection')!=SECTIONS.index(original['section']):continue
                    for f in binding['files']:
                        path=retail/(str(f['FileDataID'])+'.bin')
                        if not path.exists():continue
                        raw=path.read_bytes()
                        other=decode_blp(raw)
                        equal=other.size==image.size and other.tobytes()==image.tobytes()
                        c={'fileDataId':f['FileDataID'],'usageType':f['UsageType'],'sha256':sha(raw),'blp':inspect_blp(raw),'byteIdentical':raw==data,'pixelsIdentical':equal}
                        if other.size==image.size:
                            c['rgbaMeanAbsoluteDifference']=float(np.abs(np.asarray(other,dtype=np.int16)-np.asarray(image,dtype=np.int16)).mean())
                        candidates.append(c)
                if original.get('model'):
                    old=(workspace/'original'/original['model']).read_bytes();old_e=model_evidence(old)
                    for m in plan['models']:
                        new=(retail/(str(m['FileDataID'])+'.bin')).read_bytes();new_e=model_evidence(new)
                        entry['models'].append({'legacy':original['model'],'retailFileDataId':m['FileDataID'],'legacyEvidence':old_e,'retailEvidence':new_e,'sameUV':old_e['uvSha256']==new_e['uvSha256'],'sameTextureTypesAndFlags':old_e['textureTypesAndFlags']==new_e['textureTypesAndFlags']})
            status='unchanged-retail-no-upgrade' if any(c['pixelsIdentical'] for c in candidates) else 'unresolved-different-or-unavailable'
            entry['textures'].append({'path':original['path'],'status':status,'candidates':candidates})
        entry['status']='unchanged-retail-no-upgrade' if entry['textures'] and all(x['status']=='unchanged-retail-no-upgrade' for x in entry['textures']) else 'unresolved'
        result['items'].append(entry)
    (workspace/'retail-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps([{'itemId':i['itemId'],'status':i['status']} for i in result['items']],indent=2))


def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--retail',type=Path,required=True);a=p.parse_args();compare(a.workspace,a.retail)
if __name__=='__main__':main()
