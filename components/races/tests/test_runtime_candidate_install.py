import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import install_release as install

MODULE = 'Extensions/wxl-modern-m2/wxl-modern-m2.dll'


class CandidateInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.client, self.package = root/'client', root/'package'
        self.client.mkdir(); self.package.mkdir()
        self.before, self.after = {}, {}
        entries = []
        for name in install.OUTPUT_HASHES:
            old = ('verified baseline ' + name).encode()
            new = old + b' fixed' if name == MODULE else old
            self.before[name] = hashlib.sha256(old).hexdigest()
            self.after[name] = hashlib.sha256(new).hexdigest()
            for base, data in ((self.client, old), (self.package, new)):
                target = base/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            entries.append({'path': name, 'size': len(new), 'sha256': self.after[name]})
        (self.package/'release-manifest.json').write_text(json.dumps({
            'schemaVersion': 1, 'kind': 'wxl-modern-races-runtime-candidate', 'files': entries}))
        for attr, value in (('OUTPUT_HASHES', self.before), ('CANDIDATE_OUTPUT_HASHES', self.after)):
            mock = patch.object(install, attr, value)
            mock.start(); self.addCleanup(mock.stop)
        self.closed = patch.object(install, 'require_wow_closed').start()
        self.addCleanup(patch.stopall)

    def plan(self):
        return install.plan(self.package, self.client, candidate_dip_start_index=True)

    def test_explicit_opt_in_module_only_no_backup_and_idempotence(self):
        with self.assertRaisesRegex(ValueError, 'supported release'):
            install.plan(self.package, self.client)
        entries = self.plan()
        self.assertEqual([entry['path'] for entry in entries], [MODULE])
        unchanged = {name: (self.client/name).stat().st_mtime_ns for name in self.before if name != MODULE}
        result = install.apply_runtime_candidate(self.package, self.client, entries)
        self.assertEqual(result['changedFiles'], 1)
        self.assertFalse(result['backupCreated'])
        self.assertFalse((self.client/'DisabledPatches').exists())
        self.assertEqual(install.digest(self.client/MODULE), self.after[MODULE])
        self.assertEqual(unchanged, {name: (self.client/name).stat().st_mtime_ns for name in unchanged})
        self.assertEqual(self.plan(), [])
        self.assertEqual(install.apply_runtime_candidate(self.package, self.client, [])['changedFiles'], 0)

    def test_unknown_installed_core_refused_before_write(self):
        (self.client/'WarcraftXL.dll').write_bytes(b'unknown core')
        with self.assertRaisesRegex(ValueError, 'verified installed runtime'):
            self.plan()
        self.assertEqual(install.digest(self.client/MODULE), self.before[MODULE])

    def test_core_changed_after_preflight_refused(self):
        entries = self.plan()
        (self.client/'WarcraftXL.dll').write_bytes(b'changed concurrently')
        with self.assertRaisesRegex(ValueError, 'verified installed runtime'):
            install.apply_runtime_candidate(self.package, self.client, entries)
        self.assertEqual(install.digest(self.client/MODULE), self.before[MODULE])

    def test_core_changed_during_final_process_check_refused(self):
        entries = self.plan()
        def check():
            if self.closed.call_count == 2:
                (self.client/'WarcraftXL.dll').write_bytes(b'changed at final process check')
        self.closed.side_effect = check
        with self.assertRaisesRegex(ValueError, 'verified installed runtime'):
            install.apply_runtime_candidate(self.package, self.client, entries)
        self.assertEqual(install.digest(self.client/MODULE), self.before[MODULE])

    def test_symlink_in_candidate_root_parents_refused(self):
        alias = self.client.parent/'alias'
        alias.symlink_to(self.client.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            install.plan(self.package, alias/'client', candidate_dip_start_index=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            install.plan(alias/'package', self.client, candidate_dip_start_index=True)
        self.assertEqual(install.digest(self.client/MODULE), self.before[MODULE])

    def test_changed_candidate_and_running_game_refused(self):
        entries = self.plan()
        self.closed.side_effect = ValueError('WoW running')
        with self.assertRaisesRegex(ValueError, 'WoW running'):
            install.apply_runtime_candidate(self.package, self.client, entries)
        self.closed.side_effect = None
        (self.package/MODULE).write_bytes(b'damaged candidate')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            install.apply_runtime_candidate(self.package, self.client, entries)
        self.assertEqual(install.digest(self.client/MODULE), self.before[MODULE])

    def test_incomplete_package_refused(self):
        manifest = self.package/'release-manifest.json'
        report = json.loads(manifest.read_text()); report['files'].pop()
        manifest.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'Incomplete runtime'):
            self.plan()


if __name__ == '__main__':
    unittest.main()
