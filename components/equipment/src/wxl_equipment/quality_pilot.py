"""Compare direct local RealESRNet output with an installed, bounded-detail package."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image, ImageDraw
from .assets import decode_blp, encode_blp, safe_path, sha
from .batch import write_json
from .client_blp import to_runtime
from .package import PATCH, no_links
from .recipes import direct_rgba


def difference(reference, image):
    expected=reference.resize(image.size, Image.Resampling.LANCZOS)
    delta=np.asarray(image.convert('RGB'),dtype=np.int32)-np.asarray(expected.convert('RGB'),dtype=np.int32)
    visible=np.asarray(image.getchannel('A'))>0
    return {'visibleRgbRmse':float(np.sqrt(np.square(delta[visible]).mean())) if visible.any() else 0,
            'visibleRgbMax':int(np.abs(delta[visible]).max(initial=0))}


def panel(images, labels, path, sampling=Image.Resampling.BILINEAR):
    width=512; height=round(width*images[0].height/images[0].width)
    canvas=Image.new('RGB',(width*len(images),height+70),(32,32,32));draw=ImageDraw.Draw(canvas)
    for col,(image,label) in enumerate(zip(images,labels)):
        # Filtered viewing and exact-pixel inspection answer different questions.
        # Neither preview changes the encoded asset or simulates the full renderer.
        display=image.resize((width,height),sampling)
        bg=Image.new('RGBA',display.size,(78,78,78,255));bg.alpha_composite(display)
        canvas.paste(bg.convert('RGB'),(col*width,70));draw.text((col*width+8,10),label,fill='white')
        draw.text((col*width+8,28),f'{image.width} x {image.height}',fill=(180,180,180))
        note='Bilinear preview; asset unchanged' if sampling==Image.Resampling.BILINEAR else 'Nearest preview: magnified pixel grid'
        draw.text((col*width+8,46),note,fill=(180,180,180))
    canvas.save(path)


def build(args):
    from .mlx_inference import MLXUpscaler
    workspace=no_links(args.workspace);output=no_links(args.output);client=no_links(args.client)
    if output.exists():raise FileExistsError(output)
    inventory_raw=no_links(workspace/'inventory.json').read_bytes();inventory=json.loads(inventory_raw)
    if inventory.get('state')!='complete':raise ValueError('Source inventory incomplete')
    rows=[(item['itemId'],r) for item in inventory['items'] for r in item['textures']]
    if not 1<=len(rows)<=128:raise ValueError('Pilot must contain 1..128 textures')
    lock=json.loads(no_links(args.lock).read_text())
    if lock['variant']!='RealESRNet_x4plus':raise ValueError('This pilot requires FP32 RealESRNet')
    model=MLXUpscaler(no_links(args.weights),lock['weights']['sha256'],lock['variant'])
    output.mkdir(parents=True);records=[];files=[];seen=set();started=time.time()
    for index,(item_id,row) in enumerate(rows):
        name=safe_path(row['path']).lower()
        if name in seen:continue
        if not name.startswith('item/') or not name.endswith('.blp'):raise ValueError('Outside Item namespace')
        seen.add(name);component=name.startswith('item/texturecomponents/')
        source_data=no_links(workspace/'original'/row['path']).read_bytes()
        if sha(source_data)!=row['sha256']:raise ValueError('Original changed')
        current_data=no_links(client/'Data'/PATCH/name).read_bytes()
        source=decode_blp(source_data);current=decode_blp(current_data)
        folder=output/'comparisons'/f'{index:03d}-{item_id}';folder.mkdir(parents=True)
        _,inference=model.run(source,1 if component else 2,.35)
        source.save(folder/'original.png');current.save(folder/'installed.png');model.raw.save(folder/'direct-4x-rgb.png')
        variants={};images={}
        for scale in (1,2,4):
            if max(source.size)*scale>2048:continue
            result=direct_rgba(source,model.raw,scale)
            encoded,encoding=to_runtime(encode_blp(result),component)
            decoded=decode_blp(encoded)
            expected_alpha=source.getchannel('A').resize(result.size,Image.Resampling.NEAREST)
            if decoded.getchannel('A').tobytes()!=expected_alpha.tobytes():raise ValueError('Pilot alpha mismatch')
            (folder/f'direct-{scale}x.blp').write_bytes(encoded);decoded.save(folder/f'direct-{scale}x.png')
            images[scale]=decoded
            variants[str(scale)]={'sha256':sha(encoded),'bytes':len(encoded),'encoding':encoding,
                                  'differenceFromSourceLanczos':difference(source,decoded)}
            if scale==2:
                dest=output/'package'/PATCH/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(encoded)
                files.append({'path':name,'beforeSha256':sha(current_data),'sha256':sha(encoded),'bytes':len(encoded),'sourceSha256':row['sha256'],'itemId':item_id})
        shown=[source,current,images[1],images[2]] if component else [source,current,images[2],images[4]]
        labels=['Original','Installed: bounded detail','Direct RealESRNet: native','Direct RealESRNet: 2x'] if component else ['Original','Installed: bounded detail 2x','Direct RealESRNet: 2x','Direct RealESRNet: 4x']
        panel(shown,labels,folder/'comparison.png')
        panel(shown,labels,folder/'comparison-pixels.png',Image.Resampling.NEAREST)
        records.append({'path':name,'itemId':item_id,'kind':'component' if component else 'object','sourceSha256':row['sha256'],'installedSha256':sha(current_data),
                        'comparison':str((folder/'comparison.png').relative_to(output)),'sourceSize':list(source.size),'installedSize':list(current.size),
                        'installedDifferenceFromSourceLanczos':difference(source,current),'inference':inference,'variants':variants})
        print(f'Compared {index+1}/{len(rows)}: item {item_id} {name}',flush=True)
    profile={'model':lock['variant'],'weightsSha256':lock['weights']['sha256'],'device':'mlx-gpu','precision':'fp32',
             'outputMode':'direct-neural-rgb','deploymentScale':2,'alphaPolicy':'nearest-exact','retail':False,
             'implementationSha256':sha(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))),
             'versions':{n:importlib.metadata.version(n) for n in ('mlx','numpy','Pillow')}}
    write_json(output/'package'/'trial-manifest.json',{'schema':1,'kind':'wxl-equipment-trial','patch':PATCH,'profile':profile,'files':files,'gameplayVerified':False})
    report={'state':'prepared-awaiting-visual-review','textures':len(records),'seconds':time.time()-started,'inventorySha256':sha(inventory_raw),
            'profile':profile,'records':records,'gameplayVerified':False,'metricsAreQualityScores':False}
    write_json(output/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('records','profile')},indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','output','client','weights','lock'):p.add_argument('--'+name,type=Path,required=True)
    build(p.parse_args())

if __name__=='__main__':main()
