"""Inspect actual CT110 container mounts, networks and published ports."""
import json
import subprocess
from pathlib import Path

ROOT = Path('/home/dev/gdds-gw-dms-08-v2')


def main() -> None:
    ids = subprocess.check_output(['docker', 'ps', '-aq'], text=True).split()
    containers = json.loads(subprocess.check_output(['docker', 'inspect', *ids], text=True)) if ids else []
    expected = {'gdds08-a': {'backend', 'worker', 'repository-service'}, 'gdds08-a-entry': {'entry'},
                'gdds08-b': {'backend', 'worker', 'repository-service'}, 'gdds08-b-entry': {'entry'}}
    found = {project: set() for project in expected}
    for container in containers:
        labels = container['Config'].get('Labels') or {}
        project = labels.get('com.docker.compose.project')
        if project not in expected:
            for mount in container['Mounts']:
                source = Path(mount['Source'])
                for scope in (ROOT / 'a', ROOT / 'b'):
                    if source == scope or scope in source.parents or source in scope.parents:
                        raise ValueError('foreign container refers to a manual scope')
            continue
        service = labels.get('com.docker.compose.service')
        if service not in expected[project] or service in found[project] or not container['State']['Running']:
            raise ValueError('unexpected, duplicate or stopped manual service')
        found[project].add(service)
        scope_name = 'a' if project in ('gdds08-a', 'gdds08-a-entry') else 'b'
        scope = ROOT / scope_name
        for mount in container['Mounts']:
            source = Path(mount['Source'])
            if mount['Type'] != 'bind' or scope not in source.parents or source.resolve() != source:
                raise ValueError('manual service mount is outside its scope')
        networks = set(container['NetworkSettings']['Networks'])
        if networks != ({'host'} if project.endswith('-entry') else {project + '_default'}):
            raise ValueError('manual service network differs')
        if not project.endswith('-entry'):
            ident = container['Id']
            pid = container['State']['Pid']
            settings = container['HostConfig']
            entries = Path(f'/proc/{pid}/cgroup').read_text().splitlines()
            paths = [line.split(':', 2)[2] for line in entries if line.startswith('0::')]
            if len(paths) != 1 or Path(paths[0]).name != f'docker-{ident}.scope' or '..' in Path(paths[0]).parts:
                raise ValueError('manual service cgroup differs')
            cgroup = Path('/sys/fs/cgroup') / paths[0].lstrip('/')
            systemd_swap = subprocess.check_output(['systemctl', 'show', f'docker-{ident}.scope',
                                                    '--property=MemorySwapMax', '--value'], text=True).strip()
            if (settings['MemorySwap'] != settings['Memory']
                    or (cgroup / 'memory.max').read_text().strip() != str(settings['Memory'])
                    or (cgroup / 'memory.swap.max').read_text().strip() != '0' or systemd_swap != '0'):
                raise ValueError('manual service memory or swap limit differs')
        ports = container['HostConfig'].get('PortBindings') or {}
        if service == 'backend':
            expected_port = '18000' if scope_name == 'a' else '18001'
            if ports != {'8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': expected_port}]}:
                raise ValueError('manual backend published port differs')
        elif ports:
            raise ValueError('unexpected published port')
    if found != expected:
        raise ValueError('manual project services are incomplete')
    print('manual container mounts, networks, published ports and zero-swap limits are verified')


if __name__ == '__main__':
    main()
