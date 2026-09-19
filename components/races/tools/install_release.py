"""Install/restore an audited local asset package. Preview by default; never launch WoW."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from configure_client import atomic_write, require_wow_closed
from build_runtime import OUTPUT_HASHES, CANDIDATE_OUTPUT_HASHES
from appearance_tables import NAMESPACE, TABLES
from build_appearance_redirect import DLL_PATH, DLL_SHA256
from pack_mpq import no_links
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from wxl_races.bundle import _destination, _game_path, BundleError


def digest(path):
  return hashlib.sha256(path.read_bytes()).hexdigest()


def allowed(relative, locale):
  relative = str(_game_path(relative))
  roots = ('Data/Patch-ModernRaces-HD.MPQ/', f'Data/{locale}/patch-{locale}-ModernRaces.MPQ/')
  if not relative.startswith(roots):
    raise ValueError(f'Not a modern-race asset path: {relative}')
  if relative.lower().endswith(('/creaturemodeldata.dbc', '/creaturedisplayinfo.dbc')):
    raise ValueError('Scale overrides are retired and cannot be installed')
  if Path(relative).suffix.lower() not in {'.m2', '.skin', '.anim', '.blp', '.dbc', '.skel', '.bone'}:
    raise ValueError(f'Unsupported package file: {relative}')
  return relative


def plan(package, client, *, candidate_dip_start_index=False):
  if candidate_dip_start_index:
    package, client = no_links(package), no_links(client)
  report = json.loads((package / 'release-manifest.json').read_text())
  kinds = ('wxl-modern-races-runtime-candidate',) if candidate_dip_start_index else ('wxl-modern-races-assets', 'wxl-modern-races-runtime')
  if report.get('schemaVersion') != 1 or report.get('kind') not in kinds:
    raise ValueError('Not a supported release manifest')
  runtime = report['kind'] in ('wxl-modern-races-runtime', 'wxl-modern-races-runtime-candidate')
  expected_runtime = CANDIDATE_OUTPUT_HASHES if candidate_dip_start_index else OUTPUT_HASHES
  locale = report.get('locale', 'enUS')
  if not isinstance(locale, str) or len(locale) != 4 or not locale.isalpha():
    raise ValueError('Invalid locale')
  result, names = [], set()
  for entry in report['files']:
    name = str(_game_path(entry['path'])) if runtime else allowed(entry['path'], locale)
    if runtime and expected_runtime.get(name) != entry['sha256']:
      raise ValueError('Only the verified runtime hashes may be installed')
    if name.casefold() in names:
      raise ValueError('Duplicate or case-colliding package path')
    names.add(name.casefold())
    source, target = _destination(package, name), _destination(client, name)
    if not source.is_file() or source.stat().st_size != entry['size'] or digest(source) != entry['sha256']:
      raise ValueError(f'Package integrity failure: {name}')
    before = digest(target) if target.exists() else None
    if candidate_dip_start_index and before not in (OUTPUT_HASHES[name], CANDIDATE_OUTPUT_HASHES[name]):
      raise ValueError(f'Candidate requires the verified installed runtime: {name}')
    if before != entry['sha256']:
      result.append({'path': name, 'before': before, 'after': entry['sha256']})
  if not names:
    raise ValueError('Empty package')
  if runtime and names != {name.casefold() for name in expected_runtime}:
    raise ValueError('Incomplete runtime package')
  if not runtime and report.get('appearanceRouting') == 'wxl-io-v1':
    required = {f'Data/Patch-ModernRaces-HD.MPQ/{NAMESPACE}/{name}'.casefold() for name in TABLES}
    if not required.issubset(names):
      raise ValueError('Namespaced appearance tables missing from package')
    extension = _destination(client, DLL_PATH)
    if not extension.is_file() or digest(extension) != DLL_SHA256:
      raise ValueError('Install the verified appearance redirect runtime before assets')
  return result


def apply_runtime_candidate(package, client, entries):
  """Guarded no-backup update of the one changed module in a pinned runtime."""
  require_wow_closed()
  if plan(package, client, candidate_dip_start_index=True) != entries:
    raise ValueError('Runtime changed after candidate preflight')
  module = 'Extensions/wxl-modern-m2/wxl-modern-m2.dll'
  if any(entry['path'] != module for entry in entries):
    raise ValueError('Candidate may replace only the verified modern-M2 module')
  for entry in entries:
    source, target = _destination(package, entry['path']), _destination(client, entry['path'])
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry['after']:
      raise ValueError('Candidate changed before installation')
    require_wow_closed()
    if plan(package, client, candidate_dip_start_index=True) != entries:
      raise ValueError('Runtime changed before candidate replacement')
    if digest(target) != entry['before']:
      raise ValueError('Client changed before candidate replacement')
    atomic_write(target, data, target.stat().st_mode & 0o777)
    if digest(target) != entry['after']:
      raise ValueError('Candidate read-back mismatch')
  if plan(package, client, candidate_dip_start_index=True):
    raise ValueError('Installed candidate verification failed')
  return {'changedFiles': len(entries), 'backupCreated': False,
          'gameplayVerified': False, 'runtimeHashes': CANDIDATE_OUTPUT_HASHES}


def apply(package, client, entries):
  if not entries:
    return None
  require_wow_closed()
  for entry in entries:
    target = _destination(client, entry['path'])
    if (digest(target) if target.exists() else None) != entry['before']:
      raise ValueError('Client changed after preflight')
  parent = _destination(client, 'DisabledPatches/ReleaseBackups')
  parent.mkdir(parents=True, exist_ok=True)
  backup = Path(tempfile.mkdtemp(prefix='before-', dir=parent))
  # Copy all originals before the first client write.
  for entry in entries:
    if entry['before'] is not None:
      source = _destination(client, entry['path'])
      atomic_write(_destination(backup, entry['path']), source.read_bytes(), 0o600)
  atomic_write(backup / 'rollback.json', (json.dumps({'schemaVersion': 1, 'entries': entries}, indent=2) + '\n').encode(), 0o600)
  try:
    for entry in entries:
      source, target = _destination(package, entry['path']), _destination(client, entry['path'])
      data = source.read_bytes()
      if hashlib.sha256(data).hexdigest() != entry['after']:
        raise ValueError('Package changed during installation')
      atomic_write(target, data, 0o600)
      if digest(target) != entry['after']:
        raise ValueError('Read-back mismatch')
  except Exception as exc:
    raise ValueError(f'Installation incomplete; rollback checkpoint: {backup}; {exc}') from exc
  return backup


def rollback(backup, client, write=False):
  root = _destination(client, 'DisabledPatches/ReleaseBackups').resolve()
  if backup.is_symlink() or not backup.resolve().is_relative_to(root):
    raise ValueError('Rollback must be a checkpoint inside this client')
  report = json.loads((backup / 'rollback.json').read_text())
  if report.get('schemaVersion') != 1:
    raise ValueError('Unknown rollback manifest')
  entries = report['entries']
  for entry in entries:
    # Same containment rules, even for a modified rollback manifest.
    name = str(_game_path(entry['path']))
    if name in OUTPUT_HASHES:
      if entry['after'] != OUTPUT_HASHES[name]:
        raise ValueError('Unexpected runtime rollback hash')
    else:
      parts = Path(name).parts
      locale = parts[1] if len(parts) > 1 and len(parts[1]) == 4 else 'enUS'
      allowed(name, locale)
    target = _destination(client, name)
    current = digest(target) if target.exists() else None
    if current not in (entry['before'], entry['after']):
      raise ValueError(f'Refusing to overwrite a later modification: {name}')
    if entry['before'] is not None and digest(_destination(backup, name)) != entry['before']:
      raise ValueError('Backup integrity failure')
  if write:
    require_wow_closed()
    for entry in entries:
      target = _destination(client, entry['path'])
      if entry['before'] is None:
        target.unlink(missing_ok=True)
      else:
        atomic_write(target, _destination(backup, entry['path']).read_bytes(), 0o600)
  return len(entries)


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--client', type=Path, required=True)
  source = parser.add_mutually_exclusive_group(required=True)
  source.add_argument('--package', type=Path)
  source.add_argument('--rollback', type=Path)
  parser.add_argument('--apply', action='store_true')
  parser.add_argument('--stormlib', type=Path, help='required for a torso MPQ package')
  parser.add_argument('--no-backup', action='store_true', help='explicit opt-in for new-only MPQ or pinned runtime candidate packages')
  parser.add_argument('--candidate-dip-start-index', action='store_true', help='explicit opt-in for the pinned DIP runtime candidate')
  parser.add_argument('--report', type=Path, help='new private MPQ installation report')
  args = parser.parse_args(argv)
  try:
    if args.candidate_dip_start_index:
      no_links(args.client.expanduser())
    client = args.client.expanduser().resolve()
    if not (client / 'Wow.exe').is_file() or not (client / 'Data').is_dir():
      raise ValueError('Expected an existing WoW client')
    if args.rollback:
      if args.no_backup or args.report or args.stormlib or args.candidate_dip_start_index:
        raise ValueError('MPQ package options cannot be used with --rollback')
      count = rollback(args.rollback.expanduser(), client, args.apply)
      print(f'Rollback files: {count}; applied: {args.apply}. Backup is retained.')
    else:
      package = args.package.expanduser()
      metadata = json.loads(_destination(package, 'release-manifest.json').read_text())
      if args.candidate_dip_start_index:
        if args.report or args.stormlib or (args.apply and not args.no_backup):
          raise ValueError('Runtime candidate apply requires --no-backup and does not accept MPQ options')
        entries = plan(package, client, candidate_dip_start_index=True)
        print(f'Candidate changed files: {len(entries)}; apply: {args.apply}')
        if args.apply:
          print(json.dumps(apply_runtime_candidate(package, client, entries), indent=2))
        return 0
      if metadata.get('kind') == 'wxl-modern-races-undead-torso':
        if args.stormlib is None:
          raise ValueError('Torso packages require --stormlib for independent archive checks')
        from undead_torso import install
        print(json.dumps(install(package, client, args.stormlib, args.apply, args.no_backup, args.report), indent=2))
        return 0
      if args.no_backup or args.report or args.stormlib:
        raise ValueError('MPQ-only options supplied for a different package type')
      entries = plan(package, client)
      print(f'Changed files: {len(entries)}; apply: {args.apply}')
      if args.apply:
        print(f'Rollback checkpoint: {apply(package, client, entries)}')
    return 0
  except (OSError, ValueError, BundleError) as exc:
    print(f'error: {exc}', file=sys.stderr)
    return 2


if __name__ == '__main__':
  raise SystemExit(main())
