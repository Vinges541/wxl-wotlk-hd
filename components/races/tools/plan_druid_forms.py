"""Plan the 30 race-owned druid forms without a mounts checkout."""
import argparse,json
from pathlib import Path
from wxl_races.druid_planning import make_druid_plan
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('original-dbc','retail','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--export-request',type=Path)
    a=p.parse_args();plan=make_druid_plan(a.original_dbc,a.retail)
    request={'build':plan['build'],'models':sorted({e['fileDataId'] for e in plan['displays']}),
             'textures':sorted({i for e in plan['displays'] for i in e['textureFileDataIds'] if i})}
    for target,value in [(a.output,plan),(a.export_request,request)]:
        if target:
            with target.open('x') as f:json.dump(value,f,indent=2)
