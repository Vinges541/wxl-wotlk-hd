"""Explicit, non-overwriting filesystem inputs and output reports."""
import hashlib
import json
from pathlib import Path


def checked_path(value):
    path = Path(value).expanduser().absolute()
    if '..' in path.parts:
        raise ValueError('Parent traversal is not supported')
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError(f'Symlink is not supported; supply a physical path: {item}')
    return path


def read_bytes(value):
    path = checked_path(value)
    if not path.is_file():
        raise ValueError(f'Expected a regular input file: {path}')
    return path.read_bytes()


def fingerprint(value):
    data = read_bytes(value)
    return {'file': Path(value).name, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}


def read_json(value):
    return json.loads(read_bytes(value))


def write_json(value, data):
    path = checked_path(value)
    # The parent must already exist. Never overwrite a reviewed report.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def asset_path(value):
    value = value.replace('\\', '/').lower()
    if (not value or any(p in ('', '.', '..') or p.endswith((' ', '.'))
                         for p in value.split('/'))
            or any(c in value for c in ':*?"<>|')
            or any(ord(c) < 32 or ord(c) > 126 for c in value)):
        raise ValueError('Unsafe virtual asset path')
    if value.endswith(('.mdx', '.mdl')):
        value = value[:-4] + '.m2'
    return value
