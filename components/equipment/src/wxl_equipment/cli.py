import argparse
import io
import json
import importlib.metadata
from pathlib import Path
from PIL import Image, ImageDraw
from .package import no_links
from .assets import MPQ, DBC, decode_blp, item_assets, inspect_blp, encode_blp, safe_path, sha


def save_json(path, data):
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data, indent=2)+'\n')
    tmp.replace(path)


def read_asset(args):
    no_links(args.output)
    if args.output.exists():raise FileExistsError(args.output)
    source=MPQ(args.stormlib,args.archive)
    try:data,archive=source.read(args.name)
    finally:source.close()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('xb') as stream:stream.write(data)
    print(json.dumps({'path':args.name,'archive':archive,'sha256':sha(data),'bytes':len(data)}))


def extract(args):
    no_links(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    source=MPQ(args.stormlib,args.archive)
    item_data=args.items.read_bytes(); display_data=args.displays.read_bytes()
    items,displays=DBC(item_data,8),DBC(display_data,25)
    report={'schema':1,'state':'in-progress','clientBuild':12340,'tables':{'Item':sha(item_data),'ItemDisplayInfo':sha(display_data)},
            'archiveOrder':[str(p.resolve()) for p in args.archive],'items':[]}
    for item_id in args.item:
        item=items.rows[item_id]
        category='weapon' if item[1]==2 else ('clothing' if item[2] in (0,1) else 'armor')
        record={'itemId':item_id,'displayId':item[5],'category':category,'inventoryType':item[6],
                'retail':{'status':'unresolved','reason':'No same-build appearance/material/UV evidence yet'},'textures':[]}
        for group in item_assets(item,displays):
            for name in group.pop('candidates'):
                try: data,archive=source.read(name)
                except FileNotFoundError: continue
                path=no_links(args.output/'original'/safe_path(name))
                path.parent.mkdir(parents=True,exist_ok=True)
                if path.exists() and sha(path.read_bytes())!=sha(data):
                    raise ValueError('Cached input changed')
                path.write_bytes(data)
                info={**group,'path':name,'sha256':sha(data),'archive':archive,'blp':inspect_blp(data)}
                if group.get('model'):
                    try:
                        model,model_archive=source.read(group['model'])
                        mp=no_links(args.output/'original'/group['model']); mp.parent.mkdir(parents=True,exist_ok=True); mp.write_bytes(model)
                        info['modelSha256']=sha(model); info['modelArchive']=model_archive
                    except FileNotFoundError:
                        info['modelStatus']='unresolved'
                record['textures'].append(info)
        report['items'].append(record)
        save_json(args.output/'inventory.json',report)
    report['state']='complete'
    save_json(args.output/'inventory.json',report)
    source.close()
    print(json.dumps({'items':len(report['items']),'textures':sum(len(r['textures']) for r in report['items'])}))


def infer(args):
    from .inference import Upscaler
    no_links(args.workspace)
    inventory=json.loads((args.workspace/'inventory.json').read_text())
    if inventory.get('state')!='complete':raise ValueError('Extraction incomplete')
    lock=json.loads(args.lock.read_text())
    if args.device=='mlx-gpu':
        from .mlx_inference import MLXUpscaler
        model=MLXUpscaler(args.weights,lock['weights']['sha256'],lock['variant'])
    else:
        model=Upscaler(args.weights,lock['weights']['sha256'],args.device)
    implementation=sha(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py'))))
    versions={n:importlib.metadata.version(n) for n in (['mlx','numpy','Pillow','realesrgan-mlx'] if args.device=='mlx-gpu' else ['torch','numpy','Pillow'])}
    records=[]
    for item in inventory['items']:
        for texture in item['textures']:
            name=safe_path(texture['path'])
            source=args.workspace/'original'/name
            data=source.read_bytes()
            if sha(data)!=texture['sha256']: raise ValueError('Input hash changed')
            # Compositor resolution not proven: native-size restoration for body layers.
            scale=1 if texture['kind']=='component' else args.scale
            key=sha(json.dumps({'source':sha(data),'weights':model.weights_hash,'scale':scale,'strength':args.strength,
                               'device':args.device,'pipeline':implementation,'versions':versions, 'variant':getattr(model,'variant','general')},sort_keys=True).encode())
            directory=no_links(args.workspace/'cache'/key); directory.mkdir(parents=True,exist_ok=True)
            blp=directory/'result.blp'; meta=directory/'report.json'
            if meta.exists() and blp.exists():
                entry=json.loads(meta.read_text())
                if sha(blp.read_bytes())!=entry['outputSha256']: raise ValueError('Cached output corrupted')
            else:
                before=decode_blp(data)
                after,entry=model.run(before,scale,args.strength)
                encoded=encode_blp(after); inspect_blp(encoded); blp.write_bytes(encoded)
                before.save(directory/'before.png'); after.save(directory/'after.png')
                if hasattr(model,'raw'):
                    model.raw.save(directory/'raw-neural-4x.png')
                    model.neural.save(directory/'raw-neural-output-size.png')
                # Same displayed dimensions, nearest original and ordinary Lanczos as controls.
                images=[before.resize(after.size,Image.Resampling.NEAREST),before.resize(after.size,Image.Resampling.LANCZOS),after]
                factor=min(1,512/after.width); size=(int(after.width*factor),int(after.height*factor))
                panel=Image.new('RGB',(size[0]*3,size[1]+26),(45,45,45)); draw=ImageDraw.Draw(panel)
                for i,(im,label) in enumerate(zip(images,['Original (nearest)','Lanczos control','Local neural detail'])):
                    draw.text((i*size[0]+4,6),label,fill='white'); panel.paste(im.resize(size), (i*size[0],26),im.resize(size).getchannel('A'))
                panel.save(directory/'comparison.png')
                entry.update({'implementationSha256':implementation,'versions':versions,'outputSha256':sha(encoded),'inputSha256':sha(data),'cacheKey':key,'blp':inspect_blp(encoded)})
                save_json(meta,entry)
            records.append({'itemId':item['itemId'],'category':item['category'],'path':name,'cacheKey':key,**entry})
            save_json(args.workspace/'inference.json',{'schema':1,'records':records})
            print(item['itemId'],name,entry['seconds'],flush=True)


def main():
    p=argparse.ArgumentParser(description='Offline equipment texture pipeline; no cloud inference')
    sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('read-asset');r.add_argument('--stormlib',type=Path,required=True);r.add_argument('--archive',type=Path,action='append',required=True);r.add_argument('--name',required=True);r.add_argument('--output',type=Path,required=True);r.set_defaults(run=read_asset)
    e=sub.add_parser('extract'); e.add_argument('--stormlib',type=Path,required=True);e.add_argument('--archive',type=Path,action='append',required=True)
    e.add_argument('--items',type=Path,required=True);e.add_argument('--displays',type=Path,required=True);e.add_argument('--item',type=int,action='append',required=True)
    e.add_argument('--output',type=Path,required=True);e.set_defaults(run=extract)
    i=sub.add_parser('infer');i.add_argument('--workspace',type=Path,required=True);i.add_argument('--weights',type=Path,required=True);i.add_argument('--lock',type=Path,required=True)
    i.add_argument('--device',choices=['mlx-gpu','mps','cpu'],default='mlx-gpu');i.add_argument('--scale',type=int,choices=[1,2,4],default=2);i.add_argument('--strength',type=float,default=.35);i.set_defaults(run=infer)
    args=p.parse_args();args.run(args)

if __name__=='__main__': main()
