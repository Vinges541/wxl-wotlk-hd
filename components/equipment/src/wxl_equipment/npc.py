"""Restore active, already-installed NPC baked atlases without changing DBCs or models."""
import argparse
from collections import Counter,defaultdict
import importlib.metadata
import json
from pathlib import Path
import struct
import time
from PIL import Image
from .assets import DBC,MPQ,safe_path,sha,decode_blp,encode_blp,inspect_blp
from .batch import write_json,mip_bytes,cache_key
from .package import no_links
from .recipes import RECIPES, restore, deployment

VIRTUAL='Textures/BakedNpcTextures'
TARGET='Data/Patch-ModernRaces-HD.MPQ'
TABLE='DBFilesClient/CreatureDisplayInfoExtra.dbc'


def inventory(args):
    if len(args.locale)!=4 or not args.locale.isascii() or not args.locale.isalpha():raise ValueError('Invalid locale')
    root=no_links(args.workspace);root.mkdir(parents=True,exist_ok=True)
    client=no_links(args.client);table=no_links(client/TARGET/TABLE);locale_table=no_links(client/'Data'/args.locale/f'patch-{args.locale}-ModernRaces.MPQ'/TABLE)
    table_data=table.read_bytes()
    if locale_table.read_bytes()!=table_data:raise ValueError('Active NPC tables disagree')
    dbc=DBC(table_data,21);references=defaultdict(list);spellings={}
    installed_names={}
    for path in no_links(client/TARGET/VIRTUAL).iterdir():
        no_links(path)
        if not path.is_file():continue
        if path.name.casefold() in installed_names:raise ValueError('Case-colliding installed bakes')
        installed_names[path.name.casefold()]=path.name
    for row in dbc.rows.values():
        name=dbc.string(row[20])
        if not name:continue
        if safe_path(name)!=Path(name).name or not name.lower().endswith('.blp'):raise ValueError('Unexpected baked texture name')
        key=name.casefold();spellings.setdefault(key,name)
        references[key].append({'id':row[0],'race':row[1],'sex':row[2],'equipmentDisplayIds':[v for v in row[9:20] if v]})
    reader=MPQ(args.stormlib,args.archive);rows=[];errors=[]
    try:
        for index,key in enumerate(sorted(references)):
            name=spellings[key];virtual=f'{VIRTUAL}/{name}';target=f'{TARGET}/{VIRTUAL}/{installed_names.get(key,key)}'
            installed=no_links(client/target)
            try:
                if installed.is_file():data=installed.read_bytes();source='installed-modern-race-overlay';before=sha(data)
                else:data,source=reader.read(virtual);before=None
                image=decode_blp(data);w,h=image.size
                if max(w,h)>1024 or min(w,h)<1 or w&(w-1) or h&(h-1):raise ValueError('Unsupported baked dimensions')
                if args.protect_face and (w,h)!=(256,256):raise ValueError('Face protection requires the validated 256-square atlas layout')
                digest=sha(data);original=root/'original'/digest[:2]/(digest+'.blp');original.parent.mkdir(parents=True,exist_ok=True)
                if original.exists() and sha(original.read_bytes())!=digest:raise ValueError('Original cache corrupted')
                if not original.exists():original.write_bytes(data)
                rows.append({'path':virtual,'target':target,'sha256':digest,'beforeTargetSha256':before,'source':source,'width':w,'height':h,'scale':2,'outputBytes':mip_bytes(w*2,h*2),'npcReferences':references[key]})
            except Exception as error:errors.append({'path':virtual,'error':str(error),'references':references[key]})
            if (index+1)%1000==0:print('inventory',index+1,'/',len(references),'errors',len(errors),flush=True)
    finally:reader.close()
    tables={str(table.relative_to(client)):sha(table_data),str(locale_table.relative_to(client)):sha(table_data)}
    result={'schema':1,'state':'complete' if not errors else 'failed','client':str(client.resolve()),'locale':args.locale,'tables':tables,'archives':[{'path':str(a.resolve()),'bytes':a.stat().st_size,'mtimeNs':a.stat().st_mtime_ns} for a in args.archive],'textures':rows,'failed':errors,'protectFace':args.protect_face,'newRetailImports':False}
    write_json(root/'inventory.json',result)
    summary={'textures':len(rows),'uniqueSources':len({r['sha256'] for r in rows}),'npcReferences':sum(len(r['npcReferences']) for r in rows),'sources':dict(Counter(r['source'] for r in rows)),'dimensions':dict(Counter(f"{r['width']}x{r['height']}" for r in rows)),'outputBytes':sum(r['outputBytes'] for r in rows),'failed':len(errors),'protectFace':args.protect_face}
    write_json(root/'inventory-summary.json',summary);print(json.dumps(summary,indent=2))
    if errors:raise ValueError('Incomplete source inventory')


def profile(args,inventory):
    lock=json.loads(args.lock.read_text())
    if lock['variant']!='RealESRNet_x4plus':raise ValueError('Reviewed FP32 model required')
    source=Path(__file__).parent
    implementation=sha(b''.join(p.read_bytes() for p in sorted(source.glob('*.py'))))
    recipe=getattr(args,'recipe','conservative')
    if recipe not in RECIPES:raise ValueError('Unknown restoration recipe')
    return {'model':lock['variant'],'weightsSha256':lock['weights']['sha256'],'strength':.35 if recipe=='conservative' else None,'recipe':recipe,'scale':2,'precision':'fp32','protectFace':inventory['protectFace'],'implementationSha256':implementation,'versions':{n:importlib.metadata.version(n) for n in ['mlx','mlx-metal','numpy','Pillow','realesrgan-mlx']},'newRetailImports':False,'encoding':'BLP2-BGRA-full-mips','alphaPolicy':'nearest-exact','deploymentAlphaPolicy':'source-bilinear-2x-recursive-box-mips' if recipe=='direct-smooth' else 'nearest-exact'}


def accept_missing(args):
    """Explicitly retain pre-existing dangling DBC references after another source probe."""
    root=no_links(args.workspace);path=root/'inventory.json';inv=json.loads(path.read_text())
    requested={safe_path(n).casefold() for n in args.name}
    if inv['state']!='failed' or requested!={r['path'].casefold() for r in inv['failed']}:raise ValueError('Explicit names must cover exactly the unresolved entries')
    client=Path(inv['client'])
    for name,digest in inv['tables'].items():
        if sha((client/name).read_bytes())!=digest:raise ValueError('NPC table changed')
    reader=MPQ(args.stormlib,args.archive)
    try:
        for record in inv['failed']:
            name=safe_path(record['path'])
            if not name.startswith(VIRTUAL+'/'):raise ValueError('Outside baked namespace')
            if (client/TARGET/name).exists():raise ValueError('Source now exists in the overlay')
            try:reader.read(name)
            except FileNotFoundError:continue
            raise ValueError('Source exists; it must be processed')
    finally:reader.close()
    inv['missingSources']=inv['failed'];inv['failed']=[];inv['state']='complete'
    inv['missingSourcePolicy']='Explicitly verified pre-existing absent source files; preserve their DBC references unchanged'
    write_json(path,inv);summary=json.loads((root/'inventory-summary.json').read_text());summary['failed']=0;summary['missingSources']=len(inv['missingSources']);write_json(root/'inventory-summary.json',summary)
    print(json.dumps({'state':'complete','textures':len(inv['textures']),'preExistingMissingSources':len(inv['missingSources'])}))


def protect_face(before,after):
    """Keep the documented classic head rectangle at baseline RGB and original alpha."""
    if before.size!=(256,256) or after.size!=(512,512):raise ValueError('Unvalidated face rectangle')
    baseline=before.convert('RGB').resize(after.size,Image.Resampling.LANCZOS).convert('RGBA')
    baseline.putalpha(before.getchannel('A').resize(after.size,Image.Resampling.NEAREST))
    after.paste(baseline.crop((0,320,256,512)),(0,320))
    return after


def process(args):
    from .mlx_inference import MLXUpscaler
    root=no_links(args.workspace);inv=json.loads((root/'inventory.json').read_text())
    if inv['state']!='complete':raise ValueError('Complete inventory required')
    config=profile(args,inv);run_id=sha(json.dumps(config,sort_keys=True).encode());run=root/'runs'/run_id;run.mkdir(parents=True,exist_ok=True);write_json(run/'profile.json',config)
    rows=inv['textures'];records=[];computed=0;reused=0;started=time.perf_counter()
    write_json(root/'progress.json',{'state':'initializing','runId':run_id,'done':0,'total':len(rows)})
    model=MLXUpscaler(args.weights,config['weightsSha256'],config['model'])
    for index,row in enumerate(rows):
        try:
            key=cache_key(row,config);folder=root/'cache'/key[:2]/key;folder.mkdir(parents=True,exist_ok=True);dest=folder/'result.blp';report=folder/'report.json'
            if dest.exists() and report.exists():
                meta=json.loads(report.read_text())
                if sha(dest.read_bytes())!=meta['outputSha256'] or meta['inputSha256']!=row['sha256']:raise ValueError('Cache corrupted')
                reused+=1
            else:
                data=(root/'original'/row['sha256'][:2]/(row['sha256']+'.blp')).read_bytes()
                if sha(data)!=row['sha256']:raise ValueError('Original changed')
                before=decode_blp(data);after,meta=restore(model,before,2,.35,config.get('recipe','conservative'))
                if config['protectFace']:after=protect_face(before,after)
                expected=before.getchannel('A').resize(after.size,Image.Resampling.NEAREST)
                if expected.tobytes()!=after.getchannel('A').tobytes():raise ValueError('Alpha changed')
                data=encode_blp(after)
                if len(data)!=row['outputBytes']:raise ValueError('Unexpected output size')
                temp=dest.with_suffix('.tmp');temp.write_bytes(data);temp.replace(dest)
                meta.update({'inputSha256':row['sha256'],'outputSha256':sha(data),'cacheKey':key,'alphaExact':True,'protectFace':config['protectFace'],'blp':inspect_blp(data)})
                write_json(report,meta);computed+=1
            records.append({**row,'cacheKey':key,'outputSha256':meta['outputSha256']})
        except Exception as error:
            write_json(root/'progress.json',{'state':'failed','runId':run_id,'done':index,'total':len(rows),'path':row['path'],'error':str(error)});raise
        if (index+1)%100==0 or index+1==len(rows):
            progress={'state':'running','runId':run_id,'done':index+1,'total':len(rows),'computed':computed,'reused':reused,'elapsedSeconds':time.perf_counter()-started,'last':row['path']};write_json(root/'progress.json',progress);print(json.dumps(progress),flush=True)
    write_json(run/'results.json',{'state':'complete','records':records,'profile':config})
    write_json(root/'progress.json',{'state':'complete','runId':run_id,'done':len(rows),'total':len(rows),'computed':computed,'reused':reused,'elapsedSeconds':time.perf_counter()-started})


def pack(args):
    root=no_links(args.workspace);progress=json.loads((root/'progress.json').read_text());inv=json.loads((root/'inventory.json').read_text())
    if progress['state']!='complete':raise ValueError('Processing incomplete')
    results=json.loads((root/'runs'/progress['runId']/'results.json').read_text())
    if {r['target']:r['sha256'] for r in results['records']}!={r['target']:r['sha256'] for r in inv['textures']}:raise ValueError('Coverage mismatch')
    output=no_links(args.output)
    if output.exists():raise FileExistsError(output)
    output.mkdir(parents=True);files=[];targets={}
    for r in results['records']:
        target=safe_path(r['target'])
        if not target.startswith(TARGET+'/'+VIRTUAL+'/') or target.count('/')!=4 or not target.lower().endswith('.blp'):raise ValueError('Outside baked texture scope')
        key=r['cacheKey'];data=(root/'cache'/key[:2]/key/'result.blp').read_bytes()
        if sha(data)!=r['outputSha256']:raise ValueError('Result changed')
        original=no_links(root/'original'/r['sha256'][:2]/(r['sha256']+'.blp')).read_bytes()
        if sha(original)!=r['sha256']:raise ValueError('Source changed')
        inspect_blp(data);data,_=deployment(data,original,False,results['profile'].get('recipe','conservative'));dest=output/target;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        files.append({'path':target,'sha256':sha(data),'size':len(data)});targets[target]=r['beforeTargetSha256']
    write_json(output/'release-manifest.json',{'schemaVersion':1,'kind':'wxl-modern-races-assets','locale':inv['locale'],'files':files,'scope':'NPC baked textures only','profile':results['profile'],'gameplayVerified':False})
    write_json(output/'source-guards.json',{'tables':inv['tables'],'archives':inv.get('archives',[]),'targets':targets,'scope':'Refuse client changes since inventory before calling the existing guarded release installer'})
    print(json.dumps({'files':len(files),'bytes':sum(f['size'] for f in files)}))


def check_guards(args):
    """Read-only preflight before the existing release installer backs up and writes."""
    client=no_links(args.client);package=no_links(args.package)
    guards=json.loads((package/'source-guards.json').read_text())
    for name,digest in guards['tables'].items():
        path=no_links(client/safe_path(name))
        if sha(path.read_bytes())!=digest:raise ValueError('Active NPC table changed: '+name)
    for record in guards['archives']:
        info=no_links(Path(record['path'])).stat()
        if info.st_size!=record['bytes'] or info.st_mtime_ns!=record['mtimeNs']:raise ValueError('Source archive changed: '+record['path'])
    for name,digest in guards['targets'].items():
        name=safe_path(name)
        if not name.startswith(TARGET+'/'+VIRTUAL+'/') or name.count('/')!=4:raise ValueError('Outside baked texture scope')
        path=no_links(client/name)
        current=sha(path.read_bytes()) if path.is_file() else None
        if current!=digest or (path.exists() and not path.is_file()):raise ValueError('NPC target changed: '+name)
    print(json.dumps({'state':'passed','targets':len(guards['targets']),'tables':len(guards['tables']),'archives':len(guards['archives'])}))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    i=sub.add_parser('inventory');i.add_argument('--workspace',type=Path,required=True);i.add_argument('--client',type=Path,required=True);i.add_argument('--locale',default='ruRU');i.add_argument('--stormlib',type=Path,required=True);i.add_argument('--archive',type=Path,action='append',required=True);i.add_argument('--protect-face',action='store_true');i.set_defaults(run=inventory)
    s=sub.add_parser('process');s.add_argument('--workspace',type=Path,required=True);s.add_argument('--weights',type=Path,required=True);s.add_argument('--lock',type=Path,required=True);s.add_argument('--recipe',choices=RECIPES,default='direct-smooth');s.set_defaults(run=process)
    b=sub.add_parser('pack');b.add_argument('--workspace',type=Path,required=True);b.add_argument('--output',type=Path,required=True);b.set_defaults(run=pack)
    m=sub.add_parser('accept-missing');m.add_argument('--workspace',type=Path,required=True);m.add_argument('--name',action='append',required=True);m.add_argument('--stormlib',type=Path,required=True);m.add_argument('--archive',type=Path,action='append',required=True);m.set_defaults(run=accept_missing)
    g=sub.add_parser('check-guards');g.add_argument('--client',type=Path,required=True);g.add_argument('--package',type=Path,required=True);g.set_defaults(run=check_guards)
    a=p.parse_args();a.run(a)

if __name__=='__main__':main()
