"""Independently audit all NPC outputs and render full-atlas/face review samples."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import time
import numpy as np
from PIL import Image, ImageDraw
from audit_batch import checker, verify_mips
from wxl_equipment.assets import decode_blp, inspect_blp, sha
from wxl_equipment.batch import cache_key
from wxl_equipment.package import no_links


def control(before, size):
    result=before.convert('RGB').resize(size,Image.Resampling.LANCZOS).convert('RGBA')
    result.putalpha(before.getchannel('A').resize(size,Image.Resampling.NEAREST))
    return result


def render(before, after, label, output, direct=False):
    panes=[before.resize(after.size,Image.Resampling.NEAREST),control(before,after.size),after]
    panel=Image.new('RGB',(1536,980),(25,25,25));draw=ImageDraw.Draw(panel)
    draw.text((8,8),label,fill='white')
    title='RealESRNet FP32 / direct RGB' if direct else 'RealESRNet FP32 / detail 0.35'
    for i,(title,pane) in enumerate(zip(['Original / nearest','Lanczos control',title],panes)):
        draw.text((i*512+8,30),title,fill='white')
        atlas=pane.resize((512,512),Image.Resampling.NEAREST)
        bg=checker(atlas.size);bg.paste(atlas.convert('RGB'),mask=atlas.getchannel('A'));panel.paste(bg,(i*512,60))
        # Classic head rectangle, shown separately so face changes cannot hide in a center crop.
        face=atlas.crop((0,320,256,512)).resize((512,384),Image.Resampling.NEAREST)
        bg=checker(face.size);bg.paste(face.convert('RGB'),mask=face.getchannel('A'));panel.paste(bg,(i*512,596))
    draw.text((8,578),'Classic head region / 2x close-up',fill='white');panel.save(output)


def validate_record(root, row, profile):
    key=row['cacheKey']
    if cache_key(row,profile)!=key:raise ValueError('Cache identity mismatch')
    folder=no_links(root/'cache'/key[:2]/key)
    data=(folder/'result.blp').read_bytes();meta=json.loads((folder/'report.json').read_text())
    original=(root/'original'/row['sha256'][:2]/(row['sha256']+'.blp')).read_bytes()
    if sha(original)!=row['sha256'] or meta['inputSha256']!=row['sha256']:raise ValueError('Source hash mismatch')
    if sha(data)!=row['outputSha256'] or meta['outputSha256']!=row['outputSha256']:raise ValueError('Output hash mismatch')
    before=decode_blp(original);after=decode_blp(data);info=inspect_blp(data)
    if before.size!=(row['width'],row['height']) or after.size!=(before.width*2,before.height*2):raise ValueError('Dimension mismatch')
    if len(data)!=row['outputBytes'] or info['encoding']!=3 or info['alphaDepth']!=8:raise ValueError('BLP format mismatch')
    if before.getchannel('A').resize(after.size,Image.Resampling.NEAREST).tobytes()!=after.getchannel('A').tobytes():raise ValueError('Base alpha changed')
    verify_mips(data,*after.size)
    baseline=control(before,after.size)
    delta=int(np.abs(np.asarray(after.convert('RGB'),dtype=np.int16)-np.asarray(baseline.convert('RGB'),dtype=np.int16)).max())
    direct=profile.get('recipe')=='direct-smooth'
    if not direct and delta>math.ceil(24*profile['strength']):raise ValueError('RGB correction bound exceeded')
    if direct and (meta.get('recipe')!='direct-smooth' or meta.get('outputMode')!='direct-neural-rgb'):raise ValueError('Direct recipe metadata mismatch')
    if profile['protectFace']:
        if before.size!=(256,256):raise ValueError('Unknown face layout')
        box=(0,320,256,512)
        if after.crop(box).tobytes()!=baseline.crop(box).tobytes():raise ValueError('Protected face changed')
    if any(meta[k]!=v for k,v in {'device':'mlx-gpu','precision':'fp32','tile':0,'scale':2,'strength':None if direct else .35,'protectFace':profile['protectFace'],'weightsSha256':profile['weightsSha256']}.items()):raise ValueError('Inference profile mismatch')
    return before,after,meta,delta


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=no_links(a.workspace);out=no_links(a.output)
    if out.exists():raise FileExistsError(out)
    progress=json.loads((root/'progress.json').read_text());inv=json.loads((root/'inventory.json').read_text())
    if progress['state']!='complete' or inv['state']!='complete':raise ValueError('Incomplete run')
    results=json.loads((root/'runs'/progress['runId']/'results.json').read_text());rows=results['records'];profile=results['profile']
    if sha(json.dumps(profile,sort_keys=True).encode())!=progress['runId']:raise ValueError('Run profile mismatch')
    coverage=lambda values:{r['target']:(r['sha256'],r['beforeTargetSha256']) for r in values}
    if len(rows)!=len(inv['textures']) or len(coverage(rows))!=len(rows) or coverage(rows)!=coverage(inv['textures']):raise ValueError('Coverage mismatch')
    direct=profile.get('recipe')=='direct-smooth'
    if profile['model']!='RealESRNet_x4plus' or profile['strength']!=(None if direct else .35) or profile['precision']!='fp32' or profile['protectFace']!=inv['protectFace']:raise ValueError('Unreviewed profile')
    groups=defaultdict(list)
    for row in rows:
        for ref in row['npcReferences']:groups[(ref['race'],ref['sex'])].append(row)
    chosen=set()
    for items in groups.values():
        equipped=[r for r in items if any(ref['equipmentDisplayIds'] for ref in r['npcReferences'])]
        chosen.add(min(equipped or items,key=lambda r:(r['sha256'],r['path']))['path'])
    for row in rows:
        if any(ref['id'] in [23,30,43,346,1518] for ref in row['npcReferences']):chosen.add(row['path'])
    out.mkdir(parents=True);seen={};gallery=[];maximum=0;peak=0;seconds=0;started=time.perf_counter()
    for index,row in enumerate(rows):
        # Recheck per-path records even when payload content is shared.
        before,after,meta,delta=validate_record(root,row,profile)
        if row['cacheKey'] not in seen:
            seen[row['cacheKey']]=row['outputSha256'];maximum=max(maximum,delta);peak=max(peak,meta['peakMemoryBytes']);seconds+=meta['seconds']
        elif seen[row['cacheKey']]!=row['outputSha256']:raise ValueError('Shared output disagrees')
        if row['path'] in chosen:
            name=f'sample-{len(gallery)+1:03d}.png';render(before,after,row['path'],out/name,direct)
            gallery.append({'file':name,'path':row['path'],'references':row['npcReferences'],'inputSize':list(before.size),'outputSize':list(after.size)})
        if (index+1)%1000==0:print('audited',index+1,'/',len(rows),flush=True)
    report={'state':'passed','runId':progress['runId'],'textures':len(rows),'uniqueOutputs':len(seen),'npcReferences':sum(len(r['npcReferences']) for r in rows),'raceSexGroups':len(groups),
            'allSourceAndOutputHashesMatch':True,'allBaseAlphaExact':True,'allMipsPixelExact':True,'allOutputsFp32Metal':True,'protectFace':profile['protectFace'],
            'maxRgbDeltaFromControl':maximum,'peakMlxMemoryBytes':peak,'summedInferenceSeconds':seconds,'auditSeconds':time.perf_counter()-started,'preExistingMissingSources':inv.get('missingSources',[]),
            'samples':gallery,'visualReview':'Full atlases and head regions require inspection; metrics do not prove visual quality','gameplayVerified':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['samples','preExistingMissingSources']},indent=2))


if __name__=='__main__':main()
