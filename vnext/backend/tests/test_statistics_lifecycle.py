"""Production telemetry activation, bounded shutdown and business failure isolation."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway_backend.app import create_app
from gateway_backend.bootstrap import composition
from gateway_backend.bootstrap.statistics import BackendStatistics, build_statistics_sink
from gateway_backend.infrastructure.control_db import initialize_and_verify_control_db
from tests.support.runtime_settings import TEST_SESSION_TOKEN, make_backend_settings, prepare_backend_runtime_paths

pytestmark = pytest.mark.unit


@pytest.mark.serial
@pytest.mark.parametrize('fault', ['disabled', 'invalid_config', 'corrupt'])
def test_statistics_failure_does_not_change_business_readiness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str) -> None:
    prepare_backend_runtime_paths(tmp_path)
    settings = make_backend_settings(tmp_path, control_db_path=tmp_path / 'control/control.sqlite3')
    if fault == 'disabled':
        monkeypatch.setenv('GATEWAY_STATISTICS_ENABLED', 'false')
    elif fault == 'invalid_config':
        monkeypatch.setenv('GATEWAY_STATISTICS_SAMPLE_INTERVAL_SECONDS', 'bad')
    else:
        sink = build_statistics_sink(settings.deployment_config, 'backend')
        sink.store.path.parent.mkdir(parents=True)
        sink.store.path.write_bytes(b'invalid sqlite')
    import json
    session_document = json.loads(settings.session_file.read_text())
    session_document['sessions'][0]['permissions'].append('statistics_read_group')
    settings.session_file.write_text(json.dumps(session_document))
    original = composition.prepare_backend_runtime
    monkeypatch.setattr(composition, 'prepare_backend_runtime',
        lambda configured: original(configured, skip_repository_ready_probe=True))
    with TestClient(create_app(settings)) as client:
        assert client.get('/readyz').status_code == 200
        assert client.get('/healthz').json() == {'status': 'ok'}
        health = client.get('/v1/statistics/group', headers={'Authorization': f'Bearer {TEST_SESSION_TOKEN}'})
        assert health.status_code == 200
        assert health.json()['health']['quality'] == 'unavailable'
        assert str(tmp_path) not in health.text
    if fault == 'corrupt':
        assert sink.store.path.read_bytes() == b'invalid sqlite'


@pytest.mark.serial
def test_active_lifecycle_persists_samples_and_releases_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('GATEWAY_STATISTICS_SAMPLE_INTERVAL_SECONDS', '.02')
    monkeypatch.setenv('GATEWAY_STATISTICS_FLUSH_SECONDS', '.02')
    settings = make_backend_settings(tmp_path)
    initialize_and_verify_control_db(settings.control_db_path)
    lifecycle = BackendStatistics(settings.deployment_config, settings.control_db_path, 'http://127.0.0.1:9', 'test')
    lifecycle.start()
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if lifecycle.sink.health.written >= 2:
                break
            time.sleep(.01)
        assert lifecycle.sink.health.available
        with sqlite3.connect(lifecycle.sink.store.path) as db:
            assert db.execute('SELECT count(*) FROM resource_samples WHERE role="backend"').fetchone()[0] > 0
            assert db.execute('SELECT count(*) FROM storage_observations WHERE category="filesystem"').fetchone()[0] > 0
        assert lifecycle.http.sample_interval_seconds == .02
    finally:
        lifecycle.close()
    assert lifecycle.sink.store.connection is None
    assert lifecycle._thread is not None and not lifecycle._thread.is_alive()


def test_periodic_thread_start_failure_still_closes_sink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import Mock
    import threading
    settings = make_backend_settings(tmp_path)
    lifecycle = BackendStatistics(settings.deployment_config, settings.control_db_path, 'http://127.0.0.1:9', 'test')
    monkeypatch.setattr(lifecycle.sink, 'start', lambda: None)
    close = Mock()
    monkeypatch.setattr(lifecycle.sink, 'close', close)
    monkeypatch.setattr(threading.Thread, 'start', Mock(side_effect=RuntimeError('no thread')))
    lifecycle.start()
    lifecycle.close()
    assert lifecycle._thread is None
    assert lifecycle.collection_failures == 1
    close.assert_called_once()
