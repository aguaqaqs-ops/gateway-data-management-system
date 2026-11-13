"""Loopback-only controller for the fixed 08 single-device reset.

The HTTPS reverse proxy owns authentication. This service is deployment-only;
it is not a gateway API and accepts neither command arguments nor paths.
"""

import fcntl
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path('/home/dev/gdds-gw-dms-08-v2')
STATUS = ROOT / 'management' / 'reset-status.json'
LOCK = ROOT / 'management' / 'reset.lock'
COMMAND = ROOT / 'ops' / 'reset-a'
ORIGIN = 'https://192.168.233.209:8443'
STAGES = {'stopping', 'rebuilding', 'provisioning', 'checking'}


def save(value: dict[str, str]) -> None:
    temporary = STATUS.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, STATUS)


def read_status() -> dict[str, str]:
    try:
        value = json.loads(STATUS.read_text(encoding='utf-8'))
        if value.get('state') in {'idle', 'running', 'success', 'failed'}:
            return {'state': value['state'], 'stage': value.get('stage', '')}
    except FileNotFoundError:
        return {'state': 'idle', 'stage': ''}
    except (OSError, ValueError, AttributeError):
        pass
    return {'state': 'failed', 'stage': 'status-unreadable'}


def acquire() -> int | None:
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        os.close(fd)
        return None


def status() -> dict[str, str]:
    fd = acquire()
    if fd is None:
        value = read_status()
        return value if value['state'] == 'running' else {'state': 'running', 'stage': ''}
    try:
        value = read_status()
        if value['state'] == 'running':
            value = {'state': 'failed', 'stage': 'interrupted'}
            save(value)
        return value
    finally:
        os.close(fd)


def run(fd: int) -> None:
    last_stage = 'stopping'
    try:
        # The fixed executable inherits the lock: an interrupted controller
        # cannot admit another reset while the original child is still alive.
        with subprocess.Popen([str(COMMAND)], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, pass_fds=(fd,)) as child:
            assert child.stdout is not None
            for line in child.stdout:
                stage = line.strip()
                if stage in STAGES:
                    last_stage = stage
                    save({'state': 'running', 'stage': stage})
            result = child.wait()
        save({'state': 'success' if result == 0 else 'failed',
              'stage': '' if result == 0 else last_stage})
    except (OSError, ValueError):
        save({'state': 'failed', 'stage': last_stage})
    finally:
        os.close(fd)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        pass

    def reply(self, code: int, body: dict[str, str]) -> None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == '/status':
            self.reply(200, status())
        else:
            self.reply(404, {'state': 'not_found'})

    def do_POST(self) -> None:
        if (self.path != '/reset' or self.headers.get('Origin') != ORIGIN
                or self.headers.get('X-GDDS-Reset') != 'confirm'
                or self.headers.get('Content-Length') != '0'
                or self.headers.get('Transfer-Encoding') is not None):
            self.reply(403, {'state': 'rejected'})
            return
        fd = acquire()
        if fd is None:
            self.reply(409, {'state': 'running'})
            return
        try:
            save({'state': 'running', 'stage': 'stopping'})
            threading.Thread(target=run, args=(fd,), daemon=True).start()
        except Exception:
            os.close(fd)
            raise
        self.reply(202, {'state': 'running'})


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 18991), Handler).serve_forever()
