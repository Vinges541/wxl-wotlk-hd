"""Resumable processing of the complete named Item texture namespace in explicit MPQs."""
import argparse
from collections import Counter
import importlib.metadata
import json
from pathlib import Path
import shutil
import struct
import time

from .assets import MPQ, EmptyAsset, safe_path, sha, decode_blp, encode_blp, inspect_blp
from .package import no_links, PATCH, validate
from .recipes import RECIPES, restore, deployment
from .client_blp import PALETTE_MODES


def write_json(path, value):
    no_links(path)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n')
    temporary.replace(path)


def scope(name):
    name=safe_path(name)
    if not name.lower().startswith('item/') or not name.lower().endswith('.blp'):
        raise ValueError('Outside Item BLP namespace')
    return 'component' if name.lower().startswith('item/texturecomponents/') else 'object'


def mip_bytes(width,height):
    total=0
    while True:
        total+=width*height*4
        if (width,height)==(1,1):return total+148
        width,height=max(1,width//2),max(1,height//2)


def inventory(args):
    root=no_links(args.workspace);root.mkdir(parents=True,exist_ok=True)
    names={};sources=[]
    for archive in args.archive:
        reader=MPQ(args.stormlib,[archive])
        try:data,_=reader.read('(listfile)')
        finally:reader.close()
        sources.append({'path':str(archive.resolve()),'size':archive.stat().st_size,'listfileSha256':sha(data)})
        for name in data.decode('utf-8',errors='strict').splitlines():
            name=name.replace('\\','/')
            if name.lower().startswith('item/') and name.lower().endswith('.blp'):
                scope(name);names.setdefault(name.casefold(),name)
    reader=MPQ(args.stormlib,args.archive);textures=[];failed=[];empty=[]
    try:
        for i,name in enumerate(sorted(names.values(),key=str.casefold)):
            try:
                data,archive=reader.read(name)
                if len(data)<148 or data[:4]!=b'BLP2':raise ValueError('Unsupported BLP header')
                w,h=struct.unpack_from('<2I',data,12)
                if not 1<=w<=2048 or not 1<=h<=2048 or w&(w-1) or h&(h-1):raise ValueError('Unexpected dimensions')
                kind=scope(name);scale=1 if kind=='component' else 2
                if max(w,h)*scale>2048:raise ValueError('Output exceeds 2048 texture limit')
                digest=sha(data);dest=no_links(root/'original'/digest[:2]/(digest+'.blp'))
                dest.parent.mkdir(parents=True,exist_ok=True)
                if dest.exists():
                    if sha(dest.read_bytes())!=digest:raise ValueError('Corrupted source cache')
                else:dest.write_bytes(data)
                textures.append({'path':name,'kind':kind,'archive':archive,'sha256':digest,'sourceBytes':len(data),
                                 'width':w,'height':h,'encoding':data[8],'alphaDepth':data[9],'scale':scale,'outputBytes':mip_bytes(w*scale,h*scale)})
            except EmptyAsset as error:
                empty.append({'path':name,'archive':error.archive,'sourceBytes':0,'action':'leave-original-empty-entry-in-place'})
            except Exception as error:failed.append({'path':name,'error':str(error)})
            if (i+1)%1000==0:print(f'inventory {i+1}/{len(names)} failures={len(failed)}',flush=True)
    finally:reader.close()
    result={'schema':1,'state':'complete' if not failed else 'failed','namespace':'Item/**/*.blp','retail':False,'archives':sources,'textures':textures,'emptyEntries':empty,'failed':failed}
    write_json(root/'inventory.json',result)
    summary={'textures':len(textures),'uniqueSources':len({r['sha256'] for r in textures}),'failed':len(failed),'emptyEntries':len(empty),
             'sourceBytes':sum(r['sourceBytes'] for r in textures),'outputBytes':sum(r['outputBytes'] for r in textures),
             'kinds':dict(Counter(r['kind'] for r in textures)),'dimensions':dict(Counter(f"{r['width']}x{r['height']}" for r in textures))}
    write_json(root/'inventory-summary.json',summary);print(json.dumps(summary,indent=2))
    if failed:raise ValueError('Inventory incomplete: inspect failed entries')


def profile(args):
    lock=json.loads(args.lock.read_text())
    if lock['variant']!='RealESRNet_x4plus':raise ValueError('Bulk profile requires the reviewed RealESRNet FP32 model')
    implementation=sha(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py'))))
    recipe=getattr(args,'recipe','conservative')
    if recipe not in RECIPES:raise ValueError('Unknown restoration recipe')
    return {'model':lock['variant'],'weightsSha256':lock['weights']['sha256'],'strength':args.strength if recipe=='conservative' else None,
            'implementationSha256':implementation,'versions':{n:importlib.metadata.version(n) for n in ['mlx','mlx-metal','numpy','Pillow','realesrgan-mlx']},
            'recipe':recipe,'paletteMode':getattr(args,'palette_mode','maxcoverage'),'componentScale':2 if recipe=='direct-smooth' else 1,'objectScale':2,
            'alphaPolicy':'nearest-exact','deploymentAlphaPolicy':'source-bilinear-2x-recursive-box-mips' if recipe=='direct-smooth' else 'nearest-exact',
            'encoding':'BLP2-BGRA-full-mips','retail':False}


def cache_key(record,configuration):
    return sha(json.dumps({'input':record['sha256'],'scale':record['scale'],'profile':configuration},sort_keys=True).encode())


def process(args):
    from .mlx_inference import MLXUpscaler
    root=no_links(args.workspace);inventory=json.loads((root/'inventory.json').read_text())
    if inventory['state']!='complete':raise ValueError('Inventory must be complete')
    configuration=profile(args);run_id=sha(json.dumps(configuration,sort_keys=True).encode())
    run=root/'runs'/run_id;run.mkdir(parents=True,exist_ok=True);write_json(run/'profile.json',configuration)
    write_json(root/'progress.json',{'state':'initializing','total':len(inventory['textures']),'done':0,'runId':run_id})
    model=MLXUpscaler(args.weights,configuration['weightsSha256'],configuration['model'])
    recipe=configuration.get('recipe','conservative')
    rows=[dict(r) for r in inventory['textures']]
    if recipe=='direct-smooth':
        for r in rows:
            r['scale']=2;r['outputBytes']=mip_bytes(r['width']*2,r['height']*2)
    start=time.perf_counter();finished=0;reused=0;errors=[]
    records=[]
    for i,record in enumerate(rows):
        key=cache_key(record,configuration);folder=no_links(root/'cache'/key[:2]/key);folder.mkdir(parents=True,exist_ok=True)
        meta=folder/'report.json';dest=folder/'result.blp'
        try:
            if meta.exists() and dest.exists():
                result=json.loads(meta.read_text())
                if result['inputSha256']!=record['sha256'] or sha(dest.read_bytes())!=result['outputSha256']:raise ValueError('Invalid cache hashes')
                reused+=1
            else:
                data=(root/'original'/record['sha256'][:2]/(record['sha256']+'.blp')).read_bytes()
                if sha(data)!=record['sha256']:raise ValueError('Input hash mismatch')
                image=decode_blp(data);after,result=restore(model,image,record['scale'],args.strength,recipe)
                expected=image.getchannel('A').resize(after.size,resample=0)
                if after.getchannel('A').tobytes()!=expected.tobytes():raise ValueError('Alpha changed')
                data=encode_blp(after);info=inspect_blp(data)
                if len(data)!=record['outputBytes']:raise ValueError('Unexpected output budget')
                temporary=dest.with_suffix('.tmp');temporary.write_bytes(data);temporary.replace(dest)
                result.update({'inputSha256':record['sha256'],'outputSha256':sha(data),'cacheKey':key,'blp':info,'alphaExact':True})
                write_json(meta,result);finished+=1
            records.append({**record,'cacheKey':key,'outputSha256':result['outputSha256']})
        except Exception as error:
            errors.append({'path':record['path'],'error':str(error)})
            # A device or input failure must be investigated, never mass-skipped.
            write_json(run/'errors.json',errors)
            write_json(root/'progress.json',{'state':'failed','total':len(rows),'done':i,'last':record['path'],'runId':run_id,'error':str(error)})
            raise
        if (i+1)%100==0 or i+1==len(rows):
            elapsed=time.perf_counter()-start
            progress={'state':'running','total':len(rows),'done':i+1,'computed':finished,'reused':reused,'elapsedSeconds':elapsed,'last':record['path'],'runId':run_id}
            write_json(root/'progress.json',progress)
            print(json.dumps(progress),flush=True)
    write_json(run/'results.json',{'schema':1,'state':'complete','profile':configuration,'records':records})
    write_json(root/'progress.json',{'state':'complete','total':len(rows),'done':len(rows),'computed':finished,'reused':reused,'elapsedSeconds':time.perf_counter()-start,'runId':run_id})


def pack(args):
    root=no_links(args.workspace);progress=json.loads((root/'progress.json').read_text())
    if progress['state']!='complete':raise ValueError('Inference incomplete')
    results=json.loads((root/'runs'/progress['runId']/'results.json').read_text())
    if results['state']!='complete':raise ValueError('Results incomplete')
    inventory=json.loads((root/'inventory.json').read_text())
    if {r['path'] for r in results['records']}!={r['path'] for r in inventory['textures']}:raise ValueError('Coverage mismatch')
    output=no_links(args.output)
    if output.exists():raise FileExistsError(output)
    output.mkdir(parents=True);files={};seen=set()
    for record in results['records']:
        # MPQ lookups ignore case. A single spelling per directory also makes
        # the manifest reproducible on both case-sensitive and insensitive hosts.
        name=safe_path(record['path']).casefold();scope(name)
        if name.casefold() in seen:raise ValueError('Case collision')
        seen.add(name.casefold());key=record['cacheKey'];source=no_links(root/'cache'/key[:2]/key/'result.blp')
        data=source.read_bytes()
        if sha(data)!=record['outputSha256']:raise ValueError('Output hash changed')
        inspect_blp(data)
        original=no_links(root/'original'/record['sha256'][:2]/(record['sha256']+'.blp')).read_bytes()
        if sha(original)!=record['sha256']:raise ValueError('Source hash changed')
        data,_=deployment(data,original,scope(name)=='component',results['profile'].get('recipe','conservative'),palette_mode=results['profile'].get('paletteMode','maxcoverage'))
        dest=output/PATCH/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);files[name]=sha(data)
    write_json(output/'manifest.json',{'schema':1,'patch':PATCH,'files':files,'gameplayVerified':False,'validation':'complete-input-coverage-alpha-mips-hashes-with-visual-sampling','profile':results['profile']})
    validate(output);print(json.dumps({'files':len(files),'bytes':sum((output/PATCH/n).stat().st_size for n in files)}))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    i=sub.add_parser('inventory');i.add_argument('--workspace',type=Path,required=True);i.add_argument('--stormlib',type=Path,required=True);i.add_argument('--archive',type=Path,action='append',required=True);i.set_defaults(run=inventory)
    i=sub.add_parser('process');i.add_argument('--workspace',type=Path,required=True);i.add_argument('--weights',type=Path,required=True);i.add_argument('--lock',type=Path,required=True);i.add_argument('--strength',type=float,default=.35);i.add_argument('--recipe',choices=RECIPES,default='direct-smooth');i.set_defaults(run=process)
    i.add_argument('--palette-mode',choices=PALETTE_MODES,default='maxcoverage')
    i=sub.add_parser('pack');i.add_argument('--workspace',type=Path,required=True);i.add_argument('--output',type=Path,required=True);i.set_defaults(run=pack)
    args=p.parse_args();args.run(args)

if __name__=='__main__':main()
