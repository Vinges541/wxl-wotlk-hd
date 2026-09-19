import csv
import json
from pathlib import Path
import struct
import tempfile
import unittest

from wxl_mounts.dbc import DBC, LAYOUTS
from wxl_mounts.discovery import discover, read_listfile
from wxl_mounts.inventory import inventory
from wxl_mounts.io import asset_path, checked_path, write_json


def dbc_bytes(name, rows, strings=b'\0'):
    fields = LAYOUTS[name]
    return (struct.pack('<4s4I', b'WDBC', len(rows), fields, fields * 4, len(strings))
            + b''.join(struct.pack(f'<{fields}I', *r) for r in rows) + strings)


def row(name, values):
    result = [0] * LAYOUTS[name]
    for key, value in values.items():
        result[key] = value
    return result


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # macOS's /var and /tmp are system aliases; use the physical test root.
        self.root = Path(self.temp.name).resolve()
        self.dbc = self.root / 'dbc'
        self.dbc.mkdir()
        self.mapping = self.root / 'models.csv'
        self.write_mapping([
            [700, 10, 1.0, 1.0, 11], [900, 12, 1.0, 1.0, 0]])
        self.write_table('Spell', [row('Spell', {
            0: 42, 72: 6, 96: 78, 111: 700, 136: 1})], b'\0Test mount\0')
        self.write_table('CreatureDisplayInfo', [
            row('CreatureDisplayInfo', {0: ident, 1: model, 4: 0x3f800000, 6: 1})
            for ident, model in [(10, 100), (11, 100), (12, 101)]], b'\0Blue\0')
        self.write_table('CreatureModelData', [
            row('CreatureModelData', {0: ident, 2: 1, 4: 0x3f800000, 16: 0x3fc00000})
            for ident in (100, 101)], b'\0Creature\\KodoBeast\\RidingKodo.MDX\0')

    def tearDown(self):
        self.temp.cleanup()

    def write_table(self, name, rows, strings=b'\0'):
        (self.dbc / (name + '.dbc')).write_bytes(dbc_bytes(name, rows, strings))

    def write_mapping(self, rows):
        with self.mapping.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['CreatureID', 'CreatureDisplayID', 'DisplayScale',
                             'Probability', 'DisplayID_Other_Gender'])
            writer.writerows(rows)

    def test_entry_is_not_display_id_and_gender_is_included(self):
        result = inventory(self.dbc, self.mapping)
        self.assertEqual(result['summary']['resolvedDisplays'], 2)
        self.assertEqual([r['displayId'] for r in result['displays']], [10, 11])
        self.assertEqual(result['spells'][0]['effectSlot'], 1)
        self.assertEqual(result['displays'][0]['modelPath'],
                         'creature/kodobeast/ridingkodo.m2')
        self.assertEqual(result['displays'][0]['mountHeight'], 1.5)

    def test_shared_path_across_model_ids_reports_npc(self):
        result = inventory(self.dbc, self.mapping)
        self.assertEqual(result['displays'][0]['sharedDisplayIds'], [10, 11, 12])
        self.assertEqual(result['displays'][0]['otherCreatureEntries'], [900])
        self.assertFalse(result['coverage']['npcReferencesExhaustive'])

    def test_missing_mapping_stays_unresolved(self):
        result = inventory(self.dbc)
        self.assertEqual(result['summary']['unresolvedEffects'], 1)
        self.assertEqual(result['displays'], [])

    def test_multiple_alternatives_and_missing_display(self):
        self.write_mapping([[700, 10, 1, 1, 11], [700, 999, 1, 0, 0]])
        result = inventory(self.dbc, self.mapping)
        self.assertEqual(result['summary']['missingDisplayOrModel'], 1)
        self.assertEqual(len(result['spells'][0]['serverModels']), 2)

    def test_empty_effect_with_stale_aura_is_ignored(self):
        self.write_table('Spell', [row('Spell', {0: 42, 95: 78, 110: 700})])
        self.assertEqual(inventory(self.dbc, self.mapping)['summary']['mountSpells'], 0)

    def test_invalid_server_scale_rejected(self):
        self.write_mapping([[700, 10, 'nan', 1, 0]])
        with self.assertRaisesRegex(ValueError, 'server model'):
            inventory(self.dbc, self.mapping)

    def make_discovery_inputs(self):
        inv = self.root / 'inventory.json'
        write_json(inv, inventory(self.dbc, self.mapping))
        retail = self.root / 'retail'
        retail.mkdir()
        write_json(retail / 'build.json', {
            'BuildConfig': 'a' * 32, 'Product': 'wow', 'VersionsName': 'test'})
        write_json(retail / 'CreatureDisplayInfo.json', [
            {'ID': 10, 'ModelID': 300, 'TextureVariationFileDataID': [800]},
            {'ID': 11, 'ModelID': 301, 'TextureVariationFileDataID': [801]}])
        write_json(retail / 'CreatureModelData.json', [
            {'ID': 300, 'FileDataID': 500}, {'ID': 301, 'FileDataID': 501}])
        listfile = self.root / 'listfile.csv'
        listfile.write_text('500;Creature/KodoBeast2Mount/KodoBeast2Mount.m2\n'
                            '501;Creature/KodoBeast/RidingKodo.m2\n')
        profile = self.root / 'profile.json'
        write_json(profile, {'retail': {
            'BuildConfig': 'a' * 32, 'product': 'wow', 'version': 'test'}})
        families = self.root / 'families.json'
        write_json(families, {'families': [{'id': 'kodo',
            'legacyPatterns': ['creature/kodobeast/*.m2'],
            'retailPatterns': ['creature/kodobeast2mount/*.m2']}]})
        return inv, retail, listfile, profile, families

    def test_discovery_does_not_approve_id_or_filename_matches(self):
        result = discover(*self.make_discovery_inputs())
        self.assertEqual([r['status'] for r in result['comparisons']],
                         ['different-path-candidate', 'same-path-unchecked'])
        self.assertFalse(any(r['approved'] for r in result['comparisons']))
        self.assertEqual(result['families'][0]['candidates'][0]['fileDataId'], 500)
        self.assertEqual(result['summary']['approvedReplacements'], 0)

    def test_wrong_build_cannot_be_substituted(self):
        args = self.make_discovery_inputs()
        (args[1] / 'build.json').write_text(json.dumps({
            'BuildConfig': 'b' * 32, 'Product': 'wow', 'VersionsName': 'test'}))
        with self.assertRaisesRegex(ValueError, 'pinned donor'):
            discover(*args)

    def test_missing_retail_record_reported(self):
        args = self.make_discovery_inputs()
        (args[1] / 'CreatureDisplayInfo.json').write_text('[]')
        result = discover(*args)
        self.assertEqual(result['comparisons'][0]['status'], 'missing-retail-display')

    def test_conflicting_file_id_rejected(self):
        path = self.root / 'list.csv'
        path.write_text('500;creature/a.m2\n500;creature/b.m2\n')
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            read_listfile(path)

    def test_duplicate_dbc_id_rejected(self):
        r = row('CreatureDisplayInfo', {0: 10})
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            DBC(dbc_bytes('CreatureDisplayInfo', [r, r]), 'CreatureDisplayInfo')

    def test_corrupt_dbc_layouts_rejected(self):
        good = dbc_bytes('CreatureModelData', [])
        for bad in (b'WDBC', b'WDB2' + good[4:], good[:-1], good + b'\0'):
            with self.subTest(data=bad):
                with self.assertRaises(ValueError):
                    DBC(bad, 'CreatureModelData')

    def test_invalid_string_offset_rejected(self):
        table = DBC(dbc_bytes('CreatureModelData', []), 'CreatureModelData')
        with self.assertRaises(ValueError):
            table.string(1)

    def test_output_is_exclusive(self):
        path = self.root / 'report.json'
        write_json(path, {'original': True})
        with self.assertRaises(FileExistsError):
            write_json(path, {'original': False})
        self.assertEqual(json.loads(path.read_text()), {'original': True})

    def test_nested_symlink_and_traversal_rejected(self):
        link = self.root / 'alias'
        link.symlink_to(self.dbc, target_is_directory=True)
        with self.assertRaises(ValueError):
            checked_path(link / 'Spell.dbc')
        for path in ('../a.m2', '/a.m2', 'creature//a.m2', 'C:\\a.m2', 'a\x00.m2'):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    asset_path(path)


if __name__ == '__main__':
    unittest.main()
