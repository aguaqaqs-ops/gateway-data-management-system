"""Complete originals plus corruption/refusal cases; execute only on node 05."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import unittest
import zlib

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
SPEC = importlib.util.spec_from_file_location('directory_evidence', SCRIPTS / 'verify-real-journey.py')
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
HEAD = subprocess.check_output(['git', '-C', str(GATE.ROOT), 'rev-parse', 'HEAD'], text=True).strip()
SESSION = 'directory-evidence-fixture'
WHEN = '2026-11-13T00:00:00Z'


def put(root, name, value):
    (root / name).write_text(json.dumps(value) + '\n')


def manifest(root):
    put(root, 'artifacts.json', {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob('*') if p.is_file() and p.name != 'artifacts.json'})


def png(width):
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00' + b'\x00' * width * 3)) + chunk(b'IEND', b'')


def fixture(root):
    identity = dict(head=HEAD, session=SESSION, hostname=socket.gethostname())
    for name in GATE.REQUIRED:
        put(root, name, {})
    locks = {p: hashlib.sha256(subprocess.check_output(['git', '-C', str(GATE.ROOT), 'show', HEAD + ':' + p])).hexdigest() for p in GATE.LOCKS}
    trees = {p: subprocess.check_output(['git', '-C', str(GATE.ROOT), 'rev-parse', HEAD + ':' + p], text=True).strip() for p in ('directory', 'frontend', 'vnext')}
    config = root.parent / 'config.json'
    config.chmod(0o600) if config.exists() else None
    result = dict(**identity, start_head=HEAD, end_head=HEAD, end_hostname=socket.gethostname(), clean_start=True, clean_end=True,
        exit=0, original_exit=0, start_utc=WHEN, end_utc=WHEN,
        entry_argv=['directory/scripts/run-real-journey.sh', '--head', HEAD, '--session', SESSION, '--config', str(config), '--evidence-dir', str(root)],
        cleanup_status='passed', credential_scan={'status': 'passed', 'leaks': []},
        stages={k: {'status': 'passed', **{field: True for field in fields}} for k, fields in GATE.FACTS.items()}, locks_end=locks)
    put(root, 'run-result.json', result)
    images = dict(toolchain='mcr.microsoft.com/playwright:v1.64.1-noble', entry='nginx:1.28.0', backend='fixture-backend:one', worker='fixture-worker:one', repository_service='fixture-rs:one')
    caches = {role: dict(source_hostname='heavy-dev-01', source_commit=HEAD, prefilled_utc=WHEN,
        lock_sha256=locks[path], archive_sha256='b' * 64, cache_tree_sha256='c' * 64)
        for role, path in [('directory', 'directory/frontend/package-lock.json'), ('gateway', 'frontend/package-lock.json')]}
    configuration = {}
    for role in ('directory', 'gateway'):
        cache = root.parent / (role + '-cache')
        cache.mkdir(exist_ok=True)
        (cache / 'cached').write_text('npm cached fixture')
        archive = root.parent / (role + '-cache.tar.gz')
        archive.write_text('archive fixture')
        caches[role]['archive_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
        caches[role]['cache_tree_sha256'] = GATE._png.tree_hash(cache)
        manifest_path = root.parent / (role + '-manifest.json')
        manifest_path.write_text(json.dumps(caches[role]))
        configuration.update({role + '_npm_cache': str(cache), role + '_npm_archive': str(archive), role + '_npm_manifest': str(manifest_path)})
    groups_path = root.parent / 'groups.json'
    groups_path.write_text(json.dumps(dict(groups=[dict(images={**{k: images[k] for k in ('backend', 'worker', 'repository_service')}, 'revision': HEAD})], entry=dict(image=images['entry']))))
    originals = root.parent / 'original-images.json'
    originals.write_text(json.dumps({ref: dict(config_digest='sha256:' + 'a' * 64, diff_ids=['sha256:' + 'b' * 64]) for ref in images.values()}))
    configuration.update(groups_file=str(groups_path), image_identities=str(originals))
    config.write_text(json.dumps(configuration))
    config.chmod(0o600)
    put(root, 'inputs.json', dict(**identity, trees=trees, locks=locks, images=images, cache_manifests=caches,
        config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(), config_path=str(config), config_mode='0o600'))
    for name in ('image-identities.json', 'verified-images.json'):
        put(root, name, {ref: dict(config_digest='sha256:' + 'a' * 64, diff_ids=['sha256:' + 'b' * 64]) for ref in images.values()})
    input_root = root.parent / 'input'
    upload_files = {}
    for directory in ('full_initial', 'full_modified'):
        for filename in ('upload.pmc', 'sql/dbcfg.sql', 'comps/logic/logics.xml'):
            path = input_root / directory / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('input')
            upload_files[directory + '/' + filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    put(root, 'upload-inputs.json', dict(source_head=HEAD, session=SESSION, root=str(input_root), files=upload_files, mode='FULL', source='existing e2e FULL'))
    static = root.parent / 'static'
    static_files = {}
    for filename in ('index.html', '.vite/manifest.json', 'assets/test.js', 'assets/test.css'):
        path = static / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('build')
        static_files[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    put(root, 'static-files.json', dict(head=HEAD, session=SESSION, root=str(static), files=static_files))
    containers = {k: dict(id=v * 64, started_at=WHEN, restarts=0) for k, v in [('backend', 'a'), ('worker', 'b')]}
    put(root, 'containers-before.json', containers)
    put(root, 'containers-after.json', containers)
    receipts = {station: dict(repository='repo-' + station, initial='initial-' + station, commit='commit-' + station) for station in GATE.STATIONS}
    put(root, 'receipts.json', receipts)
    put(root, 'business-ids.json', dict(head=HEAD, session=SESSION, a_scope='dev-fbe8accb4da11574', b_scope='dev-0a5e7c9870eaba0b',
        a=dict(workspace_id='a-ws', preview_id='a-preview', submission_id='a-submission'), b=dict(workspace_id='b-ws', initial_id=receipts['WX-0207']['initial'])))
    put(root, 'browser-exit.json', dict(head=HEAD, session=SESSION, status='passed', passed=True))
    browser_facts = {f'J{i}': {'status': 'passed', **{field: True for field in GATE.FACTS[f'J{i}']}} for i in range(2, 6)}
    browser_facts['J6'] = {'status': 'passed', 'directory_new_token': True, 'a_data_restored': True}
    put(root, 'browser-facts.json', dict(head=HEAD, session=SESSION, stages=browser_facts))
    events = [dict(event='begin', clean=True), dict(event='browser_exit', exit=0)]
    for label in ('deployment_validate', 'group_up', 'entry_up', 'deployment_inspect', 'import', 'provision', 'offline_builds', 'renew_sessions'):
        events.extend([dict(event='command_start', label=label), dict(event='command_end', label=label, exit=0)])
    events.extend(dict(event='stage_complete', stage='J' + str(i)) for i in range(7))
    for kind in ('new', 'new', 'old'):
        for station in GATE.STATIONS:
            events.append(dict(event='credential_probe', station=station, kind=kind, scope_ok=True, status=401 if kind == 'old' else 200))
    events.append(dict(event='end', exit=0, original_exit=0, cleanup_ok=True))
    events = [dict(**identity, utc=WHEN, **event) for event in events]
    (root / 'run-events.jsonl').write_text(''.join(json.dumps(v) + '\n' for v in events))
    (root / 'run.log').write_text(json.dumps(events[0]) + '\nraw output\n' + json.dumps(events[-1]) + '\n')
    shots = []
    for state in GATE.STATES:
        for width in (1280, 1920):
            name = f'{state}-{width}.png'
            (root / name).write_bytes(png(width))
            shots.append(dict(head=HEAD, session=SESSION, name=name, secret_free=True, fragment_cleared=True))
    put(root, 'screenshot-checks.json', shots)
    manifest(root)
    return result


class EvidenceRefusals(unittest.TestCase):
    def verify_failed(self, root):
        try:
            self.assertEqual(GATE.verify(root, HEAD, SESSION)['status'], 'failed')
        except (ValueError, KeyError, TypeError):
            pass  # CLI maps malformed/incomplete originals to failed+unknown.

    def test_complete_originals_and_refusals(self):
        self.assertEqual(socket.gethostname(), 'gw-dms-test-05')
        with tempfile.TemporaryDirectory(prefix='directory-evidence-', dir='/home/dev/gdds-test-tmp') as folder:
            root = Path(folder) / 'evidence'
            root.mkdir()
            original = fixture(root)
            self.assertEqual(GATE.verify(root, HEAD, SESSION)['status'], 'passed')
            changes = (
                ('wrong candidate', lambda d: d.update(end_head='b' * 40)),
                ('nonzero original exit', lambda d: d.update(original_exit=1)),
                ('missing assertion', lambda d: d['stages']['J4'].pop('actor_test1')),
                ('unknown stage', lambda d: d['stages']['J4'].update(status='unknown')),
                ('cleanup failure', lambda d: d.update(cleanup_status='failed')),
            )
            for name, mutate in changes:
                with self.subTest(name=name):
                    changed = copy.deepcopy(original)
                    mutate(changed)
                    put(root, 'run-result.json', changed)
                    manifest(root)
                    self.verify_failed(root)
            mutations = (
                ('empty images', lambda: (put(root, 'image-identities.json', {}), put(root, 'verified-images.json', {}))),
                ('missing container fields', lambda: (put(root, 'containers-before.json', {'backend': {'id': 'a'}, 'worker': {'id': 'b'}}), put(root, 'containers-after.json', {'backend': {'id': 'a'}, 'worker': {'id': 'b'}}))),
                ('empty inputs', lambda: put(root, 'inputs.json', {'head': HEAD})),
                ('empty receipts', lambda: put(root, 'receipts.json', {})),
                ('empty static', lambda: put(root, 'static-files.json', {})),
                ('wrong browser run', lambda: put(root, 'browser-exit.json', dict(head=HEAD, session='another-run', status='passed', passed=True))),
                ('missing PNG end', lambda: (root / 'a-initial-1280.png').write_bytes(png(1280)[:-12])),
                ('header-only PNG', lambda: (root / 'a-initial-1280.png').write_bytes(png(1280)[:24])),
                ('bad PNG CRC', lambda: (root / 'a-initial-1280.png').write_bytes(png(1280)[:-1] + b'X')),
                ('wrong dimensions', lambda: (root / 'a-initial-1280.png').write_bytes(png(1920))),
            )
            for name, mutate in mutations:
                with self.subTest(name=name):
                    fixture(root)
                    mutate()
                    manifest(root)
                    self.verify_failed(root)
            for name, event in [('foreign event', {'head': 'b' * 40}), ('intermediate failure', {'event': 'failure'}), ('nonzero command', {'event': 'command_end', 'exit': 1})]:
                with self.subTest(name=name):
                    fixture(root)
                    events = [json.loads(v) for v in (root / 'run-events.jsonl').read_text().splitlines()]
                    events[1].update(event)
                    (root / 'run-events.jsonl').write_text(''.join(json.dumps(v) + '\n' for v in events))
                    manifest(root)
                    self.verify_failed(root)


if __name__ == '__main__':
    unittest.main()
