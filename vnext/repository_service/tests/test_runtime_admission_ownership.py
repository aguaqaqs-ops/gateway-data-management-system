"""Runtime ownership tests for admission pools and cleaner lifecycle seam."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE, UploadRequestHeaders
from gateway_repository_service.admission import InflightKeyGate, PermitPool, UploadCancelRegistry
from gateway_repository_service.artifact_cleaner import NoOpArtifactCleaner
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import ClaimResult, EffectRecord, EffectStatus, MutationStore
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.command import UploadArtifactCommand
from support.upload_harness import upload_sha256


class RecordingCleaner:
    def __init__(self) -> None:
        self.stop_calls: list[float | None] = []
        self.events: list[str] = []

    def stop(self, *, timeout: float | None = None) -> None:
        self.stop_calls.append(timeout)
        self.events.append("cleaner_stop")


def _fake_runtime(
    *,
    cleaner: RecordingCleaner | NoOpArtifactCleaner | MagicMock | None = None,
    grace: float = 0.2,
) -> ServiceRuntime:
    settings = RepositoryServiceSettings(
        profile="test",
        bearer_token="token",
        data_root=Path("/tmp/unused-runtime-root"),
        max_concurrent_uploads=3,
        max_concurrent_row_streams=2,
        import_shutdown_grace_seconds=grace,
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
        upload_inflight=InflightKeyGate(),
        upload_cancels=UploadCancelRegistry(),
        artifact_cleaner=cleaner or NoOpArtifactCleaner(),
    )


def test_runtime_owns_singleton_admission_pools() -> None:
    runtime = _fake_runtime()
    assert runtime.upload_admission.capacity == 3
    assert runtime.row_stream_admission.capacity == 2
    assert runtime.upload_admission is runtime.upload_admission
    assert runtime.row_stream_admission is runtime.row_stream_admission
    assert runtime.upload_inflight is runtime.upload_inflight
    assert runtime.upload_cancels is runtime.upload_cancels


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
        assert runtime.upload_admission.in_use == 0

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
    assert order.index("bridge_close") < order.index("close_db")
    assert order.index("cleaner_stop") < order.index("close_db")
    assert order.index("close_db") < order.index("release_lock")
    assert runtime.upload_admission.in_use == 0
    assert runtime.row_stream_admission.in_use == 0
    assert runtime.upload_admission.closed is True
    assert runtime.row_stream_admission.closed is True


@pytest.mark.serial
def test_shutdown_cancels_active_upload_and_drains_permit_before_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _fake_runtime(grace=1.0)
    order: list[str] = []
    settings = RepositoryServiceSettings(
        profile="test",
        bearer_token="token",
        data_root=tmp_path / "data-root",
        max_concurrent_uploads=1,
        min_free_disk_bytes=1,
        min_free_disk_fraction=0.01,
    )
    layout = DurableLayout.create_service(settings.data_root)
    store = MagicMock(spec=MutationStore)
    store.hash_idempotency_key = MutationStore.hash_idempotency_key
    store.claim_or_lookup.return_value = ClaimResult(
        idempotency_id=1,
        is_new=True,
        fingerprint=b"fp",
        effect=None,
        terminal_not_published=False,
    )
    store.allocate_pending.return_value = EffectRecord(
        effect_id=1,
        idempotency_id=1,
        resource_id=uuid4(),
        status=EffectStatus.PENDING,
        response_status=None,
        response_body=None,
    )
    body_entered = threading.Event()
    upload_done = threading.Event()
    upload_error: list[BaseException] = []

    async def blocking_body() -> AsyncIterator[bytes]:
        body_entered.set()
        while True:
            await asyncio.sleep(0.01)
            yield b""

    command = UploadArtifactCommand(
        settings=settings,
        layout=layout,
        mutation_store=store,
        upload_admission=runtime.upload_admission,
        upload_inflight=runtime.upload_inflight,
        upload_cancels=runtime.upload_cancels,
        stopping=runtime.is_stopping,
    )
    payload = b"x"
    headers = UploadRequestHeaders(
        content_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        content_length=len(payload),
        idempotency_key="shutdown-upload",
        artifact_sha256=upload_sha256(payload),
    )

    def run_upload() -> None:
        try:
            with (
                patch(
                    "gateway_repository_service.upload_artifact.command.is_repository_visible",
                    return_value=True,
                ),
                patch(
                    "gateway_repository_service.upload_artifact.command.assert_upload_disk_admission",
                    return_value=None,
                ),
            ):
                asyncio.run(command.execute(uuid4(), headers, blocking_body()))
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            upload_error.append(exc)
        finally:
            upload_done.set()

    def close_db() -> None:
        order.append("close_db")
        assert runtime.upload_admission.in_use == 0

    def release_lock() -> None:
        order.append("release_lock")

    runtime.control_store.close = close_db  # type: ignore[method-assign]
    runtime.root_lock.release = release_lock  # type: ignore[method-assign]
    monkeypatch.setattr(
        "gateway_repository_service.runtime.BRIDGE_REGISTRY.close_all",
        lambda *_a, **_k: order.append("bridge_close"),
    )

    thread = threading.Thread(target=run_upload)
    thread.start()
    assert body_entered.wait(timeout=5.0)
    assert runtime.upload_admission.in_use == 1
    runtime.shutdown()
    assert upload_done.wait(timeout=5.0)
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert runtime.upload_admission.in_use == 0
    assert order.index("bridge_close") < order.index("close_db")
    assert order.index("close_db") < order.index("release_lock")
    assert upload_error
    assert isinstance(upload_error[0], ServiceError)
    assert upload_error[0].status_code == 503


@pytest.mark.serial
def test_shutdown_drains_row_stream_permit_before_db(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _fake_runtime(grace=1.0)
    order: list[str] = []
    lease = runtime.row_stream_admission.try_acquire()
    assert lease is not None

    def close_db() -> None:
        order.append("close_db")
        assert runtime.row_stream_admission.in_use == 0

    def release_lock() -> None:
        order.append("release_lock")

    runtime.control_store.close = close_db  # type: ignore[method-assign]
    runtime.root_lock.release = release_lock  # type: ignore[method-assign]

    def close_all(*_args: object, **_kwargs: object) -> None:
        order.append("bridge_close")

        def release_later() -> None:
            time.sleep(0.05)
            lease.release()

        threading.Thread(target=release_later).start()

    monkeypatch.setattr(
        "gateway_repository_service.runtime.BRIDGE_REGISTRY.close_all",
        close_all,
    )
    runtime.shutdown()
    assert order.index("bridge_close") < order.index("close_db")
    assert order.index("close_db") < order.index("release_lock")
    assert runtime.row_stream_admission.in_use == 0


def test_shutdown_cleaner_error_still_releases_lock_and_stops_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _fake_runtime()
    cleaner = MagicMock()
    cleaner.stop.side_effect = RuntimeError("cleaner boom")
    runtime.artifact_cleaner = cleaner
    worker = MagicMock()
    worker.wait_for_quiescence.return_value = True
    runtime.import_worker_pool = worker
    root_lock = MagicMock()
    root_lock.is_held.return_value = True
    runtime.root_lock = root_lock
    control_store = MagicMock()
    control_store.is_open.return_value = True
    runtime.control_store = control_store
    monkeypatch.setattr(
        "gateway_repository_service.runtime.BRIDGE_REGISTRY.close_all",
        lambda *_a, **_k: None,
    )
    with pytest.raises(RuntimeError, match="cleaner boom"):
        runtime.shutdown()
    worker.begin_shutdown.assert_called()
    worker.stop.assert_called()
    root_lock.release.assert_called_once()
    control_store.close.assert_called_once()


def test_shutdown_control_store_close_error_still_releases_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _fake_runtime()
    control_store = MagicMock()
    control_store.is_open.return_value = True
    control_store.close.side_effect = RuntimeError("close boom")
    runtime.control_store = control_store
    root_lock = MagicMock()
    root_lock.is_held.return_value = True
    runtime.root_lock = root_lock
    monkeypatch.setattr(
        "gateway_repository_service.runtime.BRIDGE_REGISTRY.close_all",
        lambda *_a, **_k: None,
    )
    with pytest.raises(RuntimeError, match="close boom"):
        runtime.shutdown()
    root_lock.release.assert_called_once()


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
