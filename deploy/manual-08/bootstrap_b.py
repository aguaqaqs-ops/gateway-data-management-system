"""One-time B directory import and formal hot provisioning; never deletes B."""
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path('/home/dev/gdds-gw-dms-08-v2')
B = ROOT / 'b'
SOURCE = ROOT / 'source'
PYTHON = ROOT / 'tools/python/bin/python3.14'


def call(*args: str, env: dict[str, str]) -> None:
    subprocess.run(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True, timeout=600)


def main() -> None:
    marker = B / 'bootstrap-complete'
    if marker.exists() or marker.is_symlink():
        raise ValueError('B is already provisioned')
    env = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root',
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(SOURCE / 'directory/service'),
           'GDDS_DIRECTORY_DB': str(B / 'private/directory.sqlite'),
           'GDDS_DIRECTORY_GATEWAY_ROOT': str(SOURCE),
           'GDDS_DIRECTORY_GROUPS_FILE': str(B / 'public/groups.json'),
           'GDDS_DIRECTORY_GATEWAY_DIRECTORY_FILE': str(B / 'public/device-directory.json'),
           'GDDS_DIRECTORY_GROUP_ID': 'group-b', 'GDDS_DIRECTORY_ENTRY_DIRECTORY': str(B / 'entry'),
           'GDDS_DIRECTORY_ENTRY_PROJECT': 'gdds08-b-entry',
           'GDDS_DIRECTORY_LOG_DIR': str(B / 'logs/provision')}
    management = (str(PYTHON), str(SOURCE / 'vnext/scripts/manage-processing-groups.py'),
                  '--groups-file', str(B / 'public/groups.json'), '--directory-file', str(B / 'public/device-directory.json'),
                  '--entry-directory', str(B / 'entry'), '--entry-project', 'gdds08-b-entry')
    group = ('docker', 'compose', '--env-file', str(B / 'group/compose.env'), '-p', 'gdds08-b',
             '-f', str(SOURCE / 'vnext/deploy/compose.yaml'), '-f', str(B / 'group/compose-runtime.json'))
    entry = ('docker', 'compose', '--env-file', str(B / 'group/compose.env'), '-p', 'gdds08-b-entry',
             '-f', str(SOURCE / 'vnext/deploy/compose.entry.yaml'))
    if not (B / 'entry/nginx.conf').exists():
        call(*management, 'render-entry', env=env)
    if not (B / 'private/directory.sqlite').exists():
        call(str(PYTHON), '-m', 'gdds_directory', 'import', str(SOURCE / 'deploy/manual-08/catalog-b.csv'), env=env)
    call(*group, 'up', '-d', '--no-build', '--pull', 'never', 'backend', 'worker', env=env)
    call(*entry, 'up', '-d', '--no-build', '--pull', 'never', 'entry', env=env)
    call(str(PYTHON), '-m', 'gdds_directory', 'provision', '--all', env=env)
    call(*management, 'check-groups', '--inspect', env=env)
    with sqlite3.connect(f'file:{B}/private/directory.sqlite?mode=ro', uri=True) as conn:
        rows = conn.execute('SELECT p.device_key, p.project_id, r.current_session, r.initial_node_id, '
                            'r.initial_commit_id FROM projects p JOIN provisioning r USING(device_key) '
                            'WHERE p.removed = 0 ORDER BY p.station_code').fetchall()
    if len(rows) != 4:
        raise ValueError('B catalog does not contain four provisioned devices')
    opener = build_opener(ProxyHandler({}))
    for device, project, raw, initial, commit in rows:
        session = json.loads(raw)
        call(*management, 'status-device', '--device', device, env=env)
        headers = {'Authorization': 'Bearer ' + session['token'],
                   'X-Gateway-Device-Key': hashlib.sha256(device.encode()).hexdigest()}
        with opener.open(Request('http://127.0.0.1:18082/v1/history?limit=100', headers=headers), timeout=15) as response:
            nodes = json.load(response)['nodes']
        if (session['business_project_id'] != project or len(nodes) != 1
                or nodes[0]['baseline_kind'] != 'INITIAL' or nodes[0]['ref_id'] != initial
                or nodes[0]['commit_id'] != commit):
            raise ValueError('B initial history differs')
    call('systemctl', 'start', 'gdds08-b-directory.service', env=env)
    deadline = time.monotonic() + 30
    while True:
        try:
            with opener.open('http://127.0.0.1:18101/api/catalog', timeout=3) as response:
                catalog = json.load(response)
            if len(catalog['projects']) == 4 and all(row['provisioned'] for row in catalog['projects']):
                break
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError('B directory did not become ready')
        time.sleep(.2)
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    os.close(fd)


if __name__ == '__main__':
    main()
