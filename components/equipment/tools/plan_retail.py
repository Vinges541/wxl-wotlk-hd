"""Join same-build Retail item appearance/material/model tables without assuming ID equality."""
import argparse,json,hashlib
from pathlib import Path
from collections import defaultdict

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--retail',type=Path,required=True);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--build',required=True);a=p.parse_args()
 build=json.loads((a.retail/'build.json').read_text())
 if build['BuildConfig']!=a.build:raise ValueError('BuildConfig mismatch')
 def rows(n):return json.loads((a.retail/(n+'.json')).read_text())
 def indexed(n,key):
  d=defaultdict(list)
  for r in rows(n):d[r[key]].append(r)
  return d
 mods=indexed('ItemModifiedAppearance','ItemID');apps={r['ID']:r for r in rows('ItemAppearance')};displays={r['ID']:r for r in rows('ItemDisplayInfo')}
 materials=indexed('ItemDisplayInfoMaterialRes','ItemDisplayInfoID');model_materials=indexed('ItemDisplayInfoModelMatRes','ItemDisplayInfoID')
 textures=indexed('TextureFileData','MaterialResourcesID');models=indexed('ModelFileData','ModelResourcesID')
 result=[];requests=set()
 for item in json.loads(a.inventory.read_text())['items']:
  for m in mods[item['itemId']]:
   if m['ItemAppearanceModifierID']!=0:continue
   appearance=apps[m['ItemAppearanceID']];d=displays[appearance['ItemDisplayInfoID']]
   entry={'itemId':item['itemId'],'legacyDisplayId':item['displayId'],'appearance':appearance,'modifiedAppearance':m,'display':d,'textureBindings':[],'models':[],'status':'unresolved-pending-file-comparison'}
   for binding in materials[d['ID']]+model_materials[d['ID']]:
    mapped=textures[binding['MaterialResourcesID']]
    entry['textureBindings'].append({'binding':binding,'files':mapped});requests.update(r['FileDataID'] for r in mapped)
   for resource in d['ModelResourcesID']:
    if resource:entry['models']+=models[resource];requests.update(r['FileDataID'] for r in models[resource])
   result.append(entry)
 if len(requests)>32:raise ValueError(f'{len(requests)} requests exceed pilot budget; narrow item list')
 (a.retail/'requests.json').write_text(json.dumps(sorted(requests)))
 (a.retail/'mapping.json').write_text(json.dumps({'BuildConfig':a.build,'items':result},indent=2))
 print(json.dumps({'items':len(result),'requestedFiles':len(requests),'ids':sorted(requests)}))
if __name__=='__main__':main()
