"""Repair deployment format from an existing hashed package without inference."""
import argparse
import json
import math
from pathlib import Path
import shutil
import time
from .assets import sha,safe_path
from .client_blp import to_runtime
from .package import PATCH,no_links
from .batch import write_json


def repack(source,output):
    source=no_links(source);output=no_links(output)
    if output.exists():raise FileExistsError(output)
    npc=(source/'release-manifest.json').is_file();filename='release-manifest.json' if npc else 'manifest.json'
    raw=(source/filename).read_bytes();manifest=json.loads(raw)
    if npc:
        if manifest['kind']!='wxl-modern-races-assets' or manifest['schemaVersion']!=1:raise ValueError('Unexpected NPC manifest')
        rows=manifest['files']
    else:
        if manifest['schema']!=1 or manifest['patch']!=PATCH:raise ValueError('Unexpected Item manifest')
        rows=[{'path':PATCH+'/'+name,'sha256':digest} for name,digest in manifest['files'].items()]
    names=set();output.mkdir(parents=True);reports=[];files=[];started=time.perf_counter()
    for index,row in enumerate(rows):
        name=safe_path(row['path'])
        prefix='Data/Patch-ModernRaces-HD.MPQ/Textures/BakedNpcTextures/' if npc else PATCH+'/item/'
        if not name.casefold().startswith(prefix.casefold()) or not name.lower().endswith('.blp') or name.casefold() in names:raise ValueError('Unexpected/colliding deployment target')
        names.add(name.casefold());data=no_links(source/name).read_bytes()
        if sha(data)!=row['sha256']:raise ValueError('Source package changed: '+name)
        component=not npc and name.casefold().startswith(PATCH.casefold()+'/item/texturecomponents/')
        encoded,report=to_runtime(data,component);dest=output/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(encoded)
        digest=sha(encoded);reports.append({'path':name,'sourceSha256':row['sha256'],'sha256':digest,'bytes':len(encoded),**report});files.append({'path':name,'size':len(encoded),'sha256':digest})
        if (index+1)%1000==0:print('repacked',index+1,'/',len(rows),flush=True)
    manifest['files']=files if npc else {r['path'][len(PATCH)+1:]:r['sha256'] for r in files}
    manifest['deployment']={'sourceManifestSha256':sha(raw),'formatVersion':2,'bgraPreferredFormat':2,'bodyComponents':'palettized with independent exact alpha','paletteQuantizer':'Pillow MAXCOVERAGE over all mips, no dithering','headerBytes':1172,'neuralInferenceRepeated':False}
    manifest['gameplayVerified']=False;write_json(output/filename,manifest)
    if npc:shutil.copy2(no_links(source/'source-guards.json'),output/'source-guards.json')
    count=sum(r['visibleRgbChannels'] for r in reports);squared=sum(r['visibleRgbQuantizationSquaredError'] for r in reports)
    report={'state':'complete','textures':len(files),'bytes':sum(r['size'] for r in files),'seconds':time.perf_counter()-started,'neuralInferenceRepeated':False,'allMipAlphaExact':True,
            'rawRgbaExactTextures':sum(r['allMipRgbaExact'] for r in reports),'palettizedTextures':sum(r['encoding']==1 for r in reports),'visibleRgbQuantizationRmse':math.sqrt(squared/count) if count else 0,'visibleRgbQuantizationMax':max(r['visibleRgbQuantizationMax'] for r in reports),'files':reports}
    write_json(output/'repack-report.json',report);print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();repack(a.package,a.output)

if __name__=='__main__':main()
