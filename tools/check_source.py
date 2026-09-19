"""Inspect public Git source paths and content; never scan private asset directories."""
from pathlib import Path
import subprocess,re
ROOT=Path(__file__).resolve().parents[1]
names=set(subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode().split('\0'))-{''}
for name in sorted(names):
    p=ROOT/name
    assert not p.is_symlink() and p.is_file(),name
    assert not set(Path(name).parts)&{'_local','.venv','__pycache__','assets','cache','vendor','dist'},name
    assert p.suffix.lower() not in {'.exe','.dll','.m2','.skin','.anim','.blp','.dbc','.db2','.mpq','.png','.jpg','.safetensors'},name
    data=p.read_bytes();assert b'\0' not in data,name
    assert not re.search(rb'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----',data),name
    if 'tests' in p.parts:data=data.replace(b'/Users/' + b'a/',b'<fixture>/')
    assert not re.search(rb'/Users/[A-Za-z0-9_.-]+/',data),name
print('Checked',len(names),'public source files')
