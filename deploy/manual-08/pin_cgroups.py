"""Keep Docker's zero-swap limit registered with systemd on CT110."""
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ('a', 'b'):
        raise ValueError('a fixed manual environment is required')
    project = 'gdds08-' + sys.argv[1]
    if subprocess.check_output(['docker', 'info', '--format', '{{.CgroupDriver}}'], text=True).strip() != 'systemd':
        raise ValueError('the systemd cgroup driver is required')
    ids = subprocess.check_output(['docker', 'ps', '-q', '--filter',
                                   'label=com.docker.compose.project=' + project], text=True).split()
    if len(ids) != 3:
        raise ValueError('the three fixed group containers must be running')
    containers = json.loads(subprocess.check_output(['docker', 'inspect', *ids], text=True))
    found = set()
    for container in containers:
        labels = container['Config'].get('Labels') or {}
        role = labels.get('com.docker.compose.service')
        if role not in {'backend', 'worker', 'repository-service'} or role in found:
            raise ValueError('unexpected or duplicate service')
        found.add(role)
        ident = container['Id']
        pid = container['State']['Pid']
        settings = container['HostConfig']
        if not container['State']['Running'] or pid <= 0 or settings['Memory'] <= 0 or settings['MemorySwap'] != settings['Memory']:
            raise ValueError('container memory settings differ')
        entries = Path(f'/proc/{pid}/cgroup').read_text().splitlines()
        paths = [line.split(':', 2)[2] for line in entries if line.startswith('0::')]
        if len(paths) != 1 or Path(paths[0]).name != f'docker-{ident}.scope' or '..' in Path(paths[0]).parts:
            raise ValueError('container cgroup scope differs')
        cgroup = Path('/sys/fs/cgroup') / paths[0].lstrip('/')
        if (cgroup / 'memory.max').read_text().strip() != str(settings['Memory']) or (cgroup / 'memory.swap.max').read_text().strip() != '0':
            raise ValueError('container cgroup limit already differs')
        subprocess.run(['systemctl', 'set-property', '--runtime', f'docker-{ident}.scope',
                        'MemorySwapMax=0'], check=True, timeout=30, stdout=subprocess.DEVNULL)
        if (cgroup / 'memory.swap.max').read_text().strip() != '0':
            raise ValueError('zero-swap property was not applied')
    print(project + ': systemd zero-swap limits confirmed')


if __name__ == '__main__':
    main()
