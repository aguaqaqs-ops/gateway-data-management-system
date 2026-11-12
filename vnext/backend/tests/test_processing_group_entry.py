"""Bounded host publication semantics; no Docker or Dolt for pure decisions."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import importlib
from pathlib import Path
import runpy
import subprocess
from typing import Any

import pytest

from gateway_backend.processing_group_config import DeviceDirectory, DeviceDirectoryEntry, ProcessingGroupsConfig

pytestmark = pytest.mark.unit
SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures/processing-groups/v1'


@pytest.fixture
def modules(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, dict[str, Any]]:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    entry = importlib.import_module('processing_group_entry')
    cli = runpy.run_path(str(SCRIPTS / 'manage-processing-groups.py'))
    return entry, cli


def config() -> ProcessingGroupsConfig:
    return ProcessingGroupsConfig.load(FIXTURES / 'groups.json')


def test_renderer_is_fixed_upstream_strict_key_and_stream_safe(modules: tuple[Any, dict[str, Any]]) -> None:
    entry, _ = modules
    groups = config()
    reserved = DeviceDirectory(1, groups.environment_id, (DeviceDirectoryEntry('设备', groups.groups[0].group_id, False),))
    _, before = entry.render_entry(groups, reserved)
    digest, after = entry.render_entry(groups, replace(reserved, devices=(replace(reserved.devices[0], enabled=True),)))
    assert reserved.devices[0].route_key.encode() not in before
    assert reserved.devices[0].route_key.encode() in after
    assert ('"config_digest":"' + digest + '"').encode() in after
    assert b'"~^[0-9a-f]{64}$"' in after
    for directive in (b'proxy_request_buffering off;', b'proxy_buffering off;', b'proxy_cache off;',
            b'proxy_next_upstream off;', b'client_max_body_size 0;', b'listen 127.0.0.1:'):
        assert directive in after
    assert b'worker_shutdown_timeout' not in after
    assert b'location /internal' not in after


@pytest.mark.parametrize('failure', ['validate', 'signal', 'unconfirmed', 'retiring'])
def test_failed_publication_preserves_loaded_route_and_never_kills_streams(
        modules: tuple[Any, dict[str, Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    entry, _ = modules
    groups = config()
    directory = DeviceDirectory(1, groups.environment_id, ())
    old_digest, old = entry.render_entry(groups, directory)
    (tmp_path / 'nginx.conf').write_bytes(old)
    new_digest, new = entry.render_entry(groups, replace(directory, devices=(DeviceDirectoryEntry('new', groups.groups[0].group_id, True),)))
    runtime = entry.EntryRuntime(groups, tmp_path, 'entry-test')
    monkeypatch.setattr(runtime, 'probe', lambda key='', **kwargs: {'config_digest': old_digest, 'group_id': ''})
    monkeypatch.setattr(runtime, 'retiring_workers', lambda: failure == 'retiring')
    commands: list[tuple[str, ...]] = []
    def validate(name: str) -> None:
        if failure == 'validate':
            raise entry.Incomplete('invalid candidate')
    def compose(*args: str) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 1 if failure == 'signal' else 0, '', '')
    monkeypatch.setattr(runtime, 'validate', validate)
    monkeypatch.setattr(runtime, 'compose', compose)
    error = entry.Busy if failure == 'retiring' else entry.Incomplete
    with pytest.raises(error):
        runtime.publish(new_digest, new, key='a' * 64, group=groups.groups[0].group_id, timeout=0)
    assert (tmp_path / 'nginx.conf').read_bytes() == (new if failure == 'unconfirmed' else old)
    if failure in ('signal', 'unconfirmed'):
        assert (tmp_path / 'previous.conf').read_bytes() == old
    assert all('kill' not in command for command in commands)
    if failure in ('validate', 'retiring'):
        assert not commands


def test_retry_uses_actual_loaded_version_after_interrupted_confirmation(
        modules: tuple[Any, dict[str, Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entry, _ = modules
    groups = config()
    directory = DeviceDirectory(1, groups.environment_id, ())
    digest, raw = entry.render_entry(groups, directory)
    (tmp_path / 'nginx.conf').write_bytes(b'unconfirmed disk candidate')
    runtime = entry.EntryRuntime(groups, tmp_path, 'entry-test')
    monkeypatch.setattr(runtime, 'probe', lambda key='', **kwargs: {'config_digest': digest, 'group_id': 'group-a'})
    monkeypatch.setattr(runtime, 'compose', lambda *args: pytest.fail('exact loaded replay must not reload'))
    runtime.publish(digest, raw, key='a' * 64, group='group-a')
    assert (tmp_path / 'nginx.conf').read_bytes() == raw


def test_session_append_is_exact_scope_and_preserves_expiry(modules: tuple[Any, dict[str, Any]]) -> None:
    _, cli = modules
    now = datetime.now(UTC)
    row = {'token': 'token', 'actor_id': 'actor', 'gateway_device_external_key': 'device',
        'business_project_id': 'project', 'permissions': ['workspace_read'], 'expires_at': (now + timedelta(hours=1)).isoformat()}
    old = {'sessions': [row]}
    raw, token = cli['merge_sessions'](old, old, device='device', project='project', now=now)
    assert token == 'token' and raw.count(b'"token":"token"') == 1
    for change in ({'business_project_id': 'other'}, {'expires_at': None}, {'permissions': ['admin']}):
        with pytest.raises(ValueError):
            cli['merge_sessions'](old, {'sessions': [{**row, **change}]}, device='device', project='project', now=now)
    with pytest.raises(ValueError):
        cli['merge_sessions']({'sessions': []}, {'sessions': [{**row, 'expires_at': (now - timedelta(seconds=1)).isoformat()}]},
            device='device', project='project', now=now)


def test_hot_add_reserves_before_effect_and_replays_after_partial_failure(
        modules: tuple[Any, dict[str, Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse
    import json
    _, cli = modules
    raw = json.loads((FIXTURES / 'groups.json').read_bytes())
    groups_file = tmp_path / 'groups.json'
    directory_file = tmp_path / 'device-directory.json'
    session_dir = tmp_path / 'sessions'
    session_dir.mkdir()
    (session_dir / 'session.json').write_text('{"sessions":[]}')
    internal = tmp_path / 'internal'
    internal.write_text('secret')
    raw['groups'][0].update(session_directory=str(session_dir), internal_token_file=str(internal))
    groups_file.write_text(json.dumps(raw))
    groups = cli['ProcessingGroupsConfig'].load(groups_file)
    directory_file.write_bytes(cli['DeviceDirectory'](1, groups.environment_id, ()).to_bytes())
    source = tmp_path / 'incoming.json'
    source.write_text(json.dumps({'sessions': [{'token': 'new-token', 'actor_id': 'actor',
        'gateway_device_external_key': 'new-device', 'business_project_id': 'project', 'permissions': ['workspace_read']}]}))
    args = argparse.Namespace(groups_file=groups_file, directory_file=directory_file, entry_directory=tmp_path,
        entry_project='entry-test', group=groups.groups[0].group_id, device='new-device', project='project', session_document=source)
    runtime_type = cli['EntryRuntime']
    events: list[str] = []
    first = True
    context = {'environment_id': groups.environment_id, 'group_id': args.group,
        'gateway_device_external_key': args.device, 'business_project_id': args.project, 'repository_id': 'repository'}
    def request(url: str, **kwargs: object) -> dict[str, object]:
        nonlocal first
        if url.endswith('/register'):
            events.append('register')
            reserved = cli['DeviceDirectory'].load(directory_file, known_groups=groups.group_ids)
            assert reserved.require_reservation(args.device, args.group).enabled is False
            if first:
                first = False
                raise cli['Incomplete']('response lost')
            return context
        if url.endswith('/v1/device-context'):
            events.append('context')
            return context
        return {}
    def publish(*args: object, **kwargs: object) -> None:
        assert json.loads(directory_file.read_text())['devices'][0]['enabled'] is True
        events.append('publish')
    monkeypatch.setitem(cli['add_device'].__globals__, 'request_json', request)
    monkeypatch.setattr(runtime_type, 'probe', lambda self, key='': {})
    monkeypatch.setattr(runtime_type, 'require_append_only', lambda self, raw: None)
    monkeypatch.setattr(runtime_type, 'retiring_workers', lambda self: False)
    monkeypatch.setattr(runtime_type, 'publish', publish)
    with pytest.raises(cli['Incomplete']):
        cli['add_device'](args, groups, runtime_type(groups, tmp_path, 'entry-test'))
    assert json.loads(directory_file.read_text())['devices'][0]['enabled'] is False
    assert json.loads((session_dir / 'session.json').read_text()) == {'sessions': []}
    assert cli['add_device'](args, groups, runtime_type(groups, tmp_path, 'entry-test'))['state'] == 'available'
    assert events == ['register', 'register', 'context', 'publish', 'context']
    assert len(json.loads((session_dir / 'session.json').read_text())['sessions']) == 1


def test_hot_publication_rejects_existing_device_or_upstream_rebinding(modules: tuple[Any, dict[str, Any]]) -> None:
    entry, _ = modules
    groups = config()
    directory = DeviceDirectory(1, groups.environment_id, (DeviceDirectoryEntry('old', 'group-a', True),))
    _, old = entry.render_entry(groups, directory)
    _, rebound = entry.render_entry(groups, replace(directory, devices=(replace(directory.devices[0], group_id='group-b'),)))
    with pytest.raises(entry.Incomplete):
        entry.require_append_only_routes(old, rebound)
    changed = replace(groups, groups=(replace(groups.groups[0], backend_port=9999), *groups.groups[1:]))
    with pytest.raises(entry.Incomplete):
        entry.require_append_only_routes(old, entry.render_entry(changed, directory)[1])
    _, appended = entry.render_entry(groups, replace(directory, devices=(*directory.devices, DeviceDirectoryEntry('new', 'group-b', True))))
    entry.require_append_only_routes(old, appended)


@pytest.mark.parametrize('state,code', [('unreserved', 1), ('reserved', 1), ('registered', 1), ('routing-pending', 1), ('available', 0)])
def test_status_exit_code_reports_actual_availability_without_writing(
        modules: tuple[Any, dict[str, Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str], state: str, code: int) -> None:
    import sys
    _, cli = modules
    groups = tmp_path / 'groups.json'
    directory = tmp_path / 'device-directory.json'
    groups.write_bytes((FIXTURES / 'groups.json').read_bytes())
    directory.write_bytes((FIXTURES / 'device-directory.json').read_bytes())
    original = directory.read_bytes()
    monkeypatch.setattr(sys, 'argv', ['manage-processing-groups.py', 'status-device', '--groups-file', str(groups),
        '--directory-file', str(directory), '--entry-directory', str(tmp_path), '--entry-project', 'entry-test', '--device', 'device'])
    monkeypatch.setitem(cli['main'].__globals__, 'status_device', lambda *args: {'state': state})
    assert cli['main']() == code
    assert directory.read_bytes() == original
    assert 'token' not in capsys.readouterr().out
