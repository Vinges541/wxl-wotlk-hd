"""Build the one creature-table redirect; never touch the client."""
import argparse,hashlib,subprocess,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from wxl_mounts.io import checked_path

SDK_HASH='7421cc82c09382d25a91bf340c197dfd2470212bc761b1dac9fb711218bc37ed'

def build(sdk):
    sdk=checked_path(sdk)
    if hashlib.sha256(checked_path(sdk/'wxl/PluginApi.h').read_bytes()).hexdigest()!=SDK_HASH:
        raise ValueError('Pinned WarcraftXL SDK required')
    source=Path(__file__).resolve().parents[1]/'runtime/creature_redirect.c'
    with tempfile.TemporaryDirectory(prefix='wxl-creatures-') as tmp:
        work=Path(tmp)
        subprocess.run(['clang','--target=i686-pc-windows-msvc','-std=c11','-Oz','-ffreestanding',
                        '-fno-builtin','-fno-stack-protector','-fno-ident','-mno-sse','-mno-sse2',
                        '-g0','-Wall','-Wextra','-Werror','-I',str(sdk),'-c',str(source),
                        '-o',str(work/'redirect.obj')],check=True)
        subprocess.run(['lld-link','/dll','/noentry','/nodefaultlib','/machine:x86','/timestamp:0',
                        '/opt:ref','/opt:icf','/safeseh:no','/out:wxl-modern-mounts.dll','redirect.obj'],cwd=work,check=True)
        return (work/'wxl-modern-mounts.dll').read_bytes()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sdk',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    data=build(a.sdk)
    with checked_path(a.output).open('xb') as f:f.write(data)
    print(hashlib.sha256(data).hexdigest())
