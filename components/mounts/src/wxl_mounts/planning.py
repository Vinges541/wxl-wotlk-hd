"""Explicit identity-reviewed mount plans and complete druid source plans."""
from pathlib import Path
from .io import read_json, read_bytes, fingerprint, asset_path
from .packing import sha
from .druids import make_plan as druid_plan, BUILD_CONFIG
from .tables import TABLES, NAMESPACE


def retail_inputs(root):
    root=Path(root)
    build=read_json(root/'build.json')
    if build.get('BuildConfig')!=BUILD_CONFIG or build.get('Product')!='wow':raise ValueError('Pinned Retail donor required')
    files=['CreatureDisplayInfo.json','CreatureModelData.json','CreatureDisplayInfoGeosetData.json','build.json']
    values={name:read_json(root/name) for name in files}
    def index(name):
        rows=values[name];idx={r['ID']:r for r in rows}
        if len(idx)!=len(rows):raise ValueError('Duplicate Retail ID in '+name)
        return idx
    return build,index(files[0]),index(files[1]),values[files[2]],{n:fingerprint(root/n) for n in files}


def selected_geosets(display,model,rows):
    if not model.get('CreatureGeosetDataID'):return None
    return sorted({(r['GeosetIndex']+1)*100+r['GeosetValue'] for r in rows if r['CreatureDisplayInfoID']==display['ID']})


from wxl_races.druid_planning import make_druid_plan


def make_mount_plan(inventory_path,original_dir,retail_dir,review_path):
    inv=read_json(inventory_path);review=read_json(review_path)
    if inv.get('kind')!='mount-inventory' or review.get('kind')!='same-mount-review' or review.get('schemaVersion')!=1:raise ValueError('Explicit inventory and identity review required')
    originals={n:read_bytes(Path(original_dir)/n) for n in TABLES}
    for n in TABLES:
        if sha(originals[n])!=inv['sources'][n[:-4]]['sha256']:raise ValueError('Inventory uses other original tables')
    build,ds,ms,geosets,sources=retail_inputs(retail_dir)
    old={d['displayId']:d for d in inv['displays']};coverage=review['displays']
    if len(coverage)!=len(old) or {r['displayId'] for r in coverage}!=set(old):raise ValueError('Review must cover every inventoried display exactly once')
    mounts=read_json(Path(retail_dir)/'Mount.json');links=read_json(Path(retail_dir)/'MountXDisplay.json')
    out=[]
    for decision in coverage:
        if decision['status']!='replace':
            if not decision.get('reason'):raise ValueError('Every exclusion needs a reason')
            continue
        did=decision['displayId'];rid=decision['retailDisplayId'];d=ds[rid];model=ms[d['ModelID']]
        if not decision.get('reason') or decision['fileDataId']!=model['FileDataID']:raise ValueError('Reviewed source model drift')
        if d.get('ConditionalCreatureModelID') or d.get('ExtendedDisplayInfoID'):raise ValueError('Conditional/customizable model needs an adapter')
        # Identical display identity, or the same actual mount spell's Retail display.
        if rid!=did:
            spells={s['spellId'] for s in inv['spells'] if any(did in (m['displayId'],m['otherGenderDisplayId']) for m in s['serverModels'])}
            mount_ids={m['ID'] for m in mounts if m['SourceSpellID'] in spells}
            match=[l for l in links if l['MountID'] in mount_ids and l['CreatureDisplayInfoID']==rid and not l['PlayerConditionID']]
            if not match:raise ValueError('Reviewed replacement does not resolve to the same mount')
        tex=d['TextureVariationFileDataID']
        if any(type(i) is not int or i<0 for i in tex):raise ValueError('Invalid variation ID')
        out.append({'displayId':did,'retailDisplayId':rid,'fileDataId':model['FileDataID'],
                    'textureFileDataIds':tex,'legacyModelId':old[did]['modelId'],'legacyPath':old[did]['modelPath'],
                    'modelGeosetDataId':model.get('CreatureGeosetDataID',0),
                    'selectedGeosets':selected_geosets(d,model,geosets),
                    'modelPath':f'{NAMESPACE}/Models/{did}/Mount.m2','approved':True,'reason':decision['reason']})
    if not out:raise ValueError('No reviewed replacements')
    return {'schemaVersion':1,'kind':'wxl-mount-replacement-plan','build':build,
            'sourceHashes':{n:sha(b) for n,b in originals.items()},'retailSources':sources,
            'inventorySource':fingerprint(inventory_path),'reviewSource':fingerprint(review_path),
            'identitySources':{n:fingerprint(Path(retail_dir)/n) for n in ('Mount.json','MountXDisplay.json')},
            'coverage':coverage,'displays':out}


def export_request(plan):
    if plan.get('build',{}).get('BuildConfig')!=BUILD_CONFIG:raise ValueError('Pinned plan required')
    return {'build':plan['build'],'models':sorted({e['fileDataId'] for e in plan['displays']}),
            'textures':sorted({i for e in plan['displays'] for i in e['textureFileDataIds'] if i})}
