"""Focused Docker ownership and setsid cancellation; node 05, outer node lock."""
import argparse
import importlib.util
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
SPEC = importlib.util.spec_from_file_location('directory_journey', SCRIPTS / 'real_journey.py')
JOURNEY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(JOURNEY)


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, timeout=30).strip()


class RuntimeBoundaries(unittest.TestCase):
    def setUp(self):
        self.assertEqual(socket.gethostname(), 'gw-dms-test-05')
        self.assertTrue(Path('/home/dev/gdds-node-busy.d').is_dir(), 'caller must own node')

    def test_reject_existing_stopped_tool_and_project_resources(self):
        with tempfile.TemporaryDirectory(prefix='directory-runtime-', dir=JOURNEY.TMP) as folder:
            root = Path(folder)
            session = 'focused-' + str(os.getpid())
            args = argparse.Namespace(head=JOURNEY.git('rev-parse', 'HEAD'), session=session,
                config=str(root / 'config.json'), evidence_dir=str(root / 'evidence'))
            journey = JOURNEY.Journey(args)
            foreign_id = docker('create', '--pull', 'never', '--name', journey.container, 'nginx:1.28.0')
            try:
                # Exercise the real finish branch after private creation and
                # ownership acquisition, while the outer node lock stays held.
                # This isolated marker prevents a test from releasing the node.
                test_marker = root / 'owned-node-marker'
                test_marker.mkdir()
                (test_marker / session).write_text('purpose=focused-collision\n')
                journey.private = root / 'private'
                journey.private.mkdir(mode=0o700)
                journey.owned = True
                with patch.object(JOURNEY, 'BUSY', test_marker):
                    with self.assertRaises(ValueError):
                        journey.reject_tool_collision()
                    self.assertEqual(journey.finish(1), 1)
                self.assertFalse(test_marker.exists())
                self.assertEqual(journey.result['original_exit'], 1)
                self.assertEqual(journey.result['cleanup_status'], 'passed')
                self.assertTrue(journey.result['stages']['J7']['occupancy_released'])
                self.assertEqual(docker('inspect', '--format', '{{.Id}}', foreign_id), foreign_id)
            finally:
                docker('rm', foreign_id)
            for kind in ('container', 'network', 'volume'):
                with self.subTest(resource=kind):
                    args.evidence_dir = str(root / ('evidence-' + kind))
                    owner = JOURNEY.Journey(args)
                    project = session + '-' + kind
                    label = 'com.docker.compose.project=' + project
                    if kind == 'container':
                        identity = docker('create', '--pull', 'never', '--label', label, 'nginx:1.28.0')
                    else:
                        identity = docker(kind, 'create', '--label', label, project)
                    try:
                        with self.assertRaises(ValueError):
                            owner.empty_project(project)
                        self.assertEqual(owner.finish(1), 1)
                        if kind == 'container':
                            self.assertEqual(docker('inspect', '--format', '{{.Id}}', identity), identity)
                        else:
                            self.assertTrue(docker(kind, 'inspect', identity))
                    finally:
                        if kind == 'container':
                            docker('rm', identity)
                        else:
                            docker(kind, 'rm', identity)

    def test_port_check_rejects_listener_and_accepts_closed_connection(self):
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', 0))
            port = server.getsockname()[1]
            server.listen()
            with self.assertRaises(OSError):
                JOURNEY.check_free_port(port)
            with socket.create_connection(('127.0.0.1', port)) as client:
                connection, _ = server.accept()
                connection.close()
                self.assertEqual(client.recv(1), b'')
        JOURNEY.check_free_port(port)

    def test_timeout_and_interrupt_stop_detached_management_helper(self):
        with tempfile.TemporaryDirectory(prefix='directory-command-', dir=JOURNEY.TMP) as folder:
            root = Path(folder)
            env = dict(os.environ, PYTHONPATH=str(JOURNEY.ROOT / 'directory/service'), PYTHONDONTWRITEBYTECODE='1')
            heartbeat = root / 'heartbeat'
            helper = root / 'helper.py'
            helper.write_text("import os,time,pathlib\np=pathlib.Path(" + repr(str(heartbeat)) + ")\nwhile True:\n p.write_text(str(os.getpid())+' '+str(time.time_ns()))\n time.sleep(.02)\n")
            invocation = [sys.executable, '-B', '-c', 'from gdds_directory.provision import _management_command; import os,sys; _management_command([sys.executable,"-B",sys.argv[1]],dict(os.environ))', str(helper)]
            for mode in ('timeout', 'interrupt'):
                with self.subTest(mode=mode):
                    commands = JOURNEY._process_module.ScopedCommands('focused-cancel-' + str(os.getpid()) + '-' + mode)
                    def interrupt(_signum, _frame):
                        raise InterruptedError('focused cancellation')
                    old = signal.signal(signal.SIGALRM, interrupt)
                    try:
                        if mode == 'interrupt':
                            signal.setitimer(signal.ITIMER_REAL, 1.0)
                        with (root / (mode + '.log')).open('w') as output:
                            with self.assertRaises(subprocess.TimeoutExpired if mode == 'timeout' else InterruptedError):
                                commands.run(invocation, env=env, cwd=JOURNEY.ROOT, stdout=output, stderr=output,
                                    timeout=1.0 if mode == 'timeout' else 30)
                        self.assertTrue(heartbeat.is_file(), 'real management helper must have run')
                        before = heartbeat.read_text()
                        pid = int(before.split()[0])
                        time.sleep(.15)
                        self.assertEqual(heartbeat.read_text(), before, 'no writes after scope cancellation')
                        process = Path('/proc') / str(pid) / 'stat'
                        self.assertTrue(not process.exists() or process.read_text().split()[2] == 'Z')
                        commands.close()
                    finally:
                        signal.setitimer(signal.ITIMER_REAL, 0)
                        signal.signal(signal.SIGALRM, old)
                        commands.close()


if __name__ == '__main__':
    unittest.main()
