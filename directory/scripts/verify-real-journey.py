#!/usr/bin/env python3
"""Fail-closed checks of one original, completed directory J0-J7 run.

Run on the evidence node; a copy alone is not authoritative. Optional --copy-dir
compares each copied original. The check reports only fixed labels, no content.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import struct
import sys

STATES = ('directory-search', 'a-initial', 'a-reviewed', 'b-initial', 'a-renewed')
FACTS = {
    'J0': {'initial_unprovisioned', 'deployment_inspected', 'python_and_caches_verified', 'image_identities_verified'},
    'J1': {'receipts', 'public_scope', 'unchanged_containers'},
    'J2': {'static_resources_ok', 'no_injected_session'},
    'J3': {'fragment_cleared', 'initial', 'refresh_scope'},
    'J4': {'ui_upload', 'preview', 'ui_submit', 'ui_approve', 'actor_test1', 'refresh_scope'},
    'J5': {'return_query_restored', 'b_initial_only', 'b_scope'},
    'J6': {'directory_new_token', 'a_data_restored', 'public_new_scope', 'public_old_401', 'unchanged_containers'},
    'J7': {'resources_stopped', 'occupancy_released'},
}
REQUIRED = {'run.log', 'run-events.jsonl', 'verified-images.json', 'run-result.json', 'inputs.json', 'image-identities.json', 'upload-inputs.json',
    'receipts.json', 'static-files.json', 'containers-before.json', 'containers-after.json',
    'browser-exit.json', 'browser-facts.json', 'browser-process.log'}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    return json.loads(path.read_text())


def verify(root, head, session, copy=None):
    checks = []
    def check(label, condition):
        checks.append(dict(check=label, status='passed' if condition else 'failed'))
    check('evidence_node', socket.gethostname() == 'gw-dms-05')
    result = load(root / 'run-result.json')
    check('same_candidate_session', result['head'] == result['start_head'] == result['end_head'] == head
        and result['session'] == session and result['hostname'] == result['end_hostname'] == socket.gethostname())
    check('complete_clean_success', result['clean_start'] is True and result['clean_end'] is True
        and type(result['exit']) is int and result['exit'] == 0
        and type(result['original_exit']) is int and result['original_exit'] == 0
        and result['cleanup_status'] == 'passed' and result['start_utc'] <= result['end_utc'])
    stages = result['stages']
    check('J0_J7_complete', set(stages) == {f'J{i}' for i in range(8)}
        and all(set(stages[k]) == FACTS[k] | {'status'} and stages[k]['status'] == 'passed'
            and all(stages[k][field] is True for field in FACTS[k]) for k in FACTS))
    check('credential_scan', result['credential_scan'] == {'status': 'passed', 'leaks': []})
    log = [json.loads(line) for line in (root / 'run-events.jsonl').read_text().splitlines()]
    check('raw_log_end', bool(log) and log[0]['event'] == 'begin' and log[-1]['event'] == 'end'
        and log[-1]['exit'] == log[-1]['original_exit'] == 0 and log[-1]['cleanup_ok'] is True)
    raw_end = json.loads((root / 'run.log').read_text().splitlines()[-1])
    check('original_log_end', raw_end == log[-1])
    check('browser_original_exit', any(row.get('event') == 'browser_exit' and row.get('exit') == 0 for row in log))
    check('browser_complete', load(root / 'browser-exit.json') == {'status': 'passed', 'passed': True})
    facts = load(root / 'browser-facts.json')
    browser_expected = {k: FACTS[k] for k in ('J2', 'J3', 'J4', 'J5')}
    browser_expected['J6'] = {'directory_new_token', 'a_data_restored'}
    check('browser_stages', set(facts) == set(browser_expected) and
        all(set(facts[k]) == fields | {'status'} and facts[k]['status'] == 'passed'
            and all(facts[k][field] is True for field in fields) for k, fields in browser_expected.items()))
    check('containers_unchanged', load(root / 'containers-before.json') == load(root / 'containers-after.json')
        and set(load(root / 'containers-before.json')) == {'backend', 'worker'})
    probes = [v for v in log if v.get('event') == 'credential_probe']
    check('public_new_old_probe', [(v['kind'], v['station']) for v in probes] ==
        [(kind, station) for kind in ('new', 'new', 'old') for station in ('SZ-0142', 'WX-0207')] and
        all(v['scope_ok'] is True and v['status'] == (401 if v['kind'] == 'old' else 200) for v in probes)
        and {v['station'] for v in probes if v['kind'] == 'old'} == {'SZ-0142', 'WX-0207'})
    check('image_identity', load(root / 'image-identities.json') == load(root / 'verified-images.json'))
    check('locks_unchanged', load(root / 'inputs.json')['locks'] == result['locks_end'])
    check('source_inputs', load(root / 'inputs.json')['head'] == head and load(root / 'upload-inputs.json')['source_head'] == head)
    files = load(root / 'artifacts.json')
    screenshots = {f'{state}-{width}.png' for state in STATES for width in (1280, 1920)}
    check('artifact_inventory', set(files) == {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name != 'artifacts.json'})
    check('mandatory_artifacts', REQUIRED | screenshots <= set(files))
    check('screenshot_set', {p.name for p in root.glob('*.png')} == screenshots)
    for name, expected in files.items():
        relative = Path(name)
        path = root / relative
        good = not relative.is_absolute() and '..' not in relative.parts and not path.is_symlink() and path.resolve().is_relative_to(root.resolve())
        good = good and path.is_file() and re.fullmatch('[0-9a-f]{64}', expected) is not None and sha(path) == expected
        check('artifact:' + name, good)
        if copy is not None:
            duplicate = copy / relative
            check('copy:' + name, good and duplicate.is_file() and not duplicate.is_symlink() and sha(duplicate) == expected)
    for name in sorted(screenshots):
        raw = (root / name).read_bytes()
        check('dimensions:' + name, len(raw) > 24 and raw[:8] == b'\x89PNG\r\n\x1a\n' and raw[12:16] == b'IHDR'
            and struct.unpack('>I', raw[16:20])[0] == int(name.rsplit('-', 1)[1][:-4])
            and struct.unpack('>I', raw[20:24])[0] > 0)
    return {'status': 'passed' if all(v['status'] == 'passed' for v in checks) else 'failed',
        'head': head, 'session': session, 'original_root': str(root), 'checks': checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--copy-dir', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.run_dir, args.head, args.session, args.copy_dir)
    except Exception as error:
        result = dict(status='failed', error_class=type(error).__name__,
            checks=[dict(check='complete_readable_original', status='unknown')])
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('directory_evidence_check=' + result['status'])
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
