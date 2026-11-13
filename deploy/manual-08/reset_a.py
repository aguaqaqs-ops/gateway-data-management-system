"""Fixed-target reset for CT110's disposable single-device environment.

This executable is intended to be called only by reset_manager.py. It never
accepts caller-provided projects or paths. A failed preflight changes no data.
"""

import json
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path('/home/dev/gdds-gw-dms-08-v2')
A = ROOT / 'a'
SOURCE = ROOT / 'source'
PYTHON = ROOT / 'tools' / 'python' / 'bin' / 'python3.14'
SLOTS = ('be-durable', 'be-canonical', 'be-comparison', 'be-export', 'be-scratch',
         'be-metadata', 'rs-repository', 'rs-artifacts', 'rs-scratch', 'rs-metadata')
OWNED_PROJECTS = {'gdds08-a', 'gdds08-a-entry'}


def call(*argv: str, env: dict[str, str] | None = None, timeout: int = 360) -> str:
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env, timeout=timeout,
                            check=True)
    return result.stdout


def no_redirect(path: Path) -> None:
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('unexpected redirected path')


def no_nested_mounts(path: Path) -> None:
    with open('/proc/self/mountinfo', encoding='utf-8') as stream:
        for line in stream:
            encoded = line.split()[4]
            mount = Path(re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), encoded))
            if mount == path or path in mount.parents:
                raise ValueError('unexpected mount within reset scope')


def inspect_scope(*, allow_owned: bool) -> None:
    ids = call('docker', 'ps', '-aq').split()
    if not ids:
        return
    containers = json.loads(call('docker', 'inspect', *ids))
    for container in containers:
        project = (container['Config'].get('Labels') or {}).get('com.docker.compose.project')
        if project in OWNED_PROJECTS and not allow_owned:
            raise ValueError('target containers remain')
        for mount in container['Mounts']:
            source = Path(mount['Source'])
            overlaps_a = source == A or A in source.parents or source in A.parents
            if project in OWNED_PROJECTS:
                if mount['Type'] != 'bind' or not (source == A or A in source.parents):
                    raise ValueError('target project has an unexpected mount')
            elif overlaps_a:
                raise ValueError('another project references the reset scope')


def validate_roots() -> None:
    for path in (ROOT, A, A / 'group', A / 'group' / 'roots', A / 'entry', A / 'private',
                 A / 'group/storage-layout.json', A / 'group/resource-profile.json',
                 A / 'group/compose-runtime.json', A / 'group/compose.env',
                 A / 'group/session', A / 'public'):
        no_redirect(path)
    layout = json.loads((A / 'group' / 'storage-layout.json').read_text())
    if layout['environment_id'] != 'gw08-a' or layout['group_id'] != 'group-a':
        raise ValueError('unexpected storage identity')
    roots = layout['roots']
    if set(roots) != set(SLOTS):
        raise ValueError('unexpected storage slots')
    for index, slot in enumerate(SLOTS, 1):
        path = A / 'group' / 'roots' / slot
        no_redirect(path)
        no_nested_mounts(path)
        if roots[slot]['source'] != str(path) or roots[slot]['storage_id'] != f'{index:032x}':
            raise ValueError('unexpected storage binding')
        if path.exists() and any(path.iterdir()):
            marker_path = path / '.gateway-storage.json'
            no_redirect(marker_path)
            marker = json.loads(marker_path.read_text())
            expected = {'schema_version': 1, 'environment_id': 'gw08-a', 'group_id': 'group-a',
                        'slot': slot, 'storage_id': f'{index:032x}'}
            if marker != expected:
                raise ValueError('storage marker differs')
    no_nested_mounts(A / 'group' / 'roots')
    no_nested_mounts(A / 'entry')
    no_nested_mounts(A / 'private')


def validate_compose(group: tuple[str, ...], entry: tuple[str, ...], env: dict[str, str]) -> None:
    for args, project, services in ((group, 'gdds08-a', {'backend', 'worker', 'repository-service'}),
                                    (entry, 'gdds08-a-entry', {'entry'})):
        config = json.loads(call(*args, 'config', '--format', 'json', env=env))
        if config['name'] != project or set(config['services']) != services:
            raise ValueError('unexpected compose project or service')
        for name, service in config['services'].items():
            if service.get('container_name') or service.get('volumes_from'):
                raise ValueError('unsupported shared container resource')
            if project == 'gdds08-a-entry' and service.get('network_mode') != 'host':
                raise ValueError('entry network differs')
            if project == 'gdds08-a' and service.get('network_mode'):
                raise ValueError('unexpected group network mode')
            for mount in service.get('volumes', []):
                source = Path(mount.get('source', ''))
                if mount['type'] != 'bind' or not source.is_absolute() or A not in source.parents:
                    raise ValueError('compose mount escapes environment A')
                no_redirect(source)
            ports = service.get('ports', [])
            if name == 'backend':
                if len(ports) != 1 or str(ports[0].get('published')) != '18000' or ports[0].get('host_ip') != '127.0.0.1' or ports[0].get('target') != 8000:
                    raise ValueError('backend port differs')
            elif ports:
                raise ValueError('unexpected published service port')
        for secret in config.get('secrets', {}).values():
            path = Path(secret.get('file', ''))
            if not path.is_absolute() or A not in path.parents:
                raise ValueError('secret escapes environment A')
            no_redirect(path)
        if project == 'gdds08-a':
            networks = config.get('networks', {})
            if set(networks) != {'default'} or networks['default'].get('name') != 'gdds08-a_default' or networks['default'].get('external'):
                raise ValueError('unexpected group network')


def atomic_json(path: Path, value: object) -> None:
    no_redirect(path)
    temporary = path.with_name(path.name + '.reset-tmp')
    no_redirect(temporary)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main() -> None:
    env = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
           'HOME': '/root', 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONPATH': str(SOURCE / 'directory/service'),
           'GDDS_DIRECTORY_DB': str(A / 'private/directory.sqlite'),
           'GDDS_DIRECTORY_GATEWAY_ROOT': str(SOURCE),
           'GDDS_DIRECTORY_GROUPS_FILE': str(A / 'public/groups.json'),
           'GDDS_DIRECTORY_GATEWAY_DIRECTORY_FILE': str(A / 'public/device-directory.json'),
           'GDDS_DIRECTORY_GROUP_ID': 'group-a',
           'GDDS_DIRECTORY_ENTRY_DIRECTORY': str(A / 'entry'),
           'GDDS_DIRECTORY_ENTRY_PROJECT': 'gdds08-a-entry',
           'GDDS_DIRECTORY_LOG_DIR': str(A / 'logs/provision')}
    group = ('docker', 'compose', '--env-file', str(A / 'group/compose.env'), '-p', 'gdds08-a',
             '-f', str(SOURCE / 'vnext/deploy/compose.yaml'), '-f', str(A / 'group/compose-runtime.json'))
    entry = ('docker', 'compose', '--env-file', str(A / 'group/compose.env'), '-p', 'gdds08-a-entry',
             '-f', str(SOURCE / 'vnext/deploy/compose.entry.yaml'))
    management = (str(PYTHON), str(SOURCE / 'vnext/scripts/manage-processing-groups.py'),
                  '--groups-file', str(A / 'public/groups.json'), '--directory-file', str(A / 'public/device-directory.json'),
                  '--entry-directory', str(A / 'entry'), '--entry-project', 'gdds08-a-entry')
    renderer = (str(PYTHON), str(SOURCE / 'vnext/scripts/render-runtime-config.py'),
                '--storage-layout', str(A / 'group/storage-layout.json'),
                '--resource-profile', str(A / 'group/resource-profile.json'))

    validate_roots()
    validate_compose(group, entry, env)
    inspect_scope(allow_owned=True)
    print('stopping', flush=True)
    call(*entry, 'down', '--timeout', '180', env=env)
    call('systemctl', 'stop', 'gdds08-a-directory.service', env=env)
    call(*group, 'down', '--timeout', '180', env=env, timeout=600)
    inspect_scope(allow_owned=False)
    validate_roots()
    print('rebuilding', flush=True)
    for slot in SLOTS:
        path = A / 'group/roots' / slot
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(mode=0o777)
        path.chmod(0o777)
    for name in ('directory.sqlite', 'directory.sqlite-wal', 'directory.sqlite-shm'):
        path = A / 'private' / name
        no_redirect(path)
        path.unlink(missing_ok=True)
    if (A / 'entry').exists():
        shutil.rmtree(A / 'entry')
    (A / 'entry').mkdir(mode=0o755)
    atomic_json(A / 'group/session/session.json', {'sessions': []})
    atomic_json(A / 'group/seed.json', {'mappings': []})
    atomic_json(A / 'public/device-directory.json', {'schema_version': 1, 'environment_id': 'gw08-a', 'devices': []})
    call(*renderer, 'init-layout', env=env)
    call(str(PYTHON), '-m', 'gdds_directory', 'import', str(SOURCE / 'deploy/manual-08/catalog-a.csv'), env=env)
    call(str(PYTHON), *management[1:], 'render-entry', env=env)
    validate_compose(group, entry, env)
    call(*group, 'up', '-d', '--no-build', '--pull', 'never', 'backend', 'worker', env=env, timeout=600)
    call(str(PYTHON), str(SOURCE / 'deploy/manual-08/pin_cgroups.py'), 'a', env=env)
    call(*entry, 'up', '-d', '--no-build', '--pull', 'never', 'entry', env=env, timeout=600)
    print('provisioning', flush=True)
    call(str(PYTHON), '-m', 'gdds_directory', 'provision', '--all', env=env, timeout=600)
    call('systemctl', 'start', 'gdds08-a-directory.service', env=env)
    print('checking', flush=True)
    call(str(PYTHON), *management[1:], 'check-groups', '--inspect', env=env, timeout=600)
    with sqlite3.connect(f'file:{A}/private/directory.sqlite?mode=ro', uri=True) as conn:
        rows = conn.execute('SELECT p.device_key, p.project_id, r.current_session, r.initial_node_id, '
                            'r.initial_commit_id FROM projects p JOIN provisioning r USING(device_key) '
                            'WHERE p.station_code = ? AND p.removed = 0', ('TEST-SINGLE-001',)).fetchall()
    if len(rows) != 1:
        raise ValueError('single-device provisioning missing')
    device, project, raw, initial, commit = rows[0]
    session = json.loads(raw)
    call(str(PYTHON), *management[1:], 'status-device', '--device', device, env=env)
    opener = build_opener(ProxyHandler({}))
    headers = {'Authorization': 'Bearer ' + session['token'],
               'X-Gateway-Device-Key': hashlib.sha256(device.encode()).hexdigest()}
    request = Request('http://127.0.0.1:18080/v1/history?limit=100', headers=headers)
    with opener.open(request, timeout=15) as response:
        history = json.load(response)
    nodes = history['nodes']
    if (session['business_project_id'] != project or len(nodes) != 1
            or nodes[0]['baseline_kind'] != 'INITIAL' or nodes[0]['ref_id'] != initial
            or nodes[0]['commit_id'] != commit):
        raise ValueError('initial history differs')
    deadline = time.monotonic() + 30
    while True:
        try:
            with opener.open('http://127.0.0.1:18100/healthz', timeout=3) as response:
                if response.status == 200:
                    break
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError('directory did not become ready')
        time.sleep(.2)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, sqlite3.Error, subprocess.SubprocessError):
        sys.exit(1)
