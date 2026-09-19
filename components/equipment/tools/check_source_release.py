"""Reject private/generated content in tracked source and built distributions."""
import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import zipfile

FORBIDDEN = {'.blp', '.m2', '.skin', '.anim', '.dbc', '.db2', '.mpq', '.exe',
             '.dll', '.dylib', '.pth', '.safetensors', '.npz', '.npy', '.png',
             '.jpg', '.jpeg', '.webp', '.dds', '.tga', '.log'}
PRIVATE = re.compile(rb'/(?:Users|home)/[^/\s]+/|/var/' + rb'folders/|/private/' + rb'tmp/')
SECRET = re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def check(name, data):
    parts = PurePosixPath(name).parts
    if any(p in ('_local', '.git', '.env') or p.startswith('.venv') for p in parts):
        raise ValueError('Private path in release: ' + name)
    if PurePosixPath(name).suffix.lower() in FORBIDDEN or b'\0' in data:
        raise ValueError('Binary/generated file in release: ' + name)
    if len(data) > 1024 * 1024:
        raise ValueError('Unexpected large source file: ' + name)
    if PRIVATE.search(data) or SECRET.search(data):
        raise ValueError('Private path or credential pattern in: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path)
    args = parser.parse_args()
    if args.dist:
        artifacts = list(args.dist.glob('*.whl')) + list(args.dist.glob('*.tar.gz'))
        if not artifacts:
            raise ValueError('No distribution artifacts found')
        for artifact in artifacts:
            if artifact.suffix == '.whl':
                with zipfile.ZipFile(artifact) as archive:
                    for name in archive.namelist():
                        if not name.endswith('/'): check(name, archive.read(name))
            else:
                with tarfile.open(artifact) as archive:
                    for item in archive.getmembers():
                        if item.issym() or item.islnk(): raise ValueError('Archive link refused')
                        if item.isfile(): check(item.name, archive.extractfile(item).read())
        print(f'Checked {len(artifacts)} source-only distributions')
    else:
        names = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
        files = [Path(n) for n in names if n and Path(n).is_file()]
        for path in files:
            if path.is_symlink(): raise ValueError('Source symlink refused')
            check(path.as_posix(), path.read_bytes())
        print(f'Checked {len(files)} tracked source files')


if __name__ == '__main__': main()
