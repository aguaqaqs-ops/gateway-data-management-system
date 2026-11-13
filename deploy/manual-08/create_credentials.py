"""Create independent HTTPS and access credentials, without printing them."""
import grp
import os
import pwd
import secrets
import subprocess
from pathlib import Path

ROOT = Path('/home/dev/gdds-gw-dms-08-v2')


def main() -> None:
    if ROOT.resolve() != ROOT:
        raise ValueError('deployment root is redirected')
    web_gid = grp.getgrnam('www-data').gr_gid
    dev = pwd.getpwnam('dev')
    output = ROOT / 'credentials'
    output.mkdir(mode=0o700)
    os.chown(output, dev.pw_uid, dev.pw_gid)
    access = []
    for name in ('a', 'b'):
        scope = ROOT / name
        if scope.resolve() != scope or not scope.is_dir():
            raise ValueError('scope is unavailable or redirected')
        tls = scope / 'tls'
        auth = scope / 'credentials'
        tls.mkdir(mode=0o755)
        auth.mkdir(mode=0o750)
        os.chown(auth, 0, web_gid)
        auth.chmod(0o750)
        password = secrets.token_urlsafe(24)
        hashed = subprocess.run(['openssl', 'passwd', '-6', '-stdin'], input=password + '\n',
                                text=True, capture_output=True, check=True, timeout=30).stdout.strip()
        if not hashed.startswith('$6$'):
            raise ValueError('password hash creation failed')
        htpasswd = auth / 'htpasswd'
        fd = os.open(htpasswd, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write('manual-' + name + ':' + hashed + '\n')
        os.chown(htpasswd, 0, web_gid)
        htpasswd.chmod(0o640)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-days', '3650',
                        '-subj', '/CN=gw-dms-08.local', '-addext', 'subjectAltName=IP:192.168.233.209',
                        '-keyout', str(tls / 'key.pem'), '-out', str(tls / 'cert.pem')],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=60)
        (tls / 'key.pem').chmod(0o600)
        (tls / 'cert.pem').chmod(0o644)
        access.append(f'环境 {name.upper()} 用户名: manual-{name}\n密码: {password}\n')
    path = output / 'access.txt'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write('\n'.join(access))
    os.chown(path, dev.pw_uid, dev.pw_gid)
    path.chmod(0o600)


if __name__ == '__main__':
    main()
