#!/usr/bin/env python3
"""Fail closed on incomplete original evidence for one directory J0-J7 run."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('directory_frontend_inputs', Path(__file__).with_name('frontend-inputs.py'))
_png = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_png)
STATES = ('directory-search', 'a-initial', 'a-reviewed', 'b-initial', 'a-renewed')
STATIONS = ('SZ-0142', 'WX-0207')
LOCKS = {'directory/service/uv.lock', 'directory/frontend/package-lock.json', 'frontend/package-lock.json'}
FACTS = {
    'J0': {'initial_unprovisioned', 'deployment_inspected', 'python_and_caches_verified', 'image_identities_verified'},
    'J1': {'receipts', 'public_scope', 'unchanged_containers'},
    'J2': {'static_resources_ok', 'no_injected_session'},
    'J3': {'fragment_cleared', 'initial', 'refresh_scope'},
    'J4': {'ui_upload', 'preview', 'ui_submit', 'ui_approve', 'actor_test1', 'refresh_scope'},
    'J5': {'return_query_restored', 'b_initial_only', 'b_scope', 'b_workspace_empty', 'excludes_a_ids'},
    'J6': {'directory_new_token', 'a_data_restored', 'public_new_scope', 'public_old_401', 'unchanged_containers'},
    'J7': {'resources_stopped', 'occupancy_released'},
}
REQUIRED = {'run.log', 'run-events.jsonl', 'verified-images.json', 'run-result.json', 'inputs.json', 'image-identities.json', 'upload-inputs.json',
    'receipts.json', 'static-files.json', 'containers-before.json', 'containers-after.json', 'screenshot-checks.json', 'business-ids.json',
    'browser-exit.json', 'browser-facts.json', 'browser-process.log'}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate field')
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=pairs)


def hexvalue(value, count=64):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(count) + '}', value) is not None


def utc(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z', value):
        return False
    datetime.fromisoformat(value.replace('Z', '+00:00'))
    return True


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def safe_file(root, relative):
    name = Path(relative)
    path = root / name
    return (not name.is_absolute() and '..' not in name.parts and path.resolve().is_relative_to(root.resolve())
        and not any(p.is_symlink() for p in (path, *path.parents)) and path.is_file())


def files_valid(root, files):
    return bool(files) and all(safe_file(root, p) and hexvalue(h) and sha(root / p) == h for p, h in files.items())


def verify(root, head, session, copy=None):
    checks = []
    def check(label, condition):
        checks.append(dict(check=label, status='passed' if condition else 'failed'))
    check('evidence_node', socket.gethostname() == 'gw-dms-test-05')
    check('full_candidate', hexvalue(head, 40))
    result = load(root / 'run-result.json')
    check('same_candidate_session', result['head'] == result['start_head'] == result['end_head'] == head
        and result['session'] == session and result['hostname'] == result['end_hostname'] == socket.gethostname())
    check('complete_clean_success', result['clean_start'] is True and result['clean_end'] is True
        and type(result['exit']) is int and result['exit'] == 0
        and type(result['original_exit']) is int and result['original_exit'] == 0
        and result['cleanup_status'] == 'passed' and utc(result['start_utc']) and utc(result['end_utc'])
        and result['start_utc'] <= result['end_utc'])
    expected_argv = ['directory/scripts/run-real-journey.sh', '--head', head, '--session', session,
        '--config', result['entry_argv'][6], '--evidence-dir', str(root)]
    check('entry_argv', result['entry_argv'] == expected_argv and Path(expected_argv[6]).is_absolute())
    stages = result['stages']
    check('J0_J7_complete', set(stages) == set(FACTS)
        and all(set(stages[k]) == FACTS[k] | {'status'} and stages[k]['status'] == 'passed'
            and all(stages[k][field] is True for field in FACTS[k]) for k in FACTS))
    check('credential_scan', result['credential_scan'] == {'status': 'passed', 'leaks': []})
    log = [json.loads(line) for line in (root / 'run-events.jsonl').read_text().splitlines()]
    check('event_identity', bool(log) and all(v['head'] == head and v['session'] == session
        and v['hostname'] == socket.gethostname() and utc(v['utc'])
        and result['start_utc'] <= v['utc'] <= result['end_utc'] for v in log)
        and [v['utc'] for v in log] == sorted(v['utc'] for v in log))
    check('raw_log_end', bool(log) and log[0]['event'] == 'begin' and log[0]['clean'] is True
        and log[-1]['event'] == 'end' and log[-1]['exit'] == log[-1]['original_exit'] == 0 and log[-1]['cleanup_ok'] is True)
    check('no_intermediate_failure', all(v['event'] not in ('failure', 'command_abort')
        and (v['event'] not in ('command_end', 'browser_exit') or type(v['exit']) is int and v['exit'] == 0) for v in log))
    starts = [v['label'] for v in log if v['event'] == 'command_start']
    ends = [v['label'] for v in log if v['event'] == 'command_end']
    check('commands_completed', bool(starts) and starts == ends
        and {'deployment_validate', 'group_up', 'entry_up', 'deployment_inspect', 'import', 'provision', 'offline_builds', 'renew_sessions'} <= set(ends))
    check('stage_chain', [v['stage'] for v in log if v['event'] == 'stage_complete'] == [f'J{i}' for i in range(7)])
    raw_lines = (root / 'run.log').read_text().splitlines()
    check('original_log_identity', json.loads(raw_lines[0]) == log[0] and json.loads(raw_lines[-1]) == log[-1])
    check('browser_original_exit', len([v for v in log if v['event'] == 'browser_exit']) == 1
        and all(v['exit'] == 0 for v in log if v['event'] == 'browser_exit'))
    check('browser_complete', load(root / 'browser-exit.json') == {'head': head, 'session': session, 'status': 'passed', 'passed': True})
    browser = load(root / 'browser-facts.json')
    facts = browser['stages']
    browser_expected = {k: FACTS[k] for k in ('J2', 'J3', 'J4', 'J5')}
    browser_expected['J6'] = {'directory_new_token', 'a_data_restored'}
    check('browser_stages', browser['head'] == head and browser['session'] == session and set(facts) == set(browser_expected) and
        all(set(facts[k]) == fields | {'status'} and facts[k]['status'] == 'passed'
            and all(facts[k][field] is True for field in fields) for k, fields in browser_expected.items()))
    before, after = (load(root / name) for name in ('containers-before.json', 'containers-after.json'))
    check('containers_unchanged', before == after and set(before) == {'backend', 'worker'} and
        all(set(v) == {'id', 'started_at', 'restarts'} and hexvalue(v['id']) and utc(v['started_at'])
            and type(v['restarts']) is int and v['restarts'] >= 0 for v in before.values())
        and len({v['id'] for v in before.values()}) == 2)
    probes = [v for v in log if v['event'] == 'credential_probe']
    check('public_new_old_probe', [(v['kind'], v['station']) for v in probes] ==
        [(kind, station) for kind in ('new', 'new', 'old') for station in STATIONS] and
        all(v['scope_ok'] is True and v['status'] == (401 if v['kind'] == 'old' else 200) for v in probes))
    inputs = load(root / 'inputs.json')
    config_path = Path(inputs['config_path'])
    config = load(config_path)
    check('fixed_config', config_path.is_absolute() and sha(config_path) == inputs['config_sha256']
        and (config_path.stat().st_mode & 0o7777) == 0o600)
    check('source_inputs', inputs['head'] == head and inputs['session'] == session and inputs['hostname'] == socket.gethostname()
        and hexvalue(inputs['config_sha256']) and inputs['config_mode'] == '0o600' and Path(inputs['config_path']).is_absolute())
    check('source_trees', set(inputs['trees']) == {'directory', 'frontend', 'vnext'}
        and all(hexvalue(v, 40) for v in inputs['trees'].values()))
    check('locks_unchanged', set(inputs['locks']) == LOCKS and inputs['locks'] == result['locks_end'] and all(hexvalue(v) for v in inputs['locks'].values()))
    # Bind declared trees/locks to the referenced immutable source, not to an
    # arbitrary equal pair of manifest documents.
    trees = {p: subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', head + ':' + p], text=True, timeout=10).strip() for p in ('directory', 'frontend', 'vnext')}
    locks = {p: hashlib.sha256(subprocess.check_output(['git', '-C', str(ROOT), 'show', head + ':' + p], timeout=10)).hexdigest() for p in LOCKS}
    check('immutable_source_match', inputs['trees'] == trees and inputs['locks'] == locks)
    cache_fields = {'source_hostname', 'source_commit', 'prefilled_utc', 'lock_sha256', 'archive_sha256', 'cache_tree_sha256'}
    caches = inputs['cache_manifests']
    check('cache_provenance', set(caches) == {'directory', 'gateway'} and all(set(c) == cache_fields
        and nonempty(c['source_hostname']) and hexvalue(c['source_commit'], 40) and utc(c['prefilled_utc'])
        and all(hexvalue(c[k]) for k in ('lock_sha256', 'archive_sha256', 'cache_tree_sha256'))
        and c['lock_sha256'] == inputs['locks']['directory/frontend/package-lock.json' if role == 'directory' else 'frontend/package-lock.json'] for role, c in caches.items()))
    for role in ('directory', 'gateway'):
        original = load(Path(config[role + '_npm_manifest']))
        check('original_cache:' + role, original == caches[role]
            and sha(Path(config[role + '_npm_archive'])) == original['archive_sha256']
            and _png.tree_hash(Path(config[role + '_npm_cache'])) == original['cache_tree_sha256'])
    roles = inputs['images']
    groups = load(Path(config['groups_file']))
    group = groups['groups'][0]
    check('fixed_image_selection', len(groups['groups']) == 1 and group['images']['revision'] == head
        and roles == dict(toolchain='mcr.microsoft.com/playwright:v1.64.1-noble', entry=groups['entry']['image'],
            **{k: group['images'][k] for k in ('backend', 'worker', 'repository_service')}))
    expected, verified = load(root / 'image-identities.json'), load(root / 'verified-images.json')
    check('original_image_identity', load(Path(config['image_identities'])) == expected)
    check('image_identity', set(roles) == {'toolchain', 'entry', 'backend', 'worker', 'repository_service'}
        and roles['toolchain'] == 'mcr.microsoft.com/playwright:v1.64.1-noble' and roles['entry'] == 'nginx:1.28.0'
        and all(nonempty(v) for v in roles.values()) and len(set(roles.values())) == 5
        and set(expected) == set(roles.values()) and expected == verified and all(set(v) == {'config_digest', 'diff_ids'}
            and re.fullmatch(r'sha256:[0-9a-f]{64}', v['config_digest']) and bool(v['diff_ids'])
            and all(re.fullmatch(r'sha256:[0-9a-f]{64}', d) for d in v['diff_ids']) for v in verified.values()))
    receipts = load(root / 'receipts.json')
    check('receipts', set(receipts) == set(STATIONS) and all(set(v) == {'repository', 'initial', 'commit'}
        and all(nonempty(field) for field in v.values()) for v in receipts.values())
        and all(len({v[k] for v in receipts.values()}) == 2 for k in ('repository', 'initial')))
    upload = load(root / 'upload-inputs.json')
    upload_names = {p + '/' + f for p in ('full_initial', 'full_modified') for f in ('upload.pmc', 'sql/dbcfg.sql', 'comps/logic/logics.xml')}
    check('upload_inputs', upload['source_head'] == head and upload['session'] == session and upload['mode'] == 'FULL'
        and nonempty(upload['source']) and set(upload['files']) == upload_names and files_valid(Path(upload['root']), upload['files']))
    static = load(root / 'static-files.json')
    check('built_static_inputs', static['head'] == head and static['session'] == session
        and {'index.html', '.vite/manifest.json'} <= set(static['files'])
        and any(p.endswith('.js') for p in static['files']) and any(p.endswith('.css') for p in static['files'])
        and files_valid(Path(static['root']), static['files']))
    business = load(root / 'business-ids.json')
    check('business_isolation', business['head'] == head and business['session'] == session
        and business['a_scope'] == 'dev-fbe8accb4da11574' and business['b_scope'] == 'dev-0a5e7c9870eaba0b'
        and set(business['a']) == {'workspace_id', 'preview_id', 'submission_id'}
        and set(business['b']) == {'workspace_id', 'initial_id'}
        and all(nonempty(v) for v in business['a'].values()) and all(nonempty(v) for v in business['b'].values())
        and business['a']['workspace_id'] != business['b']['workspace_id'] and business['b']['initial_id'] == receipts['WX-0207']['initial'])
    files = load(root / 'artifacts.json')
    screenshots = {f'{state}-{width}.png' for state in STATES for width in (1280, 1920)}
    check('artifact_inventory', set(files) == {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name != 'artifacts.json'})
    check('mandatory_artifacts', REQUIRED | screenshots <= set(files))
    check('screenshot_set', {p.name for p in root.glob('*.png')} == screenshots)
    shots = load(root / 'screenshot-checks.json')
    check('screenshots_secret_free', len(shots) == 10 and {v['name'] for v in shots} == screenshots
        and all(v['head'] == head and v['session'] == session and v['secret_free'] is True and v['fragment_cleared'] is True for v in shots))
    for name, expected_hash in files.items():
        good = safe_file(root, name) and hexvalue(expected_hash) and sha(root / name) == expected_hash
        check('artifact:' + name, good)
        if copy is not None:
            check('copy:' + name, good and safe_file(copy, name) and sha(copy / name) == expected_hash)
    for name in sorted(screenshots):
        _png.validate_png(root / name, int(name.rsplit('-', 1)[1][:-4]))
        check('complete_png:' + name, True)
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
        result = dict(status='failed', error_class=type(error).__name__, checks=[dict(check='complete_readable_original', status='unknown')])
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('directory_evidence_check=' + result['status'])
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
