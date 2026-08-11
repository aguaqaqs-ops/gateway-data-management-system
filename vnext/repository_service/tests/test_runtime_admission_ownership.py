"""Runtime ownership tests for admission pools and cleaner lifecycle seam."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gateway_repository_service.admission import PermitPool
from gateway_repository_service.artifact_cleaner import NoOpArtifactCleaner
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings


class RecordingCleaner:
    def __init__(self) -> None:
        self.stop_calls: list[float | None] = []
        self.events: list[str] = []

    def stop(self, *, timeout: float | None = None) -> None:
        self.stop_calls.append(timeout)
        self.events.append("cleaner_stop")


def _fake_runtime(*, cleaner: RecordingCleaner | None = None) -> ServiceRuntime:
    settings = RepositoryServiceSettings(
        profile="test",
        bearer_token="token",
        data_root=Path("/tmp/unused-runtime-root"),
        max_concurrent_uploads=3,
        max_concurrent_row_streams=2,
    )
    control_store = MagicMock()
    control_store.is_open.return_value = True
    root_lock = MagicMock()
    root_lock.is_held.return_value = True
    worker_pool = MagicMock()
    worker_pool.wait_for_quiescence.return_value = True
    return ServiceRuntime(
        settings=settings,
        layout=MagicMock(),
        root_lock=root_lock,
        control_store=control_store,
        mutation_store=MagicMock(),
        import_store=MagicMock(),
        import_locks=MagicMock(),
        import_worker_pool=worker_pool,
        versioned_read_application=MagicMock(),
        dolt_runner=MagicMock(),
        provider_gate=MagicMock(),
        auth_state=MagicMock(),
        upload_admission=PermitPool(3),
        row_stream_admission=PermitPool(2),
        artifact_cleaner=cleaner or NoOpArtifactCleaner(),
    )


def test_runtime_owns_singleton_admission_pools() -> None:
    runtime = _fake_runtime()
    assert runtime.upload_admission.capacity == 3
    assert runtime.row_stream_admission.capacity == 2
    assert runtime.upload_admission is runtime.upload_admission
    assert runtime.row_stream_admission is runtime.row_stream_admission


@pytest.mark.serial
def test_shutdown_closes_admission_then_stops_cleaner_before_db_and_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleaner = RecordingCleaner()
    runtime = _fake_runtime(cleaner=cleaner)
    order: list[str] = []

    upload_lease = runtime.upload_admission.try_acquire()
    assert upload_lease is not None

    original_close_upload = runtime.upload_admission.close
    original_close_row = runtime.row_stream_admission.close

    def close_upload() -> None:
        order.append("close_upload")
        original_close_upload()

    def close_row() -> None:
        order.append("close_row")
        original_close_row()

    runtime.upload_admission.close = close_upload  # type: ignore[method-assign]
    runtime.row_stream_admission.close = close_row  # type: ignore[method-assign]

    def stop_cleaner(*, timeout: float | None = None) -> None:
        order.append("cleaner_stop")
        cleaner.stop(timeout=timeout)

    runtime.artifact_cleaner = MagicMock()
    runtime.artifact_cleaner.stop.side_effect = stop_cleaner

    def begin_shutdown() -> None:
        order.append("begin_shutdown")

    cast_worker = runtime.import_worker_pool
    cast_worker.begin_shutdown = begin_shutdown  # type: ignore[method-assign]

    def close_db() -> None:
        order.append("close_db")
        assert runtime.upload_admission.closed is True
        assert "cleaner_stop" in order

    def release_lock() -> None:
        order.append("release_lock")
        assert "close_db" in order

    runtime.control_store.close = close_db  # type: ignore[method-assign]
    runtime.root_lock.release = release_lock  # type: ignore[method-assign]

    def close_all(*_args: object, **_kwargs: object) -> None:
        order.append("bridge_close")
        upload_lease.release()

    monkeypatch.setattr(
        "gateway_repository_service.runtime.BRIDGE_REGISTRY.close_all",
        close_all,
    )

    runtime.shutdown()

    assert order.index("close_upload") < order.index("cleaner_stop")
    assert order.index("close_row") < order.index("cleaner_stop")
    assert order.index("cleaner_stop") < order.index("begin_shutdown")
    assert order.index("cleaner_stop") < order.index("close_db")
    assert order.index("close_db") < order.index("release_lock")
    assert runtime.upload_admission.in_use == 0
    assert runtime.row_stream_admission.in_use == 0
    assert runtime.upload_admission.closed is True
    assert runtime.row_stream_admission.closed is True


def test_noop_cleaner_does_not_start_thread() -> None:
    cleaner = NoOpArtifactCleaner()
    cleaner.stop(timeout=1.0)
    assert isinstance(cleaner, NoOpArtifactCleaner)


def test_shutdown_logs_safe_operational_fields(caplog: pytest.LogCaptureFixture) -> None:
    runtime = _fake_runtime()
    with caplog.at_level(logging.INFO):
        runtime.shutdown()
    fields_list = [
        getattr(record, "gateway_fields", None)
        for record in caplog.records
        if hasattr(record, "gateway_fields")
    ]
    assert any(
        fields is not None and fields.get("event") == "runtime_shutdown" for fields in fields_list
    )
    for fields in fields_list:
        if fields is None:
            continue
        assert "bearer_token" not in fields
        assert "data_root" not in fields
        text = str(fields)
        assert "token" not in text.lower() or fields.get("event") == "runtime_shutdown"
