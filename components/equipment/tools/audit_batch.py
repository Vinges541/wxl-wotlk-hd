"""Validate every bulk output and render deterministic local visual-review samples."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import struct
import time
import numpy as np
from PIL import Image, ImageDraw
from wxl_equipment.assets import decode_blp, inspect_blp, sha
from wxl_equipment.package import no_links


def verify_mips(data, width, height):
    offsets=struct.unpack_from('<16I',data,20);sizes=struct.unpack_from('<16I',data,84)
    cursor=148;levels=1+int(math.log2(max(width,height)))
    previous=None
    for level in range(16):
        if level>=levels:
            if offsets[level] or sizes[level]:raise ValueError('Unexpected extra mip')
            continue
        w,h=max(1,width>>level),max(1,height>>level)
        if offsets[level]!=cursor or sizes[level]!=w*h*4:raise ValueError('Mip dimensions or offset mismatch')
        current=Image.frombytes('RGBA',(w,h),data[cursor:cursor+sizes[level]],'raw','BGRA')
        if previous is not None:
            expected=previous.resize((w,h),Image.Resampling.BOX)
            if current.tobytes()!=expected.tobytes():raise ValueError('Mip pixels do not match the declared filter')
        previous=current;cursor+=sizes[level]
    if cursor!=len(data):raise ValueError('Unexpected output payload')


def group(record):
    parts=record['path'].split('/')
    return '/'.join(parts[1:3]) if len(parts)>3 else 'Other'


def checker(size):
    image=Image.new('RGB',size);draw=ImageDraw.Draw(image)
    for y in range(0,size[1],16):
        for x in range(0,size[0],16):
            value=52 if (x//16+y//16)%2 else 74
            draw.rectangle((x,y,x+15,y+15),fill=(value,)*3)
    return image


def render(original, after, label, output, strength=.35):
    # Same source-space crop and same view scale for all three columns.
    box=((original.width-min(128,original.width))//2,(original.height-min(128,original.height))//2)
    box=(*box,box[0]+min(128,original.width),box[1]+min(128,original.height))
    scale=after.width//original.width
    baseline=original.convert('RGB').resize(after.size,Image.Resampling.LANCZOS).convert('RGBA')
    baseline.putalpha(original.getchannel('A').resize(after.size,Image.Resampling.NEAREST))
    panes=[original.crop(box),baseline.crop(tuple(v*scale for v in box)),after.crop(tuple(v*scale for v in box))]
    size=((box[2]-box[0])*4,(box[3]-box[1])*4)
    panel=Image.new('RGB',(3*size[0],size[1]+65),(25,25,25));draw=ImageDraw.Draw(panel)
    draw.text((8,7),label,fill='white')
    label='RealESRNet FP32 / direct RGB' if strength is None else f'RealESRNet FP32 / detail {strength:g}'
    for index,(title,pane) in enumerate(zip(['Original / nearest','Lanczos control',label],panes)):
        draw.text((index*size[0]+8,29),title,fill='white')
        pane=pane.resize(size,Image.Resampling.NEAREST);background=checker(size);background.paste(pane.convert('RGB'),mask=pane.getchannel('A'))
        panel.paste(background,(index*size[0],60))
    panel.save(output)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=no_links(a.workspace);out=no_links(a.output)
    if out.exists():raise FileExistsError(out)
    progress=json.loads((root/'progress.json').read_text())
    if progress['state']!='complete':raise ValueError('Processing has not completed')
    results=json.loads((root/'runs'/progress['runId']/'results.json').read_text());inventory=json.loads((root/'inventory.json').read_text())
    rows=results['records']
    if {r['path']:r['sha256'] for r in rows}!={r['path']:r['sha256'] for r in inventory['textures']}:raise ValueError('Inventory coverage mismatch')
    out.mkdir(parents=True);samples=defaultdict(list)
    for r in rows:samples[group(r)].append(r)
    selected=set()
    for items in samples.values():
        ordered=sorted(items,key=lambda r:r['sha256'])
        selected.update(r['path'] for r in ordered[:3])
        selected.add(max(items,key=lambda r:r['width']*r['height'])['path'])
        selected.add(min(items,key=lambda r:r['width']*r['height'])['path'])
    seen={};maximum=0;peak=0;seconds=0;gallery=[];start=time.perf_counter()
    for index,r in enumerate(rows):
        folder=no_links(root/'cache'/r['cacheKey'][:2]/r['cacheKey']);data=(folder/'result.blp').read_bytes();meta=json.loads((folder/'report.json').read_text())
        if sha(data)!=r['outputSha256'] or meta['outputSha256']!=r['outputSha256']:raise ValueError('Output hash mismatch')
        original_data=(root/'original'/r['sha256'][:2]/(r['sha256']+'.blp')).read_bytes()
        if sha(original_data)!=r['sha256']:raise ValueError('Source hash mismatch')
        before=decode_blp(original_data);after=decode_blp(data);info=inspect_blp(data)
        if after.size!=(before.width*r['scale'],before.height*r['scale']):raise ValueError('Scale mismatch')
        if info['encoding']!=3 or info['alphaDepth']!=8:raise ValueError('Output format mismatch')
        if before.getchannel('A').resize(after.size,Image.Resampling.NEAREST).tobytes()!=after.getchannel('A').tobytes():raise ValueError('Base alpha changed')
        if r['cacheKey'] not in seen:
            verify_mips(data,*after.size)
            baseline=before.convert('RGB').resize(after.size,Image.Resampling.LANCZOS)
            difference=np.abs(np.asarray(after.convert('RGB'),dtype=np.int16)-np.asarray(baseline,dtype=np.int16));delta=int(difference.max())
            direct=results['profile'].get('recipe')=='direct-smooth'
            if not direct and delta>math.ceil(24*results['profile']['strength']):raise ValueError('RGB correction bound exceeded')
            if direct and (meta.get('recipe')!='direct-smooth' or meta.get('outputMode')!='direct-neural-rgb'):raise ValueError('Direct recipe metadata mismatch')
            if meta['device']!='mlx-gpu' or meta['precision']!='fp32' or meta['tile']!=0:raise ValueError('Inference profile mismatch')
            if meta['weightsSha256']!=results['profile']['weightsSha256']:raise ValueError('Model mismatch')
            seen[r['cacheKey']]=delta;maximum=max(maximum,delta);peak=max(peak,meta['peakMemoryBytes']);seconds+=meta['seconds']
        if r['path'] in selected:
            filename=f"sample-{len(gallery)+1:03d}.png";render(before,after,r['path'],out/filename,results['profile']['strength'])
            gallery.append({'path':r['path'],'group':group(r),'file':filename,'inputSize':list(before.size),'outputSize':list(after.size)})
        if (index+1)%1000==0:print('audited',index+1,'/',len(rows),flush=True)
    report={'state':'passed','runId':progress['runId'],'textures':len(rows),'uniqueOutputs':len(seen),'groups':dict(Counter(group(r) for r in rows)),
            'allSourceAndOutputHashesMatch':True,'allBaseAlphaExact':True,'allMipsPixelExact':True,'allOutputsFp32Metal':True,'maxRgbDeltaFromControl':maximum,
            'peakMlxMemoryBytes':peak,'summedInferenceSeconds':seconds,'auditSeconds':time.perf_counter()-start,'emptySourceEntriesPreserved':inventory['emptyEntries'],
            'samples':gallery,'visualReview':'samples require inspection; metrics are not ground-truth quality scores','gameplayVerified':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['samples','emptySourceEntriesPreserved','groups']},indent=2))

if __name__=='__main__':main()
