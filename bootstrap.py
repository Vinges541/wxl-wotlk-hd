"""Install the unified source toolkit into a local virtual environment."""
from pathlib import Path
import os,subprocess,sys,venv
ROOT=Path(__file__).resolve().parent
if __name__=='__main__':
    target=ROOT/'.venv'
    if not target.exists():venv.create(target,with_pip=True)
    python=target/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    subprocess.run([str(python),'-m','pip','install','-e',str(ROOT)+'[prepare]'],check=True)
    print('Ready. Use',python, 'hd.py --help')
