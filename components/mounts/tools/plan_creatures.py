"""Plan all druid forms or compile a complete, explicitly reviewed mount inventory."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from wxl_mounts.planning import make_druid_plan,make_mount_plan,export_request
from wxl_mounts.io import write_json

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('kind',choices=['druids','mounts'])
    p.add_argument('--original-dbc',type=Path,required=True);p.add_argument('--retail',type=Path,required=True)
    p.add_argument('--inventory',type=Path);p.add_argument('--review',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--export-request',type=Path)
    a=p.parse_args()
    if a.kind=='mounts':
        if not a.inventory or not a.review:p.error('mounts requires --inventory and --review')
        plan=make_mount_plan(a.inventory,a.original_dbc,a.retail,a.review)
    else:plan=make_druid_plan(a.original_dbc,a.retail)
    write_json(a.output,plan)
    if a.export_request:write_json(a.export_request,export_request(plan))
    print('Planned',len(plan['displays']),'displays')
