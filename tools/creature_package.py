"""Build/verify the combined mount and druid package; use install_creatures.py to deploy."""
import argparse,hashlib,json,os,shutil,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for component in ('races','equipment','mounts'):
    sys.path.insert(0,str(ROOT/'components'/component/'src'))
sys.path.insert(0,str(ROOT/'components/mounts/tools'))
from build_redirect import build as build_redirect
from wxl_mounts.io import checked_path,read_json,write_json
from wxl_mounts.packing import Storm,inventory,digest,sha,check_names
from wxl_mounts.mpq_format import LegacyMPQ
from wxl_mounts.exports import RawIndex
from wxl_mounts.model.bundle import audit,stage
from wxl_mounts.model.chunks import inspect_asset,read_chunks,texture_records
from wxl_mounts.creatures import bind_textures,select_sections,validate_geometry,array
from wxl_races.druids import BUILD_CONFIG,DISPLAY_IDS,patch_tables as druid_tables
from wxl_races.tauren_scale import apply_world_scale
from wxl_mounts.tables import TABLES,NAMESPACE,patch_mounts
from wxl_mounts.closure import required_members
from wxl_mounts.animations import repair_missing_remaps,unreachable_runtime_ids

ARCHIVE='Data/Patch-ModernMounts-HD.MPQ'
DLL_PATH='Extensions/wxl-modern-mounts/wxl-modern-mounts.dll'
DLL_SHA='75349fdd73424591b61f4342658f1d898f3db63ad8a5ca372843af4c78a01321'
DRUID_ASSET_DIGEST='cbe61708690c30b22babf76642d61f49bc500aebc9fc24d31512b7a50e9131a8'

def asset_digest(rows):
    return sha(json.dumps(sorted(rows,key=lambda r:r['path']),sort_keys=True,separators=(',',':')).encode())

OLD_ARCHIVE='Data/Patch-ModernRaces-DruidForms.MPQ'
OLD_DLL='Extensions/wxl-druid-forms/wxl-druid-forms.dll'
OLD_FILES={OLD_ARCHIVE:'108f38ce4083d4cbc4ffb6721207d28d8b4a404275703851d465247e11e10f8e',
           OLD_DLL:'db3e5b2e3bcf6344544b1842ab2f1452de050b1a17c937d920142348a88157c0'}

def extension_checks(data):
    from wxl_mounts.abi import check as check_abi
    return [check_abi(data,delta,expected_hash=DLL_SHA) for delta in (0,0x08000000)]

def import_druids(package, staged, originals):
    package=checked_path(package);manifest=read_json(package/'release-manifest.json')
    if manifest.get('kind')!='wxl-druid-forms' or manifest.get('schemaVersion')!=1:raise ValueError('Unrecognized druid package')
    if {r['path']:r['sha256'] for r in manifest['files']}!=OLD_FILES:raise ValueError('Unverified druid handoff')
    for r in manifest['files']:
        p=checked_path(package/r['path'])
        if p.stat().st_size!=r['size'] or digest(p)!=r['sha256']:raise ValueError('Druid handoff changed')
    plan=manifest['plan'];tables=druid_tables(originals[TABLES[0]],originals[TABLES[1]],plan)
    check_names(manifest['assets']);reader=LegacyMPQ(package/OLD_ARCHIVE)
    imported=[]
    try:
        names=[n.replace('\\','/') for n in reader.read('(listfile)').decode('ascii').splitlines() if n!='(listfile)']
        if len(names)!=len(manifest['assets']) or set(names)!={r['path'] for r in manifest['assets']}:raise ValueError('Druid archive members changed')
        for row in manifest['assets']:
            name=row['path'];data=reader.read(name)
            if not name.startswith('WXL/DruidForms/') or len(data)!=row['size'] or sha(data)!=row['sha256']:raise ValueError('Druid asset mismatch')
            if name in [f'WXL/DruidForms/DBFilesClient/{n}' for n in TABLES]:
                if data!=tables[Path(name).name]:raise ValueError('Druid table extends beyond agreed model references')
                continue
            dest=staged/name;dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as f:f.write(data)
            imported.append(row)
    finally:reader.close()
    if len(imported)!=534 or asset_digest(imported)!=DRUID_ASSET_DIGEST:raise ValueError('Druid asset inventory differs from the verified handoff')
    return tables,{'plan':plan,'assets':imported,'manifestSha256':digest(package/'release-manifest.json'),'sourceFiles':manifest['files'],'byteIdenticalImport':True}

def prepare_entry(entry,index,staged,namespace=NAMESPACE):
    did=entry['displayId'];filename='Form' if namespace=='WXL/DruidForms' else 'Mount'
    if entry['modelPath']!=f'{namespace}/Models/{did}/{filename}.m2':raise ValueError('Unsafe creature destination')
    if entry.get('modelGeosetDataId') and entry.get('selectedGeosets') is None:raise ValueError('Explicit creature geoset selection is missing')
    fid=entry['fileDataId'];source=index.resolve_fdid(fid)
    if source is None:raise ValueError(f'Missing model {fid}')
    info=inspect_asset(source)
    paths={str(i):f'{namespace}/Textures/{i}.blp' for i in info.get('txid',[]) if i}
    target={'schemaVersion':1,'source':{'modelPath':f'{fid}.m2','fileDataId':fid,'fileDataIdPaths':paths},
            'target':{'clientBuild':12340,'legacyPath':entry['modelPath']}}
    check=audit(target,index)
    if not check['readyForCurrentWarcraftXL'] or info.get('skid'):raise ValueError(f'Unsupported model {fid}: '+str(check['errors'])+str(check['warnings']))
    if any(not dep['path'] for dep in check['dependencies']['lodSkins']):raise ValueError('Missing requested LOD skin')
    for dep in check['dependencies']['textures']:
        if dep.get('required') and not dep['path']:raise ValueError('Missing static texture')
    result=stage(target,index,staged)
    model=staged/entry['modelPath']
    data,bindings=bind_textures(model.read_bytes(),entry['textureFileDataIds'],namespace=namespace)
    animation_fix={}
    if namespace==NAMESPACE:data,animation_fix=repair_missing_remaps(data)
    model.write_bytes(data)
    for tid in bindings:
        p=index.resolve_fdid(tid)
        if p is None or p.read_bytes()[:4] not in (b'BLP1',b'BLP2'):raise ValueError('Missing/invalid variation texture '+str(tid))
        dest=staged/namespace/'Textures'/f'{tid}.blp';dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and digest(dest)!=digest(p):raise ValueError('Variation texture collision')
        if not dest.exists():shutil.copyfile(p,dest)
    geometry,removed={},{}
    selection=set(entry['selectedGeosets']) if entry.get('selectedGeosets') is not None else None
    for skin in sorted(model.parent.glob('*.skin')):
        converted,excluded=select_sections(skin.read_bytes(),selection)
        geometry[skin.name]=validate_geometry(data,converted);skin.write_bytes(converted);removed[skin.name]=excluded
    body=read_chunks(data)[0].payload
    n,o=array(body,28,64);animations=sorted({struct.unpack_from('<H',body,o+i*64)[0] for i in range(n)})
    n,o=array(body,0xf0,40);attachments=[{'id':struct.unpack_from('<I',body,o+i*40)[0],'bone':struct.unpack_from('<H',body,o+i*40+4)[0], 'position':list(struct.unpack_from('<3f',body,o+i*40+8))} for i in range(n)]
    closure={fid,*bindings}
    for key in ('skins','lodSkins','animations','textures','bones'):
        closure.update(d['fileDataId'] for d in check['dependencies'][key] if d.get('fileDataId') and d.get('path'))
    return {'displayId':entry['displayId'],'sourceModel':fid,'sourceSha256':digest(source),
            'geometry':geometry,'removedGeosets':removed,'animationIds':animations,'attachments':attachments,
            'animationLookupAdaptation':animation_fix,
            'sourceFiles':[{'fileDataId':i,'size':index.resolve_fdid(i).stat().st_size,'sha256':digest(index.resolve_fdid(i))} for i in sorted(closure)],
            'gameplayVerified':False}

def build(plan_path,original_dir,raw_roots,output,library,sdk,druid_package=None,druid_plan_path=None):
    output=checked_path(output);original_dir=checked_path(original_dir);plan=read_json(plan_path)
    if output.exists():raise ValueError('Fresh output required')
    if sys.flags.optimize:raise ValueError('Optimized Python is unsupported')
    for source in [original_dir,*map(checked_path,raw_roots),*( [checked_path(druid_package)] if druid_package else [])]:
        if output==source or output in source.parents or source in output.parents:raise ValueError('Output overlaps input workspace')
    originals={n:checked_path(original_dir/n).read_bytes() for n in TABLES}
    if druid_package and druid_plan_path:raise ValueError('Choose druid import or source preparation')
    index=RawIndex(raw_roots,BUILD_CONFIG);extension=build_redirect(sdk);checks=extension_checks(extension)
    output.mkdir(parents=True);staged=output/'staged';staged.mkdir();baseline=originals;druid=None;reports=[]
    if druid_package:baseline,druid=import_druids(druid_package,staged,originals)
    if druid_plan_path:
        dp=read_json(druid_plan_path);baseline=druid_tables(originals[TABLES[0]],originals[TABLES[1]],dp)
        for e in dp['displays']:reports.append(prepare_entry(e,index,staged,'WXL/DruidForms'))
        diagnostic=staged/'bundle-report.json'
        if diagnostic.exists():diagnostic.unlink()
        druid={'plan':dp,'assets':inventory(staged),'byteIdenticalImport':False}
    tables=patch_mounts(originals,baseline,plan)
    tables['CreatureModelData.dbc']=apply_world_scale(originals['CreatureModelData.dbc'],tables['CreatureModelData.dbc'])
    for entry in sorted(plan['displays'],key=lambda e:e['displayId']):
        reports.append(prepare_entry(entry,index,staged));print('prepared',entry['displayId'],flush=True)
    diagnostic=staged/'bundle-report.json'
    if diagnostic.exists():diagnostic.unlink()
    folder=staged/NAMESPACE/'DBFilesClient';folder.mkdir(parents=True)
    for name,data in tables.items():(folder/name).write_bytes(data)
    rows=inventory(staged);namespaces=(NAMESPACE+'/', 'WXL/DruidForms/')
    if any(not r['path'].startswith(namespaces) for r in rows):raise ValueError('Global asset override outside ownership')
    archive=output/ARCHIVE;archive.parent.mkdir();storm=Storm(library);handle=storm.create(archive,max_files=1 << (len(rows)+1).bit_length())
    try:
        for row in rows:storm.add(handle,row['path'],(staged/row['path']).read_bytes())
    finally:storm.close(handle)
    dll=output/DLL_PATH;dll.parent.mkdir(parents=True);dll.write_bytes(extension)
    manifest={'schemaVersion':1,'kind':'wxl-modern-creatures','gameplayVerified':False,'mountPlan':plan,'druids':druid,'taurenScale':0.75,
              'assets':rows,'conversion':reports,'extensionChecks':checks,'exportProvenance':index.provenance,
              'originalHashes':{n:sha(b) for n,b in originals.items()},
              'files':[{'path':n,'size':(output/n).stat().st_size,'sha256':digest(output/n)} for n in (ARCHIVE,DLL_PATH)]}
    write_json(output/'release-manifest.json',manifest)
    verify(output,library,originals=originals)
    return manifest

def verify(package,library,originals=None):
    if not originals or set(originals)!=set(TABLES):raise ValueError('Full verification requires both original DBCs')
    package=checked_path(package);m=read_json(package/'release-manifest.json')
    if m.get('kind')!='wxl-modern-creatures' or m.get('schemaVersion')!=1:raise ValueError('Unknown package')
    if [r['path'] for r in m['files']]!=[ARCHIVE,DLL_PATH]:raise ValueError('Unexpected installed files/order')
    for r in m['files']:
        p=checked_path(package/r['path'])
        if p.stat().st_size!=r['size'] or digest(p)!=r['sha256']:raise ValueError('Package bytes changed')
    if digest(package/DLL_PATH)!=DLL_SHA:raise ValueError('Unknown extension')
    if m['originalHashes']!={n:sha(b) for n,b in originals.items()}:raise ValueError('Package original DBC profile mismatch')
    rows=m['assets'];check_names(rows);expected={r['path'] for r in rows}
    if m['druids'] and m['druids'].get('byteIdenticalImport'):
        if len(m['druids']['assets'])!=534 or asset_digest(m['druids']['assets'])!=DRUID_ASSET_DIGEST:raise ValueError('Altered druid handoff inventory')
    if any(not n.startswith((NAMESPACE+'/', 'WXL/DruidForms/')) for n in expected):raise ValueError('Outside namespace')
    model_names={e['modelPath'] for e in m['mountPlan']['displays']}
    if m['druids']:model_names|={f'WXL/DruidForms/Models/{i}/Form.m2' for i in DISPLAY_IDS}
    if {n for n in expected if n.endswith('.m2')}!=model_names:raise ValueError('Model coverage mismatch')
    table_names={f'{NAMESPACE}/DBFilesClient/{n}' for n in TABLES}
    if {n for n in expected if n.endswith('.dbc')}!=table_names:raise ValueError('Multiple creature-table owners')
    reader=LegacyMPQ(package/ARCHIVE);storm=Storm(library);h=None
    try:
        h=storm.open(package/ARCHIVE)
        listed=[n.replace('\\','/') for n in reader.read('(listfile)').decode('ascii').splitlines() if n!='(listfile)']
        if len(listed)!=len(expected) or set(listed)!=expected or len(reader.blocks)!=len(expected)+1:raise ValueError('MPQ listfile/blocks mismatch')
        for row in rows:
            b=reader.read(row['path'])
            if len(b)!=row['size'] or sha(b)!=row['sha256'] or storm.read(h,row['path'].swapcase())!=b:raise ValueError('MPQ readback mismatch')
        from io import BytesIO
        from PIL import Image
        for name in sorted(expected):
            if name.endswith('.m2'):
                b=reader.read(name)
                if name.startswith(NAMESPACE+'/') and unreachable_runtime_ids(b):raise ValueError('Unreachable native animation after runtime remaps')
                missing=required_members(name,b)-expected
                if missing:raise ValueError('Missing runtime aliases: '+str(sorted(missing)))
                skins=[n for n in expected if n.startswith(name[:-3]) and n.endswith('.skin')]
                if not skins:raise ValueError('Model without skin')
                for skin in skins:validate_geometry(b,reader.read(skin))
                for t in texture_records(read_chunks(b)[0].payload):
                    if t['type']!=0 or t['name'] not in expected:raise ValueError('Unresolved texture reference')
            if name.endswith('.blp'):
                with Image.open(BytesIO(reader.read(name))) as im:
                    im.load()
                    if max(im.size)>4096:raise ValueError('Texture exceeds 4096')
        if m['druids']:
            for row in m['druids']['assets']:
                if sha(reader.read(row['path']))!=row['sha256']:raise ValueError('Druid bytes changed')
        if originals:
            baseline=originals
            if m['druids']:baseline=druid_tables(originals[TABLES[0]],originals[TABLES[1]],m['druids']['plan'])
            tables=patch_mounts(originals,baseline,m['mountPlan'])
            if m.get('taurenScale') != 0.75:raise ValueError('Expected suite Tauren scale')
            tables['CreatureModelData.dbc']=apply_world_scale(originals['CreatureModelData.dbc'],tables['CreatureModelData.dbc'])
            for n,b in tables.items():
                if reader.read(f'{NAMESPACE}/DBFilesClient/{n}')!=b:raise ValueError('Unexpected DBC mutation')
    finally:
        reader.close()
        if h:storm.close(h)
    return m

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build');b.add_argument('--plan',type=Path,required=True);b.add_argument('--original-dbc',type=Path,required=True);b.add_argument('--raw',type=Path,action='append',required=True);b.add_argument('--output',type=Path,required=True);b.add_argument('--sdk',type=Path,required=True);b.add_argument('--druid-package',type=Path);b.add_argument('--druid-plan',type=Path)
    v=sub.add_parser('verify');v.add_argument('--package',type=Path,required=True);v.add_argument('--original-dbc',type=Path,required=True)
    for cmd in (b,v):cmd.add_argument('--stormlib',type=Path,required=True)
    a=p.parse_args()
    if a.command=='build':m=build(a.plan,a.original_dbc,a.raw,a.output,a.stormlib,a.sdk,a.druid_package,a.druid_plan)
    else:m=verify(a.package,a.stormlib,{n:(a.original_dbc/n).read_bytes() for n in TABLES} if a.original_dbc else None)
    print(json.dumps({'assets':len(m['assets']),'mounts':len(m['mountPlan']['displays']),'druids':len(m['druids']['plan']['displays']) if m['druids'] else 0,'files':m['files']},indent=2))
