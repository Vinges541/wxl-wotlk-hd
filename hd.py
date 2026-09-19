"""Run component source tools from one checkout; preparation never implies installation."""
import argparse,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('component',choices=['races','equipment','mounts','shared'])
    p.add_argument('tool',help='script basename, e.g. prepare_release.py or creature_package.py')
    p.add_argument('args',nargs=argparse.REMAINDER)
    a=p.parse_args()
    if Path(a.tool).name!=a.tool or not a.tool.endswith('.py'):p.error('Expected a Python tool basename')
    base=ROOT if a.component=='shared' else ROOT/'components'/a.component
    tool=base/'tools'/a.tool
    if not tool.is_file():p.error('Unknown tool')
    env=dict(os.environ)
    env['PYTHONPATH']=os.pathsep.join(str(ROOT/'components'/c/'src') for c in ('races','equipment','mounts'))
    raise SystemExit(subprocess.call([sys.executable,str(tool),*a.args],cwd=base,env=env))
