"""One owner for the creature tables; clone only selected display model references."""
from .creatures import DBC
from .packing import sha
from .druids import BUILD_CONFIG, DISPLAY_IDS
TABLES=('CreatureDisplayInfo.dbc','CreatureModelData.dbc')
NAMESPACE='WXL/ModernMounts'

def patch_mounts(originals, baseline, plan):
    if plan.get('schemaVersion')!=1 or plan.get('kind')!='wxl-mount-replacement-plan' or plan.get('build',{}).get('BuildConfig')!=BUILD_CONFIG:
        raise ValueError('Unsupported reviewed mount plan')
    if plan.get('sourceHashes')!={name:sha(originals[name]) for name in TABLES}:
        raise ValueError('Original DBC changed since planning')
    a=DBC(baseline[TABLES[0]],16,(6,7,8,9));b=DBC(baseline[TABLES[1]],28,(2,))
    original_a=DBC(originals[TABLES[0]],16); entries=plan['displays'];ids=[e['displayId'] for e in entries]
    if len(set(ids))!=len(ids) or set(ids)&DISPLAY_IDS:raise ValueError('Duplicate mount display or druid collision')
    next_id=max(b.by_id)+1
    for e in sorted(entries,key=lambda e:e['displayId']):
        did=e['displayId'];path=f'{NAMESPACE}/Models/{did}/Mount.m2'
        if e.get('approved') is not True or e['modelPath']!=path or e['legacyModelId']!=original_a.by_id[did][1] or a.by_id[did]!=original_a.by_id[did]:
            raise ValueError('Unreviewed target or existing table owner changed the display')
        row=b.by_id[e['legacyModelId']].copy();row[0]=next_id;row[2]=b.add_string(path.replace('/','\\'))
        b.rows.append(row);a.by_id[did][1]=next_id;next_id+=1
    return {TABLES[0]:a.encode(),TABLES[1]:b.encode()}
