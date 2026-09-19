"""Run independent synthetic suites without module-name collisions."""
from pathlib import Path
import os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
env['PYTHONPATH']=os.pathsep.join(str(ROOT/'components'/c/'src') for c in ('races','equipment','mounts'))
for component in ('races','equipment','mounts'):
    subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT/'components'/component,env=env,check=True)
