"""Use existing systemd scopes to cancel commands including setsid descendants."""
from __future__ import annotations
import subprocess


class ScopedCommands:
    def __init__(self, session):
        self.session = session
        self.units = []
        self.sequence = 0

    @staticmethod
    def state(unit):
        result = subprocess.run(['systemctl', 'show', unit, '--property=LoadState', '--property=ActiveState'],
            capture_output=True, text=True, timeout=10, check=False)
        return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)

    def stop(self, unit):
        state = self.state(unit)
        if state.get('LoadState') == 'not-found':
            return
        result = subprocess.run(['systemctl', 'stop', unit], capture_output=True, timeout=20, check=False)
        state = self.state(unit)
        if result.returncode or state.get('ActiveState') not in ('inactive', 'failed') and state.get('LoadState') != 'not-found':
            raise RuntimeError('command scope did not stop')

    def close(self):
        errors = []
        for unit in reversed(self.units):
            try:
                self.stop(unit)
            except Exception as error:
                errors.append(error)
        if errors:
            raise RuntimeError('command scopes remain')

    def run(self, args, *, env, cwd, stdout, stderr, timeout):
        self.sequence += 1
        unit = f'gdds-directory-{self.session}-{self.sequence}.scope'
        if self.state(unit).get('LoadState') != 'not-found':
            raise RuntimeError('command scope already exists')
        self.units.append(unit)
        process = subprocess.Popen(['systemd-run', '--scope', '--quiet', '--collect',
            '--unit=' + unit, '--property=TimeoutStopSec=10s', '--', *map(str, args)],
            env=env, cwd=cwd, stdout=stdout, stderr=stderr, text=True)
        try:
            output, _ = process.communicate(timeout=timeout)
            code = process.returncode
        finally:
            # Scope membership survives setsid(), unlike a process group. systemd
            # stop waits for all command descendants before the caller can down
            # Compose or release the node. Failure keeps the unit registered.
            try:
                self.stop(unit)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
        return code, output
