"""Guarded replacement of a small, explicitly reviewed equipment texture set."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from .assets import safe_path, sha
from .batch import write_json
from .client_blp import validate as validate_blp
from .package import PATCH, no_links, stopped, tree


def item_path(value):
    name=safe_path(value)
    if name!=name.lower() or not name.startswith('item/') or not name.endswith('.blp'):
        raise ValueError('Expected canonical equipment BLP path')
    return name


def atomic(path, data):
    path=no_links(path)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name)
        try:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True);raise
    try:os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def validate(client, package):
    client=no_links(client);package=no_links(package)
    if not no_links(client/'Wow.exe').is_file():raise ValueError('Client missing')
    manifest=json.loads(no_links(package/'trial-manifest.json').read_text())
    if manifest.get('schema')!=1 or manifest.get('kind')!='wxl-equipment-trial' or manifest.get('patch')!=PATCH:
        raise ValueError('Unsupported trial manifest')
    rows=manifest['files']
    if not 1<=len(rows)<=128:raise ValueError('Trial must contain 1..128 textures')
    names={item_path(row['path']) for row in rows}
    if len(names)!=len(rows):raise ValueError('Duplicate trial target')
    if tree(package/PATCH)!={row['path']:row['sha256'] for row in rows}:raise ValueError('Trial contents/hash mismatch')
    for row in rows:
        name=row['path'];data=no_links(package/PATCH/name).read_bytes()
        if len(data)!=row['bytes']:raise ValueError('Trial size mismatch')
        validate_blp(data,name.startswith('item/texturecomponents/'))
        if sha(no_links(client/'Data'/PATCH/name).read_bytes())!=row['beforeSha256']:
            raise ValueError('Client changed since comparison: '+name)
    return rows


def install(client,package,apply=False):
    rows=validate(client,package)
    report={'state':'preview','files':len(rows),'bytes':sum(r['bytes'] for r in rows),'gameplayVerified':False}
    if not apply:return report
    stopped()
    parent=no_links(client/'DisabledPatches/EquipmentBackups');parent.mkdir(parents=True,exist_ok=True)
    checkpoint=Path(tempfile.mkdtemp(prefix='trial-',dir=parent))
    for row in rows:
        data=no_links(client/'Data'/PATCH/row['path']).read_bytes()
        if sha(data)!=row['beforeSha256']:raise ValueError('Client changed during backup')
        backup=checkpoint/'before'/row['path'];backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(data)
        if sha(backup.read_bytes())!=row['beforeSha256']:raise ValueError('Backup verification failed')
    journal={'schema':1,'kind':'wxl-equipment-trial','client':str(client.resolve()),'patch':PATCH,'files':rows,'state':'prepared'}
    write_json(checkpoint/'checkpoint.json',journal)
    for row in rows:
        stopped()
        target=no_links(client/'Data'/PATCH/row['path']);data=no_links(package/PATCH/row['path']).read_bytes()
        if sha(data)!=row['sha256'] or sha(target.read_bytes())!=row['beforeSha256']:
            raise ValueError('Concurrent change; retained checkpoint: '+str(checkpoint))
        atomic(target,data)
        if sha(target.read_bytes())!=row['sha256']:raise ValueError('Trial read-back failed')
    journal['state']='installed';write_json(checkpoint/'checkpoint.json',journal)
    return {**report,'state':'installed','checkpoint':str(checkpoint/'checkpoint.json')}


def rollback(client,checkpoint,apply=False):
    client=no_links(client);checkpoint=no_links(checkpoint)
    root=no_links(client/'DisabledPatches/EquipmentBackups')
    if not checkpoint.resolve().is_relative_to(root.resolve()):raise ValueError('Checkpoint outside client')
    journal=json.loads(checkpoint.read_text())
    if journal.get('schema')!=1 or journal.get('kind')!='wxl-equipment-trial' or journal.get('patch')!=PATCH or journal.get('client')!=str(client.resolve()):
        raise ValueError('Trial checkpoint mismatch')
    rows=journal['files'];backups={}
    if not 1<=len(rows)<=128 or len({item_path(r['path']) for r in rows})!=len(rows):raise ValueError('Invalid trial checkpoint targets')
    for row in rows:
        name=item_path(row['path']);backup=no_links(checkpoint.parent/'before'/name).read_bytes()
        if sha(backup)!=row['beforeSha256']:raise ValueError('Backup changed')
        if sha(no_links(client/'Data'/PATCH/name).read_bytes()) not in (row['sha256'],row['beforeSha256']):
            raise ValueError('Later client edit; rollback refused')
        backups[name]=backup
    if apply:
        for row in rows:
            stopped();target=no_links(client/'Data'/PATCH/row['path'])
            if sha(target.read_bytes()) not in (row['sha256'],row['beforeSha256']):raise ValueError('Concurrent client edit')
            atomic(target,backups[row['path']])
            if sha(target.read_bytes())!=row['beforeSha256']:raise ValueError('Rollback read-back failed')
        journal['state']='restored';write_json(checkpoint,journal)
    return {'state':'restored' if apply else 'rollback-preview','files':len(rows)}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--client',type=Path,required=True)
    group=p.add_mutually_exclusive_group(required=True);group.add_argument('--package',type=Path);group.add_argument('--rollback',type=Path)
    p.add_argument('--apply',action='store_true');a=p.parse_args()
    print(json.dumps(install(a.client,a.package,a.apply) if a.package else rollback(a.client,a.rollback,a.apply),indent=2))

if __name__=='__main__':main()
