"""Focused checks for the deployment-only reset controller."""

import http.client
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import reset_manager as manager


class ResetManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        manager.STATUS = root / 'status.json'
        manager.LOCK = root / 'reset.lock'
        manager.COMMAND = root / 'reset-a'
        manager.COMMAND.write_text('#!/bin/sh\necho stopping\nsleep 0.4\necho checking\nexit 0\n')
        manager.COMMAND.chmod(0o700)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), manager.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        deadline = time.monotonic() + 3
        while manager.status()['state'] == 'running' and time.monotonic() < deadline:
            time.sleep(0.02)
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.tmp.cleanup()

    def request(self, method, path, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        conn.request(method, path, body=b'' if method == 'POST' else None, headers=headers or {})
        response = conn.getresponse()
        data = json.loads(response.read())
        result = response.status, data
        conn.close()
        return result

    def test_fixed_target_origin_concurrency_and_retry(self):
        valid = {'Origin': manager.ORIGIN, 'X-GDDS-Reset': 'confirm'}
        self.assertEqual(self.request('POST', '/reset?project=b', valid)[0], 403)
        self.assertEqual(self.request('POST', '/reset', {'Origin': 'https://invalid', 'X-GDDS-Reset': 'confirm'})[0], 403)
        self.assertEqual(self.request('POST', '/reset', valid)[0], 202)
        self.assertEqual(self.request('POST', '/reset', valid)[0], 409)
        self.assertEqual(self.request('GET', '/status')[1]['state'], 'running')
        deadline = time.monotonic() + 3
        while manager.status()['state'] == 'running' and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(manager.status()['state'], 'success')
        manager.COMMAND.write_text('#!/bin/sh\nexit 1\n')
        self.assertEqual(self.request('POST', '/reset', valid)[0], 202)
        deadline = time.monotonic() + 3
        while manager.status()['state'] == 'running' and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(manager.status()['state'], 'failed')
        manager.COMMAND.write_text('#!/bin/sh\nexit 0\n')
        self.assertEqual(self.request('POST', '/reset', valid)[0], 202)
        deadline = time.monotonic() + 3
        while manager.status()['state'] == 'running' and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(manager.status()['state'], 'success')

    def test_interrupted_operation_is_not_reported_as_success(self):
        manager.save({'state': 'running', 'stage': 'provisioning'})
        self.assertEqual(manager.status(), {'state': 'failed', 'stage': 'interrupted'})

    def test_unreadable_status_fails_closed(self):
        manager.STATUS.write_text('{')
        self.assertEqual(manager.status(), {'state': 'failed', 'stage': 'status-unreadable'})


if __name__ == '__main__':
    unittest.main()
