"""Read-only race/material and NPC reference audit. This is not a gameplay test."""
import argparse,json,struct
from pathlib import Path
from wxl_equipment.assets import DBC,sha
from wxl_equipment.retail import model_evidence

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--characters',type=Path,required=True);p.add_argument('--npc-dbc',type=Path,required=True);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 report={'gameplayVerified':False,'models':[],'npcReferences':[],'npcPolicy':'Baked atlases are not modified by item texture overlays'}
 for path in sorted(a.characters.glob('*/*/*.m2')):
  data=path.read_bytes();e=model_evidence(data)
  report['models'].append({'path':str(path.relative_to(a.characters)),'sha256':sha(data),'bodyMaterialPresent':any(t[0]==1 for t in e['textureTypesAndFlags']),'vertices':e['vertices'],'uvSha256':e['uvSha256']})
 npc=DBC(a.npc_dbc.read_bytes(),21);displays={r['displayId'] for r in json.loads(a.inventory.read_text())['items']}
 for row in npc.rows.values():
  matched=sorted(displays & set(row[9:20]))
  if matched:report['npcReferences'].append({'id':row[0],'race':row[1],'sex':row[2],'displayIds':matched,'bakedTexture':npc.string(row[20]),'affectedByComponentOverlay':False})
 a.output.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'raceSexModels':len(report['models']),'bodyMaterialPresent':sum(r['bodyMaterialPresent'] for r in report['models']),'npcReferences':len(report['npcReferences']),'gameplayVerified':False}))
if __name__=='__main__':main()
