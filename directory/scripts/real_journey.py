#!/usr/bin/env python3
"""Single-node directory acceptance orchestration; no shell/configured commands.

Deployment artifacts are prepared by the existing gateway tools before this
entry. This entry owns their start/stop, and never seeds a device or repository.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

# -I excludes the script directory; load only this committed sibling.
import importlib.util
_process_spec = importlib.util.spec_from_file_location('journey_process', Path(__file__).with_name('journey_process.py'))
_process_module = importlib.util.module_from_spec(_process_spec)
_process_spec.loader.exec_module(_process_module)
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'mcr.microsoft.com/playwright:v1.64.1-noble'
TMP = Path('/home/dev/gdds-test-tmp')
BUSY = Path('/home/dev/gdds-node-busy.d')
STAGES = tuple('J' + str(n) for n in range(8))
DEVICES = {'SZ-0142': ('dev-fbe8accb4da11574', 'prj-fbe8accb4da11574'),
           'WX-0207': ('dev-0a5e7c9870eaba0b', 'prj-0a5e7c9870eaba0b')}


def utc():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def document(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate field')
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=pairs)


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True, timeout=30).strip()


def clean():
    return git('status', '--porcelain', '--untracked-files=all') == ''


def outside(value):
    path = Path(value)
    if not path.is_absolute() or path.resolve() != path or path == ROOT or ROOT in path.parents:
        raise ValueError('absolute tree-external ordinary path required')
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('symlink path refused')
    return path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http(url, headers=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(urllib.request.Request(url, headers=headers or {}), timeout=10) as response:
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError('HTTP response exceeds bound')
            return response.status, data
    except urllib.error.HTTPError as error:
        return error.code, b''


def wait(check, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(.25)
    raise TimeoutError('bounded readiness wait expired')


class Journey:
    def __init__(self, args):
        self.args = args
        self.evidence = outside(args.evidence_dir)
        self.evidence.mkdir(mode=0o700)  # new run only; never overwrite a failure
        self.log = (self.evidence / 'run.log').open('x')
        self.events = (self.evidence / 'run-events.jsonl').open('x')
        self.result = dict(session=args.session, head=args.head, hostname=socket.gethostname(),
            start_utc=utc(), start_head=git('rev-parse', 'HEAD'), clean_start=clean(),
            entry_argv=['directory/scripts/run-real-journey.sh', '--head', args.head, '--session', args.session, '--config', args.config, '--evidence-dir', args.evidence_dir],
            stages={stage: {'status': 'unknown'} for stage in STAGES})
        self.owned = False
        self.lock = None
        self.processes = []
        self.commands = _process_module.ScopedCommands(args.session)
        self.container = 'directory-journey-' + args.session
        self.tool_id = None
        self.started = False
        self.entry_started = False
        self.tokens = []
        self.config = {}
        self.env = {}
        self.compose_args = []
        self.entry_args = []
        self.private = None
        self.record('begin', clean=self.result['clean_start'])

    def record(self, event, **values):
        line = json.dumps(dict(utc=utc(), event=event, head=self.args.head, session=self.args.session, hostname=socket.gethostname(), **values), sort_keys=True) + '\n'
        self.log.write(line)
        self.log.flush()
        self.events.write(line)
        self.events.flush()

    def command(self, label, args, timeout=300, env=None, capture=False):
        # Never log argv/output containing credentials or HTTP response bodies.
        self.record('command_start', label=label)
        try:
            code, output = self.commands.run(args, env=env or self.env or os.environ.copy(),
                cwd=ROOT, stdout=subprocess.PIPE if capture else self.log,
                stderr=self.log, timeout=timeout)
        except BaseException as error:
            self.record('command_abort', label=label, error_class=type(error).__name__)
            raise
        self.record('command_end', label=label, exit=code)
        if code:
            raise RuntimeError('command failed: ' + label)
        return output if capture else ''

    def empty_project(self, project):
        for resource, command in [('containers', ['ps', '-aq']), ('networks', ['network', 'ls', '-q']), ('volumes', ['volume', 'ls', '-q'])]:
            if self.command('reject_existing_' + resource, ['docker', *command,
                    '--filter', 'label=com.docker.compose.project=' + project], capture=True).strip():
                raise ValueError('selected project already has resources')

    def reject_tool_collision(self):
        if self.command('reject_existing_tool', ['docker', 'ps', '-aq', '--filter', 'name=^/' + self.container + '$'], capture=True).strip():
            raise ValueError('tool container name already exists')

    def owned_tool(self):
        cidfile = self.private / 'toolchain.cid' if self.private else None
        if cidfile is None or not cidfile.exists():
            return None
        value = cidfile.read_text().strip()
        if not re.fullmatch('[0-9a-f]{64}', value):
            raise ValueError('invalid owned container receipt')
        data = json.loads(self.command('tool_ownership', ['docker', 'inspect', value], capture=True))[0]
        if (data['Id'] != value or data['Name'] != '/' + self.container
                or data['Config']['Labels'].get('gateway.directory.session') != self.args.session):
            raise ValueError('tool ownership mismatch')
        return value

    def mark(self, stage, **facts):
        self.result['stages'][stage] = dict(status='passed', **facts)
        self.record('stage_complete', stage=stage)

    def management(self, command, *extra):
        return [self.config['python'], ROOT / 'vnext/scripts/manage-processing-groups.py', command,
            '--groups-file', self.config['groups_file'], '--directory-file', self.config['directory_file'],
            '--entry-directory', self.config['entry_directory'], '--entry-project', self.config['entry_project'], *extra]

    def cli(self, label, *args):
        return self.command(label, [self.config['python'], '-B', '-m', 'gdds_directory', *args], env=self.env)

    def snapshot(self):
        ids = self.command('container_ids', [*self.compose_args, 'ps', '-q', 'backend', 'worker'], capture=True).split()
        if len(ids) != 2:
            raise ValueError('exact backend and worker required')
        data = json.loads(self.command('container_state', ['docker', 'inspect', *ids], capture=True))
        return {item['Config']['Labels']['com.docker.compose.service']:
            dict(id=item['Id'], started_at=item['State']['StartedAt'], restarts=item['RestartCount']) for item in data}

    def sessions(self):
        with sqlite3.connect('file:' + str(self.private / 'directory.sqlite') + '?mode=ro', uri=True) as conn:
            rows = conn.execute('SELECT p.station_code,p.device_key,p.project_id,r.current_session,r.repository_id,r.initial_node_id,r.initial_commit_id FROM projects p JOIN provisioning r USING(device_key) ORDER BY p.station_code').fetchall()
        if len(rows) != 2:
            raise ValueError('two local receipts required')
        result = {}
        for station, device, project, raw, repository, initial, commit in rows:
            if (device, project) != DEVICES[station] or not all((raw, repository, initial, commit)):
                raise ValueError('receipt identity mismatch')
            session = json.loads(raw)
            self.tokens.append(session['token'])
            result[station] = dict(session=session, repository=repository, initial=initial, commit=commit)
        if len({v['repository'] for v in result.values()}) != 2 or len({v['initial'] for v in result.values()}) != 2:
            raise ValueError('device receipts are not isolated')
        return result

    def probe(self, sessions, old=False):
        group = self.group
        for station, values in sessions.items():
            session = values['session']
            device, project = DEVICES[station]
            status, raw = http(self.entry_url + '/v1/device-context', {
                'Authorization': 'Bearer ' + session['token'],
                'X-Gateway-Device-Key': hashlib.sha256(device.encode()).hexdigest()})
            good = status == 401 if old else status == 200
            if good and not old:
                body = json.loads(raw)
                good = all(body.get(key) == value for key, value in dict(
                    environment_id=self.groups['environment_id'], group_id=group['group_id'],
                    gateway_device_external_key=device, business_project_id=project,
                    repository_id=values['repository']).items())
            self.record('credential_probe', station=station, kind='old' if old else 'new', status=status, scope_ok=good)
            if not good:
                raise ValueError('credential probe failed')

    def prepare(self):
        if socket.gethostname() != 'gw-dms-test-05' or not re.fullmatch('[0-9a-f]{40}', self.args.head):
            raise ValueError('dedicated 05 node and full HEAD required')
        if self.result['start_head'] != self.args.head or not self.result['clean_start']:
            raise ValueError('clean expected HEAD required')
        config_path = outside(self.args.config)
        info = config_path.stat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600 or not stat.S_ISREG(info.st_mode):
            raise ValueError('private owned config required')
        self.config = document(config_path)
        fields = {'python', 'private_dir', 'groups_file', 'directory_file', 'entry_directory',
            'entry_project', 'group_id', 'runtime_override', 'seed_file',
            'directory_npm_cache', 'directory_npm_archive', 'directory_npm_manifest',
            'gateway_npm_cache', 'gateway_npm_archive', 'gateway_npm_manifest', 'image_identities'}
        if set(self.config) != fields or any(not isinstance(v, str) or not v for v in self.config.values()):
            raise ValueError('strict config fields required')
        for key, value in self.config.items():
            if key not in ('entry_project', 'group_id'):
                outside(value)
        if not all(re.fullmatch('[a-z0-9][a-z0-9-]{1,62}', self.config[k]) for k in ('entry_project', 'group_id')):
            raise ValueError('invalid fixed identifiers')
        if not TMP.is_dir():
            raise ValueError('TMPDIR unavailable')
        BUSY.mkdir()
        self.owned = True
        (BUSY / self.args.session).write_text('purpose=directory-stage2\nstart_utc=' + utc() + '\n')
        self.lock = Path('/tmp/gateway-compose-gate.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if any(p.read_text().strip() == 'dolt' for p in Path('/proc').glob('[0-9]*/comm') if p.exists()):
            raise ValueError('Dolt already running')
        if subprocess.check_output(['docker', 'ps', '-q'], text=True).strip():
            raise ValueError('node has running containers')
        self.groups = document(Path(self.config['groups_file']))
        if len(self.groups['groups']) != 1:
            raise ValueError('one independently prepared group required')
        self.group = self.groups['groups'][0]
        if self.group['group_id'] != self.config['group_id'] or self.group['images']['revision'] != self.args.head:
            raise ValueError('group revision mismatch')
        entry = self.groups['entry']
        if entry['listen_address'] != '127.0.0.1':
            raise ValueError('loopback public test entry required')
        self.entry_url = 'http://127.0.0.1:' + str(entry['listen_port'])
        ports = (8100, 4173, entry['listen_port'], entry['management_port'], self.group['backend_port'])
        if len(set(ports)) != len(ports):
            raise ValueError('test ports overlap')
        if document(Path(self.config['seed_file'])) != {'mappings': []}:
            raise ValueError('fresh empty seed required')
        for port in ports:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', port))
        self.private = outside(self.config['private_dir'])
        self.private.mkdir(mode=0o700)
        self.env = {'PATH': os.environ['PATH'], 'HOME': '/home/dev', 'TMPDIR': str(TMP),
            'UV_OFFLINE': '1', 'CARGO_NET_OFFLINE': 'true', 'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONPATH': str(ROOT / 'directory/service'),
            'GDDS_DIRECTORY_DB': str(self.private / 'directory.sqlite'),
            'GDDS_DIRECTORY_PUBLIC_URL': 'http://127.0.0.1:8100',
            'GDDS_DIRECTORY_GATEWAY_FRONTEND_URL': 'http://127.0.0.1:4173',
            'GDDS_DIRECTORY_LISTEN': '127.0.0.1:8100',
            'GDDS_DIRECTORY_STATIC_DIR': str(self.private / 'static'),
            'GDDS_DIRECTORY_GATEWAY_ROOT': str(ROOT),
            'GDDS_DIRECTORY_GROUPS_FILE': self.config['groups_file'],
            'GDDS_DIRECTORY_GATEWAY_DIRECTORY_FILE': self.config['directory_file'],
            'GDDS_DIRECTORY_GROUP_ID': self.config['group_id'],
            'GDDS_DIRECTORY_ENTRY_DIRECTORY': self.config['entry_directory'],
            'GDDS_DIRECTORY_ENTRY_PROJECT': self.config['entry_project'],
            'GDDS_DIRECTORY_LOG_DIR': str(self.evidence / 'provision'),
            'GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE': self.config['seed_file'],
            'GATEWAY_BACKEND_SESSION_DIRECTORY': self.group['session_directory'],
            'GATEWAY_PROCESSING_GROUPS_DIRECTORY': str(Path(self.config['groups_file']).parent),
            'GATEWAY_P2R2_BEARER_TOKEN_FILE': self.group['repository_token_file'],
            'GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE': self.group['internal_token_file'],
            'GATEWAY_ENTRY_DIRECTORY': self.config['entry_directory'], 'GATEWAY_ENTRY_IMAGE': entry['image']}
        self.compose_args = ['docker', 'compose', '-p', self.group['project'], '-f', str(ROOT / 'vnext/deploy/compose.yaml'), '-f', self.config['runtime_override']]
        self.entry_args = ['docker', 'compose', '-p', self.config['entry_project'], '-f', str(ROOT / 'vnext/deploy/compose.entry.yaml')]
        if self.group['project'] == self.config['entry_project']:
            raise ValueError('group and entry projects overlap')
        self.empty_project(self.group['project'])
        self.empty_project(self.config['entry_project'])
        self.reject_tool_collision()
        self.command('python_version', [self.config['python'], '-c', 'import sys; assert sys.version_info[:3] == (3,14,6)'])
        for prefix, lock in [('directory', ROOT / 'directory/frontend/package-lock.json'), ('gateway', ROOT / 'frontend/package-lock.json')]:
            self.command(prefix + '_cache', [self.config['python'], '-I', ROOT / 'directory/scripts/frontend-inputs.py', 'verify',
                self.config[prefix + '_npm_manifest'], self.config[prefix + '_npm_cache'], self.config[prefix + '_npm_archive'], lock])
        expected = document(Path(self.config['image_identities']))
        refs = [IMAGE, entry['image'], *[self.group['images'][k] for k in ('backend', 'worker', 'repository_service')]]
        if set(expected) != set(refs):
            raise ValueError('exact selected image identity set required')
        verified_images = {}
        for index, ref in enumerate(refs):
            archive = self.private / ('image-' + str(index) + '.tar')
            self.command('image_export', ['docker', 'image', 'save', '-o', archive, ref], timeout=600)
            actual = json.loads(self.command('image_identity', [self.config['python'], '-I', ROOT / 'directory/scripts/docker-save-image-identity.py', archive], capture=True))
            archive.unlink()
            if actual['config_digest'] != expected[ref]['config_digest'] or actual['diff_ids'] != expected[ref]['diff_ids']:
                raise ValueError('selected image identity mismatch')
            verified_images[ref] = {k: actual[k] for k in ('config_digest', 'diff_ids')}
            if ref == IMAGE:
                self.command('fixed_toolchain', [self.config['python'], '-I', ROOT / 'directory/scripts/frontend-inputs.py', 'image', json.dumps(actual)])
        write(self.evidence / 'verified-images.json', verified_images)
        shutil.copyfile(self.config['image_identities'], self.evidence / 'image-identities.json')
        write(self.evidence / 'inputs.json', dict(head=self.args.head, session=self.args.session, hostname=socket.gethostname(),
            images=dict(toolchain=IMAGE, entry=entry['image'], **{k: self.group['images'][k] for k in ('backend', 'worker', 'repository_service')}),
            trees={p: git('rev-parse', 'HEAD:' + p) for p in ('directory', 'frontend', 'vnext')},
            locks={p: digest(ROOT / p) for p in ('directory/service/uv.lock', 'directory/frontend/package-lock.json', 'frontend/package-lock.json')},
            config_sha256=digest(config_path), config_path=str(config_path), config_mode=oct(stat.S_IMODE(info.st_mode)),
            cache_manifests={p: document(Path(self.config[p + '_npm_manifest'])) for p in ('directory', 'gateway')}))

    def run(self):
        self.prepare()
        self.command('deployment_validate', self.management('validate'))
        if document(Path(self.config['directory_file']))['devices'] or document(Path(self.group['session_directory']) / 'session.json')['sessions']:
            raise ValueError('fresh empty target environment required')
        self.empty_project(self.group['project'])
        self.started = True
        self.command('group_up', [*self.compose_args, 'up', '-d', '--no-build', '--pull', 'never', 'backend', 'worker'], timeout=300)
        wait(lambda: http('http://127.0.0.1:' + str(self.group['backend_port']) + '/readyz')[0] == 200)
        self.empty_project(self.config['entry_project'])
        self.entry_started = True
        self.command('entry_up', [*self.entry_args, 'up', '-d', '--no-build', '--pull', 'never', 'entry'])
        wait(lambda: http(self.entry_url + '/healthz')[0] == 200)
        self.command('deployment_inspect', self.management('check-groups', '--inspect'))
        before = self.snapshot()
        write(self.evidence / 'containers-before.json', before)
        fixtures = ROOT / 'directory/journey/fixtures'
        self.cli('import_dry_run', 'import', str(fixtures / 'catalog.csv'), '--dry-run')
        self.cli('import', 'import', str(fixtures / 'catalog.csv'))
        self.cli('status_before', 'status')
        self.mark('J0', initial_unprovisioned=True, deployment_inspected=True, python_and_caches_verified=True, image_identities_verified=True)
        self.cli('provision_dry_run', 'provision', '--stations', str(fixtures / 'stations.txt'), '--dry-run')
        self.cli('provision', 'provision', '--stations', str(fixtures / 'stations.txt'))
        old = self.sessions()
        self.probe(old)
        if before != self.snapshot():
            raise ValueError('hot provision restarted containers')
        write(self.evidence / 'receipts.json', {k: {field: v[field] for field in ('repository', 'initial', 'commit')} for k, v in old.items()})
        self.mark('J1', receipts=True, public_scope=True, unchanged_containers=True)
        self.browser(before, old)

    def browser(self, before, old):
        source = self.private / 'source.tar'
        with source.open('wb') as stream:
            subprocess.run(['git', '-C', str(ROOT), 'archive', self.args.head, 'directory', 'frontend'], stdout=stream, check=True, timeout=30)
        inputs = self.private / 'input'
        for name, sql, logic in [('full_initial', 'sql-baseline.sql', 'logics-1.xml'), ('full_modified', 'sql-initial.sql', 'logics-2.xml')]:
            target = inputs / name
            (target / 'sql').mkdir(parents=True)
            (target / 'comps/logic').mkdir(parents=True)
            (target / 'upload.pmc').write_text('directory-stage2-' + name + '\n')
            shutil.copyfile(ROOT / 'frontend/e2e-real/fixtures/upload-inputs' / sql, target / 'sql/dbcfg.sql')
            shutil.copyfile(ROOT / 'frontend/src/test/fixtures/source/upload-inputs' / logic, target / 'comps/logic/logics.xml')
        write(self.evidence / 'upload-inputs.json', dict(source_head=self.args.head, session=self.args.session, root=str(inputs),
            files={str(p.relative_to(inputs)): digest(p) for p in sorted(inputs.rglob('*')) if p.is_file()},
            mode='FULL', source='frontend/scripts/run-real-backend-e2e.sh full_initial/full_modified'))
        (self.private / 'static').mkdir()
        control = self.private / 'control'
        control.mkdir()
        write(control / 'public-inputs.json', {k: {f: v[f] for f in ('repository', 'initial', 'commit')} for k, v in old.items()})
        self.reject_tool_collision()
        self.command('toolchain_start', ['docker', 'run', '-d', '--init', '--ipc=host', '--pull', 'never',
            '--name', self.container, '--cidfile', str(self.private / 'toolchain.cid'),
            '--label', 'gateway.directory.session=' + self.args.session, '--network', 'host',
            '-v', str(source) + ':/source.tar:ro',
            '-v', self.config['directory_npm_cache'] + ':/directory-cache:ro',
            '-v', self.config['gateway_npm_cache'] + ':/gateway-cache:ro',
            '-v', str(self.private / 'static') + ':/directory-static',
            '-v', str(inputs) + ':/input:ro', '-v', str(control) + ':/control',
            '-v', str(self.evidence) + ':/evidence',
            '-e', 'GATEWAY_FRONTEND_ENTRY_ORIGIN=' + self.entry_url,
            '-e', 'GDDS_JOURNEY_HEAD=' + self.args.head, '-e', 'GDDS_JOURNEY_SESSION=' + self.args.session, IMAGE, 'sleep', 'infinity'])
        self.tool_id = self.owned_tool()
        self.command('offline_builds', ['docker', 'exec', self.container, 'bash', '-euo', 'pipefail', '-c', '''
mkdir -p /tmp/source /tmp/directory-cache /tmp/gateway-cache
 tar -xf /source.tar -C /tmp/source
 cp -a /directory-cache/. /tmp/directory-cache/
 cp -a /gateway-cache/. /tmp/gateway-cache/
 cd /tmp/source/directory/frontend
 npm ci --offline --cache /tmp/directory-cache --no-audit --no-fund
 npm run build
 cp -a dist/. /directory-static/
 cd /tmp/source/frontend
 npm ci --offline --cache /tmp/gateway-cache --no-audit --no-fund
 npm run build
 # Resolve the directory-owned test from this frontend's locked test runner.
 mkdir -p directory-journey
 cp /tmp/source/directory/journey/browser/* directory-journey/
'''], timeout=900)
        static = self.private / 'static'
        write(self.evidence / 'static-files.json', dict(head=self.args.head, session=self.args.session, root=str(static), files={str(p.relative_to(static)): digest(p) for p in sorted(static.rglob('*')) if p.is_file()}))
        self.command('preview_start', ['docker', 'exec', '-d', self.container, 'bash', '-c',
            'cd /tmp/source/frontend && exec npm run preview -- --host 127.0.0.1 --port 4173 > /tmp/preview.log 2>&1'])
        process = subprocess.Popen([self.config['python'], '-B', '-m', 'gdds_directory', 'serve'],
            cwd=ROOT, env=self.env, stdout=self.log, stderr=self.log, start_new_session=True)
        self.processes.append(process)
        wait(lambda: http('http://127.0.0.1:8100/healthz')[0] == 200)
        wait(lambda: http('http://127.0.0.1:4173/')[0] == 200)
        status, raw = http('http://127.0.0.1:8100/api/catalog')
        catalog = json.loads(raw)
        actual = {p['station_code']: p['device_key'] for p in catalog['projects'] if p['provisioned']}
        if status != 200 or actual != {k: v[0] for k, v in DEVICES.items()}:
            raise ValueError('served catalog differs from real DB')
        hidden, _ = http('http://127.0.0.1:8100/.vite/manifest.json')
        if hidden == 200:
            raise ValueError('static manifest exposed')
        self.record('static_served', catalog=True, manifest_hidden=True)
        self.command('browser_typecheck', ['docker', 'exec', self.container, 'bash', '-euo', 'pipefail', '-c',
            'cd /tmp/source/frontend && npx tsc --noEmit --strict --skipLibCheck --target ES2022 --module NodeNext --moduleResolution NodeNext directory-journey/*.ts'], timeout=120)
        browser_log = (self.evidence / 'browser-process.log').open('x')
        browser = subprocess.Popen(['docker', 'exec', self.container, 'bash', '-euo', 'pipefail', '-c',
            'cd /tmp/source/frontend && npx playwright test --config directory-journey/playwright.config.ts'],
            env=self.env, stdout=browser_log, stderr=browser_log, start_new_session=True)
        self.processes.append(browser)
        deadline = time.monotonic() + 1860
        renewed = False
        try:
            while browser.poll() is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError('browser journey deadline expired')
                if (control / 'renew-request').exists() and not renewed:
                    self.cli('renew_sessions', 'provision', '--renew-sessions')
                    new = self.sessions()
                    if any(new[k]['session']['token'] == old[k]['session']['token'] for k in old):
                        raise ValueError('token not rotated')
                    self.probe(new)
                    self.probe(old, old=True)
                    after = self.snapshot()
                    write(self.evidence / 'containers-after.json', after)
                    if after != before:
                        raise ValueError('renewal restarted containers')
                    renewed = True
                    (control / 'renew-complete').write_text('done\n')
                time.sleep(.25)
            self.record('browser_exit', exit=browser.returncode)
            if browser.returncode != 0 or not renewed:
                raise ValueError('browser failed or renewal not completed')
        finally:
            browser_log.close()
        browser_exit = document(self.evidence / 'browser-exit.json')
        if browser_exit != {'head': self.args.head, 'session': self.args.session, 'status': 'passed', 'passed': True}:
            raise ValueError('browser completion missing')
        browser_facts = document(self.evidence / 'browser-facts.json')
        if browser_facts['head'] != self.args.head or browser_facts['session'] != self.args.session:
            raise ValueError('browser run identity mismatch')
        facts = browser_facts['stages']
        if set(facts) != {'J2', 'J3', 'J4', 'J5', 'J6'}:
            raise ValueError('incomplete browser stages')
        for stage, value in facts.items():
            if value.get('status') != 'passed' or any(v is not True for k, v in value.items() if k != 'status'):
                raise ValueError('browser assertion failed')
            self.mark(stage, **{k: v for k, v in value.items() if k != 'status'})
        self.result['stages']['J6'].update(public_new_scope=True, public_old_401=True, unchanged_containers=True)

    def finish(self, primary):
        cleanup_ok = True
        # End browser first, then directory/preview, then only the owned stacks.
        for process in reversed(self.processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=15)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired):
                        cleanup_ok = False
        try:
            self.commands.close()
        except Exception:
            cleanup_ok = False
        commands_stopped = cleanup_ok
        # No resource teardown while an unconfirmed management scope can write.
        if not cleanup_ok:
            self.record('cleanup_management_scopes', status='failed')
        try:
            tool_id = self.owned_tool()
        except Exception:
            tool_id = None
            cleanup_ok = False
        for label, args, condition in [('toolchain_remove', ['docker', 'rm', '-f', tool_id or ''], bool(tool_id)),
                ('entry_down', [*self.entry_args, 'down', '--volumes', '--remove-orphans'], self.entry_started),
                ('group_down', [*self.compose_args, 'down', '--volumes', '--remove-orphans'], self.started)]:
            if condition and commands_stopped:
                try:
                    self.command(label, args, timeout=180)
                except Exception:
                    cleanup_ok = False
        try:
            self.commands.close()
            if self.private is not None and self.command('tool_residual', ['docker', 'ps', '-aq', '--filter', 'name=^/' + self.container + '$'], capture=True).strip():
                cleanup_ok = False
        except Exception:
            cleanup_ok = False
        if self.started:
            for project in (self.group['project'], self.config['entry_project']):
                for resource, subcommand in [('containers', ['ps', '-aq']), ('networks', ['network', 'ls', '-q']), ('volumes', ['volume', 'ls', '-q'])]:
                    try:
                        leftovers = self.command('cleanup_check_' + resource, ['docker', *subcommand,
                            '--filter', 'label=com.docker.compose.project=' + project], capture=True)
                        if leftovers.strip():
                            cleanup_ok = False
                    except Exception:
                        cleanup_ok = False
        if self.started:
            for port in (8100, 4173, self.groups['entry']['listen_port'], self.groups['entry']['management_port'], self.group['backend_port']):
                try:
                    with socket.socket() as sock:
                        sock.bind(('127.0.0.1', port))
                except OSError:
                    cleanup_ok = False
        # Private DB/session documents are not evidence and must remain private.
        # Scan raw evidence using actual old and current tokens without printing any.
        leaks = []
        if self.private is not None and (self.private / 'directory.sqlite').exists():
            try:
                with sqlite3.connect('file:' + str(self.private / 'directory.sqlite') + '?mode=ro', uri=True) as conn:
                    for current, pending in conn.execute('SELECT current_session,pending_session FROM provisioning'):
                        for raw in (current, pending):
                            if raw:
                                self.tokens.append(json.loads(raw)['token'])
                for filename in (self.group['internal_token_file'], self.group['repository_token_file']):
                    token = Path(filename).read_text().strip()
                    if token:
                        self.tokens.append(token)
            except Exception:
                cleanup_ok = False
        for path in sorted(self.evidence.rglob('*')):
            if path.is_file() and path.name != 'run.log':
                data = path.read_bytes()
                hits = sum(data.count(token.encode()) for token in set(self.tokens))
                hits += len(re.findall(rb'gdds-handoff(?:=|%3[dD])', data))
                if hits:
                    leaks.append({'file': str(path.relative_to(self.evidence)), 'hits': hits})
        self.log.flush()
        log_hits = sum((self.evidence / 'run.log').read_bytes().count(token.encode()) for token in set(self.tokens))
        log_hits += len(re.findall(rb'gdds-handoff(?:=|%3[dD])', (self.evidence / 'run.log').read_bytes()))
        if log_hits:
            leaks.append({'file': 'run.log', 'hits': log_hits})
        self.result['credential_scan'] = {'status': 'failed' if leaks else 'passed', 'leaks': leaks}
        if leaks:
            cleanup_ok = False
            # Never export leaked evidence. Revoke owned runtime sessions even if
            # down failed; diagnostics remain untouched for owner investigation.
            try:
                (Path(self.group['session_directory']) / 'session.json').write_text('{"sessions":[]}')
            except OSError:
                pass
        self.result.update(end_hostname=socket.gethostname(), end_utc=utc(), end_head=git('rev-parse', 'HEAD'), clean_end=clean(),
            original_exit=primary, cleanup_status='passed' if cleanup_ok else 'failed')
        if (self.evidence / 'inputs.json').exists():
            self.result['locks_end'] = {p: digest(ROOT / p) for p in document(self.evidence / 'inputs.json')['locks']}
            if self.result['locks_end'] != document(self.evidence / 'inputs.json')['locks']:
                cleanup_ok = False
        if self.result['end_head'] != self.args.head or not self.result['clean_end']:
            cleanup_ok = False
        if self.owned and cleanup_ok:
            if self.lock is not None:
                self.lock.close()
            try:
                (BUSY / self.args.session).unlink()
                BUSY.rmdir()
                self.owned = False
            except OSError:
                cleanup_ok = False
        elif self.owned:
            with (BUSY / self.args.session).open('a') as marker:
                marker.write('cleanup_status=failed\n')
        self.result['cleanup_status'] = 'passed' if cleanup_ok else 'failed'
        self.result['stages']['J7'] = {'status': 'passed' if cleanup_ok else 'failed', 'resources_stopped': cleanup_ok, 'occupancy_released': not self.owned}
        code = 0 if primary == 0 and cleanup_ok and not leaks else 1
        self.result['exit'] = code
        self.record('end', exit=code, original_exit=primary, cleanup_ok=cleanup_ok)
        self.result['end_utc'] = utc()
        self.log.close()
        self.events.close()
        # The finalized original log is hashed only after its end record.
        write(self.evidence / 'run-result.json', self.result)
        artifacts = {str(p.relative_to(self.evidence)): digest(p) for p in sorted(self.evidence.rglob('*')) if p.is_file() and p.name != 'artifacts.json'}
        write(self.evidence / 'artifacts.json', artifacts)
        return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--head', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--evidence-dir', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9-]{1,62}', args.session):
        parser.error('invalid session label')
    journey = Journey(args)
    primary = 1
    def interrupted(_signal, _frame):
        raise InterruptedError('run interrupted')
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupted)
    try:
        journey.run()
        primary = 0
    except BaseException as error:
        # Exception strings and tracebacks can contain URLs, auth or session data.
        journey.record('failure', error_class=type(error).__name__)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
    return journey.finish(primary)


if __name__ == '__main__':
    raise SystemExit(main())
