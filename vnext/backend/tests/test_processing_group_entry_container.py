"""Real fixed Nginx header, inode and graceful HUP wiring; business auth has its own owner."""
from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import threading
import time
from typing import Any

import httpx
import pytest

from gateway_backend.processing_group_config import DeviceDirectory, DeviceDirectoryEntry, ProcessingGroupsConfig
from gateway_backend.device_identity import device_route_key

pytestmark = [pytest.mark.integration, pytest.mark.serial]
SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures/processing-groups/v1'


def _port() -> int:
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return int(listener.getsockname()[1])


def test_real_entry_routes_exact_headers_and_keeps_upload_download_across_hup(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which('docker') is None:
        pytest.skip('docker required for entry wiring')
    monkeypatch.syspath_prepend(str(SCRIPTS))
    entry = importlib.import_module('processing_group_entry')
    download_started, upload_started, release = threading.Event(), threading.Event(), threading.Event()
    received: list[bytes] = []
    refused: list[int] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == '/v1/download':
                self.send_response(200)
                self.send_header('Content-Length', '10')
                self.end_headers()
                self.wfile.write(b'start')
                self.wfile.flush()
                download_started.set()
                if release.wait(20):
                    self.wfile.write(b'ended')
                    self.wfile.flush()
                return
            if self.path.startswith('/v1/refused/'):
                status = int(self.path.rsplit('/', 1)[1])
                refused.append(status)
                raw = b'{"code":"RESOURCE_NOT_FOUND","message":"backend refusal","details":null}'
                self.send_response(status)
                self.send_header('X-Gateway-Entry-Rejection', 'route-not-loaded')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if self.path == '/v1/device-context':
                device = 'new' if self.headers.get('X-Gateway-Device-Key') == device_route_key('new') else 'old'
                payload = {'environment_id': groups.environment_id, 'group_id': 'group-a',
                    'gateway_device_external_key': device, 'business_project_id': 'project', 'repository_id': 'repository-' + device}
            else:
                payload = {'group_id': 'group-a'}
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:
            first = self.rfile.read(1)
            upload_started.set()
            rest = self.rfile.read(int(self.headers['Content-Length']) - 1)
            received.append(first + rest)
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    groups = ProcessingGroupsConfig.load(FIXTURES / 'groups.json')
    groups = replace(groups, entry=replace(groups.entry, listen_address='127.0.0.1',
        listen_port=_port(), management_port=_port(), image=os.environ.get('GATEWAY_ENTRY_IMAGE', 'nginx:1.28.0')),
        groups=(replace(groups.groups[0], backend_port=server.server_port),))
    directory = DeviceDirectory(1, groups.environment_id, (DeviceDirectoryEntry('old', 'group-a', True),))
    tmp_path.chmod(0o755)
    (tmp_path / 'versions').mkdir()
    (tmp_path / 'versions').chmod(0o755)
    digest, raw = entry.render_entry(groups, directory)
    entry.atomic_write(tmp_path / 'versions' / (digest + '.conf'), raw)
    entry.atomic_write(tmp_path / 'nginx.conf', raw)
    runtime = entry.EntryRuntime(groups, tmp_path, 'entry-' + tmp_path.name.lower().replace('_', '-')[:45])
    url = f'http://127.0.0.1:{groups.entry.listen_port}'
    key = device_route_key('old')
    uploader: threading.Thread | None = None
    upload_results: list[int] = []
    try:
        runtime.validate('nginx.conf')
        up = runtime.compose('up', '-d', '--no-build', '--pull', 'never', 'entry')
        assert up.returncode == 0, up.stderr
        deadline = time.monotonic() + 10
        while True:
            try:
                assert runtime.probe(key) == {'config_digest': digest, 'group_id': 'group-a'}
                break
            except entry.Incomplete:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        container = runtime.container_id()
        for headers, status in [([], 422), ([('X-Gateway-Device-Key', key.upper())], 422),
                ([('X-Gateway-Device-Key', key), ('X-Gateway-Device-Key', key)], 422),
                ([('X-Gateway-Device-Key', 'a' * 64)], 404)]:
            rejected = httpx.get(url + '/v1/ping', headers=headers)
            assert rejected.status_code == status
            assert rejected.headers['Content-Type'].startswith('application/json')
            assert rejected.json()['code'] == ('RESOURCE_NOT_FOUND' if status == 404 else 'REQUEST_VALIDATION_FAILED')
        with pytest.raises(entry.EntryRoutePending):
            entry.request_json(url + '/v1/device-context', key='a' * 64, route_pending=True)
        for status in (401, 403, 404):
            def rejected_public(timeout: float) -> None:
                entry.request_json(url + '/v1/refused/' + str(status), key=key, timeout=timeout, route_pending=True)
            with pytest.raises(entry.Incomplete) as refusal:
                runtime.confirm_loaded(digest, key=key, group='group-a', confirm=rejected_public)
            assert not isinstance(refusal.value, entry.EntryRoutePending)
        assert refused == [401, 403, 404]
        assert httpx.get(url + '/internal/v1/statistics/group').status_code == 404
        assert httpx.get(url + '/openapi.json').status_code == 404

        def upload() -> None:
            def data() -> Any:
                yield b'x'
                if release.wait(20):
                    yield b'y' * 65535
            try:
                response = httpx.post(url + '/v1/upload', headers={'X-Gateway-Device-Key': key, 'Content-Length': '65536'},
                    content=data(), timeout=25)
                upload_results.append(response.status_code)
            except Exception:
                upload_results.append(0)
        with httpx.stream('GET', url + '/v1/download', headers={'X-Gateway-Device-Key': key}, timeout=25) as stream:
            chunks = stream.iter_bytes(chunk_size=5)
            assert next(chunks) == b'start'
            assert download_started.wait(5)
            uploader = threading.Thread(target=upload, daemon=True)
            uploader.start()
            assert upload_started.wait(5), 'request body was buffered instead of forwarded'
            newer = replace(directory, devices=(*directory.devices, DeviceDirectoryEntry('new', 'group-a', True)))
            new_digest, new = entry.render_entry(groups, newer)
            def confirm_public(timeout: float) -> None:
                assert entry.request_json(url + '/v1/device-context', key=device_route_key('new'), timeout=timeout, route_pending=True) == {
                    'environment_id': groups.environment_id, 'group_id': 'group-a', 'gateway_device_external_key': 'new',
                    'business_project_id': 'project', 'repository_id': 'repository-new'}
            runtime.publish(new_digest, new, key=device_route_key('new'), group='group-a', confirm=confirm_public)
            assert runtime.container_id() == container
            assert entry.request_json(url + '/v1/ping', key=device_route_key('new')) == {'group_id': 'group-a'}
            assert entry.request_json(url + '/v1/ping', key=key) == {'group_id': 'group-a'}
            with pytest.raises(entry.Busy):
                runtime.publish(digest, raw, key=key, group='group-a')
            release.set()
            assert b''.join(chunks) == b'ended'
        uploader.join(10)
        assert not uploader.is_alive()
        assert upload_results == [200]
        assert received == [b'x' + b'y' * 65535]
    finally:
        release.set()
        if uploader is not None:
            uploader.join(10)
        logs = runtime.compose('logs', '--no-color', 'entry')
        print(logs.stdout)
        down = runtime.compose('down', '--remove-orphans')
        server.shutdown()
        server.server_close()
        thread.join(5)
        assert down.returncode == 0, down.stderr
