"""Preparation and guarded installation of an independent loose WarcraftXL patch."""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from .assets import safe_path, sha, inspect_blp
from .client_blp import to_runtime,validate as validate_client_blp

PATCH='Patch-WXL-Equipment.MPQ'
BASE={'common.mpq','common-2.mpq','expansion.mpq','lichking.mpq','patch.mpq','patch-2.mpq','patch-3.mpq',
      'base-ruru.mpq','backup-ruru.mpq','locale-ruru.mpq','speech-ruru.mpq',
      'expansion-locale-ruru.mpq','expansion-speech-ruru.mpq','lichking-locale-ruru.mpq','lichking-speech-ruru.mpq',
      'patch-ruru.mpq','patch-ruru-2.mpq','patch-ruru-3.mpq'}


def no_links(path):
    path=path.absolute()
    for part in [path,*path.parents]:
        if part.is_symlink():raise ValueError(f'Symlink refused: {part}')
    return path


def tree(root, hashes=True):
    no_links(root)
    result={};seen=set()
    for path in sorted(root.rglob('*')):
        no_links(path)
        if path.is_file():
            name=safe_path(path.relative_to(root).as_posix())
            if name.casefold() in seen:raise ValueError('Case collision')
            seen.add(name.casefold())
            result[name]=sha(path.read_bytes()) if hashes else None
    return result


def stopped():
    result=subprocess.run(['ps','-axo','comm='],text=True,capture_output=True,check=True)
    for line in result.stdout.splitlines():
        name=line.strip().replace('\\','/').split('/')[-1].casefold()
        if name in ('wow.exe','wow','wow-64.exe'):raise RuntimeError('Close WoW before installation or rollback')


def prepare(workspace, output, accepted):
    """Explicit accepted cache keys represent offline review, never gameplay certification."""
    no_links(output)
    if output.exists():raise FileExistsError(output)
    data=json.loads((workspace/'inference.json').read_text())
    records=[r for r in data['records'] if r['cacheKey'] in accepted]
    if not records or {r['cacheKey'] for r in records}!=set(accepted):raise ValueError('Unknown/empty accepted selection')
    output.mkdir(parents=True)
    files={}
    for r in records:
        name=safe_path(r['path'])
        if not name.lower().startswith('item/') or not name.lower().endswith('.blp'):raise ValueError('Only equipment BLP permitted')
        source=no_links(workspace/'cache'/r['cacheKey']/'result.blp');data=source.read_bytes()
        if sha(data)!=r['outputSha256']:raise ValueError('Result hash mismatch')
        inspect_blp(data)
        data,_=to_runtime(data,name.lower().startswith('item/texturecomponents/'))
        dest=output/PATCH/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);files[name]=sha(data)
    manifest={'schema':1,'patch':PATCH,'files':files,'gameplayVerified':False,'offlineReviewedKeys':sorted(accepted)}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def validate(package):
    no_links(package)
    no_links(package/'manifest.json')
    m=json.loads((package/'manifest.json').read_text())
    if m['schema']!=1 or m['patch']!=PATCH or not m['files']:raise ValueError('Unsupported manifest')
    for name in m['files']:
        safe_path(name)
        if not name.lower().startswith('item/') or not name.lower().endswith('.blp'):raise ValueError('Non-equipment path')
    if tree(package/PATCH)!=m['files']:raise ValueError('Package contents/hash mismatch')
    for name in m['files']:
        validate_client_blp((package/PATCH/name).read_bytes(),name.lower().startswith('item/texturecomponents/'))
    return m


def conflicts(client, names):
    collisions=[];unknown=[];requested={n.casefold() for n in names}
    for directory in [client/'Data',*(p for p in (client/'Data').iterdir() if p.is_dir() and not p.name.lower().endswith('.mpq'))]:
        no_links(directory)
        for patch in directory.iterdir():
            if not patch.name.lower().endswith('.mpq') or patch.name==PATCH:continue
            no_links(patch)
            if patch.is_dir():
                found={n.casefold() for n in tree(patch,hashes=False)} & requested
                if found:collisions.append({'patch':patch.name,'paths':sorted(found)})
            elif patch.name.lower() not in BASE and not re.fullmatch(r'(?:base|backup|locale|speech|expansion-locale|expansion-speech|lichking-locale|lichking-speech|patch)-[a-z]{4}(?:-[23])?\.mpq',patch.name.lower()):unknown.append(str(patch))
    if collisions or unknown:raise ValueError(f'Overlay priority unresolved: collisions={collisions}, unknown archives={unknown}')
    return 'No overlapping loose overlay assets; relative patch ordering does not affect these paths'


def install(client, package, apply=False):
    no_links(client);no_links(client/'Data')
    if not (client/'Wow.exe').is_file():raise ValueError('Client executable missing')
    m=validate(package);priority=conflicts(client,m['files'])
    dest=no_links(client/'Data'/PATCH)
    if dest.exists():
        if tree(dest)==m['files']:return {'state':'already-installed'}
        raise ValueError('Existing different equipment patch: rollback before replacing')
    result={'state':'preview','files':len(m['files']),'bytes':sum((package/PATCH/n).stat().st_size for n in m['files']),
            'priorityCheck':priority,'gameplayVerified':False}
    if not apply:return result
    stopped()
    base=no_links(client/'DisabledPatches'/'EquipmentBackups');base.mkdir(parents=True,exist_ok=True)
    checkpoint=Path(tempfile.mkdtemp(prefix='install-',dir=base))
    journal={'schema':1,'client':str(client.resolve()),'patch':PATCH,'before':None,'installed':m['files'],'state':'prepared'}
    journal_path=checkpoint/'checkpoint.json';journal_path.write_text(json.dumps(journal,indent=2))
    staging=Path(tempfile.mkdtemp(prefix='.equipment-',dir=client/'Data'))
    try:
        shutil.copytree(package/PATCH,staging,dirs_exist_ok=True)
        if tree(staging)!=m['files']:raise ValueError('Staged hashes changed')
        stopped()
        if dest.exists():raise FileExistsError(dest)
        staging.rename(dest)
        journal['state']='installed';journal_path.write_text(json.dumps(journal,indent=2))
    finally:
        if staging.exists():shutil.rmtree(staging)
    return {**result,'state':'installed','checkpoint':str(journal_path)}


def rollback(client, checkpoint, apply=False):
    no_links(client);no_links(checkpoint)
    journal=json.loads(checkpoint.read_text())
    if journal['schema']!=1 or journal['client']!=str(client.resolve()) or journal['patch']!=PATCH or journal['before'] is not None:
        raise ValueError('Checkpoint/client mismatch')
    dest=no_links(client/'Data'/PATCH)
    if not dest.exists():return {'state':'already-absent'}
    if tree(dest)!=journal['installed']:raise ValueError('Later changes detected; rollback refused')
    if apply:
        stopped()
        backup=no_links(checkpoint.parent/'removed-patch')
        if backup.exists():raise FileExistsError(backup)
        dest.rename(backup)  # Retain the entire removed package for recovery.
    return {'state':'rolled-back' if apply else 'rollback-preview'}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    s=sub.add_parser('prepare');s.add_argument('--workspace',type=Path,required=True);s.add_argument('--output',type=Path,required=True);s.add_argument('--accept',action='append',required=True)
    s=sub.add_parser('install');s.add_argument('--client',type=Path,required=True);s.add_argument('--package',type=Path,required=True);s.add_argument('--apply',action='store_true')
    s=sub.add_parser('rollback');s.add_argument('--client',type=Path,required=True);s.add_argument('--checkpoint',type=Path,required=True);s.add_argument('--apply',action='store_true')
    a=p.parse_args()
    result=prepare(a.workspace,a.output,a.accept) if a.action=='prepare' else install(a.client,a.package,a.apply) if a.action=='install' else rollback(a.client,a.checkpoint,a.apply)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
