"""Create separate TLS keys for the two manual environments."""
import subprocess
from pathlib import Path

ROOT = Path('/home/dev/gdds-gw-dms-08-v2')


def main() -> None:
    if ROOT.resolve() != ROOT:
        raise ValueError('deployment root is redirected')
    for name in ('a', 'b'):
        scope = ROOT / name
        if scope.resolve() != scope or not scope.is_dir():
            raise ValueError('scope is unavailable or redirected')
        tls = scope / 'tls'
        tls.mkdir(mode=0o755)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-days', '3650',
                        '-subj', '/CN=gw-dms-08.local', '-addext',
                        'subjectAltName=IP:192.168.233.209,IP:10.78.0.3,IP:10.79.0.3',
                        '-keyout', str(tls / 'key.pem'), '-out', str(tls / 'cert.pem')],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=60)
        (tls / 'key.pem').chmod(0o600)
        (tls / 'cert.pem').chmod(0o644)


if __name__ == '__main__':
    main()
