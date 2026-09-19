"""Prepare a private wow.export app and verified cache copy; never edit the supplied app."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app',type=Path,required=True);p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    source=a.app/'Contents/Resources/app.nw'
    if json.loads((source/'package.json').read_text())['version']!='0.2.19':raise ValueError('Expected wow.export 0.2.19')
    original=(source/'src/app.js').read_bytes();text=original.decode()
    first,rest=text.split('\n',1)
    if first.startswith('require(') and 'doh_preload.cjs' in first:text=rest
    marker='  modules.source_select.setActive();'
    if text.count(marker)!=1:raise ValueError('Unsupported bootstrap')
    text=text[:text.rindex(marker)]+marker+'''
  if (process.env.WXL_EQUIPMENT_EXPORT) {
    await require(ADAPTER).run({core, CASCRemote: require_casc_source_remote(), db2: require_db2()});
    nw.App.quit();
  }
})();
'''.replace('ADAPTER',json.dumps(str(Path(__file__).with_name('export-equipment.cjs').resolve())))
    a.output.mkdir(parents=True)
    dest=a.output/'EquipmentExport.app';shutil.copytree(a.app,dest,symlinks=True)
    (dest/'Contents/Resources/app.nw/src/app.js').write_text(text)
    cache=a.output/'profile/Default/casc';shutil.copytree(a.cache,cache)
    integrity=json.loads((cache/'cacheintegrity').read_text());mapped={}
    for name,digest in integrity.items():
        if '/casc/' not in name:continue
        relative=name.split('/casc/',1)[1]
        if '..' in Path(relative).parts:raise ValueError('Unsafe cache entry')
        local=cache/relative
        if local.is_file() and hashlib.sha1(local.read_bytes()).hexdigest()==digest:mapped[str(local.resolve())]=digest
    (cache/'cacheintegrity').write_text(json.dumps(mapped))
    (a.output/'preparation.json').write_text(json.dumps({'version':'0.2.19','sourceAppJsSha256':hashlib.sha256(original).hexdigest(),'verifiedCacheEntries':len(mapped)},indent=2))
    print(dest.resolve())

if __name__=='__main__':main()
