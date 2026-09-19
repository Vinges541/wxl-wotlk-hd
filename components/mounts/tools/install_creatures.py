"""Guarded no-backup installation of one combined creature archive and one redirect."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from creature_package import verify,ARCHIVE,DLL_PATH,OLD_ARCHIVE,OLD_DLL,OLD_FILES
from wxl_mounts.io import checked_path,read_json
from wxl_mounts.packing import digest,read_va
from wxl_mounts.mpq import Reader
from wxl_mounts.tables import TABLES,NAMESPACE

RUNTIME={
 'Wow.exe':'86c242044eddc3cafffa70ca6ee373929048245bccb1b4bb25d6f904e81a5f26',
 'WarcraftXL.dll':'0723d3b115d60ad8aca27bc5caaff8dffa113efb491251d9db0fa4e22426f09d',
 'Extensions/wxl-modern-m2/wxl-modern-m2.dll':'76947b794d899280da55a639d6f6207c6e47be8d59904acdb61effcb55081d1d',
 'Extensions/wxl-modern-races/wxl-modern-races.dll':'a0b853e41b7896733cd1447056309554cd58627ba933e4c304589370eea24185',
}


def require_wow_closed():
    try:
        result=subprocess.run(['ps','-ax','-o','args='],capture_output=True,text=True,timeout=10,check=True)
    except (OSError,subprocess.SubprocessError) as e:raise ValueError('Cannot check processes; no client writes allowed') from e
    if re.search(r'''(?:^|[/\\\s"'])Wow(?:-64)?\.exe(?=$|[\s"'])''',result.stdout,re.I|re.M):
        raise ValueError('Close WoW before changing active patches')
    # Process command lines are never written to reports or stdout.


def check_runtime(client):
    for name,checksum in RUNTIME.items():
        if digest(checked_path(client/name))!=checksum:raise ValueError('Runtime profile changed: '+name)
    exe=(client/'Wow.exe').read_bytes()
    for va,value in [(0x9e2700,b'patch-%s-*.MPQ\0'),(0x9e2710,b'patch-*.MPQ\0')]:
        if read_va(exe,va,len(value))!=value:raise ValueError('Named patch loading is absent')


def originals(client,library):
    data=checked_path(client/'Data')
    config=checked_path(client/'WTF/Config.wtf')
    matches=re.findall(r'^SET\s+locale\s+"([a-z]{2}[A-Z]{2})"\s*$',config.read_text() if config.is_file() else '',re.M)
    locales=[p.name for p in data.iterdir() if re.fullmatch('[a-z]{2}[A-Z]{2}',p.name) and p.is_dir()]
    if len(matches)==1:locale=matches[0]
    elif not matches and len(locales)==1:locale=locales[0]
    else:raise ValueError('Cannot determine the active client locale')
    folder=checked_path(data/locale)
    if not folder.is_dir():raise ValueError('Configured locale data is absent')
    localized=[f'patch-{locale}-3.MPQ',f'patch-{locale}-2.MPQ',f'patch-{locale}.MPQ',
               f'lichking-locale-{locale}.MPQ',f'expansion-locale-{locale}.MPQ',f'locale-{locale}.MPQ']
    names=['patch-3.MPQ','patch-2.MPQ','patch.MPQ','lichking.MPQ','expansion.MPQ','common-2.MPQ','common.MPQ']
    archives=[checked_path(folder/n) for n in localized if (folder/n).exists()]
    archives += [checked_path(data/n) for n in names if (data/n).exists()]
    # Creature tables can live in locale archives even though their records are not translated.
    reader=Reader(library,archives)
    try:return {n:reader.read('DBFilesClient\\'+n)[0] for n in TABLES}
    finally:reader.close()


def check_overlays(client,library,manifest):
    data=checked_path(client/'Data');names={r['path'].casefold() for r in manifest['assets']}
    names|={f'DBFilesClient/{n}'.casefold() for n in TABLES}
    names|={f'WXL/DruidForms/DBFilesClient/{n}'.casefold() for n in TABLES}
    folders=[data]+[checked_path(p) for p in data.iterdir() if re.fullmatch('[a-z]{2}[A-Z]{2}',p.name) and p.is_dir()]
    preserved={}
    for folder in folders:
        stock={'patch.mpq','patch-2.mpq','patch-3.mpq'} if folder==data else {f'patch-{folder.name.lower()}{suffix}.mpq' for suffix in ('','-2','-3')}
        for p in folder.iterdir():
            lower=p.name.casefold()
            if not lower.startswith('patch') or not lower.endswith('.mpq') or lower in stock:continue
            checked_path(p)
            if folder==data and lower in {Path(ARCHIVE).name.casefold(),Path(OLD_ARCHIVE).name.casefold()}:continue
            if p.is_dir():
                members=set()
                for f in p.rglob('*'):
                    checked_path(f)
                    if f.is_file():members.add(f.relative_to(p).as_posix().casefold());preserved[f]=digest(f)
            elif p.is_file():
                reader=Reader(library,[p])
                try:members={n.casefold().replace('\\','/') for n in reader.read('(listfile)')[0].decode('ascii').splitlines()}
                finally:reader.close()
                preserved[p]=digest(p)
            else:raise ValueError('Unsupported patch storage')
            if names & members:raise ValueError('Conflicting creature asset/table overlay: '+p.name)
    return preserved


def configuration_snapshot(client):
    result={}
    excluded={client/DLL_PATH,client/OLD_DLL}
    for folder in (client,client/'WTF',client/'Extensions'):
        if not folder.exists():continue
        paths=folder.iterdir() if folder==client else folder.rglob('*')
        for p in paths:
            checked_path(p)
            if p.is_file() and p not in excluded and not p.name.startswith('.wxl-creatures-'):
                result[p]=digest(p)
    return result


def aggregate(snapshot,client):
    h=hashlib.sha256()
    for p,value in sorted(snapshot.items()):h.update(p.relative_to(client).as_posix().encode()+b'\0'+value.encode()+b'\n')
    return h.hexdigest()


def save_journal(path,value):
    data=(json.dumps(value,indent=2)+'\n').encode()
    with path.open('wb') as out:out.write(data);out.flush();os.fsync(out.fileno())


def install(package,client,library,apply=False,no_backup=False,report=None):
    client,package=checked_path(client),checked_path(package)
    if client==package or client in package.parents or package in client.parents:raise ValueError('Package must be outside the physical client')
    check_runtime(client)
    manifest=verify(package,library,originals(client,library))
    preserved_patches=check_overlays(client,library,manifest)
    new={r['path']:r for r in manifest['files']}
    for name,row in new.items():
        p=checked_path(client/name)
        if p.exists() and (not p.is_file() or digest(p)!=row['sha256']):raise ValueError('Unknown existing destination: '+name)
    for name,checksum in OLD_FILES.items():
        p=checked_path(client/name)
        if p.exists() and (not p.is_file() or digest(p)!=checksum):raise ValueError('Old druid pair changed: '+name)
    if any((client/n).exists() for n in OLD_FILES) and not manifest['druids']:
        raise ValueError('Existing druid forms must be present in the combined package')
    changes={'add':[n for n in new if not (client/n).exists()], 'remove':[n for n in OLD_FILES if (client/n).exists()]}
    if not apply:return {'apply':False,'changes':changes,'packageVerified':True,'gameplayVerified':False}
    if not no_backup or report is None:raise ValueError('Explicit --no-backup and private report required')
    report=checked_path(report)
    if report.exists() or not report.parent.is_dir() or report==client or client in report.parents:raise ValueError('Use a new report outside the client')
    require_wow_closed();check_runtime(client)
    preserved={**preserved_patches,**configuration_snapshot(client)}
    journal={'kind':'wxl-creature-install','state':'preflight','manifestSha256':digest(package/'release-manifest.json'),
             'changes':changes,'operations':[],'backupsCreated':False,'gameplayVerified':False,
             'preservedBefore':aggregate(preserved,client)}
    with report.open('x') as f:json.dump(journal,f)
    staged={}
    try:
        # Stage both verified files under names the client does not scan as MPQ/DLL.
        for name in changes['add']:
            row=new[name];source=checked_path(package/name);target=checked_path(client/name)
            if digest(source)!=row['sha256']:raise ValueError('Package changed during installation')
            target.parent.mkdir(parents=True,exist_ok=True)
            temp=checked_path(target.parent/f".wxl-creatures-{row['sha256']}.pending")
            if temp.exists():
                if not temp.is_file() or digest(temp)!=row['sha256']:raise ValueError('Unknown interrupted staging file')
            else:
                with source.open('rb') as inp,temp.open('xb') as out:shutil.copyfileobj(inp,out);out.flush();os.fsync(out.fileno())
            if digest(temp)!=row['sha256']:raise ValueError('Staged readback mismatch')
            staged[name]=temp
        journal['state']='staged';save_journal(report,journal)
        def activate(name):
            if name not in staged:return
            require_wow_closed();target=checked_path(client/name);temp=checked_path(staged[name])
            if digest(temp)!=new[name]['sha256']:raise ValueError('Staged file changed')
            # Hard-link publication is atomic and refuses to overwrite a raced destination.
            os.link(temp,target);temp.unlink()
            if digest(target)!=new[name]['sha256']:raise ValueError('Installed readback mismatch')
            journal['operations'].append({'installed':name,'sha256':new[name]['sha256']});save_journal(report,journal)
        def remove_old(name):
            p=checked_path(client/name)
            if not p.exists():return
            require_wow_closed()
            if digest(p)!=OLD_FILES[name]:raise ValueError('Old druid file changed during install')
            p.unlink();journal['operations'].append({'removed':name,'sha256':OLD_FILES[name]});save_journal(report,journal)
        activate(ARCHIVE)
        # There is never a point with both creature redirect DLLs active.
        remove_old(OLD_DLL)
        activate(DLL_PATH)
        for name,row in new.items():
            if digest(checked_path(client/name))!=row['sha256']:raise ValueError('Combined pair is incomplete')
        remove_old(OLD_ARCHIVE)
        old_dir=checked_path((client/OLD_DLL).parent)
        if old_dir.is_dir() and not any(old_dir.iterdir()):old_dir.rmdir()
        if any(not p.is_file() or digest(p)!=value for p,value in preserved.items()):raise ValueError('Unrelated client files changed')
        journal['preservedAfter']=aggregate(preserved,client);journal['state']='complete';journal['installed']=manifest['files'];save_journal(report,journal)
        return journal
    except Exception as e:
        journal['state']='interrupted';journal['error']=type(e).__name__+': '+str(e);save_journal(report,journal)
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--client',type=Path,required=True);p.add_argument('--stormlib',type=Path,required=True)
    p.add_argument('--apply',action='store_true');p.add_argument('--no-backup',action='store_true');p.add_argument('--report',type=Path)
    a=p.parse_args();print(json.dumps(install(a.package,a.client,a.stormlib,a.apply,a.no_backup,a.report),indent=2))
