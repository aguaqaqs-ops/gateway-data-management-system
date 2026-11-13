"""Focused refusal cases for the acceptance verifier; execute only on node 05."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import struct
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/verify-real-journey.py'
SPEC = importlib.util.spec_from_file_location('directory_evidence', SCRIPT)
assert SPEC is not None and SPEC.loader is not None
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
HEAD = 'a' * 40
SESSION = 'directory-evidence-fixture'


def put(root, name, value):
    (root / name).write_text(json.dumps(value) + '\n')


def manifest(root):
    put(root, 'artifacts.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.iterdir() if p.name != 'artifacts.json'})


def fixture(root):
    for name in GATE.REQUIRED:
        put(root, name, {})
    result = dict(head=HEAD, start_head=HEAD, end_head=HEAD, session=SESSION,
        hostname=socket.gethostname(), end_hostname=socket.gethostname(), clean_start=True, clean_end=True,
        exit=0, original_exit=0, start_utc='2026-11-13T00:00:00Z', end_utc='2026-11-13T00:00:01Z',
        cleanup_status='passed', credential_scan={'status': 'passed', 'leaks': []},
        stages={k: {'status': 'passed', **{field: True for field in fields}} for k, fields in GATE.FACTS.items()}, locks_end={'lock': HEAD})
    put(root, 'run-result.json', result)
    put(root, 'inputs.json', {'head': HEAD, 'locks': {'lock': HEAD}})
    put(root, 'upload-inputs.json', {'source_head': HEAD})
    put(root, 'containers-before.json', {'backend': {'id': 'backend'}, 'worker': {'id': 'worker'}})
    put(root, 'containers-after.json', {'backend': {'id': 'backend'}, 'worker': {'id': 'worker'}})
    put(root, 'browser-exit.json', {'status': 'passed', 'passed': True})
    browser_facts = {f'J{i}': {'status': 'passed', **{field: True for field in GATE.FACTS[f'J{i}']}} for i in range(2, 6)}
    browser_facts['J6'] = {'status': 'passed', 'directory_new_token': True, 'a_data_restored': True}
    put(root, 'browser-facts.json', browser_facts)
    events = [{'event': 'begin'}, {'event': 'browser_exit', 'exit': 0}]
    for kind in ('new', 'new', 'old'):
        for station in ('SZ-0142', 'WX-0207'):
            events.append(dict(event='credential_probe', station=station, kind=kind, scope_ok=True, status=401 if kind == 'old' else 200))
    events.append(dict(event='end', exit=0, original_exit=0, cleanup_ok=True))
    (root / 'run-events.jsonl').write_text(''.join(json.dumps(v) + '\n' for v in events))
    (root / 'run.log').write_text('raw output\n' + json.dumps(events[-1]) + '\n')
    for state in GATE.STATES:
        for width in (1280, 1920):
            (root / f'{state}-{width}.png').write_bytes(b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', width, 900) + b'fixture')
    manifest(root)
    return result


class EvidenceRefusals(unittest.TestCase):
    def test_completed_fixture_and_refusals(self):
        self.assertEqual(socket.gethostname(), 'gw-dms-05', 'focused verifier tests belong on 05')
        with tempfile.TemporaryDirectory(prefix='directory-evidence-', dir='/home/dev/gdds-test-tmp') as folder:
            root = Path(folder)
            original = fixture(root)
            self.assertEqual(GATE.verify(root, HEAD, SESSION)['status'], 'passed')
            changes = (
                ('wrong candidate', lambda d: d.update(end_head='b' * 40)),
                ('nonzero original exit', lambda d: d.update(original_exit=1)),
                ('missing assertion', lambda d: d['stages']['J4'].pop('actor_test1')),
                ('unknown stage', lambda d: d['stages']['J4'].update(status='unknown')),
                ('cleanup failure', lambda d: d.update(cleanup_status='failed')),
                ('credential scan unknown', lambda d: d.update(credential_scan={'status': 'unknown', 'leaks': []})),
            )
            for name, mutate in changes:
                with self.subTest(name=name):
                    changed = copy.deepcopy(original)
                    mutate(changed)
                    put(root, 'run-result.json', changed)
                    manifest(root)
                    self.assertEqual(GATE.verify(root, HEAD, SESSION)['status'], 'failed')
            put(root, 'run-result.json', original)
            manifest(root)
            with (root / 'run.log').open('a') as stream:
                stream.write('truncated/nonfinal output\n')
            with self.assertRaises(json.JSONDecodeError):
                GATE.verify(root, HEAD, SESSION)
            fixture(root)
            (root / 'receipts.json').write_text('changed after hashing')
            self.assertEqual(GATE.verify(root, HEAD, SESSION)['status'], 'failed')
            fixture(root)
            image = root / 'a-initial-1280.png'
            image.write_bytes(image.read_bytes()[:16] + struct.pack('>I', 1920) + image.read_bytes()[20:])
            manifest(root)
            self.assertEqual(GATE.verify(root, HEAD, SESSION)['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
