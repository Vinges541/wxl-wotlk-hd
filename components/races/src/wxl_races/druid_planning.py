"""Race-owned druid selection from pinned Retail and original WotLK tables."""
from pathlib import Path
import hashlib,json
from .druids import make_plan as druid_plan, BUILD_CONFIG
TABLES=('CreatureDisplayInfo.dbc','CreatureModelData.dbc')
def read_bytes(path):
    path=Path(path)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Symlink input')
    return path.read_bytes()
def read_json(path): return json.loads(read_bytes(path))
def fingerprint(path):
    data=read_bytes(path)
    return {'file':Path(path).name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
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


def make_druid_plan(original_dir,retail_dir):
    originals={n:read_bytes(Path(original_dir)/n) for n in TABLES}
    build,displays,models,geosets,sources=retail_inputs(retail_dir)
    plan=druid_plan(originals[TABLES[0]],originals[TABLES[1]],list(displays.values()),list(models.values()),build)
    for e in plan['displays']:
        d=displays[e['displayId']];e['selectedGeosets']=selected_geosets(d,models[d['ModelID']],geosets)
    plan['retailSources']=sources
    return plan
