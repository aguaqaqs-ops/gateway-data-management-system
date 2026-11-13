"""Prepare two new, fixed, isolated CT110 manual deployments.

This does not start services or delete existing data. Run once on the target
host after installing the exact source, host Python dependencies and images.
"""

import json
import os
import re
import secrets
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path('/home/dev/gdds-gw-dms-08-v2')
SOURCE = ROOT / 'source'
PYTHON = ROOT / 'tools/python/bin/python3.14'
sys.path.insert(0, str(SOURCE / 'vnext/scripts'))
import host_runtime_config as host  # noqa: E402

GIB = 1024 ** 3
HOST_BUDGET = {'memory_bytes': 96 * GIB, 'cpu_count': 16,
               'shared_memory_reserve_bytes': 8 * GIB, 'shared_cpu_reserve': 2}


def write(path: Path, value: object, mode: int = 0o644) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(json.dumps(value) + '\n')
    path.chmod(mode)


def available(port: int) -> None:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))


def execute(argv: list[str], env: dict[str, str]) -> None:
    subprocess.run(argv, env=env, check=True, timeout=300)


def prepare(name: str, revision: str, observed: list) -> None:
    scope = ROOT / name
    group_id = 'group-' + name
    environment_id = 'gw08-' + name
    group = scope / 'group'
    for path in (scope, group, group / 'roots', group / 'session', scope / 'public',
                 scope / 'entry', scope / 'logs', scope / 'logs/provision'):
        path.mkdir(mode=0o755)
    scope.chmod(0o711)
    group.chmod(0o700)
    (scope / 'private').mkdir(mode=0o700)
    storage = json.loads((SOURCE / 'vnext/fixtures/runtime-config/v1/storage-layout.json').read_bytes())
    profile = json.loads((SOURCE / 'vnext/fixtures/runtime-config/v1/resource-profile.json').read_bytes())
    storage.update(environment_id=environment_id, group_id=group_id, filesystems={})
    profile.update(environment_id=environment_id, group_id=group_id, host_budget=HOST_BUDGET)
    for slot, item in storage['roots'].items():
        path = group / 'roots' / slot
        path.mkdir(mode=0o777)
        path.chmod(0o777)
        mount = max((m for m in observed if Path(m.target) == path or Path(m.target) in path.parents),
                    key=lambda m: len(m.target))
        fs_id = 'fs-' + str(mount.mount_id)
        storage['filesystems'][fs_id] = {'mountpoint': mount.target, 'expected_source': mount.source,
                                          'min_free_bytes': 5 * GIB, 'min_free_fraction': 0.1}
        item.update(source=str(path), filesystem_id=fs_id)
    layout = group / 'storage-layout.json'
    resources = group / 'resource-profile.json'
    write(layout, storage, 0o444)
    write(resources, profile, 0o444)
    host.initialize_host(host.DeploymentConfig.load(layout, resources))
    write(group / 'seed.json', {'mappings': []})
    write(group / 'session/session.json', {'sessions': []})
    for token in ('internal.token', 'repository.token'):
        (group / token).write_text(secrets.token_urlsafe(48) + '\n')
        (group / token).chmod(0o644)
    short = revision[:12]
    images = {'backend': 'gdds08-backend:' + short, 'worker': 'gdds08-worker:' + short,
              'repository_service': 'gdds08-repository:' + short, 'revision': revision}
    ports = {'a': (18000, 18080, 18081), 'b': (18001, 18082, 18083)}
    backend_port, entry_port, management_port = ports[name]
    groups = {'schema_version': 1, 'environment_id': environment_id, 'host': HOST_BUDGET,
              'entry': {'listen_address': '127.0.0.1', 'listen_port': entry_port,
                        'management_port': management_port, 'image': 'nginx:1.28.0',
                        'memory_limit_bytes': 512 * 1024**2, 'cpu_limit': 1},
              'groups': [{'group_id': group_id, 'project': 'gdds08-' + name,
                          'backend_port': backend_port, 'storage_config': str(layout),
                          'resource_config': str(resources), 'session_directory': str(group / 'session'),
                          'internal_token_file': str(group / 'internal.token'),
                          'repository_token_file': str(group / 'repository.token'), 'images': images}]}
    groups_file = scope / 'public/groups.json'
    directory_file = scope / 'public/device-directory.json'
    write(groups_file, groups)
    write(directory_file, {'schema_version': 1, 'environment_id': environment_id, 'devices': []})
    values = {'GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE': str(group / 'seed.json'),
              'GATEWAY_BACKEND_SESSION_DIRECTORY': str(group / 'session'),
              'GATEWAY_PROCESSING_GROUPS_DIRECTORY': str(scope / 'public'),
              'GATEWAY_P2R2_BEARER_TOKEN_FILE': str(group / 'repository.token'),
              'GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE': str(group / 'internal.token'),
              'GATEWAY_ENTRY_DIRECTORY': str(scope / 'entry'), 'GATEWAY_ENTRY_IMAGE': 'nginx:1.28.0'}
    (group / 'compose.env').write_text(''.join(k + '=' + v + '\n' for k, v in values.items()))
    (group / 'compose.env').chmod(0o600)
    env = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
           'HOME': '/root', 'PYTHONDONTWRITEBYTECODE': '1'}
    execute([str(PYTHON), str(SOURCE / 'vnext/scripts/render-runtime-config.py'),
             '--storage-layout', str(layout), '--resource-profile', str(resources), 'render',
             '--groups-file', str(groups_file), '--directory-file', str(directory_file),
             '--group', group_id, '--output', str(group / 'compose-runtime.json')], env)
    execute([str(PYTHON), str(SOURCE / 'vnext/scripts/manage-processing-groups.py'), 'check-groups',
             '--groups-file', str(groups_file), '--directory-file', str(directory_file),
             '--entry-directory', str(scope / 'entry'), '--entry-project', 'gdds08-' + name + '-entry'], env)


def main() -> None:
    if socket.gethostname() != 'gw-dms-08':
        raise ValueError('this deployment is fixed to gw-dms-08')
    if ROOT.resolve() != ROOT or not ROOT.is_dir() or (ROOT / 'a').exists() or (ROOT / 'b').exists():
        raise ValueError('target root must be new and unredirected')
    revision = (ROOT / 'revision').read_text().strip()
    if re.fullmatch('[0-9a-f]{40}', revision) is None:
        raise ValueError('full source revision required')
    actual = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain'], text=True).strip()
    if actual != revision or dirty:
        raise ValueError('clean deployed source must match its revision')
    for image in ('gdds08-backend:' + revision[:12], 'gdds08-worker:' + revision[:12],
                  'gdds08-repository:' + revision[:12]):
        actual_revision = subprocess.check_output(
            ['docker', 'image', 'inspect', '--format', '{{index .Config.Labels "org.opencontainers.image.revision"}}', image],
            text=True).strip()
        if actual_revision != revision:
            raise ValueError('image revision differs from source')
    subprocess.run(['docker', 'image', 'inspect', 'nginx:1.28.0'], stdout=subprocess.DEVNULL, check=True)
    if len(os.sched_getaffinity(0)) < 16 or os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') < 96 * GIB:
        raise ValueError('insufficient host capacity')
    # Two standard group envelopes, two entry processes, and one shared reserve.
    if 2 * (32 + 2 + 4) * GIB + 2 * 512 * 1024**2 + 8 * GIB > HOST_BUDGET['memory_bytes']:
        raise ValueError('aggregate memory budget exceeded')
    if 2 * (2 + 1 + 2) + 2 + 2 > HOST_BUDGET['cpu_count']:
        raise ValueError('aggregate CPU budget exceeded')
    for port in (18000, 18001, 18080, 18081, 18082, 18083, 18100, 18101, 18991, 8443, 9443, 10443):
        available(port)
    observed = host.mounts()
    prepare('a', revision, observed)
    prepare('b', revision, observed)


if __name__ == '__main__':
    main()
