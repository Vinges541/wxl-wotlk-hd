"""Mount spell -> creature -> display -> model, without modifying game data."""
import csv
import io
import math
from collections import defaultdict

from .dbc import DBC, LAYOUTS, as_float
from .io import asset_path, checked_path, fingerprint, read_bytes


def server_models(path):
    rows = list(csv.DictReader(io.StringIO(read_bytes(path).decode('utf-8-sig'))))
    required = {'CreatureID', 'CreatureDisplayID', 'DisplayScale', 'Probability',
                'DisplayID_Other_Gender'}
    if not rows or not required <= rows[0].keys():
        raise ValueError('Creature CSV needs the columns documented in docs/BUILD.md')
    result = defaultdict(list)
    for row in rows:
        entry, display, other = (int(row[k]) for k in
                                ('CreatureID', 'CreatureDisplayID', 'DisplayID_Other_Gender'))
        scale, probability = float(row['DisplayScale']), float(row['Probability'])
        if (entry <= 0 or display < 0 or other < 0 or not math.isfinite(scale)
                or scale <= 0 or not math.isfinite(probability) or probability < 0):
            raise ValueError('Invalid server model row')
        result[entry].append({'displayId': display, 'otherGenderDisplayId': other,
                              'serverScale': scale, 'probability': probability})
    return result


def inventory(dbc_dir, creature_csv=None):
    root = checked_path(dbc_dir)
    tables = {name: DBC(read_bytes(root / (name + '.dbc')), name) for name in LAYOUTS}
    spell, display, model = (tables[name] for name in LAYOUTS)
    mapping = server_models(creature_csv) if creature_csv else {}
    sources = {name: fingerprint(root / (name + '.dbc')) for name in LAYOUTS}
    if creature_csv:
        sources['creatureModels'] = fingerprint(creature_csv)
    spells = []
    for row in spell.rows.values():
        for slot in range(3):
            if row[71 + slot] == 0 or row[95 + slot] != 78:
                continue
            # Names are labels only; localized strings do not drive identification.
            names = [spell.string(offset) for offset in row[136:152]]
            entry = row[110 + slot]
            spells.append({'spellId': row[0], 'name': next((n for n in names if n), ''),
                           'effectSlot': slot, 'creatureEntry': entry,
                           'resolution': 'mapped' if mapping.get(entry) else 'unresolved',
                           'serverModels': mapping.get(entry, [])})
    mounted_entries = {s['creatureEntry'] for s in spells}
    selected = defaultdict(set)
    references = defaultdict(set)
    for entry, rows in mapping.items():
        for row in rows:
            for key in ('displayId', 'otherGenderDisplayId'):
                if row[key]:
                    references[row[key]].add(entry)
                    if entry in mounted_entries:
                        selected[row[key]].add(entry)
    paths = {row[0]: asset_path(model.string(row[2]))
             for row in model.rows.values() if row[2]}
    path_displays = defaultdict(list)
    for row in display.rows.values():
        if row[1] in paths:
            path_displays[paths[row[1]]].append(row[0])
    records, issues = [], []
    for ident in sorted(selected):
        row = display.rows.get(ident)
        if row is None or row[1] not in paths:
            issues.append({'displayId': ident, 'reason': 'missing-display-or-model'})
            continue
        model_row = model.rows[row[1]]
        path = paths[row[1]]
        shared_displays = sorted(path_displays[path])
        shared_entries = sorted({entry for did in shared_displays for entry in references[did]}
                                - mounted_entries)
        floats = {'displayScale': as_float(row[4]), 'modelScale': as_float(model_row[4]),
                  'mountHeight': as_float(model_row[16])}
        if not all(math.isfinite(v) for v in floats.values()):
            raise ValueError(f'Nonfinite model values: {ident}')
        records.append({'displayId': ident, 'modelId': row[1], 'modelPath': path,
                        'creatureEntries': sorted(selected[ident]), **floats,
                        'textureVariations': [display.string(v) for v in row[6:9]],
                        'sharedDisplayIds': shared_displays,
                        'otherCreatureEntries': shared_entries,
                        'replacementScope': 'shared-model-review-required'
                            if len(shared_displays) > 1 or shared_entries else 'review-required'})
    unresolved = sum(s['resolution'] == 'unresolved' for s in spells)
    return {'schemaVersion': 1, 'kind': 'mount-inventory', 'clientBuild': 12340,
            'evidence': 'offline-input-snapshot', 'sources': sources,
            'coverage': {'mountedAuraOnly': True, 'dynamicServerRulesEvaluated': False,
                         'liveServerVerified': False, 'npcReferencesExhaustive': False},
            'summary': {'mountSpells': len({s['spellId'] for s in spells}),
                        'mountEffects': len(spells), 'creatureEntries': len(mounted_entries),
                        'unresolvedEffects': unresolved, 'resolvedDisplays': len(records),
                        'modelPaths': len({r['modelPath'] for r in records}),
                        'missingDisplayOrModel': len(issues)},
            'spells': sorted(spells, key=lambda s: (s['spellId'], s['effectSlot'])),
            'displays': records, 'issues': issues}
