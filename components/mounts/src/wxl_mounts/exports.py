"""Resolve only explicit raw-export FileDataID manifests, with byte-identical deduplication."""
from pathlib import Path
import os
from .io import checked_path, read_json
from .packing import digest

EXTENSIONS = {'.m2','.skin','.anim','.blp','.skel','.bone'}
TYPES = {'M2':'.m2','SKIN':'.skin','LOD_SKIN':'.skin','ANIM':'.anim',
         'BLP':'.blp','SKEL':'.skel','BONE':'.bone'}

class RawIndex:
    def __init__(self, roots, build_config):
        roots = [checked_path(p) for p in roots]
        if not roots: raise ValueError('At least one raw export required')
        self.root = Path(os.path.commonpath(roots))
        self.manifest_paths, self.files, self.models, self.provenance = [], {}, {}, []
        for root in roots:
            status = read_json(root/'status.json')
            if (status.get('build',{}).get('BuildConfig') != build_config
                    or status['build'].get('Product') != 'wow'):
                raise ValueError('Raw export has another donor')
            if status.get('state') not in ('complete','partial'):
                raise ValueError('Raw export is not finished')
            for record in status['models']:
                if record.get('state') != 'complete': continue
                fid = record['fileDataId']; manifest = checked_path(root/f'{fid}.files.manifest.json')
                self.manifest_paths.append(manifest)
                entries = read_json(manifest)['files']
                if not any(e['type']=='M2' and e['fileDataID']==fid for e in entries):
                    raise ValueError('Manifest lacks its model')
                for entry in entries:
                    path = Path(entry['file'])
                    if not path.is_absolute(): path = root/path
                    path = checked_path(path)
                    if (not path.is_relative_to(root) or path.suffix.lower() not in EXTENSIONS
                            or TYPES.get(entry['type']) != path.suffix.lower()):
                        raise ValueError('Raw manifest escapes export or names a non-asset')
                    if entry.get('sha256') and digest(path) != entry['sha256']:
                        raise ValueError('Raw asset receipt hash changed')
                    self.add(entry['fileDataID'], path)
                if self.files[fid].suffix.lower() != '.m2':raise ValueError('Model ID refers to another asset type')
                self.models[f'{fid}.m2'] = self.files[fid]
            for record in status.get('files',[]):
                if record.get('state') == 'complete':
                    fid=record['fileDataId']; path=checked_path(root/'textures'/f'{fid}.blp')
                    if record.get('sha256') and digest(path)!=record['sha256']:raise ValueError('Texture receipt hash changed')
                    self.add(fid,path)
            self.provenance.append({'statusSha256':digest(root/'status.json'),
                                    'buildConfig':build_config,'bundleSha256':status.get('bundleSha256')})
    def add(self, fid, path):
        if type(fid) is not int or fid<=0 or not path.is_file(): raise ValueError('Invalid raw FileDataID')
        if fid in self.files and digest(self.files[fid]) != digest(path):
            raise ValueError(f'Conflicting bytes for FileDataID {fid}')
        self.files[fid]=path
    def resolve_fdid(self, fid): return self.files.get(fid)
    def resolve_path(self, name): return self.models.get(name)
