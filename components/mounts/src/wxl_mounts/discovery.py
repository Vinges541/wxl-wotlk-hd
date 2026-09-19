"""Table-ID joins and explicit family searches produce candidates, not approvals."""
import csv
import fnmatch
import io

from .io import asset_path, checked_path, fingerprint, read_bytes, read_json


def index_rows(path):
    rows = read_json(path)
    if not isinstance(rows, list):
        raise ValueError('Expected wow.export JSON row array')
    result = {}
    for row in rows:
        ident = row.get('ID')
        if type(ident) is not int or ident <= 0 or ident in result:
            raise ValueError('Invalid or duplicate Retail table ID')
        result[ident] = row
    return result


def read_listfile(path):
    result = {}
    for row in csv.reader(io.StringIO(read_bytes(path).decode('utf-8-sig')), delimiter=';'):
        if not row:
            continue
        if len(row) != 2:
            raise ValueError('Expected listfile rows: FileDataID;path')
        ident, name = int(row[0]), asset_path(row[1])
        if ident <= 0 or (ident in result and result[ident] != name):
            raise ValueError('Invalid or conflicting FileDataID')
        result[ident] = name
    return result


def discover(inventory_path, retail_dir, listfile_path, profile_path, families_path):
    original = read_json(inventory_path)
    if (original.get('schemaVersion') != 1 or original.get('kind') != 'mount-inventory'
            or original.get('clientBuild') != 12340):
        raise ValueError('Expected build-12340 mount inventory')
    profile = read_json(profile_path)
    retail = checked_path(retail_dir)
    build = read_json(retail / 'build.json')
    expected = profile['retail']
    for key, actual in [('BuildConfig', build.get('BuildConfig')),
                        ('product', build.get('Product')),
                        ('version', build.get('VersionsName'))]:
        if actual != expected[key]:
            raise ValueError(f'Retail {key} differs from the pinned donor')
    displays = index_rows(retail / 'CreatureDisplayInfo.json')
    models = index_rows(retail / 'CreatureModelData.json')
    names = read_listfile(listfile_path)
    families = read_json(families_path)['families']
    family_candidates = []
    for family in families:
        legacy = [row['displayId'] for row in original['displays'] if any(
            fnmatch.fnmatchcase(row['modelPath'], p) for p in family['legacyPatterns'])]
        candidates = [{'fileDataId': ident, 'path': name}
                      for ident, name in sorted(names.items())
                      if name.endswith('.m2') and any(fnmatch.fnmatchcase(name, p)
                                                      for p in family['retailPatterns'])]
        family_candidates.append({'family': family['id'], 'legacyDisplayIds': legacy,
                                  'candidates': candidates,
                                  'status': 'filename-candidates-unverified'})
    comparisons = []
    for old in original['displays']:
        row = displays.get(old['displayId'])
        target = models.get(row['ModelID']) if row else None
        file_id = target.get('FileDataID', 0) if target else 0
        name = names.get(file_id)
        if not row:
            status = 'missing-retail-display'
        elif not file_id:
            status = 'missing-retail-model'
        elif not name:
            status = 'unnamed-retail-model'
        else:
            status = ('same-path-unchecked' if old['modelPath'] == name
                      else 'different-path-candidate')
        comparisons.append({'displayId': old['displayId'], 'legacyPath': old['modelPath'],
                            'retailModelId': row['ModelID'] if row else None,
                            'retailFileDataId': file_id, 'retailPath': name,
                            'retailTextureFileDataIds': row.get('TextureVariationFileDataID', [])
                                if row else [],
                            'status': status, 'approved': False})
    counts = {status: sum(c['status'] == status for c in comparisons)
              for status in sorted({c['status'] for c in comparisons})}
    inputs = {'inventory': inventory_path, 'profile': profile_path, 'listfile': listfile_path,
              'families': families_path, 'build': retail / 'build.json',
              'retailDisplays': retail / 'CreatureDisplayInfo.json',
              'retailModels': retail / 'CreatureModelData.json'}
    return {'schemaVersion': 1, 'kind': 'mount-discovery', 'retail': expected,
            'evidence': 'offline-metadata-only',
            'limitations': ['Table provenance is declared by the export build.json, not CASC-reverified.',
                            'Matching IDs and names do not establish visual equivalence or compatibility.',
                            'Same-path assets may have changed bytes; no raw-model comparison was done.',
                            'Listfile membership does not establish availability in the pinned donor.'],
            'sources': {key: fingerprint(path) for key, path in inputs.items()},
            'summary': {'comparedDisplays': len(comparisons), 'statuses': counts,
                        'familyCandidates': sum(len(f['candidates']) for f in family_candidates),
                        'approvedReplacements': 0},
            'comparisons': comparisons, 'families': family_candidates}
